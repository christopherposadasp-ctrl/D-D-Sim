from __future__ import annotations

from backend.content.enemies import create_enemy, get_monster_definition_for_unit, unit_has_bonus_action, unit_has_trait
from backend.engine import create_encounter, run_encounter
from backend.engine.ai.decision import (
    TurnDecision,
    can_intentionally_provoke_opportunity_attack,
    choose_turn_decision,
    finalize_player_turn_decision,
    get_ranked_attack_targets,
)
from backend.engine.combat.engine import clear_turn_flags, execute_decision, resolve_attack_action
from backend.engine.constants import ARCHER_GOBLIN_IDS, DEFAULT_POSITIONS, MELEE_GOBLIN_IDS
from backend.engine.models.state import (
    ConcentrationEffect,
    EncounterConfig,
    GridPosition,
    HiddenEffect,
    NoReactionsEffect,
    OnHitEffect,
    RageEffect,
    WeaponRange,
)
from backend.engine.rules.combat_rules import AttackRollOverrides


def build_placements(**overrides):
    placements = {
        "F1": {"x": 1, "y": 1},
        "F2": {"x": 1, "y": 3},
        "F3": {"x": 1, "y": 5},
        "F4": {"x": 1, "y": 7},
        "G1": {"x": 15, "y": 1},
        "G2": {"x": 15, "y": 4},
        "G3": {"x": 15, "y": 7},
        "G4": {"x": 15, "y": 10},
        "G5": {"x": 15, "y": 13},
        "G6": {"x": 14, "y": 14},
        "G7": {"x": 15, "y": 15},
    }
    placements.update(overrides)
    return placements


def build_trio_placements(**overrides):
    placements = build_placements(**overrides)
    placements.pop("F4", None)
    return placements


def defeat_other_enemies(encounter, *active_enemy_ids: str) -> None:
    active_ids = set(active_enemy_ids)
    for unit in encounter.units.values():
        if unit.faction != "goblins" or unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True


def keep_only_active_units(encounter, *active_unit_ids: str) -> None:
    active_ids = set(active_unit_ids)
    for unit in encounter.units.values():
        if unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True
        unit.conditions.unconscious = False
        unit.conditions.prone = False


def test_level5_fighter_opens_with_dash_then_action_surge_extra_attack_from_default_layout() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-open-dash", placements=DEFAULT_POSITIONS))

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "dash"
    assert decision.between_action_movement is not None
    assert decision.between_action_movement.mode == "dash"
    assert decision.surged_action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_intents": [
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
        ],
    }
    assert decision.post_action_movement is None


def test_level1_fighter_sample_still_opens_with_dash_from_default_layout() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-level1-open-dash",
            placements=build_trio_placements(),
            player_preset_id="fighter_sample_trio",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "dash"
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "dash"
    assert decision.surged_action is None


def test_level5_fighter_prefers_dash_plus_action_surge_melee_over_javelin_fallback() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-move-javelin", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=9, y=1)

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "dash"
    assert decision.between_action_movement is not None
    assert decision.between_action_movement.mode == "dash"
    assert decision.surged_action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_intents": [
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
            {"maneuver_id": "battle_master_auto", "precision_max_miss_margin": 8},
        ],
    }
    assert [point.model_dump() for point in decision.between_action_movement.path] == [
        {"x": 1, "y": 1},
        {"x": 2, "y": 1},
        {"x": 3, "y": 1},
        {"x": 4, "y": 1},
        {"x": 5, "y": 1},
        {"x": 6, "y": 1},
        {"x": 7, "y": 1},
        {"x": 8, "y": 1},
    ]
    assert decision.post_action_movement is None


def test_level5_fighter_uses_baseline_auto_maneuvers_when_already_in_melee() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-adjacent-action-surge", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)

    decision = choose_turn_decision(encounter, "F1")

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


def test_level5_fighter_can_tactical_shift_after_second_wind_and_normal_movement() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-tactical-shift-after-move", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].current_hp = 18
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=5, y=1)
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "second_wind", "timing": "before_action"}
    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.path[-1] == GridPosition(x=4, y=1)
    assert decision.action["kind"] == "attack"
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "tactical_shift"
    assert len(decision.post_action_movement.path) - 1 <= 3


def test_smart_fighter_does_not_use_before_action_second_wind_above_forty_percent() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-smart-second-wind-threshold",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="fighter_level5_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1")
    encounter.units["F1"].current_hp = 19

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action is None


def test_dumb_fighter_keeps_half_hp_before_action_second_wind_threshold() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-dumb-second-wind-threshold",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="fighter_level5_sample_trio",
            player_behavior="dumb",
        )
    )
    keep_only_active_units(encounter, "F1", "G1")
    encounter.units["F1"].current_hp = 22

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "second_wind", "timing": "before_action"}


def test_level2_fighter_does_not_spend_action_surge_for_double_javelin_turns() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="fighter-no-double-javelin", placements=DEFAULT_POSITIONS, player_behavior="dumb")
    )
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=15, y=1)
    encounter.units["F1"].effective_speed = 0

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "javelin"
    assert decision.surged_action is None


def test_level5_fighter_holds_action_surge_when_only_non_finisher_javelins_remain() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-hold-surge-after-melee-kill", placements=DEFAULT_POSITIONS))
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["G1"].position = GridPosition(x=6, y=5)
    encounter.units["G1"].current_hp = 0
    encounter.units["G1"].conditions.dead = True
    encounter.units["G2"].position = GridPosition(x=12, y=5)
    encounter.units["G2"].current_hp = 30
    events = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "skip", "reason": "normal action already resolved in this setup"},
            surged_action={"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"},
        ),
        events,
        rescue_mode=False,
    )

    assert encounter.units["F1"].resources.action_surge_uses == 1
    assert not any(event.event_type == "phase_change" and "Action Surge" in event.text_summary for event in events)


def test_level5_fighter_allows_action_surge_javelin_finisher_when_melee_is_gone() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-surge-ranged-finisher", placements=DEFAULT_POSITIONS))
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["G1"].position = GridPosition(x=6, y=5)
    encounter.units["G1"].current_hp = 0
    encounter.units["G1"].conditions.dead = True
    encounter.units["G2"].position = GridPosition(x=12, y=5)
    encounter.units["G2"].current_hp = 5
    events = []

    execute_decision(
        encounter,
        "F1",
        TurnDecision(
            action={"kind": "skip", "reason": "normal action already resolved in this setup"},
            surged_action={"kind": "attack", "target_id": "G2", "weapon_id": "javelin"},
        ),
        events,
        rescue_mode=False,
    )

    assert encounter.units["F1"].resources.action_surge_uses == 0
    assert any(event.event_type == "phase_change" and "Action Surge" in event.text_summary for event in events)
    assert any(event.event_type == "attack" and "with Javelin" in event.text_summary for event in events)


def test_smart_fighter_does_not_throw_javelin_when_adjacent_melee_is_available() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-frontliner-melee-over-javelin",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}, G2={"x": 12, "y": 5}),
            player_preset_id="fighter_level5_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].resources.action_surge_uses = 0

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "attack"
    assert decision.action["target_id"] == "G1"
    assert decision.action["weapon_id"] == "greatsword"


def test_smart_fighter_uses_clean_normal_range_javelin_when_melee_is_unreachable() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-frontliner-clean-javelin",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 9, "y": 1}),
            player_preset_id="fighter_level5_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1")
    encounter.units["F1"].resources.action_surge_uses = 0

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "attack"
    assert decision.action["target_id"] == "G1"
    assert decision.action["weapon_id"] == "javelin"
    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.path[-1] == GridPosition(x=3, y=1)


def test_smart_fighter_advances_instead_of_throwing_long_range_javelin() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-frontliner-no-long-range-javelin",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 15, "y": 1}),
            player_preset_id="fighter_level5_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1")
    encounter.units["F1"].resources.action_surge_uses = 0

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "dash"
    assert decision.post_action_movement is not None
    assert decision.action.get("weapon_id") != "javelin"


