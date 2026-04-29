from __future__ import annotations

from dataclasses import dataclass

from backend.content.class_progressions import get_proficiency_bonus
from backend.content.spell_definitions import get_spell_definition
from backend.engine.models.state import (
    CombatEvent,
    DamageCandidate,
    DamageComponentResult,
    EncounterState,
    UnitState,
)


class AttackRollOverrides:
    def __init__(
        self,
        *,
        attack_rolls: list[int] | None = None,
        damage_rolls: list[int] | None = None,
        save_rolls: list[int] | None = None,
        savage_damage_rolls: list[int] | None = None,
        advantage_damage_rolls: list[int] | None = None,
        superiority_rolls: list[int] | None = None,
        smite_damage_rolls: list[int] | None = None,
        divine_favor_damage_rolls: list[int] | None = None,
        concentration_rolls: list[int] | None = None,
        counterspell_rolls: list[int] | None = None,
    ) -> None:
        self.attack_rolls = attack_rolls or []
        self.damage_rolls = damage_rolls or []
        self.save_rolls = save_rolls or []
        self.savage_damage_rolls = savage_damage_rolls or []
        self.advantage_damage_rolls = advantage_damage_rolls or []
        self.superiority_rolls = superiority_rolls or []
        self.smite_damage_rolls = smite_damage_rolls or []
        self.divine_favor_damage_rolls = divine_favor_damage_rolls or []
        self.concentration_rolls = concentration_rolls or []
        self.counterspell_rolls = counterspell_rolls or []


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
    damage_prevented: int = 0
    damage_mitigation_source: str | None = None
    concentration_save_rolls: list[int] | None = None
    concentration_save_total: int | None = None
    concentration_save_dc: int | None = None
    concentration_save_success: bool | None = None
    concentration_spell_id: str | None = None
    concentration_ended: bool = False
    concentration_bless_rolls: list[int] | None = None
    concentration_bless_bonus: int = 0
    concentration_bless_source_id: str | None = None


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


def get_spellcasting_ability(unit: UnitState) -> str:
    if unit.class_id == "paladin":
        return "cha"
    return "int"


def resolve_spell_ability(unit: UnitState, ability: str | None) -> str:
    if ability == "spellcasting" or ability is None:
        return get_spellcasting_ability(unit)
    return ability


def get_unit_spell_save_dc(caster: UnitState, ability: str | None = None) -> int:
    return 8 + get_proficiency_bonus(caster.level or 1) + get_ability_modifier(
        caster,
        resolve_spell_ability(caster, ability),
    )


def get_spell_save_dc(caster: UnitState, spell_id: str) -> int:
    spell = get_spell_definition(spell_id)
    return get_unit_spell_save_dc(caster, resolve_spell_ability(caster, spell.attack_ability))


def spend_spell_slot(unit: UnitState, spell_level: int) -> bool:
    return unit.resources.spend_pool(f"spell_slots_level_{spell_level}", 1)


def get_remaining_spell_slots(unit: UnitState, spell_level: int) -> int:
    return unit.resources.get_pool(f"spell_slots_level_{spell_level}")


def apply_healing_to_unit(target: UnitState, healing_total: int) -> tuple[int, list[str]]:
    if target.conditions.dead or healing_total <= 0:
        return 0, []
    if any(effect.kind == "healing_blocked" for effect in target.temporary_effects):
        return 0, [f"{target.id} cannot regain HP until the start of the caster's next turn."]

    healed = min(target.max_hp - target.current_hp, healing_total)
    if healed <= 0:
        return 0, []

    was_downed = target.current_hp == 0
    target.current_hp += healed
    condition_deltas: list[str] = []
    if was_downed:
        target.conditions.unconscious = False
        target.conditions.prone = False
        target.stable = False
        target.death_save_failures = 0
        target.death_save_successes = 0
        condition_deltas.append(f"{target.id} returns to consciousness.")

    return healed, condition_deltas


def attach_damage_result_event_fields(
    raw_rolls: dict[str, object],
    resolved_totals: dict[str, object],
    damage_result: DamageApplicationResult,
) -> None:
    if damage_result.concentration_save_rolls:
        raw_rolls["concentrationSaveRolls"] = damage_result.concentration_save_rolls
    if damage_result.concentration_bless_rolls:
        raw_rolls["concentrationBlessRolls"] = damage_result.concentration_bless_rolls
    if damage_result.concentration_spell_id:
        resolved_totals["concentrationSpellId"] = damage_result.concentration_spell_id
        resolved_totals["concentrationSaveDc"] = damage_result.concentration_save_dc
        resolved_totals["concentrationSaveTotal"] = damage_result.concentration_save_total
        resolved_totals["concentrationSaveSuccess"] = damage_result.concentration_save_success
        resolved_totals["concentrationEnded"] = damage_result.concentration_ended
        if damage_result.concentration_bless_bonus:
            resolved_totals["concentrationBlessBonus"] = damage_result.concentration_bless_bonus
            resolved_totals["concentrationBlessSourceId"] = damage_result.concentration_bless_source_id


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
