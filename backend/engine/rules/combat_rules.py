from __future__ import annotations

from dataclasses import dataclass

from backend.content.class_progressions import (
    get_monk_focus_points_max,
    get_monk_martial_arts_die_sides,
    get_proficiency_bonus,
    get_progression_scalar,
)
from backend.content.cunning_strike_definitions import (
    get_cunning_strike_definition,
    get_cunning_strike_save_dc,
    unit_has_cunning_strike,
)
from backend.content.enemies import unit_has_reaction, unit_has_trait
from backend.content.feature_definitions import unit_has_feature, unit_has_granted_action
from backend.content.maneuver_definitions import (
    get_maneuver_definition,
    get_maneuver_save_dc,
    get_superiority_die_sides,
    spend_superiority_die,
    unit_has_maneuver,
)
from backend.content.spell_definitions import get_spell_definition
from backend.engine.models.state import (
    AttackId,
    AttackMode,
    AttackRiderType,
    BlessedEffect,
    CombatEvent,
    ConcentrationEffect,
    DamageCandidate,
    DamageComponentResult,
    DamageDetails,
    DivineFavorEffect,
    DodgingEffect,
    EncounterState,
    GrappledEffect,
    GridPosition,
    HaltedEffect,
    HarriedEffect,
    HasteEffect,
    HasteLethargyEffect,
    HeroismEffect,
    HiddenEffect,
    MasteryType,
    MovementDetails,
    PoisonedEffect,
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
)
from backend.engine.rules.combat_support import (
    AttackRollOverrides,
    DamageApplicationResult,
    ResolveSavingThrowArgs,
    SavingThrowOverrides,
    apply_healing_to_unit,
    attach_damage_result_event_fields,
    build_final_damage_components,
    build_skip_event,
    event_base,
    get_ability_modifier,
    get_unit_spell_save_dc,
    spend_spell_slot,
    unit_has_combat_spell,
)
from backend.engine.rules.combat_support import (
    get_remaining_spell_slots as get_remaining_spell_slots,
)
from backend.engine.rules.combat_support import (
    get_spell_save_dc as get_spell_save_dc,
)
from backend.engine.rules.combat_support import (
    get_spellcasting_ability as get_spellcasting_ability,
)
from backend.engine.rules.combat_support import (
    resolve_spell_ability as resolve_spell_ability,
)
from backend.engine.rules.spatial import (
    GRID_SIZE,
    build_position_index,
    can_attempt_hide_from_position,
    chebyshev_distance,
    get_attack_context,
    get_hide_passive_perception_dc,
    get_line_squares,
    get_min_chebyshev_distance_between_footprints,
    get_occupied_squares_for_position,
    get_unit_footprint,
    has_line_of_sight_between_units,
    is_active_grapple,
)
from backend.engine.utils.helpers import unit_can_take_reactions, unit_sort_key
from backend.engine.utils.rng import roll_die


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
        maneuver_id: str | None = None,
        precision_max_miss_margin: int | None = None,
        great_weapon_master_eligible: bool = False,
        cunning_strike_id: str | None = None,
    ) -> None:
        self.attacker_id = attacker_id
        self.target_id = target_id
        self.weapon_id = weapon_id
        self.savage_attacker_available = savage_attacker_available
        self.movement_details = movement_details
        self.is_opportunity_attack = is_opportunity_attack
        self.overrides = overrides
        self.omit_ability_modifier_damage = omit_ability_modifier_damage
        self.maneuver_id = maneuver_id
        self.precision_max_miss_margin = precision_max_miss_margin
        self.great_weapon_master_eligible = great_weapon_master_eligible
        self.cunning_strike_id = cunning_strike_id


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


def unit_is_steady_aiming(unit: UnitState) -> bool:
    return unit._steady_aim_active_this_turn


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


def unit_has_no_reactions_effect(unit: UnitState) -> bool:
    return any(effect.kind == "no_reactions" for effect in unit.temporary_effects)


def unit_has_shield_effect(unit: UnitState) -> bool:
    return any(effect.kind == "shield" for effect in unit.temporary_effects)


def get_shield_ac_bonus(unit: UnitState) -> int:
    return sum(
        effect.ac_bonus
        for effect in unit.temporary_effects
        if effect.kind in {"shield", "shield_of_faith", "haste"}
    )


def get_shield_of_faith_ac_bonus(unit: UnitState, source_id: str | None = None) -> int:
    return sum(
        effect.ac_bonus
        for effect in unit.temporary_effects
        if effect.kind == "shield_of_faith" and (source_id is None or effect.source_id == source_id)
    )


def get_active_concentration_effect(unit: UnitState, spell_id: str | None = None) -> ConcentrationEffect | None:
    for effect in unit.temporary_effects:
        if effect.kind != "concentration":
            continue
        if spell_id is not None and effect.spell_id != spell_id:
            continue
        return effect
    return None


def unit_is_concentrating_on(unit: UnitState, spell_id: str) -> bool:
    return get_active_concentration_effect(unit, spell_id) is not None


def get_active_divine_favor_effect(unit: UnitState) -> DivineFavorEffect | None:
    if not unit_is_concentrating_on(unit, "divine_favor"):
        return None
    for effect in unit.temporary_effects:
        if effect.kind == "divine_favor":
            return effect
    return None


def get_active_heroism_effect(state: EncounterState, unit: UnitState) -> HeroismEffect | None:
    for effect in unit.temporary_effects:
        if effect.kind != "heroism":
            continue
        caster = state.units.get(effect.source_id)
        if caster and unit_is_concentrating_on(caster, "heroism"):
            return effect
    return None


def get_active_haste_effect(state: EncounterState, unit: UnitState) -> HasteEffect | None:
    for effect in unit.temporary_effects:
        if effect.kind != "haste":
            continue
        caster = state.units.get(effect.source_id)
        if caster and unit_is_concentrating_on(caster, "haste"):
            return effect
    return None


def get_haste_ac_bonus(unit: UnitState, source_id: str | None = None) -> int:
    return sum(
        effect.ac_bonus
        for effect in unit.temporary_effects
        if effect.kind == "haste" and (source_id is None or effect.source_id == source_id)
    )


def unit_is_haste_lethargic(unit: UnitState) -> bool:
    return any(effect.kind == "haste_lethargy" for effect in unit.temporary_effects)


def unit_is_frightened_by_source(state: EncounterState, unit: UnitState, source_id: str) -> bool:
    source = state.units.get(source_id)
    return bool(
        source
        and source.current_hp > 0
        and not source.conditions.dead
        and any(effect.kind == "frightened_by" and effect.source_id == source_id for effect in unit.temporary_effects)
        and has_line_of_sight_between_units(state, unit.id, source_id)
    )


def unit_is_frightened_immune(state: EncounterState, unit: UnitState) -> bool:
    return "frightened" in unit.condition_immunities or get_active_heroism_effect(state, unit) is not None


def clear_frightened_effects(unit: UnitState, source_id: str | None = None) -> int:
    original_count = len(unit.temporary_effects)
    unit.temporary_effects = [
        effect
        for effect in unit.temporary_effects
        if not (effect.kind == "frightened_by" and (source_id is None or effect.source_id == source_id))
    ]
    return original_count - len(unit.temporary_effects)


def unit_projects_aura_of_authority(unit: UnitState) -> bool:
    if not unit.position or unit.current_hp <= 0 or unit.conditions.dead or unit.conditions.unconscious:
        return False
    try:
        return unit_has_trait(unit, "aura_of_authority")
    except ValueError:
        return False


def unit_benefits_from_aura_of_authority(state: EncounterState, unit: UnitState) -> bool:
    if not unit.position or unit.current_hp <= 0 or unit.conditions.dead or unit.conditions.unconscious:
        return False

    for source in state.units.values():
        if source.faction != unit.faction or not unit_projects_aura_of_authority(source):
            continue
        distance = get_min_chebyshev_distance_between_footprints(
            source.position,
            get_unit_footprint(source),
            unit.position,
            get_unit_footprint(unit),
        )
        if distance <= 2:
            return True
    return False


def unit_is_halted(unit: UnitState) -> bool:
    return any(effect.kind == "halted" for effect in unit.temporary_effects)


def apply_sentinel_halt(
    state: EncounterState,
    attacker: UnitState,
    target: UnitState,
    *,
    hit: bool,
    is_opportunity_attack: bool | None,
) -> bool:
    if not hit or not is_opportunity_attack or not unit_has_feature(attacker, "sentinel"):
        return False
    if target.conditions.dead or target.current_hp <= 0 or target.conditions.unconscious:
        return False

    active_actor_id = (
        state.initiative_order[state.active_combatant_index]
        if 0 <= state.active_combatant_index < len(state.initiative_order)
        else target.id
    )
    target.temporary_effects = [
        effect
        for effect in target.temporary_effects
        if not (
            effect.kind == "halted"
            and effect.source_id == attacker.id
            and effect.expires_at_turn_end_of == active_actor_id
        )
    ]
    target.temporary_effects.append(
        HaltedEffect(kind="halted", source_id=attacker.id, expires_at_turn_end_of=active_actor_id)
    )
    recalculate_effective_speed_for_unit(target)
    return True


def get_active_bless_effect(state: EncounterState, unit: UnitState) -> BlessedEffect | None:
    for effect in unit.temporary_effects:
        if effect.kind != "blessed":
            continue
        source = state.units.get(effect.source_id)
        if source and unit_is_concentrating_on(source, "bless"):
            return effect
    return None


def roll_bless_bonus(
    state: EncounterState,
    unit: UnitState,
    override_roll: int | None = None,
) -> tuple[int, list[int], str | None]:
    bless_effect = get_active_bless_effect(state, unit)
    if not bless_effect:
        return 0, [], None
    roll = pull_die(state, 4, override_roll)
    return roll, [roll], bless_effect.source_id


