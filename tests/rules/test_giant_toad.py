from __future__ import annotations

from backend.engine import create_encounter, run_encounter
from backend.engine.combat.engine import (
    apply_start_of_turn_ongoing_effects,
    resolve_attack_action,
    resolve_special_action,
)
from backend.engine.models.state import (
    BlindedEffect,
    EncounterConfig,
    Footprint,
    GrappledEffect,
    GridPosition,
    RestrainedEffect,
    SwallowedEffect,
)
from backend.engine.rules.combat_rules import AttackRollOverrides, ResolveAttackArgs, resolve_attack
from backend.engine.rules.spatial import (
    build_position_index,
    get_attack_context,
    get_min_chebyshev_distance_between_footprints,
    get_occupant_at,
    inspect_placements_for_unit_ids,
    path_provokes_opportunity_attack,
)
from tests.rules.action_assertions import assert_attack_action_core


def place_toad_within_swallow_reach(encounter) -> None:
    encounter.units["E1"].position = GridPosition(x=3, y=7)
    encounter.units["F1"].position = GridPosition(x=1, y=7)


def test_giant_toad_preset_uses_true_large_footprint() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-preset", enemy_preset_id="giant_toad_solo"))
    toad = encounter.units["E1"]
    position_index = build_position_index(encounter)

    assert toad.combat_role == "giant_toad"
    assert toad.footprint.model_dump() == {"width": 2, "height": 2}
    assert toad.position.model_dump() == {"x": 10, "y": 7}
    assert get_occupant_at(encounter, GridPosition(x=10, y=7), position_index=position_index) == toad
    assert get_occupant_at(encounter, GridPosition(x=11, y=7), position_index=position_index) == toad
    assert get_occupant_at(encounter, GridPosition(x=10, y=8), position_index=position_index) == toad
    assert get_occupant_at(encounter, GridPosition(x=11, y=8), position_index=position_index) == toad


def test_large_footprint_validation_rejects_overlap() -> None:
    validation = inspect_placements_for_unit_ids(
        {"F1": GridPosition(x=10, y=7), "E1": GridPosition(x=10, y=7)},
        ["F1", "E1"],
        {"F1": Footprint(width=1, height=1), "E1": Footprint(width=2, height=2)},
    )

    assert validation.is_valid is False
    assert validation.overlapping_groups


def test_giant_toad_bite_logs_split_damage_and_applies_grappled_restrained() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-bite", enemy_preset_id="giant_toad_solo"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=8, y=5)

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E1",
            target_id="F1",
            weapon_id="toad_bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[16], damage_rolls=[4, 5]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.damage_details.total_damage == 11
    assert [component.damage_type for component in attack_event.damage_details.damage_components] == [
        "piercing",
        "poison",
    ]
    assert any(effect.kind == "grappled_by" and effect.source_id == "E1" and effect.escape_dc == 13 for effect in encounter.units["F1"].temporary_effects)
    assert any(effect.kind == "restrained_by" and effect.source_id == "E1" and effect.escape_dc == 13 for effect in encounter.units["F1"].temporary_effects)


def test_swallow_removes_target_from_board_and_ongoing_acid_triggers() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-swallow", enemy_preset_id="giant_toad_solo"))
    place_toad_within_swallow_reach(encounter)
    encounter.units["F1"].temporary_effects.extend(
        [
            GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=13),
            RestrainedEffect(kind="restrained_by", source_id="E1", escape_dc=13),
        ]
    )

    swallow_event = resolve_special_action(
        encounter,
        "E1",
        {"kind": "special_action", "action_id": "swallow", "target_id": "F1"},
    )

    assert swallow_event.text_summary == "E1 swallows F1."
    assert encounter.units["F1"].position is None
    assert get_occupant_at(encounter, GridPosition(x=1, y=7), position_index=build_position_index(encounter)) is None

    acid_events = apply_start_of_turn_ongoing_effects(encounter, "E1")

    assert len(acid_events) == 1
    assert acid_events[0].event_type == "ongoing_damage"
    assert acid_events[0].target_ids == ["F1"]


