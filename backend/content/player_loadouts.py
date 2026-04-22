from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from backend.content.class_progressions import get_class_progression
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import (
    AbilityModifiers,
    ConditionState,
    DiceSpec,
    Footprint,
    GridPosition,
    ResourceState,
    UnitState,
    WeaponProfile,
    WeaponRange,
)


@dataclass(frozen=True)
class PlayerLoadoutDefinition:
    """Static loadout entry for a specific class/level sample build."""

    loadout_id: str
    display_name: str
    class_id: str
    level: int
    template_name: str
    behavior_profile: str
    max_hp: int
    ac: int | None
    speed: int
    initiative_mod: int
    passive_perception: int
    ability_mods: AbilityModifiers
    size_category: str
    footprint: Footprint
    attacks: dict[str, WeaponProfile]
    extra_feature_ids: tuple[str, ...] = ()
    extra_resource_pools: dict[str, int] | None = None
    role_tags: tuple[str, ...] = ()
    medicine_modifier: int = -1
    default_melee_weapon_id: str | None = None
    default_ranged_weapon_id: str | None = None
    combat_skill_modifiers: dict[str, int] | None = None
    ac_formula_id: str | None = None


@dataclass(frozen=True)
class PlayerPresetUnit:
    unit_id: str
    loadout_id: str


@dataclass(frozen=True)
class PlayerPresetDefinition:
    preset_id: str
    display_name: str
    description: str
    units: tuple[PlayerPresetUnit, ...]


fighter_ability_mods = AbilityModifiers(str=3, dex=1, con=2, int=0, wis=-1, cha=1)
rogue_ability_mods = AbilityModifiers(str=0, dex=3, con=2, int=1, wis=1, cha=-1)
barbarian_ability_mods = AbilityModifiers(str=3, dex=1, con=3, int=-1, wis=0, cha=0)
monk_ability_mods = AbilityModifiers(str=0, dex=3, con=2, int=0, wis=2, cha=-1)
medium_footprint = Footprint(width=1, height=1)
TRIO_PLAYER_IDS = ("F1", "F2", "F3")

AC_FORMULAS = {
    # Keeping AC formulas in one lookup keeps fixed-AC builds working while
    # letting later class features opt into formula-driven defenses cleanly.
    "barbarian_unarmored_defense": lambda ability_mods: 10 + ability_mods.dex + ability_mods.con,
    "monk_unarmored_defense": lambda ability_mods: 10 + ability_mods.dex + ability_mods.wis,
}

player_weapons: dict[str, WeaponProfile] = {
    "greatsword": WeaponProfile(
        id="greatsword",
        display_name="Greatsword",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="str",
        damage_dice=[DiceSpec(count=2, sides=6)],
        damage_modifier=3,
        damage_type="slashing",
        mastery="graze",
        kind="melee",
        two_handed=True,
    ),
    "flail": WeaponProfile(
        id="flail",
        display_name="Flail",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="str",
        damage_dice=[DiceSpec(count=1, sides=8)],
        damage_modifier=3,
        damage_type="bludgeoning",
        mastery="sap",
        kind="melee",
    ),
    "javelin": WeaponProfile(
        id="javelin",
        display_name="Javelin",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="str",
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=3,
        damage_type="piercing",
        mastery="slow",
        kind="ranged",
        range=WeaponRange(normal=30, long=120),
        resource_pool_id="javelins",
    ),
    "greataxe": WeaponProfile(
        id="greataxe",
        display_name="Greataxe",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="str",
        damage_dice=[DiceSpec(count=1, sides=12)],
        damage_modifier=3,
        damage_type="slashing",
        mastery="cleave",
        kind="melee",
        two_handed=True,
    ),
    "handaxe": WeaponProfile(
        id="handaxe",
        display_name="Handaxe",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="str",
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=3,
        damage_type="slashing",
        mastery="vex",
        kind="ranged",
        range=WeaponRange(normal=20, long=60),
        resource_pool_id="handaxes",
    ),
    "shortsword": WeaponProfile(
        id="shortsword",
        display_name="Shortsword",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="dex",
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=3,
        damage_type="piercing",
        kind="melee",
        finesse=True,
    ),
    "rapier": WeaponProfile(
        id="rapier",
        display_name="Rapier",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="dex",
        damage_dice=[DiceSpec(count=1, sides=8)],
        damage_modifier=3,
        damage_type="piercing",
        kind="melee",
        finesse=True,
    ),
    "shortbow": WeaponProfile(
        id="shortbow",
        display_name="Shortbow",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="dex",
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=3,
        damage_type="piercing",
        kind="ranged",
        range=WeaponRange(normal=80, long=320),
    ),
    "unarmed_strike": WeaponProfile(
        id="unarmed_strike",
        display_name="Unarmed Strike",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="dex",
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=3,
        damage_type="bludgeoning",
        kind="melee",
    ),
}

