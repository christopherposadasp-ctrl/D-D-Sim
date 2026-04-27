from __future__ import annotations

import pytest

import backend.engine.combat.batch as batch_module
import backend.engine.rules.combat_rules as combat_rules_module
from backend.content.enemies import unit_has_reaction
from backend.content.feature_definitions import unit_has_granted_bonus_action
from backend.content.spell_definitions import get_spell_definition
from backend.engine import create_encounter, run_encounter, step_encounter, summarize_encounter
from backend.engine.ai.decision import MovementPlan, TurnDecision, choose_turn_decision
from backend.engine.combat.batch import resolve_batch_execution_plan
from backend.engine.combat.engine import (
    execute_decision,
    execute_movement,
    expire_turn_end_effects,
    get_opportunity_attack_weapon_id,
    get_total_movement_budget,
    maybe_resolve_great_weapon_master_hewing,
    resolve_action_surge,
    resolve_attack_action,
    resolve_bonus_action,
    resolve_bonus_action_events,
    resolve_bonus_attack_action,
    resolve_cast_spell_action,
    run_batch_parallel,
    run_batch_serial,
    run_encounter_summary_fast,
    run_single_batch_accumulator,
)
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import (
    AidEffect,
    BlessedEffect,
    ConcentrationEffect,
    DamageCandidate,
    DamageComponentResult,
    DivineFavorEffect,
    EncounterConfig,
    FrightenedEffect,
    GrappledEffect,
    GridPosition,
    HeroismEffect,
    HiddenEffect,
    NoReactionsEffect,
    PoisonedEffect,
    RageEffect,
    RecklessAttackEffect,
    RestrainedEffect,
    SlowEffect,
    WeaponRange,
)
from backend.engine.rules.combat_rules import (
    AttackRollOverrides,
    ResolveAttackArgs,
    ResolveSavingThrowArgs,
    SavingThrowOverrides,
    apply_damage,
    apply_great_weapon_fighting,
    apply_healing_to_unit,
    apply_heroism_start_of_turn,
    attempt_hide,
    attempt_lay_on_hands,
    attempt_natures_wrath,
    attempt_uncanny_metabolism,
    can_trigger_attack_reaction,
    choose_damage_candidate,
    clear_invalid_hidden_effects,
    expire_turn_effects,
    recalculate_effective_speed,
    resolve_attack,
    resolve_bless,
    resolve_death_save,
    resolve_poisoned_end_of_turn_save,
    resolve_restrained_end_of_turn_save,
    resolve_saving_throw,
)
from backend.engine.utils.rng import normalize_seed, roll_die


def build_barbarian_config(seed: str) -> EncounterConfig:
    return EncounterConfig(seed=seed, enemy_preset_id="goblin_screen", player_preset_id="barbarian_sample_trio")


def build_level2_barbarian_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="barbarian_level2_sample_trio",
        player_behavior=player_behavior,
    )


def build_level2_rogue_config(seed: str, *, player_preset_id: str = "rogue_level2_ranged_trio") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id=player_preset_id,
        player_behavior="smart",
    )


def build_level3_rogue_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="rogue_level3_ranged_assassin_trio",
        player_behavior=player_behavior,
    )


def build_level4_rogue_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="rogue_level4_ranged_assassin_trio",
        player_behavior=player_behavior,
    )


def build_level5_rogue_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="rogue_level5_ranged_assassin_trio",
        player_behavior=player_behavior,
    )


def build_monk_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="monk_sample_trio",
        player_behavior=player_behavior,
    )


def build_level2_monk_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="monk_level2_sample_trio",
        player_behavior=player_behavior,
    )


def build_paladin_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="paladin_level1_sample_trio",
        player_behavior=player_behavior,
    )


def build_level2_paladin_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="paladin_level2_sample_trio",
        player_behavior=player_behavior,
    )


def build_level3_paladin_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="paladin_level3_sample_trio",
        player_behavior=player_behavior,
    )


def build_level4_paladin_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="paladin_level4_sample_trio",
        player_behavior=player_behavior,
    )


def build_level5_paladin_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="paladin_level5_sample_trio",
        player_behavior=player_behavior,
    )


def build_wizard_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="wizard_sample_trio",
        player_behavior=player_behavior,
    )


def build_level3_wizard_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="wizard_level3_evoker_sample_trio",
        player_behavior=player_behavior,
    )


def build_level4_wizard_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="wizard_level4_evoker_sample_trio",
        player_behavior=player_behavior,
    )


def build_level3_fighter_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="fighter_level3_sample_trio",
        player_behavior=player_behavior,
    )


def build_level4_fighter_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="fighter_level4_sample_trio",
        player_behavior=player_behavior,
    )


def build_level5_fighter_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="fighter_level5_sample_trio",
        player_behavior=player_behavior,
    )


def defeat_other_enemies(encounter, *active_enemy_ids: str) -> None:
    active_ids = set(active_enemy_ids)
    for unit in encounter.units.values():
        if unit.faction != "goblins" or unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True


def build_monster_benchmark_config(seed: str, variant_id: str) -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id=f"{variant_id}_benchmark",
        player_preset_id="monster_benchmark_duo",
    )


def test_great_weapon_fighting_replaces_ones_and_twos() -> None:
    assert apply_great_weapon_fighting([1, 2, 3, 6]) == [3, 3, 3, 6]


def test_choose_damage_candidate_prefers_better_savage_roll() -> None:
    chosen, candidate = choose_damage_candidate(
        primary=DamageCandidate(raw_rolls=[1, 4], adjusted_rolls=[3, 4], subtotal=7),
        savage=DamageCandidate(raw_rolls=[6, 6], adjusted_rolls=[6, 6], subtotal=12),
    )

    assert chosen == "savage"
    assert candidate.subtotal == 12


def test_slow_penalties_cap_at_ten_feet() -> None:
    encounter = create_encounter(EncounterConfig(seed="slow-speed", placements=DEFAULT_POSITIONS))
    slowed = recalculate_effective_speed(
        encounter.units["G1"].model_copy(
            update={
                "temporary_effects": [
                    SlowEffect(kind="slow", source_id="F1", expires_at_turn_start_of="F1", penalty=10),
                    SlowEffect(kind="slow", source_id="F2", expires_at_turn_start_of="F2", penalty=10),
                ]
            },
            deep=True,
        )
    )

    assert slowed.effective_speed == 20


def test_natural_twenty_death_save_returns_fighter_to_one_hp() -> None:
    encounter = create_encounter(EncounterConfig(seed="death-save", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True

    resolve_death_save(encounter, "F1", 20)

    assert encounter.units["F1"].current_hp == 1
    assert encounter.units["F1"].conditions.unconscious is False


def test_graze_damage_removes_goblin_at_zero_hp() -> None:
    encounter = create_encounter(EncounterConfig(seed="graze-kill", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["G1"].position = GridPosition(x=6, y=5)
    encounter.units["G1"].current_hp = 3

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="G1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[2]),
        ),
    )

    assert attack.damage_details.mastery_applied == "graze"
    assert encounter.units["G1"].conditions.dead is True


def test_precision_attack_converts_a_near_miss_into_a_hit() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-precision-hit"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="precision_attack",
            overrides=AttackRollOverrides(attack_rolls=[8], damage_rolls=[4, 3], superiority_rolls=[2]),
        ),
    )

    assert attack.resolved_totals["hit"] is True
    assert attack.resolved_totals["attackTotal"] == 15
    assert attack.resolved_totals["maneuverId"] == "precision_attack"
    assert attack.raw_rolls["superiorityDiceRolls"] == [2]
    assert encounter.units["F1"].resources.superiority_dice == 3
    assert attack.damage_details.mastery_applied is None


def test_precision_attack_failure_still_allows_graze() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-precision-graze"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="precision_attack",
            overrides=AttackRollOverrides(attack_rolls=[8], superiority_rolls=[1]),
        ),
    )

    assert attack.resolved_totals["hit"] is False
    assert attack.resolved_totals["maneuverId"] == "precision_attack"
    assert attack.damage_details.mastery_applied == "graze"
    assert attack.damage_details.total_damage == 3
    assert encounter.units["F1"].resources.superiority_dice == 3


def test_smart_precision_attack_ignores_misses_wider_than_two() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-smart-precision-margin"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="precision_attack",
            precision_max_miss_margin=2,
            overrides=AttackRollOverrides(attack_rolls=[7], superiority_rolls=[3]),
        ),
    )

    assert attack.resolved_totals["hit"] is False
    assert attack.resolved_totals.get("maneuverId") is None
    assert "superiorityDiceRolls" not in attack.raw_rolls
    assert encounter.units["F1"].resources.superiority_dice == 4


def test_uncapped_auto_precision_still_uses_full_superiority_die_margin() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-dumb-precision-margin"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="battle_master_auto",
            overrides=AttackRollOverrides(attack_rolls=[7], damage_rolls=[4, 3], superiority_rolls=[3]),
        ),
    )

    assert attack.resolved_totals["hit"] is True
    assert attack.resolved_totals["maneuverId"] == "precision_attack"
    assert attack.raw_rolls["superiorityDiceRolls"] == [3]
    assert encounter.units["F1"].resources.superiority_dice == 3


def test_trip_attack_adds_damage_and_knocks_failed_save_target_prone() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-trip-prone"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[2]),
        ),
    )

    assert attack.resolved_totals["maneuverId"] == "trip_attack"
    assert attack.resolved_totals["maneuverSaveDc"] == 13
    assert attack.resolved_totals["maneuverSaveSuccess"] is False
    assert attack.resolved_totals["maneuverProneApplied"] is True
    assert attack.raw_rolls["superiorityDiceRolls"] == [5]
    assert attack.raw_rolls["maneuverSaveRolls"] == [2]
    assert encounter.units["E1"].conditions.prone is True
    assert encounter.units["F1"].resources.superiority_dice == 3
    assert any(component.total_damage == 5 for component in attack.damage_details.damage_components)


def test_trip_attack_does_not_prone_on_successful_save() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-trip-save"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[20]),
        ),
    )

    assert attack.resolved_totals["maneuverSaveSuccess"] is True
    assert attack.resolved_totals["maneuverProneApplied"] is False
    assert encounter.units["E1"].conditions.prone is False


def test_trip_attack_superiority_damage_doubles_on_critical_hits() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-trip-crit"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 50

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[20]),
        ),
    )

    superiority_component = next(component for component in attack.damage_details.damage_components if component.raw_rolls == [5])

    assert attack.resolved_totals["critical"] is True
    assert superiority_component.total_damage == 10


def test_riposte_attack_spends_superiority_die_and_adds_damage_on_hit() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-riposte-damage"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="riposte",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3], superiority_rolls=[5]),
        ),
    )

    assert attack.resolved_totals["maneuverId"] == "riposte"
    assert attack.raw_rolls["superiorityDiceRolls"] == [5]
    assert encounter.units["F1"].resources.superiority_dice == 3
    assert any(component.total_damage == 5 for component in attack.damage_details.damage_components)


def test_riposte_attack_can_use_precision_to_convert_a_tactical_near_miss() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-riposte-precision"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="riposte",
            precision_max_miss_margin=4,
            overrides=AttackRollOverrides(attack_rolls=[7], damage_rolls=[4, 3], superiority_rolls=[3, 5]),
        ),
    )

    assert attack.resolved_totals["hit"] is True
    assert attack.resolved_totals["maneuverId"] == "riposte"
    assert attack.resolved_totals["precisionManeuverId"] == "precision_attack"
    assert attack.raw_rolls["superiorityDiceRolls"] == [3, 5]
    assert encounter.units["F1"].resources.superiority_dice == 2
    assert any(component.total_damage == 5 for component in attack.damage_details.damage_components)


def test_riposte_triggers_on_missed_melee_attack_and_spends_reaction() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-riposte-trigger"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "scimitar"},
        step_overrides=[AttackRollOverrides(attack_rolls=[2])],
    )

    assert any(event.resolved_totals.get("reaction") == "riposte" for event in events)
    riposte_attack = next(event for event in events if event.actor_id == "F1" and event.event_type == "attack")
    assert riposte_attack.resolved_totals["maneuverId"] == "riposte"
    assert encounter.units["F1"].reaction_available is False
    assert encounter.units["F1"].resources.superiority_dice == 3


def test_opportunity_attack_can_use_precision_but_not_trip() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-oa-maneuvers"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    precision_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            maneuver_id="precision_attack",
            overrides=AttackRollOverrides(attack_rolls=[8], damage_rolls=[4, 3], superiority_rolls=[2]),
        ),
    )
    trip_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[2]),
        ),
    )

    assert precision_attack.resolved_totals["maneuverId"] == "precision_attack"
    assert trip_attack.resolved_totals.get("maneuverId") is None
    assert encounter.units["E1"].conditions.prone is False


def test_action_surge_after_trip_attacks_prone_target_with_advantage() -> None:
    encounter = create_encounter(build_level3_fighter_config("fighter-trip-action-surge-advantage"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[2]),
        ),
    )
    follow_up, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[3, 15], damage_rolls=[4, 3]),
        ),
    )

    assert encounter.units["E1"].conditions.prone is True
    assert follow_up.resolved_totals["attackMode"] == "advantage"
    assert "target_prone" in follow_up.raw_rolls["advantageSources"]


def test_level4_great_weapon_master_adds_proficiency_damage_on_greatsword_attack_action() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-gwm-damage"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            great_weapon_master_eligible=True,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3]),
        ),
    )

    assert attack.resolved_totals["hit"] is True
    assert attack.resolved_totals["greatWeaponMasterDamageBonus"] == 2
    assert attack.damage_details.total_damage == 13
    assert any(component.flat_modifier == 2 and component.raw_rolls == [] for component in attack.damage_details.damage_components)


def test_level4_great_weapon_master_damage_does_not_double_on_critical_hits() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-gwm-critical-flat"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            great_weapon_master_eligible=True,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[4, 3]),
        ),
    )

    great_weapon_master_component = next(
        component for component in attack.damage_details.damage_components if component.flat_modifier == 2 and component.raw_rolls == []
    )

    assert attack.resolved_totals["critical"] is True
    assert great_weapon_master_component.total_damage == 2
    assert attack.damage_details.total_damage == 20


def test_level4_great_weapon_master_does_not_apply_to_nonqualifying_attacks() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-gwm-nonqualifying"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    flail_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="flail",
            savage_attacker_available=False,
            great_weapon_master_eligible=True,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4]),
        ),
    )
    opportunity_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            great_weapon_master_eligible=True,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3]),
        ),
    )
    riposte_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="riposte",
            great_weapon_master_eligible=True,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3], superiority_rolls=[1]),
        ),
    )

    assert flail_attack.resolved_totals.get("greatWeaponMasterDamageBonus") is None
    assert opportunity_attack.resolved_totals.get("greatWeaponMasterDamageBonus") is None
    assert riposte_attack.resolved_totals.get("greatWeaponMasterDamageBonus") is None


def test_level4_trip_attack_save_dc_uses_strength_eighteen() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-level4-trip-dc"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[2]),
        ),
    )

    assert attack.resolved_totals["maneuverSaveDc"] == 14


def test_level4_great_weapon_master_hewing_triggers_after_a_critical_hit() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-gwm-hewing-crit"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[AttackRollOverrides(attack_rolls=[20], damage_rolls=[4, 3])],
    )
    hewing_events = maybe_resolve_great_weapon_master_hewing(
        encounter,
        "F1",
        attack_events,
        planned_bonus_action=None,
    )

    assert any(event.resolved_totals.get("bonusAction") == "great_weapon_master_hewing" for event in hewing_events)
    hewing_attack = next(event for event in hewing_events if event.event_type == "attack")
    assert hewing_attack.actor_id == "F1"
    assert hewing_attack.damage_details.weapon_id == "greatsword"
    assert hewing_attack.resolved_totals.get("greatWeaponMasterDamageBonus") is None
    assert encounter.units["F1"]._great_weapon_master_hewing_used_this_turn is True


def test_level4_great_weapon_master_hewing_triggers_after_dropping_a_target() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-gwm-hewing-kill"))
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=5, y=6)
    encounter.units["E1"].current_hp = 1

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3])],
    )
    hewing_events = maybe_resolve_great_weapon_master_hewing(
        encounter,
        "F1",
        attack_events,
        planned_bonus_action=None,
    )

    assert attack_events[-1].resolved_totals["targetDroppedToZero"] is True
    assert any(event.resolved_totals.get("triggerReason") == "dropped_to_zero" for event in hewing_events)
    hewing_attack = next(event for event in hewing_events if event.event_type == "attack")
    assert hewing_attack.target_ids == ["E2"]


def test_level4_great_weapon_master_hewing_respects_bonus_action_limit() -> None:
    encounter = create_encounter(build_level4_fighter_config("fighter-gwm-hewing-bonus-used"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[AttackRollOverrides(attack_rolls=[20], damage_rolls=[4, 3])],
    )
    encounter.units["F1"]._bonus_action_used_this_turn = True

    assert (
        maybe_resolve_great_weapon_master_hewing(
            encounter,
            "F1",
            attack_events,
            planned_bonus_action=None,
        )
        == []
    )


def test_level5_attack_action_resolves_two_attacks() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-extra-attack"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 100

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3]),
            AttackRollOverrides(attack_rolls=[13], damage_rolls=[5, 3]),
        ],
    )

    attacks = [event for event in attack_events if event.event_type == "attack" and event.actor_id == "F1"]
    assert len(attacks) == 2
    assert [event.damage_details.weapon_id for event in attacks] == ["greatsword", "greatsword"]


def test_level5_action_surge_resolves_two_more_attack_action_attacks() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-action-surge-attacks"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 100

    first_action = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3]),
            AttackRollOverrides(attack_rolls=[13], damage_rolls=[5, 3]),
        ],
    )
    surge_event = resolve_action_surge(encounter, "F1")
    second_action = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[14], damage_rolls=[4, 3]),
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[5, 3]),
        ],
    )

    attacks = [event for event in first_action + second_action if event.event_type == "attack" and event.actor_id == "F1"]
    assert surge_event.event_type == "phase_change"
    assert encounter.units["F1"].resources.action_surge_uses == 0
    assert len(attacks) == 4


def test_level5_extra_attack_retargets_after_dropping_first_target() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-extra-attack-retarget"))
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=5, y=6)
    encounter.units["E1"].current_hp = 1
    encounter.units["E2"].current_hp = 100

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3]),
            AttackRollOverrides(attack_rolls=[13], damage_rolls=[5, 3]),
        ],
    )

    attacks = [event for event in attack_events if event.event_type == "attack" and event.actor_id == "F1"]
    assert attacks[0].target_ids == ["E1"]
    assert attacks[0].resolved_totals["targetDroppedToZero"] is True
    assert attacks[1].target_ids == ["E2"]


def test_level5_great_weapon_master_uses_proficiency_three_damage_bonus() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-gwm-damage"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            great_weapon_master_eligible=True,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3]),
        ),
    )

    assert attack.resolved_totals["greatWeaponMasterDamageBonus"] == 3
    assert attack.damage_details.total_damage == 14
    assert any(component.flat_modifier == 3 and component.raw_rolls == [] for component in attack.damage_details.damage_components)


def test_level5_trip_attack_save_dc_uses_proficiency_three() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-trip-dc"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greatsword",
            savage_attacker_available=False,
            maneuver_id="trip_attack",
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4, 3], superiority_rolls=[5], save_rolls=[2]),
        ),
    )

    assert attack.resolved_totals["maneuverSaveDc"] == 15


def test_level5_tactical_shift_movement_does_not_provoke_and_is_capped() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-tactical-shift"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].current_hp = 10
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            bonus_action={"kind": "second_wind", "timing": "before_action"},
            action={"kind": "skip", "reason": "Testing Tactical Shift."},
            post_action_movement=MovementPlan(
                path=[GridPosition(x=5, y=5), GridPosition(x=5, y=4), GridPosition(x=5, y=3), GridPosition(x=5, y=2)],
                mode="tactical_shift",
            ),
        ),
        events,
        rescue_mode=False,
    )

    move_event = next(event for event in events if event.event_type == "move")
    assert move_event.resolved_totals["tacticalShiftApplied"] is True
    assert move_event.resolved_totals["opportunityAttackers"] == []
    assert encounter.units["E1"].reaction_available is True

    too_far_events: list = []
    execute_decision(
        create_encounter(build_level5_fighter_config("fighter-level5-tactical-shift-cap")),
        "F1",
        TurnDecision(
            bonus_action={"kind": "second_wind", "timing": "before_action"},
            action={"kind": "skip", "reason": "Testing Tactical Shift cap."},
            post_action_movement=MovementPlan(
                path=[
                    GridPosition(x=1, y=1),
                    GridPosition(x=2, y=1),
                    GridPosition(x=3, y=1),
                    GridPosition(x=4, y=1),
                    GridPosition(x=5, y=1),
                ],
                mode="tactical_shift",
            ),
        ),
        too_far_events,
        rescue_mode=False,
    )

    assert too_far_events[0].event_type == "skip"
    assert too_far_events[0].text_summary == "F1 skips its turn: Planned movement exceeds the unit speed budget."


def test_second_wind_does_not_protect_unrelated_normal_movement() -> None:
    encounter = create_encounter(build_level5_fighter_config("fighter-level5-second-wind-normal-move"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].current_hp = 10
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            bonus_action={"kind": "second_wind", "timing": "before_action"},
            pre_action_movement=MovementPlan(
                path=[GridPosition(x=5, y=5), GridPosition(x=5, y=4), GridPosition(x=5, y=3)],
                mode="move",
            ),
            action={"kind": "skip", "reason": "Testing normal movement."},
        ),
        events,
        rescue_mode=False,
    )

    move_event = next(event for event in events if event.event_type == "move")
    assert move_event.resolved_totals["tacticalShiftApplied"] is False
    assert move_event.resolved_totals["opportunityAttackers"] == ["E1"]
    assert encounter.units["E1"].reaction_available is False


def test_barbarian_unarmored_defense_uses_dex_plus_con() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-unarmored-defense"))

    assert encounter.units["F1"].ac == 14


def test_fire_bolt_uses_attack_roll_logic_and_applies_cover() -> None:
    encounter = create_encounter(build_wizard_config("wizard-fire-bolt-cover"))
    defeat_other_enemies(encounter, "E4")
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "E4"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[6]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "fire_bolt"
    assert attack_event.resolved_totals["coverAcBonus"] == 2
    assert attack_event.resolved_totals["attackMode"] == "normal"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.damage_details.total_damage == 6


