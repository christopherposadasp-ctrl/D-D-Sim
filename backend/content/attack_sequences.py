from __future__ import annotations

from dataclasses import dataclass

from backend.content.class_progressions import get_class_progression
from backend.content.feature_definitions import unit_has_feature
from backend.engine.models.state import AttackId, UnitState


@dataclass(frozen=True)
class AttackStepDefinition:
    """One attack made as part of a larger Attack or Multiattack action."""

    allowed_weapon_ids: tuple[AttackId, ...]


@dataclass(frozen=True)
class AttackActionDefinition:
    """Ordered weapon attacks resolved by the engine without extra movement."""

    action_id: str
    display_name: str
    steps: tuple[AttackStepDefinition, ...]


def single_weapon_attack_action(
    action_id: str,
    display_name: str,
    weapon_id: AttackId,
) -> AttackActionDefinition:
    return AttackActionDefinition(
        action_id=action_id,
        display_name=display_name,
        steps=(AttackStepDefinition(allowed_weapon_ids=(weapon_id,)),),
    )


def repeated_choice_attack_action(
    action_id: str,
    display_name: str,
    allowed_weapon_ids: tuple[AttackId, ...],
    step_count: int,
) -> AttackActionDefinition:
    if step_count <= 0:
        raise ValueError("step_count must be positive.")

    return AttackActionDefinition(
        action_id=action_id,
        display_name=display_name,
        steps=tuple(AttackStepDefinition(allowed_weapon_ids=allowed_weapon_ids) for _ in range(step_count)),
    )


def get_player_attack_count(unit: UnitState) -> int:
    """Return how many weapon attacks the player makes with one Attack action.

    The current live build only exposes the level-1 fighter sample loadout, but
    the count already resolves through class progression / feature metadata so
    V4.2 can add martial classes without changing the combat loop.
    """

    if unit.class_id and unit.level is not None:
        progression = get_class_progression(unit.class_id, unit.level)
        return progression.attack_count

    if unit_has_feature(unit, "extra_attack"):
        return 2

    return 1


def build_player_attack_action(unit: UnitState) -> AttackActionDefinition:
    equipped_weapon_ids = tuple(unit.attacks.keys())
    if not equipped_weapon_ids:
        raise ValueError(f"{unit.id} has no equipped weapons for the Attack action.")

    attack_count = get_player_attack_count(unit)
    return repeated_choice_attack_action("attack", "Attack", equipped_weapon_ids, attack_count)


def build_fighter_attack_action(unit: UnitState) -> AttackActionDefinition:
    """Backward-compatible alias while the current party is still fighter-only."""

    return build_player_attack_action(unit)
