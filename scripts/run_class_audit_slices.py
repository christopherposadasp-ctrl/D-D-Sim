from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine.services.barbarian_audit import (
    get_barbarian_audit_player_preset_ids,
    get_barbarian_audit_scenario_ids,
)
from backend.engine.services.fighter_audit import (
    get_fighter_audit_player_preset_ids,
    get_fighter_audit_scenario_ids,
)

AuditClass = Literal["fighter", "barbarian"]
AuditProfile = Literal["quick", "full"]
SliceStatus = Literal["pass", "warn", "fail", "timeout", "skipped"]

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pass1" / "class_slices"
DEFAULT_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class ClassAuditSlice:
    audit_class: AuditClass
    profile: AuditProfile
    player_preset_id: str
    scenario_id: str

    @property
    def slug(self) -> str:
        return f"{self.audit_class}_{self.profile}_{self.player_preset_id}_{self.scenario_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Fighter/Barbarian audit slices one at a time.")
    parser.add_argument(
        "--class",
        action="append",
        choices=("fighter", "barbarian", "both"),
        dest="audit_classes",
        default=None,
        help="Audit class to run. Repeat for multiple classes, or use both. Defaults to both.",
    )
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--scenario", action="append", dest="scenario_ids", default=None)
    parser.add_argument("--player-preset", action="append", dest="player_preset_ids", default=None)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--summary-json-path", type=Path, default=None)
    parser.add_argument("--summary-markdown-path", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-slices", type=int, default=None, help="Limit execution to the first N planned slices.")
    parser.add_argument("--force", action="store_true", help="Rerun slices even when their JSON report already exists.")
    parser.add_argument("--include-rules-gate", action="store_true", help="Do not pass --skip-rules-gate to slice runners.")
    parser.add_argument("--dry-run", action="store_true", help="Plan slices and write a summary without running them.")
    parser.add_argument("--fixed-seed-runs", type=int, default=None)
    parser.add_argument("--behavior-batch-size", type=int, default=None)
    parser.add_argument("--health-batch-size", type=int, default=None)
    return parser.parse_args()


def normalize_classes(raw_classes: list[str] | None) -> tuple[AuditClass, ...]:
    if not raw_classes:
        return ("fighter", "barbarian")
    if "both" in raw_classes:
        return ("fighter", "barbarian")
    normalized: list[AuditClass] = []
    for raw_class in raw_classes:
        if raw_class not in normalized:
            normalized.append(raw_class)  # type: ignore[arg-type]
    return tuple(normalized)


def get_default_player_presets(audit_class: AuditClass) -> tuple[str, ...]:
    if audit_class == "fighter":
        return get_fighter_audit_player_preset_ids()
    return get_barbarian_audit_player_preset_ids()


def get_default_scenarios(audit_class: AuditClass) -> tuple[str, ...]:
    if audit_class == "fighter":
        return get_fighter_audit_scenario_ids()
    return get_barbarian_audit_scenario_ids()


def build_slices(
    audit_classes: tuple[AuditClass, ...],
    profile: AuditProfile,
    scenario_ids: list[str] | None = None,
    player_preset_ids: list[str] | None = None,
    max_slices: int | None = None,
) -> list[ClassAuditSlice]:
    slices: list[ClassAuditSlice] = []
    for audit_class in audit_classes:
        class_player_presets = tuple(player_preset_ids) if player_preset_ids else get_default_player_presets(audit_class)
        class_scenarios = tuple(scenario_ids) if scenario_ids else get_default_scenarios(audit_class)
        for player_preset_id in class_player_presets:
            for scenario_id in class_scenarios:
                slices.append(ClassAuditSlice(audit_class, profile, player_preset_id, scenario_id))
                if max_slices is not None and len(slices) >= max_slices:
                    return slices
    return slices


def slice_report_paths(report_dir: Path, audit_slice: ClassAuditSlice) -> tuple[Path, Path]:
    return report_dir / f"{audit_slice.slug}.json", report_dir / f"{audit_slice.slug}.md"


def build_slice_command(args: argparse.Namespace, audit_slice: ClassAuditSlice, json_path: Path, markdown_path: Path) -> list[str]:
    script_name = "run_fighter_audit.py" if audit_slice.audit_class == "fighter" else "run_barbarian_audit.py"
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / script_name),
        f"--{audit_slice.profile}",
        "--scenario",
        audit_slice.scenario_id,
        "--player-preset",
        audit_slice.player_preset_id,
        "--json-path",
        str(json_path),
        "--markdown-path",
        str(markdown_path),
    ]
    if not args.include_rules_gate:
        command.append("--skip-rules-gate")
    if args.fixed_seed_runs is not None:
        command.extend(["--fixed-seed-runs", str(args.fixed_seed_runs)])
    if args.behavior_batch_size is not None:
        command.extend(["--behavior-batch-size", str(args.behavior_batch_size)])
    if args.health_batch_size is not None:
        command.extend(["--health-batch-size", str(args.health_batch_size)])
    return command


