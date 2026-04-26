from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.player_loadouts import DEFAULT_PLAYER_PRESET_ID
from backend.content.scenario_definitions import get_scenario_definition
from backend.engine import run_encounter
from backend.engine.models.state import EncounterConfig, RunEncounterResult
from scripts.audit_common import collect_git_context, write_json_report, write_text_report
from scripts.run_party_validation import DEFAULT_SCENARIO_IDS

DEFAULT_PROFILE = "paladin"
DEFAULT_UNIT_ID = "F2"
DEFAULT_RUNS_PER_SCENARIO = 60
DEFAULT_PLAYER_BEHAVIOR = "smart"
DEFAULT_MONSTER_BEHAVIOR = "balanced"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pc_tuning"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "pc_tuning_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "pc_tuning_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run event-level PC tuning samples for the current party.")
    parser.add_argument("--profile", choices=("paladin",), default=DEFAULT_PROFILE, help="PC tuning profile to run.")
    parser.add_argument("--unit", default=DEFAULT_UNIT_ID, help="Unit id to analyze. Paladin profile defaults to F2.")
    parser.add_argument("--player-preset", default=DEFAULT_PLAYER_PRESET_ID, help="Player preset id to validate.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        help="Scenario id to sample. Repeat to include more. Defaults to the standard party-validation set.",
    )
    parser.add_argument(
        "--runs-per-scenario",
        type=int,
        default=DEFAULT_RUNS_PER_SCENARIO,
        help="Deterministic event-level replays per scenario.",
    )
    parser.add_argument(
        "--player-behavior",
        choices=("smart", "dumb"),
        default=DEFAULT_PLAYER_BEHAVIOR,
        help="Player behavior to sample.",
    )
    parser.add_argument(
        "--monster-behavior",
        choices=("kind", "balanced", "evil"),
        default=DEFAULT_MONSTER_BEHAVIOR,
        help="Monster behavior to sample.",
    )
    parser.add_argument("--json", action="store_true", help="Print the final JSON payload to stdout.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH, help="Write the JSON report here.")
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH, help="Write the Markdown report here.")
    return parser.parse_args()


def validate_scenarios(scenario_ids: tuple[str, ...]) -> None:
    for scenario_id in scenario_ids:
        get_scenario_definition(scenario_id)


def percent(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 1) if denominator else 0.0


def average(values: list[int | float]) -> float:
    return round(mean(values), 2) if values else 0.0


def distribution(values: list[int]) -> dict[str, int]:
    return {str(value): count for value, count in sorted(Counter(values).items())}


def new_metrics() -> dict[str, Any]:
    return {
        "runs": 0,
        "wins": Counter(),
        "rounds": [],
        "endingSpellSlots": [],
        "endingSpellSlotsLevel1": [],
        "endingSpellSlotsLevel2": [],
        "endingLayOnHands": [],
        "paladinDownAtEnd": 0,
        "paladinEvents": 0,
        "blessCasts": 0,
        "divineSmites": 0,
        "sentinelGuardianTriggers": 0,
        "sentinelHaltApplied": 0,
        "naturesWrathUses": 0,
        "naturesWrathTargets": [],
        "naturesWrathRestrained": [],
        "layOnHandsUses": 0,
        "layOnHandsTotalHealing": 0,
        "layOnHandsHeals": [],
        "layOnHandsDownedPickups": 0,
        "cureWoundsUses": 0,
        "cureWoundsTotalHealing": 0,
        "cureWoundsHeals": [],
        "cureWoundsDownedPickups": 0,
    }


def add_metric(counter: dict[str, Any], key: str, value: int = 1) -> None:
    counter[key] = int(counter.get(key, 0)) + value


