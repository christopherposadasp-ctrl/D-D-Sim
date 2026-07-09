from __future__ import annotations

from backend.engine import run_encounter
from backend.engine.models.state import EncounterConfig
from backend.engine.services.rogue_audit import (
    RogueAuditConfig,
    RogueAuditRow,
    build_full_rogue_audit_config,
    build_preset_aggregates,
    build_quick_rogue_audit_config,
    classify_smart_underperformance,
    extract_rogue_run_metrics,
    format_rogue_audit_report,
    get_rogue_audit_player_preset_ids,
    get_rogue_audit_scenario_ids,
    review_signature_probes,
)


def test_rogue_audit_profiles_expose_quick_and_full_defaults() -> None:
    quick = build_quick_rogue_audit_config()
    full = build_full_rogue_audit_config()

    assert quick == RogueAuditConfig(signature_probe_runs=1, health_batch_size=12, seed_prefix="rogue-audit")
    assert full == RogueAuditConfig(signature_probe_runs=2, health_batch_size=40, seed_prefix="rogue-audit")


def test_rogue_audit_targets_cover_expected_preset_and_scenarios() -> None:
    assert get_rogue_audit_player_preset_ids() == ("rogue_level2_ranged_trio",)
    assert get_rogue_audit_scenario_ids() == (
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


def test_extract_rogue_run_metrics_reads_sneak_attack_and_hide_counts() -> None:
    result = run_encounter(
        EncounterConfig(
            seed="rogue-audit-metrics",
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
            monster_behavior="balanced",
        )
    )

    metrics = extract_rogue_run_metrics(result)

    assert metrics.sneak_attack_applied_count >= 0
    assert metrics.sneak_attack_turn_count >= 0
    assert metrics.sneak_attack_missed_opportunity_count >= 0
    assert metrics.shortbow_attack_count > 0
    assert metrics.hide_attempt_count >= 0
    assert metrics.hide_success_count <= metrics.hide_attempt_count


def test_review_signature_probes_passes_quick_probe_set() -> None:
    probes = review_signature_probes(
        RogueAuditConfig(signature_probe_runs=1, health_batch_size=1, seed_prefix="rogue-review-probe")
    )

    assert len(probes) == 5
    assert all(probe.status == "pass" for probe in probes)
    sneak_probe = next(probe for probe in probes if probe.probe_id == "sneak_attack_target_choice")
    assert sneak_probe.sneak_attack_expected is True
    assert sneak_probe.sneak_attack_applied is True
    hide_probe = next(probe for probe in probes if probe.probe_id == "hide_before_attack")
    assert hide_probe.hide_attempted is True
    assert hide_probe.hide_succeeded is True


def test_build_preset_aggregates_flags_smart_underperforming_dumb() -> None:
    rows = [
        RogueAuditRow(
            scenario_id="goblin_screen",
            scenario_display_name="Goblin Screen",
            player_preset_id="rogue_level2_ranged_trio",
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
            sneak_attack_applied_count=10,
            sneak_attack_turn_count=10,
            multiple_sneak_attacks_same_turn_count=0,
            sneak_attack_eligible_hit_count=10,
            sneak_attack_missed_opportunity_count=0,
            shortbow_attack_count=20,
            shortsword_fallback_count=0,
            hide_attempt_count=6,
            hide_success_count=4,
            hide_success_rate=4 / 6,
            hide_before_attack_count=2,
            hide_before_attack_success_count=2,
            hide_after_attack_count=4,
            hide_after_attack_success_count=2,
            disengage_into_attack_count=1,
            bonus_dash_into_attack_count=1,
            turns_ending_hidden_count=3,
            rogue_downed_count=0,
            rogue_death_count=0,
            status="warn",
            recommendation="Inspect Rogue target selection and escape timing before touching numbers.",
        )
    ]

    aggregates = build_preset_aggregates(rows)

    assert aggregates[0].status == "fail"
    assert len(aggregates[0].failures) == 1
    assert "aggregate combined pass" in aggregates[0].failures[0]


def test_smart_underperformance_classifies_small_sample_signal_as_note() -> None:
    assert classify_smart_underperformance(0.80, 0.8666666666666667, 45, 45) == "note"


def test_smart_underperformance_classifies_small_sample_gap_as_warn() -> None:
    assert classify_smart_underperformance(0.8, 0.9111111111111111, 45, 45) == "warn"


def test_smart_underperformance_classifies_large_sample_gap_as_fail() -> None:
    assert classify_smart_underperformance(0.5, 0.7, 450, 450) == "fail"


def test_format_rogue_audit_report_includes_signature_probe_section() -> None:
    row = RogueAuditRow(
        scenario_id="goblin_screen",
        scenario_display_name="Goblin Screen",
        player_preset_id="rogue_level2_ranged_trio",
        enemy_preset_id="goblin_screen",
        player_behavior="balanced",
        monster_behavior="combined",
        total_runs=60,
        smart_run_count=30,
        dumb_run_count=30,
        player_win_rate=0.6,
        smart_player_win_rate=0.65,
        dumb_player_win_rate=0.55,
        average_rounds=5.0,
        average_fighter_deaths=1.0,
        sneak_attack_applied_count=8,
        sneak_attack_turn_count=8,
        multiple_sneak_attacks_same_turn_count=0,
        sneak_attack_eligible_hit_count=8,
        sneak_attack_missed_opportunity_count=0,
        shortbow_attack_count=12,
        shortsword_fallback_count=1,
        hide_attempt_count=4,
        hide_success_count=3,
        hide_success_rate=0.75,
        hide_before_attack_count=1,
        hide_before_attack_success_count=1,
        hide_after_attack_count=3,
        hide_after_attack_success_count=2,
        disengage_into_attack_count=1,
        bonus_dash_into_attack_count=1,
        turns_ending_hidden_count=2,
        rogue_downed_count=0,
        rogue_death_count=0,
        status="pass",
        recommendation=None,
        notes=[],
        warnings=[],
        failures=[],
    )

    probes = review_signature_probes(
        RogueAuditConfig(signature_probe_runs=1, health_batch_size=1, seed_prefix="rogue-report-probe")
    )
    report = format_rogue_audit_report(
        [row],
        probes,
        build_preset_aggregates([row]),
        rules_gate={"status": "pass", "command": "pytest", "stdoutTail": []},
    )

    assert "## Rules Gate" in report
    assert "## Signature Probes" in report
    assert "## Preset Aggregates" in report
    assert "## Scenario Rows" in report
    assert "rogue_level2_ranged_trio" in report
