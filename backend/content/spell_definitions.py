from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpellDefinition:
    """Future combat spell content entry.

    V4.2 only establishes the registry shape. The live simulator does not
    consume these entries yet.
    """

    spell_id: str
    display_name: str
    level: int
    school: str
    description: str


SPELL_DEFINITIONS: dict[str, SpellDefinition] = {}