def record_paladin_run(metrics: dict[str, Any], result: RunEncounterResult, unit_id: str) -> None:
    final_state = result.final_state
    paladin = final_state.units[unit_id]
    metrics["runs"] += 1
    metrics["wins"][final_state.winner] += 1
    metrics["rounds"].append(final_state.round)
    ending_level_1_slots = paladin.resources.spell_slots_level_1
    ending_level_2_slots = paladin.resources.spell_slots_level_2
    metrics["endingSpellSlots"].append(ending_level_1_slots + ending_level_2_slots)
    metrics["endingSpellSlotsLevel1"].append(ending_level_1_slots)
    metrics["endingSpellSlotsLevel2"].append(ending_level_2_slots)
    metrics["endingLayOnHands"].append(paladin.resources.lay_on_hands_points)
    if paladin.current_hp <= 0 or paladin.conditions.dead or paladin.conditions.unconscious:
        add_metric(metrics, "paladinDownAtEnd")

    previous_unconscious: dict[str, bool] = {}
    if result.replay_frames:
        for current_unit_id, unit in result.replay_frames[0].state.units.items():
            previous_unconscious[current_unit_id] = unit.conditions.unconscious or unit.current_hp <= 0

    for frame in result.replay_frames[1:]:
        for event in frame.events:
            resolved_totals = event.resolved_totals or {}
            text = (event.text_summary or "").lower()
            is_actor = event.actor_id == unit_id
            is_reaction = (
                resolved_totals.get("reactionActorId") == unit_id
                or resolved_totals.get("defenseReactionActorId") == unit_id
            )
            if not (is_actor or is_reaction):
                continue

            add_metric(metrics, "paladinEvents")
            if resolved_totals.get("spellId") == "bless" or "casts bless" in text:
                add_metric(metrics, "blessCasts")
            if resolved_totals.get("divineSmiteApplied") is True:
                add_metric(metrics, "divineSmites")
            if resolved_totals.get("reaction") == "sentinel_guardian":
                add_metric(metrics, "sentinelGuardianTriggers")
            if resolved_totals.get("sentinelHaltApplied") is True:
                add_metric(metrics, "sentinelHaltApplied")
            if resolved_totals.get("specialAction") == "natures_wrath":
                add_metric(metrics, "naturesWrathUses")
                metrics["naturesWrathTargets"].append(len(resolved_totals.get("affectedTargetIds") or []))
                metrics["naturesWrathRestrained"].append(len(resolved_totals.get("restrainedTargetIds") or []))

            if event.event_type != "heal" or not is_actor:
                continue

            healing_total = int(resolved_totals.get("healingTotal") or 0)
            target_id = event.target_ids[0] if event.target_ids else None
            was_down = bool(target_id and previous_unconscious.get(target_id))
            is_lay_on_hands = "lay on hands" in text or "layOnHandsPointsRemaining" in resolved_totals
            is_cure_wounds = resolved_totals.get("spellId") == "cure_wounds" or "cure wounds" in text

            if is_lay_on_hands:
                add_metric(metrics, "layOnHandsUses")
                add_metric(metrics, "layOnHandsTotalHealing", healing_total)
                metrics["layOnHandsHeals"].append(healing_total)
                if was_down:
                    add_metric(metrics, "layOnHandsDownedPickups")
            elif is_cure_wounds:
                add_metric(metrics, "cureWoundsUses")
                add_metric(metrics, "cureWoundsTotalHealing", healing_total)
                metrics["cureWoundsHeals"].append(healing_total)
                if was_down:
                    add_metric(metrics, "cureWoundsDownedPickups")

        for current_unit_id, unit in frame.state.units.items():
            previous_unconscious[current_unit_id] = unit.conditions.unconscious or unit.current_hp <= 0


