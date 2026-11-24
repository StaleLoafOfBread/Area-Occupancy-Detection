"""Pure entity and device filtering heuristics for automatic sensor discovery."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
import re
from typing import Any, Final, cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.cover import CoverDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_EXCLUDED_DEVICE_MATCHES,
    CONF_EXCLUDED_MANUFACTURERS,
    CONF_EXCLUDED_MODELS,
    DEFAULT_EXCLUDED_DEVICE_MATCHES,
    DEFAULT_EXCLUDED_MANUFACTURERS,
    DEFAULT_EXCLUDED_MODELS,
    DEVICE_ATTR_MANUFACTURER,
    DEVICE_ATTR_MODEL,
    DOMAIN,
    WEATHER_KEYWORDS,
    WEATHER_PLATFORMS,
)

ENTITY_ID_SEPARATOR: Final = "."
PLATFORM_SOURCE_SEPARATOR: Final = ":"

_ATTR_ATTRIBUTES: Final = "attributes"
_ATTR_TRANSLATION_KEY: Final = "translation_key"
_ATTR_UNIQUE_ID: Final = "unique_id"
_ATTR_ORIGINAL_NAME: Final = "original_name"
_ATTR_SOURCE_DOMAIN: Final = "source_domain"
_ATTR_SOURCE_ENTITY: Final = "source_entity"
_ATTR_ENTITIES: Final = "entities"
_ATTR_ASYNC_GET: Final = "async_get"
_POWERCALC_PLATFORM: Final = "powercalc"

# Observed on ratgdo (v32disco_secplusv1 / ESPHome):
#   lock unique_id: "<mac>/0/lock/Lock remotes"
#   binary_sensor unique_id: "<mac>/0/binary_sensor/Vehicle detected"
_REMOTE_LOCK_MARKERS: Final[tuple[str, ...]] = ("lock_remotes",)
_VEHICLE_DETECTED_MARKERS: Final[tuple[str, ...]] = ("vehicle_detected",)

# Observed on multi-zone mmWave and bed-presence sensors (e.g. Everything
# Presence Lite/Pro, Aqara FP2, Apollo MSR-2, ElevatedSensors BedPresenceMk1):
#   main unique_id: "<mac>/0/binary_sensor/Occupancy"
#   subzone unique_id: "<mac>/0/binary_sensor/Zone 1 Occupancy"
#   bed main unique_id: "<mac>/0/binary_sensor/Bed Occupied Either"
#   bed subzone unique_id: "<mac>/0/binary_sensor/Bed Occupied Left"
_SUBZONE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[_/])(?:"
    r"subzone(?:_?\d+)?"
    r"|(?:zone|region)_?\d+"
    r"|bed_occupied_(?:both|left|right)(?:_?\(?(?:fast|normal|slow)\)?)?"
    r"|bed_occupied_either_?\(?(?:fast|normal|slow)\)?"
    r")(?:$|[_/])"
)
# Known multi-zone devices whose main occupancy sensor covers the full area
# while subzone/subset entities report parts of that same sensor.
# Matched as (manufacturer_fragment, model_fragment) after stripping spaces,
# hyphens, and underscores.
_KNOWN_MULTI_ZONE_OCCUPANCY_DEVICES: Final[tuple[tuple[str, str], ...]] = (
    ("everythingsmarttechnology", "everythingpresencelite"),
    ("everythingsmarttechnology", "everythingpresencepro"),
    ("aqara", "fp2"),
    ("lumi", "fp2"),
    ("lumi", "pss02d"),
    ("apollo", "msr2"),
    ("apollo", "mtr1"),
    ("elevatedsensors", "bedpresence"),
)
_COMPACT_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[\s_-]+")
_OCCUPANCY_DEVICE_CLASSES: Final[frozenset[str]] = frozenset(
    {BinarySensorDeviceClass.OCCUPANCY, BinarySensorDeviceClass.PRESENCE}
)
_MOTION_ONLY_DEVICE_CLASS: Final[str] = BinarySensorDeviceClass.MOTION
MOTION_BINARY_DEVICE_CLASSES: Final[frozenset[str]] = _OCCUPANCY_DEVICE_CLASSES | {
    _MOTION_ONLY_DEVICE_CLASS
}
_MOTION_BINARY_DEVICE_CLASSES = MOTION_BINARY_DEVICE_CLASSES


def is_weather_entity(entity_id: str, platform: str | None) -> bool:
    """Return True if an entity originates from an outdoor weather integration."""
    if platform and platform.lower() in WEATHER_PLATFORMS:
        return True
    entity_lower = entity_id.lower()
    return any(keyword in entity_lower for keyword in WEATHER_KEYWORDS)


def normalize_text_fragments(values: Collection[Any] | None) -> set[str]:
    """Normalize non-empty string fragments to casefolded tokens."""
    if not values:
        return set()
    return {
        cleaned.casefold()
        for value in values
        if isinstance(value, str) and (cleaned := value.strip())
    }


def normalize_excluded_platforms(
    excluded_platforms: Collection[Any] | None,
) -> set[str]:
    """Normalize excluded integration platform slugs to a lowercase set."""
    if not excluded_platforms:
        return set()
    return {p.lower() for p in excluded_platforms if isinstance(p, str) and p}


def entity_domain(entity_id: str) -> str:
    """Return the domain prefix of an entity ID, or ``""`` if missing."""
    return (
        entity_id.split(ENTITY_ID_SEPARATOR, 1)[0]
        if ENTITY_ID_SEPARATOR in entity_id
        else ""
    )


def entity_object_id(entity_id: str) -> str:
    """Return the object ID suffix of an entity ID."""
    return entity_id.split(ENTITY_ID_SEPARATOR, 1)[-1]


def format_platform_source(platform: str, source_domain: str) -> str:
    """Build a ``platform:source_domain`` exclusion identifier."""
    return f"{platform}{PLATFORM_SOURCE_SEPARATOR}{source_domain}"


def split_platform_source(platform_spec: str) -> tuple[str, str]:
    """Split a ``platform`` or ``platform:source_domain`` token."""
    base, _, source = platform_spec.partition(PLATFORM_SOURCE_SEPARATOR)
    return base, source


def collect_device_exclusion_filters(
    area_data: Mapping[str, Any],
    global_options: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Combine area-level and global device exclusion fragments."""
    global_opts = global_options or {}

    def _combine(key: str, default: tuple[str, ...]) -> list[str]:
        return [
            *(area_data.get(key) or default),
            *(global_opts.get(key) or default),
        ]

    return (
        _combine(CONF_EXCLUDED_DEVICE_MATCHES, DEFAULT_EXCLUDED_DEVICE_MATCHES),
        _combine(CONF_EXCLUDED_MANUFACTURERS, DEFAULT_EXCLUDED_MANUFACTURERS),
        _combine(CONF_EXCLUDED_MODELS, DEFAULT_EXCLUDED_MODELS),
    )


