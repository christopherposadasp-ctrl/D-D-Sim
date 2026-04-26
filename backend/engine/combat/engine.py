from __future__ import annotations

from backend.content.attack_sequences import AttackStepDefinition
from backend.content.class_progressions import get_progression_scalar
from backend.content.combat_actions import action_prevents_opportunity_attacks, get_extra_movement_multiplier
from backend.content.enemies import (
    get_attack_action_definition_for_unit,
    get_monster_definition_for_unit,
    unit_has_trait,
)
from backend.content.feature_definitions import unit_has_feature
from backend.content.special_actions import get_special_action
from backend.content.spell_definitions import get_spell_definition
from backend.engine.ai.decision import (
    MovementPlan,
    TurnDecision,
    choose_turn_decision,
    get_enemy_melee_weapon_id,
    get_ranked_attack_targets,
    get_smart_precision_max_miss_margin,
)
from backend.engine.combat.setup import create_encounter
from backend.engine.models.state import (
    CombatEvent,
    DamageCandidate,
    DamageComponentResult,
    DamageDetails,
    EncounterConfig,
    EncounterState,
    EncounterSummary,
    Footprint,
    GridPosition,
    MovementDetails,
    RageEffect,
    ReplayFrame,
    RunEncounterResult,
    StepEncounterResult,
    UnitState,
)
from backend.engine.rules.combat_rules import (
    AttackRollOverrides,
    ResolveAttackArgs,
    ResolveSavingThrowArgs,
    SavingThrowOverrides,
    apply_damage,
    apply_heroism_start_of_turn,
    attempt_hide,
    attempt_lay_on_hands,
    attempt_natures_wrath,
    attempt_patient_defense,
    attempt_second_wind,
    attempt_stabilize,
    attempt_steady_aim,
    attempt_step_of_the_wind,
    can_use_battle_master_maneuver,
    attach_damage_result_event_fields,
    clear_invalid_hidden_effects,
    create_skip_event,
    expire_turn_effects,
    event_base,
    format_effect_kinds,
    get_active_rage_effect,
    get_attack_mode,
    build_cone_breath_targeting,
    choose_cold_breath_targeting,
    get_saving_throw_mode,
    maybe_commit_reckless_attack,
    pull_die,
    recalculate_effective_speed_for_unit,
    resolve_aid,
    resolve_attack,
    resolve_bless,
    resolve_burning_hands,
    resolve_cast_spell,
    resolve_death_save,
    resolve_multi_target_save_spell,
    resolve_poisoned_end_of_turn_save,
    resolve_ray_of_sickness_poison_save,
    resolve_saving_throw,
    resolve_restrained_end_of_turn_save,
    resolve_single_target_save_spell,
)
from backend.engine.rules.spatial import (
    build_position_index,
    chebyshev_distance,
    find_advance_path,
    get_active_grappler_ids,
    get_attack_context,
    get_melee_reach_squares,
    get_min_chebyshev_distance_between_footprints,
    get_occupied_squares_for_position,
    get_swallow_source_id,
    get_unit_footprint,
    is_active_grapple,
    is_unit_swallowed,
)
from backend.engine.utils.helpers import (
    clone_value,
    describe_winner,
    get_final_winner,
    get_remaining_hp,
    get_units_by_faction,
    is_unit_conscious,
    is_unit_stable_at_zero,
    unit_can_take_reactions,
    unit_sort_key,
)


def format_position(position: GridPosition) -> str:
    return f"({position.x},{position.y})"


def fighters_defeated(state: EncounterState) -> bool:
    return all(unit.current_hp == 0 or unit.conditions.dead for unit in get_units_by_faction(state, "fighters"))


def goblins_defeated(state: EncounterState) -> bool:
    return all(unit.conditions.dead for unit in get_units_by_faction(state, "goblins"))


def add_phase_event(state: EncounterState, actor_id: str, text_summary: str) -> CombatEvent:
    return CombatEvent(
        round=state.round,
        actor_id=actor_id,
        target_ids=[],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={"winner": state.winner},
        movement_details=None,
        damage_details=None,
        condition_deltas=[],
        text_summary=text_summary,
    )


def add_unit_phase_event(
    state: EncounterState,
    actor_id: str,
    target_id: str,
    text_summary: str,
    *,
    condition_deltas: list[str] | None = None,
    resolved_totals: dict[str, object] | None = None,
) -> CombatEvent:
    return CombatEvent(
        round=state.round,
        actor_id=actor_id,
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals=resolved_totals or {},
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas or [],
        text_summary=text_summary,
    )


def build_attack_reaction_pre_events(state: EncounterState, attack_event: CombatEvent) -> list[CombatEvent]:
    reaction_kind = attack_event.resolved_totals.get("defenseReaction")
    reaction_actor_id = attack_event.resolved_totals.get("defenseReactionActorId")
    if not reaction_kind or not reaction_actor_id or reaction_actor_id not in state.units:
        return []

    if reaction_kind == "shield":
        return [
            add_unit_phase_event(
                state,
                reaction_actor_id,
                attack_event.actor_id,
                f"{reaction_actor_id} casts Shield.",
                condition_deltas=[f"{reaction_actor_id} gains +5 AC until the start of its next turn."],
                resolved_totals={
                    "reaction": "shield",
                    "shieldAcBonus": attack_event.resolved_totals.get("shieldAcBonus", 5),
                    "spellSlotsLevel1Remaining": attack_event.resolved_totals.get("reactionSpellSlotsLevel1Remaining"),
                    "trigger": attack_event.resolved_totals.get("defenseReactionTrigger"),
                },
            )
        ]

    if reaction_kind == "uncanny_dodge":
        return [
            add_unit_phase_event(
                state,
                reaction_actor_id,
                reaction_actor_id,
                f"{reaction_actor_id} uses Uncanny Dodge.",
                condition_deltas=[
                    f"{reaction_actor_id} prevents {attack_event.resolved_totals.get('uncannyDodgeDamagePrevented', 0)} damage."
                ],
                resolved_totals={
                    "reaction": "uncanny_dodge",
                    "damagePrevented": attack_event.resolved_totals.get("uncannyDodgeDamagePrevented", 0),
                    "damageAfterUncannyDodge": attack_event.resolved_totals.get("damageAfterUncannyDodge", 0),
                },
            )
        ]

    return []


def build_attack_reaction_phase_events(state: EncounterState, attack_event: CombatEvent) -> list[CombatEvent]:
    reaction_kind = attack_event.resolved_totals.get("attackReaction")
    reaction_actor_id = attack_event.resolved_totals.get("reactionActorId")
    if not reaction_kind or not reaction_actor_id or reaction_actor_id not in state.units:
        return []

    if reaction_kind == "parry":
        return [
            add_unit_phase_event(
                state,
                reaction_actor_id,
                attack_event.actor_id,
                f"{reaction_actor_id} uses Parry against {attack_event.actor_id}.",
                condition_deltas=[f"{reaction_actor_id} raises AC by 2 against the incoming melee attack."],
                resolved_totals={"reaction": "parry"},
            )
        ]

    if reaction_kind == "redirect_attack":
        final_target_id = attack_event.target_ids[0] if attack_event.target_ids else reaction_actor_id
        return [
            add_unit_phase_event(
                state,
                reaction_actor_id,
                final_target_id,
                f"{reaction_actor_id} uses Redirect Attack and swaps with {final_target_id}.",
                condition_deltas=[f"{reaction_actor_id} redirects the attack onto {final_target_id}."],
                resolved_totals={"reaction": "redirect_attack", "redirectedTargetId": final_target_id},
            )
        ]

    return []


def maybe_resolve_riposte_follow_up(state: EncounterState, attack_event: CombatEvent) -> list[CombatEvent]:
    if attack_event.event_type != "attack" or attack_event.resolved_totals.get("hit") is not False:
        return []
    if attack_event.resolved_totals.get("spellId"):
        return []
    if not attack_event.target_ids or not attack_event.damage_details:
        return []

    defender_id = attack_event.target_ids[0]
    attacker_id = attack_event.actor_id
    defender = state.units.get(defender_id)
    attacker = state.units.get(attacker_id)
    if not defender or not attacker or defender.faction != "fighters" or attacker.faction == defender.faction:
        return []

    incoming_weapon = attacker.attacks.get(attack_event.damage_details.weapon_id)
    if not incoming_weapon or incoming_weapon.kind != "melee":
        return []
    if not unit_can_take_reactions(defender) or not can_use_battle_master_maneuver(defender, "riposte"):
        return []
    if attacker.conditions.dead or attacker.current_hp <= 0 or not attacker.position or not defender.position:
        return []

    riposte_weapon_id = get_opportunity_attack_weapon_id(defender)
    riposte_weapon = defender.attacks.get(riposte_weapon_id)
    if not riposte_weapon or not get_attack_context(state, defender_id, attacker_id, riposte_weapon).legal:
        return []

    precision_max_miss_margin = None
    if state.player_behavior == "smart":
        precision_max_miss_margin = get_smart_precision_max_miss_margin(
            state, defender, attacker, riposte_weapon, defender.resources.superiority_dice
        )
    elif state.player_behavior == "dumb":
        precision_max_miss_margin = 8

    defender.reaction_available = False
    phase_event = add_unit_phase_event(
        state,
        defender_id,
        attacker_id,
        f"{defender_id} uses Riposte against {attacker_id}.",
        condition_deltas=[f"{defender_id} spends a reaction on Riposte."],
        resolved_totals={"reaction": "riposte"},
    )
    riposte_attack, _ = resolve_attack(
        state,
        ResolveAttackArgs(
            attacker_id=defender_id,
            target_id=attacker_id,
            weapon_id=riposte_weapon_id,
            savage_attacker_available=unit_has_feature(defender, "savage_attacker"),
            maneuver_id="riposte",
            precision_max_miss_margin=precision_max_miss_margin,
        ),
    )
    events = [phase_event]
    events.extend(build_attack_reaction_pre_events(state, riposte_attack))
    events.extend(build_attack_reaction_phase_events(state, riposte_attack))
    events.append(riposte_attack)

    if state.units[attacker_id].conditions.dead:
        events.extend(release_grappled_targets_from_source(state, attacker_id, "source_dead"))
        events.extend(release_swallowed_units_from_source(state, attacker_id))

    return events


def get_legal_sentinel_guardian_weapon_id(
    state: EncounterState,
    reactor: UnitState,
    attacker: UnitState,
) -> str | None:
    try:
        weapon_id = get_opportunity_attack_weapon_id(reactor)
    except ValueError:
        return None

    weapon = reactor.attacks.get(weapon_id)
    if not weapon or not reactor.position or not attacker.position:
        return None
    if (
        get_min_chebyshev_distance_between_footprints(
            reactor.position,
            get_unit_footprint(reactor),
            attacker.position,
            get_unit_footprint(attacker),
        )
        > get_melee_reach_squares(weapon)
    ):
        return None
    if not get_attack_context(state, reactor.id, attacker.id, weapon).legal:
        return None
    return weapon_id


