"""Config flow for Area Occupancy Detection integration.

This module handles the configuration flow for the Area Occupancy Detection integration.
It provides both initial configuration and options update capabilities, with comprehensive
validation of all inputs to ensure a valid configuration.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
import contextlib
import json
import logging
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast, override

import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    STATE_CLOSED,
    STATE_HOME,
    STATE_IDLE,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_ON,
    STATE_OPEN,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_STANDBY,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import AbortFlow, SectionConfig, section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    BooleanSelector,
    DurationSelector,
    DurationSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    Selector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)
from homeassistant.helpers.translation import (
    async_get_cached_translations,
    async_get_translations,
)
from homeassistant.loader import DATA_INTEGRATIONS

from . import preview
from .config_helpers import (
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    THRESHOLD_STEP,
    WEIGHT_MAX,
    WEIGHT_MIN,
    WEIGHT_STEP,
    apply_purpose_based_decay_default,
    duration_to_seconds,
    find_area_by_id,
    find_area_subentry_id,
    flatten_sectioned_input,
    is_active_config_entry,
    iter_area_subentries,
    normalize_adjacent_areas,
    normalize_exclusion_mode,
    normalize_group_expansion_mode,
    parse_global_purpose_decay_half_lives,
    parse_global_sleep_decay_half_life,
    remove_area_from_list,
    seconds_to_duration,
    update_area_in_list,
    validate_area_config,
    validate_decay_half_life,
    validate_person_input,
    validate_sensor_states,
    validate_sleep_decay_half_life,
)
from .const import (
    AWAY_MODE_ENTITY_DOMAINS,
    CONF_ACTION_ADD_AREA,
    CONF_ACTION_GLOBAL_SETTINGS,
    CONF_ACTION_MANAGE_PEOPLE,
    CONF_ADJACENT_AREAS,
    CONF_AIR_QUALITY_SENSORS,
    CONF_APPLIANCE_ACTIVE_STATES,
    CONF_APPLIANCES,
    CONF_AREA_ID,
    CONF_AUTO_ADDED_SENSORS,
    CONF_AUTO_DISCOVER_DOMAINS,
    CONF_AUTO_DISCOVER_SENSORS,
    CONF_AWAY_MODE_ENTITY,
    CONF_BUTTON_PULSE_DURATION,
    CONF_BUTTON_SENSORS,
    CONF_CLOSED_DOOR_HOLD,
    CONF_CO2_SENSORS,
    CONF_CO_SENSORS,
    CONF_COVER_ACTIVE_STATES,
    CONF_COVER_SENSORS,
    CONF_CUSTOM_BINARY_ACTIVE_STATES,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_ACTIVE_MAX,
    CONF_CUSTOM_NUMERIC_ACTIVE_MIN,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_DECAY_ENABLED,
    CONF_DECAY_HALF_LIFE,
    CONF_DOOR_ACTIVE_STATE,
    CONF_DOOR_SENSORS,
    CONF_EXCLUDE_FROM_ALL_AREAS,
    CONF_EXCLUDED_INTEGRATIONS,
    CONF_EXCLUDED_MANUFACTURERS,
    CONF_EXCLUDED_MODELS,
    CONF_EXCLUDED_SENSOR_TYPES,
    CONF_EXCLUDED_SENSORS,
    CONF_EXPAND_GROUPS,
    CONF_HEALTH_ENABLED,
    CONF_HUMIDITY_SENSORS,
    CONF_ILLUMINANCE_SENSORS,
    CONF_LOCK_ACTIVE_STATE,
    CONF_LOCK_SENSORS,
    CONF_MEDIA_ACTIVE_STATES,
    CONF_MEDIA_DEVICES,
    CONF_MIN_PRIOR_OVERRIDE,
    CONF_MOTION_PROB_GIVEN_FALSE,
    CONF_MOTION_PROB_GIVEN_TRUE,
    CONF_MOTION_SENSORS,
    CONF_MOTION_TIMEOUT,
    CONF_OPTION_PREFIX_AREA,
    CONF_PEOPLE,
    CONF_PERSON_CONFIDENCE_THRESHOLD,
    CONF_PERSON_DEVICE_TRACKER,
    CONF_PERSON_ENTITY,
    CONF_PERSON_SLEEP_AREA,
    CONF_PERSON_SLEEP_SENSOR,
    CONF_PERSON_SLEEP_SENSORS,
    CONF_PM10_SENSORS,
    CONF_PM25_SENSORS,
    CONF_POWER_SENSORS,
    CONF_PRESSURE_SENSORS,
    CONF_PURPOSE,
    CONF_PURPOSE_DECAY_HALF_LIVES,
    CONF_SENSOR_PRECISION,
    CONF_SLEEP_DECAY_HALF_LIFE,
    CONF_SLEEP_END,
    CONF_SLEEP_START,
    CONF_SOUND_PRESSURE_SENSORS,
    CONF_TEMPERATURE_SENSORS,
    CONF_THRESHOLD,
    CONF_VERSION,
    CONF_VOC_SENSORS,
    CONF_WASP_ENABLED,
    CONF_WASP_MAX_DURATION,
    CONF_WASP_MOTION_TIMEOUT,
    CONF_WASP_VERIFICATION_DELAY,
    CONF_WASP_WEIGHT,
    CONF_WEIGHT_APPLIANCE,
    CONF_WEIGHT_BUTTON,
    CONF_WEIGHT_COVER,
    CONF_WEIGHT_CUSTOM_BINARY,
    CONF_WEIGHT_CUSTOM_NUMERIC,
    CONF_WEIGHT_DOOR,
    CONF_WEIGHT_ENVIRONMENTAL,
    CONF_WEIGHT_LOCK,
    CONF_WEIGHT_MEDIA,
    CONF_WEIGHT_MOTION,
    CONF_WEIGHT_POWER,
    CONF_WEIGHT_WIFI_CLIENTS,
    CONF_WEIGHT_WINDOW,
    CONF_WIFI_CLIENTS_SENSORS,
    CONF_WINDOW_ACTIVE_STATE,
    CONF_WINDOW_SENSORS,
    DEFAULT_APPLIANCE_ACTIVE_STATES,
    DEFAULT_BUTTON_PULSE_DURATION,
    DEFAULT_COVER_ACTIVE_STATES,
    DEFAULT_CUSTOM_BINARY_ACTIVE_STATES,
    DEFAULT_CUSTOM_NUMERIC_ACTIVE_MAX,
    DEFAULT_CUSTOM_NUMERIC_ACTIVE_MIN,
    DEFAULT_DECAY_ENABLED,
    DEFAULT_DECAY_HALF_LIFE,
    DEFAULT_EXCLUDE_FROM_ALL_AREAS,
    DEFAULT_EXCLUDED_MANUFACTURERS,
    DEFAULT_EXCLUDED_MODELS,
    DEFAULT_GLOBAL_EXPAND_GROUPS,
    DEFAULT_HEALTH_ENABLED,
    DEFAULT_LANGUAGE,
    DEFAULT_MEDIA_ACTIVE_STATES,
    DEFAULT_MIN_PRIOR_OVERRIDE,
    DEFAULT_MOTION_PROB_GIVEN_FALSE,
    DEFAULT_MOTION_PROB_GIVEN_TRUE,
    DEFAULT_MOTION_TIMEOUT,
    DEFAULT_PURPOSE,
    DEFAULT_SENSOR_PRECISION,
    DEFAULT_SLEEP_CONFIDENCE_THRESHOLD,
    DEFAULT_SLEEP_DECAY_HALF_LIFE,
    DEFAULT_SLEEP_END,
    DEFAULT_SLEEP_START,
    DEFAULT_THRESHOLD,
    DEFAULT_WASP_MAX_DURATION,
    DEFAULT_WASP_MOTION_TIMEOUT,
    DEFAULT_WASP_VERIFICATION_DELAY,
    DEFAULT_WASP_WEIGHT,
    DEFAULT_WEIGHT_APPLIANCE,
    DEFAULT_WEIGHT_BUTTON,
    DEFAULT_WEIGHT_COVER,
    DEFAULT_WEIGHT_CUSTOM_BINARY,
    DEFAULT_WEIGHT_CUSTOM_NUMERIC,
    DEFAULT_WEIGHT_DOOR,
    DEFAULT_WEIGHT_ENVIRONMENTAL,
    DEFAULT_WEIGHT_LOCK,
    DEFAULT_WEIGHT_MEDIA,
    DEFAULT_WEIGHT_MOTION,
    DEFAULT_WEIGHT_POWER,
    DEFAULT_WEIGHT_WIFI_CLIENTS,
    DEFAULT_WEIGHT_WINDOW,
    DEFAULT_WINDOW_ACTIVE_STATE,
    DISCOVERY_EXCLUSION_RULES,
    DOMAIN,
    DURATION_FIELDS,
    INTEGRATION_TITLE,
    MAX_PROBABILITY,
    MIN_PROBABILITY,
    SENSOR_KEY_TO_TYPE_SLUG,
    SLEEP_PRESENCE_HALF_LIFE,
    SUBENTRY_TYPE_AREA,
    TYPE_SLUG_TO_SENSOR_KEY,
    ExclusionMode,
    GroupExpansionMode,
    get_default_state,
    get_sensor_type_mapping,
    get_state_options,
)
from .data.entity_type import InputType
from .data.purpose import (
    PURPOSE_DEFINITIONS,
    AreaPurpose,
    Purpose,
    get_default_decay_half_life,
    get_purpose_options,
)
from .discovery import (
    ALL_AREA_SENSOR_KEYS,
    DISCOVERABLE_SENSOR_KEYS,
    area_discovery_unique_id,
    async_trigger_area_discoveries,
    build_area_discovery_kwargs,
    build_suggested_area_config,
    collect_excluded_sensor_ids,
    discover_area_sensors,
    discover_eligible_areas,
    get_enabled_discovery_domains,
    is_auto_discovery_enabled,
    parse_tracked_auto_sensors,
    resolve_area_sensors,
    resolve_excluded_device_entity_ids,
)
from .discovery_filters import (
    entry_source_domain,
    format_platform_source,
    is_weather_entity,
    split_platform_source,
)

_LOGGER = logging.getLogger(__name__)


# Menu options of the ``area_action`` hub that open one wizard page as a
# standalone edit form (see ``BaseOccupancyFlow._start_section_edit``).
AREA_EDIT_SPOKES: tuple[str, ...] = (
    "edit_basics",
    "edit_motion",
    "edit_sensors",
    "edit_behavior",
)

# Offered as suggestions in the custom-sensor state picker; the selector also
# accepts a typed value, so this list only has to cover the common cases.
COMMON_CUSTOM_ACTIVE_STATES: list[str] = [
    STATE_ON,
    STATE_OFF,
    STATE_OPEN,
    STATE_CLOSED,
    STATE_HOME,
    STATE_NOT_HOME,
    STATE_PLAYING,
    STATE_PAUSED,
    STATE_IDLE,
    STATE_STANDBY,
]

ENVIRONMENTAL_SENSOR_KEYS: tuple[str, ...] = (
    CONF_ILLUMINANCE_SENSORS,
    CONF_HUMIDITY_SENSORS,
    CONF_TEMPERATURE_SENSORS,
    CONF_CO2_SENSORS,
    CONF_CO_SENSORS,
    CONF_SOUND_PRESSURE_SENSORS,
    CONF_PRESSURE_SENSORS,
    CONF_AIR_QUALITY_SENSORS,
    CONF_VOC_SENSORS,
    CONF_PM25_SENSORS,
    CONF_PM10_SENSORS,
)

SENSOR_GROUP_KEYS: dict[str, tuple[str, ...]] = {
    "windows_and_doors": (
        CONF_DOOR_SENSORS,
        CONF_LOCK_SENSORS,
        CONF_WINDOW_SENSORS,
        CONF_COVER_SENSORS,
    ),
    "media": (CONF_MEDIA_DEVICES,),
    "appliances": (CONF_APPLIANCES, CONF_BUTTON_SENSORS),
    "environmental": ENVIRONMENTAL_SENSOR_KEYS,
    "power": (CONF_POWER_SENSORS,),
    "wifi_clients": (CONF_WIFI_CLIENTS_SENSORS,),
    "custom": (CONF_CUSTOM_BINARY_SENSORS, CONF_CUSTOM_NUMERIC_SENSORS),
}

# Sensor groups of the "Additional sensors" wizard step, in display order.
# Each is a spoke in the edit hub (``area_sensors_menu``).
SENSOR_GROUPS: tuple[str, ...] = tuple(SENSOR_GROUP_KEYS)

SECTION_AUTO_DISCOVERY_TYPES: Final = "auto_discovery_types"
SECTION_AREA_EXCLUSIONS: Final = "area_exclusions"
SECTION_GLOBAL_SENSOR_TYPES: Final = "sensor_types"
SECTION_GLOBAL_DEVICES: Final = "devices"
SECTION_GLOBAL_ENTITIES: Final = "entities"
SECTION_GLOBAL_INTEGRATIONS: Final = "integrations"
AUTO_ADDED_SECTION: Final = "auto_added"
EXPLICIT_SECTION: Final = "explicit"
AUTO_ADDED_ENTITIES_FIELD: Final = "auto_added_entities"
AUTO_ADDED_FIELD_PREFIX: Final = "auto_added_"

STEP_GLOBAL_SETTINGS: Final = "global_settings"
STEP_GLOBAL_SLEEP: Final = "global_sleep"
STEP_GLOBAL_PURPOSE_DECAY: Final = "global_purpose_decay"
STEP_GLOBAL_GENERAL: Final = "global_general"
STEP_GLOBAL_EXCLUSIONS: Final = "global_exclusions"
STEP_DISCOVERY_CONFIRM: Final = "discovery_confirm"

_TRANSLATION_SENSOR_TYPES: Final = "sensor_types"
_TRANSLATION_GROUP_EXPANSION: Final = "group_expansion"
_AREA_EXCLUSION_FIELD_KEYS: Final[tuple[str, ...]] = (
    CONF_EXCLUDED_MANUFACTURERS,
    CONF_EXCLUDED_MODELS,
    CONF_EXCLUDED_SENSORS,
    CONF_EXCLUDED_INTEGRATIONS,
)
_TIME_HHMM_LEN: Final = 5
_TRANSLATIONS_DIR: Final = "translations"
_COMMON_TRANSLATION_CATEGORY: Final = "common"
_TITLE_TRANSLATION_CATEGORY: Final = "title"
_COMMON_TRANSLATION_PREFIX: Final = (
    f"component.{DOMAIN}.{_COMMON_TRANSLATION_CATEGORY}."
)
_INTEGRATION_SOURCE_LABEL_SEPARATOR: Final = " — "
_CONTEXT_TITLE_PLACEHOLDERS: Final = "title_placeholders"
_PLACEHOLDER_AREA_NAME: Final = "area_name"
_PLACEHOLDER_NAME: Final = "name"
_PLACEHOLDER_DECAY_DEFAULT: Final = "decay_default"
_PLACEHOLDER_SLEEP_DECAY_DEFAULT: Final = "sleep_decay_default"
_PLACEHOLDER_SLEEP_DECAY_BUILTIN_DEFAULT: Final = "sleep_decay_builtin_default"
_PLACEHOLDER_MOTION_COUNT: Final = "motion_count"
_PLACEHOLDER_SENSOR_COUNT: Final = "sensor_count"
_PLACEHOLDER_SLEEP_START: Final = "sleep_start"
_PLACEHOLDER_SLEEP_END: Final = "sleep_end"
_PLACEHOLDER_SLEEP_DECAY: Final = "sleep_decay"
_PLACEHOLDER_PURPOSE_OVERRIDES: Final = "purpose_overrides"
_PLACEHOLDER_HEALTH: Final = "health"
_PLACEHOLDER_PRECISION: Final = "precision"
_PLACEHOLDER_GROUPS: Final = "groups"
_PLACEHOLDER_AWAY: Final = "away"
_PLACEHOLDER_EXCLUDED_TYPES_COUNT: Final = "excluded_types_count"
_PLACEHOLDER_EXCLUDED_DEVICES_COUNT: Final = "excluded_devices_count"
_PLACEHOLDER_EXCLUDED_ENTITIES_COUNT: Final = "excluded_entities_count"
_PLACEHOLDER_EXCLUDED_INTEGRATIONS_COUNT: Final = "excluded_integrations_count"
_ERROR_BASE: Final = "base"
_ERROR_PROB_TRUE_MUST_EXCEED_FALSE: Final = "prob_true_must_exceed_false"
_ERROR_AREA_REQUIRED: Final = "area_required"
_ERROR_AREA_NOT_FOUND: Final = "area_not_found"
_ERROR_MOTION_REQUIRED: Final = "motion_required"
_PURPOSE_DEFAULT_PLACEHOLDER_SUFFIX: Final = "_default"
_UTF8_ENCODING: Final = "utf-8"
_ABORT_AREA_REQUIRED: Final = "area_required"
_ABORT_AREA_NOT_FOUND: Final = "area_not_found"
_ABORT_AREA_ALREADY_CONFIGURED: Final = "area_already_configured"
_ABORT_MOTION_REQUIRED: Final = "motion_required"
_ABORT_AREA_ADDED: Final = "area_added"
_ABORT_ALREADY_CONFIGURED: Final = "already_configured"
_COMMON_KEY_PURPOSE_OVERRIDES_DEFAULT: Final = (
    "global_settings_purpose_overrides_default"
)
_COMMON_KEY_PURPOSE_OVERRIDES_COUNT: Final = "global_settings_purpose_overrides_count"
_COMMON_KEY_STATE_ON: Final = "state_on"
_COMMON_KEY_STATE_OFF: Final = "state_off"
_COMMON_KEY_GROUP_EXPAND: Final = "group_expansion_expand"
_COMMON_KEY_GROUP_KEEP: Final = "group_expansion_keep"
_COMMON_KEY_AWAY_PERSON_TRACKING: Final = "away_mode_person_tracking"

_COMMON_TRANSLATION_KEYS: Final[tuple[str, ...]] = (
    _COMMON_KEY_PURPOSE_OVERRIDES_DEFAULT,
    _COMMON_KEY_PURPOSE_OVERRIDES_COUNT,
    _COMMON_KEY_STATE_ON,
    _COMMON_KEY_STATE_OFF,
    _COMMON_KEY_GROUP_EXPAND,
    _COMMON_KEY_GROUP_KEEP,
    _COMMON_KEY_AWAY_PERSON_TRACKING,
)


def _section_options(*, collapsed: bool) -> SectionConfig:
    """Build Home Assistant ``section(...)`` options dict."""
    return SectionConfig(collapsed=collapsed)


def _component_title_key(component: str) -> str:
    """Return the Home Assistant translation key for a component title."""
    return f"component.{component}.{_TITLE_TRANSLATION_CATEGORY}"


def _read_only_entity_selector() -> Selector[Any]:
    """Return the shared read-only multi-entity selector for auto-added sensors."""
    return cast(
        "Selector[Any]",
        EntitySelector(EntitySelectorConfig(multiple=True, read_only=True)),
    )


def _multi_custom_list_selector(options: list[SelectOptionDict]) -> Selector[Any]:
    """Return a multi-select list selector that accepts custom text entries."""
    return cast(
        "Selector[Any]",
        SelectSelector(
            SelectSelectorConfig(
                options=options,
                multiple=True,
                custom_value=True,
                mode=SelectSelectorMode.LIST,
            )
        ),
    )


def _sensor_types_list_selector(options: list[str]) -> Selector[Any]:
    """Return a multi-select sensor-type checkbox list selector."""
    return cast(
        "Selector[Any]",
        SelectSelector(
            SelectSelectorConfig(
                options=options,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=_TRANSLATION_SENSOR_TYPES,
            )
        ),
    )


def _duration_selector() -> Selector[Any]:
    """Return the shared duration selector without a days field."""
    return cast(
        "Selector[Any]",
        DurationSelector(DurationSelectorConfig(enable_day=False)),
    )


def _load_en_common_translations() -> dict[str, str]:
    """Load bundled English ``common`` strings once for bare-mock fallback."""
    path = Path(__file__).parent / _TRANSLATIONS_DIR / f"{DEFAULT_LANGUAGE}.json"
    try:
        loaded: Any = json.loads(path.read_text(encoding=_UTF8_ENCODING))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    common: Any = cast("dict[Any, Any]", loaded).get(_COMMON_TRANSLATION_CATEGORY)
    if not isinstance(common, dict):
        return {}
    return {
        f"{_COMMON_TRANSLATION_PREFIX}{key}": value
        for key, value in cast("dict[Any, Any]", common).items()
        if isinstance(key, str) and isinstance(value, str)
    }


_EN_COMMON_TRANSLATIONS: Final[dict[str, str]] = _load_en_common_translations()


def _translation_language(hass: HomeAssistant | None) -> str:
    """Return the active Home Assistant UI language tag, defaulting to English."""
    config = getattr(hass, "config", None)
    language = getattr(config, "language", None)
    return language if isinstance(language, str) and language else DEFAULT_LANGUAGE


async def _async_get_common_translations(
    hass: HomeAssistant | None,
) -> dict[str, str]:
    """Return localized ``common`` translations merged over English defaults."""
    merged = dict(_EN_COMMON_TRANSLATIONS)
    if hass is None:
        return merged
    language = _translation_language(hass)
    with contextlib.suppress(
        AttributeError, KeyError, RuntimeError, TypeError, ValueError
    ):
        fetched = await async_get_translations(
            hass,
            language,
            _COMMON_TRANSLATION_CATEGORY,
            integrations=[DOMAIN],
        )
        merged.update(fetched)
    return merged


def _format_common_translation(
    translations: Mapping[str, str],
    key: str,
    **placeholders: Any,
) -> str:
    """Look up and format one ``common`` translation string cleanly."""
    template = translations.get(f"{_COMMON_TRANSLATION_PREFIX}{key}", key)
    return template.format(**placeholders) if placeholders else template


# Keep the sensor type ordering aligned with the manual wizard's groups and
# field order. Motion is configured in its own wizard step.
_SENSOR_TYPE_ORDER: Final[tuple[str, ...]] = (
    SENSOR_KEY_TO_TYPE_SLUG[CONF_MOTION_SENSORS],
    *(
        SENSOR_KEY_TO_TYPE_SLUG[key]
        for group in SENSOR_GROUPS
        for key in SENSOR_GROUP_KEYS[group]
        if key in SENSOR_KEY_TO_TYPE_SLUG
    ),
)


def _get_auto_discover_sensor_type_options() -> list[str]:
    """Return ordered checkbox options for each auto-discoverable sensor type."""
    return [
        sensor_type
        for sensor_type in _SENSOR_TYPE_ORDER
        if TYPE_SLUG_TO_SENSOR_KEY[sensor_type] in DISCOVERABLE_SENSOR_KEYS
    ]


def _get_excluded_sensor_type_options() -> list[str]:
    """Return ordered sensor type choices grouped like manual configuration."""
    sensor_types = get_sensor_type_mapping()
    return [
        sensor_type
        for sensor_type in _SENSOR_TYPE_ORDER
        if sensor_type in sensor_types and sensor_type != InputType.SLEEP
    ]


def _get_ordered_auto_discover_types(data: dict[str, Any]) -> list[str]:
    """Return enabled sensor types in the manual wizard's display order."""
    enabled = get_enabled_discovery_domains(data)
    return [
        sensor_type
        for sensor_type in _get_auto_discover_sensor_type_options()
        if TYPE_SLUG_TO_SENSOR_KEY[sensor_type] in enabled
    ]