def test_smart_fighter_extra_attack_retarget_avoids_disadvantage_javelin() -> None:
    result = run_encounter(
        EncounterConfig(
            seed="focused-first5-hobgoblin_command_screen-001",
            enemy_preset_id="hobgoblin_command_screen",
            player_preset_id="martial_mixed_party",
            player_behavior="smart",
            monster_behavior="balanced",
        )
    )

    assert not any(
        event.actor_id == "F1"
        and event.event_type == "attack"
        and event.damage_details
        and event.damage_details.weapon_id == "javelin"
        and event.resolved_totals.get("attackMode") == "disadvantage"
        for frame in result.replay_frames
        if frame.round <= 5
        for event in frame.events
    )


def test_level3_fighter_uses_baseline_auto_maneuver_when_no_action_surge_followup_is_available() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-smart-precision",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="fighter_level3_sample_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].resources.action_surge_uses = 0
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_id": "battle_master_auto",
        "precision_max_miss_margin": 8,
    }
    assert decision.surged_action is None


def test_level3_fighter_uses_baseline_auto_maneuver_against_healthy_melee_threat() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-smart-pressure-precision",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="fighter_level3_sample_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].resources.action_surge_uses = 0
    encounter.units["G1"].current_hp = 40
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_id": "battle_master_auto",
        "precision_max_miss_margin": 8,
    }


def test_dumb_level3_fighter_uses_auto_maneuvers_opportunistically() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-dumb-auto-maneuver",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="fighter_level3_sample_trio",
            player_behavior="dumb",
        )
    )
    encounter.units["F1"].resources.action_surge_uses = 0
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {
        "kind": "attack",
        "target_id": "G1",
        "weapon_id": "greatsword",
        "maneuver_id": "battle_master_auto",
        "precision_max_miss_margin": 8,
    }
    assert decision.surged_action is None


def test_level3_fighter_selects_no_maneuver_when_superiority_dice_are_exhausted() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-no-superiority-dice",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="fighter_level3_sample_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].resources.superiority_dice = 0
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}
    assert decision.surged_action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}


def test_rogue_skirmisher_does_not_close_after_opening_shortbow_attack() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-open-shortbow",
            placements=build_trio_placements(),
            player_preset_id="rogue_ranged_trio",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "shortbow"
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is None


def test_rogue_skirmisher_prefers_sneak_attack_target_when_shooting() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-sneak-target-choice",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, F2={"x": 5, "y": 3}, G1={"x": 6, "y": 1}, G2={"x": 6, "y": 3}),
            player_preset_id="rogue_ranged_trio",
        )
    )
    encounter.units["G1"].current_hp = 1
    encounter.units["G2"].current_hp = 7

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "shortbow"}


def test_melee_rogue_prefers_rapier_line_when_melee_is_available() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="melee-rogue-rapier-first",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, F2={"x": 3, "y": 1}, G1={"x": 4, "y": 1}),
            player_preset_id="rogue_melee_trio",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "rapier"}
    assert decision.pre_action_movement is not None


def test_melee_rogue_uses_shortbow_only_after_closing_options_fail() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="melee-rogue-shortbow-fallback",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 15, "y": 1}),
            player_preset_id="rogue_melee_trio",
        )
    )
    encounter.units["F1"].effective_speed = 0

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "shortbow"
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is None


def test_smart_monk_uses_shortsword_plus_bonus_unarmed_when_already_in_melee() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-adjacent-martial-arts-smart",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="monk_sample_trio",
            player_behavior="smart",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortsword"}
    assert decision.bonus_action == {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "G1"}


def test_dumb_monk_still_uses_bonus_unarmed_when_already_in_melee() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-adjacent-martial-arts-dumb",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="monk_sample_trio",
            player_behavior="dumb",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortsword"}
    assert decision.bonus_action == {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "G1"}


def test_smart_monk_uses_baseline_dash_without_bonus_unarmed_when_normal_move_cannot_reach_melee() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-dash-bonus-smart",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 10, "y": 1}),
            player_preset_id="monk_sample_trio",
            player_behavior="smart",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "dash"
    assert decision.bonus_action is None
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "dash"


def test_dumb_monk_does_not_build_dash_plus_bonus_unarmed_turns() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-dash-bonus-dumb",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 10, "y": 1}),
            player_preset_id="monk_sample_trio",
            player_behavior="dumb",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "dash"
    assert decision.bonus_action is None
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "dash"


def test_level2_smart_monk_uses_baseline_bonus_unarmed_instead_of_flurry() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-level2-flurry-smart",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="monk_level2_sample_trio",
            player_behavior="smart",
        )
    )
    encounter.units["G1"].current_hp = 14
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortsword"}
    assert decision.bonus_action == {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "G1"}


def test_level2_smart_monk_uses_baseline_bonus_unarmed_instead_of_patient_defense() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-level2-patient-defense-smart",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}, G2={"x": 5, "y": 6}),
            player_preset_id="monk_level2_sample_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].current_hp = 8
    defeat_other_enemies(encounter, "G1", "G2")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "shortsword"
    assert decision.bonus_action == {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "G1"}


def test_level2_smart_monk_uses_baseline_adjacent_attack_instead_of_step_of_the_wind() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-level2-step-smart",
            placements=build_trio_placements(F1={"x": 2, "y": 1}, G1={"x": 3, "y": 1}, G2={"x": 12, "y": 1}),
            player_preset_id="monk_level2_sample_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].current_hp = 8
    encounter.units["G2"].current_hp = 6
    defeat_other_enemies(encounter, "G1", "G2")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "G1"}
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortsword"}
    assert decision.pre_action_movement is None


def test_level2_dumb_monk_keeps_the_free_bonus_strike_and_does_not_spend_focus() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-level2-flurry-dumb",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="monk_level2_sample_trio",
            player_behavior="dumb",
        )
    )
    encounter.units["G1"].current_hp = 14
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortsword"}
    assert decision.bonus_action == {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": "G1"}


def test_smart_wizard_uses_fire_bolt_as_the_default_ranged_action() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-fire-bolt-smart",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 8, "y": 1}),
            player_preset_id="wizard_sample_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "G1"}


def test_level2_wizard_does_not_select_mage_armor_in_normal_ai_turns() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level2-no-mage-armor-ai",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 8, "y": 1}),
            player_preset_id="wizard_level2_sample_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "G1"}


def test_level3_evoker_wizard_does_not_select_mage_armor_in_normal_ai_turns() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level3-no-mage-armor-ai",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 8, "y": 1}),
            player_preset_id="wizard_level3_evoker_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1")
    encounter.units["F1"].resources.spell_slots_level_2 = 0
    encounter.units["G1"].current_hp = 7

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "G1"}


def test_level4_evoker_wizard_keeps_existing_spell_priority_and_ignores_mage_armor() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level4-shatter-cluster",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 8, "y": 1}, G2={"x": 9, "y": 1}),
            player_preset_id="wizard_level4_evoker_sample_trio",
            player_behavior="smart",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action
    assert decision.action["kind"] == "cast_spell"
    assert decision.action["spell_id"] == "shatter"
    assert set(decision.action["target_ids"]) == {"G1", "G2"}


def test_evoker_wizard_shatter_plans_only_mutually_legal_cluster_targets() -> None:
    for behavior in ("smart", "dumb"):
        encounter = create_encounter(
            EncounterConfig(
                seed=f"wizard-shatter-mutual-cluster-{behavior}",
                placements=build_trio_placements(
                    F1={"x": 1, "y": 1},
                    G1={"x": 8, "y": 1},
                    G2={"x": 6, "y": 1},
                    G3={"x": 10, "y": 1},
                ),
                player_preset_id="wizard_level4_evoker_sample_trio",
                player_behavior=behavior,
            )
        )
        keep_only_active_units(encounter, "F1", "G1", "G2", "G3")
        encounter.units["G1"].current_hp = 20
        encounter.units["G2"].current_hp = 20
        encounter.units["G3"].current_hp = 20

        decision = choose_turn_decision(encounter, "F1")

        assert decision.action
        assert decision.action["kind"] == "cast_spell"
        assert decision.action["spell_id"] == "shatter"
        assert len(decision.action["target_ids"]) == 2
        assert set(decision.action["target_ids"]) != {"G1", "G2", "G3"}


