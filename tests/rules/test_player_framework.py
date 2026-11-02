from __future__ import annotations

from backend.content.attack_sequences import build_player_attack_action
from backend.content.class_progressions import get_proficiency_bonus
from backend.content.feature_definitions import (
    unit_has_granted_action,
    unit_has_granted_bonus_action,
    unit_has_granted_cunning_strike,
)
from backend.engine import create_encounter
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import AidEffect, EncounterConfig, GridPosition
from backend.engine.rules.combat_rules import AttackRollOverrides, ResolveAttackArgs, resolve_attack
from backend.engine.services.catalog import get_player_catalog


def build_trio_placements(**overrides):
    placements = {
        "F1": GridPosition(x=1, y=1),
        "F2": GridPosition(x=2, y=1),
        "F3": GridPosition(x=5, y=5),
        "G1": GridPosition(x=3, y=1),
        "G2": GridPosition(x=10, y=10),
        "G3": GridPosition(x=11, y=10),
        "G4": GridPosition(x=12, y=10),
        "G5": GridPosition(x=13, y=10),
        "G6": GridPosition(x=14, y=10),
        "G7": GridPosition(x=15, y=10),
    }
    placements.update(overrides)
    return placements


def test_current_player_sample_build_uses_content_registry_metadata() -> None:
    encounter = create_encounter(EncounterConfig(seed="player-registry-metadata", placements=DEFAULT_POSITIONS))
    fighter = encounter.units["F1"]

    assert fighter.class_id == "fighter"
    assert fighter.level == 5
    assert fighter.loadout_id == "fighter_level5_sample_build"
    assert fighter.behavior_profile == "martial_striker"
    assert "second_wind" in fighter.feature_ids
    assert "action_surge" in fighter.feature_ids
    assert "combat_superiority" in fighter.feature_ids
    assert "student_of_war" in fighter.feature_ids
    assert "great_weapon_master" in fighter.feature_ids
    assert "extra_attack" in fighter.feature_ids
    assert "tactical_shift" in fighter.feature_ids
    assert "savage_attacker" in fighter.feature_ids
    assert fighter.resource_pools == {"second_wind": 3, "action_surge": 1, "superiority_dice": 4, "javelins": 8}
    assert fighter.resources.action_surge_uses == 1
    assert fighter.resources.superiority_dice == 4


def test_level3_fighter_battle_master_sample_build_uses_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-level3-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="fighter_level3_sample_trio",
        )
    )
    fighter = encounter.units["F1"]

    assert fighter.class_id == "fighter"
    assert fighter.level == 3
    assert fighter.loadout_id == "fighter_level3_sample_build"
    assert fighter.max_hp == 29
    assert fighter.ac == 18
    assert tuple(sorted(fighter.attacks.keys())) == ("flail", "greatsword", "javelin")
    assert "second_wind" in fighter.feature_ids
    assert "action_surge" in fighter.feature_ids
    assert "combat_superiority" in fighter.feature_ids
    assert "student_of_war" in fighter.feature_ids
    assert fighter.resource_pools == {"second_wind": 2, "action_surge": 1, "superiority_dice": 4, "javelins": 8}
    assert fighter.resources.superiority_dice == 4


def test_level4_fighter_great_weapon_master_sample_build_uses_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-level4-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="fighter_level4_sample_trio",
        )
    )
    fighter = encounter.units["F1"]

    assert fighter.class_id == "fighter"
    assert fighter.level == 4
    assert fighter.loadout_id == "fighter_level4_sample_build"
    assert fighter.max_hp == 37
    assert fighter.ac == 18
    assert fighter.ability_mods.str == 4
    assert tuple(sorted(fighter.attacks.keys())) == ("flail", "greatsword", "javelin")
    assert fighter.attacks["greatsword"].attack_bonus == 6
    assert fighter.attacks["greatsword"].damage_modifier == 4
    assert "second_wind" in fighter.feature_ids
    assert "action_surge" in fighter.feature_ids
    assert "combat_superiority" in fighter.feature_ids
    assert "student_of_war" in fighter.feature_ids
    assert "great_weapon_master" in fighter.feature_ids
    assert fighter.resource_pools == {"second_wind": 2, "action_surge": 1, "superiority_dice": 4, "javelins": 8}
    assert fighter.resources.superiority_dice == 4


def test_level5_fighter_extra_attack_sample_build_uses_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-level5-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="fighter_level5_sample_trio",
        )
    )
    fighter = encounter.units["F1"]
    attack_action = build_player_attack_action(fighter)

    assert fighter.class_id == "fighter"
    assert fighter.level == 5
    assert fighter.loadout_id == "fighter_level5_sample_build"
    assert fighter.max_hp == 45
    assert fighter.ac == 18
    assert fighter.ability_mods.str == 4
    assert tuple(sorted(fighter.attacks.keys())) == ("flail", "greatsword", "javelin")
    assert fighter.attacks["greatsword"].attack_bonus == 7
    assert fighter.attacks["greatsword"].damage_modifier == 4
    assert "second_wind" in fighter.feature_ids
    assert "action_surge" in fighter.feature_ids
    assert "combat_superiority" in fighter.feature_ids
    assert "student_of_war" in fighter.feature_ids
    assert "great_weapon_master" in fighter.feature_ids
    assert "extra_attack" in fighter.feature_ids
    assert "tactical_shift" in fighter.feature_ids
    assert fighter.resource_pools == {"second_wind": 3, "action_surge": 1, "superiority_dice": 4, "javelins": 8}
    assert fighter.resources.second_wind_uses == 3
    assert fighter.resources.superiority_dice == 4
    assert len(attack_action.steps) == 2


