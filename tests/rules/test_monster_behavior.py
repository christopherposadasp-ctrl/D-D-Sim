from __future__ import annotations

import pytest

from backend.content.enemies import BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT, unit_has_trait
from backend.engine import create_encounter
from backend.engine.ai.decision import choose_turn_decision
from backend.engine.combat.engine import execute_decision
from backend.engine.models.state import EncounterConfig, GridPosition
from backend.engine.rules.combat_rules import AttackRollOverrides, ResolveAttackArgs, resolve_attack
from backend.engine.rules.spatial import GRID_SIZE, get_occupied_squares_for_position
from tests.rules.monster_expectations import (
    LARGE_MONSTER_IDS,
    MELEE_ONLY_MONSTER_IDS,
    MONSTER_EXPECTATIONS,
    PACK_TACTICS_MONSTER_IDS,
    RANGED_SKIRMISHER_MONSTER_IDS,
)

FIXED_ATTACK_CASES = (
    ("hobgoblin_warrior", "longsword", [3, 4], ["slashing"], [8]),
    ("hobgoblin_archer", "longbow", [5], ["piercing"], [6]),
    ("tough", "heavy_crossbow", [5], ["piercing"], [6]),
    ("tough", "mace", [4], ["bludgeoning"], [6]),
    ("axe_beak", "beak", [5], ["slashing"], [7]),
    ("draft_horse", "hooves", [4], ["bludgeoning"], [8]),
    ("riding_horse", "hooves", [5], ["bludgeoning"], [8]),
    ("cultist", "ritual_sickle", [3], ["slashing", "necrotic"], [4, 1]),
    ("warrior_infantry", "spear", [4], ["piercing"], [5]),
    ("camel", "bite", [4], ["bludgeoning"], [6]),
    ("mule", "hooves", [4], ["bludgeoning"], [6]),
    ("pony", "hooves", [4], ["bludgeoning"], [6]),
    ("commoner", "club", [4], ["bludgeoning"], [4]),
    ("hyena", "bite", [4], ["piercing"], [4]),
    ("jackal", "bite", [4], ["piercing"], [3]),
)


def build_monster_benchmark_encounter(variant_id: str, *, monster_behavior: str = "balanced"):
    return create_encounter(
        EncounterConfig(
            seed=f"monster-behavior-{variant_id}-{monster_behavior}",
            enemy_preset_id=BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT[variant_id],
            player_preset_id="monster_benchmark_duo",
            player_behavior="balanced",
            monster_behavior=monster_behavior,
        )
    )


def defeat_other_units(encounter, *active_unit_ids: str) -> None:
    active_ids = set(active_unit_ids)
    for unit in encounter.units.values():
        if unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True


def set_duel_positions(encounter, variant_id: str, weapon_id: str) -> None:
    weapon = encounter.units["E1"].attacks[weapon_id]
    footprint = encounter.units["E1"].footprint
    if weapon.kind == "ranged":
        encounter.units["E1"].position = GridPosition(x=10, y=5)
        encounter.units["F1"].position = GridPosition(x=6, y=5)
        return
    if footprint.width == 2:
        encounter.units["E1"].position = GridPosition(x=5, y=5)
        encounter.units["F1"].position = GridPosition(x=7, y=5)
        return
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)


def run_actor_turn(encounter, actor_id: str):
    decision = choose_turn_decision(encounter, actor_id)
    events: list = []
    execute_decision(encounter, actor_id, decision, events, rescue_mode=False)
    return decision, events


def enemy_attack_events(events: list) -> list:
    return [event for event in events if event.event_type == "attack" and event.actor_id.startswith("E")]


def assert_occupied_squares_are_valid(encounter, unit_id: str, *other_unit_ids: str) -> None:
    unit = encounter.units[unit_id]
    occupied_squares = get_occupied_squares_for_position(unit.position, unit.footprint)
    other_squares = {
        (square.x, square.y)
        for other_unit_id in other_unit_ids
        for square in get_occupied_squares_for_position(
            encounter.units[other_unit_id].position, encounter.units[other_unit_id].footprint
        )
    }

    for square in occupied_squares:
        assert 1 <= square.x <= GRID_SIZE
        assert 1 <= square.y <= GRID_SIZE
        assert (square.x, square.y) not in other_squares


