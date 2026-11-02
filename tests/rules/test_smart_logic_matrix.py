from __future__ import annotations

from backend.engine import create_encounter
from backend.engine.ai.decision import choose_turn_decision, sort_player_ranged_targets
from backend.engine.models.state import EncounterConfig, GridPosition
from scripts import run_smart_logic_matrix


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


def defeat_other_enemies(encounter, *active_enemy_ids: str) -> None:
    active_ids = set(active_enemy_ids)
    for unit in encounter.units.values():
        if unit.faction != "goblins" or unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True


def test_smart_logic_config_defaults_preserve_current_live_behavior() -> None:
    config = EncounterConfig(seed="smart-logic-defaults", placements=build_placements())
    encounter = create_encounter(config)

    assert config.smart_targeting_policy == "new"
    assert config.enable_end_turn_flanking is True
    assert config.enable_frontline_body_blocking is True
    assert encounter.smart_targeting_policy == "new"
    assert encounter.enable_end_turn_flanking is True
    assert encounter.enable_frontline_body_blocking is True
    assert "smartTargetingPolicy" not in encounter.model_dump(by_alias=True)
    assert "enableEndTurnFlanking" not in encounter.model_dump(by_alias=True)
    assert "enableFrontlineBodyBlocking" not in encounter.model_dump(by_alias=True)


def test_smart_logic_matrix_defines_requested_scenarios_and_variants() -> None:
    assert run_smart_logic_matrix.DEFAULT_SCENARIO_IDS == (
        "hobgoblin_kill_box",
        "bugbear_dragnet",
        "deadwatch_phalanx",
        "reaction_bastion",
        "skyhunter_pincer",
        "hobgoblin_command_screen",
        "berserker_overrun",
    )
    assert tuple(variant.id for variant in run_smart_logic_matrix.VARIANTS) == (
        "old_plain",
        "old_body_blocking",
        "old_flanking",
        "old_flanking_body_blocking",
        "new_plain",
        "new_body_blocking",
        "new_flanking",
        "new_flanking_body_blocking_current",
    )
    assert run_smart_logic_matrix.variant_config_kwargs(
        run_smart_logic_matrix.VARIANT_BY_ID["old_body_blocking"]
    ) == {
        "smart_targeting_policy": "old",
        "enable_end_turn_flanking": False,
        "enable_frontline_body_blocking": True,
    }


def test_paired_seed_generation_is_variant_independent() -> None:
    assert run_smart_logic_matrix.paired_seed_for_scenario(
        "hobgoblin_kill_box", "balanced"
    ) == run_smart_logic_matrix.paired_seed_for_scenario("hobgoblin_kill_box", "balanced")
    assert "old_plain" not in run_smart_logic_matrix.paired_seed_for_scenario("hobgoblin_kill_box", "balanced")
    assert "new_flanking" not in run_smart_logic_matrix.paired_seed_for_scenario("hobgoblin_kill_box", "balanced")


def test_old_and_new_smart_ranged_target_priority_can_select_different_targets() -> None:
    placements = build_placements(
        F1={"x": 1, "y": 1},
        F3={"x": 1, "y": 5},
        G1={"x": 2, "y": 5},
        G2={"x": 10, "y": 5},
    )
    old = create_encounter(
        EncounterConfig(seed="old-targeting", placements=placements, player_behavior="smart", smart_targeting_policy="old")
    )
    new = create_encounter(
        EncounterConfig(seed="new-targeting", placements=placements, player_behavior="smart", smart_targeting_policy="new")
    )
    defeat_other_enemies(old, "G1", "G2")
    defeat_other_enemies(new, "G1", "G2")
    old.units["G2"].role_tags = ["caster"]
    new.units["G2"].role_tags = ["caster"]

    old_targets = sort_player_ranged_targets(old, old.units["F3"], [old.units["G1"], old.units["G2"]], "smart", ranged_weapon_id="shortbow")
    new_targets = sort_player_ranged_targets(new, new.units["F3"], [new.units["G1"], new.units["G2"]], "smart", ranged_weapon_id="shortbow")

    assert old_targets[0].id == "G2"
    assert new_targets[0].id == "G1"


