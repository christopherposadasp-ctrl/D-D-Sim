from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassProgressionDefinition:
    """Per-level granted features and persistent resource pools."""

    class_id: str
    level: int
    feature_ids: tuple[str, ...]
    resource_pools: dict[str, int]
    attack_count: int = 1
    feature_scalars: dict[str, int] | None = None


CLASS_PROGRESSIONS: dict[tuple[str, int], ClassProgressionDefinition] = {
    (
        "fighter",
        1,
    ): ClassProgressionDefinition(
        class_id="fighter",
        level=1,
        feature_ids=("second_wind",),
        resource_pools={"second_wind": 2},
        attack_count=1,
    ),
    (
        "fighter",
        2,
    ): ClassProgressionDefinition(
        class_id="fighter",
        level=2,
        feature_ids=("second_wind", "action_surge"),
        resource_pools={"second_wind": 2, "action_surge": 1},
        attack_count=1,
    ),
    (
        "fighter",
        3,
    ): ClassProgressionDefinition(
        class_id="fighter",
        level=3,
        feature_ids=("second_wind", "action_surge", "combat_superiority", "student_of_war"),
        resource_pools={"second_wind": 2, "action_surge": 1, "superiority_dice": 4},
        attack_count=1,
        feature_scalars={"superiority_die_sides": 8},
    ),
    (
        "fighter",
        4,
    ): ClassProgressionDefinition(
        class_id="fighter",
        level=4,
        feature_ids=("second_wind", "action_surge", "combat_superiority", "student_of_war", "great_weapon_master"),
        resource_pools={"second_wind": 2, "action_surge": 1, "superiority_dice": 4},
        attack_count=1,
        feature_scalars={"superiority_die_sides": 8},
    ),
    (
        "fighter",
        5,
    ): ClassProgressionDefinition(
        class_id="fighter",
        level=5,
        feature_ids=(
            "second_wind",
            "action_surge",
            "combat_superiority",
            "student_of_war",
            "great_weapon_master",
            "extra_attack",
            "tactical_shift",
        ),
        resource_pools={"second_wind": 3, "action_surge": 1, "superiority_dice": 4},
        attack_count=2,
        feature_scalars={"superiority_die_sides": 8},
    ),
    (
        "rogue",
        1,
    ): ClassProgressionDefinition(
        class_id="rogue",
        level=1,
        feature_ids=("sneak_attack", "expertise_stealth"),
        resource_pools={},
        attack_count=1,
        feature_scalars={"sneak_attack_d6": 1},
    ),
    (
        "rogue",
        2,
    ): ClassProgressionDefinition(
        class_id="rogue",
        level=2,
        feature_ids=("sneak_attack", "expertise_stealth", "cunning_action"),
        resource_pools={},
        attack_count=1,
        feature_scalars={"sneak_attack_d6": 1},
    ),
    (
        "rogue",
        3,
    ): ClassProgressionDefinition(
        class_id="rogue",
        level=3,
        feature_ids=(
            "sneak_attack",
            "expertise_stealth",
            "cunning_action",
            "steady_aim",
            "assassinate",
            "assassin_tools",
        ),
        resource_pools={},
        attack_count=1,
        feature_scalars={"sneak_attack_d6": 2},
    ),
    (
        "rogue",
        4,
    ): ClassProgressionDefinition(
        class_id="rogue",
        level=4,
        feature_ids=(
            "sneak_attack",
            "expertise_stealth",
            "cunning_action",
            "steady_aim",
            "assassinate",
            "assassin_tools",
            "sharpshooter",
        ),
        resource_pools={},
        attack_count=1,
        feature_scalars={"sneak_attack_d6": 2},
    ),
    (
        "barbarian",
        1,
    ): ClassProgressionDefinition(
        class_id="barbarian",
        level=1,
        feature_ids=("rage", "unarmored_defense"),
        resource_pools={"rage": 2, "handaxes": 4},
        attack_count=1,
        feature_scalars={"rage_damage_bonus": 2},
    ),
    (
        "barbarian",
        2,
    ): ClassProgressionDefinition(
        class_id="barbarian",
        level=2,
        feature_ids=("rage", "unarmored_defense", "reckless_attack", "danger_sense"),
        resource_pools={"rage": 2, "handaxes": 4},
        attack_count=1,
        feature_scalars={"rage_damage_bonus": 2},
    ),
    (
        "monk",
        1,
    ): ClassProgressionDefinition(
        class_id="monk",
        level=1,
        feature_ids=("martial_arts", "unarmored_defense"),
        resource_pools={},
        attack_count=1,
        feature_scalars={"martial_arts_die_sides": 6},
    ),
    (
        "monk",
        2,
    ): ClassProgressionDefinition(
        class_id="monk",
        level=2,
        feature_ids=(
            "martial_arts",
            "unarmored_defense",
            "monks_focus",
            "unarmored_movement",
            "uncanny_metabolism",
        ),
        resource_pools={"focus_points": 2, "uncanny_metabolism": 1},
        attack_count=1,
        feature_scalars={"martial_arts_die_sides": 6},
    ),
    (
        "wizard",
        1,
    ): ClassProgressionDefinition(
        class_id="wizard",
        level=1,
        feature_ids=("spellcasting", "ritual_adept", "arcane_recovery"),
        resource_pools={"spell_slots_level_1": 2},
        attack_count=1,
        feature_scalars={
            "cantrips_known": 3,
            "spellbook_spells": 6,
            "prepared_spells": 4,
        },
    ),
}


def get_class_progression(class_id: str, level: int) -> ClassProgressionDefinition:
    try:
        return CLASS_PROGRESSIONS[(class_id, level)]
    except KeyError as error:
        raise ValueError(f"Unsupported class progression '{class_id}' level {level}.") from error


def get_progression_scalar(class_id: str, level: int, scalar_id: str, default: int = 0) -> int:
    progression = get_class_progression(class_id, level)
    if not progression.feature_scalars:
        return default
    return progression.feature_scalars.get(scalar_id, default)


def get_proficiency_bonus(level: int) -> int:
    if level <= 0:
        raise ValueError(f"Level must be positive to resolve proficiency bonus, got {level}.")
    return 2 + ((level - 1) // 4)


def get_monk_focus_points_max(level: int) -> int:
    return get_class_progression("monk", level).resource_pools.get("focus_points", 0)


def get_monk_martial_arts_die_sides(level: int, default: int = 6) -> int:
    return get_progression_scalar("monk", level, "martial_arts_die_sides", default)
