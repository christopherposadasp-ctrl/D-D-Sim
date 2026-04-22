from __future__ import annotations

from backend.engine import run_encounter
from backend.engine.models.state import EncounterConfig
from backend.engine.services.barbarian_audit import (
    BarbarianAuditConfig,
    BarbarianAuditRow,
    build_full_barbarian_audit_config,
    build_preset_aggregates,
    build_quick_barbarian_audit_config,
    extract_barbarian_run_metrics,
    format_barbarian_audit_report,
    get_barbarian_audit_player_preset_ids,
    get_barbarian_audit_scenario_ids,
    review_fixed_seed_replays,
)


def test_barbarian_audit_profiles_expose_quick_and_full_defaults() -> None:
    quick = build_quick_barbarian_audit_config()
    full = build_full_barbarian_audit_config()

    assert quick == BarbarianAuditConfig(
        fixed_seed_runs=2,
        behavior_batch_size=10,
        health_batch_size=30,
        seed_prefix="barbarian-audit",
    )
    assert full == BarbarianAuditConfig()


def test_barbarian_audit_targets_cover_expected_presets_and_scenarios() -> None:
    assert get_barbarian_audit_player_preset_ids() == ("barbarian_level2_sample_trio", "martial_mixed_party")
    assert get_barbarian_audit_scenario_ids() == (
        "goblin_screen",
        "bandit_ambush",
        "mixed_patrol",
        "orc_push",
        "wolf_harriers",
        "marsh_predators",
    )


def test_extract_barbarian_run_metrics_reads_opening_rage_and_weapon_counts() -> None:
    result = run_encounter(
        EncounterConfig(
            seed="barbarian-audit-metrics",
            enemy_preset_id="goblin_screen",
            player_preset_id="barbarian_level2_sample_trio",
            player_behavior="smart",
            monster_behavior="balanced",
        )
    )

    metrics = extract_barbarian_run_metrics(result)

    assert metrics.opening_rage_opportunities >= 0
    assert metrics.opening_rage_successes >= 0
    assert metrics.opening_rage_successes <= metrics.opening_rage_opportunities
    assert metrics.greataxe_attack_count > 0
    assert metrics.handaxe_attack_count >= 0


def test_review_fixed_seed_replays_returns_seed_list_for_small_probe() -> None:
    issues, replay_seeds = review_fixed_seed_replays(
        "barbarian_level2_sample_trio",
        "goblin_screen",
        BarbarianAuditConfig(
            fixed_seed_runs=1,
            behavior_batch_size=1,
            health_batch_size=1,
            seed_prefix="barbarian-review-probe",
        ),
    )

    assert replay_seeds == [
        "barbarian-review-probe-barbarian_level2_sample_trio-goblin_screen-smart-00",
        "barbarian-review-probe-barbarian_level2_sample_trio-goblin_screen-dumb-00",
    ]
    assert all("skipped opening rage" not in issue for issue in issues)


def test_build_preset_aggregates_flags_smart_underperforming_dumb() -> None:
    rows = [
        BarbarianAuditRow(
            scenario_id="goblin_screen",
            scenario_display_name="Goblin Screen",
            player_preset_id="barbarian_level2_sample_trio",
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
            rage_opened_on_first_actionable_turn_rate=1.0,
            rage_dropped_without_qualifying_reason_count=0,
            rage_extended_count=0,
            greataxe_attack_count=10,
            handaxe_attack_count=1,
            turn_one_handaxe_count=0,
            cleave_trigger_count=2,
            vex_applied_count=1,
            vex_consumed_count=1,
            damage_resisted_total=4,
            temporary_hp_absorbed_total=1,
            barbarian_downed_count=0,
            barbarian_death_count=0,
            status="warn",
            recommendation="Inspect flanking pathing and target ranking before touching numbers.",
        )
    ]

    aggregates = build_preset_aggregates(rows)

    assert aggregates[0].status == "fail"
    assert aggregates[0].warnings == ["Smart players underperformed dumb players in the aggregate combined pass."]


def test_format_barbarian_audit_report_includes_core_sections() -> None:
    row = BarbarianAuditRow(
        scenario_id="goblin_screen",
        scenario_display_name="Goblin Screen",
        player_preset_id="barbarian_level2_sample_trio",
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
        rage_opened_on_first_actionable_turn_rate=1.0,
        rage_dropped_without_qualifying_reason_count=0,
        rage_extended_count=0,
        greataxe_attack_count=10,
        handaxe_attack_count=1,
        turn_one_handaxe_count=0,
        cleave_trigger_count=2,
        vex_applied_count=1,
        vex_consumed_count=1,
        damage_resisted_total=4,
        temporary_hp_absorbed_total=1,
        barbarian_downed_count=0,
        barbarian_death_count=0,
        status="pass",
        recommendation=None,
        warnings=[],
        failures=[],
    )

    report = format_barbarian_audit_report(
        [row],
        build_preset_aggregates([row]),
        rules_gate={"status": "pass", "command": "pytest", "stdoutTail": []},
    )

    assert "## Rules Gate" in report
    assert "## Preset Aggregates" in report
    assert "## Scenario Rows" in report
    assert "barbarian_level2_sample_trio" in report
