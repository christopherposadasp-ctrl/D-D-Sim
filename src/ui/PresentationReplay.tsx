import { startTransition, useEffect, useState } from 'react';

import { inspectPlacementsForUnitIds } from '../shared/sim/spatial';
import type {
  CombatEvent,
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
  getTerrainFeaturesForPreset
} from './catalog';
import {
  PRESENTATION_REPLAY_CONFIG,
  PRESENTATION_SAVED_REPLAY_URL,
  PRESENTATION_SCENARIO_DESCRIPTION,
  PRESENTATION_SCENARIO_DISPLAY_NAME,
  PRESENTATION_TERRAIN_FEATURES,
  PRESENTATION_UNIT_DISPLAY_NAMES
} from './presentationConfig';

const AUTOPLAY_INTERVAL_MS = 900;

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

function getAttackLine(frame: ReplayFrame | null, currentState: ReplayFrame['state'] | null): AttackLine | null {
  const attackEvent = [...(frame?.events ?? [])].reverse().find((event) => event.eventType === 'attack') ?? null;
  const targetId = attackEvent?.targetIds[0] ?? null;

  if (!attackEvent || !targetId || !currentState) {
    return null;
  }

  const actor = currentState.units[attackEvent.actorId];
  const target = currentState.units[targetId];

  if (!actor?.position || !target?.position) {
    return null;
  }

  return {
    actorId: attackEvent.actorId,
    targetId,
    from: actor.position,
    to: target.position,
    fromFootprint: actor.footprint ?? MEDIUM_FOOTPRINT,
    toFootprint: target.footprint ?? MEDIUM_FOOTPRINT
  };
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

type SavedPresentationReplayPayload = RunEncounterResult | { result: RunEncounterResult };

function getSavedReplayFromPayload(payload: SavedPresentationReplayPayload): RunEncounterResult {
  if ('result' in payload) {
    return payload.result;
  }

  return payload;
}

async function loadSavedPresentationReplay(): Promise<RunEncounterResult | null> {
  if (!PRESENTATION_SAVED_REPLAY_URL) {
    return null;
  }

  const response = await fetch(PRESENTATION_SAVED_REPLAY_URL);

  if (!response.ok) {
    throw new Error(`Saved replay request failed with status ${response.status}.`);
  }

  return getSavedReplayFromPayload((await response.json()) as SavedPresentationReplayPayload);
}

export function PresentationReplay() {
  const [enemyCatalog, setEnemyCatalog] = useState<EnemyCatalogResponse | null>(null);
  const [playerCatalog, setPlayerCatalog] = useState<PlayerCatalogResponse | null>(null);
  const [encounter, setEncounter] = useState<RunEncounterResult | null>(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [isAutoplaying, setIsAutoplaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadPresentationReplay(): Promise<void> {
      try {
        const [loadedEnemyCatalog, loadedPlayerCatalog] = await Promise.all([
          getEnemyCatalogRequest(),
          getPlayerCatalogRequest()
        ]);
        const replay =
          (await loadSavedPresentationReplay()) ??
          (await runEncounterRequest(buildPresentationConfig(loadedEnemyCatalog, loadedPlayerCatalog)));

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

    const timer = window.setInterval(() => {
      setReplayIndex((currentIndex) => {
        if (currentIndex >= encounter.replayFrames.length - 1) {
          window.clearInterval(timer);
          setIsAutoplaying(false);
          return currentIndex;
        }

        return getNextPresentationFrameIndex(encounter, currentIndex, 1);
      });
    }, AUTOPLAY_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [encounter, isAutoplaying]);

  const currentFrame = encounter?.replayFrames[replayIndex] ?? null;
  const displayCurrentFrame = formatPresentationFrame(currentFrame);
  const initialFrame = encounter?.replayFrames[0] ?? null;
  const currentState = currentFrame?.state ?? initialFrame?.state ?? null;
  const orderedUnits = currentState ? sortUnits(currentState.units) : [];
  const displayOrderedUnits = orderedUnits.map(formatPresentationUnit);
  const visibleEventCount = getVisibleEventCount(encounter, replayIndex, currentFrame);
  const timelineEvents = encounter?.events.slice(0, visibleEventCount).map(formatPresentationEvent) ?? [];
  const movementEvents = currentFrame?.events.filter((event) => event.eventType === 'move') ?? [];
  const highlightedPath = combineMovementPaths(
    movementEvents
      .map((event) => event.movementDetails?.path ?? [])
      .filter((path) => path.length > 1)
  );
  const attackLine = getAttackLine(currentFrame, currentState);
  const catalogTerrainFeatures = getTerrainFeaturesForPreset(enemyCatalog, PRESENTATION_REPLAY_CONFIG.enemyPresetId);
  const terrainFeatures = catalogTerrainFeatures.length > 0 ? catalogTerrainFeatures : PRESENTATION_TERRAIN_FEATURES;
  const catalogActiveUnitIds = getCombinedUnitIds(
    enemyCatalog,
    PRESENTATION_REPLAY_CONFIG.enemyPresetId,
    playerCatalog,
    PRESENTATION_REPLAY_CONFIG.playerPresetId
  );
  const activeUnitIds = catalogActiveUnitIds.length > 0 ? catalogActiveUnitIds : initialFrame?.state.initiativeOrder ?? [];
  const placements =
    enemyCatalog && playerCatalog
      ? getDefaultPlacementsForPreset(
          enemyCatalog,
          PRESENTATION_REPLAY_CONFIG.enemyPresetId,
          playerCatalog,
          PRESENTATION_REPLAY_CONFIG.playerPresetId
        )
      : {};
  const placementFootprints =
    enemyCatalog && playerCatalog
      ? getPlacementFootprintsForPreset(
          enemyCatalog,
          PRESENTATION_REPLAY_CONFIG.enemyPresetId,
          playerCatalog,
          PRESENTATION_REPLAY_CONFIG.playerPresetId
        )
      : {};
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
          highlightedPath={highlightedPath}
          currentFrame={currentFrame}
          initialFrame={initialFrame}
          currentRound={currentState?.round ?? 1}
          attackLine={attackLine}
          onResetLayout={() => undefined}
          onSelectPlacementUnit={() => undefined}
          onPlacementCellClick={() => undefined}
        />

        <CurrentFramePanel currentFrame={displayCurrentFrame} />
      </section>

      <section className="grid-layout">
        <UnitStatePanel orderedUnits={displayOrderedUnits} />
        <TimelinePanel timelineEvents={timelineEvents} />
      </section>
    </main>
  );
}
