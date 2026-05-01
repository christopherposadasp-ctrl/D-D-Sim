import {
  getOccupiedSquaresForPosition,
  GRID_SIZE,
  SINGLE_SQUARE_FOOTPRINT,
  terrainBlocksPlacement
} from '../shared/sim/spatial';
import type { PlacementValidationResult } from '../shared/sim/spatial';
import type {
  BatchJobStatus,
  BatchCombinationSummary,
  BatchSummary,
  CombatEvent,
  EncounterSummary,
  EnemyCatalogResponse,
  EnemyPresetCatalogEntry,
  Footprint,
  GridPosition,
  MonsterBehaviorSelection,
  PlayerBehavior,
  PlayerCatalogResponse,
  PlayerPresetCatalogEntry,
  ReplayFrame,
  TerrainFeature,
  UnitState
} from '../shared/sim/types';
import {
  DEFAULT_PARTY_MAX_HP,
  MAX_BATCH_SIZE,
  getEnemyPreset,
  getPlayerPreset,
  getTotalEnemyMaxHpForPreset,
  getTotalPlayerMaxHpForPreset,
  getUnitDisplayName
} from './catalog';

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function formatElapsedTime(value: number): string {
  const totalSeconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function getTerrainToken(feature: TerrainFeature): string {
  if (feature.kind === 'low_wall') {
    return 'W';
  }
  if (feature.kind === 'boulder') {
    return 'B';
  }
  if (feature.kind === 'column') {
    return 'C';
  }
  return 'R';
}

function getTerrainLabel(feature: TerrainFeature): string {
  if (feature.kind === 'low_wall') {
    return 'low wall';
  }
  if (feature.kind === 'boulder') {
    return 'boulder';
  }
  if (feature.kind === 'column') {
    return 'column';
  }
  return 'rock';
}

function formatFieldValue(value: CombatEvent['rawRolls'][string]): string {
  if (Array.isArray(value)) {
    return value.join(', ');
  }

  if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  }

  if (value === null) {
    return '-';
  }

  return String(value);
}

function getUnitStatus(unit: UnitState): string {
  if (unit.conditions.dead) {
    return 'Dead';
  }

  if (unit.currentHp === 0 && unit.stable) {
    return 'Stable';
  }

  if (unit.currentHp === 0) {
    return 'Dying';
  }

  return 'Active';
}

function formatOutOf(value: number, maximum: number): string {
  return `${formatNumber(value)} / ${maximum}`;
}

function formatPosition(position: GridPosition): string {
  return `(${position.x},${position.y})`;
}

function formatPath(path: GridPosition[]): string {
  return path.map(formatPosition).join(' -> ');
}

function formatUnitList(unitIds: string[]): string {
  return unitIds.join(', ');
}

function formatPlayerBehavior(value: PlayerBehavior | EncounterSummary['playerBehavior']): string {
  if (value === 'balanced') {
    return 'Balanced';
  }

  return value === 'smart' ? 'Smart' : 'Dumb';
}

function formatMonsterBehavior(
  value: MonsterBehaviorSelection | EncounterSummary['monsterBehavior'] | BatchCombinationSummary['monsterBehavior']
): string {
  if (value === 'combined') {
    return 'Combined';
  }

  if (value === 'kind') {
    return 'Kind';
  }

  return value === 'balanced' ? 'Balanced' : 'Evil';
}

function formatWinner(value: EncounterSummary['winner'] | null | undefined): string {
  if (!value) {
    return '-';
  }

  if (value === 'fighters') {
    return 'Party';
  }

  if (value === 'goblins') {
    return 'Enemies';
  }

  if (value === 'mutual_annihilation') {
    return 'Mutual Annihilation';
  }

  return value;
}

export interface AttackLine {
  actorId: string;
  targetId: string;
  from: GridPosition;
  to: GridPosition;
  fromFootprint: Footprint;
  toFootprint: Footprint;
}

export type BoardUnit = Pick<UnitState, 'id' | 'faction' | 'position' | 'footprint'>;

function getUnitLabel(
  enemyCatalog: EnemyCatalogResponse | null,
  playerCatalog: PlayerCatalogResponse | null,
  enemyPresetId: string,
  playerPresetId: string,
  unitId: string
): string {
  return getUnitDisplayName(enemyCatalog, playerCatalog, enemyPresetId, playerPresetId, unitId);
}

function getEnemyPresetLabel(catalog: EnemyCatalogResponse | null, enemyPresetId: string): string {
  return getEnemyPreset(catalog, enemyPresetId)?.displayName ?? enemyPresetId ?? '-';
}

function getPlayerPresetLabel(catalog: PlayerCatalogResponse | null, playerPresetId: string): string {
  return getPlayerPreset(catalog, playerPresetId)?.displayName ?? playerPresetId ?? '-';
}

function getBoardPoint(position: GridPosition, footprint: Footprint = SINGLE_SQUARE_FOOTPRINT): { x: number; y: number } {
  return {
    x: position.x - 0.5 + (footprint.width - 1) / 2,
    y: GRID_SIZE - position.y + 0.5 - (footprint.height - 1) / 2
  };
}

