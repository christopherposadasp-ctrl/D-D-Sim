import { describe, expect, it } from 'vitest';

import { chooseTurnDecision } from '../engine/ai';
import { createEncounter } from '../engine';
import { ARCHER_GOBLIN_IDS, DEFAULT_POSITIONS, MELEE_GOBLIN_IDS } from '../engine/constants';
import type { GridPosition } from '../engine/types';

function buildPlacements(overrides: Partial<Record<string, GridPosition>> = {}): Record<string, GridPosition> {
  return {
    F1: { x: 1, y: 1 },
    F2: { x: 1, y: 3 },
    F3: { x: 1, y: 5 },
    G1: { x: 15, y: 1 },
    G2: { x: 15, y: 3 },
    G3: { x: 15, y: 5 },
    G4: { x: 15, y: 7 },
    G5: { x: 15, y: 9 },
    G6: { x: 15, y: 11 },
    G7: { x: 15, y: 13 },
    ...overrides
  };
}

describe('fighter decision logic', () => {
  it('dashes from the default opening position instead of throwing a long-range javelin', () => {
    const encounter = createEncounter({ seed: 'fighter-open-dash', placements: DEFAULT_POSITIONS });

    const decision = chooseTurnDecision(encounter, 'F1');

    expect(decision.action.kind).toBe('dash');
    expect(decision.postActionMovement?.mode).toBe('dash');
  });

  it('moves to normal javelin range and attacks when melee is still unavailable', () => {
    const encounter = createEncounter({ seed: 'fighter-move-javelin', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 1, y: 1 };
    encounter.units.G1.position = { x: 9, y: 1 };

    const decision = chooseTurnDecision(encounter, 'F1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'G1',
      weaponId: 'javelin'
    });
    expect(decision.preActionMovement?.mode).toBe('move');
    expect(decision.preActionMovement?.path).toEqual([
      { x: 1, y: 1 },
      { x: 2, y: 1 },
      { x: 3, y: 1 }
    ]);
    expect(decision.postActionMovement?.mode).toBe('move');
    expect(decision.postActionMovement?.path).toEqual([
      { x: 3, y: 1 },
      { x: 4, y: 1 },
      { x: 5, y: 1 },
      { x: 6, y: 1 },
      { x: 7, y: 1 }
    ]);
  });

  it('prefers a flanking melee square for smart players while dumb players take the first adjacent square', () => {
    const smartEncounter = createEncounter({
      seed: 'smart-flank-choice',
      placements: DEFAULT_POSITIONS,
      playerBehavior: 'smart'
    });
    smartEncounter.units.F1.position = { x: 3, y: 5 };
    smartEncounter.units.F2.position = { x: 5, y: 4 };
    smartEncounter.units.G1.position = { x: 5, y: 5 };

    const dumbEncounter = createEncounter({
      seed: 'dumb-flank-choice',
      placements: DEFAULT_POSITIONS,
      playerBehavior: 'dumb'
    });
    dumbEncounter.units.F1.position = { x: 3, y: 5 };
    dumbEncounter.units.F2.position = { x: 5, y: 4 };
    dumbEncounter.units.G1.position = { x: 5, y: 5 };

    const smartDecision = chooseTurnDecision(smartEncounter, 'F1');
    const dumbDecision = chooseTurnDecision(dumbEncounter, 'F1');

    expect(smartDecision.action).toEqual({
      kind: 'attack',
      targetId: 'G1',
      weaponId: 'greatsword'
    });
    expect(smartDecision.preActionMovement?.path).toEqual([
      { x: 3, y: 5 },
      { x: 4, y: 6 }
    ]);
    expect(dumbDecision.preActionMovement?.path).toEqual([
      { x: 3, y: 5 },
      { x: 4, y: 4 }
    ]);
  });

  it('targets weaker enemies for smart players while dumb players default to the nearest tie-break', () => {
    const smartEncounter = createEncounter({
      seed: 'smart-target-priority',
      placements: DEFAULT_POSITIONS,
      playerBehavior: 'smart'
    });
    smartEncounter.units.F1.position = { x: 5, y: 5 };
    smartEncounter.units.G1.position = { x: 6, y: 5 };
    smartEncounter.units.G2.position = { x: 6, y: 6 };
    smartEncounter.units.G2.currentHp = 1;

    const dumbEncounter = createEncounter({
      seed: 'dumb-target-priority',
      placements: DEFAULT_POSITIONS,
      playerBehavior: 'dumb'
    });
    dumbEncounter.units.F1.position = { x: 5, y: 5 };
    dumbEncounter.units.G1.position = { x: 6, y: 5 };
    dumbEncounter.units.G2.position = { x: 6, y: 6 };
    dumbEncounter.units.G2.currentHp = 1;

    const smartDecision = chooseTurnDecision(smartEncounter, 'F1');
    const dumbDecision = chooseTurnDecision(dumbEncounter, 'F1');

    expect(smartDecision.action).toEqual({
      kind: 'attack',
      targetId: 'G2',
      weaponId: 'greatsword'
    });
    expect(dumbDecision.action).toEqual({
      kind: 'attack',
      targetId: 'G1',
      weaponId: 'greatsword'
    });
  });

  it('keeps attacking an adjacent goblin instead of provoking to chase a weaker target', () => {
    const encounter = createEncounter({
      seed: 'smart-avoid-opportunity-attack',
      placements: buildPlacements({
        F1: { x: 5, y: 5 },
        G1: { x: 6, y: 5 },
        G2: { x: 8, y: 8 }
      }),
      playerBehavior: 'smart'
    });
    encounter.units.G2.currentHp = 1;

    const decision = chooseTurnDecision(encounter, 'F1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'G1',
      weaponId: 'greatsword'
    });
    expect(decision.preActionMovement).toBeUndefined();
  });
});

