from __future__ import annotations

from backend.engine.models.state import GridPosition

DEFAULT_SEED = "fighter-vs-goblins-001"
DEFAULT_BATCH_SIZE = 100
BATCH_HISTORY_THRESHOLD = 10
PARALLEL_BATCH_MIN_TOTAL_RUNS = 60
MAX_PARALLEL_BATCH_WORKERS = 8
MAX_BATCH_SIZE = 1000
DEFAULT_PLAYER_BEHAVIOR = "smart"
DEFAULT_BATCH_PLAYER_BEHAVIOR = "balanced"
DEFAULT_MONSTER_BEHAVIOR = "balanced"
DEFAULT_BATCH_MONSTER_BEHAVIOR = "combined"
TOTAL_FIGHTER_MAX_HP = 66
TOTAL_GOBLIN_MAX_HP = 70

FIGHTER_IDS = ("F1", "F2", "F3", "F4")
GOBLIN_IDS = ("G1", "G2", "G3", "G4", "G5", "G6", "G7")
UNIT_IDS = (*FIGHTER_IDS, *GOBLIN_IDS)
MELEE_GOBLIN_IDS = ("G1", "G2", "G3", "G4")
ARCHER_GOBLIN_IDS = ("G5", "G6", "G7")
MONSTER_BEHAVIORS = ("kind", "balanced", "evil")

DEFAULT_POSITIONS: dict[str, GridPosition] = {
    "F1": GridPosition(x=1, y=7),
    "F2": GridPosition(x=1, y=8),
    "F3": GridPosition(x=1, y=9),
    "F4": GridPosition(x=1, y=10),
    "G1": GridPosition(x=14, y=6),
    "G2": GridPosition(x=14, y=7),
    "G3": GridPosition(x=14, y=8),
    "G4": GridPosition(x=14, y=9),
    "G5": GridPosition(x=15, y=5),
    "G6": GridPosition(x=15, y=8),
    "G7": GridPosition(x=15, y=11),
}