def end_concentration(state: EncounterState, caster_id: str, *, reason: str | None = None) -> list[str]:
    caster = state.units.get(caster_id)
    if not caster:
        return []
    concentration_effects = [effect for effect in caster.temporary_effects if effect.kind == "concentration"]
    if not concentration_effects:
        return []

    spell_ids = {effect.spell_id for effect in concentration_effects}
    caster.temporary_effects = [effect for effect in caster.temporary_effects if effect.kind != "concentration"]
    removed_blessed_targets: list[str] = []
    removed_shield_of_faith_targets: list[str] = []
    removed_heroism_targets: list[str] = []
    removed_haste_targets: list[str] = []
    removed_frightened_targets: list[str] = []
    divine_favor_removed = False
    if "bless" in spell_ids:
        for unit in state.units.values():
            original_count = len(unit.temporary_effects)
            unit.temporary_effects = [
                effect
                for effect in unit.temporary_effects
                if not (effect.kind == "blessed" and effect.source_id == caster_id)
            ]
            if len(unit.temporary_effects) != original_count:
                removed_blessed_targets.append(unit.id)
    if "shield_of_faith" in spell_ids:
        for unit in state.units.values():
            original_count = len(unit.temporary_effects)
            unit.temporary_effects = [
                effect
                for effect in unit.temporary_effects
                if not (effect.kind == "shield_of_faith" and effect.source_id == caster_id)
            ]
            if len(unit.temporary_effects) != original_count:
                removed_shield_of_faith_targets.append(unit.id)
    if "heroism" in spell_ids:
        for unit in state.units.values():
            original_count = len(unit.temporary_effects)
            unit.temporary_effects = [
                effect
                for effect in unit.temporary_effects
                if not (effect.kind == "heroism" and effect.source_id == caster_id)
            ]
            if len(unit.temporary_effects) != original_count:
                removed_heroism_targets.append(unit.id)
    if "haste" in spell_ids:
        for unit in state.units.values():
            original_count = len(unit.temporary_effects)
            unit.temporary_effects = [
                effect
                for effect in unit.temporary_effects
                if not (effect.kind == "haste" and effect.source_id == caster_id)
            ]
            if len(unit.temporary_effects) != original_count:
                removed_haste_targets.append(unit.id)
                recalculate_effective_speed_for_unit(unit)
                if unit.current_hp > 0 and not unit.conditions.dead:
                    unit.temporary_effects.append(
                        HasteLethargyEffect(
                            kind="haste_lethargy",
                            source_id=caster_id,
                            expires_at_turn_end_of=unit.id,
                        )
                    )
                    recalculate_effective_speed_for_unit(unit)
    if "fear" in spell_ids:
        for unit in state.units.values():
            removed_count = clear_frightened_effects(unit, caster_id)
            if removed_count:
                removed_frightened_targets.append(unit.id)
    if "divine_favor" in spell_ids:
        original_count = len(caster.temporary_effects)
        caster.temporary_effects = [
            effect
            for effect in caster.temporary_effects
            if not (effect.kind == "divine_favor" and effect.source_id == caster_id)
        ]
        divine_favor_removed = len(caster.temporary_effects) != original_count

    summary = reason or f"{caster_id}'s concentration ends."
    if removed_blessed_targets:
        summary = f"{summary} Bless ends on {', '.join(sorted(removed_blessed_targets, key=unit_sort_key))}."
    if removed_shield_of_faith_targets:
        summary = (
            f"{summary} Shield of Faith ends on "
            f"{', '.join(sorted(removed_shield_of_faith_targets, key=unit_sort_key))}."
        )
    if removed_heroism_targets:
        summary = f"{summary} Heroism ends on {', '.join(sorted(removed_heroism_targets, key=unit_sort_key))}."
    if removed_haste_targets:
        summary = f"{summary} Haste ends on {', '.join(sorted(removed_haste_targets, key=unit_sort_key))}; lethargy begins."
    if removed_frightened_targets:
        summary = f"{summary} Fear ends on {', '.join(sorted(removed_frightened_targets, key=unit_sort_key))}."
    if divine_favor_removed:
        summary = f"{summary} Divine Favor ends on {caster_id}."
    return [summary]


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


def choose_selectable_damage_type(selectable_damage_types: list[str], target: UnitState) -> str:
    vulnerable_choices: list[str] = []
    unmitigated_choices: list[str] = []
    nonimmune_choices: list[str] = []

    for damage_type in selectable_damage_types:
        immune, resistant, vulnerable = get_damage_defense_flags(target, damage_type)
        if vulnerable and not resistant and not immune:
            vulnerable_choices.append(damage_type)
        if not immune and not resistant:
            unmitigated_choices.append(damage_type)
        if not immune:
            nonimmune_choices.append(damage_type)

    if vulnerable_choices:
        return vulnerable_choices[0]
    if unmitigated_choices:
        return unmitigated_choices[0]
    if nonimmune_choices:
        return nonimmune_choices[0]
    return selectable_damage_types[0]


def resolve_selectable_damage_weapon(weapon: WeaponProfile, target: UnitState) -> WeaponProfile:
    if not weapon.selectable_damage_types:
        return weapon
    selected_damage_type = choose_selectable_damage_type(weapon.selectable_damage_types, target)
    return weapon.model_copy(update={"damage_type": selected_damage_type})


def weapon_qualifies_for_sneak_attack(weapon: WeaponProfile) -> bool:
    return weapon.kind == "ranged" or weapon.finesse is True


def get_sneak_attack_d6_count(attacker: UnitState) -> int:
    if not unit_has_feature(attacker, "sneak_attack"):
        return 0
    if not attacker.class_id or attacker.level is None:
        return 0
    return get_progression_scalar(attacker.class_id, attacker.level, "sneak_attack_d6", 0)


def unit_has_not_taken_turn_this_combat_round(state: EncounterState, unit_id: str) -> bool:
    if state.round != 1:
        return False
    try:
        unit_index = state.initiative_order.index(unit_id)
    except ValueError:
        return False
    return unit_index > state.active_combatant_index


def can_apply_assassinate_advantage(state: EncounterState, attacker: UnitState, target_id: str) -> bool:
    return bool(
        unit_has_feature(attacker, "assassinate")
        and state.round == 1
        and unit_has_not_taken_turn_this_combat_round(state, target_id)
    )


def get_assassinate_damage_bonus(state: EncounterState, attacker: UnitState) -> int:
    if not unit_has_feature(attacker, "assassinate") or state.round != 1:
        return 0
    return attacker.level or 0


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


def unit_is_poisoned(unit: UnitState) -> bool:
    return any(effect.kind == "poisoned" for effect in unit.temporary_effects)


def get_cunning_strike_damage_type(weapon: WeaponProfile) -> str:
    return weapon.damage_type or (weapon.damage_components[0].damage_type if weapon.damage_components else "damage")


def can_apply_cunning_strike(
    attacker: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    strike_id: str | None,
    sneak_attack_dice: int,
) -> bool:
    if not strike_id:
        return False
    if not unit_has_feature(attacker, "cunning_strike") or not unit_has_cunning_strike(attacker, strike_id):
        return False
    if sneak_attack_dice <= 0:
        return False

    definition = get_cunning_strike_definition(strike_id)
    if sneak_attack_dice < definition.cost_d6:
        return False

    if strike_id == "poison":
        return "poisoned" not in target.condition_immunities and not unit_is_poisoned(target)
    if strike_id == "trip":
        return (
            not target.conditions.dead
            and target.current_hp > 0
            and not target.conditions.unconscious
            and not target.conditions.prone
            and is_within_max_target_size(target.size_category, definition.max_target_size)
        )
    if strike_id == "withdraw":
        return True
    return False


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


def can_use_battle_master_maneuver(unit: UnitState, maneuver_id: str) -> bool:
    return (
        unit.current_hp > 0
        and not unit.conditions.dead
        and not unit.conditions.unconscious
        and unit_has_maneuver(unit, maneuver_id)
        and get_superiority_die_sides(unit) > 0
        and unit.resources.superiority_dice > 0
    )


def get_great_weapon_master_damage_bonus(attacker: UnitState, weapon: WeaponProfile, eligible: bool) -> int:
    if not eligible:
        return 0
    if not unit_has_feature(attacker, "great_weapon_master"):
        return 0
    if weapon.kind != "melee" or weapon.two_handed is not True:
        return 0
    if attacker.level is None or attacker.level <= 0:
        return 0
    return get_proficiency_bonus(attacker.level)


def can_attempt_precision_attack(
    attacker: UnitState,
    *,
    maneuver_intent: str | None,
    max_miss_margin: int | None,
    hit: bool,
    natural_one: bool,
    attack_total: int,
    target_ac: int,
) -> bool:
    if maneuver_intent not in {"precision_attack", "battle_master_auto"} and not (
        maneuver_intent == "riposte" and max_miss_margin is not None
    ):
        return False
    if hit or natural_one:
        return False
    miss_margin = target_ac - attack_total
    die_sides = get_superiority_die_sides(attacker)
    allowed_margin = die_sides if max_miss_margin is None else min(die_sides, max(0, max_miss_margin))
    return 1 <= miss_margin <= allowed_margin and can_use_battle_master_maneuver(attacker, "precision_attack")


def can_attempt_trip_attack(
    attacker: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    *,
    maneuver_intent: str | None,
    hit: bool,
    is_opportunity_attack: bool | None,
) -> bool:
    if maneuver_intent not in {"trip_attack", "battle_master_auto"}:
        return False
    if not hit or is_opportunity_attack:
        return False
    if weapon.kind != "melee":
        return False
    if target.conditions.dead or target.current_hp <= 0 or target.conditions.unconscious or target.conditions.prone:
        return False
    if not is_within_max_target_size(target.size_category, get_maneuver_definition("trip_attack").max_target_size):
        return False
    return can_use_battle_master_maneuver(attacker, "trip_attack")


def roll_superiority_damage_component(
    state: EncounterState,
    attacker: UnitState,
    weapon: WeaponProfile,
    critical_multiplier: int,
    override_rolls: list[int] | None = None,
) -> tuple[int, DamageComponentResult]:
    roll = pull_die(state, get_superiority_die_sides(attacker), override_rolls.pop(0) if override_rolls else None)
    damage_type = weapon.damage_type or (
        weapon.damage_components[0].damage_type if weapon.damage_components else "damage"
    )
    return (
        roll,
        DamageComponentResult(
            damage_type=damage_type,
            raw_rolls=[roll],
            adjusted_rolls=[roll],
            subtotal=roll,
            flat_modifier=0,
            total_damage=roll * critical_multiplier,
        ),
    )


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
    if unit_is_halted(unit):
        unit.effective_speed = 0
        return

    if unit_is_haste_lethargic(unit):
        unit.effective_speed = 0
        return

    if any(effect.kind == "speed_zero" for effect in unit.temporary_effects):
        unit.effective_speed = 0
        return

    if any(effect.kind == "restrained_by" for effect in unit.temporary_effects):
        unit.effective_speed = 0
        return

    slow_penalty = sum(effect.penalty for effect in unit.temporary_effects if effect.kind == "slow")
    speed_bonus = max(0, unit.longstrider_speed_bonus)
    haste_multiplier = max(
        (effect.speed_multiplier for effect in unit.temporary_effects if effect.kind == "haste"),
        default=1,
    )
    unit.effective_speed = max(0, ((unit.speed + speed_bonus) * haste_multiplier) - min(10, slow_penalty))


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

    actor = state.units.get(actor_id)
    concentration = get_active_concentration_effect(actor) if actor else None
    if concentration:
        concentration.remaining_rounds -= 1
        if concentration.remaining_rounds <= 0:
            condition_deltas = end_concentration(
                state,
                actor_id,
                reason=f"{actor_id}'s concentration on {concentration.spell_id} ends after reaching its duration limit.",
            )
            events.append(
                CombatEvent(
                    **event_base(state, actor_id),
                    target_ids=[actor_id],
                    event_type="effect_expired",
                    raw_rolls={},
                    resolved_totals={
                        "expiredCount": 1,
                        "unitId": actor_id,
                        "spellId": concentration.spell_id,
                    },
                    movement_details=None,
                    damage_details=None,
                    condition_deltas=condition_deltas,
                    text_summary=f"{actor_id}'s concentration on {concentration.spell_id} expires.",
                )
            )

    return events