@pytest.mark.parametrize("variant_id, weapon_id, damage_rolls, damage_types, damage_totals", FIXED_ATTACK_CASES)
def test_remaining_monster_attack_math_with_fixed_rolls(
    variant_id: str,
    weapon_id: str,
    damage_rolls: list[int],
    damage_types: list[str],
    damage_totals: list[int],
) -> None:
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    set_duel_positions(encounter, variant_id, weapon_id)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id=weapon_id,
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[18], damage_rolls=damage_rolls),
        ),
    )

    assert [component.damage_type for component in attack.damage_details.damage_components] == damage_types
    assert [component.total_damage for component in attack.damage_details.damage_components] == damage_totals
    assert attack.damage_details.total_damage == sum(damage_totals)


def test_hobgoblin_archer_advantaged_longbow_hit_adds_poison_damage() -> None:
    encounter = build_monster_benchmark_encounter("hobgoblin_archer")
    defeat_other_units(encounter, "E1", "E2", "F1")
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E2"].position = GridPosition(x=6, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="longbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(
                attack_rolls=[3, 16],
                damage_rolls=[6],
                advantage_damage_rolls=[2, 3, 4],
            ),
        ),
    )

    assert attack.resolved_totals["attackMode"] == "advantage"
    assert "pack_tactics" in attack.raw_rolls["advantageSources"]
    assert [component.damage_type for component in attack.damage_details.damage_components] == ["piercing", "poison"]
    assert [component.total_damage for component in attack.damage_details.damage_components] == [7, 9]
    assert attack.damage_details.total_damage == 16


def test_hobgoblin_archer_normal_longbow_hit_does_not_add_poison_damage() -> None:
    encounter = build_monster_benchmark_encounter("hobgoblin_archer")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="longbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(
                attack_rolls=[16],
                damage_rolls=[6],
                advantage_damage_rolls=[2, 3, 4],
            ),
        ),
    )

    assert attack.resolved_totals["attackMode"] == "normal"
    assert attack.damage_details.advantage_bonus_candidate is None
    assert [component.damage_type for component in attack.damage_details.damage_components] == ["piercing"]
    assert attack.damage_details.total_damage == 7


def test_cultist_ritual_sickle_logs_slashing_and_necrotic_damage() -> None:
    encounter = build_monster_benchmark_encounter("cultist")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="ritual_sickle",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3]),
        ),
    )

    assert [component.damage_type for component in attack.damage_details.damage_components] == ["slashing", "necrotic"]
    assert [component.total_damage for component in attack.damage_details.damage_components] == [4, 1]
    assert attack.damage_details.total_damage == 5


@pytest.mark.parametrize("variant_id", PACK_TACTICS_MONSTER_IDS)
def test_pack_tactics_variants_gain_advantage_through_trait_system(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "E2", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["E2"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id=expectation.melee_fallback_weapon_id,
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[2, 17], damage_rolls=[4, 4]),
        ),
    )

    assert unit_has_trait(encounter.units["E1"], "pack_tactics") is True
    assert attack.resolved_totals["attackMode"] == "advantage"
    assert "pack_tactics" in attack.raw_rolls["advantageSources"]


@pytest.mark.parametrize("variant_id", RANGED_SKIRMISHER_MONSTER_IDS)
def test_ranged_skirmishers_open_with_ranged_weapon_on_clean_shot(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=12, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": expectation.opening_weapon_id}
    assert [event.damage_details.weapon_id for event in attacks] == [expectation.opening_weapon_id]


@pytest.mark.parametrize("variant_id", RANGED_SKIRMISHER_MONSTER_IDS)
def test_ranged_skirmishers_commit_to_melee_when_pinned(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=8, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision = choose_turn_decision(encounter, "E1")

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": expectation.melee_fallback_weapon_id}
    assert encounter.units["E1"]._committed_to_melee is True


@pytest.mark.parametrize("variant_id", MELEE_ONLY_MONSTER_IDS)
def test_melee_monsters_close_and_use_only_legal_attack(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    if variant_id in LARGE_MONSTER_IDS:
        encounter.units["E1"].position = GridPosition(x=13, y=5)
        encounter.units["F1"].position = GridPosition(x=9, y=5)
    else:
        encounter.units["E1"].position = GridPosition(x=10, y=5)
        encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": expectation.opening_weapon_id}
    assert decision.pre_action_movement is not None
    assert all(event.damage_details.weapon_id == expectation.opening_weapon_id for event in attacks)


@pytest.mark.parametrize("variant_id", LARGE_MONSTER_IDS)
def test_large_monsters_keep_footprint_legal_after_first_turn(variant_id: str) -> None:
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=13, y=5)
    encounter.units["F1"].position = GridPosition(x=9, y=5)

    _, events = run_actor_turn(encounter, "E1")

    assert enemy_attack_events(events)
    assert_occupied_squares_are_valid(encounter, "E1", "F1")
