"""Pure configuration helpers shared by every writer of area configuration.

Nothing in this module touches ``hass``. The config flow, the options flow,
the threshold ``number`` entity and any future writer (a websocket API, a
service call) validate and transform area configuration through these
functions so that the rules live in exactly one place.

Validation functions return translation keys (the ``strings.json`` error
ids), never user-facing text, so callers can surface them in a form or turn
them into an exception as they see fit.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final, TypeVar, cast

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IGNORE

from .const import (
    CONF_ADJACENT_AREAS,
    CONF_APPLIANCE_ACTIVE_STATES,
    CONF_APPLIANCES,
    CONF_AREA_ID,
    CONF_BUTTON_PULSE_DURATION,
    CONF_COVER_ACTIVE_STATES,
    CONF_COVER_SENSORS,
    CONF_CUSTOM_BINARY_ACTIVE_STATES,
    CONF_CUSTOM_BINARY_SENSORS,
    CONF_CUSTOM_NUMERIC_ACTIVE_MAX,
    CONF_CUSTOM_NUMERIC_ACTIVE_MIN,
    CONF_CUSTOM_NUMERIC_SENSORS,
    CONF_DECAY_ENABLED,
    CONF_DECAY_HALF_LIFE,
    CONF_DOOR_ACTIVE_STATE,
    CONF_DOOR_SENSORS,
    CONF_LOCK_ACTIVE_STATE,
    CONF_LOCK_SENSORS,
    CONF_MEDIA_ACTIVE_STATES,
    CONF_MEDIA_DEVICES,
    CONF_MOTION_PROB_GIVEN_FALSE,
    CONF_MOTION_PROB_GIVEN_TRUE,
    CONF_MOTION_SENSORS,
    CONF_PERSON_CONFIDENCE_THRESHOLD,
    CONF_PERSON_DEVICE_TRACKER,
    CONF_PERSON_ENTITY,
    CONF_PERSON_SLEEP_AREA,
    CONF_PERSON_SLEEP_SENSORS,
    CONF_PURPOSE,
    CONF_PURPOSE_DECAY_HALF_LIVES,
    CONF_SLEEP_DECAY_HALF_LIFE,
    CONF_THRESHOLD,
    CONF_WEIGHT_APPLIANCE,
    CONF_WEIGHT_BUTTON,
    CONF_WEIGHT_COVER,
    CONF_WEIGHT_CUSTOM_BINARY,
    CONF_WEIGHT_CUSTOM_NUMERIC,
    CONF_WEIGHT_DOOR,
    CONF_WEIGHT_ENVIRONMENTAL,
    CONF_WEIGHT_LOCK,
    CONF_WEIGHT_MEDIA,
    CONF_WEIGHT_MOTION,
    CONF_WEIGHT_POWER,
    CONF_WEIGHT_WIFI_CLIENTS,
    CONF_WEIGHT_WINDOW,
    CONF_WINDOW_ACTIVE_STATE,
    CONF_WINDOW_SENSORS,
    DEFAULT_APPLIANCE_ACTIVE_STATES,
    DEFAULT_AREA_EXCLUSION_SETTING,
    DEFAULT_AREA_EXPAND_GROUPS,
    DEFAULT_COVER_ACTIVE_STATES,
    DEFAULT_CUSTOM_BINARY_ACTIVE_STATES,
    DEFAULT_CUSTOM_NUMERIC_ACTIVE_MAX,
    DEFAULT_CUSTOM_NUMERIC_ACTIVE_MIN,
    DEFAULT_DECAY_ENABLED,
    DEFAULT_DECAY_HALF_LIFE,
    DEFAULT_DOOR_ACTIVE_STATE,
    DEFAULT_LOCK_ACTIVE_STATE,
    DEFAULT_MEDIA_ACTIVE_STATES,
    DEFAULT_MOTION_PROB_GIVEN_FALSE,
    DEFAULT_MOTION_PROB_GIVEN_TRUE,
    DEFAULT_PURPOSE,
    DEFAULT_SLEEP_CONFIDENCE_THRESHOLD,
    DEFAULT_SLEEP_DECAY_HALF_LIFE,
    DEFAULT_WEIGHT_APPLIANCE,
    DEFAULT_WEIGHT_BUTTON,
    DEFAULT_WEIGHT_COVER,
    DEFAULT_WEIGHT_CUSTOM_BINARY,
    DEFAULT_WEIGHT_CUSTOM_NUMERIC,
    DEFAULT_WEIGHT_DOOR,
    DEFAULT_WEIGHT_ENVIRONMENTAL,
    DEFAULT_WEIGHT_LOCK,
    DEFAULT_WEIGHT_MEDIA,
    DEFAULT_WEIGHT_MOTION,
    DEFAULT_WEIGHT_POWER,
    DEFAULT_WEIGHT_WIFI_CLIENTS,
    DEFAULT_WEIGHT_WINDOW,
    DEFAULT_WINDOW_ACTIVE_STATE,
    DURATION_FIELDS,
    GROUP_EXPANSION_SETTING_LABEL,
    SLEEP_PRESENCE_HALF_LIFE,
    SUBENTRY_TYPE_AREA,
    ExclusionMode,
    GroupExpansionMode,
)

_ModeT = TypeVar("_ModeT", bound=StrEnum)
_DEFAULT_EXCLUSION_SETTING_LABEL: Final = "exclusion"

# ── Shared bounds ────────────────────────────────────────────────────
# One definition for the UI selectors, the server-side validator and the
# threshold number entity. Change them here, nowhere else.
WEIGHT_STEP = 0.05
WEIGHT_MIN = 0
WEIGHT_MAX = 1

THRESHOLD_STEP = 1
THRESHOLD_MIN = 1
THRESHOLD_MAX = 100

# Explicit decay half-life bounds in seconds. ``0`` is the sentinel for "use
# the purpose default" and is always accepted (see ``apply_purpose_based_
# decay_default``).
DECAY_HALF_LIFE_MIN = 10
DECAY_HALF_LIFE_MAX = 3600
BUTTON_PULSE_DURATION_MIN = 5
BUTTON_PULSE_DURATION_MAX = 600

# Explicit sleep presence decay half-life bounds in seconds. For per-area
# overrides, ``0`` is the sentinel for "use the global default".
SLEEP_DECAY_HALF_LIFE_MIN = 10
SLEEP_DECAY_HALF_LIFE_MAX = 86400

# Translation error keys returned by decay validators.
ERROR_INVALID_DECAY_HALF_LIFE: Final = "invalid_decay_half_life"
ERROR_INVALID_SLEEP_DECAY_HALF_LIFE: Final = "invalid_sleep_decay_half_life"
ERROR_INVALID_GLOBAL_SLEEP_DECAY_HALF_LIFE: Final = (
    "invalid_global_sleep_decay_half_life"
)

# Every per-type weight key with its default, in one place so the validator
# and any future per-type UI iterate the same list.
WEIGHT_KEYS: tuple[tuple[str, float], ...] = (
    (CONF_WEIGHT_MOTION, DEFAULT_WEIGHT_MOTION),
    (CONF_WEIGHT_MEDIA, DEFAULT_WEIGHT_MEDIA),
    (CONF_WEIGHT_APPLIANCE, DEFAULT_WEIGHT_APPLIANCE),
    (CONF_WEIGHT_BUTTON, DEFAULT_WEIGHT_BUTTON),
    (CONF_WEIGHT_DOOR, DEFAULT_WEIGHT_DOOR),
    (CONF_WEIGHT_LOCK, DEFAULT_WEIGHT_LOCK),
    (CONF_WEIGHT_WINDOW, DEFAULT_WEIGHT_WINDOW),
    (CONF_WEIGHT_COVER, DEFAULT_WEIGHT_COVER),
    (CONF_WEIGHT_ENVIRONMENTAL, DEFAULT_WEIGHT_ENVIRONMENTAL),
    (CONF_WEIGHT_POWER, DEFAULT_WEIGHT_POWER),
    (CONF_WEIGHT_WIFI_CLIENTS, DEFAULT_WEIGHT_WIFI_CLIENTS),
    (CONF_WEIGHT_CUSTOM_BINARY, DEFAULT_WEIGHT_CUSTOM_BINARY),
    (CONF_WEIGHT_CUSTOM_NUMERIC, DEFAULT_WEIGHT_CUSTOM_NUMERIC),
)

# (entities key, active-state key, default active state, error key) for every
# sensor channel whose entities need an active-state selection.
_STATE_REQUIREMENTS: tuple[tuple[str, str, Any, str], ...] = (
    (
        CONF_MEDIA_DEVICES,
        CONF_MEDIA_ACTIVE_STATES,
        DEFAULT_MEDIA_ACTIVE_STATES,
        "media_states_required",
    ),
    (
        CONF_APPLIANCES,
        CONF_APPLIANCE_ACTIVE_STATES,
        DEFAULT_APPLIANCE_ACTIVE_STATES,
        "appliance_states_required",
    ),
    (
        CONF_DOOR_SENSORS,
        CONF_DOOR_ACTIVE_STATE,
        DEFAULT_DOOR_ACTIVE_STATE,
        "door_state_required",
    ),
    (
        CONF_LOCK_SENSORS,
        CONF_LOCK_ACTIVE_STATE,
        DEFAULT_LOCK_ACTIVE_STATE,
        "lock_state_required",
    ),
    (
        CONF_WINDOW_SENSORS,
        CONF_WINDOW_ACTIVE_STATE,
        DEFAULT_WINDOW_ACTIVE_STATE,
        "window_state_required",
    ),
    (
        CONF_COVER_SENSORS,
        CONF_COVER_ACTIVE_STATES,
        DEFAULT_COVER_ACTIVE_STATES,
        "cover_states_required",
    ),
    (
        CONF_CUSTOM_BINARY_SENSORS,
        CONF_CUSTOM_BINARY_ACTIVE_STATES,
        DEFAULT_CUSTOM_BINARY_ACTIVE_STATES,
        "custom_binary_states_required",
    ),
)


# ── Duration conversion ──────────────────────────────────────────────


def seconds_to_duration(seconds: float) -> dict[str, int]:
    """Convert seconds to the duration dict a ``DurationSelector`` expects.

    Args:
        seconds: Duration in seconds

    Returns:
        Dictionary with days, hours, minutes, seconds keys.
    """
    total = int(seconds)
    return {
        "days": total // 86400,
        "hours": (total % 86400) // 3600,
        "minutes": (total % 3600) // 60,
        "seconds": total % 60,
    }


def duration_to_seconds(duration: dict[str, int] | float) -> int:
    """Convert a duration dict or raw number to seconds.

    Args:
        duration: Duration dict with days/hours/minutes/seconds keys, or raw seconds.

    Returns:
        Total seconds as integer
    """
    if isinstance(duration, (int, float)):
        return int(duration)
    return (
        duration.get("days", 0) * 86400
        + duration.get("hours", 0) * 3600
        + duration.get("minutes", 0) * 60
        + duration.get("seconds", 0)
    )


def flatten_sectioned_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten sectioned user input into flat configuration dictionary.

    Converts nested section structure (motion, doors, windows, etc.) into
    a flat dictionary suitable for validation and storage.

    Args:
        user_input: Sectioned user input dictionary

    Returns:
        Flattened configuration dictionary
    """
    flattened_input = {}
    for key, value in user_input.items():
        if isinstance(value, dict) and key not in DURATION_FIELDS:
            # All sections (motion, doors, windows, wasp_in_box, etc.) are flattened the same way
            flattened_input.update(value)
        else:
            flattened_input[key] = value

    # Convert duration fields from DurationSelector format back to seconds
    for field in DURATION_FIELDS:
        if field in flattened_input:
            flattened_input[field] = duration_to_seconds(flattened_input[field])

    return flattened_input


