from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Literal

from backend.engine.combat.setup import clone_placements_for_unit_ids, resolve_placements, resolve_player_behavior
from backend.engine.constants import (
    BATCH_HISTORY_THRESHOLD,
    DEFAULT_BATCH_MONSTER_BEHAVIOR,
    DEFAULT_BATCH_PLAYER_BEHAVIOR,
    DEFAULT_BATCH_SIZE,
    DEFAULT_SEED,
    MAX_BATCH_SIZE,
    MAX_PARALLEL_BATCH_WORKERS,
    MONSTER_BEHAVIORS,
    PARALLEL_BATCH_MIN_TOTAL_RUNS,
)
from backend.engine.models.state import (
    BatchCombinationSummary,
    BatchSummary,
    EncounterConfig,
    EncounterSummary,
    GridPosition,
    MonsterBehavior,
    MonsterBehaviorSelection,
    PlayerBehavior,
    ResolvedPlayerBehavior,
)


@dataclass(frozen=True)
class BatchChunkTask:
    """Serializable unit of work for the process pool batch path."""

    seed: str
    placements: dict[str, tuple[int, int]]
    requested_player_behavior: PlayerBehavior
    requested_monster_behavior: MonsterBehavior
    enemy_preset_id: str | None
    player_preset_id: str | None
    smart_targeting_policy: str
    enable_end_turn_flanking: bool
    enable_frontline_body_blocking: bool
    start_index: int
    run_count: int
    preserve_history: bool


@dataclass(frozen=True)
class BatchChunkResult:
    monster_behavior: MonsterBehavior
    completed_runs: int
    accumulator: dict[str, float]


BatchExecutionMode = Literal["parallel", "serial"]
BATCH_WORKERS_ENV_VAR = "DND_SIM_BATCH_WORKERS"


@dataclass(frozen=True)
class BatchExecutionPlan:
    execution_mode: BatchExecutionMode
    worker_count: int
    total_runs: int


def create_empty_batch_accumulator() -> dict[str, float]:
    return {
        "fighter_wins": 0,
        "goblin_wins": 0,
        "mutual_annihilations": 0,
        "smart_player_wins": 0,
        "dumb_player_wins": 0,
        "smart_run_count": 0,
        "dumb_run_count": 0,
        "rounds_total": 0,
        "fighter_deaths_total": 0,
        "goblins_killed_total": 0,
        "remaining_fighter_hp_total": 0,
        "remaining_goblin_hp_total": 0,
        "stable_but_unconscious_count": 0,
        "total_runs": 0,
    }


def divide_number(total: float, count: float) -> int | float:
    value = total / count
    if float(value).is_integer():
        return int(value)
    return value


