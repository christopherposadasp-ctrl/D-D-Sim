from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Literal

from backend.content.enemies import (
    get_enemy_preset,
    get_enemy_variant,
)
from backend.content.player_loadouts import get_player_preset_unit_ids
from backend.content.scenario_definitions import ACTIVE_SCENARIO_IDS, get_scenario_definition
from backend.engine import create_encounter, run_batch, run_encounter, step_encounter
from backend.engine.models.state import (
    BatchCombinationSummary,
    BatchSummary,
    CombatEvent,
    EncounterConfig,
    RunEncounterResult,
)
from backend.engine.rules.spatial import inspect_placements_for_unit_ids

AuditStatus = Literal["pass", "warn", "fail"]
AuditProgressStage = Literal["structural", "smoke", "mechanic", "health", "complete"]
SignatureMatcher = Callable[[RunEncounterResult], bool]
ScenarioAuditProgressCallback = Callable[[str, AuditProgressStage, dict[str, object]], None]


@dataclass(frozen=True)
class ScenarioAuditConfig:
    smart_smoke_runs: int = 5
    dumb_smoke_runs: int = 5
    mechanic_runs: int = 100
    health_batch_size: int = 1000
    seed_prefix: str = "scenario-audit"


def build_quick_scenario_audit_config(seed_prefix: str = "scenario-audit") -> ScenarioAuditConfig:
    """Return the lighter-weight audit profile used for routine local checks."""

    return ScenarioAuditConfig(
        smart_smoke_runs=3,
        dumb_smoke_runs=3,
        mechanic_runs=25,
        health_batch_size=250,
        seed_prefix=seed_prefix,
    )


def build_full_scenario_audit_config(seed_prefix: str = "scenario-audit") -> ScenarioAuditConfig:
    """Return the deeper audit profile used for slower validation passes."""

    return ScenarioAuditConfig(seed_prefix=seed_prefix)


@dataclass(frozen=True)
class SignatureCheck:
    name: str
    matcher: SignatureMatcher


@dataclass
class ScenarioAuditRow:
    scenario_id: str
    display_name: str
    unit_count: int
    combined_player_win_rate: float
    combined_enemy_win_rate: float
    smart_player_win_rate: float | None
    dumb_player_win_rate: float | None
    kind_player_win_rate: float | None
    balanced_player_win_rate: float | None
    evil_player_win_rate: float | None
    average_rounds: float
    signature_mechanic_count: int
    status: AuditStatus
    simple_suggestion: str | None
    warnings: list[str] = field(default_factory=list)
    signature_breakdown: dict[str, int] = field(default_factory=dict)

    def to_report_dict(self) -> dict[str, object]:
        return {
            "scenarioId": self.scenario_id,
            "displayName": self.display_name,
            "unitCount": self.unit_count,
            "combinedPlayerWinRate": self.combined_player_win_rate,
            "combinedEnemyWinRate": self.combined_enemy_win_rate,
            "smartPlayerWinRate": self.smart_player_win_rate,
            "dumbPlayerWinRate": self.dumb_player_win_rate,
            "kindPlayerWinRate": self.kind_player_win_rate,
            "balancedPlayerWinRate": self.balanced_player_win_rate,
            "evilPlayerWinRate": self.evil_player_win_rate,
            "averageRounds": self.average_rounds,
            "signatureMechanicCount": self.signature_mechanic_count,
            "status": self.status,
            "simpleSuggestion": self.simple_suggestion,
            "warnings": list(self.warnings),
            "signatureBreakdown": dict(self.signature_breakdown),
        }


def emit_progress(
    callback: ScenarioAuditProgressCallback | None,
    preset_id: str,
    stage: AuditProgressStage,
    details: dict[str, object] | None = None,
) -> None:
    if callback is None:
        return
    callback(preset_id, stage, details or {})


def actor_has_role(result: RunEncounterResult, actor_id: str, *roles: str) -> bool:
    actor = result.final_state.units.get(actor_id)
    return actor is not None and actor.combat_role in roles


def get_string_list(mapping: dict[str, object], key: str) -> list[str]:
    value = mapping.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def iter_events(result: RunEncounterResult, event_type: str | None = None) -> Iterable[CombatEvent]:
    for event in result.events:
        if event_type is None or event.event_type == event_type:
            yield event


def any_attack_with_weapon(result: RunEncounterResult, actor_roles: set[str], weapon_id: str) -> bool:
    for event in iter_events(result, "attack"):
        if not event.damage_details:
            continue
        if event.damage_details.weapon_id != weapon_id:
            continue
        if actor_has_role(result, event.actor_id, *actor_roles):
            return True
    return False