def _normalize_identifier(value: str | None) -> str:
    """Normalize a canonical identifier (translation_key or unique_id) for matching."""
    if not isinstance(value, str) or not value:
        return ""
    return value.lower().replace("-", "_").replace(" ", "_")


def _compact_token(value: Any) -> str:
    """Normalize a device metadata string for compact substring matching."""
    if not isinstance(value, str) or not value:
        return ""
    return _COMPACT_TOKEN_RE.sub("", value.casefold())


def lookup_registry_entry(
    entity_id: str,
    registry: er.EntityRegistry | None,
) -> er.RegistryEntry | None:
    """Safely look up an entity registry entry without failing on bare mocks."""
    if registry is None:
        return None
    entities = getattr(registry, _ATTR_ENTITIES, None)
    if isinstance(entities, dict):
        return cast("dict[str, er.RegistryEntry]", entities).get(entity_id)
    if hasattr(registry, _ATTR_ASYNC_GET):
        return registry.async_get(entity_id)
    return None


def state_attributes(hass: HomeAssistant, entity_id: str) -> Mapping[str, Any] | None:
    """Return the state attributes mapping for ``entity_id``, or ``None``."""
    state = hass.states.get(entity_id)
    attrs = getattr(state, _ATTR_ATTRIBUTES, None) if state else None
    return cast("Mapping[str, Any]", attrs) if isinstance(attrs, Mapping) else None


