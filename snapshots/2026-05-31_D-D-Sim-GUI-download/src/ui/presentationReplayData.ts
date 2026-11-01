import type {
  BatchSummary,
  EncounterConfig,
  RunEncounterResult,
  UnitState,
} from '../shared/sim/types';
import {
  PRESENTATION_REPLAY_CONFIG,
  PRESENTATION_SAVED_REPLAY_URL,
} from './presentationConfig';

type SavedPresentationReplayPayload = RunEncounterResult | { result: RunEncounterResult };

function getSavedReplayFromPayload(payload: SavedPresentationReplayPayload): RunEncounterResult {
  if ('result' in payload) {
    return payload.result;
  }

  return payload;
}

export async function loadSavedPresentationReplay(): Promise<RunEncounterResult | null> {
  if (!PRESENTATION_SAVED_REPLAY_URL) {
    return null;
  }

  const response = await fetch(PRESENTATION_SAVED_REPLAY_URL);

  if (!response.ok) {
    throw new Error(`Saved replay request failed with status ${response.status}.`);
  }

  return getSavedReplayFromPayload((await response.json()) as SavedPresentationReplayPayload);
}

export function isSavedPresentationScenarioId(enemyPresetId: string | undefined): boolean {
  return enemyPresetId === PRESENTATION_REPLAY_CONFIG.enemyPresetId;
}

export function isSavedPresentationReplayConfig(config: EncounterConfig): boolean {
  return isSavedPresentationScenarioId(config.enemyPresetId);
}

export async function loadSavedReplayForConfig(config: EncounterConfig): Promise<RunEncounterResult | null> {
  if (!isSavedPresentationReplayConfig(config)) {
    return null;
  }

  return loadSavedPresentationReplay();
}

function isFighter(unit: UnitState): boolean {
  return unit.faction === 'fighters';
}

function isEnemy(unit: UnitState): boolean {
  return unit.faction === 'goblins';
}

function isDefeated(unit: UnitState): boolean {
  return unit.conditions.dead || unit.currentHp <= 0;
}

function sumRemainingHp(units: UnitState[], predicate: (unit: UnitState) => boolean): number {
  return units
    .filter(predicate)
    .reduce((total, unit) => total + Math.max(0, unit.currentHp), 0);
}

export function createBatchSummaryFromSavedReplay(
  encounter: RunEncounterResult,
  config: EncounterConfig
): BatchSummary {
  const units = Object.values(encounter.finalState.units);
  const playerWinRate = encounter.finalState.winner === 'fighters' ? 1 : 0;
  const goblinWinRate = encounter.finalState.winner === 'goblins' ? 1 : 0;

  return {
    seed: encounter.finalState.seed,
    playerBehavior: config.playerBehavior ?? encounter.finalState.playerBehavior,
    monsterBehavior: config.monsterBehavior ?? encounter.finalState.monsterBehavior,
    batchSize: config.batchSize ?? PRESENTATION_REPLAY_CONFIG.batchSize,
    totalRuns: 1,
    playerWinRate,
    goblinWinRate,
    mutualAnnihilationRate: encounter.finalState.winner === 'mutual_annihilation' ? 1 : 0,
    smartPlayerWinRate: config.playerBehavior === 'smart' ? playerWinRate : null,
    dumbPlayerWinRate: config.playerBehavior === 'dumb' ? playerWinRate : null,
    smartRunCount: config.playerBehavior === 'smart' ? 1 : 0,
    dumbRunCount: config.playerBehavior === 'dumb' ? 1 : 0,
    averageRounds: encounter.finalState.round,
    averageFighterDeaths: units.filter((unit) => isFighter(unit) && unit.conditions.dead).length,
    averageGoblinsKilled: units.filter((unit) => isEnemy(unit) && isDefeated(unit)).length,
    averageRemainingFighterHp: sumRemainingHp(units, isFighter),
    averageRemainingGoblinHp: sumRemainingHp(units, isEnemy),
    stableButUnconsciousCount: units.filter(
      (unit) => isFighter(unit) && unit.conditions.unconscious && unit.stable
    ).length,
    combinationSummaries: null,
  };
}
