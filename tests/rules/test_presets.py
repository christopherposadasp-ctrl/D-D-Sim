from __future__ import annotations

import pytest

from backend.content.enemies import get_enemy_preset
from backend.engine import create_encounter, run_batch, step_encounter
from backend.engine.models.state import EncounterConfig
from backend.engine.rules.spatial import has_line_of_sight_between_units


def test_preset_default_layout_builds_expected_units() -> None:
    encounter = create_encounter(EncounterConfig(seed="preset-default", enemy_preset_id="goblin_screen"))
    preset = get_enemy_preset("goblin_screen")

    assert sorted(encounter.units) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "F1", "F2", "F3", "F4"]
    assert encounter.units["F1"].position.model_dump() == {"x": 1, "y": 7}
    assert encounter.units["F2"].position.model_dump() == {"x": 1, "y": 8}
    assert encounter.units["F3"].position.model_dump() == {"x": 1, "y": 9}
    assert encounter.units["F4"].position.model_dump() == {"x": 1, "y": 10}

    for preset_unit in preset.units:
        unit = encounter.units[preset_unit.unit_id]
        assert unit.position.model_dump() == preset_unit.position.model_dump()

    assert [feature.model_dump() for feature in encounter.terrain_features] == [
        {
            "feature_id": "rock_1",
            "kind": "rock",
            "position": {"x": 5, "y": 8},
            "footprint": {"width": 1, "height": 1},
        }
    ]


def test_bandit_ambush_uses_mixed_roles() -> None:
    encounter = create_encounter(EncounterConfig(seed="bandit-ambush", enemy_preset_id="bandit_ambush"))

    assert encounter.units["E1"].combat_role == "bandit_melee"
    assert encounter.units["E2"].combat_role == "bandit_melee"
    assert encounter.units["E3"].combat_role == "bandit_archer"
    assert encounter.units["E4"].combat_role == "bandit_archer"
    assert encounter.units["E5"].combat_role == "scout"
    assert "club" in encounter.units["E1"].attacks
    assert "shortbow" in encounter.units["E3"].attacks
    assert "longbow" not in encounter.units["E3"].attacks
    assert "longbow" in encounter.units["E5"].attacks


def test_hobgoblin_kill_box_builds_ten_enemy_units() -> None:
    encounter = create_encounter(EncounterConfig(seed="hobgoblin-kill-box", enemy_preset_id="hobgoblin_kill_box"))

    assert sorted(encounter.units) == ["E1", "E10", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "F1", "F2", "F3", "F4"]
    assert encounter.units["E1"].combat_role == "hobgoblin_melee"
    assert encounter.units["E5"].combat_role == "hobgoblin_archer"
    assert encounter.units["E8"].combat_role == "goblin_boss"


def test_bugbear_dragnet_builds_controller_screen() -> None:
    encounter = create_encounter(EncounterConfig(seed="bugbear-dragnet", enemy_preset_id="bugbear_dragnet"))

    assert sorted(encounter.units) == [
        "E1",
        "E10",
        "E11",
        "E12",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "F1",
        "F2",
        "F3",
        "F4",
    ]
    assert encounter.units["E1"].combat_role == "bugbear_warrior"
    assert encounter.units["E3"].combat_role == "goblin_boss"
    assert encounter.units["E6"].combat_role == "hobgoblin_archer"


def test_deadwatch_phalanx_builds_undead_armor_line() -> None:
    encounter = create_encounter(EncounterConfig(seed="deadwatch-phalanx", enemy_preset_id="deadwatch_phalanx"))

    assert sorted(encounter.units) == [
        "E1",
        "E10",
        "E11",
        "E12",
        "E13",
        "E14",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "F1",
        "F2",
        "F3",
        "F4",
    ]
    assert encounter.units["E1"].combat_role == "animated_armor"
    assert encounter.units["E3"].combat_role == "zombie"
    assert encounter.units["E5"].combat_role == "skeleton"


