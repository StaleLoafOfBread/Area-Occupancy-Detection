"""Resolve typed sensors in a Home Assistant area without changing saved choices."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, EVENT_HOMEASSISTANT_STARTED, Platform
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
    CONF_AIR_QUALITY_SENSORS,
    CONF_APPLIANCES,
    CONF_AREA_ID,
    CONF_AUTO_ADDED_SENSORS,
    CONF_AUTO_DISCOVER_DOMAINS,
    CONF_AUTO_DISCOVER_SENSORS,
    CONF_BUTTON_SENSORS,
    CONF_CO2_SENSORS,
    CONF_CO_SENSORS,
    CONF_COVER_SENSORS,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_DECAY_HALF_LIFE,
    CONF_DOOR_SENSORS,
    CONF_EXCLUDE_LIGHT_POWER,
    CONF_EXCLUDE_OCCUPANCY_SUBZONES,
    CONF_EXCLUDE_REMOTE_LOCKS,
    CONF_EXCLUDE_VEHICLE_DETECTED,
    CONF_EXCLUDED_DEVICE_MATCHES,
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
    CONF_WIFI_CLIENTS_SENSORS,
    CONF_WINDOW_SENSORS,
    DEFAULT_AREA_EXCLUSION_SETTING,
    DEFAULT_AREA_EXPAND_GROUPS,
    DEFAULT_AUTO_DISCOVER_SENSORS,
    DEFAULT_DECAY_HALF_LIFE,
    DEFAULT_GLOBAL_EXCLUDE_LIGHT_POWER,
    DEFAULT_GLOBAL_EXPAND_GROUPS,
    DISCOVERY_EXCLUSION_RULES,
    DISCOVERY_EXCLUSION_RULES_BY_KEY,
    DISCOVERY_UNIQUE_ID_PREFIX,
    DOMAIN,
    SENSOR_KEY_TO_TYPE_SLUG,
)
from .data.purpose import infer_purpose_from_name
from .discovery_filters import (
    ENTITY_ID_SEPARATOR,
    MOTION_BINARY_DEVICE_CLASSES,
    collect_device_exclusion_filters,
    entity_domain,
    find_excluded_device_entity_ids,
    garage_cover_device_ids,
    is_ineligible_entry,
    is_light_power_sensor,
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
_GROUP_DOMAIN: Final = "group"

DISCOVERABLE_SENSOR_KEYS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        (
            *_BINARY_CLASSES.values(),
            *_NUMERIC_CLASSES.values(),
            *_DOMAINS.values(),
        )
    )
)
ALL_AREA_SENSOR_KEYS: Final[tuple[str, ...]] = (
    *DISCOVERABLE_SENSOR_KEYS,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_APPLIANCES,
    CONF_BUTTON_SENSORS,
    CONF_WIFI_CLIENTS_SENSORS,
)
_KEY_EXPECTED_DOMAINS: Final[dict[str, str]] = {
    **dict.fromkeys(_BINARY_CLASSES.values(), Platform.BINARY_SENSOR),
    **dict.fromkeys(_NUMERIC_CLASSES.values(), Platform.SENSOR),
    **{key: domain for domain, key in _DOMAINS.items()},
}

_DISCOVERY_DEBOUNCE_SECONDS: Final = 1
_DISCOVERY_KEY_VERSION: Final = 1
_RELEVANT_REGISTRY_CHANGE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "area_id",
        "device_id",
        "device_class",
        "original_device_class",
        "disabled_by",
        "entity_category",
        ATTR_ENTITY_ID,
    }
)
_EVENT_KEY_ACTION: Final = "action"
_EVENT_ACTION_UPDATE: Final = "update"
_EVENT_KEY_CHANGES: Final = "changes"
_FLOW_KEY_CONTEXT: Final = "context"
_FLOW_KEY_SOURCE: Final = "source"
_FLOW_KEY_UNIQUE_ID: Final = "unique_id"
_FLOW_KEY_ID: Final = "flow_id"


@dataclass(frozen=True, slots=True)
class _AreaDiscoveryFilters:
    """Resolved discovery toggles, domains, and exclusions for one area scan."""

    expand_groups: bool
    allowed_domains: set[str] | None
    excluded_platforms: set[str]
    excluded_entity_ids: set[str]
    excluded_type_keys: set[str]
    exclude_light_power: bool
    exclude_occupancy_subzones: bool
    exclude_remote_locks: bool
    exclude_vehicle_detected: bool


@dataclass(frozen=True, slots=True)
class _AreaScanContext:
    """Precomputed filters and device context for scanning one area."""

    filters: _AreaDiscoveryFilters
    garage_device_ids: set[str]
    main_classes_by_device: Mapping[str, set[str]]


def _excluded_sensor_keys(excluded_types: Collection[Any]) -> set[str]:
    """Return area config keys covered by global sensor type exclusions."""
    normalized = {item for item in excluded_types if isinstance(item, str)}
    return {
        key
        for key, sensor_type in SENSOR_KEY_TO_TYPE_SLUG.items()
        if sensor_type in normalized
    }


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


def _lookup_registry_entry(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
) -> er.RegistryEntry | None:
    """Safely look up an entity registry entry without failing on bare mocks."""
    if registry is None:
        try:
            registry = er.async_get(hass)
        except (AttributeError, KeyError, RuntimeError, TypeError):
            return None
    return lookup_registry_entry(entity_id, registry)


def _is_own_entity(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
) -> bool:
    """Return True if ``entity_id`` belongs to this integration."""
    entry = _lookup_registry_entry(hass, entity_id, registry)
    return entry is not None and entry.platform == DOMAIN


def _group_contains_own_entity(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
    _visited: set[str] | None = None,
) -> bool:
    """Return True if a group directly or recursively contains an own entity."""
    visited: set[str] = _visited if _visited is not None else set()
    if entity_id in visited:
        return False
    visited.add(entity_id)

    members = _get_group_members(hass, entity_id)
    if members is None:
        return _is_own_entity(hass, entity_id, registry)

    return any(
        _group_contains_own_entity(hass, member_id, registry, visited)
        for member_id in members
    )


def _expand_group_entity(
    hass: HomeAssistant,
    entity_id: str,
    required_domain: str | None = None,
    _visited: set[str] | None = None,
    *,
    registry: er.EntityRegistry | None = None,
) -> list[str]:
    """Expand a group entity recursively into domain-filtered member entity IDs."""
    visited: set[str] = _visited if _visited is not None else set()
    if entity_id in visited:
        return []
    visited.add(entity_id)

    members = _get_group_members(hass, entity_id)
    if members is None:
        if _is_own_entity(hass, entity_id, registry):
            return []
        if required_domain is not None and entity_domain(entity_id) != required_domain:
            return []
        return [entity_id]

    effective_domain = required_domain
    group_domain = entity_domain(entity_id)
    if effective_domain is None and group_domain != _GROUP_DOMAIN:
        effective_domain = group_domain

    expanded: list[str] = []
    for member_id in members:
        expanded.extend(
            _expand_group_entity(
                hass,
                member_id,
                required_domain=effective_domain,
                _visited=visited,
                registry=registry,
            )
        )
    return list(dict.fromkeys(expanded))


def excluded_device_entity_ids(
    hass: HomeAssistant,
    matches: Collection[str] | None = None,
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
        matches,
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
    matches, manufacturers, models = collect_device_exclusion_filters(
        area_data, global_options
    )
    if not matches and not manufacturers and not models:
        return set()
    return excluded_device_entity_ids(
        hass,
        matches,
        manufacturers=manufacturers,
        models=models,
    )


def _classify_entity(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    entity_id: str,
    *,
    entry: er.RegistryEntry | None = None,
    fallback_domain: str | None = None,
    fallback_device_class: str | None = None,
    excluded_platforms: set[str] | None = None,
    exclude_light_power: bool = DEFAULT_GLOBAL_EXCLUDE_LIGHT_POWER,
) -> str | None:
    """Classify an entity ID into a sensor config key, or ``None`` if ineligible."""
    excluded = excluded_platforms or set()
    if entry is None:
        entry = _lookup_registry_entry(hass, entity_id, registry)
    if entry is not None:
        if is_ineligible_entry(hass, entry, excluded):
            return None
        domain = entry.domain
    else:
        if is_weather_entity(entity_id, None):
            return None
        if hass.states.get(entity_id) is None:
            return None
        domain = entity_domain(entity_id)

    device_class = resolve_entry_device_class(
        hass,
        entry,
        entity_id,
        fallback_domain=fallback_domain,
        fallback_device_class=fallback_device_class,
    )
    if domain == Platform.BINARY_SENSOR:
        return _BINARY_CLASSES.get(device_class or "")
    if domain == Platform.SENSOR:
        key = _NUMERIC_CLASSES.get(device_class or "")
        if (
            key == CONF_POWER_SENSORS
            and exclude_light_power
            and is_light_power_sensor(hass, entity_id, entry=entry, registry=registry)
        ):
            return None
        return key
    return _DOMAINS.get(domain)


def get_enabled_discovery_domains(data: dict[str, Any]) -> set[str]:
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
    if entity_id in filters.excluded_entity_ids:
        return
    target = discovered.setdefault(key, [])
    if entity_id not in target:
        target.append(entity_id)


def _resolve_expand_groups(
    area_setting: bool | str,
    global_options: Mapping[str, Any],
) -> bool:
    """Resolve the tri-state group-expansion setting against global defaults."""
    return resolve_group_expansion_enabled(
        area_setting,
        global_options.get(CONF_EXPAND_GROUPS, DEFAULT_GLOBAL_EXPAND_GROUPS),
    )


def _resolve_exclusion_rule(
    config_key: str,
    area_setting: bool | str,
    global_options: Mapping[str, Any],
) -> bool:
    """Resolve one tri-state exclusion rule using its authoritative rule metadata."""
    rule = DISCOVERY_EXCLUSION_RULES_BY_KEY[config_key]
    return resolve_exclusion_enabled(
        area_setting,
        global_options.get(rule.config_key, rule.global_default),
        setting_name=rule.setting_label,
    )


def _build_area_discovery_filters(
    hass: HomeAssistant,
    *,
    expand_groups: bool | str,
    enabled_domains: Collection[str] | None,
    excluded_platforms: Collection[str] | None,
    exclude_light_power: bool | str,
    exclude_occupancy_subzones: bool | str,
    exclude_remote_locks: bool | str,
    exclude_vehicle_detected: bool | str,
    excluded_device_matches: Collection[str] | None,
    excluded_manufacturers: Collection[str] | None,
    excluded_models: Collection[str] | None,
    excluded_entities: Collection[str] | None,
    global_options: Mapping[str, Any],
    precomputed_device_exclusions: bool,
) -> _AreaDiscoveryFilters:
    """Resolve area and global options into a single discovery filter bundle."""
    excluded_entity_ids = collect_excluded_sensor_ids(excluded_entities, global_options)
    if not precomputed_device_exclusions:
        area_filters = {
            CONF_EXCLUDED_DEVICE_MATCHES: excluded_device_matches,
            CONF_EXCLUDED_MANUFACTURERS: excluded_manufacturers,
            CONF_EXCLUDED_MODELS: excluded_models,
        }
        excluded_entity_ids.update(
            resolve_excluded_device_entity_ids(hass, area_filters, global_options)
        )

    excluded_set = normalize_excluded_platforms(excluded_platforms)
    excluded_set.update(
        normalize_excluded_platforms(global_options.get(CONF_EXCLUDED_INTEGRATIONS))
    )
    return _AreaDiscoveryFilters(
        expand_groups=_resolve_expand_groups(expand_groups, global_options),
        allowed_domains=set(enabled_domains) if enabled_domains is not None else None,
        excluded_platforms=excluded_set,
        excluded_entity_ids=excluded_entity_ids,
        excluded_type_keys=_excluded_sensor_keys(
            global_options.get(CONF_EXCLUDED_SENSOR_TYPES) or ()
        ),
        exclude_light_power=_resolve_exclusion_rule(
            CONF_EXCLUDE_LIGHT_POWER, exclude_light_power, global_options
        ),
        exclude_occupancy_subzones=_resolve_exclusion_rule(
            CONF_EXCLUDE_OCCUPANCY_SUBZONES,
            exclude_occupancy_subzones,
            global_options,
        ),
        exclude_remote_locks=_resolve_exclusion_rule(
            CONF_EXCLUDE_REMOTE_LOCKS, exclude_remote_locks, global_options
        ),
        exclude_vehicle_detected=_resolve_exclusion_rule(
            CONF_EXCLUDE_VEHICLE_DETECTED, exclude_vehicle_detected, global_options
        ),
    )


def _collect_area_entries(
    registry: er.EntityRegistry,
    devices: dr.DeviceRegistry,
    area_id: str,
) -> list[tuple[er.RegistryEntry, Any]]:
    """Return sorted ``(entry, device)`` pairs belonging to ``area_id``."""
    area_entries: list[tuple[er.RegistryEntry, Any]] = []
    for entry in sorted(registry.entities.values(), key=lambda item: item.entity_id):
        device = devices.async_get(entry.device_id) if entry.device_id else None
        entry_area_id = entry.area_id or (device.area_id if device else None)
        if entry_area_id == area_id:
            area_entries.append((entry, device))
    return area_entries


def _build_area_scan_context(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    area_entries: Collection[tuple[er.RegistryEntry, Any]],
    filters: _AreaDiscoveryFilters,
) -> _AreaScanContext:
    """Build per-area device lookup context used when evaluating exclusions."""
    has_locks = any(entry.domain == Platform.LOCK for entry, _ in area_entries)
    garage_device_ids: set[str] = (
        garage_cover_device_ids(hass, registry)
        if filters.exclude_remote_locks and has_locks
        else set()
    )
    main_classes_by_device = (
        main_motion_classes_by_device_in_area(
            hass,
            area_entries,
            excluded_platforms=filters.excluded_platforms,
            excluded_entity_ids=filters.excluded_entity_ids,
            exclude_vehicle_detected=filters.exclude_vehicle_detected,
        )
        if filters.exclude_occupancy_subzones
        else {}
    )
    return _AreaScanContext(
        filters=filters,
        garage_device_ids=garage_device_ids,
        main_classes_by_device=main_classes_by_device,
    )


def _is_special_excluded(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    scan_ctx: _AreaScanContext,
) -> bool:
    """Return True if ``entry`` matches any active special exclusion rule."""
    filters = scan_ctx.filters
    return is_special_excluded_entry(
        hass,
        entry,
        exclude_remote_locks=filters.exclude_remote_locks,
        exclude_vehicle_detected=filters.exclude_vehicle_detected,
        exclude_occupancy_subzones=filters.exclude_occupancy_subzones,
        garage_device_ids=scan_ctx.garage_device_ids,
        main_classes_by_device=scan_ctx.main_classes_by_device,
    )


def _expand_and_collect_group(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    entry: er.RegistryEntry,
    scan_ctx: _AreaScanContext,
    discovered: dict[str, list[str]],
) -> None:
    """Expand a group registry entry and append eligible member entities."""
    filters = scan_ctx.filters
    required_domain = entry.domain if entry.domain != _GROUP_DOMAIN else None
    group_dc = resolve_entry_device_class(hass, entry)
    for member_id in _expand_group_entity(
        hass,
        entry.entity_id,
        required_domain=required_domain,
        registry=registry,
    ):
        if member_id in filters.excluded_entity_ids:
            continue
        member_entry = _lookup_registry_entry(hass, member_id, registry)
        if member_entry is not None and _is_special_excluded(
            hass, member_entry, scan_ctx
        ):
            continue
        key = _classify_entity(
            hass,
            registry,
            member_id,
            fallback_domain=entry.domain,
            fallback_device_class=group_dc,
            excluded_platforms=filters.excluded_platforms,
            exclude_light_power=filters.exclude_light_power,
        )
        _append_discovered(discovered, filters, key, member_id)


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
    if _is_special_excluded(hass, entry, scan_ctx):
        return

    is_group = _get_group_members(hass, entry.entity_id) is not None
    if filters.expand_groups and is_group:
        _expand_and_collect_group(hass, registry, entry, scan_ctx, discovered)
        return

    if is_group and _group_contains_own_entity(hass, entry.entity_id, registry):
        return

    key = _classify_entity(
        hass,
        registry,
        entry.entity_id,
        entry=entry,
        excluded_platforms=filters.excluded_platforms,
        exclude_light_power=filters.exclude_light_power,
    )
    _append_discovered(discovered, filters, key, entry.entity_id)


def discover_area_sensors(
    hass: HomeAssistant,
    area_id: str | None,
    *,
    expand_groups: bool | str = DEFAULT_AREA_EXPAND_GROUPS,
    enabled_domains: Collection[str] | None = None,
    excluded_platforms: Collection[str] | None = None,
    exclude_light_power: bool | str = DEFAULT_AREA_EXCLUSION_SETTING,
    exclude_occupancy_subzones: bool | str = DEFAULT_AREA_EXCLUSION_SETTING,
    exclude_remote_locks: bool | str = DEFAULT_AREA_EXCLUSION_SETTING,
    exclude_vehicle_detected: bool | str = DEFAULT_AREA_EXCLUSION_SETTING,
    excluded_device_matches: Collection[str] | None = None,
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

    filters = _build_area_discovery_filters(
        hass,
        expand_groups=expand_groups,
        enabled_domains=enabled_domains,
        excluded_platforms=excluded_platforms,
        exclude_light_power=exclude_light_power,
        exclude_occupancy_subzones=exclude_occupancy_subzones,
        exclude_remote_locks=exclude_remote_locks,
        exclude_vehicle_detected=exclude_vehicle_detected,
        excluded_device_matches=excluded_device_matches,
        excluded_manufacturers=excluded_manufacturers,
        excluded_models=excluded_models,
        excluded_entities=excluded_entities,
        global_options=global_options or {},
        precomputed_device_exclusions=precomputed_device_exclusions,
    )

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
    expand_groups: bool | str | None = None,
) -> dict[str, Any]:
    """Build shared keyword arguments for ``discover_area_sensors``."""
    return {
        "expand_groups": (
            area_data.get(CONF_EXPAND_GROUPS, DEFAULT_AREA_EXPAND_GROUPS)
            if expand_groups is None
            else expand_groups
        ),
        "enabled_domains": enabled_domains,
        "excluded_platforms": area_data.get(CONF_EXCLUDED_INTEGRATIONS),
        **{
            rule.config_key: area_data.get(
                rule.config_key, DEFAULT_AREA_EXCLUSION_SETTING
            )
            for rule in DISCOVERY_EXCLUSION_RULES
        },
        "excluded_entities": excluded_entities,
        "global_options": global_options,
        "precomputed_device_exclusions": True,
    }


def _expand_manual_groups(
    hass: HomeAssistant,
    resolved: dict[str, Any],
    excluded: set[str],
) -> None:
    """Expand configured group entities in place across sensor keys."""
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
                expanded.extend(
                    _expand_group_entity(
                        hass, entity_id, required_domain=expected_domain
                    )
                )
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
    for key in ALL_AREA_SENSOR_KEYS:
        existing = resolved.get(key)
        if isinstance(existing, list):
            resolved[key] = [
                entity_id
                for entity_id in cast("list[Any]", existing)
                if entity_id not in excluded
            ]
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
    for key in ALL_AREA_SENSOR_KEYS:
        existing = resolved.get(key)
        auto_ids = set(tracked_auto.get(key, []))
        if isinstance(existing, list) and auto_ids:
            resolved[key] = [
                entity_id
                for entity_id in cast("list[Any]", existing)
                if entity_id not in auto_ids
            ]
    if preserve_empty_key:
        resolved[CONF_AUTO_ADDED_SENSORS] = {}


def _strip_stale_auto_sensors(
    resolved: dict[str, Any],
    tracked_auto: dict[str, list[str]],
    discovered: dict[str, list[str]],
) -> None:
    """Remove previously auto-added sensors that are no longer eligible."""
    for key in ALL_AREA_SENSOR_KEYS:
        existing = resolved.get(key)
        if not isinstance(existing, list):
            continue
        eligible_ids = set(discovered.get(key, []))
        stale_auto_ids = set(tracked_auto.get(key, [])) - eligible_ids
        if stale_auto_ids:
            resolved[key] = [
                entity_id
                for entity_id in cast("list[Any]", existing)
                if entity_id not in stale_auto_ids
            ]


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
        additions = [
            entity_id
            for entity_id in entity_ids
            if entity_id not in excluded and entity_id not in existing_entities
        ]
        if additions:
            resolved[key] = [*(resolved.get(key) or ()), *additions]
        eligible_discovered = set(entity_ids)
        if not eligible_discovered:
            continue
        previously_auto = tracked_auto.get(key, [])
        resolved_auto[key] = list(
            dict.fromkeys(
                entity_id
                for entity_id in (*previously_auto, *additions)
                if entity_id in eligible_discovered
            )
        )
    return {key: entity_ids for key, entity_ids in resolved_auto.items() if entity_ids}


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
    data: dict[str, Any],
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

    excluded_type_keys = _excluded_sensor_keys(
        global_options.get(CONF_EXCLUDED_SENSOR_TYPES) or ()
    )
    for key in excluded_type_keys:
        resolved.pop(key, None)

    tracked_auto = parse_tracked_auto_sensors(
        data, allowed_keys=ALL_AREA_SENSOR_KEYS, excluded_keys=excluded_type_keys
    )
    preserve_empty_key = CONF_AUTO_ADDED_SENSORS in data

    excluded = collect_excluded_sensor_ids(
        data.get(CONF_EXCLUDED_SENSORS), global_options
    )
    excluded.update(resolve_excluded_device_entity_ids(hass, data, global_options))

    if expand_groups:
        _expand_manual_groups(hass, resolved, excluded)
    _strip_excluded_entities(resolved, tracked_auto, excluded)

    enabled_domains = get_enabled_discovery_domains(data)
    if (
        not data.get(CONF_AUTO_DISCOVER_SENSORS, DEFAULT_AUTO_DISCOVER_SENSORS)
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
            expand_groups=expand_groups,
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


def build_suggested_area_config(
    hass: HomeAssistant,
    area_id: str,
    area_name: str | None = None,
    *,
    area_entry: ar.AreaEntry | None = None,
) -> dict[str, Any]:
    """Build a suggested initial configuration dict for a Home Assistant area."""
    if area_entry is None:
        with contextlib.suppress(AttributeError, KeyError, RuntimeError, TypeError):
            area_entry = ar.async_get(hass).async_get_area(area_id)

    if area_name is None:
        raw_entry_name = getattr(area_entry, "name", None) if area_entry else None
        area_name = (
            raw_entry_name
            if isinstance(raw_entry_name, str) and raw_entry_name
            else area_id
        )

    raw_language = getattr(getattr(hass, "config", None), "language", None)
    language = raw_language if isinstance(raw_language, str) else None
    raw_icon = getattr(area_entry, "icon", None) if area_entry else None
    icon = raw_icon if isinstance(raw_icon, str) else None
    raw_aliases = getattr(area_entry, "aliases", None) if area_entry else None
    aliases: list[str] | None = (
        [
            alias
            for alias in cast("Iterable[Any]", raw_aliases)
            if isinstance(alias, str)
        ]
        if isinstance(raw_aliases, (set, list, tuple, frozenset))
        else None
    )

    return {
        CONF_AREA_ID: area_id,
        CONF_PURPOSE: infer_purpose_from_name(
            area_name,
            language=language,
            icon=icon,
            aliases=aliases,
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


def discover_eligible_areas(
    hass: HomeAssistant,
    excluded_area_ids: set[str] | None = None,
    global_options: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return suggested configs for unconfigured HA areas with motion sensors."""
    area_reg = ar.async_get(hass)
    list_areas = getattr(area_reg, "async_list_areas", None)
    areas_attr: Any = getattr(area_reg, "areas", None)
    raw_areas: Iterable[Any] = (
        cast("Iterable[Any]", list_areas())
        if callable(list_areas)
        else (
            cast("Mapping[Any, Any]", areas_attr).values()
            if isinstance(areas_attr, Mapping)
            else ()
        )
    )
    areas: list[Any] = sorted(
        raw_areas,
        key=lambda area: str(
            getattr(area, "name", None) or getattr(area, "id", "")
        ).lower(),
    )

    suggestions: list[dict[str, Any]] = []
    for area in areas:
        area_id = getattr(area, "id", None)
        if (
            not isinstance(area_id, str)
            or not area_id
            or (excluded_area_ids and area_id in excluded_area_ids)
        ):
            continue
        discovered = discover_area_sensors(hass, area_id, global_options=global_options)
        if discovered.get(CONF_MOTION_SENSORS):
            raw_area_name = getattr(area, "name", None)
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
    entries: list[ConfigEntry],
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
    if flow_mgr is None or not hasattr(flow_mgr, "async_progress_by_handler"):
        return
    in_progress = flow_mgr.async_progress_by_handler(DOMAIN)
    if not isinstance(in_progress, list):
        return
    for flow in cast("list[dict[str, Any]]", in_progress):
        context = flow.get(_FLOW_KEY_CONTEXT, {})
        if context.get(_FLOW_KEY_SOURCE) != SOURCE_INTEGRATION_DISCOVERY:
            continue
        uid = str(context.get(_FLOW_KEY_UNIQUE_ID) or "")
        if not uid.startswith(DISCOVERY_UNIQUE_ID_PREFIX):
            continue
        flow_area_id = uid.removeprefix(DISCOVERY_UNIQUE_ID_PREFIX)
        if flow_area_id not in eligible_ids or uid in ignored_unique_ids:
            flow_mgr.async_abort(flow[_FLOW_KEY_ID])


