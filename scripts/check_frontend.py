#!/usr/bin/env python3
"""Syntax-check the frontends and their translations.

The page, kiosk and card are self-contained HTML/JS served as-is, so the
Python test suite never executes them: a stray duplicate declaration or a
missing translation key only shows up as a blank screen in front of the
pool. This runs in CI instead.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FRONTEND = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "pool_maintenance_tracker"
    / "frontend"
)
PAGES = ("page.html", "kiosk.html", "manual.html")
LANGUAGES = ("en", "pt", "es", "fr", "de", "it")

SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.DOTALL)
# S.a.b / K.c — the shapes the frontends use to reach into the string bundle
KEY_RE = re.compile(r"\bS\.(report|kiosk|roles|tiles|units|modes)\.([a-z_0-9]+)|\bK\.([a-z_0-9]+)")


def check_syntax(errors: list[str]) -> None:
    """Every inline script and the card must parse under node."""
    targets: list[tuple[str, str]] = [("card.js", (FRONTEND / "card.js").read_text())]
    for name in PAGES:
        text = (FRONTEND / name).read_text()
        for index, body in enumerate(SCRIPT_RE.findall(text)):
            # the injected config marker is not valid JS on its own
            targets.append((f"{name} script #{index + 1}", body.replace('"__', '"x__')))

    for label, source in targets:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
            handle.write(source)
            path = handle.name
        result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        Path(path).unlink()
        if result.returncode != 0:
            errors.append(f"{label}: {_first_useful_line(result.stderr)}")


# Home Assistant loads card.js as an ES module, so it runs in strict mode.
# Parsing it is not enough: a card that throws on load, or that stops
# defining its element, shows up in Lovelace as "Custom element doesn't
# exist" and nowhere else.
CARD_HARNESS = """
const defined = [];
globalThis.HTMLElement = class {};
globalThis.customElements = { define: (name) => defined.push(name), get: () => undefined };
globalThis.window = globalThis;
globalThis.document = { createElement: () => ({ style: {}, classList: { add() {} } }) };
await import(SPECIFIER);
if (!defined.includes("pool-maintenance-card")) {
  console.error("card.js did not define pool-maintenance-card (defined: " + defined + ")");
  process.exit(1);
}
"""


def _first_useful_line(stderr: str) -> str:
    """Node prints a banner and a stack; the first real line is the point."""
    for line in stderr.splitlines():
        if "did not define" in line or "Error" in line:
            return line.strip()
    return "failed to load as a module"


def check_card_defines_its_element(errors: list[str]) -> None:
    """Load the card the way a browser does and check it registers."""
    with tempfile.TemporaryDirectory() as folder:
        card = Path(folder) / "card.mjs"
        card.write_text((FRONTEND / "card.js").read_text())
        harness = Path(folder) / "harness.mjs"
        harness.write_text(CARD_HARNESS.replace("SPECIFIER", json.dumps(card.as_uri())))
        result = subprocess.run(["node", str(harness)], capture_output=True, text=True, cwd=folder)
    if result.returncode != 0:
        errors.append(f"card.js: {_first_useful_line(result.stderr)}")


def check_strings(errors: list[str]) -> None:
    """Every key a frontend reads must exist in all six bundles."""
    sources = {name: (FRONTEND / name).read_text() for name in (*PAGES, "card.js")}
    for language in LANGUAGES:
        bundle = json.loads((FRONTEND / "strings" / f"{language}.json").read_text())
        for name, text in sources.items():
            for section, key, kiosk_key in KEY_RE.findall(text):
                path = ("kiosk", kiosk_key) if kiosk_key else (section, key)
                if path[1] not in bundle.get(path[0], {}):
                    errors.append(f"{language}.json: missing {path[0]}.{path[1]} (used in {name})")
            if "S.impact_salt" in text and "impact_salt" not in bundle:
                errors.append(f"{language}.json: missing impact_salt (used in {name})")
        for status in ("low", "ideal", "high"):
            if status not in bundle["report"].get("status", {}):
                errors.append(f"{language}.json: missing report.status.{status}")


def main() -> int:
    errors: list[str] = []
    check_syntax(errors)
    check_card_defines_its_element(errors)
    check_strings(errors)
    if errors:
        for error in sorted(set(errors)):
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("frontend ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
