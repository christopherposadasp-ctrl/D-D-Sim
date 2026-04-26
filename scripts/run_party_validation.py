from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.player_loadouts import DEFAULT_PLAYER_PRESET_ID
from backend.content.scenario_definitions import get_scenario_definition
from backend.engine import run_batch, run_encounter, summarize_encounter
from backend.engine.combat.batch import resolve_batch_execution_plan
from backend.engine.models.state import (
    BatchCombinationSummary,
    BatchSummary,
    CombatEvent,
    EncounterConfig,
    RunEncounterResult,
    UnitState,
)
from scripts.audit_common import collect_git_context, write_json_report, write_text_report

DEFAULT_SCENARIO_IDS = ("hobgoblin_kill_box", "bugbear_dragnet", "deadwatch_phalanx")
DEFAULT_BATCH_SIZE = 400
DEFAULT_PLAYER_BEHAVIOR = "balanced"
DEFAULT_MONSTER_BEHAVIOR = "combined"
DEFAULT_REPLAY_MONSTER_BEHAVIOR = "balanced"
DEFAULT_REPLAY_SMOKE_RUNS = 2
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "party_validation"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "party_validation_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "party_validation_latest.md"
RULES_GATE_TARGETS = (
    "tests/rules/test_player_framework.py",
    "tests/rules/test_ai.py",
    "tests/rules/test_rules.py",
    "-k",
    "fighter or action_surge or battle_master or superiority or maneuver or riposte or trip or precision or great_weapon_master or hewing or barbarian or rage or reckless or rogue or sneak_attack or hide or paladin or bless or lay_on_hands or concentration or cure_wounds or smite or divine_smite or channel_divinity or natures_wrath or sentinel",
    "-q",
)

Status = Literal["pass", "warn", "fail", "skipped"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the focused current-party validation gate.")
    parser.add_argument("--player-preset", default=DEFAULT_PLAYER_PRESET_ID, help="Player preset id to validate.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        help="Scenario id to validate. Repeat to include more. Defaults to the focused Phase A set.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Total batch encounters per scenario.")
    parser.add_argument(
        "--player-behavior",
        default=DEFAULT_PLAYER_BEHAVIOR,
        choices=("smart", "dumb", "balanced"),
        help="Player behavior for replay and batch validation.",
    )
    parser.add_argument(
        "--monster-behavior",
        default=DEFAULT_MONSTER_BEHAVIOR,
        choices=("kind", "balanced", "evil", "combined"),
        help="Monster behavior for batch validation.",
    )
    parser.add_argument("--serial", action="store_true", help="Force serial batch health execution.")
    parser.add_argument("--workers", type=int, default=None, help="Requested batch worker count, capped at 8.")
    parser.add_argument("--skip-rules-gate", action="store_true", help="Skip the targeted pytest rules smoke.")
    parser.add_argument("--json", action="store_true", help="Print the final JSON payload to stdout.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH, help="Write the JSON report here.")
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH, help="Write the Markdown report here.")
    return parser.parse_args()


def run_rules_gate() -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", *RULES_GATE_TARGETS]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output_lines = [
        line
        for line in [*completed.stdout.splitlines(), *completed.stderr.splitlines()]
        if line.strip()
    ]
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": " ".join(command),
        "exitCode": completed.returncode,
        "stdoutTail": output_lines[-12:],
    }


def build_batch_run_plan(batch_size: int, monster_behavior: str) -> tuple[tuple[str, int], ...]:
    if monster_behavior != "combined":
        return ((monster_behavior, batch_size),)

    base_runs, remainder = divmod(batch_size, 3)
    runs_by_behavior = {"kind": base_runs, "balanced": base_runs, "evil": base_runs}
    for behavior in ("balanced", "kind", "evil")[:remainder]:
        runs_by_behavior[behavior] += 1

    return tuple((behavior, runs_by_behavior[behavior]) for behavior in ("kind", "balanced", "evil") if runs_by_behavior[behavior] > 0)


