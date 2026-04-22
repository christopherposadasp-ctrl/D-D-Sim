import type {
  BatchJobStatus,
  BatchSummary,
  EnemyCatalogResponse,
  EncounterConfig,
  EncounterSummary,
  PlayerCatalogResponse,
  RunEncounterResult,
  UnitState,
  Winner
} from '../shared/sim/types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

function buildApiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function getApiErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown };

    if (typeof payload.detail === 'string' && payload.detail.length > 0) {
      return payload.detail;
    }

    if (typeof payload.message === 'string' && payload.message.length > 0) {
      return payload.message;
    }
  } catch {
    // Fall back to the generic HTTP status message if the response body is not JSON.
  }

  return `Request failed with status ${response.status}.`;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(buildApiUrl(path));

  if (!response.ok) {
    throw new Error(await getApiErrorMessage(response));
  }

  return (await response.json()) as T;
}

async function postJson<T>(path: string, config: EncounterConfig): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(config)
  });

  if (!response.ok) {
    throw new Error(await getApiErrorMessage(response));
  }

  return (await response.json()) as T;
}

function getWinnerFromBatch(batchSummary: BatchSummary): Winner {
  if (batchSummary.playerWinRate === 1) {
    return 'fighters';
  }

  if (batchSummary.goblinWinRate === 1) {
    return 'goblins';
  }

  return 'mutual_annihilation';
}

function countConsciousFighters(units: Record<string, UnitState>): number {
  return Object.values(units).filter((unit) => unit.faction === 'fighters' && unit.currentHp > 0).length;
}

export function createEncounterSummary(
  encounter: RunEncounterResult,
  batchSummary: BatchSummary
): EncounterSummary {
  return {
    seed: batchSummary.seed,
    playerBehavior: encounter.finalState.playerBehavior,
    monsterBehavior: encounter.finalState.monsterBehavior,
    winner: getWinnerFromBatch(batchSummary),
    rounds: batchSummary.averageRounds,
    fighterDeaths: batchSummary.averageFighterDeaths,
    goblinsKilled: batchSummary.averageGoblinsKilled,
    remainingFighterHp: batchSummary.averageRemainingFighterHp,
    remainingGoblinHp: batchSummary.averageRemainingGoblinHp,
    stableUnconsciousFighters: batchSummary.stableButUnconsciousCount,
    consciousFighters: countConsciousFighters(encounter.finalState.units)
  };
}

export async function runEncounterRequest(config: EncounterConfig): Promise<RunEncounterResult> {
  return postJson<RunEncounterResult>('/api/encounters/run', config);
}

export async function getEnemyCatalogRequest(): Promise<EnemyCatalogResponse> {
  return getJson<EnemyCatalogResponse>('/api/catalog/enemies');
}

export async function getPlayerCatalogRequest(): Promise<PlayerCatalogResponse> {
  return getJson<PlayerCatalogResponse>('/api/catalog/classes');
}

export async function runBatchRequest(config: EncounterConfig): Promise<BatchSummary> {
  return postJson<BatchSummary>('/api/encounters/batch', config);
}

export async function startBatchJobRequest(config: EncounterConfig): Promise<BatchJobStatus> {
  return postJson<BatchJobStatus>('/api/encounters/batch-jobs', config);
}

export async function getBatchJobStatusRequest(jobId: string): Promise<BatchJobStatus> {
  return getJson<BatchJobStatus>(`/api/encounters/batch-jobs/${jobId}`);
}
