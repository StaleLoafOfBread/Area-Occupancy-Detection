"""Tests for the bundled time-priors Lovelace card registration (issue #559)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from unittest.mock import AsyncMock, Mock, patch

import pytest

import custom_components.area_occupancy as aod_init
from custom_components.area_occupancy import async_setup
from custom_components.area_occupancy.const import (
    DASHBOARD_STRATEGY_FILENAME,
    DOMAIN,
    FRONTEND_DIR,
    FRONTEND_REGISTERED_KEY,
    FRONTEND_URL_BASE,
    TIME_PRIORS_CARD_FILENAME,
)
from homeassistant.core import HomeAssistant

COMPONENT_DIR = Path(aod_init.__file__).parent
CARD_URL = f"{FRONTEND_URL_BASE}/{TIME_PRIORS_CARD_FILENAME}"
STRATEGY_URL = f"{FRONTEND_URL_BASE}/{DASHBOARD_STRATEGY_FILENAME}"


@pytest.fixture
def frontend_mocks(hass: HomeAssistant):
    """Stub the http/frontend APIs async_setup talks to."""
    hass.http = Mock()
    hass.http.async_register_static_paths = AsyncMock()
    integration = Mock(version="2026.9.99")
    with (
        patch.object(aod_init, "add_extra_js_url") as add_js,
        patch.object(
            aod_init, "async_get_integration", AsyncMock(return_value=integration)
        ),
    ):
        yield hass.http.async_register_static_paths, add_js


async def test_registers_static_paths_for_bundled_frontend_assets(
    hass: HomeAssistant, frontend_mocks
) -> None:
    """The static path points at the card file shipped inside the integration."""
    register, _ = frontend_mocks

    assert await async_setup(hass, {}) is True

    register.assert_awaited_once()
    (configs,) = register.await_args.args
    assert {config.url_path for config in configs} == {CARD_URL, STRATEGY_URL}
    for config in configs:
        filename = config.url_path.rsplit("/", 1)[-1]
        assert Path(config.path) == COMPONENT_DIR / FRONTEND_DIR / filename
        assert config.cache_headers is True


async def test_registers_versioned_js_urls_once(
    hass: HomeAssistant, frontend_mocks
) -> None:
    """The extra module URL carries the integration version and is added once."""
    register, add_js = frontend_mocks

    assert await async_setup(hass, {}) is True
    assert await async_setup(hass, {}) is True

    assert {call.args[1] for call in add_js.call_args_list} == {
        f"{CARD_URL}?v=2026.9.99",
        f"{STRATEGY_URL}?v=2026.9.99",
    }
    assert add_js.call_count == 2
    register.assert_awaited_once()
    assert hass.data[FRONTEND_REGISTERED_KEY] is True


async def test_missing_card_file_warns_but_registers_strategy(
    hass: HomeAssistant, frontend_mocks, caplog: pytest.LogCaptureFixture
) -> None:
    """A missing card file is logged and skipped; setup still succeeds."""
    register, add_js = frontend_mocks

    with (
        patch.object(aod_init, "TIME_PRIORS_CARD_FILENAME", "does-not-exist.js"),
        caplog.at_level(logging.WARNING, logger=aod_init.__name__),
    ):
        assert await async_setup(hass, {}) is True

    register.assert_awaited_once()
    (configs,) = register.await_args.args
    assert [config.url_path for config in configs] == [STRATEGY_URL]
    add_js.assert_called_once_with(hass, f"{STRATEGY_URL}?v=2026.9.99")
    assert hass.data[FRONTEND_REGISTERED_KEY] is True
    assert "Time-priors card not found" in caplog.text


def test_card_ships_inside_integration() -> None:
    """The card lives in the integration package so the release zip carries it."""
    card = COMPONENT_DIR / FRONTEND_DIR / TIME_PRIORS_CARD_FILENAME
    assert card.is_file()
    source = card.read_text(encoding="utf-8")
    # A second load (old manual /local resource + bundled URL) must not throw.
    assert "if (customElements.get(CARD_TAG)) return;" in source
    # Loaded as an extra module the card can define itself before the
    # frontend patches CustomElementRegistry, which hides that definition from
    # Lovelace ("Configuration error"); it registers again after the patch.
    assert 'customElements.whenDefined("home-assistant").then(registerCard)' in source


def test_manifest_declares_http_and_frontend() -> None:
    """Serving the card needs http and frontend set up before the integration."""
    manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text())
    assert manifest["domain"] == DOMAIN
    assert {"http", "frontend"} <= set(manifest["dependencies"])


def test_dashboard_strategy_uses_backend_decay_clear_at() -> None:
    """The dashboard strategy reads decay_clear_at and uses localized Holding label."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    assert strategy.is_file()
    source = strategy.read_text(encoding="utf-8")
    assert "decay_clear_at" in source
    assert "startCountdownTo(decayClearAtMs)" in source
    assert "I18N_KEY.DECAY_HOLDING" in source
    assert '"dashboard_decay_holding"' in source
    strings = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    assert strings["common"]["dashboard_decay_holding"] == "Holding"


