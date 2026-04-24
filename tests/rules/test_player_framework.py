from __future__ import annotations

from backend.content.attack_sequences import build_player_attack_action
from backend.content.class_progressions import get_proficiency_bonus
from backend.engine import create_encounter
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import EncounterConfig, GridPosition
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
    assert fighter.level == 2
    assert fighter.loadout_id == "fighter_level2_sample_build"
    assert fighter.behavior_profile == "martial_striker"
    assert "second_wind" in fighter.feature_ids
    assert "action_surge" in fighter.feature_ids
    assert "savage_attacker" in fighter.feature_ids
    assert fighter.resource_pools == {"second_wind": 2, "action_surge": 1, "javelins": 8}
    assert fighter.resources.action_surge_uses == 1


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
    assert wizard.prepared_combat_spell_ids == ["magic_missile", "shield", "burning_hands"]
    assert wizard.cantrips_known == 3
    assert wizard.spellbook_spells == 6
    assert wizard.prepared_spells == 4
    assert "spellcasting" in wizard.feature_ids
    assert "ritual_adept" in wizard.feature_ids
    assert "arcane_recovery" in wizard.feature_ids
    assert wizard.resource_pools == {"spell_slots_level_1": 2}


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


def test_player_attack_action_resolves_through_progression_metadata() -> None:
    encounter = create_encounter(EncounterConfig(seed="player-attack-action", placements=DEFAULT_POSITIONS))
    attack_action = build_player_attack_action(encounter.units["F1"])

    assert attack_action.action_id == "attack"
    assert len(attack_action.steps) == 1
    assert tuple(sorted(attack_action.steps[0].allowed_weapon_ids)) == ("flail", "greatsword", "javelin")


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


def test_player_catalog_reports_current_supported_sample_party() -> None:
    catalog = get_player_catalog()

    assert catalog.default_player_preset_id == "martial_mixed_party"
    assert [entry.id for entry in catalog.classes] == ["barbarian", "fighter", "monk", "rogue", "wizard"]
    assert [entry.id for entry in catalog.loadouts] == [
        "barbarian_sample_build",
        "barbarian_level2_sample_build",
        "fighter_sample_build",
        "fighter_level2_benchmark_tank",
        "fighter_level2_sample_build",
        "monk_sample_build",
        "monk_level2_sample_build",
        "rogue_melee_sample_build",
        "rogue_ranged_sample_build",
        "rogue_melee_level2_sample_build",
        "rogue_ranged_level2_benchmark_archer",
        "rogue_ranged_level2_sample_build",
        "wizard_sample_build",
    ]
    assert [entry.id for entry in catalog.player_presets] == [
        "fighter_sample_trio",
        "fighter_level2_sample_trio",
        "rogue_ranged_trio",
        "rogue_melee_trio",
        "rogue_level2_ranged_trio",
        "rogue_level2_melee_trio",
        "barbarian_sample_trio",
        "barbarian_level2_sample_trio",
        "monk_sample_trio",
        "monk_level2_sample_trio",
        "wizard_sample_trio",
        "martial_mixed_party",
    ]
    assert {entry.id: entry.max_supported_level for entry in catalog.classes} == {
        "barbarian": 2,
        "fighter": 2,
        "monk": 2,
        "rogue": 2,
        "wizard": 1,
    }


def test_default_player_preset_loads_fighter_barbarian_and_two_rogues() -> None:
    encounter = create_encounter(EncounterConfig(seed="default-mixed-party", enemy_preset_id="goblin_screen"))

    assert encounter.units["F1"].loadout_id == "fighter_level2_sample_build"
    assert encounter.units["F1"].level == 2
    assert encounter.units["F2"].loadout_id == "barbarian_level2_sample_build"
    assert encounter.units["F2"].level == 2
    assert encounter.units["F3"].loadout_id == "rogue_ranged_level2_sample_build"
    assert encounter.units["F3"].level == 2
    assert encounter.units["F4"].loadout_id == "rogue_melee_level2_sample_build"
    assert encounter.units["F4"].level == 2
    assert encounter.units["F4"].position.model_dump() == {"x": 1, "y": 10}
    assert sum(encounter.units[unit_id].max_hp for unit_id in ("F1", "F2", "F3", "F4")) == 82


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
    assert "cunning_action" in rogue.feature_ids
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
    assert "cunning_action" in rogue.feature_ids


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
