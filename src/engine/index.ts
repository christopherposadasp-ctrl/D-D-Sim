import { chooseTurnDecision } from './ai';
import {
  DEFAULT_BATCH_SIZE,
  DEFAULT_BATCH_MONSTER_BEHAVIOR,
  DEFAULT_BATCH_PLAYER_BEHAVIOR,
  DEFAULT_MONSTER_BEHAVIOR,
  DEFAULT_PLAYER_BEHAVIOR,
  DEFAULT_SEED,
  FIGHTER_IDS,
  GOBLIN_IDS,
  MAX_BATCH_SIZE,
  MONSTER_BEHAVIORS,
  UNIT_IDS
} from './constants';
import {
  cloneValue,
  compareUnitIds,
  describeWinner,
  getFinalWinner,
  getRemainingHp,
  getUnitsByFaction,
  isUnitConscious,
  isUnitStableAtZero
} from './helpers';
import { normalizeSeed, rollDie } from './rng';
import { assertValidPlacements } from './spatial';
import {
  attemptSecondWind,
  attemptStabilize,
  createSkipEvent,
  expireTurnEffects,
  resolveAttack,
  resolveDeathSave
} from './rules';
import { createFighter, createGoblin } from './templates';
import type {
  BatchSummary,
  BatchCombinationSummary,
  CombatEvent,
  EncounterConfig,
  EncounterState,
  EncounterSummary,
  GridPosition,
  MonsterBehavior,
  MonsterBehaviorSelection,
  PlayerBehavior,
  ReplayFrame,
  ResolvedPlayerBehavior,
  RunEncounterResult,
  StepEncounterResult,
  UnitState
} from './types';

function formatPosition(position: GridPosition): string {
  return `(${position.x},${position.y})`;
}

function clonePlacements(placements: Record<string, GridPosition>): Record<string, GridPosition> {
  const clonedPlacements: Record<string, GridPosition> = {};

  for (const unitId of UNIT_IDS) {
    const position = placements[unitId];

    if (position) {
      clonedPlacements[unitId] = { ...position };
    }
  }

  return clonedPlacements;
}

function resolvePlacements(config: EncounterConfig): Record<string, GridPosition> {
  if (!config.placements) {
    throw new Error('The simulator requires a complete manual placement layout before combat starts.');
  }

  const placements = config.placements;
  assertValidPlacements(placements);
  return clonePlacements(placements);
}

function resolvePlayerBehavior(
  requestedBehavior: PlayerBehavior | undefined,
  runIndex = 0
): ResolvedPlayerBehavior {
  const behavior = requestedBehavior ?? DEFAULT_PLAYER_BEHAVIOR;

  if (behavior === 'balanced') {
    return runIndex % 2 === 0 ? 'smart' : 'dumb';
  }

  return behavior;
}

function resolveMonsterBehavior(requestedBehavior: MonsterBehaviorSelection | undefined): MonsterBehavior {
  const behavior = requestedBehavior ?? DEFAULT_MONSTER_BEHAVIOR;

  if (behavior === 'combined') {
    throw new Error('Combined DM behavior is only available for batch runs.');
  }

  return behavior;
}

interface BatchAccumulator {
  fighterWins: number;
  goblinWins: number;
  mutualAnnihilations: number;
  smartPlayerWins: number;
  dumbPlayerWins: number;
  smartRunCount: number;
  dumbRunCount: number;
  roundsTotal: number;
  fighterDeathsTotal: number;
  goblinsKilledTotal: number;
  remainingFighterHpTotal: number;
  remainingGoblinHpTotal: number;
  stableButUnconsciousCount: number;
  totalRuns: number;
}

function createEmptyBatchAccumulator(): BatchAccumulator {
  return {
    fighterWins: 0,
    goblinWins: 0,
    mutualAnnihilations: 0,
    smartPlayerWins: 0,
    dumbPlayerWins: 0,
    smartRunCount: 0,
    dumbRunCount: 0,
    roundsTotal: 0,
    fighterDeathsTotal: 0,
    goblinsKilledTotal: 0,
    remainingFighterHpTotal: 0,
    remainingGoblinHpTotal: 0,
    stableButUnconsciousCount: 0,
    totalRuns: 0
  };
}

