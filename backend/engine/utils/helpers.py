from __future__ import annotations

import copy

from backend.engine.models.state import EncounterState, Faction, UnitState, Winner


def clone_value(value):
    """Deep clone mutable engine state before stepping the simulation."""
    return copy.deepcopy(value)


def compare_unit_ids(left: str, right: str) -> int:
    left_prefix = left[0]
    right_prefix = right[0]
    left_number = int(left[1:])
    right_number = int(right[1:])

    if left_prefix != right_prefix:
        return -1 if left_prefix == "F" else 1

    return left_number - right_number


def unit_sort_key(unit_id: str) -> tuple[int, int]:
    return (0 if unit_id.startswith("F") else 1, int(unit_id[1:]))


def get_units_by_faction(state: EncounterState, faction: Faction) -> list[UnitState]:
    units = [unit for unit in state.units.values() if unit.faction == faction]
    return sorted(units, key=lambda unit: unit_sort_key(unit.id))


def is_unit_dead(unit: UnitState) -> bool:
    return unit.conditions.dead


def is_unit_conscious(unit: UnitState) -> bool:
    return unit.current_hp > 0 and not unit.conditions.dead and not unit.conditions.unconscious


def is_unit_dying(unit: UnitState) -> bool:
    return unit.current_hp == 0 and not unit.stable and not unit.conditions.dead


def is_unit_stable_at_zero(unit: UnitState) -> bool:
    return unit.current_hp == 0 and unit.stable and not unit.conditions.dead


def get_remaining_hp(units: list[UnitState]) -> int:
    return sum(unit.current_hp for unit in units)


def get_final_winner(state: EncounterState) -> Winner:
    fighters = get_units_by_faction(state, "fighters")
    goblins = get_units_by_faction(state, "goblins")
    any_living_fighter = any(not unit.conditions.dead for unit in fighters)
    any_living_goblin = any(not unit.conditions.dead for unit in goblins)

    if not any_living_goblin and any_living_fighter:
        return "fighters"
    if not any_living_fighter and any_living_goblin:
        return "goblins"
    if not any_living_goblin and not any_living_fighter:
        return "mutual_annihilation"

    return "goblins"


def describe_winner(winner: Winner | None) -> str:
    if winner == "fighters":
        return "Fighters win"
    if winner == "goblins":
        return "Goblins win"
    if winner == "mutual_annihilation":
        return "Mutual annihilation"
    return "Unresolved"
