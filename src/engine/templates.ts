import { ARCHER_GOBLIN_IDS } from './constants';
import type { AbilityModifiers, AttackId, UnitState, WeaponProfile } from './types';

const fighterAbilityMods: AbilityModifiers = {
  str: 3,
  dex: 1,
  con: 2,
  int: 0,
  wis: -1,
  cha: 1
};

const goblinAbilityMods: AbilityModifiers = {
  str: -1,
  dex: 2,
  con: 0,
  int: 0,
  wis: -1,
  cha: -1
};

const fighterWeapons: Record<AttackId, WeaponProfile | undefined> = {
  greatsword: {
    id: 'greatsword',
    displayName: 'Greatsword',
    attackBonus: 5,
    abilityModifier: 3,
    damageDice: [{ count: 2, sides: 6 }],
    damageModifier: 3,
    damageType: 'slashing',
    mastery: 'graze',
    kind: 'melee',
    twoHanded: true
  },
  flail: {
    id: 'flail',
    displayName: 'Flail',
    attackBonus: 5,
    abilityModifier: 3,
    damageDice: [{ count: 1, sides: 8 }],
    damageModifier: 3,
    damageType: 'bludgeoning',
    mastery: 'sap',
    kind: 'melee'
  },
  javelin: {
    id: 'javelin',
    displayName: 'Javelin',
    attackBonus: 5,
    abilityModifier: 3,
    damageDice: [{ count: 1, sides: 6 }],
    damageModifier: 3,
    damageType: 'piercing',
    mastery: 'slow',
    kind: 'ranged',
    range: {
      normal: 30,
      long: 120
    }
  },
  scimitar: undefined,
  shortbow: undefined
};

const goblinWeapons: Record<AttackId, WeaponProfile | undefined> = {
  greatsword: undefined,
  flail: undefined,
  javelin: undefined,
  scimitar: {
    id: 'scimitar',
    displayName: 'Scimitar',
    attackBonus: 4,
    abilityModifier: 2,
    damageDice: [{ count: 1, sides: 6 }],
    damageModifier: 2,
    damageType: 'slashing',
    kind: 'melee',
    advantageDamageDice: [{ count: 1, sides: 4 }]
  },
  shortbow: {
    id: 'shortbow',
    displayName: 'Shortbow',
    attackBonus: 4,
    abilityModifier: 2,
    damageDice: [{ count: 1, sides: 6 }],
    damageModifier: 2,
    damageType: 'piercing',
    kind: 'ranged',
    range: {
      normal: 80,
      long: 320
    },
    advantageDamageDice: [{ count: 1, sides: 4 }]
  }
};

const goblinMeleeWeapons: Record<AttackId, WeaponProfile | undefined> = {
  ...goblinWeapons,
  shortbow: undefined
};

function cloneAttacks(source: Record<AttackId, WeaponProfile | undefined>): Record<AttackId, WeaponProfile | undefined> {
  return {
    greatsword: source.greatsword ? { ...source.greatsword } : undefined,
    flail: source.flail ? { ...source.flail } : undefined,
    javelin: source.javelin ? { ...source.javelin } : undefined,
    scimitar: source.scimitar ? { ...source.scimitar } : undefined,
    shortbow: source.shortbow ? { ...source.shortbow } : undefined
  };
}

export function createFighter(id: string): UnitState {
  return {
    id,
    faction: 'fighters',
    combatRole: 'fighter',
    templateName: 'Level 1 Fighter Sample Build',
    roleTags: [],
    currentHp: 13,
    maxHp: 13,
    ac: 16,
    speed: 30,
    effectiveSpeed: 30,
    initiativeMod: 1,
    initiativeScore: 0,
    abilityMods: { ...fighterAbilityMods },
    passivePerception: 11,
    conditions: {
      unconscious: false,
      prone: false,
      dead: false
    },
    deathSaveSuccesses: 0,
    deathSaveFailures: 0,
    stable: false,
    resources: {
      secondWindUses: 2,
      javelins: 8
    },
    temporaryEffects: [],
    reactionAvailable: true,
    attacks: cloneAttacks(fighterWeapons),
    medicineModifier: -1
  };
}

export function createGoblin(id: string): UnitState {
  const isArcher = ARCHER_GOBLIN_IDS.includes(id as (typeof ARCHER_GOBLIN_IDS)[number]);

  return {
    id,
    faction: 'goblins',
    combatRole: isArcher ? 'goblin_archer' : 'goblin_melee',
    templateName: isArcher ? '2024 Goblin Archer' : '2024 Goblin Raider',
    roleTags: [],
    currentHp: 10,
    maxHp: 10,
    ac: 15,
    speed: 30,
    effectiveSpeed: 30,
    initiativeMod: 2,
    initiativeScore: 0,
    abilityMods: { ...goblinAbilityMods },
    passivePerception: 9,
    conditions: {
      unconscious: false,
      prone: false,
      dead: false
    },
    deathSaveSuccesses: 0,
    deathSaveFailures: 0,
    stable: false,
    resources: {
      secondWindUses: 0,
      javelins: 0
    },
    temporaryEffects: [],
    reactionAvailable: true,
    attacks: cloneAttacks(isArcher ? goblinWeapons : goblinMeleeWeapons),
    medicineModifier: -1
  };
}