function mergeBatchAccumulators(left: BatchAccumulator, right: BatchAccumulator): BatchAccumulator {
  return {
    fighterWins: left.fighterWins + right.fighterWins,
    goblinWins: left.goblinWins + right.goblinWins,
    mutualAnnihilations: left.mutualAnnihilations + right.mutualAnnihilations,
    smartPlayerWins: left.smartPlayerWins + right.smartPlayerWins,
    dumbPlayerWins: left.dumbPlayerWins + right.dumbPlayerWins,
    smartRunCount: left.smartRunCount + right.smartRunCount,
    dumbRunCount: left.dumbRunCount + right.dumbRunCount,
    roundsTotal: left.roundsTotal + right.roundsTotal,
    fighterDeathsTotal: left.fighterDeathsTotal + right.fighterDeathsTotal,
    goblinsKilledTotal: left.goblinsKilledTotal + right.goblinsKilledTotal,
    remainingFighterHpTotal: left.remainingFighterHpTotal + right.remainingFighterHpTotal,
    remainingGoblinHpTotal: left.remainingGoblinHpTotal + right.remainingGoblinHpTotal,
    stableButUnconsciousCount: left.stableButUnconsciousCount + right.stableButUnconsciousCount,
    totalRuns: left.totalRuns + right.totalRuns
  };
}

function finalizeBatchSummary(
  seed: string,
  playerBehavior: PlayerBehavior,
  monsterBehavior: MonsterBehaviorSelection,
  batchSize: number,
  accumulator: BatchAccumulator,
  combinationSummaries: BatchCombinationSummary[] | null
): BatchSummary {
  return {
    seed,
    playerBehavior,
    monsterBehavior,
    batchSize,
    totalRuns: accumulator.totalRuns,
    playerWinRate: accumulator.fighterWins / accumulator.totalRuns,
    goblinWinRate: accumulator.goblinWins / accumulator.totalRuns,
    mutualAnnihilationRate: accumulator.mutualAnnihilations / accumulator.totalRuns,
    smartPlayerWinRate:
      accumulator.smartRunCount > 0 ? accumulator.smartPlayerWins / accumulator.smartRunCount : null,
    dumbPlayerWinRate:
      accumulator.dumbRunCount > 0 ? accumulator.dumbPlayerWins / accumulator.dumbRunCount : null,
    smartRunCount: accumulator.smartRunCount,
    dumbRunCount: accumulator.dumbRunCount,
    averageRounds: accumulator.roundsTotal / accumulator.totalRuns,
    averageFighterDeaths: accumulator.fighterDeathsTotal / accumulator.totalRuns,
    averageGoblinsKilled: accumulator.goblinsKilledTotal / accumulator.totalRuns,
    averageRemainingFighterHp: accumulator.remainingFighterHpTotal / accumulator.totalRuns,
    averageRemainingGoblinHp: accumulator.remainingGoblinHpTotal / accumulator.totalRuns,
    stableButUnconsciousCount: accumulator.stableButUnconsciousCount,
    combinationSummaries
  };
}

function finalizeBatchCombinationSummary(
  seed: string,
  playerBehavior: PlayerBehavior,
  monsterBehavior: MonsterBehavior,
  batchSize: number,
  accumulator: BatchAccumulator
): BatchCombinationSummary {
  return {
    seed,
    playerBehavior,
    monsterBehavior,
    batchSize,
    totalRuns: accumulator.totalRuns,
    playerWinRate: accumulator.fighterWins / accumulator.totalRuns,
    goblinWinRate: accumulator.goblinWins / accumulator.totalRuns,
    mutualAnnihilationRate: accumulator.mutualAnnihilations / accumulator.totalRuns,
    smartPlayerWinRate:
      accumulator.smartRunCount > 0 ? accumulator.smartPlayerWins / accumulator.smartRunCount : null,
    dumbPlayerWinRate:
      accumulator.dumbRunCount > 0 ? accumulator.dumbPlayerWins / accumulator.dumbRunCount : null,
    smartRunCount: accumulator.smartRunCount,
    dumbRunCount: accumulator.dumbRunCount,
    averageRounds: accumulator.roundsTotal / accumulator.totalRuns,
    averageFighterDeaths: accumulator.fighterDeathsTotal / accumulator.totalRuns,
    averageGoblinsKilled: accumulator.goblinsKilledTotal / accumulator.totalRuns,
    averageRemainingFighterHp: accumulator.remainingFighterHpTotal / accumulator.totalRuns,
    averageRemainingGoblinHp: accumulator.remainingGoblinHpTotal / accumulator.totalRuns,
    stableButUnconsciousCount: accumulator.stableButUnconsciousCount
  };
}