def test_swallow_clears_external_grapples_and_restraints() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-external-grapple", enemy_preset_id="marsh_predators"))
    place_toad_within_swallow_reach(encounter)
    encounter.units["F1"].temporary_effects.extend(
        [
            GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=13),
            RestrainedEffect(kind="restrained_by", source_id="E1", escape_dc=13),
            GrappledEffect(kind="grappled_by", source_id="E2", escape_dc=12),
            RestrainedEffect(kind="restrained_by", source_id="E2", escape_dc=12),
        ]
    )

    swallow_event = resolve_special_action(
        encounter,
        "E1",
        {"kind": "special_action", "action_id": "swallow", "target_id": "F1"},
    )

    assert "F1 is no longer grappled by E2." in swallow_event.condition_deltas
    assert "F1 is no longer restrained by E2." in swallow_event.condition_deltas
    assert all(
        not (effect.kind == "grappled_by" and effect.source_id == "E2") for effect in encounter.units["F1"].temporary_effects
    )
    assert all(
        not (effect.kind == "restrained_by" and effect.source_id == "E2")
        for effect in encounter.units["F1"].temporary_effects
    )
    assert any(effect.kind == "swallowed_by" and effect.source_id == "E1" for effect in encounter.units["F1"].temporary_effects)
    assert any(effect.kind == "blinded_by" and effect.source_id == "E1" for effect in encounter.units["F1"].temporary_effects)


def test_swallowed_fighter_targets_only_swallowing_toad() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-swallowed-ai", enemy_preset_id="giant_toad_solo"))
    fighter = encounter.units["F1"]
    fighter.current_hp = 6
    fighter.position = None
    fighter.temporary_effects.extend(
        [
            GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=13),
            RestrainedEffect(kind="restrained_by", source_id="E1", escape_dc=13),
            BlindedEffect(kind="blinded_by", source_id="E1"),
            SwallowedEffect(kind="swallowed_by", source_id="E1"),
        ]
    )

    from backend.engine.ai.decision import choose_turn_decision

    decision = choose_turn_decision(encounter, "F1")
    context_against_toad = get_attack_context(encounter, "F1", "E1", fighter.attacks["greatsword"])
    context_against_other = get_attack_context(encounter, "F1", "E1", fighter.attacks["javelin"])

    assert_attack_action_core(decision.action, target_id="E1", weapon_id="greatsword")
    assert decision.bonus_action == {"kind": "second_wind", "timing": "before_action"}
    assert context_against_toad.legal is True
    assert context_against_other.legal is False


def test_toad_death_releases_swallowed_fighter_adjacent_and_prone() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-release", enemy_preset_id="giant_toad_solo"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].current_hp = 1
    encounter.units["F1"].position = None
    encounter.units["F1"].temporary_effects.extend(
        [
            GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=13),
            RestrainedEffect(kind="restrained_by", source_id="E1", escape_dc=13),
            BlindedEffect(kind="blinded_by", source_id="E1"),
            SwallowedEffect(kind="swallowed_by", source_id="E1"),
        ]
    )
    encounter.units["F2"].position = GridPosition(x=7, y=5)

    events = resolve_attack_action(
        encounter,
        "F2",
        {"kind": "attack", "target_id": "E1", "weapon_id": "greatsword"},
        step_overrides=[AttackRollOverrides(attack_rolls=[19], damage_rolls=[6, 6])],
    )

    release_event = next(event for event in events if "releases F1" in event.text_summary)

    assert release_event.event_type == "phase_change"
    assert encounter.units["F1"].position is not None
    assert encounter.units["F1"].conditions.prone is True
    assert get_min_chebyshev_distance_between_footprints(
        encounter.units["F1"].position,
        encounter.units["F1"].footprint,
        encounter.units["E1"].position,
        encounter.units["E1"].footprint,
    ) == 1
    assert all(effect.kind != "swallowed_by" for effect in encounter.units["F1"].temporary_effects)


def test_toad_reach_sets_opportunity_attack_threat_from_ten_feet() -> None:
    encounter = create_encounter(EncounterConfig(seed="giant-toad-reach-oa", enemy_preset_id="giant_toad_solo"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=8, y=5)

    assert path_provokes_opportunity_attack(
        encounter,
        "F1",
        [GridPosition(x=8, y=5), GridPosition(x=9, y=5)],
    ) is True


def test_fixed_seed_encounter_contains_swallow_and_acid_sequence() -> None:
    result = run_encounter(
        EncounterConfig(
            # Pin the older three-fighter party here so this rule test stays
            # focused on the toad sequence instead of shifting whenever the
            # default mixed party changes.
            seed="swallow-search-fighter_sample_trio-dumb-101",
            enemy_preset_id="giant_toad_solo",
            player_preset_id="fighter_sample_trio",
            player_behavior="dumb",
            monster_behavior="balanced",
        )
    )

    event_types = [event.event_type for event in result.events]
    text_summaries = [event.text_summary for event in result.events]

    assert "ongoing_damage" in event_types
    assert any("swallows" in summary for summary in text_summaries)
    assert any("releases" in summary for summary in text_summaries)
