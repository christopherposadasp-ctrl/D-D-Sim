import frostfallCourtyardVariantSeed from './scenarioSeeds/frostfall_courtyard_variant.json';
import type {
  EncounterState,
  GridPosition,
  MonsterBehaviorSelection,
  PlayerBehavior,
  ReplayFrame,
  SavedScenarioDelayedArrival,
} from './types';

interface SavedScenarioSeedFile {
  seed: string;
  scenarioId?: string;
  scenarioName?: string;
  description?: string;
  enemyPresetId?: string;
  playerPresetId: string;
  playerBehavior: PlayerBehavior;
  monsterBehavior: MonsterBehaviorSelection;
  selectedUnitId?: string;
  placements?: Record<string, GridPosition>;
  initialState?: EncounterState;
  delayedArrivals?: SavedScenarioDelayedArrival[];
  spriteRoleMap?: Record<string, string>;
  result?: {
    replayFrames?: ReplayFrame[];
    finalState?: EncounterState;
  };
}

export interface FixedScenarioSeed {
  seed: string;
  scenarioName?: string;
  description?: string;
  enemyPresetId: string;
  playerPresetId: string;
  playerBehavior: PlayerBehavior;
  monsterBehavior: MonsterBehaviorSelection;
  selectedUnitId?: string;
  placements: Record<string, GridPosition>;
  initialState?: EncounterState;
  delayedArrivals?: SavedScenarioDelayedArrival[];
  spriteRoleMap?: Record<string, string>;
}

export const FIXED_SCENARIO_SEEDS: Record<string, FixedScenarioSeed> = {
  frostfall_courtyard_variant: normalizeFixedScenarioSeed(
    frostfallCourtyardVariantSeed as SavedScenarioSeedFile
  ),
};

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function getInitialState(source: SavedScenarioSeedFile): EncounterState | undefined {
  return source.initialState ?? source.result?.replayFrames?.[0]?.state;
}

function getPlacementsFromInitialState(initialState: EncounterState | undefined): Record<string, GridPosition> {
  if (!initialState) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(initialState.units)
      .filter(([, unit]) => Boolean(unit.position))
      .map(([unitId, unit]) => [unitId, { ...unit.position! }])
  );
}

function normalizeFixedScenarioSeed(source: SavedScenarioSeedFile): FixedScenarioSeed {
  const initialState = getInitialState(source);
  const placements = source.placements ?? getPlacementsFromInitialState(initialState);

  return {
    seed: source.seed,
    scenarioName: source.scenarioName,
    description: source.description,
    enemyPresetId: source.enemyPresetId ?? source.scenarioId ?? '',
    playerPresetId: source.playerPresetId,
    playerBehavior: source.playerBehavior,
    monsterBehavior: source.monsterBehavior,
    selectedUnitId:
      source.selectedUnitId ??
      initialState?.initiativeOrder.find((unitId) => unitId.startsWith('F')) ??
      initialState?.initiativeOrder[0],
    placements,
    initialState,
    delayedArrivals: source.delayedArrivals,
    spriteRoleMap: source.spriteRoleMap,
  };
}

export function getFixedScenarioSeed(enemyPresetId: string): FixedScenarioSeed | null {
  const fixedSeed = FIXED_SCENARIO_SEEDS[enemyPresetId];

  if (!fixedSeed) {
    return null;
  }

  return cloneJson(fixedSeed);
}