def resolve_entry_device_class(
    hass: HomeAssistant,
    entry: er.RegistryEntry | None,
    entity_id: str | None = None,
    *,
    fallback_domain: str | None = None,
    fallback_device_class: str | None = None,
) -> str | None:
    """Resolve effective device_class from registry entry, live state, or fallback."""
    target_id = entry.entity_id if entry is not None else entity_id
    attrs = state_attributes(hass, target_id) if target_id else None
    state_dc = attrs.get(ATTR_DEVICE_CLASS) if attrs is not None else None
    entry_dc = entry.device_class if entry is not None else None
    orig_dc = entry.original_device_class if entry is not None else None
    domain = (
        entry.domain
        if entry is not None
        else (entity_domain(target_id) if target_id else None)
    )
    fallback = fallback_device_class if domain == fallback_domain else None
    return entry_dc or state_dc or orig_dc or fallback


def source_domain_from_attrs(attrs: Mapping[str, Any] | None) -> str | None:
    """Return the source entity domain exposed in state attributes, if any."""
    if not isinstance(attrs, Mapping):
        return None
    source_domain = attrs.get(_ATTR_SOURCE_DOMAIN)
    if isinstance(source_domain, str) and source_domain:
        return source_domain.lower()
    source_entity = attrs.get(_ATTR_SOURCE_ENTITY)
    if isinstance(source_entity, str) and (domain := entity_domain(source_entity)):
        return domain.lower()
    return None


def entry_source_domain(hass: HomeAssistant, entity_id: str) -> str | None:
    """Return the source entity domain exposed in state attributes, if any."""
    return source_domain_from_attrs(state_attributes(hass, entity_id))


def _device_matches_exclusions(
    device: Any,
    *,
    matches: set[str],
    manufacturers: set[str],
    models: set[str],
) -> bool:
    """Return True if a device's manufacturer or model matches any exclusion fragment."""
    manufacturer = getattr(device, DEVICE_ATTR_MANUFACTURER, None)
    model = getattr(device, DEVICE_ATTR_MODEL, None)
    mfr_cf = manufacturer.casefold() if isinstance(manufacturer, str) else ""
    model_cf = model.casefold() if isinstance(model, str) else ""
    return (
        (bool(mfr_cf) and any(match in mfr_cf for match in manufacturers))
        or (bool(model_cf) and any(match in model_cf for match in models))
        or any(
            match in value for match in matches for value in (mfr_cf, model_cf) if value
        )
    )


def find_excluded_device_entity_ids(
    registry: er.EntityRegistry,
    devices: dr.DeviceRegistry,
    matches: Collection[str] | None = None,
    *,
    manufacturers: Collection[str] | None = None,
    models: Collection[str] | None = None,
) -> set[str]:
    """Return entity IDs whose device manufacturer or model matches a filter."""
    normalized_matches = normalize_text_fragments(matches)
    normalized_manufacturers = normalize_text_fragments(manufacturers)
    normalized_models = normalize_text_fragments(models)
    if (
        not normalized_matches
        and not normalized_manufacturers
        and not normalized_models
    ):
        return set()

    excluded_ids: set[str] = set()
    checked_devices: dict[str, bool] = {}

    for entry in registry.entities.values():
        if not entry.device_id:
            continue
        is_excluded = checked_devices.get(entry.device_id)
        if is_excluded is None:
            device = devices.async_get(entry.device_id)
            is_excluded = _device_matches_exclusions(
                device,
                matches=normalized_matches,
                manufacturers=normalized_manufacturers,
                models=normalized_models,
            )
            checked_devices[entry.device_id] = is_excluded
        if is_excluded:
            excluded_ids.add(entry.entity_id)

    return excluded_ids


def _all_members_are_light_power_sensors(
    hass: HomeAssistant,
    member_entities: Any,
    *,
    registry: er.EntityRegistry | None,
    lookup_entry: Callable[[str], er.RegistryEntry | None] | None,
    visited: frozenset[str],
) -> bool:
    """Return True when a non-empty group contains only lights or light power sensors."""
    if not (
        isinstance(member_entities, (list, tuple, set, frozenset)) and member_entities
    ):
        return False
    return all(
        isinstance(member, str)
        and (
            entity_domain(member) == Platform.LIGHT
            or is_light_power_sensor(
                hass,
                member,
                registry=registry,
                lookup_entry=lookup_entry,
                _visited=visited,
            )
        )
        for member in cast("Iterable[Any]", member_entities)
    )


