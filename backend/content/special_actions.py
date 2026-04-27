from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecialActionDefinition:
    """Static metadata for non-standard bespoke actions.

    Regular weapon attacks stay in the attack-sequence content path. This
    registry exists for actions that have bespoke preconditions and resolvers
    but still need a stable data vocabulary.
    """

    action_id: str
    display_name: str
    description: str


@dataclass(frozen=True)
class DragonBreathActionDefinition:
    action_id: str
    display_name: str
    resource_pool_id: str
    save_ability: str
    save_dc: int
    range_squares: int
    damage_die_count: int
    damage_die_sides: int
    damage_type: str
    recharge_threshold: int = 5


SPECIAL_ACTIONS: dict[str, SpecialActionDefinition] = {
    "swallow": SpecialActionDefinition(
        action_id="swallow",
        display_name="Swallow",
        description="Swallow a creature the monster already has grappled in its mouth.",
    ),
    "cold_breath": SpecialActionDefinition(
        action_id="cold_breath",
        display_name="Cold Breath",
        description="Exhale a freezing cone that forces Constitution saves for half cold damage.",
    ),
    "fire_breath": SpecialActionDefinition(
        action_id="fire_breath",
        display_name="Fire Breath",
        description="Exhale a fiery cone that forces Dexterity saves for half fire damage.",
    ),
    "natures_wrath": SpecialActionDefinition(
        action_id="natures_wrath",
        display_name="Nature's Wrath",
        description="Channel Divinity action that restrains nearby chosen enemies with spectral vines.",
    ),
}


DRAGON_BREATH_ACTIONS: dict[str, DragonBreathActionDefinition] = {
    "cold_breath": DragonBreathActionDefinition(
        action_id="cold_breath",
        display_name="Cold Breath",
        resource_pool_id="cold_breath_available",
        save_ability="con",
        save_dc=15,
        range_squares=6,
        damage_die_count=9,
        damage_die_sides=8,
        damage_type="cold",
    ),
    "fire_breath": DragonBreathActionDefinition(
        action_id="fire_breath",
        display_name="Fire Breath",
        resource_pool_id="fire_breath_available",
        save_ability="dex",
        save_dc=17,
        range_squares=6,
        damage_die_count=16,
        damage_die_sides=6,
        damage_type="fire",
    ),
}


def get_special_action(action_id: str) -> SpecialActionDefinition:
    try:
        return SPECIAL_ACTIONS[action_id]
    except KeyError as error:
        raise ValueError(f"Unknown special action '{action_id}'.") from error
