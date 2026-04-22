from __future__ import annotations

from dataclasses import dataclass

from backend.content.class_progressions import (
    get_monk_focus_points_max,
    get_monk_martial_arts_die_sides,
    get_progression_scalar,
)
from backend.content.enemies import unit_has_reaction, unit_has_trait
from backend.content.feature_definitions import unit_has_feature
from backend.content.spell_definitions import get_spell_definition
from backend.engine.models.state import (
    AttackId,
    AttackMode,
    AttackRiderType,
    CombatEvent,
    DamageCandidate,
    DamageComponentResult,
    DamageDetails,
    DodgingEffect,
    EncounterState,
    GridPosition,
    GrappledEffect,
    HarriedEffect,
    HiddenEffect,
    MasteryType,
    MovementDetails,
    NoReactionsEffect,
    RageEffect,
    RecklessAttackEffect,
    RestrainedEffect,
    SapEffect,
    ShieldEffect,
    SlowEffect,
    TemporaryEffect,
    UnitState,
    VexEffect,
    WeaponDamageComponent,
    WeaponProfile,
    WeaponRange,
)
from backend.engine.rules.spatial import (
    build_position_index,
    can_attempt_hide_from_position,
    find_advance_path,
    get_line_squares,
    get_attack_context,
    get_hide_passive_perception_dc,
    get_min_chebyshev_distance_between_footprints,
    get_occupied_squares_for_position,
    is_active_grapple,
    get_unit_footprint,
)
from backend.engine.utils.helpers import unit_can_take_reactions, unit_sort_key
from backend.engine.utils.rng import roll_die


class AttackRollOverrides:
    def __init__(
        self,
        *,
        attack_rolls: list[int] | None = None,
        damage_rolls: list[int] | None = None,
        save_rolls: list[int] | None = None,
        savage_damage_rolls: list[int] | None = None,
        advantage_damage_rolls: list[int] | None = None,
    ) -> None:
        self.attack_rolls = attack_rolls or []
        self.damage_rolls = damage_rolls or []
        self.save_rolls = save_rolls or []
        self.savage_damage_rolls = savage_damage_rolls or []
        self.advantage_damage_rolls = advantage_damage_rolls or []


@dataclass
class DamageApplicationResult:
    hp_delta: int
    condition_deltas: list[str]
    resisted_damage: int
    amplified_damage: int
    temporary_hp_absorbed: int
    final_damage_to_hp: int
    final_total_damage: int
    undead_fortitude_triggered: bool = False
    undead_fortitude_success: bool | None = None
    undead_fortitude_dc: int | None = None
    undead_fortitude_bypass_reason: str | None = None


class ResolveAttackArgs:
    def __init__(
        self,
        *,
        attacker_id: str,
        target_id: str,
        weapon_id: AttackId,
        savage_attacker_available: bool,
        movement_details: MovementDetails | None = None,
        is_opportunity_attack: bool | None = None,
        overrides: AttackRollOverrides | None = None,
        omit_ability_modifier_damage: bool = False,
    ) -> None:
        self.attacker_id = attacker_id
        self.target_id = target_id
        self.weapon_id = weapon_id
        self.savage_attacker_available = savage_attacker_available
        self.movement_details = movement_details
        self.is_opportunity_attack = is_opportunity_attack
        self.overrides = overrides
        self.omit_ability_modifier_damage = omit_ability_modifier_damage


class SavingThrowOverrides:
    def __init__(
        self,
        *,
        save_rolls: list[int] | None = None,
    ) -> None:
        self.save_rolls = save_rolls or []


class ResolveSavingThrowArgs:
    def __init__(
        self,
        *,
        actor_id: str,
        ability: str,
        dc: int,
        reason: str,
        advantage_sources: list[str] | None = None,
        disadvantage_sources: list[str] | None = None,
        overrides: SavingThrowOverrides | None = None,
    ) -> None:
        self.actor_id = actor_id
        self.ability = ability
        self.dc = dc
        self.reason = reason
        self.advantage_sources = advantage_sources or []
        self.disadvantage_sources = disadvantage_sources or []
        self.overrides = overrides


def event_base(state: EncounterState, actor_id: str) -> dict[str, int | str]:
    return {"round": state.round, "actor_id": actor_id}


def get_active_rage_effect(unit: UnitState) -> RageEffect | None:
    for effect in unit.temporary_effects:
        if effect.kind == "rage":
            return effect
    return None


def unit_is_raging(unit: UnitState) -> bool:
    return get_active_rage_effect(unit) is not None


def unit_has_reckless_attack_effect(unit: UnitState) -> bool:
    return any(effect.kind == "reckless_attack" for effect in unit.temporary_effects)


def unit_is_hidden(unit: UnitState) -> bool:
    return any(effect.kind == "hidden" for effect in unit.temporary_effects)


def unit_is_dodging(unit: UnitState) -> bool:
    return any(effect.kind == "dodging" for effect in unit.temporary_effects)


def end_hidden(unit: UnitState, *, reason: str | None = None) -> list[str]:
    if not unit_is_hidden(unit):
        return []

    unit.temporary_effects = [effect for effect in unit.temporary_effects if effect.kind != "hidden"]
    if reason:
        return [reason]
    return []


def end_rage(unit: UnitState, *, reason: str | None = None) -> list[str]:
    if not unit_is_raging(unit):
        return []

    unit.temporary_effects = [effect for effect in unit.temporary_effects if effect.kind != "rage"]
    if reason:
        return [reason]
    return []


def has_vex_effect(attacker: UnitState, target_id: str) -> bool:
    return any(effect.kind == "vex" and effect.target_id == target_id for effect in attacker.temporary_effects)


def consume_vex_effect(attacker: UnitState, target_id: str) -> bool:
    consumed = False
    remaining_effects: list[TemporaryEffect] = []

    for effect in attacker.temporary_effects:
        if not consumed and effect.kind == "vex" and effect.target_id == target_id:
            consumed = True
            continue
        remaining_effects.append(effect)

    attacker.temporary_effects = remaining_effects
    return consumed


def has_harried_effect(target: UnitState) -> bool:
    return any(effect.kind == "harried_by" for effect in target.temporary_effects)


def consume_harried_effect(target: UnitState) -> bool:
    consumed = False
    remaining_effects: list[TemporaryEffect] = []

    for effect in target.temporary_effects:
        if not consumed and effect.kind == "harried_by":
            consumed = True
            continue
        remaining_effects.append(effect)

    target.temporary_effects = remaining_effects
    return consumed


def clear_invalid_hidden_effects(state: EncounterState) -> list[str]:
    position_index = build_position_index(state)
    condition_deltas: list[str] = []

    for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id)):
        if not unit_is_hidden(unit):
            continue
        if can_attempt_hide_from_position(state, unit.id, unit.position, position_index):
            continue
        condition_deltas.extend(end_hidden(unit, reason=f"{unit.id} is no longer hidden."))

    return condition_deltas


def pull_die(state: EncounterState, sides: int, override: int | None = None) -> int:
    if override is not None:
        return override
    value, next_state = roll_die(state.rng_state, sides)
    state.rng_state = next_state
    return value


def get_ability_modifier(unit: UnitState, ability: str) -> int:
    ability_map = {
        "str": unit.ability_mods.str,
        "dex": unit.ability_mods.dex,
        "con": unit.ability_mods.con,
        "int": unit.ability_mods.int,
        "wis": unit.ability_mods.wis,
        "cha": unit.ability_mods.cha,
    }
    try:
        return ability_map[ability]
    except KeyError as error:
        raise ValueError(f"Unsupported ability '{ability}' for a saving throw.") from error


def unit_has_combat_spell(unit: UnitState, spell_id: str) -> bool:
    return spell_id in unit.combat_cantrip_ids or spell_id in unit.prepared_combat_spell_ids


def build_spell_attack_profile(attacker: UnitState, spell_id: str) -> WeaponProfile:
    spell = get_spell_definition(spell_id)
    spell_attack_bonus = 2 + get_ability_modifier(attacker, spell.attack_ability or "int")
    is_melee_spell = spell.targeting_mode == "melee_spell_attack"
    return WeaponProfile(
        id=spell_id,
        display_name=spell.display_name,
        attack_bonus=spell_attack_bonus,
        ability_modifier=0,
        damage_dice=list(spell.damage_dice),
        damage_modifier=spell.damage_modifier,
        damage_type=spell.damage_type,
        kind="melee" if is_melee_spell else "ranged",
        reach=spell.range_feet if is_melee_spell else None,
        range=None if is_melee_spell else WeaponRange(normal=spell.range_feet, long=spell.range_feet),
    )


def get_spell_save_dc(caster: UnitState, spell_id: str) -> int:
    spell = get_spell_definition(spell_id)
    return 8 + 2 + get_ability_modifier(caster, spell.attack_ability or "int")


def unit_has_no_reactions_effect(unit: UnitState) -> bool:
    return any(effect.kind == "no_reactions" for effect in unit.temporary_effects)


def unit_has_shield_effect(unit: UnitState) -> bool:
    return any(effect.kind == "shield" for effect in unit.temporary_effects)


def get_shield_ac_bonus(unit: UnitState) -> int:
    return sum(effect.ac_bonus for effect in unit.temporary_effects if effect.kind == "shield")


def has_danger_sense(unit: UnitState) -> bool:
    return (
        unit_has_feature(unit, "danger_sense")
        and unit.current_hp > 0
        and not unit.conditions.dead
        and not unit.conditions.unconscious
    )


def unit_is_bloodied(unit: UnitState) -> bool:
    return unit.max_hp > 0 and unit.current_hp > 0 and unit.current_hp <= unit.max_hp // 2


def apply_great_weapon_fighting(rolls: list[int]) -> list[int]:
    return [3 if roll <= 2 else roll for roll in rolls]


def get_base_weapon_damage_components(weapon: WeaponProfile):
    if weapon.damage_components:
        return weapon.damage_components
    return [
        WeaponDamageComponent(
            damage_type=weapon.damage_type or "damage",
            damage_dice=list(weapon.damage_dice),
            damage_modifier=weapon.damage_modifier,
        )
    ]


def weapon_qualifies_for_sneak_attack(weapon: WeaponProfile) -> bool:
    return weapon.kind == "ranged" or weapon.finesse is True


def get_sneak_attack_d6_count(attacker: UnitState) -> int:
    if not unit_has_feature(attacker, "sneak_attack"):
        return 0
    if not attacker.class_id or attacker.level is None:
        return 0
    return get_progression_scalar(attacker.class_id, attacker.level, "sneak_attack_d6", 0)


def has_adjacent_ally_for_sneak_attack(
    state: EncounterState,
    attacker: UnitState,
    target: UnitState,
) -> bool:
    if not target.position:
        return False

    for unit in state.units.values():
        if unit.id == attacker.id or unit.faction != attacker.faction:
            continue
        if unit.conditions.dead or unit.current_hp <= 0 or unit.conditions.unconscious or not unit.position:
            continue
        if (
            get_min_chebyshev_distance_between_footprints(
                unit.position,
                get_unit_footprint(unit),
                target.position,
                get_unit_footprint(target),
            )
            <= 1
        ):
            return True

    return False


