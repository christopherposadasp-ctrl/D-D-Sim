from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Literal

from backend.content.scenario_definitions import ACTIVE_SCENARIO_IDS, get_scenario_definition
from backend.engine import create_encounter, run_encounter, step_encounter, summarize_encounter
from backend.engine.ai.decision import choose_turn_decision
from backend.engine.combat.batch import (
    accumulate_batch_summary,
    build_batch_encounter_config,
    combine_batch_accumulators,
    create_empty_batch_accumulator,
    finalize_batch_combination_summary,
    finalize_batch_summary,
    get_batch_behaviors,
)
from backend.engine.combat.setup import resolve_placements
from backend.engine.models.state import (
    BatchSummary,
    CombatEvent,
    EncounterConfig,
    GridPosition,
    RunEncounterResult,
    UnitState,
    WeaponRange,
)
from backend.engine.rules.combat_rules import can_apply_sneak_attack
from backend.engine.rules.spatial import can_attempt_hide_from_position
from backend.engine.utils.helpers import unit_sort_key

AuditStatus = Literal["pass", "warn", "fail"]
FindingSeverity = Literal["none", "note", "warn", "fail"]
ProbeStatus = Literal["pass", "fail"]
AuditProgressStage = Literal["probe", "health", "complete"]
RogueAuditProgressCallback = Callable[[str, AuditProgressStage, dict[str, object]], None]

ROGUE_AUDIT_PLAYER_PRESET_IDS = ("rogue_level2_ranged_trio",)
SMART_UNDERPERFORMANCE_SMALL_SAMPLE_RUNS = 100
SMART_UNDERPERFORMANCE_NOTE_MIN_DELTA = 0.05
SMART_UNDERPERFORMANCE_WARN_MIN_DELTA = 0.10
SMART_UNDERPERFORMANCE_WARN_Z_SCORE = 1.96
SMART_UNDERPERFORMANCE_FAIL_Z_SCORE = 2.58


@dataclass(frozen=True)
class RogueAuditConfig:
    signature_probe_runs: int = 1
    health_batch_size: int = 12
    seed_prefix: str = "rogue-audit"


@dataclass(frozen=True)
class SmartUnderperformanceAssessment:
    severity: FindingSeverity = "none"
    message: str | None = None


@dataclass
class RogueRunMetrics:
    sneak_attack_applied_count: int = 0
    sneak_attack_turn_count: int = 0
    multiple_sneak_attacks_same_turn_count: int = 0
    sneak_attack_eligible_hit_count: int = 0
    sneak_attack_missed_opportunity_count: int = 0
    shortbow_attack_count: int = 0
    shortsword_fallback_count: int = 0
    hide_attempt_count: int = 0
    hide_success_count: int = 0
    hide_before_attack_count: int = 0
    hide_before_attack_success_count: int = 0
    hide_after_attack_count: int = 0
    hide_after_attack_success_count: int = 0
    disengage_into_attack_count: int = 0
    bonus_dash_into_attack_count: int = 0
    turns_ending_hidden_count: int = 0
    rogue_downed_count: int = 0
    rogue_death_count: int = 0


@dataclass
class RogueCounterTotals:
    sneak_attack_applied_count: int = 0
    sneak_attack_turn_count: int = 0
    multiple_sneak_attacks_same_turn_count: int = 0
    sneak_attack_eligible_hit_count: int = 0
    sneak_attack_missed_opportunity_count: int = 0
    shortbow_attack_count: int = 0
    shortsword_fallback_count: int = 0
    hide_attempt_count: int = 0
    hide_success_count: int = 0
    hide_before_attack_count: int = 0
    hide_before_attack_success_count: int = 0
    hide_after_attack_count: int = 0
    hide_after_attack_success_count: int = 0
    disengage_into_attack_count: int = 0
    bonus_dash_into_attack_count: int = 0
    turns_ending_hidden_count: int = 0
    rogue_downed_count: int = 0
    rogue_death_count: int = 0

    def add_run(self, metrics: RogueRunMetrics) -> None:
        self.sneak_attack_applied_count += metrics.sneak_attack_applied_count
        self.sneak_attack_turn_count += metrics.sneak_attack_turn_count
        self.multiple_sneak_attacks_same_turn_count += metrics.multiple_sneak_attacks_same_turn_count
        self.sneak_attack_eligible_hit_count += metrics.sneak_attack_eligible_hit_count
        self.sneak_attack_missed_opportunity_count += metrics.sneak_attack_missed_opportunity_count
        self.shortbow_attack_count += metrics.shortbow_attack_count
        self.shortsword_fallback_count += metrics.shortsword_fallback_count
        self.hide_attempt_count += metrics.hide_attempt_count
        self.hide_success_count += metrics.hide_success_count
        self.hide_before_attack_count += metrics.hide_before_attack_count
        self.hide_before_attack_success_count += metrics.hide_before_attack_success_count
        self.hide_after_attack_count += metrics.hide_after_attack_count
        self.hide_after_attack_success_count += metrics.hide_after_attack_success_count
        self.disengage_into_attack_count += metrics.disengage_into_attack_count
        self.bonus_dash_into_attack_count += metrics.bonus_dash_into_attack_count
        self.turns_ending_hidden_count += metrics.turns_ending_hidden_count
        self.rogue_downed_count += metrics.rogue_downed_count
        self.rogue_death_count += metrics.rogue_death_count

    def hide_success_rate(self) -> float:
        if self.hide_attempt_count <= 0:
            return 0.0
        return self.hide_success_count / self.hide_attempt_count


