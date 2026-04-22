from __future__ import annotations

import pytest

from backend.content.enemies import BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT, unit_has_trait
from backend.engine import create_encounter
from backend.engine.ai.decision import choose_turn_decision
from backend.engine.combat.engine import execute_decision, resolve_attack_action
from backend.engine.models.state import EncounterConfig, GridPosition
from backend.engine.rules.combat_rules import (
    AttackRollOverrides,
    ResolveAttackArgs,
    ResolveSavingThrowArgs,
    SavingThrowOverrides,
    resolve_attack,
    resolve_saving_throw,
)
from backend.engine.rules.spatial import GRID_SIZE, get_occupied_squares_for_position
from tests.rules.monster_expectations import (
    MELEE_ONLY_MONSTER_IDS,
    MONSTER_EXPECTATIONS,
    MULTI_SQUARE_MONSTER_IDS,
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
    ("goblin_minion", "dagger", [3], ["piercing"], [5]),
    ("goblin_minion", "dagger_throw", [3], ["piercing"], [5]),
    ("skeleton", "shortsword", [3], ["piercing"], [6]),
    ("skeleton", "shortbow", [3], ["piercing"], [6]),
    ("zombie", "slam", [4], ["bludgeoning"], [5]),
    ("giant_rat", "bite", [2], ["piercing"], [5]),
    ("giant_fire_beetle", "bite", [], ["fire"], [1]),
    ("giant_weasel", "bite", [2], ["piercing"], [5]),
    ("worg", "bite", [4], ["piercing"], [7]),
    ("animated_armor", "slam", [3], ["bludgeoning"], [5]),
    ("dire_wolf", "bite", [5], ["piercing"], [8]),
    ("awakened_shrub", "rake", [], ["slashing"], [1]),
    ("awakened_tree", "slam", [4, 3, 2], ["bludgeoning"], [13]),
    ("lemure", "vile_slime", [3], ["poison"], [3]),
    ("ogre", "greatclub", [4, 5], ["bludgeoning"], [13]),
    ("ogre", "javelin", [3, 4], ["piercing"], [11]),
    ("ogre", "javelin_throw", [3, 4], ["piercing"], [11]),
    ("black_bear", "rend", [3], ["slashing"], [5]),
    ("brown_bear", "bite", [4], ["piercing"], [7]),
    ("brown_bear", "claw", [2], ["slashing"], [5]),
    ("tiger", "rend", [4, 3], ["slashing"], [10]),
    ("berserker", "greataxe", [6], ["slashing"], [9]),
    ("gnoll_warrior", "rend", [3], ["piercing"], [5]),
    ("gnoll_warrior", "bone_bow", [5], ["piercing"], [6]),
    ("giant_hyena", "bite", [4, 3], ["piercing"], [10]),
    ("bandit_captain", "captain_scimitar", [3], ["slashing"], [6]),
    ("bandit_captain", "pistol", [5], ["piercing"], [8]),
    ("goblin_boss", "scimitar", [3], ["slashing"], [5]),
    ("goblin_boss", "shortbow", [3], ["piercing"], [5]),
    ("bugbear_warrior", "grab", [3, 4], ["bludgeoning"], [9]),
    ("bugbear_warrior", "light_hammer", [2, 3, 2], ["bludgeoning"], [9]),
    ("bugbear_warrior", "light_hammer_throw", [2, 3, 2], ["bludgeoning"], [9]),
    ("noble", "rapier", [5], ["piercing"], [6]),
    ("mastiff", "bite", [4], ["piercing"], [5]),
    ("giant_crab", "claw", [4], ["bludgeoning"], [5]),
    ("giant_badger", "bite", [3, 2], ["piercing"], [6]),
    ("giant_lizard", "bite", [5], ["piercing"], [7]),
    ("violet_fungus", "rotting_touch", [5], ["necrotic"], [5]),
    ("polar_bear", "rend", [4], ["slashing"], [9]),
    ("guard_captain", "longsword", [3, 4], ["slashing"], [11]),
    ("guard_captain", "javelin_throw", [2, 3, 4], ["piercing"], [13]),
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
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=5 + footprint.width, y=5)


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


