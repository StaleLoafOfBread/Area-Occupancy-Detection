"""Group inspection and classification-aware expansion for sensor discovery."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .discovery_filters import (
    ENTITY_ID_SEPARATOR,
    SpecialExclusionContext,
    entity_domain,
    entity_state_and_attributes,
    is_ineligible_entry,
    is_own_entry,
    is_special_excluded_entry,
    is_weather_entity,
    lookup_registry_entry,
    resolve_entry_device_class,
    state_attributes,
)


@dataclass(frozen=True, slots=True)
class ResolvedGroupMember:
    """Resolved member yielded from expanding a group entity."""

    entity_id: str
    entry: er.RegistryEntry | None
    fallback_domain: str | None = None
    fallback_device_class: str | None = None


@dataclass(frozen=True, slots=True)
class _DiscoveryGroupContext:
    """Shared context passed down recursive discovery group expansion."""

    registry: er.EntityRegistry | None
    map_sensor_key: Callable[[str, str | None], str | None]
    excluded_entity_ids: Collection[str]
    excluded_platforms: set[str]
    special_exclusions: SpecialExclusionContext


def get_group_members(hass: HomeAssistant, entity_id: str) -> list[str] | None:
    """Return member entity IDs if ``entity_id`` is a group, otherwise ``None``."""
    attrs = state_attributes(hass, entity_id)
    members = attrs.get(ATTR_ENTITY_ID) if attrs else None
    if not isinstance(members, (list, tuple)):
        return None
    return [
        member
        for member in cast("list[Any] | tuple[Any, ...]", members)
        if isinstance(member, str) and ENTITY_ID_SEPARATOR in member
    ]


def is_own_entity(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
) -> bool:
    """Return True if ``entity_id`` belongs to this integration."""
    del hass
    entry = lookup_registry_entry(entity_id, registry)
    return entry is not None and is_own_entry(entry)


def group_contains_own_entity(
    hass: HomeAssistant,
    entity_id: str,
    registry: er.EntityRegistry | None = None,
    _visited: frozenset[str] | None = None,
) -> bool:
    """Return True if a group directly or recursively contains an own entity."""
    visited = _visited if _visited is not None else frozenset()
    if entity_id in visited:
        return False

    members = get_group_members(hass, entity_id)
    if members is None:
        return is_own_entity(hass, entity_id, registry)

    next_visited = visited | {entity_id}
    return any(
        group_contains_own_entity(hass, member_id, registry, next_visited)
        for member_id in members
    )


def member_matches_group_classification(
    hass: HomeAssistant,
    member_id: str,
    *,
    member_entry: er.RegistryEntry | None,
    expected_domain: str,
    expected_key: str,
    map_sensor_key: Callable[[str, str | None], str | None],
) -> bool:
    """Return True if a member's own classification matches the enclosing group."""
    if member_entry is not None:
        member_domain = member_entry.domain
        member_dc = resolve_entry_device_class(hass, member_entry, member_id)
    else:
        state, attrs = entity_state_and_attributes(hass, member_id)
        if state is None:
            return True
        member_domain = entity_domain(member_id)
        member_dc = resolve_entry_device_class(hass, None, member_id, attrs=attrs)

    if member_dc is None:
        return member_domain == expected_domain
    return map_sensor_key(member_domain, member_dc) == expected_key


def _resolve_discovery_leaf_member(
    hass: HomeAssistant,
    entity_id: str,
    entry: er.RegistryEntry | None,
    *,
    required_domain: str | None,
    fallback_domain: str | None,
    fallback_device_class: str | None,
    ctx: _DiscoveryGroupContext,
) -> list[ResolvedGroupMember]:
    """Validate and wrap a single non-group leaf discovered inside a group."""
    if entry is not None:
        # Defer entity_category filtering so parent reclassified groups can see
        # diagnostic mismatched members before choosing to keep the group itself.
        if is_ineligible_entry(
            hass, entry, ctx.excluded_platforms, allow_entity_category=True
        ) or is_special_excluded_entry(hass, entry, ctx.special_exclusions):
            return []
        if required_domain is not None and entry.domain != required_domain:
            return []
        return [
            ResolvedGroupMember(
                entity_id, entry, fallback_domain, fallback_device_class
            )
        ]

    if is_weather_entity(entity_id, None):
        return []
    state, _ = entity_state_and_attributes(hass, entity_id)
    if state is None:
        return []
    if required_domain is not None and entity_domain(entity_id) != required_domain:
        return []
    return [
        ResolvedGroupMember(entity_id, None, fallback_domain, fallback_device_class)
    ]