def test_barbarian_sample_build_uses_content_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="barbarian_sample_trio",
        )
    )
    barbarian = encounter.units["F1"]

    assert barbarian.class_id == "barbarian"
    assert barbarian.level == 1
    assert barbarian.loadout_id == "barbarian_sample_build"
    assert barbarian.behavior_profile == "martial_berserker"
    assert barbarian.ac == 14
    assert "rage" in barbarian.feature_ids
    assert "unarmored_defense" in barbarian.feature_ids
    assert "weapon_mastery_cleave" in barbarian.feature_ids
    assert "weapon_mastery_vex" in barbarian.feature_ids
    assert barbarian.resource_pools == {"rage": 2, "handaxes": 4}
    assert barbarian.resources.rage_uses == 2
    assert barbarian.resources.handaxes == 4


def test_level2_barbarian_sample_build_uses_content_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-level2-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="barbarian_level2_sample_trio",
        )
    )
    barbarian = encounter.units["F1"]

    assert barbarian.class_id == "barbarian"
    assert barbarian.level == 2
    assert barbarian.loadout_id == "barbarian_level2_sample_build"
    assert barbarian.behavior_profile == "martial_berserker"
    assert barbarian.ac == 14
    assert barbarian.max_hp == 25
    assert "rage" in barbarian.feature_ids
    assert "unarmored_defense" in barbarian.feature_ids
    assert "reckless_attack" in barbarian.feature_ids
    assert "danger_sense" in barbarian.feature_ids
    assert barbarian.resource_pools == {"rage": 2, "handaxes": 4}
    assert barbarian.resources.rage_uses == 2
    assert barbarian.resources.handaxes == 4


def test_monk_sample_build_uses_content_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="monk_sample_trio",
        )
    )
    monk = encounter.units["F1"]

    assert monk.class_id == "monk"
    assert monk.level == 1
    assert monk.loadout_id == "monk_sample_build"
    assert monk.behavior_profile == "martial_artist"
    assert monk.ac == 15
    assert monk.max_hp == 10
    assert monk.resources.second_wind_uses == 0
    assert monk.resources.javelins == 0
    assert monk.resources.rage_uses == 0
    assert monk.resources.handaxes == 0
    assert "martial_arts" in monk.feature_ids
    assert "unarmored_defense" in monk.feature_ids
    assert monk.resource_pools == {}


def test_level2_monk_sample_build_uses_focus_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-level2-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="monk_level2_sample_trio",
        )
    )
    monk = encounter.units["F1"]

    assert monk.class_id == "monk"
    assert monk.level == 2
    assert monk.loadout_id == "monk_level2_sample_build"
    assert monk.behavior_profile == "martial_artist"
    assert monk.ac == 15
    assert monk.max_hp == 18
    assert monk.speed == 40
    assert monk.resources.focus_points == 2
    assert monk.resources.uncanny_metabolism_uses == 1
    assert "martial_arts" in monk.feature_ids
    assert "unarmored_defense" in monk.feature_ids
    assert "monks_focus" in monk.feature_ids
    assert "unarmored_movement" in monk.feature_ids
    assert "uncanny_metabolism" in monk.feature_ids
    assert monk.resource_pools == {"focus_points": 2, "uncanny_metabolism": 1}


def test_wizard_sample_build_uses_spellcasting_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="wizard_sample_trio",
            player_behavior="dumb",
        )
    )
    wizard = encounter.units["F1"]

    assert wizard.class_id == "wizard"
    assert wizard.level == 1
    assert wizard.loadout_id == "wizard_sample_build"
    assert wizard.behavior_profile == "arcane_artillery"
    assert wizard.ac == 12
    assert wizard.max_hp == 8
    assert wizard.role_tags == ["caster"]
    assert wizard.resources.spell_slots_level_1 == 2
    assert wizard.combat_cantrip_ids == ["fire_bolt", "shocking_grasp"]
    assert wizard.prepared_combat_spell_ids == ["magic_missile", "shield", "burning_hands", "mage_armor"]
    assert wizard.cantrips_known == 3
    assert wizard.spellbook_spells == 6
    assert wizard.prepared_spells == 4
    assert "spellcasting" in wizard.feature_ids
    assert "ritual_adept" in wizard.feature_ids
    assert "arcane_recovery" in wizard.feature_ids
    assert wizard.resource_pools == {"spell_slots_level_1": 2}


