"""Resolve typed sensors in a Home Assistant area without changing saved choices."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, TypedDict, cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_DEVICE_CLASS,
    ATTR_DEVICE_ID,
    ATTR_ENTITY_ID,
    ATTR_ICON,
    ATTR_ID,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    CONF_SOURCE,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    discovery_flow,
    entity_registry as er,
)
from homeassistant.helpers.event import async_call_later

from .config_helpers import (
    is_active_config_entry,
    iter_area_subentries,
    resolve_exclusion_enabled,
    resolve_group_expansion_enabled,
)
from .const import (
    ALL_AREA_SENSOR_KEYS,
    CONF_AIR_QUALITY_SENSORS,
    CONF_AREA_ID,
    CONF_AUTO_ADDED_SENSORS,
    CONF_AUTO_DISCOVER_DOMAINS,
    CONF_AUTO_DISCOVER_SENSORS,
    CONF_CO2_SENSORS,
    CONF_CO_SENSORS,
    CONF_COVER_SENSORS,
    CONF_DECAY_HALF_LIFE,
    CONF_DOOR_SENSORS,
    CONF_EXCLUDE_LIGHT_POWER,
    CONF_EXCLUDE_OCCUPANCY_SUBZONES,
    CONF_EXCLUDE_REMOTE_LOCKS,
    CONF_EXCLUDE_VEHICLE_DETECTED,
    CONF_EXCLUDED_INTEGRATIONS,
    CONF_EXCLUDED_MANUFACTURERS,
    CONF_EXCLUDED_MODELS,
    CONF_EXCLUDED_SENSOR_TYPES,
    CONF_EXCLUDED_SENSORS,
    CONF_EXPAND_GROUPS,
    CONF_HUMIDITY_SENSORS,
    CONF_ILLUMINANCE_SENSORS,
    CONF_LOCK_SENSORS,
    CONF_MEDIA_DEVICES,
    CONF_MOTION_SENSORS,
    CONF_PM10_SENSORS,
    CONF_PM25_SENSORS,
    CONF_POWER_SENSORS,
    CONF_PRESSURE_SENSORS,
    CONF_PURPOSE,
    CONF_SOUND_PRESSURE_SENSORS,
    CONF_TEMPERATURE_SENSORS,
    CONF_VOC_SENSORS,
    CONF_WINDOW_SENSORS,
    DEFAULT_AREA_EXCLUSION_SETTING,
    DEFAULT_AREA_EXPAND_GROUPS,
    DEFAULT_AUTO_DISCOVER_SENSORS,
    DEFAULT_DECAY_HALF_LIFE,
    DEFAULT_GLOBAL_EXPAND_GROUPS,
    DISCOVERY_EXCLUSION_RULES,
    DISCOVERY_UNIQUE_ID_PREFIX,
    DOMAIN,
    SENSOR_KEY_TO_TYPE_SLUG,
)
from .data.purpose import infer_purpose_from_name
from .discovery_filters import (
    ENTITY_ID_SEPARATOR,
    MOTION_BINARY_DEVICE_CLASSES,
    SpecialExclusionContext,
    collect_device_exclusion_filters,
    entity_domain,
    entity_state_and_attributes,
    find_excluded_device_entity_ids,
    garage_cover_device_ids,
    is_ineligible_entry,
    is_light_power_sensor,
    is_own_entry,
    is_special_excluded_entry,
    is_weather_entity,
    lookup_registry_entry,
    main_motion_classes_by_device_in_area,
    normalize_excluded_platforms,
    resolve_entry_device_class,
    state_attributes,
)

# Only unambiguous classes are automatic. Generic opening contacts, switches,
# appliances, sleep sensors, and Wi-Fi counts still need a user's interpretation.
_BINARY_CLASSES: Final[dict[str, str]] = {
    **dict.fromkeys(MOTION_BINARY_DEVICE_CLASSES, CONF_MOTION_SENSORS),
    BinarySensorDeviceClass.DOOR: CONF_DOOR_SENSORS,
    BinarySensorDeviceClass.GARAGE_DOOR: CONF_DOOR_SENSORS,
    BinarySensorDeviceClass.WINDOW: CONF_WINDOW_SENSORS,
}
_NUMERIC_CLASSES: Final[dict[str, str]] = {
    SensorDeviceClass.TEMPERATURE: CONF_TEMPERATURE_SENSORS,
    SensorDeviceClass.HUMIDITY: CONF_HUMIDITY_SENSORS,
    SensorDeviceClass.MOISTURE: CONF_HUMIDITY_SENSORS,
    SensorDeviceClass.ILLUMINANCE: CONF_ILLUMINANCE_SENSORS,
    SensorDeviceClass.CO2: CONF_CO2_SENSORS,
    SensorDeviceClass.CO: CONF_CO_SENSORS,
    SensorDeviceClass.SOUND_PRESSURE: CONF_SOUND_PRESSURE_SENSORS,
    SensorDeviceClass.PRESSURE: CONF_PRESSURE_SENSORS,
    SensorDeviceClass.ATMOSPHERIC_PRESSURE: CONF_PRESSURE_SENSORS,
    SensorDeviceClass.AQI: CONF_AIR_QUALITY_SENSORS,
    SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS: CONF_VOC_SENSORS,
    SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS: CONF_VOC_SENSORS,
    SensorDeviceClass.PM25: CONF_PM25_SENSORS,
    SensorDeviceClass.PM10: CONF_PM10_SENSORS,
    SensorDeviceClass.POWER: CONF_POWER_SENSORS,
    SensorDeviceClass.CURRENT: CONF_POWER_SENSORS,
}
_DOMAINS: Final[dict[str, str]] = {
    Platform.MEDIA_PLAYER: CONF_MEDIA_DEVICES,
    Platform.LOCK: CONF_LOCK_SENSORS,
    Platform.COVER: CONF_COVER_SENSORS,
}

DISCOVERABLE_SENSOR_KEYS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        (
            *_BINARY_CLASSES.values(),
            *_NUMERIC_CLASSES.values(),
            *_DOMAINS.values(),
        )
    )
)
_KEY_EXPECTED_DOMAINS: Final[dict[str, str]] = {
    **dict.fromkeys(_BINARY_CLASSES.values(), Platform.BINARY_SENSOR),
    **dict.fromkeys(_NUMERIC_CLASSES.values(), Platform.SENSOR),
    **{key: domain for domain, key in _DOMAINS.items()},
}

_DISCOVERY_DEBOUNCE_SECONDS: Final = 1
_DISCOVERY_KEY_VERSION: Final = 1
_ATTR_ORIGINAL_DEVICE_CLASS: Final = "original_device_class"
_ATTR_DISABLED_BY: Final = "disabled_by"
_ATTR_ENTITY_CATEGORY: Final = "entity_category"
_RELEVANT_REGISTRY_CHANGE_KEYS: Final[frozenset[str]] = frozenset(
    {
        ATTR_AREA_ID,
        ATTR_DEVICE_ID,
        ATTR_DEVICE_CLASS,
        ATTR_MANUFACTURER,
        ATTR_MODEL,
        _ATTR_ORIGINAL_DEVICE_CLASS,
        _ATTR_DISABLED_BY,
        _ATTR_ENTITY_CATEGORY,
        ATTR_ENTITY_ID,
    }
)
_EVENT_KEY_ACTION: Final = "action"
_EVENT_ACTION_UPDATE: Final = "update"
_EVENT_KEY_CHANGES: Final = "changes"
_FLOW_KEY_CONTEXT: Final = "context"
_FLOW_KEY_ID: Final = "flow_id"

_ATTR_CONFIG: Final = "config"
_ATTR_LANGUAGE: Final = "language"
_ATTR_ALIASES: Final = "aliases"
_ATTR_ASYNC_LIST_AREAS: Final = "async_list_areas"
_ATTR_AREAS: Final = "areas"
_ATTR_ASYNC_PROGRESS_BY_HANDLER: Final = "async_progress_by_handler"
_ATTR_CONFIG_ENTRIES: Final = "config_entries"
_ATTR_FLOW: Final = "flow"
_ATTR_DATA: Final = "data"


class AreaDiscoveryKwargs(TypedDict):
    """Keyword arguments passed from area config to ``discover_area_sensors``."""

    expand_groups: str
    enabled_domains: Collection[str]
    excluded_platforms: Collection[str] | None
    exclude_light_power: str
    exclude_occupancy_subzones: str
    exclude_remote_locks: str
    exclude_vehicle_detected: str
    excluded_entities: Collection[str]
    global_options: Mapping[str, Any]
    precomputed_device_exclusions: bool


@dataclass(frozen=True, slots=True)
class _AreaDiscoveryOptions:
    """Normalized inputs for building area discovery filters."""

    expand_groups: str
    enabled_domains: Collection[str] | None
    excluded_platforms: Collection[str] | None
    exclusion_overrides: Mapping[str, str]
    excluded_manufacturers: Collection[str] | None
    excluded_models: Collection[str] | None
    excluded_entities: Collection[str] | None
    global_options: Mapping[str, Any]
    precomputed_device_exclusions: bool


@dataclass(frozen=True, slots=True)
class _AreaDiscoveryFilters:
    """Resolved discovery toggles, domains, and exclusions for one area scan."""

    expand_groups: bool
    allowed_domains: set[str] | None
    excluded_platforms: set[str]
    excluded_entity_ids: set[str]
    excluded_type_keys: set[str]
    enabled_exclusions: frozenset[str]

    def is_excluded(self, rule_key: str) -> bool:
        """Return True when the given discovery exclusion rule is active."""
        return rule_key in self.enabled_exclusions


@dataclass(frozen=True, slots=True)
class _AreaScanContext:
    """Precomputed filters and device context for scanning one area."""

    filters: _AreaDiscoveryFilters
    special_exclusions: SpecialExclusionContext


@dataclass(frozen=True, slots=True)
class _AreaPurposeHints:
    """Metadata collected from Home Assistant to infer an area's purpose."""

    area_name: str
    language: str | None
    icon: str | None
    aliases: list[str] | None


