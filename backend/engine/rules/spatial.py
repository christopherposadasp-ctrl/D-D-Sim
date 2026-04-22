from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from backend.content.enemies import unit_has_trait
from backend.engine.models.state import EncounterState, Faction, Footprint, GridPosition, TerrainFeature, UnitState, WeaponProfile
from backend.engine.utils.helpers import unit_can_take_reactions, unit_sort_key

GRID_SIZE = 15
SINGLE_SQUARE_FOOTPRINT = Footprint(width=1, height=1)


class ReachableSquare:
    """Simple container used by pathing and AI helpers."""

    def __init__(self, position: GridPosition, path: list[GridPosition], distance: int) -> None:
        self.position = position
        self.path = path
        self.distance = distance


class AttackContext:
    """Resolved spatial context for a single attack."""

    def __init__(
        self,
        *,
        legal: bool,
        distance_squares: int | None,
        distance_feet: int | None,
        within_reach: bool,
        within_normal_range: bool,
        within_long_range: bool,
        cover_ac_bonus: int,
        advantage_sources: list[str],
        disadvantage_sources: list[str],
    ) -> None:
        self.legal = legal
        self.distance_squares = distance_squares
        self.distance_feet = distance_feet
        self.within_reach = within_reach
        self.within_normal_range = within_normal_range
        self.within_long_range = within_long_range
        self.cover_ac_bonus = cover_ac_bonus
        self.advantage_sources = advantage_sources
        self.disadvantage_sources = disadvantage_sources


class PlacementValidationResult:
    def __init__(
        self,
        *,
        placed_unit_ids: list[str],
        missing_unit_ids: list[str],
        unexpected_unit_ids: list[str],
        out_of_bounds_unit_ids: list[str],
        overlapping_groups: list[dict[str, object]],
        blocked_square_groups: list[dict[str, object]],
        is_complete: bool,
        is_valid: bool,
        errors: list[str],
    ) -> None:
        self.placed_unit_ids = placed_unit_ids
        self.missing_unit_ids = missing_unit_ids
        self.unexpected_unit_ids = unexpected_unit_ids
        self.out_of_bounds_unit_ids = out_of_bounds_unit_ids
        self.overlapping_groups = overlapping_groups
        self.blocked_square_groups = blocked_square_groups
        self.is_complete = is_complete
        self.is_valid = is_valid
        self.errors = errors


@dataclass
class PositionIndex:
    """Precomputed view of occupied squares for a single state snapshot."""

    all_units: list[UnitState]
    units_by_faction: dict[Faction, list[UnitState]]
    occupancy: dict[str, list[UnitState]]
    terrain_occupancy: dict[str, list[TerrainFeature]]


def position_key(position: GridPosition) -> str:
    return f"{position.x},{position.y}"


def positions_equal(left: GridPosition | None = None, right: GridPosition | None = None) -> bool:
    return bool(left and right and left.x == right.x and left.y == right.y)


def get_unit_footprint(unit: UnitState) -> Footprint:
    return unit.footprint or SINGLE_SQUARE_FOOTPRINT


def get_occupied_squares_for_position(position: GridPosition, footprint: Footprint | None = None) -> list[GridPosition]:
    occupied_squares: list[GridPosition] = []
    resolved_footprint = footprint or SINGLE_SQUARE_FOOTPRINT

    for delta_x in range(resolved_footprint.width):
        for delta_y in range(resolved_footprint.height):
            occupied_squares.append(GridPosition(x=position.x + delta_x, y=position.y + delta_y))

    return occupied_squares


def get_unit_occupied_squares(unit: UnitState) -> list[GridPosition]:
    if not unit.position:
        return []
    return get_occupied_squares_for_position(unit.position, get_unit_footprint(unit))


def get_terrain_occupied_squares(feature: TerrainFeature) -> list[GridPosition]:
    return get_occupied_squares_for_position(feature.position, feature.footprint)


def is_unit_swallowed(unit: UnitState) -> bool:
    return any(effect.kind == "swallowed_by" for effect in unit.temporary_effects)


def get_swallow_source_id(unit: UnitState) -> str | None:
    swallowed_effect = next((effect for effect in unit.temporary_effects if effect.kind == "swallowed_by"), None)
    return swallowed_effect.source_id if swallowed_effect else None


def get_grappled_target_ids(state: EncounterState, source_id: str) -> list[str]:
    return sorted(
        [
            unit.id
            for unit in state.units.values()
            if any(effect.kind == "grappled_by" and effect.source_id == source_id for effect in unit.temporary_effects)
        ]
    )


