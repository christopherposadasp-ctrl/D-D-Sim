from __future__ import annotations

from backend.content.enemies import create_enemy
from backend.content.player_loadouts import create_player_unit
from backend.engine.constants import ARCHER_GOBLIN_IDS
from backend.engine.models.state import UnitState

DEFAULT_PLAYER_LOADOUT_ID = "fighter_sample_build"


def create_fighter(unit_id: str) -> UnitState:
    """Create the current proof-of-concept player unit from the content registry."""

    return create_player_unit(unit_id, DEFAULT_PLAYER_LOADOUT_ID)


def create_goblin(unit_id: str) -> UnitState:
    """Create the legacy goblin setup through the shared monster registry."""

    variant_id = "goblin_archer" if unit_id in ARCHER_GOBLIN_IDS else "goblin_raider"
    return create_enemy(unit_id, variant_id)