def maybe_resolve_sentinel_guardian_follow_up(state: EncounterState, attack_event: CombatEvent) -> list[CombatEvent]:
    if attack_event.event_type != "attack" or attack_event.resolved_totals.get("hit") is not True:
        return []
    if not attack_event.target_ids:
        return []

    attacker = state.units.get(attack_event.actor_id)
    target = state.units.get(attack_event.target_ids[0])
    if not attacker or not target or attacker.faction == target.faction:
        return []
    if attacker.conditions.dead or attacker.current_hp <= 0 or attacker.conditions.unconscious or not attacker.position:
        return []

    eligible_reactors: list[tuple[UnitState, str]] = []
    for reactor in state.units.values():
        if reactor.id == target.id:
            continue
        if reactor.faction != target.faction or not unit_has_feature(reactor, "sentinel"):
            continue
        if not unit_can_take_reactions(reactor):
            continue
        if reactor.conditions.dead or reactor.current_hp <= 0 or reactor.conditions.unconscious:
            continue

        weapon_id = get_legal_sentinel_guardian_weapon_id(state, reactor, attacker)
        if weapon_id:
            eligible_reactors.append((reactor, weapon_id))

    events: list[CombatEvent] = []
    for reactor, weapon_id in sorted(eligible_reactors, key=lambda item: unit_sort_key(item[0].id)):
        if not unit_can_take_reactions(reactor):
            continue
        if attacker.conditions.dead or attacker.current_hp <= 0 or attacker.conditions.unconscious:
            break
        if not get_legal_sentinel_guardian_weapon_id(state, reactor, attacker):
            continue

        reactor.reaction_available = False
        events.append(
            add_unit_phase_event(
                state,
                reactor.id,
                attacker.id,
                f"{reactor.id} uses Sentinel: Guardian against {attacker.id}.",
                condition_deltas=[f"{reactor.id} makes a Sentinel opportunity attack."],
                resolved_totals={"reaction": "sentinel_guardian"},
            )
        )
        guardian_attack, _ = resolve_attack(
            state,
            ResolveAttackArgs(
                attacker_id=reactor.id,
                target_id=attacker.id,
                weapon_id=weapon_id,
                savage_attacker_available=unit_has_feature(reactor, "savage_attacker"),
                is_opportunity_attack=True,
            ),
        )
        events.extend(build_attack_reaction_pre_events(state, guardian_attack))
        events.extend(build_attack_reaction_phase_events(state, guardian_attack))
        events.append(guardian_attack)
        events.extend(maybe_resolve_riposte_follow_up(state, guardian_attack))

        resolved_target_id = guardian_attack.target_ids[0] if guardian_attack.target_ids else attacker.id
        if state.units[resolved_target_id].conditions.dead:
            events.extend(release_grappled_targets_from_source(state, resolved_target_id, "source_dead"))
            events.extend(release_swallowed_units_from_source(state, resolved_target_id))

    return events


def update_encounter_phase(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    events: list[CombatEvent] = []

    if fighters_defeated(state) or goblins_defeated(state):
        state.winner = get_final_winner(state)
        state.terminal_state = "complete"
        state.rescue_subphase = False
        events.append(add_phase_event(state, actor_id, f"Combat ends. {describe_winner(state.winner)}."))

    return events


def clear_turn_flags(actor: UnitState) -> None:
    actor._cleave_used_this_turn = False
    actor._bonus_action_used_this_turn = False
    actor._great_weapon_master_hewing_used_this_turn = False
    actor._savage_attacker_used_this_turn = False
    actor._rage_extended_this_turn = False
    actor._reckless_attack_available_this_turn = unit_has_feature(actor, "reckless_attack")
    actor._steady_aim_active_this_turn = False


def expire_turn_end_effects(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    events: list[CombatEvent] = []

    for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id)):
        expired = [
            effect
            for effect in unit.temporary_effects
            if getattr(effect, "expires_at_turn_end_of", None) == actor_id
            and getattr(effect, "expires_at_round", state.round) <= state.round
        ]
        if not expired:
            continue

        unit.temporary_effects = [
            effect
            for effect in unit.temporary_effects
            if not (
                getattr(effect, "expires_at_turn_end_of", None) == actor_id
                and getattr(effect, "expires_at_round", state.round) <= state.round
            )
        ]
        recalculate_effective_speed_for_unit(unit)

        events.append(
            add_unit_phase_event(
                state,
                actor_id,
                unit.id,
                f"{format_effect_kinds(expired)} expire on {unit.id} at the end of {actor_id}'s turn.",
                condition_deltas=[f"Expired {format_effect_kinds(expired)} on {unit.id}."],
                resolved_totals={"expiredCount": len(expired), "unitId": unit.id},
            )
        )

    return events


def resolve_turn_end_rage(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    actor = state.units[actor_id]
    rage_effect = get_active_rage_effect(actor)
    if not rage_effect:
        actor._rage_qualified_since_turn_end = False
        actor._rage_extended_this_turn = False
        return []

    rage_effect.remaining_rounds -= 1

    if actor.conditions.dead or actor.current_hp <= 0 or actor.conditions.unconscious:
        actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "rage"]
        actor._rage_qualified_since_turn_end = False
        actor._rage_extended_this_turn = False
        return [
            add_unit_phase_event(
                state,
                actor_id,
                actor_id,
                f"{actor_id}'s rage ends because the barbarian is down.",
                condition_deltas=[f"{actor_id}'s rage ends."],
                resolved_totals={"rageActive": False, "reason": "downed"},
            )
        ]

    if rage_effect.remaining_rounds <= 0:
        actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "rage"]
        actor._rage_qualified_since_turn_end = False
        actor._rage_extended_this_turn = False
        return [
            add_unit_phase_event(
                state,
                actor_id,
                actor_id,
                f"{actor_id}'s rage ends after reaching its duration limit.",
                condition_deltas=[f"{actor_id}'s rage ends."],
                resolved_totals={"rageActive": False, "reason": "duration"},
            )
        ]

    if not (actor._rage_qualified_since_turn_end or actor._rage_extended_this_turn):
        actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "rage"]
        actor._rage_qualified_since_turn_end = False
        actor._rage_extended_this_turn = False
        return [
            add_unit_phase_event(
                state,
                actor_id,
                actor_id,
                f"{actor_id}'s rage ends without an attack, damage taken, or manual extension.",
                condition_deltas=[f"{actor_id}'s rage ends."],
                resolved_totals={"rageActive": False, "reason": "upkeep"},
            )
        ]

    actor._rage_qualified_since_turn_end = False
    actor._rage_extended_this_turn = False
    return []


def advance_initiative(state: EncounterState) -> None:
    next_index = state.active_combatant_index + 1
    if next_index >= len(state.initiative_order):
        state.active_combatant_index = 0
        state.round += 1
        return
    state.active_combatant_index = next_index


def get_opportunity_attack_weapon_id(unit: UnitState) -> str:
    preferred_order = ("greatsword", "scimitar", "greataxe", "spear", "bite", "club", "flail", "toad_bite", "crocodile_bite")
    melee_weapons = [(weapon_id, weapon) for weapon_id, weapon in unit.attacks.items() if weapon and weapon.kind == "melee"]

    if not melee_weapons:
        raise ValueError(f"{unit.id} has no melee weapon profile for an opportunity attack.")

    def sort_key(item: tuple[str, object]) -> tuple[int, int, int, str]:
        weapon_id, weapon = item
        preferred_index = preferred_order.index(weapon_id) if weapon_id in preferred_order else len(preferred_order)
        return (-get_melee_reach_squares(weapon), preferred_index, -weapon.attack_bonus, weapon_id)

    return sorted(melee_weapons, key=sort_key)[0][0]


def is_grappled(state: EncounterState | None, unit: UnitState) -> bool:
    if state is None:
        return any(effect.kind == "grappled_by" for effect in unit.temporary_effects)
    return bool(get_active_grappler_ids(state, unit.id))


def is_restrained(unit: UnitState) -> bool:
    return any(effect.kind == "restrained_by" for effect in unit.temporary_effects)


def get_move_squares(state: EncounterState | None, unit: UnitState) -> int:
    if is_grappled(state, unit) or is_restrained(unit):
        return 0
    return unit.effective_speed // 5


def get_stand_up_cost_squares(unit: UnitState) -> int:
    return unit._turn_stand_up_cost_squares


def get_movement_distance(movement: dict[str, object] | None) -> int:
    if not movement or len(movement["path"]) <= 1:
        return 0
    return len(movement["path"]) - 1


def get_total_movement_budget(
    actor: UnitState,
    action: dict[str, str],
    bonus_action: dict[str, str] | None = None,
    surged_action: dict[str, str] | None = None,
    *,
    state: EncounterState | None = None,
) -> int:
    move_squares = get_move_squares(state, actor)
    action_multiplier = int(action["kind"] == "dash") + int(bool(surged_action and surged_action["kind"] == "dash"))
    bonus_multiplier = get_extra_movement_multiplier(bonus_action["kind"] if bonus_action else None)
    total_budget = move_squares * (1 + action_multiplier + bonus_multiplier)
    return max(0, total_budget - get_stand_up_cost_squares(actor))