def summarize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    runs = int(metrics["runs"])
    ending_slots = list(metrics["endingSpellSlots"])
    ending_level_1_slots = list(metrics["endingSpellSlotsLevel1"])
    ending_level_2_slots = list(metrics["endingSpellSlotsLevel2"])
    ending_lay_on_hands = list(metrics["endingLayOnHands"])
    natures_wrath_targets = list(metrics["naturesWrathTargets"])
    natures_wrath_restrained = list(metrics["naturesWrathRestrained"])
    lay_on_hands_heals = list(metrics["layOnHandsHeals"])
    cure_wounds_heals = list(metrics["cureWoundsHeals"])

    return {
        "runs": runs,
        "wins": dict(metrics["wins"]),
        "playerWinRate": percent(metrics["wins"].get("fighters", 0), runs),
        "enemyWinRate": percent(metrics["wins"].get("goblins", 0), runs),
        "averageRounds": average(metrics["rounds"]),
        "endingSpellSlotsDistribution": distribution(ending_slots),
        "endingSpellSlotsLevel1Distribution": distribution(ending_level_1_slots),
        "endingSpellSlotsLevel2Distribution": distribution(ending_level_2_slots),
        "runsWithUnusedSpellSlots": sum(value > 0 for value in ending_slots),
        "runsWithUnusedSpellSlotsRate": percent(sum(value > 0 for value in ending_slots), runs),
        "averageEndingSpellSlots": average(ending_slots),
        "averageEndingSpellSlotsLevel1": average(ending_level_1_slots),
        "averageEndingSpellSlotsLevel2": average(ending_level_2_slots),
        "endingLayOnHandsDistribution": distribution(ending_lay_on_hands),
        "runsWithUnusedLayOnHands": sum(value > 0 for value in ending_lay_on_hands),
        "runsWithUnusedLayOnHandsRate": percent(sum(value > 0 for value in ending_lay_on_hands), runs),
        "averageEndingLayOnHands": average(ending_lay_on_hands),
        "paladinDownAtEnd": metrics["paladinDownAtEnd"],
        "paladinDownAtEndRate": percent(metrics["paladinDownAtEnd"], runs),
        "paladinEvents": metrics["paladinEvents"],
        "blessCasts": metrics["blessCasts"],
        "divineSmites": metrics["divineSmites"],
        "sentinelGuardianTriggers": metrics["sentinelGuardianTriggers"],
        "sentinelHaltApplied": metrics["sentinelHaltApplied"],
        "sentinelHaltPerGuardianRate": percent(
            metrics["sentinelHaltApplied"],
            metrics["sentinelGuardianTriggers"],
        ),
        "naturesWrathUses": metrics["naturesWrathUses"],
        "naturesWrathUseRate": percent(metrics["naturesWrathUses"], runs),
        "naturesWrathAverageTargets": average(natures_wrath_targets),
        "naturesWrathAverageRestrained": average(natures_wrath_restrained),
        "naturesWrathRestrainedTargetRate": percent(sum(natures_wrath_restrained), sum(natures_wrath_targets)),
        "naturesWrathTargetDistribution": distribution(natures_wrath_targets),
        "naturesWrathRestrainedDistribution": distribution(natures_wrath_restrained),
        "layOnHandsUses": metrics["layOnHandsUses"],
        "layOnHandsTotalHealing": metrics["layOnHandsTotalHealing"],
        "layOnHandsAverageHeal": average(lay_on_hands_heals),
        "layOnHandsDownedPickups": metrics["layOnHandsDownedPickups"],
        "layOnHandsHealDistribution": distribution(lay_on_hands_heals),
        "cureWoundsUses": metrics["cureWoundsUses"],
        "cureWoundsTotalHealing": metrics["cureWoundsTotalHealing"],
        "cureWoundsAverageHeal": average(cure_wounds_heals),
        "cureWoundsDownedPickups": metrics["cureWoundsDownedPickups"],
        "cureWoundsHealDistribution": distribution(cure_wounds_heals),
    }


def run_paladin_sample(
    *,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overall_metrics = new_metrics()
    scenario_rows: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        scenario_metrics = new_metrics()
        print(f"[{scenario_id}] {runs_per_scenario} event-level replay(s)")
        for run_index in range(runs_per_scenario):
            seed = f"pc-tuning-{unit_id}-{scenario_id}-{run_index:03d}"
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=monster_behavior,
                )
            )
            unit = result.final_state.units.get(unit_id)
            if not unit:
                raise ValueError(f"Unit `{unit_id}` is not present in final encounter state.")
            if unit.class_id != "paladin":
                raise ValueError(f"Paladin tuning profile requires a paladin unit; `{unit_id}` is `{unit.class_id}`.")

            record_paladin_run(overall_metrics, result, unit_id)
            record_paladin_run(scenario_metrics, result, unit_id)

        scenario_summary = summarize_metrics(scenario_metrics)
        scenario_summary["scenarioId"] = scenario_id
        scenario_rows.append(scenario_summary)

    return summarize_metrics(overall_metrics), scenario_rows


def build_report_payload(
    *,
    profile: str,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
    elapsed_seconds: float,
    overall: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "profile": profile,
        "unitId": unit_id,
        "playerPresetId": player_preset_id,
        "scenarioIds": list(scenario_ids),
        "runsPerScenario": runs_per_scenario,
        "totalRuns": runs_per_scenario * len(scenario_ids),
        "playerBehavior": player_behavior,
        "monsterBehavior": monster_behavior,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "generatedContext": collect_git_context(REPO_ROOT),
        "overall": overall,
        "scenarios": scenarios,
    }


def format_console_summary(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        (
            f"- overall: players {overall['playerWinRate']}%, enemies {overall['enemyWinRate']}%, "
            f"avg rounds {overall['averageRounds']}"
        ),
        (
            f"- resources: avg ending slots {overall['averageEndingSpellSlots']}, "
            f"L1 {overall['averageEndingSpellSlotsLevel1']}, L2 {overall['averageEndingSpellSlotsLevel2']}; "
            f"unused slots {overall['runsWithUnusedSpellSlots']}/{overall['runs']}; "
            f"avg ending Lay on Hands {overall['averageEndingLayOnHands']}, "
            f"unused Lay on Hands {overall['runsWithUnusedLayOnHands']}/{overall['runs']}"
        ),
        (
            f"- healing: Lay on Hands {overall['layOnHandsUses']} use(s), "
            f"{overall['layOnHandsTotalHealing']} HP, {overall['layOnHandsDownedPickups']} downed pickup(s); "
            f"Cure Wounds {overall['cureWoundsUses']} use(s), {overall['cureWoundsTotalHealing']} HP"
        ),
        (
            f"- features: Divine Smite {overall['divineSmites']}, "
            f"Sentinel Guardian {overall['sentinelGuardianTriggers']}, "
            f"Sentinel Halt {overall['sentinelHaltApplied']}, "
            f"Nature's Wrath {overall['naturesWrathUses']} use(s), "
            f"avg restrained {overall['naturesWrathAverageRestrained']}"
        ),
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"- {row['scenarioId']}: players {row['playerWinRate']}%, "
            f"Smite {row['divineSmites']}, LoH {row['layOnHandsUses']}, "
            f"Nature {row['naturesWrathUses']}, Sentinel {row['sentinelGuardianTriggers']}"
        )
    return "\n".join(lines)


