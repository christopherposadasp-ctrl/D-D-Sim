export type MonsterId = 'ogre_zombie' | 'saber_toothed_tiger';

interface MonsterAbilityScore {
  score: number;
  modifier: number;
  save: number;
}

export interface MonsterAction {
  name: string;
  kind: 'attack' | 'multiattack' | 'utility';
  attackBonus?: number;
  reachFeet?: number;
  averageDamage?: number;
  damageDice?: string;
  damageType?: string;
  text: string;
}

export interface MonsterTrait {
  name: string;
  text: string;
}

export interface MonsterDefinition {
  id: MonsterId;
  displayName: string;
  source: 'SRD_CC_v5.2.1';
  sourcePage: number;
  size: string;
  creatureType: string;
  alignment: string;
  armorClass: number;
  initiative: {
    modifier: number;
    score: number;
  };
  hitPoints: {
    average: number;
    formula: string;
  };
  speed: {
    walk: number;
  };
  abilities: {
    str: MonsterAbilityScore;
    dex: MonsterAbilityScore;
    con: MonsterAbilityScore;
    int: MonsterAbilityScore;
    wis: MonsterAbilityScore;
    cha: MonsterAbilityScore;
  };
  skills: Record<string, number>;
  damageImmunities: string[];
  conditionImmunities: string[];
  senses: string[];
  passivePerception: number;
  languages: string[];
  challengeRating: number;
  xp: number;
  proficiencyBonus: number;
  traits: MonsterTrait[];
  actions: MonsterAction[];
  bonusActions: MonsterAction[];
}

const OGRE_ZOMBIE: MonsterDefinition = {
  id: 'ogre_zombie',
  displayName: 'Ogre Zombie',
  source: 'SRD_CC_v5.2.1',
  sourcePage: 344,
  size: 'Large',
  creatureType: 'Undead',
  alignment: 'Neutral Evil',
  armorClass: 8,
  initiative: {
    modifier: -2,
    score: 8
  },
  hitPoints: {
    average: 85,
    formula: '9d10 + 36'
  },
  speed: {
    walk: 30
  },
  abilities: {
    str: {
      score: 19,
      modifier: 4,
      save: 4
    },
    dex: {
      score: 6,
      modifier: -2,
      save: -2
    },
    con: {
      score: 18,
      modifier: 4,
      save: 4
    },
    int: {
      score: 3,
      modifier: -4,
      save: -4
    },
    wis: {
      score: 6,
      modifier: -2,
      save: 0
    },
    cha: {
      score: 5,
      modifier: -3,
      save: -3
    }
  },
  skills: {},
  damageImmunities: ['poison'],
  conditionImmunities: ['exhaustion', 'poisoned'],
  senses: ['darkvision 60 ft.'],
  passivePerception: 8,
  languages: ["understands Common and Giant but can't speak"],
  challengeRating: 2,
  xp: 450,
  proficiencyBonus: 2,
  traits: [
    {
      name: 'Undead Fortitude',
      text: 'If damage reduces the zombie to 0 HP, it makes a Constitution save (DC 5 + damage taken) unless the damage is radiant or from a critical hit. On a success, it drops to 1 HP instead.'
    }
  ],
  actions: [
    {
      name: 'Slam',
      kind: 'attack',
      attackBonus: 6,
      reachFeet: 5,
      averageDamage: 13,
      damageDice: '2d8 + 4',
      damageType: 'bludgeoning',
      text: 'Melee Attack Roll: +6, reach 5 ft. Hit: 13 (2d8 + 4) bludgeoning damage.'
    }
  ],
  bonusActions: []
};

const SABER_TOOTHED_TIGER: MonsterDefinition = {
  id: 'saber_toothed_tiger',
  displayName: 'Saber-Toothed Tiger',
  source: 'SRD_CC_v5.2.1',
  sourcePage: 360,
  size: 'Large',
  creatureType: 'Beast',
  alignment: 'Unaligned',
  armorClass: 13,
  initiative: {
    modifier: 3,
    score: 13
  },
  hitPoints: {
    average: 52,
    formula: '7d10 + 14'
  },
  speed: {
    walk: 40
  },
  abilities: {
    str: {
      score: 18,
      modifier: 4,
      save: 6
    },
    dex: {
      score: 17,
      modifier: 3,
      save: 5
    },
    con: {
      score: 15,
      modifier: 2,
      save: 2
    },
    int: {
      score: 3,
      modifier: -4,
      save: -4
    },
    wis: {
      score: 12,
      modifier: 1,
      save: 1
    },
    cha: {
      score: 8,
      modifier: -1,
      save: -1
    }
  },
  skills: {
    perception: 5,
    stealth: 7
  },
  damageImmunities: [],
  conditionImmunities: [],
  senses: ['darkvision 60 ft.'],
  passivePerception: 15,
  languages: ['none'],
  challengeRating: 2,
  xp: 450,
  proficiencyBonus: 2,
  traits: [
    {
      name: 'Running Leap',
      text: 'With a 10-foot running start, the tiger can long jump up to 25 feet.'
    }
  ],
  actions: [
    {
      name: 'Multiattack',
      kind: 'multiattack',
      text: 'The tiger makes two Rend attacks.'
    },
    {
      name: 'Rend',
      kind: 'attack',
      attackBonus: 6,
      reachFeet: 5,
      averageDamage: 11,
      damageDice: '2d6 + 4',
      damageType: 'slashing',
      text: 'Melee Attack Roll: +6, reach 5 ft. Hit: 11 (2d6 + 4) slashing damage.'
    }
  ],
  bonusActions: [
    {
      name: 'Nimble Escape',
      kind: 'utility',
      text: 'The tiger takes the Disengage or Hide action.'
    }
  ]
};

export const CR2_6_MONSTERS: Readonly<Record<MonsterId, MonsterDefinition>> = {
  ogre_zombie: OGRE_ZOMBIE,
  saber_toothed_tiger: SABER_TOOTHED_TIGER
};

export function getCr2To6Monster(monsterId: MonsterId): MonsterDefinition {
  return CR2_6_MONSTERS[monsterId];
}

export function listCr2To6MonsterIds(): MonsterId[] {
  return ['ogre_zombie', 'saber_toothed_tiger'];
}
