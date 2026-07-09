import { describe, expect, it } from 'vitest';

import {
  GRID_SIZE,
  SINGLE_SQUARE_FOOTPRINT,
  getOccupiedSquaresForPosition,
  inspectPlacementsForUnitIds,
  isWithinBounds,
} from '../shared/sim/spatial';

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
});