def _sensor_types_to_discovery_domains(sensor_types: list[str]) -> list[str]:
    """Convert selector type values to the persisted discovery domain keys."""
    resolved: list[str] = []
    for item in sensor_types:
        key = TYPE_SLUG_TO_SENSOR_KEY.get(item, item)
        if key in DISCOVERABLE_SENSOR_KEYS and key not in resolved:
            resolved.append(key)
    return resolved


def _collect_registered_platforms(
    hass: HomeAssistant | None,
    current: dict[str, Any] | None = None,
) -> set[str]:
    """Collect integration platform slugs and ``platform:source`` keys."""
    platforms: set[str] = set()
    if hass is not None:
        with contextlib.suppress(AttributeError, KeyError, RuntimeError, TypeError):
            registry = er.async_get(hass)
            for entry in registry.entities.values():
                if entry.platform and entry.platform != DOMAIN:
                    platforms.add(entry.platform)
                    if source_domain := entry_source_domain(hass, entry.entity_id):
                        platforms.add(
                            format_platform_source(entry.platform, source_domain)
                        )
    raw_excluded: Any = (current or {}).get(CONF_EXCLUDED_INTEGRATIONS) or []
    if isinstance(raw_excluded, (list, tuple, set, frozenset)):
        for platform in cast("Iterable[Any]", raw_excluded):
            if isinstance(platform, str) and platform:
                platforms.add(platform)
    return platforms


def _get_cached_component_titles(hass: HomeAssistant | None) -> Mapping[str, Any]:
    """Return cached component title translations when available."""
    if hass is None:
        return {}
    with contextlib.suppress(AttributeError, KeyError, RuntimeError, TypeError):
        return async_get_cached_translations(
            hass, _translation_language(hass), _TITLE_TRANSLATION_CATEGORY
        )
    return {}


def _format_integration_option(
    platform: str,
    integrations: Mapping[str, Any],
    cached_titles: Mapping[str, Any],
) -> SelectOptionDict:
    """Format one integration exclusion option with localized display labels."""
    base_platform, source_domain = split_platform_source(platform)
    integration = integrations.get(base_platform)
    name = (
        cached_titles.get(_component_title_key(base_platform))
        or getattr(integration, "name", None)
        or base_platform.replace("_", " ").title()
    )
    source_label = (
        cached_titles.get(_component_title_key(source_domain))
        or source_domain.replace("_", " ").title()
        if source_domain
        else ""
    )
    label = (
        f"{name}{_INTEGRATION_SOURCE_LABEL_SEPARATOR}{source_label}"
        if source_label
        else name
    )
    return SelectOptionDict(value=platform, label=label)


def _get_excluded_integration_options(
    hass: HomeAssistant | None,
    current: dict[str, Any] | None = None,
) -> list[SelectOptionDict]:
    """Return sorted integration options pre-populated from the entity registry."""
    platforms = _collect_registered_platforms(hass, current)
    raw_integrations: Any = (
        hass.data.get(DATA_INTEGRATIONS, {})
        if hass is not None and isinstance(getattr(hass, "data", None), dict)
        else {}
    )
    integrations: Mapping[str, Any] = (
        cast("Mapping[str, Any]", raw_integrations)
        if isinstance(raw_integrations, Mapping)
        else {}
    )
    cached_titles = _get_cached_component_titles(hass)
    return [
        _format_integration_option(platform, integrations, cached_titles)
        for platform in sorted(platforms, key=str.lower)
    ]


def _get_excluded_device_attribute_options(
    hass: HomeAssistant | None,
    attribute: str,
    config_key: str,
    current: dict[str, Any] | None = None,
) -> list[SelectOptionDict]:
    """Return registered device attribute values (manufacturer or model) for matching."""
    matches: set[str] = set()
    if hass is not None:
        with contextlib.suppress(AttributeError, KeyError, RuntimeError, TypeError):
            raw_devices: Any = getattr(dr.async_get(hass), "devices", None)
            device_iter = (
                cast("Mapping[Any, Any]", raw_devices).values()
                if isinstance(raw_devices, Mapping)
                else (raw_devices or ())
            )
            for device in device_iter:
                value = getattr(device, attribute, None)
                if isinstance(value, str) and value.strip():
                    matches.add(value.strip())
    raw_matches: Any = (current or {}).get(config_key) or []
    if isinstance(raw_matches, (list, tuple, set, frozenset)):
        for match in cast("Iterable[Any]", raw_matches):
            if isinstance(match, str) and match.strip():
                matches.add(match.strip())

    return [
        SelectOptionDict(value=match, label=match)
        for match in sorted(matches, key=str.casefold)
    ]


def _format_seconds(seconds: float) -> str:
    """Render a duration in seconds as a short human string (45s, 5m, 1h 30m)."""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _get_state_select_options(state_type: str) -> list[dict[str, str]]:
    """Get state options for SelectSelector."""
    states = get_state_options(state_type)
    return [
        {"value": option.value, "label": option.name} for option in states["options"]
    ]


def _entity_contains_keyword(hass: HomeAssistant, entity_id: str, keyword: str) -> bool:
    """Check if entity ID or friendly name contains a keyword.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to check
        keyword: Keyword to search for (case-insensitive)

    Returns:
        True if keyword is found in entity_id or friendly name
    """
    # Convert keyword to lowercase for case-insensitive comparison
    keyword_lower = keyword.lower()

    # Check entity ID
    if keyword_lower in entity_id.lower():
        return True

    # Check friendly name from state
    state = hass.states.get(entity_id)
    return bool(state and state.name and keyword_lower in state.name.lower())


def _is_weather_entity(entity_id: str, platform: str | None) -> bool:
    """Check if an entity is from a weather integration.

    Weather entities measure outdoor conditions and are not suitable for
    room occupancy detection.

    Args:
        entity_id: Entity ID to check
        platform: Platform/integration that created the entity

    Returns:
        True if entity is from a weather integration
    """
    return is_weather_entity(entity_id, platform)


def _get_include_entities(hass: HomeAssistant) -> dict[str, list[str]]:
    """Get lists of entities to include for specific selectors."""
    registry = er.async_get(hass)
    include_appliance_entities = []
    include_button_entities = []
    include_window_entities = []
    include_door_entities = []
    include_temperature_entities = []
    include_humidity_entities = []
    include_pressure_entities = []
    include_air_quality_entities = []
    include_pm25_entities = []
    include_pm10_entities = []
    include_motion_entities = []
    include_wifi_clients_entities = []
    include_custom_binary_entities = []
    include_custom_numeric_entities = []

    door_window_classes = (
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.GARAGE_DOOR,
        BinarySensorDeviceClass.OPENING,
        BinarySensorDeviceClass.WINDOW,
    )
    door_classes = (
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.GARAGE_DOOR,
    )
    door_keyword_classes = (
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.GARAGE_DOOR,
        BinarySensorDeviceClass.OPENING,
    )

    appliance_excluded_classes = [
        BinarySensorDeviceClass.MOTION,
        BinarySensorDeviceClass.OCCUPANCY,
        BinarySensorDeviceClass.PRESENCE,
        *door_window_classes,
    ]

    # Check binary_sensor, switch, fan, and light for potential appliances.
    domains_to_check = [
        Platform.BINARY_SENSOR,
        Platform.SWITCH,
        Platform.FAN,
        Platform.LIGHT,
    ]
    entity_ids = []
    for domain in domains_to_check:
        entity_ids.extend(hass.states.async_entity_ids(domain))

    for eid in entity_ids:
        state = hass.states.get(eid)
        if state:
            device_class = state.attributes.get("device_class")
            if device_class not in appliance_excluded_classes:
                include_appliance_entities.append(eid)

    include_button_entities = [
        *hass.states.async_entity_ids(Platform.BUTTON),
        *hass.states.async_entity_ids(Platform.EVENT),
    ]

    # Check registry for specific door/window classes
    for entry in registry.entities.values():
        if entry.domain == Platform.BINARY_SENSOR:
            # Custom binary sensors have no device_class/domain filter at
            # all — every binary_sensor or sensor entity (except this
            # integration's own outputs) is offered, since the whole point
            # is supporting entities today's typed sections reject (#531).
            if entry.platform != DOMAIN:
                include_custom_binary_entities.append(entry.entity_id)

            device_class = entry.device_class
            original_device_class = entry.original_device_class

            # Check if entity contains "window" or "door" keyword in entity_id or friendly name
            has_window_keyword = _entity_contains_keyword(
                hass, entry.entity_id, "window"
            )
            has_door_keyword = _entity_contains_keyword(hass, entry.entity_id, "door")

            window_class = (BinarySensorDeviceClass.WINDOW,)
            is_window_candidate = (
                device_class in window_class
                or original_device_class in window_class
                or (
                    has_window_keyword
                    and not has_door_keyword
                    and (
                        device_class in door_window_classes
                        or original_device_class in door_window_classes
                    )
                )
            )
            is_door_candidate = (
                device_class in door_classes
                or original_device_class in door_classes
                or (
                    has_door_keyword
                    and (
                        device_class in door_keyword_classes
                        or original_device_class in door_keyword_classes
                    )
                )
                or (
                    not has_window_keyword
                    and (
                        BinarySensorDeviceClass.OPENING
                        in (device_class, original_device_class)
                    )
                )
            )

            if is_window_candidate:
                include_window_entities.append(entry.entity_id)
            if is_door_candidate:
                include_door_entities.append(entry.entity_id)

            # Exclude our own integration's sensors from motion selection
            # to prevent circular dependencies
            if entry.platform != DOMAIN:
                motion_classes = (
                    BinarySensorDeviceClass.MOTION,
                    BinarySensorDeviceClass.OCCUPANCY,
                    BinarySensorDeviceClass.PRESENCE,
                )
                if (
                    entry.device_class in motion_classes
                    or entry.original_device_class in motion_classes
                ):
                    include_motion_entities.append(entry.entity_id)

        # Filter environmental sensors to exclude weather entities
        elif entry.domain == Platform.SENSOR:
            # Skip weather entities
            if _is_weather_entity(entry.entity_id, entry.platform):
                continue

            device_class = entry.device_class
            original_device_class = entry.original_device_class

            # Include temperature sensors (excluding weather)
            temp_class = (SensorDeviceClass.TEMPERATURE,)
            if device_class in temp_class or original_device_class in temp_class:
                include_temperature_entities.append(entry.entity_id)

            # Include humidity sensors (excluding weather)
            humidity_classes = (SensorDeviceClass.HUMIDITY, SensorDeviceClass.MOISTURE)
            if (
                device_class in humidity_classes
                or original_device_class in humidity_classes
            ):
                include_humidity_entities.append(entry.entity_id)

            # Include pressure sensors (excluding weather)
            pressure_classes = (
                SensorDeviceClass.PRESSURE,
                SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            )
            if (
                device_class in pressure_classes
                or original_device_class in pressure_classes
            ):
                include_pressure_entities.append(entry.entity_id)

            # Include air quality sensors (excluding weather)
            aqi_class = (SensorDeviceClass.AQI,)
            if device_class in aqi_class or original_device_class in aqi_class:
                include_air_quality_entities.append(entry.entity_id)

            # Include PM2.5 sensors (excluding weather)
            pm25_class = (SensorDeviceClass.PM25,)
            if device_class in pm25_class or original_device_class in pm25_class:
                include_pm25_entities.append(entry.entity_id)

            # Include PM10 sensors (excluding weather)
            pm10_class = (SensorDeviceClass.PM10,)
            if device_class in pm10_class or original_device_class in pm10_class:
                include_pm10_entities.append(entry.entity_id)

            # Wi-Fi client-count sensors have no reliable device_class to
            # filter by, so offer every sensor-domain entity except this
            # integration's own output sensors (probability, priors, decay,
            # etc.) — selecting one of those would create a feedback loop.
            if entry.platform != DOMAIN:
                include_wifi_clients_entities.append(entry.entity_id)
                # `sensor.` entities can report discrete/string states too
                # (e.g. a HASS.Agent sensor reporting "on"/"off"), not just
                # numeric values, so they're valid custom-binary candidates
                # alongside custom-numeric ones.
                include_custom_binary_entities.append(entry.entity_id)
                include_custom_numeric_entities.append(entry.entity_id)

    # input_boolean helpers are on/off flags that a person or an automation
    # flips (a "showering" or "do not disturb" toggle), so they are natural
    # custom-binary inputs. They sit in neither the binary_sensor nor the
    # sensor domain, so the registry loop above never offered them. Discover
    # them via hass.states, like locks, so YAML-defined helpers without a
    # registry entry are offered too. Disabled registry entries are skipped:
    # a disabled helper no longer updates, so it would never give evidence.
    disabled_input_booleans = {
        entry.entity_id
        for entry in registry.entities.values()
        if entry.domain == "input_boolean" and entry.disabled
    }
    include_custom_binary_entities.extend(
        entity_id
        for entity_id in hass.states.async_entity_ids("input_boolean")
        if entity_id not in disabled_input_booleans
    )

    # Collect all cover entities (blinds, shades, garage doors, shutters, etc.)
    include_cover_entities = [
        entry.entity_id
        for entry in registry.entities.values()
        if entry.entity_id.startswith("cover.") and not entry.disabled
    ]

    # Collect all lock entities (smart locks, e.g. door locks). Locks don't
    # have meaningfully distinct device_class variants the way binary_sensor
    # door/window entities do, so just include the whole domain. Discover
    # via hass.states rather than the entity registry: entities without a
    # unique_id (some MQTT-configured locks, e.g.) have no registry entry
    # and would otherwise be silently excluded from selection. The registry
    # is still consulted, but only to filter out disabled entities.
    disabled_lock_entities = {
        entry.entity_id
        for entry in registry.entities.values()
        if entry.entity_id.startswith("lock.") and entry.disabled
    }
    include_lock_entities = [
        entity_id
        for entity_id in hass.states.async_entity_ids("lock")
        if entity_id not in disabled_lock_entities
    ]

    return {
        "appliance": include_appliance_entities,
        "button": include_button_entities,
        "window": include_window_entities,
        "door": include_door_entities,
        "lock": include_lock_entities,
        "cover": include_cover_entities,
        "temperature": include_temperature_entities,
        "humidity": include_humidity_entities,
        "pressure": include_pressure_entities,
        "air_quality": include_air_quality_entities,
        "pm25": include_pm25_entities,
        "pm10": include_pm10_entities,
        "motion": include_motion_entities,
        "wifi_clients": include_wifi_clients_entities,
        "custom_binary": include_custom_binary_entities,
        "custom_numeric": include_custom_numeric_entities,
    }