def weighted_average(weighted_values: list[tuple[int | float | None, int]]) -> int | float | None:
    total_weight = sum(weight for _, weight in weighted_values if weight > 0)
    if total_weight <= 0:
        return None
    total_value = sum(float(value) * weight for value, weight in weighted_values if value is not None and weight > 0)
    return total_value / total_weight


def to_combination_summary(summary: BatchSummary) -> BatchCombinationSummary:
    return BatchCombinationSummary(
        seed=summary.seed,
        player_behavior=summary.player_behavior,
        monster_behavior=summary.monster_behavior,
        batch_size=summary.batch_size,
        total_runs=summary.total_runs,
        player_win_rate=summary.player_win_rate,
        goblin_win_rate=summary.goblin_win_rate,
        mutual_annihilation_rate=summary.mutual_annihilation_rate,
        smart_player_win_rate=summary.smart_player_win_rate,
        dumb_player_win_rate=summary.dumb_player_win_rate,
        smart_run_count=summary.smart_run_count,
        dumb_run_count=summary.dumb_run_count,
        average_rounds=summary.average_rounds,
        average_fighter_deaths=summary.average_fighter_deaths,
        average_goblins_killed=summary.average_goblins_killed,
        average_remaining_fighter_hp=summary.average_remaining_fighter_hp,
        average_remaining_goblin_hp=summary.average_remaining_goblin_hp,
        stable_but_unconscious_count=summary.stable_but_unconscious_count,
    )


def combine_batch_summaries(seed: str, player_behavior: str, batch_size: int, summaries: list[BatchSummary]) -> BatchSummary:
    total_runs = sum(summary.total_runs for summary in summaries)
    smart_run_count = sum(summary.smart_run_count for summary in summaries)
    dumb_run_count = sum(summary.dumb_run_count for summary in summaries)

    return BatchSummary(
        seed=seed,
        player_behavior=player_behavior,
        monster_behavior="combined",
        batch_size=batch_size,
        total_runs=total_runs,
        player_win_rate=weighted_average([(summary.player_win_rate, summary.total_runs) for summary in summaries]) or 0.0,
        goblin_win_rate=weighted_average([(summary.goblin_win_rate, summary.total_runs) for summary in summaries]) or 0.0,
        mutual_annihilation_rate=weighted_average([(summary.mutual_annihilation_rate, summary.total_runs) for summary in summaries]) or 0.0,
        smart_player_win_rate=weighted_average([(summary.smart_player_win_rate, summary.smart_run_count) for summary in summaries]),
        dumb_player_win_rate=weighted_average([(summary.dumb_player_win_rate, summary.dumb_run_count) for summary in summaries]),
        smart_run_count=smart_run_count,
        dumb_run_count=dumb_run_count,
        average_rounds=weighted_average([(summary.average_rounds, summary.total_runs) for summary in summaries]) or 0.0,
        average_fighter_deaths=weighted_average([(summary.average_fighter_deaths, summary.total_runs) for summary in summaries]) or 0.0,
        average_goblins_killed=weighted_average([(summary.average_goblins_killed, summary.total_runs) for summary in summaries]) or 0.0,
        average_remaining_fighter_hp=weighted_average([(summary.average_remaining_fighter_hp, summary.total_runs) for summary in summaries]) or 0.0,
        average_remaining_goblin_hp=weighted_average([(summary.average_remaining_goblin_hp, summary.total_runs) for summary in summaries]) or 0.0,
        stable_but_unconscious_count=sum(summary.stable_but_unconscious_count for summary in summaries),
        combination_summaries=[to_combination_summary(summary) for summary in summaries],
    )


def event_text(event: CombatEvent) -> str:
    pieces = [
        event.text_summary,
        " ".join(event.condition_deltas),
        " ".join(str(value) for value in event.resolved_totals.values()),
    ]
    if event.damage_details:
        pieces.append(event.damage_details.weapon_id)
        pieces.append(event.damage_details.weapon_name)
        pieces.extend(component.damage_type for component in event.damage_details.damage_components)
        if event.damage_details.mastery_applied:
            pieces.append(event.damage_details.mastery_applied)
    return " ".join(pieces).lower()