def test_fire_bolt_picks_up_adjacent_enemy_disadvantage() -> None:
    encounter = create_encounter(build_wizard_config("wizard-fire-bolt-adjacent"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[4, 17], damage_rolls=[6]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["attackMode"] == "disadvantage"
    assert "adjacent_enemy" in attack_event.raw_rolls["disadvantageSources"]
    assert attack_event.resolved_totals["selectedRoll"] == 4


def test_evoker_potent_cantrip_fire_bolt_miss_deals_minimum_one_damage() -> None:
    encounter = create_encounter(build_level3_wizard_config("wizard-potent-fire-bolt-minimum"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[1]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "fire_bolt"
    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals["potentCantripApplied"] is True
    assert attack_event.resolved_totals["potentCantripDamage"] == 1
    assert attack_event.damage_details.total_damage == 1
    assert attack_event.damage_details.final_damage_to_hp == 1


def test_evoker_potent_cantrip_shocking_grasp_miss_deals_damage_without_no_reactions_rider() -> None:
    encounter = create_encounter(build_level3_wizard_config("wizard-potent-shocking-grasp-no-rider"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "shocking_grasp"
    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals["potentCantripApplied"] is True
    assert attack_event.resolved_totals["potentCantripDamage"] == 2
    assert attack_event.damage_details.total_damage == 2
    assert all(effect.kind != "no_reactions" for effect in encounter.units["E1"].temporary_effects)


def test_level4_evoker_fire_bolt_uses_int_asi_spell_attack_bonus() -> None:
    encounter = create_encounter(build_level4_wizard_config("wizard-level4-fire-bolt-attack-bonus"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[9], damage_rolls=[6]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "fire_bolt"
    assert attack_event.resolved_totals["selectedRoll"] == 9
    assert attack_event.resolved_totals["attackTotal"] == 15
    assert attack_event.resolved_totals["hit"] is True


def test_magic_missile_auto_hits_and_spends_a_level1_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-magic-missile"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=8, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "magic_missile", "target_id": "E1"},
        overrides=AttackRollOverrides(damage_rolls=[1, 2, 3]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "magic_missile"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.raw_rolls["damageRolls"] == [1, 2, 3]
    assert attack_event.damage_details.total_damage == 9
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1


def test_magic_missile_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_wizard_config("wizard-magic-missile-empty"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "magic_missile", "target_id": "E1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary


def test_level2_wizard_has_third_level1_slot_for_leveled_spells() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level2-third-slot",
            enemy_preset_id="goblin_screen",
            player_preset_id="wizard_level2_sample_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=8, y=5)
    encounter.units["E1"].max_hp = 50
    encounter.units["E1"].current_hp = 50

    for _ in range(3):
        spell_events = resolve_cast_spell_action(
            encounter,
            "F1",
            {"kind": "cast_spell", "spell_id": "magic_missile", "target_id": "E1"},
            overrides=AttackRollOverrides(damage_rolls=[1, 1, 1]),
        )
        assert any(event.event_type == "attack" for event in spell_events)

    assert encounter.units["F1"].resources.spell_slots_level_1 == 0


def test_chromatic_orb_hits_with_selected_damage_type_and_spends_slot() -> None:
    spell = get_spell_definition("chromatic_orb")
    encounter = create_encounter(build_wizard_config("wizard-chromatic-orb"))
    prepare_chromatic_orb_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chromatic_orb", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4, 5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert spell.level == 1
    assert spell.school == "evocation"
    assert spell.range_feet == 90
    assert spell.damage_dice[0].count == 3
    assert spell.damage_dice[0].sides == 8
    assert spell.selectable_damage_types == ("acid", "cold", "fire", "lightning", "poison", "thunder")
    assert attack_event.resolved_totals["spellId"] == "chromatic_orb"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["selectedDamageType"] == "acid"
    assert attack_event.resolved_totals["selectableDamageTypes"] == list(spell.selectable_damage_types)
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert attack_event.raw_rolls["attackRolls"] == [15]
    assert attack_event.damage_details.damage_components[0].raw_rolls == [3, 4, 5]
    assert attack_event.damage_details.damage_components[0].damage_type == "acid"
    assert attack_event.damage_details.total_damage == 12
    assert "Chromatic Orb" in attack_event.text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_chromatic_orb_selects_vulnerable_damage_type_when_available() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chromatic-orb-vulnerable"))
    prepare_chromatic_orb_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    encounter.units["E1"].damage_vulnerabilities = ("fire",)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chromatic_orb", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4, 5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["selectedDamageType"] == "fire"
    assert attack_event.damage_details.damage_components[0].damage_type == "fire"
    assert attack_event.damage_details.total_damage == 12
    assert attack_event.damage_details.amplified_damage == 12
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1


def test_chromatic_orb_miss_spends_slot_without_damage() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chromatic-orb-miss"))
    prepare_chromatic_orb_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    hp_before = encounter.units["E1"].current_hp

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chromatic_orb", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[3, 4, 5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert attack_event.resolved_totals["selectedDamageType"] == "acid"
    assert attack_event.damage_details.total_damage == 0
    assert attack_event.damage_details.damage_components == []
    assert encounter.units["E1"].current_hp == hp_before
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_chromatic_orb_requires_prepared_spell_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chromatic-orb-unprepared"))
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chromatic_orb", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Chromatic Orb: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_chromatic_orb_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chromatic-orb-empty"))
    prepare_chromatic_orb_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chromatic_orb", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 0


def test_chromatic_orb_out_of_range_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chromatic-orb-range"))
    prepare_chromatic_orb_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["E1"].position = GridPosition(x=19, y=0)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chromatic_orb", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Chromatic Orb: is not in range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_ray_of_sickness_hits_for_poison_damage_failed_save_poisons_and_spends_slot() -> None:
    spell = get_spell_definition("ray_of_sickness")
    encounter = create_encounter(build_wizard_config("wizard-ray-of-sickness"))
    prepare_ray_of_sickness_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    encounter.units["E1"].max_hp = 20
    encounter.units["E1"].current_hp = 20

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_sickness", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2, 3], save_rolls=[1]),
    )
    assert [event.event_type for event in spell_events] == ["attack", "saving_throw"]
    attack_event, save_event = spell_events

    assert spell.level == 1
    assert spell.school == "necromancy"
    assert spell.range_feet == 60
    assert spell.damage_dice[0].count == 2
    assert spell.damage_dice[0].sides == 8
    assert spell.damage_type == "poison"
    assert spell.save_ability == "con"
    assert attack_event.resolved_totals["spellId"] == "ray_of_sickness"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert attack_event.raw_rolls["attackRolls"] == [15]
    assert attack_event.damage_details.total_damage == 5
    assert attack_event.damage_details.damage_components[0].damage_type == "poison"
    assert "Ray of Sickness" in attack_event.text_summary
    assert save_event.resolved_totals["spellId"] == "ray_of_sickness"
    assert save_event.resolved_totals["ability"] == "con"
    assert save_event.resolved_totals["success"] is False
    assert save_event.raw_rolls["savingThrowRolls"] == [1]
    assert save_event.resolved_totals["poisonedApplied"] is True
    assert save_event.resolved_totals["poisonedExpiresAtTurnEndOf"] == "F1"
    assert save_event.resolved_totals["poisonedExpiresAtRound"] == encounter.round + 1
    assert save_event.resolved_totals["poisonedDurationRounds"] == 1
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1
    assert any(effect.kind == "poisoned" for effect in encounter.units["E1"].temporary_effects)

    assert expire_turn_end_effects(encounter, "F1") == []
    encounter.round += 1
    expire_events = expire_turn_end_effects(encounter, "F1")

    assert any(event.event_type == "phase_change" for event in expire_events)
    assert all(effect.kind != "poisoned" for effect in encounter.units["E1"].temporary_effects)


def test_ray_of_sickness_successful_con_save_deals_damage_without_poisoning() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-sickness-save"))
    prepare_ray_of_sickness_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    encounter.units["E1"].max_hp = 20
    encounter.units["E1"].current_hp = 20

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_sickness", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2, 3], save_rolls=[20]),
    )
    assert [event.event_type for event in spell_events] == ["attack", "saving_throw"]
    attack_event, save_event = spell_events

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.damage_details.total_damage == 5
    assert save_event.resolved_totals["spellId"] == "ray_of_sickness"
    assert save_event.resolved_totals["success"] is True
    assert save_event.resolved_totals["poisonedApplied"] is False
    assert save_event.resolved_totals["poisonedSkipReason"] == "save_succeeded"
    assert all(effect.kind != "poisoned" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_ray_of_sickness_miss_spends_slot_without_damage_or_poison_save() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-sickness-miss"))
    prepare_ray_of_sickness_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    hp_before = encounter.units["E1"].current_hp

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_sickness", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[8, 8], save_rolls=[1]),
    )
    assert [event.event_type for event in spell_events] == ["attack"]
    attack_event = spell_events[0]

    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "savingThrowRolls" not in attack_event.raw_rolls
    assert "poisonedApplied" not in attack_event.resolved_totals
    assert attack_event.damage_details.total_damage == 0
    assert encounter.units["E1"].current_hp == hp_before
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_ray_of_sickness_poison_immune_target_takes_hit_damage_without_poison_save() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-sickness-immune"))
    prepare_ray_of_sickness_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    encounter.units["E1"].condition_immunities = ("poisoned",)
    encounter.units["E1"].max_hp = 20
    encounter.units["E1"].current_hp = 20

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_sickness", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2, 3], save_rolls=[1]),
    )

    assert [event.event_type for event in spell_events] == ["attack"]
    assert spell_events[0].damage_details.total_damage == 5
    assert all(effect.kind != "poisoned" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_ray_of_sickness_requires_prepared_spell_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-sickness-unprepared"))
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_sickness", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2, 3], save_rolls=[1]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Ray of Sickness: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_ray_of_sickness_out_of_range_does_not_spend_slot_or_roll_save() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-sickness-range"))
    prepare_ray_of_sickness_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["E1"].position = GridPosition(x=13, y=0)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_sickness", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2, 3], save_rolls=[1]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Ray of Sickness: is not in range" in spell_events[0].text_summary
    assert spell_events[0].raw_rolls == {}
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_mage_armor_raises_ac_spends_slot_and_logs_event() -> None:
    encounter = create_encounter(build_wizard_config("wizard-mage-armor"))

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "mage_armor", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    mage_armor_event = spell_events[0]
    assert mage_armor_event.event_type == "phase_change"
    assert mage_armor_event.resolved_totals["spellId"] == "mage_armor"
    assert mage_armor_event.resolved_totals["previousAc"] == 12
    assert mage_armor_event.resolved_totals["mageArmorAc"] == 15
    assert mage_armor_event.resolved_totals["newAc"] == 15
    assert mage_armor_event.resolved_totals["acChanged"] is True
    assert mage_armor_event.resolved_totals["durationRounds"] == 4800
    assert mage_armor_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "Mage Armor" in mage_armor_event.text_summary
    assert encounter.units["F1"].ac == 15
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_mage_armor_does_not_lower_existing_ac() -> None:
    encounter = create_encounter(build_wizard_config("wizard-mage-armor-no-lower"))
    encounter.units["F1"].ac = 16

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "mage_armor", "target_id": "F1"},
    )
    mage_armor_event = spell_events[0]

    assert encounter.units["F1"].ac == 16
    assert mage_armor_event.resolved_totals["previousAc"] == 16
    assert mage_armor_event.resolved_totals["mageArmorAc"] == 15
    assert mage_armor_event.resolved_totals["newAc"] == 16
    assert mage_armor_event.resolved_totals["acChanged"] is False
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_mage_armor_is_self_only_and_does_not_spend_slot_on_invalid_target() -> None:
    encounter = create_encounter(build_wizard_config("wizard-mage-armor-self-only"))

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "mage_armor", "target_id": "F2"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "can only target self" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert encounter.units["F2"].ac == 12


def prepare_false_life_test_wizard(encounter) -> None:
    if "false_life" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("false_life")


def prepare_longstrider_test_wizard(encounter) -> None:
    if "longstrider" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("longstrider")


def prepare_ray_of_frost_test_wizard(encounter) -> None:
    if "ray_of_frost" not in encounter.units["F1"].combat_cantrip_ids:
        encounter.units["F1"].combat_cantrip_ids.append("ray_of_frost")


def prepare_chill_touch_test_wizard(encounter) -> None:
    if "chill_touch" not in encounter.units["F1"].combat_cantrip_ids:
        encounter.units["F1"].combat_cantrip_ids.append("chill_touch")


def prepare_poison_spray_test_wizard(encounter) -> None:
    if "poison_spray" not in encounter.units["F1"].combat_cantrip_ids:
        encounter.units["F1"].combat_cantrip_ids.append("poison_spray")


def prepare_acid_splash_test_wizard(encounter) -> None:
    if "acid_splash" not in encounter.units["F1"].combat_cantrip_ids:
        encounter.units["F1"].combat_cantrip_ids.append("acid_splash")


def prepare_chromatic_orb_test_wizard(encounter) -> None:
    if "chromatic_orb" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("chromatic_orb")


def prepare_ray_of_sickness_test_wizard(encounter) -> None:
    if "ray_of_sickness" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("ray_of_sickness")


def prepare_shatter_test_wizard(encounter) -> None:
    if "shatter" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("shatter")
    encounter.units["F1"].resources.spell_slots_level_2 = 1


def test_false_life_grants_temporary_hp_spends_slot_and_logs_event() -> None:
    spell = get_spell_definition("false_life")
    encounter = create_encounter(build_wizard_config("wizard-false-life"))
    prepare_false_life_test_wizard(encounter)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "false_life", "target_id": "F1"},
        overrides=AttackRollOverrides(damage_rolls=[4, 3]),
    )

    assert spell.level == 1
    assert spell.school == "necromancy"
    assert len(spell_events) == 1
    false_life_event = spell_events[0]
    assert false_life_event.event_type == "phase_change"
    assert false_life_event.raw_rolls["temporaryHitPointRolls"] == [4, 3]
    assert false_life_event.resolved_totals["spellId"] == "false_life"
    assert false_life_event.resolved_totals["temporaryHitPointModifier"] == 4
    assert false_life_event.resolved_totals["temporaryHitPointTotal"] == 11
    assert false_life_event.resolved_totals["previousTemporaryHitPoints"] == 0
    assert false_life_event.resolved_totals["temporaryHitPointsGained"] == 11
    assert false_life_event.resolved_totals["newTemporaryHitPoints"] == 11
    assert false_life_event.resolved_totals["durationRounds"] == 600
    assert false_life_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "False Life" in false_life_event.text_summary
    assert encounter.units["F1"].temporary_hit_points == 11
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_false_life_does_not_replace_higher_temporary_hp() -> None:
    encounter = create_encounter(build_wizard_config("wizard-false-life-no-replace"))
    prepare_false_life_test_wizard(encounter)
    encounter.units["F1"].temporary_hit_points = 12

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "false_life", "target_id": "F1"},
        overrides=AttackRollOverrides(damage_rolls=[1, 1]),
    )
    false_life_event = spell_events[0]

    assert false_life_event.resolved_totals["temporaryHitPointTotal"] == 6
    assert false_life_event.resolved_totals["previousTemporaryHitPoints"] == 12
    assert false_life_event.resolved_totals["temporaryHitPointsGained"] == 0
    assert false_life_event.resolved_totals["newTemporaryHitPoints"] == 12
    assert encounter.units["F1"].temporary_hit_points == 12
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_false_life_is_self_only_and_does_not_spend_slot_on_invalid_target() -> None:
    encounter = create_encounter(build_wizard_config("wizard-false-life-self-only"))
    prepare_false_life_test_wizard(encounter)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "false_life", "target_id": "F2"},
        overrides=AttackRollOverrides(damage_rolls=[4, 4]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "can only target self" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert encounter.units["F1"].temporary_hit_points == 0
    assert encounter.units["F2"].temporary_hit_points == 0


def test_false_life_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_wizard_config("wizard-false-life-empty"))
    prepare_false_life_test_wizard(encounter)
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "false_life", "target_id": "F1"},
        overrides=AttackRollOverrides(damage_rolls=[4, 4]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary
    assert encounter.units["F1"].temporary_hit_points == 0


def test_longstrider_increases_speed_spends_slot_and_logs_event() -> None:
    spell = get_spell_definition("longstrider")
    encounter = create_encounter(build_wizard_config("wizard-longstrider"))
    prepare_longstrider_test_wizard(encounter)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "longstrider", "target_id": "F1"},
    )

    assert spell.level == 1
    assert spell.school == "transmutation"
    assert spell.range_feet == 5
    assert spell.speed_bonus == 10
    assert len(spell_events) == 1
    longstrider_event = spell_events[0]
    assert longstrider_event.event_type == "phase_change"
    assert longstrider_event.resolved_totals["spellId"] == "longstrider"
    assert longstrider_event.resolved_totals["spellLevel"] == 1
    assert longstrider_event.resolved_totals["speedBonus"] == 10
    assert longstrider_event.resolved_totals["previousSpeedBonus"] == 0
    assert longstrider_event.resolved_totals["newSpeedBonus"] == 10
    assert longstrider_event.resolved_totals["previousEffectiveSpeed"] == 30
    assert longstrider_event.resolved_totals["newEffectiveSpeed"] == 40
    assert longstrider_event.resolved_totals["speedChanged"] is True
    assert longstrider_event.resolved_totals["durationRounds"] == 600
    assert longstrider_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "Longstrider" in longstrider_event.text_summary
    assert encounter.units["F1"].longstrider_speed_bonus == 10
    assert encounter.units["F1"].effective_speed == 40
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_longstrider_does_not_stack_existing_bonus() -> None:
    encounter = create_encounter(build_wizard_config("wizard-longstrider-no-stack"))
    prepare_longstrider_test_wizard(encounter)
    encounter.units["F1"].longstrider_speed_bonus = 10
    encounter.units["F1"].effective_speed = 40

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "longstrider", "target_id": "F1"},
    )
    longstrider_event = spell_events[0]

    assert longstrider_event.resolved_totals["previousSpeedBonus"] == 10
    assert longstrider_event.resolved_totals["newSpeedBonus"] == 10
    assert longstrider_event.resolved_totals["previousEffectiveSpeed"] == 40
    assert longstrider_event.resolved_totals["newEffectiveSpeed"] == 40
    assert longstrider_event.resolved_totals["speedChanged"] is False
    assert encounter.units["F1"].longstrider_speed_bonus == 10
    assert encounter.units["F1"].effective_speed == 40
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_longstrider_can_target_touch_range_ally() -> None:
    encounter = create_encounter(build_wizard_config("wizard-longstrider-ally"))
    prepare_longstrider_test_wizard(encounter)
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "longstrider", "target_id": "F2"},
    )
    longstrider_event = spell_events[0]

    assert longstrider_event.event_type == "phase_change"
    assert longstrider_event.resolved_totals["spellId"] == "longstrider"
    assert encounter.units["F2"].longstrider_speed_bonus == 10
    assert encounter.units["F2"].effective_speed == 40
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_longstrider_rejects_enemy_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-longstrider-enemy"))
    prepare_longstrider_test_wizard(encounter)
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "longstrider", "target_id": "E1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "target is not a living ally" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert encounter.units["E1"].longstrider_speed_bonus == 0


def test_longstrider_requires_touch_range_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-longstrider-range"))
    prepare_longstrider_test_wizard(encounter)
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=8, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "longstrider", "target_id": "F2"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "target is not within touch range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert encounter.units["F2"].longstrider_speed_bonus == 0


def test_longstrider_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_wizard_config("wizard-longstrider-empty"))
    prepare_longstrider_test_wizard(encounter)
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "longstrider", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary
    assert encounter.units["F1"].longstrider_speed_bonus == 0
    assert encounter.units["F1"].effective_speed == 30


