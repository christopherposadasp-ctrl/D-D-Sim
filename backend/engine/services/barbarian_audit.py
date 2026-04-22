from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal

from backend.content.scenario_definitions import ACTIVE_SCENARIO_IDS, get_scenario_definition
from backend.engine import create_encounter, run_encounter, step_encounter, summarize_encounter
from backend.engine.ai.decision import (
    build_position_index,
    can_intentionally_provoke_opportunity_attack,
    find_preferred_adjacent_square,
    find_preferred_advance_path,
    get_move_squares,
    get_player_primary_melee_weapon_id,
    get_smart_melee_attack_option,
    get_total_move_squares,
    should_commit_barbarian_rage,
    sort_player_combat_targets,
    sort_player_melee_targets,
)
from backend.engine.combat.engine import run_batch_serial
from backend.engine.combat.setup import resolve_player_behavior
from backend.engine.models.state import BatchSummary, CombatEvent, EncounterConfig, RunEncounterResult, UnitState
from backend.engine.utils.helpers import get_units_by_faction, unit_sort_key

AuditStatus = Literal["pass", "warn", "fail"]
AuditProgressStage = Literal["replay", "behavior", "health", "comparison", "complete"]
BarbarianAuditProgressCallback = Callable[[str, AuditProgressStage, dict[str, object]], None]

BARBARIAN_AUDIT_PLAYER_PRESET_IDS = ("barbarian_level2_sample_trio", "martial_mixed_party")
STRESS_SCENARIO_IDS = {"marsh_predators"}
DEFAULT_BASELINE_PATH = Path(__file__).resolve().parents[3] / "reports" / "baselines" / "pre_barbarian_baseline_2026-04-20.json"


@dataclass(frozen=True)
class BarbarianAuditConfig:
    fixed_seed_runs: int = 5
    behavior_batch_size: int = 100
    health_batch_size: int = 300
    seed_prefix: str = "barbarian-audit"
    baseline_report_path: Path = DEFAULT_BASELINE_PATH


def build_quick_barbarian_audit_config(seed_prefix: str = "barbarian-audit") -> BarbarianAuditConfig:
    return BarbarianAuditConfig(
        fixed_seed_runs=2,
        behavior_batch_size=10,
        health_batch_size=30,
        seed_prefix=seed_prefix,
    )


def build_full_barbarian_audit_config(seed_prefix: str = "barbarian-audit") -> BarbarianAuditConfig:
    return BarbarianAuditConfig(seed_prefix=seed_prefix)


@dataclass
class BarbarianRunMetrics:
    opening_rage_opportunities: int = 0
    opening_rage_successes: int = 0
    rage_dropped_without_qualifying_reason_count: int = 0
    rage_extended_count: int = 0
    greataxe_attack_count: int = 0
    handaxe_attack_count: int = 0
    turn_one_handaxe_count: int = 0
    cleave_trigger_count: int = 0
    vex_applied_count: int = 0
    vex_consumed_count: int = 0
    damage_resisted_total: int = 0
    temporary_hp_absorbed_total: int = 0
    barbarian_downed_count: int = 0
    barbarian_death_count: int = 0


@dataclass
class BarbarianCounterTotals:
    opening_rage_opportunities: int = 0
    opening_rage_successes: int = 0
    rage_dropped_without_qualifying_reason_count: int = 0
    rage_extended_count: int = 0
    greataxe_attack_count: int = 0
    handaxe_attack_count: int = 0
    turn_one_handaxe_count: int = 0
    cleave_trigger_count: int = 0
    vex_applied_count: int = 0
    vex_consumed_count: int = 0
    damage_resisted_total: int = 0
    temporary_hp_absorbed_total: int = 0
    barbarian_downed_count: int = 0
    barbarian_death_count: int = 0

    def add_run(self, metrics: BarbarianRunMetrics) -> None:
        self.opening_rage_opportunities += metrics.opening_rage_opportunities
        self.opening_rage_successes += metrics.opening_rage_successes
        self.rage_dropped_without_qualifying_reason_count += metrics.rage_dropped_without_qualifying_reason_count
        self.rage_extended_count += metrics.rage_extended_count
        self.greataxe_attack_count += metrics.greataxe_attack_count
        self.handaxe_attack_count += metrics.handaxe_attack_count
        self.turn_one_handaxe_count += metrics.turn_one_handaxe_count
        self.cleave_trigger_count += metrics.cleave_trigger_count
        self.vex_applied_count += metrics.vex_applied_count
        self.vex_consumed_count += metrics.vex_consumed_count
        self.damage_resisted_total += metrics.damage_resisted_total
        self.temporary_hp_absorbed_total += metrics.temporary_hp_absorbed_total
        self.barbarian_downed_count += metrics.barbarian_downed_count
        self.barbarian_death_count += metrics.barbarian_death_count

    def rage_open_rate(self) -> float:
        if self.opening_rage_opportunities <= 0:
            return 0.0
        return self.opening_rage_successes / self.opening_rage_opportunities