PLAYER_LOADOUTS: dict[str, PlayerLoadoutDefinition] = {
    "fighter_sample_build": PlayerLoadoutDefinition(
        loadout_id="fighter_sample_build",
        display_name="Level 1 Fighter Sample Build",
        class_id="fighter",
        level=1,
        template_name="Level 1 Fighter Sample Build",
        behavior_profile="martial_striker",
        max_hp=13,
        ac=16,
        speed=30,
        initiative_mod=1,
        passive_perception=11,
        ability_mods=fighter_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "greatsword": player_weapons["greatsword"],
            "flail": player_weapons["flail"],
            "javelin": player_weapons["javelin"],
        },
        extra_feature_ids=(
            "great_weapon_fighting",
            "savage_attacker",
            "weapon_mastery_graze",
            "weapon_mastery_sap",
            "weapon_mastery_slow",
        ),
        extra_resource_pools={"javelins": 8},
        default_melee_weapon_id="greatsword",
        default_ranged_weapon_id="javelin",
    ),
    "fighter_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="fighter_level2_sample_build",
        display_name="Level 2 Fighter Sample Build",
        class_id="fighter",
        level=2,
        template_name="Level 2 Fighter Sample Build",
        behavior_profile="martial_striker",
        max_hp=21,
        ac=16,
        speed=30,
        initiative_mod=1,
        passive_perception=11,
        ability_mods=fighter_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "greatsword": player_weapons["greatsword"],
            "flail": player_weapons["flail"],
            "javelin": player_weapons["javelin"],
        },
        extra_feature_ids=(
            "great_weapon_fighting",
            "savage_attacker",
            "weapon_mastery_graze",
            "weapon_mastery_sap",
            "weapon_mastery_slow",
        ),
        extra_resource_pools={"javelins": 8},
        default_melee_weapon_id="greatsword",
        default_ranged_weapon_id="javelin",
    ),
    "rogue_ranged_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_ranged_sample_build",
        display_name="Ranged Rogue Sample Build",
        class_id="rogue",
        level=1,
        template_name="Level 1 Ranged Rogue Sample Build",
        behavior_profile="martial_skirmisher",
        max_hp=10,
        ac=14,
        speed=30,
        initiative_mod=3,
        passive_perception=11,
        ability_mods=rogue_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortbow": player_weapons["shortbow"],
            "shortsword": player_weapons["shortsword"],
        },
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
        combat_skill_modifiers={"stealth": 5},
    ),
    "rogue_ranged_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_ranged_level2_sample_build",
        display_name="Level 2 Ranged Rogue Sample Build",
        class_id="rogue",
        level=2,
        template_name="Level 2 Ranged Rogue Sample Build",
        behavior_profile="martial_skirmisher",
        max_hp=18,
        ac=14,
        speed=30,
        initiative_mod=3,
        passive_perception=11,
        ability_mods=rogue_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortbow": player_weapons["shortbow"],
            "shortsword": player_weapons["shortsword"],
        },
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
        combat_skill_modifiers={"stealth": 5},
    ),
    "rogue_melee_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_melee_sample_build",
        display_name="Melee Rogue Sample Build",
        class_id="rogue",
        level=1,
        template_name="Level 1 Melee Rogue Sample Build",
        behavior_profile="martial_opportunist",
        max_hp=10,
        ac=14,
        speed=30,
        initiative_mod=3,
        passive_perception=11,
        ability_mods=rogue_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "rapier": player_weapons["rapier"],
            "shortbow": player_weapons["shortbow"],
        },
        default_melee_weapon_id="rapier",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
        combat_skill_modifiers={"stealth": 5},
    ),
    "rogue_melee_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_melee_level2_sample_build",
        display_name="Level 2 Melee Rogue Sample Build",
        class_id="rogue",
        level=2,
        template_name="Level 2 Melee Rogue Sample Build",
        behavior_profile="martial_opportunist",
        max_hp=18,
        ac=14,
        speed=30,
        initiative_mod=3,
        passive_perception=11,
        ability_mods=rogue_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "rapier": player_weapons["rapier"],
            "shortbow": player_weapons["shortbow"],
        },
        default_melee_weapon_id="rapier",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
        combat_skill_modifiers={"stealth": 5},
    ),
    "barbarian_sample_build": PlayerLoadoutDefinition(
        loadout_id="barbarian_sample_build",
        display_name="Level 1 Barbarian Sample Build",
        class_id="barbarian",
        level=1,
        template_name="Level 1 Barbarian Sample Build",
        behavior_profile="martial_berserker",
        max_hp=15,
        ac=None,
        ac_formula_id="barbarian_unarmored_defense",
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=barbarian_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "greataxe": player_weapons["greataxe"],
            "handaxe": player_weapons["handaxe"],
        },
        extra_feature_ids=("weapon_mastery_cleave", "weapon_mastery_vex"),
        default_melee_weapon_id="greataxe",
        default_ranged_weapon_id="handaxe",
        medicine_modifier=0,
    ),
    "barbarian_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="barbarian_level2_sample_build",
        display_name="Level 2 Barbarian Sample Build",
        class_id="barbarian",
        level=2,
        template_name="Level 2 Barbarian Sample Build",
        behavior_profile="martial_berserker",
        max_hp=25,
        ac=None,
        ac_formula_id="barbarian_unarmored_defense",
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=barbarian_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "greataxe": player_weapons["greataxe"],
            "handaxe": player_weapons["handaxe"],
        },
        extra_feature_ids=("weapon_mastery_cleave", "weapon_mastery_vex"),
        default_melee_weapon_id="greataxe",
        default_ranged_weapon_id="handaxe",
        medicine_modifier=0,
    ),
    "monk_sample_build": PlayerLoadoutDefinition(
        loadout_id="monk_sample_build",
        display_name="Level 1 Monk Sample Build",
        class_id="monk",
        level=1,
        template_name="Level 1 Monk Sample Build",
        behavior_profile="martial_artist",
        max_hp=10,
        ac=None,
        ac_formula_id="monk_unarmored_defense",
        speed=30,
        initiative_mod=3,
        passive_perception=12,
        ability_mods=monk_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortsword": player_weapons["shortsword"],
            "unarmed_strike": player_weapons["unarmed_strike"],
        },
        default_melee_weapon_id="shortsword",
        medicine_modifier=2,
    ),
    "monk_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="monk_level2_sample_build",
        display_name="Level 2 Monk Sample Build",
        class_id="monk",
        level=2,
        template_name="Level 2 Monk Sample Build",
        behavior_profile="martial_artist",
        max_hp=18,
        ac=None,
        ac_formula_id="monk_unarmored_defense",
        speed=40,
        initiative_mod=3,
        passive_perception=12,
        ability_mods=monk_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortsword": player_weapons["shortsword"],
            "unarmed_strike": player_weapons["unarmed_strike"],
        },
        default_melee_weapon_id="shortsword",
        medicine_modifier=2,
    ),
}

