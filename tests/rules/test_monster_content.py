from __future__ import annotations

import pytest

from backend.content.enemies import (
    BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT,
    BENCHMARK_MONSTER_COUNTS,
    MONSTER_DEFINITIONS,
    get_enemy_preset,
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
        "reach": weapon.reach,
        "range": None if weapon.range is None else (weapon.range.normal, weapon.range.long),
        "damage_dice": tuple((die.count, die.sides) for die in weapon.damage_dice),
        "damage_components": serialize_damage_components(weapon.damage_components),
        "advantage_damage_components": serialize_damage_components(weapon.advantage_damage_components),
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

    assert set(definition.attacks) == set(expectation.attacks)
    for weapon_id, attack_expectation in expectation.attacks.items():
        assert serialize_weapon_profile(definition.attacks[weapon_id]) == {
            "kind": attack_expectation.kind,
            "attack_bonus": attack_expectation.attack_bonus,
            "ability_modifier": attack_expectation.ability_modifier,
            "damage_modifier": attack_expectation.damage_modifier,
            "damage_type": attack_expectation.damage_type,
            "reach": attack_expectation.reach,
            "range": attack_expectation.range,
            "damage_dice": attack_expectation.damage_dice,
            "damage_components": tuple(
                (component.damage_type, component.damage_dice, component.damage_modifier)
                for component in attack_expectation.damage_components
            ),
            "advantage_damage_components": tuple(
                (component.damage_type, component.damage_dice, component.damage_modifier)
                for component in attack_expectation.advantage_damage_components
            ),
        }

    if "pack_tactics" in expectation.special_mechanics:
        assert "pack_tactics" in definition.trait_ids

    if "advantage_poison" in expectation.special_mechanics:
        longbow = definition.attacks["longbow"]
        assert serialize_damage_components(longbow.advantage_damage_components) == (("poison", ((3, 4),), 0),)

    if "split_damage" in expectation.special_mechanics:
        ritual_sickle = definition.attacks["ritual_sickle"]
        assert serialize_damage_components(ritual_sickle.damage_components) == (
            ("slashing", ((1, 4),), 1),
            ("necrotic", (), 1),
        )
