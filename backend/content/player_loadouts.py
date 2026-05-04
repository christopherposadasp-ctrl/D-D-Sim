from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from backend.content.class_progressions import get_class_progression, get_proficiency_bonus, get_progression_scalar
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import (
    AbilityModifiers,
    ConditionState,
    DiceSpec,
    Footprint,
    GridPosition,
    ResourceState,
    RoleTag,
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
    role_tags: tuple[RoleTag, ...] = ()
    medicine_modifier: int = -1
    default_melee_weapon_id: str | None = None
    default_ranged_weapon_id: str | None = None
    combat_skill_modifiers: dict[str, int] | None = None
    ac_formula_id: str | None = None
    combat_cantrip_ids: tuple[str, ...] = ()
    prepared_combat_spell_ids: tuple[str, ...] = ()


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
fighter_level4_ability_mods = AbilityModifiers(str=4, dex=1, con=2, int=0, wis=-1, cha=1)
rogue_ability_mods = AbilityModifiers(str=0, dex=3, con=2, int=1, wis=1, cha=-1)
rogue_level4_ability_mods = AbilityModifiers(str=0, dex=4, con=2, int=1, wis=1, cha=-1)
barbarian_ability_mods = AbilityModifiers(str=3, dex=1, con=3, int=-1, wis=0, cha=0)
monk_ability_mods = AbilityModifiers(str=0, dex=3, con=2, int=0, wis=2, cha=-1)
paladin_ability_mods = AbilityModifiers(str=3, dex=0, con=3, int=-1, wis=0, cha=2)
paladin_level4_ability_mods = AbilityModifiers(str=4, dex=0, con=3, int=-1, wis=0, cha=2)
wizard_ability_mods = AbilityModifiers(str=-1, dex=2, con=2, int=3, wis=1, cha=0)
wizard_level4_ability_mods = AbilityModifiers(str=-1, dex=2, con=2, int=4, wis=1, cha=0)
medium_footprint = Footprint(width=1, height=1)
TRIO_PLAYER_IDS = ("F1", "F2", "F3")
COMBAT_SKILL_ABILITY_IDS = {
    "stealth": "dex",
}
EXPERTISE_SKILL_BY_FEATURE_ID = {
    "expertise_stealth": "stealth",
}

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
    "longsword": WeaponProfile(
        id="longsword",
        display_name="Longsword",
        attack_bonus=5,
        ability_modifier=3,
        attack_ability="str",
        damage_dice=[DiceSpec(count=1, sides=8)],
        damage_modifier=3,
        damage_type="slashing",
        mastery="sap",
        kind="melee",
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
    "dagger": WeaponProfile(
        id="dagger",
        display_name="Dagger",
        attack_bonus=4,
        ability_modifier=2,
        attack_ability="dex",
        damage_dice=[DiceSpec(count=1, sides=4)],
        damage_modifier=2,
        damage_type="piercing",
        kind="melee",
        finesse=True,
    ),
}

rogue_vex_shortbow = player_weapons["shortbow"].model_copy(update={"mastery": "vex"}, deep=True)
rogue_vex_rapier = player_weapons["rapier"].model_copy(update={"mastery": "vex"}, deep=True)

fighter_level4_weapons: dict[str, WeaponProfile] = {
    "greatsword": player_weapons["greatsword"].model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
    "flail": player_weapons["flail"].model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
    "javelin": player_weapons["javelin"].model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
}

fighter_level5_weapons: dict[str, WeaponProfile] = {
    "greatsword": fighter_level4_weapons["greatsword"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
    ),
    "flail": fighter_level4_weapons["flail"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
    ),
    "javelin": fighter_level4_weapons["javelin"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
    ),
}

paladin_level4_weapons: dict[str, WeaponProfile] = {
    "longsword": player_weapons["longsword"].model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
    "javelin": player_weapons["javelin"].model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
}

paladin_level5_weapons: dict[str, WeaponProfile] = {
    "longsword": paladin_level4_weapons["longsword"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
    ),
    "javelin": paladin_level4_weapons["javelin"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
    ),
}

rogue_level4_weapons: dict[str, WeaponProfile] = {
    "shortbow": rogue_vex_shortbow.model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
    "shortsword": player_weapons["shortsword"].model_copy(
        update={"attack_bonus": 6, "ability_modifier": 4, "damage_modifier": 4},
        deep=True,
    ),
}

rogue_level5_weapons: dict[str, WeaponProfile] = {
    "shortbow": rogue_level4_weapons["shortbow"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
    ),
    "shortsword": rogue_level4_weapons["shortsword"].model_copy(
        update={"attack_bonus": 7},
        deep=True,
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
    "fighter_level3_sample_build": PlayerLoadoutDefinition(
        loadout_id="fighter_level3_sample_build",
        display_name="Level 3 Fighter Battle Master Sample Build",
        class_id="fighter",
        level=3,
        template_name="Level 3 Fighter Battle Master Sample Build",
        behavior_profile="martial_striker",
        max_hp=29,
        ac=18,
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
    "fighter_level4_sample_build": PlayerLoadoutDefinition(
        loadout_id="fighter_level4_sample_build",
        display_name="Level 4 Fighter Battle Master Sample Build",
        class_id="fighter",
        level=4,
        template_name="Level 4 Fighter Battle Master Sample Build",
        behavior_profile="martial_striker",
        max_hp=37,
        ac=18,
        speed=30,
        initiative_mod=1,
        passive_perception=11,
        ability_mods=fighter_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "greatsword": fighter_level4_weapons["greatsword"],
            "flail": fighter_level4_weapons["flail"],
            "javelin": fighter_level4_weapons["javelin"],
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
    "fighter_level5_sample_build": PlayerLoadoutDefinition(
        loadout_id="fighter_level5_sample_build",
        display_name="Level 5 Fighter Battle Master Sample Build",
        class_id="fighter",
        level=5,
        template_name="Level 5 Fighter Battle Master Sample Build",
        behavior_profile="martial_striker",
        max_hp=45,
        ac=18,
        speed=30,
        initiative_mod=1,
        passive_perception=11,
        ability_mods=fighter_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "greatsword": fighter_level5_weapons["greatsword"],
            "flail": fighter_level5_weapons["flail"],
            "javelin": fighter_level5_weapons["javelin"],
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
            "shortbow": rogue_vex_shortbow,
            "shortsword": player_weapons["shortsword"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
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
            "shortbow": rogue_vex_shortbow,
            "shortsword": player_weapons["shortsword"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
    ),
    "rogue_ranged_level3_assassin_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_ranged_level3_assassin_sample_build",
        display_name="Level 3 Ranged Assassin Rogue Sample Build",
        class_id="rogue",
        level=3,
        template_name="Level 3 Ranged Assassin Rogue Sample Build",
        behavior_profile="martial_skirmisher",
        max_hp=26,
        ac=15,
        speed=30,
        initiative_mod=3,
        passive_perception=11,
        ability_mods=rogue_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortbow": rogue_vex_shortbow,
            "shortsword": player_weapons["shortsword"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
    ),
    "rogue_ranged_level4_assassin_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_ranged_level4_assassin_sample_build",
        display_name="Level 4 Ranged Assassin Rogue Sample Build",
        class_id="rogue",
        level=4,
        template_name="Level 4 Ranged Assassin Rogue Sample Build",
        behavior_profile="martial_skirmisher",
        max_hp=34,
        ac=16,
        speed=30,
        initiative_mod=4,
        passive_perception=11,
        ability_mods=rogue_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortbow": rogue_level4_weapons["shortbow"],
            "shortsword": rogue_level4_weapons["shortsword"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
    ),
    "rogue_ranged_level5_assassin_sample_build": PlayerLoadoutDefinition(
        loadout_id="rogue_ranged_level5_assassin_sample_build",
        display_name="Level 5 Ranged Assassin Rogue Sample Build",
        class_id="rogue",
        level=5,
        template_name="Level 5 Ranged Assassin Rogue Sample Build",
        behavior_profile="martial_skirmisher",
        max_hp=42,
        ac=16,
        speed=30,
        initiative_mod=4,
        passive_perception=11,
        ability_mods=rogue_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "shortbow": rogue_level5_weapons["shortbow"],
            "shortsword": rogue_level5_weapons["shortsword"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="shortsword",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
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
            "rapier": rogue_vex_rapier,
            "shortbow": player_weapons["shortbow"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="rapier",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
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
            "rapier": rogue_vex_rapier,
            "shortbow": player_weapons["shortbow"],
        },
        extra_feature_ids=("weapon_mastery_vex",),
        default_melee_weapon_id="rapier",
        default_ranged_weapon_id="shortbow",
        medicine_modifier=1,
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
    "paladin_level1_sample_build": PlayerLoadoutDefinition(
        loadout_id="paladin_level1_sample_build",
        display_name="Level 1 Paladin Sample Build",
        class_id="paladin",
        level=1,
        template_name="Level 1 Paladin Sample Build",
        behavior_profile="divine_guardian",
        max_hp=13,
        ac=20,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        ability_mods=paladin_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "longsword": player_weapons["longsword"],
            "javelin": player_weapons["javelin"],
        },
        extra_feature_ids=("weapon_mastery_sap", "weapon_mastery_slow"),
        extra_resource_pools={"javelins": 5},
        role_tags=("healer",),
        medicine_modifier=2,
        default_melee_weapon_id="longsword",
        default_ranged_weapon_id="javelin",
        prepared_combat_spell_ids=("bless", "cure_wounds"),
    ),
    "paladin_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="paladin_level2_sample_build",
        display_name="Level 2 Paladin Sample Build",
        class_id="paladin",
        level=2,
        template_name="Level 2 Paladin Sample Build",
        behavior_profile="divine_guardian",
        max_hp=22,
        ac=21,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        ability_mods=paladin_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "longsword": player_weapons["longsword"],
            "javelin": player_weapons["javelin"],
        },
        extra_feature_ids=("weapon_mastery_sap", "weapon_mastery_slow"),
        extra_resource_pools={"javelins": 5},
        role_tags=("healer",),
        medicine_modifier=2,
        default_melee_weapon_id="longsword",
        default_ranged_weapon_id="javelin",
        prepared_combat_spell_ids=("bless", "cure_wounds"),
    ),
    "paladin_level3_sample_build": PlayerLoadoutDefinition(
        loadout_id="paladin_level3_sample_build",
        display_name="Level 3 Paladin Sample Build",
        class_id="paladin",
        level=3,
        template_name="Level 3 Paladin Sample Build",
        behavior_profile="divine_guardian",
        max_hp=31,
        ac=21,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        ability_mods=paladin_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "longsword": player_weapons["longsword"],
            "javelin": player_weapons["javelin"],
        },
        extra_feature_ids=("weapon_mastery_sap", "weapon_mastery_slow"),
        extra_resource_pools={"javelins": 5},
        role_tags=("healer",),
        medicine_modifier=2,
        default_melee_weapon_id="longsword",
        default_ranged_weapon_id="javelin",
        prepared_combat_spell_ids=("bless", "cure_wounds"),
    ),
    "paladin_level4_sample_build": PlayerLoadoutDefinition(
        loadout_id="paladin_level4_sample_build",
        display_name="Level 4 Paladin Sample Build",
        class_id="paladin",
        level=4,
        template_name="Level 4 Paladin Sample Build",
        behavior_profile="divine_guardian",
        max_hp=40,
        ac=21,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        ability_mods=paladin_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "longsword": paladin_level4_weapons["longsword"],
            "javelin": paladin_level4_weapons["javelin"],
        },
        extra_feature_ids=("weapon_mastery_sap", "weapon_mastery_slow"),
        extra_resource_pools={"javelins": 5},
        role_tags=("healer",),
        medicine_modifier=2,
        default_melee_weapon_id="longsword",
        default_ranged_weapon_id="javelin",
        prepared_combat_spell_ids=("bless", "cure_wounds"),
    ),
    "paladin_level5_sample_build": PlayerLoadoutDefinition(
        loadout_id="paladin_level5_sample_build",
        display_name="Level 5 Paladin Sample Build",
        class_id="paladin",
        level=5,
        template_name="Level 5 Paladin Sample Build",
        behavior_profile="divine_guardian",
        max_hp=49,
        ac=21,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        ability_mods=paladin_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "longsword": paladin_level5_weapons["longsword"],
            "javelin": paladin_level5_weapons["javelin"],
        },
        extra_feature_ids=("weapon_mastery_sap", "weapon_mastery_slow"),
        extra_resource_pools={"javelins": 5},
        role_tags=("healer",),
        medicine_modifier=2,
        default_melee_weapon_id="longsword",
        default_ranged_weapon_id="javelin",
        prepared_combat_spell_ids=("bless", "cure_wounds", "aid"),
    ),
    "wizard_sample_build": PlayerLoadoutDefinition(
        loadout_id="wizard_sample_build",
        display_name="Level 1 Wizard Sample Build",
        class_id="wizard",
        level=1,
        template_name="Level 1 Wizard Sample Build",
        behavior_profile="arcane_artillery",
        max_hp=8,
        ac=12,
        speed=30,
        initiative_mod=2,
        passive_perception=11,
        ability_mods=wizard_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"dagger": player_weapons["dagger"]},
        role_tags=("caster",),
        medicine_modifier=1,
        default_melee_weapon_id="dagger",
        combat_cantrip_ids=("fire_bolt", "shocking_grasp"),
        prepared_combat_spell_ids=("magic_missile", "shield", "burning_hands", "mage_armor"),
    ),
    "wizard_level2_sample_build": PlayerLoadoutDefinition(
        loadout_id="wizard_level2_sample_build",
        display_name="Level 2 Wizard Sample Build",
        class_id="wizard",
        level=2,
        template_name="Level 2 Wizard Sample Build",
        behavior_profile="arcane_artillery",
        max_hp=14,
        ac=12,
        speed=30,
        initiative_mod=2,
        passive_perception=11,
        ability_mods=wizard_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"dagger": player_weapons["dagger"]},
        role_tags=("caster",),
        medicine_modifier=1,
        default_melee_weapon_id="dagger",
        combat_cantrip_ids=("fire_bolt", "shocking_grasp"),
        prepared_combat_spell_ids=("magic_missile", "shield", "burning_hands", "mage_armor"),
    ),
    "wizard_level3_evoker_sample_build": PlayerLoadoutDefinition(
        loadout_id="wizard_level3_evoker_sample_build",
        display_name="Level 3 Evoker Wizard Sample Build",
        class_id="wizard",
        level=3,
        template_name="Level 3 Evoker Wizard Sample Build",
        behavior_profile="arcane_artillery",
        max_hp=20,
        ac=12,
        speed=30,
        initiative_mod=2,
        passive_perception=11,
        ability_mods=wizard_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"dagger": player_weapons["dagger"]},
        role_tags=("caster",),
        medicine_modifier=1,
        default_melee_weapon_id="dagger",
        combat_cantrip_ids=("fire_bolt", "shocking_grasp"),
        prepared_combat_spell_ids=(
            "magic_missile",
            "shield",
            "burning_hands",
            "mage_armor",
            "scorching_ray",
            "shatter",
        ),
    ),
    "wizard_level4_evoker_sample_build": PlayerLoadoutDefinition(
        loadout_id="wizard_level4_evoker_sample_build",
        display_name="Level 4 Evoker Wizard Sample Build",
        class_id="wizard",
        level=4,
        template_name="Level 4 Evoker Wizard Sample Build",
        behavior_profile="arcane_artillery",
        max_hp=26,
        ac=12,
        speed=30,
        initiative_mod=2,
        passive_perception=11,
        ability_mods=wizard_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"dagger": player_weapons["dagger"]},
        role_tags=("caster",),
        medicine_modifier=1,
        default_melee_weapon_id="dagger",
        combat_cantrip_ids=("fire_bolt", "shocking_grasp"),
        prepared_combat_spell_ids=(
            "magic_missile",
            "shield",
            "burning_hands",
            "mage_armor",
            "scorching_ray",
            "shatter",
        ),
    ),
    "wizard_level5_evoker_sample_build": PlayerLoadoutDefinition(
        loadout_id="wizard_level5_evoker_sample_build",
        display_name="Level 5 Evoker Wizard Sample Build",
        class_id="wizard",
        level=5,
        template_name="Level 5 Evoker Wizard Sample Build",
        behavior_profile="arcane_artillery",
        max_hp=32,
        ac=12,
        speed=30,
        initiative_mod=2,
        passive_perception=11,
        ability_mods=wizard_level4_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"dagger": player_weapons["dagger"]},
        role_tags=("caster",),
        medicine_modifier=1,
        default_melee_weapon_id="dagger",
        combat_cantrip_ids=("fire_bolt", "shocking_grasp"),
        prepared_combat_spell_ids=(
            "magic_missile",
            "shield",
            "burning_hands",
            "mage_armor",
            "scorching_ray",
            "shatter",
            "fireball",
            "counterspell",
            "haste",
        ),
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
                "shortbow": rogue_vex_shortbow,
                "shortsword": player_weapons["shortsword"],
            },
            extra_feature_ids=("weapon_mastery_vex",),
            default_melee_weapon_id="shortsword",
            default_ranged_weapon_id="shortbow",
            medicine_modifier=1,
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
    "fighter_level3_sample_trio": PlayerPresetDefinition(
        preset_id="fighter_level3_sample_trio",
        display_name="Level 3 Fighter Battle Master Trio",
        description="Three level 3 great-weapon Battle Master fighters with Superiority Dice.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="fighter_level3_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "fighter_level4_sample_trio": PlayerPresetDefinition(
        preset_id="fighter_level4_sample_trio",
        display_name="Level 4 Fighter Battle Master Trio",
        description="Three level 4 great-weapon Battle Master fighters with Great Weapon Master.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="fighter_level4_sample_build") for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "fighter_level5_sample_trio": PlayerPresetDefinition(
        preset_id="fighter_level5_sample_trio",
        display_name="Level 5 Fighter Battle Master Trio",
        description="Three level 5 great-weapon Battle Master fighters with Extra Attack and Tactical Shift.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="fighter_level5_sample_build") for fighter_id in TRIO_PLAYER_IDS
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
    "rogue_level3_ranged_assassin_trio": PlayerPresetDefinition(
        preset_id="rogue_level3_ranged_assassin_trio",
        display_name="Level 3 Ranged Assassin Rogue Trio",
        description="Three level 3 ranged Assassin rogues with shortbows, Steady Aim, and Assassinate.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_ranged_level3_assassin_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "rogue_level4_ranged_assassin_trio": PlayerPresetDefinition(
        preset_id="rogue_level4_ranged_assassin_trio",
        display_name="Level 4 Ranged Assassin Rogue Trio",
        description="Three level 4 ranged Assassin rogues with shortbows, Sharpshooter, Steady Aim, and Assassinate.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_ranged_level4_assassin_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "rogue_level5_ranged_assassin_trio": PlayerPresetDefinition(
        preset_id="rogue_level5_ranged_assassin_trio",
        display_name="Level 5 Ranged Assassin Rogue Trio",
        description="Three level 5 ranged Assassin rogues with shortbows, Cunning Strike, and Uncanny Dodge.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="rogue_ranged_level5_assassin_sample_build")
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
    "paladin_level1_sample_trio": PlayerPresetDefinition(
        preset_id="paladin_level1_sample_trio",
        display_name="Level 1 Paladin Trio",
        description="Three level 1 plate-and-shield paladins with Bless, Cure Wounds, and Lay on Hands.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="paladin_level1_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "paladin_level2_sample_trio": PlayerPresetDefinition(
        preset_id="paladin_level2_sample_trio",
        display_name="Level 2 Paladin Trio",
        description="Three level 2 plate-and-shield paladins with Defense, Divine Smite, Bless, and Lay on Hands.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="paladin_level2_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "paladin_level3_sample_trio": PlayerPresetDefinition(
        preset_id="paladin_level3_sample_trio",
        display_name="Level 3 Paladin Trio",
        description="Three level 3 Oath of the Ancients paladins with Nature's Wrath.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="paladin_level3_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "paladin_level4_sample_trio": PlayerPresetDefinition(
        preset_id="paladin_level4_sample_trio",
        display_name="Level 4 Paladin Trio",
        description="Three level 4 Oath of the Ancients paladins with Sentinel.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="paladin_level4_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "paladin_level5_sample_trio": PlayerPresetDefinition(
        preset_id="paladin_level5_sample_trio",
        display_name="Level 5 Paladin Trio",
        description="Three level 5 Oath of the Ancients paladins with Extra Attack, level 2 Bless, and Aid rules support.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="paladin_level5_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "wizard_sample_trio": PlayerPresetDefinition(
        preset_id="wizard_sample_trio",
        display_name="Level 1 Wizard Trio",
        description="Three level 1 wizards with direct damage, melee escape, Shield, and Burning Hands pressure.",
        units=tuple(PlayerPresetUnit(unit_id=fighter_id, loadout_id="wizard_sample_build") for fighter_id in TRIO_PLAYER_IDS),
    ),
    "wizard_level2_sample_trio": PlayerPresetDefinition(
        preset_id="wizard_level2_sample_trio",
        display_name="Level 2 Wizard Trio",
        description="Three level 2 wizards with extra durability, a third level 1 slot, and Mage Armor metadata.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="wizard_level2_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "wizard_level3_evoker_sample_trio": PlayerPresetDefinition(
        preset_id="wizard_level3_evoker_sample_trio",
        display_name="Level 3 Evoker Wizard Trio",
        description="Three level 3 Evoker wizards with Potent Cantrip, Scorching Ray, and Shatter.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="wizard_level3_evoker_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "wizard_level4_evoker_sample_trio": PlayerPresetDefinition(
        preset_id="wizard_level4_evoker_sample_trio",
        display_name="Level 4 Evoker Wizard Trio",
        description="Three level 4 Evoker wizards with an Intelligence ASI and expanded spell access metadata.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="wizard_level4_evoker_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "wizard_level5_evoker_sample_trio": PlayerPresetDefinition(
        preset_id="wizard_level5_evoker_sample_trio",
        display_name="Level 5 Evoker Wizard Trio",
        description="Three level 5 Evoker wizards with level 3 slot and spell access metadata.",
        units=tuple(
            PlayerPresetUnit(unit_id=fighter_id, loadout_id="wizard_level5_evoker_sample_build")
            for fighter_id in TRIO_PLAYER_IDS
        ),
    ),
    "martial_mixed_party": PlayerPresetDefinition(
        preset_id="martial_mixed_party",
        display_name="Level 5 Adventuring Party",
        description="One level 5 Battle Master fighter, one level 5 Paladin, one level 5 ranged Assassin rogue, and one level 5 Evoker wizard.",
        units=(
            PlayerPresetUnit(unit_id="F1", loadout_id="fighter_level5_sample_build"),
            PlayerPresetUnit(unit_id="F2", loadout_id="paladin_level5_sample_build"),
            PlayerPresetUnit(unit_id="F3", loadout_id="rogue_ranged_level5_assassin_sample_build"),
            PlayerPresetUnit(unit_id="F4", loadout_id="wizard_level5_evoker_sample_build"),
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
    "fighter_level3_sample_trio",
    "fighter_level4_sample_trio",
    "fighter_level5_sample_trio",
    "rogue_ranged_trio",
    "rogue_melee_trio",
    "rogue_level2_ranged_trio",
    "rogue_level2_melee_trio",
    "rogue_level3_ranged_assassin_trio",
    "rogue_level4_ranged_assassin_trio",
    "rogue_level5_ranged_assassin_trio",
    "barbarian_sample_trio",
    "barbarian_level2_sample_trio",
    "monk_sample_trio",
    "monk_level2_sample_trio",
    "paladin_level1_sample_trio",
    "paladin_level2_sample_trio",
    "paladin_level3_sample_trio",
    "paladin_level4_sample_trio",
    "paladin_level5_sample_trio",
    "wizard_sample_trio",
    "wizard_level2_sample_trio",
    "wizard_level3_evoker_sample_trio",
    "wizard_level4_evoker_sample_trio",
    "wizard_level5_evoker_sample_trio",
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


def get_combat_skill_ability_modifier(loadout: PlayerLoadoutDefinition, skill_id: str) -> int:
    ability_id = COMBAT_SKILL_ABILITY_IDS.get(skill_id)
    if ability_id is None:
        raise ValueError(f"Unsupported combat skill '{skill_id}'.")
    return getattr(loadout.ability_mods, ability_id)


def build_combat_skill_modifiers_for_loadout(loadout: PlayerLoadoutDefinition) -> dict[str, int]:
    modifiers = deepcopy(loadout.combat_skill_modifiers or {})
    proficiency_bonus = get_proficiency_bonus(loadout.level)

    for feature_id in get_feature_ids_for_loadout(loadout):
        skill_id = EXPERTISE_SKILL_BY_FEATURE_ID.get(feature_id)
        if skill_id is None:
            continue
        modifiers[skill_id] = get_combat_skill_ability_modifier(loadout, skill_id) + (2 * proficiency_bonus)

    return modifiers


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
        superiority_dice=resource_pools.get("superiority_dice", 0),
        focus_points=resource_pools.get("focus_points", 0),
        uncanny_metabolism_uses=resource_pools.get("uncanny_metabolism", 0),
        spell_slots_level_1=resource_pools.get("spell_slots_level_1", 0),
        spell_slots_level_2=resource_pools.get("spell_slots_level_2", 0),
        spell_slots_level_3=resource_pools.get("spell_slots_level_3", 0),
        lay_on_hands_points=resource_pools.get("lay_on_hands", 0),
        channel_divinity_uses=resource_pools.get("channel_divinity", 0),
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
        combat_skill_modifiers=build_combat_skill_modifiers_for_loadout(loadout),
        combat_cantrip_ids=list(loadout.combat_cantrip_ids),
        prepared_combat_spell_ids=list(loadout.prepared_combat_spell_ids),
        cantrips_known=get_progression_scalar(loadout.class_id, loadout.level, "cantrips_known", 0),
        spellbook_spells=get_progression_scalar(loadout.class_id, loadout.level, "spellbook_spells", 0),
        prepared_spells=get_progression_scalar(loadout.class_id, loadout.level, "prepared_spells", 0),
        damage_resistances=(),
        damage_immunities=(),
        damage_vulnerabilities=(),
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