def test_dashboard_strategy_sensor_cards_show_decay_countdown() -> None:
    """Decaying sensor cards on area subviews show a live countdown."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    assert strategy.is_file()
    source = strategy.read_text(encoding="utf-8")
    assert "decaying_expires_at" in source
    assert "startCountdownTo(expiresAtMs)" in source
    assert "startCountdownFrom" not in source
    assert "decaying_half_lives" not in source


def test_dashboard_strategy_replaces_history_with_conditional_info_view() -> None:
    """The dashboard strategy omits the History view and gates Info on detected issues."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    source = strategy.read_text(encoding="utf-8")
    assert "buildHistorySections" not in source
    assert 'path: "history"' not in source
    assert 'path: "info"' in source
    assert "collectDashboardIssues" in source
    assert "issues.hasIssues" in source


def test_probability_card_scales_viewbox_without_distortion() -> None:
    """The probability history SVG tracks container width instead of stretching."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    source = strategy.read_text(encoding="utf-8")
    assert 'preserveAspectRatio="none"' not in source
    assert "new ResizeObserver(" in source
    assert re.search(r'this\._svgEl\.setAttribute\(\s*"viewBox"', source)


def test_probability_card_history_link_includes_full_selected_range() -> None:
    """The History link passes both start_date and end_date for the active range."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    source = strategy.read_text(encoding="utf-8")
    assert 'START_DATE: "start_date"' in source
    assert 'END_DATE: "end_date"' in source
    assert "HISTORY_QUERY_PARAM.END_DATE" in source
    assert "this._buildHistoryUrl(Date.now())" in source


def test_strategy_uses_environmental_attribute_backoff_and_threshold_max() -> None:
    """Dashboard strategy uses environmental_entities, WS backoff, and threshold max 100."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    source = strategy.read_text(encoding="utf-8")
    assert "environmental_entities" in source
    assert "HISTORY_ERROR_BACKOFF_MS" in source
    assert "_nextFetchAt" in source
    assert "THRESHOLD_MAX: 100" in source


def test_strategy_uses_frontend_translations_instead_of_hardcoded_defaults() -> None:
    """Dashboard strategy loads translations via frontend/get_translations and I18N_KEY."""
    strategy = COMPONENT_DIR / FRONTEND_DIR / DASHBOARD_STRATEGY_FILENAME
    source = strategy.read_text(encoding="utf-8")
    assert '"frontend/get_translations"' in source
    assert "I18N_KEY" in source
    assert "DASHBOARD_DESCRIPTION:" not in source
    assert "UNASSIGNED_FLOOR_LABEL:" not in source
    assert "PROBABILITY_CARD_TITLE:" not in source
    assert "DECAY_IMMINENT_LABEL:" not in source