def test_captains_crossfire_builds_leader_screen() -> None:
    encounter = create_encounter(EncounterConfig(seed="captains-crossfire", enemy_preset_id="captains_crossfire"))

    assert sorted(encounter.units) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "F1", "F2", "F3", "F4"]
    assert encounter.units["E1"].combat_role == "guard"
    assert encounter.units["E3"].combat_role == "bandit_captain"
    assert encounter.units["E4"].combat_role == "noble"


def test_reaction_bastion_builds_elite_reaction_line() -> None:
    encounter = create_encounter(EncounterConfig(seed="reaction-bastion", enemy_preset_id="reaction_bastion"))

    assert sorted(encounter.units) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "F1", "F2", "F3", "F4"]
    assert encounter.units["E1"].combat_role == "knight"
    assert encounter.units["E3"].combat_role == "warrior_veteran"
    assert encounter.units["E5"].combat_role == "guard_captain"
    assert encounter.units["E6"].combat_role == "bandit_archer"


def test_skyhunter_pincer_builds_air_pincer_screen() -> None:
    encounter = create_encounter(EncounterConfig(seed="skyhunter-pincer", enemy_preset_id="skyhunter_pincer"))

    assert sorted(encounter.units) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "F1", "F2", "F3", "F4"]
    assert encounter.units["E1"].combat_role == "griffon"
    assert encounter.units["E2"].combat_role == "centaur_trooper"
    assert encounter.units["E4"].combat_role == "scout"
    assert encounter.units["E6"].combat_role == "guard_captain"


def test_hobgoblin_command_screen_builds_layered_leader_shell() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="hobgoblin-command-screen", enemy_preset_id="hobgoblin_command_screen")
    )

    assert sorted(encounter.units) == [
        "E1",
        "E10",
        "E11",
        "E12",
        "E13",
        "E14",
        "E15",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "F1",
        "F2",
        "F3",
        "F4",
    ]
    assert encounter.units["E1"].combat_role == "hobgoblin_melee"
    assert encounter.units["E7"].combat_role == "hobgoblin_melee"
    assert encounter.units["E11"].combat_role == "hobgoblin_captain"
    assert encounter.units["E12"].combat_role == "hobgoblin_archer"
    assert [feature.model_dump() for feature in encounter.terrain_features] == [
        {
            "feature_id": "rock_1",
            "kind": "rock",
            "position": {"x": 5, "y": 8},
            "footprint": {"width": 1, "height": 1},
        },
        {
            "feature_id": "command_low_wall_1",
            "kind": "low_wall",
            "position": {"x": 7, "y": 6},
            "footprint": {"width": 2, "height": 1},
        },
        {
            "feature_id": "command_low_wall_2",
            "kind": "low_wall",
            "position": {"x": 7, "y": 10},
            "footprint": {"width": 2, "height": 1},
        },
        {
            "feature_id": "command_boulder_1",
            "kind": "boulder",
            "position": {"x": 6, "y": 4},
            "footprint": {"width": 1, "height": 1},
        },
    ]


def test_berserker_overrun_builds_staggered_mob_and_hammers() -> None:
    encounter = create_encounter(EncounterConfig(seed="berserker-overrun", enemy_preset_id="berserker_overrun"))

    assert sorted(encounter.units) == [
        "E1",
        "E10",
        "E11",
        "E12",
        "E13",
        "E14",
        "E15",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "F1",
        "F2",
        "F3",
        "F4",
    ]
    assert encounter.units["E1"].combat_role == "goblin_melee"
    assert encounter.units["E12"].combat_role == "berserker"
    assert encounter.units["E14"].combat_role == "hobgoblin_archer"


