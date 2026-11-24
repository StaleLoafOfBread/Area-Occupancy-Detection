"""Area purpose definitions for Area Occupancy Detection."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import math
from pathlib import Path
import re
from typing import Any, Final, cast
import unicodedata

from ..const import DEFAULT_DECAY_HALF_LIFE, DEFAULT_LANGUAGE, DEFAULT_PURPOSE

_LOGGER = logging.getLogger(__name__)


class AreaPurpose(StrEnum):
    """Area purpose types."""

    PASSAGEWAY = "passageway"
    UTILITY = "utility"
    BATHROOM = "bathroom"
    FOOD_PREP = "food_prep"
    EATING = "eating"
    WORKING = "working"
    SOCIAL = "social"
    RELAXING = "relaxing"
    SLEEPING = "sleeping"
    GARAGE = "garage"
    GARDEN = "garden"
    DRIVEWAY = "driveway"


class Purpose:
    """Area purpose definition with associated decay properties."""

    def __init__(
        self,
        purpose: AreaPurpose | str | None = None,
        *,
        _name: str | None = None,
        _description: str | None = None,
        _half_life: float | None = None,
        _min_prior: float = 0.0,
        _awake_half_life: float | None = None,
    ) -> None:
        """Initialize the purpose.

        Args:
            purpose: The purpose enum or string value. Defaults to SOCIAL if None or invalid.
            _name: Internal parameter for direct creation (used by PURPOSE_DEFINITIONS).
            _description: Internal parameter for direct creation (used by PURPOSE_DEFINITIONS).
            _half_life: Internal parameter for direct creation (used by PURPOSE_DEFINITIONS).
            _min_prior: Internal parameter for minimum prior floor (used by PURPOSE_DEFINITIONS).
                Transit spaces have duration-biased learned priors that are unrealistically
                low because people don't linger; this floor prevents that.
            _awake_half_life: Internal parameter for alternative half-life used outside
                sleep windows (used by PURPOSE_DEFINITIONS). Only relevant for SLEEPING;
                when set, decay uses this shorter half-life during waking hours so the
                room clears faster after everyone gets up.

        Note:
            If _name, _description, and _half_life are provided, creates instance directly.
            Otherwise, looks up from PURPOSE_DEFINITIONS.
        """
        # Direct creation from data (for PURPOSE_DEFINITIONS)
        if _name is not None and _description is not None and _half_life is not None:
            if purpose is None:
                raise ValueError("purpose must be provided when using direct creation")
            self.purpose = AreaPurpose(purpose) if isinstance(purpose, str) else purpose
            self.name = _name
            self.description = _description
            self.half_life = _half_life
            self.min_prior = _min_prior
            self.awake_half_life = _awake_half_life
            return

        # Lookup from PURPOSE_DEFINITIONS
        purpose_value = purpose if purpose is not None else AreaPurpose.SOCIAL

        try:
            purpose_enum = AreaPurpose(purpose_value)
            definition = PURPOSE_DEFINITIONS[purpose_enum]
        except (ValueError, KeyError):
            definition = PURPOSE_DEFINITIONS[AreaPurpose.SOCIAL]

        self.purpose = definition.purpose
        self.name = definition.name
        self.description = definition.description
        self.half_life = definition.half_life
        self.min_prior = definition.min_prior
        self.awake_half_life = definition.awake_half_life

    @classmethod
    def get_purpose(cls, purpose: AreaPurpose) -> Purpose:
        """Get purpose definition by enum.

        Args:
            purpose: The purpose enum to get.

        Returns:
            Purpose instance for the given enum.
        """
        return PURPOSE_DEFINITIONS[purpose]

    @classmethod
    def get_all_purposes(cls) -> dict[AreaPurpose, Purpose]:
        """Get all purpose definitions.

        Returns:
            Dictionary mapping purpose enums to Purpose instances.
        """
        return PURPOSE_DEFINITIONS.copy()

    @staticmethod
    def display_name(purpose: str) -> str:
        """Get the human-readable display name for a purpose value.

        Args:
            purpose: Purpose enum value string.

        Returns:
            Human-readable name (e.g. "Living Room"), or a title-cased
            fallback for unrecognised values.
        """
        try:
            return PURPOSE_DEFINITIONS[AreaPurpose(purpose)].name
        except (ValueError, KeyError):
            return purpose.replace("_", " ").title()

    @staticmethod
    def is_purpose_half_life(
        value: float,
        purpose: str | None = None,
        overrides: Mapping[str, int | float] | None = None,
    ) -> bool:
        """Check whether a half-life value matches the purpose's default.

        When ``purpose`` is provided, the value is compared only against that
        purpose's effective default half-life (including any global override).
        This is the correct check when deciding whether a user-entered override
        should be normalised to 0 (auto), so that switching purpose or updating
        global purpose defaults later picks up the new default.

        When ``purpose`` is ``None``, only the ``0`` sentinel returns True.
        The legacy behaviour of matching against *any* purpose's default was
        removed because it silently overwrote valid custom half-lives that
        happened to equal another purpose's default (see issue #439).

        Args:
            value: Half-life value to check.
            purpose: Purpose string to compare against. Optional.
            overrides: Optional global per-purpose half-life overrides.

        Returns:
            True if the value is 0 (auto) or equals the selected purpose's
            effective default half-life.
        """
        if value == DEFAULT_DECAY_HALF_LIFE:
            return True
        if purpose is None:
            return False
        try:
            _ = AreaPurpose(purpose)
        except ValueError:
            return False
        return get_default_decay_half_life(purpose, overrides) == value

    def cleanup(self) -> None:
        """Clean up the purpose (no-op for compatibility)."""


# Purpose definitions based on the provided table
PURPOSE_DEFINITIONS: dict[AreaPurpose, Purpose] = {
    AreaPurpose.PASSAGEWAY: Purpose(
        purpose=AreaPurpose.PASSAGEWAY,
        _name="Passageway",
        _description="Quick walk-through: halls, stair landings, entry vestibules. Motion evidence should disappear almost immediately after the last footstep.",
        _half_life=45.0,
        _min_prior=0.1,
    ),
    AreaPurpose.DRIVEWAY: Purpose(
        purpose=AreaPurpose.DRIVEWAY,
        _name="Driveway",
        _description="Parking and vehicle access area. Brief transit for entering/exiting vehicles with occasional short pauses for loading or unloading.",
        _half_life=60.0,
        _min_prior=0.05,
    ),
    AreaPurpose.UTILITY: Purpose(
        purpose=AreaPurpose.UTILITY,
        _name="Utility",
        _description="Laundry room, pantry, boot room. Short functional visits (grab the detergent, put on shoes) with little lingering.",
        _half_life=90.0,
    ),
    AreaPurpose.GARAGE: Purpose(
        purpose=AreaPurpose.GARAGE,
        _name="Garage",
        _description="Storage and workshop space. Visits range from quick item retrieval to extended projects; moderate memory accommodates varying activity patterns.",
        _half_life=180.0,
    ),
    AreaPurpose.FOOD_PREP: Purpose(
        purpose=AreaPurpose.FOOD_PREP,
        _name="Kitchen",
        _description="Kitchen work zone around the hob or countertop. Residents step away to the fridge or sink and return; a few minutes of memory prevents flicker.",
        _half_life=240.0,
    ),
    AreaPurpose.GARDEN: Purpose(
        purpose=AreaPurpose.GARDEN,
        _name="Garden",
        _description="Outdoor activity space for gardening, relaxing, or yard work. People may remain still while working or resting; longer memory accounts for sparse motion detection.",
        _half_life=360.0,
    ),
    AreaPurpose.BATHROOM: Purpose(
        purpose=AreaPurpose.BATHROOM,
        _name="Bathroom",
        _description="Showers, baths, getting ready. Motion can be obstructed or minimal; a moderate memory prevents darkness during a shower.",
        _half_life=450.0,
    ),
    AreaPurpose.EATING: Purpose(
        purpose=AreaPurpose.EATING,
        _name="Dining Room",
        _description="Dining table, breakfast bar. Family members usually stay seated 10-20 minutes but may be fairly still between bites.",
        _half_life=480.0,
    ),
    AreaPurpose.SOCIAL: Purpose(
        purpose=AreaPurpose.SOCIAL,
        _name="Living Room",
        _description="Living room, play zone, game area. Conversations or board games create sporadic motion; evidence fades gently to ride out quiet pauses.",
        _half_life=520.0,
    ),
    AreaPurpose.WORKING: Purpose(
        purpose=AreaPurpose.WORKING,
        _name="Office",
        _description='Home office, homework desk. Long seated sessions with occasional trips for coffee or printer; ten-minute half-life avoids premature "vacant".',
        _half_life=600.0,
    ),
    AreaPurpose.RELAXING: Purpose(
        purpose=AreaPurpose.RELAXING,
        _name="Media Room",
        _description='TV lounge, reading nook, music corner. People can remain very still while watching or reading; a quarter-hour memory keeps the room "occupied" through stretches of calm.',
        _half_life=620.0,
    ),
    AreaPurpose.SLEEPING: Purpose(
        purpose=AreaPurpose.SLEEPING,
        _name="Bedroom",
        _description='Bedrooms, nap pods. Motion is scarce; a long half-life prevents false vacancy during deep sleep yet lets the house revert to "empty" within a couple of hours after everyone gets up.',
        _half_life=1200.0,
        _awake_half_life=620.0,
    ),
}


def get_purpose_options() -> list[dict[str, str]]:
    """Get purpose options for SelectSelector."""
    return [
        {"value": purpose.purpose.value, "label": purpose.name}
        for purpose in PURPOSE_DEFINITIONS.values()
    ]


def _parse_positive_half_life(value: Any) -> float | None:
    """Return a positive finite float half-life override, or ``None`` if invalid."""
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    ):
        return float(value)
    return None


def get_default_decay_half_life(
    purpose: str | None = None,
    overrides: Mapping[str, int | float] | None = None,
) -> float:
    """Get the default decay half-life based on the selected purpose.

    Args:
        purpose: The purpose string value. If None, uses DEFAULT_PURPOSE.
        overrides: Optional global per-purpose half-life overrides in seconds.

    Returns:
        The half-life value in seconds for the given purpose.
    """
    default_purpose = AreaPurpose(DEFAULT_PURPOSE)
    if purpose is None:
        purpose_enum = default_purpose
    else:
        try:
            purpose_enum = AreaPurpose(purpose)
        except ValueError:
            purpose_enum = default_purpose

    if overrides and (
        override := _parse_positive_half_life(overrides.get(purpose_enum.value))
    ):
        return override

    return PURPOSE_DEFINITIONS[purpose_enum].half_life


_DEFAULT_LEXICON_LOCALE: Final = DEFAULT_LANGUAGE
_PURPOSE_KEYWORDS_DIR: Final = Path(__file__).parent / "purpose_keywords"
_MDI_ICON_PREFIX: Final = "mdi:"
_UNICODE_NORM_FORM: Final = "NFKD"
_UNICODE_COMBINING_MARK_CATEGORY: Final = "Mn"
_LEXICON_FILE_GLOB: Final = "*.json"
_WORD_BOUNDARY_PATTERN_TEMPLATE: Final = r"(?<!\w){}(?!\w)"
_UTF8_ENCODING: Final = "utf-8"

_PURPOSE_INFERENCE_ORDER: Final[tuple[AreaPurpose, ...]] = (
    AreaPurpose.BATHROOM,
    AreaPurpose.SLEEPING,
    AreaPurpose.FOOD_PREP,
    AreaPurpose.EATING,
    AreaPurpose.WORKING,
    AreaPurpose.GARAGE,
    AreaPurpose.DRIVEWAY,
    AreaPurpose.GARDEN,
    AreaPurpose.UTILITY,
    AreaPurpose.PASSAGEWAY,
    AreaPurpose.RELAXING,
    AreaPurpose.SOCIAL,
)

# Language-independent Home Assistant area icon -> purpose mapping (without "mdi:" prefix).
_PURPOSE_ICON_MAP: Final[dict[str, AreaPurpose]] = {
    **dict.fromkeys(
        ("shower", "shower-head", "bathtub", "bathtub-outline", "toilet"),
        AreaPurpose.BATHROOM,
    ),
    **dict.fromkeys(
        (
            "bed",
            "bed-empty",
            "bed-king",
            "bed-king-outline",
            "bed-queen",
            "bed-queen-outline",
            "bed-double",
            "bed-double-outline",
            "bed-single",
            "bed-single-outline",
            "bunk-bed",
            "bunk-bed-outline",
            "cradle",
            "cradle-outline",
            "sleep",
        ),
        AreaPurpose.SLEEPING,
    ),
    **dict.fromkeys(
        (
            "stove",
            "pot-steam",
            "pot-steam-outline",
            "countertop",
            "countertop-outline",
            "fridge",
            "fridge-outline",
            "microwave",
            "chef-hat",
        ),
        AreaPurpose.FOOD_PREP,
    ),
    **dict.fromkeys(
        ("silverware-fork-knife", "silverware", "table-chair", "food"),
        AreaPurpose.EATING,
    ),
    **dict.fromkeys(
        ("desk", "office-chair", "laptop", "monitor", "briefcase", "bookshelf"),
        AreaPurpose.WORKING,
    ),
    **dict.fromkeys(
        (
            "garage",
            "garage-variant",
            "garage-open",
            "garage-open-variant",
            "tools",
            "hammer-wrench",
        ),
        AreaPurpose.GARAGE,
    ),
    **dict.fromkeys(("car", "car-multiple", "parking"), AreaPurpose.DRIVEWAY),
    **dict.fromkeys(
        (
            "flower",
            "flower-outline",
            "flower-tulip",
            "flower-tulip-outline",
            "tree",
            "tree-outline",
            "grass",
            "grill",
            "grill-outline",
            "patio-heater",
            "balcony",
            "deck",
        ),
        AreaPurpose.GARDEN,
    ),
    **dict.fromkeys(
        (
            "washing-machine",
            "tumble-dryer",
            "hanger",
            "wardrobe",
            "wardrobe-outline",
            "server",
            "archive",
            "home-battery",
        ),
        AreaPurpose.UTILITY,
    ),
    **dict.fromkeys(
        (
            "stairs",
            "stairs-up",
            "stairs-down",
            "stairs-box",
            "door-open",
            "coat-rack",
        ),
        AreaPurpose.PASSAGEWAY,
    ),
    **dict.fromkeys(
        (
            "television",
            "television-classic",
            "movie",
            "movie-open",
            "filmstrip",
            "book-open-page-variant",
            "gamepad-variant",
        ),
        AreaPurpose.RELAXING,
    ),
    **dict.fromkeys(
        (
            "sofa",
            "sofa-outline",
            "sofa-single",
            "sofa-single-outline",
            "couch",
            "home-group",
            "table-furniture",
        ),
        AreaPurpose.SOCIAL,
    ),
}


@dataclass(frozen=True, slots=True)
class _CompiledPurposeLexicon:
    """Pre-compiled keyword patterns and normalized terms for one locale."""

    raw_keywords: tuple[tuple[AreaPurpose, tuple[str, ...]], ...]
    word_patterns: tuple[tuple[AreaPurpose, tuple[re.Pattern[str], ...]], ...]
    substrings: tuple[tuple[AreaPurpose, tuple[str, ...]], ...]


def _normalize_purpose_text(text: str) -> str:
    """Normalize text via NFKD decomposition, diacritic removal, and casefolding."""
    decomposed = unicodedata.normalize(_UNICODE_NORM_FORM, text)
    stripped = "".join(
        ch
        for ch in decomposed
        if unicodedata.category(ch) != _UNICODE_COMBINING_MARK_CATEGORY
    )
    return stripped.casefold()


def _compile_purpose_lexicon(raw_data: Mapping[str, Any]) -> _CompiledPurposeLexicon:
    """Compile one locale's purpose keyword mapping in precedence order."""
    raw_entries: list[tuple[AreaPurpose, tuple[str, ...]]] = []
    pattern_entries: list[tuple[AreaPurpose, tuple[re.Pattern[str], ...]]] = []
    substring_entries: list[tuple[AreaPurpose, tuple[str, ...]]] = []

    for purpose in _PURPOSE_INFERENCE_ORDER:
        terms = raw_data.get(purpose.value)
        if not isinstance(terms, list):
            continue
        cleaned = tuple(
            term.strip()
            for term in cast("list[Any]", terms)
            if isinstance(term, str) and term.strip()
        )
        if not cleaned:
            continue
        normalized_terms = tuple(
            dict.fromkeys(
                norm for term in cleaned if (norm := _normalize_purpose_text(term))
            )
        )
        raw_entries.append((purpose, cleaned))
        pattern_entries.append(
            (
                purpose,
                tuple(
                    re.compile(_WORD_BOUNDARY_PATTERN_TEMPLATE.format(re.escape(term)))
                    for term in normalized_terms
                ),
            )
        )
        substring_entries.append((purpose, normalized_terms))

    return _CompiledPurposeLexicon(
        raw_keywords=tuple(raw_entries),
        word_patterns=tuple(pattern_entries),
        substrings=tuple(substring_entries),
    )