def can_apply_sneak_attack(
    state: EncounterState,
    attacker: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    attack_mode: AttackMode,
) -> bool:
    if get_sneak_attack_d6_count(attacker) <= 0:
        return False
    if not weapon_qualifies_for_sneak_attack(weapon):
        return False
    if attack_mode == "advantage":
        return True
    if attack_mode == "disadvantage":
        return False
    return has_adjacent_ally_for_sneak_attack(state, attacker, target)


def get_rage_damage_bonus(attacker: UnitState, weapon: WeaponProfile) -> int:
    if not unit_is_raging(attacker):
        return 0
    if weapon.attack_ability != "str":
        return 0
    if not attacker.class_id or attacker.level is None:
        return 0
    return get_progression_scalar(attacker.class_id, attacker.level, "rage_damage_bonus", 0)


def get_monk_focus_points_max_for_unit(unit: UnitState) -> int:
    if unit.class_id != "monk" or unit.level is None:
        return unit.resource_pools.get("focus_points", 0)
    return get_monk_focus_points_max(unit.level)


def get_monk_martial_arts_die_sides_for_unit(unit: UnitState) -> int:
    if unit.class_id != "monk" or unit.level is None:
        return 6
    return get_monk_martial_arts_die_sides(unit.level)


def roll_sneak_attack_component(
    state: EncounterState,
    dice_count: int,
    override_rolls: list[int] | None = None,
) -> DamageComponentResult | None:
    if dice_count <= 0:
        return None

    raw_rolls: list[int] = []
    override_queue = list(override_rolls or [])

    for _ in range(dice_count):
        raw_rolls.append(pull_die(state, 6, override_queue.pop(0) if override_queue else None))

    return DamageComponentResult(
        damage_type="precision",
        raw_rolls=raw_rolls,
        adjusted_rolls=list(raw_rolls),
        subtotal=sum(raw_rolls),
        flat_modifier=0,
        total_damage=sum(raw_rolls),
    )


def roll_damage_candidate(
    state: EncounterState,
    weapon: WeaponProfile,
    override_rolls: list[int] | None = None,
    apply_gwf: bool = False,
    omit_ability_modifier_damage: bool = False,
) -> DamageCandidate:
    raw_rolls: list[int] = []
    adjusted_rolls: list[int] = []
    component_results: list[DamageComponentResult] = []
    override_queue = list(override_rolls or [])

    for component in get_base_weapon_damage_components(weapon):
        component_raw_rolls: list[int] = []
        flat_modifier = 0 if omit_ability_modifier_damage else component.damage_modifier

        for spec in component.damage_dice:
            for _ in range(spec.count):
                component_raw_rolls.append(pull_die(state, spec.sides, override_queue.pop(0) if override_queue else None))

        component_adjusted_rolls = apply_great_weapon_fighting(component_raw_rolls) if apply_gwf else list(component_raw_rolls)
        component_subtotal = sum(component_adjusted_rolls)
        raw_rolls.extend(component_raw_rolls)
        adjusted_rolls.extend(component_adjusted_rolls)
        component_results.append(
            DamageComponentResult(
                damage_type=component.damage_type,
                raw_rolls=component_raw_rolls,
                adjusted_rolls=component_adjusted_rolls,
                subtotal=component_subtotal,
                flat_modifier=flat_modifier,
                total_damage=component_subtotal + flat_modifier,
            )
        )

    return DamageCandidate(
        components=component_results,
        raw_rolls=raw_rolls,
        adjusted_rolls=adjusted_rolls,
        subtotal=sum(adjusted_rolls),
    )


def roll_bonus_candidate(
    state: EncounterState,
    weapon: WeaponProfile,
    override_rolls: list[int] | None = None,
) -> DamageCandidate | None:
    if not weapon.advantage_damage_dice and not weapon.advantage_damage_components:
        return None

    raw_rolls: list[int] = []
    adjusted_rolls: list[int] = []
    component_results: list[DamageComponentResult] = []
    override_queue = list(override_rolls or [])

    if weapon.advantage_damage_dice:
        bonus_raw_rolls: list[int] = []
        for spec in weapon.advantage_damage_dice:
            for _ in range(spec.count):
                bonus_raw_rolls.append(pull_die(state, spec.sides, override_queue.pop(0) if override_queue else None))

        damage_type = weapon.damage_type or (
            weapon.damage_components[0].damage_type if weapon.damage_components else "damage"
        )
        raw_rolls.extend(bonus_raw_rolls)
        adjusted_rolls.extend(bonus_raw_rolls)
        component_results.append(
            DamageComponentResult(
                damage_type=damage_type,
                raw_rolls=list(bonus_raw_rolls),
                adjusted_rolls=list(bonus_raw_rolls),
                subtotal=sum(bonus_raw_rolls),
                flat_modifier=0,
                total_damage=sum(bonus_raw_rolls),
            )
        )

    for component in weapon.advantage_damage_components or []:
        component_raw_rolls: list[int] = []
        for spec in component.damage_dice:
            for _ in range(spec.count):
                component_raw_rolls.append(pull_die(state, spec.sides, override_queue.pop(0) if override_queue else None))

        component_subtotal = sum(component_raw_rolls)
        raw_rolls.extend(component_raw_rolls)
        adjusted_rolls.extend(component_raw_rolls)
        component_results.append(
            DamageComponentResult(
                damage_type=component.damage_type,
                raw_rolls=component_raw_rolls,
                adjusted_rolls=list(component_raw_rolls),
                subtotal=component_subtotal,
                flat_modifier=component.damage_modifier,
                total_damage=component_subtotal + component.damage_modifier,
            )
        )

    return DamageCandidate(
        components=component_results,
        raw_rolls=raw_rolls,
        adjusted_rolls=adjusted_rolls,
        subtotal=sum(component.subtotal for component in component_results),
    )


def choose_damage_candidate(primary: DamageCandidate, savage: DamageCandidate | None) -> tuple[str, DamageCandidate]:
    if not savage:
        return "primary", primary
    if savage.subtotal > primary.subtotal:
        return "savage", savage
    return "primary", primary


def recalculate_effective_speed_for_unit(unit: UnitState) -> None:
    slow_penalty = sum(effect.penalty for effect in unit.temporary_effects if effect.kind == "slow")
    unit.effective_speed = max(0, unit.speed - min(10, slow_penalty))


def recalculate_effective_speed(unit: UnitState) -> UnitState:
    next_unit = unit.model_copy(deep=True)
    recalculate_effective_speed_for_unit(next_unit)
    return next_unit


def format_effect_kinds(effects: list[TemporaryEffect]) -> str:
    return ", ".join(sorted(effect.kind for effect in effects))


def expire_turn_effects(state: EncounterState, actor_id: str) -> list[CombatEvent]:
    events: list[CombatEvent] = []

    for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id)):
        expired = [
            effect
            for effect in unit.temporary_effects
            if getattr(effect, "expires_at_turn_start_of", None) == actor_id
        ]
        if not expired:
            continue

        unit.temporary_effects = [
            effect
            for effect in unit.temporary_effects
            if getattr(effect, "expires_at_turn_start_of", None) != actor_id
        ]
        recalculate_effective_speed_for_unit(unit)

        events.append(
            CombatEvent(
                **event_base(state, actor_id),
                target_ids=[unit.id],
                event_type="effect_expired",
                raw_rolls={},
                resolved_totals={"expiredCount": len(expired), "unitId": unit.id},
                movement_details=None,
                damage_details=None,
                condition_deltas=[f"Expired {format_effect_kinds(expired)} on {unit.id}."],
                text_summary=f"{format_effect_kinds(expired)} expire on {unit.id} at the start of {actor_id}'s turn.",
            )
        )

    return events


def get_saving_throw_mode(
    actor: UnitState,
    ability: str,
    base_advantage_sources: list[str] | None = None,
    base_disadvantage_sources: list[str] | None = None,
) -> tuple[AttackMode, list[str], list[str]]:
    advantage_sources = list(base_advantage_sources or [])
    disadvantage_sources = list(base_disadvantage_sources or [])

    if ability == "dex" and has_danger_sense(actor):
        advantage_sources.append("danger_sense")

    if actor.faction == "goblins" and unit_has_trait(actor, "bloodied_frenzy") and unit_is_bloodied(actor):
        advantage_sources.append("bloodied_frenzy")

    if advantage_sources and disadvantage_sources:
        return "normal", advantage_sources, disadvantage_sources
    if advantage_sources:
        return "advantage", advantage_sources, disadvantage_sources
    if disadvantage_sources:
        return "disadvantage", advantage_sources, disadvantage_sources
    return "normal", advantage_sources, disadvantage_sources


