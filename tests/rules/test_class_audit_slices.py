from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.run_class_audit_slices import (
    ClassAuditSlice,
    build_slice_command,
    build_slices,
    build_summary,
    normalize_classes,
    run_slice,
)


def build_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    defaults = {
        "report_dir": tmp_path,
        "include_rules_gate": False,
        "fixed_seed_runs": None,
        "behavior_batch_size": None,
        "health_batch_size": None,
        "force": False,
        "dry_run": False,
        "timeout_seconds": 5.0,
        "profile": "quick",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_build_slices_defaults_to_fighter_and_barbarian_matrix() -> None:
    slices = build_slices(normalize_classes(None), "quick")

    assert len(slices) == 44
    assert slices[0] == ClassAuditSlice("fighter", "quick", "fighter_level2_sample_trio", "goblin_screen")
    assert slices[-1] == ClassAuditSlice("barbarian", "quick", "martial_mixed_party", "captains_crossfire")


def test_build_slices_can_limit_smoke_subset() -> None:
    slices = build_slices(
        ("fighter", "barbarian"),
        "quick",
        scenario_ids=["goblin_screen", "bandit_ambush"],
        player_preset_ids=["martial_mixed_party"],
        max_slices=3,
    )

    assert slices == [
        ClassAuditSlice("fighter", "quick", "martial_mixed_party", "goblin_screen"),
        ClassAuditSlice("fighter", "quick", "martial_mixed_party", "bandit_ambush"),
        ClassAuditSlice("barbarian", "quick", "martial_mixed_party", "goblin_screen"),
    ]


def test_build_slice_command_uses_existing_runner_with_explicit_slice_paths(tmp_path: Path) -> None:
    audit_slice = ClassAuditSlice("barbarian", "full", "martial_mixed_party", "wolf_harriers")
    args = build_args(tmp_path, fixed_seed_runs=1, behavior_batch_size=2, health_batch_size=3)

    command = build_slice_command(args, audit_slice, tmp_path / "slice.json", tmp_path / "slice.md")

    assert command[1].endswith("run_barbarian_audit.py")
    assert "--full" in command
    assert command[command.index("--scenario") + 1] == "wolf_harriers"
    assert command[command.index("--player-preset") + 1] == "martial_mixed_party"
    assert "--skip-rules-gate" in command
    assert command[command.index("--fixed-seed-runs") + 1] == "1"
    assert command[command.index("--behavior-batch-size") + 1] == "2"
    assert command[command.index("--health-batch-size") + 1] == "3"


def test_run_slice_skips_existing_json_report(tmp_path: Path) -> None:
    audit_slice = ClassAuditSlice("fighter", "quick", "fighter_level2_sample_trio", "goblin_screen")
    existing_path = tmp_path / f"{audit_slice.slug}.json"
    existing_path.write_text(json.dumps({"overallStatus": "warn"}), encoding="utf-8")
    args = build_args(tmp_path)

    result = run_slice(args, audit_slice)

    assert result["status"] == "warn"
    assert result["executionStatus"] == "skipped"
    assert result["reportStatus"] == "warn"
    assert result["jsonPath"] == str(existing_path)


def test_build_summary_stops_release_gate_on_timeout() -> None:
    summary = build_summary(
        [
            {"status": "pass"},
            {"status": "timeout", "hardBlocker": True},
        ],
        planned_count=4,
        args=build_args(Path("reports/pass1/class_slices")),
    )

    assert summary["overallStatus"] == "fail"
    assert summary["stopReason"] == "hard_blocker"
    assert summary["statusCounts"]["timeout"] == 1


def test_build_summary_records_audit_failures_without_hard_stop() -> None:
    summary = build_summary(
        [
            {"status": "pass"},
            {"status": "fail", "hardBlocker": False},
        ],
        planned_count=4,
        args=build_args(Path("reports/pass1/class_slices")),
    )

    assert summary["overallStatus"] == "fail"
    assert summary["stopReason"] is None
    assert summary["statusCounts"]["fail"] == 1
