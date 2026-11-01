import type { Footprint, GridPosition, TerrainFeature } from './types';

export const GRID_SIZE = 15;
export const SINGLE_SQUARE_FOOTPRINT: Footprint = { width: 1, height: 1 };
export const LARGE_2X2_FOOTPRINT: Footprint = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 0, y: 1 },
  { x: 1, y: 1 },
];
export const HORIZONTAL_2_FOOTPRINT: Footprint = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
];
export const VERTICAL_2_FOOTPRINT: Footprint = [
  { x: 0, y: 0 },
  { x: 0, y: 1 },
];
export const HORIZONTAL_3_FOOTPRINT: Footprint = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 2, y: 0 },
];

export interface PlacementValidationResult {
  placedUnitIds: string[];
  missingUnitIds: string[];
  unexpectedUnitIds: string[];
  outOfBoundsUnitIds: string[];
  overlappingGroups: Array<{
    position: GridPosition;
    unitIds: string[];
  }>;
  blockedSquareGroups: Array<{
    position: GridPosition;
    unitIds: string[];
    terrainFeatureIds: string[];
  }>;
  isComplete: boolean;
  isValid: boolean;
  errors: string[];
}

export function positionKey(position: GridPosition): string {
  return `${position.x},${position.y}`;
}

export function getFootprintOffsets(footprint: Footprint = SINGLE_SQUARE_FOOTPRINT): GridPosition[] {
  if (Array.isArray(footprint)) {
    return footprint;
  }

  const offsets: GridPosition[] = [];

  for (let deltaX = 0; deltaX < footprint.width; deltaX += 1) {
    for (let deltaY = 0; deltaY < footprint.height; deltaY += 1) {
      offsets.push({ x: deltaX, y: deltaY });
    }
  }

  return offsets;
}

export function getFootprintDimensions(footprint: Footprint = SINGLE_SQUARE_FOOTPRINT): {
  width: number;
  height: number;
} {
  if (!Array.isArray(footprint)) {
    return footprint;
  }

  return {
    width: Math.max(...footprint.map((offset) => offset.x)) + 1,
    height: Math.max(...footprint.map((offset) => offset.y)) + 1,
  };
}

export function getOccupiedSquaresForPosition(
  position: GridPosition,
  footprint: Footprint = SINGLE_SQUARE_FOOTPRINT
): GridPosition[] {
  return getFootprintOffsets(footprint).map((offset) => ({
    x: position.x + offset.x,
    y: position.y + offset.y,
  }));
}

export function isWithinBounds(position: GridPosition, footprint: Footprint = SINGLE_SQUARE_FOOTPRINT): boolean {
  return getOccupiedSquaresForPosition(position, footprint).every(
    (square) =>
      square.x >= 1 &&
      square.x <= GRID_SIZE &&
      square.y >= 1 &&
      square.y <= GRID_SIZE
  );
}

export function terrainBlocksPlacement(feature: TerrainFeature): boolean {
  return (
    feature.kind === 'rock' ||
    feature.kind === 'boulder' ||
    feature.kind === 'column' ||
    feature.kind === 'low_wall' ||
    feature.kind === 'wall'
  );
}

export function canPlaceUnitAtPosition(
  unitId: string,
  targetPosition: GridPosition,
  placements: Record<string, GridPosition> | undefined,
  expectedUnitIds: readonly string[],
  footprintsByUnitId: Record<string, Footprint> = {},
  terrainFeatures: TerrainFeature[] = []
): boolean {
  const footprint = footprintsByUnitId[unitId] ?? SINGLE_SQUARE_FOOTPRINT;

  if (!isWithinBounds(targetPosition, footprint)) {
    return false;
  }

  const targetSquareKeys = new Set(
    getOccupiedSquaresForPosition(targetPosition, footprint).map(positionKey)
  );

  for (const feature of terrainFeatures) {
    if (!terrainBlocksPlacement(feature)) {
      continue;
    }

    for (const occupiedSquare of getOccupiedSquaresForPosition(feature.position, feature.footprint)) {
      if (targetSquareKeys.has(positionKey(occupiedSquare))) {
        return false;
      }
    }
  }

  const normalizedPlacements = placements ?? {};
  const unitIdsToCheck = new Set([...expectedUnitIds, ...Object.keys(normalizedPlacements)]);

  for (const otherUnitId of unitIdsToCheck) {
    if (otherUnitId === unitId) {
      continue;
    }

    const otherPosition = normalizedPlacements[otherUnitId];
    if (!otherPosition) {
      continue;
    }

    const otherFootprint = footprintsByUnitId[otherUnitId] ?? SINGLE_SQUARE_FOOTPRINT;

    for (const occupiedSquare of getOccupiedSquaresForPosition(otherPosition, otherFootprint)) {
      if (targetSquareKeys.has(positionKey(occupiedSquare))) {
        return false;
      }
    }
  }

  return true;
}