def test_animated_armor_multiattack_resolves_two_slam_attacks() -> None:
    encounter = build_monster_benchmark_encounter("animated_armor")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "slam"}
    assert [event.damage_details.weapon_id for event in attacks] == ["slam", "slam"]


def test_black_bear_multiattack_resolves_two_rend_attacks() -> None:
    encounter = build_monster_benchmark_encounter("black_bear")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "rend"}
    assert [event.damage_details.weapon_id for event in attacks] == ["rend", "rend"]


def test_brown_bear_multiattack_uses_bite_then_claw_and_claw_prones_large_or_smaller_targets() -> None:
    encounter = build_monster_benchmark_encounter("brown_bear")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "bite"}
    assert [event.damage_details.weapon_id for event in attacks] == ["bite", "claw"]

    fresh_encounter = build_monster_benchmark_encounter("brown_bear")
    defeat_other_units(fresh_encounter, "E1", "F1")
    fresh_encounter.units["E1"].position = GridPosition(x=5, y=5)
    fresh_encounter.units["F1"].position = GridPosition(x=7, y=5)
    claw_attack, _ = resolve_attack(
        fresh_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="claw",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2]),
        ),
    )

    assert claw_attack.damage_details.attack_riders_applied == ["prone_on_hit"]
    assert fresh_encounter.units["F1"].conditions.prone is True

    blocked_encounter = build_monster_benchmark_encounter("brown_bear")
    defeat_other_units(blocked_encounter, "E1", "F1")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=7, y=5)
    blocked_encounter.units["F1"].size_category = "huge"

    blocked_attack, _ = resolve_attack(
        blocked_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="claw",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2]),
        ),
    )

    assert blocked_attack.damage_details.attack_riders_applied is None
    assert blocked_encounter.units["F1"].conditions.prone is False


def test_mastiff_bite_knocks_medium_targets_prone_but_not_large_targets() -> None:
    encounter = build_monster_benchmark_encounter("mastiff")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    prone_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert prone_attack.damage_details.attack_riders_applied == ["prone_on_hit"]
    assert encounter.units["F1"].conditions.prone is True

    blocked_encounter = build_monster_benchmark_encounter("mastiff")
    defeat_other_units(blocked_encounter, "E1", "F1")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=6, y=5)
    blocked_encounter.units["F1"].size_category = "large"

    blocked_attack, _ = resolve_attack(
        blocked_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert blocked_attack.damage_details.attack_riders_applied is None
    assert blocked_encounter.units["F1"].conditions.prone is False


def test_giant_crab_claw_grapples_medium_targets_with_dc_11_but_not_large_targets() -> None:
    encounter = build_monster_benchmark_encounter("giant_crab")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    grapple_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="claw",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert grapple_attack.damage_details.attack_riders_applied == ["grapple_on_hit"]
    assert any(
        effect.kind == "grappled_by"
        and effect.source_id == "E1"
        and effect.escape_dc == 11
        and effect.maintain_reach_feet == 5
        for effect in encounter.units["F1"].temporary_effects
    )

    blocked_encounter = build_monster_benchmark_encounter("giant_crab")
    defeat_other_units(blocked_encounter, "E1", "F1")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=6, y=5)
    blocked_encounter.units["F1"].size_category = "large"

    blocked_attack, _ = resolve_attack(
        blocked_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="claw",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert blocked_attack.damage_details.attack_riders_applied is None
    assert any(effect.kind == "grappled_by" for effect in blocked_encounter.units["F1"].temporary_effects) is False


def test_tiger_rend_prone_is_size_gated() -> None:
    encounter = build_monster_benchmark_encounter("tiger")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="rend",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
        ),
    )

    assert attack.damage_details.attack_riders_applied == ["prone_on_hit"]
    assert encounter.units["F1"].conditions.prone is True

    blocked_encounter = build_monster_benchmark_encounter("tiger")
    defeat_other_units(blocked_encounter, "E1", "F1")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=7, y=5)
    blocked_encounter.units["F1"].size_category = "huge"

    blocked_attack, _ = resolve_attack(
        blocked_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="rend",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
        ),
    )

    assert blocked_attack.damage_details.attack_riders_applied is None
    assert blocked_encounter.units["F1"].conditions.prone is False