def test_shocking_grasp_is_a_melee_spell_attack_and_applies_no_reactions() -> None:
    encounter = create_encounter(build_wizard_config("wizard-shocking-grasp-hit"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "shocking_grasp"
    assert attack_event.resolved_totals["attackMode"] == "normal"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.damage_details.total_damage == 5
    assert any(effect.kind == "no_reactions" for effect in encounter.units["E1"].temporary_effects)


def test_ray_of_frost_deals_cold_damage_and_slows_on_hit() -> None:
    spell = get_spell_definition("ray_of_frost")
    encounter = create_encounter(build_wizard_config("wizard-ray-of-frost"))
    prepare_ray_of_frost_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_frost", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert spell.level == 0
    assert spell.school == "evocation"
    assert spell.damage_type == "cold"
    assert spell.range_feet == 60
    assert spell.speed_penalty == 10
    assert attack_event.resolved_totals["spellId"] == "ray_of_frost"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["slowApplied"] is True
    assert attack_event.resolved_totals["speedPenalty"] == 10
    assert attack_event.resolved_totals["previousEffectiveSpeed"] == 30
    assert attack_event.resolved_totals["newEffectiveSpeed"] == 20
    assert attack_event.resolved_totals["slowExpiresAtTurnStartOf"] == "F1"
    assert attack_event.damage_details.total_damage == 5
    assert attack_event.damage_details.damage_components[0].damage_type == "cold"
    assert "Ray of Frost" in attack_event.text_summary
    assert any(effect.kind == "slow" and effect.source_id == "F1" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["E1"].effective_speed == 20
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_ray_of_frost_miss_does_not_slow_or_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-frost-miss"))
    prepare_ray_of_frost_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_frost", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[2], damage_rolls=[5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "ray_of_frost"
    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals.get("slowApplied") is None
    assert all(effect.kind != "slow" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["E1"].effective_speed == 30
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_ray_of_frost_requires_known_cantrip_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-frost-unprepared"))
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_frost", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Ray of Frost: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "slow" for effect in encounter.units["E1"].temporary_effects)


def test_ray_of_frost_out_of_range_does_not_slow_or_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-frost-range"))
    prepare_ray_of_frost_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["E1"].position = GridPosition(x=13, y=0)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_frost", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Ray of Frost: is not in range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "slow" for effect in encounter.units["E1"].temporary_effects)


def test_ray_of_frost_slow_expires_at_caster_turn_start() -> None:
    encounter = create_encounter(build_wizard_config("wizard-ray-of-frost-expire"))
    prepare_ray_of_frost_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)

    resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "ray_of_frost", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )

    expire_turn_effects(encounter, "F1")

    assert all(effect.kind != "slow" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["E1"].effective_speed == 30


def test_chill_touch_deals_necrotic_damage_blocks_healing_and_spends_no_slot() -> None:
    spell = get_spell_definition("chill_touch")
    encounter = create_encounter(build_wizard_config("wizard-chill-touch"))
    prepare_chill_touch_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chill_touch", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert spell.level == 0
    assert spell.school == "necromancy"
    assert spell.damage_type == "necrotic"
    assert spell.range_feet == 120
    assert attack_event.resolved_totals["spellId"] == "chill_touch"
    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["healingBlockedApplied"] is True
    assert attack_event.resolved_totals["healingBlockedExpiresAtTurnStartOf"] == "F1"
    assert attack_event.resolved_totals["undeadAttackDisadvantageModeled"] is False
    assert attack_event.damage_details.total_damage == 5
    assert attack_event.damage_details.damage_components[0].damage_type == "necrotic"
    assert "Chill Touch" in attack_event.text_summary
    assert any(effect.kind == "healing_blocked" and effect.source_id == "F1" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2

    encounter.units["E1"].current_hp = max(1, encounter.units["E1"].current_hp - 2)
    hp_before_healing = encounter.units["E1"].current_hp
    healed, condition_deltas = apply_healing_to_unit(encounter.units["E1"], 5)

    assert healed == 0
    assert encounter.units["E1"].current_hp == hp_before_healing
    assert condition_deltas == ["E1 cannot regain HP until the start of the caster's next turn."]


def test_chill_touch_miss_does_not_block_healing_or_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chill-touch-miss"))
    prepare_chill_touch_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chill_touch", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[2], damage_rolls=[5]),
    )
    attack_event = next(event for event in spell_events if event.event_type == "attack")

    assert attack_event.resolved_totals["spellId"] == "chill_touch"
    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals.get("healingBlockedApplied") is None
    assert all(effect.kind != "healing_blocked" for effect in encounter.units["E1"].temporary_effects)
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_chill_touch_requires_known_cantrip_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chill-touch-unprepared"))
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chill_touch", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Chill Touch: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "healing_blocked" for effect in encounter.units["E1"].temporary_effects)


def test_chill_touch_out_of_range_does_not_block_healing_or_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chill-touch-range"))
    prepare_chill_touch_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["E1"].position = GridPosition(x=25, y=0)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chill_touch", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Chill Touch: is not in range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "healing_blocked" for effect in encounter.units["E1"].temporary_effects)


def test_chill_touch_healing_block_expires_at_caster_turn_start() -> None:
    encounter = create_encounter(build_wizard_config("wizard-chill-touch-expire"))
    prepare_chill_touch_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "chill_touch", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )

    expire_turn_effects(encounter, "F1")

    assert all(effect.kind != "healing_blocked" for effect in encounter.units["E1"].temporary_effects)


def test_poison_spray_failed_con_save_deals_poison_damage_and_spends_no_slot() -> None:
    spell = get_spell_definition("poison_spray")
    encounter = create_encounter(build_wizard_config("wizard-poison-spray"))
    prepare_poison_spray_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "poison_spray", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[9]),
    )

    assert spell.level == 0
    assert spell.school == "necromancy"
    assert spell.save_ability == "con"
    assert spell.damage_type == "poison"
    assert spell.range_feet == 30
    assert [event.event_type for event in spell_events] == ["saving_throw", "attack"]
    save_event, damage_event = spell_events
    assert save_event.resolved_totals["ability"] == "con"
    assert save_event.resolved_totals["success"] is False
    assert damage_event.resolved_totals["spellId"] == "poison_spray"
    assert damage_event.resolved_totals["saveAbility"] == "con"
    assert damage_event.resolved_totals["saveSucceeded"] is False
    assert damage_event.resolved_totals["fullDamage"] == 9
    assert damage_event.resolved_totals["damageApplied"] == 9
    assert damage_event.raw_rolls["damageRolls"] == [9]
    assert damage_event.damage_details.total_damage == 9
    assert damage_event.damage_details.damage_components[0].damage_type == "poison"
    assert "Poison Spray" in damage_event.text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_poison_spray_successful_con_save_deals_no_damage_and_spends_no_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-poison-spray-save"))
    prepare_poison_spray_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)
    hp_before = encounter.units["E1"].current_hp

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "poison_spray", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[20], damage_rolls=[9]),
    )
    save_event, damage_event = spell_events

    assert save_event.resolved_totals["success"] is True
    assert damage_event.resolved_totals["saveSucceeded"] is True
    assert damage_event.resolved_totals["fullDamage"] == 9
    assert damage_event.resolved_totals["damageApplied"] == 0
    assert damage_event.damage_details.total_damage == 0
    assert encounter.units["E1"].current_hp == hp_before
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_poison_spray_requires_known_cantrip_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-poison-spray-unprepared"))
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "poison_spray", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[9]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Poison Spray: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_poison_spray_out_of_range_does_not_roll_or_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-poison-spray-range"))
    prepare_poison_spray_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["E1"].position = GridPosition(x=7, y=0)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "poison_spray", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[9]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Poison Spray: is not in range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_acid_splash_failed_dex_save_deals_acid_damage_and_spends_no_slot() -> None:
    spell = get_spell_definition("acid_splash")
    encounter = create_encounter(build_wizard_config("wizard-acid-splash"))
    prepare_acid_splash_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=12, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "acid_splash", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[6]),
    )

    assert spell.level == 0
    assert spell.school == "evocation"
    assert spell.save_ability == "dex"
    assert spell.damage_type == "acid"
    assert spell.range_feet == 60
    assert spell.max_targets == 2
    assert [event.event_type for event in spell_events] == ["saving_throw", "attack"]
    save_event, damage_event = spell_events
    assert save_event.resolved_totals["ability"] == "dex"
    assert save_event.resolved_totals["success"] is False
    assert damage_event.resolved_totals["spellId"] == "acid_splash"
    assert damage_event.resolved_totals["saveAbility"] == "dex"
    assert damage_event.resolved_totals["saveSucceeded"] is False
    assert damage_event.resolved_totals["fullDamage"] == 6
    assert damage_event.resolved_totals["damageApplied"] == 6
    assert damage_event.resolved_totals["targetCount"] == 1
    assert damage_event.raw_rolls["damageRolls"] == [6]
    assert damage_event.damage_details.total_damage == 6
    assert damage_event.damage_details.damage_components[0].damage_type == "acid"
    assert "Acid Splash" in damage_event.text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_acid_splash_successful_dex_save_deals_no_damage_and_spends_no_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-acid-splash-save"))
    prepare_acid_splash_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=12, y=5)
    hp_before = encounter.units["E1"].current_hp

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "acid_splash", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[20], damage_rolls=[6]),
    )
    save_event, damage_event = spell_events

    assert save_event.resolved_totals["success"] is True
    assert damage_event.resolved_totals["saveSucceeded"] is True
    assert damage_event.resolved_totals["fullDamage"] == 6
    assert damage_event.resolved_totals["damageApplied"] == 0
    assert damage_event.damage_details.total_damage == 0
    assert encounter.units["E1"].current_hp == hp_before
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_acid_splash_can_target_two_nearby_creatures() -> None:
    encounter = create_encounter(build_wizard_config("wizard-acid-splash-two-targets"))
    prepare_acid_splash_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=11, y=5)
    encounter.units["E2"].position = GridPosition(x=12, y=5)
    e2_hp_before = encounter.units["E2"].current_hp

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {
            "kind": "cast_spell",
            "spell_id": "acid_splash",
            "target_id": "E1",
            "target_ids": ["E1", "E2"],
        },
        overrides=AttackRollOverrides(save_rolls=[1, 20], damage_rolls=[4]),
    )

    assert [event.event_type for event in spell_events] == [
        "phase_change",
        "saving_throw",
        "attack",
        "saving_throw",
        "attack",
    ]
    phase_event = spell_events[0]
    first_attack = spell_events[2]
    second_attack = spell_events[4]
    assert phase_event.resolved_totals["spellId"] == "acid_splash"
    assert phase_event.resolved_totals["targetCount"] == 2
    assert first_attack.target_ids == ["E1"]
    assert first_attack.resolved_totals["damageApplied"] == 4
    assert first_attack.raw_rolls["damageRolls"] == [4]
    assert second_attack.target_ids == ["E2"]
    assert second_attack.resolved_totals["damageApplied"] == 0
    assert second_attack.raw_rolls["damageRolls"] == [4]
    assert encounter.units["E2"].current_hp == e2_hp_before
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_acid_splash_rejects_non_nearby_second_target_without_spending_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-acid-splash-spread-targets"))
    prepare_acid_splash_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E2"].position = GridPosition(x=12, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {
            "kind": "cast_spell",
            "spell_id": "acid_splash",
            "target_id": "E1",
            "target_ids": ["E1", "E2"],
        },
        overrides=AttackRollOverrides(save_rolls=[1, 1], damage_rolls=[6]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Acid Splash: targets are not within 5 feet of each other" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_acid_splash_requires_known_cantrip_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-acid-splash-unprepared"))
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "acid_splash", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[6]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Acid Splash: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_acid_splash_out_of_range_does_not_roll_or_spend_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-acid-splash-range"))
    prepare_acid_splash_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["E1"].position = GridPosition(x=13, y=0)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "acid_splash", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[6]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Acid Splash: is not in range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2


def test_shatter_deals_thunder_damage_on_con_saves_spends_level2_slot_and_logs_events() -> None:
    spell = get_spell_definition("shatter")
    encounter = create_encounter(build_wizard_config("wizard-shatter"))
    prepare_shatter_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E2"].position = GridPosition(x=12, y=5)
    encounter.units["E1"].max_hp = 30
    encounter.units["E1"].current_hp = 30
    encounter.units["E2"].max_hp = 30
    encounter.units["E2"].current_hp = 30

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {
            "kind": "cast_spell",
            "spell_id": "shatter",
            "target_id": "E1",
            "target_ids": ["E1", "E2"],
        },
        overrides=AttackRollOverrides(save_rolls=[1, 20], damage_rolls=[3, 4, 5]),
    )

    assert spell.level == 2
    assert spell.school == "evocation"
    assert spell.save_ability == "con"
    assert spell.damage_type == "thunder"
    assert spell.range_feet == 60
    assert spell.half_on_success is True
    assert spell.target_cluster_feet == 10
    assert [event.event_type for event in spell_events] == [
        "phase_change",
        "saving_throw",
        "attack",
        "saving_throw",
        "attack",
    ]
    phase_event = spell_events[0]
    first_save = spell_events[1]
    first_attack = spell_events[2]
    second_save = spell_events[3]
    second_attack = spell_events[4]
    assert phase_event.resolved_totals["spellId"] == "shatter"
    assert phase_event.resolved_totals["targetCount"] == 2
    assert phase_event.resolved_totals["targetClusterFeet"] == 10
    assert first_save.resolved_totals["ability"] == "con"
    assert first_save.resolved_totals["success"] is False
    assert first_attack.resolved_totals["spellId"] == "shatter"
    assert first_attack.resolved_totals["spellLevel"] == 2
    assert first_attack.resolved_totals["saveSucceeded"] is False
    assert first_attack.resolved_totals["fullDamage"] == 12
    assert first_attack.resolved_totals["damageApplied"] == 12
    assert first_attack.resolved_totals["spellSlotsLevel2Remaining"] == 0
    assert first_attack.raw_rolls["damageRolls"] == [3, 4, 5]
    assert first_attack.damage_details.damage_components[0].damage_type == "thunder"
    assert first_attack.damage_details.total_damage == 12
    assert second_save.resolved_totals["success"] is True
    assert second_attack.resolved_totals["saveSucceeded"] is True
    assert second_attack.resolved_totals["damageApplied"] == 6
    assert second_attack.damage_details.total_damage == 6
    assert "Shatter" in first_attack.text_summary
    assert encounter.units["F1"].resources.spell_slots_level_2 == 0


def test_level4_evoker_shatter_and_burning_hands_use_int_asi_save_dc() -> None:
    shatter_encounter = create_encounter(build_level4_wizard_config("wizard-level4-shatter-save-dc"))
    defeat_other_enemies(shatter_encounter, "E1")
    shatter_encounter.units["F1"].position = GridPosition(x=5, y=5)
    shatter_encounter.units["E1"].position = GridPosition(x=10, y=5)

    shatter_events = resolve_cast_spell_action(
        shatter_encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shatter", "target_id": "E1", "target_ids": ["E1"]},
        overrides=AttackRollOverrides(save_rolls=[13], damage_rolls=[3, 4, 5]),
    )
    shatter_attack = next(event for event in shatter_events if event.event_type == "attack")

    assert shatter_attack.resolved_totals["saveDc"] == 14
    assert shatter_attack.resolved_totals["saveSucceeded"] is False

    burning_hands_encounter = create_encounter(build_level4_wizard_config("wizard-level4-burning-hands-save-dc"))
    defeat_other_enemies(burning_hands_encounter, "E1")
    burning_hands_encounter.units["F1"].position = GridPosition(x=5, y=5)
    burning_hands_encounter.units["E1"].position = GridPosition(x=6, y=5)

    burning_hands_events = resolve_cast_spell_action(
        burning_hands_encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "burning_hands", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[3, 2, 1]),
    )
    burning_hands_attack = next(event for event in burning_hands_events if event.event_type == "attack")

    assert burning_hands_attack.resolved_totals["saveDc"] == 14
    assert burning_hands_attack.resolved_totals["saveSucceeded"] is False


def test_scorching_ray_spends_one_level2_slot_and_resolves_three_spell_attacks() -> None:
    spell = get_spell_definition("scorching_ray")
    encounter = create_encounter(build_level3_wizard_config("wizard-scorching-ray-three-rays"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E1"].max_hp = 50
    encounter.units["E1"].current_hp = 50

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "scorching_ray", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[18, 18, 18], damage_rolls=[1, 2, 3, 4, 5, 6]),
    )
    attack_events = [event for event in spell_events if event.event_type == "attack"]

    assert spell.level == 2
    assert spell.school == "evocation"
    assert spell.targeting_mode == "multi_ray_spell_attack"
    assert spell.range_feet == 120
    assert [event.event_type for event in spell_events] == ["phase_change", "attack", "attack", "attack"]
    assert [event.resolved_totals["rayIndex"] for event in attack_events] == [1, 2, 3]
    assert [event.resolved_totals["hit"] for event in attack_events] == [True, True, True]
    assert [event.damage_details.total_damage for event in attack_events] == [3, 7, 11]
    assert encounter.units["F1"].resources.spell_slots_level_2 == 1
    assert all("potentCantripApplied" not in event.resolved_totals for event in attack_events)


def test_level4_evoker_scorching_ray_uses_int_asi_spell_attack_bonus_and_third_level2_slot() -> None:
    encounter = create_encounter(build_level4_wizard_config("wizard-level4-scorching-ray-attack-bonus"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E1"].max_hp = 50
    encounter.units["E1"].current_hp = 50

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "scorching_ray", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[9, 9, 9], damage_rolls=[1, 2, 3, 4, 5, 6]),
    )
    attack_events = [event for event in spell_events if event.event_type == "attack"]

    assert [event.resolved_totals["attackTotal"] for event in attack_events] == [15, 15, 15]
    assert [event.resolved_totals["hit"] for event in attack_events] == [True, True, True]
    assert encounter.units["F1"].resources.spell_slots_level_2 == 2


def test_scorching_ray_stops_remaining_rays_after_target_drops() -> None:
    encounter = create_encounter(build_level3_wizard_config("wizard-scorching-ray-stop-after-drop"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E1"].max_hp = 5
    encounter.units["E1"].current_hp = 5

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "scorching_ray", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[18, 18, 18], damage_rolls=[3, 3, 6, 6, 6, 6]),
    )
    attack_events = [event for event in spell_events if event.event_type == "attack"]

    assert len(attack_events) == 1
    assert attack_events[0].resolved_totals["rayIndex"] == 1
    assert attack_events[0].damage_details.total_damage == 6
    assert encounter.units["E1"].conditions.dead is True
    assert encounter.units["F1"].resources.spell_slots_level_2 == 1


def test_shatter_requires_prepared_spell_and_does_not_spend_level2_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-shatter-unprepared"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].resources.spell_slots_level_2 = 1
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shatter", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Shatter: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_2 == 1


def test_shatter_rejects_targets_outside_burst_cluster_without_spending_slot() -> None:
    encounter = create_encounter(build_wizard_config("wizard-shatter-spread-targets"))
    prepare_shatter_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)
    encounter.units["E2"].position = GridPosition(x=13, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {
            "kind": "cast_spell",
            "spell_id": "shatter",
            "target_id": "E1",
            "target_ids": ["E1", "E2"],
        },
        overrides=AttackRollOverrides(save_rolls=[1, 1], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Shatter: targets are not within 10 feet of each other" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_2 == 1


def test_shatter_rejects_intentional_ally_targets_without_spending_slot() -> None:
    encounter = create_encounter(build_level3_wizard_config("wizard-shatter-ally-target"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=10, y=6)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {
            "kind": "cast_spell",
            "spell_id": "shatter",
            "target_id": "E1",
            "target_ids": ["E1", "F2"],
        },
        overrides=AttackRollOverrides(save_rolls=[1, 1], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Shatter: cannot intentionally target allies" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_2 == 2


def test_shatter_fails_cleanly_when_no_level2_slots_remain() -> None:
    encounter = create_encounter(build_wizard_config("wizard-shatter-no-slot"))
    prepare_shatter_test_wizard(encounter)
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].resources.spell_slots_level_2 = 0
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=10, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shatter", "target_id": "E1"},
        overrides=AttackRollOverrides(save_rolls=[1], damage_rolls=[3, 4, 5]),
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 2 spell slots remain" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_2 == 0


def test_shocking_grasp_prevents_opportunity_attacks_until_target_turn_start() -> None:
    encounter = create_encounter(build_wizard_config("wizard-shocking-grasp-escape"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": "E1"},
        overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[5]),
    )
    movement_events, interrupted = execute_movement(
        encounter,
        "F1",
        MovementPlan(path=[GridPosition(x=5, y=5), GridPosition(x=4, y=5)], mode="move"),
        False,
        "after_action",
    )

    assert interrupted is False
    assert [event.event_type for event in movement_events] == ["move"]

    expire_turn_effects(encounter, "E1")
    assert any(effect.kind == "no_reactions" for effect in encounter.units["E1"].temporary_effects) is False


@pytest.mark.parametrize(
    ("seed", "variant_id", "reaction_id"),
    [
        ("bandit-captain-no-reactions", "bandit_captain", "parry"),
        ("goblin-boss-no-reactions", "goblin_boss", "redirect_attack"),
    ],
)
def test_no_reactions_effect_blocks_monster_attack_reactions(
    seed: str, variant_id: str, reaction_id: str
) -> None:
    encounter = create_encounter(build_monster_benchmark_config(seed, variant_id))
    reactor = encounter.units["E1"]

    assert unit_has_reaction(reactor, reaction_id) is True

    reactor.temporary_effects.append(
        NoReactionsEffect(kind="no_reactions", source_id="F1", expires_at_turn_start_of=reactor.id)
    )

    assert can_trigger_attack_reaction(reactor, reaction_id) is False


def test_shield_reaction_turns_a_stoppable_hit_into_a_miss() -> None:
    encounter = create_encounter(build_wizard_config("wizard-shield-hit-to-miss"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["defenseReaction"] == "shield"
    assert attack_event.resolved_totals["hit"] is False
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1
    assert encounter.units["F1"].reaction_available is False
    assert any(effect.kind == "shield" for effect in encounter.units["F1"].temporary_effects)


def test_baseline_shield_overuses_against_unstoppable_hits() -> None:
    smart = create_encounter(build_wizard_config("wizard-shield-smart-skip", player_behavior="smart"))
    dumb = create_encounter(build_wizard_config("wizard-shield-dumb-cast", player_behavior="dumb"))
    for encounter in (smart, dumb):
        defeat_other_enemies(encounter, "E1")
        encounter.units["F1"].position = GridPosition(x=5, y=5)
        encounter.units["E1"].position = GridPosition(x=6, y=5)

    smart_attack, _ = resolve_attack(
        smart,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )
    dumb_attack, _ = resolve_attack(
        dumb,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert smart_attack.resolved_totals["defenseReaction"] == "shield"
    assert smart.units["F1"].resources.spell_slots_level_1 == 1
    assert any(effect.kind == "shield" for effect in smart.units["F1"].temporary_effects)

    assert dumb_attack.resolved_totals["defenseReaction"] == "shield"
    assert dumb.units["F1"].resources.spell_slots_level_1 == 1
    assert any(effect.kind == "shield" for effect in dumb.units["F1"].temporary_effects)


def test_magic_missile_triggers_shield_and_is_fully_blocked() -> None:
    encounter = create_encounter(build_wizard_config("wizard-magic-missile-shield"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=7, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "magic_missile", "target_id": "F2"},
    )

    assert [event.event_type for event in spell_events] == ["phase_change", "attack"]
    assert spell_events[0].resolved_totals["reaction"] == "shield"
    assert spell_events[1].resolved_totals["blockedByShield"] is True
    assert spell_events[1].damage_details.total_damage == 0
    assert encounter.units["F2"].resources.spell_slots_level_1 == 1
    assert any(effect.kind == "shield" for effect in encounter.units["F2"].temporary_effects)


def test_burning_hands_rolls_saves_uses_one_damage_roll_and_can_hit_allies() -> None:
    encounter = create_encounter(build_wizard_config("wizard-burning-hands-rules"))
    defeat_other_enemies(encounter, "E1", "E2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=7, y=6)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=7, y=5)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "burning_hands", "target_id": "E2"},
        overrides=AttackRollOverrides(damage_rolls=[3, 2, 1], save_rolls=[4, 5, 15]),
    )

    assert [event.event_type for event in spell_events[:7]] == [
        "phase_change",
        "saving_throw",
        "attack",
        "saving_throw",
        "attack",
        "saving_throw",
        "attack",
    ]
    attack_events = [event for event in spell_events if event.event_type == "attack"]
    assert [event.target_ids[0] for event in attack_events] == ["F2", "E1", "E2"]
    assert [event.damage_details.total_damage for event in attack_events] == [6, 6, 3]
    assert all(event.raw_rolls["damageRolls"] == [3, 2, 1] for event in attack_events)


def test_wizard_sample_trio_smoke_run_completes() -> None:
    result = run_encounter(build_wizard_config("wizard-smoke-run"))

    assert result.final_state.terminal_state == "complete"
    assert result.final_state.winner in {"fighters", "goblins", "mutual_annihilation"}


def test_lay_on_hands_restores_downed_target_to_twenty_five_percent_hp() -> None:
    encounter = create_encounter(build_paladin_config("paladin-lay-on-hands-downed"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)
    encounter.units["F2"].current_hp = 0
    encounter.units["F2"].conditions.unconscious = True
    encounter.units["F2"].conditions.prone = True

    heal_event = attempt_lay_on_hands(encounter, "F1", "F2")

    assert heal_event.event_type == "heal"
    assert heal_event.resolved_totals["healingTotal"] == 4
    assert encounter.units["F2"].current_hp == 4
    assert encounter.units["F2"].conditions.unconscious is False
    assert encounter.units["F1"].resources.lay_on_hands_points == 1


def test_lay_on_hands_living_target_heals_to_half_hp_when_triggered() -> None:
    encounter = create_encounter(build_paladin_config("paladin-lay-on-hands-living"))
    encounter.units["F1"].current_hp = 4

    heal_event = attempt_lay_on_hands(encounter, "F1", "F1")

    assert heal_event.resolved_totals["healingTotal"] == 3
    assert encounter.units["F1"].current_hp == 7
    assert encounter.units["F1"].resources.lay_on_hands_points == 2


def test_adjacent_lay_on_hands_rescue_executes_before_paladin_attack() -> None:
    encounter = create_encounter(EncounterConfig(seed="paladin-adjacent-rescue-exec", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True
    encounter.units["G1"].position = GridPosition(x=2, y=8)
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")
    events: list = []
    execute_decision(encounter, "F2", decision, events, rescue_mode=False)

    heal_index = next(index for index, event in enumerate(events) if event.event_type == "heal")
    attack_index = next(index for index, event in enumerate(events) if event.event_type == "attack")
    assert heal_index < attack_index
    assert encounter.units["F1"].current_hp > 0
    assert events[attack_index].target_ids == ["G1"]


def test_movement_lay_on_hands_rescue_preserves_after_action_heal() -> None:
    encounter = create_encounter(EncounterConfig(seed="paladin-movement-rescue-exec", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=1, y=4)
    encounter.units["G1"].position = GridPosition(x=3, y=4)
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True
    encounter.units["G1"].ac = 1
    encounter.units["G1"].current_hp = 13
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")
    events: list = []
    execute_decision(encounter, "F2", decision, events, rescue_mode=False)

    movement_index = next(index for index, event in enumerate(events) if event.event_type == "move")
    attack_index = next(index for index, event in enumerate(events) if event.event_type == "attack")
    heal_index = next(index for index, event in enumerate(events) if event.event_type == "heal")
    assert movement_index < attack_index < heal_index
    assert encounter.units["F1"].current_hp > 0
    assert events[attack_index].resolved_totals.get("divineSmiteApplied") is None


def test_bless_applies_to_weapon_attacks_and_saving_throws() -> None:
    encounter = create_encounter(build_paladin_config("paladin-bless-attack-save"))
    bless_event = resolve_bless(encounter, "F1", ["F1", "F2", "F3"])

    assert bless_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert bless_event.resolved_totals["blessedTargetIds"] == ["F1", "F2", "F3"]
    assert any(
        isinstance(effect, ConcentrationEffect) and effect.spell_id == "bless"
        for effect in encounter.units["F1"].temporary_effects
    )
    assert any(isinstance(effect, BlessedEffect) for effect in encounter.units["F2"].temporary_effects)

    encounter.units["F2"].position = GridPosition(x=4, y=5)
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F2",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[8], damage_rolls=[4]),
        ),
    )

    assert attack_event.raw_rolls["blessRolls"]
    assert attack_event.resolved_totals["blessBonus"] == attack_event.raw_rolls["blessRolls"][0]
    assert (
        attack_event.resolved_totals["attackTotal"]
        == 8 + encounter.units["F2"].attacks["longsword"].attack_bonus + attack_event.raw_rolls["blessRolls"][0]
    )

    save_event = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F2",
            ability="dex",
            dc=30,
            reason="Bless test",
            overrides=SavingThrowOverrides(save_rolls=[10]),
        ),
    )

    assert save_event.raw_rolls["blessRolls"]
    assert (
        save_event.resolved_totals["total"]
        == 10 + encounter.units["F2"].ability_mods.dex + save_event.raw_rolls["blessRolls"][0]
    )


def test_paladin_level5_bless_uses_level2_slot_and_four_targets() -> None:
    encounter = create_encounter(EncounterConfig(seed="paladin-level5-bless", enemy_preset_id="goblin_screen"))

    bless_event = resolve_bless(encounter, "F2", ["F2", "F1", "F3", "F4", "E1"])

    assert bless_event.resolved_totals["spellLevel"] == 2
    assert bless_event.resolved_totals["blessedTargetIds"] == ["F2", "F1", "F3", "F4"]
    assert bless_event.resolved_totals["spellSlotsLevel2Remaining"] == 1
    assert encounter.units["F2"].resources.spell_slots_level_1 == 4
    assert encounter.units["F2"].resources.spell_slots_level_2 == 1
    assert all(
        any(effect.kind == "blessed" for effect in encounter.units[unit_id].temporary_effects)
        for unit_id in ("F1", "F2", "F3", "F4")
    )


def test_paladin_level5_bless_falls_back_to_level1_when_level2_slots_are_empty() -> None:
    encounter = create_encounter(build_level5_paladin_config("paladin-level5-bless-fallback"))
    encounter.units["F1"].resources.spell_slots_level_2 = 0

    bless_event = resolve_bless(encounter, "F1", ["F1", "F2", "F3"])

    assert bless_event.resolved_totals["spellLevel"] == 1
    assert bless_event.resolved_totals["spellSlotsLevel1Remaining"] == 3
    assert bless_event.resolved_totals["spellSlotsLevel2Remaining"] == 0
    assert encounter.units["F1"].resources.spell_slots_level_1 == 3


def test_bless_concentration_persists_on_success_and_drops_on_failure() -> None:
    success = create_encounter(build_paladin_config("paladin-bless-concentration-success"))
    resolve_bless(success, "F1", ["F1", "F2", "F3"])

    success_result = apply_damage(
        success,
        "F1",
        [DamageComponentResult(damage_type="slashing", raw_rolls=[], adjusted_rolls=[], subtotal=0, flat_modifier=2, total_damage=2)],
        False,
        concentration_save_rolls=[20, 4],
    )

    assert success_result.concentration_save_success is True
    assert any(effect.kind == "concentration" for effect in success.units["F1"].temporary_effects)
    assert any(effect.kind == "blessed" for effect in success.units["F2"].temporary_effects)

    failure = create_encounter(build_paladin_config("paladin-bless-concentration-failure"))
    resolve_bless(failure, "F1", ["F1", "F2", "F3"])

    failure_result = apply_damage(
        failure,
        "F1",
        [DamageComponentResult(damage_type="slashing", raw_rolls=[], adjusted_rolls=[], subtotal=0, flat_modifier=2, total_damage=2)],
        False,
        concentration_save_rolls=[1, 1],
    )

    assert failure_result.concentration_save_success is False
    assert failure_result.concentration_ended is True
    assert all(effect.kind != "concentration" for effect in failure.units["F1"].temporary_effects)
    assert all(effect.kind != "blessed" for effect in failure.units["F2"].temporary_effects)


def prepare_shield_of_faith_test_paladin(encounter) -> None:
    if "shield_of_faith" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("shield_of_faith")


def prepare_divine_favor_test_paladin(encounter) -> None:
    if "divine_favor" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("divine_favor")


def prepare_heroism_test_paladin(encounter) -> None:
    if "heroism" not in encounter.units["F1"].prepared_combat_spell_ids:
        encounter.units["F1"].prepared_combat_spell_ids.append("heroism")


def test_heroism_applies_concentration_effect_spends_slot_and_grants_start_turn_temp_hp() -> None:
    spell = get_spell_definition("heroism")
    encounter = create_encounter(build_paladin_config("paladin-heroism"))
    prepare_heroism_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F2"},
    )
    heroism_event = spell_events[0]
    start_event = apply_heroism_start_of_turn(encounter, "F2")

    assert spell.level == 1
    assert spell.school == "enchantment"
    assert spell.timing == "action"
    assert spell.range_feet == 5
    assert spell.concentration is True
    assert spell.duration_rounds == 10
    assert heroism_event.event_type == "phase_change"
    assert heroism_event.resolved_totals["spellId"] == "heroism"
    assert heroism_event.resolved_totals["spellLevel"] == 1
    assert heroism_event.resolved_totals["concentration"] is True
    assert heroism_event.resolved_totals["temporaryHitPointAmount"] == encounter.units["F1"].ability_mods.cha
    assert heroism_event.resolved_totals["startOfTurnUpkeep"] is True
    assert heroism_event.resolved_totals["immediateTemporaryHitPointsApplied"] is False
    assert heroism_event.resolved_totals["frightenedImmunityModeled"] is True
    assert heroism_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "Heroism" in heroism_event.text_summary
    assert any(effect.kind == "concentration" and effect.spell_id == "heroism" for effect in encounter.units["F1"].temporary_effects)
    assert any(isinstance(effect, HeroismEffect) for effect in encounter.units["F2"].temporary_effects)
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1

    assert start_event is not None
    assert start_event.resolved_totals["spellId"] == "heroism"
    assert start_event.resolved_totals["trigger"] == "turn_start"
    assert start_event.resolved_totals["sourceId"] == "F1"
    assert start_event.resolved_totals["temporaryHitPointTotal"] == encounter.units["F1"].ability_mods.cha
    assert start_event.resolved_totals["temporaryHitPointsGained"] == encounter.units["F1"].ability_mods.cha
    assert start_event.resolved_totals["newTemporaryHitPoints"] == encounter.units["F1"].ability_mods.cha
    assert start_event.resolved_totals["frightenedImmunityModeled"] is True
    assert encounter.units["F2"].temporary_hit_points == encounter.units["F1"].ability_mods.cha


def test_heroism_removes_existing_frightened_effect_and_models_immunity() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-frightened"))
    prepare_heroism_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)
    encounter.units["F2"].temporary_effects.append(FrightenedEffect(kind="frightened_by", source_id="E1", save_dc=14))

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F2"},
    )

    assert spell_events[0].resolved_totals["frightenedImmunityModeled"] is True
    assert "F2 is no longer frightened." in spell_events[0].condition_deltas
    assert not any(effect.kind == "frightened_by" for effect in encounter.units["F2"].temporary_effects)
    assert any(
        isinstance(effect, HeroismEffect) and effect.frightened_immunity_modeled is True
        for effect in encounter.units["F2"].temporary_effects
    )


def test_heroism_start_turn_upkeep_does_not_replace_higher_temporary_hp() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-no-replace"))
    prepare_heroism_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)
    encounter.units["F2"].temporary_hit_points = 7

    resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F2"},
    )
    start_event = apply_heroism_start_of_turn(encounter, "F2")

    assert start_event is not None
    assert start_event.resolved_totals["temporaryHitPointsGained"] == 0
    assert start_event.resolved_totals["previousTemporaryHitPoints"] == 7
    assert start_event.resolved_totals["newTemporaryHitPoints"] == 7
    assert encounter.units["F2"].temporary_hit_points == 7


def test_heroism_rejects_enemy_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-enemy"))
    prepare_heroism_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "E1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "target is not a living ally" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "heroism" for effect in encounter.units["E1"].temporary_effects)


def test_heroism_rejects_out_of_touch_range_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-range"))
    prepare_heroism_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=7, y=4)

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F2"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "target is not within touch range" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "heroism" for effect in encounter.units["F2"].temporary_effects)


