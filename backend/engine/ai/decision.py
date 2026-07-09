from __future__ import annotations

from dataclasses import dataclass

from backend.content.enemies import (
    get_attack_action_definition_for_unit,
    get_monster_definition_for_unit,
    unit_has_bonus_action,
    unit_has_reaction,
)
from backend.content.feature_definitions import unit_has_feature, unit_has_granted_bonus_action
from backend.content.player_loadouts import get_player_primary_melee_weapon_id, get_player_primary_ranged_weapon_id
from backend.content.spell_definitions import get_spell_definition
from backend.engine.ai.profiles import get_monster_ai_profile
from backend.engine.models.state import (
    AttackId,
    AttackMode,
    EncounterState,
    GridPosition,
    NoReactionsEffect,
    ResolvedPlayerBehavior,
    RoleTag,
    UnitState,
    WeaponProfile,
    WeaponRange,
)
from backend.engine.rules.combat_rules import (
    build_spell_attack_profile,
    can_apply_sneak_attack,
    can_use_battle_master_maneuver,
    choose_burning_hands_targeting,
    get_damage_defense_flags,
    get_rage_damage_bonus,
    get_shield_ac_bonus,
    get_sneak_attack_d6_count,
    has_harried_effect,
    has_vex_effect,
    target_is_grappled_by_attacker,
    unit_has_reckless_attack_effect,
    unit_is_bloodied,
    unit_is_dodging,
)
from backend.engine.rules.spatial import (
    PositionIndex,
    ReachableSquare,
    build_position_index,
    can_attempt_hide_from_position,
    chebyshev_distance,
    get_active_grappled_target_ids,
    get_active_grappler_ids,
    get_attack_context,
    get_min_chebyshev_distance_between_footprints,
    get_min_distance_to_faction,
    get_reachable_squares,
    get_swallow_source_id,
    get_unit_footprint,
    get_units_with_positions,
    path_provokes_opportunity_attack,
)
from backend.engine.utils.helpers import get_units_by_faction, is_unit_conscious, unit_can_take_reactions


SMART_PRECISION_ATTACK_DEFAULT_MAX_MISS_MARGIN = 2
SMART_PRECISION_ATTACK_PRESSURE_MAX_MISS_MARGIN = 4
SMART_PRECISION_ATTACK_FINISHER_MAX_MISS_MARGIN = 4
DUMB_PRECISION_ATTACK_MAX_MISS_MARGIN = 8


@dataclass
class MovementPlan:
    path: list[GridPosition]
    mode: str


@dataclass
class TurnDecision:
    action: dict[str, str]
    bonus_action: dict[str, str] | None = None
    pre_action_movement: MovementPlan | None = None
    between_action_movement: MovementPlan | None = None
    surged_action: dict[str, str] | None = None
    post_action_movement: MovementPlan | None = None


@dataclass
class AttackPlan:
    target_id: str
    weapon_id: AttackId
    path: list[GridPosition]


@dataclass
class MeleeAttackOption:
    target: UnitState
    path: list[GridPosition]
    distance: int
    creates_flank: bool
    adjacent_allies: int


@dataclass(frozen=True)
class AttackProjection:
    hit_probability: float
    average_on_hit_damage: float


def get_monster_profile(unit: UnitState):
    definition = get_monster_definition_for_unit(unit)
    return get_monster_ai_profile(definition.ai_profile_id)


def uses_ranged_monster_ai(unit: UnitState) -> bool:
    return get_monster_profile(unit).combat_style == "ranged"


def can_use_disengage_bonus_action(unit: UnitState) -> bool:
    return unit_has_bonus_action(unit, "disengage")


def can_use_aggressive_bonus_movement(unit: UnitState) -> bool:
    return unit_has_bonus_action(unit, "aggressive_dash")


def unit_is_hidden(unit: UnitState) -> bool:
    return any(effect.kind == "hidden" for effect in unit.temporary_effects)


def can_use_player_bonus_action(unit: UnitState, action_id: str) -> bool:
    return (
        unit.current_hp > 0
        and not unit.conditions.dead
        and not unit.conditions.unconscious
        and unit_has_granted_bonus_action(unit, action_id)
    )


def can_use_player_disengage_bonus_action(unit: UnitState) -> bool:
    return can_use_player_bonus_action(unit, "disengage")


def can_use_player_bonus_dash(unit: UnitState) -> bool:
    return can_use_player_bonus_action(unit, "bonus_dash")


def can_use_player_hide_bonus_action(unit: UnitState) -> bool:
    return can_use_player_bonus_action(unit, "hide")


def can_use_player_bonus_unarmed_strike(unit: UnitState) -> bool:
    return can_use_player_bonus_action(unit, "bonus_unarmed_strike")


def can_use_monk_focus_bonus_action(unit: UnitState, action_id: str) -> bool:
    return can_use_player_bonus_action(unit, action_id) and unit.resources.focus_points > 0


def is_committed_to_melee(unit: UnitState) -> bool:
    return unit._committed_to_melee


def commit_to_melee(unit: UnitState) -> None:
    unit._committed_to_melee = True


def get_hp_ratio(unit: UnitState) -> float:
    if unit.max_hp <= 0:
        return 0.0
    return unit.current_hp / unit.max_hp


def has_role_tag(unit: UnitState, role_tag: RoleTag) -> bool:
    return role_tag in unit.role_tags


def is_unit_downed(unit: UnitState) -> bool:
    return not unit.conditions.dead and unit.current_hp == 0


def is_grappled(unit: UnitState, state: EncounterState | None = None) -> bool:
    if state is None:
        return any(effect.kind == "grappled_by" for effect in unit.temporary_effects)
    return bool(get_active_grappler_ids(state, unit.id))


def get_move_squares(unit: UnitState, state: EncounterState | None = None) -> int:
    if is_grappled(unit, state):
        return 0
    base_move_squares = unit.effective_speed // 5
    return max(0, base_move_squares - unit._turn_stand_up_cost_squares)


def get_total_move_squares(
    unit: UnitState,
    extra_speed_multipliers: int = 0,
    *,
    state: EncounterState | None = None,
) -> int:
    if is_grappled(unit, state):
        return 0
    base_move_squares = unit.effective_speed // 5
    total_budget = base_move_squares * (1 + extra_speed_multipliers)
    return max(0, total_budget - unit._turn_stand_up_cost_squares)


def is_player_ranged_skirmisher(unit: UnitState) -> bool:
    return unit.behavior_profile == "martial_skirmisher"


def is_player_melee_opportunist(unit: UnitState) -> bool:
    return unit.behavior_profile == "martial_opportunist"


def is_player_barbarian(unit: UnitState) -> bool:
    return unit.behavior_profile == "martial_berserker"


def is_player_fighter(unit: UnitState) -> bool:
    return unit.class_id == "fighter" and unit.behavior_profile == "martial_striker"


def is_player_monk(unit: UnitState) -> bool:
    return unit.class_id == "monk" and unit.behavior_profile == "martial_artist"


def is_player_wizard(unit: UnitState) -> bool:
    return unit.class_id == "wizard" and unit.behavior_profile == "arcane_artillery"


def unit_is_raging(unit: UnitState) -> bool:
    return any(effect.kind == "rage" for effect in unit.temporary_effects)


def should_use_second_wind(unit: UnitState) -> bool:
    return (
        can_use_player_bonus_action(unit, "second_wind")
        and unit.current_hp > 0
        and unit.current_hp <= unit.max_hp // 2
        and unit.resources.second_wind_uses > 0
    )


def get_player_bonus_action(unit: UnitState) -> dict[str, str] | None:
    if should_use_second_wind(unit):
        return {"kind": "second_wind", "timing": "before_action"}
    return None


def can_use_player_weapon(unit: UnitState, weapon_id: str | None) -> bool:
    if not weapon_id:
        return False
    weapon = unit.attacks.get(weapon_id)
    if not weapon:
        return False
    if weapon.resource_pool_id:
        return unit.resources.get_pool(weapon.resource_pool_id) > 0
    return True


def can_cast_combat_spell(unit: UnitState, spell_id: str) -> bool:
    if unit.current_hp <= 0 or unit.conditions.dead or unit.conditions.unconscious:
        return False
    if spell_id in unit.combat_cantrip_ids:
        return True
    if spell_id not in unit.prepared_combat_spell_ids:
        return False
    spell = get_spell_definition(spell_id)
    if spell.level <= 0:
        return True
    if spell.level == 1:
        return unit.resources.spell_slots_level_1 > 0
    return False


def can_open_barbarian_rage(actor: UnitState) -> bool:
    return (
        is_player_barbarian(actor)
        and can_use_player_bonus_action(actor, "rage")
        and not unit_is_raging(actor)
        and actor.resources.rage_uses > 0
    )


def can_use_action_surge(actor: UnitState) -> bool:
    return (
        is_player_fighter(actor)
        and unit_has_feature(actor, "action_surge")
        and actor.resources.action_surge_uses > 0
        and actor.current_hp > 0
        and not actor.conditions.dead
        and not actor.conditions.unconscious
    )


def can_use_tactical_shift(actor: UnitState, decision: TurnDecision) -> bool:
    return bool(
        is_player_fighter(actor)
        and unit_has_feature(actor, "tactical_shift")
        and decision.bonus_action
        and decision.bonus_action.get("kind") == "second_wind"
        and actor.resources.second_wind_uses > 0
        and actor.current_hp > 0
        and not actor.conditions.dead
        and not actor.conditions.unconscious
    )


def is_player_battle_master(actor: UnitState) -> bool:
    return is_player_fighter(actor) and unit_has_feature(actor, "combat_superiority")


def target_is_trip_eligible(target: UnitState) -> bool:
    return (
        target.current_hp > 0
        and not target.conditions.dead
        and not target.conditions.unconscious
        and not target.conditions.prone
        and target.size_category in {"tiny", "small", "medium", "large"}
    )


def is_barbarian_under_immediate_melee_threat(
    state: EncounterState,
    actor: UnitState,
    position_index: PositionIndex | None = None,
) -> bool:
    if not actor.position:
        return False

    for enemy in get_units_by_faction(state, "goblins"):
        if not is_unit_conscious(enemy) or not enemy.position:
            continue

        try:
            melee_weapon_id = get_enemy_melee_weapon_id(enemy)
        except ValueError:
            continue

        if build_melee_attack_options(
            state,
            enemy,
            [actor],
            get_move_squares(enemy, state),
            melee_weapon_id,
            False,
            position_index,
        ):
            return True

    return False


def apply_barbarian_opening_rage(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    position_index: PositionIndex | None = None,
) -> TurnDecision:
    if decision.bonus_action or not should_commit_barbarian_rage(
        state,
        actor,
        will_attack_this_turn=decision.action["kind"] == "attack",
        position_index=position_index,
    ):
        return decision

    decision.bonus_action = {"kind": "rage", "timing": "before_action"}
    return decision


def apply_barbarian_rage_upkeep(actor: UnitState, decision: TurnDecision) -> TurnDecision:
    if not is_player_barbarian(actor) or not unit_is_raging(actor) or decision.bonus_action:
        return decision

    if decision.action["kind"] != "attack":
        decision.bonus_action = {"kind": "rage", "timing": "after_action"}

    return decision