@dataclass
class RogueSignatureProbeResult:
    probe_id: str
    display_name: str
    status: ProbeStatus
    action: dict[str, object] | None
    bonus_action: dict[str, object] | None
    sneak_attack_expected: bool | None = None
    sneak_attack_applied: bool | None = None
    hide_attempted: bool | None = None
    hide_succeeded: bool | None = None
    notes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "displayName": self.display_name,
            "status": self.status,
            "action": self.action,
            "bonusAction": self.bonus_action,
            "sneakAttackExpected": self.sneak_attack_expected,
            "sneakAttackApplied": self.sneak_attack_applied,
            "hideAttempted": self.hide_attempted,
            "hideSucceeded": self.hide_succeeded,
            "notes": list(self.notes),
            "failures": list(self.failures),
        }


@dataclass
class RogueAuditRow:
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
    sneak_attack_applied_count: int
    sneak_attack_turn_count: int
    multiple_sneak_attacks_same_turn_count: int
    sneak_attack_eligible_hit_count: int
    sneak_attack_missed_opportunity_count: int
    shortbow_attack_count: int
    shortsword_fallback_count: int
    hide_attempt_count: int
    hide_success_count: int
    hide_success_rate: float
    hide_before_attack_count: int
    hide_before_attack_success_count: int
    hide_after_attack_count: int
    hide_after_attack_success_count: int
    disengage_into_attack_count: int
    bonus_dash_into_attack_count: int
    turns_ending_hidden_count: int
    rogue_downed_count: int
    rogue_death_count: int
    status: AuditStatus
    recommendation: str | None
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

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
            "sneakAttackAppliedCount": self.sneak_attack_applied_count,
            "sneakAttackTurnCount": self.sneak_attack_turn_count,
            "multipleSneakAttacksSameTurnCount": self.multiple_sneak_attacks_same_turn_count,
            "sneakAttackEligibleHitCount": self.sneak_attack_eligible_hit_count,
            "sneakAttackMissedOpportunityCount": self.sneak_attack_missed_opportunity_count,
            "shortbowAttackCount": self.shortbow_attack_count,
            "shortswordFallbackCount": self.shortsword_fallback_count,
            "hideAttemptCount": self.hide_attempt_count,
            "hideSuccessCount": self.hide_success_count,
            "hideSuccessRate": self.hide_success_rate,
            "hideBeforeAttackCount": self.hide_before_attack_count,
            "hideBeforeAttackSuccessCount": self.hide_before_attack_success_count,
            "hideAfterAttackCount": self.hide_after_attack_count,
            "hideAfterAttackSuccessCount": self.hide_after_attack_success_count,
            "disengageIntoAttackCount": self.disengage_into_attack_count,
            "bonusDashIntoAttackCount": self.bonus_dash_into_attack_count,
            "turnsEndingHiddenCount": self.turns_ending_hidden_count,
            "rogueDownedCount": self.rogue_downed_count,
            "rogueDeathCount": self.rogue_death_count,
            "status": self.status,
            "recommendation": self.recommendation,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "failures": list(self.failures),
        }


@dataclass
class PresetAggregate:
    player_preset_id: str
    total_runs: int
    player_win_rate: float
    smart_player_win_rate: float | None
    dumb_player_win_rate: float | None
    status: AuditStatus
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict[str, object]:
        return {
            "playerPresetId": self.player_preset_id,
            "totalRuns": self.total_runs,
            "playerWinRate": self.player_win_rate,
            "smartPlayerWinRate": self.smart_player_win_rate,
            "dumbPlayerWinRate": self.dumb_player_win_rate,
            "status": self.status,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "failures": list(self.failures),
        }


def build_quick_rogue_audit_config(seed_prefix: str = "rogue-audit") -> RogueAuditConfig:
    return RogueAuditConfig(signature_probe_runs=1, health_batch_size=12, seed_prefix=seed_prefix)


def build_full_rogue_audit_config(seed_prefix: str = "rogue-audit") -> RogueAuditConfig:
    return RogueAuditConfig(signature_probe_runs=2, health_batch_size=40, seed_prefix=seed_prefix)


def emit_progress(
    callback: RogueAuditProgressCallback | None,
    label: str,
    stage: AuditProgressStage,
    details: dict[str, object] | None = None,
) -> None:
    if callback is None:
        return
    callback(label, stage, details or {})


def get_rogue_audit_player_preset_ids() -> tuple[str, ...]:
    return ROGUE_AUDIT_PLAYER_PRESET_IDS


def get_rogue_audit_scenario_ids() -> tuple[str, ...]:
    return ACTIVE_SCENARIO_IDS


def get_ranged_rogue_unit_ids(units: dict[str, UnitState]) -> tuple[str, ...]:
    rogue_ids = [
        unit.id
        for unit in units.values()
        if unit.class_id == "rogue"
        and (unit.level or 0) >= 2
        and unit.behavior_profile == "martial_skirmisher"
    ]
    return tuple(sorted(rogue_ids, key=unit_sort_key))


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


def get_actor_attack_events(turn_events: list[CombatEvent], actor_id: str) -> list[CombatEvent]:
    return [event for event in turn_events if event.actor_id == actor_id and event.event_type == "attack"]


def get_weapon_id(event: CombatEvent) -> str | None:
    if event.damage_details is None:
        return None
    return event.damage_details.weapon_id