PLAYER_LOADOUTS.update(
    {
        "fighter_level2_benchmark_tank": PlayerLoadoutDefinition(
            loadout_id="fighter_level2_benchmark_tank",
            display_name="Level 2 Fighter Benchmark Tank",
            class_id="fighter",
            level=2,
            template_name="Level 2 Fighter Benchmark Tank",
            behavior_profile="martial_striker",
            max_hp=100,
            ac=16,
            speed=30,
            initiative_mod=1,
            passive_perception=11,
            ability_mods=fighter_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "greatsword": player_weapons["greatsword"],
                "flail": player_weapons["flail"],
                "javelin": player_weapons["javelin"],
            },
            extra_feature_ids=(
                "great_weapon_fighting",
                "savage_attacker",
                "weapon_mastery_graze",
                "weapon_mastery_sap",
                "weapon_mastery_slow",
            ),
            extra_resource_pools={"javelins": 8},
            default_melee_weapon_id="greatsword",
            default_ranged_weapon_id="javelin",
        ),
        "rogue_ranged_level2_benchmark_archer": PlayerLoadoutDefinition(
            loadout_id="rogue_ranged_level2_benchmark_archer",
            display_name="Level 2 Ranged Rogue Benchmark Archer",
            class_id="rogue",
            level=2,
            template_name="Level 2 Ranged Rogue Benchmark Archer",
            behavior_profile="martial_skirmisher",
            max_hp=50,
            ac=14,
            speed=30,
            initiative_mod=3,
            passive_perception=11,
            ability_mods=rogue_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "shortbow": player_weapons["shortbow"],
                "shortsword": player_weapons["shortsword"],
            },
            default_melee_weapon_id="shortsword",
            default_ranged_weapon_id="shortbow",
            medicine_modifier=1,
            combat_skill_modifiers={"stealth": 5},
        ),
    }
)