def resolve_saving_throw(state: EncounterState, args: ResolveSavingThrowArgs) -> CombatEvent:
    actor = state.units[args.actor_id]
    overrides = SavingThrowOverrides(save_rolls=list(args.overrides.save_rolls if args.overrides else []))
    mode, advantage_sources, disadvantage_sources = get_saving_throw_mode(
        actor,
        args.ability,
        args.advantage_sources,
        args.disadvantage_sources,
    )

    if mode == "normal":
        save_rolls = [pull_die(state, 20, overrides.save_rolls.pop(0) if overrides.save_rolls else None)]
    else:
        save_rolls = [
            pull_die(state, 20, overrides.save_rolls.pop(0) if overrides.save_rolls else None),
            pull_die(state, 20, overrides.save_rolls.pop(0) if overrides.save_rolls else None),
        ]

    if mode == "advantage":
        selected_roll = max(save_rolls)
    elif mode == "disadvantage":
        selected_roll = min(save_rolls)
    else:
        selected_roll = save_rolls[0]

    modifier = get_ability_modifier(actor, args.ability)
    total = selected_roll + modifier
    success = total >= args.dc

    return CombatEvent(
        **event_base(state, args.actor_id),
        target_ids=[args.actor_id],
        event_type="saving_throw",
        raw_rolls={
            "savingThrowRolls": save_rolls,
            "advantageSources": advantage_sources,
            "disadvantageSources": disadvantage_sources,
        },
        resolved_totals={
            "ability": args.ability,
            "saveMode": mode,
            "selectedRoll": selected_roll,
            "modifier": modifier,
            "total": total,
            "dc": args.dc,
            "success": success,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[],
        text_summary=(
            f"{args.actor_id} makes a {args.ability.upper()} save for {args.reason}: "
            f"{'success' if success else 'failure'} with {total} against DC {args.dc}."
        ),
    )


def resolve_death_save(state: EncounterState, actor_id: str, override_roll: int | None = None) -> CombatEvent:
    actor = state.units[actor_id]
    raw_roll = pull_die(state, 20, override_roll)
    outcome = "success"

    # Death saves are ordered to match the tabletop branches and the TS oracle:
    # nat 1, failure, nat 20, then normal success.
    if raw_roll == 1:
        actor.death_save_failures += 2
        outcome = "critical_failure"
    elif raw_roll < 10:
        actor.death_save_failures += 1
        outcome = "failure"
    elif raw_roll == 20:
        actor.current_hp = 1
        actor.conditions.unconscious = False
        actor.conditions.prone = False
        actor.stable = False
        actor.death_save_failures = 0
        actor.death_save_successes = 0
        outcome = "critical_success"
    else:
        actor.death_save_successes += 1

    condition_deltas: list[str] = []

    if actor.death_save_failures >= 3:
        actor.conditions.dead = True
        actor.conditions.unconscious = False
        actor.conditions.prone = False
        condition_deltas.append(f"{actor_id} dies after three failed death saves.")
        outcome = "dead"
    elif actor.death_save_successes >= 3 and actor.current_hp == 0:
        actor.stable = True
        actor.conditions.unconscious = True
        actor.conditions.prone = True
        condition_deltas.append(f"{actor_id} stabilizes at 0 HP.")
        outcome = "stable"
    elif outcome == "critical_success":
        condition_deltas.append(f"{actor_id} regains 1 HP and returns to consciousness.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="death_save",
        raw_rolls={"deathSaveRolls": [raw_roll]},
        resolved_totals={
            "successes": actor.death_save_successes,
            "failures": actor.death_save_failures,
            "outcome": outcome,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=(
            f"{actor_id} rolls a natural 20 on a death save, regains 1 HP, and stands back up."
            if outcome == "critical_success"
            else f"{actor_id} makes a death save with {raw_roll}."
        ),
    )


def attempt_second_wind(state: EncounterState, actor_id: str, override_roll: int | None = None) -> CombatEvent | None:
    actor = state.units[actor_id]
    if not unit_has_feature(actor, "second_wind") or actor.resources.second_wind_uses <= 0 or actor.current_hp <= 0:
        return None

    raw_roll = pull_die(state, 10, override_roll)
    healed = min(actor.max_hp - actor.current_hp, raw_roll + 1)
    actor.current_hp += healed
    actor.resources.second_wind_uses -= 1

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="heal",
        raw_rolls={"healingRolls": [raw_roll]},
        resolved_totals={
            "healingTotal": healed,
            "currentHp": actor.current_hp,
            "secondWindUsesRemaining": actor.resources.second_wind_uses,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[],
        text_summary=f"{actor_id} uses Second Wind and regains {healed} HP.",
    )


def attempt_patient_defense(state: EncounterState, actor_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return create_skip_event(state, actor_id, "Cannot use Patient Defense while down.")
    if not unit_has_feature(actor, "monks_focus"):
        return create_skip_event(state, actor_id, "Patient Defense is not available.")
    if not actor.resources.spend_pool("focus_points", 1):
        return create_skip_event(state, actor_id, "No Focus Points remain.")

    actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "dodging"]
    actor.temporary_effects.append(
        DodgingEffect(kind="dodging", source_id=actor_id, expires_at_turn_start_of=actor_id)
    )

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "dodging": True,
            "disengageApplied": True,
            "focusPointsRemaining": actor.resources.focus_points,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[f"{actor_id} takes Patient Defense."],
        text_summary=f"{actor_id} spends 1 Focus Point on Patient Defense.",
    )


def attempt_step_of_the_wind(state: EncounterState, actor_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return create_skip_event(state, actor_id, "Cannot use Step of the Wind while down.")
    if not unit_has_feature(actor, "monks_focus"):
        return create_skip_event(state, actor_id, "Step of the Wind is not available.")
    if not actor.resources.spend_pool("focus_points", 1):
        return create_skip_event(state, actor_id, "No Focus Points remain.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "disengageApplied": True,
            "extraMovementMultiplier": 1,
            "focusPointsRemaining": actor.resources.focus_points,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[f"{actor_id} uses Step of the Wind."],
        text_summary=f"{actor_id} spends 1 Focus Point on Step of the Wind.",
    )


def attempt_uncanny_metabolism(state: EncounterState, actor_id: str) -> CombatEvent | None:
    actor = state.units[actor_id]
    if (
        actor.class_id != "monk"
        or actor.level is None
        or not unit_has_feature(actor, "uncanny_metabolism")
        or actor.resources.uncanny_metabolism_uses <= 0
        or actor.current_hp <= 0
        or actor.conditions.dead
        or actor.conditions.unconscious
    ):
        return None

    max_focus_points = get_monk_focus_points_max_for_unit(actor)
    if actor.current_hp >= actor.max_hp and actor.resources.focus_points >= max_focus_points:
        return None

    martial_arts_die_sides = get_monk_martial_arts_die_sides_for_unit(actor)
    raw_roll = pull_die(state, martial_arts_die_sides)
    healing_total = min(actor.max_hp - actor.current_hp, raw_roll + actor.level)
    actor.current_hp += healing_total
    actor.resources.focus_points = max_focus_points
    actor.resources.uncanny_metabolism_uses -= 1

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="heal",
        raw_rolls={"uncannyMetabolismRolls": [raw_roll]},
        resolved_totals={
            "healingTotal": healing_total,
            "currentHp": actor.current_hp,
            "focusPoints": actor.resources.focus_points,
            "focusPointsMax": max_focus_points,
            "uncannyMetabolismUsesRemaining": actor.resources.uncanny_metabolism_uses,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[],
        text_summary=f"{actor_id} uses Uncanny Metabolism, restoring Focus and regaining {healing_total} HP.",
    )


def attempt_hide(state: EncounterState, actor_id: str, override_roll: int | None = None) -> CombatEvent:
    actor = state.units[actor_id]
    position_index = build_position_index(state)

    if unit_is_hidden(actor):
        return create_skip_event(state, actor_id, "Already hidden.")

    if not can_attempt_hide_from_position(state, actor_id, actor.position, position_index):
        return create_skip_event(state, actor_id, "Cannot hide from the current position.")

    if not actor.position:
        return create_skip_event(state, actor_id, "Cannot hide without a position on the map.")

    target_dc = get_hide_passive_perception_dc(state, actor_id, actor.position, position_index)
    if target_dc is None:
        return create_skip_event(state, actor_id, "No enemy observers remain.")

    stealth_modifier = actor.combat_skill_modifiers.get("stealth", actor.ability_mods.dex)
    raw_roll = pull_die(state, 20, override_roll)
    total = raw_roll + stealth_modifier
    success = total >= target_dc
    condition_deltas: list[str] = []

    if success:
        actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "hidden"]
        actor.temporary_effects.append(
            HiddenEffect(kind="hidden", source_id=actor_id, expires_at_turn_start_of=actor_id)
        )
        condition_deltas.append(f"{actor_id} becomes hidden.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={"stealthRolls": [raw_roll]},
        resolved_totals={
            "stealthModifier": stealth_modifier,
            "total": total,
            "targetDc": target_dc,
            "success": success,
            "hidden": success,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=(
            f"{actor_id} hides with a Stealth check of {total}."
            if success
            else f"{actor_id} fails to hide with a Stealth check of {total} against DC {target_dc}."
        ),
    )


def attempt_stabilize(
    state: EncounterState,
    actor_id: str,
    target_id: str,
    override_roll: int | None = None,
) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units[target_id]
    raw_roll = pull_die(state, 20, override_roll)
    total = raw_roll + actor.medicine_modifier
    success = total >= 10

    if success:
        target.stable = True
        target.conditions.unconscious = True
        target.conditions.prone = True

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="stabilize",
        raw_rolls={"medicineRolls": [raw_roll]},
        resolved_totals={
            "medicineModifier": actor.medicine_modifier,
            "total": total,
            "success": success,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[f"{target_id} becomes stable."] if success else [],
        text_summary=(
            f"{actor_id} stabilizes {target_id} with a Medicine check of {total}."
            if success
            else f"{actor_id} fails to stabilize {target_id} with a Medicine check of {total}."
        ),
    )


def consume_sap_effects(actor: UnitState) -> int:
    sap_count = sum(1 for effect in actor.temporary_effects if effect.kind == "sap")
    if sap_count == 0:
        return 0
    actor.temporary_effects = [effect for effect in actor.temporary_effects if effect.kind != "sap"]
    return sap_count


def get_damage_defense_flags(target: UnitState, damage_type: str) -> tuple[bool, bool, bool]:
    damage_key = damage_type.lower()
    immune = damage_key in target.damage_immunities
    resistant = damage_key in target.damage_resistances
    vulnerable = damage_key in target.damage_vulnerabilities

    if unit_is_raging(target) and damage_key in {"bludgeoning", "piercing", "slashing"}:
        resistant = True

    return immune, resistant, vulnerable


def resolve_damage_component_against_target(
    target: UnitState,
    component: DamageComponentResult,
) -> tuple[int, int, int]:
    if component.total_damage <= 0:
        return 0, 0, 0

    component_damage = component.total_damage
    immune, resistant, vulnerable = get_damage_defense_flags(target, component.damage_type)

    if immune:
        return 0, component_damage, 0
    if resistant and vulnerable:
        return component_damage, 0, 0
    if resistant:
        reduced_damage = component_damage // 2
        return reduced_damage, component_damage - reduced_damage, 0
    if vulnerable:
        amplified_damage = component_damage * 2
        return amplified_damage, 0, amplified_damage - component_damage

    return component_damage, 0, 0


def resolve_undead_fortitude(
    state: EncounterState,
    target: UnitState,
    target_id: str,
    damage_components: list[DamageComponentResult],
    final_damage_to_hp: int,
    is_critical: bool,
) -> tuple[bool, bool | None, int | None, str | None]:
    if (
        target.faction != "goblins"
        or final_damage_to_hp <= 0
        or not unit_has_trait(target, "undead_fortitude")
    ):
        return False, None, None, None

    if any(component.damage_type == "radiant" and component.total_damage > 0 for component in damage_components):
        return True, None, None, "radiant"

    if is_critical:
        return True, None, None, "critical"

    save_dc = 5 + final_damage_to_hp
    save_total = pull_die(state, 20) + get_ability_modifier(target, "con")
    return True, save_total >= save_dc, save_dc, None


def apply_damage(
    state: EncounterState,
    target_id: str,
    damage_components: list[DamageComponentResult],
    is_critical: bool,
) -> DamageApplicationResult:
    target = state.units[target_id]
    previous_hp = target.current_hp
    condition_deltas: list[str] = []
    resisted_damage = 0
    amplified_damage = 0
    temporary_hp_absorbed = 0
    final_damage_to_hp = 0
    final_total_damage = 0
    undead_fortitude_triggered = False
    undead_fortitude_success: bool | None = None
    undead_fortitude_dc: int | None = None
    undead_fortitude_bypass_reason: str | None = None

    if target.conditions.dead:
        return DamageApplicationResult(
            hp_delta=0,
            condition_deltas=[],
            resisted_damage=0,
            amplified_damage=0,
            temporary_hp_absorbed=0,
            final_damage_to_hp=0,
            final_total_damage=0,
            undead_fortitude_triggered=False,
            undead_fortitude_success=None,
            undead_fortitude_dc=None,
            undead_fortitude_bypass_reason=None,
        )

    for component in damage_components:
        component_damage, component_resisted_damage, component_amplified_damage = resolve_damage_component_against_target(
            target,
            component,
        )
        resisted_damage += component_resisted_damage
        amplified_damage += component_amplified_damage
        final_total_damage += component_damage

    if final_total_damage <= 0:
        return DamageApplicationResult(
            hp_delta=0,
            condition_deltas=condition_deltas,
            resisted_damage=resisted_damage,
            amplified_damage=amplified_damage,
            temporary_hp_absorbed=0,
            final_damage_to_hp=0,
            final_total_damage=0,
            undead_fortitude_triggered=False,
            undead_fortitude_success=None,
            undead_fortitude_dc=None,
            undead_fortitude_bypass_reason=None,
        )

    condition_deltas.extend(end_hidden(target, reason=f"{target_id} is no longer hidden after taking damage."))

    if unit_is_raging(target):
        target._rage_qualified_since_turn_end = True

    # Damage at 0 HP is resolved before standard HP reduction because it advances death saves
    # or kills outright instead of changing current HP further.
    if target.current_hp == 0:
        target.stable = False

        temporary_hp_absorbed = min(target.temporary_hit_points, final_total_damage)
        if temporary_hp_absorbed > 0:
            target.temporary_hit_points -= temporary_hp_absorbed
        final_damage_to_hp = final_total_damage - temporary_hp_absorbed

        if final_damage_to_hp <= 0:
            return DamageApplicationResult(
                hp_delta=0,
                condition_deltas=condition_deltas,
                resisted_damage=resisted_damage,
                amplified_damage=amplified_damage,
                temporary_hp_absorbed=temporary_hp_absorbed,
                final_damage_to_hp=0,
                final_total_damage=final_total_damage,
                undead_fortitude_triggered=False,
                undead_fortitude_success=None,
                undead_fortitude_dc=None,
                undead_fortitude_bypass_reason=None,
            )

        if final_damage_to_hp >= target.max_hp:
            target.conditions.dead = True
            target.conditions.unconscious = False
            target.conditions.prone = False
            condition_deltas.append(f"{target_id} is killed outright while at 0 HP.")
            condition_deltas.extend(end_rage(target, reason=f"{target_id}'s rage ends."))
            return DamageApplicationResult(
                hp_delta=0,
                condition_deltas=condition_deltas,
                resisted_damage=resisted_damage,
                amplified_damage=amplified_damage,
                temporary_hp_absorbed=temporary_hp_absorbed,
                final_damage_to_hp=final_damage_to_hp,
                final_total_damage=final_total_damage,
                undead_fortitude_triggered=False,
                undead_fortitude_success=None,
                undead_fortitude_dc=None,
                undead_fortitude_bypass_reason=None,
            )

        target.death_save_failures += 2 if is_critical else 1
        condition_deltas.append(
            f"{target_id} suffers {2 if is_critical else 1} failed death save{'s' if is_critical else ''} from damage at 0 HP."
        )

        if target.death_save_failures >= 3:
            target.conditions.dead = True
            target.conditions.unconscious = False
            target.conditions.prone = False
            condition_deltas.append(f"{target_id} dies after taking damage at 0 HP.")
            condition_deltas.extend(end_rage(target, reason=f"{target_id}'s rage ends."))

        return DamageApplicationResult(
            hp_delta=0,
            condition_deltas=condition_deltas,
            resisted_damage=resisted_damage,
            amplified_damage=amplified_damage,
            temporary_hp_absorbed=temporary_hp_absorbed,
            final_damage_to_hp=final_damage_to_hp,
            final_total_damage=final_total_damage,
            undead_fortitude_triggered=False,
            undead_fortitude_success=None,
            undead_fortitude_dc=None,
            undead_fortitude_bypass_reason=None,
        )

    temporary_hp_absorbed = min(target.temporary_hit_points, final_total_damage)
    if temporary_hp_absorbed > 0:
        target.temporary_hit_points -= temporary_hp_absorbed
    final_damage_to_hp = final_total_damage - temporary_hp_absorbed

    if final_damage_to_hp <= 0:
        return DamageApplicationResult(
            hp_delta=0,
            condition_deltas=condition_deltas,
            resisted_damage=resisted_damage,
            amplified_damage=amplified_damage,
            temporary_hp_absorbed=temporary_hp_absorbed,
            final_damage_to_hp=0,
            final_total_damage=final_total_damage,
            undead_fortitude_triggered=False,
            undead_fortitude_success=None,
            undead_fortitude_dc=None,
            undead_fortitude_bypass_reason=None,
        )

    target.current_hp = max(0, target.current_hp - final_damage_to_hp)

    if target.faction == "goblins" and target.current_hp == 0:
        (
            undead_fortitude_triggered,
            undead_fortitude_success,
            undead_fortitude_dc,
            undead_fortitude_bypass_reason,
        ) = resolve_undead_fortitude(
            state,
            target,
            target_id,
            damage_components,
            final_damage_to_hp,
            is_critical,
        )

        if undead_fortitude_triggered and undead_fortitude_success is True:
            target.current_hp = 1
            condition_deltas.append(
                f"{target_id}'s Undead Fortitude succeeds (DC {undead_fortitude_dc}); it remains at 1 HP."
            )
        else:
            if undead_fortitude_bypass_reason == "radiant":
                condition_deltas.append(f"{target_id}'s Undead Fortitude is bypassed by radiant damage.")
            elif undead_fortitude_bypass_reason == "critical":
                condition_deltas.append(f"{target_id}'s Undead Fortitude is bypassed by a critical hit.")
            elif undead_fortitude_triggered and undead_fortitude_success is False:
                condition_deltas.append(
                    f"{target_id}'s Undead Fortitude fails against DC {undead_fortitude_dc}."
                )

            target.conditions.dead = True
            target.conditions.unconscious = False
            target.conditions.prone = False
            target.temporary_effects = []
            target.effective_speed = 0
            condition_deltas.append(f"{target_id} is removed from combat at 0 HP.")
    elif target.faction == "fighters" and target.current_hp == 0:
        overflow = final_damage_to_hp - previous_hp
        if overflow >= target.max_hp:
            target.conditions.dead = True
            target.conditions.unconscious = False
            target.conditions.prone = False
            condition_deltas.append(f"{target_id} dies from massive damage.")
            condition_deltas.extend(end_rage(target, reason=f"{target_id}'s rage ends."))
        else:
            target.stable = False
            target.conditions.unconscious = True
            target.conditions.prone = True
            target.death_save_failures = 0
            target.death_save_successes = 0
            condition_deltas.append(f"{target_id} drops to 0 HP and falls unconscious.")
            condition_deltas.extend(end_rage(target, reason=f"{target_id}'s rage ends."))

    return DamageApplicationResult(
        hp_delta=target.current_hp - previous_hp,
        condition_deltas=condition_deltas,
        resisted_damage=resisted_damage,
        amplified_damage=amplified_damage,
        temporary_hp_absorbed=temporary_hp_absorbed,
        final_damage_to_hp=final_damage_to_hp,
        final_total_damage=final_total_damage,
        undead_fortitude_triggered=undead_fortitude_triggered,
        undead_fortitude_success=undead_fortitude_success,
        undead_fortitude_dc=undead_fortitude_dc,
        undead_fortitude_bypass_reason=undead_fortitude_bypass_reason,
    )


def apply_mastery(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    mastery: MasteryType | None,
    hit: bool,
    damage: int,
) -> tuple[MasteryType | None, str | None, list[str]]:
    target = state.units[target_id]

    if not mastery or not hit:
        return None, None, []

    if mastery == "sap":
        target.temporary_effects = [
            effect
            for effect in target.temporary_effects
            if not (effect.kind == "sap" and effect.source_id == attacker_id)
        ]
        target.temporary_effects.append(
            SapEffect(kind="sap", source_id=attacker_id, expires_at_turn_start_of=attacker_id)
        )
        return (
            "sap",
            f"{target_id} has disadvantage on its next attack roll before {attacker_id}'s next turn.",
            [f"{target_id} is sapped by {attacker_id}."],
        )

    if mastery == "slow" and damage > 0:
        target.temporary_effects = [
            effect
            for effect in target.temporary_effects
            if not (effect.kind == "slow" and effect.source_id == attacker_id)
        ]
        target.temporary_effects.append(
            SlowEffect(kind="slow", source_id=attacker_id, expires_at_turn_start_of=attacker_id, penalty=10)
        )
        recalculate_effective_speed_for_unit(target)
        return (
            "slow",
            f"{target_id}'s speed is reduced by 10 feet until {attacker_id}'s next turn.",
            [f"{target_id} is slowed by {attacker_id}."],
        )

    if mastery == "vex" and damage > 0:
        attacker = state.units[attacker_id]
        attacker.temporary_effects = [
            effect
            for effect in attacker.temporary_effects
            if not (effect.kind == "vex" and effect.target_id == target_id)
        ]
        attacker.temporary_effects.append(
            VexEffect(
                kind="vex",
                source_id=attacker_id,
                target_id=target_id,
                expires_at_turn_end_of=attacker_id,
                expires_at_round=state.round + 1,
            )
        )
        return (
            "vex",
            f"{attacker_id} has advantage on the next attack roll against {target_id}.",
            [f"{attacker_id} vexes {target_id} for the next attack roll."],
        )

    return None, None, []


def is_within_max_target_size(target_size: str, max_target_size: str | None) -> bool:
    if not max_target_size:
        return True

    size_order = {
        "tiny": 0,
        "small": 1,
        "medium": 2,
        "large": 3,
        "huge": 4,
        "gargantuan": 5,
    }
    return size_order[target_size] <= size_order[max_target_size]


def apply_on_hit_effects(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    weapon: WeaponProfile,
    hit: bool,
) -> tuple[list[AttackRiderType], list[str]]:
    target = state.units[target_id]

    if not hit or not weapon.on_hit_effects:
        return [], []

    applied_riders: list[AttackRiderType] = []
    condition_deltas: list[str] = []

    for effect in weapon.on_hit_effects:
        if effect.kind == "prone_on_hit":
            if target.conditions.dead or target.current_hp <= 0 or target.conditions.unconscious or target.conditions.prone:
                continue
            if not is_within_max_target_size(target.size_category, effect.max_target_size):
                continue

            target.conditions.prone = True
            applied_riders.append("prone_on_hit")
            condition_deltas.append(f"{target_id} is knocked prone.")
            continue

        if effect.kind in {"grapple_on_hit", "grapple_and_restrain"}:
            if target.conditions.dead or target.current_hp <= 0:
                continue
            if not is_within_max_target_size(target.size_category, effect.max_target_size):
                continue

            escape_dc = effect.escape_dc or 0
            target.temporary_effects = [
                active_effect
                for active_effect in target.temporary_effects
                if not (
                    active_effect.kind in {"grappled_by", "restrained_by"}
                    and active_effect.source_id == attacker_id
                )
            ]
            target.temporary_effects.append(
                GrappledEffect(
                    kind="grappled_by",
                    source_id=attacker_id,
                    escape_dc=escape_dc,
                    maintain_reach_feet=weapon.reach or 5,
                )
            )

            if effect.kind == "grapple_and_restrain":
                target.temporary_effects.append(
                    RestrainedEffect(kind="restrained_by", source_id=attacker_id, escape_dc=escape_dc)
                )

            applied_riders.append(effect.kind)
            condition_deltas.append(f"{target_id} is grappled by {attacker_id} (escape DC {escape_dc}).")
            if effect.kind == "grapple_and_restrain":
                condition_deltas.append(f"{target_id} is restrained by {attacker_id} (escape DC {escape_dc}).")
            continue

        if effect.kind == "harry_target":
            if target.conditions.dead or target.current_hp <= 0:
                continue

            target.temporary_effects = [
                active_effect
                for active_effect in target.temporary_effects
                if not (active_effect.kind == "harried_by" and active_effect.source_id == attacker_id)
            ]
            target.temporary_effects.append(
                HarriedEffect(
                    kind="harried_by",
                    source_id=attacker_id,
                    target_id=target_id,
                    expires_at_turn_start_of=attacker_id,
                )
            )
            applied_riders.append("harry_target")
            condition_deltas.append(
                f"{target_id} is harried by {attacker_id}; the next attack roll against it has advantage."
            )

    return applied_riders, condition_deltas


def target_is_grappled_by_attacker(state: EncounterState, target: UnitState, attacker_id: str) -> bool:
    return is_active_grapple(state, attacker_id, target.id)


def can_trigger_attack_reaction(unit: UnitState, reaction_id: str) -> bool:
    return (
        unit.faction == "goblins"
        and
        unit_can_take_reactions(unit)
        and unit_has_reaction(unit, reaction_id)
    )


def can_cast_shield_reaction(unit: UnitState) -> bool:
    return (
        unit_can_take_reactions(unit)
        and not unit_has_shield_effect(unit)
        and unit_has_combat_spell(unit, "shield")
        and unit.resources.spell_slots_level_1 > 0
    )


def maybe_apply_shield_reaction(
    state: EncounterState,
    *,
    attacker_id: str,
    target_id: str,
    trigger: str,
    attack_total: int | None = None,
    target_ac: int | None = None,
    natural_twenty: bool = False,
) -> dict[str, int | str] | None:
    _ = attacker_id
    target = state.units[target_id]
    shield_spell = get_spell_definition("shield")
    if not can_cast_shield_reaction(target):
        return None

    should_cast = trigger == "magic_missile"
    if trigger == "attack_hit":
        if attack_total is None or target_ac is None:
            return None
        if state.player_behavior == "smart":
            should_cast = (not natural_twenty) and attack_total < (target_ac + shield_spell.ac_bonus)
        else:
            should_cast = True

    if not should_cast:
        return None

    if not target.resources.spend_pool("spell_slots_level_1", 1):
        return None

    target.reaction_available = False
    target.temporary_effects = [effect for effect in target.temporary_effects if effect.kind != "shield"]
    target.temporary_effects.append(
        ShieldEffect(
            kind="shield",
            source_id=target_id,
            expires_at_turn_start_of=target_id,
            ac_bonus=shield_spell.ac_bonus,
        )
    )
    return {
        "defenseReaction": "shield",
        "defenseReactionActorId": target_id,
        "defenseReactionTrigger": trigger,
        "shieldAcBonus": shield_spell.ac_bonus,
        "reactionSpellSlotsLevel1Remaining": target.resources.spell_slots_level_1,
    }


@dataclass(frozen=True)
class BurningHandsTargeting:
    primary_target_id: str
    target_ids: tuple[str, ...]
    enemy_target_ids: tuple[str, ...]
    ally_target_ids: tuple[str, ...]


BURNING_HANDS_CONE_ENDPOINTS: dict[str, tuple[tuple[int, int], ...]] = {
    "n": ((-1, -3), (0, -3), (1, -3)),
    "ne": ((1, -3), (3, -3), (3, -1)),
    "e": ((3, -1), (3, 0), (3, 1)),
    "se": ((1, 3), (3, 1), (3, 3)),
    "s": ((-1, 3), (0, 3), (1, 3)),
    "sw": ((-3, 1), (-3, 3), (-1, 3)),
    "w": ((-3, -1), (-3, 0), (-3, 1)),
    "nw": ((-3, -3), (-3, -1), (-1, -3)),
}


def get_burning_hands_cone_squares(origin: GridPosition, direction: str) -> list[GridPosition]:
    square_keys: set[tuple[int, int]] = set()
    for delta_x, delta_y in BURNING_HANDS_CONE_ENDPOINTS[direction]:
        endpoint = GridPosition(x=origin.x + delta_x, y=origin.y + delta_y)
        for square in get_line_squares(origin, endpoint)[1:]:
            square_keys.add((square.x, square.y))
    return [GridPosition(x=x, y=y) for x, y in sorted(square_keys)]


def choose_burning_hands_targeting(
    state: EncounterState,
    actor_id: str,
    *,
    actor_position: GridPosition | None = None,
    required_primary_target_id: str | None = None,
) -> BurningHandsTargeting | None:
    actor = state.units[actor_id]
    origin = actor_position or actor.position
    if not origin:
        return None

    viable: list[BurningHandsTargeting] = []
    live_units = [
        unit
        for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id))
        if unit.position and not unit.conditions.dead
    ]

    for direction in sorted(BURNING_HANDS_CONE_ENDPOINTS):
        cone_square_keys = {(square.x, square.y) for square in get_burning_hands_cone_squares(origin, direction)}
        hit_units = [
            unit
            for unit in live_units
            if any(
                (occupied_square.x, occupied_square.y) in cone_square_keys
                for occupied_square in get_occupied_squares_for_position(unit.position, get_unit_footprint(unit))
            )
        ]
        if not hit_units:
            continue

        if required_primary_target_id and all(unit.id != required_primary_target_id for unit in hit_units):
            continue

        sorted_target_ids = tuple(unit.id for unit in hit_units)
        enemy_target_ids = tuple(unit.id for unit in hit_units if unit.faction != actor.faction)
        ally_target_ids = tuple(unit.id for unit in hit_units if unit.faction == actor.faction and unit.id != actor_id)
        if not enemy_target_ids:
            continue

        primary_target_id = required_primary_target_id or sorted(enemy_target_ids, key=unit_sort_key)[0]
        viable.append(
            BurningHandsTargeting(
                primary_target_id=primary_target_id,
                target_ids=sorted_target_ids,
                enemy_target_ids=enemy_target_ids,
                ally_target_ids=ally_target_ids,
            )
        )

    if not viable:
        return None

    return sorted(
        viable,
        key=lambda targeting: (
            -len(targeting.enemy_target_ids),
            len(targeting.ally_target_ids),
            sum(state.units[target_id].current_hp for target_id in targeting.enemy_target_ids),
            targeting.primary_target_id,
            targeting.target_ids,
        ),
    )[0]