def test_berserker_bloodied_frenzy_grants_attack_and_save_advantage_only_while_bloodied() -> None:
    encounter = build_monster_benchmark_encounter("berserker")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    normal_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="greataxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[16], damage_rolls=[6]),
        ),
    )
    normal_save = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="E1",
            ability="wis",
            dc=10,
            reason="berserker-normal",
            overrides=SavingThrowOverrides(save_rolls=[16]),
        ),
    )

    encounter.units["E1"].current_hp = encounter.units["E1"].max_hp // 2

    bloodied_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="greataxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[3, 16], damage_rolls=[6]),
        ),
    )
    bloodied_save = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="E1",
            ability="wis",
            dc=10,
            reason="berserker-bloodied",
            overrides=SavingThrowOverrides(save_rolls=[3, 16]),
        ),
    )

    assert normal_attack.resolved_totals["attackMode"] == "normal"
    assert "bloodied_frenzy" not in normal_attack.raw_rolls["advantageSources"]
    assert normal_save.resolved_totals["saveMode"] == "normal"
    assert "bloodied_frenzy" not in normal_save.raw_rolls["advantageSources"]
    assert bloodied_attack.resolved_totals["attackMode"] == "advantage"
    assert "bloodied_frenzy" in bloodied_attack.raw_rolls["advantageSources"]
    assert bloodied_save.resolved_totals["saveMode"] == "advantage"
    assert "bloodied_frenzy" in bloodied_save.raw_rolls["advantageSources"]


def test_gnoll_warrior_rampage_requires_a_bloodied_target_and_only_triggers_once() -> None:
    blocked_encounter = build_monster_benchmark_encounter("gnoll_warrior")
    defeat_other_units(blocked_encounter, "E1", "F1", "F3")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=6, y=5)
    blocked_encounter.units["F1"].max_hp = 10
    blocked_encounter.units["F1"].current_hp = 6
    blocked_encounter.units["F3"].position = GridPosition(x=8, y=5)

    blocked_events = resolve_attack_action(
        blocked_encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "rend"},
        step_overrides=[AttackRollOverrides(attack_rolls=[15], damage_rolls=[3])],
    )

    assert not any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in blocked_events
    )
    assert blocked_encounter.units["E1"].resource_pools["rampage_uses"] == 1

    encounter = build_monster_benchmark_encounter("gnoll_warrior")
    defeat_other_units(encounter, "E1", "F1", "F3")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)
    encounter.units["F1"].max_hp = 10
    encounter.units["F1"].current_hp = 5
    encounter.units["F3"].position = GridPosition(x=8, y=5)

    events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "rend"},
        step_overrides=[AttackRollOverrides(attack_rolls=[15], damage_rolls=[3])],
    )
    attack_events = [event for event in events if event.event_type == "attack"]

    assert any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in events
    )
    assert len(attack_events) == 2
    assert attack_events[0].target_ids == ["F1"]
    assert attack_events[1].target_ids == ["F3"]
    assert encounter.units["E1"].resource_pools["rampage_uses"] == 0

    encounter.units["F3"].max_hp = 10
    encounter.units["F3"].current_hp = 5
    second_events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F3", "weapon_id": "rend"},
        step_overrides=[AttackRollOverrides(attack_rolls=[15], damage_rolls=[3])],
    )

    assert not any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in second_events
    )


def test_giant_hyena_rampage_requires_a_bloodied_target_and_only_triggers_once() -> None:
    blocked_encounter = build_monster_benchmark_encounter("giant_hyena")
    defeat_other_units(blocked_encounter, "E1", "F1", "F3")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=7, y=5)
    blocked_encounter.units["F1"].max_hp = 10
    blocked_encounter.units["F1"].current_hp = 6
    blocked_encounter.units["F3"].position = GridPosition(x=9, y=5)

    blocked_events = resolve_attack_action(
        blocked_encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "bite"},
        step_overrides=[AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3])],
    )

    assert not any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in blocked_events
    )
    assert blocked_encounter.units["E1"].resource_pools["rampage_uses"] == 1

    encounter = build_monster_benchmark_encounter("giant_hyena")
    defeat_other_units(encounter, "E1", "F1", "F3")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].max_hp = 10
    encounter.units["F1"].current_hp = 5
    encounter.units["F3"].position = GridPosition(x=9, y=5)

    events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "bite"},
        step_overrides=[AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3])],
    )
    attack_events = [event for event in events if event.event_type == "attack"]

    assert any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in events
    )
    assert len(attack_events) == 2
    assert attack_events[0].target_ids == ["F1"]
    assert attack_events[1].target_ids == ["F3"]
    assert encounter.units["E1"].resource_pools["rampage_uses"] == 0

    encounter.units["F3"].max_hp = 10
    encounter.units["F3"].current_hp = 5
    second_events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F3", "weapon_id": "bite"},
        step_overrides=[AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3])],
    )

    assert not any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in second_events
    )


