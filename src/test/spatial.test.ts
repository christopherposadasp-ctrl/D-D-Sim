import { describe, expect, it } from 'vitest';

import { createEncounter } from '../engine';
import { DEFAULT_POSITIONS } from '../engine/constants';
import { findPathToAdjacentSquare, getAttackContext, pathProvokesOpportunityAttack } from '../engine/spatial';

describe('spatial rules', () => {
  it('grants flanking for melee attacks when an adjacent ally forms an angle greater than 90 degrees', () => {
    const encounter = createEncounter({ seed: 'flanking-obtuse', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 4 };
    encounter.units.G1.position = { x: 5, y: 5 };
    encounter.units.F2.position = { x: 6, y: 6 };

    const context = getAttackContext(encounter, 'F1', 'G1', encounter.units.F1.attacks.greatsword!);

    expect(context.legal).toBe(true);
    expect(context.advantageSources).toContain('flanking');
  });

  it('does not grant flanking when the supporting ally is only at a right angle to the attacker', () => {
    const encounter = createEncounter({ seed: 'no-flanking-right-angle', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 4 };
    encounter.units.G1.position = { x: 5, y: 5 };
    encounter.units.F2.position = { x: 6, y: 5 };

    const context = getAttackContext(encounter, 'F1', 'G1', encounter.units.F1.attacks.greatsword!);

    expect(context.legal).toBe(true);
    expect(context.advantageSources).not.toContain('flanking');
  });

  it('does not grant flanking from unconscious allies or for ranged attacks', () => {
    const encounter = createEncounter({ seed: 'no-flanking-ranged', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 4 };
    encounter.units.G1.position = { x: 5, y: 5 };
    encounter.units.F2.position = { x: 6, y: 6 };
    encounter.units.F2.currentHp = 0;
    encounter.units.F2.conditions.unconscious = true;
    encounter.units.F2.conditions.prone = true;
    encounter.units.F3.position = { x: 4, y: 5 };

    const meleeContext = getAttackContext(encounter, 'F1', 'G1', encounter.units.F1.attacks.greatsword!);
    const rangedContext = getAttackContext(encounter, 'F3', 'G1', encounter.units.F3.attacks.javelin!);

    expect(meleeContext.advantageSources).not.toContain('flanking');
    expect(rangedContext.advantageSources).not.toContain('flanking');
  });

  it('applies ranged-in-melee disadvantage when an enemy is adjacent to the attacker', () => {
    const encounter = createEncounter({ seed: 'adjacent-enemy', placements: DEFAULT_POSITIONS });
    encounter.units.G5.position = { x: 5, y: 5 };
    encounter.units.F1.position = { x: 8, y: 5 };
    encounter.units.F2.position = { x: 5, y: 6 };

    const context = getAttackContext(encounter, 'G5', 'F1', encounter.units.G5.attacks.shortbow!);

    expect(context.legal).toBe(true);
    expect(context.disadvantageSources).toContain('adjacent_enemy');
  });

  it('ignores unconscious adjacent enemies for ranged-in-melee disadvantage', () => {
    const encounter = createEncounter({ seed: 'unconscious-adjacent-enemy', placements: DEFAULT_POSITIONS });
    encounter.units.G5.position = { x: 5, y: 5 };
    encounter.units.F1.position = { x: 8, y: 5 };
    encounter.units.F2.position = { x: 5, y: 6 };
    encounter.units.F2.currentHp = 0;
    encounter.units.F2.conditions.unconscious = true;
    encounter.units.F2.conditions.prone = true;

    const context = getAttackContext(encounter, 'G5', 'F1', encounter.units.G5.attacks.shortbow!);

    expect(context.legal).toBe(true);
    expect(context.disadvantageSources).not.toContain('adjacent_enemy');
  });

  it('applies long-range disadvantage and half cover for ranged attacks', () => {
    const encounter = createEncounter({ seed: 'range-and-cover', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 1, y: 1 };
    encounter.units.G1.position = { x: 10, y: 1 };
    encounter.units.F2.position = { x: 5, y: 1 };

    const context = getAttackContext(encounter, 'F1', 'G1', encounter.units.F1.attacks.javelin!);

    expect(context.legal).toBe(true);
    expect(context.withinNormalRange).toBe(false);
    expect(context.withinLongRange).toBe(true);
    expect(context.disadvantageSources).toContain('long_range');
    expect(context.coverAcBonus).toBe(2);
  });

  it('finds a shortest path to an open square adjacent to the target', () => {
    const encounter = createEncounter({ seed: 'shortest-path', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 1, y: 1 };
    encounter.units.G1.position = { x: 4, y: 1 };

    const path = findPathToAdjacentSquare(encounter, 'F1', 'G1', 6);

    expect(path).not.toBeNull();
    expect(path?.path).toEqual([
      { x: 1, y: 1 },
      { x: 2, y: 1 },
      { x: 3, y: 1 }
    ]);
    expect(path?.distance).toBe(2);
  });

  it('detects when a movement path leaves an enemy reach and provokes an opportunity attack', () => {
    const encounter = createEncounter({ seed: 'provokes-opportunity-attack', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 5 };
    encounter.units.G1.position = { x: 6, y: 5 };

    expect(
      pathProvokesOpportunityAttack(encounter, 'F1', [
        { x: 5, y: 5 },
        { x: 5, y: 6 }
      ])
    ).toBe(false);
    expect(
      pathProvokesOpportunityAttack(encounter, 'F1', [
        { x: 5, y: 5 },
        { x: 5, y: 6 },
        { x: 5, y: 7 }
      ])
    ).toBe(true);
  });
});