@callback
def async_trigger_area_discoveries(hass: HomeAssistant) -> None:
    """Create discovery flows for eligible unconfigured areas and abort stale ones."""
    config_entries = getattr(hass, "config_entries", None)
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
        getattr(config_entries, "flow", None),
        eligible_ids,
        ignored_unique_ids,
    )

    if isinstance(getattr(hass, "data", None), dict):
        for cfg in eligible:
            area_id = cfg[CONF_AREA_ID]
            uid = area_discovery_unique_id(area_id)
            if uid in ignored_unique_ids:
                continue
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={_FLOW_KEY_SOURCE: SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_AREA_ID: area_id},
                discovery_key=discovery_flow.DiscoveryKey(
                    domain=DOMAIN, key=area_id, version=_DISCOVERY_KEY_VERSION
                ),
            )


def _has_discovery_enabled(entry: ConfigEntry) -> bool:
    """Return True when at least one area subentry enables auto-discovery."""
    return any(
        data.get(CONF_AUTO_DISCOVER_SENSORS, DEFAULT_AUTO_DISCOVER_SENSORS)
        for _, data in iter_area_subentries(entry)
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


@callback
def async_track_discovery(
    hass: HomeAssistant,
    entry: ConfigEntry,
    refresh: Callable[[], Awaitable[None]],
) -> None:
    """Refresh automatic inputs after registry changes, coalescing event bursts."""
    cancel_pending: Callable[[], None] | None = None

    async def refresh_inputs(_now: datetime) -> None:
        nonlocal cancel_pending
        cancel_pending = None
        await refresh()
        async_trigger_area_discoveries(hass)

    @callback
    def schedule_refresh() -> None:
        nonlocal cancel_pending
        if cancel_pending:
            cancel_pending()
        cancel_pending = async_call_later(
            hass, _DISCOVERY_DEBOUNCE_SECONDS, refresh_inputs
        )

    @callback
    def registry_changed(event: Event[Any]) -> None:
        if _has_discovery_enabled(entry) and _is_relevant_registry_event(event):
            schedule_refresh()

    @callback
    def ha_started(_event: Event[Any]) -> None:
        if _has_discovery_enabled(entry):
            schedule_refresh()

    @callback
    def area_registry_changed(_event: Event[Any]) -> None:
        schedule_refresh()

    @callback
    def cancel() -> None:
        if cancel_pending:
            cancel_pending()

    entry.async_on_unload(cancel)
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