@dataclass
class BarbarianAuditRow:
    scenario_id: str
    scenario_display_name: str
    player_preset_id: str
    enemy_preset_id: str
    player_behavior: str
    monster_behavior: str
    total_runs: int
    smart_run_count: int
    dumb_run_count: int
    player_win_rate: float
    smart_player_win_rate: float | None
    dumb_player_win_rate: float | None
    average_rounds: float
    average_fighter_deaths: float
    counter_run_count: int
    rage_opened_on_first_actionable_turn_rate: float
    rage_dropped_without_qualifying_reason_count: int
    rage_extended_count: int
    greataxe_attack_count: int
    handaxe_attack_count: int
    turn_one_handaxe_count: int
    cleave_trigger_count: int
    vex_applied_count: int
    vex_consumed_count: int
    damage_resisted_total: int
    temporary_hp_absorbed_total: int
    barbarian_downed_count: int
    barbarian_death_count: int
    status: AuditStatus
    recommendation: str | None
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    replay_seeds: list[str] = field(default_factory=list)
    behavior_win_rates: dict[str, float] = field(default_factory=dict)

    def to_report_dict(self) -> dict[str, object]:
        return {
            "scenarioId": self.scenario_id,
            "scenarioDisplayName": self.scenario_display_name,
            "playerPresetId": self.player_preset_id,
            "enemyPresetId": self.enemy_preset_id,
            "playerBehavior": self.player_behavior,
            "monsterBehavior": self.monster_behavior,
            "totalRuns": self.total_runs,
            "smartRunCount": self.smart_run_count,
            "dumbRunCount": self.dumb_run_count,
            "playerWinRate": self.player_win_rate,
            "smartPlayerWinRate": self.smart_player_win_rate,
            "dumbPlayerWinRate": self.dumb_player_win_rate,
            "averageRounds": self.average_rounds,
            "averageFighterDeaths": self.average_fighter_deaths,
            "counterRunCount": self.counter_run_count,
            "rageOpenedOnFirstActionableTurnRate": self.rage_opened_on_first_actionable_turn_rate,
            "rageDroppedWithoutQualifyingReasonCount": self.rage_dropped_without_qualifying_reason_count,
            "rageExtendedCount": self.rage_extended_count,
            "greataxeAttackCount": self.greataxe_attack_count,
            "handaxeAttackCount": self.handaxe_attack_count,
            "turnOneHandaxeCount": self.turn_one_handaxe_count,
            "cleaveTriggerCount": self.cleave_trigger_count,
            "vexAppliedCount": self.vex_applied_count,
            "vexConsumedCount": self.vex_consumed_count,
            "damageResistedTotal": self.damage_resisted_total,
            "temporaryHpAbsorbedTotal": self.temporary_hp_absorbed_total,
            "barbarianDownedCount": self.barbarian_downed_count,
            "barbarianDeathCount": self.barbarian_death_count,
            "status": self.status,
            "recommendation": self.recommendation,
            "warnings": list(self.warnings),
            "failures": list(self.failures),
            "replaySeeds": list(self.replay_seeds),
            "behaviorWinRates": dict(self.behavior_win_rates),
        }


@dataclass
class PresetAggregate:
    player_preset_id: str
    total_runs: int
    player_win_rate: float
    smart_player_win_rate: float | None
    dumb_player_win_rate: float | None
    status: AuditStatus
    warnings: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict[str, object]:
        return {
            "playerPresetId": self.player_preset_id,
            "totalRuns": self.total_runs,
            "playerWinRate": self.player_win_rate,
            "smartPlayerWinRate": self.smart_player_win_rate,
            "dumbPlayerWinRate": self.dumb_player_win_rate,
            "status": self.status,
            "warnings": list(self.warnings),
        }


def emit_progress(
    callback: BarbarianAuditProgressCallback | None,
    label: str,
    stage: AuditProgressStage,
    details: dict[str, object] | None = None,
) -> None:
    if callback is None:
        return
    callback(label, stage, details or {})


def get_barbarian_audit_player_preset_ids() -> tuple[str, ...]:
    return BARBARIAN_AUDIT_PLAYER_PRESET_IDS


def get_barbarian_audit_scenario_ids() -> tuple[str, ...]:
    return ACTIVE_SCENARIO_IDS


def get_barbarian_unit_ids(units: dict[str, UnitState]) -> tuple[str, ...]:
    barbarian_ids = [unit.id for unit in units.values() if unit.class_id == "barbarian"]
    return tuple(sorted(barbarian_ids, key=unit_sort_key))


def is_barbarian_unit(unit: UnitState) -> bool:
    return unit.class_id == "barbarian"


def is_actionable_actor_event(event: CombatEvent) -> bool:
    return event.event_type in {"phase_change", "move", "attack", "skip", "heal", "stabilize"}


def get_turn_blocks(events: list[CombatEvent]) -> list[tuple[str, int, list[CombatEvent]]]:
    blocks: list[tuple[str, int, list[CombatEvent]]] = []
    current_actor_id: str | None = None
    current_round = 0
    current_events: list[CombatEvent] = []

    for event in events:
        if event.event_type == "turn_start":
            if current_actor_id is not None:
                blocks.append((current_actor_id, current_round, current_events))
            current_actor_id = event.actor_id
            current_round = event.round
            current_events = [event]
            continue

        if current_actor_id is None:
            continue
        current_events.append(event)

    if current_actor_id is not None:
        blocks.append((current_actor_id, current_round, current_events))

    return blocks


