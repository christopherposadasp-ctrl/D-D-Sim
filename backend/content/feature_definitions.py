from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from backend.engine.models.state import UnitState

FeatureKind = Literal["class_feature", "fighting_style", "feat", "weapon_mastery", "resource", "passive"]


@dataclass(frozen=True)
class FeatureDefinition:
    """Static content entry for a reusable player-facing feature."""

    feature_id: str
    display_name: str
    kind: FeatureKind
    description: str
    granted_action_ids: tuple[str, ...] = ()
    granted_bonus_action_ids: tuple[str, ...] = ()
    granted_reaction_ids: tuple[str, ...] = ()
    granted_maneuver_ids: tuple[str, ...] = ()
    granted_cunning_strike_ids: tuple[str, ...] = ()


FEATURE_DEFINITIONS: dict[str, FeatureDefinition] = {
    "second_wind": FeatureDefinition(
        feature_id="second_wind",
        display_name="Second Wind",
        kind="class_feature",
        description="Bonus-action self-heal with limited uses per encounter.",
        granted_bonus_action_ids=("second_wind",),
    ),
    "action_surge": FeatureDefinition(
        feature_id="action_surge",
        display_name="Action Surge",
        kind="class_feature",
        description="Once per encounter, take one additional action on your turn.",
    ),
    "combat_superiority": FeatureDefinition(
        feature_id="combat_superiority",
        display_name="Combat Superiority",
        kind="class_feature",
        description="Battle Master maneuvers fueled by d8 Superiority Dice.",
        granted_maneuver_ids=("precision_attack", "riposte", "trip_attack"),
    ),
    "student_of_war": FeatureDefinition(
        feature_id="student_of_war",
        display_name="Student of War",
        kind="class_feature",
        description="Battle Master level 3 non-combat proficiency support tracked as metadata.",
    ),
    "great_weapon_master": FeatureDefinition(
        feature_id="great_weapon_master",
        display_name="Great Weapon Master",
        kind="feat",
        description="Strength increase plus heavy-weapon damage and Hew bonus attacks for great-weapon strikes.",
        granted_bonus_action_ids=("great_weapon_master_hewing",),
    ),
    "tactical_shift": FeatureDefinition(
        feature_id="tactical_shift",
        display_name="Tactical Shift",
        kind="class_feature",
        description="When Second Wind is used, the fighter can shift up to half speed without provoking opportunity attacks.",
    ),
    "great_weapon_fighting": FeatureDefinition(
        feature_id="great_weapon_fighting",
        display_name="Great Weapon Fighting",
        kind="fighting_style",
        description="Two-handed melee damage dice treat 1s and 2s as 3s in the current model.",
    ),
    "savage_attacker": FeatureDefinition(
        feature_id="savage_attacker",
        display_name="Savage Attacker",
        kind="feat",
        description="Roll weapon damage twice once per turn and keep the better result.",
    ),
    "weapon_mastery_graze": FeatureDefinition(
        feature_id="weapon_mastery_graze",
        display_name="Weapon Mastery: Graze",
        kind="weapon_mastery",
        description="Missed attacks with the mastered weapon still deal graze damage.",
    ),
    "weapon_mastery_sap": FeatureDefinition(
        feature_id="weapon_mastery_sap",
        display_name="Weapon Mastery: Sap",
        kind="weapon_mastery",
        description="Hits with the mastered weapon impose disadvantage on the next attack.",
    ),
    "weapon_mastery_slow": FeatureDefinition(
        feature_id="weapon_mastery_slow",
        display_name="Weapon Mastery: Slow",
        kind="weapon_mastery",
        description="Hits with the mastered weapon reduce the target's speed.",
    ),
    "weapon_mastery_cleave": FeatureDefinition(
        feature_id="weapon_mastery_cleave",
        display_name="Weapon Mastery: Cleave",
        kind="weapon_mastery",
        description="Once per turn, a hit can spill into a nearby second target without the ability modifier to damage.",
    ),
    "weapon_mastery_vex": FeatureDefinition(
        feature_id="weapon_mastery_vex",
        display_name="Weapon Mastery: Vex",
        kind="weapon_mastery",
        description="A damaging hit grants advantage on the next attack against the same target.",
    ),
    "sneak_attack": FeatureDefinition(
        feature_id="sneak_attack",
        display_name="Sneak Attack",
        kind="class_feature",
        description="Once per turn, qualifying finesse or ranged hits add rogue precision damage.",
    ),
    "expertise_stealth": FeatureDefinition(
        feature_id="expertise_stealth",
        display_name="Expertise (Stealth)",
        kind="class_feature",
        description="The rogue doubles proficiency for Stealth checks.",
    ),
    "cunning_action": FeatureDefinition(
        feature_id="cunning_action",
        display_name="Cunning Action",
        kind="class_feature",
        description="Bonus-action Dash, Disengage, and Hide package for rogue skirmishing turns.",
        granted_bonus_action_ids=("bonus_dash", "disengage", "hide"),
    ),
    "steady_aim": FeatureDefinition(
        feature_id="steady_aim",
        display_name="Steady Aim",
        kind="class_feature",
        description="Bonus-action aim that grants advantage on a stationary rogue's next attack.",
        granted_bonus_action_ids=("steady_aim",),
    ),
    "assassinate": FeatureDefinition(
        feature_id="assassinate",
        display_name="Assassinate",
        kind="class_feature",
        description="Assassin initiative advantage plus first-round attack and Sneak Attack damage pressure.",
    ),
    "assassin_tools": FeatureDefinition(
        feature_id="assassin_tools",
        display_name="Assassin Tools",
        kind="class_feature",
        description="Metadata-only Assassin tool training; poison and disguise systems are out of scope.",
    ),
    "sharpshooter": FeatureDefinition(
        feature_id="sharpshooter",
        display_name="Sharpshooter",
        kind="feat",
        description="Dexterity increase plus ranged weapon reliability against cover, long range, and close pressure.",
    ),
    "cunning_strike": FeatureDefinition(
        feature_id="cunning_strike",
        display_name="Cunning Strike",
        kind="class_feature",
        description="Spend Sneak Attack dice for tactical riders; AI selection is intentionally deferred.",
        granted_cunning_strike_ids=("poison", "trip", "withdraw"),
    ),
    "uncanny_dodge": FeatureDefinition(
        feature_id="uncanny_dodge",
        display_name="Uncanny Dodge",
        kind="class_feature",
        description="Reaction to halve qualifying attack-roll damage.",
        granted_reaction_ids=("uncanny_dodge",),
    ),
    "rage": FeatureDefinition(
        feature_id="rage",
        display_name="Rage",
        kind="class_feature",
        description="Bonus-action rage granting temporary HP, bonus melee damage, and weapon-damage resistance upkeep.",
        granted_bonus_action_ids=("rage",),
    ),
    "unarmored_defense": FeatureDefinition(
        feature_id="unarmored_defense",
        display_name="Unarmored Defense",
        kind="class_feature",
        description="Class-specific AC formula for unarmored martial defenses.",
    ),
    "reckless_attack": FeatureDefinition(
        feature_id="reckless_attack",
        display_name="Reckless Attack",
        kind="class_feature",
        description="The first Strength-based attack roll on the barbarian's turn can become reckless, granting outgoing and incoming attack advantage until the next turn.",
    ),
    "danger_sense": FeatureDefinition(
        feature_id="danger_sense",
        display_name="Danger Sense",
        kind="class_feature",
        description="The barbarian has advantage on Dexterity saving throws while conscious.",
    ),
    "martial_arts": FeatureDefinition(
        feature_id="martial_arts",
        display_name="Martial Arts",
        kind="class_feature",
        description="Monk level 1 package granting Dexterity-based martial arts attacks and a bonus unarmed strike.",
        granted_bonus_action_ids=("bonus_unarmed_strike",),
    ),
    "monks_focus": FeatureDefinition(
        feature_id="monks_focus",
        display_name="Monk's Focus",
        kind="class_feature",
        description="Level 2 monk focus pool with free bonus Dash and Disengage plus Flurry of Blows, Patient Defense, and Step of the Wind.",
        granted_bonus_action_ids=("bonus_dash", "disengage", "flurry_of_blows", "patient_defense", "step_of_the_wind"),
    ),
    "unarmored_movement": FeatureDefinition(
        feature_id="unarmored_movement",
        display_name="Unarmored Movement",
        kind="class_feature",
        description="The monk's speed increases while using the live unarmored sample build.",
    ),
    "uncanny_metabolism": FeatureDefinition(
        feature_id="uncanny_metabolism",
        display_name="Uncanny Metabolism",
        kind="class_feature",
        description="Initiative-time monk recovery that restores Focus and heals when the monk starts an encounter worn down.",
    ),
    "spellcasting": FeatureDefinition(
        feature_id="spellcasting",
        display_name="Spellcasting",
        kind="class_feature",
        description="Level 1 wizard spellcasting with prepared spell counts, cantrips, and first-level spell slots.",
    ),
    "ritual_adept": FeatureDefinition(
        feature_id="ritual_adept",
        display_name="Ritual Adept",
        kind="class_feature",
        description="Wizard ritual casting support tracked as level 1 metadata for future non-combat magic.",
    ),
    "arcane_recovery": FeatureDefinition(
        feature_id="arcane_recovery",
        display_name="Arcane Recovery",
        kind="class_feature",
        description="Wizard short-rest slot recovery tracked as metadata; live encounter actions do not use it yet.",
    ),
    "ki": FeatureDefinition(
        feature_id="ki",
        display_name="Ki",
        kind="resource",
        description="Future monk limited-use resource.",
    ),
    "extra_attack": FeatureDefinition(
        feature_id="extra_attack",
        display_name="Extra Attack",
        kind="class_feature",
        description="The fighter makes two weapon attacks when taking the Attack action.",
    ),
}


