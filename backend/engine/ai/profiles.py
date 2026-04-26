from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MonsterCombatStyle = Literal["melee", "ranged"]


@dataclass(frozen=True)
class MonsterAiProfile:
    """High-level AI profile shared across many monsters.

    Profiles intentionally stay broad. Monster-specific exceptions should come
    from traits and legal action lists, not from a unique AI function per
    creature.
    """

    profile_id: str
    display_name: str
    combat_style: MonsterCombatStyle
    description: str
    prefers_spacing: bool = False


MONSTER_AI_PROFILES: dict[str, MonsterAiProfile] = {
    "melee_brute": MonsterAiProfile(
        profile_id="melee_brute",
        display_name="Melee Brute",
        combat_style="melee",
        description="Close into melee and stay there.",
    ),
    "line_holder": MonsterAiProfile(
        profile_id="line_holder",
        display_name="Line Holder",
        combat_style="melee",
        description="Occupy melee space and pressure the closest front-line target.",
    ),
    "ranged_skirmisher": MonsterAiProfile(
        profile_id="ranged_skirmisher",
        display_name="Ranged Skirmisher",
        combat_style="ranged",
        description="Maintain ranged pressure and reposition for cleaner shots.",
        prefers_spacing=True,
    ),
    "pack_hunter": MonsterAiProfile(
        profile_id="pack_hunter",
        display_name="Pack Hunter",
        combat_style="melee",
        description="Close quickly and attack in close quarters.",
    ),
    "dragon": MonsterAiProfile(
        profile_id="dragon",
        display_name="Dragon",
        combat_style="melee",
        description="Use dragon-specific opening movement, then fight as a grounded melee threat.",
    ),
    "swallow_predator": MonsterAiProfile(
        profile_id="swallow_predator",
        display_name="Swallow Predator",
        combat_style="melee",
        description="Bite a target, then swallow it as soon as the mouth hold is secure.",
    ),
    "grappling_brute": MonsterAiProfile(
        profile_id="grappling_brute",
        display_name="Grappling Brute",
        combat_style="melee",
        description="Clamp onto one target with a bite and keep pressure on that same victim.",
    ),
}


def get_monster_ai_profile(profile_id: str) -> MonsterAiProfile:
    try:
        return MONSTER_AI_PROFILES[profile_id]
    except KeyError as error:
        raise ValueError(f"Unknown monster AI profile '{profile_id}'.") from error
