/* Pool Maintenance Tracker — Lovelace card + visual editor
 * Pick exactly which items to show: equipment, readings, tasks, alerts
 * and a live countdown to the next schedule change.
 */

const TOGGLE_DOMAINS = ["switch", "input_boolean", "light", "fan"];
const TOGGLE_ROLES = ["pool_system", "heat_pump", "pump", "pool_light", "cover"];
/* An empty drum needs refilling; no drum at all is a decision, not a fault */
const ACID_ALERT_LEVELS = ["quarter", "empty"];

const READING_KEYS = ["ph", "free_chlorine", "salt_level", "water_temperature"];
const REFRESH_MS = 30000;

const GROUPS = ["general", "equipment", "readings", "tasks"];
const GENERAL_ITEMS = ["temperature", "alerts", "countdown", "filtration"];

const DEFAULTS = {
  entry: undefined,
  title: "",
  items: undefined,   /* undefined = everything the pool offers */
  only_due_tasks: false,
};

/* Editor labels — same six languages as the pages. */
const EDITOR_TEXT = {
  en: {
    entry: "Pool", entry_help: "Leave empty to use the only pool you have.",
    title: "Title (optional)", only_due_tasks: "Only show overdue tasks",
    general: "General", equipment: "Equipment", readings: "Water readings", tasks: "Tasks",
    temperature: "Water temperature (header)", alerts: "Alerts",
    countdown: "Schedule countdown", filtration: "Filtration suggestion", chlorinator: "Chlorinator", acid_tank: "Acid tank",
  },
  pt: {
    entry: "Piscina", entry_help: "Deixa vazio para usar a única piscina que tens.",
    title: "Título (opcional)", only_due_tasks: "Mostrar só tarefas em atraso",
    general: "Geral", equipment: "Equipamento", readings: "Leituras da água", tasks: "Tarefas",
    temperature: "Temperatura da água (cabeçalho)", alerts: "Alertas",
    countdown: "Contagem decrescente do horário", filtration: "Sugestão de filtração", chlorinator: "Clorador",
    acid_tank: "Depósito de ácido",
  },
  es: {
    entry: "Piscina", entry_help: "Déjalo vacío para usar la única piscina que tengas.",
    title: "Título (opcional)", only_due_tasks: "Mostrar solo tareas atrasadas",
    general: "General", equipment: "Equipamiento", readings: "Lecturas del agua", tasks: "Tareas",
    temperature: "Temperatura del agua (encabezado)", alerts: "Alertas",
    countdown: "Cuenta atrás del horario", filtration: "Sugerencia de filtración", chlorinator: "Clorador",
    acid_tank: "Depósito de ácido",
  },
  fr: {
    entry: "Piscine", entry_help: "Laissez vide pour utiliser votre seule piscine.",
    title: "Titre (facultatif)", only_due_tasks: "N'afficher que les tâches en retard",
    general: "Général", equipment: "Équipement", readings: "Mesures de l'eau", tasks: "Tâches",
    temperature: "Température de l'eau (en-tête)", alerts: "Alertes",
    countdown: "Compte à rebours de l'horaire", filtration: "Suggestion de filtration", chlorinator: "Électrolyseur",
    acid_tank: "Réservoir d'acide",
  },
  de: {
    entry: "Pool", entry_help: "Leer lassen, um den einzigen Pool zu verwenden.",
    title: "Titel (optional)", only_due_tasks: "Nur überfällige Aufgaben zeigen",
    general: "Allgemein", equipment: "Geräte", readings: "Wasserwerte", tasks: "Aufgaben",
    temperature: "Wassertemperatur (Kopfzeile)", alerts: "Warnungen",
    countdown: "Countdown des Zeitplans", filtration: "Filtrationsempfehlung", chlorinator: "Elektrolyseur",
    acid_tank: "Säuretank",
  },
  it: {
    entry: "Piscina", entry_help: "Lascia vuoto per usare l'unica piscina che hai.",
    title: "Titolo (facoltativo)", only_due_tasks: "Mostra solo attività in ritardo",
    general: "Generale", equipment: "Attrezzatura", readings: "Letture dell'acqua",
    tasks: "Attività", temperature: "Temperatura dell'acqua (intestazione)",
    alerts: "Avvisi", countdown: "Conto alla rovescia dell'orario",
    filtration: "Suggerimento di filtrazione",
    chlorinator: "Clorinatore", acid_tank: "Serbatoio dell'acido",
  },
};

