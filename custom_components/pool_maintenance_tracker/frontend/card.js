/* Pool Maintenance Tracker — Lovelace card + visual editor
 * Pick exactly which items to show: equipment, readings, tasks, alerts
 * and a live countdown to the next schedule change.
 */

const TOGGLE_DOMAINS = ["switch", "input_boolean", "light", "fan"];
const TOGGLE_ROLES = ["pool_system", "heat_pump", "pump", "pool_light", "cover"];
/* One MDI icon per item key. An icon set on the entity itself wins. */
const ITEM_ICONS = {
  temperature: "mdi:thermometer-water",
  "value:water_temperature": "mdi:thermometer-water",
  "value:ph": "mdi:ph",
  "value:free_chlorine": "mdi:test-tube",
  "value:salt_level": "mdi:shaker-outline",
  chlorinator: "mdi:waves",
  acid_tank: "mdi:cup-water",
  filter_pressure: "mdi:gauge",
  filtration: "mdi:autorenew",
  "task:water_test": "mdi:test-tube",
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
};

/* An empty drum needs refilling; no drum at all is a decision, not a fault */
const ACID_ALERT_LEVELS = ["quarter", "empty", "none"];

const READING_KEYS = ["ph", "free_chlorine", "salt_level", "water_temperature"];
const REFRESH_MS = 30000;

const GROUPS = ["general", "equipment", "readings", "tasks"];
const GENERAL_ITEMS = ["temperature", "alerts", "countdown", "filtration"];

const DEFAULTS = {
  entry: undefined,
  title: "",
  only_due_tasks: false,
  show_icons: false,
  /* "list" packs rows for a column of cards; "tiles" spreads everything
     into kiosk-style minis, for a dashboard made of this card alone. */
  layout: "list",
};