export function inspectPlacementsForUnitIds(
  placements: Record<string, GridPosition> | undefined,
  expectedUnitIds: readonly string[],
  footprintsByUnitId: Record<string, Footprint> = {},
  terrainFeatures: TerrainFeature[] = []
): PlacementValidationResult {
  const normalizedPlacements = placements ?? {};
  const expectedUnitSet = new Set<string>(expectedUnitIds);
  const placedUnitIds = expectedUnitIds.filter((unitId) => Boolean(normalizedPlacements[unitId]));
  const missingUnitIds = expectedUnitIds.filter((unitId) => !normalizedPlacements[unitId]);
  const unexpectedUnitIds = Object.keys(normalizedPlacements).filter((unitId) => !expectedUnitSet.has(unitId));
  const outOfBoundsUnitIds: string[] = [];
  const occupiedSquares = new Map<string, string[]>();
  const terrainOccupiedSquares = new Map<string, string[]>();
  const blockedSquareGroups = new Map<
    string,
    {
      position: GridPosition;
      unitIds: string[];
      terrainFeatureIds: string[];
    }
  >();

  for (const feature of terrainFeatures) {
    if (!terrainBlocksPlacement(feature)) {
      continue;
    }
    for (const occupiedSquare of getOccupiedSquaresForPosition(feature.position, feature.footprint)) {
      const key = positionKey(occupiedSquare);
      const featureIds = terrainOccupiedSquares.get(key) ?? [];
      featureIds.push(feature.featureId);
      terrainOccupiedSquares.set(key, featureIds);
    }
  }

  for (const unitId of placedUnitIds) {
    const position = normalizedPlacements[unitId];
    const footprint = footprintsByUnitId[unitId] ?? SINGLE_SQUARE_FOOTPRINT;

    if (!isWithinBounds(position, footprint)) {
      outOfBoundsUnitIds.push(unitId);
      continue;
    }

    for (const occupiedSquare of getOccupiedSquaresForPosition(position, footprint)) {
      const key = positionKey(occupiedSquare);
      const occupants = occupiedSquares.get(key) ?? [];
      occupants.push(unitId);
      occupiedSquares.set(key, occupants);

      const terrainFeatureIds = terrainOccupiedSquares.get(key) ?? [];
      if (terrainFeatureIds.length === 0) {
        continue;
      }

      const blockedGroup = blockedSquareGroups.get(key) ?? {
        position: occupiedSquare,
        unitIds: [],
        terrainFeatureIds: [...terrainFeatureIds]
      };
      if (!blockedGroup.unitIds.includes(unitId)) {
        blockedGroup.unitIds.push(unitId);
      }
      blockedSquareGroups.set(key, blockedGroup);
    }
  }

  const overlappingGroups = [...occupiedSquares.entries()]
    .filter(([, unitIds]) => unitIds.length > 1)
    .map(([key, unitIds]) => {
      const [x, y] = key.split(',').map(Number);
      return {
        position: { x, y },
        unitIds
      };
    });

  const errors: string[] = [];

  if (missingUnitIds.length > 0) {
    errors.push(`Missing placements for: ${missingUnitIds.join(', ')}.`);
  }

  if (unexpectedUnitIds.length > 0) {
    errors.push(`Unexpected unit ids in placement map: ${unexpectedUnitIds.join(', ')}.`);
  }

  if (outOfBoundsUnitIds.length > 0) {
    errors.push(`Out-of-bounds placements for: ${outOfBoundsUnitIds.join(', ')}.`);
  }

  for (const overlap of overlappingGroups) {
    errors.push(
      `Overlapping placements at (${overlap.position.x},${overlap.position.y}): ${overlap.unitIds.join(', ')}.`
    );
  }

  const blockedSquareGroupList = [...blockedSquareGroups.values()].sort(
    (left, right) => left.position.x - right.position.x || left.position.y - right.position.y
  );

  for (const blocked of blockedSquareGroupList) {
    errors.push(
      `Blocked terrain at (${blocked.position.x},${blocked.position.y}): ${blocked.unitIds.join(', ')} overlaps ${blocked.terrainFeatureIds.join(', ')}.`
    );
  }

  return {
    placedUnitIds,
    missingUnitIds,
    unexpectedUnitIds,
    outOfBoundsUnitIds,
    overlappingGroups,
    blockedSquareGroups: blockedSquareGroupList,
    isComplete: missingUnitIds.length === 0,
    isValid:
      missingUnitIds.length === 0 &&
      unexpectedUnitIds.length === 0 &&
      outOfBoundsUnitIds.length === 0 &&
      overlappingGroups.length === 0 &&
      blockedSquareGroupList.length === 0,
    errors
  };
}
