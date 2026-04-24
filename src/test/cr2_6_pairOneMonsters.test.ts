import { describe, expect, it } from 'vitest';

import {
  getPairOneMonster,
  getPairOneMonsterBaselineAverageDamagePerTurn,
  getPairOneMonsterExpectation,
  listPairOneMonsters
} from '../content/monsters/cr2_6PairOne';

describe('CR 2-6 pair one content (Ogre Zombie + Saber-Toothed Tiger)', () => {
  it('models exactly two monsters for the first tonight queue pair', () => {
    const ids = listPairOneMonsters().map((monster) => monster.id);

    expect(ids).toEqual(['ogre_zombie', 'saber_toothed_tiger']);
  });

  it('matches Ogre Zombie SRD data on page 344', () => {
    const monster = getPairOneMonster('ogre_zombie');

    expect(monster.displayName).toBe('Ogre Zombie');
    expect(monster.source).toEqual({
      book: 'SRD_CC_v5.2.1',
      page: 344
    });
    expect(monster.challengeRating).toBe(2);
    expect(monster.xp).toBe(450);
    expect(monster.proficiencyBonus).toBe(2);
    expect(monster.armorClass).toBe(8);
    expect(monster.initiativeModifier).toBe(-2);
    expect(monster.hitPoints).toEqual({
      average: 85,
      formula: '9d10 + 36'
    });
    expect(monster.speedFt).toBe(30);
    expect(monster.abilityModifiers).toEqual({
      str: 4,
      dex: -2,
      con: 4,
      int: -4,
      wis: -2,
      cha: -3
    });
    expect(monster.savingThrowModifiers).toEqual({
      str: 4,
      dex: -2,
      con: 4,
      int: -4,
      wis: 0,
      cha: -3
    });
    expect(monster.damageImmunities).toEqual(['Poison']);
    expect(monster.conditionImmunities).toEqual(['Exhaustion', 'Poisoned']);
    expect(monster.languages).toBe("Understands Common and Giant but can't speak");
    expect(monster.actions).toEqual([
      {
        id: 'slam',
        name: 'Slam',
        kind: 'melee',
        attackBonus: 6,
        reachFt: 5,
        averageHitDamage: 13,
        damageRoll: '2d8 + 4',
        damageType: 'Bludgeoning'
      }
    ]);
    expect(monster.traits.map((trait) => trait.name)).toEqual(['Undead Fortitude']);
  });

  it('matches Saber-Toothed Tiger SRD data on page 360', () => {
    const monster = getPairOneMonster('saber_toothed_tiger');

    expect(monster.displayName).toBe('Saber-Toothed Tiger');
    expect(monster.source).toEqual({
      book: 'SRD_CC_v5.2.1',
      page: 360
    });
    expect(monster.challengeRating).toBe(2);
    expect(monster.xp).toBe(450);
    expect(monster.proficiencyBonus).toBe(2);
    expect(monster.armorClass).toBe(13);
    expect(monster.initiativeModifier).toBe(3);
    expect(monster.hitPoints).toEqual({
      average: 52,
      formula: '7d10 + 14'
    });
    expect(monster.speedFt).toBe(40);
    expect(monster.abilityModifiers).toEqual({
      str: 4,
      dex: 3,
      con: 2,
      int: -4,
      wis: 1,
      cha: -1
    });
    expect(monster.savingThrowModifiers).toEqual({
      str: 6,
      dex: 5,
      con: 2,
      int: -4,
      wis: 1,
      cha: -1
    });
    expect(monster.skills).toEqual({
      Perception: 5,
      Stealth: 7
    });
    expect(monster.actions).toEqual([
      {
        id: 'rend',
        name: 'Rend',
        kind: 'melee',
        attackBonus: 6,
        reachFt: 5,
        averageHitDamage: 11,
        damageRoll: '2d6 + 4',
        damageType: 'Slashing'
      }
    ]);
    expect(monster.multiattackSequence).toEqual(['rend', 'rend']);
    expect(monster.bonusActions.map((action) => action.name)).toEqual(['Nimble Escape']);
  });
});

describe('CR 2-6 pair one behavior expectations', () => {
  it('classifies Ogre Zombie as a melee undead brute with no bonus-action mobility', () => {
    const expectation = getPairOneMonsterExpectation('ogre_zombie');

    expect(expectation).toEqual({
      monsterId: 'ogre_zombie',
      role: 'undead_brute',
      meleeOnly: true,
      hasDurabilityTrait: true,
      hasBonusDisengageOrHide: false,
      defaultActionSequence: ['slam'],
      baselineAverageDamagePerTurn: 13
    });
  });

  it('classifies Saber-Toothed Tiger as a mobile predator with double-rend baseline', () => {
    const expectation = getPairOneMonsterExpectation('saber_toothed_tiger');

    expect(expectation).toEqual({
      monsterId: 'saber_toothed_tiger',
      role: 'mobile_predator',
      meleeOnly: true,
      hasDurabilityTrait: false,
      hasBonusDisengageOrHide: true,
      defaultActionSequence: ['rend', 'rend'],
      baselineAverageDamagePerTurn: 22
    });
  });
});

describe('CR 2-6 pair one benchmark baselines', () => {
  it('computes deterministic baseline average damage per turn from multiattack data', () => {
    const ogreZombieBaseline = getPairOneMonsterBaselineAverageDamagePerTurn('ogre_zombie');
    const saberToothedTigerBaseline =
      getPairOneMonsterBaselineAverageDamagePerTurn('saber_toothed_tiger');

    expect(ogreZombieBaseline).toBe(13);
    expect(saberToothedTigerBaseline).toBe(22);
    expect(saberToothedTigerBaseline).toBeGreaterThan(ogreZombieBaseline);
  });
});
