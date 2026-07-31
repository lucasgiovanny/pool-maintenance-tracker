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
# S.a.b — the long way into the string bundle, used from anywhere
SECTION_RE = re.compile(r"\bS\.(report|kiosk|roles|tiles|units|modes|maintenance)\.([a-z_0-9]+)")
# Every page also takes a one-letter shorthand for the section it works in,
# and the same letter means different things in different files.
ALIASES = {
    "kiosk.html": ("K", "kiosk"),
    "manual.html": ("M", "manual"),
    "page.html": ("M", "maintenance"),
}


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
            used = list(SECTION_RE.findall(text))
            if name in ALIASES:
                letter, section = ALIASES[name]
                shorthand = re.compile(rf"\b{letter}\.([a-z_0-9]+)")
                used += [(section, key) for key in shorthand.findall(text)]
            for section, key in used:
                if key not in bundle.get(section, {}):
                    errors.append(f"{language}.json: missing {section}.{key} (used in {name})")
            if "S.impact_salt" in text and "impact_salt" not in bundle:
                errors.append(f"{language}.json: missing impact_salt (used in {name})")
        for status in ("low", "ideal", "high"):
            if status not in bundle["report"].get("status", {}):
                errors.append(f"{language}.json: missing report.status.{status}")


def check_ids(errors: list[str]) -> None:
    """Every element a page reaches for by id must actually be there.

    The pages are one file of markup and one of script, and nothing checks
    that they agree: a renamed id shows up as a page that half works in front
    of the pool. Ids the script creates itself count as declared.
    """
    for name in PAGES:
        text = (FRONTEND / name).read_text()
        declared = set(re.findall(r'\bid="([\w-]+)"', text))
        declared.update(re.findall(r'\.id\s*=\s*"([\w-]+)"', text))
        for used in sorted(set(re.findall(r'getElementById\("([\w-]+)"\)', text))):
            if used not in declared:
                errors.append(f'{name}: getElementById("{used}") has no such id')


PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
IDENTIFIER_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\Z")


def check_translations(errors: list[str]) -> None:
    """The two rules Home Assistant enforces on every translation string.

    No leading or trailing space, and every {…} has to be a placeholder it
    can substitute — which makes a braced example (a JSON snippet, say) a
    validation failure rather than documentation.
    """
    folder = FRONTEND.parent / "translations"
    for path in sorted(folder.glob("*.json")):
        stack = [(json.loads(path.read_text()), "")]
        while stack:
            node, trail = stack.pop()
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                where = f"{trail}.{key}" if trail else key
                if isinstance(value, str):
                    if value != value.strip():
                        errors.append(f"{path.name}: padded string at {where}")
                    for found in PLACEHOLDER_RE.findall(value):
                        if not IDENTIFIER_RE.match(found):
                            errors.append(
                                f"{path.name}: {{{found}}} at {where} is not a placeholder "
                                "Home Assistant can substitute"
                            )
                else:
                    stack.append((value, where))


def main() -> int:
    errors: list[str] = []
    check_syntax(errors)
    check_card_defines_its_element(errors)
    check_strings(errors)
    check_ids(errors)
    check_translations(errors)
    if errors:
        for error in sorted(set(errors)):
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("frontend ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
