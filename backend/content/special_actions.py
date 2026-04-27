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


@dataclass(frozen=True)
class LegendarySphereActionDefinition:
    action_id: str
    display_name: str
    resource_pool_id: str
    save_ability: str
    save_dc: int
    range_squares: int
    radius_squares: int
    damage_die_count: int
    damage_die_sides: int
    damage_type: str
    speed_zero_on_failed_save: bool = False


@dataclass(frozen=True)
class LegendaryConeFearActionDefinition:
    action_id: str
    display_name: str
    resource_pool_id: str
    save_ability: str
    save_dc: int
    range_squares: int
    duration_rounds: int


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
    "scorching_ray": SpecialActionDefinition(
        action_id="scorching_ray",
        display_name="Scorching Ray",
        description="Cast three ranged fire rays as a monster spell-like action.",
    ),
    "freezing_burst": SpecialActionDefinition(
        action_id="freezing_burst",
        display_name="Freezing Burst",
        description="A freezing sphere that can damage and halt creatures that fail Constitution saves.",
    ),
    "frightful_presence": SpecialActionDefinition(
        action_id="frightful_presence",
        display_name="Frightful Presence",
        description="A terrifying presence that can frighten creatures in a cone.",
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
    "adult_white_cold_breath": DragonBreathActionDefinition(
        action_id="cold_breath",
        display_name="Cold Breath",
        resource_pool_id="cold_breath_available",
        save_ability="con",
        save_dc=19,
        range_squares=12,
        damage_die_count=12,
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
    "adult_red_fire_breath": DragonBreathActionDefinition(
        action_id="fire_breath",
        display_name="Fire Breath",
        resource_pool_id="fire_breath_available",
        save_ability="dex",
        save_dc=21,
        range_squares=12,
        damage_die_count=17,
        damage_die_sides=6,
        damage_type="fire",
    ),
}


LEGENDARY_CONE_FEAR_ACTIONS: dict[str, LegendaryConeFearActionDefinition] = {
    "frightful_presence": LegendaryConeFearActionDefinition(
        action_id="frightful_presence",
        display_name="Frightful Presence",
        resource_pool_id="frightful_presence_available",
        save_ability="wis",
        save_dc=14,
        range_squares=6,
        duration_rounds=10,
    ),
}


LEGENDARY_SPHERE_ACTIONS: dict[str, LegendarySphereActionDefinition] = {
    "freezing_burst": LegendarySphereActionDefinition(
        action_id="freezing_burst",
        display_name="Freezing Burst",
        resource_pool_id="freezing_burst_available",
        save_ability="con",
        save_dc=14,
        range_squares=24,
        radius_squares=6,
        damage_die_count=2,
        damage_die_sides=6,
        damage_type="cold",
        speed_zero_on_failed_save=True,
    ),
}


def get_special_action(action_id: str) -> SpecialActionDefinition:
    try:
        return SPECIAL_ACTIONS[action_id]
    except KeyError as error:
        raise ValueError(f"Unknown special action '{action_id}'.") from error