# ── Field-level validation ───────────────────────────────────────────


def validate_threshold(value: Any) -> str | None:
    """Validate an occupancy threshold expressed as a percentage.

    Returns:
        ``None`` when valid, otherwise the ``strings.json`` error key.
    """
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < THRESHOLD_MIN
        or value > THRESHOLD_MAX
    ):
        return "invalid_threshold"
    return None


def _validate_half_life_bounds(
    value: Any,
    *,
    min_seconds: int,
    max_seconds: int,
    allow_zero: bool,
    zero_sentinel: int,
    error_key: str,
) -> str | None:
    """Validate a half-life in seconds against bounds and optional zero sentinel."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return error_key
    if allow_zero and value == zero_sentinel:
        return None
    if value < min_seconds or value > max_seconds:
        return error_key
    return None


def validate_decay_half_life(value: Any) -> str | None:
    """Validate a decay half-life in seconds.

    ``0`` means "use the purpose default" and is always valid; any other
    value must fall inside ``[DECAY_HALF_LIFE_MIN, DECAY_HALF_LIFE_MAX]``.

    Returns:
        ``None`` when valid, otherwise the ``strings.json`` error key.
    """
    return _validate_half_life_bounds(
        value,
        min_seconds=DECAY_HALF_LIFE_MIN,
        max_seconds=DECAY_HALF_LIFE_MAX,
        allow_zero=True,
        zero_sentinel=DEFAULT_DECAY_HALF_LIFE,
        error_key=ERROR_INVALID_DECAY_HALF_LIFE,
    )


def validate_sleep_decay_half_life(
    value: Any, *, allow_zero: bool = True
) -> str | None:
    """Validate a sleep presence decay half-life in seconds.

    When ``allow_zero`` is True (per-area override), ``0`` means "use the
    global default" and is valid. Any other value must fall inside
    ``[SLEEP_DECAY_HALF_LIFE_MIN, SLEEP_DECAY_HALF_LIFE_MAX]``.

    Returns:
        ``None`` when valid, otherwise the ``strings.json`` error key.
    """
    error_key = (
        ERROR_INVALID_SLEEP_DECAY_HALF_LIFE
        if allow_zero
        else ERROR_INVALID_GLOBAL_SLEEP_DECAY_HALF_LIFE
    )
    return _validate_half_life_bounds(
        value,
        min_seconds=SLEEP_DECAY_HALF_LIFE_MIN,
        max_seconds=SLEEP_DECAY_HALF_LIFE_MAX,
        allow_zero=allow_zero,
        zero_sentinel=DEFAULT_SLEEP_DECAY_HALF_LIFE,
        error_key=error_key,
    )


def validate_button_pulse_duration(value: Any) -> str | None:
    """Validate the duration of a button presence pulse in seconds."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < BUTTON_PULSE_DURATION_MIN
        or value > BUTTON_PULSE_DURATION_MAX
    ):
        return "invalid_button_pulse_duration"
    return None


