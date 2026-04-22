from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.engine.models.state import DiceSpec


@dataclass(frozen=True)
class SpellDefinition:
    """Static combat spell content entry for the live simulator."""

    spell_id: str
    display_name: str
    level: int
    school: str
    description: str
    timing: Literal["action", "reaction"]
    targeting_mode: Literal[
        "ranged_spell_attack",
        "melee_spell_attack",
        "auto_hit_single_target",
        "reaction_self",
        "self_cone_save",
    ]
    range_feet: int
    damage_dice: tuple[DiceSpec, ...]
    damage_modifier: int
    damage_type: str
    attack_ability: str | None = None
    save_ability: str | None = None
    half_on_success: bool = False
    on_hit_effect_kind: Literal["no_reactions"] | None = None
    ac_bonus: int = 0
    negates_magic_missile: bool = False


SPELL_DEFINITIONS: dict[str, SpellDefinition] = {
    "fire_bolt": SpellDefinition(
        spell_id="fire_bolt",
        display_name="Fire Bolt",
        level=0,
        school="evocation",
        description="Ranged spell attack dealing fire damage.",
        timing="action",
        targeting_mode="ranged_spell_attack",
        range_feet=120,
        damage_dice=(DiceSpec(count=1, sides=10),),
        damage_modifier=0,
        damage_type="fire",
        attack_ability="int",
    ),
    "shocking_grasp": SpellDefinition(
        spell_id="shocking_grasp",
        display_name="Shocking Grasp",
        level=0,
        school="evocation",
        description="Melee spell attack dealing lightning damage and suppressing reactions on a hit.",
        timing="action",
        targeting_mode="melee_spell_attack",
        range_feet=5,
        damage_dice=(DiceSpec(count=1, sides=8),),
        damage_modifier=0,
        damage_type="lightning",
        attack_ability="int",
        on_hit_effect_kind="no_reactions",
    ),
    "magic_missile": SpellDefinition(
        spell_id="magic_missile",
        display_name="Magic Missile",
        level=1,
        school="evocation",
        description="Auto-hit force darts focused into one target in the current model.",
        timing="action",
        targeting_mode="auto_hit_single_target",
        range_feet=120,
        damage_dice=(DiceSpec(count=3, sides=4),),
        damage_modifier=3,
        damage_type="force",
    ),
    "shield": SpellDefinition(
        spell_id="shield",
        display_name="Shield",
        level=1,
        school="abjuration",
        description="Reaction spell that grants +5 AC and blocks Magic Missile until the next turn start.",
        timing="reaction",
        targeting_mode="reaction_self",
        range_feet=0,
        damage_dice=(),
        damage_modifier=0,
        damage_type="force",
        ac_bonus=5,
        negates_magic_missile=True,
    ),
    "burning_hands": SpellDefinition(
        spell_id="burning_hands",
        display_name="Burning Hands",
        level=1,
        school="evocation",
        description="Self-origin fire cone forcing Dexterity saves for half damage.",
        timing="action",
        targeting_mode="self_cone_save",
        range_feet=15,
        damage_dice=(DiceSpec(count=3, sides=6),),
        damage_modifier=0,
        damage_type="fire",
        save_ability="dex",
        half_on_success=True,
    ),
}


def get_spell_definition(spell_id: str) -> SpellDefinition:
    try:
        return SPELL_DEFINITIONS[spell_id]
    except KeyError as error:
        raise ValueError(f"Unknown spell definition '{spell_id}'.") from error
