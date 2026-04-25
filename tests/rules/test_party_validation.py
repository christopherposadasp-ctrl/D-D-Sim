from __future__ import annotations

from types import SimpleNamespace

from backend.engine.models.state import BatchSummary
from backend.engine.services import barbarian_audit, fighter_audit
from backend.engine.services.barbarian_audit import BarbarianAuditConfig
from backend.engine.services.fighter_audit import FighterAuditConfig
from scripts import run_party_validation


def make_batch_summary(seed: str = "party-validation-test") -> BatchSummary:
    return BatchSummary(
        seed=seed,
        player_behavior="balanced",
        monster_behavior="combined",
        batch_size=1,
        total_runs=3,
        player_win_rate=1,
        goblin_win_rate=0,
        mutual_annihilation_rate=0,
        smart_player_win_rate=1,
        dumb_player_win_rate=1,
        smart_run_count=2,
        dumb_run_count=1,
        average_rounds=3,
        average_fighter_deaths=0,
        average_goblins_killed=2,
        average_remaining_fighter_hp=20,
        average_remaining_goblin_hp=0,
        stable_but_unconscious_count=0,
        combination_summaries=None,
    )


def test_party_validation_defaults_are_focused_on_current_party() -> None:
    assert run_party_validation.DEFAULT_SCENARIO_IDS == ("hobgoblin_kill_box", "bugbear_dragnet", "deadwatch_phalanx")
    assert run_party_validation.DEFAULT_BATCH_SIZE == 400
    assert run_party_validation.DEFAULT_PLAYER_BEHAVIOR == "balanced"
    assert run_party_validation.DEFAULT_MONSTER_BEHAVIOR == "combined"
    assert run_party_validation.DEFAULT_REPLAY_SMOKE_RUNS == 2


def test_party_validation_combined_batch_plan_preserves_requested_total_runs() -> None:
    assert run_party_validation.build_batch_run_plan(400, "combined") == (
        ("kind", 133),
        ("balanced", 134),
        ("evil", 133),
    )
    assert run_party_validation.build_batch_run_plan(400, "balanced") == (("balanced", 400),)


def test_party_validation_report_shape_is_stable(monkeypatch) -> None:
    monkeypatch.setattr(
        run_party_validation,
        "collect_git_context",
        lambda repo_root: {"generatedAt": "test", "branch": "test", "commit": "test", "gitStatusShort": []},
    )

    payload = run_party_validation.build_report_payload(
        player_preset_id="martial_mixed_party",
        scenario_ids=("goblin_screen",),
        batch_size=100,
        execution_mode="parallel",
        worker_count=8,
        total_runs=300,
        elapsed_seconds=1.25,
        rules_gate={"status": "pass", "command": "pytest", "exitCode": 0, "stdoutTail": []},
        replay_rows=[],
        batch_rows=[],
        feature_evidence=[],
        issue_list=[],
    )

    assert payload["overallStatus"] == "pass"
    assert payload["playerPresetId"] == "martial_mixed_party"
    assert payload["scenarioIds"] == ["goblin_screen"]
    assert payload["executionMode"] == "parallel"
    assert payload["workerCount"] == 8
    assert set(payload) >= {
        "rulesGate",
        "replayRows",
        "batchRows",
        "featureEvidence",
        "issueList",
    }


