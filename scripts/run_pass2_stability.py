from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.content.scenario_definitions import ACTIVE_SCENARIO_IDS
from backend.engine import run_batch, run_encounter
from backend.engine.models.state import EncounterConfig, MonsterBehavior
from scripts.audit_common import (
    Status,
    build_status_counts,
    collect_git_context,
    relative_path,
    text_tail,
    write_json_report,
    write_text_report,
)
from scripts.audit_findings import get_active_waivers, get_monitored_findings

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pass2"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "pass2_stability_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "pass2_stability_latest.md"
DEFAULT_PLAYER_PRESET_IDS = (
    "martial_mixed_party",
    "fighter_level2_sample_trio",
    "barbarian_level2_sample_trio",
    "rogue_level2_ranged_trio",
    "monk_level2_sample_trio",
    "wizard_sample_trio",
)
REPLAY_MONSTER_BEHAVIORS: tuple[MonsterBehavior, ...] = ("kind", "balanced", "evil")
DEFAULT_ASYNC_ROWS = (
    ("martial_mixed_party", "orc_push"),
    ("rogue_level2_ranged_trio", "marsh_predators"),
    ("fighter_level2_sample_trio", "hobgoblin_kill_box"),
)


@dataclass(frozen=True)
class ComparisonRow:
    kind: str
    row_id: str
    status: Status
    player_preset_id: str
    scenario_id: str
    seed: str
    details: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "rowId": self.row_id,
            "status": self.status,
            "playerPresetId": self.player_preset_id,
            "scenarioId": self.scenario_id,
            "seed": self.seed,
            **self.details,
        }


@dataclass(frozen=True)
class AsyncJobRow:
    row_id: str
    status: Status
    player_preset_id: str
    scenario_id: str
    seed: str
    details: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "rowId": self.row_id,
            "status": self.status,
            "playerPresetId": self.player_preset_id,
            "scenarioId": self.scenario_id,
            "seed": self.seed,
            **self.details,
        }


@dataclass(frozen=True)
class CommandRow:
    row_id: str
    status: Status
    command: list[str]
    exit_code: int | None
    elapsed_seconds: float
    timeout_seconds: int
    stdout_tail: list[str]
    stderr_tail: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "rowId": self.row_id,
            "status": self.status,
            "command": self.command,
            "exitCode": self.exit_code,
            "elapsedSeconds": round(self.elapsed_seconds, 3),
            "timeoutSeconds": self.timeout_seconds,
            "stdoutTail": self.stdout_tail,
            "stderrTail": self.stderr_tail,
        }


def collect_context() -> dict[str, Any]:
    return collect_git_context()


def build_seed(player_preset_id: str, scenario_id: str, suffix: str | None = None) -> str:
    base = f"pass2-{player_preset_id}-{scenario_id}"
    return f"{base}-{suffix}" if suffix else base


def build_config(
    *,
    player_preset_id: str,
    scenario_id: str,
    seed: str,
    monster_behavior: str,
    batch_size: int | None = None,
) -> EncounterConfig:
    return EncounterConfig(
        player_preset_id=player_preset_id,
        enemy_preset_id=scenario_id,
        seed=seed,
        player_behavior="balanced",
        monster_behavior=monster_behavior,
        batch_size=batch_size,
    )


def make_comparison_row(
    *,
    kind: str,
    row_id: str,
    player_preset_id: str,
    scenario_id: str,
    seed: str,
    first: dict[str, Any],
    second: dict[str, Any],
    extra_details: dict[str, Any] | None = None,
) -> ComparisonRow:
    status: Status = "pass" if first == second else "fail"
    details = dict(extra_details or {})
    if status == "fail":
        details["mismatch"] = describe_mismatch(first, second)
    return ComparisonRow(
        kind=kind,
        row_id=row_id,
        status=status,
        player_preset_id=player_preset_id,
        scenario_id=scenario_id,
        seed=seed,
        details=details,
    )


