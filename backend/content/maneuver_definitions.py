from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from backend.content.class_progressions import get_proficiency_bonus, get_progression_scalar
from backend.content.feature_definitions import unit_has_granted_maneuver

if TYPE_CHECKING:
    from backend.engine.models.state import UnitState, WeaponProfile


ManeuverTrigger = Literal["miss", "hit", "enemy_miss"]


@dataclass(frozen=True)
class ManeuverDefinition:
    maneuver_id: str
    display_name: str
    trigger: ManeuverTrigger
    description: str
    adds_superiority_damage: bool = False
    save_ability: str | None = None
    max_target_size: str | None = None


BATTLE_MASTER_LEVEL3_MANEUVERS: tuple[str, ...] = ("precision_attack", "trip_attack", "riposte")


MANEUVER_DEFINITIONS: dict[str, ManeuverDefinition] = {
    "precision_attack": ManeuverDefinition(
        maneuver_id="precision_attack",
        display_name="Precision Attack",
        trigger="miss",
        description="Spend one Superiority Die to add it to a missed weapon attack roll.",
    ),
    "trip_attack": ManeuverDefinition(
        maneuver_id="trip_attack",
        display_name="Trip Attack",
        trigger="hit",
        description="Spend one Superiority Die to add damage and possibly knock the target prone.",
        adds_superiority_damage=True,
        save_ability="str",
        max_target_size="large",
    ),
    "riposte": ManeuverDefinition(
        maneuver_id="riposte",
        display_name="Riposte",
        trigger="enemy_miss",
        description="Spend one Superiority Die and a reaction to counterattack after a melee miss.",
        adds_superiority_damage=True,
    ),
}


def get_maneuver_definition(maneuver_id: str) -> ManeuverDefinition:
    try:
        return MANEUVER_DEFINITIONS[maneuver_id]
    except KeyError as error:
        raise ValueError(f"Unknown maneuver definition '{maneuver_id}'.") from error


def unit_has_maneuver(unit: UnitState, maneuver_id: str) -> bool:
    return unit_has_granted_maneuver(unit, maneuver_id)


def get_superiority_die_sides(unit: UnitState) -> int:
    if unit.class_id != "fighter" or unit.level is None:
        return 0
    return get_progression_scalar(unit.class_id, unit.level, "superiority_die_sides", 0)


def get_maneuver_save_dc(unit: UnitState, weapon: WeaponProfile) -> int:
    if unit.level is None:
        return 0
    ability_id = weapon.attack_ability or "str"
    ability_modifier = getattr(unit.ability_mods, ability_id)
    return 8 + get_proficiency_bonus(unit.level) + ability_modifier


def spend_superiority_die(unit: UnitState) -> bool:
    return unit.resources.spend_pool("superiority_dice", 1)