def is_auto_discovery_enabled(data: Mapping[str, Any]) -> bool:
    """Return True when automatic sensor discovery is enabled for an area."""
    return bool(data.get(CONF_AUTO_DISCOVER_SENSORS, DEFAULT_AUTO_DISCOVER_SENSORS))


def _excluded_sensor_keys(global_options: Mapping[str, Any]) -> set[str]:
    """Return area config keys covered by global sensor type exclusions."""
    excluded_types = global_options.get(CONF_EXCLUDED_SENSOR_TYPES) or ()
    normalized = {item for item in excluded_types if isinstance(item, str)}
    return {
        key
        for key, sensor_type in SENSOR_KEY_TO_TYPE_SLUG.items()
        if sensor_type in normalized
    }


def _get_entity_registry(hass: HomeAssistant) -> er.EntityRegistry | None:
    """Safely look up the entity registry without failing on bare mocks."""
    try:
        return er.async_get(hass)
    except (AttributeError, KeyError, RuntimeError, TypeError):
        return None


def _get_group_members(hass: HomeAssistant, entity_id: str) -> list[str] | None:
    """Return member entity IDs if ``entity_id`` is a group, otherwise ``None``."""
    attrs = state_attributes(hass, entity_id)
    members = attrs.get(ATTR_ENTITY_ID) if attrs else None
    if not isinstance(members, (list, tuple)):
        return None
    return [
        member
        for member in cast("list[Any] | tuple[Any, ...]", members)
        if isinstance(member, str) and ENTITY_ID_SEPARATOR in member
    ]


def _is_own_entity(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
) -> bool:
    """Return True if ``entity_id`` belongs to this integration."""
    entry = lookup_registry_entry(entity_id, registry, hass=hass)
    return entry is not None and is_own_entry(entry)


def _group_contains_own_entity(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
    _visited: frozenset[str] | None = None,
) -> bool:
    """Return True if a group directly or recursively contains an own entity."""
    visited = _visited if _visited is not None else frozenset()
    if entity_id in visited:
        return False

    members = _get_group_members(hass, entity_id)
    if members is None:
        return _is_own_entity(hass, entity_id, registry)

    next_visited = visited | {entity_id}
    return any(
        _group_contains_own_entity(hass, member_id, registry, next_visited)
        for member_id in members
    )


