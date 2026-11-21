"""Resolve typed sensors in a Home Assistant area without changing saved choices."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import datetime
from typing import Any, Final

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigEntry,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    discovery_flow,
    entity_registry as er,
)
from homeassistant.helpers.event import async_call_later

from .config_helpers import iter_area_subentries
from .const import (
    CONF_AIR_QUALITY_SENSORS,
    CONF_APPLIANCES,
    CONF_AREA_ID,
    CONF_AUTO_ADDED_SENSORS,
    CONF_AUTO_DISCOVER_DOMAINS,
    CONF_AUTO_DISCOVER_SENSORS,
    CONF_CO2_SENSORS,
    CONF_CO_SENSORS,
    CONF_COVER_SENSORS,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_DECAY_HALF_LIFE,
    CONF_DOOR_SENSORS,
    CONF_EXCLUDE_LIGHT_POWER,
    CONF_EXCLUDED_DEVICE_MATCHES,
    CONF_EXCLUDED_INTEGRATIONS,
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
    DEFAULT_AREA_EXPAND_GROUPS,
    DEFAULT_AREA_LIGHT_POWER_SETTING,
    DEFAULT_AUTO_DISCOVER_SENSORS,
    DEFAULT_DECAY_HALF_LIFE,
    DEFAULT_EXCLUDE_LIGHT_POWER,
    DEFAULT_EXCLUDED_DEVICE_MATCHES,
    DEFAULT_GLOBAL_EXPAND_GROUPS,
    DISCOVERY_UNIQUE_ID_PREFIX,
    DOMAIN,
    GROUPS_EXPAND,
    GROUPS_FOLLOW_GLOBAL,
    GROUPS_KEEP,
    LIGHT_POWER_EXCLUDE,
    LIGHT_POWER_FOLLOW_GLOBAL,
    LIGHT_POWER_INCLUDE,
    WEATHER_KEYWORDS,
    WEATHER_PLATFORMS,
)
from .data.purpose import infer_purpose_from_name

# Only unambiguous classes are automatic. Generic opening contacts, switches,
# appliances, sleep sensors, and Wi-Fi counts still need a user's interpretation.
_BINARY_CLASSES = {
    "motion": CONF_MOTION_SENSORS,
    "occupancy": CONF_MOTION_SENSORS,
    "presence": CONF_MOTION_SENSORS,
    "door": CONF_DOOR_SENSORS,
    "garage_door": CONF_DOOR_SENSORS,
    "window": CONF_WINDOW_SENSORS,
}
_NUMERIC_CLASSES = {
    "temperature": CONF_TEMPERATURE_SENSORS,
    "humidity": CONF_HUMIDITY_SENSORS,
    "moisture": CONF_HUMIDITY_SENSORS,
    "illuminance": CONF_ILLUMINANCE_SENSORS,
    "carbon_dioxide": CONF_CO2_SENSORS,
    "carbon_monoxide": CONF_CO_SENSORS,
    "sound_pressure": CONF_SOUND_PRESSURE_SENSORS,
    "pressure": CONF_PRESSURE_SENSORS,
    "atmospheric_pressure": CONF_PRESSURE_SENSORS,
    "aqi": CONF_AIR_QUALITY_SENSORS,
    "volatile_organic_compounds": CONF_VOC_SENSORS,
    "volatile_organic_compounds_parts": CONF_VOC_SENSORS,
    "pm25": CONF_PM25_SENSORS,
    "pm10": CONF_PM10_SENSORS,
    "power": CONF_POWER_SENSORS,
    "current": CONF_POWER_SENSORS,
}
_DOMAINS = {
    "media_player": CONF_MEDIA_DEVICES,
    "lock": CONF_LOCK_SENSORS,
    "cover": CONF_COVER_SENSORS,
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
_POWERCALC_PLATFORM: Final = "powercalc"
ALL_AREA_SENSOR_KEYS: Final[tuple[str, ...]] = (
    *DISCOVERABLE_SENSOR_KEYS,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_APPLIANCES,
    CONF_WIFI_CLIENTS_SENSORS,
)
_SENSOR_KEY_TYPES: Final[dict[str, str]] = {
    CONF_MOTION_SENSORS: "motion",
    CONF_DOOR_SENSORS: "door",
    CONF_WINDOW_SENSORS: "window",
    CONF_LOCK_SENSORS: "lock",
    CONF_COVER_SENSORS: "cover",
    CONF_MEDIA_DEVICES: "media",
    CONF_APPLIANCES: "appliance",
    CONF_TEMPERATURE_SENSORS: "temperature",
    CONF_HUMIDITY_SENSORS: "humidity",
    CONF_ILLUMINANCE_SENSORS: "illuminance",
    CONF_CO2_SENSORS: "co2",
    CONF_CO_SENSORS: "co",
    CONF_SOUND_PRESSURE_SENSORS: "sound_pressure",
    CONF_PRESSURE_SENSORS: "pressure",
    CONF_AIR_QUALITY_SENSORS: "air_quality",
    CONF_VOC_SENSORS: "voc",
    CONF_PM25_SENSORS: "pm25",
    CONF_PM10_SENSORS: "pm10",
    CONF_POWER_SENSORS: "power",
    CONF_WIFI_CLIENTS_SENSORS: "wifi_clients",
    CONF_CUSTOM_BINARY_SENSORS: "custom_binary",
    CONF_CUSTOM_NUMERIC_SENSORS: "custom_numeric",
}


def _excluded_sensor_keys(excluded_types: Collection[str]) -> set[str]:
    """Return area config keys covered by global sensor type exclusions."""
    normalized = {item for item in excluded_types if isinstance(item, str)}
    return {
        key
        for key, sensor_type in _SENSOR_KEY_TYPES.items()
        if sensor_type in normalized
    }


_KEY_EXPECTED_DOMAINS: Final[dict[str, str]] = {
    CONF_MOTION_SENSORS: "binary_sensor",
    CONF_DOOR_SENSORS: "binary_sensor",
    CONF_WINDOW_SENSORS: "binary_sensor",
    CONF_TEMPERATURE_SENSORS: "sensor",
    CONF_HUMIDITY_SENSORS: "sensor",
    CONF_ILLUMINANCE_SENSORS: "sensor",
    CONF_CO2_SENSORS: "sensor",
    CONF_CO_SENSORS: "sensor",
    CONF_SOUND_PRESSURE_SENSORS: "sensor",
    CONF_PRESSURE_SENSORS: "sensor",
    CONF_AIR_QUALITY_SENSORS: "sensor",
    CONF_VOC_SENSORS: "sensor",
    CONF_PM25_SENSORS: "sensor",
    CONF_PM10_SENSORS: "sensor",
    CONF_POWER_SENSORS: "sensor",
    CONF_MEDIA_DEVICES: "media_player",
    CONF_LOCK_SENSORS: "lock",
    CONF_COVER_SENSORS: "cover",
}


def is_weather_entity(entity_id: str, platform: str | None) -> bool:
    """Return True if an entity originates from an outdoor weather integration."""
    if platform and platform.lower() in WEATHER_PLATFORMS:
        return True
    entity_lower = entity_id.lower()
    return any(keyword in entity_lower for keyword in WEATHER_KEYWORDS)


def _get_group_members(hass: HomeAssistant, entity_id: str) -> list[str] | None:
    """Return member entity IDs if ``entity_id`` is a group, otherwise ``None``."""
    state = hass.states.get(entity_id)
    attrs = getattr(state, "attributes", None) if state else None
    members = attrs.get("entity_id") if attrs else None
    if not isinstance(members, (list, tuple)):
        return None
    return [member for member in members if isinstance(member, str) and "." in member]


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
    entities = getattr(registry, "entities", None)
    if isinstance(entities, dict):
        return entities.get(entity_id)
    if hasattr(registry, "async_get"):
        return registry.async_get(entity_id)
    return None


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
    visited = _visited if _visited is not None else set()
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
    visited = _visited if _visited is not None else set()
    if entity_id in visited:
        return []
    visited.add(entity_id)

    members = _get_group_members(hass, entity_id)
    if members is None:
        if _is_own_entity(hass, entity_id, registry):
            return []
        if (
            required_domain is not None
            and entity_id.split(".", 1)[0] != required_domain
        ):
            return []
        return [entity_id]

    effective_domain = required_domain
    group_domain = entity_id.split(".", 1)[0]
    if effective_domain is None and group_domain != "group":
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


def _normalize_excluded_platforms(
    excluded_platforms: Collection[str] | None,
) -> set[str]:
    """Normalize excluded integration platform slugs to a lowercase set."""
    if not excluded_platforms:
        return set()
    return {p.lower() for p in excluded_platforms if isinstance(p, str) and p}


def excluded_device_entity_ids(
    hass: HomeAssistant, matches: Collection[str] | None
) -> set[str]:
    """Return entity IDs whose device manufacturer or model matches a filter."""
    normalized_matches = {
        match.strip().casefold()
        for match in (matches or ())
        if isinstance(match, str) and match.strip()
    }
    if not normalized_matches:
        return set()

    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    excluded_ids: set[str] = set()
    checked_devices: dict[str, bool] = {}

    for entry in registry.entities.values():
        if not entry.device_id:
            continue
        is_excluded = checked_devices.get(entry.device_id)
        if is_excluded is None:
            device = devices.async_get(entry.device_id)
            manufacturer = getattr(device, "manufacturer", None)
            model = getattr(device, "model", None)
            metadata = [
                value.casefold()
                for value in (manufacturer, model)
                if isinstance(value, str)
            ]
            is_excluded = any(
                match in value for match in normalized_matches for value in metadata
            )
            checked_devices[entry.device_id] = is_excluded
        if is_excluded:
            excluded_ids.add(entry.entity_id)

    return excluded_ids


def _source_domain_from_attrs(attrs: Mapping[str, Any] | None) -> str | None:
    """Return the source entity domain exposed in state attributes, if any."""
    if not isinstance(attrs, Mapping):
        return None
    source_domain = attrs.get("source_domain")
    if isinstance(source_domain, str) and source_domain:
        return source_domain.lower()
    source_entity = attrs.get("source_entity")
    if isinstance(source_entity, str) and "." in source_entity:
        return source_entity.split(".", 1)[0].lower()
    return None


def _entry_source_domain(hass: HomeAssistant, entity_id: str) -> str | None:
    """Return the source entity domain exposed in state attributes, if any."""
    state = hass.states.get(entity_id)
    attrs = getattr(state, "attributes", None) if state else None
    return _source_domain_from_attrs(attrs)


def _is_light_power_sensor(
    hass: HomeAssistant,
    entity_id: str,
    entry: er.RegistryEntry | None = None,
    registry: er.EntityRegistry | None = None,
    _visited: frozenset[str] = frozenset(),
) -> bool:
    """Return True if a power sensor tracks light entities (e.g., Powercalc lights)."""
    if entity_id in _visited or not entity_id.startswith(f"{Platform.SENSOR}."):
        return False

    if entry is None:
        entry = _lookup_registry_entry(hass, entity_id, registry)
    if entry is None or (entry.platform or "").lower() != _POWERCALC_PLATFORM:
        return False

    state = hass.states.get(entity_id)
    attrs = getattr(state, "attributes", None) if state else None
    device_class = (
        entry.device_class
        or (attrs.get("device_class") if isinstance(attrs, Mapping) else None)
        or entry.original_device_class
    )
    if device_class != SensorDeviceClass.POWER:
        return False

    if _source_domain_from_attrs(attrs) == Platform.LIGHT:
        return True

    member_entities = attrs.get("entities") if isinstance(attrs, Mapping) else None
    if isinstance(member_entities, (list, tuple, set, frozenset)) and member_entities:
        return all(
            isinstance(member, str)
            and (
                member.startswith(f"{Platform.LIGHT}.")
                or _is_light_power_sensor(
                    hass,
                    member,
                    registry=registry,
                    _visited=_visited | {entity_id},
                )
            )
            for member in member_entities
        )
    return False


def _is_ineligible_entry(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    excluded_platforms: set[str],
) -> bool:
    """Return True if a registry entry should never be auto-discovered."""
    platform = (entry.platform or "").lower()
    source_domain = (
        _entry_source_domain(hass, entry.entity_id)
        if platform and excluded_platforms
        else None
    )
    platform_excluded = bool(platform) and (
        platform in excluded_platforms
        or (
            source_domain is not None
            and f"{platform}:{source_domain}" in excluded_platforms
        )
    )
    return (
        entry.platform == DOMAIN
        or platform_excluded
        or is_weather_entity(entry.entity_id, entry.platform)
        or entry.disabled_by is not None
        or entry.entity_category is not None
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
    exclude_light_power: bool = DEFAULT_EXCLUDE_LIGHT_POWER,
) -> str | None:
    """Classify an entity ID into a sensor config key, or ``None`` if ineligible."""
    excluded = excluded_platforms or set()
    if entry is None:
        entry = _lookup_registry_entry(hass, entity_id, registry)
    if entry is not None:
        if _is_ineligible_entry(hass, entry, excluded):
            return None
        domain = entry.domain
        entry_dc = entry.device_class
        orig_dc = entry.original_device_class
    else:
        if is_weather_entity(entity_id, None):
            return None
        domain = entity_id.split(".", 1)[0]
        entry_dc = None
        orig_dc = None

    state = hass.states.get(entity_id)
    if entry is None and state is None:
        return None
    attrs = getattr(state, "attributes", None) if state else None
    state_dc = attrs.get("device_class") if attrs else None
    device_class = (
        entry_dc
        or state_dc
        or orig_dc
        or (fallback_device_class if domain == fallback_domain else None)
    )
    if domain == "binary_sensor":
        return _BINARY_CLASSES.get(device_class)
    if domain == "sensor":
        key = _NUMERIC_CLASSES.get(device_class)
        if (
            key == CONF_POWER_SENSORS
            and exclude_light_power
            and _is_light_power_sensor(hass, entity_id, entry=entry, registry=registry)
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


def _light_power_exclusion_enabled(
    area_setting: bool | str, global_setting: Any
) -> bool:
    """Resolve the area's light-power choice against the global default."""
    if area_setting == LIGHT_POWER_EXCLUDE or area_setting is True:
        return True
    if area_setting == LIGHT_POWER_INCLUDE:
        return False
    if area_setting == LIGHT_POWER_FOLLOW_GLOBAL or area_setting is False:
        return bool(global_setting)
    raise ValueError(f"Invalid light-power exclusion setting: {area_setting!r}")