function editorText(hass) {
  const language = (hass && hass.language ? hass.language : "en").split("-")[0];
  return EDITOR_TEXT[language] || EDITOR_TEXT.en;
}

function fireEvent(node, type, detail) {
  node.dispatchEvent(new CustomEvent(type, {
    detail: detail, bubbles: true, composed: true, cancelable: false
  }));
}

/* Everything this pool can show, grouped, in render order. */
function availableItems(data, text) {
  const S = data.strings;
  const report = data.report || {};
  const roles = report.roles || {};
  const values = report.values || {};

  const general = GENERAL_ITEMS.map(item => ({ value: item, label: text[item] }));

  const equipment = [];
  TOGGLE_ROLES.forEach(role => {
    if (roles[role]) {
      equipment.push({ value: "role:" + role, label: roles[role].name || S.roles[role] });
    }
  });
  if (values.chlorinator_mode !== undefined || values.chlorinator_output !== undefined) {
    equipment.push({ value: "chlorinator", label: text.chlorinator });
  }
  if (values.acid_tank_level !== undefined) {
    equipment.push({ value: "acid_tank", label: text.acid_tank });
  }
  if ((report.filter_pressure || {}).value !== undefined
      && (report.filter_pressure || {}).value !== null) {
    equipment.push({ value: "filter_pressure", label: S.report.filter_pressure });
  }
  (report.extra || []).forEach(item => {
    equipment.push({ value: "extra:" + item.entity_id, label: item.name });
  });

  const readings = READING_KEYS
    .filter(key => values[key] !== undefined || (data.live || {})[key === "salt_level"
      ? "salt" : key === "water_temperature" ? "temperature" : key])
    .map(key => ({ value: "value:" + key, label: S.report.values[key] || key }));

  const tasks = (report.tasks || []).map(task => ({
    value: "task:" + task.key,
    label: S.tiles[task.key] || S.report.values[task.key] || task.key,
  }));

  return { general, equipment, readings, tasks };
}

function allItemValues(available) {
  return GROUPS.reduce((all, group) =>
    all.concat(available[group].map(item => item.value)), []);
}

class PoolMaintenanceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._timer = null;
    this._tick = null;
    this._loading = false;
  }

  setConfig(config) {
    this._config = Object.assign({}, DEFAULTS, config || {});
    /* Cards written before per-item selection used show_* booleans. */
    if (!this._config.items && config && "show_temperature" in config) {
      this._legacy = config;
    }
    if (this._data) this._render();
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
    if (this._tick) clearInterval(this._tick);
    this._timer = this._tick = null;
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("pool-maintenance-card-editor");
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
        type: "pool_maintenance_tracker/status",
        entry_id: entryId,
        /* The card follows the Home Assistant UI language. */
        language: this._hass.language || "en",
      });
      this._error = null;
    } catch (error) {
      this._error = error && error.message ? error.message : String(error);
    }
    this._loading = false;
    this._render();
  }

  /* ---------------- helpers ---------------- */
  _locale() {
    if (this._hass && this._hass.language) return this._hass.language;
    return (this._data && this._data.language) || "en";
  }

  _selection(available) {
    if (this._config.items) return this._config.items;
    if (this._legacy) return this._fromLegacy(available);
    /* Nothing configured: show everything except the extra entities,
       which already have their place on the page and the kiosk. */
    return allItemValues(available).filter(value => !value.startsWith("extra:"));
  }

  _fromLegacy(available) {
    const legacy = this._legacy;
    const items = [];
    if (legacy.show_temperature !== false) items.push("temperature");
    if (legacy.show_alerts !== false) items.push("alerts");
    if (legacy.show_equipment !== false) {
      available.equipment
        .filter(item => item.value.startsWith("role:"))
        .forEach(item => items.push(item.value));
    }
    if (legacy.show_chlorinator !== false) items.push("chlorinator");
    if (legacy.show_tasks !== false) {
      available.tasks.forEach(item => items.push(item.value));
    }
    return items;
  }

  _rangeStatus(key, value) {
    const band = ((this._data.report || {}).ranges || {})[key];
    if (!band || value === undefined || value === null) return null;
    if (value < band.min) return "low";
    if (value > band.max) return "high";
    return "ideal";
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

  _relTime(iso) {
    const S = this._data.strings.kiosk;
    const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 3600) return S.minutes_short.replace("{n}", Math.max(1, Math.floor(seconds / 60)));
    if (seconds < 86400) return S.hours_short.replace("{n}", Math.floor(seconds / 3600));
    return this._daysAgo(iso);
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
    if (this._tick) { clearInterval(this._tick); this._tick = null; }
    if (!this._data) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">${
        this._error ? this._escape(this._error) : "…"}</div>${this._styles()}</ha-card>`;
      return;
    }
    const config = this._config;
    const data = this._data;
    const S = data.strings;
    const report = data.report || {};
    const roles = report.roles || {};
    const values = report.values || {};
    const ids = report.entity_ids || {};
    const tasks = report.tasks || [];
    const text = editorText(this._hass);
    const available = availableItems(data, text);
    const shown = new Set(this._selection(available));

    /* header ------------------------------------------------------- */
    const probe = (data.live || {}).temperature;
    const temp = probe ? probe.value : values.water_temperature;
    const tempUnit = (probe && probe.unit) || S.units.water_temperature;
    const showTemp = shown.has("temperature") && temp !== undefined && temp !== null;

    const due = tasks.filter(task => task.due);
    const subtitleBits = [];
    if (roles.pool_system) {
      subtitleBits.push(S.roles.pool_system + " " +
        (roles.pool_system.state === "on"
          ? S.report.state_on.toLowerCase() : S.report.state_off.toLowerCase()));
    }
    if (due.length) subtitleBits.push(due.length + " " + S.kiosk.overdue_count);

    /* alerts ------------------------------------------------------- */
    const alertLines = [];
    if (shown.has("alerts")) {
      due.forEach(task => {
        const days = this._overdueDays(task);
        alertLines.push(this._taskLabel(task) + " — " + (task.last && days !== null
          ? S.kiosk.overdue_days.replace("{days}", days)
          : S.kiosk.never_recorded));
      });
      if (ACID_ALERT_LEVELS.includes(values.acid_tank_level)) {
        alertLines.push(S.report.values.acid_tank_level + " — "
          + S.acid_levels[values.acid_tank_level]);
      }
    }

    /* countdown ---------------------------------------------------- */
    const schedule = roles.filtration_schedule;
    const countdown = shown.has("countdown") && schedule && schedule.next_change
      ? schedule : null;

    /* equipment toggles -------------------------------------------- */
    const toggles = TOGGLE_ROLES.filter(role => roles[role] && shown.has("role:" + role));

    /* rows --------------------------------------------------------- */
    const rows = [];
    if (shown.has("chlorinator")) {
      const bits = [];
      if (values.chlorinator_mode !== undefined) {
        bits.push(S.modes[values.chlorinator_mode] || values.chlorinator_mode);
      }
      if (values.chlorinator_output !== undefined) {
        bits.push(values.chlorinator_output + " " + S.units.chlorinator_output);
      }
      if (bits.length) {
        rows.push({
          name: text.chlorinator, value: bits.join(" · "),
          entity: ids.chlorinator_mode || ids.chlorinator_output
        });
      }
    }
    if (shown.has("acid_tank") && values.acid_tank_level !== undefined) {
      rows.push({
        name: S.report.values.acid_tank_level,
        value: S.acid_levels[values.acid_tank_level] || values.acid_tank_level,
        entity: ids.acid_tank_level,
        warn: ACID_ALERT_LEVELS.includes(values.acid_tank_level),
      });
    }
    READING_KEYS.forEach(key => {
      if (!shown.has("value:" + key)) return;
      const liveKey = key === "salt_level" ? "salt"
        : key === "water_temperature" ? "temperature" : key;
      const liveValue = (data.live || {})[liveKey];
      const value = liveValue ? liveValue.value : values[key];
      if (value === undefined || value === null) return;
      const name = S.report.values[key] || key;
      const unit = (liveValue && liveValue.unit) || S.units[key] || "";
      /* "pH 7.2 pH" reads silly — drop a unit that repeats the label. */
      const showUnit = unit && unit.toLowerCase() !== name.toLowerCase();
      const status = this._rangeStatus(key, value);
      rows.push({
        name: name,
        value: showUnit ? value + " " + unit : String(value),
        entity: ids[key],
        badge: status ? { text: S.report.status[status], status: status } : null,
        warn: status === "low" || status === "high",
      });
    });
    (report.extra || []).forEach(item => {
      if (!shown.has("extra:" + item.entity_id)) return;
      const onOff = item.state === "on" || item.state === "off";
      rows.push({
        name: item.name, entity: item.entity_id,
        value: onOff
          ? (item.state === "on" ? S.report.state_on : S.report.state_off)
            + " · " + this._relTime(item.last_changed)
          : item.state + (item.unit ? " " + item.unit : ""),
      });
    });
    /* Filtration rule of thumb — a suggestion, never a command */
    const filtration = report.filtration;
    if (shown.has("filtration") && filtration) {
      const scheduled = filtration.scheduled_hours;
      const hasSchedule = scheduled !== null && scheduled !== undefined;
      rows.push({
        name: hasSchedule ? S.report.filtration : S.report.filtration_recommended,
        value: S.report.hours.replace("{h}", hasSchedule ? scheduled : filtration.recommended_hours)
          + (hasSchedule
            ? " · " + S.report.recommended.replace("{h}", filtration.recommended_hours) : ""),
        entity: (roles.filtration_schedule || {}).entity_id,
      });
    }

    /* The filter's pressure decides its wash, so it belongs on the card */
    const pressure = report.filter_pressure;
    if (shown.has("filter_pressure") && pressure
        && pressure.value !== null && pressure.value !== undefined) {
      rows.push({
        name: S.report.filter_pressure,
        value: pressure.value + (pressure.unit ? " " + pressure.unit : "")
          + (pressure.rise_percent === null || pressure.rise_percent === undefined ? ""
            : " · " + S.report.pressure_rise.replace("{p}", pressure.rise_percent)),
        entity: pressure.entity_id,
        badge: pressure.due ? { text: S.report.wash_filter, due: true } : null,
        warn: !!pressure.due,
      });
    }

    tasks.forEach(task => {
      if (!shown.has("task:" + task.key)) return;
      if (config.only_due_tasks && !task.due) return;
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
        warn: task.due || !task.last,
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
            <div class="name">${this._escape(config.title || data.title)}</div>
            <div class="sub">${this._escape(subtitleBits.join(" · "))}</div>
          </div>
          ${showTemp ? `<div class="temp" data-entity="${
            ids.water_temperature || ""}">${temp}<small>${tempUnit}</small></div>` : ""}
        </div>

        ${alertLines.length ? `<div class="alert">
          <svg viewBox="0 0 24 24"><path d="M12 8v5M12 17h.01"/>
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
          <div>${alertLines.map(line => `<div>${this._escape(line)}</div>`).join("")}</div>
        </div>` : ""}

        ${countdown ? `<div class="countdown" data-entity="${countdown.entity_id}">
          <span class="cd-label">${this._escape(countdown.state === "on"
            ? S.card.turns_off : S.card.turns_on)}</span>
          <span class="cd-value" id="cd">—</span>
        </div>` : ""}

        ${toggles.length ? `<div class="toggles">${toggles.map((role, index) => {
          const item = roles[role];
          const on = item.state === "on" || item.state === "open";
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

        ${rows.length ? `<div class="rows">
          ${rows.map((row, index) => `
            <div class="row" data-row="${index}">
              <span class="row-name">${this._escape(row.name)}</span>
              ${row.badge ? `<span class="badge ${row.badge.due ? "due" : (row.badge.status || "")}">${
                this._escape(row.badge.text)}</span>` : ""}
              <span class="row-value ${row.warn ? "warn" : ""}">${this._escape(row.value)}</span>
            </div>`).join("")}
        </div>` : ""}
        ${this._styles()}
      </ha-card>`;

    /* events + countdown ------------------------------------------- */
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
    if (countdown) {
      const box = root.querySelector(".countdown");
      box.classList.add("clickable");
      box.addEventListener("click", () => this._openMoreInfo(countdown.entity_id));
      const target = new Date(countdown.next_change).getTime();
      const paint = () => {
        const total = Math.floor((target - Date.now()) / 1000);
        const node = root.getElementById ? root.getElementById("cd") : root.querySelector("#cd");
        if (!node) return;
        if (total <= 0) { node.textContent = "…"; this._load(); return; }
        let seconds = total;
        const days = Math.floor(seconds / 86400); seconds %= 86400;
        node.textContent = (days ? days + "d " : "")
          + String(Math.floor(seconds / 3600)).padStart(2, "0") + ":"
          + String(Math.floor((seconds % 3600) / 60)).padStart(2, "0") + ":"
          + String(seconds % 60).padStart(2, "0");
        box.classList.toggle("soon", total <= 3600);
      };
      paint();
      this._tick = setInterval(paint, 1000);
    }
  }

  _escape(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  _styles() {
    return `<style>
      *{box-sizing:border-box}
      ha-card{padding:16px;display:block}
      .empty{color:var(--secondary-text-color,#8a8f94);padding:8px 0}
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
      .sub{color:var(--secondary-text-color,#8a8f94);font-size:.92rem;margin-top:2px}
      .temp{font-size:1.9rem;font-weight:500;white-space:nowrap}
      .temp small{font-size:.95rem;color:var(--secondary-text-color,#8a8f94);margin-left:3px}

      .alert{
        display:flex;gap:10px;margin-top:14px;padding:10px 12px;border-radius:10px;
        background:rgba(233,185,79,.14);color:var(--warning-color,#E9B94F);
        font-size:.95rem;line-height:1.45;font-weight:500;
      }
      .alert svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;flex:none;margin-top:1px}

      .countdown{
        display:flex;align-items:center;gap:10px;margin-top:14px;
        padding:10px 12px;border-radius:10px;background:var(--secondary-background-color,rgba(127,127,127,.12));
      }
      .cd-label{color:var(--secondary-text-color,#8a8f94);font-size:.92rem;font-weight:500;flex:1}
      .cd-value{
        font-size:1.25rem;font-weight:600;font-variant-numeric:tabular-nums;
        color:var(--primary-color,#4fc3d7);
      }
      .countdown.soon .cd-value{color:var(--warning-color,#E9B94F)}

      .toggles{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
      .tile{
        flex:1 1 calc(50% - 5px);min-width:0;border:1px solid var(--divider-color,rgba(127,127,127,.35));
        border-radius:12px;padding:10px 12px;cursor:pointer;
      }
      .tile.on{border-color:var(--primary-color,#4fc3d7)}
      @supports (background:color-mix(in srgb,red 10%,transparent)){
        .tile.on{background:color-mix(in srgb,var(--primary-color,#4fc3d7) 8%,transparent)}
      }
      .tile-top{display:flex;align-items:center;gap:8px}
      .tile-name{flex:1;min-width:0;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .tile-sub{color:var(--secondary-text-color,#8a8f94);font-size:.88rem;margin-top:3px}
      .tile.on .tile-sub{color:var(--primary-color,#4fc3d7)}
      .switch{
        width:38px;height:22px;border-radius:11px;background:var(--disabled-text-color,#8c8c8c);
        flex:none;position:relative;transition:background .15s;
      }
      .switch.on{background:var(--primary-color,#4fc3d7)}
      .switch i{
        position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;
        background:#fff;transition:transform .15s;
      }
      .switch.on i{transform:translateX(16px)}

      .rows{margin-top:6px}
      .row{
        display:flex;align-items:center;gap:10px;padding:12px 0;
        border-bottom:1px solid var(--divider-color,rgba(127,127,127,.35));
      }
      .row:last-child{border-bottom:none}
      .row-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .row-value{font-weight:500;white-space:nowrap}
      .row-value.warn{color:var(--warning-color,#E9B94F)}
      .badge{
        border-radius:999px;padding:2px 9px;font-size:.78rem;font-weight:500;white-space:nowrap;
        background:var(--secondary-background-color,rgba(127,127,127,.12));color:var(--secondary-text-color,#8a8f94);
      }
      .badge.due,.badge.low,.badge.high{background:rgba(233,185,79,.2);color:var(--warning-color,#E9B94F)}
      .badge.ideal{background:rgba(47,204,139,.18);color:var(--success-color,#2FCC8B)}
    </style>`;
  }
}