def test_wizard_level2_sample_build_uses_expanded_spellcasting_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level2-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="wizard_level2_sample_trio",
            player_behavior="dumb",
        )
    )
    wizard = encounter.units["F1"]

    assert wizard.class_id == "wizard"
    assert wizard.level == 2
    assert wizard.loadout_id == "wizard_level2_sample_build"
    assert wizard.behavior_profile == "arcane_artillery"
    assert wizard.ac == 12
    assert wizard.max_hp == 14
    assert wizard.role_tags == ["caster"]
    assert wizard.resources.spell_slots_level_1 == 3
    assert wizard.combat_cantrip_ids == ["fire_bolt", "shocking_grasp"]
    assert wizard.prepared_combat_spell_ids == ["magic_missile", "shield", "burning_hands", "mage_armor"]
    assert wizard.cantrips_known == 3
    assert wizard.spellbook_spells == 8
    assert wizard.prepared_spells == 5
    assert "spellcasting" in wizard.feature_ids
    assert "ritual_adept" in wizard.feature_ids
    assert "arcane_recovery" in wizard.feature_ids
    assert "scholar" in wizard.feature_ids
    assert wizard.resource_pools == {"spell_slots_level_1": 3}


def test_wizard_level3_evoker_sample_build_uses_subclass_and_level2_slot_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level3-evoker-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="wizard_level3_evoker_sample_trio",
            player_behavior="dumb",
        )
    )
    wizard = encounter.units["F1"]

    assert wizard.class_id == "wizard"
    assert wizard.level == 3
    assert wizard.loadout_id == "wizard_level3_evoker_sample_build"
    assert wizard.behavior_profile == "arcane_artillery"
    assert wizard.ac == 12
    assert wizard.max_hp == 20
    assert wizard.role_tags == ["caster"]
    assert wizard.resources.spell_slots_level_1 == 4
    assert wizard.resources.spell_slots_level_2 == 2
    assert wizard.combat_cantrip_ids == ["fire_bolt", "shocking_grasp"]
    assert wizard.prepared_combat_spell_ids == [
        "magic_missile",
        "shield",
        "burning_hands",
        "mage_armor",
        "scorching_ray",
        "shatter",
    ]
    assert wizard.cantrips_known == 3
    assert wizard.spellbook_spells == 12
    assert wizard.prepared_spells == 6
    assert "evoker" in wizard.feature_ids
    assert "evocation_savant" in wizard.feature_ids
    assert "potent_cantrip" in wizard.feature_ids
    assert wizard.resource_pools == {"spell_slots_level_1": 4, "spell_slots_level_2": 2}


def test_wizard_level4_evoker_sample_build_uses_int_asi_and_extra_level2_slot() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level4-evoker-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="wizard_level4_evoker_sample_trio",
            player_behavior="dumb",
        )
    )
    wizard = encounter.units["F1"]

    assert wizard.class_id == "wizard"
    assert wizard.level == 4
    assert wizard.loadout_id == "wizard_level4_evoker_sample_build"
    assert wizard.behavior_profile == "arcane_artillery"
    assert wizard.ac == 12
    assert wizard.max_hp == 26
    assert wizard.ability_mods.int == 4
    assert wizard.role_tags == ["caster"]
    assert wizard.resources.spell_slots_level_1 == 4
    assert wizard.resources.spell_slots_level_2 == 3
    assert wizard.combat_cantrip_ids == ["fire_bolt", "shocking_grasp"]
    assert wizard.prepared_combat_spell_ids == [
        "magic_missile",
        "shield",
        "burning_hands",
        "mage_armor",
        "scorching_ray",
        "shatter",
    ]
    assert wizard.cantrips_known == 4
    assert wizard.spellbook_spells == 14
    assert wizard.prepared_spells == 8
    assert "ability_score_improvement" in wizard.feature_ids
    assert "potent_cantrip" in wizard.feature_ids
    assert wizard.resource_pools == {"spell_slots_level_1": 4, "spell_slots_level_2": 3}


def test_wizard_level5_evoker_sample_build_adds_level3_slot_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-level5-evoker-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="wizard_level5_evoker_sample_trio",
            player_behavior="dumb",
        )
    )
    wizard = encounter.units["F1"]

    assert wizard.class_id == "wizard"
    assert wizard.level == 5
    assert wizard.loadout_id == "wizard_level5_evoker_sample_build"
    assert wizard.behavior_profile == "arcane_artillery"
    assert wizard.ac == 12
    assert wizard.max_hp == 32
    assert wizard.ability_mods.int == 4
    assert wizard.role_tags == ["caster"]
    assert wizard.resources.spell_slots_level_1 == 4
    assert wizard.resources.spell_slots_level_2 == 3
    assert wizard.resources.spell_slots_level_3 == 2
    assert wizard.combat_cantrip_ids == ["fire_bolt", "shocking_grasp"]
    assert wizard.prepared_combat_spell_ids == [
        "magic_missile",
        "shield",
        "burning_hands",
        "mage_armor",
        "scorching_ray",
        "shatter",
        "fireball",
        "counterspell",
        "haste",
    ]
    assert wizard.cantrips_known == 4
    assert wizard.spellbook_spells == 17
    assert wizard.prepared_spells == 9
    assert "memorize_spell" in wizard.feature_ids
    assert "potent_cantrip" in wizard.feature_ids
    assert wizard.resource_pools == {
        "spell_slots_level_1": 4,
        "spell_slots_level_2": 3,
        "spell_slots_level_3": 2,
    }