def tail_lines(value: str | None, limit: int = 24) -> list[str]:
    if not value:
        return []
    return value.splitlines()[-limit:]


def get_existing_report_status(json_path: Path) -> tuple[str, str]:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "fail", "Existing report could not be parsed."
    return str(payload.get("overallStatus", "fail")), "Existing slice report reused."


def run_slice(args: argparse.Namespace, audit_slice: ClassAuditSlice) -> dict[str, object]:
    json_path, markdown_path = slice_report_paths(args.report_dir, audit_slice)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_slice_command(args, audit_slice, json_path, markdown_path)

    if json_path.exists() and not args.force:
        report_status, detail = get_existing_report_status(json_path)
        status = report_status if report_status in {"pass", "warn", "fail"} else "fail"
        return {
            "class": audit_slice.audit_class,
            "profile": audit_slice.profile,
            "playerPresetId": audit_slice.player_preset_id,
            "scenarioId": audit_slice.scenario_id,
            "status": status,
            "executionStatus": "skipped",
            "reportStatus": report_status,
            "hardBlocker": False,
            "detail": detail,
            "jsonPath": str(json_path),
            "markdownPath": str(markdown_path),
            "command": " ".join(command),
            "elapsedSeconds": 0.0,
        }

    if args.dry_run:
        return {
            "class": audit_slice.audit_class,
            "profile": audit_slice.profile,
            "playerPresetId": audit_slice.player_preset_id,
            "scenarioId": audit_slice.scenario_id,
            "status": "skipped",
            "executionStatus": "dry_run",
            "reportStatus": "not_run",
            "hardBlocker": False,
            "detail": "Dry run only.",
            "jsonPath": str(json_path),
            "markdownPath": str(markdown_path),
            "command": " ".join(command),
            "elapsedSeconds": 0.0,
        }

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "class": audit_slice.audit_class,
            "profile": audit_slice.profile,
            "playerPresetId": audit_slice.player_preset_id,
            "scenarioId": audit_slice.scenario_id,
            "status": "timeout",
            "reportStatus": "timeout",
            "hardBlocker": True,
            "detail": f"Slice exceeded {args.timeout_seconds:.1f}s timeout.",
            "jsonPath": str(json_path),
            "markdownPath": str(markdown_path),
            "command": " ".join(command),
            "elapsedSeconds": time.perf_counter() - started,
            "stdoutTail": tail_lines(exc.stdout if isinstance(exc.stdout, str) else None),
            "stderrTail": tail_lines(exc.stderr if isinstance(exc.stderr, str) else None),
        }

    elapsed = time.perf_counter() - started
    report_status = "fail"
    detail = "Slice runner exited successfully."
    if json_path.exists():
        report_status, _ = get_existing_report_status(json_path)
    elif completed.returncode == 0:
        detail = "Slice runner exited successfully but did not write JSON."

    status: SliceStatus = "pass"
    hard_blocker = completed.returncode != 0 or not json_path.exists()
    if hard_blocker or report_status == "fail":
        status = "fail"
    elif report_status == "warn":
        status = "warn"

    return {
        "class": audit_slice.audit_class,
        "profile": audit_slice.profile,
        "playerPresetId": audit_slice.player_preset_id,
        "scenarioId": audit_slice.scenario_id,
        "status": status,
        "executionStatus": "run",
        "reportStatus": report_status,
        "hardBlocker": hard_blocker,
        "detail": detail,
        "jsonPath": str(json_path),
        "markdownPath": str(markdown_path),
        "command": " ".join(command),
        "exitCode": completed.returncode,
        "elapsedSeconds": elapsed,
        "stdoutTail": tail_lines(completed.stdout),
        "stderrTail": tail_lines(completed.stderr),
    }