def extract_barbarian_run_metrics(result: RunEncounterResult) -> BarbarianRunMetrics:
    metrics = BarbarianRunMetrics()
    barbarian_ids = set(get_barbarian_unit_ids(result.final_state.units))

    seen_first_turns: set[str] = set()
    for frame_index in range(1, len(result.replay_frames)):
        pre_turn_state = result.replay_frames[frame_index - 1].state
        frame = result.replay_frames[frame_index]
        actor_id = frame.active_combatant_id
        if actor_id not in barbarian_ids or actor_id in seen_first_turns:
            continue

        actor = pre_turn_state.units[actor_id]
        turn_events = frame.events
        first_actionable = next(
            (
                event
                for event in turn_events
                if event.actor_id == actor_id and is_actionable_actor_event(event)
            ),
            None,
        )
        if first_actionable is None:
            continue

        seen_first_turns.add(actor_id)
        will_attack_this_turn = any(
            event.actor_id == actor_id and event.event_type == "attack" for event in turn_events
        )
        if should_commit_barbarian_rage(
            pre_turn_state,
            actor,
            will_attack_this_turn=will_attack_this_turn,
            position_index=build_position_index(pre_turn_state),
        ):
            metrics.opening_rage_opportunities += 1
            if first_actionable.event_type == "phase_change" and "enters a rage" in first_actionable.text_summary.lower():
                metrics.opening_rage_successes += 1

    for event in result.events:
        if event.actor_id in barbarian_ids:
            if event.event_type == "phase_change" and event.resolved_totals.get("reason") == "upkeep":
                metrics.rage_dropped_without_qualifying_reason_count += 1
            if "extends the current rage" in " ".join(event.condition_deltas):
                metrics.rage_extended_count += 1
            if event.event_type == "attack" and event.damage_details:
                if event.damage_details.weapon_id == "greataxe":
                    metrics.greataxe_attack_count += 1
                if event.damage_details.weapon_id == "handaxe":
                    metrics.handaxe_attack_count += 1
                    if event.round == 1:
                        metrics.turn_one_handaxe_count += 1
                if event.damage_details.mastery_applied == "cleave":
                    metrics.cleave_trigger_count += 1
                if event.damage_details.mastery_applied == "vex":
                    metrics.vex_applied_count += 1
                if any("vex advantage is consumed" in delta for delta in event.condition_deltas):
                    metrics.vex_consumed_count += 1

        if event.damage_details and any(target_id in barbarian_ids for target_id in event.target_ids):
            metrics.damage_resisted_total += int(event.damage_details.resisted_damage)
            metrics.temporary_hp_absorbed_total += int(event.damage_details.temporary_hp_absorbed)

    for unit_id in barbarian_ids:
        unit = result.final_state.units[unit_id]
        if unit.conditions.dead:
            metrics.barbarian_death_count += 1
        elif unit.current_hp == 0:
            metrics.barbarian_downed_count += 1

    return metrics


def get_first_actor_event(turn_events: list[CombatEvent], actor_id: str) -> CombatEvent | None:
    for event in turn_events:
        if event.actor_id == actor_id and event.event_type != "turn_start":
            return event
    return None


def get_actor_damage_taken(turn_events: list[CombatEvent], actor_id: str) -> int:
    total_damage = 0
    for event in turn_events:
        if not event.damage_details or actor_id not in event.target_ids:
            continue
        total_damage += int(event.damage_details.final_damage_to_hp)
        total_damage += int(event.damage_details.temporary_hp_absorbed)
    return total_damage


def state_has_legal_barbarian_melee_attack(state, actor: UnitState) -> bool:
    move_squares = get_move_squares(actor)
    position_index = build_position_index(state)
    melee_weapon_id = get_player_primary_melee_weapon_id(actor)
    conscious_enemies = sort_player_combat_targets(
        state,
        actor,
        [unit for unit in get_units_by_faction(state, "goblins") if not unit.conditions.dead],
        state.player_behavior,
    )
    melee_targets = sort_player_melee_targets(state, actor, conscious_enemies, state.player_behavior)

    smart_option = (
        get_smart_melee_attack_option(state, actor, melee_targets, move_squares, melee_weapon_id, position_index)
        if state.player_behavior == "smart"
        else None
    )
    if smart_option:
        return True

    for target in melee_targets:
        melee_path = find_preferred_adjacent_square(
            state,
            actor.id,
            target.id,
            move_squares,
            can_intentionally_provoke_opportunity_attack(state, actor, target),
            position_index,
        )
        if melee_path:
            return True

    return False