function runSingleBatchAccumulator(
  config: EncounterConfig,
  requestedPlayerBehavior: PlayerBehavior,
  requestedMonsterBehavior: MonsterBehavior
): BatchAccumulator {
  const requestedSize = config.batchSize ?? DEFAULT_BATCH_SIZE;
  const placements = resolvePlacements(config);
  const accumulator = createEmptyBatchAccumulator();

  for (let index = 0; index < requestedSize; index += 1) {
    const derivedSeed = `${config.seed.trim() || DEFAULT_SEED}#${index + 1}`;
    const resolvedBehavior = resolvePlayerBehavior(requestedPlayerBehavior, index);
    const result = runEncounter({
      seed: derivedSeed,
      placements: clonePlacements(placements),
      playerBehavior: resolvedBehavior,
      monsterBehavior: requestedMonsterBehavior
    });
    const summary = summarizeEncounter(result.finalState);

    if (summary.winner === 'fighters') {
      accumulator.fighterWins += 1;
      if (resolvedBehavior === 'smart') {
        accumulator.smartPlayerWins += 1;
      } else {
        accumulator.dumbPlayerWins += 1;
      }
    } else if (summary.winner === 'goblins') {
      accumulator.goblinWins += 1;
    } else if (summary.winner === 'mutual_annihilation') {
      accumulator.mutualAnnihilations += 1;
    }

    if (resolvedBehavior === 'smart') {
      accumulator.smartRunCount += 1;
    } else {
      accumulator.dumbRunCount += 1;
    }

    accumulator.roundsTotal += summary.rounds;
    accumulator.fighterDeathsTotal += summary.fighterDeaths;
    accumulator.goblinsKilledTotal += summary.goblinsKilled;
    accumulator.remainingFighterHpTotal += summary.remainingFighterHp;
    accumulator.remainingGoblinHpTotal += summary.remainingGoblinHp;
    accumulator.totalRuns += 1;

    if (summary.stableUnconsciousFighters > 0) {
      accumulator.stableButUnconsciousCount += 1;
    }
  }

  return accumulator;
}

function buildUnits(placements: Record<string, GridPosition>): Record<string, UnitState> {
  const units: Record<string, UnitState> = {
    F1: createFighter('F1'),
    F2: createFighter('F2'),
    F3: createFighter('F3'),
    G1: createGoblin('G1'),
    G2: createGoblin('G2'),
    G3: createGoblin('G3'),
    G4: createGoblin('G4'),
    G5: createGoblin('G5'),
    G6: createGoblin('G6'),
    G7: createGoblin('G7')
  };

  for (const [unitId, position] of Object.entries(placements)) {
    units[unitId].position = { ...position };
  }

  return units;
}

function sortInitiativeEntries(
  entries: Array<{ id: string; total: number; faction: 'fighters' | 'goblins' }>
): Array<{ id: string; total: number; faction: 'fighters' | 'goblins' }> {
  return [...entries].sort((left, right) => {
    if (left.total !== right.total) {
      return right.total - left.total;
    }

    if (left.faction !== right.faction) {
      return left.faction === 'fighters' ? -1 : 1;
    }

    return left.id.localeCompare(right.id, undefined, { numeric: true });
  });
}

function pushEvent(state: EncounterState, events: CombatEvent[], event: CombatEvent | null): void {
  if (!event) {
    return;
  }

  events.push(event);
}

