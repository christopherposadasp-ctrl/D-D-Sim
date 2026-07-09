import {
  DEFAULT_SEED,
  FIGHTER_IDS,
  MAX_BATCH_SIZE,
  getCombinedUnitIds,
  getDefaultPlacementsForPreset,
  getPlacementFootprintsForPreset,
  getTerrainFeaturesForPreset
} from './catalog';
import { inspectPlacementsForUnitIds } from '../shared/sim/spatial';
import type {
  BatchJobStatus,
  BatchSummary,
  EncounterConfig,
  EncounterSummary,
  EnemyCatalogResponse,
  GridPosition,
  MonsterBehaviorSelection,
  PlayerBehavior,
  PlayerCatalogResponse,
  ReplayFrame,
  RunEncounterResult
} from '../shared/sim/types';

export interface UiState {
  enemyCatalog: EnemyCatalogResponse | null;
  playerCatalog: PlayerCatalogResponse | null;
  seedInput: string;
  batchSizeInput: string;
  enemyPresetIdInput: string;
  playerPresetIdInput: string;
  playerBehaviorInput: PlayerBehavior;
  monsterBehaviorInput: MonsterBehaviorSelection;
  encounter: RunEncounterResult | null;
  encounterSummary: EncounterSummary | null;
  batchSummary: BatchSummary | null;
  batchJobStatus: BatchJobStatus | null;
  isRunning: boolean;
  replayIndex: number;
  isAutoplaying: boolean;
  error: string | null;
  placements: Record<string, GridPosition>;
  selectedPlacementUnitId: string | null;
}

export type UiAction =
  | {
      type: 'catalogsLoadSuccess';
      enemyCatalog: EnemyCatalogResponse;
      playerCatalog: PlayerCatalogResponse;
    }
  | { type: 'catalogLoadError'; message: string }
  | { type: 'setSeed'; value: string }
  | { type: 'setBatchSize'; value: string }
  | { type: 'setEnemyPreset'; value: string }
  | { type: 'setPlayerPreset'; value: string }
  | { type: 'setPlayerBehavior'; value: PlayerBehavior }
  | { type: 'setMonsterBehavior'; value: MonsterBehaviorSelection }
  | { type: 'runSimulationStart' }
  | { type: 'setBatchJobStatus'; batchJobStatus: BatchJobStatus | null }
  | {
      type: 'runSimulationSuccess';
      encounter: RunEncounterResult | null;
      encounterSummary: EncounterSummary | null;
      batchSummary: BatchSummary;
      batchJobStatus?: BatchJobStatus | null;
    }
  | { type: 'runSimulationError'; message: string; batchJobStatus?: BatchJobStatus | null }
  | { type: 'editLayout' }
  | { type: 'setReplayIndex'; value: number }
  | { type: 'toggleAutoplay' }
  | { type: 'tickAutoplay' }
  | { type: 'clearError' }
  | { type: 'selectPlacementUnit'; unitId: string }
  | { type: 'resetLayout' }
  | {
      type: 'placeUnit';
      unitId: string;
      position: GridPosition;
    };

function createCatalogBackedState(
  enemyCatalog: EnemyCatalogResponse,
  playerCatalog: PlayerCatalogResponse
): Pick<
  UiState,
  'enemyCatalog' | 'playerCatalog' | 'enemyPresetIdInput' | 'playerPresetIdInput' | 'placements' | 'selectedPlacementUnitId'
> {
  const enemyPresetIdInput = enemyCatalog.defaultEnemyPresetId;
  const playerPresetIdInput = playerCatalog.defaultPlayerPresetId;
  const activeUnitIds = getCombinedUnitIds(enemyCatalog, enemyPresetIdInput, playerCatalog, playerPresetIdInput);

  return {
    enemyCatalog,
    playerCatalog,
    enemyPresetIdInput,
    playerPresetIdInput,
    placements: getDefaultPlacementsForPreset(enemyCatalog, enemyPresetIdInput, playerCatalog, playerPresetIdInput),
    selectedPlacementUnitId: activeUnitIds[0] ?? FIGHTER_IDS[0]
  };
}

