from __future__ import annotations

from backend.engine import create_encounter
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import EncounterConfig, Footprint, GridPosition, SwallowedEffect, TerrainFeature
from backend.engine.rules.spatial import (
    can_attempt_hide_from_position,
    find_path_to_adjacent_square,
    get_attack_context,
    get_hide_passive_perception_dc,
    get_reachable_squares,
    has_line_of_sight_between_units,
    has_terrain_half_cover_against_observer,
    inspect_placements_for_unit_ids,
    path_provokes_opportunity_attack,
)


def build_low_wall(feature_id: str = "low_wall_1", x: int = 5, y: int = 8) -> TerrainFeature:
    return TerrainFeature(
        feature_id=feature_id,
        kind="low_wall",
        position=GridPosition(x=x, y=y),
        footprint=Footprint(width=1, height=1),
    )


def build_column(feature_id: str = "column_1", x: int = 5, y: int = 8) -> TerrainFeature:
    return TerrainFeature(
        feature_id=feature_id,
        kind="column",
        position=GridPosition(x=x, y=y),
        footprint=Footprint(width=1, height=1),
    )


def test_flanking_requires_support_angle_greater_than_ninety_degrees() -> None:
    encounter = create_encounter(EncounterConfig(seed="flanking-obtuse", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=5, y=4)
    encounter.units["G1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=6)

    context = get_attack_context(encounter, "F1", "G1", encounter.units["F1"].attacks["greatsword"])

    assert context.legal is True
    assert "flanking" in context.advantage_sources


def test_right_angle_support_does_not_grant_flanking() -> None:
    encounter = create_encounter(EncounterConfig(seed="no-flanking-right-angle", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=5, y=4)
    encounter.units["G1"].position = GridPosition(x=5, y=5)
    encounter.units["F2"].position = GridPosition(x=6, y=5)

    context = get_attack_context(encounter, "F1", "G1", encounter.units["F1"].attacks["greatsword"])

    assert "flanking" not in context.advantage_sources


def test_ranged_long_range_and_cover_apply_together() -> None:
    encounter = create_encounter(EncounterConfig(seed="range-and-cover", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=10, y=1)
    encounter.units["F2"].position = GridPosition(x=5, y=1)

    context = get_attack_context(encounter, "F1", "G1", encounter.units["F1"].attacks["javelin"])

    assert context.legal is True
    assert context.within_normal_range is False
    assert context.within_long_range is True
    assert "long_range" in context.disadvantage_sources
    assert context.cover_ac_bonus == 2


def test_find_path_to_adjacent_square_uses_shortest_route() -> None:
    encounter = create_encounter(EncounterConfig(seed="shortest-path", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=1, y=1)
    encounter.units["G1"].position = GridPosition(x=4, y=1)

    path = find_path_to_adjacent_square(encounter, "F1", "G1", 6)

    assert path is not None
    assert [point.model_dump() for point in path.path] == [{"x": 1, "y": 1}, {"x": 2, "y": 1}, {"x": 3, "y": 1}]
    assert path.distance == 2


def test_path_provokes_opportunity_attack_when_it_leaves_reach() -> None:
    encounter = create_encounter(EncounterConfig(seed="provokes-opportunity-attack", placements=DEFAULT_POSITIONS))
    encounter.units["F1"].position = GridPosition(x=5, y=5)
    encounter.units["G1"].position = GridPosition(x=6, y=5)

    assert path_provokes_opportunity_attack(encounter, "F1", [GridPosition(x=5, y=5), GridPosition(x=5, y=6)]) is False
    assert path_provokes_opportunity_attack(
        encounter,
        "F1",
        [GridPosition(x=5, y=5), GridPosition(x=5, y=6), GridPosition(x=5, y=7)],
    ) is True


def test_pack_tactics_grants_advantage_when_an_ally_is_adjacent_to_target() -> None:
    encounter = create_encounter(EncounterConfig(seed="wolf-pack-tactics", enemy_preset_id="wolf_harriers"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["E2"].position = GridPosition(x=7, y=5)
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    context = get_attack_context(encounter, "E1", "F1", encounter.units["E1"].attacks["bite"])

    assert context.legal is True
    assert "pack_tactics" in context.advantage_sources


def test_pack_tactics_does_not_count_unconscious_allies() -> None:
    encounter = create_encounter(EncounterConfig(seed="wolf-pack-tactics-unconscious", enemy_preset_id="wolf_harriers"))
    encounter.units["E1"].position = GridPosition(x=5, y=5)
    encounter.units["E2"].position = GridPosition(x=7, y=5)
    encounter.units["E2"].current_hp = 0
    encounter.units["E2"].conditions.unconscious = True
    encounter.units["E2"].conditions.prone = True
    encounter.units["F1"].position = GridPosition(x=6, y=5)

    context = get_attack_context(encounter, "E1", "F1", encounter.units["E1"].attacks["bite"])

    assert "pack_tactics" not in context.advantage_sources


def test_terrain_blocks_manual_placement_validation() -> None:
    validation = inspect_placements_for_unit_ids(
        {
            "F1": GridPosition(x=5, y=8),
            "G1": GridPosition(x=10, y=8),
        },
        ["F1", "G1"],
        {
            "F1": Footprint(width=1, height=1),
            "G1": Footprint(width=1, height=1),
        },
        [
            TerrainFeature(
                feature_id="rock_1",
                kind="rock",
                position=GridPosition(x=5, y=8),
                footprint=Footprint(width=1, height=1),
            )
        ],
    )

    assert validation.is_valid is False
    assert validation.blocked_square_groups == [
        {
            "position": GridPosition(x=5, y=8),
            "unit_ids": ["F1"],
            "terrain_feature_ids": ["rock_1"],
        }
    ]


def test_column_blocks_manual_placement_validation() -> None:
    validation = inspect_placements_for_unit_ids(
        {"F1": GridPosition(x=5, y=8)},
        ["F1"],
        {"F1": Footprint(width=1, height=1)},
        [build_column()],
    )

    assert validation.is_valid is False
    assert validation.blocked_square_groups == [
        {
            "position": GridPosition(x=5, y=8),
            "unit_ids": ["F1"],
            "terrain_feature_ids": ["column_1"],
        }
    ]


def test_pathfinding_routes_around_blocking_rock() -> None:
    encounter = create_encounter(EncounterConfig(seed="rock-route", enemy_preset_id="goblin_screen"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=6, y=8)

    path = find_path_to_adjacent_square(encounter, "F1", "E1", 4)

    assert path is not None
    assert [point.model_dump() for point in path.path] == [{"x": 4, "y": 8}, {"x": 5, "y": 7}]


def test_rock_grants_ranged_cover_bonus() -> None:
    encounter = create_encounter(EncounterConfig(seed="rock-cover", enemy_preset_id="goblin_screen"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=6, y=8)

    context = get_attack_context(encounter, "F1", "E1", encounter.units["F1"].attacks["javelin"])

    assert context.legal is True
    assert context.cover_ac_bonus == 2


def test_low_wall_grants_cover_without_blocking_placement_path_or_line_of_sight() -> None:
    low_wall = build_low_wall()
    validation = inspect_placements_for_unit_ids(
        {"F1": GridPosition(x=5, y=8)},
        ["F1"],
        {"F1": Footprint(width=1, height=1)},
        [low_wall],
    )
    encounter = create_encounter(EncounterConfig(seed="low-wall-cover", enemy_preset_id="goblin_screen"))
    encounter.terrain_features = [low_wall]
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=6, y=8)

    reachable_positions = [square.position.model_dump() for square in get_reachable_squares(encounter, "F1", 1)]
    context = get_attack_context(encounter, "F1", "E1", encounter.units["F1"].attacks["javelin"])

    assert validation.is_valid is True
    assert {"x": 5, "y": 8} in reachable_positions
    assert has_line_of_sight_between_units(encounter, "F1", "E1") is True
    assert context.legal is True
    assert context.cover_ac_bonus == 2


def test_terrain_cover_does_not_stack_with_unit_cover() -> None:
    encounter = create_encounter(EncounterConfig(seed="rock-and-unit-cover", enemy_preset_id="goblin_screen"))
    encounter.units["F1"].position = GridPosition(x=4, y=8)
    encounter.units["F2"].position = GridPosition(x=6, y=8)
    encounter.units["E1"].position = GridPosition(x=8, y=8)

    context = get_attack_context(encounter, "F1", "E1", encounter.units["F1"].attacks["javelin"])

    assert context.legal is True
    assert context.cover_ac_bonus == 2


def test_terrain_cover_helper_reports_future_hide_cover() -> None:
    encounter = create_encounter(EncounterConfig(seed="rock-hide-helper", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=8, y=8)

    assert has_terrain_half_cover_against_observer(
        encounter,
        "F3",
        "E1",
        encounter.units["F3"].position,
        encounter.units["E1"].position,
    ) is True


def test_rock_cover_allows_hide_attempt_and_sets_minimum_dc_fifteen() -> None:
    encounter = create_encounter(EncounterConfig(seed="rock-hide-eligibility", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E1":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is True
    assert get_hide_passive_perception_dc(encounter, "F3", encounter.units["F3"].position) == 15


def test_low_wall_cover_does_not_allow_hide_attempt() -> None:
    encounter = create_encounter(EncounterConfig(seed="low-wall-hide-denied", enemy_preset_id="goblin_screen"))
    encounter.terrain_features = [build_low_wall()]
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E1":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert has_terrain_half_cover_against_observer(
        encounter,
        "F3",
        "E1",
        encounter.units["F3"].position,
        encounter.units["E1"].position,
    ) is True
    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is False


def test_unit_cover_alone_does_not_allow_hide_attempt() -> None:
    encounter = create_encounter(EncounterConfig(seed="unit-cover-hide-denied", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=5)
    encounter.units["F2"].position = GridPosition(x=5, y=5)
    encounter.units["E1"].position = GridPosition(x=8, y=5)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E1":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is False


def test_adjacent_enemy_blocks_hide_even_with_rock_cover() -> None:
    encounter = create_encounter(EncounterConfig(seed="adjacent-hide-blocked", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=8, y=8)
    encounter.units["E2"].position = GridPosition(x=4, y=9)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id in {"E1", "E2"}:
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is False


def test_hide_requires_terrain_cover_from_every_conscious_non_adjacent_observer() -> None:
    encounter = create_encounter(EncounterConfig(seed="all-observers-hide-block", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["E1"].position = GridPosition(x=8, y=8)
    encounter.units["E2"].position = GridPosition(x=4, y=12)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id in {"E1", "E2"}:
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is False


def test_downed_unit_cannot_attempt_hide_even_from_a_valid_rock_square() -> None:
    encounter = create_encounter(EncounterConfig(seed="downed-hide-block", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["F3"].current_hp = 0
    encounter.units["F3"].conditions.unconscious = True
    encounter.units["F3"].conditions.prone = True
    encounter.units["E1"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E1":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is False


def test_swallowed_unit_cannot_attempt_hide_even_if_it_still_has_a_position() -> None:
    encounter = create_encounter(EncounterConfig(seed="swallowed-hide-block", enemy_preset_id="goblin_screen"))
    encounter.units["F3"].position = GridPosition(x=4, y=8)
    encounter.units["F3"].temporary_effects.append(SwallowedEffect(kind="swallowed_by", source_id="E1"))
    encounter.units["E1"].position = GridPosition(x=8, y=8)

    for enemy_id, enemy in encounter.units.items():
        if not enemy_id.startswith("E") or enemy_id == "E1":
            continue
        enemy.current_hp = 0
        enemy.conditions.dead = True

    assert can_attempt_hide_from_position(encounter, "F3", encounter.units["F3"].position) is False