def test_level3_evoker_wizard_uses_shatter_over_scorching_ray_for_ally_safe_cluster() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level3-shatter-cluster",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 8, "y": 1}, G2={"x": 9, "y": 1}),
            player_preset_id="wizard_level3_evoker_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].current_hp = 20
    encounter.units["G2"].current_hp = 20

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "cast_spell"
    assert decision.action["spell_id"] == "shatter"
    assert set(decision.action["target_ids"]) == {"G1", "G2"}


def test_level3_evoker_wizard_rejects_ally_unsafe_shatter_and_uses_single_target_spell() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level3-shatter-ally-unsafe",
            placements=build_trio_placements(
                F1={"x": 1, "y": 1},
                F2={"x": 8, "y": 2},
                G1={"x": 8, "y": 1},
                G2={"x": 9, "y": 1},
            ),
            player_preset_id="wizard_level3_evoker_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "F2", "G1", "G2")
    encounter.units["G1"].current_hp = 20
    encounter.units["G2"].current_hp = 20

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "scorching_ray", "target_id": "G1"}


def test_level3_evoker_wizard_uses_scorching_ray_for_healthy_single_target() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level3-scorching-ray-single-target",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 8, "y": 1}),
            player_preset_id="wizard_level3_evoker_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1")
    encounter.units["G1"].current_hp = 20
    encounter.units["G1"].max_hp = 20

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "scorching_ray", "target_id": "G1"}


def test_smart_wizard_uses_baseline_shocking_grasp_without_retreat_when_pinned_by_one_enemy() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-shocking-grasp-smart",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="wizard_sample_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": "G1"}
    assert decision.post_action_movement is None


def test_dumb_wizard_uses_shocking_grasp_opportunistically_without_retreat_plan() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-shocking-grasp-dumb",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="wizard_sample_trio",
            player_behavior="dumb",
        )
    )
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": "G1"}
    assert decision.post_action_movement is None


def test_smart_wizard_uses_baseline_fire_bolt_instead_of_magic_missile_for_bad_attack_rolls() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="wizard-magic-missile-smart",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="wizard_sample_trio",
            player_behavior="smart",
        )
    )
    dumb = create_encounter(
        EncounterConfig(
            seed="wizard-magic-missile-dumb",
            placements=build_trio_placements(F1={"x": 5, "y": 5}, G1={"x": 6, "y": 5}),
            player_preset_id="wizard_sample_trio",
            player_behavior="dumb",
        )
    )

    smart.units["G1"].current_hp = 8
    dumb.units["G1"].current_hp = 8
    smart.units["G1"].temporary_effects.append(
        NoReactionsEffect(kind="no_reactions", source_id="F2", expires_at_turn_start_of="G1")
    )
    dumb.units["G1"].temporary_effects.append(
        NoReactionsEffect(kind="no_reactions", source_id="F2", expires_at_turn_start_of="G1")
    )
    defeat_other_enemies(smart, "G1")
    defeat_other_enemies(dumb, "G1")

    smart_decision = choose_turn_decision(smart, "F1")
    dumb_decision = choose_turn_decision(dumb, "F1")

    assert smart_decision.action == {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "G1"}
    assert dumb_decision.action == {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "G1"}


def test_smart_wizard_uses_baseline_fire_bolt_instead_of_repositioning_for_burning_hands() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-burning-hands-smart",
            placements=build_trio_placements(
                F1={"x": 5, "y": 5},
                F2={"x": 6, "y": 5},
                G1={"x": 7, "y": 4},
                G2={"x": 7, "y": 5},
            ),
            player_preset_id="wizard_sample_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1", "G2")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "cast_spell"
    assert decision.action["spell_id"] == "fire_bolt"


def test_dumb_wizard_does_not_reposition_specifically_for_burning_hands() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-burning-hands-dumb",
            placements=build_trio_placements(
                F1={"x": 5, "y": 5},
                F2={"x": 6, "y": 5},
                G1={"x": 7, "y": 4},
                G2={"x": 7, "y": 5},
            ),
            player_preset_id="wizard_sample_trio",
            player_behavior="dumb",
        )
    )
    defeat_other_enemies(encounter, "G1", "G2")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action["kind"] == "cast_spell"
    assert decision.action["spell_id"] == "fire_bolt"


def test_paladin_opens_with_level2_bless_on_full_mixed_party() -> None:
    encounter = create_encounter(EncounterConfig(seed="paladin-open-bless", placements=DEFAULT_POSITIONS))

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action["kind"] == "cast_spell"
    assert decision.action["spell_id"] == "bless"
    assert decision.action["spell_level"] == 2
    assert decision.action["target_ids"] == ["F2", "F1", "F3", "F4"]
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "move"
    assert decision.post_action_movement.path[0] == encounter.units["F2"].position
    assert decision.post_action_movement.path[-1] != encounter.units["F2"].position


def test_smart_paladin_bless_movement_prefers_ending_as_flanking_support() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="paladin-bless-flank-support",
            placements=build_placements(F1={"x": 5, "y": 5}, F2={"x": 1, "y": 3}, G1={"x": 6, "y": 5}),
            player_behavior="smart",
        )
    )
    dumb = create_encounter(
        EncounterConfig(
            seed="paladin-bless-no-flank-support",
            placements=build_placements(F1={"x": 5, "y": 5}, F2={"x": 1, "y": 3}, G1={"x": 6, "y": 5}),
            player_behavior="dumb",
        )
    )
    defeat_other_enemies(smart, "G1")
    defeat_other_enemies(dumb, "G1")

    smart_decision = choose_turn_decision(smart, "F2")
    dumb_decision = choose_turn_decision(dumb, "F2")

    assert smart_decision.action["spell_id"] == "bless"
    assert smart_decision.post_action_movement is not None
    assert smart_decision.post_action_movement.path[-1].model_dump() in [
        {"x": 7, "y": 4},
        {"x": 7, "y": 5},
        {"x": 7, "y": 6},
    ]
    assert dumb_decision.post_action_movement is not None
    assert dumb_decision.post_action_movement.path[-1].model_dump() not in [
        {"x": 7, "y": 4},
        {"x": 7, "y": 5},
        {"x": 7, "y": 6},
    ]


def test_smart_paladin_bless_movement_body_blocks_for_backline_when_no_flank_exists() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-bless-body-block",
            placements=build_placements(
                F1={"x": 1, "y": 1},
                F2={"x": 1, "y": 9},
                F3={"x": 1, "y": 5},
                F4={"x": 1, "y": 15},
                G1={"x": 6, "y": 15},
                G2={"x": 4, "y": 5},
            ),
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1", "G2")
    encounter.units["F3"].current_hp = 0
    encounter.units["F3"].conditions.dead = True

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action["spell_id"] == "bless"
    assert decision.post_action_movement is not None
    end = decision.post_action_movement.path[-1]
    assert abs(end.x - 6) <= 1
    assert abs(end.y - 15) <= 1


def test_paladin_trio_does_not_recast_redundant_bless() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-trio-bless-once",
            placements=build_trio_placements(),
            player_preset_id="paladin_level2_sample_trio",
        )
    )
    first_decision = choose_turn_decision(encounter, "F1")
    events: list = []
    execute_decision(encounter, "F1", first_decision, events, rescue_mode=False)

    second_decision = choose_turn_decision(encounter, "F2")

    assert first_decision.action["spell_id"] == "bless"
    assert second_decision.action.get("spell_id") != "bless"


def test_paladin_uses_lay_on_hands_for_downed_adjacent_ally() -> None:
    encounter = create_encounter(EncounterConfig(seed="paladin-downed-ally", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True
    encounter.units["G1"].position = GridPosition(x=2, y=8)
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.bonus_action == {"kind": "lay_on_hands", "timing": "before_action", "target_id": "F1"}
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "longsword"}


def test_paladin_moves_to_rescue_downed_ally_and_still_acts_from_rescue_square() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-move-rescue-action",
            placements=build_placements(
                F1={"x": 4, "y": 4},
                F2={"x": 1, "y": 4},
                G1={"x": 3, "y": 4},
            ),
        )
    )
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True
    encounter.units["F2"].temporary_effects.append(
        ConcentrationEffect(kind="concentration", source_id="F2", spell_id="bless", remaining_rounds=10)
    )
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.path[-1] == GridPosition(x=3, y=3)
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "longsword"}
    assert decision.bonus_action == {"kind": "lay_on_hands", "timing": "after_action", "target_id": "F1"}