def event_has_rogue_signature(event: CombatEvent, actor_id: str) -> bool:
    if event.actor_id != actor_id:
        return False
    if "hide" in event_text(event):
        return True
    return bool(
        event.damage_details
        and any(component.damage_type == "precision" for component in event.damage_details.damage_components)
    )


def feature_signatures_for_unit(unit: UnitState) -> tuple[str, tuple[str, ...]]:
    class_id = unit.class_id or ""
    loadout_id = unit.loadout_id or ""
    if class_id == "fighter":
        return "fighter", (
            "action surge",
            "second wind",
            "superiority",
            "precision attack",
            "trip attack",
            "riposte",
            "great weapon",
            "hewing",
        )
    if class_id == "barbarian":
        return "barbarian", ("enters a rage", "reckless attack")
    if class_id == "rogue":
        return "rogue", ("hide", "precision")
    if class_id == "monk":
        return "monk", ("flurry", "patient defense", "step of the wind", "martial arts")
    if class_id == "wizard":
        return "wizard", ("casts", "shield")
    if class_id == "paladin":
        return "paladin", (
            "bless",
            "lay on hands",
            "smite",
            "divine",
            "nature's wrath",
            "channel divinity",
            "sentinel",
            "guardian",
            "halt",
        )
    return loadout_id or unit.template_name, ()


def build_feature_evidence(replay_results: list[RunEncounterResult]) -> list[dict[str, Any]]:
    if not replay_results:
        return []

    units = [
        unit
        for unit in replay_results[0].final_state.units.values()
        if unit.faction == "fighters"
    ]
    evidence_rows: list[dict[str, Any]] = []
    all_events = [event for result in replay_results for event in result.events]

    for unit in sorted(units, key=lambda item: item.id):
        feature_label, patterns = feature_signatures_for_unit(unit)
        matching_events: list[CombatEvent] = []
        matched_patterns: set[str] = set()
        for event in all_events:
            if event.actor_id != unit.id:
                continue
            if feature_label == "rogue" and event_has_rogue_signature(event, unit.id):
                matching_events.append(event)
                matched_patterns.add("precision")
                continue
            normalized_event_text = event_text(event)
            event_patterns = {pattern for pattern in patterns if pattern in normalized_event_text}
            if event_patterns:
                matching_events.append(event)
                matched_patterns.update(event_patterns)

        evidence_rows.append(
            {
                "unitId": unit.id,
                "classId": unit.class_id,
                "level": unit.level,
                "loadoutId": unit.loadout_id,
                "signature": feature_label,
                "matchedPatterns": sorted(matched_patterns),
                "observed": bool(matching_events),
                "eventCount": len(matching_events),
                "example": matching_events[0].text_summary if matching_events else None,
                "status": "pass" if matching_events else "warn",
            }
        )

    return evidence_rows


def run_replay_smoke(
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    player_behavior: str,
    replay_runs: int,
) -> tuple[list[dict[str, Any]], list[RunEncounterResult], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    results: list[RunEncounterResult] = []
    issues: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        for replay_index in range(replay_runs):
            seed = f"party-validation-{player_preset_id}-{scenario_id}-replay-{replay_index:02d}"
            start_time = time.perf_counter()
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=DEFAULT_REPLAY_MONSTER_BEHAVIOR,
                )
            )
            elapsed_seconds = time.perf_counter() - start_time
            summary = summarize_encounter(result.final_state)
            status: Status = "pass"
            if summary.winner is None or result.final_state.terminal_state != "complete":
                status = "fail"
                issues.append(
                    {
                        "severity": "fail",
                        "section": "replaySmoke",
                        "scenarioId": scenario_id,
                        "message": "Replay smoke did not complete with a winner.",
                        "recommendation": "Inspect the fixed seed replay before running larger batches.",
                    }
                )

            rows.append(
                {
                    "scenarioId": scenario_id,
                    "seed": seed,
                    "playerBehavior": result.final_state.player_behavior,
                    "monsterBehavior": result.final_state.monster_behavior,
                    "winner": summary.winner,
                    "rounds": summary.rounds,
                    "eventCount": len(result.events),
                    "elapsedSeconds": round(elapsed_seconds, 3),
                    "status": status,
                }
            )
            results.append(result)

    return rows, results, issues


