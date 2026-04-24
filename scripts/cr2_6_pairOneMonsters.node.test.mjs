import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getPairOneMonster,
  getPairOneMonsterBaselineAverageDamagePerTurn,
  getPairOneMonsterExpectation
} from '../src/content/monsters/cr2_6PairOne.ts';

test('content: Ogre Zombie uses exact SRD fields for pair one modeling', () => {
  const monster = getPairOneMonster('ogre_zombie');

  assert.equal(monster.source.page, 344);
  assert.equal(monster.challengeRating, 2);
  assert.equal(monster.armorClass, 8);
  assert.equal(monster.initiativeModifier, -2);
  assert.deepEqual(monster.hitPoints, {
    average: 85,
    formula: '9d10 + 36'
  });
  assert.deepEqual(monster.savingThrowModifiers, {
    str: 4,
    dex: -2,
    con: 4,
    int: -4,
    wis: 0,
    cha: -3
  });
  assert.deepEqual(monster.damageImmunities, ['Poison']);
  assert.deepEqual(monster.conditionImmunities, ['Exhaustion', 'Poisoned']);
  assert.equal(monster.actions[0]?.name, 'Slam');
  assert.equal(monster.actions[0]?.attackBonus, 6);
  assert.equal(monster.actions[0]?.averageHitDamage, 13);
});

test('content: Saber-Toothed Tiger uses exact SRD fields for pair one modeling', () => {
  const monster = getPairOneMonster('saber_toothed_tiger');

  assert.equal(monster.source.page, 360);
  assert.equal(monster.challengeRating, 2);
  assert.equal(monster.armorClass, 13);
  assert.equal(monster.initiativeModifier, 3);
  assert.deepEqual(monster.hitPoints, {
    average: 52,
    formula: '7d10 + 14'
  });
  assert.deepEqual(monster.savingThrowModifiers, {
    str: 6,
    dex: 5,
    con: 2,
    int: -4,
    wis: 1,
    cha: -1
  });
  assert.deepEqual(monster.skills, {
    Perception: 5,
    Stealth: 7
  });
  assert.deepEqual(monster.multiattackSequence, ['rend', 'rend']);
  assert.equal(monster.bonusActions[0]?.name, 'Nimble Escape');
});

test('behavior: expectations reflect undead brute vs mobile predator roles', () => {
  const ogreZombie = getPairOneMonsterExpectation('ogre_zombie');
  const saberToothedTiger = getPairOneMonsterExpectation('saber_toothed_tiger');

  assert.equal(ogreZombie.role, 'undead_brute');
  assert.equal(ogreZombie.hasDurabilityTrait, true);
  assert.equal(ogreZombie.hasBonusDisengageOrHide, false);
  assert.deepEqual(ogreZombie.defaultActionSequence, ['slam']);

  assert.equal(saberToothedTiger.role, 'mobile_predator');
  assert.equal(saberToothedTiger.hasDurabilityTrait, false);
  assert.equal(saberToothedTiger.hasBonusDisengageOrHide, true);
  assert.deepEqual(saberToothedTiger.defaultActionSequence, ['rend', 'rend']);
});

test('benchmark: baseline deterministic damage-per-turn is 13 vs 22', () => {
  const ogreZombieBaseline = getPairOneMonsterBaselineAverageDamagePerTurn('ogre_zombie');
  const saberToothedTigerBaseline =
    getPairOneMonsterBaselineAverageDamagePerTurn('saber_toothed_tiger');

  assert.equal(ogreZombieBaseline, 13);
  assert.equal(saberToothedTigerBaseline, 22);
  assert.equal(saberToothedTigerBaseline > ogreZombieBaseline, true);
});
