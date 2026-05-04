import type { EncounterConfig, TerrainFeature } from '../shared/sim/types';

export const PRESENTATION_REPLAY_CONFIG = {
  seed: 'frostfall-variant-0034',
  enemyPresetId: 'frostfall_courtyard_variant',
  playerPresetId: 'martial_mixed_party',
  playerBehavior: 'smart',
  monsterBehavior: 'balanced',
  batchSize: 1
} satisfies Omit<EncounterConfig, 'placements'>;

// When set, the presentation page loads this fixed replay instead of rerunning the backend.
export const PRESENTATION_SAVED_REPLAY_URL =
  '/presentation/frostfall_courtyard_variant_party_victory_fireball_haste_paladin_pickup_low_hp_seed_frostfall-variant-0034.json';

export const PRESENTATION_SCENARIO_DISPLAY_NAME = 'Frostfall Courtyard Variant';

export const PRESENTATION_SCENARIO_DESCRIPTION =
  'A tuned alternate Frostfall Courtyard run where the party wins narrowly after the dragon descends into the frozen ruins.';

export const PRESENTATION_TERRAIN_FEATURES = [
  {
    featureId: 'rock_1',
    kind: 'rock',
    position: { x: 5, y: 8 },
    footprint: { width: 1, height: 1 }
  },
  {
    featureId: 'courtyard_column_1',
    kind: 'column',
    position: { x: 3, y: 5 },
    footprint: { width: 1, height: 1 }
  },
  {
    featureId: 'courtyard_column_2',
    kind: 'column',
    position: { x: 3, y: 11 },
    footprint: { width: 1, height: 1 }
  },
  {
    featureId: 'courtyard_column_3',
    kind: 'column',
    position: { x: 5, y: 6 },
    footprint: { width: 1, height: 1 }
  },
  {
    featureId: 'courtyard_column_4',
    kind: 'column',
    position: { x: 5, y: 10 },
    footprint: { width: 1, height: 1 }
  },
  {
    featureId: 'courtyard_low_wall_1',
    kind: 'low_wall',
    position: { x: 7, y: 5 },
    footprint: { width: 2, height: 1 }
  },
  {
    featureId: 'courtyard_low_wall_2',
    kind: 'low_wall',
    position: { x: 7, y: 11 },
    footprint: { width: 2, height: 1 }
  }
] satisfies TerrainFeature[];

export const PRESENTATION_UNIT_DISPLAY_NAMES: Record<string, string> = {
  F1: 'Boromir the Fighter',
  F2: 'Lancelot the Paladin',
  F3: 'Stark the Rogue',
  F4: 'Dumbledore the Wizard',
  E1: 'Kobold Warrior 1',
  E2: 'Kobold Warrior 2',
  E3: 'Kobold Warrior 3',
  E4: 'Kobold Warrior 4',
  E5: 'Kobold Warrior 5',
  E6: 'Kobold Warrior 6',
  E7: 'Kobold Warrior 7',
  E8: 'Kobold Warrior 8',
  E9: 'Kobold Sorcerer 1',
  E10: 'Kobold Sorcerer 2',
  E11: 'Kobold Warrior 9',
  E12: 'Kobold Warrior 10',
  E13: 'Kobold Dragonshield 1',
  E14: 'Kobold Dragonshield 2',
  E15: 'Kobold Dragonshield 3',
  E16: 'Kobold Dragonshield 4',
  E17: 'Frostfang the White Dragon'
};