def is_within_bounds(position: GridPosition, footprint: Footprint | None = None) -> bool:
    return all(1 <= square.x <= GRID_SIZE and 1 <= square.y <= GRID_SIZE for square in get_occupied_squares_for_position(position, footprint))


def inspect_placements_for_unit_ids(
    placements: dict[str, GridPosition] | None,
    expected_unit_ids: list[str] | tuple[str, ...],
    footprints_by_unit_id: dict[str, Footprint] | None = None,
    terrain_features: list[TerrainFeature] | tuple[TerrainFeature, ...] | None = None,
) -> PlacementValidationResult:
    normalized_placements = placements or {}
    expected_unit_id_list = list(expected_unit_ids)
    expected_unit_set = set(expected_unit_id_list)
    placed_unit_ids = [unit_id for unit_id in expected_unit_id_list if normalized_placements.get(unit_id)]
    missing_unit_ids = [unit_id for unit_id in expected_unit_id_list if not normalized_placements.get(unit_id)]
    unexpected_unit_ids = [unit_id for unit_id in normalized_placements if unit_id not in expected_unit_set]
    resolved_footprints = footprints_by_unit_id or {}
    out_of_bounds_unit_ids: list[str] = []
    occupied_squares: dict[str, list[str]] = {}
    terrain_occupied_squares: dict[str, list[str]] = {}
    blocked_square_groups_by_key: dict[str, dict[str, object]] = {}

    for feature in terrain_features or ():
        for occupied_square in get_terrain_occupied_squares(feature):
            terrain_occupied_squares.setdefault(position_key(occupied_square), []).append(feature.feature_id)

    for unit_id in placed_unit_ids:
        position = normalized_placements[unit_id]
        footprint = resolved_footprints.get(unit_id, SINGLE_SQUARE_FOOTPRINT)

        if not is_within_bounds(position, footprint):
            out_of_bounds_unit_ids.append(unit_id)
            continue

        for occupied_square in get_occupied_squares_for_position(position, footprint):
            key = position_key(occupied_square)
            occupied_squares.setdefault(key, []).append(unit_id)

            terrain_feature_ids = terrain_occupied_squares.get(key, [])
            if not terrain_feature_ids:
                continue

            blocked_group = blocked_square_groups_by_key.setdefault(
                key,
                {
                    "position": GridPosition(x=occupied_square.x, y=occupied_square.y),
                    "unit_ids": [],
                    "terrain_feature_ids": list(terrain_feature_ids),
                },
            )
            blocked_unit_ids = blocked_group["unit_ids"]
            if unit_id not in blocked_unit_ids:
                blocked_unit_ids.append(unit_id)

    overlapping_groups: list[dict[str, object]] = []
    for key, unit_ids in occupied_squares.items():
        if len(unit_ids) <= 1:
            continue
        x, y = (int(value) for value in key.split(","))
        overlapping_groups.append({"position": GridPosition(x=x, y=y), "unit_ids": unit_ids})

    blocked_square_groups = sorted(
        blocked_square_groups_by_key.values(),
        key=lambda group: (
            group["position"].x,
            group["position"].y,
        ),
    )

    errors: list[str] = []
    if missing_unit_ids:
        errors.append(f"Missing placements for: {', '.join(missing_unit_ids)}.")
    if unexpected_unit_ids:
        errors.append(f"Unexpected unit ids in placement map: {', '.join(unexpected_unit_ids)}.")
    if out_of_bounds_unit_ids:
        errors.append(f"Out-of-bounds placements for: {', '.join(out_of_bounds_unit_ids)}.")

    for overlap in overlapping_groups:
        position = overlap["position"]
        unit_ids = overlap["unit_ids"]
        errors.append(f"Overlapping placements at ({position.x},{position.y}): {', '.join(unit_ids)}.")

    for blocked_group in blocked_square_groups:
        position = blocked_group["position"]
        unit_ids = blocked_group["unit_ids"]
        terrain_feature_ids = blocked_group["terrain_feature_ids"]
        errors.append(
            f"Blocked terrain at ({position.x},{position.y}): {', '.join(unit_ids)} overlaps {', '.join(terrain_feature_ids)}."
        )

    return PlacementValidationResult(
        placed_unit_ids=placed_unit_ids,
        missing_unit_ids=missing_unit_ids,
        unexpected_unit_ids=unexpected_unit_ids,
        out_of_bounds_unit_ids=out_of_bounds_unit_ids,
        overlapping_groups=overlapping_groups,
        blocked_square_groups=blocked_square_groups,
        is_complete=not missing_unit_ids,
        is_valid=not missing_unit_ids
        and not unexpected_unit_ids
        and not out_of_bounds_unit_ids
        and not overlapping_groups
        and not blocked_square_groups,
        errors=errors,
    )