def _expand_discovery_node(
    hass: HomeAssistant,
    entity_id: str,
    entry: er.RegistryEntry | None,
    *,
    required_domain: str | None,
    fallback_domain: str | None,
    fallback_device_class: str | None,
    visited: frozenset[str],
    ctx: _DiscoveryGroupContext,
) -> list[ResolvedGroupMember]:
    """Recursively expand a discovery group while respecting nested classifications."""
    if entity_id in visited or entity_id in ctx.excluded_entity_ids:
        return []

    members = get_group_members(hass, entity_id)
    if members is None:
        return _resolve_discovery_leaf_member(
            hass,
            entity_id,
            entry,
            required_domain=required_domain,
            fallback_domain=fallback_domain,
            fallback_device_class=fallback_device_class,
            ctx=ctx,
        )

    if (
        visited
        and entry is not None
        and (
            is_ineligible_entry(hass, entry, ctx.excluded_platforms)
            or is_special_excluded_entry(hass, entry, ctx.special_exclusions)
        )
    ):
        return []

    group_domain = entry.domain if entry is not None else entity_domain(entity_id)
    group_dc = resolve_entry_device_class(hass, entry, entity_id)
    group_key = ctx.map_sensor_key(group_domain, group_dc)
    if group_domain != GROUP_DOMAIN and group_dc is not None and group_key is None:
        return []

    child_required_domain = required_domain
    if child_required_domain is None and group_domain != GROUP_DOMAIN:
        child_required_domain = group_domain
    child_fb_domain = group_domain if group_dc is not None else fallback_domain
    child_fb_dc = group_dc if group_dc is not None else fallback_device_class
    next_visited = visited | {entity_id}

    deduped_children: dict[str, ResolvedGroupMember] = {}
    for member_id in members:
        member_entry = lookup_registry_entry(member_id, ctx.registry)
        for resolved in _expand_discovery_node(
            hass,
            member_id,
            member_entry,
            required_domain=child_required_domain,
            fallback_domain=child_fb_domain,
            fallback_device_class=child_fb_dc,
            visited=next_visited,
            ctx=ctx,
        ):
            deduped_children.setdefault(resolved.entity_id, resolved)

    resolved_children = list(deduped_children.values())
    if (
        group_domain != GROUP_DOMAIN
        and group_dc is not None
        and group_key is not None
        and any(
            not member_matches_group_classification(
                hass,
                child.entity_id,
                member_entry=child.entry,
                expected_domain=group_domain,
                expected_key=group_key,
                map_sensor_key=ctx.map_sensor_key,
            )
            for child in resolved_children
        )
    ):
        if group_contains_own_entity(hass, entity_id, ctx.registry):
            return []
        if required_domain is not None and group_domain != required_domain:
            return []
        return [
            ResolvedGroupMember(
                entity_id, entry, fallback_domain, fallback_device_class
            )
        ]

    return [
        child
        for child in resolved_children
        if not (child.entry is not None and child.entry.entity_category is not None)
    ]