def get_saving_throw_mode(
    actor: UnitState,
    ability: str,
    base_advantage_sources: list[str] | None = None,
    base_disadvantage_sources: list[str] | None = None,
    *,
    state: EncounterState | None = None,
) -> tuple[AttackMode, list[str], list[str]]:
    advantage_sources = list(base_advantage_sources or [])
    disadvantage_sources = list(base_disadvantage_sources or [])

    if ability == "dex" and has_danger_sense(actor):
        advantage_sources.append("danger_sense")

    if ability == "dex" and state and get_active_haste_effect(state, actor):
        advantage_sources.append("haste")

    if actor.faction == "goblins" and unit_has_trait(actor, "bloodied_frenzy") and unit_is_bloodied(actor):
        advantage_sources.append("bloodied_frenzy")

    if state and "aura_of_authority" not in advantage_sources and unit_benefits_from_aura_of_authority(state, actor):
        advantage_sources.append("aura_of_authority")

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
        state=state,
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
    bless_bonus, bless_rolls, bless_source_id = roll_bless_bonus(state, actor)
    total = selected_roll + modifier + bless_bonus
    success = total >= args.dc
    legendary_resistance_applied = False
    if not success:
        try:
            has_legendary_resistance = unit_has_trait(actor, "legendary_resistance")
        except ValueError:
            has_legendary_resistance = False
        if has_legendary_resistance and actor.resource_pools.get("legendary_resistance_uses", 0) > 0:
            actor.resource_pools["legendary_resistance_uses"] -= 1
            legendary_resistance_applied = True
            success = True
    raw_rolls = {
        "savingThrowRolls": save_rolls,
        "advantageSources": advantage_sources,
        "disadvantageSources": disadvantage_sources,
    }
    if bless_rolls:
        raw_rolls["blessRolls"] = bless_rolls
    resolved_totals = {
        "ability": args.ability,
        "saveMode": mode,
        "selectedRoll": selected_roll,
        "modifier": modifier,
        "total": total,
        "dc": args.dc,
        "success": success,
    }
    if bless_bonus:
        resolved_totals["blessBonus"] = bless_bonus
        resolved_totals["blessSourceId"] = bless_source_id
    condition_deltas = []
    if legendary_resistance_applied:
        resolved_totals["legendaryResistanceApplied"] = True
        resolved_totals["legendaryResistanceUsesRemaining"] = actor.resource_pools.get("legendary_resistance_uses", 0)
        condition_deltas.append(f"{args.actor_id} uses Legendary Resistance to succeed instead.")

    return CombatEvent(
        **event_base(state, args.actor_id),
        target_ids=[args.actor_id],
        event_type="saving_throw",
        raw_rolls=raw_rolls,
        resolved_totals=resolved_totals,
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=(
            f"{args.actor_id} makes a {args.ability.upper()} save for {args.reason}: "
            f"{'success' if success else 'failure'} with {total} against DC {args.dc}"
            f"{' using Legendary Resistance' if legendary_resistance_applied else ''}."
        ),
    )


def resolve_poisoned_end_of_turn_save(state: EncounterState, actor_id: str) -> CombatEvent | None:
    actor = state.units[actor_id]
    poisoned_effects = [
        effect
        for effect in actor.temporary_effects
        if effect.kind == "poisoned" and getattr(effect, "expires_at_turn_end_of", None) is None
    ]
    if not poisoned_effects or actor.conditions.dead or actor.current_hp <= 0:
        return None

    effect = poisoned_effects[0]
    save_event = resolve_saving_throw(
        state,
        ResolveSavingThrowArgs(
            actor_id=actor_id,
            ability="con",
            dc=effect.save_dc,
            reason="Poisoned",
        ),
    )
    success = bool(save_event.resolved_totals["success"])

    if success:
        actor.temporary_effects = [active_effect for active_effect in actor.temporary_effects if active_effect is not effect]
        save_event.condition_deltas.append(f"{actor_id} is no longer poisoned.")
        save_event.resolved_totals["poisonedEnded"] = True
    else:
        effect.remaining_rounds -= 1
        if effect.remaining_rounds <= 0:
            actor.temporary_effects = [active_effect for active_effect in actor.temporary_effects if active_effect is not effect]
            save_event.condition_deltas.append(f"{actor_id}'s poison expires.")
            save_event.resolved_totals["poisonedEnded"] = True
            save_event.resolved_totals["poisonExpired"] = True
        else:
            save_event.condition_deltas.append(f"{actor_id} remains poisoned.")
            save_event.resolved_totals["poisonedEnded"] = False
            save_event.resolved_totals["poisonRemainingRounds"] = effect.remaining_rounds

    return save_event


def is_natures_wrath_restrained(unit: UnitState, source_id: str | None = None) -> bool:
    return any(
        effect.kind == "restrained_by"
        and effect.save_ends
        and effect.save_ability == "str"
        and (source_id is None or effect.source_id == source_id)
        for effect in unit.temporary_effects
    )


def get_natures_wrath_legal_targets(
    state: EncounterState,
    actor_id: str,
    target_ids: list[str],
) -> list[UnitState]:
    actor = state.units[actor_id]
    if not actor.position:
        return []

    actor_footprint = get_unit_footprint(actor)
    legal_targets: list[UnitState] = []
    seen_target_ids: set[str] = set()
    for target_id in target_ids:
        if target_id in seen_target_ids:
            continue
        seen_target_ids.add(target_id)
        target = state.units.get(target_id)
        if not target or target.faction == actor.faction:
            continue
        if target.conditions.dead or target.conditions.unconscious or target.current_hp <= 0 or not target.position:
            continue
        if is_natures_wrath_restrained(target):
            continue
        distance = get_min_chebyshev_distance_between_footprints(
            actor.position,
            actor_footprint,
            target.position,
            get_unit_footprint(target),
        )
        if distance <= 3:
            legal_targets.append(target)

    return sorted(legal_targets, key=lambda unit: unit_sort_key(unit.id))


def attempt_natures_wrath(
    state: EncounterState,
    actor_id: str,
    target_ids: list[str],
    overrides: SavingThrowOverrides | None = None,
) -> CombatEvent:
    actor = state.units[actor_id]
    if (
        actor.conditions.dead
        or actor.conditions.unconscious
        or actor.current_hp <= 0
        or not unit_has_granted_action(actor, "natures_wrath")
    ):
        return create_skip_event(state, actor_id, "Nature's Wrath is not available.")

    legal_targets = get_natures_wrath_legal_targets(state, actor_id, target_ids)
    if not legal_targets:
        return create_skip_event(state, actor_id, "Nature's Wrath has no legal targets.")
    if not actor.resources.spend_pool("channel_divinity", 1):
        return create_skip_event(state, actor_id, "No Channel Divinity uses remain.")

    save_dc = get_unit_spell_save_dc(actor)
    save_overrides = SavingThrowOverrides(save_rolls=list(overrides.save_rolls if overrides else []))
    raw_save_rolls: list[int] = []
    save_totals: list[int] = []
    restrained_target_ids: list[str] = []
    successful_save_target_ids: list[str] = []
    condition_deltas: list[str] = []

    for target in legal_targets:
        save_roll = pull_die(state, 20, save_overrides.save_rolls.pop(0) if save_overrides.save_rolls else None)
        save_total = save_roll + get_ability_modifier(target, "str")
        raw_save_rolls.append(save_roll)
        save_totals.append(save_total)

        if save_total >= save_dc:
            successful_save_target_ids.append(target.id)
            condition_deltas.append(f"{target.id} resists Nature's Wrath.")
            continue

        target.temporary_effects = [
            effect
            for effect in target.temporary_effects
            if not (
                effect.kind == "restrained_by"
                and effect.source_id == actor_id
                and effect.save_ends
                and effect.save_ability == "str"
            )
        ]
        target.temporary_effects.append(
            RestrainedEffect(
                kind="restrained_by",
                source_id=actor_id,
                escape_dc=save_dc,
                save_ability="str",
                save_ends=True,
                remaining_rounds=10,
            )
        )
        recalculate_effective_speed_for_unit(target)
        restrained_target_ids.append(target.id)
        condition_deltas.append(f"{target.id} is restrained by Nature's Wrath (DC {save_dc}).")

    legal_target_ids = [target.id for target in legal_targets]
    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=legal_target_ids,
        event_type="phase_change",
        raw_rolls={"savingThrowRolls": raw_save_rolls},
        resolved_totals={
            "specialAction": "natures_wrath",
            "success": True,
            "saveAbility": "str",
            "saveDc": save_dc,
            "saveTotals": save_totals,
            "affectedTargetIds": legal_target_ids,
            "restrainedTargetIds": restrained_target_ids,
            "successfulSaveTargetIds": successful_save_target_ids,
            "channelDivinityUsesRemaining": actor.resources.channel_divinity_uses,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=(
            f"{actor_id} invokes Nature's Wrath, restraining "
            f"{len(restrained_target_ids)} of {len(legal_target_ids)} targets."
        ),
    )


