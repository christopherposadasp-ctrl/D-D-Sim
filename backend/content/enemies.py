from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from backend.content.attack_sequences import (
    AttackActionDefinition,
    AttackStepDefinition,
    build_player_attack_action,
    repeated_choice_attack_action,
    single_weapon_attack_action,
)
from backend.content.monster_traits import get_monster_trait
from backend.engine.models.state import (
    AbilityModifiers,
    AttackId,
    ConditionState,
    DiceSpec,
    Footprint,
    GridPosition,
    OnHitEffect,
    ResourceState,
    RoleTag,
    SizeCategory,
    TerrainFeature,
    UnitState,
    WeaponDamageComponent,
    WeaponProfile,
    WeaponRange,
)


@dataclass(frozen=True)
class MonsterDefinition:
    """Static monster content entry.

    The live simulator still uses a generic UnitState during combat. This
    definition object exists so monster uniqueness is represented in data:
    attacks, traits, legal actions, and AI profile choice all live here.
    """

    base_creature_id: str
    variant_id: str
    display_name: str
    combat_role: str
    ai_profile_id: str
    max_hp: int
    ac: int
    speed: int
    initiative_mod: int
    passive_perception: int
    ability_mods: AbilityModifiers
    size_category: SizeCategory
    footprint: Footprint
    attacks: dict[str, WeaponProfile]
    tags: tuple[str, ...] = ()
    creature_tags: tuple[str, ...] = ()
    role_tags: tuple[RoleTag, ...] = ()
    action_ids: tuple[str, ...] = ()
    special_action_ids: tuple[str, ...] = ()
    bonus_action_ids: tuple[str, ...] = ()
    reaction_ids: tuple[str, ...] = ("opportunity_attack",)
    trait_ids: tuple[str, ...] = ()
    attack_actions: tuple[AttackActionDefinition, ...] = ()
    default_melee_attack_action_id: str | None = None
    default_ranged_attack_action_id: str | None = None
    medicine_modifier: int = -1
    damage_resistances: tuple[str, ...] = ()
    damage_immunities: tuple[str, ...] = ()
    damage_vulnerabilities: tuple[str, ...] = ()
    condition_immunities: tuple[str, ...] = ()
    extra_resource_pools: dict[str, int] = field(default_factory=dict)


# Keep the legacy type name as an alias so older references still read cleanly.
EnemyVariantDefinition = MonsterDefinition


@dataclass(frozen=True)
class EnemyPresetUnit:
    unit_id: str
    variant_id: str
    position: GridPosition


@dataclass(frozen=True)
class EnemyPresetDefinition:
    preset_id: str
    display_name: str
    description: str
    units: tuple[EnemyPresetUnit, ...]
    terrain_features: tuple[TerrainFeature, ...] = ()


goblin_ability_mods = AbilityModifiers(str=-1, dex=2, con=0, int=0, wis=-1, cha=-1)
bandit_ability_mods = AbilityModifiers(str=1, dex=1, con=0, int=0, wis=0, cha=0)
guard_ability_mods = AbilityModifiers(str=1, dex=1, con=1, int=0, wis=0, cha=0)
scout_ability_mods = AbilityModifiers(str=0, dex=2, con=1, int=0, wis=1, cha=0)
orc_ability_mods = AbilityModifiers(str=3, dex=1, con=2, int=-1, wis=0, cha=0)
wolf_ability_mods = AbilityModifiers(str=1, dex=2, con=1, int=-4, wis=1, cha=-2)
giant_toad_ability_mods = AbilityModifiers(str=2, dex=1, con=1, int=-4, wis=0, cha=-4)
crocodile_ability_mods = AbilityModifiers(str=2, dex=0, con=1, int=-4, wis=0, cha=-3)
hobgoblin_warrior_ability_mods = AbilityModifiers(str=1, dex=1, con=1, int=0, wis=0, cha=-1)
tough_ability_mods = AbilityModifiers(str=2, dex=1, con=2, int=0, wis=0, cha=0)
axe_beak_ability_mods = AbilityModifiers(str=2, dex=1, con=1, int=-4, wis=0, cha=-3)
draft_horse_ability_mods = AbilityModifiers(str=4, dex=0, con=2, int=-4, wis=0, cha=-2)
riding_horse_ability_mods = AbilityModifiers(str=3, dex=1, con=1, int=-4, wis=0, cha=-2)
cultist_ability_mods = AbilityModifiers(str=0, dex=1, con=0, int=0, wis=1, cha=0)
warrior_infantry_ability_mods = AbilityModifiers(str=1, dex=0, con=0, int=-1, wis=0, cha=-1)
camel_ability_mods = AbilityModifiers(str=2, dex=-1, con=3, int=-4, wis=0, cha=-3)
mule_ability_mods = AbilityModifiers(str=2, dex=0, con=1, int=-4, wis=0, cha=-3)
pony_ability_mods = AbilityModifiers(str=2, dex=0, con=1, int=-4, wis=0, cha=-2)
commoner_ability_mods = AbilityModifiers(str=0, dex=0, con=0, int=0, wis=0, cha=0)
hyena_ability_mods = AbilityModifiers(str=0, dex=1, con=1, int=-4, wis=1, cha=-3)
jackal_ability_mods = AbilityModifiers(str=-1, dex=2, con=0, int=-4, wis=1, cha=-2)
skeleton_ability_mods = AbilityModifiers(str=0, dex=3, con=2, int=-2, wis=-1, cha=-3)
zombie_ability_mods = AbilityModifiers(str=1, dex=-2, con=3, int=-4, wis=-2, cha=-3)
ogre_zombie_ability_mods = AbilityModifiers(str=4, dex=-2, con=4, int=-4, wis=-2, cha=-3)
giant_rat_ability_mods = AbilityModifiers(str=-2, dex=3, con=0, int=-4, wis=0, cha=-3)
giant_fire_beetle_ability_mods = AbilityModifiers(str=-1, dex=0, con=1, int=-5, wis=-2, cha=-4)
giant_weasel_ability_mods = AbilityModifiers(str=0, dex=3, con=0, int=-3, wis=1, cha=-3)
worg_ability_mods = AbilityModifiers(str=3, dex=1, con=1, int=-2, wis=0, cha=-1)
animated_armor_ability_mods = AbilityModifiers(str=2, dex=0, con=1, int=-5, wis=-4, cha=-5)
dire_wolf_ability_mods = AbilityModifiers(str=3, dex=2, con=2, int=-4, wis=1, cha=-2)
awakened_shrub_ability_mods = AbilityModifiers(str=-4, dex=-1, con=0, int=0, wis=0, cha=-2)
awakened_tree_ability_mods = AbilityModifiers(str=4, dex=-2, con=2, int=0, wis=0, cha=-2)
lemure_ability_mods = AbilityModifiers(str=0, dex=-3, con=0, int=-5, wis=0, cha=-4)
ogre_ability_mods = AbilityModifiers(str=4, dex=-1, con=3, int=-3, wis=-2, cha=-2)
black_bear_ability_mods = AbilityModifiers(str=2, dex=1, con=2, int=-4, wis=1, cha=-2)
brown_bear_ability_mods = AbilityModifiers(str=3, dex=1, con=2, int=-4, wis=1, cha=-2)
tiger_ability_mods = AbilityModifiers(str=3, dex=3, con=2, int=-4, wis=1, cha=-1)
saber_toothed_tiger_ability_mods = AbilityModifiers(str=4, dex=3, con=2, int=-4, wis=1, cha=-1)
owlbear_ability_mods = AbilityModifiers(str=5, dex=1, con=3, int=-4, wis=1, cha=-2)
ankylosaurus_ability_mods = AbilityModifiers(str=4, dex=0, con=2, int=-4, wis=1, cha=-3)
archelon_ability_mods = AbilityModifiers(str=4, dex=3, con=1, int=-3, wis=2, cha=-2)
grick_ability_mods = AbilityModifiers(str=2, dex=2, con=0, int=-4, wis=2, cha=-3)
griffon_ability_mods = AbilityModifiers(str=4, dex=2, con=3, int=-4, wis=1, cha=-1)
hippopotamus_ability_mods = AbilityModifiers(str=5, dex=-2, con=2, int=-4, wis=1, cha=-3)
berserker_ability_mods = AbilityModifiers(str=3, dex=1, con=3, int=-1, wis=0, cha=-1)
gnoll_warrior_ability_mods = AbilityModifiers(str=2, dex=1, con=0, int=-2, wis=0, cha=-2)
giant_hyena_ability_mods = AbilityModifiers(str=3, dex=2, con=2, int=-4, wis=1, cha=-2)
bandit_captain_ability_mods = AbilityModifiers(str=2, dex=3, con=2, int=2, wis=0, cha=2)
goblin_boss_ability_mods = AbilityModifiers(str=0, dex=2, con=0, int=0, wis=-1, cha=0)
bugbear_warrior_ability_mods = AbilityModifiers(str=2, dex=2, con=1, int=-1, wis=0, cha=-1)
noble_ability_mods = AbilityModifiers(str=0, dex=1, con=0, int=1, wis=2, cha=3)
mastiff_ability_mods = AbilityModifiers(str=1, dex=2, con=1, int=-4, wis=1, cha=-2)
giant_crab_ability_mods = AbilityModifiers(str=1, dex=1, con=0, int=-5, wis=-1, cha=-4)
giant_badger_ability_mods = AbilityModifiers(str=1, dex=0, con=3, int=-4, wis=1, cha=-3)
giant_lizard_ability_mods = AbilityModifiers(str=2, dex=1, con=1, int=-4, wis=0, cha=-3)
violet_fungus_ability_mods = AbilityModifiers(str=-4, dex=-5, con=0, int=-5, wis=-4, cha=-5)
polar_bear_ability_mods = AbilityModifiers(str=5, dex=2, con=3, int=-4, wis=1, cha=-2)
guard_captain_ability_mods = AbilityModifiers(str=4, dex=2, con=3, int=1, wis=2, cha=1)
warrior_veteran_ability_mods = AbilityModifiers(str=3, dex=1, con=2, int=0, wis=0, cha=0)
knight_ability_mods = AbilityModifiers(str=3, dex=0, con=2, int=0, wis=0, cha=2)
medium_footprint = Footprint(width=1, height=1)
large_footprint = Footprint(width=2, height=2)
huge_footprint = Footprint(width=3, height=3)


def build_rock_terrain_feature() -> TerrainFeature:
    return TerrainFeature(
        feature_id="rock_1",
        kind="rock",
        position=GridPosition(x=5, y=8),
        footprint=Footprint(width=1, height=1),
    )

