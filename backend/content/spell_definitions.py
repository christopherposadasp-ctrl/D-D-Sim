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
    timing: Literal["action", "bonus_action", "reaction"]
    targeting_mode: Literal[
        "ranged_spell_attack",
        "melee_spell_attack",
        "auto_hit_single_target",
        "reaction_self",
        "smite_trigger",
        "self_cone_save",
        "multi_ally_buff",
        "touch_heal",
        "self_ac_buff",
        "self_temp_hp",
        "multi_ally_hp_buff",
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
    concentration: bool = False
    duration_rounds: int = 0
    max_targets: int = 1
    healing_dice: tuple[DiceSpec, ...] = ()
    healing_modifier_ability: str | None = None
    temporary_hit_point_dice: tuple[DiceSpec, ...] = ()
    temporary_hit_point_modifier: int = 0
    hp_bonus: int = 0


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
    "bless": SpellDefinition(
        spell_id="bless",
        display_name="Bless",
        level=1,
        school="enchantment",
        description="Concentration prayer that adds 1d4 to attack rolls and saving throws for up to three allies.",
        timing="action",
        targeting_mode="multi_ally_buff",
        range_feet=30,
        damage_dice=(),
        damage_modifier=0,
        damage_type="none",
        concentration=True,
        duration_rounds=10,
        max_targets=3,
    ),
    "cure_wounds": SpellDefinition(
        spell_id="cure_wounds",
        display_name="Cure Wounds",
        level=1,
        school="abjuration",
        description="Touch-range healing spell restoring 2d8 plus the caster's spellcasting modifier.",
        timing="action",
        targeting_mode="touch_heal",
        range_feet=5,
        damage_dice=(),
        damage_modifier=0,
        damage_type="none",
        healing_dice=(DiceSpec(count=2, sides=8),),
        healing_modifier_ability="spellcasting",
    ),
    "aid": SpellDefinition(
        spell_id="aid",
        display_name="Aid",
        level=2,
        school="abjuration",
        description="Non-concentration support magic that increases current and maximum HP for up to three allies.",
        timing="action",
        targeting_mode="multi_ally_hp_buff",
        range_feet=30,
        damage_dice=(),
        damage_modifier=0,
        damage_type="none",
        duration_rounds=4800,
        max_targets=3,
        hp_bonus=5,
    ),
    "mage_armor": SpellDefinition(
        spell_id="mage_armor",
        display_name="Mage Armor",
        level=1,
        school="abjuration",
        description="Self-only abjuration that sets base AC to 13 + Dexterity modifier when better.",
        timing="action",
        targeting_mode="self_ac_buff",
        range_feet=0,
        damage_dice=(),
        damage_modifier=0,
        damage_type="none",
        concentration=False,
        duration_rounds=4800,
    ),
    "false_life": SpellDefinition(
        spell_id="false_life",
        display_name="False Life",
        level=1,
        school="necromancy",
        description="Self-only necromancy spell granting 2d4 + 4 temporary hit points.",
        timing="action",
        targeting_mode="self_temp_hp",
        range_feet=0,
        damage_dice=(),
        damage_modifier=0,
        damage_type="none",
        concentration=False,
        duration_rounds=600,
        temporary_hit_point_dice=(DiceSpec(count=2, sides=4),),
        temporary_hit_point_modifier=4,
    ),
    "divine_smite": SpellDefinition(
        spell_id="divine_smite",
        display_name="Divine Smite",
        level=1,
        school="evocation",
        description="Bonus-action smite after a melee hit, adding radiant damage to the attack.",
        timing="bonus_action",
        targeting_mode="smite_trigger",
        range_feet=0,
        damage_dice=(DiceSpec(count=2, sides=8),),
        damage_modifier=0,
        damage_type="radiant",
    ),
}


def get_spell_definition(spell_id: str) -> SpellDefinition:
    try:
        return SPELL_DEFINITIONS[spell_id]
    except KeyError as error:
        raise ValueError(f"Unknown spell definition '{spell_id}'.") from error
