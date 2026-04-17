import { compareUnitIds } from './helpers';
import { UNIT_IDS } from './constants';
import type { EncounterState, Faction, GridPosition, UnitState, WeaponProfile } from './types';

export const GRID_SIZE = 15;

export interface ReachableSquare {
  position: GridPosition;
  path: GridPosition[];
  distance: number;
}

export interface AttackContext {
  legal: boolean;
  distanceSquares: number | null;
  distanceFeet: number | null;
  withinReach: boolean;
  withinNormalRange: boolean;
  withinLongRange: boolean;
  coverAcBonus: number;
  advantageSources: string[];
  disadvantageSources: string[];
}

export interface PlacementValidationResult {
  placedUnitIds: string[];
  missingUnitIds: string[];
  unexpectedUnitIds: string[];
  outOfBoundsUnitIds: string[];
  overlappingGroups: Array<{
    position: GridPosition;
    unitIds: string[];
  }>;
  isComplete: boolean;
  isValid: boolean;
  errors: string[];
}

function sortGridPositions(left: GridPosition, right: GridPosition): number {
  if (left.x !== right.x) {
    return left.x - right.x;
  }

  return left.y - right.y;
}

export function positionKey(position: GridPosition): string {
  return `${position.x},${position.y}`;
}

export function positionsEqual(left?: GridPosition, right?: GridPosition): boolean {
  return Boolean(left && right && left.x === right.x && left.y === right.y);
}

export function isWithinBounds(position: GridPosition): boolean {
  return (
    position.x >= 1 &&
    position.x <= GRID_SIZE &&
    position.y >= 1 &&
    position.y <= GRID_SIZE
  );
}

export function inspectPlacements(
  placements: Record<string, GridPosition> | undefined
): PlacementValidationResult {
  const normalizedPlacements = placements ?? {};
  const expectedUnitIds = [...UNIT_IDS];
  const expectedUnitSet = new Set<string>(expectedUnitIds);
  const placedUnitIds = expectedUnitIds.filter((unitId) => Boolean(normalizedPlacements[unitId]));
  const missingUnitIds = expectedUnitIds.filter((unitId) => !normalizedPlacements[unitId]);
  const unexpectedUnitIds = Object.keys(normalizedPlacements).filter((unitId) => !expectedUnitSet.has(unitId));
  const outOfBoundsUnitIds: string[] = [];
  const occupiedSquares = new Map<string, string[]>();

  for (const unitId of placedUnitIds) {
    const position = normalizedPlacements[unitId];

    if (!isWithinBounds(position)) {
      outOfBoundsUnitIds.push(unitId);
      continue;
    }

    const key = positionKey(position);
    const occupants = occupiedSquares.get(key) ?? [];
    occupants.push(unitId);
    occupiedSquares.set(key, occupants);
  }

  const overlappingGroups = [...occupiedSquares.entries()]
    .filter(([, unitIds]) => unitIds.length > 1)
    .map(([key, unitIds]) => {
      const [x, y] = key.split(',').map(Number);
      return {
        position: { x, y },
        unitIds
      };
    });

  const errors: string[] = [];

  if (missingUnitIds.length > 0) {
    errors.push(`Missing placements for: ${missingUnitIds.join(', ')}.`);
  }

  if (unexpectedUnitIds.length > 0) {
    errors.push(`Unexpected unit ids in placement map: ${unexpectedUnitIds.join(', ')}.`);
  }

  if (outOfBoundsUnitIds.length > 0) {
    errors.push(`Out-of-bounds placements for: ${outOfBoundsUnitIds.join(', ')}.`);
  }

  for (const overlap of overlappingGroups) {
    errors.push(
      `Overlapping placements at (${overlap.position.x},${overlap.position.y}): ${overlap.unitIds.join(', ')}.`
    );
  }

  return {
    placedUnitIds,
    missingUnitIds,
    unexpectedUnitIds,
    outOfBoundsUnitIds,
    overlappingGroups,
    isComplete: missingUnitIds.length === 0,
    isValid:
      missingUnitIds.length === 0 &&
      unexpectedUnitIds.length === 0 &&
      outOfBoundsUnitIds.length === 0 &&
      overlappingGroups.length === 0,
    errors
  };
}