def _normalize_locale_tag(tag: str) -> str:
    """Normalize a locale tag or filename stem to lowercase BCP-47 hyphen form."""
    return tag.replace("_", "-").casefold()


def _load_purpose_lexicons() -> dict[str, _CompiledPurposeLexicon]:
    """Load and compile all shipped purpose keyword JSON lexicons once at import."""
    lexicons: dict[str, _CompiledPurposeLexicon] = {}
    if not _PURPOSE_KEYWORDS_DIR.is_dir():
        return lexicons
    for path in sorted(_PURPOSE_KEYWORDS_DIR.glob(_LEXICON_FILE_GLOB)):
        try:
            loaded = json.loads(path.read_text(encoding=_UTF8_ENCODING))
        except (OSError, ValueError) as err:
            _LOGGER.warning("Failed to load purpose lexicon %s: %s", path.name, err)
            continue
        if isinstance(loaded, Mapping):
            lexicons[_normalize_locale_tag(path.stem)] = _compile_purpose_lexicon(
                cast("Mapping[str, Any]", loaded)
            )
    return lexicons


_PURPOSE_LEXICONS: Final[dict[str, _CompiledPurposeLexicon]] = _load_purpose_lexicons()


def _resolve_locale_chain(language: str | None) -> tuple[str, ...]:
    """Return ordered BCP-47 locale candidates for ``language``."""
    if not isinstance(language, str) or not (cleaned := language.strip()):
        return (_DEFAULT_LEXICON_LOCALE,)
    tag = _normalize_locale_tag(cleaned)
    parts = [part for part in tag.split("-") if part]
    if not parts:
        return (_DEFAULT_LEXICON_LOCALE,)
    return tuple("-".join(parts[:idx]) for idx in range(len(parts), 0, -1))


