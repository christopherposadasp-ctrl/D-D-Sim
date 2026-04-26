from __future__ import annotations

from backend.engine import create_encounter, run_encounter
from backend.engine.combat.engine import resolve_attack_action, step_encounter_without_history
from backend.engine.models.state import EncounterConfig, GrappledEffect, GridPosition
from backend.engine.rules.combat_rules import AttackRollOverrides, ResolveAttackArgs, resolve_attack
from backend.engine.rules.spatial import build_position_index, get_attack_context, get_occupant_at


def test_crocodile_preset_uses_true_large_footprint() -> None:
    encounter = create_encounter(EncounterConfig(seed="marsh-preset", enemy_preset_id="marsh_predators"))
    position_index = build_position_index(encounter)
    northwest_crocodile = encounter.units["E2"]
    northeast_crocodile = encounter.units["E3"]
    south_crocodile = encounter.units["E4"]
    second_toad = encounter.units["E5"]

    assert northwest_crocodile.combat_role == "crocodile"
    assert northwest_crocodile.footprint.model_dump() == {"width": 2, "height": 2}
    assert northwest_crocodile.position.model_dump() == {"x": 1, "y": 1}
    assert northeast_crocodile.position.model_dump() == {"x": 4, "y": 1}
    assert south_crocodile.position.model_dump() == {"x": 2, "y": 4}
    assert get_occupant_at(encounter, GridPosition(x=1, y=1), position_index=position_index) == northwest_crocodile
    assert get_occupant_at(encounter, GridPosition(x=2, y=1), position_index=position_index) == northwest_crocodile
    assert get_occupant_at(encounter, GridPosition(x=4, y=1), position_index=position_index) == northeast_crocodile
    assert get_occupant_at(encounter, GridPosition(x=5, y=2), position_index=position_index) == northeast_crocodile
    assert get_occupant_at(encounter, GridPosition(x=2, y=4), position_index=position_index) == south_crocodile
    assert get_occupant_at(encounter, GridPosition(x=3, y=5), position_index=position_index) == south_crocodile
    assert second_toad.combat_role == "giant_toad"
    assert second_toad.position.model_dump() == {"x": 9, "y": 10}


def test_crocodile_bite_damage_and_grapple_are_applied() -> None:
    encounter = create_encounter(EncounterConfig(seed="croc-bite", enemy_preset_id="marsh_predators"))
    encounter.units["E2"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)

    attack_event, _ = resolve_attack(
        encounter,
        ResolveAttackArgs(
            attacker_id="E2",
            target_id="F1",
            weapon_id="crocodile_bite",
            savage_attacker_available=False,
            overrides=AttackRollOverrides(attack_rolls=[15], damage_rolls=[6]),
        ),
    )

    assert attack_event.resolved_totals["hit"] is True
    assert attack_event.damage_details.total_damage == 8
    assert [component.damage_type for component in attack_event.damage_details.damage_components] == ["piercing"]
    assert any(effect.kind == "grappled_by" and effect.source_id == "E2" and effect.escape_dc == 12 for effect in encounter.units["F1"].temporary_effects)
    assert all(effect.kind != "restrained_by" for effect in encounter.units["F1"].temporary_effects)


def test_crocodile_bite_cannot_switch_targets_while_holding_someone() -> None:
    encounter = create_encounter(EncounterConfig(seed="croc-lock", enemy_preset_id="marsh_predators"))
    encounter.units["E2"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["F2"].position = GridPosition(x=7, y=6)
    encounter.units["F1"].temporary_effects.append(GrappledEffect(kind="grappled_by", source_id="E2", escape_dc=12))

    weapon = encounter.units["E2"].attacks["crocodile_bite"]
    same_target_context = get_attack_context(encounter, "E2", "F1", weapon)
    other_target_context = get_attack_context(encounter, "E2", "F2", weapon)

    assert same_target_context.legal is True
    assert other_target_context.legal is False


def test_crocodile_releases_downed_target_before_retargeting() -> None:
    encounter = create_encounter(EncounterConfig(seed="croc-release", enemy_preset_id="marsh_predators"))
    encounter.initiative_order = ["E2", "F1", "F2", "F3", "E1", "E3"]
    encounter.active_combatant_index = 0
    encounter.units["E2"].position = GridPosition(x=5, y=5)
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["F2"].position = GridPosition(x=8, y=6)
    encounter.units["F1"].current_hp = 0
    encounter.units["F1"].conditions.unconscious = True
    encounter.units["F1"].temporary_effects.append(GrappledEffect(kind="grappled_by", source_id="E2", escape_dc=12))

    result = step_encounter_without_history(encounter)

    assert any(event.resolved_totals.get("releaseReason") == "invalid_grapple" for event in result.events)
    assert all(not (effect.kind == "grappled_by" and effect.source_id == "E2") for effect in result.state.units["F1"].temporary_effects)
    assert any(event.event_type == "attack" and event.target_ids == ["F2"] for event in result.events)


def test_crocodile_death_releases_held_target() -> None:
    encounter = create_encounter(EncounterConfig(seed="croc-death-release", enemy_preset_id="marsh_predators"))
    encounter.units["E2"].position = GridPosition(x=5, y=5)
    encounter.units["E2"].current_hp = 1
    encounter.units["F1"].position = GridPosition(x=7, y=5)
    encounter.units["F2"].position = GridPosition(x=7, y=6)
    encounter.units["F1"].temporary_effects.append(GrappledEffect(kind="grappled_by", source_id="E2", escape_dc=12))

    events = resolve_attack_action(
        encounter,
        "F2",
        {"kind": "attack", "target_id": "E2", "weapon_id": "greatsword"},
        step_overrides=[AttackRollOverrides(attack_rolls=[19], damage_rolls=[6, 6])],
    )

    assert any("dies and releases F1" in event.text_summary for event in events)
    assert all(not (effect.kind == "grappled_by" and effect.source_id == "E2") for effect in encounter.units["F1"].temporary_effects)


def test_fixed_seed_marsh_predators_encounter_shows_crocodile_control_and_toad_presence() -> None:
    result = run_encounter(
        EncounterConfig(
            seed="marsh-dumb-005",
            enemy_preset_id="marsh_predators",
            player_behavior="dumb",
            monster_behavior="balanced",
        )
    )

    final_roles = {unit.combat_role for unit in result.final_state.units.values()}

    assert result.final_state.units["E2"].combat_role == "crocodile"
    assert "crocodile" in final_roles
    assert "giant_toad" in final_roles
    assert any(
        "is grappled by E2" in delta or "is grappled by E3" in delta or "is grappled by E4" in delta
        for event in result.events
        for delta in event.condition_deltas
    )