def choose_redirect_attack_ally(state: EncounterState, reactor_id: str) -> UnitState | None:
    reactor = state.units[reactor_id]
    if not reactor.position:
        return None

    eligible_allies = [
        unit
        for unit in state.units.values()
        if unit.id != reactor_id
        and unit.faction == reactor.faction
        and unit.position
        and unit.current_hp > 0
        and not unit.conditions.dead
        and not unit.conditions.unconscious
        and unit.size_category in {"small", "medium"}
        and get_min_chebyshev_distance_between_footprints(
            reactor.position,
            get_unit_footprint(reactor),
            unit.position,
            get_unit_footprint(unit),
        )
        <= 1
    ]

    if not eligible_allies:
        return None

    return sorted(eligible_allies, key=lambda unit: (-unit.ac, -unit.current_hp, unit_sort_key(unit.id)))[0]


def get_attack_mode(
    state: EncounterState,
    attacker: UnitState,
    attacker_id: str,
    target: UnitState,
    target_id: str,
    weapon: WeaponProfile,
) -> tuple[AttackMode, list[str], list[str]]:
    spatial_context = get_attack_context(state, attacker_id, target_id, weapon)
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

    if has_vex_effect(attacker, target_id):
        advantage_sources.append("vex")

    if has_harried_effect(target):
        advantage_sources.append("harried_target")

    if weapon.advantage_against_self_grappled_target and target_is_grappled_by_attacker(state, target, attacker_id):
        advantage_sources.append("self_grappled_target")

    if attacker.faction == "goblins" and unit_has_trait(attacker, "bloodied_frenzy") and unit_is_bloodied(attacker):
        advantage_sources.append("bloodied_frenzy")

    if unit_has_reckless_attack_effect(attacker) and weapon.attack_ability == "str":
        advantage_sources.append("reckless_attack")

    if advantage_sources and disadvantage_sources:
        return "normal", advantage_sources, disadvantage_sources
    if advantage_sources:
        return "advantage", advantage_sources, disadvantage_sources
    if disadvantage_sources:
        return "disadvantage", advantage_sources, disadvantage_sources
    return "normal", advantage_sources, disadvantage_sources