def _create_windows_and_doors_section_schema(
    defaults: dict[str, Any],
    door_entities: list[str],
    window_entities: list[str],
    cover_entities: list[str],
    lock_entities: list[str],
    door_state_options: list[SelectOptionDict],
    window_state_options: list[SelectOptionDict],
    cover_state_options: list[SelectOptionDict],
    lock_state_options: list[SelectOptionDict],
) -> vol.Schema:
    """Create schema for the combined windows, doors, locks, and covers section."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_DOOR_SENSORS, default=defaults.get(CONF_DOOR_SENSORS, [])
            ): EntitySelector(
                EntitySelectorConfig(include_entities=door_entities, multiple=True)
            ),
            vol.Optional(
                CONF_DOOR_ACTIVE_STATE,
                default=defaults.get(CONF_DOOR_ACTIVE_STATE, get_default_state("door")),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=door_state_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_DOOR,
                default=defaults.get(CONF_WEIGHT_DOOR, DEFAULT_WEIGHT_DOOR),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_LOCK_SENSORS, default=defaults.get(CONF_LOCK_SENSORS, [])
            ): EntitySelector(
                EntitySelectorConfig(include_entities=lock_entities, multiple=True)
            ),
            vol.Optional(
                CONF_LOCK_ACTIVE_STATE,
                default=defaults.get(CONF_LOCK_ACTIVE_STATE, get_default_state("lock")),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=lock_state_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_LOCK,
                default=defaults.get(CONF_WEIGHT_LOCK, DEFAULT_WEIGHT_LOCK),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_WINDOW_SENSORS, default=defaults.get(CONF_WINDOW_SENSORS, [])
            ): EntitySelector(
                EntitySelectorConfig(include_entities=window_entities, multiple=True)
            ),
            vol.Optional(
                CONF_WINDOW_ACTIVE_STATE,
                default=defaults.get(
                    CONF_WINDOW_ACTIVE_STATE, DEFAULT_WINDOW_ACTIVE_STATE
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=window_state_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_WINDOW,
                default=defaults.get(CONF_WEIGHT_WINDOW, DEFAULT_WEIGHT_WINDOW),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_COVER_SENSORS, default=defaults.get(CONF_COVER_SENSORS, [])
            ): EntitySelector(
                EntitySelectorConfig(include_entities=cover_entities, multiple=True)
            ),
            vol.Optional(
                CONF_COVER_ACTIVE_STATES,
                default=defaults.get(
                    CONF_COVER_ACTIVE_STATES, list(DEFAULT_COVER_ACTIVE_STATES)
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=cover_state_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=True,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_COVER,
                default=defaults.get(CONF_WEIGHT_COVER, DEFAULT_WEIGHT_COVER),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_media_section_schema(
    defaults: dict[str, Any], state_options: list[SelectOptionDict]
) -> vol.Schema:
    """Create schema for the media section."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_MEDIA_DEVICES, default=defaults.get(CONF_MEDIA_DEVICES, [])
            ): EntitySelector(
                EntitySelectorConfig(domain=Platform.MEDIA_PLAYER, multiple=True)
            ),
            vol.Optional(
                CONF_MEDIA_ACTIVE_STATES,
                default=defaults.get(
                    CONF_MEDIA_ACTIVE_STATES, DEFAULT_MEDIA_ACTIVE_STATES
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=state_options,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_MEDIA,
                default=defaults.get(CONF_WEIGHT_MEDIA, DEFAULT_WEIGHT_MEDIA),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_appliances_section_schema(
    defaults: dict[str, Any],
    include_entities: list[str],
    button_entities: list[str],
    state_options: list[SelectOptionDict],
) -> vol.Schema:
    """Create schema for the appliances section."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_APPLIANCES, default=defaults.get(CONF_APPLIANCES, [])
            ): EntitySelector(
                EntitySelectorConfig(include_entities=include_entities, multiple=True)
            ),
            vol.Optional(
                CONF_APPLIANCE_ACTIVE_STATES,
                default=defaults.get(
                    CONF_APPLIANCE_ACTIVE_STATES, DEFAULT_APPLIANCE_ACTIVE_STATES
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=state_options,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_APPLIANCE,
                default=defaults.get(CONF_WEIGHT_APPLIANCE, DEFAULT_WEIGHT_APPLIANCE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_BUTTON_SENSORS, default=defaults.get(CONF_BUTTON_SENSORS, [])
            ): EntitySelector(
                EntitySelectorConfig(include_entities=button_entities, multiple=True)
            ),
            vol.Optional(
                CONF_BUTTON_PULSE_DURATION,
                default=seconds_to_duration(
                    defaults.get(
                        CONF_BUTTON_PULSE_DURATION, DEFAULT_BUTTON_PULSE_DURATION
                    )
                ),
            ): DurationSelector(DurationSelectorConfig(enable_day=False)),
            vol.Optional(
                CONF_WEIGHT_BUTTON,
                default=defaults.get(CONF_WEIGHT_BUTTON, DEFAULT_WEIGHT_BUTTON),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_environmental_section_schema(
    defaults: dict[str, Any],
    temperature_entities: list[str],
    humidity_entities: list[str],
    pressure_entities: list[str],
    air_quality_entities: list[str],
    pm25_entities: list[str],
    pm10_entities: list[str],
) -> vol.Schema:
    """Create schema for the environmental section."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_ILLUMINANCE_SENSORS,
                default=defaults.get(CONF_ILLUMINANCE_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.ILLUMINANCE,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_HUMIDITY_SENSORS, default=defaults.get(CONF_HUMIDITY_SENSORS, [])
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=humidity_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_TEMPERATURE_SENSORS,
                default=defaults.get(CONF_TEMPERATURE_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=temperature_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_CO2_SENSORS,
                default=defaults.get(CONF_CO2_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.CO2,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_CO_SENSORS,
                default=defaults.get(CONF_CO_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.CO,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_SOUND_PRESSURE_SENSORS,
                default=defaults.get(CONF_SOUND_PRESSURE_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.SOUND_PRESSURE,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_PRESSURE_SENSORS,
                default=defaults.get(CONF_PRESSURE_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=pressure_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_AIR_QUALITY_SENSORS,
                default=defaults.get(CONF_AIR_QUALITY_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=air_quality_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_VOC_SENSORS,
                default=defaults.get(CONF_VOC_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=[
                        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
                        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
                    ],
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_PM25_SENSORS,
                default=defaults.get(CONF_PM25_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=pm25_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_PM10_SENSORS,
                default=defaults.get(CONF_PM10_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=pm10_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_ENVIRONMENTAL,
                default=defaults.get(
                    CONF_WEIGHT_ENVIRONMENTAL, DEFAULT_WEIGHT_ENVIRONMENTAL
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_power_section_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Create schema for the power section."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_POWER_SENSORS,
                default=defaults.get(CONF_POWER_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=[
                        SensorDeviceClass.POWER,
                        SensorDeviceClass.CURRENT,
                    ],
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_POWER,
                default=defaults.get(CONF_WEIGHT_POWER, DEFAULT_WEIGHT_POWER),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_wifi_clients_section_schema(
    defaults: dict[str, Any], wifi_clients_entities: list[str]
) -> vol.Schema:
    """Create schema for the Wi-Fi client-count section.

    Unlike power sensors, Wi-Fi client-count sensors (e.g. from the UniFi
    Network integration) have no reliable SensorDeviceClass to auto-filter
    by, so this offers every sensor-domain entity except this integration's
    own output sensors (see ``_get_include_entities``'s ``wifi_clients`` key)
    rather than a device_class-scanned include list.
    """
    return vol.Schema(
        {
            vol.Optional(
                CONF_WIFI_CLIENTS_SENSORS,
                default=defaults.get(CONF_WIFI_CLIENTS_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=wifi_clients_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_WIFI_CLIENTS,
                default=defaults.get(
                    CONF_WEIGHT_WIFI_CLIENTS, DEFAULT_WEIGHT_WIFI_CLIENTS
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_custom_section_schema(
    defaults: dict[str, Any],
    custom_binary_entities: list[str],
    custom_numeric_entities: list[str],
    custom_state_options: list[SelectOptionDict],
) -> vol.Schema:
    """Create schema for the custom entities section (#531).

    Unlike every other section, these have no domain/device_class filter
    at all — the whole point is supporting entities today's typed sections
    reject (e.g. an MQTT/HASS.Agent sensor with no matching device_class).
    Binary and numeric are separate InputTypes (not one flexible type)
    because the rest of the codebase classifies InputTypes statically as
    binary or numeric (DB storage, health checks, probability channel).
    """
    return vol.Schema(
        {
            vol.Optional(
                CONF_CUSTOM_BINARY_SENSORS,
                default=defaults.get(CONF_CUSTOM_BINARY_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=custom_binary_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_CUSTOM_BINARY_ACTIVE_STATES,
                default=defaults.get(
                    CONF_CUSTOM_BINARY_ACTIVE_STATES,
                    list(DEFAULT_CUSTOM_BINARY_ACTIVE_STATES),
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=custom_state_options,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_WEIGHT_CUSTOM_BINARY,
                default=defaults.get(
                    CONF_WEIGHT_CUSTOM_BINARY, DEFAULT_WEIGHT_CUSTOM_BINARY
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_CUSTOM_NUMERIC_SENSORS,
                default=defaults.get(CONF_CUSTOM_NUMERIC_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(
                    include_entities=custom_numeric_entities,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_CUSTOM_NUMERIC_ACTIVE_MIN,
                default=defaults.get(
                    CONF_CUSTOM_NUMERIC_ACTIVE_MIN, DEFAULT_CUSTOM_NUMERIC_ACTIVE_MIN
                ),
            ): NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_CUSTOM_NUMERIC_ACTIVE_MAX,
                default=defaults.get(
                    CONF_CUSTOM_NUMERIC_ACTIVE_MAX, DEFAULT_CUSTOM_NUMERIC_ACTIVE_MAX
                ),
            ): NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_WEIGHT_CUSTOM_NUMERIC,
                default=defaults.get(
                    CONF_WEIGHT_CUSTOM_NUMERIC, DEFAULT_WEIGHT_CUSTOM_NUMERIC
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=WEIGHT_MIN,
                    max=WEIGHT_MAX,
                    step=WEIGHT_STEP,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _create_wasp_in_box_section_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Create schema for the wasp in box section."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_WASP_ENABLED, default=defaults.get(CONF_WASP_ENABLED, False)
            ): BooleanSelector(),
            vol.Optional(
                CONF_WASP_MOTION_TIMEOUT,
                default=seconds_to_duration(
                    defaults.get(CONF_WASP_MOTION_TIMEOUT, DEFAULT_WASP_MOTION_TIMEOUT)
                ),
            ): DurationSelector(DurationSelectorConfig(enable_day=False)),
            vol.Optional(
                CONF_WASP_WEIGHT,
                default=defaults.get(CONF_WASP_WEIGHT, DEFAULT_WASP_WEIGHT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="weight",
                )
            ),
            vol.Optional(
                CONF_WASP_MAX_DURATION,
                default=seconds_to_duration(
                    defaults.get(CONF_WASP_MAX_DURATION, DEFAULT_WASP_MAX_DURATION)
                ),
            ): DurationSelector(DurationSelectorConfig(enable_day=True)),
            vol.Optional(
                CONF_WASP_VERIFICATION_DELAY,
                default=seconds_to_duration(
                    defaults.get(
                        CONF_WASP_VERIFICATION_DELAY, DEFAULT_WASP_VERIFICATION_DELAY
                    )
                ),
            ): DurationSelector(DurationSelectorConfig(enable_day=False)),
        }
    )


class _ExclusionFields(NamedTuple):
    """Voluptuous schema entries for shared entity, device, and integration exclusions."""

    manufacturers: tuple[vol.Marker, Any]
    models: tuple[vol.Marker, Any]
    entities: tuple[vol.Marker, Any]
    integrations: tuple[vol.Marker, Any]

    def as_schema_dict(self) -> dict[vol.Marker, Any]:
        """Return all four exclusion fields as a Voluptuous field mapping."""
        return dict([self.manufacturers, self.models, self.entities, self.integrations])


def _create_exclusion_fields(
    defaults: dict[str, Any],
    hass: HomeAssistant | None,
) -> _ExclusionFields:
    """Create the shared manufacturer, model, entity, and integration exclusion fields."""
    return _ExclusionFields(
        manufacturers=(
            vol.Optional(
                CONF_EXCLUDED_MANUFACTURERS,
                default=list(
                    defaults.get(
                        CONF_EXCLUDED_MANUFACTURERS, DEFAULT_EXCLUDED_MANUFACTURERS
                    )
                    or []
                ),
            ),
            _multi_custom_list_selector(
                _get_excluded_device_attribute_options(
                    hass,
                    ATTR_MANUFACTURER,
                    CONF_EXCLUDED_MANUFACTURERS,
                    defaults,
                )
            ),
        ),
        models=(
            vol.Optional(
                CONF_EXCLUDED_MODELS,
                default=list(
                    defaults.get(CONF_EXCLUDED_MODELS, DEFAULT_EXCLUDED_MODELS) or []
                ),
            ),
            _multi_custom_list_selector(
                _get_excluded_device_attribute_options(
                    hass, ATTR_MODEL, CONF_EXCLUDED_MODELS, defaults
                )
            ),
        ),
        entities=(
            vol.Optional(
                CONF_EXCLUDED_SENSORS,
                default=list(defaults.get(CONF_EXCLUDED_SENSORS) or []),
            ),
            EntitySelector(EntitySelectorConfig(multiple=True)),
        ),
        integrations=(
            vol.Optional(
                CONF_EXCLUDED_INTEGRATIONS,
                default=list(defaults.get(CONF_EXCLUDED_INTEGRATIONS) or []),
            ),
            _multi_custom_list_selector(
                _get_excluded_integration_options(hass, defaults)
            ),
        ),
    )


def _build_tri_state_selector(
    *,
    options: list[str],
    translation_key: str,
) -> Selector[Any]:
    """Build a dropdown selector for a tri-state area override."""
    return cast(
        "Selector[Any]",
        SelectSelector(
            SelectSelectorConfig(
                options=options,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=translation_key,
            )
        ),
    )


def _create_basics_step_schema(
    *,
    is_editing: bool = False,
    adjacent_options: list[SelectOptionDict] | None = None,
    current: dict[str, Any] | None = None,
    hass: HomeAssistant | None = None,
) -> dict[vol.Marker, Any]:
    """Create schema for wizard step 1: area selection and purpose.

    Args:
        is_editing: True if editing an existing area (skips area selector).
        adjacent_options: Other areas in this entry available as adjacency
            choices. Each option is `{"value": area_id, "label": area_name}`.
            When None or empty, the adjacency field is omitted (e.g. the
            first area being added has no neighbours to pick from).
        current: The area's saved config when editing. Its purpose and
            adjacency become the fields' defaults: the flow manager fills a
            default into any submission that omits the field, so a fixed
            default silently reset an existing area's purpose to "social"
            and cleared its adjacency.
        hass: Optional Home Assistant instance used to pre-populate available
            integrations and devices for exclusion.
    """
    current = current or {}
    fields: dict[vol.Marker, Any] = {}
    if not is_editing:
        fields[vol.Required(CONF_AREA_ID)] = AreaSelector()
    purpose_default = current.get(CONF_PURPOSE) or DEFAULT_PURPOSE
    fields[vol.Optional(CONF_PURPOSE, default=purpose_default)] = SelectSelector(
        SelectSelectorConfig(
            options=cast("list[SelectOptionDict]", get_purpose_options()),
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    fields[
        vol.Optional(
            CONF_AUTO_DISCOVER_SENSORS,
            default=is_auto_discovery_enabled(current),
        )
    ] = BooleanSelector()
    fields[vol.Optional(SECTION_AUTO_DISCOVERY_TYPES)] = section(
        vol.Schema(
            {
                vol.Optional(
                    CONF_AUTO_DISCOVER_DOMAINS,
                    default=_get_ordered_auto_discover_types(current),
                ): _sensor_types_list_selector(_get_auto_discover_sensor_type_options())
            }
        ),
        _section_options(collapsed=True),
    )
    group_default = normalize_group_expansion_mode(current.get(CONF_EXPAND_GROUPS))
    fields[vol.Optional(CONF_EXPAND_GROUPS, default=group_default.value)] = (
        _build_tri_state_selector(
            options=[mode.value for mode in GroupExpansionMode],
            translation_key=_TRANSLATION_GROUP_EXPANSION,
        )
    )
    exclusion_options = [mode.value for mode in ExclusionMode]
    for rule in DISCOVERY_EXCLUSION_RULES:
        exclusion_default = normalize_exclusion_mode(current.get(rule.config_key))
        fields[vol.Optional(rule.config_key, default=exclusion_default.value)] = (
            _build_tri_state_selector(
                options=exclusion_options,
                translation_key=rule.translation_key,
            )
        )
    exclusion_fields = _create_exclusion_fields(current, hass)
    fields[vol.Optional(SECTION_AREA_EXCLUSIONS)] = section(
        vol.Schema(exclusion_fields.as_schema_dict()),
        _section_options(collapsed=True),
    )
    if adjacent_options:
        adjacent_default = list(current.get(CONF_ADJACENT_AREAS) or [])
        fields[vol.Optional(CONF_ADJACENT_AREAS, default=adjacent_default)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=adjacent_options,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        )
    return fields


def _create_motion_step_schema(
    hass: HomeAssistant,
    include_entities: dict[str, list[str]] | None = None,
    auto_added_entities: list[str] | None = None,
) -> dict[vol.Marker, Any]:
    """Create schema for wizard step 2: motion sensor configuration."""
    if include_entities is None:
        include_entities = _get_include_entities(hass)

    fields: dict[vol.Marker, Any] = {
        vol.Optional(CONF_MOTION_SENSORS, default=[]): EntitySelector(
            EntitySelectorConfig(
                include_entities=include_entities["motion"],
                multiple=True,
            )
        ),
        vol.Optional(CONF_WEIGHT_MOTION, default=DEFAULT_WEIGHT_MOTION): NumberSelector(
            NumberSelectorConfig(
                min=WEIGHT_MIN,
                max=WEIGHT_MAX,
                step=WEIGHT_STEP,
                mode=NumberSelectorMode.SLIDER,
                unit_of_measurement="weight",
            )
        ),
        vol.Optional(
            CONF_MOTION_TIMEOUT,
            default=seconds_to_duration(DEFAULT_MOTION_TIMEOUT),
        ): DurationSelector(DurationSelectorConfig(enable_day=False)),
        vol.Optional(
            CONF_MOTION_PROB_GIVEN_TRUE,
            default=DEFAULT_MOTION_PROB_GIVEN_TRUE,
        ): NumberSelector(
            NumberSelectorConfig(
                min=MIN_PROBABILITY,
                max=MAX_PROBABILITY,
                step=0.01,
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_MOTION_PROB_GIVEN_FALSE,
            default=DEFAULT_MOTION_PROB_GIVEN_FALSE,
        ): NumberSelector(
            NumberSelectorConfig(
                min=0.001,
                max=MAX_PROBABILITY,
                step=0.001,
                mode=NumberSelectorMode.BOX,
            )
        ),
    }

    result: dict[vol.Marker, Any] = {}
    if auto_added_entities:
        result[vol.Required(AUTO_ADDED_SECTION)] = section(
            vol.Schema(
                {
                    vol.Optional(
                        AUTO_ADDED_ENTITIES_FIELD,
                        default=auto_added_entities,
                    ): _read_only_entity_selector()
                }
            )
        )
    result[vol.Required(EXPLICIT_SECTION)] = section(vol.Schema(fields))
    return result


def _create_sensors_step_schema(
    hass: HomeAssistant,
    include_entities: dict[str, list[str]] | None = None,
    groups: tuple[str, ...] | list[str] | None = None,
    auto_added_entities: dict[str, list[str]] | None = None,
) -> dict[vol.Marker, Any]:
    """Create schema for wizard step 3: additional sensors with sections.

    Args:
        hass: Home Assistant instance.
        include_entities: Pre-computed candidate entities per channel.
        groups: Subset of ``SENSOR_GROUPS`` to render. ``None`` renders all
            groups (the add wizard); a single group renders the edit hub spoke.
        auto_added_entities: Read-only discovered entity IDs per group.
    """
    if include_entities is None:
        include_entities = _get_include_entities(hass)
    selected = tuple(groups) if groups else SENSOR_GROUPS

    defaults: dict[str, Any] = {}
    door_state_options = _get_state_select_options("door")
    lock_state_options = _get_state_select_options("lock")
    media_state_options = _get_state_select_options("media")
    window_state_options = _get_state_select_options("window")
    cover_state_options = _get_state_select_options("cover")
    appliance_state_options = _get_state_select_options("appliance")
    custom_state_options = _get_state_select_options("custom")

    builders: dict[str, Any] = {
        "windows_and_doors": lambda: _create_windows_and_doors_section_schema(
            defaults,
            include_entities["door"],
            include_entities["window"],
            include_entities["cover"],
            include_entities["lock"],
            cast("list[SelectOptionDict]", door_state_options),
            cast("list[SelectOptionDict]", window_state_options),
            cast("list[SelectOptionDict]", cover_state_options),
            cast("list[SelectOptionDict]", lock_state_options),
        ),
        "media": lambda: _create_media_section_schema(
            defaults, cast("list[SelectOptionDict]", media_state_options)
        ),
        "appliances": lambda: _create_appliances_section_schema(
            defaults,
            include_entities["appliance"],
            include_entities["button"],
            cast("list[SelectOptionDict]", appliance_state_options),
        ),
        "environmental": lambda: _create_environmental_section_schema(
            defaults,
            include_entities["temperature"],
            include_entities["humidity"],
            include_entities["pressure"],
            include_entities["air_quality"],
            include_entities["pm25"],
            include_entities["pm10"],
        ),
        "power": lambda: _create_power_section_schema(defaults),
        "wifi_clients": lambda: _create_wifi_clients_section_schema(
            defaults, include_entities["wifi_clients"]
        ),
        "custom": lambda: _create_custom_section_schema(
            defaults,
            include_entities["custom_binary"],
            include_entities["custom_numeric"],
            cast("list[SelectOptionDict]", custom_state_options),
        ),
    }
    explicit_fields: dict[vol.Marker, Any] = {}
    for group in selected:
        if group_ids := (auto_added_entities or {}).get(group):
            explicit_fields[
                vol.Optional(
                    f"{AUTO_ADDED_FIELD_PREFIX}{group}",
                    default=group_ids,
                )
            ] = _read_only_entity_selector()
        explicit_fields.update(builders[group]().schema)
    return {
        vol.Required(EXPLICIT_SECTION): section(
            vol.Schema(explicit_fields), _section_options(collapsed=False)
        ),
    }


def _closed_door_hold_default(area: dict[str, Any]) -> bool:
    """The closed-door hold's form default for an area (#558).

    An area saved before the setting existed follows its Wasp in Box
    setting, as the loader does. A new area defaults it on for the
    bathroom purpose, the room most often with one way in.
    """
    if CONF_CLOSED_DOOR_HOLD in area:
        return bool(area[CONF_CLOSED_DOOR_HOLD])
    if CONF_WASP_ENABLED in area:
        return bool(area[CONF_WASP_ENABLED])
    return area.get(CONF_PURPOSE) == AreaPurpose.BATHROOM


def _create_behavior_step_schema(
    defaults: dict[str, Any] | None = None,
) -> dict[vol.Marker, Any]:
    """Create schema for wizard step 4: thresholds, decay, and wasp-in-box."""
    defaults = defaults or {}

    fields: dict[vol.Marker, Any] = {
        vol.Optional(CONF_THRESHOLD, default=DEFAULT_THRESHOLD): NumberSelector(
            NumberSelectorConfig(
                min=THRESHOLD_MIN,
                max=THRESHOLD_MAX,
                step=THRESHOLD_STEP,
                mode=NumberSelectorMode.SLIDER,
            )
        ),
        vol.Optional(
            CONF_DECAY_ENABLED, default=DEFAULT_DECAY_ENABLED
        ): BooleanSelector(),
        vol.Optional(
            CONF_EXCLUDE_FROM_ALL_AREAS, default=DEFAULT_EXCLUDE_FROM_ALL_AREAS
        ): BooleanSelector(),
        vol.Optional(
            CONF_CLOSED_DOOR_HOLD, default=_closed_door_hold_default(defaults)
        ): BooleanSelector(),
        vol.Optional(
            CONF_DECAY_HALF_LIFE,
            default=seconds_to_duration(DEFAULT_DECAY_HALF_LIFE),
        ): _duration_selector(),
        vol.Optional(
            CONF_SLEEP_DECAY_HALF_LIFE,
            default=seconds_to_duration(DEFAULT_SLEEP_DECAY_HALF_LIFE),
        ): _duration_selector(),
        vol.Optional(
            CONF_MIN_PRIOR_OVERRIDE,
            default=DEFAULT_MIN_PRIOR_OVERRIDE,
        ): NumberSelector(
            NumberSelectorConfig(
                min=0.0,
                max=1.0,
                step=0.01,
                mode=NumberSelectorMode.SLIDER,
                unit_of_measurement="probability",
            )
        ),
        vol.Required("wasp_in_box"): section(
            _create_wasp_in_box_section_schema(defaults),
            {"collapsed": True},
        ),
    }

    return fields


def _nest_config_for_sections(flat_config: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Group flat area config by sensor type for form suggested values.

    Args:
        flat_config: Flat area configuration dictionary

    Returns:
        A dictionary whose keys are sensor groups and whose values contain
        that group's configured fields.
    """
    nested: dict[str, Any] = {}

    # Root-level fields
    if CONF_AREA_ID in flat_config:
        nested[CONF_AREA_ID] = flat_config[CONF_AREA_ID]
    if CONF_PURPOSE in flat_config:
        nested[CONF_PURPOSE] = flat_config[CONF_PURPOSE]

    # Motion section
    motion: dict[str, Any] = {}
    for key in (
        CONF_MOTION_SENSORS,
        CONF_WEIGHT_MOTION,
        CONF_MOTION_TIMEOUT,
        CONF_MOTION_PROB_GIVEN_TRUE,
        CONF_MOTION_PROB_GIVEN_FALSE,
    ):
        if key in flat_config:
            val = flat_config[key]
            # Convert seconds to duration for DurationSelector fields
            if key in DURATION_FIELDS:
                val = seconds_to_duration(val)
            motion[key] = val
    if motion:
        nested["motion"] = motion

    # Windows and doors section
    windows_and_doors: dict[str, Any] = {}
    for key in (
        CONF_DOOR_SENSORS,
        CONF_DOOR_ACTIVE_STATE,
        CONF_WEIGHT_DOOR,
        CONF_LOCK_SENSORS,
        CONF_LOCK_ACTIVE_STATE,
        CONF_WEIGHT_LOCK,
        CONF_WINDOW_SENSORS,
        CONF_WINDOW_ACTIVE_STATE,
        CONF_WEIGHT_WINDOW,
        CONF_COVER_SENSORS,
        CONF_COVER_ACTIVE_STATES,
        CONF_WEIGHT_COVER,
    ):
        if key in flat_config:
            windows_and_doors[key] = flat_config[key]
    if windows_and_doors:
        nested["windows_and_doors"] = windows_and_doors

    # Media section
    media: dict[str, Any] = {}
    for key in (CONF_MEDIA_DEVICES, CONF_MEDIA_ACTIVE_STATES, CONF_WEIGHT_MEDIA):
        if key in flat_config:
            media[key] = flat_config[key]
    if media:
        nested["media"] = media

    # Appliances section
    appliances: dict[str, Any] = {}
    for key in (
        CONF_APPLIANCES,
        CONF_APPLIANCE_ACTIVE_STATES,
        CONF_WEIGHT_APPLIANCE,
        CONF_BUTTON_SENSORS,
        CONF_BUTTON_PULSE_DURATION,
        CONF_WEIGHT_BUTTON,
    ):
        if key in flat_config:
            val = flat_config[key]
            if key in DURATION_FIELDS:
                val = seconds_to_duration(val)
            appliances[key] = val
    if appliances:
        nested["appliances"] = appliances

    # Environmental section
    environmental: dict[str, Any] = {}
    for key in (
        CONF_ILLUMINANCE_SENSORS,
        CONF_HUMIDITY_SENSORS,
        CONF_TEMPERATURE_SENSORS,
        CONF_CO2_SENSORS,
        CONF_CO_SENSORS,
        CONF_SOUND_PRESSURE_SENSORS,
        CONF_PRESSURE_SENSORS,
        CONF_AIR_QUALITY_SENSORS,
        CONF_VOC_SENSORS,
        CONF_PM25_SENSORS,
        CONF_PM10_SENSORS,
        CONF_WEIGHT_ENVIRONMENTAL,
    ):
        if key in flat_config:
            environmental[key] = flat_config[key]
    if environmental:
        nested["environmental"] = environmental

    # Power section
    power: dict[str, Any] = {}
    for key in (CONF_POWER_SENSORS, CONF_WEIGHT_POWER):
        if key in flat_config:
            power[key] = flat_config[key]
    if power:
        nested["power"] = power

    # Wi-Fi clients section
    wifi_clients: dict[str, Any] = {}
    for key in (CONF_WIFI_CLIENTS_SENSORS, CONF_WEIGHT_WIFI_CLIENTS):
        if key in flat_config:
            wifi_clients[key] = flat_config[key]
    if wifi_clients:
        nested["wifi_clients"] = wifi_clients

    # Custom entities section (binary + numeric, unfiltered — #531)
    custom: dict[str, Any] = {}
    for key in (
        CONF_CUSTOM_BINARY_SENSORS,
        CONF_CUSTOM_BINARY_ACTIVE_STATES,
        CONF_WEIGHT_CUSTOM_BINARY,
        CONF_CUSTOM_NUMERIC_SENSORS,
        CONF_CUSTOM_NUMERIC_ACTIVE_MIN,
        CONF_CUSTOM_NUMERIC_ACTIVE_MAX,
        CONF_WEIGHT_CUSTOM_NUMERIC,
    ):
        if key in flat_config:
            custom[key] = flat_config[key]
    if custom:
        nested["custom"] = custom

    # Wasp in box section
    wasp: dict[str, Any] = {}
    for key in (
        CONF_WASP_ENABLED,
        CONF_WASP_MOTION_TIMEOUT,
        CONF_WASP_WEIGHT,
        CONF_WASP_MAX_DURATION,
        CONF_WASP_VERIFICATION_DELAY,
    ):
        if key in flat_config:
            val = flat_config[key]
            if key in DURATION_FIELDS:
                val = seconds_to_duration(val)
            wasp[key] = val
    if wasp:
        nested["wasp_in_box"] = wasp

    # Parameters section
    parameters: dict[str, Any] = {}
    for key in (
        CONF_THRESHOLD,
        CONF_DECAY_ENABLED,
        CONF_DECAY_HALF_LIFE,
        CONF_SLEEP_DECAY_HALF_LIFE,
        CONF_MIN_PRIOR_OVERRIDE,
    ):
        if key in flat_config:
            val = flat_config[key]
            if key in DURATION_FIELDS:
                val = seconds_to_duration(val)
            parameters[key] = val
    if parameters:
        nested["parameters"] = parameters

    return nested


def _draft_to_suggested(draft: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    """Extract suggested values from draft, converting duration fields.

    Args:
        draft: Flat area configuration draft
        keys: Set of field keys to extract

    Returns:
        Dictionary of suggested values with durations converted for display
    """
    suggested: dict[str, Any] = {}
    for key in keys:
        if key in draft:
            val = draft[key]
            if key in DURATION_FIELDS:
                val = seconds_to_duration(val)
            suggested[key] = val
    return suggested


def _strip_excluded_sensors_from_draft(
    draft: dict[str, Any], excluded: set[str]
) -> dict[str, Any]:
    """Return updated sensor list entries with excluded entities removed."""
    if not excluded:
        return {}
    stripped: dict[str, Any] = {}
    for key in ALL_AREA_SENSOR_KEYS:
        existing = draft.get(key)
        if isinstance(existing, list):
            items = cast("list[Any]", existing)
            if any(item in excluded for item in items):
                stripped[key] = [item for item in items if item not in excluded]
    return stripped


def _normalize_basics_submission(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten basics form input and map discovery sensor types to config keys."""
    flattened = flatten_sectioned_input(user_input)
    if CONF_AUTO_DISCOVER_DOMAINS in flattened:
        flattened[CONF_AUTO_DISCOVER_DOMAINS] = _sensor_types_to_discovery_domains(
            flattened[CONF_AUTO_DISCOVER_DOMAINS] or []
        )
    return flattened


def _discover_for_sync(
    hass: HomeAssistant | None,
    draft: dict[str, Any],
    *,
    excluded_devices: set[str],
    global_options: dict[str, Any],
) -> dict[str, list[str]]:
    """Run area discovery for ``_sync_discovered_and_excluded`` when enabled."""
    if not hass or not is_auto_discovery_enabled(draft) or not draft.get(CONF_AREA_ID):
        return {}
    enabled_domains = get_enabled_discovery_domains(draft)
    if not enabled_domains:
        return {}
    excluded_entities = (
        collect_excluded_sensor_ids(
            draft.get(CONF_EXCLUDED_SENSORS),
            global_options,
        )
        | excluded_devices
    )
    return discover_area_sensors(
        hass,
        draft[CONF_AREA_ID],
        **build_area_discovery_kwargs(
            draft,
            enabled_domains=enabled_domains,
            excluded_entities=excluded_entities,
            global_options=global_options,
        ),
    )


def _reconcile_sensor_key_selection(
    *,
    chosen: list[str],
    eligible_list: list[str],
    previous_auto: set[str],
    previous_selected: list[str],
    excluded: Collection[str],
    excluded_devices: set[str],
) -> tuple[list[str], list[str], set[str]]:
    """Separate explicit selections from auto-added entities for one sensor key."""
    eligible = set(eligible_list)
    excluded_set = set(excluded)
    previous_explicit = set(previous_selected) - previous_auto
    re_included: set[str] = set()
    explicit_ids: list[str] = []
    for entity_id in chosen:
        if entity_id in excluded_devices:
            continue
        if entity_id in excluded_set:
            re_included.add(entity_id)
        if entity_id in previous_explicit or entity_id not in eligible:
            explicit_ids.append(entity_id)

    effective_excluded = excluded_set - re_included
    auto_ids = [
        entity_id
        for entity_id in eligible_list
        if entity_id not in explicit_ids and entity_id not in effective_excluded
    ]
    return list(dict.fromkeys([*explicit_ids, *auto_ids])), auto_ids, re_included


def _sync_discovered_and_excluded(
    hass: HomeAssistant | None,
    draft: dict[str, Any],
    submitted: dict[str, Any],
    sensor_keys: tuple[str, ...],
    global_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sync sensor selections while preserving auto-added provenance."""
    updated = dict(submitted)
    tracked_auto = parse_tracked_auto_sensors(draft)
    global_options = global_options or {}

    excluded_devices = resolve_excluded_device_entity_ids(hass, draft, global_options)
    discovered = _discover_for_sync(
        hass,
        draft,
        excluded_devices=excluded_devices,
        global_options=global_options,
    )

    updated_auto = {
        key: entity_ids
        for key, entity_ids in tracked_auto.items()
        if key not in sensor_keys
    }
    excluded = list(dict.fromkeys(draft.get(CONF_EXCLUDED_SENSORS) or []))
    for key in sensor_keys:
        if key not in updated:
            continue
        merged, auto_ids, re_included = _reconcile_sensor_key_selection(
            chosen=list(dict.fromkeys(updated.get(key) or [])),
            eligible_list=discovered.get(key, []),
            previous_auto=set(tracked_auto.get(key, ())),
            previous_selected=draft.get(key) or [],
            excluded=excluded,
            excluded_devices=excluded_devices,
        )
        if re_included:
            excluded = [
                entity_id for entity_id in excluded if entity_id not in re_included
            ]
        updated[key] = merged
        if auto_ids:
            updated_auto[key] = auto_ids

    updated[CONF_AUTO_ADDED_SENSORS] = updated_auto
    if CONF_EXCLUDED_SENSORS in draft or excluded != draft.get(
        CONF_EXCLUDED_SENSORS, []
    ):
        updated[CONF_EXCLUDED_SENSORS] = excluded
    return updated


def _explicit_sensor_config(
    config: dict[str, Any], sensor_keys: tuple[str, ...]
) -> dict[str, Any]:
    """Return configured sensor values excluding tracked automatic additions."""
    tracked_auto = parse_tracked_auto_sensors(config)
    explicit = dict(config)
    for key in sensor_keys:
        selected = config.get(key)
        automatic_ids = set(tracked_auto.get(key, ()))
        if isinstance(selected, list):
            explicit[key] = [
                entity_id
                for entity_id in cast("list[Any]", selected)
                if entity_id not in automatic_ids
            ]
    return explicit


def _auto_added_sensor_ids(
    config: dict[str, Any],
    sensor_keys: tuple[str, ...],
) -> list[str]:
    """Return entity IDs that discovery added for the requested sensor keys."""
    tracked_auto = parse_tracked_auto_sensors(config)
    entity_ids: list[str] = []
    for key in sensor_keys:
        selected = config.get(key)
        automatic_ids = set(tracked_auto.get(key, ()))
        if not isinstance(selected, list) or not automatic_ids:
            continue
        entity_ids.extend(
            entity_id
            for entity_id in cast("list[Any]", selected)
            if isinstance(entity_id, str)
            and entity_id in automatic_ids
            and entity_id not in entity_ids
        )
    return entity_ids


def _editable_form_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten form sections and discard read-only automatic-sensor fields."""
    return _editable_section_input(flatten_sectioned_input(user_input))


def _editable_section_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Return submitted section values without read-only discovery summaries."""
    return {
        key: value
        for key, value in user_input.items()
        if not key.startswith(AUTO_ADDED_FIELD_PREFIX)
    }


def _resolve_area_id_to_name(hass: HomeAssistant, area_id: str) -> str:
    """Resolve area ID to area name for display.

    Args:
        hass: Home Assistant instance
        area_id: Home Assistant area ID

    Returns:
        Area name from Home Assistant registry

    Raises:
        ValueError: If area ID doesn't exist in registry
    """
    registry = ar.async_get(hass)
    area_entry = registry.async_get_area(area_id)
    if not area_entry:
        raise ValueError(
            f"Area ID '{area_id}' not found in Home Assistant area registry"
        )
    return area_entry.name


def _get_purpose_display_name(purpose: str) -> str:
    """Get display name for a purpose value.

    Args:
        purpose: Purpose enum value string

    Returns:
        Human-readable purpose name
    """
    return Purpose.display_name(purpose)


def _find_area_by_sanitized_id(
    areas: list[dict[str, Any]], sanitized_id: str
) -> dict[str, Any] | None:
    """Find an area by matching sanitized area ID.

    Args:
        areas: List of area configurations
        sanitized_id: Sanitized area ID to find

    Returns:
        Area configuration dict if found, None otherwise
    """
    for area in areas:
        area_id = area.get(CONF_AREA_ID)
        if not area_id:
            continue
        area_sanitized = area_id.replace(" ", "_").replace("/", "_")
        if area_sanitized == sanitized_id:
            return area
    return None


def _build_area_description_placeholders(
    area_config: dict[str, Any],
    area_id: str,
    hass: HomeAssistant | None = None,
    global_options: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build description placeholders for the area hub menus.

    Every value is a string so it can be substituted into ``strings.json``
    step descriptions and ``menu_option_descriptions``.

    Args:
        area_config: Area configuration dictionary
        area_id: Area ID
        hass: Home Assistant instance (optional, for resolving area names)
        global_options: Integration-wide discovery exclusions, when available

    Returns:
        Dictionary of placeholders for form/menu descriptions
    """

    if hass:
        area_config = resolve_area_sensors(hass, area_config, global_options)

    def _name(some_area_id: str) -> str:
        if hass:
            with contextlib.suppress(ValueError):
                return _resolve_area_id_to_name(hass, some_area_id)
        return some_area_id

    def _count(key: str) -> str:
        return str(len(area_config.get(key) or []))

    purpose = area_config.get(CONF_PURPOSE, DEFAULT_PURPOSE)
    adjacent_ids = normalize_adjacent_areas(area_config.get(CONF_ADJACENT_AREAS))
    adjacent = ", ".join(_name(a) for a in adjacent_ids) if adjacent_ids else "none"

    decay_enabled = area_config.get(CONF_DECAY_ENABLED, DEFAULT_DECAY_ENABLED)
    half_life = int(area_config.get(CONF_DECAY_HALF_LIFE, DEFAULT_DECAY_HALF_LIFE) or 0)
    if not decay_enabled:
        decay = "off"
    elif half_life == 0:
        decay = "on (purpose default)"
    else:
        decay = f"on ({_format_seconds(half_life)})"

    environmental_count = sum(
        len(area_config.get(key) or []) for key in ENVIRONMENTAL_SENSOR_KEYS
    )
    threshold = area_config.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)

    return {
        "area_name": _name(area_id),
        "purpose": _get_purpose_display_name(purpose),
        "adjacent": adjacent,
        "motion_count": _count(CONF_MOTION_SENSORS),
        "weight_motion": str(
            area_config.get(CONF_WEIGHT_MOTION, DEFAULT_WEIGHT_MOTION)
        ),
        "motion_timeout": _format_seconds(
            area_config.get(CONF_MOTION_TIMEOUT, DEFAULT_MOTION_TIMEOUT)
        ),
        "media_count": _count(CONF_MEDIA_DEVICES),
        "door_count": _count(CONF_DOOR_SENSORS),
        "lock_count": _count(CONF_LOCK_SENSORS),
        "window_count": _count(CONF_WINDOW_SENSORS),
        "cover_count": _count(CONF_COVER_SENSORS),
        "appliance_count": _count(CONF_APPLIANCES),
        "button_count": _count(CONF_BUTTON_SENSORS),
        "environmental_count": str(environmental_count),
        "power_count": _count(CONF_POWER_SENSORS),
        "wifi_count": _count(CONF_WIFI_CLIENTS_SENSORS),
        "custom_count": str(
            len(area_config.get(CONF_CUSTOM_BINARY_SENSORS) or [])
            + len(area_config.get(CONF_CUSTOM_NUMERIC_SENSORS) or [])
        ),
        "threshold": str(
            int(threshold) if float(threshold).is_integer() else threshold
        ),
        "decay": decay,
        "wasp": "on" if area_config.get(CONF_WASP_ENABLED, False) else "off",
    }


def _get_area_summary_info(area: dict[str, Any]) -> str:
    """Get formatted summary information for an area.

    Args:
        area: Area configuration dictionary

    Returns:
        Formatted string with purpose, sensor count, and threshold
    """
    purpose = area.get(CONF_PURPOSE, DEFAULT_PURPOSE)
    purpose_name = _get_purpose_display_name(purpose)

    # Count sensors
    motion_count = len(area.get(CONF_MOTION_SENSORS, []))
    media_count = len(area.get(CONF_MEDIA_DEVICES, []))
    door_count = len(area.get(CONF_DOOR_SENSORS, []))
    lock_count = len(area.get(CONF_LOCK_SENSORS, []))
    window_count = len(area.get(CONF_WINDOW_SENSORS, []))
    appliance_count = len(area.get(CONF_APPLIANCES, []))
    total_sensors = (
        motion_count
        + media_count
        + door_count
        + lock_count
        + window_count
        + appliance_count
    )

    threshold = area.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)

    return (
        f"Purpose: {purpose_name} • {total_sensors} sensors • Threshold: {threshold}%"
    )


def _handle_step_error(err: Exception) -> str:
    """Handle step errors and convert to user-friendly error message.

    Args:
        err: Exception that occurred during step processing

    Returns:
        Error message string for display to user
    """
    if isinstance(err, HomeAssistantError):
        _LOGGER.error("Validation error: %s", err)
        return str(err)
    if isinstance(err, vol.Invalid):
        _LOGGER.error("Validation error: %s", err)
        return str(err)
    # ValueError, KeyError, TypeError
    _LOGGER.error("Unexpected error: %s", err)
    return "unknown"


def _create_area_selector_schema(
    areas: list[dict[str, Any]],
    hass: HomeAssistant | None = None,
    global_options: dict[str, Any] | None = None,
) -> vol.Schema:
    """Create schema for area selection step.

    Args:
        areas: List of configured areas
        hass: Home Assistant instance (optional, for resolving area names)
        global_options: Integration-wide discovery exclusions, when available

    Returns:
        Schema with SelectSelector in LIST mode (radio buttons) for area selection
    """
    # Ensure areas is a list
    if not isinstance(areas, list):
        areas = []

    options: list[SelectOptionDict] = []

    # Add each area as an option
    for area in areas:
        if not isinstance(area, dict):
            _LOGGER.warning("Skipping invalid area config (not a dict): %s", area)
            continue
        area_id = area.get(CONF_AREA_ID)
        if not area_id:
            _LOGGER.warning(
                "Area config missing area_id, skipping: %s",
                area,
            )
            continue

        # Resolve area name from ID
        area_name = "Unknown"
        if hass:
            try:
                area_name = _resolve_area_id_to_name(hass, area_id)
            except ValueError as err:
                # Area was deleted, log and skip it
                _LOGGER.warning(
                    "Area ID '%s' not found in registry (may have been deleted), skipping: %s",
                    area_id,
                    err,
                )
                continue
        else:
            # Fallback to area_id if we can't resolve
            area_name = area_id

        summary = _get_area_summary_info(
            resolve_area_sensors(hass, area, global_options) if hass else area
        )
        # Use area_id for option value (sanitized)
        sanitized_id = area_id.replace(" ", "_").replace("/", "_")
        # Include summary in label for better UX
        options.append(
            {
                "value": f"{CONF_OPTION_PREFIX_AREA}{sanitized_id}",
                "label": f"{area_name} - {summary}",
            }
        )

    return vol.Schema(
        {
            vol.Required("selected_option"): SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    mode=SelectSelectorMode.LIST,
                )
            )
        }
    )


def _create_global_sleep_schema(
    defaults: Mapping[str, Any],
) -> vol.Schema:
    """Create schema for global sleep schedule and sleep decay settings."""
    return vol.Schema(
        {
            vol.Required(
                CONF_SLEEP_START,
                default=defaults.get(CONF_SLEEP_START, DEFAULT_SLEEP_START),
            ): TimeSelector(),
            vol.Required(
                CONF_SLEEP_END,
                default=defaults.get(CONF_SLEEP_END, DEFAULT_SLEEP_END),
            ): TimeSelector(),
            vol.Required(
                CONF_SLEEP_DECAY_HALF_LIFE,
                default=seconds_to_duration(
                    parse_global_sleep_decay_half_life(defaults)
                ),
            ): _duration_selector(),
        }
    )


def _create_global_general_schema(
    defaults: Mapping[str, Any],
) -> vol.Schema:
    """Create schema for general integration-wide settings."""
    return vol.Schema(
        {
            vol.Required(
                CONF_HEALTH_ENABLED,
                default=defaults.get(CONF_HEALTH_ENABLED, DEFAULT_HEALTH_ENABLED),
            ): BooleanSelector(),
            vol.Required(
                CONF_SENSOR_PRECISION,
                default=defaults.get(CONF_SENSOR_PRECISION, DEFAULT_SENSOR_PRECISION),
            ): vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=2,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Coerce(int),
            ),
            vol.Required(
                CONF_EXPAND_GROUPS,
                default=defaults.get(CONF_EXPAND_GROUPS, DEFAULT_GLOBAL_EXPAND_GROUPS),
            ): BooleanSelector(),
            # The current value is only suggested, not a default: a default
            # would refill the field whenever the user clears it.
            vol.Optional(
                CONF_AWAY_MODE_ENTITY,
                description={"suggested_value": defaults.get(CONF_AWAY_MODE_ENTITY)},
            ): EntitySelector(
                EntitySelectorConfig(domain=list(AWAY_MODE_ENTITY_DOMAINS))
            ),
        }
    )


def _create_global_purpose_decay_schema(
    defaults: Mapping[str, Any],
) -> vol.Schema:
    """Create schema for global per-purpose default decay half-lives."""
    overrides = parse_global_purpose_decay_half_lives(defaults)
    fields: dict[vol.Marker, Any] = {}
    for purpose_def in PURPOSE_DEFINITIONS.values():
        key = purpose_def.purpose.value
        seconds = overrides.get(key, DEFAULT_DECAY_HALF_LIFE)
        fields[
            vol.Optional(
                key,
                default=seconds_to_duration(seconds),
            )
        ] = _duration_selector()
    return vol.Schema(fields)


def _create_global_exclusions_schema(
    defaults: Mapping[str, Any],
    hass: HomeAssistant | None = None,
) -> vol.Schema:
    """Create one-page schema for integration-wide exclusions."""
    defaults_dict = dict(defaults)
    exclusion_fields = _create_exclusion_fields(defaults_dict, hass)
    sensor_type_options = _get_excluded_sensor_type_options()
    fields: dict[vol.Marker, Any] = {
        vol.Optional(SECTION_GLOBAL_SENSOR_TYPES): section(
            vol.Schema(
                {
                    vol.Optional(
                        CONF_EXCLUDED_SENSOR_TYPES,
                        default=list(defaults.get(CONF_EXCLUDED_SENSOR_TYPES) or []),
                    ): _sensor_types_list_selector(sensor_type_options)
                }
            ),
            _section_options(collapsed=True),
        ),
        vol.Optional(SECTION_GLOBAL_DEVICES): section(
            vol.Schema(
                {
                    **{
                        vol.Optional(
                            rule.config_key,
                            default=defaults.get(rule.config_key, rule.global_default),
                        ): BooleanSelector()
                        for rule in DISCOVERY_EXCLUSION_RULES
                    },
                    **dict([exclusion_fields.manufacturers, exclusion_fields.models]),
                }
            ),
            _section_options(collapsed=True),
        ),
        vol.Optional(SECTION_GLOBAL_ENTITIES): section(
            vol.Schema(dict([exclusion_fields.entities])),
            _section_options(collapsed=True),
        ),
        vol.Optional(SECTION_GLOBAL_INTEGRATIONS): section(
            vol.Schema(dict([exclusion_fields.integrations])),
            _section_options(collapsed=True),
        ),
    }
    return vol.Schema(fields)


def _build_basics_suggested_values(draft: dict[str, Any]) -> dict[str, Any]:
    """Build section-aware suggested values for ``area_basics`` from a draft dict."""
    suggested = _draft_to_suggested(
        draft,
        {
            CONF_AREA_ID,
            CONF_PURPOSE,
            CONF_ADJACENT_AREAS,
            CONF_AUTO_DISCOVER_SENSORS,
            CONF_EXPAND_GROUPS,
            *(rule.config_key for rule in DISCOVERY_EXCLUSION_RULES),
        },
    )
    if CONF_EXPAND_GROUPS in suggested:
        suggested[CONF_EXPAND_GROUPS] = normalize_group_expansion_mode(
            suggested[CONF_EXPAND_GROUPS]
        ).value
    for rule in DISCOVERY_EXCLUSION_RULES:
        if rule.config_key in suggested:
            suggested[rule.config_key] = normalize_exclusion_mode(
                suggested[rule.config_key]
            ).value
    area_exclusions_suggested = {
        key: draft[key] for key in _AREA_EXCLUSION_FIELD_KEYS if key in draft
    }
    if area_exclusions_suggested:
        suggested[SECTION_AREA_EXCLUSIONS] = area_exclusions_suggested
    if CONF_AUTO_DISCOVER_DOMAINS in draft:
        suggested[SECTION_AUTO_DISCOVERY_TYPES] = {
            CONF_AUTO_DISCOVER_DOMAINS: _get_ordered_auto_discover_types(draft)
        }
    return suggested


if TYPE_CHECKING:
    from collections.abc import Callable

    class _FlowBase:
        """What the mixin below uses from Home Assistant's flow classes.

        The mixin is only ever combined with the config flow, the options flow
        or the subentry flow, which provide these. They are declared here, for
        the type checker only. The three flows have different result types, so
        the results are ``Any`` and the arguments aren't checked inside the
        mixin; Home Assistant's own signatures apply at run time. At run time
        this base is ``object``.
        """

        hass: HomeAssistant
        add_suggested_values_to_schema: Callable[..., vol.Schema]
        async_show_form: Callable[..., Any]
        async_show_menu: Callable[..., Any]

else:
    _FlowBase = object


class BaseOccupancyFlow(_FlowBase):
    """Base class for config and options flow.

    This class provides shared validation logic used by both the config flow
    and options flow. It ensures consistent validation across both flows.
    """

    if TYPE_CHECKING:

        async def async_step_area_action(
            self, user_input: dict[str, Any] | None = None
        ) -> Any:
            """The hub menu, defined by the flows that use this mixin."""

    def _schema_with_input(
        self, base_schema: vol.Schema, user_input: dict[str, Any] | None
    ) -> vol.Schema:
        """Apply ``user_input`` as suggested values on error re-display."""
        return (
            self.add_suggested_values_to_schema(base_schema, user_input)
            if user_input is not None
            else base_schema
        )

    def _schema_with_explicit_suggested(
        self,
        base_schema: vol.Schema,
        user_input: dict[str, Any] | None,
        draft_suggested: dict[str, Any],
    ) -> vol.Schema:
        """Populate ``EXPLICIT_SECTION`` suggested values from user input or draft."""
        if user_input is not None:
            return self.add_suggested_values_to_schema(
                base_schema,
                {
                    EXPLICIT_SECTION: _editable_section_input(
                        user_input.get(EXPLICIT_SECTION, {})
                    )
                },
            )
        if draft_suggested:
            return self.add_suggested_values_to_schema(
                base_schema, {EXPLICIT_SECTION: draft_suggested}
            )
        return base_schema

    def _prepare_sensor_step_submission(
        self, user_input: dict[str, Any], sensor_keys: tuple[str, ...]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Flatten, sync discovery exclusions, and resolve effective area sensors."""
        flattened = _editable_form_input(user_input)
        flattened = _sync_discovered_and_excluded(
            self.hass,
            self._area_config_draft,
            flattened,
            sensor_keys,
            self._get_global_options(),
        )
        candidate = {**self._area_config_draft, **flattened}
        return flattened, self._resolve_area_sensors(candidate)

    def _resolve_area_sensors(self, data: dict[str, Any]) -> dict[str, Any]:
        """Resolve area sensors with integration-wide discovery exclusions."""
        if not getattr(self, "hass", None):
            return data
        return resolve_area_sensors(self.hass, data, self._get_global_options())

    def _validate_duplicate_area_id(
        self,
        flattened_input: dict[str, Any],
        areas: list[dict[str, Any]],
        area_id_being_edited: str | None = None,
        hass: HomeAssistant | None = None,
    ) -> dict[str, str]:
        """Validate that area ID is not a duplicate.

        Args:
            flattened_input: The flattened input configuration
            areas: List of existing area configurations
            area_id_being_edited: Optional area ID being edited (to exclude from duplicate check)
            hass: Home Assistant instance (for resolving area names in error messages)

        Returns:
            Dictionary mapping field keys to error translation keys
        """
        errors: dict[str, str] = {}
        area_id = flattened_input.get(CONF_AREA_ID, "")
        if area_id:
            for area in areas:
                existing_area_id = area.get(CONF_AREA_ID)
                if existing_area_id == area_id and (
                    not area_id_being_edited or existing_area_id != area_id_being_edited
                ):
                    errors[CONF_AREA_ID] = "area_already_configured"
                    break
        return errors

    def _validate_config(
        self,
        data: dict[str, Any],
        hass: HomeAssistant | None = None,
        global_options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Validate a flat area configuration and return per-field errors.

        Every hass-free rule lives in ``config_helpers.validate_area_config``
        so other writers (entities, services) validate identically. This
        wrapper adds the one check that needs the registry: the selected
        Home Assistant area must exist.

        Args:
            data: Flat (un-sectioned) area configuration
            hass: Home Assistant instance (for validating the area id)
            global_options: Integration-wide discovery exclusions, when available

        Returns:
            Mapping of field key (or ``"base"``) to ``strings.json`` error key.
            Empty when validation passed.
        """
        effective_global_options = (
            self._get_global_options() if global_options is None else global_options
        )
        errors = validate_area_config(
            resolve_area_sensors(
                hass,
                data,
                effective_global_options,
            )
            if hass
            else data
        )
        area_id = data.get(CONF_AREA_ID, "")
        if area_id and hass and CONF_AREA_ID not in errors:
            try:
                _resolve_area_id_to_name(hass, area_id)
            except ValueError:
                errors[CONF_AREA_ID] = "area_not_found"
        return errors

    def _prepare_area_action_edit(self) -> None:
        """Prepare state for editing an area."""
        self._area_to_remove = None

    def _prepare_area_action_remove(self) -> None:
        """Prepare state for removing an area."""
        area_id = self._area_being_edited
        self._area_to_remove = area_id
        self._area_being_edited = None

    def _prepare_area_action_cancel(self) -> None:
        """Prepare state for cancelling area action."""
        self._area_to_remove = None
        self._area_being_edited = None

    # ── Multi-step area config wizard ────────────────────────────────

    def _get_wizard_areas(self) -> list[dict[str, Any]]:
        """Get the list of areas for duplicate checking. Overridden by subclasses."""
        raise NotImplementedError

    async def _on_area_config_complete(
        self, config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle completion of the area config wizard. Overridden by subclasses."""
        raise NotImplementedError

    def _build_adjacent_area_options(
        self,
        areas: list[dict[str, Any]] | None = None,
        exclude_area_id: str | None = None,
    ) -> list[SelectOptionDict]:
        """Build the multi-select options for the adjacency field.

        Returns options for every area configured in this entry except the
        one currently being edited (you can't be adjacent to yourself).
        Labels resolve to the HA area registry name when possible, falling
        back to the raw area_id.
        """
        options: list[SelectOptionDict] = []
        seen: set[str] = set()
        editing_area_id = (
            exclude_area_id if exclude_area_id is not None else self._area_being_edited
        )
        for area in areas if areas is not None else self._get_wizard_areas():
            other_area_id = area.get(CONF_AREA_ID)
            # Defensive: malformed persisted data could leave a non-string
            # value here. Comparison still works but downstream
            # ``_resolve_area_id_to_name`` and ``SelectOptionDict`` both
            # expect str — skip rather than crash later.
            if not isinstance(other_area_id, str) or not other_area_id:
                continue
            if other_area_id == editing_area_id or other_area_id in seen:
                continue
            seen.add(other_area_id)
            label = other_area_id
            if self.hass:
                with contextlib.suppress(ValueError):
                    label = _resolve_area_id_to_name(self.hass, other_area_id)
            options.append(SelectOptionDict(value=other_area_id, label=label))
        options.sort(key=lambda opt: opt["label"].lower())
        return options

    def _init_area_wizard(self) -> None:
        """Initialize the area config wizard draft (full linear wizard mode)."""
        self._area_edit_section = None
        self._sensor_group_being_edited = None
        if self._area_being_edited:
            areas = self._get_wizard_areas()
            area = find_area_by_id(areas, self._area_being_edited)
            self._area_config_draft = area.copy() if area else {}
        elif getattr(self, "hass", None):
            configured_ids = {
                str(a.get(CONF_AREA_ID))
                for a in self._get_wizard_areas()
                if a.get(CONF_AREA_ID)
            }
            eligible = discover_eligible_areas(
                self.hass,
                excluded_area_ids=configured_ids,
                global_options=self._get_global_options(),
            )
            self._area_config_draft = eligible[0] if eligible else {}
        else:
            self._area_config_draft = {}

    def _get_wizard_placeholders(self) -> dict[str, str]:
        """Get description placeholders showing the area being configured."""
        area_id = self._area_config_draft.get(CONF_AREA_ID, "")
        area_name = "New Area"
        if area_id:
            with contextlib.suppress(ValueError):
                area_name = _resolve_area_id_to_name(self.hass, area_id)
        return {_PLACEHOLDER_AREA_NAME: area_name}

    def _get_global_options(self) -> dict[str, Any]:
        """Return saved integration-wide options from the config entry, if any."""
        config_entry: ConfigEntry | None = getattr(self, "config_entry", None)
        if config_entry is None and callable(
            get_entry := getattr(self, "_get_entry", None)
        ):
            with contextlib.suppress(Exception):
                config_entry = cast("ConfigEntry | None", get_entry())
        if config_entry is None and callable(
            get_active := getattr(self, "_get_active_entry", None)
        ):
            with contextlib.suppress(Exception):
                config_entry = cast("ConfigEntry | None", get_active())
        return dict(config_entry.options) if config_entry is not None else {}

    def _get_global_sleep_decay_half_life(self) -> int:
        """Return the configured global sleep decay half-life in seconds."""
        return parse_global_sleep_decay_half_life(self._get_global_options())

    def _get_global_purpose_decay_half_lives(self) -> dict[str, int]:
        """Return configured global per-purpose decay half-life overrides."""
        return parse_global_purpose_decay_half_lives(self._get_global_options())

    def _get_behavior_placeholders(self) -> dict[str, str]:
        """Get description placeholders for the area behavior step."""
        placeholders = self._get_wizard_placeholders()
        purpose = self._area_config_draft.get(CONF_PURPOSE, DEFAULT_PURPOSE)
        placeholders[_PLACEHOLDER_DECAY_DEFAULT] = _format_seconds(
            get_default_decay_half_life(
                purpose, self._get_global_purpose_decay_half_lives()
            )
        )
        placeholders[_PLACEHOLDER_SLEEP_DECAY_DEFAULT] = _format_seconds(
            self._get_global_sleep_decay_half_life()
        )
        return placeholders

    # ── Persisting an area ───────────────────────────────────────────

    def _persist_area_subentry(
        self,
        entry: ConfigEntry,
        config: dict[str, Any],
        area_id_being_edited: str | None,
        *,
        create_missing: bool = True,
    ) -> None:
        """Create or update the area's subentry and mirror adjacency.

        Adjacency is mutual but edited per area, so saving one area rewrites
        its neighbours' rows too. The mirror runs over the flat list of every
        area's data -- the same pure transform the list format used -- and
        each changed row is written back to its own subentry.
        """
        areas = [data for _, data in iter_area_subentries(entry)]
        updated = update_area_in_list(areas, config, area_id_being_edited)

        by_area_id = {
            data.get(CONF_AREA_ID): data for data in updated if data.get(CONF_AREA_ID)
        }
        target_area_id = config.get(CONF_AREA_ID)

        for subentry_id, existing in iter_area_subentries(entry):
            area_id = existing.get(CONF_AREA_ID)
            new_data = by_area_id.get(area_id)
            if new_data is None or new_data == existing:
                continue
            subentry = entry.subentries[subentry_id]
            self.hass.config_entries.async_update_subentry(
                entry, subentry, data=new_data
            )

        if (
            create_missing
            and target_area_id
            and find_area_subentry_id(entry, target_area_id) is None
        ):
            self.hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(by_area_id[target_area_id]),
                    subentry_type=SUBENTRY_TYPE_AREA,
                    title=self._area_title(target_area_id),
                    unique_id=str(target_area_id),
                ),
            )

    def _area_title(self, area_id: str) -> str:
        """Human-readable subentry title for an area id."""
        if self.hass:
            with contextlib.suppress(ValueError):
                return _resolve_area_id_to_name(self.hass, area_id)
        return str(area_id)

    def _reset_wizard_state(self) -> None:
        """Clear the per-edit wizard state after a save."""
        self._area_being_edited = None
        self._area_config_draft = {}
        self._area_edit_section = None
        self._sensor_group_being_edited = None

    # ── Live preview (options flow only) ─────────────────────────────

    def _preview_component(self) -> str | None:
        """Name of the frontend preview to show next to sensor/behaviour forms.

        ``None`` disables the preview. The options flow overrides this: a
        preview needs a loaded area to read live evidence from, which the
        initial config flow does not have yet.
        """
        return None

    def _publish_preview_context(self) -> None:
        """Expose the draft to the preview websocket handler (options flow)."""

    # ── Hub-and-spoke editing of an existing area ────────────────────
    #
    # The linear wizard is the right shape for *adding* an area. For
    # *editing* one, each wizard page is reachable directly from the
    # ``area_action`` menu as a spoke that saves on submit. The wizard step
    # handlers stay shared; ``_area_edit_section`` tells them to finish
    # instead of advancing.

    @property
    def _editing_single_section(self) -> bool:
        return self._area_edit_section is not None

    async def _start_section_edit(self, section: str) -> ConfigFlowResult:
        """Open one wizard page as a standalone edit form."""
        self._prepare_area_action_edit()
        self._init_area_wizard()
        self._area_edit_section = section
        if section == "basics":
            return await self.async_step_area_basics()
        if section == "motion":
            return await self.async_step_area_motion()
        if section == "sensors":
            return await self.async_step_area_sensors()
        return await self.async_step_area_behavior()

    async def _complete_section_edit(
        self, updates: dict[str, Any]
    ) -> tuple[dict[str, str], ConfigFlowResult | None]:
        """Merge a single-section edit into the draft, validate, and save.

        Returns ``(errors, result)``: on validation failure ``errors`` is
        non-empty and ``result`` is ``None`` so the caller can re-render its
        form; on success ``result`` is the completed flow result.
        """
        candidate = {**self._area_config_draft, **updates}
        apply_purpose_based_decay_default(
            candidate,
            candidate.get(CONF_PURPOSE),
            self._get_global_purpose_decay_half_lives(),
        )
        errors = self._validate_config(candidate, self.hass)
        if errors:
            return errors, None
        self._area_config_draft = candidate
        return {}, await self._on_area_config_complete(candidate)

    async def async_step_edit_basics(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: edit purpose and adjacency only."""
        return await self._start_section_edit("basics")

    async def async_step_edit_motion(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: edit motion sensors only."""
        return await self._start_section_edit("motion")

    async def async_step_edit_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: edit threshold, decay and wasp-in-box only."""
        return await self._start_section_edit("behavior")

    async def async_step_edit_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke hub: pick which additional-sensor group to edit."""
        self._prepare_area_action_edit()
        return await self.async_step_area_sensors_menu()

    async def async_step_area_sensors_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu of additional-sensor groups for the area being edited."""
        area_id = self._area_being_edited
        area_config = find_area_by_id(self._get_wizard_areas(), area_id or "")
        if not area_id or area_config is None:
            return await self.async_step_area_action()
        return self.async_show_menu(
            step_id="area_sensors_menu",
            menu_options=[f"edit_sensors_{group}" for group in SENSOR_GROUPS]
            + ["cancel_sensors_menu"],
            description_placeholders=_build_area_description_placeholders(
                area_config,
                area_id,
                self.hass,
                self._get_global_options(),
            ),
        )

    async def _start_sensor_group_edit(self, group: str) -> ConfigFlowResult:
        """Open one additional-sensor group as a standalone edit form."""
        self._prepare_area_action_edit()
        self._init_area_wizard()
        self._area_edit_section = "sensors"
        self._sensor_group_being_edited = group
        return await self.async_step_area_sensors()

    async def async_step_edit_sensors_windows_and_doors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: doors, windows, locks and covers."""
        return await self._start_sensor_group_edit("windows_and_doors")

    async def async_step_edit_sensors_media(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: media players."""
        return await self._start_sensor_group_edit("media")

    async def async_step_edit_sensors_appliances(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: appliances."""
        return await self._start_sensor_group_edit("appliances")

    async def async_step_edit_sensors_environmental(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: environmental sensors."""
        return await self._start_sensor_group_edit("environmental")

    async def async_step_edit_sensors_power(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: power sensors."""
        return await self._start_sensor_group_edit("power")

    async def async_step_edit_sensors_wifi_clients(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: Wi-Fi client-count sensors."""
        return await self._start_sensor_group_edit("wifi_clients")

    async def async_step_edit_sensors_custom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spoke: custom sensor rows."""
        return await self._start_sensor_group_edit("custom")

    async def async_step_cancel_sensors_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Back from the sensor-group menu to the area menu."""
        return await self.async_step_area_action()

    async def async_step_area_basics(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wizard step 1: Area selection and purpose."""
        errors: dict[str, str] = {}

        if user_input is not None:
            flattened_input = _normalize_basics_submission(user_input)
            # Read-only area selector doesn't submit a value when editing,
            # so fill it in from the draft
            if self._area_being_edited and CONF_AREA_ID not in flattened_input:
                flattened_input[CONF_AREA_ID] = self._area_config_draft.get(
                    CONF_AREA_ID, self._area_being_edited
                )
            area_id = flattened_input.get(CONF_AREA_ID, "")
            if not area_id:
                errors[CONF_AREA_ID] = _ERROR_AREA_REQUIRED
            elif self.hass:
                try:
                    _resolve_area_id_to_name(self.hass, area_id)
                except ValueError:
                    errors[CONF_AREA_ID] = _ERROR_AREA_NOT_FOUND

            if not errors:
                areas = self._get_wizard_areas()
                errors.update(
                    self._validate_duplicate_area_id(
                        flattened_input, areas, self._area_being_edited, self.hass
                    )
                )

            if not errors:
                updates = dict(flattened_input)
                if CONF_EXCLUDED_SENSORS in updates:
                    excluded_set = set(updates.get(CONF_EXCLUDED_SENSORS) or [])
                    updates.update(
                        _strip_excluded_sensors_from_draft(
                            self._area_config_draft, excluded_set
                        )
                    )
                if self._editing_single_section:
                    errors, result = await self._complete_section_edit(updates)
                    if result is not None:
                        return result
                else:
                    self._area_config_draft.update(updates)
                    return await self.async_step_area_motion()

        adjacent_options = self._build_adjacent_area_options()
        schema_dict = _create_basics_step_schema(
            is_editing=self._area_being_edited is not None,
            adjacent_options=adjacent_options,
            current=self._area_config_draft if self._area_being_edited else None,
            hass=self.hass,
        )
        base_schema = vol.Schema(schema_dict)

        # Apply suggested values from draft or user_input (for error re-display)
        suggested = (
            user_input
            if user_input is not None
            else _build_basics_suggested_values(self._area_config_draft)
        )
        data_schema = self._schema_with_input(base_schema, suggested or None)

        # Build description placeholders
        if self._area_being_edited and self._area_config_draft.get(CONF_AREA_ID):
            area_name = self._area_config_draft.get(CONF_AREA_ID, "")
            with contextlib.suppress(ValueError):
                area_name = _resolve_area_id_to_name(
                    self.hass, self._area_config_draft[CONF_AREA_ID]
                )
            placeholders = {"mode": "Editing", "area_name": area_name}
        else:
            placeholders = {"mode": "Adding", "area_name": "New Area"}

        return self.async_show_form(
            step_id="area_basics",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=placeholders,
            last_step=self._editing_single_section,
        )

    async def async_step_area_motion(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wizard step 2: Motion sensor configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            flattened, effective = self._prepare_sensor_step_submission(
                user_input, (CONF_MOTION_SENSORS,)
            )
            if not effective.get(CONF_MOTION_SENSORS):
                errors[_ERROR_BASE] = _ERROR_MOTION_REQUIRED

            prob_true = flattened.get(
                CONF_MOTION_PROB_GIVEN_TRUE, DEFAULT_MOTION_PROB_GIVEN_TRUE
            )
            prob_false = flattened.get(
                CONF_MOTION_PROB_GIVEN_FALSE, DEFAULT_MOTION_PROB_GIVEN_FALSE
            )
            if prob_true <= prob_false:
                errors[_ERROR_BASE] = _ERROR_PROB_TRUE_MUST_EXCEED_FALSE

            if not errors:
                if self._editing_single_section:
                    errors, result = await self._complete_section_edit(flattened)
                    if result is not None:
                        return result
                else:
                    self._area_config_draft.update(flattened)
                    return await self.async_step_area_sensors()

        # Suggested values
        motion_keys = {
            CONF_MOTION_SENSORS,
            CONF_WEIGHT_MOTION,
            CONF_MOTION_TIMEOUT,
            CONF_MOTION_PROB_GIVEN_TRUE,
            CONF_MOTION_PROB_GIVEN_FALSE,
        }
        resolved_draft = self._resolve_area_sensors(self._area_config_draft)
        auto_added_ids = _auto_added_sensor_ids(resolved_draft, (CONF_MOTION_SENSORS,))
        schema_dict = _create_motion_step_schema(
            self.hass, auto_added_entities=auto_added_ids
        )
        base_schema = vol.Schema(schema_dict)
        draft_suggested = (
            _draft_to_suggested(
                _explicit_sensor_config(resolved_draft, (CONF_MOTION_SENSORS,)),
                motion_keys,
            )
            if user_input is None
            else {}
        )
        data_schema = self._schema_with_explicit_suggested(
            base_schema, user_input, draft_suggested
        )

        self._publish_preview_context()
        return self.async_show_form(
            step_id="area_motion",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=self._get_wizard_placeholders(),
            preview=self._preview_component(),
            last_step=self._editing_single_section,
        )

    async def async_step_area_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wizard step 3: Additional sensor configuration (sections)."""
        errors: dict[str, str] = {}

        groups: tuple[str, ...] = (
            (self._sensor_group_being_edited,)
            if self._sensor_group_being_edited
            else SENSOR_GROUPS
        )
        active_sensor_keys = tuple(
            key for group in groups for key in SENSOR_GROUP_KEYS.get(group, ())
        )

        if user_input is not None:
            flattened, effective = self._prepare_sensor_step_submission(
                user_input, active_sensor_keys
            )

            # Validate here, while the fields are on screen: a sensor-state
            # error raised on a later step has no field to show against.
            errors.update(validate_sensor_states(effective))

            if not errors:
                if self._editing_single_section:
                    errors, result = await self._complete_section_edit(flattened)
                    if result is not None:
                        return result
                else:
                    self._area_config_draft.update(flattened)
                    return await self.async_step_area_behavior()

        resolved_draft = self._resolve_area_sensors(self._area_config_draft)
        auto_added_ids = {
            group: entity_ids
            for group in groups
            if (
                entity_ids := _auto_added_sensor_ids(
                    resolved_draft,
                    SENSOR_GROUP_KEYS.get(group, ()),
                )
            )
        }
        schema_dict = _create_sensors_step_schema(
            self.hass,
            groups=groups,
            auto_added_entities=auto_added_ids,
        )
        base_schema = vol.Schema(schema_dict)

        # For edit mode with sections, need nested suggested values
        explicit_suggested: dict[str, Any] = {}
        if user_input is None and self._area_config_draft:
            explicit_config = _explicit_sensor_config(
                resolved_draft, active_sensor_keys
            )
            nested = _nest_config_for_sections(explicit_config)
            for group in groups:
                explicit_suggested.update(nested.get(group, {}))
        data_schema = self._schema_with_explicit_suggested(
            base_schema, user_input, explicit_suggested
        )

        self._publish_preview_context()
        return self.async_show_form(
            step_id="area_sensors",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=self._get_wizard_placeholders(),
            preview=self._preview_component(),
            last_step=self._editing_single_section,
        )

    async def async_step_area_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wizard step 4: Behavior parameters (threshold, decay, wasp)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            flattened = flatten_sectioned_input(user_input)

            # Validate on a copy to avoid corrupting the draft on failure
            candidate = {**self._area_config_draft, **flattened}

            # Auto-set decay half-life based on purpose
            selected_purpose = candidate.get(CONF_PURPOSE)
            apply_purpose_based_decay_default(
                candidate,
                selected_purpose,
                self._get_global_purpose_decay_half_lives(),
            )

            # Run full validation on the complete candidate
            validation_errors = self._validate_config(candidate, self.hass)

            if not validation_errors:
                self._area_config_draft.update(candidate)
                return await self._on_area_config_complete(self._area_config_draft)

            errors.update(validation_errors)

        schema_dict = _create_behavior_step_schema(self._area_config_draft)
        base_schema = vol.Schema(schema_dict)

        # Suggested values - top-level behavior + nested wasp section
        behavior_keys = {
            CONF_THRESHOLD,
            CONF_DECAY_ENABLED,
            CONF_DECAY_HALF_LIFE,
            CONF_SLEEP_DECAY_HALF_LIFE,
            CONF_MIN_PRIOR_OVERRIDE,
            CONF_EXCLUDE_FROM_ALL_AREAS,
            CONF_CLOSED_DOOR_HOLD,
        }
        if user_input is not None:
            data_schema = self.add_suggested_values_to_schema(base_schema, user_input)
        elif self._area_config_draft:
            suggested = _draft_to_suggested(self._area_config_draft, behavior_keys)
            # Build nested wasp section suggested values
            nested = _nest_config_for_sections(self._area_config_draft)
            if "wasp_in_box" in nested:
                suggested["wasp_in_box"] = nested["wasp_in_box"]
            if suggested:
                data_schema = self.add_suggested_values_to_schema(
                    base_schema, suggested
                )
            else:
                data_schema = base_schema
        else:
            data_schema = base_schema

        self._publish_preview_context()
        return self.async_show_form(
            step_id="area_behavior",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=self._get_behavior_placeholders(),
            preview=self._preview_component(),
            last_step=True,
        )


class AreaSubentryFlowHandler(ConfigSubentryFlow, BaseOccupancyFlow):
    """Add or reconfigure one area as a config subentry.

    This is the native path: Home Assistant renders every area on the
    integration page with its own "Add", "Reconfigure" and "Delete", so the
    integration no longer hand-rolls an area list. The wizard and the
    hub-and-spoke edit steps are the same ones the options flow uses -- only
    where the result is written differs.
    """

    def __init__(self) -> None:
        """Initialize the subentry flow."""
        super().__init__()
        self._area_being_edited: str | None = None
        self._area_to_remove: str | None = None
        self._area_config_draft: dict[str, Any] = {}
        self._area_edit_section: str | None = None
        self._sensor_group_being_edited: str | None = None

    @staticmethod
    async def async_setup_preview(hass: HomeAssistant) -> None:
        """Register the preview websocket command on first use.

        Home Assistant calls this once per flow *class* that shows a form
        with a preview, so the subentry flow needs its own copy: without it
        the forms below advertise a preview the frontend then cannot
        subscribe to, and the preview panel reads "Unknown command" unless
        the options flow happened to register it earlier in the same run.
        """
        await preview.async_setup_preview(hass)

    def _get_wizard_areas(self) -> list[dict[str, Any]]:
        """Every configured area, for duplicate and adjacency checks."""
        return [data for _, data in iter_area_subentries(self._get_entry())]

    # The subentry flow ends with a subentry result, the other flows with a
    # config flow result, and the shared base method is typed for the latter.
    async def _on_area_config_complete(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, config: dict[str, Any]
    ) -> SubentryFlowResult:
        """Write the area, mirroring adjacency onto its neighbours."""
        entry = self._get_entry()
        editing = self._area_being_edited
        # Neighbours are written here; this area's own row is written by the
        # create/update call below, which is what ends the flow.
        self._persist_area_subentry(entry, config, editing, create_missing=False)
        area_id = str(config.get(CONF_AREA_ID) or "")
        title = self._area_title(area_id)
        self._reset_wizard_state()

        if editing:
            return self.async_update_and_abort(
                entry,
                self._get_reconfigure_subentry(),
                data=config,
                title=title,
            )
        return self.async_create_entry(title=title, data=config, unique_id=area_id)

    def _preview_component(self) -> str | None:
        """Show the live estimate on this flow's forms too.

        Reconfiguring an existing area is the main edit path now, so it gets
        the same preview the options flow has. A brand-new area has nothing
        loaded to preview, and the handler reports that itself.
        """
        return preview.PREVIEW_COMPONENT

    def _publish_preview_context(self) -> None:
        """Hand the draft to the preview handler under this flow's id."""
        flow_id = getattr(self, "flow_id", None)
        if not flow_id or not self.hass:
            return
        preview.register_preview_context(
            self.hass,
            flow_id,
            self._get_entry().entry_id,
            self._area_config_draft.get(CONF_AREA_ID) or self._area_being_edited,
            self._area_config_draft,
        )

    @callback
    def async_remove(self) -> None:
        """Drop the preview context when the flow ends."""
        flow_id = getattr(self, "flow_id", None)
        if flow_id and self.hass:
            preview.unregister_preview_context(self.hass, flow_id)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add an area: the full linear wizard."""
        self._area_being_edited = None
        self._init_area_wizard()
        # The shared wizard steps are typed with the config flow's result,
        # but under this flow they return its own.
        return cast(
            "SubentryFlowResult", cast("object", await self.async_step_area_basics())
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an area: the hub menu of per-page spokes."""
        return await self.async_step_area_action()

    async def async_step_area_action(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The hub menu itself.

        A menu's ``step_id`` must have a matching step handler, because the
        flow manager re-enters it when the user picks an option, so this is a
        real step rather than something ``async_step_reconfigure`` renders
        inline.
        """
        subentry = self._get_reconfigure_subentry()
        area_data = dict(subentry.data)
        area_id = area_data.get(CONF_AREA_ID)
        if not area_id:
            return self.async_abort(reason="area_required")

        self._area_being_edited = str(area_id)
        return self.async_show_menu(
            step_id="area_action",
            menu_options=[*AREA_EDIT_SPOKES, "edit_area"],
            description_placeholders=_build_area_description_placeholders(
                area_data,
                str(area_id),
                self.hass,
                self._get_global_options(),
            ),
        )

    async def async_step_edit_area(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Walk every wizard page in order."""
        self._prepare_area_action_edit()
        self._init_area_wizard()
        return cast(
            "SubentryFlowResult", cast("object", await self.async_step_area_basics())
        )


class AreaOccupancyConfigFlow(ConfigFlow, BaseOccupancyFlow, domain=DOMAIN):
    """Handle a config flow for Area Occupancy Detection.

    This class handles the initial configuration flow when the integration is first set up.
    It provides a multi-step configuration process with comprehensive validation.
    """

    VERSION = CONF_VERSION

    def __init__(self) -> None:
        """Initialize config flow.

        Sets up the initial empty data dictionary that will store configuration
        as it is built through the flow.
        """
        self._data: dict[str, Any] = {}
        self._areas: list[
            dict[str, Any]
        ] = []  # Store areas being configured during initial setup
        self._area_being_edited: str | None = None  # Store area ID (not name)
        self._area_to_remove: str | None = None  # Store area ID (not name)
        self._area_config_draft: dict[str, Any] = {}
        self._area_edit_section: str | None = None
        self._sensor_group_being_edited: str | None = None
        self._discovered_area_id: str | None = None

    def _get_active_entry(self) -> ConfigEntry | None:
        """Return the active config entry for this domain, if one exists."""
        return next(
            (
                entry
                for entry in self.hass.config_entries.async_entries(DOMAIN)
                if is_active_config_entry(entry)
            ),
            None,
        )

    def _get_wizard_areas(self) -> list[dict[str, Any]]:
        """Get areas list for duplicate checking."""
        return self._areas

    async def _on_area_config_complete(
        self, config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle wizard completion: update areas list and return to menu."""
        self._areas = update_area_in_list(self._areas, config, self._area_being_edited)
        self._area_being_edited = None
        self._area_config_draft = {}
        self._area_edit_section = None
        self._sensor_group_being_edited = None
        return await self.async_step_user()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Areas are configured as subentries of the single entry."""
        return {SUBENTRY_TYPE_AREA: AreaSubentryFlowHandler}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - show area selection form or auto-start first area."""
        # Check if a config entry already exists (e.g., user clicked "Add device" button)
        # In single-instance architecture, only one config entry should exist;
        # areas are added as subentries with the entry's "Add an area" button.
        if self._get_active_entry() and user_input is None:
            # Config entry already exists - point to "Add an area" (#582)
            return self.async_abort(reason=_ABORT_ALREADY_CONFIGURED)

        # If no areas exist yet, automatically start configuring the first area
        # This provides a smoother user experience - users don't need to click "Add New Area" first
        if not self._areas and user_input is None:
            self._area_being_edited = None
            return await self.async_step_area_config()

        # Hybrid approach: Static menu for main actions if areas exist
        # "Finish Setup" maps to async_step_finish_setup
        menu_options = [CONF_ACTION_ADD_AREA]
        if self._areas:
            menu_options.append("manage_areas")
            menu_options.append("finish_setup")

        return self.async_show_menu(
            step_id="user",
            menu_options=menu_options,
        )

    async def async_step_manage_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show list of areas to manage during initial setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_option = user_input.get("selected_option", "")
            if selected_option.startswith(CONF_OPTION_PREFIX_AREA):
                # User selected an area - extract area ID and go to action step
                sanitized_id = selected_option.replace(CONF_OPTION_PREFIX_AREA, "", 1)
                # Find the actual area by matching sanitized IDs
                area = _find_area_by_sanitized_id(self._areas, sanitized_id)
                if area:
                    self._area_being_edited = area.get(CONF_AREA_ID)
                    return await self.async_step_area_action()
                # If we couldn't find the area, show error
                errors["base"] = "Selected area could not be found"

        return self.async_show_form(
            step_id="manage_areas",
            data_schema=_create_area_selector_schema(
                self._areas,
                hass=self.hass,
                global_options=self._get_global_options(),
            ),
            errors=errors,
        )

    async def async_step_add_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new area."""
        self._area_being_edited = None
        return await self.async_step_area_config(user_input)

    async def async_step_finish_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish setup and create the config entry."""
        errors: dict[str, str] = {}

        if not self._areas:
            errors["base"] = (
                "At least one area must be configured before finishing setup"
            )
            return await self.async_step_user()

        try:
            # Validate all areas before creating entry
            for area in self._areas:
                area_errors = self._validate_config(area, self.hass)
                if area_errors:
                    # Surface the first error found
                    errors.update(area_errors)
                    return await self.async_step_user()

            # Store in new multi-area format
            # Use a fixed title for the integration entry
            await self.async_set_unique_id(DOMAIN)
            try:
                self._abort_if_unique_id_configured()
            except AbortFlow as err:
                if err.reason == "already_configured":
                    # Guide user to use Options Flow instead
                    raise AbortFlow(
                        "already_configured",
                        description_placeholders={
                            "title": "Area Occupancy Detection",
                            "hint": "To add more areas, please use the Options Flow from Settings > Devices & Services > Area Occupancy Detection > Configure.",
                        },
                    ) from err
                raise

            async_trigger_area_discoveries(self.hass)

            # Each area becomes a config subentry so the integration page
            # lists them natively with their own reconfigure and delete.
            return self.async_create_entry(
                title="Area Occupancy Detection",
                data={},
                subentries=[
                    ConfigSubentryData(
                        data=area,
                        subentry_type=SUBENTRY_TYPE_AREA,
                        title=self._area_title(area.get(CONF_AREA_ID, "")),
                        unique_id=str(area.get(CONF_AREA_ID)),
                    )
                    for area in self._areas
                ],
            )
        except AbortFlow:
            raise
        except HomeAssistantError as err:
            _LOGGER.error("Validation error: %s", err)
            errors["base"] = str(err)
        except vol.Invalid as err:
            _LOGGER.error("Validation error: %s", err)
            errors["base"] = str(err)
        except Exception:
            _LOGGER.exception("Unexpected error creating entry")
            errors["base"] = "unknown"

        return await self.async_step_user()

    async def async_step_area_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initialize the area config wizard."""
        self._init_area_wizard()
        return await self.async_step_area_basics()

    async def async_step_area_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle action selection for a specific area via menu."""
        area_id = self._area_being_edited
        if not area_id:
            return await self.async_step_user()

        area_config = find_area_by_id(self._areas, area_id)
        if not area_config:
            return await self.async_step_user()

        description_placeholders = _build_area_description_placeholders(
            area_config,
            area_id,
            self.hass,
            self._get_global_options(),
        )

        return self.async_show_menu(
            step_id="area_action",
            menu_options=[
                *AREA_EDIT_SPOKES,
                "edit_area",
                "remove_area_confirm",
                "cancel_area_action",
            ],
            description_placeholders=description_placeholders,
        )

    async def async_step_edit_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected area."""
        self._prepare_area_action_edit()
        return await self.async_step_area_config()

    async def async_step_remove_area_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initiate area removal."""
        self._prepare_area_action_remove()
        return await self.async_step_remove_area()

    async def async_step_cancel_area_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel area action and return to main menu."""
        self._prepare_area_action_cancel()
        return await self.async_step_user()

    async def async_step_remove_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm removal of an area during initial setup via menu."""
        area_id = self._area_to_remove
        if not area_id:
            return await self.async_step_user()

        return self.async_show_menu(
            step_id="remove_area",
            menu_options=["confirm_remove_area", "cancel_remove_area"],
        )

    async def async_step_confirm_remove_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Execute area removal."""
        area_id = self._area_to_remove
        if not area_id:
            return await self.async_step_user()

        updated_areas = remove_area_from_list(self._areas, area_id)
        if not updated_areas:
            return self.async_abort(reason="cannot_remove_last_area")

        self._areas = updated_areas
        self._area_to_remove = None
        return await self.async_step_user()

    async def async_step_cancel_remove_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel area removal."""
        self._area_to_remove = None
        return await self.async_step_user()

    def _resolve_discovered_area_context(
        self, area_id: str
    ) -> tuple[str | None, ConfigEntry | None, ConfigFlowResult | None]:
        """Validate a discovered area ID and return ``(area_name, active_entry, abort)``."""
        if not area_id:
            return None, None, self.async_abort(reason=_ABORT_AREA_REQUIRED)

        try:
            area_name = _resolve_area_id_to_name(self.hass, area_id)
        except ValueError:
            return None, None, self.async_abort(reason=_ABORT_AREA_NOT_FOUND)

        active_entry = self._get_active_entry()
        if active_entry and find_area_subentry_id(active_entry, area_id) is not None:
            return (
                None,
                None,
                self.async_abort(reason=_ABORT_AREA_ALREADY_CONFIGURED),
            )

        return area_name, active_entry, None

    @override
    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle discovery of an eligible Home Assistant area."""
        area_id = str(discovery_info.get(CONF_AREA_ID) or "")
        area_name, active_entry, abort = self._resolve_discovered_area_context(area_id)
        if abort is not None or area_name is None:
            return abort or self.async_abort(reason=_ABORT_AREA_NOT_FOUND)

        _ = await self.async_set_unique_id(area_discovery_unique_id(area_id))
        self._abort_if_unique_id_configured()

        discovered = discover_area_sensors(
            self.hass,
            area_id,
            global_options=active_entry.options if active_entry else None,
        )
        if not discovered.get(CONF_MOTION_SENSORS):
            return self.async_abort(reason=_ABORT_MOTION_REQUIRED)

        self.context[_CONTEXT_TITLE_PLACEHOLDERS] = {_PLACEHOLDER_NAME: area_name}
        self._discovered_area_id = area_id
        return await self.async_step_discovery_confirm()

    async def _persist_discovered_area(
        self,
        *,
        active_entry: ConfigEntry | None,
        candidate: dict[str, Any],
        area_id: str,
        area_name: str,
    ) -> ConfigFlowResult:
        """Create or update the integration entry for a confirmed discovered area."""
        if active_entry is not None:
            self._persist_area_subentry(active_entry, candidate, None)
            async_trigger_area_discoveries(self.hass)
            return self.async_abort(
                reason=_ABORT_AREA_ADDED,
                description_placeholders={_PLACEHOLDER_AREA_NAME: area_name},
            )

        _ = await self.async_set_unique_id(DOMAIN, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=INTEGRATION_TITLE,
            data={},
            subentries=[
                ConfigSubentryData(
                    data=candidate,
                    subentry_type=SUBENTRY_TYPE_AREA,
                    title=area_name,
                    unique_id=str(area_id),
                )
            ],
        )

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered area to Area Occupancy Detection."""
        area_id = self._discovered_area_id or ""
        area_name, active_entry, abort = self._resolve_discovered_area_context(area_id)
        if abort is not None or area_name is None:
            return abort or self.async_abort(reason=_ABORT_AREA_NOT_FOUND)

        global_options = dict(active_entry.options) if active_entry else {}
        discovered = discover_area_sensors(
            self.hass, area_id, global_options=global_options
        )
        suggested_config = build_suggested_area_config(self.hass, area_id, area_name)
        adjacent_options = (
            self._build_adjacent_area_options(
                areas=[data for _, data in iter_area_subentries(active_entry)],
                exclude_area_id=area_id,
            )
            if active_entry is not None
            else []
        )
        errors: dict[str, str] = {}

        if user_input is not None:
            flattened_input = _normalize_basics_submission(user_input)
            candidate = {
                **suggested_config,
                **flattened_input,
                CONF_AREA_ID: area_id,
            }
            apply_purpose_based_decay_default(
                candidate,
                candidate.get(CONF_PURPOSE),
                self._get_global_purpose_decay_half_lives(),
            )
            errors.update(self._validate_config(candidate, self.hass, global_options))

            if not errors:
                return await self._persist_discovered_area(
                    active_entry=active_entry,
                    candidate=candidate,
                    area_id=area_id,
                    area_name=area_name,
                )

        base_schema = vol.Schema(
            _create_basics_step_schema(
                is_editing=True,
                adjacent_options=adjacent_options,
                current=suggested_config,
                hass=self.hass,
            )
        )
        data_schema = self._schema_with_input(base_schema, user_input)

        return self.async_show_form(
            step_id=STEP_DISCOVERY_CONFIRM,
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                _PLACEHOLDER_AREA_NAME: area_name,
                _PLACEHOLDER_MOTION_COUNT: str(
                    len(discovered.get(CONF_MOTION_SENSORS, []))
                ),
                _PLACEHOLDER_SENSOR_COUNT: str(
                    sum(len(v) for v in discovered.values())
                ),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> AreaOccupancyOptionsFlow:
        """Get the options flow."""
        return AreaOccupancyOptionsFlow()


def _parse_purpose_decay_submission(
    validated: Mapping[str, Any],
) -> tuple[dict[str, int], dict[str, str]]:
    """Validate and extract non-default global per-purpose decay overrides."""
    overrides: dict[str, int] = {}
    errors: dict[str, str] = {}
    for purpose_def in PURPOSE_DEFINITIONS.values():
        key = purpose_def.purpose.value
        seconds = duration_to_seconds(validated[key])
        if error := validate_decay_half_life(seconds):
            errors[key] = error
        elif not Purpose.is_purpose_half_life(seconds, key):
            overrides[key] = seconds
    return overrides, errors


class AreaOccupancyOptionsFlow(OptionsFlow, BaseOccupancyFlow):
    """Handle options flow for global settings, area management, and people management."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        self._area_being_edited: str | None = None
        self._area_to_remove: str | None = None
        self._area_to_reset: str | None = None  # area_id pending learning reset
        self._area_config_draft: dict[str, Any] = {}
        self._area_edit_section: str | None = None
        self._sensor_group_being_edited: str | None = None
        self._person_being_edited: int | None = None  # Index into people list
        self._person_to_remove: int | None = None  # Index into people list for removal

    @staticmethod
    async def async_setup_preview(hass: HomeAssistant) -> None:
        """Register the preview websocket command on first use."""
        await preview.async_setup_preview(hass)

    def _preview_component(self) -> str | None:
        """Show the live estimate next to the sensor and behaviour forms."""
        return preview.PREVIEW_COMPONENT

    def _publish_preview_context(self) -> None:
        """Hand the draft to the preview handler under this flow's id."""
        flow_id = getattr(self, "flow_id", None)
        if not flow_id or not self.hass:
            return
        preview.register_preview_context(
            self.hass,
            flow_id,
            self.config_entry.entry_id,
            self._area_config_draft.get(CONF_AREA_ID) or self._area_being_edited,
            self._area_config_draft,
        )

    @callback
    def async_remove(self) -> None:
        """Drop the preview context when the flow ends."""
        flow_id = getattr(self, "flow_id", None)
        if flow_id and self.hass:
            preview.unregister_preview_context(self.hass, flow_id)

    def _get_areas_from_config(self) -> list[dict[str, Any]]:
        """Get each configured area's data from its config subentry."""
        return [data for _, data in iter_area_subentries(self.config_entry)]

    def _get_wizard_areas(self) -> list[dict[str, Any]]:
        """Get areas list for duplicate checking."""
        return self._get_areas_from_config()

    async def _on_area_config_complete(
        self, config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle wizard completion: write the area to its config subentry.

        The _async_entry_updated listener sees the structural change and
        reloads the integration so entity platforms are rebuilt.
        """
        self._persist_area_subentry(self.config_entry, config, self._area_being_edited)
        self._reset_wizard_state()
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                CONF_ACTION_ADD_AREA,
                "manage_areas",
                CONF_ACTION_GLOBAL_SETTINGS,
                CONF_ACTION_MANAGE_PEOPLE,
            ],
        )

    async def async_step_add_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new area via the wizard."""
        self._area_being_edited = None
        self._area_config_draft = {}
        self._init_area_wizard()
        return await self.async_step_area_basics()

    async def async_step_manage_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show list of areas to manage."""
        errors: dict[str, str] = {}
        areas = self._get_areas_from_config()

        if user_input is not None:
            selected_option = user_input.get("selected_option", "")
            if selected_option.startswith(CONF_OPTION_PREFIX_AREA):
                sanitized_id = selected_option.replace(CONF_OPTION_PREFIX_AREA, "", 1)
                area = _find_area_by_sanitized_id(areas, sanitized_id)
                if area:
                    self._area_being_edited = area.get(CONF_AREA_ID)
                    return await self.async_step_area_action()
                errors["base"] = "Selected area could not be found"

        return self.async_show_form(
            step_id="manage_areas",
            data_schema=_create_area_selector_schema(
                areas,
                hass=self.hass,
                global_options=self._get_global_options(),
            ),
            errors=errors,
        )

    async def async_step_area_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle action selection for a specific area via menu."""
        area_id = self._area_being_edited
        if not area_id:
            return await self.async_step_init()

        areas = self._get_areas_from_config()
        area_config = find_area_by_id(areas, area_id)
        if not area_config:
            return await self.async_step_init()

        description_placeholders = _build_area_description_placeholders(
            area_config,
            area_id,
            self.hass,
            self._get_global_options(),
        )

        return self.async_show_menu(
            step_id="area_action",
            menu_options=[
                *AREA_EDIT_SPOKES,
                "edit_area",
                "reset_learning_confirm",
                "remove_area_confirm",
                "cancel_area_action",
            ],
            description_placeholders=description_placeholders,
        )

    async def async_step_edit_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected area."""
        self._prepare_area_action_edit()
        self._init_area_wizard()
        return await self.async_step_area_basics()

    async def async_step_remove_area_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initiate area removal."""
        self._prepare_area_action_remove()
        return await self.async_step_remove_area()

    async def async_step_reset_learning_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initiate learning reset for the area being edited."""
        self._area_to_reset = self._area_being_edited
        return await self.async_step_reset_learning()

    async def async_step_cancel_area_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel area action and return to main menu."""
        self._prepare_area_action_cancel()
        return await self.async_step_init()

    async def async_step_remove_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm removal of an area via menu."""
        area_id = self._area_to_remove
        if not area_id:
            return await self.async_step_init()

        return self.async_show_menu(
            step_id="remove_area",
            menu_options=["confirm_remove_area", "cancel_remove_area"],
        )

    async def async_step_confirm_remove_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Execute area removal."""
        area_id = self._area_to_remove
        if not area_id:
            return await self.async_step_init()

        areas = self._get_areas_from_config()
        surviving = remove_area_from_list(areas, area_id)
        if not surviving:
            return self.async_abort(reason="cannot_remove_last_area")

        # Strip the removed area from its neighbours before dropping it, so
        # no adjacency reference is left dangling.
        by_area_id = {
            data.get(CONF_AREA_ID): data for data in surviving if data.get(CONF_AREA_ID)
        }
        for subentry_id, existing in iter_area_subentries(self.config_entry):
            existing_area_id = existing.get(CONF_AREA_ID)
            if existing_area_id == area_id:
                self.hass.config_entries.async_remove_subentry(
                    self.config_entry, subentry_id
                )
                continue
            new_data = by_area_id.get(existing_area_id)
            if new_data is not None and new_data != existing:
                self.hass.config_entries.async_update_subentry(
                    self.config_entry,
                    self.config_entry.subentries[subentry_id],
                    data=new_data,
                )

        self._area_to_remove = None
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_cancel_remove_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel area removal."""
        self._area_to_remove = None
        return await self.async_step_init()

    async def async_step_reset_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Yes/no menu confirming learning reset for the selected area."""
        if not self._area_to_reset:
            return await self.async_step_init()

        return self.async_show_menu(
            step_id="reset_learning",
            menu_options=["confirm_reset_learning", "cancel_reset_learning"],
        )

    async def async_step_confirm_reset_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Execute the per-area learning reset.

        Wipes the area's learned history (intervals, priors, correlations,
        cache) without removing the area from the configuration. Returns to
        the area_action menu so the user can continue editing.
        """
        # Lazy import to avoid pulling service.py into the config-flow load path.
        from .service import (  # noqa: PLC0415
            _find_area_by_area_id,
            async_purge_area_data,
        )

        area_id = self._area_to_reset
        if not area_id:
            return await self.async_step_init()

        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None:
            _LOGGER.warning(
                "Reset learning aborted for area_id '%s': coordinator not loaded",
                area_id,
            )
            self._area_to_reset = None
            return self.async_abort(reason="reset_learning_failed")

        area_name, area = _find_area_by_area_id(coordinator, area_id)
        if area_name is None or area is None:
            _LOGGER.warning(
                "Reset learning aborted: no configured area found for area_id '%s'",
                area_id,
            )
            self._area_to_reset = None
            return self.async_abort(reason="reset_learning_failed")

        _LOGGER.info(
            "Resetting learned history for area '%s' (area_id=%s) via options flow",
            area_name,
            area_id,
        )

        try:
            await async_purge_area_data(self.hass, coordinator, area_name, area)
        except HomeAssistantError:
            _LOGGER.exception(
                "Reset learning failed for area '%s' (area_id=%s)", area_name, area_id
            )
            self._area_to_reset = None
            return self.async_abort(reason="reset_learning_failed")

        self._area_to_reset = None
        # Stay scoped to the same area so the user lands back in its menu.
        self._area_being_edited = area_id
        return await self.async_step_area_action()

    async def async_step_cancel_reset_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel the learning reset and return to the area_action menu."""
        area_id = self._area_to_reset
        self._area_to_reset = None
        if area_id:
            self._area_being_edited = area_id
            return await self.async_step_area_action()
        return await self.async_step_init()

    async def _async_get_global_settings_placeholders(self) -> dict[str, str]:
        """Build localized summary placeholders for the Global Settings menu."""
        options = self._get_global_options()
        translations = await _async_get_common_translations(self.hass)

        def _tr(key: str, **placeholders: Any) -> str:
            return _format_common_translation(translations, key, **placeholders)

        sleep_start = str(options.get(CONF_SLEEP_START, DEFAULT_SLEEP_START))[
            :_TIME_HHMM_LEN
        ]
        sleep_end = str(options.get(CONF_SLEEP_END, DEFAULT_SLEEP_END))[:_TIME_HHMM_LEN]
        sleep_decay = _format_seconds(self._get_global_sleep_decay_half_life())

        overrides = self._get_global_purpose_decay_half_lives()
        purpose_overrides = (
            _tr(_COMMON_KEY_PURPOSE_OVERRIDES_COUNT, count=len(overrides))
            if overrides
            else _tr(_COMMON_KEY_PURPOSE_OVERRIDES_DEFAULT)
        )

        health = _tr(
            _COMMON_KEY_STATE_ON
            if options.get(CONF_HEALTH_ENABLED, DEFAULT_HEALTH_ENABLED)
            else _COMMON_KEY_STATE_OFF
        )
        precision = str(options.get(CONF_SENSOR_PRECISION, DEFAULT_SENSOR_PRECISION))
        groups = _tr(
            _COMMON_KEY_GROUP_EXPAND
            if options.get(CONF_EXPAND_GROUPS, DEFAULT_GLOBAL_EXPAND_GROUPS)
            else _COMMON_KEY_GROUP_KEEP
        )
        away = options.get(CONF_AWAY_MODE_ENTITY) or _tr(
            _COMMON_KEY_AWAY_PERSON_TRACKING
        )

        return {
            _PLACEHOLDER_SLEEP_START: sleep_start,
            _PLACEHOLDER_SLEEP_END: sleep_end,
            _PLACEHOLDER_SLEEP_DECAY: sleep_decay,
            _PLACEHOLDER_PURPOSE_OVERRIDES: purpose_overrides,
            _PLACEHOLDER_HEALTH: health,
            _PLACEHOLDER_PRECISION: precision,
            _PLACEHOLDER_GROUPS: groups,
            _PLACEHOLDER_AWAY: str(away),
            _PLACEHOLDER_EXCLUDED_TYPES_COUNT: str(
                len(options.get(CONF_EXCLUDED_SENSOR_TYPES) or [])
            ),
            _PLACEHOLDER_EXCLUDED_DEVICES_COUNT: str(
                len(options.get(CONF_EXCLUDED_MANUFACTURERS) or [])
                + len(options.get(CONF_EXCLUDED_MODELS) or [])
            ),
            _PLACEHOLDER_EXCLUDED_ENTITIES_COUNT: str(
                len(options.get(CONF_EXCLUDED_SENSORS) or [])
            ),
            _PLACEHOLDER_EXCLUDED_INTEGRATIONS_COUNT: str(
                len(options.get(CONF_EXCLUDED_INTEGRATIONS) or [])
            ),
        }

    async def async_step_global_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the Global Settings menu grouped by category."""
        _ = user_input
        return self.async_show_menu(
            step_id=STEP_GLOBAL_SETTINGS,
            menu_options=[
                STEP_GLOBAL_SLEEP,
                STEP_GLOBAL_PURPOSE_DECAY,
                STEP_GLOBAL_GENERAL,
                STEP_GLOBAL_EXCLUSIONS,
            ],
            description_placeholders=(
                await self._async_get_global_settings_placeholders()
            ),
        )

    def _save_global_options(
        self,
        updates: Mapping[str, Any] | None = None,
        *,
        remove_keys: Collection[str] = (),
    ) -> ConfigFlowResult:
        """Persist updated integration-wide options on the config entry."""
        new_options = self._get_global_options()
        if updates:
            new_options.update(updates)
        for key in remove_keys:
            new_options.pop(key, None)
        return self.async_create_entry(title="", data=new_options)

    async def async_step_global_sleep(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage global sleep schedule and sleep presence decay settings."""
        errors: dict[str, str] = {}
        base_schema = _create_global_sleep_schema(self._get_global_options())

        if user_input is not None:
            validated = cast("dict[str, Any]", base_schema(user_input))
            sleep_half_life = duration_to_seconds(validated[CONF_SLEEP_DECAY_HALF_LIFE])
            if error := validate_sleep_decay_half_life(
                sleep_half_life, allow_zero=False
            ):
                errors[CONF_SLEEP_DECAY_HALF_LIFE] = error
            else:
                validated[CONF_SLEEP_DECAY_HALF_LIFE] = sleep_half_life
                return self._save_global_options(validated)

        return self.async_show_form(
            step_id=STEP_GLOBAL_SLEEP,
            data_schema=self._schema_with_input(base_schema, user_input),
            errors=errors,
            description_placeholders={
                _PLACEHOLDER_SLEEP_DECAY_BUILTIN_DEFAULT: _format_seconds(
                    SLEEP_PRESENCE_HALF_LIFE
                ),
            },
        )

    async def async_step_global_purpose_decay(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage global default decay half-lives for each room purpose."""
        errors: dict[str, str] = {}
        base_schema = _create_global_purpose_decay_schema(self._get_global_options())

        if user_input is not None:
            overrides, parsed_errors = _parse_purpose_decay_submission(
                cast("dict[str, Any]", base_schema(user_input))
            )
            errors.update(parsed_errors)
            if not errors:
                if overrides:
                    return self._save_global_options(
                        {CONF_PURPOSE_DECAY_HALF_LIVES: overrides}
                    )
                return self._save_global_options(
                    remove_keys=(CONF_PURPOSE_DECAY_HALF_LIVES,)
                )

        return self.async_show_form(
            step_id=STEP_GLOBAL_PURPOSE_DECAY,
            data_schema=self._schema_with_input(base_schema, user_input),
            errors=errors,
            description_placeholders={
                f"{purpose_def.purpose.value}{_PURPOSE_DEFAULT_PLACEHOLDER_SUFFIX}": (
                    _format_seconds(purpose_def.half_life)
                )
                for purpose_def in PURPOSE_DEFINITIONS.values()
            },
        )

    async def async_step_global_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage general integration-wide settings."""
        base_schema = _create_global_general_schema(self._get_global_options())

        if user_input is not None:
            validated = cast("dict[str, Any]", base_schema(user_input))
            remove_keys = (
                (CONF_AWAY_MODE_ENTITY,)
                if CONF_AWAY_MODE_ENTITY not in validated
                else ()
            )
            return self._save_global_options(validated, remove_keys=remove_keys)

        return self.async_show_form(
            step_id=STEP_GLOBAL_GENERAL,
            data_schema=base_schema,
        )

    async def async_step_global_exclusions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration-wide exclusions on one page."""
        base_schema = _create_global_exclusions_schema(
            self._get_global_options(), self.hass
        )
        if user_input is not None:
            exclusions = flatten_sectioned_input(
                cast("dict[str, Any]", base_schema(user_input))
            )
            return self._save_global_options(exclusions)

        return self.async_show_form(
            step_id=STEP_GLOBAL_EXCLUSIONS,
            data_schema=base_schema,
        )

    def _get_person_display_name(self, person_entity: str) -> str:
        """Get friendly display name for a person entity."""
        person_state = self.hass.states.get(person_entity)
        return (
            person_state.attributes.get("friendly_name", person_entity)
            if person_state
            else person_entity
        )

    async def async_step_manage_people(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage configured people for sleep tracking."""
        errors: dict[str, str] = {}
        people: list[dict[str, Any]] = list(
            self.config_entry.options.get(CONF_PEOPLE, [])
        )

        if user_input is not None:
            selected = user_input.get("selected_option", "")
            if selected == "add_person":
                self._person_being_edited = None
                return await self.async_step_person_config()
            if selected.startswith("person_"):
                try:
                    idx = int(selected.replace("person_", ""))
                except (ValueError, TypeError):
                    idx = -1
                if 0 <= idx < len(people):
                    self._person_being_edited = idx
                    return await self.async_step_person_action()
                errors["base"] = "invalid_selection"

        # Build options list - one entry per person
        options: list[SelectOptionDict] = []
        for i, person in enumerate(people):
            person_entity = person.get(CONF_PERSON_ENTITY, "unknown")
            sleep_area = person.get(CONF_PERSON_SLEEP_AREA, "unknown")

            area_name = sleep_area
            with contextlib.suppress(ValueError):
                area_name = _resolve_area_id_to_name(self.hass, sleep_area)

            person_name = self._get_person_display_name(person_entity)
            threshold = person.get(
                CONF_PERSON_CONFIDENCE_THRESHOLD, DEFAULT_SLEEP_CONFIDENCE_THRESHOLD
            )
            options.append(
                {
                    "value": f"person_{i}",
                    "label": f"{person_name} → {area_name} (threshold: {threshold}%)",
                }
            )

        options.append({"value": "add_person", "label": "Add Person"})

        schema = vol.Schema(
            {
                vol.Required("selected_option"): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="manage_people",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_person_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show action menu for a selected person."""
        idx = self._person_being_edited
        people: list[dict[str, Any]] = list(
            self.config_entry.options.get(CONF_PEOPLE, [])
        )
        if idx is None or not (0 <= idx < len(people)):
            return await self.async_step_init()

        person = people[idx]
        person_name = self._get_person_display_name(
            person.get(CONF_PERSON_ENTITY, "unknown")
        )

        return self.async_show_menu(
            step_id="person_action",
            menu_options=[
                "edit_person",
                "remove_person_confirm",
                "cancel_person_action",
            ],
            description_placeholders={"person_name": person_name},
        )

    async def async_step_edit_person(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected person."""
        return await self.async_step_person_config()

    async def async_step_remove_person_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initiate person removal."""
        self._person_to_remove = self._person_being_edited
        self._person_being_edited = None
        return await self.async_step_remove_person()

    async def async_step_cancel_person_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel person action and return to main menu."""
        self._person_being_edited = None
        return await self.async_step_init()

    async def async_step_remove_person(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm removal of a person via menu."""
        idx = self._person_to_remove
        people: list[dict[str, Any]] = list(
            self.config_entry.options.get(CONF_PEOPLE, [])
        )
        if idx is None or not (0 <= idx < len(people)):
            return await self.async_step_init()

        person = people[idx]
        person_name = self._get_person_display_name(
            person.get(CONF_PERSON_ENTITY, "unknown")
        )

        return self.async_show_menu(
            step_id="remove_person",
            menu_options=["confirm_remove_person", "cancel_remove_person"],
            description_placeholders={"person_name": person_name},
        )

    async def async_step_confirm_remove_person(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Execute person removal."""
        idx = self._person_to_remove
        people: list[dict[str, Any]] = list(
            self.config_entry.options.get(CONF_PEOPLE, [])
        )
        if idx is None or not (0 <= idx < len(people)):
            return await self.async_step_init()

        updated_people = [p for i, p in enumerate(people) if i != idx]
        config_data = dict(self.config_entry.options)
        config_data[CONF_PEOPLE] = updated_people
        result = self.async_create_entry(title="", data=config_data)
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(self.config_entry.entry_id)
        )
        self._person_to_remove = None
        return result

    async def async_step_cancel_remove_person(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cancel person removal."""
        self._person_to_remove = None
        return await self.async_step_init()

    async def async_step_person_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a person for sleep tracking."""
        errors: dict[str, str] = {}
        people: list[dict[str, Any]] = list(
            self.config_entry.options.get(CONF_PEOPLE, [])
        )

        # Get defaults for editing
        defaults: dict[str, Any] = {}
        idx = getattr(self, "_person_being_edited", None)
        if idx is not None and 0 <= idx < len(people):
            defaults = dict(people[idx])
            # Migrate old single-sensor key to list for form population
            if (
                CONF_PERSON_SLEEP_SENSORS not in defaults
                and CONF_PERSON_SLEEP_SENSOR in defaults
            ):
                old_val = defaults.pop(CONF_PERSON_SLEEP_SENSOR)
                defaults[CONF_PERSON_SLEEP_SENSORS] = [old_val] if old_val else []

        if user_input is not None:
            # Check for duplicate person entity before validation
            new_entity = user_input.get(CONF_PERSON_ENTITY, "")
            duplicate = any(
                existing.get(CONF_PERSON_ENTITY) == new_entity
                for i, existing in enumerate(people)
                if i != idx
            )
            if duplicate:
                errors["base"] = "person_already_configured"

            if not errors:
                try:
                    person_data = validate_person_input(user_input)

                    # Update or add person
                    updated_people = list(people)
                    if idx is not None and 0 <= idx < len(updated_people):
                        updated_people[idx] = person_data
                    else:
                        updated_people.append(person_data)

                    config_data = dict(self.config_entry.options)
                    config_data[CONF_PEOPLE] = updated_people
                    result = self.async_create_entry(title="", data=config_data)
                    # Trigger integration reload to update sleep presence sensors
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )

                except (vol.Invalid, ValueError, TypeError) as err:
                    errors["base"] = _handle_step_error(err)
                else:
                    return result

        base_schema = vol.Schema(
            {
                vol.Required(CONF_PERSON_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="person")
                ),
                vol.Required(CONF_PERSON_SLEEP_SENSORS): EntitySelector(
                    EntitySelectorConfig(
                        domain=["sensor", "binary_sensor"], multiple=True
                    )
                ),
                vol.Required(CONF_PERSON_SLEEP_AREA): AreaSelector(
                    AreaSelectorConfig()
                ),
                vol.Optional(
                    CONF_PERSON_CONFIDENCE_THRESHOLD,
                    default=DEFAULT_SLEEP_CONFIDENCE_THRESHOLD,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=100,
                        step=5,
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(CONF_PERSON_DEVICE_TRACKER): EntitySelector(
                    EntitySelectorConfig(domain="device_tracker")
                ),
            }
        )

        # Use suggested values for edit mode
        suggested = user_input if user_input is not None else defaults
        if suggested:
            data_schema = self.add_suggested_values_to_schema(base_schema, suggested)
        else:
            data_schema = base_schema

        return self.async_show_form(
            step_id="person_config",
            data_schema=data_schema,
            errors=errors,
        )
