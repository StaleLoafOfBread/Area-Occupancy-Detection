"""Automatic input selection preserves manual configuration and area boundaries."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.area_occupancy.discovery import (
    async_track_discovery,
    resolve_area_sensors,
)


def entity(entity_id: str, **kwargs: object) -> SimpleNamespace:
    """Build a registry entry with realistic empty optional fields."""
    return SimpleNamespace(
        **{
            "entity_id": entity_id,
            "domain": entity_id.split(".", maxsplit=1)[0],
            "platform": "test",
            "area_id": "room",
            "device_id": None,
            "device_class": None,
            "original_device_class": None,
            "disabled_by": None,
            "hidden_by": None,
            "entity_category": None,
            **kwargs,
        }
    )


def resolve(data: dict[str, Any], *entries: SimpleNamespace) -> dict[str, Any]:
    """Resolve against a device in room, with no live states required."""
    hass = Mock()
    hass.states.get.return_value = None
    with (
        patch("custom_components.area_occupancy.discovery.er.async_get") as registry,
        patch("custom_components.area_occupancy.discovery.dr.async_get") as devices,
    ):
        registry.return_value.entities = {e.entity_id: e for e in entries}
        devices.return_value.async_get.return_value = SimpleNamespace(area_id="room")
        return resolve_area_sensors(hass, data)


@pytest.mark.parametrize("enabled", [None, False])
def test_existing_area_is_manual(enabled: bool | None) -> None:
    data = {"area_id": "room", "motion_sensors": ["binary_sensor.manual"]}
    if enabled is not None:
        data["auto_discover_sensors"] = enabled
    assert resolve(data, entity("binary_sensor.new", device_class="motion")) == data


@pytest.mark.parametrize(
    ("entity_id", "device_class", "key"),
    [
        ("binary_sensor.motion", "motion", "motion_sensors"),
        ("binary_sensor.presence", "presence", "motion_sensors"),
        ("binary_sensor.occupancy", "occupancy", "motion_sensors"),
        ("binary_sensor.door", "door", "door_sensors"),
        ("binary_sensor.window", "window", "window_sensors"),
        ("sensor.temperature", "temperature", "temperature_sensors"),
        ("sensor.humidity", "humidity", "humidity_sensors"),
        ("sensor.power", "power", "power_sensors"),
        ("sensor.co2", "carbon_dioxide", "co2_sensors"),
        ("sensor.co", "carbon_monoxide", "co_sensors"),
        ("sensor.sound", "sound_pressure", "sound_pressure_sensors"),
        ("sensor.pressure", "pressure", "pressure_sensors"),
        ("sensor.atmospheric", "atmospheric_pressure", "pressure_sensors"),
        ("sensor.illuminance", "illuminance", "illuminance_sensors"),
        ("sensor.aqi", "aqi", "air_quality_sensors"),
        ("sensor.pm25", "pm25", "pm25_sensors"),
        ("sensor.pm10", "pm10", "pm10_sensors"),
        ("sensor.voc_mass", "volatile_organic_compounds", "voc_sensors"),
        ("sensor.voc", "volatile_organic_compounds_parts", "voc_sensors"),
        ("media_player.tv", None, "media_devices"),
        ("cover.blinds", None, "cover_sensors"),
        ("lock.front", None, "lock_sensors"),
    ],
)
def test_classification(entity_id: str, device_class: str | None, key: str) -> None:
    result = resolve(
        {"area_id": "room", "auto_discover_sensors": True},
        entity(entity_id, original_device_class=device_class),
    )
    assert result[key] == [entity_id]


def test_device_area_and_entity_override() -> None:
    result = resolve(
        {"area_id": "room", "auto_discover_sensors": True},
        entity("lock.inherited", area_id=None, device_id="device"),
        entity("lock.override", area_id="elsewhere", device_id="device"),
        entity("lock.unassigned", area_id=None),
    )
    assert result["lock_sensors"] == ["lock.inherited"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"platform": "area_occupancy"},
        {"disabled_by": "user"},
        {"hidden_by": "user"},
        {"entity_category": "diagnostic"},
        {"area_id": "elsewhere"},
    ],
)
def test_ineligible_entities_are_ignored(overrides: dict[str, Any]) -> None:
    data = {"area_id": "room", "auto_discover_sensors": True}
    assert resolve(data, entity("lock.ignored", **overrides)) == data


def test_exclusions_manual_precedence_and_no_mutation() -> None:
    data = {
        "area_id": "room",
        "auto_discover_sensors": True,
        "excluded_sensors": ["lock.excluded", "lock.manual"],
        "lock_sensors": ["lock.manual"],
        "custom_binary_sensors": ["lock.custom"],
    }
    original = deepcopy(data)
    result = resolve(
        data,
        *(entity(f"lock.{name}") for name in ["excluded", "manual", "custom", "new"]),
    )
    assert result["lock_sensors"] == ["lock.manual", "lock.new"]
    assert result["custom_binary_sensors"] == ["lock.custom"]
    assert data == original


def test_ambiguous_types_are_not_guessed() -> None:
    data = {"area_id": "room", "auto_discover_sensors": True}
    assert (
        resolve(
            data,
            entity("switch.appliance"),
            entity("sensor.clients"),
            entity("binary_sensor.contact", device_class="opening"),
        )
        == data
    )


def test_user_device_class_overrides_original() -> None:
    result = resolve(
        {"area_id": "room", "auto_discover_sensors": True},
        entity(
            "binary_sensor.contact", device_class="window", original_device_class="door"
        ),
    )
    assert result["window_sensors"] == ["binary_sensor.contact"]
    assert "door_sensors" not in result


def test_missing_area_cannot_discover_unassigned_entities() -> None:
    data = {"auto_discover_sensors": True}
    assert resolve(data, entity("lock.unassigned", area_id=None)) == data


def test_disabling_discovery_restores_manual_selections() -> None:
    data = {
        "area_id": "room",
        "auto_discover_sensors": True,
        "lock_sensors": ["lock.manual"],
    }
    assert resolve(data, entity("lock.new"))["lock_sensors"] == [
        "lock.manual",
        "lock.new",
    ]
    data["auto_discover_sensors"] = False
    assert resolve(data, entity("lock.new"))["lock_sensors"] == ["lock.manual"]


def test_live_device_class_fallback() -> None:
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={"device_class": "motion"}
    )
    with (
        patch("custom_components.area_occupancy.discovery.er.async_get") as registry,
        patch("custom_components.area_occupancy.discovery.dr.async_get"),
    ):
        registry.return_value.entities = {
            "binary_sensor.live": entity("binary_sensor.live")
        }
        result = resolve_area_sensors(
            hass, {"area_id": "room", "auto_discover_sensors": True}
        )
    assert result["motion_sensors"] == ["binary_sensor.live"]


def test_registry_changes_refresh_and_cleanup() -> None:
    hass, entry = Mock(), Mock()
    refresh = AsyncMock()
    with (
        patch(
            "custom_components.area_occupancy.discovery.iter_area_subentries",
            return_value=[("id", {"auto_discover_sensors": True})],
        ),
        patch("custom_components.area_occupancy.discovery.async_call_later") as later,
    ):
        async_track_discovery(hass, entry, refresh)
        listener = hass.bus.async_listen.call_args_list[0].args[1]
        listener(SimpleNamespace(data={"action": "update", "changes": {"name": "old"}}))
        later.assert_not_called()
        listener(SimpleNamespace(data={"action": "create"}))
        listener(
            SimpleNamespace(data={"action": "update", "changes": {"area_id": "old"}})
        )
        assert later.call_count == 2
        later.return_value.assert_called_once()
        asyncio.run(later.call_args.args[2](None))
        refresh.assert_awaited_once()
        listener(SimpleNamespace(data={"action": "remove"}))
        entry.async_on_unload.call_args_list[0].args[0]()
        assert later.return_value.call_count == 2


def test_registry_changes_do_nothing_for_manual_areas() -> None:
    hass, entry = Mock(), Mock()
    with (
        patch(
            "custom_components.area_occupancy.discovery.iter_area_subentries",
            return_value=[("id", {})],
        ),
        patch("custom_components.area_occupancy.discovery.async_call_later") as later,
    ):
        async_track_discovery(hass, entry, AsyncMock())
        listener = hass.bus.async_listen.call_args_list[0].args[1]
        listener(SimpleNamespace(data={"action": "create"}))
        later.assert_not_called()