def format_markdown_report(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# PC Tuning Sample",
        "",
        f"- profile: `{payload['profile']}`",
        f"- unitId: `{payload['unitId']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- runsPerScenario: `{payload['runsPerScenario']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        f"- playerBehavior: `{payload['playerBehavior']}`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Player win rate | {overall['playerWinRate']}% |",
        f"| Average rounds | {overall['averageRounds']} |",
        f"| Average ending spell slots | {overall['averageEndingSpellSlots']} |",
        f"| Average ending 1st-level slots | {overall['averageEndingSpellSlotsLevel1']} |",
        f"| Average ending 2nd-level slots | {overall['averageEndingSpellSlotsLevel2']} |",
        f"| Runs with unused spell slots | {overall['runsWithUnusedSpellSlots']} |",
        f"| Average ending Lay on Hands | {overall['averageEndingLayOnHands']} |",
        f"| Runs with unused Lay on Hands | {overall['runsWithUnusedLayOnHands']} |",
        f"| Lay on Hands uses | {overall['layOnHandsUses']} |",
        f"| Lay on Hands total healing | {overall['layOnHandsTotalHealing']} |",
        f"| Lay on Hands downed pickups | {overall['layOnHandsDownedPickups']} |",
        f"| Cure Wounds uses | {overall['cureWoundsUses']} |",
        f"| Cure Wounds total healing | {overall['cureWoundsTotalHealing']} |",
        f"| Divine Smites | {overall['divineSmites']} |",
        f"| Sentinel Guardian triggers | {overall['sentinelGuardianTriggers']} |",
        f"| Sentinel Halt applied | {overall['sentinelHaltApplied']} |",
        f"| Nature's Wrath uses | {overall['naturesWrathUses']} |",
        f"| Nature's Wrath average targets | {overall['naturesWrathAverageTargets']} |",
        f"| Nature's Wrath average restrained | {overall['naturesWrathAverageRestrained']} |",
        "",
        "## Scenarios",
        "",
        "| Scenario | Win Rate | Avg Rounds | Smite | LoH Uses | Cure | Nature | Avg Restrained | Sentinel | Halt |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"| `{row['scenarioId']}` | {row['playerWinRate']}% | {row['averageRounds']} | "
            f"{row['divineSmites']} | {row['layOnHandsUses']} | {row['cureWoundsUses']} | "
            f"{row['naturesWrathUses']} | {row['naturesWrathAverageRestrained']} | "
            f"{row['sentinelGuardianTriggers']} | {row['sentinelHaltApplied']} |"
        )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    scenario_ids = tuple(args.scenario_ids) if args.scenario_ids else DEFAULT_SCENARIO_IDS
    if args.runs_per_scenario <= 0:
        raise ValueError("--runs-per-scenario must be positive.")
    validate_scenarios(scenario_ids)

    started = time.perf_counter()
    overall, scenarios = run_paladin_sample(
        unit_id=args.unit,
        player_preset_id=args.player_preset,
        scenario_ids=scenario_ids,
        runs_per_scenario=args.runs_per_scenario,
        player_behavior=args.player_behavior,
        monster_behavior=args.monster_behavior,
    )
    elapsed = time.perf_counter() - started
    payload = build_report_payload(
        profile=args.profile,
        unit_id=args.unit,
        player_preset_id=args.player_preset,
        scenario_ids=scenario_ids,
        runs_per_scenario=args.runs_per_scenario,
        player_behavior=args.player_behavior,
        monster_behavior=args.monster_behavior,
        elapsed_seconds=elapsed,
        overall=overall,
        scenarios=scenarios,
    )
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, format_markdown_report(payload))
    print(format_console_summary(payload))
    print(f"Wrote JSON report: {args.json_path}")
    print(f"Wrote Markdown report: {args.markdown_path}")
    if args.json:
        import json

        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