enemy_weapons: dict[str, WeaponProfile] = {
    "scimitar": WeaponProfile(
        id="scimitar",
        display_name="Scimitar",
        attack_bonus=4,
        ability_modifier=2,
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=2,
        damage_type="slashing",
        kind="melee",
        advantage_damage_dice=[DiceSpec(count=1, sides=4)],
    ),
    "shortbow": WeaponProfile(
        id="shortbow",
        display_name="Shortbow",
        attack_bonus=4,
        ability_modifier=2,
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=2,
        damage_type="piercing",
        kind="ranged",
        range=WeaponRange(normal=80, long=320),
        advantage_damage_dice=[DiceSpec(count=1, sides=4)],
    ),
    "club": WeaponProfile(
        id="club",
        display_name="Club",
        attack_bonus=3,
        ability_modifier=1,
        damage_dice=[DiceSpec(count=1, sides=4)],
        damage_modifier=1,
        damage_type="bludgeoning",
        kind="melee",
    ),
    "spear": WeaponProfile(
        id="spear",
        display_name="Spear",
        attack_bonus=3,
        ability_modifier=1,
        damage_dice=[DiceSpec(count=1, sides=6)],
        damage_modifier=1,
        damage_type="piercing",
        kind="melee",
    ),
    "longbow": WeaponProfile(
        id="longbow",
        display_name="Longbow",
        attack_bonus=4,
        ability_modifier=2,
        damage_dice=[DiceSpec(count=1, sides=8)],
        damage_modifier=2,
        damage_type="piercing",
        kind="ranged",
        range=WeaponRange(normal=150, long=600),
    ),
    "greataxe": WeaponProfile(
        id="greataxe",
        display_name="Greataxe",
        attack_bonus=5,
        ability_modifier=3,
        damage_dice=[DiceSpec(count=1, sides=12)],
        damage_modifier=3,
        damage_type="slashing",
        kind="melee",
        two_handed=True,
    ),
    "bite": WeaponProfile(
        id="bite",
        display_name="Bite",
        attack_bonus=4,
        ability_modifier=2,
        damage_dice=[DiceSpec(count=2, sides=4)],
        damage_modifier=2,
        damage_type="piercing",
        kind="melee",
        on_hit_effects=[OnHitEffect(kind="prone_on_hit")],
    ),
    "toad_bite": WeaponProfile(
        id="toad_bite",
        display_name="Bite",
        attack_bonus=4,
        ability_modifier=2,
        damage_components=[
            WeaponDamageComponent(
                damage_type="piercing",
                damage_dice=[DiceSpec(count=1, sides=10)],
                damage_modifier=2,
            ),
            WeaponDamageComponent(
                damage_type="poison",
                damage_dice=[DiceSpec(count=1, sides=10)],
                damage_modifier=0,
            ),
        ],
        kind="melee",
        reach=10,
        on_hit_effects=[
            OnHitEffect(kind="grapple_and_restrain", escape_dc=13, max_target_size="medium"),
        ],
        locks_to_grappled_target=True,
    ),
    "crocodile_bite": WeaponProfile(
        id="crocodile_bite",
        display_name="Bite",
        attack_bonus=4,
        ability_modifier=2,
        damage_dice=[DiceSpec(count=1, sides=8)],
        damage_modifier=2,
        damage_type="piercing",
        kind="melee",
        on_hit_effects=[
            OnHitEffect(kind="grapple_on_hit", escape_dc=12, max_target_size="medium"),
        ],
        locks_to_grappled_target=True,
    ),
}


def melee_attack_action(weapon_id: AttackId, display_name: str = "Melee Attack") -> AttackActionDefinition:
    return single_weapon_attack_action("melee_attack", display_name, weapon_id)


def ranged_attack_action(weapon_id: AttackId, display_name: str = "Ranged Attack") -> AttackActionDefinition:
    return single_weapon_attack_action("ranged_attack", display_name, weapon_id)


def fixed_multiattack_action(
    action_id: str,
    display_name: str,
    weapon_ids: tuple[AttackId, ...],
) -> AttackActionDefinition:
    return AttackActionDefinition(
        action_id=action_id,
        display_name=display_name,
        steps=tuple(AttackStepDefinition(allowed_weapon_ids=(weapon_id,)) for weapon_id in weapon_ids),
    )


MONSTER_DEFINITIONS: dict[str, MonsterDefinition] = {
    "goblin_raider": MonsterDefinition(
        base_creature_id="goblin",
        variant_id="goblin_raider",
        display_name="Goblin Raider",
        combat_role="goblin_melee",
        ai_profile_id="melee_brute",
        max_hp=10,
        ac=15,
        speed=30,
        initiative_mod=2,
        passive_perception=9,
        ability_mods=goblin_ability_mods,
        size_category="small",
        footprint=medium_footprint,
        attacks={"scimitar": enemy_weapons["scimitar"]},
        tags=("goblin", "melee"),
        action_ids=("melee_attack",),
        trait_ids=("nimble_escape",),
        attack_actions=(melee_attack_action("scimitar", "Scimitar"),),
        default_melee_attack_action_id="melee_attack",
    ),
    "goblin_archer": MonsterDefinition(
        base_creature_id="goblin",
        variant_id="goblin_archer",
        display_name="Goblin Archer",
        combat_role="goblin_archer",
        ai_profile_id="ranged_skirmisher",
        max_hp=10,
        ac=15,
        speed=30,
        initiative_mod=2,
        passive_perception=9,
        ability_mods=goblin_ability_mods,
        size_category="small",
        footprint=medium_footprint,
        attacks={
            "scimitar": enemy_weapons["scimitar"],
            "shortbow": enemy_weapons["shortbow"],
        },
        tags=("goblin", "archer"),
        action_ids=("melee_attack", "ranged_attack"),
        trait_ids=("nimble_escape",),
        attack_actions=(
            melee_attack_action("scimitar", "Scimitar"),
            ranged_attack_action("shortbow", "Shortbow"),
        ),
        default_melee_attack_action_id="melee_attack",
        default_ranged_attack_action_id="ranged_attack",
    ),
    "bandit_melee": MonsterDefinition(
        base_creature_id="bandit",
        variant_id="bandit_melee",
        display_name="Bandit Melee",
        combat_role="bandit_melee",
        ai_profile_id="melee_brute",
        max_hp=11,
        ac=12,
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=bandit_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"club": enemy_weapons["club"]},
        tags=("humanoid", "bandit", "melee"),
        action_ids=("melee_attack",),
        attack_actions=(melee_attack_action("club", "Club"),),
        default_melee_attack_action_id="melee_attack",
    ),
    "bandit_archer": MonsterDefinition(
        base_creature_id="bandit",
        variant_id="bandit_archer",
        display_name="Bandit Archer",
        combat_role="bandit_archer",
        ai_profile_id="ranged_skirmisher",
        max_hp=11,
        ac=12,
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=bandit_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "club": enemy_weapons["club"],
            "shortbow": WeaponProfile(
                id="shortbow",
                display_name="Shortbow",
                attack_bonus=3,
                ability_modifier=1,
                damage_dice=[DiceSpec(count=1, sides=6)],
                damage_modifier=1,
                damage_type="piercing",
                kind="ranged",
                range=WeaponRange(normal=80, long=320),
            ),
        },
        tags=("humanoid", "bandit", "archer"),
        action_ids=("melee_attack", "ranged_attack"),
        attack_actions=(
            melee_attack_action("club", "Club"),
            ranged_attack_action("shortbow", "Shortbow"),
        ),
        default_melee_attack_action_id="melee_attack",
        default_ranged_attack_action_id="ranged_attack",
    ),
    "guard": MonsterDefinition(
        base_creature_id="guard",
        variant_id="guard",
        display_name="Guard",
        combat_role="guard",
        ai_profile_id="line_holder",
        max_hp=11,
        ac=16,
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=guard_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"spear": enemy_weapons["spear"]},
        tags=("humanoid", "guard", "melee"),
        action_ids=("melee_attack",),
        attack_actions=(melee_attack_action("spear", "Spear"),),
        default_melee_attack_action_id="melee_attack",
    ),
    "scout": MonsterDefinition(
        base_creature_id="scout",
        variant_id="scout",
        display_name="Scout",
        combat_role="scout",
        ai_profile_id="ranged_skirmisher",
        max_hp=16,
        ac=13,
        speed=30,
        initiative_mod=2,
        passive_perception=13,
        ability_mods=scout_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={
            "club": WeaponProfile(
                id="club",
                display_name="Shortsword",
                attack_bonus=4,
                ability_modifier=2,
                damage_dice=[DiceSpec(count=1, sides=6)],
                damage_modifier=2,
                damage_type="piercing",
                kind="melee",
            ),
            "longbow": enemy_weapons["longbow"],
        },
        tags=("humanoid", "scout", "archer"),
        action_ids=("melee_attack", "ranged_attack", "multiattack"),
        attack_actions=(
            melee_attack_action("club", "Shortsword"),
            ranged_attack_action("longbow", "Longbow"),
            repeated_choice_attack_action("multiattack", "Multiattack", ("club", "longbow"), 2),
        ),
        default_melee_attack_action_id="multiattack",
        default_ranged_attack_action_id="multiattack",
    ),
    "orc_warrior": MonsterDefinition(
        base_creature_id="orc",
        variant_id="orc_warrior",
        display_name="Orc Warrior",
        combat_role="orc_warrior",
        ai_profile_id="melee_brute",
        max_hp=15,
        ac=13,
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=orc_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"greataxe": enemy_weapons["greataxe"]},
        tags=("orc", "melee", "frontliner"),
        action_ids=("melee_attack",),
        trait_ids=("aggressive",),
        attack_actions=(melee_attack_action("greataxe", "Greataxe"),),
        default_melee_attack_action_id="melee_attack",
    ),
    "wolf": MonsterDefinition(
        base_creature_id="wolf",
        variant_id="wolf",
        display_name="Wolf",
        combat_role="wolf",
        ai_profile_id="pack_hunter",
        max_hp=11,
        ac=13,
        speed=40,
        initiative_mod=2,
        passive_perception=13,
        ability_mods=wolf_ability_mods,
        size_category="medium",
        footprint=medium_footprint,
        attacks={"bite": enemy_weapons["bite"]},
        tags=("beast", "wolf", "melee"),
        action_ids=("melee_attack",),
        trait_ids=("pack_tactics",),
        attack_actions=(melee_attack_action("bite", "Bite"),),
        default_melee_attack_action_id="melee_attack",
    ),
    "giant_toad": MonsterDefinition(
        base_creature_id="giant_toad",
        variant_id="giant_toad",
        display_name="Giant Toad",
        combat_role="giant_toad",
        ai_profile_id="swallow_predator",
        max_hp=39,
        ac=11,
        speed=20,
        initiative_mod=1,
        passive_perception=10,
        ability_mods=giant_toad_ability_mods,
        size_category="large",
        footprint=large_footprint,
        attacks={"toad_bite": enemy_weapons["toad_bite"]},
        tags=("beast", "toad", "solo"),
        action_ids=("melee_attack", "swallow"),
        special_action_ids=("swallow",),
        attack_actions=(melee_attack_action("toad_bite", "Bite"),),
        default_melee_attack_action_id="melee_attack",
    ),
    "crocodile": MonsterDefinition(
        base_creature_id="crocodile",
        variant_id="crocodile",
        display_name="Crocodile",
        combat_role="crocodile",
        ai_profile_id="grappling_brute",
        max_hp=13,
        ac=12,
        speed=20,
        initiative_mod=0,
        passive_perception=10,
        ability_mods=crocodile_ability_mods,
        size_category="large",
        footprint=large_footprint,
        attacks={"crocodile_bite": enemy_weapons["crocodile_bite"]},
        tags=("beast", "crocodile", "melee", "controller"),
        action_ids=("melee_attack",),
        attack_actions=(melee_attack_action("crocodile_bite", "Bite"),),
        default_melee_attack_action_id="melee_attack",
    ),
}