function fightersDefeated(state: EncounterState): boolean {
  return getUnitsByFaction(state, 'fighters').every((unit) => unit.currentHp === 0 || unit.conditions.dead);
}

function goblinsDefeated(state: EncounterState): boolean {
  return getUnitsByFaction(state, 'goblins').every((unit) => unit.conditions.dead);
}

function fightersResolved(state: EncounterState): boolean {
  return getUnitsByFaction(state, 'fighters').every(
    (unit) => unit.currentHp > 0 || unit.stable || unit.conditions.dead
  );
}

function addPhaseEvent(state: EncounterState, actorId: string, textSummary: string): CombatEvent {
  return {
    round: state.round,
    actorId,
    targetIds: [],
    eventType: 'phase_change',
    rawRolls: {},
    resolvedTotals: {
      winner: state.winner
    },
    movementDetails: null,
    damageDetails: null,
    conditionDeltas: [],
    textSummary
  };
}

function updateEncounterPhase(state: EncounterState, actorId: string): CombatEvent[] {
  const events: CombatEvent[] = [];

  if (!state.rescueSubphase && (fightersDefeated(state) || goblinsDefeated(state))) {
    state.winner = getFinalWinner(state);

    if (fightersResolved(state)) {
      state.terminalState = 'complete';
      state.rescueSubphase = false;
      events.push(
        addPhaseEvent(
          state,
          actorId,
          `Combat ends. ${describeWinner(state.winner)}. No rescue turns are required.`
        )
      );
    } else {
      state.terminalState = 'rescue';
      state.rescueSubphase = true;
      events.push(
        addPhaseEvent(
          state,
          actorId,
          `Combat ends. ${describeWinner(state.winner)}. Rescue turns continue until every fighter is conscious, stable, or dead.`
        )
      );
    }
  } else if (state.rescueSubphase && fightersResolved(state)) {
    state.winner = getFinalWinner(state);
    state.terminalState = 'complete';
    state.rescueSubphase = false;
    events.push(
      addPhaseEvent(
        state,
        actorId,
        `Rescue subphase ends. ${describeWinner(state.winner)}.`
      )
    );
  }

  return events;
}

function advanceInitiative(state: EncounterState): void {
  const nextIndex = state.activeCombatantIndex + 1;

  if (nextIndex >= state.initiativeOrder.length) {
    state.activeCombatantIndex = 0;
    state.round += 1;
    return;
  }

  state.activeCombatantIndex = nextIndex;
}

function getOpportunityAttackWeaponId(unit: UnitState): 'greatsword' | 'scimitar' {
  return unit.faction === 'fighters' ? 'greatsword' : 'scimitar';
}

function getMoveSquares(unit: UnitState): number {
  return Math.floor(unit.effectiveSpeed / 5);
}

function getMovementDistance(movement: { path: GridPosition[]; mode: 'move' | 'dash' } | undefined): number {
  if (!movement || movement.path.length <= 1) {
    return 0;
  }

  return movement.path.length - 1;
}

function getTotalMovementBudget(
  actor: UnitState,
  action: { kind: 'attack' | 'stabilize' | 'dash' | 'skip' }
): number {
  const moveSquares = getMoveSquares(actor);
  return action.kind === 'dash' ? moveSquares * 2 : moveSquares;
}

function createMovementEvent(
  state: EncounterState,
  actorId: string,
  path: GridPosition[],
  mode: 'move' | 'dash',
  disengageApplied: boolean,
  triggeredAttackers: string[],
  phase: 'before_action' | 'after_action'
): CombatEvent | null {
  if (path.length <= 1) {
    return null;
  }

  const start = path[0];
  const end = path[path.length - 1];
  const distance = path.length - 1;

  return {
    round: state.round,
    actorId,
    targetIds: [],
    eventType: 'move',
    rawRolls: {},
    resolvedTotals: {
      movementMode: mode,
      movementPhase: phase,
      disengageApplied,
      opportunityAttackers: triggeredAttackers
    },
    movementDetails: {
      start,
      end,
      path,
      distance
    },
    damageDetails: null,
    conditionDeltas: [],
    textSummary: `${actorId} ${mode === 'dash' ? 'dashes' : 'moves'} ${distance} square${
      distance === 1 ? '' : 's'
    } from ${formatPosition(start)} to ${formatPosition(end)}${
      disengageApplied ? ' using Disengage' : ''
    } ${phase === 'before_action' ? 'before acting' : 'after acting'}.`
  };
}

