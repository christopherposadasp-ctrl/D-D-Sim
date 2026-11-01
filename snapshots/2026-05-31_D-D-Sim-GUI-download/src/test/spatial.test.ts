import { describe, expect, it } from 'vitest';

import {
  GRID_SIZE,
  SINGLE_SQUARE_FOOTPRINT,
  canPlaceUnitAtPosition,
  getOccupiedSquaresForPosition,
  inspectPlacementsForUnitIds,
  isWithinBounds,
  terrainBlocksPlacement,
} from '../shared/sim/spatial';
import { getTerrainFeaturesForPreset } from '../shared/sim/catalog';

describe('shared spatial helpers', () => {
  it('lists all occupied squares for a large footprint from its top-left anchor', () => {
    expect(getOccupiedSquaresForPosition({ x: 10, y: 7 }, { width: 2, height: 2 })).toEqual([
      { x: 10, y: 7 },
      { x: 10, y: 8 },
      { x: 11, y: 7 },
      { x: 11, y: 8 },
    ]);
  });

  it('accepts legal in-bounds placements', () => {
    expect(isWithinBounds({ x: 1, y: 1 }, SINGLE_SQUARE_FOOTPRINT)).toBe(true);
    expect(isWithinBounds({ x: GRID_SIZE - 1, y: GRID_SIZE - 1 }, { width: 2, height: 2 })).toBe(true);
  });

  it('rejects out-of-bounds large placements', () => {
    expect(isWithinBounds({ x: GRID_SIZE, y: GRID_SIZE }, { width: 2, height: 2 })).toBe(false);
  });

  it('reports missing placements and footprint overlaps', () => {
    const validation = inspectPlacementsForUnitIds(
      {
        F1: { x: 1, y: 7 },
        E1: { x: 10, y: 7 },
        E2: { x: 11, y: 8 },
      },
      ['F1', 'F2', 'E1', 'E2'],
      {
        F1: SINGLE_SQUARE_FOOTPRINT,
        F2: SINGLE_SQUARE_FOOTPRINT,
        E1: { width: 2, height: 2 },
        E2: SINGLE_SQUARE_FOOTPRINT,
      },
    );

    expect(validation.isValid).toBe(false);
    expect(validation.missingUnitIds).toEqual(['F2']);
    expect(validation.overlappingGroups).toEqual([
      {
        position: { x: 11, y: 8 },
        unitIds: ['E1', 'E2'],
      },
    ]);
  });

  it('accepts complete placement maps for mixed unit footprints', () => {
    const validation = inspectPlacementsForUnitIds(
      {
        F1: { x: 1, y: 7 },
        F2: { x: 1, y: 8 },
        F3: { x: 1, y: 9 },
        E1: { x: 9, y: 7 },
        E2: { x: 11, y: 5 },
        E3: { x: 11, y: 9 },
      },
      ['F1', 'F2', 'F3', 'E1', 'E2', 'E3'],
      {
        F1: SINGLE_SQUARE_FOOTPRINT,
        F2: SINGLE_SQUARE_FOOTPRINT,
        F3: SINGLE_SQUARE_FOOTPRINT,
        E1: { width: 2, height: 2 },
        E2: { width: 2, height: 2 },
        E3: { width: 2, height: 2 },
      },
    );

    expect(validation.isValid).toBe(true);
    expect(validation.errors).toEqual([]);
  });

  it('rejects target positions that collide through the selected unit footprint', () => {
    const placements = {
      D1: { x: 10, y: 5 },
      E1: { x: 9, y: 8 },
      F1: { x: 1, y: 7 },
    };
    const footprints = {
      D1: { width: 2, height: 2 },
      E1: { width: 2, height: 2 },
      F1: SINGLE_SQUARE_FOOTPRINT,
    };

    expect(
      canPlaceUnitAtPosition('D1', { x: 8, y: 9 }, placements, ['D1', 'E1', 'F1'], footprints)
    ).toBe(false);
    expect(
      canPlaceUnitAtPosition('D1', { x: GRID_SIZE, y: GRID_SIZE }, placements, ['D1', 'E1', 'F1'], footprints)
    ).toBe(false);
    expect(
      canPlaceUnitAtPosition(
        'D1',
        { x: 4, y: 7 },
        placements,
        ['D1', 'E1', 'F1'],
        footprints,
        [{ featureId: 'rock_1', kind: 'rock', position: { x: 5, y: 8 }, footprint: SINGLE_SQUARE_FOOTPRINT }]
      )
    ).toBe(false);
    expect(
      canPlaceUnitAtPosition('D1', { x: 12, y: 6 }, placements, ['D1', 'E1', 'F1'], footprints)
    ).toBe(true);
  });

  it('rejects placements onto blocked terrain squares', () => {
    const validation = inspectPlacementsForUnitIds(
      {
        F1: { x: 5, y: 8 },
        E1: { x: 10, y: 7 }
      },
      ['F1', 'E1'],
      {
        F1: SINGLE_SQUARE_FOOTPRINT,
        E1: { width: 2, height: 2 }
      },
      [{ featureId: 'rock_1', kind: 'rock', position: { x: 5, y: 8 }, footprint: SINGLE_SQUARE_FOOTPRINT }]
    );

    expect(validation.isValid).toBe(false);
    expect(validation.blockedSquareGroups).toEqual([
      {
        position: { x: 5, y: 8 },
        unitIds: ['F1'],
        terrainFeatureIds: ['rock_1']
      }
    ]);
  });

  it('treats low wall footprints as blocked terrain squares', () => {
    const validation = inspectPlacementsForUnitIds(
      {
        F1: { x: 5, y: 8 }
      },
      ['F1'],
      {
        F1: SINGLE_SQUARE_FOOTPRINT
      },
      [{ featureId: 'low_wall_1', kind: 'low_wall', position: { x: 5, y: 8 }, footprint: SINGLE_SQUARE_FOOTPRINT }]
    );

    expect(validation.isValid).toBe(false);
    expect(validation.blockedSquareGroups).toEqual([
      {
        position: { x: 5, y: 8 },
        unitIds: ['F1'],
        terrainFeatureIds: ['low_wall_1']
      }
    ]);
  });

  it('treats columns as blocking terrain', () => {
    const column = { featureId: 'column_1', kind: 'column' as const, position: { x: 5, y: 8 }, footprint: SINGLE_SQUARE_FOOTPRINT };
    const validation = inspectPlacementsForUnitIds(
      {
        F1: { x: 5, y: 8 }
      },
      ['F1'],
      {
        F1: SINGLE_SQUARE_FOOTPRINT
      },
      [column]
    );

    expect(terrainBlocksPlacement(column)).toBe(true);
    expect(validation.isValid).toBe(false);
    expect(validation.blockedSquareGroups).toEqual([
      {
        position: { x: 5, y: 8 },
        unitIds: ['F1'],
        terrainFeatureIds: ['column_1']
      }
    ]);
  });

  it('returns manual Frozen Courtyard Dragon Test terrain coordinates', () => {
    const terrain = getTerrainFeaturesForPreset('frozen_courtyard_dragon_test');

    expect(terrain).toEqual([
      { featureId: 'frozen-column-1', kind: 'column', position: { x: 4, y: 12 }, footprint: SINGLE_SQUARE_FOOTPRINT },
      { featureId: 'frozen-column-2', kind: 'column', position: { x: 5, y: 10 }, footprint: SINGLE_SQUARE_FOOTPRINT },
      { featureId: 'frozen-column-3', kind: 'column', position: { x: 4, y: 5 }, footprint: SINGLE_SQUARE_FOOTPRINT },
      { featureId: 'frozen-column-4', kind: 'column', position: { x: 5, y: 6 }, footprint: SINGLE_SQUARE_FOOTPRINT },
      { featureId: 'frozen-column-5', kind: 'column', position: { x: 6, y: 6 }, footprint: SINGLE_SQUARE_FOOTPRINT },
      {
        featureId: 'frozen-rock-1',
        kind: 'rock',
        position: { x: 4, y: 8 },
        footprint: [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
          { x: 0, y: 1 },
          { x: 1, y: 1 },
        ],
      },
      {
        featureId: 'frozen-wall-1',
        kind: 'wall',
        position: { x: 7, y: 5 },
        footprint: [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
        ],
      },
      {
        featureId: 'frozen-wall-2',
        kind: 'wall',
        position: { x: 7, y: 12 },
        footprint: [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
        ],
      },
    ]);

    expect(getOccupiedSquaresForPosition(terrain[5].position, terrain[5].footprint)).toEqual([
      { x: 4, y: 8 },
      { x: 5, y: 8 },
      { x: 4, y: 9 },
      { x: 5, y: 9 },
    ]);
    expect(getOccupiedSquaresForPosition(terrain[6].position, terrain[6].footprint)).toEqual([
      { x: 7, y: 5 },
      { x: 8, y: 5 },
    ]);
    expect(getOccupiedSquaresForPosition(terrain[7].position, terrain[7].footprint)).toEqual([
      { x: 7, y: 12 },
      { x: 8, y: 12 },
    ]);
  });
});
