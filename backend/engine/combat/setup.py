from __future__ import annotations

from backend.content.enemies import create_enemy, get_enemy_preset, get_enemy_variant
from backend.content.feature_definitions import unit_has_feature
from backend.content.player_loadouts import (
    create_player_party_units,
    get_default_player_positions,
    get_player_preset_footprints,
    get_player_preset_unit_ids,
)
from backend.engine.constants import (
    DEFAULT_MONSTER_BEHAVIOR,
    DEFAULT_PLAYER_BEHAVIOR,
    DEFAULT_SEED,
    GOBLIN_IDS,
)
from backend.engine.models.state import (
    EncounterConfig,
    EncounterState,
    Footprint,
    GridPosition,
    MonsterBehavior,
    MonsterBehaviorSelection,
    PlayerBehavior,
    ResolvedPlayerBehavior,
    TerrainFeature,
    UnitState,
)
from backend.engine.rules.combat_rules import attempt_uncanny_metabolism
from backend.engine.rules.spatial import assert_valid_placements_for_unit_ids
from backend.engine.templates import create_goblin
from backend.engine.utils.helpers import unit_sort_key
from backend.engine.utils.rng import normalize_seed, roll_die


def clone_placements_for_unit_ids(
    placements: dict[str, GridPosition],
    unit_ids: list[str] | tuple[str, ...],
) -> dict[str, GridPosition]:
    cloned: dict[str, GridPosition] = {}
    for unit_id in unit_ids:
        position = placements.get(unit_id)
        if position:
            cloned[unit_id] = position.model_copy(deep=True)
    return cloned


def get_enemy_preset_definition(config: EncounterConfig):
    if not config.enemy_preset_id:
        return None
    return get_enemy_preset(config.enemy_preset_id)


def get_config_player_unit_ids(config: EncounterConfig) -> list[str]:
    return get_player_preset_unit_ids(config.player_preset_id)


def get_config_unit_ids(config: EncounterConfig) -> list[str]:
    preset = get_enemy_preset_definition(config)
    player_unit_ids = get_config_player_unit_ids(config)
    if not preset:
        return [*player_unit_ids, *GOBLIN_IDS]
    return [*player_unit_ids, *[unit.unit_id for unit in preset.units]]


def get_config_unit_footprints(config: EncounterConfig) -> dict[str, Footprint]:
    footprints = get_player_preset_footprints(config.player_preset_id)
    preset = get_enemy_preset_definition(config)

    if preset:
        for unit in preset.units:
            footprints[unit.unit_id] = get_enemy_variant(unit.variant_id).footprint
        return footprints

    for goblin_id in GOBLIN_IDS:
        footprints[goblin_id] = Footprint(width=1, height=1)

    return footprints


def get_default_preset_placements(config: EncounterConfig) -> dict[str, GridPosition]:
    preset = get_enemy_preset_definition(config)
    if not preset:
        return {}

    placements = get_default_player_positions(config.player_preset_id)
    for unit in preset.units:
        placements[unit.unit_id] = unit.position.model_copy(deep=True)
    return placements


def resolve_terrain_features(config: EncounterConfig) -> list[TerrainFeature]:
    preset = get_enemy_preset_definition(config)
    if not preset:
        return []
    return [feature.model_copy(deep=True) for feature in preset.terrain_features]


def resolve_placements(config: EncounterConfig) -> dict[str, GridPosition]:
    expected_unit_ids = get_config_unit_ids(config)
    footprints_by_unit_id = get_config_unit_footprints(config)
    terrain_features = resolve_terrain_features(config)

    if config.enemy_preset_id:
        if not config.placements:
            default_placements = get_default_preset_placements(config)
            assert_valid_placements_for_unit_ids(
                default_placements,
                expected_unit_ids,
                footprints_by_unit_id,
                terrain_features,
            )
            return clone_placements_for_unit_ids(default_placements, expected_unit_ids)

    elif not config.placements:
        raise ValueError("The simulator requires a complete manual placement layout before combat starts.")

    assert_valid_placements_for_unit_ids(config.placements, expected_unit_ids, footprints_by_unit_id, terrain_features)
    return clone_placements_for_unit_ids(config.placements, expected_unit_ids)


def resolve_player_behavior(requested_behavior: PlayerBehavior | None, run_index: int = 0) -> ResolvedPlayerBehavior:
    behavior = requested_behavior or DEFAULT_PLAYER_BEHAVIOR
    if behavior == "balanced":
        return "smart" if run_index % 2 == 0 else "dumb"
    return behavior


def resolve_monster_behavior(requested_behavior: MonsterBehaviorSelection | None) -> MonsterBehavior:
    behavior = requested_behavior or DEFAULT_MONSTER_BEHAVIOR
    if behavior == "combined":
        raise ValueError("Combined DM behavior is only available for batch runs.")
    return behavior


