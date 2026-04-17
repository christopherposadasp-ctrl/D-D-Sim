import {
  DEFAULT_BATCH_SIZE,
  DEFAULT_BATCH_MONSTER_BEHAVIOR,
  DEFAULT_BATCH_PLAYER_BEHAVIOR,
  DEFAULT_SEED,
  DEFAULT_POSITIONS,
  MAX_BATCH_SIZE,
  UNIT_IDS
} from '../engine/constants';
import { inspectPlacements } from '../engine/spatial';
import { runBatch, runEncounter, summarizeEncounter } from '../engine';
import type {
  BatchSummary,
  EncounterSummary,
  GridPosition,
  MonsterBehaviorSelection,
  PlayerBehavior,
  ReplayFrame,
  RunEncounterResult
} from '../engine/types';

export interface UiState {
  seedInput: string;
  batchSizeInput: string;
  playerBehaviorInput: PlayerBehavior;
  monsterBehaviorInput: MonsterBehaviorSelection;
  encounter: RunEncounterResult | null;
  encounterSummary: EncounterSummary | null;
  batchSummary: BatchSummary | null;
  replayIndex: number;
  isAutoplaying: boolean;
  error: string | null;
  placements: Record<string, GridPosition>;
  selectedPlacementUnitId: string | null;
}

export type UiAction =
  | { type: 'setSeed'; value: string }
  | { type: 'setBatchSize'; value: string }
  | { type: 'setPlayerBehavior'; value: PlayerBehavior }
  | { type: 'setMonsterBehavior'; value: MonsterBehaviorSelection }
  | { type: 'runBatch' }
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

export function createInitialUiState(): UiState {
  return {
    seedInput: DEFAULT_SEED,
    batchSizeInput: String(DEFAULT_BATCH_SIZE),
    playerBehaviorInput: DEFAULT_BATCH_PLAYER_BEHAVIOR,
    monsterBehaviorInput: DEFAULT_BATCH_MONSTER_BEHAVIOR,
    encounter: null,
    encounterSummary: null,
    batchSummary: null,
    replayIndex: 0,
    isAutoplaying: false,
    error: null,
    placements: { ...DEFAULT_POSITIONS },
    selectedPlacementUnitId: UNIT_IDS[0]
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
  'encounter' | 'encounterSummary' | 'batchSummary' | 'replayIndex' | 'isAutoplaying'
>;

const EMPTY_SIMULATION_RESULTS: SimulationResultState = {
  encounter: null,
  encounterSummary: null,
  batchSummary: null,
  replayIndex: 0,
  isAutoplaying: false
};

function clearSimulationResults(): SimulationResultState {
  return { ...EMPTY_SIMULATION_RESULTS };
}

function getNextPlacementUnitId(
  placements: Record<string, GridPosition>,
  fallbackUnitId: string | null
): string {
  return UNIT_IDS.find((unitId) => !placements[unitId]) ?? fallbackUnitId ?? UNIT_IDS[0];
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

export function uiReducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'setSeed':
      return {
        ...state,
        seedInput: action.value
      };
    case 'setBatchSize':
      return {
        ...state,
        batchSizeInput: action.value
      };
    case 'setPlayerBehavior':
      return {
        ...state,
        playerBehaviorInput: action.value
      };
    case 'setMonsterBehavior':
      return {
        ...state,
        monsterBehaviorInput: action.value
      };
    case 'runBatch': {
      const batchSize = Number.parseInt(state.batchSizeInput, 10);

      if (!Number.isInteger(batchSize) || batchSize < 1) {
        return {
          ...state,
          error: 'Batch size must be a positive integer.'
        };
      }

      if (batchSize > MAX_BATCH_SIZE) {
        return {
          ...state,
          error: `Batch size must be ${MAX_BATCH_SIZE} or lower in the browser runner.`
        };
      }

      const validation = inspectPlacements(state.placements);

      if (!validation.isValid) {
        return {
          ...state,
          isAutoplaying: false,
          error: validation.errors[0] ?? 'The simulator requires a complete, valid placement layout.'
        };
      }

      try {
        if (batchSize === 1 && state.monsterBehaviorInput !== 'combined') {
          const encounter = runEncounter({
            seed: state.seedInput,
            placements: state.placements,
            playerBehavior: state.playerBehaviorInput,
            monsterBehavior: state.monsterBehaviorInput
          });
          const encounterSummary = summarizeEncounter(encounter.finalState);
          const batchSummary = runBatch({
            seed: state.seedInput,
            batchSize,
            placements: state.placements,
            playerBehavior: state.playerBehaviorInput,
            monsterBehavior: state.monsterBehaviorInput
          });

          return resetSimulationView(state, {
            encounter,
            encounterSummary,
            batchSummary
          });
        }

        const batchSummary = runBatch({
          seed: state.seedInput,
          batchSize,
          placements: state.placements,
          playerBehavior: state.playerBehaviorInput,
          monsterBehavior: state.monsterBehaviorInput
        });

        return resetSimulationView(state, { batchSummary });
      } catch (error) {
        return {
          ...state,
          isAutoplaying: false,
          error: error instanceof Error ? error.message : 'Failed to run batch simulation.'
        };
      }
    }
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
        placements: { ...DEFAULT_POSITIONS },
        selectedPlacementUnitId: UNIT_IDS[0],
      });
    case 'placeUnit': {
      const nextPlacements = {
        ...state.placements,
        [action.unitId]: action.position
      };

      return resetSimulationView(state, {
        placements: nextPlacements,
        selectedPlacementUnitId: getNextPlacementUnitId(nextPlacements, action.unitId)
      });
    }
    default:
      return state;
  }
}