def _expand_group_entity(
    hass: HomeAssistant,
    entity_id: str,
    required_domain: str | None = None,
    _visited: frozenset[str] | None = None,
    *,
    registry: er.EntityRegistry | None = None,
    excluded_entity_ids: Collection[str] = (),
    excluded_platforms: set[str] | None = None,
) -> list[str]:
    """Expand a group entity recursively into domain-filtered member entity IDs."""
    visited = _visited if _visited is not None else frozenset()
    if entity_id in visited or entity_id in excluded_entity_ids:
        return []

    members = _get_group_members(hass, entity_id)
    if members is None:
        if _is_own_entity(hass, entity_id, registry):
            return []
        if required_domain is not None and entity_domain(entity_id) != required_domain:
            return []
        return [entity_id]

    if visited and excluded_platforms is not None:
        entry = lookup_registry_entry(entity_id, registry, hass=hass)
        if entry is not None and is_ineligible_entry(hass, entry, excluded_platforms):
            return []

    effective_domain = required_domain
    group_domain = entity_domain(entity_id)
    if effective_domain is None and group_domain != GROUP_DOMAIN:
        effective_domain = group_domain

    next_visited = visited | {entity_id}
    expanded: list[str] = []
    for member_id in members:
        expanded.extend(
            _expand_group_entity(
                hass,
                member_id,
                required_domain=effective_domain,
                _visited=next_visited,
                registry=registry,
                excluded_entity_ids=excluded_entity_ids,
                excluded_platforms=excluded_platforms,
            )
        )
    return list(dict.fromkeys(expanded))


def excluded_device_entity_ids(
    hass: HomeAssistant,
    *,
    manufacturers: Collection[str] | None = None,
    models: Collection[str] | None = None,
) -> set[str]:
    """Return entity IDs whose device manufacturer or model matches a filter."""
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    return find_excluded_device_entity_ids(
        registry,
        devices,
        manufacturers=manufacturers,
        models=models,
    )


def collect_excluded_sensor_ids(
    excluded_entities: Collection[str] | None,
    global_options: Mapping[str, Any] | None = None,
) -> set[str]:
    """Collect normalized excluded entity IDs from area and global options."""
    global_opts = global_options or {}
    return {
        entity_id
        for entity_id in (
            *(excluded_entities or ()),
            *(global_opts.get(CONF_EXCLUDED_SENSORS) or ()),
        )
        if isinstance(entity_id, str)
    }


def resolve_excluded_device_entity_ids(
    hass: HomeAssistant | None,
    area_data: Mapping[str, Any],
    global_options: Mapping[str, Any] | None = None,
) -> set[str]:
    """Return entity IDs blocked by area or global device exclusion filters."""
    if hass is None:
        return set()
    manufacturers, models = collect_device_exclusion_filters(area_data, global_options)
    if not manufacturers and not models:
        return set()
    return excluded_device_entity_ids(
        hass,
        manufacturers=manufacturers,
        models=models,
    )


def _resolve_all_excluded_entities(
    hass: HomeAssistant,
    excluded_entities: Collection[str] | None,
    device_filter_data: Mapping[str, Any],
    global_options: Mapping[str, Any],
) -> set[str]:
    """Combine entity-level and device-level exclusions for an area."""
    excluded = collect_excluded_sensor_ids(excluded_entities, global_options)
    excluded.update(
        resolve_excluded_device_entity_ids(hass, device_filter_data, global_options)
    )
    return excluded


def _map_sensor_key(domain: str, device_class: str | None) -> str | None:
    """Map an entity's domain and device class to an area sensor config key."""
    if domain == Platform.BINARY_SENSOR:
        return _BINARY_CLASSES.get(device_class) if device_class else None
    if domain == Platform.SENSOR:
        return _NUMERIC_CLASSES.get(device_class) if device_class else None
    return _DOMAINS.get(domain)


def _classify_entity(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    entity_id: str,
    *,
    entry: er.RegistryEntry | None = None,
    fallback_domain: str | None = None,
    fallback_device_class: str | None = None,
    excluded_platforms: set[str] | None = None,
    exclude_light_power: bool,
    check_eligibility: bool = True,
) -> str | None:
    """Classify an entity ID into a sensor config key, or ``None`` if ineligible."""
    excluded = excluded_platforms or set()
    if entry is None:
        entry = lookup_registry_entry(entity_id, registry, hass=hass)
    if entry is not None:
        if check_eligibility and is_ineligible_entry(hass, entry, excluded):
            return None
        domain = entry.domain
        device_class = resolve_entry_device_class(
            hass,
            entry,
            entity_id,
            fallback_domain=fallback_domain,
            fallback_device_class=fallback_device_class,
        )
    else:
        if is_weather_entity(entity_id, None):
            return None
        state, attrs = entity_state_and_attributes(hass, entity_id)
        if state is None:
            return None
        domain = entity_domain(entity_id)
        device_class = resolve_entry_device_class(
            hass,
            None,
            entity_id,
            fallback_domain=fallback_domain,
            fallback_device_class=fallback_device_class,
            attrs=attrs,
        )

    key = _map_sensor_key(domain, device_class)
    if (
        key == CONF_POWER_SENSORS
        and exclude_light_power
        and is_light_power_sensor(hass, entity_id, entry=entry, registry=registry)
    ):
        return None
    return key


def get_enabled_discovery_domains(data: Mapping[str, Any]) -> set[str]:
    """Return sensor config keys enabled for auto-discovery, defaulting to all."""
    raw_domains = data.get(CONF_AUTO_DISCOVER_DOMAINS)
    if raw_domains is None:
        return set(DISCOVERABLE_SENSOR_KEYS)
    return {domain for domain in raw_domains if domain in DISCOVERABLE_SENSOR_KEYS}


def _append_discovered(
    discovered: dict[str, list[str]],
    filters: _AreaDiscoveryFilters,
    key: str | None,
    entity_id: str,
) -> None:
    """Record ``entity_id`` under ``key`` if allowed and not excluded."""
    if key is None:
        return
    if key in filters.excluded_type_keys:
        return
    if filters.allowed_domains is not None and key not in filters.allowed_domains:
        return
    target = discovered.setdefault(key, [])
    if entity_id not in target:
        target.append(entity_id)


def _resolve_expand_groups(
    area_setting: str,
    global_options: Mapping[str, Any],
) -> bool:
    """Resolve the tri-state group-expansion setting against global defaults."""
    return resolve_group_expansion_enabled(
        area_setting,
        global_options.get(CONF_EXPAND_GROUPS, DEFAULT_GLOBAL_EXPAND_GROUPS),
    )


def _resolve_enabled_exclusions(
    area_overrides: Mapping[str, str],
    global_options: Mapping[str, Any],
) -> frozenset[str]:
    """Resolve all tri-state discovery exclusion rules from authoritative rule metadata."""
    return frozenset(
        rule.config_key
        for rule in DISCOVERY_EXCLUSION_RULES
        if resolve_exclusion_enabled(
            area_overrides.get(rule.config_key, DEFAULT_AREA_EXCLUSION_SETTING),
            global_options.get(rule.config_key, rule.global_default),
            setting_name=rule.setting_label,
        )
    )


