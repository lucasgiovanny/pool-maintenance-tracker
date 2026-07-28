/* Pool Maintenance Tracker — Lovelace card
 * Shows one pool at a glance: alerts, equipment toggles, task status,
 * and shortcuts to the public logging page.
 */

const TOGGLE_DOMAINS = ["switch", "input_boolean", "light", "fan"];
const REFRESH_MS = 30000;

function fireEvent(node, type, detail) {
  node.dispatchEvent(new CustomEvent(type, {
    detail: detail, bubbles: true, composed: true, cancelable: false
  }));
}

class PoolMaintenanceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._timer = null;
    this._loading = false;
  }

  setConfig(config) {
    this._config = config || {};
    this._data = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._load();
      this._timer = setInterval(() => this._load(), REFRESH_MS);
    } else if (this._data) {
      this._render();
    }
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {};
  }

  async _entryId() {
    if (this._config.entry) return this._config.entry;
    const pools = await this._hass.callWS({ type: "pool_maintenance_tracker/pools" });
    if (!pools.length) throw new Error("no pool");
    return pools[0].entry_id;
  }

  async _load() {
    if (this._loading || !this._hass) return;
    this._loading = true;
    try {
      const entryId = await this._entryId();
      this._data = await this._hass.callWS({
        type: "pool_maintenance_tracker/status", entry_id: entryId
      });
      this._error = null;
    } catch (error) {
      this._error = error && error.message ? error.message : String(error);
    }
    this._loading = false;
    this._render();
  }

  /* ---------------- helpers ---------------- */
  _t(path, fallback) {
    const strings = (this._data && this._data.strings) || {};
    return path.split(".").reduce((node, key) =>
      (node && node[key] !== undefined ? node[key] : undefined), strings) ?? fallback;
  }

  _locale() {
    const language = (this._data && this._data.language) || "en";
    return language === "pt" ? "pt-PT" : language;
  }

  _daysAgo(iso) {
    const S = this._data.strings.report;
    if (!iso) return S.never;
    const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (days <= 0) return S.today;
    if (days === 1) return S.day_ago;
    return S.days_ago.replace("{days}", days);
  }

  _shortDate(iso) {
    return new Date(iso).toLocaleDateString(this._locale(),
      { day: "2-digit", month: "2-digit" });
  }

  _taskLabel(task) {
    const S = this._data.strings;
    return S.tiles[task.key] || S.report.values[task.key] || task.key;
  }

  _overdueDays(task) {
    if (!task.next) return null;
    return Math.max(0, Math.floor((Date.now() - new Date(task.next).getTime()) / 86400000));
  }

  _openMoreInfo(entityId) {
    if (entityId) fireEvent(this, "hass-more-info", { entityId: entityId });
  }

  _toggle(item, event) {
    event.stopPropagation();
    if (!TOGGLE_DOMAINS.includes(item.domain)) {
      this._openMoreInfo(item.entity_id);
      return;
    }
    this._hass.callService(item.domain, "toggle", { entity_id: item.entity_id });
  }

  /* ---------------- render ---------------- */
  _render() {
    if (!this._data) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">${
        this._error ? this._error : "…"}</div>${this._styles()}</ha-card>`;
      return;
    }
    const data = this._data;
    const S = data.strings;
    const report = data.report || {};
    const roles = report.roles || {};
    const values = report.values || {};
    const ids = report.entity_ids || {};
    const tasks = report.tasks || [];
    const due = tasks.filter(task => task.due);
    const acidLow = values.acid_tank_level === "quarter";

    /* header ------------------------------------------------------- */
    const probe = (data.live || {}).temperature;
    const temp = probe ? probe.value : values.water_temperature;
    const tempUnit = (probe && probe.unit) || S.units.water_temperature;

    const subtitleBits = [];
    if (roles.pool_system) {
      subtitleBits.push(S.roles.pool_system + " " +
        (roles.pool_system.state === "on"
          ? S.report.state_on.toLowerCase() : S.report.state_off.toLowerCase()));
    }
    if (due.length) {
      subtitleBits.push(due.length + " " + S.kiosk.overdue_count);
    }

    /* alerts ------------------------------------------------------- */
    const alertLines = due.map(task => {
      const days = this._overdueDays(task);
      return this._taskLabel(task) + " — " + (task.last && days !== null
        ? S.kiosk.overdue_days.replace("{days}", days)
        : S.kiosk.never_recorded);
    });
    if (acidLow) {
      alertLines.push(S.report.values.acid_tank_level + " — " + S.acid_levels.quarter);
    }

    /* toggles ------------------------------------------------------ */
    const toggles = ["pool_system", "heat_pump", "pump", "pool_light"]
      .filter(role => roles[role]).slice(0, 2);

    /* rows --------------------------------------------------------- */
    const rows = [];
    if (values.chlorinator_mode !== undefined || values.chlorinator_output !== undefined) {
      const bits = [];
      if (values.chlorinator_mode !== undefined) {
        bits.push(S.modes[values.chlorinator_mode] || values.chlorinator_mode);
      }
      if (values.chlorinator_output !== undefined) {
        bits.push(values.chlorinator_output + " " + S.units.chlorinator_output);
      }
      rows.push({
        name: S.kiosk.chlorinator, value: bits.join(" · "),
        entity: ids.chlorinator_mode || ids.chlorinator_output
      });
    }
    tasks.forEach(task => {
      const badge = task.due
        ? { text: S.kiosk.overdue_days.replace("{days}", this._overdueDays(task) ?? 0), due: true }
        : (task.next ? { text: this._shortDate(task.next), due: false } : null);
      let value = this._daysAgo(task.last);
      if (task.key === "salt_added" && values.salt_added !== undefined && task.last) {
        value += " · " + values.salt_added + " " + S.units.salt_added;
      }
      rows.push({
        name: this._taskLabel(task), value: value, badge: badge,
        entity: ids["last_" + task.key] || ids[task.key],
        warn: task.due || !task.last
      });
    });

    /* html --------------------------------------------------------- */
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="head">
          <div class="icon">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 6v7M15 6v7" />
              <path d="M3 16c1.5 0 1.5 1.4 3 1.4S7.5 16 9 16s1.5 1.4 3 1.4S13.5 16 15 16s1.5 1.4 3 1.4S19.5 16 21 16"/>
              <path d="M3 20c1.5 0 1.5 1.4 3 1.4S7.5 20 9 20s1.5 1.4 3 1.4S13.5 20 15 20s1.5 1.4 3 1.4S19.5 20 21 20"/>
            </svg>
          </div>
          <div class="titles">
            <div class="name">${this._escape(data.title)}</div>
            <div class="sub">${this._escape(subtitleBits.join(" · "))}</div>
          </div>
          ${temp !== undefined && temp !== null ? `<div class="temp" data-entity="${
            ids.water_temperature || ""}">${temp}<small>${tempUnit}</small></div>` : ""}
        </div>

        ${alertLines.length ? `<div class="alert">
          <svg viewBox="0 0 24 24"><path d="M12 8v5M12 17h.01"/>
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
          <div>${alertLines.map(line => `<div>${this._escape(line)}</div>`).join("")}</div>
        </div>` : ""}

        ${toggles.length ? `<div class="toggles">${toggles.map((role, index) => {
          const item = roles[role];
          const on = item.state === "on" || item.state === "open";
          const schedule = roles.filtration_schedule;
          let sub = on ? S.report.state_on : S.report.state_off;
          if (role === "pool_system" && on && schedule && schedule.next_change) {
            sub = S.kiosk.until.replace("{time}", new Date(schedule.next_change)
              .toLocaleTimeString(this._locale(), { hour: "2-digit", minute: "2-digit" }));
          }
          return `<div class="tile ${on ? "on" : ""}" data-toggle="${index}">
            <div class="tile-top">
              <span class="tile-name">${this._escape(item.name || S.roles[role])}</span>
              <span class="switch ${on ? "on" : ""}"><i></i></span>
            </div>
            <div class="tile-sub">${this._escape(sub)}</div>
          </div>`;
        }).join("")}</div>` : ""}

        <div class="rows">
          ${rows.map((row, index) => `
            <div class="row" data-row="${index}">
              <span class="row-name">${this._escape(row.name)}</span>
              ${row.badge ? `<span class="badge ${row.badge.due ? "due" : ""}">${
                this._escape(row.badge.text)}</span>` : ""}
              <span class="row-value ${row.warn ? "warn" : ""}">${this._escape(row.value)}</span>
            </div>`).join("")}
        </div>

        ${data.page_url ? `<div class="actions">
          <button data-open="log">${this._escape(S.tabs.log)}</button>
          <button data-open="history">${this._escape(S.tabs.history)}</button>
        </div>` : ""}
        ${this._styles()}
      </ha-card>`;

    /* events ------------------------------------------------------- */
    const root = this.shadowRoot;
    root.querySelectorAll("[data-toggle]").forEach(node => {
      const item = roles[toggles[Number(node.dataset.toggle)]];
      node.querySelector(".switch").addEventListener("click",
        event => this._toggle(item, event));
      node.addEventListener("click", () => this._openMoreInfo(item.entity_id));
    });
    root.querySelectorAll("[data-row]").forEach(node => {
      const row = rows[Number(node.dataset.row)];
      if (!row.entity) return;
      node.classList.add("clickable");
      node.addEventListener("click", () => this._openMoreInfo(row.entity));
    });
    const temperature = root.querySelector(".temp[data-entity]");
    if (temperature && temperature.dataset.entity) {
      temperature.classList.add("clickable");
      temperature.addEventListener("click",
        () => this._openMoreInfo(temperature.dataset.entity));
    }
    root.querySelectorAll("[data-open]").forEach(node => {
      node.addEventListener("click", () => {
        const suffix = node.dataset.open === "history" ? "#history" : "";
        window.open(data.page_url + suffix, "_blank", "noopener");
      });
    });
  }

  _escape(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  _styles() {
    return `<style>
      ha-card{padding:16px;display:block}
      .empty{color:var(--secondary-text-color);padding:8px 0}
      .clickable{cursor:pointer}

      .head{display:flex;align-items:center;gap:14px}
      .icon{
        width:52px;height:52px;border-radius:50%;flex:none;
        background:var(--state-icon-color,#0FA3B1);opacity:.9;
        display:flex;align-items:center;justify-content:center;
      }
      .icon svg{width:28px;height:28px;stroke:#fff;fill:none;stroke-width:1.8;stroke-linecap:round}
      .titles{flex:1;min-width:0}
      .name{font-size:1.3rem;font-weight:600;line-height:1.2}
      .sub{color:var(--secondary-text-color);font-size:.92rem;margin-top:2px}
      .temp{font-size:1.9rem;font-weight:500;white-space:nowrap}
      .temp small{font-size:.95rem;color:var(--secondary-text-color);margin-left:3px}

      .alert{
        display:flex;gap:10px;margin-top:14px;padding:10px 12px;border-radius:10px;
        background:rgba(233,185,79,.14);color:var(--warning-color,#E9B94F);
        font-size:.95rem;line-height:1.45;font-weight:500;
      }
      .alert svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;flex:none;margin-top:1px}

      .toggles{display:flex;gap:10px;margin-top:14px}
      .tile{
        flex:1;min-width:0;border:1px solid var(--divider-color);border-radius:12px;
        padding:10px 12px;cursor:pointer;
      }
      .tile.on{border-color:var(--primary-color)}
      .tile-top{display:flex;align-items:center;gap:8px}
      .tile-name{flex:1;min-width:0;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .tile-sub{color:var(--secondary-text-color);font-size:.88rem;margin-top:3px}
      .tile.on .tile-sub{color:var(--primary-color)}
      .switch{
        width:38px;height:22px;border-radius:11px;background:var(--disabled-text-color,#8c8c8c);
        flex:none;position:relative;transition:background .15s;
      }
      .switch.on{background:var(--primary-color)}
      .switch i{
        position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;
        background:#fff;transition:transform .15s;
      }
      .switch.on i{transform:translateX(16px)}

      .rows{margin-top:6px}
      .row{
        display:flex;align-items:center;gap:10px;padding:12px 0;
        border-bottom:1px solid var(--divider-color);
      }
      .row:last-child{border-bottom:none}
      .row-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .row-value{font-weight:500;white-space:nowrap}
      .row-value.warn{color:var(--warning-color,#E9B94F)}
      .badge{
        border-radius:999px;padding:2px 9px;font-size:.78rem;font-weight:500;white-space:nowrap;
        background:var(--secondary-background-color);color:var(--secondary-text-color);
      }
      .badge.due{background:rgba(233,185,79,.2);color:var(--warning-color,#E9B94F)}

      .actions{
        display:flex;gap:8px;margin-top:8px;padding-top:12px;
        border-top:1px solid var(--divider-color);
      }
      .actions button{
        flex:1;background:none;border:none;color:var(--primary-color);
        font:inherit;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
        padding:10px;border-radius:8px;cursor:pointer;
      }
      .actions button:hover{background:var(--secondary-background-color)}
    </style>`;
  }
}

customElements.define("pool-maintenance-card", PoolMaintenanceCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pool-maintenance-card",
  name: "Pool Maintenance Tracker",
  description: "Pool status, equipment and maintenance tasks at a glance.",
  documentationURL: "https://github.com/lucasgiovanny/pool-maintenance-tracker",
});