def test_heroism_requires_prepared_spell_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-unprepared"))

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Heroism: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "heroism" for effect in encounter.units["F1"].temporary_effects)


def test_heroism_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-empty"))
    prepare_heroism_test_paladin(encounter)
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary
    assert all(effect.kind != "heroism" for effect in encounter.units["F1"].temporary_effects)


def test_heroism_ends_when_concentration_fails_and_stops_upkeep() -> None:
    encounter = create_encounter(build_paladin_config("paladin-heroism-concentration"))
    prepare_heroism_test_paladin(encounter)
    resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "heroism", "target_id": "F2"},
    )

    damage_result = apply_damage(
        encounter,
        "F1",
        [DamageComponentResult(damage_type="slashing", raw_rolls=[], adjusted_rolls=[], subtotal=0, flat_modifier=2, total_damage=2)],
        False,
        concentration_save_rolls=[1],
    )

    assert damage_result.concentration_save_success is False
    assert damage_result.concentration_ended is True
    assert all(effect.kind != "concentration" for effect in encounter.units["F1"].temporary_effects)
    assert all(effect.kind != "heroism" for effect in encounter.units["F2"].temporary_effects)
    assert apply_heroism_start_of_turn(encounter, "F2") is None


def test_shield_of_faith_adds_ac_bonus_spends_slot_and_logs_event() -> None:
    spell = get_spell_definition("shield_of_faith")
    encounter = create_encounter(build_paladin_config("paladin-shield-of-faith"))
    prepare_shield_of_faith_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shield_of_faith", "target_id": "F2"},
    )

    assert spell.level == 1
    assert spell.school == "abjuration"
    assert spell.timing == "bonus_action"
    assert spell.range_feet == 60
    assert spell.ac_bonus == 2
    assert len(spell_events) == 1
    shield_event = spell_events[0]
    assert shield_event.event_type == "phase_change"
    assert shield_event.resolved_totals["spellId"] == "shield_of_faith"
    assert shield_event.resolved_totals["spellLevel"] == 1
    assert shield_event.resolved_totals["concentration"] is True
    assert shield_event.resolved_totals["acBonus"] == 2
    assert shield_event.resolved_totals["previousShieldOfFaithBonus"] == 0
    assert shield_event.resolved_totals["newShieldOfFaithBonus"] == 2
    assert shield_event.resolved_totals["previousEffectiveAc"] == encounter.units["F2"].ac
    assert shield_event.resolved_totals["newEffectiveAc"] == encounter.units["F2"].ac + 2
    assert shield_event.resolved_totals["durationRounds"] == 100
    assert shield_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "Shield of Faith" in shield_event.text_summary
    assert any(effect.kind == "concentration" and effect.spell_id == "shield_of_faith" for effect in encounter.units["F1"].temporary_effects)
    assert any(effect.kind == "shield_of_faith" and effect.ac_bonus == 2 for effect in encounter.units["F2"].temporary_effects)
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_shield_of_faith_bonus_affects_attack_target_ac() -> None:
    encounter = create_encounter(build_paladin_config("paladin-shield-of-faith-ac"))
    prepare_shield_of_faith_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].position = GridPosition(x=6, y=4)
    resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shield_of_faith", "target_id": "F2"},
    )

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F2",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[17], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["targetAc"] == encounter.units["F2"].ac + 2
    assert attack_event.resolved_totals["shieldAcBonus"] == 2
    assert attack_event.resolved_totals["hit"] is False


def test_shield_of_faith_rejects_enemy_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-shield-of-faith-enemy"))
    prepare_shield_of_faith_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shield_of_faith", "target_id": "E1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "target is not a living ally" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "shield_of_faith" for effect in encounter.units["E1"].temporary_effects)


def test_shield_of_faith_rejects_out_of_range_target_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-shield-of-faith-range"))
    prepare_shield_of_faith_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=0, y=0)
    encounter.units["F2"].position = GridPosition(x=13, y=0)

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shield_of_faith", "target_id": "F2"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "target is not within 60 feet" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "shield_of_faith" for effect in encounter.units["F2"].temporary_effects)


def test_shield_of_faith_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_paladin_config("paladin-shield-of-faith-empty"))
    prepare_shield_of_faith_test_paladin(encounter)
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shield_of_faith", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary
    assert all(effect.kind != "shield_of_faith" for effect in encounter.units["F1"].temporary_effects)


def test_shield_of_faith_ends_when_concentration_fails() -> None:
    encounter = create_encounter(build_paladin_config("paladin-shield-of-faith-concentration"))
    prepare_shield_of_faith_test_paladin(encounter)
    resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "shield_of_faith", "target_id": "F2"},
    )

    damage_result = apply_damage(
        encounter,
        "F1",
        [DamageComponentResult(damage_type="slashing", raw_rolls=[], adjusted_rolls=[], subtotal=0, flat_modifier=2, total_damage=2)],
        False,
        concentration_save_rolls=[1],
    )

    assert damage_result.concentration_save_success is False
    assert damage_result.concentration_ended is True
    assert all(effect.kind != "concentration" for effect in encounter.units["F1"].temporary_effects)
    assert all(effect.kind != "shield_of_faith" for effect in encounter.units["F2"].temporary_effects)


def test_divine_favor_adds_radiant_weapon_damage_spends_slot_and_logs_event() -> None:
    spell = get_spell_definition("divine_favor")
    encounter = create_encounter(build_paladin_config("paladin-divine-favor"))
    prepare_divine_favor_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].current_hp = 30
    defeat_other_enemies(encounter, "E1")

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "divine_favor", "target_id": "F1"},
    )
    favor_event = spell_events[0]

    assert spell.level == 1
    assert spell.school == "evocation"
    assert spell.timing == "bonus_action"
    assert spell.concentration is True
    assert spell.duration_rounds == 10
    assert spell.damage_type == "radiant"
    assert spell.damage_dice[0].count == 1
    assert spell.damage_dice[0].sides == 4
    assert favor_event.event_type == "phase_change"
    assert favor_event.resolved_totals["spellId"] == "divine_favor"
    assert favor_event.resolved_totals["spellLevel"] == 1
    assert favor_event.resolved_totals["concentration"] is True
    assert favor_event.resolved_totals["damageDieCount"] == 1
    assert favor_event.resolved_totals["damageDieSides"] == 4
    assert favor_event.resolved_totals["damageType"] == "radiant"
    assert favor_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert "Divine Favor" in favor_event.text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1
    assert any(effect.kind == "concentration" and effect.spell_id == "divine_favor" for effect in encounter.units["F1"].temporary_effects)
    assert any(isinstance(effect, DivineFavorEffect) for effect in encounter.units["F1"].temporary_effects)

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[3], divine_favor_damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["divineFavorSpellId"] == "divine_favor"
    assert attack_event.resolved_totals["divineFavorApplied"] is True
    assert attack_event.resolved_totals["divineFavorDamage"] == 4
    assert attack_event.resolved_totals["divineFavorDamageType"] == "radiant"
    assert attack_event.raw_rolls["divineFavorRolls"] == [4]
    assert any(component.damage_type == "radiant" and component.total_damage == 4 for component in attack_event.damage_details.damage_components)
    assert attack_event.resolved_totals.get("divineSmiteApplied") is None


def test_divine_favor_does_not_apply_on_missed_weapon_attack() -> None:
    encounter = create_encounter(build_paladin_config("paladin-divine-favor-miss"))
    prepare_divine_favor_test_paladin(encounter)
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    defeat_other_enemies(encounter, "E1")
    resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "divine_favor", "target_id": "F1"},
    )

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[3], divine_favor_damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals.get("divineFavorApplied") is None
    assert "divineFavorRolls" not in attack_event.raw_rolls


def test_divine_favor_is_self_only_and_does_not_spend_slot_on_invalid_target() -> None:
    encounter = create_encounter(build_paladin_config("paladin-divine-favor-self-only"))
    prepare_divine_favor_test_paladin(encounter)

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "divine_favor", "target_id": "F2"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "can only target self" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "divine_favor" for effect in encounter.units["F1"].temporary_effects)


def test_divine_favor_requires_prepared_spell_and_does_not_spend_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-divine-favor-unprepared"))

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "divine_favor", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "Divine Favor: is not prepared" in spell_events[0].text_summary
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert all(effect.kind != "divine_favor" for effect in encounter.units["F1"].temporary_effects)


def test_divine_favor_fails_cleanly_when_no_level1_slots_remain() -> None:
    encounter = create_encounter(build_paladin_config("paladin-divine-favor-empty"))
    prepare_divine_favor_test_paladin(encounter)
    encounter.units["F1"].resources.spell_slots_level_1 = 0

    spell_events = resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "divine_favor", "target_id": "F1"},
    )

    assert len(spell_events) == 1
    assert spell_events[0].event_type == "skip"
    assert "No level 1 spell slots remain" in spell_events[0].text_summary
    assert all(effect.kind != "divine_favor" for effect in encounter.units["F1"].temporary_effects)


def test_divine_favor_ends_when_concentration_fails() -> None:
    encounter = create_encounter(build_paladin_config("paladin-divine-favor-concentration"))
    prepare_divine_favor_test_paladin(encounter)
    resolve_bonus_action_events(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "divine_favor", "target_id": "F1"},
    )

    damage_result = apply_damage(
        encounter,
        "F1",
        [DamageComponentResult(damage_type="slashing", raw_rolls=[], adjusted_rolls=[], subtotal=0, flat_modifier=2, total_damage=2)],
        False,
        concentration_save_rolls=[1],
    )

    assert damage_result.concentration_save_success is False
    assert damage_result.concentration_ended is True
    assert all(effect.kind != "concentration" for effect in encounter.units["F1"].temporary_effects)
    assert all(effect.kind != "divine_favor" for effect in encounter.units["F1"].temporary_effects)


def test_cure_wounds_heals_two_d8_plus_charisma_and_spends_slot() -> None:
    encounter = create_encounter(build_paladin_config("paladin-cure-wounds"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)
    encounter.units["F2"].current_hp = 1

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "cure_wounds", "target_id": "F2"},
        overrides=AttackRollOverrides(damage_rolls=[8, 7]),
    )

    assert len(spell_events) == 1
    heal_event = spell_events[0]
    assert heal_event.event_type == "heal"
    assert heal_event.raw_rolls["healingRolls"] == [8, 7]
    assert heal_event.resolved_totals["healingModifier"] == 2
    assert heal_event.resolved_totals["healingTotal"] == 12
    assert encounter.units["F2"].current_hp == 13
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1


def test_aid_increases_current_and_max_hp_and_spends_level2_slot() -> None:
    encounter = create_encounter(build_level5_paladin_config("paladin-aid"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["F2"].position = GridPosition(x=5, y=4)
    encounter.units["F3"].position = GridPosition(x=6, y=4)
    encounter.units["F2"].current_hp = 10
    encounter.units["F3"].current_hp = 0
    encounter.units["F3"].conditions.unconscious = True
    encounter.units["F3"].conditions.prone = True

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "aid", "target_id": "F1", "target_ids": ["F1", "F2", "F3"]},
    )

    assert len(spell_events) == 1
    aid_event = spell_events[0]
    assert aid_event.event_type == "heal"
    assert aid_event.resolved_totals["spellId"] == "aid"
    assert aid_event.resolved_totals["spellLevel"] == 2
    assert aid_event.resolved_totals["aidHpBonus"] == 5
    assert aid_event.resolved_totals["aidAppliedTargetIds"] == ["F1", "F2", "F3"]
    assert aid_event.resolved_totals["spellSlotsLevel2Remaining"] == 1
    assert encounter.units["F1"].max_hp == 54
    assert encounter.units["F2"].max_hp == 54
    assert encounter.units["F2"].current_hp == 15
    assert encounter.units["F3"].max_hp == 54
    assert encounter.units["F3"].current_hp == 5
    assert encounter.units["F3"].conditions.unconscious is False
    assert any(isinstance(effect, AidEffect) and effect.hp_bonus == 5 for effect in encounter.units["F2"].temporary_effects)


def test_aid_fails_cleanly_without_level2_slots() -> None:
    encounter = create_encounter(build_level5_paladin_config("paladin-aid-no-slot"))
    encounter.units["F1"].resources.spell_slots_level_2 = 0

    spell_events = resolve_cast_spell_action(
        encounter,
        "F1",
        {"kind": "cast_spell", "spell_id": "aid", "target_id": "F1", "target_ids": ["F1", "F2", "F3"]},
    )

    assert spell_events[0].event_type == "skip"
    assert "Aid: No level 2 spell slots remain." in spell_events[0].resolved_totals["reason"]
    assert encounter.units["F1"].max_hp == 49


def test_divine_smite_does_not_fire_if_weapon_damage_already_kills() -> None:
    encounter = create_encounter(build_level2_paladin_config("paladin-smite-overkill"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].current_hp = 4

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4], smite_damage_rolls=[8, 8]),
        ),
    )

    assert attack_event.resolved_totals.get("divineSmiteApplied") is None
    assert attack_event.damage_details.total_damage == 7
    assert encounter.units["F1"].resources.spell_slots_level_1 == 2
    assert encounter.units["F1"]._bonus_action_used_this_turn is False


def test_divine_smite_fires_on_surviving_critical_melee_hit() -> None:
    encounter = create_encounter(build_level2_paladin_config("paladin-smite-crit"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].max_hp = 100
    encounter.units["E1"].current_hp = 100

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[1], smite_damage_rolls=[8, 7]),
        ),
    )

    assert attack_event.resolved_totals["divineSmiteApplied"] is True
    assert attack_event.resolved_totals["divineSmiteDice"] == 2
    assert attack_event.raw_rolls["divineSmiteRolls"] == [8, 7]
    assert attack_event.resolved_totals["divineSmiteDamage"] == 30
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 1
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1
    assert encounter.units["F1"]._bonus_action_used_this_turn is True


def test_divine_smite_fires_on_normal_hit_only_when_average_smite_can_finish() -> None:
    encounter = create_encounter(build_level2_paladin_config("paladin-smite-kill-confirm"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].current_hp = 10

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[3, 3]),
        ),
    )

    assert attack_event.resolved_totals["divineSmiteApplied"] is True
    assert attack_event.resolved_totals["divineSmiteDamage"] == 6
    assert encounter.units["E1"].current_hp == 0
    assert encounter.units["F1"].resources.spell_slots_level_1 == 1

    no_smite = create_encounter(build_level2_paladin_config("paladin-smite-save-slot"))
    no_smite.units["F1"].position = GridPosition(x=4, y=4)
    no_smite.units["E1"].position = GridPosition(x=5, y=4)
    no_smite.units["E1"].max_hp = 30
    no_smite.units["E1"].current_hp = 30

    no_smite_event, _ = resolve_attack(
        no_smite,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )

    assert no_smite_event.resolved_totals.get("divineSmiteApplied") is None
    assert no_smite.units["F1"].resources.spell_slots_level_1 == 2