def describe_mismatch(first: Any, second: Any, path: str = "$") -> dict[str, Any]:
    if type(first) is not type(second):
        return {"path": path, "firstType": type(first).__name__, "secondType": type(second).__name__}
    if isinstance(first, dict):
        first_keys = set(first)
        second_keys = set(second)
        if first_keys != second_keys:
            return {
                "path": path,
                "firstOnlyKeys": sorted(first_keys - second_keys),
                "secondOnlyKeys": sorted(second_keys - first_keys),
            }
        for key in sorted(first_keys):
            if first[key] != second[key]:
                return describe_mismatch(first[key], second[key], f"{path}.{key}")
    elif isinstance(first, list):
        if len(first) != len(second):
            return {"path": path, "firstLength": len(first), "secondLength": len(second)}
        for index, (left, right) in enumerate(zip(first, second, strict=True)):
            if left != right:
                return describe_mismatch(left, right, f"{path}[{index}]")
    return {"path": path, "first": first, "second": second}


def detect_progress_regression(completed_runs: list[int]) -> bool:
    return any(current < previous for previous, current in zip(completed_runs, completed_runs[1:], strict=False))


def run_replay_determinism(
    player_preset_ids: list[str],
    scenario_ids: list[str],
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for player_preset_id in player_preset_ids:
        for scenario_id in scenario_ids:
            for monster_behavior in REPLAY_MONSTER_BEHAVIORS:
                seed = build_seed(player_preset_id, scenario_id, f"replay-{monster_behavior}")
                config = build_config(
                    player_preset_id=player_preset_id,
                    scenario_id=scenario_id,
                    seed=seed,
                    monster_behavior=monster_behavior,
                )
                first = run_encounter(config).model_dump(by_alias=True, mode="json")
                second = run_encounter(config).model_dump(by_alias=True, mode="json")
                rows.append(
                    make_comparison_row(
                        kind="replay",
                        row_id=f"{player_preset_id}/{scenario_id}/{monster_behavior}",
                        player_preset_id=player_preset_id,
                        scenario_id=scenario_id,
                        seed=seed,
                        first=first,
                        second=second,
                        extra_details={
                            "playerBehavior": "balanced",
                            "requestedMonsterBehavior": "combined",
                            "resolvedMonsterBehavior": monster_behavior,
                            "comparison": "run_encounter model_dump(by_alias=True)",
                        },
                    )
                )
    return rows


def run_batch_determinism(
    player_preset_ids: list[str],
    scenario_ids: list[str],
    batch_size: int,
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for player_preset_id in player_preset_ids:
        for scenario_id in scenario_ids:
            seed = build_seed(player_preset_id, scenario_id, "batch-combined")
            config = build_config(
                player_preset_id=player_preset_id,
                scenario_id=scenario_id,
                seed=seed,
                monster_behavior="combined",
                batch_size=batch_size,
            )
            first = run_batch(config).model_dump(by_alias=True, mode="json")
            second = run_batch(config).model_dump(by_alias=True, mode="json")
            rows.append(
                make_comparison_row(
                    kind="batch",
                    row_id=f"{player_preset_id}/{scenario_id}/combined",
                    player_preset_id=player_preset_id,
                    scenario_id=scenario_id,
                    seed=seed,
                    first=first,
                    second=second,
                    extra_details={
                        "playerBehavior": "balanced",
                        "monsterBehavior": "combined",
                        "batchSize": batch_size,
                        "comparison": "BatchSummary model_dump(by_alias=True)",
                    },
                )
            )
    return rows


def run_async_job_check(
    *,
    client: TestClient,
    player_preset_id: str,
    scenario_id: str,
    batch_size: int,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> AsyncJobRow:
    seed = build_seed(player_preset_id, scenario_id, "async-combined")
    config = build_config(
        player_preset_id=player_preset_id,
        scenario_id=scenario_id,
        seed=seed,
        monster_behavior="combined",
        batch_size=batch_size,
    )
    payload = config.model_dump(by_alias=True, mode="json")
    started = time.monotonic()
    response = client.post("/api/encounters/batch-jobs", json=payload)
    if response.status_code != 200:
        return AsyncJobRow(
            row_id=f"{player_preset_id}/{scenario_id}",
            status="fail",
            player_preset_id=player_preset_id,
            scenario_id=scenario_id,
            seed=seed,
            details={"error": "submit_failed", "statusCode": response.status_code, "response": response.json()},
        )

    job = response.json()
    job_id = job["jobId"]
    completed_samples = [int(job["completedRuns"])]
    status_samples = [job["status"]]
    final_payload = job

    while time.monotonic() - started < timeout_seconds:
        response = client.get(f"/api/encounters/batch-jobs/{job_id}")
        if response.status_code != 200:
            return AsyncJobRow(
                row_id=f"{player_preset_id}/{scenario_id}",
                status="fail",
                player_preset_id=player_preset_id,
                scenario_id=scenario_id,
                seed=seed,
                details={
                    "jobId": job_id,
                    "error": "poll_failed",
                    "statusCode": response.status_code,
                    "completedRunSamples": completed_samples,
                },
            )
        final_payload = response.json()
        completed_samples.append(int(final_payload["completedRuns"]))
        status_samples.append(final_payload["status"])
        if final_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(poll_interval_seconds)

    status: Status = "pass"
    details: dict[str, Any] = {
        "jobId": job_id,
        "completedRunSamples": completed_samples,
        "statusSamples": status_samples,
        "pollElapsedSeconds": round(time.monotonic() - started, 3),
        "batchSize": batch_size,
    }
    if detect_progress_regression(completed_samples):
        status = "fail"
        details["error"] = "completed_runs_regressed"
    elif final_payload["status"] != "completed":
        status = "fail"
        details["error"] = "job_did_not_complete"
        details["finalStatus"] = final_payload["status"]
    elif final_payload.get("batchSummary") is None:
        status = "fail"
        details["error"] = "missing_batch_summary"
    elif int(final_payload["completedRuns"]) != int(final_payload["totalRuns"]):
        status = "fail"
        details["error"] = "completed_runs_did_not_match_total_runs"
    else:
        sync_summary = run_batch(config).model_dump(by_alias=True, mode="json")
        async_summary = final_payload["batchSummary"]
        if async_summary != sync_summary:
            status = "fail"
            details["error"] = "async_summary_desynchronized"
            details["mismatch"] = describe_mismatch(async_summary, sync_summary)

    return AsyncJobRow(
        row_id=f"{player_preset_id}/{scenario_id}",
        status=status,
        player_preset_id=player_preset_id,
        scenario_id=scenario_id,
        seed=seed,
        details=details,
    )


def run_async_job_checks(
    rows: list[tuple[str, str]],
    batch_size: int,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> list[AsyncJobRow]:
    client = TestClient(app)
    return [
        run_async_job_check(
            client=client,
            player_preset_id=player_preset_id,
            scenario_id=scenario_id,
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        for player_preset_id, scenario_id in rows
    ]


def select_async_rows(
    player_preset_ids: list[str],
    scenario_ids: list[str],
    restricted: bool,
) -> list[tuple[str, str]]:
    if not restricted:
        return list(DEFAULT_ASYNC_ROWS)
    selected_players = set(player_preset_ids)
    selected_scenarios = set(scenario_ids)
    matching_rows = [
        (player_preset_id, scenario_id)
        for player_preset_id, scenario_id in DEFAULT_ASYNC_ROWS
        if player_preset_id in selected_players and scenario_id in selected_scenarios
    ]
    if matching_rows:
        return matching_rows
    return [(player_preset_ids[0], scenario_ids[0])]


def powershell_command(*args: str) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\scripts\\dev.ps1", *args]


def run_command(row_id: str, command: list[str], timeout_seconds: int) -> CommandRow:
    started = time.monotonic()
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
        return CommandRow(
            row_id=row_id,
            status="pass" if completed.returncode == 0 else "fail",
            command=command,
            exit_code=completed.returncode,
            elapsed_seconds=time.monotonic() - started,
            timeout_seconds=timeout_seconds,
            stdout_tail=text_tail(completed.stdout),
            stderr_tail=text_tail(completed.stderr),
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        return CommandRow(
            row_id=row_id,
            status="fail",
            command=command,
            exit_code=None,
            elapsed_seconds=time.monotonic() - started,
            timeout_seconds=timeout_seconds,
            stdout_tail=text_tail(stdout),
            stderr_tail=text_tail(stderr),
        )


def build_long_audit_commands(timeout_seconds: int) -> list[tuple[str, list[str], int]]:
    class_slice_json = REPO_ROOT / "reports" / "pass2" / "class_slices_mixed_party_latest.json"
    class_slice_md = REPO_ROOT / "reports" / "pass2" / "class_slices_mixed_party_latest.md"
    return [
        ("audit_quick", powershell_command("audit-quick"), timeout_seconds),
        ("rogue_audit_quick", powershell_command("rogue-audit-quick"), timeout_seconds),
        (
            "fighter_barbarian_mixed_party_slices",
            powershell_command(
                "class-audit-slices",
                "--class",
                "fighter",
                "--class",
                "barbarian",
                "--profile",
                "quick",
                "--player-preset",
                "martial_mixed_party",
                "--force",
                "--timeout-seconds",
                "300",
                "--summary-json-path",
                str(class_slice_json),
                "--summary-markdown-path",
                str(class_slice_md),
            ),
            timeout_seconds,
        ),
    ]


def run_long_audits(skip_long_audits: bool, timeout_seconds: int) -> list[CommandRow]:
    if skip_long_audits:
        return [
            CommandRow(
                row_id="long_audits",
                status="skipped",
                command=[],
                exit_code=0,
                elapsed_seconds=0,
                timeout_seconds=timeout_seconds,
                stdout_tail=["Skipped by --skip-long-audits."],
                stderr_tail=[],
            )
        ]
    return [
        run_command(row_id=row_id, command=command, timeout_seconds=command_timeout)
        for row_id, command, command_timeout in build_long_audit_commands(timeout_seconds)
    ]


def determine_overall_status(
    *,
    replay_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
    async_rows: list[dict[str, Any]],
    command_rows: list[dict[str, Any]],
    known_warnings: list[dict[str, Any]],
) -> Status:
    checked_rows = [*replay_rows, *batch_rows, *async_rows, *command_rows]
    if any(row["status"] == "fail" for row in checked_rows):
        return "fail"
    if known_warnings:
        return "warn"
    return "pass"


def build_report_payload(
    *,
    context: dict[str, Any],
    replay_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
    async_rows: list[dict[str, Any]],
    command_rows: list[dict[str, Any]],
    json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    known_warnings = get_monitored_findings()
    waivers = get_active_waivers()
    overall_status = determine_overall_status(
        replay_rows=replay_rows,
        batch_rows=batch_rows,
        async_rows=async_rows,
        command_rows=command_rows,
        known_warnings=known_warnings,
    )
    return {
        "overallStatus": overall_status,
        "context": context,
        "artifactPaths": {
            "json": relative_path(json_path),
            "markdown": relative_path(markdown_path),
        },
        "config": {
            "pass1ClosureCommit": "01cecc3",
            "playerBehavior": "balanced",
            "batchMonsterBehavior": "combined",
            "replayMonsterBehaviors": list(REPLAY_MONSTER_BEHAVIORS),
        },
        "statusCounts": {
            "replayDeterminism": build_status_counts(replay_rows),
            "batchDeterminism": build_status_counts(batch_rows),
            "asyncJobs": build_status_counts(async_rows),
            "longAudits": build_status_counts(command_rows),
        },
        "replayDeterminismRows": replay_rows,
        "batchDeterminismRows": batch_rows,
        "asyncJobRows": async_rows,
        "longAuditRows": command_rows,
        "knownWarnings": known_warnings,
        "waivers": waivers,
    }


def format_report_markdown(payload: dict[str, Any]) -> str:
    context = payload["context"]
    status_counts = payload["statusCounts"]
    lines = [
        "# Pass 2 Stability Report",
        "",
        f"- Overall status: `{payload['overallStatus']}`",
        f"- Branch: `{context['branch']}`",
        f"- Commit: `{context['commit']}`",
        f"- Generated: `{context['generatedAt']}`",
        f"- JSON report: `{payload['artifactPaths']['json']}`",
        f"- Markdown report: `{payload['artifactPaths']['markdown']}`",
        "",
        "## Gate Counts",
        "",
        f"- Replay determinism: `{status_counts['replayDeterminism']}`",
        f"- Batch determinism: `{status_counts['batchDeterminism']}`",
        f"- Async jobs: `{status_counts['asyncJobs']}`",
        f"- Long audits: `{status_counts['longAudits']}`",
        "",
        "## Known Warnings",
        "",
    ]
    if payload["knownWarnings"]:
        lines.extend(f"- `{warning['id']}`: {warning['summary']}" for warning in payload["knownWarnings"])
    else:
        lines.append("- None.")
    lines.extend(["", "## Active Waivers", ""])
    if payload["waivers"]:
        lines.extend(f"- `{waiver['id']}`: {waiver['summary']}" for waiver in payload["waivers"])
    else:
        lines.append("- None.")

    failures = [
        (section, row)
        for section in ("replayDeterminismRows", "batchDeterminismRows", "asyncJobRows", "longAuditRows")
        for row in payload[section]
        if row["status"] == "fail"
    ]
    lines.extend(["", "## Blockers", ""])
    if failures:
        lines.extend(f"- `{section}` `{row['rowId']}` failed." for section, row in failures[:20])
        if len(failures) > 20:
            lines.append(f"- {len(failures) - 20} additional failure(s) omitted from Markdown summary.")
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Pass 2 stability and determinism checks.")
    parser.add_argument("--player-preset", action="append", dest="player_preset_ids", help="Restrict player presets.")
    parser.add_argument("--scenario", action="append", dest="scenario_ids", help="Restrict scenarios.")
    parser.add_argument("--determinism-batch-size", type=int, default=3)
    parser.add_argument("--async-batch-size", type=int, default=2)
    parser.add_argument("--async-timeout-seconds", type=int, default=45)
    parser.add_argument("--async-poll-interval-seconds", type=float, default=0.05)
    parser.add_argument("--long-audit-timeout-seconds", type=int, default=3600)
    parser.add_argument("--skip-async", action="store_true")
    parser.add_argument("--skip-long-audits", action="store_true")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    player_preset_ids = args.player_preset_ids or list(DEFAULT_PLAYER_PRESET_IDS)
    scenario_ids = args.scenario_ids or list(ACTIVE_SCENARIO_IDS)

    print(
        "Running Pass 2 stability:"
        f" {len(player_preset_ids)} player preset(s),"
        f" {len(scenario_ids)} scenario(s),"
        f" replay monster behaviors {', '.join(REPLAY_MONSTER_BEHAVIORS)}."
    )
    replay_rows = [row.to_payload() for row in run_replay_determinism(player_preset_ids, scenario_ids)]
    print(f"Replay determinism rows complete: {len(replay_rows)}")

    batch_rows = [
        row.to_payload()
        for row in run_batch_determinism(player_preset_ids, scenario_ids, args.determinism_batch_size)
    ]
    print(f"Batch determinism rows complete: {len(batch_rows)}")

    if args.skip_async:
        async_rows = [
            {
                "rowId": "async_jobs",
                "status": "skipped",
                "playerPresetId": "",
                "scenarioId": "",
                "seed": "",
                "details": "Skipped by --skip-async.",
            }
        ]
    else:
        async_rows = [
            row.to_payload()
            for row in run_async_job_checks(
                rows=select_async_rows(
                    player_preset_ids=player_preset_ids,
                    scenario_ids=scenario_ids,
                    restricted=bool(args.player_preset_ids or args.scenario_ids),
                ),
                batch_size=args.async_batch_size,
                timeout_seconds=args.async_timeout_seconds,
                poll_interval_seconds=args.async_poll_interval_seconds,
            )
        ]
    print(f"Async job rows complete: {len(async_rows)}")

    command_rows = [
        row.to_payload()
        for row in run_long_audits(
            skip_long_audits=args.skip_long_audits,
            timeout_seconds=args.long_audit_timeout_seconds,
        )
    ]
    print(f"Long audit rows complete: {len(command_rows)}")

    payload = build_report_payload(
        context=collect_context(),
        replay_rows=replay_rows,
        batch_rows=batch_rows,
        async_rows=async_rows,
        command_rows=command_rows,
        json_path=args.json_path,
        markdown_path=args.markdown_path,
    )
    markdown = format_report_markdown(payload)
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, markdown)
    print(f"Wrote {relative_path(args.json_path)}")
    print(f"Wrote {relative_path(args.markdown_path)}")
    print(f"Overall status: {payload['overallStatus']}")
    if payload["overallStatus"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