export function assertValidPlacements(
  placements: Record<string, GridPosition> | undefined
): PlacementValidationResult {
  const validation = inspectPlacements(placements);

  if (!validation.isValid) {
    throw new Error(validation.errors.join(' '));
  }

  return validation;
}

export function chebyshevDistance(left: GridPosition, right: GridPosition): number {
  return Math.max(Math.abs(left.x - right.x), Math.abs(left.y - right.y));
}

export function squaresToFeet(squares: number): number {
  return squares * 5;
}

export function feetToSquares(feet: number): number {
  return Math.ceil(feet / 5);
}

export function doesUnitOccupySquare(unit: UnitState): boolean {
  return Boolean(unit.position && !unit.conditions.dead);
}

export function getUnitsWithPositions(state: EncounterState, faction?: Faction): UnitState[] {
  return Object.values(state.units).filter((unit) => {
    if (faction && unit.faction !== faction) {
      return false;
    }

    return doesUnitOccupySquare(unit);
  });
}

export function getOccupantAt(
  state: EncounterState,
  position: GridPosition,
  ignoredUnitIds: string[] = []
): UnitState | null {
  return (
    getUnitsWithPositions(state).find(
      (unit) =>
        !ignoredUnitIds.includes(unit.id) &&
        unit.position &&
        positionsEqual(unit.position, position)
    ) ?? null
  );
}

function canMoveThrough(mover: UnitState, occupant: UnitState): boolean {
  if (occupant.id === mover.id) {
    return true;
  }

  if (occupant.conditions.dead) {
    return true;
  }

  if (occupant.faction === mover.faction) {
    return true;
  }

  return occupant.conditions.unconscious;
}

export function isAdjacent(left?: GridPosition, right?: GridPosition): boolean {
  return Boolean(left && right && chebyshevDistance(left, right) <= 1);
}

export function getAdjacentSquares(position: GridPosition): GridPosition[] {
  const squares: GridPosition[] = [];

  for (let deltaX = -1; deltaX <= 1; deltaX += 1) {
    for (let deltaY = -1; deltaY <= 1; deltaY += 1) {
      if (deltaX === 0 && deltaY === 0) {
        continue;
      }

      const candidate = {
        x: position.x + deltaX,
        y: position.y + deltaY
      };

      if (isWithinBounds(candidate)) {
        squares.push(candidate);
      }
    }
  }

  return squares.sort(sortGridPositions);
}

export function getOpportunityAttackThreatsForPath(
  state: EncounterState,
  moverId: string,
  path: GridPosition[]
): string[] {
  const mover = state.units[moverId];

  if (!mover.position || path.length <= 1) {
    return [];
  }

  const threats = new Set<string>();

  for (let index = 1; index < path.length; index += 1) {
    const previous = path[index - 1];
    const next = path[index];

    for (const unit of Object.values(state.units)) {
      if (
        unit.faction === mover.faction ||
        unit.currentHp <= 0 ||
        unit.conditions.dead ||
        !unit.reactionAvailable ||
        !unit.position
      ) {
        continue;
      }

      if (chebyshevDistance(unit.position, previous) <= 1 && chebyshevDistance(unit.position, next) > 1) {
        threats.add(unit.id);
      }
    }
  }

  return [...threats].sort(compareUnitIds);
}

export function pathProvokesOpportunityAttack(
  state: EncounterState,
  moverId: string,
  path: GridPosition[]
): boolean {
  return getOpportunityAttackThreatsForPath(state, moverId, path).length > 0;
}

function canProvideFlanking(unit: UnitState): boolean {
  return !unit.conditions.dead && !unit.conditions.unconscious && unit.currentHp > 0;
}

function hasFlankingSupport(
  state: EncounterState,
  attackerId: string,
  targetId: string,
  attackerPosition: GridPosition,
  targetPosition: GridPosition
): boolean {
  if (!isAdjacent(attackerPosition, targetPosition)) {
    return false;
  }

  const attacker = state.units[attackerId];
  const attackerOffsetX = attackerPosition.x - targetPosition.x;
  const attackerOffsetY = attackerPosition.y - targetPosition.y;

  return getUnitsWithPositions(state, attacker.faction)
    .filter((unit) => unit.id !== attackerId && unit.id !== targetId)
    .filter(canProvideFlanking)
    .some((unit) => {
      if (!unit.position || !isAdjacent(unit.position, targetPosition)) {
        return false;
      }

      const allyOffsetX = unit.position.x - targetPosition.x;
      const allyOffsetY = unit.position.y - targetPosition.y;

      return attackerOffsetX * allyOffsetX + attackerOffsetY * allyOffsetY < 0;
    });
}

