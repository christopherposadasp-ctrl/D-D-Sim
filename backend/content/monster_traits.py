from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonsterTraitDefinition:
    """Reusable monster trait metadata.

    Traits define legal capabilities. The AI layer remains responsible for
    choosing when to spend those capabilities on a turn.
    """

    trait_id: str
    display_name: str
    description: str
    granted_action_ids: tuple[str, ...] = ()
    granted_bonus_action_ids: tuple[str, ...] = ()
    granted_reaction_ids: tuple[str, ...] = ()


MONSTER_TRAITS: dict[str, MonsterTraitDefinition] = {
    "nimble_escape": MonsterTraitDefinition(
        trait_id="nimble_escape",
        display_name="Nimble Escape",
        description="This creature can Disengage as a bonus action.",
        granted_bonus_action_ids=("disengage",),
    ),
    "aggressive": MonsterTraitDefinition(
        trait_id="aggressive",
        display_name="Aggressive",
        description="This creature can spend a bonus action to gain extra movement toward an enemy.",
        granted_bonus_action_ids=("aggressive_dash",),
    ),
    "pack_tactics": MonsterTraitDefinition(
        trait_id="pack_tactics",
        display_name="Pack Tactics",
        description=(
            "This creature has advantage on attack rolls against a creature "
            "if at least one conscious ally is within 5 feet of the target."
        ),
    ),
    "sunlight_sensitivity": MonsterTraitDefinition(
        trait_id="sunlight_sensitivity",
        display_name="Sunlight Sensitivity",
        description="This creature is sensitive to bright sunlight; lighting is not modeled by the live simulator.",
    ),
    "aura_of_authority": MonsterTraitDefinition(
        trait_id="aura_of_authority",
        display_name="Aura of Authority",
        description=(
            "While this creature is active, it and allied creatures within 10 feet "
            "have advantage on attack rolls and saving throws."
        ),
    ),
    "agile": MonsterTraitDefinition(
        trait_id="agile",
        display_name="Agile",
        description="This creature avoids opportunity attacks when moving away; opportunity immunity is not modeled yet.",
    ),
    "jumper": MonsterTraitDefinition(
        trait_id="jumper",
        display_name="Jumper",
        description="This creature uses Dexterity for jump distance; tactical jumping is not modeled by the live simulator.",
    ),
    "bloodied_frenzy": MonsterTraitDefinition(
        trait_id="bloodied_frenzy",
        display_name="Bloodied Frenzy",
        description="While Bloodied, this creature has advantage on attack rolls and saving throws.",
    ),
    "rampage": MonsterTraitDefinition(
        trait_id="rampage",
        display_name="Rampage",
        description=(
            "Immediately after dealing damage to a creature that is already Bloodied, "
            "this creature can move up to half its Speed and make one melee attack."
        ),
        granted_bonus_action_ids=("rampage",),
    ),
    "undead_fortitude": MonsterTraitDefinition(
        trait_id="undead_fortitude",
        display_name="Undead Fortitude",
        description=(
            "When this undead would be reduced to 0 Hit Points, it can attempt a Constitution "
            "save to remain at 1 Hit Point unless the damage was radiant or from a critical hit."
        ),
    ),
    "opening_flight_landing": MonsterTraitDefinition(
        trait_id="opening_flight_landing",
        display_name="Opening Flight Landing",
        description=(
            "On its first turn, this creature can descend into any legal landing space, "
            "then fights on the ground afterward."
        ),
    ),
    "ice_walk": MonsterTraitDefinition(
        trait_id="ice_walk",
        display_name="Ice Walk",
        description="This creature moves across ice safely; ice terrain is not modeled by the live simulator.",
    ),
    "legendary_resistance": MonsterTraitDefinition(
        trait_id="legendary_resistance",
        display_name="Legendary Resistance",
        description="If this creature fails a saving throw, it can choose to succeed instead.",
    ),
    "detect_magic": MonsterTraitDefinition(
        trait_id="detect_magic",
        display_name="Detect Magic",
        description="This creature can detect magic outside the combat model; no runtime behavior is applied.",
    ),
}


def get_monster_trait(trait_id: str) -> MonsterTraitDefinition:
    try:
        return MONSTER_TRAITS[trait_id]
    except KeyError as error:
        raise ValueError(f"Unknown monster trait '{trait_id}'.") from error
