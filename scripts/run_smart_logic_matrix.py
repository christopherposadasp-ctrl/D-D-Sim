from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.player_loadouts import DEFAULT_PLAYER_PRESET_ID
from backend.content.scenario_definitions import get_scenario_definition
from backend.engine import run_batch
from backend.engine.combat.batch import resolve_batch_execution_plan
from backend.engine.models.state import BatchSummary, EncounterConfig, MonsterBehaviorSelection, PlayerBehavior
from scripts.audit_common import collect_git_context, write_json_report, write_text_report
from scripts.run_party_validation import build_batch_run_plan, combine_batch_summaries, format_rate

DEFAULT_SCENARIO_IDS = (
    "hobgoblin_kill_box",
    "bugbear_dragnet",
    "deadwatch_phalanx",
    "reaction_bastion",
    "skyhunter_pincer",
    "hobgoblin_command_screen",
    "berserker_overrun",
)
DEFAULT_BATCH_SIZE = 1000
DEFAULT_PLAYER_BEHAVIOR: PlayerBehavior = "balanced"
DEFAULT_MONSTER_BEHAVIOR: MonsterBehaviorSelection = "combined"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "smart_logic_matrix"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "smart_logic_matrix_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "smart_logic_matrix_latest.md"
CURRENT_VARIANT_ID = "new_flanking_body_blocking_current"
REFERENCE_VARIANT_ID = "old_plain"
WIN_RATE_LOSS_TOLERANCE = 0.02
SMART_DELTA_WORSEN_TOLERANCE = 0.01


@dataclass(frozen=True)
class SmartLogicVariant:
    id: str
    smart_targeting_policy: str
    enable_end_turn_flanking: bool
    enable_frontline_body_blocking: bool