/* Editor labels — same six languages as the pages. */
const EDITOR_TEXT = {
  en: {
    entry: "Pool", entry_help: "Leave empty to use the only pool you have.",
    title: "Title (optional)", only_due_tasks: "Only show overdue tasks",
    general: "General", equipment: "Equipment", readings: "Water readings", tasks: "Tasks",
    temperature: "Water temperature (header)", alerts: "Alerts",
    countdown: "Schedule countdown", filtration: "Filtration suggestion", chlorinator: "Chlorinator", acid_tank: "Acid tank",
    layout: "Layout", layout_list: "List", layout_tiles: "Tiles",
    show_icons: "Show icons",
    items: "Items shown, in this order",
  },
  pt: {
    entry: "Piscina", entry_help: "Deixa vazio para usar a única piscina que tens.",
    title: "Título (opcional)", only_due_tasks: "Mostrar só tarefas em atraso",
    general: "Geral", equipment: "Equipamento", readings: "Leituras da água", tasks: "Tarefas",
    temperature: "Temperatura da água (cabeçalho)", alerts: "Alertas",
    countdown: "Contagem decrescente do horário", filtration: "Sugestão de filtração", chlorinator: "Clorador",
    acid_tank: "Depósito de ácido",
    layout: "Disposição", layout_list: "Lista", layout_tiles: "Cartões",
    show_icons: "Mostrar ícones",
    items: "Itens exibidos, nesta ordem",
  },
  es: {
    entry: "Piscina", entry_help: "Déjalo vacío para usar la única piscina que tengas.",
    title: "Título (opcional)", only_due_tasks: "Mostrar solo tareas atrasadas",
    general: "General", equipment: "Equipamiento", readings: "Lecturas del agua", tasks: "Tareas",
    temperature: "Temperatura del agua (encabezado)", alerts: "Alertas",
    countdown: "Cuenta atrás del horario", filtration: "Sugerencia de filtración", chlorinator: "Clorador",
    acid_tank: "Depósito de ácido",
    layout: "Disposición", layout_list: "Lista", layout_tiles: "Tarjetas",
    show_icons: "Mostrar iconos",
    items: "Elementos mostrados, en este orden",
  },
  fr: {
    entry: "Piscine", entry_help: "Laissez vide pour utiliser votre seule piscine.",
    title: "Titre (facultatif)", only_due_tasks: "N'afficher que les tâches en retard",
    general: "Général", equipment: "Équipement", readings: "Mesures de l'eau", tasks: "Tâches",
    temperature: "Température de l'eau (en-tête)", alerts: "Alertes",
    countdown: "Compte à rebours de l'horaire", filtration: "Suggestion de filtration", chlorinator: "Électrolyseur",
    acid_tank: "Réservoir d'acide",
    layout: "Disposition", layout_list: "Liste", layout_tiles: "Vignettes",
    show_icons: "Afficher les icônes",
    items: "Éléments affichés, dans cet ordre",
  },
  de: {
    entry: "Pool", entry_help: "Leer lassen, um den einzigen Pool zu verwenden.",
    title: "Titel (optional)", only_due_tasks: "Nur überfällige Aufgaben zeigen",
    general: "Allgemein", equipment: "Geräte", readings: "Wasserwerte", tasks: "Aufgaben",
    temperature: "Wassertemperatur (Kopfzeile)", alerts: "Warnungen",
    countdown: "Countdown des Zeitplans", filtration: "Filtrationsempfehlung", chlorinator: "Elektrolyseur",
    acid_tank: "Säuretank",
    layout: "Anordnung", layout_list: "Liste", layout_tiles: "Kacheln",
    show_icons: "Symbole anzeigen",
    items: "Angezeigte Elemente, in dieser Reihenfolge",
  },
  it: {
    entry: "Piscina", entry_help: "Lascia vuoto per usare l'unica piscina che hai.",
    title: "Titolo (facoltativo)", only_due_tasks: "Mostra solo attività in ritardo",
    general: "Generale", equipment: "Attrezzatura", readings: "Letture dell'acqua",
    tasks: "Attività", temperature: "Temperatura dell'acqua (intestazione)",
    alerts: "Avvisi", countdown: "Conto alla rovescia dell'orario",
    filtration: "Suggerimento di filtrazione",
    chlorinator: "Clorinatore", acid_tank: "Serbatoio dell'acido",
    layout: "Disposizione", layout_list: "Elenco", layout_tiles: "Riquadri",
    show_icons: "Mostra icone",
    items: "Elementi mostrati, in questo ordine",
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
    /* No picking, no ordering: the card shows everything the pool offers,
       composed the way the card thinks a pool dashboard should read.
       Choosing and dragging shipped, twice — and produced configuration
       work and layout puzzles instead of dashboards. items/show_* keys in
       old configs are deliberately ignored. */
    return allItemValues(available);
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
    const reading = (report.current || {}).water_temperature;
    const temp = reading ? reading.value : values.water_temperature;
    const tempUnit = (reading && reading.unit) || (probe && probe.unit)
      || S.units.water_temperature;
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
      if (values.acid_tank_level === "none") {
        alertLines.push(S.report.alert_acid_missing);
      } else if (ACID_ALERT_LEVELS.includes(values.acid_tank_level)) {
        alertLines.push(S.report.values.acid_tank_level + " — "
          + S.acid_levels[values.acid_tank_level]);
      }
      if ((report.filtration || {}).short_by) {
        alertLines.push(S.report.alert_filtration_short
          .replace("{scheduled}", report.filtration.scheduled_hours)
          .replace("{recommended}", report.filtration.recommended_hours));
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
        entity: ids[key],
        badge: status ? { text: S.report.status[status], status: status } : null,
        warn: status === "low" || status === "high",
      });
    });
    (report.extra || []).forEach(item => {
      if (!shown.has("extra:" + item.entity_id)) return;
      const onOff = item.state === "on" || item.state === "off";
      rows.push({
        key: "extra:" + item.entity_id,
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
        key: "filtration",
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
    /* Set by Lovelace on panel ("single card") views — the hook the map
       card uses to fill the screen. The grid stretches to the viewport
       and each mini centers itself in its share of it. */
    const panel = this.isPanel === true;

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
          sub: filtration ? [
            S.report.recommended.replace("{h}", filtration.recommended_hours),
            filtration.actual_hours !== null && filtration.actual_hours !== undefined
              ? S.report.actual_today.replace("{h}", filtration.actual_hours) : null,
          ].filter(Boolean).join(" · ") : "",
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
      const on = item.state === "on" || item.state === "open";
      let sub = on ? S.report.state_on : S.report.state_off;
      if (role === "pool_system" && on && schedule && schedule.next_change) {
        sub = S.kiosk.until.replace("{time}", new Date(schedule.next_change)
          .toLocaleTimeString(this._locale(), { hour: "2-digit", minute: "2-digit" }));
      }
      return `<div class="tile ${on ? "on" : ""}" data-toggle="${index}">
        <div class="tile-top">
          <span class="tile-name">${this._iconTag("role:" + role, item.entity_id)}<span class="nm">${
            this._escape(item.name || S.roles[role])}</span></span>
          <span class="switch ${on ? "on" : ""}"><i></i></span>
        </div>
        <div class="tile-sub">${this._escape(sub)}</div>
      </div>`;
    };
    const countdownHtml = countdown ? `<div class="countdown" data-entity="${countdown.entity_id}">
          <span class="cd-label">${this._escape(countdown.state === "on"
            ? S.card.turns_off : S.card.turns_on)}</span>
          <span class="cd-value" id="cd">—</span>
        </div>` : "";
    let gridHtml = "";
    if (tiles) {
      /* The fixed composition, top to bottom: what needs attention, the
         water right now (temperature hero beside the readings), the
         equipment, then the filtration plan, then the task history.
         One full-width row per section; no configuration involved. */
      const SECTION_RANK = { alerts: 0, water: 1, equipment: 2, countdown: 3, cycle: 4, tasks: 5 };
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
      if (hero) {
        put("water",
          `<div class="mini hero clickable" data-entity="${ids.water_temperature || ""}">
            <div class="mini-name">${this._iconTag("temperature", ids.water_temperature)}<span class="nm">${
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
      <ha-card class="${tiles ? "tiles-layout" : ""}${panel ? " panel" : ""}">
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
          ${showTemp && !hero ? `<div class="temp" data-entity="${
            ids.water_temperature || ""}">${temp}<small>${tempUnit}</small></div>` : ""}
        </div>

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

  _styles() {
    return `<style>
      *{box-sizing:border-box}
      :host{display:block;height:100%}
      ha-card{padding:16px;display:block}
      ha-card.panel{height:100%;display:flex;flex-direction:column;overflow:auto}
      .panel .grid{flex:1;justify-content:space-evenly}
      .panel .mini{display:flex;flex-direction:column;justify-content:center}
      .panel .hero-value{font-size:clamp(1.9rem,5.5vh,3.2rem)}
      .panel .mini-value{font-size:clamp(1.1rem,2.8vh,1.6rem)}
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
    this._form = null;
  }

  setConfig(config) {
    this._config = Object.assign({}, DEFAULTS, config || {});
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
    return schema;
  }

  _formData() {
    const data = {
      entry: this._config.entry,
      title: this._config.title,
      layout: this._config.layout || "list",
      show_icons: !!this._config.show_icons,
      only_due_tasks: this._config.only_due_tasks,
    };
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
    this._config = Object.assign({}, this._config, config);
    /* Back to the default: stale values must not shadow the emitted ones */
    if (!config.layout) delete this._config.layout;
    if (!config.show_icons) delete this._config.show_icons;
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
