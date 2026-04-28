from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_common import (
    collect_git_context,
    output_tail,
    relative_path,
    write_json_report,
    write_text_report,
)

Status = Literal["pass", "warn", "fail", "skipped"]
GateLevel = Literal["inner_loop", "checkpoint", "release", "forensic", "unknown"]
Confidence = Literal["high", "medium", "low"]

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "audit_validation"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "audit_validation_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "audit_validation_latest.md"
DEFAULT_STALE_DAYS = 14
STATUS_FIELD_NAMES = {"status", "overallStatus", "reportStatus"}
BLOCKING_REPORT_STATUSES = {"fail", "timeout"}
CANONICAL_CLASS_EVIDENCE_PATHS = (
    "reports/class_audit/fighter_barbarian_quick_latest.json",
    "reports/class_audit/fighter_barbarian_quick_latest.md",
)
LEGACY_CLASS_AUDIT_COMMANDS = (
    "fighter-audit-quick",
    "fighter-audit-full",
    "barbarian-audit-quick",
    "barbarian-audit-full",
)


@dataclass(frozen=True)
class AuditMechanism:
    task: str
    purpose: str
    recommended_gate_level: GateLevel
    report_paths: tuple[str, ...]
    overlap_candidates: tuple[str, ...]
    heavy: bool = False
    smoke_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmokeMeasurement:
    status: Status
    command: list[str]
    exit_code: int | None
    elapsed_seconds: float
    timeout_seconds: int
    output_tail: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "command": self.command,
            "exitCode": self.exit_code,
            "elapsedSeconds": round(self.elapsed_seconds, 3),
            "timeoutSeconds": self.timeout_seconds,
            "outputTail": self.output_tail,
        }


