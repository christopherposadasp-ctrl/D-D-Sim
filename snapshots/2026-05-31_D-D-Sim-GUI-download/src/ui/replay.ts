import type {
  CombatEvent,
  EncounterState,
  Footprint,
  GridPosition,
  ReplayFrame,
  UnitState,
} from "../shared/sim/types";
import { MEDIUM_FOOTPRINT } from "./catalog";

const TARGET_REPLAY_DURATION_MS = 3 * 60 * 1000;

export function getReplayStepDelayMs(stepCount: number): number {
  if (stepCount <= 0) {
    return 1000;
  }

  const delay = Math.floor(TARGET_REPLAY_DURATION_MS / stepCount);

  return Math.max(1200, Math.min(delay, 6000));
}

export function getReplayDelayMs(frameCount: number): number {
  if (frameCount <= 1) {
    return 1000;
  }

  return getReplayStepDelayMs(frameCount - 1);
}

export function getActiveReplayEvents(
  frame: ReplayFrame | null,
): CombatEvent[] {
  if (!frame?.activeCombatantId) {
    return [];
  }

  return frame.events.filter(
    (event) => event.actorId === frame.activeCombatantId,
  );
}

export function getActiveReplayMovementEvents(
  frame: ReplayFrame | null,
): CombatEvent[] {
  return getActiveReplayEvents(frame).filter(
    (event) => event.eventType === "move",
  );
}

export function getActiveReplayAttackEvent(
  frame: ReplayFrame | null,
): CombatEvent | null {
  return (
    [...getActiveReplayEvents(frame)]
      .reverse()
      .find((event) => event.eventType === "attack") ?? null
  );
}

export interface ReplayAttackLine {
  actorId: string;
  targetId: string;
  from: GridPosition;
  to: GridPosition;
  fromFootprint: Footprint;
  toFootprint: Footprint;
  eventIndex: number;
}

function getCombatEventEndPosition(event: CombatEvent): GridPosition | null {
  const path = event.movementDetails?.path;

  return (
    event.movementDetails?.end ??
    (path && path.length > 0 ? path[path.length - 1] : null)
  );
}

function getCombatEventStartPosition(event: CombatEvent): GridPosition | null {
  const path = event.movementDetails?.path;

  return (
    event.movementDetails?.start ??
    (path && path.length > 0 ? path[0] : null)
  );
}

function getStateUnit(
  unitId: string,
  ...states: Array<EncounterState | null>
): UnitState | undefined {
  return states.map((state) => state?.units[unitId]).find(Boolean);
}

function getPositionAtReplayEvent(params: {
  unitId: string;
  frame: ReplayFrame;
  attackEventIndex: number;
  currentState: EncounterState | null;
  previousState: EncounterState | null;
}): GridPosition | undefined {
  const positions = new Map<string, GridPosition>();
  const hasFrameStartPosition = new Set<string>();

  for (const [unitId, unit] of Object.entries(params.currentState?.units ?? {})) {
    if (unit.position) {
      positions.set(unitId, unit.position);
    }
  }

  for (const [unitId, unit] of Object.entries(params.previousState?.units ?? {})) {
    if (unit.position) {
      positions.set(unitId, unit.position);
      hasFrameStartPosition.add(unitId);
    }
  }

  const seededMovementStarts = new Set<string>();

  for (const event of params.frame.events) {
    const start = getCombatEventStartPosition(event);

    if (
      start &&
      !hasFrameStartPosition.has(event.actorId) &&
      !seededMovementStarts.has(event.actorId)
    ) {
      positions.set(event.actorId, start);
      seededMovementStarts.add(event.actorId);
    }
  }

  for (const event of params.frame.events.slice(0, params.attackEventIndex)) {
    const end = getCombatEventEndPosition(event);

    if (end) {
      positions.set(event.actorId, end);
    }
  }

  return positions.get(params.unitId);
}

function getStringResolvedField(
  event: CombatEvent,
  fieldName: string,
): string {
  const value = event.resolvedTotals[fieldName];

  return typeof value === "string" ? value.toLowerCase() : "";
}

function isAttackLineEligibleEvent(event: CombatEvent): boolean {
  if (event.eventType !== "attack" || event.targetIds.length === 0) {
    return false;
  }

  const text = event.textSummary.toLowerCase();
  const specialAction = getStringResolvedField(event, "specialAction");
  const spellId = getStringResolvedField(event, "spellId");

  if (
    specialAction === "cold_breath" ||
    text.includes("cold breath") ||
    spellId === "fireball" ||
    event.resolvedTotals.radiusFeet !== undefined ||
    event.resolvedTotals.radiusSquares !== undefined
  ) {
    return false;
  }

  return true;
}

function getReplayAttackEventIndex(frame: ReplayFrame): number {
  for (let index = frame.events.length - 1; index >= 0; index -= 1) {
    const event = frame.events[index];

    if (
      event.actorId !== frame.activeCombatantId &&
      isAttackLineEligibleEvent(event)
    ) {
      return index;
    }
  }

  for (let index = frame.events.length - 1; index >= 0; index -= 1) {
    if (isAttackLineEligibleEvent(frame.events[index])) {
      return index;
    }
  }

  return -1;
}

export function getReplayAttackLine(
  frame: ReplayFrame | null,
  currentState: EncounterState | null,
  previousState: EncounterState | null,
): ReplayAttackLine | null {
  if (!frame?.activeCombatantId) {
    return null;
  }

  const attackEventIndex = getReplayAttackEventIndex(frame);
  const attackEvent =
    attackEventIndex >= 0 ? frame.events[attackEventIndex] : null;
  const targetId = attackEvent?.targetIds[0] ?? null;

  if (!attackEvent || !targetId) {
    return null;
  }

  const from = getPositionAtReplayEvent({
    unitId: attackEvent.actorId,
    frame,
    attackEventIndex,
    currentState,
    previousState,
  });
  const to = getPositionAtReplayEvent({
    unitId: targetId,
    frame,
    attackEventIndex,
    currentState,
    previousState,
  });

  if (!from || !to) {
    return null;
  }

  const actor = getStateUnit(attackEvent.actorId, currentState, previousState);
  const target = getStateUnit(targetId, currentState, previousState);

  return {
    actorId: attackEvent.actorId,
    targetId,
    from,
    to,
    fromFootprint: actor?.footprint ?? MEDIUM_FOOTPRINT,
    toFootprint: target?.footprint ?? MEDIUM_FOOTPRINT,
    eventIndex: attackEventIndex,
  };
}
