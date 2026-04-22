from __future__ import annotations

import pytest

from backend.content.enemies import get_enemy_preset
from backend.engine import create_encounter, run_batch
from backend.engine.models.state import EncounterConfig


def test_preset_default_layout_builds_expected_units() -> None:
    encounter = create_encounter(EncounterConfig(seed="preset-default", enemy_preset_id="goblin_screen"))
    preset = get_enemy_preset("goblin_screen")

    assert sorted(encounter.units) == ["E1", "E2", "E3", "E4", "E5", "E6", "F1", "F2", "F3", "F4"]
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


def test_hobgoblin_kill_box_builds_eight_enemy_units() -> None:
    encounter = create_encounter(EncounterConfig(seed="hobgoblin-kill-box", enemy_preset_id="hobgoblin_kill_box"))

    assert sorted(encounter.units) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "F1", "F2", "F3", "F4"]
    assert encounter.units["E1"].combat_role == "hobgoblin_melee"
    assert encounter.units["E5"].combat_role == "hobgoblin_archer"
    assert encounter.units["E8"].combat_role == "goblin_boss"


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