def build_skip_event(state: EncounterState, actor_id: str, reason: str) -> CombatEvent:
    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[],
        event_type="skip",
        raw_rolls={},
        resolved_totals={"reason": reason},
        movement_details=None,
        damage_details=None,
        condition_deltas=[],
        text_summary=f"{actor_id} skips its turn: {reason}",
    )


def create_skip_event(state: EncounterState, actor_id: str, reason: str) -> CombatEvent:
    return build_skip_event(state, actor_id, reason)


def build_final_damage_components(
    chosen_candidate: DamageCandidate | None,
    advantage_bonus_candidate: DamageCandidate | None,
    critical_multiplier: int,
) -> list[DamageComponentResult]:
    components: list[DamageComponentResult] = []

    for candidate in [chosen_candidate, advantage_bonus_candidate]:
        if not candidate:
            continue

        for component in candidate.components:
            components.append(
                DamageComponentResult(
                    damage_type=component.damage_type,
                    raw_rolls=list(component.raw_rolls),
                    adjusted_rolls=list(component.adjusted_rolls),
                    subtotal=component.subtotal,
                    flat_modifier=component.flat_modifier,
                    total_damage=(component.subtotal * critical_multiplier) + component.flat_modifier,
                )
            )

    return components


def build_spell_skip_event(state: EncounterState, actor_id: str, spell_id: str, reason: str) -> CombatEvent:
    spell = get_spell_definition(spell_id)
    return build_skip_event(state, actor_id, f"{spell.display_name}: {reason}")


