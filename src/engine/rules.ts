import { compareUnitIds } from './helpers';
import { rollDie } from './rng';
import { getAttackContext } from './spatial';
import type {
  AttackId,
  AttackMode,
  CombatEvent,
  DamageCandidate,
  EncounterState,
  MasteryType,
  SlowEffect,
  TemporaryEffect,
  UnitState,
  WeaponProfile
} from './types';

export interface AttackRollOverrides {
  attackRolls?: number[];
  damageRolls?: number[];
  savageDamageRolls?: number[];
  advantageDamageRolls?: number[];
}

export interface ResolveAttackArgs {
  attackerId: string;
  targetId: string;
  weaponId: AttackId;
  savageAttackerAvailable: boolean;
  movementDetails?: CombatEvent['movementDetails'];
  isOpportunityAttack?: boolean;
  overrides?: AttackRollOverrides;
}

function eventBase(state: EncounterState, actorId: string): Pick<CombatEvent, 'round' | 'actorId'> {
  return {
    round: state.round,
    actorId
  };
}

function pullDie(state: EncounterState, sides: number, override?: number): number {
  if (override !== undefined) {
    return override;
  }

  const rolled = rollDie(state.rngState, sides);
  state.rngState = rolled.state;
  return rolled.value;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

export function applyGreatWeaponFighting(rolls: number[]): number[] {
  return rolls.map((roll) => (roll <= 2 ? 3 : roll));
}

function rollDamageCandidate(
  state: EncounterState,
  weapon: WeaponProfile,
  overrideRolls?: number[],
  applyGwf = false
): DamageCandidate {
  const rawRolls: number[] = [];

  for (const spec of weapon.damageDice) {
    for (let index = 0; index < spec.count; index += 1) {
      rawRolls.push(pullDie(state, spec.sides, overrideRolls?.shift()));
    }
  }

  const adjustedRolls = applyGwf ? applyGreatWeaponFighting(rawRolls) : [...rawRolls];

  return {
    rawRolls,
    adjustedRolls,
    subtotal: sum(adjustedRolls)
  };
}

function rollBonusCandidate(
  state: EncounterState,
  weapon: WeaponProfile,
  overrideRolls?: number[]
): DamageCandidate | null {
  if (!weapon.advantageDamageDice) {
    return null;
  }

  const rawRolls: number[] = [];

  for (const spec of weapon.advantageDamageDice) {
    for (let index = 0; index < spec.count; index += 1) {
      rawRolls.push(pullDie(state, spec.sides, overrideRolls?.shift()));
    }
  }

  return {
    rawRolls,
    adjustedRolls: [...rawRolls],
    subtotal: sum(rawRolls)
  };
}

export function chooseDamageCandidate(
  primary: DamageCandidate,
  savage: DamageCandidate | null
): { chosen: 'primary' | 'savage'; candidate: DamageCandidate } {
  if (!savage) {
    return {
      chosen: 'primary',
      candidate: primary
    };
  }

  if (savage.subtotal > primary.subtotal) {
    return {
      chosen: 'savage',
      candidate: savage
    };
  }

  return {
    chosen: 'primary',
    candidate: primary
  };
}

function recalculateEffectiveSpeedForUnit(unit: UnitState): void {
  const slowPenalty = unit.temporaryEffects
    .filter((effect): effect is SlowEffect => effect.kind === 'slow')
    .reduce((total, effect) => total + effect.penalty, 0);

  unit.effectiveSpeed = Math.max(0, unit.speed - Math.min(10, slowPenalty));
}

export function recalculateEffectiveSpeed(unit: UnitState): UnitState {
  const nextUnit = {
    ...unit,
    temporaryEffects: [...unit.temporaryEffects]
  };

  recalculateEffectiveSpeedForUnit(nextUnit);
  return nextUnit;
}

function formatEffectKinds(effects: TemporaryEffect[]): string {
  return effects
    .map((effect) => effect.kind)
    .sort()
    .join(', ');
}

export function expireTurnEffects(state: EncounterState, actorId: string): CombatEvent[] {
  const events: CombatEvent[] = [];

  for (const unit of Object.values(state.units).sort((left, right) => compareUnitIds(left.id, right.id))) {
    const expired = unit.temporaryEffects.filter(
      (effect) => effect.expiresAtTurnStartOf === actorId
    );

    if (expired.length === 0) {
      continue;
    }

    unit.temporaryEffects = unit.temporaryEffects.filter(
      (effect) => effect.expiresAtTurnStartOf !== actorId
    );
    recalculateEffectiveSpeedForUnit(unit);

    events.push({
      ...eventBase(state, actorId),
      targetIds: [unit.id],
      eventType: 'effect_expired',
      rawRolls: {},
      resolvedTotals: {
        expiredCount: expired.length,
        unitId: unit.id
      },
      movementDetails: null,
      damageDetails: null,
      conditionDeltas: [`Expired ${formatEffectKinds(expired)} on ${unit.id}.`],
      textSummary: `${formatEffectKinds(expired)} expire on ${unit.id} at the start of ${actorId}'s turn.`
    });
  }

  return events;
}

export function resolveDeathSave(
  state: EncounterState,
  actorId: string,
  overrideRoll?: number
): CombatEvent {
  const actor = state.units[actorId];
  const rawRoll = pullDie(state, 20, overrideRoll);
  let outcome = 'success';

  if (rawRoll === 1) {
    actor.deathSaveFailures += 2;
    outcome = 'critical_failure';
  } else if (rawRoll < 10) {
    actor.deathSaveFailures += 1;
    outcome = 'failure';
  } else if (rawRoll === 20) {
    actor.currentHp = 1;
    actor.conditions.unconscious = false;
    actor.conditions.prone = false;
    actor.stable = false;
    actor.deathSaveFailures = 0;
    actor.deathSaveSuccesses = 0;
    outcome = 'critical_success';
  } else {
    actor.deathSaveSuccesses += 1;
  }

  const conditionDeltas: string[] = [];

  if (actor.deathSaveFailures >= 3) {
    actor.conditions.dead = true;
    actor.conditions.unconscious = false;
    actor.conditions.prone = false;
    conditionDeltas.push(`${actorId} dies after three failed death saves.`);
    outcome = 'dead';
  } else if (actor.deathSaveSuccesses >= 3 && actor.currentHp === 0) {
    actor.stable = true;
    actor.conditions.unconscious = true;
    actor.conditions.prone = true;
    conditionDeltas.push(`${actorId} stabilizes at 0 HP.`);
    outcome = 'stable';
  } else if (outcome === 'critical_success') {
    conditionDeltas.push(`${actorId} regains 1 HP and returns to consciousness.`);
  }

  return {
    ...eventBase(state, actorId),
    targetIds: [actorId],
    eventType: 'death_save',
    rawRolls: {
      deathSaveRolls: [rawRoll]
    },
    resolvedTotals: {
      successes: actor.deathSaveSuccesses,
      failures: actor.deathSaveFailures,
      outcome
    },
    movementDetails: null,
    damageDetails: null,
    conditionDeltas,
    textSummary:
      outcome === 'critical_success'
        ? `${actorId} rolls a natural 20 on a death save, regains 1 HP, and stands back up.`
        : `${actorId} makes a death save with ${rawRoll}.`
  };
}

export function attemptSecondWind(
  state: EncounterState,
  actorId: string,
  overrideRoll?: number
): CombatEvent | null {
  const actor = state.units[actorId];

  if (actor.resources.secondWindUses <= 0 || actor.currentHp <= 0) {
    return null;
  }

  const rawRoll = pullDie(state, 10, overrideRoll);
  const healed = Math.min(actor.maxHp - actor.currentHp, rawRoll + 1);
  actor.currentHp += healed;
  actor.resources.secondWindUses -= 1;

  return {
    ...eventBase(state, actorId),
    targetIds: [actorId],
    eventType: 'heal',
    rawRolls: {
      healingRolls: [rawRoll]
    },
    resolvedTotals: {
      healingTotal: healed,
      currentHp: actor.currentHp,
      secondWindUsesRemaining: actor.resources.secondWindUses
    },
    movementDetails: null,
    damageDetails: null,
    conditionDeltas: [],
    textSummary: `${actorId} uses Second Wind and regains ${healed} HP.`
  };
}

export function attemptStabilize(
  state: EncounterState,
  actorId: string,
  targetId: string,
  overrideRoll?: number
): CombatEvent {
  const actor = state.units[actorId];
  const target = state.units[targetId];
  const rawRoll = pullDie(state, 20, overrideRoll);
  const total = rawRoll + actor.medicineModifier;
  const success = total >= 10;

  if (success) {
    target.stable = true;
    target.conditions.unconscious = true;
    target.conditions.prone = true;
  }

  return {
    ...eventBase(state, actorId),
    targetIds: [targetId],
    eventType: 'stabilize',
    rawRolls: {
      medicineRolls: [rawRoll]
    },
    resolvedTotals: {
      medicineModifier: actor.medicineModifier,
      total,
      success
    },
    movementDetails: null,
    damageDetails: null,
    conditionDeltas: success ? [`${targetId} becomes stable.`] : [],
    textSummary: success
      ? `${actorId} stabilizes ${targetId} with a Medicine check of ${total}.`
      : `${actorId} fails to stabilize ${targetId} with a Medicine check of ${total}.`
  };
}

function consumeSapEffects(actor: UnitState): number {
  const sapCount = actor.temporaryEffects.filter((effect) => effect.kind === 'sap').length;

  if (sapCount === 0) {
    return 0;
  }

  actor.temporaryEffects = actor.temporaryEffects.filter((effect) => effect.kind !== 'sap');
  return sapCount;
}

function applyDamage(
  state: EncounterState,
  targetId: string,
  damage: number,
  isCritical: boolean
): { hpDelta: number; conditionDeltas: string[] } {
  const target = state.units[targetId];
  const previousHp = target.currentHp;
  const conditionDeltas: string[] = [];

  if (damage <= 0 || target.conditions.dead) {
    return {
      hpDelta: 0,
      conditionDeltas
    };
  }

  if (target.currentHp === 0) {
    target.stable = false;

    if (damage >= target.maxHp) {
      target.conditions.dead = true;
      target.conditions.unconscious = false;
      target.conditions.prone = false;
      conditionDeltas.push(`${targetId} is killed outright while at 0 HP.`);
      return {
        hpDelta: 0,
        conditionDeltas
      };
    }

    target.deathSaveFailures += isCritical ? 2 : 1;
    conditionDeltas.push(
      `${targetId} suffers ${isCritical ? 2 : 1} failed death save${isCritical ? 's' : ''} from damage at 0 HP.`
    );

    if (target.deathSaveFailures >= 3) {
      target.conditions.dead = true;
      target.conditions.unconscious = false;
      target.conditions.prone = false;
      conditionDeltas.push(`${targetId} dies after taking damage at 0 HP.`);
    }

    return {
      hpDelta: 0,
      conditionDeltas
    };
  }

  target.currentHp = Math.max(0, target.currentHp - damage);

  if (target.faction === 'goblins' && target.currentHp === 0) {
    target.conditions.dead = true;
    target.conditions.unconscious = false;
    target.conditions.prone = false;
    target.temporaryEffects = [];
    target.effectiveSpeed = 0;
    conditionDeltas.push(`${targetId} is removed from combat at 0 HP.`);
  } else if (target.faction === 'fighters' && target.currentHp === 0) {
    const overflow = damage - previousHp;

    if (overflow >= target.maxHp) {
      target.conditions.dead = true;
      target.conditions.unconscious = false;
      target.conditions.prone = false;
      conditionDeltas.push(`${targetId} dies from massive damage.`);
    } else {
      target.stable = false;
      target.conditions.unconscious = true;
      target.conditions.prone = true;
      target.deathSaveFailures = 0;
      target.deathSaveSuccesses = 0;
      conditionDeltas.push(`${targetId} drops to 0 HP and falls unconscious.`);
    }
  }

  return {
    hpDelta: target.currentHp - previousHp,
    conditionDeltas
  };
}

function applyMastery(
  state: EncounterState,
  attackerId: string,
  targetId: string,
  mastery: MasteryType | undefined,
  hit: boolean,
  damage: number
): { masteryApplied: MasteryType | null; masteryNotes: string | null; conditionDeltas: string[] } {
  const target = state.units[targetId];

  if (!mastery || !hit) {
    return {
      masteryApplied: null,
      masteryNotes: null,
      conditionDeltas: []
    };
  }

  if (mastery === 'sap') {
    target.temporaryEffects = [
      ...target.temporaryEffects.filter(
        (effect) => !(effect.kind === 'sap' && effect.sourceId === attackerId)
      ),
      {
        kind: 'sap',
        sourceId: attackerId,
        expiresAtTurnStartOf: attackerId
      }
    ];

    return {
      masteryApplied: 'sap',
      masteryNotes: `${targetId} has disadvantage on its next attack roll before ${attackerId}'s next turn.`,
      conditionDeltas: [`${targetId} is sapped by ${attackerId}.`]
    };
  }

  if (mastery === 'slow' && damage > 0) {
    target.temporaryEffects = [
      ...target.temporaryEffects.filter(
        (effect) => !(effect.kind === 'slow' && effect.sourceId === attackerId)
      ),
      {
        kind: 'slow',
        sourceId: attackerId,
        expiresAtTurnStartOf: attackerId,
        penalty: 10
      }
    ];
    recalculateEffectiveSpeedForUnit(target);

    return {
      masteryApplied: 'slow',
      masteryNotes: `${targetId}'s speed is reduced by 10 feet until ${attackerId}'s next turn.`,
      conditionDeltas: [`${targetId} is slowed by ${attackerId}.`]
    };
  }

  return {
    masteryApplied: null,
    masteryNotes: null,
    conditionDeltas: []
  };
}

function getAttackMode(
  state: EncounterState,
  attacker: UnitState,
  attackerId: string,
  target: UnitState,
  targetId: string,
  weapon: WeaponProfile
): { mode: AttackMode; advantageSources: string[]; disadvantageSources: string[] } {
  const spatialContext = getAttackContext(state, attackerId, targetId, weapon);
  const advantageSources: string[] = [...spatialContext.advantageSources];
  const disadvantageSources: string[] = [...spatialContext.disadvantageSources];

  if (target.conditions.unconscious) {
    advantageSources.push('target_unconscious');
  }

  if (target.conditions.prone && spatialContext.distanceSquares !== null) {
    if (spatialContext.distanceSquares <= 1) {
      advantageSources.push('target_prone');
    } else {
      disadvantageSources.push('target_prone');
    }
  }

  if (attacker.temporaryEffects.some((effect) => effect.kind === 'sap')) {
    disadvantageSources.push('sap');
  }

  if (advantageSources.length > 0 && disadvantageSources.length > 0) {
    return {
      mode: 'normal',
      advantageSources,
      disadvantageSources
    };
  }

  if (advantageSources.length > 0) {
    return {
      mode: 'advantage',
      advantageSources,
      disadvantageSources
    };
  }

  if (disadvantageSources.length > 0) {
    return {
      mode: 'disadvantage',
      advantageSources,
      disadvantageSources
    };
  }

  return {
    mode: 'normal',
    advantageSources,
    disadvantageSources
  };
}

function buildSkipEvent(state: EncounterState, actorId: string, reason: string): CombatEvent {
  return {
    ...eventBase(state, actorId),
    targetIds: [],
    eventType: 'skip',
    rawRolls: {},
    resolvedTotals: {
      reason
    },
    movementDetails: null,
    damageDetails: null,
    conditionDeltas: [],
    textSummary: `${actorId} skips its turn: ${reason}`
  };
}

export function createSkipEvent(state: EncounterState, actorId: string, reason: string): CombatEvent {
  return buildSkipEvent(state, actorId, reason);
}

export function resolveAttack(
  state: EncounterState,
  args: ResolveAttackArgs
): { event: CombatEvent; savageAttackerConsumed: boolean } {
  const attacker = state.units[args.attackerId];
  const target = state.units[args.targetId];
  const weapon = attacker.attacks[args.weaponId];

  if (!weapon) {
    return {
      event: buildSkipEvent(state, args.attackerId, `${args.weaponId} is unavailable.`),
      savageAttackerConsumed: false
    };
  }

  const attackContext = getAttackContext(state, args.attackerId, args.targetId, weapon);

  if (!attackContext.legal) {
    return {
      event: buildSkipEvent(state, args.attackerId, `${weapon.displayName} is not in range.`),
      savageAttackerConsumed: false
    };
  }

  if (args.weaponId === 'javelin') {
    if (attacker.resources.javelins <= 0) {
      return {
        event: buildSkipEvent(state, args.attackerId, 'No javelins remain.'),
        savageAttackerConsumed: false
      };
    }

    attacker.resources.javelins -= 1;
  }

  const overrides = {
    attackRolls: [...(args.overrides?.attackRolls ?? [])],
    damageRolls: [...(args.overrides?.damageRolls ?? [])],
    savageDamageRolls: [...(args.overrides?.savageDamageRolls ?? [])],
    advantageDamageRolls: [...(args.overrides?.advantageDamageRolls ?? [])]
  };

  const { mode, advantageSources, disadvantageSources } = getAttackMode(
    state,
    attacker,
    args.attackerId,
    target,
    args.targetId,
    weapon
  );
  const attackRolls =
    mode === 'normal'
      ? [pullDie(state, 20, overrides.attackRolls.shift())]
      : [
          pullDie(state, 20, overrides.attackRolls.shift()),
          pullDie(state, 20, overrides.attackRolls.shift())
        ];

  const selectedRoll =
    mode === 'advantage'
      ? Math.max(...attackRolls)
      : mode === 'disadvantage'
        ? Math.min(...attackRolls)
        : attackRolls[0];

  const sapConsumed = consumeSapEffects(attacker);
  const attackTotal = selectedRoll + weapon.attackBonus;
  const naturalOne = selectedRoll === 1;
  const naturalTwenty = selectedRoll === 20;
  const targetAc = target.ac + attackContext.coverAcBonus;
  const hit = naturalTwenty || (!naturalOne && attackTotal >= targetAc);
  const automaticCritical = weapon.kind === 'melee' && target.conditions.unconscious;
  const critical = hit && (naturalTwenty || automaticCritical);

  let primaryCandidate: DamageCandidate | null = null;
  let savageCandidate: DamageCandidate | null = null;
  let chosenCandidate: 'primary' | 'savage' | null = null;
  let advantageBonusCandidate: DamageCandidate | null = null;
  let masteryApplied: MasteryType | null = null;
  let masteryNotes: string | null = null;
  let totalDamage = 0;
  let hpDelta = 0;
  const conditionDeltas: string[] = [];
  let savageAttackerConsumed = false;

  if (hit) {
    const applyGwf = weapon.kind === 'melee' && weapon.twoHanded === true;
    primaryCandidate = rollDamageCandidate(state, weapon, overrides.damageRolls, applyGwf);

    if (args.savageAttackerAvailable) {
      savageCandidate = rollDamageCandidate(
        state,
        weapon,
        overrides.savageDamageRolls,
        applyGwf
      );
      savageAttackerConsumed = true;
    }

    const chosen = chooseDamageCandidate(primaryCandidate, savageCandidate);
    chosenCandidate = chosen.chosen;

    if (mode === 'advantage' && weapon.advantageDamageDice) {
      advantageBonusCandidate = rollBonusCandidate(state, weapon, overrides.advantageDamageRolls);
    }

    const criticalMultiplier = critical ? 2 : 1;
    totalDamage =
      chosen.candidate.subtotal * criticalMultiplier +
      (advantageBonusCandidate ? advantageBonusCandidate.subtotal * criticalMultiplier : 0) +
      weapon.damageModifier;

    const damageResult = applyDamage(state, args.targetId, totalDamage, critical);
    hpDelta = damageResult.hpDelta;
    conditionDeltas.push(...damageResult.conditionDeltas);

    const masteryResult = applyMastery(
      state,
      args.attackerId,
      args.targetId,
      weapon.mastery,
      true,
      totalDamage
    );
    masteryApplied = masteryResult.masteryApplied;
    masteryNotes = masteryResult.masteryNotes;
    conditionDeltas.push(...masteryResult.conditionDeltas);
  } else if (weapon.mastery === 'graze') {
    masteryApplied = 'graze';
    masteryNotes = `${target.id} takes ${weapon.abilityModifier} graze damage on the miss.`;
    totalDamage = Math.max(0, weapon.abilityModifier);

    const damageResult = applyDamage(state, args.targetId, totalDamage, false);
    hpDelta = damageResult.hpDelta;
    conditionDeltas.push(...damageResult.conditionDeltas);
  }

  if (sapConsumed > 0) {
    conditionDeltas.push(`${args.attackerId}'s sap disadvantage is consumed on this attack roll.`);
  }

  const criticalMultiplier = critical ? 2 : 1;
  const hitLabel = critical ? 'critical hit' : hit ? 'hit' : 'miss';

  return {
    event: {
      ...eventBase(state, args.attackerId),
      targetIds: [args.targetId],
      eventType: 'attack',
      rawRolls: {
        attackRolls,
        advantageSources,
        disadvantageSources
      },
      resolvedTotals: {
        attackMode: mode,
        selectedRoll,
        attackTotal,
        targetAc,
        coverAcBonus: attackContext.coverAcBonus,
        distanceSquares: attackContext.distanceSquares,
        distanceFeet: attackContext.distanceFeet,
        hit,
        critical,
        sapConsumed,
        opportunityAttack: args.isOpportunityAttack ?? false
      },
      movementDetails: args.movementDetails ?? null,
      damageDetails: {
        weaponId: args.weaponId,
        weaponName: weapon.displayName,
        damageType: weapon.damageType,
        primaryCandidate,
        savageCandidate,
        chosenCandidate,
        criticalApplied: critical,
        criticalMultiplier,
        flatModifier: weapon.damageModifier,
        advantageBonusCandidate,
        masteryApplied,
        masteryNotes,
        totalDamage,
        hpDelta
      },
      conditionDeltas,
      textSummary: `${args.isOpportunityAttack ? 'Opportunity attack: ' : ''}${args.attackerId} attacks ${args.targetId} with ${
        weapon.displayName
      }: ${hitLabel}${totalDamage > 0 ? ` for ${totalDamage} damage` : ''}.`
    },
    savageAttackerConsumed
  };
}
