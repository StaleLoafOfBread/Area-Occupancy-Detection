"""Resolve typed sensors in a Home Assistant area without changing saved choices."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Final

from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigEntry,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
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
    CONF_AUTO_DISCOVER_SENSORS,
    CONF_CO2_SENSORS,
    CONF_CO_SENSORS,
    CONF_COVER_SENSORS,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_DECAY_HALF_LIFE,
    CONF_DOOR_SENSORS,
    CONF_EXCLUDED_SENSORS,
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
    DEFAULT_AUTO_DISCOVER_SENSORS,
    DEFAULT_DECAY_HALF_LIFE,
    DISCOVERY_UNIQUE_ID_PREFIX,
    DOMAIN,
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
ALL_AREA_SENSOR_KEYS: Final[tuple[str, ...]] = (
    *DISCOVERABLE_SENSOR_KEYS,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_APPLIANCES,
    CONF_WIFI_CLIENTS_SENSORS,
)


def is_weather_entity(entity_id: str, platform: str | None) -> bool:
    """Return True if an entity originates from an outdoor weather integration."""
    if platform and platform.lower() in WEATHER_PLATFORMS:
        return True
    entity_lower = entity_id.lower()
    return any(keyword in entity_lower for keyword in WEATHER_KEYWORDS)


def discover_area_sensors(
    hass: HomeAssistant, area_id: str | None
) -> dict[str, list[str]]:
    """Return eligible discoverable entities grouped by sensor config key for an area.

    Disabled, hidden, diagnostic/config, integration-owned, and outdoor weather
    entities are excluded.
    """
    if not area_id:
        return {}

    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    discovered: dict[str, list[str]] = {}

    for entry in sorted(registry.entities.values(), key=lambda item: item.entity_id):
        if (
            entry.platform == DOMAIN
            or is_weather_entity(entry.entity_id, entry.platform)
            or entry.disabled_by is not None
            or entry.hidden_by is not None
            or entry.entity_category is not None
        ):
            continue

        device = devices.async_get(entry.device_id) if entry.device_id else None
        entry_area_id = entry.area_id or (device.area_id if device else None)
        if entry_area_id != area_id:
            continue

        state = hass.states.get(entry.entity_id)
        device_class = (
            entry.device_class
            or (state.attributes.get("device_class") if state else None)
            or entry.original_device_class
        )
        key = _DOMAINS.get(entry.domain)
        if entry.domain == "binary_sensor":
            key = _BINARY_CLASSES.get(device_class)
        elif entry.domain == "sensor":
            key = _NUMERIC_CLASSES.get(device_class)
        if key is not None:
            discovered.setdefault(key, []).append(entry.entity_id)

    return discovered


def resolve_area_sensors(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Merge discovered inputs into a copy of the area's manual selections.

    Auto-discovery defaults to enabled unless explicitly set to ``False``.
    Exclusions always strip matching entities from every sensor list (including
    previously saved manual selections). Explicit non-excluded custom
    classifications still avoid duplicate auto-discovery under another key.
    """
    resolved = dict(data)
    excluded = set(data.get(CONF_EXCLUDED_SENSORS) or [])
    if excluded:
        for key in ALL_AREA_SENSOR_KEYS:
            existing = resolved.get(key)
            if isinstance(existing, list):
                resolved[key] = [
                    entity_id for entity_id in existing if entity_id not in excluded
                ]

    if not data.get(
        CONF_AUTO_DISCOVER_SENSORS, DEFAULT_AUTO_DISCOVER_SENSORS
    ) or not data.get(CONF_AREA_ID):
        return resolved

    manual = {
        entity_id for key in ALL_AREA_SENSOR_KEYS for entity_id in resolved.get(key, [])
    }
    discovered = discover_area_sensors(hass, data[CONF_AREA_ID])
    for key, entity_ids in discovered.items():
        additions = [
            entity_id
            for entity_id in entity_ids
            if entity_id not in excluded and entity_id not in manual
        ]
        if additions:
            resolved[key] = [*resolved.get(key, []), *additions]

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
        CONF_DECAY_HALF_LIFE: DEFAULT_DECAY_HALF_LIFE,
    }


def discover_eligible_areas(
    hass: HomeAssistant, excluded_area_ids: set[str] | None = None
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
        discovered = discover_area_sensors(hass, area_id)
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

    eligible = discover_eligible_areas(hass, excluded_area_ids=configured_area_ids)
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
            "hidden_by",
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
