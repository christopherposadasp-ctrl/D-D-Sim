import { startTransition, useEffect, useState } from 'react';

import { inspectPlacementsForUnitIds } from '../shared/sim/spatial';
import type {
  CombatEvent,
  EncounterState,
  EnemyCatalogResponse,
  EncounterConfig,
  GridPosition,
  PlayerCatalogResponse,
  ReplayFrame,
  RunEncounterResult,
  UnitState
} from '../shared/sim/types';
import {
  CurrentFramePanel,
  TimelinePanel,
  UnitStatePanel,
  VisualizationPanel,
  type AttackLine,
  type BoardUnit
} from './components';
import { getEnemyCatalogRequest, getPlayerCatalogRequest, runEncounterRequest } from './api';
import {
  MEDIUM_FOOTPRINT,
  getCombinedUnitIds,
  getDefaultPlacementsForPreset,
  getEnemyPreset,
  getPlacementFootprintsForPreset,
  getPlayerPreset,
  getTerrainFeaturesForPreset,
  getUnitDisplayName
} from './catalog';
import {
  PRESENTATION_REPLAY_CONFIG,
  PRESENTATION_SAVED_REPLAY_URL,
  PRESENTATION_SCENARIO_DESCRIPTION,
  PRESENTATION_SCENARIO_DISPLAY_NAME,
  PRESENTATION_UNIT_DISPLAY_NAMES
} from './presentationConfig';
import { loadSavedPresentationReplay } from './presentationReplayData';
import {
  getActiveReplayMovementEvents,
  getReplayAttackLine,
  getReplayStepDelayMs
} from './replay';

function sortUnits(units: Record<string, UnitState>): UnitState[] {
  return Object.values(units).sort((left, right) =>
    left.id.localeCompare(right.id, undefined, { numeric: true })
  );
}