def test_paladin_sample_build_uses_support_tank_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="paladin_level1_sample_trio",
        )
    )
    paladin = encounter.units["F1"]

    assert paladin.class_id == "paladin"
    assert paladin.level == 1
    assert paladin.loadout_id == "paladin_level1_sample_build"
    assert paladin.behavior_profile == "divine_guardian"
    assert paladin.role_tags == ["healer"]
    assert paladin.max_hp == 13
    assert paladin.ac == 20
    assert paladin.ability_mods.str == 3
    assert paladin.ability_mods.cha == 2
    assert tuple(sorted(paladin.attacks.keys())) == ("javelin", "longsword")
    assert paladin.attacks["longsword"].attack_bonus == 5
    assert paladin.attacks["longsword"].damage_modifier == 3
    assert paladin.attacks["longsword"].mastery == "sap"
    assert paladin.attacks["javelin"].mastery == "slow"
    assert paladin.resources.lay_on_hands_points == 5
    assert paladin.resources.spell_slots_level_1 == 2
    assert paladin.prepared_combat_spell_ids == ["bless", "cure_wounds"]
    assert paladin.prepared_spells == 2
    assert "lay_on_hands" in paladin.feature_ids
    assert "spellcasting" in paladin.feature_ids
    assert "weapon_mastery" in paladin.feature_ids
    assert unit_has_granted_bonus_action(paladin, "lay_on_hands")
    assert paladin.resource_pools == {"lay_on_hands": 5, "spell_slots_level_1": 2, "javelins": 5}


def test_level2_paladin_sample_build_uses_smite_tank_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-level2-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="paladin_level2_sample_trio",
        )
    )
    paladin = encounter.units["F1"]

    assert paladin.class_id == "paladin"
    assert paladin.level == 2
    assert paladin.loadout_id == "paladin_level2_sample_build"
    assert paladin.behavior_profile == "divine_guardian"
    assert paladin.role_tags == ["healer"]
    assert paladin.max_hp == 22
    assert paladin.ac == 21
    assert tuple(sorted(paladin.attacks.keys())) == ("javelin", "longsword")
    assert paladin.resources.lay_on_hands_points == 10
    assert paladin.resources.spell_slots_level_1 == 2
    assert paladin.prepared_combat_spell_ids == ["bless", "cure_wounds"]
    assert paladin.prepared_spells == 3
    assert "fighting_style_defense" in paladin.feature_ids
    assert "paladins_smite" in paladin.feature_ids
    assert paladin.resource_pools == {"lay_on_hands": 10, "spell_slots_level_1": 2, "javelins": 5}


def test_level3_paladin_sample_build_uses_ancients_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-level3-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="paladin_level3_sample_trio",
        )
    )
    paladin = encounter.units["F1"]

    assert paladin.class_id == "paladin"
    assert paladin.level == 3
    assert paladin.loadout_id == "paladin_level3_sample_build"
    assert paladin.behavior_profile == "divine_guardian"
    assert paladin.role_tags == ["healer"]
    assert paladin.max_hp == 31
    assert paladin.ac == 21
    assert tuple(sorted(paladin.attacks.keys())) == ("javelin", "longsword")
    assert paladin.resources.lay_on_hands_points == 15
    assert paladin.resources.spell_slots_level_1 == 3
    assert paladin.resources.channel_divinity_uses == 2
    assert paladin.prepared_combat_spell_ids == ["bless", "cure_wounds"]
    assert paladin.prepared_spells == 4
    for feature_id in (
        "fighting_style_defense",
        "paladins_smite",
        "channel_divinity",
        "oath_of_the_ancients",
        "natures_wrath",
        "oath_spells_ancients",
    ):
        assert feature_id in paladin.feature_ids
    assert unit_has_granted_action(paladin, "natures_wrath") is True
    assert paladin.resource_pools == {
        "lay_on_hands": 15,
        "spell_slots_level_1": 3,
        "channel_divinity": 2,
        "javelins": 5,
    }


