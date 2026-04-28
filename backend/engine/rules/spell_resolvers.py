from __future__ import annotations

from backend.content.class_progressions import get_proficiency_bonus
from backend.content.spell_definitions import get_spell_definition
from backend.engine.models.state import (
    AidEffect,
    BlessedEffect,
    CombatEvent,
    ConcentrationEffect,
    DamageCandidate,
    DamageComponentResult,
    DamageDetails,
    DiceSpec,
    DivineFavorEffect,
    EncounterState,
    HealingBlockedEffect,
    HeroismEffect,
    NoReactionsEffect,
    PoisonedEffect,
    ShieldOfFaithEffect,
    SlowEffect,
    UnitState,
    WeaponProfile,
    WeaponRange,
)
from backend.engine.rules.combat_rules import (
    apply_damage,
    can_trigger_attack_reaction,
    choose_burning_hands_targeting,
    choose_redirect_attack_ally,
    clear_frightened_effects,
    consume_harried_effect,
    consume_sap_effects,
    consume_vex_effect,
    end_concentration,
    end_hidden,
    get_active_divine_favor_effect,
    get_active_heroism_effect,
    get_attack_mode,
    get_saving_throw_mode,
    get_shield_ac_bonus,
    get_shield_of_faith_ac_bonus,
    has_harried_effect,
    has_vex_effect,
    maybe_apply_shield_reaction,
    pull_die,
    recalculate_effective_speed_for_unit,
    resolve_saving_throw,
    resolve_selectable_damage_weapon,
    roll_bless_bonus,
    roll_damage_candidate,
    unit_has_shield_effect,
    unit_is_poisoned,
    units_are_touch_reachable,
    units_are_within_spell_range,
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
    get_remaining_spell_slots,
    get_spell_save_dc,
    get_spellcasting_ability,
    resolve_spell_ability,
    spend_spell_slot,
    unit_has_combat_spell,
)
from backend.engine.rules.spatial import (
    get_attack_context,
    get_min_chebyshev_distance_between_footprints,
    get_unit_footprint,
)


def build_spell_attack_profile(
    attacker: UnitState,
    spell_id: str,
    *,
    attack_bonus_override: int | None = None,
    spellcasting_ability_override: str | None = None,
) -> WeaponProfile:
    spell = get_spell_definition(spell_id)
    ability = spellcasting_ability_override or resolve_spell_ability(attacker, spell.attack_ability)
    ability_modifier = get_ability_modifier(attacker, ability)
    spell_attack_bonus = (
        attack_bonus_override
        if attack_bonus_override is not None
        else get_proficiency_bonus(attacker.level or 1) + ability_modifier
    )
    is_melee_spell = spell.targeting_mode == "melee_spell_attack"
    return WeaponProfile(
        id=spell_id,
        display_name=spell.display_name,
        attack_bonus=spell_attack_bonus,
        ability_modifier=ability_modifier if attack_bonus_override is not None else 0,
        damage_dice=list(spell.damage_dice),
        damage_modifier=spell.damage_modifier,
        damage_type=spell.damage_type,
        selectable_damage_types=list(spell.selectable_damage_types) or None,
        kind="melee" if is_melee_spell else "ranged",
        reach=spell.range_feet if is_melee_spell else None,
        range=None if is_melee_spell else WeaponRange(normal=spell.range_feet, long=spell.range_feet),
    )


def build_spell_skip_event(state: EncounterState, actor_id: str, spell_id: str, reason: str) -> CombatEvent:
    spell = get_spell_definition(spell_id)
    return build_skip_event(state, actor_id, f"{spell.display_name}: {reason}")


def can_apply_potent_cantrip(attacker: UnitState, spell_id: str) -> bool:
    spell = get_spell_definition(spell_id)
    return (
        spell.level == 0
        and "potent_cantrip" in attacker.feature_ids
        and bool(spell.damage_dice)
        and spell.damage_type != "none"
    )


