import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useReducer,
  useState,
} from "react";

import {
  canPlaceUnitAtPosition,
  getOccupiedSquaresForPosition,
  inspectPlacementsForUnitIds,
  terrainBlocksPlacement,
} from "../shared/sim/spatial";
import { getFixedScenarioSeed } from "../shared/sim/scenarioSeeds";
import type {
  BatchJobStatus,
  EnemyCatalogResponse,
  EncounterState,
  Footprint,
  GridPosition,
  PlayerCatalogResponse,
  ReplayFrame,
  UnitState,
} from "../shared/sim/types";
import {
  ControlsPanel,
  CurrentFramePanel,
  EncounterSummaryPanel,
  TimelinePanel,
  VisualizationPanel,
  type AttackLine,
  type BoardUnit,
} from "./components";
import {
  createEncounterSummary,
  getBatchJobStatusRequest,
  getEnemyCatalogRequest,
  getPlayerCatalogRequest,
  runBatchRequest,
  runEncounterRequest,
  startBatchJobRequest,
} from "./api";
import {
  createInitialUiState,
  createSimulationExecutionPlan,
  type SimulationExecutionPlan,
  uiReducer,
} from "./store";
import {
  getActiveReplayMovementEvents,
  getReplayDelayMs,
  getReplayAttackLine,
} from "./replay";
import {
  FIGHTER_IDS,
  MEDIUM_FOOTPRINT,
  getCombinedUnitIds,
  getEnemyPreset,
  getPlacementFootprintsForPreset,
  getTerrainFeaturesForPreset,
  getUnitDisplayName,
} from "./catalog";
import {
  isSavedPresentationScenarioId,
} from "./presentationReplayData";
import { PresentationReplay } from "./PresentationReplay";

function sortUnits(units: Record<string, UnitState>): UnitState[] {
  return Object.values(units).sort((left, right) =>
    left.id.localeCompare(right.id, undefined, { numeric: true }),
  );
}