def attack_has_sneak_attack(event: CombatEvent) -> bool:
    if event.damage_details is None:
        return False
    return any(component.damage_type == "precision" for component in event.damage_details.damage_components)


def unit_is_hidden(unit: UnitState) -> bool:
    return any(effect.kind == "hidden" for effect in unit.temporary_effects)


def extract_rogue_run_metrics(result: RunEncounterResult) -> RogueRunMetrics:
    metrics = RogueRunMetrics()
    rogue_ids = set(get_ranged_rogue_unit_ids(result.final_state.units))

    for actor_id, _, turn_events in get_turn_blocks(result.events):
        if actor_id not in rogue_ids:
            continue

        attack_events = get_actor_attack_events(turn_events, actor_id)
        precision_attacks = [event for event in attack_events if attack_has_sneak_attack(event)]
        if precision_attacks:
            metrics.sneak_attack_turn_count += 1
            metrics.sneak_attack_applied_count += len(precision_attacks)
        if len(precision_attacks) > 1:
            metrics.multiple_sneak_attacks_same_turn_count += 1

        for attack_event in attack_events:
            weapon_id = get_weapon_id(attack_event)
            if weapon_id == "shortbow":
                metrics.shortbow_attack_count += 1
            if weapon_id == "shortsword":
                metrics.shortsword_fallback_count += 1

        first_attack_index = next(
            (index for index, event in enumerate(turn_events) if event.actor_id == actor_id and event.event_type == "attack"),
            None,
        )
        hide_events = [
            (index, event)
            for index, event in enumerate(turn_events)
            if event.actor_id == actor_id and event.event_type == "phase_change" and "stealthRolls" in event.raw_rolls
        ]
        for index, hide_event in hide_events:
            metrics.hide_attempt_count += 1
            success = bool(hide_event.resolved_totals.get("success"))
            if success:
                metrics.hide_success_count += 1
            if first_attack_index is not None and index < first_attack_index:
                metrics.hide_before_attack_count += 1
                if success:
                    metrics.hide_before_attack_success_count += 1
            elif first_attack_index is not None and index > first_attack_index:
                metrics.hide_after_attack_count += 1
                if success:
                    metrics.hide_after_attack_success_count += 1

        if attack_events:
            if any(
                event.actor_id == actor_id
                and event.event_type == "move"
                and event.resolved_totals.get("movementPhase") == "before_action"
                and event.resolved_totals.get("disengageApplied")
                for event in turn_events
            ):
                metrics.disengage_into_attack_count += 1
            if any(
                event.actor_id == actor_id
                and event.event_type == "move"
                and event.resolved_totals.get("movementMode") == "dash"
                and event.resolved_totals.get("movementPhase") == "before_action"
                for event in turn_events
            ):
                metrics.bonus_dash_into_attack_count += 1

    for frame_index in range(1, len(result.replay_frames)):
        pre_turn_state = result.replay_frames[frame_index - 1].state
        frame = result.replay_frames[frame_index]
        actor_id = frame.active_combatant_id
        if actor_id not in rogue_ids:
            continue

        attack_event = next(
            (
                event
                for event in frame.events
                if event.actor_id == actor_id and event.event_type == "attack" and event.damage_details is not None
            ),
            None,
        )
        if attack_event is not None and attack_event.resolved_totals.get("hit"):
            weapon_id = get_weapon_id(attack_event)
            target_id = attack_event.target_ids[0] if attack_event.target_ids else None
            attack_mode = str(attack_event.resolved_totals.get("attackMode", "normal"))
            if target_id is not None:
                attacker = pre_turn_state.units[actor_id]
                target = pre_turn_state.units[target_id]
                weapon = attacker.attacks.get(weapon_id or "")
                if weapon is not None and can_apply_sneak_attack(pre_turn_state, attacker, target, weapon, attack_mode):
                    metrics.sneak_attack_eligible_hit_count += 1
                    if not attack_has_sneak_attack(attack_event):
                        metrics.sneak_attack_missed_opportunity_count += 1

        if unit_is_hidden(frame.state.units[actor_id]):
            metrics.turns_ending_hidden_count += 1

    for unit_id in rogue_ids:
        unit = result.final_state.units[unit_id]
        if unit.conditions.dead:
            metrics.rogue_death_count += 1
        elif unit.current_hp == 0:
            metrics.rogue_downed_count += 1

    return metrics


def build_probe_trio_placements(**overrides: dict[str, int]) -> dict[str, GridPosition]:
    placements = {
        "F1": GridPosition(x=1, y=1),
        "F2": GridPosition(x=1, y=3),
        "F3": GridPosition(x=1, y=5),
        "G1": GridPosition(x=15, y=1),
        "G2": GridPosition(x=15, y=4),
        "G3": GridPosition(x=15, y=7),
        "G4": GridPosition(x=15, y=10),
        "G5": GridPosition(x=15, y=13),
        "G6": GridPosition(x=14, y=14),
        "G7": GridPosition(x=15, y=15),
    }
    for unit_id, point in overrides.items():
        placements[unit_id] = GridPosition(x=int(point["x"]), y=int(point["y"]))
    return placements


def defeat_other_enemies(encounter, *active_enemy_ids: str) -> None:
    active_ids = set(active_enemy_ids)
    for unit in encounter.units.values():
        if unit.faction != "goblins" or unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True
        unit.conditions.unconscious = False
        unit.conditions.prone = False


