import {
  getFootprintDimensions,
  getOccupiedSquaresForPosition,
  GRID_SIZE,
  SINGLE_SQUARE_FOOTPRINT,
  terrainBlocksPlacement,
} from "../shared/sim/spatial";
import { useState, type CSSProperties } from "react";
import type { PlacementValidationResult } from "../shared/sim/spatial";
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
  ReplayAction,
  ReplayFrame,
  TerrainFeature,
  UnitState,
} from "../shared/sim/types";
import {
  DEFAULT_PARTY_MAX_HP,
  MAX_BATCH_SIZE,
  getEnemyPreset,
  getPlayerPreset,
  getTotalEnemyMaxHpForPreset,
  getTotalPlayerMaxHpForPreset,
  getUnitDisplayName,
} from "./catalog";
import { getActiveReplayEvents } from "./replay";

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
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function getTerrainToken(feature: TerrainFeature): string {
  if (feature.kind === "wall" || feature.kind === "low_wall") {
    return "W";
  }
  if (feature.kind === "boulder") {
    return "B";
  }
  if (feature.kind === "column") {
    return "C";
  }
  return "R";
}

function getTerrainLabel(feature: TerrainFeature): string {
  if (feature.kind === "wall" || feature.kind === "low_wall") {
    return "wall";
  }
  if (feature.kind === "boulder") {
    return "boulder";
  }
  if (feature.kind === "column") {
    return "column";
  }
  return "rock";
}

function formatFieldValue(value: CombatEvent["rawRolls"][string]): string {
  if (Array.isArray(value)) {
    return value.join(", ");
  }

  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }

  if (value === null) {
    return "-";
  }

  return String(value);
}

function getUnitStatus(unit: UnitState): string {
  if (unit.conditions.dead) {
    return "Dead";
  }

  if (unit.currentHp === 0 && unit.stable) {
    return "Stable";
  }

  if (unit.currentHp === 0) {
    return "Dying";
  }

  return "Active";
}

function formatOutOf(value: number, maximum: number): string {
  return `${formatNumber(value)} / ${maximum}`;
}

function formatPosition(position: GridPosition): string {
  return `(${position.x},${position.y})`;
}

function formatPath(path: GridPosition[]): string {
  return path.map(formatPosition).join(" -> ");
}

function formatUnitList(unitIds: string[]): string {
  return unitIds.join(", ");
}

function formatPlayerBehavior(
  value: PlayerBehavior | EncounterSummary["playerBehavior"],
): string {
  if (value === "balanced") {
    return "Balanced";
  }

  return value === "smart" ? "Smart" : "Dumb";
}

function formatMonsterBehavior(
  value:
    | MonsterBehaviorSelection
    | EncounterSummary["monsterBehavior"]
    | BatchCombinationSummary["monsterBehavior"],
): string {
  if (value === "combined") {
    return "Combined";
  }

  if (value === "kind") {
    return "Kind";
  }

  return value === "balanced" ? "Balanced" : "Evil";
}