function getPlacementStatusText(validation: PlacementValidationResult, activeUnitCount: number): string {
  if (validation.isValid) {
    return `All ${activeUnitCount} units are placed. Combat is ready.`;
  }

  if (
    validation.outOfBoundsUnitIds.length > 0 ||
    validation.overlappingGroups.length > 0 ||
    validation.blockedSquareGroups.length > 0
  ) {
    return validation.errors[0] ?? 'The simulator requires a complete, valid placement layout.';
  }

  return `Place the remaining units: ${formatUnitList(validation.missingUnitIds)}.`;
}

function getSelectedPlacementSummary(
  selectedPlacementUnitId: string | null,
  placements: Record<string, GridPosition>,
  enemyPresetId: string,
  playerPresetId: string,
  enemyCatalog: EnemyCatalogResponse | null,
  playerCatalog: PlayerCatalogResponse | null
): string {
  if (!selectedPlacementUnitId) {
    return 'No unit selected';
  }

  const position = placements[selectedPlacementUnitId];
  return `${selectedPlacementUnitId} ${getUnitLabel(enemyCatalog, playerCatalog, enemyPresetId, playerPresetId, selectedPlacementUnitId)}${
    position ? ` at ${formatPosition(position)}` : ' is unplaced'
  }`;
}

function MetricCard(props: { label: string; value: string; tone?: 'fighters' | 'goblins' | 'neutral' }) {
  return (
    <div className={`metric-card ${props.tone ?? 'neutral'}`}>
      <span className="metric-label">{props.label}</span>
      <strong className="metric-value">{props.value}</strong>
    </div>
  );
}