function buildReachableSquareMap(
  state: EncounterState,
  moverId: string,
  maxSquares: number
): Map<string, ReachableSquare> {
  const mover = state.units[moverId];

  if (!mover.position) {
    return new Map();
  }

  const start = mover.position;
  const queue: GridPosition[] = [start];
  const visited = new Set<string>([positionKey(start)]);
  const pathMap = new Map<string, GridPosition[]>([[positionKey(start), [start]]]);
  const distanceMap = new Map<string, number>([[positionKey(start), 0]]);
  const legalEnds = new Map<string, ReachableSquare>([
    [
      positionKey(start),
      {
        position: start,
        path: [start],
        distance: 0
      }
    ]
  ]);

  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentDistance = distanceMap.get(positionKey(current)) ?? 0;
    const currentPath = pathMap.get(positionKey(current)) ?? [start];

    if (currentDistance >= maxSquares) {
      continue;
    }

    for (const neighbor of getAdjacentSquares(current)) {
      const key = positionKey(neighbor);

      if (visited.has(key)) {
        continue;
      }

      const occupant = getOccupantAt(state, neighbor, [moverId]);

      if (occupant && !canMoveThrough(mover, occupant)) {
        continue;
      }

      visited.add(key);
      const nextPath = [...currentPath, neighbor];
      const nextDistance = currentDistance + 1;
      pathMap.set(key, nextPath);
      distanceMap.set(key, nextDistance);
      queue.push(neighbor);

      if (!occupant) {
        legalEnds.set(key, {
          position: neighbor,
          path: nextPath,
          distance: nextDistance
        });
      }
    }
  }

  return legalEnds;
}

export function getReachableSquares(
  state: EncounterState,
  moverId: string,
  maxSquares: number
): ReachableSquare[] {
  return [...buildReachableSquareMap(state, moverId, maxSquares).values()].sort((left, right) => {
    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    return sortGridPositions(left.position, right.position);
  });
}

function chooseBestReachableSquare(candidates: ReachableSquare[]): ReachableSquare | null {
  if (candidates.length === 0) {
    return null;
  }

  return [...candidates].sort((left, right) => {
    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    return sortGridPositions(left.position, right.position);
  })[0];
}

export function findPathToAdjacentSquare(
  state: EncounterState,
  moverId: string,
  targetId: string,
  maxSquares = Number.POSITIVE_INFINITY
): ReachableSquare | null {
  const target = state.units[targetId];

  if (!target.position) {
    return null;
  }

  const reachable = buildReachableSquareMap(state, moverId, maxSquares);
  const candidates = getAdjacentSquares(target.position)
    .map((square) => reachable.get(positionKey(square)))
    .filter((square): square is ReachableSquare => Boolean(square));

  return chooseBestReachableSquare(candidates);
}

export function truncatePath(path: GridPosition[], maxSquares: number): GridPosition[] {
  if (path.length <= 1 || maxSquares <= 0) {
    return [path[0]];
  }

  return path.slice(0, Math.min(path.length, maxSquares + 1));
}

export function findAdvancePath(
  state: EncounterState,
  moverId: string,
  targetId: string,
  maxSquares: number
): ReachableSquare | null {
  const target = state.units[targetId];

  if (!target.position) {
    return null;
  }

  const fullAdjacentPath = findPathToAdjacentSquare(state, moverId, targetId);

  if (fullAdjacentPath) {
    if (fullAdjacentPath.distance <= maxSquares) {
      return fullAdjacentPath;
    }

    const truncatedPath = truncatePath(fullAdjacentPath.path, maxSquares);

    return {
      position: truncatedPath[truncatedPath.length - 1],
      path: truncatedPath,
      distance: truncatedPath.length - 1
    };
  }

  const reachable = getReachableSquares(state, moverId, maxSquares);
  const fallback = [...reachable].sort((left, right) => {
    const leftDistance = chebyshevDistance(left.position, target.position!);
    const rightDistance = chebyshevDistance(right.position, target.position!);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    if (right.distance !== left.distance) {
      return right.distance - left.distance;
    }

    return sortGridPositions(left.position, right.position);
  })[0];

  return fallback ?? null;
}