function formatWinner(
  value: EncounterSummary["winner"] | null | undefined,
): string {
  if (!value) {
    return "-";
  }

  if (value === "fighters") {
    return "Party";
  }

  if (value === "goblins") {
    return "Enemies";
  }

  if (value === "mutual_annihilation") {
    return "Mutual Annihilation";
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
  eventIndex?: number;
}

export type BoardUnit = Pick<
  UnitState,
  "id" | "faction" | "position" | "footprint"
> & {
  templateName?: string;
  combatRole?: string;
  spriteKey?: string;
};

type GridInteractionMode = "setup" | "movement" | "attack" | "replay";
type CoverStatus = "clear" | "cover";

function cleanUnitName(name: string): string {
  return name
    .replace(/^Level\s+\d+\s+/i, "")
    .replace(/\s*Sample Build\s*/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getUnitLabel(
  enemyCatalog: EnemyCatalogResponse | null,
  playerCatalog: PlayerCatalogResponse | null,
  enemyPresetId: string,
  playerPresetId: string,
  unitId: string,
): string {
  return cleanUnitName(
    getUnitDisplayName(
      enemyCatalog,
      playerCatalog,
      enemyPresetId,
      playerPresetId,
      unitId,
    ),
  );
}

function getEnemyPresetLabel(
  catalog: EnemyCatalogResponse | null,
  enemyPresetId: string,
): string {
  return (
    getEnemyPreset(catalog, enemyPresetId)?.displayName ?? enemyPresetId ?? "-"
  );
}

function getPlayerPresetLabel(
  catalog: PlayerCatalogResponse | null,
  playerPresetId: string,
): string {
  return (
    getPlayerPreset(catalog, playerPresetId)?.displayName ??
    playerPresetId ??
    "-"
  );
}

function getBoardPoint(
  position: GridPosition,
  footprint: Footprint = SINGLE_SQUARE_FOOTPRINT,
): { x: number; y: number } {
  const dimensions = getFootprintDimensions(footprint);

  return {
    x: position.x - 0.5 + (dimensions.width - 1) / 2,
    y: GRID_SIZE - position.y + 0.5 - (dimensions.height - 1) / 2,
  };
}

function logBoardCellClick(
  position: GridPosition,
  occupantId: string | null,
  terrainFeature: TerrainFeature | null,
): void {
  console.log("Clicked cell for terrain calibration:", {
    x: position.x,
    y: position.y,
    square: `${position.x},${position.y}`,
    flippedY: GRID_SIZE + 1 - position.y,
    occupantId,
    terrainFeatureId: terrainFeature?.featureId ?? null,
    terrainKind: terrainFeature?.kind ?? null,
  });
}

function getPlacementStatusText(
  validation: PlacementValidationResult,
  activeUnitCount: number,
): string {
  if (validation.isValid) {
    return `All ${activeUnitCount} units are placed. Combat is ready.`;
  }

  if (
    validation.outOfBoundsUnitIds.length > 0 ||
    validation.overlappingGroups.length > 0 ||
    validation.blockedSquareGroups.length > 0
  ) {
    return (
      validation.errors[0] ??
      "The simulator requires a complete, valid placement layout."
    );
  }

  return `Place the remaining units: ${formatUnitList(validation.missingUnitIds)}.`;
}

function MetricCard(props: {
  label: string;
  value: string;
  tone?: "fighters" | "goblins" | "neutral";
}) {
  return (
    <div className={`metric-card ${props.tone ?? "neutral"}`}>
      <span className="metric-label">{props.label}</span>
      <strong className="metric-value">{props.value}</strong>
    </div>
  );
}
function isWhiteDragonUnit(unit: BoardUnit | UnitState): boolean {
  const name = String(
    unit.templateName ??
      (unit as any).name ??
      (unit as any).template_name ??
      (unit as any).label ??
      "",
  ).toLowerCase();
  const spriteKey = String((unit as BoardUnit).spriteKey ?? "").toLowerCase();

  return name.includes("white dragon") || spriteKey.includes("white_dragon");
}

function isDeadWhiteDragonUnit(unit: BoardUnit | UnitState | undefined): boolean {
  return Boolean(unit && isWhiteDragonUnit(unit) && isUnitDefeated(unit));
}

function getUnitSprite(unit: BoardUnit | UnitState): string {
  const id = unit.id?.toLowerCase() ?? "";
  const name = String(
    unit.templateName ??
      (unit as any).name ??
      (unit as any).template_name ??
      (unit as any).label ??
      "",
  ).toLowerCase();

  if (id === "f1") return "/sprites/fighter.png";
  if (id === "f2") return "/sprites/paladin.png";
  if (id === "f3") return "/sprites/rogue.png";
  if (id === "f4") return "/sprites/wizard.png";

  if (isDeadWhiteDragonUnit(unit)) {
    return "/sprites/dead_white_dragon.png";
  }

  if (name.includes("white dragon")) {
    return "/sprites/boss_white_dragon.png";
  }

  if (name.includes("scale sorcerer")) {
    return "/sprites/reptilian_warrior_in_pixel_art.png";
  }

  if (name.includes("dragonshield")) {
    return "/sprites/enemy.png";
  }

  if (name.includes("kobold warrior")) {
    return "/sprites/reptilian_warrior_in_battle_stance.png";
  }

  if (name.includes("red dragon")) {
    return "/sprites/young_red_dragon.png";
  }

  if (name.includes("dragon")) {
    return "/sprites/dragon.png";
  }

  if (name.includes("centaur")) {
    return "/sprites/centaurTrooper.png";
  }

  if (name.includes("shield guard")) {
    return "/sprites/enemy.png";
  }

  if (
    name.includes("fire shaman") ||
    name.includes("shaman") ||
    name.includes("mage")
  ) {
    return "/sprites/reptilian_warrior_in_pixel_art.png";
  }

  if (name.includes("brute")) {
    return "/sprites/reptilian_warrior_in_battle_stance.png";
  }

  if (name.includes("warrior")) {
    return "/sprites/reptilian_warrior_in_pixel_art.png";
  }

  if (
    name.includes("kobold") ||
    name.includes("reptilian") ||
    name.includes("lizard")
  ) {
    return "/sprites/reptilian_warrior_in_battle_stance.png";
  }

  if (name.includes("goblin")) return "/sprites/enemy.png";
  if (name.includes("guard")) return "/sprites/enemy.png";
  if (name.includes("scout")) return "/sprites/enemy.png";
  if (name.includes("knight")) return "/sprites/enemy.png";

  return "/sprites/enemy.png";
}

function getUnitTokenStyle(unit: BoardUnit): CSSProperties {
  const dimensions = getFootprintDimensions(
    unit.footprint ?? SINGLE_SQUARE_FOOTPRINT,
  );

  return {
    width: `${dimensions.width * 100}%`,
    height: `${dimensions.height * 100}%`,
    left: 0,
    top: `${-(dimensions.height - 1) * 100}%`,
  };
}

function positionKey(position: GridPosition): string {
  return `${position.x},${position.y}`;
}

function parsePositionKey(key: string): GridPosition {
  const [x, y] = key.split(",").map(Number);
  return { x, y };
}

function gridDistance(a: GridPosition, b: GridPosition): number {
  return Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
}

function getMoveRangeForUnit(unit: BoardUnit): number {
  const id = unit.id.toLowerCase();
  const name = unit.templateName?.toLowerCase() ?? "";

  if (name.includes("kobold brute")) return 4;
  if (name.includes("kobold fire shaman")) return 3;
  if (name.includes("kobold shield guard")) return 3;
  if (id.startsWith("f")) return 6;
  if (id.startsWith("e")) return 6;
  if (id.startsWith("d")) return 8;

  return 6;
}

function getAttackRangeForUnit(unit: BoardUnit): number {
  const id = unit.id.toLowerCase();
  const name = unit.templateName?.toLowerCase() ?? "";

  if (id === "f1") return 1;
  if (id === "f2") return 1;
  if (id === "f3") return 12;
  if (id === "f4") return 12;

  if (name.includes("kobold fire shaman")) return 4;
  if (name.includes("kobold brute")) return 1;
  if (name.includes("kobold shield guard")) return 1;
  if (name.includes("archer")) return 12;
  if (name.includes("centaur")) return 12;
  if (name.includes("griffon")) return 1;
  if (name.includes("dragon")) return 3;

  return 1;
}

function isWithinAttackRange(
  attacker: GridPosition,
  target: GridPosition,
  range: number,
): boolean {
  return gridDistance(attacker, target) <= range;
}

function getLineCells(start: GridPosition, end: GridPosition): GridPosition[] {
  const cells: GridPosition[] = [];
  let x0 = start.x;
  let y0 = start.y;
  const x1 = end.x;
  const y1 = end.y;
  const dx = Math.abs(x1 - x0);
  const dy = Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx - dy;

  while (!(x0 === x1 && y0 === y1)) {
    const e2 = 2 * err;

    if (e2 > -dy) {
      err -= dy;
      x0 += sx;
    }

    if (e2 < dx) {
      err += dx;
      y0 += sy;
    }

    if (!(x0 === x1 && y0 === y1)) {
      cells.push({ x: x0, y: y0 });
    }
  }

  return cells;
}

function getCoverStatus(
  attackerPosition: GridPosition,
  targetPosition: GridPosition,
  terrainSquares: Map<string, unknown>,
  occupiedSquares: Map<string, { unit: BoardUnit }>,
  attackerId: string,
  targetId: string,
): CoverStatus {
  const lineCells = getLineCells(attackerPosition, targetPosition);

  for (const cell of lineCells) {
    const key = positionKey(cell);

    if (terrainSquares.has(key)) {
      return "cover";
    }

    const occupant = occupiedSquares.get(key)?.unit;

    if (occupant && occupant.id !== attackerId && occupant.id !== targetId) {
      return "cover";
    }
  }

  return "clear";
}

function getBoardUnitById(
  units: BoardUnit[],
  unitId: string | null | undefined,
): BoardUnit | undefined {
  if (!unitId) {
    return undefined;
  }

  return units.find((unit) => unit.id === unitId);
}

function getHudUnitDisplayName(
  unit: BoardUnit | UnitState | undefined,
): string {
  if (!unit) {
    return "Unknown Unit";
  }

  return cleanUnitName(unit.templateName ?? unit.id);
}

function replaceUnitIdsWithNames(
  text: string,
  units: Array<BoardUnit | UnitState>,
): string {
  return [...units]
    .sort((left, right) => right.id.length - left.id.length)
    .reduce(
      (updatedText, unit) =>
        updatedText.replace(
          new RegExp(`\\b${unit.id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g"),
          getHudUnitDisplayName(unit),
        ),
      text,
    );
}

function getUnitCurrentHp(
  unit: BoardUnit | UnitState | undefined,
): number | null {
  const candidate = unit as
    | (Partial<UnitState> & {
        hp?: number;
        hitPoints?: number;
        state?: Partial<UnitState>;
        combatState?: Partial<UnitState>;
      })
    | undefined;
  const hp =
    candidate?.currentHp ??
    candidate?.hp ??
    candidate?.hitPoints ??
    candidate?.state?.currentHp ??
    candidate?.combatState?.currentHp;

  return typeof hp === "number" ? hp : null;
}

function getUnitMaxHp(unit: BoardUnit | UnitState | undefined): number | null {
  const candidate = unit as
    | (Partial<UnitState> & {
        hitPointsMax?: number;
        max_hp?: number;
        state?: Partial<UnitState>;
        combatState?: Partial<UnitState>;
      })
    | undefined;
  const hp =
    candidate?.maxHp ??
    candidate?.max_hp ??
    candidate?.hitPointsMax ??
    candidate?.state?.maxHp ??
    candidate?.combatState?.maxHp;

  return typeof hp === "number" ? hp : null;
}

function getUnitHpText(unit: BoardUnit | UnitState | undefined): string {
  const currentHp = getUnitCurrentHp(unit);
  const maxHp = getUnitMaxHp(unit);

  if (currentHp === null || maxHp === null) {
    return "-";
  }

  return `${currentHp}/${maxHp}`;
}

function getUnitAcText(unit: BoardUnit | UnitState | undefined): string {
  const candidate = unit as
    | (Partial<UnitState> & {
        armorClass?: number;
        armor_class?: number;
      })
    | undefined;
  const ac = candidate?.armorClass ?? candidate?.ac ?? candidate?.armor_class;
  return ac !== undefined ? String(ac) : "-";
}

function getCatalogMaxHpForUnit(
  enemyCatalog: EnemyCatalogResponse | null,
  playerCatalog: PlayerCatalogResponse | null,
  enemyPresetId: string,
  playerPresetId: string,
  unitId: string,
): number | undefined {
  if (unitId.startsWith("F")) {
    const playerPreset = getPlayerPreset(playerCatalog, playerPresetId);
    const presetUnit = playerPreset?.units.find(
      (unit) => unit.unitId === unitId,
    );

    return playerCatalog?.loadouts.find(
      (loadout) => loadout.id === presetUnit?.loadoutId,
    )?.maxHp;
  }

  const enemyPreset = getEnemyPreset(enemyCatalog, enemyPresetId);
  const presetUnit = enemyPreset?.units.find((unit) => unit.unitId === unitId);

  return enemyCatalog?.enemyVariants.find(
    (variant) => variant.id === presetUnit?.variantId,
  )?.maxHp;
}

function getUnitPositionText(unit: BoardUnit | UnitState | undefined): string {
  if (!unit?.position) {
    return "-";
  }

  return `(${unit.position.x},${unit.position.y})`;
}

function isUnitDefeated(unit: BoardUnit | UnitState | undefined): boolean {
  const candidate = unit as
    | (Partial<UnitState> & {
        condition?: string;
        status?: string;
        state?: { status?: string };
        combatState?: { status?: string };
      })
    | undefined;

  if (!candidate) {
    return false;
  }

  const currentHp = getUnitCurrentHp(unit);
  const statusText = String(
    candidate.status ??
      candidate.condition ??
      candidate.state?.status ??
      candidate.combatState?.status ??
      "",
  ).toLowerCase();

  if (currentHp !== null && currentHp <= 0) {
    return true;
  }

  return (
    Boolean(candidate.conditions?.dead || candidate.conditions?.unconscious) ||
    statusText.includes("dead") ||
    statusText.includes("unconscious") ||
    statusText.includes("defeated") ||
    statusText.includes("removed")
  );
}

function getUnitStatusLabel(unit: UnitState): string {
  if (isUnitDefeated(unit)) {
    return "Dead";
  }

  return getUnitStatus(unit);
}

function getDeathRoundForUnit(
  unitId: string,
  timelineEvents: CombatEvent[] | undefined,
): number | null {
  if (!timelineEvents) {
    return null;
  }

  const normalizedUnitId = unitId.toLowerCase();

  for (const event of timelineEvents) {
    const conditionText = event.conditionDeltas.join(" ").toLowerCase();
    const eventText = [
      event.textSummary,
      event.eventType,
      conditionText,
    ]
      .join(" ")
      .toLowerCase();
    const unitDeathPatterns = [
      `${normalizedUnitId} drops to zero`,
      `${normalizedUnitId} dropped to zero`,
      `${normalizedUnitId} drops to 0`,
      `${normalizedUnitId} dropped to 0`,
      `${normalizedUnitId} is removed`,
      `${normalizedUnitId} removed`,
      `${normalizedUnitId} dies`,
      `${normalizedUnitId} is dead`,
      `${normalizedUnitId} dead`,
      `${normalizedUnitId} defeated`,
      `${normalizedUnitId} unconscious`,
    ];
    const mentionsUnit =
      event.targetIds.includes(unitId) ||
      conditionText.includes(normalizedUnitId) ||
      unitDeathPatterns.some((pattern) => eventText.includes(pattern));
    const isDeathEvent =
      eventText.includes("removed from combat") ||
      eventText.includes("0 hp") ||
      eventText.includes("drops to zero") ||
      eventText.includes("dropped to zero") ||
      eventText.includes("dead") ||
      eventText.includes("defeated") ||
      eventText.includes("unconscious");

    if (mentionsUnit && isDeathEvent) {
      return event.round;
    }
  }

  return null;
}

function getLastKnownPositionForUnit(
  unit: UnitState,
  timelineEvents: CombatEvent[] | undefined,
  initialFrame: ReplayFrame | null,
): GridPosition | null {
  const events = timelineEvents ?? [];

  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];

    if (event.actorId !== unit.id || !event.movementDetails) {
      continue;
    }

    const path = event.movementDetails.path;
    const pathEnd = path && path.length > 0 ? path[path.length - 1] : null;
    const end = event.movementDetails.end ?? pathEnd;

    if (end) {
      return end;
    }
  }

  return unit.position ?? initialFrame?.state.units[unit.id]?.position ?? null;
}

function getRosterHpText(unit: UnitState, defeated: boolean): string {
  if (defeated && !isUnitDefeated(unit)) {
    const maxHp = getUnitMaxHp(unit);
    return maxHp === null ? "0/-" : `0/${maxHp}`;
  }

  return getUnitHpText(unit);
}

function getActiveUnitIdFromFrame(frame: ReplayFrame | null): string | null {
  const candidate = frame as
    | (ReplayFrame & {
        activeUnitId?: string | null;
        state: ReplayFrame["state"] & { activeCombatantId?: string | null };
      })
    | null;

  return (
    candidate?.activeCombatantId ??
    candidate?.state?.activeCombatantId ??
    candidate?.activeUnitId ??
    null
  );
}

function getInitiativeQueue(
  orderedUnits: UnitState[],
  currentFrame: ReplayFrame | null,
  initialFrame: ReplayFrame | null,
): UnitState[] {
  const initiativeOrder =
    currentFrame?.state.initiativeOrder ??
    initialFrame?.state.initiativeOrder ??
    orderedUnits.map((unit) => unit.id);
  const unitMap = new Map(orderedUnits.map((unit) => [unit.id, unit]));

  return initiativeOrder
    .map((id) => unitMap.get(id))
    .filter((unit): unit is UnitState => Boolean(unit));
}

function getBfsReachableCells(
  start: GridPosition,
  maxSteps: number,
  blocked: Set<string>,
): GridPosition[] {
  const queue: { position: GridPosition; distance: number }[] = [
    { position: start, distance: 0 },
  ];
  const visited = new Set<string>([positionKey(start)]);
  const reachable: GridPosition[] = [];

  while (queue.length > 0) {
    const current = queue.shift()!;

    if (current.distance > 0) {
      reachable.push(current.position);
    }

    if (current.distance >= maxSteps) {
      continue;
    }

    const neighbors: GridPosition[] = [
      { x: current.position.x + 1, y: current.position.y },
      { x: current.position.x - 1, y: current.position.y },
      { x: current.position.x, y: current.position.y + 1 },
      { x: current.position.x, y: current.position.y - 1 },
    ];

    for (const next of neighbors) {
      const key = positionKey(next);

      if (
        next.x < 1 ||
        next.x > GRID_SIZE ||
        next.y < 1 ||
        next.y > GRID_SIZE
      ) {
        continue;
      }

      if (visited.has(key) || blocked.has(key)) {
        continue;
      }

      visited.add(key);
      queue.push({
        position: next,
        distance: current.distance + 1,
      });
    }
  }

  return reachable;
}

type ActionAnimationType = "fireball" | "buff" | "attack" | "move" | null;
type FireballEffect = {
  center: { x: number; y: number };
  radiusSquares: number;
};
type TimedTargetEffect = {
  targetIds: Set<string>;
  delayMs: number;
};
type HideSmokeEffect = {
  center: { x: number; y: number };
  delayMs: number;
  key: string;
};
type HealingHeartEffect = {
  center: { x: number; y: number };
  delayMs: number;
  key: string;
};
type IceBreathConeEffect = {
  origin: { x: number; y: number };
  points: string;
  streaks: Array<{ x1: number; y1: number; x2: number; y2: number }>;
  delayMs: number;
  key: string;
};
type MovementAnimation = {
  key: string;
  unit: BoardUnit;
  keyTimes: string;
  xValues: string;
  yValues: string;
  width: number;
  height: number;
  effectCenter: { x: number; y: number } | null;
};
type ReplayAnimationTiming = {
  movements: MovementAnimation[];
  effectDelayMs: number;
  effectDurationMs: number;
  frameDurationMs: number;
};

const FIREBALL_ANIMATION_TERMS = [
  "fireball",
  "fire breath",
  "burning",
  "explosion",
];
const BUFF_ANIMATION_TERMS = [
  "bless",
  "buff",
  "haste",
  "action surge",
  "healing",
  "heal",
  "lay on hands",
  "aid",
];

function eventIncludesAny(event: CombatEvent, terms: string[]): boolean {
  const eventText = [
    event.textSummary,
    String(event.resolvedTotals.spellId ?? ""),
    event.damageDetails?.weaponId ?? "",
  ]
    .join(" ")
    .toLowerCase();

  return terms.some((term) => eventText.includes(term));
}

function eventMatchesAnimationType(
  event: CombatEvent,
  animationType: Exclude<ActionAnimationType, null>,
): boolean {
  if (animationType === "fireball") {
    return eventIncludesAny(event, FIREBALL_ANIMATION_TERMS);
  }

  if (animationType === "buff") {
    return (
      event.eventType === "heal" ||
      eventIncludesAny(event, BUFF_ANIMATION_TERMS)
    );
  }

  return event.eventType === animationType;
}

function getActionAnimationType(events: CombatEvent[]): ActionAnimationType {
  if (events.some((event) => eventMatchesAnimationType(event, "fireball"))) {
    return "fireball";
  }

  if (events.some((event) => eventMatchesAnimationType(event, "buff"))) {
    return "buff";
  }

  if (events.some((event) => event.eventType === "attack")) {
    return "attack";
  }

  if (events.some((event) => event.eventType === "move")) {
    return "move";
  }

  return null;
}

function getActionAnimationEvent(
  events: CombatEvent[],
  animationType: ActionAnimationType,
): CombatEvent | null {
  if (!animationType) {
    return null;
  }

  if (animationType === "fireball") {
    return events.find((event) => eventMatchesAnimationType(event, animationType)) ?? null;
  }

  return (
    [...events]
      .reverse()
      .find((event) => eventMatchesAnimationType(event, animationType)) ?? null
  );
}

function getNumberEventField(
  event: CombatEvent,
  fieldName: string,
): number | null {
  const value = event.resolvedTotals[fieldName];
  return typeof value === "number" ? value : null;
}

function getStringEventField(
  event: CombatEvent,
  fieldName: string,
): string | null {
  const value = event.resolvedTotals[fieldName];
  return typeof value === "string" ? value : null;
}

function getFireballEffect(events: CombatEvent[]): FireballEffect | null {
  const fireballEvent = events.find((event) =>
    eventMatchesAnimationType(event, "fireball"),
  );

  if (!fireballEvent) {
    return null;
  }

  const centerX = getNumberEventField(fireballEvent, "centerX");
  const centerY = getNumberEventField(fireballEvent, "centerY");

  if (centerX === null || centerY === null) {
    return null;
  }

  return {
    center: getBoardPoint({ x: centerX, y: centerY }),
    radiusSquares: getNumberEventField(fireballEvent, "radiusSquares") ?? 4,
  };
}

function getMovementEvents(events: CombatEvent[]): CombatEvent[] {
  return events.filter(
    (event) =>
      event.eventType === "move" &&
      (event.movementDetails?.path?.length ?? 0) > 1,
  );
}

function getEventWeight(event: CombatEvent): number {
  if (event.eventType === "move") {
    return 1.8;
  }

  if (event.eventType === "turn_start" || event.eventType === "effect_expired") {
    return 0.3;
  }

  if (event.eventType === "saving_throw") {
    return 0.45;
  }

  if (event.eventType === "phase_change" || event.eventType === "heal") {
    return 0.9;
  }

  if (event.eventType === "skip") {
    return 0.55;
  }

  return 1;
}

function getEventTimeline(
  events: CombatEvent[],
): Array<{ event: CombatEvent; startRatio: number; endRatio: number }> {
  const weights = events.map(getEventWeight);
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0) || 1;
  let elapsedWeight = 0;

  return events.map((event, index) => {
    const startRatio = elapsedWeight / totalWeight;
    elapsedWeight += weights[index];

    return {
      event,
      startRatio,
      endRatio: elapsedWeight / totalWeight,
    };
  });
}

function getEventTimelineEntry(
  timeline: Array<{ event: CombatEvent; startRatio: number; endRatio: number }>,
  events: CombatEvent[],
  targetEvent: CombatEvent | null,
): { startRatio: number; endRatio: number } | null {
  if (!targetEvent) {
    return null;
  }

  const index = events.indexOf(targetEvent);
  return index >= 0 ? timeline[index] : null;
}

function getEventDelayMs(
  events: CombatEvent[],
  targetEvent: CombatEvent,
  frameDurationMs: number,
): number {
  const timeline = getEventTimeline(events);
  const entry = getEventTimelineEntry(timeline, events, targetEvent);

  return Math.round(frameDurationMs * (entry?.startRatio ?? 0));
}

function getSpellId(event: CombatEvent): string {
  const spellId = event.resolvedTotals.spellId;

  return typeof spellId === "string" ? spellId.toLowerCase() : "";
}

function eventMatchesSpell(
  event: CombatEvent,
  spellId: string,
  displayName: string,
): boolean {
  const text = event.textSummary.toLowerCase();

  return (
    getSpellId(event) === spellId ||
    text.includes(`casts ${displayName.toLowerCase()}`)
  );
}

function getTimedSpellTargetEffect(
  events: CombatEvent[],
  spellId: string,
  displayName: string,
  frameDurationMs: number,
): TimedTargetEffect | null {
  const event = events.find((candidate) =>
    eventMatchesSpell(candidate, spellId, displayName),
  );

  if (!event || event.targetIds.length === 0) {
    return null;
  }

  return {
    targetIds: new Set(event.targetIds),
    delayMs: getEventDelayMs(events, event, frameDurationMs),
  };
}

function isShieldReactionEvent(event: CombatEvent, units: BoardUnit[]): boolean {
  const actor = units.find((candidate) => candidate.id === event.actorId);
  const actorRole = actor?.combatRole?.toLowerCase() ?? "";
  const actorName = actor?.templateName?.toLowerCase() ?? "";
  const eventText = event.textSummary.toLowerCase();
  const isWizard =
    actorRole.includes("wizard") ||
    actorName.includes("wizard") ||
    event.actorId === "F4";

  return (
    event.eventType === "phase_change" &&
    isWizard &&
    (getSpellId(event) === "shield" || eventText.includes("casts shield"))
  );
}

function getShieldReactionEffect(
  events: CombatEvent[],
  units: BoardUnit[],
  frameDurationMs: number,
): TimedTargetEffect | null {
  const event = events.find((candidate) =>
    isShieldReactionEvent(candidate, units),
  );

  if (!event) {
    return null;
  }

  return {
    targetIds: new Set([event.actorId]),
    delayMs: getEventDelayMs(events, event, frameDurationMs),
  };
}

function formatSvgNumber(value: number): string {
  return Number(value.toFixed(4)).toString();
}

function addAnimationKey(
  keys: Array<{ time: number; x: number; y: number }>,
  time: number,
  point: { x: number; y: number },
): void {
  const clampedTime = Math.min(1, Math.max(0, time));
  const lastKey = keys[keys.length - 1];

  if (lastKey && Math.abs(lastKey.time - clampedTime) < 0.0005) {
    lastKey.x = point.x;
    lastKey.y = point.y;
    return;
  }

  keys.push({
    time: clampedTime,
    x: point.x,
    y: point.y,
  });
}

function getInterpolatedAnimationPoint(
  keys: Array<{ time: number; x: number; y: number }>,
  ratio: number,
): { x: number; y: number } | null {
  if (keys.length === 0) {
    return null;
  }

  const clampedRatio = Math.min(1, Math.max(0, ratio));

  for (let index = 0; index < keys.length - 1; index += 1) {
    const current = keys[index];
    const next = keys[index + 1];

    if (clampedRatio >= current.time && clampedRatio <= next.time) {
      if (Math.abs(next.time - current.time) < 0.0005) {
        return { x: next.x, y: next.y };
      }

      const segmentRatio = (clampedRatio - current.time) / (next.time - current.time);

      return {
        x: current.x + (next.x - current.x) * segmentRatio,
        y: current.y + (next.y - current.y) * segmentRatio,
      };
    }
  }

  const finalKey = keys[keys.length - 1];
  return { x: finalKey.x, y: finalKey.y };
}

function getReplayAnimationTiming(params: {
  events: CombatEvent[];
  units: BoardUnit[];
  actionEvent: CombatEvent | null;
  hasActionEffect: boolean;
  frameDurationMs?: number;
}): ReplayAnimationTiming {
  const frameDurationMs = params.frameDurationMs ?? 4864;
  const timeline = getEventTimeline(params.events);
  const movementEvents = getMovementEvents(params.events);
  const actionTimeline = getEventTimelineEntry(timeline, params.events, params.actionEvent);
  const isFireballEffect =
    params.actionEvent && eventMatchesAnimationType(params.actionEvent, "fireball");
  const effectStartRatio = params.hasActionEffect
    ? isFireballEffect
      ? Math.max(0.18, actionTimeline?.startRatio ?? 0.18)
      : actionTimeline?.startRatio ?? 0.5
    : 0;
  const effectDelayMs = params.hasActionEffect
    ? Math.round(frameDurationMs * effectStartRatio)
    : 0;
  const effectDurationMs = params.hasActionEffect
    ? Math.max(400, frameDurationMs - effectDelayMs)
    : 0;
  const movements: MovementAnimation[] = [];

  for (const firstMovementEvent of movementEvents) {
    if (movements.some((candidate) => candidate.unit.id === firstMovementEvent.actorId)) {
      continue;
    }

    const actorMovementEvents = movementEvents.filter(
      (event) => event.actorId === firstMovementEvent.actorId,
    );
    const unit = params.units.find(
      (candidate) => candidate.id === firstMovementEvent.actorId,
    );

    if (unit) {
      const footprint = unit.footprint ?? SINGLE_SQUARE_FOOTPRINT;
      const dimensions = getFootprintDimensions(footprint);
      const keys: Array<{ time: number; x: number; y: number }> = [];
      const toTopLeftPoint = (position: GridPosition): { x: number; y: number } => {
        const center = getBoardPoint(position, footprint);

        return {
          x: center.x - dimensions.width / 2,
          y: center.y - dimensions.height / 2,
        };
      };
      let currentPoint = toTopLeftPoint(firstMovementEvent.movementDetails!.path![0]);

      addAnimationKey(keys, 0, currentPoint);

      for (const movementEvent of actorMovementEvents) {
        const movementTimeline = getEventTimelineEntry(timeline, params.events, movementEvent);
        const path = movementEvent.movementDetails?.path;

        if (!movementTimeline || !path || path.length < 2) {
          continue;
        }

        const pathPoints = path.map(toTopLeftPoint);
        addAnimationKey(keys, movementTimeline.startRatio, currentPoint);

        for (let index = 1; index < pathPoints.length; index += 1) {
          const segmentRatio = index / (pathPoints.length - 1);
          const pointTime =
            movementTimeline.startRatio +
            (movementTimeline.endRatio - movementTimeline.startRatio) * segmentRatio;

          addAnimationKey(keys, pointTime, pathPoints[index]);
        }

        currentPoint = pathPoints[pathPoints.length - 1];
      }

      addAnimationKey(keys, 1, currentPoint);

      if (keys.length > 1) {
        const effectPoint = params.hasActionEffect
          ? getInterpolatedAnimationPoint(keys, effectStartRatio)
          : null;

        movements.push({
          key: `${unit.id}-${keys.map((key) => `${formatSvgNumber(key.time)}:${formatSvgNumber(key.x)},${formatSvgNumber(key.y)}`).join("|")}`,
          unit,
          keyTimes: keys.map((key) => formatSvgNumber(key.time)).join(";"),
          xValues: keys.map((key) => formatSvgNumber(key.x)).join(";"),
          yValues: keys.map((key) => formatSvgNumber(key.y)).join(";"),
          width: dimensions.width,
          height: dimensions.height,
          effectCenter: effectPoint
            ? {
                x: effectPoint.x + dimensions.width / 2,
                y: effectPoint.y + dimensions.height / 2,
              }
            : null,
        });
      }
    }
  }

  return {
    movements,
    effectDelayMs,
    effectDurationMs,
    frameDurationMs,
  };
}

function getUnitBoardPoint(
  units: BoardUnit[],
  unitId: string | undefined,
): { x: number; y: number } | null {
  const unit = units.find((candidate) => candidate.id === unitId);

  return unit?.position
    ? getBoardPoint(unit.position, unit.footprint ?? SINGLE_SQUARE_FOOTPRINT)
    : null;
}

function getMovementCssAnimationName(
  frameIndex: number | undefined,
  movementIndex: number,
): string {
  return `movement-token-${frameIndex ?? "static"}-${movementIndex}`;
}

function getMovementCssKeyframes(
  animationName: string,
  movement: MovementAnimation,
): string {
  const times = movement.keyTimes.split(";").map(Number);
  const xValues = movement.xValues.split(";").map(Number);
  const yValues = movement.yValues.split(";").map(Number);

  return `@keyframes ${animationName} { ${times
    .map((time, index) => {
      const percent = formatSvgNumber(time * 100);
      const left = formatSvgNumber((xValues[index] / GRID_SIZE) * 100);
      const top = formatSvgNumber((yValues[index] / GRID_SIZE) * 100);

      return `${percent}% { left: ${left}%; top: ${top}%; }`;
    })
    .join(" ")} }`;
}

function getMovingTokenAnimationStyle(params: {
  movement: MovementAnimation;
  animationName: string;
  frameDurationMs: number;
  blessEffect: TimedTargetEffect | null;
  hasteEffect: TimedTargetEffect | null;
  shieldEffect: TimedTargetEffect | null;
}): string {
  const animations = [
    `${params.animationName} ${params.frameDurationMs}ms linear 0ms both`,
  ];

  if (params.blessEffect?.targetIds.has(params.movement.unit.id)) {
    animations.push(
      `blessGoldFlash 1.5s ease-out ${params.blessEffect.delayMs}ms both`,
    );
  }

  if (params.hasteEffect?.targetIds.has(params.movement.unit.id)) {
    animations.push(
      `hasteVibrate 1.5s linear ${params.hasteEffect.delayMs}ms both`,
    );
  }

  if (params.shieldEffect?.targetIds.has(params.movement.unit.id)) {
    animations.push(
      `shieldBlueGlow 1.5s ease-out ${params.shieldEffect.delayMs}ms both`,
    );
  }

  return animations.join(", ");
}

function isRogueHideAttempt(event: CombatEvent, units: BoardUnit[]): boolean {
  const actor = units.find((candidate) => candidate.id === event.actorId);
  const actorRole = actor?.combatRole?.toLowerCase() ?? "";
  const actorName = actor?.templateName?.toLowerCase() ?? "";
  const isRogue =
    actorRole.includes("rogue") ||
    actorName.includes("rogue") ||
    event.actorId === "F3";

  return (
    event.eventType === "phase_change" &&
    isRogue &&
    event.textSummary.toLowerCase().includes("hide")
  );
}

function getHideSmokeEffects(
  events: CombatEvent[],
  units: BoardUnit[],
  frameDurationMs: number,
): HideSmokeEffect[] {
  return events.flatMap((event, index) => {
    if (!isRogueHideAttempt(event, units)) {
      return [];
    }

    const center = getUnitBoardPoint(units, event.actorId);

    if (!center) {
      return [];
    }

    return [
      {
        center,
        delayMs: getEventDelayMs(events, event, frameDurationMs),
        key: `${event.actorId}-${index}-${formatSvgNumber(center.x)}-${formatSvgNumber(center.y)}`,
      },
    ];
  });
}

function isPaladinHealEvent(event: CombatEvent, units: BoardUnit[]): boolean {
  const actor = units.find((candidate) => candidate.id === event.actorId);
  const actorRole = actor?.combatRole?.toLowerCase() ?? "";
  const actorName = actor?.templateName?.toLowerCase() ?? "";
  const isPaladin =
    actorRole.includes("paladin") ||
    actorName.includes("paladin") ||
    event.actorId === "F2";

  return event.eventType === "heal" && isPaladin && event.targetIds.length > 0;
}

function getHealingHeartEffects(
  events: CombatEvent[],
  units: BoardUnit[],
  frameDurationMs: number,
): HealingHeartEffect[] {
  return events.flatMap((event, eventIndex) => {
    if (!isPaladinHealEvent(event, units)) {
      return [];
    }

    return event.targetIds.flatMap((targetId, targetIndex) => {
      const center = getUnitBoardPointAtEvent(events, units, targetId, eventIndex);

      if (!center) {
        return [];
      }

      return [
        {
          center,
          delayMs: getEventDelayMs(events, event, frameDurationMs),
          key: `${event.actorId}-${targetId}-${eventIndex}-${targetIndex}`,
        },
      ];
    });
  });
}

function getEventStartPosition(event: CombatEvent): GridPosition | null {
  const path = event.movementDetails?.path;

  return (
    event.movementDetails?.start ??
    (path && path.length > 0 ? path[0] : null)
  );
}

function getEventEndPosition(event: CombatEvent): GridPosition | null {
  const path = event.movementDetails?.path;

  return (
    event.movementDetails?.end ??
    (path && path.length > 0 ? path[path.length - 1] : null)
  );
}

function getUnitBoardPointAtEvent(
  events: CombatEvent[],
  units: BoardUnit[],
  unitId: string,
  eventIndex: number,
): { x: number; y: number } | null {
  const positions = new Map<string, GridPosition>();
  const seededMovementStarts = new Set<string>();

  for (const unit of units) {
    if (unit.position) {
      positions.set(unit.id, unit.position);
    }
  }

  for (const event of events) {
    const start = getEventStartPosition(event);

    if (start && !seededMovementStarts.has(event.actorId)) {
      positions.set(event.actorId, start);
      seededMovementStarts.add(event.actorId);
    }
  }

  for (const event of events.slice(0, eventIndex)) {
    const end = getEventEndPosition(event);

    if (end) {
      positions.set(event.actorId, end);
    }
  }

  const unit = units.find((candidate) => candidate.id === unitId);
  const position = positions.get(unitId);

  return position
    ? getBoardPoint(position, unit?.footprint ?? SINGLE_SQUARE_FOOTPRINT)
    : null;
}

function parseGridPositionText(value: string | null): GridPosition | null {
  const match = value?.match(/\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?/);

  if (!match) {
    return null;
  }

  return {
    x: Number(match[1]),
    y: Number(match[2]),
  };
}

function getDirectionVector(direction: string): { x: number; y: number } {
  const normalized = direction.toLowerCase();
  const x = normalized.includes("w") ? -1 : normalized.includes("e") ? 1 : 0;
  const y = normalized.includes("n") ? -1 : normalized.includes("s") ? 1 : 0;
  const length = Math.hypot(x, y) || 1;

  return {
    x: x / length,
    y: y / length,
  };
}

function getIceBreathConeGeometry(
  origin: { x: number; y: number },
  direction: string,
): Pick<IceBreathConeEffect, "points" | "streaks"> {
  const vector = getDirectionVector(direction);
  const perpendicular = { x: -vector.y, y: vector.x };
  const length = 8.2;
  const halfWidth = 4.4;
  const end = {
    x: origin.x + vector.x * length,
    y: origin.y + vector.y * length,
  };
  const leftEdge = {
    x: end.x + perpendicular.x * halfWidth,
    y: end.y + perpendicular.y * halfWidth,
  };
  const rightEdge = {
    x: end.x - perpendicular.x * halfWidth,
    y: end.y - perpendicular.y * halfWidth,
  };
  const points = [origin, leftEdge, rightEdge]
    .map((point) => `${formatSvgNumber(point.x)},${formatSvgNumber(point.y)}`)
    .join(" ");
  const spreadFractions = [-0.72, -0.36, 0, 0.36, 0.72];
  const streaks = spreadFractions.map((spread, index) => {
    const reach = index === 2 ? 0.92 : 0.78;

    return {
      x1: origin.x + vector.x * 0.35,
      y1: origin.y + vector.y * 0.35,
      x2: origin.x + vector.x * length * reach + perpendicular.x * halfWidth * spread,
      y2: origin.y + vector.y * length * reach + perpendicular.y * halfWidth * spread,
    };
  });

  return { points, streaks };
}

function isIceBreathConeEvent(event: CombatEvent): boolean {
  return (
    event.eventType === "phase_change" &&
    event.resolvedTotals.specialAction === "cold_breath" &&
    Boolean(getStringEventField(event, "origin")) &&
    Boolean(getStringEventField(event, "direction"))
  );
}

function getIceBreathConeEffects(
  events: CombatEvent[],
  frameDurationMs: number,
): IceBreathConeEffect[] {
  return events.flatMap((event, index) => {
    if (!isIceBreathConeEvent(event)) {
      return [];
    }

    const originPosition = parseGridPositionText(getStringEventField(event, "origin"));
    const direction = getStringEventField(event, "direction");

    if (!originPosition || !direction) {
      return [];
    }

    const origin = getBoardPoint(originPosition);
    const geometry = getIceBreathConeGeometry(origin, direction);

    return [
      {
        ...geometry,
        origin,
        delayMs: getEventDelayMs(events, event, frameDurationMs),
        key: `${event.actorId}-cold-breath-${index}-${direction}-${formatSvgNumber(origin.x)}-${formatSvgNumber(origin.y)}`,
      },
    ];
  });
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
  useBattlefieldBackground?: boolean;
  interactionMode?: GridInteractionMode;
  showReplayGrid?: boolean;
  currentFrame?: ReplayFrame | null;
  replayFrameDurationMs?: number;
}) {
  const placementMode = Boolean(props.onCellClick);
  const isSetupMode = props.interactionMode === "setup";
  const isMovementPreviewMode = props.interactionMode === "movement";
  const isAttackPreviewMode = props.interactionMode === "attack";
  const isReplayMode =
    props.interactionMode === "replay" ||
    (!isSetupMode && !isMovementPreviewMode && !isAttackPreviewMode);
  const occupiedSquares = new Map<
    string,
    { unit: BoardUnit; isAnchor: boolean }
  >();
  const terrainSquares = new Map<
    string,
    { feature: TerrainFeature; isAnchor: boolean }
  >();

  for (const unit of props.units) {
    if (!unit.position) {
      continue;
    }

    if (isUnitDefeated(unit) && !isDeadWhiteDragonUnit(unit)) {
      continue;
    }

    for (const occupiedSquare of getOccupiedSquaresForPosition(
      unit.position,
      unit.footprint ?? SINGLE_SQUARE_FOOTPRINT,
    )) {
      occupiedSquares.set(`${occupiedSquare.x},${occupiedSquare.y}`, {
        unit,
        isAnchor:
          occupiedSquare.x === unit.position.x &&
          occupiedSquare.y === unit.position.y,
      });
    }
  }

  for (const feature of props.terrainFeatures) {
    for (const occupiedSquare of getOccupiedSquaresForPosition(
      feature.position,
      feature.footprint,
    )) {
      terrainSquares.set(`${occupiedSquare.x},${occupiedSquare.y}`, {
        feature,
        isAnchor:
          occupiedSquare.x === feature.position.x &&
          occupiedSquare.y === feature.position.y,
      });
    }
  }
  const selectedUnit = props.selectedPlacementUnitId
    ? props.units.find((unit) => unit.id === props.selectedPlacementUnitId)
    : undefined;
  const blockedSquares = new Set<string>();

  for (const [key, occupant] of occupiedSquares.entries()) {
    if (occupant.unit.id !== selectedUnit?.id) {
      blockedSquares.add(key);
    }
  }

  for (const key of terrainSquares.keys()) {
    blockedSquares.add(key);
  }

  const movementRestrictionActive =
    isMovementPreviewMode && selectedUnit?.position != null;
  const reachableSquares = movementRestrictionActive && selectedUnit?.position
    ? getBfsReachableCells(
        selectedUnit.position,
        getMoveRangeForUnit(selectedUnit),
        blockedSquares,
      )
    : [];
  const reachableSquareKeys = new Set(reachableSquares.map(positionKey));
  const attackRange = selectedUnit ? getAttackRangeForUnit(selectedUnit) : 0;
  const clearAttackTargetKeys = new Set<string>();
  const coveredAttackTargetKeys = new Set<string>();

  if (isAttackPreviewMode && selectedUnit?.position) {
    for (const [key, occupiedSquare] of occupiedSquares.entries()) {
      const occupant = occupiedSquare.unit;

      if (
        occupant.id === selectedUnit.id ||
        occupant.faction === selectedUnit.faction
      ) {
        continue;
      }

      const targetPosition = parsePositionKey(key);

      if (
        !isWithinAttackRange(
          selectedUnit.position,
          targetPosition,
          attackRange,
        )
      ) {
        continue;
      }

      const coverStatus = getCoverStatus(
        selectedUnit.position,
        targetPosition,
        terrainSquares,
        occupiedSquares,
        selectedUnit.id,
        occupant.id,
      );

      if (coverStatus === "clear") {
        clearAttackTargetKeys.add(key);
      } else {
        coveredAttackTargetKeys.add(key);
      }
    }
  }
  const pathIndex = new Map(
    props.highlightedPath.length > 1
      ? props.highlightedPath.map((position, index) => [
          positionKey(position),
          index,
        ])
      : [],
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
  const frameReplayEvents = props.currentFrame?.events ?? [];
  const replayMovementLinePoints = getMovementEvents(frameReplayEvents).map(
    (event) =>
      event.movementDetails!.path!.map((position) => {
        const point = getBoardPoint(position);
        return `${point.x},${point.y}`;
      }),
  );
  const movementLinePointSets =
    replayMovementLinePoints.length > 0
      ? replayMovementLinePoints
      : movementPoints.length > 1
        ? [movementPoints]
        : [];
  const attackFrom = props.attackLine
    ? getBoardPoint(props.attackLine.from, props.attackLine.fromFootprint)
    : null;
  const attackTo = props.attackLine
    ? getBoardPoint(props.attackLine.to, props.attackLine.toFootprint)
    : null;
  const activeReplayEvents = getActiveReplayEvents(props.currentFrame ?? null);
  const animationTimelineEvents =
    frameReplayEvents.length > 0 ? frameReplayEvents : activeReplayEvents;
  const frameDurationMs = props.replayFrameDurationMs ?? 4864;
  const blessEffect = getTimedSpellTargetEffect(
    animationTimelineEvents,
    "bless",
    "Bless",
    frameDurationMs,
  );
  const hasteEffect = getTimedSpellTargetEffect(
    animationTimelineEvents,
    "haste",
    "Haste",
    frameDurationMs,
  );
  const shieldEffect = getShieldReactionEffect(
    animationTimelineEvents,
    props.units,
    frameDurationMs,
  );
  const hideSmokeEffects = getHideSmokeEffects(
    animationTimelineEvents,
    props.units,
    frameDurationMs,
  );
  const healingHeartEffects = getHealingHeartEffects(
    animationTimelineEvents,
    props.units,
    frameDurationMs,
  );
  const iceBreathConeEffects = getIceBreathConeEffects(
    animationTimelineEvents,
    frameDurationMs,
  );
  const actionAnimationType = getActionAnimationType(activeReplayEvents);
  const actionAnimationEvent = getActionAnimationEvent(
    activeReplayEvents,
    actionAnimationType,
  );
  const attackLineEvent =
    props.attackLine?.eventIndex !== undefined
      ? animationTimelineEvents[props.attackLine.eventIndex] ?? null
      : null;
  const replayEffectEvent =
    attackLineEvent ?? (actionAnimationType === "move" ? null : actionAnimationEvent);
  const actionSource = getUnitBoardPoint(
    props.units,
    actionAnimationEvent?.actorId,
  );
  const actionTarget = getUnitBoardPoint(
    props.units,
    actionAnimationEvent?.targetIds[0],
  );
  const fireballEffect =
    actionAnimationType === "fireball"
      ? getFireballEffect(activeReplayEvents)
      : null;
  const buffPoint =
    actionAnimationType === "buff" && !blessEffect && !hasteEffect
      ? actionTarget ?? actionSource
      : null;
  const hasActionEffect = Boolean((attackFrom && attackTo) || fireballEffect || buffPoint);
  const replayAnimationTiming = getReplayAnimationTiming({
    events: animationTimelineEvents,
    units: props.units,
    actionEvent: replayEffectEvent,
    hasActionEffect,
    frameDurationMs: props.replayFrameDurationMs,
  });
  const replayEffectStyle = {
    "--replay-frame-duration": `${replayAnimationTiming.frameDurationMs}ms`,
    "--replay-effect-delay": `${replayAnimationTiming.effectDelayMs}ms`,
    "--replay-effect-duration": `${replayAnimationTiming.effectDurationMs}ms`,
  } as CSSProperties;
  const movingTokenKeyframes = replayAnimationTiming.movements
    .map((movement, index) =>
      getMovementCssKeyframes(
        getMovementCssAnimationName(props.currentFrame?.index, index),
        movement,
      ),
    )
    .join("\n");
  const attackMovement = props.attackLine
    ? replayAnimationTiming.movements.find(
        (movement) => movement.unit.id === props.attackLine?.actorId,
      )
    : undefined;
  const visualAttackFrom =
    props.attackLine &&
    attackFrom &&
    attackMovement?.effectCenter
      ? attackMovement.effectCenter
      : attackFrom;
  const animationKey = [
    props.currentFrame?.index ?? "static",
    actionAnimationType ?? "none",
    props.activeUnitId ?? "none",
    props.attackLine?.eventIndex ?? "no-attack-line-event",
    movementLinePointSets.map((points) => points.join("|")).join("||"),
    replayAnimationTiming.movements.map((movement) => movement.key).join("||"),
    visualAttackFrom ? `${visualAttackFrom.x},${visualAttackFrom.y}` : "",
    attackTo ? `${attackTo.x},${attackTo.y}` : "",
    blessEffect ? [...blessEffect.targetIds].join(",") : "",
    hasteEffect ? [...hasteEffect.targetIds].join(",") : "",
    shieldEffect ? [...shieldEffect.targetIds].join(",") : "",
    hideSmokeEffects.map((effect) => effect.key).join("|"),
    healingHeartEffects.map((effect) => effect.key).join("|"),
    iceBreathConeEffects.map((effect) => effect.key).join("|"),
  ].join("-");

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
      <div
        className={`battle-map-frame ${
          props.useBattlefieldBackground ? "battlefield-background" : ""
        } ${fireballEffect || iceBreathConeEffects.length > 0 ? "spell-effect-visible" : ""}`}
      >
        <div
          className={`board-grid board-play-area ${placementMode ? "placement-mode" : ""} ${
            props.showReplayGrid ? "replay-grid" : ""
          } ${fireballEffect || iceBreathConeEffects.length > 0 ? "spell-effect-visible" : ""}`}
          role={placementMode ? "grid" : "img"}
          aria-label={props.ariaLabel}
        >
          {cells.map((cell) => {
            const key = positionKey(cell);
            const isFirstCol = cell.x === 1;
            const isFirstRow = cell.y === GRID_SIZE;
            const occupiedSquare = occupiedSquares.get(key);
            const occupant = occupiedSquare?.unit;
            const isAnchorSquare = occupiedSquare?.isAnchor ?? false;
            const terrainSquare = terrainSquares.get(key);
            const terrainFeature = terrainSquare?.feature ?? null;
            const isTerrainAnchor = terrainSquare?.isAnchor ?? false;
            const isBlockingTerrain = terrainFeature
              ? terrainBlocksPlacement(terrainFeature)
              : false;
            const pathStep = pathIndex.get(key);
            const isReachable = reachableSquareKeys.has(key);
            const isIllegalMoveTarget =
              movementRestrictionActive && !occupant && !isReachable;
            const isInAttackRange =
              isAttackPreviewMode &&
              selectedUnit?.position != null &&
              key !== positionKey(selectedUnit.position) &&
              isWithinAttackRange(selectedUnit.position, cell, attackRange);
            const isClearAttackTarget = clearAttackTargetKeys.has(key);
            const isCoveredAttackTarget = coveredAttackTargetKeys.has(key);
            const isActiveUnit = occupant?.id === props.activeUnitId;
            const isSelectedPlacementUnit =
              occupant?.id === props.selectedPlacementUnitId;
            const isDefeatedOccupant = isUnitDefeated(occupant);
            const isDeadWhiteDragonOccupant = isDeadWhiteDragonUnit(occupant);
            const isMovingReplayUnit =
              occupant
                ? replayAnimationTiming.movements.some(
                    (movement) => movement.unit.id === occupant.id,
                  )
                : false;
            const isBlessTarget =
              occupant ? blessEffect?.targetIds.has(occupant.id) ?? false : false;
            const isHasteTarget =
              occupant ? hasteEffect?.targetIds.has(occupant.id) ?? false : false;
            const isShieldTarget =
              occupant ? shieldEffect?.targetIds.has(occupant.id) ?? false : false;
            const isAttackOrigin =
              props.attackLine &&
              key === `${props.attackLine.from.x},${props.attackLine.from.y}`;
            const isAttackTarget =
              props.attackLine &&
              key === `${props.attackLine.to.x},${props.attackLine.to.y}`;
            const cellClasses = [
              "board-cell",
              placementMode ? "interactive" : "",
              occupant ? occupant.faction : "",
              terrainFeature ? `terrain ${terrainFeature.kind}` : "",
              placementMode && isBlockingTerrain ? "blocked-terrain" : "",
              pathStep !== undefined ? "path" : "",
              isActiveUnit ? "active-unit" : "",
              isAttackOrigin ? "attack-origin" : "",
              isAttackTarget ? "attack-target" : "",
              isSelectedPlacementUnit ? "selected-placement-unit" : "",
              isAnchorSquare ? "unit-anchor" : "",
              isDefeatedOccupant ? "defeated-map-unit" : "",
              isDeadWhiteDragonOccupant ? "dead-dragon-map-unit" : "",
              isReachable ? "reachable" : "",
              isIllegalMoveTarget ? "illegal-move" : "",
              isInAttackRange ? "attack-range" : "",
              isClearAttackTarget ? "attack-target-clear" : "",
              isCoveredAttackTarget ? "attack-target-cover" : "",
              isReplayMode ? "replay-cell" : "",
              isFirstCol ? "first-col" : "",
              isFirstRow ? "first-row" : "",
            ]
              .filter(Boolean)
              .join(" ");
            const cellContents = (
              <>
                <span className="board-coordinate">
                  {cell.x},{cell.y}
                </span>
                {pathStep !== undefined ? (
                  <span className="path-step">{pathStep + 1}</span>
                ) : null}
                {terrainFeature && isTerrainAnchor ? (
                  <span className="terrain-token">
                    {getTerrainToken(terrainFeature)}
                  </span>
                ) : null}
                {occupant && isAnchorSquare ? (
                  <span
                    className={`unit-token ${isActiveUnit ? "active-token" : ""} ${
                      isDefeatedOccupant ? "defeated-token" : ""
                    } ${isDeadWhiteDragonOccupant ? "dead-dragon-token" : ""} ${
                      isMovingReplayUnit ? "moving-token-static" : ""
                    } ${isHasteTarget ? "haste-vibrate-token" : ""
                    }`}
                    style={
                      {
                        ...getUnitTokenStyle(occupant),
                        "--bless-effect-delay": `${blessEffect?.delayMs ?? 0}ms`,
                        "--haste-effect-delay": `${hasteEffect?.delayMs ?? 0}ms`,
                        "--shield-effect-delay": `${shieldEffect?.delayMs ?? 0}ms`,
                      } as CSSProperties
                    }
                  >
                    <img
                      className={`unit-sprite ${isBlessTarget ? "bless-gold-sprite" : ""} ${
                        isShieldTarget ? "shield-blue-sprite" : ""
                      } ${isDeadWhiteDragonOccupant ? "dead-dragon-sprite" : ""}`}
                      src={getUnitSprite(occupant)}
                      alt={occupant.id}
                      onError={(event) => {
                        event.currentTarget.src = "/sprites/enemy.png";
                      }}
                    />
                  </span>
                ) : null}
              </>
            );

            if (placementMode && props.onCellClick) {
              return (
                <button
                  key={key}
                  type="button"
                  className={cellClasses}
                  onClick={() => {
                    const clickedPosition = { x: cell.x, y: cell.y };
                    const clickedOccupantId = occupant?.id ?? null;

                    logBoardCellClick(
                      clickedPosition,
                      clickedOccupantId,
                      terrainFeature,
                    );

                    if ((isBlockingTerrain && !occupant) || isIllegalMoveTarget) {
                      return;
                    }

                    props.onCellClick?.(
                      clickedPosition,
                      clickedOccupantId,
                    );
                  }}
                  aria-label={`Square ${cell.x},${cell.y}${
                    occupant
                      ? ` occupied by ${occupant.id}`
                      : terrainFeature
                        ? ` contains ${getTerrainLabel(terrainFeature)} terrain`
                        : " empty"
                  }`}
                  aria-pressed={isSelectedPlacementUnit}
                  aria-disabled={isBlockingTerrain || isIllegalMoveTarget}
                >
                  {cellContents}
                </button>
              );
            }

            return (
              <div
                key={key}
                className={cellClasses}
                onClick={() =>
                  logBoardCellClick(
                    { x: cell.x, y: cell.y },
                    occupant?.id ?? null,
                    terrainFeature,
                  )
                }
              >
                {cellContents}
              </div>
            );
          })}

          {replayAnimationTiming.movements.length > 0 ? (
            <div
              key={`moving-token-layer-${animationKey}`}
              className="moving-token-layer"
              aria-hidden="true"
            >
              <style>{movingTokenKeyframes}</style>
              {replayAnimationTiming.movements.map((movement, index) => {
                const animationName = getMovementCssAnimationName(
                  props.currentFrame?.index,
                  index,
                );
                const x = Number(movement.xValues.split(";")[0]);
                const y = Number(movement.yValues.split(";")[0]);

                return (
                  <img
                    key={movement.key}
                    className="moving-token-html-sprite"
                    src={getUnitSprite(movement.unit)}
                    alt=""
                    style={
                      {
                        left: `${(x / GRID_SIZE) * 100}%`,
                        top: `${(y / GRID_SIZE) * 100}%`,
                        width: `${(movement.width / GRID_SIZE) * 100}%`,
                        height: `${(movement.height / GRID_SIZE) * 100}%`,
                        animation: getMovingTokenAnimationStyle({
                          movement,
                          animationName,
                          frameDurationMs: replayAnimationTiming.frameDurationMs,
                          blessEffect,
                          hasteEffect,
                          shieldEffect,
                        }),
                      } as CSSProperties
                    }
                    onError={(event) => {
                      event.currentTarget.src = "/sprites/enemy.png";
                    }}
                  />
                );
              })}
            </div>
          ) : null}

          {movementLinePointSets.length > 0 ||
          replayAnimationTiming.movements.length > 0 ||
          (attackFrom && attackTo) ||
          fireballEffect ||
          buffPoint ||
          iceBreathConeEffects.length > 0 ||
          hideSmokeEffects.length > 0 ? (
            <svg
              key={animationKey}
              className={`board-overlay ${
                fireballEffect || iceBreathConeEffects.length > 0
                  ? "spell-effect-visible"
                  : ""
              }`}
              style={replayEffectStyle}
              viewBox={`0 0 ${GRID_SIZE} ${GRID_SIZE}`}
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {movementLinePointSets.map((points, index) => (
                <polyline
                  key={`movement-line-${index}-${points.join("|")}`}
                  className="movement-line animated"
                  points={points.join(" ")}
                />
              ))}
              {iceBreathConeEffects.map((effect) => (
                <g
                  key={effect.key}
                  className="ice-breath-effect"
                  style={
                    {
                      "--ice-breath-delay": `${effect.delayMs}ms`,
                    } as CSSProperties
                  }
                >
                  <polygon className="ice-breath-cone" points={effect.points} />
                  {effect.streaks.map((streak, index) => (
                    <line
                      key={`${effect.key}-streak-${index}`}
                      className="ice-breath-streak"
                      x1={streak.x1}
                      y1={streak.y1}
                      x2={streak.x2}
                      y2={streak.y2}
                    />
                  ))}
                  <circle
                    className="ice-breath-origin"
                    cx={effect.origin.x}
                    cy={effect.origin.y}
                    r="0.32"
                  />
                </g>
              ))}
              {attackFrom && attackTo ? (
                <line
                  className="attack-line animated"
                  x1={visualAttackFrom?.x ?? attackFrom.x}
                  y1={visualAttackFrom?.y ?? attackFrom.y}
                  x2={attackTo.x}
                  y2={attackTo.y}
                />
              ) : null}
              {attackTo ? (
                <circle
                  className="impact-pulse"
                  cx={attackTo.x}
                  cy={attackTo.y}
                  r="0.28"
                />
              ) : null}
              {fireballEffect ? (
                <>
                  <circle
                    className="fireball-area-ring"
                    cx={fireballEffect.center.x}
                    cy={fireballEffect.center.y}
                    r={fireballEffect.radiusSquares}
                  />
                  <image
                    className="fireball-sprite"
                    href="/sprites/fireball.svg"
                    x={fireballEffect.center.x - fireballEffect.radiusSquares}
                    y={fireballEffect.center.y - fireballEffect.radiusSquares}
                    width={fireballEffect.radiusSquares * 2}
                    height={fireballEffect.radiusSquares * 2}
                    preserveAspectRatio="xMidYMid meet"
                  />
                </>
              ) : null}
              {buffPoint ? (
                <circle
                  className="buff-glow"
                  cx={buffPoint.x}
                  cy={buffPoint.y}
                  r="0.45"
                />
              ) : null}
              {hideSmokeEffects.map((effect) => (
                <g
                  key={effect.key}
                  className="hide-smoke-effect"
                  style={
                    {
                      "--hide-smoke-delay": `${effect.delayMs}ms`,
                    } as CSSProperties
                  }
                  transform={`translate(${formatSvgNumber(effect.center.x - 0.5)} ${formatSvgNumber(
                    effect.center.y - 0.5,
                  )})`}
                >
                  <rect
                    className="hide-smoke-square"
                    x="0"
                    y="0"
                    width="1"
                    height="1"
                    rx="0.08"
                  />
                  <circle className="hide-smoke-wisp hide-smoke-wisp-a" cx="0.28" cy="0.62" r="0.24" />
                  <circle className="hide-smoke-wisp hide-smoke-wisp-b" cx="0.56" cy="0.42" r="0.28" />
                  <circle className="hide-smoke-wisp hide-smoke-wisp-c" cx="0.75" cy="0.66" r="0.2" />
                </g>
              ))}
            </svg>
          ) : null}
          {healingHeartEffects.length > 0 ? (
            <svg
              key={`healing-${animationKey}`}
              className="board-overlay healing-heart-overlay"
              viewBox={`0 0 ${GRID_SIZE} ${GRID_SIZE}`}
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {healingHeartEffects.map((effect) => (
                <g
                  key={effect.key}
                  transform={`translate(${formatSvgNumber(effect.center.x)} ${formatSvgNumber(
                    effect.center.y,
                  )})`}
                >
                  <g
                    className="healing-heart-effect"
                    style={
                      {
                        "--healing-heart-delay": `${effect.delayMs}ms`,
                      } as CSSProperties
                    }
                  >
                    <path
                      className="healing-heart"
                      d="M 0 -0.28 C -0.36 -0.64 -0.9 -0.34 -0.72 0.14 C -0.58 0.52 -0.18 0.72 0 0.88 C 0.18 0.72 0.58 0.52 0.72 0.14 C 0.9 -0.34 0.36 -0.64 0 -0.28 Z"
                    />
                  </g>
                </g>
              ))}
            </svg>
          ) : null}
        </div>
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
  const {
    batchSummary,
    enemyCatalog,
    playerCatalog,
    enemyPresetIdInput,
    playerPresetIdInput,
  } = props;

  if (!batchSummary) {
    return (
      <div className="panel-copy">
        Batch mode is ready. Run a seeded sample set to estimate win rates,
        average round counts, losses, and remaining HP for the selected party
        and scenario.
      </div>
    );
  }

  const isCombined = batchSummary.monsterBehavior === "combined";
  const totalEnemyMaxHp = getTotalEnemyMaxHpForPreset(
    enemyCatalog,
    enemyPresetIdInput,
  );
  const totalPlayerMaxHp = getTotalPlayerMaxHpForPreset(
    playerCatalog,
    playerPresetIdInput,
  );

  function renderMetricGrid(
    summary: BatchSummary | BatchCombinationSummary,
    includeSeed = false,
  ) {
    return (
      <div className="metrics-grid">
        {includeSeed ? (
          <MetricCard label="Batch Seed" value={summary.seed} />
        ) : null}
        <MetricCard
          label="Player Policy"
          value={formatPlayerBehavior(summary.playerBehavior)}
        />
        <MetricCard
          label="DM Policy"
          value={formatMonsterBehavior(summary.monsterBehavior)}
        />
        <MetricCard label="Runs" value={String(summary.totalRuns)} />
        <MetricCard
          label="Party Win Rate"
          value={formatPercent(summary.playerWinRate)}
          tone="fighters"
        />
        <MetricCard
          label="Enemy Win Rate"
          value={formatPercent(summary.goblinWinRate)}
          tone="goblins"
        />
        <MetricCard
          label="Mutual Annihilation"
          value={formatPercent(summary.mutualAnnihilationRate)}
        />
        {summary.playerBehavior === "balanced" ? (
          <>
            <MetricCard
              label="Smart Player Win Rate"
              value={
                summary.smartPlayerWinRate === null
                  ? "-"
                  : formatPercent(summary.smartPlayerWinRate)
              }
              tone="fighters"
            />
            <MetricCard
              label="Dumb Player Win Rate"
              value={
                summary.dumbPlayerWinRate === null
                  ? "-"
                  : formatPercent(summary.dumbPlayerWinRate)
              }
              tone="fighters"
            />
          </>
        ) : null}
        <MetricCard
          label="Average Rounds"
          value={formatNumber(summary.averageRounds)}
        />
        <MetricCard
          label="Average Party Deaths"
          value={formatNumber(summary.averageFighterDeaths)}
        />
        <MetricCard
          label="Average Enemies Killed"
          value={formatNumber(summary.averageGoblinsKilled)}
        />
        <MetricCard
          label="Average Party HP"
          value={formatOutOf(
            summary.averageRemainingFighterHp,
            totalPlayerMaxHp,
          )}
          tone="fighters"
        />
        <MetricCard
          label="Average Enemy HP"
          value={formatOutOf(summary.averageRemainingGoblinHp, totalEnemyMaxHp)}
          tone="goblins"
        />
        <MetricCard
          label="Stable Unconscious Count"
          value={String(summary.stableButUnconsciousCount)}
        />
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
                <strong>
                  {formatMonsterBehavior(summary.monsterBehavior)} DM
                </strong>
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
          A seed-driven replay lab for a fixed level 5 party against
          backend-driven encounter scenarios. Use turn-by-turn replay to inspect
          tactical choices, then run batches to estimate encounter difficulty
          and compare behavior assumptions.
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
  scenarioPlaybackLocked: boolean;
  error: string | null;
  onGenerateSeed: () => void;
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
  const selectedScenario =
    props.enemyPresets.find(
      (preset) => preset.id === props.enemyPresetIdInput,
    ) ?? null;
  const progressLabel = props.batchJobStatus
    ? `${props.batchJobStatus.completedRuns} / ${props.batchJobStatus.totalRuns} runs completed`
    : null;
  const progressPercent = props.batchJobStatus
    ? Math.max(0, Math.min(100, props.batchJobStatus.progressRatio * 100))
    : 0;
  const progressPhase = props.batchJobStatus?.currentMonsterBehavior
    ? `${formatMonsterBehavior(props.batchJobStatus.currentMonsterBehavior)} DM`
    : props.batchJobStatus?.status === "completed"
      ? "Complete"
      : props.batchJobStatus?.status === "failed"
        ? "Failed"
        : "Preparing";

  return (
    <section className="panel controls-panel">
      <div className="panel-header">
        <h2>Controls</h2>
        <p>
          Choose the party, scenario, behavior model, and batch size for a
          deterministic simulation run.
        </p>
      </div>

      <div className="control-grid">
        <div className="field">
          <span>Seed</span>
          <div className="seed-control">
            <code>{props.seedInput}</code>
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={props.onGenerateSeed}
              disabled={props.scenarioPlaybackLocked}
            >
              New Seed
            </button>
          </div>
        </div>

        <label className="field">
          <span>Batch Size</span>
          <input
            type="number"
            min={1}
            max={MAX_BATCH_SIZE}
            value={props.batchSizeInput}
            onChange={(event) => props.onBatchSizeChange(event.target.value)}
            inputMode="numeric"
            disabled={props.scenarioPlaybackLocked}
          />
        </label>

        <label className="field">
          <span>Player Behavior</span>
          <select
            value={props.playerBehaviorInput}
            onChange={(event) =>
              props.onPlayerBehaviorChange(event.target.value as PlayerBehavior)
            }
            disabled={props.scenarioPlaybackLocked}
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
            disabled={!props.catalogLoaded || props.scenarioPlaybackLocked}
          >
            {!props.catalogLoaded ? (
              <option value="">Loading parties...</option>
            ) : null}
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
            {!props.catalogLoaded ? (
              <option value="">Loading scenarios...</option>
            ) : null}
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
            onChange={(event) =>
              props.onMonsterBehaviorChange(
                event.target.value as MonsterBehaviorSelection,
              )
            }
            disabled={props.scenarioPlaybackLocked}
          >
            <option value="kind">Kind DM</option>
            <option value="balanced">Balanced DM</option>
            <option value="evil">Evil DM</option>
            <option value="combined">Combined Batch</option>
          </select>
        </label>
      </div>

      <div className="panel-copy accent scenario-callout">
        <strong>Selected Scenario:</strong>{" "}
        {selectedScenario?.displayName ?? (props.enemyPresetIdInput || "-")}
        {selectedScenario?.description ? (
          <span> {selectedScenario.description}</span>
        ) : null}
      </div>

      <div className="panel-copy">
        Combined Batch runs Kind, Balanced, and Evil DM styles and reports the
        aggregate.
      </div>

      <div className="button-row">
        <button
          type="button"
          className="secondary-button"
          onClick={props.onEditLayout}
          disabled={!props.hasEncounter || props.scenarioPlaybackLocked}
        >
          Edit Layout
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={props.onToggleAutoplay}
          disabled={!props.hasEncounter || props.isRunning}
        >
          {props.isAutoplaying ? "Pause Replay" : "Auto Play"}
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={props.onRunBatch}
          disabled={!props.canRunSimulation || props.isRunning}
        >
          {props.isRunning ? "Running..." : "Batch Run"}
        </button>
      </div>

      <div className="panel-copy">
        Set <strong>Batch Size</strong> to <strong>1</strong> with a single{" "}
        <strong>DM Style</strong> for a turn-by-turn replay. Use larger batches
        to estimate outcome rates.
      </div>

      <div className="panel-copy">
        {props.scenarioPlaybackLocked
          ? "Frostfall Variant uses the locked presentation playback."
          : "Runs are processed by the local Python simulation backend."}
      </div>

      {props.batchJobStatus ? (
        <div className="progress-shell" aria-live="polite">
          <div className="progress-header-row">
            <strong>Batch Progress</strong>
            <span>{progressLabel}</span>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPercent}
          >
            <div
              className="progress-fill"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="progress-meta-row">
            <span>
              Elapsed: {formatElapsedTime(props.batchElapsedSeconds ?? 0)}
            </span>
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
            onChange={(event) =>
              props.onReplayIndexChange(Number(event.target.value))
            }
          />
        </label>
      ) : null}

      <div
        className={`panel-copy accent ${props.placementValidation.isValid ? "ready-accent" : ""}`}
      >
        {props.placementValidation.placedUnitIds.length} /{" "}
        {props.activeUnitCount} units placed. {props.placementStatusText}
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
    getTotalPlayerMaxHpForPreset(
      props.playerCatalog,
      props.playerPresetIdInput,
    ) || DEFAULT_PARTY_MAX_HP;

  return (
    <section className="panel battle-overview">
      <div className="panel-header">
        <h2>Encounter Summary</h2>
        <p>Current outcome, replay position, and batch aggregates.</p>
      </div>

      <div className="metrics-grid">
        <MetricCard
          label="Seed"
          value={props.encounterSummary?.seed ?? props.seedInput}
        />
        <MetricCard
          label="Party"
          value={getPlayerPresetLabel(
            props.playerCatalog,
            props.playerPresetIdInput,
          )}
        />
        <MetricCard
          label="Scenario"
          value={getEnemyPresetLabel(
            props.enemyCatalog,
            props.enemyPresetIdInput,
          )}
        />
        <MetricCard
          label="Player Behavior"
          value={formatPlayerBehavior(
            props.encounterSummary?.playerBehavior ?? props.playerBehaviorInput,
          )}
        />
        <MetricCard
          label="DM Style"
          value={formatMonsterBehavior(
            props.encounterSummary?.monsterBehavior ??
              props.monsterBehaviorInput,
          )}
        />
        <MetricCard
          label="Winner"
          value={formatWinner(props.encounterSummary?.winner)}
        />
        <MetricCard
          label="Rounds"
          value={
            props.encounterSummary ? String(props.encounterSummary.rounds) : "-"
          }
        />
        <MetricCard
          label="Party Deaths"
          value={
            props.encounterSummary
              ? String(props.encounterSummary.fighterDeaths)
              : "-"
          }
          tone="fighters"
        />
        <MetricCard
          label="Enemies Killed"
          value={
            props.encounterSummary
              ? String(props.encounterSummary.goblinsKilled)
              : "-"
          }
          tone="goblins"
        />
        <MetricCard
          label="Party HP"
          value={
            props.encounterSummary
              ? `${props.encounterSummary.remainingFighterHp} / ${totalPlayerMaxHp}`
              : "-"
          }
          tone="fighters"
        />
        <MetricCard
          label="Enemy HP"
          value={
            props.encounterSummary
              ? `${props.encounterSummary.remainingGoblinHp} / ${getTotalEnemyMaxHpForPreset(props.enemyCatalog, props.enemyPresetIdInput)}`
              : "-"
          }
          tone="goblins"
        />
        <MetricCard
          label="Stable Unconscious"
          value={
            props.encounterSummary
              ? String(props.encounterSummary.stableUnconsciousFighters)
              : "-"
          }
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
  rosterUnits: UnitState[];
  timelineEvents: CombatEvent[];
  highlightedPath: GridPosition[];
  currentFrame: ReplayFrame | null;
  initialFrame: ReplayFrame | null;
  currentRound: number;
  attackLine: AttackLine | null;
  replayTextFormatter?: (text: string) => string;
  showBattleReplayControls?: boolean;
  frameIndex?: number;
  frameCount?: number;
  autoPlayActive?: boolean;
  frameTransitionProgress?: number;
  replayFrameDurationMs?: number;
  onToggleAutoPlay?: () => void;
  onPreviousFrame?: () => void;
  onNextFrame?: () => void;
  onFrameChange?: (frameIndex: number) => void;
  onResetLayout: () => void;
  onSelectPlacementUnit: (unitId: string) => void;
  onPlacementCellClick: (
    position: GridPosition,
    occupantId: string | null,
  ) => void;
}

function InitiativeRail(props: {
  orderedUnits: UnitState[];
  currentFrame: ReplayFrame | null;
  initialFrame: ReplayFrame | null;
}) {
  const queue = getInitiativeQueue(
    props.orderedUnits,
    props.currentFrame,
    props.initialFrame,
  ).filter((unit) => !isUnitDefeated(unit));
  const activeId = getActiveUnitIdFromFrame(props.currentFrame);

  return (
    <aside className="initiative-rail">
      <div className="initiative-rail-header">Turn Order</div>

      <div className="initiative-list">
        {queue.length > 0 ? (
          queue.slice(0, 8).map((unit, index) => {
            const isActive = unit.id === activeId;

            return (
              <button
                key={unit.id}
                type="button"
                className={`initiative-item ${isActive ? "active" : ""}`}
                aria-label={`${isActive ? "Active unit" : "Initiative"} ${unit.id} ${getHudUnitDisplayName(unit)}`}
              >
                <span className="initiative-rank">{index + 1}</span>

                <span className="initiative-portrait">
                  <img
                    src={getUnitSprite(unit)}
                    alt={unit.id}
                    onError={(event) => {
                      event.currentTarget.src = "/sprites/enemy.png";
                    }}
                  />
                </span>

                <span className="initiative-meta">
                  <strong>{unit.id}</strong>
                  <small>{getHudUnitDisplayName(unit)}</small>
                  <small>HP {getUnitHpText(unit)}</small>
                </span>
              </button>
            );
          })
        ) : (
          <div className="initiative-empty">Run a seed</div>
        )}
      </div>
    </aside>
  );
}

function UnitRosterPanel(props: {
  units: UnitState[];
  activeUnitId: string | null;
  timelineEvents: CombatEvent[];
  initialFrame: ReplayFrame | null;
}) {
  return (
    <section
      className="unit-roster-panel"
      aria-label="Unit roster and casualty tracker"
    >
      <div className="unit-roster-header">
        <h3>Unit Roster</h3>
        <span>{props.units.length} total</span>
      </div>

      <div className="unit-roster-list">
        {props.units.length > 0 ? (
          props.units.map((unit) => {
            const deathRound = getDeathRoundForUnit(
              unit.id,
              props.timelineEvents,
            );
            const defeated = isUnitDefeated(unit) || deathRound !== null;
            const active = unit.id === props.activeUnitId;
            const lastKnownPosition = getLastKnownPositionForUnit(
              unit,
              props.timelineEvents,
              props.initialFrame,
            );

            return (
              <article
                key={unit.id}
                className={`unit-roster-card ${active ? "active" : ""} ${
                  defeated ? "defeated" : ""
                }`}
              >
                <div className="unit-roster-top">
                  <strong>{unit.id}</strong>
                  <span>{getHudUnitDisplayName(unit)}</span>
                  <b>{defeated ? "OUT" : getUnitStatusLabel(unit)}</b>
                </div>

                <div className="unit-roster-stats">
                  <span>
                    <small>HP</small>
                    <b>{getRosterHpText(unit, defeated)}</b>
                  </span>
                  <span>
                    <small>AC</small>
                    <b>{getUnitAcText(unit)}</b>
                  </span>
                  <span>
                    <small>Pos</small>
                    <b>
                      {lastKnownPosition
                        ? formatPosition(lastKnownPosition)
                        : "-"}
                    </b>
                  </span>
                  <span>
                    <small>Removed</small>
                    <b>{deathRound ? `R${deathRound}` : defeated ? "Yes" : "-"}</b>
                  </span>
                </div>
              </article>
            );
          })
        ) : (
          <div className="unit-roster-empty">Run a seed</div>
        )}
      </div>
    </section>
  );
}

function ActiveUnitCard(props: {
  activeUnit: BoardUnit | UnitState | undefined;
  selectedUnit: BoardUnit | UnitState | undefined;
  currentRound: number;
  modeLabel: string;
}) {
  const unit = props.activeUnit ?? props.selectedUnit;
  const currentHp = getUnitCurrentHp(unit);
  const maxHp = getUnitMaxHp(unit);
  const unitRoleLabel = props.activeUnit ? "Active unit" : "Selected unit:";

  if (!unit) {
    return (
      <section className="active-unit-card-hud empty">
        <div>
          <strong>No active unit</strong>
          <span>Selected unit: None</span>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`active-unit-card-hud ${isUnitDefeated(unit) ? "defeated" : ""}`}
    >
      <div className="active-unit-portrait">
        <img
          src={getUnitSprite(unit)}
          alt={unit.id}
          onError={(event) => {
            event.currentTarget.src = "/sprites/enemy.png";
          }}
        />
      </div>

      <div className="active-unit-main">
        <span className="active-unit-kicker">{unitRoleLabel}</span>
        <div className="active-unit-title-row">
          <strong>{unit.id}</strong>
          <span>{getHudUnitDisplayName(unit)}</span>
        </div>

        <div className="active-unit-meta-grid">
          <span>
            <small>HP</small>
            <b>
              {currentHp !== null && maxHp !== null
                ? `${currentHp}/${maxHp}`
                : "-"}
            </b>
          </span>
          <span>
            <small>AC</small>
            <b>{getUnitAcText(unit)}</b>
          </span>
          <span>
            <small>Pos</small>
            <b>{getUnitPositionText(unit)}</b>
          </span>
          <span>
            <small>Mode</small>
            <b>{props.modeLabel}</b>
          </span>
          <span>
            <small>Round</small>
            <b>{props.currentRound}</b>
          </span>
        </div>
      </div>
    </section>
  );
}

function BattleReplayControls(props: {
  frameIndex: number;
  frameCount: number;
  autoPlayActive: boolean;
  frameTransitionProgress: number;
  onToggleAutoPlay: () => void;
  onPreviousFrame: () => void;
  onNextFrame: () => void;
  onFrameChange: (frameIndex: number) => void;
}) {
  const maxFrameIndex = Math.max(props.frameCount - 1, 0);
  const frameNumber = props.frameCount > 0 ? props.frameIndex + 1 : 0;

  return (
    <section
      className="battle-replay-controls"
      aria-label="Battle replay controls"
    >
      <button
        type="button"
        onClick={props.onPreviousFrame}
        disabled={props.frameIndex <= 0}
      >
        Previous Frame
      </button>

      <button
        type="button"
        className={props.autoPlayActive ? "active" : ""}
        onClick={props.onToggleAutoPlay}
        disabled={props.frameCount === 0}
      >
        {props.autoPlayActive ? "Pause Replay" : "Auto Run"}
      </button>

      <button
        type="button"
        onClick={props.onNextFrame}
        disabled={props.frameCount === 0 || props.frameIndex >= maxFrameIndex}
      >
        Next Frame
      </button>

      <label className="battle-replay-slider">
        <span>
          Frame {frameNumber} / {props.frameCount}
        </span>
        <input
          type="range"
          aria-label="Battle replay frame"
          min={0}
          max={maxFrameIndex}
          value={Math.min(props.frameIndex, maxFrameIndex)}
          onChange={(event) => props.onFrameChange(Number(event.target.value))}
          disabled={props.frameCount === 0}
        />
      </label>

      <div className="frame-transition-timer" aria-hidden="true">
        <div className="frame-transition-track">
          <div
            className="frame-transition-fill"
            style={{ width: `${props.frameTransitionProgress}%` }}
          />
        </div>
      </div>
    </section>
  );
}

function formatPositionLabel(position?: GridPosition | null): string {
  if (!position) {
    return "-";
  }

  const column = String.fromCharCode(64 + position.x);

  return `${column}${position.y}`;
}

function getNumericEventField(
  value: CombatEvent["resolvedTotals"][string] | undefined,
): number | undefined {
  if (typeof value === "number") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.find((candidate): candidate is number => typeof candidate === "number");
  }

  return undefined;
}

function getReplayAction(props: {
  activeUnitId: string | null;
  units: Array<BoardUnit | UnitState>;
  highlightedPath: GridPosition[];
  attackLine: AttackLine | null;
  currentFrame: ReplayFrame | null;
}): ReplayAction | null {
  if (!props.activeUnitId) {
    return null;
  }

  const events = getActiveReplayEvents(props.currentFrame);
  const attackEvent =
    [...events].reverse().find((event) => event.eventType === "attack") ?? null;
  const hasMovement = props.highlightedPath.length > 1;
  const attackLine =
    props.attackLine?.actorId === props.activeUnitId ? props.attackLine : null;
  const hasAttack = Boolean(attackEvent);
  const hasSupport = events.some(
    (event) =>
      event.eventType === "heal" ||
      event.eventType === "phase_change" ||
      eventIncludesAny(event, BUFF_ANIMATION_TERMS),
  );
  const actor = props.units.find((unit) => unit.id === props.activeUnitId);
  const targetEvent =
    attackEvent ??
    [...events]
      .reverse()
      .find((event) =>
        event.targetIds.some((targetId) => targetId !== props.activeUnitId),
      );
  const targetId =
    targetEvent?.targetIds.find((candidate) => candidate !== props.activeUnitId) ??
    targetEvent?.targetIds[0] ??
    attackLine?.targetId;
  const target = props.units.find((unit) => unit.id === targetId);
  const attackRoll =
    getNumericEventField(attackEvent?.resolvedTotals.selectedRoll) ??
    getNumericEventField(attackEvent?.rawRolls.attackRoll) ??
    getNumericEventField(attackEvent?.rawRolls.attackRolls);
  const attackTotal =
    getNumericEventField(attackEvent?.resolvedTotals.attackTotal) ??
    getNumericEventField(attackEvent?.resolvedTotals.total);
  const hitValue = attackEvent?.resolvedTotals.hit;

  return {
    actorId: props.activeUnitId,
    actorName: getHudUnitDisplayName(actor),
    actorPosition:
      attackLine?.from ??
      (hasMovement
        ? props.highlightedPath[props.highlightedPath.length - 1]
        : actor?.position),
    actionType: hasMovement && hasAttack
      ? "move_attack"
      : hasMovement
        ? "move"
        : hasAttack
          ? "attack"
          : hasSupport
            ? "support"
          : "none",
    movePath: hasMovement ? props.highlightedPath : undefined,
    attackName: attackEvent?.damageDetails?.weaponName,
    attackRoll,
    attackModifier:
      attackRoll !== undefined && attackTotal !== undefined
        ? attackTotal - attackRoll
        : undefined,
    attackTotal,
    hit: typeof hitValue === "boolean" ? hitValue : undefined,
    damage: attackEvent?.damageDetails?.totalDamage,
    targetId,
    targetName: target ? getHudUnitDisplayName(target) : undefined,
    targetPosition: attackLine?.to ?? target?.position,
  };
}

function getReplayActionClass(action: ReplayAction | null): string {
  if (action?.actionType === "move_attack") {
    return "movement-attack";
  }

  if (action?.actionType === "move") {
    return "movement";
  }

  return action?.actionType ?? "none";
}

function getReplayActionLabel(action: ReplayAction | null): string {
  if (action?.actionType === "move_attack") {
    return "Move + Attack";
  }

  if (action?.actionType === "move") {
    return "Movement";
  }

  if (action?.actionType === "attack") {
    return "Attack";
  }

  if (action?.actionType === "support") {
    return "Support / Spell";
  }

  return "No Action";
}

function summarizeFrameEvents(
  events: CombatEvent[],
  units: Array<BoardUnit | UnitState>,
  formatText?: (text: string) => string,
): string {
  if (events.length === 0) {
    return "No action recorded.";
  }

  return events
    .map((event) =>
      formatText === undefined
        ? replaceUnitIdsWithNames(event.textSummary, units)
        : formatText(event.textSummary),
    )
    .join(" ");
}

export function VisualizationPanel(props: VisualizationPanelProps) {
  const [gridInteractionMode, setGridInteractionMode] =
    useState<GridInteractionMode>("setup");
  const placementStatusText = getPlacementStatusText(
    props.placementValidation,
    props.activeUnitIds.length,
  );
  const isReplayMode = props.spatialReplayActive && props.currentFrame !== null;
  const selectedSetupUnit = getBoardUnitById(
    props.setupUnits,
    props.selectedPlacementUnitId,
  );
  const selectedSetupMaxHp = selectedSetupUnit
    ? getCatalogMaxHpForUnit(
        props.enemyCatalog,
        props.playerCatalog,
        props.enemyPresetIdInput,
        props.playerPresetIdInput,
        selectedSetupUnit.id,
      )
    : undefined;
  const selectedSetupHudUnit =
    selectedSetupUnit && selectedSetupMaxHp !== undefined
      ? {
          ...selectedSetupUnit,
          currentHp: selectedSetupMaxHp,
          maxHp: selectedSetupMaxHp,
        }
      : selectedSetupUnit;
  const activeUnitId = getActiveUnitIdFromFrame(props.currentFrame);
  const activeUnit = activeUnitId
    ? props.orderedUnits.find((unit) => unit.id === activeUnitId) ??
      props.setupUnits.find((unit) => unit.id === activeUnitId)
    : undefined;
  const activeUnitDefeated = activeUnit ? isUnitDefeated(activeUnit) : false;
  const safeActiveUnitId = activeUnitDefeated ? null : activeUnitId;
  const safeActiveUnit = activeUnitDefeated ? undefined : activeUnit;
  const safeActiveCombatantLabel = safeActiveUnitId ?? "-";
  const safeHighlightedPath = activeUnitDefeated ? [] : props.highlightedPath;
  const safeAttackLine = activeUnitDefeated ? null : props.attackLine;
  const replayAction = getReplayAction({
    activeUnitId: safeActiveUnitId,
    units: props.rosterUnits,
    highlightedPath: safeHighlightedPath,
    attackLine: safeAttackLine,
    currentFrame: props.currentFrame,
  });
  const activeReplaySummary = summarizeFrameEvents(
    getActiveReplayEvents(props.currentFrame),
    props.rosterUnits,
    props.replayTextFormatter,
  );
  const replayActor = props.rosterUnits.find(
    (unit) => unit.id === replayAction?.actorId,
  );
  const replayTarget = props.rosterUnits.find(
    (unit) => unit.id === replayAction?.targetId,
  );
  const modeLabel = isReplayMode
    ? "Replay"
    : gridInteractionMode === "setup"
      ? "Setup"
      : gridInteractionMode === "movement"
        ? "Move"
        : "Attack";
  const combatStateDescription = props.isSetupMode
    ? `Click-to-place setup on the 15 x 15 grid for the ${getPlayerPresetLabel(props.playerCatalog, props.playerPresetIdInput)} against ${getEnemyPresetLabel(props.enemyCatalog, props.enemyPresetIdInput)}. Combat stays locked until every active unit is placed.`
    : "15 x 15 combat grid with movement, range, terrain cover, and opportunity attacks.";
  const initialFrame = props.initialFrame;
  const currentUnitMap = new Map(props.orderedUnits.map((unit) => [unit.id, unit]));
  const visibleInitiativeOrder =
    initialFrame?.state.initiativeOrder.filter(
      (unitId) => !isUnitDefeated(currentUnitMap.get(unitId)),
    ) ?? [];
  const initiativeRibbon = initialFrame ? (
    visibleInitiativeOrder.map((unitId) => (
      <div
        key={unitId}
        className={`initiative-token ${safeActiveUnitId === unitId ? "active" : ""}`}
      >
        <span>{unitId}</span>
        <small>{initialFrame.state.initiativeScores[unitId]}</small>
      </div>
    ))
  ) : (
    <div className="panel-copy">
      Run the encounter to populate initiative order.
    </div>
  );

  return (
    <section className="panel visualization-panel">
      {!props.isSetupMode && !props.spatialReplayActive ? (
        <div className="panel-header">
          <h2>Combat State</h2>
          <p>{combatStateDescription}</p>
        </div>
      ) : null}

      {props.isSetupMode ? (
        <>
          <div className="grid-board-section compact-battle-panel">
            <div className="battlefield-header">
              <div className="battlefield-title-block">
                <h2>Combat State</h2>
                <h3>Placement Grid</h3>
              </div>

              <div className="combat-compact-status">
                <span>
                  <small>Placed</small>
                  <strong>
                    {props.placementValidation.placedUnitIds.length} /{" "}
                    {props.activeUnitIds.length}
                  </strong>
                </span>
                <span>
                  <small>Selected</small>
                  <strong>{props.selectedPlacementUnitId ?? "-"}</strong>
                </span>
                <span>
                  <small>Status</small>
                  <strong>
                    {props.placementValidation.isValid ? "Ready" : "Setup"}
                  </strong>
                </span>
              </div>
            </div>

            <div className="battlefield-command-bar">
              <div
                className="mode-toggle"
                role="group"
                aria-label="Grid interaction mode"
              >
                <button
                  type="button"
                  className={`mode-button ${gridInteractionMode === "setup" ? "active" : ""}`}
                  onClick={() => setGridInteractionMode("setup")}
                >
                  Setup
                </button>

                <button
                  type="button"
                  className={`mode-button ${gridInteractionMode === "movement" ? "active" : ""}`}
                  onClick={() => setGridInteractionMode("movement")}
                >
                  Move
                </button>

                <button
                  type="button"
                  className={`mode-button ${gridInteractionMode === "attack" ? "active" : ""}`}
                  onClick={() => setGridInteractionMode("attack")}
                >
                  Attack
                </button>
              </div>

              <div className={`mode-helper ${gridInteractionMode}`}>
                <strong>
                  {gridInteractionMode === "setup"
                    ? "Setup"
                    : gridInteractionMode === "movement"
                      ? "Movement"
                      : "Attack"}
                </strong>
                <span>
                  {gridInteractionMode === "setup"
                    ? "Select unit -> click square."
                    : gridInteractionMode === "movement"
                      ? "Blue = reachable movement."
                      : "Red = clear target. Orange = cover."}
                </span>
              </div>

              <div className="preview-legend compact">
                <span className="legend-pill move">Blue = move</span>
                <span className="legend-pill attack">Red = attack</span>
                <span className="legend-pill cover">Orange = cover</span>
              </div>
            </div>

            <div className="grid-view-shell">
              <div className="battlefield-workbench">
                <aside className="map-left-rail">
                  <ActiveUnitCard
                    activeUnit={safeActiveUnit}
                    selectedUnit={selectedSetupHudUnit}
                    currentRound={props.currentRound}
                    modeLabel={modeLabel}
                  />

                  <button
                    type="button"
                    className="reset-layout-button secondary-button"
                    onClick={props.onResetLayout}
                  >
                    Reset Layout
                  </button>

                  <div
                    className={`placement-status ${props.placementValidation.isValid ? "ready" : ""}`}
                  >
                    {placementStatusText}
                  </div>

                  <div className="placement-unit-list rail-unit-list">
                    {props.activeUnitIds.map((unitId) => {
                      const position = props.placements[unitId];
                      const isSelected =
                        props.selectedPlacementUnitId === unitId;

                      return (
                        <button
                          key={unitId}
                          type="button"
                          className={`placement-unit-button ${isSelected ? "active" : ""} ${position ? "placed" : ""}`}
                          onClick={() => props.onSelectPlacementUnit(unitId)}
                          aria-label={`Select ${unitId} ${getUnitLabel(props.enemyCatalog, props.playerCatalog, props.enemyPresetIdInput, props.playerPresetIdInput, unitId)}${position ? ` at ${formatPosition(position)}` : ", unplaced"}`}
                        >
                          <span>{unitId}</span>
                          <strong>
                            {getUnitLabel(
                              props.enemyCatalog,
                              props.playerCatalog,
                              props.enemyPresetIdInput,
                              props.playerPresetIdInput,
                              unitId,
                            )}
                          </strong>
                          <small>
                            {position ? formatPosition(position) : "Unplaced"}
                          </small>
                        </button>
                      );
                    })}
                  </div>
                </aside>

                <div className="board-column">
                  <div className="board-stage-shell">
                    <GridBoard
                      units={props.setupUnits}
                      terrainFeatures={props.terrainFeatures}
                      highlightedPath={[]}
                      activeUnitId={safeActiveUnitId}
                      attackLine={null}
                      selectedPlacementUnitId={props.selectedPlacementUnitId}
                      onCellClick={props.onPlacementCellClick}
                      ariaLabel="Placement grid"
                      useBattlefieldBackground={true}
                      interactionMode={gridInteractionMode}
                      showReplayGrid={false}
                    />
                  </div>
                </div>
              </div>
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
              <strong>{safeActiveCombatantLabel}</strong>
            </div>
            <div className="stage-chip">
              <span>Phase</span>
              <strong>
                {props.currentFrame?.state.terminalState === "complete"
                  ? "Complete"
                  : "Combat"}
              </strong>
            </div>
          </div>

          <div className="initiative-ribbon">{initiativeRibbon}</div>
        </>
      )}

      {props.spatialReplayActive ? (
        <div className="grid-board-section compact-battle-panel">
          <div className="battlefield-header">
            <div className="battlefield-title-block">
              <h2>Combat State</h2>
              <h3>Grid View</h3>
            </div>

            <div className="combat-compact-status">
              <span>
                <small>Round</small>
                <strong>{props.currentRound}</strong>
              </span>
              <span>
                <small>Active</small>
                <strong>{safeActiveCombatantLabel}</strong>
              </span>
              <span>
                <small>Phase</small>
                <strong>
                  {props.currentFrame?.state.terminalState === "complete"
                    ? "Complete"
                    : "Combat"}
                </strong>
              </span>
            </div>
          </div>

          <div className="battlefield-command-bar replay-command-bar">
            <div className="mode-helper replay">
              <strong>Replay</strong>
              <span>
                Active combatant:{" "}
                {safeActiveUnitId ?? "Pending"}
              </span>
            </div>
          </div>

          {props.showBattleReplayControls &&
          props.frameIndex !== undefined &&
          props.frameCount !== undefined &&
          props.autoPlayActive !== undefined &&
          props.frameTransitionProgress !== undefined &&
          props.onToggleAutoPlay &&
          props.onPreviousFrame &&
          props.onNextFrame &&
          props.onFrameChange ? (
            <BattleReplayControls
              frameIndex={props.frameIndex}
              frameCount={props.frameCount}
              autoPlayActive={props.autoPlayActive}
              frameTransitionProgress={props.frameTransitionProgress}
              onToggleAutoPlay={props.onToggleAutoPlay}
              onPreviousFrame={props.onPreviousFrame}
              onNextFrame={props.onNextFrame}
              onFrameChange={props.onFrameChange}
            />
          ) : null}

          <div className="grid-view-shell">
            <div className="battlefield-workbench">
              <aside className="map-left-rail replay-map-rail">
                <ActiveUnitCard
                  activeUnit={safeActiveUnit}
                  selectedUnit={selectedSetupHudUnit}
                  currentRound={props.currentRound}
                  modeLabel={modeLabel}
                />

                <InitiativeRail
                  orderedUnits={props.orderedUnits}
                  currentFrame={props.currentFrame}
                  initialFrame={props.initialFrame}
                />

                <UnitRosterPanel
                  units={props.rosterUnits}
                  activeUnitId={activeUnitId}
                  timelineEvents={props.timelineEvents}
                  initialFrame={props.initialFrame}
                />
              </aside>

              <div className="board-column">
                <div className="board-stage-shell">
                  <GridBoard
                    units={props.orderedUnits}
                    terrainFeatures={props.terrainFeatures}
                    highlightedPath={safeHighlightedPath}
                    activeUnitId={safeActiveUnitId}
                    attackLine={safeAttackLine}
                    ariaLabel="Combat grid"
                    useBattlefieldBackground={true}
                    interactionMode="replay"
                    showReplayGrid={props.spatialReplayActive}
                    currentFrame={props.currentFrame}
                    replayFrameDurationMs={props.replayFrameDurationMs}
                  />
                </div>
              </div>
            </div>

            <section
              className={`current-action-banner ${getReplayActionClass(replayAction)}`}
            >
              <div className="action-banner-title">
                <strong>
                  {replayAction?.actorName ?? "Replay frame has no active action."}
                </strong>
                <b className="action-pill">{getReplayActionLabel(replayAction)}</b>
              </div>

              {replayAction?.movePath && replayAction.movePath.length > 1 ? (
                <span className="action-banner-detail">
                  Move: {formatPositionLabel(replayAction.movePath[0])} -&gt;{" "}
                  {formatPositionLabel(replayAction.movePath[replayAction.movePath.length - 1])}
                </span>
              ) : null}

              {replayAction?.attackName ? (
                <span className="action-banner-detail">
                  Attack: {replayAction.attackName}
                </span>
              ) : null}

              {replayAction?.attackTotal !== undefined ? (
                <span className="action-banner-detail">
                  Roll: {replayAction.attackRoll ?? "-"}
                  {replayAction.attackModifier !== undefined
                    ? ` ${replayAction.attackModifier >= 0 ? "+" : "-"} ${Math.abs(replayAction.attackModifier)}`
                    : ""}{" "}
                  = {replayAction.attackTotal}
                </span>
              ) : null}

              {replayAction?.targetId ? (
                <span className="action-banner-detail">
                  Target: {replayAction.targetName ?? replayAction.targetId} (
                  {formatPositionLabel(replayAction.targetPosition)})
                </span>
              ) : null}

              {replayAction?.hit !== undefined ? (
                <span className="action-banner-detail">
                  Result: {replayAction.hit ? "Hit" : "Miss"}
                  {replayAction.damage !== undefined
                    ? ` | Damage: ${replayAction.damage}`
                    : ""}
                </span>
              ) : null}

              <div className="action-banner-meta">
                <span>ID: {replayAction?.actorId ?? "-"}</span>
                <span>
                  Actor Loc: {formatPositionLabel(replayAction?.actorPosition)}
                </span>
                {replayTarget ? (
                  <>
                    <span>Target: {getHudUnitDisplayName(replayTarget)}</span>
                    <span>Target ID: {replayTarget.id}</span>
                    <span>
                      Target Loc: {formatPositionLabel(replayAction?.targetPosition)}
                    </span>
                  </>
                ) : null}
              </div>

              <span className="action-banner-turn-summary">
                Turn: {activeReplaySummary}
              </span>
            </section>

            <div className="frame-diagnostics">
              {activeUnitDefeated ? (
                <span>Active unit is defeated; movement and attack are skipped.</span>
              ) : (
                <>
                  <span>
                    {safeHighlightedPath.length > 1
                      ? `Movement path: ${safeHighlightedPath.length - 1} step(s).`
                      : "No movement in this replay frame."}
                  </span>
                  <span>
                    {safeAttackLine
                      ? `Attack line: ${getHudUnitDisplayName(replayActor)} ${formatPositionLabel(
                          safeAttackLine.from,
                        )} to ${getHudUnitDisplayName(replayTarget)} ${formatPositionLabel(
                          safeAttackLine.to,
                        )}.`
                      : "No attack in this replay frame."}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      ) : !props.isSetupMode ? (
        <div className="panel-copy">
          Run the simulation to view the 15 x 15 combat grid.
        </div>
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
            <article
              key={`${event.actorId}-${event.eventType}-${index}-${event.round}`}
              className="event-card"
            >
              <header className="event-header">
                <span className="event-type">
                  {event.eventType.replace("_", " ")}
                </span>
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

              {event.movementDetails?.path &&
              event.movementDetails.path.length > 1 ? (
                <div className="movement-trace">
                  <strong>Path:</strong>{" "}
                  {formatPath(event.movementDetails.path)}
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
        <div className="panel-copy">
          Run a seed to populate the replay feed.
        </div>
      )}
    </section>
  );
}

export function UnitStatePanel(props: {
  orderedUnits: UnitState[];
  activeUnitId?: string | null;
}) {
  return (
    <section className="panel unit-panel">
      <div className="panel-header">
        <h2>Unit State</h2>
        <p>
          Per-unit HP, resources, status, and temporary effects at the selected
          frame.
        </p>
      </div>

      <div className="unit-grid">
        {props.orderedUnits.length > 0 ? (
          props.orderedUnits.map((unit) => {
            const statusText = getUnitStatus(unit);
            const isActive = unit.id === props.activeUnitId;
            const isDefeated = isUnitDefeated(unit);

            return (
              <article
                key={unit.id}
                className={`unit-card ${unit.faction} ${
                  isActive ? "active-unit-card" : ""
                } ${isDefeated ? "defeated-unit-card" : ""}`}
              >
                <header className="unit-header">
                  <div>
                    <span className="unit-id">{unit.id}</span>
                    <strong>{cleanUnitName(unit.templateName)}</strong>
                  </div>
                  <span className={`status-pill ${statusText.toLowerCase()}`}>
                    {statusText}
                  </span>
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
                    <dd>{unit.combatRole.replace(/_/g, " ")}</dd>
                  </div>
                  <div>
                    <dt>Resources</dt>
                    <dd>
                      {[
                        unit.resources.secondWindUses > 0
                          ? `Second Wind ${unit.resources.secondWindUses}`
                          : null,
                        unit.resources.javelins > 0
                          ? `Javelins ${unit.resources.javelins}`
                          : null,
                        unit.resources.rageUses > 0
                          ? `Rage ${unit.resources.rageUses}`
                          : null,
                        unit.resources.handaxes > 0
                          ? `Handaxes ${unit.resources.handaxes}`
                          : null,
                        unit.resources.actionSurgeUses > 0
                          ? `Action Surge ${unit.resources.actionSurgeUses}`
                          : null,
                        unit.resources.superiorityDice > 0
                          ? `Superiority Dice ${unit.resources.superiorityDice}`
                          : null,
                        unit.resources.focusPoints > 0
                          ? `Focus ${unit.resources.focusPoints}`
                          : null,
                        unit.resources.spellSlotsLevel1 > 0
                          ? `1st-level Slots ${unit.resources.spellSlotsLevel1}`
                          : null,
                        unit.resources.spellSlotsLevel2 > 0
                          ? `2nd-level Slots ${unit.resources.spellSlotsLevel2}`
                          : null,
                        unit.resources.spellSlotsLevel3 > 0
                          ? `3rd-level Slots ${unit.resources.spellSlotsLevel3}`
                          : null,
                        unit.resources.layOnHandsPoints > 0
                          ? `Lay on Hands ${unit.resources.layOnHandsPoints}`
                          : null,
                        unit.resources.channelDivinityUses > 0
                          ? `Channel Divinity ${unit.resources.channelDivinityUses}`
                          : null,
                        unit.resources.uncannyMetabolismUses > 0
                          ? `Uncanny Metabolism ${unit.resources.uncannyMetabolismUses}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(", ") || "None"}
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
                        ? unit.temporaryEffects
                            .map((effect) => effect.kind.replace(/_/g, " "))
                            .join(", ")
                        : "None"}
                    </dd>
                  </div>
                </dl>
              </article>
            );
          })
        ) : (
          <div className="panel-copy">
            Unit cards appear after the first run.
          </div>
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
            <div
              key={`${event.actorId}-${event.eventType}-${index}-${event.round}`}
              className="timeline-row"
            >
              <span className="timeline-round">R{event.round}</span>
              <strong>{event.actorId}</strong>
              <span>{event.textSummary}</span>
            </div>
          ))
        ) : (
          <div className="panel-copy">
            The full event log will populate after the first run.
          </div>
        )}
      </div>
    </section>
  );
}