def _resolve_excluded_platforms(
    excluded_platforms: Collection[str] | None,
    global_options: Mapping[str, Any],
) -> set[str]:
    """Combine area-level and global integration exclusions."""
    excluded_set = normalize_excluded_platforms(excluded_platforms)
    excluded_set.update(
        normalize_excluded_platforms(global_options.get(CONF_EXCLUDED_INTEGRATIONS))
    )
    return excluded_set


def _build_area_discovery_filters(
    hass: HomeAssistant,
    options: _AreaDiscoveryOptions,
) -> _AreaDiscoveryFilters:
    """Resolve area and global options into a single discovery filter bundle."""
    global_options = options.global_options
    if options.precomputed_device_exclusions:
        excluded_entity_ids = collect_excluded_sensor_ids(
            options.excluded_entities, global_options
        )
    else:
        device_filter_data = {
            CONF_EXCLUDED_MANUFACTURERS: options.excluded_manufacturers,
            CONF_EXCLUDED_MODELS: options.excluded_models,
        }
        excluded_entity_ids = _resolve_all_excluded_entities(
            hass, options.excluded_entities, device_filter_data, global_options
        )

    return _AreaDiscoveryFilters(
        expand_groups=_resolve_expand_groups(options.expand_groups, global_options),
        allowed_domains=(
            set(options.enabled_domains)
            if options.enabled_domains is not None
            else None
        ),
        excluded_platforms=_resolve_excluded_platforms(
            options.excluded_platforms, global_options
        ),
        excluded_entity_ids=excluded_entity_ids,
        excluded_type_keys=_excluded_sensor_keys(global_options),
        enabled_exclusions=_resolve_enabled_exclusions(
            options.exclusion_overrides, global_options
        ),
    )


def _collect_area_entries(
    registry: er.EntityRegistry,
    devices: dr.DeviceRegistry,
    area_id: str,
) -> list[tuple[er.RegistryEntry, dr.DeviceEntry | None]]:
    """Return sorted ``(entry, device)`` pairs belonging to ``area_id``."""
    area_entries: list[tuple[er.RegistryEntry, dr.DeviceEntry | None]] = []
    for entry in registry.entities.values():
        if entry.area_id is not None:
            if entry.area_id != area_id:
                continue
            device = devices.async_get(entry.device_id) if entry.device_id else None
            area_entries.append((entry, device))
            continue
        device = devices.async_get(entry.device_id) if entry.device_id else None
        if device is not None and device.area_id == area_id:
            area_entries.append((entry, device))
    area_entries.sort(key=lambda item: item[0].entity_id)
    return area_entries


def _build_area_scan_context(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    area_entries: Collection[tuple[er.RegistryEntry, dr.DeviceEntry | None]],
    filters: _AreaDiscoveryFilters,
) -> _AreaScanContext:
    """Build per-area device lookup context used when evaluating exclusions."""
    exclude_remote_locks = filters.is_excluded(CONF_EXCLUDE_REMOTE_LOCKS)
    exclude_occupancy_subzones = filters.is_excluded(CONF_EXCLUDE_OCCUPANCY_SUBZONES)
    exclude_vehicle_detected = filters.is_excluded(CONF_EXCLUDE_VEHICLE_DETECTED)

    has_lock_candidates = any(
        entry.domain == Platform.LOCK
        or (filters.expand_groups and entry.domain == GROUP_DOMAIN)
        for entry, _ in area_entries
    )
    garage_device_ids: set[str] = (
        garage_cover_device_ids(hass, registry)
        if exclude_remote_locks and has_lock_candidates
        else set()
    )
    main_classes_by_device = (
        main_motion_classes_by_device_in_area(
            hass,
            area_entries,
            excluded_platforms=filters.excluded_platforms,
            excluded_entity_ids=filters.excluded_entity_ids,
            exclude_vehicle_detected=exclude_vehicle_detected,
        )
        if exclude_occupancy_subzones
        else {}
    )
    return _AreaScanContext(
        filters=filters,
        special_exclusions=SpecialExclusionContext(
            exclude_remote_locks=exclude_remote_locks,
            exclude_vehicle_detected=exclude_vehicle_detected,
            exclude_occupancy_subzones=exclude_occupancy_subzones,
            garage_device_ids=garage_device_ids,
            main_classes_by_device=main_classes_by_device,
        ),
    )


def _member_matches_group_classification(
    hass: HomeAssistant,
    member_id: str,
    *,
    member_entry: er.RegistryEntry | None,
    expected_domain: str,
    expected_key: str,
) -> bool:
    """Return True if a member's own classification matches the enclosing group."""
    if member_entry is not None:
        member_domain = member_entry.domain
        member_dc = resolve_entry_device_class(hass, member_entry, member_id)
    else:
        state, attrs = entity_state_and_attributes(hass, member_id)
        if state is None:
            return True
        member_domain = entity_domain(member_id)
        member_dc = resolve_entry_device_class(hass, None, member_id, attrs=attrs)

    if member_dc is None:
        return member_domain == expected_domain
    return _map_sensor_key(member_domain, member_dc) == expected_key


def _is_eligible_expanded_member(
    hass: HomeAssistant,
    member_id: str,
    member_entry: er.RegistryEntry | None,
    scan_ctx: _AreaScanContext,
) -> bool:
    """Return True if an expanded group member is eligible for area discovery."""
    if member_entry is not None:
        return not is_ineligible_entry(
            hass, member_entry, scan_ctx.filters.excluded_platforms
        ) and not is_special_excluded_entry(
            hass, member_entry, scan_ctx.special_exclusions
        )
    if is_weather_entity(member_id, None):
        return False
    state, _ = entity_state_and_attributes(hass, member_id)
    return state is not None