def test_paladin_uses_longsword_in_melee_and_javelin_as_fallback() -> None:
    melee = create_encounter(EncounterConfig(seed="paladin-melee", placements=DEFAULT_POSITIONS))
    melee.units["F2"].resources.spell_slots_level_1 = 0
    melee.units["F2"].resources.spell_slots_level_2 = 0
    melee.units["F2"].position = GridPosition(x=4, y=5)
    melee.units["G1"].position = GridPosition(x=5, y=5)

    melee_decision = choose_turn_decision(melee, "F2")

    assert melee_decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "longsword"}

    ranged = create_encounter(EncounterConfig(seed="paladin-ranged-fallback", placements=DEFAULT_POSITIONS))
    ranged.units["F2"].resources.spell_slots_level_1 = 0
    ranged.units["F2"].resources.spell_slots_level_2 = 0
    ranged.units["F2"].effective_speed = 0
    ranged.units["G1"].position = GridPosition(x=5, y=8)

    ranged_decision = choose_turn_decision(ranged, "F2")

    assert ranged_decision.action["kind"] == "attack"
    assert ranged_decision.action["weapon_id"] == "javelin"


def test_smart_paladin_uses_clean_normal_range_javelin_when_melee_is_unreachable() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-frontliner-clean-javelin",
            placements=build_placements(F2={"x": 1, "y": 2}, G1={"x": 6, "y": 2}),
            player_behavior="smart",
        )
    )
    encounter.units["F2"].resources.spell_slots_level_1 = 0
    encounter.units["F2"].resources.spell_slots_level_2 = 0
    encounter.units["F2"].effective_speed = 0
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "javelin"}


def test_smart_paladin_advances_instead_of_throwing_long_range_javelin() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-frontliner-no-long-range-javelin",
            placements=build_placements(F2={"x": 1, "y": 2}, G1={"x": 15, "y": 2}),
            player_behavior="smart",
        )
    )
    encounter.units["F2"].resources.spell_slots_level_1 = 0
    encounter.units["F2"].resources.spell_slots_level_2 = 0
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action["kind"] == "dash"
    assert decision.post_action_movement is not None
    assert decision.action.get("weapon_id") != "javelin"


def test_paladin_rescue_followup_does_not_throw_disadvantage_javelin() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-rescue-no-disadvantage-javelin",
            placements=build_placements(F1={"x": 3, "y": 1}, F2={"x": 1, "y": 1}, G1={"x": 13, "y": 1}),
            player_behavior="smart",
        )
    )
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True
    encounter.units["F2"].resources.spell_slots_level_1 = 0
    encounter.units["F2"].resources.spell_slots_level_2 = 0
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.pre_action_movement is not None
    assert decision.bonus_action == {"kind": "lay_on_hands", "timing": "after_action", "target_id": "F1"}
    assert decision.action["kind"] == "skip"
    assert decision.action.get("weapon_id") != "javelin"


def test_paladin_does_not_select_aid_even_when_prepared_and_available() -> None:
    encounter = create_encounter(EncounterConfig(seed="paladin-aid-not-ai", placements=DEFAULT_POSITIONS))
    encounter.units["F2"].temporary_effects.append(
        ConcentrationEffect(kind="concentration", source_id="F2", spell_id="bless", remaining_rounds=10)
    )
    encounter.units["F2"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "longsword"
    assert decision.action.get("spell_id") != "aid"


def test_paladin_uses_natures_wrath_when_four_enemies_can_be_caught() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-natures-wrath-ai",
            placements=build_placements(
                F1={"x": 1, "y": 3},
                F2={"x": 1, "y": 1},
                G1={"x": 6, "y": 1},
                G2={"x": 7, "y": 1},
                G3={"x": 8, "y": 1},
                G4={"x": 6, "y": 2},
            ),
        )
    )
    encounter.units["F2"].resources.spell_slots_level_1 = 0
    encounter.units["F2"].resources.spell_slots_level_2 = 0
    defeat_other_enemies(encounter, "G1", "G2", "G3", "G4")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.path[-1].model_dump() != {"x": 1, "y": 1}
    assert decision.action["kind"] == "special_action"
    assert decision.action["action_id"] == "natures_wrath"
    assert decision.action["target_ids"] == ["G1", "G2", "G3", "G4"]


def test_smart_paladin_natures_wrath_can_still_end_as_flanking_support() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-natures-wrath-flank-support",
            placements=build_placements(
                F1={"x": 5, "y": 5},
                F2={"x": 4, "y": 4},
                G1={"x": 6, "y": 5},
                G2={"x": 6, "y": 6},
                G3={"x": 6, "y": 7},
                G4={"x": 7, "y": 7},
            ),
            player_behavior="smart",
        )
    )
    encounter.units["F2"].resources.spell_slots_level_1 = 0
    encounter.units["F2"].resources.spell_slots_level_2 = 0
    keep_only_active_units(encounter, "F1", "F2", "G1", "G2", "G3", "G4")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action["kind"] == "special_action"
    assert decision.action["action_id"] == "natures_wrath"
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.path[-1].model_dump() in [
        {"x": 7, "y": 4},
        {"x": 7, "y": 5},
        {"x": 7, "y": 6},
    ]


def test_paladin_does_not_use_natures_wrath_for_three_enemies() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-natures-wrath-ai-threshold",
            placements=build_placements(
                F2={"x": 4, "y": 1},
                G1={"x": 6, "y": 1},
                G2={"x": 7, "y": 1},
                G3={"x": 8, "y": 1},
            ),
        )
    )
    encounter.units["F2"].resources.spell_slots_level_1 = 0
    encounter.units["F2"].resources.spell_slots_level_2 = 0
    defeat_other_enemies(encounter, "G1", "G2", "G3")

    decision = choose_turn_decision(encounter, "F2")

    assert decision.action.get("action_id") != "natures_wrath"


def test_barbarian_delays_rage_on_opening_dash_from_default_layout() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-open-dash",
            placements=build_trio_placements(),
            player_preset_id="barbarian_level2_sample_trio",
        )
    )

    decision = choose_turn_decision(encounter, "F2")

    assert decision.bonus_action is None
    assert decision.action["kind"] == "dash"
    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "dash"


def test_barbarian_prefers_greataxe_when_melee_is_reachable() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-greataxe-first",
            placements=build_trio_placements(),
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)

    decision = choose_turn_decision(encounter, "F2")

    assert decision.bonus_action == {"kind": "rage", "timing": "before_action"}
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greataxe"}


def test_barbarian_throws_handaxe_only_after_close_and_dash_fail() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-handaxe-fallback",
            placements=build_trio_placements(),
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=8, y=1)
    encounter.units["F2"].effective_speed = 0

    decision = choose_turn_decision(encounter, "F2")

    assert decision.bonus_action == {"kind": "rage", "timing": "before_action"}
    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "handaxe"
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is None


def test_smart_barbarian_uses_baseline_no_reckless_attack_on_an_eligible_greataxe_turn() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-barbarian-reckless",
            placements=build_trio_placements(),
            player_behavior="smart",
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)

    decision = choose_turn_decision(encounter, "F2")
    clear_turn_flags(encounter.units["F2"])
    attack_events = resolve_attack_action(
        encounter,
        "F2",
        decision.action,
        step_overrides=[AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[7])],
    )

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greataxe"}
    assert attack_events[0].event_type == "attack"
    assert all(event.resolved_totals.get("recklessAttack") is not True for event in attack_events)
    assert attack_events[0].resolved_totals["attackMode"] == "normal"
    assert "reckless_attack" not in attack_events[0].raw_rolls.get("advantageSources", [])


def test_dumb_barbarian_does_not_use_reckless_attack() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="dumb-barbarian-reckless",
            placements=build_trio_placements(),
            player_behavior="dumb",
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)

    decision = choose_turn_decision(encounter, "F2")
    clear_turn_flags(encounter.units["F2"])
    attack_events = resolve_attack_action(
        encounter,
        "F2",
        decision.action,
        step_overrides=[AttackRollOverrides(attack_rolls=[16], damage_rolls=[7])],
    )

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greataxe"}
    assert all(event.resolved_totals.get("recklessAttack") is not True for event in attack_events)
    assert any(effect.kind == "reckless_attack" for effect in encounter.units["F2"].temporary_effects) is False


