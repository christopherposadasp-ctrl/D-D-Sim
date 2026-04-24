export type PairOneMonsterId = 'ogre_zombie' | 'saber_toothed_tiger';

export interface PairOneAttackProfile {
  id: string;
  name: string;
  kind: 'melee' | 'ranged';
  attackBonus: number;
  reachFt?: number;
  rangeFt?: {
    normal: number;
    long?: number;
  };
  averageHitDamage: number;
  damageRoll: string;
  damageType: string;
}

export interface PairOneTrait {
  name: string;
  text: string;
}

export interface PairOneMonsterEntry {
  id: PairOneMonsterId;
  displayName: string;
  source: {
    book: 'SRD_CC_v5.2.1';
    page: number;
  };
  challengeRating: number;
  xp: number;
  proficiencyBonus: number;
  size: 'Large';
  creatureType: 'Undead' | 'Beast';
  alignment: 'Neutral Evil' | 'Unaligned';
  armorClass: number;
  initiativeModifier: number;
  hitPoints: {
    average: number;
    formula: string;
  };
  speedFt: number;
  abilityModifiers: {
    str: number;
    dex: number;
    con: number;
    int: number;
    wis: number;
    cha: number;
  };
  savingThrowModifiers: {
    str: number;
    dex: number;
    con: number;
    int: number;
    wis: number;
    cha: number;
  };
  skills: Record<string, number>;
  senses: string[];
  passivePerception: number;
  languages: string;
  damageImmunities: string[];
  conditionImmunities: string[];
  traits: PairOneTrait[];
  actions: PairOneAttackProfile[];
  multiattackSequence: string[];
  bonusActions: PairOneTrait[];
}

export interface PairOneMonsterExpectation {
  monsterId: PairOneMonsterId;
  role: 'undead_brute' | 'mobile_predator';
  meleeOnly: boolean;
  hasDurabilityTrait: boolean;
  hasBonusDisengageOrHide: boolean;
  defaultActionSequence: string[];
  baselineAverageDamagePerTurn: number;
}

const pairOneMonsters: Readonly<Record<PairOneMonsterId, PairOneMonsterEntry>> = {
  ogre_zombie: {
    id: 'ogre_zombie',
    displayName: 'Ogre Zombie',
    source: {
      book: 'SRD_CC_v5.2.1',
      page: 344
    },
    challengeRating: 2,
    xp: 450,
    proficiencyBonus: 2,
    size: 'Large',
    creatureType: 'Undead',
    alignment: 'Neutral Evil',
    armorClass: 8,
    initiativeModifier: -2,
    hitPoints: {
      average: 85,
      formula: '9d10 + 36'
    },
    speedFt: 30,
    abilityModifiers: {
      str: 4,
      dex: -2,
      con: 4,
      int: -4,
      wis: -2,
      cha: -3
    },
    savingThrowModifiers: {
      str: 4,
      dex: -2,
      con: 4,
      int: -4,
      wis: 0,
      cha: -3
    },
    skills: {},
    senses: ['Darkvision 60 ft.'],
    passivePerception: 8,
    languages: "Understands Common and Giant but can't speak",
    damageImmunities: ['Poison'],
    conditionImmunities: ['Exhaustion', 'Poisoned'],
    traits: [
      {
        name: 'Undead Fortitude',
        text:
          'If damage reduces the zombie to 0 Hit Points, it makes a Constitution saving throw (DC 5 plus the damage taken) unless the damage is Radiant or from a Critical Hit. On a successful save, the zombie drops to 1 Hit Point instead.'
      }
    ],
    actions: [
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
    ],
    multiattackSequence: ['slam'],
    bonusActions: []
  },
  saber_toothed_tiger: {
    id: 'saber_toothed_tiger',
    displayName: 'Saber-Toothed Tiger',
    source: {
      book: 'SRD_CC_v5.2.1',
      page: 360
    },
    challengeRating: 2,
    xp: 450,
    proficiencyBonus: 2,
    size: 'Large',
    creatureType: 'Beast',
    alignment: 'Unaligned',
    armorClass: 13,
    initiativeModifier: 3,
    hitPoints: {
      average: 52,
      formula: '7d10 + 14'
    },
    speedFt: 40,
    abilityModifiers: {
      str: 4,
      dex: 3,
      con: 2,
      int: -4,
      wis: 1,
      cha: -1
    },
    savingThrowModifiers: {
      str: 6,
      dex: 5,
      con: 2,
      int: -4,
      wis: 1,
      cha: -1
    },
    skills: {
      Perception: 5,
      Stealth: 7
    },
    senses: ['Darkvision 60 ft.'],
    passivePerception: 15,
    languages: 'None',
    damageImmunities: [],
    conditionImmunities: [],
    traits: [
      {
        name: 'Running Leap',
        text: 'With a 10-foot running start, the tiger can Long Jump up to 25 feet.'
      }
    ],
    actions: [
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
    ],
    multiattackSequence: ['rend', 'rend'],
    bonusActions: [
      {
        name: 'Nimble Escape',
        text: 'The tiger takes the Disengage or Hide action.'
      }
    ]
  }
};

function getAttackById(monster: PairOneMonsterEntry, attackId: string): PairOneAttackProfile {
  const attack = monster.actions.find((candidate) => candidate.id === attackId);

  if (!attack) {
    throw new Error(`Missing attack '${attackId}' for monster '${monster.displayName}'.`);
  }

  return attack;
}

export function getPairOneMonster(id: PairOneMonsterId): PairOneMonsterEntry {
  return pairOneMonsters[id];
}

export function listPairOneMonsters(): PairOneMonsterEntry[] {
  return [pairOneMonsters.ogre_zombie, pairOneMonsters.saber_toothed_tiger];
}

export function getPairOneMonsterBaselineAverageDamagePerTurn(id: PairOneMonsterId): number {
  const monster = getPairOneMonster(id);

  return monster.multiattackSequence.reduce((total, attackId) => {
    const attack = getAttackById(monster, attackId);
    return total + attack.averageHitDamage;
  }, 0);
}

export function getPairOneMonsterExpectation(id: PairOneMonsterId): PairOneMonsterExpectation {
  const monster = getPairOneMonster(id);
  const hasDurabilityTrait = monster.traits.some((trait) => trait.name === 'Undead Fortitude');
  const hasBonusDisengageOrHide = monster.bonusActions.some(
    (action) => action.text.includes('Disengage') || action.text.includes('Hide')
  );
  const meleeOnly = monster.actions.every((action) => action.kind === 'melee');

  return {
    monsterId: id,
    role: hasDurabilityTrait ? 'undead_brute' : 'mobile_predator',
    meleeOnly,
    hasDurabilityTrait,
    hasBonusDisengageOrHide,
    defaultActionSequence: [...monster.multiattackSequence],
    baselineAverageDamagePerTurn: getPairOneMonsterBaselineAverageDamagePerTurn(id)
  };
}