def get_tactical_shift_budget_squares(actor: UnitState, state: EncounterState) -> int:
    return max(0, get_move_squares(actor, state) // 2)


def choose_tactical_shift_movement(
    state: EncounterState,
    actor: UnitState,
    position_index: PositionIndex | None = None,
) -> MovementPlan | None:
    if not actor.position:
        return None

    budget = get_tactical_shift_budget_squares(actor, state)
    if budget <= 0:
        return None

    enemy_faction = "goblins" if actor.faction == "fighters" else "fighters"
    actor_footprint = get_unit_footprint(actor)
    current_adjacent_count = len(get_adjacent_conscious_enemies_at_position(state, actor, actor.position))
    current_distance = get_min_distance_to_faction(state, actor.position, enemy_faction, position_index, actor_footprint)
    candidates = [square for square in get_reachable_squares(state, actor.id, budget, position_index) if square.distance > 0]
    improvements: list[tuple[ReachableSquare, int, int]] = []

    for square in candidates:
        adjacent_count = len(get_adjacent_conscious_enemies_at_position(state, actor, square.position))
        distance_to_enemy = get_min_distance_to_faction(state, square.position, enemy_faction, position_index, actor_footprint)
        if adjacent_count < current_adjacent_count or distance_to_enemy > current_distance:
            improvements.append((square, adjacent_count, distance_to_enemy))

    if not improvements:
        return None

    if state.player_behavior == "smart":
        best_square = sorted(
            improvements,
            key=lambda option: (
                option[1],
                -option[2],
                option[0].distance,
                option[0].position.x,
                option[0].position.y,
            ),
        )[0][0]
    else:
        best_square = sorted(improvements, key=lambda option: (option[0].distance, option[0].position.x, option[0].position.y))[0][0]

    return MovementPlan(path=best_square.path, mode="tactical_shift")


def apply_fighter_tactical_shift(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    position_index: PositionIndex | None = None,
) -> TurnDecision:
    if not can_use_tactical_shift(actor, decision):
        return decision
    if decision.pre_action_movement or decision.between_action_movement or decision.post_action_movement:
        return decision

    tactical_shift = choose_tactical_shift_movement(state, actor, position_index)
    if tactical_shift:
        decision.post_action_movement = tactical_shift
    return decision


def get_remaining_move_squares_after_primary_action(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
) -> int:
    return max(0, get_move_squares(actor, state) - get_movement_distance(decision.pre_action_movement))


def choose_action_surge_reposition(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    remaining_move_squares: int,
    melee_weapon_id: str,
    position_index: PositionIndex | None = None,
) -> MovementPlan | None:
    if state.player_behavior != "smart" or remaining_move_squares <= 0:
        return None

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
    if not flanking_options:
        return None

    best_option = sorted(
        flanking_options,
        key=lambda option: (
            option.distance,
            -option.adjacent_allies,
            option.path[-1].x,
            option.path[-1].y,
        ),
    )[0]
    return MovementPlan(path=best_option.path, mode="move")


def apply_fighter_action_surge(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    melee_weapon_id: str,
    position_index: PositionIndex | None = None,
) -> TurnDecision:
    if not can_use_action_surge(actor) or decision.surged_action:
        return decision

    if decision.action["kind"] != "attack" or decision.action.get("weapon_id") != melee_weapon_id:
        return decision

    decision.surged_action = {
        "kind": "attack",
        "target_id": decision.action["target_id"],
        "weapon_id": melee_weapon_id,
    }

    target = state.units.get(decision.action["target_id"])
    if not target:
        return decision

    remaining_move_squares = get_remaining_move_squares_after_primary_action(state, actor, decision)
    between_action_movement = choose_action_surge_reposition(
        state,
        actor,
        target,
        remaining_move_squares,
        melee_weapon_id,
        position_index,
    )
    if between_action_movement:
        decision.between_action_movement = between_action_movement

    return decision


def attack_action_uses_melee_weapon(actor: UnitState, action: dict[str, str] | None) -> bool:
    if not action or action.get("kind") != "attack":
        return False
    weapon = actor.attacks.get(action.get("weapon_id", ""))
    return bool(weapon and weapon.kind == "melee")


def estimate_average_weapon_damage(weapon: WeaponProfile) -> float:
    if weapon.damage_components:
        dice_average = sum(spec.count * (spec.sides + 1) / 2 for component in weapon.damage_components for spec in component.damage_dice)
        modifier = sum(component.damage_modifier for component in weapon.damage_components)
        return dice_average + modifier
    return sum(spec.count * (spec.sides + 1) / 2 for spec in weapon.damage_dice) + weapon.damage_modifier


def get_smart_precision_max_miss_margin(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    dice_available: int,
) -> int:
    estimated_damage = estimate_average_weapon_damage(weapon)
    if target.current_hp <= estimated_damage:
        return SMART_PRECISION_ATTACK_FINISHER_MAX_MISS_MARGIN
    if can_pressure_allies_now(state, target, actor.faction):
        return SMART_PRECISION_ATTACK_PRESSURE_MAX_MISS_MARGIN
    return SMART_PRECISION_ATTACK_DEFAULT_MAX_MISS_MARGIN


def get_player_attack_step_count(actor: UnitState, action: dict[str, str]) -> int:
    if action.get("kind") != "attack":
        return 0
    try:
        return len(
            get_attack_action_definition_for_unit(
                actor,
                preferred_weapon_id=action.get("weapon_id"),
                action_id=action.get("attack_action_id"),
            ).steps
        )
    except ValueError:
        return 1


def set_attack_maneuver_intent(
    action: dict[str, str],
    step_index: int,
    step_count: int,
    maneuver_id: str,
    precision_max_miss_margin: int | None = None,
) -> None:
    if step_count <= 1:
        action["maneuver_id"] = maneuver_id
        if precision_max_miss_margin is not None:
            action["precision_max_miss_margin"] = precision_max_miss_margin
        return

    maneuver_intents = action.get("maneuver_intents")
    if not isinstance(maneuver_intents, list) or len(maneuver_intents) != step_count:
        maneuver_intents = [{} for _ in range(step_count)]
        action["maneuver_intents"] = maneuver_intents

    step_intent = {"maneuver_id": maneuver_id}
    if precision_max_miss_margin is not None:
        step_intent["precision_max_miss_margin"] = precision_max_miss_margin
    maneuver_intents[step_index] = step_intent


def apply_fighter_maneuver_intents(state: EncounterState, actor: UnitState, decision: TurnDecision) -> TurnDecision:
    if not is_player_battle_master(actor) or actor.resources.superiority_dice <= 0:
        return decision

    attack_actions = [action for action in (decision.action, decision.surged_action) if action and action.get("kind") == "attack"]
    if not attack_actions:
        return decision

    attack_steps: list[tuple[dict[str, str], int, int]] = []
    for action in attack_actions:
        step_count = get_player_attack_step_count(actor, action)
        attack_steps.extend((action, step_index, step_count) for step_index in range(step_count))

    if state.player_behavior == "dumb":
        dice_available = actor.resources.superiority_dice
        for action, step_index, step_count in attack_steps:
            if dice_available <= 0:
                break
            if action.get("maneuver_id"):
                continue
            set_attack_maneuver_intent(action, step_index, step_count, "battle_master_auto", DUMB_PRECISION_ATTACK_MAX_MISS_MARGIN)
            dice_available -= 1
        return decision

    dice_available = actor.resources.superiority_dice
    trip_planned = False
    for index, (action, step_index, step_count) in enumerate(attack_steps):
        if action.get("maneuver_id"):
            continue

        target = state.units.get(action.get("target_id", ""))
        weapon = actor.attacks.get(action.get("weapon_id", ""))
        if not target or not weapon:
            continue

        has_follow_up_melee_attack = any(
            later_action is not action or later_step_index != step_index
            for later_action, later_step_index, _ in attack_steps[index + 1 :]
            if attack_action_uses_melee_weapon(actor, later_action)
        )
        if (
            weapon.kind == "melee"
            and has_follow_up_melee_attack
            and not trip_planned
            and target_is_trip_eligible(target)
            and dice_available > 1
            and can_use_battle_master_maneuver(actor, "trip_attack")
        ):
            set_attack_maneuver_intent(action, step_index, step_count, "trip_attack")
            dice_available -= 1
            trip_planned = True
            continue

        precision_max_miss_margin = get_smart_precision_max_miss_margin(state, actor, target, weapon, dice_available)
        if can_use_battle_master_maneuver(actor, "precision_attack") and (
            dice_available > 1 or precision_max_miss_margin == SMART_PRECISION_ATTACK_FINISHER_MAX_MISS_MARGIN
        ):
            set_attack_maneuver_intent(action, step_index, step_count, "precision_attack", precision_max_miss_margin)
            dice_available -= 1

    return decision


def should_commit_barbarian_rage(
    state: EncounterState,
    actor: UnitState,
    *,
    will_attack_this_turn: bool,
    position_index: PositionIndex | None = None,
) -> bool:
    if not can_open_barbarian_rage(actor):
        return False

    # Rage should be committed when the barbarian can actually attack this turn,
    # or when the front line has already collapsed enough that a normal enemy
    # move-and-attack line is likely before the barbarian acts again.
    return will_attack_this_turn or is_barbarian_under_immediate_melee_threat(state, actor, position_index)


def finalize_player_bonus_action_decision(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    position_index: PositionIndex | None = None,
) -> TurnDecision:
    decision = apply_monk_martial_arts(state, actor, decision)
    decision = apply_rogue_cunning_action(state, actor, decision, position_index)
    decision = apply_barbarian_opening_rage(state, actor, decision, position_index)
    decision = apply_barbarian_rage_upkeep(actor, decision)
    return apply_fighter_tactical_shift(state, actor, decision, position_index)


def finalize_player_turn_decision(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    melee_weapon_id: str,
    position_index: PositionIndex | None = None,
) -> TurnDecision:
    decision = apply_fighter_action_surge(state, actor, decision, melee_weapon_id, position_index)
    decision = apply_fighter_maneuver_intents(state, actor, decision)
    return finalize_player_bonus_action_decision(state, actor, decision, position_index)


def build_fighter_action_surge_dash_attack_decision(
    state: EncounterState,
    actor: UnitState,
    melee_targets: list[UnitState],
    melee_weapon_id: str,
    move_squares: int,
    dash_squares: int,
    position_index: PositionIndex | None = None,
) -> TurnDecision | None:
    if not can_use_action_surge(actor):
        return None

    melee_option = (
        get_smart_melee_attack_option(state, actor, melee_targets, dash_squares, melee_weapon_id, position_index)
        if state.player_behavior == "smart"
        else None
    )

    if melee_option is None:
        for target in melee_targets:
            allow_provoking = can_intentionally_provoke_opportunity_attack(state, actor, target)
            candidate = find_preferred_adjacent_square(
                state,
                actor.id,
                target.id,
                dash_squares,
                allow_provoking,
                position_index,
            )
            if candidate:
                melee_option = MeleeAttackOption(
                    target=target,
                    path=candidate.path,
                    distance=candidate.distance,
                    creates_flank=False,
                    adjacent_allies=count_adjacent_allied_units(state, actor, target),
                )
                break

    if not melee_option or melee_option.distance <= move_squares:
        return None

    return finalize_player_turn_decision(
        state,
        actor,
        TurnDecision(
            action={"kind": "dash", "reason": f"Dashing toward {melee_option.target.id} before Action Surge."},
            between_action_movement=MovementPlan(path=melee_option.path, mode="dash"),
            surged_action={"kind": "attack", "target_id": melee_option.target.id, "weapon_id": melee_weapon_id},
        ),
        melee_weapon_id,
        position_index,
    )


def get_enemy_melee_weapon_id(actor: UnitState) -> AttackId:
    preferred_order = ("toad_bite", "crocodile_bite", "scimitar", "greataxe", "spear", "bite", "club")
    for weapon_id in preferred_order:
        weapon = actor.attacks.get(weapon_id)
        if weapon and weapon.kind == "melee":
            return weapon_id

    for weapon_id, weapon in actor.attacks.items():
        if weapon and weapon.kind == "melee":
            return weapon_id

    raise ValueError(f"{actor.id} has no melee weapon profile.")


def get_enemy_ranged_weapon_id(actor: UnitState) -> AttackId:
    preferred_order = ("longbow", "shortbow")
    for weapon_id in preferred_order:
        weapon = actor.attacks.get(weapon_id)
        if weapon and weapon.kind == "ranged":
            return weapon_id

    for weapon_id, weapon in actor.attacks.items():
        if weapon and weapon.kind == "ranged":
            return weapon_id

    raise ValueError(f"{actor.id} has no ranged weapon profile.")


def get_movement_distance(plan: MovementPlan | None) -> int:
    if not plan or len(plan.path) <= 1:
        return 0
    return len(plan.path) - 1


def choose_closest_reachable_square(candidates: list[ReachableSquare]) -> ReachableSquare | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda square: (square.distance, square.position.x, square.position.y))[0]


def choose_advance_square(candidates: list[ReachableSquare], target_position: GridPosition) -> ReachableSquare | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda square: (
            chebyshev_distance(square.position, target_position),
            -square.distance,
            square.position.x,
            square.position.y,
        ),
    )[0]


def get_distance_between_units(actor: UnitState, target: UnitState) -> int:
    if not actor.position or not target.position:
        return 0
    return get_min_chebyshev_distance_between_footprints(
        actor.position,
        get_unit_footprint(actor),
        target.position,
        get_unit_footprint(target),
    )


def get_distance_for_priority(state: EncounterState, actor: UnitState, target: UnitState) -> int:
    _ = state
    return get_distance_between_units(actor, target)


def average_dice_total(dice_specs) -> float:
    return sum(spec.count * (spec.sides + 1) / 2 for spec in dice_specs)


def average_damage_component_total(component) -> float:
    return average_dice_total(component.damage_dice) + component.damage_modifier


def get_weapon_base_damage_components(weapon: WeaponProfile) -> list[tuple[str, float]]:
    if weapon.damage_components:
        return [(component.damage_type, average_damage_component_total(component)) for component in weapon.damage_components]

    damage_type = weapon.damage_type or "damage"
    return [(damage_type, average_dice_total(weapon.damage_dice) + weapon.damage_modifier)]


def get_weapon_advantage_damage_components(weapon: WeaponProfile) -> list[tuple[str, float]]:
    components: list[tuple[str, float]] = []
    default_damage_type = weapon.damage_type or (
        weapon.damage_components[0].damage_type if weapon.damage_components else "damage"
    )

    if weapon.advantage_damage_dice:
        components.append((default_damage_type, average_dice_total(weapon.advantage_damage_dice)))

    for component in weapon.advantage_damage_components or []:
        components.append((component.damage_type, average_damage_component_total(component)))

    return components