def _expand_and_collect_group(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    entry: er.RegistryEntry,
    scan_ctx: _AreaScanContext,
    discovered: dict[str, list[str]],
) -> bool:
    """Expand a group registry entry when its members match its classification.

    Returns ``True`` if the group was expanded (or skipped as a non-discoverable
    typed group only via fallback), or ``False`` when the caller should fall
    through to evaluate the group entity itself.
    """
    filters = scan_ctx.filters
    required_domain = entry.domain if entry.domain != GROUP_DOMAIN else None
    group_dc = resolve_entry_device_class(hass, entry)
    group_key = _map_sensor_key(entry.domain, group_dc)
    if entry.domain != GROUP_DOMAIN and group_dc is not None and group_key is None:
        return False

    eligible_members: list[tuple[str, er.RegistryEntry | None]] = []
    for member_id in _expand_group_entity(
        hass,
        entry.entity_id,
        required_domain=required_domain,
        registry=registry,
        excluded_entity_ids=filters.excluded_entity_ids,
        excluded_platforms=filters.excluded_platforms,
    ):
        member_entry = lookup_registry_entry(member_id, registry, hass=hass)
        if _is_eligible_expanded_member(hass, member_id, member_entry, scan_ctx):
            eligible_members.append((member_id, member_entry))

    if (
        entry.domain != GROUP_DOMAIN
        and group_dc is not None
        and group_key is not None
        and any(
            not _member_matches_group_classification(
                hass,
                member_id,
                member_entry=member_entry,
                expected_domain=entry.domain,
                expected_key=group_key,
            )
            for member_id, member_entry in eligible_members
        )
    ):
        return False

    exclude_light_power = filters.is_excluded(CONF_EXCLUDE_LIGHT_POWER)
    for member_id, member_entry in eligible_members:
        key = _classify_entity(
            hass,
            registry,
            member_id,
            entry=member_entry,
            fallback_domain=entry.domain,
            fallback_device_class=group_dc,
            excluded_platforms=filters.excluded_platforms,
            exclude_light_power=exclude_light_power,
            check_eligibility=False,
        )
        _append_discovered(discovered, filters, key, member_id)
    return True


def _discover_entry_sensors(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    entry: er.RegistryEntry,
    scan_ctx: _AreaScanContext,
    discovered: dict[str, list[str]],
) -> None:
    """Classify a single area registry entry and append any discovered sensors."""
    filters = scan_ctx.filters
    if entry.entity_id in filters.excluded_entity_ids:
        return
    if is_ineligible_entry(hass, entry, filters.excluded_platforms):
        return
    if is_special_excluded_entry(hass, entry, scan_ctx.special_exclusions):
        return

    is_group = _get_group_members(hass, entry.entity_id) is not None
    if (
        filters.expand_groups
        and is_group
        and _expand_and_collect_group(hass, registry, entry, scan_ctx, discovered)
    ):
        return

    if is_group and _group_contains_own_entity(hass, entry.entity_id, registry):
        return

    key = _classify_entity(
        hass,
        registry,
        entry.entity_id,
        entry=entry,
        excluded_platforms=filters.excluded_platforms,
        exclude_light_power=filters.is_excluded(CONF_EXCLUDE_LIGHT_POWER),
        check_eligibility=False,
    )
    _append_discovered(discovered, filters, key, entry.entity_id)


def discover_area_sensors(
    hass: HomeAssistant,
    area_id: str | None,
    *,
    expand_groups: str = DEFAULT_AREA_EXPAND_GROUPS,
    enabled_domains: Collection[str] | None = None,
    excluded_platforms: Collection[str] | None = None,
    exclude_light_power: str = DEFAULT_AREA_EXCLUSION_SETTING,
    exclude_occupancy_subzones: str = DEFAULT_AREA_EXCLUSION_SETTING,
    exclude_remote_locks: str = DEFAULT_AREA_EXCLUSION_SETTING,
    exclude_vehicle_detected: str = DEFAULT_AREA_EXCLUSION_SETTING,
    excluded_manufacturers: Collection[str] | None = None,
    excluded_models: Collection[str] | None = None,
    excluded_entities: Collection[str] | None = None,
    global_options: Mapping[str, Any] | None = None,
    precomputed_device_exclusions: bool = False,
) -> dict[str, list[str]]:
    """Return eligible discoverable entities grouped by sensor config key for an area.

    Disabled, diagnostic/config, integration-owned, outdoor weather, and
    excluded-integration entities are skipped. Group expansion follows the
    global setting unless explicitly overridden by the area. When
    ``enabled_domains`` is given, only matching sensor config keys are returned.
    Area exclusion settings follow or override their global counterparts.
    """
    if not area_id or (enabled_domains is not None and not enabled_domains):
        return {}

    options = _AreaDiscoveryOptions(
        expand_groups=expand_groups,
        enabled_domains=enabled_domains,
        excluded_platforms=excluded_platforms,
        exclusion_overrides={
            CONF_EXCLUDE_LIGHT_POWER: exclude_light_power,
            CONF_EXCLUDE_OCCUPANCY_SUBZONES: exclude_occupancy_subzones,
            CONF_EXCLUDE_REMOTE_LOCKS: exclude_remote_locks,
            CONF_EXCLUDE_VEHICLE_DETECTED: exclude_vehicle_detected,
        },
        excluded_manufacturers=excluded_manufacturers,
        excluded_models=excluded_models,
        excluded_entities=excluded_entities,
        global_options=global_options or {},
        precomputed_device_exclusions=precomputed_device_exclusions,
    )
    filters = _build_area_discovery_filters(hass, options)

    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    area_entries = _collect_area_entries(registry, devices, area_id)
    if not area_entries:
        return {}

    scan_ctx = _build_area_scan_context(hass, registry, area_entries, filters)

    discovered: dict[str, list[str]] = {}
    for entry, _ in area_entries:
        _discover_entry_sensors(hass, registry, entry, scan_ctx, discovered)

    return discovered


def parse_tracked_auto_sensors(
    data: Mapping[str, Any],
    *,
    allowed_keys: Collection[str] | None = None,
    excluded_keys: Collection[str] = (),
) -> dict[str, list[str]]:
    """Extract normalized per-key auto-added sensor lists from area config."""
    tracked_auto: dict[str, list[str]] = {}
    raw_tracked_auto = data.get(CONF_AUTO_ADDED_SENSORS)
    if not isinstance(raw_tracked_auto, Mapping):
        return tracked_auto
    allowed_set = set(allowed_keys) if allowed_keys is not None else None
    excluded_set = set(excluded_keys)
    for key, entity_ids in cast("Mapping[Any, Any]", raw_tracked_auto).items():
        if not isinstance(key, str) or key in excluded_set:
            continue
        if allowed_set is not None and key not in allowed_set:
            continue
        if isinstance(entity_ids, list):
            tracked_auto[key] = [
                entity_id
                for entity_id in cast("list[Any]", entity_ids)
                if isinstance(entity_id, str)
            ]
    return tracked_auto