def test_smart_barbarian_skips_reckless_attack_on_pure_handaxe_fallback_turns() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-barbarian-no-reckless-handaxe",
            placements=build_trio_placements(),
            player_behavior="smart",
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=8, y=1)
    encounter.units["F2"].effective_speed = 0

    decision = choose_turn_decision(encounter, "F2")
    clear_turn_flags(encounter.units["F2"])
    attack_events = resolve_attack_action(
        encounter,
        "F2",
        decision.action,
        step_overrides=[AttackRollOverrides(attack_rolls=[16], damage_rolls=[4])],
    )

    assert decision.action["weapon_id"] == "handaxe"
    assert all(event.resolved_totals.get("recklessAttack") is not True for event in attack_events)
    assert any(effect.kind == "reckless_attack" for effect in encounter.units["F2"].temporary_effects) is False


def test_smart_barbarian_skips_reckless_attack_when_first_melee_attack_already_has_advantage() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-barbarian-no-reckless-advantage",
            placements=build_trio_placements(),
            player_behavior="smart",
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].position = GridPosition(x=4, y=5)
    encounter.units["G1"].position = GridPosition(x=5, y=5)
    encounter.units["G1"].conditions.prone = True

    decision = choose_turn_decision(encounter, "F2")
    clear_turn_flags(encounter.units["F2"])
    attack_events = resolve_attack_action(
        encounter,
        "F2",
        decision.action,
        step_overrides=[AttackRollOverrides(attack_rolls=[4, 16], damage_rolls=[7])],
    )

    attack_event = next(event for event in attack_events if event.event_type == "attack")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greataxe"}
    assert all(event.resolved_totals.get("recklessAttack") is not True for event in attack_events)
    assert attack_event.resolved_totals["attackMode"] == "advantage"
    assert "target_prone" in attack_event.raw_rolls["advantageSources"]
    assert "reckless_attack" not in attack_event.raw_rolls["advantageSources"]


def test_smart_melee_rogue_prefers_ally_supported_target() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="smart-melee-rogue-target-choice",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, F2={"x": 5, "y": 3}, G1={"x": 4, "y": 1}, G2={"x": 6, "y": 3}),
            player_preset_id="rogue_melee_trio",
            player_behavior="smart",
        )
    )
    smart.units["G1"].current_hp = 1
    smart.units["G2"].current_hp = 7

    decision = choose_turn_decision(smart, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "rapier"}


def test_smart_level2_ranged_rogue_hides_from_rock_before_attacking_when_already_set() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-hide-open",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].effective_speed = 0
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E4":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "hide", "timing": "before_action"}
    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert decision.pre_action_movement is None


def test_ranged_assassin_rogue_uses_steady_aim_when_stationary_without_advantage() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-steady-aim-open",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level3_ranged_assassin_trio",
            player_behavior="dumb",
        )
    )
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert decision.bonus_action == {"kind": "steady_aim", "timing": "before_action"}
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is None


def test_ranged_assassin_rogue_does_not_use_steady_aim_when_assassinate_already_grants_advantage() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-assassinate-no-steady",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level3_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].position = GridPosition(x=3, y=8)
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert decision.bonus_action == {"kind": "hide", "timing": "after_movement"}
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is not None


def test_ranged_assassin_rogue_uses_after_action_hide_when_already_set_and_attack_has_advantage() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-assassinate-defensive-hide",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level3_ranged_assassin_trio",
            player_behavior="dumb",
        )
    )
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].effective_speed = 0
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    encounter.initiative_order = ["F1", "E4"]
    encounter.active_combatant_index = 0
    encounter.round = 1
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert decision.bonus_action == {"kind": "hide", "timing": "after_action"}
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is None


def test_ranged_assassin_rogue_does_not_use_steady_aim_when_hidden_already_grants_advantage() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-hidden-no-steady",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level3_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["E4"].position = GridPosition(x=8, y=1)
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert decision.bonus_action is None


def test_ranged_assassin_rogue_keeps_existing_hide_behavior_around_the_rock() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-hide-open",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level3_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].effective_speed = 0
    encounter.units["E4"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E4":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "hide", "timing": "before_action"}
    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}


def test_level4_ranged_assassin_uses_sharpshooter_shortbow_when_stationary_and_pinned() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level4-sharpshooter-pinned",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level4_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].effective_speed = 0
    encounter.units["E4"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert decision.bonus_action == {"kind": "steady_aim", "timing": "before_action"}
    assert decision.pre_action_movement is None
    assert decision.post_action_movement is None


def test_level4_ranged_assassin_keeps_existing_hide_behavior_around_the_rock() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level4-hide-open",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level4_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].effective_speed = 0
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "hide", "timing": "before_action"}
    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}


def test_level5_ranged_assassin_does_not_select_cunning_strike_in_normal_ai() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level5-no-cunning-ai",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level5_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.round = 2
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].effective_speed = 0
    encounter.units["E4"].position = GridPosition(x=6, y=5)
    defeat_other_enemies(encounter, "E4")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert "cunning_strike_id" not in decision.action


def test_level2_ranged_rogue_uses_baseline_after_movement_hide_setup_for_both_behaviors() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="rogue-level2-smart-hide-setup",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    dumb = create_encounter(
        EncounterConfig(
            seed="rogue-level2-dumb-hide-setup",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="dumb",
        )
    )

    for encounter in (smart, dumb):
        encounter.units["F1"].position = GridPosition(x=3, y=7)
        encounter.units["E4"].position = GridPosition(x=8, y=8)
        for enemy_id, enemy in encounter.units.items():
            if not enemy_id.startswith("E") or enemy_id == "E4":
                continue
            enemy.current_hp = 0
            enemy.conditions.dead = True

    smart_decision = choose_turn_decision(smart, "F1")
    dumb_decision = choose_turn_decision(dumb, "F1")

    assert smart_decision.bonus_action == {"kind": "hide", "timing": "after_movement"}
    assert dumb_decision.bonus_action == {"kind": "hide", "timing": "after_movement"}
    assert smart_decision.pre_action_movement is None
    assert dumb_decision.pre_action_movement is None
    assert smart_decision.post_action_movement is not None
    assert dumb_decision.post_action_movement is not None


def test_smart_level2_ranged_rogue_uses_disengage_to_escape_melee_into_a_shortbow_turn() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-ranged-disengage",
            placements=build_trio_placements(
                F1={"x": 5, "y": 5},
                F2={"x": 10, "y": 5},
                G1={"x": 6, "y": 5},
                G2={"x": 11, "y": 5},
            ),
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "disengage", "timing": "before_action"}
    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "shortbow"
    assert decision.action["target_id"] in {"G1", "G2"}
    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.mode == "move"


def test_smart_level2_ranged_rogue_uses_bonus_dash_when_a_normal_move_cannot_reach_shortbow_range() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-ranged-bonus-dash",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 15, "y": 1}),
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].attacks["shortbow"].range = WeaponRange(normal=30, long=60)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("G") or enemy_id == "G1":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "bonus_dash", "timing": "before_action"}
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortbow"}
    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.mode == "dash"
    assert len(decision.pre_action_movement.path) - 1 > 6


def test_ranged_rogue_uses_defensive_bonus_dash_after_shortbow_attack_for_both_behaviors() -> None:
    decisions = []
    for behavior in ("smart", "dumb"):
        encounter = create_encounter(
            EncounterConfig(
                seed=f"rogue-defensive-bonus-dash-{behavior}",
                placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 13, "y": 1}),
                player_preset_id="rogue_level5_ranged_assassin_trio",
                player_behavior=behavior,
            )
        )
        encounter.round = 2
        encounter.units["F1"].attacks["shortbow"].range = WeaponRange(normal=30, long=60)
        defeat_other_enemies(encounter, "G1")

        decisions.append(choose_turn_decision(encounter, "F1"))

    for decision in decisions:
        assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortbow"}
        assert decision.pre_action_movement is not None
        assert decision.bonus_action == {"kind": "bonus_dash", "timing": "after_action"}
        assert decision.post_action_movement is not None
        assert decision.post_action_movement.mode == "dash"
        assert decision.post_action_movement.path[-1] == GridPosition(x=1, y=1)


