import { compareUnitIds, getUnitsByFaction, isUnitConscious, isUnitDying } from './helpers';
import {
  chebyshevDistance,
  getAttackContext,
  getMinDistanceToFaction,
  getReachableSquares,
  pathProvokesOpportunityAttack
} from './spatial';
import type {
  AttackId,
  EncounterState,
  GridPosition,
  ResolvedPlayerBehavior,
  RoleTag,
  UnitState
} from './types';
import type { ReachableSquare } from './spatial';

export interface MovementPlan {
  path: GridPosition[];
  mode: 'move' | 'dash';
}

export interface TurnDecision {
  bonusAction?: {
    kind: 'second_wind' | 'disengage';
    timing: 'before_action' | 'after_action';
  };
  preActionMovement?: MovementPlan;
  postActionMovement?: MovementPlan;
  action:
    | {
        kind: 'attack';
        targetId: string;
        weaponId: AttackId;
      }
    | {
        kind: 'stabilize';
        targetId: string;
      }
    | {
        kind: 'dash';
        reason: string;
      }
    | {
        kind: 'skip';
        reason: string;
      };
}

interface AttackPlan {
  targetId: string;
  weaponId: AttackId;
  path: GridPosition[];
}

interface MeleeAttackOption {
  target: UnitState;
  path: GridPosition[];
  distance: number;
  createsFlank: boolean;
  adjacentAllies: number;
}

function getHpRatio(unit: UnitState): number {
  if (unit.maxHp <= 0) {
    return 0;
  }

  return unit.currentHp / unit.maxHp;
}

function hasRoleTag(unit: UnitState, roleTag: RoleTag): boolean {
  return unit.roleTags.includes(roleTag);
}

function isUnitDowned(unit: UnitState): boolean {
  return !unit.conditions.dead && unit.currentHp === 0;
}

function getMoveSquares(unit: UnitState): number {
  return Math.floor(unit.effectiveSpeed / 5);
}

function getMovementDistance(plan: MovementPlan | undefined): number {
  if (!plan || plan.path.length <= 1) {
    return 0;
  }

  return plan.path.length - 1;
}

function compareGridPositions(left: GridPosition, right: GridPosition): number {
  if (left.x !== right.x) {
    return left.x - right.x;
  }

  return left.y - right.y;
}

function chooseClosestReachableSquare(candidates: ReachableSquare[]): ReachableSquare | null {
  if (candidates.length === 0) {
    return null;
  }

  return [...candidates].sort((left, right) => {
    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    return compareGridPositions(left.position, right.position);
  })[0];
}

function chooseAdvanceSquare(candidates: ReachableSquare[], targetPosition: GridPosition): ReachableSquare | null {
  if (candidates.length === 0) {
    return null;
  }

  return [...candidates].sort((left, right) => {
    const leftDistance = chebyshevDistance(left.position, targetPosition);
    const rightDistance = chebyshevDistance(right.position, targetPosition);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    if (right.distance !== left.distance) {
      return right.distance - left.distance;
    }

    return compareGridPositions(left.position, right.position);
  })[0];
}

function getDistanceForPriority(state: EncounterState, actor: UnitState, target: UnitState): number {
  if (!actor.position || !target.position) {
    return 0;
  }

  return chebyshevDistance(actor.position, target.position);
}