def build_potent_cantrip_damage_components(
    state: EncounterState,
    weapon: WeaponProfile,
    override_rolls: list[int] | None = None,
) -> tuple[DamageCandidate, list[DamageComponentResult], int]:
    primary_candidate = roll_damage_candidate(state, weapon, override_rolls)
    rolled_damage = sum(component.total_damage for component in primary_candidate.components)
    potent_damage = max(1, rolled_damage // 2) if rolled_damage > 0 else 0
    damage_type = weapon.damage_type or (
        weapon.damage_components[0].damage_type if weapon.damage_components else "damage"
    )
    return (
        primary_candidate,
        [
            DamageComponentResult(
                damage_type=damage_type,
                raw_rolls=list(primary_candidate.raw_rolls),
                adjusted_rolls=list(primary_candidate.adjusted_rolls),
                subtotal=primary_candidate.subtotal,
                flat_modifier=0,
                total_damage=potent_damage,
            )
        ],
        potent_damage,
    )


def resolve_ranged_spell_attack(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    spell_id: str,
    overrides: AttackRollOverrides | None = None,
    *,
    spend_slot: bool = True,
    attack_bonus_override: int | None = None,
    spellcasting_ability_override: str | None = None,
) -> CombatEvent:
    attacker = state.units[attacker_id]
    target = state.units[target_id]
    spell = get_spell_definition(spell_id)
    weapon = build_spell_attack_profile(
        attacker,
        spell_id,
        attack_bonus_override=attack_bonus_override,
        spellcasting_ability_override=spellcasting_ability_override,
    )

    attack_context = get_attack_context(state, attacker_id, target_id, weapon)
    if not attack_context.legal or not attack_context.within_normal_range:
        return build_spell_skip_event(state, attacker_id, spell_id, "is not in range.")
    if spell.level > 0 and spend_slot and not spend_spell_slot(attacker, spell.level):
        return build_spell_skip_event(state, attacker_id, spell_id, f"No level {spell.level} spell slots remain.")

    overrides = AttackRollOverrides(
        attack_rolls=list(overrides.attack_rolls if overrides else []),
        damage_rolls=list(overrides.damage_rolls if overrides else []),
        save_rolls=list(overrides.save_rolls if overrides else []),
        concentration_rolls=list(overrides.concentration_rolls if overrides else []),
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
    bless_bonus, bless_rolls, bless_source_id = roll_bless_bonus(state, attacker)
    attack_total = selected_roll + weapon.attack_bonus + bless_bonus
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

    target_was_alive_before_hit = spell_target_was_alive_before_damage(target)
    selected_damage_type: str | None = None
    if spell.selectable_damage_types:
        weapon = resolve_selectable_damage_weapon(weapon, target)
        selected_damage_type = weapon.damage_type

    critical = hit and natural_twenty
    primary_candidate: DamageCandidate | None = None
    final_damage_components: list[DamageComponentResult] = []
    total_damage = 0
    resisted_damage = 0
    amplified_damage = 0
    temporary_hp_absorbed = 0
    final_damage_to_hp = 0
    final_total_damage = 0
    hp_delta = 0
    damage_prevented = 0
    damage_mitigation_source: str | None = None
    condition_deltas: list[str] = []
    slow_applied = False
    slow_previous_effective_speed: int | None = None
    slow_new_effective_speed: int | None = None
    healing_blocked_applied = False
    potent_cantrip_applied = False
    potent_cantrip_damage = 0
    damage_result: DamageApplicationResult | None = None

    if attack_reaction == "redirect_attack":
        condition_deltas.append(f"{target_id} uses Redirect Attack and swaps with {resolved_target_id}.")
    elif attack_reaction == "parry" and reaction_actor_id:
        condition_deltas.append(f"{reaction_actor_id} uses Parry and adds 2 AC against this attack.")

    condition_deltas.extend(end_hidden(attacker, reason=f"{attacker_id} is no longer hidden after attacking."))

    if hit:
        primary_candidate = roll_damage_candidate(state, weapon, overrides.damage_rolls)
        critical_multiplier = 2 if critical else 1
        final_damage_components = build_final_damage_components(primary_candidate, None, critical_multiplier)
        damage_result = apply_damage(
            state,
            resolved_target_id,
            final_damage_components,
            critical,
            attacker_id=attacker_id,
            attack_roll_damage=True,
            concentration_save_rolls=overrides.concentration_rolls,
        )
        total_damage = sum(component.total_damage for component in final_damage_components)
        resisted_damage = damage_result.resisted_damage
        amplified_damage = damage_result.amplified_damage
        temporary_hp_absorbed = damage_result.temporary_hp_absorbed
        final_damage_to_hp = damage_result.final_damage_to_hp
        final_total_damage = damage_result.final_total_damage
        damage_prevented = damage_result.damage_prevented
        damage_mitigation_source = damage_result.damage_mitigation_source
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
        if (
            spell.on_hit_effect_kind == "slow"
            and spell.speed_penalty > 0
            and state.units[resolved_target_id].current_hp > 0
            and not state.units[resolved_target_id].conditions.dead
        ):
            slowed_target = state.units[resolved_target_id]
            slow_previous_effective_speed = slowed_target.effective_speed
            slowed_target.temporary_effects = [
                effect
                for effect in slowed_target.temporary_effects
                if not (effect.kind == "slow" and effect.source_id == attacker_id)
            ]
            slowed_target.temporary_effects.append(
                SlowEffect(
                    kind="slow",
                    source_id=attacker_id,
                    expires_at_turn_start_of=attacker_id,
                    penalty=spell.speed_penalty,
                )
            )
            recalculate_effective_speed_for_unit(slowed_target)
            slow_new_effective_speed = slowed_target.effective_speed
            slow_applied = True
            condition_deltas.append(
                f"{resolved_target_id}'s speed is reduced by {spell.speed_penalty} feet until {attacker_id}'s next turn."
            )
        if (
            spell.on_hit_effect_kind == "healing_blocked"
            and state.units[resolved_target_id].current_hp > 0
            and not state.units[resolved_target_id].conditions.dead
        ):
            healing_blocked_target = state.units[resolved_target_id]
            healing_blocked_target.temporary_effects = [
                effect
                for effect in healing_blocked_target.temporary_effects
                if not (effect.kind == "healing_blocked" and effect.source_id == attacker_id)
            ]
            healing_blocked_target.temporary_effects.append(
                HealingBlockedEffect(
                    kind="healing_blocked",
                    source_id=attacker_id,
                    expires_at_turn_start_of=attacker_id,
                )
            )
            healing_blocked_applied = True
            condition_deltas.append(
                f"{resolved_target_id} cannot regain HP until the start of {attacker_id}'s next turn."
            )
    elif can_apply_potent_cantrip(attacker, spell_id):
        primary_candidate, final_damage_components, potent_cantrip_damage = build_potent_cantrip_damage_components(
            state,
            weapon,
            overrides.damage_rolls,
        )
        if potent_cantrip_damage > 0:
            damage_result = apply_damage(
                state,
                resolved_target_id,
                final_damage_components,
                False,
                attacker_id=attacker_id,
                attack_roll_damage=False,
                concentration_save_rolls=overrides.concentration_rolls,
            )
            potent_cantrip_applied = True
            total_damage = sum(component.total_damage for component in final_damage_components)
            resisted_damage = damage_result.resisted_damage
            amplified_damage = damage_result.amplified_damage
            temporary_hp_absorbed = damage_result.temporary_hp_absorbed
            final_damage_to_hp = damage_result.final_damage_to_hp
            final_total_damage = damage_result.final_total_damage
            hp_delta = damage_result.hp_delta
            condition_deltas.extend(damage_result.condition_deltas)

    if sap_consumed > 0:
        condition_deltas.append(f"{attacker_id}'s sap disadvantage is consumed on this attack roll.")
    if vex_consumed:
        condition_deltas.append(f"{attacker_id}'s vex advantage is consumed on this attack roll.")
    if harried_consumed:
        condition_deltas.append(f"{target_id}'s harried defense is consumed on this attack roll.")

    critical_multiplier = 2 if critical else 1
    hit_label = "critical hit" if critical else "hit" if hit else "miss"
    resolved_totals = {
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
    }
    if spell.level > 0:
        resolved_totals[f"spellSlotsLevel{spell.level}Remaining"] = get_remaining_spell_slots(attacker, spell.level)
    if selected_damage_type:
        resolved_totals["selectedDamageType"] = selected_damage_type
        resolved_totals["selectableDamageTypes"] = list(spell.selectable_damage_types)
    if damage_mitigation_source == "uncanny_dodge":
        resolved_totals["defenseReaction"] = "uncanny_dodge"
        resolved_totals["defenseReactionActorId"] = resolved_target_id
        resolved_totals["uncannyDodgeDamagePrevented"] = damage_prevented
        resolved_totals["damageAfterUncannyDodge"] = final_total_damage
    if bless_bonus:
        resolved_totals["blessBonus"] = bless_bonus
        resolved_totals["blessSourceId"] = bless_source_id
    if slow_applied:
        resolved_totals["slowApplied"] = True
        resolved_totals["speedPenalty"] = spell.speed_penalty
        resolved_totals["previousEffectiveSpeed"] = slow_previous_effective_speed
        resolved_totals["newEffectiveSpeed"] = slow_new_effective_speed
        resolved_totals["slowExpiresAtTurnStartOf"] = attacker_id
    if healing_blocked_applied:
        resolved_totals["healingBlockedApplied"] = True
        resolved_totals["healingBlockedExpiresAtTurnStartOf"] = attacker_id
        resolved_totals["undeadAttackDisadvantageModeled"] = False
    if potent_cantrip_applied:
        resolved_totals["potentCantripApplied"] = True
        resolved_totals["potentCantripDamage"] = potent_cantrip_damage
        resolved_totals["potentCantripNoRider"] = True
    attach_spell_target_outcome_fields(state, resolved_totals, resolved_target_id, target_was_alive_before_hit)
    raw_rolls = {
        "attackRolls": attack_rolls,
        "advantageSources": advantage_sources,
        "disadvantageSources": disadvantage_sources,
    }
    if bless_rolls:
        raw_rolls["blessRolls"] = bless_rolls
    if damage_result:
        attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)

    return CombatEvent(
        **event_base(state, attacker_id),
        target_ids=[resolved_target_id],
        event_type="attack",
        raw_rolls=raw_rolls,
        resolved_totals=resolved_totals,
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


def resolve_ray_of_sickness_poison_save(
    state: EncounterState,
    attacker_id: str,
    attack_event: CombatEvent,
    overrides: AttackRollOverrides | None = None,
) -> CombatEvent | None:
    if attack_event.event_type != "attack" or not bool(attack_event.resolved_totals.get("hit")):
        return None
    if not attack_event.target_ids:
        return None

    target_id = attack_event.target_ids[0]
    target = state.units[target_id]
    if target.current_hp <= 0 or target.conditions.dead:
        return None
    if "poisoned" in target.condition_immunities or unit_is_poisoned(target):
        return None

    spell = get_spell_definition("ray_of_sickness")
    save_dc = get_spell_save_dc(state.units[attacker_id], "ray_of_sickness")
    save_overrides = SavingThrowOverrides(save_rolls=list(overrides.save_rolls if overrides else []))
    save_event = resolve_saving_throw(
        state,
        ResolveSavingThrowArgs(
            actor_id=target_id,
            ability=spell.save_ability or "con",
            dc=save_dc,
            reason=spell.display_name,
            overrides=save_overrides,
        ),
    )
    save_success = bool(save_event.resolved_totals["success"])
    poisoned_applied = False
    poisoned_expires_at_turn_end_of: str | None = None
    poisoned_expires_at_round: int | None = None
    poisoned_skip_reason = "save_succeeded" if save_success else None

    if save_success:
        save_event.condition_deltas.append(f"{target_id} resists {spell.display_name}'s poison.")
    else:
        poisoned_expires_at_turn_end_of = attacker_id
        poisoned_expires_at_round = state.round + 1
        target.temporary_effects.append(
            PoisonedEffect(
                kind="poisoned",
                source_id=attacker_id,
                save_dc=save_dc,
                remaining_rounds=spell.duration_rounds,
                expires_at_turn_end_of=poisoned_expires_at_turn_end_of,
                expires_at_round=poisoned_expires_at_round,
            )
        )
        poisoned_applied = True
        save_event.condition_deltas.append(
            f"{target_id} fails {spell.display_name}'s CON save and is poisoned until the end of {attacker_id}'s next turn."
        )

    save_event.resolved_totals["spellId"] = "ray_of_sickness"
    save_event.resolved_totals["poisonedApplied"] = poisoned_applied
    save_event.resolved_totals["poisonedExpiresAtTurnEndOf"] = poisoned_expires_at_turn_end_of
    save_event.resolved_totals["poisonedExpiresAtRound"] = poisoned_expires_at_round
    save_event.resolved_totals["poisonedDurationRounds"] = spell.duration_rounds
    save_event.resolved_totals["poisonedSkipReason"] = poisoned_skip_reason
    return save_event


def resolve_magic_missile(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
    *,
    spell_level: int | None = None,
) -> CombatEvent:
    attacker = state.units[attacker_id]
    spell = get_spell_definition("magic_missile")
    weapon = build_spell_attack_profile(attacker, "magic_missile")
    cast_level = max(spell.level, int(spell_level or spell.level))
    dart_count = get_magic_missile_dart_count(cast_level)
    weapon.damage_dice = [DiceSpec(count=dart_count, sides=4)]
    weapon.damage_modifier = dart_count
    attack_context = get_attack_context(state, attacker_id, target_id, weapon)

    if not attack_context.legal or not attack_context.within_normal_range:
        return build_spell_skip_event(state, attacker_id, "magic_missile", "is not in range.")
    if not spend_spell_slot(attacker, cast_level):
        return build_spell_skip_event(state, attacker_id, "magic_missile", f"No level {cast_level} spell slots remain.")

    target = state.units[target_id]
    target_was_alive_before_hit = spell_target_was_alive_before_damage(target)
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
        damage_overrides = AttackRollOverrides(
            damage_rolls=list(overrides.damage_rolls if overrides else []),
            concentration_rolls=list(overrides.concentration_rolls if overrides else []),
        )
        primary_candidate = roll_damage_candidate(state, weapon, damage_overrides.damage_rolls)
        final_damage_components = build_final_damage_components(primary_candidate, None, 1)
        damage_result = apply_damage(
            state,
            target_id,
            final_damage_components,
            False,
            concentration_save_rolls=damage_overrides.concentration_rolls,
        )
        total_damage = sum(component.total_damage for component in final_damage_components)
        condition_deltas = list(damage_result.condition_deltas)
    raw_rolls = {"damageRolls": primary_candidate.raw_rolls if primary_candidate else []}
    resolved_totals = {
        "spellId": "magic_missile",
        "spellLevel": cast_level,
        "hit": True,
        "critical": False,
        "distanceSquares": attack_context.distance_squares,
        "distanceFeet": attack_context.distance_feet,
        "spellSlotsLevel1Remaining": attacker.resources.spell_slots_level_1,
        "spellSlotsLevel2Remaining": attacker.resources.spell_slots_level_2,
        f"spellSlotsLevel{cast_level}Remaining": get_remaining_spell_slots(attacker, cast_level),
        "blockedByShield": blocked_by_shield,
        "dartCount": dart_count,
        "dartsInGroup": dart_count,
        "projectileGroupIndex": 1,
        "projectileGroupCount": 1,
        "spellCastEvent": True,
        "projectileTargetIds": [target_id for _ in range(dart_count)],
        **(defense_reaction_data or {}),
    }
    attach_spell_target_outcome_fields(state, resolved_totals, target_id, target_was_alive_before_hit)
    attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)

    return CombatEvent(
        **event_base(state, attacker_id),
        target_ids=[target_id],
        event_type="attack",
        raw_rolls=raw_rolls,
        resolved_totals=resolved_totals,
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


def get_magic_missile_dart_count(spell_level: int) -> int:
    return 3 + max(0, spell_level - 1)


def normalize_projectile_target_ids(target_ids: list[str], projectile_count: int) -> list[str]:
    if not target_ids:
        return []
    normalized = list(target_ids[:projectile_count])
    while len(normalized) < projectile_count:
        normalized.append(normalized[-1])
    return normalized


def resolve_magic_missile_projectiles(
    state: EncounterState,
    attacker_id: str,
    target_ids: list[str],
    overrides: AttackRollOverrides | None = None,
    *,
    spell_level: int | None = None,
) -> list[CombatEvent]:
    attacker = state.units[attacker_id]
    spell = get_spell_definition("magic_missile")
    if not unit_has_combat_spell(attacker, "magic_missile"):
        return [build_spell_skip_event(state, attacker_id, "magic_missile", "is not prepared.")]

    cast_level = max(spell.level, int(spell_level or spell.level))
    dart_count = get_magic_missile_dart_count(cast_level)
    projectile_target_ids = normalize_projectile_target_ids(target_ids, dart_count)
    if not projectile_target_ids:
        return [build_spell_skip_event(state, attacker_id, "magic_missile", "has no target.")]

    weapon = build_spell_attack_profile(attacker, "magic_missile")
    attack_contexts = {}
    for target_id in dict.fromkeys(projectile_target_ids):
        target = state.units.get(target_id)
        if not target or target.conditions.dead:
            return [build_spell_skip_event(state, attacker_id, "magic_missile", "target is unavailable.")]
        attack_context = get_attack_context(state, attacker_id, target_id, weapon)
        if not attack_context.legal or not attack_context.within_normal_range:
            return [build_spell_skip_event(state, attacker_id, "magic_missile", "is not in range.")]
        attack_contexts[target_id] = attack_context

    if not spend_spell_slot(attacker, cast_level):
        return [build_spell_skip_event(state, attacker_id, "magic_missile", f"No level {cast_level} spell slots remain.")]

    grouped_projectiles: list[tuple[str, int]] = []
    for target_id in projectile_target_ids:
        if grouped_projectiles and grouped_projectiles[-1][0] == target_id:
            previous_target_id, previous_count = grouped_projectiles[-1]
            grouped_projectiles[-1] = (previous_target_id, previous_count + 1)
        else:
            grouped_projectiles.append((target_id, 1))

    damage_overrides = AttackRollOverrides(
        damage_rolls=list(overrides.damage_rolls if overrides else []),
        concentration_rolls=list(overrides.concentration_rolls if overrides else []),
    )
    events: list[CombatEvent] = []

    for group_index, (target_id, darts_in_group) in enumerate(grouped_projectiles, start=1):
        target = state.units[target_id]
        attack_context = attack_contexts[target_id]
        target_was_alive_before_hit = spell_target_was_alive_before_damage(target)
        defense_reaction_data = (
            maybe_apply_shield_reaction(state, attacker_id=attacker_id, target_id=target_id, trigger="magic_missile")
            if not unit_has_shield_effect(target)
            else None
        )
        blocked_by_shield = unit_has_shield_effect(state.units[target_id])
        primary_candidate: DamageCandidate | None = None
        final_damage_components: list[DamageComponentResult] = []
        total_damage = 0
        damage_result = build_no_damage_result()
        condition_deltas: list[str] = []

        if blocked_by_shield:
            condition_deltas.append(f"{target_id}'s Shield blocks Magic Missile.")
        else:
            damage_rolls = [
                pull_die(
                    state,
                    4,
                    damage_overrides.damage_rolls.pop(0) if damage_overrides.damage_rolls else None,
                )
                for _ in range(darts_in_group)
            ]
            damage_component = DamageComponentResult(
                damage_type=spell.damage_type,
                raw_rolls=list(damage_rolls),
                adjusted_rolls=list(damage_rolls),
                subtotal=sum(damage_rolls),
                flat_modifier=darts_in_group,
                total_damage=sum(damage_rolls) + darts_in_group,
            )
            final_damage_components = [damage_component]
            primary_candidate = DamageCandidate(
                components=list(final_damage_components),
                raw_rolls=list(damage_rolls),
                adjusted_rolls=list(damage_rolls),
                subtotal=sum(damage_rolls),
            )
            damage_result = apply_damage(
                state,
                target_id,
                final_damage_components,
                False,
                concentration_save_rolls=damage_overrides.concentration_rolls,
            )
            total_damage = sum(component.total_damage for component in final_damage_components)
            condition_deltas = list(damage_result.condition_deltas)

        raw_rolls = {"damageRolls": primary_candidate.raw_rolls if primary_candidate else []}
        resolved_totals = {
            "spellId": "magic_missile",
            "spellLevel": cast_level,
            "hit": True,
            "critical": False,
            "distanceSquares": attack_context.distance_squares,
            "distanceFeet": attack_context.distance_feet,
            "spellSlotsLevel1Remaining": attacker.resources.spell_slots_level_1,
            "spellSlotsLevel2Remaining": attacker.resources.spell_slots_level_2,
            f"spellSlotsLevel{cast_level}Remaining": get_remaining_spell_slots(attacker, cast_level),
            "blockedByShield": blocked_by_shield,
            "dartCount": dart_count,
            "dartsInGroup": darts_in_group,
            "projectileGroupIndex": group_index,
            "projectileGroupCount": len(grouped_projectiles),
            "spellCastEvent": group_index == 1,
            "projectileTargetIds": list(projectile_target_ids),
            **(defense_reaction_data or {}),
        }
        attach_spell_target_outcome_fields(state, resolved_totals, target_id, target_was_alive_before_hit)
        attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)

        events.append(
            CombatEvent(
                **event_base(state, attacker_id),
                target_ids=[target_id],
                event_type="attack",
                raw_rolls=raw_rolls,
                resolved_totals=resolved_totals,
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
                        f"{attacker_id} casts {spell.display_name} at {target_id} "
                        f"with {darts_in_group} dart{'s' if darts_in_group != 1 else ''} for {total_damage} damage"
                        f"{f' ({damage_result.resisted_damage} resisted)' if damage_result.resisted_damage > 0 else ''}"
                        f"{f' (+{damage_result.amplified_damage} vulnerability)' if damage_result.amplified_damage > 0 else ''}."
                    )
                ),
            )
        )

    return events


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


