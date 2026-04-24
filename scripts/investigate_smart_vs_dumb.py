from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.player_loadouts import get_player_primary_melee_weapon_id
from backend.engine import run_encounter
from backend.engine.ai.decision import (
    MeleeAttackOption,
    TurnDecision,
    build_melee_attack_options,
    build_repeated_weapon_step_profiles,
    build_smart_target_priority,
    choose_turn_decision,
    classify_target_kill_band,
    count_adjacent_allied_units,
    get_attack_range_squares,
    get_distance_between_units,
    get_move_squares,
    get_remaining_move_squares_after_primary_action,
    get_target_immediacy,
    get_target_threat_tier,
    get_total_move_squares,
    is_player_fighter,
    is_player_melee_opportunist,
    sort_player_melee_targets,
)
from backend.engine.combat.engine import run_encounter_summary_fast, summarize_encounter
from backend.engine.constants import MONSTER_BEHAVIORS
from backend.engine.models.state import (
    CombatEvent,
    EncounterConfig,
    EncounterState,
    EncounterSummary,
    GridPosition,
    RunEncounterResult,
    UnitState,
)
from backend.engine.rules.spatial import (
    build_position_index,
    get_min_chebyshev_distance_between_footprints,
    get_unit_footprint,
)
from backend.engine.utils.helpers import get_units_by_faction, is_unit_conscious, unit_sort_key

AuditClass = Literal["fighter", "barbarian"]
PlayerBehavior = Literal["smart", "dumb"]
MonsterBehaviorArg = Literal["kind", "balanced", "evil", "combined"]

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pass1" / "behavior_diagnostics"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "smart_vs_dumb_diagnostics_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "smart_vs_dumb_diagnostics_latest.md"
INVERSION_THRESHOLD = -0.05


@dataclass(frozen=True)
class DiagnosticRow:
    audit_class: AuditClass
    player_preset_id: str
    scenario_id: str

    @property
    def label(self) -> str:
        return f"{self.audit_class}:{self.player_preset_id}:{self.scenario_id}"