/* ---------------------------------------------------------------------- */
/* Visual editor                                                           */
/* ---------------------------------------------------------------------- */

class PoolMaintenanceCardEditor extends HTMLElement {
  constructor() {
    super();
    this._pools = [];
    this._available = null;
    this._form = null;
  }

  setConfig(config) {
    this._config = Object.assign({}, DEFAULTS, config || {});
    this._loadAvailable();
    this._update();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    if (first) {
      this._loadPools();
      this._loadAvailable();
    }
  }

  async _loadPools() {
    try {
      this._pools = await this._hass.callWS({ type: "pool_maintenance_tracker/pools" });
    } catch (error) {
      this._pools = [];
    }
    this._update();
  }

  /* The option list depends on how this particular pool is set up. */
  async _loadAvailable() {
    if (!this._hass || !this._config) return;
    try {
      let entryId = this._config.entry;
      if (!entryId) {
        const pools = this._pools.length
          ? this._pools
          : await this._hass.callWS({ type: "pool_maintenance_tracker/pools" });
        if (!pools.length) return;
        entryId = pools[0].entry_id;
      }
      if (this._loadedFor === entryId) return;
      const data = await this._hass.callWS({
        type: "pool_maintenance_tracker/status",
        entry_id: entryId,
        language: this._hass.language || "en",
      });
      this._loadedFor = entryId;
      this._data = data;
      this._available = availableItems(data, editorText(this._hass));
    } catch (error) {
      this._available = null;
    }
    this._update();
  }

