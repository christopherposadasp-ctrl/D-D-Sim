from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Literal

from backend.content.scenario_definitions import ACTIVE_SCENARIO_IDS, get_scenario_definition
from backend.engine import create_encounter, run_encounter, step_encounter, summarize_encounter
from backend.engine.ai.decision import (
    build_fighter_action_surge_dash_attack_decision,
    build_position_index,
    can_intentionally_provoke_opportunity_attack,
    find_preferred_adjacent_square,
    get_move_squares,
    get_player_primary_melee_weapon_id,
    get_smart_melee_attack_option,
    get_total_move_squares,
    sort_player_combat_targets,
    sort_player_melee_targets,
)
from backend.engine.combat.engine import run_batch_serial
from backend.engine.combat.setup import resolve_player_behavior
from backend.engine.models.state import BatchSummary, CombatEvent, EncounterConfig, RunEncounterResult, UnitState
from backend.engine.utils.helpers import get_units_by_faction, unit_sort_key

AuditStatus = Literal["pass", "warn", "fail"]
AuditProgressStage = Literal["replay", "behavior", "health", "comparison", "complete"]
FighterAuditProgressCallback = Callable[[str, AuditProgressStage, dict[str, object]], None]

FIGHTER_AUDIT_PLAYER_PRESET_IDS = ("fighter_level2_sample_trio", "martial_mixed_party")
STRESS_SCENARIO_IDS = {"marsh_predators"}


@dataclass(frozen=True)
class FighterAuditConfig:
    fixed_seed_runs: int = 5
    behavior_batch_size: int = 100
    health_batch_size: int = 300
    seed_prefix: str = "fighter-audit"


def build_quick_fighter_audit_config(seed_prefix: str = "fighter-audit") -> FighterAuditConfig:
    return FighterAuditConfig(
        fixed_seed_runs=1,
        behavior_batch_size=5,
        health_batch_size=15,
        seed_prefix=seed_prefix,
    )


def build_full_fighter_audit_config(seed_prefix: str = "fighter-audit") -> FighterAuditConfig:
    return FighterAuditConfig(seed_prefix=seed_prefix)


@dataclass
class FighterRunMetrics:
    opening_action_surge_opportunities: int = 0
    opening_action_surge_successes: int = 0
    action_surge_use_count: int = 0
    greatsword_attack_count: int = 0
    javelin_attack_count: int = 0
    turn_one_javelin_count: int = 0
    dash_action_surge_attack_count: int = 0
    double_melee_action_surge_turn_count: int = 0
    double_javelin_action_surge_turn_count: int = 0
    second_wind_use_count: int = 0
    fighter_downed_count: int = 0
    fighter_death_count: int = 0


@dataclass
class FighterCounterTotals:
    opening_action_surge_opportunities: int = 0
    opening_action_surge_successes: int = 0
    action_surge_use_count: int = 0
    greatsword_attack_count: int = 0
    javelin_attack_count: int = 0
    turn_one_javelin_count: int = 0
    dash_action_surge_attack_count: int = 0
    double_melee_action_surge_turn_count: int = 0
    double_javelin_action_surge_turn_count: int = 0
    second_wind_use_count: int = 0
    fighter_downed_count: int = 0
    fighter_death_count: int = 0

    def add_run(self, metrics: FighterRunMetrics) -> None:
        self.opening_action_surge_opportunities += metrics.opening_action_surge_opportunities
        self.opening_action_surge_successes += metrics.opening_action_surge_successes
        self.action_surge_use_count += metrics.action_surge_use_count
        self.greatsword_attack_count += metrics.greatsword_attack_count
        self.javelin_attack_count += metrics.javelin_attack_count
        self.turn_one_javelin_count += metrics.turn_one_javelin_count
        self.dash_action_surge_attack_count += metrics.dash_action_surge_attack_count
        self.double_melee_action_surge_turn_count += metrics.double_melee_action_surge_turn_count
        self.double_javelin_action_surge_turn_count += metrics.double_javelin_action_surge_turn_count
        self.second_wind_use_count += metrics.second_wind_use_count
        self.fighter_downed_count += metrics.fighter_downed_count
        self.fighter_death_count += metrics.fighter_death_count

    def opening_action_surge_rate(self) -> float:
        if self.opening_action_surge_opportunities <= 0:
            return 0.0
        return self.opening_action_surge_successes / self.opening_action_surge_opportunities


