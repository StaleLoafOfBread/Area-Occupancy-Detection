"""Automatic input selection preserves manual configuration and area boundaries."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.area_occupancy.const import (
    CONF_AREA_ID,
    CONF_AUTO_ADDED_SENSORS,
    CONF_AUTO_DISCOVER_DOMAINS,
    CONF_AUTO_DISCOVER_SENSORS,
    CONF_DOOR_SENSORS,
    CONF_EXCLUDE_LIGHT_POWER,
    CONF_EXCLUDED_INTEGRATIONS,
    CONF_EXCLUDED_SENSORS,
    CONF_EXPAND_GROUPS,
    CONF_MOTION_SENSORS,
    CONF_POWER_SENSORS,
    CONF_PURPOSE,
    CONF_TEMPERATURE_SENSORS,
    DEFAULT_PURPOSE,
    SUBENTRY_TYPE_AREA,
)
from custom_components.area_occupancy.data.purpose import (
    PURPOSE_DEFINITIONS,
    infer_purpose_from_name,
)
from custom_components.area_occupancy.discovery import (
    DISCOVERABLE_SENSOR_KEYS,
    _is_light_power_sensor,
    area_discovery_unique_id,
    async_track_discovery,
    async_trigger_area_discoveries,
    build_suggested_area_config,
    discover_eligible_areas,
    resolve_area_sensors,
)
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers import area_registry as ar


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


def test_discovery_enabled_by_default() -> None:
    data = {"area_id": "room", "motion_sensors": ["binary_sensor.manual"]}
    result = resolve(data, entity("binary_sensor.new", device_class="motion"))
    assert result["motion_sensors"] == ["binary_sensor.manual", "binary_sensor.new"]


def test_disabling_discovery_stays_manual() -> None:
    data = {
        "area_id": "room",
        "auto_discover_sensors": False,
        "motion_sensors": ["binary_sensor.manual"],
    }
    assert resolve(data, entity("binary_sensor.new", device_class="motion")) == data


def test_resolve_none_sensor_list() -> None:
    """A None sensor list accepts automatic discovery additions."""
    result = resolve(
        {CONF_AREA_ID: "room", CONF_MOTION_SENSORS: None},
        entity("binary_sensor.new", device_class="motion"),
    )
    assert result[CONF_MOTION_SENSORS] == ["binary_sensor.new"]


def test_light_power_member_entities_set() -> None:
    """Powercalc YAML groups can be detected from their entities attribute."""
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={
            "device_class": "power",
            "entities": {"light.ikea_lamp", "light.bedside_lamp"},
        }
    )
    entry = entity(
        "sensor.ikea_lamp_power",
        platform="powercalc",
        device_class="power",
        original_device_class="power",
    )

    assert _is_light_power_sensor(hass, "sensor.ikea_lamp_power", entry=entry)


def test_nested_light_power_groups_are_excluded() -> None:
    """Nested Powercalc groups resolve their light-backed power members."""
    desk_lamp = _reg_entry(
        "sensor.desk_lamp_power", area_id="office", device_class="power"
    )
    ceiling_group = _reg_entry(
        "sensor.ceiling_group_power", area_id="office", device_class="power"
    )
    all_lights = _reg_entry(
        "sensor.all_lights_power", area_id="office", device_class="power"
    )
    for entry in (desk_lamp, ceiling_group, all_lights):
        entry.platform = "powercalc"

    hass, registry, _ = _make_group_hass(
        entities=[desk_lamp, ceiling_group, all_lights],
        states={
            "sensor.desk_lamp_power": {"source_domain": "light"},
            "sensor.ceiling_group_power": {"entities": ["sensor.desk_lamp_power"]},
            "sensor.all_lights_power": {"entities": ["sensor.ceiling_group_power"]},
        },
    )

    assert _is_light_power_sensor(hass, "sensor.all_lights_power", registry=registry)


def test_mixed_powercalc_group_is_not_light_power() -> None:
    """A group containing non-light power is not excluded as light power."""
    desk_lamp = _reg_entry(
        "sensor.desk_lamp_power", area_id="office", device_class="power"
    )
    light_group = _reg_entry(
        "sensor.light_group_power", area_id="office", device_class="power"
    )
    appliance_power = _reg_entry(
        "sensor.appliance_power", area_id="office", device_class="power"
    )
    desk_lamp.platform = light_group.platform = "powercalc"
    appliance_power.platform = "zha"

    hass, registry, _ = _make_group_hass(
        entities=[desk_lamp, light_group, appliance_power],
        states={
            "sensor.desk_lamp_power": {"source_domain": "light"},
            "sensor.light_group_power": {
                "entities": ["sensor.desk_lamp_power", "sensor.appliance_power"]
            },
        },
    )

    assert not _is_light_power_sensor(
        hass, "sensor.light_group_power", registry=registry
    )


def test_cyclic_powercalc_groups_are_not_light_power() -> None:
    """Cyclic Powercalc groups terminate without being classified as light power."""
    first_group = _reg_entry(
        "sensor.first_group_power", area_id="office", device_class="power"
    )
    second_group = _reg_entry(
        "sensor.second_group_power", area_id="office", device_class="power"
    )
    first_group.platform = second_group.platform = "powercalc"

    hass, registry, _ = _make_group_hass(
        entities=[first_group, second_group],
        states={
            "sensor.first_group_power": {"entities": ["sensor.second_group_power"]},
            "sensor.second_group_power": {"entities": ["sensor.first_group_power"]},
        },
    )

    assert not _is_light_power_sensor(
        hass, "sensor.first_group_power", registry=registry
    )


def test_light_power_source_entity_is_detected() -> None:
    """Powercalc source_entity metadata identifies a light without source_domain."""
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={"source_entity": "light.desk_lamp"}
    )
    entry = entity(
        "sensor.desk_lamp_power",
        platform="powercalc",
        device_class="power",
        original_device_class="power",
    )

    assert _is_light_power_sensor(hass, "sensor.desk_lamp_power", entry=entry)


@pytest.mark.parametrize(
    ("entity_id", "attrs"),
    [
        (
            "sensor.mixed_group_power",
            {"entities": ["light.ikea_lamp", "switch.ikea_plug"]},
        ),
        ("sensor.vacuum_power", {"source_domain": "vacuum"}),
    ],
)
def test_non_light_power_attributes_are_not_excluded(
    entity_id: str, attrs: dict[str, Any]
) -> None:
    """Mixed groups and non-light sources are not classified as light power."""
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={"device_class": "power", **attrs}
    )
    entry = entity(
        entity_id,
        platform="powercalc",
        device_class="power",
        original_device_class="power",
    )

    assert not _is_light_power_sensor(hass, entity_id, entry=entry)


def test_non_sensor_entity_is_not_light_power() -> None:
    """A light entity itself is never treated as a power sensor."""
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={"source_domain": "light"}
    )

    assert not _is_light_power_sensor(hass, "light.ikea_lamp")
    hass.states.get.assert_not_called()


@pytest.mark.parametrize(
    "entry",
    [
        None,
        entity(
            "sensor.ikea_lamp_power",
            platform="zha",
            device_class="power",
            original_device_class="power",
        ),
    ],
)
def test_light_source_requires_powercalc_entry(entry: SimpleNamespace | None) -> None:
    """Light source metadata alone does not qualify a non-Powercalc entity."""
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={"device_class": "power", "source_domain": "light"}
    )
    registry = SimpleNamespace(entities={})

    assert not _is_light_power_sensor(
        hass,
        "sensor.ikea_lamp_power",
        entry=entry,
        registry=registry,
    )


@pytest.mark.parametrize("device_class", ["energy", "current", None])
def test_light_source_requires_power_device_class(
    device_class: str | None,
) -> None:
    """Light-backed Powercalc entities must measure power specifically."""
    hass = Mock()
    hass.states.get.return_value = SimpleNamespace(
        attributes={"source_domain": "light"}
    )
    entry = entity(
        "sensor.ikea_lamp_power",
        platform="powercalc",
        device_class=device_class,
        original_device_class=device_class,
    )

    assert not _is_light_power_sensor(hass, "sensor.ikea_lamp_power", entry=entry)


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
        ("sensor.moisture", "moisture", "humidity_sensors"),
        ("sensor.power", "power", "power_sensors"),
        ("sensor.current", "current", "power_sensors"),
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
        {"platform": "weather", "original_device_class": "temperature"},
        {"disabled_by": "user"},
        {"entity_category": "diagnostic"},
        {"area_id": "elsewhere"},
    ],
)
def test_ineligible_entities_are_ignored(overrides: dict[str, Any]) -> None:
    data = {"area_id": "room", "auto_discover_sensors": True}
    entity_id = (
        "sensor.temp_ignored"
        if overrides.get("platform") == "weather"
        else "lock.ignored"
    )
    assert resolve(data, entity(entity_id, **overrides)) == data


def test_hidden_entities_are_discovered() -> None:
    """Enabled entities hidden from the UI are still eligible for discovery."""
    data = {"area_id": "room", "auto_discover_sensors": True}
    result = resolve(
        data,
        entity(
            "sensor.office_co2",
            original_device_class="carbon_dioxide",
            hidden_by="user",
        ),
    )
    assert result["co2_sensors"] == ["sensor.office_co2"]


def test_weather_keyword_entities_are_ignored() -> None:
    data = {"area_id": "room", "auto_discover_sensors": True}
    assert (
        resolve(
            data,
            entity("sensor.weather_temperature", original_device_class="temperature"),
            entity("sensor.forecast_humidity", original_device_class="humidity"),
        )
        == data
    )


def test_exclusions_strip_saved_and_discovered_without_mutation() -> None:
    data = {
        "area_id": "room",
        "auto_discover_sensors": True,
        "excluded_sensors": ["lock.excluded", "lock.saved_excluded"],
        "lock_sensors": ["lock.saved_excluded", "lock.manual"],
        "custom_binary_sensors": ["lock.custom"],
    }
    original = deepcopy(data)
    result = resolve(
        data,
        *(
            entity(f"lock.{name}")
            for name in ["excluded", "saved_excluded", "manual", "custom", "new"]
        ),
    )
    assert result["lock_sensors"] == ["lock.manual", "lock.new"]
    assert result["custom_binary_sensors"] == ["lock.custom"]
    assert data == original


def test_exclusions_apply_even_when_discovery_disabled() -> None:
    data = {
        "area_id": "room",
        "auto_discover_sensors": False,
        "excluded_sensors": ["binary_sensor.blocked"],
        "motion_sensors": ["binary_sensor.blocked", "binary_sensor.kept"],
    }
    result = resolve(data, entity("binary_sensor.new", device_class="motion"))
    assert result["motion_sensors"] == ["binary_sensor.kept"]


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
            return_value=[("id", {})],
        ),
        patch("custom_components.area_occupancy.discovery.async_call_later") as later,
    ):
        async_track_discovery(hass, entry, refresh)
        listener = hass.bus.async_listen.call_args_list[0].args[1]
        assert (
            hass.bus.async_listen.call_args_list[2].args[0]
            == EVENT_HOMEASSISTANT_STARTED
        )
        assert (
            hass.bus.async_listen.call_args_list[3].args[0]
            == ar.EVENT_AREA_REGISTRY_UPDATED
        )
        started_listener = hass.bus.async_listen.call_args_list[2].args[1]
        area_listener = hass.bus.async_listen.call_args_list[3].args[1]
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
        started_listener(SimpleNamespace(data={}))
        assert later.call_count == 3
        area_listener(SimpleNamespace(data={}))
        assert later.call_count == 4
        listener(SimpleNamespace(data={"action": "remove"}))
        entry.async_on_unload.call_args_list[0].args[0]()
        assert later.return_value.call_count == 4


def test_registry_changes_do_nothing_when_discovery_disabled() -> None:
    hass, entry = Mock(), Mock()
    with (
        patch(
            "custom_components.area_occupancy.discovery.iter_area_subentries",
            return_value=[("id", {"auto_discover_sensors": False})],
        ),
        patch("custom_components.area_occupancy.discovery.async_call_later") as later,
    ):
        async_track_discovery(hass, entry, AsyncMock())
        listener = hass.bus.async_listen.call_args_list[0].args[1]
        started_listener = hass.bus.async_listen.call_args_list[2].args[1]
        listener(SimpleNamespace(data={"action": "create"}))
        started_listener(SimpleNamespace(data={}))
        later.assert_not_called()


def test_infer_purpose_from_name() -> None:
    """Room names infer matching valid purposes and fall back to default."""
    assert infer_purpose_from_name(None) == DEFAULT_PURPOSE
    assert infer_purpose_from_name("") == DEFAULT_PURPOSE
    assert infer_purpose_from_name("Unrecognized Room") == DEFAULT_PURPOSE

    kitchen = infer_purpose_from_name("Kitchen")
    bedroom = infer_purpose_from_name("Master Bedroom")
    bathroom = infer_purpose_from_name("Guest Bathroom")
    office = infer_purpose_from_name("Home Office")
    hallway = infer_purpose_from_name("Main Hallway")

    for inferred in (kitchen, bedroom, bathroom, office, hallway):
        assert inferred in PURPOSE_DEFINITIONS
        assert inferred != DEFAULT_PURPOSE

    assert infer_purpose_from_name("Living Room") == DEFAULT_PURPOSE
    assert infer_purpose_from_name("KITCHEN") == kitchen
    assert infer_purpose_from_name("master bedroom") == bedroom
    assert len({kitchen, bedroom, bathroom, office, hallway}) >= 4


def test_build_suggested_area_config() -> None:
    """Suggested area configuration populates area ID, discovery flag, and purpose."""
    hass = Mock()
    area_reg = Mock()
    area_reg.async_get_area.return_value = SimpleNamespace(
        id="bedroom", name="Master Bedroom"
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.ar.async_get",
            return_value=area_reg,
        ),
        patch(
            "custom_components.area_occupancy.discovery.discover_area_sensors",
            return_value={CONF_MOTION_SENSORS: ["binary_sensor.bed_motion"]},
        ),
    ):
        suggested = build_suggested_area_config(hass, "bedroom")

    assert suggested[CONF_AREA_ID] == "bedroom"
    assert suggested[CONF_AUTO_DISCOVER_SENSORS] is True
    assert suggested[CONF_AUTO_DISCOVER_DOMAINS] == list(DISCOVERABLE_SENSOR_KEYS)
    assert suggested[CONF_PURPOSE] == infer_purpose_from_name("Master Bedroom")


def test_discover_eligible_areas_filters_and_sorts() -> None:
    """Only unexcluded areas with discoverable motion sensors are returned."""
    hass = Mock()
    areas = [
        SimpleNamespace(id="kitchen", name="Kitchen"),
        SimpleNamespace(id="attic", name="Attic"),
        SimpleNamespace(id="bedroom", name="Bedroom"),
        SimpleNamespace(id="dining", name="Dining Room"),
    ]
    area_reg = Mock()
    area_reg.async_list_areas.return_value = areas
    area_reg.async_get_area.side_effect = lambda area_id: next(
        (a for a in areas if a.id == area_id), None
    )

    def _discover_sensors(_hass: Any, area_id: str) -> dict[str, list[str]]:
        if area_id == "attic":
            return {}
        return {CONF_MOTION_SENSORS: [f"binary_sensor.{area_id}_motion"]}

    with (
        patch(
            "custom_components.area_occupancy.discovery.ar.async_get",
            return_value=area_reg,
        ),
        patch(
            "custom_components.area_occupancy.discovery.discover_area_sensors",
            side_effect=_discover_sensors,
        ),
    ):
        eligible = discover_eligible_areas(hass, excluded_area_ids={"dining"})

    assert [item[CONF_AREA_ID] for item in eligible] == ["bedroom", "kitchen"]


def test_async_trigger_area_discoveries_creates_and_aborts() -> None:
    """Discovery trigger creates flows for new eligible areas and aborts stale ones."""
    hass = Mock()
    hass.data = {}
    active_entry = SimpleNamespace(
        source="user",
        data={},
        options={},
        subentries={
            "sub_living": SimpleNamespace(
                subentry_type=SUBENTRY_TYPE_AREA,
                data={CONF_AREA_ID: "living_room"},
            )
        },
    )
    ignored_entry = SimpleNamespace(
        source=SOURCE_IGNORE,
        unique_id=area_discovery_unique_id("garage"),
        data={},
        options={},
        subentries={},
    )
    hass.config_entries.async_entries.return_value = [active_entry, ignored_entry]
    hass.config_entries.flow.async_progress_by_handler.return_value = [
        {
            "flow_id": "flow_kitchen",
            "context": {
                "source": SOURCE_INTEGRATION_DISCOVERY,
                "unique_id": area_discovery_unique_id("kitchen"),
            },
        },
        {
            "flow_id": "flow_stale",
            "context": {
                "source": SOURCE_INTEGRATION_DISCOVERY,
                "unique_id": area_discovery_unique_id("attic"),
            },
        },
    ]

    area_reg = Mock()
    area_lookup = {
        "bedroom": SimpleNamespace(id="bedroom", name="Bedroom"),
        "garage": SimpleNamespace(id="garage", name="Garage"),
        "kitchen": SimpleNamespace(id="kitchen", name="Kitchen"),
        "living_room": SimpleNamespace(id="living_room", name="Living Room"),
    }
    area_reg.async_get_area.side_effect = area_lookup.get

    with (
        patch(
            "custom_components.area_occupancy.discovery.ar.async_get",
            return_value=area_reg,
        ),
        patch(
            "custom_components.area_occupancy.discovery.discover_eligible_areas",
            return_value=[
                {
                    CONF_AREA_ID: "bedroom",
                    CONF_PURPOSE: infer_purpose_from_name("Bedroom"),
                },
                {
                    CONF_AREA_ID: "garage",
                    CONF_PURPOSE: infer_purpose_from_name("Garage"),
                },
                {
                    CONF_AREA_ID: "kitchen",
                    CONF_PURPOSE: infer_purpose_from_name("Kitchen"),
                },
            ],
        ) as mock_discover,
        patch(
            "custom_components.area_occupancy.discovery.discovery_flow.async_create_flow"
        ) as mock_create_flow,
    ):
        async_trigger_area_discoveries(hass)

    assert mock_discover.call_args.kwargs["excluded_area_ids"] == {"living_room"}
    assert [
        call.kwargs["data"][CONF_AREA_ID] for call in mock_create_flow.call_args_list
    ] == ["bedroom", "kitchen"]
    assert all(
        call.kwargs["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
        for call in mock_create_flow.call_args_list
    )
    hass.config_entries.flow.async_abort.assert_called_once_with("flow_stale")


def _make_group_hass(
    entities: list[SimpleNamespace],
    states: dict[str, dict[str, Any]],
) -> Any:
    """Create a lightweight fake hass with entity registry and state attributes."""
    ent_map = {item.entity_id: item for item in entities}
    registry = SimpleNamespace(entities=ent_map, async_get=ent_map.get)
    devices = SimpleNamespace(async_get=lambda _device_id: None)
    state_objs = {
        eid: SimpleNamespace(attributes=attrs) for eid, attrs in states.items()
    }
    return (
        SimpleNamespace(states=SimpleNamespace(get=state_objs.get)),
        registry,
        devices,
    )


def _reg_entry(
    entity_id: str,
    *,
    area_id: str | None = None,
    device_class: str | None = None,
) -> SimpleNamespace:
    domain = entity_id.split(".", 1)[0]
    return SimpleNamespace(
        entity_id=entity_id,
        domain=domain,
        platform="test",
        area_id=area_id,
        device_id=None,
        device_class=device_class,
        original_device_class=device_class,
        disabled_by=None,
        hidden_by=None,
        entity_category=None,
    )


def test_expand_groups_replaces_binary_sensor_group_and_filters_domain() -> None:
    """Binary sensor groups expand to binary_sensor members only and drop the group."""
    hass, registry, devices = _make_group_hass(
        entities=[
            _reg_entry(
                "binary_sensor.kitchen_motion_group",
                area_id="kitchen",
                device_class="motion",
            ),
            _reg_entry("binary_sensor.pir_1", device_class="motion"),
            _reg_entry("binary_sensor.pir_2"),
            _reg_entry("media_player.tv"),
        ],
        states={
            "binary_sensor.kitchen_motion_group": {
                "device_class": "motion",
                "entity_id": [
                    "binary_sensor.pir_1",
                    "switch.fan",
                    "media_player.tv",
                    "binary_sensor.pir_2",
                ],
            }
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        resolved = resolve_area_sensors(hass, {CONF_AREA_ID: "kitchen"})

    assert resolved[CONF_MOTION_SENSORS] == [
        "binary_sensor.pir_1",
        "binary_sensor.pir_2",
    ]
    assert "binary_sensor.kitchen_motion_group" not in resolved[CONF_MOTION_SENSORS]
    assert "media_devices" not in resolved


def test_expand_groups_handles_nested_cycles_and_legacy_group() -> None:
    """Legacy group.* entities expand recursively with cycle protection."""
    hass, registry, devices = _make_group_hass(
        entities=[
            _reg_entry("group.room_sensors", area_id="office"),
            _reg_entry("binary_sensor.door_1", device_class="door"),
            _reg_entry("binary_sensor.pir_1", device_class="motion"),
            _reg_entry("sensor.room_temp", device_class="temperature"),
        ],
        states={
            "group.room_sensors": {
                "entity_id": [
                    "group.nested",
                    "binary_sensor.door_1",
                    "sensor.room_temp",
                ]
            },
            "group.nested": {
                "entity_id": ["group.room_sensors", "binary_sensor.pir_1"]
            },
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        resolved = resolve_area_sensors(hass, {CONF_AREA_ID: "office"})

    assert resolved[CONF_MOTION_SENSORS] == ["binary_sensor.pir_1"]
    assert resolved[CONF_DOOR_SENSORS] == ["binary_sensor.door_1"]
    assert resolved[CONF_TEMPERATURE_SENSORS] == ["sensor.room_temp"]


def test_expand_groups_manual_list_filters_domain_and_respects_exclusions() -> None:
    """Manually configured groups expand, filter by key domain, and honor exclusions."""
    hass, _, _ = _make_group_hass(
        entities=[],
        states={
            "binary_sensor.motion_group": {
                "entity_id": [
                    "binary_sensor.pir_a",
                    "binary_sensor.pir_b",
                    "light.lamp",
                ]
            }
        },
    )
    resolved = resolve_area_sensors(
        hass,
        {
            CONF_AREA_ID: "hall",
            CONF_AUTO_DISCOVER_SENSORS: False,
            CONF_MOTION_SENSORS: ["binary_sensor.motion_group"],
            CONF_EXCLUDED_SENSORS: ["binary_sensor.pir_b"],
        },
    )
    assert resolved[CONF_MOTION_SENSORS] == ["binary_sensor.pir_a"]


def test_expand_groups_disabled_uses_group_entity() -> None:
    """Disabling expand_groups keeps the group entity directly without expanding."""
    hass, registry, devices = _make_group_hass(
        entities=[
            _reg_entry(
                "binary_sensor.kitchen_motion_group",
                area_id="kitchen",
                device_class="motion",
            ),
            _reg_entry("binary_sensor.pir_1", device_class="motion"),
        ],
        states={
            "binary_sensor.kitchen_motion_group": {
                "device_class": "motion",
                "entity_id": ["binary_sensor.pir_1"],
            }
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        resolved = resolve_area_sensors(
            hass, {CONF_AREA_ID: "kitchen", CONF_EXPAND_GROUPS: False}
        )

    assert resolved[CONF_MOTION_SENSORS] == ["binary_sensor.kitchen_motion_group"]


def test_expand_groups_skips_missing_entities() -> None:
    """Group members absent from both entity registry and states are ignored."""
    hass, registry, devices = _make_group_hass(
        entities=[
            _reg_entry(
                "binary_sensor.office_group",
                area_id="office",
                device_class="occupancy",
            ),
            _reg_entry("binary_sensor.real_motion", device_class="occupancy"),
        ],
        states={
            "binary_sensor.office_group": {
                "device_class": "occupancy",
                "entity_id": [
                    "binary_sensor.real_motion",
                    "binary_sensor.stale_missing_entity",
                ],
            }
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        resolved = resolve_area_sensors(hass, {CONF_AREA_ID: "office"})

    assert resolved[CONF_MOTION_SENSORS] == ["binary_sensor.real_motion"]


def test_expand_groups_excludes_own_integration_members() -> None:
    """Expanding auto-discovered or manual groups strips area_occupancy entities."""
    own_entry = _reg_entry(
        "binary_sensor.office_occupancy_status", device_class="occupancy"
    )
    own_entry.platform = "area_occupancy"
    group_entry = _reg_entry(
        "binary_sensor.office_group",
        area_id="office",
        device_class="occupancy",
    )
    pir_entry = _reg_entry("binary_sensor.real_pir", device_class="motion")
    hass, registry, devices = _make_group_hass(
        entities=[group_entry, own_entry, pir_entry],
        states={
            "binary_sensor.office_group": {
                "device_class": "occupancy",
                "entity_id": [
                    "binary_sensor.office_occupancy_status",
                    "binary_sensor.real_pir",
                ],
            }
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        auto_resolved = resolve_area_sensors(hass, {CONF_AREA_ID: "office"})
        manual_resolved = resolve_area_sensors(
            hass,
            {
                CONF_AREA_ID: "office",
                CONF_AUTO_DISCOVER_SENSORS: False,
                CONF_MOTION_SENSORS: ["binary_sensor.office_group"],
            },
        )

    assert auto_resolved[CONF_MOTION_SENSORS] == ["binary_sensor.real_pir"]
    assert manual_resolved[CONF_MOTION_SENSORS] == ["binary_sensor.real_pir"]


def test_expand_groups_disabled_skips_group_containing_own_entity() -> None:
    """When expand_groups is False, groups containing own entities are skipped."""
    own_entry = _reg_entry(
        "binary_sensor.office_occupancy_status", device_class="occupancy"
    )
    own_entry.platform = "area_occupancy"
    outer_group = _reg_entry(
        "binary_sensor.outer_group",
        area_id="office",
        device_class="occupancy",
    )
    nested_group = _reg_entry(
        "binary_sensor.nested_group",
        device_class="occupancy",
    )
    clean_group = _reg_entry(
        "binary_sensor.clean_group",
        area_id="office",
        device_class="motion",
    )
    pir_entry = _reg_entry("binary_sensor.real_pir", device_class="motion")
    hass, registry, devices = _make_group_hass(
        entities=[outer_group, nested_group, own_entry, clean_group, pir_entry],
        states={
            "binary_sensor.outer_group": {
                "device_class": "occupancy",
                "entity_id": ["binary_sensor.nested_group"],
            },
            "binary_sensor.nested_group": {
                "device_class": "occupancy",
                "entity_id": [
                    "binary_sensor.office_occupancy_status",
                    "binary_sensor.real_pir",
                ],
            },
            "binary_sensor.clean_group": {
                "device_class": "motion",
                "entity_id": ["binary_sensor.real_pir"],
            },
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        resolved = resolve_area_sensors(
            hass, {CONF_AREA_ID: "office", CONF_EXPAND_GROUPS: False}
        )

    assert resolved[CONF_MOTION_SENSORS] == ["binary_sensor.clean_group"]


def test_auto_discover_domains_allows_unchecking_power() -> None:
    """Only enabled discovery domains are auto-added while manual selections remain."""
    entities = [
        entity("binary_sensor.pir", original_device_class="motion"),
        entity("sensor.temp", original_device_class="temperature"),
        entity("sensor.plug_power", original_device_class="power"),
    ]
    without_power = [k for k in DISCOVERABLE_SENSOR_KEYS if k != CONF_POWER_SENSORS]
    result = resolve(
        {
            CONF_AREA_ID: "room",
            CONF_AUTO_DISCOVER_DOMAINS: without_power,
            CONF_POWER_SENSORS: ["sensor.manual_power"],
        },
        *entities,
    )
    assert result[CONF_MOTION_SENSORS] == ["binary_sensor.pir"]
    assert result[CONF_TEMPERATURE_SENSORS] == ["sensor.temp"]
    assert result[CONF_POWER_SENSORS] == ["sensor.manual_power"]

    empty_result = resolve(
        {
            CONF_AREA_ID: "room",
            CONF_AUTO_DISCOVER_DOMAINS: [],
            CONF_POWER_SENSORS: ["sensor.manual_power"],
        },
        *entities,
    )
    assert CONF_MOTION_SENSORS not in empty_result
    assert CONF_TEMPERATURE_SENSORS not in empty_result
    assert empty_result[CONF_POWER_SENSORS] == ["sensor.manual_power"]


def test_excluded_integrations_skips_auto_add_and_groups() -> None:
    """Entities and groups from excluded integrations are not auto-added."""
    powercalc = _reg_entry(
        "sensor.powercalc_watt", area_id="office", device_class="power"
    )
    powercalc.platform = "powercalc"
    magic_group = _reg_entry(
        "binary_sensor.magic_group", area_id="office", device_class="motion"
    )
    magic_group.platform = "magic_areas"
    ha_group = _reg_entry("group.ha_group", area_id="office")
    ha_group.platform = "group"
    real_pir = _reg_entry(
        "binary_sensor.real_pir", area_id="office", device_class="motion"
    )
    real_pir.platform = "esphome"
    real_temp = _reg_entry("sensor.real_temp", device_class="temperature")
    real_temp.platform = "esphome"

    hass, registry, devices = _make_group_hass(
        entities=[powercalc, magic_group, ha_group, real_pir, real_temp],
        states={
            "binary_sensor.magic_group": {
                "device_class": "motion",
                "entity_id": ["binary_sensor.real_pir"],
            },
            "group.ha_group": {
                "entity_id": ["sensor.powercalc_watt", "sensor.real_temp"],
            },
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        auto_only = resolve_area_sensors(
            hass,
            {
                CONF_AREA_ID: "office",
                CONF_EXCLUDED_INTEGRATIONS: ["powercalc", "Magic_Areas"],
            },
        )
        with_manual = resolve_area_sensors(
            hass,
            {
                CONF_AREA_ID: "office",
                CONF_EXCLUDED_INTEGRATIONS: ["powercalc"],
                CONF_POWER_SENSORS: ["sensor.powercalc_watt"],
            },
        )

    assert auto_only[CONF_MOTION_SENSORS] == ["binary_sensor.real_pir"]
    assert auto_only[CONF_TEMPERATURE_SENSORS] == ["sensor.real_temp"]
    assert CONF_POWER_SENSORS not in auto_only
    assert with_manual[CONF_POWER_SENSORS] == ["sensor.powercalc_watt"]


def test_auto_added_provenance_removed_but_explicit_selection_kept() -> None:
    """An integration exclusion removes only entities that discovery added."""
    hass = Mock()
    hass.states = Mock()
    hass.states.get = Mock(return_value=None)

    data = {
        CONF_AREA_ID: "office",
        CONF_POWER_SENSORS: ["sensor.powercalc_auto", "sensor.explicit_power"],
        CONF_EXPAND_GROUPS: False,
        CONF_AUTO_ADDED_SENSORS: {CONF_POWER_SENSORS: ["sensor.powercalc_auto"]},
        CONF_EXCLUDED_INTEGRATIONS: ["powercalc"],
    }

    with patch(
        "custom_components.area_occupancy.discovery.discover_area_sensors",
        return_value={},
    ):
        resolved = resolve_area_sensors(hass, data)

    assert resolved[CONF_POWER_SENSORS] == ["sensor.explicit_power"]
    assert resolved[CONF_AUTO_ADDED_SENSORS] == {}


def test_exclude_light_power_default_and_source_domain_blacklist() -> None:
    """Light-backed power sensors are excluded by default while appliance power stays."""
    lamp_power = _reg_entry(
        "sensor.desk_lamp_power", area_id="office", device_class="power"
    )
    lamp_power.platform = "powercalc"

    ceiling_group_power = _reg_entry(
        "sensor.office_ceiling_power", area_id="office", device_class="power"
    )
    ceiling_group_power.platform = "powercalc"

    rosey_power = _reg_entry(
        "sensor.rosey_power", area_id="office", device_class="power"
    )
    rosey_power.platform = "powercalc"

    desk_plug = _reg_entry(
        "sensor.desk_plug_power", area_id="office", device_class="power"
    )
    desk_plug.platform = "zha"

    hass, registry, devices = _make_group_hass(
        entities=[lamp_power, ceiling_group_power, rosey_power, desk_plug],
        states={
            "sensor.desk_lamp_power": {
                "device_class": "power",
                "source_domain": "light",
                "source_entity": "light.desk_lamp",
            },
            "sensor.rosey_power": {
                "device_class": "power",
                "source_domain": "vacuum",
                "source_entity": "vacuum.rosey_the_robot",
            },
            "sensor.office_ceiling_power": {
                "device_class": "power",
                "entities": ["sensor.desk_lamp_power"],
            },
        },
    )
    with (
        patch(
            "custom_components.area_occupancy.discovery.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.area_occupancy.discovery.dr.async_get",
            return_value=devices,
        ),
    ):
        default_res = resolve_area_sensors(hass, {CONF_AREA_ID: "office"})
        include_lights_res = resolve_area_sensors(
            hass, {CONF_AREA_ID: "office", CONF_EXCLUDE_LIGHT_POWER: False}
        )
        vacuum_blacklisted_res = resolve_area_sensors(
            hass,
            {
                CONF_AREA_ID: "office",
                CONF_EXCLUDE_LIGHT_POWER: False,
                CONF_EXCLUDED_INTEGRATIONS: ["powercalc:vacuum"],
            },
        )
        global_exclusions_res = resolve_area_sensors(
            hass,
            {
                CONF_AREA_ID: "office",
                CONF_EXCLUDE_LIGHT_POWER: False,
                CONF_POWER_SENSORS: [
                    "sensor.rosey_power",
                    "sensor.desk_plug_power",
                ],
            },
            {
                CONF_EXCLUDE_LIGHT_POWER: True,
                CONF_EXCLUDED_SENSORS: ["sensor.desk_plug_power"],
                CONF_EXCLUDED_INTEGRATIONS: ["powercalc:vacuum"],
            },
        )

    assert default_res[CONF_POWER_SENSORS] == [
        "sensor.desk_plug_power",
        "sensor.rosey_power",
    ]
    assert include_lights_res[CONF_POWER_SENSORS] == [
        "sensor.desk_lamp_power",
        "sensor.desk_plug_power",
        "sensor.office_ceiling_power",
        "sensor.rosey_power",
    ]
    assert vacuum_blacklisted_res[CONF_POWER_SENSORS] == [
        "sensor.desk_lamp_power",
        "sensor.desk_plug_power",
        "sensor.office_ceiling_power",
    ]
    assert global_exclusions_res[CONF_POWER_SENSORS] == ["sensor.rosey_power"]