def test_divine_smite_spends_early_slot_on_surviving_target_at_twelve_hp_or_less() -> None:
    smite = create_encounter(build_level2_paladin_config("paladin-smite-early-slot"))
    smite.units["F1"].position = GridPosition(x=4, y=4)
    smite.units["E1"].position = GridPosition(x=5, y=4)
    smite.units["E1"].max_hp = 16
    smite.units["E1"].current_hp = 16

    smite_event, _ = resolve_attack(
        smite,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[1, 1]),
        ),
    )

    assert smite_event.resolved_totals["divineSmiteApplied"] is True
    assert smite_event.resolved_totals["divineSmiteDamage"] == 2
    assert smite.units["F1"].resources.spell_slots_level_1 == 1

    conserve = create_encounter(build_level2_paladin_config("paladin-smite-conserve-last-slot"))
    conserve.units["F1"].position = GridPosition(x=4, y=4)
    conserve.units["E1"].position = GridPosition(x=5, y=4)
    conserve.units["E1"].max_hp = 16
    conserve.units["E1"].current_hp = 16
    conserve.units["F1"].resources.spell_slots_level_1 = 1

    conserve_event, _ = resolve_attack(
        conserve,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )

    assert conserve_event.resolved_totals.get("divineSmiteApplied") is None
    assert conserve.units["F1"].resources.spell_slots_level_1 == 1


def test_level5_divine_smite_uses_level2_slot_when_level1_average_would_not_finish() -> None:
    encounter = create_encounter(build_level5_paladin_config("paladin-smite-level2-kill-confirm"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].max_hp = 18
    encounter.units["E1"].current_hp = 18

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[4, 4, 4]),
        ),
    )

    assert attack_event.resolved_totals["divineSmiteApplied"] is True
    assert attack_event.resolved_totals["spellLevel"] == 2
    assert attack_event.resolved_totals["divineSmiteDice"] == 3
    assert attack_event.raw_rolls["divineSmiteRolls"] == [4, 4, 4]
    assert attack_event.resolved_totals["spellSlotsLevel1Remaining"] == 4
    assert attack_event.resolved_totals["spellSlotsLevel2Remaining"] == 1
    assert encounter.units["F1"].resources.spell_slots_level_1 == 4
    assert encounter.units["F1"].resources.spell_slots_level_2 == 1


def test_level5_divine_smite_uses_level1_slot_when_level1_average_finishes() -> None:
    encounter = create_encounter(build_level5_paladin_config("paladin-smite-level1-first"))
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].max_hp = 14
    encounter.units["E1"].current_hp = 14

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[4, 4]),
        ),
    )

    assert attack_event.resolved_totals["divineSmiteApplied"] is True
    assert attack_event.resolved_totals["spellLevel"] == 1
    assert attack_event.resolved_totals["divineSmiteDice"] == 2
    assert encounter.units["F1"].resources.spell_slots_level_1 == 3
    assert encounter.units["F1"].resources.spell_slots_level_2 == 2


def test_divine_smite_uses_three_d8_against_undead() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-smite-undead",
            enemy_preset_id="skeleton_benchmark",
            player_preset_id="paladin_level2_sample_trio",
        )
    )
    encounter.units["F1"].position = GridPosition(x=4, y=4)
    encounter.units["E1"].position = GridPosition(x=5, y=4)
    encounter.units["E1"].current_hp = 12

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[1, 2, 3]),
        ),
    )

    assert attack_event.resolved_totals["divineSmiteApplied"] is True
    assert attack_event.resolved_totals["divineSmiteDice"] == 3
    assert attack_event.raw_rolls["divineSmiteRolls"] == [1, 2, 3]
    assert attack_event.resolved_totals["divineSmiteDamage"] == 6


def test_divine_smite_rejects_ranged_opportunity_no_slot_and_used_bonus_action_cases() -> None:
    ranged = create_encounter(build_level2_paladin_config("paladin-smite-ranged"))
    ranged.units["F1"].position = GridPosition(x=4, y=4)
    ranged.units["E1"].position = GridPosition(x=5, y=4)
    ranged.units["E1"].current_hp = 10
    ranged_event, _ = resolve_attack(
        ranged,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="javelin",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )
    assert ranged_event.resolved_totals.get("divineSmiteApplied") is None

    opportunity = create_encounter(build_level2_paladin_config("paladin-smite-opportunity"))
    opportunity.units["F1"].position = GridPosition(x=4, y=4)
    opportunity.units["E1"].position = GridPosition(x=5, y=4)
    opportunity.units["E1"].current_hp = 100
    opportunity_event, _ = resolve_attack(
        opportunity,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )
    assert opportunity_event.resolved_totals.get("divineSmiteApplied") is None

    no_slot = create_encounter(build_level2_paladin_config("paladin-smite-no-slot"))
    no_slot.units["F1"].position = GridPosition(x=4, y=4)
    no_slot.units["E1"].position = GridPosition(x=5, y=4)
    no_slot.units["E1"].current_hp = 100
    no_slot.units["F1"].resources.spell_slots_level_1 = 0
    no_slot_event, _ = resolve_attack(
        no_slot,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )
    assert no_slot_event.resolved_totals.get("divineSmiteApplied") is None

    used_bonus = create_encounter(build_level2_paladin_config("paladin-smite-bonus-used"))
    used_bonus.units["F1"].position = GridPosition(x=4, y=4)
    used_bonus.units["E1"].position = GridPosition(x=5, y=4)
    used_bonus.units["E1"].current_hp = 100
    used_bonus.units["F1"]._bonus_action_used_this_turn = True
    used_bonus_event, _ = resolve_attack(
        used_bonus,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )
    assert used_bonus_event.resolved_totals.get("divineSmiteApplied") is None

    reserved_bonus = create_encounter(build_level2_paladin_config("paladin-smite-bonus-reserved"))
    reserved_bonus.units["F1"].position = GridPosition(x=4, y=4)
    reserved_bonus.units["E1"].position = GridPosition(x=5, y=4)
    reserved_bonus.units["E1"].current_hp = 100
    reserved_bonus.units["F1"]._bonus_action_reserved_this_turn = True
    reserved_bonus_event, _ = resolve_attack(
        reserved_bonus,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )
    assert reserved_bonus_event.resolved_totals.get("divineSmiteApplied") is None


def test_paladin_level2_sample_trio_smoke_run_completes() -> None:
    result = run_encounter(build_level2_paladin_config("paladin-level2-smoke-run"))

    assert result.final_state.terminal_state == "complete"
    assert result.final_state.winner in {"fighters", "goblins", "mutual_annihilation"}


def test_natures_wrath_spends_channel_divinity_and_restrains_failed_saves() -> None:
    encounter = create_encounter(build_level3_paladin_config("paladin-natures-wrath"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=8, y=5)
    defeat_other_enemies(encounter, "E1", "E2")

    event = attempt_natures_wrath(
        encounter,
        "F1",
        ["E1", "E2"],
        SavingThrowOverrides(save_rolls=[1, 20]),
    )

    assert event.event_type == "phase_change"
    assert event.resolved_totals["saveDc"] == 12
    assert event.resolved_totals["restrainedTargetIds"] == ["E1"]
    assert event.resolved_totals["successfulSaveTargetIds"] == ["E2"]
    assert encounter.units["F1"].resources.channel_divinity_uses == 1
    assert any(effect.kind == "restrained_by" and effect.save_ends for effect in encounter.units["E1"].temporary_effects)
    assert any(effect.kind == "restrained_by" for effect in encounter.units["E2"].temporary_effects) is False


def test_natures_wrath_skips_invalid_targets_and_fails_without_channel_divinity() -> None:
    encounter = create_encounter(build_level3_paladin_config("paladin-natures-wrath-invalid-targets"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=10, y=5)
    encounter.units["E3"].position = GridPosition(x=7, y=5)
    encounter.units["E3"].conditions.unconscious = True
    encounter.units["E3"].current_hp = 0
    encounter.units["E4"].position = GridPosition(x=8, y=5)
    encounter.units["E1"].temporary_effects.append(
        RestrainedEffect(
            kind="restrained_by",
            source_id="F2",
            escape_dc=12,
            save_ability="str",
            save_ends=True,
            remaining_rounds=10,
        )
    )
    defeat_other_enemies(encounter, "E1", "E2", "E3", "E4")

    event = attempt_natures_wrath(
        encounter,
        "F1",
        ["E1", "E2", "E3", "E4"],
        SavingThrowOverrides(save_rolls=[1]),
    )

    assert event.target_ids == ["E4"]
    assert event.resolved_totals["restrainedTargetIds"] == ["E4"]

    no_channel = create_encounter(build_level3_paladin_config("paladin-natures-wrath-no-channel"))
    no_channel.units["F1"].position = GridPosition(x=5, y=5)
    no_channel.units["E1"].position = GridPosition(x=6, y=5)
    no_channel.units["F1"].resources.channel_divinity_uses = 0

    no_channel_event = attempt_natures_wrath(no_channel, "F1", ["E1"])

    assert no_channel_event.event_type == "skip"
    assert "No Channel Divinity uses remain" in no_channel_event.text_summary


def test_natures_wrath_end_of_turn_save_removes_or_preserves_restraint() -> None:
    success = create_encounter(build_level3_paladin_config("paladin-natures-wrath-end-save-success"))
    success.units["E1"].temporary_effects.append(
        RestrainedEffect(
            kind="restrained_by",
            source_id="F1",
            escape_dc=12,
            save_ability="str",
            save_ends=True,
            remaining_rounds=10,
        )
    )
    success.units["E1"].effective_speed = 0

    success_event = resolve_restrained_end_of_turn_save(
        success,
        "E1",
        SavingThrowOverrides(save_rolls=[20]),
    )

    assert success_event is not None
    assert success_event.resolved_totals["restrainedEnded"] is True
    assert any(effect.kind == "restrained_by" for effect in success.units["E1"].temporary_effects) is False
    assert success.units["E1"].effective_speed == success.units["E1"].speed

    failure = create_encounter(build_level3_paladin_config("paladin-natures-wrath-end-save-failure"))
    failure.units["E1"].temporary_effects.append(
        RestrainedEffect(
            kind="restrained_by",
            source_id="F1",
            escape_dc=12,
            save_ability="str",
            save_ends=True,
            remaining_rounds=10,
        )
    )
    failure.units["E1"].effective_speed = 0

    failure_event = resolve_restrained_end_of_turn_save(
        failure,
        "E1",
        SavingThrowOverrides(save_rolls=[1]),
    )

    assert failure_event is not None
    assert failure_event.resolved_totals["restrainedEnded"] is False
    assert any(effect.kind == "restrained_by" for effect in failure.units["E1"].temporary_effects) is True
    assert failure.units["E1"].effective_speed == 0


def test_paladin_level3_sample_trio_smoke_run_completes() -> None:
    result = run_encounter(build_level3_paladin_config("paladin-level3-smoke-run"))

    assert result.final_state.terminal_state == "complete"
    assert result.final_state.winner in {"fighters", "goblins", "mutual_annihilation"}


def test_sentinel_halt_reduces_speed_after_opportunity_attack_hit() -> None:
    encounter = create_encounter(build_level4_paladin_config("paladin-sentinel-halt"))
    encounter.initiative_order = ["E1", "F1", "F2", "F3"]
    encounter.active_combatant_index = 0
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[1]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["sentinelHaltApplied"] is True
    assert attack_event.resolved_totals["speedReducedToZero"] is True
    assert encounter.units["E1"].effective_speed == 0
    assert any(effect.kind == "halted" and effect.expires_at_turn_end_of == "E1" for effect in encounter.units["E1"].temporary_effects)

    expire_turn_end_effects(encounter, "E1")

    assert any(effect.kind == "halted" for effect in encounter.units["E1"].temporary_effects) is False
    assert encounter.units["E1"].effective_speed == encounter.units["E1"].speed


def test_sentinel_halt_does_not_apply_on_missed_opportunity_attack() -> None:
    encounter = create_encounter(build_level4_paladin_config("paladin-sentinel-halt-miss"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 40
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[1]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is False
    assert attack_event.resolved_totals.get("sentinelHaltApplied") is None
    assert encounter.units["E1"].effective_speed == encounter.units["E1"].speed
    assert any(effect.kind == "halted" for effect in encounter.units["E1"].temporary_effects) is False


def test_sentinel_guardian_reacts_when_adjacent_enemy_hits_an_ally() -> None:
    encounter = create_encounter(build_level4_paladin_config("paladin-sentinel-guardian"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=5)
    encounter.units["F3"].position = GridPosition(x=1, y=1)
    encounter.units["E1"].position = GridPosition(x=5, y=6)
    defeat_other_enemies(encounter, "E1")

    events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F2", "weapon_id": "scimitar"},
        step_overrides=[AttackRollOverrides(attack_rolls=[20], damage_rolls=[1])],
    )

    guardian_phase = next(
        event for event in events if event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "sentinel_guardian"
    )
    guardian_attack = next(
        event
        for event in events
        if event.event_type == "attack" and event.actor_id == "F1" and event.resolved_totals.get("opportunityAttack") is True
    )

    assert guardian_phase.actor_id == "F1"
    assert guardian_phase.target_ids == ["E1"]
    assert guardian_attack.damage_details.weapon_id == "longsword"
    assert encounter.units["F1"].reaction_available is False


def test_sentinel_guardian_respects_target_reaction_and_reach_limits() -> None:
    paladin_target = create_encounter(build_level4_paladin_config("paladin-sentinel-guardian-target"))
    paladin_target.units["F1"].position = GridPosition(x=5, y=5)
    paladin_target.units["E1"].position = GridPosition(x=5, y=6)
    defeat_other_enemies(paladin_target, "E1")

    target_events = resolve_attack_action(
        paladin_target,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "scimitar"},
        step_overrides=[AttackRollOverrides(attack_rolls=[20], damage_rolls=[1])],
    )
    assert any(event.resolved_totals.get("reaction") == "sentinel_guardian" for event in target_events) is False

    no_reaction = create_encounter(build_level4_paladin_config("paladin-sentinel-guardian-no-reaction"))
    no_reaction.units["F1"].position = GridPosition(x=5, y=5)
    no_reaction.units["F2"].position = GridPosition(x=6, y=5)
    no_reaction.units["F3"].position = GridPosition(x=1, y=1)
    no_reaction.units["E1"].position = GridPosition(x=5, y=6)
    no_reaction.units["F1"].reaction_available = False
    defeat_other_enemies(no_reaction, "E1")

    no_reaction_events = resolve_attack_action(
        no_reaction,
        "E1",
        {"kind": "attack", "target_id": "F2", "weapon_id": "scimitar"},
        step_overrides=[AttackRollOverrides(attack_rolls=[20], damage_rolls=[1])],
    )
    assert any(event.resolved_totals.get("reaction") == "sentinel_guardian" for event in no_reaction_events) is False

    out_of_reach = create_encounter(build_level4_paladin_config("paladin-sentinel-guardian-out-of-reach"))
    out_of_reach.units["F1"].position = GridPosition(x=1, y=1)
    out_of_reach.units["F2"].position = GridPosition(x=6, y=5)
    out_of_reach.units["F3"].position = GridPosition(x=2, y=1)
    out_of_reach.units["E1"].position = GridPosition(x=5, y=6)
    defeat_other_enemies(out_of_reach, "E1")

    out_of_reach_events = resolve_attack_action(
        out_of_reach,
        "E1",
        {"kind": "attack", "target_id": "F2", "weapon_id": "scimitar"},
        step_overrides=[AttackRollOverrides(attack_rolls=[20], damage_rolls=[1])],
    )
    assert any(event.resolved_totals.get("reaction") == "sentinel_guardian" for event in out_of_reach_events) is False


def test_sentinel_opportunity_attacks_do_not_trigger_divine_smite() -> None:
    encounter = create_encounter(build_level4_paladin_config("paladin-sentinel-no-smite"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="longsword",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[1], smite_damage_rolls=[8, 8]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals.get("divineSmiteApplied") is None
    assert encounter.units["F1"].resources.spell_slots_level_1 == 3


def test_sentinel_can_opportunity_attack_through_disengage_movement() -> None:
    encounter = create_encounter(build_level4_paladin_config("paladin-sentinel-disengage"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=1, y=1)
    encounter.units["F3"].position = GridPosition(x=2, y=1)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")

    events, _ = execute_movement(
        encounter,
        "E1",
        MovementPlan(
            path=[GridPosition(x=6, y=5), GridPosition(x=7, y=5)],
            mode="move",
        ),
        disengage_applied=True,
        phase="before_action",
    )

    move_event = next(event for event in events if event.event_type == "move")
    opportunity_events = [event for event in events if event.event_type == "attack" and event.actor_id == "F1"]

    assert move_event.resolved_totals["disengageApplied"] is True
    assert move_event.resolved_totals["opportunityAttackers"] == ["F1"]
    assert opportunity_events
    assert opportunity_events[0].resolved_totals["opportunityAttack"] is True
    assert encounter.units["F1"].reaction_available is False


def test_paladin_level4_sample_trio_smoke_run_completes() -> None:
    result = run_encounter(build_level4_paladin_config("paladin-level4-smoke-run"))

    assert result.final_state.terminal_state == "complete"
    assert result.final_state.winner in {"fighters", "goblins", "mutual_annihilation"}


def test_paladin_level5_sample_trio_smoke_run_completes() -> None:
    result = run_encounter(build_level5_paladin_config("paladin-level5-smoke-run"))

    assert result.final_state.terminal_state == "complete"
    assert result.final_state.winner in {"fighters", "goblins", "mutual_annihilation"}


def test_monk_unarmored_defense_uses_dex_plus_wis() -> None:
    encounter = create_encounter(build_monk_config("monk-unarmored-defense"))

    assert encounter.units["F1"].ac == 15


def test_martial_arts_grants_bonus_unarmed_strike() -> None:
    encounter = create_encounter(build_monk_config("monk-martial-arts-grant"))

    assert unit_has_granted_bonus_action(encounter.units["F1"], "bonus_unarmed_strike") is True


def test_bonus_unarmed_strike_uses_dex_and_martial_arts_damage_die() -> None:
    encounter = create_encounter(build_monk_config("monk-bonus-unarmed"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    bonus_events = resolve_bonus_attack_action(
        encounter,
        "F1",
        {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "E1"},
        step_overrides=[AttackRollOverrides(attack_rolls=[14], damage_rolls=[4])],
    )

    assert len(bonus_events) == 1
    attack_event = bonus_events[0]
    assert attack_event.event_type == "attack"
    assert attack_event.damage_details.weapon_id == "unarmed_strike"
    assert attack_event.damage_details.weapon_name == "Unarmed Strike"
    assert attack_event.damage_details.flat_modifier == 3
    assert attack_event.damage_details.total_damage == 7
    assert attack_event.resolved_totals["attackTotal"] == 19


def test_attack_then_bonus_unarmed_strike_produces_two_attack_events() -> None:
    encounter = create_encounter(build_monk_config("monk-attack-bonus"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "attack", "target_id": "E1", "weapon_id": "shortsword"},
            bonus_action={"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "E1"},
        ),
        events,
        rescue_mode=False,
    )

    attack_events = [event for event in events if event.event_type == "attack"]
    assert len(attack_events) == 2
    assert attack_events[0].damage_details.weapon_id == "shortsword"
    assert attack_events[1].damage_details.weapon_id == "unarmed_strike"


def test_dash_then_bonus_unarmed_strike_works_without_attack_action() -> None:
    encounter = create_encounter(build_monk_config("monk-dash-bonus"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E1"].position = GridPosition(x=5, y=1)
    defeat_other_enemies(encounter, "E1")

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "dash", "reason": "Closing to use Martial Arts."},
            bonus_action={"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "E1"},
            pre_action_movement=MovementPlan(
                path=[
                    GridPosition(x=1, y=1),
                    GridPosition(x=2, y=1),
                    GridPosition(x=3, y=1),
                    GridPosition(x=4, y=1),
                ],
                mode="dash",
            ),
        ),
        events,
        rescue_mode=False,
    )

    assert encounter.units["F1"].position.model_dump() == {"x": 4, "y": 1}
    assert [event.event_type for event in events if event.event_type in {"move", "attack"}] == ["move", "attack"]
    assert next(event for event in events if event.event_type == "attack").damage_details.weapon_id == "unarmed_strike"


def test_bonus_unarmed_strike_skips_cleanly_when_no_adjacent_target_remains() -> None:
    encounter = create_encounter(build_monk_config("monk-bonus-skip"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 1
    defeat_other_enemies(encounter, "E1")

    resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[19], damage_rolls=[6]),
        ),
    )

    bonus_events = resolve_bonus_attack_action(
        encounter,
        "F1",
        {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "E1"},
    )

    assert len(bonus_events) == 1
    assert bonus_events[0].event_type == "skip"
    assert "No bonus-action unarmed target is available." in bonus_events[0].text_summary


def test_level2_monks_focus_grants_bonus_actions() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-focus-grants"))
    monk = encounter.units["F1"]

    for action_id in ("bonus_dash", "disengage", "flurry_of_blows", "patient_defense", "step_of_the_wind"):
        assert unit_has_granted_bonus_action(monk, action_id) is True


def test_flurry_of_blows_spends_focus_and_resolves_two_unarmed_strikes() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-flurry"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    bonus_events = resolve_bonus_attack_action(
        encounter,
        "F1",
        {"kind": "flurry_of_blows", "timing": "after_action", "target_id": "E1"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[14], damage_rolls=[2]),
            AttackRollOverrides(attack_rolls=[13], damage_rolls=[5]),
        ],
    )

    attack_events = [event for event in bonus_events if event.event_type == "attack"]

    assert bonus_events[0].event_type == "phase_change"
    assert bonus_events[0].resolved_totals["focusPointsRemaining"] == 1
    assert len(attack_events) == 2
    assert all(event.damage_details.weapon_id == "unarmed_strike" for event in attack_events)
    assert encounter.units["F1"].resources.focus_points == 1


def test_flurry_of_blows_skips_remaining_strikes_when_the_target_drops() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-flurry-drop"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 1
    defeat_other_enemies(encounter, "E1")

    bonus_events = resolve_bonus_attack_action(
        encounter,
        "F1",
        {"kind": "flurry_of_blows", "timing": "after_action", "target_id": "E1"},
        step_overrides=[AttackRollOverrides(attack_rolls=[19], damage_rolls=[3])],
    )

    attack_events = [event for event in bonus_events if event.event_type == "attack"]

    assert bonus_events[0].event_type == "phase_change"
    assert len(attack_events) == 1
    assert encounter.units["E1"].conditions.dead is True
    assert encounter.units["F1"].resources.focus_points == 1


def test_patient_defense_spends_focus_and_applies_dodging() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-patient-defense"))

    bonus_event = resolve_bonus_action(encounter, "F1", {"kind": "patient_defense", "timing": "before_action"})

    assert bonus_event is not None
    assert bonus_event.event_type == "phase_change"
    assert bonus_event.resolved_totals["dodging"] is True
    assert bonus_event.resolved_totals["disengageApplied"] is True
    assert encounter.units["F1"].resources.focus_points == 1
    assert any(effect.kind == "dodging" for effect in encounter.units["F1"].temporary_effects)


def test_dodging_imposes_attack_disadvantage_and_expires_at_turn_start() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-dodging-expiry"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    resolve_bonus_action(encounter, "F1", {"kind": "patient_defense", "timing": "before_action"})
    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[18, 7], damage_rolls=[4]),
        ),
    )

    expiry_events = expire_turn_effects(encounter, "F1")

    assert attack_event.resolved_totals["attackMode"] == "disadvantage"
    assert "target_dodging" in attack_event.raw_rolls["disadvantageSources"]
    assert any(effect.kind == "dodging" for effect in encounter.units["F1"].temporary_effects) is False
    assert any(event.event_type == "effect_expired" for event in expiry_events)


def test_step_of_the_wind_spends_focus_and_grants_dash_budget() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-step-of-the-wind"))

    bonus_event = resolve_bonus_action(encounter, "F1", {"kind": "step_of_the_wind", "timing": "before_action"})
    movement_budget = get_total_movement_budget(
        encounter.units["F1"],
        {"kind": "attack", "target_id": "E1", "weapon_id": "shortsword"},
        {"kind": "step_of_the_wind", "timing": "before_action"},
    )

    assert bonus_event is not None
    assert bonus_event.event_type == "phase_change"
    assert bonus_event.resolved_totals["disengageApplied"] is True
    assert bonus_event.resolved_totals["extraMovementMultiplier"] == 1
    assert encounter.units["F1"].resources.focus_points == 1
    assert movement_budget == 16


def test_paid_focus_actions_skip_cleanly_when_no_focus_points_remain() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-no-focus"))
    encounter.units["F1"].resources.focus_points = 0
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    patient_defense_event = resolve_bonus_action(encounter, "F1", {"kind": "patient_defense", "timing": "before_action"})
    flurry_events = resolve_bonus_attack_action(
        encounter,
        "F1",
        {"kind": "flurry_of_blows", "timing": "after_action", "target_id": "E1"},
    )

    assert patient_defense_event is not None
    assert patient_defense_event.event_type == "skip"
    assert patient_defense_event.resolved_totals["reason"] == "No Focus Points remain."
    assert len(flurry_events) == 1
    assert flurry_events[0].event_type == "skip"
    assert flurry_events[0].resolved_totals["reason"] == "No Focus Points remain."


def test_uncanny_metabolism_restores_focus_and_heals_when_beneficial() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-uncanny-metabolism"))
    monk = encounter.units["F1"]
    monk.current_hp = 10
    monk.resources.focus_points = 0

    event = attempt_uncanny_metabolism(encounter, "F1")

    assert event is not None
    assert event.event_type == "heal"
    assert event.resolved_totals["currentHp"] == monk.current_hp
    assert monk.current_hp > 10
    assert monk.resources.focus_points == 2
    assert monk.resources.uncanny_metabolism_uses == 0


def test_uncanny_metabolism_stays_quiet_when_the_monk_is_fresh() -> None:
    encounter = create_encounter(build_level2_monk_config("monk-uncanny-metabolism-fresh"))

    assert attempt_uncanny_metabolism(encounter, "F1") is None
    assert encounter.units["F1"].resources.focus_points == 2
    assert encounter.units["F1"].resources.uncanny_metabolism_uses == 1


def test_rage_activation_consumes_a_use_and_grants_temp_hp() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-rage-activation"))

    rage_event = resolve_bonus_action(encounter, "F1", {"kind": "rage", "timing": "before_action"})

    assert rage_event is not None
    assert encounter.units["F1"].resources.rage_uses == 1
    assert encounter.units["F1"].temporary_hit_points == 1
    assert any(effect.kind == "rage" for effect in encounter.units["F1"].temporary_effects)


def test_rage_resistance_and_temp_hp_reduce_weapon_damage_before_hp_loss() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-rage-resistance"))
    resolve_bonus_action(encounter, "F1", {"kind": "rage", "timing": "before_action"})

    damage_result = apply_damage(
        encounter,
        "F1",
        [
            DamageComponentResult(
                damage_type="slashing",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 4
    assert damage_result.temporary_hp_absorbed == 1
    assert damage_result.final_damage_to_hp == 2
    assert encounter.units["F1"].current_hp == 13
    assert encounter.units["F1"].temporary_hit_points == 0


def test_skeleton_bludgeoning_vulnerability_doubles_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("skeleton-bludgeoning", "skeleton"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="bludgeoning",
                raw_rolls=[5],
                adjusted_rolls=[5],
                subtotal=5,
                flat_modifier=0,
                total_damage=5,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 0
    assert damage_result.amplified_damage == 5
    assert damage_result.final_total_damage == 10
    assert encounter.units["E1"].current_hp == 3


def test_skeleton_poison_immunity_prevents_all_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("skeleton-poison", "skeleton"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="poison",
                raw_rolls=[5],
                adjusted_rolls=[5],
                subtotal=5,
                flat_modifier=0,
                total_damage=5,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 5
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 0
    assert encounter.units["E1"].current_hp == 13


def test_zombie_poison_immunity_prevents_all_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-poison", "zombie"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="poison",
                raw_rolls=[5],
                adjusted_rolls=[5],
                subtotal=5,
                flat_modifier=0,
                total_damage=5,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 5
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 0
    assert encounter.units["E1"].current_hp == 15


def test_zombie_undead_fortitude_failure_removes_it_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-fortitude-fail", "zombie"))
    monkeypatch.setattr(combat_rules_module, "pull_die", lambda state, sides, override=None: 2)

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="bludgeoning",
                raw_rolls=[15],
                adjusted_rolls=[15],
                subtotal=15,
                flat_modifier=0,
                total_damage=15,
            )
        ],
        False,
    )

    assert damage_result.undead_fortitude_triggered is True
    assert damage_result.undead_fortitude_success is False
    assert damage_result.undead_fortitude_dc == 20
    assert damage_result.undead_fortitude_bypass_reason is None
    assert encounter.units["E1"].current_hp == 0
    assert encounter.units["E1"].conditions.dead is True
    assert "E1's Undead Fortitude fails against DC 20." in damage_result.condition_deltas
    assert "E1 is removed from combat at 0 HP." in damage_result.condition_deltas


def test_zombie_undead_fortitude_success_leaves_it_at_one_hp(monkeypatch: pytest.MonkeyPatch) -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-fortitude-success", "zombie"))
    encounter.units["E1"].temporary_effects.append(SlowEffect(kind="slow", source_id="F1", expires_at_turn_start_of="F1", penalty=10))
    monkeypatch.setattr(combat_rules_module, "pull_die", lambda state, sides, override=None: 20)

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="slashing",
                raw_rolls=[15],
                adjusted_rolls=[15],
                subtotal=15,
                flat_modifier=0,
                total_damage=15,
            )
        ],
        False,
    )

    assert damage_result.undead_fortitude_triggered is True
    assert damage_result.undead_fortitude_success is True
    assert damage_result.undead_fortitude_dc == 20
    assert damage_result.undead_fortitude_bypass_reason is None
    assert encounter.units["E1"].current_hp == 1
    assert encounter.units["E1"].conditions.dead is False
    assert any(effect.kind == "slow" for effect in encounter.units["E1"].temporary_effects) is True
    assert "E1's Undead Fortitude succeeds (DC 20); it remains at 1 HP." in damage_result.condition_deltas


def test_zombie_undead_fortitude_is_bypassed_by_radiant_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-fortitude-radiant", "zombie"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="radiant",
                raw_rolls=[15],
                adjusted_rolls=[15],
                subtotal=15,
                flat_modifier=0,
                total_damage=15,
            )
        ],
        False,
    )

    assert damage_result.undead_fortitude_triggered is True
    assert damage_result.undead_fortitude_success is None
    assert damage_result.undead_fortitude_dc is None
    assert damage_result.undead_fortitude_bypass_reason == "radiant"
    assert encounter.units["E1"].conditions.dead is True
    assert "E1's Undead Fortitude is bypassed by radiant damage." in damage_result.condition_deltas