export function createInitialUiState(
  enemyCatalog: EnemyCatalogResponse | null = null,
  playerCatalog: PlayerCatalogResponse | null = null
): UiState {
  const catalogState =
    enemyCatalog && playerCatalog
      ? createCatalogBackedState(enemyCatalog, playerCatalog)
      : {
          enemyCatalog: null,
          playerCatalog: null,
          enemyPresetIdInput: '',
          playerPresetIdInput: '',
          placements: {},
          selectedPlacementUnitId: null
        };

  return {
    seedInput: DEFAULT_SEED,
    batchSizeInput: '100',
    playerBehaviorInput: 'balanced',
    monsterBehaviorInput: 'combined',
    encounter: null,
    encounterSummary: null,
    batchSummary: null,
    batchJobStatus: null,
    isRunning: false,
    replayIndex: 0,
    isAutoplaying: false,
    error: null,
    ...catalogState
  };
}

function getBoundedReplayIndex(state: UiState, value: number): number {
  if (!state.encounter) {
    return 0;
  }

  const maxIndex = state.encounter.replayFrames.length - 1;
  return Math.min(Math.max(0, value), maxIndex);
}

type SimulationResultState = Pick<
  UiState,
  'encounter' | 'encounterSummary' | 'batchSummary' | 'batchJobStatus' | 'replayIndex' | 'isAutoplaying'
>;

const EMPTY_SIMULATION_RESULTS: SimulationResultState = {
  encounter: null,
  encounterSummary: null,
  batchSummary: null,
  batchJobStatus: null,
  replayIndex: 0,
  isAutoplaying: false
};

function clearSimulationResults(): SimulationResultState {
  return { ...EMPTY_SIMULATION_RESULTS };
}

function getNextPlacementUnitId(
  placements: Record<string, GridPosition>,
  activeUnitIds: string[],
  fallbackUnitId: string | null
): string | null {
  return activeUnitIds.find((unitId) => !placements[unitId]) ?? fallbackUnitId ?? activeUnitIds[0] ?? null;
}

function resetSimulationView(state: UiState, overrides: Partial<UiState> = {}): UiState {
  return {
    ...state,
    ...clearSimulationResults(),
    error: null,
    ...overrides
  };
}

export function getCurrentReplayFrame(state: UiState): ReplayFrame | null {
  if (!state.encounter) {
    return null;
  }

  return state.encounter.replayFrames[state.replayIndex] ?? null;
}

export interface SimulationExecutionPlan {
  config: EncounterConfig;
  includeEncounterReplay: boolean;
}

export function createSimulationExecutionPlan(state: UiState): SimulationExecutionPlan {
  if (!state.enemyCatalog || !state.playerCatalog || !state.enemyPresetIdInput || !state.playerPresetIdInput) {
    throw new Error('The encounter catalog is still loading.');
  }

  const batchSize = Number.parseInt(state.batchSizeInput, 10);
  const activeUnitIds = getCombinedUnitIds(
    state.enemyCatalog,
    state.enemyPresetIdInput,
    state.playerCatalog,
    state.playerPresetIdInput
  );
  const footprintsByUnitId = getPlacementFootprintsForPreset(
    state.enemyCatalog,
    state.enemyPresetIdInput,
    state.playerCatalog,
    state.playerPresetIdInput
  );
  const terrainFeatures = getTerrainFeaturesForPreset(state.enemyCatalog, state.enemyPresetIdInput);

  if (!Number.isInteger(batchSize) || batchSize < 1) {
    throw new Error('Batch size must be a positive integer.');
  }

  if (batchSize > MAX_BATCH_SIZE) {
    throw new Error(`Batch size must be ${MAX_BATCH_SIZE} or lower in the browser runner.`);
  }

  const validation = inspectPlacementsForUnitIds(
    state.placements,
    activeUnitIds,
    footprintsByUnitId,
    terrainFeatures
  );

  if (!validation.isValid) {
    throw new Error(validation.errors[0] ?? 'The simulator requires a complete, valid placement layout.');
  }

  return {
    config: {
      seed: state.seedInput,
      batchSize,
      placements: state.placements,
      enemyPresetId: state.enemyPresetIdInput,
      playerPresetId: state.playerPresetIdInput,
      playerBehavior: state.playerBehaviorInput,
      monsterBehavior: state.monsterBehaviorInput
    },
    includeEncounterReplay: batchSize === 1 && state.monsterBehaviorInput !== 'combined'
  };
}

