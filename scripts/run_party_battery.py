from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.enemies import ACTIVE_ENEMY_PRESET_IDS, get_enemy_preset
from backend.content.player_loadouts import DEFAULT_PLAYER_PRESET_ID
from backend.engine import run_batch
from backend.engine.models.state import EncounterConfig

BATCH_SIZE = 100
PLAYER_BEHAVIORS = ("smart", "dumb")
MONSTER_BEHAVIORS = ("kind", "balanced", "evil")
SEED_PREFIX = "party-battery-2026-04-21"


def main() -> None:
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    raw_path = report_dir / "standard_party_battery_2026-04-21.json"
    if raw_path.exists():
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        rows = list(payload.get("rows", []))
    else:
        rows = []

    completed_keys = {
        (str(row["scenarioId"]), str(row["playerBehavior"]), str(row["monsterBehavior"]))
        for row in rows
    }

    total_runs = len(ACTIVE_ENEMY_PRESET_IDS) * len(PLAYER_BEHAVIORS) * len(MONSTER_BEHAVIORS)
    started = perf_counter()
    completed_count = len(completed_keys)

    if completed_count:
        print(f"Resuming battery report with {completed_count}/{total_runs} combinations already complete.", flush=True)

    for scenario_id in ACTIVE_ENEMY_PRESET_IDS:
        scenario = get_enemy_preset(scenario_id)
        for player_behavior in PLAYER_BEHAVIORS:
            for monster_behavior in MONSTER_BEHAVIORS:
                key = (scenario_id, player_behavior, monster_behavior)
                if key in completed_keys:
                    continue

                completed_count += 1
                batch_seed = f"{SEED_PREFIX}-{scenario_id}-{player_behavior}-{monster_behavior}"
                batch_started = perf_counter()
                print(
                    f"[{completed_count}/{total_runs}] {scenario_id} | players={player_behavior} | dm={monster_behavior} | batch={BATCH_SIZE}",
                    flush=True,
                )
                summary = run_batch(
                    EncounterConfig(
                        seed=batch_seed,
                        enemy_preset_id=scenario_id,
                        player_preset_id=DEFAULT_PLAYER_PRESET_ID,
                        batch_size=BATCH_SIZE,
                        player_behavior=player_behavior,
                        monster_behavior=monster_behavior,
                    )
                )
                batch_elapsed = perf_counter() - batch_started
                row = {
                    "scenarioId": scenario_id,
                    "displayName": scenario.display_name,
                    "playerPresetId": DEFAULT_PLAYER_PRESET_ID,
                    "playerBehavior": player_behavior,
                    "monsterBehavior": monster_behavior,
                    "batchSize": BATCH_SIZE,
                    "playerWinRate": float(summary.player_win_rate),
                    "enemyWinRate": float(summary.goblin_win_rate),
                    "mutualAnnihilationRate": float(summary.mutual_annihilation_rate),
                    "averageRounds": float(summary.average_rounds),
                    "averageFighterDeaths": float(summary.average_fighter_deaths),
                    "averageGoblinsKilled": float(summary.average_goblins_killed),
                    "averageRemainingFighterHp": float(summary.average_remaining_fighter_hp),
                    "averageRemainingGoblinHp": float(summary.average_remaining_goblin_hp),
                    "stableButUnconsciousCount": int(summary.stable_but_unconscious_count),
                    "elapsedSeconds": batch_elapsed,
                }
                rows.append(row)
                completed_keys.add(key)
                raw_path.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
                print(
                    f"    players {row['playerWinRate'] * 100:.1f}% | enemies {row['enemyWinRate'] * 100:.1f}% | rounds {row['averageRounds']:.2f} | {batch_elapsed:.1f}s",
                    flush=True,
                )

    finished = perf_counter()
    payload = {
        "playerPresetId": DEFAULT_PLAYER_PRESET_ID,
        "batchSize": BATCH_SIZE,
        "scenarioIds": list(ACTIVE_ENEMY_PRESET_IDS),
        "playerBehaviors": list(PLAYER_BEHAVIORS),
        "monsterBehaviors": list(MONSTER_BEHAVIORS),
        "totalElapsedSeconds": finished - started,
        "rows": rows,
    }
    raw_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {raw_path}")
    print(f"Total elapsed: {finished - started:.1f}s")


if __name__ == "__main__":
    main()