def validate_sensor_states(data: dict[str, Any]) -> dict[str, str]:
    """Validate the sensor groups' state and range settings.

    The one source of these rules for every writer. The config flow runs it
    on the sensor step itself, while the fields are on screen: an error
    raised later, on a step without those fields, has nowhere to show.

    Args:
        data: Flat area configuration (defaults apply to missing keys).

    Returns:
        Errors keyed by the sensor group's entities key; empty if valid.
    """
    errors = {
        entities_key: error_key
        for entities_key, state_key, default_state, error_key in _STATE_REQUIREMENTS
        if data.get(entities_key, []) and not data.get(state_key, default_state)
    }
    # Custom numeric entities are the only channel whose active band is
    # user-supplied on both ends, so an inverted range is possible here and
    # nowhere else; it would silently match nothing.
    if data.get(CONF_CUSTOM_NUMERIC_SENSORS, []) and data.get(
        CONF_CUSTOM_NUMERIC_ACTIVE_MIN, DEFAULT_CUSTOM_NUMERIC_ACTIVE_MIN
    ) >= data.get(CONF_CUSTOM_NUMERIC_ACTIVE_MAX, DEFAULT_CUSTOM_NUMERIC_ACTIVE_MAX):
        errors[CONF_CUSTOM_NUMERIC_SENSORS] = "custom_numeric_range_invalid"
    return errors