def is_light_power_sensor(
    hass: HomeAssistant,
    entity_id: str,
    *,
    entry: er.RegistryEntry | None = None,
    registry: er.EntityRegistry | None = None,
    lookup_entry: Callable[[str], er.RegistryEntry | None] | None = None,
    _visited: frozenset[str] | None = None,
) -> bool:
    """Return True if a power sensor tracks light entities (e.g., Powercalc lights)."""
    visited: frozenset[str] = _visited if _visited is not None else frozenset()
    if entity_id in visited or entity_domain(entity_id) != Platform.SENSOR:
        return False

    if entry is None:
        entry = (
            lookup_entry(entity_id)
            if lookup_entry is not None
            else lookup_registry_entry(entity_id, registry)
        )
    if entry is None or (entry.platform or "").lower() != _POWERCALC_PLATFORM:
        return False

    device_class = resolve_entry_device_class(hass, entry)
    if device_class != SensorDeviceClass.POWER:
        return False

    attrs = state_attributes(hass, entity_id)
    if source_domain_from_attrs(attrs) == Platform.LIGHT:
        return True

    member_entities = attrs.get(_ATTR_ENTITIES) if attrs is not None else None
    return _all_members_are_light_power_sensors(
        hass,
        member_entities,
        registry=registry,
        lookup_entry=lookup_entry,
        visited=visited | {entity_id},
    )


def garage_cover_device_ids(
    hass: HomeAssistant, registry: er.EntityRegistry
) -> set[str]:
    """Return device IDs that expose a garage-door cover entity."""
    device_ids: set[str] = set()
    for entry in registry.entities.values():
        if entry.domain != Platform.COVER or not entry.device_id:
            continue
        if resolve_entry_device_class(hass, entry) == CoverDeviceClass.GARAGE:
            device_ids.add(entry.device_id)
    return device_ids


def _has_canonical_identifier_marker(
    entry: er.RegistryEntry, markers: tuple[str, ...]
) -> bool:
    """Return True if an entry's normalized translation_key or unique_id contains a marker."""
    identifiers = (
        _normalize_identifier(getattr(entry, _ATTR_TRANSLATION_KEY, None)),
        _normalize_identifier(getattr(entry, _ATTR_UNIQUE_ID, None)),
    )
    return any(
        marker in identifier
        for identifier in identifiers
        if identifier
        for marker in markers
    )


def is_remote_lock(entry: er.RegistryEntry, garage_device_ids: Collection[str]) -> bool:
    """Identify remote-lock entities using language-independent metadata.

    Matches lock entities attached to a garage-door device (a device with a
    ``cover`` entity of device class ``garage``) or whose canonical
    ``translation_key`` / ``unique_id`` identifies a remote lock.
    """
    if entry.domain != Platform.LOCK:
        return False
    if entry.device_id and entry.device_id in garage_device_ids:
        return True
    return _has_canonical_identifier_marker(entry, _REMOTE_LOCK_MARKERS)


def is_vehicle_detected(entry: er.RegistryEntry) -> bool:
    """Identify vehicle-detection binary sensors using language-independent metadata."""
    if entry.domain != Platform.BINARY_SENSOR:
        return False
    return _has_canonical_identifier_marker(entry, _VEHICLE_DETECTED_MARKERS)


def is_occupancy_subzone(entry: er.RegistryEntry) -> bool:
    """Identify multi-zone subzone binary sensors from canonical metadata."""
    if entry.domain != Platform.BINARY_SENSOR:
        return False
    object_id = entity_object_id(entry.entity_id)
    identifiers = (
        _normalize_identifier(getattr(entry, _ATTR_TRANSLATION_KEY, None)),
        _normalize_identifier(getattr(entry, _ATTR_UNIQUE_ID, None)),
        _normalize_identifier(getattr(entry, _ATTR_ORIGINAL_NAME, None)),
        _normalize_identifier(object_id),
    )
    return any(
        _SUBZONE_PATTERN.search(identifier) for identifier in identifiers if identifier
    )


