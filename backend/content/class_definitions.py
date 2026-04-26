from __future__ import annotations

from dataclasses import dataclass

from backend.engine.models.catalog import PlayerClassCategory


@dataclass(frozen=True)
class ClassDefinition:
    """Static class metadata used to build content-driven player support."""

    class_id: str
    display_name: str
    category: PlayerClassCategory
    hit_die: int
    primary_abilities: tuple[str, ...]
    max_supported_level: int


CLASS_DEFINITIONS: dict[str, ClassDefinition] = {
    "fighter": ClassDefinition(
        class_id="fighter",
        display_name="Fighter",
        category="martial",
        hit_die=10,
        primary_abilities=("str", "dex"),
        max_supported_level=5,
    ),
    "rogue": ClassDefinition(
        class_id="rogue",
        display_name="Rogue",
        category="martial",
        hit_die=8,
        primary_abilities=("dex",),
        max_supported_level=5,
    ),
    "barbarian": ClassDefinition(
        class_id="barbarian",
        display_name="Barbarian",
        category="martial",
        hit_die=12,
        primary_abilities=("str", "con"),
        max_supported_level=2,
    ),
    "monk": ClassDefinition(
        class_id="monk",
        display_name="Monk",
        category="martial",
        hit_die=8,
        primary_abilities=("dex", "wis"),
        max_supported_level=2,
    ),
    "paladin": ClassDefinition(
        class_id="paladin",
        display_name="Paladin",
        category="half_caster",
        hit_die=10,
        primary_abilities=("str", "cha"),
        max_supported_level=5,
    ),
    "wizard": ClassDefinition(
        class_id="wizard",
        display_name="Wizard",
        category="spellcaster",
        hit_die=6,
        primary_abilities=("int",),
        max_supported_level=1,
    ),
}


def get_class_definition(class_id: str) -> ClassDefinition:
    try:
        return CLASS_DEFINITIONS[class_id]
    except KeyError as error:
        raise ValueError(f"Unknown class definition '{class_id}'.") from error