def test_ranged_rogue_defensive_bonus_dash_preserves_future_shortbow_line() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-defensive-bonus-dash-preserve-shot",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 13, "y": 1}),
            player_preset_id="rogue_level5_ranged_assassin_trio",
            player_behavior="smart",
        )
    )
    encounter.round = 2
    encounter.units["F1"].attacks["shortbow"].range = WeaponRange(normal=30, long=35)
    defeat_other_enemies(encounter, "G1")

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortbow"}
    assert decision.pre_action_movement is not None
    assert decision.bonus_action is None
    assert decision.post_action_movement is None


def test_level2_melee_rogue_uses_bonus_dash_to_turn_distance_into_a_rapier_attack() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-melee-bonus-dash",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 10, "y": 1}),
            player_preset_id="rogue_level2_melee_trio",
            player_behavior="smart",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action == {"kind": "bonus_dash", "timing": "before_action"}
    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "rapier"
    assert decision.action["target_id"] in {"G5", "G6", "G7"}
    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.mode == "dash"


def test_smart_level2_melee_rogue_uses_baseline_rapier_attack_instead_of_ranged_reset() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-melee-disengage",
            placements=build_trio_placements(
                F1={"x": 5, "y": 5},
                F2={"x": 10, "y": 5},
                G1={"x": 6, "y": 5},
                G2={"x": 11, "y": 5},
            ),
            player_preset_id="rogue_level2_melee_trio",
            player_behavior="smart",
        )
    )

    decision = choose_turn_decision(encounter, "F1")

    assert decision.bonus_action is None
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "rapier"}
    assert decision.pre_action_movement is None


def test_smart_level2_melee_rogue_uses_baseline_no_opportunistic_hide() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="rogue-level2-melee-hide-smart",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_melee_trio",
            player_behavior="smart",
        )
    )
    dumb = create_encounter(
        EncounterConfig(
            seed="rogue-level2-melee-hide-dumb",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_melee_trio",
            player_behavior="dumb",
        )
    )

    for encounter in (smart, dumb):
        encounter.units["F1"].position = GridPosition(x=4, y=8)
        encounter.units["F1"].effective_speed = 0
        encounter.units["E4"].position = GridPosition(x=8, y=8)
        for enemy_id, enemy in encounter.units.items():
            if not enemy_id.startswith("E") or enemy_id == "E4":
                continue
            enemy.current_hp = 0
            enemy.conditions.dead = True

    smart_decision = choose_turn_decision(smart, "F1")
    dumb_decision = choose_turn_decision(dumb, "F1")

    assert smart_decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert smart_decision.bonus_action is None
    assert dumb_decision.action == {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}
    assert dumb_decision.bonus_action is None


def test_monsters_do_not_attempt_hide_even_with_the_rock_present() -> None:
    encounter = create_encounter(EncounterConfig(seed="monster-no-hide", enemy_preset_id="goblin_screen", monster_behavior="balanced"))
    encounter.units["E4"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].position = GridPosition(x=8, y=8)
    encounter.active_combatant_index = encounter.initiative_order.index("E4")

    decision = choose_turn_decision(encounter, "E4")

    assert decision.bonus_action != {"kind": "hide", "timing": "before_action"}
    assert decision.bonus_action != {"kind": "hide", "timing": "after_action"}


def test_balanced_monsters_deprioritize_hidden_rogues_when_a_visible_target_is_available() -> None:
    encounter = create_encounter(EncounterConfig(seed="monster-hidden-target-priority", enemy_preset_id="goblin_screen", monster_behavior="balanced"))
    encounter.units["E4"].position = GridPosition(x=10, y=8)
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F2"].position = GridPosition(x=4, y=9)
    encounter.units["F1"].temporary_effects.append(HiddenEffect(kind="hidden", source_id="F1", expires_at_turn_start_of="F1"))

    for fighter_id, fighter in encounter.units.items():
        if not fighter_id.startswith("F") or fighter_id in {"F1", "F2"}:
            continue
        fighter.current_hp = 0
        fighter.conditions.dead = True

    decision = choose_turn_decision(encounter, "E4")

    assert decision.action == {"kind": "attack", "target_id": "F2", "weapon_id": "shortbow"}


def test_smart_barbarian_seeks_flanking_while_dumb_barbarian_does_not() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="smart-barbarian-flank",
            placements=build_trio_placements(),
            player_behavior="smart",
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    smart.units["F2"].position = GridPosition(x=3, y=5)
    smart.units["F1"].position = GridPosition(x=5, y=4)
    smart.units["G1"].position = GridPosition(x=5, y=5)

    dumb = create_encounter(
        EncounterConfig(
            seed="dumb-barbarian-flank",
            placements=build_trio_placements(),
            player_behavior="dumb",
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    dumb.units["F2"].position = GridPosition(x=3, y=5)
    dumb.units["F1"].position = GridPosition(x=5, y=4)
    dumb.units["G1"].position = GridPosition(x=5, y=5)

    smart_decision = choose_turn_decision(smart, "F2")
    dumb_decision = choose_turn_decision(dumb, "F2")

    assert smart_decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greataxe"}
    assert [point.model_dump() for point in smart_decision.pre_action_movement.path] == [{"x": 3, "y": 5}, {"x": 4, "y": 6}]
    assert [point.model_dump() for point in dumb_decision.pre_action_movement.path] == [{"x": 3, "y": 5}, {"x": 4, "y": 4}]


def test_raging_barbarian_uses_bonus_action_upkeep_when_no_attack_is_available() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-rage-upkeep-ai",
            placements=build_trio_placements(),
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    encounter.units["F2"].temporary_effects.append(
        RageEffect(kind="rage", source_id="F2", damage_bonus=2, remaining_rounds=99)
    )
    encounter.units["F2"].resources.rage_uses = 1
    encounter.units["F2"].resources.handaxes = 0
    encounter.units["F2"].effective_speed = 0

    decision = choose_turn_decision(encounter, "F2")

    assert decision.bonus_action == {"kind": "rage", "timing": "after_action"}
    assert decision.action["kind"] == "skip"


def test_smart_players_seek_flanking_while_dumb_players_take_first_adjacent_square() -> None:
    smart = create_encounter(
        EncounterConfig(
            seed="smart-flank-choice",
            placements=build_trio_placements(),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    smart.units["F1"].position = GridPosition(x=3, y=5)
    smart.units["F2"].position = GridPosition(x=5, y=4)
    smart.units["G1"].position = GridPosition(x=5, y=5)

    dumb = create_encounter(
        EncounterConfig(
            seed="dumb-flank-choice",
            placements=build_trio_placements(),
            player_preset_id="fighter_sample_trio",
            player_behavior="dumb",
        )
    )
    dumb.units["F1"].position = GridPosition(x=3, y=5)
    dumb.units["F2"].position = GridPosition(x=5, y=4)
    dumb.units["G1"].position = GridPosition(x=5, y=5)

    smart_decision = choose_turn_decision(smart, "F1")
    dumb_decision = choose_turn_decision(dumb, "F1")

    assert smart_decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}
    assert [point.model_dump() for point in smart_decision.pre_action_movement.path] == [{"x": 3, "y": 5}, {"x": 4, "y": 6}]
    assert [point.model_dump() for point in dumb_decision.pre_action_movement.path] == [{"x": 3, "y": 5}, {"x": 4, "y": 4}]


def test_smart_fighter_can_use_leftover_movement_for_end_turn_flanking_support() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-end-turn-flank-support",
            placements=build_placements(
                F1={"x": 1, "y": 5},
                F2={"x": 5, "y": 5},
                F3={"x": 1, "y": 7},
                F4={"x": 1, "y": 9},
                G1={"x": 6, "y": 5},
                G2={"x": 10, "y": 1},
            ),
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "F2", "G1", "G2")

    decision = finalize_player_turn_decision(
        encounter,
        encounter.units["F1"],
        TurnDecision(action={"kind": "attack", "target_id": "G2", "weapon_id": "javelin"}),
        "greatsword",
    )

    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "move"
    assert decision.post_action_movement.path[-1].model_dump() in [
        {"x": 7, "y": 4},
        {"x": 7, "y": 5},
        {"x": 7, "y": 6},
    ]


def test_dumb_fighter_does_not_add_end_turn_flanking_support_movement() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-no-end-turn-flank-support",
            placements=build_placements(
                F1={"x": 1, "y": 5},
                F2={"x": 5, "y": 5},
                F3={"x": 1, "y": 7},
                F4={"x": 1, "y": 9},
                G1={"x": 6, "y": 5},
                G2={"x": 10, "y": 1},
            ),
            player_behavior="dumb",
        )
    )
    keep_only_active_units(encounter, "F1", "F2", "G1", "G2")

    decision = finalize_player_turn_decision(
        encounter,
        encounter.units["F1"],
        TurnDecision(action={"kind": "attack", "target_id": "G2", "weapon_id": "javelin"}),
        "greatsword",
    )

    assert decision.post_action_movement is None