def test_level4_paladin_sample_build_uses_sentinel_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-level4-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="paladin_level4_sample_trio",
        )
    )
    paladin = encounter.units["F1"]

    assert paladin.class_id == "paladin"
    assert paladin.level == 4
    assert paladin.loadout_id == "paladin_level4_sample_build"
    assert paladin.behavior_profile == "divine_guardian"
    assert paladin.role_tags == ["healer"]
    assert paladin.max_hp == 40
    assert paladin.ac == 21
    assert paladin.ability_mods.str == 4
    assert tuple(sorted(paladin.attacks.keys())) == ("javelin", "longsword")
    assert paladin.attacks["longsword"].attack_bonus == 6
    assert paladin.attacks["longsword"].damage_modifier == 4
    assert paladin.attacks["javelin"].attack_bonus == 6
    assert paladin.attacks["javelin"].damage_modifier == 4
    assert paladin.resources.lay_on_hands_points == 20
    assert paladin.resources.spell_slots_level_1 == 3
    assert paladin.resources.channel_divinity_uses == 2
    assert paladin.prepared_combat_spell_ids == ["bless", "cure_wounds"]
    assert paladin.prepared_spells == 5
    for feature_id in (
        "fighting_style_defense",
        "paladins_smite",
        "channel_divinity",
        "oath_of_the_ancients",
        "natures_wrath",
        "oath_spells_ancients",
        "sentinel",
    ):
        assert feature_id in paladin.feature_ids
    assert unit_has_granted_action(paladin, "natures_wrath") is True
    assert paladin.resource_pools == {
        "lay_on_hands": 20,
        "spell_slots_level_1": 3,
        "channel_divinity": 2,
        "javelins": 5,
    }


def test_level5_paladin_sample_build_uses_extra_attack_spell_registry_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-level5-registry-metadata",
            placements=build_trio_placements(),
            player_preset_id="paladin_level5_sample_trio",
        )
    )
    paladin = encounter.units["F1"]

    assert paladin.class_id == "paladin"
    assert paladin.level == 5
    assert paladin.loadout_id == "paladin_level5_sample_build"
    assert paladin.behavior_profile == "divine_guardian"
    assert paladin.role_tags == ["healer"]
    assert paladin.max_hp == 49
    assert paladin.ac == 21
    assert paladin.ability_mods.str == 4
    assert tuple(sorted(paladin.attacks.keys())) == ("javelin", "longsword")
    assert paladin.attacks["longsword"].attack_bonus == 7
    assert paladin.attacks["longsword"].damage_modifier == 4
    assert paladin.attacks["javelin"].attack_bonus == 7
    assert paladin.attacks["javelin"].damage_modifier == 4
    assert paladin.resources.lay_on_hands_points == 25
    assert paladin.resources.spell_slots_level_1 == 4
    assert paladin.resources.spell_slots_level_2 == 2
    assert paladin.resources.channel_divinity_uses == 2
    assert paladin.prepared_combat_spell_ids == ["bless", "cure_wounds", "aid"]
    assert paladin.prepared_spells == 6
    for feature_id in (
        "fighting_style_defense",
        "paladins_smite",
        "channel_divinity",
        "oath_of_the_ancients",
        "natures_wrath",
        "oath_spells_ancients",
        "sentinel",
        "extra_attack",
        "faithful_steed",
    ):
        assert feature_id in paladin.feature_ids
    assert unit_has_granted_action(paladin, "natures_wrath") is True
    assert paladin.resource_pools == {
        "lay_on_hands": 25,
        "spell_slots_level_1": 4,
        "spell_slots_level_2": 2,
        "channel_divinity": 2,
        "javelins": 5,
    }


def test_runtime_player_metadata_stays_out_of_live_api_payload() -> None:
    encounter = create_encounter(EncounterConfig(seed="player-registry-transport", placements=DEFAULT_POSITIONS))
    fighter = encounter.units["F1"]
    payload = fighter.model_dump(by_alias=True)

    assert fighter.combat_skill_modifiers == {}
    assert "classId" not in payload
    assert "level" not in payload
    assert "loadoutId" not in payload
    assert "featureIds" not in payload
    assert "resourcePools" not in payload
    assert "behaviorProfile" not in payload
    assert "combatSkillModifiers" not in payload
    assert "combatCantripIds" not in payload
    assert "preparedCombatSpellIds" not in payload
    assert "cantripsKnown" not in payload
    assert "spellbookSpells" not in payload
    assert "preparedSpells" not in payload


def test_current_fighter_attack_action_resolves_extra_attack_through_progression_metadata() -> None:
    encounter = create_encounter(EncounterConfig(seed="player-attack-action", placements=DEFAULT_POSITIONS))
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 2
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("flail", "greatsword", "javelin")
    assert tuple(sorted(attack_action.steps[1].allowed_weapon_ids)) == ("flail", "greatsword", "javelin")


def test_level2_fighter_still_gets_one_attack_per_attack_action() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="fighter-level2-attack-action",
            placements=build_trio_placements(),
            player_preset_id="fighter_level2_sample_trio",
        )
    )
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 1


def test_monk_attack_action_uses_shortsword_and_unarmed_strike_choices() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="monk-attack-action",
            placements=build_trio_placements(),
            player_preset_id="monk_sample_trio",
        )
    )
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 1
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("shortsword", "unarmed_strike")


def test_wizard_attack_action_uses_dagger_fallback_choice() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="wizard-attack-action",
            placements=build_trio_placements(),
            player_preset_id="wizard_sample_trio",
        )
    )
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 1
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("dagger",)


def test_paladin_attack_action_uses_longsword_and_javelin_choices() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-attack-action",
            placements=build_trio_placements(),
            player_preset_id="paladin_level1_sample_trio",
        )
    )
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 1
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("javelin", "longsword")