def merge_batch_accumulators(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    return {key: left[key] + right[key] for key in left}


def finalize_batch_summary(
    seed: str,
    player_behavior: PlayerBehavior,
    monster_behavior: MonsterBehaviorSelection,
    batch_size: int,
    accumulator: dict[str, float],
    combination_summaries: list[BatchCombinationSummary] | None,
) -> BatchSummary:
    total_runs = accumulator["total_runs"]
    return BatchSummary(
        seed=seed,
        player_behavior=player_behavior,
        monster_behavior=monster_behavior,
        batch_size=batch_size,
        total_runs=int(total_runs),
        player_win_rate=divide_number(accumulator["fighter_wins"], total_runs),
        goblin_win_rate=divide_number(accumulator["goblin_wins"], total_runs),
        mutual_annihilation_rate=divide_number(accumulator["mutual_annihilations"], total_runs),
        smart_player_win_rate=(
            divide_number(accumulator["smart_player_wins"], accumulator["smart_run_count"])
            if accumulator["smart_run_count"] > 0
            else None
        ),
        dumb_player_win_rate=(
            divide_number(accumulator["dumb_player_wins"], accumulator["dumb_run_count"])
            if accumulator["dumb_run_count"] > 0
            else None
        ),
        smart_run_count=int(accumulator["smart_run_count"]),
        dumb_run_count=int(accumulator["dumb_run_count"]),
        average_rounds=divide_number(accumulator["rounds_total"], total_runs),
        average_fighter_deaths=divide_number(accumulator["fighter_deaths_total"], total_runs),
        average_goblins_killed=divide_number(accumulator["goblins_killed_total"], total_runs),
        average_remaining_fighter_hp=divide_number(accumulator["remaining_fighter_hp_total"], total_runs),
        average_remaining_goblin_hp=divide_number(accumulator["remaining_goblin_hp_total"], total_runs),
        stable_but_unconscious_count=int(accumulator["stable_but_unconscious_count"]),
        combination_summaries=combination_summaries,
    )


def finalize_batch_combination_summary(
    seed: str,
    player_behavior: PlayerBehavior,
    monster_behavior: MonsterBehavior,
    batch_size: int,
    accumulator: dict[str, float],
) -> BatchCombinationSummary:
    total_runs = accumulator["total_runs"]
    return BatchCombinationSummary(
        seed=seed,
        player_behavior=player_behavior,
        monster_behavior=monster_behavior,
        batch_size=batch_size,
        total_runs=int(total_runs),
        player_win_rate=divide_number(accumulator["fighter_wins"], total_runs),
        goblin_win_rate=divide_number(accumulator["goblin_wins"], total_runs),
        mutual_annihilation_rate=divide_number(accumulator["mutual_annihilations"], total_runs),
        smart_player_win_rate=(
            divide_number(accumulator["smart_player_wins"], accumulator["smart_run_count"])
            if accumulator["smart_run_count"] > 0
            else None
        ),
        dumb_player_win_rate=(
            divide_number(accumulator["dumb_player_wins"], accumulator["dumb_run_count"])
            if accumulator["dumb_run_count"] > 0
            else None
        ),
        smart_run_count=int(accumulator["smart_run_count"]),
        dumb_run_count=int(accumulator["dumb_run_count"]),
        average_rounds=divide_number(accumulator["rounds_total"], total_runs),
        average_fighter_deaths=divide_number(accumulator["fighter_deaths_total"], total_runs),
        average_goblins_killed=divide_number(accumulator["goblins_killed_total"], total_runs),
        average_remaining_fighter_hp=divide_number(accumulator["remaining_fighter_hp_total"], total_runs),
        average_remaining_goblin_hp=divide_number(accumulator["remaining_goblin_hp_total"], total_runs),
        stable_but_unconscious_count=int(accumulator["stable_but_unconscious_count"]),
    )


def should_capture_batch_history(requested_size: int, capture_history: bool | None = None) -> bool:
    if capture_history is not None:
        return capture_history
    return requested_size <= BATCH_HISTORY_THRESHOLD


def serialize_placements(placements: dict[str, GridPosition]) -> dict[str, tuple[int, int]]:
    return {unit_id: (position.x, position.y) for unit_id, position in placements.items()}


def deserialize_placements(placements: dict[str, tuple[int, int]]) -> dict[str, GridPosition]:
    return {unit_id: GridPosition(x=x, y=y) for unit_id, (x, y) in placements.items()}


def build_batch_encounter_config(
    seed: str,
    placements: dict[str, GridPosition],
    requested_player_behavior: PlayerBehavior,
    requested_monster_behavior: MonsterBehavior,
    enemy_preset_id: str | None,
    player_preset_id: str | None,
    smart_targeting_policy: str,
    enable_end_turn_flanking: bool,
    enable_frontline_body_blocking: bool,
    run_index: int,
) -> tuple[EncounterConfig, ResolvedPlayerBehavior]:
    derived_seed = f"{(seed.strip() or DEFAULT_SEED)}#{run_index + 1}"
    resolved_behavior = resolve_player_behavior(requested_player_behavior, run_index)
    encounter_config = EncounterConfig(
        seed=derived_seed,
        placements=clone_placements_for_unit_ids(placements, placements.keys()),
        player_behavior=resolved_behavior,
        monster_behavior=requested_monster_behavior,
        enemy_preset_id=enemy_preset_id,
        player_preset_id=player_preset_id,
        smart_targeting_policy=smart_targeting_policy,
        enable_end_turn_flanking=enable_end_turn_flanking,
        enable_frontline_body_blocking=enable_frontline_body_blocking,
    )
    return encounter_config, resolved_behavior


def summarize_batch_run(
    seed: str,
    placements: dict[str, GridPosition],
    requested_player_behavior: PlayerBehavior,
    requested_monster_behavior: MonsterBehavior,
    enemy_preset_id: str | None,
    player_preset_id: str | None,
    smart_targeting_policy: str,
    enable_end_turn_flanking: bool,
    enable_frontline_body_blocking: bool,
    run_index: int,
    preserve_history: bool,
) -> tuple[EncounterSummary, ResolvedPlayerBehavior]:
    encounter_config, resolved_behavior = build_batch_encounter_config(
        seed,
        placements,
        requested_player_behavior,
        requested_monster_behavior,
        enemy_preset_id,
        player_preset_id,
        smart_targeting_policy,
        enable_end_turn_flanking,
        enable_frontline_body_blocking,
        run_index,
    )

    # Imported lazily to avoid a circular import between turn orchestration and
    # the batch executor.
    from backend.engine.combat.engine import run_encounter, run_encounter_summary_fast, summarize_encounter

    if preserve_history:
        result = run_encounter(encounter_config)
        summary = summarize_encounter(result.final_state)
    else:
        summary = run_encounter_summary_fast(encounter_config)

    return summary, resolved_behavior


def accumulate_batch_summary(
    accumulator: dict[str, float],
    summary: EncounterSummary,
    resolved_behavior: ResolvedPlayerBehavior,
) -> None:
    if summary.winner == "fighters":
        accumulator["fighter_wins"] += 1
        if resolved_behavior == "smart":
            accumulator["smart_player_wins"] += 1
        else:
            accumulator["dumb_player_wins"] += 1
    elif summary.winner == "goblins":
        accumulator["goblin_wins"] += 1
    elif summary.winner == "mutual_annihilation":
        accumulator["mutual_annihilations"] += 1

    if resolved_behavior == "smart":
        accumulator["smart_run_count"] += 1
    else:
        accumulator["dumb_run_count"] += 1

    accumulator["rounds_total"] += summary.rounds
    accumulator["fighter_deaths_total"] += summary.fighter_deaths
    accumulator["goblins_killed_total"] += summary.goblins_killed
    accumulator["remaining_fighter_hp_total"] += summary.remaining_fighter_hp
    accumulator["remaining_goblin_hp_total"] += summary.remaining_goblin_hp
    accumulator["total_runs"] += 1

    if summary.stable_unconscious_fighters > 0:
        accumulator["stable_but_unconscious_count"] += 1


def run_batch_chunk(task: BatchChunkTask) -> BatchChunkResult:
    placements = deserialize_placements(task.placements)
    accumulator = create_empty_batch_accumulator()

    for run_index in range(task.start_index, task.start_index + task.run_count):
        summary, resolved_behavior = summarize_batch_run(
            task.seed,
            placements,
            task.requested_player_behavior,
            task.requested_monster_behavior,
            task.enemy_preset_id,
            task.player_preset_id,
            task.smart_targeting_policy,
            task.enable_end_turn_flanking,
            task.enable_frontline_body_blocking,
            run_index,
            task.preserve_history,
        )
        accumulate_batch_summary(accumulator, summary, resolved_behavior)

    return BatchChunkResult(
        monster_behavior=task.requested_monster_behavior,
        completed_runs=task.run_count,
        accumulator=accumulator,
    )


def get_batch_behaviors(requested_monster_behavior: MonsterBehaviorSelection) -> tuple[MonsterBehavior, ...]:
    if requested_monster_behavior == "combined":
        return MONSTER_BEHAVIORS
    return (requested_monster_behavior,)


def get_total_batch_runs(requested_size: int, requested_monster_behavior: MonsterBehaviorSelection) -> int:
    return requested_size * len(get_batch_behaviors(requested_monster_behavior))


def should_parallelize_batch(total_runs: int) -> bool:
    return total_runs >= PARALLEL_BATCH_MIN_TOTAL_RUNS


def get_requested_worker_count(worker_count: int | None = None) -> int | None:
    requested_worker_count = worker_count
    if requested_worker_count is None:
        env_value = os.environ.get(BATCH_WORKERS_ENV_VAR)
        if env_value is None or not env_value.strip():
            return None
        try:
            requested_worker_count = int(env_value)
        except ValueError as error:
            raise ValueError(f"{BATCH_WORKERS_ENV_VAR} must be a positive integer.") from error

    if requested_worker_count < 1:
        raise ValueError("Worker count must be a positive integer.")
    return min(MAX_PARALLEL_BATCH_WORKERS, requested_worker_count)


def get_parallel_worker_count(total_runs: int, worker_count: int | None = None) -> int:
    cpu_count = os.cpu_count() or 1
    requested_worker_count = get_requested_worker_count(worker_count)
    if requested_worker_count is not None:
        return max(1, min(requested_worker_count, total_runs))
    return max(1, min(MAX_PARALLEL_BATCH_WORKERS, cpu_count, total_runs))


def resolve_batch_execution_plan(
    total_runs: int,
    force_serial: bool = False,
    worker_count: int | None = None,
) -> BatchExecutionPlan:
    if force_serial or not should_parallelize_batch(total_runs):
        return BatchExecutionPlan(execution_mode="serial", worker_count=1, total_runs=total_runs)

    resolved_worker_count = get_parallel_worker_count(total_runs, worker_count)
    if resolved_worker_count <= 1:
        return BatchExecutionPlan(execution_mode="serial", worker_count=1, total_runs=total_runs)

    return BatchExecutionPlan(execution_mode="parallel", worker_count=resolved_worker_count, total_runs=total_runs)


def get_parallel_chunk_size(run_count: int, worker_count: int) -> int:
    return max(10, math.ceil(run_count / worker_count))


def build_batch_chunk_tasks(
    seed: str,
    placements: dict[str, GridPosition],
    requested_player_behavior: PlayerBehavior,
    requested_monster_behavior: MonsterBehavior,
    enemy_preset_id: str | None,
    player_preset_id: str | None,
    smart_targeting_policy: str,
    enable_end_turn_flanking: bool,
    enable_frontline_body_blocking: bool,
    requested_size: int,
    preserve_history: bool,
    worker_count: int,
) -> list[BatchChunkTask]:
    chunk_size = get_parallel_chunk_size(requested_size, worker_count)
    serialized_placements = serialize_placements(placements)
    tasks: list[BatchChunkTask] = []

    for start_index in range(0, requested_size, chunk_size):
        tasks.append(
            BatchChunkTask(
                seed=seed,
                placements=serialized_placements,
                requested_player_behavior=requested_player_behavior,
                requested_monster_behavior=requested_monster_behavior,
                enemy_preset_id=enemy_preset_id,
                player_preset_id=player_preset_id,
                smart_targeting_policy=smart_targeting_policy,
                enable_end_turn_flanking=enable_end_turn_flanking,
                enable_frontline_body_blocking=enable_frontline_body_blocking,
                start_index=start_index,
                run_count=min(chunk_size, requested_size - start_index),
                preserve_history=preserve_history,
            )
        )

    return tasks


def combine_batch_accumulators(accumulators: list[dict[str, float]]) -> dict[str, float]:
    combined = create_empty_batch_accumulator()
    for accumulator in accumulators:
        combined = merge_batch_accumulators(combined, accumulator)
    return combined


def run_single_batch_accumulator(
    config: EncounterConfig,
    requested_player_behavior: PlayerBehavior,
    requested_monster_behavior: MonsterBehavior,
    capture_history: bool | None = None,
    progress_callback: Callable[[int, int, MonsterBehavior], None] | None = None,
    completed_offset: int = 0,
    total_runs: int | None = None,
) -> dict[str, float]:
    requested_size = config.batch_size or DEFAULT_BATCH_SIZE
    placements = resolve_placements(config)
    accumulator = create_empty_batch_accumulator()
    preserve_history = should_capture_batch_history(requested_size, capture_history)
    job_total_runs = total_runs or requested_size

    for run_index in range(requested_size):
        summary, resolved_behavior = summarize_batch_run(
            config.seed,
            placements,
            requested_player_behavior,
            requested_monster_behavior,
            config.enemy_preset_id,
            config.player_preset_id,
            config.smart_targeting_policy,
            config.enable_end_turn_flanking,
            config.enable_frontline_body_blocking,
            run_index,
            preserve_history,
        )
        accumulate_batch_summary(accumulator, summary, resolved_behavior)

        if progress_callback:
            progress_callback(completed_offset + run_index + 1, job_total_runs, requested_monster_behavior)

    return accumulator


def run_batch_serial(
    config: EncounterConfig,
    requested_size: int,
    requested_player_behavior: PlayerBehavior,
    requested_monster_behavior: MonsterBehaviorSelection,
    seed: str,
    progress_callback: Callable[[int, int, MonsterBehavior], None] | None = None,
    capture_history: bool | None = None,
) -> BatchSummary:
    total_runs = get_total_batch_runs(requested_size, requested_monster_behavior)
    accumulators_by_monster: dict[MonsterBehavior, dict[str, float]] = {}
    completed_offset = 0

    for monster_behavior in get_batch_behaviors(requested_monster_behavior):
        accumulator = run_single_batch_accumulator(
            config,
            requested_player_behavior,
            monster_behavior,
            capture_history=capture_history,
            progress_callback=progress_callback,
            completed_offset=completed_offset,
            total_runs=total_runs,
        )
        accumulators_by_monster[monster_behavior] = accumulator
        completed_offset += requested_size

    if requested_monster_behavior == "combined":
        combination_summaries = [
            finalize_batch_combination_summary(
                seed,
                requested_player_behavior,
                monster_behavior,
                requested_size,
                accumulators_by_monster[monster_behavior],
            )
            for monster_behavior in MONSTER_BEHAVIORS
        ]
        combined_accumulator = combine_batch_accumulators(list(accumulators_by_monster.values()))
        return finalize_batch_summary(
            seed,
            requested_player_behavior,
            "combined",
            requested_size,
            combined_accumulator,
            combination_summaries,
        )

    return finalize_batch_summary(
        seed,
        requested_player_behavior,
        requested_monster_behavior,
        requested_size,
        accumulators_by_monster[requested_monster_behavior],
        None,
    )


def run_batch_parallel(
    config: EncounterConfig,
    requested_size: int,
    requested_player_behavior: PlayerBehavior,
    requested_monster_behavior: MonsterBehaviorSelection,
    seed: str,
    progress_callback: Callable[[int, int, MonsterBehavior], None] | None = None,
    worker_count: int | None = None,
    capture_history: bool | None = None,
) -> BatchSummary:
    placements = resolve_placements(config)
    total_runs = get_total_batch_runs(requested_size, requested_monster_behavior)
    resolved_worker_count = get_parallel_worker_count(total_runs, worker_count)
    preserve_history = should_capture_batch_history(requested_size, capture_history)
    accumulators_by_monster = {
        monster_behavior: create_empty_batch_accumulator()
        for monster_behavior in get_batch_behaviors(requested_monster_behavior)
    }

    tasks: list[BatchChunkTask] = []
    for monster_behavior in get_batch_behaviors(requested_monster_behavior):
        tasks.extend(
            build_batch_chunk_tasks(
                seed,
                placements,
                requested_player_behavior,
                monster_behavior,
                config.enemy_preset_id,
                config.player_preset_id,
                config.smart_targeting_policy,
                config.enable_end_turn_flanking,
                config.enable_frontline_body_blocking,
                requested_size,
                preserve_history,
                resolved_worker_count,
            )
        )

    completed_runs = 0
    with ProcessPoolExecutor(max_workers=resolved_worker_count) as executor:
        futures = [executor.submit(run_batch_chunk, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            accumulators_by_monster[result.monster_behavior] = merge_batch_accumulators(
                accumulators_by_monster[result.monster_behavior],
                result.accumulator,
            )
            completed_runs += result.completed_runs

            if progress_callback:
                progress_callback(completed_runs, total_runs, result.monster_behavior)

    if requested_monster_behavior == "combined":
        combination_summaries = [
            finalize_batch_combination_summary(
                seed,
                requested_player_behavior,
                monster_behavior,
                requested_size,
                accumulators_by_monster[monster_behavior],
            )
            for monster_behavior in MONSTER_BEHAVIORS
        ]
        combined_accumulator = combine_batch_accumulators(list(accumulators_by_monster.values()))
        return finalize_batch_summary(
            seed,
            requested_player_behavior,
            "combined",
            requested_size,
            combined_accumulator,
            combination_summaries,
        )

    return finalize_batch_summary(
        seed,
        requested_player_behavior,
        requested_monster_behavior,
        requested_size,
        accumulators_by_monster[requested_monster_behavior],
        None,
    )


def run_batch(
    config: EncounterConfig,
    progress_callback: Callable[[int, int, MonsterBehavior], None] | None = None,
    *,
    force_serial: bool = False,
    worker_count: int | None = None,
    capture_history: bool | None = None,
) -> BatchSummary:
    requested_size = config.batch_size or DEFAULT_BATCH_SIZE
    requested_player_behavior = config.player_behavior or DEFAULT_BATCH_PLAYER_BEHAVIOR
    requested_monster_behavior = config.monster_behavior or DEFAULT_BATCH_MONSTER_BEHAVIOR

    if requested_size < 1 or requested_size > MAX_BATCH_SIZE or int(requested_size) != requested_size:
        raise ValueError(f"Batch size must be an integer between 1 and {MAX_BATCH_SIZE}.")

    seed = config.seed.strip() or DEFAULT_SEED
    total_runs = get_total_batch_runs(requested_size, requested_monster_behavior)
    execution_plan = resolve_batch_execution_plan(total_runs, force_serial=force_serial, worker_count=worker_count)

    if execution_plan.execution_mode == "parallel":
        return run_batch_parallel(
            config,
            requested_size,
            requested_player_behavior,
            requested_monster_behavior,
            seed,
            progress_callback,
            worker_count=execution_plan.worker_count,
            capture_history=capture_history,
        )

    return run_batch_serial(
        config,
        requested_size,
        requested_player_behavior,
        requested_monster_behavior,
        seed,
        progress_callback,
        capture_history=capture_history,
    )