function sortFighterTargets(state: EncounterState, actor: UnitState, units: UnitState[]): UnitState[] {
  return [...units].sort((left, right) => {
    if (left.currentHp !== right.currentHp) {
      return left.currentHp - right.currentHp;
    }

    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function countAdjacentAlliedUnits(state: EncounterState, actor: UnitState, target: UnitState): number {
  if (!target.position) {
    return 0;
  }

  return getUnitsByFaction(state, actor.faction).filter(
    (unit) =>
      unit.id !== actor.id &&
      isUnitConscious(unit) &&
      unit.position &&
      chebyshevDistance(unit.position, target.position!) <= 1
  ).length;
}

function sortPlayerCombatTargets(
  state: EncounterState,
  actor: UnitState,
  units: UnitState[],
  behavior: ResolvedPlayerBehavior
): UnitState[] {
  if (behavior === 'dumb') {
    return [...units].sort((left, right) => {
      const leftDistance = getDistanceForPriority(state, actor, left);
      const rightDistance = getDistanceForPriority(state, actor, right);

      if (leftDistance !== rightDistance) {
        return leftDistance - rightDistance;
      }

      return compareUnitIds(left.id, right.id);
    });
  }

  return [...units].sort((left, right) => {
    if (left.currentHp !== right.currentHp) {
      return left.currentHp - right.currentHp;
    }

    const leftAdjacency = countAdjacentAlliedUnits(state, actor, left);
    const rightAdjacency = countAdjacentAlliedUnits(state, actor, right);

    if (leftAdjacency !== rightAdjacency) {
      return rightAdjacency - leftAdjacency;
    }

    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function sortClosestTargets(state: EncounterState, actor: UnitState, units: UnitState[]): UnitState[] {
  return [...units].sort((left, right) => {
    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    if (left.currentHp !== right.currentHp) {
      return left.currentHp - right.currentHp;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function getConsciousFighterTargets(state: EncounterState): UnitState[] {
  return getUnitsByFaction(state, 'fighters').filter(isUnitConscious);
}

function getDownedFighterTargets(state: EncounterState): UnitState[] {
  return getUnitsByFaction(state, 'fighters').filter(isUnitDowned);
}

function sortKindTargets(state: EncounterState, actor: UnitState, units: UnitState[]): UnitState[] {
  return [...units].sort((left, right) => {
    const leftRatio = getHpRatio(left);
    const rightRatio = getHpRatio(right);

    if (leftRatio !== rightRatio) {
      return rightRatio - leftRatio;
    }

    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    if (right.currentHp !== left.currentHp) {
      return right.currentHp - left.currentHp;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function sortBalancedMonsterTargets(state: EncounterState, actor: UnitState, units: UnitState[]): UnitState[] {
  return [...units].sort((left, right) => {
    if (left.currentHp !== right.currentHp) {
      return left.currentHp - right.currentHp;
    }

    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function sortEvilConsciousTargets(state: EncounterState, actor: UnitState, units: UnitState[]): UnitState[] {
  return [...units].sort((left, right) => {
    const leftHealer = hasRoleTag(left, 'healer') ? 1 : 0;
    const rightHealer = hasRoleTag(right, 'healer') ? 1 : 0;

    if (leftHealer !== rightHealer) {
      return rightHealer - leftHealer;
    }

    const leftCaster = hasRoleTag(left, 'caster') ? 1 : 0;
    const rightCaster = hasRoleTag(right, 'caster') ? 1 : 0;

    if (leftCaster !== rightCaster) {
      return rightCaster - leftCaster;
    }

    const leftRatio = getHpRatio(left);
    const rightRatio = getHpRatio(right);

    if (leftRatio !== rightRatio) {
      return leftRatio - rightRatio;
    }

    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function sortDownedTargets(state: EncounterState, actor: UnitState, units: UnitState[]): UnitState[] {
  return [...units].sort((left, right) => {
    const leftDistance = getDistanceForPriority(state, actor, left);
    const rightDistance = getDistanceForPriority(state, actor, right);

    if (leftDistance !== rightDistance) {
      return leftDistance - rightDistance;
    }

    return compareUnitIds(left.id, right.id);
  });
}

function canIntentionallyProvokeOpportunityAttack(
  state: EncounterState,
  actor: UnitState,
  target: UnitState
): boolean {
  if (actor.faction === 'fighters') {
    if (state.playerBehavior !== 'smart') {
      return false;
    }

    void target;

    // No current enemies are marked high-value, so the smart-only provoke exception is dormant for now.
    return false;
  }

  if (state.monsterBehavior !== 'evil') {
    return false;
  }

  return isUnitDowned(target) || hasRoleTag(target, 'healer') || hasRoleTag(target, 'caster');
}

function getSafeReachableSquares(
  state: EncounterState,
  actorId: string,
  maxMoveSquares: number,
  allowProvoking = false
): ReachableSquare[] {
  const reachableSquares = getReachableSquares(state, actorId, maxMoveSquares);

  if (allowProvoking) {
    return reachableSquares;
  }

  return reachableSquares.filter((square) => !pathProvokesOpportunityAttack(state, actorId, square.path));
}

function findPreferredAdjacentSquare(
  state: EncounterState,
  moverId: string,
  targetId: string,
  maxSquares: number,
  allowProvoking = false
): ReachableSquare | null {
  const target = state.units[targetId];

  if (!target.position) {
    return null;
  }

  const candidates = getSafeReachableSquares(state, moverId, maxSquares, allowProvoking).filter(
    (square) => chebyshevDistance(square.position, target.position!) <= 1
  );

  return chooseClosestReachableSquare(candidates);
}

function findPreferredAdvancePath(
  state: EncounterState,
  moverId: string,
  targetId: string,
  maxSquares: number,
  allowProvoking = false
): ReachableSquare | null {
  const target = state.units[targetId];

  if (!target.position) {
    return null;
  }

  const adjacentPath = findPreferredAdjacentSquare(state, moverId, targetId, maxSquares, allowProvoking);

  if (adjacentPath) {
    return adjacentPath;
  }

  return chooseAdvanceSquare(getSafeReachableSquares(state, moverId, maxSquares, allowProvoking), target.position);
}

function buildMeleeAttackOptions(
  state: EncounterState,
  actor: UnitState,
  targets: UnitState[],
  moveSquares: number,
  weaponId: 'greatsword' | 'scimitar',
  seekFlanking: boolean
): MeleeAttackOption[] {
  const weapon = actor.attacks[weaponId];

  if (!weapon || !actor.position) {
    return [];
  }

  return targets.flatMap((target) => {
    if (!target.position) {
      return [];
    }

    const allowProvoking = canIntentionallyProvokeOpportunityAttack(state, actor, target);
    const candidateSquares = seekFlanking
      ? getSafeReachableSquares(state, actor.id, moveSquares, allowProvoking).filter(
          (square) => chebyshevDistance(square.position, target.position!) <= 1
        )
      : (() => {
          const path = findPreferredAdjacentSquare(state, actor.id, target.id, moveSquares, allowProvoking);
          return path ? [path] : [];
        })();
    const adjacentAllies = countAdjacentAlliedUnits(state, actor, target);

    return candidateSquares.map((square) => ({
      target,
      path: square.path,
      distance: square.distance,
      createsFlank: getAttackContext(state, actor.id, target.id, weapon, square.position, target.position!)
        .advantageSources.includes('flanking'),
      adjacentAllies
    }));
  });
}

function getSmartMeleeAttackOption(
  state: EncounterState,
  actor: UnitState,
  targets: UnitState[],
  moveSquares: number
): MeleeAttackOption | null {
  const options = buildMeleeAttackOptions(state, actor, targets, moveSquares, 'greatsword', true);

  if (options.length === 0) {
    return null;
  }

  return [...options].sort((left, right) => {
    if (left.createsFlank !== right.createsFlank) {
      return left.createsFlank ? -1 : 1;
    }

    if (left.target.currentHp !== right.target.currentHp) {
      return left.target.currentHp - right.target.currentHp;
    }

    if (left.adjacentAllies !== right.adjacentAllies) {
      return right.adjacentAllies - left.adjacentAllies;
    }

    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    const targetComparison = compareUnitIds(left.target.id, right.target.id);

    if (targetComparison !== 0) {
      return targetComparison;
    }

    return compareGridPositions(left.path[left.path.length - 1], right.path[right.path.length - 1]);
  })[0];
}

function chooseFirstTargetedPlan<T extends { targetId: string }>(
  targets: UnitState[],
  buildPlan: (target: UnitState) => T | null
): T | null {
  for (const target of targets) {
    const plan = buildPlan(target);

    if (plan) {
      return plan;
    }
  }

  return null;
}

function chooseKindTargetedPlan<T extends { targetId: string }>(
  preferredTargets: UnitState[],
  fallbackTargets: UnitState[],
  buildPlan: (target: UnitState) => T | null
): T | null {
  const preferredTarget = preferredTargets[0];

  if (preferredTarget) {
    const preferredPlan = buildPlan(preferredTarget);

    if (preferredPlan) {
      return preferredPlan;
    }
  }

  return chooseFirstTargetedPlan(fallbackTargets, buildPlan);
}

function chooseClosestMonsterMeleeOption(options: MeleeAttackOption[]): MeleeAttackOption | null {
  if (options.length === 0) {
    return null;
  }

  return [...options].sort((left, right) => {
    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    if (left.target.currentHp !== right.target.currentHp) {
      return left.target.currentHp - right.target.currentHp;
    }

    const targetComparison = compareUnitIds(left.target.id, right.target.id);

    if (targetComparison !== 0) {
      return targetComparison;
    }

    return compareGridPositions(left.path[left.path.length - 1], right.path[right.path.length - 1]);
  })[0];
}

function chooseBalancedMonsterMeleeOption(options: MeleeAttackOption[]): MeleeAttackOption | null {
  if (options.length === 0) {
    return null;
  }

  return [...options].sort((left, right) => {
    if (left.createsFlank !== right.createsFlank) {
      return left.createsFlank ? -1 : 1;
    }

    if (left.target.currentHp !== right.target.currentHp) {
      return left.target.currentHp - right.target.currentHp;
    }

    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    const targetComparison = compareUnitIds(left.target.id, right.target.id);

    if (targetComparison !== 0) {
      return targetComparison;
    }

    return compareGridPositions(left.path[left.path.length - 1], right.path[right.path.length - 1]);
  })[0];
}

function chooseEvilMonsterMeleeOption(options: MeleeAttackOption[]): MeleeAttackOption | null {
  if (options.length === 0) {
    return null;
  }

  return [...options].sort((left, right) => {
    const leftHealer = hasRoleTag(left.target, 'healer') ? 1 : 0;
    const rightHealer = hasRoleTag(right.target, 'healer') ? 1 : 0;

    if (leftHealer !== rightHealer) {
      return rightHealer - leftHealer;
    }

    const leftCaster = hasRoleTag(left.target, 'caster') ? 1 : 0;
    const rightCaster = hasRoleTag(right.target, 'caster') ? 1 : 0;

    if (leftCaster !== rightCaster) {
      return rightCaster - leftCaster;
    }

    const leftRatio = getHpRatio(left.target);
    const rightRatio = getHpRatio(right.target);

    if (leftRatio !== rightRatio) {
      return leftRatio - rightRatio;
    }

    if (left.createsFlank !== right.createsFlank) {
      return left.createsFlank ? -1 : 1;
    }

    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    const targetComparison = compareUnitIds(left.target.id, right.target.id);

    if (targetComparison !== 0) {
      return targetComparison;
    }

    return compareGridPositions(left.path[left.path.length - 1], right.path[right.path.length - 1]);
  })[0];
}

function buildRangedAttackPlan(
  state: EncounterState,
  actor: UnitState,
  target: UnitState,
  weaponId: 'javelin' | 'shortbow',
  maxMoveSquares: number,
  requireNormalRange: boolean,
  requireMovement: boolean,
  preferDistanceFromFaction?: 'fighters' | 'goblins',
  avoidOpportunityAttacks = true
): AttackPlan | null {
  const weapon = actor.attacks[weaponId];

  if (!weapon || !target.position || !actor.position) {
    return null;
  }

  const candidates = getSafeReachableSquares(state, actor.id, maxMoveSquares, !avoidOpportunityAttacks)
    .filter((square) => (requireMovement ? square.distance > 0 : true))
    .map((square) => ({
      ...square,
      context: getAttackContext(state, actor.id, target.id, weapon, square.position, target.position!)
    }))
    .filter((square) => square.context.legal)
    .filter((square) => (requireNormalRange ? square.context.withinNormalRange : true));

  if (candidates.length === 0) {
    return null;
  }

  const best = [...candidates].sort((left, right) => {
    if (left.context.withinNormalRange !== right.context.withinNormalRange) {
      return left.context.withinNormalRange ? -1 : 1;
    }

    const leftAdjacentPenalty = left.context.disadvantageSources.includes('adjacent_enemy') ? 1 : 0;
    const rightAdjacentPenalty = right.context.disadvantageSources.includes('adjacent_enemy') ? 1 : 0;

    if (leftAdjacentPenalty !== rightAdjacentPenalty) {
      return leftAdjacentPenalty - rightAdjacentPenalty;
    }

    if (left.context.coverAcBonus !== right.context.coverAcBonus) {
      return left.context.coverAcBonus - right.context.coverAcBonus;
    }

    if (preferDistanceFromFaction) {
      const leftDistance = getMinDistanceToFaction(state, left.position, preferDistanceFromFaction);
      const rightDistance = getMinDistanceToFaction(state, right.position, preferDistanceFromFaction);

      if (leftDistance !== rightDistance) {
        return rightDistance - leftDistance;
      }
    }

    if (left.distance !== right.distance) {
      return left.distance - right.distance;
    }

    if (left.position.x !== right.position.x) {
      return left.position.x - right.position.x;
    }

    return left.position.y - right.position.y;
  })[0];

  return {
    targetId: target.id,
    weaponId,
    path: best.path
  };
}

function buildPostActionAdvance(
  state: EncounterState,
  actor: UnitState,
  targetId: string,
  attackPosition: GridPosition,
  remainingMoveSquares: number
): MovementPlan | undefined {
  if (remainingMoveSquares <= 0) {
    return undefined;
  }

  const projectedState: EncounterState = {
    ...state,
    units: {
      ...state.units,
      [actor.id]: {
        ...actor,
        position: { ...attackPosition }
      }
    }
  };
  const advance = findPreferredAdvancePath(projectedState, actor.id, targetId, remainingMoveSquares);

  if (!advance || advance.distance === 0) {
    return undefined;
  }

  return {
    path: advance.path,
    mode: 'move'
  };
}

function getFighterDecision(state: EncounterState, actor: UnitState): TurnDecision {
  const moveSquares = getMoveSquares(actor);
  const dashSquares = moveSquares * 2;
  const behavior = state.playerBehavior;
  const bonusAction =
    actor.currentHp <= Math.floor(actor.maxHp / 2) && actor.resources.secondWindUses > 0
      ? { kind: 'second_wind' as const, timing: 'before_action' as const }
      : undefined;

  if (state.rescueSubphase) {
    const dyingAllies = sortFighterTargets(
      state,
      actor,
      getUnitsByFaction(state, 'fighters').filter((unit) => unit.id !== actor.id && isUnitDying(unit))
    );
    const target = dyingAllies[0];

    if (!target) {
      return {
        action: {
          kind: 'skip',
          reason: 'No ally requires stabilization.'
        }
      };
    }

    const stabilizePath = findPreferredAdjacentSquare(state, actor.id, target.id, moveSquares);

    if (stabilizePath) {
      return {
        preActionMovement: stabilizePath.distance > 0 ? { path: stabilizePath.path, mode: 'move' } : undefined,
        action: {
          kind: 'stabilize',
          targetId: target.id
        }
      };
    }

    const advance = findPreferredAdvancePath(state, actor.id, target.id, moveSquares);

    return {
      preActionMovement: advance && advance.distance > 0 ? { path: advance.path, mode: 'move' } : undefined,
      action: {
        kind: 'skip',
        reason: `Moving toward ${target.id} to stabilize on a later turn.`
      }
    };
  }

  const consciousGoblins = sortPlayerCombatTargets(
    state,
    actor,
    getUnitsByFaction(state, 'goblins').filter((unit) => !unit.conditions.dead),
    behavior
  );

  const smartMeleeOption =
    behavior === 'smart' ? getSmartMeleeAttackOption(state, actor, consciousGoblins, moveSquares) : null;

  if (smartMeleeOption) {
    return {
      bonusAction,
      preActionMovement:
        smartMeleeOption.distance > 0 ? { path: smartMeleeOption.path, mode: 'move' } : undefined,
      action: {
        kind: 'attack',
        targetId: smartMeleeOption.target.id,
        weaponId: 'greatsword'
      }
    };
  }

  for (const target of consciousGoblins) {
    const allowProvoking = canIntentionallyProvokeOpportunityAttack(state, actor, target);
    const meleePath = findPreferredAdjacentSquare(state, actor.id, target.id, moveSquares, allowProvoking);

    if (meleePath) {
      return {
        bonusAction,
        preActionMovement: meleePath.distance > 0 ? { path: meleePath.path, mode: 'move' } : undefined,
        action: {
          kind: 'attack',
          targetId: target.id,
          weaponId: 'greatsword'
        }
      };
    }
  }

  if (actor.resources.javelins > 0) {
    for (const target of consciousGoblins) {
      const javelinPlan = buildRangedAttackPlan(
        state,
        actor,
        target,
        'javelin',
        moveSquares,
        true,
        false,
        undefined,
        true
      );

      if (javelinPlan) {
        const preActionMovement =
          javelinPlan.path.length > 1 ? { path: javelinPlan.path, mode: 'move' as const } : undefined;
        const attackPosition = javelinPlan.path[javelinPlan.path.length - 1] ?? actor.position;
        const postActionMovement = attackPosition
          ? buildPostActionAdvance(
              state,
              actor,
              javelinPlan.targetId,
              attackPosition,
              moveSquares - getMovementDistance(preActionMovement)
            )
          : undefined;

        return {
          bonusAction,
          preActionMovement,
          postActionMovement,
          action: {
            kind: 'attack',
            targetId: javelinPlan.targetId,
            weaponId: 'javelin'
          }
        };
      }
    }
  }

  const nearestTarget = consciousGoblins[0];

  if (!nearestTarget) {
    return {
      action: {
        kind: 'skip',
        reason: 'No goblins remain.'
      }
    };
  }

  const dashPath = findPreferredAdvancePath(
    state,
    actor.id,
    nearestTarget.id,
    dashSquares,
    canIntentionallyProvokeOpportunityAttack(state, actor, nearestTarget)
  );

  if (dashPath && dashPath.distance > 0) {
    return {
      bonusAction,
      postActionMovement: {
        path: dashPath.path,
        mode: 'dash'
      },
      action: {
        kind: 'dash',
        reason: `Dashing toward ${nearestTarget.id}.`
      }
    };
  }

  if (actor.resources.javelins > 0) {
    for (const target of consciousGoblins) {
      const javelinPlan = buildRangedAttackPlan(
        state,
        actor,
        target,
        'javelin',
        moveSquares,
        false,
        false,
        undefined,
        true
      );

      if (javelinPlan) {
        const preActionMovement =
          javelinPlan.path.length > 1 ? { path: javelinPlan.path, mode: 'move' as const } : undefined;
        const attackPosition = javelinPlan.path[javelinPlan.path.length - 1] ?? actor.position;
        const postActionMovement = attackPosition
          ? buildPostActionAdvance(
              state,
              actor,
              javelinPlan.targetId,
              attackPosition,
              moveSquares - getMovementDistance(preActionMovement)
            )
          : undefined;

        return {
          bonusAction,
          preActionMovement,
          postActionMovement,
          action: {
            kind: 'attack',
            targetId: javelinPlan.targetId,
            weaponId: 'javelin'
          }
        };
      }
    }
  }

  return {
    bonusAction,
    action: {
      kind: 'skip',
      reason: 'No legal movement remains.'
    }
  };
}

function getGoblinMeleeDecision(state: EncounterState, actor: UnitState): TurnDecision {
  const moveSquares = getMoveSquares(actor);
  const dashSquares = moveSquares * 2;
  const consciousTargets = getConsciousFighterTargets(state);
  const downedTargets = sortDownedTargets(state, actor, getDownedFighterTargets(state));
  const adjacentDownedTargets = sortDownedTargets(state, actor, getAdjacentDownedFighters(state, actor));

  if (state.monsterBehavior === 'evil' && adjacentDownedTargets.length > 0) {
    return {
      action: {
        kind: 'attack',
        targetId: adjacentDownedTargets[0].id,
        weaponId: 'scimitar'
      }
    };
  }

  const kindTargets = sortKindTargets(state, actor, consciousTargets);
  const closestTargets = sortClosestTargets(state, actor, consciousTargets);
  const balancedTargets = sortBalancedMonsterTargets(state, actor, consciousTargets);
  const evilConsciousTargets = sortEvilConsciousTargets(state, actor, consciousTargets);
  let meleeOption: MeleeAttackOption | null = null;

  if (state.monsterBehavior === 'kind') {
    const preferredTarget = kindTargets[0];
    meleeOption = preferredTarget
      ? chooseClosestMonsterMeleeOption(
          buildMeleeAttackOptions(state, actor, [preferredTarget], moveSquares, 'scimitar', false)
        )
      : null;

    if (!meleeOption) {
      meleeOption = chooseClosestMonsterMeleeOption(
        buildMeleeAttackOptions(state, actor, closestTargets, moveSquares, 'scimitar', false)
      );
    }
  } else if (state.monsterBehavior === 'balanced') {
    meleeOption = chooseBalancedMonsterMeleeOption(
      buildMeleeAttackOptions(state, actor, balancedTargets, moveSquares, 'scimitar', false)
    );
  } else {
    meleeOption = chooseEvilMonsterMeleeOption(
      buildMeleeAttackOptions(state, actor, evilConsciousTargets, moveSquares, 'scimitar', true)
    );

    if (!meleeOption) {
      meleeOption = chooseClosestMonsterMeleeOption(
        buildMeleeAttackOptions(state, actor, downedTargets, moveSquares, 'scimitar', true)
      );
    }
  }

  if (meleeOption) {
    return {
      preActionMovement: meleeOption.distance > 0 ? { path: meleeOption.path, mode: 'move' } : undefined,
      action: {
        kind: 'attack',
        targetId: meleeOption.target.id,
        weaponId: 'scimitar'
      }
    };
  }

  const dashTarget =
    state.monsterBehavior === 'kind'
      ? kindTargets[0] ?? closestTargets[0]
      : state.monsterBehavior === 'balanced'
        ? balancedTargets[0]
        : evilConsciousTargets[0] ?? downedTargets[0];

  if (!dashTarget) {
    return {
      action: {
        kind: 'skip',
        reason: 'No fighters remain.'
      }
    };
  }

  const dashPath = findPreferredAdvancePath(
    state,
    actor.id,
    dashTarget.id,
    dashSquares,
    canIntentionallyProvokeOpportunityAttack(state, actor, dashTarget)
  );

  if (dashPath && dashPath.distance > 0) {
    return {
      postActionMovement: {
        path: dashPath.path,
        mode: 'dash'
      },
      action: {
        kind: 'dash',
        reason: `Dashing into melee against ${dashTarget.id}.`
      }
    };
  }

  return {
    action: {
      kind: 'skip',
      reason: 'No legal movement remains.'
    }
  };
}

function getAdjacentConsciousFighters(state: EncounterState, actor: UnitState): UnitState[] {
  return getUnitsByFaction(state, 'fighters').filter(
    (unit) =>
      unit.position &&
      actor.position &&
      isUnitConscious(unit) &&
      chebyshevDistance(actor.position, unit.position) <= 1
  );
}

function getAdjacentDownedFighters(state: EncounterState, actor: UnitState): UnitState[] {
  return getUnitsByFaction(state, 'fighters').filter(
    (unit) =>
      unit.position &&
      actor.position &&
      isUnitDowned(unit) &&
      chebyshevDistance(actor.position, unit.position) <= 1
  );
}

function getGoblinArcherDecision(state: EncounterState, actor: UnitState): TurnDecision {
  const moveSquares = getMoveSquares(actor);
  const dashSquares = moveSquares * 2;
  const consciousTargets = getConsciousFighterTargets(state);
  const kindTargets = sortKindTargets(state, actor, consciousTargets);
  const closestTargets = sortClosestTargets(state, actor, consciousTargets);
  const balancedTargets = sortBalancedMonsterTargets(state, actor, consciousTargets);
  const evilConsciousTargets = sortEvilConsciousTargets(state, actor, consciousTargets);
  const downedTargets = sortDownedTargets(state, actor, getDownedFighterTargets(state));
  const adjacentDownedTargets = sortDownedTargets(state, actor, getAdjacentDownedFighters(state, actor));
  const prioritizedConsciousTargets =
    state.monsterBehavior === 'kind'
      ? kindTargets
      : state.monsterBehavior === 'balanced'
        ? balancedTargets
        : evilConsciousTargets;

  if (state.monsterBehavior === 'evil' && adjacentDownedTargets.length > 0) {
    return {
      action: {
        kind: 'attack',
        targetId: adjacentDownedTargets[0].id,
        weaponId: 'scimitar'
      }
    };
  }

  const adjacentConscious = getAdjacentConsciousFighters(state, actor);

  if (adjacentConscious.length > 0 && prioritizedConsciousTargets.length > 0) {
    const bowPlan =
      state.monsterBehavior === 'kind'
        ? chooseKindTargetedPlan(kindTargets, closestTargets, (target) =>
            buildRangedAttackPlan(state, actor, target, 'shortbow', moveSquares, true, true, 'fighters', false)
          )
        : chooseFirstTargetedPlan(prioritizedConsciousTargets, (target) =>
            buildRangedAttackPlan(state, actor, target, 'shortbow', moveSquares, true, true, 'fighters', false)
          );

    if (bowPlan) {
      return {
        bonusAction: {
          kind: 'disengage',
          timing: 'before_action'
        },
        preActionMovement: {
          path: bowPlan.path,
          mode: 'move'
        },
        action: {
          kind: 'attack',
          targetId: bowPlan.targetId,
          weaponId: 'shortbow'
        }
      };
    }

    const retreatTarget =
      state.monsterBehavior === 'kind'
        ? kindTargets[0] ?? closestTargets[0]
        : state.monsterBehavior === 'balanced'
          ? balancedTargets[0]
          : evilConsciousTargets[0] ?? downedTargets[0];
    const retreatPath = retreatTarget
      ? findPreferredAdvancePath(state, actor.id, retreatTarget.id, moveSquares, true)
      : null;

    return {
      bonusAction: {
        kind: 'disengage',
        timing: 'before_action'
      },
      preActionMovement: retreatPath && retreatPath.distance > 0 ? { path: retreatPath.path, mode: 'move' } : undefined,
      action: {
        kind: 'skip',
        reason: 'Disengaging to find a future bow shot.'
      }
    };
  }

  const currentNormalAttack =
    state.monsterBehavior === 'kind'
      ? chooseKindTargetedPlan(kindTargets, closestTargets, (target) => {
          const currentContext = getAttackContext(state, actor.id, target.id, actor.attacks.shortbow!);

          return currentContext.legal && currentContext.withinNormalRange ? { targetId: target.id } : null;
        })
      : chooseFirstTargetedPlan(prioritizedConsciousTargets, (target) => {
          const currentContext = getAttackContext(state, actor.id, target.id, actor.attacks.shortbow!);

          return currentContext.legal && currentContext.withinNormalRange ? { targetId: target.id } : null;
        });

  if (currentNormalAttack) {
    return {
      action: {
        kind: 'attack',
        targetId: currentNormalAttack.targetId,
        weaponId: 'shortbow'
      }
    };
  }

  const moveAndShoot =
    state.monsterBehavior === 'kind'
      ? chooseKindTargetedPlan(kindTargets, closestTargets, (target) =>
          buildRangedAttackPlan(
            state,
            actor,
            target,
            'shortbow',
            moveSquares,
            true,
            false,
            'fighters',
            !canIntentionallyProvokeOpportunityAttack(state, actor, target)
          )
        )
      : chooseFirstTargetedPlan(prioritizedConsciousTargets, (target) =>
          buildRangedAttackPlan(
            state,
            actor,
            target,
            'shortbow',
            moveSquares,
            true,
            false,
            'fighters',
            !canIntentionallyProvokeOpportunityAttack(state, actor, target)
          )
        );

  if (moveAndShoot && moveAndShoot.path.length > 1) {
    return {
      preActionMovement: {
        path: moveAndShoot.path,
        mode: 'move'
      },
      action: {
        kind: 'attack',
        targetId: moveAndShoot.targetId,
        weaponId: 'shortbow'
      }
    };
  }

  const currentLongRangeAttack =
    state.monsterBehavior === 'kind'
      ? chooseKindTargetedPlan(kindTargets, closestTargets, (target) => {
          const currentContext = getAttackContext(state, actor.id, target.id, actor.attacks.shortbow!);

          return currentContext.legal && currentContext.withinLongRange ? { targetId: target.id } : null;
        })
      : chooseFirstTargetedPlan(prioritizedConsciousTargets, (target) => {
          const currentContext = getAttackContext(state, actor.id, target.id, actor.attacks.shortbow!);

          return currentContext.legal && currentContext.withinLongRange ? { targetId: target.id } : null;
        });

  if (currentLongRangeAttack) {
    return {
      action: {
        kind: 'attack',
        targetId: currentLongRangeAttack.targetId,
        weaponId: 'shortbow'
      }
    };
  }

  if (state.monsterBehavior === 'evil') {
    const downedNormalAttack = chooseFirstTargetedPlan(downedTargets, (target) => {
      const currentContext = getAttackContext(state, actor.id, target.id, actor.attacks.shortbow!);

      return currentContext.legal && currentContext.withinNormalRange ? { targetId: target.id } : null;
    });

    if (downedNormalAttack) {
      return {
        action: {
          kind: 'attack',
          targetId: downedNormalAttack.targetId,
          weaponId: 'shortbow'
        }
      };
    }

    const downedMoveAndShoot = chooseFirstTargetedPlan(downedTargets, (target) =>
      buildRangedAttackPlan(
        state,
        actor,
        target,
        'shortbow',
        moveSquares,
        true,
        false,
        'fighters',
        !canIntentionallyProvokeOpportunityAttack(state, actor, target)
      )
    );

    if (downedMoveAndShoot && downedMoveAndShoot.path.length > 1) {
      return {
        preActionMovement: {
          path: downedMoveAndShoot.path,
          mode: 'move'
        },
        action: {
          kind: 'attack',
          targetId: downedMoveAndShoot.targetId,
          weaponId: 'shortbow'
        }
      };
    }

    const downedLongRangeAttack = chooseFirstTargetedPlan(downedTargets, (target) => {
      const currentContext = getAttackContext(state, actor.id, target.id, actor.attacks.shortbow!);

      return currentContext.legal && currentContext.withinLongRange ? { targetId: target.id } : null;
    });

    if (downedLongRangeAttack) {
      return {
        action: {
          kind: 'attack',
          targetId: downedLongRangeAttack.targetId,
          weaponId: 'shortbow'
        }
      };
    }
  }

  const nearestTarget =
    state.monsterBehavior === 'kind'
      ? kindTargets[0] ?? closestTargets[0]
      : state.monsterBehavior === 'balanced'
        ? balancedTargets[0]
        : evilConsciousTargets[0] ?? downedTargets[0];

  if (!nearestTarget) {
    return {
      action: {
        kind: 'skip',
        reason: 'No fighters remain.'
      }
    };
  }

  const dashPath = findPreferredAdvancePath(
    state,
    actor.id,
    nearestTarget.id,
    dashSquares,
    canIntentionallyProvokeOpportunityAttack(state, actor, nearestTarget)
  );

  if (dashPath && dashPath.distance > 0) {
    return {
      postActionMovement: {
        path: dashPath.path,
        mode: 'dash'
      },
      action: {
        kind: 'dash',
        reason: `Dashing to improve shortbow position against ${nearestTarget.id}.`
      }
    };
  }

  return {
    action: {
      kind: 'skip',
      reason: 'No legal movement remains.'
    }
  };
}

export function chooseTurnDecision(state: EncounterState, actorId: string): TurnDecision {
  const actor = state.units[actorId];

  if (actor.faction === 'fighters') {
    return getFighterDecision(state, actor);
  }

  if (state.rescueSubphase) {
    return {
      action: {
        kind: 'skip',
        reason: 'Goblins take no actions during the rescue subphase.'
      }
    };
  }

  if (actor.combatRole === 'goblin_melee') {
    return getGoblinMeleeDecision(state, actor);
  }

  return getGoblinArcherDecision(state, actor);
}
