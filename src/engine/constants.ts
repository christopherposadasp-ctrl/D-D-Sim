import type {
  GridPosition,
  MonsterBehavior,
  MonsterBehaviorSelection,
  PlayerBehavior
} from './types';

export const DEFAULT_SEED = 'fighter-vs-goblins-001';
export const DEFAULT_BATCH_SIZE = 100;
export const MAX_BATCH_SIZE = 1000;
export const DEFAULT_PLAYER_BEHAVIOR: PlayerBehavior = 'smart';
export const DEFAULT_BATCH_PLAYER_BEHAVIOR: PlayerBehavior = 'balanced';
export const DEFAULT_MONSTER_BEHAVIOR: MonsterBehavior = 'balanced';
export const DEFAULT_BATCH_MONSTER_BEHAVIOR: MonsterBehaviorSelection = 'combined';
export const TOTAL_FIGHTER_MAX_HP = 39;
export const TOTAL_GOBLIN_MAX_HP = 70;

export const FIGHTER_IDS = ['F1', 'F2', 'F3'] as const;
export const GOBLIN_IDS = ['G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7'] as const;
export const UNIT_IDS = [...FIGHTER_IDS, ...GOBLIN_IDS] as const;
export const MELEE_GOBLIN_IDS = ['G1', 'G2', 'G3', 'G4'] as const;
export const ARCHER_GOBLIN_IDS = ['G5', 'G6', 'G7'] as const;
export const MONSTER_BEHAVIORS = ['kind', 'balanced', 'evil'] as const;

export const DEFAULT_POSITIONS: Record<string, GridPosition> = {
  F1: { x: 1, y: 7 },
  F2: { x: 1, y: 8 },
  F3: { x: 1, y: 9 },
  G1: { x: 14, y: 6 },
  G2: { x: 14, y: 7 },
  G3: { x: 14, y: 8 },
  G4: { x: 14, y: 9 },
  G5: { x: 15, y: 5 },
  G6: { x: 15, y: 8 },
  G7: { x: 15, y: 11 }
};