def test_party_validation_console_summary_includes_batch_results() -> None:
    payload = run_party_validation.build_report_payload(
        player_preset_id="martial_mixed_party",
        scenario_ids=("hobgoblin_kill_box",),
        batch_size=400,
        execution_mode="serial",
        worker_count=1,
        total_runs=400,
        elapsed_seconds=1.25,
        rules_gate={"status": "pass", "command": "pytest", "exitCode": 0, "stdoutTail": []},
        replay_rows=[],
        batch_rows=[
            {
                "scenarioId": "hobgoblin_kill_box",
                "playerBehavior": "balanced",
                "monsterBehavior": "combined",
                "batchSize": 400,
                "totalRuns": 400,
                "playerWinRate": 0.125,
                "enemyWinRate": 0.875,
                "smartPlayerWinRate": 0.2,
                "dumbPlayerWinRate": 0.05,
                "smartRunCount": 200,
                "dumbRunCount": 200,
                "averageRounds": 4.5,
                "averageFighterDeaths": 2.0,
                "averagePartyDead": 2.0,
                "executionMode": "serial",
                "workerCount": 1,
                "elapsedSeconds": 1.25,
                "status": "pass",
                "behaviorBreakdown": [
                    {
                        "monsterBehavior": "kind",
                        "batchSize": 133,
                        "totalRuns": 133,
                        "playerWinRate": 0.2,
                        "enemyWinRate": 0.8,
                        "smartPlayerWinRate": 0.3,
                        "dumbPlayerWinRate": 0.1,
                        "smartRunCount": 67,
                        "dumbRunCount": 66,
                        "averageRounds": 4.2,
                        "averagePartyDead": 1.6,
                    },
                    {
                        "monsterBehavior": "balanced",
                        "batchSize": 134,
                        "totalRuns": 134,
                        "playerWinRate": 0.125,
                        "enemyWinRate": 0.875,
                        "smartPlayerWinRate": 0.2,
                        "dumbPlayerWinRate": 0.05,
                        "smartRunCount": 67,
                        "dumbRunCount": 67,
                        "averageRounds": 4.5,
                        "averagePartyDead": 2.0,
                    },
                    {
                        "monsterBehavior": "evil",
                        "batchSize": 133,
                        "totalRuns": 133,
                        "playerWinRate": 0.05,
                        "enemyWinRate": 0.95,
                        "smartPlayerWinRate": 0.1,
                        "dumbPlayerWinRate": 0.0,
                        "smartRunCount": 67,
                        "dumbRunCount": 66,
                        "averageRounds": 4.8,
                        "averagePartyDead": 2.5,
                    },
                ],
            }
        ],
        feature_evidence=[],
        issue_list=[],
    )

    summary = run_party_validation.format_console_summary(payload)

    assert "Batch summary:" in summary
    assert "playerBehavior: balanced" in summary
    assert "monsterBehavior: combined" in summary
    assert "hobgoblin_kill_box: players 12.5%, enemies 87.5%, smart 20.0%, dumb 5.0%, avg rounds 4.5, avg party dead 2.0" in summary
    assert "kind: smart 30.0%, dumb 10.0%, players 20.0%, enemies 80.0%, avg rounds 4.2, avg party dead 1.6" in summary
    assert "balanced: smart 20.0%, dumb 5.0%, players 12.5%, enemies 87.5%, avg rounds 4.5, avg party dead 2.0" in summary
    assert "evil: smart 10.0%, dumb 0.0%, players 5.0%, enemies 95.0%, avg rounds 4.8, avg party dead 2.5" in summary


def test_party_validation_cli_accepts_serial_and_worker_controls(monkeypatch) -> None:
    monkeypatch.setattr(
        run_party_validation.sys,
        "argv",
        ["run_party_validation.py", "--serial", "--workers", "4", "--scenario", "orc_push"],
    )

    args = run_party_validation.parse_args()

    assert args.serial is True
    assert args.workers == 4
    assert args.scenario_ids == ["orc_push"]


def test_party_validation_failures_drive_overall_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        run_party_validation,
        "collect_git_context",
        lambda repo_root: {"generatedAt": "test", "branch": "test", "commit": "test", "gitStatusShort": []},
    )

    payload = run_party_validation.build_report_payload(
        player_preset_id="martial_mixed_party",
        scenario_ids=("goblin_screen",),
        batch_size=100,
        execution_mode="parallel",
        worker_count=8,
        total_runs=300,
        elapsed_seconds=1.25,
        rules_gate={"status": "pass", "command": "pytest", "exitCode": 0, "stdoutTail": []},
        replay_rows=[],
        batch_rows=[],
        feature_evidence=[],
        issue_list=[{"severity": "fail", "section": "batchHealth", "message": "failed"}],
    )

    assert payload["overallStatus"] == "fail"