def test_frozen_courtyard_dragon_test_builds_white_dragon_map() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="frozen-courtyard-dragon-test", enemy_preset_id="frozen_courtyard_dragon_test")
    )

    assert sorted(encounter.units) == ["E1", "F1", "F2", "F3", "F4"]
    assert encounter.units["F1"].position.model_dump() == {"x": 1, "y": 7}
    assert encounter.units["F2"].position.model_dump() == {"x": 1, "y": 9}
    assert encounter.units["F3"].position.model_dump() == {"x": 2, "y": 5}
    assert encounter.units["F4"].position.model_dump() == {"x": 2, "y": 11}
    assert encounter.units["E1"].combat_role == "young_white_dragon_boss"
    assert encounter.units["E1"].position.model_dump() == {"x": 9, "y": 8}
    assert encounter.units["E1"].resource_pools["opening_landing_uses"] == 0
    assert [feature.model_dump() for feature in encounter.terrain_features] == [
        {
            "feature_id": "rock_1",
            "kind": "rock",
            "position": {"x": 5, "y": 8},
            "footprint": {"width": 1, "height": 1},
        },
        {
            "feature_id": "courtyard_column_1",
            "kind": "column",
            "position": {"x": 3, "y": 5},
            "footprint": {"width": 1, "height": 1},
        },
        {
            "feature_id": "courtyard_column_2",
            "kind": "column",
            "position": {"x": 3, "y": 11},
            "footprint": {"width": 1, "height": 1},
        },
        {
            "feature_id": "courtyard_column_3",
            "kind": "column",
            "position": {"x": 5, "y": 6},
            "footprint": {"width": 1, "height": 1},
        },
        {
            "feature_id": "courtyard_column_4",
            "kind": "column",
            "position": {"x": 5, "y": 10},
            "footprint": {"width": 1, "height": 1},
        },
        {
            "feature_id": "courtyard_low_wall_1",
            "kind": "low_wall",
            "position": {"x": 7, "y": 5},
            "footprint": {"width": 2, "height": 1},
        },
        {
            "feature_id": "courtyard_low_wall_2",
            "kind": "low_wall",
            "position": {"x": 7, "y": 11},
            "footprint": {"width": 2, "height": 1},
        },
    ]


def test_frozen_courtyard_kobold_opening_builds_accepted_opening_layout() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="frozen-courtyard-kobold-opening", enemy_preset_id="frozen_courtyard_kobold_opening")
    )

    assert sorted(encounter.units) == [
        "E1",
        "E10",
        "E11",
        "E12",
        "E13",
        "E14",
        "E15",
        "E16",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "F1",
        "F2",
        "F3",
        "F4",
    ]
    assert encounter.units["F1"].position.model_dump() == {"x": 3, "y": 7}
    assert encounter.units["F2"].position.model_dump() == {"x": 3, "y": 12}
    assert encounter.units["F3"].position.model_dump() == {"x": 1, "y": 5}
    assert encounter.units["F4"].position.model_dump() == {"x": 1, "y": 13}
    assert encounter.units["E9"].combat_role == "kobold_scale_sorcerer"
    assert encounter.units["E10"].combat_role == "kobold_scale_sorcerer"
    assert encounter.units["E13"].combat_role == "kobold_dragonshield"
    assert encounter.units["E13"].position.model_dump() == {"x": 5, "y": 5}
    assert encounter.units["E14"].combat_role == "kobold_dragonshield"
    assert encounter.units["E14"].position.model_dump() == {"x": 5, "y": 12}
    assert encounter.units["E15"].combat_role == "kobold_dragonshield"
    assert encounter.units["E15"].position.model_dump() == {"x": 14, "y": 6}
    assert encounter.units["E16"].combat_role == "kobold_dragonshield"
    assert encounter.units["E16"].position.model_dump() == {"x": 14, "y": 13}
    assert all(has_line_of_sight_between_units(encounter, "F4", f"E{index}") for index in range(1, 13))
    assert all(has_line_of_sight_between_units(encounter, "F4", f"E{index}") for index in (15, 16))


def test_frozen_courtyard_dragon_landing_stages_boss_for_round_three() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="frozen-courtyard-dragon-landing", enemy_preset_id="frozen_courtyard_dragon_landing")
    )

    assert "E17" not in encounter.units
    assert len(encounter.pending_enemy_arrivals) == 1
    arrival = encounter.pending_enemy_arrivals[0]
    assert arrival.unit_id == "E17"
    assert arrival.variant_id == "young_white_dragon_boss"
    assert arrival.arrival_round == 3
    assert arrival.position.model_dump() == {"x": 9, "y": 8}
    assert arrival.resource_pools == {"opening_landing_uses": 0}