def resolve_restrained_end_of_turn_save(
    state: EncounterState,
    actor_id: str,
    overrides: SavingThrowOverrides | None = None,
) -> CombatEvent | None:
    actor = state.units[actor_id]
    effects = [
        effect
        for effect in actor.temporary_effects
        if effect.kind == "restrained_by" and effect.save_ends and effect.save_ability
    ]
    if not effects or actor.conditions.dead or actor.current_hp <= 0:
        return None

    effect = effects[0]
    save_event = resolve_saving_throw(
        state,
        ResolveSavingThrowArgs(
            actor_id=actor_id,
            ability=effect.save_ability or "str",
            dc=effect.escape_dc,
            reason="Nature's Wrath",
            overrides=overrides,
        ),
    )
    success = bool(save_event.resolved_totals["success"])
    save_event.resolved_totals["sourceId"] = effect.source_id
    save_event.resolved_totals["restrainedSaveEnds"] = True

    if success:
        actor.temporary_effects = [active_effect for active_effect in actor.temporary_effects if active_effect is not effect]
        recalculate_effective_speed_for_unit(actor)
        save_event.condition_deltas.append(f"{actor_id} breaks free from Nature's Wrath.")
        save_event.resolved_totals["restrainedEnded"] = True
    else:
        if effect.remaining_rounds is not None:
            effect.remaining_rounds -= 1
            save_event.resolved_totals["restrainedRemainingRounds"] = effect.remaining_rounds
        if effect.remaining_rounds is not None and effect.remaining_rounds <= 0:
            actor.temporary_effects = [active_effect for active_effect in actor.temporary_effects if active_effect is not effect]
            recalculate_effective_speed_for_unit(actor)
            save_event.condition_deltas.append(f"{actor_id}'s Nature's Wrath restraint expires.")
            save_event.resolved_totals["restrainedEnded"] = True
            save_event.resolved_totals["restrainedExpired"] = True
        else:
            save_event.condition_deltas.append(f"{actor_id} remains restrained by Nature's Wrath.")
            save_event.resolved_totals["restrainedEnded"] = False

    return save_event


def release_save_ending_restrained_effects_from_source(state: EncounterState, source_id: str) -> list[str]:
    condition_deltas: list[str] = []
    for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id)):
        released = [
            effect
            for effect in unit.temporary_effects
            if effect.kind == "restrained_by" and effect.source_id == source_id and effect.save_ends
        ]
        if not released:
            continue

        unit.temporary_effects = [effect for effect in unit.temporary_effects if effect not in released]
        recalculate_effective_speed_for_unit(unit)
        condition_deltas.append(f"{unit.id} is no longer restrained by {source_id}.")

    return condition_deltas


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


def units_are_touch_reachable(state: EncounterState, actor_id: str, target_id: str) -> bool:
    if actor_id == target_id:
        return True
    actor = state.units[actor_id]
    target = state.units[target_id]
    if not actor.position or not target.position:
        return False
    return (
        get_min_chebyshev_distance_between_footprints(
            actor.position,
            get_unit_footprint(actor),
            target.position,
            get_unit_footprint(target),
        )
        <= 1
    )


def units_are_within_spell_range(state: EncounterState, actor_id: str, target_id: str, range_feet: int) -> bool:
    if actor_id == target_id:
        return True
    actor = state.units[actor_id]
    target = state.units[target_id]
    if not actor.position or not target.position:
        return False
    return (
        get_min_chebyshev_distance_between_footprints(
            actor.position,
            get_unit_footprint(actor),
            target.position,
            get_unit_footprint(target),
        )
        <= range_feet // 5
    )


def get_second_wind_heal_modifier(actor: UnitState) -> int:
    return max(1, actor.level or 1)


def get_second_wind_max_heal(actor: UnitState) -> int:
    return 10 + get_second_wind_heal_modifier(actor)


def attempt_second_wind(state: EncounterState, actor_id: str, override_roll: int | None = None) -> CombatEvent | None:
    actor = state.units[actor_id]
    if not unit_has_feature(actor, "second_wind") or actor.resources.second_wind_uses <= 0 or actor.current_hp <= 0:
        return None

    raw_roll = pull_die(state, 10, override_roll)
    healed = min(actor.max_hp - actor.current_hp, raw_roll + get_second_wind_heal_modifier(actor))
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


