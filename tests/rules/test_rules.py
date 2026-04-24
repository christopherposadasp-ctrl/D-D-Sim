from __future__ import annotations

import pytest

import backend.engine.rules.combat_rules as combat_rules_module
from backend.content.enemies import unit_has_reaction
from backend.content.feature_definitions import unit_has_granted_bonus_action
from backend.engine import create_encounter, run_encounter, step_encounter, summarize_encounter
from backend.engine.ai.decision import MovementPlan, TurnDecision, choose_turn_decision
from backend.engine.combat.engine import (
    execute_decision,
    execute_movement,
    expire_turn_end_effects,
    get_opportunity_attack_weapon_id,
    get_total_movement_budget,
    resolve_action_surge,
    resolve_attack_action,
    resolve_bonus_action,
    resolve_bonus_attack_action,
    resolve_cast_spell_action,
    run_batch_parallel,
    run_batch_serial,
    run_encounter_summary_fast,
    run_single_batch_accumulator,
)
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import (
    DamageCandidate,
    DamageComponentResult,
    EncounterConfig,
    GrappledEffect,
    GridPosition,
    HiddenEffect,
    NoReactionsEffect,
    RageEffect,
    RecklessAttackEffect,
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
    attempt_hide,
    attempt_uncanny_metabolism,
    can_trigger_attack_reaction,
    choose_damage_candidate,
    clear_invalid_hidden_effects,
    expire_turn_effects,
    recalculate_effective_speed,
    resolve_attack,
    resolve_death_save,
    resolve_saving_throw,
)


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


def build_wizard_config(seed: str, *, player_behavior: str = "smart") -> EncounterConfig:
    return EncounterConfig(
        seed=seed,
        enemy_preset_id="goblin_screen",
        player_preset_id="wizard_sample_trio",
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


def test_smart_shield_skips_unstoppable_hits_while_dumb_shield_still_casts() -> None:
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

    assert smart_attack.resolved_totals.get("defenseReaction") is None
    assert smart.units["F1"].resources.spell_slots_level_1 == 2
    assert any(effect.kind == "shield" for effect in smart.units["F1"].temporary_effects) is False

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


def test_barbarian_level2_reckless_attack_grants_advantage_on_strength_attacks_until_next_turn() -> None:
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

    assert attack_events[0].event_type == "phase_change"
    assert attack_events[0].resolved_totals["recklessAttack"] is True
    assert any(effect.kind == "reckless_attack" for effect in encounter.units["F1"].temporary_effects)
    attack_event = next(event for event in attack_events if event.event_type == "attack")
    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert "reckless_attack" in attack_event.raw_rolls["advantageSources"]


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
            overrides=AttackRollOverrides(attack_rolls=[12, 5], damage_rolls=[1], advantage_damage_rolls=[1]),
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
    assert result.events[0].text_summary == "Combat ends. Goblins win."


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

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}
    assert decision.surged_action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}
    assert [event.event_type for event in events] == ["attack", "phase_change", "attack"]
    assert [event.target_ids for event in events if event.event_type == "attack"] == [["G1"], ["G1"]]
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
    assert decision.surged_action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}
    assert [event.event_type for event in events] == ["phase_change", "move", "attack"]
    assert events[1].resolved_totals["movementPhase"] == "between_actions"
    assert encounter.units["F1"].position.model_dump() == {"x": 8, "y": 1}
    assert encounter.units["F1"].resources.action_surge_uses == 0


def test_scout_multiattack_resolves_two_longbow_attacks() -> None:
    encounter = create_encounter(EncounterConfig(seed="scout-multiattack", enemy_preset_id="bandit_ambush", monster_behavior="balanced"))
    encounter.units["E5"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].position = GridPosition(x=10, y=6)
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
        EncounterConfig(seed="scout-switches-weapons", enemy_preset_id="bandit_ambush", monster_behavior="balanced")
    )
    encounter.units["E5"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].position = GridPosition(x=10, y=6)
    encounter.units["F2"].position = GridPosition(x=7, y=6)
    encounter.units["F3"].position = GridPosition(x=1, y=13)
    encounter.units["F3"].current_hp = 20
    encounter.units["F3"].ac = 25
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

    assert attack_events[0].damage_details.weapon_id == "longbow"
    assert attack_events[1].damage_details.weapon_id == "club"


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