def get_feature_definition(feature_id: str) -> FeatureDefinition:
    try:
        return FEATURE_DEFINITIONS[feature_id]
    except KeyError as error:
        raise ValueError(f"Unknown feature definition '{feature_id}'.") from error


def unit_has_feature(unit: UnitState, feature_id: str) -> bool:
    return feature_id in unit.feature_ids


def get_granted_bonus_action_ids_for_unit(unit: UnitState) -> tuple[str, ...]:
    granted_bonus_action_ids: set[str] = set()
    for feature_id in unit.feature_ids:
        granted_bonus_action_ids.update(get_feature_definition(feature_id).granted_bonus_action_ids)
    return tuple(sorted(granted_bonus_action_ids))


def unit_has_granted_bonus_action(unit: UnitState, action_id: str) -> bool:
    return action_id in get_granted_bonus_action_ids_for_unit(unit)


def get_granted_maneuver_ids_for_unit(unit: UnitState) -> tuple[str, ...]:
    granted_maneuver_ids: set[str] = set()
    for feature_id in unit.feature_ids:
        granted_maneuver_ids.update(get_feature_definition(feature_id).granted_maneuver_ids)
    return tuple(sorted(granted_maneuver_ids))


def unit_has_granted_maneuver(unit: UnitState, maneuver_id: str) -> bool:
    return maneuver_id in get_granted_maneuver_ids_for_unit(unit)


def get_granted_cunning_strike_ids_for_unit(unit: UnitState) -> tuple[str, ...]:
    granted_cunning_strike_ids: set[str] = set()
    for feature_id in unit.feature_ids:
        granted_cunning_strike_ids.update(get_feature_definition(feature_id).granted_cunning_strike_ids)
    return tuple(sorted(granted_cunning_strike_ids))


def unit_has_granted_cunning_strike(unit: UnitState, strike_id: str) -> bool:
    return strike_id in get_granted_cunning_strike_ids_for_unit(unit)