def has_scout_multiattack(result: RunEncounterResult) -> bool:
    attacks_by_turn: dict[tuple[int, str], int] = {}
    for event in iter_events(result, "attack"):
        if not actor_has_role(result, event.actor_id, "scout"):
            continue
        key = (event.round, event.actor_id)
        attacks_by_turn[key] = attacks_by_turn.get(key, 0) + 1
        if attacks_by_turn[key] >= 2:
            return True
    return False


def has_early_orc_advance(result: RunEncounterResult) -> bool:
    first_orc_attack_index: int | None = None

    for index, event in enumerate(result.events):
        if event.event_type != "attack":
            continue
        if actor_has_role(result, event.actor_id, "orc_warrior") and event.damage_details and event.damage_details.weapon_id == "greataxe":
            first_orc_attack_index = index
            break

    if first_orc_attack_index is None:
        return False

    for index, event in enumerate(result.events[:first_orc_attack_index]):
        if event.event_type != "move" or not actor_has_role(result, event.actor_id, "orc_warrior"):
            continue
        if event.movement_details and (event.movement_details.distance or 0) >= 3:
            return True

    return False


def has_pack_tactics_attack(result: RunEncounterResult) -> bool:
    for event in iter_events(result, "attack"):
        if not actor_has_role(result, event.actor_id, "wolf"):
            continue
        if "pack_tactics" in get_string_list(event.raw_rolls, "advantageSources"):
            return True
    return False


def has_attack_rider(result: RunEncounterResult, actor_roles: set[str], rider: str) -> bool:
    for event in iter_events(result, "attack"):
        if not actor_has_role(result, event.actor_id, *actor_roles):
            continue
        if not event.damage_details or not event.damage_details.attack_riders_applied:
            continue
        if rider in event.damage_details.attack_riders_applied:
            return True
    return False


def has_swallow_action(result: RunEncounterResult) -> bool:
    for event in iter_events(result, "attack"):
        if not actor_has_role(result, event.actor_id, "giant_toad"):
            continue
        if event.resolved_totals.get("specialAction") == "swallow":
            return True
    return False


def build_signature_checks() -> dict[str, list[SignatureCheck]]:
    signature_library = {
        "goblin_melee_engagement": SignatureCheck(
            "goblinMeleeEngagement",
            lambda result: any_attack_with_weapon(result, {"goblin_melee"}, "scimitar"),
        ),
        "goblin_shortbow_attack": SignatureCheck(
            "goblinShortbowAttack",
            lambda result: any_attack_with_weapon(result, {"goblin_archer"}, "shortbow"),
        ),
        "bandit_melee_attack": SignatureCheck(
            "banditMeleeAttack",
            lambda result: any_attack_with_weapon(result, {"bandit_melee"}, "club"),
        ),
        "bandit_shortbow_attack": SignatureCheck(
            "banditShortbowAttack",
            lambda result: any_attack_with_weapon(result, {"bandit_archer"}, "shortbow"),
        ),
        "scout_multiattack": SignatureCheck("scoutMultiattack", has_scout_multiattack),
        "guard_spear_attack": SignatureCheck(
            "guardSpearAttack",
            lambda result: any_attack_with_weapon(result, {"guard"}, "spear"),
        ),
        "goblin_ranged_support": SignatureCheck(
            "goblinRangedSupport",
            lambda result: any_attack_with_weapon(result, {"goblin_archer"}, "shortbow"),
        ),
        "orc_greataxe_attack": SignatureCheck(
            "orcGreataxeAttack",
            lambda result: any_attack_with_weapon(result, {"orc_warrior"}, "greataxe"),
        ),
        "orc_early_advance": SignatureCheck("orcEarlyAdvance", has_early_orc_advance),
        "pack_tactics_attack": SignatureCheck("packTacticsAttack", has_pack_tactics_attack),
        "prone_rider_applied": SignatureCheck(
            "proneRiderApplied",
            lambda result: has_attack_rider(result, {"wolf"}, "prone_on_hit"),
        ),
        "crocodile_grapple": SignatureCheck(
            "crocodileGrapple",
            lambda result: has_attack_rider(result, {"crocodile"}, "grapple_on_hit"),
        ),
        "toad_swallow": SignatureCheck("toadSwallow", has_swallow_action),
    }

    return {
        scenario_id: [signature_library[expectation_id] for expectation_id in get_scenario_definition(scenario_id).audit_expectation_ids]
        for scenario_id in ACTIVE_SCENARIO_IDS
    }


SIGNATURE_CHECKS = build_signature_checks()


def get_active_scenario_ids() -> tuple[str, ...]:
    return ACTIVE_SCENARIO_IDS