def test_flanking_support_can_be_disabled_independently() -> None:
    support_squares = [{"x": 7, "y": 4}, {"x": 7, "y": 5}, {"x": 7, "y": 6}]
    enabled = create_encounter(
        EncounterConfig(
            seed="flanking-enabled",
            placements=build_placements(F1={"x": 5, "y": 5}, F2={"x": 1, "y": 3}, G1={"x": 6, "y": 5}),
            player_behavior="smart",
            enable_end_turn_flanking=True,
            enable_frontline_body_blocking=True,
        )
    )
    disabled = create_encounter(
        EncounterConfig(
            seed="flanking-disabled",
            placements=build_placements(F1={"x": 5, "y": 5}, F2={"x": 1, "y": 3}, G1={"x": 6, "y": 5}),
            player_behavior="smart",
            enable_end_turn_flanking=False,
            enable_frontline_body_blocking=False,
        )
    )
    defeat_other_enemies(enabled, "G1")
    defeat_other_enemies(disabled, "G1")

    enabled_decision = choose_turn_decision(enabled, "F2")
    disabled_decision = choose_turn_decision(disabled, "F2")

    assert enabled_decision.post_action_movement is not None
    assert enabled_decision.post_action_movement.path[-1].model_dump() in support_squares
    assert disabled_decision.post_action_movement is None or disabled_decision.post_action_movement.path[-1].model_dump() not in support_squares


def test_body_blocking_can_be_disabled_independently() -> None:
    placements = build_placements(
        F1={"x": 1, "y": 1},
        F2={"x": 1, "y": 9},
        F3={"x": 1, "y": 5},
        F4={"x": 1, "y": 15},
        G1={"x": 6, "y": 15},
        G2={"x": 4, "y": 5},
    )
    enabled = create_encounter(
        EncounterConfig(
            seed="body-block-enabled",
            placements=placements,
            player_behavior="smart",
            enable_end_turn_flanking=False,
            enable_frontline_body_blocking=True,
        )
    )
    disabled = create_encounter(
        EncounterConfig(
            seed="body-block-disabled",
            placements=placements,
            player_behavior="smart",
            enable_end_turn_flanking=False,
            enable_frontline_body_blocking=False,
        )
    )
    for encounter in (enabled, disabled):
        defeat_other_enemies(encounter, "G1", "G2")
        encounter.units["F3"].current_hp = 0
        encounter.units["F3"].conditions.dead = True

    enabled_decision = choose_turn_decision(enabled, "F2")
    disabled_decision = choose_turn_decision(disabled, "F2")
    assert enabled_decision.post_action_movement is not None
    enabled_end = enabled_decision.post_action_movement.path[-1]
    assert abs(enabled_end.x - 6) <= 1
    assert abs(enabled_end.y - 15) <= 1
    assert disabled_decision.post_action_movement is None or disabled_decision.post_action_movement.path[-1] != GridPosition(
        x=enabled_end.x, y=enabled_end.y
    )


def test_report_payload_includes_aggregates_and_recommendations() -> None:
    rows = [
        {
            "variantId": "old_plain",
            "scenarioId": "hobgoblin_kill_box",
            "totalRuns": 100,
            "playerWinRate": 0.5,
            "smartPlayerWinRate": 0.45,
            "dumbPlayerWinRate": 0.55,
            "smartMinusDumbWinRate": -0.1,
            "averageRounds": 5,
            "averagePartyDead": 1,
            "averageEnemiesKilled": 4,
            "averageRemainingPartyHp": 40,
            "averageRemainingEnemyHp": 20,
        },
        {
            "variantId": "new_flanking_body_blocking_current",
            "scenarioId": "hobgoblin_kill_box",
            "totalRuns": 100,
            "playerWinRate": 0.55,
            "smartPlayerWinRate": 0.6,
            "dumbPlayerWinRate": 0.5,
            "smartMinusDumbWinRate": 0.1,
            "averageRounds": 4,
            "averagePartyDead": 0.5,
            "averageEnemiesKilled": 5,
            "averageRemainingPartyHp": 50,
            "averageRemainingEnemyHp": 10,
        },
    ]

    payload = run_smart_logic_matrix.build_report_payload(
        scenario_ids=("hobgoblin_kill_box",),
        selected_variant_ids=("old_plain", "new_flanking_body_blocking_current"),
        batch_size=100,
        player_preset_id="martial_mixed_party",
        player_behavior="balanced",
        monster_behavior="combined",
        rows=rows,
    )

    assert len(payload["aggregateRows"]) == 2
    assert payload["aggregateRows"][0]["variantId"] == "old_plain"
    assert payload["aggregateRows"][0]["inversionCount"] == 1
    assert payload["recommendations"]["bestByTotalPlayerWinRate"] == "new_flanking_body_blocking_current"
    assert payload["recommendations"]["bestBySmartWinRate"] == "new_flanking_body_blocking_current"
    assert payload["recommendations"]["bestBySmartMinusDumbDelta"] == "new_flanking_body_blocking_current"
