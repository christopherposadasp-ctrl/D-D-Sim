from __future__ import annotations

from scripts import run_pc_tuning_sample


def test_pc_tuning_sample_defaults_to_paladin_standard_battery() -> None:
    assert run_pc_tuning_sample.DEFAULT_PROFILE == "paladin"
    assert run_pc_tuning_sample.DEFAULT_UNIT_ID == "F2"
    assert run_pc_tuning_sample.DEFAULT_RUNS_PER_SCENARIO == 60
    assert run_pc_tuning_sample.DEFAULT_PLAYER_BEHAVIOR == "smart"
    assert run_pc_tuning_sample.DEFAULT_MONSTER_BEHAVIOR == "balanced"
    assert run_pc_tuning_sample.DEFAULT_SCENARIO_IDS == (
        "hobgoblin_kill_box",
        "bugbear_dragnet",
        "deadwatch_phalanx",
    )


def test_pc_tuning_sample_summary_tracks_paladin_resources_and_feature_rates() -> None:
    metrics = run_pc_tuning_sample.new_metrics()
    metrics["runs"] = 2
    metrics["wins"].update({"fighters": 1, "goblins": 1})
    metrics["rounds"].extend([5, 7])
    metrics["endingSpellSlots"].extend([0, 3])
    metrics["endingSpellSlotsLevel1"].extend([0, 2])
    metrics["endingSpellSlotsLevel2"].extend([0, 1])
    metrics["endingLayOnHands"].extend([0, 4])
    metrics["divineSmites"] = 3
    metrics["sentinelGuardianTriggers"] = 4
    metrics["sentinelHaltApplied"] = 2
    metrics["naturesWrathUses"] = 2
    metrics["naturesWrathTargets"].extend([4, 6])
    metrics["naturesWrathRestrained"].extend([2, 3])
    metrics["layOnHandsUses"] = 3
    metrics["layOnHandsTotalHealing"] = 21
    metrics["layOnHandsHeals"].extend([4, 7, 10])
    metrics["layOnHandsDownedPickups"] = 2
    metrics["cureWoundsUses"] = 1
    metrics["cureWoundsTotalHealing"] = 8
    metrics["cureWoundsHeals"].append(8)

    summary = run_pc_tuning_sample.summarize_metrics(metrics)

    assert summary["playerWinRate"] == 50.0
    assert summary["averageRounds"] == 6
    assert summary["runsWithUnusedSpellSlots"] == 1
    assert summary["averageEndingSpellSlots"] == 1.5
    assert summary["averageEndingSpellSlotsLevel1"] == 1
    assert summary["averageEndingSpellSlotsLevel2"] == 0.5
    assert summary["runsWithUnusedLayOnHands"] == 1
    assert summary["averageEndingLayOnHands"] == 2
    assert summary["divineSmites"] == 3
    assert summary["sentinelHaltPerGuardianRate"] == 50.0
    assert summary["naturesWrathAverageTargets"] == 5
    assert summary["naturesWrathAverageRestrained"] == 2.5
    assert summary["naturesWrathRestrainedTargetRate"] == 50.0
    assert summary["layOnHandsAverageHeal"] == 7
    assert summary["layOnHandsDownedPickups"] == 2
    assert summary["cureWoundsAverageHeal"] == 8