def test_smart_fighter_can_body_block_for_backline_when_no_flank_exists() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-body-block-backline",
            placements=build_placements(
                F1={"x": 1, "y": 8},
                F2={"x": 1, "y": 3},
                F3={"x": 1, "y": 5},
                F4={"x": 1, "y": 12},
                G1={"x": 6, "y": 12},
                G2={"x": 10, "y": 1},
            ),
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "F2", "F3", "F4", "G1", "G2")

    decision = finalize_player_turn_decision(
        encounter,
        encounter.units["F1"],
        TurnDecision(action={"kind": "attack", "target_id": "G2", "weapon_id": "javelin"}),
        "greatsword",
    )

    assert decision.post_action_movement is not None
    assert decision.post_action_movement.mode == "move"
    end = decision.post_action_movement.path[-1]
    assert abs(end.x - 6) <= 1
    assert abs(end.y - 12) <= 1


def test_smart_frontliner_prefers_lower_hp_kill_target_over_fresh_rider() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-kill-band-rider-priority",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 2, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].current_hp = 8
    encounter.units["G1"].attacks["scimitar"].on_hit_effects = [OnHitEffect(kind="prone_on_hit")]
    encounter.units["G2"].current_hp = 6

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "greatsword"}


def test_smart_frontliner_does_not_chase_caster_over_better_kill_target() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-kill-band-caster-priority",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 2, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].role_tags = ["caster"]
    encounter.units["G1"].current_hp = 8
    encounter.units["G2"].attacks["scimitar"].on_hit_effects = [OnHitEffect(kind="prone_on_hit")]
    encounter.units["G2"].current_hp = 6

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "greatsword"}


def test_smart_players_take_kill_confirm_over_higher_threat_outside_kill_band() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-kill-confirm-over-threat",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 2, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].role_tags = ["caster"]
    encounter.units["G1"].current_hp = 30
    encounter.units["G2"].current_hp = 1
    encounter.units["G2"].ac = 14

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "greatsword"}


def test_smart_players_prefer_immediate_rider_over_distant_caster_that_cannot_pressure_allies_soon() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-immediate-rider-over-distant-caster",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 14, "y": 15}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].attacks["scimitar"].on_hit_effects = [OnHitEffect(kind="prone_on_hit")]
    encounter.units["G1"].current_hp = 18
    encounter.units["G2"].role_tags = ["caster"]

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}


def test_smart_melee_prefers_nearer_frontline_controller_over_farther_backline_caster() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-melee-frontline-over-backline-caster",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 7, "y": 1}, G2={"x": 8, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].attacks["scimitar"].on_hit_effects = [OnHitEffect(kind="grapple_on_hit")]
    encounter.units["G1"].current_hp = 18
    encounter.units["G2"].role_tags = ["caster"]
    encounter.units["G2"].current_hp = 18

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}


def test_smart_ranged_rogue_keeps_backline_threat_priority_when_killability_matches() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-ranged-rogue-backline-threat",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 6, "y": 1}, G2={"x": 8, "y": 1}),
            player_preset_id="rogue_ranged_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].current_hp = 6
    encounter.units["G2"].current_hp = 6
    encounter.units["G2"].role_tags = ["caster"]

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "shortbow"}


def test_smart_ranged_assassin_prioritizes_kobold_scale_sorcerer_caster_target() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-ranged-assassin-kobold-scale-sorcerer",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 6, "y": 1}, G2={"x": 8, "y": 1}),
            player_preset_id="rogue_ranged_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G2"] = create_enemy("G2", "kobold_scale_sorcerer")
    encounter.units["G2"].position = GridPosition(x=8, y=1)
    encounter.units["G1"].current_hp = 27
    encounter.units["G1"].max_hp = 27
    encounter.units["G1"].ac = 15

    decision = choose_turn_decision(encounter, "F1")

    assert encounter.units["G2"].role_tags == ["caster"]
    assert decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "shortbow"}


def test_smart_rogue_and_wizard_prioritize_aura_of_authority_leader() -> None:
    rogue = create_encounter(
        EncounterConfig(
            seed="smart-rogue-aura-of-authority-priority",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 6, "y": 1}, G2={"x": 8, "y": 1}),
            player_preset_id="rogue_ranged_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(rogue, "F1", "G1", "G2")
    rogue.units["G1"].current_hp = 30
    rogue.units["G1"].max_hp = 30
    rogue.units["G2"] = create_enemy("G2", "hobgoblin_captain")
    rogue.units["G2"].position = GridPosition(x=8, y=1)
    rogue.units["G2"].current_hp = 30
    rogue.units["G2"].max_hp = 30

    wizard = create_encounter(
        EncounterConfig(
            seed="smart-wizard-aura-of-authority-priority",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 6, "y": 1}, G2={"x": 8, "y": 1}),
            player_preset_id="wizard_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(wizard, "F1", "G1", "G2")
    wizard.units["F1"].resources.spell_slots_level_1 = 0
    wizard.units["G1"].current_hp = 30
    wizard.units["G1"].max_hp = 30
    wizard.units["G2"] = create_enemy("G2", "hobgoblin_captain")
    wizard.units["G2"].position = GridPosition(x=8, y=1)
    wizard.units["G2"].current_hp = 30
    wizard.units["G2"].max_hp = 30

    rogue_decision = choose_turn_decision(rogue, "F1")
    wizard_decision = choose_turn_decision(wizard, "F1")

    assert unit_has_trait(rogue.units["G2"], "aura_of_authority")
    assert rogue_decision.action == {"kind": "attack", "target_id": "G2", "weapon_id": "shortbow"}
    assert wizard_decision.action == {"kind": "cast_spell", "spell_id": "fire_bolt", "target_id": "G2"}


def test_smart_rogue_ignores_backline_priority_without_a_legal_attack_line() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-rogue-backline-no-legal-line",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 6, "y": 1}, G2={"x": 8, "y": 1}),
            player_preset_id="rogue_ranged_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["G1"].current_hp = 30
    encounter.units["G1"].max_hp = 30
    encounter.units["G2"] = create_enemy("G2", "hobgoblin_captain")
    encounter.units["G2"].position = None
    encounter.units["G2"].current_hp = 30
    encounter.units["G2"].max_hp = 30

    decision = choose_turn_decision(encounter, "F1")

    assert unit_has_trait(encounter.units["G2"], "aura_of_authority")
    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "shortbow"}


def test_melee_ranked_attack_targets_use_immediacy_and_distance_before_backline_threat() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="melee-ranked-attack-targets",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 7, "y": 1}, G2={"x": 8, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].feature_ids.append("extra_attack")
    encounter.units["F1"].class_id = None
    encounter.units["G1"].current_hp = 20
    encounter.units["G2"].role_tags = ["caster"]
    encounter.units["G2"].current_hp = 20

    ranked_targets = get_ranked_attack_targets(encounter, encounter.units["F1"], preferred_weapon_id="greatsword")

    assert [target.id for target in ranked_targets[:2]] == ["G1", "G2"]