def test_level5_paladin_attack_action_resolves_extra_attack_through_progression_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="paladin-level5-attack-action",
            placements=build_trio_placements(),
            player_preset_id="paladin_level5_sample_trio",
        )
    )
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 2
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("javelin", "longsword")
    assert tuple(sorted(attack_action.steps[1].allowed_weapon_ids)) == ("javelin", "longsword")


def test_player_catalog_reports_current_supported_sample_party() -> None:
    catalog = get_player_catalog()

    assert catalog.default_player_preset_id == "martial_mixed_party"
    assert [entry.id for entry in catalog.classes] == ["barbarian", "fighter", "monk", "paladin", "rogue", "wizard"]
    assert [entry.id for entry in catalog.loadouts] == [
        "barbarian_sample_build",
        "barbarian_level2_sample_build",
        "fighter_sample_build",
        "fighter_level2_benchmark_tank",
        "fighter_level2_sample_build",
        "fighter_level3_sample_build",
        "fighter_level4_sample_build",
        "fighter_level5_sample_build",
        "monk_sample_build",
        "monk_level2_sample_build",
        "paladin_level1_sample_build",
        "paladin_level2_sample_build",
        "paladin_level3_sample_build",
        "paladin_level4_sample_build",
        "paladin_level5_sample_build",
        "rogue_melee_sample_build",
        "rogue_ranged_sample_build",
        "rogue_melee_level2_sample_build",
        "rogue_ranged_level2_benchmark_archer",
        "rogue_ranged_level2_sample_build",
        "rogue_ranged_level3_assassin_sample_build",
        "rogue_ranged_level4_assassin_sample_build",
        "rogue_ranged_level5_assassin_sample_build",
        "wizard_sample_build",
        "wizard_level2_sample_build",
        "wizard_level3_evoker_sample_build",
        "wizard_level4_evoker_sample_build",
        "wizard_level5_evoker_sample_build",
    ]
    assert [entry.id for entry in catalog.player_presets] == [
        "fighter_sample_trio",
        "fighter_level2_sample_trio",
        "fighter_level3_sample_trio",
        "fighter_level4_sample_trio",
        "fighter_level5_sample_trio",
        "rogue_ranged_trio",
        "rogue_melee_trio",
        "rogue_level2_ranged_trio",
        "rogue_level2_melee_trio",
        "rogue_level3_ranged_assassin_trio",
        "rogue_level4_ranged_assassin_trio",
        "rogue_level5_ranged_assassin_trio",
        "barbarian_sample_trio",
        "barbarian_level2_sample_trio",
        "monk_sample_trio",
        "monk_level2_sample_trio",
        "paladin_level1_sample_trio",
        "paladin_level2_sample_trio",
        "paladin_level3_sample_trio",
        "paladin_level4_sample_trio",
        "paladin_level5_sample_trio",
        "wizard_sample_trio",
        "wizard_level2_sample_trio",
        "wizard_level3_evoker_sample_trio",
        "wizard_level4_evoker_sample_trio",
        "wizard_level5_evoker_sample_trio",
        "martial_mixed_party",
    ]
    assert {entry.id: entry.max_supported_level for entry in catalog.classes} == {
        "barbarian": 2,
        "fighter": 5,
        "monk": 2,
        "paladin": 5,
        "rogue": 5,
        "wizard": 5,
    }


def test_default_player_preset_loads_fighter_paladin_rogue_and_wizard() -> None:
    encounter = create_encounter(EncounterConfig(seed="default-mixed-party", enemy_preset_id="goblin_screen"))

    assert encounter.units["F1"].loadout_id == "fighter_level5_sample_build"
    assert encounter.units["F1"].level == 5
    assert encounter.units["F2"].loadout_id == "paladin_level5_sample_build"
    assert encounter.units["F2"].level == 5
    assert encounter.units["F2"].ac == 21
    assert encounter.units["F2"].max_hp == 54
    assert encounter.units["F2"].current_hp == 54
    assert encounter.units["F2"].resources.lay_on_hands_points == 25
    assert encounter.units["F2"].resources.spell_slots_level_1 == 4
    assert encounter.units["F2"].resources.spell_slots_level_2 == 1
    assert encounter.units["F2"].resources.channel_divinity_uses == 2
    assert encounter.units["F3"].loadout_id == "rogue_ranged_level5_assassin_sample_build"
    assert encounter.units["F3"].level == 5
    assert encounter.units["F3"].max_hp == 42
    assert encounter.units["F4"].loadout_id == "wizard_level5_evoker_sample_build"
    assert encounter.units["F4"].level == 5
    assert encounter.units["F4"].class_id == "wizard"
    assert encounter.units["F4"].ac == 15
    assert encounter.units["F4"].max_hp == 37
    assert encounter.units["F4"].current_hp == 37
    assert encounter.units["F4"].resources.spell_slots_level_1 == 3
    assert encounter.units["F4"].resources.spell_slots_level_2 == 3
    assert encounter.units["F4"].resources.spell_slots_level_3 == 2
    assert encounter.units["F4"].position.model_dump() == {"x": 1, "y": 10}
    assert sum(encounter.units[unit_id].max_hp for unit_id in ("F1", "F2", "F3", "F4")) == 183
    for unit_id in ("F1", "F2", "F4"):
        assert any(
            isinstance(effect, AidEffect) and effect.source_id == "F2" and effect.hp_bonus == 5
            for effect in encounter.units[unit_id].temporary_effects
        )
    assert not any(isinstance(effect, AidEffect) for effect in encounter.units["F3"].temporary_effects)