def build_units(
    placements: dict[str, GridPosition],
    enemy_preset_id: str | None = None,
    player_preset_id: str | None = None,
) -> dict[str, UnitState]:
    units = create_player_party_units(player_preset_id or None)

    if enemy_preset_id:
        preset = get_enemy_preset(enemy_preset_id)
        for unit in preset.units:
            units[unit.unit_id] = create_enemy(unit.unit_id, unit.variant_id)
    else:
        units.update(
            {
                "G1": create_goblin("G1"),
                "G2": create_goblin("G2"),
                "G3": create_goblin("G3"),
                "G4": create_goblin("G4"),
                "G5": create_goblin("G5"),
                "G6": create_goblin("G6"),
                "G7": create_goblin("G7"),
            }
        )

    for unit_id, position in placements.items():
        units[unit_id].position = position.model_copy(deep=True)

    return units


def get_enemy_unit_ids(units: dict[str, UnitState]) -> list[str]:
    return sorted(
        [unit.id for unit in units.values() if unit.faction == "goblins"],
        key=unit_sort_key,
    )


def get_player_unit_ids(units: dict[str, UnitState]) -> list[str]:
    return sorted(
        [unit.id for unit in units.values() if unit.faction == "fighters"],
        key=unit_sort_key,
    )


def maybe_apply_smart_precombat_mage_armor(unit: UnitState, player_behavior: ResolvedPlayerBehavior) -> None:
    if player_behavior != "smart":
        return
    if unit.class_id != "wizard":
        return
    if "mage_armor" not in unit.prepared_combat_spell_ids:
        return
    if unit.current_hp <= 0 or unit.conditions.dead or unit.conditions.unconscious:
        return

    mage_armor_ac = 13 + unit.ability_mods.dex
    if mage_armor_ac <= unit.ac:
        return
    if unit.resources.spend_pool("spell_slots_level_1", 1):
        unit.ac = mage_armor_ac


def apply_smart_precombat_buffs(
    units: dict[str, UnitState],
    player_unit_ids: list[str],
    player_behavior: ResolvedPlayerBehavior,
) -> None:
    for player_unit_id in player_unit_ids:
        maybe_apply_smart_precombat_mage_armor(units[player_unit_id], player_behavior)


def sort_initiative_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        entries,
        key=lambda entry: (
            -int(entry["total"]),
            0 if entry["faction"] == "fighters" else 1,
            entry["id"],
        ),
    )


def create_encounter(config: EncounterConfig) -> EncounterState:
    seed = config.seed.strip() or DEFAULT_SEED
    player_behavior = resolve_player_behavior(config.player_behavior)
    monster_behavior = resolve_monster_behavior(config.monster_behavior)
    placements = resolve_placements(config)
    units = build_units(placements, config.enemy_preset_id, config.player_preset_id)
    terrain_features = resolve_terrain_features(config)
    player_unit_ids = get_player_unit_ids(units)
    enemy_unit_ids = get_enemy_unit_ids(units)
    apply_smart_precombat_buffs(units, player_unit_ids, player_behavior)
    rng_state = normalize_seed(seed)
    initiative_entries: list[dict[str, object]] = []
    initiative_scores: dict[str, int] = {}

    # Player characters roll initiative individually, while the opposing force
    # shares one rolled value in the current model.
    for player_unit_id in player_unit_ids:
        roll_value, rng_state = roll_die(rng_state, 20)
        if unit_has_feature(units[player_unit_id], "assassinate"):
            second_roll, rng_state = roll_die(rng_state, 20)
            roll_value = max(roll_value, second_roll)
        total = roll_value + units[player_unit_id].initiative_mod
        units[player_unit_id].initiative_score = total
        initiative_scores[player_unit_id] = total
        initiative_entries.append({"id": player_unit_id, "total": total, "faction": "fighters"})

    enemy_roll, rng_state = roll_die(rng_state, 20)
    for enemy_id in enemy_unit_ids:
        total = enemy_roll + units[enemy_id].initiative_mod
        units[enemy_id].initiative_score = total
        initiative_scores[enemy_id] = total
        initiative_entries.append({"id": enemy_id, "total": total, "faction": "goblins"})

    initiative_order = [entry["id"] for entry in sort_initiative_entries(initiative_entries)]

    state = EncounterState(
        seed=seed,
        player_behavior=player_behavior,
        monster_behavior=monster_behavior,
        rng_state=rng_state,
        round=1,
        initiative_order=initiative_order,
        initiative_scores=initiative_scores,
        active_combatant_index=0,
        units=units,
        combat_log=[],
        winner=None,
        terminal_state="ongoing",
        rescue_subphase=False,
        terrain_features=terrain_features,
        smart_targeting_policy=config.smart_targeting_policy,
        enable_end_turn_flanking=config.enable_end_turn_flanking,
        enable_frontline_body_blocking=config.enable_frontline_body_blocking,
    )

    for player_unit_id in player_unit_ids:
        attempt_uncanny_metabolism(state, player_unit_id)

    return state