def batch_summary_to_row(
    scenario_id: str,
    summary: BatchSummary,
    elapsed_seconds: float,
    execution_mode: str,
    worker_count: int,
) -> dict[str, Any]:
    behavior_breakdown = [
        {
            "monsterBehavior": combination.monster_behavior,
            "batchSize": combination.batch_size,
            "totalRuns": combination.total_runs,
            "playerWinRate": combination.player_win_rate,
            "enemyWinRate": combination.goblin_win_rate,
            "smartPlayerWinRate": combination.smart_player_win_rate,
            "dumbPlayerWinRate": combination.dumb_player_win_rate,
            "smartRunCount": combination.smart_run_count,
            "dumbRunCount": combination.dumb_run_count,
            "averageRounds": combination.average_rounds,
            "averagePartyDead": combination.average_fighter_deaths,
        }
        for combination in (summary.combination_summaries or [])
    ]
    return {
        "scenarioId": scenario_id,
        "playerBehavior": summary.player_behavior,
        "monsterBehavior": summary.monster_behavior,
        "batchSize": summary.batch_size,
        "totalRuns": summary.total_runs,
        "playerWinRate": summary.player_win_rate,
        "enemyWinRate": summary.goblin_win_rate,
        "smartPlayerWinRate": summary.smart_player_win_rate,
        "dumbPlayerWinRate": summary.dumb_player_win_rate,
        "smartRunCount": summary.smart_run_count,
        "dumbRunCount": summary.dumb_run_count,
        "averageRounds": summary.average_rounds,
        "averageFighterDeaths": summary.average_fighter_deaths,
        "averagePartyDead": summary.average_fighter_deaths,
        "executionMode": execution_mode,
        "workerCount": worker_count,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "status": "pass" if summary.total_runs > 0 else "fail",
        "behaviorBreakdown": behavior_breakdown,
    }