def validate_area_config(data: dict[str, Any]) -> dict[str, str]:
    """Validate a flat area configuration dict.

    Covers everything that can be checked without Home Assistant: purpose,
    motion sensors and likelihoods, threshold, per-channel active states,
    weights and decay. Existence of the HA area itself needs the registry
    and is checked by the caller (see ``BaseOccupancyFlow._validate_config``).

    Args:
        data: Flat (un-sectioned) area configuration.

    Returns:
        Mapping of field key (or ``"base"``) to ``strings.json`` error key.
        Empty when the configuration is valid.
    """
    errors: dict[str, str] = {}

    if not data.get(CONF_AREA_ID):
        errors[CONF_AREA_ID] = "area_required"

    if not data.get(CONF_PURPOSE, DEFAULT_PURPOSE):
        errors[CONF_PURPOSE] = "purpose_required"

    if not data.get(CONF_MOTION_SENSORS, []):
        errors.setdefault("base", "motion_required")

    prob_given_true = data.get(
        CONF_MOTION_PROB_GIVEN_TRUE, DEFAULT_MOTION_PROB_GIVEN_TRUE
    )
    prob_given_false = data.get(
        CONF_MOTION_PROB_GIVEN_FALSE, DEFAULT_MOTION_PROB_GIVEN_FALSE
    )
    if prob_given_true <= prob_given_false:
        errors.setdefault("base", "prob_true_must_exceed_false")

    threshold = data.get(CONF_THRESHOLD)
    if threshold is not None and (error := validate_threshold(threshold)):
        errors[CONF_THRESHOLD] = error

    errors.update(validate_sensor_states(data))

    for key, default in WEIGHT_KEYS:
        if not WEIGHT_MIN <= data.get(key, default) <= WEIGHT_MAX:
            errors[key] = "invalid_weight"
            break

    if data.get(CONF_DECAY_ENABLED, DEFAULT_DECAY_ENABLED):
        half_life = data.get(CONF_DECAY_HALF_LIFE, DEFAULT_DECAY_HALF_LIFE)
        if error := validate_decay_half_life(half_life):
            errors[CONF_DECAY_HALF_LIFE] = error
        sleep_half_life = data.get(
            CONF_SLEEP_DECAY_HALF_LIFE, DEFAULT_SLEEP_DECAY_HALF_LIFE
        )
        if error := validate_sleep_decay_half_life(sleep_half_life, allow_zero=True):
            errors[CONF_SLEEP_DECAY_HALF_LIFE] = error

    if CONF_BUTTON_PULSE_DURATION in data and (
        error := validate_button_pulse_duration(data[CONF_BUTTON_PULSE_DURATION])
    ):
        errors[CONF_BUTTON_PULSE_DURATION] = error

    return errors