def get_purpose_keywords(
    language: str | None = None,
) -> tuple[tuple[AreaPurpose, tuple[str, ...]], ...]:
    """Return the keyword lexicon for ``language``, falling back to English."""
    for locale in _resolve_locale_chain(language):
        if (lexicon := _PURPOSE_LEXICONS.get(locale)) is not None:
            return lexicon.raw_keywords
    if (fallback := _PURPOSE_LEXICONS.get(_DEFAULT_LEXICON_LOCALE)) is not None:
        return fallback.raw_keywords
    return ()


def _match_lexicon(
    lexicon: _CompiledPurposeLexicon, normalized_texts: tuple[str, ...]
) -> AreaPurpose | None:
    """Return the first purpose matching word boundaries or substrings."""
    for purpose, patterns in lexicon.word_patterns:
        if any(
            pattern.search(text) for text in normalized_texts for pattern in patterns
        ):
            return purpose
    for purpose, keywords in lexicon.substrings:
        if any(keyword in text for text in normalized_texts for keyword in keywords):
            return purpose
    return None


def _infer_purpose_from_icon(icon: str | None) -> AreaPurpose | None:
    """Map an ``mdi:*`` area icon to an ``AreaPurpose`` when recognized."""
    if not isinstance(icon, str):
        return None
    slug = icon.strip().casefold().removeprefix(_MDI_ICON_PREFIX)
    return _PURPOSE_ICON_MAP.get(slug)