def should_stop_after_result(result: dict[str, object]) -> bool:
    return bool(result.get("hardBlocker"))


def build_summary(results: list[dict[str, object]], planned_count: int, args: argparse.Namespace) -> dict[str, object]:
    status_counts = {
        status: sum(1 for result in results if result["status"] == status)
        for status in ("pass", "warn", "fail", "timeout", "skipped")
    }
    hard_blocked = any(bool(result.get("hardBlocker")) for result in results)
    if status_counts["fail"] or status_counts["timeout"]:
        overall_status = "fail"
    elif status_counts["warn"]:
        overall_status = "warn"
    else:
        overall_status = "pass"

    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "mode": "dry_run" if args.dry_run else "run",
        "profile": args.profile,
        "plannedSliceCount": planned_count,
        "completedSliceCount": len(results),
        "overallStatus": overall_status,
        "statusCounts": status_counts,
        "stopReason": "hard_blocker" if hard_blocked and len(results) < planned_count else None,
        "results": results,
    }


def format_summary_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Class Audit Slice Summary",
        "",
        f"- Generated: `{summary['generatedAt']}`",
        f"- Mode: `{summary['mode']}`",
        f"- Profile: `{summary['profile']}`",
        f"- Overall status: `{summary['overallStatus']}`",
        f"- Completed/planned: `{summary['completedSliceCount']}/{summary['plannedSliceCount']}`",
        "",
        "## Results",
        "| class | playerPresetId | scenarioId | status | reportStatus | elapsed |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for result in summary["results"]:
        lines.append(
            "| "
            f"{result['class']} | "
            f"{result['playerPresetId']} | "
            f"{result['scenarioId']} | "
            f"{result['status']} | "
            f"{result['reportStatus']} | "
            f"{float(result.get('elapsedSeconds', 0.0)):.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def default_summary_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y-%m-%d")
    json_path = args.summary_json_path or args.report_dir / f"class_audit_slices_summary_{stamp}.json"
    markdown_path = args.summary_markdown_path or args.report_dir / f"class_audit_slices_summary_{stamp}.md"
    return json_path, markdown_path


def write_summary(summary: dict[str, object], args: argparse.Namespace) -> tuple[Path, Path]:
    json_path, markdown_path = default_summary_paths(args)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(format_summary_markdown(summary), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    args = parse_args()
    audit_classes = normalize_classes(args.audit_classes)
    slices = build_slices(
        audit_classes,
        args.profile,
        scenario_ids=args.scenario_ids,
        player_preset_ids=args.player_preset_ids,
        max_slices=args.max_slices,
    )

    results: list[dict[str, object]] = []
    print(f"Planned {len(slices)} class audit slice(s).")
    for audit_slice in slices:
        print(f"[{audit_slice.slug}] starting")
        result = run_slice(args, audit_slice)
        results.append(result)
        print(f"[{audit_slice.slug}] {result['status']} ({result['reportStatus']})")
        if should_stop_after_result(result):
            print(f"[{audit_slice.slug}] hard blocker; stopping remaining slices.")
            break

    summary = build_summary(results, len(slices), args)
    json_path, markdown_path = write_summary(summary, args)
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    raise SystemExit(1 if summary["overallStatus"] == "fail" else 0)


if __name__ == "__main__":
    main()
