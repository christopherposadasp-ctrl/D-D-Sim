from __future__ import annotations

import pytest

from backend.content.enemies import (
    BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT,
    BENCHMARK_MONSTER_COUNTS,
    MONSTER_DEFINITIONS,
    create_enemy,
    get_enemy_preset,
    get_unit_bonus_action_ids,
    get_unit_reaction_ids,
    unit_has_creature_tag,
    unit_is_undead,
)
from backend.engine.models.state import WeaponDamageComponent, WeaponProfile
from tests.rules.monster_expectations import MONSTER_EXPECTATIONS, REMAINING_MONSTER_IDS


def serialize_damage_components(
    components: list[WeaponDamageComponent] | tuple[WeaponDamageComponent, ...] | None,
) -> tuple[tuple[str, tuple[tuple[int, int], ...], int], ...]:
    if not components:
        return ()
    return tuple(
        (
            component.damage_type,
            tuple((die.count, die.sides) for die in component.damage_dice),
            component.damage_modifier,
        )
        for component in components
    )


def serialize_weapon_profile(weapon: WeaponProfile) -> dict[str, object]:
    return {
        "kind": weapon.kind,
        "attack_bonus": weapon.attack_bonus,
        "ability_modifier": weapon.ability_modifier,
        "damage_modifier": weapon.damage_modifier,
        "damage_type": weapon.damage_type,
        "selectable_damage_types": tuple(weapon.selectable_damage_types or ()),
        "reach": weapon.reach,
        "range": None if weapon.range is None else (weapon.range.normal, weapon.range.long),
        "damage_dice": tuple((die.count, die.sides) for die in weapon.damage_dice),
        "advantage_damage_dice": tuple((die.count, die.sides) for die in weapon.advantage_damage_dice or ()),
        "damage_components": serialize_damage_components(weapon.damage_components),
        "advantage_damage_components": serialize_damage_components(weapon.advantage_damage_components),
        "advantage_against_self_grappled_target": bool(weapon.advantage_against_self_grappled_target),
    }