MECHANISMS: tuple[AuditMechanism, ...] = (
    AuditMechanism(
        "check-fast",
        "Fast backend correctness gate: Ruff plus non-slow golden/rules/integration tests.",
        "inner_loop",
        (),
        ("party-validation", "pass2-stability"),
    ),
    AuditMechanism(
        "daily-housekeeping",
        "Report-only repo hygiene, doc drift, and safe commit recommendation check.",
        "inner_loop",
        ("reports/housekeeping/daily_housekeeping_latest.json", "reports/housekeeping/daily_housekeeping_latest.md"),
        ("pass3-clarity",),
        smoke_args=("daily-housekeeping",),
    ),
    AuditMechanism(
        "party-validation",
        "Focused current-party behavior gate for the default party path.",
        "inner_loop",
        ("reports/party_validation/party_validation_latest.json", "reports/party_validation/party_validation_latest.md"),
        ("audit-quick", "pc-tuning-sample", "class-audit-slices"),
        smoke_args=(
            "party-validation",
            "--scenario",
            "reaction_bastion",
            "--batch-size",
            "6",
            "--skip-rules-gate",
            "--json-path",
            "reports/audit_validation/smoke_party_validation.json",
            "--markdown-path",
            "reports/audit_validation/smoke_party_validation.md",
        ),
    ),
    AuditMechanism(
        "pc-tuning-sample",
        "Event-level PC tuning sample for current party profiles.",
        "forensic",
        ("reports/pc_tuning/pc_tuning_latest.json", "reports/pc_tuning/pc_tuning_latest.md"),
        ("party-validation", "rogue-audit-quick"),
        smoke_args=(
            "pc-tuning-sample",
            "--profile",
            "rogue",
            "--scenario",
            "reaction_bastion",
            "--runs-per-scenario",
            "1",
            "--json-path",
            "reports/audit_validation/smoke_pc_tuning.json",
            "--markdown-path",
            "reports/audit_validation/smoke_pc_tuning.md",
        ),
    ),
    AuditMechanism(
        "audit-quick",
        "Scenario behavior and signature audit using the quick profile.",
        "checkpoint",
        ("reports/scenario_audit_latest.json",),
        ("party-validation", "pass2-stability", "nightly-audit"),
        smoke_args=(
            "audit-quick",
            "--scenario",
            "goblin_screen",
            "--smart-smoke-runs",
            "1",
            "--dumb-smoke-runs",
            "1",
            "--mechanic-runs",
            "1",
            "--health-batch-size",
            "3",
            "--report-path",
            "reports/audit_validation/smoke_scenario_audit.json",
        ),
    ),
    AuditMechanism(
        "audit-full",
        "Slower full scenario behavior and signature audit.",
        "release",
        ("reports/scenario_audit_latest.json",),
        ("audit-quick", "nightly-audit"),
        heavy=True,
    ),
    AuditMechanism(
        "audit-health",
        "Code-health and benchmark-style diagnostic report.",
        "checkpoint",
        ("reports/code_health_audit.json", "reports/code_health_audit.md"),
        ("daily-housekeeping", "pass3-clarity"),
        smoke_args=("audit-health", "--benchmark-batch-size", "1", "--largest-limit", "3"),
    ),
    AuditMechanism(
        "audit-validation",
        "Measure-first report on audit command coverage, report freshness, runtime evidence, and overlap candidates.",
        "checkpoint",
        ("reports/audit_validation/audit_validation_latest.json", "reports/audit_validation/audit_validation_latest.md"),
        ("daily-housekeeping", "pass3-clarity"),
    ),
    AuditMechanism(
        "fighter-audit-quick",
        "Legacy targeted Fighter quick audit; canonical Fighter matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("class-audit-slices", "party-validation"),
        smoke_args=(
            "fighter-audit-quick",
            "--scenario",
            "goblin_screen",
            "--player-preset",
            "fighter_level2_sample_trio",
            "--fixed-seed-runs",
            "1",
            "--behavior-batch-size",
            "3",
            "--health-batch-size",
            "3",
            "--skip-rules-gate",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "fighter-audit-full",
        "Legacy targeted Fighter full audit; canonical Fighter matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("fighter-audit-quick", "class-audit-slices"),
        heavy=True,
    ),
    AuditMechanism(
        "barbarian-audit-quick",
        "Legacy targeted Barbarian quick audit; canonical Barbarian matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("class-audit-slices", "party-validation"),
        smoke_args=(
            "barbarian-audit-quick",
            "--scenario",
            "goblin_screen",
            "--player-preset",
            "barbarian_level2_sample_trio",
            "--fixed-seed-runs",
            "1",
            "--behavior-batch-size",
            "3",
            "--health-batch-size",
            "3",
            "--skip-rules-gate",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "barbarian-audit-full",
        "Legacy targeted Barbarian full audit; canonical Barbarian matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("barbarian-audit-quick", "class-audit-slices"),
        heavy=True,
    ),
    AuditMechanism(
        "rogue-audit-quick",
        "Dedicated level 2 ranged Rogue quick audit.",
        "checkpoint",
        ("reports/rogue_audit/rogue_audit_latest.json", "reports/rogue_audit/rogue_audit_latest.md"),
        ("party-validation", "pc-tuning-sample"),
        smoke_args=(
            "rogue-audit-quick",
            "--scenario",
            "goblin_screen",
            "--signature-probe-runs",
            "1",
            "--health-batch-size",
            "3",
            "--skip-rules-gate",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "rogue-audit-full",
        "Dedicated Rogue full audit.",
        "release",
        ("reports/rogue_audit/rogue_audit_latest.json", "reports/rogue_audit/rogue_audit_latest.md"),
        ("rogue-audit-quick",),
        heavy=True,
    ),
    AuditMechanism(
        "class-audit-slices",
        "Canonical timeout-safe segmented Fighter/Barbarian class audit evidence route.",
        "checkpoint",
        CANONICAL_CLASS_EVIDENCE_PATHS,
        ("fighter-audit-quick", "barbarian-audit-quick", "pass2-stability"),
        smoke_args=("class-audit-slices", "--dry-run", "--max-slices", "2"),
    ),
    AuditMechanism(
        "behavior-diagnostics",
        "Focused smart-vs-dumb investigation helper.",
        "forensic",
        (),
        ("fighter-audit-quick", "barbarian-audit-quick"),
        smoke_args=(
            "behavior-diagnostics",
            "--class",
            "fighter",
            "--player-preset",
            "fighter_level2_sample_trio",
            "--scenario",
            "goblin_screen",
            "--monster-behavior",
            "balanced",
            "--sample-size",
            "1",
            "--detail-limit",
            "0",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "nightly-audit",
        "Layered nightly safety net on the integration branch.",
        "release",
        ("reports/nightly/nightly_audit_latest.json", "reports/nightly/nightly_audit_latest.md"),
        ("check-fast", "audit-quick", "audit-health"),
        heavy=True,
    ),
    AuditMechanism(
        "pass2-stability",
        "Determinism, repeatability, async batch, and long-audit stability gate.",
        "release",
        ("reports/pass2/pass2_stability_latest.json", "reports/pass2/pass2_stability_latest.md"),
        ("check-fast", "audit-quick", "class-audit-slices"),
        heavy=True,
        smoke_args=(
            "pass2-stability",
            "--scenario",
            "orc_push",
            "--player-preset",
            "rogue_level2_ranged_trio",
            "--skip-async",
            "--skip-long-audits",
            "--determinism-batch-size",
            "1",
            "--json-path",
            "reports/audit_validation/smoke_pass2_stability.json",
            "--markdown-path",
            "reports/audit_validation/smoke_pass2_stability.md",
        ),
    ),
    AuditMechanism(
        "pass3-clarity",
        "Docs, report, runner consistency, and audit-maintainability gate.",
        "checkpoint",
        ("reports/pass3/pass3_clarity_latest.json", "reports/pass3/pass3_clarity_latest.md"),
        ("daily-housekeeping",),
        smoke_args=(
            "pass3-clarity",
            "--json-path",
            "reports/audit_validation/smoke_pass3_clarity.json",
            "--markdown-path",
            "reports/audit_validation/smoke_pass3_clarity.md",
        ),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the current audit and testing mechanisms without trimming them.")
    parser.add_argument("--measure-smoke", action="store_true", help="Run bounded smoke measurements for cheap/scoped commands.")
    parser.add_argument("--include-heavy", action="store_true", help="Allow heavy release commands to run in smoke measurement mode.")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Per-command timeout for smoke measurements.")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS, help="Report age that lowers confidence.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    return parser.parse_args()


def extract_dev_tasks(dev_ps1_text: str) -> list[str]:
    match = re.search(r"ValidateSet\((.*?)\)\]\s*\[string\]\$Task", dev_ps1_text, flags=re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def extract_runbook_direct_equivalents(runbook_text: str) -> dict[str, str]:
    mappings: dict[str, str] = {}
    pattern = re.compile(r"^- `([^`]+)`: `([^`]+)`", flags=re.MULTILINE)
    for match in pattern.finditer(runbook_text):
        mappings[match.group(1)] = match.group(2)
    return mappings


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def iter_status_values(value: Any) -> list[str]:
    statuses: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in STATUS_FIELD_NAMES and isinstance(child, str):
                statuses.append(child)
            else:
                statuses.extend(iter_status_values(child))
    elif isinstance(value, list):
        for child in value:
            statuses.extend(iter_status_values(child))
    return statuses


def collect_key_values(value: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys:
                values.append(child)
            values.extend(collect_key_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            values.extend(collect_key_values(child, keys))
    return values


def flatten_string_values(values: list[Any]) -> list[str]:
    strings: list[str] = []
    for value in values:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, list | tuple | set):
            strings.extend(str(item) for item in value if isinstance(item, str))
    return sorted(set(strings))


def count_rows(payload: dict[str, Any]) -> int:
    row_keys = (
        "rows",
        "results",
        "checks",
        "issues",
        "signatureProbes",
        "replayDeterminismRows",
        "batchDeterminismRows",
        "asyncJobRows",
        "longAuditRows",
    )
    total = 0
    for key in row_keys:
        value = payload.get(key)
        if isinstance(value, list):
            total += len(value)
    return total


def first_number(values: list[Any]) -> float | None:
    for value in values:
        if isinstance(value, int | float):
            return float(value)
    return None


def summarize_json_report(path: Path, now: datetime, stale_days: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": relative_path(path),
            "exists": False,
            "status": "missing",
            "confidenceImpact": "missing_report",
        }

    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    age_hours = round((now - modified_at).total_seconds() / 3600, 2)
    summary: dict[str, Any] = {
        "path": relative_path(path),
        "exists": True,
        "modifiedAt": modified_at.isoformat(),
        "ageHours": age_hours,
        "stale": age_hours > stale_days * 24,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Report JSON root is not an object.")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        summary.update({"status": "malformed", "error": str(error), "confidenceImpact": "malformed_report"})
        return summary

    status_values = iter_status_values(payload)
    status = str(payload.get("overallStatus") or payload.get("status") or payload.get("reportStatus") or "unknown")
    warning_count = sum(1 for value in status_values if value == "warn")
    failure_count = sum(1 for value in status_values if value in {"fail", "timeout"})
    elapsed_seconds = first_number(collect_key_values(payload, {"elapsedSeconds", "totalElapsedSeconds"}))
    scenario_ids = flatten_string_values(collect_key_values(payload, {"scenarioId", "scenarioIds"}))
    player_preset_ids = flatten_string_values(collect_key_values(payload, {"playerPresetId", "playerPresetIds"}))
    warning_strings = flatten_string_values(collect_key_values(payload, {"warnings", "knownWarnings", "issues"}))[:12]

    summary.update(
        {
            "status": status,
            "statusFields": sorted(set(status_values)),
            "rowCount": count_rows(payload),
            "warningCount": warning_count,
            "failureCount": failure_count,
            "elapsedSeconds": elapsed_seconds,
            "scenarioIds": scenario_ids[:20],
            "playerPresetIds": player_preset_ids[:20],
            "warningSamples": warning_strings,
        }
    )
    if summary["stale"]:
        summary["confidenceImpact"] = "stale_report"
    return summary


def summarize_text_report(path: Path, now: datetime, stale_days: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": relative_path(path),
            "exists": False,
            "status": "missing",
            "confidenceImpact": "missing_report",
        }
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    age_hours = round((now - modified_at).total_seconds() / 3600, 2)
    return {
        "path": relative_path(path),
        "exists": True,
        "modifiedAt": modified_at.isoformat(),
        "ageHours": age_hours,
        "stale": age_hours > stale_days * 24,
        "lineCount": len(path.read_text(encoding="utf-8").splitlines()),
        "confidenceImpact": "stale_report" if age_hours > stale_days * 24 else None,
    }


def summarize_report(path_text: str, now: datetime, stale_days: int) -> dict[str, Any]:
    path = REPO_ROOT / path_text
    if path.suffix.lower() == ".json":
        return summarize_json_report(path, now, stale_days)
    return summarize_text_report(path, now, stale_days)


def direct_command_for(mechanism: AuditMechanism, runbook_mappings: dict[str, str]) -> str:
    if mechanism.task in runbook_mappings:
        return runbook_mappings[mechanism.task]
    return ""


def infer_runtime_class(elapsed_seconds: float | None, report_count: int, heavy: bool) -> str:
    if elapsed_seconds is None:
        return "unknown" if report_count == 0 else "unmeasured"
    if elapsed_seconds < 60:
        return "fast"
    if elapsed_seconds < 600:
        return "medium"
    if heavy or elapsed_seconds >= 600:
        return "slow"
    return "medium"


def determine_confidence(
    mechanism: AuditMechanism,
    in_wrapper: bool,
    direct_command: str,
    report_summaries: list[dict[str, Any]],
) -> tuple[Confidence, list[str]]:
    reasons: list[str] = []
    if not in_wrapper:
        reasons.append("wrapper_missing")
    if not direct_command:
        reasons.append("runbook_direct_equivalent_missing")

    json_reports = [summary for summary in report_summaries if summary["path"].endswith(".json")]
    if mechanism.report_paths and not any(summary.get("exists") for summary in json_reports):
        reasons.append("json_report_missing")
    if any(summary.get("status") == "malformed" for summary in report_summaries):
        reasons.append("report_malformed")
    if any(summary.get("stale") for summary in report_summaries):
        reasons.append("report_stale")
    if mechanism.task == "class-audit-slices" and any(
        summary.get("status") in BLOCKING_REPORT_STATUSES for summary in json_reports
    ):
        reasons.append("canonical_class_evidence_failed")

    if not reasons:
        return "high", ["wrapper, runbook mapping, and report evidence are present"]
    if "wrapper_missing" in reasons or "report_malformed" in reasons:
        return "low", reasons
    if (
        "json_report_missing" in reasons
        or "runbook_direct_equivalent_missing" in reasons
        or "report_stale" in reasons
        or "canonical_class_evidence_failed" in reasons
    ):
        return "low", reasons
    return "medium", reasons


def row_status(confidence: Confidence, report_summaries: list[dict[str, Any]]) -> Status:
    if any(summary.get("status") == "malformed" for summary in report_summaries):
        return "fail"
    if confidence == "low":
        return "warn"
    if any(summary.get("status") == "fail" for summary in report_summaries):
        return "warn"
    return "pass"


def build_powershell_command(args: tuple[str, ...]) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "scripts" / "dev.ps1"), *args]


def run_smoke_measurement(mechanism: AuditMechanism, timeout_seconds: int) -> SmokeMeasurement:
    if not mechanism.smoke_args:
        return SmokeMeasurement(
            status="skipped",
            command=[],
            exit_code=0,
            elapsed_seconds=0.0,
            timeout_seconds=timeout_seconds,
            output_tail=["No bounded smoke command is configured for this mechanism."],
        )

    command = build_powershell_command(mechanism.smoke_args)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        elapsed = time.perf_counter() - started
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else error.stdout
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        return SmokeMeasurement(
            status="fail",
            command=command,
            exit_code=None,
            elapsed_seconds=elapsed,
            timeout_seconds=timeout_seconds,
            output_tail=output_tail(stdout, stderr),
        )

    elapsed = time.perf_counter() - started
    return SmokeMeasurement(
        status="pass" if completed.returncode == 0 else "fail",
        command=command,
        exit_code=completed.returncode,
        elapsed_seconds=elapsed,
        timeout_seconds=timeout_seconds,
        output_tail=output_tail(completed.stdout, completed.stderr),
    )


def build_mechanism_row(
    mechanism: AuditMechanism,
    wrapper_tasks: list[str],
    runbook_mappings: dict[str, str],
    now: datetime,
    stale_days: int,
) -> dict[str, Any]:
    report_summaries = [summarize_report(path, now, stale_days) for path in mechanism.report_paths]
    in_wrapper = mechanism.task in wrapper_tasks
    direct_command = direct_command_for(mechanism, runbook_mappings)
    confidence, confidence_reasons = determine_confidence(mechanism, in_wrapper, direct_command, report_summaries)
    latest_json_report = next((summary for summary in report_summaries if summary["path"].endswith(".json") and summary.get("exists")), None)
    elapsed_seconds = first_number([summary.get("elapsedSeconds") for summary in report_summaries])

    return {
        "task": mechanism.task,
        "status": row_status(confidence, report_summaries),
        "wrapperCommand": f".\\scripts\\dev.ps1 {mechanism.task}",
        "directCommand": direct_command,
        "wrapperPresent": in_wrapper,
        "runbookDirectEquivalentPresent": bool(direct_command),
        "expectedPurpose": mechanism.purpose,
        "recommendedGateLevel": mechanism.recommended_gate_level,
        "heavy": mechanism.heavy,
        "latestStatus": latest_json_report.get("status") if latest_json_report else "unreported",
        "observedElapsedSeconds": elapsed_seconds,
        "inferredRuntimeClass": infer_runtime_class(elapsed_seconds, len(report_summaries), mechanism.heavy),
        "reportArtifacts": report_summaries,
        "overlapCandidates": list(mechanism.overlap_candidates),
        "validationConfidence": confidence,
        "confidenceReasons": confidence_reasons,
    }


def maybe_measure_rows(
    rows: list[dict[str, Any]],
    mechanisms: tuple[AuditMechanism, ...],
    measure_smoke: bool,
    include_heavy: bool,
    timeout_seconds: int,
) -> None:
    if not measure_smoke:
        return
    by_task = {mechanism.task: mechanism for mechanism in mechanisms}
    for row in rows:
        mechanism = by_task[row["task"]]
        if mechanism.heavy and not include_heavy:
            row["smokeMeasurement"] = {
                "status": "skipped",
                "reason": "Heavy command skipped without --include-heavy.",
            }
            continue
        measurement = run_smoke_measurement(mechanism, timeout_seconds)
        row["smokeMeasurement"] = measurement.to_payload()
        row["observedElapsedSeconds"] = measurement.elapsed_seconds
        row["inferredRuntimeClass"] = infer_runtime_class(measurement.elapsed_seconds, len(row["reportArtifacts"]), mechanism.heavy)
        if measurement.status == "fail":
            row["status"] = "fail"
            row["validationConfidence"] = "low"
            row["confidenceReasons"] = [*row["confidenceReasons"], "smoke_measurement_failed"]


def build_recommendations(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    default_gate = [
        row["task"]
        for row in rows
        if row["recommendedGateLevel"] == "inner_loop" and row["validationConfidence"] != "low"
    ]
    checkpoint_or_release = [
        row["task"]
        for row in rows
        if row["recommendedGateLevel"] in {"checkpoint", "release"} and row["validationConfidence"] != "low"
    ]
    forensic = [
        row["task"]
        for row in rows
        if row["recommendedGateLevel"] == "forensic" and row["validationConfidence"] != "low"
    ]
    needs_validation = [row["task"] for row in rows if row["validationConfidence"] == "low"]
    needs_evidence_refresh = [
        row["task"]
        for row in rows
        if row["validationConfidence"] == "low"
        or any(
            artifact.get("confidenceImpact") in {"missing_report", "stale_report", "malformed_report"}
            or artifact.get("status") in BLOCKING_REPORT_STATUSES
            for artifact in row["reportArtifacts"]
        )
    ]
    return {
        "keepInDefaultGate": default_gate,
        "checkpointOrReleaseOnly": checkpoint_or_release,
        "forensicOnly": forensic,
        "needsLaterValidation": needs_validation,
        "needsEvidenceRefresh": needs_evidence_refresh,
    }


def build_canonical_class_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    class_row = next((row for row in rows if row["task"] == "class-audit-slices"), None)
    return {
        "task": "class-audit-slices",
        "summaryJsonPath": CANONICAL_CLASS_EVIDENCE_PATHS[0],
        "summaryMarkdownPath": CANONICAL_CLASS_EVIDENCE_PATHS[1],
        "status": class_row["status"] if class_row else "missing",
        "validationConfidence": class_row["validationConfidence"] if class_row else "low",
        "reportArtifacts": class_row["reportArtifacts"] if class_row else [],
    }


def build_command_coverage(wrapper_tasks: list[str], runbook_mappings: dict[str, str]) -> dict[str, Any]:
    known_tasks = [mechanism.task for mechanism in MECHANISMS]
    return {
        "wrapperTasks": wrapper_tasks,
        "runbookDirectEquivalentTasks": sorted(runbook_mappings),
        "missingFromWrapper": [task for task in known_tasks if task not in wrapper_tasks],
        "missingRunbookDirectEquivalent": [task for task in known_tasks if task not in runbook_mappings],
        "undocumentedWrapperTasks": [task for task in wrapper_tasks if task not in runbook_mappings],
        "unknownWrapperTasks": [task for task in wrapper_tasks if task not in known_tasks],
    }


def determine_overall_status(rows: list[dict[str, Any]], command_coverage: dict[str, Any]) -> Status:
    if command_coverage["missingFromWrapper"]:
        return "fail"
    if any(row["status"] == "fail" for row in rows):
        return "fail"
    if command_coverage["missingRunbookDirectEquivalent"] or any(row["status"] == "warn" for row in rows):
        return "warn"
    return "pass"


def build_report_payload(
    *,
    context: dict[str, Any],
    rows: list[dict[str, Any]],
    command_coverage: dict[str, Any],
    measure_smoke: bool,
    include_heavy: bool,
    timeout_seconds: int,
    stale_days: int,
    json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    recommendations = build_recommendations(rows)
    status_counts = {
        "pass": sum(1 for row in rows if row["status"] == "pass"),
        "warn": sum(1 for row in rows if row["status"] == "warn"),
        "fail": sum(1 for row in rows if row["status"] == "fail"),
        "skipped": sum(1 for row in rows if row["status"] == "skipped"),
    }
    payload = {
        "overallStatus": determine_overall_status(rows, command_coverage),
        "context": context,
        "config": {
            "measureSmoke": measure_smoke,
            "includeHeavy": include_heavy,
            "timeoutSeconds": timeout_seconds,
            "staleDays": stale_days,
        },
        "artifactPaths": {
            "json": relative_path(json_path),
            "markdown": relative_path(markdown_path),
        },
        "commandCoverage": command_coverage,
        "canonicalClassEvidence": build_canonical_class_evidence(rows),
        "legacyClassAuditCommands": list(LEGACY_CLASS_AUDIT_COMMANDS),
        "statusCounts": status_counts,
        "recommendations": recommendations,
        "rows": rows,
    }
    return payload


def format_report_markdown(payload: dict[str, Any]) -> str:
    recommendations = payload["recommendations"]
    lines = [
        "# Audit Validation Report",
        "",
        f"- Overall status: `{payload['overallStatus']}`",
        f"- Branch: `{payload['context']['branch']}`",
        f"- Commit: `{payload['context']['commit']}`",
        f"- Measure smoke: `{payload['config']['measureSmoke']}`",
        f"- Include heavy: `{payload['config']['includeHeavy']}`",
        f"- JSON report: `{payload['artifactPaths']['json']}`",
        f"- Markdown report: `{payload['artifactPaths']['markdown']}`",
        "",
        "## Recommendations",
        "",
        f"- Keep in default gate: `{', '.join(recommendations['keepInDefaultGate']) or 'none'}`",
        f"- Checkpoint/release only: `{', '.join(recommendations['checkpointOrReleaseOnly']) or 'none'}`",
        f"- Forensic only: `{', '.join(recommendations['forensicOnly']) or 'none'}`",
        f"- Needs later validation: `{', '.join(recommendations['needsLaterValidation']) or 'none'}`",
        f"- Needs evidence refresh: `{', '.join(recommendations['needsEvidenceRefresh']) or 'none'}`",
        "",
        "## Canonical Class Evidence",
        "",
        f"- Task: `{payload['canonicalClassEvidence']['task']}`",
        f"- Status: `{payload['canonicalClassEvidence']['status']}`",
        f"- Confidence: `{payload['canonicalClassEvidence']['validationConfidence']}`",
        f"- JSON: `{payload['canonicalClassEvidence']['summaryJsonPath']}`",
        f"- Markdown: `{payload['canonicalClassEvidence']['summaryMarkdownPath']}`",
        f"- Legacy class commands: `{', '.join(payload['legacyClassAuditCommands'])}`",
        "",
        "## Mechanisms",
        "",
        "| command | status | gate | confidence | latest status | runtime | report evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        report_paths = ", ".join(
            f"`{artifact['path']}`"
            for artifact in row["reportArtifacts"]
            if artifact.get("exists")
        )
        lines.append(
            f"| `{row['task']}` | `{row['status']}` | `{row['recommendedGateLevel']}` | "
            f"`{row['validationConfidence']}` | `{row['latestStatus']}` | "
            f"`{row['inferredRuntimeClass']}` | {report_paths or '`none`'} |"
        )

    coverage = payload["commandCoverage"]
    lines.extend(
        [
            "",
            "## Command Coverage",
            "",
            f"- Missing from wrapper: `{', '.join(coverage['missingFromWrapper']) or 'none'}`",
            f"- Missing runbook direct equivalent: `{', '.join(coverage['missingRunbookDirectEquivalent']) or 'none'}`",
            f"- Undocumented wrapper tasks: `{', '.join(coverage['undocumentedWrapperTasks']) or 'none'}`",
            f"- Unknown wrapper tasks: `{', '.join(coverage['unknownWrapperTasks']) or 'none'}`",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    now = datetime.now(tz=UTC)
    dev_ps1_text = read_text(REPO_ROOT / "scripts" / "dev.ps1")
    runbook_text = read_text(REPO_ROOT / "docs" / "AUDIT_RUNBOOK.md")
    wrapper_tasks = extract_dev_tasks(dev_ps1_text)
    runbook_mappings = extract_runbook_direct_equivalents(runbook_text)
    command_coverage = build_command_coverage(wrapper_tasks, runbook_mappings)
    rows = [
        build_mechanism_row(
            mechanism=mechanism,
            wrapper_tasks=wrapper_tasks,
            runbook_mappings=runbook_mappings,
            now=now,
            stale_days=args.stale_days,
        )
        for mechanism in MECHANISMS
    ]
    maybe_measure_rows(
        rows=rows,
        mechanisms=MECHANISMS,
        measure_smoke=args.measure_smoke,
        include_heavy=args.include_heavy,
        timeout_seconds=args.timeout_seconds,
    )
    payload = build_report_payload(
        context=collect_git_context(),
        rows=rows,
        command_coverage=command_coverage,
        measure_smoke=args.measure_smoke,
        include_heavy=args.include_heavy,
        timeout_seconds=args.timeout_seconds,
        stale_days=args.stale_days,
        json_path=args.json_path,
        markdown_path=args.markdown_path,
    )
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, format_report_markdown(payload))
    print(format_report_markdown(payload))


if __name__ == "__main__":
    main()