def test_barbarian_attack_action_uses_greataxe_and_handaxe_choices() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="barbarian-attack-action",
            placements=build_trio_placements(),
            player_preset_id="barbarian_sample_trio",
        )
    )
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 1
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("greataxe", "handaxe")


def test_player_preset_selection_changes_loaded_party_builds() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-party",
            placements=build_trio_placements(),
            player_preset_id="rogue_melee_trio",
        )
    )

    rogue = encounter.units["F1"]
    assert rogue.class_id == "rogue"
    assert rogue.loadout_id == "rogue_melee_sample_build"
    assert rogue.template_name == "Level 1 Melee Rogue Sample Build"
    assert rogue.resources.second_wind_uses == 0
    assert rogue.resources.javelins == 0
    assert rogue.resources.rage_uses == 0
    assert rogue.resources.handaxes == 0
    assert "sneak_attack" in rogue.feature_ids
    assert "expertise_stealth" in rogue.feature_ids
    assert "weapon_mastery" in rogue.feature_ids
    assert "weapon_mastery_vex" in rogue.feature_ids
    assert rogue.attacks["rapier"].mastery == "vex"
    assert rogue.attacks["shortbow"].mastery is None
    assert rogue.combat_skill_modifiers == {"stealth": 7}


def test_level2_rogue_ranged_build_uses_cunning_action_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-ranged-metadata",
            placements=build_trio_placements(),
            player_preset_id="rogue_level2_ranged_trio",
        )
    )

    rogue = encounter.units["F1"]
    assert rogue.class_id == "rogue"
    assert rogue.level == 2
    assert rogue.loadout_id == "rogue_ranged_level2_sample_build"
    assert rogue.template_name == "Level 2 Ranged Rogue Sample Build"
    assert "sneak_attack" in rogue.feature_ids
    assert "expertise_stealth" in rogue.feature_ids
    assert "weapon_mastery" in rogue.feature_ids
    assert "weapon_mastery_vex" in rogue.feature_ids
    assert "cunning_action" in rogue.feature_ids
    assert rogue.attacks["shortbow"].mastery == "vex"
    assert rogue.combat_skill_modifiers == {"stealth": 7}


def test_level2_rogue_melee_build_uses_cunning_action_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level2-melee-metadata",
            placements=build_trio_placements(),
            player_preset_id="rogue_level2_melee_trio",
        )
    )

    rogue = encounter.units["F1"]
    assert rogue.class_id == "rogue"
    assert rogue.level == 2
    assert rogue.loadout_id == "rogue_melee_level2_sample_build"
    assert rogue.template_name == "Level 2 Melee Rogue Sample Build"
    assert "sneak_attack" in rogue.feature_ids
    assert "expertise_stealth" in rogue.feature_ids
    assert "weapon_mastery" in rogue.feature_ids
    assert "weapon_mastery_vex" in rogue.feature_ids
    assert "cunning_action" in rogue.feature_ids
    assert rogue.attacks["rapier"].mastery == "vex"
    assert rogue.attacks["shortbow"].mastery is None


def test_level3_ranged_assassin_rogue_build_uses_assassin_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-assassin-metadata",
            placements=build_trio_placements(),
            player_preset_id="rogue_level3_ranged_assassin_trio",
        )
    )

    rogue = encounter.units["F1"]
    assert rogue.class_id == "rogue"
    assert rogue.level == 3
    assert rogue.loadout_id == "rogue_ranged_level3_assassin_sample_build"
    assert rogue.template_name == "Level 3 Ranged Assassin Rogue Sample Build"
    assert rogue.max_hp == 26
    assert rogue.ac == 15
    assert tuple(sorted(rogue.attacks.keys())) == ("shortbow", "shortsword")
    assert "sneak_attack" in rogue.feature_ids
    assert "expertise_stealth" in rogue.feature_ids
    assert "weapon_mastery" in rogue.feature_ids
    assert "weapon_mastery_vex" in rogue.feature_ids
    assert "cunning_action" in rogue.feature_ids
    assert "steady_aim" in rogue.feature_ids
    assert "assassinate" in rogue.feature_ids
    assert "assassin_tools" in rogue.feature_ids
    assert rogue.attacks["shortbow"].mastery == "vex"
    assert unit_has_granted_bonus_action(rogue, "steady_aim") is True
    assert rogue.combat_skill_modifiers == {"stealth": 7}