def state_has_meaningful_barbarian_dash(state, actor: UnitState) -> bool:
    dash_squares = get_total_move_squares(actor, 1)
    position_index = build_position_index(state)
    conscious_enemies = sort_player_combat_targets(
        state,
        actor,
        [unit for unit in get_units_by_faction(state, "goblins") if not unit.conditions.dead],
        state.player_behavior,
    )
    melee_targets = sort_player_melee_targets(state, actor, conscious_enemies, state.player_behavior)
    nearest_target = melee_targets[0] if melee_targets else None
    if not nearest_target:
        return False

    dash_path = find_preferred_advance_path(
        state,
        actor.id,
        nearest_target.id,
        dash_squares,
        can_intentionally_provoke_opportunity_attack(state, actor, nearest_target),
        position_index,
    )
    return bool(dash_path and dash_path.distance > 0)


def build_replay_config(
    seed_prefix: str,
    player_preset_id: str,
    scenario_id: str,
    player_behavior: str,
    run_index: int,
) -> EncounterConfig:
    return EncounterConfig(
        seed=f"{seed_prefix}-{player_preset_id}-{scenario_id}-{player_behavior}-{run_index:02d}",
        enemy_preset_id=scenario_id,
        player_preset_id=player_preset_id,
        player_behavior=player_behavior,
        monster_behavior="balanced",
    )


def review_fixed_seed_replays(
    player_preset_id: str,
    scenario_id: str,
    config: BarbarianAuditConfig,
    progress_callback: BarbarianAuditProgressCallback | None = None,
) -> tuple[list[str], list[str]]:
    label = f"{player_preset_id}:{scenario_id}"
    issues: list[str] = []
    replay_seeds: list[str] = []
    total_runs = config.fixed_seed_runs * 2
    completed_runs = 0

    for player_behavior in ("smart", "dumb"):
        for run_index in range(config.fixed_seed_runs):
            emit_progress(
                progress_callback,
                label,
                "replay",
                {
                    "current": completed_runs,
                    "total": total_runs,
                    "playerBehavior": player_behavior,
                },
            )
            encounter = create_encounter(build_replay_config(config.seed_prefix, player_preset_id, scenario_id, player_behavior, run_index))
            replay_seeds.append(encounter.seed)

            reviewed_opening_turns: set[str] = set()
            while encounter.terminal_state != "complete":
                actor_id = encounter.initiative_order[encounter.active_combatant_index]
                actor = encounter.units[actor_id]
                pre_step_state = encounter.model_copy(deep=True)
                turn_result = step_encounter(encounter)
                turn_events = turn_result.events
                encounter = turn_result.state

                if not is_barbarian_unit(actor):
                    continue

                if actor_id not in reviewed_opening_turns:
                    first_event = get_first_actor_event(turn_events, actor_id)
                    if (
                        pre_step_state.units[actor_id].current_hp > 0
                        and not pre_step_state.units[actor_id].conditions.unconscious
                        and pre_step_state.units[actor_id].resources.rage_uses > 0
                        and not any(effect.kind == "rage" for effect in pre_step_state.units[actor_id].temporary_effects)
                    ):
                        reviewed_opening_turns.add(actor_id)
                        pre_actor = pre_step_state.units[actor_id]
                        will_attack_this_turn = any(
                            event.actor_id == actor_id and event.event_type == "attack" for event in turn_events
                        )
                        expected_opening_rage = should_commit_barbarian_rage(
                            pre_step_state,
                            pre_actor,
                            will_attack_this_turn=will_attack_this_turn,
                            position_index=build_position_index(pre_step_state),
                        )
                        if expected_opening_rage and (
                            first_event is None or "enters a rage" not in first_event.text_summary.lower()
                        ):
                            issues.append(
                                f"{encounter.seed}: {actor_id} skipped opening rage on the first actionable turn."
                            )

                handaxe_event = next(
                    (
                        event
                        for event in turn_events
                        if event.actor_id == actor_id
                        and event.event_type == "attack"
                        and event.damage_details
                        and event.damage_details.weapon_id == "handaxe"
                    ),
                    None,
                )
                if handaxe_event:
                    pre_actor = pre_step_state.units[actor_id]
                    if state_has_legal_barbarian_melee_attack(pre_step_state, pre_actor):
                        issues.append(f"{encounter.seed}: {actor_id} threw a handaxe when a melee attack was available.")
                    elif state_has_meaningful_barbarian_dash(pre_step_state, pre_actor):
                        issues.append(f"{encounter.seed}: {actor_id} threw a handaxe when a meaningful closer dash existed.")

                rage_drop_event = next(
                    (
                        event
                        for event in turn_events
                        if event.actor_id == actor_id
                        and event.event_type == "phase_change"
                        and event.resolved_totals.get("reason") == "upkeep"
                    ),
                    None,
                )
                if rage_drop_event:
                    pre_actor = pre_step_state.units[actor_id]
                    took_damage = get_actor_damage_taken(turn_events, actor_id) > 0
                    made_attack_roll = any(
                        event.actor_id == actor_id and event.event_type == "attack" for event in turn_events
                    )
                    extended_rage = any("extends the current rage" in " ".join(event.condition_deltas) for event in turn_events)
                    actor_finished_turn = encounter.units[actor_id]
                    if (
                        any(effect.kind == "rage" for effect in pre_actor.temporary_effects)
                        and pre_actor.resources.rage_uses > 0
                        and not took_damage
                        and not made_attack_roll
                        and not extended_rage
                        and actor_finished_turn.current_hp > 0
                        and not actor_finished_turn.conditions.dead
                        and not actor_finished_turn.conditions.unconscious
                    ):
                        issues.append(
                            f"{encounter.seed}: {actor_id} let rage drop without attacking, taking damage, or extending it."
                        )

            completed_runs += 1
            emit_progress(
                progress_callback,
                label,
                "replay",
                {
                    "current": completed_runs,
                    "total": total_runs,
                    "playerBehavior": player_behavior,
                },
            )

    return issues, replay_seeds