MONSTER_DEFINITIONS.update(
    {
        "hobgoblin_warrior": MonsterDefinition(
            base_creature_id="hobgoblin",
            variant_id="hobgoblin_warrior",
            display_name="Hobgoblin Warrior",
            combat_role="hobgoblin_melee",
            ai_profile_id="melee_brute",
            max_hp=11,
            ac=18,
            speed=30,
            initiative_mod=3,
            passive_perception=10,
            ability_mods=hobgoblin_warrior_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "longsword": WeaponProfile(
                    id="longsword",
                    display_name="Longsword",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=2, sides=10)],
                    damage_modifier=1,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("humanoid", "hobgoblin", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("pack_tactics",),
            attack_actions=(melee_attack_action("longsword", "Longsword"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "hobgoblin_archer": MonsterDefinition(
            base_creature_id="hobgoblin",
            variant_id="hobgoblin_archer",
            display_name="Hobgoblin Archer",
            combat_role="hobgoblin_archer",
            ai_profile_id="ranged_skirmisher",
            max_hp=11,
            ac=18,
            speed=30,
            initiative_mod=3,
            passive_perception=10,
            ability_mods=hobgoblin_warrior_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "longsword": WeaponProfile(
                    id="longsword",
                    display_name="Longsword",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=2, sides=10)],
                    damage_modifier=1,
                    damage_type="slashing",
                    kind="melee",
                ),
                "longbow": WeaponProfile(
                    id="longbow",
                    display_name="Longbow",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=150, long=600),
                    advantage_damage_components=[
                        WeaponDamageComponent(
                            damage_type="poison",
                            damage_dice=[DiceSpec(count=3, sides=4)],
                            damage_modifier=0,
                        )
                    ],
                ),
            },
            tags=("humanoid", "hobgoblin", "archer"),
            action_ids=("melee_attack", "ranged_attack"),
            trait_ids=("pack_tactics",),
            attack_actions=(
                melee_attack_action("longsword", "Longsword"),
                ranged_attack_action("longbow", "Longbow"),
            ),
            default_melee_attack_action_id="melee_attack",
            default_ranged_attack_action_id="ranged_attack",
        ),
        "tough": MonsterDefinition(
            base_creature_id="tough",
            variant_id="tough",
            display_name="Tough",
            combat_role="tough",
            ai_profile_id="ranged_skirmisher",
            max_hp=32,
            ac=12,
            speed=30,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=tough_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "mace": WeaponProfile(
                    id="mace",
                    display_name="Mace",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                ),
                "heavy_crossbow": WeaponProfile(
                    id="heavy_crossbow",
                    display_name="Heavy Crossbow",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=10)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=100, long=400),
                ),
            },
            tags=("humanoid", "tough", "archer"),
            action_ids=("melee_attack", "ranged_attack"),
            trait_ids=("pack_tactics",),
            attack_actions=(
                melee_attack_action("mace", "Mace"),
                ranged_attack_action("heavy_crossbow", "Heavy Crossbow"),
            ),
            default_melee_attack_action_id="melee_attack",
            default_ranged_attack_action_id="ranged_attack",
        ),
        "axe_beak": MonsterDefinition(
            base_creature_id="axe_beak",
            variant_id="axe_beak",
            display_name="Axe Beak",
            combat_role="axe_beak",
            ai_profile_id="melee_brute",
            max_hp=19,
            ac=11,
            speed=50,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=axe_beak_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "beak": WeaponProfile(
                    id="beak",
                    display_name="Beak",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=2,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("beast", "mount", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("beak", "Beak"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "draft_horse": MonsterDefinition(
            base_creature_id="draft_horse",
            variant_id="draft_horse",
            display_name="Draft Horse",
            combat_role="draft_horse",
            ai_profile_id="melee_brute",
            max_hp=15,
            ac=10,
            speed=40,
            initiative_mod=0,
            passive_perception=10,
            ability_mods=draft_horse_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "hooves": WeaponProfile(
                    id="hooves",
                    display_name="Hooves",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=4,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("beast", "mount", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("hooves", "Hooves"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "riding_horse": MonsterDefinition(
            base_creature_id="riding_horse",
            variant_id="riding_horse",
            display_name="Riding Horse",
            combat_role="riding_horse",
            ai_profile_id="melee_brute",
            max_hp=13,
            ac=11,
            speed=60,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=riding_horse_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "hooves": WeaponProfile(
                    id="hooves",
                    display_name="Hooves",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=3,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("beast", "mount", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("hooves", "Hooves"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "cultist": MonsterDefinition(
            base_creature_id="cultist",
            variant_id="cultist",
            display_name="Cultist",
            combat_role="cultist",
            ai_profile_id="melee_brute",
            max_hp=9,
            ac=12,
            speed=30,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=cultist_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "ritual_sickle": WeaponProfile(
                    id="ritual_sickle",
                    display_name="Ritual Sickle",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_components=[
                        WeaponDamageComponent(
                            damage_type="slashing",
                            damage_dice=[DiceSpec(count=1, sides=4)],
                            damage_modifier=1,
                        ),
                        WeaponDamageComponent(
                            damage_type="necrotic",
                            damage_dice=[],
                            damage_modifier=1,
                        ),
                    ],
                    kind="melee",
                )
            },
            tags=("humanoid", "cultist", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("ritual_sickle", "Ritual Sickle"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "warrior_infantry": MonsterDefinition(
            base_creature_id="warrior_infantry",
            variant_id="warrior_infantry",
            display_name="Warrior Infantry",
            combat_role="warrior_infantry",
            ai_profile_id="line_holder",
            max_hp=9,
            ac=13,
            speed=30,
            initiative_mod=0,
            passive_perception=10,
            ability_mods=warrior_infantry_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "spear": WeaponProfile(
                    id="spear",
                    display_name="Spear",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("humanoid", "soldier", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("pack_tactics",),
            attack_actions=(melee_attack_action("spear", "Spear"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "camel": MonsterDefinition(
            base_creature_id="camel",
            variant_id="camel",
            display_name="Camel",
            combat_role="camel",
            ai_profile_id="melee_brute",
            max_hp=17,
            ac=10,
            speed=50,
            initiative_mod=-1,
            passive_perception=10,
            ability_mods=camel_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("beast", "mount", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "mule": MonsterDefinition(
            base_creature_id="mule",
            variant_id="mule",
            display_name="Mule",
            combat_role="mule",
            ai_profile_id="melee_brute",
            max_hp=11,
            ac=10,
            speed=40,
            initiative_mod=0,
            passive_perception=10,
            ability_mods=mule_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "hooves": WeaponProfile(
                    id="hooves",
                    display_name="Hooves",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("beast", "pack_animal", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("hooves", "Hooves"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "pony": MonsterDefinition(
            base_creature_id="pony",
            variant_id="pony",
            display_name="Pony",
            combat_role="pony",
            ai_profile_id="melee_brute",
            max_hp=11,
            ac=10,
            speed=40,
            initiative_mod=0,
            passive_perception=10,
            ability_mods=pony_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "hooves": WeaponProfile(
                    id="hooves",
                    display_name="Hooves",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("beast", "mount", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("hooves", "Hooves"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "commoner": MonsterDefinition(
            base_creature_id="commoner",
            variant_id="commoner",
            display_name="Commoner",
            combat_role="commoner",
            ai_profile_id="melee_brute",
            max_hp=4,
            ac=10,
            speed=30,
            initiative_mod=0,
            passive_perception=10,
            ability_mods=commoner_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "club": WeaponProfile(
                    id="club",
                    display_name="Club",
                    attack_bonus=2,
                    ability_modifier=0,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=0,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("humanoid", "civilian", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("club", "Club"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "hyena": MonsterDefinition(
            base_creature_id="hyena",
            variant_id="hyena",
            display_name="Hyena",
            combat_role="hyena",
            ai_profile_id="pack_hunter",
            max_hp=5,
            ac=11,
            speed=50,
            initiative_mod=1,
            passive_perception=13,
            ability_mods=hyena_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=2,
                    ability_modifier=0,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=0,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "pack", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("pack_tactics",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "jackal": MonsterDefinition(
            base_creature_id="jackal",
            variant_id="jackal",
            display_name="Jackal",
            combat_role="jackal",
            ai_profile_id="melee_brute",
            max_hp=3,
            ac=12,
            speed=40,
            initiative_mod=2,
            passive_perception=15,
            ability_mods=jackal_ability_mods,
            size_category="small",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=1,
                    ability_modifier=-1,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=-1,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "small", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "goblin_minion": MonsterDefinition(
            base_creature_id="goblin",
            variant_id="goblin_minion",
            display_name="Goblin Minion",
            combat_role="goblin_minion",
            ai_profile_id="ranged_skirmisher",
            max_hp=7,
            ac=12,
            speed=30,
            initiative_mod=2,
            passive_perception=9,
            ability_mods=goblin_ability_mods,
            size_category="small",
            footprint=medium_footprint,
            attacks={
                "dagger": WeaponProfile(
                    id="dagger",
                    display_name="Dagger",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=2,
                    damage_type="piercing",
                    kind="melee",
                ),
                "dagger_throw": WeaponProfile(
                    id="dagger_throw",
                    display_name="Dagger",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=2,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=20, long=60),
                ),
            },
            tags=("goblin", "minion", "archer"),
            action_ids=("melee_attack", "ranged_attack"),
            trait_ids=("nimble_escape",),
            attack_actions=(
                melee_attack_action("dagger", "Dagger"),
                ranged_attack_action("dagger_throw", "Dagger"),
            ),
            default_melee_attack_action_id="melee_attack",
            default_ranged_attack_action_id="ranged_attack",
        ),
        "skeleton": MonsterDefinition(
            base_creature_id="skeleton",
            variant_id="skeleton",
            display_name="Skeleton",
            combat_role="skeleton",
            ai_profile_id="ranged_skirmisher",
            max_hp=13,
            ac=14,
            speed=30,
            initiative_mod=3,
            passive_perception=9,
            ability_mods=skeleton_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "shortsword": WeaponProfile(
                    id="shortsword",
                    display_name="Shortsword",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                ),
                "shortbow": WeaponProfile(
                    id="shortbow",
                    display_name="Shortbow",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=80, long=320),
                ),
            },
            tags=("undead", "skeleton", "archer"),
            creature_tags=("undead",),
            action_ids=("melee_attack", "ranged_attack"),
            attack_actions=(
                melee_attack_action("shortsword", "Shortsword"),
                ranged_attack_action("shortbow", "Shortbow"),
            ),
            default_melee_attack_action_id="melee_attack",
            default_ranged_attack_action_id="ranged_attack",
            damage_immunities=("poison",),
            damage_vulnerabilities=("bludgeoning",),
        ),
        "zombie": MonsterDefinition(
            base_creature_id="zombie",
            variant_id="zombie",
            display_name="Zombie",
            combat_role="zombie",
            ai_profile_id="melee_brute",
            max_hp=15,
            ac=8,
            speed=20,
            initiative_mod=-2,
            passive_perception=8,
            ability_mods=zombie_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "slam": WeaponProfile(
                    id="slam",
                    display_name="Slam",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=1,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("undead", "zombie", "melee"),
            creature_tags=("undead",),
            action_ids=("melee_attack",),
            trait_ids=("undead_fortitude",),
            attack_actions=(melee_attack_action("slam", "Slam"),),
            default_melee_attack_action_id="melee_attack",
            damage_immunities=("poison",),
        ),
        "ogre_zombie": MonsterDefinition(
            base_creature_id="ogre_zombie",
            variant_id="ogre_zombie",
            display_name="Ogre Zombie",
            combat_role="ogre_zombie",
            ai_profile_id="melee_brute",
            max_hp=85,
            ac=8,
            speed=30,
            initiative_mod=-2,
            passive_perception=8,
            ability_mods=ogre_zombie_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "slam": WeaponProfile(
                    id="slam",
                    display_name="Slam",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=2, sides=8)],
                    damage_modifier=4,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("undead", "zombie", "ogre", "melee"),
            creature_tags=("undead",),
            action_ids=("melee_attack",),
            trait_ids=("undead_fortitude",),
            attack_actions=(melee_attack_action("slam", "Slam"),),
            default_melee_attack_action_id="melee_attack",
            damage_immunities=("poison",),
        ),
        "giant_rat": MonsterDefinition(
            base_creature_id="giant_rat",
            variant_id="giant_rat",
            display_name="Giant Rat",
            combat_role="giant_rat",
            ai_profile_id="pack_hunter",
            max_hp=7,
            ac=13,
            speed=30,
            initiative_mod=3,
            passive_perception=12,
            ability_mods=giant_rat_ability_mods,
            size_category="small",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "rat", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("pack_tactics",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "giant_fire_beetle": MonsterDefinition(
            base_creature_id="giant_fire_beetle",
            variant_id="giant_fire_beetle",
            display_name="Giant Fire Beetle",
            combat_role="giant_fire_beetle",
            ai_profile_id="melee_brute",
            max_hp=4,
            ac=13,
            speed=30,
            initiative_mod=0,
            passive_perception=8,
            ability_mods=giant_fire_beetle_ability_mods,
            size_category="small",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=1,
                    ability_modifier=-1,
                    damage_dice=[],
                    damage_modifier=1,
                    damage_type="fire",
                    kind="melee",
                )
            },
            tags=("beast", "beetle", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
            damage_resistances=("fire",),
        ),
        "giant_weasel": MonsterDefinition(
            base_creature_id="giant_weasel",
            variant_id="giant_weasel",
            display_name="Giant Weasel",
            combat_role="giant_weasel",
            ai_profile_id="melee_brute",
            max_hp=9,
            ac=13,
            speed=40,
            initiative_mod=3,
            passive_perception=13,
            ability_mods=giant_weasel_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "weasel", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "worg": MonsterDefinition(
            base_creature_id="worg",
            variant_id="worg",
            display_name="Worg",
            combat_role="worg",
            ai_profile_id="melee_brute",
            max_hp=26,
            ac=13,
            speed=50,
            initiative_mod=1,
            passive_perception=14,
            ability_mods=worg_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="harry_target")],
                )
            },
            tags=("fey", "worg", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "animated_armor": MonsterDefinition(
            base_creature_id="animated_armor",
            variant_id="animated_armor",
            display_name="Animated Armor",
            combat_role="animated_armor",
            ai_profile_id="melee_brute",
            max_hp=33,
            ac=18,
            speed=25,
            initiative_mod=2,
            passive_perception=6,
            ability_mods=animated_armor_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "slam": WeaponProfile(
                    id="slam",
                    display_name="Slam",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                )
            },
            tags=("construct", "armor", "melee"),
            action_ids=("multiattack",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("slam",), 2),),
            default_melee_attack_action_id="multiattack",
            damage_immunities=("poison", "psychic"),
        ),
        "dire_wolf": MonsterDefinition(
            base_creature_id="dire_wolf",
            variant_id="dire_wolf",
            display_name="Dire Wolf",
            combat_role="dire_wolf",
            ai_profile_id="pack_hunter",
            max_hp=22,
            ac=14,
            speed=50,
            initiative_mod=2,
            passive_perception=15,
            ability_mods=dire_wolf_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=10)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="prone_on_hit")],
                )
            },
            tags=("beast", "wolf", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("pack_tactics",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "awakened_shrub": MonsterDefinition(
            base_creature_id="awakened_shrub",
            variant_id="awakened_shrub",
            display_name="Awakened Shrub",
            combat_role="awakened_shrub",
            ai_profile_id="melee_brute",
            max_hp=10,
            ac=9,
            speed=20,
            initiative_mod=-1,
            passive_perception=10,
            ability_mods=awakened_shrub_ability_mods,
            size_category="small",
            footprint=medium_footprint,
            attacks={
                "rake": WeaponProfile(
                    id="rake",
                    display_name="Rake",
                    attack_bonus=1,
                    ability_modifier=-1,
                    damage_dice=[],
                    damage_modifier=1,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("plant", "shrub", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("rake", "Rake"),),
            default_melee_attack_action_id="melee_attack",
            damage_resistances=("piercing",),
            damage_vulnerabilities=("fire",),
        ),
        "awakened_tree": MonsterDefinition(
            base_creature_id="awakened_tree",
            variant_id="awakened_tree",
            display_name="Awakened Tree",
            combat_role="awakened_tree",
            ai_profile_id="melee_brute",
            max_hp=59,
            ac=13,
            speed=20,
            initiative_mod=-2,
            passive_perception=10,
            ability_mods=awakened_tree_ability_mods,
            size_category="huge",
            footprint=huge_footprint,
            attacks={
                "slam": WeaponProfile(
                    id="slam",
                    display_name="Slam",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=3, sides=6)],
                    damage_modifier=4,
                    damage_type="bludgeoning",
                    kind="melee",
                    reach=10,
                )
            },
            tags=("plant", "tree", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("slam", "Slam"),),
            default_melee_attack_action_id="melee_attack",
            damage_resistances=("bludgeoning", "piercing"),
            damage_vulnerabilities=("fire",),
        ),
        "lemure": MonsterDefinition(
            base_creature_id="lemure",
            variant_id="lemure",
            display_name="Lemure",
            combat_role="lemure",
            ai_profile_id="melee_brute",
            max_hp=9,
            ac=9,
            speed=20,
            initiative_mod=-3,
            passive_perception=10,
            ability_mods=lemure_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "vile_slime": WeaponProfile(
                    id="vile_slime",
                    display_name="Vile Slime",
                    attack_bonus=2,
                    ability_modifier=0,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=0,
                    damage_type="poison",
                    kind="melee",
                )
            },
            tags=("fiend", "devil", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("vile_slime", "Vile Slime"),),
            default_melee_attack_action_id="melee_attack",
            damage_resistances=("cold",),
            damage_immunities=("fire", "poison"),
        ),
        "ogre": MonsterDefinition(
            base_creature_id="ogre",
            variant_id="ogre",
            display_name="Ogre",
            combat_role="ogre",
            ai_profile_id="ranged_skirmisher",
            max_hp=68,
            ac=11,
            speed=40,
            initiative_mod=-1,
            passive_perception=8,
            ability_mods=ogre_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "greatclub": WeaponProfile(
                    id="greatclub",
                    display_name="Greatclub",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=2, sides=8)],
                    damage_modifier=4,
                    damage_type="bludgeoning",
                    kind="melee",
                ),
                "javelin": WeaponProfile(
                    id="javelin",
                    display_name="Javelin",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=4,
                    damage_type="piercing",
                    kind="melee",
                ),
                "javelin_throw": WeaponProfile(
                    id="javelin_throw",
                    display_name="Javelin",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=4,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=30, long=120),
                ),
            },
            tags=("giant", "ogre", "brute"),
            action_ids=("melee_attack", "ranged_attack"),
            attack_actions=(
                melee_attack_action("greatclub", "Greatclub"),
                ranged_attack_action("javelin_throw", "Javelin"),
            ),
            default_melee_attack_action_id="melee_attack",
            default_ranged_attack_action_id="ranged_attack",
        ),
        "black_bear": MonsterDefinition(
            base_creature_id="black_bear",
            variant_id="black_bear",
            display_name="Black Bear",
            combat_role="black_bear",
            ai_profile_id="melee_brute",
            max_hp=19,
            ac=11,
            speed=30,
            initiative_mod=1,
            passive_perception=15,
            ability_mods=black_bear_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=2,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("beast", "bear", "melee"),
            action_ids=("multiattack",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("rend",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "brown_bear": MonsterDefinition(
            base_creature_id="brown_bear",
            variant_id="brown_bear",
            display_name="Brown Bear",
            combat_role="brown_bear",
            ai_profile_id="melee_brute",
            max_hp=22,
            ac=11,
            speed=40,
            initiative_mod=1,
            passive_perception=13,
            ability_mods=brown_bear_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                ),
                "claw": WeaponProfile(
                    id="claw",
                    display_name="Claw",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=4)],
                    damage_modifier=3,
                    damage_type="slashing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="prone_on_hit", max_target_size="large")],
                ),
            },
            tags=("beast", "bear", "melee"),
            action_ids=("multiattack",),
            attack_actions=(fixed_multiattack_action("multiattack", "Multiattack", ("bite", "claw")),),
            default_melee_attack_action_id="multiattack",
        ),
        "tiger": MonsterDefinition(
            base_creature_id="tiger",
            variant_id="tiger",
            display_name="Tiger",
            combat_role="tiger",
            ai_profile_id="melee_brute",
            max_hp=30,
            ac=13,
            speed=40,
            initiative_mod=3,
            passive_perception=13,
            ability_mods=tiger_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=3,
                    damage_type="slashing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="prone_on_hit", max_target_size="large")],
                )
            },
            tags=("beast", "cat", "melee"),
            action_ids=("multiattack",),
            trait_ids=("nimble_escape",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("rend",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "saber_toothed_tiger": MonsterDefinition(
            base_creature_id="saber_toothed_tiger",
            variant_id="saber_toothed_tiger",
            display_name="Saber-Toothed Tiger",
            combat_role="saber_toothed_tiger",
            ai_profile_id="melee_brute",
            max_hp=52,
            ac=13,
            speed=40,
            initiative_mod=3,
            passive_perception=15,
            ability_mods=saber_toothed_tiger_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=4,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("beast", "cat", "melee"),
            action_ids=("multiattack",),
            trait_ids=("nimble_escape",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("rend",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "owlbear": MonsterDefinition(
            base_creature_id="owlbear",
            variant_id="owlbear",
            display_name="Owlbear",
            combat_role="owlbear",
            ai_profile_id="melee_brute",
            max_hp=59,
            ac=13,
            speed=40,
            initiative_mod=1,
            passive_perception=15,
            ability_mods=owlbear_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=7,
                    ability_modifier=5,
                    damage_dice=[DiceSpec(count=2, sides=8)],
                    damage_modifier=5,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("monstrosity", "owlbear", "melee"),
            action_ids=("multiattack",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("rend",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "ankylosaurus": MonsterDefinition(
            base_creature_id="ankylosaurus",
            variant_id="ankylosaurus",
            display_name="Ankylosaurus",
            combat_role="ankylosaurus",
            ai_profile_id="melee_brute",
            max_hp=68,
            ac=15,
            speed=30,
            initiative_mod=0,
            passive_perception=11,
            ability_mods=ankylosaurus_ability_mods,
            size_category="huge",
            footprint=huge_footprint,
            attacks={
                "tail": WeaponProfile(
                    id="tail",
                    display_name="Tail",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=1, sides=10)],
                    damage_modifier=4,
                    damage_type="bludgeoning",
                    kind="melee",
                    reach=10,
                    on_hit_effects=[OnHitEffect(kind="prone_on_hit", max_target_size="huge")],
                )
            },
            tags=("beast", "dinosaur", "melee"),
            action_ids=("multiattack",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("tail",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "archelon": MonsterDefinition(
            base_creature_id="archelon",
            variant_id="archelon",
            display_name="Archelon",
            combat_role="archelon",
            ai_profile_id="melee_brute",
            max_hp=90,
            ac=17,
            speed=20,
            initiative_mod=3,
            passive_perception=12,
            ability_mods=archelon_ability_mods,
            size_category="huge",
            footprint=huge_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=3, sides=6)],
                    damage_modifier=4,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "dinosaur", "melee"),
            action_ids=("multiattack",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("bite",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "grick": MonsterDefinition(
            base_creature_id="grick",
            variant_id="grick",
            display_name="Grick",
            combat_role="grick",
            ai_profile_id="melee_brute",
            max_hp=54,
            ac=14,
            speed=30,
            initiative_mod=2,
            passive_perception=12,
            ability_mods=grick_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "beak": WeaponProfile(
                    id="beak",
                    display_name="Beak",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=2,
                    damage_type="piercing",
                    kind="melee",
                ),
                "tentacles": WeaponProfile(
                    id="tentacles",
                    display_name="Tentacles",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=10)],
                    damage_modifier=2,
                    damage_type="slashing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="grapple_on_hit", escape_dc=12, max_target_size="medium")],
                ),
            },
            tags=("aberration", "grick", "melee"),
            action_ids=("multiattack",),
            attack_actions=(fixed_multiattack_action("multiattack", "Multiattack", ("beak", "tentacles")),),
            default_melee_attack_action_id="multiattack",
        ),
        "griffon": MonsterDefinition(
            base_creature_id="griffon",
            variant_id="griffon",
            display_name="Griffon",
            combat_role="griffon",
            ai_profile_id="melee_brute",
            max_hp=59,
            ac=12,
            speed=30,
            initiative_mod=2,
            passive_perception=15,
            ability_mods=griffon_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=4,
                    damage_type="piercing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="grapple_on_hit", escape_dc=14, max_target_size="medium")],
                )
            },
            tags=("monstrosity", "griffon", "melee"),
            action_ids=("multiattack",),
            trait_ids=("opening_flight_landing",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("rend",), 2),),
            default_melee_attack_action_id="multiattack",
            extra_resource_pools={"opening_landing_uses": 1},
        ),
        "hippopotamus": MonsterDefinition(
            base_creature_id="hippopotamus",
            variant_id="hippopotamus",
            display_name="Hippopotamus",
            combat_role="hippopotamus",
            ai_profile_id="melee_brute",
            max_hp=82,
            ac=14,
            speed=30,
            initiative_mod=-2,
            passive_perception=13,
            ability_mods=hippopotamus_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=7,
                    ability_modifier=5,
                    damage_dice=[DiceSpec(count=2, sides=10)],
                    damage_modifier=5,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "melee"),
            action_ids=("multiattack",),
            attack_actions=(repeated_choice_attack_action("multiattack", "Multiattack", ("bite",), 2),),
            default_melee_attack_action_id="multiattack",
        ),
        "berserker": MonsterDefinition(
            base_creature_id="berserker",
            variant_id="berserker",
            display_name="Berserker",
            combat_role="berserker",
            ai_profile_id="melee_brute",
            max_hp=67,
            ac=13,
            speed=30,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=berserker_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "greataxe": WeaponProfile(
                    id="greataxe",
                    display_name="Greataxe",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=12)],
                    damage_modifier=3,
                    damage_type="slashing",
                    kind="melee",
                    two_handed=True,
                    attack_ability="str",
                )
            },
            tags=("humanoid", "berserker", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("bloodied_frenzy",),
            attack_actions=(melee_attack_action("greataxe", "Greataxe"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "gnoll_warrior": MonsterDefinition(
            base_creature_id="gnoll",
            variant_id="gnoll_warrior",
            display_name="Gnoll Warrior",
            combat_role="gnoll_warrior",
            ai_profile_id="ranged_skirmisher",
            max_hp=27,
            ac=15,
            speed=30,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=gnoll_warrior_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=2,
                    damage_type="piercing",
                    kind="melee",
                ),
                "bone_bow": WeaponProfile(
                    id="bone_bow",
                    display_name="Bone Bow",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=10)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=150, long=600),
                ),
            },
            tags=("fiend", "gnoll", "ranged"),
            action_ids=("melee_attack", "ranged_attack"),
            trait_ids=("rampage",),
            attack_actions=(
                melee_attack_action("rend", "Rend"),
                ranged_attack_action("bone_bow", "Bone Bow"),
            ),
            default_melee_attack_action_id="melee_attack",
            default_ranged_attack_action_id="ranged_attack",
            extra_resource_pools={"rampage_uses": 1},
        ),
        "giant_hyena": MonsterDefinition(
            base_creature_id="giant_hyena",
            variant_id="giant_hyena",
            display_name="Giant Hyena",
            combat_role="giant_hyena",
            ai_profile_id="melee_brute",
            max_hp=45,
            ac=12,
            speed=50,
            initiative_mod=2,
            passive_perception=13,
            ability_mods=giant_hyena_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "hyena", "melee"),
            action_ids=("melee_attack",),
            trait_ids=("rampage",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
            extra_resource_pools={"rampage_uses": 1},
        ),
        "bandit_captain": MonsterDefinition(
            base_creature_id="bandit",
            variant_id="bandit_captain",
            display_name="Bandit Captain",
            combat_role="bandit_captain",
            ai_profile_id="ranged_skirmisher",
            max_hp=52,
            ac=15,
            speed=30,
            initiative_mod=3,
            passive_perception=10,
            ability_mods=bandit_captain_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "captain_scimitar": WeaponProfile(
                    id="captain_scimitar",
                    display_name="Scimitar",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=3,
                    damage_type="slashing",
                    kind="melee",
                    finesse=True,
                ),
                "pistol": WeaponProfile(
                    id="pistol",
                    display_name="Pistol",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=1, sides=10)],
                    damage_modifier=3,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=30, long=90),
                ),
            },
            tags=("humanoid", "bandit", "leader"),
            action_ids=("melee_attack", "ranged_attack", "multiattack"),
            reaction_ids=("opportunity_attack", "parry"),
            attack_actions=(
                melee_attack_action("captain_scimitar", "Scimitar"),
                ranged_attack_action("pistol", "Pistol"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("captain_scimitar", "pistol"), 2),
            ),
            default_melee_attack_action_id="multiattack",
            default_ranged_attack_action_id="multiattack",
        ),
        "goblin_boss": MonsterDefinition(
            base_creature_id="goblin",
            variant_id="goblin_boss",
            display_name="Goblin Boss",
            combat_role="goblin_boss",
            ai_profile_id="ranged_skirmisher",
            max_hp=21,
            ac=17,
            speed=30,
            initiative_mod=2,
            passive_perception=9,
            ability_mods=goblin_boss_ability_mods,
            size_category="small",
            footprint=medium_footprint,
            attacks={
                "scimitar": enemy_weapons["scimitar"],
                "shortbow": enemy_weapons["shortbow"],
            },
            tags=("goblin", "leader", "archer"),
            action_ids=("melee_attack", "ranged_attack", "multiattack"),
            reaction_ids=("opportunity_attack", "redirect_attack"),
            trait_ids=("nimble_escape",),
            attack_actions=(
                melee_attack_action("scimitar", "Scimitar"),
                ranged_attack_action("shortbow", "Shortbow"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("scimitar", "shortbow"), 2),
            ),
            default_melee_attack_action_id="multiattack",
            default_ranged_attack_action_id="multiattack",
        ),
        "bugbear_warrior": MonsterDefinition(
            base_creature_id="bugbear",
            variant_id="bugbear_warrior",
            display_name="Bugbear Warrior",
            combat_role="bugbear_warrior",
            ai_profile_id="grappling_brute",
            max_hp=33,
            ac=14,
            speed=30,
            initiative_mod=2,
            passive_perception=10,
            ability_mods=bugbear_warrior_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "grab": WeaponProfile(
                    id="grab",
                    display_name="Grab",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                    reach=10,
                    on_hit_effects=[OnHitEffect(kind="grapple_on_hit", escape_dc=12, max_target_size="medium")],
                ),
                "light_hammer": WeaponProfile(
                    id="light_hammer",
                    display_name="Light Hammer",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=3, sides=4)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="melee",
                    reach=10,
                    advantage_against_self_grappled_target=True,
                ),
                "light_hammer_throw": WeaponProfile(
                    id="light_hammer_throw",
                    display_name="Light Hammer",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=3, sides=4)],
                    damage_modifier=2,
                    damage_type="bludgeoning",
                    kind="ranged",
                    range=WeaponRange(normal=20, long=60),
                    advantage_against_self_grappled_target=True,
                ),
            },
            tags=("fey", "bugbear", "controller"),
            action_ids=("melee_attack", "ranged_attack"),
            attack_actions=(
                single_weapon_attack_action("grab_attack", "Grab", "grab"),
                single_weapon_attack_action("light_hammer_attack", "Light Hammer", "light_hammer"),
                ranged_attack_action("light_hammer_throw", "Light Hammer"),
            ),
            default_melee_attack_action_id=None,
            default_ranged_attack_action_id="ranged_attack",
        ),
        "noble": MonsterDefinition(
            base_creature_id="noble",
            variant_id="noble",
            display_name="Noble",
            combat_role="noble",
            ai_profile_id="melee_brute",
            max_hp=9,
            ac=15,
            speed=30,
            initiative_mod=1,
            passive_perception=12,
            ability_mods=noble_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "rapier": WeaponProfile(
                    id="rapier",
                    display_name="Rapier",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="melee",
                    finesse=True,
                )
            },
            tags=("humanoid", "noble", "melee"),
            action_ids=("melee_attack",),
            reaction_ids=("opportunity_attack", "parry"),
            attack_actions=(melee_attack_action("rapier", "Rapier"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "mastiff": MonsterDefinition(
            base_creature_id="mastiff",
            variant_id="mastiff",
            display_name="Mastiff",
            combat_role="mastiff",
            ai_profile_id="melee_brute",
            max_hp=5,
            ac=12,
            speed=40,
            initiative_mod=2,
            passive_perception=15,
            ability_mods=mastiff_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="prone_on_hit", max_target_size="medium")],
                )
            },
            tags=("beast", "hound", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "giant_crab": MonsterDefinition(
            base_creature_id="giant_crab",
            variant_id="giant_crab",
            display_name="Giant Crab",
            combat_role="giant_crab",
            ai_profile_id="grappling_brute",
            max_hp=13,
            ac=15,
            speed=30,
            initiative_mod=1,
            passive_perception=9,
            ability_mods=giant_crab_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "claw": WeaponProfile(
                    id="claw",
                    display_name="Claw",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=1, sides=6)],
                    damage_modifier=1,
                    damage_type="bludgeoning",
                    kind="melee",
                    on_hit_effects=[OnHitEffect(kind="grapple_on_hit", escape_dc=11, max_target_size="medium")],
                )
            },
            tags=("beast", "crab", "controller"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("claw", "Claw"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "giant_badger": MonsterDefinition(
            base_creature_id="giant_badger",
            variant_id="giant_badger",
            display_name="Giant Badger",
            combat_role="giant_badger",
            ai_profile_id="melee_brute",
            max_hp=15,
            ac=13,
            speed=30,
            initiative_mod=0,
            passive_perception=13,
            ability_mods=giant_badger_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=2, sides=4)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "badger", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
            damage_resistances=("poison",),
        ),
        "giant_lizard": MonsterDefinition(
            base_creature_id="giant_lizard",
            variant_id="giant_lizard",
            display_name="Giant Lizard",
            combat_role="giant_lizard",
            ai_profile_id="melee_brute",
            max_hp=19,
            ac=12,
            speed=40,
            initiative_mod=1,
            passive_perception=10,
            ability_mods=giant_lizard_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "bite": WeaponProfile(
                    id="bite",
                    display_name="Bite",
                    attack_bonus=4,
                    ability_modifier=2,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=2,
                    damage_type="piercing",
                    kind="melee",
                )
            },
            tags=("beast", "lizard", "melee"),
            action_ids=("melee_attack",),
            attack_actions=(melee_attack_action("bite", "Bite"),),
            default_melee_attack_action_id="melee_attack",
        ),
        "violet_fungus": MonsterDefinition(
            base_creature_id="violet_fungus",
            variant_id="violet_fungus",
            display_name="Violet Fungus",
            combat_role="violet_fungus",
            ai_profile_id="melee_brute",
            max_hp=18,
            ac=5,
            speed=5,
            initiative_mod=-5,
            passive_perception=6,
            ability_mods=violet_fungus_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "rotting_touch": WeaponProfile(
                    id="rotting_touch",
                    display_name="Rotting Touch",
                    attack_bonus=2,
                    ability_modifier=-4,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=0,
                    damage_type="necrotic",
                    kind="melee",
                    reach=10,
                )
            },
            tags=("plant", "fungus", "melee"),
            action_ids=("melee_attack", "multiattack"),
            attack_actions=(
                melee_attack_action("rotting_touch", "Rotting Touch"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("rotting_touch",), 2),
            ),
            default_melee_attack_action_id="multiattack",
        ),
        "polar_bear": MonsterDefinition(
            base_creature_id="polar_bear",
            variant_id="polar_bear",
            display_name="Polar Bear",
            combat_role="polar_bear",
            ai_profile_id="melee_brute",
            max_hp=42,
            ac=12,
            speed=40,
            initiative_mod=2,
            passive_perception=15,
            ability_mods=polar_bear_ability_mods,
            size_category="large",
            footprint=large_footprint,
            attacks={
                "rend": WeaponProfile(
                    id="rend",
                    display_name="Rend",
                    attack_bonus=7,
                    ability_modifier=5,
                    damage_dice=[DiceSpec(count=1, sides=8)],
                    damage_modifier=5,
                    damage_type="slashing",
                    kind="melee",
                )
            },
            tags=("beast", "bear", "melee"),
            action_ids=("melee_attack", "multiattack"),
            attack_actions=(
                melee_attack_action("rend", "Rend"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("rend",), 2),
            ),
            default_melee_attack_action_id="multiattack",
            damage_resistances=("cold",),
        ),
        "guard_captain": MonsterDefinition(
            base_creature_id="guard",
            variant_id="guard_captain",
            display_name="Guard Captain",
            combat_role="guard_captain",
            ai_profile_id="ranged_skirmisher",
            max_hp=75,
            ac=18,
            speed=30,
            initiative_mod=4,
            passive_perception=14,
            ability_mods=guard_captain_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "longsword": WeaponProfile(
                    id="longsword",
                    display_name="Longsword",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=2, sides=10)],
                    damage_modifier=4,
                    damage_type="slashing",
                    kind="melee",
                ),
                "javelin": WeaponProfile(
                    id="javelin",
                    display_name="Javelin",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=3, sides=6)],
                    damage_modifier=4,
                    damage_type="piercing",
                    kind="melee",
                ),
                "javelin_throw": WeaponProfile(
                    id="javelin_throw",
                    display_name="Javelin",
                    attack_bonus=6,
                    ability_modifier=4,
                    damage_dice=[DiceSpec(count=3, sides=6)],
                    damage_modifier=4,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=30, long=120),
                ),
            },
            tags=("humanoid", "guard", "leader"),
            action_ids=("melee_attack", "ranged_attack", "multiattack"),
            reaction_ids=("opportunity_attack", "parry"),
            attack_actions=(
                melee_attack_action("longsword", "Longsword"),
                ranged_attack_action("javelin_throw", "Javelin"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("longsword", "javelin_throw"), 2),
            ),
            default_melee_attack_action_id="multiattack",
            default_ranged_attack_action_id="multiattack",
        ),
        "warrior_veteran": MonsterDefinition(
            base_creature_id="warrior_veteran",
            variant_id="warrior_veteran",
            display_name="Warrior Veteran",
            combat_role="warrior_veteran",
            ai_profile_id="line_holder",
            max_hp=65,
            ac=17,
            speed=30,
            initiative_mod=3,
            passive_perception=12,
            ability_mods=warrior_veteran_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "greatsword": WeaponProfile(
                    id="greatsword",
                    display_name="Greatsword",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_dice=[DiceSpec(count=2, sides=6)],
                    damage_modifier=3,
                    damage_type="slashing",
                    kind="melee",
                    two_handed=True,
                    attack_ability="str",
                ),
                "heavy_crossbow": WeaponProfile(
                    id="heavy_crossbow",
                    display_name="Heavy Crossbow",
                    attack_bonus=3,
                    ability_modifier=1,
                    damage_dice=[DiceSpec(count=2, sides=10)],
                    damage_modifier=1,
                    damage_type="piercing",
                    kind="ranged",
                    range=WeaponRange(normal=100, long=400),
                ),
            },
            tags=("humanoid", "warrior", "veteran"),
            action_ids=("melee_attack", "ranged_attack", "multiattack"),
            reaction_ids=("opportunity_attack", "parry"),
            attack_actions=(
                melee_attack_action("greatsword", "Greatsword"),
                ranged_attack_action("heavy_crossbow", "Heavy Crossbow"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("greatsword", "heavy_crossbow"), 2),
            ),
            default_melee_attack_action_id="multiattack",
            default_ranged_attack_action_id="multiattack",
        ),
        "knight": MonsterDefinition(
            base_creature_id="knight",
            variant_id="knight",
            display_name="Knight",
            combat_role="knight",
            ai_profile_id="line_holder",
            max_hp=52,
            ac=18,
            speed=30,
            initiative_mod=0,
            passive_perception=10,
            ability_mods=knight_ability_mods,
            size_category="medium",
            footprint=medium_footprint,
            attacks={
                "greatsword": WeaponProfile(
                    id="greatsword",
                    display_name="Greatsword",
                    attack_bonus=5,
                    ability_modifier=3,
                    damage_components=[
                        WeaponDamageComponent(
                            damage_type="slashing",
                            damage_dice=[DiceSpec(count=2, sides=6)],
                            damage_modifier=3,
                        ),
                        WeaponDamageComponent(
                            damage_type="radiant",
                            damage_dice=[DiceSpec(count=1, sides=8)],
                            damage_modifier=0,
                        ),
                    ],
                    kind="melee",
                    two_handed=True,
                    attack_ability="str",
                ),
                "heavy_crossbow": WeaponProfile(
                    id="heavy_crossbow",
                    display_name="Heavy Crossbow",
                    attack_bonus=2,
                    ability_modifier=0,
                    damage_components=[
                        WeaponDamageComponent(
                            damage_type="piercing",
                            damage_dice=[DiceSpec(count=2, sides=10)],
                            damage_modifier=0,
                        ),
                        WeaponDamageComponent(
                            damage_type="radiant",
                            damage_dice=[DiceSpec(count=1, sides=8)],
                            damage_modifier=0,
                        ),
                    ],
                    kind="ranged",
                    range=WeaponRange(normal=100, long=400),
                ),
            },
            tags=("humanoid", "knight"),
            action_ids=("melee_attack", "ranged_attack", "multiattack"),
            reaction_ids=("opportunity_attack", "parry"),
            attack_actions=(
                melee_attack_action("greatsword", "Greatsword"),
                ranged_attack_action("heavy_crossbow", "Heavy Crossbow"),
                repeated_choice_attack_action("multiattack", "Multiattack", ("greatsword", "heavy_crossbow"), 2),
            ),
            default_melee_attack_action_id="multiattack",
            default_ranged_attack_action_id="multiattack",
            condition_immunities=("frightened",),
        ),
    }
)

# Backward-compatible alias used by the existing preset and test code.
ENEMY_VARIANTS = MONSTER_DEFINITIONS

# Runtime unit state still exposes combat_role, so keep a fast lookup keyed by
# that stable outward-facing field.
MONSTER_DEFINITIONS_BY_COMBAT_ROLE = {definition.combat_role: definition for definition in MONSTER_DEFINITIONS.values()}


ENEMY_PRESETS: dict[str, EnemyPresetDefinition] = {
    "goblin_screen": EnemyPresetDefinition(
        preset_id="goblin_screen",
        display_name="Goblin Screen",
        description="Five raiders screening three archers.",
        units=(
            EnemyPresetUnit("E1", "goblin_raider", GridPosition(x=14, y=6)),
            EnemyPresetUnit("E2", "goblin_raider", GridPosition(x=14, y=8)),
            EnemyPresetUnit("E3", "goblin_raider", GridPosition(x=14, y=10)),
            EnemyPresetUnit("E4", "goblin_archer", GridPosition(x=15, y=5)),
            EnemyPresetUnit("E5", "goblin_archer", GridPosition(x=15, y=8)),
            EnemyPresetUnit("E6", "goblin_archer", GridPosition(x=15, y=11)),
            EnemyPresetUnit("E7", "goblin_raider", GridPosition(x=14, y=4)),
            EnemyPresetUnit("E8", "goblin_raider", GridPosition(x=14, y=12)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "bandit_ambush": EnemyPresetDefinition(
        preset_id="bandit_ambush",
        display_name="Bandit Ambush",
        description="Two melee bandits, two archers, and a scout.",
        units=(
            EnemyPresetUnit("E1", "bandit_melee", GridPosition(x=14, y=7)),
            EnemyPresetUnit("E2", "bandit_melee", GridPosition(x=14, y=9)),
            EnemyPresetUnit("E3", "bandit_archer", GridPosition(x=15, y=5)),
            EnemyPresetUnit("E4", "bandit_archer", GridPosition(x=15, y=11)),
            EnemyPresetUnit("E5", "scout", GridPosition(x=15, y=8)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "mixed_patrol": EnemyPresetDefinition(
        preset_id="mixed_patrol",
        display_name="Mixed Patrol",
        description="Guards leading a mixed ranged patrol.",
        units=(
            EnemyPresetUnit("E1", "guard", GridPosition(x=14, y=7)),
            EnemyPresetUnit("E2", "guard", GridPosition(x=14, y=9)),
            EnemyPresetUnit("E3", "goblin_archer", GridPosition(x=15, y=5)),
            EnemyPresetUnit("E4", "goblin_archer", GridPosition(x=15, y=11)),
            EnemyPresetUnit("E5", "bandit_melee", GridPosition(x=14, y=8)),
            EnemyPresetUnit("E6", "scout", GridPosition(x=15, y=8)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "orc_push": EnemyPresetDefinition(
        preset_id="orc_push",
        display_name="Orc Push",
        description="Three orcs advancing with goblin ranged support.",
        units=(
            EnemyPresetUnit("E1", "orc_warrior", GridPosition(x=13, y=6)),
            EnemyPresetUnit("E2", "orc_warrior", GridPosition(x=13, y=8)),
            EnemyPresetUnit("E3", "orc_warrior", GridPosition(x=13, y=10)),
            EnemyPresetUnit("E4", "goblin_archer", GridPosition(x=15, y=6)),
            EnemyPresetUnit("E5", "goblin_archer", GridPosition(x=15, y=10)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "wolf_harriers": EnemyPresetDefinition(
        preset_id="wolf_harriers",
        display_name="Wolf Harriers",
        description="Wolves rushing ahead of goblin support fire.",
        units=(
            EnemyPresetUnit("E1", "wolf", GridPosition(x=13, y=6)),
            EnemyPresetUnit("E2", "wolf", GridPosition(x=13, y=8)),
            EnemyPresetUnit("E3", "wolf", GridPosition(x=13, y=10)),
            EnemyPresetUnit("E7", "wolf", GridPosition(x=13, y=12)),
            EnemyPresetUnit("E4", "goblin_archer", GridPosition(x=15, y=6)),
            EnemyPresetUnit("E5", "goblin_archer", GridPosition(x=15, y=10)),
            EnemyPresetUnit("E6", "goblin_raider", GridPosition(x=14, y=8)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "giant_toad_solo": EnemyPresetDefinition(
        preset_id="giant_toad_solo",
        display_name="Giant Toad",
        description="A single giant toad using its bite and swallow routine.",
        units=(EnemyPresetUnit("E1", "giant_toad", GridPosition(x=10, y=7)),),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "marsh_predators": EnemyPresetDefinition(
        preset_id="marsh_predators",
        display_name="Marsh Predators",
        description="Two giant toads backed by five crocodiles clustered along the marsh edge.",
        units=(
            EnemyPresetUnit("E1", "giant_toad", GridPosition(x=9, y=7)),
            EnemyPresetUnit("E2", "crocodile", GridPosition(x=1, y=1)),
            EnemyPresetUnit("E3", "crocodile", GridPosition(x=4, y=1)),
            EnemyPresetUnit("E4", "crocodile", GridPosition(x=2, y=4)),
            EnemyPresetUnit("E5", "giant_toad", GridPosition(x=9, y=10)),
            EnemyPresetUnit("E6", "crocodile", GridPosition(x=7, y=1)),
            EnemyPresetUnit("E7", "crocodile", GridPosition(x=5, y=4)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "hobgoblin_kill_box": EnemyPresetDefinition(
        preset_id="hobgoblin_kill_box",
        display_name="Hobgoblin Kill Box",
        description="A hobgoblin shield line locking lanes for archers and a goblin boss.",
        units=(
            EnemyPresetUnit("E1", "hobgoblin_warrior", GridPosition(x=10, y=5)),
            EnemyPresetUnit("E2", "hobgoblin_warrior", GridPosition(x=10, y=8)),
            EnemyPresetUnit("E3", "hobgoblin_warrior", GridPosition(x=10, y=11)),
            EnemyPresetUnit("E4", "hobgoblin_warrior", GridPosition(x=12, y=8)),
            EnemyPresetUnit("E5", "hobgoblin_archer", GridPosition(x=14, y=5)),
            EnemyPresetUnit("E6", "hobgoblin_archer", GridPosition(x=14, y=8)),
            EnemyPresetUnit("E7", "hobgoblin_archer", GridPosition(x=14, y=11)),
            EnemyPresetUnit("E8", "goblin_boss", GridPosition(x=13, y=8)),
            EnemyPresetUnit("E9", "hobgoblin_warrior", GridPosition(x=12, y=5)),
            EnemyPresetUnit("E10", "hobgoblin_warrior", GridPosition(x=12, y=11)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "predator_rampage": EnemyPresetDefinition(
        preset_id="predator_rampage",
        display_name="Predator Rampage",
        description="Dire wolves and worgs crash in ahead of gnoll bows and a giant hyena finisher.",
        units=(
            EnemyPresetUnit("E1", "dire_wolf", GridPosition(x=10, y=5)),
            EnemyPresetUnit("E2", "dire_wolf", GridPosition(x=10, y=10)),
            EnemyPresetUnit("E3", "giant_hyena", GridPosition(x=12, y=7)),
            EnemyPresetUnit("E4", "gnoll_warrior", GridPosition(x=14, y=6)),
            EnemyPresetUnit("E5", "gnoll_warrior", GridPosition(x=14, y=10)),
            EnemyPresetUnit("E6", "worg", GridPosition(x=12, y=10)),
            EnemyPresetUnit("E7", "worg", GridPosition(x=12, y=2)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "bugbear_dragnet": EnemyPresetDefinition(
        preset_id="bugbear_dragnet",
        display_name="Bugbear Dragnet",
        description="Bugbears pin the front while a goblin boss and archers punish the approach lanes.",
        units=(
            EnemyPresetUnit("E1", "bugbear_warrior", GridPosition(x=10, y=6)),
            EnemyPresetUnit("E2", "bugbear_warrior", GridPosition(x=10, y=10)),
            EnemyPresetUnit("E3", "goblin_boss", GridPosition(x=13, y=8)),
            EnemyPresetUnit("E4", "goblin_archer", GridPosition(x=14, y=8)),
            EnemyPresetUnit("E5", "goblin_minion", GridPosition(x=14, y=6)),
            EnemyPresetUnit("E6", "hobgoblin_archer", GridPosition(x=15, y=5)),
            EnemyPresetUnit("E7", "hobgoblin_archer", GridPosition(x=15, y=11)),
            EnemyPresetUnit("E8", "bugbear_warrior", GridPosition(x=12, y=6)),
            EnemyPresetUnit("E9", "bugbear_warrior", GridPosition(x=12, y=10)),
            EnemyPresetUnit("E10", "goblin_minion", GridPosition(x=14, y=10)),
            EnemyPresetUnit("E11", "goblin_minion", GridPosition(x=13, y=4)),
            EnemyPresetUnit("E12", "goblin_minion", GridPosition(x=13, y=12)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "deadwatch_phalanx": EnemyPresetDefinition(
        preset_id="deadwatch_phalanx",
        display_name="Deadwatch Phalanx",
        description="Animated armor and undead archers grind attackers down behind a rigid phalanx.",
        units=(
            EnemyPresetUnit("E1", "animated_armor", GridPosition(x=10, y=6)),
            EnemyPresetUnit("E2", "animated_armor", GridPosition(x=10, y=10)),
            EnemyPresetUnit("E3", "zombie", GridPosition(x=12, y=5)),
            EnemyPresetUnit("E4", "zombie", GridPosition(x=12, y=11)),
            EnemyPresetUnit("E5", "skeleton", GridPosition(x=15, y=4)),
            EnemyPresetUnit("E6", "skeleton", GridPosition(x=15, y=7)),
            EnemyPresetUnit("E7", "skeleton", GridPosition(x=15, y=10)),
            EnemyPresetUnit("E8", "skeleton", GridPosition(x=15, y=13)),
            EnemyPresetUnit("E9", "zombie", GridPosition(x=12, y=8)),
            EnemyPresetUnit("E10", "zombie", GridPosition(x=13, y=6)),
            EnemyPresetUnit("E11", "zombie", GridPosition(x=13, y=10)),
            EnemyPresetUnit("E12", "zombie", GridPosition(x=13, y=4)),
            EnemyPresetUnit("E13", "zombie", GridPosition(x=13, y=8)),
            EnemyPresetUnit("E14", "zombie", GridPosition(x=13, y=12)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
    "captains_crossfire": EnemyPresetDefinition(
        preset_id="captains_crossfire",
        display_name="Captain's Crossfire",
        description="A veteran captain anchors a layered crossfire with guard screens and parrying nobles.",
        units=(
            EnemyPresetUnit("E1", "guard", GridPosition(x=10, y=7)),
            EnemyPresetUnit("E2", "guard", GridPosition(x=10, y=9)),
            EnemyPresetUnit("E3", "bandit_captain", GridPosition(x=11, y=8)),
            EnemyPresetUnit("E4", "noble", GridPosition(x=12, y=6)),
            EnemyPresetUnit("E5", "noble", GridPosition(x=12, y=10)),
            EnemyPresetUnit("E6", "scout", GridPosition(x=14, y=4)),
            EnemyPresetUnit("E7", "scout", GridPosition(x=14, y=12)),
        ),
        terrain_features=(build_rock_terrain_feature(),),
    ),
}

BENCHMARK_MONSTER_VARIANT_IDS: tuple[str, ...] = (
    "hobgoblin_warrior",
    "hobgoblin_archer",
    "tough",
    "axe_beak",
    "draft_horse",
    "riding_horse",
    "cultist",
    "warrior_infantry",
    "camel",
    "mule",
    "pony",
    "commoner",
    "hyena",
    "jackal",
    "goblin_minion",
    "skeleton",
    "zombie",
    "ogre_zombie",
    "giant_rat",
    "giant_fire_beetle",
    "giant_weasel",
    "worg",
    "animated_armor",
    "dire_wolf",
    "awakened_shrub",
    "awakened_tree",
    "lemure",
    "ogre",
    "black_bear",
    "brown_bear",
    "tiger",
    "saber_toothed_tiger",
    "owlbear",
    "ankylosaurus",
    "archelon",
    "grick",
    "griffon",
    "hippopotamus",
    "berserker",
    "gnoll_warrior",
    "giant_hyena",
    "bandit_captain",
    "goblin_boss",
    "bugbear_warrior",
    "noble",
    "mastiff",
    "giant_crab",
    "giant_badger",
    "giant_lizard",
    "violet_fungus",
    "polar_bear",
    "guard_captain",
    "warrior_veteran",
    "knight",
)


def get_benchmark_monster_count(variant_id: str) -> int:
    return max(1, min(15, round(100 / MONSTER_DEFINITIONS[variant_id].max_hp)))


BENCHMARK_MONSTER_COUNTS: dict[str, int] = {
    variant_id: get_benchmark_monster_count(variant_id) for variant_id in BENCHMARK_MONSTER_VARIANT_IDS
}
BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT: dict[str, str] = {
    variant_id: f"{variant_id}_benchmark" for variant_id in BENCHMARK_MONSTER_COUNTS
}
BENCHMARK_ENEMY_PRESET_IDS: tuple[str, ...] = tuple(BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT.values())
_BENCHMARK_STANDARD_COLUMNS = (15, 14, 13, 12, 11, 10, 9)
_BENCHMARK_STANDARD_ROWS = tuple(range(1, 16))
_BENCHMARK_LARGE_COLUMNS = (14, 12, 10, 8)
_BENCHMARK_LARGE_ROWS = (1, 3, 5, 7, 9, 11, 13)
_BENCHMARK_HUGE_COLUMNS = (13, 10, 7)
_BENCHMARK_HUGE_ROWS = (1, 4, 7, 10, 13)


def _iter_benchmark_positions(footprint: Footprint) -> list[GridPosition]:
    if footprint.width == 3 and footprint.height == 3:
        return [GridPosition(x=column, y=row) for column in _BENCHMARK_HUGE_COLUMNS for row in _BENCHMARK_HUGE_ROWS]
    if footprint.width == 2 and footprint.height == 2:
        return [
            GridPosition(x=column, y=row) for column in _BENCHMARK_LARGE_COLUMNS for row in _BENCHMARK_LARGE_ROWS
        ]
    return [
        GridPosition(x=column, y=row) for column in _BENCHMARK_STANDARD_COLUMNS for row in _BENCHMARK_STANDARD_ROWS
    ]


def _build_benchmark_enemy_units(variant_id: str, count: int) -> tuple[EnemyPresetUnit, ...]:
    definition = MONSTER_DEFINITIONS[variant_id]
    positions = _iter_benchmark_positions(definition.footprint)
    if count > len(positions):
        raise ValueError(f"Not enough benchmark positions are available for {variant_id} ({count} requested).")
    return tuple(
        EnemyPresetUnit(unit_id=f"E{index}", variant_id=variant_id, position=positions[index - 1])
        for index in range(1, count + 1)
    )


def build_benchmark_enemy_preset(variant_id: str, count: int) -> EnemyPresetDefinition:
    definition = MONSTER_DEFINITIONS[variant_id]
    return EnemyPresetDefinition(
        preset_id=BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT[variant_id],
        display_name=f"{definition.display_name} Benchmark",
        description=f"Test-only benchmark preset for {definition.display_name} at roughly 100 total HP.",
        units=_build_benchmark_enemy_units(variant_id, count),
    )


ENEMY_PRESETS.update(
    {
        preset_id: build_benchmark_enemy_preset(variant_id, count)
        for variant_id, count in BENCHMARK_MONSTER_COUNTS.items()
        for preset_id in (BENCHMARK_ENEMY_PRESET_ID_BY_VARIANT[variant_id],)
    }
)

ACTIVE_ENEMY_PRESET_IDS: tuple[str, ...] = (
    "goblin_screen",
    "bandit_ambush",
    "mixed_patrol",
    "orc_push",
    "wolf_harriers",
    "marsh_predators",
    "hobgoblin_kill_box",
    "predator_rampage",
    "bugbear_dragnet",
    "deadwatch_phalanx",
    "captains_crossfire",
)

DEFAULT_ENEMY_PRESET_ID = "goblin_screen"


def clone_attacks(source: dict[str, WeaponProfile]) -> dict[str, WeaponProfile]:
    return deepcopy(source)


def get_enemy_variant(variant_id: str) -> MonsterDefinition:
    try:
        return MONSTER_DEFINITIONS[variant_id]
    except KeyError as error:
        raise ValueError(f"Unknown enemy variant '{variant_id}'.") from error


def get_enemy_preset(preset_id: str) -> EnemyPresetDefinition:
    try:
        return ENEMY_PRESETS[preset_id]
    except KeyError as error:
        raise ValueError(f"Unknown enemy preset '{preset_id}'.") from error


def get_active_enemy_presets() -> list[EnemyPresetDefinition]:
    return [ENEMY_PRESETS[preset_id] for preset_id in ACTIVE_ENEMY_PRESET_IDS]


def get_monster_definition_for_unit(unit: UnitState) -> MonsterDefinition:
    try:
        return MONSTER_DEFINITIONS_BY_COMBAT_ROLE[unit.combat_role]
    except KeyError as error:
        raise ValueError(f"No monster definition is registered for combat role '{unit.combat_role}'.") from error


def get_unit_action_ids(unit: UnitState) -> tuple[str, ...]:
    definition = get_monster_definition_for_unit(unit)
    granted_action_ids = set(definition.action_ids)
    for trait_id in definition.trait_ids:
        granted_action_ids.update(get_monster_trait(trait_id).granted_action_ids)
    return tuple(sorted(granted_action_ids))


def get_unit_bonus_action_ids(unit: UnitState) -> tuple[str, ...]:
    definition = get_monster_definition_for_unit(unit)
    granted_bonus_action_ids = set(definition.bonus_action_ids)
    for trait_id in definition.trait_ids:
        granted_bonus_action_ids.update(get_monster_trait(trait_id).granted_bonus_action_ids)
    return tuple(sorted(granted_bonus_action_ids))


def get_unit_reaction_ids(unit: UnitState) -> tuple[str, ...]:
    definition = get_monster_definition_for_unit(unit)
    granted_reaction_ids = set(definition.reaction_ids)
    for trait_id in definition.trait_ids:
        granted_reaction_ids.update(get_monster_trait(trait_id).granted_reaction_ids)
    return tuple(sorted(granted_reaction_ids))


def get_attack_action_definition_for_unit(
    unit: UnitState,
    *,
    preferred_weapon_id: AttackId | None = None,
    action_id: str | None = None,
) -> AttackActionDefinition:
    """Return the ordered attack sequence this unit uses for the chosen action.

    Fighters and monsters share the same execution model, but their content is
    defined differently. Fighters use the generic Attack action, while monsters
    point at explicit stat-block actions such as Multiattack.
    """

    if unit.faction == "fighters":
        player_action = build_player_attack_action(unit)
        if action_id and action_id != player_action.action_id:
            raise ValueError(f"Unsupported player attack action '{action_id}'.")
        return player_action

    definition = get_monster_definition_for_unit(unit)
    action_map = {attack_action.action_id: attack_action for attack_action in definition.attack_actions}

    if action_id:
        try:
            return action_map[action_id]
        except KeyError as error:
            raise ValueError(f"{unit.id} cannot use attack action '{action_id}'.") from error

    if preferred_weapon_id:
        preferred_weapon = unit.attacks.get(preferred_weapon_id)
        if preferred_weapon and preferred_weapon.kind == "melee" and definition.default_melee_attack_action_id:
            return action_map[definition.default_melee_attack_action_id]
        if preferred_weapon and preferred_weapon.kind == "ranged" and definition.default_ranged_attack_action_id:
            return action_map[definition.default_ranged_attack_action_id]

        for attack_action in definition.attack_actions:
            if any(preferred_weapon_id in step.allowed_weapon_ids for step in attack_action.steps):
                return attack_action

    if definition.attack_actions:
        return definition.attack_actions[0]

    raise ValueError(f"{unit.id} has no configured attack actions.")


def unit_has_trait(unit: UnitState, trait_id: str) -> bool:
    definition = get_monster_definition_for_unit(unit)
    return trait_id in definition.trait_ids


def unit_has_creature_tag(unit: UnitState, tag: str) -> bool:
    return tag in unit.creature_tags


def unit_is_undead(unit: UnitState) -> bool:
    return unit_has_creature_tag(unit, "undead")


def unit_has_action(unit: UnitState, action_id: str) -> bool:
    return action_id in get_unit_action_ids(unit)


def unit_has_bonus_action(unit: UnitState, action_id: str) -> bool:
    return action_id in get_unit_bonus_action_ids(unit)


def unit_has_reaction(unit: UnitState, action_id: str) -> bool:
    return action_id in get_unit_reaction_ids(unit)


def create_enemy(unit_id: str, variant_id: str) -> UnitState:
    variant = get_enemy_variant(variant_id)
    return UnitState(
        id=unit_id,
        faction="goblins",
        combat_role=variant.combat_role,
        template_name=variant.display_name,
        role_tags=list(variant.role_tags),
        current_hp=variant.max_hp,
        max_hp=variant.max_hp,
        temporary_hit_points=0,
        ac=variant.ac,
        speed=variant.speed,
        effective_speed=variant.speed,
        initiative_mod=variant.initiative_mod,
        initiative_score=0,
        ability_mods=deepcopy(variant.ability_mods),
        passive_perception=variant.passive_perception,
        size_category=variant.size_category,
        footprint=deepcopy(variant.footprint),
        conditions=ConditionState(unconscious=False, prone=False, dead=False),
        death_save_successes=0,
        death_save_failures=0,
        stable=False,
        resources=ResourceState(
            second_wind_uses=0,
            javelins=0,
            rage_uses=0,
            handaxes=0,
            action_surge_uses=0,
            superiority_dice=0,
            focus_points=0,
            uncanny_metabolism_uses=0,
            spell_slots_level_1=0,
        ),
        temporary_effects=[],
        reaction_available=True,
        attacks=clone_attacks(variant.attacks),
        medicine_modifier=variant.medicine_modifier,
        damage_resistances=variant.damage_resistances,
        damage_immunities=variant.damage_immunities,
        damage_vulnerabilities=variant.damage_vulnerabilities,
        condition_immunities=variant.condition_immunities,
        creature_tags=variant.creature_tags,
        resource_pools=dict(variant.extra_resource_pools),
    )