def get_attack_range_squares(weapon: WeaponProfile) -> int:
    if weapon.kind == "melee":
        return max(1, (weapon.reach or 5) // 5)
    if weapon.range is None:
        return 0
    return max(0, weapon.range.normal // 5)


def build_remaining_attack_step_weapon_profiles(
    actor: UnitState,
    *,
    preferred_weapon_id: str | None = None,
    action_id: str | None = None,
    step_index: int = 0,
) -> tuple[tuple[WeaponProfile, ...], ...]:
    attack_action = get_attack_action_definition_for_unit(
        actor,
        preferred_weapon_id=preferred_weapon_id,
        action_id=action_id,
    )
    remaining_steps = attack_action.steps[step_index:]
    return tuple(
        tuple(actor.attacks[weapon_id] for weapon_id in step.allowed_weapon_ids if weapon_id in actor.attacks)
        for step in remaining_steps
    )


def build_repeated_weapon_step_profiles(actor: UnitState, weapon_id: str) -> tuple[tuple[WeaponProfile, ...], ...]:
    weapon = actor.attacks.get(weapon_id)
    if weapon is None:
        return ()

    attack_action = get_attack_action_definition_for_unit(actor, preferred_weapon_id=weapon_id)
    return tuple((weapon,) for _ in attack_action.steps)


def build_single_attack_step_profiles(attack_profile: WeaponProfile) -> tuple[tuple[WeaponProfile, ...], ...]:
    return ((attack_profile,),)


def get_attack_mode_for_context(
    state: EncounterState,
    attacker: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    spatial_context,
) -> AttackMode:
    advantage_sources = list(spatial_context.advantage_sources)
    disadvantage_sources = list(spatial_context.disadvantage_sources)

    if target.conditions.unconscious:
        advantage_sources.append("target_unconscious")

    if unit_is_hidden(attacker):
        advantage_sources.append("hidden")

    if unit_is_dodging(target):
        disadvantage_sources.append("target_dodging")

    if unit_is_hidden(target):
        disadvantage_sources.append("target_hidden")

    if any(effect.kind == "restrained_by" for effect in target.temporary_effects):
        advantage_sources.append("target_restrained")

    if unit_has_reckless_attack_effect(target):
        advantage_sources.append("target_reckless")

    if target.conditions.prone and spatial_context.distance_squares is not None:
        if spatial_context.distance_squares <= 1:
            advantage_sources.append("target_prone")
        else:
            disadvantage_sources.append("target_prone")

    if any(effect.kind == "sap" for effect in attacker.temporary_effects):
        disadvantage_sources.append("sap")

    if any(effect.kind in {"restrained_by", "blinded_by"} for effect in attacker.temporary_effects):
        disadvantage_sources.append("impaired_attacker")

    if has_vex_effect(attacker, target.id):
        advantage_sources.append("vex")

    if has_harried_effect(target):
        advantage_sources.append("harried_target")

    if weapon.advantage_against_self_grappled_target and target_is_grappled_by_attacker(state, target, attacker.id):
        advantage_sources.append("self_grappled_target")

    if attacker.faction == "goblins" and unit_is_bloodied(attacker) and unit_has_trait(attacker, "bloodied_frenzy"):
        advantage_sources.append("bloodied_frenzy")

    if unit_has_reckless_attack_effect(attacker) and weapon.attack_ability == "str":
        advantage_sources.append("reckless_attack")

    if advantage_sources and disadvantage_sources:
        return "normal"
    if advantage_sources:
        return "advantage"
    if disadvantage_sources:
        return "disadvantage"
    return "normal"


def attack_roll_hits(natural_roll: int, attack_bonus: int, target_ac: int) -> bool:
    if natural_roll == 1:
        return False
    if natural_roll == 20:
        return True
    return natural_roll + attack_bonus >= target_ac


def get_hit_probability(attack_bonus: int, target_ac: int, attack_mode: AttackMode) -> float:
    if attack_mode == "normal":
        return sum(1 for roll in range(1, 21) if attack_roll_hits(roll, attack_bonus, target_ac)) / 20.0

    successful_pairs = 0
    for first_roll in range(1, 21):
        for second_roll in range(1, 21):
            selected_roll = max(first_roll, second_roll) if attack_mode == "advantage" else min(first_roll, second_roll)
            if attack_roll_hits(selected_roll, attack_bonus, target_ac):
                successful_pairs += 1
    return successful_pairs / 400.0


def get_average_on_hit_damage(
    state: EncounterState,
    attacker: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    attack_mode: AttackMode,
) -> float:
    components = get_weapon_base_damage_components(weapon)
    if attack_mode == "advantage":
        components.extend(get_weapon_advantage_damage_components(weapon))

    if can_apply_sneak_attack(state, attacker, target, weapon, attack_mode):
        components.append(("precision", get_sneak_attack_d6_count(attacker) * 3.5))

    rage_damage_bonus = get_rage_damage_bonus(attacker, weapon)
    if rage_damage_bonus > 0:
        primary_damage_type = components[0][0] if components else (weapon.damage_type or "damage")
        components.append((primary_damage_type, float(rage_damage_bonus)))

    total_damage = 0.0
    for damage_type, average_damage in components:
        immune, resistant, vulnerable = get_damage_defense_flags(target, damage_type)
        if immune:
            continue
        if resistant and not vulnerable:
            average_damage *= 0.5
        elif vulnerable and not resistant:
            average_damage *= 2.0
        total_damage += average_damage
    return total_damage


def get_attack_projection_for_weapon(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    *,
    attacker_position: GridPosition | None = None,
    target_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> AttackProjection | None:
    attack_context = get_attack_context(
        state,
        actor.id,
        target.id,
        weapon,
        attacker_position,
        target_position,
        position_index,
    )
    if not attack_context.legal:
        return None

    attack_mode = get_attack_mode_for_context(state, actor, target, weapon, attack_context)
    target_ac = target.ac + get_shield_ac_bonus(target) + attack_context.cover_ac_bonus
    hit_probability = get_hit_probability(weapon.attack_bonus, target_ac, attack_mode)
    average_on_hit_damage = get_average_on_hit_damage(state, actor, target, weapon, attack_mode)
    return AttackProjection(hit_probability=hit_probability, average_on_hit_damage=average_on_hit_damage)


def get_best_attack_step_projection(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    weapon_profiles: tuple[WeaponProfile, ...],
    *,
    preferred_weapon_id: str | None = None,
    attacker_position: GridPosition | None = None,
    target_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> AttackProjection | None:
    best_choice: tuple[tuple[float, int, float, float], AttackProjection] | None = None

    for weapon in weapon_profiles:
        projection = get_attack_projection_for_weapon(
            state,
            actor,
            target,
            weapon,
            attacker_position=attacker_position,
            target_position=target_position,
            position_index=position_index,
        )
        if projection is None:
            continue

        score = (
            projection.hit_probability * projection.average_on_hit_damage,
            1 if weapon.id == preferred_weapon_id else 0,
            projection.average_on_hit_damage,
            projection.hit_probability,
        )
        if best_choice is None or score > best_choice[0]:
            best_choice = (score, projection)

    return best_choice[1] if best_choice else None


def probability_of_at_least_hits(probabilities: list[float], minimum_hits: int) -> float:
    if minimum_hits <= 0:
        return 1.0
    if minimum_hits > len(probabilities):
        return 0.0

    dp = [0.0] * (len(probabilities) + 1)
    dp[0] = 1.0
    for probability in probabilities:
        next_dp = [0.0] * (len(probabilities) + 1)
        for hits, chance in enumerate(dp):
            if chance == 0.0:
                continue
            next_dp[hits] += chance * (1.0 - probability)
            next_dp[hits + 1] += chance * probability
        dp = next_dp
    return sum(dp[minimum_hits:])


def classify_target_kill_band(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    attack_step_weapon_profiles: tuple[tuple[WeaponProfile, ...], ...] | None,
    *,
    preferred_weapon_id: str | None = None,
    attacker_position: GridPosition | None = None,
    target_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> tuple[int, float]:
    if not attack_step_weapon_profiles:
        return 0, 0.0

    projections = [
        projection
        for weapon_profiles in attack_step_weapon_profiles
        if (
            projection := get_best_attack_step_projection(
                state,
                actor,
                target,
                weapon_profiles,
                preferred_weapon_id=preferred_weapon_id,
                attacker_position=attacker_position,
                target_position=target_position,
                position_index=position_index,
            )
        )
        is not None
    ]
    if not projections:
        return 0, 0.0

    remaining_hp = float(target.current_hp)
    hits_needed = 0
    for projection in sorted(projections, key=lambda item: item.average_on_hit_damage, reverse=True):
        remaining_hp -= projection.average_on_hit_damage
        hits_needed += 1
        if remaining_hp <= 0:
            break

    if remaining_hp > 0:
        return 0, 0.0

    kill_probability = probability_of_at_least_hits(
        [projection.hit_probability for projection in projections],
        hits_needed,
    )
    if kill_probability >= 0.8:
        return 2, kill_probability
    if kill_probability >= 0.6:
        return 1, kill_probability
    return 0, kill_probability


def can_pressure_allies_now(state: EncounterState, actor: UnitState, threatened_faction: str) -> bool:
    for unit in get_units_by_faction(state, threatened_faction):
        if not is_unit_conscious(unit) or not unit.position:
            continue
        for weapon in actor.attacks.values():
            if get_attack_context(state, actor.id, unit.id, weapon).legal:
                return True
    return False


def can_pressure_allies_next_turn(state: EncounterState, actor: UnitState, threatened_faction: str) -> bool:
    if not actor.position:
        return False

    move_squares = get_move_squares(actor, state)
    for unit in get_units_by_faction(state, threatened_faction):
        if not is_unit_conscious(unit) or not unit.position:
            continue

        distance_to_target = get_distance_between_units(actor, unit)
        for weapon in actor.attacks.values():
            if distance_to_target <= move_squares + get_attack_range_squares(weapon):
                return True
    return False


def get_target_immediacy(state: EncounterState, actor: UnitState, target: UnitState) -> int:
    if not target.position or not is_unit_conscious(target):
        return 0
    if can_pressure_allies_now(state, target, actor.faction):
        return 3
    if can_pressure_allies_next_turn(state, target, actor.faction):
        return 2
    return 1


def get_target_base_threat_tier(target: UnitState) -> int:
    has_swallow = target.faction == "goblins" and "swallow" in get_monster_definition_for_unit(target).special_action_ids
    has_grapple_and_restrain = any(
        weapon.kind == "melee"
        and any(effect.kind == "grapple_and_restrain" for effect in weapon.on_hit_effects or [])
        for weapon in target.attacks.values()
    )
    has_pressure_rider = any(
        weapon.kind == "melee"
        and any(effect.kind in {"grapple_on_hit", "prone_on_hit", "harry_target"} for effect in weapon.on_hit_effects or [])
        for weapon in target.attacks.values()
    )
    has_multiattack = len(get_attack_action_definition_for_unit(target).steps) >= 2
    has_elite_reaction = unit_has_reaction(target, "parry") or unit_has_reaction(target, "redirect_attack")

    if has_role_tag(target, "caster") or has_role_tag(target, "healer"):
        return 4
    if has_role_tag(target, "controller") or has_swallow or has_grapple_and_restrain:
        return 3
    if has_pressure_rider or has_multiattack or has_elite_reaction:
        return 2
    return 1


def get_target_threat_tier(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    immediacy: int | None = None,
) -> int:
    resolved_immediacy = get_target_immediacy(state, actor, target) if immediacy is None else immediacy
    base_tier = get_target_base_threat_tier(target)

    if resolved_immediacy <= 1:
        if has_role_tag(target, "caster") or has_role_tag(target, "healer"):
            return 2
        return 1

    if resolved_immediacy == 2:
        if base_tier >= 4:
            return 3
        if base_tier >= 3:
            return 2
    return base_tier


def build_smart_target_priority(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    *,
    attack_step_weapon_profiles: tuple[tuple[WeaponProfile, ...], ...] | None = None,
    preferred_weapon_id: str | None = None,
    attacker_position: GridPosition | None = None,
    target_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> tuple[int, int, float, int, int, int]:
    kill_band, kill_probability = classify_target_kill_band(
        state,
        actor,
        target,
        attack_step_weapon_profiles,
        preferred_weapon_id=preferred_weapon_id,
        attacker_position=attacker_position,
        target_position=target_position,
        position_index=position_index,
    )
    immediacy = get_target_immediacy(state, actor, target)
    threat_tier = get_target_threat_tier(state, actor, target, immediacy)
    allied_pressure = count_adjacent_allied_units(state, actor, target)
    return (
        -kill_band,
        -threat_tier,
        -immediacy,
        -allied_pressure,
        -kill_probability,
        target.current_hp,
    )


def sort_fighter_targets(state: EncounterState, actor: UnitState, units: list[UnitState]) -> list[UnitState]:
    return sorted(
        units,
        key=lambda unit: (unit.current_hp, get_distance_for_priority(state, actor, unit), unit.id),
    )


def count_adjacent_allied_units(state: EncounterState, actor: UnitState, target: UnitState) -> int:
    if not target.position:
        return 0

    return len(
        [
            unit
            for unit in get_units_by_faction(state, actor.faction)
            if unit.id != actor.id
            and is_unit_conscious(unit)
            and unit.position
            and get_distance_between_units(unit, target) <= 1
        ]
    )


def sort_player_combat_targets(
    state: EncounterState,
    actor: UnitState,
    units: list[UnitState],
    behavior: ResolvedPlayerBehavior,
    *,
    attack_step_weapon_profiles: tuple[tuple[WeaponProfile, ...], ...] | None = None,
    preferred_weapon_id: str | None = None,
    attacker_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> list[UnitState]:
    if behavior == "dumb":
        return sorted(units, key=lambda unit: (get_distance_for_priority(state, actor, unit), unit.id))

    return sorted(
        units,
        key=lambda unit: (
            *build_smart_target_priority(
                state,
                actor,
                unit,
                attack_step_weapon_profiles=attack_step_weapon_profiles,
                preferred_weapon_id=preferred_weapon_id,
                attacker_position=attacker_position,
                target_position=unit.position,
                position_index=position_index,
            ),
            get_distance_for_priority(state, actor, unit),
            unit.id,
        ),
    )


def sort_player_melee_targets(
    state: EncounterState,
    actor: UnitState,
    units: list[UnitState],
    behavior: ResolvedPlayerBehavior,
    *,
    melee_weapon_id: str | None = None,
    attack_profile: WeaponProfile | None = None,
    position_index: PositionIndex | None = None,
) -> list[UnitState]:
    if behavior == "dumb":
        return sort_player_combat_targets(state, actor, units, behavior)

    attack_step_weapon_profiles = (
        build_single_attack_step_profiles(attack_profile)
        if attack_profile is not None
        else build_repeated_weapon_step_profiles(actor, melee_weapon_id)
        if melee_weapon_id is not None
        else None
    )

    return sorted(
        units,
        key=lambda unit: (
            *build_smart_target_priority(
                state,
                actor,
                unit,
                attack_step_weapon_profiles=attack_step_weapon_profiles,
                preferred_weapon_id=melee_weapon_id or (attack_profile.id if attack_profile is not None else None),
                position_index=position_index,
            ),
            get_distance_for_priority(state, actor, unit),
            unit.id,
        ),
    )


def sort_player_ranged_targets(
    state: EncounterState,
    actor: UnitState,
    units: list[UnitState],
    behavior: ResolvedPlayerBehavior,
    *,
    ranged_weapon_id: str | None = None,
    attack_profile: WeaponProfile | None = None,
    position_index: PositionIndex | None = None,
) -> list[UnitState]:
    if behavior == "dumb":
        return sorted(units, key=lambda unit: (get_distance_for_priority(state, actor, unit), unit.id))

    attack_step_weapon_profiles = (
        build_single_attack_step_profiles(attack_profile)
        if attack_profile is not None
        else build_repeated_weapon_step_profiles(actor, ranged_weapon_id)
        if ranged_weapon_id is not None
        else None
    )

    return sorted(
        units,
        key=lambda unit: (
            *build_smart_target_priority(
                state,
                actor,
                unit,
                attack_step_weapon_profiles=attack_step_weapon_profiles,
                preferred_weapon_id=ranged_weapon_id or (attack_profile.id if attack_profile is not None else None),
                position_index=position_index,
            ),
            get_distance_for_priority(state, actor, unit),
            unit.id,
        ),
    )


def sort_closest_targets(state: EncounterState, actor: UnitState, units: list[UnitState]) -> list[UnitState]:
    return sorted(
        units,
        key=lambda unit: (get_distance_for_priority(state, actor, unit), unit.current_hp, unit.id),
    )


def get_conscious_fighter_targets(state: EncounterState) -> list[UnitState]:
    return [unit for unit in get_units_by_faction(state, "fighters") if is_unit_conscious(unit)]


def get_downed_fighter_targets(state: EncounterState) -> list[UnitState]:
    return [unit for unit in get_units_by_faction(state, "fighters") if is_unit_downed(unit)]


def sort_kind_targets(state: EncounterState, actor: UnitState, units: list[UnitState]) -> list[UnitState]:
    return sorted(
        units,
        key=lambda unit: (
            int(unit_is_hidden(unit)),
            -get_hp_ratio(unit),
            get_distance_for_priority(state, actor, unit),
            -unit.current_hp,
            unit.id,
        ),
    )


def sort_balanced_monster_targets(state: EncounterState, actor: UnitState, units: list[UnitState]) -> list[UnitState]:
    return sorted(
        units,
        key=lambda unit: (
            int(unit_is_hidden(unit)),
            unit.current_hp,
            get_distance_for_priority(state, actor, unit),
            unit.id,
        ),
    )


def sort_evil_conscious_targets(state: EncounterState, actor: UnitState, units: list[UnitState]) -> list[UnitState]:
    return sorted(
        units,
        key=lambda unit: (
            int(unit_is_hidden(unit)),
            -int(has_role_tag(unit, "healer")),
            -int(has_role_tag(unit, "caster")),
            get_hp_ratio(unit),
            get_distance_for_priority(state, actor, unit),
            unit.id,
        ),
    )


def sort_downed_targets(state: EncounterState, actor: UnitState, units: list[UnitState]) -> list[UnitState]:
    return sorted(units, key=lambda unit: (get_distance_for_priority(state, actor, unit), unit.id))


def get_ranked_attack_targets(
    state: EncounterState,
    actor: UnitState,
    preferred_target_id: str | None = None,
    *,
    preferred_weapon_id: str | None = None,
    action_id: str | None = None,
    step_index: int = 0,
) -> list[UnitState]:
    """Return the actor's current ordered target list for repeated attacks.

    This is intentionally simpler than the full turn-planning logic. It exists
    so multiattack and future Extra Attack flows can keep the same target if it
    survives, then fall through to the next best legal target after each hit.
    """

    if actor.faction == "fighters":
        attack_step_weapon_profiles = build_remaining_attack_step_weapon_profiles(
            actor,
            preferred_weapon_id=preferred_weapon_id,
            action_id=action_id,
            step_index=step_index,
        )
        targets = sort_player_combat_targets(
            state,
            actor,
            [unit for unit in get_units_by_faction(state, "goblins") if not unit.conditions.dead],
            state.player_behavior,
            attack_step_weapon_profiles=attack_step_weapon_profiles,
            preferred_weapon_id=preferred_weapon_id,
        )
    else:
        conscious_targets = get_conscious_fighter_targets(state)
        if state.monster_behavior == "kind":
            targets = sort_kind_targets(state, actor, conscious_targets)
        elif state.monster_behavior == "balanced":
            targets = sort_balanced_monster_targets(state, actor, conscious_targets)
        else:
            targets = sort_evil_conscious_targets(state, actor, conscious_targets) + sort_downed_targets(
                state,
                actor,
                get_downed_fighter_targets(state),
            )

    swallowed_by = get_swallow_source_id(actor)
    if swallowed_by:
        swallowing_unit = state.units.get(swallowed_by)
        return [swallowing_unit] if swallowing_unit and not swallowing_unit.conditions.dead else []

    if not preferred_target_id:
        return targets

    preferred_target = next((target for target in targets if target.id == preferred_target_id), None)
    if not preferred_target:
        return targets

    return [preferred_target, *[target for target in targets if target.id != preferred_target_id]]


def can_intentionally_provoke_opportunity_attack(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
) -> bool:
    if actor.faction == "fighters":
        if state.player_behavior != "smart":
            return False

        # The smart-player exception exists for future high-value enemies.
        # In the current content set no enemy is marked that way, so this stays dormant.
        _ = target
        return False

    if state.monster_behavior != "evil":
        return False

    # Evil monsters may risk an opportunity attack to pressure a healer or caster,
    # but they should not do that just to finish a downed target.
    if is_unit_downed(target):
        return False

    return has_role_tag(target, "healer") or has_role_tag(target, "caster")


def get_safe_reachable_squares(
    state: EncounterState,
    actor_id: str,
    max_move_squares: int,
    allow_provoking: bool = False,
    position_index: PositionIndex | None = None,
) -> list[ReachableSquare]:
    reachable_squares = get_reachable_squares(state, actor_id, max_move_squares, position_index)
    if allow_provoking:
        return reachable_squares

    actor = state.units[actor_id]
    threatening_units = get_units_with_positions(
        state,
        "goblins" if actor.faction == "fighters" else "fighters",
        position_index,
    )
    return [
        square
        for square in reachable_squares
        if not path_provokes_opportunity_attack(state, actor_id, square.path, position_index, threatening_units)
    ]


def find_preferred_adjacent_square(
    state: EncounterState,
    mover_id: str,
    target_id: str,
    max_squares: int,
    allow_provoking: bool = False,
    position_index: PositionIndex | None = None,
) -> ReachableSquare | None:
    target = state.units[target_id]
    if not target.position:
        return None

    candidates = [
        square
        for square in get_safe_reachable_squares(state, mover_id, max_squares, allow_provoking, position_index)
        if get_min_chebyshev_distance_between_footprints(
            square.position,
            get_unit_footprint(state.units[mover_id]),
            target.position,
            get_unit_footprint(target),
        )
        <= 1
    ]
    return choose_closest_reachable_square(candidates)


def find_preferred_advance_path(
    state: EncounterState,
    mover_id: str,
    target_id: str,
    max_squares: int,
    allow_provoking: bool = False,
    position_index: PositionIndex | None = None,
) -> ReachableSquare | None:
    target = state.units[target_id]
    mover = state.units[mover_id]
    if not target.position:
        return None

    adjacent_path = find_preferred_adjacent_square(
        state,
        mover_id,
        target_id,
        max_squares,
        allow_provoking,
        position_index,
    )
    if adjacent_path:
        return adjacent_path

    reachable = get_safe_reachable_squares(state, mover_id, max_squares, allow_provoking, position_index)
    if not reachable:
        return None

    return sorted(
        reachable,
        key=lambda square: (
            get_min_chebyshev_distance_between_footprints(
                square.position,
                get_unit_footprint(mover),
                target.position,
                get_unit_footprint(target),
            ),
            -square.distance,
            square.position.x,
            square.position.y,
        ),
    )[0]


def build_melee_attack_options(
    state: EncounterState,
    actor: UnitState,
    targets: list[UnitState],
    move_squares: int,
    weapon_id: str,
    seek_flanking: bool,
    position_index: PositionIndex | None = None,
) -> list[MeleeAttackOption]:
    weapon = actor.attacks.get(weapon_id)
    if not weapon or not actor.position:
        return []

    options: list[MeleeAttackOption] = []

    for target in targets:
        if not target.position:
            continue

        allow_provoking = can_intentionally_provoke_opportunity_attack(state, actor, target)
        if seek_flanking:
            candidate_squares = [
                square
                for square in get_safe_reachable_squares(state, actor.id, move_squares, allow_provoking, position_index)
                if get_attack_context(
                    state,
                    actor.id,
                    target.id,
                    weapon,
                    square.position,
                    target.position,
                    position_index,
                ).legal
            ]
        else:
            legal_squares = [
                square
                for square in get_safe_reachable_squares(state, actor.id, move_squares, allow_provoking, position_index)
                if get_attack_context(
                    state,
                    actor.id,
                    target.id,
                    weapon,
                    square.position,
                    target.position,
                    position_index,
                ).legal
            ]
            best_square = choose_closest_reachable_square(legal_squares)
            candidate_squares = [best_square] if best_square else []

        adjacent_allies = count_adjacent_allied_units(state, actor, target)

        for square in candidate_squares:
            if not square:
                continue
            attack_context = get_attack_context(
                state,
                actor.id,
                target.id,
                weapon,
                square.position,
                target.position,
                position_index,
            )
            if not attack_context.legal:
                continue
            creates_flank = "flanking" in get_attack_context(
                state,
                actor.id,
                target.id,
                weapon,
                square.position,
                target.position,
                position_index,
            ).advantage_sources
            options.append(
                MeleeAttackOption(
                    target=target,
                    path=square.path,
                    distance=square.distance,
                    creates_flank=creates_flank,
                    adjacent_allies=adjacent_allies,
                )
            )

    return options


def get_smart_melee_attack_option(
    state: EncounterState,
    actor: UnitState,
    targets: list[UnitState],
    move_squares: int,
    melee_weapon_id: str,
    position_index: PositionIndex | None = None,
) -> MeleeAttackOption | None:
    options = build_melee_attack_options(state, actor, targets, move_squares, melee_weapon_id, True, position_index)
    if not options:
        return None

    attack_step_weapon_profiles = build_repeated_weapon_step_profiles(actor, melee_weapon_id)

    def option_priority(option: MeleeAttackOption) -> tuple[int, int, int, int, int, int, int, float, int, str, int]:
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
        )

    return sorted(
        options,
        key=lambda option: option_priority(option) + (option.path[-1].y,),
    )[0]


def choose_first_targeted_plan(targets: list[UnitState], build_plan):
    for target in targets:
        plan = build_plan(target)
        if plan:
            return plan
    return None


def choose_kind_targeted_plan(preferred_targets: list[UnitState], fallback_targets: list[UnitState], build_plan):
    preferred_target = preferred_targets[0] if preferred_targets else None
    if preferred_target:
        preferred_plan = build_plan(preferred_target)
        if preferred_plan:
            return preferred_plan
    return choose_first_targeted_plan(fallback_targets, build_plan)


def choose_closest_monster_melee_option(options: list[MeleeAttackOption]) -> MeleeAttackOption | None:
    if not options:
        return None
    return sorted(
        options,
        key=lambda option: (
            option.distance,
            option.target.current_hp,
            option.target.id,
            option.path[-1].x,
            option.path[-1].y,
        ),
    )[0]


def choose_balanced_monster_melee_option(options: list[MeleeAttackOption]) -> MeleeAttackOption | None:
    if not options:
        return None
    return sorted(
        options,
        key=lambda option: (
            -int(option.creates_flank),
            option.target.current_hp,
            option.distance,
            option.target.id,
            option.path[-1].x,
            option.path[-1].y,
        ),
    )[0]


def choose_evil_monster_melee_option(options: list[MeleeAttackOption]) -> MeleeAttackOption | None:
    if not options:
        return None
    return sorted(
        options,
        key=lambda option: (
            -int(has_role_tag(option.target, "healer")),
            -int(has_role_tag(option.target, "caster")),
            get_hp_ratio(option.target),
            -int(option.creates_flank),
            option.distance,
            option.target.id,
            option.path[-1].x,
            option.path[-1].y,
        ),
    )[0]


def build_ranged_attack_plan(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    weapon_id: str,
    max_move_squares: int,
    require_normal_range: bool,
    require_movement: bool,
    prefer_distance_from_faction: str | None = None,
    avoid_opportunity_attacks: bool = True,
    prefer_hide_positions: bool = False,
    position_index: PositionIndex | None = None,
) -> AttackPlan | None:
    weapon = actor.attacks.get(weapon_id)
    if not weapon or not target.position or not actor.position:
        return None

    candidates = []
    for square in get_safe_reachable_squares(
        state,
        actor.id,
        max_move_squares,
        not avoid_opportunity_attacks,
        position_index,
    ):
        if require_movement and square.distance <= 0:
            continue
        context = get_attack_context(
            state,
            actor.id,
            target.id,
            weapon,
            square.position,
            target.position,
            position_index,
        )
        if not context.legal:
            continue
        if require_normal_range and not context.within_normal_range:
            continue
        candidates.append((square, context))

    if not candidates:
        return None

    def sort_key(item):
        square, context = item
        adjacent_penalty = int("adjacent_enemy" in context.disadvantage_sources)
        can_hide_here = (
            prefer_hide_positions and can_attempt_hide_from_position(state, actor.id, square.position, position_index)
        )
        distance_from_faction = (
            -get_min_distance_to_faction(
                state,
                square.position,
                prefer_distance_from_faction,
                position_index,
                get_unit_footprint(actor),
            )
            if prefer_distance_from_faction
            else 0
        )
        return (
            -int(context.within_normal_range),
            adjacent_penalty,
            -int(can_hide_here),
            context.cover_ac_bonus,
            distance_from_faction,
            square.distance,
            square.position.x,
            square.position.y,
        )

    best_square, _ = sorted(candidates, key=sort_key)[0]
    return AttackPlan(target_id=target.id, weapon_id=weapon_id, path=best_square.path)


def build_spell_attack_context_profile(spell_id: str) -> WeaponProfile:
    spell = get_spell_definition(spell_id)
    is_melee_spell = spell.targeting_mode == "melee_spell_attack"
    return WeaponProfile(
        id=spell_id,
        display_name=spell.display_name,
        attack_bonus=0,
        ability_modifier=0,
        damage_dice=[],
        damage_modifier=0,
        kind="melee" if is_melee_spell else "ranged",
        reach=spell.range_feet if is_melee_spell else None,
        range=None if is_melee_spell else WeaponRange(normal=spell.range_feet, long=spell.range_feet),
    )


def build_spell_attack_plan(
    state: EncounterState,
    actor: UnitState,
    target: UnitState,
    spell_id: str,
    max_move_squares: int,
    position_index: PositionIndex | None = None,
) -> AttackPlan | None:
    spell_profile = build_spell_attack_context_profile(spell_id)
    if not target.position or not actor.position:
        return None

    candidates = []
    for square in get_safe_reachable_squares(
        state,
        actor.id,
        max_move_squares,
        False,
        position_index,
    ):
        context = get_attack_context(
            state,
            actor.id,
            target.id,
            spell_profile,
            square.position,
            target.position,
            position_index,
        )
        if not context.legal or not context.within_normal_range:
            continue
        candidates.append((square, context))

    if not candidates:
        return None

    def sort_key(item):
        square, context = item
        return (
            int("adjacent_enemy" in context.disadvantage_sources),
            context.cover_ac_bonus,
            -get_min_distance_to_faction(
                state,
                square.position,
                "goblins" if actor.faction == "fighters" else "fighters",
                position_index,
                get_unit_footprint(actor),
            ),
            square.distance,
            square.position.x,
            square.position.y,
        )

    best_square, _ = sorted(candidates, key=sort_key)[0]
    return AttackPlan(target_id=target.id, weapon_id=spell_id, path=best_square.path)


def build_post_action_advance(
    state: EncounterState,
    actor: UnitState,
    target_id: str,
    attack_position: GridPosition,
    remaining_move_squares: int,
) -> MovementPlan | None:
    if remaining_move_squares <= 0:
        return None

    projected_state = state.model_copy(deep=True)
    projected_state.units[actor.id].position = attack_position.model_copy(deep=True)
    advance = find_preferred_advance_path(projected_state, actor.id, target_id, remaining_move_squares)
    if not advance or advance.distance == 0:
        return None
    return MovementPlan(path=advance.path, mode="move")


def build_post_action_retreat(
    state: EncounterState,
    actor: UnitState,
    attack_position: GridPosition,
    remaining_move_squares: int,
) -> MovementPlan | None:
    if remaining_move_squares <= 0:
        return None

    projected_state = state.model_copy(deep=True)
    projected_actor = projected_state.units[actor.id]
    projected_actor.position = attack_position.model_copy(deep=True)
    projected_index = build_position_index(projected_state)
    threatened_by_faction = "goblins" if actor.faction == "fighters" else "fighters"

    retreat_options = get_safe_reachable_squares(
        projected_state,
        actor.id,
        remaining_move_squares,
        False,
        projected_index,
    )
    if not retreat_options:
        return None

    current_distance = get_min_distance_to_faction(
        projected_state,
        attack_position,
        threatened_by_faction,
        projected_index,
        get_unit_footprint(actor),
    )

    best_retreat = sorted(
        retreat_options,
        key=lambda square: (
            -get_min_distance_to_faction(
                projected_state,
                square.position,
                threatened_by_faction,
                projected_index,
                get_unit_footprint(actor),
            ),
            square.distance,
            square.position.x,
            square.position.y,
        ),
    )[0]

    best_distance = get_min_distance_to_faction(
        projected_state,
        best_retreat.position,
        threatened_by_faction,
        projected_index,
        get_unit_footprint(actor),
    )

    if best_retreat.distance == 0 or best_distance <= current_distance:
        return None

    return MovementPlan(path=best_retreat.path, mode="move")


def get_swallowed_player_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    swallowing_source_id = get_swallow_source_id(actor)
    if not swallowing_source_id or state.units[swallowing_source_id].conditions.dead:
        return TurnDecision(action={"kind": "skip", "reason": "No swallowing creature remains."})

    melee_weapon_id = get_player_primary_melee_weapon_id(actor)
    return finalize_player_turn_decision(
        state,
        actor,
        TurnDecision(
            bonus_action=get_player_bonus_action(actor),
            action={"kind": "attack", "target_id": swallowing_source_id, "weapon_id": melee_weapon_id},
        ),
        melee_weapon_id,
    )


def build_player_ranged_attack_decision(
    state: EncounterState,
    actor: UnitState,
    conscious_enemies: list[UnitState],
    ranged_weapon_id: str,
    move_squares: int,
    require_normal_range: bool,
    position_index: PositionIndex | None,
    bonus_action: dict[str, str] | None,
) -> TurnDecision | None:
    ranged_targets = sort_player_ranged_targets(
        state,
        actor,
        conscious_enemies,
        state.player_behavior,
        ranged_weapon_id=ranged_weapon_id,
        position_index=position_index,
    )
    prefer_distance_from_faction = "goblins" if is_player_ranged_skirmisher(actor) else None
    prefer_hide_positions = (
        state.player_behavior == "smart" and is_player_ranged_skirmisher(actor) and can_use_player_hide_bonus_action(actor)
    )

    for target in ranged_targets:
        ranged_plan = build_ranged_attack_plan(
            state,
            actor,
            target,
            ranged_weapon_id,
            move_squares,
            require_normal_range,
            False,
            prefer_distance_from_faction,
            True,
            prefer_hide_positions,
            position_index,
        )
        if not ranged_plan:
            continue

        pre_action_movement = MovementPlan(path=ranged_plan.path, mode="move") if len(ranged_plan.path) > 1 else None
        attack_position = ranged_plan.path[-1] if ranged_plan.path else actor.position
        post_action_movement = (
            build_post_action_retreat(
                state,
                actor,
                attack_position,
                move_squares - get_movement_distance(pre_action_movement),
            )
            if attack_position and is_player_ranged_skirmisher(actor)
            else build_post_action_advance(
                state,
                actor,
                ranged_plan.target_id,
                attack_position,
                move_squares - get_movement_distance(pre_action_movement),
            )
            if attack_position
            else None
        )

        return TurnDecision(
            bonus_action=bonus_action,
            pre_action_movement=pre_action_movement,
            post_action_movement=post_action_movement,
            action={"kind": "attack", "target_id": ranged_plan.target_id, "weapon_id": ranged_weapon_id},
        )

    return None


def build_player_spell_attack_decision(
    state: EncounterState,
    actor: UnitState,
    conscious_enemies: list[UnitState],
    spell_id: str,
    move_squares: int,
    position_index: PositionIndex | None,
) -> TurnDecision | None:
    ranged_targets = sort_player_ranged_targets(
        state,
        actor,
        conscious_enemies,
        state.player_behavior,
        attack_profile=build_spell_attack_profile(actor, spell_id),
        position_index=position_index,
    )

    for target in ranged_targets:
        spell_plan = build_spell_attack_plan(
            state,
            actor,
            target,
            spell_id,
            move_squares,
            position_index,
        )
        if not spell_plan:
            continue

        pre_action_movement = MovementPlan(path=spell_plan.path, mode="move") if len(spell_plan.path) > 1 else None
        attack_position = spell_plan.path[-1] if spell_plan.path else actor.position
        post_action_movement = (
            build_post_action_retreat(
                state,
                actor,
                attack_position,
                move_squares - get_movement_distance(pre_action_movement),
            )
            if attack_position
            else None
        )

        return TurnDecision(
            pre_action_movement=pre_action_movement,
            post_action_movement=post_action_movement,
            action={"kind": "cast_spell", "spell_id": spell_id, "target_id": spell_plan.target_id},
        )

    return None


def build_burning_hands_decision(
    state: EncounterState,
    actor: UnitState,
    move_squares: int,
    position_index: PositionIndex | None,
) -> TurnDecision | None:
    if not actor.position or not can_cast_combat_spell(actor, "burning_hands"):
        return None

    candidate_squares = (
        get_safe_reachable_squares(state, actor.id, move_squares, False, position_index)
        if state.player_behavior == "smart"
        else [ReachableSquare(position=actor.position, path=[actor.position], distance=0)]
    )
    candidate_options: list[tuple[ReachableSquare, object]] = []

    for square in candidate_squares:
        targeting = choose_burning_hands_targeting(
            state,
            actor.id,
            actor_position=square.position,
        )
        if not targeting:
            continue
        if len(targeting.enemy_target_ids) < 2 or len(targeting.ally_target_ids) > 0:
            continue
        candidate_options.append((square, targeting))

    if not candidate_options:
        return None

    best_square, best_targeting = sorted(
        candidate_options,
        key=lambda item: (
            -len(item[1].enemy_target_ids),
            item[0].distance,
            sum(state.units[target_id].current_hp for target_id in item[1].enemy_target_ids),
            item[0].position.x,
            item[0].position.y,
            item[1].primary_target_id,
        ),
    )[0]

    return TurnDecision(
        pre_action_movement=MovementPlan(path=best_square.path, mode="move") if best_square.distance > 0 else None,
        action={"kind": "cast_spell", "spell_id": "burning_hands", "target_id": best_targeting.primary_target_id},
    )


def build_shocking_grasp_decision(
    state: EncounterState,
    actor: UnitState,
    conscious_enemies: list[UnitState],
    move_squares: int,
) -> TurnDecision | None:
    if not actor.position or not can_cast_combat_spell(actor, "shocking_grasp"):
        return None

    adjacent_threats = [
        target
        for target in sort_player_melee_targets(
            state,
            actor,
            conscious_enemies,
            state.player_behavior,
            attack_profile=build_spell_attack_profile(actor, "shocking_grasp"),
            position_index=build_position_index(state),
        )
        if target.position and get_distance_between_units(actor, target) <= 1 and unit_can_take_reactions(target)
    ]
    if not adjacent_threats:
        return None

    if state.player_behavior == "dumb":
        return TurnDecision(action={"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": adjacent_threats[0].id})

    if len(adjacent_threats) != 1:
        return None

    target = adjacent_threats[0]
    projected_state = state.model_copy(deep=True)
    projected_actor = projected_state.units[actor.id]
    projected_target = projected_state.units[target.id]
    projected_target.temporary_effects = [
        effect
        for effect in projected_target.temporary_effects
        if not (effect.kind == "no_reactions" and effect.source_id == actor.id)
    ]
    projected_target.temporary_effects.append(
        NoReactionsEffect(kind="no_reactions", source_id=actor.id, expires_at_turn_start_of=target.id)
    )
    retreat_plan = build_post_action_retreat(projected_state, projected_actor, projected_actor.position, move_squares)
    if not retreat_plan:
        return None

    return TurnDecision(
        action={"kind": "cast_spell", "spell_id": "shocking_grasp", "target_id": target.id},
        post_action_movement=retreat_plan,
    )


def choose_magic_missile_target_id(state: EncounterState, actor: UnitState, conscious_enemies: list[UnitState]) -> str | None:
    if not actor.position or not can_cast_combat_spell(actor, "magic_missile"):
        return None

    magic_missile_profile = build_spell_attack_context_profile("magic_missile")
    fire_bolt_profile = build_spell_attack_context_profile("fire_bolt")
    prioritized_targets = sort_player_ranged_targets(
        state,
        actor,
        conscious_enemies,
        state.player_behavior,
        attack_profile=build_spell_attack_profile(actor, "fire_bolt"),
    )

    for target in prioritized_targets:
        if not target.position:
            continue
        magic_missile_context = get_attack_context(state, actor.id, target.id, magic_missile_profile)
        if not magic_missile_context.legal or not magic_missile_context.within_normal_range:
            continue

        obvious_finish = target.current_hp <= 6
        if state.player_behavior == "dumb":
            if obvious_finish:
                return target.id
            continue

        fire_bolt_context = get_attack_context(state, actor.id, target.id, fire_bolt_profile)
        avoids_bad_attack_roll = (
            "adjacent_enemy" in fire_bolt_context.disadvantage_sources or fire_bolt_context.cover_ac_bonus > 0
        )
        if obvious_finish or (avoids_bad_attack_roll and target.current_hp <= 10):
            return target.id

    return None


def get_player_wizard_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    move_squares = get_move_squares(actor, state)
    position_index = build_position_index(state)
    melee_weapon_id = get_player_primary_melee_weapon_id(actor)
    conscious_enemies = sort_player_combat_targets(
        state,
        actor,
        [unit for unit in get_units_by_faction(state, "goblins") if not unit.conditions.dead],
        state.player_behavior,
    )
    melee_targets = sort_player_melee_targets(
        state,
        actor,
        conscious_enemies,
        state.player_behavior,
        melee_weapon_id=melee_weapon_id,
        position_index=position_index,
    )
    has_adjacent_enemy = any(
        actor.position and target.position and get_distance_between_units(actor, target) <= 1 for target in conscious_enemies
    )

    shocking_grasp_decision = build_shocking_grasp_decision(state, actor, conscious_enemies, move_squares)
    if shocking_grasp_decision:
        return shocking_grasp_decision

    burning_hands_decision = build_burning_hands_decision(state, actor, move_squares, position_index)
    if burning_hands_decision:
        return burning_hands_decision

    magic_missile_target_id = choose_magic_missile_target_id(state, actor, conscious_enemies)
    if magic_missile_target_id:
        return TurnDecision(action={"kind": "cast_spell", "spell_id": "magic_missile", "target_id": magic_missile_target_id})

    fire_bolt_decision = (
        build_player_spell_attack_decision(state, actor, conscious_enemies, "fire_bolt", move_squares, position_index)
        if can_cast_combat_spell(actor, "fire_bolt")
        else None
    )

    if state.player_behavior == "smart" and has_adjacent_enemy and can_use_player_weapon(actor, melee_weapon_id):
        adjacent_targets = [
            target for target in melee_targets if actor.position and target.position and get_distance_between_units(actor, target) <= 1
        ]
        if adjacent_targets and not magic_missile_target_id:
            return TurnDecision(action={"kind": "attack", "target_id": adjacent_targets[0].id, "weapon_id": melee_weapon_id})

    if fire_bolt_decision:
        return fire_bolt_decision

    if can_use_player_weapon(actor, melee_weapon_id):
        for target in melee_targets:
            allow_provoking = can_intentionally_provoke_opportunity_attack(state, actor, target)
            melee_path = find_preferred_adjacent_square(
                state,
                actor.id,
                target.id,
                move_squares,
                allow_provoking,
                position_index,
            )
            if melee_path:
                return TurnDecision(
                    pre_action_movement=MovementPlan(path=melee_path.path, mode="move") if melee_path.distance > 0 else None,
                    action={"kind": "attack", "target_id": target.id, "weapon_id": melee_weapon_id},
                )

    nearest_target = melee_targets[0] if melee_targets else None
    if not nearest_target:
        return TurnDecision(action={"kind": "skip", "reason": "No enemies remain."})

    return TurnDecision(action={"kind": "skip", "reason": f"No legal spell or melee line remains against {nearest_target.id}."})


def get_planned_attack_position(actor: UnitState, decision: TurnDecision) -> GridPosition | None:
    if decision.pre_action_movement and decision.pre_action_movement.path:
        return decision.pre_action_movement.path[-1]
    return actor.position


def sort_monk_bonus_strike_targets(
    state: EncounterState,
    actor: UnitState,
    targets: list[UnitState],
) -> list[UnitState]:
    if state.player_behavior == "dumb":
        return sorted(targets, key=lambda unit: (unit.current_hp, unit.id))

    return sorted(
        targets,
        key=lambda unit: (
            unit.current_hp,
            -count_adjacent_allied_units(state, actor, unit),
            unit.id,
        ),
    )


def get_monk_bonus_strike_target_id(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
) -> str | None:
    attack_position = get_planned_attack_position(actor, decision)
    if not attack_position:
        return None

    adjacent_targets = [
        unit
        for unit in get_units_by_faction(state, "goblins")
        if is_unit_conscious(unit)
        and unit.position
        and get_min_chebyshev_distance_between_footprints(
            attack_position,
            get_unit_footprint(actor),
            unit.position,
            get_unit_footprint(unit),
        )
        <= 1
    ]
    if not adjacent_targets:
        return None

    preferred_target_id = decision.action.get("target_id")
    preferred_target = next((unit for unit in adjacent_targets if unit.id == preferred_target_id), None)
    if preferred_target and state.player_behavior == "dumb":
        return preferred_target.id

    ranked_targets = sort_monk_bonus_strike_targets(state, actor, adjacent_targets)
    if not ranked_targets:
        return None

    if preferred_target and ranked_targets[0].current_hp >= preferred_target.current_hp:
        return preferred_target.id

    return ranked_targets[0].id


def get_average_weapon_damage(actor: UnitState, weapon_id: str) -> float:
    weapon = actor.attacks.get(weapon_id)
    if not weapon:
        return 0.0
    return float(sum(spec.count * (spec.sides + 1) / 2 for spec in weapon.damage_dice) + weapon.damage_modifier)


def get_adjacent_conscious_enemies_at_position(
    state: EncounterState,
    actor: UnitState,
    position: GridPosition | None,
) -> list[UnitState]:
    if not position:
        return []

    enemy_faction = "goblins" if actor.faction == "fighters" else "fighters"
    actor_footprint = get_unit_footprint(actor)
    return [
        unit
        for unit in get_units_by_faction(state, enemy_faction)
        if is_unit_conscious(unit)
        and unit.position
        and get_min_chebyshev_distance_between_footprints(
            position,
            actor_footprint,
            unit.position,
            get_unit_footprint(unit),
        )
        <= 1
    ]


def should_use_monk_patient_defense(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
) -> bool:
    if (
        not is_player_monk(actor)
        or state.player_behavior != "smart"
        or decision.bonus_action
        or not can_use_monk_focus_bonus_action(actor, "patient_defense")
        or get_hp_ratio(actor) > 0.5
    ):
        return False

    attack_position = get_planned_attack_position(actor, decision)
    threatened_enemies = get_adjacent_conscious_enemies_at_position(state, actor, attack_position)
    if not threatened_enemies:
        return False

    if decision.action["kind"] != "attack":
        return True

    if len(threatened_enemies) >= 2:
        return True

    bonus_strike_damage = get_average_weapon_damage(actor, "unarmed_strike")
    target = state.units.get(decision.action.get("target_id", ""))
    return bool(target and target.current_hp > bonus_strike_damage)


def should_use_monk_flurry_of_blows(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    target_id: str,
) -> bool:
    if (
        not is_player_monk(actor)
        or state.player_behavior != "smart"
        or decision.action["kind"] != "attack"
        or not can_use_monk_focus_bonus_action(actor, "flurry_of_blows")
    ):
        return False

    attack_weapon_id = decision.action.get("weapon_id", "")
    attack_weapon = actor.attacks.get(attack_weapon_id)
    target = state.units.get(target_id)
    if not attack_weapon or attack_weapon.kind != "melee" or not target or not is_unit_conscious(target):
        return False

    free_turn_damage = get_average_weapon_damage(actor, attack_weapon_id) + get_average_weapon_damage(actor, "unarmed_strike")
    flurry_turn_damage = free_turn_damage + get_average_weapon_damage(actor, "unarmed_strike")
    return free_turn_damage < target.current_hp <= flurry_turn_damage


def build_player_disengage_ranged_attack_decision(
    state: EncounterState,
    actor: UnitState,
    conscious_enemies: list[UnitState],
    ranged_weapon_id: str,
    move_squares: int,
    position_index: PositionIndex | None,
) -> TurnDecision | None:
    if not can_use_player_disengage_bonus_action(actor):
        return None

    ranged_targets = sort_player_ranged_targets(
        state,
        actor,
        conscious_enemies,
        state.player_behavior,
        ranged_weapon_id=ranged_weapon_id,
        position_index=position_index,
    )
    prefer_distance_from_faction = "goblins" if is_player_ranged_skirmisher(actor) else None

    for require_normal_range in (True, False):
        for target in ranged_targets:
            ranged_plan = build_ranged_attack_plan(
                state,
                actor,
                target,
                ranged_weapon_id,
                move_squares,
                require_normal_range,
                True,
                prefer_distance_from_faction,
                False,
                False,
                position_index,
            )
            if not ranged_plan or len(ranged_plan.path) <= 1:
                continue

            return TurnDecision(
                bonus_action={"kind": "disengage", "timing": "before_action"},
                pre_action_movement=MovementPlan(path=ranged_plan.path, mode="move"),
                action={"kind": "attack", "target_id": ranged_plan.target_id, "weapon_id": ranged_weapon_id},
            )

    return None


def build_player_bonus_dash_ranged_attack_decision(
    state: EncounterState,
    actor: UnitState,
    conscious_enemies: list[UnitState],
    ranged_weapon_id: str,
    move_squares: int,
    dash_squares: int,
    position_index: PositionIndex | None,
) -> TurnDecision | None:
    if not can_use_player_bonus_dash(actor):
        return None

    ranged_targets = sort_player_ranged_targets(
        state,
        actor,
        conscious_enemies,
        state.player_behavior,
        ranged_weapon_id=ranged_weapon_id,
        position_index=position_index,
    )
    prefer_distance_from_faction = "goblins" if is_player_ranged_skirmisher(actor) else None
    prefer_hide_positions = (
        state.player_behavior == "smart" and is_player_ranged_skirmisher(actor) and can_use_player_hide_bonus_action(actor)
    )

    for require_normal_range in (True, False):
        for target in ranged_targets:
            ranged_plan = build_ranged_attack_plan(
                state,
                actor,
                target,
                ranged_weapon_id,
                dash_squares,
                require_normal_range,
                True,
                prefer_distance_from_faction,
                True,
                prefer_hide_positions,
                position_index,
            )
            if not ranged_plan or len(ranged_plan.path) <= 1:
                continue

            return TurnDecision(
                bonus_action={"kind": "bonus_dash", "timing": "before_action"},
                pre_action_movement=MovementPlan(
                    path=ranged_plan.path,
                    mode="dash" if len(ranged_plan.path) - 1 > move_squares else "move",
                ),
                action={"kind": "attack", "target_id": ranged_plan.target_id, "weapon_id": ranged_weapon_id},
            )

    return None


def build_player_bonus_dash_melee_attack_decision(
    state: EncounterState,
    actor: UnitState,
    melee_targets: list[UnitState],
    melee_weapon_id: str,
    move_squares: int,
    dash_squares: int,
    position_index: PositionIndex | None,
) -> TurnDecision | None:
    if not can_use_player_bonus_dash(actor):
        return None

    melee_option = (
        get_smart_melee_attack_option(state, actor, melee_targets, dash_squares, melee_weapon_id, position_index)
        if state.player_behavior == "smart"
        else None
    )

    if melee_option is None:
        for target in melee_targets:
            allow_provoking = can_intentionally_provoke_opportunity_attack(state, actor, target)
            candidate = find_preferred_adjacent_square(
                state,
                actor.id,
                target.id,
                dash_squares,
                allow_provoking,
                position_index,
            )
            if candidate:
                melee_option = MeleeAttackOption(
                    target=target,
                    path=candidate.path,
                    distance=candidate.distance,
                    creates_flank=False,
                    adjacent_allies=count_adjacent_allied_units(state, actor, target),
                )
                break

    if not melee_option or melee_option.distance <= move_squares:
        return None

    return TurnDecision(
        bonus_action={"kind": "bonus_dash", "timing": "before_action"},
        pre_action_movement=MovementPlan(path=melee_option.path, mode="dash"),
        action={"kind": "attack", "target_id": melee_option.target.id, "weapon_id": melee_weapon_id},
    )


def build_monk_dash_bonus_unarmed_strike_decision(
    state: EncounterState,
    actor: UnitState,
    melee_targets: list[UnitState],
    move_squares: int,
    dash_squares: int,
    position_index: PositionIndex | None = None,
) -> TurnDecision | None:
    if not is_player_monk(actor) or state.player_behavior != "smart" or not can_use_player_bonus_unarmed_strike(actor):
        return None

    unarmed_weapon_id = "unarmed_strike"
    melee_option = get_smart_melee_attack_option(
        state,
        actor,
        melee_targets,
        dash_squares,
        unarmed_weapon_id,
        position_index,
    )
    if not melee_option or melee_option.distance <= move_squares:
        return None

    return TurnDecision(
        bonus_action={"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": melee_option.target.id},
        pre_action_movement=MovementPlan(path=melee_option.path, mode="dash"),
        action={"kind": "dash", "reason": f"Dashing into range for a bonus unarmed strike against {melee_option.target.id}."},
    )


def build_monk_step_of_the_wind_attack_decision(
    state: EncounterState,
    actor: UnitState,
    melee_targets: list[UnitState],
    melee_weapon_id: str,
    move_squares: int,
    dash_squares: int,
    position_index: PositionIndex | None = None,
) -> TurnDecision | None:
    if (
        not is_player_monk(actor)
        or state.player_behavior != "smart"
        or not actor.position
        or get_hp_ratio(actor) > 0.5
        or not can_use_monk_focus_bonus_action(actor, "step_of_the_wind")
    ):
        return None

    enemy_faction = "goblins" if actor.faction == "fighters" else "fighters"
    threatening_units = [
        unit for unit in get_units_with_positions(state, enemy_faction, position_index) if is_unit_conscious(unit)
    ]
    if not any(get_distance_between_units(actor, target) <= 1 for target in threatening_units):
        return None

    expected_attack_damage = get_average_weapon_damage(actor, melee_weapon_id)
    candidate_options: list[MeleeAttackOption] = []
    for target in melee_targets:
        candidate = find_preferred_adjacent_square(
            state,
            actor.id,
            target.id,
            dash_squares,
            True,
            position_index,
        )
        if not candidate or candidate.distance <= move_squares or target.current_hp > expected_attack_damage:
            continue
        if not path_provokes_opportunity_attack(state, actor.id, candidate.path, position_index, threatening_units):
            continue
        candidate_options.append(
            MeleeAttackOption(
                target=target,
                path=candidate.path,
                distance=candidate.distance,
                creates_flank=False,
                adjacent_allies=count_adjacent_allied_units(state, actor, target),
            )
        )
    if not candidate_options:
        return None

    best_option = sorted(
        candidate_options,
        key=lambda option: (
            option.target.current_hp,
            option.distance,
            -option.adjacent_allies,
            option.target.id,
            option.path[-1].x,
            option.path[-1].y,
        ),
    )[0]

    return TurnDecision(
        bonus_action={"kind": "step_of_the_wind", "timing": "before_action"},
        pre_action_movement=MovementPlan(path=best_option.path, mode="dash"),
        action={"kind": "attack", "target_id": best_option.target.id, "weapon_id": melee_weapon_id},
    )


def apply_rogue_cunning_action(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
    position_index: PositionIndex | None = None,
) -> TurnDecision:
    if actor.class_id != "rogue" or decision.bonus_action or decision.action["kind"] != "attack" or unit_is_hidden(actor):
        return decision

    if not can_use_player_hide_bonus_action(actor):
        return decision

    weapon = actor.attacks.get(decision.action.get("weapon_id", ""))
    if not weapon or weapon.kind != "ranged":
        return decision

    attack_position = get_planned_attack_position(actor, decision)
    if not attack_position:
        return decision

    starts_in_hide_square = bool(
        actor.position and can_attempt_hide_from_position(state, actor.id, actor.position, position_index)
    )
    ends_in_hide_square = can_attempt_hide_from_position(state, actor.id, attack_position, position_index)

    if is_player_ranged_skirmisher(actor):
        if not decision.pre_action_movement and starts_in_hide_square:
            decision.bonus_action = {"kind": "hide", "timing": "before_action"}
            decision.post_action_movement = None
            return decision

        if ends_in_hide_square and (state.player_behavior == "smart" or not decision.pre_action_movement):
            decision.bonus_action = {"kind": "hide", "timing": "after_action"}
            decision.post_action_movement = None
            return decision

    if is_player_melee_opportunist(actor) and state.player_behavior == "smart" and ends_in_hide_square:
        decision.bonus_action = {"kind": "hide", "timing": "after_action"}
        decision.post_action_movement = None

    return decision


def apply_monk_martial_arts(
    state: EncounterState,
    actor: UnitState,
    decision: TurnDecision,
) -> TurnDecision:
    if not is_player_monk(actor) or decision.bonus_action:
        return decision

    if should_use_monk_patient_defense(state, actor, decision):
        decision.bonus_action = {"kind": "patient_defense", "timing": "after_action"}
        return decision

    if not can_use_player_bonus_unarmed_strike(actor):
        return decision

    if decision.action["kind"] != "attack":
        return decision

    attack_weapon = actor.attacks.get(decision.action.get("weapon_id", ""))
    if not attack_weapon or attack_weapon.kind != "melee":
        return decision

    target_id = get_monk_bonus_strike_target_id(state, actor, decision)
    if not target_id:
        return decision

    if should_use_monk_flurry_of_blows(state, actor, decision, target_id):
        decision.bonus_action = {"kind": "flurry_of_blows", "timing": "after_action", "target_id": target_id}
        return decision

    decision.bonus_action = {"kind": "bonus_unarmed_strike", "timing": "after_action", "target_id": target_id}
    return decision


def get_player_martial_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    if get_swallow_source_id(actor):
        return get_swallowed_player_decision(state, actor)

    if is_player_wizard(actor):
        return get_player_wizard_decision(state, actor)

    move_squares = get_move_squares(actor, state)
    dash_squares = get_total_move_squares(actor, 1, state=state)
    behavior = state.player_behavior
    position_index = build_position_index(state)
    melee_weapon_id = get_player_primary_melee_weapon_id(actor)
    ranged_weapon_id = get_player_primary_ranged_weapon_id(actor)
    bonus_action = get_player_bonus_action(actor)

    conscious_enemies = sort_player_combat_targets(
        state,
        actor,
        [unit for unit in get_units_by_faction(state, "goblins") if not unit.conditions.dead],
        behavior,
    )
    melee_targets = sort_player_melee_targets(
        state,
        actor,
        conscious_enemies,
        behavior,
        melee_weapon_id=melee_weapon_id,
        position_index=position_index,
    )
    has_adjacent_enemy = any(
        actor.position and target.position and get_distance_between_units(actor, target) <= 1 for target in conscious_enemies
    )
    prefer_ranged_first = is_player_ranged_skirmisher(actor) and not has_adjacent_enemy

    if is_player_ranged_skirmisher(actor) and has_adjacent_enemy and can_use_player_weapon(actor, ranged_weapon_id):
        disengage_ranged_decision = build_player_disengage_ranged_attack_decision(
            state,
            actor,
            conscious_enemies,
            ranged_weapon_id,
            move_squares,
            position_index,
        )
        if disengage_ranged_decision:
            return finalize_player_turn_decision(state, actor, disengage_ranged_decision, melee_weapon_id, position_index)

    if prefer_ranged_first and can_use_player_weapon(actor, ranged_weapon_id):
        normal_range_decision = build_player_ranged_attack_decision(
            state,
            actor,
            conscious_enemies,
            ranged_weapon_id,
            move_squares,
            True,
            position_index,
            bonus_action,
        )
        if normal_range_decision:
            return finalize_player_turn_decision(state, actor, normal_range_decision, melee_weapon_id, position_index)

        bonus_dash_ranged_decision = build_player_bonus_dash_ranged_attack_decision(
            state,
            actor,
            conscious_enemies,
            ranged_weapon_id,
            move_squares,
            dash_squares,
            position_index,
        )
        if bonus_dash_ranged_decision:
            return finalize_player_turn_decision(state, actor, bonus_dash_ranged_decision, melee_weapon_id, position_index)

    smart_melee_option = (
        get_smart_melee_attack_option(state, actor, melee_targets, move_squares, melee_weapon_id, position_index)
        if behavior == "smart"
        else None
    )
    monk_step_attack_decision = build_monk_step_of_the_wind_attack_decision(
        state,
        actor,
        melee_targets,
        melee_weapon_id,
        move_squares,
        dash_squares,
        position_index,
    )
    if monk_step_attack_decision:
        return finalize_player_turn_decision(state, actor, monk_step_attack_decision, melee_weapon_id, position_index)

    if smart_melee_option:
        if (
            is_player_melee_opportunist(actor)
            and has_adjacent_enemy
            and smart_melee_option.adjacent_allies == 0
            and can_use_player_weapon(actor, ranged_weapon_id)
        ):
            disengage_ranged_decision = build_player_disengage_ranged_attack_decision(
                state,
                actor,
                conscious_enemies,
                ranged_weapon_id,
                move_squares,
                position_index,
            )
            if disengage_ranged_decision:
                return finalize_player_turn_decision(
                    state,
                    actor,
                    disengage_ranged_decision,
                    melee_weapon_id,
                    position_index,
                )

        return finalize_player_turn_decision(
            state,
            actor,
            TurnDecision(
                bonus_action=bonus_action,
                pre_action_movement=MovementPlan(path=smart_melee_option.path, mode="move") if smart_melee_option.distance > 0 else None,
                action={"kind": "attack", "target_id": smart_melee_option.target.id, "weapon_id": melee_weapon_id},
            ),
            melee_weapon_id,
            position_index,
        )

    for target in melee_targets:
        allow_provoking = can_intentionally_provoke_opportunity_attack(state, actor, target)
        melee_path = find_preferred_adjacent_square(
            state,
            actor.id,
            target.id,
            move_squares,
            allow_provoking,
            position_index,
        )
        if melee_path:
            return finalize_player_turn_decision(
                state,
                actor,
                TurnDecision(
                    bonus_action=bonus_action,
                    pre_action_movement=MovementPlan(path=melee_path.path, mode="move") if melee_path.distance > 0 else None,
                    action={"kind": "attack", "target_id": target.id, "weapon_id": melee_weapon_id},
                ),
                melee_weapon_id,
                position_index,
            )

    monk_dash_bonus_decision = build_monk_dash_bonus_unarmed_strike_decision(
        state,
        actor,
        melee_targets,
        move_squares,
        dash_squares,
        position_index,
    )
    if monk_dash_bonus_decision:
        return finalize_player_turn_decision(state, actor, monk_dash_bonus_decision, melee_weapon_id, position_index)

    if is_player_melee_opportunist(actor) or is_player_monk(actor):
        bonus_dash_melee_decision = build_player_bonus_dash_melee_attack_decision(
            state,
            actor,
            melee_targets,
            melee_weapon_id,
            move_squares,
            dash_squares,
            position_index,
        )
        if bonus_dash_melee_decision:
            return finalize_player_turn_decision(state, actor, bonus_dash_melee_decision, melee_weapon_id, position_index)

    nearest_target = melee_targets[0] if melee_targets else None
    if not nearest_target:
        return TurnDecision(action={"kind": "skip", "reason": "No enemies remain."})

    if is_player_melee_opportunist(actor) and has_adjacent_enemy and can_use_player_weapon(actor, ranged_weapon_id):
        disengage_ranged_decision = build_player_disengage_ranged_attack_decision(
            state,
            actor,
            conscious_enemies,
            ranged_weapon_id,
            move_squares,
            position_index,
        )
        if disengage_ranged_decision:
            return finalize_player_turn_decision(state, actor, disengage_ranged_decision, melee_weapon_id, position_index)

    if is_player_melee_opportunist(actor) or is_player_barbarian(actor):
        dash_path = find_preferred_advance_path(
            state,
            actor.id,
            nearest_target.id,
            dash_squares,
            can_intentionally_provoke_opportunity_attack(state, actor, nearest_target),
            position_index,
        )
        if dash_path and dash_path.distance > 0:
            return finalize_player_turn_decision(
                state,
                actor,
                TurnDecision(
                    bonus_action=bonus_action,
                    post_action_movement=MovementPlan(path=dash_path.path, mode="dash"),
                    action={"kind": "dash", "reason": f"Dashing toward {nearest_target.id}."},
                ),
                melee_weapon_id,
                position_index,
            )

    fighter_action_surge_dash_attack = build_fighter_action_surge_dash_attack_decision(
        state,
        actor,
        melee_targets,
        melee_weapon_id,
        move_squares,
        dash_squares,
        position_index,
    )
    if fighter_action_surge_dash_attack:
        fighter_action_surge_dash_attack.bonus_action = bonus_action
        return fighter_action_surge_dash_attack

    if can_use_player_weapon(actor, ranged_weapon_id):
        # Fighters still treat ranged attacks as a fallback after checking for a
        # reachable melee line. Melee rogues reach this fallback only after they
        # fail to find a meaningful closing dash.
        normal_range_decision = build_player_ranged_attack_decision(
            state,
            actor,
            conscious_enemies,
            ranged_weapon_id,
            move_squares,
            True,
            position_index,
            bonus_action,
        )
        if normal_range_decision:
            return finalize_player_turn_decision(state, actor, normal_range_decision, melee_weapon_id, position_index)

    dash_path = find_preferred_advance_path(
        state,
        actor.id,
        nearest_target.id,
        dash_squares,
        can_intentionally_provoke_opportunity_attack(state, actor, nearest_target),
        position_index,
    )
    if dash_path and dash_path.distance > 0:
        return finalize_player_turn_decision(
            state,
            actor,
            TurnDecision(
                bonus_action=bonus_action,
                post_action_movement=MovementPlan(path=dash_path.path, mode="dash"),
                action={"kind": "dash", "reason": f"Dashing toward {nearest_target.id}."},
            ),
            melee_weapon_id,
            position_index,
        )

    if can_use_player_weapon(actor, ranged_weapon_id):
        long_range_decision = build_player_ranged_attack_decision(
            state,
            actor,
            conscious_enemies,
            ranged_weapon_id,
            move_squares,
            False,
            position_index,
            bonus_action,
        )
        if long_range_decision:
            return finalize_player_turn_decision(state, actor, long_range_decision, melee_weapon_id, position_index)

    return finalize_player_turn_decision(
        state,
        actor,
        TurnDecision(bonus_action=bonus_action, action={"kind": "skip", "reason": "No legal movement remains."}),
        melee_weapon_id,
        position_index,
    )


def get_enemy_melee_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    move_squares = get_move_squares(actor, state)
    dash_squares = get_total_move_squares(actor, 1, state=state)
    position_index = build_position_index(state)
    conscious_targets = get_conscious_fighter_targets(state)
    downed_targets = sort_downed_targets(state, actor, get_downed_fighter_targets(state))
    adjacent_downed_targets = sort_downed_targets(state, actor, get_adjacent_downed_fighters(state, actor))
    melee_weapon_id = get_enemy_melee_weapon_id(actor)

    if state.monster_behavior == "evil" and adjacent_downed_targets:
        return TurnDecision(action={"kind": "attack", "target_id": adjacent_downed_targets[0].id, "weapon_id": melee_weapon_id})

    kind_targets = sort_kind_targets(state, actor, conscious_targets)
    closest_targets = sort_closest_targets(state, actor, conscious_targets)
    balanced_targets = sort_balanced_monster_targets(state, actor, conscious_targets)
    evil_conscious_targets = sort_evil_conscious_targets(state, actor, conscious_targets)

    melee_option = None
    if state.monster_behavior == "kind":
        preferred_target = kind_targets[0] if kind_targets else None
        melee_option = (
            choose_closest_monster_melee_option(
                build_melee_attack_options(state, actor, [preferred_target], move_squares, melee_weapon_id, False, position_index)
            )
            if preferred_target
            else None
        )
        if not melee_option:
            melee_option = choose_closest_monster_melee_option(
                build_melee_attack_options(state, actor, closest_targets, move_squares, melee_weapon_id, False, position_index)
            )
    elif state.monster_behavior == "balanced":
        melee_option = choose_balanced_monster_melee_option(
            build_melee_attack_options(state, actor, balanced_targets, move_squares, melee_weapon_id, False, position_index)
        )
    else:
        melee_option = choose_evil_monster_melee_option(
            build_melee_attack_options(state, actor, evil_conscious_targets, move_squares, melee_weapon_id, True, position_index)
        )
        if not melee_option:
            melee_option = choose_closest_monster_melee_option(
                build_melee_attack_options(state, actor, downed_targets, move_squares, melee_weapon_id, True, position_index)
            )

    if melee_option:
        return TurnDecision(
            pre_action_movement=MovementPlan(path=melee_option.path, mode="move") if melee_option.distance > 0 else None,
            action={"kind": "attack", "target_id": melee_option.target.id, "weapon_id": melee_weapon_id},
        )

    dash_target = (
        ((kind_targets[0] if kind_targets else None) or (closest_targets[0] if closest_targets else None))
        if state.monster_behavior == "kind"
        else (balanced_targets[0] if balanced_targets else None)
        if state.monster_behavior == "balanced"
        else ((evil_conscious_targets[0] if evil_conscious_targets else None) or (downed_targets[0] if downed_targets else None))
    )

    if not dash_target:
        return TurnDecision(action={"kind": "skip", "reason": "No fighters remain."})

    # Aggressive is modeled as a reusable bonus-action movement grant. Orcs use
    # it to convert a turn that would otherwise be a plain dash into either:
    # 1. a longer move that still reaches melee for an attack, or
    # 2. a stronger closing dash when even that is not enough.
    if can_use_aggressive_bonus_movement(actor):
        aggressive_reach = get_total_move_squares(actor, 1, state=state)
        aggressive_option = None

        if state.monster_behavior == "kind":
            preferred_target = kind_targets[0] if kind_targets else None
            aggressive_option = (
                choose_closest_monster_melee_option(
                    build_melee_attack_options(
                        state,
                        actor,
                        [preferred_target],
                        aggressive_reach,
                        melee_weapon_id,
                        False,
                        position_index,
                    )
                )
                if preferred_target
                else None
            )
            if not aggressive_option:
                aggressive_option = choose_closest_monster_melee_option(
                    build_melee_attack_options(
                        state,
                        actor,
                        closest_targets,
                        aggressive_reach,
                        melee_weapon_id,
                        False,
                        position_index,
                    )
                )
        elif state.monster_behavior == "balanced":
            aggressive_option = choose_balanced_monster_melee_option(
                build_melee_attack_options(
                    state,
                    actor,
                    balanced_targets,
                    aggressive_reach,
                    melee_weapon_id,
                    False,
                    position_index,
                )
            )
        else:
            aggressive_option = choose_evil_monster_melee_option(
                build_melee_attack_options(
                    state,
                    actor,
                    evil_conscious_targets,
                    aggressive_reach,
                    melee_weapon_id,
                    True,
                    position_index,
                )
            )
            if not aggressive_option:
                aggressive_option = choose_closest_monster_melee_option(
                    build_melee_attack_options(
                        state,
                        actor,
                        downed_targets,
                        aggressive_reach,
                        melee_weapon_id,
                        True,
                        position_index,
                    )
                )

        if aggressive_option:
            return TurnDecision(
                bonus_action={"kind": "aggressive_dash", "timing": "before_action"},
                pre_action_movement=(
                    MovementPlan(
                        path=aggressive_option.path,
                        mode="dash" if aggressive_option.distance > move_squares else "move",
                    )
                    if aggressive_option.distance > 0
                    else None
                ),
                action={"kind": "attack", "target_id": aggressive_option.target.id, "weapon_id": melee_weapon_id},
            )

    dash_path = find_preferred_advance_path(
        state,
        actor.id,
        dash_target.id,
        get_total_move_squares(actor, 2, state=state) if can_use_aggressive_bonus_movement(actor) else dash_squares,
        can_intentionally_provoke_opportunity_attack(state, actor, dash_target),
        position_index,
    )
    if dash_path and dash_path.distance > 0:
        return TurnDecision(
            bonus_action={"kind": "aggressive_dash", "timing": "before_action"}
            if can_use_aggressive_bonus_movement(actor)
            else None,
            post_action_movement=MovementPlan(path=dash_path.path, mode="dash"),
            action={"kind": "dash", "reason": f"Dashing into melee against {dash_target.id}."},
        )

    return TurnDecision(action={"kind": "skip", "reason": "No legal movement remains."})


def get_swallow_predator_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    current_grappled_target = get_current_grappled_target(state, actor)
    if current_grappled_target and current_grappled_target.size_category in {"tiny", "small", "medium"}:
        return TurnDecision(
            action={"kind": "special_action", "action_id": "swallow", "target_id": current_grappled_target.id}
        )

    return get_enemy_melee_decision(state, actor)


def get_current_grappled_target(state: EncounterState, actor: UnitState) -> UnitState | None:
    active_grappled_target_ids = set(get_active_grappled_target_ids(state, actor.id))
    grappled_targets = get_ranked_attack_targets(state, actor)
    return next(
        (
            target
            for target in grappled_targets
            if target.id in active_grappled_target_ids and is_unit_conscious(target)
        ),
        None,
    )


def get_grappling_brute_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    current_grappled_target = get_current_grappled_target(state, actor)
    if current_grappled_target:
        melee_weapon_id = "light_hammer" if actor.attacks.get("light_hammer") else get_enemy_melee_weapon_id(actor)
        weapon = actor.attacks.get(melee_weapon_id)
        if weapon and get_attack_context(state, actor.id, current_grappled_target.id, weapon).legal:
            return TurnDecision(
                action={"kind": "attack", "target_id": current_grappled_target.id, "weapon_id": melee_weapon_id}
            )

    return get_enemy_melee_decision(state, actor)


def get_adjacent_conscious_fighters(state: EncounterState, actor: UnitState) -> list[UnitState]:
    return [
        unit
        for unit in get_units_by_faction(state, "fighters")
        if unit.position and actor.position and is_unit_conscious(unit) and get_distance_between_units(actor, unit) <= 1
    ]


def get_adjacent_downed_fighters(state: EncounterState, actor: UnitState) -> list[UnitState]:
    return [
        unit
        for unit in get_units_by_faction(state, "fighters")
        if unit.position and actor.position and is_unit_downed(unit) and get_distance_between_units(actor, unit) <= 1
    ]


def get_enemy_ranged_decision(state: EncounterState, actor: UnitState) -> TurnDecision:
    move_squares = get_move_squares(actor, state)
    dash_squares = get_total_move_squares(actor, 1, state=state)
    position_index = build_position_index(state)
    conscious_targets = get_conscious_fighter_targets(state)
    kind_targets = sort_kind_targets(state, actor, conscious_targets)
    closest_targets = sort_closest_targets(state, actor, conscious_targets)
    balanced_targets = sort_balanced_monster_targets(state, actor, conscious_targets)
    evil_conscious_targets = sort_evil_conscious_targets(state, actor, conscious_targets)
    downed_targets = sort_downed_targets(state, actor, get_downed_fighter_targets(state))
    adjacent_downed_targets = sort_downed_targets(state, actor, get_adjacent_downed_fighters(state, actor))
    melee_weapon_id = get_enemy_melee_weapon_id(actor)
    ranged_weapon_id = get_enemy_ranged_weapon_id(actor)
    prioritized_conscious_targets = (
        kind_targets if state.monster_behavior == "kind" else balanced_targets if state.monster_behavior == "balanced" else evil_conscious_targets
    )

    if state.monster_behavior == "evil" and adjacent_downed_targets:
        return TurnDecision(action={"kind": "attack", "target_id": adjacent_downed_targets[0].id, "weapon_id": melee_weapon_id})

    adjacent_conscious = get_adjacent_conscious_fighters(state, actor)
    if adjacent_conscious and unit_has_reaction(actor, "redirect_attack"):
        adjacent_target_ids = {unit.id for unit in adjacent_conscious}
        adjacent_prioritized_targets = [target for target in prioritized_conscious_targets if target.id in adjacent_target_ids]
        if adjacent_prioritized_targets:
            commit_to_melee(actor)
            return TurnDecision(
                action={"kind": "attack", "target_id": adjacent_prioritized_targets[0].id, "weapon_id": melee_weapon_id}
            )

    if adjacent_conscious and not can_use_disengage_bonus_action(actor):
        # Generic archers that cannot bonus-action Disengage stop trying to kite
        # once they have been pinned in melee. They switch to melee behavior for
        # the rest of the encounter.
        commit_to_melee(actor)
        return get_enemy_melee_decision(state, actor)

    if adjacent_conscious and prioritized_conscious_targets and can_use_disengage_bonus_action(actor):
        # Ranged enemies try to disengage into a clean shot instead of shooting in melee.
        bow_plan = (
            choose_kind_targeted_plan(
                kind_targets,
                closest_targets,
                lambda target: build_ranged_attack_plan(
                    state,
                    actor,
                    target,
                    ranged_weapon_id,
                    move_squares,
                    True,
                    True,
                    "fighters",
                    False,
                    position_index,
                ),
            )
            if state.monster_behavior == "kind"
            else choose_first_targeted_plan(
                prioritized_conscious_targets,
                lambda target: build_ranged_attack_plan(
                    state,
                    actor,
                    target,
                    ranged_weapon_id,
                    move_squares,
                    True,
                    True,
                    "fighters",
                    False,
                    position_index,
                ),
            )
        )

        if bow_plan:
            return TurnDecision(
                bonus_action={"kind": "disengage", "timing": "before_action"},
                pre_action_movement=MovementPlan(path=bow_plan.path, mode="move"),
                action={"kind": "attack", "target_id": bow_plan.target_id, "weapon_id": ranged_weapon_id},
            )

        retreat_target = (
            ((kind_targets[0] if kind_targets else None) or (closest_targets[0] if closest_targets else None))
            if state.monster_behavior == "kind"
            else (balanced_targets[0] if balanced_targets else None)
            if state.monster_behavior == "balanced"
            else ((evil_conscious_targets[0] if evil_conscious_targets else None) or (downed_targets[0] if downed_targets else None))
        )
        retreat_path = (
            find_preferred_advance_path(state, actor.id, retreat_target.id, move_squares, True, position_index)
            if retreat_target
            else None
        )

        return TurnDecision(
            bonus_action={"kind": "disengage", "timing": "before_action"},
            pre_action_movement=MovementPlan(path=retreat_path.path, mode="move") if retreat_path and retreat_path.distance > 0 else None,
            action={"kind": "skip", "reason": "Disengaging to find a future bow shot."},
        )

    if adjacent_conscious:
        adjacent_target_ids = {unit.id for unit in adjacent_conscious}
        adjacent_prioritized_targets = [target for target in prioritized_conscious_targets if target.id in adjacent_target_ids]
        if adjacent_prioritized_targets:
            return TurnDecision(
                action={"kind": "attack", "target_id": adjacent_prioritized_targets[0].id, "weapon_id": melee_weapon_id}
            )

    ranged_weapon = actor.attacks.get(ranged_weapon_id)

    def current_ranged_attack_plan(target: UnitState, require_normal_range: bool):
        if not ranged_weapon:
            return None
        context = get_attack_context(state, actor.id, target.id, ranged_weapon, position_index=position_index)
        if not context.legal:
            return None
        if require_normal_range and not context.within_normal_range:
            return None
        if not require_normal_range and not context.within_long_range:
            return None
        return {"target_id": target.id}

    current_normal_attack = (
        choose_kind_targeted_plan(kind_targets, closest_targets, lambda target: current_ranged_attack_plan(target, True))
        if state.monster_behavior == "kind"
        else choose_first_targeted_plan(prioritized_conscious_targets, lambda target: current_ranged_attack_plan(target, True))
    )

    if current_normal_attack:
        return TurnDecision(action={"kind": "attack", "target_id": current_normal_attack["target_id"], "weapon_id": ranged_weapon_id})

    move_and_shoot = (
        choose_kind_targeted_plan(
            kind_targets,
            closest_targets,
            lambda target: build_ranged_attack_plan(
                state,
                actor,
                target,
                ranged_weapon_id,
                move_squares,
                True,
                False,
                "fighters",
                not can_intentionally_provoke_opportunity_attack(state, actor, target),
                position_index,
            ),
        )
        if state.monster_behavior == "kind"
        else choose_first_targeted_plan(
            prioritized_conscious_targets,
            lambda target: build_ranged_attack_plan(
                state,
                actor,
                target,
                ranged_weapon_id,
                move_squares,
                True,
                False,
                "fighters",
                not can_intentionally_provoke_opportunity_attack(state, actor, target),
                position_index,
            ),
        )
    )

    if move_and_shoot and len(move_and_shoot.path) > 1:
        return TurnDecision(
            pre_action_movement=MovementPlan(path=move_and_shoot.path, mode="move"),
            action={"kind": "attack", "target_id": move_and_shoot.target_id, "weapon_id": ranged_weapon_id},
        )

    current_long_range_attack = (
        choose_kind_targeted_plan(kind_targets, closest_targets, lambda target: current_ranged_attack_plan(target, False))
        if state.monster_behavior == "kind"
        else choose_first_targeted_plan(prioritized_conscious_targets, lambda target: current_ranged_attack_plan(target, False))
    )

    if current_long_range_attack:
        return TurnDecision(action={"kind": "attack", "target_id": current_long_range_attack["target_id"], "weapon_id": ranged_weapon_id})

    if state.monster_behavior == "evil":
        downed_normal_attack = choose_first_targeted_plan(downed_targets, lambda target: current_ranged_attack_plan(target, True))
        if downed_normal_attack:
            return TurnDecision(action={"kind": "attack", "target_id": downed_normal_attack["target_id"], "weapon_id": ranged_weapon_id})

        downed_move_and_shoot = choose_first_targeted_plan(
            downed_targets,
            lambda target: build_ranged_attack_plan(
                state,
                actor,
                target,
                ranged_weapon_id,
                move_squares,
                True,
                False,
                "fighters",
                not can_intentionally_provoke_opportunity_attack(state, actor, target),
                position_index,
            ),
        )
        if downed_move_and_shoot and len(downed_move_and_shoot.path) > 1:
            return TurnDecision(
                pre_action_movement=MovementPlan(path=downed_move_and_shoot.path, mode="move"),
                action={"kind": "attack", "target_id": downed_move_and_shoot.target_id, "weapon_id": ranged_weapon_id},
            )

        downed_long_range_attack = choose_first_targeted_plan(downed_targets, lambda target: current_ranged_attack_plan(target, False))
        if downed_long_range_attack:
            return TurnDecision(action={"kind": "attack", "target_id": downed_long_range_attack["target_id"], "weapon_id": ranged_weapon_id})

    nearest_target = (
        ((kind_targets[0] if kind_targets else None) or (closest_targets[0] if closest_targets else None))
        if state.monster_behavior == "kind"
        else (balanced_targets[0] if balanced_targets else None)
        if state.monster_behavior == "balanced"
        else ((evil_conscious_targets[0] if evil_conscious_targets else None) or (downed_targets[0] if downed_targets else None))
    )

    if not nearest_target:
        return TurnDecision(action={"kind": "skip", "reason": "No fighters remain."})

    dash_path = find_preferred_advance_path(
        state,
        actor.id,
        nearest_target.id,
        dash_squares,
        can_intentionally_provoke_opportunity_attack(state, actor, nearest_target),
        position_index,
    )
    if dash_path and dash_path.distance > 0:
        return TurnDecision(
            post_action_movement=MovementPlan(path=dash_path.path, mode="dash"),
            action={"kind": "dash", "reason": f"Dashing to improve ranged position against {nearest_target.id}."},
        )

    return TurnDecision(action={"kind": "skip", "reason": "No legal movement remains."})


def choose_turn_decision(state: EncounterState, actor_id: str) -> TurnDecision:
    actor = state.units[actor_id]

    if actor.faction == "fighters":
        return get_player_martial_decision(state, actor)

    if get_monster_profile(actor).profile_id == "swallow_predator":
        return get_swallow_predator_decision(state, actor)

    if get_monster_profile(actor).profile_id == "grappling_brute":
        return get_grappling_brute_decision(state, actor)

    if uses_ranged_monster_ai(actor):
        if is_committed_to_melee(actor):
            return get_enemy_melee_decision(state, actor)
        return get_enemy_ranged_decision(state, actor)

    return get_enemy_melee_decision(state, actor)
