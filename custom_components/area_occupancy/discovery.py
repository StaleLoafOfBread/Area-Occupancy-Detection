"""Resolve typed sensors in a Home Assistant area without changing saved choices."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
    CONF_SOUND_PRESSURE_SENSORS,
    CONF_TEMPERATURE_SENSORS,
    CONF_VOC_SENSORS,
    CONF_WIFI_CLIENTS_SENSORS,
    CONF_WINDOW_SENSORS,
    DOMAIN,
)

# Only unambiguous classes are automatic. Generic opening contacts, switches,
# appliances, sleep sensors and Wi-Fi counts still need a user's interpretation.
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
}
_DOMAINS = {
    "media_player": CONF_MEDIA_DEVICES,
    "lock": CONF_LOCK_SENSORS,
    "cover": CONF_COVER_SENSORS,
}


def resolve_area_sensors(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Merge discovered inputs into a copy of the area's manual selections.

    Missing opt-in means manual mode, preserving pre-existing installations.
    Entity area overrides device area. Explicit custom classifications take
    precedence over discovery, and exclusions affect only automatic additions.
    Disabled, hidden, diagnostic and integration-owned entities are never added.
    """
    resolved = dict(data)
    if not data.get(CONF_AUTO_DISCOVER_SENSORS, False) or not data.get(CONF_AREA_ID):
        return resolved

    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    excluded = set(data.get(CONF_EXCLUDED_SENSORS, []))
    manual = {
        entity_id
        for key in (
            *_BINARY_CLASSES.values(),
            *_NUMERIC_CLASSES.values(),
            *_DOMAINS.values(),
            CONF_CUSTOM_BINARY_SENSORS,
            CONF_CUSTOM_NUMERIC_SENSORS,
            CONF_APPLIANCES,
            CONF_WIFI_CLIENTS_SENSORS,
        )
        for entity_id in data.get(key, [])
    }
    for entry in sorted(registry.entities.values(), key=lambda item: item.entity_id):
        if (
            entry.platform == DOMAIN
            or entry.disabled_by is not None
            or entry.hidden_by is not None
            or entry.entity_category is not None
            or entry.entity_id in excluded
            or entry.entity_id in manual
        ):
            continue
        device = devices.async_get(entry.device_id) if entry.device_id else None
        area_id = entry.area_id or (device.area_id if device else None)
        if area_id != data[CONF_AREA_ID]:
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
            resolved[key] = [*resolved.get(key, []), entry.entity_id]
    return resolved


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

    @callback
    def registry_changed(event: Event) -> None:
        nonlocal cancel_pending
        if not any(
            data.get(CONF_AUTO_DISCOVER_SENSORS, False)
            for _, data in iter_area_subentries(entry)
        ):
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
        if cancel_pending:
            cancel_pending()
        cancel_pending = async_call_later(hass, 1, refresh_inputs)

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