def test_replay_smoke_runs_each_scenario_twice() -> None:
    def fake_run_encounter(config):
        return SimpleNamespace(
            final_state=SimpleNamespace(
                player_behavior=config.player_behavior,
                monster_behavior=config.monster_behavior,
                terminal_state="complete",
            ),
            events=[1, 2, 3],
        )

    def fake_summarize_encounter(final_state):
        return SimpleNamespace(winner="fighters", rounds=4)

    original_run_encounter = run_party_validation.run_encounter
    original_summarize_encounter = run_party_validation.summarize_encounter
    run_party_validation.run_encounter = fake_run_encounter
    run_party_validation.summarize_encounter = fake_summarize_encounter
    try:
        rows, results, issues = run_party_validation.run_replay_smoke(
            "martial_mixed_party",
            ("hobgoblin_kill_box",),
            "balanced",
            2,
        )
    finally:
        run_party_validation.run_encounter = original_run_encounter
        run_party_validation.summarize_encounter = original_summarize_encounter

    assert [row["seed"] for row in rows] == [
        "party-validation-martial_mixed_party-hobgoblin_kill_box-replay-00",
        "party-validation-martial_mixed_party-hobgoblin_kill_box-replay-01",
    ]
    assert len(results) == 2
    assert issues == []


def test_batch_health_splits_combined_totals_evenly(monkeypatch) -> None:
    calls = []

    def fake_run_batch(config, force_serial=False, worker_count=None):
        calls.append((config.monster_behavior, config.batch_size))
        return make_batch_summary(config.seed).model_copy(
            update={
                "player_behavior": config.player_behavior,
                "monster_behavior": config.monster_behavior,
                "batch_size": config.batch_size,
                "total_runs": config.batch_size,
                "smart_run_count": config.batch_size // 2,
                "dumb_run_count": config.batch_size - (config.batch_size // 2),
            }
        )

    monkeypatch.setattr(run_party_validation, "run_batch", fake_run_batch)

    rows, issues, _ = run_party_validation.run_batch_health(
        "martial_mixed_party",
        ("hobgoblin_kill_box",),
        400,
        "balanced",
        "combined",
        True,
        None,
    )

    assert calls == [("kind", 133), ("balanced", 134), ("evil", 133)]
    assert rows[0]["monsterBehavior"] == "combined"
    assert rows[0]["totalRuns"] == 400
    assert [entry["monsterBehavior"] for entry in rows[0]["behaviorBreakdown"]] == ["kind", "balanced", "evil"]
    assert issues == []


def test_fighter_health_pass_uses_default_batch_entrypoint(monkeypatch) -> None:
    calls = {}

    def fake_run_batch(config, progress_callback=None):
        calls["config"] = config
        calls["progressCallback"] = progress_callback
        return make_batch_summary(config.seed)

    monkeypatch.setattr(fighter_audit, "run_batch", fake_run_batch)

    summary = fighter_audit.run_health_pass(
        "fighter_level2_sample_trio",
        "goblin_screen",
        FighterAuditConfig(fixed_seed_runs=0, behavior_batch_size=0, health_batch_size=7),
    )

    assert summary.seed == "fighter-audit-fighter_level2_sample_trio-goblin_screen-health"
    assert calls["config"].batch_size == 7
    assert calls["config"].monster_behavior == "combined"
    assert calls["progressCallback"] is None


def test_barbarian_health_pass_uses_default_batch_entrypoint(monkeypatch) -> None:
    calls = {}

    def fake_run_batch(config, progress_callback=None):
        calls["config"] = config
        calls["progressCallback"] = progress_callback
        return make_batch_summary(config.seed)

    monkeypatch.setattr(barbarian_audit, "run_batch", fake_run_batch)

    summary = barbarian_audit.run_health_pass(
        "barbarian_level2_sample_trio",
        "goblin_screen",
        BarbarianAuditConfig(fixed_seed_runs=0, behavior_batch_size=0, health_batch_size=9),
    )

    assert summary.seed == "barbarian-audit-barbarian_level2_sample_trio-goblin_screen-health"
    assert calls["config"].batch_size == 9
    assert calls["config"].monster_behavior == "combined"
    assert calls["progressCallback"] is None