def set_active_actor(encounter, actor_id: str = "F1") -> None:
    encounter.active_combatant_index = encounter.initiative_order.index(actor_id)


def probe_result_status(failures: list[str]) -> ProbeStatus:
    return "fail" if failures else "pass"


def run_sneak_attack_target_probe(seed: str) -> RogueSignatureProbeResult:
    encounter = create_encounter(
        EncounterConfig(
            seed=seed,
            placements=build_probe_trio_placements(
                F1={"x": 1, "y": 1},
                F2={"x": 5, "y": 3},
                G1={"x": 6, "y": 1},
                G2={"x": 6, "y": 3},
            ),
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1", "G2")
    encounter.units["G1"].current_hp = 1
    encounter.units["G2"].current_hp = 7
    encounter.units["G2"].ac = 1
    set_active_actor(encounter)

    decision = choose_turn_decision(encounter, "F1")
    turn_result = step_encounter(encounter)
    attack_event = next((event for event in turn_result.events if event.actor_id == "F1" and event.event_type == "attack"), None)
    sneak_attack_applied = attack_event is not None and attack_has_sneak_attack(attack_event)

    failures: list[str] = []
    if decision.action != {"kind": "attack", "target_id": "G2", "weapon_id": "shortbow"}:
        failures.append("Smart ranged Rogue did not choose the Sneak Attack-supported shortbow target.")
    if not sneak_attack_applied:
        failures.append("The Sneak Attack target-choice probe did not apply Sneak Attack on the live attack.")

    return RogueSignatureProbeResult(
        probe_id="sneak_attack_target_choice",
        display_name="Sneak Attack target choice",
        status=probe_result_status(failures),
        action=decision.action,
        bonus_action=decision.bonus_action,
        sneak_attack_expected=True,
        sneak_attack_applied=sneak_attack_applied,
        failures=failures,
    )


def run_hide_before_attack_probe(seed: str) -> RogueSignatureProbeResult:
    encounter = create_encounter(
        EncounterConfig(
            seed=seed,
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F1"].effective_speed = 0
    encounter.units["F1"].combat_skill_modifiers["stealth"] = 30
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(encounter, "E4")
    set_active_actor(encounter)

    decision = choose_turn_decision(encounter, "F1")
    turn_result = step_encounter(encounter)
    hide_event = next(
        (
            event
            for event in turn_result.events
            if event.actor_id == "F1" and event.event_type == "phase_change" and "stealthRolls" in event.raw_rolls
        ),
        None,
    )
    hide_succeeded = bool(hide_event and hide_event.resolved_totals.get("success"))

    failures: list[str] = []
    if decision.bonus_action != {"kind": "hide", "timing": "before_action"}:
        failures.append("Ranged Rogue did not spend Cunning Action Hide before attacking from a ready hide square.")
    if decision.action != {"kind": "attack", "target_id": "E4", "weapon_id": "shortbow"}:
        failures.append("Ranged Rogue did not follow the hide setup with the expected shortbow attack.")
    if hide_event is None or not hide_succeeded:
        failures.append("The before-attack hide probe did not produce a successful hide event.")

    return RogueSignatureProbeResult(
        probe_id="hide_before_attack",
        display_name="Hide before attack from rock cover",
        status=probe_result_status(failures),
        action=decision.action,
        bonus_action=decision.bonus_action,
        hide_attempted=hide_event is not None,
        hide_succeeded=hide_succeeded,
        failures=failures,
    )


def run_hide_after_attack_probe(seed: str) -> RogueSignatureProbeResult:
    encounter = create_encounter(
        EncounterConfig(
            seed=seed,
            enemy_preset_id="goblin_screen",
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    encounter.units["F1"].position = GridPosition(x=3, y=8)
    encounter.units["F1"].combat_skill_modifiers["stealth"] = 30
    encounter.units["E4"].position = GridPosition(x=8, y=8)
    defeat_other_enemies(encounter, "E4")
    set_active_actor(encounter)

    decision = choose_turn_decision(encounter, "F1")
    turn_result = step_encounter(encounter)
    hide_event = next(
        (
            event
            for event in turn_result.events
            if event.actor_id == "F1" and event.event_type == "phase_change" and "stealthRolls" in event.raw_rolls
        ),
        None,
    )
    hide_succeeded = bool(hide_event and hide_event.resolved_totals.get("success"))

    failures: list[str] = []
    if decision.pre_action_movement is None:
        failures.append("Ranged Rogue did not reposition into a hide-ready square before attacking.")
    elif not can_attempt_hide_from_position(encounter, "F1", decision.pre_action_movement.path[-1]):
        failures.append("Ranged Rogue did not choose a legal hide-ready square before attacking.")
    if decision.bonus_action != {"kind": "hide", "timing": "after_action"}:
        failures.append("Ranged Rogue did not spend Cunning Action Hide after attacking from the hide-ready square.")
    if hide_event is None or not hide_succeeded:
        failures.append("The after-attack hide probe did not produce a successful hide event.")

    return RogueSignatureProbeResult(
        probe_id="hide_after_attack",
        display_name="Move to hide-ready square and hide after attack",
        status=probe_result_status(failures),
        action=decision.action,
        bonus_action=decision.bonus_action,
        hide_attempted=hide_event is not None,
        hide_succeeded=hide_succeeded,
        failures=failures,
    )


def run_disengage_probe(seed: str) -> RogueSignatureProbeResult:
    encounter = create_encounter(
        EncounterConfig(
            seed=seed,
            placements=build_probe_trio_placements(
                F1={"x": 5, "y": 5},
                F2={"x": 10, "y": 5},
                G1={"x": 6, "y": 5},
                G2={"x": 11, "y": 5},
            ),
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1", "G2")
    encounter.units["G2"].current_hp = min(encounter.units["G2"].current_hp, 4)
    set_active_actor(encounter)

    decision = choose_turn_decision(encounter, "F1")
    turn_result = step_encounter(encounter)
    attack_event = next(
        (
            event
            for event in turn_result.events
            if event.actor_id == "F1" and event.event_type == "attack" and get_weapon_id(event) == "shortbow"
        ),
        None,
    )
    disengage_event = next(
        (
            event
            for event in turn_result.events
            if event.actor_id == "F1"
            and event.event_type == "move"
            and event.resolved_totals.get("movementPhase") == "before_action"
            and event.resolved_totals.get("disengageApplied")
        ),
        None,
    )

    failures: list[str] = []
    if decision.bonus_action != {"kind": "disengage", "timing": "before_action"}:
        failures.append("Ranged Rogue did not spend Cunning Action Disengage before the escape shot.")
    if not decision.action or decision.action.get("kind") != "attack" or decision.action.get("weapon_id") != "shortbow":
        failures.append("Ranged Rogue did not convert the disengage into a shortbow attack.")
    if disengage_event is None:
        failures.append("The disengage probe did not emit a disengage phase-change event.")
    if attack_event is None or not attack_has_sneak_attack(attack_event):
        failures.append("The disengage probe shortbow attack did not apply Sneak Attack.")

    return RogueSignatureProbeResult(
        probe_id="disengage_into_attack",
        display_name="Disengage out of melee into shortbow attack",
        status=probe_result_status(failures),
        action=decision.action,
        bonus_action=decision.bonus_action,
        failures=failures,
    )


def run_bonus_dash_probe(seed: str) -> RogueSignatureProbeResult:
    encounter = create_encounter(
        EncounterConfig(
            seed=seed,
            placements=build_probe_trio_placements(F1={"x": 1, "y": 1}, G1={"x": 15, "y": 1}),
            player_preset_id="rogue_level2_ranged_trio",
            player_behavior="smart",
        )
    )
    defeat_other_enemies(encounter, "G1")
    encounter.units["F1"].attacks["shortbow"].range = WeaponRange(normal=30, long=60)
    set_active_actor(encounter)

    decision = choose_turn_decision(encounter, "F1")
    turn_result = step_encounter(encounter)
    dash_move_event = next(
        (
            event
            for event in turn_result.events
            if event.actor_id == "F1"
            and event.event_type == "move"
            and event.resolved_totals.get("movementMode") == "dash"
            and event.resolved_totals.get("movementPhase") == "before_action"
        ),
        None,
    )

    failures: list[str] = []
    if decision.bonus_action != {"kind": "bonus_dash", "timing": "before_action"}:
        failures.append("Ranged Rogue did not spend Cunning Action Dash before the long-range shortbow attack.")
    if decision.action != {"kind": "attack", "target_id": "G1", "weapon_id": "shortbow"}:
        failures.append("Ranged Rogue did not follow bonus Dash with the expected shortbow attack.")
    if dash_move_event is None:
        failures.append("The bonus-Dash probe did not emit a before-action dash movement event.")

    return RogueSignatureProbeResult(
        probe_id="bonus_dash_into_attack",
        display_name="Bonus Dash into shortbow attack",
        status=probe_result_status(failures),
        action=decision.action,
        bonus_action=decision.bonus_action,
        failures=failures,
    )


def review_signature_probes(
    config: RogueAuditConfig,
    progress_callback: RogueAuditProgressCallback | None = None,
) -> list[RogueSignatureProbeResult]:
    probe_builders = (
        ("Sneak Attack target", run_sneak_attack_target_probe),
        ("Hide before attack", run_hide_before_attack_probe),
        ("Hide after attack", run_hide_after_attack_probe),
        ("Disengage", run_disengage_probe),
        ("Bonus Dash", run_bonus_dash_probe),
    )
    total_runs = len(probe_builders) * config.signature_probe_runs
    completed_runs = 0
    results: list[RogueSignatureProbeResult] = []

    for run_index in range(config.signature_probe_runs):
        for label, builder in probe_builders:
            emit_progress(
                progress_callback,
                label,
                "probe",
                {"current": completed_runs, "total": total_runs},
            )
            seed = f"{config.seed_prefix}-probe-{builder.__name__.replace('run_', '').replace('_probe', '')}-{run_index:02d}"
            results.append(builder(seed))
            completed_runs += 1
            emit_progress(
                progress_callback,
                label,
                "probe",
                {"current": completed_runs, "total": total_runs},
            )

    return results


def run_health_pass(
    player_preset_id: str,
    scenario_id: str,
    config: RogueAuditConfig,
    progress_callback: RogueAuditProgressCallback | None = None,
) -> tuple[BatchSummary, RogueCounterTotals]:
    label = f"{player_preset_id}:{scenario_id}"
    requested_player_behavior = "balanced"
    requested_monster_behavior = "combined"
    seed = f"{config.seed_prefix}-{player_preset_id}-{scenario_id}-health"
    base_config = EncounterConfig(
        seed=seed,
        enemy_preset_id=scenario_id,
        player_preset_id=player_preset_id,
        batch_size=config.health_batch_size,
        player_behavior=requested_player_behavior,
        monster_behavior=requested_monster_behavior,
    )
    placements = resolve_placements(base_config)
    total_runs = config.health_batch_size * len(get_batch_behaviors(requested_monster_behavior))
    completed_runs = 0
    totals = RogueCounterTotals()
    accumulators_by_monster: dict[str, dict[str, float]] = {}

    for monster_behavior in get_batch_behaviors(requested_monster_behavior):
        accumulator = create_empty_batch_accumulator()
        for run_index in range(config.health_batch_size):
            emit_progress(
                progress_callback,
                label,
                "health",
                {"current": completed_runs, "total": total_runs, "monsterBehavior": monster_behavior},
            )
            encounter_config, resolved_behavior = build_batch_encounter_config(
                seed,
                placements,
                requested_player_behavior,
                monster_behavior,
                scenario_id,
                player_preset_id,
                run_index,
            )
            result = run_encounter(encounter_config)
            accumulate_batch_summary(accumulator, summarize_encounter(result.final_state), resolved_behavior)
            totals.add_run(extract_rogue_run_metrics(result))
            completed_runs += 1
            emit_progress(
                progress_callback,
                label,
                "health",
                {"current": completed_runs, "total": total_runs, "monsterBehavior": monster_behavior},
            )
        accumulators_by_monster[monster_behavior] = accumulator

    combination_summaries = [
        finalize_batch_combination_summary(
            seed,
            requested_player_behavior,
            monster_behavior,
            config.health_batch_size,
            accumulators_by_monster[monster_behavior],
        )
        for monster_behavior in get_batch_behaviors(requested_monster_behavior)
    ]
    summary = finalize_batch_summary(
        seed,
        requested_player_behavior,
        requested_monster_behavior,
        config.health_batch_size,
        combine_batch_accumulators(list(accumulators_by_monster.values())),
        combination_summaries,
    )
    return summary, totals


def assess_smart_underperformance(
    smart_rate: float | int | None,
    dumb_rate: float | int | None,
    smart_run_count: int,
    dumb_run_count: int,
) -> SmartUnderperformanceAssessment:
    if smart_rate is None or dumb_rate is None or smart_run_count <= 0 or dumb_run_count <= 0:
        return SmartUnderperformanceAssessment()

    smart = float(smart_rate)
    dumb = float(dumb_rate)
    delta = dumb - smart
    if delta < SMART_UNDERPERFORMANCE_NOTE_MIN_DELTA:
        return SmartUnderperformanceAssessment()

    min_run_count = min(smart_run_count, dumb_run_count)
    detail = ""
    if min_run_count < SMART_UNDERPERFORMANCE_SMALL_SAMPLE_RUNS:
        severity: FindingSeverity = "warn" if delta >= SMART_UNDERPERFORMANCE_WARN_MIN_DELTA else "note"
        detail = "small-sample signal"
    else:
        import math

        standard_error = math.sqrt(
            (smart * (1.0 - smart) / smart_run_count)
            + (dumb * (1.0 - dumb) / dumb_run_count)
        )
        if standard_error == 0:
            z_score = math.inf if delta > 0 else 0.0
        else:
            z_score = delta / standard_error
        if z_score >= SMART_UNDERPERFORMANCE_FAIL_Z_SCORE:
            severity = "fail"
        elif z_score >= SMART_UNDERPERFORMANCE_WARN_Z_SCORE:
            severity = "warn"
        else:
            severity = "note"
        detail = f"z={z_score:.2f}"

    message = (
        "Smart players underperformed dumb players in the combined pass "
        f"(smart {smart:.1%}, dumb {dumb:.1%}, delta {delta * 100:.1f} pts over "
        f"{smart_run_count} vs {dumb_run_count} runs; {detail})."
    )
    return SmartUnderperformanceAssessment(severity=severity, message=message)


def add_smart_underperformance_assessment(
    assessment: SmartUnderperformanceAssessment,
    notes: list[str],
    warnings: list[str],
    failures: list[str],
) -> None:
    if assessment.message is None:
        return
    if assessment.severity == "note":
        notes.append(assessment.message)
        return
    if assessment.severity == "warn":
        warnings.append(assessment.message)
        return
    if assessment.severity == "fail":
        failures.append(assessment.message)


def classify_smart_underperformance(
    smart_rate: float | int | None,
    dumb_rate: float | int | None,
    smart_run_count: int,
    dumb_run_count: int,
) -> FindingSeverity:
    return assess_smart_underperformance(
        smart_rate,
        dumb_rate,
        smart_run_count,
        dumb_run_count,
    ).severity


def determine_row_status(notes: list[str], warnings: list[str], failures: list[str]) -> AuditStatus:
    if failures:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def build_row_findings(
    summary: BatchSummary,
    counter_totals: RogueCounterTotals,
) -> tuple[list[str], list[str], list[str]]:
    notes: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    add_smart_underperformance_assessment(
        assess_smart_underperformance(
            summary.smart_player_win_rate,
            summary.dumb_player_win_rate,
            summary.smart_run_count,
            summary.dumb_run_count,
        ),
        notes,
        warnings,
        failures,
    )

    if counter_totals.multiple_sneak_attacks_same_turn_count > 0:
        failures.append("The Rogue applied Sneak Attack more than once in the same turn.")
    if counter_totals.sneak_attack_eligible_hit_count > 0 and counter_totals.sneak_attack_applied_count == 0:
        failures.append("The Rogue landed qualifying hits but never applied Sneak Attack.")
    if counter_totals.sneak_attack_missed_opportunity_count > 0:
        warnings.append("The Rogue missed at least one Sneak Attack opportunity on a qualifying hit.")
    if counter_totals.shortsword_fallback_count > counter_totals.shortbow_attack_count:
        warnings.append("Shortsword fallback volume exceeded shortbow volume for the ranged Rogue.")
    if counter_totals.hide_attempt_count > 0 and counter_totals.hide_success_rate() < 0.4:
        warnings.append("Hide success rate fell below 40% across the health pass.")

    return notes, warnings, failures


def build_row_recommendation(notes: list[str], warnings: list[str], failures: list[str]) -> str | None:
    issues = [*notes, *warnings, *failures]
    if any("Sneak Attack" in issue for issue in issues):
        return "Inspect Sneak Attack qualification and ranged target selection before touching numbers."
    if any("Hide" in issue for issue in issues):
        return "Inspect hide-square selection and cover usage before changing Rogue damage output."
    if any("shortsword" in issue.lower() for issue in issues):
        return "Inspect ranged standoff logic before touching class or scenario balance."
    if any("Smart players underperformed dumb players" in issue for issue in issues):
        return "Inspect Rogue target selection and escape timing before touching numbers."
    return None


def audit_rogue_pair(
    player_preset_id: str,
    scenario_id: str,
    config: RogueAuditConfig | None = None,
    progress_callback: RogueAuditProgressCallback | None = None,
) -> RogueAuditRow:
    audit_config = config or RogueAuditConfig()
    scenario = get_scenario_definition(scenario_id)
    summary, counter_totals = run_health_pass(player_preset_id, scenario_id, audit_config, progress_callback)
    notes, warnings, failures = build_row_findings(summary, counter_totals)
    recommendation = build_row_recommendation(notes, warnings, failures)
    status = determine_row_status(notes, warnings, failures)

    row = RogueAuditRow(
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
        sneak_attack_applied_count=counter_totals.sneak_attack_applied_count,
        sneak_attack_turn_count=counter_totals.sneak_attack_turn_count,
        multiple_sneak_attacks_same_turn_count=counter_totals.multiple_sneak_attacks_same_turn_count,
        sneak_attack_eligible_hit_count=counter_totals.sneak_attack_eligible_hit_count,
        sneak_attack_missed_opportunity_count=counter_totals.sneak_attack_missed_opportunity_count,
        shortbow_attack_count=counter_totals.shortbow_attack_count,
        shortsword_fallback_count=counter_totals.shortsword_fallback_count,
        hide_attempt_count=counter_totals.hide_attempt_count,
        hide_success_count=counter_totals.hide_success_count,
        hide_success_rate=counter_totals.hide_success_rate(),
        hide_before_attack_count=counter_totals.hide_before_attack_count,
        hide_before_attack_success_count=counter_totals.hide_before_attack_success_count,
        hide_after_attack_count=counter_totals.hide_after_attack_count,
        hide_after_attack_success_count=counter_totals.hide_after_attack_success_count,
        disengage_into_attack_count=counter_totals.disengage_into_attack_count,
        bonus_dash_into_attack_count=counter_totals.bonus_dash_into_attack_count,
        turns_ending_hidden_count=counter_totals.turns_ending_hidden_count,
        rogue_downed_count=counter_totals.rogue_downed_count,
        rogue_death_count=counter_totals.rogue_death_count,
        status=status,
        recommendation=recommendation,
        notes=notes,
        warnings=warnings,
        failures=failures,
    )

    emit_progress(
        progress_callback,
        f"{player_preset_id}:{scenario_id}",
        "complete",
        {"status": row.status, "noteCount": len(row.notes), "warningCount": len(row.warnings), "failureCount": len(row.failures)},
    )
    return row


def audit_rogue_profiles(
    config: RogueAuditConfig | None = None,
    player_preset_ids: Iterable[str] | None = None,
    scenario_ids: Iterable[str] | None = None,
    progress_callback: RogueAuditProgressCallback | None = None,
) -> list[RogueAuditRow]:
    audit_config = config or RogueAuditConfig()
    selected_player_presets = tuple(player_preset_ids) if player_preset_ids is not None else ROGUE_AUDIT_PLAYER_PRESET_IDS
    selected_scenarios = tuple(scenario_ids) if scenario_ids is not None else ACTIVE_SCENARIO_IDS

    rows: list[RogueAuditRow] = []
    for player_preset_id in selected_player_presets:
        for scenario_id in selected_scenarios:
            rows.append(audit_rogue_pair(player_preset_id, scenario_id, audit_config, progress_callback))
    return rows


def build_preset_aggregates(rows: list[RogueAuditRow]) -> list[PresetAggregate]:
    aggregates: list[PresetAggregate] = []
    for player_preset_id in ROGUE_AUDIT_PLAYER_PRESET_IDS:
        matching_rows = [row for row in rows if row.player_preset_id == player_preset_id]
        if not matching_rows:
            continue

        total_runs = sum(row.total_runs for row in matching_rows)
        player_wins = sum(row.player_win_rate * row.total_runs for row in matching_rows)
        total_smart_runs = sum(row.smart_run_count for row in matching_rows)
        total_dumb_runs = sum(row.dumb_run_count for row in matching_rows)
        smart_wins = sum((row.smart_player_win_rate or 0.0) * row.smart_run_count for row in matching_rows)
        dumb_wins = sum((row.dumb_player_win_rate or 0.0) * row.dumb_run_count for row in matching_rows)

        notes: list[str] = []
        warnings: list[str] = []
        failures: list[str] = []
        smart_rate = smart_wins / total_smart_runs if total_smart_runs > 0 else None
        dumb_rate = dumb_wins / total_dumb_runs if total_dumb_runs > 0 else None
        assessment = assess_smart_underperformance(smart_rate, dumb_rate, total_smart_runs, total_dumb_runs)
        if assessment.message is not None:
            assessment = SmartUnderperformanceAssessment(
                severity=assessment.severity,
                message=assessment.message.replace("the combined pass", "the aggregate combined pass", 1),
            )
        add_smart_underperformance_assessment(assessment, notes, warnings, failures)
        aggregate_status = determine_row_status(notes, warnings, failures)

        aggregates.append(
            PresetAggregate(
                player_preset_id=player_preset_id,
                total_runs=total_runs,
                player_win_rate=player_wins / total_runs if total_runs > 0 else 0.0,
                smart_player_win_rate=smart_rate,
                dumb_player_win_rate=dumb_rate,
                status=aggregate_status,
                notes=notes,
                warnings=warnings,
                failures=failures,
            )
        )

    return aggregates


def build_report_payload(
    rows: list[RogueAuditRow],
    config: RogueAuditConfig,
    signature_probes: list[RogueSignatureProbeResult],
    rules_gate: dict[str, object] | None = None,
) -> dict[str, object]:
    aggregates = build_preset_aggregates(rows)
    overall_status: AuditStatus = "pass"
    if rules_gate and rules_gate.get("status") == "fail":
        overall_status = "fail"
    elif any(probe.status == "fail" for probe in signature_probes):
        overall_status = "fail"
    elif any(aggregate.status == "fail" for aggregate in aggregates) or any(row.status == "fail" for row in rows):
        overall_status = "fail"
    elif any(aggregate.status != "pass" for aggregate in aggregates) or any(row.status != "pass" for row in rows):
        overall_status = "warn"

    return {
        "config": asdict(config),
        "rulesGate": rules_gate,
        "playerPresetIds": list(get_rogue_audit_player_preset_ids()),
        "scenarioIds": list(get_rogue_audit_scenario_ids()),
        "overallStatus": overall_status,
        "signatureProbes": [probe.to_report_dict() for probe in signature_probes],
        "rows": [row.to_report_dict() for row in rows],
        "presetAggregates": [aggregate.to_report_dict() for aggregate in aggregates],
    }


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def format_rogue_audit_report(
    rows: list[RogueAuditRow],
    signature_probes: list[RogueSignatureProbeResult],
    aggregates: list[PresetAggregate],
    rules_gate: dict[str, object] | None = None,
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

    lines.append("## Signature Probes")
    lines.append("| probeId | status | action | bonusAction | sneakAttackApplied | hideSucceeded |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for probe in signature_probes:
        lines.append(
            "| "
            + " | ".join(
                [
                    probe.probe_id,
                    probe.status,
                    str(probe.action),
                    str(probe.bonus_action),
                    str(probe.sneak_attack_applied),
                    str(probe.hide_succeeded),
                ]
            )
            + " |"
        )
    for probe in signature_probes:
        if not probe.failures and not probe.notes:
            continue
        lines.append("")
        lines.append(f"### Probe / {probe.probe_id}")
        for failure in probe.failures:
            lines.append(f"- fail: {failure}")
        for note in probe.notes:
            lines.append(f"- note: {note}")

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
    for aggregate in aggregates:
        if not aggregate.failures and not aggregate.warnings and not aggregate.notes:
            continue
        lines.append("")
        lines.append(f"### Aggregate / {aggregate.player_preset_id}")
        for failure in aggregate.failures:
            lines.append(f"- fail: {failure}")
        for warning in aggregate.warnings:
            lines.append(f"- warn: {warning}")
        for note in aggregate.notes:
            lines.append(f"- note: {note}")

    lines.append("")
    lines.append("## Scenario Rows")
    lines.append(
        "| scenarioId | playerWinRate | smartPlayerWinRate | dumbPlayerWinRate | averageRounds | hideSuccessRate | sneakAttackApplied | missedSneakAttack | shortbowAttacks | shortswordFallback | status | recommendation |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.scenario_id,
                    format_percent(row.player_win_rate),
                    format_percent(row.smart_player_win_rate),
                    format_percent(row.dumb_player_win_rate),
                    f"{row.average_rounds:.2f}",
                    format_percent(row.hide_success_rate),
                    str(row.sneak_attack_applied_count),
                    str(row.sneak_attack_missed_opportunity_count),
                    str(row.shortbow_attack_count),
                    str(row.shortsword_fallback_count),
                    row.status,
                    row.recommendation or "-",
                ]
            )
            + " |"
        )
    for row in rows:
        if not row.failures and not row.warnings and not row.notes:
            continue
        lines.append("")
        lines.append(f"### Row / {row.player_preset_id} / {row.scenario_id}")
        for failure in row.failures:
            lines.append(f"- fail: {failure}")
        for warning in row.warnings:
            lines.append(f"- warn: {warning}")
        for note in row.notes:
            lines.append(f"- note: {note}")

    return "\n".join(lines)
