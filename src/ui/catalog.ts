import type {
  EnemyCatalogResponse,
  EnemyPresetCatalogEntry,
  Footprint,
  GridPosition,
  PlayerCatalogResponse,
  PlayerLoadoutCatalogEntry,
  PlayerPresetCatalogEntry,
  TerrainFeature
} from '../shared/sim/types';

export const DEFAULT_SEED = 'fighters-vs-goblin-screen-001';
export const DEFAULT_PARTY_MAX_HP = 154;
export const MAX_BATCH_SIZE = 1000;

export const FIGHTER_IDS = ['F1', 'F2', 'F3', 'F4'] as const;
export const MEDIUM_FOOTPRINT: Footprint = { width: 1, height: 1 };
export const DEFAULT_FIGHTER_POSITIONS: Record<(typeof FIGHTER_IDS)[number], GridPosition> = {
  F1: { x: 1, y: 7 },
  F2: { x: 1, y: 8 },
  F3: { x: 1, y: 9 },
  F4: { x: 1, y: 10 }
};

function buildEnemyVariantMap(catalog: EnemyCatalogResponse): Map<string, EnemyCatalogResponse['enemyVariants'][number]> {
  return new Map(catalog.enemyVariants.map((variant) => [variant.id, variant]));
}

function buildPlayerLoadoutMap(
  catalog: PlayerCatalogResponse
): Map<string, PlayerLoadoutCatalogEntry> {
  return new Map(catalog.loadouts.map((loadout) => [loadout.id, loadout]));
}

export function getEnemyPreset(catalog: EnemyCatalogResponse | null, presetId: string): EnemyPresetCatalogEntry | null {
  if (!catalog) {
    return null;
  }

  return catalog.enemyPresets.find((preset) => preset.id === presetId) ?? null;
}

export function getPlayerPreset(
  catalog: PlayerCatalogResponse | null,
  presetId: string
): PlayerPresetCatalogEntry | null {
  if (!catalog) {
    return null;
  }

  return catalog.playerPresets.find((preset) => preset.id === presetId) ?? null;
}

export function getActiveUnitIdsForPreset(catalog: EnemyCatalogResponse | null, presetId: string): string[] {
  return getCombinedUnitIds(catalog, presetId, null, '');
}

export function getTerrainFeaturesForPreset(
  catalog: EnemyCatalogResponse | null,
  presetId: string
): TerrainFeature[] {
  return getEnemyPreset(catalog, presetId)?.terrainFeatures ?? [];
}

export function getDefaultPlacementsForPreset(
  catalog: EnemyCatalogResponse | null,
  presetId: string,
  playerCatalog: PlayerCatalogResponse | null = null,
  playerPresetId = ''
): Record<string, GridPosition> {
  const preset = getEnemyPreset(catalog, presetId);
  const placements: Record<string, GridPosition> = getDefaultPlayerPlacements(playerCatalog, playerPresetId);

  if (!preset) {
    return placements;
  }

  for (const unit of preset.units) {
    placements[unit.unitId] = { ...unit.position };
  }

  return placements;
}

export function getPlacementFootprintsForPreset(
  catalog: EnemyCatalogResponse | null,
  presetId: string,
  playerCatalog: PlayerCatalogResponse | null = null,
  playerPresetId = ''
): Record<string, Footprint> {
  const footprints: Record<string, Footprint> = getDefaultPlayerFootprints(playerCatalog, playerPresetId);

  if (!catalog) {
    return footprints;
  }

  const preset = getEnemyPreset(catalog, presetId);
  if (!preset) {
    return footprints;
  }

  const enemyVariantMap = buildEnemyVariantMap(catalog);

  for (const unit of preset.units) {
    footprints[unit.unitId] = enemyVariantMap.get(unit.variantId)?.footprint ?? MEDIUM_FOOTPRINT;
  }

  return footprints;
}