def test_bandit_captain_uses_pistol_at_range_and_scimitar_in_melee() -> None:
    ranged_encounter = build_monster_benchmark_encounter("bandit_captain")
    defeat_other_units(ranged_encounter, "E1", "F1")
    ranged_encounter.units["E1"].position = GridPosition(x=12, y=5)
    ranged_encounter.units["F1"].position = GridPosition(x=7, y=5)

    ranged_decision, ranged_events = run_actor_turn(ranged_encounter, "E1")
    ranged_attacks = enemy_attack_events(ranged_events)

    assert ranged_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "pistol"}
    assert [event.damage_details.weapon_id for event in ranged_attacks] == ["pistol", "pistol"]

    melee_encounter = build_monster_benchmark_encounter("bandit_captain")
    defeat_other_units(melee_encounter, "E1", "F1")
    melee_encounter.units["E1"].position = GridPosition(x=8, y=5)
    melee_encounter.units["F1"].position = GridPosition(x=7, y=5)

    melee_decision, melee_events = run_actor_turn(melee_encounter, "E1")
    melee_attacks = enemy_attack_events(melee_events)

    assert melee_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "captain_scimitar"}
    assert [event.damage_details.weapon_id for event in melee_attacks] == ["captain_scimitar", "captain_scimitar"]


def test_violet_fungus_multiattack_resolves_two_rotting_touch_attacks() -> None:
    encounter = build_monster_benchmark_encounter("violet_fungus")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "rotting_touch"}
    assert [event.damage_details.weapon_id for event in attacks] == ["rotting_touch", "rotting_touch"]


def test_polar_bear_multiattack_resolves_two_rend_attacks() -> None:
    encounter = build_monster_benchmark_encounter("polar_bear")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "rend"}
    assert [event.damage_details.weapon_id for event in attacks] == ["rend", "rend"]


def test_guard_captain_uses_javelins_at_range_and_longsword_in_melee() -> None:
    ranged_encounter = build_monster_benchmark_encounter("guard_captain")
    defeat_other_units(ranged_encounter, "E1", "F1")
    ranged_encounter.units["E1"].position = GridPosition(x=12, y=5)
    ranged_encounter.units["F1"].position = GridPosition(x=7, y=5)

    ranged_decision, ranged_events = run_actor_turn(ranged_encounter, "E1")
    ranged_attacks = enemy_attack_events(ranged_events)

    assert ranged_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "javelin_throw"}
    assert [event.damage_details.weapon_id for event in ranged_attacks] == ["javelin_throw", "javelin_throw"]

    melee_encounter = build_monster_benchmark_encounter("guard_captain")
    defeat_other_units(melee_encounter, "E1", "F1")
    melee_encounter.units["E1"].position = GridPosition(x=8, y=5)
    melee_encounter.units["F1"].position = GridPosition(x=7, y=5)

    melee_decision, melee_events = run_actor_turn(melee_encounter, "E1")
    melee_attacks = enemy_attack_events(melee_events)

    assert melee_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "longsword"}
    assert [event.damage_details.weapon_id for event in melee_attacks] == ["longsword", "longsword"]


