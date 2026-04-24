from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_pass2_stability.py"
MODULE_SPEC = importlib.util.spec_from_file_location("run_pass2_stability", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
pass2_stability = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = pass2_stability
MODULE_SPEC.loader.exec_module(pass2_stability)


def test_deterministic_row_comparison_reports_pass_on_exact_match() -> None:
    row = pass2_stability.make_comparison_row(
        kind="replay",
        row_id="rogue_level2_ranged_trio/orc_push/balanced",
        player_preset_id="rogue_level2_ranged_trio",
        scenario_id="orc_push",
        seed="seed",
        first={"summary": {"winner": "fighters"}, "events": [{"id": 1}]},
        second={"summary": {"winner": "fighters"}, "events": [{"id": 1}]},
    )

    payload = row.to_payload()

    assert payload["status"] == "pass"
    assert "mismatch" not in payload


def test_replay_mismatch_becomes_fail_with_first_mismatch_path() -> None:
    row = pass2_stability.make_comparison_row(
        kind="replay",
        row_id="rogue_level2_ranged_trio/orc_push/balanced",
        player_preset_id="rogue_level2_ranged_trio",
        scenario_id="orc_push",
        seed="seed",
        first={"summary": {"winner": "fighters"}, "events": [{"id": 1}]},
        second={"summary": {"winner": "goblins"}, "events": [{"id": 1}]},
    )

    payload = row.to_payload()

    assert payload["status"] == "fail"
    assert payload["mismatch"]["path"] == "$.summary.winner"


def test_batch_summary_mismatch_becomes_fail() -> None:
    row = pass2_stability.make_comparison_row(
        kind="batch",
        row_id="rogue_level2_ranged_trio/orc_push/combined",
        player_preset_id="rogue_level2_ranged_trio",
        scenario_id="orc_push",
        seed="seed",
        first={"totalRuns": 6, "playerWinRate": 0.5},
        second={"totalRuns": 6, "playerWinRate": 0.667},
    )

    payload = row.to_payload()

    assert payload["status"] == "fail"
    assert payload["mismatch"]["path"] == "$.playerWinRate"


def test_async_progress_regression_becomes_fail_signal() -> None:
    assert pass2_stability.detect_progress_regression([0, 1, 3, 2]) is True
    assert pass2_stability.detect_progress_regression([0, 0, 2, 3]) is False


def test_async_rows_respect_restricted_smoke_matrix() -> None:
    rows = pass2_stability.select_async_rows(
        player_preset_ids=["rogue_level2_ranged_trio"],
        scenario_ids=["orc_push"],
        restricted=True,
    )

    assert rows == [("rogue_level2_ranged_trio", "orc_push")]


def test_known_warnings_produce_warn_not_fail() -> None:
    status = pass2_stability.determine_overall_status(
        replay_rows=[{"status": "pass"}],
        batch_rows=[{"status": "pass"}],
        async_rows=[{"status": "pass"}],
        command_rows=[{"status": "pass"}],
        known_warnings=[{"id": "fighter_martial_mixed_party_orc_push"}],
    )

    assert status == "warn"


def test_failure_overrides_known_warning() -> None:
    status = pass2_stability.determine_overall_status(
        replay_rows=[{"status": "fail"}],
        batch_rows=[{"status": "pass"}],
        async_rows=[{"status": "pass"}],
        command_rows=[{"status": "pass"}],
        known_warnings=[{"id": "fighter_martial_mixed_party_orc_push"}],
    )

    assert status == "fail"


def test_report_payload_and_markdown_include_commit_status_waivers_and_artifacts(tmp_path: Path) -> None:
    json_path = tmp_path / "pass2.json"
    markdown_path = tmp_path / "pass2.md"
    payload = pass2_stability.build_report_payload(
        context={
            "generatedAt": "2026-04-23T12:00:00+00:00",
            "branch": "integration",
            "commit": "01cecc3",
            "gitStatusShort": [],
        },
        replay_rows=[{"status": "pass", "rowId": "replay"}],
        batch_rows=[{"status": "pass", "rowId": "batch"}],
        async_rows=[{"status": "pass", "rowId": "async"}],
        command_rows=[{"status": "pass", "rowId": "audit"}],
        json_path=json_path,
        markdown_path=markdown_path,
    )

    markdown = pass2_stability.format_report_markdown(payload)

    assert payload["context"]["commit"] == "01cecc3"
    assert payload["overallStatus"] == "warn"
    assert payload["artifactPaths"]["json"].endswith("pass2.json")
    assert "monk_audit_runner_missing" in {waiver["id"] for waiver in payload["waivers"]}
    assert "Overall status: `warn`" in markdown
    assert "Commit: `01cecc3`" in markdown
    assert "pass2.json" in markdown
    assert "monster_audit_runner_missing" in markdown
