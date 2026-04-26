from __future__ import annotations

from backend.engine import run_encounter
from backend.content.scenario_definitions import get_scenario_definition
from backend.engine.models.state import EncounterConfig
from backend.engine.services.scenario_audit import (
    ScenarioAuditConfig,
    audit_scenario,
    build_full_scenario_audit_config,
    build_quick_scenario_audit_config,
    build_report_payload,
    build_simple_suggestion,
    get_active_scenario_ids,
    has_swallow_action,
)


def test_active_scenario_ids_exclude_giant_toad_solo() -> None:
    assert get_active_scenario_ids() == (
        "goblin_screen",
        "bandit_ambush",
        "mixed_patrol",
        "orc_push",
        "wolf_harriers",
        "marsh_predators",
        "hobgoblin_kill_box",
        "predator_rampage",
        "bugbear_dragnet",
        "deadwatch_phalanx",
        "captains_crossfire",
    )
    assert "giant_toad_solo" not in get_active_scenario_ids()


def test_simple_suggestion_rules_are_scenario_specific() -> None:
    assert build_simple_suggestion("goblin_screen", 0.95, 0.05) == "Move the enemy front line 1 square closer."
    assert build_simple_suggestion("marsh_predators", 0.95, 0.05) == (
        "Move the crocodile cluster 1 square closer before changing monster counts or stats."
    )
    assert build_simple_suggestion("deadwatch_phalanx", 0.91, 0.09) is None
    assert build_simple_suggestion("deadwatch_phalanx", 0.09, 0.91) is None
    assert build_simple_suggestion("goblin_screen", 0.05, 0.95) == (
        "Move the enemy front line 1 square back, or spread the back line by 1 square."
    )
    assert build_simple_suggestion("marsh_predators", 0.05, 0.95) == (
        "Move one crocodile 1 square back before changing composition."
    )
    assert build_simple_suggestion("deadwatch_phalanx", 0.93, 0.07) == "Move the enemy front line 1 square closer."
    assert build_simple_suggestion("deadwatch_phalanx", 0.07, 0.93) == (
        "Move the enemy front line 1 square back, or spread the back line by 1 square."
    )


def test_audit_profiles_expose_quick_and_full_defaults() -> None:
    quick_config = build_quick_scenario_audit_config()
    full_config = build_full_scenario_audit_config()

    assert quick_config == ScenarioAuditConfig(
        smart_smoke_runs=3,
        dumb_smoke_runs=3,
        mechanic_runs=25,
        health_batch_size=250,
        seed_prefix="scenario-audit",
    )
    assert full_config == ScenarioAuditConfig()


def test_audit_scenario_returns_report_shape_for_active_preset() -> None:
    row = audit_scenario(
        "goblin_screen",
        ScenarioAuditConfig(
            smart_smoke_runs=1,
            dumb_smoke_runs=1,
            mechanic_runs=1,
            health_batch_size=1,
            seed_prefix="test-audit",
        ),
    )

    payload = row.to_report_dict()

    assert row.scenario_id == "goblin_screen"
    assert row.unit_count == 12
    assert {
        "scenarioId",
        "displayName",
        "unitCount",
        "combinedPlayerWinRate",
        "combinedEnemyWinRate",
        "smartPlayerWinRate",
        "dumbPlayerWinRate",
        "kindPlayerWinRate",
        "balancedPlayerWinRate",
        "evilPlayerWinRate",
        "averageRounds",
        "signatureMechanicCount",
        "status",
        "simpleSuggestion",
        "warnings",
        "signatureBreakdown",
    }.issubset(payload.keys())


def test_build_report_payload_lists_only_active_scenarios() -> None:
    row = audit_scenario(
        "marsh_predators",
        ScenarioAuditConfig(
            smart_smoke_runs=1,
            dumb_smoke_runs=1,
            mechanic_runs=1,
            health_batch_size=1,
            seed_prefix="test-marsh-audit",
        ),
    )

    payload = build_report_payload([row], ScenarioAuditConfig())

    assert payload["activeScenarioIds"] == list(get_active_scenario_ids())
    assert payload["rows"][0]["scenarioId"] == "marsh_predators"
    assert "giant_toad_solo" not in payload["activeScenarioIds"]


def test_has_swallow_action_detects_logged_toad_swallow() -> None:
    result = run_encounter(EncounterConfig(seed="swallow-smart-059", enemy_preset_id="giant_toad_solo"))

    assert has_swallow_action(result) is True


def test_reaction_bastion_scenario_definition_is_staged_with_expected_expectations() -> None:
    definition = get_scenario_definition("reaction_bastion")

    assert definition.display_name == "Reaction Bastion"
    assert definition.enemy_preset_id == "reaction_bastion"
    assert definition.audit_expectation_ids == (
        "elite_line_holder_multiattack",
        "parry_reaction",
        "scout_multiattack",
    )


def test_audit_scenario_supports_staged_reaction_bastion() -> None:
    row = audit_scenario(
        "reaction_bastion",
        ScenarioAuditConfig(
            smart_smoke_runs=1,
            dumb_smoke_runs=1,
            mechanic_runs=1,
            health_batch_size=1,
            seed_prefix="test-reaction-bastion-audit",
        ),
    )

    payload = row.to_report_dict()

    assert row.scenario_id == "reaction_bastion"
    assert row.unit_count == 11
    assert payload["scenarioId"] == "reaction_bastion"
    assert set(payload["signatureBreakdown"]) == {
        "eliteLineHolderMultiattack",
        "parryReaction",
        "scoutMultiattack",
    }


def test_skyhunter_pincer_scenario_definition_is_staged_with_expected_expectations() -> None:
    definition = get_scenario_definition("skyhunter_pincer")

    assert definition.display_name == "Skyhunter Pincer"
    assert definition.enemy_preset_id == "skyhunter_pincer"
    assert definition.audit_expectation_ids == (
        "griffon_opening_landing",
        "griffon_grapple",
        "centaur_multiattack",
        "scout_multiattack",
    )


def test_audit_scenario_supports_staged_skyhunter_pincer() -> None:
    row = audit_scenario(
        "skyhunter_pincer",
        ScenarioAuditConfig(
            smart_smoke_runs=1,
            dumb_smoke_runs=1,
            mechanic_runs=1,
            health_batch_size=1,
            seed_prefix="test-skyhunter-pincer-audit",
        ),
    )

    payload = row.to_report_dict()

    assert row.scenario_id == "skyhunter_pincer"
    assert row.unit_count == 11
    assert payload["scenarioId"] == "skyhunter_pincer"
    assert set(payload["signatureBreakdown"]) == {
        "griffonOpeningLanding",
        "griffonGrapple",
        "centaurMultiattack",
        "scoutMultiattack",
    }
