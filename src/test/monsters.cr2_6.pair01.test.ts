import { describe, expect, it } from 'vitest';

import { getCr2To6Monster, listCr2To6MonsterIds } from '../content/monsters/cr2_6';
import {
  buildMonsterBenchmarkSnapshot,
  CR2_6_PAIR_01_EXPECTATIONS,
  hasUndeadFortitude
} from '../content/monsters/expectations';
import { CR2_6_PAIR_01_PRESET } from './fixtures/cr2_6_pair_presets';

describe('CR2-6 pair 01 content (Ogre Zombie + Saber-Toothed Tiger)', () => {
  it('models only the requested pair for this run', () => {
    expect(CR2_6_PAIR_01_PRESET.monsterIds).toEqual(['ogre_zombie', 'saber_toothed_tiger']);
    expect(listCr2To6MonsterIds()).toEqual(['ogre_zombie', 'saber_toothed_tiger']);
  });

  it('captures Ogre Zombie SRD fields exactly for combat-relevant values', () => {
    const ogreZombie = getCr2To6Monster('ogre_zombie');

    expect(ogreZombie.displayName).toBe('Ogre Zombie');
    expect(ogreZombie.sourcePage).toBe(344);
    expect(ogreZombie.armorClass).toBe(8);
    expect(ogreZombie.initiative).toEqual({ modifier: -2, score: 8 });
    expect(ogreZombie.hitPoints).toEqual({ average: 85, formula: '9d10 + 36' });
    expect(ogreZombie.speed.walk).toBe(30);
    expect(ogreZombie.abilities.str).toEqual({ score: 19, modifier: 4, save: 4 });
    expect(ogreZombie.abilities.wis).toEqual({ score: 6, modifier: -2, save: 0 });
    expect(ogreZombie.damageImmunities).toEqual(['poison']);
    expect(ogreZombie.conditionImmunities).toEqual(['exhaustion', 'poisoned']);
    expect(ogreZombie.challengeRating).toBe(2);
    expect(ogreZombie.xp).toBe(450);
    expect(ogreZombie.proficiencyBonus).toBe(2);

    const slam = ogreZombie.actions.find((action) => action.name === 'Slam');
    expect(slam).toBeDefined();
    expect(slam?.attackBonus).toBe(6);
    expect(slam?.averageDamage).toBe(13);
    expect(slam?.damageDice).toBe('2d8 + 4');
    expect(slam?.damageType).toBe('bludgeoning');
  });

  it('captures Saber-Toothed Tiger SRD fields exactly for combat-relevant values', () => {
    const tiger = getCr2To6Monster('saber_toothed_tiger');

    expect(tiger.displayName).toBe('Saber-Toothed Tiger');
    expect(tiger.sourcePage).toBe(360);
    expect(tiger.armorClass).toBe(13);
    expect(tiger.initiative).toEqual({ modifier: 3, score: 13 });
    expect(tiger.hitPoints).toEqual({ average: 52, formula: '7d10 + 14' });
    expect(tiger.speed.walk).toBe(40);
    expect(tiger.abilities.str).toEqual({ score: 18, modifier: 4, save: 6 });
    expect(tiger.abilities.dex).toEqual({ score: 17, modifier: 3, save: 5 });
    expect(tiger.skills).toEqual({ perception: 5, stealth: 7 });
    expect(tiger.challengeRating).toBe(2);
    expect(tiger.xp).toBe(450);
    expect(tiger.proficiencyBonus).toBe(2);
    expect(tiger.traits.some((trait) => trait.name === 'Running Leap')).toBe(true);

    const rend = tiger.actions.find((action) => action.name === 'Rend');
    expect(rend).toBeDefined();
    expect(rend?.attackBonus).toBe(6);
    expect(rend?.averageDamage).toBe(11);
    expect(rend?.damageDice).toBe('2d6 + 4');
    expect(rend?.damageType).toBe('slashing');
    expect(tiger.bonusActions.map((action) => action.name)).toEqual(['Nimble Escape']);
  });
});

describe('CR2-6 pair 01 behavior expectations', () => {
  it('stores behavior expectations for each modeled monster', () => {
    expect(CR2_6_PAIR_01_EXPECTATIONS.ogre_zombie).toEqual({
      primaryRole: 'brute',
      preferredRangeFeet: 5,
      keepsPressureOnBloodiedTargets: true,
      defaultAttackRoutine: {
        actionName: 'Slam',
        attackCount: 1
      },
      bonusActionOptions: []
    });

    expect(CR2_6_PAIR_01_EXPECTATIONS.saber_toothed_tiger).toEqual({
      primaryRole: 'mobile_predator',
      preferredRangeFeet: 5,
      keepsPressureOnBloodiedTargets: true,
      defaultAttackRoutine: {
        actionName: 'Rend',
        attackCount: 2
      },
      bonusActionOptions: ['Disengage', 'Hide']
    });
  });

  it('flags Undead Fortitude behavior only for Ogre Zombie', () => {
    expect(hasUndeadFortitude('ogre_zombie')).toBe(true);
    expect(hasUndeadFortitude('saber_toothed_tiger')).toBe(false);
  });
});

describe('CR2-6 pair 01 benchmark snapshots', () => {
  it('computes deterministic offense and durability benchmarks for both monsters', () => {
    const ogreBenchmark = buildMonsterBenchmarkSnapshot('ogre_zombie');
    const tigerBenchmark = buildMonsterBenchmarkSnapshot('saber_toothed_tiger');

    expect(ogreBenchmark).toEqual({
      sustainedDamagePerRound: 13,
      durabilityIndex: 680,
      initiativeModifier: -2,
      primaryAttackBonus: 6
    });
    expect(tigerBenchmark).toEqual({
      sustainedDamagePerRound: 22,
      durabilityIndex: 676,
      initiativeModifier: 3,
      primaryAttackBonus: 6
    });
  });

  it('captures relative benchmark differences for pair-level balancing checks', () => {
    const ogreBenchmark = buildMonsterBenchmarkSnapshot('ogre_zombie');
    const tigerBenchmark = buildMonsterBenchmarkSnapshot('saber_toothed_tiger');

    expect(tigerBenchmark.sustainedDamagePerRound).toBeGreaterThan(ogreBenchmark.sustainedDamagePerRound);
    expect(ogreBenchmark.durabilityIndex).toBeGreaterThan(tigerBenchmark.durabilityIndex);
  });
});