def _group_expansion_enabled(area_setting: bool | str, global_setting: Any) -> bool:
    """Resolve the area's group-expansion choice against the global default."""
    if area_setting is True or area_setting == GROUPS_EXPAND:
        return True
    if area_setting is False or area_setting == GROUPS_KEEP:
        return False
    if area_setting == GROUPS_FOLLOW_GLOBAL:
        if isinstance(global_setting, bool):
            return global_setting
        raise ValueError(f"Invalid global group-expansion setting: {global_setting!r}")
    raise ValueError(f"Invalid group-expansion setting: {area_setting!r}")


def discover_area_sensors(
    hass: HomeAssistant,
    area_id: str | None,
    *,
    expand_groups: bool | str = DEFAULT_AREA_EXPAND_GROUPS,
    enabled_domains: Collection[str] | None = None,
    excluded_platforms: Collection[str] | None = None,
    exclude_light_power: bool | str = DEFAULT_AREA_LIGHT_POWER_SETTING,
    excluded_device_matches: Collection[str] | None = None,
    excluded_entities: Collection[str] | None = None,
    global_options: Mapping[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Return eligible discoverable entities grouped by sensor config key for an area.

    Disabled, diagnostic/config, integration-owned, outdoor weather, and
    excluded-integration entities are skipped. Group expansion follows the
    global setting unless explicitly overridden by the area. When
    ``enabled_domains`` is given, only matching sensor config keys are returned.
    The area's light-power setting follows or overrides the global setting.
    Device and integration exclusions combine across scopes, and device
    exclusions match case-insensitive fragments in manufacturer or model.
    """
    allowed_domains = set(enabled_domains) if enabled_domains is not None else None
    if not area_id or (allowed_domains is not None and not allowed_domains):
        return {}

    global_options = global_options or {}
    expand_groups = _group_expansion_enabled(
        expand_groups,
        global_options.get(CONF_EXPAND_GROUPS, DEFAULT_GLOBAL_EXPAND_GROUPS),
    )
    excluded_set = _normalize_excluded_platforms(excluded_platforms)
    excluded_set.update(
        _normalize_excluded_platforms(global_options.get(CONF_EXCLUDED_INTEGRATIONS))
    )
    excluded_entity_ids = {
        entity_id
        for entity_id in (
            *(excluded_entities or ()),
            *(global_options.get(CONF_EXCLUDED_SENSORS) or ()),
        )
        if isinstance(entity_id, str)
    }
    exclude_light_power = _light_power_exclusion_enabled(
        exclude_light_power, global_options.get(CONF_EXCLUDE_LIGHT_POWER, False)
    )
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    excluded_entity_ids.update(
        excluded_device_entity_ids(
            hass,
            [
                *(excluded_device_matches or ()),
                *(
                    global_options.get(CONF_EXCLUDED_DEVICE_MATCHES)
                    or DEFAULT_EXCLUDED_DEVICE_MATCHES
                ),
            ],
        )
    )
    discovered: dict[str, list[str]] = {}

    for entry in sorted(registry.entities.values(), key=lambda item: item.entity_id):
        if _is_ineligible_entry(hass, entry, excluded_set):
            continue

        device = devices.async_get(entry.device_id) if entry.device_id else None
        entry_area_id = entry.area_id or (device.area_id if device else None)
        if entry_area_id != area_id:
            continue

        is_group = _get_group_members(hass, entry.entity_id) is not None
        if expand_groups and is_group:
            required_domain = entry.domain if entry.domain != "group" else None
            group_state = hass.states.get(entry.entity_id)
            group_attrs = (
                getattr(group_state, "attributes", None) if group_state else None
            )
            group_dc = (
                entry.device_class
                or (group_attrs.get("device_class") if group_attrs else None)
                or entry.original_device_class
            )
            for member_id in _expand_group_entity(
                hass,
                entry.entity_id,
                required_domain=required_domain,
                registry=registry,
            ):
                key = _classify_entity(
                    hass,
                    registry,
                    member_id,
                    fallback_domain=entry.domain,
                    fallback_device_class=group_dc,
                    excluded_platforms=excluded_set,
                    exclude_light_power=exclude_light_power,
                )
                if (
                    key is not None
                    and (allowed_domains is None or key in allowed_domains)
                    and member_id not in excluded_entity_ids
                ):
                    target = discovered.setdefault(key, [])
                    if member_id not in target:
                        target.append(member_id)
            continue

        if is_group and _group_contains_own_entity(hass, entry.entity_id, registry):
            continue

        key = _classify_entity(
            hass,
            registry,
            entry.entity_id,
            entry=entry,
            excluded_platforms=excluded_set,
            exclude_light_power=exclude_light_power,
        )
        if (
            key is not None
            and (allowed_domains is None or key in allowed_domains)
            and entry.entity_id not in excluded_entity_ids
        ):
            target = discovered.setdefault(key, [])
            if entry.entity_id not in target:
                target.append(entry.entity_id)

    excluded_type_keys = _excluded_sensor_keys(
        global_options.get(CONF_EXCLUDED_SENSOR_TYPES) or ()
    )
    return {
        key: entities
        for key, entities in discovered.items()
        if key not in excluded_type_keys
    }


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
    expand_groups = _group_expansion_enabled(
        data.get(CONF_EXPAND_GROUPS, DEFAULT_AREA_EXPAND_GROUPS),
        global_options.get(CONF_EXPAND_GROUPS, DEFAULT_GLOBAL_EXPAND_GROUPS),
    )
    if expand_groups:
        for key in ALL_AREA_SENSOR_KEYS:
            existing = resolved.get(key)
            if isinstance(existing, list):
                expected_domain = _KEY_EXPECTED_DOMAINS.get(key)
                expanded: list[str] = []
                for entity_id in existing:
                    if _get_group_members(hass, entity_id) is not None:
                        expanded.extend(
                            _expand_group_entity(
                                hass, entity_id, required_domain=expected_domain
                            )
                        )
                    else:
                        expanded.append(entity_id)
                resolved[key] = list(dict.fromkeys(expanded))

    excluded_type_keys = _excluded_sensor_keys(
        global_options.get(CONF_EXCLUDED_SENSOR_TYPES) or ()
    )
    for key in excluded_type_keys:
        resolved.pop(key, None)

    tracked_auto: dict[str, list[str]] = {}
    raw_tracked_auto = data.get(CONF_AUTO_ADDED_SENSORS)
    if isinstance(raw_tracked_auto, dict):
        for key, entity_ids in raw_tracked_auto.items():
            if (
                key in ALL_AREA_SENSOR_KEYS
                and key not in excluded_type_keys
                and isinstance(entity_ids, list)
            ):
                tracked_auto[key] = [
                    entity_id for entity_id in entity_ids if isinstance(entity_id, str)
                ]

    excluded = set(data.get(CONF_EXCLUDED_SENSORS) or [])
    excluded.update(global_options.get(CONF_EXCLUDED_SENSORS) or [])
    excluded_device_matches = [
        *(data.get(CONF_EXCLUDED_DEVICE_MATCHES) or DEFAULT_EXCLUDED_DEVICE_MATCHES),
        *(
            global_options.get(CONF_EXCLUDED_DEVICE_MATCHES)
            or DEFAULT_EXCLUDED_DEVICE_MATCHES
        ),
    ]
    excluded.update(excluded_device_entity_ids(hass, excluded_device_matches))
    if excluded:
        for key in ALL_AREA_SENSOR_KEYS:
            existing = resolved.get(key)
            if isinstance(existing, list):
                resolved[key] = [
                    entity_id for entity_id in existing if entity_id not in excluded
                ]
        for key, entity_ids in tracked_auto.items():
            tracked_auto[key] = [
                entity_id for entity_id in entity_ids if entity_id not in excluded
            ]

    if not data.get(
        CONF_AUTO_DISCOVER_SENSORS, DEFAULT_AUTO_DISCOVER_SENSORS
    ) or not data.get(CONF_AREA_ID):
        for key in ALL_AREA_SENSOR_KEYS:
            existing = resolved.get(key)
            auto_ids = set(tracked_auto.get(key, []))
            if isinstance(existing, list) and auto_ids:
                resolved[key] = [
                    entity_id for entity_id in existing if entity_id not in auto_ids
                ]
        resolved[CONF_AUTO_ADDED_SENSORS] = {}
        return resolved

    enabled_domains = get_enabled_discovery_domains(data)
    if not enabled_domains:
        for key in ALL_AREA_SENSOR_KEYS:
            existing = resolved.get(key)
            auto_ids = set(tracked_auto.get(key, []))
            if isinstance(existing, list) and auto_ids:
                resolved[key] = [
                    entity_id for entity_id in existing if entity_id not in auto_ids
                ]
        resolved[CONF_AUTO_ADDED_SENSORS] = {}
        return resolved

    manual = {
        entity_id
        for key in ALL_AREA_SENSOR_KEYS
        for entity_id in (resolved.get(key) or ())
    }
    discovered = discover_area_sensors(
        hass,
        data[CONF_AREA_ID],
        expand_groups=expand_groups,
        enabled_domains=enabled_domains,
        excluded_platforms=data.get(CONF_EXCLUDED_INTEGRATIONS),
        exclude_light_power=data.get(
            CONF_EXCLUDE_LIGHT_POWER, DEFAULT_AREA_LIGHT_POWER_SETTING
        ),
        excluded_device_matches=excluded_device_matches,
        excluded_entities=excluded,
        global_options=global_options,
    )
    for key in ALL_AREA_SENSOR_KEYS:
        existing = resolved.get(key)
        if not isinstance(existing, list):
            continue
        eligible_ids = set(discovered.get(key, []))
        stale_auto_ids = set(tracked_auto.get(key, [])) - eligible_ids
        if stale_auto_ids:
            resolved[key] = [
                entity_id for entity_id in existing if entity_id not in stale_auto_ids
            ]

    resolved_auto: dict[str, list[str]] = {}
    for key, entity_ids in discovered.items():
        additions = [
            entity_id
            for entity_id in entity_ids
            if entity_id not in excluded and entity_id not in manual
        ]
        if additions:
            resolved[key] = [*(resolved.get(key) or ()), *additions]
        previously_auto = tracked_auto.get(key, [])
        resolved_auto[key] = (
            list(
                dict.fromkeys(
                    [
                        entity_id
                        for entity_id in (*previously_auto, *additions)
                        if entity_id in eligible_discovered
                    ]
                )
            )
            if (eligible_discovered := set(entity_ids))
            else []
        )

    resolved[CONF_AUTO_ADDED_SENSORS] = {
        key: entity_ids for key, entity_ids in resolved_auto.items() if entity_ids
    }

    return resolved


def area_discovery_unique_id(area_id: str) -> str:
    """Return the unique ID used by discovery flows for an HA area."""
    return f"{DISCOVERY_UNIQUE_ID_PREFIX}{area_id}"


def build_suggested_area_config(
    hass: HomeAssistant, area_id: str, area_name: str | None = None
) -> dict[str, Any]:
    """Build a suggested initial configuration dict for a Home Assistant area."""
    if area_name is None:
        area_entry = ar.async_get(hass).async_get_area(area_id)
        area_name = area_entry.name if area_entry else area_id

    return {
        CONF_AREA_ID: area_id,
        CONF_PURPOSE: infer_purpose_from_name(area_name),
        CONF_AUTO_DISCOVER_SENSORS: DEFAULT_AUTO_DISCOVER_SENSORS,
        CONF_AUTO_DISCOVER_DOMAINS: list(DISCOVERABLE_SENSOR_KEYS),
        CONF_EXPAND_GROUPS: DEFAULT_AREA_EXPAND_GROUPS,
        CONF_EXCLUDE_LIGHT_POWER: DEFAULT_AREA_LIGHT_POWER_SETTING,
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
    raw_areas = (
        list_areas()
        if callable(list_areas)
        else getattr(area_reg, "areas", {}).values()
    )
    areas = sorted(
        raw_areas,
        key=lambda area: (
            getattr(area, "name", None) or getattr(area, "id", "")
        ).lower(),
    )

    suggestions: list[dict[str, Any]] = []
    for area in areas:
        area_id = getattr(area, "id", None)
        if not area_id or (excluded_area_ids and area_id in excluded_area_ids):
            continue
        discovered = discover_area_sensors(hass, area_id, global_options=global_options)
        if discovered.get(CONF_MOTION_SENSORS):
            suggestions.append(
                build_suggested_area_config(hass, area_id, getattr(area, "name", None))
            )
    return suggestions


@callback
def async_trigger_area_discoveries(hass: HomeAssistant) -> None:
    """Create discovery flows for eligible unconfigured areas and abort stale ones."""
    config_entries = getattr(hass, "config_entries", None)
    if config_entries is None:
        return
    entries = config_entries.async_entries(DOMAIN)
    if not isinstance(entries, list):
        return

    configured_area_ids: set[str] = set()
    ignored_unique_ids: set[str] = set()
    for entry in entries:
        if getattr(entry, "source", None) == SOURCE_IGNORE:
            if entry.unique_id:
                ignored_unique_ids.add(str(entry.unique_id))
            continue
        for _, data in iter_area_subentries(entry):
            if area_id := data.get(CONF_AREA_ID):
                configured_area_ids.add(str(area_id))

    active_entry = next(
        (entry for entry in entries if getattr(entry, "source", None) != SOURCE_IGNORE),
        None,
    )
    eligible = discover_eligible_areas(
        hass,
        excluded_area_ids=configured_area_ids,
        global_options=active_entry.options if active_entry else None,
    )
    eligible_ids = {cfg[CONF_AREA_ID] for cfg in eligible}

    flow_mgr = getattr(config_entries, "flow", None)
    if flow_mgr is not None and hasattr(flow_mgr, "async_progress_by_handler"):
        in_progress = flow_mgr.async_progress_by_handler(DOMAIN)
        if isinstance(in_progress, list):
            for flow in in_progress:
                context = flow.get("context", {})
                if context.get("source") != SOURCE_INTEGRATION_DISCOVERY:
                    continue
                uid = str(context.get("unique_id") or "")
                if uid.startswith(DISCOVERY_UNIQUE_ID_PREFIX):
                    flow_area_id = uid.removeprefix(DISCOVERY_UNIQUE_ID_PREFIX)
                    if flow_area_id not in eligible_ids or uid in ignored_unique_ids:
                        flow_mgr.async_abort(flow["flow_id"])

    if isinstance(getattr(hass, "data", None), dict):
        for cfg in eligible:
            area_id = cfg[CONF_AREA_ID]
            uid = area_discovery_unique_id(area_id)
            if uid in ignored_unique_ids:
                continue
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_AREA_ID: area_id},
                discovery_key=discovery_flow.DiscoveryKey(
                    domain=DOMAIN, key=area_id, version=1
                ),
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
        cancel_pending = async_call_later(hass, 1, refresh_inputs)

    def has_discovery_enabled() -> bool:
        return any(
            data.get(CONF_AUTO_DISCOVER_SENSORS, DEFAULT_AUTO_DISCOVER_SENSORS)
            for _, data in iter_area_subentries(entry)
        )

    @callback
    def registry_changed(event: Event) -> None:
        if not has_discovery_enabled():
            return
        if event.data.get("action") == "update" and not {
            "area_id",
            "device_id",
            "device_class",
            "original_device_class",
            "disabled_by",
            "entity_category",
            "entity_id",
        }.intersection(event.data.get("changes", {})):
            return
        schedule_refresh()

    @callback
    def ha_started(_event: Event) -> None:
        if has_discovery_enabled():
            schedule_refresh()

    @callback
    def area_registry_changed(_event: Event) -> None:
        schedule_refresh()

    @callback
    def cancel() -> None:
        if cancel_pending:
            cancel_pending()

    entry.async_on_unload(cancel)
    for event_type in (
        er.EVENT_ENTITY_REGISTRY_UPDATED,
        dr.EVENT_DEVICE_REGISTRY_UPDATED,
    ):
        entry.async_on_unload(hass.bus.async_listen(event_type, registry_changed))
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, ha_started)
    )
    entry.async_on_unload(
        hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, area_registry_changed)
    )