def run_behavior_sanity_pass(
    player_preset_id: str,
    scenario_id: str,
    config: BarbarianAuditConfig,
    progress_callback: BarbarianAuditProgressCallback | None = None,
) -> tuple[BarbarianCounterTotals, dict[str, float]]:
    label = f"{player_preset_id}:{scenario_id}"
    totals = BarbarianCounterTotals()
    total_runs = config.behavior_batch_size * 3
    completed_runs = 0
    behavior_win_rates: dict[str, float] = {}

    for requested_player_behavior in ("smart", "dumb", "balanced"):
        player_wins = 0

        for run_index in range(config.behavior_batch_size):
            emit_progress(
                progress_callback,
                label,
                "behavior",
                {
                    "current": completed_runs,
                    "total": total_runs,
                    "playerBehavior": requested_player_behavior,
                },
            )
            resolved_behavior = resolve_player_behavior(requested_player_behavior, run_index)
            encounter_config = EncounterConfig(
                seed=f"{config.seed_prefix}-{player_preset_id}-{scenario_id}-behavior-{requested_player_behavior}-{run_index:03d}",
                enemy_preset_id=scenario_id,
                player_preset_id=player_preset_id,
                player_behavior=resolved_behavior,
                monster_behavior="balanced",
            )
            result = run_encounter(encounter_config)
            if summarize_encounter(result.final_state).winner == "fighters":
                player_wins += 1
            totals.add_run(extract_barbarian_run_metrics(result))
            completed_runs += 1
            emit_progress(
                progress_callback,
                label,
                "behavior",
                {
                    "current": completed_runs,
                    "total": total_runs,
                    "playerBehavior": requested_player_behavior,
                },
            )

        behavior_win_rates[requested_player_behavior] = player_wins / config.behavior_batch_size if config.behavior_batch_size > 0 else 0.0

    return totals, behavior_win_rates


def run_health_pass(
    player_preset_id: str,
    scenario_id: str,
    config: BarbarianAuditConfig,
    progress_callback: BarbarianAuditProgressCallback | None = None,
) -> BatchSummary:
    label = f"{player_preset_id}:{scenario_id}"

    def on_progress(completed_runs: int, total_runs: int, monster_behavior: str) -> None:
        emit_progress(
            progress_callback,
            label,
            "health",
            {
                "current": completed_runs,
                "total": total_runs,
                "monsterBehavior": monster_behavior,
            },
        )

    return run_batch_serial(
        EncounterConfig(
            seed=f"{config.seed_prefix}-{player_preset_id}-{scenario_id}-health",
            enemy_preset_id=scenario_id,
            player_preset_id=player_preset_id,
            batch_size=config.health_batch_size,
            player_behavior="balanced",
            monster_behavior="combined",
        ),
        config.health_batch_size,
        "balanced",
        "combined",
        f"{config.seed_prefix}-{player_preset_id}-{scenario_id}-health",
        on_progress if progress_callback else None,
    )


def build_row_warnings(
    scenario_id: str,
    summary: BatchSummary,
    counter_totals: BarbarianCounterTotals,
) -> list[str]:
    warnings: list[str] = []

    if (
        summary.smart_player_win_rate is not None
        and summary.dumb_player_win_rate is not None
        and float(summary.smart_player_win_rate) < float(summary.dumb_player_win_rate)
    ):
        warnings.append("Smart players underperformed dumb players in the combined pass.")

    if counter_totals.turn_one_handaxe_count > 0:
        warnings.append("The Barbarian opened with at least one round-1 handaxe attack.")

    if scenario_id not in STRESS_SCENARIO_IDS and counter_totals.greataxe_attack_count <= counter_totals.handaxe_attack_count:
        warnings.append("Handaxe volume matched or exceeded greataxe volume in a non-stress scenario.")

    return warnings


def build_row_recommendation(
    scenario_id: str,
    warnings: list[str],
    failures: list[str],
) -> str | None:
    if any("handaxe" in issue.lower() for issue in failures) or any("handaxe" in issue.lower() for issue in warnings):
        return "Inspect melee-closure decision order before touching stats."

    if any("rage drop" in issue.lower() or "rage" in issue.lower() for issue in failures):
        return "Inspect rage upkeep decision timing before touching encounter balance."

    if any("smart players underperformed dumb players" in issue.lower() for issue in warnings):
        if scenario_id == "orc_push":
            return "Inspect scenario-specific front-line pressure before changing Barbarian logic globally."
        return "Inspect flanking pathing and target ranking before touching numbers."

    return None


