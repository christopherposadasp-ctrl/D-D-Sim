import { afterEach, describe, expect, it, vi } from 'vitest';

import type { RunEncounterResult } from '../shared/sim/types';
import {
  PRESENTATION_REPLAY_CONFIG,
  PRESENTATION_SAVED_REPLAY_URL,
} from '../ui/presentationConfig';
import {
  createBatchSummaryFromSavedReplay,
  loadSavedReplayForConfig,
} from '../ui/presentationReplayData';

function buildSavedReplay(): RunEncounterResult {
  return {
    finalState: {
      seed: 'frostfall-variant-0034',
      playerBehavior: 'smart',
      monsterBehavior: 'balanced',
      round: 6,
      winner: 'fighters',
      units: {
        F1: {
          id: 'F1',
          faction: 'fighters',
          currentHp: 15,
          conditions: { dead: false, unconscious: false, prone: false },
          stable: false,
          position: { x: 4, y: 12 },
        },
        E1: {
          id: 'E1',
          faction: 'goblins',
          currentHp: 0,
          conditions: { dead: true, unconscious: false, prone: false },
          stable: false,
          position: { x: 12, y: 1 },
        },
      },
    },
    events: [],
    replayFrames: [
      {
        index: 0,
        round: 1,
        activeCombatantId: 'F1',
        events: [],
        state: {
          units: {
            F1: {
              id: 'F1',
              faction: 'fighters',
              currentHp: 50,
              conditions: { dead: false, unconscious: false, prone: false },
              stable: false,
              position: { x: 4, y: 12 },
            },
            E1: {
              id: 'E1',
              faction: 'goblins',
              currentHp: 7,
              conditions: { dead: false, unconscious: false, prone: false },
              stable: false,
              position: { x: 12, y: 1 },
            },
          },
        },
      },
    ],
  } as unknown as RunEncounterResult;
}

describe('presentation replay data', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads the saved replay asset whenever the Frostfall Variant scenario is selected', async () => {
    const savedReplay = buildSavedReplay();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(PRESENTATION_SAVED_REPLAY_URL);
      expect(String(input)).not.toContain('/api/');

      return new Response(JSON.stringify({ result: savedReplay }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const replay = await loadSavedReplayForConfig({
      ...PRESENTATION_REPLAY_CONFIG,
      seed: 'anything-else',
      playerPresetId: 'other_party',
      playerBehavior: 'dumb',
      monsterBehavior: 'evil',
      batchSize: 100,
      placements: {
        F1: { x: 4, y: 12 },
        E1: { x: 12, y: 1 },
      },
    });

    expect(replay?.finalState.seed).toBe('frostfall-variant-0034');
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const batchSummary = createBatchSummaryFromSavedReplay(replay!, {
      ...PRESENTATION_REPLAY_CONFIG,
      placements: {
        F1: { x: 4, y: 12 },
        E1: { x: 12, y: 1 },
      },
    });
    expect(batchSummary.playerWinRate).toBe(1);
    expect(batchSummary.averageRemainingFighterHp).toBe(15);
    expect(batchSummary.averageGoblinsKilled).toBe(1);
  });
});