def run_batch_health(
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    batch_size: int,
    player_behavior: str,
    monster_behavior: str,
    force_serial: bool,
    worker_count: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    elapsed_total = 0.0

    for scenario_id in scenario_ids:
        seed = f"party-validation-{player_preset_id}-{scenario_id}-batch"
        batch_plan = build_batch_run_plan(batch_size, monster_behavior)
        total_runs = sum(run_count for _, run_count in batch_plan)
        execution_plan = resolve_batch_execution_plan(total_runs, force_serial=force_serial, worker_count=worker_count)
        print(
            f"[{scenario_id}] batch health: {total_runs} run(s), "
            f"{execution_plan.execution_mode}, {execution_plan.worker_count} worker(s)"
        )
        start_time = time.perf_counter()
        sub_summaries: list[BatchSummary] = []
        for sub_behavior, sub_batch_size in batch_plan:
            summary = run_batch(
                EncounterConfig(
                    seed=f"{seed}-{sub_behavior}",
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    batch_size=sub_batch_size,
                    player_behavior=player_behavior,
                    monster_behavior=sub_behavior,
                ),
                force_serial=force_serial,
                worker_count=worker_count,
            )
            sub_summaries.append(summary)

        summary = combine_batch_summaries(seed, player_behavior, batch_size, sub_summaries) if monster_behavior == "combined" else sub_summaries[0]
        elapsed_seconds = time.perf_counter() - start_time
        elapsed_total += elapsed_seconds
        row = batch_summary_to_row(
            scenario_id,
            summary,
            elapsed_seconds,
            execution_plan.execution_mode,
            execution_plan.worker_count,
        )
        rows.append(row)
        if row["status"] == "fail":
            issues.append(
                {
                    "severity": "fail",
                    "section": "batchHealth",
                    "scenarioId": scenario_id,
                    "message": "Batch health produced no completed runs.",
                    "recommendation": "Inspect batch execution before changing combat rules.",
                }
            )

    return rows, issues, elapsed_total


def collect_feature_issues(feature_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for row in feature_evidence:
        if row["observed"]:
            continue
        issues.append(
            {
                "severity": "warn",
                "section": "featureEvidence",
                "unitId": row["unitId"],
                "message": f"No signature feature evidence observed for {row['unitId']} ({row['signature']}).",
                "recommendation": "Use a focused class audit if this party member is under active development.",
            }
        )
    return issues


def determine_overall_status(rules_gate: dict[str, Any], issue_list: list[dict[str, Any]]) -> Status:
    if rules_gate.get("status") == "fail" or any(issue.get("severity") == "fail" for issue in issue_list):
        return "fail"
    if rules_gate.get("status") == "skipped" or any(issue.get("severity") == "warn" for issue in issue_list):
        return "warn"
    return "pass"


def build_report_payload(
    *,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    batch_size: int,
    execution_mode: str,
    worker_count: int,
    total_runs: int,
    elapsed_seconds: float,
    rules_gate: dict[str, Any],
    replay_rows: list[dict[str, Any]],
    batch_rows: list[dict[str, Any]],
    feature_evidence: list[dict[str, Any]],
    issue_list: list[dict[str, Any]],
) -> dict[str, Any]:
    overall_status = determine_overall_status(rules_gate, issue_list)
    return {
        "overallStatus": overall_status,
        "generatedContext": collect_git_context(REPO_ROOT),
        "playerPresetId": player_preset_id,
        "scenarioIds": list(scenario_ids),
        "batchSize": batch_size,
        "executionMode": execution_mode,
        "workerCount": worker_count,
        "totalRuns": total_runs,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "rulesGate": rules_gate,
        "replayRows": replay_rows,
        "batchRows": batch_rows,
        "featureEvidence": feature_evidence,
        "issueList": issue_list,
    }


def format_rate(value: object) -> str:
    if isinstance(value, int | float):
        return f"{float(value) * 100:.1f}%"
    return "-"


def format_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Party Validation",
        "",
        f"- overallStatus: `{payload['overallStatus']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- batchSize: `{payload['batchSize']}`",
        f"- executionMode: `{payload['executionMode']}`",
        f"- workerCount: `{payload['workerCount']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
        "## Rules Gate",
        "",
        f"- status: `{payload['rulesGate']['status']}`",
        f"- command: `{payload['rulesGate'].get('command', '')}`",
        "",
        "## Replay Smoke",
        "",
        "| scenarioId | winner | rounds | events | status |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in payload["replayRows"]:
        lines.append(
            f"| `{row['scenarioId']}` | `{row['winner']}` | {row['rounds']} | "
            f"{row['eventCount']} | `{row['status']}` |"
        )

    lines.extend(
        [
            "",
            "## Batch Health",
            "",
            "| scenarioId | playerWinRate | enemyWinRate | smart | dumb | avgRounds | elapsedSeconds | status |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["batchRows"]:
        lines.append(
            f"| `{row['scenarioId']}` | {format_rate(row['playerWinRate'])} | "
            f"{format_rate(row['enemyWinRate'])} | {format_rate(row['smartPlayerWinRate'])} | "
            f"{format_rate(row['dumbPlayerWinRate'])} | {row['averageRounds']} | "
            f"{row['elapsedSeconds']} | `{row['status']}` |"
        )

    lines.extend(
        [
            "",
            "## Feature Evidence",
            "",
            "| unitId | classId | loadoutId | signature | matched | observed | events | status |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in payload["featureEvidence"]:
        matched = ", ".join(row.get("matchedPatterns") or ["none"])
        lines.append(
            f"| `{row['unitId']}` | `{row['classId']}` | `{row['loadoutId']}` | "
            f"`{row['signature']}` | `{matched}` | `{row['observed']}` | {row['eventCount']} | `{row['status']}` |"
        )

    lines.extend(["", "## Issues", ""])
    if payload["issueList"]:
        for issue in payload["issueList"]:
            location = issue.get("scenarioId") or issue.get("unitId") or issue.get("section")
            lines.append(f"- `{issue['severity']}` `{location}`: {issue['message']}")
    else:
        lines.append("- none")

    return "\n".join(lines)


def format_console_summary(payload: dict[str, Any]) -> str:
    batch_rows = payload.get("batchRows", [])
    if not batch_rows:
        return "Batch summary: no completed batch rows."

    player_behavior = batch_rows[0]["playerBehavior"]
    monster_behavior = batch_rows[0]["monsterBehavior"]
    lines = [
        "Batch summary:",
        f"- playerPresetId: {payload['playerPresetId']}",
        f"- playerBehavior: {player_behavior}",
        f"- monsterBehavior: {monster_behavior}",
        f"- batchSizePerScenario: {payload['batchSize']}",
        f"- scenarioCount: {len(payload['scenarioIds'])}",
    ]

    for row in batch_rows:
        lines.append(
            f"- {row['scenarioId']}: "
            f"players {format_rate(row['playerWinRate'])}, "
            f"enemies {format_rate(row['enemyWinRate'])}, "
            f"smart {format_rate(row['smartPlayerWinRate'])}, "
            f"dumb {format_rate(row['dumbPlayerWinRate'])}, "
            f"avg rounds {row['averageRounds']}, "
            f"avg party dead {row['averagePartyDead']}"
        )
        for breakdown in row.get("behaviorBreakdown", []):
            lines.append(
                f"  {breakdown['monsterBehavior']}: "
                f"smart {format_rate(breakdown['smartPlayerWinRate'])}, "
                f"dumb {format_rate(breakdown['dumbPlayerWinRate'])}, "
                f"players {format_rate(breakdown['playerWinRate'])}, "
                f"enemies {format_rate(breakdown['enemyWinRate'])}, "
                f"avg rounds {breakdown['averageRounds']}, "
                f"avg party dead {breakdown['averagePartyDead']}"
            )

    return "\n".join(lines)


def validate_scenarios(scenario_ids: tuple[str, ...]) -> None:
    for scenario_id in scenario_ids:
        get_scenario_definition(scenario_id)


def main() -> None:
    args = parse_args()
    scenario_ids = tuple(args.scenario_ids) if args.scenario_ids else DEFAULT_SCENARIO_IDS
    validate_scenarios(scenario_ids)
    total_runs = args.batch_size * len(scenario_ids)
    execution_plan = resolve_batch_execution_plan(
        args.batch_size,
        force_serial=args.serial,
        worker_count=args.workers,
    )

    print(
        f"Running party validation for {args.player_preset} across {len(scenario_ids)} scenario(s): "
        f"{', '.join(scenario_ids)}"
    )

    rules_gate = {"status": "skipped", "command": "", "exitCode": 0, "stdoutTail": []}
    if not args.skip_rules_gate:
        print("Running targeted party rules smoke...")
        rules_gate = run_rules_gate()
        print(f"Rules gate: {rules_gate['status']}")

    replay_rows, replay_results, replay_issues = run_replay_smoke(
        args.player_preset,
        scenario_ids,
        args.player_behavior,
        DEFAULT_REPLAY_SMOKE_RUNS,
    )
    batch_rows, batch_issues, batch_elapsed_seconds = run_batch_health(
        args.player_preset,
        scenario_ids,
        args.batch_size,
        args.player_behavior,
        args.monster_behavior,
        args.serial,
        args.workers,
    )
    feature_evidence = build_feature_evidence(replay_results)
    issue_list = [*replay_issues, *batch_issues, *collect_feature_issues(feature_evidence)]

    payload = build_report_payload(
        player_preset_id=args.player_preset,
        scenario_ids=scenario_ids,
        batch_size=args.batch_size,
        execution_mode=execution_plan.execution_mode,
        worker_count=execution_plan.worker_count,
        total_runs=total_runs,
        elapsed_seconds=batch_elapsed_seconds,
        rules_gate=rules_gate,
        replay_rows=replay_rows,
        batch_rows=batch_rows,
        feature_evidence=feature_evidence,
        issue_list=issue_list,
    )
    markdown_report = format_markdown_report(payload)
    console_summary = format_console_summary(payload)
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, markdown_report)
    print(console_summary)
    print(f"Wrote JSON report: {args.json_path}")
    print(f"Wrote Markdown report: {args.markdown_path}")
    print(f"Overall status: {payload['overallStatus']}")
    if args.json:
        import json

        print(json.dumps(payload, indent=2))

    if payload["overallStatus"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