describe('goblin role split', () => {
  it('assigns four melee goblins and three archers with the expected weapon loadouts', () => {
    const encounter = createEncounter({ seed: 'goblin-roles', placements: DEFAULT_POSITIONS });

    for (const goblinId of MELEE_GOBLIN_IDS) {
      expect(encounter.units[goblinId].combatRole).toBe('goblin_melee');
      expect(encounter.units[goblinId].attacks.shortbow).toBeUndefined();
      expect(encounter.units[goblinId].attacks.scimitar).toBeDefined();
    }

    for (const goblinId of ARCHER_GOBLIN_IDS) {
      expect(encounter.units[goblinId].combatRole).toBe('goblin_archer');
      expect(encounter.units[goblinId].attacks.shortbow).toBeDefined();
      expect(encounter.units[goblinId].attacks.scimitar).toBeDefined();
    }
  });

  it('has melee goblins close into melee while archers keep shortbow behavior', () => {
    const encounter = createEncounter({ seed: 'goblin-role-ai', placements: DEFAULT_POSITIONS });

    const meleeDecision = chooseTurnDecision(encounter, 'G1');
    const archerDecision = chooseTurnDecision(encounter, 'G5');

    expect(meleeDecision.action.kind).toBe('dash');
    expect(meleeDecision.postActionMovement?.mode).toBe('dash');
    expect(archerDecision.action).toEqual({
      kind: 'attack',
      targetId: 'F1',
      weaponId: 'shortbow'
    });
  });

  it('has melee goblins stay on an adjacent fighter instead of provoking to chase a weaker target', () => {
    const encounter = createEncounter({
      seed: 'goblin-melee-avoid-opportunity-attack',
      placements: buildPlacements({
        F1: { x: 5, y: 5 },
        F2: { x: 8, y: 8 },
        G1: { x: 6, y: 5 }
      })
    });
    encounter.units.F2.currentHp = 1;

    const decision = chooseTurnDecision(encounter, 'G1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'F1',
      weaponId: 'scimitar'
    });
    expect(decision.preActionMovement).toBeUndefined();
  });

  it('lets archer goblins disengage and retreat before firing when adjacent to a fighter', () => {
    const encounter = createEncounter({
      seed: 'goblin-archer-disengage-shot',
      placements: buildPlacements({
        F1: { x: 5, y: 5 },
        F2: { x: 10, y: 5 },
        G5: { x: 6, y: 5 }
      })
    });

    const decision = chooseTurnDecision(encounter, 'G5');

    expect(decision.bonusAction).toEqual({
      kind: 'disengage',
      timing: 'before_action'
    });
    expect(decision.preActionMovement?.mode).toBe('move');
    expect((decision.preActionMovement?.path.length ?? 0) > 1).toBe(true);
    expect(decision.action).toMatchObject({
      kind: 'attack',
      weaponId: 'shortbow'
    });
  });
});