function executeMovement(
  state: EncounterState,
  actorId: string,
  movement: { path: GridPosition[]; mode: 'move' | 'dash' } | undefined,
  disengageApplied: boolean,
  phase: 'before_action' | 'after_action'
): { events: CombatEvent[]; interrupted: boolean } {
  if (!movement) {
    return {
      events: [],
      interrupted: false
    };
  }

  const actor = state.units[actorId];

  if (!actor.position || movement.path.length <= 1) {
    return {
      events: [],
      interrupted: false
    };
  }

  const pathTravelled: GridPosition[] = [movement.path[0]];
  const reactionEvents: CombatEvent[] = [];
  const triggeredAttackers: string[] = [];

  for (let index = 1; index < movement.path.length; index += 1) {
    const previous = movement.path[index - 1];
    const next = movement.path[index];
    actor.position = { ...next };
    pathTravelled.push({ ...next });

    if (disengageApplied) {
      continue;
    }

    const opportunityAttackers = Object.values(state.units)
      .filter(
        (unit) =>
          unit.faction !== actor.faction &&
          unit.currentHp > 0 &&
          !unit.conditions.dead &&
          unit.reactionAvailable &&
          unit.position &&
          Math.max(Math.abs(unit.position.x - previous.x), Math.abs(unit.position.y - previous.y)) <= 1 &&
          Math.max(Math.abs(unit.position.x - next.x), Math.abs(unit.position.y - next.y)) > 1
      )
      .sort((left, right) => compareUnitIds(left.id, right.id));

    for (const reactionUnit of opportunityAttackers) {
      reactionUnit.reactionAvailable = false;
      triggeredAttackers.push(reactionUnit.id);

      const attackResult = resolveAttack(state, {
        attackerId: reactionUnit.id,
        targetId: actorId,
        weaponId: getOpportunityAttackWeaponId(reactionUnit),
        savageAttackerAvailable: reactionUnit.faction === 'fighters',
        isOpportunityAttack: true
      });
      reactionEvents.push(attackResult.event);

      if (actor.conditions.dead || actor.currentHp === 0) {
        const moveEvent = createMovementEvent(
          state,
          actorId,
          pathTravelled,
          movement.mode,
          disengageApplied,
          triggeredAttackers,
          phase
        );

        return {
          events: moveEvent ? [moveEvent, ...reactionEvents] : reactionEvents,
          interrupted: true
        };
      }
    }
  }

  const moveEvent = createMovementEvent(
    state,
    actorId,
    pathTravelled,
    movement.mode,
    disengageApplied,
    triggeredAttackers,
    phase
  );

  return {
    events: moveEvent ? [moveEvent, ...reactionEvents] : reactionEvents,
    interrupted: false
  };
}

function canActAfterMovement(actor: UnitState): boolean {
  return !actor.conditions.dead && actor.currentHp > 0;
}

function resolveBonusAction(
  state: EncounterState,
  actorId: string,
  bonusAction: {
    kind: 'second_wind' | 'disengage';
    timing: 'before_action' | 'after_action';
  } | undefined
): CombatEvent | null {
  if (!bonusAction) {
    return null;
  }

  if (bonusAction.kind === 'second_wind') {
    return attemptSecondWind(state, actorId);
  }

  return null;
}

function exceedsMovementBudget(
  actor: UnitState,
  decision: {
    preActionMovement?: { path: GridPosition[]; mode: 'move' | 'dash' };
    postActionMovement?: { path: GridPosition[]; mode: 'move' | 'dash' };
    action: { kind: 'attack' | 'stabilize' | 'dash' | 'skip' };
  }
): boolean {
  const totalDistance =
    getMovementDistance(decision.preActionMovement) + getMovementDistance(decision.postActionMovement);
  return totalDistance > getTotalMovementBudget(actor, decision.action);
}