def test_zombie_undead_fortitude_is_bypassed_by_critical_hit() -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-fortitude-critical", "zombie"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="bludgeoning",
                raw_rolls=[15],
                adjusted_rolls=[15],
                subtotal=15,
                flat_modifier=0,
                total_damage=15,
            )
        ],
        True,
    )

    assert damage_result.undead_fortitude_triggered is True
    assert damage_result.undead_fortitude_success is None
    assert damage_result.undead_fortitude_dc is None
    assert damage_result.undead_fortitude_bypass_reason == "critical"
    assert encounter.units["E1"].conditions.dead is True
    assert "E1's Undead Fortitude is bypassed by a critical hit." in damage_result.condition_deltas


def test_zombie_undead_fortitude_dc_uses_final_damage_to_hp_after_temp_hp(monkeypatch: pytest.MonkeyPatch) -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-fortitude-dc", "zombie"))
    encounter.units["E1"].current_hp = 10
    encounter.units["E1"].temporary_hit_points = 4
    monkeypatch.setattr(combat_rules_module, "pull_die", lambda state, sides, override=None: 2)

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="bludgeoning",
                raw_rolls=[15],
                adjusted_rolls=[15],
                subtotal=15,
                flat_modifier=0,
                total_damage=15,
            )
        ],
        False,
    )

    assert damage_result.temporary_hp_absorbed == 4
    assert damage_result.final_damage_to_hp == 11
    assert damage_result.undead_fortitude_dc == 16
    assert damage_result.undead_fortitude_success is False


def test_zombie_attack_event_reports_undead_fortitude_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    encounter = create_encounter(build_monster_benchmark_config("zombie-fortitude-event", "zombie"))
    defeat_other_enemies(encounter, "E1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 5
    melee_weapon_id = next(weapon_id for weapon_id, weapon in encounter.units["F1"].attacks.items() if weapon.kind == "melee")
    monkeypatch.setattr(
        combat_rules_module,
        "pull_die",
        lambda state, sides, override=None: override if override is not None else 20,
    )

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id=melee_weapon_id,
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[18], damage_rolls=[6, 6, 6]),
        ),
    )

    assert attack.resolved_totals["undeadFortitudeTriggered"] is True
    assert attack.resolved_totals["undeadFortitudeSuccess"] is True
    assert attack.resolved_totals["undeadFortitudeDc"] == attack.damage_details.final_damage_to_hp + 5
    assert "Undead Fortitude succeeds" in " ".join(attack.condition_deltas)


def test_giant_fire_beetle_fire_resistance_halves_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("fire-beetle-defense", "giant_fire_beetle"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="fire",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 4
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 3
    assert encounter.units["E1"].current_hp == 1


def test_giant_badger_poison_resistance_halves_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("giant-badger-defense", "giant_badger"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="poison",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 4
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 3
    assert encounter.units["E1"].current_hp == 12


def test_polar_bear_cold_resistance_halves_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("polar-bear-defense", "polar_bear"))

    damage_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="cold",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 4
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 3
    assert encounter.units["E1"].current_hp == 39


def test_animated_armor_poison_and_psychic_immunities_prevent_damage() -> None:
    encounter = create_encounter(build_monster_benchmark_config("animated-armor-defense", "animated_armor"))

    poison_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="poison",
                raw_rolls=[8],
                adjusted_rolls=[8],
                subtotal=8,
                flat_modifier=0,
                total_damage=8,
            )
        ],
        False,
    )
    psychic_result = apply_damage(
        encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="psychic",
                raw_rolls=[8],
                adjusted_rolls=[8],
                subtotal=8,
                flat_modifier=0,
                total_damage=8,
            )
        ],
        False,
    )

    assert poison_result.resisted_damage == 8
    assert poison_result.final_total_damage == 0
    assert psychic_result.resisted_damage == 8
    assert psychic_result.final_total_damage == 0
    assert encounter.units["E1"].current_hp == 33


def test_lemure_damage_defenses_apply_by_type() -> None:
    cold_encounter = create_encounter(build_monster_benchmark_config("lemure-cold", "lemure"))
    fire_encounter = create_encounter(build_monster_benchmark_config("lemure-fire", "lemure"))
    poison_encounter = create_encounter(build_monster_benchmark_config("lemure-poison", "lemure"))

    cold_result = apply_damage(
        cold_encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="cold",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )
    fire_result = apply_damage(
        fire_encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="fire",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )
    poison_result = apply_damage(
        poison_encounter,
        "E1",
        [
            DamageComponentResult(
                damage_type="poison",
                raw_rolls=[7],
                adjusted_rolls=[7],
                subtotal=7,
                flat_modifier=0,
                total_damage=7,
            )
        ],
        False,
    )

    assert cold_result.resisted_damage == 4
    assert cold_result.final_total_damage == 3
    assert fire_result.resisted_damage == 7
    assert fire_result.final_total_damage == 0
    assert poison_result.resisted_damage == 7
    assert poison_result.final_total_damage == 0


def test_static_resistance_and_vulnerability_cancel_each_other() -> None:
    encounter = create_encounter(build_barbarian_config("static-defense-cancel"))
    target = encounter.units["F1"]
    target.damage_resistances = ("fire",)
    target.damage_vulnerabilities = ("fire",)

    damage_result = apply_damage(
        encounter,
        "F1",
        [
            DamageComponentResult(
                damage_type="fire",
                raw_rolls=[9],
                adjusted_rolls=[9],
                subtotal=9,
                flat_modifier=0,
                total_damage=9,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 0
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 9
    assert encounter.units["F1"].current_hp == 6


def test_rage_and_static_resistance_do_not_stack_beyond_one_halving() -> None:
    encounter = create_encounter(build_barbarian_config("rage-static-resistance"))
    target = encounter.units["F1"]
    target.damage_resistances = ("slashing",)
    target.temporary_hit_points = 0
    target.temporary_effects.append(RageEffect(kind="rage", source_id="F1", damage_bonus=2, remaining_rounds=99))

    damage_result = apply_damage(
        encounter,
        "F1",
        [
            DamageComponentResult(
                damage_type="slashing",
                raw_rolls=[9],
                adjusted_rolls=[9],
                subtotal=9,
                flat_modifier=0,
                total_damage=9,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 5
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 4
    assert encounter.units["F1"].current_hp == 11


def test_rage_resistance_and_static_vulnerability_cancel_each_other() -> None:
    encounter = create_encounter(build_barbarian_config("rage-static-vulnerability"))
    target = encounter.units["F1"]
    target.damage_vulnerabilities = ("slashing",)
    target.temporary_hit_points = 0
    target.temporary_effects.append(RageEffect(kind="rage", source_id="F1", damage_bonus=2, remaining_rounds=99))

    damage_result = apply_damage(
        encounter,
        "F1",
        [
            DamageComponentResult(
                damage_type="slashing",
                raw_rolls=[9],
                adjusted_rolls=[9],
                subtotal=9,
                flat_modifier=0,
                total_damage=9,
            )
        ],
        False,
    )

    assert damage_result.resisted_damage == 0
    assert damage_result.amplified_damage == 0
    assert damage_result.final_total_damage == 9
    assert encounter.units["F1"].current_hp == 6


def test_prone_on_hit_honors_max_target_size() -> None:
    large_encounter = create_encounter(build_monster_benchmark_config("brown-bear-prone-large", "brown_bear"))
    large_encounter.units["E1"].position = GridPosition(x=5, y=5)
    large_encounter.units["F1"].position = GridPosition(x=7, y=5)

    large_attack, _ = resolve_attack(
        large_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="claw",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2]),
        ),
    )

    huge_encounter = create_encounter(build_monster_benchmark_config("brown-bear-prone-huge", "brown_bear"))
    huge_encounter.units["E1"].position = GridPosition(x=5, y=5)
    huge_encounter.units["F1"].position = GridPosition(x=7, y=5)
    huge_encounter.units["F1"].size_category = "huge"

    huge_attack, _ = resolve_attack(
        huge_encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="claw",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2]),
        ),
    )

    assert large_attack.damage_details.attack_riders_applied == ["prone_on_hit"]
    assert large_encounter.units["F1"].conditions.prone is True
    assert huge_attack.damage_details.attack_riders_applied is None
    assert huge_encounter.units["F1"].conditions.prone is False


def test_advantage_against_self_grappled_target_requires_the_same_attacker() -> None:
    encounter = create_encounter(build_monster_benchmark_config("bugbear-self-grapple-advantage", "bugbear_warrior"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].temporary_effects.append(GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=12))

    advantaged_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="light_hammer",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[2, 17], damage_rolls=[2, 3, 2]),
        ),
    )

    encounter.units["F1"].temporary_effects = [GrappledEffect(kind="grappled_by", source_id="E2", escape_dc=12)]
    normal_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="light_hammer",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[17], damage_rolls=[2, 3, 2]),
        ),
    )

    assert advantaged_attack.resolved_totals["attackMode"] == "advantage"
    assert "self_grappled_target" in advantaged_attack.raw_rolls["advantageSources"]
    assert normal_attack.resolved_totals["attackMode"] == "normal"
    assert "self_grappled_target" not in normal_attack.raw_rolls["advantageSources"]


def test_parry_only_triggers_when_plus_two_ac_changes_a_melee_hit_to_a_miss() -> None:
    encounter = create_encounter(build_monster_benchmark_config("bandit-captain-parry", "bandit_captain"))
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
    assert melee_attack.resolved_totals["targetAc"] == encounter.units["E1"].ac + 2
    assert melee_attack.resolved_totals["hit"] is False
    assert encounter.units["E1"].reaction_available is False

    ranged_encounter = create_encounter(build_monster_benchmark_config("bandit-captain-no-parry", "bandit_captain"))
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


def test_redirect_attack_swaps_targets_rechecks_ac_and_does_not_chain() -> None:
    encounter = create_encounter(build_monster_benchmark_config("goblin-boss-redirect", "goblin_boss"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=6, y=6)
    encounter.units["E2"].ac = 19
    melee_weapon_id = next(weapon_id for weapon_id, weapon in encounter.units["F1"].attacks.items() if weapon.kind == "melee")
    hit_roll = encounter.units["E1"].ac - encounter.units["F1"].attacks[melee_weapon_id].attack_bonus

    events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": melee_weapon_id},
        step_overrides=[AttackRollOverrides(attack_rolls=[hit_roll], damage_rolls=[6])],
    )
    attack = next(event for event in events if event.event_type == "attack")

    assert events[0].event_type == "phase_change"
    assert events[0].resolved_totals["reaction"] == "redirect_attack"
    assert events[0].resolved_totals["redirectedTargetId"] == "E2"
    assert attack.target_ids == ["E2"]
    assert attack.resolved_totals["originalTargetId"] == "E1"
    assert attack.resolved_totals["reactionActorId"] == "E1"
    assert attack.resolved_totals["attackReaction"] == "redirect_attack"
    assert attack.resolved_totals["targetAc"] == 19
    assert attack.resolved_totals["hit"] is False
    assert encounter.units["E1"].position == GridPosition(x=6, y=6)
    assert encounter.units["E2"].position == GridPosition(x=6, y=5)
    assert encounter.units["E1"].reaction_available is False
    assert encounter.units["E2"].reaction_available is True
    assert sum(
        1 for event in events if event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "redirect_attack"
    ) == 1


def test_rampage_requires_a_bloodied_target_and_respects_its_one_use_limit() -> None:
    blocked_encounter = create_encounter(build_monster_benchmark_config("gnoll-rampage-blocked", "gnoll_warrior"))
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

    encounter = create_encounter(build_monster_benchmark_config("gnoll-rampage-fired", "gnoll_warrior"))
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
    follow_up_attacks = [event for event in events if event.event_type == "attack"]

    assert any(
        event.event_type == "phase_change" and event.resolved_totals.get("reaction") == "rampage"
        for event in events
    )
    assert len(follow_up_attacks) == 2
    assert follow_up_attacks[0].target_ids == ["F1"]
    assert follow_up_attacks[1].target_ids == ["F3"]
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


def test_rage_bonus_damage_applies_to_strength_based_greataxe_and_handaxe_attacks() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-rage-damage"))
    resolve_bonus_action(encounter, "F1", {"kind": "rage", "timing": "before_action"})
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=11, y=5)

    greataxe_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greataxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[6]),
        ),
    )
    encounter.units["F1"].position = GridPosition(x=8, y=5)

    handaxe_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E2",
            weapon_id="handaxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[4]),
        ),
    )

    assert greataxe_attack.damage_details.total_damage == 11
    assert handaxe_attack.damage_details.total_damage == 9


def test_cleave_follow_up_omits_ability_modifier_damage() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-cleave"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E2"].position = GridPosition(x=6, y=6)

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greataxe"},
        step_overrides=[AttackRollOverrides(attack_rolls=[14], damage_rolls=[7])],
    )

    assert len([event for event in attack_events if event.event_type == "attack"]) == 2
    assert attack_events[0].damage_details.mastery_applied == "cleave"
    assert attack_events[1].damage_details.weapon_id == "greataxe"
    assert attack_events[1].damage_details.flat_modifier == 0


def test_vex_grants_and_consumes_next_attack_advantage_on_same_target() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-vex"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)

    first_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="handaxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[4]),
        ),
    )
    second_attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="handaxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[3]),
        ),
    )

    assert first_attack.damage_details.mastery_applied == "vex"
    assert second_attack.resolved_totals["attackMode"] == "advantage"
    assert "vex" in second_attack.raw_rolls["advantageSources"]
    assert "F1's vex advantage is consumed on this attack roll." in second_attack.condition_deltas
    assert any(effect.kind == "vex" for effect in encounter.units["F1"].temporary_effects) is True


def test_vex_expires_at_end_of_attackers_next_turn_if_unused() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-vex-expiry"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=9, y=5)

    resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="handaxe",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[4]),
        ),
    )

    encounter.round = 1
    expire_turn_end_effects(encounter, "F1")
    assert any(effect.kind == "vex" for effect in encounter.units["F1"].temporary_effects) is True

    encounter.round = 2
    expire_turn_end_effects(encounter, "F1")
    assert any(effect.kind == "vex" for effect in encounter.units["F1"].temporary_effects) is False


def test_rage_bonus_action_can_extend_an_existing_rage() -> None:
    encounter = create_encounter(build_barbarian_config("barbarian-rage-upkeep"))
    resolve_bonus_action(encounter, "F1", {"kind": "rage", "timing": "before_action"})

    rage_event = resolve_bonus_action(encounter, "F1", {"kind": "rage", "timing": "after_action"})

    assert rage_event is not None
    assert encounter.units["F1"].resources.rage_uses == 1
    assert encounter.units["F1"]._rage_extended_this_turn is True


def test_barbarian_level2_reckless_attack_is_suspended_by_default() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-reckless-attack"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["F1"]._reckless_attack_available_this_turn = True

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greataxe"},
        step_overrides=[AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[7])],
    )

    assert attack_events[0].event_type == "attack"
    assert any(effect.kind == "reckless_attack" for effect in encounter.units["F1"].temporary_effects) is False
    assert attack_events[0].resolved_totals["attackMode"] == "normal"
    assert "reckless_attack" not in attack_events[0].raw_rolls.get("advantageSources", [])


def test_barbarian_level2_reckless_attack_grants_attackers_advantage_against_the_barbarian() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-reckless-defense"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["F1"].temporary_effects.append(
        RecklessAttackEffect(kind="reckless_attack", source_id="F1", expires_at_turn_start_of="F1")
    )

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert "target_reckless" in attack_event.raw_rolls["advantageSources"]