export function getActivePlayerUnitIds(
  playerCatalog: PlayerCatalogResponse | null,
  presetId: string
): string[] {
  const preset = getPlayerPreset(playerCatalog, presetId);
  return preset ? preset.units.map((unit) => unit.unitId) : [...FIGHTER_IDS];
}

export function getCombinedUnitIds(
  enemyCatalog: EnemyCatalogResponse | null,
  enemyPresetId: string,
  playerCatalog: PlayerCatalogResponse | null,
  playerPresetId: string
): string[] {
  const enemyPreset = getEnemyPreset(enemyCatalog, enemyPresetId);
  const playerUnitIds = getActivePlayerUnitIds(playerCatalog, playerPresetId);
  return enemyPreset ? [...playerUnitIds, ...enemyPreset.units.map((unit) => unit.unitId)] : playerUnitIds;
}

export function getDefaultPlayerPlacements(
  playerCatalog: PlayerCatalogResponse | null,
  playerPresetId: string
): Record<string, GridPosition> {
  const playerUnitIds = getActivePlayerUnitIds(playerCatalog, playerPresetId);
  return Object.fromEntries(playerUnitIds.map((unitId) => [unitId, { ...DEFAULT_FIGHTER_POSITIONS[unitId as keyof typeof DEFAULT_FIGHTER_POSITIONS] }]));
}

export function getDefaultPlayerFootprints(
  playerCatalog: PlayerCatalogResponse | null,
  playerPresetId: string
): Record<string, Footprint> {
  const playerUnitIds = getActivePlayerUnitIds(playerCatalog, playerPresetId);
  return Object.fromEntries(playerUnitIds.map((unitId) => [unitId, MEDIUM_FOOTPRINT]));
}

export function getPlayerUnitDisplayName(
  playerCatalog: PlayerCatalogResponse | null,
  playerPresetId: string,
  unitId: string
): string {
  const preset = getPlayerPreset(playerCatalog, playerPresetId);
  if (!preset || !playerCatalog) {
    return unitId;
  }

  const presetUnit = preset.units.find((unit) => unit.unitId === unitId);
  if (!presetUnit) {
    return unitId;
  }

  return buildPlayerLoadoutMap(playerCatalog).get(presetUnit.loadoutId)?.displayName ?? presetUnit.loadoutId;
}

export function getUnitDisplayName(
  enemyCatalog: EnemyCatalogResponse | null,
  playerCatalog: PlayerCatalogResponse | null,
  enemyPresetId: string,
  playerPresetId: string,
  unitId: string
): string {
  if (unitId.startsWith('F')) {
    return getPlayerUnitDisplayName(playerCatalog, playerPresetId, unitId);
  }

  const preset = getEnemyPreset(enemyCatalog, enemyPresetId);
  if (!preset || !enemyCatalog) {
    return unitId;
  }

  const presetUnit = preset.units.find((unit) => unit.unitId === unitId);
  if (!presetUnit) {
    return unitId;
  }

  return buildEnemyVariantMap(enemyCatalog).get(presetUnit.variantId)?.displayName ?? presetUnit.variantId;
}

export function getTotalEnemyMaxHpForPreset(catalog: EnemyCatalogResponse | null, presetId: string): number {
  const preset = getEnemyPreset(catalog, presetId);
  if (!preset || !catalog) {
    return 0;
  }

  const enemyVariantMap = buildEnemyVariantMap(catalog);
  return preset.units.reduce((total, unit) => total + (enemyVariantMap.get(unit.variantId)?.maxHp ?? 0), 0);
}

export function getTotalPlayerMaxHpForPreset(
  catalog: PlayerCatalogResponse | null,
  presetId: string
): number {
  const preset = getPlayerPreset(catalog, presetId);
  if (!preset || !catalog) {
    return DEFAULT_PARTY_MAX_HP;
  }

  const playerLoadoutMap = buildPlayerLoadoutMap(catalog);
  return preset.units.reduce((total, unit) => total + (playerLoadoutMap.get(unit.loadoutId)?.maxHp ?? 0), 0);
}
