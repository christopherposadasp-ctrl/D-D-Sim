from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DamageComponentExpectation:
    damage_type: str
    damage_dice: tuple[tuple[int, int], ...] = ()
    damage_modifier: int = 0


@dataclass(frozen=True)
class AttackExpectation:
    kind: str
    attack_bonus: int
    ability_modifier: int
    damage_modifier: int
    damage_type: str | None
    reach: int | None = None
    range: tuple[int, int] | None = None
    damage_dice: tuple[tuple[int, int], ...] = ()
    damage_components: tuple[DamageComponentExpectation, ...] = ()
    advantage_damage_components: tuple[DamageComponentExpectation, ...] = ()


@dataclass(frozen=True)
class MonsterExpectation:
    ai_profile_id: str
    max_hp: int
    ac: int
    speed: int
    initiative_mod: int
    passive_perception: int
    size_category: str
    footprint: tuple[int, int]
    ability_mods: dict[str, int]
    trait_ids: tuple[str, ...]
    attacks: dict[str, AttackExpectation]
    opening_weapon_id: str
    melee_fallback_weapon_id: str
    special_mechanics: tuple[str, ...]
    benchmark_preset_id: str
    benchmark_count: int


MONSTER_EXPECTATIONS: dict[str, MonsterExpectation] = {
    "hobgoblin_warrior": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=11,
        ac=18,
        speed=30,
        initiative_mod=3,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 1, "dex": 1, "con": 1, "int": 0, "wis": 0, "cha": -1},
        trait_ids=("pack_tactics",),
        attacks={
            "longsword": AttackExpectation(
                kind="melee",
                attack_bonus=3,
                ability_modifier=1,
                damage_modifier=1,
                damage_type="slashing",
                damage_dice=((2, 10),),
            )
        },
        opening_weapon_id="longsword",
        melee_fallback_weapon_id="longsword",
        special_mechanics=("pack_tactics",),
        benchmark_preset_id="hobgoblin_warrior_benchmark",
        benchmark_count=9,
    ),
    "hobgoblin_archer": MonsterExpectation(
        ai_profile_id="ranged_skirmisher",
        max_hp=11,
        ac=18,
        speed=30,
        initiative_mod=3,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 1, "dex": 1, "con": 1, "int": 0, "wis": 0, "cha": -1},
        trait_ids=("pack_tactics",),
        attacks={
            "longsword": AttackExpectation(
                kind="melee",
                attack_bonus=3,
                ability_modifier=1,
                damage_modifier=1,
                damage_type="slashing",
                damage_dice=((2, 10),),
            ),
            "longbow": AttackExpectation(
                kind="ranged",
                attack_bonus=3,
                ability_modifier=1,
                damage_modifier=1,
                damage_type="piercing",
                range=(150, 600),
                damage_dice=((1, 8),),
                advantage_damage_components=(DamageComponentExpectation("poison", ((3, 4),)),),
            ),
        },
        opening_weapon_id="longbow",
        melee_fallback_weapon_id="longsword",
        special_mechanics=("pack_tactics", "advantage_poison"),
        benchmark_preset_id="hobgoblin_archer_benchmark",
        benchmark_count=9,
    ),
    "tough": MonsterExpectation(
        ai_profile_id="ranged_skirmisher",
        max_hp=32,
        ac=12,
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 2, "dex": 1, "con": 2, "int": 0, "wis": 0, "cha": 0},
        trait_ids=("pack_tactics",),
        attacks={
            "mace": AttackExpectation(
                kind="melee",
                attack_bonus=4,
                ability_modifier=2,
                damage_modifier=2,
                damage_type="bludgeoning",
                damage_dice=((1, 6),),
            ),
            "heavy_crossbow": AttackExpectation(
                kind="ranged",
                attack_bonus=3,
                ability_modifier=1,
                damage_modifier=1,
                damage_type="piercing",
                range=(100, 400),
                damage_dice=((1, 10),),
            ),
        },
        opening_weapon_id="heavy_crossbow",
        melee_fallback_weapon_id="mace",
        special_mechanics=("pack_tactics",),
        benchmark_preset_id="tough_benchmark",
        benchmark_count=3,
    ),
    "axe_beak": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=19,
        ac=11,
        speed=50,
        initiative_mod=1,
        passive_perception=10,
        size_category="large",
        footprint=(2, 2),
        ability_mods={"str": 2, "dex": 1, "con": 1, "int": -4, "wis": 0, "cha": -3},
        trait_ids=(),
        attacks={
            "beak": AttackExpectation(
                kind="melee",
                attack_bonus=4,
                ability_modifier=2,
                damage_modifier=2,
                damage_type="slashing",
                damage_dice=((1, 8),),
            )
        },
        opening_weapon_id="beak",
        melee_fallback_weapon_id="beak",
        special_mechanics=(),
        benchmark_preset_id="axe_beak_benchmark",
        benchmark_count=5,
    ),
    "draft_horse": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=15,
        ac=10,
        speed=40,
        initiative_mod=0,
        passive_perception=10,
        size_category="large",
        footprint=(2, 2),
        ability_mods={"str": 4, "dex": 0, "con": 2, "int": -4, "wis": 0, "cha": -2},
        trait_ids=(),
        attacks={
            "hooves": AttackExpectation(
                kind="melee",
                attack_bonus=6,
                ability_modifier=4,
                damage_modifier=4,
                damage_type="bludgeoning",
                damage_dice=((1, 4),),
            )
        },
        opening_weapon_id="hooves",
        melee_fallback_weapon_id="hooves",
        special_mechanics=(),
        benchmark_preset_id="draft_horse_benchmark",
        benchmark_count=7,
    ),
    "riding_horse": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=13,
        ac=11,
        speed=60,
        initiative_mod=1,
        passive_perception=10,
        size_category="large",
        footprint=(2, 2),
        ability_mods={"str": 3, "dex": 1, "con": 1, "int": -4, "wis": 0, "cha": -2},
        trait_ids=(),
        attacks={
            "hooves": AttackExpectation(
                kind="melee",
                attack_bonus=5,
                ability_modifier=3,
                damage_modifier=3,
                damage_type="bludgeoning",
                damage_dice=((1, 8),),
            )
        },
        opening_weapon_id="hooves",
        melee_fallback_weapon_id="hooves",
        special_mechanics=(),
        benchmark_preset_id="riding_horse_benchmark",
        benchmark_count=8,
    ),
    "cultist": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=9,
        ac=12,
        speed=30,
        initiative_mod=1,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 0, "dex": 1, "con": 0, "int": 0, "wis": 1, "cha": 0},
        trait_ids=(),
        attacks={
            "ritual_sickle": AttackExpectation(
                kind="melee",
                attack_bonus=3,
                ability_modifier=1,
                damage_modifier=0,
                damage_type=None,
                damage_components=(
                    DamageComponentExpectation("slashing", ((1, 4),), 1),
                    DamageComponentExpectation("necrotic", (), 1),
                ),
            )
        },
        opening_weapon_id="ritual_sickle",
        melee_fallback_weapon_id="ritual_sickle",
        special_mechanics=("split_damage",),
        benchmark_preset_id="cultist_benchmark",
        benchmark_count=11,
    ),
    "warrior_infantry": MonsterExpectation(
        ai_profile_id="line_holder",
        max_hp=9,
        ac=13,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 1, "dex": 0, "con": 0, "int": -1, "wis": 0, "cha": -1},
        trait_ids=("pack_tactics",),
        attacks={
            "spear": AttackExpectation(
                kind="melee",
                attack_bonus=3,
                ability_modifier=1,
                damage_modifier=1,
                damage_type="piercing",
                damage_dice=((1, 6),),
            )
        },
        opening_weapon_id="spear",
        melee_fallback_weapon_id="spear",
        special_mechanics=("pack_tactics",),
        benchmark_preset_id="warrior_infantry_benchmark",
        benchmark_count=11,
    ),
    "camel": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=17,
        ac=10,
        speed=50,
        initiative_mod=-1,
        passive_perception=10,
        size_category="large",
        footprint=(2, 2),
        ability_mods={"str": 2, "dex": -1, "con": 3, "int": -4, "wis": 0, "cha": -3},
        trait_ids=(),
        attacks={
            "bite": AttackExpectation(
                kind="melee",
                attack_bonus=4,
                ability_modifier=2,
                damage_modifier=2,
                damage_type="bludgeoning",
                damage_dice=((1, 4),),
            )
        },
        opening_weapon_id="bite",
        melee_fallback_weapon_id="bite",
        special_mechanics=(),
        benchmark_preset_id="camel_benchmark",
        benchmark_count=6,
    ),
    "mule": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=11,
        ac=10,
        speed=40,
        initiative_mod=0,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 2, "dex": 0, "con": 1, "int": -4, "wis": 0, "cha": -3},
        trait_ids=(),
        attacks={
            "hooves": AttackExpectation(
                kind="melee",
                attack_bonus=4,
                ability_modifier=2,
                damage_modifier=2,
                damage_type="bludgeoning",
                damage_dice=((1, 4),),
            )
        },
        opening_weapon_id="hooves",
        melee_fallback_weapon_id="hooves",
        special_mechanics=(),
        benchmark_preset_id="mule_benchmark",
        benchmark_count=9,
    ),
    "pony": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=11,
        ac=10,
        speed=40,
        initiative_mod=0,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 2, "dex": 0, "con": 1, "int": -4, "wis": 0, "cha": -2},
        trait_ids=(),
        attacks={
            "hooves": AttackExpectation(
                kind="melee",
                attack_bonus=4,
                ability_modifier=2,
                damage_modifier=2,
                damage_type="bludgeoning",
                damage_dice=((1, 4),),
            )
        },
        opening_weapon_id="hooves",
        melee_fallback_weapon_id="hooves",
        special_mechanics=(),
        benchmark_preset_id="pony_benchmark",
        benchmark_count=9,
    ),
    "commoner": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=4,
        ac=10,
        speed=30,
        initiative_mod=0,
        passive_perception=10,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0},
        trait_ids=(),
        attacks={
            "club": AttackExpectation(
                kind="melee",
                attack_bonus=2,
                ability_modifier=0,
                damage_modifier=0,
                damage_type="bludgeoning",
                damage_dice=((1, 4),),
            )
        },
        opening_weapon_id="club",
        melee_fallback_weapon_id="club",
        special_mechanics=(),
        benchmark_preset_id="commoner_benchmark",
        benchmark_count=15,
    ),
    "hyena": MonsterExpectation(
        ai_profile_id="pack_hunter",
        max_hp=5,
        ac=11,
        speed=50,
        initiative_mod=1,
        passive_perception=13,
        size_category="medium",
        footprint=(1, 1),
        ability_mods={"str": 0, "dex": 1, "con": 1, "int": -4, "wis": 1, "cha": -3},
        trait_ids=("pack_tactics",),
        attacks={
            "bite": AttackExpectation(
                kind="melee",
                attack_bonus=2,
                ability_modifier=0,
                damage_modifier=0,
                damage_type="piercing",
                damage_dice=((1, 6),),
            )
        },
        opening_weapon_id="bite",
        melee_fallback_weapon_id="bite",
        special_mechanics=("pack_tactics",),
        benchmark_preset_id="hyena_benchmark",
        benchmark_count=15,
    ),
    "jackal": MonsterExpectation(
        ai_profile_id="melee_brute",
        max_hp=3,
        ac=12,
        speed=40,
        initiative_mod=2,
        passive_perception=15,
        size_category="small",
        footprint=(1, 1),
        ability_mods={"str": -1, "dex": 2, "con": 0, "int": -4, "wis": 1, "cha": -2},
        trait_ids=(),
        attacks={
            "bite": AttackExpectation(
                kind="melee",
                attack_bonus=1,
                ability_modifier=-1,
                damage_modifier=-1,
                damage_type="piercing",
                damage_dice=((1, 4),),
            )
        },
        opening_weapon_id="bite",
        melee_fallback_weapon_id="bite",
        special_mechanics=(),
        benchmark_preset_id="jackal_benchmark",
        benchmark_count=15,
    ),
}

REMAINING_MONSTER_IDS: tuple[str, ...] = tuple(MONSTER_EXPECTATIONS)
RANGED_SKIRMISHER_MONSTER_IDS: tuple[str, ...] = tuple(
    monster_id
    for monster_id, expectation in MONSTER_EXPECTATIONS.items()
    if expectation.ai_profile_id == "ranged_skirmisher"
)
PACK_TACTICS_MONSTER_IDS: tuple[str, ...] = tuple(
    monster_id
    for monster_id, expectation in MONSTER_EXPECTATIONS.items()
    if "pack_tactics" in expectation.special_mechanics
)
LARGE_MONSTER_IDS: tuple[str, ...] = tuple(
    monster_id for monster_id, expectation in MONSTER_EXPECTATIONS.items() if expectation.footprint == (2, 2)
)
MELEE_ONLY_MONSTER_IDS: tuple[str, ...] = tuple(
    monster_id
    for monster_id, expectation in MONSTER_EXPECTATIONS.items()
    if all(attack.kind == "melee" for attack in expectation.attacks.values())
)
