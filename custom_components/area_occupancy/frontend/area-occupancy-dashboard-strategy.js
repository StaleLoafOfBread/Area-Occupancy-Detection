/* Area Occupancy dashboard strategy. Entity IDs are resolved from HA registries,
 * so entity renames and different room/floor names do not require YAML edits. */
(() => {
  "use strict";

  const STRATEGY_TYPE = "area-occupancy";
  const STRATEGY_KIND = "dashboard";
  const DOMAIN = "area_occupancy";
  const BRAND_NAME = "Area Occupancy";
  const STRATEGY_TAG = `ll-strategy-dashboard-${STRATEGY_TYPE}`;
  const PROBABILITY_CARD_TAG = "area-occupancy-probability-card";
  const HA_ROOT_TAG = "home-assistant";
  const CONFIG_PATH_SEGMENT = "config";
  const ENTITY_PLACEHOLDER = "__ENTITY__";
  const ENTITY_ID_SEP = ".";
  const COUNTDOWN_TEXT_CLASS = "cd-txt";
  const DECAY_ICON_PREFIX = "⏳ ";
  const FLOOR_GROUP_KEY_PREFIX = "floor:";
  const PERCENT_SCALE = 100;
  const SECONDS_PER_MINUTE = 60;
  const COORDINATE_DECIMALS = 1;
  const I18N_PLACEHOLDER_PATTERN = /\{([a-z0-9_]+)\}/g;

  const CARD_TYPE = Object.freeze({
    BUTTON: "custom:button-card",
    AUTO_ENTITIES: "custom:auto-entities",
    TIME_PRIORS: "custom:area-occupancy-time-priors-card",
    PROBABILITY: `custom:${PROBABILITY_CARD_TAG}`,
    HISTORY_GRAPH: "history-graph",
    MARKDOWN: "markdown",
  });

  const ENTITY_DOMAIN = Object.freeze({
    SENSOR: "sensor",
    BINARY_SENSOR: "binary_sensor",
    MEDIA_PLAYER: "media_player",
    COVER: "cover",
    NUMBER: "number",
  });

  const SERVICE = Object.freeze({
    SET_VALUE: "set_value",
  });

  const ENTITY_STATE = Object.freeze({
    ON: "on",
    MISSING: "missing",
  });

  const ENTITY_ATTR = Object.freeze({
    ACTIVE_ENTITIES: "active_entities",
    ADJACENT_AREAS: "adjacent_areas",
    DECAYING_ENTITIES: "decaying_entities",
    DECAYING_EXPIRES_AT: "decaying_expires_at",
    DECAY_CLEAR_AT: "decay_clear_at",
    DETAILS: "details",
    ENVIRONMENTAL_ENTITIES: "environmental_entities",
    ISSUES: "issues",
    PRIOR_VALUE: "prior_value",
  });

  const DECAY_ITEM_KEY = Object.freeze({
    ENTITY_ID: "entity_id",
    DECAY_FACTOR: "decay_factor",
  });

  const AREA_MODE = Object.freeze({
    UNOCCUPIED: "unoccupied",
    LIVE: "live",
    DECAYING: "decaying",
    PRIOR: "prior",
    ENVIRONMENTAL: "environmental",
    SUPPORT: "support",
  });

  const SENSOR_STATE = Object.freeze({
    DECAY: "decay",
    ACTIVE: "active",
    IDLE: "idle",
  });

  const CARD_ACTION = Object.freeze({
    MORE_INFO: "more-info",
    NAVIGATE: "navigate",
  });

  const LAYOUT_TYPE = Object.freeze({
    GRID: "grid",
    HEADING: "heading",
    SECTIONS: "sections",
  });

  const HEADING_STYLE = Object.freeze({
    TITLE: "title",
  });

  const AUTO_ENTITIES_CONFIG = Object.freeze({
    VISIBILITY_CONDITION: "screen",
    CARD_PARAM: "cards",
  });

  const RANGE_ID = Object.freeze({
    D7: "7d",
    H24: "24h",
    H12: "12h",
    H1: "1h",
    M15: "15m",
    TODAY: "today",
  });

  const WS_TYPE = Object.freeze({
    AREA_REGISTRY: "config/area_registry/list",
    FLOOR_REGISTRY: "config/floor_registry/list",
    DEVICE_REGISTRY: "config/device_registry/list",
    ENTITY_REGISTRY: "config/entity_registry/list",
    HISTORY_DURING_PERIOD: "history/history_during_period",
    GET_TRANSLATIONS: "frontend/get_translations",
  });

  const TRANSLATION_CATEGORY = Object.freeze({
    COMMON: "common",
    ENTITY: "entity",
  });
  const COMMON_TRANSLATION_PREFIX = `component.${DOMAIN}.common.`;
  const ENTITY_TRANSLATION_PREFIX = `component.${DOMAIN}.entity.`;

  const I18N_KEY = Object.freeze({
    DASHBOARD_TITLE: "dashboard_title",
    STRATEGY_DESCRIPTION: "dashboard_strategy_description",
    VIEW_STATUS: "dashboard_view_status",
    VIEW_FORECAST: "dashboard_view_forecast",
    VIEW_INFO: "dashboard_view_info",
    AREAS_HEADING: "dashboard_areas_heading",
    SENSORS_AND_DECAY_HEADING: "dashboard_sensors_and_decay_heading",
    PROBABILITY_HISTORY_TITLE: "dashboard_probability_history_title",
    AREA_WEEKLY_FORECAST_TITLE: "dashboard_area_weekly_forecast_title",
    WEEKLY_FORECAST_TITLE: "dashboard_weekly_forecast_title",
    FLOOR_PROBABILITY_HISTORY_TITLE: "dashboard_floor_probability_history_title",
    FLOOR_AREA_PROBABILITIES_TITLE: "dashboard_floor_area_probabilities_title",
    STATE_OCCUPIED: "dashboard_state_occupied",
    STATE_UNOCCUPIED: "dashboard_state_unoccupied",
    OCCUPIED_AREAS_ONE: "dashboard_occupied_areas_one",
    OCCUPIED_AREAS_OTHER: "dashboard_occupied_areas_other",
    MODE_PRIOR: "dashboard_mode_prior",
    MODE_ENVIRONMENTAL: "dashboard_mode_environmental",
    MODE_SUPPORT: "dashboard_mode_support",
    PRIOR_READING: "dashboard_prior_reading",
    COUNT_PRIMARY: "dashboard_count_primary",
    COUNT_DECAYING: "dashboard_count_decaying",
    COUNT_ENVIRONMENTAL: "dashboard_count_environmental",
    DECAY_HOLDING: "dashboard_decay_holding",
    DECAY_IMMINENT: "dashboard_decay_imminent",
    COUNTDOWN_MINUTES_SECONDS: "dashboard_countdown_minutes_seconds",
    COUNTDOWN_SECONDS: "dashboard_countdown_seconds",
    SENSOR_ACTIVE: "dashboard_sensor_active",
    SENSOR_IDLE: "dashboard_sensor_idle",
    SENSOR_DECAY_PCT: "dashboard_sensor_decay_pct",
    PROBABILITY_TITLE: "dashboard_probability_title",
    PROBABILITY_BADGE: "dashboard_probability_badge",
    THRESHOLD_BADGE: "dashboard_threshold_badge",
    DRAG_THRESHOLD_HINT: "dashboard_drag_threshold_hint",
    HISTORY_LINK: "dashboard_history_link",
    HISTORY_LINK_TITLE: "dashboard_history_link_title",
    AXIS_NOW: "dashboard_axis_now",
    RANGE_7D: "dashboard_range_7d",
    RANGE_24H: "dashboard_range_24h",
    RANGE_12H: "dashboard_range_12h",
    RANGE_1H: "dashboard_range_1h",
    RANGE_15M: "dashboard_range_15m",
    RANGE_TODAY: "dashboard_range_today",
    NO_AREAS_TITLE: "dashboard_no_areas_title",
    NO_AREAS_BODY: "dashboard_no_areas_body",
    NO_AREAS_CTA: "dashboard_no_areas_cta",
    DISABLED_DIAGNOSTICS_TITLE: "dashboard_disabled_diagnostics_title",
    DISABLED_DIAGNOSTICS_ONE_ONE: "dashboard_disabled_diagnostics_one_one",
    DISABLED_DIAGNOSTICS_MANY_ONE: "dashboard_disabled_diagnostics_many_one",
    DISABLED_DIAGNOSTICS_MANY_MANY: "dashboard_disabled_diagnostics_many_many",
    DISABLED_DIAGNOSTICS_EVIDENCE_NOTE:
      "dashboard_disabled_diagnostics_evidence_note",
    DISABLED_DIAGNOSTICS_PRIOR_NOTE:
      "dashboard_disabled_diagnostics_prior_note",
    DISABLED_DIAGNOSTICS_CTA: "dashboard_disabled_diagnostics_cta",
    DISABLED_CORE_TITLE: "dashboard_disabled_core_title",
    DISABLED_CORE_BODY: "dashboard_disabled_core_body",
    UNAVAILABLE_TITLE: "dashboard_unavailable_title",
    UNAVAILABLE_BODY: "dashboard_unavailable_body",
    SENSOR_HEALTH_TITLE: "dashboard_sensor_health_title",
    SENSOR_HEALTH_BODY: "dashboard_sensor_health_body",
    SENSOR_HEALTH_COUNT_ONE: "dashboard_sensor_health_count_one",
    SENSOR_HEALTH_COUNT_OTHER: "dashboard_sensor_health_count_other",
    SENSOR_HEALTH_ISSUE_FALLBACK: "dashboard_sensor_health_issue_fallback",
  });

  const ENTITY_CATEGORY = Object.freeze({
    DIAGNOSTIC: "diagnostic",
  });

  const UNAVAILABLE_STATES = Object.freeze(["unavailable", "unknown"]);

  // Immutable registry matchers (domain, translation_key, unique_id)
  // so user entity_id renames never break entity discovery.
  const ENTITY_SPEC = Object.freeze({
    STATUS: Object.freeze({
      domain: ENTITY_DOMAIN.BINARY_SENSOR,
      translationKey: "occupancy_status",
      uniqueIdSuffix: "occupancy_status",
    }),
    PROBABILITY: Object.freeze({
      domain: ENTITY_DOMAIN.SENSOR,
      translationKey: "occupancy_probability",
      uniqueIdSuffix: "occupancy_probability",
    }),
    THRESHOLD: Object.freeze({
      domain: ENTITY_DOMAIN.NUMBER,
      translationKey: "threshold",
      uniqueIdSuffix: "occupancy_threshold",
    }),
    ACTIVITY: Object.freeze({
      domain: ENTITY_DOMAIN.SENSOR,
      translationKey: "detected_activity",
      uniqueIdSuffix: "detected_activity",
    }),
    EVIDENCE: Object.freeze({
      domain: ENTITY_DOMAIN.SENSOR,
      translationKey: "evidence",
      uniqueIdSuffix: "evidence",
    }),
    PRIOR: Object.freeze({
      domain: ENTITY_DOMAIN.SENSOR,
      translationKey: "prior_probability",
      uniqueIdSuffix: "prior_probability",
    }),
    SENSOR_HEALTH: Object.freeze({
      domain: ENTITY_DOMAIN.SENSOR,
      translationKey: "sensor_health",
      uniqueIdSuffix: "sensor_health",
    }),
  });

  const CORE_ENTITY_SPECS = Object.freeze([
    ENTITY_SPEC.STATUS,
    ENTITY_SPEC.PROBABILITY,
    ENTITY_SPEC.THRESHOLD,
    ENTITY_SPEC.ACTIVITY,
  ]);

  const DEVICE_ID = Object.freeze({
    ALL_AREAS: "all_areas",
    FLOOR_PREFIX: "floor_",
  });

  const ICON = Object.freeze({
    AREA: "mdi:home-outline",
    AREAS_GROUP: "mdi:home-group",
    DOOR: "mdi:door",
    FLASH: "mdi:flash",
    FLOOR: "mdi:floor-plan",
    STATUS: "mdi:home-account",
    FORECAST: "mdi:chart-box",
    INFO: "mdi:alert-circle-outline",
    OPEN_IN_NEW: "mdi:open-in-new",
    SENSORS: "mdi:radar",
    MOTION: "mdi:motion-sensor",
  });

  const ROUTE = Object.freeze({
    HISTORY: "/history",
    DEVICE_PREFIX: "/config/devices/device/",
    ENTITIES: `/config/entities?domain=${DOMAIN}`,
    INTEGRATION: `/config/integrations/integration/${DOMAIN}`,
  });

  const HISTORY_QUERY_PARAM = Object.freeze({
    ENTITY_ID: "entity_id",
    START_DATE: "start_date",
    END_DATE: "end_date",
    BACK: "back",
    BACK_ENABLED: "1",
  });

  const VIEW_CONFIG = Object.freeze({
    STATUS: Object.freeze({
      titleKey: I18N_KEY.VIEW_STATUS,
      path: "status",
      icon: ICON.STATUS,
    }),
    FORECAST: Object.freeze({
      titleKey: I18N_KEY.VIEW_FORECAST,
      path: "forecast",
      icon: ICON.FORECAST,
    }),
    INFO: Object.freeze({
      titleKey: I18N_KEY.VIEW_INFO,
      path: "info",
      icon: ICON.INFO,
    }),
  });

  const RGB = Object.freeze({
    OCCUPIED: "76,175,80",
    DECAYING: "255,152,0",
    PRIOR: "255,193,7",
    PROBABILITY: "66,165,245",
    NEUTRAL: "128,128,128",
  });

  const DIVIDER_COLOR = `var(--divider-color, rgba(${RGB.NEUTRAL},.2))`;

  const COLOR = Object.freeze({
    OCCUPIED: "#4caf50",
    UNOCCUPIED: "#9e9e9e",
    DECAYING: "#ff9800",
    PRIOR: "#ffc107",
    ENVIRONMENTAL: "#29b6f6",
    PROBABILITY: "#42a5f5",
    BORDER_OCCUPIED: `1px solid rgba(${RGB.OCCUPIED},.45)`,
    BORDER_DECAYING: `1px solid rgba(${RGB.DECAYING},.45)`,
    BORDER_PRIOR: `1px solid rgba(${RGB.PRIOR},.45)`,
    BORDER_DEFAULT: `1px solid ${DIVIDER_COLOR}`,
    SENSOR_BG_ACTIVE: `rgba(${RGB.OCCUPIED},.26)`,
    SENSOR_BG_DECAY: `rgba(${RGB.DECAYING},.28)`,
    SENSOR_BORDER_ACTIVE: `1px solid rgba(${RGB.OCCUPIED},.65)`,
    SENSOR_BORDER_DECAY: `1px solid rgba(${RGB.DECAYING},.6)`,
    TRACK_IDLE: `rgba(${RGB.NEUTRAL},.18)`,
    TRACK_SENSOR_IDLE: `rgba(${RGB.NEUTRAL},.15)`,
    TRACK_DECAY: `rgba(${RGB.DECAYING},.2)`,
    TRACK_SENSOR_DECAY: `rgba(${RGB.DECAYING},.18)`,
    CHART_AREA: `rgba(${RGB.PROBABILITY}, 0.16)`,
    CHART_TH_HISTORY: `rgba(${RGB.DECAYING}, 0.55)`,
    CHART_PILL_TEXT: "#111",
    DISABLED_TEXT: "var(--disabled-text-color, #888)",
    TEXT_PRIMARY: "var(--primary-text-color)",
    TEXT_SECONDARY: "var(--secondary-text-color)",
    CARD_BG: "var(--ha-card-background, var(--card-background-color))",
    FLOOR_BANNER_BG: `var(--secondary-background-color, rgba(${RGB.NEUTRAL},.08))`,
  });

  const CHART_CLASS = Object.freeze({
    HEADER: "header",
    TITLE_GROUP: "title-group",
    TITLE: "title",
    META: "meta",
    CHART: "chart",
    RANGES_WRAP: "ranges-wrap",
    RANGES: "ranges",
    RANGE_BTN: "range-btn",
    ACTIVE: "active",
    EDITABLE: "editable",
    HISTORY_LINK: "history-link",
    GRID: "grid",
    TICK: "tick",
    AREA: "area",
    LINE: "line",
    TH_HISTORY: "th-history",
    TH_LINE: "th-line",
    TH_PILL: "th-pill",
    TH_TEXT: "th-text",
    TH_HANDLE: "th-handle",
    BADGE: "badge",
    TH: "th",
    PROB: "prob",
    HINT: "hint",
  });

  const TIME_MS = Object.freeze({
    SECOND: 1_000,
    MINUTE: 60_000,
    HOUR: 3_600_000,
  });

  const DEFAULTS = Object.freeze({
    LANGUAGE: "en",
    SLUG_FALLBACK: "area",
    UNASSIGNED_FLOOR_KEY: "areas",
    DASHBOARD_PATH: "lovelace",
    DOCUMENTATION_URL: "https://hankanman.github.io/Area-Occupancy-Detection/",
    PROBABILITY_CARD_SIZE: 4,
    THRESHOLD: 50,
    THRESHOLD_MIN: 1,
    THRESHOLD_MAX: 100,
    HISTORY_HOURS: 24,
    DEFAULT_RANGE_ID: RANGE_ID.TODAY,
    FALLBACK_RANGE_ID: RANGE_ID.H24,
    MAX_COLUMNS: 4,
    VIEW_COLUMNS: 3,
    HISTORY_REFRESH_MS: TIME_MS.MINUTE,
    HISTORY_ERROR_BACKOFF_MS: 15_000,
    TRANSLATION_ERROR_BACKOFF_MS: 15_000,
    TRANSLATION_MAX_RETRIES: 3,
    PENDING_THRESHOLD_MS: 2_500,
    DRAG_DEADZONE_PX: 4,
    COUNTDOWN_TICK_MS: TIME_MS.SECOND,
    LOCALIZE_RETRY_DELAY_MS: 250,
    LOCALIZE_MAX_RETRIES: 20,
    ADJACENCY_SEARCH_BUDGET: 5_000,
  });

  const CARD_STYLE = Object.freeze({
    RADIUS: "16px",
    PADDING: "10px 14px",
    ICON_SIZE: "22px",
    FLOOR_ACCENT_WIDTH: "4px",
    FLOOR_NAME_SIZE: "16px",
    FLOOR_SECTION_GAP: "20px",
    STATUS_BAR_HEIGHT_PX: 6,
    STATUS_BAR_RADIUS_PX: 3,
    SENSOR_BAR_HEIGHT_PX: 4,
    SENSOR_BAR_RADIUS_PX: 2,
  });

  const FULL_WIDTH_GRID = Object.freeze({ columns: "full" });

  // Responsive column counts for the fixed-column grid inside auto-entities.
  const SENSOR_GRID_BREAKPOINTS = Object.freeze([
    Object.freeze({ columns: 1, mediaQuery: "(width <= 600px)" }),
    Object.freeze({
      columns: 2,
      mediaQuery: "(width > 600px) and (width < 1024px)",
    }),
    Object.freeze({
      columns: DEFAULTS.VIEW_COLUMNS,
      mediaQuery: "(width >= 1024px)",
    }),
  ]);

  // Single source of truth for per-area occupancy modes (color, border, and translation key).
  const AREA_MODE_STYLE = Object.freeze({
    [AREA_MODE.UNOCCUPIED]: Object.freeze({
      color: COLOR.UNOCCUPIED,
      border: COLOR.BORDER_DEFAULT,
      labelKey: null,
    }),
    [AREA_MODE.LIVE]: Object.freeze({
      color: COLOR.OCCUPIED,
      border: COLOR.BORDER_OCCUPIED,
      labelKey: null,
    }),
    [AREA_MODE.DECAYING]: Object.freeze({
      color: COLOR.DECAYING,
      border: COLOR.BORDER_DECAYING,
      labelKey: null,
    }),
    [AREA_MODE.PRIOR]: Object.freeze({
      color: COLOR.PRIOR,
      border: COLOR.BORDER_PRIOR,
      labelKey: I18N_KEY.MODE_PRIOR,
    }),
    [AREA_MODE.ENVIRONMENTAL]: Object.freeze({
      color: COLOR.PRIOR,
      border: COLOR.BORDER_PRIOR,
      labelKey: I18N_KEY.MODE_ENVIRONMENTAL,
    }),
    [AREA_MODE.SUPPORT]: Object.freeze({
      color: COLOR.PRIOR,
      border: COLOR.BORDER_PRIOR,
      labelKey: I18N_KEY.MODE_SUPPORT,
    }),
  });

  // Single source of truth for per-sensor card state styles and translation keys.
  const SENSOR_STATE_STYLE = Object.freeze({
    [SENSOR_STATE.DECAY]: Object.freeze({
      border: COLOR.SENSOR_BORDER_DECAY,
      iconColor: COLOR.DECAYING,
      background: COLOR.CARD_BG,
      barColor: COLOR.DECAYING,
      labelKey: null,
    }),
    [SENSOR_STATE.ACTIVE]: Object.freeze({
      border: COLOR.SENSOR_BORDER_ACTIVE,
      iconColor: COLOR.OCCUPIED,
      background: COLOR.SENSOR_BG_ACTIVE,
      barColor: COLOR.OCCUPIED,
      labelPrefix: "🟢 ",
      labelColor: COLOR.OCCUPIED,
      labelKey: I18N_KEY.SENSOR_ACTIVE,
    }),
    [SENSOR_STATE.IDLE]: Object.freeze({
      border: COLOR.BORDER_DEFAULT,
      iconColor: COLOR.DISABLED_TEXT,
      background: COLOR.CARD_BG,
      barColor: COLOR.TRACK_SENSOR_IDLE,
      labelPrefix: "⚪ ",
      labelOpacity: ".55",
      labelKey: I18N_KEY.SENSOR_IDLE,
    }),
  });

  const CHART_LAYOUT = Object.freeze({
    WIDTH: 900,
    MIN_WIDTH: 240,
    NARROW_WIDTH: 420,
    HEIGHT: 220,
    PAD_LEFT: 38,
    PAD_RIGHT_WITH_THRESHOLD: 44,
    PAD_RIGHT_NO_THRESHOLD: 16,
    PAD_TOP: 14,
    PAD_BOTTOM: 26,
    Y_LABEL_GAP: 6,
    Y_LABEL_OFFSET_Y: 4,
    X_LABEL_BOTTOM_GAP: 6,
    PILL_GAP_X: 4,
    PILL_WIDTH: 36,
    PILL_HEIGHT: 18,
    PILL_RADIUS: 4,
    PILL_OFFSET_Y: 9,
    PILL_TEXT_OFFSET_Y: 4,
    Y_TICKS: Object.freeze([0, 25, 50, 75, 100]),
    X_FRACTIONS: Object.freeze([0, 0.25, 0.5, 0.75, 1]),
    X_FRACTIONS_NARROW: Object.freeze([0, 0.5, 1]),
  });

  const CHART_PLOT_HEIGHT =
    CHART_LAYOUT.HEIGHT - CHART_LAYOUT.PAD_TOP - CHART_LAYOUT.PAD_BOTTOM;

  const PROBABILITY_CHART_RANGES = Object.freeze([
    Object.freeze({
      id: RANGE_ID.D7,
      labelKey: I18N_KEY.RANGE_7D,
      hours: 7 * DEFAULTS.HISTORY_HOURS,
    }),
    Object.freeze({
      id: RANGE_ID.H24,
      labelKey: I18N_KEY.RANGE_24H,
      hours: DEFAULTS.HISTORY_HOURS,
    }),
    Object.freeze({
      id: RANGE_ID.H12,
      labelKey: I18N_KEY.RANGE_12H,
      hours: 12,
    }),
    Object.freeze({ id: RANGE_ID.H1, labelKey: I18N_KEY.RANGE_1H, hours: 1 }),
    Object.freeze({
      id: RANGE_ID.M15,
      labelKey: I18N_KEY.RANGE_15M,
      hours: 15 / SECONDS_PER_MINUTE,
    }),
    Object.freeze({
      id: RANGE_ID.TODAY,
      labelKey: I18N_KEY.RANGE_TODAY,
      sinceMidnight: true,
      separated: true,
    }),
  ]);

  const PROBABILITY_CHART_RANGE_BY_ID = new Map(
    PROBABILITY_CHART_RANGES.map((range) => [range.id, range]),
  );

  const SENSOR_DOMAIN_ICONS = Object.freeze({
    [ENTITY_DOMAIN.MEDIA_PLAYER]: "mdi:play-circle",
    [ENTITY_DOMAIN.COVER]: "mdi:garage",
  });

  const FLOOR_LEVEL_ICONS = Object.freeze({
    [-1]: "mdi:home-floor-negative-1",
    0: "mdi:home-floor-0",
    1: "mdi:home-floor-1",
    2: "mdi:home-floor-2",
    3: "mdi:home-floor-3",
  });

  const SENSOR_DEVICE_CLASS_ICONS = Object.freeze({
    carbon_dioxide: "mdi:molecule-co2",
    current: ICON.FLASH,
    door: ICON.DOOR,
    humidity: "mdi:water-percent",
    illuminance: "mdi:brightness-6",
    motion: ICON.MOTION,
    occupancy: ICON.MOTION,
    opening: ICON.DOOR,
    pm25: "mdi:blur",
    power: ICON.FLASH,
    pressure: "mdi:gauge",
    temperature: "mdi:thermometer",
    volatile_organic_compounds: "mdi:air-filter",
  });

  // Converts a plain CSS rule map into button-card's single-key object array format.
  const styleList = (rules) =>
    Object.entries(rules).map(([prop, value]) => ({ [prop]: value }));

  const STATUS_CARD_BASE_STYLES = Object.freeze({
    grid: styleList({
      "grid-template-areas":
        "'i n headline' 'status status status' 'bar bar bar' 'counts counts counts'",
      "grid-template-columns": "1fr auto 1fr",
      "grid-template-rows": `auto auto ${CARD_STYLE.STATUS_BAR_HEIGHT_PX}px auto`,
      "column-gap": "8px",
      "row-gap": "6px",
    }),
    img_cell: styleList({
      "justify-self": "start",
      "justify-content": "flex-start",
      width: "auto",
    }),
    name: styleList({
      "grid-area": "n",
      "justify-self": "center",
      "text-align": "center",
      "font-weight": "700",
      color: COLOR.TEXT_PRIMARY,
      "white-space": "normal",
      overflow: "visible",
      "text-overflow": "unset",
      "max-width": "unset",
    }),
    custom_fields: Object.freeze({
      headline: styleList({
        "grid-area": "headline",
        "justify-self": "end",
        "font-size": "12px",
      }),
      status: styleList({
        "grid-area": "status",
        "justify-self": "stretch",
        width: "100%",
        "font-size": "12px",
        "line-height": "1.4",
      }),
      bar: styleList({ "grid-area": "bar", width: "100%" }),
      counts: styleList({
        "grid-area": "counts",
        "justify-self": "center",
        "font-size": "11px",
        "line-height": "1.3",
        opacity: "0.85",
      }),
    }),
  });

  const SENSOR_CARD_BASE_STYLES = Object.freeze({
    grid: styleList({
      "grid-template-areas": "'i n s' 'i bar bar'",
      "grid-template-columns": "28px minmax(0,1fr) auto",
      "grid-template-rows": "auto auto",
      "column-gap": "10px",
      "row-gap": "6px",
    }),
    name: styleList({
      "justify-self": "start",
      "font-weight": "600",
      "font-size": "13px",
      "text-overflow": "ellipsis",
      overflow: "hidden",
      "white-space": "nowrap",
    }),
    custom_fields: Object.freeze({
      s: styleList({
        "justify-self": "end",
        "font-size": "12px",
        "font-weight": "600",
      }),
      bar: styleList({ width: "100%" }),
    }),
  });

  // --- General helpers ---

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const fmtCoord = (value) => value.toFixed(COORDINATE_DECIMALS);

  /** Parse numeric HA states/attributes without coercing null, booleans, or blanks to 0. */
  function parseFiniteNumber(value, fallback = null) {
    if (
      value === null ||
      value === undefined ||
      typeof value === "boolean" ||
      (typeof value === "string" && value.trim() === "")
    ) {
      return fallback;
    }
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function slug(value) {
    const normalized = String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    return normalized || DEFAULTS.SLUG_FALLBACK;
  }

  const title = (value) => String(value || "").replaceAll("_", " ");

  const areaViewPath = (area) =>
    `area-${slug(area.name)}-${slug(area.area_id)}`;

  const floorViewPath = (group) =>
    `floor-${slug(group.label)}-${slug(group.floorId || group.label)}`;

  function resolveDashboardPath() {
    const first = window.location.pathname.split("/").filter(Boolean)[0];
    return first && first !== CONFIG_PATH_SEGMENT
      ? first
      : DEFAULTS.DASHBOARD_PATH;
  }

  // --- Localization helpers ---

  const TRANSLATION_CACHE = new Map();
  const ACTIVITY_STATE_SUBKEY = `${ENTITY_SPEC.ACTIVITY.domain}${ENTITY_ID_SEP}${ENTITY_SPEC.ACTIVITY.translationKey}.state.`;

  function getHassLanguage(hass) {
    return hass?.locale?.language || hass?.language || DEFAULTS.LANGUAGE;
  }

  function fetchTranslations(hass, category, languageOverride) {
    if (!hass?.callWS) {
      return Promise.resolve({});
    }
    const language = languageOverride || getHassLanguage(hass);
    const cacheKey = `${language}:${category}`;
    if (TRANSLATION_CACHE.has(cacheKey)) {
      return TRANSLATION_CACHE.get(cacheKey);
    }
    const promise = Promise.resolve()
      .then(() =>
        hass.callWS({
          type: WS_TYPE.GET_TRANSLATIONS,
          language,
          category,
          integration: [DOMAIN],
        }),
      )
      .then((res) => {
        const resources = res?.resources || {};
        if (!Object.keys(resources).length) {
          TRANSLATION_CACHE.delete(cacheKey);
        }
        return resources;
      })
      .catch((err) => {
        TRANSLATION_CACHE.delete(cacheKey);
        throw err;
      });
    TRANSLATION_CACHE.set(cacheKey, promise);
    return promise;
  }

  async function fetchTranslationsWithFallback(hass, category) {
    const loadSafe = (languageOverride) =>
      fetchTranslations(hass, category, languageOverride).catch(() => ({}));
    const primary = await loadSafe();
    if (Object.keys(primary).length > 0) return primary;

    await new Promise((resolve) =>
      setTimeout(resolve, DEFAULTS.LOCALIZE_RETRY_DELAY_MS),
    );
    const retried = await loadSafe();
    if (Object.keys(retried).length > 0) return retried;

    if (getHassLanguage(hass) !== DEFAULTS.LANGUAGE) {
      return loadSafe(DEFAULTS.LANGUAGE);
    }
    return {};
  }

  function translateKey(hass, resources, key, placeholders) {
    if (!key) return "";
    const fullKey = `${COMMON_TRANSLATION_PREFIX}${key}`;
    const raw = resources?.[fullKey];
    const localized = typeof raw === "string" ? raw : hass?.localize?.(fullKey);
    if (typeof localized !== "string" || !localized) {
      return "";
    }
    if (!placeholders) return localized;
    return localized.replace(I18N_PLACEHOLDER_PATTERN, (match, name) =>
      name in placeholders ? String(placeholders[name]) : match,
    );
  }

  function createTranslator(hass, resources = {}) {
    return (key, placeholders) =>
      translateKey(hass, resources, key, placeholders);
  }

  function escapeHtmlText(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  // Convert a localized placeholder pattern (e.g. "Prior {value}%") into a JS string
  // expression evaluated at button-card render time, preserving any locale word order.
  function templateStringToJsExpr(template, bindings) {
    const parts = [];
    let lastIdx = 0;
    for (const match of String(template || "").matchAll(
      I18N_PLACEHOLDER_PATTERN,
    )) {
      if (match.index > lastIdx) {
        parts.push(JSON.stringify(template.slice(lastIdx, match.index)));
      }
      const name = match[1];
      parts.push(
        name in bindings ? `(${bindings[name]})` : JSON.stringify(match[0]),
      );
      lastIdx = match.index + match[0].length;
    }
    if (lastIdx < String(template || "").length) {
      parts.push(JSON.stringify(template.slice(lastIdx)));
    }
    return parts.length ? parts.join(" + ") : JSON.stringify("");
  }

  function resolveAreaModeStyles(t) {
    return Object.fromEntries(
      Object.entries(AREA_MODE_STYLE).map(([mode, style]) => [
        mode,
        {
          color: style.color,
          border: style.border,
          label: style.labelKey ? escapeHtmlText(t(style.labelKey)) : "",
        },
      ]),
    );
  }

  function resolveSensorStateStyles(t) {
    return Object.fromEntries(
      Object.entries(SENSOR_STATE_STYLE).map(([state, style]) => {
        let label = "";
        if (style.labelKey) {
          const prefix = escapeHtmlText(style.labelPrefix || "");
          const text = escapeHtmlText(t(style.labelKey));
          const attrs = style.labelColor
            ? `style='color:${style.labelColor}'`
            : `style='opacity:${style.labelOpacity}'`;
          label = `<span ${attrs}>${prefix}${text}</span>`;
        }
        return [
          state,
          {
            border: style.border,
            iconColor: style.iconColor,
            background: style.background,
            barColor: style.barColor,
            label,
          },
        ];
      }),
    );
  }

  function extractActivityLabels(entityResources = {}) {
    const prefix = `${ENTITY_TRANSLATION_PREFIX}${ACTIVITY_STATE_SUBKEY}`;
    const labels = {};
    for (const [key, value] of Object.entries(entityResources || {})) {
      if (key.startsWith(prefix) && typeof value === "string" && value) {
        labels[key.slice(prefix.length)] = value;
      }
    }
    return labels;
  }

  // --- Home Assistant registry & layout helpers ---

  function domainIdentifiers(device) {
    return (device.identifiers || [])
      .filter(
        (item) => (Array.isArray(item) ? item[0] : item?.domain) === DOMAIN,
      )
      .map((item) => (Array.isArray(item) ? item[1] : item?.identifier))
      .filter(Boolean);
  }

  function isDomainDevice(device) {
    return domainIdentifiers(device).length > 0;
  }

  function isAggregateDevice(device, areasById) {
    return domainIdentifiers(device).some(
      (id) =>
        id === DEVICE_ID.ALL_AREAS ||
        (id.startsWith(DEVICE_ID.FLOOR_PREFIX) && !areasById?.has(id)),
    );
  }

  function indexEntitiesByDevice(registry) {
    const byDevice = new Map();
    for (const entity of registry) {
      if (entity.platform !== DOMAIN || !entity.device_id) continue;
      let list = byDevice.get(entity.device_id);
      if (!list) {
        list = [];
        byDevice.set(entity.device_id, list);
      }
      list.push(entity);
    }
    return byDevice;
  }

  function indexDevicesByIdentifier(devices) {
    const byId = new Map();
    for (const device of devices) {
      for (const id of domainIdentifiers(device)) {
        byId.set(id, device);
      }
    }
    return byId;
  }

  function entityDomain(entityId) {
    return typeof entityId === "string" ? entityId.split(ENTITY_ID_SEP)[0] : "";
  }

  function matchesEntitySpec(entity, spec) {
    if (spec.domain && entityDomain(entity.entity_id) !== spec.domain) {
      return false;
    }
    if (spec.translationKey && entity.translation_key) {
      return entity.translation_key === spec.translationKey;
    }
    return Boolean(
      spec.uniqueIdSuffix &&
      entity.unique_id?.endsWith(`_${spec.uniqueIdSuffix}`),
    );
  }

  function findEntity(entities, spec) {
    return entities.find(
      (entity) => !entity.disabled_by && matchesEntitySpec(entity, spec),
    )?.entity_id;
  }

  function gridSection(cards, columns = DEFAULTS.VIEW_COLUMNS) {
    const live = cards.filter(Boolean);
    if (!live.length) return undefined;
    return {
      type: LAYOUT_TYPE.GRID,
      cards: live,
      column_span: Math.min(columns, DEFAULTS.MAX_COLUMNS),
    };
  }

  function sections(cards, columns = DEFAULTS.MAX_COLUMNS) {
    const section = gridSection(cards, columns);
    return section ? [section] : [];
  }

  function singleCardSection(card, columns = DEFAULTS.VIEW_COLUMNS) {
    return card ? gridSection([card], columns) : undefined;
  }

  function headingSection(heading, icon, cards) {
    const live = cards.filter(Boolean);
    if (!live.length) return undefined;
    return gridSection(
      [
        {
          type: LAYOUT_TYPE.HEADING,
          heading,
          heading_style: HEADING_STYLE.TITLE,
          icon,
        },
        ...live,
      ],
      DEFAULTS.VIEW_COLUMNS,
    );
  }

  function sectionsView({
    title: viewTitle,
    path,
    icon,
    sections: viewSections,
    maxColumns = DEFAULTS.VIEW_COLUMNS,
    subview = false,
  }) {
    return {
      title: viewTitle,
      path,
      icon,
      type: LAYOUT_TYPE.SECTIONS,
      ...(subview ? { subview: true } : {}),
      max_columns: maxColumns,
      sections: viewSections,
    };
  }

  function buildAdjacencyGraph(items) {
    const byId = new Map(items.map((item) => [item.area.area_id, item]));
    const adjacency = new Map([...byId.keys()].map((id) => [id, new Set()]));

    for (const [id, item] of byId) {
      for (const neighbour of item.adjacentAreas || []) {
        if (neighbour === id || !byId.has(neighbour)) continue;
        adjacency.get(id).add(neighbour);
        adjacency.get(neighbour).add(id);
      }
    }
    return { byId, adjacency };
  }

  function comparePathsByName(left, right, nameFor) {
    const len = Math.min(left.length, right.length);
    for (let i = 0; i < len; i += 1) {
      const cmp = nameFor(left[i]).localeCompare(nameFor(right[i]));
      if (cmp !== 0) return cmp;
    }
    return left.length - right.length;
  }

  function orientPath(path, nameFor) {
    if (path.length <= 1) return path;
    const reversed = [...path].reverse();
    return comparePathsByName(path, reversed, nameFor) <= 0 ? path : reversed;
  }

  function collectConnectedComponents(remaining, adjacency, compareByName) {
    const visited = new Set();
    const components = [];

    for (const seed of [...remaining].sort(compareByName)) {
      if (visited.has(seed)) continue;
      const component = [];
      const queue = [seed];
      visited.add(seed);

      for (let head = 0; head < queue.length; head += 1) {
        const current = queue[head];
        component.push(current);
        for (const neighbour of adjacency.get(current)) {
          if (!remaining.has(neighbour) || visited.has(neighbour)) continue;
          visited.add(neighbour);
          queue.push(neighbour);
        }
      }
      component.sort(compareByName);
      components.push(component);
    }

    components.sort((left, right) => right.length - left.length);
    return components;
  }

  function buildComponentAdjacency(component, adjacency, compareByName) {
    const inComponent = new Set(component);
    const localAdj = new Map();
    let doubleEdgeCount = 0;

    for (const id of component) {
      const neighbours = [...adjacency.get(id)]
        .filter((neighbour) => inComponent.has(neighbour))
        .sort(compareByName);
      localAdj.set(id, neighbours);
      doubleEdgeCount += neighbours.length;
    }
    return { localAdj, isTree: doubleEdgeCount / 2 === component.length - 1 };
  }

  function findFarthestInTree(start, localAdj) {
    const parent = new Map([[start, null]]);
    const depth = new Map([[start, 0]]);
    const queue = [start];
    let farthest = start;
    let maxDepth = 0;

    for (let head = 0; head < queue.length; head += 1) {
      const current = queue[head];
      const currentDepth = depth.get(current);
      if (currentDepth > maxDepth) {
        maxDepth = currentDepth;
        farthest = current;
      }
      for (const neighbour of localAdj.get(current)) {
        if (parent.has(neighbour)) continue;
        parent.set(neighbour, current);
        depth.set(neighbour, currentDepth + 1);
        queue.push(neighbour);
      }
    }

    const path = [];
    for (let node = farthest; node !== null; node = parent.get(node)) {
      path.push(node);
    }
    return path.reverse();
  }

  function findLongestPathInTree(component, localAdj, nameFor) {
    // Two-pass BFS finds an exact diameter in O(V) time for any acyclic component.
    const firstPass = findFarthestInTree(component[0], localAdj);
    const diameter = findFarthestInTree(
      firstPass[firstPass.length - 1],
      localAdj,
    );
    return orientPath(diameter, nameFor);
  }

  function countReachableUnvisited(start, visited, localAdj) {
    const seen = new Set([start]);
    const queue = [start];

    for (let head = 0; head < queue.length; head += 1) {
      for (const neighbour of localAdj.get(queue[head])) {
        if (visited.has(neighbour) || seen.has(neighbour)) continue;
        seen.add(neighbour);
        queue.push(neighbour);
      }
    }
    return seen.size - 1;
  }

  function searchLongestPathInCyclicComponent(
    component,
    localAdj,
    nameFor,
    compareByName,
  ) {
    const targetLength = component.length;
    const starts = [...component].sort(
      (left, right) =>
        localAdj.get(left).length - localAdj.get(right).length ||
        compareByName(left, right),
    );
    const visited = new Set();
    const path = [];
    let bestPath = [];
    let steps = 0;

    const isSearchExhausted = () =>
      bestPath.length === targetLength ||
      steps >= DEFAULTS.ADJACENCY_SEARCH_BUDGET;

    const unvisitedDegree = (id) => {
      let count = 0;
      for (const neighbour of localAdj.get(id)) {
        if (!visited.has(neighbour)) count += 1;
      }
      return count;
    };

    const search = (current) => {
      steps += 1;
      if (path.length > bestPath.length) {
        bestPath = [...path];
      }
      if (isSearchExhausted()) return;

      const candidates = localAdj
        .get(current)
        .filter((neighbour) => !visited.has(neighbour));
      if (!candidates.length) return;
      if (
        path.length + countReachableUnvisited(current, visited, localAdj) <=
        bestPath.length
      ) {
        return;
      }

      // Prefer constrained neighbours first (Warnsdorff heuristic) to find Hamiltonian paths fast.
      candidates.sort(
        (left, right) =>
          unvisitedDegree(left) - unvisitedDegree(right) ||
          compareByName(left, right),
      );

      for (const next of candidates) {
        visited.add(next);
        path.push(next);
        search(next);
        path.pop();
        visited.delete(next);
        if (isSearchExhausted()) return;
      }
    };

    for (const start of starts) {
      if (isSearchExhausted()) break;
      visited.add(start);
      path.push(start);
      search(start);
      path.pop();
      visited.delete(start);
    }

    return orientPath(bestPath, nameFor);
  }

  function findLongestPathInComponent(
    component,
    adjacency,
    nameFor,
    compareByName,
  ) {
    if (component.length <= 1) return component;
    if (component.length === 2) return orientPath(component, nameFor);

    const { localAdj, isTree } = buildComponentAdjacency(
      component,
      adjacency,
      compareByName,
    );
    if (isTree) {
      return findLongestPathInTree(component, localAdj, nameFor);
    }

    return searchLongestPathInCyclicComponent(
      component,
      localAdj,
      nameFor,
      compareByName,
    );
  }

  /** Orders areas by repeatedly extracting the longest connected chain of adjacent areas. */
  function orderByAdjacency(items) {
    if (items.length <= 1) return [...items];

    const { byId, adjacency } = buildAdjacencyGraph(items);
    const remaining = new Set(byId.keys());
    const nameFor = (id) => byId.get(id)?.area.name || id;
    const compareByName = (left, right) =>
      nameFor(left).localeCompare(nameFor(right));
    const ordered = [];

    while (remaining.size) {
      const components = collectConnectedComponents(
        remaining,
        adjacency,
        compareByName,
      );
      let bestPath = [];

      for (const component of components) {
        if (component.length < bestPath.length) break;
        const candidate = findLongestPathInComponent(
          component,
          adjacency,
          nameFor,
          compareByName,
        );
        if (
          candidate.length > bestPath.length ||
          (candidate.length === bestPath.length &&
            comparePathsByName(candidate, bestPath, nameFor) < 0)
        ) {
          bestPath = candidate;
        }
      }

      for (const id of bestPath) {
        remaining.delete(id);
        ordered.push(byId.get(id));
      }
    }

    return ordered;
  }

  // --- Button-card JS template builders ---

  function jsTemplate(body) {
    return `[[[\n${body}\n]]]`;
  }

  // Inline finite-number parser for button-card templates (handles HA "unavailable"/"unknown" safely).
  const NUM_HELPER_JS =
    "const num = (v, fb = 0) => { if (v === null || v === undefined || typeof v === 'boolean' || (typeof v === 'string' && v.trim() === '')) return fb; const n = Number(v); return Number.isFinite(n) ? n : fb; };";

  // Inline HTML escaper for dynamic strings inserted into button-card HTML templates.
  const ESC_HTML_HELPER_JS =
    "const esc = (v) => String(v ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('\"', '&quot;').replaceAll(\"'\", '&#39;');";

  const headlineHtmlExpr = (colorExpr, labelExpr) =>
    `"<span style='white-space:nowrap'><span style='color:" + (${colorExpr}) + "'>●</span> <span style='color:${COLOR.TEXT_SECONDARY}'>" + (${labelExpr}) + "</span></span>"`;

  const statusLabelHtmlExpr = (occupiedExpr, colorExpr, labelExpr) =>
    `((${occupiedExpr}) ? "<span style='color:" + (${colorExpr}) + ";font-weight:600'>" + (${labelExpr}) + "</span>" : "<span style='color:${COLOR.TEXT_SECONDARY};opacity:.7'>" + (${labelExpr}) + "</span>")`;

  const readingRowHtmlExpr = (leftExpr, rightExpr) =>
    `"<div style='display:flex;justify-content:space-between;align-items:baseline;width:100%'>" + (${leftExpr}) + (${rightExpr}) + "</div>"`;

  const countdownHtmlExpr = (colorExpr, remainingExpr, extraStyle = "") =>
    `"<span style='color:" + (${colorExpr}) + "${extraStyle ? `;${extraStyle}` : ""}'>${DECAY_ICON_PREFIX}<span class='${COUNTDOWN_TEXT_CLASS}'>" + esc(formatRemaining(${remainingExpr})) + "</span></span>"`;

  const probabilityPctHtmlExpr = (valueExpr, colorExpr, suffixExpr = '""') =>
    `(${valueExpr} !== null ? "<span style='white-space:nowrap'><span style='font-weight:700;color:" + (${colorExpr}) + "'>" + Math.round(${valueExpr}) + "%</span>" + (${suffixExpr}) + "</span>" : "<span></span>")`;

  function progressBarHelperJs(heightPx, radiusPx) {
    return `
      const barBase = "height:${heightPx}px;border-radius:${radiusPx}px;overflow:hidden;width:100%;";
      const solidBar = (color) => "<div style='" + barBase + "background:" + color + "'></div>";
      const fillBar = (track, color, pct) =>
        "<div style='" + barBase + "background:" + track + "'><div style='height:100%;background:" + color + ";border-radius:${radiusPx}px;width:" + Math.min(${PERCENT_SCALE}, Math.max(0, pct)) + "%'></div></div>";
    `;
  }

  function buildCountdownTimerHelperJs(t) {
    const minSecExpr = templateStringToJsExpr(
      t(I18N_KEY.COUNTDOWN_MINUTES_SECONDS),
      {
        minutes: `Math.floor(sec / ${SECONDS_PER_MINUTE})`,
        seconds: `sec % ${SECONDS_PER_MINUTE}`,
      },
    );
    const secExpr = templateStringToJsExpr(t(I18N_KEY.COUNTDOWN_SECONDS), {
      seconds: "sec",
    });
    const imminentLiteral = JSON.stringify(t(I18N_KEY.DECAY_IMMINENT));
    return `
      const formatRemaining = (sec) =>
        sec >= ${SECONDS_PER_MINUTE}
          ? (${minSecExpr})
          : (sec ? (${secExpr}) : ${imminentLiteral});
      const stopCountdown = () => {
        this._cdEnd = null;
        if (this._cdTimer) { clearInterval(this._cdTimer); this._cdTimer = null; }
      };
      const remainingFromTarget = (targetMs) =>
        Math.max(0, Math.ceil((targetMs - Date.now()) / ${TIME_MS.SECOND}));
      const startCountdownTo = (targetMs) => {
        this._cdEnd = targetMs;
        if (!this._cdTimer) {
          this._cdTimer = setInterval(() => {
            if (!this.isConnected || !this._cdEnd) { stopCountdown(); return; }
            const node = this.shadowRoot?.querySelector(".${COUNTDOWN_TEXT_CLASS}");
            if (node) node.textContent = formatRemaining(remainingFromTarget(this._cdEnd));
          }, ${DEFAULTS.COUNTDOWN_TICK_MS});
        }
        return remainingFromTarget(this._cdEnd);
      };
    `;
  }

  function buildTemplateContext(t, entityResources) {
    const areaModes = resolveAreaModeStyles(t);
    const escT = (key, placeholders) => escapeHtmlText(t(key, placeholders));
    return {
      areaModeStylesJson: JSON.stringify(areaModes),
      aggregateModeStylesJson: JSON.stringify({
        [AREA_MODE.LIVE]: areaModes[AREA_MODE.LIVE],
        [AREA_MODE.UNOCCUPIED]: areaModes[AREA_MODE.UNOCCUPIED],
      }),
      sensorStateStylesJson: JSON.stringify(resolveSensorStateStyles(t)),
      countdownHelperJs: buildCountdownTimerHelperJs(t),
      priorExpr: templateStringToJsExpr(escT(I18N_KEY.PRIOR_READING), {
        value: "Math.round(priorValue)",
      }),
      occupiedLabel: JSON.stringify(escT(I18N_KEY.STATE_OCCUPIED)),
      unoccupiedLabel: JSON.stringify(escT(I18N_KEY.STATE_UNOCCUPIED)),
      occupiedFallback: JSON.stringify(t(I18N_KEY.STATE_OCCUPIED)),
      unoccupiedFallback: JSON.stringify(t(I18N_KEY.STATE_UNOCCUPIED)),
      holdingLabel: JSON.stringify(escT(I18N_KEY.DECAY_HOLDING)),
      countPrimary: JSON.stringify(escT(I18N_KEY.COUNT_PRIMARY)),
      countDecaying: JSON.stringify(escT(I18N_KEY.COUNT_DECAYING)),
      countEnvironmental: JSON.stringify(escT(I18N_KEY.COUNT_ENVIRONMENTAL)),
      occupiedOneExpr: templateStringToJsExpr(
        escT(I18N_KEY.OCCUPIED_AREAS_ONE),
        { occupied: "occupiedCount", total: "total" },
      ),
      occupiedOtherExpr: templateStringToJsExpr(
        escT(I18N_KEY.OCCUPIED_AREAS_OTHER),
        { occupied: "occupiedCount", total: "total" },
      ),
      decayPctExpr: templateStringToJsExpr(escT(I18N_KEY.SENSOR_DECAY_PCT), {
        percent: "decayPct",
      }),
      activityLabelsJson: JSON.stringify(
        extractActivityLabels(entityResources),
      ),
      sensorIconTemplate: buildSensorIconTemplate(),
    };
  }

  /**
   * Shared state-resolution prelude for per-area button-card JS templates.
   * Defines: num, probEntity, occupied, thresholdValue, threshold, probabilityValue,
   * probability, active, decaying, dominantDecay, maxDecay, primary, environmental,
   * priorValue, prior, decayClearAtMs, hasValidClearAt, mode, modeStyle, stateColor.
   */
  function areaStatePrelude(
    statusId,
    probabilityId,
    thresholdId,
    priorId,
    areaModeStylesJson,
  ) {
    const sensorPrefix = JSON.stringify(`${ENTITY_DOMAIN.SENSOR}${ENTITY_ID_SEP}`);
    const envAttrKey = JSON.stringify(ENTITY_ATTR.ENVIRONMENTAL_ENTITIES);
    return `
      ${NUM_HELPER_JS}
      const probEntity = ${probabilityId} ? states[${probabilityId}] : null;
      const probabilityValue = num(probEntity?.state, null);
      const probability = probabilityValue ?? 0;
      const thresholdValue = ${thresholdId} ? num(states[${thresholdId}]?.state, null) : null;
      const threshold = thresholdValue ?? ${DEFAULTS.THRESHOLD};
      const statusEntity = ${statusId} ? states[${statusId}] : null;
      const occupied = statusEntity
        ? statusEntity.state === ${JSON.stringify(ENTITY_STATE.ON)}
        : (probabilityValue !== null && probabilityValue >= threshold);
      const active = probEntity?.attributes?.${ENTITY_ATTR.ACTIVE_ENTITIES} || [];
      const decaying = (probEntity?.attributes?.${ENTITY_ATTR.DECAYING_ENTITIES} || [])
        .filter((item) => item && typeof item === "object" && item.${DECAY_ITEM_KEY.ENTITY_ID})
        .map((item) => ({
          ${DECAY_ITEM_KEY.ENTITY_ID}: item.${DECAY_ITEM_KEY.ENTITY_ID},
          ${DECAY_ITEM_KEY.DECAY_FACTOR}: num(item.${DECAY_ITEM_KEY.DECAY_FACTOR}, 0),
        }));
      const dominantDecay = decaying.reduce(
        (best, item) => (!best || item.${DECAY_ITEM_KEY.DECAY_FACTOR} > best.${DECAY_ITEM_KEY.DECAY_FACTOR} ? item : best),
        null
      );
      const maxDecay = dominantDecay ? dominantDecay.${DECAY_ITEM_KEY.DECAY_FACTOR} : 0;
      const decayingIds = decaying.map((item) => item.${DECAY_ITEM_KEY.ENTITY_ID});
      const live = active.filter((id) => !decayingIds.includes(id));
      const environmentalAttr = probEntity?.attributes?.[${envAttrKey}];
      const isEnvironmental = Array.isArray(environmentalAttr)
        ? (id) => environmentalAttr.includes(id)
        : (id) => id.startsWith(${sensorPrefix});
      const primary = live.filter((id) => !isEnvironmental(id));
      const environmental = live.filter((id) => isEnvironmental(id));
      const attrPrior = num(probEntity?.attributes?.${ENTITY_ATTR.PRIOR_VALUE}, null);
      const sensorPrior = ${priorId} ? num(states[${priorId}]?.state, null) : null;
      const priorValue = attrPrior !== null ? attrPrior * ${PERCENT_SCALE} : sensorPrior;
      const prior = priorValue ?? 0;
      const decayClearAtMs =
        typeof probEntity?.attributes?.${ENTITY_ATTR.DECAY_CLEAR_AT} === "string"
          ? Date.parse(probEntity.attributes.${ENTITY_ATTR.DECAY_CLEAR_AT})
          : NaN;
      const hasValidClearAt = Number.isFinite(decayClearAtMs);
      const resolveMode = () => {
        if (!occupied) return "${AREA_MODE.UNOCCUPIED}";
        if (primary.length > 0) return "${AREA_MODE.LIVE}";
        if (priorValue !== null && prior >= threshold) return "${AREA_MODE.PRIOR}";
        if (decaying.length > 0 || hasValidClearAt) return "${AREA_MODE.DECAYING}";
        return environmental.length > 0 ? "${AREA_MODE.ENVIRONMENTAL}" : "${AREA_MODE.SUPPORT}";
      };
      const mode = resolveMode();
      const modeStyle = (${areaModeStylesJson})[mode];
      const stateColor = modeStyle.color;
    `;
  }

  function sensorStateTemplate(probabilityId, stateStylesJson, body) {
    return jsTemplate(`
      ${NUM_HELPER_JS}
      const pr = states[${probabilityId}];
      const active = pr?.attributes?.${ENTITY_ATTR.ACTIVE_ENTITIES} || [];
      const decaying = pr?.attributes?.${ENTITY_ATTR.DECAYING_ENTITIES} || [];
      const entityId = entity?.entity_id;
      const decay = decaying.find((item) => item?.${DECAY_ITEM_KEY.ENTITY_ID} === entityId);
      const isActive = active.includes(entityId);
      const resolveSensorState = () => {
        if (decay) return "${SENSOR_STATE.DECAY}";
        return isActive ? "${SENSOR_STATE.ACTIVE}" : "${SENSOR_STATE.IDLE}";
      };
      const sensorState = resolveSensorState();
      const stateStyle = (${stateStylesJson})[sensorState];
      const decayFactor = decay ? num(decay.${DECAY_ITEM_KEY.DECAY_FACTOR}, 0) : 0;
      const decayPct = Math.round(decayFactor * ${PERCENT_SCALE});
      ${body}
    `);
  }

  function buildAggregateStatusTemplates(
    statusId,
    probabilityId,
    priorId,
    memberStatusIds,
    templateCtx,
  ) {
    const aggregatePrelude = `
      ${NUM_HELPER_JS}
      const memberIds = ${memberStatusIds};
      const occupied = ${statusId} ? states[${statusId}]?.state === ${JSON.stringify(ENTITY_STATE.ON)} : memberIds.some((id) => states[id]?.state === ${JSON.stringify(ENTITY_STATE.ON)});
      const modeStyle = (${templateCtx.aggregateModeStylesJson})[occupied ? "${AREA_MODE.LIVE}" : "${AREA_MODE.UNOCCUPIED}"];
      const stateColor = modeStyle.color;
      const label = occupied ? ${templateCtx.occupiedLabel} : ${templateCtx.unoccupiedLabel};
    `;
    return {
      stateColor: jsTemplate(`${aggregatePrelude} return stateColor;`),
      cardBorder: jsTemplate(`${aggregatePrelude} return modeStyle.border;`),
      accentBorder: jsTemplate(
        `${aggregatePrelude} return "${CARD_STYLE.FLOOR_ACCENT_WIDTH} solid " + stateColor;`,
      ),
      headline: jsTemplate(
        `${aggregatePrelude} return ${headlineHtmlExpr("stateColor", "label")};`,
      ),
      reading: jsTemplate(`
        ${aggregatePrelude}
        const probValue = ${probabilityId} ? num(states[${probabilityId}]?.state, null) : null;
        const priorValue = ${priorId} ? num(states[${priorId}]?.state, null) : null;
        const probColor = occupied ? stateColor : "${COLOR.TEXT_PRIMARY}";
        const leftHtml = priorValue !== null
          ? ${statusLabelHtmlExpr("false", "stateColor", templateCtx.priorExpr)}
          : "<span></span>";
        const pctHtml = ${probabilityPctHtmlExpr("probValue", "probColor")};
        return ${readingRowHtmlExpr("leftHtml", "pctHtml")};
      `),
      counts: jsTemplate(`
        const ids = ${memberStatusIds};
        const total = ids.length;
        if (!total) return "";
        const occupiedCount = ids.filter((id) => states[id]?.state === ${JSON.stringify(ENTITY_STATE.ON)}).length;
        const ratio = total === 1 ? (${templateCtx.occupiedOneExpr}) : (${templateCtx.occupiedOtherExpr});
        return occupiedCount
          ? "<span style='color:${COLOR.OCCUPIED}'>" + ratio + "</span>"
          : "<span style='color:${COLOR.TEXT_SECONDARY}'>" + ratio + "</span>";
      `),
      bar: jsTemplate(`
        ${aggregatePrelude}
        ${progressBarHelperJs(CARD_STYLE.STATUS_BAR_HEIGHT_PX, CARD_STYLE.STATUS_BAR_RADIUS_PX)}
        if (occupied) return solidBar(stateColor);
        const probValue = ${probabilityId} ? num(states[${probabilityId}]?.state, 0) : 0;
        return fillBar("${COLOR.TRACK_IDLE}", stateColor, probValue);
      `),
    };
  }

  function buildAreaReadingTemplate(prelude, templateCtx) {
    return jsTemplate(`
      ${prelude}
      ${ESC_HTML_HELPER_JS}
      ${templateCtx.countdownHelperJs}
      const probColor = occupied ? stateColor : "${COLOR.TEXT_PRIMARY}";
      const thresholdPart = thresholdValue !== null
        ? "<span style='color:${COLOR.TEXT_SECONDARY};opacity:.75'> / " + Math.round(thresholdValue) + "%</span>"
        : "";
      const pctHtml = ${probabilityPctHtmlExpr("probabilityValue", "probColor", "thresholdPart")};
      let leftHtml = "";
      if (mode === "${AREA_MODE.DECAYING}") {
        if (hasValidClearAt) {
          const remaining = startCountdownTo(decayClearAtMs);
          leftHtml = ${countdownHtmlExpr("stateColor", "remaining", "font-weight:600")};
        } else {
          stopCountdown();
          leftHtml = ${statusLabelHtmlExpr("true", "stateColor", templateCtx.holdingLabel)};
        }
      } else {
        stopCountdown();
        const showPrior = mode === "${AREA_MODE.UNOCCUPIED}" || mode === "${AREA_MODE.LIVE}";
        const modeLabel = showPrior
          ? (priorValue !== null ? (${templateCtx.priorExpr}) : "")
          : modeStyle.label;
        leftHtml = modeLabel
          ? ${statusLabelHtmlExpr("occupied && !showPrior", "stateColor", "modeLabel")}
          : "<span></span>";
      }
      return ${readingRowHtmlExpr("leftHtml", "pctHtml")};
    `);
  }

  function buildAreaStatusTemplates(prelude, activityId, templateCtx) {
    const unavailableJson = JSON.stringify(UNAVAILABLE_STATES);
    return {
      stateColor: jsTemplate(`${prelude} return stateColor;`),
      cardBorder: jsTemplate(`${prelude} return modeStyle.border;`),
      headline: jsTemplate(`
        ${prelude}
        ${ESC_HTML_HELPER_JS}
        const activityState = ${activityId} ? states[${activityId}]?.state : null;
        const hasActivity = activityState && !(${unavailableJson}).includes(activityState);
        const activityLabels = ${templateCtx.activityLabelsJson};
        const activity = hasActivity
          ? (activityLabels[activityState] || activityState.replaceAll("_", " "))
          : (occupied ? ${templateCtx.occupiedFallback} : ${templateCtx.unoccupiedFallback});
        return ${headlineHtmlExpr("stateColor", "esc(activity)")};
      `),
      reading: buildAreaReadingTemplate(prelude, templateCtx),
      counts: jsTemplate(`
        ${prelude}
        if (!probEntity) return "";
        const countSpan = (label, count, color) =>
          count ? "<span style='color:" + color + "'>" + label + " " + count + "</span>" : label + " 0";
        return "<span style='color:${COLOR.TEXT_SECONDARY}'>" +
          countSpan(${templateCtx.countPrimary}, primary.length, "${COLOR.OCCUPIED}") + " · " +
          countSpan(${templateCtx.countDecaying}, decaying.length, "${COLOR.DECAYING}") + " · " +
          countSpan(${templateCtx.countEnvironmental}, environmental.length, "${COLOR.ENVIRONMENTAL}") +
        "</span>";
      `),
      bar: jsTemplate(`
        ${prelude}
        ${progressBarHelperJs(CARD_STYLE.STATUS_BAR_HEIGHT_PX, CARD_STYLE.STATUS_BAR_RADIUS_PX)}
        if (mode === "${AREA_MODE.UNOCCUPIED}") {
          const width = probabilityValue !== null && threshold > 0
            ? (probability / threshold) * ${PERCENT_SCALE}
            : 0;
          return fillBar("${COLOR.TRACK_IDLE}", stateColor, width);
        }
        if (mode === "${AREA_MODE.DECAYING}") {
          return decaying.length > 0
            ? fillBar("${COLOR.TRACK_DECAY}", stateColor, maxDecay * ${PERCENT_SCALE})
            : solidBar(stateColor);
        }
        return solidBar(stateColor);
      `),
    };
  }

  function buildStatusCardStyles(
    cardBorder,
    stateColor,
    { isAggregate = false, accentBorder, topMargin } = {},
  ) {
    const cardRules = {
      "border-radius": CARD_STYLE.RADIUS,
      padding: CARD_STYLE.PADDING,
      border: cardBorder,
      ...(isAggregate ? { background: COLOR.FLOOR_BANNER_BG } : {}),
      ...(accentBorder ? { "border-left": accentBorder } : {}),
      ...(topMargin ? { "margin-top": topMargin } : {}),
    };
    return {
      ...STATUS_CARD_BASE_STYLES,
      ...(isAggregate
        ? {
            name: [
              ...STATUS_CARD_BASE_STYLES.name,
              { "font-size": CARD_STYLE.FLOOR_NAME_SIZE },
            ],
          }
        : {}),
      card: styleList(cardRules),
      icon: styleList({ color: stateColor, width: CARD_STYLE.ICON_SIZE }),
    };
  }

  function buildSensorIconTemplate() {
    const domainIconsJson = JSON.stringify(SENSOR_DOMAIN_ICONS);
    const deviceClassIconsJson = JSON.stringify(SENSOR_DEVICE_CLASS_ICONS);
    return jsTemplate(`
      if (entity?.attributes?.icon) return entity.attributes.icon;
      const domain = entity?.entity_id?.split("${ENTITY_ID_SEP}")[0];
      const domainIcons = ${domainIconsJson};
      if (domainIcons[domain]) return domainIcons[domain];
      const icons = ${deviceClassIconsJson};
      return icons[entity?.attributes?.device_class] || (domain === "${ENTITY_DOMAIN.BINARY_SENSOR}" ? "${ICON.MOTION}" : "${ICON.SENSORS}");
    `);
  }

  function buildSensorNameTemplate(area) {
    const prefixes = JSON.stringify([
      ...new Set([area.name, area.name.split(" ")[0]].filter(Boolean)),
    ]);
    return jsTemplate(`
      const name = entity?.attributes?.friendly_name || entity?.entity_id?.split("${ENTITY_ID_SEP}")[1]?.replaceAll("_", " ") || "";
      const prefixes = ${prefixes};
      const prefix = prefixes.find((value) => name.toLowerCase().startsWith(value.toLowerCase() + " "));
      const stripped = prefix ? name.slice(prefix.length + 1).trim() : "";
      return stripped || name;
    `);
  }

  function buildSensorCountdownTemplate(probabilityId, templateCtx) {
    return sensorStateTemplate(
      probabilityId,
      templateCtx.sensorStateStylesJson,
      `
        ${ESC_HTML_HELPER_JS}
        ${templateCtx.countdownHelperJs}
        if (sensorState === "${SENSOR_STATE.DECAY}") {
          const rawExpires = entityId ? pr?.attributes?.${ENTITY_ATTR.DECAYING_EXPIRES_AT}?.[entityId] : null;
          const expiresAtMs = typeof rawExpires === "string" ? Date.parse(rawExpires) : NaN;
          if (Number.isFinite(expiresAtMs)) {
            const remaining = startCountdownTo(expiresAtMs);
            return ${countdownHtmlExpr("stateStyle.iconColor", "remaining", "white-space:nowrap")};
          }
          stopCountdown();
          return "<span style='color:" + stateStyle.iconColor + "'>${DECAY_ICON_PREFIX}" + (${templateCtx.decayPctExpr}) + "</span>";
        }
        stopCountdown();
        return stateStyle.label;
      `,
    );
  }

  function buildSensorItemCard(area, probability, templateCtx) {
    const probabilityId = JSON.stringify(probability || "");

    return {
      type: CARD_TYPE.BUTTON,
      entity: ENTITY_PLACEHOLDER,
      triggers_update: [ENTITY_PLACEHOLDER, probability].filter(Boolean),
      icon: templateCtx.sensorIconTemplate,
      name: buildSensorNameTemplate(area),
      tap_action: { action: CARD_ACTION.MORE_INFO },
      styles: {
        ...SENSOR_CARD_BASE_STYLES,
        card: styleList({
          "border-radius": CARD_STYLE.RADIUS,
          padding: CARD_STYLE.PADDING,
          background: sensorStateTemplate(
            probabilityId,
            templateCtx.sensorStateStylesJson,
            `
              if (sensorState === "${SENSOR_STATE.DECAY}") {
                return "linear-gradient(90deg, ${COLOR.SENSOR_BG_DECAY} " + decayPct + "%, ${COLOR.CARD_BG} " + decayPct + "%)";
              }
              return stateStyle.background;
            `,
          ),
          border: sensorStateTemplate(
            probabilityId,
            templateCtx.sensorStateStylesJson,
            "return stateStyle.border;",
          ),
        }),
        icon: styleList({
          width: CARD_STYLE.ICON_SIZE,
          height: CARD_STYLE.ICON_SIZE,
          color: sensorStateTemplate(
            probabilityId,
            templateCtx.sensorStateStylesJson,
            "return stateStyle.iconColor;",
          ),
        }),
      },
      custom_fields: {
        s: buildSensorCountdownTemplate(probabilityId, templateCtx),
        bar: sensorStateTemplate(
          probabilityId,
          templateCtx.sensorStateStylesJson,
          `
            ${progressBarHelperJs(CARD_STYLE.SENSOR_BAR_HEIGHT_PX, CARD_STYLE.SENSOR_BAR_RADIUS_PX)}
            if (sensorState === "${SENSOR_STATE.DECAY}") return fillBar("${COLOR.TRACK_SENSOR_DECAY}", stateStyle.barColor, decayPct);
            return solidBar(stateStyle.barColor);
          `,
        ),
      },
    };
  }

  // Escape curly braces inside serialized JSON string literals so Jinja2 never
  // interprets user-supplied entity or area names containing braces as tags.
  function escapeJsonStringLiteralForJinja(value) {
    return JSON.stringify(value)
      .replaceAll("{", "\\u007b")
      .replaceAll("}", "\\u007d");
  }

  function buildSensorAutoEntitiesTemplate(evidenceEntityId, cardJson) {
    const evidenceLiteral = escapeJsonStringLiteralForJinja(evidenceEntityId);
    const cardJsonLiteral = escapeJsonStringLiteralForJinja(cardJson);
    return [
      `{% set details = state_attr(${evidenceLiteral}, '${ENTITY_ATTR.DETAILS}') or [] %}`,
      "{% set ns = namespace(items=[]) %}",
      "{% for detail in details if detail.id is defined %}",
      "{% set ns.items = ns.items + [{'id': detail.id, 'name': (detail.name or detail.id)|lower}] %}",
      "{% endfor %}",
      `[{% for item in ns.items|sort(attribute='name') %}{{ ${cardJsonLiteral} | replace('${ENTITY_PLACEHOLDER}', item.id) }}{% if not loop.last %},{% endif %}{% endfor %}]`,
    ].join("");
  }

  // --- Card builders ---

  function buildStatusCardShell(
    meta,
    primaryEntity,
    triggerEntities,
    templates,
    { navigationPath, gridOptions, isAggregate = false, topMargin } = {},
  ) {
    return {
      type: CARD_TYPE.BUTTON,
      entity: primaryEntity,
      triggers_update: triggerEntities.filter(Boolean),
      name: meta.name,
      icon: meta.icon,
      tap_action: navigationPath
        ? { action: CARD_ACTION.NAVIGATE, navigation_path: navigationPath }
        : { action: CARD_ACTION.MORE_INFO },
      ...(gridOptions ? { grid_options: gridOptions } : {}),
      custom_fields: {
        headline: templates.headline,
        status: templates.reading,
        bar: templates.bar,
        counts: templates.counts,
      },
      styles: buildStatusCardStyles(
        templates.cardBorder,
        templates.stateColor,
        {
          isAggregate,
          accentBorder: templates.accentBorder,
          topMargin,
        },
      ),
    };
  }

  function areaStatusCard(
    area,
    entities,
    { dashboardPath, gridOptions, templateCtx } = {},
  ) {
    const status = findEntity(entities, ENTITY_SPEC.STATUS);
    const probability = findEntity(entities, ENTITY_SPEC.PROBABILITY);
    const threshold = findEntity(entities, ENTITY_SPEC.THRESHOLD);
    const activity = findEntity(entities, ENTITY_SPEC.ACTIVITY);
    const prior = findEntity(entities, ENTITY_SPEC.PRIOR);
    if (!status && !probability) return undefined;

    const prelude = areaStatePrelude(
      JSON.stringify(status || ""),
      JSON.stringify(probability || ""),
      JSON.stringify(threshold || ""),
      JSON.stringify(prior || ""),
      templateCtx.areaModeStylesJson,
    );
    const templates = buildAreaStatusTemplates(
      prelude,
      JSON.stringify(activity || ""),
      templateCtx,
    );
    const navigationPath = dashboardPath
      ? `/${dashboardPath}/${areaViewPath(area)}`
      : undefined;

    return buildStatusCardShell(
      area,
      probability || status,
      [status, probability, threshold, activity, prior],
      templates,
      { navigationPath, gridOptions },
    );
  }

  function resolveFloorEntities(group, aggregateById, entitiesByDevice) {
    if (!group.floorId) return [];
    const floorDevice = aggregateById.get(
      `${DEVICE_ID.FLOOR_PREFIX}${group.floorId}`,
    );
    return floorDevice ? entitiesByDevice.get(floorDevice.id) || [] : [];
  }

  function floorStatusCard(
    group,
    floorEntities,
    { gridOptions, navigationPath, topMargin, templateCtx } = {},
  ) {
    const status = findEntity(floorEntities, ENTITY_SPEC.STATUS);
    const probability = findEntity(floorEntities, ENTITY_SPEC.PROBABILITY);
    const prior = findEntity(floorEntities, ENTITY_SPEC.PRIOR);
    if (!status && !probability) return undefined;

    const floorMeta = {
      name: group.label,
      area_id: group.floorId || group.label,
      icon: group.icon,
    };
    const memberStatuses = group.areas
      .map(({ entities }) => findEntity(entities, ENTITY_SPEC.STATUS))
      .filter(Boolean);
    const templates = buildAggregateStatusTemplates(
      JSON.stringify(status || ""),
      JSON.stringify(probability || ""),
      JSON.stringify(prior || ""),
      JSON.stringify(memberStatuses),
      templateCtx,
    );

    return buildStatusCardShell(
      floorMeta,
      probability || status,
      [status, probability, prior, ...memberStatuses],
      templates,
      { navigationPath, gridOptions, isAggregate: true, topMargin },
    );
  }

  function sensorDecayCard(area, entities, templateCtx, t) {
    const evidence = findEntity(entities, ENTITY_SPEC.EVIDENCE);
    if (!evidence) return undefined;

    const probability = findEntity(entities, ENTITY_SPEC.PROBABILITY);
    const cardJson = JSON.stringify(
      buildSensorItemCard(area, probability, templateCtx),
    );
    const template = buildSensorAutoEntitiesTemplate(evidence, cardJson);

    return headingSection(
      t(I18N_KEY.SENSORS_AND_DECAY_HEADING),
      ICON.SENSORS,
      SENSOR_GRID_BREAKPOINTS.map(({ columns, mediaQuery }) => ({
        type: CARD_TYPE.AUTO_ENTITIES,
        grid_options: FULL_WIDTH_GRID,
        visibility: [
          {
            condition: AUTO_ENTITIES_CONFIG.VISIBILITY_CONDITION,
            media_query: mediaQuery,
          },
        ],
        card: { type: LAYOUT_TYPE.GRID, columns, square: false },
        card_param: AUTO_ENTITIES_CONFIG.CARD_PARAM,
        filter: { template },
      })),
    );
  }

  function probabilityHistoryCard(cardTitle, probability, threshold) {
    if (!probability) return undefined;
    return {
      type: CARD_TYPE.PROBABILITY,
      title: cardTitle,
      probability_entity: probability,
      ...(threshold ? { threshold_entity: threshold } : {}),
      grid_options: FULL_WIDTH_GRID,
    };
  }

  function historyGraphCard(graphTitle, entities, { gridOptions } = {}) {
    if (!entities.length) return undefined;
    return {
      type: CARD_TYPE.HISTORY_GRAPH,
      title: graphTitle,
      hours_to_show: DEFAULTS.HISTORY_HOURS,
      entities,
      ...(gridOptions ? { grid_options: gridOptions } : {}),
    };
  }

  function timePriorsCard(cardTitle, { areaId, threshold } = {}) {
    return {
      type: CARD_TYPE.TIME_PRIORS,
      title: cardTitle,
      ...(areaId ? { area_id: areaId } : {}),
      threshold,
      grid_options: FULL_WIDTH_GRID,
    };
  }

  // --- View builders ---

  function buildOrderedAreaCards(areas, dashboardPath, templateCtx) {
    return orderByAdjacency(areas)
      .map(({ area, entities }) =>
        areaStatusCard(area, entities, {
          dashboardPath,
          templateCtx,
        }),
      )
      .filter(Boolean);
  }

  function areaView({ area, entities, threshold }, t, templateCtx) {
    const probability = findEntity(entities, ENTITY_SPEC.PROBABILITY);
    const thresholdEntity = findEntity(entities, ENTITY_SPEC.THRESHOLD);

    const viewSections = [
      singleCardSection(
        areaStatusCard(area, entities, {
          gridOptions: FULL_WIDTH_GRID,
          templateCtx,
        }),
      ),
      sensorDecayCard(area, entities, templateCtx, t),
      singleCardSection(
        probabilityHistoryCard(
          t(I18N_KEY.PROBABILITY_HISTORY_TITLE),
          probability,
          thresholdEntity,
        ),
      ),
      singleCardSection(
        timePriorsCard(
          t(I18N_KEY.AREA_WEEKLY_FORECAST_TITLE, { area: area.name }),
          {
            areaId: area.area_id,
            threshold: threshold ?? DEFAULTS.THRESHOLD,
          },
        ),
      ),
    ].filter(Boolean);

    return sectionsView({
      title: area.name,
      path: areaViewPath(area),
      icon: area.icon,
      subview: true,
      sections: viewSections,
    });
  }

  function floorView(group, floorEntities, dashboardPath, t, templateCtx) {
    const probability = findEntity(floorEntities, ENTITY_SPEC.PROBABILITY);
    const memberProbabilities = [
      ...(probability ? [{ entity: probability, name: group.label }] : []),
      ...group.areas.flatMap(({ area, entities }) => {
        const entity = findEntity(entities, ENTITY_SPEC.PROBABILITY);
        return entity ? [{ entity, name: area.name }] : [];
      }),
    ];

    const viewSections = [
      singleCardSection(
        floorStatusCard(group, floorEntities, {
          gridOptions: FULL_WIDTH_GRID,
          templateCtx,
        }),
      ),
      headingSection(
        t(I18N_KEY.AREAS_HEADING),
        ICON.AREAS_GROUP,
        buildOrderedAreaCards(group.areas, dashboardPath, templateCtx),
      ),
      singleCardSection(
        probabilityHistoryCard(
          t(I18N_KEY.FLOOR_PROBABILITY_HISTORY_TITLE, { floor: group.label }),
          probability,
        ),
      ),
      singleCardSection(
        historyGraphCard(
          t(I18N_KEY.FLOOR_AREA_PROBABILITIES_TITLE, {
            floor: group.label,
            hours: DEFAULTS.HISTORY_HOURS,
          }),
          memberProbabilities,
          { gridOptions: FULL_WIDTH_GRID },
        ),
      ),
    ].filter(Boolean);

    return sectionsView({
      title: group.label,
      path: floorViewPath(group),
      icon: group.icon,
      subview: true,
      sections: viewSections,
    });
  }

  // --- Strategy helpers ---

  function resolveAreaThreshold(entities, hass) {
    const id = findEntity(entities, ENTITY_SPEC.THRESHOLD);
    return id
      ? parseFiniteNumber(hass.states[id]?.state, undefined)
      : undefined;
  }

  function computeAverageThreshold(configured) {
    const values = configured
      .map(({ threshold }) => threshold)
      .filter((value) => value !== undefined);
    return values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : DEFAULTS.THRESHOLD;
  }

  async function fetchRawRegistries(hass) {
    const [areas, floors, devices, registry] = await Promise.all([
      hass.callWS({ type: WS_TYPE.AREA_REGISTRY }),
      hass.callWS({ type: WS_TYPE.FLOOR_REGISTRY }),
      hass.callWS({ type: WS_TYPE.DEVICE_REGISTRY }),
      hass.callWS({ type: WS_TYPE.ENTITY_REGISTRY }),
    ]);
    return { areas, floors, devices, registry };
  }

  function indexRegistries({ areas, floors, devices, registry }) {
    const areasById = new Map(areas.map((area) => [area.area_id, area]));
    const integrationDevices = devices.filter(isDomainDevice);
    return {
      areasById,
      areasByName: new Map(areas.map((area) => [area.name, area])),
      floorsById: new Map(floors.map((floor) => [floor.floor_id, floor])),
      entitiesByDevice: indexEntitiesByDevice(registry),
      aggregateDevices: integrationDevices.filter((device) =>
        isAggregateDevice(device, areasById),
      ),
      areaDevices: integrationDevices.filter(
        (device) => !isAggregateDevice(device, areasById),
      ),
    };
  }

  function resolveConfiguredAreas(
    areaDevices,
    areasById,
    areasByName,
    entitiesByDevice,
    hass,
  ) {
    return areaDevices
      .map((device) => {
        const id = domainIdentifiers(device)[0];
        const rawArea = areasById.get(id) || areasByName.get(device.name);
        const entities = entitiesByDevice.get(device.id) || [];
        const probability = findEntity(entities, ENTITY_SPEC.PROBABILITY);
        const adjacentAreas = probability
          ? hass.states[probability]?.attributes?.[ENTITY_ATTR.ADJACENT_AREAS] ||
            []
          : [];
        return {
          id,
          deviceId: device.id,
          area: {
            ...rawArea,
            area_id: rawArea?.area_id || id,
            name: rawArea?.name || device.name || title(id),
            icon: rawArea?.icon || ICON.AREA,
            floor_id: rawArea?.floor_id || null,
          },
          entities,
          adjacentAreas,
          threshold: resolveAreaThreshold(entities, hass),
        };
      })
      .filter((item) => item.entities.length > 0);
  }

  function compareFloorGroups(left, right, floorsById) {
    if (left.floorId && !right.floorId) return -1;
    if (!left.floorId && right.floorId) return 1;
    const leftLevel = floorsById.get(left.floorId)?.level;
    const rightLevel = floorsById.get(right.floorId)?.level;
    const leftHasLevel = leftLevel != null;
    const rightHasLevel = rightLevel != null;
    if (leftHasLevel !== rightHasLevel) return leftHasLevel ? -1 : 1;
    if (leftHasLevel && rightHasLevel && leftLevel !== rightLevel) {
      return leftLevel - rightLevel;
    }
    return left.label.localeCompare(right.label);
  }

  function resolveFloorIcon(floor) {
    if (floor?.icon) return floor.icon;
    if (floor?.level != null && FLOOR_LEVEL_ICONS[floor.level]) {
      return FLOOR_LEVEL_ICONS[floor.level];
    }
    return ICON.FLOOR;
  }

  function groupAndSortByFloor(configured, floorsById, t) {
    const groups = new Map();
    const unassignedLabel = t(I18N_KEY.AREAS_HEADING);
    for (const item of configured) {
      const floorId = item.area.floor_id;
      const floor = floorId ? floorsById.get(floorId) : null;
      const key = floorId
        ? `${FLOOR_GROUP_KEY_PREFIX}${floorId}`
        : DEFAULTS.UNASSIGNED_FLOOR_KEY;
      const label = floorId ? floor?.name || title(floorId) : unassignedLabel;
      if (!groups.has(key)) {
        groups.set(key, {
          label,
          floorId,
          icon: resolveFloorIcon(floor),
          areas: [],
        });
      }
      groups.get(key).areas.push(item);
    }

    return [...groups.values()].sort((left, right) =>
      compareFloorGroups(left, right, floorsById),
    );
  }

  function buildStatusSections(
    sortedGroups,
    aggregateById,
    entitiesByDevice,
    dashboardPath,
    templateCtx,
  ) {
    return sortedGroups
      .map((group, index) => {
        const navigationPath = group.floorId
          ? `/${dashboardPath}/${floorViewPath(group)}`
          : undefined;
        const floorEntities = resolveFloorEntities(
          group,
          aggregateById,
          entitiesByDevice,
        );
        const floorCard = floorStatusCard(group, floorEntities, {
          gridOptions: FULL_WIDTH_GRID,
          navigationPath,
          topMargin: index > 0 ? CARD_STYLE.FLOOR_SECTION_GAP : undefined,
          templateCtx,
        });
        const areaCards = buildOrderedAreaCards(
          group.areas,
          dashboardPath,
          templateCtx,
        );
        if (floorCard) {
          return gridSection([floorCard, ...areaCards], DEFAULTS.VIEW_COLUMNS);
        }
        return headingSection(group.label, group.icon, areaCards);
      })
      .filter(Boolean);
  }

  function markdownCard(cardTitle, content) {
    if (!content) return undefined;
    return {
      type: CARD_TYPE.MARKDOWN,
      title: cardTitle,
      content,
      grid_options: FULL_WIDTH_GRID,
    };
  }

  function formatRegistryEntityName(entity, entityResources = {}) {
    if (entity.name) return entity.name;
    const domain = entityDomain(entity.entity_id);
    if (domain && entity.translation_key) {
      const key = `${ENTITY_TRANSLATION_PREFIX}${domain}.${entity.translation_key}.name`;
      if (typeof entityResources?.[key] === "string" && entityResources[key]) {
        return entityResources[key];
      }
    }
    return (
      entity.original_name ||
      (entity.translation_key
        ? title(entity.translation_key)
        : entity.entity_id)
    );
  }

  function escapeMarkdownLinkText(text) {
    return String(text ?? "").replace(/[\\[\]]/g, "\\$&");
  }

  function deviceMarkdownLink(name, deviceId) {
    const safeName = escapeMarkdownLinkText(name);
    return deviceId
      ? `[${safeName}](${ROUTE.DEVICE_PREFIX}${deviceId})`
      : `**${safeName}**`;
  }

  function collectDiagnosticTargets(
    configured,
    aggregateDevices,
    entitiesByDevice,
  ) {
    const areaTargets = configured
      .map(({ area, deviceId, entities }) => ({
        name: area.name,
        deviceId,
        entities,
      }))
      .sort((left, right) => left.name.localeCompare(right.name));
    const aggregateTargets = aggregateDevices
      .map((device) => ({
        name: device.name || title(domainIdentifiers(device)[0]),
        deviceId: device.id,
        entities: entitiesByDevice.get(device.id) || [],
      }))
      .filter((target) => target.entities.length > 0)
      .sort((left, right) => left.name.localeCompare(right.name));
    return [...areaTargets, ...aggregateTargets];
  }

  function collectTargetEntityIssues(targets, selectEntities) {
    return targets
      .map((target) => ({
        name: target.name,
        deviceId: target.deviceId,
        entities: selectEntities(target),
      }))
      .filter((item) => item.entities.length > 0);
  }

  function findDisabledDiagnosticIssues(targets) {
    return collectTargetEntityIssues(targets, (target) =>
      target.entities.filter(
        (entity) =>
          entity.entity_category === ENTITY_CATEGORY.DIAGNOSTIC &&
          Boolean(entity.disabled_by),
      ),
    );
  }

  function findDisabledCoreIssues(targets) {
    return collectTargetEntityIssues(targets, (target) =>
      target.entities.filter(
        (entity) =>
          entity.entity_category !== ENTITY_CATEGORY.DIAGNOSTIC &&
          Boolean(entity.disabled_by) &&
          CORE_ENTITY_SPECS.some((spec) => matchesEntitySpec(entity, spec)),
      ),
    );
  }

  function findUnavailableCoreIssues(targets, hass, entityResources) {
    return collectTargetEntityIssues(targets, (target) =>
      target.entities
        .filter(
          (entity) =>
            !entity.disabled_by &&
            CORE_ENTITY_SPECS.some((spec) => matchesEntitySpec(entity, spec)),
        )
        .map((entity) => ({
          label: formatRegistryEntityName(entity, entityResources),
          state: hass?.states?.[entity.entity_id]?.state ?? ENTITY_STATE.MISSING,
        }))
        .filter(
          (entry) =>
            entry.state === ENTITY_STATE.MISSING ||
            UNAVAILABLE_STATES.includes(entry.state),
        ),
    );
  }

  function findSensorHealthIssues(configured, hass) {
    return configured
      .map(({ area, deviceId, entities }) => {
        const healthId = findEntity(entities, ENTITY_SPEC.SENSOR_HEALTH);
        if (!healthId) return null;
        const healthState = hass?.states?.[healthId];
        const count = parseFiniteNumber(healthState?.state, 0);
        if (count <= 0) return null;
        const issues = healthState?.attributes?.[ENTITY_ATTR.ISSUES];
        return {
          name: area.name,
          deviceId,
          count,
          issues: Array.isArray(issues) ? issues : [],
        };
      })
      .filter(Boolean)
      .sort((left, right) => left.name.localeCompare(right.name));
  }

  function collectDashboardIssues(
    configured,
    aggregateDevices,
    entitiesByDevice,
    hass,
    entityResources,
  ) {
    const targets = collectDiagnosticTargets(
      configured,
      aggregateDevices,
      entitiesByDevice,
    );
    const noAreas = configured.length === 0;
    const disabledDiagnostics = findDisabledDiagnosticIssues(targets);
    const disabledCore = findDisabledCoreIssues(targets);
    const unavailableCore = findUnavailableCoreIssues(
      targets,
      hass,
      entityResources,
    );
    const sensorHealth = findSensorHealthIssues(configured, hass);

    return {
      noAreas,
      disabledDiagnostics,
      disabledCore,
      unavailableCore,
      sensorHealth,
      hasIssues:
        noAreas ||
        disabledDiagnostics.length > 0 ||
        disabledCore.length > 0 ||
        unavailableCore.length > 0 ||
        sensorHealth.length > 0,
    };
  }

  function buildNoAreasCard(t) {
    return markdownCard(
      t(I18N_KEY.NO_AREAS_TITLE),
      [
        t(I18N_KEY.NO_AREAS_BODY),
        "",
        t(I18N_KEY.NO_AREAS_CTA, { url: ROUTE.INTEGRATION }),
      ].join("\n"),
    );
  }

  function formatDisabledDiagnosticsSummary(totalEntities, deviceCount, t) {
    if (totalEntities === 1 && deviceCount === 1) {
      return t(I18N_KEY.DISABLED_DIAGNOSTICS_ONE_ONE);
    }
    if (deviceCount === 1) {
      return t(I18N_KEY.DISABLED_DIAGNOSTICS_MANY_ONE, {
        entity_count: totalEntities,
      });
    }
    return t(I18N_KEY.DISABLED_DIAGNOSTICS_MANY_MANY, {
      entity_count: totalEntities,
      device_count: deviceCount,
    });
  }

  function collectDisabledDiagnosticNotes(disabledDiagnostics, t) {
    const hasDisabledSpec = (spec) =>
      disabledDiagnostics.some((item) =>
        item.entities.some((entity) => matchesEntitySpec(entity, spec)),
      );
    return [
      hasDisabledSpec(ENTITY_SPEC.EVIDENCE)
        ? t(I18N_KEY.DISABLED_DIAGNOSTICS_EVIDENCE_NOTE)
        : null,
      hasDisabledSpec(ENTITY_SPEC.PRIOR)
        ? t(I18N_KEY.DISABLED_DIAGNOSTICS_PRIOR_NOTE)
        : null,
    ].filter(Boolean);
  }

  function buildDisabledDiagnosticsCard(
    disabledDiagnostics,
    t,
    entityResources,
  ) {
    if (!disabledDiagnostics.length) return undefined;
    const totalEntities = disabledDiagnostics.reduce(
      (sum, item) => sum + item.entities.length,
      0,
    );
    const summary = formatDisabledDiagnosticsSummary(
      totalEntities,
      disabledDiagnostics.length,
      t,
    );
    const impactNotes = collectDisabledDiagnosticNotes(disabledDiagnostics, t);
    const rows = formatEntityIssueRows(disabledDiagnostics, entityResources);

    return markdownCard(
      t(I18N_KEY.DISABLED_DIAGNOSTICS_TITLE),
      [
        summary,
        ...(impactNotes.length ? ["", ...impactNotes] : []),
        "",
        t(I18N_KEY.DISABLED_DIAGNOSTICS_CTA, { url: ROUTE.ENTITIES }),
        "",
        ...rows,
      ].join("\n"),
    );
  }

  function formatEntityIssueRows(items, entityResources) {
    return items.map((item) => {
      const names = item.entities
        .map((entity) => formatRegistryEntityName(entity, entityResources))
        .sort((left, right) => left.localeCompare(right))
        .join(", ");
      return `- ${deviceMarkdownLink(item.name, item.deviceId)}: ${names}`;
    });
  }

  function buildDisabledCoreCard(disabledCore, t, entityResources) {
    if (!disabledCore.length) return undefined;
    const rows = formatEntityIssueRows(disabledCore, entityResources);
    return markdownCard(
      t(I18N_KEY.DISABLED_CORE_TITLE),
      [t(I18N_KEY.DISABLED_CORE_BODY), "", ...rows].join("\n"),
    );
  }

  function buildUnavailableCoreCard(unavailableCore, t) {
    if (!unavailableCore.length) return undefined;
    const rows = unavailableCore.map((item) => {
      const names = [...item.entities]
        .sort((left, right) => left.label.localeCompare(right.label))
        .map((entry) => `${entry.label} (\`${entry.state}\`)`)
        .join(", ");
      return `- ${deviceMarkdownLink(item.name, item.deviceId)}: ${names}`;
    });
    return markdownCard(
      t(I18N_KEY.UNAVAILABLE_TITLE),
      [t(I18N_KEY.UNAVAILABLE_BODY), "", ...rows].join("\n"),
    );
  }

  function buildSensorHealthCard(sensorHealth, t) {
    if (!sensorHealth.length) return undefined;
    const fallbackType = t(I18N_KEY.SENSOR_HEALTH_ISSUE_FALLBACK);
    const rows = sensorHealth.map((item) => {
      const link = deviceMarkdownLink(item.name, item.deviceId);
      if (!item.issues.length) {
        const countKey =
          item.count === 1
            ? I18N_KEY.SENSOR_HEALTH_COUNT_ONE
            : I18N_KEY.SENSOR_HEALTH_COUNT_OTHER;
        return `- ${link}: ${t(countKey, { count: item.count })}`;
      }
      const details = item.issues
        .map((issue) => {
          const label = title(issue.type || fallbackType);
          return issue.entity_id ? `\`${issue.entity_id}\` (${label})` : label;
        })
        .join(", ");
      return `- ${link}: ${details}`;
    });
    return markdownCard(
      t(I18N_KEY.SENSOR_HEALTH_TITLE),
      [t(I18N_KEY.SENSOR_HEALTH_BODY), "", ...rows].join("\n"),
    );
  }

  function buildInfoSections(issues, t, entityResources) {
    return sections(
      [
        issues.noAreas ? buildNoAreasCard(t) : undefined,
        buildDisabledDiagnosticsCard(
          issues.disabledDiagnostics,
          t,
          entityResources,
        ),
        buildDisabledCoreCard(issues.disabledCore, t, entityResources),
        buildUnavailableCoreCard(issues.unavailableCore, t),
        buildSensorHealthCard(issues.sensorHealth, t),
      ],
      DEFAULTS.VIEW_COLUMNS,
    );
  }

  function buildFloorViews(
    sortedGroups,
    aggregateById,
    entitiesByDevice,
    dashboardPath,
    t,
    templateCtx,
  ) {
    return sortedGroups
      .filter((group) => group.floorId)
      .map((group) => {
        const floorEntities = resolveFloorEntities(
          group,
          aggregateById,
          entitiesByDevice,
        );
        return floorView(
          group,
          floorEntities,
          dashboardPath,
          t,
          templateCtx,
        );
      });
  }

  // --- Dashboard strategy ---

  async function loadDashboardContext(hass) {
    const [rawRegistries, commonResources, entityResources] = await Promise.all([
      fetchRawRegistries(hass),
      fetchTranslationsWithFallback(hass, TRANSLATION_CATEGORY.COMMON),
      fetchTranslationsWithFallback(hass, TRANSLATION_CATEGORY.ENTITY),
    ]);
    const t = createTranslator(hass, commonResources);
    const {
      areasById,
      areasByName,
      floorsById,
      entitiesByDevice,
      aggregateDevices,
      areaDevices,
    } = indexRegistries(rawRegistries);

    const configured = resolveConfiguredAreas(
      areaDevices,
      areasById,
      areasByName,
      entitiesByDevice,
      hass,
    );
    return {
      t,
      entityResources,
      templateCtx: buildTemplateContext(t, entityResources),
      entitiesByDevice,
      configured,
      sortedGroups: groupAndSortByFloor(configured, floorsById, t),
      aggregateById: indexDevicesByIdentifier(aggregateDevices),
      comfortThreshold: computeAverageThreshold(configured),
      issues: collectDashboardIssues(
        configured,
        aggregateDevices,
        entitiesByDevice,
        hass,
        entityResources,
      ),
    };
  }

  function buildDashboardViews(context, dashboardPath) {
    const {
      t,
      entityResources,
      templateCtx,
      entitiesByDevice,
      configured,
      sortedGroups,
      aggregateById,
      comfortThreshold,
      issues,
    } = context;
    return [
      sectionsView({
        title: t(VIEW_CONFIG.STATUS.titleKey),
        path: VIEW_CONFIG.STATUS.path,
        icon: VIEW_CONFIG.STATUS.icon,
        sections: buildStatusSections(
          sortedGroups,
          aggregateById,
          entitiesByDevice,
          dashboardPath,
          templateCtx,
        ),
      }),
      sectionsView({
        title: t(VIEW_CONFIG.FORECAST.titleKey),
        path: VIEW_CONFIG.FORECAST.path,
        icon: VIEW_CONFIG.FORECAST.icon,
        maxColumns: DEFAULTS.MAX_COLUMNS,
        sections: sections([
          timePriorsCard(t(I18N_KEY.WEEKLY_FORECAST_TITLE), {
            threshold: comfortThreshold,
          }),
        ]),
      }),
      ...(issues.hasIssues
        ? [
            sectionsView({
              title: t(VIEW_CONFIG.INFO.titleKey),
              path: VIEW_CONFIG.INFO.path,
              icon: VIEW_CONFIG.INFO.icon,
              sections: buildInfoSections(issues, t, entityResources),
            }),
          ]
        : []),
      ...buildFloorViews(
        sortedGroups,
        aggregateById,
        entitiesByDevice,
        dashboardPath,
        t,
        templateCtx,
      ),
      ...configured.map((item) => areaView(item, t, templateCtx)),
    ];
  }

  class AreaOccupancyDashboardStrategy extends HTMLElement {
    static getCreateSuggestions() {
      return { title: BRAND_NAME, icon: ICON.STATUS };
    }

    static async generate(config, hass) {
      const dashboardPath = resolveDashboardPath();
      const context = await loadDashboardContext(hass);
      return {
        title: config.title || context.t(I18N_KEY.DASHBOARD_TITLE) || BRAND_NAME,
        views: buildDashboardViews(context, dashboardPath),
      };
    }
  }

  // --- Probability chart pure helpers ---

  function valueToSvgY(value) {
    return (
      CHART_LAYOUT.PAD_TOP +
      (1 - clamp(value, 0, PERCENT_SCALE) / PERCENT_SCALE) * CHART_PLOT_HEIGHT
    );
  }

  function svgYToPercent(svgY) {
    const relativeY = clamp(svgY - CHART_LAYOUT.PAD_TOP, 0, CHART_PLOT_HEIGHT);
    return Math.round((1 - relativeY / CHART_PLOT_HEIGHT) * PERCENT_SCALE);
  }

  function thresholdSvgCoords(value) {
    const y = valueToSvgY(value);
    return {
      lineY: fmtCoord(y),
      pillY: fmtCoord(y - CHART_LAYOUT.PILL_OFFSET_Y),
      textY: fmtCoord(y + CHART_LAYOUT.PILL_TEXT_OFFSET_Y),
      label: `${Math.round(value)}%`,
    };
  }

  function resolveRangeWindow(rangeId, now) {
    const range =
      PROBABILITY_CHART_RANGE_BY_ID.get(rangeId) ||
      PROBABILITY_CHART_RANGE_BY_ID.get(DEFAULTS.FALLBACK_RANGE_ID);
    if (range.sinceMidnight) {
      const midnight = new Date(now);
      midnight.setHours(0, 0, 0, 0);
      return {
        startMs: Math.min(
          midnight.getTime(),
          now - DEFAULTS.HISTORY_REFRESH_MS,
        ),
        isMultiDay: false,
      };
    }
    const hours = range.hours ?? DEFAULTS.HISTORY_HOURS;
    return {
      startMs: now - hours * TIME_MS.HOUR,
      isMultiDay: hours > DEFAULTS.HISTORY_HOURS,
    };
  }

  function parseHistoryPoints(raw) {
    return (raw || [])
      .map((pt) => {
        const ts = pt.lu ?? pt.lc;
        return {
          t: ts == null ? NaN : Number(ts) * TIME_MS.SECOND,
          v: parseFiniteNumber(pt.s),
        };
      })
      .filter((pt) => Number.isFinite(pt.t) && pt.v !== null);
  }

  function clipPointsToWindow(points, startMs) {
    if (!points.length) return [];
    let anchor = null;
    const inWindow = [];
    for (const pt of points) {
      if (pt.t <= startMs) {
        if (!anchor || pt.t >= anchor.t) {
          anchor = pt;
        }
      } else {
        inWindow.push(pt);
      }
    }
    return anchor ? [{ t: startMs, v: anchor.v }, ...inWindow] : inWindow;
  }

  function extendSeriesToNow(points, currentValue, now) {
    if (!points.length) {
      return currentValue !== null ? [{ t: now, v: currentValue }] : [];
    }
    return currentValue !== null
      ? [...points, { t: now, v: currentValue }]
      : points;
  }

  function pointsToSvgCoords(points, xOf) {
    return points.map((pt) => [
      fmtCoord(xOf(pt.t)),
      fmtCoord(valueToSvgY(pt.v)),
    ]);
  }

  function buildLinearPaths(points, xOf, baseY) {
    if (points.length < 2) return { linePath: "", areaPath: "" };
    const coords = pointsToSvgCoords(points, xOf);
    const linePath = coords
      .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x},${y}`)
      .join(" ");
    const firstX = coords[0][0];
    const lastX = coords[coords.length - 1][0];
    return {
      linePath,
      areaPath: `${linePath} L${lastX},${baseY} L${firstX},${baseY} Z`,
    };
  }

  function buildStepPath(points, xOf) {
    if (points.length < 2) return "";
    const coords = pointsToSvgCoords(points, xOf);
    return coords
      .map(([x, y], index) => {
        if (index === 0) return `M${x},${y}`;
        const prevY = coords[index - 1][1];
        return `L${x},${prevY} L${x},${y}`;
      })
      .join(" ");
  }

  function formatAxisTickLabel(
    timestampMs,
    isMultiDay,
    isEnd,
    { nowLabel = "", locale = [] } = {},
  ) {
    if (isEnd) return nowLabel;
    const dt = new Date(timestampMs);
    const intlLocale = locale || [];
    return isMultiDay
      ? dt.toLocaleDateString(intlLocale, { month: "short", day: "numeric" })
      : dt.toLocaleTimeString(intlLocale, {
          hour: "numeric",
          minute: "2-digit",
        });
  }

  function buildHistoryUrl(entityIds, startMs, endMs) {
    const ids = entityIds.filter(Boolean);
    if (!ids.length) return "";
    const params = new URLSearchParams({
      [HISTORY_QUERY_PARAM.ENTITY_ID]: ids.join(","),
    });
    if (Number.isFinite(startMs)) {
      params.set(
        HISTORY_QUERY_PARAM.START_DATE,
        new Date(startMs).toISOString(),
      );
    }
    if (Number.isFinite(endMs)) {
      params.set(HISTORY_QUERY_PARAM.END_DATE, new Date(endMs).toISOString());
    }
    params.set(HISTORY_QUERY_PARAM.BACK, HISTORY_QUERY_PARAM.BACK_ENABLED);
    return `${ROUTE.HISTORY}?${params.toString()}`;
  }

  function buildChartGeometry(
    now,
    { startMs, isMultiDay },
    hasThreshold,
    chartWidth = CHART_LAYOUT.WIDTH,
    { nowLabel = "", locale = [] } = {},
  ) {
    const width = Math.max(
      CHART_LAYOUT.MIN_WIDTH,
      chartWidth || CHART_LAYOUT.WIDTH,
    );
    const padL = CHART_LAYOUT.PAD_LEFT;
    const padR = hasThreshold
      ? CHART_LAYOUT.PAD_RIGHT_WITH_THRESHOLD
      : CHART_LAYOUT.PAD_RIGHT_NO_THRESHOLD;
    const plotRight = width - padR;
    const plotW = plotRight - padL;
    const baseY = fmtCoord(CHART_LAYOUT.PAD_TOP + CHART_PLOT_HEIGHT);
    const spanMs = Math.max(1, now - startMs);
    const xOf = (t) => padL + clamp((t - startMs) / spanMs, 0, 1) * plotW;
    const xFractions =
      width < CHART_LAYOUT.NARROW_WIDTH
        ? CHART_LAYOUT.X_FRACTIONS_NARROW
        : CHART_LAYOUT.X_FRACTIONS;

    const xTicks = xFractions.map((frac) => ({
      x: fmtCoord(padL + frac * plotW),
      label: formatAxisTickLabel(
        startMs + frac * spanMs,
        isMultiDay,
        frac === 1,
        { nowLabel, locale },
      ),
    }));

    return { width, padL, plotRight, baseY, xOf, xTicks };
  }

  const PROBABILITY_CARD_STYLES = `
    <style>
      ha-card { padding: 14px 16px 10px; border-radius: ${CARD_STYLE.RADIUS}; }
      .${CHART_CLASS.HEADER} { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
      .${CHART_CLASS.TITLE_GROUP} { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
      .${CHART_CLASS.TITLE} { font-size: 16px; font-weight: 600; color: ${COLOR.TEXT_PRIMARY}; }
      .${CHART_CLASS.RANGES_WRAP} { display: inline-flex; align-items: center; gap: 10px; }
      .${CHART_CLASS.RANGES} { display: inline-flex; gap: 4px; background: var(--secondary-background-color, rgba(${RGB.NEUTRAL},.12)); padding: 2px; border-radius: 8px; }
      .${CHART_CLASS.RANGE_BTN} { border: none; background: transparent; color: ${COLOR.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px; cursor: pointer; }
      .${CHART_CLASS.RANGE_BTN}:hover { color: ${COLOR.TEXT_PRIMARY}; }
      .${CHART_CLASS.RANGE_BTN}.${CHART_CLASS.ACTIVE} { background: var(--primary-color, ${COLOR.PROBABILITY}); color: var(--text-primary-color, #fff); }
      .${CHART_CLASS.META} { display: flex; align-items: center; gap: 12px; font-size: 12px; color: ${COLOR.TEXT_SECONDARY}; }
      .${CHART_CLASS.BADGE} { font-weight: 600; }
      .${CHART_CLASS.PROB} { color: ${COLOR.PROBABILITY}; }
      .${CHART_CLASS.TH} { color: ${COLOR.DECAYING}; }
      .${CHART_CLASS.HINT} { opacity: 0.7; }
      .${CHART_CLASS.HISTORY_LINK} { display: inline-flex; align-items: center; gap: 4px; color: var(--primary-color, ${COLOR.PROBABILITY}); text-decoration: none; font-weight: 500; white-space: nowrap; }
      .${CHART_CLASS.HISTORY_LINK}:hover { text-decoration: underline; }
      .${CHART_CLASS.HISTORY_LINK} ha-icon { --mdc-icon-size: 14px; }
      svg.${CHART_CLASS.CHART} { width: 100%; height: ${CHART_LAYOUT.HEIGHT}px; display: block; user-select: none; }
      .${CHART_CLASS.GRID} { stroke: ${DIVIDER_COLOR}; stroke-width: 1; }
      .${CHART_CLASS.TICK} { fill: ${COLOR.TEXT_SECONDARY}; font-size: 11px; }
      .${CHART_CLASS.AREA} { fill: ${COLOR.CHART_AREA}; }
      .${CHART_CLASS.LINE} { fill: none; stroke: ${COLOR.PROBABILITY}; stroke-width: 2; stroke-linejoin: round; }
      .${CHART_CLASS.TH_HISTORY} { fill: none; stroke: ${COLOR.CHART_TH_HISTORY}; stroke-width: 1.5; pointer-events: none; }
      .${CHART_CLASS.TH_LINE} { stroke: ${COLOR.DECAYING}; stroke-width: 2; stroke-dasharray: 6 4; pointer-events: none; }
      svg.${CHART_CLASS.CHART}.${CHART_CLASS.EDITABLE} .${CHART_CLASS.TH_HANDLE} { cursor: ns-resize; touch-action: none; }
      .${CHART_CLASS.TH_PILL} { fill: ${COLOR.DECAYING}; }
      .${CHART_CLASS.TH_TEXT} { fill: ${COLOR.CHART_PILL_TEXT}; font-size: 11px; font-weight: 700; pointer-events: none; }
    </style>
  `;

  // --- Probability history card ---

  class AreaOccupancyProbabilityCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._points = [];
      this._thresholdPoints = [];
      this._nextFetchAt = 0;
      this._fetchToken = 0;
      this._fetching = false;
      this._mounted = false;
      this._canEdit = false;
      this._dragging = false;
      this._dragStartY = 0;
      this._dragMoved = false;
      this._dragRect = null;
      this._draftThreshold = null;
      this._pendingThreshold = null;
      this._pendingUntil = 0;
      this._lastRenderKey = "";
      this._selectedRangeId = DEFAULTS.DEFAULT_RANGE_ID;
      this._chartWidth = CHART_LAYOUT.WIDTH;
      this._resizeObserver = null;
      this._translations = {};
      this._translationsLang = "";
      this._translationsPendingLang = "";
      this._translationsLoaded = false;
      this._translationsRetryLang = "";
      this._translationsRetries = 0;
      this._translationsNextRetryAt = 0;
    }

    getCardSize() {
      return DEFAULTS.PROBABILITY_CARD_SIZE;
    }

    connectedCallback() {
      this._startResizeObserver();
    }

    disconnectedCallback() {
      this._stopResizeObserver();
      this._cancelDrag();
      this._fetchToken += 1;
      this._fetching = false;
    }

    _startResizeObserver() {
      if (
        this._resizeObserver ||
        !this._svgEl ||
        typeof ResizeObserver === "undefined"
      ) {
        return;
      }
      this._resizeObserver = new ResizeObserver((entries) => {
        const measured = Math.round(entries[0]?.contentRect?.width || 0);
        if (measured <= 0) return;
        const nextWidth = Math.max(CHART_LAYOUT.MIN_WIDTH, measured);
        if (nextWidth !== this._chartWidth) {
          this._chartWidth = nextWidth;
          if (!this._dragging) {
            this._updateView();
          }
        }
      });
      this._resizeObserver.observe(this._svgEl);
    }

    _stopResizeObserver() {
      if (this._resizeObserver) {
        this._resizeObserver.disconnect();
        this._resizeObserver = null;
      }
    }

    _resolveCurrentRange(now) {
      return resolveRangeWindow(this._selectedRangeId, now);
    }

    _buildHistoryUrl(now) {
      const { startMs } = this._resolveCurrentRange(now);
      return buildHistoryUrl(
        [this._config?.probability_entity, this._config?.threshold_entity],
        startMs,
        now,
      );
    }

    setConfig(config) {
      if (!config) {
        throw new Error("Invalid configuration");
      }
      const prevConfig = this._config;
      const resolveDefaultRange = (rawRange) =>
        rawRange && PROBABILITY_CHART_RANGE_BY_ID.has(rawRange)
          ? rawRange
          : DEFAULTS.DEFAULT_RANGE_ID;
      const prevDefaultRange = prevConfig
        ? resolveDefaultRange(prevConfig.default_range)
        : null;
      const nextDefaultRange = resolveDefaultRange(config.default_range);
      const entitiesChanged =
        !prevConfig ||
        config.probability_entity !== prevConfig.probability_entity ||
        config.threshold_entity !== prevConfig.threshold_entity;
      const defaultRangeChanged =
        Boolean(prevConfig) && nextDefaultRange !== prevDefaultRange;

      this._config = config;
      if (!prevConfig || defaultRangeChanged) {
        this._selectedRangeId = nextDefaultRange;
      }

      if (entitiesChanged) {
        this._resetHistoryState();
      } else if (defaultRangeChanged) {
        this._nextFetchAt = 0;
      }

      this._ensureMounted();
      this._updateView({ force: true });
      if (this._hass) {
        this._loadTranslations(this._hass);
        if (
          defaultRangeChanged ||
          (!this._fetching && Date.now() >= this._nextFetchAt)
        ) {
          this._fetchHistory();
        }
      }
    }

    _t(key, placeholders) {
      return translateKey(this._hass, this._translations, key, placeholders);
    }

    _formatThresholdLabel(value) {
      return this._t(I18N_KEY.THRESHOLD_BADGE, { value: Math.round(value) });
    }

    async _loadTranslations(hass) {
      const lang = getHassLanguage(hass);
      if (
        (this._translationsLoaded && lang === this._translationsLang) ||
        lang === this._translationsPendingLang
      ) {
        return;
      }
      if (this._translationsRetryLang !== lang) {
        this._translationsRetryLang = lang;
        this._translationsRetries = 0;
        this._translationsNextRetryAt = 0;
      }
      if (
        this._translationsRetries >= DEFAULTS.TRANSLATION_MAX_RETRIES ||
        Date.now() < this._translationsNextRetryAt
      ) {
        return;
      }
      this._translationsPendingLang = lang;
      try {
        const resources =
          (await fetchTranslations(hass, TRANSLATION_CATEGORY.COMMON)) || {};
        if (getHassLanguage(this._hass) !== lang) return;
        if (Object.keys(resources).length > 0) {
          this._translations = resources;
          this._translationsLang = lang;
          this._translationsLoaded = true;
          this._translationsRetries = 0;
          this._translationsNextRetryAt = 0;
          this._updateView({ force: true });
        } else {
          this._translationsRetries += 1;
          this._translationsNextRetryAt =
            Date.now() + DEFAULTS.TRANSLATION_ERROR_BACKOFF_MS;
        }
      } catch {
        // Back off and cap retries so WS failures don't spin on state updates.
        if (this._translationsRetryLang === lang) {
          this._translationsRetries += 1;
          this._translationsNextRetryAt =
            Date.now() + DEFAULTS.TRANSLATION_ERROR_BACKOFF_MS;
        }
      } finally {
        if (this._translationsPendingLang === lang) {
          this._translationsPendingLang = "";
        }
      }
    }

    set hass(hass) {
      this._hass = hass;
      this._loadTranslations(hass);
      if (!this._config) return;

      const now = Date.now();
      this._syncLivePoints(now);

      if (!this._fetching && now >= this._nextFetchAt) {
        this._fetchHistory();
      }
      if (!this._dragging) {
        this._updateView({ now });
      }
    }

    _resetHistoryState() {
      this._points = [];
      this._thresholdPoints = [];
      this._nextFetchAt = 0;
      this._fetchToken += 1;
      this._fetching = false;
      this._pendingThreshold = null;
      this._pendingUntil = 0;
    }

    _clearResolvedPendingThreshold(currentThreshold, now) {
      if (
        this._pendingThreshold !== null &&
        (Math.round(currentThreshold) === Math.round(this._pendingThreshold) ||
          now > this._pendingUntil)
      ) {
        this._pendingThreshold = null;
      }
    }

    _appendLivePoint(points, value, now) {
      if (value === null) return;
      if (!points.length || points[points.length - 1].v !== value) {
        points.push({ t: now, v: value });
      }
    }

    _syncLivePoints(now) {
      if (!this._hass || !this._config) return;
      const probVal = parseFiniteNumber(
        this._hass.states?.[this._config.probability_entity]?.state,
      );
      this._appendLivePoint(this._points, probVal, now);

      const thVal = parseFiniteNumber(
        this._hass.states?.[this._config.threshold_entity]?.state,
      );
      if (thVal !== null) {
        this._clearResolvedPendingThreshold(thVal, now);
        this._appendLivePoint(this._thresholdPoints, thVal, now);
      }
    }

    async _fetchHistory() {
      const entityId = this._config?.probability_entity;
      const thresholdEntity = this._config?.threshold_entity;
      if (!this._hass || !entityId) return;

      const token = ++this._fetchToken;
      this._fetching = true;
      try {
        const now = Date.now();
        const { startMs } = this._resolveCurrentRange(now);
        const res = await this._hass.callWS({
          type: WS_TYPE.HISTORY_DURING_PERIOD,
          start_time: new Date(startMs).toISOString(),
          end_time: new Date(now).toISOString(),
          entity_ids: [entityId, thresholdEntity].filter(Boolean),
          minimal_response: true,
          significant_changes_only: false,
        });
        if (token !== this._fetchToken) return;
        const fetchedAt = Date.now();
        const freshStartMs = this._resolveCurrentRange(fetchedAt).startMs;
        const nextPoints = parseHistoryPoints(res?.[entityId]);
        const nextThresholdPoints = thresholdEntity
          ? parseHistoryPoints(res?.[thresholdEntity])
          : [];
        this._points =
          nextPoints.length > 0
            ? nextPoints
            : clipPointsToWindow(this._points, freshStartMs);
        this._thresholdPoints = !thresholdEntity
          ? []
          : nextThresholdPoints.length > 0
            ? nextThresholdPoints
            : clipPointsToWindow(this._thresholdPoints, freshStartMs);
        this._syncLivePoints(fetchedAt);
        this._nextFetchAt = fetchedAt + DEFAULTS.HISTORY_REFRESH_MS;
      } catch {
        if (token !== this._fetchToken) return;
        // Back off briefly on transient WS errors so rapid state updates don't spin retries.
        this._nextFetchAt = Date.now() + DEFAULTS.HISTORY_ERROR_BACKOFF_MS;
      } finally {
        if (token === this._fetchToken) {
          this._fetching = false;
          if (!this._dragging) {
            this._updateView({ force: true });
          }
        }
      }
    }

    _thresholdBounds() {
      const thState = this._hass?.states?.[this._config?.threshold_entity];
      return {
        min: parseFiniteNumber(
          thState?.attributes?.min,
          DEFAULTS.THRESHOLD_MIN,
        ),
        max: parseFiniteNumber(
          thState?.attributes?.max,
          DEFAULTS.THRESHOLD_MAX,
        ),
      };
    }

    _valueFromPointer(event, rect) {
      if (!rect || rect.height <= 0) return null;
      const svgY =
        ((event.clientY - rect.top) / rect.height) * CHART_LAYOUT.HEIGHT;
      const { min, max } = this._thresholdBounds();
      return clamp(svgYToPercent(svgY), min, max);
    }

    _commitThreshold(value) {
      const entityId = this._config?.threshold_entity;
      if (!this._hass || !entityId || !Number.isFinite(value)) return;
      Promise.resolve(
        this._hass.callService(ENTITY_DOMAIN.NUMBER, SERVICE.SET_VALUE, {
          entity_id: entityId,
          value,
        }),
      ).catch(() => {
        if (this._pendingThreshold === value) {
          this._pendingThreshold = null;
          this._pendingUntil = 0;
          this._updateView({ force: true });
        }
      });
    }

    _resolveRenderState(now) {
      const probState = this._hass?.states?.[this._config.probability_entity];
      const thState = this._hass?.states?.[this._config.threshold_entity];
      const currentProb = parseFiniteNumber(probState?.state);
      const currentThreshold = parseFiniteNumber(thState?.state);
      const hasThreshold = Boolean(this._config.threshold_entity);
      const savedThreshold = currentThreshold ?? DEFAULTS.THRESHOLD;
      const pendingActive =
        this._pendingThreshold !== null && now <= this._pendingUntil;
      const threshold =
        this._draftThreshold ??
        (pendingActive ? this._pendingThreshold : savedThreshold);

      return {
        currentProb,
        currentThreshold,
        hasThreshold,
        threshold,
        canEdit: Boolean(hasThreshold && thState),
      };
    }

    _ensureMounted() {
      if (this._mounted) return;
      this._mounted = true;

      const renderButtons = (separated) =>
        PROBABILITY_CHART_RANGES.filter(
          (r) => Boolean(r.separated) === separated,
        )
          .map(
            (r) =>
              `<button type="button" class="${CHART_CLASS.RANGE_BTN}" data-range="${r.id}">${escapeHtmlText(this._t(r.labelKey) || r.id)}</button>`,
          )
          .join("");

      this.shadowRoot.innerHTML = `
        ${PROBABILITY_CARD_STYLES}
        <ha-card>
          <div class="${CHART_CLASS.HEADER}">
            <div class="${CHART_CLASS.TITLE_GROUP}">
              <span class="${CHART_CLASS.TITLE}"></span>
              <div class="${CHART_CLASS.RANGES_WRAP}">
                <div class="${CHART_CLASS.RANGES}">${renderButtons(true)}</div>
                <div class="${CHART_CLASS.RANGES}">${renderButtons(false)}</div>
              </div>
            </div>
            <div class="${CHART_CLASS.META}"></div>
          </div>
          <svg class="${CHART_CLASS.CHART}" viewBox="0 0 ${CHART_LAYOUT.WIDTH} ${CHART_LAYOUT.HEIGHT}"></svg>
        </ha-card>
      `;

      this._titleEl = this.shadowRoot.querySelector(`.${CHART_CLASS.TITLE}`);
      this._metaEl = this.shadowRoot.querySelector(`.${CHART_CLASS.META}`);
      this._svgEl = this.shadowRoot.querySelector(`svg.${CHART_CLASS.CHART}`);
      this._rangeButtons = [
        ...this.shadowRoot.querySelectorAll(`.${CHART_CLASS.RANGE_BTN}`),
      ];

      this._bindRangeHandlers();
      this._bindHistoryLinkHandlers();
      this._bindDragHandlers();
      this._startResizeObserver();
    }

    _bindRangeHandlers() {
      this.shadowRoot
        .querySelector(`.${CHART_CLASS.RANGES_WRAP}`)
        .addEventListener("click", (event) => {
          const btn = event.target.closest(`.${CHART_CLASS.RANGE_BTN}`);
          const nextRangeId = btn?.dataset.range;
          if (
            !nextRangeId ||
            !PROBABILITY_CHART_RANGE_BY_ID.has(nextRangeId) ||
            nextRangeId === this._selectedRangeId
          ) {
            return;
          }
          this._selectedRangeId = nextRangeId;
          this._nextFetchAt = 0;
          this._updateView({ force: true });
          this._fetchHistory();
        });
    }

    _bindHistoryLinkHandlers() {
      const refreshHistoryLink = (event) => {
        const link = event.target.closest(`.${CHART_CLASS.HISTORY_LINK}`);
        if (!link) return;
        const freshUrl = this._buildHistoryUrl(Date.now());
        if (freshUrl) link.setAttribute("href", freshUrl);
      };
      this._metaEl.addEventListener("click", refreshHistoryLink);
      this._metaEl.addEventListener("auxclick", refreshHistoryLink);
    }

    _updateThresholdVisual(value) {
      const { lineY, pillY, textY, label } = thresholdSvgCoords(value);
      const thLine = this._svgEl?.querySelector(`.${CHART_CLASS.TH_LINE}`);
      const thPill = this._svgEl?.querySelector(`.${CHART_CLASS.TH_PILL}`);
      const thText = this._svgEl?.querySelector(`.${CHART_CLASS.TH_TEXT}`);
      const thBadge = this._metaEl?.querySelector(
        `.${CHART_CLASS.BADGE}.${CHART_CLASS.TH}`,
      );

      if (thLine) {
        thLine.setAttribute("y1", lineY);
        thLine.setAttribute("y2", lineY);
      }
      if (thPill) thPill.setAttribute("y", pillY);
      if (thText) {
        thText.setAttribute("y", textY);
        thText.textContent = label;
      }
      if (thBadge) thBadge.textContent = this._formatThresholdLabel(value);
    }

    _releaseDragState(event) {
      if (event && this._svgEl?.hasPointerCapture?.(event.pointerId)) {
        this._svgEl.releasePointerCapture(event.pointerId);
      }
      this._dragging = false;
      this._dragMoved = false;
      this._dragRect = null;
      this._draftThreshold = null;
    }

    _cancelDrag(event) {
      if (!this._dragging) return;
      this._releaseDragState(event);
      this._updateView({ force: true });
    }

    _onDragStart(event) {
      if (
        event.button !== 0 ||
        !this._canEdit ||
        !event.target.closest(`.${CHART_CLASS.TH_HANDLE}`)
      ) {
        return;
      }
      this._dragging = true;
      this._dragStartY = event.clientY;
      this._dragMoved = false;
      this._dragRect = this._svgEl.getBoundingClientRect();
      this._svgEl.setPointerCapture?.(event.pointerId);
    }

    _onDragMove(event) {
      if (!this._dragging || !this._dragRect) return;
      if (
        !this._dragMoved &&
        Math.abs(event.clientY - this._dragStartY) < DEFAULTS.DRAG_DEADZONE_PX
      ) {
        return;
      }
      this._dragMoved = true;
      const nextVal = this._valueFromPointer(event, this._dragRect);
      if (nextVal !== null && nextVal !== this._draftThreshold) {
        this._draftThreshold = nextVal;
        this._updateThresholdVisual(nextVal);
      }
    }

    _onDragEnd(event) {
      if (!this._dragging) return;
      const finalValue = this._dragMoved
        ? this._valueFromPointer(event, this._dragRect)
        : null;
      this._releaseDragState(event);
      if (finalValue !== null) {
        this._pendingThreshold = finalValue;
        this._pendingUntil = Date.now() + DEFAULTS.PENDING_THRESHOLD_MS;
        this._commitThreshold(finalValue);
      }
      this._updateView({ force: true });
    }

    _bindDragHandlers() {
      this._svgEl.addEventListener("pointerdown", (event) =>
        this._onDragStart(event),
      );
      this._svgEl.addEventListener("pointermove", (event) =>
        this._onDragMove(event),
      );
      this._svgEl.addEventListener("pointerup", (event) =>
        this._onDragEnd(event),
      );
      this._svgEl.addEventListener("pointercancel", (event) =>
        this._cancelDrag(event),
      );
      this._svgEl.addEventListener("lostpointercapture", (event) =>
        this._cancelDrag(event),
      );
    }

    _renderYAxisGridMarkup(padL, plotRight) {
      return CHART_LAYOUT.Y_TICKS.map((tickValue) => {
        const y = valueToSvgY(tickValue);
        const yFixed = fmtCoord(y);
        return `<line class="${CHART_CLASS.GRID}" x1="${padL}" y1="${yFixed}" x2="${plotRight}" y2="${yFixed}" />
          <text class="${CHART_CLASS.TICK}" x="${padL - CHART_LAYOUT.Y_LABEL_GAP}" y="${y + CHART_LAYOUT.Y_LABEL_OFFSET_Y}" text-anchor="end">${tickValue}%</text>`;
      }).join("");
    }

    _renderXAxisTicksMarkup(xTicks) {
      return xTicks
        .map(
          ({ x, label }) =>
            `<text class="${CHART_CLASS.TICK}" x="${x}" y="${CHART_LAYOUT.HEIGHT - CHART_LAYOUT.X_LABEL_BOTTOM_GAP}" text-anchor="middle">${escapeHtmlText(label)}</text>`,
        )
        .join("");
    }

    _renderThresholdMarkup(padL, plotRight, threshold) {
      const { lineY, pillY, textY, label } = thresholdSvgCoords(threshold);
      const pillX = plotRight + CHART_LAYOUT.PILL_GAP_X;
      const pillTextX = pillX + CHART_LAYOUT.PILL_WIDTH / 2;
      return `<line class="${CHART_CLASS.TH_LINE}" x1="${padL}" y1="${lineY}" x2="${plotRight}" y2="${lineY}" />
        <g class="${CHART_CLASS.TH_HANDLE}">
          <rect class="${CHART_CLASS.TH_PILL}" x="${pillX}" y="${pillY}" width="${CHART_LAYOUT.PILL_WIDTH}" height="${CHART_LAYOUT.PILL_HEIGHT}" rx="${CHART_LAYOUT.PILL_RADIUS}" />
          <text class="${CHART_CLASS.TH_TEXT}" x="${pillTextX}" y="${textY}" text-anchor="middle">${label}</text>
        </g>`;
    }

    _renderSvgMarkup(geometry, paths, hasThreshold, threshold) {
      const { padL, plotRight, xTicks } = geometry;
      const { linePath, areaPath, thHistoryPath } = paths;

      return `
        ${this._renderYAxisGridMarkup(padL, plotRight)}
        ${this._renderXAxisTicksMarkup(xTicks)}
        ${areaPath ? `<path class="${CHART_CLASS.AREA}" d="${areaPath}" />` : ""}
        ${linePath ? `<path class="${CHART_CLASS.LINE}" d="${linePath}" />` : ""}
        ${thHistoryPath ? `<path class="${CHART_CLASS.TH_HISTORY}" d="${thHistoryPath}" />` : ""}
        ${hasThreshold ? this._renderThresholdMarkup(padL, plotRight, threshold) : ""}
      `;
    }

    _buildRenderKey(now, state) {
      return [
        this._selectedRangeId,
        this._chartWidth,
        this._translationsLang,
        Object.keys(this._translations).length,
        state.currentProb,
        state.currentThreshold,
        state.threshold,
        state.canEdit,
        this._points.length,
        this._thresholdPoints.length,
        Math.floor(now / TIME_MS.MINUTE),
      ].join("|");
    }

    _updateRangeButtons() {
      for (const btn of this._rangeButtons) {
        const range = PROBABILITY_CHART_RANGE_BY_ID.get(btn.dataset.range);
        if (range) {
          btn.textContent = this._t(range.labelKey) || range.id;
        }
        btn.classList.toggle(
          CHART_CLASS.ACTIVE,
          btn.dataset.range === this._selectedRangeId,
        );
      }
    }

    _renderMetaBar(now, { currentProb, hasThreshold, threshold, canEdit }) {
      const historyUrl = this._buildHistoryUrl(now);
      const probBadge =
        currentProb !== null
          ? escapeHtmlText(
              this._t(I18N_KEY.PROBABILITY_BADGE, {
                value: Math.round(currentProb),
              }),
            )
          : "";
      const thBadge = hasThreshold
        ? escapeHtmlText(this._formatThresholdLabel(threshold))
        : "";
      const dragHint = canEdit
        ? escapeHtmlText(this._t(I18N_KEY.DRAG_THRESHOLD_HINT))
        : "";
      const historyLinkTitle = escapeHtmlText(
        this._t(I18N_KEY.HISTORY_LINK_TITLE),
      );
      const historyLinkText = escapeHtmlText(this._t(I18N_KEY.HISTORY_LINK));

      this._metaEl.innerHTML = [
        probBadge
          ? `<span class="${CHART_CLASS.BADGE} ${CHART_CLASS.PROB}">${probBadge}</span>`
          : "",
        thBadge
          ? `<span class="${CHART_CLASS.BADGE} ${CHART_CLASS.TH}">${thBadge}</span>`
          : "",
        dragHint ? `<span class="${CHART_CLASS.HINT}">${dragHint}</span>` : "",
        historyUrl
          ? `<a class="${CHART_CLASS.HISTORY_LINK}" href="${escapeHtmlText(historyUrl)}" title="${historyLinkTitle}"><ha-icon icon="${ICON.OPEN_IN_NEW}"></ha-icon>${historyLinkText}</a>`
          : "",
      ].join("");
    }

    _renderHeader(now, state) {
      this._titleEl.textContent =
        this._config.title || this._t(I18N_KEY.PROBABILITY_TITLE);
      this._updateRangeButtons();
      this._renderMetaBar(now, state);
    }

    _renderChart(
      now,
      { currentProb, currentThreshold, hasThreshold, threshold, canEdit },
    ) {
      const rangeWindow = this._resolveCurrentRange(now);
      const geometry = buildChartGeometry(
        now,
        rangeWindow,
        hasThreshold,
        this._chartWidth,
        {
          nowLabel: this._t(I18N_KEY.AXIS_NOW),
          locale: getHassLanguage(this._hass),
        },
      );
      const pts = extendSeriesToNow(
        clipPointsToWindow(this._points, rangeWindow.startMs),
        currentProb,
        now,
      );
      const thPts = hasThreshold
        ? extendSeriesToNow(
            clipPointsToWindow(this._thresholdPoints, rangeWindow.startMs),
            currentThreshold,
            now,
          )
        : [];
      const paths = {
        ...buildLinearPaths(pts, geometry.xOf, geometry.baseY),
        thHistoryPath: buildStepPath(thPts, geometry.xOf),
      };

      this._svgEl.setAttribute(
        "viewBox",
        `0 0 ${geometry.width} ${CHART_LAYOUT.HEIGHT}`,
      );
      this._svgEl.classList.toggle(CHART_CLASS.EDITABLE, canEdit);
      this._svgEl.innerHTML = this._renderSvgMarkup(
        geometry,
        paths,
        hasThreshold,
        threshold,
      );
    }

    _updateView({ now = Date.now(), force = false } = {}) {
      if (!this._config || !this._mounted) return;
      const state = this._resolveRenderState(now);
      const renderKey = this._buildRenderKey(now, state);
      if (!force && renderKey === this._lastRenderKey) return;

      this._lastRenderKey = renderKey;
      this._canEdit = state.canEdit;
      this._renderHeader(now, state);
      this._renderChart(now, state);
    }
  }

  // --- Custom element & strategy registration ---

  let localizeRetryTimer = null;

  function defineElementOnce(tag, ctor) {
    if (!customElements.get(tag)) {
      customElements.define(tag, ctor);
    }
  }

  function localizeStrategyEntry(
    strategyEntry,
    retriesLeft = DEFAULTS.LOCALIZE_MAX_RETRIES,
  ) {
    if (localizeRetryTimer !== null) {
      clearTimeout(localizeRetryTimer);
      localizeRetryTimer = null;
    }
    const haRoot =
      typeof document !== "undefined"
        ? document.querySelector(HA_ROOT_TAG)
        : null;
    const hass = haRoot?.hass;
    if (!hass) {
      if (retriesLeft > 0 && typeof setTimeout === "function") {
        localizeRetryTimer = setTimeout(() => {
          localizeRetryTimer = null;
          localizeStrategyEntry(strategyEntry, retriesLeft - 1);
        }, DEFAULTS.LOCALIZE_RETRY_DELAY_MS);
      }
      return;
    }
    fetchTranslationsWithFallback(hass, TRANSLATION_CATEGORY.COMMON)
      .then((resources) => {
        const t = createTranslator(hass, resources);
        const localizedName = t(I18N_KEY.DASHBOARD_TITLE);
        const localizedDesc = t(I18N_KEY.STRATEGY_DESCRIPTION);
        if (localizedName) strategyEntry.name = localizedName;
        if (localizedDesc) strategyEntry.description = localizedDesc;
      })
      .catch(() => {});
  }

  /** Register custom elements and dashboard strategy idempotently.
   *  Called immediately and again once HA's root element is defined so definitions
   *  survive HA's scoped CustomElementRegistry polyfill race when loaded early. */
  function registerDashboardStrategy() {
    defineElementOnce(PROBABILITY_CARD_TAG, AreaOccupancyProbabilityCard);
    defineElementOnce(STRATEGY_TAG, AreaOccupancyDashboardStrategy);

    window.customStrategies = window.customStrategies || [];
    let strategyEntry = window.customStrategies.find(
      (item) =>
        item.type === STRATEGY_TYPE && item.strategyType === STRATEGY_KIND,
    );
    if (!strategyEntry) {
      strategyEntry = {
        type: STRATEGY_TYPE,
        strategyType: STRATEGY_KIND,
        name: BRAND_NAME,
        documentationURL: DEFAULTS.DOCUMENTATION_URL,
      };
      window.customStrategies.push(strategyEntry);
    }

    localizeStrategyEntry(strategyEntry);
  }

  registerDashboardStrategy();
  customElements.whenDefined(HA_ROOT_TAG).then(registerDashboardStrategy);
})();