def determine_row_status(warnings: list[str], failures: list[str]) -> AuditStatus:
    if failures:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def audit_barbarian_pair(
    player_preset_id: str,
    scenario_id: str,
    config: BarbarianAuditConfig | None = None,
    progress_callback: BarbarianAuditProgressCallback | None = None,
) -> BarbarianAuditRow:
    audit_config = config or BarbarianAuditConfig()
    scenario = get_scenario_definition(scenario_id)

    failures, replay_seeds = review_fixed_seed_replays(player_preset_id, scenario_id, audit_config, progress_callback)
    counter_totals, behavior_win_rates = run_behavior_sanity_pass(player_preset_id, scenario_id, audit_config, progress_callback)
    summary = run_health_pass(player_preset_id, scenario_id, audit_config, progress_callback)
    warnings = build_row_warnings(scenario_id, summary, counter_totals)
    recommendation = build_row_recommendation(scenario_id, warnings, failures)
    status = determine_row_status(warnings, failures)

    row = BarbarianAuditRow(
        scenario_id=scenario_id,
        scenario_display_name=scenario.display_name,
        player_preset_id=player_preset_id,
        enemy_preset_id=scenario.enemy_preset_id,
        player_behavior="balanced",
        monster_behavior="combined",
        total_runs=int(summary.total_runs),
        smart_run_count=int(summary.smart_run_count),
        dumb_run_count=int(summary.dumb_run_count),
        player_win_rate=float(summary.player_win_rate),
        smart_player_win_rate=float(summary.smart_player_win_rate) if summary.smart_player_win_rate is not None else None,
        dumb_player_win_rate=float(summary.dumb_player_win_rate) if summary.dumb_player_win_rate is not None else None,
        average_rounds=float(summary.average_rounds),
        average_fighter_deaths=float(summary.average_fighter_deaths),
        counter_run_count=audit_config.behavior_batch_size * 3,
        rage_opened_on_first_actionable_turn_rate=counter_totals.rage_open_rate(),
        rage_dropped_without_qualifying_reason_count=counter_totals.rage_dropped_without_qualifying_reason_count,
        rage_extended_count=counter_totals.rage_extended_count,
        greataxe_attack_count=counter_totals.greataxe_attack_count,
        handaxe_attack_count=counter_totals.handaxe_attack_count,
        turn_one_handaxe_count=counter_totals.turn_one_handaxe_count,
        cleave_trigger_count=counter_totals.cleave_trigger_count,
        vex_applied_count=counter_totals.vex_applied_count,
        vex_consumed_count=counter_totals.vex_consumed_count,
        damage_resisted_total=counter_totals.damage_resisted_total,
        temporary_hp_absorbed_total=counter_totals.temporary_hp_absorbed_total,
        barbarian_downed_count=counter_totals.barbarian_downed_count,
        barbarian_death_count=counter_totals.barbarian_death_count,
        status=status,
        recommendation=recommendation,
        warnings=warnings,
        failures=failures,
        replay_seeds=replay_seeds,
        behavior_win_rates=behavior_win_rates,
    )

    emit_progress(
        progress_callback,
        f"{player_preset_id}:{scenario_id}",
        "complete",
        {
            "status": row.status,
            "warningCount": len(row.warnings),
            "failureCount": len(row.failures),
        },
    )
    return row


def audit_barbarian_profiles(
    config: BarbarianAuditConfig | None = None,
    player_preset_ids: Iterable[str] | None = None,
    scenario_ids: Iterable[str] | None = None,
    progress_callback: BarbarianAuditProgressCallback | None = None,
) -> list[BarbarianAuditRow]:
    audit_config = config or BarbarianAuditConfig()
    selected_player_presets = tuple(player_preset_ids) if player_preset_ids is not None else BARBARIAN_AUDIT_PLAYER_PRESET_IDS
    selected_scenarios = tuple(scenario_ids) if scenario_ids is not None else ACTIVE_SCENARIO_IDS

    rows: list[BarbarianAuditRow] = []
    for player_preset_id in selected_player_presets:
        for scenario_id in selected_scenarios:
            rows.append(audit_barbarian_pair(player_preset_id, scenario_id, audit_config, progress_callback))
    return rows


