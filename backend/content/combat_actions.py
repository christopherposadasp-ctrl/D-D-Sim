from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActionTiming = Literal["action", "bonus_action", "reaction"]


@dataclass(frozen=True)
class CombatActionDefinition:
    """Static metadata for a reusable combat action.

    The engine still resolves most actions in specialized code paths, but this
    registry gives content definitions a stable vocabulary for what a creature is
    allowed to do. That keeps future monster growth data-driven instead of
    relying on ad hoc role-name branching.
    """

    action_id: str
    display_name: str
    timing: ActionTiming
    description: str
    extra_movement_multiplier: int = 0
    prevents_opportunity_attacks: bool = False


COMBAT_ACTIONS: dict[str, CombatActionDefinition] = {
    "melee_attack": CombatActionDefinition(
        action_id="melee_attack",
        display_name="Melee Attack",
        timing="action",
        description="Make a melee weapon attack.",
    ),
    "ranged_attack": CombatActionDefinition(
        action_id="ranged_attack",
        display_name="Ranged Attack",
        timing="action",
        description="Make a ranged weapon attack.",
    ),
    "dash": CombatActionDefinition(
        action_id="dash",
        display_name="Dash",
        timing="action",
        description="Spend the action to gain an extra full-speed movement budget.",
        extra_movement_multiplier=1,
    ),
    "bonus_dash": CombatActionDefinition(
        action_id="bonus_dash",
        display_name="Dash",
        timing="bonus_action",
        description="Gain an extra full-speed movement budget as a bonus action.",
        extra_movement_multiplier=1,
    ),
    "second_wind": CombatActionDefinition(
        action_id="second_wind",
        display_name="Second Wind",
        timing="bonus_action",
        description="Use the fighter's bonus-action self-heal.",
    ),
    "rage": CombatActionDefinition(
        action_id="rage",
        display_name="Rage",
        timing="bonus_action",
        description="Enter or sustain the barbarian's rage.",
    ),
    "disengage": CombatActionDefinition(
        action_id="disengage",
        display_name="Disengage",
        timing="bonus_action",
        description="Movement made with this bonus action active does not provoke opportunity attacks.",
        prevents_opportunity_attacks=True,
    ),
    "hide": CombatActionDefinition(
        action_id="hide",
        display_name="Hide",
        timing="bonus_action",
        description="Attempt to hide using terrain cover and a stealth check.",
    ),
    "bonus_unarmed_strike": CombatActionDefinition(
        action_id="bonus_unarmed_strike",
        display_name="Bonus Unarmed Strike",
        timing="bonus_action",
        description="Make one unarmed strike as a bonus action.",
    ),
    "flurry_of_blows": CombatActionDefinition(
        action_id="flurry_of_blows",
        display_name="Flurry of Blows",
        timing="bonus_action",
        description="Spend 1 Focus Point to make two unarmed strikes as a bonus action.",
    ),
    "patient_defense": CombatActionDefinition(
        action_id="patient_defense",
        display_name="Patient Defense",
        timing="bonus_action",
        description="Spend 1 Focus Point to take a dodge-focused disengaging bonus action.",
        prevents_opportunity_attacks=True,
    ),
    "step_of_the_wind": CombatActionDefinition(
        action_id="step_of_the_wind",
        display_name="Step of the Wind",
        timing="bonus_action",
        description="Spend 1 Focus Point to gain bonus-action Dash and Disengage together.",
        extra_movement_multiplier=1,
        prevents_opportunity_attacks=True,
    ),
    "aggressive_dash": CombatActionDefinition(
        action_id="aggressive_dash",
        display_name="Aggressive",
        timing="bonus_action",
        description="Gain an extra full-speed movement budget that must be used to close with an enemy.",
        extra_movement_multiplier=1,
    ),
    "opportunity_attack": CombatActionDefinition(
        action_id="opportunity_attack",
        display_name="Opportunity Attack",
        timing="reaction",
        description="Make a reaction melee attack when an enemy leaves reach.",
    ),
}


def get_combat_action(action_id: str) -> CombatActionDefinition:
    try:
        return COMBAT_ACTIONS[action_id]
    except KeyError as error:
        raise ValueError(f"Unknown combat action '{action_id}'.") from error


def get_extra_movement_multiplier(action_id: str | None) -> int:
    if not action_id:
        return 0
    action = COMBAT_ACTIONS.get(action_id)
    if not action:
        return 0
    return action.extra_movement_multiplier


def action_prevents_opportunity_attacks(action_id: str | None) -> bool:
    if not action_id:
        return False
    action = COMBAT_ACTIONS.get(action_id)
    if not action:
        return False
    return action.prevents_opportunity_attacks
