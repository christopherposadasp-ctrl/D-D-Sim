import type { EncounterConfig, RunEncounterResult } from '../shared/sim/types';

export const PRESENTATION_REPLAY_CONFIG = {
  seed: 'presentation-heroic-victory-001',
  enemyPresetId: 'captains_crossfire',
  playerPresetId: 'martial_mixed_party',
  playerBehavior: 'smart',
  monsterBehavior: 'balanced',
  batchSize: 1
} satisfies Omit<EncounterConfig, 'placements'>;

// Replace this with an imported saved replay once the final heroic seed is selected.
// When null, the presentation page generates the fixed replay from the local backend.
export const PRESENTATION_SAVED_REPLAY: RunEncounterResult | null = null;
