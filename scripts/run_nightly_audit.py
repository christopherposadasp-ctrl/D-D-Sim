from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "nightly"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "nightly_audit_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "nightly_audit_latest.md"
DEFAULT_ROTATION_STATE_PATH = DEFAULT_REPORT_DIR / "rotation_state.json"
DEFAULT_INTEGRATION_BRANCH = "integration"

Status = Literal["pass", "warn", "fail", "skipped"]
ReportParser = Callable[[Path], tuple[Status, list[str]]]


@dataclass(frozen=True)
class CommandSpec:
    step_id: str
    label: str
    argv: tuple[str, ...]
    display_command: str
    timeout_seconds: int
    report_paths: tuple[Path, ...] = ()
    report_parser: ReportParser | None = None
    hard_blocker_on_fail: bool = False


@dataclass(frozen=True)
class RotatingSlice:
    slice_id: str
    label: str
    command: CommandSpec


@dataclass
class StepResult:
    step_id: str
    label: str
    status: Status
    command: str
    timeout_seconds: int | None = None
    detail: str | None = None
    warnings: list[str] = field(default_factory=list)
    output_tail: list[str] = field(default_factory=list)
    report_paths: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict[str, object]:
        return {
            "stepId": self.step_id,
            "label": self.label,
            "status": self.status,
            "command": self.command,
            "timeoutSeconds": self.timeout_seconds,
            "detail": self.detail,
            "warnings": list(self.warnings),
            "outputTail": list(self.output_tail),
            "reportPaths": list(self.report_paths),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the nightly layered audit workflow.")
    parser.add_argument(
        "--integration-branch",
        default=DEFAULT_INTEGRATION_BRANCH,
        help="Required branch name for nightly audits.",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help="Path for the machine-readable nightly report.",
    )
    parser.add_argument(
        "--markdown-path",
        type=Path,
        default=DEFAULT_MARKDOWN_PATH,
        help="Path for the Markdown nightly report.",
    )
    parser.add_argument(
        "--rotation-state-path",
        type=Path,
        default=DEFAULT_ROTATION_STATE_PATH,
        help="Path for the rotating deep-slice state file.",
    )
    return parser.parse_args()


def split_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return [line for line in text.splitlines() if line.strip()]


def build_output_tail(stdout: str | None, stderr: str | None, limit: int = 12) -> list[str]:
    lines = [*split_lines(stdout), *split_lines(stderr)]
    return lines[-limit:]


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Expected report file was not created: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def parse_scenario_audit_report(path: Path) -> tuple[Status, list[str]]:
    payload = load_json(path)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Scenario audit report is missing rows.")

    failures: list[str] = []
    warnings: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        scenario_id = str(row.get("scenarioId", "unknown"))
        row_status = row.get("status")
        row_warnings = [entry for entry in row.get("warnings", []) if isinstance(entry, str)]
        message = row_warnings[0] if row_warnings else str(row.get("simpleSuggestion") or f"status={row_status}")
        if row_status == "fail":
            failures.append(f"{scenario_id}: {message}")
        elif row_status == "warn":
            warnings.append(f"{scenario_id}: {message}")

    if failures:
        return "fail", failures[:8]
    if warnings:
        return "warn", warnings[:8]
    return "pass", []


def parse_class_audit_report(path: Path) -> tuple[Status, list[str]]:
    payload = load_json(path)
    overall_status = payload.get("overallStatus")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Class audit report is missing rows.")

    failures: list[str] = []
    warnings: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = f"{row.get('playerPresetId', 'unknown')} / {row.get('scenarioId', 'unknown')}"
        row_failures = [entry for entry in row.get("failures", []) if isinstance(entry, str)]
        row_warnings = [entry for entry in row.get("warnings", []) if isinstance(entry, str)]
        if row_failures:
            failures.append(f"{label}: {row_failures[0]}")
        elif row.get("status") == "fail":
            failures.append(f"{label}: status=fail")
        elif row_warnings:
            warnings.append(f"{label}: {row_warnings[0]}")
        elif row.get("status") == "warn":
            warnings.append(f"{label}: status=warn")

    if overall_status == "fail":
        return "fail", failures[:8] or ["Class audit reported overallStatus=fail."]
    if overall_status == "warn":
        return "warn", warnings[:8] or ["Class audit reported overallStatus=warn."]
    return "pass", []


def parse_code_health_report(path: Path) -> tuple[Status, list[str]]:
    payload = load_json(path)
    warnings: list[str] = []

    legacy_imports = payload.get("legacyFrontendImports")
    if isinstance(legacy_imports, list) and legacy_imports:
        warnings.append(f"Legacy frontend engine imports detected: {len(legacy_imports)} finding(s).")

    root_artifacts = payload.get("rootArtifacts")
    if isinstance(root_artifacts, list) and root_artifacts:
        sample = ", ".join(str(entry) for entry in root_artifacts[:3])
        warnings.append(f"Root-level audit artifacts detected: {sample}.")

    if warnings:
        return "warn", warnings
    return "pass", []


def make_powershell_spec(
    step_id: str,
    label: str,
    task: str,
    *,
    timeout_seconds: int,
    report_paths: tuple[Path, ...] = (),
    report_parser: ReportParser | None = None,
    hard_blocker_on_fail: bool = False,
) -> CommandSpec:
    script_path = REPO_ROOT / "scripts" / "dev.ps1"
    return CommandSpec(
        step_id=step_id,
        label=label,
        argv=(
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            task,
        ),
        display_command=f".\\scripts\\dev.ps1 {task}",
        timeout_seconds=timeout_seconds,
        report_paths=report_paths,
        report_parser=report_parser,
        hard_blocker_on_fail=hard_blocker_on_fail,
    )


def build_rotating_slices(report_dir: Path) -> tuple[RotatingSlice, ...]:
    fighter_json = report_dir / "fighter_audit_latest.json"
    fighter_md = report_dir / "fighter_audit_latest.md"
    barbarian_json = report_dir / "barbarian_audit_latest.json"
    barbarian_md = report_dir / "barbarian_audit_latest.md"
    marsh_json = report_dir / "marsh_predators_deep_latest.json"
    orc_json = report_dir / "orc_push_deep_latest.json"

    return (
        RotatingSlice(
            slice_id="fighter_quick",
            label="Fighter quick audit",
            command=CommandSpec(
                step_id="rotating_slice",
                label="Rotating slice",
                argv=(
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_fighter_audit.py"),
                    "--quick",
                    "--json-path",
                    str(fighter_json),
                    "--markdown-path",
                    str(fighter_md),
                ),
                display_command=(
                    "py -3.13 .\\scripts\\run_fighter_audit.py --quick"
                    " --json-path .\\reports\\nightly\\fighter_audit_latest.json"
                    " --markdown-path .\\reports\\nightly\\fighter_audit_latest.md"
                ),
                timeout_seconds=30 * 60,
                report_paths=(fighter_json, fighter_md),
                report_parser=parse_class_audit_report,
            ),
        ),
        RotatingSlice(
            slice_id="barbarian_quick",
            label="Barbarian quick audit",
            command=CommandSpec(
                step_id="rotating_slice",
                label="Rotating slice",
                argv=(
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_barbarian_audit.py"),
                    "--quick",
                    "--json-path",
                    str(barbarian_json),
                    "--markdown-path",
                    str(barbarian_md),
                ),
                display_command=(
                    "py -3.13 .\\scripts\\run_barbarian_audit.py --quick"
                    " --json-path .\\reports\\nightly\\barbarian_audit_latest.json"
                    " --markdown-path .\\reports\\nightly\\barbarian_audit_latest.md"
                ),
                timeout_seconds=30 * 60,
                report_paths=(barbarian_json, barbarian_md),
                report_parser=parse_class_audit_report,
            ),
        ),
        RotatingSlice(
            slice_id="marsh_predators_deep",
            label="Marsh Predators deep scenario audit",
            command=CommandSpec(
                step_id="rotating_slice",
                label="Rotating slice",
                argv=(
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_scenario_audit.py"),
                    "--scenario",
                    "marsh_predators",
                    "--smart-smoke-runs",
                    "1",
                    "--dumb-smoke-runs",
                    "1",
                    "--mechanic-runs",
                    "10",
                    "--health-batch-size",
                    "1000",
                    "--json",
                    "--report-path",
                    str(marsh_json),
                ),
                display_command=(
                    "py -3.13 .\\scripts\\run_scenario_audit.py --scenario marsh_predators"
                    " --smart-smoke-runs 1 --dumb-smoke-runs 1 --mechanic-runs 10"
                    " --health-batch-size 1000 --json"
                    " --report-path .\\reports\\nightly\\marsh_predators_deep_latest.json"
                ),
                timeout_seconds=30 * 60,
                report_paths=(marsh_json,),
                report_parser=parse_scenario_audit_report,
            ),
        ),
        RotatingSlice(
            slice_id="orc_push_deep",
            label="Orc Push deep scenario audit",
            command=CommandSpec(
                step_id="rotating_slice",
                label="Rotating slice",
                argv=(
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_scenario_audit.py"),
                    "--scenario",
                    "orc_push",
                    "--smart-smoke-runs",
                    "1",
                    "--dumb-smoke-runs",
                    "1",
                    "--mechanic-runs",
                    "10",
                    "--health-batch-size",
                    "1000",
                    "--json",
                    "--report-path",
                    str(orc_json),
                ),
                display_command=(
                    "py -3.13 .\\scripts\\run_scenario_audit.py --scenario orc_push"
                    " --smart-smoke-runs 1 --dumb-smoke-runs 1 --mechanic-runs 10"
                    " --health-batch-size 1000 --json"
                    " --report-path .\\reports\\nightly\\orc_push_deep_latest.json"
                ),
                timeout_seconds=30 * 60,
                report_paths=(orc_json,),
                report_parser=parse_scenario_audit_report,
            ),
        ),
    )


def load_rotation_index(path: Path, total_slices: int) -> int:
    if total_slices <= 0:
        return 0
    if not path.exists():
        return 0

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return 0
    value = payload.get("nextIndex", 0)
    if not isinstance(value, int):
        return 0
    return value % total_slices


def save_rotation_index(path: Path, next_index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "nextIndex": next_index,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def collect_context() -> dict[str, object]:
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    commit = git_output("rev-parse", "HEAD") or "unknown"
    short_status = split_lines(git_output("status", "--short"))
    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "branch": branch,
        "commit": commit,
        "shortStatus": short_status,
    }


def git_status_summary(short_status: list[str]) -> str:
    if not short_status:
        return "clean"
    return f"dirty ({len(short_status)} path(s))"


def make_report_paths(paths: tuple[Path, ...]) -> list[str]:
    return [relative_path(path) for path in paths]


def make_skipped_step(spec: CommandSpec, reason: str) -> StepResult:
    return StepResult(
        step_id=spec.step_id,
        label=spec.label,
        status="skipped",
        command=spec.display_command,
        timeout_seconds=spec.timeout_seconds,
        detail=reason,
        report_paths=make_report_paths(spec.report_paths),
    )


def run_command(spec: CommandSpec) -> StepResult:
    report_paths = make_report_paths(spec.report_paths)
    try:
        completed = subprocess.run(
            spec.argv,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=spec.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        return StepResult(
            step_id=spec.step_id,
            label=spec.label,
            status="fail",
            command=spec.display_command,
            timeout_seconds=spec.timeout_seconds,
            detail=f"Timed out after {spec.timeout_seconds} seconds.",
            output_tail=build_output_tail(
                error.stdout if isinstance(error.stdout, str) else None,
                error.stderr if isinstance(error.stderr, str) else None,
            ),
            report_paths=report_paths,
        )

    output_tail = build_output_tail(completed.stdout, completed.stderr)
    result = StepResult(
        step_id=spec.step_id,
        label=spec.label,
        status="pass" if completed.returncode == 0 else "fail",
        command=spec.display_command,
        timeout_seconds=spec.timeout_seconds,
        detail=None if completed.returncode == 0 else f"Command exited with code {completed.returncode}.",
        output_tail=output_tail,
        report_paths=report_paths,
    )
    if result.status == "fail":
        return result

    if spec.report_parser is None:
        return result

    try:
        primary_report_path = spec.report_paths[0]
        parsed_status, warnings = spec.report_parser(primary_report_path)
    except Exception as error:  # pragma: no cover - defensive conversion
        result.status = "fail"
        result.detail = f"Failed to parse report output: {error}"
        return result

    result.status = parsed_status
    result.warnings = warnings
    if parsed_status == "fail":
        result.detail = "Audit report contained failing findings."
    elif parsed_status == "warn":
        result.detail = "Audit report contained warnings."
    return result


def choose_overall_status(step_results: dict[str, StepResult]) -> Status:
    statuses = [result.status for result in step_results.values()]
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def build_notable_warnings(step_results: dict[str, StepResult]) -> list[str]:
    notable: list[str] = []
    for result in step_results.values():
        for warning in result.warnings:
            notable.append(f"{result.label}: {warning}")
            if len(notable) >= 10:
                return notable
    return notable


def build_recommended_next_action(overall_status: Status, blocker_step: str | None) -> str:
    if blocker_step == "branch_gate":
        return "Switch this workspace to the integration branch before trusting nightly audit results."
    if overall_status == "fail":
        return "Fix the first blocking failure and rerun the nightly audit before merging more simulator changes."
    if overall_status == "warn":
        return "Review the warning rows in the referenced report files before treating the current build as stable."
    return "No immediate action is required beyond reviewing the refreshed nightly reports."


def build_markdown_report(
    context: dict[str, object],
    integration_branch: str,
    rotating_slice: RotatingSlice,
    step_results: dict[str, StepResult],
    overall_status: Status,
    blocker_step: str | None,
    report_paths: list[str],
) -> str:
    branch = str(context["branch"])
    commit = str(context["commit"])
    short_status = [entry for entry in context["shortStatus"] if isinstance(entry, str)]
    lines = [
        "## Nightly Audit",
        f"- Overall status: {overall_status}",
        f"- Audited at: {context['generatedAt']}",
        f"- Required branch: {integration_branch}",
        f"- Audited branch: {branch}",
        f"- Commit: {commit}",
        f"- Git status: {git_status_summary(short_status)}",
        f"- Rotating slice: {rotating_slice.label}",
        f"- Branch gate: {step_results['branch_gate'].status}",
        f"- Backend gate: {step_results['check_fast'].status}",
        f"- Frontend tests: {step_results['npm_test'].status}",
        f"- Frontend build: {step_results['npm_build'].status}",
        f"- Scenario quick audit: {step_results['scenario_quick'].status}",
        f"- Code health audit: {step_results['code_health'].status}",
        f"- Deep slice result: {step_results['rotating_slice'].status}",
    ]

    if blocker_step:
        lines.append(f"- Blocking step: {blocker_step}")

    lines.append("")
    lines.append("## Details")
    for step_id in ("branch_gate", "check_fast", "npm_test", "npm_build", "scenario_quick", "code_health", "rotating_slice"):
        result = step_results[step_id]
        if result.detail:
            lines.append(f"- {result.label}: {result.detail}")
        for warning in result.warnings[:3]:
            lines.append(f"- {result.label}: {warning}")
        if result.status == "fail":
            for entry in result.output_tail[:4]:
                lines.append(f"- {result.label} output: {entry}")

    if len(lines) == 15:
        lines.append("- No additional details.")

    lines.append("")
    lines.append("## Reports")
    for report_path in report_paths:
        lines.append(f"- {report_path}")

    lines.append("")
    lines.append(f"- Recommended next action: {build_recommended_next_action(overall_status, blocker_step)}")
    return "\n".join(lines) + "\n"


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    report_dir = args.json_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    context = collect_context()
    rotating_slices = build_rotating_slices(report_dir)
    rotation_index = load_rotation_index(args.rotation_state_path, len(rotating_slices))
    rotating_slice = rotating_slices[rotation_index]

    branch_gate = StepResult(
        step_id="branch_gate",
        label="Branch gate",
        status="pass" if context["branch"] == args.integration_branch else "fail",
        command="git rev-parse --abbrev-ref HEAD",
        detail=None,
    )
    if branch_gate.status == "fail":
        branch_gate.detail = f"Expected branch `{args.integration_branch}` but found `{context['branch']}`."

    check_fast_spec = make_powershell_spec(
        "check_fast",
        "Backend gate",
        "check-fast",
        timeout_seconds=45 * 60,
        hard_blocker_on_fail=True,
    )
    npm_test_spec = CommandSpec(
        step_id="npm_test",
        label="Frontend tests",
        argv=("npm", "run", "test"),
        display_command="npm run test",
        timeout_seconds=20 * 60,
        hard_blocker_on_fail=True,
    )
    npm_build_spec = CommandSpec(
        step_id="npm_build",
        label="Frontend build",
        argv=("npm", "run", "build"),
        display_command="npm run build",
        timeout_seconds=20 * 60,
        hard_blocker_on_fail=True,
    )
    scenario_quick_report = REPO_ROOT / "reports" / "scenario_audit_latest.json"
    scenario_quick_spec = make_powershell_spec(
        "scenario_quick",
        "Scenario quick audit",
        "audit-quick",
        timeout_seconds=45 * 60,
        report_paths=(scenario_quick_report,),
        report_parser=parse_scenario_audit_report,
        hard_blocker_on_fail=True,
    )
    code_health_report = REPO_ROOT / "reports" / "code_health_audit.json"
    code_health_spec = make_powershell_spec(
        "code_health",
        "Code health audit",
        "audit-health",
        timeout_seconds=30 * 60,
        report_paths=(code_health_report,),
        report_parser=parse_code_health_report,
    )

    step_results: dict[str, StepResult] = {"branch_gate": branch_gate}
    blocker_step: str | None = "branch_gate" if branch_gate.status == "fail" else None
    code_health_ran = False

    execution_order = (check_fast_spec, npm_test_spec, npm_build_spec, scenario_quick_spec)
    for spec in execution_order:
        if blocker_step is not None:
            step_results[spec.step_id] = make_skipped_step(spec, f"Skipped because {blocker_step} blocked the nightly run.")
            continue

        result = run_command(spec)
        step_results[spec.step_id] = result
        if result.status == "fail" and spec.hard_blocker_on_fail:
            blocker_step = spec.step_id

    if blocker_step is None:
        step_results["code_health"] = run_command(code_health_spec)
        code_health_ran = True
        if step_results["code_health"].status == "fail":
            blocker_step = "code_health"
    else:
        step_results["code_health"] = run_command(code_health_spec)
        code_health_ran = True

    if blocker_step is None:
        rotating_result = run_command(rotating_slice.command)
        step_results["rotating_slice"] = rotating_result
        if rotating_result.status != "fail":
            save_rotation_index(args.rotation_state_path, (rotation_index + 1) % len(rotating_slices))
        elif rotating_result.output_tail:
            blocker_step = "rotating_slice"
    else:
        step_results["rotating_slice"] = make_skipped_step(
            rotating_slice.command,
            f"Skipped because {blocker_step} blocked the nightly run.",
        )

    if not code_health_ran:
        step_results["code_health"] = make_skipped_step(code_health_spec, "Skipped unexpectedly.")

    overall_status = choose_overall_status(step_results)
    report_paths = [
        relative_path(args.json_path),
        relative_path(args.markdown_path),
    ]
    for result in step_results.values():
        for path in result.report_paths:
            if path not in report_paths:
                report_paths.append(path)

    payload = {
        "generatedAt": context["generatedAt"],
        "integrationBranch": args.integration_branch,
        "auditedBranch": context["branch"],
        "commit": context["commit"],
        "gitStatus": list(context["shortStatus"]),
        "gitStatusSummary": git_status_summary([entry for entry in context["shortStatus"] if isinstance(entry, str)]),
        "overallStatus": overall_status,
        "blockerStepId": blocker_step,
        "selectedRotatingSlice": {
            "sliceId": rotating_slice.slice_id,
            "label": rotating_slice.label,
            "command": rotating_slice.command.display_command,
        },
        "notableWarnings": build_notable_warnings(step_results),
        "steps": {step_id: result.to_report_dict() for step_id, result in step_results.items()},
        "reportPaths": report_paths,
    }
    markdown = build_markdown_report(
        context,
        args.integration_branch,
        rotating_slice,
        step_results,
        overall_status,
        blocker_step,
        report_paths,
    )

    write_report(args.json_path, json.dumps(payload, indent=2) + "\n")
    write_report(args.markdown_path, markdown)

    print(markdown, end="")


if __name__ == "__main__":
    main()