PLAYER_PRESET_DEFINITIONS: dict[str, PlayerPresetDefinition] = {
    "fighter_sample_trio": PlayerPresetDefinition(
        preset_id="fighter_sample_trio",
        display_name="Level 1 Fighter Trio",
        description="Three level 1 fighters using the original proof-of-concept build.",
        units=tuple(PlayerPresetUnit(unit_id=fighter_id, loadout_id="fighter_sample_build") for fighter_id in TRIO_PLAYER_IDS),
    ),
    "fighter_level2_sample_trio": PlayerPresetDefinition(
        preset_id="fighter_level2_sample_trio",
        display_name="Level 2 Fighter Trio",
        description="Three level 2 great-weapon fighters with Action Surge.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="fighter_level2_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "rogue_ranged_trio": PlayerPresetDefinition(
        preset_id="rogue_ranged_trio",
        display_name="Ranged Rogue Trio",
        description="Three level 1 ranged rogues with shortbows and shortsword fallback.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_ranged_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "rogue_melee_trio": PlayerPresetDefinition(
        preset_id="rogue_melee_trio",
        display_name="Melee Rogue Trio",
        description="Three level 1 melee rogues with rapiers and shortbow fallback.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_melee_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "rogue_level2_ranged_trio": PlayerPresetDefinition(
        preset_id="rogue_level2_ranged_trio",
        display_name="Level 2 Ranged Rogue Trio",
        description="Three level 2 ranged rogues with shortbows, Cunning Action, and shortsword fallback.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_ranged_level2_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "rogue_level2_melee_trio": PlayerPresetDefinition(
        preset_id="rogue_level2_melee_trio",
        display_name="Level 2 Melee Rogue Trio",
        description="Three level 2 melee rogues with rapiers, Cunning Action, and shortbow fallback.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_melee_level2_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "barbarian_sample_trio": PlayerPresetDefinition(
        preset_id="barbarian_sample_trio",
        display_name="Level 1 Barbarian Trio",
        description="Three level 1 barbarians with greataxes and thrown handaxe fallback.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="barbarian_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "barbarian_level2_sample_trio": PlayerPresetDefinition(
        preset_id="barbarian_level2_sample_trio",
        display_name="Level 2 Barbarian Trio",
        description="Three level 2 barbarians with greataxes, handaxes, Reckless Attack, and Danger Sense.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="barbarian_level2_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "monk_sample_trio": PlayerPresetDefinition(
        preset_id="monk_sample_trio",
        display_name="Level 1 Monk Trio",
        description="Three level 1 monks with shortswords, Martial Arts, and Unarmored Defense.",
        units=tuple(PlayerPresetUnit(unit_id=fighter_id, loadout_id="monk_sample_build") for fighter_id in TRIO_PLAYER_IDS),
    ),
    "monk_level2_sample_trio": PlayerPresetDefinition(
        preset_id="monk_level2_sample_trio",
        display_name="Level 2 Monk Trio",
        description="Three level 2 monks with Focus, Unarmored Movement, and Uncanny Metabolism.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="monk_level2_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "martial_mixed_party": PlayerPresetDefinition(
        preset_id="martial_mixed_party",
        display_name="Mixed Martial Party",
        description="One level 2 fighter, one level 2 barbarian, one level 2 ranged rogue, and one level 2 melee rogue.",
        units=(
            PlayerPresetUnit(unit_id="F1", loadout_id="fighter_level2_sample_build"),
            PlayerPresetUnit(unit_id="F2", loadout_id="barbarian_level2_sample_build"),
            PlayerPresetUnit(unit_id="F3", loadout_id="rogue_ranged_level2_sample_build"),
            PlayerPresetUnit(unit_id="F4", loadout_id="rogue_melee_level2_sample_build"),
        ),
    ),
}

PLAYER_PRESET_DEFINITIONS.update(
    {
        "monster_benchmark_duo": PlayerPresetDefinition(
            preset_id="monster_benchmark_duo",
            display_name="Monster Benchmark Duo",
            description="Test-only duo with a high-HP fighter tank and ranged rogue archer for monster smoke runs.",
            units=(
                PlayerPresetUnit(unit_id="F1", loadout_id="fighter_level2_benchmark_tank"),
                PlayerPresetUnit(unit_id="F3", loadout_id="rogue_ranged_level2_benchmark_archer"),
            ),
        )
    }
)

DEFAULT_PLAYER_PRESET_ID = "martial_mixed_party"
ACTIVE_PLAYER_PRESET_IDS = (
    "fighter_sample_trio",
    "fighter_level2_sample_trio",
    "rogue_ranged_trio",
    "rogue_melee_trio",
    "rogue_level2_ranged_trio",
    "rogue_level2_melee_trio",
    "barbarian_sample_trio",
    "barbarian_level2_sample_trio",
    "monk_sample_trio",
    "monk_level2_sample_trio",
    "martial_mixed_party",
)


def clone_attacks(source: dict[str, WeaponProfile]) -> dict[str, WeaponProfile]:
    return deepcopy(source)


def get_player_loadout(loadout_id: str) -> PlayerLoadoutDefinition:
    try:
        return PLAYER_LOADOUTS[loadout_id]
    except KeyError as error:
        raise ValueError(f"Unknown player loadout '{loadout_id}'.") from error


def get_player_preset(preset_id: str) -> PlayerPresetDefinition:
    try:
        return PLAYER_PRESET_DEFINITIONS[preset_id]
    except KeyError as error:
        raise ValueError(f"Unknown player preset '{preset_id}'.") from error


def get_active_player_presets() -> list[PlayerPresetDefinition]:
    return [PLAYER_PRESET_DEFINITIONS[preset_id] for preset_id in ACTIVE_PLAYER_PRESET_IDS]


def get_player_preset_unit_ids(preset_id: str | None = None) -> list[str]:
    preset = get_player_preset(preset_id or DEFAULT_PLAYER_PRESET_ID)
    return [unit.unit_id for unit in preset.units]


def get_player_preset_footprints(preset_id: str | None = None) -> dict[str, Footprint]:
    preset = get_player_preset(preset_id or DEFAULT_PLAYER_PRESET_ID)
    return {
        unit.unit_id: get_player_loadout(unit.loadout_id).footprint.model_copy(deep=True)
        for unit in preset.units
    }


def get_default_player_positions(preset_id: str | None = None) -> dict[str, GridPosition]:
    preset = get_player_preset(preset_id or DEFAULT_PLAYER_PRESET_ID)
    return {
        unit.unit_id: DEFAULT_POSITIONS[unit.unit_id].model_copy(deep=True)
        for unit in preset.units
    }


def get_feature_ids_for_loadout(loadout: PlayerLoadoutDefinition) -> list[str]:
    progression = get_class_progression(loadout.class_id, loadout.level)
    return [*progression.feature_ids, *loadout.extra_feature_ids]


def get_resource_pools_for_loadout(loadout: PlayerLoadoutDefinition) -> dict[str, int]:
    progression = get_class_progression(loadout.class_id, loadout.level)
    pools = dict(progression.resource_pools)
    for resource_id, amount in (loadout.extra_resource_pools or {}).items():
        pools[resource_id] = amount
    return pools


def resolve_loadout_ac(loadout: PlayerLoadoutDefinition) -> int:
    if loadout.ac is not None:
        return loadout.ac
    if loadout.ac_formula_id and loadout.ac_formula_id in AC_FORMULAS:
        return AC_FORMULAS[loadout.ac_formula_id](loadout.ability_mods)
    raise ValueError(f"{loadout.loadout_id} does not define a usable AC source.")


def build_legacy_resource_state(resource_pools: dict[str, int]) -> ResourceState:
    return ResourceState(
        second_wind_uses=resource_pools.get("second_wind", 0),
        javelins=resource_pools.get("javelins", 0),
        rage_uses=resource_pools.get("rage", 0),
        handaxes=resource_pools.get("handaxes", 0),
        action_surge_uses=resource_pools.get("action_surge", 0),
        focus_points=resource_pools.get("focus_points", 0),
        uncanny_metabolism_uses=resource_pools.get("uncanny_metabolism", 0),
    )


def create_player_unit(unit_id: str, loadout_id: str) -> UnitState:
    loadout = get_player_loadout(loadout_id)
    resource_pools = get_resource_pools_for_loadout(loadout)

    return UnitState(
        id=unit_id,
        faction="fighters",
        combat_role=loadout.class_id,
        template_name=loadout.template_name,
        role_tags=list(loadout.role_tags),
        current_hp=loadout.max_hp,
        max_hp=loadout.max_hp,
        temporary_hit_points=0,
        ac=resolve_loadout_ac(loadout),
        speed=loadout.speed,
        effective_speed=loadout.speed,
        initiative_mod=loadout.initiative_mod,
        initiative_score=0,
        ability_mods=deepcopy(loadout.ability_mods),
        passive_perception=loadout.passive_perception,
        size_category=loadout.size_category,
        footprint=deepcopy(loadout.footprint),
        conditions=ConditionState(unconscious=False, prone=False, dead=False),
        death_save_successes=0,
        death_save_failures=0,
        stable=False,
        resources=build_legacy_resource_state(resource_pools),
        temporary_effects=[],
        reaction_available=True,
        attacks=clone_attacks(loadout.attacks),
        medicine_modifier=loadout.medicine_modifier,
        class_id=loadout.class_id,
        level=loadout.level,
        loadout_id=loadout.loadout_id,
        feature_ids=get_feature_ids_for_loadout(loadout),
        resource_pools=resource_pools,
        behavior_profile=loadout.behavior_profile,
        combat_skill_modifiers=deepcopy(loadout.combat_skill_modifiers or {}),
    )


def create_player_party_units(preset_id: str | None = None) -> dict[str, UnitState]:
    preset = get_player_preset(preset_id or DEFAULT_PLAYER_PRESET_ID)
    return {unit.unit_id: create_player_unit(unit.unit_id, unit.loadout_id) for unit in preset.units}


def get_player_loadout_for_unit(unit: UnitState) -> PlayerLoadoutDefinition:
    if not unit.loadout_id:
        raise ValueError(f"{unit.id} does not have a player loadout id.")
    return get_player_loadout(unit.loadout_id)


def get_player_primary_melee_weapon_id(unit: UnitState) -> str:
    loadout = get_player_loadout_for_unit(unit)
    if loadout.default_melee_weapon_id and loadout.default_melee_weapon_id in unit.attacks:
        return loadout.default_melee_weapon_id

    for weapon_id, weapon in unit.attacks.items():
        if weapon and weapon.kind == "melee":
            return weapon_id

    raise ValueError(f"{unit.id} has no melee weapon profile.")


def get_player_primary_ranged_weapon_id(unit: UnitState) -> str | None:
    loadout = get_player_loadout_for_unit(unit)
    if loadout.default_ranged_weapon_id and loadout.default_ranged_weapon_id in unit.attacks:
        return loadout.default_ranged_weapon_id

    for weapon_id, weapon in unit.attacks.items():
        if weapon and weapon.kind == "ranged":
            return weapon_id

    return None
