from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecialActionDefinition:
    """Static metadata for non-standard monster actions.

    Regular weapon attacks stay in the attack-sequence content path. This
    registry exists for actions like Swallow that have bespoke preconditions
    and resolvers but still need a stable data vocabulary.
    """

    action_id: str
    display_name: str
    description: str


SPECIAL_ACTIONS: dict[str, SpecialActionDefinition] = {
    "swallow": SpecialActionDefinition(
        action_id="swallow",
        display_name="Swallow",
        description="Swallow a creature the monster already has grappled in its mouth.",
    ),
}


def get_special_action(action_id: str) -> SpecialActionDefinition:
    try:
        return SPECIAL_ACTIONS[action_id]
    except KeyError as error:
        raise ValueError(f"Unknown special action '{action_id}'.") from error
