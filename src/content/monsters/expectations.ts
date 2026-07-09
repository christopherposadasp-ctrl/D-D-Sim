import { getCr2To6Monster, type MonsterId } from './cr2_6.ts';

export interface MonsterBehaviorExpectation {
  primaryRole: 'brute' | 'mobile_predator';
  preferredRangeFeet: number;
  keepsPressureOnBloodiedTargets: boolean;
  defaultAttackRoutine: {
    actionName: string;
    attackCount: number;
  };
  bonusActionOptions: string[];
}

export interface MonsterBenchmarkSnapshot {
  sustainedDamagePerRound: number;
  durabilityIndex: number;
  initiativeModifier: number;
  primaryAttackBonus: number;
}

export const CR2_6_PAIR_01_EXPECTATIONS: Readonly<Record<MonsterId, MonsterBehaviorExpectation>> = {
  ogre_zombie: {
    primaryRole: 'brute',
    preferredRangeFeet: 5,
    keepsPressureOnBloodiedTargets: true,
    defaultAttackRoutine: {
      actionName: 'Slam',
      attackCount: 1
    },
    bonusActionOptions: []
  },
  saber_toothed_tiger: {
    primaryRole: 'mobile_predator',
    preferredRangeFeet: 5,
    keepsPressureOnBloodiedTargets: true,
    defaultAttackRoutine: {
      actionName: 'Rend',
      attackCount: 2
    },
    bonusActionOptions: ['Disengage', 'Hide']
  }
};

function getPrimaryAttack(monsterId: MonsterId): {
  attackBonus: number;
  averageDamage: number;
} {
  const monster = getCr2To6Monster(monsterId);
  const routine = CR2_6_PAIR_01_EXPECTATIONS[monsterId].defaultAttackRoutine;
  const attack = monster.actions.find(
    (action) => action.kind === 'attack' && action.name === routine.actionName
  );

  if (!attack || attack.attackBonus === undefined || attack.averageDamage === undefined) {
    throw new Error(`Missing benchmark attack profile for ${monster.displayName}.`);
  }

  return {
    attackBonus: attack.attackBonus,
    averageDamage: attack.averageDamage
  };
}

export function buildMonsterBenchmarkSnapshot(monsterId: MonsterId): MonsterBenchmarkSnapshot {
  const monster = getCr2To6Monster(monsterId);
  const routine = CR2_6_PAIR_01_EXPECTATIONS[monsterId].defaultAttackRoutine;
  const attack = getPrimaryAttack(monsterId);

  return {
    sustainedDamagePerRound: attack.averageDamage * routine.attackCount,
    durabilityIndex: monster.armorClass * monster.hitPoints.average,
    initiativeModifier: monster.initiative.modifier,
    primaryAttackBonus: attack.attackBonus
  };
}

export function hasUndeadFortitude(monsterId: MonsterId): boolean {
  const monster = getCr2To6Monster(monsterId);
  return monster.traits.some((trait) => trait.name === 'Undead Fortitude');
}