def resolve_ranged_spell_attack(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    spell_id: str,
    overrides: AttackRollOverrides | None = None,
) -> CombatEvent:
    attacker = state.units[attacker_id]
    target = state.units[target_id]
    spell = get_spell_definition(spell_id)
    weapon = build_spell_attack_profile(attacker, spell_id)

    attack_context = get_attack_context(state, attacker_id, target_id, weapon)
    if not attack_context.legal or not attack_context.within_normal_range:
        return build_spell_skip_event(state, attacker_id, spell_id, "is not in range.")

    overrides = AttackRollOverrides(
        attack_rolls=list(overrides.attack_rolls if overrides else []),
        damage_rolls=list(overrides.damage_rolls if overrides else []),
    )

    vex_available = has_vex_effect(attacker, target_id)
    harried_available = has_harried_effect(target)
    mode, advantage_sources, disadvantage_sources = get_attack_mode(state, attacker, attacker_id, target, target_id, weapon)

    if mode == "normal":
        attack_rolls = [pull_die(state, 20, overrides.attack_rolls.pop(0) if overrides.attack_rolls else None)]
    else:
        attack_rolls = [
            pull_die(state, 20, overrides.attack_rolls.pop(0) if overrides.attack_rolls else None),
            pull_die(state, 20, overrides.attack_rolls.pop(0) if overrides.attack_rolls else None),
        ]

    if mode == "advantage":
        selected_roll = max(attack_rolls)
    elif mode == "disadvantage":
        selected_roll = min(attack_rolls)
    else:
        selected_roll = attack_rolls[0]

    vex_consumed = consume_vex_effect(attacker, target_id) if vex_available else False
    harried_consumed = consume_harried_effect(target) if harried_available else False
    sap_consumed = consume_sap_effects(attacker)
    attack_total = selected_roll + weapon.attack_bonus
    natural_one = selected_roll == 1
    natural_twenty = selected_roll == 20
    resolved_target_id = target_id
    reaction_actor_id: str | None = None
    attack_reaction: str | None = None
    defense_reaction_data: dict[str, int | str] | None = None
    target_ac = target.ac + attack_context.cover_ac_bonus + get_shield_ac_bonus(target)
    hit = natural_twenty or (not natural_one and attack_total >= target_ac)

    if hit:
        defense_reaction_data = maybe_apply_shield_reaction(
            state,
            attacker_id=attacker_id,
            target_id=target_id,
            trigger="attack_hit",
            attack_total=attack_total,
            target_ac=target_ac,
            natural_twenty=natural_twenty,
        )
        if defense_reaction_data:
            target_ac += int(defense_reaction_data["shieldAcBonus"])
            hit = natural_twenty or (not natural_one and attack_total >= target_ac)

    if hit and can_trigger_attack_reaction(target, "redirect_attack"):
        redirect_target = choose_redirect_attack_ally(state, target_id)
        if redirect_target:
            original_position = target.position.model_copy(deep=True) if target.position else None
            redirect_position = redirect_target.position.model_copy(deep=True) if redirect_target.position else None
            target.reaction_available = False
            if original_position and redirect_position:
                target.position = redirect_position
                redirect_target.position = original_position
            resolved_target_id = redirect_target.id
            target = redirect_target
            attack_context = get_attack_context(state, attacker_id, resolved_target_id, weapon)
            target_ac = target.ac + attack_context.cover_ac_bonus + get_shield_ac_bonus(target)
            hit = attack_context.legal and (natural_twenty or (not natural_one and attack_total >= target_ac))
            reaction_actor_id = target_id
            attack_reaction = "redirect_attack"

    if (
        not attack_reaction
        and hit
        and weapon.kind == "melee"
        and can_trigger_attack_reaction(target, "parry")
        and not natural_twenty
        and attack_total < (target_ac + 2)
    ):
        target.reaction_available = False
        target_ac += 2
        hit = False
        reaction_actor_id = target.id
        attack_reaction = "parry"

    critical = hit and natural_twenty
    primary_candidate: DamageCandidate | None = None
    final_damage_components: list[DamageComponentResult] = []
    total_damage = 0
    resisted_damage = 0
    amplified_damage = 0
    temporary_hp_absorbed = 0
    final_damage_to_hp = 0
    hp_delta = 0
    condition_deltas: list[str] = []

    if attack_reaction == "redirect_attack":
        condition_deltas.append(f"{target_id} uses Redirect Attack and swaps with {resolved_target_id}.")
    elif attack_reaction == "parry" and reaction_actor_id:
        condition_deltas.append(f"{reaction_actor_id} uses Parry and adds 2 AC against this attack.")

    condition_deltas.extend(end_hidden(attacker, reason=f"{attacker_id} is no longer hidden after attacking."))

    if hit:
        primary_candidate = roll_damage_candidate(state, weapon, overrides.damage_rolls)
        critical_multiplier = 2 if critical else 1
        final_damage_components = build_final_damage_components(primary_candidate, None, critical_multiplier)
        damage_result = apply_damage(state, resolved_target_id, final_damage_components, critical)
        total_damage = sum(component.total_damage for component in final_damage_components)
        resisted_damage = damage_result.resisted_damage
        amplified_damage = damage_result.amplified_damage
        temporary_hp_absorbed = damage_result.temporary_hp_absorbed
        final_damage_to_hp = damage_result.final_damage_to_hp
        hp_delta = damage_result.hp_delta
        condition_deltas.extend(damage_result.condition_deltas)
        if (
            spell.on_hit_effect_kind == "no_reactions"
            and state.units[resolved_target_id].current_hp > 0
            and not state.units[resolved_target_id].conditions.dead
        ):
            shocked_target = state.units[resolved_target_id]
            shocked_target.temporary_effects = [
                effect
                for effect in shocked_target.temporary_effects
                if not (effect.kind == "no_reactions" and effect.source_id == attacker_id)
            ]
            shocked_target.temporary_effects.append(
                NoReactionsEffect(
                    kind="no_reactions",
                    source_id=attacker_id,
                    expires_at_turn_start_of=resolved_target_id,
                )
            )
            condition_deltas.append(f"{resolved_target_id} cannot take reactions until the start of its next turn.")

    if sap_consumed > 0:
        condition_deltas.append(f"{attacker_id}'s sap disadvantage is consumed on this attack roll.")
    if vex_consumed:
        condition_deltas.append(f"{attacker_id}'s vex advantage is consumed on this attack roll.")
    if harried_consumed:
        condition_deltas.append(f"{target_id}'s harried defense is consumed on this attack roll.")

    critical_multiplier = 2 if critical else 1
    hit_label = "critical hit" if critical else "hit" if hit else "miss"
    return CombatEvent(
        **event_base(state, attacker_id),
        target_ids=[resolved_target_id],
        event_type="attack",
        raw_rolls={
            "attackRolls": attack_rolls,
            "advantageSources": advantage_sources,
            "disadvantageSources": disadvantage_sources,
        },
        resolved_totals={
            "spellId": spell_id,
            "attackMode": mode,
            "selectedRoll": selected_roll,
            "attackTotal": attack_total,
            "targetAc": target_ac,
            "coverAcBonus": attack_context.cover_ac_bonus,
            "distanceSquares": attack_context.distance_squares,
            "distanceFeet": attack_context.distance_feet,
            "hit": hit,
            "critical": critical,
            "sapConsumed": sap_consumed,
            "opportunityAttack": False,
            "originalTargetId": target_id,
            "attackReaction": attack_reaction,
            "reactionActorId": reaction_actor_id,
            "shieldAcBonus": get_shield_ac_bonus(target),
            **(defense_reaction_data or {}),
        },
        movement_details=None,
        damage_details=DamageDetails(
            weapon_id=spell_id,
            weapon_name=spell.display_name,
            damage_components=final_damage_components,
            primary_candidate=primary_candidate,
            savage_candidate=None,
            chosen_candidate="primary" if primary_candidate else None,
            critical_applied=critical,
            critical_multiplier=critical_multiplier,
            flat_modifier=sum(component.flat_modifier for component in final_damage_components),
            advantage_bonus_candidate=None,
            mastery_applied=None,
            mastery_notes=None,
            attack_riders_applied=None,
            total_damage=total_damage,
            resisted_damage=resisted_damage,
            amplified_damage=amplified_damage or None,
            temporary_hp_absorbed=temporary_hp_absorbed,
            final_damage_to_hp=final_damage_to_hp,
            hp_delta=hp_delta,
        ),
        condition_deltas=condition_deltas,
        text_summary=(
            f"{attacker_id} casts {spell.display_name} at {resolved_target_id}: "
            f"{hit_label}"
            f"{f' for {total_damage} damage' if total_damage > 0 else ''}"
            f"{f' ({resisted_damage} resisted)' if resisted_damage > 0 else ''}"
            f"{f' (+{amplified_damage} vulnerability)' if amplified_damage > 0 else ''}."
        ),
    )


