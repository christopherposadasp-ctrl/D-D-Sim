import { describe, expect, it } from "vitest";

import type {
  CombatEvent,
  EncounterState,
  GridPosition,
  ReplayFrame,
  UnitState,
} from "../shared/sim/types";
import {
  getReplayAttackLine,
  getReplayDelayMs,
  getReplayStepDelayMs,
} from "../ui/replay";

function buildTestUnit(id: string, position: GridPosition): UnitState {
  return {
    id,
    faction: id.startsWith("F") ? "fighters" : "goblins",
    combatRole: id.startsWith("F") ? "paladin" : "young_white_dragon_boss",
    templateName: id.startsWith("F") ? "Paladin" : "Young White Dragon Boss",
    roleTags: [],
    currentHp: 20,
    maxHp: 20,
    temporaryHitPoints: 0,
    ac: 15,
    speed: 30,
    effectiveSpeed: 30,
    initiativeMod: 0,
    initiativeScore: 10,
    abilityMods: { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 },
    passivePerception: 10,
    sizeCategory: "medium",
    footprint: { width: 1, height: 1 },
    conditions: { unconscious: false, prone: false, dead: false },
    deathSaveSuccesses: 0,
    deathSaveFailures: 0,
    stable: false,
    resources: {
      secondWindUses: 0,
      javelins: 0,
      rageUses: 0,
      handaxes: 0,
      actionSurgeUses: 0,
      superiorityDice: 0,
      focusPoints: 0,
      uncannyMetabolismUses: 0,
      spellSlotsLevel1: 0,
      spellSlotsLevel2: 0,
      spellSlotsLevel3: 0,
      layOnHandsPoints: 0,
      channelDivinityUses: 0,
    },
    position,
    temporaryEffects: [],
    reactionAvailable: true,
    attacks: {},
    medicineModifier: 0,
  };
}

function buildTestState(units: Record<string, UnitState>): EncounterState {
  return {
    seed: "test-seed",
    playerBehavior: "smart",
    monsterBehavior: "balanced",
    rngState: 1,
    round: 1,
    initiativeOrder: Object.keys(units),
    initiativeScores: Object.fromEntries(Object.keys(units).map((id) => [id, 10])),
    activeCombatantIndex: 0,
    units,
    combatLog: [],
    winner: null,
    terminalState: "ongoing",
    rescueSubphase: false,
  };
}

function buildMoveEvent(actorId: string, path: GridPosition[]): CombatEvent {
  return {
    round: 1,
    actorId,
    targetIds: [],
    eventType: "move",
    rawRolls: {},
    resolvedTotals: {},
    movementDetails: {
      start: path[0],
      end: path[path.length - 1],
      path,
      distance: path.length - 1,
    },
    damageDetails: null,
    conditionDeltas: [],
    textSummary: `${actorId} moves.`,
  };
}

function buildAttackEvent(actorId: string, targetId: string): CombatEvent {
  return {
    round: 1,
    actorId,
    targetIds: [targetId],
    eventType: "attack",
    rawRolls: {},
    resolvedTotals: {},
    movementDetails: null,
    damageDetails: null,
    conditionDeltas: [],
    textSummary: `${actorId} attacks ${targetId}.`,
  };
}

describe("getReplayDelayMs", () => {
  it("paces a 40-frame replay at about three minutes", () => {
    expect(getReplayDelayMs(40)).toBe(4615);
  });

  it("paces the 37 visible presentation steps at about three minutes", () => {
    expect(getReplayStepDelayMs(37)).toBe(4864);
  });

  it("clamps unusually short and long delays", () => {
    expect(getReplayDelayMs(1)).toBe(1000);
    expect(getReplayDelayMs(2)).toBe(6000);
    expect(getReplayDelayMs(1000)).toBe(1200);
  });
});

describe("getReplayAttackLine", () => {
  it("uses unit positions at the attack event instead of later frame-end movement", () => {
    const previousState = buildTestState({
      F2: buildTestUnit("F2", { x: 15, y: 2 }),
      E17: buildTestUnit("E17", { x: 13, y: 13 }),
    });
    const currentState = buildTestState({
      F2: buildTestUnit("F2", { x: 9, y: 8 }),
      E17: buildTestUnit("E17", { x: 10, y: 10 }),
    });
    const frame: ReplayFrame = {
      index: 85,
      round: 5,
      activeCombatantId: "F2",
      state: currentState,
      events: [
        buildMoveEvent("F2", [
          { x: 15, y: 2 },
          { x: 10, y: 7 },
        ]),
        buildAttackEvent("F2", "E17"),
        buildMoveEvent("F2", [
          { x: 10, y: 7 },
          { x: 9, y: 8 },
        ]),
        buildMoveEvent("E17", [
          { x: 13, y: 13 },
          { x: 10, y: 10 },
        ]),
      ],
    };

    expect(getReplayAttackLine(frame, currentState, previousState)).toEqual(
      expect.objectContaining({
        actorId: "F2",
        targetId: "E17",
        from: { x: 10, y: 7 },
        to: { x: 13, y: 13 },
      }),
    );
  });

  it("prioritizes reaction attacks over later active-combatant attacks", () => {
    const previousState = buildTestState({
      F1: buildTestUnit("F1", { x: 7, y: 7 }),
      F2: buildTestUnit("F2", { x: 9, y: 8 }),
      E17: buildTestUnit("E17", { x: 10, y: 10 }),
    });
    const currentState = buildTestState({
      F1: buildTestUnit("F1", { x: 7, y: 7 }),
      F2: buildTestUnit("F2", { x: 9, y: 8 }),
      E17: buildTestUnit("E17", { x: 9, y: 9 }),
    });
    const frame: ReplayFrame = {
      index: 104,
      round: 6,
      activeCombatantId: "E17",
      state: currentState,
      events: [
        buildMoveEvent("E17", [
          { x: 10, y: 10 },
          { x: 9, y: 9 },
        ]),
        buildAttackEvent("E17", "F1"),
        {
          ...buildAttackEvent("F2", "E17"),
          textSummary: "Opportunity attack: F2 attacks E17 with Longsword: miss.",
        },
        buildAttackEvent("E17", "F2"),
      ],
    };

    expect(getReplayAttackLine(frame, currentState, previousState)).toEqual(
      expect.objectContaining({
        actorId: "F2",
        targetId: "E17",
        from: { x: 9, y: 8 },
        to: { x: 9, y: 9 },
        eventIndex: 2,
      }),
    );
  });

  it("does not draw direct attack lines for cold breath area damage", () => {
    const currentState = buildTestState({
      F3: buildTestUnit("F3", { x: 4, y: 7 }),
      E17: buildTestUnit("E17", { x: 9, y: 9 }),
    });
    const coldBreathAttack = buildAttackEvent("E17", "F3");
    coldBreathAttack.resolvedTotals = { specialAction: "cold_breath" };
    coldBreathAttack.textSummary =
      "E17's Cold Breath hits F3 for 20 cold damage after a successful save.";

    const frame: ReplayFrame = {
      index: 41,
      round: 3,
      activeCombatantId: "F1",
      state: currentState,
      events: [coldBreathAttack],
    };

    expect(getReplayAttackLine(frame, currentState, null)).toBeNull();
  });
});