  _selectionFor(group) {
    const available = this._available[group].map(item => item.value);
    const items = this._config.items
      || (this._data ? allItemValues(this._available)
        .filter(value => !value.startsWith("extra:")) : []);
    return items.filter(value => available.includes(value));
  }

  _schema() {
    const text = editorText(this._hass);
    const schema = [
      {
        name: "entry",
        selector: {
          select: {
            mode: "dropdown",
            options: this._pools.map(pool => ({ value: pool.entry_id, label: pool.title })),
          },
        },
      },
      { name: "title", selector: { text: {} } },
    ];
    if (this._available) {
      GROUPS.forEach(group => {
        if (!this._available[group].length) return;
        schema.push({
          name: "group_" + group,
          selector: {
            select: {
              multiple: true, mode: "list", options: this._available[group],
            },
          },
        });
      });
    }
    schema.push({ name: "only_due_tasks", selector: { boolean: {} } });
    return schema;
  }

  _formData() {
    const data = {
      entry: this._config.entry,
      title: this._config.title,
      only_due_tasks: this._config.only_due_tasks,
    };
    if (this._available) {
      GROUPS.forEach(group => {
        data["group_" + group] = this._selectionFor(group);
      });
    }
    return data;
  }

  _update() {
    if (!this._config) return;
    if (!this._form) {
      this.innerHTML = "";
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", event => this._valueChanged(event));
      this.appendChild(this._form);
    }
    const text = editorText(this._hass);
    this._form.hass = this._hass;
    this._form.data = this._formData();
    this._form.schema = this._schema();
    this._form.computeLabel = schema => schema.name.startsWith("group_")
      ? text[schema.name.slice(6)]
      : (text[schema.name] || schema.name);
    this._form.computeHelper = schema =>
      schema.name === "entry" ? text.entry_help : undefined;
  }