function getLineSquares(start: GridPosition, end: GridPosition): GridPosition[] {
  const cells: GridPosition[] = [{ ...start }];
  const deltaX = end.x - start.x;
  const deltaY = end.y - start.y;
  const stepsX = Math.abs(deltaX);
  const stepsY = Math.abs(deltaY);
  const signX = deltaX === 0 ? 0 : deltaX > 0 ? 1 : -1;
  const signY = deltaY === 0 ? 0 : deltaY > 0 ? 1 : -1;
  let x = start.x;
  let y = start.y;
  let iterX = 0;
  let iterY = 0;

  while (iterX < stepsX || iterY < stepsY) {
    const decision = (1 + 2 * iterX) * stepsY - (1 + 2 * iterY) * stepsX;

    if (decision === 0) {
      x += signX;
      y += signY;
      iterX += 1;
      iterY += 1;
    } else if (decision < 0) {
      x += signX;
      iterX += 1;
    } else {
      y += signY;
      iterY += 1;
    }

    cells.push({ x, y });
  }

  return cells;
}

function hasHalfCover(
  state: EncounterState,
  attackerId: string,
  targetId: string,
  attackerPosition: GridPosition,
  targetPosition: GridPosition
): boolean {
  const traversedSquares = getLineSquares(attackerPosition, targetPosition).slice(1, -1);

  return traversedSquares.some((square) =>
    Boolean(getOccupantAt(state, square, [attackerId, targetId]))
  );
}

export function getAttackContext(
  state: EncounterState,
  attackerId: string,
  targetId: string,
  weapon: WeaponProfile,
  attackerPosition = state.units[attackerId].position,
  targetPosition = state.units[targetId].position
): AttackContext {
  if (!attackerPosition || !targetPosition) {
    return {
      legal: true,
      distanceSquares: null,
      distanceFeet: null,
      withinReach: true,
      withinNormalRange: true,
      withinLongRange: true,
      coverAcBonus: 0,
      advantageSources: [],
      disadvantageSources: []
    };
  }

  const distanceSquares = chebyshevDistance(attackerPosition, targetPosition);
  const distanceFeet = squaresToFeet(distanceSquares);
  const disadvantageSources: string[] = [];
  const advantageSources: string[] = [];
  let legal = false;
  let withinReach = false;
  let withinNormalRange = false;
  let withinLongRange = false;
  let coverAcBonus = 0;

  if (weapon.kind === 'melee') {
    withinReach = distanceSquares <= 1;
    legal = withinReach;
    withinNormalRange = withinReach;
    withinLongRange = withinReach;

    if (withinReach && hasFlankingSupport(state, attackerId, targetId, attackerPosition, targetPosition)) {
      advantageSources.push('flanking');
    }
  } else {
    const normalRangeFeet = weapon.range?.normal ?? 0;
    const longRangeFeet = weapon.range?.long ?? 0;
    withinNormalRange = distanceFeet <= normalRangeFeet;
    withinLongRange = distanceFeet <= longRangeFeet;
    legal = withinLongRange;

    if (legal && !withinNormalRange) {
      disadvantageSources.push('long_range');
    }

    const nearbyVisibleEnemy = getUnitsWithPositions(state)
      .filter(
        (unit) =>
          unit.faction !== state.units[attackerId].faction &&
          !unit.conditions.unconscious
      )
      .some((unit) => unit.position && chebyshevDistance(attackerPosition, unit.position) <= 1);

    if (nearbyVisibleEnemy) {
      disadvantageSources.push('adjacent_enemy');
    }

    if (hasHalfCover(state, attackerId, targetId, attackerPosition, targetPosition)) {
      coverAcBonus = 2;
    }
  }

  return {
    legal,
    distanceSquares,
    distanceFeet,
    withinReach,
    withinNormalRange,
    withinLongRange,
    coverAcBonus,
    advantageSources,
    disadvantageSources
  };
}

export function getMinDistanceToFaction(
  state: EncounterState,
  position: GridPosition,
  faction: Faction
): number {
  const units = getUnitsWithPositions(state, faction);

  if (units.length === 0) {
    return Number.POSITIVE_INFINITY;
  }

  return Math.min(
    ...units.map((unit) => chebyshevDistance(position, unit.position!))
  );
}