def run_structural_pass(preset_id: str, seed_prefix: str) -> list[str]:
    issues: list[str] = []
    player_unit_ids = get_player_preset_unit_ids()

    try:
        preset = get_enemy_preset(preset_id)
        encounter = create_encounter(EncounterConfig(seed=f"{seed_prefix}-{preset_id}-struct", enemy_preset_id=preset_id))
        expected_unit_ids = [*player_unit_ids, *[unit.unit_id for unit in preset.units]]

        if sorted(encounter.units) != sorted(expected_unit_ids):
            issues.append("Loaded unit set does not match the preset roster.")

        placements = {}
        footprints = {}
        for unit_id in expected_unit_ids:
            unit = encounter.units[unit_id]
            if unit.position is None:
                issues.append(f"{unit_id} is missing a starting position.")
                continue
            placements[unit_id] = unit.position
            footprints[unit_id] = unit.footprint

        validation = inspect_placements_for_unit_ids(placements, expected_unit_ids, footprints, encounter.terrain_features)
        if not validation.is_valid:
            issues.extend(validation.errors)

        for preset_unit in preset.units:
            unit = encounter.units[preset_unit.unit_id]
            expected_variant = get_enemy_variant(preset_unit.variant_id)
            if unit.combat_role != expected_variant.combat_role:
                issues.append(f"{preset_unit.unit_id} loaded as {unit.combat_role} instead of {expected_variant.combat_role}.")
            if not unit.position or unit.position.model_dump() != preset_unit.position.model_dump():
                issues.append(f"{preset_unit.unit_id} did not load at the expected default position.")

        first_step = step_encounter(encounter)
        if not first_step.events:
            issues.append("The preset can be created but does not emit any events on its first step.")
    except Exception as error:
        issues.append(str(error))

    return issues


def run_smoke_pass(
    preset_id: str,
    config: ScenarioAuditConfig,
    progress_callback: ScenarioAuditProgressCallback | None = None,
) -> list[str]:
    issues: list[str] = []

    smoke_plan = [("smart", config.smart_smoke_runs), ("dumb", config.dumb_smoke_runs)]
    total_runs = sum(run_count for _, run_count in smoke_plan)
    completed_runs = 0
    for player_behavior, run_count in smoke_plan:
        for run_index in range(run_count):
            emit_progress(
                progress_callback,
                preset_id,
                "smoke",
                {
                    "playerBehavior": player_behavior,
                    "current": completed_runs,
                    "total": total_runs,
                },
            )
            result = run_encounter(
                EncounterConfig(
                    seed=f"{config.seed_prefix}-{preset_id}-smoke-{player_behavior}-{run_index:02d}",
                    enemy_preset_id=preset_id,
                    player_behavior=player_behavior,
                    monster_behavior="balanced",
                )
            )
            if result.final_state.terminal_state != "complete":
                issues.append(f"{player_behavior} smoke run {run_index} did not reach completion.")
                continue
            if result.final_state.winner is None:
                issues.append(f"{player_behavior} smoke run {run_index} completed without a winner.")
            event_types = {event.event_type for event in result.events}
            if "turn_start" not in event_types or "attack" not in event_types:
                issues.append(f"{player_behavior} smoke run {run_index} did not emit the expected combat events.")
            completed_runs += 1
            emit_progress(
                progress_callback,
                preset_id,
                "smoke",
                {
                    "playerBehavior": player_behavior,
                    "current": completed_runs,
                    "total": total_runs,
                },
            )

    return issues


def run_mechanic_pass(
    preset_id: str,
    config: ScenarioAuditConfig,
    progress_callback: ScenarioAuditProgressCallback | None = None,
) -> tuple[dict[str, int], int]:
    signature_counts = {check.name: 0 for check in SIGNATURE_CHECKS[preset_id]}

    for run_index in range(config.mechanic_runs):
        emit_progress(
            progress_callback,
            preset_id,
            "mechanic",
            {
                "current": run_index,
                "total": config.mechanic_runs,
            },
        )
        result = run_encounter(
            EncounterConfig(
                seed=f"{config.seed_prefix}-{preset_id}-mechanic-{run_index:03d}",
                enemy_preset_id=preset_id,
                player_behavior="balanced",
                monster_behavior="balanced",
            )
        )
        for check in SIGNATURE_CHECKS[preset_id]:
            if check.matcher(result):
                signature_counts[check.name] += 1
        emit_progress(
            progress_callback,
            preset_id,
            "mechanic",
            {
                "current": run_index + 1,
                "total": config.mechanic_runs,
            },
        )

    signature_mechanic_count = min(signature_counts.values()) if signature_counts else 0
    return signature_counts, signature_mechanic_count