describe('monster behavior settings', () => {
  it('kind goblins ignore downed fighters and focus the healthiest conscious target', () => {
    const encounter = createEncounter({
      seed: 'kind-monster-targeting',
      placements: buildPlacements({
        F1: { x: 5, y: 5 },
        F2: { x: 6, y: 6 },
        F3: { x: 5, y: 6 },
        G1: { x: 6, y: 5 }
      }),
      monsterBehavior: 'kind'
    });
    encounter.units.F1.currentHp = 0;
    encounter.units.F1.conditions.unconscious = true;
    encounter.units.F1.conditions.prone = true;
    encounter.units.F3.currentHp = 4;

    const decision = chooseTurnDecision(encounter, 'G1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'F2',
      weaponId: 'scimitar'
    });
  });

  it('balanced goblins prefer a flanked legal melee target without moving to create flanking', () => {
    const encounter = createEncounter({
      seed: 'balanced-monster-flanking',
      placements: buildPlacements({
        F1: { x: 6, y: 5 },
        F2: { x: 6, y: 6 },
        G1: { x: 5, y: 5 },
        G2: { x: 7, y: 7 }
      }),
      monsterBehavior: 'balanced'
    });

    const decision = chooseTurnDecision(encounter, 'G1');

    expect(decision.preActionMovement).toBeUndefined();
    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'F2',
      weaponId: 'scimitar'
    });
  });

  it('balanced goblins never attack adjacent downed fighters on purpose', () => {
    const encounter = createEncounter({
      seed: 'balanced-ignore-downed',
      placements: buildPlacements({
        F1: { x: 5, y: 5 },
        F2: { x: 6, y: 6 },
        G1: { x: 6, y: 5 }
      }),
      monsterBehavior: 'balanced'
    });
    encounter.units.F1.currentHp = 0;
    encounter.units.F1.conditions.unconscious = true;
    encounter.units.F1.conditions.prone = true;

    const decision = chooseTurnDecision(encounter, 'G1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'F2',
      weaponId: 'scimitar'
    });
  });

  it('evil goblins finish adjacent downed fighters before higher-value conscious targets', () => {
    const encounter = createEncounter({
      seed: 'evil-finish-downed',
      placements: buildPlacements({
        F1: { x: 5, y: 5 },
        F2: { x: 6, y: 6 },
        G1: { x: 6, y: 5 }
      }),
      monsterBehavior: 'evil'
    });
    encounter.units.F1.currentHp = 0;
    encounter.units.F1.conditions.unconscious = true;
    encounter.units.F1.conditions.prone = true;
    encounter.units.F2.roleTags = ['healer'];

    const decision = chooseTurnDecision(encounter, 'G1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'F1',
      weaponId: 'scimitar'
    });
  });

  it('evil goblins prioritize healer tags over caster tags and low-hp non-tagged fighters', () => {
    const encounter = createEncounter({
      seed: 'evil-priority-tags',
      placements: buildPlacements({
        F1: { x: 6, y: 5 },
        F2: { x: 6, y: 6 },
        F3: { x: 5, y: 6 },
        G1: { x: 5, y: 5 }
      }),
      monsterBehavior: 'evil'
    });
    encounter.units.F1.roleTags = ['healer'];
    encounter.units.F2.roleTags = ['caster'];
    encounter.units.F3.currentHp = 1;

    const decision = chooseTurnDecision(encounter, 'G1');

    expect(decision.action).toEqual({
      kind: 'attack',
      targetId: 'F1',
      weaponId: 'scimitar'
    });
  });
});
