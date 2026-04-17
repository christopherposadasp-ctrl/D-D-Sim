import { describe, expect, it } from 'vitest';

import { createEncounter, runBatch, runEncounter, stepEncounter, summarizeEncounter } from '../engine';
import { DEFAULT_POSITIONS } from '../engine/constants';

describe('engine determinism', () => {
  it('returns bit-identical encounter results for the same seed and layout', () => {
    const first = runEncounter({ seed: 'golden-seed', placements: DEFAULT_POSITIONS });
    const second = runEncounter({ seed: 'golden-seed', placements: DEFAULT_POSITIONS });

    expect(first.events).toEqual(second.events);
    expect(first.finalState).toEqual(second.finalState);
    expect(first.replayFrames).toEqual(second.replayFrames);
  });

  it('produces stable batch aggregates from a base seed', () => {
    const summary = runBatch({
      seed: 'batch-seed',
      batchSize: 5,
      placements: DEFAULT_POSITIONS
    });

    expect(summary.batchSize).toBe(5);
    expect(summary.seed).toBe('batch-seed');
    expect(summary.playerWinRate + summary.goblinWinRate + summary.mutualAnnihilationRate).toBeCloseTo(1, 10);
  });

  it('alternates smart and dumb player runs when balanced behavior is selected', () => {
    const summary = runBatch({
      seed: 'balanced-batch-seed',
      batchSize: 4,
      placements: DEFAULT_POSITIONS,
      playerBehavior: 'balanced',
      monsterBehavior: 'balanced'
    });

    expect(summary.playerBehavior).toBe('balanced');
    expect(summary.monsterBehavior).toBe('balanced');
    expect(summary.smartRunCount).toBe(2);
    expect(summary.dumbRunCount).toBe(2);
    expect(summary.smartPlayerWinRate).not.toBeNull();
    expect(summary.dumbPlayerWinRate).not.toBeNull();
  });

  it('supports combined DM batches with per-setting summaries', () => {
    const summary = runBatch({
      seed: 'combined-dm-batch',
      batchSize: 2,
      placements: DEFAULT_POSITIONS,
      playerBehavior: 'balanced',
      monsterBehavior: 'combined'
    });

    expect(summary.monsterBehavior).toBe('combined');
    expect(summary.batchSize).toBe(2);
    expect(summary.totalRuns).toBe(6);
    expect(summary.combinationSummaries).toHaveLength(3);
    expect(summary.combinationSummaries?.map((entry) => entry.monsterBehavior)).toEqual([
      'kind',
      'balanced',
      'evil'
    ]);
    expect(summary.combinationSummaries?.every((entry) => entry.totalRuns === 2)).toBe(true);
  });

  it('summarizes completed encounters', () => {
    const result = runEncounter({ seed: 'summary-seed', placements: DEFAULT_POSITIONS });
    const summary = summarizeEncounter(result.finalState);

    expect(summary.seed).toBe('summary-seed');
    expect(summary.playerBehavior).toBe('smart');
    expect(summary.monsterBehavior).toBe('balanced');
    expect(summary.rounds).toBeGreaterThan(0);
    expect(summary.goblinsKilled).toBeGreaterThanOrEqual(0);
    expect(summary.fighterDeaths).toBeGreaterThanOrEqual(0);
  });

  it('loads the exact default coordinates', () => {
    const encounter = createEncounter({ seed: 'default-layout', placements: DEFAULT_POSITIONS });

    for (const [unitId, expectedPosition] of Object.entries(DEFAULT_POSITIONS)) {
      expect(encounter.units[unitId].position).toEqual(expectedPosition);
    }
  });

  it('loads custom placements exactly', () => {
    const placements = {
      ...DEFAULT_POSITIONS,
      F1: { x: 2, y: 6 },
      F2: { x: 2, y: 8 },
      F3: { x: 2, y: 10 },
      G5: { x: 13, y: 4 },
      G6: { x: 13, y: 8 },
      G7: { x: 13, y: 12 }
    };
    const encounter = createEncounter({ seed: 'custom-layout', placements });

    for (const [unitId, expectedPosition] of Object.entries(placements)) {
      expect(encounter.units[unitId].position).toEqual(expectedPosition);
    }
  });

  it('rejects incomplete placement maps', () => {
    const placements = { ...DEFAULT_POSITIONS };
    delete placements.G7;

    expect(() => createEncounter({ seed: 'missing-unit', placements })).toThrow(/Missing placements/);
  });

  it('supports pre-action and post-action movement in the same turn', () => {
    const encounter = createEncounter({ seed: 'split-move-turn', placements: DEFAULT_POSITIONS });
    encounter.units.F1.position = { x: 1, y: 1 };
    encounter.units.G1.position = { x: 9, y: 1 };
    encounter.initiativeOrder = ['F1', ...encounter.initiativeOrder.filter((unitId) => unitId !== 'F1')];
    encounter.activeCombatantIndex = 0;

    const result = stepEncounter(encounter);
    const movementEvents = result.events.filter((event) => event.eventType === 'move');
    const attackEvents = result.events.filter((event) => event.eventType === 'attack');

    expect(movementEvents).toHaveLength(2);
    expect(attackEvents).toHaveLength(1);
    expect(movementEvents[0].resolvedTotals.movementPhase).toBe('before_action');
    expect(movementEvents[1].resolvedTotals.movementPhase).toBe('after_action');
    expect(result.state.units.F1.position).toEqual({ x: 7, y: 1 });
  });
});
