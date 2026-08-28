/* Pool Maintenance Tracker — animated scene card
 *
 * The equipment card says what is on in words; this one says it the way you
 * would see it standing at the pool. One photo of a machine room, and the
 * three things that are either happening or not drawn on top of it: water
 * turning over in the filter, heat coming off the heat pump, the lamp lit
 * under the surface. Each machine wears its own state — nothing is traced
 * along the pipework.
 *
 * Everything it draws comes from the roles the pool already has
 * (`heat_pump`, `pump` / `filtration_schedule`, `pool_light`), so a pool
 * that is configured needs no configuration here. It is a display: nothing
 * on it is clickable, and it commands nothing.
 */

/* Shipped with the integration and served next to this file. */
const SCENE_URL = "/pool_maintenance_tracker/scene/pool.jpg";
const REFRESH_MS = 30000;
/* With a live subscription the poll is only a safety net for the clock. */
const SUBSCRIBED_REFRESH_MS = 300000;

/* Sun elevation, in degrees, between which the scene fades from full day to
   full night. Well after sunset (0°) — the photo has hard midday shadows in
   it, so it can only ever pass for dusk, and pretending otherwise at the
   moment the sun crosses the horizon just looks broken. */
const NIGHT_FROM = 6;
const NIGHT_TO = -8;

const DEFAULTS = {
  entry: undefined,
  title: "",
  /* A pool that looks nothing like the shipped photo can point at its own. */
  background: "",
  show_title: true,
  show_labels: true,
  show_temperature: true,
  /* auto follows sun.sun; the other two pin the scene for a dashboard that
     wants one look (a kiosk screen in a dark hallway, say). */
  night: "auto",
  /* Where the dashboard has dragged things to, keyed by the names in
     LAYOUT. Only what was moved is in here; everything else keeps the
     table's own coordinates. */
  positions: {},
  /* The outline of the water, for a card showing its own photo. Empty means
     the shipped picture's, which is what the lamp glow is clipped to. */
  water: "",
};

const NIGHT_MODES = ["auto", "day", "night"];

/* Editor labels — same languages as the pages and the equipment card. */
const EDITOR_TEXT = {
  en: {
    entry: "Pool", entry_help: "Leave empty to use the only pool you have.",
    title: "Title (optional)", show_title: "Show title",
    show_labels: "Show labels", show_temperature: "Show water temperature",
    night: "Lighting", night_auto: "Follow the sun", night_day: "Always day",
    night_night: "Always night",
    background: "Background image (optional)",
    background_help: "Leave empty for the picture that ships with the integration.",
    pos_open: "Edit visually",
    pos_kicker: "Scene positions",
    pos_reset: "Reset all",
    pos_done: "Done",
    pos_hint: "Drag anything on the picture. Each line follows the skimmer or the jet it arrives at.",
    pos_title: "Title",
    pos_filtration: "Filtration label",
    pos_heat: "Heat pump label",
    pos_light: "Light label",
    pos_temperature: "Temperature",
    pos_swirl: "Filter churn",
    pos_fan: "Fan",
    pos_heat_waves: "Heat",
    pos_gauge: "Pressure gauge",
    pos_heat_display: "Heat pump display",
    pos_panel_display: "Controller display",
    pos_lamp: "Lamp",
    pos_skimmer: "Skimmer",
    pos_jet: "Return jet",
    pos_leg_out: "Line out",
    pos_leg_back: "Line back",
  },
  pt: {
    entry: "Piscina", entry_help: "Deixa vazio para usar a única piscina que tens.",
    title: "Título (opcional)", show_title: "Mostrar título",
    show_labels: "Mostrar etiquetas", show_temperature: "Mostrar temperatura da água",
    night: "Iluminação", night_auto: "Seguir o sol", night_day: "Sempre dia",
    night_night: "Sempre noite",
    background: "Imagem de fundo (opcional)",
    background_help: "Deixa vazio para a imagem que vem com a integração.",
    pos_open: "Editar visualmente",
    pos_kicker: "Posições da cena",
    pos_reset: "Repor tudo",
    pos_done: "Concluído",
    pos_hint: "Arrasta o que quiseres na imagem. Cada linha acompanha o skimmer ou o retorno onde chega.",
    pos_title: "Título",
    pos_filtration: "Etiqueta da filtração",
    pos_heat: "Etiqueta da bomba de calor",
    pos_light: "Etiqueta da luz",
    pos_temperature: "Temperatura",
    pos_swirl: "Turbilhão do filtro",
    pos_fan: "Ventoinha",
    pos_heat_waves: "Calor",
    pos_gauge: "Manómetro",
    pos_heat_display: "Visor da bomba de calor",
    pos_panel_display: "Visor do quadro",
    pos_lamp: "Lâmpada",
    pos_skimmer: "Skimmer",
    pos_jet: "Retorno",
    pos_leg_out: "Linha de ida",
    pos_leg_back: "Linha de volta",
  },
  "pt-br": {
    entry: "Piscina", entry_help: "Deixe vazio para usar a única piscina que você tem.",
    title: "Título (opcional)", show_title: "Mostrar título",
    show_labels: "Mostrar etiquetas", show_temperature: "Mostrar temperatura da água",
    night: "Iluminação", night_auto: "Seguir o sol", night_day: "Sempre dia",
    night_night: "Sempre noite",
    background: "Imagem de fundo (opcional)",
    background_help: "Deixe vazio para a imagem que vem com a integração.",
    pos_open: "Editar visualmente",
    pos_kicker: "Posições da cena",
    pos_reset: "Redefinir tudo",
    pos_done: "Concluído",
    pos_hint: "Arraste o que quiser na imagem. Cada linha acompanha o skimmer ou o retorno onde chega.",
    pos_title: "Título",
    pos_filtration: "Etiqueta da filtração",
    pos_heat: "Etiqueta da bomba de calor",
    pos_light: "Etiqueta da luz",
    pos_temperature: "Temperatura",
    pos_swirl: "Turbilhão do filtro",
    pos_fan: "Ventoinha",
    pos_heat_waves: "Calor",
    pos_gauge: "Manômetro",
    pos_heat_display: "Visor da bomba de calor",
    pos_panel_display: "Visor do painel",
    pos_lamp: "Lâmpada",
    pos_skimmer: "Skimmer",
    pos_jet: "Retorno",
    pos_leg_out: "Linha de ida",
    pos_leg_back: "Linha de volta",
  },
  es: {
    entry: "Piscina", entry_help: "Déjalo vacío para usar la única piscina que tengas.",
    title: "Título (opcional)", show_title: "Mostrar título",
    show_labels: "Mostrar etiquetas", show_temperature: "Mostrar temperatura del agua",
    night: "Iluminación", night_auto: "Seguir el sol", night_day: "Siempre de día",
    night_night: "Siempre de noche",
    background: "Imagen de fondo (opcional)",
    background_help: "Déjalo vacío para la imagen que viene con la integración.",
    pos_open: "Editar visualmente",
    pos_kicker: "Posiciones de la escena",
    pos_reset: "Restablecer todo",
    pos_done: "Listo",
    pos_hint: "Arrastra lo que quieras en la imagen. Cada línea sigue al skimmer o al retorno donde llega.",
    pos_title: "Título",
    pos_filtration: "Etiqueta de filtración",
    pos_heat: "Etiqueta de la bomba de calor",
    pos_light: "Etiqueta de la luz",
    pos_temperature: "Temperatura",
    pos_swirl: "Remolino del filtro",
    pos_fan: "Ventilador",
    pos_heat_waves: "Calor",
    pos_gauge: "Manómetro",
    pos_heat_display: "Pantalla de la bomba de calor",
    pos_panel_display: "Pantalla del cuadro",
    pos_lamp: "Lámpara",
    pos_skimmer: "Skimmer",
    pos_jet: "Retorno",
    pos_leg_out: "Línea de ida",
    pos_leg_back: "Línea de vuelta",
  },
  fr: {
    entry: "Piscine", entry_help: "Laisse vide pour utiliser la seule piscine que tu as.",
    title: "Titre (optionnel)", show_title: "Afficher le titre",
    show_labels: "Afficher les étiquettes", show_temperature: "Afficher la température de l'eau",
    night: "Éclairage", night_auto: "Suivre le soleil", night_day: "Toujours jour",
    night_night: "Toujours nuit",
    background: "Image de fond (optionnel)",
    background_help: "Laisse vide pour l'image fournie avec l'intégration.",
    pos_open: "Édition visuelle",
    pos_kicker: "Positions de la scène",
    pos_reset: "Tout réinitialiser",
    pos_done: "Terminé",
    pos_hint: "Fais glisser ce que tu veux sur l'image. Chaque ligne suit le skimmer ou le refoulement où elle arrive.",
    pos_title: "Titre",
    pos_filtration: "Étiquette de filtration",
    pos_heat: "Étiquette de la pompe à chaleur",
    pos_light: "Étiquette de la lumière",
    pos_temperature: "Température",
    pos_swirl: "Tourbillon du filtre",
    pos_fan: "Ventilateur",
    pos_heat_waves: "Chaleur",
    pos_gauge: "Manomètre",
    pos_heat_display: "Écran de la pompe à chaleur",
    pos_panel_display: "Écran du coffret",
    pos_lamp: "Lampe",
    pos_skimmer: "Skimmer",
    pos_jet: "Refoulement",
    pos_leg_out: "Ligne aller",
    pos_leg_back: "Ligne retour",
  },
  de: {
    entry: "Pool", entry_help: "Leer lassen, um den einzigen Pool zu verwenden.",
    title: "Titel (optional)", show_title: "Titel anzeigen",
    show_labels: "Beschriftungen anzeigen", show_temperature: "Wassertemperatur anzeigen",
    night: "Beleuchtung", night_auto: "Der Sonne folgen", night_day: "Immer Tag",
    night_night: "Immer Nacht",
    background: "Hintergrundbild (optional)",
    background_help: "Leer lassen für das mitgelieferte Bild.",
    pos_open: "Visuell bearbeiten",
    pos_kicker: "Szenenpositionen",
    pos_reset: "Alles zurücksetzen",
    pos_done: "Fertig",
    pos_hint: "Zieh alles im Bild an seinen Platz. Jede Leitung folgt dem Skimmer oder dem Rücklauf, an dem sie ankommt.",
    pos_title: "Titel",
    pos_filtration: "Beschriftung Filterung",
    pos_heat: "Beschriftung Wärmepumpe",
    pos_light: "Beschriftung Licht",
    pos_temperature: "Temperatur",
    pos_swirl: "Filterströmung",
    pos_fan: "Lüfter",
    pos_heat_waves: "Wärme",
    pos_gauge: "Manometer",
    pos_heat_display: "Display der Wärmepumpe",
    pos_panel_display: "Display der Steuerung",
    pos_lamp: "Lampe",
    pos_skimmer: "Skimmer",
    pos_jet: "Rücklauf",
    pos_leg_out: "Leitung hin",
    pos_leg_back: "Leitung zurück",
  },
  it: {
    entry: "Piscina", entry_help: "Lascia vuoto per usare l'unica piscina che hai.",
    title: "Titolo (opzionale)", show_title: "Mostra titolo",
    show_labels: "Mostra etichette", show_temperature: "Mostra temperatura dell'acqua",
    night: "Illuminazione", night_auto: "Segui il sole", night_day: "Sempre giorno",
    night_night: "Sempre notte",
    background: "Immagine di sfondo (opzionale)",
    background_help: "Lascia vuoto per l'immagine inclusa nell'integrazione.",
    pos_open: "Modifica visiva",
    pos_kicker: "Posizioni della scena",
    pos_reset: "Reimposta tutto",
    pos_done: "Fatto",
    pos_hint: "Trascina quello che vuoi sull'immagine. Ogni linea segue lo skimmer o la bocchetta a cui arriva.",
    pos_title: "Titolo",
    pos_filtration: "Etichetta filtrazione",
    pos_heat: "Etichetta pompa di calore",
    pos_light: "Etichetta luce",
    pos_temperature: "Temperatura",
    pos_swirl: "Vortice del filtro",
    pos_fan: "Ventola",
    pos_heat_waves: "Calore",
    pos_gauge: "Manometro",
    pos_heat_display: "Display della pompa di calore",
    pos_panel_display: "Display del quadro",
    pos_lamp: "Lampada",
    pos_skimmer: "Skimmer",
    pos_jet: "Bocchetta di mandata",
    pos_leg_out: "Linea di andata",
    pos_leg_back: "Linea di ritorno",
  },
};