export function createEncounter(config: EncounterConfig): EncounterState {
  const seed = config.seed.trim() || DEFAULT_SEED;
  const playerBehavior = resolvePlayerBehavior(config.playerBehavior);
  const monsterBehavior = resolveMonsterBehavior(config.monsterBehavior);
  const placements = resolvePlacements(config);
  const units = buildUnits(placements);
  let rngState = normalizeSeed(seed);
  const initiativeEntries: Array<{ id: string; total: number; faction: 'fighters' | 'goblins' }> = [];
  const initiativeScores: Record<string, number> = {};

  for (const fighterId of FIGHTER_IDS) {
    const roll = rollDie(rngState, 20);
    rngState = roll.state;
    const total = roll.value + units[fighterId].initiativeMod;
    units[fighterId].initiativeScore = total;
    initiativeScores[fighterId] = total;
    initiativeEntries.push({
      id: fighterId,
      total,
      faction: 'fighters'
    });
  }

  const goblinInitiativeRoll = rollDie(rngState, 20);
  rngState = goblinInitiativeRoll.state;

  for (const goblinId of GOBLIN_IDS) {
    const total = goblinInitiativeRoll.value + units[goblinId].initiativeMod;
    units[goblinId].initiativeScore = total;
    initiativeScores[goblinId] = total;
    initiativeEntries.push({
      id: goblinId,
      total,
      faction: 'goblins'
    });
  }

  const initiativeOrder = sortInitiativeEntries(initiativeEntries).map((entry) => entry.id);

  return {
    seed,
    playerBehavior,
    monsterBehavior,
    rngState,
    round: 1,
    initiativeOrder,
    initiativeScores,
    activeCombatantIndex: 0,
    units,
    combatLog: [],
    winner: null,
    terminalState: 'ongoing',
    rescueSubphase: false
  };
}