def inspect_placements(
    placements: dict[str, GridPosition] | None,
    footprints_by_unit_id: dict[str, Footprint] | None = None,
    terrain_features: list[TerrainFeature] | tuple[TerrainFeature, ...] | None = None,
) -> PlacementValidationResult:
    from backend.engine.constants import UNIT_IDS

    return inspect_placements_for_unit_ids(placements, UNIT_IDS, footprints_by_unit_id, terrain_features)


def assert_valid_placements_for_unit_ids(
    placements: dict[str, GridPosition] | None,
    expected_unit_ids: list[str] | tuple[str, ...],
    footprints_by_unit_id: dict[str, Footprint] | None = None,
    terrain_features: list[TerrainFeature] | tuple[TerrainFeature, ...] | None = None,
) -> PlacementValidationResult:
    validation = inspect_placements_for_unit_ids(placements, expected_unit_ids, footprints_by_unit_id, terrain_features)
    if not validation.is_valid:
        raise ValueError(" ".join(validation.errors))
    return validation


def assert_valid_placements(
    placements: dict[str, GridPosition] | None,
    footprints_by_unit_id: dict[str, Footprint] | None = None,
    terrain_features: list[TerrainFeature] | tuple[TerrainFeature, ...] | None = None,
) -> PlacementValidationResult:
    from backend.engine.constants import UNIT_IDS

    return assert_valid_placements_for_unit_ids(placements, UNIT_IDS, footprints_by_unit_id, terrain_features)


def chebyshev_distance(left: GridPosition, right: GridPosition) -> int:
    return max(abs(left.x - right.x), abs(left.y - right.y))


def squares_to_feet(squares: int) -> int:
    return squares * 5


