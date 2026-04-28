import { startTransition, useDeferredValue, useEffect, useReducer, useState } from 'react';

import { getOccupiedSquaresForPosition, inspectPlacementsForUnitIds, terrainBlocksPlacement } from '../shared/sim/spatial';
import type {
  BatchJobStatus,
  EnemyCatalogResponse,
  GridPosition,
  PlayerCatalogResponse,
  UnitState
} from '../shared/sim/types';
import {
  ControlsPanel,
  CurrentFramePanel,
  EncounterSummaryPanel,
  HeroSection,
  TimelinePanel,
  UnitStatePanel,
  VisualizationPanel,
  type AttackLine,
  type BoardUnit
} from './components';
import {
  createEncounterSummary,
  getBatchJobStatusRequest,
  getEnemyCatalogRequest,
  getPlayerCatalogRequest,
  runBatchRequest,
  runEncounterRequest,
  startBatchJobRequest
} from './api';
import {
  createInitialUiState,
  createSimulationExecutionPlan,
  type SimulationExecutionPlan,
  uiReducer
} from './store';
import {
  FIGHTER_IDS,
  MEDIUM_FOOTPRINT,
  getCombinedUnitIds,
  getPlacementFootprintsForPreset,
  getTerrainFeaturesForPreset
} from './catalog';

function sortUnits(units: Record<string, UnitState>): UnitState[] {
  return Object.values(units).sort((left, right) =>
    left.id.localeCompare(right.id, undefined, { numeric: true })
  );
}

function combineMovementPaths(paths: GridPosition[][]): GridPosition[] {
  const combined: GridPosition[] = [];

  for (const path of paths) {
    for (const position of path) {
      const last = combined[combined.length - 1];

      if (!last || last.x !== position.x || last.y !== position.y) {
        combined.push(position);
      }
    }
  }

  return combined;
}

const BATCH_JOB_POLL_INTERVAL_MS = 500;

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

const EMPTY_FOOTPRINTS: Record<string, { width: number; height: number }> = Object.fromEntries(
  FIGHTER_IDS.map((fighterId) => [fighterId, MEDIUM_FOOTPRINT])
);

interface AppProps {
  initialEnemyCatalog?: EnemyCatalogResponse | null;
  initialPlayerCatalog?: PlayerCatalogResponse | null;
}