def validate_person_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize person configuration input.

    Args:
        user_input: Raw user input from the person config form

    Returns:
        Validated person data dict

    Raises:
        vol.Invalid: If required fields are missing or empty
    """
    person_entity = user_input.get(CONF_PERSON_ENTITY, "")
    sleep_sensors = user_input.get(CONF_PERSON_SLEEP_SENSORS, [])
    sleep_area = user_input.get(CONF_PERSON_SLEEP_AREA, "")

    if not person_entity:
        raise vol.Invalid("person_entity_required")
    if not sleep_sensors:
        raise vol.Invalid("sleep_sensor_required")
    if not sleep_area:
        raise vol.Invalid("sleep_area_required")

    raw_threshold = user_input.get(
        CONF_PERSON_CONFIDENCE_THRESHOLD, DEFAULT_SLEEP_CONFIDENCE_THRESHOLD
    )
    try:
        threshold = int(raw_threshold)
    except (ValueError, TypeError) as err:
        raise vol.Invalid("confidence_not_number") from err
    threshold = max(1, min(100, threshold))

    result = {
        CONF_PERSON_ENTITY: person_entity,
        CONF_PERSON_SLEEP_SENSORS: sleep_sensors,
        CONF_PERSON_SLEEP_AREA: sleep_area,
        CONF_PERSON_CONFIDENCE_THRESHOLD: threshold,
    }

    device_tracker = user_input.get(CONF_PERSON_DEVICE_TRACKER, "")
    if device_tracker:
        result[CONF_PERSON_DEVICE_TRACKER] = device_tracker

    return result


# ── Normalisation ────────────────────────────────────────────────────


def apply_purpose_based_decay_default(
    flattened_input: dict[str, Any],
    purpose: str | None,
    purpose_overrides: Mapping[str, int | float] | None = None,
) -> None:
    """Normalise the decay half-life against the selected purpose.

    If decay half-life is not set or matches the *selected* purpose's effective
    default (including any global override), store ``0`` ("use purpose value")
    so the area follows the purpose across later purpose or global default
    changes. Any other custom value is preserved (#439/#440).
    Modifies ``flattened_input`` in place.

    Args:
        flattened_input: Flattened configuration dictionary
        purpose: Selected purpose value
        purpose_overrides: Optional global per-purpose half-life overrides
    """
    if not purpose:
        return

    from .data.purpose import Purpose  # noqa: PLC0415

    user_set_decay = flattened_input.get(CONF_DECAY_HALF_LIFE)
    if user_set_decay is None or Purpose.is_purpose_half_life(
        user_set_decay, purpose, purpose_overrides
    ):
        flattened_input[CONF_DECAY_HALF_LIFE] = DEFAULT_DECAY_HALF_LIFE


# ── Global decay & tri-state option helpers ─────────────────────────


def parse_positive_int(value: Any) -> int | None:
    """Coerce ``value`` to a positive integer, rejecting booleans and invalid values."""
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return None
    return parsed if parsed > 0 else None


def parse_global_sleep_decay_half_life(options: Mapping[str, Any] | None) -> int:
    """Return the global sleep presence decay half-life in seconds."""
    if not options:
        return SLEEP_PRESENCE_HALF_LIFE
    parsed = parse_positive_int(options.get(CONF_SLEEP_DECAY_HALF_LIFE))
    return parsed if parsed is not None else SLEEP_PRESENCE_HALF_LIFE


def parse_global_purpose_decay_half_lives(
    options: Mapping[str, Any] | None,
) -> dict[str, int]:
    """Return validated global per-purpose decay half-life overrides in seconds."""
    if not options:
        return {}
    raw = options.get(CONF_PURPOSE_DECAY_HALF_LIVES)
    if not isinstance(raw, Mapping):
        return {}
    overrides: dict[str, int] = {}
    for purpose_key, half_life in cast("Mapping[Any, Any]", raw).items():
        if not isinstance(purpose_key, str):
            continue
        if (seconds := parse_positive_int(half_life)) is not None:
            overrides[purpose_key] = seconds
    return overrides


def get_purpose_decay_overrides(coordinator: Any) -> dict[str, int] | None:
    """Return global per-purpose decay overrides from a coordinator, if valid."""
    integration_config = getattr(coordinator, "integration_config", None)
    overrides = getattr(integration_config, "purpose_decay_half_lives", None)
    if not isinstance(overrides, Mapping):
        return None
    return {
        k: v
        for k, v in cast("Mapping[Any, Any]", overrides).items()
        if isinstance(k, str) and isinstance(v, int)
    }


def get_global_sleep_decay_half_life(coordinator: Any) -> int:
    """Return the resolved global sleep decay half-life from a coordinator."""
    integration_config = getattr(coordinator, "integration_config", None)
    raw = getattr(integration_config, "sleep_decay_half_life", None)
    parsed = parse_positive_int(raw)
    return parsed if parsed is not None else SLEEP_PRESENCE_HALF_LIFE


def resolve_decay_half_life(
    configured_half_life: float,
    purpose: str | None,
    coordinator: Any,
) -> float:
    """Resolve an area's configured decay half-life, expanding ``0`` via purpose and overrides."""
    if configured_half_life == DEFAULT_DECAY_HALF_LIFE:
        from .data.purpose import get_default_decay_half_life  # noqa: PLC0415

        return get_default_decay_half_life(
            purpose, get_purpose_decay_overrides(coordinator)
        )
    return float(configured_half_life)


def resolve_sleep_decay_half_life(area_value: Any, coordinator: Any) -> int:
    """Resolve an area's sleep decay half-life, falling back to the global default."""
    area_sleep_half_life = parse_positive_int(area_value)
    if area_sleep_half_life is not None:
        return area_sleep_half_life
    return get_global_sleep_decay_half_life(coordinator)


def _normalize_tri_state_mode(
    value: Any,
    enum_cls: type[_ModeT],
    *,
    true_mode: _ModeT,
    false_mode: _ModeT,
    default: _ModeT,
) -> _ModeT:
    """Normalize a legacy boolean or enum string into ``enum_cls``."""
    if value is True:
        return true_mode
    if value is False:
        return false_mode
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            return default
    return default


def _resolve_tri_state_enabled(
    area_setting: bool | str,
    global_setting: Any,
    *,
    enable_mode: StrEnum,
    disable_mode: StrEnum,
    follow_mode: StrEnum,
    setting_name: str,
    require_bool_global: bool = False,
) -> bool:
    """Resolve a tri-state area override against a global boolean default."""
    if area_setting is True or area_setting == enable_mode:
        return True
    if area_setting is False or area_setting == disable_mode:
        return False
    if area_setting == follow_mode:
        if require_bool_global and not isinstance(global_setting, bool):
            raise ValueError(
                f"Invalid global {setting_name} setting: {global_setting!r}"
            )
        return bool(global_setting)
    raise ValueError(f"Invalid {setting_name} setting: {area_setting!r}")


def normalize_exclusion_mode(
    value: Any,
    *,
    default: ExclusionMode = DEFAULT_AREA_EXCLUSION_SETTING,
    legacy_false: ExclusionMode = ExclusionMode.INCLUDE,
) -> ExclusionMode:
    """Normalize a stored exclusion setting (legacy bool or enum string) to ``ExclusionMode``."""
    return _normalize_tri_state_mode(
        value,
        ExclusionMode,
        true_mode=ExclusionMode.EXCLUDE,
        false_mode=legacy_false,
        default=default,
    )


def resolve_exclusion_enabled(
    area_setting: bool | str,
    global_setting: Any,
    *,
    setting_name: str = _DEFAULT_EXCLUSION_SETTING_LABEL,
) -> bool:
    """Resolve an area exclusion override against the global boolean default."""
    return _resolve_tri_state_enabled(
        area_setting,
        global_setting,
        enable_mode=ExclusionMode.EXCLUDE,
        disable_mode=ExclusionMode.INCLUDE,
        follow_mode=ExclusionMode.FOLLOW_GLOBAL,
        setting_name=setting_name,
        require_bool_global=False,
    )


def normalize_group_expansion_mode(
    value: Any,
    *,
    default: GroupExpansionMode = DEFAULT_AREA_EXPAND_GROUPS,
) -> GroupExpansionMode:
    """Normalize a stored group-expansion setting (legacy bool or enum string) to ``GroupExpansionMode``."""
    return _normalize_tri_state_mode(
        value,
        GroupExpansionMode,
        true_mode=GroupExpansionMode.EXPAND,
        false_mode=GroupExpansionMode.KEEP,
        default=default,
    )


def resolve_group_expansion_enabled(
    area_setting: bool | str, global_setting: Any
) -> bool:
    """Resolve an area group-expansion override against the global boolean default."""
    return _resolve_tri_state_enabled(
        area_setting,
        global_setting,
        enable_mode=GroupExpansionMode.EXPAND,
        disable_mode=GroupExpansionMode.KEEP,
        follow_mode=GroupExpansionMode.FOLLOW_GLOBAL,
        setting_name=GROUP_EXPANSION_SETTING_LABEL,
        require_bool_global=True,
    )


# ── Area list transforms ─────────────────────────────────────────────


def is_active_config_entry(entry: Any) -> bool:
    """Return True when a config entry is active (not an ignored discovery entry)."""
    return getattr(entry, "source", None) != SOURCE_IGNORE


def iter_area_subentries(entry: Any) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(subentry_id, area_data)`` for every area subentry of an entry.

    Since CONF_VERSION 19 an area lives in its own config subentry. This is
    the single place that knows that, so callers iterate areas without
    caring how they are stored.
    """
    return [
        (subentry_id, dict(subentry.data))
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_TYPE_AREA
    ]


def find_area_subentry_id(entry: Any, area_id: str) -> str | None:
    """Return the subentry id configured for ``area_id``, if any."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type == SUBENTRY_TYPE_AREA and (
            subentry.unique_id == area_id or subentry.data.get(CONF_AREA_ID) == area_id
        ):
            return subentry_id
    return None