def feet_to_squares(feet: int) -> int:
    return -(-feet // 5)


def get_gap_between_intervals(left_start: int, left_end: int, right_start: int, right_end: int) -> int:
    if left_end < right_start:
        return right_start - left_end
    if right_end < left_start:
        return left_start - right_end
    return 0


def get_min_chebyshev_distance_between_footprints(
    left_position: GridPosition,
    left_footprint: Footprint,
    right_position: GridPosition,
    right_footprint: Footprint,
) -> int:
    left_x_end = left_position.x + left_footprint.width - 1
    left_y_end = left_position.y + left_footprint.height - 1
    right_x_end = right_position.x + right_footprint.width - 1
    right_y_end = right_position.y + right_footprint.height - 1

    gap_x = get_gap_between_intervals(left_position.x, left_x_end, right_position.x, right_x_end)
    gap_y = get_gap_between_intervals(left_position.y, left_y_end, right_position.y, right_y_end)
    return max(gap_x, gap_y)


def does_unit_occupy_square(unit: UnitState) -> bool:
    return bool(unit.position and not unit.conditions.dead and not is_unit_swallowed(unit))


def build_position_index(state: EncounterState) -> PositionIndex:
    all_units: list[UnitState] = []
    units_by_faction: dict[Faction, list[UnitState]] = {"fighters": [], "goblins": []}
    occupancy: dict[str, list[UnitState]] = {}
    terrain_occupancy: dict[str, list[TerrainFeature]] = {}

    for unit in state.units.values():
        if not does_unit_occupy_square(unit):
            continue

        all_units.append(unit)
        units_by_faction[unit.faction].append(unit)

        for occupied_square in get_unit_occupied_squares(unit):
            occupancy.setdefault(position_key(occupied_square), []).append(unit)

    all_units.sort(key=lambda unit: unit_sort_key(unit.id))
    units_by_faction["fighters"].sort(key=lambda unit: unit_sort_key(unit.id))
    units_by_faction["goblins"].sort(key=lambda unit: unit_sort_key(unit.id))

    for occupants in occupancy.values():
        occupants.sort(key=lambda unit: unit_sort_key(unit.id))

    for feature in state.terrain_features:
        for occupied_square in get_terrain_occupied_squares(feature):
            terrain_occupancy.setdefault(position_key(occupied_square), []).append(feature)

    for features in terrain_occupancy.values():
        features.sort(key=lambda feature: feature.feature_id)

    return PositionIndex(
        all_units=all_units,
        units_by_faction=units_by_faction,
        occupancy=occupancy,
        terrain_occupancy=terrain_occupancy,
    )


def get_units_with_positions(
    state: EncounterState,
    faction: Faction | None = None,
    position_index: PositionIndex | None = None,
) -> list[UnitState]:
    index = position_index or build_position_index(state)
    if faction is None:
        return index.all_units
    return index.units_by_faction[faction]


def get_occupant_at(
    state: EncounterState,
    position: GridPosition,
    ignored_unit_ids: list[str] | None = None,
    position_index: PositionIndex | None = None,
) -> UnitState | None:
    index = position_index or build_position_index(state)
    ignored_ids = set(ignored_unit_ids or [])
    for occupant in index.occupancy.get(position_key(position), []):
        if occupant.id not in ignored_ids:
            return occupant
    return None


def get_occupants_for_position(
    state: EncounterState,
    position: GridPosition,
    footprint: Footprint,
    ignored_unit_ids: list[str] | None = None,
    position_index: PositionIndex | None = None,
) -> list[UnitState]:
    ignored_ids = set(ignored_unit_ids or [])
    index = position_index or build_position_index(state)
    occupants_by_id: dict[str, UnitState] = {}

    for occupied_square in get_occupied_squares_for_position(position, footprint):
        for occupant in index.occupancy.get(position_key(occupied_square), []):
            if occupant.id in ignored_ids:
                continue
            occupants_by_id[occupant.id] = occupant

    return sorted(occupants_by_id.values(), key=lambda unit: unit_sort_key(unit.id))


def get_terrain_feature_at(
    state: EncounterState,
    position: GridPosition,
    position_index: PositionIndex | None = None,
) -> TerrainFeature | None:
    index = position_index or build_position_index(state)
    terrain_features = index.terrain_occupancy.get(position_key(position), [])
    return terrain_features[0] if terrain_features else None


def get_terrain_features_for_position(
    state: EncounterState,
    position: GridPosition,
    footprint: Footprint,
    position_index: PositionIndex | None = None,
) -> list[TerrainFeature]:
    index = position_index or build_position_index(state)
    terrain_features_by_id: dict[str, TerrainFeature] = {}

    for occupied_square in get_occupied_squares_for_position(position, footprint):
        for feature in index.terrain_occupancy.get(position_key(occupied_square), []):
            terrain_features_by_id[feature.feature_id] = feature

    return sorted(terrain_features_by_id.values(), key=lambda feature: feature.feature_id)


def can_move_through(mover: UnitState, occupant: UnitState) -> bool:
    if occupant.id == mover.id:
        return True
    if occupant.conditions.dead:
        return True
    if occupant.faction == mover.faction:
        return True
    return occupant.conditions.unconscious


def is_adjacent(left: GridPosition | None = None, right: GridPosition | None = None) -> bool:
    return bool(left and right and chebyshev_distance(left, right) <= 1)


def get_adjacent_squares(position: GridPosition) -> list[GridPosition]:
    squares: list[GridPosition] = []

    for delta_x in range(-1, 2):
        for delta_y in range(-1, 2):
            if delta_x == 0 and delta_y == 0:
                continue
            candidate = GridPosition(x=position.x + delta_x, y=position.y + delta_y)
            if is_within_bounds(candidate):
                squares.append(candidate)

    return sorted(squares, key=lambda square: (square.x, square.y))


def get_melee_reach_squares(weapon: WeaponProfile) -> int:
    if weapon.kind != "melee":
        return 0
    return feet_to_squares(weapon.reach or 5)


def get_unit_center(position: GridPosition, footprint: Footprint) -> tuple[float, float]:
    return (position.x + (footprint.width - 1) / 2, position.y + (footprint.height - 1) / 2)


def get_opportunity_attack_threats_for_path(
    state: EncounterState,
    mover_id: str,
    path: list[GridPosition],
    position_index: PositionIndex | None = None,
    enemy_units: list[UnitState] | None = None,
) -> list[str]:
    mover = state.units[mover_id]
    if not mover.position or len(path) <= 1:
        return []

    cached_positions = position_index or build_position_index(state)
    threatening_units = enemy_units or get_units_with_positions(
        state,
        "goblins" if mover.faction == "fighters" else "fighters",
        cached_positions,
    )
    threats: set[str] = set()

    for path_index in range(1, len(path)):
        previous = path[path_index - 1]
        next_position = path[path_index]

        for unit in threatening_units:
            if not unit_can_take_reactions(unit) or not unit.position:
                continue

            melee_weapon = next((weapon for weapon in unit.attacks.values() if weapon and weapon.kind == "melee"), None)
            if not melee_weapon:
                continue

            threat_reach = get_melee_reach_squares(melee_weapon)
            start_distance = get_min_chebyshev_distance_between_footprints(
                unit.position,
                get_unit_footprint(unit),
                previous,
                get_unit_footprint(mover),
            )
            end_distance = get_min_chebyshev_distance_between_footprints(
                unit.position,
                get_unit_footprint(unit),
                next_position,
                get_unit_footprint(mover),
            )

            if start_distance <= threat_reach and end_distance > threat_reach:
                threats.add(unit.id)

    return sorted(threats, key=unit_sort_key)


def path_provokes_opportunity_attack(
    state: EncounterState,
    mover_id: str,
    path: list[GridPosition],
    position_index: PositionIndex | None = None,
    enemy_units: list[UnitState] | None = None,
) -> bool:
    return bool(get_opportunity_attack_threats_for_path(state, mover_id, path, position_index, enemy_units))


def can_provide_flanking(unit: UnitState) -> bool:
    return not unit.conditions.dead and not unit.conditions.unconscious and unit.current_hp > 0


def has_flanking_support(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    attacker_position: GridPosition,
    target_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> bool:
    attacker = state.units[attacker_id]
    target = state.units[target_id]
    if get_min_chebyshev_distance_between_footprints(
        attacker_position,
        get_unit_footprint(attacker),
        target_position,
        get_unit_footprint(target),
    ) > 1:
        return False

    attacker_center = get_unit_center(attacker_position, get_unit_footprint(attacker))
    target_center = get_unit_center(target_position, get_unit_footprint(target))
    attacker_offset_x = attacker_center[0] - target_center[0]
    attacker_offset_y = attacker_center[1] - target_center[1]

    for unit in get_units_with_positions(state, attacker.faction, position_index):
        if unit.id in {attacker_id, target_id}:
            continue
        if not can_provide_flanking(unit) or not unit.position:
            continue
        if get_min_chebyshev_distance_between_footprints(
            unit.position,
            get_unit_footprint(unit),
            target_position,
            get_unit_footprint(target),
        ) > 1:
            continue

        ally_center = get_unit_center(unit.position, get_unit_footprint(unit))
        ally_offset_x = ally_center[0] - target_center[0]
        ally_offset_y = ally_center[1] - target_center[1]

        if attacker_offset_x * ally_offset_x + attacker_offset_y * ally_offset_y < 0:
            return True

    return False


def has_pack_tactics_support(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    target_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> bool:
    attacker = state.units[attacker_id]
    target = state.units[target_id]

    for unit in get_units_with_positions(state, attacker.faction, position_index):
        if unit.id in {attacker_id, target_id}:
            continue
        if not can_provide_flanking(unit) or not unit.position:
            continue
        if get_min_chebyshev_distance_between_footprints(
            unit.position,
            get_unit_footprint(unit),
            target_position,
            get_unit_footprint(target),
        ) <= 1:
            return True

    return False


def build_reachable_square_map(
    state: EncounterState,
    mover_id: str,
    max_squares: int,
    position_index: PositionIndex | None = None,
) -> dict[str, ReachableSquare]:
    mover = state.units[mover_id]
    if not mover.position:
        return {}

    index = position_index or build_position_index(state)
    mover_footprint = get_unit_footprint(mover)
    start = mover.position.model_copy(deep=True)
    queue: deque[GridPosition] = deque([start])
    visited = {position_key(start)}
    path_map: dict[str, list[GridPosition]] = {position_key(start): [start]}
    distance_map: dict[str, int] = {position_key(start): 0}
    legal_ends: dict[str, ReachableSquare] = {
        position_key(start): ReachableSquare(position=start, path=[start], distance=0)
    }

    while queue:
        current = queue.popleft()
        current_distance = distance_map[position_key(current)]
        current_path = path_map[position_key(current)]

        if current_distance >= max_squares:
            continue

        for neighbor in get_adjacent_squares(current):
            key = position_key(neighbor)
            if key in visited:
                continue
            if not is_within_bounds(neighbor, mover_footprint):
                continue
            if get_terrain_features_for_position(state, neighbor, mover_footprint, index):
                continue

            destination_occupants = get_occupants_for_position(state, neighbor, mover_footprint, [mover_id], index)
            if any(not can_move_through(mover, occupant) for occupant in destination_occupants):
                continue

            visited.add(key)
            next_path = [*current_path, neighbor]
            next_distance = current_distance + 1
            path_map[key] = next_path
            distance_map[key] = next_distance
            queue.append(neighbor)

            if not destination_occupants:
                legal_ends[key] = ReachableSquare(position=neighbor, path=next_path, distance=next_distance)

    return legal_ends


def get_reachable_squares(
    state: EncounterState,
    mover_id: str,
    max_squares: int,
    position_index: PositionIndex | None = None,
) -> list[ReachableSquare]:
    squares = list(build_reachable_square_map(state, mover_id, max_squares, position_index).values())
    return sorted(squares, key=lambda square: (square.distance, square.position.x, square.position.y))


def choose_best_reachable_square(candidates: list[ReachableSquare]) -> ReachableSquare | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda square: (square.distance, square.position.x, square.position.y))[0]


def find_path_to_adjacent_square(
    state: EncounterState,
    mover_id: str,
    target_id: str,
    max_squares: int = 10**9,
    position_index: PositionIndex | None = None,
) -> ReachableSquare | None:
    target = state.units[target_id]
    mover = state.units[mover_id]
    if not target.position:
        return None

    reachable = build_reachable_square_map(state, mover_id, max_squares, position_index)
    candidates = [
        square
        for square in reachable.values()
        if get_min_chebyshev_distance_between_footprints(
            square.position,
            get_unit_footprint(mover),
            target.position,
            get_unit_footprint(target),
        )
        <= 1
    ]
    return choose_best_reachable_square(candidates)


def truncate_path(path: list[GridPosition], max_squares: int) -> list[GridPosition]:
    if len(path) <= 1 or max_squares <= 0:
        return [path[0]]
    return path[: min(len(path), max_squares + 1)]


def find_advance_path(
    state: EncounterState,
    mover_id: str,
    target_id: str,
    max_squares: int,
    position_index: PositionIndex | None = None,
) -> ReachableSquare | None:
    target = state.units[target_id]
    mover = state.units[mover_id]
    if not target.position:
        return None

    full_adjacent_path = find_path_to_adjacent_square(state, mover_id, target_id, position_index=position_index)
    if full_adjacent_path:
        if full_adjacent_path.distance <= max_squares:
            return full_adjacent_path

        truncated_path = truncate_path(full_adjacent_path.path, max_squares)
        return ReachableSquare(position=truncated_path[-1], path=truncated_path, distance=len(truncated_path) - 1)

    reachable = get_reachable_squares(state, mover_id, max_squares, position_index)
    if not reachable:
        return None

    return sorted(
        reachable,
        key=lambda square: (
            get_min_chebyshev_distance_between_footprints(
                square.position,
                get_unit_footprint(mover),
                target.position,
                get_unit_footprint(target),
            ),
            -square.distance,
            square.position.x,
            square.position.y,
        ),
    )[0]


def get_line_squares(start: GridPosition, end: GridPosition) -> list[GridPosition]:
    cells = [start.model_copy(deep=True)]
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    steps_x = abs(delta_x)
    steps_y = abs(delta_y)
    sign_x = 0 if delta_x == 0 else (1 if delta_x > 0 else -1)
    sign_y = 0 if delta_y == 0 else (1 if delta_y > 0 else -1)
    x = start.x
    y = start.y
    iter_x = 0
    iter_y = 0

    while iter_x < steps_x or iter_y < steps_y:
        decision = (1 + 2 * iter_x) * steps_y - (1 + 2 * iter_y) * steps_x
        if decision == 0:
            x += sign_x
            y += sign_y
            iter_x += 1
            iter_y += 1
        elif decision < 0:
            x += sign_x
            iter_x += 1
        else:
            y += sign_y
            iter_y += 1

        cells.append(GridPosition(x=x, y=y))

    return cells


def get_closest_attack_line_positions(
    attacker_position: GridPosition,
    attacker_footprint: Footprint,
    target_position: GridPosition,
    target_footprint: Footprint,
) -> tuple[GridPosition, GridPosition]:
    attacker_squares = get_occupied_squares_for_position(attacker_position, attacker_footprint)
    target_squares = get_occupied_squares_for_position(target_position, target_footprint)
    return sorted(
        (
            (attacker_square, target_square)
            for attacker_square in attacker_squares
            for target_square in target_squares
        ),
        key=lambda pair: (
            chebyshev_distance(pair[0], pair[1]),
            pair[0].x,
            pair[0].y,
            pair[1].x,
            pair[1].y,
        ),
    )[0]


def get_attack_line_traversed_squares(
    attacker_position: GridPosition,
    attacker_footprint: Footprint,
    target_position: GridPosition,
    target_footprint: Footprint,
) -> list[GridPosition]:
    line_start, line_end = get_closest_attack_line_positions(
        attacker_position,
        attacker_footprint,
        target_position,
        target_footprint,
    )
    return get_line_squares(line_start, line_end)[1:-1]


def has_terrain_half_cover_against_observer(
    state: EncounterState,
    unit_id: str,
    observer_id: str,
    unit_position: GridPosition,
    observer_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> bool:
    """Return whether terrain grants half cover from one observer.

    This helper stays terrain-only so future Hide logic can reason about
    concealment geometry without inheriting unit-based cover shortcuts.
    """

    index = position_index or build_position_index(state)
    unit = state.units[unit_id]
    observer = state.units[observer_id]
    traversed = get_attack_line_traversed_squares(
        observer_position,
        get_unit_footprint(observer),
        unit_position,
        get_unit_footprint(unit),
    )
    return any(get_terrain_feature_at(state, square, index) for square in traversed)


def get_conscious_enemy_observers_for_hide(
    state: EncounterState,
    unit_id: str,
    unit_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> list[UnitState]:
    unit = state.units[unit_id]
    observers: list[UnitState] = []

    for observer in get_units_with_positions(
        state,
        "goblins" if unit.faction == "fighters" else "fighters",
        position_index,
    ):
        if observer.conditions.dead or observer.current_hp <= 0 or observer.conditions.unconscious or not observer.position:
            continue
        if (
            get_min_chebyshev_distance_between_footprints(
                unit_position,
                get_unit_footprint(unit),
                observer.position,
                get_unit_footprint(observer),
            )
            <= 1
        ):
            continue
        observers.append(observer)

    return observers


def is_adjacent_to_conscious_enemy(
    state: EncounterState,
    unit_id: str,
    unit_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> bool:
    unit = state.units[unit_id]

    for enemy in get_units_with_positions(
        state,
        "goblins" if unit.faction == "fighters" else "fighters",
        position_index,
    ):
        if enemy.conditions.dead or enemy.current_hp <= 0 or enemy.conditions.unconscious or not enemy.position:
            continue
        if (
            get_min_chebyshev_distance_between_footprints(
                unit_position,
                get_unit_footprint(unit),
                enemy.position,
                get_unit_footprint(enemy),
            )
            <= 1
        ):
            return True

    return False


def has_terrain_cover_from_all_observers_for_hide(
    state: EncounterState,
    unit_id: str,
    unit_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> bool:
    observers = get_conscious_enemy_observers_for_hide(state, unit_id, unit_position, position_index)
    if not observers:
        return False

    return all(
        has_terrain_half_cover_against_observer(
            state,
            unit_id,
            observer.id,
            unit_position,
            observer.position,
            position_index,
        )
        for observer in observers
    )


def can_attempt_hide_from_position(
    state: EncounterState,
    unit_id: str,
    unit_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> bool:
    unit = state.units[unit_id]
    resolved_position = unit_position or unit.position

    if (
        resolved_position is None
        or unit.conditions.dead
        or unit.current_hp <= 0
        or unit.conditions.unconscious
        or is_unit_swallowed(unit)
    ):
        return False

    if is_adjacent_to_conscious_enemy(state, unit_id, resolved_position, position_index):
        return False

    return has_terrain_cover_from_all_observers_for_hide(state, unit_id, resolved_position, position_index)


def get_hide_passive_perception_dc(
    state: EncounterState,
    unit_id: str,
    unit_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> int | None:
    observers = get_conscious_enemy_observers_for_hide(state, unit_id, unit_position, position_index)
    if not observers:
        return None
    return max(15, max(observer.passive_perception for observer in observers))


def has_half_cover(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    attacker_position: GridPosition,
    target_position: GridPosition,
    position_index: PositionIndex | None = None,
) -> bool:
    attacker = state.units[attacker_id]
    target = state.units[target_id]
    traversed = get_attack_line_traversed_squares(
        attacker_position,
        get_unit_footprint(attacker),
        target_position,
        get_unit_footprint(target),
    )
    has_terrain_cover = has_terrain_half_cover_against_observer(
        state,
        target_id,
        attacker_id,
        target_position,
        attacker_position,
        position_index,
    )
    has_unit_cover = any(get_occupant_at(state, square, [attacker_id, target_id], position_index) for square in traversed)
    return has_terrain_cover or has_unit_cover


def get_attack_context(
    state: EncounterState,
    attacker_id: str,
    target_id: str,
    weapon: WeaponProfile,
    attacker_position: GridPosition | None = None,
    target_position: GridPosition | None = None,
    position_index: PositionIndex | None = None,
) -> AttackContext:
    index = position_index or build_position_index(state)
    attacker = state.units[attacker_id]
    target = state.units[target_id]
    attacker_position = attacker_position or attacker.position
    target_position = target_position or target.position

    attacker_swallowed_by = get_swallow_source_id(attacker)
    target_swallowed_by = get_swallow_source_id(target)

    if target_swallowed_by is not None:
        return AttackContext(
            legal=False,
            distance_squares=None,
            distance_feet=None,
            within_reach=False,
            within_normal_range=False,
            within_long_range=False,
            cover_ac_bonus=0,
            advantage_sources=[],
            disadvantage_sources=[],
        )

    if attacker_swallowed_by is not None:
        is_targeting_swallower = attacker_swallowed_by == target_id
        legal = is_targeting_swallower and weapon.kind == "melee"
        return AttackContext(
            legal=legal,
            distance_squares=0 if legal else None,
            distance_feet=0 if legal else None,
            within_reach=legal,
            within_normal_range=legal,
            within_long_range=legal,
            cover_ac_bonus=0,
            advantage_sources=[],
            disadvantage_sources=[] if legal else ["swallowed"],
        )

    if not attacker_position or not target_position:
        return AttackContext(
            legal=False,
            distance_squares=None,
            distance_feet=None,
            within_reach=False,
            within_normal_range=False,
            within_long_range=False,
            cover_ac_bonus=0,
            advantage_sources=[],
            disadvantage_sources=[],
        )

    distance_squares = get_min_chebyshev_distance_between_footprints(
        attacker_position,
        get_unit_footprint(attacker),
        target_position,
        get_unit_footprint(target),
    )
    distance_feet = squares_to_feet(distance_squares)
    disadvantage_sources: list[str] = []
    advantage_sources: list[str] = []
    legal = False
    within_reach = False
    within_normal_range = False
    within_long_range = False
    cover_ac_bonus = 0

    if (
        attacker.faction == "goblins"
        and unit_has_trait(attacker, "pack_tactics")
        and has_pack_tactics_support(state, attacker_id, target_id, target_position, index)
    ):
        advantage_sources.append("pack_tactics")

    if weapon.kind == "melee":
        reach_squares = get_melee_reach_squares(weapon)
        within_reach = distance_squares <= reach_squares
        legal = within_reach
        within_normal_range = within_reach
        within_long_range = within_reach

        if within_reach and distance_squares <= 1 and has_flanking_support(
            state,
            attacker_id,
            target_id,
            attacker_position,
            target_position,
            index,
        ):
            advantage_sources.append("flanking")
    else:
        normal_range_feet = weapon.range.normal if weapon.range else 0
        long_range_feet = weapon.range.long if weapon.range else 0
        within_normal_range = distance_feet <= normal_range_feet
        within_long_range = distance_feet <= long_range_feet
        legal = within_long_range

        if legal and not within_normal_range:
            disadvantage_sources.append("long_range")

        nearby_visible_enemy = any(
            unit.faction != attacker.faction
            and not unit.conditions.unconscious
            and unit.position
            and get_min_chebyshev_distance_between_footprints(
                attacker_position,
                get_unit_footprint(attacker),
                unit.position,
                get_unit_footprint(unit),
            )
            <= 1
            for unit in get_units_with_positions(state, position_index=index)
        )
        if nearby_visible_enemy:
            disadvantage_sources.append("adjacent_enemy")

        if has_half_cover(state, attacker_id, target_id, attacker_position, target_position, index):
            cover_ac_bonus = 2

    # Some bite-style weapons can only keep pressuring a creature that the
    # attacker is already holding. This rule belongs in shared range legality so
    # large grapplers like crocodiles and giant toads use the same check.
    if weapon.locks_to_grappled_target:
        grappled_targets = get_grappled_target_ids(state, attacker_id)
        if grappled_targets and target_id not in grappled_targets:
            legal = False
            within_reach = False
            within_normal_range = False
            within_long_range = False

    return AttackContext(
        legal=legal,
        distance_squares=distance_squares,
        distance_feet=distance_feet,
        within_reach=within_reach,
        within_normal_range=within_normal_range,
        within_long_range=within_long_range,
        cover_ac_bonus=cover_ac_bonus,
        advantage_sources=advantage_sources,
        disadvantage_sources=disadvantage_sources,
    )


def get_min_distance_to_faction(
    state: EncounterState,
    position: GridPosition,
    faction: Faction,
    position_index: PositionIndex | None = None,
    footprint: Footprint | None = None,
) -> int:
    units = get_units_with_positions(state, faction, position_index)
    if not units:
        return 10**9

    resolved_footprint = footprint or SINGLE_SQUARE_FOOTPRINT
    return min(
        get_min_chebyshev_distance_between_footprints(
            position,
            resolved_footprint,
            unit.position,
            get_unit_footprint(unit),
        )
        for unit in units
        if unit.position
    )
