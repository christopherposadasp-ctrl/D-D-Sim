from __future__ import annotations

from dataclasses import dataclass

from backend.content.enemies import ACTIVE_ENEMY_PRESET_IDS, ENEMY_PRESETS


@dataclass(frozen=True)
class ScenarioDefinition:
    """Data-only scenario metadata that can stay stable as content grows."""

    scenario_id: str
    display_name: str
    description: str
    enemy_preset_id: str
    audit_expectation_ids: tuple[str, ...] = ()


SCENARIO_DEFINITIONS: dict[str, ScenarioDefinition] = {
    "goblin_screen": ScenarioDefinition(
        scenario_id="goblin_screen",
        display_name="Goblin Screen",
        description=ENEMY_PRESETS["goblin_screen"].description,
        enemy_preset_id="goblin_screen",
        audit_expectation_ids=("goblin_melee_engagement", "goblin_shortbow_attack"),
    ),
    "bandit_ambush": ScenarioDefinition(
        scenario_id="bandit_ambush",
        display_name="Bandit Ambush",
        description=ENEMY_PRESETS["bandit_ambush"].description,
        enemy_preset_id="bandit_ambush",
        audit_expectation_ids=("bandit_melee_attack", "bandit_shortbow_attack", "scout_multiattack"),
    ),
    "mixed_patrol": ScenarioDefinition(
        scenario_id="mixed_patrol",
        display_name="Mixed Patrol",
        description=ENEMY_PRESETS["mixed_patrol"].description,
        enemy_preset_id="mixed_patrol",
        audit_expectation_ids=("guard_spear_attack", "scout_multiattack", "goblin_ranged_support"),
    ),
    "orc_push": ScenarioDefinition(
        scenario_id="orc_push",
        display_name="Orc Push",
        description=ENEMY_PRESETS["orc_push"].description,
        enemy_preset_id="orc_push",
        audit_expectation_ids=("orc_greataxe_attack", "orc_early_advance"),
    ),
    "wolf_harriers": ScenarioDefinition(
        scenario_id="wolf_harriers",
        display_name="Wolf Harriers",
        description=ENEMY_PRESETS["wolf_harriers"].description,
        enemy_preset_id="wolf_harriers",
        audit_expectation_ids=("pack_tactics_attack", "prone_rider_applied"),
    ),
    "marsh_predators": ScenarioDefinition(
        scenario_id="marsh_predators",
        display_name="Marsh Predators",
        description=ENEMY_PRESETS["marsh_predators"].description,
        enemy_preset_id="marsh_predators",
        audit_expectation_ids=("crocodile_grapple", "toad_swallow"),
    ),
    "hobgoblin_kill_box": ScenarioDefinition(
        scenario_id="hobgoblin_kill_box",
        display_name="Hobgoblin Kill Box",
        description=ENEMY_PRESETS["hobgoblin_kill_box"].description,
        enemy_preset_id="hobgoblin_kill_box",
        audit_expectation_ids=("hobgoblin_longsword_attack", "hobgoblin_longbow_attack", "goblin_boss_multiattack"),
    ),
    "predator_rampage": ScenarioDefinition(
        scenario_id="predator_rampage",
        display_name="Predator Rampage",
        description=ENEMY_PRESETS["predator_rampage"].description,
        enemy_preset_id="predator_rampage",
        audit_expectation_ids=("dire_wolf_prone_rider", "worg_harry_target", "rampage_follow_up"),
    ),
    "bugbear_dragnet": ScenarioDefinition(
        scenario_id="bugbear_dragnet",
        display_name="Bugbear Dragnet",
        description=ENEMY_PRESETS["bugbear_dragnet"].description,
        enemy_preset_id="bugbear_dragnet",
        audit_expectation_ids=("bugbear_grapple", "goblin_boss_redirect_attack"),
    ),
    "deadwatch_phalanx": ScenarioDefinition(
        scenario_id="deadwatch_phalanx",
        display_name="Deadwatch Phalanx",
        description=ENEMY_PRESETS["deadwatch_phalanx"].description,
        enemy_preset_id="deadwatch_phalanx",
        audit_expectation_ids=("animated_armor_multiattack", "undead_fortitude_triggered"),
    ),
    "captains_crossfire": ScenarioDefinition(
        scenario_id="captains_crossfire",
        display_name="Captain's Crossfire",
        description=ENEMY_PRESETS["captains_crossfire"].description,
        enemy_preset_id="captains_crossfire",
        audit_expectation_ids=("bandit_captain_multiattack", "parry_reaction"),
    ),
    "reaction_bastion": ScenarioDefinition(
        scenario_id="reaction_bastion",
        display_name="Reaction Bastion",
        description=ENEMY_PRESETS["reaction_bastion"].description,
        enemy_preset_id="reaction_bastion",
        audit_expectation_ids=("elite_line_holder_multiattack", "parry_reaction", "scout_multiattack"),
    ),
    "skyhunter_pincer": ScenarioDefinition(
        scenario_id="skyhunter_pincer",
        display_name="Skyhunter Pincer",
        description=ENEMY_PRESETS["skyhunter_pincer"].description,
        enemy_preset_id="skyhunter_pincer",
        audit_expectation_ids=("griffon_opening_landing", "griffon_grapple", "centaur_multiattack", "scout_multiattack"),
    ),
    "hobgoblin_command_screen": ScenarioDefinition(
        scenario_id="hobgoblin_command_screen",
        display_name="Hobgoblin Command Screen",
        description=ENEMY_PRESETS["hobgoblin_command_screen"].description,
        enemy_preset_id="hobgoblin_command_screen",
        audit_expectation_ids=(
            "hobgoblin_captain_multiattack",
            "hobgoblin_captain_longbow_attack",
            "hobgoblin_longsword_attack",
            "hobgoblin_longbow_attack",
        ),
    ),
    "berserker_overrun": ScenarioDefinition(
        scenario_id="berserker_overrun",
        display_name="Berserker Overrun",
        description=ENEMY_PRESETS["berserker_overrun"].description,
        enemy_preset_id="berserker_overrun",
        audit_expectation_ids=(
            "berserker_greataxe_attack",
            "goblin_melee_engagement",
            "hobgoblin_captain_multiattack",
            "hobgoblin_captain_longbow_attack",
            "hobgoblin_longbow_attack",
        ),
    ),
    "frozen_courtyard_dragon_test": ScenarioDefinition(
        scenario_id="frozen_courtyard_dragon_test",
        display_name="Frozen Courtyard Dragon Test",
        description=ENEMY_PRESETS["frozen_courtyard_dragon_test"].description,
        enemy_preset_id="frozen_courtyard_dragon_test",
        audit_expectation_ids=(),
    ),
    "frozen_courtyard_kobold_opening": ScenarioDefinition(
        scenario_id="frozen_courtyard_kobold_opening",
        display_name="Frozen Courtyard Kobold Opening",
        description=ENEMY_PRESETS["frozen_courtyard_kobold_opening"].description,
        enemy_preset_id="frozen_courtyard_kobold_opening",
        audit_expectation_ids=(),
    ),
    "frostfall_courtyard": ScenarioDefinition(
        scenario_id="frostfall_courtyard",
        display_name="Frostfall Courtyard",
        description=ENEMY_PRESETS["frostfall_courtyard"].description,
        enemy_preset_id="frostfall_courtyard",
        audit_expectation_ids=(),
    ),
    "frostfall_courtyard_variant": ScenarioDefinition(
        scenario_id="frostfall_courtyard_variant",
        display_name="Frostfall Courtyard Variant",
        description=ENEMY_PRESETS["frostfall_courtyard_variant"].description,
        enemy_preset_id="frostfall_courtyard_variant",
        audit_expectation_ids=(),
    ),
}

ACTIVE_SCENARIO_IDS: tuple[str, ...] = ACTIVE_ENEMY_PRESET_IDS


def get_scenario_definition(scenario_id: str) -> ScenarioDefinition:
    try:
        return SCENARIO_DEFINITIONS[scenario_id]
    except KeyError as error:
        raise ValueError(f"Unknown scenario definition '{scenario_id}'.") from error


def get_active_scenario_definitions() -> list[ScenarioDefinition]:
    return [SCENARIO_DEFINITIONS[scenario_id] for scenario_id in ACTIVE_SCENARIO_IDS]