export function uiReducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'catalogsLoadSuccess': {
      const catalogState = createCatalogBackedState(action.enemyCatalog, action.playerCatalog);
      return resetSimulationView(state, {
        ...catalogState,
        error: null
      });
    }
    case 'catalogLoadError':
      return {
        ...state,
        error: action.message
      };
    case 'setSeed':
      return {
        ...state,
        seedInput: action.value,
        error: null
      };
    case 'setBatchSize':
      return {
        ...state,
        batchSizeInput: action.value,
        error: null
      };
    case 'setEnemyPreset': {
      if (!state.enemyCatalog) {
        return state;
      }

      const placements = getDefaultPlacementsForPreset(
        state.enemyCatalog,
        action.value,
        state.playerCatalog,
        state.playerPresetIdInput
      );
      const activeUnitIds = getCombinedUnitIds(
        state.enemyCatalog,
        action.value,
        state.playerCatalog,
        state.playerPresetIdInput
      );

      return resetSimulationView(state, {
        enemyPresetIdInput: action.value,
        placements,
        selectedPlacementUnitId: activeUnitIds[0] ?? null
      });
    }
    case 'setPlayerPreset': {
      const placements = getDefaultPlacementsForPreset(
        state.enemyCatalog,
        state.enemyPresetIdInput,
        state.playerCatalog,
        action.value
      );
      const activeUnitIds = getCombinedUnitIds(
        state.enemyCatalog,
        state.enemyPresetIdInput,
        state.playerCatalog,
        action.value
      );

      return resetSimulationView(state, {
        playerPresetIdInput: action.value,
        placements,
        selectedPlacementUnitId: activeUnitIds[0] ?? null
      });
    }
    case 'setPlayerBehavior':
      return {
        ...state,
        playerBehaviorInput: action.value,
        error: null
      };
    case 'setMonsterBehavior':
      return {
        ...state,
        monsterBehaviorInput: action.value,
        error: null
      };
    case 'runSimulationStart':
      return {
        ...state,
        batchJobStatus: null,
        isRunning: true,
        isAutoplaying: false,
        error: null
      };
    case 'setBatchJobStatus':
      return {
        ...state,
        batchJobStatus: action.batchJobStatus
      };
    case 'runSimulationSuccess':
      return resetSimulationView(state, {
        encounter: action.encounter,
        encounterSummary: action.encounterSummary,
        batchSummary: action.batchSummary,
        batchJobStatus: action.batchJobStatus ?? null,
        isRunning: false
      });
    case 'runSimulationError':
      return {
        ...state,
        batchJobStatus: action.batchJobStatus ?? state.batchJobStatus,
        isRunning: false,
        isAutoplaying: false,
        error: action.message
      };
    case 'editLayout':
      return resetSimulationView(state);
    case 'setReplayIndex':
      return {
        ...state,
        replayIndex: getBoundedReplayIndex(state, action.value),
        isAutoplaying: false
      };
    case 'toggleAutoplay': {
      if (!state.encounter) {
        return state;
      }

      const lastIndex = state.encounter.replayFrames.length - 1;
      const shouldRestart = state.replayIndex >= lastIndex;

      return {
        ...state,
        replayIndex: shouldRestart ? 0 : state.replayIndex,
        isAutoplaying: !state.isAutoplaying
      };
    }
    case 'tickAutoplay': {
      if (!state.encounter || !state.isAutoplaying) {
        return state;
      }

      const lastIndex = state.encounter.replayFrames.length - 1;

      if (state.replayIndex >= lastIndex) {
        return {
          ...state,
          isAutoplaying: false
        };
      }

      return {
        ...state,
        replayIndex: state.replayIndex + 1
      };
    }
    case 'clearError':
      return {
        ...state,
        error: null
      };
    case 'selectPlacementUnit':
      return {
        ...state,
        selectedPlacementUnitId: action.unitId,
        error: null
      };
    case 'resetLayout':
      return resetSimulationView(state, {
        placements: getDefaultPlacementsForPreset(
          state.enemyCatalog,
          state.enemyPresetIdInput,
          state.playerCatalog,
          state.playerPresetIdInput
        ),
        selectedPlacementUnitId:
          getCombinedUnitIds(
            state.enemyCatalog,
            state.enemyPresetIdInput,
            state.playerCatalog,
            state.playerPresetIdInput
          )[0] ?? null
      });
    case 'placeUnit': {
      const nextPlacements = {
        ...state.placements,
        [action.unitId]: action.position
      };

      return resetSimulationView(state, {
        placements: nextPlacements,
        selectedPlacementUnitId: getNextPlacementUnitId(
          nextPlacements,
          getCombinedUnitIds(
            state.enemyCatalog,
            state.enemyPresetIdInput,
            state.playerCatalog,
            state.playerPresetIdInput
          ),
          action.unitId
        )
      });
    }
    default:
      return state;
  }
}
