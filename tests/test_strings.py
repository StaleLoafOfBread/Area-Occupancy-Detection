"""The user-facing strings match what the flows actually render.

Home Assistant silently falls back to the raw config key when a section,
field or error has no string, so a gap here is invisible in tests and only
shows up as ``custom_binary_sensors`` where a label should be. These checks
walk the real flow constants rather than a copy of them.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from custom_components.area_occupancy.config_flow import (
    _COMMON_TRANSLATION_KEYS,
    AUTO_ADDED_SECTION,
    EXPLICIT_SECTION,
    _create_global_exclusions_schema,
    _create_global_general_schema,
    _create_global_purpose_decay_schema,
    _create_global_sleep_schema,
    _create_sensors_step_schema,
)
from custom_components.area_occupancy.const import (
    DASHBOARD_STRATEGY_FILENAME,
    FRONTEND_DIR,
)

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "area_occupancy"
)
STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = COMPONENT / "translations/en.json"

# Every flow scope that renders the sectioned sensors step. The subentry
# flow is the one users reach from the integration page, so a gap there is
# the most visible of the three.
SENSOR_STEP_SCOPES: tuple[tuple[str, ...], ...] = (
    ("config", "step", "area_sensors"),
    ("options", "step", "area_sensors"),
    ("config_subentries", "area", "step", "area_sensors"),
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dig(data: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    for key in path:
        data = data[key]
    return data


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            out.update(_flatten(value, f"{prefix}.{key}"))
        return out
    return {prefix: data}


class TestSensorSections:
    """Sensor section labels match the sectioned schema rendered by every flow."""

    @staticmethod
    def _rendered_explicit_fields() -> set[str]:
        fake_hass = SimpleNamespace(
            data={}, states=SimpleNamespace(async_entity_ids=lambda *_a, **_kw: [])
        )
        with (
            patch(
                "custom_components.area_occupancy.config_flow.er.async_get",
                return_value=SimpleNamespace(entities={}),
            ),
            patch(
                "custom_components.area_occupancy.config_flow.dr.async_get",
                return_value=SimpleNamespace(devices={}),
            ),
        ):
            schema = _create_sensors_step_schema(hass=fake_hass)
        explicit_section = schema[EXPLICIT_SECTION]
        return {str(key) for key in explicit_section.schema.schema}

    @pytest.mark.parametrize("scope", SENSOR_STEP_SCOPES)
    def test_every_group_has_a_section(self, scope: tuple[str, ...]) -> None:
        sections = _dig(_load(STRINGS), scope)["sections"]
        assert EXPLICIT_SECTION in sections, (
            f"{'.'.join(scope)} is missing the '{EXPLICIT_SECTION}' section"
        )

    @pytest.mark.parametrize("scope", SENSOR_STEP_SCOPES)
    def test_every_section_is_a_real_group(self, scope: tuple[str, ...]) -> None:
        sections = _dig(_load(STRINGS), scope)["sections"]
        allowed = {EXPLICIT_SECTION, AUTO_ADDED_SECTION}
        assert set(sections) <= allowed, (
            f"{'.'.join(scope)} has unexpected sections: "
            f"{sorted(set(sections) - allowed)}"
        )

    @pytest.mark.parametrize("scope", SENSOR_STEP_SCOPES)
    def test_every_field_is_labelled(self, scope: tuple[str, ...]) -> None:
        sections = _dig(_load(STRINGS), scope)["sections"]
        for name, section in sections.items():
            assert section.get("name"), f"{'.'.join(scope)}.{name} has no name"
            assert section.get("data"), f"{'.'.join(scope)}.{name} has no labels"
        rendered = self._rendered_explicit_fields()
        explicit_labels = set(sections[EXPLICIT_SECTION]["data"])
        assert rendered <= explicit_labels, (
            f"{'.'.join(scope)}.{EXPLICIT_SECTION} is missing labels for "
            f"{sorted(rendered - explicit_labels)}"
        )


class TestGlobalSettings:
    """Each global settings form field is labelled and described."""

    @pytest.mark.parametrize(
        ("step_id", "schema_factory"),
        [
            ("global_sleep", _create_global_sleep_schema),
            ("global_purpose_decay", _create_global_purpose_decay_schema),
            ("global_general", _create_global_general_schema),
        ],
    )
    def test_every_field_has_a_label_and_a_description(
        self, step_id: str, schema_factory
    ) -> None:
        step = _dig(_load(STRINGS), ("options", "step", step_id))
        fields = {str(key) for key in schema_factory({}).schema}
        assert fields <= set(step["data"]), (
            f"{step_id} has no label for {sorted(fields - set(step['data']))}"
        )
        assert fields <= set(step["data_description"]), (
            f"{step_id} has no description for "
            f"{sorted(fields - set(step['data_description']))}"
        )


class TestGlobalExclusions:
    """Each section and field of the global exclusions form is labelled and described."""

    def test_every_field_has_a_label_and_a_description(self) -> None:
        step = _dig(_load(STRINGS), ("options", "step", "global_exclusions"))
        schema = _create_global_exclusions_schema({}).schema
        sections_strings = step["sections"]
        assert {str(key) for key in schema} <= set(sections_strings)

        for section_marker, section_obj in schema.items():
            section_name = str(section_marker)
            sec_strings = sections_strings[section_name]
            assert sec_strings.get("name"), (
                f"global_exclusions.{section_name} has no name"
            )
            fields = {str(key) for key in section_obj.schema.schema}
            assert fields <= set(sec_strings["data"]), (
                f"global_exclusions.{section_name} has no label for "
                f"{sorted(fields - set(sec_strings['data']))}"
            )
            assert fields <= set(sec_strings["data_description"]), (
                f"global_exclusions.{section_name} has no description for "
                f"{sorted(fields - set(sec_strings['data_description']))}"
            )


class TestCommonTranslations:
    """Flat ``common`` translations cover backend and frontend dashboard keys."""

    def test_common_keys_are_hassfest_valid(self) -> None:
        common = _load(STRINGS)["common"]
        assert isinstance(common, dict)
        assert common
        for key, value in common.items():
            assert re.fullmatch(r"[a-z0-9_]+", key), f"Invalid common slug: {key}"
            assert isinstance(value, str)
            assert value
            assert "[%key:" not in value
            assert "{{" not in value
            assert "}}" not in value

    def test_config_flow_common_keys_exist(self) -> None:
        common = _load(STRINGS)["common"]
        missing = sorted(set(_COMMON_TRANSLATION_KEYS) - set(common))
        assert not missing, (
            f"strings.json['common'] missing config_flow keys: {missing}"
        )

    def test_dashboard_strategy_i18n_keys_exist(self) -> None:
        common = _load(STRINGS)["common"]
        strategy_source = (
            COMPONENT / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
        ).read_text(encoding="utf-8")
        block = re.search(
            r"const\s+I18N_KEY\s*=\s*Object\.freeze\(\{([\s\S]*?)\}\);",
            strategy_source,
        )
        assert block is not None, "I18N_KEY map not found in dashboard strategy"
        keys = set(re.findall(r':\s*"([a-z0-9_]+)"', block.group(1)))
        assert keys
        missing = sorted(keys - set(common))
        assert not missing, f"strings.json['common'] missing frontend keys: {missing}"


class TestTranslationsMatchStrings:
    """``translations/en.json`` is generated from ``strings.json``."""

    def test_identical(self) -> None:
        assert _flatten(_load(STRINGS)) == _flatten(_load(TRANSLATIONS)), (
            "translations/en.json has drifted from strings.json"
        )