def test_guard_captain_parry_blocks_eligible_melee_hits_but_not_ranged_hits() -> None:
    encounter = build_monster_benchmark_encounter("guard_captain")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    melee_weapon_id = next(weapon_id for weapon_id, weapon in encounter.units["F1"].attacks.items() if weapon.kind == "melee")
    hit_roll = encounter.units["E1"].ac - encounter.units["F1"].attacks[melee_weapon_id].attack_bonus

    melee_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": melee_weapon_id},
        step_overrides=[AttackRollOverrides(attack_rolls=[hit_roll], damage_rolls=[6])],
    )
    melee_attack = next(event for event in melee_events if event.event_type == "attack")

    assert melee_events[0].event_type == "phase_change"
    assert melee_events[0].resolved_totals["reaction"] == "parry"
    assert melee_attack.resolved_totals["attackReaction"] == "parry"
    assert melee_attack.resolved_totals["hit"] is False

    ranged_encounter = build_monster_benchmark_encounter("guard_captain")
    ranged_weapon_id = next(
        weapon_id for weapon_id, weapon in ranged_encounter.units["F3"].attacks.items() if weapon.kind == "ranged"
    )
    ranged_encounter.units["F3"].position = GridPosition(x=5, y=5)
    ranged_encounter.units["E1"].position = GridPosition(x=8, y=5)
    ranged_hit_roll = ranged_encounter.units["E1"].ac - ranged_encounter.units["F3"].attacks[ranged_weapon_id].attack_bonus

    ranged_events = resolve_attack_action(
        ranged_encounter,
        "F3",
        {"kind": "attack", "target_id": "E1", "weapon_id": ranged_weapon_id},
        step_overrides=[AttackRollOverrides(attack_rolls=[ranged_hit_roll], damage_rolls=[4])],
    )
    ranged_attack = next(event for event in ranged_events if event.event_type == "attack")

    assert not any(event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "parry" for event in ranged_events)
    assert ranged_attack.resolved_totals["attackReaction"] is None
    assert ranged_encounter.units["E1"].reaction_available is True


def test_goblin_boss_uses_shortbow_at_range_and_scimitar_in_melee() -> None:
    ranged_encounter = build_monster_benchmark_encounter("goblin_boss")
    defeat_other_units(ranged_encounter, "E1", "F1")
    ranged_encounter.units["E1"].position = GridPosition(x=12, y=5)
    ranged_encounter.units["F1"].position = GridPosition(x=7, y=5)

    ranged_decision, ranged_events = run_actor_turn(ranged_encounter, "E1")
    ranged_attacks = enemy_attack_events(ranged_events)

    assert ranged_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "shortbow"}
    assert [event.damage_details.weapon_id for event in ranged_attacks] == ["shortbow", "shortbow"]

    melee_encounter = build_monster_benchmark_encounter("goblin_boss")
    defeat_other_units(melee_encounter, "E1", "F1")
    melee_encounter.units["E1"].position = GridPosition(x=8, y=5)
    melee_encounter.units["F1"].position = GridPosition(x=7, y=5)

    melee_decision, melee_events = run_actor_turn(melee_encounter, "E1")
    melee_attacks = enemy_attack_events(melee_events)

    assert melee_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "scimitar"}
    assert [event.damage_details.weapon_id for event in melee_attacks] == ["scimitar", "scimitar"]


def test_bugbear_warrior_grab_applies_grapple_and_follow_up_light_hammer_gains_advantage() -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    grab_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="grab",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4]),
        ),
    )
    follow_up_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="light_hammer",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[2, 17], damage_rolls=[2, 3, 2]),
        ),
    )

    assert grab_attack.damage_details.attack_riders_applied == ["grapple_on_hit"]
    assert any(
        effect.kind == "grappled_by"
        and effect.source_id == "E1"
        and effect.maintain_reach_feet == 10
        for effect in encounter.units["F1"].temporary_effects
    )
    assert follow_up_attack.resolved_totals["attackMode"] == "advantage"
    assert "self_grappled_target" in follow_up_attack.raw_rolls["advantageSources"]

    blocked_encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(blocked_encounter, "E1", "F1")
    blocked_encounter.units["E1"].position = GridPosition(x=5, y=5)
    blocked_encounter.units["F1"].position = GridPosition(x=7, y=5)
    blocked_encounter.units["F1"].size_category = "large"

    blocked_attack, _ = resolve_attack(
        blocked_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="grab",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4]),
        ),
    )

    assert blocked_attack.damage_details.attack_riders_applied is None
    assert any(effect.kind == "grappled_by" for effect in blocked_encounter.units["F1"].temporary_effects) is False


