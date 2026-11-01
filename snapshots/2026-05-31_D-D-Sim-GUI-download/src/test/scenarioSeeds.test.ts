import { describe, expect, it } from 'vitest';

import { getFixedScenarioSeed } from '../shared/sim/scenarioSeeds';

describe('fixed scenario seeds', () => {
  it('loads the Frostfall Courtyard Variant fixed seed and clones placements', () => {
    const first = getFixedScenarioSeed('frostfall_courtyard_variant');
    const second = getFixedScenarioSeed('frostfall_courtyard_variant');

    expect(first).toMatchObject({
      seed: 'frostfall-variant-0034',
      scenarioName: 'Frostfall Courtyard Variant',
      description:
        'A frozen ruined courtyard where kobolds screen the party before a young white dragon enters from the storm on round 3.',
      enemyPresetId: 'frostfall_courtyard_variant',
      playerPresetId: 'martial_mixed_party',
      playerBehavior: 'smart',
      monsterBehavior: 'balanced',
      selectedUnitId: 'F1',
    });
    expect(first?.initialState?.round).toBe(1);
    expect(first?.initialState?.units.E17).toBeUndefined();
    expect(first?.initialState?.units.E1.templateName).toBe('Kobold Warrior');
    expect(first?.delayedArrivals?.[0]).toMatchObject({
      round: 3,
      unitId: 'E17',
      combatRole: 'young_white_dragon_boss',
      templateName: 'Young White Dragon Boss',
      position: { x: 9, y: 8 },
      initiativeScore: 15,
    });
    expect(first?.delayedArrivals?.[0]?.unit?.footprint).toEqual({ width: 3, height: 3 });
    expect(first?.placements.F1).toEqual({ x: 4, y: 12 });
    expect(first?.placements.E16).toEqual({ x: 3, y: 15 });
    expect(first?.placements.E17).toBeUndefined();
    expect(first?.placements).not.toBe(second?.placements);
    expect(first?.placements.F1).not.toBe(second?.placements.F1);
    expect(first?.initialState).not.toBe(second?.initialState);
  });

  it('returns null for scenarios without fixed seeds', () => {
    expect(getFixedScenarioSeed('skyhunter_pincer')).toBeNull();
  });
});
