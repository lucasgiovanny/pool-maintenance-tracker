/* Pool Maintenance Tracker — Lovelace card + visual editor
 * Equipment, readings, tasks, alerts and a live countdown to the next
 * schedule change, composed by the card. A dashboard picks the pool and the
 * layout, and may drop items it does not want — including the header.
 */

const TOGGLE_DOMAINS = ["switch", "input_boolean", "light", "fan"];
const TOGGLE_ROLES = ["pool_system", "heat_pump", "pump", "pool_light", "cover"];
/* One MDI icon per item key. An icon set on the entity itself wins. */
const ITEM_ICONS = {
  temperature: "mdi:thermometer-water",
  "value:water_temperature": "mdi:thermometer-water",
  "value:ph": "mdi:ph",
  "value:free_chlorine": "mdi:test-tube",
  "value:total_chlorine": "mdi:flask",
  "value:total_alkalinity": "mdi:water-percent",
  "value:cyanuric_acid": "mdi:shield-sun-outline",
  "value:calcium_hardness": "mdi:diamond-stone",
  "value:salt_level": "mdi:shaker-outline",
  chlorinator: "mdi:waves",
  acid_tank: "mdi:cup-water",
  filter_pressure: "mdi:gauge",
  filtration: "mdi:autorenew",
  "task:water_test": "mdi:test-tube",
  "task:chemistry_test": "mdi:beaker-check",
  "task:salt_added": "mdi:shaker",
  "task:filter_wash": "mdi:air-filter",
  "task:cell_clean": "mdi:lightning-bolt",
  "task:probe_calibration": "mdi:tune-variant",
  "task:acid_refill": "mdi:cup-water",
  "task:cleaning": "mdi:broom",
  "role:pool_system": "mdi:power",
  "role:heat_pump": "mdi:heat-pump",
  "role:pump": "mdi:pump",
  "role:pool_light": "mdi:lightbulb",
  "role:cover": "mdi:window-shutter",
  maintenance_mode: "mdi:account-wrench",
};

/* An empty drum needs refilling; no drum at all is a decision, not a fault */
const ACID_ALERT_LEVELS = ["quarter", "empty", "none"];

const READING_KEYS = ["ph", "free_chlorine", "total_chlorine", "total_alkalinity",
  "cyanuric_acid", "calcium_hardness", "salt_level", "water_temperature"];
const REFRESH_MS = 30000;
/* The maintenance sheet offers the same windows the page does, and 0 is
   the visit that runs until somebody ends it. */
const VISIT_PRESETS = [30, 60, 120, 240, 0];
const VISIT_DEFAULT_MINUTES = 60;

const GROUPS = ["general", "equipment", "readings", "tasks"];
const GENERAL_ITEMS = [
  "header", "temperature", "alerts", "maintenance_mode", "countdown", "filtration",
];

const DEFAULTS = {
  entry: undefined,
  title: "",
  only_due_tasks: false,
  show_icons: false,
  /* "list" packs rows for a column of cards; "tiles" spreads everything
     into kiosk-style minis, for a dashboard made of this card alone. */
  layout: "list",
  /* Item keys this dashboard does not want. Absent means everything, which
     is why it is a list of what to *drop*: order and grouping stay the
     card's business, and a dashboard only gets to say "not this one".
     Deliberately not the old `items` key — those linger in configs from
     when the card had ordering, and reviving the name would silently put
     stale lists back in charge. */
  hidden: [],
};