def get_combination_summary(summary: BatchSummary, monster_behavior: str) -> BatchCombinationSummary | None:
    if not summary.combination_summaries:
        return None

    for entry in summary.combination_summaries:
        if entry.monster_behavior == monster_behavior:
            return entry

    return None


def build_simple_suggestion(preset_id: str, player_win_rate: float, enemy_win_rate: float) -> str | None:
    if player_win_rate > 0.9:
        if preset_id == "marsh_predators":
            return "Move the crocodile cluster 1 square closer before changing monster counts or stats."
        return "Move the enemy front line 1 square closer."

    if enemy_win_rate > 0.9:
        if preset_id == "marsh_predators":
            return "Move one crocodile 1 square back before changing composition."
        return "Move the enemy front line 1 square back, or spread the back line by 1 square."

    return None


def build_diagnostic_warnings(summary: BatchSummary, signature_mechanic_count: int, structural_issues: list[str], smoke_issues: list[str]) -> list[str]:
    warnings: list[str] = []

    if structural_issues:
        warnings.extend(structural_issues)
    if smoke_issues:
        warnings.extend(smoke_issues)

    if signature_mechanic_count == 0:
        warnings.append("One or more required signature mechanics never appeared in the mechanic-frequency pass.")
    elif signature_mechanic_count < 5:
        warnings.append("At least one required signature mechanic appeared only rarely in the mechanic-frequency pass.")

    if (
        summary.smart_player_win_rate is not None
        and summary.dumb_player_win_rate is not None
        and summary.smart_player_win_rate < summary.dumb_player_win_rate
    ):
        warnings.append("Smart players underperformed dumb players.")

    kind_summary = get_combination_summary(summary, "kind")
    balanced_summary = get_combination_summary(summary, "balanced")
    evil_summary = get_combination_summary(summary, "evil")
    if (
        kind_summary
        and balanced_summary
        and evil_summary
        and (
            kind_summary.player_win_rate < balanced_summary.player_win_rate
            or kind_summary.player_win_rate < evil_summary.player_win_rate
        )
    ):
        warnings.append("Kind DM produced a lower player win rate than balanced or evil DM.")

    return warnings


def determine_status(structural_issues: list[str], smoke_issues: list[str], signature_mechanic_count: int, simple_suggestion: str | None, warnings: list[str]) -> AuditStatus:
    if structural_issues or smoke_issues or signature_mechanic_count == 0:
        return "fail"
    if signature_mechanic_count < 5 or simple_suggestion or warnings:
        return "warn"
    return "pass"