def _collect_normalized_texts(
    area_name: str | None, aliases: Collection[str] | None
) -> tuple[str, ...]:
    """Collect and normalize non-empty area names and aliases."""
    return tuple(
        norm
        for text in (area_name, *(aliases or ()))
        if isinstance(text, str)
        and text.strip()
        and (norm := _normalize_purpose_text(text))
    )


def _match_locale_chain(
    locales: tuple[str, ...], normalized_texts: tuple[str, ...]
) -> AreaPurpose | None:
    """Match normalized area texts against compiled lexicons in locale fallback order."""
    for locale in locales:
        if (lexicon := _PURPOSE_LEXICONS.get(locale)) is None:
            continue
        if matched := _match_lexicon(lexicon, normalized_texts):
            return matched
    return None


def infer_purpose_from_name(
    area_name: str | None,
    *,
    language: str | None = None,
    icon: str | None = None,
    aliases: Collection[str] | None = None,
) -> str:
    """Infer an AreaPurpose value from area name, aliases, locale lexicon, and icon."""
    normalized_texts = _collect_normalized_texts(area_name, aliases)
    locales = _resolve_locale_chain(language)
    if normalized_texts and (matched := _match_locale_chain(locales, normalized_texts)):
        return matched.value

    if icon_match := _infer_purpose_from_icon(icon):
        return icon_match.value

    if (
        normalized_texts
        and _DEFAULT_LEXICON_LOCALE not in locales
        and (
            matched := _match_locale_chain((_DEFAULT_LEXICON_LOCALE,), normalized_texts)
        )
    ):
        return matched.value

    return DEFAULT_PURPOSE