VARIANTS = (
    SmartLogicVariant("old_plain", "old", False, False),
    SmartLogicVariant("old_body_blocking", "old", False, True),
    SmartLogicVariant("old_flanking", "old", True, False),
    SmartLogicVariant("old_flanking_body_blocking", "old", True, True),
    SmartLogicVariant("new_plain", "new", False, False),
    SmartLogicVariant("new_body_blocking", "new", False, True),
    SmartLogicVariant("new_flanking", "new", True, False),
    SmartLogicVariant("new_flanking_body_blocking_current", "new", True, True),
)
VARIANT_BY_ID = {variant.id: variant for variant in VARIANTS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a smart-logic variant matrix against the hard party battery.")
    parser.add_argument("--player-preset", default=DEFAULT_PLAYER_PRESET_ID, help="Player preset id to validate.")
    parser.add_argument("--scenario", action="append", dest="scenario_ids", help="Scenario id to include.")
    parser.add_argument("--variant", action="append", dest="variant_ids", choices=tuple(VARIANT_BY_ID), help="Variant id to include.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Total batch encounters per scenario.")
    parser.add_argument(
        "--player-behavior",
        default=DEFAULT_PLAYER_BEHAVIOR,
        choices=("smart", "dumb", "balanced"),
        help="Player behavior for every variant.",
    )
    parser.add_argument(
        "--monster-behavior",
        default=DEFAULT_MONSTER_BEHAVIOR,
        choices=("kind", "balanced", "evil", "combined"),
        help="Monster behavior for every variant.",
    )
    parser.add_argument("--serial", action="store_true", help="Force serial batch execution.")
    parser.add_argument("--workers", type=int, default=None, help="Requested batch worker count, capped at 8.")
    parser.add_argument("--json", action="store_true", help="Print the final JSON payload to stdout.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH, help="Write the JSON report here.")
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH, help="Write the Markdown report here.")
    return parser.parse_args()


def validate_scenarios(scenario_ids: tuple[str, ...]) -> None:
    for scenario_id in scenario_ids:
        get_scenario_definition(scenario_id)


def paired_seed_for_scenario(scenario_id: str, monster_behavior: str) -> str:
    return f"smart-logic-matrix-{scenario_id}-{monster_behavior}"


def variant_config_kwargs(variant: SmartLogicVariant) -> dict[str, Any]:
    return {
        "smart_targeting_policy": variant.smart_targeting_policy,
        "enable_end_turn_flanking": variant.enable_end_turn_flanking,
        "enable_frontline_body_blocking": variant.enable_frontline_body_blocking,
    }


def summarize_variant_scenario(
    *,
    variant: SmartLogicVariant,
    scenario_id: str,
    summary: BatchSummary,
    elapsed_seconds: float,
    execution_mode: str,
    worker_count: int,
) -> dict[str, Any]:
    smart_win_rate = summary.smart_player_win_rate
    dumb_win_rate = summary.dumb_player_win_rate
    smart_dumb_delta = (
        round(float(smart_win_rate) - float(dumb_win_rate), 3)
        if smart_win_rate is not None and dumb_win_rate is not None
        else None
    )
    return {
        "variantId": variant.id,
        "scenarioId": scenario_id,
        "smartTargetingPolicy": variant.smart_targeting_policy,
        "enableEndTurnFlanking": variant.enable_end_turn_flanking,
        "enableFrontlineBodyBlocking": variant.enable_frontline_body_blocking,
        "batchSize": summary.batch_size,
        "totalRuns": summary.total_runs,
        "executionMode": execution_mode,
        "workerCount": worker_count,
        "playerWinRate": summary.player_win_rate,
        "enemyWinRate": summary.goblin_win_rate,
        "smartPlayerWinRate": smart_win_rate,
        "dumbPlayerWinRate": dumb_win_rate,
        "smartMinusDumbWinRate": smart_dumb_delta,
        "averageRounds": summary.average_rounds,
        "averagePartyDead": summary.average_fighter_deaths,
        "averageEnemiesKilled": summary.average_goblins_killed,
        "averageRemainingPartyHp": summary.average_remaining_fighter_hp,
        "averageRemainingEnemyHp": summary.average_remaining_goblin_hp,
        "elapsedSeconds": round(elapsed_seconds, 3),
    }


def weighted_average(rows: list[dict[str, Any]], field_name: str, weight_name: str = "totalRuns") -> float | None:
    weighted_rows = [(row.get(field_name), row.get(weight_name, 0)) for row in rows]
    total_weight = sum(weight for value, weight in weighted_rows if value is not None and weight)
    if total_weight <= 0:
        return None
    return round(sum(float(value) * weight for value, weight in weighted_rows if value is not None and weight) / total_weight, 3)


def build_aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregate_rows: list[dict[str, Any]] = []
    for variant in VARIANTS:
        variant_rows = [row for row in rows if row["variantId"] == variant.id]
        if not variant_rows:
            continue
        smart_win_rate = weighted_average(variant_rows, "smartPlayerWinRate", "totalRuns")
        dumb_win_rate = weighted_average(variant_rows, "dumbPlayerWinRate", "totalRuns")
        aggregate_rows.append(
            {
                "variantId": variant.id,
                "smartTargetingPolicy": variant.smart_targeting_policy,
                "enableEndTurnFlanking": variant.enable_end_turn_flanking,
                "enableFrontlineBodyBlocking": variant.enable_frontline_body_blocking,
                "scenarioCount": len(variant_rows),
                "totalRuns": sum(row["totalRuns"] for row in variant_rows),
                "playerWinRate": weighted_average(variant_rows, "playerWinRate"),
                "smartPlayerWinRate": smart_win_rate,
                "dumbPlayerWinRate": dumb_win_rate,
                "smartMinusDumbWinRate": (
                    round(float(smart_win_rate) - float(dumb_win_rate), 3)
                    if smart_win_rate is not None and dumb_win_rate is not None
                    else None
                ),
                "inversionCount": sum(
                    1
                    for row in variant_rows
                    if row["smartPlayerWinRate"] is not None
                    and row["dumbPlayerWinRate"] is not None
                    and row["smartPlayerWinRate"] < row["dumbPlayerWinRate"]
                ),
                "averageRounds": weighted_average(variant_rows, "averageRounds"),
                "averagePartyDead": weighted_average(variant_rows, "averagePartyDead"),
                "averageEnemiesKilled": weighted_average(variant_rows, "averageEnemiesKilled"),
                "averageRemainingPartyHp": weighted_average(variant_rows, "averageRemainingPartyHp"),
                "averageRemainingEnemyHp": weighted_average(variant_rows, "averageRemainingEnemyHp"),
            }
        )

    current = next((row for row in aggregate_rows if row["variantId"] == CURRENT_VARIANT_ID), None)
    reference = next((row for row in aggregate_rows if row["variantId"] == REFERENCE_VARIANT_ID), None)
    for row in aggregate_rows:
        row["playerWinRateDeltaVsCurrent"] = delta(row["playerWinRate"], current["playerWinRate"] if current else None)
        row["smartWinRateDeltaVsCurrent"] = delta(row["smartPlayerWinRate"], current["smartPlayerWinRate"] if current else None)
        row["dumbWinRateDeltaVsCurrent"] = delta(row["dumbPlayerWinRate"], current["dumbPlayerWinRate"] if current else None)
        row["playerWinRateDeltaVsOldPlain"] = delta(row["playerWinRate"], reference["playerWinRate"] if reference else None)
        row["smartWinRateDeltaVsOldPlain"] = delta(row["smartPlayerWinRate"], reference["smartPlayerWinRate"] if reference else None)
        row["dumbWinRateDeltaVsOldPlain"] = delta(row["dumbPlayerWinRate"], reference["dumbPlayerWinRate"] if reference else None)

    return aggregate_rows


def delta(value: int | float | None, baseline: int | float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return round(float(value) - float(baseline), 3)


def best_by(aggregate_rows: list[dict[str, Any]], field_name: str) -> dict[str, Any] | None:
    candidates = [row for row in aggregate_rows if row.get(field_name) is not None]
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (-float(row[field_name]), row["variantId"]))[0]


def metric_value(row: dict[str, Any], field_name: str, default: float = -9999.0) -> float:
    value = row.get(field_name)
    return float(value) if value is not None else default


def build_recommendations(aggregate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not aggregate_rows:
        return {}
    best_total = best_by(aggregate_rows, "playerWinRate")
    best_smart = best_by(aggregate_rows, "smartPlayerWinRate")
    best_delta = best_by(aggregate_rows, "smartMinusDumbWinRate")
    best_total_rate = float(best_total["playerWinRate"]) if best_total and best_total["playerWinRate"] is not None else 0.0
    eligible = [
        row
        for row in aggregate_rows
        if row["playerWinRate"] is not None
        and float(row["playerWinRate"]) >= best_total_rate - WIN_RATE_LOSS_TOLERANCE
    ]
    recommended = sorted(
        eligible or aggregate_rows,
        key=lambda row: (
            row["inversionCount"],
            -metric_value(row, "smartMinusDumbWinRate"),
            -metric_value(row, "smartPlayerWinRate"),
            -metric_value(row, "playerWinRate"),
            row["variantId"],
        ),
    )[0]
    current = next((row for row in aggregate_rows if row["variantId"] == CURRENT_VARIANT_ID), None)
    current_delta = metric_value(current, "smartMinusDumbWinRate", 0.0) if current else 0.0
    current_inversions = int(current["inversionCount"]) if current else 0
    reduce_inversion_without_large_loss = [
        row["variantId"]
        for row in aggregate_rows
        if row["inversionCount"] <= current_inversions
        and row["playerWinRate"] is not None
        and best_total_rate - float(row["playerWinRate"]) <= WIN_RATE_LOSS_TOLERANCE
    ]
    rejected = [
        row["variantId"]
        for row in aggregate_rows
        if row["inversionCount"] > current_inversions
        or metric_value(row, "smartMinusDumbWinRate") < current_delta - SMART_DELTA_WORSEN_TOLERANCE
    ]
    return {
        "bestByTotalPlayerWinRate": best_total["variantId"] if best_total else None,
        "bestBySmartWinRate": best_smart["variantId"] if best_smart else None,
        "bestBySmartMinusDumbDelta": best_delta["variantId"] if best_delta else None,
        "variantsReducingInversionWithoutLargeWinRateLoss": reduce_inversion_without_large_loss,
        "rejectedVariantIds": rejected,
        "recommendedDefaultForNextTuning": recommended["variantId"],
    }


def build_report_payload(
    *,
    scenario_ids: tuple[str, ...],
    selected_variant_ids: tuple[str, ...],
    batch_size: int,
    player_preset_id: str,
    player_behavior: str,
    monster_behavior: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    aggregate_rows = build_aggregate_rows(rows)
    return {
        "git": collect_git_context(),
        "playerPresetId": player_preset_id,
        "playerBehavior": player_behavior,
        "monsterBehavior": monster_behavior,
        "batchSizePerScenario": batch_size,
        "scenarioIds": list(scenario_ids),
        "variantIds": list(selected_variant_ids),
        "variants": [asdict(VARIANT_BY_ID[variant_id]) for variant_id in selected_variant_ids],
        "rows": rows,
        "aggregateRows": aggregate_rows,
        "recommendations": build_recommendations(aggregate_rows),
    }


def format_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Smart Logic Matrix",
        "",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- playerBehavior: `{payload['playerBehavior']}`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- batchSizePerScenario: `{payload['batchSizePerScenario']}`",
        "",
        "## Aggregate",
        "",
        "| variant | player | smart | dumb | smart-dumb | inversions | rounds | party dead |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["aggregateRows"]:
        lines.append(
            f"| `{row['variantId']}` | {format_rate(row['playerWinRate'])} | "
            f"{format_rate(row['smartPlayerWinRate'])} | {format_rate(row['dumbPlayerWinRate'])} | "
            f"{format_rate(row['smartMinusDumbWinRate'])} | {row['inversionCount']} | "
            f"{row['averageRounds']} | {row['averagePartyDead']} |"
        )

    lines.extend(
        [
            "",
            "## Scenario Rows",
            "",
            "| variant | scenario | player | smart | dumb | smart-dumb | rounds | party dead |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["rows"]:
        lines.append(
            f"| `{row['variantId']}` | `{row['scenarioId']}` | {format_rate(row['playerWinRate'])} | "
            f"{format_rate(row['smartPlayerWinRate'])} | {format_rate(row['dumbPlayerWinRate'])} | "
            f"{format_rate(row['smartMinusDumbWinRate'])} | {row['averageRounds']} | {row['averagePartyDead']} |"
        )

    lines.extend(["", "## Recommendations", ""])
    for key, value in payload["recommendations"].items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines)


def format_console_summary(payload: dict[str, Any]) -> str:
    lines = [
        "Smart logic matrix summary:",
        f"- playerPresetId: {payload['playerPresetId']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        f"- batchSizePerScenario: {payload['batchSizePerScenario']}",
        "- aggregates:",
    ]
    for row in payload["aggregateRows"]:
        lines.append(
            f"  - {row['variantId']}: players {format_rate(row['playerWinRate'])}, "
            f"smart {format_rate(row['smartPlayerWinRate'])}, dumb {format_rate(row['dumbPlayerWinRate'])}, "
            f"delta {format_rate(row['smartMinusDumbWinRate'])}, inversions {row['inversionCount']}"
        )
    recommendations = payload["recommendations"]
    lines.extend(
        [
            "Recommendations:",
            f"- best total win rate: {recommendations.get('bestByTotalPlayerWinRate')}",
            f"- best smart win rate: {recommendations.get('bestBySmartWinRate')}",
            f"- best smart-minus-dumb delta: {recommendations.get('bestBySmartMinusDumbDelta')}",
            f"- reduced inversion without large win-rate loss: {recommendations.get('variantsReducingInversionWithoutLargeWinRateLoss')}",
            f"- reject: {recommendations.get('rejectedVariantIds')}",
            f"- recommended next default: {recommendations.get('recommendedDefaultForNextTuning')}",
        ]
    )
    return "\n".join(lines)


def write_reports(payload: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    write_json_report(json_path, payload)
    write_text_report(markdown_path, format_markdown_report(payload))


def run_variant_scenario(
    *,
    variant: SmartLogicVariant,
    scenario_id: str,
    batch_size: int,
    player_preset_id: str,
    player_behavior: PlayerBehavior,
    monster_behavior: MonsterBehaviorSelection,
    force_serial: bool,
    worker_count: int | None,
) -> dict[str, Any]:
    batch_plan = build_batch_run_plan(batch_size, monster_behavior)
    total_runs = sum(run_count for _, run_count in batch_plan)
    execution_plan = resolve_batch_execution_plan(total_runs, force_serial=force_serial, worker_count=worker_count)
    print(
        f"[{variant.id} / {scenario_id}] batch health: {total_runs} run(s), "
        f"{execution_plan.execution_mode}, {execution_plan.worker_count} worker(s)"
    )
    start_time = time.perf_counter()
    summaries: list[BatchSummary] = []
    for sub_behavior, sub_batch_size in batch_plan:
        summaries.append(
            run_batch(
                EncounterConfig(
                    seed=paired_seed_for_scenario(scenario_id, sub_behavior),
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    batch_size=sub_batch_size,
                    player_behavior=player_behavior,
                    monster_behavior=sub_behavior,
                    **variant_config_kwargs(variant),
                ),
                force_serial=force_serial,
                worker_count=execution_plan.worker_count,
                capture_history=False,
            )
        )
    elapsed_seconds = time.perf_counter() - start_time
    summary = (
        combine_batch_summaries(
            paired_seed_for_scenario(scenario_id, "combined"),
            player_behavior,
            batch_size,
            summaries,
        )
        if monster_behavior == "combined"
        else summaries[0]
    )
    return summarize_variant_scenario(
        variant=variant,
        scenario_id=scenario_id,
        summary=summary,
        elapsed_seconds=elapsed_seconds,
        execution_mode=execution_plan.execution_mode,
        worker_count=execution_plan.worker_count,
    )


def main() -> None:
    args = parse_args()
    scenario_ids = tuple(args.scenario_ids) if args.scenario_ids else DEFAULT_SCENARIO_IDS
    selected_variant_ids = tuple(args.variant_ids) if args.variant_ids else tuple(variant.id for variant in VARIANTS)
    validate_scenarios(scenario_ids)

    rows: list[dict[str, Any]] = []
    print(
        f"Running smart logic matrix across {len(selected_variant_ids)} variant(s) and "
        f"{len(scenario_ids)} scenario(s)."
    )
    for variant_id in selected_variant_ids:
        variant = VARIANT_BY_ID[variant_id]
        for scenario_id in scenario_ids:
            rows.append(
                run_variant_scenario(
                    variant=variant,
                    scenario_id=scenario_id,
                    batch_size=args.batch_size,
                    player_preset_id=args.player_preset,
                    player_behavior=args.player_behavior,
                    monster_behavior=args.monster_behavior,
                    force_serial=args.serial,
                    worker_count=args.workers,
                )
            )
            payload = build_report_payload(
                scenario_ids=scenario_ids,
                selected_variant_ids=selected_variant_ids,
                batch_size=args.batch_size,
                player_preset_id=args.player_preset,
                player_behavior=args.player_behavior,
                monster_behavior=args.monster_behavior,
                rows=rows,
            )
            write_reports(payload, args.json_path, args.markdown_path)

    payload = build_report_payload(
        scenario_ids=scenario_ids,
        selected_variant_ids=selected_variant_ids,
        batch_size=args.batch_size,
        player_preset_id=args.player_preset,
        player_behavior=args.player_behavior,
        monster_behavior=args.monster_behavior,
        rows=rows,
    )
    write_reports(payload, args.json_path, args.markdown_path)
    print(format_console_summary(payload))
    print(f"Wrote JSON report: {args.json_path}")
    print(f"Wrote Markdown report: {args.markdown_path}")
    if args.json:
        import json

        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