def build_preset_aggregates(rows: list[BarbarianAuditRow]) -> list[PresetAggregate]:
    aggregates: list[PresetAggregate] = []

    for player_preset_id in BARBARIAN_AUDIT_PLAYER_PRESET_IDS:
        matching_rows = [row for row in rows if row.player_preset_id == player_preset_id]
        if not matching_rows:
            continue

        total_runs = sum(row.total_runs for row in matching_rows)
        player_wins = sum(row.player_win_rate * row.total_runs for row in matching_rows)
        total_smart_runs = sum(row.smart_run_count for row in matching_rows)
        total_dumb_runs = sum(row.dumb_run_count for row in matching_rows)
        smart_wins = sum((row.smart_player_win_rate or 0.0) * row.smart_run_count for row in matching_rows)
        dumb_wins = sum((row.dumb_player_win_rate or 0.0) * row.dumb_run_count for row in matching_rows)

        warnings: list[str] = []
        aggregate_status: AuditStatus = "pass"
        smart_rate = smart_wins / total_smart_runs if total_smart_runs > 0 else None
        dumb_rate = dumb_wins / total_dumb_runs if total_dumb_runs > 0 else None
        if smart_rate is not None and dumb_rate is not None and smart_rate < dumb_rate:
            warnings.append("Smart players underperformed dumb players in the aggregate combined pass.")
            aggregate_status = "fail"

        aggregates.append(
            PresetAggregate(
                player_preset_id=player_preset_id,
                total_runs=total_runs,
                player_win_rate=player_wins / total_runs if total_runs > 0 else 0.0,
                smart_player_win_rate=smart_rate,
                dumb_player_win_rate=dumb_rate,
                status=aggregate_status,
                warnings=warnings,
            )
        )

    return aggregates


def build_fighter_trio_comparison(
    rows: list[BarbarianAuditRow],
    config: BarbarianAuditConfig,
    progress_callback: BarbarianAuditProgressCallback | None = None,
) -> list[dict[str, object]]:
    comparisons: list[dict[str, object]] = []
    scenario_ids = [
        scenario_id
        for scenario_id in ACTIVE_SCENARIO_IDS
        if any(row.player_preset_id == "barbarian_level2_sample_trio" and row.scenario_id == scenario_id for row in rows)
    ]

    for scenario_id in scenario_ids:
        emit_progress(
            progress_callback,
            f"fighter-comparison:{scenario_id}",
            "comparison",
            {"status": "start"},
        )
        fighter_summary = run_health_pass("fighter_sample_trio", scenario_id, config, None)
        barbarian_row = next(
            row for row in rows if row.player_preset_id == "barbarian_level2_sample_trio" and row.scenario_id == scenario_id
        )
        comparisons.append(
            {
                "scenarioId": scenario_id,
                "fighterTrioPlayerWinRate": float(fighter_summary.player_win_rate),
                "barbarianTrioPlayerWinRate": barbarian_row.player_win_rate,
                "playerWinRateDelta": barbarian_row.player_win_rate - float(fighter_summary.player_win_rate),
                "fighterTrioAverageRounds": float(fighter_summary.average_rounds),
                "barbarianTrioAverageRounds": barbarian_row.average_rounds,
                "fighterTrioAverageFighterDeaths": float(fighter_summary.average_fighter_deaths),
                "barbarianTrioAverageFighterDeaths": barbarian_row.average_fighter_deaths,
            }
        )
        emit_progress(
            progress_callback,
            f"fighter-comparison:{scenario_id}",
            "comparison",
            {"status": "complete"},
        )

    return comparisons


def load_baseline_results(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}

    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return {entry["scenarioId"]: entry for entry in payload.get("results", []) if isinstance(entry, dict)}


def build_mixed_party_baseline_comparison(
    rows: list[BarbarianAuditRow],
    baseline_path: Path,
) -> list[dict[str, object]]:
    baseline_results = load_baseline_results(baseline_path)
    comparisons: list[dict[str, object]] = []

    for scenario_id, baseline_entry in baseline_results.items():
        matching_row = next(
            (row for row in rows if row.player_preset_id == "martial_mixed_party" and row.scenario_id == scenario_id),
            None,
        )
        if matching_row is None:
            continue

        comparisons.append(
            {
                "scenarioId": scenario_id,
                "baselinePlayerWinRate": float(baseline_entry["playerWinRate"]),
                "currentPlayerWinRate": matching_row.player_win_rate,
                "playerWinRateDelta": matching_row.player_win_rate - float(baseline_entry["playerWinRate"]),
                "baselineAverageRounds": float(baseline_entry["averageRounds"]),
                "currentAverageRounds": matching_row.average_rounds,
                "baselineAverageFighterDeaths": float(baseline_entry["averageFighterDeaths"]),
                "currentAverageFighterDeaths": matching_row.average_fighter_deaths,
            }
        )

    return comparisons