function editorText(hass) {
  const language = (hass && hass.language ? hass.language : "en").toLowerCase();
  /* The exact regional code wins when we ship it (pt-br); its base next */
  return EDITOR_TEXT[language] || EDITOR_TEXT[language.split("-")[0]] || EDITOR_TEXT.en;
}

function fireEvent(node, type, detail) {
  node.dispatchEvent(new CustomEvent(type, {
    detail: detail, bubbles: true, composed: true, cancelable: false,
  }));
}

/* The water, traced from the photo: far edge, right coping, near deck. The
   lamp glow is clipped to it, which is the whole reason it is exact — a glow
   spilling onto the decking reads as a bug immediately. A card pointed at
   somebody else's photo can hand over its own outline in `water`. */
const WATER = "M 0 331 L 465 270 L 600 309 L 600 351 L 350 400 L 0 400 Z";

/* Everything the scene puts on top of the photo, and where it sits by
   default — in the 600x400 space the SVG draws in, measured off the shipped
   picture. This table is the whole of what the visual editor can move: one
   entry per handle, so the card, the editor and the saved config all name
   the same things, and adding a piece to the scene is adding a row here.

   `kind` says what a piece is and therefore how it is dragged: a pair of
   words, an effect pinned to a machine, or a line with an end at each side.
   Point the card at your own photo and every one of these is in the wrong
   place, which is exactly what the editor is for. */
const LAYOUT = {
  title: { kind: "text", group: "labels", x: 18, y: 32 },
  filtration: { kind: "text", group: "labels", x: 211, y: 102 },
  heat: { kind: "text", group: "labels", x: 443, y: 184 },
  light: { kind: "text", group: "labels", x: 230, y: 334 },
  temperature: { kind: "text", group: "labels", x: 26, y: 344 },
  /* Inside the filter's body, clear of the clamp band and the valves */
  swirl: { kind: "anchor", group: "equipment", x: 210, y: 206 },
  fan: { kind: "anchor", group: "equipment", x: 382, y: 205 },
  heat_waves: { kind: "anchor", group: "equipment", x: 381, y: 166 },
  gauge: { kind: "anchor", group: "equipment", x: 222, y: 125 },
  heat_display: { kind: "anchor", group: "equipment", x: 411, y: 182 },
  panel_display: { kind: "anchor", group: "equipment", x: 156, y: 150 },
  /* Underwater lamp, sitting on the far wall */
  lamp: { kind: "anchor", group: "water", x: 230, y: 302 },
  /* The two holes in the far wall: water leaves at the skimmer and comes
     back at the jet. */
  skimmer: { kind: "anchor", group: "water", x: 120, y: 320 },
  jet: { kind: "anchor", group: "water", x: 455, y: 277 },
  /* The run out to the machines and the run back. Everything in between is
     buried under the decking in life, so these are not the plumbing: two
     lines, one each way, drawn where they read rather than where the pipe
     happens to go.

     Only the machine end of each is a handle. The other end is the skimmer
     or the jet — the same point the ripples are at, so drag the jet and the
     line that arrives there comes with it. Two handles on one spot is a
     coin toss over which one you grab. */
  leg_out: { kind: "anchor", group: "flow", x: 198, y: 243 },
  leg_back: { kind: "anchor", group: "flow", x: 400, y: 242 },
};

