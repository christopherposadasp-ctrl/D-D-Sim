from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_nightly_audit.py"
MODULE_SPEC = importlib.util.spec_from_file_location("run_nightly_audit", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
nightly_audit = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = nightly_audit
MODULE_SPEC.loader.exec_module(nightly_audit)


def test_scenario_audit_parser_distinguishes_pass_warn_and_fail(tmp_path: Path) -> None:
    report_path = tmp_path / "scenario.json"
    report_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "scenarioId": "goblin_screen",
                        "status": "warn",
                        "warnings": ["Smart players underperformed dumb players."],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    status, warnings = nightly_audit.parse_scenario_audit_report(report_path)

    assert status == "warn"
    assert warnings == ["goblin_screen: Smart players underperformed dumb players."]

    report_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "scenarioId": "orc_push",
                        "status": "fail",
                        "warnings": ["One or more required signature mechanics never appeared."],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    status, warnings = nightly_audit.parse_scenario_audit_report(report_path)

    assert status == "fail"
    assert warnings == ["orc_push: One or more required signature mechanics never appeared."]


def test_class_audit_parser_uses_overall_status_and_row_messages(tmp_path: Path) -> None:
    report_path = tmp_path / "class.json"
    report_path.write_text(
        json.dumps(
            {
                "overallStatus": "fail",
                "rows": [
                    {
                        "playerPresetId": "martial_mixed_party",
                        "scenarioId": "orc_push",
                        "status": "fail",
                        "failures": ["Action Surge was skipped on an opening turn."],
                        "warnings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status, warnings = nightly_audit.parse_class_audit_report(report_path)

    assert status == "fail"
    assert warnings == ["martial_mixed_party / orc_push: Action Surge was skipped on an opening turn."]


def test_class_slice_summary_parser_uses_segmented_results(tmp_path: Path) -> None:
    report_path = tmp_path / "class_slice_summary.json"
    report_path.write_text(
        json.dumps(
            {
                "overallStatus": "warn",
                "results": [
                    {
                        "class": "fighter",
                        "playerPresetId": "martial_mixed_party",
                        "scenarioId": "orc_push",
                        "status": "warn",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status, warnings = nightly_audit.parse_class_slice_summary_report(report_path)

    assert status == "warn"
    assert warnings == ["fighter / martial_mixed_party / orc_push: status=warn"]


def test_code_health_parser_warns_on_legacy_imports_and_root_artifacts(tmp_path: Path) -> None:
    report_path = tmp_path / "health.json"
    report_path.write_text(
        json.dumps(
            {
                "largestLiveModules": [],
                "legacyFrontendImports": [{"path": "src/ui/App.tsx", "line": 1, "text": "import '../engine'"}],
                "rootArtifacts": ["scenario_bad.json"],
                "benchmarks": [],
            }
        ),
        encoding="utf-8",
    )

    status, warnings = nightly_audit.parse_code_health_report(report_path)

    assert status == "warn"
    assert warnings == [
        "Legacy frontend engine imports detected: 1 finding(s).",
        "Root-level audit artifacts detected: scenario_bad.json.",
    ]


def test_rotation_state_defaults_and_advances(tmp_path: Path) -> None:
    state_path = tmp_path / "rotation_state.json"

    assert nightly_audit.load_rotation_index(state_path, 4) == 0

    nightly_audit.save_rotation_index(state_path, 3)

    assert nightly_audit.load_rotation_index(state_path, 4) == 3


def test_backend_gate_uses_fast_non_slow_pytest_filter() -> None:
    commands = nightly_audit.build_backend_gate_commands(2700)
    pytest_command = next(command for command in commands if command.step_id == "check_fast_pytest")

    assert pytest_command.argv[1:6] == ("-m", "pytest", "-q", "-m", "not slow")
    assert 'pytest -q -m "not slow" tests\\golden tests\\rules tests\\integration' in pytest_command.display_command


def test_rotating_class_slices_use_segmented_runner_instead_of_legacy_quick() -> None:
    rotating_slices = nightly_audit.build_rotating_slices(Path("reports/nightly"))
    class_slices = [entry for entry in rotating_slices if "segmented" in entry.label]

    assert class_slices
    assert all("run_class_audit_slices.py" in entry.command.display_command for entry in class_slices)
    assert all("run_fighter_audit.py --quick" not in entry.command.display_command for entry in class_slices)
    assert all("run_barbarian_audit.py --quick" not in entry.command.display_command for entry in class_slices)
    assert all(entry.command.timeout_seconds == 7 * 60 for entry in class_slices)
    assert any(entry.slice_id == "barbarian_martial_mixed_party_wolf_harriers" for entry in class_slices)


def test_step_result_report_includes_elapsed_seconds() -> None:
    result = nightly_audit.StepResult(
        step_id="check_fast",
        label="Backend gate",
        status="pass",
        command="cmd",
        elapsed_seconds=12.34567,
    )

    assert result.to_report_dict()["elapsedSeconds"] == 12.346


def test_runtime_summary_identifies_slowest_timed_step() -> None:
    results = {
        "branch_gate": nightly_audit.StepResult("branch_gate", "Branch gate", "pass", "git"),
        "check_fast": nightly_audit.StepResult("check_fast", "Backend gate", "pass", "cmd", elapsed_seconds=10.0),
        "scenario_quick": nightly_audit.StepResult("scenario_quick", "Scenario quick audit", "warn", "cmd", elapsed_seconds=25.25),
        "code_health": nightly_audit.StepResult("code_health", "Code health audit", "pass", "cmd", elapsed_seconds=5.0),
    }

    summary = nightly_audit.build_runtime_summary(results)

    assert summary["totalMeasuredSeconds"] == 40.25
    assert summary["slowestStepId"] == "scenario_quick"
    assert summary["slowestStepSeconds"] == 25.25
    assert [entry["stepId"] for entry in summary["steps"]] == ["branch_gate", "check_fast", "scenario_quick", "code_health"]


def test_markdown_report_includes_blocker_and_reports() -> None:
    context = {
        "generatedAt": "2026-04-21T23:30:00",
        "branch": "main",
        "commit": "abc123",
        "shortStatus": [" M README.md"],
    }
    rotating_slice = nightly_audit.RotatingSlice(
        slice_id="fighter_quick",
        label="Fighter quick audit",
        command=nightly_audit.CommandSpec(
            step_id="rotating_slice",
            label="Rotating slice",
            argv=("python", "noop"),
            display_command="python noop",
            timeout_seconds=10,
        ),
    )
    results = {
        "branch_gate": nightly_audit.StepResult(
            step_id="branch_gate",
            label="Branch gate",
            status="fail",
            command="git rev-parse --abbrev-ref HEAD",
            detail="Expected branch `integration` but found `main`.",
        ),
        "check_fast": nightly_audit.StepResult("check_fast", "Backend gate", "skipped", "cmd", elapsed_seconds=1.0),
        "npm_test": nightly_audit.StepResult("npm_test", "Frontend tests", "skipped", "cmd"),
        "npm_build": nightly_audit.StepResult("npm_build", "Frontend build", "skipped", "cmd"),
        "scenario_quick": nightly_audit.StepResult("scenario_quick", "Scenario quick audit", "skipped", "cmd"),
        "code_health": nightly_audit.StepResult("code_health", "Code health audit", "pass", "cmd", elapsed_seconds=2.0),
        "rotating_slice": nightly_audit.StepResult("rotating_slice", "Rotating slice", "skipped", "cmd"),
    }

    markdown = nightly_audit.build_markdown_report(
        context=context,
        integration_branch="integration",
        rotating_slice=rotating_slice,
        step_results=results,
        overall_status="fail",
        blocker_step="branch_gate",
        report_paths=["reports/nightly/nightly_audit_latest.json"],
    )

    assert "- Blocking step: branch_gate" in markdown
    assert "- Audited branch: main" in markdown
    assert "## Runtime" in markdown
    assert "- Slowest step: code_health (2.0s)" in markdown
    assert "- reports/nightly/nightly_audit_latest.json" in markdown