/* Editor labels — same six languages as the pages. */
const EDITOR_TEXT = {
  en: {
    entry: "Pool", entry_help: "Leave empty to use the only pool you have.",
    title: "Title (optional)", only_due_tasks: "Only show overdue tasks",
    general: "General", equipment: "Equipment", readings: "Water readings", tasks: "Tasks",
    temperature: "Water temperature (header)", alerts: "Alerts",
    countdown: "Schedule countdown", filtration: "Filtration hours", chlorinator: "Chlorinator", acid_tank: "Acid tank",
    layout: "Layout", layout_list: "List", layout_tiles: "Tiles",
    show_icons: "Show icons",
    shown: "Items shown", header: "Header (name and icon)",
  },
  pt: {
    entry: "Piscina", entry_help: "Deixa vazio para usar a única piscina que tens.",
    title: "Título (opcional)", only_due_tasks: "Mostrar só tarefas em atraso",
    general: "Geral", equipment: "Equipamento", readings: "Leituras da água", tasks: "Tarefas",
    temperature: "Temperatura da água (cabeçalho)", alerts: "Alertas",
    countdown: "Contagem decrescente do horário", filtration: "Horas de filtração", chlorinator: "Clorador",
    acid_tank: "Depósito de ácido",
    layout: "Disposição", layout_list: "Lista", layout_tiles: "Cartões",
    show_icons: "Mostrar ícones",
    shown: "Itens exibidos", header: "Cabeçalho (nome e ícone)",
  },
  es: {
    entry: "Piscina", entry_help: "Déjalo vacío para usar la única piscina que tengas.",
    title: "Título (opcional)", only_due_tasks: "Mostrar solo tareas atrasadas",
    general: "General", equipment: "Equipamiento", readings: "Lecturas del agua", tasks: "Tareas",
    temperature: "Temperatura del agua (encabezado)", alerts: "Alertas",
    countdown: "Cuenta atrás del horario", filtration: "Horas de filtración", chlorinator: "Clorador",
    acid_tank: "Depósito de ácido",
    layout: "Disposición", layout_list: "Lista", layout_tiles: "Tarjetas",
    show_icons: "Mostrar iconos",
    shown: "Elementos mostrados", header: "Encabezado (nombre e icono)",
  },
  fr: {
    entry: "Piscine", entry_help: "Laissez vide pour utiliser votre seule piscine.",
    title: "Titre (facultatif)", only_due_tasks: "N'afficher que les tâches en retard",
    general: "Général", equipment: "Équipement", readings: "Mesures de l'eau", tasks: "Tâches",
    temperature: "Température de l'eau (en-tête)", alerts: "Alertes",
    countdown: "Compte à rebours de l'horaire", filtration: "Heures de filtration", chlorinator: "Électrolyseur",
    acid_tank: "Réservoir d'acide",
    layout: "Disposition", layout_list: "Liste", layout_tiles: "Vignettes",
    show_icons: "Afficher les icônes",
    shown: "Éléments affichés", header: "En-tête (nom et icône)",
  },
  de: {
    entry: "Pool", entry_help: "Leer lassen, um den einzigen Pool zu verwenden.",
    title: "Titel (optional)", only_due_tasks: "Nur überfällige Aufgaben zeigen",
    general: "Allgemein", equipment: "Geräte", readings: "Wasserwerte", tasks: "Aufgaben",
    temperature: "Wassertemperatur (Kopfzeile)", alerts: "Warnungen",
    countdown: "Countdown des Zeitplans", filtration: "Filterstunden", chlorinator: "Elektrolyseur",
    acid_tank: "Säuretank",
    layout: "Anordnung", layout_list: "Liste", layout_tiles: "Kacheln",
    show_icons: "Symbole anzeigen",
    shown: "Angezeigte Elemente", header: "Kopfzeile (Name und Symbol)",
  },
  it: {
    entry: "Piscina", entry_help: "Lascia vuoto per usare l'unica piscina che hai.",
    title: "Titolo (facoltativo)", only_due_tasks: "Mostra solo attività in ritardo",
    general: "Generale", equipment: "Attrezzatura", readings: "Letture dell'acqua",
    tasks: "Attività", temperature: "Temperatura dell'acqua (intestazione)",
    alerts: "Avvisi", countdown: "Conto alla rovescia dell'orario",
    filtration: "Ore di filtrazione",
    chlorinator: "Clorinatore", acid_tank: "Serbatoio dell'acido",
    layout: "Disposizione", layout_list: "Elenco", layout_tiles: "Riquadri",
    show_icons: "Mostra icone",
    shown: "Elementi mostrati", header: "Intestazione (nome e icona)",
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

  /* Maintenance mode is only an item on pools that switched it on */
  const general = GENERAL_ITEMS
    .filter(item => item !== "maintenance_mode" || (report.maintenance_mode || {}).enabled)
    .map(item => ({
      value: item,
      label: item === "maintenance_mode" ? (S.maintenance || {}).title : text[item],
    }));

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
    this._pending = null;
    this._onVisible = null;
    this._loadedAt = 0;
    this._loading = false;
  }

  setConfig(config) {
    this._config = Object.assign({}, DEFAULTS, config || {});
    if (this._data) this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._start();
      this._load();
      return;
    }
    if (!this._data) return;
    /* Lovelace hands the card a new hass on every state change in the house.
       Repainting the same data is cheap, but what the card usually needs is
       fresh data: the pool state lives behind our own websocket command, so
       a state it shows having moved is the cue to go and fetch it. */
    if (this._moved()) this._soon(); else this._render();
  }

  /* Cards are detached and re-attached in ordinary use — switching view,
     closing the editor, a re-layout. disconnectedCallback stops the poll, so
     without starting it again here the card would freeze on whatever it last
     drew until the dashboard was reloaded. */
  connectedCallback() {
    this._start();
    if (this._hass && (!this._loadedAt || Date.now() - this._loadedAt > REFRESH_MS)) {
      this._load();
    }
  }

  disconnectedCallback() {
    this._stop();
  }

  _start() {
    if (!this._timer) this._timer = setInterval(() => this._load(), REFRESH_MS);
    if (!this._onVisible) {
      /* Background tabs get their timers throttled, and a phone waking up
         reconnects the websocket — either way, come back to a fresh card. */
      this._onVisible = () => {
        if (document.visibilityState === "visible") this._load();
      };
      document.addEventListener("visibilitychange", this._onVisible);
    }
  }

  _stop() {
    if (this._timer) clearInterval(this._timer);
    if (this._tick) clearInterval(this._tick);
    if (this._pending) clearTimeout(this._pending);
    this._timer = this._tick = this._pending = null;
    if (this._onVisible) {
      document.removeEventListener("visibilitychange", this._onVisible);
      this._onVisible = null;
    }
  }

  /* The states the card is currently drawing, as one comparable string */
  _stamp() {
    if (!this._hass) return "";
    const report = (this._data || {}).report || {};
    const ids = new Set(Object.values(report.entity_ids || {}));
    Object.values(report.roles || {}).forEach(role => {
      if (!role) return;
      if (role.entity_id) ids.add(role.entity_id);
      /* A schedule kept as separate entities moves when its hours do */
      (role.sources || []).forEach(id => ids.add(id));
    });
    (report.extra || []).forEach(item => ids.add(item.entity_id));
    if ((report.filter_pressure || {}).entity_id) ids.add(report.filter_pressure.entity_id);
    const states = this._hass.states || {};
    let stamp = "";
    ids.forEach(id => {
      stamp += id + "=" + (states[id] ? states[id].state : "?") + ";";
    });
    return stamp;
  }

  _moved() {
    const stamp = this._stamp();
    const moved = this._last !== undefined && stamp !== this._last;
    this._last = stamp;
    return moved;
  }

  /* One logged record moves a dozen entities at once — coalesce them */
  _soon() {
    if (this._pending) clearTimeout(this._pending);
    this._pending = setTimeout(() => {
      this._pending = null;
      this._load();
    }, 250);
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
    this._loadedAt = Date.now();
    /* Take the stamp from the data we just drew, or the next hass would look
       like a change and send us straight back for more. */
    this._last = this._stamp();
    this._render();
  }

  /* ---------------- helpers ---------------- */
  _locale() {
    if (this._hass && this._hass.language) return this._hass.language;
    return (this._data && this._data.language) || "en";
  }

  _selection(available) {
    /* The card still composes itself — where each thing goes, and next to
       what, is not configuration. That part shipped three times in one day
       and produced layout puzzles instead of dashboards. What a dashboard
       does get to say is "not this one", which cannot grow into a layout
       tool: everything shows unless it is named in `hidden`. */
    const hidden = new Set(this._config.hidden || []);
    return allItemValues(available).filter(value => !hidden.has(value));
  }

  _rangeStatus(key, value) {
    const band = ((this._data.report || {}).ranges || {})[key];
    if (!band || value === undefined || value === null) return null;
    if (value < band.min) return "low";
    if (value > band.max) return "high";
    return "ideal";
  }

  /* The tag for an item's icon, or "" with icons off / nothing sensible */
  _iconTag(key, entityId) {
    if (!this._config.show_icons) return "";
    const state = entityId && this._hass && this._hass.states
      ? this._hass.states[entityId] : null;
    const icon = (state && state.attributes && state.attributes.icon)
      || ITEM_ICONS[key]
      || (key && key.startsWith("extra:") ? "mdi:shape-outline" : "");
    return icon ? `<ha-icon class="item-icon" icon="${icon}"></ha-icon>` : "";
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

  /* What a piece of equipment is doing, in as many words as it has. A switch
     only knows that it is on; a heat pump knows whether it is working at this
     moment, and the temperature it is working towards. */
  _equipmentState(item) {
    const S = this._data.strings;
    if (!item.on) return S.report.state_off;
    const doing = item.action === "heating" ? S.report.state_heating
      : item.action === "cooling" ? S.report.state_cooling
      : S.report.state_on;
    if (item.target === null || item.target === undefined) return doing;
    return doing + " · " + S.report.target_temp.replace("{temp}",
      item.target + (item.target_unit ? " " + item.target_unit : ""));
  }

  /* ---------------- render ---------------- */
  _render() {
    /* A repaint would wipe the half-filled sheet under the user's finger,
       so the card holds still until the visit is started or called off. */
    if (this._sheet) return;
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

    /* The dialog has to be about the number on screen. A reading can come
       from our manual entity or from a linked probe — whichever measured
       last wins — so tapping opens whichever of the two that was. */
    const sourceOf = key => ((report.current || {})[key] || {}).entity_id || ids[key] || "";

    /* header ------------------------------------------------------- */
    /* A card that is one of several about the same pool does not need to
       repeat its name and icon; hiding the header leaves just the content. */
    const head = shown.has("header");
    const probe = (data.live || {}).temperature;
    const reading = (report.current || {}).water_temperature;
    const temp = reading ? reading.value : values.water_temperature;
    const tempUnit = (reading && reading.unit) || (probe && probe.unit)
      || S.units.water_temperature;
    const showTemp = shown.has("temperature") && temp !== undefined && temp !== null;

    const due = tasks.filter(task => task.due);
    const subtitleBits = [];
    if (roles.pool_system) {
      subtitleBits.push(S.roles.pool_system + " " +
        (roles.pool_system.on
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
      if (values.acid_tank_level === "none") {
        alertLines.push(S.report.alert_acid_missing);
      } else if (ACID_ALERT_LEVELS.includes(values.acid_tank_level)) {
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
          key: "chlorinator",
          name: text.chlorinator, value: bits.join(" · "),
          entity: ids.chlorinator_mode || ids.chlorinator_output
        });
      }
    }
    if (shown.has("acid_tank") && values.acid_tank_level !== undefined) {
      rows.push({
        key: "acid_tank",
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
      const reading = (report.current || {})[key];
      const liveValue = (data.live || {})[liveKey];
      const value = reading ? reading.value : values[key];
      if (value === undefined || value === null) return;
      const name = S.report.values[key] || key;
      const unit = (liveValue && liveValue.unit) || S.units[key] || "";
      /* "pH 7.2 pH" reads silly — drop a unit that repeats the label. */
      const showUnit = unit && unit.toLowerCase() !== name.toLowerCase();
      const status = this._rangeStatus(key, value);
      rows.push({
        key: "value:" + key,
        name: name,
        value: showUnit ? value + " " + unit : String(value),
        entity: sourceOf(key),
        badge: status ? { text: S.report.status[status], status: status } : null,
        warn: status === "low" || status === "high",
      });
    });
    (report.extra || []).forEach(item => {
      if (!shown.has("extra:" + item.entity_id)) return;
      /* null means "not an on/off thing" — that one shows its own value */
      const onOff = item.on !== null && item.on !== undefined;
      rows.push({
        key: "extra:" + item.entity_id,
        name: item.name, entity: item.entity_id,
        value: onOff
          ? (item.on ? S.report.state_on : S.report.state_off)
            + " · " + this._relTime(item.last_changed)
          : item.state + (item.unit ? " " + item.unit : ""),
      });
    });
    /* Today's filtration: the hours planned, and the hours actually run */
    const filtration = report.filtration;
    if (shown.has("filtration") && filtration) {
      const scheduled = filtration.scheduled_hours;
      const actual = filtration.actual_hours;
      const hasActual = actual !== null && actual !== undefined;
      const hasSchedule = scheduled !== null && scheduled !== undefined;
      rows.push({
        key: "filtration",
        name: S.report.filtration,
        value: hasSchedule
          ? S.report.hours.replace("{h}", scheduled)
            + (hasActual ? " · " + S.report.actual_today.replace("{h}", actual) : "")
          : S.report.actual_today.replace("{h}", actual),
        entity: (roles.filtration_schedule || {}).entity_id,
      });
    }

    /* The filter's pressure decides its wash, so it belongs on the card */
    const pressure = report.filter_pressure;
    if (shown.has("filter_pressure") && pressure
        && pressure.value !== null && pressure.value !== undefined) {
      rows.push({
        key: "filter_pressure",
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
        : (task.next
          ? { text: S.report.next_due.replace("{date}", this._shortDate(task.next)), due: false }
          : null);
      let value = task.last ? this._daysAgo(task.last) : "–";
      if (task.key === "salt_added" && values.salt_added !== undefined && task.last) {
        value += " · " + values.salt_added + " " + S.units.salt_added;
      }
      rows.push({
        key: "task:" + task.key,
        name: this._taskLabel(task), value: value, badge: badge,
        entity: ids["last_" + task.key] || ids[task.key],
        warn: task.due || !task.last,
      });
    });

    /* html --------------------------------------------------------- */
    const tiles = config.layout === "tiles";

    /* Tiles layout borrows the kiosk's two anchors: the temperature as a
       hero tile, and today's filtration cycle as a bar. Both stay inside
       HA's design language — same borders, same theme variables. */
    const hero = tiles && showTemp;
    let cycle = null;
    if (tiles && shown.has("filtration") && schedule && schedule.week) {
      const todayIndex = (new Date().getDay() + 6) % 7;  /* Monday = 0 */
      const blocks = schedule.week[todayIndex] || [];
      const minutesOf = text => {
        const [hours, minutes] = text.split(":").map(Number);
        return hours * 60 + minutes;
      };
      if (blocks.length) {
        const now = new Date();
        cycle = {
          blocks: blocks.map(([from, to]) => {
            const start = minutesOf(from);
            const end = Math.max(minutesOf(to), start + 10);
            return { left: start / 1440 * 100, width: (end - start) / 1440 * 100 };
          }),
          now: (now.getHours() * 60 + now.getMinutes()) / 1440 * 100,
          header: blocks.length <= 2
            ? blocks.map(([from, to]) => from + " – " + to).join("  ·  ")
            : S.kiosk.blocks_total.replace("{n}", blocks.length).replace("{h}",
                Math.round(blocks.reduce((total, [from, to]) =>
                  total + Math.max(0, minutesOf(to) - minutesOf(from)), 0) / 6) / 10),
          sub: filtration && filtration.actual_hours !== null
              && filtration.actual_hours !== undefined
            ? S.report.actual_today.replace("{h}", filtration.actual_hours) : "",
        };
      }
    }
    /* The hero and the cycle bar already say what their minis would */
    const gridRows = rows.filter(row =>
      !(cycle && row.key === "filtration")
      && !(hero && row.key === "value:water_temperature"));

    /* Every block is placed by its rank in the configured order — the
       alert banner and the cycle bar included, or reordering them in the
       editor would silently do nothing. */
    const alertHtml = alertLines.length ? `<div class="alert">
          <svg viewBox="0 0 24 24"><path d="M12 8v5M12 17h.01"/>
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
          <div>${alertLines.map(line => `<div>${this._escape(line)}</div>`).join("")}</div>
        </div>` : "";
    const miniHtml = row => {
      /* Rows join auxiliary facts with " · " — in a tile the value
         must stay one big figure, so the rest drops to a sub line. */
      const [main, ...aux] = String(row.value).split(" · ");
      return `<div class="mini" data-row="${rows.indexOf(row)}">
        <div class="mini-name">${this._iconTag(row.key, row.entity)}<span class="nm">${
          this._escape(row.name)}</span></div>
        <div class="mini-value ${row.warn ? "warn" : ""}">${this._escape(main)}</div>
        ${aux.length ? `<div class="mini-sub">${this._escape(aux.join(" · "))}</div>` : ""}
        ${row.badge ? `<div class="mini-badge"><span class="badge ${
          row.badge.due ? "due" : (row.badge.status || "")}">${
          this._escape(row.badge.text)}</span></div>` : ""}
      </div>`;
    };
    const toggleHtml = (role, index) => {
      const item = roles[role];
      const on = !!item.on;
      /* A switch is a promise that tapping it flips it. A thermostat takes a
         mode and a target, which is Home Assistant's dialog to ask for, so it
         gets a lamp that reports instead of a switch that lies. */
      const switchable = TOGGLE_DOMAINS.includes(item.domain);
      /* What it is doing, never when it will stop: the countdown strip
         already owns "until when". */
      const sub = this._equipmentState(item);
      return `<div class="tile ${on ? "on" : ""}" data-toggle="${index}">
        <div class="tile-top">
          <span class="tile-name">${this._iconTag("role:" + role, item.entity_id)}<span class="nm">${
            this._escape(item.name || S.roles[role])}</span></span>
          ${switchable
            ? `<span class="switch ${on ? "on" : ""}"><i></i></span>`
            : `<span class="lamp ${on ? "on" : ""}"></span>`}
        </div>
        <div class="tile-sub">${this._escape(sub)}</div>
      </div>`;
    };
    /* Maintenance mode: a flag for the automations, not a piece of kit —
       so it gets the switch shape of a tile, but its own place. */
    const mode = report.maintenance_mode || {};
    const askedFor = value =>
      value === "on" ? S.maintenance.turn_on
      : value === "off" ? S.maintenance.turn_off
      : value === "open" ? S.maintenance.open : S.maintenance.close;
    let modeSub = S.report.state_off;
    let modePlan = "";
    if (mode.on) {
      const bits = [S.report.state_on];
      /* When the visit has an end, that beats saying when it started */
      if (mode.until) {
        bits.push(S.maintenance.ends.replace("{time}",
          new Date(mode.until).toLocaleTimeString(this._locale(),
            { hour: "2-digit", minute: "2-digit" })));
      } else if (mode.since) {
        bits.push(this._relTime(mode.since));
      }
      if (mode.by) bits.push(S.maintenance.by.replace("{who}", mode.by));
      modeSub = bits.join(" · ");
      modePlan = Object.entries(mode.equipment || {}).map(([role, value]) =>
        ((roles[role] || {}).name || S.roles[role] || role)
          + " " + askedFor(value).toLowerCase()).join(" · ");
    }
    const modeHtml = (shown.has("maintenance_mode") && mode.enabled)
      ? `<div class="tile mode ${mode.on ? "on" : ""}" data-mode="1">
          <div class="tile-top">
            <span class="tile-name">${this._iconTag("maintenance_mode", ids.maintenance_mode)}<span class="nm">${
              this._escape(S.maintenance.title)}</span></span>
            <span class="switch ${mode.on ? "on" : ""}"><i></i></span>
          </div>
          <div class="tile-sub">${this._escape(modeSub)}</div>
          ${modePlan ? `<div class="tile-sub mode-plan">${this._escape(modePlan)}</div>` : ""}
        </div>`
      : "";
    const countdownHtml = countdown ? `<div class="countdown" data-entity="${countdown.entity_id}">
          <span class="cd-label">${this._escape(countdown.on
            ? S.card.turns_off : S.card.turns_on)}</span>
          <span class="cd-value" id="cd">—</span>
        </div>` : "";
    let gridHtml = "";
    if (tiles) {
      /* The fixed composition, top to bottom: what needs attention, the
         water right now (temperature hero beside the readings), the
         equipment, then the filtration plan, then the task history.
         One full-width row per section; no configuration involved. */
      const SECTION_RANK = {
        alerts: 0, mode: 1, water: 2, equipment: 3, countdown: 4, cycle: 5, tasks: 6,
      };
      let sequence = 0;
      const sections = new Map();
      const put = (name, html) => {
        const section = sections.get(name) || { rank: SECTION_RANK[name], parts: [] };
        section.parts.push({ rank: sequence++, html: html });
        sections.set(name, section);
      };
      const bucketFor = key =>
        key.startsWith("task:") ? "tasks"
        : key.startsWith("value:") || key === "filtration" ? "water"
        : "equipment";
      alertLines.forEach(line => put("alerts",
        `<div class="mini alert-mini">
          <svg viewBox="0 0 24 24"><path d="M12 8v5M12 17h.01"/>
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
          <div class="alert-text">${this._escape(line)}</div>
        </div>`));
      if (modeHtml) put("mode", modeHtml);
      if (hero) {
        put("water",
          `<div class="mini hero clickable" data-entity="${sourceOf("water_temperature")}">
            <div class="mini-name">${this._iconTag("temperature", sourceOf("water_temperature"))}<span class="nm">${
              this._escape(S.report.values.water_temperature)}</span></div>
            <div class="hero-value">${temp}<small>${tempUnit}</small></div>
          </div>`);
      }
      toggles.forEach((role, index) => put("equipment", toggleHtml(role, index)));
      gridRows.forEach(row => put(bucketFor(row.key), miniHtml(row)));
      if (countdownHtml) put("countdown", countdownHtml);
      if (cycle) {
        put("cycle",
          `<div class="mini cycle clickable" data-entity="${schedule.entity_id}">
            <div class="cycle-head">
              <span class="mini-name">${this._iconTag("filtration", schedule.entity_id)}<span class="nm">${
                this._escape(S.kiosk.filtration_cycle)}</span></span>
              <span class="cycle-hours">${this._escape(cycle.header)}</span>
            </div>
            <div class="cycle-track">
              ${cycle.blocks.map(block => `<i style="left:${block.left}%;width:${block.width}%"></i>`).join("")}
              <b style="left:${cycle.now}%"></b>
            </div>
            <div class="cycle-axis"><span>00h</span><span>06h</span><span>12h</span><span>18h</span><span>24h</span></div>
            ${cycle.sub ? `<div class="mini-sub">${this._escape(cycle.sub)}</div>` : ""}
          </div>`);
      }
      const ordered = [...sections.entries()].sort((a, b) => a[1].rank - b[1].rank);
      gridHtml = ordered.length
        ? `<div class="grid">${ordered.map(([name, section]) => {
            const inner = section.parts
              .sort((a, b) => a.rank - b.rank).map(part => part.html).join("");
            return name === "countdown" ? inner : `<div class="sec sec-${name}">${inner}</div>`;
          }).join("")}</div>` : "";
    }
    const rowHtml = row => `<div class="row" data-row="${rows.indexOf(row)}">
        <span class="row-name">${this._iconTag(row.key, row.entity)}<span class="nm">${
          this._escape(row.name)}</span></span>
        ${row.badge ? `<span class="badge ${row.badge.due ? "due" : (row.badge.status || "")}">${
          this._escape(row.badge.text)}</span>` : ""}
        <span class="row-value ${row.warn ? "warn" : ""}">${this._escape(row.value)}</span>
      </div>`;
    let listHtml = "";
    if (!tiles) {
      listHtml = alertHtml
        + (rows.length ? `<div class="rows">${rows.map(rowHtml).join("")}</div>` : "");
    }
    this.shadowRoot.innerHTML = `
      <ha-card class="${tiles ? "tiles-layout" : ""} ${head ? "" : "no-head"}">
        ${head ? `<div class="head">
          <div class="icon">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 6v7M15 6v7" />
              <path d="M3 16c1.5 0 1.5 1.4 3 1.4S7.5 16 9 16s1.5 1.4 3 1.4S13.5 16 15 16s1.5 1.4 3 1.4S19.5 16 21 16"/>
              <path d="M3 20c1.5 0 1.5 1.4 3 1.4S7.5 20 9 20s1.5 1.4 3 1.4S13.5 20 15 20s1.5 1.4 3 1.4S19.5 20 21 20"/>
            </svg>
          </div>
          <div class="titles">
            <div class="name">${this._escape(config.title || data.title)}</div>
            <div class="sub">${roles.pool_system
              ? `<span class="dot ${roles.pool_system.on ? "on" : "off"}"></span>` : ""}${
              this._escape(subtitleBits.join(" · "))}</div>
          </div>
          ${showTemp && !hero ? `<div class="temp" data-entity="${
            sourceOf("water_temperature")}">${temp}<small>${tempUnit}</small></div>` : ""}
        </div>` : ""}

        ${!tiles && modeHtml ? `<div class="toggles mode-row">${modeHtml}</div>` : ""}

        ${!tiles && countdown ? countdownHtml : ""}

        ${!tiles && toggles.length
          ? `<div class="toggles">${toggles.map(toggleHtml).join("")}</div>` : ""}

        ${tiles ? gridHtml : listHtml}
        ${this._styles()}
      </ha-card>`;

    /* events + countdown ------------------------------------------- */
    const root = this.shadowRoot;
    root.querySelectorAll("[data-toggle]").forEach(node => {
      const item = roles[toggles[Number(node.dataset.toggle)]];
      /* A lamp is not a control: the tile's own handler opens the dialog. */
      const control = node.querySelector(".switch");
      if (control) control.addEventListener("click", event => this._toggle(item, event));
      node.addEventListener("click", () => this._openMoreInfo(item.entity_id));
    });
    /* The mode switch drives our own switch entity; a tap anywhere else on
       the tile opens it, like every other tile here. */
    root.querySelectorAll("[data-mode]").forEach(node => {
      const entityId = ids.maintenance_mode;
      node.querySelector(".switch").addEventListener("click", event => {
        event.stopPropagation();
        /* Ending a visit is one tap, the way it is on the page. Starting one
           is a question first: what should happen, and for how long. */
        if (mode.on) {
          /* No optimistic flip: the switch moving is a state change, which
             is what brings the fresh data back a moment later. */
          if (entityId) this._hass.callService("switch", "turn_off", { entity_id: entityId });
        } else {
          this._openSheet();
        }
      });
      /* Already working and need longer, or changed your mind about the
         heat pump: the running visit reopens its own sheet. */
      node.addEventListener("click", () =>
        mode.on ? this._openSheet() : this._openMoreInfo(entityId));
    });
    root.querySelectorAll("[data-row]").forEach(node => {
      const row = rows[Number(node.dataset.row)];
      if (!row.entity) return;
      node.classList.add("clickable");
      node.addEventListener("click", () => this._openMoreInfo(row.entity));
    });
    root.querySelectorAll(".temp[data-entity], .mini[data-entity]").forEach(node => {
      if (!node.dataset.entity) return;
      node.classList.add("clickable");
      node.addEventListener("click", () => this._openMoreInfo(node.dataset.entity));
    });
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

  /* ---------------- the maintenance sheet ---------------- */
  /* Whoever stands at the pool gets to say what should happen and for how
     long; a dashboard should not be the poorer surface. Same question, same
     answers — the page posts them to its own endpoint, the card hands them
     to the start_maintenance action. */
  _openSheet() {
    if (this._sheet) return;
    const S = this._data.strings;
    const report = this._data.report || {};
    const plan = (report.maintenance_mode || {}).equipment || {};
    const make = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    /* "Turn on" is what you ask for; "On" is what you are told it is now */
    const asked = value =>
      value === "on" ? S.maintenance.turn_on
      : value === "off" ? S.maintenance.turn_off
      : value === "open" ? S.maintenance.open
      : value === "closed" ? S.maintenance.close : S.maintenance.keep;
    /* A cover says where it stands; everything else runs or does not —
       including the thermostat that calls it "heat" rather than "on". */
    const standing = item => {
      if (item.state === "open" || item.state === "opening") return S.maintenance.is_open;
      if (item.state === "closed" || item.state === "closing") return S.maintenance.is_closed;
      if (item.on === null || item.on === undefined) return item.state;
      return item.on ? S.report.state_on : S.report.state_off;
    };
    const segmented = (values, chosen, onPick) => {
      const box = make("div", "seg");
      values.forEach(value => {
        const button = make("button", chosen === value ? "on" : "", asked(value));
        button.type = "button";
        button.addEventListener("click", event => {
          event.stopPropagation();
          box.querySelectorAll("button").forEach(other => other.classList.remove("on"));
          button.classList.add("on");
          onPick(value);
        });
        box.appendChild(button);
      });
      return box;
    };

    const wanted = {};
    const sheet = make("div", "sheet");
    const panel = make("div", "panel");
    panel.addEventListener("click", event => event.stopPropagation());
    panel.appendChild(make("h3", null, S.maintenance.sheet_title));
    panel.appendChild(make("p", "hint", S.maintenance.sheet_hint));

    (report.maintenance_equipment || []).forEach(item => {
      const field = make("div", "field");
      const label = make("label", null, item.name);
      label.appendChild(make("span", "now",
        " · " + S.maintenance.now.replace("{state}", standing(item))));
      field.appendChild(label);
      const chosen = plan[item.role] || "";
      if (chosen) wanted[item.role] = chosen;
      field.appendChild(segmented([""].concat(item.values), chosen, value => {
        if (value) wanted[item.role] = value;
        else delete wanted[item.role];
      }));
      panel.appendChild(field);
    });

    /* How long. The presets answer it in one tap; the box is for the job
       that is neither half an hour nor the whole afternoon. */
    let minutes = VISIT_DEFAULT_MINUTES;
    const duration = make("div", "field");
    duration.appendChild(make("label", null, S.maintenance.duration));
    const presets = make("div", "seg");
    const custom = document.createElement("input");
    VISIT_PRESETS.forEach(preset => {
      const button = make("button", preset === minutes ? "on" : "",
        preset === 0 ? S.maintenance.no_limit
          : preset < 60 ? S.maintenance.preset_minutes.replace("{n}", preset)
          : S.maintenance.preset_hours.replace("{n}", preset / 60));
      button.type = "button";
      button.addEventListener("click", event => {
        event.stopPropagation();
        presets.querySelectorAll("button").forEach(other => other.classList.remove("on"));
        button.classList.add("on");
        custom.value = "";
        minutes = preset;
      });
      presets.appendChild(button);
    });
    duration.appendChild(presets);

    const stepper = make("div", "stepper");
    const minus = make("button", null, "−");
    const plus = make("button", null, "+");
    minus.type = plus.type = "button";
    custom.type = "number";
    custom.inputMode = "numeric";
    custom.step = "5";
    custom.min = "5";
    custom.max = "1440";
    custom.placeholder = "—";
    const bump = direction => {
      const current = parseInt(custom.value, 10) || minutes || VISIT_DEFAULT_MINUTES;
      custom.value = String(Math.min(1440, Math.max(5, current + direction * 5)));
      minutes = Number(custom.value);
      presets.querySelectorAll("button").forEach(other => other.classList.remove("on"));
    };
    minus.addEventListener("click", event => { event.stopPropagation(); bump(-1); });
    plus.addEventListener("click", event => { event.stopPropagation(); bump(1); });
    custom.addEventListener("input", () => {
      const typed = parseInt(custom.value, 10);
      if (!custom.value) return;
      presets.querySelectorAll("button").forEach(other => other.classList.remove("on"));
      if (!isNaN(typed) && typed > 0) minutes = typed;
    });
    stepper.append(minus, custom, make("div", "unit", S.maintenance.minutes), plus);
    duration.appendChild(stepper);
    panel.appendChild(duration);

    const failed = make("div", "sheet-error");
    panel.appendChild(failed);
    const actions = make("div", "actions");
    const cancel = make("button", "ghost", S.maintenance.cancel);
    const start = make("button", "primary", S.maintenance.start);
    cancel.type = start.type = "button";
    cancel.addEventListener("click", event => { event.stopPropagation(); this._closeSheet(); });
    start.addEventListener("click", async event => {
      event.stopPropagation();
      start.disabled = true;
      failed.textContent = "";
      if (await this._startVisit(minutes, wanted)) return;
      /* Nothing started: say so, and leave the answers where they are */
      failed.textContent = S.maintenance.error;
      start.disabled = false;
    });
    actions.append(cancel, start);
    panel.appendChild(actions);

    sheet.appendChild(panel);
    sheet.addEventListener("click", () => this._closeSheet());
    this._sheet = sheet;
    this.shadowRoot.appendChild(sheet);
  }

  _closeSheet() {
    if (!this._sheet) return;
    this._sheet.remove();
    this._sheet = null;
    this._render();
  }

  async _startVisit(minutes, equipment) {
    try {
      await this._hass.callService("pool_maintenance_tracker", "start_maintenance", {
        config_entry: this._data.entry_id,
        /* No limit is a visit without a window, which the action spells null */
        minutes: minutes > 0 ? minutes : null,
        equipment: equipment,
      });
    } catch (error) {
      return false;
    }
    this._sheet.remove();
    this._sheet = null;
    /* The equipment moving is a state change, and the fresh flag comes back
       with the reload rather than from an optimistic guess here. */
    await this._load();
    return true;
  }

  _styles() {
    return `<style>
      *{box-sizing:border-box}
      :host{display:block}
      ha-card{padding:16px;display:block}
      /* With the header gone, whatever lands first should not keep the gap
         that was there to separate it from the header. */
      ha-card.no-head > :first-child{margin-top:0}
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
      .sub{
        color:var(--secondary-text-color,#8a8f94);font-size:.92rem;margin-top:2px;
        display:flex;align-items:center;gap:6px;
      }
      .dot{width:8px;height:8px;border-radius:50%;flex:none}
      .dot.on{
        background:var(--success-color,#4caf50);
        animation:dot-pulse 2s ease-in-out infinite;
      }
      .dot.off{background:var(--error-color,#f44336)}
      @keyframes dot-pulse{
        0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(76,175,80,.45)}
        50%{opacity:.6;box-shadow:0 0 0 4px rgba(76,175,80,0)}
      }
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
        color:var(--state-icon-color,#44739E);
      }
      .countdown.soon .cd-value{color:var(--warning-color,#E9B94F)}

      .toggles{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}

      /* Tiles layout: the outer card dissolves and every mini takes the
         theme's own card surface — so a tiles dashboard reads as native
         HA cards on the transparent background, dark or light. */
      ha-card.tiles-layout{background:none;border:none;box-shadow:none}
      /* Radius is fixed on purpose. Reading --ha-card-border-radius looked
         right, but on installs where the token resolves to nothing valid,
         a failed var() does not fall back — the property resets to its
         initial value, and the corners (and once, the border) vanish.
         12px is HA's own default; the colors stay the theme's. */
      .tiles-layout .mini,.tiles-layout .tile,.tiles-layout .countdown{
        background:var(--ha-card-background,var(--card-background-color,#fff));
        border:1px solid var(--ha-card-border-color,var(--divider-color,rgba(127,127,127,.25)));
        border-radius:12px;
        box-shadow:none;
      }

      /* Tiles layout: kiosk-style minis for a single-card dashboard */
      .grid{display:flex;flex-direction:column;gap:10px;margin-top:14px}
      /* Flex, not grid: items grow to fill their line completely, the
         wrapped last line included — a dashboard without holes. Alerts
         are the exception: exceptional content stays compact. */
      .sec{display:flex;flex-wrap:wrap;gap:10px}
      .sec > *{flex:1 1 150px;min-width:150px}
      .sec-alerts > *{flex:0 1 auto;min-width:180px;max-width:340px}
      .mini{
        border:1px solid var(--divider-color,#e0e0e0);border-radius:12px;
        padding:10px 12px;cursor:pointer;min-width:0;
      }
      .mini-name{
        display:flex;align-items:center;gap:5px;min-width:0;
        font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
        color:var(--secondary-text-color,#8a8f94);
      }
      .mini-value{font-size:1.1rem;font-weight:600;margin-top:4px;line-height:1.3}
      .mini-sub{
        font-size:.74rem;font-weight:600;color:var(--secondary-text-color,#8a8f94);
        margin-top:2px;line-height:1.35;
      }
      .mini-badge{margin-top:6px}
      .item-icon{--mdc-icon-size:15px;color:var(--state-icon-color,#44739E);flex:none}
      .tile-name .item-icon,.row-name .item-icon{--mdc-icon-size:17px}
      .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
      .hero{flex:2 1 280px;display:flex;flex-direction:column;justify-content:center}
      .hero-value{font-size:1.9rem;font-weight:600;line-height:1.15;margin-top:2px}
      .hero-value small{font-size:1rem;color:var(--secondary-text-color,#8a8f94);margin-left:4px}
      .cycle{flex:1 1 100%}
      .cycle-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
      .cycle-hours{font-size:.85rem;font-weight:600;white-space:nowrap}
      .cycle-track{
        position:relative;height:8px;border-radius:999px;margin:10px 0 2px;
        background:var(--secondary-background-color,rgba(127,127,127,.15));
      }
      .cycle-track i{
        position:absolute;top:0;bottom:0;border-radius:999px;
        background:var(--state-icon-color,#44739E);
      }
      .cycle-track b{
        position:absolute;top:-3px;bottom:-3px;width:2px;border-radius:2px;
        background:var(--primary-text-color,#333);
      }
      .grid .countdown{margin-top:0}
      .sec .tile{flex:2 1 240px;min-width:220px}
      .alert-mini{
        display:flex;align-items:center;gap:8px;
        color:var(--warning-color,#E9B94F);
      }
      .alert-mini svg{
        width:18px;height:18px;flex:none;stroke:currentColor;fill:none;
        stroke-width:2;stroke-linecap:round;
      }
      .alert-text{font-size:.85rem;font-weight:500;line-height:1.35}
      .cycle-axis{
        display:flex;justify-content:space-between;margin-top:4px;
        font-size:.68rem;font-weight:600;color:var(--secondary-text-color,#8a8f94);
      }
      .tiles-layout .toggles .tile{flex:1 1 150px}
      .tile{
        flex:1 1 calc(50% - 5px);min-width:0;border:1px solid var(--divider-color,rgba(127,127,127,.35));
        border-radius:12px;padding:10px 12px;cursor:pointer;
      }
      .tile-top{display:flex;align-items:center;gap:8px}
      .tile-name{flex:1;min-width:0;font-weight:500;display:inline-flex;align-items:center;gap:6px}
      .tile-sub{color:var(--secondary-text-color,#8a8f94);font-size:.88rem;margin-top:3px}
      .tile.on .tile-sub{color:var(--state-icon-color,#44739E)}
      .switch{
        width:38px;height:22px;border-radius:11px;background:var(--disabled-text-color,#8c8c8c);
        flex:none;position:relative;transition:background .15s;
      }
      .switch.on{background:var(--state-icon-color,#44739E)}
      .switch i{
        position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;
        background:#fff;transition:transform .15s;
      }
      .switch.on i{transform:translateX(16px)}
      /* Reports, never promises: equipment whose dialog does the commanding.
         Margins carry it to the switch's 22px height, so a row of tiles keeps
         one baseline whether its equipment can be tapped on or not. */
      .lamp{
        width:10px;height:10px;border-radius:50%;flex:none;margin:6px 0;
        background:var(--disabled-text-color,#8c8c8c);
      }
      .lamp.on{
        background:var(--state-icon-color,#44739E);
        box-shadow:0 0 0 4px rgba(68,115,158,.25);
      }

      /* Maintenance mode takes the full width and, when on, the warning
         color: a flag left up by mistake has to be impossible to miss. */
      .toggles.mode-row{margin-top:14px}
      .toggles.mode-row .tile,.sec-mode .tile{flex:1 1 100%}
      .tile.mode.on{
        border-color:var(--warning-color,#E9B94F);
        background:rgba(233,185,79,.12);
      }
      .tile.mode.on .tile-sub{color:var(--warning-color,#E9B94F)}
      .tile.mode .mode-plan{
        font-size:.82rem;font-weight:600;opacity:.85;margin-top:1px;
      }
      .tile.mode.on .switch.on{background:var(--warning-color,#E9B94F)}
      @supports (background:color-mix(in srgb,red 10%,transparent)){
        .tile.mode.on{background:color-mix(in srgb,var(--warning-color,#E9B94F) 12%,transparent)}
      }

      .rows{margin-top:6px}
      .row{
        display:flex;align-items:center;gap:10px;padding:12px 0;
        border-bottom:1px solid var(--divider-color,rgba(127,127,127,.35));
      }
      .row:last-child{border-bottom:none}
      .row-name{flex:1;min-width:0;display:inline-flex;align-items:center;gap:6px}
      .row-value{font-weight:500;white-space:nowrap}
      .badge{
        border-radius:999px;padding:2px 9px;font-size:.78rem;font-weight:500;white-space:nowrap;
        background:var(--secondary-background-color,rgba(127,127,127,.12));color:var(--secondary-text-color,#8a8f94);
      }
      .badge.due,.badge.low,.badge.high{
        background:rgba(68,115,158,.18);color:var(--state-icon-color,#44739E);
      }
      @supports (background:color-mix(in srgb,red 10%,transparent)){
        .badge.due,.badge.low,.badge.high{
          background:color-mix(in srgb,var(--state-icon-color,#44739E) 16%,transparent);
        }
      }
      .badge.ideal{background:rgba(47,204,139,.18);color:var(--success-color,#2FCC8B)}

      /* The maintenance sheet: the page's questions, inside the card */
      .sheet{
        position:fixed;inset:0;z-index:9;display:flex;align-items:center;justify-content:center;
        background:rgba(0,0,0,.45);padding:16px;
      }
      .sheet .panel{
        width:100%;max-width:420px;max-height:86vh;overflow:auto;
        background:var(--card-background-color,#fff);color:var(--primary-text-color,#212121);
        border-radius:16px;padding:18px;
        box-shadow:0 12px 40px rgba(0,0,0,.4);
      }
      .sheet h3{margin:0;font-size:1.15rem;font-weight:600}
      .sheet .hint{
        margin:6px 0 14px;font-size:.88rem;line-height:1.35;
        color:var(--secondary-text-color,#8a8f94);
      }
      .sheet .field{margin-bottom:14px}
      .sheet label{display:block;font-size:.9rem;font-weight:500;margin-bottom:6px}
      .sheet .now{color:var(--secondary-text-color,#8a8f94);font-weight:400}
      .sheet .seg{display:flex;flex-wrap:wrap;gap:6px}
      .sheet .seg button{
        flex:1 1 auto;min-width:64px;padding:8px 10px;font:inherit;font-size:.86rem;
        border:1px solid var(--divider-color,rgba(127,127,127,.35));border-radius:10px;
        background:transparent;color:inherit;cursor:pointer;
      }
      .sheet .seg button.on{
        border-color:var(--state-icon-color,#44739E);
        background:rgba(68,115,158,.18);font-weight:600;
      }
      @supports (background:color-mix(in srgb,red 10%,transparent)){
        .sheet .seg button.on{
          background:color-mix(in srgb,var(--state-icon-color,#44739E) 16%,transparent);
        }
      }
      .sheet .stepper{display:flex;align-items:center;gap:8px;margin-top:10px}
      .sheet .stepper button{
        width:40px;height:40px;font-size:1.2rem;line-height:1;cursor:pointer;
        border:1px solid var(--divider-color,rgba(127,127,127,.35));border-radius:10px;
        background:transparent;color:inherit;
      }
      .sheet .stepper input{
        flex:1;min-width:0;padding:9px 10px;font:inherit;text-align:center;
        border:1px solid var(--divider-color,rgba(127,127,127,.35));border-radius:10px;
        background:transparent;color:inherit;
      }
      .sheet .unit{color:var(--secondary-text-color,#8a8f94);font-size:.86rem}
      .sheet .sheet-error{color:var(--error-color,#f44336);font-size:.88rem}
      .sheet .sheet-error:empty{display:none}
      .sheet .actions{display:flex;gap:8px;margin-top:18px}
      .sheet .actions button{
        flex:1;padding:12px;font:inherit;font-weight:600;border-radius:12px;cursor:pointer;
        border:1px solid var(--divider-color,rgba(127,127,127,.35));
        background:transparent;color:inherit;
      }
      .sheet .actions .primary{
        border-color:transparent;background:var(--state-icon-color,#44739E);color:#fff;
      }
      .sheet .actions button[disabled]{opacity:.6;cursor:default}
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
    this._items = null;
    this._itemsFor = null;
    this._form = null;
  }

  setConfig(config) {
    const before = this._config && this._config.entry;
    this._config = Object.assign({}, DEFAULTS, config || {});
    if (this._config.entry !== before) this._loadItems();
    this._update();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    if (first) this._loadPools();
  }

  async _loadPools() {
    try {
      this._pools = await this._hass.callWS({ type: "pool_maintenance_tracker/pools" });
    } catch (error) {
      this._pools = [];
    }
    this._update();
    this._loadItems();
  }

  /* What this pool actually offers, so the list is its items and not a
     catalogue of everything the card could theoretically draw. */
  async _loadItems() {
    if (!this._hass || !this._config) return;
    const entry = this._config.entry
      || (this._pools.length === 1 ? this._pools[0].entry_id : this._config.entry);
    if (!entry || entry === this._itemsFor) return;
    try {
      const data = await this._hass.callWS({
        type: "pool_maintenance_tracker/status",
        entry_id: entry,
        language: this._hass.language || "en",
      });
      const available = availableItems(data, editorText(this._hass));
      /* Same order the card renders them in, so the list reads like the card */
      this._items = GROUPS.reduce((all, group) => all.concat(available[group]), []);
      this._itemsFor = entry;
    } catch (error) {
      this._items = null;
    }
    this._update();
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

    schema.push({
      name: "layout",
      selector: {
        select: {
          mode: "dropdown",
          options: [
            { value: "list", label: text.layout_list },
            { value: "tiles", label: text.layout_tiles },
          ],
        },
      },
    });
    schema.push({ name: "show_icons", selector: { boolean: {} } });
    schema.push({ name: "only_due_tasks", selector: { boolean: {} } });
    /* Only once we know what this pool has: an empty list would read as
       "this card can show nothing" and save an all-hidden config. */
    if (this._items && this._items.length) {
      schema.push({
        name: "shown",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            options: this._items.map(item => ({
              value: item.value,
              label: item.label || item.value,
            })),
          },
        },
      });
    }
    return schema;
  }

  /* The config stores what to hide; the editor asks what to show. Same
     thing said the useful way round — a fresh card arrives with every box
     ticked, and unticking one is what writes the config. */
  _shown() {
    const hidden = new Set(this._config.hidden || []);
    return (this._items || []).map(item => item.value).filter(value => !hidden.has(value));
  }

  _formData() {
    const data = {
      entry: this._config.entry,
      title: this._config.title,
      layout: this._config.layout || "list",
      show_icons: !!this._config.show_icons,
      only_due_tasks: this._config.only_due_tasks,
    };
    if (this._items && this._items.length) data.shown = this._shown();
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
    this._form.computeLabel = schema => text[schema.name] || schema.name;
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
    if (value.layout && value.layout !== "list") config.layout = value.layout;
    if (value.show_icons) config.show_icons = true;
    if (value.only_due_tasks) config.only_due_tasks = true;
    /* Store the complement, and only when there is one: a card showing
       everything keeps a config with no item list in it at all. Items this
       pool does not currently offer keep their entry, so unplugging a probe
       for an afternoon does not silently un-hide its reading. */
    if (this._items && value.shown) {
      const shown = new Set(value.shown);
      const offered = new Set(this._items.map(item => item.value));
      const hidden = this._items.map(item => item.value).filter(v => !shown.has(v))
        .concat((this._config.hidden || []).filter(v => !offered.has(v)));
      if (hidden.length) config.hidden = hidden;
    } else if (this._config.hidden && this._config.hidden.length) {
      config.hidden = this._config.hidden;
    }
    this._config = Object.assign({}, this._config, config);
    /* Back to the default: stale values must not shadow the emitted ones */
    if (!config.layout) delete this._config.layout;
    if (!config.show_icons) delete this._config.show_icons;
    if (!config.hidden) delete this._config.hidden;
    fireEvent(this, "config-changed", { config: config });
  }
}

/* Loaded twice (an old hand-added resource plus ours), the second define
   would throw and take the whole module down with it. */
if (!customElements.get("pool-maintenance-card")) {
  customElements.define("pool-maintenance-card", PoolMaintenanceCard);
  customElements.define("pool-maintenance-card-editor", PoolMaintenanceCardEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pool-maintenance-card",
  name: "Pool Maintenance Tracker",
  description: "Pool status, equipment and maintenance tasks at a glance.",
  documentationURL: "https://github.com/lucasgiovanny/pool-maintenance-tracker",
  /* Tells the picker this card can render itself from the stub config,
     so the tile shows the real card instead of a text row. */
  preview: true,
});
