import type { MonsterId } from '../../content/monsters/cr2_6.ts';

export interface TestMonsterPairPreset {
  queueOrder: 1 | 2 | 3 | 4 | 5;
  label: string;
  monsterIds: readonly [MonsterId, MonsterId];
}

export const CR2_6_PAIR_01_PRESET: TestMonsterPairPreset = {
  queueOrder: 1,
  label: 'Ogre Zombie + Saber-Toothed Tiger',
  monsterIds: ['ogre_zombie', 'saber_toothed_tiger']
};