def test_barbarian_level2_reckless_attack_applies_to_strength_based_opportunity_attacks() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-reckless-opportunity"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["F1"].temporary_effects.append(
        RecklessAttackEffect(kind="reckless_attack", source_id="F1", expires_at_turn_start_of="F1")
    )

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="greataxe",
            savage_attacker_available=False,
            is_opportunity_attack=True,
            overrides=AttackRollOverrides(attack_rolls=[5, 17], damage_rolls=[8]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert attack_event.resolved_totals["opportunityAttack"] is True
    assert "reckless_attack" in attack_event.raw_rolls["advantageSources"]


def test_barbarian_level2_reckless_attack_expires_at_the_start_of_the_next_turn() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-reckless-expiry"))
    encounter.units["F1"].temporary_effects.append(
        RecklessAttackEffect(kind="reckless_attack", source_id="F1", expires_at_turn_start_of="F1")
    )

    expiry_events = expire_turn_end_effects(encounter, "E1")
    assert any(effect.kind == "reckless_attack" for effect in encounter.units["F1"].temporary_effects) is True
    assert expiry_events == []

    start_events = expire_turn_effects(encounter, "F1")

    assert any(effect.kind == "reckless_attack" for effect in encounter.units["F1"].temporary_effects) is False
    assert any(event.event_type == "effect_expired" for event in start_events)


def test_barbarian_saving_throw_resolver_supports_normal_advantage_and_disadvantage() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-save-resolver"))

    normal = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F1",
            ability="wis",
            dc=10,
            reason="baseline",
            overrides=SavingThrowOverrides(save_rolls=[12]),
        ),
    )
    advantage = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F1",
            ability="wis",
            dc=10,
            reason="advantage probe",
            advantage_sources=["test_advantage"],
            overrides=SavingThrowOverrides(save_rolls=[4, 13]),
        ),
    )
    disadvantage = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F1",
            ability="wis",
            dc=10,
            reason="disadvantage probe",
            disadvantage_sources=["test_disadvantage"],
            overrides=SavingThrowOverrides(save_rolls=[4, 13]),
        ),
    )

    assert normal.resolved_totals["saveMode"] == "normal"
    assert normal.resolved_totals["selectedRoll"] == 12
    assert advantage.resolved_totals["saveMode"] == "advantage"
    assert advantage.resolved_totals["selectedRoll"] == 13
    assert disadvantage.resolved_totals["saveMode"] == "disadvantage"
    assert disadvantage.resolved_totals["selectedRoll"] == 4


def test_barbarian_level2_danger_sense_grants_advantage_on_dexterity_saves_while_conscious() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-danger-sense"))

    saving_throw_event = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F1",
            ability="dex",
            dc=12,
            reason="falling rubble",
            overrides=SavingThrowOverrides(save_rolls=[4, 15]),
        ),
    )

    assert saving_throw_event.event_type == "saving_throw"
    assert saving_throw_event.resolved_totals["saveMode"] == "advantage"
    assert saving_throw_event.resolved_totals["selectedRoll"] == 15
    assert saving_throw_event.resolved_totals["total"] == 16
    assert saving_throw_event.resolved_totals["success"] is True
    assert "danger_sense" in saving_throw_event.raw_rolls["advantageSources"]


def test_barbarian_level2_danger_sense_does_not_affect_non_dexterity_saves() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-danger-sense-non-dex"))

    saving_throw_event = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F1",
            ability="con",
            dc=12,
            reason="poison cloud",
            overrides=SavingThrowOverrides(save_rolls=[4, 15]),
        ),
    )

    assert saving_throw_event.resolved_totals["saveMode"] == "normal"
    assert saving_throw_event.raw_rolls["advantageSources"] == []


def test_barbarian_level2_danger_sense_is_suppressed_while_unconscious() -> None:
    encounter = create_encounter(build_level2_barbarian_config("barbarian-danger-sense-unconscious"))
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True

    saving_throw_event = resolve_saving_throw(
        encounter,
        ResolveSavingThrowArgs(
            actor_id="F1",
            ability="dex",
            dc=12,
            reason="falling rubble",
            overrides=SavingThrowOverrides(save_rolls=[4, 15]),
        ),
    )

    assert saving_throw_event.resolved_totals["saveMode"] == "normal"
    assert saving_throw_event.raw_rolls["advantageSources"] == []


def test_rogue_hide_success_applies_hidden_effect() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hide-success"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    defeat_other_enemies(encounter, "E4")

    hide_event = attempt_hide(encounter, "F1", override_roll=10)

    assert hide_event.event_type == "phase_change"
    assert hide_event.resolved_totals["success"] is True
    assert hide_event.resolved_totals["targetDc"] == 15
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects)


def test_rogue_hide_failure_does_not_apply_hidden_effect() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hide-failure"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    defeat_other_enemies(encounter, "E4")

    hide_event = attempt_hide(encounter, "F1", override_roll=1)

    assert hide_event.event_type == "phase_change"
    assert hide_event.resolved_totals["success"] is False
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False


def test_resolve_bonus_action_hide_matches_attempt_hide_helper() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hide-bonus-action"))
    mirror = create_encounter(build_level2_rogue_config("rogue-hide-bonus-action"))

    for state in (encounter, mirror):
        state.units["F1"].position = GridPosition(x=4, y=8)
        state.units["F1"].combat_skill_modifiers["stealth"] = 20
        state.units["E4"].position = GridPosition(x=8, y=8)
        defeat_other_enemies(state, "E4")

    bonus_event = resolve_bonus_action(encounter, "F1", {"kind": "hide", "timing": "before_action"})
    helper_event = attempt_hide(mirror, "F1")

    assert bonus_event is not None
    assert bonus_event.model_dump() == helper_event.model_dump()
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects)
    assert any(effect.kind == "hidden" for effect in mirror.units["F1"].temporary_effects)


def test_attempt_hide_skips_when_the_actor_is_already_hidden() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hide-already-hidden"))
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))

    hide_event = attempt_hide(encounter, "F1", override_roll=20)

    assert hide_event.event_type == "skip"
    assert hide_event.resolved_totals["reason"] == "Already hidden."
    assert len([effect for effect in encounter.units["F1"].temporary_effects if effect.kind == "hidden"]) == 1


def test_hidden_grants_attack_advantage_enables_sneak_attack_and_breaks_on_attack() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hidden-attack"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    defeat_other_enemies(encounter, "E4")

    attempt_hide(encounter, "F1", override_roll=10)
    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[4], advantage_damage_rolls=[]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert "hidden" in attack_event.raw_rolls["advantageSources"]
    assert any(component.damage_type == "precision" for component in attack_event.damage_details.damage_components)
    assert "F1 is no longer hidden after attacking." in attack_event.condition_deltas
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False


def test_hidden_grants_disadvantage_to_attacks_against_the_rogue_and_breaks_on_damage() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hidden-defense"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    defeat_other_enemies(encounter, "E4")

    attempt_hide(encounter, "F1", override_roll=10)
    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E4",
            target_id="F1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[18, 17], damage_rolls=[4]),
        ),
    )

    assert attack_event.event_type == "attack"
    assert attack_event.target_ids == ["F1"]
    assert attack_event.resolved_totals["attackMode"] == "disadvantage"
    assert "target_hidden" in attack_event.raw_rolls["disadvantageSources"]
    assert "F1 is no longer hidden after taking damage." in attack_event.condition_deltas
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False


def test_hidden_advantage_cancels_adjacent_enemy_ranged_disadvantage() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hidden-cancel"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=4, y=9)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id in {"E1", "E4"}:
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))
    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[12], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "normal"
    assert "hidden" in attack_event.raw_rolls["advantageSources"]
    assert "adjacent_enemy" in attack_event.raw_rolls["disadvantageSources"]


def test_hidden_advantage_cancels_long_range_disadvantage_for_ranged_attacks() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hidden-long-range-cancel"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=11, y=1)
    encounter.units["F1"].attacks["shortbow"].range = WeaponRange(normal=30, long=60)
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[12, 4], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "normal"
    assert "hidden" in attack_event.raw_rolls["advantageSources"]
    assert "long_range" in attack_event.raw_rolls["disadvantageSources"]


def test_hidden_expires_at_the_start_of_the_rogues_next_turn() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hidden-expiry"))
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))

    start_events = expire_turn_effects(encounter, "F1")

    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False
    assert any(event.event_type == "effect_expired" for event in start_events)


def test_hidden_is_cleared_when_cover_or_spacing_no_longer_supports_it() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-hidden-invalidated"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E4":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))
    encounter.units["E4"].position = GridPosition(x=4, y=9)

    condition_deltas = clear_invalid_hidden_effects(encounter)

    assert condition_deltas == ["F1 is no longer hidden."]
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False


def test_execute_decision_hides_before_attacking_when_the_turn_plan_calls_for_it() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-execute-before-hide"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].combat_skill_modifiers["stealth"] = 20
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(encounter, "E4")

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            bonus_action={"kind": "hide", "timing": "before_action"},
            action={"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"},
        ),
        events,
        rescue_mode=False,
    )

    assert [event.event_type for event in events] == ["phase_change", "attack"]
    assert events[0].resolved_totals["hidden"] is True
    assert events[1].resolved_totals["attackMode"] == "advantage"
    assert "hidden" in events[1].raw_rolls["advantageSources"]


def test_execute_decision_can_hide_after_attacking_and_stay_hidden_until_enemy_pressure() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-execute-after-hide"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].combat_skill_modifiers["stealth"] = 20
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(encounter, "E4")

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"},
            bonus_action={"kind": "hide", "timing": "after_action"},
        ),
        events,
        rescue_mode=False,
    )

    assert [event.event_type for event in events] == ["attack", "phase_change"]
    assert events[1].resolved_totals["hidden"] is True
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is True

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E4",
            target_id="F1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[18, 17], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "disadvantage"
    assert "target_hidden" in attack_event.raw_rolls["disadvantageSources"]


def test_execute_movement_clears_hidden_when_cover_is_lost() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-move-breaks-hide-cover"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))
    defeat_other_enemies(encounter, "E4")

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            pre_action_movement=MovementPlan(
                path=[GridPosition(x=4, y=8), GridPosition(x=4, y=7)],
                mode="move",
            ),
            action={"kind": "skip", "reason": "Probe hidden cleanup."},
        ),
        events,
        rescue_mode=False,
    )

    move_event = next(event for event in events if event.event_type == "move")

    assert move_event.condition_deltas == ["F1 is no longer hidden."]
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False


def test_execute_movement_clears_hidden_when_the_rogue_moves_into_enemy_adjacency() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-move-breaks-hide-adjacency"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))
    defeat_other_enemies(encounter, "E4")

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            pre_action_movement=MovementPlan(
                path=[
                    GridPosition(x=4, y=8),
                    GridPosition(x=4, y=7),
                    GridPosition(x=5, y=7),
                    GridPosition(x=6, y=7),
                    GridPosition(x=7, y=7),
                ],
                mode="move",
            ),
            action={"kind": "skip", "reason": "Probe adjacency cleanup."},
        ),
        events,
        rescue_mode=False,
    )

    move_event = next(event for event in events if event.event_type == "move")

    assert move_event.condition_deltas == ["F1 is no longer hidden."]
    assert encounter.units["F1"].position == GridPosition(x=7, y=7)
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects) is False


def test_assassin_initiative_uses_advantage_deterministically() -> None:
    seed = "rogue-assassin-initiative"
    rng = normalize_seed(seed)
    first_roll, rng = roll_die(rng, 20)
    second_roll, _ = roll_die(rng, 20)
    encounter = create_encounter(build_level3_rogue_config(seed))

    assert encounter.units["F1"].initiative_score == max(first_roll, second_roll) + 3


def test_assassinate_grants_round_one_advantage_against_targets_that_have_not_acted() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-assassinate-advantage"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[3, 15], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert attack_event.resolved_totals["selectedRoll"] == 15
    assert "assassinate" in attack_event.raw_rolls["advantageSources"]


def test_assassinate_advantage_stops_after_target_turn_or_round_one() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-assassinate-no-advantage"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.initiative_order = ["E4", "F1"]
    encounter.active_combatant_index = 1
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    after_target_turn, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    encounter.round = 2
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    after_round_one, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert "assassinate" not in after_target_turn.raw_rolls["advantageSources"]
    assert "assassinate" not in after_round_one.raw_rolls["advantageSources"]


def test_assassinate_adds_flat_rogue_level_damage_to_round_one_sneak_attack() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-assassinate-damage"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.units["E4"].current_hp = 40
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15, 12], damage_rolls=[4]),
        ),
    )

    assassinate_component = next(
        component
        for component in attack_event.damage_details.damage_components
        if component.flat_modifier == 3 and component.raw_rolls == []
    )

    assert attack_event.resolved_totals["assassinateDamageBonus"] == 3
    assert assassinate_component.total_damage == 3
    assert "F1 applies Assassinate for +3 damage." in attack_event.condition_deltas


def test_assassinate_damage_does_not_double_on_critical_hits() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-assassinate-crit"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.units["E4"].current_hp = 40
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[20, 5], damage_rolls=[4]),
        ),
    )

    assassinate_component = next(
        component
        for component in attack_event.damage_details.damage_components
        if component.flat_modifier == 3 and component.raw_rolls == []
    )

    assert attack_event.resolved_totals["critical"] is True
    assert assassinate_component.total_damage == 3


def test_assassinate_damage_requires_sneak_attack() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-assassinate-no-sneak"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.units["F1"].feature_ids.remove("sneak_attack")
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15, 12], damage_rolls=[4]),
        ),
    )

    assert "assassinateDamageBonus" not in attack_event.resolved_totals
    assert all(component.damage_type != "precision" for component in attack_event.damage_details.damage_components)


def test_steady_aim_grants_advantage_and_is_consumed_by_the_next_attack() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-steady-aim-advantage"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.round = 2
    defeat_other_enemies(encounter, "E4")

    steady_event = resolve_bonus_action(encounter, "F1", {"kind": "steady_aim", "timing": "before_action"})
    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[3, 15], damage_rolls=[4]),
        ),
    )

    assert steady_event is not None
    assert steady_event.event_type == "phase_change"
    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert "steady_aim" in attack_event.raw_rolls["advantageSources"]
    assert "F1's Steady Aim is consumed on this attack roll." in attack_event.condition_deltas
    assert encounter.units["F1"]._steady_aim_active_this_turn is False


def test_execute_decision_rejects_steady_aim_when_movement_is_planned() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-steady-aim-movement-reject"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    defeat_other_enemies(encounter, "E4")
    events: list = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            bonus_action={"kind": "steady_aim", "timing": "before_action"},
            pre_action_movement=MovementPlan(
                path=[GridPosition(x=1, y=1), GridPosition(x=2, y=1)],
                mode="move",
            ),
            action={"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"},
        ),
        events,
        rescue_mode=False,
    )

    assert [event.event_type for event in events] == ["skip"]
    assert events[0].resolved_totals["reason"] == "Steady Aim cannot be used on a turn with planned movement."
    assert encounter.units["F1"]._steady_aim_active_this_turn is False


def test_after_movement_hide_resolves_after_post_action_movement() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-after-movement-hide"))
    encounter.units["F1"].position = GridPosition(x=3, y=8)
    encounter.units["F1"].combat_skill_modifiers["stealth"] = 20
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    encounter.units["E4"].current_hp = 100
    defeat_other_enemies(encounter, "E4")
    events: list = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"},
            post_action_movement=MovementPlan(
                path=[
                    GridPosition(x=3, y=8),
                    GridPosition(x=2, y=7),
                    GridPosition(x=1, y=7),
                ],
                mode="move",
            ),
            bonus_action={"kind": "hide", "timing": "after_movement"},
        ),
        events,
        rescue_mode=False,
    )

    event_types = [event.event_type for event in events]
    assert event_types == ["attack", "move", "phase_change"]
    assert events[-1].raw_rolls["stealthRolls"]
    assert events[-1].resolved_totals["success"] is True
    assert any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects)


def test_after_movement_hide_validates_the_final_square_after_interrupted_movement() -> None:
    encounter = create_encounter(build_level3_rogue_config("rogue-after-movement-hide-invalid"))
    encounter.units["F1"].position = GridPosition(x=3, y=8)
    encounter.units["F1"].combat_skill_modifiers["stealth"] = 20
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    encounter.units["E4"].current_hp = 100
    defeat_other_enemies(encounter, "E4")
    events: list = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"},
            post_action_movement=MovementPlan(
                path=[
                    GridPosition(x=3, y=8),
                    GridPosition(x=3, y=7),
                ],
                mode="move",
            ),
            bonus_action={"kind": "hide", "timing": "after_movement"},
        ),
        events,
        rescue_mode=False,
    )

    assert [event.event_type for event in events] == ["attack", "move", "skip"]
    assert events[-1].resolved_totals["reason"] == "Cannot hide from the current position."
    assert not any(effect.kind == "hidden" for effect in encounter.units["F1"].temporary_effects)


def test_after_movement_disengage_does_not_retroactively_prevent_opportunity_attacks() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-after-movement-disengage-no-retroactive"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")
    events: list = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "skip", "reason": "Testing after-movement Disengage timing."},
            post_action_movement=MovementPlan(
                path=[
                    GridPosition(x=5, y=5),
                    GridPosition(x=4, y=5),
                    GridPosition(x=3, y=5),
                ],
                mode="move",
            ),
            bonus_action={"kind": "disengage", "timing": "after_movement"},
        ),
        events,
        rescue_mode=False,
    )

    assert any(event.event_type == "attack" and event.actor_id == "E1" for event in events)
    move_event = next(event for event in events if event.event_type == "move")
    assert move_event.resolved_totals["disengageApplied"] is False


def test_sharpshooter_shortbow_ignores_half_cover_ac_bonus() -> None:
    encounter = create_encounter(build_level4_rogue_config("rogue-sharpshooter-cover"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[9], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.resolved_totals["coverAcBonus"] == 0
    assert attack_event.resolved_totals["targetAc"] == encounter.units["E4"].ac
    assert attack_event.resolved_totals["sharpshooterApplied"] is True
    assert attack_event.resolved_totals["sharpshooterIgnoredCoverAcBonus"] == 2


def test_sharpshooter_shortbow_ignores_long_range_disadvantage_but_not_range_legality() -> None:
    encounter = create_encounter(build_level4_rogue_config("rogue-sharpshooter-long-range"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=11, y=1)
    encounter.units["F1"].attacks["shortbow"].range = WeaponRange(normal=30, long=60)
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )
    encounter.units["E4"].position = GridPosition(x=14, y=1)
    out_of_range_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "normal"
    assert "long_range" not in attack_event.raw_rolls["disadvantageSources"]
    assert attack_event.raw_rolls["sharpshooterIgnoredDisadvantageSources"] == ["long_range"]
    assert attack_event.resolved_totals["sharpshooterApplied"] is True
    assert out_of_range_event.event_type == "skip"
    assert out_of_range_event.resolved_totals["reason"] == "Shortbow is not in range."


def test_sharpshooter_shortbow_ignores_adjacent_enemy_disadvantage() -> None:
    encounter = create_encounter(build_level4_rogue_config("rogue-sharpshooter-adjacent"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    assert attack_event.resolved_totals["attackMode"] == "normal"
    assert "adjacent_enemy" not in attack_event.raw_rolls["disadvantageSources"]
    assert attack_event.raw_rolls["sharpshooterIgnoredDisadvantageSources"] == ["adjacent_enemy"]
    assert attack_event.resolved_totals["sharpshooterApplied"] is True


def test_sharpshooter_does_not_apply_to_spells_melee_weapons_or_level3_rogues() -> None:
    wizard = create_encounter(build_wizard_config("wizard-fire-bolt-not-sharpshooter"))
    defeat_other_enemies(wizard, "E4")
    wizard.units["F1"].feature_ids.append("sharpshooter")
    wizard.units["F1"].position = GridPosition(x=4, y=8)
    wizard.units["E4"].position = GridPosition(x=8, y=8)
    spell_events = resolve_cast_spell_action(
        wizard,
        "F1",
        {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "E4"},
        overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[6]),
    )
    spell_attack = next(event for event in spell_events if event.event_type == "attack")

    rogue4 = create_encounter(build_level4_rogue_config("rogue-sharpshooter-not-melee"))
    rogue4.units["F1"].position = GridPosition(x=5, y=5)
    rogue4.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(rogue4, "E1")
    melee_attack, _ = resolve_attack(
        rogue4,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortsword",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    rogue3 = create_encounter(build_level3_rogue_config("rogue-level3-no-sharpshooter"))
    rogue3.round = 2
    rogue3.units["F1"].position = GridPosition(x=4, y=8)
    rogue3.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(rogue3, "E4")
    rogue3_attack, _ = resolve_attack(
        rogue3,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[10], damage_rolls=[4]),
        ),
    )

    assert spell_attack.resolved_totals["coverAcBonus"] == 2
    assert "sharpshooterApplied" not in spell_attack.resolved_totals
    assert "sharpshooterApplied" not in melee_attack.resolved_totals
    assert rogue3_attack.resolved_totals["coverAcBonus"] == 2
    assert rogue3_attack.resolved_totals["hit"] is False
    assert "sharpshooterApplied" not in rogue3_attack.resolved_totals


def test_level4_assassinate_damage_uses_rogue_level_four() -> None:
    encounter = create_encounter(build_level4_rogue_config("rogue-level4-assassinate-damage"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.units["E4"].current_hp = 40
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E4",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15, 12], damage_rolls=[4]),
        ),
    )

    assassinate_component = next(
        component
        for component in attack_event.damage_details.damage_components
        if component.flat_modifier == 4 and component.raw_rolls == []
    )

    assert attack_event.resolved_totals["assassinateDamageBonus"] == 4
    assert assassinate_component.total_damage == 4
    assert any(component.damage_type == "precision" and len(component.raw_rolls) == 2 for component in attack_event.damage_details.damage_components)


def test_level5_rogue_shortbow_sneak_attack_rolls_three_d6() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-sneak-attack"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["F2"].position = GridPosition(x=3, y=2)
    encounter.units["E1"].position = GridPosition(x=3, y=1)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    sneak_component = next(
        component for component in attack_event.damage_details.damage_components if component.damage_type == "precision"
    )

    assert len(sneak_component.raw_rolls) == 3
    assert "cunningStrikeId" not in attack_event.resolved_totals


def test_cunning_strike_spends_one_sneak_attack_die_when_explicitly_selected() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-cunning-poison"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["F2"].position = GridPosition(x=3, y=2)
    encounter.units["E1"].position = GridPosition(x=3, y=1)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            cunning_strike_id="poison",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4], save_rolls=[1]),
        ),
    )

    sneak_component = next(
        component for component in attack_event.damage_details.damage_components if component.damage_type == "precision"
    )

    assert len(sneak_component.raw_rolls) == 2
    assert attack_event.resolved_totals["cunningStrikeId"] == "poison"
    assert attack_event.resolved_totals["cunningStrikeCostD6"] == 1
    assert attack_event.resolved_totals["sneakAttackDiceSpent"] == 1
    assert attack_event.resolved_totals["sneakAttackDiceRolled"] == 2
    assert attack_event.resolved_totals["cunningStrikeSaveDc"] == 15
    assert attack_event.resolved_totals["cunningStrikeSaveSuccess"] is False
    assert any(effect.kind == "poisoned" for effect in encounter.units["E1"].temporary_effects)


