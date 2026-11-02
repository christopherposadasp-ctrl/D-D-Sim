from __future__ import annotations

from backend.engine import create_encounter
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import EncounterConfig, GridPosition
from scripts.investigate_smart_vs_dumb import (
    DiagnosticRow,
    build_config,
    capture_turn_decision_evidence,
    classify_delta,
    format_markdown,
    summarize_pair_results,
)
from tests.rules.action_assertions import assert_attack_action_core


def test_diagnostic_configs_pair_smart_and_dumb_on_the_same_seed() -> None:
    row = DiagnosticRow("fighter", "martial_mixed_party", "orc_push")

    smart = build_config(row, "balanced", "smart", 3)
    dumb = build_config(row, "balanced", "dumb", 3)

    assert smart.seed == dumb.seed
    assert smart.player_behavior == "smart"
    assert dumb.player_behavior == "dumb"
    assert smart.enemy_preset_id == "orc_push"
    assert smart.player_preset_id == "martial_mixed_party"


def test_diagnostic_classifies_large_paired_smart_underperformance() -> None:
    pairs = [
        {"smart": {"playerWon": False}, "dumb": {"playerWon": True}},
        {"smart": {"playerWon": False}, "dumb": {"playerWon": True}},
        {"smart": {"playerWon": True}, "dumb": {"playerWon": True}},
        {"smart": {"playerWon": False}, "dumb": {"playerWon": False}},
    ]

    summary = summarize_pair_results(pairs)

    assert summary["smartWinRate"] == 0.25
    assert summary["dumbWinRate"] == 0.75
    assert summary["classification"] == "confirmed_inversion"


def test_diagnostic_treats_small_negative_delta_as_needs_confirmation() -> None:
    assert classify_delta(-0.04, smart_loss_dumb_win=2, smart_win_dumb_loss=1) == "needs_confirmation"


def test_capture_turn_decision_evidence_records_target_and_square_metrics_for_fighter_dash_attack() -> None:
    encounter = create_encounter(EncounterConfig(seed="fighter-diagnostic-evidence", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=9, y=1)
    for unit_id, unit in encounter.units.items():
        if unit_id not in {"F1", "G1"}:
            unit.current_hp = 0
            unit.conditions.dead = True

    evidence = capture_turn_decision_evidence(encounter, "F1")

    assert evidence is not None
    assert evidence["decision"]["action"]["kind"] == "dash"
    assert_attack_action_core(evidence["decision"]["surgedAction"], target_id="G1", weapon_id="greatsword")
    assert evidence["chosenTargetId"] == "G1"
    assert evidence["topTargetAlternatives"][0]["targetId"] == "G1"
    assert evidence["topTargetAlternatives"][0]["killBand"] in {"none", "probable_finish", "sure_finish"}
    assert evidence["chosenSquare"]["endPosition"] == {"x": 8, "y": 1}
    assert "pressuredImmediatelyNextMonsterTurn" in evidence["chosenSquare"]
    assert evidence["actionSurgeTurn"]["mode"] == "dash_attack"
    assert evidence["actionSurgeTurn"]["chosenSquare"]["endPosition"] == {"x": 8, "y": 1}


def test_diagnostic_markdown_includes_counterexample_section_when_present() -> None:
    markdown = format_markdown(
        {
            "generatedAt": "2026-04-22T23:00:00",
            "overallStatus": "warn",
            "sampleSize": 1,
            "detailLimit": 1,
            "elapsedSeconds": 0.1,
            "results": [
                {
                    "class": "fighter",
                    "playerPresetId": "martial_mixed_party",
                    "scenarioId": "orc_push",
                    "monsterBehavior": "balanced",
                    "smartWinRate": 0.5,
                    "dumbWinRate": 0.5,
                    "delta": 0.0,
                    "classification": "no_inversion",
                    "smartLossDumbWin": 0,
                    "counterexampleDetailCount": 1,
                    "details": [],
                    "counterexampleDetails": [
                        {
                            "pairSeed": "seed-001",
                            "smart": {"winner": "fighters", "rounds": 5},
                            "dumb": {"winner": "goblins", "rounds": 6},
                        }
                    ],
                }
            ],
        }
    )

    assert "Smart vs Dumb Behavior Diagnostics" in markdown
    assert "Smart-Win / Dumb-Loss Counterexamples" in markdown
    assert "seed-001" in markdown
