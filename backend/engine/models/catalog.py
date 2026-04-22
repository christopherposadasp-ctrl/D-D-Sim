from __future__ import annotations

from typing import Literal

from backend.engine.models.state import CamelModel, Footprint, GridPosition, TerrainFeature


class EnemyVariantCatalogEntry(CamelModel):
    id: str
    display_name: str
    max_hp: int
    footprint: Footprint


class EnemyPresetUnitCatalogEntry(CamelModel):
    unit_id: str
    variant_id: str
    position: GridPosition


class EnemyPresetCatalogEntry(CamelModel):
    id: str
    display_name: str
    description: str
    units: list[EnemyPresetUnitCatalogEntry]
    terrain_features: list[TerrainFeature]


class EnemyCatalogResponse(CamelModel):
    default_enemy_preset_id: str
    enemy_variants: list[EnemyVariantCatalogEntry]
    enemy_presets: list[EnemyPresetCatalogEntry]


PlayerClassCategory = Literal["martial", "spellcaster", "half_caster"]


class PlayerClassCatalogEntry(CamelModel):
    id: str
    display_name: str
    category: PlayerClassCategory
    max_supported_level: int


class PlayerLoadoutCatalogEntry(CamelModel):
    id: str
    display_name: str
    class_id: str
    level: int
    max_hp: int
    feature_ids: list[str]
    weapon_ids: list[str]


class PlayerPresetUnitCatalogEntry(CamelModel):
    unit_id: str
    loadout_id: str


class PlayerPresetCatalogEntry(CamelModel):
    id: str
    display_name: str
    description: str
    units: list[PlayerPresetUnitCatalogEntry]


class PlayerCatalogResponse(CamelModel):
    default_player_preset_id: str
    classes: list[PlayerClassCatalogEntry]
    loadouts: list[PlayerLoadoutCatalogEntry]
    player_presets: list[PlayerPresetCatalogEntry]