def find_area_by_id(areas: list[dict[str, Any]], area_id: str) -> dict[str, Any] | None:
    """Find an area by ID in a list of areas.

    Args:
        areas: List of area configuration dictionaries
        area_id: Area ID to find

    Returns:
        Area configuration dictionary if found, None otherwise
    """
    for area in areas:
        if area.get(CONF_AREA_ID) == area_id:
            return area
    return None


def normalize_adjacent_areas(value: Any) -> list[str]:
    """Coerce a ``CONF_ADJACENT_AREAS`` value to a clean list of area_id strings.

    The persistence layer normally writes a list, but config storage is JSON
    and a hand-edited file (or an old import) can supply other shapes. The
    mirror/strip helpers do set ops over the values, so a stray string would
    be iterated character-by-character and silently corrupt the data. This
    helper folds every shape into a ``list[str]``:

    - ``None`` → ``[]``
    - empty string → ``[]``
    - non-empty string → ``[value]`` (treated as a single area_id, not a
      sequence of characters)
    - list / tuple / set → list of non-empty stringified items (drops falsy
      entries like ``""`` or ``None``)
    - anything else → ``[str(value)]`` (best-effort preservation; the helper
      never raises, so an unexpected scalar is kept as a single id rather
      than silently dropped)
    """
    if value is None:
        return []
    if isinstance(value, str):
        # A bare string is a single area_id, not a sequence to iterate.
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v]
    # Best-effort: keep the value as a single entry rather than crashing.
    return [str(value)]


