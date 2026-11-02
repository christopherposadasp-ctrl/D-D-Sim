from __future__ import annotations

from backend.engine import run_encounter
from backend.engine.models.state import EncounterConfig
from backend.engine.services.fighter_audit import (
    FighterAuditConfig,
    FighterAuditRow,
    build_full_fighter_audit_config,
    build_preset_aggregates,
    build_quick_fighter_audit_config,
    classify_smart_underperformance,
    extract_fighter_run_metrics,
    format_fighter_audit_report,
    get_fighter_audit_player_preset_ids,
    get_fighter_audit_scenario_ids,
    review_fixed_seed_replays,
)


def test_fighter_audit_profiles_expose_quick_and_full_defaults() -> None:
    quick = build_quick_fighter_audit_config()
    full = build_full_fighter_audit_config()

    assert quick == FighterAuditConfig(
        fixed_seed_runs=1,
        behavior_batch_size=5,
        health_batch_size=15,
        seed_prefix="fighter-audit",
    )
    assert full == FighterAuditConfig()


def test_fighter_audit_targets_cover_expected_presets_and_scenarios() -> None:
    assert get_fighter_audit_player_preset_ids() == ("fighter_level2_sample_trio", "martial_mixed_party")
    assert get_fighter_audit_scenario_ids() == (
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
    )


def test_extract_fighter_run_metrics_reads_action_surge_and_weapon_counts() -> None:
    result = run_encounter(
        EncounterConfig(
            seed="fighter-audit-metrics",
            enemy_preset_id="goblin_screen",
            player_preset_id="fighter_level2_sample_trio",
            player_behavior="smart",
            monster_behavior="balanced",
        )
    )

    metrics = extract_fighter_run_metrics(result)

    assert metrics.opening_action_surge_opportunities >= 0
    assert metrics.opening_action_surge_successes >= 0
    assert metrics.opening_action_surge_successes <= metrics.opening_action_surge_opportunities
    assert metrics.greatsword_attack_count > 0
    assert metrics.javelin_attack_count >= 0


def test_review_fixed_seed_replays_returns_seed_list_for_small_probe() -> None:
    issues, replay_seeds = review_fixed_seed_replays(
        "fighter_level2_sample_trio",
        "goblin_screen",
        FighterAuditConfig(
            fixed_seed_runs=1,
            behavior_batch_size=1,
            health_batch_size=1,
            seed_prefix="fighter-review-probe",
        ),
    )

    assert replay_seeds == [
        "fighter-review-probe-fighter_level2_sample_trio-goblin_screen-smart-00",
        "fighter-review-probe-fighter_level2_sample_trio-goblin_screen-dumb-00",
    ]
    assert all("double-javelin" not in issue for issue in issues)


def test_follow_up_javelin_after_melee_action_surge_is_not_counted_as_round_one_opener() -> None:
    result = run_encounter(
        EncounterConfig(
            seed="fighter-audit-martial_mixed_party-goblin_screen-dumb-00",
            enemy_preset_id="goblin_screen",
            player_preset_id="martial_mixed_party",
            player_behavior="dumb",
            monster_behavior="balanced",
        )
    )

    metrics = extract_fighter_run_metrics(result)

    assert metrics.javelin_attack_count >= 1
    assert metrics.turn_one_javelin_count == 0


def test_build_preset_aggregates_flags_smart_underperforming_dumb() -> None:
    rows = [
        FighterAuditRow(
            scenario_id="goblin_screen",
            scenario_display_name="Goblin Screen",
            player_preset_id="fighter_level2_sample_trio",
            enemy_preset_id="goblin_screen",
            player_behavior="balanced",
            monster_behavior="combined",
            total_runs=900,
            smart_run_count=450,
            dumb_run_count=450,
            player_win_rate=0.6,
            smart_player_win_rate=0.5,
            dumb_player_win_rate=0.7,
            average_rounds=5.0,
            average_fighter_deaths=1.0,
            counter_run_count=300,
            opening_action_surge_rate=1.0,
            action_surge_use_count=4,
            greatsword_attack_count=10,
            javelin_attack_count=1,
            turn_one_javelin_count=0,
            dash_action_surge_attack_count=2,
            double_melee_action_surge_turn_count=3,
            double_javelin_action_surge_turn_count=0,
            second_wind_use_count=1,
            fighter_downed_count=0,
            fighter_death_count=0,
            status="warn",
            recommendation="Inspect flanking pathing and target ranking before touching numbers.",
        )
    ]

    aggregates = build_preset_aggregates(rows)

    assert aggregates[0].status == "fail"
    assert aggregates[0].notes == []
    assert aggregates[0].warnings == []
    assert len(aggregates[0].failures) == 1
    assert "aggregate combined pass" in aggregates[0].failures[0]
    assert "delta 20.0 pts" in aggregates[0].failures[0]


def test_smart_underperformance_classifies_small_sample_signal_as_note() -> None:
    assert classify_smart_underperformance(0.80, 0.8666666666666667, 45, 45) == "note"


def test_smart_underperformance_classifies_small_sample_gap_as_warn() -> None:
    assert classify_smart_underperformance(0.8, 0.9111111111111111, 45, 45) == "warn"


def test_smart_underperformance_classifies_large_sample_gap_as_warn() -> None:
    assert classify_smart_underperformance(0.5, 0.58, 450, 450) == "warn"


def test_smart_underperformance_classifies_large_sample_gap_as_fail() -> None:
    assert classify_smart_underperformance(0.5, 0.7, 450, 450) == "fail"


def test_format_fighter_audit_report_includes_core_sections() -> None:
    row = FighterAuditRow(
        scenario_id="goblin_screen",
        scenario_display_name="Goblin Screen",
        player_preset_id="fighter_level2_sample_trio",
        enemy_preset_id="goblin_screen",
        player_behavior="balanced",
        monster_behavior="combined",
        total_runs=900,
        smart_run_count=450,
        dumb_run_count=450,
        player_win_rate=0.6,
        smart_player_win_rate=0.65,
        dumb_player_win_rate=0.55,
        average_rounds=5.0,
        average_fighter_deaths=1.0,
        counter_run_count=300,
        opening_action_surge_rate=1.0,
        action_surge_use_count=4,
        greatsword_attack_count=10,
        javelin_attack_count=1,
        turn_one_javelin_count=0,
        dash_action_surge_attack_count=2,
        double_melee_action_surge_turn_count=3,
        double_javelin_action_surge_turn_count=0,
        second_wind_use_count=1,
        fighter_downed_count=0,
        fighter_death_count=0,
        status="pass",
        recommendation=None,
        notes=["Smart players underperformed dumb players in the combined pass (smart 50.0%, dumb 56.0%, delta 6.0 pts over 100 vs 100 runs; z=1.00)."],
        warnings=[],
        failures=[],
    )

    report = format_fighter_audit_report(
        [row],
        build_preset_aggregates([row]),
        rules_gate={"status": "pass", "command": "pytest", "stdoutTail": []},
    )

    assert "## Rules Gate" in report
    assert "## Preset Aggregates" in report
    assert "## Scenario Rows" in report
    assert "fighter_level2_sample_trio" in report
    assert "- note: Smart players underperformed dumb players" in report