export function stepEncounter(state: EncounterState): StepEncounterResult {
  if (state.terminalState === 'complete') {
    return {
      state: cloneValue(state),
      events: [],
      done: true
    };
  }

  const nextState = cloneValue(state);
  const actorId = nextState.initiativeOrder[nextState.activeCombatantIndex];
  const actor = nextState.units[actorId];
  const events: CombatEvent[] = [
    {
      round: nextState.round,
      actorId,
      targetIds: [actorId],
      eventType: 'turn_start',
      rawRolls: {},
      resolvedTotals: {
        rescueSubphase: nextState.rescueSubphase
      },
      movementDetails: null,
      damageDetails: null,
      conditionDeltas: [],
      textSummary: `${actorId} starts turn ${nextState.round}.${nextState.rescueSubphase ? ' Rescue subphase.' : ''}`
    }
  ];

  events.push(...expireTurnEffects(nextState, actorId));
  nextState.units[actorId].reactionAvailable = true;

  if (actor.conditions.dead) {
    events.push(createSkipEvent(nextState, actorId, 'Dead units do not act.'));
  } else if (actor.currentHp === 0 && !nextState.rescueSubphase) {
    if (actor.stable) {
      events.push(createSkipEvent(nextState, actorId, 'Stable fighters do not act while unconscious.'));
    } else {
      events.push(resolveDeathSave(nextState, actorId));
    }
  } else if (nextState.rescueSubphase) {
    if (actor.faction === 'goblins') {
      events.push(createSkipEvent(nextState, actorId, 'Goblins take no rescue-subphase actions.'));
    } else if (actor.currentHp === 0) {
      if (actor.stable) {
        events.push(createSkipEvent(nextState, actorId, 'Stable fighters do not act while unconscious.'));
      } else {
        events.push(resolveDeathSave(nextState, actorId));
      }
    } else {
      const decision = chooseTurnDecision(nextState, actorId);
      if (exceedsMovementBudget(nextState.units[actorId], decision)) {
        events.push(createSkipEvent(nextState, actorId, 'Planned movement exceeds the unit speed budget.'));
      } else {
        if (decision.bonusAction?.timing === 'before_action') {
          pushEvent(nextState, events, resolveBonusAction(nextState, actorId, decision.bonusAction));
        }

        const preMovementResult = executeMovement(
          nextState,
          actorId,
          decision.preActionMovement,
          decision.bonusAction?.kind === 'disengage' && decision.bonusAction.timing === 'before_action',
          'before_action'
        );
        events.push(...preMovementResult.events);

        if (canActAfterMovement(nextState.units[actorId])) {
          if (decision.action.kind === 'stabilize') {
            events.push(attemptStabilize(nextState, actorId, decision.action.targetId));
          } else if (decision.action.kind === 'skip') {
            events.push(createSkipEvent(nextState, actorId, decision.action.reason));
          }
        }

        if (canActAfterMovement(nextState.units[actorId]) && decision.bonusAction?.timing === 'after_action') {
          pushEvent(nextState, events, resolveBonusAction(nextState, actorId, decision.bonusAction));
        }

        if (canActAfterMovement(nextState.units[actorId])) {
          const postMovementResult = executeMovement(
            nextState,
            actorId,
            decision.postActionMovement,
            decision.bonusAction?.kind === 'disengage',
            'after_action'
          );
          events.push(...postMovementResult.events);
        }
      }
    }
  } else {
    const decision = chooseTurnDecision(nextState, actorId);

    if (exceedsMovementBudget(nextState.units[actorId], decision)) {
      events.push(createSkipEvent(nextState, actorId, 'Planned movement exceeds the unit speed budget.'));
    } else {
      if (decision.bonusAction?.timing === 'before_action') {
        pushEvent(nextState, events, resolveBonusAction(nextState, actorId, decision.bonusAction));
      }

      const preMovementResult = executeMovement(
        nextState,
        actorId,
        decision.preActionMovement,
        decision.bonusAction?.kind === 'disengage' && decision.bonusAction.timing === 'before_action',
        'before_action'
      );
      events.push(...preMovementResult.events);

      if (canActAfterMovement(nextState.units[actorId])) {
        if (decision.action.kind === 'attack') {
          const attackResult = resolveAttack(nextState, {
            attackerId: actorId,
            targetId: decision.action.targetId,
            weaponId: decision.action.weaponId,
            savageAttackerAvailable: actor.faction === 'fighters'
          });
          events.push(attackResult.event);
        } else if (decision.action.kind === 'skip') {
          events.push(createSkipEvent(nextState, actorId, decision.action.reason));
        }
      }

      if (canActAfterMovement(nextState.units[actorId]) && decision.bonusAction?.timing === 'after_action') {
        pushEvent(nextState, events, resolveBonusAction(nextState, actorId, decision.bonusAction));
      }

      if (canActAfterMovement(nextState.units[actorId])) {
        const postMovementResult = executeMovement(
          nextState,
          actorId,
          decision.postActionMovement,
          decision.bonusAction?.kind === 'disengage',
          'after_action'
        );
        events.push(...postMovementResult.events);
      }
    }
  }

  events.push(...updateEncounterPhase(nextState, actorId));
  nextState.combatLog = [...nextState.combatLog, ...events];

  const done = nextState.terminalState === 'complete';

  if (!done) {
    advanceInitiative(nextState);
  }

  return {
    state: nextState,
    events,
    done
  };
}

export function runEncounter(config: EncounterConfig): RunEncounterResult {
  let workingState = createEncounter(config);
  const replayFrames: ReplayFrame[] = [
    {
      index: 0,
      round: workingState.round,
      activeCombatantId: workingState.initiativeOrder[workingState.activeCombatantIndex],
      state: cloneValue(workingState),
      events: []
    }
  ];

  let guard = 0;

  while (workingState.terminalState !== 'complete') {
    const actorId = workingState.initiativeOrder[workingState.activeCombatantIndex];
    const result = stepEncounter(workingState);
    workingState = result.state;

    replayFrames.push({
      index: replayFrames.length,
      round: workingState.round,
      activeCombatantId: actorId,
      state: cloneValue(workingState),
      events: cloneValue(result.events)
    });

    guard += 1;

    if (guard > 1000) {
      throw new Error('Encounter loop guard tripped.');
    }
  }

  return {
    finalState: workingState,
    events: cloneValue(workingState.combatLog),
    replayFrames
  };
}