def apply_symmetric_adjacency(
    areas: list[dict[str, Any]], updated_area: dict[str, Any]
) -> list[dict[str, Any]]:
    """Mirror an area's adjacency edits across the paired areas.

    The adjacency UI is per-area (a flat multi-select of neighbours), but
    the underlying relation is mutual. When the user saves area A with
    adjacents ``[B, C]``:

    * Add A to B's and C's adjacents (if not already there).
    * Remove A from any other area X that previously listed A but
      isn't in A's new list.

    Returns a new list; does not mutate inputs.
    """
    target_area_id = updated_area.get(CONF_AREA_ID)
    if not target_area_id:
        return areas

    target_adjacents = set(
        normalize_adjacent_areas(updated_area.get(CONF_ADJACENT_AREAS))
    )
    # Defensive: the UI excludes self from the multi-select, but a
    # hand-edited storage file or imported config could carry a stray
    # self-reference. Drop it before any set ops so downstream callers
    # never see an area listed as adjacent to itself.
    target_adjacents.discard(target_area_id)

    result: list[dict[str, Any]] = []
    sanitized_target_adjacents = sorted(target_adjacents)
    for area in areas:
        area_id = area.get(CONF_AREA_ID)
        # The target row was substituted in by the caller; rewrite its
        # adjacents field to the normalised+self-stripped value so any
        # malformed input (non-list, self-link) doesn't survive a save.
        if area_id == target_area_id:
            cleaned_target = dict(area)
            cleaned_target[CONF_ADJACENT_AREAS] = list(sanitized_target_adjacents)
            result.append(cleaned_target)
            continue
        if not area_id:
            result.append(area)
            continue

        current_adjacents = set(normalize_adjacent_areas(area.get(CONF_ADJACENT_AREAS)))
        # Same defensive guard for the partner row.
        current_adjacents.discard(area_id)

        if area_id in target_adjacents:
            new_adjacents = current_adjacents | {target_area_id}
        else:
            new_adjacents = current_adjacents - {target_area_id}

        if new_adjacents != current_adjacents:
            mirrored = dict(area)
            mirrored[CONF_ADJACENT_AREAS] = sorted(new_adjacents)
            result.append(mirrored)
        else:
            result.append(area)
    return result