def test_frozen_courtyard_dragon_landing_boss_arrives_at_round_three() -> None:
    encounter = create_encounter(
        EncounterConfig(seed="frozen-courtyard-dragon-arrival", enemy_preset_id="frozen_courtyard_dragon_landing")
    )
    encounter.round = 3
    encounter.active_combatant_index = 0

    result = step_encounter(encounter)

    arrival_events = [
        event
        for event in result.events
        if event.resolved_totals.get("event") == "delayed_enemy_arrival"
    ]
    assert len(arrival_events) == 1
    assert arrival_events[0].actor_id == "E17"
    assert arrival_events[0].event_type == "move"
    assert arrival_events[0].resolved_totals["movementMode"] == "delayed_arrival_landing"
    assert arrival_events[0].resolved_totals["arrivalRound"] == 3
    assert arrival_events[0].movement_details
    assert arrival_events[0].movement_details.end
    assert arrival_events[0].movement_details.end.model_dump() == {"x": 9, "y": 8}
    assert result.state.units["E17"].combat_role == "young_white_dragon_boss"
    assert "E17" in result.state.initiative_order
    assert result.state.pending_enemy_arrivals == []


def test_preset_layout_rejects_missing_active_unit() -> None:
    with pytest.raises(ValueError, match="Missing placements"):
        create_encounter(
            EncounterConfig(
                seed="preset-missing-unit",
                enemy_preset_id="bandit_ambush",
                placements={
                    "F1": {"x": 1, "y": 7},
                    "F2": {"x": 1, "y": 8},
                    "F3": {"x": 1, "y": 9},
                    "F4": {"x": 1, "y": 10},
                    "E1": {"x": 14, "y": 7},
                    "E2": {"x": 14, "y": 9},
                    "E3": {"x": 15, "y": 5},
                    "E4": {"x": 15, "y": 11},
                },
            )
        )


def test_combined_batch_runs_with_preset_without_manual_placements() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="preset-combined-batch",
            enemy_preset_id="wolf_harriers",
            batch_size=2,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.batch_size == 2
    assert summary.total_runs == 6
    assert summary.combination_summaries is not None
    assert [entry.monster_behavior for entry in summary.combination_summaries] == ["kind", "balanced", "evil"]


def test_giant_toad_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="giant-toad-combined-batch",
            enemy_preset_id="giant_toad_solo",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_marsh_predators_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="marsh-predators-combined-batch",
            enemy_preset_id="marsh_predators",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_predator_rampage_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="predator-rampage-combined-batch",
            enemy_preset_id="predator_rampage",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_bugbear_dragnet_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="bugbear-dragnet-combined-batch",
            enemy_preset_id="bugbear_dragnet",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_deadwatch_phalanx_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="deadwatch-phalanx-combined-batch",
            enemy_preset_id="deadwatch_phalanx",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_captains_crossfire_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="captains-crossfire-combined-batch",
            enemy_preset_id="captains_crossfire",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_reaction_bastion_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="reaction-bastion-combined-batch",
            enemy_preset_id="reaction_bastion",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_skyhunter_pincer_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="skyhunter-pincer-combined-batch",
            enemy_preset_id="skyhunter_pincer",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_hobgoblin_command_screen_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="hobgoblin-command-screen-combined-batch",
            enemy_preset_id="hobgoblin_command_screen",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None


def test_berserker_overrun_preset_runs_in_combined_batch_mode() -> None:
    summary = run_batch(
        EncounterConfig(
            seed="berserker-overrun-combined-batch",
            enemy_preset_id="berserker_overrun",
            batch_size=1,
            player_behavior="balanced",
            monster_behavior="combined",
        )
    )

    assert summary.total_runs == 3
    assert summary.combination_summaries is not None
