from __future__ import annotations

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
    assert run_party_validation.DEFAULT_SCENARIO_IDS == ("goblin_screen", "orc_push", "marsh_predators")
    assert run_party_validation.DEFAULT_BATCH_SIZE == 100
    assert run_party_validation.DEFAULT_PLAYER_BEHAVIOR == "balanced"
    assert run_party_validation.DEFAULT_MONSTER_BEHAVIOR == "combined"


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