def expand_discovery_group(
    hass: HomeAssistant,
    entry: er.RegistryEntry,
    *,
    registry: er.EntityRegistry | None,
    map_sensor_key: Callable[[str, str | None], str | None],
    excluded_entity_ids: Collection[str],
    excluded_platforms: set[str],
    special_exclusions: SpecialExclusionContext,
) -> list[ResolvedGroupMember]:
    """Expand a candidate auto-discovered group entry into eligible members or keep itself."""
    ctx = _DiscoveryGroupContext(
        registry=registry,
        map_sensor_key=map_sensor_key,
        excluded_entity_ids=excluded_entity_ids,
        excluded_platforms=excluded_platforms,
        special_exclusions=special_exclusions,
    )
    return _expand_discovery_node(
        hass,
        entry.entity_id,
        entry,
        required_domain=None,
        fallback_domain=None,
        fallback_device_class=None,
        visited=frozenset(),
        ctx=ctx,
    )


def _expand_manual_node(
    hass: HomeAssistant,
    entity_id: str,
    *,
    expected_domain: str | None,
    expected_key: str,
    required_domain: str | None,
    registry: er.EntityRegistry | None,
    excluded_entity_ids: Collection[str],
    map_sensor_key: Callable[[str, str | None], str | None],
    visited: frozenset[str],
) -> list[str]:
    """Recursively expand a manually configured group while honoring classification."""
    if entity_id in visited or entity_id in excluded_entity_ids:
        return []

    members = get_group_members(hass, entity_id)
    if members is None:
        if is_own_entity(hass, entity_id, registry):
            return []
        if required_domain is not None and entity_domain(entity_id) != required_domain:
            return []
        return [entity_id]

    entry = lookup_registry_entry(entity_id, registry)
    group_domain = entry.domain if entry is not None else entity_domain(entity_id)
    group_dc = resolve_entry_device_class(hass, entry, entity_id)
    group_key = map_sensor_key(group_domain, group_dc)
    if (
        visited
        and group_domain != GROUP_DOMAIN
        and group_dc is not None
        and group_key is None
    ):
        return []

    child_required_domain = required_domain
    if child_required_domain is None and group_domain != GROUP_DOMAIN:
        child_required_domain = group_domain

    next_visited = visited | {entity_id}
    deduped_children: list[str] = []
    seen: set[str] = set()
    for member_id in members:
        for resolved_id in _expand_manual_node(
            hass,
            member_id,
            expected_domain=expected_domain,
            expected_key=expected_key,
            required_domain=child_required_domain,
            registry=registry,
            excluded_entity_ids=excluded_entity_ids,
            map_sensor_key=map_sensor_key,
            visited=next_visited,
        ):
            if resolved_id not in seen:
                seen.add(resolved_id)
                deduped_children.append(resolved_id)

    check_domain = (
        expected_domain
        if not visited
        else (
            group_domain
            if group_domain != GROUP_DOMAIN and group_dc is not None
            else None
        )
    )
    check_key = expected_key if not visited else (group_key or expected_key)
    if (
        check_domain is not None
        and (visited or deduped_children or group_dc is not None)
        and any(
            not member_matches_group_classification(
                hass,
                member_id,
                member_entry=lookup_registry_entry(member_id, registry),
                expected_domain=check_domain,
                expected_key=check_key,
                map_sensor_key=map_sensor_key,
            )
            for member_id in deduped_children
        )
    ):
        if group_contains_own_entity(hass, entity_id, registry):
            return []
        if required_domain is not None and group_domain != required_domain:
            return []
        return [entity_id]

    return deduped_children


def expand_manual_group(
    hass: HomeAssistant,
    entity_id: str,
    *,
    expected_domain: str | None,
    expected_key: str,
    registry: er.EntityRegistry | None,
    excluded_entity_ids: Collection[str],
    map_sensor_key: Callable[[str, str | None], str | None],
) -> list[str]:
    """Expand a manually selected group entity while keeping mismatched groups intact."""
    return _expand_manual_node(
        hass,
        entity_id,
        expected_domain=expected_domain,
        expected_key=expected_key,
        required_domain=expected_domain,
        registry=registry,
        excluded_entity_ids=excluded_entity_ids,
        map_sensor_key=map_sensor_key,
        visited=frozenset(),
    )
