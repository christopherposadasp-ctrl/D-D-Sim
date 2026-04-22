from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine import run_batch
from backend.engine.models.state import EncounterConfig

DEFAULT_SCENARIOS = ("goblin_screen", "orc_push", "marsh_predators")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze a reproducible batch baseline for a small scenario set."
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        help="Scenario id to include. Repeat to run more than one.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Combined batch size to run for each scenario.",
    )
    parser.add_argument(
        "--seed-prefix",
        default="baseline",
        help="Prefix used when building per-scenario seeds.",
    )
    parser.add_argument(
        "--player-preset-id",
        default="martial_mixed_party",
        help="Player preset used for every scenario.",
    )
    parser.add_argument(
        "--player-behavior",
        default="balanced",
        choices=("smart", "dumb", "balanced"),
        help="Player behavior used for every scenario.",
    )
    parser.add_argument(
        "--monster-behavior",
        default="combined",
        choices=("kind", "balanced", "evil", "combined"),
        help="Monster behavior used for every scenario.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "baselines" / "baseline_report_latest.json",
        help="Output path for the frozen report.",
    )
    return parser.parse_args()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def build_config(args: argparse.Namespace, scenario_id: str) -> EncounterConfig:
    return EncounterConfig(
        seed=f"{args.seed_prefix}-{scenario_id}",
        batch_size=args.batch_size,
        player_behavior=args.player_behavior,
        monster_behavior=args.monster_behavior,
        enemy_preset_id=scenario_id,
        player_preset_id=args.player_preset_id,
    )


def main() -> None:
    args = parse_args()
    scenario_ids = tuple(args.scenario_ids or DEFAULT_SCENARIOS)
    results: list[dict[str, object]] = []

    for scenario_id in scenario_ids:
        print(f"Running {scenario_id}...", flush=True)
        started_at = time.perf_counter()
        summary = run_batch(build_config(args, scenario_id))
        elapsed_seconds = time.perf_counter() - started_at

        payload = summary.model_dump(mode="json", by_alias=True)
        payload["scenarioId"] = scenario_id
        payload["elapsedSeconds"] = round(elapsed_seconds, 3)
        results.append(payload)

        print(
            f"{scenario_id}: {elapsed_seconds:.2f}s, "
            f"players {payload['playerWinRate']:.3f}, enemies {payload['goblinWinRate']:.3f}"
        )

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "purpose": "Frozen batch baseline for current simulator behavior.",
        "config": {
            "playerPresetId": args.player_preset_id,
            "playerBehavior": args.player_behavior,
            "monsterBehavior": args.monster_behavior,
            "batchSize": args.batch_size,
            "scenarioIds": list(scenario_ids),
        },
        "git": {
            "branch": git_output("rev-parse", "--abbrev-ref", "HEAD"),
            "commit": git_output("rev-parse", "HEAD"),
            "shortStatus": git_output("status", "--short"),
        },
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