def resolve_magic_missile(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
) -> CombatEvent:
    attacker = state.units[attacker_id]
    spell = get_spell_definition("magic_missile")
    weapon = build_spell_attack_profile(attacker, "magic_missile")
    attack_context = get_attack_context(state, attacker_id, target_id, weapon)

    if not attack_context.legal or not attack_context.within_normal_range:
        return build_spell_skip_event(state, attacker_id, "magic_missile", "is not in range.")
    if not attacker.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, attacker_id, "magic_missile", "No level 1 spell slots remain.")

    target = state.units[target_id]
    defense_reaction_data = (
        maybe_apply_shield_reaction(state, attacker_id=attacker_id, target_id=target_id, trigger="magic_missile")
        if not unit_has_shield_effect(target)
        else None
    )
    blocked_by_shield = unit_has_shield_effect(state.units[target_id])

    primary_candidate: DamageCandidate | None = None
    final_damage_components: list[DamageComponentResult] = []
    total_damage = 0
    damage_result = DamageApplicationResult(
        hp_delta=0,
        condition_deltas=[],
        resisted_damage=0,
        amplified_damage=0,
        temporary_hp_absorbed=0,
        final_damage_to_hp=0,
        final_total_damage=0,
    )
    condition_deltas: list[str] = []

    if blocked_by_shield:
        condition_deltas.append(f"{target_id}'s Shield blocks Magic Missile.")
    else:
        damage_overrides = AttackRollOverrides(damage_rolls=list(overrides.damage_rolls if overrides else []))
        primary_candidate = roll_damage_candidate(state, weapon, damage_overrides.damage_rolls)
        final_damage_components = build_final_damage_components(primary_candidate, None, 1)
        damage_result = apply_damage(state, target_id, final_damage_components, False)
        total_damage = sum(component.total_damage for component in final_damage_components)
        condition_deltas = list(damage_result.condition_deltas)

    return CombatEvent(
        **event_base(state, attacker_id),
        target_ids=[target_id],
        event_type="attack",
        raw_rolls={"damageRolls": primary_candidate.raw_rolls if primary_candidate else []},
        resolved_totals={
            "spellId": "magic_missile",
            "spellLevel": 1,
            "hit": True,
            "critical": False,
            "distanceSquares": attack_context.distance_squares,
            "distanceFeet": attack_context.distance_feet,
            "spellSlotsLevel1Remaining": attacker.resources.spell_slots_level_1,
            "blockedByShield": blocked_by_shield,
            **(defense_reaction_data or {}),
        },
        movement_details=None,
        damage_details=DamageDetails(
            weapon_id="magic_missile",
            weapon_name=spell.display_name,
            damage_components=final_damage_components,
            primary_candidate=primary_candidate,
            savage_candidate=None,
            chosen_candidate="primary",
            critical_applied=False,
            critical_multiplier=1,
            flat_modifier=sum(component.flat_modifier for component in final_damage_components),
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
        condition_deltas=condition_deltas,
        text_summary=(
            f"{attacker_id} casts {spell.display_name} at {target_id}, but Shield blocks it."
            if blocked_by_shield
            else (
                f"{attacker_id} casts {spell.display_name} at {target_id} for {total_damage} damage"
                f"{f' ({damage_result.resisted_damage} resisted)' if damage_result.resisted_damage > 0 else ''}"
                f"{f' (+{damage_result.amplified_damage} vulnerability)' if damage_result.amplified_damage > 0 else ''}."
            )
        ),
    )


def build_burning_hands_damage_component(
    base_rolls: list[int],
    applied_damage: int,
    damage_type: str,
) -> list[DamageComponentResult]:
    return [
        DamageComponentResult(
            damage_type=damage_type,
            raw_rolls=list(base_rolls),
            adjusted_rolls=list(base_rolls),
            subtotal=sum(base_rolls),
            flat_modifier=0,
            total_damage=applied_damage,
        )
    ]


def resolve_burning_hands(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
) -> list[CombatEvent]:
    attacker = state.units[attacker_id]
    spell = get_spell_definition("burning_hands")

    if not unit_has_combat_spell(attacker, "burning_hands"):
        return [build_spell_skip_event(state, attacker_id, "burning_hands", "is not prepared.")]
    if not attacker.position:
        return [build_spell_skip_event(state, attacker_id, "burning_hands", "requires a map position.")]

    targeting = choose_burning_hands_targeting(state, attacker_id, required_primary_target_id=target_id)
    if not targeting:
        return [build_spell_skip_event(state, attacker_id, "burning_hands", "has no legal cone from the current position.")]
    if not attacker.resources.spend_pool("spell_slots_level_1", 1):
        return [build_spell_skip_event(state, attacker_id, "burning_hands", "No level 1 spell slots remain.")]

    damage_rolls_override = list(overrides.damage_rolls if overrides else [])
    save_rolls_override = list(overrides.save_rolls if overrides else [])
    damage_rolls = [pull_die(state, 6, damage_rolls_override.pop(0) if damage_rolls_override else None) for _ in range(3)]
    full_damage = sum(damage_rolls)
    save_dc = get_spell_save_dc(attacker, "burning_hands")

    events = [
        CombatEvent(
            **event_base(state, attacker_id),
            target_ids=list(targeting.target_ids),
            event_type="phase_change",
            raw_rolls={},
            resolved_totals={
                "spellId": "burning_hands",
                "spellLevel": 1,
                "enemyTargetCount": len(targeting.enemy_target_ids),
                "allyTargetCount": len(targeting.ally_target_ids),
                "spellSlotsLevel1Remaining": attacker.resources.spell_slots_level_1,
            },
            movement_details=None,
            damage_details=None,
            condition_deltas=[],
            text_summary=(
                f"{attacker_id} casts {spell.display_name}, catching "
                f"{len(targeting.enemy_target_ids)} enemies and {len(targeting.ally_target_ids)} allies."
            ),
        )
    ]

    for resolved_target_id in targeting.target_ids:
        target = state.units[resolved_target_id]
        save_mode, _, _ = get_saving_throw_mode(target, spell.save_ability or "dex")
        save_roll_count = 1 if save_mode == "normal" else 2
        save_rolls = [
            save_rolls_override.pop(0) for _ in range(min(save_roll_count, len(save_rolls_override)))
        ]
        save_event = resolve_saving_throw(
            state,
            ResolveSavingThrowArgs(
                actor_id=resolved_target_id,
                ability=spell.save_ability or "dex",
                dc=save_dc,
                reason=spell.display_name,
                overrides=SavingThrowOverrides(save_rolls=save_rolls),
            ),
        )
        save_success = bool(save_event.resolved_totals["success"])
        applied_damage = full_damage // 2 if save_success and spell.half_on_success else full_damage
        damage_components = build_burning_hands_damage_component(damage_rolls, applied_damage, spell.damage_type)
        damage_result = apply_damage(state, resolved_target_id, damage_components, False)
        events.append(save_event)
        events.append(
            CombatEvent(
                **event_base(state, attacker_id),
                target_ids=[resolved_target_id],
                event_type="attack",
                raw_rolls={"damageRolls": list(damage_rolls)},
                resolved_totals={
                    "spellId": "burning_hands",
                    "spellLevel": 1,
                    "saveAbility": spell.save_ability,
                    "saveDc": save_dc,
                    "saveSucceeded": save_success,
                    "fullDamage": full_damage,
                    "halfOnSuccess": spell.half_on_success,
                },
                movement_details=None,
                damage_details=DamageDetails(
                    weapon_id="burning_hands",
                    weapon_name=spell.display_name,
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
                    f"{attacker_id}'s {spell.display_name} hits {resolved_target_id} for {applied_damage} damage"
                    f"{' after a successful save' if save_success else ' after a failed save'}"
                    f"{f' ({damage_result.resisted_damage} resisted)' if damage_result.resisted_damage > 0 else ''}"
                    f"{f' (+{damage_result.amplified_damage} vulnerability)' if damage_result.amplified_damage > 0 else ''}."
                ),
            )
        )

    return events


def resolve_cast_spell(
    state: EncounterState,
    actor_id: str,
    spell_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
) -> CombatEvent:
    actor = state.units[actor_id]
    spell = get_spell_definition(spell_id)

    if not unit_has_combat_spell(actor, spell_id):
        return build_spell_skip_event(state, actor_id, spell_id, "is not prepared.")

    if spell.level > 0 and spell_id in actor.prepared_combat_spell_ids and spell.level == 1 and actor.resources.spell_slots_level_1 <= 0:
        return build_spell_skip_event(state, actor_id, spell_id, "No level 1 spell slots remain.")

    if spell.targeting_mode in {"ranged_spell_attack", "melee_spell_attack"}:
        return resolve_ranged_spell_attack(state, actor_id, target_id, spell_id, overrides)
    if spell.targeting_mode == "auto_hit_single_target":
        return resolve_magic_missile(state, actor_id, target_id, overrides)

    return build_spell_skip_event(state, actor_id, spell_id, "cannot be resolved by the live simulator.")


def resolve_attack(state: EncounterState, args: ResolveAttackArgs) -> tuple[CombatEvent, bool]:
    attacker = state.units[args.attacker_id]
    weapon = attacker.attacks.get(args.weapon_id)

    if not weapon:
        return build_skip_event(state, args.attacker_id, f"{args.weapon_id} is unavailable."), False

    attack_context = get_attack_context(state, args.attacker_id, args.target_id, weapon)
    if not attack_context.legal:
        return build_skip_event(state, args.attacker_id, f"{weapon.display_name} is not in range."), False

    if weapon.resource_pool_id and attacker.resources.get_pool(weapon.resource_pool_id) <= 0:
        return build_skip_event(state, args.attacker_id, f"No {weapon.display_name.lower()} uses remain."), False
    if weapon.resource_pool_id:
        attacker.resources.spend_pool(weapon.resource_pool_id)

    overrides = AttackRollOverrides(
        attack_rolls=list(args.overrides.attack_rolls if args.overrides else []),
        damage_rolls=list(args.overrides.damage_rolls if args.overrides else []),
        savage_damage_rolls=list(args.overrides.savage_damage_rolls if args.overrides else []),
        advantage_damage_rolls=list(args.overrides.advantage_damage_rolls if args.overrides else []),
    )

    target = state.units[args.target_id]
    vex_available = has_vex_effect(attacker, args.target_id)
    harried_available = has_harried_effect(target)
    mode, advantage_sources, disadvantage_sources = get_attack_mode(
        state, attacker, args.attacker_id, target, args.target_id, weapon
    )

    if mode == "normal":
        attack_rolls = [pull_die(state, 20, overrides.attack_rolls.pop(0) if overrides.attack_rolls else None)]
    else:
        attack_rolls = [
            pull_die(state, 20, overrides.attack_rolls.pop(0) if overrides.attack_rolls else None),
            pull_die(state, 20, overrides.attack_rolls.pop(0) if overrides.attack_rolls else None),
        ]

    if mode == "advantage":
        selected_roll = max(attack_rolls)
    elif mode == "disadvantage":
        selected_roll = min(attack_rolls)
    else:
        selected_roll = attack_rolls[0]

    if unit_is_raging(attacker):
        attacker._rage_qualified_since_turn_end = True

    vex_consumed = consume_vex_effect(attacker, args.target_id) if vex_available else False
    harried_consumed = consume_harried_effect(target) if harried_available else False

    sap_consumed = consume_sap_effects(attacker)
    attack_total = selected_roll + weapon.attack_bonus
    natural_one = selected_roll == 1
    natural_twenty = selected_roll == 20
    resolved_target_id = args.target_id
    reaction_actor_id: str | None = None
    attack_reaction: str | None = None
    defense_reaction_data: dict[str, int | str] | None = None
    target_ac = target.ac + attack_context.cover_ac_bonus + get_shield_ac_bonus(target)
    hit = natural_twenty or (not natural_one and attack_total >= target_ac)

    if hit:
        defense_reaction_data = maybe_apply_shield_reaction(
            state,
            attacker_id=args.attacker_id,
            target_id=args.target_id,
            trigger="attack_hit",
            attack_total=attack_total,
            target_ac=target_ac,
            natural_twenty=natural_twenty,
        )
        if defense_reaction_data:
            target_ac += int(defense_reaction_data["shieldAcBonus"])
            hit = natural_twenty or (not natural_one and attack_total >= target_ac)

    if hit and can_trigger_attack_reaction(target, "redirect_attack"):
        redirect_target = choose_redirect_attack_ally(state, args.target_id)
        if redirect_target:
            original_position = target.position.model_copy(deep=True) if target.position else None
            redirect_position = redirect_target.position.model_copy(deep=True) if redirect_target.position else None
            target.reaction_available = False
            if original_position and redirect_position:
                target.position = redirect_position
                redirect_target.position = original_position
            resolved_target_id = redirect_target.id
            target = redirect_target
            attack_context = get_attack_context(state, args.attacker_id, resolved_target_id, weapon)
            target_ac = target.ac + attack_context.cover_ac_bonus + get_shield_ac_bonus(target)
            hit = attack_context.legal and (natural_twenty or (not natural_one and attack_total >= target_ac))
            reaction_actor_id = args.target_id
            attack_reaction = "redirect_attack"

    if (
        not attack_reaction
        and hit
        and weapon.kind == "melee"
        and can_trigger_attack_reaction(target, "parry")
        and not natural_twenty
        and attack_total < (target_ac + 2)
    ):
        target.reaction_available = False
        target_ac += 2
        hit = False
        reaction_actor_id = target.id
        attack_reaction = "parry"

    target_was_bloodied_before_hit = unit_is_bloodied(target)
    automatic_critical = weapon.kind == "melee" and target.conditions.unconscious
    critical = hit and (natural_twenty or automatic_critical)

    primary_candidate: DamageCandidate | None = None
    savage_candidate: DamageCandidate | None = None
    chosen_candidate: str | None = None
    advantage_bonus_candidate: DamageCandidate | None = None
    mastery_applied: MasteryType | None = None
    mastery_notes: str | None = None
    attack_riders_applied: list[AttackRiderType] | None = None
    sneak_attack_component: DamageComponentResult | None = None
    total_damage = 0
    resisted_damage = 0
    amplified_damage = 0
    temporary_hp_absorbed = 0
    final_damage_to_hp = 0
    hp_delta = 0
    undead_fortitude_triggered = False
    undead_fortitude_success: bool | None = None
    undead_fortitude_dc: int | None = None
    undead_fortitude_bypass_reason: str | None = None
    condition_deltas: list[str] = []
    savage_attacker_consumed = False
    final_damage_components: list[DamageComponentResult] = []

    if attack_reaction == "redirect_attack":
        condition_deltas.append(f"{args.target_id} uses Redirect Attack and swaps with {resolved_target_id}.")
    elif attack_reaction == "parry" and reaction_actor_id:
        condition_deltas.append(f"{reaction_actor_id} uses Parry and adds 2 AC against this attack.")

    condition_deltas.extend(end_hidden(attacker, reason=f"{args.attacker_id} is no longer hidden after attacking."))

    if hit:
        # Great Weapon Fighting is applied before Savage Attacker chooses the better damage candidate.
        apply_gwf = weapon.kind == "melee" and weapon.two_handed is True
        primary_candidate = roll_damage_candidate(
            state,
            weapon,
            overrides.damage_rolls,
            apply_gwf,
            args.omit_ability_modifier_damage,
        )

        if args.savage_attacker_available and unit_has_feature(attacker, "savage_attacker"):
            savage_candidate = roll_damage_candidate(
                state,
                weapon,
                overrides.savage_damage_rolls,
                apply_gwf,
                args.omit_ability_modifier_damage,
            )
            savage_attacker_consumed = True

        chosen_candidate, chosen_rolls = choose_damage_candidate(primary_candidate, savage_candidate)

        if mode == "advantage" and (weapon.advantage_damage_dice or weapon.advantage_damage_components):
            advantage_bonus_candidate = roll_bonus_candidate(state, weapon, overrides.advantage_damage_rolls)

        critical_multiplier = 2 if critical else 1
        final_damage_components = build_final_damage_components(chosen_rolls, advantage_bonus_candidate, critical_multiplier)
        rage_damage_bonus = get_rage_damage_bonus(attacker, weapon)
        if rage_damage_bonus > 0:
            rage_damage_type = (
                final_damage_components[0].damage_type
                if final_damage_components
                else weapon.damage_type
                or (weapon.damage_components[0].damage_type if weapon.damage_components else "damage")
            )
            final_damage_components.append(
                DamageComponentResult(
                    damage_type=rage_damage_type,
                    raw_rolls=[],
                    adjusted_rolls=[],
                    subtotal=0,
                    flat_modifier=rage_damage_bonus,
                    total_damage=rage_damage_bonus,
                )
            )
        if can_apply_sneak_attack(state, attacker, target, weapon, mode):
            sneak_attack_component = roll_sneak_attack_component(state, get_sneak_attack_d6_count(attacker))
            if sneak_attack_component:
                final_damage_components.append(
                    DamageComponentResult(
                        damage_type=sneak_attack_component.damage_type,
                        raw_rolls=list(sneak_attack_component.raw_rolls),
                        adjusted_rolls=list(sneak_attack_component.adjusted_rolls),
                        subtotal=sneak_attack_component.subtotal,
                        flat_modifier=0,
                        total_damage=sneak_attack_component.subtotal * critical_multiplier,
                    )
                )
        total_damage = sum(component.total_damage for component in final_damage_components)

        damage_result = apply_damage(state, resolved_target_id, final_damage_components, critical)
        hp_delta = damage_result.hp_delta
        resisted_damage = damage_result.resisted_damage
        amplified_damage = damage_result.amplified_damage
        temporary_hp_absorbed = damage_result.temporary_hp_absorbed
        final_damage_to_hp = damage_result.final_damage_to_hp
        undead_fortitude_triggered = damage_result.undead_fortitude_triggered
        undead_fortitude_success = damage_result.undead_fortitude_success
        undead_fortitude_dc = damage_result.undead_fortitude_dc
        undead_fortitude_bypass_reason = damage_result.undead_fortitude_bypass_reason
        condition_deltas.extend(damage_result.condition_deltas)

        mastery_applied, mastery_notes, mastery_condition_deltas = apply_mastery(
            state, args.attacker_id, resolved_target_id, weapon.mastery, True, damage_result.final_total_damage
        )
        condition_deltas.extend(mastery_condition_deltas)
        attack_riders_applied, attack_rider_condition_deltas = apply_on_hit_effects(
            state,
            args.attacker_id,
            resolved_target_id,
            weapon,
            True,
        )
        if not attack_riders_applied:
            attack_riders_applied = None
        condition_deltas.extend(attack_rider_condition_deltas)
    elif weapon.mastery == "graze":
        mastery_applied = "graze"
        mastery_notes = f"{target.id} takes {weapon.ability_modifier} graze damage on the miss."
        total_damage = max(0, weapon.ability_modifier)
        final_damage_components = [
            DamageComponentResult(
                damage_type=weapon.damage_type or (weapon.damage_components[0].damage_type if weapon.damage_components else "damage"),
                raw_rolls=[],
                adjusted_rolls=[],
                subtotal=0,
                flat_modifier=weapon.ability_modifier,
                total_damage=total_damage,
            )
        ]
        damage_result = apply_damage(state, resolved_target_id, final_damage_components, False)
        hp_delta = damage_result.hp_delta
        resisted_damage = damage_result.resisted_damage
        amplified_damage = damage_result.amplified_damage
        temporary_hp_absorbed = damage_result.temporary_hp_absorbed
        final_damage_to_hp = damage_result.final_damage_to_hp
        undead_fortitude_triggered = damage_result.undead_fortitude_triggered
        undead_fortitude_success = damage_result.undead_fortitude_success
        undead_fortitude_dc = damage_result.undead_fortitude_dc
        undead_fortitude_bypass_reason = damage_result.undead_fortitude_bypass_reason
        condition_deltas.extend(damage_result.condition_deltas)

    if sap_consumed > 0:
        condition_deltas.append(f"{args.attacker_id}'s sap disadvantage is consumed on this attack roll.")
    if vex_consumed:
        condition_deltas.append(f"{args.attacker_id}'s vex advantage is consumed on this attack roll.")
    if harried_consumed:
        condition_deltas.append(f"{args.target_id}'s harried defense is consumed on this attack roll.")

    critical_multiplier = 2 if critical else 1
    hit_label = "critical hit" if critical else "hit" if hit else "miss"
    resolved_totals = {
        "attackMode": mode,
        "selectedRoll": selected_roll,
        "attackTotal": attack_total,
        "targetAc": target_ac,
        "coverAcBonus": attack_context.cover_ac_bonus,
        "distanceSquares": attack_context.distance_squares,
        "distanceFeet": attack_context.distance_feet,
        "hit": hit,
        "critical": critical,
        "sapConsumed": sap_consumed,
        "opportunityAttack": args.is_opportunity_attack or False,
        "originalTargetId": args.target_id,
        "attackReaction": attack_reaction,
        "reactionActorId": reaction_actor_id,
        "shieldAcBonus": get_shield_ac_bonus(target),
        "targetWasBloodiedBeforeHit": target_was_bloodied_before_hit,
    }
    if defense_reaction_data:
        resolved_totals.update(defense_reaction_data)
    if undead_fortitude_triggered:
        resolved_totals["undeadFortitudeTriggered"] = True
        resolved_totals["undeadFortitudeSuccess"] = undead_fortitude_success
        if undead_fortitude_dc is not None:
            resolved_totals["undeadFortitudeDc"] = undead_fortitude_dc
        if undead_fortitude_bypass_reason is not None:
            resolved_totals["undeadFortitudeBypassReason"] = undead_fortitude_bypass_reason

    event = CombatEvent(
        **event_base(state, args.attacker_id),
        target_ids=[resolved_target_id],
        event_type="attack",
        raw_rolls={
            "attackRolls": attack_rolls,
            "advantageSources": advantage_sources,
            "disadvantageSources": disadvantage_sources,
        },
        resolved_totals=resolved_totals,
        movement_details=args.movement_details,
        damage_details=DamageDetails(
            weapon_id=args.weapon_id,
            weapon_name=weapon.display_name,
            damage_components=final_damage_components,
            primary_candidate=primary_candidate,
            savage_candidate=savage_candidate,
            chosen_candidate=chosen_candidate,
            critical_applied=critical,
            critical_multiplier=critical_multiplier,
            flat_modifier=sum(component.flat_modifier for component in final_damage_components),
            advantage_bonus_candidate=advantage_bonus_candidate,
            mastery_applied=mastery_applied,
            mastery_notes=mastery_notes,
            attack_riders_applied=attack_riders_applied,
            total_damage=total_damage,
            resisted_damage=resisted_damage,
            amplified_damage=amplified_damage or None,
            temporary_hp_absorbed=temporary_hp_absorbed,
            final_damage_to_hp=final_damage_to_hp,
            hp_delta=hp_delta,
        ),
        condition_deltas=condition_deltas,
        text_summary=(
            f"{'Opportunity attack: ' if args.is_opportunity_attack else ''}"
            f"{args.attacker_id} attacks {resolved_target_id} with {weapon.display_name}: "
            f"{hit_label}"
            f"{f' for {total_damage} damage' if total_damage > 0 else ''}"
            f"{f' ({resisted_damage} resisted)' if resisted_damage > 0 else ''}"
            f"{f' (+{amplified_damage} vulnerability)' if amplified_damage > 0 else ''}"
            f"{f' ({temporary_hp_absorbed} temp HP absorbed)' if temporary_hp_absorbed > 0 else ''}."
        ),
    )
    return event, savage_attacker_consumed


def should_commit_reckless_attack(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    weapon: WeaponProfile,
) -> bool:
    attacker = state.units[attacker_id]
    if not attacker._reckless_attack_available_this_turn:
        return False
    if not unit_has_feature(attacker, "reckless_attack"):
        return False
    if state.player_behavior != "smart":
        return False
    if weapon.kind != "melee" or weapon.attack_ability != "str":
        return False
    if unit_has_reckless_attack_effect(attacker):
        return False

    base_mode, _, _ = get_attack_mode(state, attacker, attacker_id, state.units[target_id], target_id, weapon)
    return base_mode != "advantage"


def maybe_commit_reckless_attack(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    weapon_id: str,
) -> CombatEvent | None:
    attacker = state.units[attacker_id]
    weapon = attacker.attacks.get(weapon_id)
    if not weapon:
        attacker._reckless_attack_available_this_turn = False
        return None

    should_commit = should_commit_reckless_attack(state, attacker_id, target_id, weapon)
    # The choice is locked to the first attack roll on the barbarian's turn.
    attacker._reckless_attack_available_this_turn = False
    if not should_commit:
        return None

    attacker.temporary_effects = [
        effect
        for effect in attacker.temporary_effects
        if not (effect.kind == "reckless_attack" and effect.source_id == attacker_id)
    ]
    attacker.temporary_effects.append(
        RecklessAttackEffect(kind="reckless_attack", source_id=attacker_id, expires_at_turn_start_of=attacker_id)
    )

    return CombatEvent(
        **event_base(state, attacker_id),
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={"recklessAttack": True},
        movement_details=None,
        damage_details=None,
        condition_deltas=[f"{attacker_id} uses Reckless Attack."],
        text_summary=(
            f"{attacker_id} uses Reckless Attack, gaining advantage on Strength attacks "
            f"and granting attackers advantage until the next turn."
        ),
    )
