import { describe, expect, it } from 'vitest';

import { createEncounter } from '../engine';
import { DEFAULT_POSITIONS } from '../engine/constants';
import {
  applyGreatWeaponFighting,
  chooseDamageCandidate,
  recalculateEffectiveSpeed,
  resolveAttack,
  resolveDeathSave
} from '../engine/rules';

describe('rule helpers', () => {
  it('replaces 1s and 2s for Great Weapon Fighting', () => {
    expect(applyGreatWeaponFighting([1, 2, 3, 6])).toEqual([3, 3, 3, 6]);
  });

  it('prefers the better Savage Attacker candidate', () => {
    const choice = chooseDamageCandidate(
      {
        rawRolls: [1, 4],
        adjustedRolls: [3, 4],
        subtotal: 7
      },
      {
        rawRolls: [6, 6],
        adjustedRolls: [6, 6],
        subtotal: 12
      }
    );

    expect(choice.chosen).toBe('savage');
    expect(choice.candidate.subtotal).toBe(12);
  });

  it('caps slow penalties at 10 feet', () => {
    const encounter = createEncounter({ seed: 'slow-speed', placements: DEFAULT_POSITIONS });
    const slowed = recalculateEffectiveSpeed({
      ...encounter.units.G1,
      temporaryEffects: [
        { kind: 'slow', sourceId: 'F1', expiresAtTurnStartOf: 'F1', penalty: 10 },
        { kind: 'slow', sourceId: 'F2', expiresAtTurnStartOf: 'F2', penalty: 10 }
      ]
    });

    expect(slowed.effectiveSpeed).toBe(20);
  });

  it('resolves a natural 20 death save into 1 HP', () => {
    const encounter = createEncounter({ seed: 'death-save', placements: DEFAULT_POSITIONS });
    encounter.units.F1.currentHp = 0;
    encounter.units.F1.conditions.unconscious = true;
    encounter.units.F1.conditions.prone = true;

    resolveDeathSave(encounter, 'F1', 20);

    expect(encounter.units.F1.currentHp).toBe(1);
    expect(encounter.units.F1.conditions.unconscious).toBe(false);
  });

  it('applies graze damage on a miss and removes goblins at 0 HP', () => {
    const encounter = createEncounter({ seed: 'graze-kill', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 5 };
    encounter.units.G1.position = { x: 6, y: 5 };
    encounter.units.G1.currentHp = 3;

    const attack = resolveAttack(encounter, {
      attackerId: 'F1',
      targetId: 'G1',
      weaponId: 'greatsword',
      savageAttackerAvailable: false,
      overrides: {
        attackRolls: [2]
      }
    });

    expect(attack.event.damageDetails?.masteryApplied).toBe('graze');
    expect(encounter.units.G1.conditions.dead).toBe(true);
  });

  it('treats melee hits against unconscious fighters as critical hits', () => {
    const encounter = createEncounter({ seed: 'auto-crit', placements: DEFAULT_POSITIONS });
    encounter.units.G1.position = { x: 6, y: 5 };
    encounter.units.F1.position = { x: 5, y: 5 };
    encounter.units.F1.currentHp = 0;
    encounter.units.F1.conditions.unconscious = true;
    encounter.units.F1.conditions.prone = true;

    const attack = resolveAttack(encounter, {
      attackerId: 'G1',
      targetId: 'F1',
      weaponId: 'scimitar',
      savageAttackerAvailable: false,
      overrides: {
        attackRolls: [12, 5],
        damageRolls: [1],
        advantageDamageRolls: [1]
      }
    });

    expect(attack.event.resolvedTotals.critical).toBe(true);
    expect(encounter.units.F1.deathSaveFailures).toBe(2);
  });

  it('cancels unconscious advantage with prone disadvantage for ranged attacks from distance', () => {
    const encounter = createEncounter({ seed: 'ranged-vs-unconscious-prone', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 5 };
    encounter.units.F1.currentHp = 0;
    encounter.units.F1.conditions.unconscious = true;
    encounter.units.F1.conditions.prone = true;
    encounter.units.G5.position = { x: 8, y: 5 };

    const attack = resolveAttack(encounter, {
      attackerId: 'G5',
      targetId: 'F1',
      weaponId: 'shortbow',
      savageAttackerAvailable: false,
      overrides: {
        attackRolls: [12]
      }
    });

    expect(attack.event.resolvedTotals.attackMode).toBe('normal');
    expect(attack.event.rawRolls.advantageSources).toEqual(['target_unconscious']);
    expect(attack.event.rawRolls.disadvantageSources).toEqual(['target_prone']);
  });

  it('uses flanking to grant advantage on melee attacks', () => {
    const encounter = createEncounter({ seed: 'flanking-advantage', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 5, y: 4 };
    encounter.units.G1.position = { x: 5, y: 5 };
    encounter.units.F2.position = { x: 6, y: 6 };

    const attack = resolveAttack(encounter, {
      attackerId: 'F1',
      targetId: 'G1',
      weaponId: 'greatsword',
      savageAttackerAvailable: false,
      overrides: {
        attackRolls: [4, 16],
        damageRolls: [3, 4]
      }
    });

    expect(attack.event.rawRolls.advantageSources).toContain('flanking');
    expect(attack.event.resolvedTotals.attackMode).toBe('advantage');
    expect(attack.event.resolvedTotals.selectedRoll).toBe(16);
  });
});