def build_report_payload(
    rows: list[BarbarianAuditRow],
    config: BarbarianAuditConfig,
    rules_gate: dict[str, object] | None = None,
    comparisons: dict[str, object] | None = None,
) -> dict[str, object]:
    aggregates = build_preset_aggregates(rows)
    overall_status: AuditStatus = "pass"
    if rules_gate and rules_gate.get("status") == "fail":
        overall_status = "fail"
    elif any(aggregate.status == "fail" for aggregate in aggregates):
        overall_status = "fail"
    elif any(row.status == "fail" for row in rows) or any(row.status == "warn" for row in rows) or any(aggregate.status == "warn" for aggregate in aggregates):
        overall_status = "warn"

    comparison_payload = comparisons or {
        "barbarianSampleTrioVsFighterSampleTrio": build_fighter_trio_comparison(rows, config),
        "martialMixedPartyVsPreBarbarianBaseline": build_mixed_party_baseline_comparison(rows, config.baseline_report_path),
    }

    return {
        "config": {
            **asdict(config),
            "baseline_report_path": str(config.baseline_report_path),
        },
        "rulesGate": rules_gate,
        "playerPresetIds": list(get_barbarian_audit_player_preset_ids()),
        "scenarioIds": list(get_barbarian_audit_scenario_ids()),
        "overallStatus": overall_status,
        "rows": [row.to_report_dict() for row in rows],
        "presetAggregates": [aggregate.to_report_dict() for aggregate in aggregates],
        "comparisons": comparison_payload,
    }


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def format_barbarian_audit_report(
    rows: list[BarbarianAuditRow],
    aggregates: list[PresetAggregate],
    rules_gate: dict[str, object] | None = None,
    fighter_comparison: list[dict[str, object]] | None = None,
    baseline_comparison: list[dict[str, object]] | None = None,
) -> str:
    lines: list[str] = []

    if rules_gate:
        lines.append("## Rules Gate")
        lines.append(f"- Status: {rules_gate.get('status', 'unknown')}")
        lines.append(f"- Command: `{rules_gate.get('command', '')}`")
        if rules_gate.get("status") == "fail":
            stdout_tail = rules_gate.get("stdoutTail", [])
            if stdout_tail:
                lines.append("- Output tail:")
                lines.extend(f"  - {entry}" for entry in stdout_tail if isinstance(entry, str))
        lines.append("")

    lines.append("## Preset Aggregates")
    lines.append("| playerPresetId | totalRuns | playerWinRate | smartPlayerWinRate | dumbPlayerWinRate | status |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for aggregate in aggregates:
        lines.append(
            "| "
            + " | ".join(
                [
                    aggregate.player_preset_id,
                    str(aggregate.total_runs),
                    format_percent(aggregate.player_win_rate),
                    format_percent(aggregate.smart_player_win_rate),
                    format_percent(aggregate.dumb_player_win_rate),
                    aggregate.status,
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Scenario Rows")
    lines.append(
        "| playerPresetId | scenarioId | playerWinRate | smartPlayerWinRate | dumbPlayerWinRate | averageRounds | rageOpenRate | greataxeAttacks | handaxeAttacks | status | recommendation |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.player_preset_id,
                    row.scenario_id,
                    format_percent(row.player_win_rate),
                    format_percent(row.smart_player_win_rate),
                    format_percent(row.dumb_player_win_rate),
                    f"{row.average_rounds:.2f}",
                    format_percent(row.rage_opened_on_first_actionable_turn_rate),
                    str(row.greataxe_attack_count),
                    str(row.handaxe_attack_count),
                    row.status,
                    row.recommendation or "-",
                ]
            )
            + " |"
        )

    for row in rows:
        if not row.failures and not row.warnings:
            continue
        lines.append("")
        lines.append(f"### {row.player_preset_id} / {row.scenario_id}")
        for failure in row.failures:
            lines.append(f"- fail: {failure}")
        for warning in row.warnings:
            lines.append(f"- warn: {warning}")

    if fighter_comparison:
        lines.append("")
        lines.append("## Barbarian Trio vs Fighter Trio")
        lines.append("| scenarioId | barbarianTrioPlayerWinRate | fighterTrioPlayerWinRate | delta |")
        lines.append("| --- | --- | --- | --- |")
        for entry in fighter_comparison:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(entry["scenarioId"]),
                        format_percent(float(entry["barbarianTrioPlayerWinRate"])),
                        format_percent(float(entry["fighterTrioPlayerWinRate"])),
                        f"{float(entry['playerWinRateDelta']) * 100:.1f} pts",
                    ]
                )
                + " |"
            )

    if baseline_comparison:
        lines.append("")
        lines.append("## Mixed Party vs Pre-Barbarian Baseline")
        lines.append("| scenarioId | currentPlayerWinRate | baselinePlayerWinRate | delta |")
        lines.append("| --- | --- | --- | --- |")
        for entry in baseline_comparison:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(entry["scenarioId"]),
                        format_percent(float(entry["currentPlayerWinRate"])),
                        format_percent(float(entry["baselinePlayerWinRate"])),
                        f"{float(entry['playerWinRateDelta']) * 100:.1f} pts",
                    ]
                )
                + " |"
            )

    return "\n".join(lines)


__all__ = [
    "BARBARIAN_AUDIT_PLAYER_PRESET_IDS",
    "BarbarianAuditConfig",
    "BarbarianAuditRow",
    "BarbarianCounterTotals",
    "PresetAggregate",
    "audit_barbarian_pair",
    "audit_barbarian_profiles",
    "build_full_barbarian_audit_config",
    "build_fighter_trio_comparison",
    "build_mixed_party_baseline_comparison",
    "build_preset_aggregates",
    "build_quick_barbarian_audit_config",
    "build_report_payload",
    "extract_barbarian_run_metrics",
    "format_barbarian_audit_report",
    "get_barbarian_audit_player_preset_ids",
    "get_barbarian_audit_scenario_ids",
    "review_fixed_seed_replays",
]
