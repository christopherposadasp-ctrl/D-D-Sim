from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from backend.content.class_progressions import get_proficiency_bonus
from backend.content.feature_definitions import unit_has_granted_cunning_strike

if TYPE_CHECKING:
    from backend.engine.models.state import UnitState


CunningStrikeTrigger = Literal["sneak_attack_hit"]


@dataclass(frozen=True)
class CunningStrikeDefinition:
    strike_id: str
    display_name: str
    trigger: CunningStrikeTrigger
    description: str
    cost_d6: int = 1
    save_ability: str | None = None
    max_target_size: str | None = None


CUNNING_STRIKE_DEFINITIONS: dict[str, CunningStrikeDefinition] = {
    "poison": CunningStrikeDefinition(
        strike_id="poison",
        display_name="Poison",
        trigger="sneak_attack_hit",
        description="Spend one Sneak Attack die to force a Constitution save or poison the target.",
        save_ability="con",
    ),
    "trip": CunningStrikeDefinition(
        strike_id="trip",
        display_name="Trip",
        trigger="sneak_attack_hit",
        description="Spend one Sneak Attack die to force a Dexterity save or knock the target prone.",
        save_ability="dex",
        max_target_size="large",
    ),
    "withdraw": CunningStrikeDefinition(
        strike_id="withdraw",
        display_name="Withdraw",
        trigger="sneak_attack_hit",
        description="Spend one Sneak Attack die to unlock a half-speed no-opportunity movement leg after the attack.",
    ),
}


def get_cunning_strike_definition(strike_id: str) -> CunningStrikeDefinition:
    try:
        return CUNNING_STRIKE_DEFINITIONS[strike_id]
    except KeyError as error:
        raise ValueError(f"Unknown Cunning Strike definition '{strike_id}'.") from error


def unit_has_cunning_strike(unit: UnitState, strike_id: str) -> bool:
    return unit_has_granted_cunning_strike(unit, strike_id)


def get_cunning_strike_save_dc(unit: UnitState) -> int:
    if unit.level is None:
        return 0
    return 8 + get_proficiency_bonus(unit.level) + unit.ability_mods.dex