def test_extra_attack_targeting_uses_action_level_kill_band_before_the_first_swing() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="smart-extra-attack-kill-band",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 2, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].feature_ids.append("extra_attack")
    encounter.units["F1"].class_id = None
    encounter.units["G1"].role_tags = ["caster"]
    encounter.units["G1"].current_hp = 15
    encounter.units["G1"].ac = 8
    encounter.units["G2"].current_hp = 5

    decision = choose_turn_decision(encounter, "F1")

    assert decision.action == {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"}


def test_extra_attack_keeps_the_same_target_if_it_survives_the_first_hit() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="extra-attack-target-stickiness",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 2, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].feature_ids.append("extra_attack")
    encounter.units["F1"].class_id = None
    encounter.units["G1"].current_hp = 15
    encounter.units["G1"].ac = 8
    encounter.units["G2"].current_hp = 20

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
        ],
    )

    attack_target_ids = [event.target_ids[0] for event in attack_events if event.event_type == "attack"]

    assert attack_target_ids == ["G1", "G1"]


def test_extra_attack_retargets_after_the_first_kill() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="extra-attack-retarget-after-kill",
            placements=build_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 2, "y": 1}, G2={"x": 2, "y": 2}),
            player_preset_id="fighter_sample_trio",
            player_behavior="smart",
        )
    )
    keep_only_active_units(encounter, "F1", "G1", "G2")
    encounter.units["F1"].feature_ids.append("extra_attack")
    encounter.units["F1"].class_id = None
    encounter.units["G1"].current_hp = 5
    encounter.units["G1"].ac = 8
    encounter.units["G2"].current_hp = 20

    attack_events = resolve_attack_action(
        encounter,
        "F1",
        {"kind": "attack", "target_id": "G1", "weapon_id": "greatsword"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
        ],
    )

    attack_target_ids = [event.target_ids[0] for event in attack_events if event.event_type == "attack"]

    assert attack_target_ids == ["G1", "G2"]


def test_monster_multiattack_keeps_the_same_target_if_it_survives_the_first_hit() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monster-multiattack-stickiness",
            enemy_preset_id="deadwatch_phalanx",
            player_preset_id="fighter_sample_trio",
        )
    )
    keep_only_active_units(encounter, "F1", "F2", "E1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].current_hp = 12

    attack_events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "slam"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ],
    )

    attack_target_ids = [event.target_ids[0] for event in attack_events if event.event_type == "attack"]

    assert attack_target_ids == ["F1", "F1"]


def test_monster_multiattack_retargets_after_the_first_kill() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monster-multiattack-retarget-after-kill",
            enemy_preset_id="deadwatch_phalanx",
            player_preset_id="fighter_sample_trio",
        )
    )
    keep_only_active_units(encounter, "F1", "F2", "E1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].current_hp = 4

    attack_events = resolve_attack_action(
        encounter,
        "E1",
        {"kind": "attack", "target_id": "F1", "weapon_id": "slam"},
        step_overrides=[
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
            AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ],
    )

    attack_target_ids = [event.target_ids[0] for event in attack_events if event.event_type == "attack"]

    assert attack_target_ids == ["F1", "F2"]


def test_goblin_role_split_matches_expected_loadouts() -> None:
    encounter = create_encounter(EncounterConfig(seed="goblin-roles", placements=DEFAULT_POSITIONS))

    for goblin_id in MELEE_GOBLIN_IDS:
        assert encounter.units[goblin_id].combat_role == "goblin_melee"
        assert "shortbow" not in encounter.units[goblin_id].attacks
        assert "scimitar" in encounter.units[goblin_id].attacks
        assert get_monster_definition_for_unit(encounter.units[goblin_id]).variant_id == "goblin_raider"
        assert unit_has_trait(encounter.units[goblin_id], "nimble_escape") is True
        assert unit_has_bonus_action(encounter.units[goblin_id], "disengage") is True

    for goblin_id in ARCHER_GOBLIN_IDS:
        assert encounter.units[goblin_id].combat_role == "goblin_archer"
        assert "shortbow" in encounter.units[goblin_id].attacks
        assert "scimitar" in encounter.units[goblin_id].attacks
        assert get_monster_definition_for_unit(encounter.units[goblin_id]).variant_id == "goblin_archer"
        assert unit_has_trait(encounter.units[goblin_id], "nimble_escape") is True
        assert unit_has_bonus_action(encounter.units[goblin_id], "disengage") is True


def test_orc_aggressive_bonus_movement_extends_melee_reach() -> None:
    encounter = create_encounter(EncounterConfig(seed="orc-aggressive", enemy_preset_id="orc_push", monster_behavior="balanced"))
    encounter.units["E1"].position = GridPosition(x=1, y=1)
    encounter.units["F1"].position = GridPosition(x=9, y=1)
    encounter.units["F2"].position = GridPosition(x=1, y=12)
    encounter.units["F3"].position = GridPosition(x=1, y=13)
    encounter.units["F4"].position = GridPosition(x=1, y=15)
    encounter.units["E2"].position = GridPosition(x=15, y=15)
    encounter.units["E3"].position = GridPosition(x=15, y=14)
    encounter.units["E4"].position = GridPosition(x=16, y=15)
    encounter.units["E5"].position = GridPosition(x=16, y=14)

    decision = choose_turn_decision(encounter, "E1")

    assert unit_has_trait(encounter.units["E1"], "aggressive") is True
    assert unit_has_bonus_action(encounter.units["E1"], "aggressive_dash") is True
    assert decision.bonus_action == {"kind": "aggressive_dash", "timing": "before_action"}
    assert decision.action["kind"] == "attack"
    assert decision.action["weapon_id"] == "greataxe"
    assert decision.action["target_id"] in {"F1", "F2", "F3", "F4"}
    assert decision.pre_action_movement is not None
    assert decision.pre_action_movement.mode == "dash"


def test_bandit_archer_commits_to_melee_when_engaged_without_disengage() -> None:
    encounter = create_encounter(EncounterConfig(seed="bandit-melee-commit", enemy_preset_id="bandit_ambush", monster_behavior="balanced"))
    encounter.units["E3"].position = GridPosition(x=6, y=6)
    encounter.units["F1"].position = GridPosition(x=7, y=6)
    encounter.units["F2"].position = GridPosition(x=1, y=12)
    encounter.units["F3"].position = GridPosition(x=1, y=13)
    encounter.units["E1"].position = GridPosition(x=15, y=15)
    encounter.units["E2"].position = GridPosition(x=15, y=14)
    encounter.units["E4"].position = GridPosition(x=16, y=15)
    encounter.units["E5"].position = GridPosition(x=16, y=14)

    first_decision = choose_turn_decision(encounter, "E3")

    assert unit_has_bonus_action(encounter.units["E3"], "disengage") is False
    assert first_decision.bonus_action is None
    assert first_decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "club"}

    encounter.units["F1"].position = GridPosition(x=10, y=6)

    second_decision = choose_turn_decision(encounter, "E3")

    assert second_decision.action["weapon_id"] == "club"
    assert second_decision.bonus_action is None


def test_evil_goblins_finish_adjacent_downed_fighters_first() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="evil-finish-downed",
            placements=build_placements(F1={"x": 5, "y": 5}, F2={"x": 6, "y": 6}, G1={"x": 6, "y": 5}),
            monster_behavior="evil",
        )
    )
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True
    encounter.units["F2"].role_tags = ["healer"]

    decision = choose_turn_decision(encounter, "G1")

    assert decision.action == {"kind": "attack", "target_id": "F1", "weapon_id": "scimitar"}


def test_evil_goblins_do_not_provoke_for_downed_targets() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="evil-no-provoke-downed",
            placements=build_placements(F1={"x": 5, "y": 5}, G1={"x": 7, "y": 5}),
            monster_behavior="evil",
        )
    )
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].conditions.prone = True

    assert can_intentionally_provoke_opportunity_attack(encounter, encounter.units["G1"], encounter.units["F1"]) is False


def test_evil_goblins_still_provoke_for_healers() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="evil-provoke-healer",
            placements=build_placements(F1={"x": 5, "y": 5}, G1={"x": 7, "y": 5}),
            monster_behavior="evil",
        )
    )
    encounter.units["F1"].role_tags = ["healer"]

    assert can_intentionally_provoke_opportunity_attack(encounter, encounter.units["G1"], encounter.units["F1"]) is True