def build_area_discovery_kwargs(
    area_data: Mapping[str, Any],
    *,
    enabled_domains: Collection[str],
    excluded_entities: Collection[str],
    global_options: Mapping[str, Any],
) -> AreaDiscoveryKwargs:
    """Build shared keyword arguments for ``discover_area_sensors``."""
    exclusion_kwargs = {
        rule.config_key: area_data.get(rule.config_key, DEFAULT_AREA_EXCLUSION_SETTING)
        for rule in DISCOVERY_EXCLUSION_RULES
    }
    return cast(
        "AreaDiscoveryKwargs",
        {
            CONF_EXPAND_GROUPS: area_data.get(
                CONF_EXPAND_GROUPS, DEFAULT_AREA_EXPAND_GROUPS
            ),
            "enabled_domains": enabled_domains,
            "excluded_platforms": area_data.get(CONF_EXCLUDED_INTEGRATIONS),
            **exclusion_kwargs,
            "excluded_entities": excluded_entities,
            "global_options": global_options,
            "precomputed_device_exclusions": True,
        },
    )


def _strip_entities_from_area_lists(
    resolved: dict[str, Any],
    remove_for_key: Callable[[str], Collection[str]],
) -> None:
    """Remove per-key entity IDs from resolved sensor lists."""
    for key in ALL_AREA_SENSOR_KEYS:
        existing = resolved.get(key)
        if not isinstance(existing, list):
            continue
        to_remove = set(remove_for_key(key))
        if to_remove:
            resolved[key] = [
                entity_id
                for entity_id in cast("list[Any]", existing)
                if entity_id not in to_remove
            ]


def _expand_manual_groups(
    hass: HomeAssistant,
    resolved: dict[str, Any],
    excluded: set[str],
) -> None:
    """Expand configured group entities in place across sensor keys."""
    registry = _get_entity_registry(hass)
    for key in ALL_AREA_SENSOR_KEYS:
        existing = resolved.get(key)
        if not isinstance(existing, list):
            continue
        expected_domain = _KEY_EXPECTED_DOMAINS.get(key)
        expanded: list[str] = []
        for entity_id in cast("list[Any]", existing):
            if not isinstance(entity_id, str) or entity_id in excluded:
                continue
            if _get_group_members(hass, entity_id) is not None:
                member_ids = _expand_group_entity(
                    hass,
                    entity_id,
                    required_domain=expected_domain,
                    registry=registry,
                    excluded_entity_ids=excluded,
                )
                if expected_domain is not None and any(
                    not _member_matches_group_classification(
                        hass,
                        member_id,
                        member_entry=lookup_registry_entry(
                            member_id, registry, hass=hass
                        ),
                        expected_domain=expected_domain,
                        expected_key=key,
                    )
                    for member_id in member_ids
                ):
                    if not _group_contains_own_entity(hass, entity_id, registry):
                        expanded.append(entity_id)
                else:
                    expanded.extend(member_ids)
            else:
                expanded.append(entity_id)
        resolved[key] = list(dict.fromkeys(expanded))


def _strip_excluded_entities(
    resolved: dict[str, Any],
    tracked_auto: dict[str, list[str]],
    excluded: set[str],
) -> None:
    """Remove excluded entity IDs from resolved sensor lists and auto tracking."""
    if not excluded:
        return
    _strip_entities_from_area_lists(resolved, lambda _key: excluded)
    for key, entity_ids in tracked_auto.items():
        tracked_auto[key] = [
            entity_id for entity_id in entity_ids if entity_id not in excluded
        ]


def _clear_tracked_auto_sensors(
    resolved: dict[str, Any],
    tracked_auto: dict[str, list[str]],
    *,
    preserve_empty_key: bool,
) -> None:
    """Remove all tracked auto-added sensors when discovery cannot run."""
    _strip_entities_from_area_lists(resolved, lambda key: tracked_auto.get(key, ()))
    if preserve_empty_key:
        resolved[CONF_AUTO_ADDED_SENSORS] = {}


def _strip_stale_auto_sensors(
    resolved: dict[str, Any],
    tracked_auto: dict[str, list[str]],
    discovered: dict[str, list[str]],
) -> None:
    """Remove previously auto-added sensors that are no longer eligible."""
    _strip_entities_from_area_lists(
        resolved,
        lambda key: set(tracked_auto.get(key, ())) - set(discovered.get(key, ())),
    )


def _reconcile_auto_provenance(
    previously_auto: Collection[str],
    additions: Collection[str],
    eligible_discovered: set[str],
) -> list[str]:
    """Return ordered auto-added entity IDs still eligible after discovery."""
    return list(
        dict.fromkeys(
            entity_id
            for entity_id in (*previously_auto, *additions)
            if entity_id in eligible_discovered
        )
    )


def _merge_discovered_additions(
    resolved: dict[str, Any],
    tracked_auto: dict[str, list[str]],
    discovered: dict[str, list[str]],
    excluded: set[str],
) -> dict[str, list[str]]:
    """Append newly discovered entities and return cleaned auto-added provenance."""
    existing_entities = {
        entity_id
        for key in ALL_AREA_SENSOR_KEYS
        for entity_id in (resolved.get(key) or ())
    }
    resolved_auto: dict[str, list[str]] = {}
    for key, entity_ids in discovered.items():
        if not entity_ids:
            continue
        additions = [
            entity_id
            for entity_id in entity_ids
            if entity_id not in excluded and entity_id not in existing_entities
        ]
        if additions:
            resolved[key] = [*(resolved.get(key) or ()), *additions]
        cleaned = _reconcile_auto_provenance(
            tracked_auto.get(key, ()), additions, set(entity_ids)
        )
        if cleaned:
            resolved_auto[key] = cleaned
    return resolved_auto


def _reconcile_discovered_sensors(
    resolved: dict[str, Any],
    tracked_auto: dict[str, list[str]],
    discovered: dict[str, list[str]],
    excluded: set[str],
    *,
    preserve_empty_key: bool,
) -> None:
    """Merge discovered additions while stripping stale auto-added entities."""
    _strip_stale_auto_sensors(resolved, tracked_auto, discovered)
    cleaned_auto = _merge_discovered_additions(
        resolved, tracked_auto, discovered, excluded
    )
    if cleaned_auto or preserve_empty_key:
        resolved[CONF_AUTO_ADDED_SENSORS] = cleaned_auto