export function summarizeEncounter(state: EncounterState): EncounterSummary {
  const fighters = getUnitsByFaction(state, 'fighters');
  const goblins = getUnitsByFaction(state, 'goblins');

  return {
    seed: state.seed,
    playerBehavior: state.playerBehavior,
    monsterBehavior: state.monsterBehavior,
    winner: state.winner,
    rounds: state.round,
    fighterDeaths: fighters.filter((unit) => unit.conditions.dead).length,
    goblinsKilled: goblins.filter((unit) => unit.conditions.dead).length,
    remainingFighterHp: getRemainingHp(fighters),
    remainingGoblinHp: getRemainingHp(goblins),
    stableUnconsciousFighters: fighters.filter((unit) => isUnitStableAtZero(unit)).length,
    consciousFighters: fighters.filter((unit) => isUnitConscious(unit)).length
  };
}

export function runBatch(config: EncounterConfig): BatchSummary {
  const requestedSize = config.batchSize ?? DEFAULT_BATCH_SIZE;
  const requestedPlayerBehavior = config.playerBehavior ?? DEFAULT_BATCH_PLAYER_BEHAVIOR;
  const requestedMonsterBehavior = config.monsterBehavior ?? DEFAULT_BATCH_MONSTER_BEHAVIOR;

  if (!Number.isInteger(requestedSize) || requestedSize < 1 || requestedSize > MAX_BATCH_SIZE) {
    throw new Error(`Batch size must be an integer between 1 and ${MAX_BATCH_SIZE}.`);
  }

  const seed = config.seed.trim() || DEFAULT_SEED;

  if (requestedMonsterBehavior === 'combined') {
    const combinationSummaries = MONSTER_BEHAVIORS.map((monsterBehavior) => {
      const accumulator = runSingleBatchAccumulator(config, requestedPlayerBehavior, monsterBehavior);

      return finalizeBatchCombinationSummary(
        seed,
        requestedPlayerBehavior,
        monsterBehavior,
        requestedSize,
        accumulator
      );
    });
    const combinedAccumulator = combinationSummaries.reduce(
      (accumulator, summary) =>
        mergeBatchAccumulators(accumulator, {
          fighterWins: summary.playerWinRate * summary.totalRuns,
          goblinWins: summary.goblinWinRate * summary.totalRuns,
          mutualAnnihilations: summary.mutualAnnihilationRate * summary.totalRuns,
          smartPlayerWins:
            summary.smartPlayerWinRate === null ? 0 : summary.smartPlayerWinRate * summary.smartRunCount,
          dumbPlayerWins:
            summary.dumbPlayerWinRate === null ? 0 : summary.dumbPlayerWinRate * summary.dumbRunCount,
          smartRunCount: summary.smartRunCount,
          dumbRunCount: summary.dumbRunCount,
          roundsTotal: summary.averageRounds * summary.totalRuns,
          fighterDeathsTotal: summary.averageFighterDeaths * summary.totalRuns,
          goblinsKilledTotal: summary.averageGoblinsKilled * summary.totalRuns,
          remainingFighterHpTotal: summary.averageRemainingFighterHp * summary.totalRuns,
          remainingGoblinHpTotal: summary.averageRemainingGoblinHp * summary.totalRuns,
          stableButUnconsciousCount: summary.stableButUnconsciousCount,
          totalRuns: summary.totalRuns
        }),
      createEmptyBatchAccumulator()
    );

    return finalizeBatchSummary(
      seed,
      requestedPlayerBehavior,
      'combined',
      requestedSize,
      combinedAccumulator,
      combinationSummaries
    );
  }

  const accumulator = runSingleBatchAccumulator(config, requestedPlayerBehavior, requestedMonsterBehavior);

  return finalizeBatchSummary(
    seed,
    requestedPlayerBehavior,
    requestedMonsterBehavior,
    requestedSize,
    accumulator,
    null
  );
}