  _valueChanged(event) {
    event.stopPropagation();
    const value = Object.assign({}, event.detail.value);
    const config = {
      type: (this._config && this._config.type) || "custom:pool-maintenance-card",
    };
    if (value.entry) config.entry = value.entry;
    if (value.title) config.title = value.title;
    if (value.only_due_tasks) config.only_due_tasks = true;
    if (this._available) {
      /* Store one flat list, in the card's own render order. */
      const items = [];
      GROUPS.forEach(group => {
        const selected = value["group_" + group] || [];
        this._available[group].forEach(item => {
          if (selected.includes(item.value)) items.push(item.value);
        });
      });
      config.items = items;
    } else if (this._config.items) {
      config.items = this._config.items;
    }
    this._config = Object.assign({}, this._config, config);
    if (config.entry !== this._loadedFor) this._loadAvailable();
    fireEvent(this, "config-changed", { config: config });
  }
}

customElements.define("pool-maintenance-card", PoolMaintenanceCard);
customElements.define("pool-maintenance-card-editor", PoolMaintenanceCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pool-maintenance-card",
  name: "Pool Maintenance Tracker",
  description: "Pool status, equipment and maintenance tasks at a glance.",
  documentationURL: "https://github.com/lucasgiovanny/pool-maintenance-tracker",
});
