import { startTransition, useDeferredValue, useEffect, useReducer } from 'react';

import { UNIT_IDS } from '../engine/constants';
import { inspectPlacements } from '../engine/spatial';
import type { GridPosition, UnitState } from '../engine/types';
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
import { createInitialUiState, uiReducer } from './store';

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

export function App() {
  const [state, dispatch] = useReducer(uiReducer, createInitialUiState());
  const deferredReplayIndex = useDeferredValue(state.replayIndex);
  const currentFrame = state.encounter?.replayFrames[deferredReplayIndex] ?? null;
  const initialFrame = state.encounter?.replayFrames[0] ?? null;
  const currentState = currentFrame?.state ?? initialFrame?.state ?? null;
  const orderedUnits: UnitState[] = currentState ? sortUnits(currentState.units) : [];
  const placementValidation = inspectPlacements(state.placements);
  const setupUnits: BoardUnit[] = UNIT_IDS.map((unitId) => ({
    id: unitId,
    faction: unitId.startsWith('F') ? 'fighters' : 'goblins',
    position: state.placements[unitId]
  }));
  const visibleEventCount = currentFrame?.state.combatLog.length ?? 0;
  const timelineEvents = state.encounter?.events.slice(0, visibleEventCount) ?? [];
  const isSetupMode = !state.encounter;
  const canRunSimulation = placementValidation.isValid;
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
          to: currentState.units[attackTargetId].position!
        }
      : null;
  const placementStatusText = placementValidation.isValid
    ? 'All 10 units are placed. Combat is ready.'
    : placementValidation.outOfBoundsUnitIds.length > 0 || placementValidation.overlappingGroups.length > 0
      ? placementValidation.errors[0]
      : `Place the remaining units: ${placementValidation.missingUnitIds.join(', ')}.`;

  function handlePlacementCellClick(position: GridPosition, occupantId: string | null): void {
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

  return (
    <main className="app-shell">
      <HeroSection />

      <ControlsPanel
        seedInput={state.seedInput}
        batchSizeInput={state.batchSizeInput}
        playerBehaviorInput={state.playerBehaviorInput}
        monsterBehaviorInput={state.monsterBehaviorInput}
        hasEncounter={Boolean(state.encounter)}
        isAutoplaying={state.isAutoplaying}
        replayIndex={state.replayIndex}
        replayFrameCount={state.encounter?.replayFrames.length ?? 0}
        canRunSimulation={canRunSimulation}
        placementValidation={placementValidation}
        placementStatusText={placementStatusText}
        error={state.error}
        onSeedChange={(value) => dispatch({ type: 'setSeed', value })}
        onBatchSizeChange={(value) => dispatch({ type: 'setBatchSize', value })}
        onPlayerBehaviorChange={(value) => dispatch({ type: 'setPlayerBehavior', value })}
        onMonsterBehaviorChange={(value) => dispatch({ type: 'setMonsterBehavior', value })}
        onEditLayout={() => dispatch({ type: 'editLayout' })}
        onToggleAutoplay={() => dispatch({ type: 'toggleAutoplay' })}
        onRunBatch={() => {
          startTransition(() => {
            dispatch({ type: 'runBatch' });
          });
        }}
        onReplayIndexChange={(value) =>
          dispatch({
            type: 'setReplayIndex',
            value
          })
        }
      />

      <EncounterSummaryPanel
        seedInput={state.seedInput}
        playerBehaviorInput={state.playerBehaviorInput}
        monsterBehaviorInput={state.monsterBehaviorInput}
        encounterSummary={state.encounterSummary}
        batchSummary={state.batchSummary}
      />

      <section className="grid-layout">
        <VisualizationPanel
          isSetupMode={isSetupMode}
          spatialReplayActive={spatialReplayActive}
          placementValidation={placementValidation}
          placements={state.placements}
          selectedPlacementUnitId={state.selectedPlacementUnitId}
          setupUnits={setupUnits}
          orderedUnits={orderedUnits}
          highlightedPath={highlightedPath}
          currentFrame={currentFrame}
          initialFrame={initialFrame}
          currentRound={currentState?.round ?? 1}
          rescueSubphase={currentState?.rescueSubphase ?? false}
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