def test_dire_wolf_bite_knocks_target_prone_on_hit() -> None:
    encounter = build_monster_benchmark_encounter("dire_wolf")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert attack.damage_details.attack_riders_applied == ["prone_on_hit"]
    assert encounter.units["F1"].conditions.prone is True


def test_worg_bite_harries_target_and_next_attack_consumes_the_effect() -> None:
    encounter = build_monster_benchmark_encounter("worg")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    first_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert first_attack.damage_details.attack_riders_applied == ["harry_target"]
    assert any(effect.kind == "harried_by" for effect in encounter.units["F1"].temporary_effects) is True

    encounter.units["E1"].attacks["bite"] = encounter.units["E1"].attacks["bite"].model_copy(
        update={"on_hit_effects": None},
        deep=True,
    )
    second_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[2, 17], damage_rolls=[4]),
        ),
    )
    third_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[17], damage_rolls=[4]),
        ),
    )

    assert second_attack.resolved_totals["attackMode"] == "advantage"
    assert "harried_target" in second_attack.raw_rolls["advantageSources"]
    assert "F1's harried defense is consumed on this attack roll." in second_attack.condition_deltas
    assert any(effect.kind == "harried_by" for effect in encounter.units["F1"].temporary_effects) is False
    assert "harried_target" not in third_attack.raw_rolls["advantageSources"]


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
    weapon_ids = [event.damage_details.weapon_id for event in attacks]

    assert weapon_ids[0] == expectation.opening_weapon_id
    assert set(weapon_ids).issubset(set(expectation.attacks))
    if expectation.melee_fallback_weapon_id in weapon_ids:
        assert weapon_ids.index(expectation.opening_weapon_id) < weapon_ids.index(expectation.melee_fallback_weapon_id)


@pytest.mark.parametrize("variant_id", RANGED_SKIRMISHER_MONSTER_IDS)
def test_ranged_skirmishers_commit_to_melee_when_pinned(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=8, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision = choose_turn_decision(encounter, "E1")

    if variant_id == "goblin_minion":
        assert decision.bonus_action == {"kind": "disengage", "timing": "before_action"}
        assert decision.pre_action_movement is not None
        assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": expectation.opening_weapon_id}
        assert encounter.units["E1"]._committed_to_melee is False
        return

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": expectation.melee_fallback_weapon_id}
    assert encounter.units["E1"]._committed_to_melee is True


@pytest.mark.parametrize("variant_id", MELEE_ONLY_MONSTER_IDS)
def test_melee_monsters_close_and_use_only_legal_attack(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    if variant_id in MULTI_SQUARE_MONSTER_IDS:
        encounter.units["E1"].position = GridPosition(x=13, y=5)
        encounter.units["F1"].position = GridPosition(x=9, y=5)
    else:
        encounter.units["E1"].position = GridPosition(x=10, y=5)
        encounter.units["F1"].position = GridPosition(x=7, y=5)

    decision, events = run_actor_turn(encounter, "E1")
    attacks = enemy_attack_events(events)

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": expectation.opening_weapon_id}
    assert decision.pre_action_movement is not None
    weapon_ids = [event.damage_details.weapon_id for event in attacks]

    assert weapon_ids[0] == expectation.opening_weapon_id
    assert set(weapon_ids).issubset(set(expectation.attacks))
    if len(expectation.attacks) == 1:
        assert all(weapon_id == expectation.opening_weapon_id for weapon_id in weapon_ids)


@pytest.mark.parametrize("variant_id", MULTI_SQUARE_MONSTER_IDS)
def test_multi_square_monsters_keep_footprint_legal_after_first_turn(variant_id: str) -> None:
    encounter = build_monster_benchmark_encounter(variant_id)
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=13, y=5)
    encounter.units["F1"].position = GridPosition(x=9, y=5)

    _, events = run_actor_turn(encounter, "E1")

    assert enemy_attack_events(events)
    assert_occupied_squares_are_valid(encounter, "E1", "F1")