PRIORITY_ROWS: tuple[DiagnosticRow, ...] = (
    DiagnosticRow("fighter", "martial_mixed_party", "orc_push"),
    DiagnosticRow("fighter", "martial_mixed_party", "predator_rampage"),
    DiagnosticRow("barbarian", "barbarian_level2_sample_trio", "mixed_patrol"),
    DiagnosticRow("fighter", "fighter_level2_sample_trio", "mixed_patrol"),
    DiagnosticRow("barbarian", "martial_mixed_party", "wolf_harriers"),
    DiagnosticRow("barbarian", "barbarian_level2_sample_trio", "predator_rampage"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare paired smart/dumb encounter behavior for Pass 1 behavior failures."
    )
    parser.add_argument("--priority-set", choices=("top6",), default=None)
    parser.add_argument("--class", choices=("fighter", "barbarian"), dest="audit_class", default=None)
    parser.add_argument("--player-preset", dest="player_preset_id", default=None)
    parser.add_argument("--scenario", dest="scenario_id", default=None)
    parser.add_argument("--monster-behavior", choices=("kind", "balanced", "evil", "combined"), default="combined")
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--detail-limit", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="Print the final JSON payload to stdout.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    parser.add_argument("--no-report", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.sample_size < 1:
        raise SystemExit("--sample-size must be at least 1.")
    if args.detail_limit < 0:
        raise SystemExit("--detail-limit must be non-negative.")
    if args.priority_set:
        return
    missing = [
        name
        for name, value in (
            ("--class", args.audit_class),
            ("--player-preset", args.player_preset_id),
            ("--scenario", args.scenario_id),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required argument(s) for a single-row diagnostic: {', '.join(missing)}")


def get_rows(args: argparse.Namespace) -> tuple[DiagnosticRow, ...]:
    if args.priority_set == "top6":
        return PRIORITY_ROWS
    return (DiagnosticRow(args.audit_class, args.player_preset_id, args.scenario_id),)


def get_monster_behaviors(requested_behavior: MonsterBehaviorArg) -> tuple[str, ...]:
    if requested_behavior == "combined":
        return tuple(MONSTER_BEHAVIORS)
    return (requested_behavior,)


def build_pair_seed(row: DiagnosticRow, monster_behavior: str, run_index: int) -> str:
    return f"behavior-diagnostic-{row.audit_class}-{row.player_preset_id}-{row.scenario_id}-{monster_behavior}-{run_index:03d}"


def build_config(
    row: DiagnosticRow,
    monster_behavior: str,
    player_behavior: PlayerBehavior,
    run_index: int,
) -> EncounterConfig:
    return EncounterConfig(
        seed=build_pair_seed(row, monster_behavior, run_index),
        enemy_preset_id=row.scenario_id,
        player_preset_id=row.player_preset_id,
        player_behavior=player_behavior,
        monster_behavior=monster_behavior,
    )


def is_player_win(summary: EncounterSummary) -> bool:
    return summary.winner == "fighters"


def summarize_fast_run(row: DiagnosticRow, monster_behavior: str, player_behavior: PlayerBehavior, run_index: int) -> dict:
    started = time.perf_counter()
    config = build_config(row, monster_behavior, player_behavior, run_index)
    summary = run_encounter_summary_fast(config)
    return {
        "seed": summary.seed,
        "playerBehavior": player_behavior,
        "monsterBehavior": monster_behavior,
        "runIndex": run_index,
        "winner": summary.winner,
        "playerWon": is_player_win(summary),
        "rounds": summary.rounds,
        "fighterDeaths": summary.fighter_deaths,
        "goblinsKilled": summary.goblins_killed,
        "remainingFighterHp": summary.remaining_fighter_hp,
        "remainingMonsterHp": summary.remaining_goblin_hp,
        "elapsedSeconds": round(time.perf_counter() - started, 4),
    }


def position_payload(position: GridPosition | None) -> dict[str, int] | None:
    return position.model_dump() if position else None


def movement_payload(path: list[GridPosition] | None, mode: str | None = None) -> dict | None:
    if not path:
        return None
    return {
        "mode": mode,
        "distance": max(0, len(path) - 1),
        "path": [position_payload(point) for point in path],
    }


def unit_payload(unit: UnitState) -> dict:
    return {
        "id": unit.id,
        "faction": unit.faction,
        "classId": unit.class_id,
        "hp": unit.current_hp,
        "maxHp": unit.max_hp,
        "temporaryHp": unit.temporary_hit_points,
        "dead": unit.conditions.dead,
        "unconscious": unit.conditions.unconscious,
        "prone": unit.conditions.prone,
        "position": position_payload(unit.position),
        "rageActive": any(effect.kind == "rage" for effect in unit.temporary_effects),
    }


def distance_between_units(actor: UnitState, target: UnitState) -> int | None:
    if not actor.position or not target.position:
        return None
    return max(abs(actor.position.x - target.position.x), abs(actor.position.y - target.position.y))


def adjacent_enemy_ids(state: EncounterState, actor_id: str) -> list[str]:
    actor = state.units.get(actor_id)
    if not actor or not actor.position:
        return []
    return [
        enemy.id
        for enemy in get_units_by_faction(state, "goblins" if actor.faction == "fighters" else "fighters")
        if enemy.position
        and not enemy.conditions.dead
        and enemy.current_hp > 0
        and distance_between_units(actor, enemy) is not None
        and distance_between_units(actor, enemy) <= 1
    ]


def event_payload(event: CombatEvent) -> dict:
    payload: dict[str, object] = {
        "round": event.round,
        "actorId": event.actor_id,
        "targetIds": list(event.target_ids),
        "type": event.event_type,
        "text": event.text_summary,
    }
    if event.event_type == "move" and event.movement_details:
        payload["movement"] = {
            "phase": event.resolved_totals.get("movementPhase"),
            "mode": event.resolved_totals.get("movementMode"),
            "distance": event.movement_details.distance,
            "start": position_payload(event.movement_details.start),
            "end": position_payload(event.movement_details.end),
            "path": [position_payload(point) for point in event.movement_details.path or []],
            "opportunityAttackers": event.resolved_totals.get("opportunityAttackers", []),
        }
    if event.event_type == "attack":
        payload["attack"] = {
            "weaponId": event.damage_details.weapon_id if event.damage_details else None,
            "hit": event.resolved_totals.get("hit"),
            "critical": event.resolved_totals.get("critical"),
            "damage": event.damage_details.final_damage_to_hp if event.damage_details else 0,
            "advantageSources": event.raw_rolls.get("advantageSources", []),
            "disadvantageSources": event.raw_rolls.get("disadvantageSources", []),
            "opportunityAttack": event.resolved_totals.get("opportunityAttack", False),
        }
    if event.event_type == "phase_change":
        phase_text = event.text_summary.lower()
        if "rage" in phase_text or "action surge" in phase_text:
            payload["resourceEvent"] = event.text_summary
    if event.condition_deltas:
        payload["conditionDeltas"] = list(event.condition_deltas)
    return payload


def turn_payload(result: RunEncounterResult, frame_index: int) -> dict:
    frame = result.replay_frames[frame_index]
    actor_id = frame.active_combatant_id
    actor = frame.state.units.get(actor_id)
    return {
        "frameIndex": frame.index,
        "round": frame.round,
        "actorId": actor_id,
        "actorFaction": actor.faction if actor else None,
        "events": [event_payload(event) for event in frame.events],
        "endingAdjacentEnemies": adjacent_enemy_ids(frame.state, actor_id),
    }


def classify_delta(delta: float, smart_loss_dumb_win: int, smart_win_dumb_loss: int) -> str:
    if delta <= INVERSION_THRESHOLD and smart_loss_dumb_win > smart_win_dumb_loss:
        return "confirmed_inversion"
    if delta < 0:
        return "needs_confirmation"
    return "no_inversion"


def summarize_pair_results(run_pairs: list[dict]) -> dict:
    smart_wins = sum(1 for pair in run_pairs if pair["smart"]["playerWon"])
    dumb_wins = sum(1 for pair in run_pairs if pair["dumb"]["playerWon"])
    smart_loss_dumb_win = sum(1 for pair in run_pairs if not pair["smart"]["playerWon"] and pair["dumb"]["playerWon"])
    smart_win_dumb_loss = sum(1 for pair in run_pairs if pair["smart"]["playerWon"] and not pair["dumb"]["playerWon"])
    both_win = sum(1 for pair in run_pairs if pair["smart"]["playerWon"] and pair["dumb"]["playerWon"])
    both_loss = sum(1 for pair in run_pairs if not pair["smart"]["playerWon"] and not pair["dumb"]["playerWon"])
    total = len(run_pairs)
    smart_win_rate = smart_wins / total if total else 0.0
    dumb_win_rate = dumb_wins / total if total else 0.0
    delta = smart_win_rate - dumb_win_rate
    return {
        "totalPairs": total,
        "smartWinRate": smart_win_rate,
        "dumbWinRate": dumb_win_rate,
        "delta": delta,
        "smartLossDumbWin": smart_loss_dumb_win,
        "smartWinDumbLoss": smart_win_dumb_loss,
        "bothWin": both_win,
        "bothLoss": both_loss,
        "classification": classify_delta(delta, smart_loss_dumb_win, smart_win_dumb_loss),
    }


def kill_band_label(score: int) -> str:
    if score >= 2:
        return "sure_finish"
    if score == 1:
        return "probable_finish"
    return "none"


def positions_match(left: GridPosition | None, right: GridPosition | None) -> bool:
    return bool(left and right and left.x == right.x and left.y == right.y)


def distance_from_square_to_unit(square_position: GridPosition, moving_unit: UnitState, target: UnitState) -> int | None:
    if not target.position:
        return None
    return get_min_chebyshev_distance_between_footprints(
        square_position,
        get_unit_footprint(moving_unit),
        target.position,
        get_unit_footprint(target),
    )


def count_adjacent_units_after_move(
    state: EncounterState,
    actor: UnitState,
    square_position: GridPosition,
    faction: str,
) -> int:
    return len(
        [
            unit
            for unit in get_units_by_faction(state, faction)
            if unit.id != actor.id
            and is_unit_conscious(unit)
            and unit.position
            and (distance := distance_from_square_to_unit(square_position, actor, unit)) is not None
            and distance <= 1
        ]
    )


def get_pressuring_enemy_ids_next_turn(state: EncounterState, actor: UnitState, square_position: GridPosition) -> list[str]:
    threatened_faction = "goblins" if actor.faction == "fighters" else "fighters"
    pressuring_ids: list[str] = []
    for enemy in get_units_by_faction(state, threatened_faction):
        if not is_unit_conscious(enemy) or not enemy.position:
            continue
        distance = distance_from_square_to_unit(square_position, actor, enemy)
        if distance is None:
            continue
        if any(distance <= get_move_squares(enemy, state) + get_attack_range_squares(weapon) for weapon in enemy.attacks.values()):
            pressuring_ids.append(enemy.id)
    return pressuring_ids


def build_target_priority_payload(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    melee_weapon_id: str,
    *,
    attacker_position: GridPosition | None = None,
    position_index=None,
    rank: int | None = None,
) -> dict:
    attack_step_weapon_profiles = build_repeated_weapon_step_profiles(actor, melee_weapon_id)
    kill_band, kill_probability = classify_target_kill_band(
        state,
        actor,
        target,
        attack_step_weapon_profiles,
        preferred_weapon_id=melee_weapon_id,
        attacker_position=attacker_position,
        target_position=target.position,
        position_index=position_index,
    )
    immediacy = get_target_immediacy(state, actor, target)
    threat_tier = get_target_threat_tier(state, actor, target, immediacy)
    allied_pressure = count_adjacent_allied_units(state, actor, target)
    priority_tuple = build_smart_target_priority(
        state,
        actor,
        target,
        attack_step_weapon_profiles=attack_step_weapon_profiles,
        preferred_weapon_id=melee_weapon_id,
        attacker_position=attacker_position,
        target_position=target.position,
        position_index=position_index,
    )
    payload = {
        "targetId": target.id,
        "currentHp": target.current_hp,
        "distance": get_distance_between_units(actor, target),
        "killBand": kill_band_label(kill_band),
        "killBandScore": kill_band,
        "killProbability": round(kill_probability, 4),
        "threatTier": threat_tier,
        "immediacy": immediacy,
        "alliedPressure": allied_pressure,
        "priorityTuple": list(priority_tuple),
    }
    if rank is not None:
        payload["rank"] = rank
    return payload


def build_melee_option_sort_key(
    state: EncounterState,
    actor: UnitState,
    option: MeleeAttackOption,
    melee_weapon_id: str,
    position_index=None,
) -> tuple[int, int, int, int, int, int, float, int, str, int, int]:
    attack_step_weapon_profiles = build_repeated_weapon_step_profiles(actor, melee_weapon_id)
    target_priority = build_smart_target_priority(
        state,
        actor,
        option.target,
        attack_step_weapon_profiles=attack_step_weapon_profiles,
        preferred_weapon_id=melee_weapon_id,
        attacker_position=option.path[-1],
        target_position=option.target.position,
        position_index=position_index,
    )
    return (
        target_priority[0],
        target_priority[1],
        -option.adjacent_allies if is_player_melee_opportunist(actor) else 0,
        option.distance,
        -int(option.creates_flank),
        target_priority[2],
        target_priority[3],
        target_priority[4],
        target_priority[5],
        option.target.id,
        option.path[-1].x,
        option.path[-1].y,
    )


def build_ranked_melee_options(
    state: EncounterState,
    actor: UnitState,
    targets: list[UnitState],
    move_squares: int,
    melee_weapon_id: str,
    position_index=None,
) -> list[MeleeAttackOption]:
    options = build_melee_attack_options(state, actor, targets, move_squares, melee_weapon_id, True, position_index)
    return sorted(
        options,
        key=lambda option: build_melee_option_sort_key(state, actor, option, melee_weapon_id, position_index),
    )


def build_square_option_payload(
    state: EncounterState,
    actor: UnitState,
    option: MeleeAttackOption,
    melee_weapon_id: str,
    *,
    position_index=None,
    rank: int | None = None,
) -> dict:
    end_position = option.path[-1]
    pressuring_enemy_ids = get_pressuring_enemy_ids_next_turn(state, actor, end_position)
    payload = {
        "targetId": option.target.id,
        "endPosition": position_payload(end_position),
        "moveDistance": option.distance,
        "createsFlank": option.creates_flank,
        "adjacentEnemyCountAfterMove": count_adjacent_units_after_move(state, actor, end_position, "goblins" if actor.faction == "fighters" else "fighters"),
        "adjacentAllyCountAfterMove": count_adjacent_units_after_move(state, actor, end_position, actor.faction),
        "pressuredImmediatelyNextMonsterTurn": bool(pressuring_enemy_ids),
        "pressuringEnemyIdsNextTurn": pressuring_enemy_ids,
        "targetMetrics": build_target_priority_payload(
            state,
            actor,
            option.target,
            melee_weapon_id,
            attacker_position=end_position,
            position_index=position_index,
        ),
    }
    if rank is not None:
        payload["rank"] = rank
    return payload


def build_manual_square_payload(
    state: EncounterState,
    actor: UnitState,
    target: UnitState | None,
    square_position: GridPosition,
    melee_weapon_id: str,
    *,
    move_distance: int,
    creates_flank: bool,
    position_index=None,
) -> dict:
    payload = {
        "targetId": target.id if target else None,
        "endPosition": position_payload(square_position),
        "moveDistance": move_distance,
        "createsFlank": creates_flank,
        "adjacentEnemyCountAfterMove": count_adjacent_units_after_move(state, actor, square_position, "goblins" if actor.faction == "fighters" else "fighters"),
        "adjacentAllyCountAfterMove": count_adjacent_units_after_move(state, actor, square_position, actor.faction),
        "pressuredImmediatelyNextMonsterTurn": False,
        "pressuringEnemyIdsNextTurn": [],
        "targetMetrics": None,
    }
    pressuring_enemy_ids = get_pressuring_enemy_ids_next_turn(state, actor, square_position)
    payload["pressuredImmediatelyNextMonsterTurn"] = bool(pressuring_enemy_ids)
    payload["pressuringEnemyIdsNextTurn"] = pressuring_enemy_ids
    if target:
        payload["targetMetrics"] = build_target_priority_payload(
            state,
            actor,
            target,
            melee_weapon_id,
            attacker_position=square_position,
            position_index=position_index,
        )
    return payload


def pick_square_payloads(
    ranked_options: list[MeleeAttackOption],
    state: EncounterState,
    actor: UnitState,
    melee_weapon_id: str,
    chosen_target_id: str | None,
    chosen_end_position: GridPosition | None,
    *,
    position_index=None,
) -> tuple[dict | None, list[dict]]:
    chosen_index = None
    for index, option in enumerate(ranked_options):
        if option.target.id == chosen_target_id and positions_match(option.path[-1], chosen_end_position):
            chosen_index = index
            break

    chosen_square = None
    if chosen_index is not None:
        chosen_square = build_square_option_payload(
            state,
            actor,
            ranked_options[chosen_index],
            melee_weapon_id,
            position_index=position_index,
            rank=chosen_index + 1,
        )

    rejected_squares: list[dict] = []
    for index, option in enumerate(ranked_options):
        if chosen_index is not None and index == chosen_index:
            continue
        rejected_squares.append(
            build_square_option_payload(
                state,
                actor,
                option,
                melee_weapon_id,
                position_index=position_index,
                rank=index + 1,
            )
        )
        if len(rejected_squares) >= 2:
            break
    return chosen_square, rejected_squares


def serialize_turn_decision(decision: TurnDecision) -> dict:
    return {
        "action": decision.action,
        "bonusAction": decision.bonus_action,
        "preActionMovement": movement_payload(decision.pre_action_movement.path, decision.pre_action_movement.mode)
        if decision.pre_action_movement
        else None,
        "betweenActionMovement": movement_payload(decision.between_action_movement.path, decision.between_action_movement.mode)
        if decision.between_action_movement
        else None,
        "surgedAction": decision.surged_action,
        "postActionMovement": movement_payload(decision.post_action_movement.path, decision.post_action_movement.mode)
        if decision.post_action_movement
        else None,
    }


def capture_action_surge_turn_evidence(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    melee_targets: list[UnitState],
    melee_weapon_id: str,
    position_index=None,
) -> dict | None:
    if not decision.surged_action:
        return None

    if decision.action["kind"] == "attack":
        target = state.units.get(decision.action["target_id"])
        if not target:
            return None
        remaining_move_squares = get_remaining_move_squares_after_primary_action(state, actor, decision)
        flanking_options = [
            option
            for option in build_melee_attack_options(
                state,
                actor,
                [target],
                remaining_move_squares,
                melee_weapon_id,
                True,
                position_index,
            )
            if option.distance > 0 and option.creates_flank
        ]
        ranked_options = sorted(
            flanking_options,
            key=lambda option: (
                option.distance,
                -option.adjacent_allies,
                option.path[-1].x,
                option.path[-1].y,
            ),
        )
        chosen_end_position = decision.between_action_movement.path[-1] if decision.between_action_movement else None
        chosen_square, rejected_squares = pick_square_payloads(
            ranked_options,
            state,
            actor,
            melee_weapon_id,
            target.id,
            chosen_end_position,
            position_index=position_index,
        )
        return {
            "mode": "reposition_after_attack",
            "surgedTargetId": decision.surged_action["target_id"],
            "remainingMoveSquares": remaining_move_squares,
            "chosenSquare": chosen_square,
            "rejectedSquares": rejected_squares,
        }

    dash_squares = get_total_move_squares(actor, 1, state=state)
    ranked_options = build_ranked_melee_options(state, actor, melee_targets, dash_squares, melee_weapon_id, position_index)
    chosen_end_position = decision.between_action_movement.path[-1] if decision.between_action_movement else actor.position
    chosen_square, rejected_squares = pick_square_payloads(
        ranked_options,
        state,
        actor,
        melee_weapon_id,
        decision.surged_action["target_id"],
        chosen_end_position,
        position_index=position_index,
    )
    if chosen_square is None and chosen_end_position:
        chosen_target = state.units.get(decision.surged_action["target_id"])
        chosen_square = build_manual_square_payload(
            state,
            actor,
            chosen_target,
            chosen_end_position,
            melee_weapon_id,
            move_distance=max(0, len(decision.between_action_movement.path) - 1) if decision.between_action_movement else 0,
            creates_flank=False,
            position_index=position_index,
        )
    return {
        "mode": "dash_attack",
        "surgedTargetId": decision.surged_action["target_id"],
        "remainingMoveSquares": dash_squares,
        "chosenSquare": chosen_square,
        "rejectedSquares": rejected_squares,
    }


def capture_turn_decision_evidence(state: EncounterState, actor_id: str) -> dict | None:
    working_state = state.model_copy(deep=True)
    actor = working_state.units.get(actor_id)
    if not actor or actor.faction != "fighters" or not is_player_fighter(actor):
        return None

    decision = choose_turn_decision(working_state, actor_id)
    if decision.action["kind"] == "skip":
        return None

    actor = working_state.units[actor_id]
    position_index = build_position_index(working_state)
    melee_weapon_id = get_player_primary_melee_weapon_id(actor)
    conscious_enemies = [unit for unit in get_units_by_faction(working_state, "goblins") if not unit.conditions.dead]
    melee_targets = sort_player_melee_targets(
        working_state,
        actor,
        conscious_enemies,
        working_state.player_behavior,
        melee_weapon_id=melee_weapon_id,
        position_index=position_index,
    )
    top_target_alternatives = [
        build_target_priority_payload(
            working_state,
            actor,
            target,
            melee_weapon_id,
            position_index=position_index,
            rank=index + 1,
        )
        for index, target in enumerate(melee_targets[:3])
    ]

    move_squares = get_move_squares(actor, working_state)
    dash_squares = get_total_move_squares(actor, 1, state=working_state)
    using_dash_attack = bool(decision.surged_action and decision.action["kind"] == "dash")
    move_budget = dash_squares if using_dash_attack else move_squares
    ranked_options = build_ranked_melee_options(
        working_state,
        actor,
        melee_targets,
        move_budget,
        melee_weapon_id,
        position_index,
    )

    chosen_target_id = decision.surged_action["target_id"] if decision.surged_action else decision.action.get("target_id")
    chosen_end_position = actor.position
    if using_dash_attack and decision.between_action_movement:
        chosen_end_position = decision.between_action_movement.path[-1]
    elif decision.pre_action_movement:
        chosen_end_position = decision.pre_action_movement.path[-1]

    chosen_square, rejected_squares = pick_square_payloads(
        ranked_options,
        working_state,
        actor,
        melee_weapon_id,
        chosen_target_id,
        chosen_end_position,
        position_index=position_index,
    )

    if chosen_square is None and chosen_end_position:
        chosen_target = working_state.units.get(chosen_target_id) if chosen_target_id else None
        chosen_square = build_manual_square_payload(
            working_state,
            actor,
            chosen_target,
            chosen_end_position,
            melee_weapon_id,
            move_distance=max(0, len(decision.pre_action_movement.path) - 1) if decision.pre_action_movement else 0,
            creates_flank=False,
            position_index=position_index,
        )

    return {
        "actorId": actor_id,
        "decision": serialize_turn_decision(decision),
        "chosenTargetId": chosen_target_id,
        "topTargetAlternatives": top_target_alternatives,
        "chosenSquare": chosen_square,
        "rejectedSquares": rejected_squares,
        "actionSurgeTurn": capture_action_surge_turn_evidence(
            working_state,
            actor,
            decision,
            melee_targets,
            melee_weapon_id,
            position_index=position_index,
        ),
    }


def capture_fighter_decision_trace(result: RunEncounterResult) -> dict | None:
    first_actionable_turn = None
    first_action_surge_turn = None
    for frame_index in range(1, len(result.replay_frames)):
        actor_id = result.replay_frames[frame_index].active_combatant_id
        pre_turn_state = result.replay_frames[frame_index - 1].state
        actor = pre_turn_state.units.get(actor_id)
        if not actor or actor.faction != "fighters" or not is_player_fighter(actor):
            continue
        evidence = capture_turn_decision_evidence(pre_turn_state, actor_id)
        if not evidence:
            continue
        evidence["frameIndex"] = frame_index
        evidence["round"] = result.replay_frames[frame_index].round
        if first_actionable_turn is None:
            first_actionable_turn = evidence
        if evidence["decision"]["surgedAction"] is not None and first_action_surge_turn is None:
            first_action_surge_turn = evidence
        if first_actionable_turn is not None and first_action_surge_turn is not None:
            break
    if first_actionable_turn is None and first_action_surge_turn is None:
        return None
    return {
        "firstActionableTurn": first_actionable_turn,
        "firstActionSurgeTurn": first_action_surge_turn,
    }


def capture_detailed_run(row: DiagnosticRow, monster_behavior: str, player_behavior: PlayerBehavior, run_index: int) -> dict:
    started = time.perf_counter()
    result = run_encounter(build_config(row, monster_behavior, player_behavior, run_index))
    summary = summarize_encounter(result.final_state)
    first_two_round_turns = [
        turn_payload(result, frame_index)
        for frame_index in range(1, len(result.replay_frames))
        if result.replay_frames[frame_index].round <= 2
    ]
    final_units = sorted(result.final_state.units.values(), key=lambda unit: unit_sort_key(unit.id))
    return {
        "seed": summary.seed,
        "playerBehavior": player_behavior,
        "monsterBehavior": monster_behavior,
        "runIndex": run_index,
        "winner": summary.winner,
        "playerWon": is_player_win(summary),
        "rounds": summary.rounds,
        "fighterDeaths": summary.fighter_deaths,
        "goblinsKilled": summary.goblins_killed,
        "remainingFighterHp": summary.remaining_fighter_hp,
        "remainingMonsterHp": summary.remaining_goblin_hp,
        "eventCount": len(result.events),
        "replayFrameCount": len(result.replay_frames),
        "firstTwoRoundTurns": first_two_round_turns,
        "fighterDecisionEvidence": capture_fighter_decision_trace(result) if row.audit_class == "fighter" else None,
        "finalUnits": [unit_payload(unit) for unit in final_units],
        "elapsedSeconds": round(time.perf_counter() - started, 4),
    }


def capture_pair_detail(
    row: DiagnosticRow,
    monster_behavior: str,
    run_index: int,
) -> dict:
    return {
        "pairSeed": build_pair_seed(row, monster_behavior, run_index),
        "runIndex": run_index,
        "smart": capture_detailed_run(row, monster_behavior, "smart", run_index),
        "dumb": capture_detailed_run(row, monster_behavior, "dumb", run_index),
    }


def diagnose_row(row: DiagnosticRow, monster_behavior: str, sample_size: int, detail_limit: int) -> dict:
    print(f"Diagnosing {row.label} vs {monster_behavior} monsters ({sample_size} pair(s))...")
    run_pairs: list[dict] = []
    mismatch_details: list[dict] = []
    counterexample_details: list[dict] = []
    for run_index in range(sample_size):
        smart = summarize_fast_run(row, monster_behavior, "smart", run_index)
        dumb = summarize_fast_run(row, monster_behavior, "dumb", run_index)
        pair = {
            "pairSeed": build_pair_seed(row, monster_behavior, run_index),
            "runIndex": run_index,
            "smart": smart,
            "dumb": dumb,
        }
        run_pairs.append(pair)
        if not smart["playerWon"] and dumb["playerWon"] and len(mismatch_details) < detail_limit:
            mismatch_details.append(capture_pair_detail(row, monster_behavior, run_index))
        elif smart["playerWon"] and not dumb["playerWon"] and not counterexample_details:
            counterexample_details.append(capture_pair_detail(row, monster_behavior, run_index))

    summary = summarize_pair_results(run_pairs)
    return {
        "class": row.audit_class,
        "playerPresetId": row.player_preset_id,
        "scenarioId": row.scenario_id,
        "monsterBehavior": monster_behavior,
        **summary,
        "mismatchDetailCount": len(mismatch_details),
        "counterexampleDetailCount": len(counterexample_details),
        "details": mismatch_details,
        "counterexampleDetails": counterexample_details,
    }


def build_overall_status(results: list[dict]) -> str:
    if any(result["classification"] == "confirmed_inversion" for result in results):
        return "fail"
    if any(result["classification"] == "needs_confirmation" for result in results):
        return "warn"
    return "pass"


def build_payload(args: argparse.Namespace) -> dict:
    rows = get_rows(args)
    monster_behaviors = get_monster_behaviors(args.monster_behavior)
    results: list[dict] = []
    started = time.perf_counter()
    for row in rows:
        for monster_behavior in monster_behaviors:
            results.append(diagnose_row(row, monster_behavior, args.sample_size, args.detail_limit))
    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "sampleSize": args.sample_size,
        "detailLimit": args.detail_limit,
        "requestedMonsterBehavior": args.monster_behavior,
        "overallStatus": build_overall_status(results),
        "elapsedSeconds": round(time.perf_counter() - started, 3),
        "results": results,
    }


def format_rate(value: float) -> str:
    return f"{value:.3f}"


def format_square_summary(square: dict | None) -> str:
    if not square:
        return "n/a"
    target_id = square.get("targetId") or "?"
    end_position = square.get("endPosition") or {}
    return f"{target_id}@({end_position.get('x')},{end_position.get('y')})"


def format_markdown(payload: dict) -> str:
    lines = [
        "# Smart vs Dumb Behavior Diagnostics",
        "",
        f"- Generated: {payload['generatedAt']}",
        f"- Overall status: {payload['overallStatus']}",
        f"- Sample size: {payload['sampleSize']} paired seed(s) per row/monster behavior",
        f"- Detail limit: {payload['detailLimit']} smart-loss/dumb-win pair(s) per row/monster behavior",
        f"- Elapsed seconds: {payload['elapsedSeconds']}",
        "",
        "## Summary",
        "",
        "| class | preset | scenario | monsterBehavior | smart | dumb | delta | classification | smart-loss/dumb-win | counterexamples |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for result in payload["results"]:
        lines.append(
            "| "
            f"{result['class']} | "
            f"{result['playerPresetId']} | "
            f"{result['scenarioId']} | "
            f"{result['monsterBehavior']} | "
            f"{format_rate(result['smartWinRate'])} | "
            f"{format_rate(result['dumbWinRate'])} | "
            f"{format_rate(result['delta'])} | "
            f"{result['classification']} | "
            f"{result['smartLossDumbWin']} | "
            f"{result['counterexampleDetailCount']} |"
        )

    lines.extend(["", "## Detailed Smart-Loss / Dumb-Win Pairs", ""])
    for result in payload["results"]:
        if not result["details"]:
            continue
        lines.append(f"### {result['class']} / {result['playerPresetId']} / {result['scenarioId']} / {result['monsterBehavior']}")
        for detail in result["details"]:
            lines.append(
                f"- `{detail['pairSeed']}`: smart {detail['smart']['winner']} in {detail['smart']['rounds']} rounds; "
                f"dumb {detail['dumb']['winner']} in {detail['dumb']['rounds']} rounds."
            )
            smart_evidence = detail["smart"].get("fighterDecisionEvidence", {}) or {}
            first_turn = smart_evidence.get("firstActionableTurn")
            if first_turn:
                lines.append(
                    f"  smart first fighter turn: target `{first_turn['chosenTargetId']}`, "
                    f"square `{format_square_summary(first_turn['chosenSquare'])}`"
                )
        lines.append("")

    lines.extend(["## Smart-Win / Dumb-Loss Counterexamples", ""])
    for result in payload["results"]:
        if not result["counterexampleDetails"]:
            continue
        lines.append(f"### {result['class']} / {result['playerPresetId']} / {result['scenarioId']} / {result['monsterBehavior']}")
        for detail in result["counterexampleDetails"]:
            lines.append(
                f"- `{detail['pairSeed']}`: smart {detail['smart']['winner']} in {detail['smart']['rounds']} rounds; "
                f"dumb {detail['dumb']['winner']} in {detail['dumb']['rounds']} rounds."
            )
        lines.append("")

    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


def write_report(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def main() -> None:
    args = parse_args()
    validate_args(args)
    payload = build_payload(args)
    markdown = format_markdown(payload)
    if not args.no_report:
        write_report(args.json_path, json.dumps(payload, indent=2) + "\n")
        write_report(args.markdown_path, markdown + "\n")
        print(f"Wrote reports to {args.json_path} and {args.markdown_path}")
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(markdown)
    raise SystemExit(1 if payload["overallStatus"] == "fail" else 0)


if __name__ == "__main__":
    main()
