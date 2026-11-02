from __future__ import annotations

import argparse
import faulthandler
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine import run_encounter, summarize_encounter
from backend.engine.combat.engine import run_encounter_summary_fast
from backend.engine.combat.setup import resolve_player_behavior
from backend.engine.models.state import EncounterConfig, EncounterSummary, RunEncounterResult, UnitState
from backend.engine.services.barbarian_audit import extract_barbarian_run_metrics

DEFAULT_PLAYER_PRESET_ID = "martial_mixed_party"
DEFAULT_SCENARIO_ID = "wolf_harriers"
DEFAULT_SEED_PREFIX = "barbarian-audit"
DEFAULT_REPORT_STEM = "barbarian_stall_investigation"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_SLOW_THRESHOLD_SECONDS = 5.0
PathKind = Literal["metrics", "run_encounter", "fast_summary"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Investigate the focused Barbarian audit behavior-stage stall.")
    parser.add_argument("--player-preset", default=DEFAULT_PLAYER_PRESET_ID)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO_ID)
    parser.add_argument("--seed-prefix", default=DEFAULT_SEED_PREFIX)
    parser.add_argument("--run-start", type=int, default=0)
    parser.add_argument("--run-count", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--slow-threshold-seconds", type=float, default=DEFAULT_SLOW_THRESHOLD_SECONDS)
    parser.add_argument("--report-dir", type=Path, default=REPO_ROOT / "reports" / "pass1")
    parser.add_argument("--json-path", type=Path, default=None)
    parser.add_argument("--markdown-path", type=Path, default=None)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--child-behavior", choices=("smart", "dumb", "balanced"), default="smart")
    parser.add_argument("--child-run-index", type=int, default=0)
    parser.add_argument("--child-path", choices=("metrics", "run_encounter", "fast_summary"), default="metrics")
    return parser.parse_args()


def build_behavior_seed(seed_prefix: str, player_preset_id: str, scenario_id: str, behavior: str, run_index: int) -> str:
    return f"{seed_prefix}-{player_preset_id}-{scenario_id}-behavior-{behavior}-{run_index:03d}"


def summarize_unit(unit: UnitState) -> dict[str, object]:
    return {
        "id": unit.id,
        "classId": unit.class_id,
        "combatRole": unit.combat_role,
        "currentHp": unit.current_hp,
        "maxHp": unit.max_hp,
        "dead": unit.conditions.dead,
        "unconscious": unit.conditions.unconscious,
        "position": unit.position.model_dump(mode="json") if unit.position else None,
    }


def summarize_result(result: RunEncounterResult, elapsed_seconds: float) -> dict[str, object]:
    summary = summarize_encounter(result.final_state)
    return {
        "status": "pass",
        "elapsedSeconds": elapsed_seconds,
        "terminalState": result.final_state.terminal_state,
        "winner": summary.winner,
        "rounds": summary.rounds,
        "replayFrameCount": len(result.replay_frames),
        "eventCount": len(result.events),
        "finalUnits": {
            unit_id: summarize_unit(unit)
            for unit_id, unit in sorted(result.final_state.units.items())
        },
    }


def summarize_fast_result(summary: EncounterSummary, elapsed_seconds: float) -> dict[str, object]:
    return {
        "status": "pass",
        "elapsedSeconds": elapsed_seconds,
        "terminalState": "complete",
        "winner": summary.winner,
        "rounds": summary.rounds,
        "replayFrameCount": None,
        "eventCount": None,
        "finalUnits": {},
    }


def run_child_probe(args: argparse.Namespace) -> int:
    faulthandler.enable(file=sys.stderr, all_threads=True)
    faulthandler.dump_traceback_later(args.timeout_seconds, file=sys.stderr, repeat=False, exit=True)

    seed = build_behavior_seed(
        args.seed_prefix,
        args.player_preset,
        args.scenario,
        args.child_behavior,
        args.child_run_index,
    )
    resolved_behavior = resolve_player_behavior(args.child_behavior, args.child_run_index)
    encounter_config = EncounterConfig(
        seed=seed,
        enemy_preset_id=args.scenario,
        player_preset_id=args.player_preset,
        player_behavior=resolved_behavior,
        monster_behavior="balanced",
    )

    started = time.perf_counter()
    try:
        if args.child_path == "fast_summary":
            summary = run_encounter_summary_fast(encounter_config)
            payload = summarize_fast_result(summary, time.perf_counter() - started)
        else:
            result = run_encounter(encounter_config)
            payload = summarize_result(result, time.perf_counter() - started)
            if args.child_path == "metrics":
                metrics = extract_barbarian_run_metrics(result)
                payload["metrics"] = {
                    "openingRageOpportunities": metrics.opening_rage_opportunities,
                    "openingRageSuccesses": metrics.opening_rage_successes,
                    "rageDroppedWithoutQualifyingReasonCount": metrics.rage_dropped_without_qualifying_reason_count,
                    "rageExtendedCount": metrics.rage_extended_count,
                    "greataxeAttackCount": metrics.greataxe_attack_count,
                    "handaxeAttackCount": metrics.handaxe_attack_count,
                    "barbarianDownedCount": metrics.barbarian_downed_count,
                    "barbarianDeathCount": metrics.barbarian_death_count,
                }
                payload["elapsedSeconds"] = time.perf_counter() - started

        payload.update(
            {
                "seed": seed,
                "requestedBehavior": args.child_behavior,
                "resolvedBehavior": resolved_behavior,
                "runIndex": args.child_run_index,
                "path": args.child_path,
            }
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    except Exception as exc:
        payload = {
            "status": "error",
            "seed": seed,
            "requestedBehavior": args.child_behavior,
            "resolvedBehavior": resolved_behavior,
            "runIndex": args.child_run_index,
            "path": args.child_path,
            "elapsedSeconds": time.perf_counter() - started,
            "errorType": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(payload, sort_keys=True))
        return 1


def tail_lines(value: str | None, limit: int = 80) -> list[str]:
    if not value:
        return []
    return value.splitlines()[-limit:]


def run_parent_probe(
    args: argparse.Namespace,
    behavior: str,
    run_index: int,
    path: PathKind,
) -> dict[str, object]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--player-preset",
        args.player_preset,
        "--scenario",
        args.scenario,
        "--seed-prefix",
        args.seed_prefix,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--child-behavior",
        behavior,
        "--child-run-index",
        str(run_index),
        "--child-path",
        path,
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout_seconds + 5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "parent_timeout",
            "seed": build_behavior_seed(args.seed_prefix, args.player_preset, args.scenario, behavior, run_index),
            "requestedBehavior": behavior,
            "runIndex": run_index,
            "path": path,
            "elapsedSeconds": time.perf_counter() - started,
            "stdoutTail": tail_lines(exc.stdout if isinstance(exc.stdout, str) else None),
            "stderrTail": tail_lines(exc.stderr if isinstance(exc.stderr, str) else None),
        }

    elapsed = time.perf_counter() - started
    stdout = completed.stdout.strip()
    stderr_tail = tail_lines(completed.stderr)
    try:
        payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except json.JSONDecodeError:
        payload = {}

    if not payload:
        payload = {
            "status": "child_failed_without_json",
            "seed": build_behavior_seed(args.seed_prefix, args.player_preset, args.scenario, behavior, run_index),
            "requestedBehavior": behavior,
            "runIndex": run_index,
            "path": path,
        }

    if completed.returncode != 0 and payload.get("status") == "pass":
        payload["status"] = "child_nonzero"
    elif completed.returncode != 0 and payload.get("status") not in {"error", "timeout"}:
        payload["status"] = "child_timeout_or_error" if stderr_tail else "child_nonzero"

    payload["parentElapsedSeconds"] = elapsed
    payload["exitCode"] = completed.returncode
    payload["stdoutTail"] = tail_lines(completed.stdout)
    payload["stderrTail"] = stderr_tail
    if "Timeout" in completed.stderr or "faulthandler" in completed.stderr:
        payload["timeoutStackCaptured"] = True
    return payload


def is_probe_problem(probe: dict[str, object], slow_threshold_seconds: float) -> bool:
    elapsed = float(probe.get("elapsedSeconds") or probe.get("parentElapsedSeconds") or 0)
    return probe.get("status") != "pass" or elapsed >= slow_threshold_seconds


def classify_probe_set(probes: list[dict[str, object]]) -> tuple[str, str]:
    problem_probes = [probe for probe in probes if probe.get("status") != "pass"]
    if not problem_probes:
        slow_probes = [probe for probe in probes if probe.get("slow") is True]
        if slow_probes:
            return "extreme_runtime", "All probes completed, but at least one seed exceeded the slow threshold."
        return "not_reproduced", "All focused behavior probes completed within the configured slow threshold."

    failing_paths = {str(probe.get("path")) for probe in problem_probes}
    stderr = "\n".join("\n".join(probe.get("stderrTail", [])) for probe in problem_probes)

    if "find_" in stderr or "path" in stderr.lower() or "decision" in stderr.lower():
        return "ai_pathing_hot_loop", "A timed-out stack references AI decision/pathing code."
    if "step_encounter" in stderr or "run_encounter" in failing_paths:
        return "engine_nontermination", "The raw encounter execution path did not complete."
    if "extract_barbarian_run_metrics" in stderr or failing_paths == {"metrics"}:
        return "audit_metric_extraction_issue", "Raw encounter execution appears narrower than the metrics path."
    if "fast_summary" in failing_paths:
        return "engine_nontermination", "The fast summary path did not complete."
    return "external_process_or_runtime_issue", "The focused subprocess failed without a narrower code-path signature."


def markdown_report(payload: dict[str, object]) -> str:
    lines = [
        "# Barbarian Stall Investigation",
        "",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Target: `{payload['playerPresetId']}:{payload['scenarioId']}`",
        f"- Overall status: `{payload['overallStatus']}`",
        f"- Root cause classification: `{payload['rootCauseClassification']}`",
        f"- Summary: {payload['rootCauseSummary']}",
        "",
        "## Probe Results",
        "| behavior | run | path | status | elapsed | winner | rounds | frames | events |",
        "| --- | ---: | --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for probe in payload["probes"]:
        lines.append(
            "| "
            f"{probe.get('requestedBehavior')} | "
            f"{probe.get('runIndex')} | "
            f"{probe.get('path')} | "
            f"{probe.get('status')} | "
            f"{float(probe.get('elapsedSeconds') or probe.get('parentElapsedSeconds') or 0):.3f} | "
            f"{probe.get('winner', '-')} | "
            f"{probe.get('rounds', '-')} | "
            f"{probe.get('replayFrameCount', '-')} | "
            f"{probe.get('eventCount', '-')} |"
        )

    if payload["problemProbes"]:
        lines.extend(["", "## Problem Probe Tails"])
        for probe in payload["problemProbes"]:
            lines.append(f"### {probe.get('seed')} / {probe.get('path')}")
            stderr_tail = probe.get("stderrTail", [])
            if stderr_tail:
                lines.extend([f"- {line}" for line in stderr_tail[-12:]])
            else:
                lines.append("- No stderr tail captured.")

    lines.extend(
        [
            "",
            "## Recommendation",
            str(payload["recommendedNextAction"]),
            "",
        ]
    )
    return "\n".join(lines)


def build_report_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    json_path = args.json_path or args.report_dir / f"{DEFAULT_REPORT_STEM}_{date_stamp}.json"
    markdown_path = args.markdown_path or args.report_dir / f"{DEFAULT_REPORT_STEM}_{date_stamp}.md"
    return json_path, markdown_path


def run_parent(args: argparse.Namespace) -> int:
    probes: list[dict[str, object]] = []
    run_indices = range(args.run_start, args.run_start + args.run_count)

    print(f"Probing {args.player_preset}:{args.scenario} smart behavior runs {args.run_start}..{args.run_start + args.run_count - 1}")
    for run_index in run_indices:
        probe = run_parent_probe(args, "smart", run_index, "metrics")
        probe["slow"] = is_probe_problem(probe, args.slow_threshold_seconds) and probe.get("status") == "pass"
        probes.append(probe)
        print(
            f"smart {run_index:03d}: {probe.get('status')} "
            f"{float(probe.get('elapsedSeconds') or probe.get('parentElapsedSeconds') or 0):.3f}s"
        )

    smart_problems = [probe for probe in probes if is_probe_problem(probe, args.slow_threshold_seconds)]
    if not smart_problems:
        print("Smart probes completed; probing dumb and balanced for progress-label ambiguity.")
        for behavior in ("dumb", "balanced"):
            for run_index in range(args.run_start, args.run_start + args.run_count):
                probe = run_parent_probe(args, behavior, run_index, "metrics")
                probe["slow"] = is_probe_problem(probe, args.slow_threshold_seconds) and probe.get("status") == "pass"
                probes.append(probe)
                print(
                    f"{behavior} {run_index:03d}: {probe.get('status')} "
                    f"{float(probe.get('elapsedSeconds') or probe.get('parentElapsedSeconds') or 0):.3f}s"
                )

    candidates = [probe for probe in probes if is_probe_problem(probe, args.slow_threshold_seconds)]
    compared_keys: set[tuple[str, int]] = set()
    for candidate in candidates:
        key = (str(candidate["requestedBehavior"]), int(candidate["runIndex"]))
        if key in compared_keys:
            continue
        compared_keys.add(key)
        for path in ("run_encounter", "fast_summary"):
            comparison = run_parent_probe(args, key[0], key[1], path)
            comparison["comparisonFor"] = candidate.get("path")
            comparison["slow"] = is_probe_problem(comparison, args.slow_threshold_seconds) and comparison.get("status") == "pass"
            probes.append(comparison)
            print(
                f"{key[0]} {key[1]:03d} {path}: {comparison.get('status')} "
                f"{float(comparison.get('elapsedSeconds') or comparison.get('parentElapsedSeconds') or 0):.3f}s"
            )

    for probe in probes:
        probe["slow"] = is_probe_problem(probe, args.slow_threshold_seconds) and probe.get("status") == "pass"

    problem_probes = [probe for probe in probes if is_probe_problem(probe, args.slow_threshold_seconds)]
    classification, summary = classify_probe_set(probes)
    overall_status = "pass" if classification == "not_reproduced" else "warn" if classification == "extreme_runtime" else "fail"
    if classification == "not_reproduced":
        next_action = "Treat the original stall as not reproduced on this code state; keep the focused regression before any broader rerun."
    elif classification == "extreme_runtime":
        next_action = "Profile the slowest completed seed before broadening Barbarian audit coverage."
    else:
        next_action = "Fix the classified nontermination path before any Barbarian audit rerun."

    payload = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "playerPresetId": args.player_preset,
        "scenarioId": args.scenario,
        "seedPrefix": args.seed_prefix,
        "timeoutSeconds": args.timeout_seconds,
        "slowThresholdSeconds": args.slow_threshold_seconds,
        "overallStatus": overall_status,
        "rootCauseClassification": classification,
        "rootCauseSummary": summary,
        "probes": probes,
        "problemProbes": problem_probes,
        "recommendedNextAction": next_action,
    }

    json_path, markdown_path = build_report_paths(args)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(payload) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    print(f"Classification: {classification}")
    return 0 if overall_status in {"pass", "warn"} else 1


def main() -> None:
    args = parse_args()
    if args.child:
        raise SystemExit(run_child_probe(args))
    raise SystemExit(run_parent(args))


if __name__ == "__main__":
    main()