function mergeRosterUnits(
  initialFrame: ReplayFrame | null,
  currentState: EncounterState | null
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

function getWinnerLabel(result: RunEncounterResult | null): string {
  const winner = result?.finalState.winner;

  if (winner === 'fighters') {
    return 'Party Victory';
  }

  if (winner === 'goblins') {
    return 'Enemy Victory';
  }

  if (winner === 'mutual_annihilation') {
    return 'Mutual Annihilation';
  }

  return result ? 'Replay Complete' : 'Loading';
}

function getFrameNarration(frame: ReplayFrame | null): string {
  if (!frame || frame.events.length === 0) {
    return 'Replay is ready for the next frame.';
  }

  return frame.events.map((event) => formatPresentationText(event.textSummary)).join(' ');
}

function getVisibleEventCount(encounter: RunEncounterResult | null, replayIndex: number, currentFrame: ReplayFrame | null): number {
  const serializedCombatLogLength = currentFrame?.state.combatLog.length ?? 0;

  if (serializedCombatLogLength > 0 || !encounter) {
    return serializedCombatLogLength;
  }

  return encounter.replayFrames
    .slice(0, replayIndex + 1)
    .reduce((eventCount, frame) => eventCount + frame.events.length, 0);
}

function formatUnitDisplayName(unitId: string): string {
  return PRESENTATION_UNIT_DISPLAY_NAMES[unitId] ?? unitId;
}

function formatPresentationText(text: string): string {
  return Object.entries(PRESENTATION_UNIT_DISPLAY_NAMES)
    .sort(([leftId], [rightId]) => rightId.length - leftId.length)
    .reduce(
      (formattedText, [unitId, displayName]) =>
        formattedText.replace(new RegExp(`\\b${unitId}\\b`, 'g'), displayName),
      text
    );
}

function formatPresentationEvent(event: CombatEvent): CombatEvent {
  return {
    ...event,
    actorId: formatUnitDisplayName(event.actorId),
    targetIds: event.targetIds.map(formatUnitDisplayName),
    textSummary: formatPresentationText(event.textSummary),
    conditionDeltas: event.conditionDeltas.map(formatPresentationText)
  };
}

function isDeadUnitSkipFrame(frame: ReplayFrame): boolean {
  return (
    frame.events.length > 0 &&
    frame.events.every(
      (event) =>
        event.eventType === 'turn_start' ||
        (event.eventType === 'skip' && event.textSummary.includes('Dead units do not act.'))
    ) &&
    frame.events.some((event) => event.eventType === 'skip' && event.textSummary.includes('Dead units do not act.'))
  );
}

function getNextPresentationFrameIndex(
  encounter: RunEncounterResult,
  currentIndex: number,
  direction: 1 | -1
): number {
  let nextIndex = currentIndex + direction;

  while (
    nextIndex > 0 &&
    nextIndex < encounter.replayFrames.length - 1 &&
    isDeadUnitSkipFrame(encounter.replayFrames[nextIndex])
  ) {
    nextIndex += direction;
  }

  return Math.min(Math.max(nextIndex, 0), encounter.replayFrames.length - 1);
}

function getPresentationAutoplayStepCount(encounter: RunEncounterResult): number {
  let stepCount = 0;
  let currentIndex = 0;

  while (currentIndex < encounter.replayFrames.length - 1) {
    const nextIndex = getNextPresentationFrameIndex(encounter, currentIndex, 1);

    if (nextIndex === currentIndex) {
      break;
    }

    currentIndex = nextIndex;
    stepCount += 1;
  }

  return stepCount;
}

function formatPresentationFrame(frame: ReplayFrame | null): ReplayFrame | null {
  if (!frame) {
    return null;
  }

  return {
    ...frame,
    activeCombatantId: formatUnitDisplayName(frame.activeCombatantId),
    events: frame.events.map(formatPresentationEvent)
  };
}

function formatPresentationUnit(unit: UnitState): UnitState {
  const displayName = PRESENTATION_UNIT_DISPLAY_NAMES[unit.id];

  if (!displayName) {
    return unit;
  }

  return {
    ...unit,
    templateName: displayName
  };
}

function getReplayUnitIds(
  initialFrame: ReplayFrame | null,
  currentState: EncounterState | null
): string[] {
  const replayOrder = initialFrame?.state.initiativeOrder ?? currentState?.initiativeOrder ?? [];

  if (replayOrder.length > 0) {
    return replayOrder;
  }

  return currentState ? sortUnits(currentState.units).map((unit) => unit.id) : [];
}

function getReplayPlacements(initialFrame: ReplayFrame | null): Record<string, GridPosition> {
  if (!initialFrame) {
    return {};
  }

  const placements: Record<string, GridPosition> = {};

  for (const unit of sortUnits(initialFrame.state.units)) {
    if (unit.position) {
      placements[unit.id] = { ...unit.position };
    }
  }

  return placements;
}

function getReplayFootprints(initialFrame: ReplayFrame | null): Record<string, typeof MEDIUM_FOOTPRINT> {
  if (!initialFrame) {
    return {};
  }

  return Object.fromEntries(
    sortUnits(initialFrame.state.units).map((unit) => [
      unit.id,
      unit.footprint ?? MEDIUM_FOOTPRINT
    ])
  );
}

function buildPresentationConfig(
  enemyCatalog: EnemyCatalogResponse,
  playerCatalog: PlayerCatalogResponse
): EncounterConfig {
  return {
    ...PRESENTATION_REPLAY_CONFIG,
    placements: getDefaultPlacementsForPreset(
      enemyCatalog,
      PRESENTATION_REPLAY_CONFIG.enemyPresetId,
      playerCatalog,
      PRESENTATION_REPLAY_CONFIG.playerPresetId
    )
  };
}

export function PresentationReplay() {
  const [enemyCatalog, setEnemyCatalog] = useState<EnemyCatalogResponse | null>(null);
  const [playerCatalog, setPlayerCatalog] = useState<PlayerCatalogResponse | null>(null);
  const [encounter, setEncounter] = useState<RunEncounterResult | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [isAutoplaying, setIsAutoplaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.body.classList.add('presentation-page');

    return () => {
      document.body.classList.remove('presentation-page');
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPresentationReplay(): Promise<void> {
      try {
        const savedReplay = await loadSavedPresentationReplay();

        if (savedReplay) {
          if (cancelled) {
            return;
          }

          startTransition(() => {
            setEnemyCatalog(null);
            setPlayerCatalog(null);
            setEncounter(savedReplay);
            setReplayIndex(0);
            setError(null);
          });
          return;
        }

        const [loadedEnemyCatalog, loadedPlayerCatalog] = await Promise.all([
          getEnemyCatalogRequest(),
          getPlayerCatalogRequest()
        ]);
        const replay = await runEncounterRequest(buildPresentationConfig(loadedEnemyCatalog, loadedPlayerCatalog));

        if (cancelled) {
          return;
        }

        startTransition(() => {
          setEnemyCatalog(loadedEnemyCatalog);
          setPlayerCatalog(loadedPlayerCatalog);
          setEncounter(replay);
          setReplayIndex(0);
          setError(null);
        });
      } catch (loadError) {
        if (cancelled) {
          return;
        }

        startTransition(() => {
          setError(loadError instanceof Error ? loadError.message : 'Unable to load the presentation replay.');
        });
      }
    }

    void loadPresentationReplay();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isAutoplaying || !encounter) {
      return undefined;
    }

    const replayDelayMs = getReplayStepDelayMs(getPresentationAutoplayStepCount(encounter));
    const timer = window.setInterval(() => {
      setReplayIndex((currentIndex) => {
        if (currentIndex >= encounter.replayFrames.length - 1) {
          window.clearInterval(timer);
          setIsAutoplaying(false);
          return currentIndex;
        }

        return getNextPresentationFrameIndex(encounter, currentIndex, 1);
      });
    }, replayDelayMs);

    return () => window.clearInterval(timer);
  }, [encounter, isAutoplaying]);

  const currentFrame = encounter?.replayFrames[replayIndex] ?? null;
  const displayCurrentFrame = formatPresentationFrame(currentFrame);
  const initialFrame = encounter?.replayFrames[0] ?? null;
  const previousFrame = encounter?.replayFrames[Math.max(0, replayIndex - 1)] ?? null;
  const currentState = currentFrame?.state ?? initialFrame?.state ?? null;
  const replayFrameDurationMs = encounter
    ? getReplayStepDelayMs(getPresentationAutoplayStepCount(encounter))
    : undefined;
  const orderedUnits = currentState ? sortUnits(currentState.units) : [];
  const rosterUnits = mergeRosterUnits(initialFrame, currentState);
  const displayOrderedUnits = orderedUnits.map(formatPresentationUnit);
  const visibleEventCount = getVisibleEventCount(encounter, replayIndex, currentFrame);
  const rawTimelineEvents = encounter?.events.slice(0, visibleEventCount) ?? [];
  const timelineEvents = rawTimelineEvents.map(formatPresentationEvent);
  const movementEvents = getActiveReplayMovementEvents(currentFrame);
  const highlightedPath = combineMovementPaths(
    movementEvents
      .map((event) => event.movementDetails?.path ?? [])
      .filter((path) => path.length > 1)
  );
  const attackLine: AttackLine | null = getReplayAttackLine(
    currentFrame,
    currentState,
    previousFrame?.state ?? null
  );
  const terrainFeatures = getTerrainFeaturesForPreset(PRESENTATION_REPLAY_CONFIG.enemyPresetId);
  const catalogAvailable = Boolean(enemyCatalog && playerCatalog);
  const catalogActiveUnitIds = catalogAvailable
    ? getCombinedUnitIds(
        enemyCatalog,
        PRESENTATION_REPLAY_CONFIG.enemyPresetId,
        playerCatalog,
        PRESENTATION_REPLAY_CONFIG.playerPresetId
      )
    : [];
  const activeUnitIds = catalogActiveUnitIds.length > 0 ? catalogActiveUnitIds : getReplayUnitIds(initialFrame, currentState);
  const placements =
    catalogAvailable
      ? getDefaultPlacementsForPreset(
          enemyCatalog,
          PRESENTATION_REPLAY_CONFIG.enemyPresetId,
          playerCatalog,
          PRESENTATION_REPLAY_CONFIG.playerPresetId
        )
      : getReplayPlacements(initialFrame);
  const placementFootprints =
    catalogAvailable
      ? getPlacementFootprintsForPreset(
          enemyCatalog,
          PRESENTATION_REPLAY_CONFIG.enemyPresetId,
          playerCatalog,
          PRESENTATION_REPLAY_CONFIG.playerPresetId
        )
      : getReplayFootprints(initialFrame);
  const placementValidation = inspectPlacementsForUnitIds(
    placements,
    activeUnitIds,
    placementFootprints,
    terrainFeatures
  );
  const setupUnits: BoardUnit[] = activeUnitIds.map((unitId) => ({
    id: unitId,
    faction: unitId.startsWith('F') ? 'fighters' : 'goblins',
    position: placements[unitId] ?? initialFrame?.state.units[unitId]?.position ?? undefined,
    templateName:
      PRESENTATION_UNIT_DISPLAY_NAMES[unitId] ??
      getUnitDisplayName(
        enemyCatalog,
        playerCatalog,
        PRESENTATION_REPLAY_CONFIG.enemyPresetId,
        PRESENTATION_REPLAY_CONFIG.playerPresetId,
        unitId
      ),
    footprint: placementFootprints[unitId] ?? MEDIUM_FOOTPRINT
  }));
  const scenario = getEnemyPreset(enemyCatalog, PRESENTATION_REPLAY_CONFIG.enemyPresetId);
  const party = getPlayerPreset(playerCatalog, PRESENTATION_REPLAY_CONFIG.playerPresetId);
  const scenarioDisplayName = scenario?.displayName ?? PRESENTATION_SCENARIO_DISPLAY_NAME;
  const scenarioDescription = scenario?.description ?? PRESENTATION_SCENARIO_DESCRIPTION;
  const replaySource = PRESENTATION_SAVED_REPLAY_URL ? 'Saved replay' : 'Local backend fixed seed';

  function goToAdjacentPresentationFrame(direction: 1 | -1): void {
    if (!encounter) {
      return;
    }

    setReplayIndex((currentIndex) => getNextPresentationFrameIndex(encounter, currentIndex, direction));
  }

  return (
    <main className="app-shell presentation-shell">
      <section className="hero presentation-hero">
        <div className="hero-copy">
          <span className="eyebrow">Presentation Replay</span>
          <h1>{scenarioDisplayName}</h1>
          <p>
            A prepared smart-party replay against a Balanced DM. This page is built for the final demo: fixed seed,
            fixed party, fixed scenario, and frame-by-frame narration.
          </p>
        </div>
        <div className="hero-callout">
          <span>Outcome</span>
          <strong>{getWinnerLabel(encounter)}</strong>
          <small>{replaySource}</small>
        </div>
      </section>

      <section className="panel presentation-control-panel">
        <div className="panel-header">
          <h2>Replay Controls</h2>
          <p>
            {party?.displayName ?? PRESENTATION_REPLAY_CONFIG.playerPresetId} vs{' '}
            {scenarioDisplayName}
          </p>
          <p>{scenarioDescription}</p>
        </div>

        <div className="status-stage">
          <div className="stage-chip">
            <span>Seed</span>
            <strong>{PRESENTATION_REPLAY_CONFIG.seed}</strong>
          </div>
          <div className="stage-chip">
            <span>PCs</span>
            <strong>Smart</strong>
          </div>
          <div className="stage-chip">
            <span>DM</span>
            <strong>Balanced</strong>
          </div>
          <div className="stage-chip">
            <span>Frame</span>
            <strong>
              {encounter ? `${replayIndex + 1} / ${encounter.replayFrames.length}` : '-'}
            </strong>
          </div>
        </div>

        <div className="presentation-frame-note">
          <strong>Current Beat</strong>
          <span>{getFrameNarration(currentFrame)}</span>
        </div>

        <div className="button-row">
          <button
            type="button"
            className="secondary-button"
            onClick={() => goToAdjacentPresentationFrame(-1)}
            disabled={!encounter || replayIndex === 0}
          >
            Previous Frame
          </button>
          <button type="button" className="primary-button" onClick={() => setIsAutoplaying((value) => !value)} disabled={!encounter}>
            {isAutoplaying ? 'Pause Replay' : 'Play Replay'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => goToAdjacentPresentationFrame(1)}
            disabled={!encounter || replayIndex >= encounter.replayFrames.length - 1}
          >
            Next Frame
          </button>
          <a className="secondary-button link-button" href="/">
            Open Simulator
          </a>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        {!encounter && !error ? <div className="panel-copy">Loading fixed presentation replay...</div> : null}
      </section>

      <section className="presentation-grid">
        <VisualizationPanel
          enemyCatalog={enemyCatalog}
          playerCatalog={playerCatalog}
          isSetupMode={false}
          spatialReplayActive={Boolean(currentState)}
          enemyPresetIdInput={PRESENTATION_REPLAY_CONFIG.enemyPresetId}
          playerPresetIdInput={PRESENTATION_REPLAY_CONFIG.playerPresetId}
          activeUnitIds={activeUnitIds}
          placementValidation={placementValidation}
          placements={placements}
          selectedPlacementUnitId={null}
          terrainFeatures={terrainFeatures}
          setupUnits={setupUnits}
          orderedUnits={orderedUnits}
          rosterUnits={rosterUnits}
          timelineEvents={rawTimelineEvents}
          highlightedPath={highlightedPath}
          currentFrame={currentFrame}
          initialFrame={initialFrame}
          currentRound={currentState?.round ?? 1}
          attackLine={attackLine}
          replayTextFormatter={formatPresentationText}
          replayFrameDurationMs={replayFrameDurationMs}
          onResetLayout={() => undefined}
          onSelectPlacementUnit={() => undefined}
          onPlacementCellClick={() => undefined}
        />

        <CurrentFramePanel currentFrame={displayCurrentFrame} />
      </section>

      <section className="grid-layout">
        <UnitStatePanel
          orderedUnits={displayOrderedUnits}
          activeUnitId={currentFrame?.activeCombatantId ?? null}
        />
        <TimelinePanel timelineEvents={timelineEvents} />
      </section>
    </main>
  );
}