def strip_adjacency_references(
    areas: list[dict[str, Any]], removed_area_id: str
) -> list[dict[str, Any]]:
    """Remove a deleted area_id from every other area's adjacents list."""
    if not removed_area_id:
        return areas
    result: list[dict[str, Any]] = []
    for area in areas:
        normalized = normalize_adjacent_areas(area.get(CONF_ADJACENT_AREAS))
        if removed_area_id in normalized:
            cleaned = dict(area)
            cleaned[CONF_ADJACENT_AREAS] = [
                a for a in normalized if a != removed_area_id
            ]
            result.append(cleaned)
        else:
            result.append(area)
    return result


def update_area_in_list(
    areas: list[dict[str, Any]],
    updated_area: dict[str, Any],
    area_id: str | None,
) -> list[dict[str, Any]]:
    """Update or add an area in a list of areas.

    After the update or add, mirrors any adjacency changes across the
    other areas (adjacency is mutual; the UI is per-area).

    Args:
        areas: List of area configuration dictionaries
        updated_area: Updated area configuration
        area_id: Area ID being updated (None for new area)

    Returns:
        Updated list of areas
    """
    updated_areas = []
    area_updated = False
    for area in areas:
        if area_id and area.get(CONF_AREA_ID) == area_id:
            updated_areas.append(updated_area)
            area_updated = True
        else:
            updated_areas.append(area)

    if not area_updated:
        updated_areas.append(updated_area)

    return apply_symmetric_adjacency(updated_areas, updated_area)


def remove_area_from_list(
    areas: list[dict[str, Any]], area_id: str
) -> list[dict[str, Any]]:
    """Remove an area from a list of areas.

    Also strips the removed area_id from every surviving area's
    adjacents list so we don't leave dangling references.

    Args:
        areas: List of area configuration dictionaries
        area_id: Area ID to remove

    Returns:
        Updated list of areas with specified area removed
    """
    surviving = [area for area in areas if area.get(CONF_AREA_ID) != area_id]
    return strip_adjacency_references(surviving, area_id)