def resolve_area_sensors(
    hass: HomeAssistant,
    data: Mapping[str, Any],
    global_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge discovered inputs into a copy of the area's manual selections.

    Auto-discovery defaults to enabled. Group expansion follows the global
    setting unless explicitly overridden by the area. Area-specific and global
    entity exclusions strip matching entities and matching device entities are
    stripped from every sensor list, including saved selections and expanded
    group members.
    """
    resolved = dict(data)
    global_options = global_options or {}
    expand_groups = _resolve_expand_groups(
        data.get(CONF_EXPAND_GROUPS, DEFAULT_AREA_EXPAND_GROUPS),
        global_options,
    )

    excluded_type_keys = _excluded_sensor_keys(global_options)
    for key in excluded_type_keys:
        resolved.pop(key, None)

    tracked_auto = parse_tracked_auto_sensors(
        data, allowed_keys=ALL_AREA_SENSOR_KEYS, excluded_keys=excluded_type_keys
    )
    preserve_empty_key = CONF_AUTO_ADDED_SENSORS in data

    excluded = _resolve_all_excluded_entities(
        hass, data.get(CONF_EXCLUDED_SENSORS), data, global_options
    )

    if expand_groups:
        _expand_manual_groups(hass, resolved, excluded)
    _strip_excluded_entities(resolved, tracked_auto, excluded)

    enabled_domains = get_enabled_discovery_domains(data)
    if (
        not is_auto_discovery_enabled(data)
        or not data.get(CONF_AREA_ID)
        or not enabled_domains
    ):
        _clear_tracked_auto_sensors(
            resolved, tracked_auto, preserve_empty_key=preserve_empty_key
        )
        return resolved

    discovered = discover_area_sensors(
        hass,
        data[CONF_AREA_ID],
        **build_area_discovery_kwargs(
            data,
            enabled_domains=enabled_domains,
            excluded_entities=excluded,
            global_options=global_options,
        ),
    )
    _reconcile_discovered_sensors(
        resolved,
        tracked_auto,
        discovered,
        excluded,
        preserve_empty_key=preserve_empty_key,
    )
    return resolved


def area_discovery_unique_id(area_id: str) -> str:
    """Return the unique ID used by discovery flows for an HA area."""
    return f"{DISCOVERY_UNIQUE_ID_PREFIX}{area_id}"


def _extract_area_purpose_hints(
    hass: HomeAssistant,
    area_id: str,
    area_name: str | None,
    area_entry: ar.AreaEntry | None,
) -> _AreaPurposeHints:
    """Extract normalized name, language, icon, and alias hints for an area."""
    if area_entry is None:
        with contextlib.suppress(AttributeError, KeyError, RuntimeError, TypeError):
            area_entry = ar.async_get(hass).async_get_area(area_id)

    if area_name is None:
        raw_entry_name = getattr(area_entry, ATTR_NAME, None) if area_entry else None
        resolved_name = (
            raw_entry_name
            if isinstance(raw_entry_name, str) and raw_entry_name
            else area_id
        )
    else:
        resolved_name = area_name

    raw_language = getattr(getattr(hass, _ATTR_CONFIG, None), _ATTR_LANGUAGE, None)
    language = raw_language if isinstance(raw_language, str) else None
    raw_icon = getattr(area_entry, ATTR_ICON, None) if area_entry else None
    icon = raw_icon if isinstance(raw_icon, str) else None
    raw_aliases = getattr(area_entry, _ATTR_ALIASES, None) if area_entry else None
    aliases: list[str] | None = (
        [
            alias
            for alias in cast("Iterable[Any]", raw_aliases)
            if isinstance(alias, str)
        ]
        if isinstance(raw_aliases, (set, list, tuple, frozenset))
        else None
    )
    return _AreaPurposeHints(
        area_name=resolved_name,
        language=language,
        icon=icon,
        aliases=aliases,
    )


def build_suggested_area_config(
    hass: HomeAssistant,
    area_id: str,
    area_name: str | None = None,
    *,
    area_entry: ar.AreaEntry | None = None,
) -> dict[str, Any]:
    """Build a suggested initial configuration dict for a Home Assistant area."""
    hints = _extract_area_purpose_hints(hass, area_id, area_name, area_entry)
    return {
        CONF_AREA_ID: area_id,
        CONF_PURPOSE: infer_purpose_from_name(
            hints.area_name,
            language=hints.language,
            icon=hints.icon,
            aliases=hints.aliases,
        ),
        CONF_AUTO_DISCOVER_SENSORS: DEFAULT_AUTO_DISCOVER_SENSORS,
        CONF_AUTO_DISCOVER_DOMAINS: list(DISCOVERABLE_SENSOR_KEYS),
        CONF_EXPAND_GROUPS: DEFAULT_AREA_EXPAND_GROUPS,
        **{
            rule.config_key: DEFAULT_AREA_EXCLUSION_SETTING
            for rule in DISCOVERY_EXCLUSION_RULES
        },
        CONF_DECAY_HALF_LIFE: DEFAULT_DECAY_HALF_LIFE,
    }


def _iter_sorted_areas(hass: HomeAssistant) -> list[Any]:
    """Return Home Assistant area registry entries sorted case-insensitively by name."""
    area_reg = ar.async_get(hass)
    list_areas = getattr(area_reg, _ATTR_ASYNC_LIST_AREAS, None)
    areas_attr: Any = getattr(area_reg, _ATTR_AREAS, None)
    raw_areas: Iterable[Any] = (
        cast("Iterable[Any]", list_areas())
        if callable(list_areas)
        else (
            cast("Mapping[Any, Any]", areas_attr).values()
            if isinstance(areas_attr, Mapping)
            else ()
        )
    )
    return sorted(
        raw_areas,
        key=lambda area: str(
            getattr(area, ATTR_NAME, None) or getattr(area, ATTR_ID, "")
        ).lower(),
    )


def discover_eligible_areas(
    hass: HomeAssistant,
    excluded_area_ids: set[str] | None = None,
    global_options: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return suggested configs for unconfigured HA areas with motion sensors."""
    suggestions: list[dict[str, Any]] = []
    for area in _iter_sorted_areas(hass):
        area_id = getattr(area, ATTR_ID, None)
        if (
            not isinstance(area_id, str)
            or not area_id
            or (excluded_area_ids and area_id in excluded_area_ids)
        ):
            continue
        discovered = discover_area_sensors(hass, area_id, global_options=global_options)
        if discovered.get(CONF_MOTION_SENSORS):
            raw_area_name = getattr(area, ATTR_NAME, None)
            suggestions.append(
                build_suggested_area_config(
                    hass,
                    area_id,
                    raw_area_name if isinstance(raw_area_name, str) else None,
                    area_entry=area,
                )
            )
    return suggestions


def _collect_entry_state(
    entries: Iterable[ConfigEntry],
) -> tuple[set[str], set[str], ConfigEntry | None]:
    """Extract configured area IDs, ignored discovery UIDs, and active entry."""
    configured_area_ids: set[str] = set()
    ignored_unique_ids: set[str] = set()
    active_entry: ConfigEntry | None = None

    for entry in entries:
        if not is_active_config_entry(entry):
            if entry.unique_id:
                ignored_unique_ids.add(str(entry.unique_id))
            continue
        if active_entry is None:
            active_entry = entry
        for _, data in iter_area_subentries(entry):
            if area_id := data.get(CONF_AREA_ID):
                configured_area_ids.add(str(area_id))

    return configured_area_ids, ignored_unique_ids, active_entry


def _abort_stale_discovery_flows(
    flow_mgr: Any,
    eligible_ids: set[str],
    ignored_unique_ids: set[str],
) -> None:
    """Abort in-progress area discovery flows that are no longer eligible."""
    if flow_mgr is None or not hasattr(flow_mgr, _ATTR_ASYNC_PROGRESS_BY_HANDLER):
        return
    in_progress = flow_mgr.async_progress_by_handler(DOMAIN)
    if not isinstance(in_progress, list):
        return
    for flow in cast("list[dict[str, Any]]", in_progress):
        context = flow.get(_FLOW_KEY_CONTEXT, {})
        if context.get(CONF_SOURCE) != SOURCE_INTEGRATION_DISCOVERY:
            continue
        uid = str(context.get(CONF_UNIQUE_ID) or "")
        if not uid.startswith(DISCOVERY_UNIQUE_ID_PREFIX):
            continue
        flow_area_id = uid.removeprefix(DISCOVERY_UNIQUE_ID_PREFIX)
        if flow_area_id not in eligible_ids or uid in ignored_unique_ids:
            flow_mgr.async_abort(flow[_FLOW_KEY_ID])


def _create_area_discovery_flows(
    hass: HomeAssistant,
    eligible: Iterable[Mapping[str, Any]],
    ignored_unique_ids: set[str],
) -> None:
    """Trigger Home Assistant discovery flows for eligible unconfigured areas."""
    if not isinstance(getattr(hass, _ATTR_DATA, None), dict):
        return
    for cfg in eligible:
        area_id = cfg[CONF_AREA_ID]
        if area_discovery_unique_id(area_id) in ignored_unique_ids:
            continue
        discovery_flow.async_create_flow(
            hass,
            DOMAIN,
            context={CONF_SOURCE: SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_AREA_ID: area_id},
            discovery_key=discovery_flow.DiscoveryKey(
                domain=DOMAIN, key=area_id, version=_DISCOVERY_KEY_VERSION
            ),
        )


@callback
def async_trigger_area_discoveries(hass: HomeAssistant) -> None:
    """Create discovery flows for eligible unconfigured areas and abort stale ones."""
    config_entries = getattr(hass, _ATTR_CONFIG_ENTRIES, None)
    if config_entries is None:
        return
    entries = config_entries.async_entries(DOMAIN)
    if not isinstance(entries, list):
        return

    configured_area_ids, ignored_unique_ids, active_entry = _collect_entry_state(
        cast("list[ConfigEntry]", entries)
    )
    eligible = discover_eligible_areas(
        hass,
        excluded_area_ids=configured_area_ids,
        global_options=active_entry.options if active_entry else None,
    )
    eligible_ids = {cfg[CONF_AREA_ID] for cfg in eligible}

    _abort_stale_discovery_flows(
        getattr(config_entries, _ATTR_FLOW, None),
        eligible_ids,
        ignored_unique_ids,
    )
    _create_area_discovery_flows(hass, eligible, ignored_unique_ids)


def _has_discovery_enabled(entry: ConfigEntry) -> bool:
    """Return True when at least one area subentry enables auto-discovery."""
    return any(
        is_auto_discovery_enabled(data) for _, data in iter_area_subentries(entry)
    )


def _is_relevant_registry_event(event: Event[Any]) -> bool:
    """Return True when a registry event can alter area sensor discovery."""
    if event.data.get(_EVENT_KEY_ACTION) != _EVENT_ACTION_UPDATE:
        return True
    return bool(
        _RELEVANT_REGISTRY_CHANGE_KEYS.intersection(
            event.data.get(_EVENT_KEY_CHANGES, {})
        )
    )


class _DiscoveryRefreshDebouncer:
    """Coalesce bursts of Home Assistant registry updates into one refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        refresh: Callable[[], Awaitable[None]],
    ) -> None:
        self._hass = hass
        self._refresh = refresh
        self._cancel_pending: Callable[[], None] | None = None

    async def _run_refresh(self, _now: datetime) -> None:
        self._cancel_pending = None
        await self._refresh()
        async_trigger_area_discoveries(self._hass)

    @callback
    def schedule(self) -> None:
        """Schedule a debounced discovery refresh, replacing any pending timer."""
        if self._cancel_pending is not None:
            self._cancel_pending()
        self._cancel_pending = async_call_later(
            self._hass, _DISCOVERY_DEBOUNCE_SECONDS, self._run_refresh
        )

    @callback
    def cancel(self) -> None:
        """Cancel any scheduled discovery refresh timer."""
        if self._cancel_pending is not None:
            self._cancel_pending()
            self._cancel_pending = None


@callback
def async_track_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    refresh: Callable[[], Awaitable[None]],
) -> None:
    """Refresh automatic inputs after registry changes, coalescing event bursts."""
    debouncer = _DiscoveryRefreshDebouncer(hass, refresh)

    @callback
    def registry_changed(event: Event[Any]) -> None:
        if _has_discovery_enabled(entry) and _is_relevant_registry_event(event):
            debouncer.schedule()

    @callback
    def ha_started(_event: Event[Any]) -> None:
        if _has_discovery_enabled(entry):
            debouncer.schedule()

    @callback
    def area_registry_changed(_event: Event[Any]) -> None:
        debouncer.schedule()

    entry.async_on_unload(debouncer.cancel)
    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, registry_changed)
    )
    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, registry_changed)
    )
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, ha_started)
    )
    entry.async_on_unload(
        hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, area_registry_changed)
    )