def is_known_multi_zone_device(device: Any) -> bool:
    """Return True if a device is a known multi-zone mmWave or bed-presence sensor."""
    if device is None:
        return False
    manufacturer = _compact_token(getattr(device, DEVICE_ATTR_MANUFACTURER, None))
    model = _compact_token(getattr(device, DEVICE_ATTR_MODEL, None))
    if not manufacturer or not model:
        return False
    return any(
        mfr_frag in manufacturer and model_frag in model
        for mfr_frag, model_frag in _KNOWN_MULTI_ZONE_OCCUPANCY_DEVICES
    )


def main_motion_classes_by_device_in_area(
    hass: HomeAssistant,
    area_entries: Collection[tuple[er.RegistryEntry, Any]],
    *,
    excluded_platforms: set[str],
    excluded_entity_ids: set[str],
    exclude_vehicle_detected: bool,
) -> dict[str, set[str]]:
    """Map known multi-zone device_id -> enabled main motion/occupancy classes in an area.

    Only known multi-zone mmWave devices are included so unrelated devices
    (such as alarm panels or hubs exposing independent zones) are never
    filtered. Tracks non-subzone binary sensors per device so subzones are only
    suppressed in the area where the device's own main occupancy/presence (or
    matching motion) sensor is enabled and eligible.
    """
    classes_by_device: dict[str, set[str]] = {}
    for entry, device in area_entries:
        if not entry.device_id or entry.domain != Platform.BINARY_SENSOR:
            continue
        if is_ineligible_entry(hass, entry, excluded_platforms):
            continue
        if entry.entity_id in excluded_entity_ids:
            continue
        if exclude_vehicle_detected and is_vehicle_detected(entry):
            continue
        if is_occupancy_subzone(entry):
            continue
        if not is_known_multi_zone_device(device):
            continue
        device_class = resolve_entry_device_class(hass, entry)
        if device_class not in _MOTION_BINARY_DEVICE_CLASSES:
            continue
        classes_by_device.setdefault(entry.device_id, set()).add(device_class)
    return classes_by_device


def is_excluded_occupancy_subzone(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    main_classes_by_device: Mapping[str, set[str]],
) -> bool:
    """Return True if ``entry`` is a subzone shadowed by an enabled main sensor.

    A PIR ``motion`` sensor does not shadow mmWave ``occupancy``/``presence``
    subzones; only an enabled ``occupancy``/``presence`` main sensor shadows
    ``occupancy``/``presence`` subzones (and a main ``motion`` sensor only
    shadows ``motion`` subzones).
    """
    if not entry.device_id or not is_occupancy_subzone(entry):
        return False
    main_classes = main_classes_by_device.get(entry.device_id)
    if not main_classes:
        return False
    device_class = resolve_entry_device_class(hass, entry)
    if device_class in _OCCUPANCY_DEVICE_CLASSES:
        return bool(main_classes & _OCCUPANCY_DEVICE_CLASSES)
    if device_class == _MOTION_ONLY_DEVICE_CLASS:
        return _MOTION_ONLY_DEVICE_CLASS in main_classes
    return False


def is_ineligible_entry(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    excluded_platforms: set[str],
) -> bool:
    """Return True if a registry entry should never be auto-discovered."""
    platform = (entry.platform or "").lower()
    source_domain = (
        entry_source_domain(hass, entry.entity_id)
        if platform and excluded_platforms
        else None
    )
    platform_excluded = bool(platform) and (
        platform in excluded_platforms
        or (
            source_domain is not None
            and format_platform_source(platform, source_domain) in excluded_platforms
        )
    )
    return (
        entry.platform == DOMAIN
        or platform_excluded
        or is_weather_entity(entry.entity_id, entry.platform)
        or entry.disabled_by is not None
        or entry.entity_category is not None
    )


def is_special_excluded_entry(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    *,
    exclude_remote_locks: bool,
    exclude_vehicle_detected: bool,
    exclude_occupancy_subzones: bool,
    garage_device_ids: Collection[str],
    main_classes_by_device: Mapping[str, set[str]],
) -> bool:
    """Return True if ``entry`` matches any active special exclusion rule."""
    return (
        (exclude_remote_locks and is_remote_lock(entry, garage_device_ids))
        or (exclude_vehicle_detected and is_vehicle_detected(entry))
        or (
            exclude_occupancy_subzones
            and is_excluded_occupancy_subzone(hass, entry, main_classes_by_device)
        )
    )