@pytest.mark.parametrize("variant_id", REMAINING_MONSTER_IDS)
def test_remaining_monster_roster_matches_expectation_table(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    definition = MONSTER_DEFINITIONS[variant_id]
    preset = get_enemy_preset(expectation.benchmark_preset_id)

    assert BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT[variant_id] == expectation.benchmark_preset_id
    assert BENCHMARK_MONSTER_COUNTS[variant_id] == expectation.benchmark_count
    assert BENCHMARK_MONSTER_COUNTS[variant_id] == max(1, min(15, round(100 / definition.max_hp)))

    assert preset.preset_id == expectation.benchmark_preset_id
    assert len(preset.units) == expectation.benchmark_count
    assert all(unit.variant_id == variant_id for unit in preset.units)

    assert definition.ai_profile_id == expectation.ai_profile_id
    assert definition.max_hp == expectation.max_hp
    assert definition.ac == expectation.ac
    assert definition.speed == expectation.speed
    assert definition.initiative_mod == expectation.initiative_mod
    assert definition.passive_perception == expectation.passive_perception
    assert definition.size_category == expectation.size_category
    assert (definition.footprint.width, definition.footprint.height) == expectation.footprint
    assert definition.ability_mods.model_dump() == expectation.ability_mods
    assert tuple(definition.trait_ids) == expectation.trait_ids
    assert tuple(definition.role_tags) == expectation.role_tags
    assert tuple(definition.special_action_ids) == expectation.special_action_ids
    assert tuple(definition.damage_resistances) == expectation.damage_resistances
    assert tuple(definition.damage_immunities) == expectation.damage_immunities
    assert tuple(definition.damage_vulnerabilities) == expectation.damage_vulnerabilities
    assert tuple(definition.condition_immunities) == expectation.condition_immunities
    assert tuple(definition.creature_tags) == expectation.creature_tags
    assert tuple(definition.movement_modes) == expectation.movement_modes
    runtime_unit = create_enemy("E1", variant_id)
    assert tuple(get_unit_bonus_action_ids(runtime_unit)) == expectation.bonus_action_ids
    assert tuple(get_unit_reaction_ids(runtime_unit)) == expectation.reaction_ids
    assert tuple(runtime_unit.creature_tags) == expectation.creature_tags
    assert tuple(runtime_unit.condition_immunities) == expectation.condition_immunities
    assert tuple(runtime_unit.movement_modes) == expectation.movement_modes
    assert tuple(runtime_unit.role_tags) == expectation.role_tags
    for pool_id, expected_uses in expectation.resource_pools:
        assert runtime_unit.resource_pools.get(pool_id) == expected_uses
    assert unit_has_creature_tag(runtime_unit, "undead") is ("undead" in expectation.creature_tags)
    assert unit_is_undead(runtime_unit) is ("undead" in expectation.creature_tags)

    assert set(definition.attacks) == set(expectation.attacks)
    for weapon_id, attack_expectation in expectation.attacks.items():
        assert serialize_weapon_profile(definition.attacks[weapon_id]) == {
            "kind": attack_expectation.kind,
            "attack_bonus": attack_expectation.attack_bonus,
            "ability_modifier": attack_expectation.ability_modifier,
            "damage_modifier": attack_expectation.damage_modifier,
            "damage_type": attack_expectation.damage_type,
            "selectable_damage_types": attack_expectation.selectable_damage_types,
            "reach": attack_expectation.reach,
            "range": attack_expectation.range,
            "damage_dice": attack_expectation.damage_dice,
            "advantage_damage_dice": attack_expectation.advantage_damage_dice,
            "damage_components": tuple(
                (component.damage_type, component.damage_dice, component.damage_modifier)
                for component in attack_expectation.damage_components
            ),
            "advantage_damage_components": tuple(
                (component.damage_type, component.damage_dice, component.damage_modifier)
                for component in attack_expectation.advantage_damage_components
            ),
            "advantage_against_self_grappled_target": attack_expectation.advantage_against_self_grappled_target,
        }

    if "pack_tactics" in expectation.special_mechanics:
        assert "pack_tactics" in definition.trait_ids

    if "sunlight_sensitivity" in expectation.special_mechanics:
        assert "sunlight_sensitivity" in definition.trait_ids

    if "selectable_damage" in expectation.special_mechanics:
        chromatic_bolt = definition.attacks["chromatic_bolt"]
        assert tuple(chromatic_bolt.selectable_damage_types or ()) == (
            "acid",
            "cold",
            "fire",
            "lightning",
            "poison",
            "thunder",
        )

    if "advantage_poison" in expectation.special_mechanics:
        longbow = definition.attacks["longbow"]
        assert serialize_damage_components(longbow.advantage_damage_components) == (("poison", ((3, 4),), 0),)

    if "advantage_damage" in expectation.special_mechanics:
        for weapon_id in ("scimitar", "shortbow"):
            weapon = definition.attacks[weapon_id]
            assert tuple((die.count, die.sides) for die in weapon.advantage_damage_dice or ()) == ((1, 4),)

    if "split_damage" in expectation.special_mechanics:
        ritual_sickle = definition.attacks["ritual_sickle"]
        assert serialize_damage_components(ritual_sickle.damage_components) == (
            ("slashing", ((1, 4),), 1),
            ("necrotic", (), 1),
        )

    if "harry_target" in expectation.special_mechanics:
        bite = definition.attacks["bite"]
        assert bite.on_hit_effects is not None
        assert [effect.kind for effect in bite.on_hit_effects] == ["harry_target"]

    if "prone_on_hit" in expectation.special_mechanics:
        weapon_id = "bite"
        if variant_id == "brown_bear":
            weapon_id = "claw"
        elif variant_id == "tiger":
            weapon_id = "rend"
        elif variant_id == "ankylosaurus":
            weapon_id = "tail"
        elif variant_id == "warhorse_skeleton":
            weapon_id = "hooves"
        weapon = definition.attacks[weapon_id]
        assert weapon.on_hit_effects is not None
        assert [effect.kind for effect in weapon.on_hit_effects] == ["prone_on_hit"]

    if "multiattack" in expectation.special_mechanics:
        multiattack = next(action for action in definition.attack_actions if action.action_id == "multiattack")
        assert definition.default_melee_attack_action_id == "multiattack"
        expected_step_count = 3 if "triple_multiattack" in expectation.special_mechanics else 2
        assert len(multiattack.steps) == expected_step_count

    if "parry" in expectation.special_mechanics:
        assert tuple(get_unit_reaction_ids(runtime_unit)) == ("opportunity_attack", "parry")

    if "redirect_attack" in expectation.special_mechanics:
        assert tuple(get_unit_reaction_ids(runtime_unit)) == ("opportunity_attack", "redirect_attack")

    if "bloodied_frenzy" in expectation.special_mechanics:
        assert "bloodied_frenzy" in definition.trait_ids

    if "rampage" in expectation.special_mechanics:
        assert tuple(get_unit_bonus_action_ids(runtime_unit)) == ("rampage",)
        assert runtime_unit.resource_pools.get("rampage_uses") == 1

    if "nimble_escape" in expectation.special_mechanics:
        assert tuple(get_unit_bonus_action_ids(runtime_unit)) == ("disengage",)

    if "undead_fortitude" in expectation.special_mechanics:
        assert "undead_fortitude" in definition.trait_ids

    if "ice_walk" in expectation.special_mechanics:
        assert "ice_walk" in definition.trait_ids

    if "cold_breath" in expectation.special_mechanics:
        assert "cold_breath" in definition.special_action_ids
        assert runtime_unit.resource_pools.get("cold_breath_available") == 1

    if "grappled_target_advantage" in expectation.special_mechanics:
        hammer = definition.attacks["light_hammer"]
        thrown_hammer = definition.attacks["light_hammer_throw"]
        assert hammer.advantage_against_self_grappled_target is True
        assert thrown_hammer.advantage_against_self_grappled_target is True

    if "grapple_on_hit" in expectation.special_mechanics:
        grapple_expectations = {
            "bugbear_warrior": ("grab", 12),
            "giant_crab": ("claw", 11),
            "grick": ("tentacles", 12),
            "griffon": ("rend", 14),
        }
        weapon_id, expected_escape_dc = grapple_expectations[variant_id]
        weapon = definition.attacks[weapon_id]
        assert weapon.on_hit_effects is not None
        assert [(effect.kind, effect.max_target_size, effect.escape_dc) for effect in weapon.on_hit_effects] == [
            ("grapple_on_hit", "medium", expected_escape_dc)
        ]

    if "opening_flight_landing" in expectation.special_mechanics:
        assert "opening_flight_landing" in definition.trait_ids
        assert runtime_unit.resource_pools.get("opening_landing_uses") == 1

    if "prone_on_hit" in expectation.special_mechanics and variant_id in {
        "brown_bear",
        "tiger",
        "mastiff",
        "ankylosaurus",
        "warhorse_skeleton",
    }:
        if variant_id == "brown_bear":
            weapon_id = "claw"
        elif variant_id == "tiger":
            weapon_id = "rend"
        elif variant_id == "mastiff":
            weapon_id = "bite"
        elif variant_id == "warhorse_skeleton":
            weapon_id = "hooves"
        else:
            weapon_id = "tail"
        expected_size = (
            "huge"
            if variant_id == "ankylosaurus"
            else "large"
            if variant_id in {"brown_bear", "tiger", "warhorse_skeleton"}
            else "medium"
        )
        weapon = definition.attacks[weapon_id]
        assert weapon.on_hit_effects is not None
        assert [(effect.kind, effect.max_target_size) for effect in weapon.on_hit_effects] == [
            ("prone_on_hit", expected_size)
        ]