/* Which way round each leg runs, and what its wet end is tied to. */
const LEGS = [
  { key: "leg_out", from: "skimmer", to: "leg_out" },
  { key: "leg_back", from: "leg_back", to: "jet" },
];

const LAYOUT_GROUPS = ["labels", "equipment", "water", "flow"];

/* How far a leg bows off the straight line between its ends, as a fraction
   of its length. Enough to read as a run of hose rather than a ruler. */
const LEG_BOW = 0.15;

const FAN_R = 25;
const DISPLAY = { w: 15, h: 14 };
const PANEL_DISPLAY = { w: 21, h: 15 };

/* Water turning over inside the filter. Three dashed rings at different
   radii and speeds, the middle one running the other way, which is enough
   to read as a churn rather than a spinner. It sits on the filter exactly
   as the blades sit on the heat pump: the machine that is working shows it,
   and nothing is drawn along the pipework — a line traced over plumbing
   looked like a line drawn over plumbing, however carefully it was fitted. */
const SWIRL_RINGS = [
  { r: 14, dash: "15 10", dur: "3.4s", reverse: false },
  { r: 9.5, dash: "10 8", dur: "2.4s", reverse: true },
  { r: 5.5, dash: "6 6", dur: "1.7s", reverse: false },
];

/* Three ribbons of warm air off the top of the heat pump, spaced either
   side of the anchor so the whole set moves with one handle. */
const HEAT_WAVES = [
  { dx: -29, delay: "0s" },
  { dx: 0, delay: "0.85s" },
  { dx: 29, delay: "1.7s" },
];

/* A wave is drawn once and reused at each x: same shape, staggered start. */
const HEAT_WAVE_PATH = "M 0 0 c -5 -8, 5 -14, 0 -22 c -5 -8, 5 -13, 0 -20";

/* Six of them, evenly spaced, so the group's box is centred on the hub and
   the spin turns about the fan instead of wobbling around a lopsided one. */
const FAN_BLADES = [0, 60, 120, 180, 240, 300];

/* Where a piece actually sits: its place in the table, with whatever the
   dashboard has moved laid over the top. Shared by the card and the editor
   so a handle in one is the same coordinate as a shape in the other. */
function placement(positions, key) {
  const base = LAYOUT[key];
  const saved = (positions || {})[key];
  const at = { x: base.x, y: base.y };
  if (saved) {
    Object.keys(at).forEach(axis => {
      if (typeof saved[axis] === "number") at[axis] = saved[axis];
    });
  }
  return at;
}

/* A leg, as a curve between its two ends. The bow is computed rather than
   stored: it keeps its shape wherever the ends are dragged to, and it always
   arcs upwards, away from the ground, which is the way a hose lies. */
function legPath(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy) || 1;
  /* Whichever normal points up the screen */
  const sign = dx >= 0 ? 1 : -1;
  const bow = LEG_BOW * length;
  const cx = (from.x + to.x) / 2 + (dy / length) * bow * sign;
  const cy = (from.y + to.y) / 2 - (dx / length) * bow * sign;
  return `M ${from.x} ${from.y} Q ${round(cx)} ${round(cy)} ${to.x} ${to.y}`;
}

function round(value) {
  return Math.round(value * 10) / 10;
}

class PoolSceneCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._timer = null;
    this._pending = null;
    this._onVisible = null;
    this._observer = null;
    this._loadedAt = 0;
    this._loading = false;
    /* The shell is built once and then only has classes and text changed on
       it: rebuilding the markup would restart every CSS animation, so a
       pool whose sensors chatter would show a permanently stuttering flow. */
    this._built = "";
    this._nodes = null;
  }

  setConfig(config) {
    this._config = Object.assign({}, DEFAULTS, config || {});
    if (NIGHT_MODES.indexOf(this._config.night) === -1) this._config.night = "auto";
    /* A different background or a title appearing changes the shell */
    this._built = "";
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
       Repainting is cheap; refetching is not, so only a state this card is
       actually drawing sends us back for fresh data. */
    if (this._moved()) this._soon(); else this._render();
  }

  connectedCallback() {
    this._start();
    if (this._hass && (!this._loadedAt || Date.now() - this._loadedAt > REFRESH_MS)) {
      this._load();
    }
  }

  disconnectedCallback() {
    this._stop();
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("pool-scene-card-editor");
  }

  _start() {
    this._subscribe();
    if (!this._timer) {
      this._timer = setInterval(() => this._load(),
        this._unsub ? SUBSCRIBED_REFRESH_MS : REFRESH_MS);
    }
    if (!this._onVisible) {
      /* Background tabs get their timers throttled, and a phone waking up
         reconnects the websocket — either way, come back to a fresh card. */
      this._onVisible = () => {
        if (document.visibilityState === "visible") this._load();
      };
      document.addEventListener("visibilitychange", this._onVisible);
    }
    this._watchVisibility();
  }

  _stop() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
    this._subscribing = false;
    if (this._timer) clearInterval(this._timer);
    if (this._pending) clearTimeout(this._pending);
    this._timer = this._pending = null;
    if (this._onVisible) {
      document.removeEventListener("visibilitychange", this._onVisible);
      this._onVisible = null;
    }
    if (this._observer) {
      this._observer.disconnect();
      this._observer = null;
    }
  }

  /* Half a dozen looping animations on a card three screens down a dashboard
     is work nobody asked for. Pause them while it is out of view. */
  _watchVisibility() {
    if (this._observer || typeof IntersectionObserver === "undefined") return;
    this._observer = new IntersectionObserver(entries => {
      entries.forEach(entry => this.classList.toggle("offscreen", !entry.isIntersecting));
    }, { rootMargin: "80px" });
    this._observer.observe(this);
  }

  /* The states the card is currently drawing, as one comparable string */
  _stamp() {
    if (!this._hass) return "";
    const report = (this._data || {}).report || {};
    const ids = new Set();
    Object.values(report.roles || {}).forEach(role => {
      if (!role) return;
      if (role.entity_id) ids.add(role.entity_id);
      /* A schedule kept as separate entities moves when its hours do */
      (role.sources || []).forEach(id => ids.add(id));
    });
    const current = (report.current || {}).water_temperature;
    if (current && current.entity_id) ids.add(current.entity_id);
    /* Dusk is a state change like any other on this card */
    ids.add("sun.sun");
    const states = this._hass.states || {};
    let stamp = "";
    ids.forEach(id => {
      const state = states[id];
      stamp += id + "=" + (state ? state.state : "?") + ";";
    });
    return stamp;
  }

  _moved() {
    const stamp = this._stamp();
    const moved = this._last !== undefined && stamp !== this._last;
    this._last = stamp;
    return moved;
  }

  async _subscribe() {
    if (this._unsub || this._subscribing || !this._hass) return;
    this._subscribing = true;
    try {
      const entryId = await this._entryId();
      this._unsub = await this._hass.connection.subscribeMessage(
        data => {
          this._data = data;
          this._error = null;
          this._loadedAt = Date.now();
          this._last = this._stamp();
          this._render();
        },
        {
          type: "pool_maintenance_tracker/subscribe",
          entry_id: entryId,
          language: this._hass.language || "en",
        },
      );
      if (this._timer) {
        clearInterval(this._timer);
        this._timer = setInterval(() => this._load(), SUBSCRIBED_REFRESH_MS);
      }
    } catch (error) {
      this._unsub = null;
    }
    this._subscribing = false;
  }

  /* One logged record moves a dozen entities at once — coalesce them */
  _soon() {
    if (this._pending) clearTimeout(this._pending);
    this._pending = setTimeout(() => {
      this._pending = null;
      this._load();
    }, 250);
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

  /* ---------------- what the scene is showing ---------------- */

  /* How much of the day is left, 0 (broad daylight) to 1 (night).
     A photo taken at noon can only be pushed as far as dusk, so this is a
     ramp rather than a switch, and it stops well short of black. */
  _night() {
    if (this._config.night === "day") return 0;
    if (this._config.night === "night") return 1;
    const sun = this._hass && this._hass.states ? this._hass.states["sun.sun"] : null;
    if (!sun) return 0;
    const elevation = sun.attributes ? sun.attributes.elevation : undefined;
    if (typeof elevation !== "number") return sun.state === "below_horizon" ? 1 : 0;
    if (elevation >= NIGHT_FROM) return 0;
    if (elevation <= NIGHT_TO) return 1;
    return (NIGHT_FROM - elevation) / (NIGHT_FROM - NIGHT_TO);
  }

  /* Is water going round? A pool says so in whichever way it was set up:
     the pump switch is the direct answer, the schedule is the next best,
     and the system switch is the last thing left to ask. */
  _circulating(roles) {
    const source = roles.pump || roles.filtration_schedule || roles.pool_system;
    return source ? { on: !!source.on, role: source } : null;
  }

  /* A heat pump on a switch is either running or not. One on a thermostat
     can also be on and doing nothing, which is worth drawing differently:
     no heat comes off a unit that has reached its target. */
  _heating(roles) {
    const role = roles.heat_pump;
    if (!role) return null;
    const action = role.action;
    if (action === "heating" || action === "cooling") {
      return { on: true, working: true, action: action, role: role };
    }
    if (action === "idle" || action === "off") {
      return { on: !!role.on, working: false, action: action, role: role };
    }
    /* No hvac_action to go on: on means working. */
    return { on: !!role.on, working: !!role.on, action: null, role: role };
  }

  _stateWord(S, item) {
    if (!item) return "";
    if (item.action === "heating") return S.report.state_heating;
    if (item.action === "cooling") return S.report.state_cooling;
    return item.on ? S.report.state_on : S.report.state_off;
  }

  /* ---------------- rendering ---------------- */

  _render() {
    this._syncTheme();
    if (!this._data) {
      this._built = "";
      this._nodes = null;
      this.shadowRoot.innerHTML =
        `${this._styles()}<ha-card><div class="empty">${
          this._error ? this._escape(this._error) : "…"}</div></ha-card>`;
      return;
    }
    this._build();
    this._apply();
  }

  /* Home Assistant themes describe a card's shape in tokens the shadow root
     cannot see through. Copy the three that matter onto the host. */
  _syncTheme() {
    const view = this.ownerDocument && this.ownerDocument.defaultView;
    if (!view) return;
    const styles = view.getComputedStyle(this);
    const take = (token, fallback) => {
      const value = styles.getPropertyValue(token);
      return value && value.trim() ? value.trim() : fallback;
    };
    this.style.setProperty("--pms-radius", take("--ha-card-border-radius", "12px"));
    this.style.setProperty("--pms-border-width", take("--ha-card-border-width", "1px"));
  }

  _escape(text) {
    return String(text).replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
  }

  /* Three rings on the water, started a beat apart so there is always one
     going. Same markup at the jet and at the skimmer — the skimmer's run
     backwards, which is the difference between water being pushed out and
     water being pulled in. */
  _ripples(kind, at) {
    return ["a", "b", "c"].map(which =>
      `<ellipse class="ripple ripple-${kind} ripple-${which}" cx="${at.x}" cy="${at.y}"></ellipse>`
    ).join("");
  }

  /* The markup, built once per configuration. `_apply` does the rest. */
  _build() {
    const background = this._config.background || SCENE_URL;
    /* Positions are in here: dragging one in the editor has to rebuild the
       scene, and nothing else would notice the coordinates had changed. */
    const signature = JSON.stringify([
      background, this._config.show_title, this._config.water, this._config.positions,
    ]);
    if (this._built === signature && this._nodes) return;

    const at = key => placement(this._config.positions, key);

    this.shadowRoot.innerHTML = `${this._styles()}
      <ha-card>
        <div class="scene">
          <svg viewBox="0 0 600 400" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
            <defs>
              <clipPath id="water-clip">
                <path d="${this._escape(this._config.water || WATER)}"></path>
              </clipPath>
              <linearGradient id="sky-fade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#03142b" stop-opacity="0.72"></stop>
                <stop offset="100%" stop-color="#03142b" stop-opacity="0"></stop>
              </linearGradient>
              <linearGradient id="deck-fade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#03142b" stop-opacity="0"></stop>
                <stop offset="100%" stop-color="#03142b" stop-opacity="0.66"></stop>
              </linearGradient>
              <radialGradient id="vignette" cx="50%" cy="45%" r="74%">
                <stop offset="55%" stop-color="#03142b" stop-opacity="0"></stop>
                <stop offset="100%" stop-color="#03142b" stop-opacity="0.6"></stop>
              </radialGradient>
              <radialGradient id="lamp-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stop-color="#fff3cf" stop-opacity="0.92"></stop>
                <stop offset="38%" stop-color="#ffe3a0" stop-opacity="0.5"></stop>
                <stop offset="72%" stop-color="#8ff0e6" stop-opacity="0.2"></stop>
                <stop offset="100%" stop-color="#8ff0e6" stop-opacity="0"></stop>
              </radialGradient>
            </defs>

            <image id="photo" href="${this._escape(background)}"
                   x="0" y="0" width="600" height="400"
                   preserveAspectRatio="xMidYMid slice"></image>
            <rect id="night-tint" x="0" y="0" width="600" height="400"></rect>
            <rect class="sky-fade" x="0" y="0" width="600" height="150"></rect>
            <rect class="deck-fade" x="0" y="260" width="600" height="140"></rect>
            <rect class="vignette" x="0" y="0" width="600" height="400"></rect>

            <g clip-path="url(#water-clip)">
              <g id="lamp">
                <ellipse class="lamp-glow" cx="${at("lamp").x}" cy="${at("lamp").y + 26}"
                         rx="185" ry="96"></ellipse>
                <ellipse class="lamp-core" cx="${at("lamp").x}" cy="${at("lamp").y}"
                         rx="15" ry="6"></ellipse>
              </g>
              <g id="surface">
                ${this._ripples("jet", at("jet"))}
                ${this._ripples("skimmer", at("skimmer"))}
              </g>
            </g>

            <!-- Out to the machines and back again. Not the plumbing: the run
                 is buried under the decking, so these two say which way the
                 water is going and leave the pipe out of it. -->
            <g id="flow">
              ${LEGS.map(leg =>
                `<path id="${leg.key.replace("_", "-")}" class="leg"
                       d="${legPath(at(leg.from), at(leg.to))}"></path>`).join("")}
            </g>

            <g id="swirl" transform="translate(${at("swirl").x} ${at("swirl").y})">
              ${SWIRL_RINGS.map(ring =>
                `<circle class="swirl-ring${ring.reverse ? " swirl-back" : ""}"
                         r="${ring.r}" stroke-dasharray="${ring.dash}"
                         style="animation-duration:${ring.dur}"></circle>`).join("")}
            </g>

            <g id="fan" transform="translate(${at("fan").x} ${at("fan").y})">
              <g class="fan-spin">
                ${FAN_BLADES.map(angle =>
                  `<path class="fan-blade" transform="rotate(${angle})"
                         d="M 0 0 L ${FAN_R} -5 A ${FAN_R} ${FAN_R} 0 0 1 ${
                    round(FAN_R * 0.94)} 8 Z"></path>`).join("")}
              </g>
              <circle class="fan-ring" cx="0" cy="0" r="${FAN_R}"></circle>
            </g>

            <!-- The translate stays on a wrapper: the rising animation is a
                 transform of its own, and one on the path would replace it. -->
            <g id="heat">
              ${HEAT_WAVES.map(wave =>
                `<g transform="translate(${at("heat_waves").x + wave.dx} ${
                  at("heat_waves").y})"><path class="heat-wave"
                   style="animation-delay:${wave.delay}" d="${HEAT_WAVE_PATH}"></path></g>`)
                .join("")}
            </g>

            <rect id="hp-display" class="display"
                  x="${round(at("heat_display").x - DISPLAY.w / 2)}"
                  y="${round(at("heat_display").y - DISPLAY.h / 2)}"
                  width="${DISPLAY.w}" height="${DISPLAY.h}" rx="2"></rect>
            <rect id="panel-display" class="display"
                  x="${round(at("panel_display").x - PANEL_DISPLAY.w / 2)}"
                  y="${round(at("panel_display").y - PANEL_DISPLAY.h / 2)}"
                  width="${PANEL_DISPLAY.w}" height="${PANEL_DISPLAY.h}" rx="1.5"></rect>
            <circle id="gauge" class="gauge" cx="${at("gauge").x}"
                    cy="${at("gauge").y}" r="6"></circle>

            ${this._config.show_title
              ? `<text id="title" class="title at-start" x="${at("title").x}"
                       y="${at("title").y}"></text>` : ""}

            <g id="node-filtration" class="node">
              <line class="guide" x1="${at("filtration").x}" y1="${at("filtration").y + 20}"
                    x2="${at("filtration").x}" y2="${at("filtration").y + 30}"></line>
              <text class="node-label" x="${at("filtration").x}" y="${at("filtration").y}"></text>
              <text class="node-value" x="${at("filtration").x}"
                    y="${at("filtration").y + 14}"></text>
            </g>

            <!-- Anchoring is a class, not the text-anchor attribute: the
                 stylesheet sets it too, and a stylesheet beats a
                 presentation attribute every time. -->
            <g id="node-heat" class="node">
              <line class="guide" x1="${at("heat").x - 6}" y1="${at("heat").y + 4}"
                    x2="${at("heat").x - 14}" y2="${at("heat").y + 4}"></line>
              <text class="node-label at-start" x="${at("heat").x}" y="${at("heat").y}"></text>
              <text class="node-value at-start" x="${at("heat").x}"
                    y="${at("heat").y + 14}"></text>
            </g>

            <g id="node-light" class="node">
              <text class="node-label" x="${at("light").x}" y="${at("light").y}"></text>
              <text class="node-value" x="${at("light").x}" y="${at("light").y + 14}"></text>
            </g>

            <g id="node-temp" class="node">
              <text class="node-label at-start" x="${at("temperature").x}"
                    y="${at("temperature").y}"></text>
              <text class="temp-value at-start" x="${at("temperature").x}"
                    y="${at("temperature").y + 28}"></text>
            </g>
          </svg>
        </div>
      </ha-card>`;

    const root = this.shadowRoot;
    const pick = selector => root.querySelector(selector);
    this._nodes = {
      card: pick("ha-card"),
      photo: pick("#photo"),
      night: pick("#night-tint"),
      lamp: pick("#lamp"),
      surface: pick("#surface"),
      flow: pick("#flow"),
      legBack: pick("#leg-back"),
      swirl: pick("#swirl"),
      fan: pick("#fan"),
      heat: pick("#heat"),
      hpDisplay: pick("#hp-display"),
      panelDisplay: pick("#panel-display"),
      gauge: pick("#gauge"),
      title: pick("#title"),
      filtration: pick("#node-filtration"),
      heatNode: pick("#node-heat"),
      light: pick("#node-light"),
      temp: pick("#node-temp"),
    };
    this._built = signature;
  }

  /* Everything that changes between renders: classes on, classes off, and
     four pairs of words. */
  _apply() {
    const nodes = this._nodes;
    const data = this._data;
    const S = data.strings;
    const report = data.report || {};
    const roles = report.roles || {};
    const config = this._config;

    const night = this._night();
    nodes.card.style.setProperty("--night", night.toFixed(3));
    /* The overlays alone leave a noon-bright photo looking like a photo with
       something over it; taking the light and the colour out of the picture
       itself is what makes it read as evening. */
    nodes.photo.style.filter =
      `brightness(${(1 - 0.34 * night).toFixed(3)}) saturate(${(1 - 0.42 * night).toFixed(3)})`;

    const circulating = this._circulating(roles);
    const heating = this._heating(roles);
    const light = roles.pool_light || null;
    const system = roles.pool_system || null;

    const running = !!(circulating && circulating.on);
    const warming = !!(heating && heating.working);

    nodes.swirl.classList.toggle("on", running);
    nodes.surface.classList.toggle("on", running);
    nodes.flow.classList.toggle("running", running);
    /* Water on its way back from a heat pump that is working is the warm
       one, and the only thing on the scene whose colour says so. */
    nodes.legBack.classList.toggle("warm", running && warming);

    nodes.fan.classList.toggle("on", warming);
    nodes.heat.classList.toggle("on", warming && heating.action !== "cooling");
    nodes.hpDisplay.classList.toggle("on", !!(heating && heating.on));
    nodes.panelDisplay.classList.toggle("on", system ? !!system.on : running);
    nodes.gauge.classList.toggle("on", running);

    nodes.lamp.classList.toggle("on", !!(light && light.on));

    if (nodes.title) {
      nodes.title.textContent = config.title || data.title || "";
    }

    const label = (node, text, value) => {
      if (!node) return;
      const show = config.show_labels && !!text;
      node.classList.toggle("hidden", !show);
      if (!show) return;
      node.querySelector(".node-label").textContent = text;
      node.querySelector(".node-value, .temp-value").textContent = value;
    };

    label(nodes.filtration,
      circulating ? S.report.filtration : "",
      circulating ? this._stateWord(S, circulating) : "");
    nodes.filtration.classList.toggle("active", running);

    label(nodes.heatNode,
      heating ? S.roles.heat_pump : "",
      heating ? this._stateWord(S, heating) : "");
    nodes.heatNode.classList.toggle("active", !!(heating && heating.on));

    label(nodes.light,
      light ? S.roles.pool_light : "",
      light ? this._stateWord(S, { on: light.on }) : "");
    nodes.light.classList.toggle("active", !!(light && light.on));

    /* Water temperature: whichever of the manual reading and the linked
       probe measured last, the same one the equipment card shows. */
    const reading = (report.current || {}).water_temperature;
    const probe = (data.live || {}).temperature;
    const values = report.values || {};
    const temperature = reading ? reading.value : values.water_temperature;
    const unit = (reading && reading.unit) || (probe && probe.unit)
      || S.units.water_temperature;
    const hasTemperature = config.show_temperature
      && temperature !== undefined && temperature !== null;
    nodes.temp.classList.toggle("hidden", !hasTemperature);
    if (hasTemperature) {
      nodes.temp.querySelector(".node-label").textContent = S.report.values.water_temperature;
      const value = nodes.temp.querySelector(".temp-value");
      /* Number and unit in one text node so they stay on one baseline, the
         unit smaller — the same shape the equipment card's hero reading has. */
      value.textContent = "";
      value.appendChild(document.createTextNode(String(temperature)));
      const suffix = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
      suffix.setAttribute("class", "temp-unit");
      suffix.textContent = unit;
      value.appendChild(suffix);
    }
  }

  _styles() {
    return `<style>
      *{box-sizing:border-box}
      :host{
        display:block;
        --pms-radius:12px;
        --pms-border-width:1px;
        --night:0;
      }
      ha-card{padding:0;overflow:hidden;border-radius:var(--pms-radius)}
      .empty{padding:16px;color:var(--secondary-text-color,#8a8f94)}
      .scene{display:block;line-height:0}
      svg{display:block;width:100%;height:auto}

      /* --- the photo and the time of day --------------------------- */
      #photo{transition:filter .8s ease}
      #night-tint{
        fill:#04142c;
        opacity:calc(var(--night) * .5);
        transition:opacity .8s ease;
      }
      .sky-fade{fill:url(#sky-fade);opacity:calc(.42 + var(--night) * .34)}
      .deck-fade{fill:url(#deck-fade);opacity:calc(.5 + var(--night) * .3)}
      .vignette{fill:url(#vignette);opacity:calc(.55 + var(--night) * .3)}

      /* --- out to the machines and back ----------------------------- */
      .leg{
        fill:none;
        stroke:transparent;
        stroke-width:2.4;
        stroke-linecap:round;
        transition:stroke .4s ease;
      }
      #flow.running .leg{
        stroke:#5ee7ff;
        stroke-dasharray:12 20;
        animation:stream 1.35s linear infinite;
        /* A dark hairline first so the stroke survives the pale concrete,
           then the glow, which is what carries it on the dark water. */
        filter:drop-shadow(0 0 .6px rgba(2,10,25,.95))
               drop-shadow(0 0 2.5px rgba(94,231,255,.55))
               drop-shadow(0 0 7px rgba(94,231,255,.35));
      }
      #flow.running .leg.warm{
        stroke:#ffb066;
        filter:drop-shadow(0 0 .6px rgba(2,10,25,.95))
               drop-shadow(0 0 2.5px rgba(255,176,102,.6))
               drop-shadow(0 0 8px rgba(255,143,60,.4));
      }
      @keyframes stream{to{stroke-dashoffset:-32}}

      /* --- the filter turning water over ---------------------------- */
      #swirl{opacity:0;transition:opacity .4s ease}
      #swirl.on{opacity:1}
      .swirl-ring{
        fill:none;
        stroke:#6fe6ff;
        stroke-width:2;
        stroke-linecap:round;
        opacity:.85;
        /* A circle's own box is centred on it, so the spin turns about the
           ring instead of about the corner of the drawing. */
        transform-box:fill-box;
        transform-origin:center;
        /* A dark hairline first so the rings survive the pale tank, then the
           glow, which is what carries them once the scene goes dark. */
        filter:drop-shadow(0 0 .6px rgba(2,10,25,.9))
               drop-shadow(0 0 3px rgba(111,230,255,.6));
      }
      #swirl.on .swirl-ring{animation:churn linear infinite}
      #swirl.on .swirl-back{animation-direction:reverse}
      @keyframes churn{to{transform:rotate(360deg)}}

      /* --- the water going in and coming out ------------------------ */
      .ripple{
        fill:none;
        stroke:rgba(226,251,255,.82);
        stroke-width:1.2;
        rx:3;ry:1.5;
        opacity:0;
      }
      #surface.on .ripple{animation:ripple 3s ease-out infinite}
      #surface.on .ripple-b{animation-delay:1s}
      #surface.on .ripple-c{animation-delay:2s}
      /* Pushed out at the jet, pulled in at the skimmer: one set of frames,
         run the other way round. */
      #surface.on .ripple-skimmer{animation-direction:reverse;opacity:.5}
      @keyframes ripple{
        0%{rx:3;ry:1.5;opacity:.85;stroke-width:1.4}
        100%{rx:30;ry:12;opacity:0;stroke-width:.4}
      }

      /* --- the heat pump ------------------------------------------- */
      .fan-blade{fill:rgba(236,248,255,.2)}
      .fan-ring{fill:none;stroke:rgba(236,248,255,.2);stroke-width:1.6;opacity:0}
      #fan{opacity:0;transition:opacity .4s ease}
      #fan.on{opacity:1}
      #fan.on .fan-ring{opacity:1}
      .fan-spin{transform-box:fill-box;transform-origin:center}
      #fan.on .fan-spin{animation:spin .55s linear infinite}
      @keyframes spin{to{transform:rotate(360deg)}}

      .heat-wave{
        fill:none;
        stroke:#ffab5e;
        stroke-width:2;
        stroke-linecap:round;
        opacity:0;
        transform-box:fill-box;
      }
      #heat.on .heat-wave{animation:rise 3s ease-out infinite}
      @keyframes rise{
        0%{opacity:0;transform:translateY(8px) scaleY(.55)}
        25%{opacity:.75}
        70%{opacity:.4}
        100%{opacity:0;transform:translateY(-18px) scaleY(1.2)}
      }

      /* --- lit panels ---------------------------------------------- */
      .display{fill:#7fe3ff;opacity:0;transition:opacity .4s ease}
      .display.on{
        opacity:calc(.28 + var(--night) * .45);
        filter:drop-shadow(0 0 3px rgba(127,227,255,.8));
      }
      .gauge{fill:none;stroke:#5ee7ff;stroke-width:1.4;opacity:0;transition:opacity .4s ease}
      .gauge.on{opacity:.55;animation:breathe 3.2s ease-in-out infinite}
      @keyframes breathe{50%{opacity:.15}}

      /* --- the lamp ------------------------------------------------ */
      #lamp{opacity:0;transition:opacity .9s ease}
      #lamp.on{opacity:calc(.55 + var(--night) * .45)}
      .lamp-glow{fill:url(#lamp-glow)}
      #lamp.on .lamp-glow{animation:shimmer 6s ease-in-out infinite}
      .lamp-core{fill:#fff6dd;filter:drop-shadow(0 0 6px rgba(255,235,180,.95))}
      @keyframes shimmer{
        0%,100%{opacity:1;transform:scale(1)}
        50%{opacity:.82;transform:scale(1.04)}
      }
      .lamp-glow{transform-box:fill-box;transform-origin:center}

      /* --- labels --------------------------------------------------- */
      .node{transition:opacity .3s ease}
      .node.hidden{display:none}
      text{
        font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif);
        paint-order:stroke;
      }
      .title{
        font-size:15px;font-weight:600;fill:#f4f9ff;letter-spacing:.01em;
        filter:drop-shadow(0 1px 3px rgba(2,10,25,.9));
      }
      .node-label{
        font-size:8.5px;font-weight:600;letter-spacing:.09em;
        text-transform:uppercase;text-anchor:middle;
        fill:rgba(219,235,250,.78);
        filter:drop-shadow(0 1px 2px rgba(2,10,25,.95));
      }
      .node-value{
        font-size:12px;font-weight:700;text-anchor:middle;fill:#eef6ff;
        filter:drop-shadow(0 1px 3px rgba(2,10,25,.95))
               drop-shadow(0 0 8px rgba(2,10,25,.6));
      }
      .temp-value{
        font-size:26px;font-weight:700;text-anchor:middle;fill:#f6fbff;
        filter:drop-shadow(0 2px 5px rgba(2,10,25,.95))
               drop-shadow(0 0 12px rgba(2,10,25,.6));
      }
      .temp-unit{font-size:14px;font-weight:600;fill:rgba(232,244,255,.82)}
      .at-start{text-anchor:start}
      .guide{stroke:rgba(219,235,250,.42);stroke-width:1;stroke-linecap:round}
      .node.active .node-value{fill:#8ff2ff}
      #node-heat.active .node-value{fill:#ffc287}
      #node-light.active .node-value{fill:#ffe6a8}
      .node:not(.active) .node-value{opacity:.72}

      /* Off screen, none of this is worth a frame. */
      :host(.offscreen) .leg,
      :host(.offscreen) .swirl-ring,
      :host(.offscreen) .ripple,
      :host(.offscreen) .fan-spin,
      :host(.offscreen) .heat-wave,
      :host(.offscreen) .gauge,
      :host(.offscreen) .lamp-glow{animation-play-state:paused}

      /* Everything above still reads as on or off without the motion. */
      @media (prefers-reduced-motion:reduce){
        .leg,.swirl-ring,.ripple,.fan-spin,.heat-wave,.gauge,.lamp-glow{
          animation:none !important;
        }
        #surface.on .ripple{opacity:.45;rx:14;ry:6}
        #heat.on .heat-wave{opacity:.55}
        .gauge.on{opacity:.55}
      }
    </style>`;
  }
}

class PoolSceneCardEditor extends HTMLElement {
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
    return [
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
      { name: "show_title", selector: { boolean: {} } },
      { name: "show_labels", selector: { boolean: {} } },
      { name: "show_temperature", selector: { boolean: {} } },
      {
        name: "night",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "auto", label: text.night_auto },
              { value: "day", label: text.night_day },
              { value: "night", label: text.night_night },
            ],
          },
        },
      },
      { name: "background", selector: { text: {} } },
    ];
  }

  _formData() {
    return {
      entry: this._config.entry,
      title: this._config.title,
      show_title: this._config.show_title !== false,
      show_labels: this._config.show_labels !== false,
      show_temperature: this._config.show_temperature !== false,
      night: this._config.night || "auto",
      background: this._config.background,
    };
  }

  _update() {
    if (!this._config) return;
    if (!this._form) {
      this.innerHTML = "";
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", event => this._valueChanged(event));
      this.appendChild(this._form);
      /* Built once and kept: rebuilding the row on every keystroke in the
         form would take the open dialog with it. */
      this._openButton = document.createElement("button");
      this._openButton.type = "button";
      this._openButton.className = "pms-open-positions";
      this._openButton.addEventListener("click", () => this._openPositions());
      const row = document.createElement("div");
      row.className = "pms-open-row";
      row.innerHTML = `<style>
        .pms-open-row{margin-top:16px}
        .pms-open-positions{
          font:inherit;font-size:.9rem;font-weight:500;cursor:pointer;
          padding:9px 16px;border-radius:999px;
          border:1px solid var(--divider-color,rgba(127,127,127,.35));
          background:transparent;color:var(--primary-color,#44739E);
        }
      </style>`;
      row.appendChild(this._openButton);
      this.appendChild(row);
    }
    const text = editorText(this._hass);
    this._openButton.textContent = text.pos_open;
    this._form.hass = this._hass;
    this._form.data = this._formData();
    this._form.schema = this._schema();
    this._form.computeLabel = schema => text[schema.name] || schema.name;
    this._form.computeHelper = schema => {
      if (schema.name === "entry") return text.entry_help;
      if (schema.name === "background") return text.background_help;
      return undefined;
    };
  }

  _valueChanged(event) {
    event.stopPropagation();
    const value = Object.assign({}, event.detail.value);
    this._emit(this._fromForm(value));
  }

  /* Only what differs from the defaults is written: a card the user never
     touched should have a two-line config, not a form dump. What the visual
     editor put there is carried across — it is not on this form, and
     rebuilding the config from the form alone would drop it. */
  _fromForm(value) {
    const config = { type: (this._config && this._config.type) || "custom:pool-scene-card" };
    if (value.entry) config.entry = value.entry;
    if (value.title) config.title = value.title;
    if (value.show_title === false) config.show_title = false;
    if (value.show_labels === false) config.show_labels = false;
    if (value.show_temperature === false) config.show_temperature = false;
    if (value.night && value.night !== "auto") config.night = value.night;
    if (value.background) config.background = value.background;
    if (this._config.water) config.water = this._config.water;
    const positions = this._config.positions || {};
    if (Object.keys(positions).length) config.positions = positions;
    return config;
  }

  _emit(config) {
    this._config = Object.assign({}, DEFAULTS, config);
    fireEvent(this, "config-changed", { config: config });
  }

  /* ---------------- the visual editor ---------------- */

  /* Everything on the scene is placed for the photo that ships with the
     integration. Point the card at your own and all of it is in the wrong
     place, so the way to fix it has to be dragging, not typing pairs of
     numbers into a form. */
  _openPositions() {
    if (this._modal) return;
    const text = editorText(this._hass);
    const modal = document.createElement("div");
    modal.className = "pms-pe";
    modal.innerHTML = `${this._positionStyles()}
      <div class="pms-pe-sheet" role="dialog" aria-modal="true">
        <header>
          <div>
            <p class="kicker">${this._escape(text.pos_kicker)}</p>
            <h3>${this._escape(text.pos_open)}</h3>
          </div>
          <div class="acts">
            <button type="button" data-reset>${this._escape(text.pos_reset)}</button>
            <button type="button" data-close class="primary">${
              this._escape(text.pos_done)}</button>
          </div>
        </header>
        <div class="stage">
          <svg viewBox="0 0 600 400" data-stage>
            <image href="${this._escape(this._config.background || SCENE_URL)}"
                   x="0" y="0" width="600" height="400"
                   preserveAspectRatio="xMidYMid slice"></image>
            <rect class="scrim" x="0" y="0" width="600" height="400"></rect>
            <g data-handles>${this._handles()}</g>
          </svg>
        </div>
        <p class="hint">${this._escape(text.pos_hint)}</p>
      </div>`;

    const svg = modal.querySelector("[data-stage]");
    svg.addEventListener("pointerdown", event => this._dragStart(event, svg));
    svg.addEventListener("pointermove", event => this._dragMove(event, svg));
    svg.addEventListener("pointerup", event => this._dragEnd(event));
    svg.addEventListener("pointercancel", event => this._dragEnd(event));
    modal.querySelector("[data-close]").addEventListener("click", () => this._closePositions());
    modal.querySelector("[data-reset]").addEventListener("click", () => {
      this._config = Object.assign({}, this._config, { positions: {} });
      this._emit(this._fromForm(this._formData()));
      this._redrawHandles();
    });
    /* Clicking the backdrop is the other way out of a dialog */
    modal.addEventListener("pointerdown", event => {
      if (event.target === modal) this._closePositions();
    });

    this.appendChild(modal);
    this._modal = modal;
  }

  _closePositions() {
    if (!this._modal) return;
    this._modal.remove();
    this._modal = null;
    this._drag = null;
  }

  _at(key) {
    return placement(this._config.positions, key);
  }

  /* One handle per row of LAYOUT, so nothing can be on the scene and not be
     draggable — the table is what both of them read. The legs are drawn as
     ghosts rather than handles: each one is tied to two anchors that have
     handles of their own, so it follows whichever of them moves. */
  _handles() {
    const text = editorText(this._hass);
    const name = key => this._escape(text["pos_" + key] || key);
    const ghosts = LEGS.map(leg =>
      `<path class="ghost" data-ghost="${leg.key}"
             d="${legPath(this._at(leg.from), this._at(leg.to))}"></path>`).join("");
    const handles = LAYOUT_GROUPS.map(group => Object.keys(LAYOUT)
      .filter(key => LAYOUT[key].group === group)
      .map(key => {
        const spec = LAYOUT[key];
        const at = this._at(key);
        return `<g class="handle ${spec.kind} ${spec.group}" data-handle="${key}"
                   transform="translate(${at.x} ${at.y})">
            <circle class="hit" r="15"></circle>
            ${spec.kind === "text"
              ? '<rect class="plate" x="-9" y="-9" width="18" height="18" rx="4"></rect>'
              : '<circle class="ring" r="8"></circle>'}
            <circle class="pip" r="2"></circle>
            <text class="cap" y="20">${name(key)}</text>
          </g>`;
      }).join("")).join("");
    return ghosts + handles;
  }

  _redrawHandles() {
    const layer = this._modal && this._modal.querySelector("[data-handles]");
    if (layer) layer.innerHTML = this._handles();
  }

  /* Pointer coordinates in the 600x400 space the scene is drawn in. */
  _stagePoint(event, svg) {
    const matrix = svg.getScreenCTM && svg.getScreenCTM();
    if (svg.createSVGPoint && matrix) {
      const point = svg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      return point.matrixTransform(matrix.inverse());
    }
    const rect = svg.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * 600,
      y: ((event.clientY - rect.top) / rect.height) * 400,
    };
  }

  _dragStart(event, svg) {
    const handle = event.target.closest && event.target.closest("[data-handle]");
    if (!handle) return;
    event.preventDefault();
    if (handle.setPointerCapture) handle.setPointerCapture(event.pointerId);
    const key = handle.dataset.handle;
    this._drag = {
      key, handle,
      start: this._stagePoint(event, svg),
      from: Object.assign({}, this._at(key)),
    };
    handle.classList.add("active");
    svg.classList.add("dragging");
  }

  _dragMove(event, svg) {
    if (!this._drag) return;
    event.preventDefault();
    const point = this._stagePoint(event, svg);
    const dx = point.x - this._drag.start.x;
    const dy = point.y - this._drag.start.y;
    const { key, from, handle } = this._drag;
    const at = Object.assign({}, from);
    /* Off the edge of the picture there is nothing to line up with, so a
       handle stops at it rather than being lost past the frame. */
    const clampX = value => Math.max(0, Math.min(600, round(value)));
    const clampY = value => Math.max(0, Math.min(400, round(value)));
    at.x = clampX(from.x + dx);
    at.y = clampY(from.y + dy);

    const positions = Object.assign({}, this._config.positions);
    positions[key] = at;
    this._config = Object.assign({}, this._config, { positions });

    handle.setAttribute("transform", `translate(${at.x} ${at.y})`);
    /* A leg is two anchors: whichever end just moved, redraw the curve. */
    LEGS.filter(leg => leg.from === key || leg.to === key).forEach(leg => {
      const ghost = svg.querySelector(`[data-ghost="${leg.key}"]`);
      if (ghost) ghost.setAttribute("d", legPath(this._at(leg.from), this._at(leg.to)));
    });
    /* The card behind the dialog is a live preview — repaint it as the
       handle moves, and let the debounce keep the storage writes down. */
    this._emitSoon();
  }

  _dragEnd(event) {
    if (!this._drag) return;
    const { handle } = this._drag;
    handle.classList.remove("active");
    if (handle.releasePointerCapture) handle.releasePointerCapture(event.pointerId);
    const svg = this._modal && this._modal.querySelector("[data-stage]");
    if (svg) svg.classList.remove("dragging");
    this._drag = null;
    if (this._emitTimer) clearTimeout(this._emitTimer);
    this._emitTimer = null;
    this._emit(this._fromForm(this._formData()));
  }

  _emitSoon() {
    if (this._emitTimer) return;
    this._emitTimer = setTimeout(() => {
      this._emitTimer = null;
      this._emit(this._fromForm(this._formData()));
    }, 120);
  }

  _escape(text) {
    return String(text === undefined || text === null ? "" : text)
      .replace(/[&<>"']/g, character => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      }[character]));
  }

  _positionStyles() {
    return `<style>
      .pms-pe{
        position:fixed;inset:0;z-index:9999;
        display:flex;align-items:center;justify-content:center;padding:16px;
        background:rgba(4,10,20,.62);
      }
      .pms-pe *{box-sizing:border-box}
      .pms-pe-sheet{
        width:min(860px,100%);max-height:100%;overflow:auto;
        background:var(--card-background-color,#fff);
        color:var(--primary-text-color,#212121);
        border-radius:14px;padding:16px;
        box-shadow:0 24px 60px rgba(2,8,20,.5);
      }
      .pms-pe header{display:flex;align-items:flex-start;gap:12px;margin-bottom:12px}
      .pms-pe header > div:first-child{flex:1;min-width:0}
      .pms-pe .kicker{
        margin:0;font-size:.7rem;font-weight:600;letter-spacing:.09em;
        text-transform:uppercase;color:var(--secondary-text-color,#8a8f94);
      }
      .pms-pe h3{margin:2px 0 0;font-size:1.05rem;font-weight:600}
      .pms-pe .acts{display:flex;gap:8px;flex:none}
      .pms-pe button{
        font:inherit;font-size:.86rem;font-weight:500;cursor:pointer;
        padding:7px 14px;border-radius:999px;
        border:1px solid var(--divider-color,rgba(127,127,127,.35));
        background:transparent;color:inherit;
      }
      .pms-pe button.primary{
        background:var(--primary-color,#44739E);border-color:transparent;
        color:var(--text-primary-color,#fff);
      }
      .pms-pe .stage{
        border-radius:10px;overflow:hidden;
        border:1px solid var(--divider-color,rgba(127,127,127,.35));
      }
      .pms-pe svg{display:block;width:100%;height:auto;touch-action:none}
      .pms-pe svg.dragging{cursor:grabbing}
      .pms-pe .scrim{fill:#04142c;opacity:.34}
      .pms-pe .handle{cursor:grab}
      .pms-pe svg.dragging .handle{cursor:grabbing}
      .pms-pe .hit{fill:transparent}
      .pms-pe .ring{
        fill:rgba(94,231,255,.16);stroke:#5ee7ff;stroke-width:1.6;
      }
      .pms-pe .plate{
        fill:rgba(94,231,255,.16);stroke:#5ee7ff;stroke-width:1.6;
      }
      .pms-pe .pip{fill:#eaf9ff}
      /* A leg's handle is the colour of the leg it belongs to */
      .pms-pe .flow .ring{fill:rgba(255,176,102,.18);stroke:#ffb066}
      .pms-pe .ghost{
        fill:none;stroke:#ffb066;stroke-width:1.6;stroke-dasharray:6 6;opacity:.9;
      }
      /* Sixteen names at once turned the picture into a wall of words, and
         the ones round the heat pump sat on top of each other. The shapes
         say where things are; the name is for the one under the pointer. */
      .pms-pe .cap{
        font-family:inherit;font-size:8.5px;font-weight:600;text-anchor:middle;
        fill:#f2fbff;paint-order:stroke;stroke:rgba(2,10,25,.9);stroke-width:3;
        opacity:0;pointer-events:none;transition:opacity .12s ease;
      }
      .pms-pe .handle:hover .cap{opacity:1}
      .pms-pe .handle:hover .ring,.pms-pe .handle:hover .plate{
        fill:rgba(94,231,255,.42);stroke-width:2.2;
      }
      .pms-pe .flow:hover .ring{fill:rgba(255,176,102,.45)}
      /* The one being dragged keeps its name up while the pointer runs off it */
      .pms-pe .handle.active .cap{opacity:1}
      .pms-pe .hint{
        margin:10px 2px 0;font-size:.82rem;color:var(--secondary-text-color,#8a8f94);
      }
    </style>`;
  }
}

/* Loaded twice (an old hand-added resource plus ours), the second define
   would throw and take the whole module down with it. */
if (!customElements.get("pool-scene-card")) {
  customElements.define("pool-scene-card", PoolSceneCard);
  customElements.define("pool-scene-card-editor", PoolSceneCardEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pool-scene-card",
  name: "Pool Scene",
  description: "The pool as a picture: filtration, heating and the light, animated.",
  documentationURL: "https://github.com/lucasgiovanny/pool-maintenance-tracker",
  preview: true,
});
