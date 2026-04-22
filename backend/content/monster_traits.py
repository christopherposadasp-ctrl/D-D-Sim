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
}


def get_monster_trait(trait_id: str) -> MonsterTraitDefinition:
    try:
        return MONSTER_TRAITS[trait_id]
    except KeyError as error:
        raise ValueError(f"Unknown monster trait '{trait_id}'.") from error