@dataclass
class FighterAuditRow:
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
    opening_action_surge_rate: float
    action_surge_use_count: int
    greatsword_attack_count: int
    javelin_attack_count: int
    turn_one_javelin_count: int
    dash_action_surge_attack_count: int
    double_melee_action_surge_turn_count: int
    double_javelin_action_surge_turn_count: int
    second_wind_use_count: int
    fighter_downed_count: int
    fighter_death_count: int
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
            "openingActionSurgeRate": self.opening_action_surge_rate,
            "actionSurgeUseCount": self.action_surge_use_count,
            "greatswordAttackCount": self.greatsword_attack_count,
            "javelinAttackCount": self.javelin_attack_count,
            "turnOneJavelinCount": self.turn_one_javelin_count,
            "dashActionSurgeAttackCount": self.dash_action_surge_attack_count,
            "doubleMeleeActionSurgeTurnCount": self.double_melee_action_surge_turn_count,
            "doubleJavelinActionSurgeTurnCount": self.double_javelin_action_surge_turn_count,
            "secondWindUseCount": self.second_wind_use_count,
            "fighterDownedCount": self.fighter_downed_count,
            "fighterDeathCount": self.fighter_death_count,
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
    callback: FighterAuditProgressCallback | None,
    label: str,
    stage: AuditProgressStage,
    details: dict[str, object] | None = None,
) -> None:
    if callback is None:
        return
    callback(label, stage, details or {})


def get_fighter_audit_player_preset_ids() -> tuple[str, ...]:
    return FIGHTER_AUDIT_PLAYER_PRESET_IDS


def get_fighter_audit_scenario_ids() -> tuple[str, ...]:
    return ACTIVE_SCENARIO_IDS


def get_fighter_unit_ids(units: dict[str, UnitState]) -> tuple[str, ...]:
    fighter_ids = [
        unit.id
        for unit in units.values()
        if unit.class_id == "fighter" and (unit.level or 0) >= 2
    ]
    return tuple(sorted(fighter_ids, key=unit_sort_key))


def is_level2_fighter(unit: UnitState) -> bool:
    return unit.class_id == "fighter" and (unit.level or 0) >= 2


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


def get_first_actor_event(turn_events: list[CombatEvent], actor_id: str) -> CombatEvent | None:
    for event in turn_events:
        if event.actor_id == actor_id and event.event_type != "turn_start":
            return event
    return None


def fighter_action_surge_event_present(turn_events: list[CombatEvent], actor_id: str) -> bool:
    return any(
        event.actor_id == actor_id
        and event.event_type == "phase_change"
        and "actionSurgeUsesRemaining" in event.resolved_totals
        for event in turn_events
    )


def get_actor_attack_events(turn_events: list[CombatEvent], actor_id: str) -> list[CombatEvent]:
    return [event for event in turn_events if event.actor_id == actor_id and event.event_type == "attack"]


def get_weapon_id(event: CombatEvent) -> str | None:
    if event.damage_details is None:
        return None
    return event.damage_details.weapon_id


def state_has_legal_fighter_melee_attack(state, actor: UnitState) -> bool:
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


def state_has_meaningful_fighter_dash_action_surge(state, actor: UnitState) -> bool:
    move_squares = get_move_squares(actor)
    dash_squares = get_total_move_squares(actor, 1)
    position_index = build_position_index(state)
    melee_weapon_id = get_player_primary_melee_weapon_id(actor)
    conscious_enemies = sort_player_combat_targets(
        state,
        actor,
        [unit for unit in get_units_by_faction(state, "goblins") if not unit.conditions.dead],
        state.player_behavior,
    )
    melee_targets = sort_player_melee_targets(state, actor, conscious_enemies, state.player_behavior)

    return (
        build_fighter_action_surge_dash_attack_decision(
            state,
            actor,
            melee_targets,
            melee_weapon_id,
            move_squares,
            dash_squares,
            position_index,
        )
        is not None
    )


def should_open_fighter_action_surge(state, actor: UnitState) -> bool:
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return False
    if actor.resources.action_surge_uses <= 0:
        return False
    if state_has_legal_fighter_melee_attack(state, actor):
        return True
    return state_has_meaningful_fighter_dash_action_surge(state, actor)


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