function GridBoard(props: {
  units: BoardUnit[];
  terrainFeatures: TerrainFeature[];
  highlightedPath: GridPosition[];
  activeUnitId: string | null;
  attackLine: AttackLine | null;
  selectedPlacementUnitId?: string | null;
  onCellClick?: (position: GridPosition, occupantId: string | null) => void;
  ariaLabel: string;
}) {
  const placementMode = Boolean(props.onCellClick);
  const occupiedSquares = new Map<string, { unit: BoardUnit; isAnchor: boolean }>();
  const terrainSquares = new Map<string, { feature: TerrainFeature; isAnchor: boolean }>();

  for (const unit of props.units) {
    if (!unit.position) {
      continue;
    }

    for (const occupiedSquare of getOccupiedSquaresForPosition(unit.position, unit.footprint ?? SINGLE_SQUARE_FOOTPRINT)) {
      occupiedSquares.set(`${occupiedSquare.x},${occupiedSquare.y}`, {
        unit,
        isAnchor: occupiedSquare.x === unit.position.x && occupiedSquare.y === unit.position.y
      });
    }
  }

  for (const feature of props.terrainFeatures) {
    for (const occupiedSquare of getOccupiedSquaresForPosition(feature.position, feature.footprint)) {
      terrainSquares.set(`${occupiedSquare.x},${occupiedSquare.y}`, {
        feature,
        isAnchor: occupiedSquare.x === feature.position.x && occupiedSquare.y === feature.position.y
      });
    }
  }
  const pathIndex = new Map(
    props.highlightedPath.map((position, index) => [`${position.x},${position.y}`, index])
  );
  const cells: Array<{ x: number; y: number }> = [];

  for (let y = GRID_SIZE; y >= 1; y -= 1) {
    for (let x = 1; x <= GRID_SIZE; x += 1) {
      cells.push({ x, y });
    }
  }

  const movementPoints =
    props.highlightedPath.length > 1
      ? props.highlightedPath.map((position) => {
          const point = getBoardPoint(position);
          return `${point.x},${point.y}`;
        })
      : [];
  const attackFrom = props.attackLine ? getBoardPoint(props.attackLine.from, props.attackLine.fromFootprint) : null;
  const attackTo = props.attackLine ? getBoardPoint(props.attackLine.to, props.attackLine.toFootprint) : null;

  return (
    <div className="board-shell">
      <div className="board-legend">
        <span className="legend-chip fighters">Party</span>
        <span className="legend-chip goblins">Enemy</span>
        <span className="legend-chip terrain">Terrain / Cover</span>
        {placementMode ? (
          <span className="legend-chip selected">Selected Unit</span>
        ) : (
          <>
            <span className="legend-chip active">Active Unit</span>
            <span className="legend-chip path">Movement Path</span>
            <span className="legend-chip attack">Attack Line</span>
          </>
        )}
      </div>
      <div className="board-grid-shell">
        <div
          className={`board-grid ${placementMode ? 'placement-mode' : ''}`}
          role={placementMode ? 'grid' : 'img'}
          aria-label={props.ariaLabel}
        >
          {cells.map((cell) => {
            const key = `${cell.x},${cell.y}`;
            const occupiedSquare = occupiedSquares.get(key);
            const occupant = occupiedSquare?.unit;
            const isAnchorSquare = occupiedSquare?.isAnchor ?? false;
            const terrainSquare = terrainSquares.get(key);
            const terrainFeature = terrainSquare?.feature ?? null;
            const isTerrainAnchor = terrainSquare?.isAnchor ?? false;
            const isBlockingTerrain = terrainFeature ? terrainBlocksPlacement(terrainFeature) : false;
            const pathStep = pathIndex.get(key);
            const isActiveUnit = occupant?.id === props.activeUnitId;
            const isSelectedPlacementUnit = occupant?.id === props.selectedPlacementUnitId;
            const isAttackOrigin =
              props.attackLine && key === `${props.attackLine.from.x},${props.attackLine.from.y}`;
            const isAttackTarget =
              props.attackLine && key === `${props.attackLine.to.x},${props.attackLine.to.y}`;
            const cellClasses = `board-cell ${placementMode ? 'interactive' : ''} ${
              occupant ? occupant.faction : ''
            } ${terrainFeature ? `terrain ${terrainFeature.kind}` : ''} ${
              placementMode && isBlockingTerrain ? 'blocked-terrain' : ''
            } ${pathStep !== undefined ? 'path' : ''} ${isActiveUnit ? 'active-unit' : ''} ${
              isAttackOrigin ? 'attack-origin' : ''
            } ${isAttackTarget ? 'attack-target' : ''} ${isSelectedPlacementUnit ? 'selected-placement-unit' : ''}`;
            const cellContents = (
              <>
                <span className="board-coordinate">
                  {cell.x},{cell.y}
                </span>
                {pathStep !== undefined ? <span className="path-step">{pathStep + 1}</span> : null}
                {terrainFeature && isTerrainAnchor ? (
                  <span className="terrain-token">{getTerrainToken(terrainFeature)}</span>
                ) : null}
                {occupant && isAnchorSquare ? <span className="board-token">{occupant.id}</span> : null}
              </>
            );

            if (placementMode && props.onCellClick) {
              return (
                <button
                  key={key}
                  type="button"
                  className={cellClasses}
                  onClick={() => props.onCellClick?.({ x: cell.x, y: cell.y }, occupant?.id ?? null)}
                  aria-label={`Square ${cell.x},${cell.y}${
                    occupant
                      ? ` occupied by ${occupant.id}`
                      : terrainFeature
                        ? ` contains ${getTerrainLabel(terrainFeature)} terrain`
                        : ' empty'
                  }`}
                  aria-pressed={isSelectedPlacementUnit}
                  disabled={isBlockingTerrain}
                >
                  {cellContents}
                </button>
              );
            }

            return (
              <div key={key} className={cellClasses}>
                {cellContents}
              </div>
            );
          })}
        </div>

        {movementPoints.length > 1 || (attackFrom && attackTo) ? (
          <svg
            className="board-overlay"
            viewBox={`0 0 ${GRID_SIZE} ${GRID_SIZE}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {movementPoints.length > 1 ? (
              <polyline className="movement-line" points={movementPoints.join(' ')} />
            ) : null}
            {attackFrom && attackTo ? (
              <line className="attack-line" x1={attackFrom.x} y1={attackFrom.y} x2={attackTo.x} y2={attackTo.y} />
            ) : null}
          </svg>
        ) : null}
      </div>
    </div>
  );
}

function BatchMetrics(props: {
  batchSummary: BatchSummary | null;
  enemyCatalog: EnemyCatalogResponse | null;
  playerCatalog: PlayerCatalogResponse | null;
  enemyPresetIdInput: string;
  playerPresetIdInput: string;
}) {
  const { batchSummary, enemyCatalog, playerCatalog, enemyPresetIdInput, playerPresetIdInput } = props;

  if (!batchSummary) {
    return (
      <div className="panel-copy">
        Batch mode is ready. Run a seeded sample set to estimate win rates, average round counts, losses, and
        remaining HP for the selected party and scenario.
      </div>
    );
  }

  const isCombined = batchSummary.monsterBehavior === 'combined';
  const totalEnemyMaxHp = getTotalEnemyMaxHpForPreset(enemyCatalog, enemyPresetIdInput);
  const totalPlayerMaxHp = getTotalPlayerMaxHpForPreset(playerCatalog, playerPresetIdInput);

  function renderMetricGrid(summary: BatchSummary | BatchCombinationSummary, includeSeed = false) {
    return (
      <div className="metrics-grid">
        {includeSeed ? <MetricCard label="Batch Seed" value={summary.seed} /> : null}
        <MetricCard label="Player Policy" value={formatPlayerBehavior(summary.playerBehavior)} />
        <MetricCard label="DM Policy" value={formatMonsterBehavior(summary.monsterBehavior)} />
        <MetricCard label="Runs" value={String(summary.totalRuns)} />
        <MetricCard label="Party Win Rate" value={formatPercent(summary.playerWinRate)} tone="fighters" />
        <MetricCard label="Enemy Win Rate" value={formatPercent(summary.goblinWinRate)} tone="goblins" />
        <MetricCard label="Mutual Annihilation" value={formatPercent(summary.mutualAnnihilationRate)} />
        {summary.playerBehavior === 'balanced' ? (
          <>
            <MetricCard
              label="Smart Player Win Rate"
              value={summary.smartPlayerWinRate === null ? '-' : formatPercent(summary.smartPlayerWinRate)}
              tone="fighters"
            />
            <MetricCard
              label="Dumb Player Win Rate"
              value={summary.dumbPlayerWinRate === null ? '-' : formatPercent(summary.dumbPlayerWinRate)}
              tone="fighters"
            />
          </>
        ) : null}
        <MetricCard label="Average Rounds" value={formatNumber(summary.averageRounds)} />
        <MetricCard label="Average Party Deaths" value={formatNumber(summary.averageFighterDeaths)} />
        <MetricCard label="Average Enemies Killed" value={formatNumber(summary.averageGoblinsKilled)} />
        <MetricCard
          label="Average Party HP"
          value={formatOutOf(summary.averageRemainingFighterHp, totalPlayerMaxHp)}
          tone="fighters"
        />
        <MetricCard
          label="Average Enemy HP"
          value={formatOutOf(summary.averageRemainingGoblinHp, totalEnemyMaxHp)}
          tone="goblins"
        />
        <MetricCard label="Stable Unconscious Count" value={String(summary.stableButUnconsciousCount)} />
      </div>
    );
  }

  return (
    <>
      <div className="panel-copy">
        {isCombined
          ? `Batch size is interpreted per DM setting. ${batchSummary.batchSize} runs each across Kind, Balanced, and Evil for ${batchSummary.totalRuns} total runs.`
          : `${batchSummary.batchSize} runs executed for the selected player and DM policies.`}
      </div>

      {renderMetricGrid(batchSummary, true)}

      {isCombined && batchSummary.combinationSummaries ? (
        <div className="event-stack">
          {batchSummary.combinationSummaries.map((summary) => (
            <article key={summary.monsterBehavior} className="event-card">
              <header className="event-header">
                <span className="event-type">dm split</span>
                <strong>{formatMonsterBehavior(summary.monsterBehavior)} DM</strong>
              </header>
              {renderMetricGrid(summary)}
            </article>
          ))}
        </div>
      ) : null}
    </>
  );
}

export function HeroSection() {
  return (
    <section className="hero">
      <div className="hero-copy">
        <span className="eyebrow">Deterministic Combat Replay</span>
        <h1>D&amp;D 2024 Encounter Simulator</h1>
        <p>
          A seed-driven replay lab for a fixed level 5 party against backend-driven encounter scenarios. Use
          turn-by-turn replay to inspect tactical choices, then run batches to estimate encounter difficulty and
          compare behavior assumptions.
        </p>
      </div>
      <div className="hero-callout">
        <div className="callout-row">
          <span className="callout-label">Mode</span>
          <strong>Final Simulator</strong>
        </div>
        <div className="callout-row">
          <span className="callout-label">Setup</span>
          <strong>Manual Placement</strong>
        </div>
        <div className="callout-row">
          <span className="callout-label">Engine Shape</span>
          <strong>Python engine via FastAPI</strong>
        </div>
      </div>
    </section>
  );
}

interface ControlsPanelProps {
  playerPresetIdInput: string;
  playerPresets: PlayerPresetCatalogEntry[];
  seedInput: string;
  batchSizeInput: string;
  enemyPresetIdInput: string;
  enemyPresets: EnemyPresetCatalogEntry[];
  catalogLoaded: boolean;
  playerBehaviorInput: PlayerBehavior;
  monsterBehaviorInput: MonsterBehaviorSelection;
  activeUnitCount: number;
  hasEncounter: boolean;
  isAutoplaying: boolean;
  replayIndex: number;
  replayFrameCount: number;
  canRunSimulation: boolean;
  isRunning: boolean;
  batchJobStatus: BatchJobStatus | null;
  batchElapsedSeconds: number | null;
  placementValidation: PlacementValidationResult;
  placementStatusText: string;
  error: string | null;
  onSeedChange: (value: string) => void;
  onBatchSizeChange: (value: string) => void;
  onEnemyPresetChange: (value: string) => void;
  onPlayerPresetChange: (value: string) => void;
  onPlayerBehaviorChange: (value: PlayerBehavior) => void;
  onMonsterBehaviorChange: (value: MonsterBehaviorSelection) => void;
  onEditLayout: () => void;
  onToggleAutoplay: () => void;
  onRunBatch: () => void;
  onReplayIndexChange: (value: number) => void;
}

export function ControlsPanel(props: ControlsPanelProps) {
  const selectedScenario = props.enemyPresets.find((preset) => preset.id === props.enemyPresetIdInput) ?? null;
  const progressLabel = props.batchJobStatus
    ? `${props.batchJobStatus.completedRuns} / ${props.batchJobStatus.totalRuns} runs completed`
    : null;
  const progressPercent = props.batchJobStatus
    ? Math.max(0, Math.min(100, props.batchJobStatus.progressRatio * 100))
    : 0;
  const progressPhase = props.batchJobStatus?.currentMonsterBehavior
    ? `${formatMonsterBehavior(props.batchJobStatus.currentMonsterBehavior)} DM`
    : props.batchJobStatus?.status === 'completed'
      ? 'Complete'
      : props.batchJobStatus?.status === 'failed'
        ? 'Failed'
        : 'Preparing';

  return (
    <section className="panel controls-panel">
      <div className="panel-header">
        <h2>Controls</h2>
        <p>Choose the party, scenario, behavior model, and batch size for a deterministic simulation run.</p>
      </div>

      <div className="control-grid">
        <label className="field">
          <span>Seed</span>
          <input
            value={props.seedInput}
            onChange={(event) => props.onSeedChange(event.target.value)}
            placeholder="Enter deterministic seed"
          />
        </label>

        <label className="field">
          <span>Batch Size</span>
          <input
            type="number"
            min={1}
            max={MAX_BATCH_SIZE}
            value={props.batchSizeInput}
            onChange={(event) => props.onBatchSizeChange(event.target.value)}
            inputMode="numeric"
          />
        </label>

        <label className="field">
          <span>Player Behavior</span>
          <select
            value={props.playerBehaviorInput}
            onChange={(event) => props.onPlayerBehaviorChange(event.target.value as PlayerBehavior)}
          >
            <option value="smart">Smart Players</option>
            <option value="dumb">Dumb Players</option>
            <option value="balanced">Balanced</option>
          </select>
        </label>

        <label className="field">
          <span>Party</span>
          <select
            value={props.playerPresetIdInput}
            onChange={(event) => props.onPlayerPresetChange(event.target.value)}
            disabled={!props.catalogLoaded}
          >
            {!props.catalogLoaded ? <option value="">Loading parties...</option> : null}
            {props.playerPresets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.displayName}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Scenario</span>
          <select
            value={props.enemyPresetIdInput}
            onChange={(event) => props.onEnemyPresetChange(event.target.value)}
            disabled={!props.catalogLoaded}
          >
            {!props.catalogLoaded ? <option value="">Loading scenarios...</option> : null}
            {props.enemyPresets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.displayName}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>DM Style</span>
          <select
            value={props.monsterBehaviorInput}
            onChange={(event) => props.onMonsterBehaviorChange(event.target.value as MonsterBehaviorSelection)}
          >
            <option value="kind">Kind DM</option>
            <option value="balanced">Balanced DM</option>
            <option value="evil">Evil DM</option>
            <option value="combined">Combined Batch</option>
          </select>
        </label>
      </div>

      <div className="panel-copy accent scenario-callout">
        <strong>Selected Scenario:</strong> {selectedScenario?.displayName ?? (props.enemyPresetIdInput || '-')}
        {selectedScenario?.description ? <span> {selectedScenario.description}</span> : null}
      </div>

      <div className="panel-copy">
        Combined Batch runs Kind, Balanced, and Evil DM styles and reports the aggregate.
      </div>

      <div className="button-row">
        <button type="button" className="secondary-button" onClick={props.onEditLayout} disabled={!props.hasEncounter}>
          Edit Layout
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={props.onToggleAutoplay}
          disabled={!props.hasEncounter || props.isRunning}
        >
          {props.isAutoplaying ? 'Pause Replay' : 'Auto Play'}
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={props.onRunBatch}
          disabled={!props.canRunSimulation || props.isRunning}
        >
          {props.isRunning ? 'Running...' : 'Batch Run'}
        </button>
      </div>

      <div className="panel-copy">
        Set <strong>Batch Size</strong> to <strong>1</strong> with a single <strong>DM Style</strong> for a
        turn-by-turn replay. Use larger batches to estimate outcome rates.
      </div>

      <div className="panel-copy">
        Runs are processed by the local Python simulation backend.
      </div>

      {props.batchJobStatus ? (
        <div className="progress-shell" aria-live="polite">
          <div className="progress-header-row">
            <strong>Batch Progress</strong>
            <span>{progressLabel}</span>
          </div>
          <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent}>
            <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="progress-meta-row">
            <span>Elapsed: {formatElapsedTime(props.batchElapsedSeconds ?? 0)}</span>
            <span>Phase: {progressPhase}</span>
          </div>
        </div>
      ) : null}

      {props.hasEncounter ? (
        <label className="field scrubber">
          <span>
            Replay Frame {props.replayIndex + 1} / {props.replayFrameCount}
          </span>
          <input
            type="range"
            min={0}
            max={props.replayFrameCount - 1}
            value={props.replayIndex}
            onChange={(event) => props.onReplayIndexChange(Number(event.target.value))}
          />
        </label>
      ) : null}

      <div className={`panel-copy accent ${props.placementValidation.isValid ? 'ready-accent' : ''}`}>
        {props.placementValidation.placedUnitIds.length} / {props.activeUnitCount} units placed.{' '}
        {props.placementStatusText}
      </div>

      {props.error ? <div className="error-banner">{props.error}</div> : null}
    </section>
  );
}

interface EncounterSummaryPanelProps {
  enemyCatalog: EnemyCatalogResponse | null;
  playerCatalog: PlayerCatalogResponse | null;
  seedInput: string;
  enemyPresetIdInput: string;
  playerPresetIdInput: string;
  playerBehaviorInput: PlayerBehavior;
  monsterBehaviorInput: MonsterBehaviorSelection;
  encounterSummary: EncounterSummary | null;
  batchSummary: BatchSummary | null;
}

export function EncounterSummaryPanel(props: EncounterSummaryPanelProps) {
  const totalPlayerMaxHp =
    getTotalPlayerMaxHpForPreset(props.playerCatalog, props.playerPresetIdInput) || DEFAULT_PARTY_MAX_HP;

  return (
    <section className="panel battle-overview">
      <div className="panel-header">
        <h2>Encounter Summary</h2>
        <p>Current outcome, replay position, and batch aggregates.</p>
      </div>

      <div className="metrics-grid">
        <MetricCard label="Seed" value={props.encounterSummary?.seed ?? props.seedInput} />
        <MetricCard label="Party" value={getPlayerPresetLabel(props.playerCatalog, props.playerPresetIdInput)} />
        <MetricCard label="Scenario" value={getEnemyPresetLabel(props.enemyCatalog, props.enemyPresetIdInput)} />
        <MetricCard
          label="Player Behavior"
          value={formatPlayerBehavior(props.encounterSummary?.playerBehavior ?? props.playerBehaviorInput)}
        />
        <MetricCard
          label="DM Style"
          value={formatMonsterBehavior(props.encounterSummary?.monsterBehavior ?? props.monsterBehaviorInput)}
        />
        <MetricCard label="Winner" value={formatWinner(props.encounterSummary?.winner)} />
        <MetricCard label="Rounds" value={props.encounterSummary ? String(props.encounterSummary.rounds) : '-'} />
        <MetricCard
          label="Party Deaths"
          value={props.encounterSummary ? String(props.encounterSummary.fighterDeaths) : '-'}
          tone="fighters"
        />
        <MetricCard
          label="Enemies Killed"
          value={props.encounterSummary ? String(props.encounterSummary.goblinsKilled) : '-'}
          tone="goblins"
        />
        <MetricCard
          label="Party HP"
          value={props.encounterSummary ? `${props.encounterSummary.remainingFighterHp} / ${totalPlayerMaxHp}` : '-'}
          tone="fighters"
        />
        <MetricCard
          label="Enemy HP"
          value={
            props.encounterSummary
              ? `${props.encounterSummary.remainingGoblinHp} / ${getTotalEnemyMaxHpForPreset(props.enemyCatalog, props.enemyPresetIdInput)}`
              : '-'
          }
          tone="goblins"
        />
        <MetricCard
          label="Stable Unconscious"
          value={props.encounterSummary ? String(props.encounterSummary.stableUnconsciousFighters) : '-'}
        />
      </div>

      <BatchMetrics
        batchSummary={props.batchSummary}
        enemyCatalog={props.enemyCatalog}
        playerCatalog={props.playerCatalog}
        enemyPresetIdInput={props.enemyPresetIdInput}
        playerPresetIdInput={props.playerPresetIdInput}
      />
    </section>
  );
}

interface VisualizationPanelProps {
  enemyCatalog: EnemyCatalogResponse | null;
  playerCatalog: PlayerCatalogResponse | null;
  isSetupMode: boolean;
  spatialReplayActive: boolean;
  enemyPresetIdInput: string;
  playerPresetIdInput: string;
  activeUnitIds: string[];
  placementValidation: PlacementValidationResult;
  placements: Record<string, GridPosition>;
  selectedPlacementUnitId: string | null;
  terrainFeatures: TerrainFeature[];
  setupUnits: BoardUnit[];
  orderedUnits: UnitState[];
  highlightedPath: GridPosition[];
  currentFrame: ReplayFrame | null;
  initialFrame: ReplayFrame | null;
  currentRound: number;
  attackLine: AttackLine | null;
  onResetLayout: () => void;
  onSelectPlacementUnit: (unitId: string) => void;
  onPlacementCellClick: (position: GridPosition, occupantId: string | null) => void;
}

export function VisualizationPanel(props: VisualizationPanelProps) {
  const placementStatusText = getPlacementStatusText(props.placementValidation, props.activeUnitIds.length);
  const selectedPlacementSummary = getSelectedPlacementSummary(
    props.selectedPlacementUnitId,
    props.placements,
    props.enemyPresetIdInput,
    props.playerPresetIdInput,
    props.enemyCatalog,
    props.playerCatalog
  );
  const combatStateDescription = props.isSetupMode
    ? `Click-to-place setup on the 15 x 15 grid for the ${getPlayerPresetLabel(props.playerCatalog, props.playerPresetIdInput)} against ${getEnemyPresetLabel(props.enemyCatalog, props.enemyPresetIdInput)}. Combat stays locked until every active unit is placed.`
    : '15 x 15 combat grid with movement, range, terrain cover, and opportunity attacks.';
  const initialFrame = props.initialFrame;
  const initiativeRibbon = initialFrame ? (
    initialFrame.state.initiativeOrder.map((unitId) => (
      <div
        key={unitId}
        className={`initiative-token ${props.currentFrame?.activeCombatantId === unitId ? 'active' : ''}`}
      >
        <span>{unitId}</span>
        <small>{initialFrame.state.initiativeScores[unitId]}</small>
      </div>
    ))
  ) : (
    <div className="panel-copy">Run the encounter to populate initiative order.</div>
  );

  return (
    <section className="panel visualization-panel">
      <div className="panel-header">
        <h2>Combat State</h2>
        <p>{combatStateDescription}</p>
      </div>

      {props.isSetupMode ? (
        <>
          <div className="status-stage">
            <div className="stage-chip">
              <span>Placed</span>
              <strong>
                {props.placementValidation.placedUnitIds.length} / {props.activeUnitIds.length}
              </strong>
            </div>
            <div className="stage-chip">
              <span>Selected</span>
              <strong>{props.selectedPlacementUnitId ?? '-'}</strong>
            </div>
            <div className="stage-chip">
              <span>Status</span>
              <strong>{props.placementValidation.isValid ? 'Ready' : 'Setup'}</strong>
            </div>
          </div>

          <div className="placement-workbench">
            <div className="placement-sidebar">
              <div className="placement-toolbar">
                <button type="button" className="secondary-button" onClick={props.onResetLayout}>
                  Reset to Default Layout
                </button>
              </div>

              <div className="panel-copy">
                Select a unit, then click an empty square. Clicking an occupied square selects that unit for
                repositioning.
              </div>

              <div className={`placement-status ${props.placementValidation.isValid ? 'ready' : ''}`}>
                {placementStatusText}
              </div>

              <div className="placement-unit-list">
                {props.activeUnitIds.map((unitId) => {
                  const position = props.placements[unitId];
                  const isSelected = props.selectedPlacementUnitId === unitId;

                  return (
                    <button
                      key={unitId}
                      type="button"
                      className={`placement-unit-button ${isSelected ? 'active' : ''} ${position ? 'placed' : ''}`}
                      onClick={() => props.onSelectPlacementUnit(unitId)}
                      aria-label={`Select ${unitId} ${getUnitLabel(props.enemyCatalog, props.playerCatalog, props.enemyPresetIdInput, props.playerPresetIdInput, unitId)}${position ? ` at ${formatPosition(position)}` : ', unplaced'}`}
                    >
                      <span>{unitId}</span>
                      <strong>{getUnitLabel(props.enemyCatalog, props.playerCatalog, props.enemyPresetIdInput, props.playerPresetIdInput, unitId)}</strong>
                      <small>{position ? formatPosition(position) : 'Unplaced'}</small>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid-board-section">
              <h3>Placement Grid</h3>
              <GridBoard
                units={props.setupUnits}
                terrainFeatures={props.terrainFeatures}
                highlightedPath={[]}
                activeUnitId={null}
                attackLine={null}
                selectedPlacementUnitId={props.selectedPlacementUnitId}
                onCellClick={props.onPlacementCellClick}
                ariaLabel="Placement grid"
              />
              <div className="panel-copy">Selected unit: {selectedPlacementSummary}.</div>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="status-stage">
            <div className="stage-chip">
              <span>Round</span>
              <strong>{props.currentRound}</strong>
            </div>
            <div className="stage-chip">
              <span>Active</span>
              <strong>{props.currentFrame?.activeCombatantId ?? '-'}</strong>
            </div>
            <div className="stage-chip">
              <span>Phase</span>
              <strong>{props.currentFrame?.state.terminalState === 'complete' ? 'Complete' : 'Combat'}</strong>
            </div>
          </div>

          <div className="initiative-ribbon">
            {initiativeRibbon}
          </div>
        </>
      )}

      {props.spatialReplayActive ? (
        <div className="grid-board-section">
          <h3>Grid View</h3>
          <GridBoard
            units={props.orderedUnits}
            terrainFeatures={props.terrainFeatures}
            highlightedPath={props.highlightedPath}
            activeUnitId={props.currentFrame?.activeCombatantId ?? null}
            attackLine={props.attackLine}
            ariaLabel="Combat grid"
          />
          {props.highlightedPath.length > 1 ? (
            <div className="panel-copy">Current movement path: {formatPath(props.highlightedPath)}</div>
          ) : (
            <div className="panel-copy">This frame has no movement path.</div>
          )}
          {props.attackLine ? (
            <div className="panel-copy">
              Current attack line: {props.attackLine.actorId} {formatPosition(props.attackLine.from)} to{' '}
              {props.attackLine.targetId} {formatPosition(props.attackLine.to)}
            </div>
          ) : (
            <div className="panel-copy">This frame has no attack line.</div>
          )}
        </div>
      ) : !props.isSetupMode ? (
        <div className="panel-copy">Run the simulation to view the 15 x 15 combat grid.</div>
      ) : null}
    </section>
  );
}

export function CurrentFramePanel(props: { currentFrame: ReplayFrame | null }) {
  return (
    <section className="panel replay-panel">
      <div className="panel-header">
        <h2>Current Frame</h2>
        <p>Structured turn output with rolls, totals, and condition deltas.</p>
      </div>

      {props.currentFrame ? (
        <div className="event-stack">
          {props.currentFrame.events.map((event, index) => (
            <article key={`${event.actorId}-${event.eventType}-${index}-${event.round}`} className="event-card">
              <header className="event-header">
                <span className="event-type">{event.eventType.replace('_', ' ')}</span>
                <strong>{event.textSummary}</strong>
              </header>

              {Object.keys(event.rawRolls).length > 0 ? (
                <dl className="event-detail-grid">
                  {Object.entries(event.rawRolls).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{formatFieldValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}

              {Object.keys(event.resolvedTotals).length > 0 ? (
                <dl className="event-detail-grid">
                  {Object.entries(event.resolvedTotals).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{formatFieldValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}

              {event.movementDetails?.path && event.movementDetails.path.length > 1 ? (
                <div className="movement-trace">
                  <strong>Path:</strong> {formatPath(event.movementDetails.path)}
                </div>
              ) : null}

              {event.conditionDeltas.length > 0 ? (
                <ul className="delta-list">
                  {event.conditionDeltas.map((delta) => (
                    <li key={delta}>{delta}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="panel-copy">Run a seed to populate the replay feed.</div>
      )}
    </section>
  );
}

export function UnitStatePanel(props: { orderedUnits: UnitState[] }) {
  return (
    <section className="panel unit-panel">
      <div className="panel-header">
        <h2>Unit State</h2>
        <p>Per-unit HP, resources, status, and temporary effects at the selected frame.</p>
      </div>

      <div className="unit-grid">
        {props.orderedUnits.length > 0 ? (
          props.orderedUnits.map((unit) => (
            <article key={unit.id} className={`unit-card ${unit.faction}`}>
              <header className="unit-header">
                <div>
                  <span className="unit-id">{unit.id}</span>
                  <strong>{unit.templateName}</strong>
                </div>
                <span className={`status-pill ${getUnitStatus(unit).toLowerCase()}`}>{getUnitStatus(unit)}</span>
              </header>

              <dl className="unit-stats">
                <div>
                  <dt>HP</dt>
                  <dd>
                    {unit.currentHp} / {unit.maxHp}
                  </dd>
                </div>
                {unit.temporaryHitPoints > 0 ? (
                  <div>
                    <dt>Temp HP</dt>
                    <dd>{unit.temporaryHitPoints}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>AC</dt>
                  <dd>{unit.ac}</dd>
                </div>
                {unit.position ? (
                  <div>
                    <dt>Position</dt>
                    <dd>{formatPosition(unit.position)}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Role</dt>
                  <dd>{unit.combatRole.replace(/_/g, ' ')}</dd>
                </div>
                <div>
                  <dt>Resources</dt>
                    <dd>
                      {[
                        unit.resources.secondWindUses > 0 ? `Second Wind ${unit.resources.secondWindUses}` : null,
                        unit.resources.javelins > 0 ? `Javelins ${unit.resources.javelins}` : null,
                        unit.resources.rageUses > 0 ? `Rage ${unit.resources.rageUses}` : null,
                        unit.resources.handaxes > 0 ? `Handaxes ${unit.resources.handaxes}` : null,
                        unit.resources.actionSurgeUses > 0 ? `Action Surge ${unit.resources.actionSurgeUses}` : null,
                        unit.resources.superiorityDice > 0 ? `Superiority Dice ${unit.resources.superiorityDice}` : null,
                        unit.resources.focusPoints > 0 ? `Focus ${unit.resources.focusPoints}` : null,
                        unit.resources.spellSlotsLevel1 > 0 ? `1st-level Slots ${unit.resources.spellSlotsLevel1}` : null,
                        unit.resources.spellSlotsLevel2 > 0 ? `2nd-level Slots ${unit.resources.spellSlotsLevel2}` : null,
                        unit.resources.spellSlotsLevel3 > 0 ? `3rd-level Slots ${unit.resources.spellSlotsLevel3}` : null,
                        unit.resources.layOnHandsPoints > 0 ? `Lay on Hands ${unit.resources.layOnHandsPoints}` : null,
                        unit.resources.channelDivinityUses > 0
                          ? `Channel Divinity ${unit.resources.channelDivinityUses}`
                          : null,
                        unit.resources.uncannyMetabolismUses > 0
                          ? `Uncanny Metabolism ${unit.resources.uncannyMetabolismUses}`
                          : null
                      ]
                        .filter(Boolean)
                        .join(', ') || 'None'}
                    </dd>
                  </div>
                <div>
                  <dt>Death Saves</dt>
                  <dd>
                    {unit.deathSaveSuccesses} / {unit.deathSaveFailures}
                  </dd>
                </div>
                <div>
                  <dt>Effects</dt>
                  <dd>
                    {unit.temporaryEffects.length > 0
                      ? unit.temporaryEffects.map((effect) => effect.kind.replace(/_/g, ' ')).join(', ')
                      : 'None'}
                  </dd>
                </div>
              </dl>
            </article>
          ))
        ) : (
          <div className="panel-copy">Unit cards appear after the first run.</div>
        )}
      </div>
    </section>
  );
}

export function TimelinePanel(props: { timelineEvents: CombatEvent[] }) {
  return (
    <section className="panel log-panel">
      <div className="panel-header">
        <h2>Per-Round Event Log</h2>
        <p>The timeline is deterministic and grows frame by frame.</p>
      </div>

      <div className="timeline">
        {props.timelineEvents.length > 0 ? (
          props.timelineEvents.map((event, index) => (
            <div key={`${event.actorId}-${event.eventType}-${index}-${event.round}`} className="timeline-row">
              <span className="timeline-round">R{event.round}</span>
              <strong>{event.actorId}</strong>
              <span>{event.textSummary}</span>
            </div>
          ))
        ) : (
          <div className="panel-copy">The full event log will populate after the first run.</div>
        )}
      </div>
    </section>
  );
}