def attempt_lay_on_hands(state: EncounterState, actor_id: str, target_id: str | None = None) -> CombatEvent:
    actor = state.units[actor_id]
    resolved_target_id = target_id or actor_id
    target = state.units.get(resolved_target_id)
    if not target:
        return create_skip_event(state, actor_id, "Lay on Hands target is unavailable.")
    if not unit_has_feature(actor, "lay_on_hands"):
        return create_skip_event(state, actor_id, "Lay on Hands is not available.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return create_skip_event(state, actor_id, "Cannot use Lay on Hands while down.")
    if target.conditions.dead:
        return create_skip_event(state, actor_id, "Lay on Hands cannot restore a dead target.")
    if actor.resources.lay_on_hands_points <= 0:
        return create_skip_event(state, actor_id, "No Lay on Hands points remain.")
    if not units_are_touch_reachable(state, actor_id, resolved_target_id):
        return create_skip_event(state, actor_id, "Lay on Hands target is not within touch range.")

    if target.current_hp == 0:
        # Rescue pickups should leave the ally with enough HP to survive incidental follow-up damage.
        intended_healing = max(1, (target.max_hp + 3) // 4)
    else:
        target_half_hp = max(1, (target.max_hp + 1) // 2)
        intended_healing = max(1, target_half_hp - target.current_hp)
    healing_total = min(intended_healing, target.max_hp - target.current_hp, actor.resources.lay_on_hands_points)
    if healing_total <= 0:
        return create_skip_event(state, actor_id, "Lay on Hands target does not need healing.")

    actor.resources.lay_on_hands_points -= healing_total
    healed, condition_deltas = apply_healing_to_unit(target, healing_total)

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[resolved_target_id],
        event_type="heal",
        raw_rolls={},
        resolved_totals={
            "healingTotal": healed,
            "currentHp": target.current_hp,
            "layOnHandsPointsRemaining": actor.resources.lay_on_hands_points,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} uses Lay on Hands on {resolved_target_id}, restoring {healed} HP.",
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


def attempt_steady_aim(state: EncounterState, actor_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    if not unit_has_feature(actor, "steady_aim"):
        return create_skip_event(state, actor_id, "Steady Aim is unavailable.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return create_skip_event(state, actor_id, "Cannot use Steady Aim while down.")

    actor._steady_aim_active_this_turn = True
    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={"steadyAim": True},
        movement_details=None,
        damage_details=None,
        condition_deltas=[f"{actor_id} uses Steady Aim."],
        text_summary=f"{actor_id} uses Steady Aim.",
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


def estimate_damage_after_defenses(target: UnitState, damage_components: list[DamageComponentResult]) -> int:
    total_damage = 0
    for component in damage_components:
        component_damage, _, _ = resolve_damage_component_against_target(target, component)
        total_damage += component_damage
    return total_damage


def estimate_remaining_effective_hp_after_damage(
    target: UnitState,
    damage_components: list[DamageComponentResult],
) -> int:
    damage_after_defenses = estimate_damage_after_defenses(target, damage_components)
    remaining_temporary_hp = max(0, target.temporary_hit_points - damage_after_defenses)
    hp_damage = max(0, damage_after_defenses - target.temporary_hit_points)
    remaining_hp = max(0, target.current_hp - hp_damage)
    return remaining_hp + remaining_temporary_hp


def unit_is_fiend_or_undead(unit: UnitState) -> bool:
    creature_tags = {tag.lower() for tag in unit.creature_tags}
    return "fiend" in creature_tags or "undead" in creature_tags


def get_divine_smite_dice_count(target: UnitState, spell_level: int = 1) -> int:
    return 2 + max(0, spell_level - 1) + int(unit_is_fiend_or_undead(target))


def choose_divine_smite_spell_level(
    attacker: UnitState,
    target: UnitState,
    weapon: WeaponProfile,
    *,
    critical: bool,
    is_opportunity_attack: bool | None,
    maneuver_id: str | None,
    weapon_damage_components: list[DamageComponentResult],
) -> int | None:
    if not unit_has_feature(attacker, "paladins_smite"):
        return None
    if weapon.kind != "melee":
        return None
    if is_opportunity_attack or maneuver_id == "riposte":
        return None
    if attacker._bonus_action_used_this_turn or attacker._bonus_action_reserved_this_turn:
        return None

    has_level_1_slot = attacker.resources.spell_slots_level_1 > 0
    has_level_2_slot = attacker.resources.spell_slots_level_2 > 0
    if not (has_level_1_slot or has_level_2_slot):
        return None

    remaining_effective_hp = estimate_remaining_effective_hp_after_damage(target, weapon_damage_components)
    if remaining_effective_hp <= 0:
        return None
    if critical:
        return 1 if has_level_1_slot else 2

    level_1_average_finishes = remaining_effective_hp * 2 <= get_divine_smite_dice_count(target, 1) * 9
    level_2_average_finishes = remaining_effective_hp * 2 <= get_divine_smite_dice_count(target, 2) * 9

    if has_level_1_slot and level_1_average_finishes:
        return 1
    if has_level_2_slot and level_2_average_finishes and not level_1_average_finishes:
        return 2
    if not has_level_1_slot and has_level_2_slot and level_2_average_finishes:
        return 2

    if has_level_1_slot and not has_level_2_slot and attacker.resources.spell_slots_level_1 >= 2 and remaining_effective_hp <= 12:
        return 1

    return None


def roll_divine_smite_component(
    state: EncounterState,
    target: UnitState,
    spell_level: int,
    critical_multiplier: int,
    override_rolls: list[int] | None = None,
) -> tuple[int, list[int], DamageComponentResult]:
    dice_count = get_divine_smite_dice_count(target, spell_level)
    rolls = [pull_die(state, 8, override_rolls.pop(0) if override_rolls else None) for _ in range(dice_count)]
    subtotal = sum(rolls)
    return (
        dice_count,
        rolls,
        DamageComponentResult(
            damage_type="radiant",
            raw_rolls=list(rolls),
            adjusted_rolls=list(rolls),
            subtotal=subtotal,
            flat_modifier=0,
            total_damage=subtotal * critical_multiplier,
        ),
    )


def roll_divine_favor_component(
    state: EncounterState,
    effect: DivineFavorEffect,
    critical_multiplier: int,
    override_rolls: list[int] | None = None,
) -> tuple[list[int], DamageComponentResult]:
    rolls = [
        pull_die(state, effect.damage_die_sides, override_rolls.pop(0) if override_rolls else None)
        for _ in range(effect.damage_die_count)
    ]
    subtotal = sum(rolls)
    return (
        rolls,
        DamageComponentResult(
            damage_type=effect.damage_type,
            raw_rolls=list(rolls),
            adjusted_rolls=list(rolls),
            subtotal=subtotal,
            flat_modifier=0,
            total_damage=subtotal * critical_multiplier,
        ),
    )


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


def can_use_uncanny_dodge_reaction(target: UnitState, attacker: UnitState | None) -> bool:
    if not unit_has_feature(target, "uncanny_dodge"):
        return False
    if not unit_can_take_reactions(target):
        return False
    if attacker is None or not attacker.position or not target.position:
        return False
    if any(effect.kind == "invisible" for effect in attacker.temporary_effects):
        return False
    return True


def should_use_uncanny_dodge(target: UnitState, incoming_damage: int) -> bool:
    if incoming_damage <= 0:
        return False

    damage_after_temp_hp = max(0, incoming_damage - target.temporary_hit_points)
    if damage_after_temp_hp >= target.current_hp:
        return True
    if target.current_hp * 2 <= target.max_hp:
        return True

    minimum_damage_threshold = max(1, (target.max_hp + 9) // 10)
    return incoming_damage >= minimum_damage_threshold


def maybe_apply_uncanny_dodge(
    state: EncounterState,
    *,
    target: UnitState,
    attacker_id: str | None,
    incoming_damage: int,
    attack_roll_damage: bool,
) -> tuple[int, int, str | None]:
    if not attack_roll_damage or attacker_id is None:
        return incoming_damage, 0, None

    attacker = state.units.get(attacker_id)
    if not can_use_uncanny_dodge_reaction(target, attacker):
        return incoming_damage, 0, None
    if not should_use_uncanny_dodge(target, incoming_damage):
        return incoming_damage, 0, None

    target.reaction_available = False
    reduced_damage = incoming_damage // 2
    return reduced_damage, incoming_damage - reduced_damage, "uncanny_dodge"


def resolve_concentration_after_damage(
    state: EncounterState,
    target_id: str,
    damage_to_hp: int,
    override_rolls: list[int] | None = None,
) -> tuple[dict[str, object], list[str]]:
    target = state.units[target_id]
    concentration = get_active_concentration_effect(target)
    if not concentration or damage_to_hp <= 0:
        return {}, []

    if target.conditions.dead or target.conditions.unconscious or target.current_hp <= 0:
        condition_deltas = end_concentration(
            state,
            target_id,
            reason=f"{target_id}'s concentration on {concentration.spell_id} ends because they are down.",
        )
        return {"concentrationSpellId": concentration.spell_id, "concentrationEnded": True}, condition_deltas

    roll_queue = override_rolls or []
    concentration_roll = pull_die(state, 20, roll_queue.pop(0) if roll_queue else None)
    bless_override = roll_queue.pop(0) if roll_queue else None
    bless_bonus, bless_rolls, bless_source_id = roll_bless_bonus(state, target, bless_override)
    dc = max(10, damage_to_hp // 2)
    total = concentration_roll + get_ability_modifier(target, "con") + bless_bonus
    success = total >= dc
    data: dict[str, object] = {
        "concentrationSpellId": concentration.spell_id,
        "concentrationSaveRolls": [concentration_roll],
        "concentrationSaveDc": dc,
        "concentrationSaveTotal": total,
        "concentrationSaveSuccess": success,
        "concentrationEnded": not success,
    }
    if bless_rolls:
        data["concentrationBlessRolls"] = bless_rolls
        data["concentrationBlessBonus"] = bless_bonus
        data["concentrationBlessSourceId"] = bless_source_id

    if success:
        return data, [f"{target_id} maintains concentration on {concentration.spell_id}."]

    condition_deltas = [f"{target_id} fails concentration on {concentration.spell_id}."]
    condition_deltas.extend(
        end_concentration(
            state,
            target_id,
            reason=f"{target_id}'s concentration on {concentration.spell_id} ends.",
        )
    )
    return data, condition_deltas


def apply_damage(
    state: EncounterState,
    target_id: str,
    damage_components: list[DamageComponentResult],
    is_critical: bool,
    *,
    attacker_id: str | None = None,
    attack_roll_damage: bool = False,
    concentration_save_rolls: list[int] | None = None,
) -> DamageApplicationResult:
    target = state.units[target_id]
    previous_hp = target.current_hp
    condition_deltas: list[str] = []
    resisted_damage = 0
    amplified_damage = 0
    temporary_hp_absorbed = 0
    final_damage_to_hp = 0
    final_total_damage = 0
    damage_prevented = 0
    damage_mitigation_source: str | None = None
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

    final_total_damage, damage_prevented, damage_mitigation_source = maybe_apply_uncanny_dodge(
        state,
        target=target,
        attacker_id=attacker_id,
        incoming_damage=final_total_damage,
        attack_roll_damage=attack_roll_damage,
    )
    if damage_mitigation_source == "uncanny_dodge":
        condition_deltas.append(f"{target_id} uses Uncanny Dodge to prevent {damage_prevented} damage.")

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
            damage_prevented=damage_prevented,
            damage_mitigation_source=damage_mitigation_source,
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
                damage_prevented=damage_prevented,
                damage_mitigation_source=damage_mitigation_source,
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
                damage_prevented=damage_prevented,
                damage_mitigation_source=damage_mitigation_source,
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
            damage_prevented=damage_prevented,
            damage_mitigation_source=damage_mitigation_source,
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
            damage_prevented=damage_prevented,
            damage_mitigation_source=damage_mitigation_source,
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

    if target.current_hp <= 0 or target.conditions.dead or target.conditions.unconscious:
        condition_deltas.extend(release_save_ending_restrained_effects_from_source(state, target_id))

    concentration_data, concentration_deltas = resolve_concentration_after_damage(
        state,
        target_id,
        final_damage_to_hp,
        concentration_save_rolls,
    )
    condition_deltas.extend(concentration_deltas)

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
        damage_prevented=damage_prevented,
        damage_mitigation_source=damage_mitigation_source,
        concentration_save_rolls=concentration_data.get("concentrationSaveRolls"),
        concentration_save_total=concentration_data.get("concentrationSaveTotal"),
        concentration_save_dc=concentration_data.get("concentrationSaveDc"),
        concentration_save_success=concentration_data.get("concentrationSaveSuccess"),
        concentration_spell_id=concentration_data.get("concentrationSpellId"),
        concentration_ended=bool(concentration_data.get("concentrationEnded", False)),
        concentration_bless_rolls=concentration_data.get("concentrationBlessRolls"),
        concentration_bless_bonus=int(concentration_data.get("concentrationBlessBonus", 0)),
        concentration_bless_source_id=concentration_data.get("concentrationBlessSourceId"),
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
        # Baseline Wizard behavior intentionally overuses Shield. We will add
        # conservative smart Shield timing back as a separate tuning step.
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


@dataclass(frozen=True)
class ConeBreathTargeting:
    primary_target_id: str
    target_ids: tuple[str, ...]
    enemy_target_ids: tuple[str, ...]
    ally_target_ids: tuple[str, ...]
    origin: GridPosition
    direction: str


@dataclass(frozen=True)
class SphereTargeting:
    primary_target_id: str
    target_ids: tuple[str, ...]
    enemy_target_ids: tuple[str, ...]
    ally_target_ids: tuple[str, ...]
    center: GridPosition


def get_self_origin_cone_endpoint_deltas(range_squares: int, direction: str) -> tuple[tuple[int, int], ...]:
    half_width = max(1, range_squares // 2)
    endpoints_by_direction = {
        "n": ((-half_width, -range_squares), (0, -range_squares), (half_width, -range_squares)),
        "ne": ((half_width, -range_squares), (range_squares, -range_squares), (range_squares, -half_width)),
        "e": ((range_squares, -half_width), (range_squares, 0), (range_squares, half_width)),
        "se": ((half_width, range_squares), (range_squares, half_width), (range_squares, range_squares)),
        "s": ((-half_width, range_squares), (0, range_squares), (half_width, range_squares)),
        "sw": ((-range_squares, half_width), (-range_squares, range_squares), (-half_width, range_squares)),
        "w": ((-range_squares, -half_width), (-range_squares, 0), (-range_squares, half_width)),
        "nw": ((-range_squares, -range_squares), (-range_squares, -half_width), (-half_width, -range_squares)),
    }
    return endpoints_by_direction[direction]


def get_self_origin_cone_squares(origin: GridPosition, direction: str, range_squares: int) -> list[GridPosition]:
    square_keys: set[tuple[int, int]] = set()
    for delta_x, delta_y in get_self_origin_cone_endpoint_deltas(range_squares, direction):
        endpoint = GridPosition(x=origin.x + delta_x, y=origin.y + delta_y)
        for square in get_line_squares(origin, endpoint)[1:]:
            if 1 <= square.x <= GRID_SIZE and 1 <= square.y <= GRID_SIZE:
                square_keys.add((square.x, square.y))
    return [GridPosition(x=x, y=y) for x, y in sorted(square_keys)]


def build_cone_breath_targeting(
    state: EncounterState,
    actor_id: str,
    *,
    actor_position: GridPosition | None = None,
    origin: GridPosition,
    direction: str,
    range_squares: int,
    required_primary_target_id: str | None = None,
) -> ConeBreathTargeting | None:
    actor = state.units[actor_id]
    footprint_position = actor_position or actor.position
    actor_footprint_keys = {
        (square.x, square.y)
        for square in (
            get_occupied_squares_for_position(footprint_position, get_unit_footprint(actor))
            if footprint_position
            else []
        )
    }
    cone_square_keys = {
        (square.x, square.y)
        for square in get_self_origin_cone_squares(origin, direction, range_squares)
        if (square.x, square.y) not in actor_footprint_keys
    }
    if not cone_square_keys:
        return None

    live_units = [
        unit
        for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id))
        if unit.id != actor_id and unit.position and not unit.conditions.dead
    ]
    hit_units = [
        unit
        for unit in live_units
        if any(
            (occupied_square.x, occupied_square.y) in cone_square_keys
            for occupied_square in get_occupied_squares_for_position(unit.position, get_unit_footprint(unit))
        )
    ]
    if required_primary_target_id and all(unit.id != required_primary_target_id for unit in hit_units):
        return None

    enemy_target_ids = tuple(unit.id for unit in hit_units if unit.faction != actor.faction)
    if not enemy_target_ids:
        return None
    ally_target_ids = tuple(unit.id for unit in hit_units if unit.faction == actor.faction)
    primary_target_id = required_primary_target_id or sorted(enemy_target_ids, key=unit_sort_key)[0]
    return ConeBreathTargeting(
        primary_target_id=primary_target_id,
        target_ids=tuple(unit.id for unit in hit_units),
        enemy_target_ids=enemy_target_ids,
        ally_target_ids=ally_target_ids,
        origin=origin,
        direction=direction,
    )


def choose_cone_breath_targeting(
    state: EncounterState,
    actor_id: str,
    *,
    actor_position: GridPosition | None = None,
    required_primary_target_id: str | None = None,
    minimum_enemy_targets: int = 1,
    allow_allies: bool = True,
    range_squares: int = 6,
) -> ConeBreathTargeting | None:
    actor = state.units[actor_id]
    position = actor_position or actor.position
    if not position:
        return None

    actor_origins = get_occupied_squares_for_position(position, get_unit_footprint(actor))
    viable: list[ConeBreathTargeting] = []
    for origin in actor_origins:
        for direction in sorted(BURNING_HANDS_CONE_ENDPOINTS):
            targeting = build_cone_breath_targeting(
                state,
                actor_id,
                actor_position=position,
                origin=origin,
                direction=direction,
                range_squares=range_squares,
                required_primary_target_id=required_primary_target_id,
            )
            if not targeting:
                continue
            if len(targeting.enemy_target_ids) < minimum_enemy_targets:
                continue
            if not allow_allies and targeting.ally_target_ids:
                continue
            viable.append(targeting)

    if not viable:
        return None

    return sorted(
        viable,
        key=lambda targeting: (
            -len(targeting.enemy_target_ids),
            len(targeting.ally_target_ids),
            sum(state.units[target_id].current_hp for target_id in targeting.enemy_target_ids),
            targeting.primary_target_id,
            targeting.origin.x,
            targeting.origin.y,
            targeting.direction,
            targeting.target_ids,
        ),
    )[0]


def choose_cold_breath_targeting(
    state: EncounterState,
    actor_id: str,
    *,
    actor_position: GridPosition | None = None,
    required_primary_target_id: str | None = None,
    minimum_enemy_targets: int = 1,
    allow_allies: bool = True,
) -> ConeBreathTargeting | None:
    return choose_cone_breath_targeting(
        state,
        actor_id,
        actor_position=actor_position,
        required_primary_target_id=required_primary_target_id,
        minimum_enemy_targets=minimum_enemy_targets,
        allow_allies=allow_allies,
        range_squares=6,
    )


def build_sphere_targeting(
    state: EncounterState,
    actor_id: str,
    *,
    actor_position: GridPosition | None = None,
    center: GridPosition,
    radius_squares: int,
    range_squares: int,
    required_primary_target_id: str | None = None,
    exclude_actor: bool = False,
) -> SphereTargeting | None:
    actor = state.units[actor_id]
    origin_position = actor_position or actor.position
    if not origin_position:
        return None
    if not (1 <= center.x <= GRID_SIZE and 1 <= center.y <= GRID_SIZE):
        return None

    actor_origins = get_occupied_squares_for_position(origin_position, get_unit_footprint(actor))
    if all(chebyshev_distance(origin, center) > range_squares for origin in actor_origins):
        return None

    live_units = [
        unit
        for unit in sorted(state.units.values(), key=lambda item: unit_sort_key(item.id))
        if unit.position and not unit.conditions.dead and not (exclude_actor and unit.id == actor_id)
    ]
    hit_units = [
        unit
        for unit in live_units
        if any(
            chebyshev_distance(center, occupied_square) <= radius_squares
            for occupied_square in get_occupied_squares_for_position(unit.position, get_unit_footprint(unit))
        )
    ]
    if required_primary_target_id and all(unit.id != required_primary_target_id for unit in hit_units):
        return None

    enemy_target_ids = tuple(unit.id for unit in hit_units if unit.faction != actor.faction)
    if not enemy_target_ids:
        return None
    ally_target_ids = tuple(unit.id for unit in hit_units if unit.faction == actor.faction)
    primary_target_id = required_primary_target_id or sorted(enemy_target_ids, key=unit_sort_key)[0]
    return SphereTargeting(
        primary_target_id=primary_target_id,
        target_ids=tuple(unit.id for unit in hit_units),
        enemy_target_ids=enemy_target_ids,
        ally_target_ids=ally_target_ids,
        center=center,
    )


def choose_sphere_targeting(
    state: EncounterState,
    actor_id: str,
    *,
    actor_position: GridPosition | None = None,
    required_primary_target_id: str | None = None,
    minimum_enemy_targets: int = 1,
    allow_allies: bool = True,
    radius_squares: int,
    range_squares: int,
    exclude_actor: bool = False,
) -> SphereTargeting | None:
    viable: list[SphereTargeting] = []
    for x in range(1, GRID_SIZE + 1):
        for y in range(1, GRID_SIZE + 1):
            targeting = build_sphere_targeting(
                state,
                actor_id,
                actor_position=actor_position,
                center=GridPosition(x=x, y=y),
                radius_squares=radius_squares,
                range_squares=range_squares,
                required_primary_target_id=required_primary_target_id,
                exclude_actor=exclude_actor,
            )
            if not targeting:
                continue
            if len(targeting.enemy_target_ids) < minimum_enemy_targets:
                continue
            if not allow_allies and targeting.ally_target_ids:
                continue
            viable.append(targeting)

    if not viable:
        return None

    return sorted(
        viable,
        key=lambda targeting: (
            -len(targeting.enemy_target_ids),
            len(targeting.ally_target_ids),
            sum(state.units[target_id].current_hp for target_id in targeting.enemy_target_ids),
            targeting.primary_target_id,
            targeting.center.x,
            targeting.center.y,
            targeting.target_ids,
        ),
    )[0]


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

    if unit_is_steady_aiming(attacker):
        advantage_sources.append("steady_aim")

    if can_apply_assassinate_advantage(state, attacker, target_id):
        advantage_sources.append("assassinate")

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

    if unit_is_frightened_by_source(state, attacker, target_id):
        disadvantage_sources.append("frightened")

    if unit_is_poisoned(attacker):
        disadvantage_sources.append("poisoned")

    if has_vex_effect(attacker, target_id):
        advantage_sources.append("vex")

    if has_harried_effect(target):
        advantage_sources.append("harried_target")

    if weapon.advantage_against_self_grappled_target and target_is_grappled_by_attacker(state, target, attacker_id):
        advantage_sources.append("self_grappled_target")

    if attacker.faction == "goblins" and unit_has_trait(attacker, "bloodied_frenzy") and unit_is_bloodied(attacker):
        advantage_sources.append("bloodied_frenzy")

    if "aura_of_authority" not in advantage_sources and unit_benefits_from_aura_of_authority(state, attacker):
        advantage_sources.append("aura_of_authority")

    if unit_has_reckless_attack_effect(attacker) and weapon.attack_ability == "str":
        advantage_sources.append("reckless_attack")

    if advantage_sources and disadvantage_sources:
        return "normal", advantage_sources, disadvantage_sources
    if advantage_sources:
        return "advantage", advantage_sources, disadvantage_sources
    if disadvantage_sources:
        return "disadvantage", advantage_sources, disadvantage_sources
    return "normal", advantage_sources, disadvantage_sources


def create_skip_event(state: EncounterState, actor_id: str, reason: str) -> CombatEvent:
    return build_skip_event(state, actor_id, reason)


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
        save_rolls=list(args.overrides.save_rolls if args.overrides else []),
        savage_damage_rolls=list(args.overrides.savage_damage_rolls if args.overrides else []),
        advantage_damage_rolls=list(args.overrides.advantage_damage_rolls if args.overrides else []),
        superiority_rolls=list(args.overrides.superiority_rolls if args.overrides else []),
        smite_damage_rolls=list(args.overrides.smite_damage_rolls if args.overrides else []),
        divine_favor_damage_rolls=list(args.overrides.divine_favor_damage_rolls if args.overrides else []),
        concentration_rolls=list(args.overrides.concentration_rolls if args.overrides else []),
    )

    target = state.units[args.target_id]
    maneuver_intent = args.maneuver_id
    maneuver_id: str | None = None
    maneuver_notes: str | None = None
    maneuver_condition_deltas: list[str] = []
    superiority_dice_rolls: list[int] = []
    maneuver_save_rolls: list[int] = []
    maneuver_save_total: int | None = None
    maneuver_save_dc: int | None = None
    maneuver_save_success: bool | None = None
    maneuver_prone_applied: bool | None = None
    superiority_dice_remaining: int | None = None
    precision_maneuver_applied = False

    if (
        maneuver_intent == "riposte"
        and can_use_battle_master_maneuver(attacker, "riposte")
        and spend_superiority_die(attacker)
    ):
        maneuver_id = "riposte"
        superiority_dice_remaining = attacker.resources.superiority_dice

    vex_available = has_vex_effect(attacker, args.target_id)
    harried_available = has_harried_effect(target)
    mode, advantage_sources, disadvantage_sources = get_attack_mode(
        state, attacker, args.attacker_id, target, args.target_id, weapon
    )
    bless_bonus, bless_rolls, bless_source_id = roll_bless_bonus(state, attacker)

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
    attack_total = selected_roll + weapon.attack_bonus + bless_bonus
    natural_one = selected_roll == 1
    natural_twenty = selected_roll == 20
    resolved_target_id = args.target_id
    reaction_actor_id: str | None = None
    attack_reaction: str | None = None
    defense_reaction_data: dict[str, int | str] | None = None
    target_ac = target.ac + attack_context.cover_ac_bonus + get_shield_ac_bonus(target)
    hit = natural_twenty or (not natural_one and attack_total >= target_ac)

    if (
        can_attempt_precision_attack(
            attacker,
            maneuver_intent=maneuver_intent,
            max_miss_margin=args.precision_max_miss_margin,
            hit=hit,
            natural_one=natural_one,
            attack_total=attack_total,
            target_ac=target_ac,
        )
        and spend_superiority_die(attacker)
    ):
        if maneuver_id == "riposte":
            precision_maneuver_applied = True
        else:
            maneuver_id = "precision_attack"
        superiority_dice_remaining = attacker.resources.superiority_dice
        precision_roll = pull_die(
            state,
            get_superiority_die_sides(attacker),
            overrides.superiority_rolls.pop(0) if overrides.superiority_rolls else None,
        )
        superiority_dice_rolls.append(precision_roll)
        attack_total += precision_roll
        hit = natural_twenty or (not natural_one and attack_total >= target_ac)
        maneuver_notes = f"{args.attacker_id} uses Precision Attack, adding {precision_roll} to the attack roll."
        maneuver_condition_deltas.append(maneuver_notes)

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
    target_was_alive_before_hit = target.current_hp > 0 and not target.conditions.dead
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
    final_total_damage = 0
    hp_delta = 0
    damage_prevented = 0
    damage_mitigation_source: str | None = None
    undead_fortitude_triggered = False
    undead_fortitude_success: bool | None = None
    undead_fortitude_dc: int | None = None
    undead_fortitude_bypass_reason: str | None = None
    great_weapon_master_damage_bonus = 0
    great_weapon_master_attack_action_eligible = (
        args.great_weapon_master_eligible
        and not args.is_opportunity_attack
        and args.maneuver_id != "riposte"
        and not args.omit_ability_modifier_damage
    )
    condition_deltas: list[str] = []
    savage_attacker_consumed = False
    final_damage_components: list[DamageComponentResult] = []
    assassinate_damage_bonus = 0
    cunning_strike_id: str | None = None
    cunning_strike_cost_d6 = 0
    sneak_attack_dice_rolled: int | None = None
    sneak_attack_dice_spent = 0
    cunning_strike_save_ability: str | None = None
    cunning_strike_save_dc: int | None = None
    cunning_strike_save_rolls: list[int] = []
    cunning_strike_save_total: int | None = None
    cunning_strike_save_success: bool | None = None
    cunning_strike_condition_applied: bool | None = None
    divine_smite_applied = False
    divine_smite_spell_level = 0
    divine_smite_dice = 0
    divine_smite_rolls: list[int] = []
    divine_smite_damage = 0
    divine_favor_applied = False
    divine_favor_rolls: list[int] = []
    divine_favor_damage = 0
    sentinel_halt_applied = False

    if attack_reaction == "redirect_attack":
        condition_deltas.append(f"{args.target_id} uses Redirect Attack and swaps with {resolved_target_id}.")
    elif attack_reaction == "parry" and reaction_actor_id:
        condition_deltas.append(f"{reaction_actor_id} uses Parry and adds 2 AC against this attack.")

    condition_deltas.extend(end_hidden(attacker, reason=f"{args.attacker_id} is no longer hidden after attacking."))
    steady_aim_consumed = unit_is_steady_aiming(attacker)
    if steady_aim_consumed:
        attacker._steady_aim_active_this_turn = False

    if hit:
        weapon = resolve_selectable_damage_weapon(weapon, target)
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
        great_weapon_master_damage_bonus = get_great_weapon_master_damage_bonus(
            attacker,
            weapon,
            great_weapon_master_attack_action_eligible,
        )
        if great_weapon_master_damage_bonus > 0:
            great_weapon_master_damage_type = (
                final_damage_components[0].damage_type
                if final_damage_components
                else weapon.damage_type
                or (weapon.damage_components[0].damage_type if weapon.damage_components else "damage")
            )
            final_damage_components.append(
                DamageComponentResult(
                    damage_type=great_weapon_master_damage_type,
                    raw_rolls=[],
                    adjusted_rolls=[],
                    subtotal=0,
                    flat_modifier=great_weapon_master_damage_bonus,
                    total_damage=great_weapon_master_damage_bonus,
                )
            )
            condition_deltas.append(
                f"{args.attacker_id} applies Great Weapon Master for +{great_weapon_master_damage_bonus} damage."
            )
        if can_apply_sneak_attack(state, attacker, target, weapon, mode):
            sneak_attack_dice = get_sneak_attack_d6_count(attacker)
            if can_apply_cunning_strike(attacker, target, weapon, args.cunning_strike_id, sneak_attack_dice):
                definition = get_cunning_strike_definition(args.cunning_strike_id or "")
                cunning_strike_id = definition.strike_id
                cunning_strike_cost_d6 = definition.cost_d6
                sneak_attack_dice_spent = definition.cost_d6
                sneak_attack_dice -= definition.cost_d6
                condition_deltas.append(
                    f"{args.attacker_id} uses Cunning Strike: {definition.display_name}, spending {definition.cost_d6} Sneak Attack die."
                )

                if definition.save_ability:
                    cunning_strike_save_ability = definition.save_ability
                    cunning_strike_save_dc = get_cunning_strike_save_dc(attacker)
                    save_roll = pull_die(state, 20, overrides.save_rolls.pop(0) if overrides.save_rolls else None)
                    cunning_strike_save_rolls.append(save_roll)
                    save_modifier = get_ability_modifier(target, definition.save_ability)
                    cunning_strike_save_total = save_roll + save_modifier
                    cunning_strike_save_success = cunning_strike_save_total >= cunning_strike_save_dc

            sneak_attack_dice_rolled = sneak_attack_dice
            sneak_attack_component = roll_sneak_attack_component(state, sneak_attack_dice)
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
                assassinate_damage_bonus = get_assassinate_damage_bonus(state, attacker)
                if assassinate_damage_bonus > 0:
                    assassinate_damage_type = weapon.damage_type or (
                        weapon.damage_components[0].damage_type if weapon.damage_components else "damage"
                    )
                    final_damage_components.append(
                        DamageComponentResult(
                            damage_type=assassinate_damage_type,
                            raw_rolls=[],
                            adjusted_rolls=[],
                            subtotal=0,
                            flat_modifier=assassinate_damage_bonus,
                            total_damage=assassinate_damage_bonus,
                        )
                    )
                    condition_deltas.append(f"{args.attacker_id} applies Assassinate for +{assassinate_damage_bonus} damage.")

        if (
            maneuver_id is None
            and can_attempt_trip_attack(
                attacker,
                target,
                weapon,
                maneuver_intent=maneuver_intent,
                hit=hit,
                is_opportunity_attack=args.is_opportunity_attack,
            )
            and spend_superiority_die(attacker)
        ):
            maneuver_id = "trip_attack"
            superiority_dice_remaining = attacker.resources.superiority_dice

        if maneuver_id in {"trip_attack", "riposte"}:
            superiority_roll, superiority_component = roll_superiority_damage_component(
                state,
                attacker,
                weapon,
                critical_multiplier,
                overrides.superiority_rolls,
            )
            superiority_dice_rolls.append(superiority_roll)
            final_damage_components.append(superiority_component)
            base_maneuver_notes = f"{args.attacker_id} uses {get_maneuver_definition(maneuver_id).display_name}."
            maneuver_notes = f"{maneuver_notes} {base_maneuver_notes}" if maneuver_notes else base_maneuver_notes
            maneuver_condition_deltas.append(base_maneuver_notes)

        trip_save_failed = False
        if maneuver_id == "trip_attack":
            maneuver_save_dc = get_maneuver_save_dc(attacker, weapon)
            save_roll = pull_die(state, 20, overrides.save_rolls.pop(0) if overrides.save_rolls else None)
            maneuver_save_rolls.append(save_roll)
            save_modifier = get_ability_modifier(target, "str")
            maneuver_save_total = save_roll + save_modifier
            maneuver_save_success = maneuver_save_total >= maneuver_save_dc
            trip_save_failed = not maneuver_save_success

        divine_favor_effect = get_active_divine_favor_effect(attacker)
        if divine_favor_effect:
            divine_favor_rolls, divine_favor_component = roll_divine_favor_component(
                state,
                divine_favor_effect,
                critical_multiplier,
                overrides.divine_favor_damage_rolls,
            )
            divine_favor_damage = divine_favor_component.total_damage
            final_damage_components.append(divine_favor_component)
            divine_favor_applied = True
            condition_deltas.append(
                f"{args.attacker_id}'s Divine Favor adds {divine_favor_damage} {divine_favor_effect.damage_type} damage."
            )

        selected_smite_spell_level = choose_divine_smite_spell_level(
            attacker,
            target,
            weapon,
            critical=critical,
            is_opportunity_attack=args.is_opportunity_attack,
            maneuver_id=args.maneuver_id,
            weapon_damage_components=final_damage_components,
        )
        if selected_smite_spell_level and spend_spell_slot(attacker, selected_smite_spell_level):
            attacker._bonus_action_used_this_turn = True
            divine_smite_applied = True
            divine_smite_spell_level = selected_smite_spell_level
            divine_smite_dice, divine_smite_rolls, divine_smite_component = roll_divine_smite_component(
                state,
                target,
                divine_smite_spell_level,
                critical_multiplier,
                overrides.smite_damage_rolls,
            )
            divine_smite_damage = divine_smite_component.total_damage
            final_damage_components.append(divine_smite_component)
            condition_deltas.append(
                f"{args.attacker_id} casts Divine Smite for {divine_smite_damage} radiant damage."
            )

        total_damage = sum(component.total_damage for component in final_damage_components)

        damage_result = apply_damage(
            state,
            resolved_target_id,
            final_damage_components,
            critical,
            attacker_id=args.attacker_id,
            attack_roll_damage=True,
            concentration_save_rolls=overrides.concentration_rolls,
        )
        hp_delta = damage_result.hp_delta
        resisted_damage = damage_result.resisted_damage
        amplified_damage = damage_result.amplified_damage
        temporary_hp_absorbed = damage_result.temporary_hp_absorbed
        final_damage_to_hp = damage_result.final_damage_to_hp
        final_total_damage = damage_result.final_total_damage
        damage_prevented = damage_result.damage_prevented
        damage_mitigation_source = damage_result.damage_mitigation_source
        undead_fortitude_triggered = damage_result.undead_fortitude_triggered
        undead_fortitude_success = damage_result.undead_fortitude_success
        undead_fortitude_dc = damage_result.undead_fortitude_dc
        undead_fortitude_bypass_reason = damage_result.undead_fortitude_bypass_reason
        condition_deltas.extend(damage_result.condition_deltas)

        if cunning_strike_id == "poison":
            cunning_strike_condition_applied = False
            if (
                cunning_strike_save_success is False
                and not target.conditions.dead
                and target.current_hp > 0
                and "poisoned" not in target.condition_immunities
                and not unit_is_poisoned(target)
            ):
                target.temporary_effects.append(
                    PoisonedEffect(
                        kind="poisoned",
                        source_id=args.attacker_id,
                        save_dc=cunning_strike_save_dc or 0,
                        remaining_rounds=10,
                    )
                )
                cunning_strike_condition_applied = True
                condition_deltas.append(f"{resolved_target_id} fails Poison Cunning Strike save and is poisoned.")
            elif cunning_strike_save_success is True:
                condition_deltas.append(f"{resolved_target_id} resists Poison Cunning Strike.")

        if cunning_strike_id == "trip":
            cunning_strike_condition_applied = False
            if (
                cunning_strike_save_success is False
                and not target.conditions.dead
                and target.current_hp > 0
                and not target.conditions.unconscious
                and not target.conditions.prone
                and is_within_max_target_size(target.size_category, get_cunning_strike_definition("trip").max_target_size)
            ):
                target.conditions.prone = True
                cunning_strike_condition_applied = True
                condition_deltas.append(f"{resolved_target_id} fails Trip Cunning Strike save and is knocked prone.")
            elif cunning_strike_save_success is True:
                condition_deltas.append(f"{resolved_target_id} resists Trip Cunning Strike.")

        if cunning_strike_id == "withdraw":
            cunning_strike_condition_applied = True
            condition_deltas.append(f"{args.attacker_id} can withdraw up to half speed without provoking opportunity attacks.")

        if maneuver_id == "trip_attack":
            maneuver_prone_applied = False
            if (
                trip_save_failed
                and not target.conditions.dead
                and target.current_hp > 0
                and not target.conditions.unconscious
                and not target.conditions.prone
                and is_within_max_target_size(target.size_category, get_maneuver_definition("trip_attack").max_target_size)
            ):
                target.conditions.prone = True
                maneuver_prone_applied = True
                maneuver_condition_deltas.append(f"{resolved_target_id} fails Trip Attack save and is knocked prone.")
            elif maneuver_save_success is True:
                maneuver_condition_deltas.append(f"{resolved_target_id} resists Trip Attack.")

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
        sentinel_halt_applied = apply_sentinel_halt(
            state,
            attacker,
            target,
            hit=hit,
            is_opportunity_attack=args.is_opportunity_attack,
        )
        if sentinel_halt_applied:
            condition_deltas.append(f"{resolved_target_id}'s speed becomes 0 for the rest of the turn.")
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
        damage_result = apply_damage(
            state,
            resolved_target_id,
            final_damage_components,
            False,
            concentration_save_rolls=overrides.concentration_rolls,
        )
        hp_delta = damage_result.hp_delta
        resisted_damage = damage_result.resisted_damage
        amplified_damage = damage_result.amplified_damage
        temporary_hp_absorbed = damage_result.temporary_hp_absorbed
        final_damage_to_hp = damage_result.final_damage_to_hp
        final_total_damage = damage_result.final_total_damage
        damage_prevented = damage_result.damage_prevented
        damage_mitigation_source = damage_result.damage_mitigation_source
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
    if steady_aim_consumed:
        condition_deltas.append(f"{args.attacker_id}'s Steady Aim is consumed on this attack roll.")
    condition_deltas.extend(maneuver_condition_deltas)

    critical_multiplier = 2 if critical else 1
    hit_label = "critical hit" if critical else "hit" if hit else "miss"
    target_dropped_to_zero = bool(
        hit
        and target_was_alive_before_hit
        and resolved_target_id in state.units
        and (state.units[resolved_target_id].conditions.dead or state.units[resolved_target_id].current_hp <= 0)
    )
    great_weapon_master_hewing_trigger = bool(
        great_weapon_master_attack_action_eligible
        and unit_has_feature(attacker, "great_weapon_master")
        and weapon.kind == "melee"
        and weapon.two_handed is True
        and hit
        and (critical or target_dropped_to_zero)
    )
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
        "targetWasAliveBeforeHit": target_was_alive_before_hit,
        "targetDroppedToZero": target_dropped_to_zero,
    }
    if great_weapon_master_damage_bonus > 0:
        resolved_totals["greatWeaponMasterDamageBonus"] = great_weapon_master_damage_bonus
    if assassinate_damage_bonus > 0:
        resolved_totals["assassinateDamageBonus"] = assassinate_damage_bonus
    if divine_smite_applied:
        resolved_totals["spellId"] = "divine_smite"
        resolved_totals["spellLevel"] = divine_smite_spell_level
        resolved_totals["divineSmiteApplied"] = True
        resolved_totals["divineSmiteDice"] = divine_smite_dice
        resolved_totals["divineSmiteDamage"] = divine_smite_damage
        resolved_totals["spellSlotsLevel1Remaining"] = attacker.resources.spell_slots_level_1
        resolved_totals["spellSlotsLevel2Remaining"] = attacker.resources.spell_slots_level_2
    if divine_favor_applied:
        resolved_totals["divineFavorSpellId"] = "divine_favor"
        resolved_totals["divineFavorApplied"] = True
        resolved_totals["divineFavorDamage"] = divine_favor_damage
        resolved_totals["divineFavorDamageType"] = "radiant"
    if attack_context.sharpshooter_applied:
        resolved_totals["sharpshooterApplied"] = True
        if attack_context.sharpshooter_ignored_cover_ac_bonus > 0:
            resolved_totals["sharpshooterIgnoredCoverAcBonus"] = attack_context.sharpshooter_ignored_cover_ac_bonus
    if great_weapon_master_hewing_trigger:
        resolved_totals["greatWeaponMasterHewingTrigger"] = True
        resolved_totals["greatWeaponMasterHewingTriggerReason"] = "critical" if critical else "dropped_to_zero"
    if sentinel_halt_applied:
        resolved_totals["sentinelHaltApplied"] = True
        resolved_totals["speedReducedToZero"] = True
    if defense_reaction_data:
        resolved_totals.update(defense_reaction_data)
    if undead_fortitude_triggered:
        resolved_totals["undeadFortitudeTriggered"] = True
        resolved_totals["undeadFortitudeSuccess"] = undead_fortitude_success
        if undead_fortitude_dc is not None:
            resolved_totals["undeadFortitudeDc"] = undead_fortitude_dc
        if undead_fortitude_bypass_reason is not None:
            resolved_totals["undeadFortitudeBypassReason"] = undead_fortitude_bypass_reason
    if damage_mitigation_source == "uncanny_dodge":
        resolved_totals["defenseReaction"] = "uncanny_dodge"
        resolved_totals["defenseReactionActorId"] = resolved_target_id
        resolved_totals["uncannyDodgeDamagePrevented"] = damage_prevented
        resolved_totals["damageAfterUncannyDodge"] = final_total_damage
    if bless_bonus:
        resolved_totals["blessBonus"] = bless_bonus
        resolved_totals["blessSourceId"] = bless_source_id
    if cunning_strike_id:
        resolved_totals["cunningStrikeId"] = cunning_strike_id
        resolved_totals["cunningStrikeCostD6"] = cunning_strike_cost_d6
        resolved_totals["sneakAttackDiceSpent"] = sneak_attack_dice_spent
        resolved_totals["sneakAttackDiceRolled"] = sneak_attack_dice_rolled or 0
        resolved_totals["cunningStrikeApplied"] = cunning_strike_condition_applied is not False
        if cunning_strike_save_dc is not None:
            resolved_totals["cunningStrikeSaveAbility"] = cunning_strike_save_ability
            resolved_totals["cunningStrikeSaveDc"] = cunning_strike_save_dc
            resolved_totals["cunningStrikeSaveTotal"] = cunning_strike_save_total
            resolved_totals["cunningStrikeSaveSuccess"] = cunning_strike_save_success
            resolved_totals["cunningStrikeConditionApplied"] = cunning_strike_condition_applied or False
    if maneuver_id:
        resolved_totals["maneuverId"] = maneuver_id
        resolved_totals["superiorityDiceRemaining"] = superiority_dice_remaining
    if precision_maneuver_applied:
        resolved_totals["precisionManeuverId"] = "precision_attack"
    if maneuver_save_dc is not None:
        resolved_totals["maneuverSaveAbility"] = "str"
        resolved_totals["maneuverSaveDc"] = maneuver_save_dc
        resolved_totals["maneuverSaveTotal"] = maneuver_save_total
        resolved_totals["maneuverSaveSuccess"] = maneuver_save_success
        resolved_totals["maneuverProneApplied"] = maneuver_prone_applied or False
    raw_rolls = {
        "attackRolls": attack_rolls,
        "advantageSources": advantage_sources,
        "disadvantageSources": disadvantage_sources,
    }
    if attack_context.sharpshooter_ignored_disadvantage_sources:
        raw_rolls["sharpshooterIgnoredDisadvantageSources"] = attack_context.sharpshooter_ignored_disadvantage_sources
    if bless_rolls:
        raw_rolls["blessRolls"] = bless_rolls
    if divine_smite_rolls:
        raw_rolls["divineSmiteRolls"] = divine_smite_rolls
    if divine_favor_rolls:
        raw_rolls["divineFavorRolls"] = divine_favor_rolls
    if maneuver_id or precision_maneuver_applied:
        raw_rolls["superiorityDiceRolls"] = superiority_dice_rolls
    if maneuver_save_rolls:
        raw_rolls["maneuverSaveRolls"] = maneuver_save_rolls
    if cunning_strike_save_rolls:
        raw_rolls["cunningStrikeSaveRolls"] = cunning_strike_save_rolls
    if final_damage_components:
        attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)

    event = CombatEvent(
        **event_base(state, args.attacker_id),
        target_ids=[resolved_target_id],
        event_type="attack",
        raw_rolls=raw_rolls,
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
            maneuver_applied=maneuver_id,
            maneuver_notes=maneuver_notes,
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
    _ = target_id, weapon
    attacker = state.units[attacker_id]
    if not attacker._reckless_attack_available_this_turn:
        return False
    if not unit_has_feature(attacker, "reckless_attack"):
        return False
    # Barbarian-specific Reckless Attack timing is suspended while generic
    # smart-vs-dumb behavior is tuned.
    return False


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

# Spell mechanics live in spell_resolvers. Resolve these lazily so legacy
# imports from combat_rules still work without creating an import cycle.
_SPELL_RESOLVER_EXPORTS = {
    "apply_heroism_start_of_turn",
    "build_spell_attack_profile",
    "build_spell_skip_event",
    "resolve_aid",
    "resolve_bless",
    "resolve_burning_hands",
    "resolve_cast_spell",
    "resolve_cure_wounds",
    "resolve_divine_favor",
    "resolve_false_life",
    "resolve_heroism",
    "resolve_haste",
    "resolve_longstrider",
    "resolve_mage_armor",
    "resolve_magic_missile",
    "resolve_multi_target_save_spell",
    "resolve_ranged_spell_attack",
    "resolve_ray_of_sickness_poison_save",
    "resolve_scorching_ray",
    "resolve_shield_of_faith",
    "resolve_single_target_save_spell",
}


def __getattr__(name: str) -> object:
    if name in _SPELL_RESOLVER_EXPORTS:
        from backend.engine.rules import spell_resolvers

        value = getattr(spell_resolvers, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
