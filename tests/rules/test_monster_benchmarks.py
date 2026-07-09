from __future__ import annotations

import pytest

from backend.content.enemies import get_enemy_preset
from backend.engine import create_encounter, run_batch, run_encounter, step_encounter
from backend.engine.models.state import EncounterConfig
from backend.engine.rules.spatial import GRID_SIZE, get_occupied_squares_for_position
from tests.rules.monster_expectations import MONSTER_EXPECTATIONS, REMAINING_MONSTER_IDS


def get_enemy_attack_events(events: list) -> list:
    return [event for event in events if event.event_type == "attack" and event.actor_id.startswith("E")]


def assert_primary_benchmark_behavior(variant_id: str, attack_events: list) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    weapon_ids = [event.damage_details.weapon_id for event in attack_events]

    if variant_id == "ogre":
        assert set(weapon_ids).issubset({"javelin_throw", "greatclub"})
        if "javelin_throw" in weapon_ids and "greatclub" in weapon_ids:
            assert weapon_ids.index("javelin_throw") < weapon_ids.index("greatclub")
        return

    if expectation.ai_profile_id == "ranged_skirmisher":
        assert attack_events[0].damage_details.weapon_id == expectation.opening_weapon_id
        if expectation.melee_fallback_weapon_id in weapon_ids:
            assert weapon_ids.index(expectation.opening_weapon_id) < weapon_ids.index(expectation.melee_fallback_weapon_id)
        return

    if variant_id == "brown_bear":
        assert attack_events[0].damage_details.weapon_id == "bite"
        assert "claw" in weapon_ids
        return

    if variant_id == "bugbear_warrior":
        assert attack_events[0].damage_details.weapon_id == "grab"
        assert set(weapon_ids).issubset({"grab", "light_hammer"})
        return

    assert set(weapon_ids) == {expectation.opening_weapon_id}
    if variant_id in {"warrior_infantry", "hyena", "giant_rat", "dire_wolf"}:
        assert any(event.resolved_totals.get("attackMode") == "advantage" for event in attack_events)


@pytest.mark.parametrize("variant_id", REMAINING_MONSTER_IDS)
def test_benchmark_presets_build_valid_layout_and_emit_first_step(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    encounter = create_encounter(
        EncounterConfig(
            seed=f"benchmark-structure-{variant_id}",
            enemy_preset_id=expectation.benchmark_preset_id,
            player_preset_id="monster_benchmark_duo",
        )
    )
    preset = get_enemy_preset(expectation.benchmark_preset_id)

    assert [unit.unit_id for unit in preset.units] == [f"E{index}" for index in range(1, expectation.benchmark_count + 1)]
    assert len(encounter.units) == 2 + expectation.benchmark_count
    assert encounter.terrain_features == []

    occupied_squares: set[tuple[int, int]] = set()
    for unit in encounter.units.values():
        for square in get_occupied_squares_for_position(unit.position, unit.footprint):
            assert 1 <= square.x <= GRID_SIZE
            assert 1 <= square.y <= GRID_SIZE
            key = (square.x, square.y)
            assert key not in occupied_squares
            occupied_squares.add(key)

    first_step = step_encounter(encounter)

    assert first_step.events


@pytest.mark.slow
@pytest.mark.parametrize("variant_id", REMAINING_MONSTER_IDS)
def test_monster_benchmark_batches_report_health_metrics(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]
    summary = run_batch(
        EncounterConfig(
            seed=f"benchmark-batch-{variant_id}",
            enemy_preset_id=expectation.benchmark_preset_id,
            player_preset_id="monster_benchmark_duo",
            player_behavior="balanced",
            monster_behavior="combined",
            batch_size=3,
        )
    )

    assert summary.total_runs == 9
    assert summary.combination_summaries is not None

    summaries_by_behavior = {
        combination_summary.monster_behavior: combination_summary for combination_summary in summary.combination_summaries
    }
    assert set(summaries_by_behavior) == {"kind", "balanced", "evil"}

    for behavior in ("kind", "balanced", "evil"):
        entry = summaries_by_behavior[behavior]
        print(
            f"{variant_id} {behavior}: "
            f"player_win_rate={entry.player_win_rate:.3f} "
            f"goblin_win_rate={entry.goblin_win_rate:.3f} "
            f"average_rounds={entry.average_rounds:.3f}"
        )
        assert 0 <= entry.player_win_rate <= 1
        assert 0 <= entry.goblin_win_rate <= 1
        assert 0 <= entry.mutual_annihilation_rate <= 1
        assert entry.average_rounds > 0


@pytest.mark.slow
@pytest.mark.parametrize("variant_id", REMAINING_MONSTER_IDS)
def test_monster_benchmark_replays_show_primary_behavior_across_dm_modes(variant_id: str) -> None:
    expectation = MONSTER_EXPECTATIONS[variant_id]

    for monster_behavior in ("kind", "balanced", "evil"):
        result = run_encounter(
            EncounterConfig(
                seed=f"benchmark-replay-{variant_id}-{monster_behavior}",
                enemy_preset_id=expectation.benchmark_preset_id,
                player_preset_id="monster_benchmark_duo",
                player_behavior="balanced",
                monster_behavior=monster_behavior,
            )
        )
        attack_events = get_enemy_attack_events(result.events)

        assert result.final_state.terminal_state == "complete"
        assert attack_events
        assert_primary_benchmark_behavior(variant_id, attack_events)