function mergeRosterUnits(
  initialFrame: ReplayFrame | null,
  currentState: EncounterState | null,
): UnitState[] {
  const unitsById = new Map<string, UnitState>();

  if (initialFrame) {
    for (const unit of sortUnits(initialFrame.state.units)) {
      unitsById.set(unit.id, unit);
    }
  }

  if (currentState) {
    for (const unit of sortUnits(currentState.units)) {
      unitsById.set(unit.id, unit);
    }
  }

  return Array.from(unitsById.values()).sort((left, right) =>
    left.id.localeCompare(right.id, undefined, { numeric: true }),
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

const EMPTY_FOOTPRINTS: Record<string, Footprint> = Object.fromEntries(
  FIGHTER_IDS.map((fighterId) => [fighterId, MEDIUM_FOOTPRINT]),
);

function createNewSeed(): string {
  const timestamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const suffix = Math.random().toString(36).slice(2, 8);
  return `level5-party-${timestamp}-${suffix}`;
}

interface AppProps {
  initialEnemyCatalog?: EnemyCatalogResponse | null;
  initialPlayerCatalog?: PlayerCatalogResponse | null;
}

export function App(props: AppProps = {}) {
  const [state, dispatch] = useReducer(
    uiReducer,
    createInitialUiState(
      props.initialEnemyCatalog ?? null,
      props.initialPlayerCatalog ?? null,
    ),
  );
  const [clockNowMs, setClockNowMs] = useState(() => Date.now());
  const [battleViewActive, setBattleViewActive] = useState(false);
  const [frameTransitionProgress, setFrameTransitionProgress] = useState(0);
  const [showPresentationReplay, setShowPresentationReplay] = useState(false);
  const replayFrameCount = state.encounter?.replayFrames.length ?? 0;
  const replayDelayMs = getReplayDelayMs(replayFrameCount);
  const deferredReplayIndex = useDeferredValue(state.replayIndex);
  const currentFrame =
    state.encounter?.replayFrames[deferredReplayIndex] ?? null;
  const initialFrame = state.encounter?.replayFrames[0] ?? null;
  const currentState = currentFrame?.state ?? initialFrame?.state ?? null;
  const orderedUnits: UnitState[] = currentState
    ? sortUnits(currentState.units)
    : [];
  const rosterUnits = mergeRosterUnits(initialFrame, currentState);
  const activeUnitIds = getCombinedUnitIds(
    state.enemyCatalog,
    state.enemyPresetIdInput,
    state.playerCatalog,
    state.playerPresetIdInput,
  );
  const placementFootprints =
    state.enemyCatalog && state.enemyPresetIdInput
      ? getPlacementFootprintsForPreset(
          state.enemyCatalog,
          state.enemyPresetIdInput,
          state.playerCatalog,
          state.playerPresetIdInput,
        )
      : EMPTY_FOOTPRINTS;
  const terrainFeatures = useMemo(
    () =>
      state.enemyPresetIdInput
        ? getTerrainFeaturesForPreset(state.enemyPresetIdInput)
        : [],
    [state.enemyPresetIdInput],
  );
  const placementValidation = inspectPlacementsForUnitIds(
    state.placements,
    activeUnitIds,
    placementFootprints,
    terrainFeatures,
  );
  const enemyPreset = getEnemyPreset(
    state.enemyCatalog,
    state.enemyPresetIdInput,
  );
  const setupUnits: BoardUnit[] = activeUnitIds.map((unitId) => {
    const presetUnit = enemyPreset?.units.find((unit) => unit.unitId === unitId);

    return {
      id: unitId,
      faction: unitId.startsWith("F") ? "fighters" : "goblins",
      position: state.placements[unitId],
      templateName: getUnitDisplayName(
        state.enemyCatalog,
        state.playerCatalog,
        state.enemyPresetIdInput,
        state.playerPresetIdInput,
        unitId,
      ),
      combatRole: presetUnit?.variantId,
      spriteKey: presetUnit?.variantId,
      footprint: placementFootprints[unitId] ?? MEDIUM_FOOTPRINT,
    };
  });
  const visibleEventCount = currentFrame?.state.combatLog.length ?? 0;
  const timelineEvents =
    state.encounter?.events.slice(0, visibleEventCount) ?? [];
  const isSetupMode = !state.encounter;
  const canRunSimulation =
    Boolean(state.enemyCatalog && state.playerCatalog) &&
    placementValidation.isValid;
  const scenarioPlaybackLocked = isSavedPresentationScenarioId(
    state.enemyPresetIdInput,
  );
  const spatialReplayActive = Boolean(currentState);
  const previousFrame =
    state.encounter?.replayFrames[Math.max(0, deferredReplayIndex - 1)] ?? null;
  const previousState = previousFrame?.state ?? null;
  const movementEvents = getActiveReplayMovementEvents(currentFrame);
  const highlightedPath = combineMovementPaths(
    movementEvents
      .map((event) => event.movementDetails?.path ?? [])
      .filter((path) => path.length > 1),
  );
  const attackLine: AttackLine | null = getReplayAttackLine(
    currentFrame,
    currentState,
    previousState,
  );
  const placementStatusText =
    !state.enemyCatalog || !state.playerCatalog
      ? "Loading encounter catalogs."
      : placementValidation.isValid
        ? `All ${activeUnitIds.length} units are placed. Combat is ready.`
        : placementValidation.outOfBoundsUnitIds.length > 0 ||
            placementValidation.overlappingGroups.length > 0 ||
            placementValidation.blockedSquareGroups.length > 0
          ? placementValidation.errors[0]
          : `Place the remaining units: ${placementValidation.missingUnitIds.join(", ")}.`;
  const batchElapsedSeconds =
    state.batchJobStatus === null
      ? null
      : state.batchJobStatus.finishedAt
        ? state.batchJobStatus.elapsedSeconds
        : Math.max(
            state.batchJobStatus.elapsedSeconds,
            (clockNowMs - Date.parse(state.batchJobStatus.startedAt)) / 1000,
          );

  async function pollBatchJob(jobId: string): Promise<BatchJobStatus> {
    let currentStatus = await getBatchJobStatusRequest(jobId);

    startTransition(() => {
      dispatch({ type: "setBatchJobStatus", batchJobStatus: currentStatus });
    });

    while (
      currentStatus.status === "queued" ||
      currentStatus.status === "running"
    ) {
      await sleep(BATCH_JOB_POLL_INTERVAL_MS);
      currentStatus = await getBatchJobStatusRequest(jobId);

      startTransition(() => {
        dispatch({ type: "setBatchJobStatus", batchJobStatus: currentStatus });
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
          type: "runSimulationError",
          message:
            error instanceof Error
              ? error.message
              : "Failed to validate the simulation request.",
        });
      });
      return;
    }

    if (isSavedPresentationScenarioId(plan.config.enemyPresetId)) {
      window.history.pushState(null, "", "/presentation");
      setShowPresentationReplay(true);
      return;
    }

    try {
      startTransition(() => {
        dispatch({ type: "runSimulationStart" });
      });

      if (plan.includeEncounterReplay) {
        const [encounter, batchSummary] = await Promise.all([
          runEncounterRequest(plan.config),
          runBatchRequest(plan.config),
        ]);

        startTransition(() => {
          dispatch({
            type: "runSimulationSuccess",
            encounter,
            encounterSummary: createEncounterSummary(encounter, batchSummary),
            batchSummary,
            batchJobStatus: null,
          });
        });
        return;
      }

      const initialJobStatus = await startBatchJobRequest(plan.config);

      startTransition(() => {
        dispatch({
          type: "setBatchJobStatus",
          batchJobStatus: initialJobStatus,
        });
      });

      const finalJobStatus = await pollBatchJob(initialJobStatus.jobId);

      if (finalJobStatus.status === "failed") {
        startTransition(() => {
          dispatch({
            type: "runSimulationError",
            message: finalJobStatus.error ?? "Batch simulation failed.",
            batchJobStatus: finalJobStatus,
          });
        });
        return;
      }

      if (!finalJobStatus.batchSummary) {
        startTransition(() => {
          dispatch({
            type: "runSimulationError",
            message: "Batch job completed without a summary.",
            batchJobStatus: finalJobStatus,
          });
        });
        return;
      }

      const batchSummary = finalJobStatus.batchSummary;

      startTransition(() => {
        dispatch({
          type: "runSimulationSuccess",
          encounter: null,
          encounterSummary: null,
          batchSummary,
          batchJobStatus: finalJobStatus,
        });
      });
    } catch (error) {
      startTransition(() => {
        dispatch({
          type: "runSimulationError",
          message:
            error instanceof Error
              ? error.message
              : "Failed to run the simulation.",
        });
      });
    }
  }

  function handlePlacementCellClick(
    position: GridPosition,
    occupantId: string | null,
  ): void {
    if (scenarioPlaybackLocked) {
      return;
    }

    if (occupantId) {
      dispatch({ type: "selectPlacementUnit", unitId: occupantId });
      return;
    }

    const blockingTerrainOccupiesSquare = terrainFeatures.some(
      (feature) =>
        terrainBlocksPlacement(feature) &&
        getOccupiedSquaresForPosition(feature.position, feature.footprint).some(
          (occupiedSquare) =>
            occupiedSquare.x === position.x && occupiedSquare.y === position.y,
        ),
    );

    if (blockingTerrainOccupiesSquare) {
      return;
    }

    if (!state.selectedPlacementUnitId) {
      return;
    }

    const canPlace = canPlaceUnitAtPosition(
      state.selectedPlacementUnitId,
      position,
      state.placements,
      activeUnitIds,
      placementFootprints,
      terrainFeatures,
    );

    if (!canPlace) {
      console.warn(
        "Invalid placement: footprint overlaps another unit, terrain, or board edge.",
        {
          unitId: state.selectedPlacementUnitId,
          position,
        },
      );
      return;
    }

    dispatch({
      type: "placeUnit",
      unitId: state.selectedPlacementUnitId,
      position,
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
          dispatch({
            type: "catalogsLoadSuccess",
            enemyCatalog,
            playerCatalog,
          });
        });
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }

        startTransition(() => {
          dispatch({
            type: "catalogLoadError",
            message:
              error instanceof Error
                ? error.message
                : "Failed to load the encounter catalogs.",
          });
        });
      });

    return () => {
      cancelled = true;
    };
  }, [state.enemyCatalog, state.playerCatalog]);

  useEffect(() => {
    const fixedSeed = getFixedScenarioSeed(state.enemyPresetIdInput);

    if (!fixedSeed) {
      return;
    }

    startTransition(() => {
      dispatch({
        type: "applyFixedScenarioSeed",
        fixedSeed,
      });
    });
  }, [state.enemyPresetIdInput]);

  useEffect(() => {
    if (!state.isAutoplaying) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      startTransition(() => {
        dispatch({ type: "tickAutoplay" });
      });
    }, replayDelayMs);

    return () => window.clearInterval(timer);
  }, [replayDelayMs, state.isAutoplaying]);

  useEffect(() => {
    setFrameTransitionProgress(0);

    if (!state.isAutoplaying) {
      return undefined;
    }

    const transitionStartedAt = Date.now();
    const timer = window.setInterval(() => {
      const elapsedMs = Date.now() - transitionStartedAt;
      setFrameTransitionProgress(
        Math.min((elapsedMs / replayDelayMs) * 100, 100),
      );
    }, 50);

    return () => window.clearInterval(timer);
  }, [replayDelayMs, state.isAutoplaying, state.replayIndex]);

  useEffect(() => {
    if (
      !state.isRunning ||
      !state.batchJobStatus ||
      state.batchJobStatus.finishedAt
    ) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setClockNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [
    state.isRunning,
    state.batchJobStatus?.startedAt,
    state.batchJobStatus?.finishedAt,
  ]);

  if (showPresentationReplay) {
    return <PresentationReplay />;
  }

  return (
    <main
      className={`sim-shell projector-mode ${battleViewActive ? "battle-view-active" : ""}`}
    >
      <header className="sim-topbar">
        <div className="sim-topbar-title">
          <span className="sim-eyebrow">Deterministic Combat Replay</span>
          <strong>D&amp;D Encounter Simulator</strong>
        </div>

        <div className="sim-topbar-meta">
          <span>
            Scenario: <strong>{state.enemyPresetIdInput || "-"}</strong>
          </span>
          <span>
            Party: <strong>{state.playerPresetIdInput || "-"}</strong>
          </span>
          <span>
            Seed: <strong>{state.seedInput}</strong>
          </span>
          <span
            className={`status-dot ${
              placementValidation.isValid ? "ready" : "setup"
            }`}
          >
            {placementValidation.isValid ? "Ready" : "Setup Required"}
          </span>
          <button
            type="button"
            className={`battle-view-toggle ${battleViewActive ? "active" : ""}`}
            onClick={() => setBattleViewActive((current) => !current)}
          >
            {battleViewActive ? "Exit Battle View" : "Battle View"}
          </button>
        </div>
      </header>

      <section className="sim-dashboard">
        <aside className="sim-sidebar sim-sidebar-left">
          <ControlsPanel
            playerPresetIdInput={state.playerPresetIdInput}
            playerPresets={state.playerCatalog?.playerPresets ?? []}
            seedInput={state.seedInput}
            batchSizeInput={state.batchSizeInput}
            enemyPresetIdInput={state.enemyPresetIdInput}
            enemyPresets={
              state.enemyCatalog
                ? [...state.enemyCatalog.enemyPresets].reverse()
                : []
            }
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
            scenarioPlaybackLocked={scenarioPlaybackLocked}
            error={state.error}
            onGenerateSeed={() =>
              dispatch({ type: "setSeed", value: createNewSeed() })
            }
            onBatchSizeChange={(value) =>
              dispatch({ type: "setBatchSize", value })
            }
            onEnemyPresetChange={(value) =>
              dispatch({ type: "setEnemyPreset", value })
            }
            onPlayerPresetChange={(value) =>
              dispatch({ type: "setPlayerPreset", value })
            }
            onPlayerBehaviorChange={(value) =>
              dispatch({ type: "setPlayerBehavior", value })
            }
            onMonsterBehaviorChange={(value) =>
              dispatch({ type: "setMonsterBehavior", value })
            }
            onEditLayout={() => dispatch({ type: "editLayout" })}
            onToggleAutoplay={() => dispatch({ type: "toggleAutoplay" })}
            onRunBatch={() => {
              void handleRunBatch();
            }}
            onReplayIndexChange={(value) =>
              dispatch({
                type: "setReplayIndex",
                value,
              })
            }
          />

        </aside>

        <section className="sim-center-stage">
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
            rosterUnits={rosterUnits}
            timelineEvents={timelineEvents}
            highlightedPath={highlightedPath}
            currentFrame={currentFrame}
            initialFrame={initialFrame}
            currentRound={currentState?.round ?? 1}
            attackLine={attackLine}
            showBattleReplayControls={battleViewActive}
            frameIndex={state.replayIndex}
            frameCount={state.encounter?.replayFrames.length ?? 0}
            autoPlayActive={state.isAutoplaying}
            frameTransitionProgress={frameTransitionProgress}
            replayFrameDurationMs={replayDelayMs}
            onToggleAutoPlay={() => dispatch({ type: "toggleAutoplay" })}
            onPreviousFrame={() =>
              dispatch({
                type: "setReplayIndex",
                value: state.replayIndex - 1,
              })
            }
            onNextFrame={() =>
              dispatch({
                type: "setReplayIndex",
                value: state.replayIndex + 1,
              })
            }
            onFrameChange={(value) =>
              dispatch({
                type: "setReplayIndex",
                value,
              })
            }
            onResetLayout={() => dispatch({ type: "resetLayout" })}
            onSelectPlacementUnit={(unitId) =>
              dispatch({ type: "selectPlacementUnit", unitId })
            }
            onPlacementCellClick={handlePlacementCellClick}
          />

        </section>

        <aside className="sim-sidebar sim-sidebar-right">
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

          <CurrentFramePanel currentFrame={currentFrame} />
          <TimelinePanel timelineEvents={timelineEvents} />
        </aside>
      </section>
    </main>
  );
}