def test_cunning_strike_does_not_spend_on_miss_or_non_sneak_attack_hit() -> None:
    miss = create_encounter(build_level5_rogue_config("rogue-level5-cunning-miss"))
    miss.round = 2
    miss.units["F1"].position = GridPosition(x=1, y=1)
    miss.units["F2"].position = GridPosition(x=3, y=2)
    miss.units["E1"].position = GridPosition(x=3, y=1)
    defeat_other_enemies(miss, "E1")

    miss_event, _ = resolve_attack(
        miss,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            cunning_strike_id="poison",
            overrides=AttackRollOverrides(attack_rolls=[1], damage_rolls=[4], save_rolls=[1]),
        ),
    )

    no_sneak = create_encounter(build_level5_rogue_config("rogue-level5-cunning-no-sneak"))
    no_sneak.round = 2
    no_sneak.units["F1"].position = GridPosition(x=1, y=1)
    no_sneak.units["E1"].position = GridPosition(x=3, y=1)
    defeat_other_enemies(no_sneak, "E1")

    no_sneak_event, _ = resolve_attack(
        no_sneak,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            cunning_strike_id="poison",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4], save_rolls=[1]),
        ),
    )

    assert "cunningStrikeId" not in miss_event.resolved_totals
    assert "cunningStrikeId" not in no_sneak_event.resolved_totals


def test_trip_cunning_strike_knocks_eligible_failed_save_target_prone() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-cunning-trip"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["F2"].position = GridPosition(x=3, y=2)
    encounter.units["E1"].position = GridPosition(x=3, y=1)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            cunning_strike_id="trip",
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4], save_rolls=[1]),
        ),
    )

    assert encounter.units["E1"].conditions.prone is True
    assert attack_event.resolved_totals["cunningStrikeId"] == "trip"
    assert attack_event.resolved_totals["cunningStrikeSaveAbility"] == "dex"
    assert attack_event.resolved_totals["cunningStrikeConditionApplied"] is True


def test_withdraw_cunning_strike_enables_half_speed_no_opportunity_movement_when_it_hits() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-cunning-withdraw"))
    encounter.round = 2
    encounter.active_combatant_index = encounter.initiative_order.index("F1")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=6)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")
    events = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "attack", "target_id": "E1", "weapon_id": "shortbow", "cunning_strike_id": "withdraw"},
            post_action_movement=MovementPlan(
                path=[
                    GridPosition(x=5, y=5),
                    GridPosition(x=4, y=5),
                    GridPosition(x=3, y=5),
                    GridPosition(x=2, y=5),
                ],
                mode="cunning_withdraw",
            ),
        ),
        events,
        rescue_mode=False,
    )

    move_event = next(event for event in events if event.event_type == "move")
    attack_event = next(event for event in events if event.event_type == "attack" and event.actor_id == "F1")
    assert attack_event.resolved_totals["cunningStrikeId"] == "withdraw"
    assert move_event.resolved_totals["cunningWithdrawApplied"] is True
    assert move_event.resolved_totals["opportunityAttackers"] == []
    assert encounter.units["F1"].position == GridPosition(x=2, y=5)


def test_cunning_strike_critical_doubles_only_remaining_sneak_attack_dice() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-cunning-crit"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["F2"].position = GridPosition(x=3, y=2)
    encounter.units["E1"].position = GridPosition(x=3, y=1)
    encounter.units["E1"].current_hp = 100
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="E1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            cunning_strike_id="withdraw",
            overrides=AttackRollOverrides(attack_rolls=[20], damage_rolls=[4]),
        ),
    )

    sneak_component = next(
        component for component in attack_event.damage_details.damage_components if component.damage_type == "precision"
    )

    assert len(sneak_component.raw_rolls) == 2
    assert sneak_component.total_damage == sneak_component.subtotal * 2


def test_poisoned_effect_imposes_attack_disadvantage_and_can_end_on_turn_end_save() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-poison-save"))
    encounter.round = 2
    encounter.units["E1"].temporary_effects.append(
        PoisonedEffect(kind="poisoned", source_id="F1", save_dc=0, remaining_rounds=10)
    )
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15, 15], damage_rolls=[3]),
        ),
    )

    save_event = resolve_poisoned_end_of_turn_save(encounter, "E1")

    assert attack_event.resolved_totals["attackMode"] == "disadvantage"
    assert "poisoned" in attack_event.raw_rolls["disadvantageSources"]
    assert save_event is not None
    assert save_event.resolved_totals["success"] is True
    assert save_event.resolved_totals["poisonedEnded"] is True
    assert not any(effect.kind == "poisoned" for effect in encounter.units["E1"].temporary_effects)


def test_uncanny_dodge_halves_qualifying_damage_and_consumes_reaction() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-uncanny-dodge"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[6]),
        ),
    )

    assert attack_event.resolved_totals["defenseReaction"] == "uncanny_dodge"
    assert attack_event.resolved_totals["uncannyDodgeDamagePrevented"] == 4
    assert attack_event.resolved_totals["damageAfterUncannyDodge"] == 4
    assert encounter.units["F1"].reaction_available is False
    assert encounter.units["F1"].current_hp == 38


def test_uncanny_dodge_threshold_skips_small_hits_above_half_hp() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-uncanny-skip-small"))
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2]),
        ),
    )

    assert "defenseReaction" not in attack_event.resolved_totals
    assert encounter.units["F1"].reaction_available is True
    assert encounter.units["F1"].current_hp == 38


def test_uncanny_dodge_threshold_uses_small_hits_at_or_below_half_hp() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-uncanny-low-hp"))
    encounter.round = 2
    encounter.units["F1"].current_hp = 21
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[1]),
        ),
    )

    assert attack_event.resolved_totals["defenseReaction"] == "uncanny_dodge"
    assert attack_event.resolved_totals["uncannyDodgeDamagePrevented"] == 2
    assert encounter.units["F1"].current_hp == 20


def test_uncanny_dodge_triggers_when_hit_would_drop_rogue_to_zero() -> None:
    encounter = create_encounter(build_level5_rogue_config("rogue-level5-uncanny-drop"))
    encounter.round = 2
    encounter.units["F1"].current_hp = 4
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E1")

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[2]),
        ),
    )

    assert attack_event.resolved_totals["defenseReaction"] == "uncanny_dodge"
    assert encounter.units["F1"].current_hp == 2


def test_bonus_dash_extends_player_rogue_movement_budget_in_execute_decision() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-bonus-dash-budget"))
    encounter.units["F1"].position = GridPosition(x=1, y=1)

    decision = TurnDecision(
        bonus_action={"kind": "bonus_dash", "timing": "before_action"},
        pre_action_movement=MovementPlan(
            path=[
                GridPosition(x=1, y=1),
                GridPosition(x=2, y=1),
                GridPosition(x=3, y=1),
                GridPosition(x=4, y=1),
                GridPosition(x=5, y=1),
                GridPosition(x=6, y=1),
                GridPosition(x=7, y=1),
                GridPosition(x=8, y=1),
                GridPosition(x=9, y=1),
            ],
            mode="dash",
        ),
        action={"kind": "skip", "reason": "Probe bonus dash movement budget."},
    )
    events: list = []

    execute_decision(encounter, "F1", decision, events, rescue_mode=False)

    move_event = next(event for event in events if event.event_type == "move")

    assert get_total_movement_budget(encounter.units["F1"], decision.action, decision.bonus_action) == 12
    assert move_event.movement_details is not None
    assert move_event.movement_details.distance == 8
    assert move_event.resolved_totals["movementMode"] == "dash"
    assert events[-1].event_type == "skip"
    assert events[-1].resolved_totals["reason"] == "Probe bonus dash movement budget."


def test_disengage_prevents_opportunity_attacks_when_a_rogue_escapes_melee() -> None:
    encounter = create_encounter(build_level2_rogue_config("rogue-disengage-no-opportunity"))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=6, y=5)
    encounter.units["E4"].position = GridPosition(x=10, y=5)
    defeat_other_enemies(encounter, "E1", "E4")

    events: list = []
    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            bonus_action={"kind": "disengage", "timing": "before_action"},
            pre_action_movement=MovementPlan(
                path=[GridPosition(x=5, y=5), GridPosition(x=4, y=5), GridPosition(x=3, y=5)],
                mode="move",
            ),
            action={"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"},
        ),
        events,
        rescue_mode=False,
    )

    move_event = next(event for event in events if event.event_type == "move")
    attack_events = [event for event in events if event.event_type == "attack"]

    assert move_event.resolved_totals["disengageApplied"] is True
    assert move_event.resolved_totals["opportunityAttackers"] == []
    assert len(attack_events) == 1
    assert attack_events[0].actor_id == "F1"


def test_melee_hits_against_unconscious_fighters_are_critical() -> None:
    encounter = create_encounter(EncounterConfig(seed="auto-crit", placements=DEFAULT_POSITIONS))
    encounter.units["G1"].position = GridPosition(x=6, y=5)
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="G1",
            target_id="F1",
            weapon_id="scimitar",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[16, 5], damage_rolls=[1], advantage_damage_rolls=[1]),
        ),
    )

    assert attack.resolved_totals["critical"] is True
    assert encounter.units["F1"].death_save_failures == 2


def test_opportunity_attacks_use_each_enemy_variant_melee_weapon() -> None:
    default_encounter = create_encounter(EncounterConfig(seed="legacy-goblin-oa", placements=DEFAULT_POSITIONS))
    bandit_encounter = create_encounter(EncounterConfig(seed="bandit-oa", enemy_preset_id="bandit_ambush"))
    orc_encounter = create_encounter(EncounterConfig(seed="orc-oa", enemy_preset_id="orc_push"))
    wolf_encounter = create_encounter(EncounterConfig(seed="wolf-oa", enemy_preset_id="wolf_harriers"))

    assert get_opportunity_attack_weapon_id(default_encounter.units["G1"]) == "scimitar"
    assert get_opportunity_attack_weapon_id(bandit_encounter.units["E1"]) == "club"
    assert get_opportunity_attack_weapon_id(bandit_encounter.units["E5"]) == "club"
    assert get_opportunity_attack_weapon_id(orc_encounter.units["E1"]) == "greataxe"
    assert get_opportunity_attack_weapon_id(wolf_encounter.units["E1"]) == "bite"


@pytest.mark.parametrize(
    "enemy_preset_id",
    [
        "goblin_screen",
        "bandit_ambush",
        "mixed_patrol",
        "orc_push",
        "wolf_harriers",
        "marsh_predators",
        "hobgoblin_kill_box",
        "predator_rampage",
        "bugbear_dragnet",
        "deadwatch_phalanx",
        "captains_crossfire",
    ],
)
def test_level2_martial_mixed_party_completes_all_active_enemy_presets(enemy_preset_id: str) -> None:
    result = run_encounter(
        EncounterConfig(
            seed=f"rogue-level2-smoke-{enemy_preset_id}",
            enemy_preset_id=enemy_preset_id,
            player_preset_id="martial_mixed_party",
            player_behavior="smart",
        )
    )
    summary = summarize_encounter(result.final_state)

    assert result.final_state.terminal_state == "complete"
    assert summary.winner in {"fighters", "goblins"}
    assert summary.rounds >= 1
    assert len(result.replay_frames) > 1


def test_fast_summary_path_matches_replay_path_for_single_encounter() -> None:
    config = EncounterConfig(
        seed="fast-summary-parity",
        placements=DEFAULT_POSITIONS,
        player_behavior="balanced",
        monster_behavior="evil",
    )

    fast_summary = run_encounter_summary_fast(config)
    full_summary = summarize_encounter(run_encounter(config.model_copy(deep=True)).final_state)

    assert fast_summary.model_dump(by_alias=True) == full_summary.model_dump(by_alias=True)


def test_large_batch_fast_path_matches_history_capturing_accumulator() -> None:
    config = EncounterConfig(
        seed="large-batch-parity",
        batch_size=11,
        placements=DEFAULT_POSITIONS,
        player_behavior="balanced",
        monster_behavior="balanced",
    )

    with_history = run_single_batch_accumulator(
        config.model_copy(deep=True),
        requested_player_behavior="balanced",
        requested_monster_behavior="balanced",
        capture_history=True,
    )
    without_history = run_single_batch_accumulator(
        config.model_copy(deep=True),
        requested_player_behavior="balanced",
        requested_monster_behavior="balanced",
        capture_history=False,
    )

    assert without_history == with_history


def test_step_finishes_immediately_when_all_fighters_are_already_down() -> None:
    encounter = create_encounter(EncounterConfig(seed="all-down-terminal", placements=DEFAULT_POSITIONS))

    for fighter_id in ("F1", "F2", "F3", "F4"):
        fighter = encounter.units[fighter_id]
        fighter.current_hp = 0
        fighter.conditions.unconscious = True
        fighter.conditions.prone = True
        fighter.stable = False

    result = step_encounter(encounter)

    assert result.done is True
    assert result.state.terminal_state == "complete"
    assert result.state.winner == "goblins"
    assert [event.event_type for event in result.events] == ["phase_change"]
    assert result.events[0].text_summary == "Combat ends. Monsters win."


def test_parallel_batch_path_matches_serial_batch_path() -> None:
    config = EncounterConfig(
        seed="parallel-batch-parity",
        batch_size=20,
        placements=DEFAULT_POSITIONS,
        player_behavior="balanced",
        monster_behavior="combined",
    )

    serial_summary = run_batch_serial(
        config.model_copy(deep=True),
        requested_size=20,
        requested_player_behavior="balanced",
        requested_monster_behavior="combined",
        seed="parallel-batch-parity",
    )
    parallel_summary = run_batch_parallel(
        config.model_copy(deep=True),
        requested_size=20,
        requested_player_behavior="balanced",
        requested_monster_behavior="combined",
        seed="parallel-batch-parity",
    )

    assert parallel_summary.model_dump(by_alias=True) == serial_summary.model_dump(by_alias=True)


def test_batch_execution_plan_uses_parallel_workers_up_to_eight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DND_SIM_BATCH_WORKERS", raising=False)
    monkeypatch.setattr(batch_module.os, "cpu_count", lambda: 32)

    plan = resolve_batch_execution_plan(total_runs=500)

    assert plan.execution_mode == "parallel"
    assert plan.worker_count == 8
    assert plan.total_runs == 500


def test_batch_execution_plan_honors_explicit_worker_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DND_SIM_BATCH_WORKERS", raising=False)

    plan = resolve_batch_execution_plan(total_runs=500, worker_count=4)

    assert plan.execution_mode == "parallel"
    assert plan.worker_count == 4


def test_batch_execution_plan_caps_env_worker_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DND_SIM_BATCH_WORKERS", "99")

    plan = resolve_batch_execution_plan(total_runs=500)

    assert plan.execution_mode == "parallel"
    assert plan.worker_count == 8


def test_batch_execution_plan_forces_serial() -> None:
    plan = resolve_batch_execution_plan(total_runs=500, force_serial=True, worker_count=8)

    assert plan.execution_mode == "serial"
    assert plan.worker_count == 1


def test_action_surge_consumes_its_use_and_cannot_be_used_twice() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-action-surge-spend", placements=DEFAULT_POSITIONS))

    first_event = resolve_action_surge(encounter, "F1")
    second_event = resolve_action_surge(encounter, "F1")

    assert first_event.event_type == "phase_change"
    assert encounter.units["F1"].resources.action_surge_uses == 0
    assert second_event.event_type == "skip"
    assert second_event.text_summary == "F1 skips its turn: No Action Surge uses remain."


def test_attack_plus_action_surge_attack_resolves_two_separate_attack_actions() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-double-attack", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)
    encounter.units["G1"].current_hp = 40

    decision = choose_turn_decision(encounter, "F1")
    events: list = []
    execute_decision(encounter, "F1", decision, events, rescue_mode=False)

    assert decision.action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_intents": [
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
        ],
    }
    assert decision.surged_action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_intents": [
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
        ],
    }
    assert [event.event_type for event in events] == ["attack", "attack", "phase_change", "attack", "attack"]
    attack_target_ids = [event.target_ids for event in events if event.event_type == "attack"]
    assert attack_target_ids[:3] == [["G1"], ["G1"], ["G1"]]
    assert attack_target_ids[3][0].startswith("G")
    assert encounter.units["F1"].resources.action_surge_uses == 0


def test_dash_plus_action_surge_attack_executes_with_between_action_movement() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-dash-attack-turn", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=9, y=1)

    decision = choose_turn_decision(encounter, "F1")
    events: list = []
    execute_decision(encounter, "F1", decision, events, rescue_mode=False)

    assert decision.action["kind"] == "dash"
    assert decision.between_action_movement is not None
    assert decision.surged_action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_intents": [
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
        ],
    }
    assert [event.event_type for event in events] == ["phase_change", "move", "attack", "attack"]
    assert events[1].resolved_totals["movementPhase"] == "between_actions"
    assert encounter.units["F1"].position.model_dump() == {"x": 8, "y": 1}
    assert encounter.units["F1"].resources.action_surge_uses == 0


def test_scout_multiattack_resolves_two_longbow_attacks() -> None:
    encounter = create_encounter(EncounterConfig(seed="scout-multiattack", enemy_preset_id="bandit_ambush", monster_behavior="balanced"))
    encounter.units["E5"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].position = GridPosition(x=10, y=6)
    encounter.units["F1"].current_hp = 10
    encounter.units["F2"].position = GridPosition(x=1, y=12)
    encounter.units["F2"].current_hp = 30
    encounter.units["F2"].ac = 25
    encounter.units["F3"].position = GridPosition(x=1, y=13)
    encounter.units["F3"].current_hp = 30
    encounter.units["F3"].ac = 25
    encounter.units["F4"].position = GridPosition(x=1, y=15)
    encounter.units["F4"].current_hp = 30
    encounter.units["F4"].ac = 25
    encounter.units["E1"].position = GridPosition(x=15, y=15)
    encounter.units["E2"].position = GridPosition(x=15, y=14)
    encounter.units["E3"].position = GridPosition(x=16, y=15)
    encounter.units["E4"].position = GridPosition(x=16, y=14)
    encounter.active_combatant_index = encounter.initiative_order.index("E5")

    result = step_encounter(encounter)
    attack_events = [event for event in result.events if event.event_type == "attack"]

    assert len(attack_events) == 2
    assert [event.actor_id for event in attack_events] == ["E5", "E5"]
    assert [event.target_ids for event in attack_events] == [["F1"], ["F1"]]


def test_scout_multiattack_retargets_after_dropping_the_first_target() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="scout-retargets", enemy_preset_id="bandit_ambush", monster_behavior="balanced")
    )
    encounter.units["E5"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].position = GridPosition(x=10, y=6)
    encounter.units["F2"].position = GridPosition(x=11, y=6)
    encounter.units["F3"].position = GridPosition(x=1, y=13)
    encounter.units["F3"].current_hp = 20
    encounter.units["F3"].ac = 25
    if "F4" in encounter.units:
        encounter.units["F4"].position = GridPosition(x=1, y=15)
        encounter.units["F4"].current_hp = 20
        encounter.units["F4"].ac = 25
    encounter.units["F1"].current_hp = 1
    encounter.units["F1"].ac = 1
    encounter.units["F2"].current_hp = 1
    encounter.units["F2"].ac = 1

    attack_events = resolve_attack_action(
        encounter,
        "E5",
        {"kind": "attack", "target_id": "F1", "weapon_id": "longbow"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[6]),
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[6]),
        ],
    )

    assert [event.target_ids for event in attack_events] == [["F1"], ["F2"]]


def test_scout_multiattack_can_switch_weapons_between_steps() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="scout-switches-weapons",
            enemy_preset_id="bandit_ambush",
            player_preset_id="fighter_level5_sample_trio",
            monster_behavior="balanced",
        )
    )
    encounter.units["E5"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].position = GridPosition(x=10, y=6)
    encounter.units["F2"].position = GridPosition(x=7, y=6)
    encounter.units["F3"].position = GridPosition(x=1, y=13)
    encounter.units["F3"].current_hp = 20
    encounter.units["F3"].ac = 25
    if "F4" in encounter.units:
        encounter.units["F4"].position = GridPosition(x=1, y=15)
        encounter.units["F4"].current_hp = 20
        encounter.units["F4"].ac = 25
    encounter.units["F1"].current_hp = 1
    encounter.units["F1"].ac = 1
    encounter.units["F2"].current_hp = 1
    encounter.units["F2"].ac = 1

    attack_events = resolve_attack_action(
        encounter,
        "E5",
        {"kind": "attack", "target_id": "F1", "weapon_id": "longbow"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[6]),
            AttackRollOverrides(attack_rolls=[12], damage_rolls=[6]),
        ],
    )

    scout_attack_events = [
        event for event in attack_events if event.event_type == "attack" and event.actor_id == "E5"
    ]

    assert scout_attack_events[0].damage_details.weapon_id == "longbow"
    assert scout_attack_events[1].damage_details.weapon_id == "club"


def test_wolf_pack_tactics_uses_advantage_on_attack_rolls() -> None:
    encounter = create_encounter(EncounterConfig(seed="wolf-pack-tactics-attack", enemy_preset_id="wolf_harriers"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["E2"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[3, 16], damage_rolls=[2, 2]),
        ),
    )

    assert attack.resolved_totals["attackMode"] == "advantage"
    assert "pack_tactics" in attack.raw_rolls["advantageSources"]
    assert attack.resolved_totals["selectedRoll"] == 16


def test_pack_tactics_and_flanking_do_not_stack_beyond_normal_advantage() -> None:
    encounter = create_encounter(EncounterConfig(seed="wolf-double-advantage-check", enemy_preset_id="wolf_harriers"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["E2"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[2, 2]),
        ),
    )

    assert attack.resolved_totals["attackMode"] == "advantage"
    assert len(attack.raw_rolls["attackRolls"]) == 2
    assert "pack_tactics" in attack.raw_rolls["advantageSources"]
    assert "flanking" in attack.raw_rolls["advantageSources"]
    assert attack.resolved_totals["selectedRoll"] == 16


def test_wolf_bite_knocks_conscious_target_prone_on_hit() -> None:
    encounter = create_encounter(EncounterConfig(seed="wolf-prone-rider", enemy_preset_id="wolf_harriers"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    attack, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[14], damage_rolls=[2, 2]),
        ),
    )

    assert encounter.units["F1"].conditions.prone is True
    assert attack.damage_details.attack_riders_applied == ["prone_on_hit"]
    assert "F1 is knocked prone." in attack.condition_deltas

def test_conscious_prone_unit_stands_up_at_turn_start_and_loses_half_speed() -> None:
    encounter = create_encounter(EncounterConfig(seed="stand-up-turn-start", placements=DEFAULT_POSITIONS))
    encounter.active_combatant_index = encounter.initiative_order.index("F1")
    encounter.units["F1"].conditions.prone = True

    result = step_encounter(encounter)
    stand_up_event = next(event for event in result.events if event.resolved_totals.get("movementPhase") == "stand_up")

    assert result.state.units["F1"].conditions.prone is False
    assert stand_up_event.event_type == "move"
    assert stand_up_event.resolved_totals["movementCostSquares"] == 3
    assert stand_up_event.text_summary == "F1 stands up, spending 15 feet of movement."
    assert get_total_movement_budget(result.state.units["F1"], {"kind": "dash", "reason": "test"}) == 9