def get_tactical_shift_budget(actor: UnitState, state: EncounterState | None = None) -> int:
    if not unit_has_feature(actor, "tactical_shift"):
        return 0
    return max(0, get_move_squares(state, actor) // 2)


def movement_distance(movement: MovementPlan | None) -> int:
    if not movement or len(movement.path) <= 1:
        return 0
    return len(movement.path) - 1


def decision_movement_distance(decision: TurnDecision) -> int:
    return sum(
        movement_distance(movement)
        for movement in (decision.pre_action_movement, decision.between_action_movement, decision.post_action_movement)
    )


def is_tactical_shift_movement(movement: MovementPlan | None) -> bool:
    return bool(movement and movement.mode == "tactical_shift")


def is_landing_movement(movement: MovementPlan | None) -> bool:
    return bool(movement and movement.mode == "landing")


def is_cunning_withdraw_movement(movement: MovementPlan | None) -> bool:
    return bool(movement and movement.mode == "cunning_withdraw")


def get_cunning_withdraw_budget(actor: UnitState, state: EncounterState) -> int:
    return max(0, get_move_squares(state, actor) // 2)


def can_apply_tactical_shift(actor: UnitState, decision: TurnDecision) -> bool:
    return bool(
        unit_has_feature(actor, "tactical_shift")
        and decision.bonus_action
        and decision.bonus_action.get("kind") == "second_wind"
        and actor.resources.second_wind_uses > 0
        and actor.current_hp > 0
        and not actor.conditions.dead
        and not actor.conditions.unconscious
    )


def can_apply_cunning_withdraw(actor: UnitState, decision: TurnDecision) -> bool:
    return bool(
        unit_has_feature(actor, "cunning_strike")
        and decision.action
        and decision.action.get("kind") == "attack"
        and decision.action.get("cunning_strike_id") == "withdraw"
        and actor.current_hp > 0
        and not actor.conditions.dead
        and not actor.conditions.unconscious
    )


def bonus_action_applies_disengage(bonus_action: dict[str, str] | None) -> bool:
    if not bonus_action:
        return False
    return action_prevents_opportunity_attacks(bonus_action["kind"])


def resolve_turn_start_posture(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    actor = state.units[actor_id]
    actor._turn_stand_up_cost_squares = 0

    if actor.conditions.dead or actor.current_hp <= 0 or actor.conditions.unconscious or not actor.conditions.prone:
        return []

    # Grappled creatures have speed 0, so they cannot spend movement to stand.
    if get_move_squares(state, actor) <= 0:
        return []

    stand_up_cost_squares = max(1, (get_move_squares(state, actor) + 1) // 2)
    actor._turn_stand_up_cost_squares = stand_up_cost_squares
    actor.conditions.prone = False

    return [
        CombatEvent(
            round=state.round,
            actor_id=actor_id,
            target_ids=[actor_id],
            event_type="move",
            raw_rolls={},
            resolved_totals={
                "movementPhase": "stand_up",
                "movementCostSquares": stand_up_cost_squares,
                "movementCostFeet": stand_up_cost_squares * 5,
            },
            movement_details=None,
            damage_details=None,
            condition_deltas=[f"{actor_id} is no longer prone."],
            text_summary=f"{actor_id} stands up, spending {stand_up_cost_squares * 5} feet of movement.",
        )
    ]


def get_units_grappled_by(state: EncounterState, source_id: str) -> list[UnitState]:
    return sorted(
        [
            unit
            for unit in state.units.values()
            if any(effect.kind == "grappled_by" and effect.source_id == source_id for effect in unit.temporary_effects)
        ],
        key=lambda unit: unit_sort_key(unit.id),
    )


def get_units_swallowed_by(state: EncounterState, source_id: str) -> list[UnitState]:
    return sorted(
        [
            unit
            for unit in state.units.values()
            if any(effect.kind == "swallowed_by" and effect.source_id == source_id for effect in unit.temporary_effects)
        ],
        key=lambda unit: unit_sort_key(unit.id),
    )


def clear_source_bound_effects(unit: UnitState, source_id: str, effect_kinds: set[str]) -> None:
    unit.temporary_effects = [
        effect
        for effect in unit.temporary_effects
        if not (effect.kind in effect_kinds and getattr(effect, "source_id", None) == source_id)
    ]


def clear_external_grapple_and_restrain_effects(unit: UnitState, protected_source_id: str) -> list[str]:
    """Remove grapple/restraint effects applied by other creatures.

    Swallowing a target should end outside creatures' physical holds on that
    target. The swallowing creature's own source-bound effects stay in place so
    the internal swallowed state remains consistent.
    """

    released_sources: list[tuple[str, bool]] = []
    for effect in unit.temporary_effects:
        if effect.kind != "grappled_by" or effect.source_id == protected_source_id:
            continue
        had_restrained = any(
            active_effect.kind == "restrained_by" and active_effect.source_id == effect.source_id
            for active_effect in unit.temporary_effects
        )
        released_sources.append((effect.source_id, had_restrained))

    if not released_sources:
        return []

    released_source_ids = {source_id for source_id, _ in released_sources}
    unit.temporary_effects = [
        effect
        for effect in unit.temporary_effects
        if not (
            effect.kind in {"grappled_by", "restrained_by"}
            and getattr(effect, "source_id", None) in released_source_ids
        )
    ]

    condition_deltas: list[str] = []
    for source_id, had_restrained in released_sources:
        condition_deltas.append(f"{unit.id} is no longer grappled by {source_id}.")
        if had_restrained:
            condition_deltas.append(f"{unit.id} is no longer restrained by {source_id}.")

    return condition_deltas


def release_grappled_targets_from_source(state: EncounterState, source_id: str, reason: str) -> list[CombatEvent]:
    events: list[CombatEvent] = []

    for grappled_unit in get_units_grappled_by(state, source_id):
        # Swallowed targets are handled by the existing release-on-death flow so
        # they can be placed back onto the map correctly.
        if any(effect.kind == "swallowed_by" and effect.source_id == source_id for effect in grappled_unit.temporary_effects):
            continue

        had_restrained = any(
            effect.kind == "restrained_by" and effect.source_id == source_id for effect in grappled_unit.temporary_effects
        )
        clear_source_bound_effects(grappled_unit, source_id, {"grappled_by", "restrained_by", "blinded_by"})

        if grappled_unit.conditions.dead:
            continue

        condition_deltas = [f"{grappled_unit.id} is no longer grappled by {source_id}."]
        if had_restrained:
            condition_deltas.append(f"{grappled_unit.id} is no longer restrained by {source_id}.")

        text_summary = (
            f"{source_id} dies and releases {grappled_unit.id}."
            if reason == "source_dead"
            else f"{source_id} releases {grappled_unit.id} and looks for a new target."
        )
        events.append(
            CombatEvent(
                round=state.round,
                actor_id=source_id,
                target_ids=[grappled_unit.id],
                event_type="phase_change",
                raw_rolls={},
                resolved_totals={"releaseReason": reason},
                movement_details=None,
                damage_details=None,
                condition_deltas=condition_deltas,
                text_summary=text_summary,
            )
        )

    return events


def classify_invalid_grapple_reason(state: EncounterState, source_id: str) -> str:
    source = state.units.get(source_id)
    if not source or source.conditions.dead:
        return "source_dead"
    if source.current_hp <= 0 or source.conditions.unconscious:
        return "source_incapacitated"
    return "invalid_grapple"


def build_invalid_grapple_release_summary(reason: str, source_id: str, target_id: str) -> str:
    if reason == "source_dead":
        return f"{source_id} dies and releases {target_id}."
    if reason == "source_incapacitated":
        return f"{source_id} can no longer maintain the grapple on {target_id}."
    return f"{source_id} loses its hold on {target_id}."


def release_invalid_grappled_targets_at_turn_start(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    _ = actor_id
    events: list[CombatEvent] = []
    invalid_pairs: list[tuple[str, str, bool, str]] = []

    for target in sorted(state.units.values(), key=lambda unit: unit_sort_key(unit.id)):
        source_ids = sorted(
            {effect.source_id for effect in target.temporary_effects if effect.kind == "grappled_by"},
            key=unit_sort_key,
        )
        for source_id in source_ids:
            if any(effect.kind == "swallowed_by" and effect.source_id == source_id for effect in target.temporary_effects):
                continue
            if is_active_grapple(state, source_id, target.id):
                continue

            had_restrained = any(
                effect.kind == "restrained_by" and effect.source_id == source_id for effect in target.temporary_effects
            )
            invalid_pairs.append((source_id, target.id, had_restrained, classify_invalid_grapple_reason(state, source_id)))

    for source_id, target_id, had_restrained, reason in invalid_pairs:
        target = state.units[target_id]
        clear_source_bound_effects(target, source_id, {"grappled_by", "restrained_by", "blinded_by"})

        if target.conditions.dead:
            continue

        condition_deltas = [f"{target_id} is no longer grappled by {source_id}."]
        if had_restrained:
            condition_deltas.append(f"{target_id} is no longer restrained by {source_id}.")

        events.append(
            CombatEvent(
                round=state.round,
                actor_id=source_id,
                target_ids=[target_id],
                event_type="phase_change",
                raw_rolls={},
                resolved_totals={"releaseReason": reason},
                movement_details=None,
                damage_details=None,
                condition_deltas=condition_deltas,
                text_summary=build_invalid_grapple_release_summary(reason, source_id, target_id),
            )
        )

    return events


def is_release_square_open(state: EncounterState, released_unit_id: str, position: GridPosition, footprint: Footprint) -> bool:
    if not get_occupied_squares_for_position(position, footprint):
        return False

    for occupant in state.units.values():
        if occupant.id == released_unit_id or occupant.conditions.dead or not occupant.position or is_unit_swallowed(occupant):
            continue
        if get_min_chebyshev_distance_between_footprints(
            position,
            footprint,
            occupant.position,
            get_unit_footprint(occupant),
        ) == 0:
            return False

    return True


def find_nearest_release_square(state: EncounterState, source_unit: UnitState, released_unit: UnitState) -> GridPosition | None:
    if not source_unit.position:
        return None

    released_footprint = get_unit_footprint(released_unit)
    candidates: list[GridPosition] = []

    for x in range(1, 16):
        for y in range(1, 16):
            candidate = GridPosition(x=x, y=y)
            if not is_release_square_open(state, released_unit.id, candidate, released_footprint):
                continue
            if get_min_chebyshev_distance_between_footprints(
                candidate,
                released_footprint,
                source_unit.position,
                get_unit_footprint(source_unit),
            ) != 1:
                continue
            candidates.append(candidate)

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda position: (
            get_min_chebyshev_distance_between_footprints(
                position,
                released_footprint,
                source_unit.position,
                get_unit_footprint(source_unit),
            ),
            position.x,
            position.y,
        ),
    )[0]


def release_swallowed_units_from_source(state: EncounterState, source_id: str) -> list[CombatEvent]:
    source_unit = state.units[source_id]
    events: list[CombatEvent] = []

    for swallowed_unit in get_units_swallowed_by(state, source_id):
        clear_source_bound_effects(
            swallowed_unit,
            source_id,
            {"swallowed_by", "grappled_by", "restrained_by", "blinded_by"},
        )

        if swallowed_unit.conditions.dead:
            continue

        release_position = find_nearest_release_square(state, source_unit, swallowed_unit)
        if release_position:
            swallowed_unit.position = release_position.model_copy(deep=True)
            swallowed_unit.conditions.prone = True

        events.append(
            CombatEvent(
                round=state.round,
                actor_id=source_id,
                target_ids=[swallowed_unit.id],
                event_type="phase_change",
                raw_rolls={},
                resolved_totals={
                    "releasePosition": format_position(release_position) if release_position else None,
                },
                movement_details=None,
                damage_details=None,
                condition_deltas=[
                    f"{swallowed_unit.id} is released from {source_id}."
                ],
                text_summary=(
                    f"{source_id} dies and releases {swallowed_unit.id}"
                    + (
                        f" at {format_position(release_position)}."
                        if release_position
                        else " without a legal adjacent landing square."
                    )
                ),
            )
        )

    return events


def build_ongoing_damage_event(
    state: EncounterState,
    actor_id: str,
    target_id: str,
    raw_rolls: list[int],
    total_damage: int,
    damage_result,
) -> CombatEvent:
    component = DamageComponentResult(
        damage_type="acid",
        raw_rolls=list(raw_rolls),
        adjusted_rolls=list(raw_rolls),
        subtotal=sum(raw_rolls),
        flat_modifier=0,
        total_damage=total_damage,
    )
    candidate = DamageCandidate(
        components=[component],
        raw_rolls=list(raw_rolls),
        adjusted_rolls=list(raw_rolls),
        subtotal=sum(raw_rolls),
    )

    return CombatEvent(
        round=state.round,
        actor_id=actor_id,
        target_ids=[target_id],
        event_type="ongoing_damage",
        raw_rolls={"damageRolls": raw_rolls},
        resolved_totals={"damageType": "acid", "damageTotal": total_damage},
        movement_details=None,
        damage_details=DamageDetails(
            weapon_id="swallow_acid",
            weapon_name="Swallowed Acid",
            damage_components=[component],
            primary_candidate=candidate,
            savage_candidate=None,
            chosen_candidate="primary",
            critical_applied=False,
            critical_multiplier=1,
            flat_modifier=0,
            advantage_bonus_candidate=None,
            mastery_applied=None,
            mastery_notes=None,
            attack_riders_applied=None,
            total_damage=total_damage,
            resisted_damage=damage_result.resisted_damage,
            amplified_damage=damage_result.amplified_damage or None,
            temporary_hp_absorbed=damage_result.temporary_hp_absorbed,
            final_damage_to_hp=damage_result.final_damage_to_hp,
            hp_delta=damage_result.hp_delta,
        ),
        condition_deltas=damage_result.condition_deltas,
        text_summary=(
            f"{target_id} takes {total_damage} acid damage while swallowed by {actor_id}"
            f"{f' ({damage_result.resisted_damage} resisted)' if damage_result.resisted_damage > 0 else ''}"
            f"{f' (+{damage_result.amplified_damage} vulnerability)' if damage_result.amplified_damage > 0 else ''}."
        ),
    )


def resolve_cold_breath_recharge(
    state: EncounterState,
    actor_id: str,
    *,
    roll_override: int | None = None,
) -> CombatEvent | None:
    actor = state.units[actor_id]
    if actor.current_hp <= 0 or actor.conditions.dead:
        return None
    if "cold_breath_available" not in actor.resource_pools:
        return None
    if actor.resource_pools.get("cold_breath_available", 0) > 0:
        return None

    recharge_roll = pull_die(state, 6, roll_override)
    success = recharge_roll >= 5
    if success:
        actor.resource_pools["cold_breath_available"] = 1

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={"rechargeRoll": recharge_roll},
        resolved_totals={
            "specialAction": "cold_breath",
            "rechargeThreshold": 5,
            "rechargeSucceeded": success,
            "coldBreathAvailable": actor.resource_pools.get("cold_breath_available", 0),
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[f"{actor_id}'s Cold Breath recharges."] if success else [],
        text_summary=(
            f"{actor_id} rolls {recharge_roll} to recharge Cold Breath: "
            f"{'recharged' if success else 'not recharged'}."
        ),
    )


def apply_start_of_turn_ongoing_effects(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    actor = state.units[actor_id]
    events: list[CombatEvent] = []
    heroism_event = apply_heroism_start_of_turn(state, actor_id)
    if heroism_event:
        events.append(heroism_event)
    cold_breath_recharge_event = resolve_cold_breath_recharge(state, actor_id)
    if cold_breath_recharge_event:
        events.append(cold_breath_recharge_event)

    if actor.combat_role != "giant_toad":
        return events

    for swallowed_unit in get_units_swallowed_by(state, actor_id):
        if swallowed_unit.conditions.dead:
            continue

        raw_rolls = [pull_die(state, 6), pull_die(state, 6), pull_die(state, 6)]
        total_damage = sum(raw_rolls)
        from backend.engine.rules.combat_rules import apply_damage

        damage_component = DamageComponentResult(
            damage_type="acid",
            raw_rolls=list(raw_rolls),
            adjusted_rolls=list(raw_rolls),
            subtotal=sum(raw_rolls),
            flat_modifier=0,
            total_damage=total_damage,
        )
        damage_result = apply_damage(state, swallowed_unit.id, [damage_component], False)
        events.append(
            build_ongoing_damage_event(
                state,
                actor_id,
                swallowed_unit.id,
                raw_rolls,
                total_damage,
                damage_result,
            )
        )

        if fighters_defeated(state):
            break

    return events


def can_use_swallow_special_action(state: EncounterState, actor_id: str, target_id: str) -> bool:
    actor = state.units[actor_id]
    target = state.units[target_id]
    if actor.combat_role != "giant_toad" or target.conditions.dead:
        return False
    if target.size_category not in {"tiny", "small", "medium"}:
        return False
    if get_swallow_source_id(target) is not None:
        return False
    return is_active_grapple(state, actor_id, target_id)


def resolve_special_action(state: EncounterState, actor_id: str, action: dict[str, object]) -> CombatEvent:
    action_id = str(action.get("action_id") or "")
    target_id = action.get("target_id")

    if action_id:
        get_special_action(action_id)

    if action_id == "natures_wrath":
        raw_target_ids = action.get("target_ids")
        target_ids = [str(target_id)] if target_id else []
        if isinstance(raw_target_ids, list):
            target_ids = [str(candidate_id) for candidate_id in raw_target_ids]
        return attempt_natures_wrath(state, actor_id, target_ids)

    if not isinstance(target_id, str):
        target_id = None

    if action_id != "swallow" or not target_id or not can_use_swallow_special_action(state, actor_id, target_id):
        return create_skip_event(state, actor_id, "Special action is not legal.")

    target = state.units[target_id]
    clear_source_bound_effects(target, actor_id, {"swallowed_by", "blinded_by"})
    condition_deltas = clear_external_grapple_and_restrain_effects(target, actor_id)
    from backend.engine.models.state import BlindedEffect, SwallowedEffect

    target.temporary_effects.append(BlindedEffect(kind="blinded_by", source_id=actor_id))
    target.temporary_effects.append(SwallowedEffect(kind="swallowed_by", source_id=actor_id))
    target.position = None

    return CombatEvent(
        round=state.round,
        actor_id=actor_id,
        target_ids=[target_id],
        event_type="attack",
        raw_rolls={},
        resolved_totals={"specialAction": action_id, "success": True},
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas
        + [
            f"{target_id} is swallowed by {actor_id}.",
            f"{target_id} is blinded inside {actor_id}.",
        ],
        text_summary=f"{actor_id} swallows {target_id}.",
    )


def build_cold_breath_damage_component(base_rolls: list[int], applied_damage: int) -> list[DamageComponentResult]:
    return [
        DamageComponentResult(
            damage_type="cold",
            raw_rolls=list(base_rolls),
            adjusted_rolls=list(base_rolls),
            subtotal=sum(base_rolls),
            flat_modifier=0,
            total_damage=applied_damage,
        )
    ]


def resolve_cold_breath(
    state: EncounterState,
    actor_id: str,
    action: dict[str, object],
    overrides: AttackRollOverrides | None = None,
) -> list[CombatEvent]:
    actor = state.units[actor_id]
    target_id = action.get("target_id")
    required_target_id = str(target_id) if isinstance(target_id, str) else None

    if "cold_breath" not in get_monster_definition_for_unit(actor).special_action_ids:
        return [create_skip_event(state, actor_id, "Cold Breath is not available to this creature.")]
    if actor.resource_pools.get("cold_breath_available", 0) <= 0:
        return [create_skip_event(state, actor_id, "Cold Breath has not recharged.")]

    origin = None
    direction = action.get("direction")
    if "origin_x" in action and "origin_y" in action:
        origin = GridPosition(x=int(action["origin_x"]), y=int(action["origin_y"]))

    targeting = (
        build_cone_breath_targeting(
            state,
            actor_id,
            origin=origin,
            direction=str(direction),
            range_squares=6,
            required_primary_target_id=required_target_id,
        )
        if origin and isinstance(direction, str)
        else choose_cold_breath_targeting(
            state,
            actor_id,
            required_primary_target_id=required_target_id,
            minimum_enemy_targets=1,
            allow_allies=True,
        )
    )
    if not targeting:
        return [create_skip_event(state, actor_id, "Cold Breath has no legal cone.")]

    actor.resource_pools["cold_breath_available"] = 0
    damage_rolls_override = list(overrides.damage_rolls if overrides else [])
    save_rolls_override = list(overrides.save_rolls if overrides else [])
    concentration_rolls_override = list(overrides.concentration_rolls if overrides else [])
    damage_rolls = [pull_die(state, 8, damage_rolls_override.pop(0) if damage_rolls_override else None) for _ in range(9)]
    full_damage = sum(damage_rolls)
    save_dc = 15

    events: list[CombatEvent] = [
        CombatEvent(
            **event_base(state, actor_id),
            target_ids=list(targeting.target_ids),
            event_type="phase_change",
            raw_rolls={},
            resolved_totals={
                "specialAction": "cold_breath",
                "origin": format_position(targeting.origin),
                "direction": targeting.direction,
                "enemyTargetCount": len(targeting.enemy_target_ids),
                "allyTargetCount": len(targeting.ally_target_ids),
                "coldBreathAvailable": actor.resource_pools.get("cold_breath_available", 0),
            },
            movement_details=None,
            damage_details=None,
            condition_deltas=[],
            text_summary=(
                f"{actor_id} exhales Cold Breath, catching "
                f"{len(targeting.enemy_target_ids)} enemies and {len(targeting.ally_target_ids)} allies."
            ),
        )
    ]

    for resolved_target_id in targeting.target_ids:
        target = state.units[resolved_target_id]
        save_mode, _, _ = get_saving_throw_mode(target, "con")
        save_roll_count = 1 if save_mode == "normal" else 2
        save_rolls = [save_rolls_override.pop(0) for _ in range(min(save_roll_count, len(save_rolls_override)))]
        save_event = resolve_saving_throw(
            state,
            ResolveSavingThrowArgs(
                actor_id=resolved_target_id,
                ability="con",
                dc=save_dc,
                reason="Cold Breath",
                overrides=SavingThrowOverrides(save_rolls=save_rolls),
            ),
        )
        save_success = bool(save_event.resolved_totals["success"])
        applied_damage = full_damage // 2 if save_success else full_damage
        damage_components = build_cold_breath_damage_component(damage_rolls, applied_damage)
        damage_result = apply_damage(
            state,
            resolved_target_id,
            damage_components,
            False,
            concentration_save_rolls=concentration_rolls_override,
        )
        events.append(save_event)
        raw_rolls = {"damageRolls": list(damage_rolls)}
        resolved_totals = {
            "specialAction": "cold_breath",
            "saveAbility": "con",
            "saveDc": save_dc,
            "saveSucceeded": save_success,
            "fullDamage": full_damage,
            "halfOnSuccess": True,
        }
        attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)
        events.append(
            CombatEvent(
                **event_base(state, actor_id),
                target_ids=[resolved_target_id],
                event_type="attack",
                raw_rolls=raw_rolls,
                resolved_totals=resolved_totals,
                movement_details=None,
                damage_details=DamageDetails(
                    weapon_id="cold_breath",
                    weapon_name="Cold Breath",
                    damage_components=damage_components,
                    primary_candidate=None,
                    savage_candidate=None,
                    chosen_candidate=None,
                    critical_applied=False,
                    critical_multiplier=1,
                    flat_modifier=0,
                    advantage_bonus_candidate=None,
                    mastery_applied=None,
                    mastery_notes=None,
                    attack_riders_applied=None,
                    total_damage=applied_damage,
                    resisted_damage=damage_result.resisted_damage,
                    amplified_damage=damage_result.amplified_damage or None,
                    temporary_hp_absorbed=damage_result.temporary_hp_absorbed,
                    final_damage_to_hp=damage_result.final_damage_to_hp,
                    hp_delta=damage_result.hp_delta,
                ),
                condition_deltas=list(damage_result.condition_deltas),
                text_summary=(
                    f"{actor_id}'s Cold Breath hits {resolved_target_id} for {applied_damage} cold damage"
                    f"{' after a successful save' if save_success else ' after a failed save'}"
                    f"{f' ({damage_result.resisted_damage} resisted)' if damage_result.resisted_damage > 0 else ''}"
                    f"{f' (+{damage_result.amplified_damage} vulnerability)' if damage_result.amplified_damage > 0 else ''}."
                ),
            )
        )

        if state.units[resolved_target_id].conditions.dead:
            events.extend(release_grappled_targets_from_source(state, resolved_target_id, "source_dead"))
            events.extend(release_swallowed_units_from_source(state, resolved_target_id))

    return events


def resolve_special_action_events(
    state: EncounterState,
    actor_id: str,
    action: dict[str, object],
    *,
    overrides: AttackRollOverrides | None = None,
) -> list[CombatEvent]:
    if action.get("action_id") == "cold_breath":
        return resolve_cold_breath(state, actor_id, action, overrides)
    return [resolve_special_action(state, actor_id, action)]


def get_expected_weapon_damage(weapon, attack_mode: str) -> float:
    def average_damage_for_components(components) -> float:
        return sum(
            sum(spec.count * (spec.sides + 1) / 2 for spec in component.damage_dice) + component.damage_modifier
            for component in components
        )

    if weapon.damage_components:
        average_damage = average_damage_for_components(weapon.damage_components)
    else:
        average_damage = sum(spec.count * (spec.sides + 1) / 2 for spec in weapon.damage_dice) + weapon.damage_modifier

    if attack_mode == "advantage":
        if weapon.advantage_damage_dice:
            average_damage += sum(spec.count * (spec.sides + 1) / 2 for spec in weapon.advantage_damage_dice)
        if weapon.advantage_damage_components:
            average_damage += average_damage_for_components(weapon.advantage_damage_components)

    return average_damage


def choose_step_weapon_for_target(
    state: EncounterState,
    actor_id: str,
    target_id: str,
    attack_step: AttackStepDefinition,
    preferred_weapon_id: str | None,
) -> str | None:
    actor = state.units[actor_id]
    target = state.units[target_id]
    best_choice: tuple[tuple[int, int, float, int], str] | None = None
    attack_mode_priority = {"advantage": 2, "normal": 1, "disadvantage": 0}

    for order_index, weapon_id in enumerate(attack_step.allowed_weapon_ids):
        weapon = actor.attacks.get(weapon_id)
        if not weapon:
            continue
        if weapon.resource_pool_id and actor.resources.get_pool(weapon.resource_pool_id) <= 0:
            continue

        attack_context = get_attack_context(state, actor_id, target_id, weapon)
        if not attack_context.legal:
            continue

        attack_mode, _, _ = get_attack_mode(state, actor, actor_id, target, target_id, weapon)
        score = (
            attack_mode_priority[attack_mode],
            1 if weapon_id == preferred_weapon_id else 0,
            get_expected_weapon_damage(weapon, attack_mode),
            -order_index,
        )

        if best_choice is None or score > best_choice[0]:
            best_choice = (score, weapon_id)

    return best_choice[1] if best_choice else None


def choose_attack_step_target_and_weapon(
    state: EncounterState,
    actor_id: str,
    attack_step: AttackStepDefinition,
    preferred_target_id: str | None,
    preferred_weapon_id: str | None,
    *,
    action_id: str | None = None,
    step_index: int = 0,
) -> tuple[str, str] | None:
    actor = state.units[actor_id]

    for target in get_ranked_attack_targets(
        state,
        actor,
        preferred_target_id,
        preferred_weapon_id=preferred_weapon_id,
        action_id=action_id,
        step_index=step_index,
    ):
        if target.conditions.dead:
            continue

        selected_weapon_id = choose_step_weapon_for_target(
            state,
            actor_id,
            target.id,
            attack_step,
            preferred_weapon_id,
        )
        if selected_weapon_id:
            return target.id, selected_weapon_id

    return None


def choose_rampage_follow_up(state: EncounterState, actor_id: str, weapon_id: str) -> tuple[str, list[GridPosition]] | None:
    actor = state.units[actor_id]
    weapon = actor.attacks.get(weapon_id)
    if not actor.position or not weapon:
        return None

    position_index = build_position_index(state)
    half_speed_squares = max(0, get_move_squares(state, actor) // 2)

    for target in get_ranked_attack_targets(state, actor):
        if target.conditions.dead or target.current_hp <= 0 or target.conditions.unconscious:
            continue

        if get_attack_context(state, actor_id, target.id, weapon, position_index=position_index).legal:
            return target.id, [actor.position.model_copy(deep=True)]

        if half_speed_squares <= 0:
            continue

        advance = find_advance_path(state, actor_id, target.id, half_speed_squares, position_index)
        if not advance or not advance.path:
            continue

        original_position = actor.position.model_copy(deep=True)
        actor.position = advance.path[-1].model_copy(deep=True)
        legal_after_move = get_attack_context(state, actor_id, target.id, weapon, position_index=build_position_index(state)).legal
        actor.position = original_position
        if legal_after_move:
            return target.id, advance.path

    return None


def maybe_resolve_rampage_follow_up(state: EncounterState, actor_id: str, triggering_attack: CombatEvent) -> list[CombatEvent]:
    actor = state.units[actor_id]
    if actor.faction != "goblins" or not unit_has_trait(actor, "rampage"):
        return []
    if actor.resource_pools.get("rampage_uses", 0) <= 0:
        return []
    if not triggering_attack.resolved_totals.get("hit"):
        return []
    if not triggering_attack.resolved_totals.get("targetWasBloodiedBeforeHit"):
        return []
    if not triggering_attack.damage_details:
        return []

    applied_damage = (
        triggering_attack.damage_details.final_damage_to_hp + triggering_attack.damage_details.temporary_hp_absorbed
    )
    if applied_damage <= 0:
        return []

    melee_weapon_id = get_enemy_melee_weapon_id(actor)
    follow_up = choose_rampage_follow_up(state, actor_id, melee_weapon_id)
    if not follow_up:
        return []

    target_id, path = follow_up
    events: list[CombatEvent] = []
    if len(path) > 1:
        movement_events, interrupted = execute_movement(
            state,
            actor_id,
            MovementPlan(path=path, mode="move"),
            False,
            "after_action",
        )
        events.extend(movement_events)
        if interrupted or state.units[actor_id].conditions.dead or state.units[actor_id].current_hp <= 0:
            return events

    weapon = state.units[actor_id].attacks.get(melee_weapon_id)
    if not weapon or not get_attack_context(state, actor_id, target_id, weapon).legal:
        return events

    actor.resource_pools["rampage_uses"] = max(0, actor.resource_pools.get("rampage_uses", 0) - 1)
    events.append(
        add_unit_phase_event(
            state,
            actor_id,
            target_id,
            f"{actor_id} uses Rampage.",
            condition_deltas=[f"{actor_id} moves up to half Speed and makes a bonus melee attack."],
            resolved_totals={"reaction": "rampage", "rampageUsesRemaining": actor.resource_pools.get("rampage_uses", 0)},
        )
    )

    follow_up_attack, _ = resolve_attack(
        state,
        ResolveAttackArgs(
            attacker_id=actor_id,
            target_id=target_id,
            weapon_id=melee_weapon_id,
            savage_attacker_available=unit_has_feature(actor, "savage_attacker"),
        ),
    )
    events.extend(build_attack_reaction_pre_events(state, follow_up_attack))
    events.extend(build_attack_reaction_phase_events(state, follow_up_attack))
    events.append(follow_up_attack)

    if follow_up_attack.target_ids and state.units[follow_up_attack.target_ids[0]].conditions.dead:
        dead_target_id = follow_up_attack.target_ids[0]
        events.extend(release_grappled_targets_from_source(state, dead_target_id, "source_dead"))
        events.extend(release_swallowed_units_from_source(state, dead_target_id))

    return events


def get_cleave_follow_up_target_id(
    state: EncounterState,
    actor_id: str,
    original_target_id: str,
    weapon_id: str,
) -> str | None:
    actor = state.units[actor_id]
    original_target = state.units[original_target_id]
    weapon = actor.attacks.get(weapon_id)

    if (
        not weapon
        or weapon.mastery != "cleave"
        or actor._cleave_used_this_turn
        or not actor.position
        or not original_target.position
    ):
        return None

    legal_targets = [
        unit
        for unit in state.units.values()
        if unit.faction != actor.faction
        and unit.id != original_target_id
        and not unit.conditions.dead
        and unit.current_hp > 0
        and unit.position
        and get_min_chebyshev_distance_between_footprints(
            unit.position,
            get_unit_footprint(unit),
            original_target.position,
            get_unit_footprint(original_target),
        )
        <= 1
        and get_attack_context(state, actor_id, unit.id, weapon).legal
    ]

    if not legal_targets:
        return None

    if actor.faction == "fighters" and state.player_behavior == "smart":
        return sorted(
            legal_targets,
            key=lambda unit: (
                unit.current_hp,
                get_min_chebyshev_distance_between_footprints(
                    actor.position,
                    get_unit_footprint(actor),
                    unit.position,
                    get_unit_footprint(unit),
                ),
                unit_sort_key(unit.id),
            ),
        )[0].id

    return sorted(legal_targets, key=lambda unit: unit_sort_key(unit.id))[0].id


def maybe_resolve_cleave_follow_up(
    state: EncounterState,
    actor_id: str,
    original_target_id: str,
    weapon_id: str,
    savage_attacker_available: bool,
) -> tuple[list[CombatEvent], bool, str | None]:
    cleave_target_id = get_cleave_follow_up_target_id(state, actor_id, original_target_id, weapon_id)
    if not cleave_target_id:
        return [], False, None

    actor = state.units[actor_id]
    actor._cleave_used_this_turn = True

    follow_up_event, savage_consumed = resolve_attack(
        state,
        ResolveAttackArgs(
            attacker_id=actor_id,
            target_id=cleave_target_id,
            weapon_id=weapon_id,
            savage_attacker_available=savage_attacker_available,
            omit_ability_modifier_damage=True,
        ),
    )

    return [follow_up_event], savage_consumed, cleave_target_id


def get_great_weapon_master_hewing_trigger(
    events: list[CombatEvent],
    actor_id: str,
) -> CombatEvent | None:
    for event in events:
        if event.actor_id != actor_id or event.event_type != "attack":
            continue
        if event.resolved_totals.get("greatWeaponMasterHewingTrigger") is True:
            return event
    return None


def get_great_weapon_master_hewing_target_id(
    state: EncounterState,
    actor_id: str,
    trigger_event: CombatEvent,
    weapon_id: str,
) -> str | None:
    actor = state.units[actor_id]
    weapon = actor.attacks.get(weapon_id)
    if not weapon:
        return None

    original_target_id = trigger_event.target_ids[0] if trigger_event.target_ids else None
    if original_target_id:
        original_target = state.units.get(original_target_id)
        if (
            original_target
            and original_target.current_hp > 0
            and not original_target.conditions.dead
            and not original_target.conditions.unconscious
            and get_attack_context(state, actor_id, original_target_id, weapon).legal
        ):
            return original_target_id

    for target in get_ranked_attack_targets(state, actor, preferred_weapon_id=weapon_id):
        if target.current_hp <= 0 or target.conditions.dead or target.conditions.unconscious:
            continue
        if get_attack_context(state, actor_id, target.id, weapon).legal:
            return target.id

    return None


def maybe_resolve_great_weapon_master_hewing(
    state: EncounterState,
    actor_id: str,
    turn_events: list[CombatEvent],
    *,
    planned_bonus_action: dict[str, str] | None,
) -> list[CombatEvent]:
    actor = state.units[actor_id]
    if planned_bonus_action or actor._bonus_action_used_this_turn:
        return []
    if actor._great_weapon_master_hewing_used_this_turn:
        return []
    if not unit_has_feature(actor, "great_weapon_master"):
        return []
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return []

    trigger_event = get_great_weapon_master_hewing_trigger(turn_events, actor_id)
    if not trigger_event or not trigger_event.damage_details:
        return []

    weapon_id = trigger_event.damage_details.weapon_id
    target_id = get_great_weapon_master_hewing_target_id(state, actor_id, trigger_event, weapon_id)
    if not target_id:
        return []

    actor._bonus_action_used_this_turn = True
    actor._great_weapon_master_hewing_used_this_turn = True
    trigger_reason = trigger_event.resolved_totals.get("greatWeaponMasterHewingTriggerReason") or "trigger"
    phase_event = add_unit_phase_event(
        state,
        actor_id,
        target_id,
        f"{actor_id} uses Great Weapon Master: Hew against {target_id}.",
        condition_deltas=[f"{actor_id} makes a Hew bonus attack after a {trigger_reason}."],
        resolved_totals={
            "bonusAction": "great_weapon_master_hewing",
            "triggerReason": trigger_reason,
        },
    )
    hewing_attack, savage_consumed = resolve_attack(
        state,
        ResolveAttackArgs(
            attacker_id=actor_id,
            target_id=target_id,
            weapon_id=weapon_id,
            savage_attacker_available=unit_has_feature(actor, "savage_attacker")
            and not actor._savage_attacker_used_this_turn,
        ),
    )
    if savage_consumed:
        actor._savage_attacker_used_this_turn = True

    events = [phase_event]
    events.extend(build_attack_reaction_pre_events(state, hewing_attack))
    events.extend(build_attack_reaction_phase_events(state, hewing_attack))
    events.append(hewing_attack)

    for hewing_target_id in hewing_attack.target_ids:
        if state.units[hewing_target_id].conditions.dead:
            events.extend(release_grappled_targets_from_source(state, hewing_target_id, "source_dead"))
            events.extend(release_swallowed_units_from_source(state, hewing_target_id))

    return events


def get_attack_step_maneuver_intent(action: dict[str, str], step_index: int) -> tuple[str | None, int | None]:
    maneuver_intents = action.get("maneuver_intents")
    if isinstance(maneuver_intents, list) and step_index < len(maneuver_intents):
        step_intent = maneuver_intents[step_index]
        if isinstance(step_intent, dict):
            return step_intent.get("maneuver_id"), step_intent.get("precision_max_miss_margin")

    return action.get("maneuver_id"), action.get("precision_max_miss_margin")


def get_attack_step_cunning_strike_intent(action: dict[str, str], step_index: int) -> str | None:
    cunning_strike_intents = action.get("cunning_strike_intents")
    if isinstance(cunning_strike_intents, list) and step_index < len(cunning_strike_intents):
        step_intent = cunning_strike_intents[step_index]
        if isinstance(step_intent, dict):
            return step_intent.get("cunning_strike_id")
        if isinstance(step_intent, str):
            return step_intent

    return action.get("cunning_strike_id")


def resolve_attack_action(
    state: EncounterState,
    actor_id: str,
    action: dict[str, str],
    *,
    step_overrides: list[AttackRollOverrides] | None = None,
) -> list[CombatEvent]:
    actor = state.units[actor_id]
    preferred_target_id = action.get("target_id")
    preferred_weapon_id = action.get("weapon_id")
    attack_action = get_attack_action_definition_for_unit(
        actor,
        preferred_weapon_id=preferred_weapon_id,
        action_id=action.get("attack_action_id"),
    )

    attack_events: list[CombatEvent] = []
    savage_attacker_available = unit_has_feature(actor, "savage_attacker")

    # Each attack step is resolved against the live state so later steps can
    # redirect after a kill or swap weapons when the next target calls for it.
    for step_index, attack_step in enumerate(attack_action.steps):
        if state.units[actor_id].conditions.dead or state.units[actor_id].current_hp <= 0:
            break

        selected_target_and_weapon = choose_attack_step_target_and_weapon(
            state,
            actor_id,
            attack_step,
            preferred_target_id,
            preferred_weapon_id,
            action_id=attack_action.action_id,
            step_index=step_index,
        )
        if not selected_target_and_weapon:
            if step_index == 0 and not attack_events:
                return [create_skip_event(state, actor_id, "No legal attack target is available.")]
            break

        target_id, weapon_id = selected_target_and_weapon
        if step_index == 0:
            reckless_event = maybe_commit_reckless_attack(state, actor_id, target_id, weapon_id)
            if reckless_event:
                attack_events.append(reckless_event)
        maneuver_id, precision_max_miss_margin = get_attack_step_maneuver_intent(action, step_index)
        cunning_strike_id = get_attack_step_cunning_strike_intent(action, step_index)
        attack_event, savage_consumed = resolve_attack(
            state,
            ResolveAttackArgs(
                attacker_id=actor_id,
                target_id=target_id,
                weapon_id=weapon_id,
                savage_attacker_available=savage_attacker_available,
                overrides=step_overrides[step_index] if step_overrides and step_index < len(step_overrides) else None,
                maneuver_id=maneuver_id,
                precision_max_miss_margin=precision_max_miss_margin,
                great_weapon_master_eligible=True,
                cunning_strike_id=cunning_strike_id,
            ),
        )
        attack_events.extend(build_attack_reaction_pre_events(state, attack_event))
        attack_events.extend(build_attack_reaction_phase_events(state, attack_event))
        attack_events.append(attack_event)
        attack_events.extend(maybe_resolve_riposte_follow_up(state, attack_event))
        attack_events.extend(maybe_resolve_sentinel_guardian_follow_up(state, attack_event))
        cleave_events: list[CombatEvent] = []
        resolved_target_id = attack_event.target_ids[0] if attack_event.target_ids else target_id

        if savage_consumed:
            savage_attacker_available = False
            actor._savage_attacker_used_this_turn = True

        if attack_event.resolved_totals.get("hit"):
            cleave_events, cleave_savage_consumed, cleave_target_id = maybe_resolve_cleave_follow_up(
                state,
                actor_id,
                target_id,
                weapon_id,
                savage_attacker_available,
            )
            if cleave_target_id and attack_event.damage_details:
                attack_event.damage_details.mastery_applied = "cleave"
                attack_event.damage_details.mastery_notes = f"{actor_id} cleaves into {cleave_target_id}."
                attack_event.condition_deltas.append(f"{actor_id} cleaves into {cleave_target_id}.")
            attack_events.extend(cleave_events)
            if cleave_savage_consumed:
                savage_attacker_available = False
                actor._savage_attacker_used_this_turn = True

            attack_events.extend(maybe_resolve_rampage_follow_up(state, actor_id, attack_event))

        if state.units[resolved_target_id].conditions.dead:
            attack_events.extend(release_grappled_targets_from_source(state, resolved_target_id, "source_dead"))
            attack_events.extend(release_swallowed_units_from_source(state, resolved_target_id))

        for follow_up_event in cleave_events:
            for follow_up_target_id in follow_up_event.target_ids:
                if state.units[follow_up_target_id].conditions.dead:
                    attack_events.extend(release_grappled_targets_from_source(state, follow_up_target_id, "source_dead"))
                    attack_events.extend(release_swallowed_units_from_source(state, follow_up_target_id))

    return attack_events


def resolve_cast_spell_action(
    state: EncounterState,
    actor_id: str,
    action: dict[str, str],
    *,
    overrides: AttackRollOverrides | None = None,
) -> list[CombatEvent]:
    spell = get_spell_definition(action["spell_id"])
    if spell.targeting_mode == "self_cone_save":
        spell_events = resolve_burning_hands(state, actor_id, action["target_id"], overrides)
        follow_up_events: list[CombatEvent] = []
        for event in spell_events:
            if event.event_type != "attack":
                continue
            for target_id in event.target_ids:
                if state.units[target_id].conditions.dead:
                    follow_up_events.extend(release_grappled_targets_from_source(state, target_id, "source_dead"))
                    follow_up_events.extend(release_swallowed_units_from_source(state, target_id))
        return spell_events + follow_up_events

    if spell.targeting_mode == "multi_ally_buff":
        target_ids = action.get("target_ids")
        if not isinstance(target_ids, list):
            target_ids = [action["target_id"]]
        return [
            resolve_bless(
                state,
                actor_id,
                [str(target_id) for target_id in target_ids],
                spell_level=int(action["spell_level"]) if "spell_level" in action else None,
            )
        ]

    if spell.targeting_mode == "multi_ally_hp_buff":
        target_ids = action.get("target_ids")
        if not isinstance(target_ids, list):
            target_ids = [action["target_id"]]
        return [resolve_aid(state, actor_id, [str(target_id) for target_id in target_ids])]

    if spell.targeting_mode == "single_target_save":
        return resolve_single_target_save_spell(
            state,
            actor_id,
            action["target_id"],
            action["spell_id"],
            overrides,
        )

    if spell.targeting_mode == "multi_target_save":
        target_ids = action.get("target_ids")
        if not isinstance(target_ids, list):
            target_ids = [action["target_id"]]
        return resolve_multi_target_save_spell(
            state,
            actor_id,
            [str(target_id) for target_id in target_ids],
            action["spell_id"],
            overrides,
        )

    if spell.on_hit_effect_kind == "poisoned_save":
        spell_event = resolve_cast_spell(
            state,
            actor_id,
            action["spell_id"],
            action["target_id"],
            overrides,
        )
        spell_events = build_attack_reaction_pre_events(state, spell_event) if spell_event.event_type == "attack" else []
        if spell_event.event_type == "attack":
            spell_events.extend(build_attack_reaction_phase_events(state, spell_event))
        spell_events.append(spell_event)
        if spell_event.event_type != "attack" or not bool(spell_event.resolved_totals.get("hit")):
            return spell_events
        poison_save_event = resolve_ray_of_sickness_poison_save(state, actor_id, spell_event, overrides)
        if poison_save_event:
            spell_events.append(poison_save_event)
        spell_events.extend(maybe_resolve_sentinel_guardian_follow_up(state, spell_event))
        return spell_events

    spell_event = resolve_cast_spell(
        state,
        actor_id,
        action["spell_id"],
        action["target_id"],
        overrides,
    )
    spell_events = build_attack_reaction_pre_events(state, spell_event) if spell_event.event_type == "attack" else []
    if spell_event.event_type == "attack":
        spell_events.extend(build_attack_reaction_phase_events(state, spell_event))
    spell_events.append(spell_event)
    if spell_event.event_type == "attack":
        spell_events.extend(maybe_resolve_sentinel_guardian_follow_up(state, spell_event))

    for target_id in spell_event.target_ids:
        if state.units[target_id].conditions.dead:
            spell_events.extend(release_grappled_targets_from_source(state, target_id, "source_dead"))
            spell_events.extend(release_swallowed_units_from_source(state, target_id))

    return spell_events


def create_movement_event(
    state: EncounterState,
    actor_id: str,
    path: list[GridPosition],
    mode: str,
    disengage_applied: bool,
    triggered_attackers: list[str],
    phase: str,
    *,
    condition_deltas: list[str] | None = None,
) -> CombatEvent | None:
    if len(path) <= 1:
        return None

    start = path[0]
    end = path[-1]
    distance = chebyshev_distance(start, end) if mode == "landing" else len(path) - 1
    tactical_shift_applied = mode == "tactical_shift"
    cunning_withdraw_applied = mode == "cunning_withdraw"
    landing_applied = mode == "landing"
    movement_verb = (
        "lands"
        if landing_applied
        else "withdraws"
        if cunning_withdraw_applied
        else "tactically shifts"
        if tactical_shift_applied
        else "dashes"
        if mode == "dash"
        else "moves"
    )
    protection_note = (
        " using Cunning Strike"
        if cunning_withdraw_applied
        else " using Tactical Shift"
        if tactical_shift_applied
        else " using Disengage"
        if disengage_applied
        else ""
    )
    if landing_applied:
        protection_note = " from flight"
    distance_text = "" if landing_applied else f"{distance} square{'s' if distance != 1 else ''} "
    return CombatEvent(
        round=state.round,
        actor_id=actor_id,
        target_ids=[],
        event_type="move",
        raw_rolls={},
        resolved_totals={
            "movementMode": mode,
            "movementPhase": phase,
            "disengageApplied": disengage_applied,
            "tacticalShiftApplied": tactical_shift_applied,
            "cunningWithdrawApplied": cunning_withdraw_applied,
            "landingApplied": landing_applied,
            "opportunityAttackers": triggered_attackers,
        },
        movement_details=MovementDetails(start=start, end=end, path=path, distance=distance),
        damage_details=None,
        condition_deltas=condition_deltas or [],
        text_summary=(
            f"{actor_id} {movement_verb} "
            f"{distance_text}"
            f"from {format_position(start)} to {format_position(end)}{protection_note} "
            f"{'before acting' if phase == 'before_action' else 'between actions' if phase == 'between_actions' else 'after acting'}."
        ),
    )


def execute_movement(
    state: EncounterState,
    actor_id: str,
    movement: MovementPlan | None,
    disengage_applied: bool,
    phase: str,
) -> tuple[list[CombatEvent], bool]:
    if not movement:
        return [], False

    actor = state.units[actor_id]
    if not actor.position or len(movement.path) <= 1:
        return [], False

    path_travelled = [movement.path[0]]
    reaction_events: list[CombatEvent] = []
    triggered_attackers: list[str] = []
    opportunity_attacks_prevented = movement.mode in {"tactical_shift", "landing", "cunning_withdraw"}

    for index in range(1, len(movement.path)):
        previous = movement.path[index - 1]
        next_position = movement.path[index]
        actor.position = next_position.model_copy(deep=True)
        path_travelled.append(next_position.model_copy(deep=True))

        if opportunity_attacks_prevented:
            continue

        opportunity_attackers = sorted(
            [
                unit
                for unit in state.units.values()
                if unit.faction != actor.faction
                and unit_can_take_reactions(unit)
                and (not disengage_applied or unit_has_feature(unit, "sentinel"))
                and unit.position
                and get_min_chebyshev_distance_between_footprints(
                    unit.position,
                    get_unit_footprint(unit),
                    previous,
                    get_unit_footprint(actor),
                )
                <= get_melee_reach_squares(unit.attacks[get_opportunity_attack_weapon_id(unit)])
                and get_min_chebyshev_distance_between_footprints(
                    unit.position,
                    get_unit_footprint(unit),
                    next_position,
                    get_unit_footprint(actor),
                )
                > get_melee_reach_squares(unit.attacks[get_opportunity_attack_weapon_id(unit)])
            ],
            key=lambda unit: unit_sort_key(unit.id),
        )

        for reaction_unit in opportunity_attackers:
            reaction_unit.reaction_available = False
            triggered_attackers.append(reaction_unit.id)

            # Opportunity attacks resolve as the mover leaves reach, before the
            # destination square is fully established for attack legality.
            post_step_position = actor.position.model_copy(deep=True) if actor.position else None
            actor.position = previous.model_copy(deep=True)
            attack_event, savage_consumed = resolve_attack(
                state,
                ResolveAttackArgs(
                    attacker_id=reaction_unit.id,
                    target_id=actor_id,
                    weapon_id=get_opportunity_attack_weapon_id(reaction_unit),
                    savage_attacker_available=unit_has_feature(reaction_unit, "savage_attacker"),
                    is_opportunity_attack=True,
                    maneuver_id="precision_attack" if reaction_unit.faction == "fighters" else None,
                ),
            )
            if post_step_position is not None:
                actor.position = post_step_position
            reaction_events.extend(build_attack_reaction_pre_events(state, attack_event))
            reaction_events.extend(build_attack_reaction_phase_events(state, attack_event))
            reaction_events.append(attack_event)
            reaction_events.extend(maybe_resolve_riposte_follow_up(state, attack_event))
            reaction_events.extend(maybe_resolve_sentinel_guardian_follow_up(state, attack_event))
            resolved_target_id = attack_event.target_ids[0] if attack_event.target_ids else actor_id

            if attack_event.resolved_totals.get("hit"):
                cleave_events, _, cleave_target_id = maybe_resolve_cleave_follow_up(
                    state,
                    reaction_unit.id,
                    actor_id,
                    get_opportunity_attack_weapon_id(reaction_unit),
                    unit_has_feature(reaction_unit, "savage_attacker") and not savage_consumed,
                )
                if cleave_target_id and attack_event.damage_details:
                    attack_event.damage_details.mastery_applied = "cleave"
                    attack_event.damage_details.mastery_notes = f"{reaction_unit.id} cleaves into {cleave_target_id}."
                    attack_event.condition_deltas.append(f"{reaction_unit.id} cleaves into {cleave_target_id}.")
                reaction_events.extend(cleave_events)
                for cleave_event in cleave_events:
                    for cleave_target_id in cleave_event.target_ids:
                        if state.units[cleave_target_id].conditions.dead:
                            reaction_events.extend(release_grappled_targets_from_source(state, cleave_target_id, "source_dead"))
                            reaction_events.extend(release_swallowed_units_from_source(state, cleave_target_id))

            if state.units[resolved_target_id].conditions.dead:
                reaction_events.extend(release_grappled_targets_from_source(state, resolved_target_id, "source_dead"))
                reaction_events.extend(release_swallowed_units_from_source(state, resolved_target_id))

            if actor.conditions.dead or actor.current_hp == 0 or (
                resolved_target_id == actor_id and attack_event.resolved_totals.get("sentinelHaltApplied") is True
            ):
                movement_condition_deltas = clear_invalid_hidden_effects(state)
                move_event = create_movement_event(
                    state,
                    actor_id,
                    path_travelled,
                    movement.mode,
                    disengage_applied,
                    triggered_attackers,
                    phase,
                    condition_deltas=movement_condition_deltas,
                )
                return ([move_event] if move_event else []) + reaction_events, True

    movement_condition_deltas = clear_invalid_hidden_effects(state)
    move_event = create_movement_event(
        state,
        actor_id,
        path_travelled,
        movement.mode,
        disengage_applied,
        triggered_attackers,
        phase,
        condition_deltas=movement_condition_deltas,
    )
    return ([move_event] if move_event else []) + reaction_events, False


def can_act_after_movement(actor: UnitState) -> bool:
    return not actor.conditions.dead and actor.current_hp > 0


def resolve_bonus_action(
    state: EncounterState,
    actor_id: str,
    bonus_action: dict[str, str] | None,
) -> CombatEvent | None:
    if not bonus_action:
        return None
    actor = state.units[actor_id]
    if bonus_action["kind"] == "second_wind":
        return attempt_second_wind(state, actor_id)
    if bonus_action["kind"] == "lay_on_hands":
        return attempt_lay_on_hands(state, actor_id, bonus_action.get("target_id"))
    if bonus_action["kind"] == "rage":
        if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
            return create_skip_event(state, actor_id, "Cannot rage while down.")

        active_rage = get_active_rage_effect(actor)
        if active_rage:
            actor._rage_extended_this_turn = True
            return add_unit_phase_event(
                state,
                actor_id,
                actor_id,
                f"{actor_id} spends a bonus action to keep the rage burning.",
                condition_deltas=[f"{actor_id} extends the current rage."],
                resolved_totals={
                    "rageActive": True,
                    "rageUsesRemaining": actor.resources.rage_uses,
                    "temporaryHitPoints": actor.temporary_hit_points,
                },
            )

        if actor.resources.rage_uses <= 0:
            return create_skip_event(state, actor_id, "No rage uses remain.")

        actor.resources.rage_uses -= 1
        actor.temporary_hit_points = max(actor.temporary_hit_points, actor.level or 0)
        actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "rage"]
        actor.temporary_effects.append(
            RageEffect(
                kind="rage",
                source_id=actor_id,
                damage_bonus=get_progression_scalar(actor.class_id or "", actor.level or 0, "rage_damage_bonus", 0),
                remaining_rounds=100,
            )
        )
        return add_unit_phase_event(
            state,
            actor_id,
            actor_id,
            f"{actor_id} enters a rage.",
            condition_deltas=[
                f"{actor_id} enters a rage.",
                f"{actor_id} gains {(actor.level or 0)} temporary HP.",
            ],
            resolved_totals={
                "rageActive": True,
                "rageUsesRemaining": actor.resources.rage_uses,
                "temporaryHitPoints": actor.temporary_hit_points,
            },
        )
    if bonus_action["kind"] == "hide":
        return attempt_hide(state, actor_id)
    if bonus_action["kind"] == "steady_aim":
        return attempt_steady_aim(state, actor_id)
    if bonus_action["kind"] == "patient_defense":
        return attempt_patient_defense(state, actor_id)
    if bonus_action["kind"] == "step_of_the_wind":
        return attempt_step_of_the_wind(state, actor_id)
    if bonus_action["kind"] in {"bonus_dash", "disengage", "aggressive_dash"}:
        return None
    return None


def get_bonus_attack_target_id(
    state: EncounterState,
    actor_id: str,
    weapon_id: str,
    preferred_target_id: str | None,
    *,
    retarget: bool,
) -> str | None:
    actor = state.units[actor_id]
    weapon = actor.attacks.get(weapon_id)
    if not weapon:
        return None

    if not retarget:
        if not preferred_target_id:
            return None
        target = state.units.get(preferred_target_id)
        if not target or target.conditions.dead or target.current_hp <= 0 or target.conditions.unconscious:
            return None
        return preferred_target_id if get_attack_context(state, actor_id, preferred_target_id, weapon).legal else None

    for target in get_ranked_attack_targets(state, actor, preferred_target_id):
        if target.conditions.dead or target.current_hp <= 0 or target.conditions.unconscious:
            continue
        if get_attack_context(state, actor_id, target.id, weapon).legal:
            return target.id

    return None


def build_focus_bonus_action_event(
    state: EncounterState,
    actor_id: str,
    action_name: str,
    focus_points_remaining: int,
) -> CombatEvent:
    return add_unit_phase_event(
        state,
        actor_id,
        actor_id,
        f"{actor_id} spends 1 Focus Point on {action_name}.",
        condition_deltas=[f"{actor_id} spends 1 Focus Point on {action_name}."],
        resolved_totals={"focusPointsRemaining": focus_points_remaining},
    )


def resolve_bonus_attack_action(
    state: EncounterState,
    actor_id: str,
    bonus_action: dict[str, str] | None,
    *,
    step_overrides: list[AttackRollOverrides] | None = None,
) -> list[CombatEvent]:
    if not bonus_action or bonus_action["kind"] not in {"bonus_unarmed_strike", "flurry_of_blows"}:
        return []

    actor = state.units[actor_id]
    preferred_target_id = bonus_action.get("target_id")
    weapon_id = "unarmed_strike"
    weapon = actor.attacks.get(weapon_id)
    if not weapon:
        return [create_skip_event(state, actor_id, "Unarmed Strike is unavailable.")]

    if bonus_action["kind"] == "bonus_unarmed_strike":
        target_id = get_bonus_attack_target_id(
            state,
            actor_id,
            weapon_id,
            preferred_target_id,
            retarget=True,
        )
        if not target_id:
            return [create_skip_event(state, actor_id, "No bonus-action unarmed target is available.")]

        attack_event, _ = resolve_attack(
            state,
            ResolveAttackArgs(
                attacker_id=actor_id,
                target_id=target_id,
                weapon_id=weapon_id,
                savage_attacker_available=False,
                overrides=step_overrides[0] if step_overrides else None,
            ),
        )
        attack_events = [attack_event]
        if state.units[target_id].conditions.dead:
            attack_events.extend(release_grappled_targets_from_source(state, target_id, "source_dead"))
            attack_events.extend(release_swallowed_units_from_source(state, target_id))
        return attack_events

    target_id = get_bonus_attack_target_id(
        state,
        actor_id,
        weapon_id,
        preferred_target_id,
        retarget=False,
    )
    if not target_id:
        return [create_skip_event(state, actor_id, "No Flurry of Blows target is available.")]
    if not actor.resources.spend_pool("focus_points", 1):
        return [create_skip_event(state, actor_id, "No Focus Points remain.")]

    attack_events = [build_focus_bonus_action_event(state, actor_id, "Flurry of Blows", actor.resources.focus_points)]
    for step_index in range(2):
        current_target_id = get_bonus_attack_target_id(
            state,
            actor_id,
            weapon_id,
            target_id,
            retarget=False,
        )
        if not current_target_id:
            break

        attack_event, _ = resolve_attack(
            state,
            ResolveAttackArgs(
                attacker_id=actor_id,
                target_id=current_target_id,
                weapon_id=weapon_id,
                savage_attacker_available=False,
                overrides=step_overrides[step_index] if step_overrides and step_index < len(step_overrides) else None,
            ),
        )
        attack_events.append(attack_event)
        if state.units[current_target_id].conditions.dead:
            attack_events.extend(release_grappled_targets_from_source(state, current_target_id, "source_dead"))
            attack_events.extend(release_swallowed_units_from_source(state, current_target_id))
            break

    return attack_events


def resolve_bonus_action_events(
    state: EncounterState,
    actor_id: str,
    bonus_action: dict[str, str] | None,
) -> list[CombatEvent]:
    if not bonus_action:
        return []

    actor = state.units[actor_id]
    if actor._bonus_action_used_this_turn:
        return [create_skip_event(state, actor_id, "Bonus action has already been used this turn.")]

    actor._bonus_action_used_this_turn = True

    if bonus_action["kind"] in {"bonus_unarmed_strike", "flurry_of_blows"}:
        return resolve_bonus_attack_action(state, actor_id, bonus_action)
    if bonus_action["kind"] == "cast_spell":
        spell = get_spell_definition(bonus_action["spell_id"])
        if spell.timing != "bonus_action":
            return [create_skip_event(state, actor_id, f"{spell.display_name} is not a bonus action spell.")]
        return resolve_cast_spell_action(state, actor_id, bonus_action)

    bonus_event = resolve_bonus_action(state, actor_id, bonus_action)
    return [bonus_event] if bonus_event else []


def resolve_action_surge(state: EncounterState, actor_id: str) -> CombatEvent:
    actor = state.units[actor_id]

    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return create_skip_event(state, actor_id, "Cannot use Action Surge while down.")

    if not unit_has_feature(actor, "action_surge"):
        return create_skip_event(state, actor_id, "Action Surge is not available.")

    if actor.resources.action_surge_uses <= 0:
        return create_skip_event(state, actor_id, "No Action Surge uses remain.")

    actor.resources.action_surge_uses -= 1
    return add_unit_phase_event(
        state,
        actor_id,
        actor_id,
        f"{actor_id} uses Action Surge for an extra action.",
        condition_deltas=[f"{actor_id} spends Action Surge."],
        resolved_totals={"actionSurgeUsesRemaining": actor.resources.action_surge_uses},
    )


def exceeds_movement_budget(state: EncounterState, actor: UnitState, decision: TurnDecision) -> bool:
    movement_legs = [decision.pre_action_movement, decision.between_action_movement, decision.post_action_movement]
    tactical_shift_distance = sum(movement_distance(movement) for movement in movement_legs if is_tactical_shift_movement(movement))
    tactical_shift_legs = sum(1 for movement in movement_legs if is_tactical_shift_movement(movement) and movement_distance(movement) > 0)
    cunning_withdraw_distance = sum(
        movement_distance(movement) for movement in movement_legs if is_cunning_withdraw_movement(movement)
    )
    cunning_withdraw_legs = sum(
        1 for movement in movement_legs if is_cunning_withdraw_movement(movement) and movement_distance(movement) > 0
    )
    normal_distance = sum(
        movement_distance(movement)
        for movement in movement_legs
        if not is_tactical_shift_movement(movement)
        and not is_landing_movement(movement)
        and not is_cunning_withdraw_movement(movement)
    )

    if tactical_shift_distance > 0:
        if tactical_shift_legs > 1 or not can_apply_tactical_shift(actor, decision):
            return True
        if tactical_shift_distance > get_tactical_shift_budget(actor, state):
            return True

    if cunning_withdraw_distance > 0:
        if cunning_withdraw_legs > 1 or not can_apply_cunning_withdraw(actor, decision):
            return True
        if cunning_withdraw_distance > get_cunning_withdraw_budget(actor, state):
            return True

    return normal_distance > get_total_movement_budget(
        actor,
        decision.action,
        decision.bonus_action,
        decision.surged_action,
        state=state,
    )


def resolve_turn_action(
    state: EncounterState,
    actor_id: str,
    action: dict[str, str],
    events: list[CombatEvent],
    *,
    rescue_mode: bool,
) -> None:
    if action["kind"] == "attack" and not rescue_mode:
        events.extend(resolve_attack_action(state, actor_id, action))
    elif action["kind"] == "cast_spell" and not rescue_mode:
        events.extend(resolve_cast_spell_action(state, actor_id, action))
    elif action["kind"] == "special_action" and not rescue_mode:
        events.extend(resolve_special_action_events(state, actor_id, action))
    elif action["kind"] == "stabilize":
        events.append(attempt_stabilize(state, actor_id, action["target_id"]))
    elif action["kind"] == "skip":
        events.append(create_skip_event(state, actor_id, action["reason"]))


def action_sequence_triggered_cunning_withdraw(events: list[CombatEvent], actor_id: str) -> bool:
    return any(
        event.actor_id == actor_id
        and event.event_type == "attack"
        and event.resolved_totals.get("cunningStrikeId") == "withdraw"
        and event.resolved_totals.get("cunningStrikeApplied") is True
        for event in events
    )


def step_encounter_internal(
    state: EncounterState,
    *,
    copy_state: bool,
    record_log: bool,
) -> StepEncounterResult:
    if state.terminal_state == "complete":
        terminal_state = clone_value(state) if copy_state else state
        return StepEncounterResult(state=terminal_state, events=[], done=True)

    next_state = clone_value(state) if copy_state else state
    actor_id = next_state.initiative_order[next_state.active_combatant_index]

    # Encounters now end as soon as one side is fully down or dead, so skip
    # any additional turn processing if the incoming state is already terminal.
    if fighters_defeated(next_state) or goblins_defeated(next_state):
        events = update_encounter_phase(next_state, actor_id)
        if record_log:
            next_state.combat_log.extend(events)
        completed_state = clone_value(next_state) if copy_state else next_state
        return StepEncounterResult(state=completed_state, events=events, done=True)

    actor = next_state.units[actor_id]
    clear_turn_flags(actor)
    events = [
        CombatEvent(
            round=next_state.round,
            actor_id=actor_id,
            target_ids=[actor_id],
            event_type="turn_start",
            raw_rolls={},
            resolved_totals={"rescueSubphase": next_state.rescue_subphase},
            movement_details=None,
            damage_details=None,
            condition_deltas=[],
            text_summary=f"{actor_id} starts turn {next_state.round}.",
        )
    ]

    events.extend(expire_turn_effects(next_state, actor_id))
    next_state.units[actor_id].reaction_available = True
    events.extend(resolve_turn_start_posture(next_state, actor_id))
    events.extend(release_invalid_grappled_targets_at_turn_start(next_state, actor_id))
    events.extend(apply_start_of_turn_ongoing_effects(next_state, actor_id))

    if fighters_defeated(next_state) or goblins_defeated(next_state):
        events.extend(update_encounter_phase(next_state, actor_id))
        if record_log:
            next_state.combat_log.extend(events)
        completed_state = clone_value(next_state) if copy_state else next_state
        return StepEncounterResult(state=completed_state, events=events, done=True)

    # The branch order mirrors the TypeScript engine exactly so death saves and
    # normal combat turns stay bit-identical to the oracle implementation.
    if actor.conditions.dead:
        events.append(create_skip_event(next_state, actor_id, "Dead units do not act."))
    elif actor.current_hp == 0:
        if actor.stable:
            events.append(create_skip_event(next_state, actor_id, "Stable fighters do not act while unconscious."))
        else:
            events.append(resolve_death_save(next_state, actor_id))
    else:
        execute_decision(next_state, actor_id, choose_turn_decision(next_state, actor_id), events, rescue_mode=False)

    events.extend(resolve_turn_end_rage(next_state, actor_id))
    poisoned_save_event = resolve_poisoned_end_of_turn_save(next_state, actor_id)
    if poisoned_save_event:
        events.append(poisoned_save_event)
    restrained_save_event = resolve_restrained_end_of_turn_save(next_state, actor_id)
    if restrained_save_event:
        events.append(restrained_save_event)
    events.extend(expire_turn_end_effects(next_state, actor_id))
    events.extend(update_encounter_phase(next_state, actor_id))
    if record_log:
        next_state.combat_log.extend(events)

    done = next_state.terminal_state == "complete"
    if not done:
        advance_initiative(next_state)

    return StepEncounterResult(state=next_state, events=events, done=done)


def step_encounter(state: EncounterState) -> StepEncounterResult:
    return step_encounter_internal(state, copy_state=True, record_log=True)


def step_encounter_without_history(state: EncounterState) -> StepEncounterResult:
    return step_encounter_internal(state, copy_state=False, record_log=False)


def execute_decision(
    state: EncounterState,
    actor_id: str,
    decision: TurnDecision,
    events: list[CombatEvent],
    *,
    rescue_mode: bool,
) -> None:
    if exceeds_movement_budget(state, state.units[actor_id], decision):
        events.append(create_skip_event(state, actor_id, "Planned movement exceeds the unit speed budget."))
        return
    if decision.bonus_action and decision.bonus_action["kind"] == "steady_aim" and decision_movement_distance(decision) > 0:
        events.append(create_skip_event(state, actor_id, "Steady Aim cannot be used on a turn with planned movement."))
        return

    if decision.bonus_action and decision.bonus_action["timing"] == "before_action":
        events.extend(resolve_bonus_action_events(state, actor_id, decision.bonus_action))

    # Movement can be split around the action. Opportunity attacks are resolved
    # during each leg and can stop the rest of the plan immediately.
    pre_events, _ = execute_movement(
        state,
        actor_id,
        decision.pre_action_movement,
        bonus_action_applies_disengage(decision.bonus_action) and decision.bonus_action["timing"] == "before_action",
        "before_action",
    )
    events.extend(pre_events)

    action_sequence_start_index = len(events)
    if can_act_after_movement(state.units[actor_id]):
        resolve_turn_action(state, actor_id, decision.action, events, rescue_mode=rescue_mode)

    if can_act_after_movement(state.units[actor_id]) and decision.surged_action:
        action_surge_event = resolve_action_surge(state, actor_id)
        if action_surge_event:
            events.append(action_surge_event)

        if action_surge_event.event_type != "skip" and can_act_after_movement(state.units[actor_id]):
            between_events, _ = execute_movement(
                state,
                actor_id,
                decision.between_action_movement,
                bonus_action_applies_disengage(decision.bonus_action),
                "between_actions",
            )
            events.extend(between_events)

        if action_surge_event.event_type != "skip" and can_act_after_movement(state.units[actor_id]):
            resolve_turn_action(state, actor_id, decision.surged_action, events, rescue_mode=rescue_mode)

    if can_act_after_movement(state.units[actor_id]):
        events.extend(
            maybe_resolve_great_weapon_master_hewing(
                state,
                actor_id,
                events[action_sequence_start_index:],
                planned_bonus_action=decision.bonus_action,
            )
        )

    if can_act_after_movement(state.units[actor_id]) and decision.bonus_action and decision.bonus_action["timing"] == "after_action":
        events.extend(resolve_bonus_action_events(state, actor_id, decision.bonus_action))

    if can_act_after_movement(state.units[actor_id]):
        post_action_movement = decision.post_action_movement
        if is_cunning_withdraw_movement(post_action_movement) and not action_sequence_triggered_cunning_withdraw(
            events[action_sequence_start_index:],
            actor_id,
        ):
            post_action_movement = None
        post_events, _ = execute_movement(
            state,
            actor_id,
            post_action_movement,
            bonus_action_applies_disengage(decision.bonus_action),
            "after_action",
        )
        events.extend(post_events)


def run_encounter(config: EncounterConfig) -> RunEncounterResult:
    working_state = create_encounter(config)
    replay_frames = [
        ReplayFrame(
            index=0,
            round=working_state.round,
            active_combatant_id=working_state.initiative_order[working_state.active_combatant_index],
            state=clone_value(working_state),
            events=[],
        )
    ]

    guard = 0
    while working_state.terminal_state != "complete":
        actor_id = working_state.initiative_order[working_state.active_combatant_index]
        result = step_encounter(working_state)
        working_state = result.state
        replay_frames.append(
            ReplayFrame(
                index=len(replay_frames),
                round=working_state.round,
                active_combatant_id=actor_id,
                state=clone_value(working_state),
                events=clone_value(result.events),
            )
        )
        guard += 1
        if guard > 1000:
            raise RuntimeError("Encounter loop guard tripped.")

    return RunEncounterResult(final_state=working_state, events=clone_value(working_state.combat_log), replay_frames=replay_frames)


def run_encounter_summary_fast(config: EncounterConfig) -> EncounterSummary:
    """Run an encounter without replay/history capture and return only the final summary.

    Large browser-driven batches do not need combat logs or replay frames for every sample.
    This path keeps the combat rules identical while avoiding the most expensive history work.
    """

    working_state = create_encounter(config)
    guard = 0

    while working_state.terminal_state != "complete":
        result = step_encounter_without_history(working_state)
        working_state = result.state
        guard += 1
        if guard > 1000:
            raise RuntimeError("Encounter loop guard tripped.")

    return summarize_encounter(working_state)


def summarize_encounter(state: EncounterState) -> EncounterSummary:
    fighters = get_units_by_faction(state, "fighters")
    goblins = get_units_by_faction(state, "goblins")
    return EncounterSummary(
        seed=state.seed,
        player_behavior=state.player_behavior,
        monster_behavior=state.monster_behavior,
        winner=state.winner,
        rounds=state.round,
        fighter_deaths=len([unit for unit in fighters if unit.conditions.dead]),
        goblins_killed=len([unit for unit in goblins if unit.conditions.dead]),
        remaining_fighter_hp=get_remaining_hp(fighters),
        remaining_goblin_hp=get_remaining_hp(goblins),
        stable_unconscious_fighters=len([unit for unit in fighters if is_unit_stable_at_zero(unit)]),
        conscious_fighters=len([unit for unit in fighters if is_unit_conscious(unit)]),
    )


def run_single_batch_accumulator(
    config: EncounterConfig,
    requested_player_behavior: str,
    requested_monster_behavior: str,
    capture_history: bool | None = None,
    progress_callback=None,
):
    """Compatibility wrapper for callers still importing batch helpers from this module."""

    from backend.engine.combat.batch import run_single_batch_accumulator as run_single_batch_accumulator_impl

    return run_single_batch_accumulator_impl(
        config,
        requested_player_behavior,
        requested_monster_behavior,
        capture_history,
        progress_callback,
    )


def run_batch_serial(
    config: EncounterConfig,
    requested_size: int,
    requested_player_behavior: str,
    requested_monster_behavior: str,
    seed: str,
    progress_callback=None,
):
    """Compatibility wrapper for the extracted serial batch executor."""

    from backend.engine.combat.batch import run_batch_serial as run_batch_serial_impl

    return run_batch_serial_impl(
        config,
        requested_size,
        requested_player_behavior,
        requested_monster_behavior,
        seed,
        progress_callback,
    )


def run_batch_parallel(
    config: EncounterConfig,
    requested_size: int,
    requested_player_behavior: str,
    requested_monster_behavior: str,
    seed: str,
    progress_callback=None,
    worker_count=None,
):
    """Compatibility wrapper for the extracted parallel batch executor."""

    from backend.engine.combat.batch import run_batch_parallel as run_batch_parallel_impl

    return run_batch_parallel_impl(
        config,
        requested_size,
        requested_player_behavior,
        requested_monster_behavior,
        seed,
        progress_callback,
        worker_count=worker_count,
    )


def run_batch(
    config: EncounterConfig,
    progress_callback=None,
    *,
    force_serial: bool = False,
    worker_count: int | None = None,
):
    """Compatibility wrapper for the extracted batch module."""

    from backend.engine.combat.batch import run_batch as run_batch_impl

    return run_batch_impl(config, progress_callback, force_serial=force_serial, worker_count=worker_count)