def test_level4_ranged_assassin_rogue_build_uses_sharpshooter_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level4-assassin-metadata",
            placements=build_trio_placements(),
            player_preset_id="rogue_level4_ranged_assassin_trio",
        )
    )

    rogue = encounter.units["F1"]
    assert rogue.class_id == "rogue"
    assert rogue.level == 4
    assert rogue.loadout_id == "rogue_ranged_level4_assassin_sample_build"
    assert rogue.template_name == "Level 4 Ranged Assassin Rogue Sample Build"
    assert rogue.max_hp == 34
    assert rogue.ac == 16
    assert rogue.ability_mods.dex == 4
    assert rogue.initiative_mod == 4
    assert rogue.attacks["shortbow"].attack_bonus == 6
    assert rogue.attacks["shortbow"].damage_modifier == 4
    assert rogue.attacks["shortsword"].attack_bonus == 6
    assert rogue.attacks["shortsword"].damage_modifier == 4
    assert "sneak_attack" in rogue.feature_ids
    assert "expertise_stealth" in rogue.feature_ids
    assert "weapon_mastery" in rogue.feature_ids
    assert "weapon_mastery_vex" in rogue.feature_ids
    assert "cunning_action" in rogue.feature_ids
    assert "steady_aim" in rogue.feature_ids
    assert "assassinate" in rogue.feature_ids
    assert "assassin_tools" in rogue.feature_ids
    assert "sharpshooter" in rogue.feature_ids
    assert rogue.attacks["shortbow"].mastery == "vex"
    assert rogue.combat_skill_modifiers == {"stealth": 8}


def test_level5_ranged_assassin_rogue_build_uses_cunning_strike_and_uncanny_dodge_metadata() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level5-assassin-metadata",
            placements=build_trio_placements(),
            player_preset_id="rogue_level5_ranged_assassin_trio",
        )
    )

    rogue = encounter.units["F1"]
    assert rogue.class_id == "rogue"
    assert rogue.level == 5
    assert rogue.loadout_id == "rogue_ranged_level5_assassin_sample_build"
    assert rogue.template_name == "Level 5 Ranged Assassin Rogue Sample Build"
    assert rogue.max_hp == 42
    assert rogue.ac == 16
    assert rogue.ability_mods.dex == 4
    assert rogue.initiative_mod == 4
    assert rogue.attacks["shortbow"].attack_bonus == 7
    assert rogue.attacks["shortbow"].damage_modifier == 4
    assert rogue.attacks["shortsword"].attack_bonus == 7
    assert rogue.attacks["shortsword"].damage_modifier == 4
    assert "sneak_attack" in rogue.feature_ids
    assert "expertise_stealth" in rogue.feature_ids
    assert "weapon_mastery" in rogue.feature_ids
    assert "weapon_mastery_vex" in rogue.feature_ids
    assert "cunning_action" in rogue.feature_ids
    assert "steady_aim" in rogue.feature_ids
    assert "assassinate" in rogue.feature_ids
    assert "assassin_tools" in rogue.feature_ids
    assert "sharpshooter" in rogue.feature_ids
    assert "cunning_strike" in rogue.feature_ids
    assert "uncanny_dodge" in rogue.feature_ids
    assert rogue.attacks["shortbow"].mastery == "vex"
    assert unit_has_granted_cunning_strike(rogue, "poison") is True
    assert unit_has_granted_cunning_strike(rogue, "trip") is True
    assert unit_has_granted_cunning_strike(rogue, "withdraw") is True
    assert rogue.combat_skill_modifiers == {"stealth": 10}


def test_proficiency_bonus_scales_with_level_breakpoints() -> None:
    assert get_proficiency_bonus(1) == 2
    assert get_proficiency_bonus(4) == 2
    assert get_proficiency_bonus(5) == 3
    assert get_proficiency_bonus(9) == 4


def test_rapier_can_apply_sneak_attack_with_adjacent_ally() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-rapier-sneak-attack",
            placements=build_trio_placements(
                F1=GridPosition(x=2, y=1),
                F2=GridPosition(x=3, y=2),
                G1=GridPosition(x=3, y=1),
            ),
            player_preset_id="rogue_melee_trio",
        )
    )

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="G1",
            weapon_id="rapier",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
        ),
    )

    assert any(component.damage_type == "precision" for component in attack_event.damage_details.damage_components)


def test_shortbow_can_apply_sneak_attack_with_adjacent_ally() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-shortbow-sneak-attack",
            placements=build_trio_placements(),
            player_preset_id="rogue_ranged_trio",
        )
    )

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="G1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4, 3]),
        ),
    )

    assert any(component.damage_type == "precision" for component in attack_event.damage_details.damage_components)


def test_level3_rogue_shortbow_sneak_attack_rolls_two_d6() -> None:
    encounter = create_encounter(
        EncounterConfig(
            seed="rogue-level3-shortbow-sneak-attack",
            placements=build_trio_placements(),
            player_preset_id="rogue_level3_ranged_assassin_trio",
        )
    )
    encounter.round = 2

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="F1",
            target_id="G1",
            weapon_id="shortbow",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[4]),
        ),
    )

    sneak_component = next(
        component for component in attack_event.damage_details.damage_components if component.damage_type == "precision"
    )

    assert len(sneak_component.raw_rolls) == 2