export function App(props: AppProps = {}) {
  const [state, dispatch] = useReducer(
    uiReducer,
    createInitialUiState(props.initialEnemyCatalog ?? null, props.initialPlayerCatalog ?? null)
  );
  const [clockNowMs, setClockNowMs] = useState(() => Date.now());
  const deferredReplayIndex = useDeferredValue(state.replayIndex);
  const currentFrame = state.encounter?.replayFrames[deferredReplayIndex] ?? null;
  const initialFrame = state.encounter?.replayFrames[0] ?? null;
  const currentState = currentFrame?.state ?? initialFrame?.state ?? null;
  const orderedUnits: UnitState[] = currentState ? sortUnits(currentState.units) : [];
  const activeUnitIds = getCombinedUnitIds(
    state.enemyCatalog,
    state.enemyPresetIdInput,
    state.playerCatalog,
    state.playerPresetIdInput
  );
  const placementFootprints =
    state.enemyCatalog && state.enemyPresetIdInput
      ? getPlacementFootprintsForPreset(
          state.enemyCatalog,
          state.enemyPresetIdInput,
          state.playerCatalog,
          state.playerPresetIdInput
        )
      : EMPTY_FOOTPRINTS;
  const terrainFeatures =
    state.enemyCatalog && state.enemyPresetIdInput
      ? getTerrainFeaturesForPreset(state.enemyCatalog, state.enemyPresetIdInput)
      : [];
  const placementValidation = inspectPlacementsForUnitIds(
    state.placements,
    activeUnitIds,
    placementFootprints,
    terrainFeatures
  );
  const setupUnits: BoardUnit[] = activeUnitIds.map((unitId) => ({
    id: unitId,
    faction: unitId.startsWith('F') ? 'fighters' : 'goblins',
    position: state.placements[unitId],
    footprint: placementFootprints[unitId] ?? MEDIUM_FOOTPRINT
  }));
  const visibleEventCount = currentFrame?.state.combatLog.length ?? 0;
  const timelineEvents = state.encounter?.events.slice(0, visibleEventCount) ?? [];
  const isSetupMode = !state.encounter;
  const canRunSimulation = Boolean(state.enemyCatalog && state.playerCatalog) && placementValidation.isValid;
  const spatialReplayActive = Boolean(currentState);
  const movementEvents = currentFrame?.events.filter((event) => event.eventType === 'move') ?? [];
  const highlightedPath = combineMovementPaths(
    movementEvents
      .map((event) => event.movementDetails?.path ?? [])
      .filter((path) => path.length > 1)
  );
  const currentAttackEvent =
    [...(currentFrame?.events ?? [])].reverse().find((event) => event.eventType === 'attack') ?? null;
  const attackTargetId = currentAttackEvent?.targetIds[0] ?? null;
  const attackLine: AttackLine | null =
    currentState &&
    currentAttackEvent &&
    attackTargetId &&
    currentState.units[currentAttackEvent.actorId]?.position &&
    currentState.units[attackTargetId]?.position
      ? {
          actorId: currentAttackEvent.actorId,
          targetId: attackTargetId,
          from: currentState.units[currentAttackEvent.actorId].position!,
          to: currentState.units[attackTargetId].position!,
          fromFootprint: currentState.units[currentAttackEvent.actorId].footprint ?? MEDIUM_FOOTPRINT,
          toFootprint: currentState.units[attackTargetId].footprint ?? MEDIUM_FOOTPRINT
        }
      : null;
  const placementStatusText = !state.enemyCatalog || !state.playerCatalog
    ? 'Loading encounter catalogs.'
    : placementValidation.isValid
      ? `All ${activeUnitIds.length} units are placed. Combat is ready.`
      : placementValidation.outOfBoundsUnitIds.length > 0 ||
          placementValidation.overlappingGroups.length > 0 ||
          placementValidation.blockedSquareGroups.length > 0
        ? placementValidation.errors[0]
        : `Place the remaining units: ${placementValidation.missingUnitIds.join(', ')}.`;
  const batchElapsedSeconds =
    state.batchJobStatus === null
      ? null
      : state.batchJobStatus.finishedAt
        ? state.batchJobStatus.elapsedSeconds
        : Math.max(
            state.batchJobStatus.elapsedSeconds,
            (clockNowMs - Date.parse(state.batchJobStatus.startedAt)) / 1000
          );

  async function pollBatchJob(jobId: string): Promise<BatchJobStatus> {
    let currentStatus = await getBatchJobStatusRequest(jobId);

    startTransition(() => {
      dispatch({ type: 'setBatchJobStatus', batchJobStatus: currentStatus });
    });

    while (currentStatus.status === 'queued' || currentStatus.status === 'running') {
      await sleep(BATCH_JOB_POLL_INTERVAL_MS);
      currentStatus = await getBatchJobStatusRequest(jobId);

      startTransition(() => {
        dispatch({ type: 'setBatchJobStatus', batchJobStatus: currentStatus });
      });
    }

    return currentStatus;
  }

  async function handleRunBatch(): Promise<void> {
    let plan: SimulationExecutionPlan;

    try {
      plan = createSimulationExecutionPlan(state);
    } catch (error) {
      startTransition(() => {
        dispatch({
          type: 'runSimulationError',
          message: error instanceof Error ? error.message : 'Failed to validate the simulation request.'
        });
      });
      return;
    }

    startTransition(() => {
      dispatch({ type: 'runSimulationStart' });
    });

    try {
      if (plan.includeEncounterReplay) {
        const [encounter, batchSummary] = await Promise.all([
          runEncounterRequest(plan.config),
          runBatchRequest(plan.config)
        ]);

        startTransition(() => {
          dispatch({
            type: 'runSimulationSuccess',
            encounter,
            encounterSummary: createEncounterSummary(encounter, batchSummary),
            batchSummary,
            batchJobStatus: null
          });
        });
        return;
      }

      const initialJobStatus = await startBatchJobRequest(plan.config);

      startTransition(() => {
        dispatch({ type: 'setBatchJobStatus', batchJobStatus: initialJobStatus });
      });

      const finalJobStatus = await pollBatchJob(initialJobStatus.jobId);

      if (finalJobStatus.status === 'failed') {
        startTransition(() => {
          dispatch({
            type: 'runSimulationError',
            message: finalJobStatus.error ?? 'Batch simulation failed.',
            batchJobStatus: finalJobStatus
          });
        });
        return;
      }

      if (!finalJobStatus.batchSummary) {
        startTransition(() => {
          dispatch({
            type: 'runSimulationError',
            message: 'Batch job completed without a summary.',
            batchJobStatus: finalJobStatus
          });
        });
        return;
      }

      const batchSummary = finalJobStatus.batchSummary;

      startTransition(() => {
        dispatch({
          type: 'runSimulationSuccess',
          encounter: null,
          encounterSummary: null,
          batchSummary,
          batchJobStatus: finalJobStatus
        });
      });
    } catch (error) {
      startTransition(() => {
        dispatch({
          type: 'runSimulationError',
          message: error instanceof Error ? error.message : 'Failed to run the simulation.'
        });
      });
    }
  }

  function handlePlacementCellClick(position: GridPosition, occupantId: string | null): void {
    const blockingTerrainOccupiesSquare = terrainFeatures.some((feature) =>
      terrainBlocksPlacement(feature)
        && getOccupiedSquaresForPosition(feature.position, feature.footprint).some(
          (occupiedSquare) => occupiedSquare.x === position.x && occupiedSquare.y === position.y
        )
    );

    if (blockingTerrainOccupiesSquare) {
      return;
    }

    if (occupantId && occupantId !== state.selectedPlacementUnitId) {
      dispatch({ type: 'selectPlacementUnit', unitId: occupantId });
      return;
    }

    if (!state.selectedPlacementUnitId) {
      return;
    }

    dispatch({
      type: 'placeUnit',
      unitId: state.selectedPlacementUnitId,
      position
    });
  }

  useEffect(() => {
    if (state.enemyCatalog && state.playerCatalog) {
      return undefined;
    }

    let cancelled = false;

    void Promise.all([getEnemyCatalogRequest(), getPlayerCatalogRequest()])
      .then(([enemyCatalog, playerCatalog]) => {
        if (cancelled) {
          return;
        }

        startTransition(() => {
          dispatch({ type: 'catalogsLoadSuccess', enemyCatalog, playerCatalog });
        });
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }

        startTransition(() => {
          dispatch({
            type: 'catalogLoadError',
            message: error instanceof Error ? error.message : 'Failed to load the encounter catalogs.'
          });
        });
      });

    return () => {
      cancelled = true;
    };
  }, [state.enemyCatalog, state.playerCatalog]);

  useEffect(() => {
    if (!state.isAutoplaying) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      startTransition(() => {
        dispatch({ type: 'tickAutoplay' });
      });
    }, 700);

    return () => window.clearInterval(timer);
  }, [state.isAutoplaying]);

  useEffect(() => {
    if (!state.isRunning || !state.batchJobStatus || state.batchJobStatus.finishedAt) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setClockNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [state.isRunning, state.batchJobStatus?.startedAt, state.batchJobStatus?.finishedAt]);

  return (
    <main className="app-shell">
      <HeroSection />

      <ControlsPanel
        playerPresetIdInput={state.playerPresetIdInput}
        playerPresets={state.playerCatalog?.playerPresets ?? []}
        seedInput={state.seedInput}
        batchSizeInput={state.batchSizeInput}
        enemyPresetIdInput={state.enemyPresetIdInput}
        enemyPresets={state.enemyCatalog?.enemyPresets ?? []}
        catalogLoaded={Boolean(state.enemyCatalog && state.playerCatalog)}
        playerBehaviorInput={state.playerBehaviorInput}
        monsterBehaviorInput={state.monsterBehaviorInput}
        activeUnitCount={activeUnitIds.length}
        hasEncounter={Boolean(state.encounter)}
        isAutoplaying={state.isAutoplaying}
        replayIndex={state.replayIndex}
        replayFrameCount={state.encounter?.replayFrames.length ?? 0}
        canRunSimulation={canRunSimulation}
        isRunning={state.isRunning}
        batchJobStatus={state.batchJobStatus}
        batchElapsedSeconds={batchElapsedSeconds}
        placementValidation={placementValidation}
        placementStatusText={placementStatusText}
        error={state.error}
        onSeedChange={(value) => dispatch({ type: 'setSeed', value })}
        onBatchSizeChange={(value) => dispatch({ type: 'setBatchSize', value })}
        onEnemyPresetChange={(value) => dispatch({ type: 'setEnemyPreset', value })}
        onPlayerPresetChange={(value) => dispatch({ type: 'setPlayerPreset', value })}
        onPlayerBehaviorChange={(value) => dispatch({ type: 'setPlayerBehavior', value })}
        onMonsterBehaviorChange={(value) => dispatch({ type: 'setMonsterBehavior', value })}
        onEditLayout={() => dispatch({ type: 'editLayout' })}
        onToggleAutoplay={() => dispatch({ type: 'toggleAutoplay' })}
        onRunBatch={() => {
          void handleRunBatch();
        }}
        onReplayIndexChange={(value) =>
          dispatch({
            type: 'setReplayIndex',
            value
          })
        }
      />

      <EncounterSummaryPanel
        enemyCatalog={state.enemyCatalog}
        playerCatalog={state.playerCatalog}
        seedInput={state.seedInput}
        enemyPresetIdInput={state.enemyPresetIdInput}
        playerPresetIdInput={state.playerPresetIdInput}
        playerBehaviorInput={state.playerBehaviorInput}
        monsterBehaviorInput={state.monsterBehaviorInput}
        encounterSummary={state.encounterSummary}
        batchSummary={state.batchSummary}
      />

      <section className="grid-layout">
        <VisualizationPanel
          enemyCatalog={state.enemyCatalog}
          playerCatalog={state.playerCatalog}
          isSetupMode={isSetupMode}
          spatialReplayActive={spatialReplayActive}
          enemyPresetIdInput={state.enemyPresetIdInput}
          playerPresetIdInput={state.playerPresetIdInput}
          activeUnitIds={activeUnitIds}
        placementValidation={placementValidation}
        placements={state.placements}
        selectedPlacementUnitId={state.selectedPlacementUnitId}
        terrainFeatures={terrainFeatures}
        setupUnits={setupUnits}
        orderedUnits={orderedUnits}
          highlightedPath={highlightedPath}
          currentFrame={currentFrame}
          initialFrame={initialFrame}
          currentRound={currentState?.round ?? 1}
          attackLine={attackLine}
          onResetLayout={() => dispatch({ type: 'resetLayout' })}
          onSelectPlacementUnit={(unitId) => dispatch({ type: 'selectPlacementUnit', unitId })}
          onPlacementCellClick={handlePlacementCellClick}
        />

        <CurrentFramePanel currentFrame={currentFrame} />
      </section>

      <section className="grid-layout">
        <UnitStatePanel orderedUnits={orderedUnits} />
        <TimelinePanel timelineEvents={timelineEvents} />
      </section>
    </main>
  );
}
