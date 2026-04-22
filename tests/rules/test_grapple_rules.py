from __future__ import annotations

import pytest

from backend.engine import create_encounter
from backend.engine.ai.decision import choose_turn_decision, get_move_squares
from backend.engine.combat.engine import resolve_attack_action, step_encounter_without_history
from backend.engine.models.state import EncounterConfig, GrappledEffect, GridPosition, RestrainedEffect
from backend.engine.rules.spatial import get_active_grappled_target_ids, get_active_grappler_ids, is_active_grapple


def build_monster_benchmark_encounter(variant_id: str):
    return create_encounter(
        EncounterConfig(
            seed=f"grapple-rules-{variant_id}",
            enemy_preset_id=f"{variant_id}_benchmark",
            player_preset_id="monster_benchmark_duo",
            player_behavior="balanced",
            monster_behavior="balanced",
        )
    )


def defeat_other_units(encounter, *active_unit_ids: str) -> None:
    active_ids = set(active_unit_ids)
    for unit in encounter.units.values():
        if unit.id in active_ids:
            continue
        unit.current_hp = 0
        unit.conditions.dead = True


def test_valid_bugbear_grapple_stays_active_within_reach() -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].temporary_effects.append(
        GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=12, maintain_reach_feet=10)
    )

    assert is_active_grapple(encounter, "E1", "F1") is True
    assert get_active_grappled_target_ids(encounter, "E1") == ["F1"]
    assert get_active_grappler_ids(encounter, "F1") == ["E1"]


def test_distant_grapple_becomes_inactive_and_target_keeps_movement() -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=12, y=5)
    encounter.units["F1"].temporary_effects.append(
        GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=12, maintain_reach_feet=10)
    )

    assert is_active_grapple(encounter, "E1", "F1") is False
    assert get_active_grappler_ids(encounter, "F1") == []
    assert get_move_squares(encounter.units["F1"], encounter) > 0


@pytest.mark.parametrize(
    ("current_hp", "unconscious", "dead"),
    [
        (0, False, False),
        (33, True, False),
        (0, False, True),
    ],
)
def test_incapacitated_source_invalidates_grapple(current_hp: int, unconscious: bool, dead: bool) -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["E1"].current_hp = current_hp
    encounter.units["E1"].conditions.unconscious = unconscious
    encounter.units["E1"].conditions.dead = dead
    encounter.units["F1"].temporary_effects.append(
        GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=12, maintain_reach_feet=10)
    )

    assert is_active_grapple(encounter, "E1", "F1") is False


def test_turn_start_cleanup_removes_invalid_grapple_and_matching_restraint() -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=12, y=5)
    encounter.units["F1"].temporary_effects.extend(
        [
            GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=12, maintain_reach_feet=10),
            RestrainedEffect(kind="restrained_by", source_id="E1", escape_dc=12),
        ]
    )
    encounter.active_combatant_index = encounter.initiative_order.index("F1")

    result = step_encounter_without_history(encounter)

    assert any(event.resolved_totals.get("releaseReason") == "invalid_grapple" for event in result.events)
    assert all(effect.kind != "grappled_by" for effect in result.state.units["F1"].temporary_effects)
    assert all(effect.kind != "restrained_by" for effect in result.state.units["F1"].temporary_effects)


def test_resolve_attack_action_skips_when_no_first_attack_step_is_legal() -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=15, y=15)

    events = resolve_attack_action(encounter, "E1", {"kind": "attack", "target_id": "F1", "weapon_id": "light_hammer"})

    assert len(events) == 1
    assert events[0].event_type == "skip"
    assert events[0].resolved_totals["reason"] == "No legal attack target is available."


def test_bugbear_ai_does_not_commit_to_illegal_hammer_follow_up_on_stale_grapple() -> None:
    encounter = build_monster_benchmark_encounter("bugbear_warrior")
    defeat_other_units(encounter, "E1", "F1")
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=12, y=8)
    encounter.units["F1"].temporary_effects.append(
        GrappledEffect(kind="grappled_by", source_id="E1", escape_dc=12, maintain_reach_feet=10)
    )

    decision = choose_turn_decision(encounter, "E1")

    assert not (
        decision.action["kind"] == "attack"
        and decision.action.get("weapon_id") == "light_hammer"
        and decision.action.get("target_id") == "F1"
    )