def audit_scenario(
    preset_id: str,
    config: ScenarioAuditConfig | None = None,
    progress_callback: ScenarioAuditProgressCallback | None = None,
) -> ScenarioAuditRow:
    audit_config = config or ScenarioAuditConfig()
    preset = get_enemy_preset(preset_id)
    player_unit_ids = get_player_preset_unit_ids()

    emit_progress(progress_callback, preset_id, "structural", {"status": "start"})
    structural_issues = run_structural_pass(preset_id, audit_config.seed_prefix)
    emit_progress(
        progress_callback,
        preset_id,
        "structural",
        {"status": "complete", "issueCount": len(structural_issues)},
    )

    emit_progress(progress_callback, preset_id, "smoke", {"status": "start"})
    smoke_issues = run_smoke_pass(preset_id, audit_config, progress_callback)
    emit_progress(
        progress_callback,
        preset_id,
        "smoke",
        {"status": "complete", "issueCount": len(smoke_issues)},
    )

    emit_progress(progress_callback, preset_id, "mechanic", {"status": "start"})
    signature_breakdown, signature_mechanic_count = run_mechanic_pass(preset_id, audit_config, progress_callback)
    emit_progress(
        progress_callback,
        preset_id,
        "mechanic",
        {
            "status": "complete",
            "signatureMechanicCount": signature_mechanic_count,
            "signatureBreakdown": signature_breakdown,
        },
    )

    def on_health_progress(completed_runs: int, total_runs: int, monster_behavior: str) -> None:
        emit_progress(
            progress_callback,
            preset_id,
            "health",
            {
                "current": completed_runs,
                "total": total_runs,
                "monsterBehavior": monster_behavior,
            },
        )

    emit_progress(progress_callback, preset_id, "health", {"status": "start"})
    summary = run_batch(
        EncounterConfig(
            seed=f"{audit_config.seed_prefix}-{preset_id}-health",
            enemy_preset_id=preset_id,
            batch_size=audit_config.health_batch_size,
            player_behavior="balanced",
            monster_behavior="combined",
        ),
        progress_callback=on_health_progress if progress_callback else None,
    )
    emit_progress(
        progress_callback,
        preset_id,
        "health",
        {
            "status": "complete",
            "playerWinRate": float(summary.player_win_rate),
            "enemyWinRate": float(summary.goblin_win_rate),
        },
    )

    kind_summary = get_combination_summary(summary, "kind")
    balanced_summary = get_combination_summary(summary, "balanced")
    evil_summary = get_combination_summary(summary, "evil")
    simple_suggestion = build_simple_suggestion(preset_id, float(summary.player_win_rate), float(summary.goblin_win_rate))
    warnings = build_diagnostic_warnings(summary, signature_mechanic_count, structural_issues, smoke_issues)
    status = determine_status(structural_issues, smoke_issues, signature_mechanic_count, simple_suggestion, warnings)

    row = ScenarioAuditRow(
        scenario_id=preset.preset_id,
        display_name=preset.display_name,
        unit_count=len(preset.units) + len(player_unit_ids),
        combined_player_win_rate=float(summary.player_win_rate),
        combined_enemy_win_rate=float(summary.goblin_win_rate),
        smart_player_win_rate=float(summary.smart_player_win_rate) if summary.smart_player_win_rate is not None else None,
        dumb_player_win_rate=float(summary.dumb_player_win_rate) if summary.dumb_player_win_rate is not None else None,
        kind_player_win_rate=float(kind_summary.player_win_rate) if kind_summary is not None else None,
        balanced_player_win_rate=float(balanced_summary.player_win_rate) if balanced_summary is not None else None,
        evil_player_win_rate=float(evil_summary.player_win_rate) if evil_summary is not None else None,
        average_rounds=float(summary.average_rounds),
        signature_mechanic_count=signature_mechanic_count,
        status=status,
        simple_suggestion=simple_suggestion,
        warnings=warnings,
        signature_breakdown=signature_breakdown,
    )
    emit_progress(
        progress_callback,
        preset_id,
        "complete",
        {
            "status": row.status,
            "warningCount": len(row.warnings),
        },
    )
    return row


def audit_active_scenarios(
    config: ScenarioAuditConfig | None = None,
    scenario_ids: Iterable[str] | None = None,
    progress_callback: ScenarioAuditProgressCallback | None = None,
) -> list[ScenarioAuditRow]:
    audit_config = config or ScenarioAuditConfig()
    selected_ids = tuple(scenario_ids) if scenario_ids is not None else ACTIVE_SCENARIO_IDS
    return [audit_scenario(preset_id, audit_config, progress_callback) for preset_id in selected_ids]


def build_report_payload(rows: list[ScenarioAuditRow], config: ScenarioAuditConfig) -> dict[str, object]:
    return {
        "config": asdict(config),
        "activeScenarioIds": list(get_active_scenario_ids()),
        "rows": [row.to_report_dict() for row in rows],
    }


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def format_scenario_audit_report(rows: list[ScenarioAuditRow]) -> str:
    headers = [
        "scenarioId",
        "displayName",
        "unitCount",
        "combinedPlayerWinRate",
        "combinedEnemyWinRate",
        "smartPlayerWinRate",
        "dumbPlayerWinRate",
        "kindPlayerWinRate",
        "balancedPlayerWinRate",
        "evilPlayerWinRate",
        "averageRounds",
        "signatureMechanicCount",
        "status",
        "simpleSuggestion",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.scenario_id,
                    row.display_name,
                    str(row.unit_count),
                    format_percent(row.combined_player_win_rate),
                    format_percent(row.combined_enemy_win_rate),
                    format_percent(row.smart_player_win_rate),
                    format_percent(row.dumb_player_win_rate),
                    format_percent(row.kind_player_win_rate),
                    format_percent(row.balanced_player_win_rate),
                    format_percent(row.evil_player_win_rate),
                    f"{row.average_rounds:.2f}",
                    str(row.signature_mechanic_count),
                    row.status,
                    row.simple_suggestion or "-",
                ]
            )
            + " |"
        )

    for row in rows:
        if row.warnings:
            lines.append("")
            lines.append(f"{row.scenario_id}:")
            for warning in row.warnings:
                lines.append(f"- {warning}")

    return "\n".join(lines)


__all__ = [
    "ScenarioAuditConfig",
    "ScenarioAuditRow",
    "audit_active_scenarios",
    "audit_scenario",
    "build_full_scenario_audit_config",
    "build_report_payload",
    "build_quick_scenario_audit_config",
    "format_scenario_audit_report",
    "get_active_scenario_ids",
    "has_swallow_action",
]