def build_spell_save_damage_component(
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


def build_no_damage_result() -> DamageApplicationResult:
    return DamageApplicationResult(
        hp_delta=0,
        condition_deltas=[],
        resisted_damage=0,
        amplified_damage=0,
        temporary_hp_absorbed=0,
        final_damage_to_hp=0,
        final_total_damage=0,
    )


def spell_target_was_alive_before_damage(target: UnitState) -> bool:
    return target.current_hp > 0 and not target.conditions.dead


def attach_spell_target_outcome_fields(
    state: EncounterState,
    resolved_totals: dict[str, object],
    target_id: str,
    target_was_alive_before_damage: bool,
) -> None:
    target = state.units.get(target_id)
    target_dropped_to_zero = bool(
        target_was_alive_before_damage
        and target is not None
        and (target.conditions.dead or target.current_hp <= 0)
    )
    resolved_totals["targetWasAliveBeforeHit"] = target_was_alive_before_damage
    resolved_totals["targetDroppedToZero"] = target_dropped_to_zero


def resolve_spell_attack_roll_count(
    state: EncounterState,
    attacker: UnitState,
    target_id: str,
    spell_id: str,
    *,
    attack_bonus_override: int | None = None,
    spellcasting_ability_override: str | None = None,
) -> int:
    target = state.units[target_id]
    weapon = build_spell_attack_profile(
        attacker,
        spell_id,
        attack_bonus_override=attack_bonus_override,
        spellcasting_ability_override=spellcasting_ability_override,
    )
    mode, _, _ = get_attack_mode(state, attacker, attacker.id, target, target_id, weapon)
    return 1 if mode == "normal" else 2


def resolve_scorching_ray(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
    *,
    spend_slot: bool = True,
    require_prepared: bool = True,
    attack_bonus_override: int | None = None,
    spellcasting_ability_override: str | None = None,
    target_ids: list[str] | None = None,
    spell_level: int | None = None,
) -> list[CombatEvent]:
    attacker = state.units[attacker_id]
    spell = get_spell_definition("scorching_ray")
    weapon = build_spell_attack_profile(
        attacker,
        "scorching_ray",
        attack_bonus_override=attack_bonus_override,
        spellcasting_ability_override=spellcasting_ability_override,
    )

    if require_prepared and not unit_has_combat_spell(attacker, "scorching_ray"):
        return [build_spell_skip_event(state, attacker_id, "scorching_ray", "is not prepared.")]
    target = state.units.get(target_id)
    if not target or target.conditions.dead:
        return [build_spell_skip_event(state, attacker_id, "scorching_ray", "target is unavailable.")]

    attack_context = get_attack_context(state, attacker_id, target_id, weapon)
    if not attack_context.legal or not attack_context.within_normal_range:
        return [build_spell_skip_event(state, attacker_id, "scorching_ray", "is not in range.")]
    cast_level = max(spell.level, int(spell_level or spell.level))
    ray_count = spell.ray_count + max(0, cast_level - spell.level)
    ray_target_ids = normalize_projectile_target_ids(target_ids or [target_id], ray_count)
    if spend_slot and not spend_spell_slot(attacker, cast_level):
        return [build_spell_skip_event(state, attacker_id, "scorching_ray", f"No level {cast_level} spell slots remain.")]

    attack_rolls_override = list(overrides.attack_rolls if overrides else [])
    damage_rolls_override = list(overrides.damage_rolls if overrides else [])
    concentration_rolls_override = list(overrides.concentration_rolls if overrides else [])
    phase_totals = {
        "spellId": "scorching_ray",
        "spellLevel": cast_level,
        "rayCount": ray_count,
        "rayTargetIds": list(ray_target_ids),
    }
    if spend_slot:
        phase_totals[f"spellSlotsLevel{cast_level}Remaining"] = get_remaining_spell_slots(attacker, cast_level)
        phase_totals["spellSlotsLevel2Remaining"] = attacker.resources.spell_slots_level_2
    else:
        phase_totals["spellLikeAction"] = True
    events: list[CombatEvent] = [
        CombatEvent(
            **event_base(state, attacker_id),
            target_ids=list(ray_target_ids),
            event_type="phase_change",
            raw_rolls={},
            resolved_totals=phase_totals,
            movement_details=None,
            damage_details=None,
            condition_deltas=[],
            text_summary=f"{attacker_id} casts {spell.display_name} at {target_id}.",
        )
    ]

    for ray_index, ray_target_id in enumerate(ray_target_ids, start=1):
        target = state.units.get(ray_target_id)
        if not target or target.conditions.dead or target.current_hp <= 0:
            continue
        attack_roll_count = resolve_spell_attack_roll_count(
            state,
            attacker,
            ray_target_id,
            "scorching_ray",
            attack_bonus_override=attack_bonus_override,
            spellcasting_ability_override=spellcasting_ability_override,
        )
        ray_attack_rolls = [
            attack_rolls_override.pop(0) for _ in range(min(attack_roll_count, len(attack_rolls_override)))
        ]
        ray_overrides = AttackRollOverrides(
            attack_rolls=ray_attack_rolls,
            damage_rolls=list(damage_rolls_override[:2]),
            concentration_rolls=list(concentration_rolls_override),
        )
        ray_event = resolve_ranged_spell_attack(
            state,
            attacker_id,
            ray_target_id,
            "scorching_ray",
            ray_overrides,
            spend_slot=False,
            attack_bonus_override=attack_bonus_override,
            spellcasting_ability_override=spellcasting_ability_override,
        )
        if ray_event.event_type != "attack":
            events.append(ray_event)
            break
        if ray_event.damage_details and ray_event.damage_details.primary_candidate:
            used_damage_rolls = len(ray_event.damage_details.primary_candidate.raw_rolls)
            damage_rolls_override = damage_rolls_override[used_damage_rolls:]
        if ray_event.damage_details and ray_event.damage_details.final_damage_to_hp > 0:
            concentration_rolls_override = []
        ray_event.resolved_totals["rayIndex"] = ray_index
        ray_event.resolved_totals["rayCount"] = ray_count
        ray_event.resolved_totals["rayTargetIds"] = list(ray_target_ids)
        if spend_slot:
            ray_event.resolved_totals[f"spellSlotsLevel{cast_level}Remaining"] = get_remaining_spell_slots(
                attacker, cast_level
            )
            ray_event.resolved_totals["spellSlotsLevel2Remaining"] = attacker.resources.spell_slots_level_2
        else:
            ray_event.resolved_totals["spellLikeAction"] = True
        events.append(ray_event)

    return events


def resolve_single_target_save_spell(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    spell_id: str,
    overrides: AttackRollOverrides | None = None,
) -> list[CombatEvent]:
    return resolve_multi_target_save_spell(state, attacker_id, [target_id], spell_id, overrides)


def targets_are_within_spell_cluster(state: EncounterState, target_ids: list[str], range_feet: int) -> bool:
    if len(target_ids) <= 1:
        return True

    for index, left_id in enumerate(target_ids):
        left = state.units[left_id]
        if not left.position:
            return False
        for right_id in target_ids[index + 1 :]:
            right = state.units[right_id]
            if not right.position:
                return False
            if (
                get_min_chebyshev_distance_between_footprints(
                    left.position,
                    get_unit_footprint(left),
                    right.position,
                    get_unit_footprint(right),
                )
                > range_feet // 5
            ):
                return False
    return True


def resolve_multi_target_save_spell(
    state: EncounterState,
    attacker_id: str,
    target_ids: list[str],
    spell_id: str,
    overrides: AttackRollOverrides | None = None,
) -> list[CombatEvent]:
    attacker = state.units[attacker_id]
    spell = get_spell_definition(spell_id)
    weapon = build_spell_attack_profile(attacker, spell_id)

    if not unit_has_combat_spell(attacker, spell_id):
        return [build_spell_skip_event(state, attacker_id, spell_id, "is not prepared.")]
    if attacker.current_hp <= 0 or attacker.conditions.dead or attacker.conditions.unconscious:
        return [build_spell_skip_event(state, attacker_id, spell_id, "cannot be cast while down.")]

    resolved_target_ids: list[str] = []
    seen_target_ids: set[str] = set()
    for target_id in target_ids:
        if target_id in seen_target_ids:
            continue
        resolved_target_ids.append(target_id)
        seen_target_ids.add(target_id)

    if not resolved_target_ids:
        return [build_spell_skip_event(state, attacker_id, spell_id, "has no target.")]
    if len(resolved_target_ids) > spell.max_targets:
        return [build_spell_skip_event(state, attacker_id, spell_id, f"can target at most {spell.max_targets} creatures.")]

    attack_contexts = {}
    for target_id in resolved_target_ids:
        target = state.units.get(target_id)
        if not target:
            return [build_spell_skip_event(state, attacker_id, spell_id, "target is unavailable.")]
        if target.conditions.dead:
            return [build_spell_skip_event(state, attacker_id, spell_id, "target is dead.")]
        if spell_id == "shatter" and target.faction == attacker.faction:
            return [build_spell_skip_event(state, attacker_id, spell_id, "cannot intentionally target allies.")]
        attack_context = get_attack_context(state, attacker_id, target_id, weapon)
        if not attack_context.legal or not attack_context.within_normal_range:
            return [build_spell_skip_event(state, attacker_id, spell_id, "is not in range.")]
        attack_contexts[target_id] = attack_context

    if spell.max_targets > 1 and not targets_are_within_spell_cluster(
        state, resolved_target_ids, spell.target_cluster_feet
    ):
        return [
            build_spell_skip_event(
                state,
                attacker_id,
                spell_id,
                f"targets are not within {spell.target_cluster_feet} feet of each other.",
            )
        ]

    if spell.level > 0 and not spend_spell_slot(attacker, spell.level):
        return [build_spell_skip_event(state, attacker_id, spell_id, f"No level {spell.level} spell slots remain.")]

    damage_rolls_override = list(overrides.damage_rolls if overrides else [])
    damage_rolls = [
        pull_die(state, dice.sides, damage_rolls_override.pop(0) if damage_rolls_override else None)
        for dice in spell.damage_dice
        for _ in range(dice.count)
    ]
    full_damage = sum(damage_rolls) + spell.damage_modifier
    save_dc = get_spell_save_dc(attacker, spell_id)
    save_rolls_override = list(overrides.save_rolls if overrides else [])
    concentration_rolls_override = list(overrides.concentration_rolls if overrides else [])
    events: list[CombatEvent] = []

    if len(resolved_target_ids) > 1:
        events.append(
            CombatEvent(
                **event_base(state, attacker_id),
                target_ids=list(resolved_target_ids),
                event_type="phase_change",
                raw_rolls={},
                resolved_totals={
                    "spellId": spell_id,
                    "spellLevel": spell.level,
                    "targetCount": len(resolved_target_ids),
                    "maxTargets": spell.max_targets,
                    "targetClusterFeet": spell.target_cluster_feet,
                },
                movement_details=None,
                damage_details=None,
                condition_deltas=[],
                text_summary=f"{attacker_id} casts {spell.display_name} at {len(resolved_target_ids)} targets.",
            )
        )

    for resolved_target_id in resolved_target_ids:
        target = state.units[resolved_target_id]
        target_was_alive_before_hit = spell_target_was_alive_before_damage(target)
        save_mode, _, _ = get_saving_throw_mode(target, spell.save_ability or "con", state=state)
        save_roll_count = 1 if save_mode == "normal" else 2
        save_rolls = [
            save_rolls_override.pop(0) for _ in range(min(save_roll_count, len(save_rolls_override)))
        ]
        save_event = resolve_saving_throw(
            state,
            ResolveSavingThrowArgs(
                actor_id=resolved_target_id,
                ability=spell.save_ability or "con",
                dc=save_dc,
                reason=spell.display_name,
                overrides=SavingThrowOverrides(save_rolls=save_rolls),
            ),
        )
        save_success = bool(save_event.resolved_totals["success"])
        potent_cantrip_applied = save_success and can_apply_potent_cantrip(attacker, spell_id)
        if potent_cantrip_applied:
            applied_damage = max(1, full_damage // 2) if full_damage > 0 else 0
        else:
            applied_damage = 0 if save_success and not spell.half_on_success else full_damage // 2 if save_success else full_damage
        damage_components = build_spell_save_damage_component(damage_rolls, applied_damage, spell.damage_type)
        damage_result = (
            apply_damage(
                state,
                resolved_target_id,
                damage_components,
                False,
                concentration_save_rolls=concentration_rolls_override,
            )
            if applied_damage > 0
            else build_no_damage_result()
        )

        raw_rolls = {"damageRolls": list(damage_rolls)}
        attack_context = attack_contexts[resolved_target_id]
        resolved_totals = {
            "spellId": spell_id,
            "spellLevel": spell.level,
            "saveAbility": spell.save_ability,
            "saveDc": save_dc,
            "saveSucceeded": save_success,
            "fullDamage": full_damage,
            "halfOnSuccess": spell.half_on_success,
            "damageApplied": applied_damage,
            "targetCount": len(resolved_target_ids),
            "targetClusterFeet": spell.target_cluster_feet,
            "distanceSquares": attack_context.distance_squares,
            "distanceFeet": attack_context.distance_feet,
        }
        if potent_cantrip_applied:
            resolved_totals["potentCantripApplied"] = True
            resolved_totals["potentCantripDamage"] = applied_damage
            resolved_totals["potentCantripNoRider"] = True
        if spell.level > 0:
            resolved_totals[f"spellSlotsLevel{spell.level}Remaining"] = get_remaining_spell_slots(attacker, spell.level)
        attach_spell_target_outcome_fields(state, resolved_totals, resolved_target_id, target_was_alive_before_hit)
        attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)

        events.append(save_event)
        events.append(
            CombatEvent(
                **event_base(state, attacker_id),
                target_ids=[resolved_target_id],
                event_type="attack",
                raw_rolls=raw_rolls,
                resolved_totals=resolved_totals,
                movement_details=None,
                damage_details=DamageDetails(
                    weapon_id=spell_id,
                    weapon_name=spell.display_name,
                    damage_components=damage_components,
                    primary_candidate=None,
                    savage_candidate=None,
                    chosen_candidate=None,
                    critical_applied=False,
                    critical_multiplier=1,
                    flat_modifier=spell.damage_modifier,
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
                    f"{attacker_id}'s {spell.display_name} "
                    f"{'deals no damage to' if save_success else 'hits'} {resolved_target_id}"
                    f"{f' for {applied_damage} damage' if applied_damage > 0 else ''}"
                    f"{' after a successful save' if save_success else ' after a failed save'}."
                ),
            )
        )

    return events


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
    concentration_rolls_override = list(overrides.concentration_rolls if overrides else [])
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
        target_was_alive_before_hit = spell_target_was_alive_before_damage(target)
        save_mode, _, _ = get_saving_throw_mode(target, spell.save_ability or "dex", state=state)
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
            "spellId": "burning_hands",
            "spellLevel": 1,
            "saveAbility": spell.save_ability,
            "saveDc": save_dc,
            "saveSucceeded": save_success,
            "fullDamage": full_damage,
            "halfOnSuccess": spell.half_on_success,
        }
        attach_spell_target_outcome_fields(state, resolved_totals, resolved_target_id, target_was_alive_before_hit)
        attach_damage_result_event_fields(raw_rolls, resolved_totals, damage_result)
        events.append(
            CombatEvent(
                **event_base(state, attacker_id),
                target_ids=[resolved_target_id],
                event_type="attack",
                raw_rolls=raw_rolls,
                resolved_totals=resolved_totals,
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


def choose_bless_spell_level(actor: UnitState) -> int:
    if actor.class_id == "paladin" and (actor.level or 0) >= 5 and actor.resources.spell_slots_level_2 > 0:
        return 2
    return 1


def get_bless_max_targets_for_spell_level(spell_level: int) -> int:
    spell = get_spell_definition("bless")
    return spell.max_targets + max(0, spell_level - spell.level)


def get_legal_bless_target_ids(
    state: EncounterState,
    actor_id: str,
    target_ids: list[str],
    *,
    spell_level: int | None = None,
) -> list[str]:
    actor = state.units[actor_id]
    spell = get_spell_definition("bless")
    target_limit = get_bless_max_targets_for_spell_level(spell_level or choose_bless_spell_level(actor))
    legal_target_ids: list[str] = []
    seen_target_ids: set[str] = set()

    for target_id in target_ids:
        if target_id in seen_target_ids:
            continue
        seen_target_ids.add(target_id)
        target = state.units.get(target_id)
        if not target:
            continue
        if target.faction != actor.faction or target.conditions.dead:
            continue
        if not units_are_within_spell_range(state, actor_id, target_id, spell.range_feet):
            continue
        legal_target_ids.append(target_id)
        if len(legal_target_ids) >= target_limit:
            break

    return legal_target_ids


def resolve_bless(
    state: EncounterState,
    actor_id: str,
    target_ids: list[str],
    *,
    spell_level: int | None = None,
) -> CombatEvent:
    actor = state.units[actor_id]
    spell = get_spell_definition("bless")
    cast_level = spell_level or choose_bless_spell_level(actor)

    if not unit_has_combat_spell(actor, "bless"):
        return build_spell_skip_event(state, actor_id, "bless", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "bless", "cannot be cast while down.")
    if cast_level < spell.level:
        return build_spell_skip_event(state, actor_id, "bless", "cannot be cast below spell level.")

    legal_target_ids = get_legal_bless_target_ids(state, actor_id, target_ids, spell_level=cast_level)
    if not legal_target_ids:
        return build_spell_skip_event(state, actor_id, "bless", "has no legal targets.")
    if not spend_spell_slot(actor, cast_level):
        return build_spell_skip_event(state, actor_id, "bless", f"No level {cast_level} spell slots remain.")

    condition_deltas = end_concentration(
        state,
        actor_id,
        reason=f"{actor_id}'s prior concentration ends before casting {spell.display_name}.",
    )
    actor.temporary_effects.append(
        ConcentrationEffect(
            kind="concentration",
            source_id=actor_id,
            spell_id="bless",
            remaining_rounds=spell.duration_rounds,
        )
    )

    for target_id in legal_target_ids:
        target = state.units[target_id]
        target.temporary_effects = [
            effect
            for effect in target.temporary_effects
            if not (effect.kind == "blessed" and effect.source_id == actor_id)
        ]
        target.temporary_effects.append(BlessedEffect(kind="blessed", source_id=actor_id))

    condition_deltas.append(f"{actor_id} blesses {', '.join(legal_target_ids)}.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=legal_target_ids,
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "bless",
            "spellLevel": cast_level,
            "concentration": True,
            "durationRounds": spell.duration_rounds,
            "blessedTargetIds": legal_target_ids,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
            "spellSlotsLevel2Remaining": actor.resources.spell_slots_level_2,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} casts {spell.display_name} on {', '.join(legal_target_ids)}.",
    )


def resolve_cure_wounds(
    state: EncounterState,
    actor_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("cure_wounds")

    if not unit_has_combat_spell(actor, "cure_wounds"):
        return build_spell_skip_event(state, actor_id, "cure_wounds", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "cure_wounds", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "cure_wounds", "target is unavailable.")
    if target.faction != actor.faction or target.conditions.dead:
        return build_spell_skip_event(state, actor_id, "cure_wounds", "target is not a living ally.")
    if not units_are_touch_reachable(state, actor_id, target_id):
        return build_spell_skip_event(state, actor_id, "cure_wounds", "target is not within touch range.")
    if target.current_hp >= target.max_hp:
        return build_spell_skip_event(state, actor_id, "cure_wounds", "target does not need healing.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "cure_wounds", "No level 1 spell slots remain.")

    healing_roll_overrides = list(overrides.damage_rolls if overrides else [])
    healing_rolls = [
        pull_die(state, dice.sides, healing_roll_overrides.pop(0) if healing_roll_overrides else None)
        for dice in spell.healing_dice
        for _ in range(dice.count)
    ]
    healing_modifier = get_ability_modifier(actor, resolve_spell_ability(actor, spell.healing_modifier_ability))
    healing_total = sum(healing_rolls) + healing_modifier
    healed, condition_deltas = apply_healing_to_unit(target, healing_total)

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="heal",
        raw_rolls={"healingRolls": healing_rolls},
        resolved_totals={
            "spellId": "cure_wounds",
            "spellLevel": spell.level,
            "healingModifier": healing_modifier,
            "healingTotal": healed,
            "currentHp": target.current_hp,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} casts {spell.display_name} on {target_id}, restoring {healed} HP.",
    )


def get_legal_aid_target_ids(state: EncounterState, actor_id: str, target_ids: list[str]) -> list[str]:
    actor = state.units[actor_id]
    spell = get_spell_definition("aid")
    legal_target_ids: list[str] = []
    seen_target_ids: set[str] = set()

    for target_id in target_ids:
        if target_id in seen_target_ids:
            continue
        seen_target_ids.add(target_id)
        target = state.units.get(target_id)
        if not target:
            continue
        if target.faction != actor.faction or target.conditions.dead:
            continue
        if not units_are_within_spell_range(state, actor_id, target_id, spell.range_feet):
            continue
        legal_target_ids.append(target_id)
        if len(legal_target_ids) >= spell.max_targets:
            break

    return legal_target_ids


def get_active_aid_bonus(unit: UnitState) -> int:
    return max((effect.hp_bonus for effect in unit.temporary_effects if effect.kind == "aid"), default=0)


def resolve_aid(state: EncounterState, actor_id: str, target_ids: list[str]) -> CombatEvent:
    actor = state.units[actor_id]
    spell = get_spell_definition("aid")

    if not unit_has_combat_spell(actor, "aid"):
        return build_spell_skip_event(state, actor_id, "aid", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "aid", "cannot be cast while down.")

    legal_target_ids = get_legal_aid_target_ids(state, actor_id, target_ids)
    if not legal_target_ids:
        return build_spell_skip_event(state, actor_id, "aid", "has no legal targets.")
    if not spend_spell_slot(actor, 2):
        return build_spell_skip_event(state, actor_id, "aid", "No level 2 spell slots remain.")

    total_current_hp_added = 0
    applied_target_ids: list[str] = []
    condition_deltas: list[str] = []
    for target_id in legal_target_ids:
        target = state.units[target_id]
        existing_bonus = get_active_aid_bonus(target)
        if existing_bonus >= spell.hp_bonus:
            condition_deltas.append(f"{target_id} is already bolstered by Aid.")
            continue

        bonus_delta = spell.hp_bonus - existing_bonus
        target.max_hp += bonus_delta
        healed, healing_deltas = apply_healing_to_unit(target, bonus_delta)
        total_current_hp_added += healed
        target.temporary_effects = [effect for effect in target.temporary_effects if effect.kind != "aid"]
        target.temporary_effects.append(
            AidEffect(
                kind="aid",
                source_id=actor_id,
                hp_bonus=spell.hp_bonus,
                remaining_rounds=spell.duration_rounds,
            )
        )
        applied_target_ids.append(target_id)
        condition_deltas.extend(healing_deltas)
        condition_deltas.append(f"{target_id}'s maximum HP increases by {bonus_delta}.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=legal_target_ids,
        event_type="heal",
        raw_rolls={},
        resolved_totals={
            "spellId": "aid",
            "spellLevel": spell.level,
            "aidHpBonus": spell.hp_bonus,
            "aidTargetIds": legal_target_ids,
            "aidAppliedTargetIds": applied_target_ids,
            "healingTotal": total_current_hp_added,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel2Remaining": actor.resources.spell_slots_level_2,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} casts {spell.display_name} on {', '.join(legal_target_ids)}.",
    )


def resolve_mage_armor(state: EncounterState, actor_id: str, target_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("mage_armor")

    if not unit_has_combat_spell(actor, "mage_armor"):
        return build_spell_skip_event(state, actor_id, "mage_armor", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "mage_armor", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "mage_armor", "target is unavailable.")
    if target_id != actor_id:
        return build_spell_skip_event(state, actor_id, "mage_armor", "can only target self.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "mage_armor", "No level 1 spell slots remain.")

    # UnitState has no equipment or worn-armor field yet, so this cannot reject
    # armored targets. Apply only as a beneficial AC floor.
    previous_ac = target.ac
    mage_armor_ac = 13 + target.ability_mods.dex
    target.ac = max(target.ac, mage_armor_ac)
    ac_changed = target.ac != previous_ac

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "mage_armor",
            "spellLevel": spell.level,
            "previousAc": previous_ac,
            "mageArmorAc": mage_armor_ac,
            "newAc": target.ac,
            "acChanged": ac_changed,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[
            f"{target_id}'s AC becomes {target.ac}."
            if ac_changed
            else f"{target_id}'s AC remains {target.ac}."
        ],
        text_summary=f"{actor_id} casts {spell.display_name} on {target_id}.",
    )


def resolve_false_life(
    state: EncounterState,
    actor_id: str,
    target_id: str,
    overrides: AttackRollOverrides | None = None,
) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("false_life")

    if not unit_has_combat_spell(actor, "false_life"):
        return build_spell_skip_event(state, actor_id, "false_life", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "false_life", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "false_life", "target is unavailable.")
    if target_id != actor_id:
        return build_spell_skip_event(state, actor_id, "false_life", "can only target self.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "false_life", "No level 1 spell slots remain.")

    roll_overrides = list(overrides.damage_rolls if overrides else [])
    temporary_hp_rolls = [
        pull_die(state, dice.sides, roll_overrides.pop(0) if roll_overrides else None)
        for dice in spell.temporary_hit_point_dice
        for _ in range(dice.count)
    ]
    temporary_hp_total = sum(temporary_hp_rolls) + spell.temporary_hit_point_modifier
    previous_temporary_hp = target.temporary_hit_points
    target.temporary_hit_points = max(target.temporary_hit_points, temporary_hp_total)
    temporary_hp_gained = target.temporary_hit_points - previous_temporary_hp

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={"temporaryHitPointRolls": temporary_hp_rolls},
        resolved_totals={
            "spellId": "false_life",
            "spellLevel": spell.level,
            "temporaryHitPointModifier": spell.temporary_hit_point_modifier,
            "temporaryHitPointTotal": temporary_hp_total,
            "previousTemporaryHitPoints": previous_temporary_hp,
            "temporaryHitPointsGained": temporary_hp_gained,
            "newTemporaryHitPoints": target.temporary_hit_points,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[
            f"{target_id} gains {temporary_hp_gained} temporary HP."
            if temporary_hp_gained > 0
            else f"{target_id}'s temporary HP remains {target.temporary_hit_points}."
        ],
        text_summary=f"{actor_id} casts {spell.display_name} and gains {temporary_hp_gained} temporary HP.",
    )


def resolve_longstrider(state: EncounterState, actor_id: str, target_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("longstrider")

    if not unit_has_combat_spell(actor, "longstrider"):
        return build_spell_skip_event(state, actor_id, "longstrider", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "longstrider", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "longstrider", "target is unavailable.")
    if target.faction != actor.faction or target.conditions.dead:
        return build_spell_skip_event(state, actor_id, "longstrider", "target is not a living ally.")
    if not units_are_touch_reachable(state, actor_id, target_id):
        return build_spell_skip_event(state, actor_id, "longstrider", "target is not within touch range.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "longstrider", "No level 1 spell slots remain.")

    previous_speed_bonus = target.longstrider_speed_bonus
    previous_effective_speed = target.effective_speed
    target.longstrider_speed_bonus = max(target.longstrider_speed_bonus, spell.speed_bonus)
    recalculate_effective_speed_for_unit(target)
    speed_changed = target.effective_speed != previous_effective_speed

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "longstrider",
            "spellLevel": spell.level,
            "speedBonus": spell.speed_bonus,
            "previousSpeedBonus": previous_speed_bonus,
            "newSpeedBonus": target.longstrider_speed_bonus,
            "previousEffectiveSpeed": previous_effective_speed,
            "newEffectiveSpeed": target.effective_speed,
            "speedChanged": speed_changed,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[
            f"{target_id}'s speed becomes {target.effective_speed} feet."
            if speed_changed
            else f"{target_id}'s speed remains {target.effective_speed} feet."
        ],
        text_summary=f"{actor_id} casts {spell.display_name} on {target_id}.",
    )


def resolve_shield_of_faith(state: EncounterState, actor_id: str, target_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("shield_of_faith")

    if not unit_has_combat_spell(actor, "shield_of_faith"):
        return build_spell_skip_event(state, actor_id, "shield_of_faith", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "shield_of_faith", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "shield_of_faith", "target is unavailable.")
    if target.faction != actor.faction or target.conditions.dead:
        return build_spell_skip_event(state, actor_id, "shield_of_faith", "target is not a living ally.")
    if not units_are_within_spell_range(state, actor_id, target_id, spell.range_feet):
        return build_spell_skip_event(state, actor_id, "shield_of_faith", "target is not within 60 feet.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "shield_of_faith", "No level 1 spell slots remain.")

    previous_shield_of_faith_bonus = get_shield_of_faith_ac_bonus(target)
    previous_effective_ac = target.ac + get_shield_ac_bonus(target)
    condition_deltas = end_concentration(
        state,
        actor_id,
        reason=f"{actor_id}'s prior concentration ends before casting {spell.display_name}.",
    )

    actor.temporary_effects.append(
        ConcentrationEffect(
            kind="concentration",
            source_id=actor_id,
            spell_id="shield_of_faith",
            remaining_rounds=spell.duration_rounds,
        )
    )
    target.temporary_effects = [
        effect
        for effect in target.temporary_effects
        if not (effect.kind == "shield_of_faith" and effect.source_id == actor_id)
    ]
    target.temporary_effects.append(
        ShieldOfFaithEffect(kind="shield_of_faith", source_id=actor_id, ac_bonus=spell.ac_bonus)
    )

    new_shield_of_faith_bonus = get_shield_of_faith_ac_bonus(target)
    new_effective_ac = target.ac + get_shield_ac_bonus(target)
    condition_deltas.append(f"{target_id} gains +{spell.ac_bonus} AC from {spell.display_name}.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "shield_of_faith",
            "spellLevel": spell.level,
            "concentration": True,
            "acBonus": spell.ac_bonus,
            "previousShieldOfFaithBonus": previous_shield_of_faith_bonus,
            "newShieldOfFaithBonus": new_shield_of_faith_bonus,
            "previousEffectiveAc": previous_effective_ac,
            "newEffectiveAc": new_effective_ac,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} casts {spell.display_name} on {target_id}.",
    )


def apply_heroism_start_of_turn(state: EncounterState, actor_id: str) -> CombatEvent | None:
    actor = state.units[actor_id]
    effect = get_active_heroism_effect(state, actor)
    if not effect or actor.conditions.dead:
        return None

    previous_temporary_hp = actor.temporary_hit_points
    actor.temporary_hit_points = max(actor.temporary_hit_points, effect.temporary_hit_points)
    temporary_hp_gained = actor.temporary_hit_points - previous_temporary_hp

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "heroism",
            "trigger": "turn_start",
            "sourceId": effect.source_id,
            "temporaryHitPointTotal": effect.temporary_hit_points,
            "previousTemporaryHitPoints": previous_temporary_hp,
            "temporaryHitPointsGained": temporary_hp_gained,
            "newTemporaryHitPoints": actor.temporary_hit_points,
            "frightenedImmunityModeled": effect.frightened_immunity_modeled,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=[
            f"{actor_id} gains {temporary_hp_gained} temporary HP from Heroism."
            if temporary_hp_gained > 0
            else f"{actor_id}'s temporary HP remains {actor.temporary_hit_points}."
        ],
        text_summary=f"{actor_id} gains {temporary_hp_gained} temporary HP from Heroism.",
    )


def resolve_heroism(state: EncounterState, actor_id: str, target_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("heroism")

    if not unit_has_combat_spell(actor, "heroism"):
        return build_spell_skip_event(state, actor_id, "heroism", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "heroism", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "heroism", "target is unavailable.")
    if target.faction != actor.faction or target.conditions.dead:
        return build_spell_skip_event(state, actor_id, "heroism", "target is not a living ally.")
    if not units_are_touch_reachable(state, actor_id, target_id):
        return build_spell_skip_event(state, actor_id, "heroism", "target is not within touch range.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "heroism", "No level 1 spell slots remain.")

    spellcasting_ability = get_spellcasting_ability(actor)
    temporary_hp_amount = max(0, get_ability_modifier(actor, spellcasting_ability))
    condition_deltas = end_concentration(
        state,
        actor_id,
        reason=f"{actor_id}'s prior concentration ends before casting {spell.display_name}.",
    )
    actor.temporary_effects.append(
        ConcentrationEffect(
            kind="concentration",
            source_id=actor_id,
            spell_id="heroism",
            remaining_rounds=spell.duration_rounds,
        )
    )
    target.temporary_effects = [
        effect
        for effect in target.temporary_effects
        if not (effect.kind == "heroism" and effect.source_id == actor_id)
    ]
    removed_frightened_count = clear_frightened_effects(target)
    target.temporary_effects.append(
        HeroismEffect(
            kind="heroism",
            source_id=actor_id,
            temporary_hit_points=temporary_hp_amount,
            frightened_immunity_modeled=True,
        )
    )
    condition_deltas.append(
        f"{target_id} will gain {temporary_hp_amount} temporary HP at the start of each turn from {spell.display_name}."
    )
    if removed_frightened_count:
        condition_deltas.append(f"{target_id} is no longer frightened.")

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[target_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "heroism",
            "spellLevel": spell.level,
            "concentration": True,
            "targetId": target_id,
            "spellcastingAbility": spellcasting_ability,
            "temporaryHitPointAmount": temporary_hp_amount,
            "startOfTurnUpkeep": True,
            "immediateTemporaryHitPointsApplied": False,
            "frightenedImmunityModeled": True,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} casts {spell.display_name} on {target_id}.",
    )


def resolve_divine_favor(state: EncounterState, actor_id: str, target_id: str) -> CombatEvent:
    actor = state.units[actor_id]
    target = state.units.get(target_id)
    spell = get_spell_definition("divine_favor")

    if not unit_has_combat_spell(actor, "divine_favor"):
        return build_spell_skip_event(state, actor_id, "divine_favor", "is not prepared.")
    if actor.current_hp <= 0 or actor.conditions.dead or actor.conditions.unconscious:
        return build_spell_skip_event(state, actor_id, "divine_favor", "cannot be cast while down.")
    if not target:
        return build_spell_skip_event(state, actor_id, "divine_favor", "target is unavailable.")
    if target_id != actor_id:
        return build_spell_skip_event(state, actor_id, "divine_favor", "can only target self.")
    if not actor.resources.spend_pool("spell_slots_level_1", 1):
        return build_spell_skip_event(state, actor_id, "divine_favor", "No level 1 spell slots remain.")

    previous_active = get_active_divine_favor_effect(actor) is not None
    condition_deltas = end_concentration(
        state,
        actor_id,
        reason=f"{actor_id}'s prior concentration ends before casting {spell.display_name}.",
    )
    actor.temporary_effects.append(
        ConcentrationEffect(
            kind="concentration",
            source_id=actor_id,
            spell_id="divine_favor",
            remaining_rounds=spell.duration_rounds,
        )
    )
    actor.temporary_effects = [
        effect
        for effect in actor.temporary_effects
        if not (effect.kind == "divine_favor" and effect.source_id == actor_id)
    ]
    damage_die = spell.damage_dice[0]
    actor.temporary_effects.append(
        DivineFavorEffect(
            kind="divine_favor",
            source_id=actor_id,
            damage_die_count=damage_die.count,
            damage_die_sides=damage_die.sides,
            damage_type=spell.damage_type,
        )
    )
    condition_deltas.append(
        f"{actor_id}'s weapon attacks deal an extra {damage_die.count}d{damage_die.sides} {spell.damage_type} damage."
    )

    return CombatEvent(
        **event_base(state, actor_id),
        target_ids=[actor_id],
        event_type="phase_change",
        raw_rolls={},
        resolved_totals={
            "spellId": "divine_favor",
            "spellLevel": spell.level,
            "concentration": True,
            "previousActive": previous_active,
            "damageDieCount": damage_die.count,
            "damageDieSides": damage_die.sides,
            "damageType": spell.damage_type,
            "durationRounds": spell.duration_rounds,
            "spellSlotsLevel1Remaining": actor.resources.spell_slots_level_1,
        },
        movement_details=None,
        damage_details=None,
        condition_deltas=condition_deltas,
        text_summary=f"{actor_id} casts {spell.display_name}.",
    )


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

    if (
        spell.level > 0
        and spell_id in actor.prepared_combat_spell_ids
        and get_remaining_spell_slots(actor, spell.level) <= 0
    ):
        return build_spell_skip_event(state, actor_id, spell_id, f"No level {spell.level} spell slots remain.")

    if spell.targeting_mode in {"ranged_spell_attack", "melee_spell_attack"}:
        return resolve_ranged_spell_attack(state, actor_id, target_id, spell_id, overrides)
    if spell.targeting_mode == "auto_hit_single_target":
        return resolve_magic_missile(state, actor_id, target_id, overrides)
    if spell.targeting_mode == "multi_ally_buff":
        return resolve_bless(state, actor_id, [target_id])
    if spell.targeting_mode == "touch_heal":
        return resolve_cure_wounds(state, actor_id, target_id, overrides)
    if spell.targeting_mode == "multi_ally_hp_buff":
        return resolve_aid(state, actor_id, [target_id])
    if spell.targeting_mode == "self_ac_buff":
        return resolve_mage_armor(state, actor_id, target_id)
    if spell.targeting_mode == "self_temp_hp":
        return resolve_false_life(state, actor_id, target_id, overrides)
    if spell.targeting_mode == "touch_speed_buff":
        return resolve_longstrider(state, actor_id, target_id)
    if spell.targeting_mode == "ranged_ally_ac_buff":
        return resolve_shield_of_faith(state, actor_id, target_id)
    if spell.targeting_mode == "touch_heroism_buff":
        return resolve_heroism(state, actor_id, target_id)
    if spell.targeting_mode == "self_weapon_damage_buff":
        return resolve_divine_favor(state, actor_id, target_id)
    if spell.targeting_mode == "single_target_save":
        return resolve_single_target_save_spell(state, actor_id, target_id, spell_id, overrides)[-1]
    if spell.targeting_mode == "multi_target_save":
        return resolve_multi_target_save_spell(state, actor_id, [target_id], spell_id, overrides)[-1]

    return build_spell_skip_event(state, actor_id, spell_id, "cannot be resolved by the live simulator.")