def extract_fighter_run_metrics(result: RunEncounterResult) -> FighterRunMetrics:
    metrics = FighterRunMetrics()
    fighter_ids = set(get_fighter_unit_ids(result.final_state.units))

    seen_first_turns: set[str] = set()
    for frame_index in range(1, len(result.replay_frames)):
        pre_turn_state = result.replay_frames[frame_index - 1].state
        frame = result.replay_frames[frame_index]
        actor_id = frame.active_combatant_id
        if actor_id not in fighter_ids or actor_id in seen_first_turns:
            continue

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
        pre_actor = pre_turn_state.units[actor_id]
        if should_open_fighter_action_surge(pre_turn_state, pre_actor):
            metrics.opening_action_surge_opportunities += 1
            if fighter_action_surge_event_present(turn_events, actor_id):
                metrics.opening_action_surge_successes += 1

    for event in result.events:
        if event.actor_id not in fighter_ids:
            continue

        if event.event_type == "phase_change" and "actionSurgeUsesRemaining" in event.resolved_totals:
            metrics.action_surge_use_count += 1
        if event.event_type == "heal":
            metrics.second_wind_use_count += 1
        if event.event_type == "attack" and event.damage_details:
            if event.damage_details.weapon_id == "greatsword":
                metrics.greatsword_attack_count += 1
            if event.damage_details.weapon_id == "javelin":
                metrics.javelin_attack_count += 1

    for actor_id, _, turn_events in get_turn_blocks(result.events):
        if actor_id not in fighter_ids:
            continue

        attack_events = get_actor_attack_events(turn_events, actor_id)
        if attack_events and attack_events[0].round == 1 and get_weapon_id(attack_events[0]) == "javelin":
            metrics.turn_one_javelin_count += 1
        if not fighter_action_surge_event_present(turn_events, actor_id):
            continue

        if any(
            event.actor_id == actor_id
            and event.event_type == "move"
            and event.resolved_totals.get("movementPhase") == "between_actions"
            for event in turn_events
        ) and any(event.damage_details and event.damage_details.weapon_id == "greatsword" for event in attack_events):
            metrics.dash_action_surge_attack_count += 1

        if sum(1 for event in attack_events if event.damage_details and event.damage_details.weapon_id == "greatsword") >= 2:
            metrics.double_melee_action_surge_turn_count += 1

        if sum(1 for event in attack_events if event.damage_details and event.damage_details.weapon_id == "javelin") >= 2:
            metrics.double_javelin_action_surge_turn_count += 1

    for unit_id in fighter_ids:
        unit = result.final_state.units[unit_id]
        if unit.conditions.dead:
            metrics.fighter_death_count += 1
        elif unit.current_hp == 0:
            metrics.fighter_downed_count += 1

    return metrics


