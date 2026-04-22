from __future__ import annotations

from backend.content.class_definitions import CLASS_DEFINITIONS
from backend.content.enemies import DEFAULT_ENEMY_PRESET_ID, MONSTER_DEFINITIONS, get_active_enemy_presets
from backend.content.player_loadouts import (
    DEFAULT_PLAYER_PRESET_ID,
    PLAYER_LOADOUTS,
    get_active_player_presets,
    get_feature_ids_for_loadout,
)
from backend.engine.models.catalog import (
    EnemyCatalogResponse,
    EnemyPresetCatalogEntry,
    EnemyPresetUnitCatalogEntry,
    EnemyVariantCatalogEntry,
    PlayerCatalogResponse,
    PlayerClassCatalogEntry,
    PlayerLoadoutCatalogEntry,
    PlayerPresetCatalogEntry,
    PlayerPresetUnitCatalogEntry,
)


def get_enemy_catalog() -> EnemyCatalogResponse:
    """Build the frontend-facing enemy catalog from the backend content source of truth."""

    enemy_variants = [
        EnemyVariantCatalogEntry(
            id=definition.variant_id,
            display_name=definition.display_name,
            max_hp=definition.max_hp,
            footprint=definition.footprint.model_copy(deep=True),
        )
        for definition in sorted(MONSTER_DEFINITIONS.values(), key=lambda value: value.display_name)
    ]

    enemy_presets = [
        EnemyPresetCatalogEntry(
            id=preset.preset_id,
            display_name=preset.display_name,
            description=preset.description,
            units=[
                EnemyPresetUnitCatalogEntry(
                    unit_id=unit.unit_id,
                    variant_id=unit.variant_id,
                    position=unit.position.model_copy(deep=True),
                )
                for unit in preset.units
            ],
            terrain_features=[feature.model_copy(deep=True) for feature in preset.terrain_features],
        )
        for preset in get_active_enemy_presets()
    ]

    return EnemyCatalogResponse(
        default_enemy_preset_id=DEFAULT_ENEMY_PRESET_ID,
        enemy_variants=enemy_variants,
        enemy_presets=enemy_presets,
    )


def get_player_catalog() -> PlayerCatalogResponse:
    """Build the frontend-facing player catalog from the backend content source of truth."""

    classes = [
        PlayerClassCatalogEntry(
            id=definition.class_id,
            display_name=definition.display_name,
            category=definition.category,
            max_supported_level=definition.max_supported_level,
        )
        for definition in sorted(CLASS_DEFINITIONS.values(), key=lambda value: value.display_name)
        if definition.max_supported_level > 0
    ]

    loadouts = [
        PlayerLoadoutCatalogEntry(
            id=loadout.loadout_id,
            display_name=loadout.display_name,
            class_id=loadout.class_id,
            level=loadout.level,
            max_hp=loadout.max_hp,
            feature_ids=get_feature_ids_for_loadout(loadout),
            weapon_ids=sorted(loadout.attacks.keys()),
        )
        for loadout in sorted(PLAYER_LOADOUTS.values(), key=lambda value: (value.class_id, value.level, value.display_name))
    ]

    player_presets = [
        PlayerPresetCatalogEntry(
            id=preset.preset_id,
            display_name=preset.display_name,
            description=preset.description,
            units=[
                PlayerPresetUnitCatalogEntry(
                    unit_id=unit.unit_id,
                    loadout_id=unit.loadout_id,
                )
                for unit in preset.units
            ],
        )
        for preset in get_active_player_presets()
    ]

    return PlayerCatalogResponse(
        default_player_preset_id=DEFAULT_PLAYER_PRESET_ID,
        classes=classes,
        loadouts=loadouts,
        player_presets=player_presets,
    )