def review_fixed_seed_replays(
    player_preset_id: str,
    scenario_id: str,
    config: FighterAuditConfig,
    progress_callback: FighterAuditProgressCallback | None = None,
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
                {"current": completed_runs, "total": total_runs, "playerBehavior": player_behavior},
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

                if not is_level2_fighter(actor):
                    continue

                pre_actor = pre_step_state.units[actor_id]
                actor_attack_events = get_actor_attack_events(turn_events, actor_id)
                used_action_surge = fighter_action_surge_event_present(turn_events, actor_id)

                if actor_id not in reviewed_opening_turns:
                    reviewed_opening_turns.add(actor_id)
                    if should_open_fighter_action_surge(pre_step_state, pre_actor) and not used_action_surge:
                        issues.append(
                            f"{encounter.seed}: {actor_id} skipped Action Surge on the first actionable turn."
                        )

                first_attack_event = actor_attack_events[0] if actor_attack_events else None
                javelin_attacks = [
                    event for event in actor_attack_events if get_weapon_id(event) == "javelin"
                ]
                if first_attack_event is not None and get_weapon_id(first_attack_event) == "javelin":
                    if state_has_legal_fighter_melee_attack(pre_step_state, pre_actor):
                        issues.append(f"{encounter.seed}: {actor_id} threw a javelin when a melee attack was available.")
                    elif state_has_meaningful_fighter_dash_action_surge(pre_step_state, pre_actor):
                        issues.append(
                            f"{encounter.seed}: {actor_id} threw a javelin when Dash plus Action Surge could reach melee."
                        )

                if used_action_surge and len(javelin_attacks) >= 2:
                    issues.append(f"{encounter.seed}: {actor_id} spent Action Surge on a double-javelin turn.")

                actor_finished_turn = encounter.units[actor_id]
                if (
                    used_action_surge
                    and not actor_attack_events
                    and actor_finished_turn.current_hp > 0
                    and not actor_finished_turn.conditions.dead
                    and not actor_finished_turn.conditions.unconscious
                ):
                    issues.append(f"{encounter.seed}: {actor_id} spent Action Surge without an attack follow-up.")

            completed_runs += 1
            emit_progress(
                progress_callback,
                label,
                "replay",
                {"current": completed_runs, "total": total_runs, "playerBehavior": player_behavior},
            )

    return issues, replay_seeds


def run_behavior_sanity_pass(
    player_preset_id: str,
    scenario_id: str,
    config: FighterAuditConfig,
    progress_callback: FighterAuditProgressCallback | None = None,
) -> tuple[FighterCounterTotals, dict[str, float]]:
    label = f"{player_preset_id}:{scenario_id}"
    totals = FighterCounterTotals()
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
                {"current": completed_runs, "total": total_runs, "playerBehavior": requested_player_behavior},
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
            totals.add_run(extract_fighter_run_metrics(result))
            completed_runs += 1
            emit_progress(
                progress_callback,
                label,
                "behavior",
                {"current": completed_runs, "total": total_runs, "playerBehavior": requested_player_behavior},
            )

        if config.behavior_batch_size > 0:
            behavior_win_rates[requested_player_behavior] = player_wins / config.behavior_batch_size
        else:
            behavior_win_rates[requested_player_behavior] = 0.0

    return totals, behavior_win_rates


def run_health_pass(
    player_preset_id: str,
    scenario_id: str,
    config: FighterAuditConfig,
    progress_callback: FighterAuditProgressCallback | None = None,
) -> BatchSummary:
    label = f"{player_preset_id}:{scenario_id}"

    def on_progress(completed_runs: int, total_runs: int, monster_behavior: str) -> None:
        emit_progress(
            progress_callback,
            label,
            "health",
            {"current": completed_runs, "total": total_runs, "monsterBehavior": monster_behavior},
        )

    seed = f"{config.seed_prefix}-{player_preset_id}-{scenario_id}-health"
    return run_batch_serial(
        EncounterConfig(
            seed=seed,
            enemy_preset_id=scenario_id,
            player_preset_id=player_preset_id,
            batch_size=config.health_batch_size,
            player_behavior="balanced",
            monster_behavior="combined",
        ),
        config.health_batch_size,
        "balanced",
        "combined",
        seed,
        on_progress if progress_callback else None,
    )


def build_row_warnings(
    scenario_id: str,
    summary: BatchSummary,
    counter_totals: FighterCounterTotals,
) -> list[str]:
    warnings: list[str] = []

    if (
        summary.smart_player_win_rate is not None
        and summary.dumb_player_win_rate is not None
        and float(summary.smart_player_win_rate) < float(summary.dumb_player_win_rate)
    ):
        warnings.append("Smart players underperformed dumb players in the combined pass.")

    if counter_totals.turn_one_javelin_count > 0:
        warnings.append("The Fighter opened with at least one round-1 javelin attack.")

    if counter_totals.action_surge_use_count == 0:
        warnings.append("No Action Surge uses were recorded in the behavior sanity pass.")

    if scenario_id not in STRESS_SCENARIO_IDS and counter_totals.greatsword_attack_count <= counter_totals.javelin_attack_count:
        warnings.append("Javelin volume matched or exceeded greatsword volume in a non-stress scenario.")

    return warnings


def build_row_recommendation(warnings: list[str], failures: list[str]) -> str | None:
    if any("javelin" in issue.lower() for issue in failures) or any("javelin" in issue.lower() for issue in warnings):
        return "Inspect melee-closure and Action Surge spend order before touching stats."

    if any("action surge" in issue.lower() for issue in failures):
        return "Inspect Action Surge trigger timing and between-action execution before touching numbers."

    if any("smart players underperformed dumb players" in issue.lower() for issue in warnings):
        return "Inspect flanking pathing and target ranking before touching numbers."

    return None


def determine_row_status(warnings: list[str], failures: list[str]) -> AuditStatus:
    if failures:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def audit_fighter_pair(
    player_preset_id: str,
    scenario_id: str,
    config: FighterAuditConfig | None = None,
    progress_callback: FighterAuditProgressCallback | None = None,
) -> FighterAuditRow:
    audit_config = config or FighterAuditConfig()
    scenario = get_scenario_definition(scenario_id)

    failures, replay_seeds = review_fixed_seed_replays(player_preset_id, scenario_id, audit_config, progress_callback)
    counter_totals, behavior_win_rates = run_behavior_sanity_pass(player_preset_id, scenario_id, audit_config, progress_callback)
    summary = run_health_pass(player_preset_id, scenario_id, audit_config, progress_callback)
    warnings = build_row_warnings(scenario_id, summary, counter_totals)
    recommendation = build_row_recommendation(warnings, failures)
    status = determine_row_status(warnings, failures)

    row = FighterAuditRow(
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
        opening_action_surge_rate=counter_totals.opening_action_surge_rate(),
        action_surge_use_count=counter_totals.action_surge_use_count,
        greatsword_attack_count=counter_totals.greatsword_attack_count,
        javelin_attack_count=counter_totals.javelin_attack_count,
        turn_one_javelin_count=counter_totals.turn_one_javelin_count,
        dash_action_surge_attack_count=counter_totals.dash_action_surge_attack_count,
        double_melee_action_surge_turn_count=counter_totals.double_melee_action_surge_turn_count,
        double_javelin_action_surge_turn_count=counter_totals.double_javelin_action_surge_turn_count,
        second_wind_use_count=counter_totals.second_wind_use_count,
        fighter_downed_count=counter_totals.fighter_downed_count,
        fighter_death_count=counter_totals.fighter_death_count,
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
        {"status": row.status, "warningCount": len(row.warnings), "failureCount": len(row.failures)},
    )
    return row


def audit_fighter_profiles(
    config: FighterAuditConfig | None = None,
    player_preset_ids: Iterable[str] | None = None,
    scenario_ids: Iterable[str] | None = None,
    progress_callback: FighterAuditProgressCallback | None = None,
) -> list[FighterAuditRow]:
    audit_config = config or FighterAuditConfig()
    selected_player_presets = tuple(player_preset_ids) if player_preset_ids is not None else FIGHTER_AUDIT_PLAYER_PRESET_IDS
    selected_scenarios = tuple(scenario_ids) if scenario_ids is not None else ACTIVE_SCENARIO_IDS

    rows: list[FighterAuditRow] = []
    for player_preset_id in selected_player_presets:
        for scenario_id in selected_scenarios:
            rows.append(audit_fighter_pair(player_preset_id, scenario_id, audit_config, progress_callback))
    return rows


def build_preset_aggregates(rows: list[FighterAuditRow]) -> list[PresetAggregate]:
    aggregates: list[PresetAggregate] = []

    for player_preset_id in FIGHTER_AUDIT_PLAYER_PRESET_IDS:
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


def build_level1_fighter_comparison(
    rows: list[FighterAuditRow],
    config: FighterAuditConfig,
    progress_callback: FighterAuditProgressCallback | None = None,
) -> list[dict[str, object]]:
    comparisons: list[dict[str, object]] = []
    scenario_ids = [
        scenario_id
        for scenario_id in ACTIVE_SCENARIO_IDS
        if any(row.player_preset_id == "fighter_level2_sample_trio" and row.scenario_id == scenario_id for row in rows)
    ]

    for scenario_id in scenario_ids:
        emit_progress(progress_callback, f"fighter-comparison:{scenario_id}", "comparison", {"status": "start"})
        level1_summary = run_health_pass("fighter_sample_trio", scenario_id, config, None)
        level2_row = next(
            row for row in rows if row.player_preset_id == "fighter_level2_sample_trio" and row.scenario_id == scenario_id
        )
        comparisons.append(
            {
                "scenarioId": scenario_id,
                "fighterLevel1PlayerWinRate": float(level1_summary.player_win_rate),
                "fighterLevel2PlayerWinRate": level2_row.player_win_rate,
                "playerWinRateDelta": level2_row.player_win_rate - float(level1_summary.player_win_rate),
                "fighterLevel1AverageRounds": float(level1_summary.average_rounds),
                "fighterLevel2AverageRounds": level2_row.average_rounds,
                "fighterLevel1AverageFighterDeaths": float(level1_summary.average_fighter_deaths),
                "fighterLevel2AverageFighterDeaths": level2_row.average_fighter_deaths,
            }
        )
        emit_progress(progress_callback, f"fighter-comparison:{scenario_id}", "comparison", {"status": "complete"})

    return comparisons


def build_report_payload(
    rows: list[FighterAuditRow],
    config: FighterAuditConfig,
    rules_gate: dict[str, object] | None = None,
    comparisons: dict[str, object] | None = None,
) -> dict[str, object]:
    aggregates = build_preset_aggregates(rows)
    overall_status: AuditStatus = "pass"
    if rules_gate and rules_gate.get("status") == "fail":
        overall_status = "fail"
    elif any(aggregate.status == "fail" for aggregate in aggregates):
        overall_status = "fail"
    elif any(row.status != "pass" for row in rows) or any(aggregate.status != "pass" for aggregate in aggregates):
        overall_status = "warn"

    comparison_payload = comparisons or {
        "fighterLevel2TrioVsFighterLevel1Trio": build_level1_fighter_comparison(rows, config),
    }

    return {
        "config": asdict(config),
        "rulesGate": rules_gate,
        "playerPresetIds": list(get_fighter_audit_player_preset_ids()),
        "scenarioIds": list(get_fighter_audit_scenario_ids()),
        "overallStatus": overall_status,
        "rows": [row.to_report_dict() for row in rows],
        "presetAggregates": [aggregate.to_report_dict() for aggregate in aggregates],
        "comparisons": comparison_payload,
    }


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def format_fighter_audit_report(
    rows: list[FighterAuditRow],
    aggregates: list[PresetAggregate],
    rules_gate: dict[str, object] | None = None,
    fighter_comparison: list[dict[str, object]] | None = None,
) -> str:
    lines: list[str] = []

    if rules_gate:
        lines.append("## Rules Gate")
        lines.append(f"- Status: {rules_gate.get('status', 'unknown')}")
        lines.append(f"- Command: `{rules_gate.get('command', '')}`")
        if rules_gate.get("status") == "fail":
            for entry in rules_gate.get("stdoutTail", []):
                if isinstance(entry, str):
                    lines.append(f"- {entry}")
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
        "| playerPresetId | scenarioId | playerWinRate | smartPlayerWinRate | dumbPlayerWinRate | averageRounds | openingActionSurgeRate | greatswordAttacks | javelinAttacks | actionSurgeUses | status | recommendation |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
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
                    format_percent(row.opening_action_surge_rate),
                    str(row.greatsword_attack_count),
                    str(row.javelin_attack_count),
                    str(row.action_surge_use_count),
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
        lines.append("## Fighter Level 2 Trio vs Level 1 Fighter Trio")
        lines.append("| scenarioId | fighterLevel2PlayerWinRate | fighterLevel1PlayerWinRate | delta |")
        lines.append("| --- | --- | --- | --- |")
        for entry in fighter_comparison:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(entry["scenarioId"]),
                        format_percent(float(entry["fighterLevel2PlayerWinRate"])),
                        format_percent(float(entry["fighterLevel1PlayerWinRate"])),
                        f"{float(entry['playerWinRateDelta']) * 100:.1f} pts",
                    ]
                )
                + " |"
            )

    return "\n".join(lines)


__all__ = [
    "FIGHTER_AUDIT_PLAYER_PRESET_IDS",
    "FighterAuditConfig",
    "FighterAuditRow",
    "FighterCounterTotals",
    "PresetAggregate",
    "audit_fighter_pair",
    "audit_fighter_profiles",
    "build_full_fighter_audit_config",
    "build_level1_fighter_comparison",
    "build_preset_aggregates",
    "build_quick_fighter_audit_config",
    "build_report_payload",
    "extract_fighter_run_metrics",
    "format_fighter_audit_report",
    "get_fighter_audit_player_preset_ids",
    "get_fighter_audit_scenario_ids",
    "review_fixed_seed_replays",
]
