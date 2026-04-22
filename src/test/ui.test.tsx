import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  BatchSummary,
  CombatEvent,
  EnemyCatalogResponse,
  EncounterConfig,
  EncounterState,
  GridPosition,
  PlayerCatalogResponse,
  ReplayFrame,
  RunEncounterResult,
  UnitState,
} from '../shared/sim/types';
import { App } from '../ui/App';

const TEST_ENEMY_CATALOG: EnemyCatalogResponse = {
  defaultEnemyPresetId: 'goblin_screen',
  enemyVariants: [
    { id: 'goblin_raider', displayName: 'Goblin Raider', maxHp: 10, footprint: { width: 1, height: 1 } },
    { id: 'goblin_archer', displayName: 'Goblin Archer', maxHp: 10, footprint: { width: 1, height: 1 } },
    { id: 'bandit_melee', displayName: 'Bandit Melee', maxHp: 11, footprint: { width: 1, height: 1 } },
    { id: 'bandit_archer', displayName: 'Bandit Archer', maxHp: 11, footprint: { width: 1, height: 1 } },
    { id: 'guard', displayName: 'Guard', maxHp: 11, footprint: { width: 1, height: 1 } },
    { id: 'scout', displayName: 'Scout', maxHp: 16, footprint: { width: 1, height: 1 } },
    { id: 'orc_warrior', displayName: 'Orc Warrior', maxHp: 15, footprint: { width: 1, height: 1 } },
    { id: 'wolf', displayName: 'Wolf', maxHp: 11, footprint: { width: 1, height: 1 } },
    { id: 'giant_toad', displayName: 'Giant Toad', maxHp: 39, footprint: { width: 2, height: 2 } },
    { id: 'crocodile', displayName: 'Crocodile', maxHp: 13, footprint: { width: 2, height: 2 } },
  ],
  enemyPresets: [
    {
      id: 'goblin_screen',
      displayName: 'Goblin Screen',
      description: 'Three raiders screening three archers.',
      terrainFeatures: [{ featureId: 'rock_1', kind: 'rock', position: { x: 5, y: 8 }, footprint: { width: 1, height: 1 } }],
      units: [
        { unitId: 'E1', variantId: 'goblin_raider', position: { x: 14, y: 6 } },
        { unitId: 'E2', variantId: 'goblin_raider', position: { x: 14, y: 8 } },
        { unitId: 'E3', variantId: 'goblin_raider', position: { x: 14, y: 10 } },
        { unitId: 'E4', variantId: 'goblin_archer', position: { x: 15, y: 5 } },
        { unitId: 'E5', variantId: 'goblin_archer', position: { x: 15, y: 8 } },
        { unitId: 'E6', variantId: 'goblin_archer', position: { x: 15, y: 11 } },
      ],
    },
    {
      id: 'marsh_predators',
      displayName: 'Marsh Predators',
      description: 'A giant toad backed by two crocodiles that try to pin fighters in place.',
      terrainFeatures: [{ featureId: 'rock_1', kind: 'rock', position: { x: 5, y: 8 }, footprint: { width: 1, height: 1 } }],
      units: [
        { unitId: 'E1', variantId: 'giant_toad', position: { x: 9, y: 7 } },
        { unitId: 'E2', variantId: 'crocodile', position: { x: 11, y: 5 } },
        { unitId: 'E3', variantId: 'crocodile', position: { x: 11, y: 9 } },
      ],
    },
  ],
};

const TEST_PLAYER_CATALOG: PlayerCatalogResponse = {
  defaultPlayerPresetId: 'martial_mixed_party',
  classes: [
    { id: 'barbarian', displayName: 'Barbarian', category: 'martial', maxSupportedLevel: 2 },
    { id: 'fighter', displayName: 'Fighter', category: 'martial', maxSupportedLevel: 2 },
    { id: 'rogue', displayName: 'Rogue', category: 'martial', maxSupportedLevel: 1 },
  ],
  loadouts: [
    {
      id: 'barbarian_sample_build',
      displayName: 'Level 1 Barbarian Sample Build',
      classId: 'barbarian',
      level: 1,
      maxHp: 15,
      featureIds: ['rage', 'unarmored_defense', 'weapon_mastery_cleave', 'weapon_mastery_vex'],
      weaponIds: ['greataxe', 'handaxe'],
    },
    {
      id: 'barbarian_level2_sample_build',
      displayName: 'Level 2 Barbarian Sample Build',
      classId: 'barbarian',
      level: 2,
      maxHp: 25,
      featureIds: ['rage', 'unarmored_defense', 'reckless_attack', 'danger_sense', 'weapon_mastery_cleave', 'weapon_mastery_vex'],
      weaponIds: ['greataxe', 'handaxe'],
    },
    {
      id: 'fighter_sample_build',
      displayName: 'Level 1 Fighter Sample Build',
      classId: 'fighter',
      level: 1,
      maxHp: 13,
      featureIds: ['second_wind', 'great_weapon_fighting', 'savage_attacker'],
      weaponIds: ['flail', 'greatsword', 'javelin'],
    },
    {
      id: 'fighter_level2_sample_build',
      displayName: 'Level 2 Fighter Sample Build',
      classId: 'fighter',
      level: 2,
      maxHp: 21,
      featureIds: ['second_wind', 'action_surge', 'great_weapon_fighting', 'savage_attacker'],
      weaponIds: ['flail', 'greatsword', 'javelin'],
    },
    {
      id: 'rogue_ranged_sample_build',
      displayName: 'Ranged Rogue Sample Build',
      classId: 'rogue',
      level: 1,
      maxHp: 10,
      featureIds: ['sneak_attack'],
      weaponIds: ['shortbow', 'shortsword'],
    },
    {
      id: 'rogue_melee_sample_build',
      displayName: 'Melee Rogue Sample Build',
      classId: 'rogue',
      level: 1,
      maxHp: 10,
      featureIds: ['sneak_attack'],
      weaponIds: ['rapier', 'shortbow'],
    },
  ],
  playerPresets: [
    {
      id: 'fighter_sample_trio',
      displayName: 'Level 1 Fighter Trio',
      description: 'Three level 1 fighters.',
      units: [
        { unitId: 'F1', loadoutId: 'fighter_sample_build' },
        { unitId: 'F2', loadoutId: 'fighter_sample_build' },
        { unitId: 'F3', loadoutId: 'fighter_sample_build' },
      ],
    },
    {
      id: 'fighter_level2_sample_trio',
      displayName: 'Level 2 Fighter Trio',
      description: 'Three level 2 fighters.',
      units: [
        { unitId: 'F1', loadoutId: 'fighter_level2_sample_build' },
        { unitId: 'F2', loadoutId: 'fighter_level2_sample_build' },
        { unitId: 'F3', loadoutId: 'fighter_level2_sample_build' },
      ],
    },
    {
      id: 'rogue_ranged_trio',
      displayName: 'Ranged Rogue Trio',
      description: 'Three ranged rogues.',
      units: [
        { unitId: 'F1', loadoutId: 'rogue_ranged_sample_build' },
        { unitId: 'F2', loadoutId: 'rogue_ranged_sample_build' },
        { unitId: 'F3', loadoutId: 'rogue_ranged_sample_build' },
      ],
    },
    {
      id: 'rogue_melee_trio',
      displayName: 'Melee Rogue Trio',
      description: 'Three melee rogues.',
      units: [
        { unitId: 'F1', loadoutId: 'rogue_melee_sample_build' },
        { unitId: 'F2', loadoutId: 'rogue_melee_sample_build' },
        { unitId: 'F3', loadoutId: 'rogue_melee_sample_build' },
      ],
    },
    {
      id: 'barbarian_sample_trio',
      displayName: 'Level 1 Barbarian Trio',
      description: 'Three level 1 barbarians.',
      units: [
        { unitId: 'F1', loadoutId: 'barbarian_sample_build' },
        { unitId: 'F2', loadoutId: 'barbarian_sample_build' },
        { unitId: 'F3', loadoutId: 'barbarian_sample_build' },
      ],
    },
    {
      id: 'barbarian_level2_sample_trio',
      displayName: 'Level 2 Barbarian Trio',
      description: 'Three level 2 barbarians.',
      units: [
        { unitId: 'F1', loadoutId: 'barbarian_level2_sample_build' },
        { unitId: 'F2', loadoutId: 'barbarian_level2_sample_build' },
        { unitId: 'F3', loadoutId: 'barbarian_level2_sample_build' },
      ],
    },
    {
      id: 'martial_mixed_party',
      displayName: 'Mixed Martial Party',
      description: 'One fighter, one barbarian, one ranged rogue, and one melee rogue.',
      units: [
        { unitId: 'F1', loadoutId: 'fighter_level2_sample_build' },
        { unitId: 'F2', loadoutId: 'barbarian_level2_sample_build' },
        { unitId: 'F3', loadoutId: 'rogue_ranged_sample_build' },
        { unitId: 'F4', loadoutId: 'rogue_melee_sample_build' },
      ],
    },
  ],
};

function buildUnit(
  id: string,
  templateName: string,
  faction: 'fighters' | 'goblins',
  combatRole: UnitState['combatRole'],
  position: GridPosition,
  maxHp: number,
): UnitState {
  return {
    id,
    faction,
    combatRole,
    templateName,
    roleTags: [],
    currentHp: maxHp,
    maxHp,
    temporaryHitPoints: 0,
    ac: faction === 'fighters' ? 16 : 15,
    speed: 30,
    effectiveSpeed: 30,
    initiativeMod: faction === 'fighters' ? 1 : 2,
    initiativeScore: 12,
    abilityMods: {
      str: 3,
      dex: 1,
      con: 2,
      int: 0,
      wis: 0,
      cha: 0,
    },
    passivePerception: 10,
    sizeCategory: faction === 'fighters' ? 'medium' : 'small',
    footprint: { width: 1, height: 1 },
    conditions: {
      unconscious: false,
      prone: false,
      dead: false,
    },
    deathSaveSuccesses: 0,
    deathSaveFailures: 0,
    stable: false,
    resources: {
      secondWindUses: faction === 'fighters' ? 1 : 0,
      javelins: faction === 'fighters' ? 6 : 0,
      rageUses: 0,
      handaxes: 0,
      actionSurgeUses: 0,
      focusPoints: 0,
      uncannyMetabolismUses: 0,
    },
    position,
    temporaryEffects: [],
    reactionAvailable: true,
    attacks: {} as UnitState['attacks'],
    medicineModifier: 0,
  };
}

function buildEncounterState(
  seed: string,
  playerBehavior: EncounterState['playerBehavior'],
  monsterBehavior: EncounterState['monsterBehavior'],
  combatLogLength: number,
): EncounterState {
  const units: Record<string, UnitState> = {
    F1: buildUnit('F1', 'Level 2 Fighter Sample Build', 'fighters', 'fighter', { x: 1, y: 7 }, 21),
    F2: buildUnit('F2', 'Level 2 Barbarian Sample Build', 'fighters', 'barbarian', { x: 1, y: 8 }, 25),
    F3: buildUnit('F3', 'Level 1 Ranged Rogue Sample Build', 'fighters', 'rogue', { x: 1, y: 9 }, 10),
    F4: buildUnit('F4', 'Level 1 Melee Rogue Sample Build', 'fighters', 'rogue', { x: 1, y: 10 }, 10),
    E1: buildUnit('E1', '2024 Goblin Raider', 'goblins', 'goblin_melee', { x: 14, y: 6 }, 10),
    E2: buildUnit('E2', '2024 Goblin Raider', 'goblins', 'goblin_melee', { x: 14, y: 8 }, 10),
    E3: buildUnit('E3', '2024 Goblin Raider', 'goblins', 'goblin_melee', { x: 14, y: 10 }, 10),
    E4: buildUnit('E4', '2024 Goblin Archer', 'goblins', 'goblin_archer', { x: 15, y: 5 }, 10),
    E5: buildUnit('E5', '2024 Goblin Archer', 'goblins', 'goblin_archer', { x: 15, y: 8 }, 10),
    E6: buildUnit('E6', '2024 Goblin Archer', 'goblins', 'goblin_archer', { x: 15, y: 11 }, 10),
  };
  units.F1.resources.actionSurgeUses = 1;
  units.F2.ac = 14;
  units.F2.resources.secondWindUses = 0;
  units.F2.resources.javelins = 0;
  units.F2.resources.rageUses = 2;
  units.F2.resources.handaxes = 4;

  const combatLog: CombatEvent[] = Array.from({ length: combatLogLength }, (_, index): CombatEvent => ({
    round: 1,
    actorId: 'F1',
    targetIds: ['E1'],
    eventType: index === 0 ? 'move' : 'attack',
    rawRolls: index === 0 ? {} : { attackRoll: 14 },
    resolvedTotals: index === 0 ? { movementPhase: 'before_action' } : { total: 19 },
    movementDetails:
      index === 0
        ? {
            start: { x: 1, y: 7 },
            end: { x: 3, y: 7 },
            path: [
              { x: 1, y: 7 },
              { x: 2, y: 7 },
              { x: 3, y: 7 },
            ],
            distance: 2,
          }
        : null,
    damageDetails: null,
    conditionDeltas: [],
    textSummary: index === 0 ? 'F1 moves into range.' : 'F1 attacks E1.',
  }));

  return {
    seed,
    playerBehavior,
    monsterBehavior,
    rngState: 123456,
    round: 1,
    initiativeOrder: ['F1', 'F2', 'F3', 'F4', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6'],
    initiativeScores: {
      F1: 15,
      F2: 14,
      F3: 13,
      F4: 12,
      E1: 12,
      E2: 12,
      E3: 12,
      E4: 12,
      E5: 12,
      E6: 12,
    },
    activeCombatantIndex: 0,
    units,
    combatLog,
    winner: null,
    terminalState: 'ongoing',
    rescueSubphase: false,
  };
}

function buildEncounterResult(config: EncounterConfig): RunEncounterResult {
  const finalState = buildEncounterState(
    config.seed,
    config.playerBehavior === 'dumb' ? 'dumb' : 'smart',
    config.monsterBehavior === 'kind' ? 'kind' : config.monsterBehavior === 'evil' ? 'evil' : 'balanced',
    2,
  );

  const firstFrame: ReplayFrame = {
    index: 0,
    round: 1,
    activeCombatantId: 'F1',
    state: buildEncounterState(finalState.seed, finalState.playerBehavior, finalState.monsterBehavior, 1),
    events: [
      {
        round: 1,
        actorId: 'F1',
        targetIds: ['E1'],
        eventType: 'move',
        rawRolls: {},
        resolvedTotals: { movementPhase: 'before_action' },
        movementDetails: {
          start: { x: 1, y: 7 },
          end: { x: 3, y: 7 },
          path: [
            { x: 1, y: 7 },
            { x: 2, y: 7 },
            { x: 3, y: 7 },
          ],
          distance: 2,
        },
        damageDetails: null,
        conditionDeltas: [],
        textSummary: 'F1 moves into range.',
      },
    ],
  };

  const secondFrame: ReplayFrame = {
    index: 1,
    round: 1,
    activeCombatantId: 'F1',
    state: finalState,
    events: [
      {
        round: 1,
        actorId: 'F1',
        targetIds: ['E1'],
        eventType: 'attack',
        rawRolls: { attackRoll: 14 },
        resolvedTotals: { total: 19 },
        movementDetails: null,
        damageDetails: null,
        conditionDeltas: [],
        textSummary: 'F1 attacks E1.',
      },
    ],
  };

  return {
    finalState,
    events: [...firstFrame.events, ...secondFrame.events],
    replayFrames: [firstFrame, secondFrame],
  };
}

function buildBatchSummary(config: EncounterConfig): BatchSummary {
  const batchSize = config.batchSize ?? 100;
  const playerBehavior = config.playerBehavior ?? 'balanced';
  const monsterBehavior = config.monsterBehavior ?? 'combined';

  if (monsterBehavior === 'combined') {
    return {
      seed: config.seed,
      playerBehavior,
      monsterBehavior: 'combined',
      batchSize,
      totalRuns: batchSize * 3,
      playerWinRate: 0.35,
      goblinWinRate: 0.65,
      mutualAnnihilationRate: 0,
      smartPlayerWinRate: 0.42,
      dumbPlayerWinRate: 0.28,
      smartRunCount: Math.ceil((batchSize * 3) / 2),
      dumbRunCount: Math.floor((batchSize * 3) / 2),
      averageRounds: 6.5,
      averageFighterDeaths: 1.2,
      averageGoblinsKilled: 3.7,
      averageRemainingFighterHp: 7.4,
      averageRemainingGoblinHp: 28.1,
      stableButUnconsciousCount: 4,
      combinationSummaries: [
        {
          seed: config.seed,
          playerBehavior,
          monsterBehavior: 'kind',
          batchSize,
          totalRuns: batchSize,
          playerWinRate: 0.5,
          goblinWinRate: 0.5,
          mutualAnnihilationRate: 0,
          smartPlayerWinRate: 0.6,
          dumbPlayerWinRate: 0.4,
          smartRunCount: Math.ceil(batchSize / 2),
          dumbRunCount: Math.floor(batchSize / 2),
          averageRounds: 6.1,
          averageFighterDeaths: 0.8,
          averageGoblinsKilled: 4.2,
          averageRemainingFighterHp: 10.2,
          averageRemainingGoblinHp: 18.5,
          stableButUnconsciousCount: 1,
        },
        {
          seed: config.seed,
          playerBehavior,
          monsterBehavior: 'balanced',
          batchSize,
          totalRuns: batchSize,
          playerWinRate: 0.3,
          goblinWinRate: 0.7,
          mutualAnnihilationRate: 0,
          smartPlayerWinRate: 0.4,
          dumbPlayerWinRate: 0.2,
          smartRunCount: Math.ceil(batchSize / 2),
          dumbRunCount: Math.floor(batchSize / 2),
          averageRounds: 6.7,
          averageFighterDeaths: 1.1,
          averageGoblinsKilled: 3.6,
          averageRemainingFighterHp: 6.4,
          averageRemainingGoblinHp: 29.8,
          stableButUnconsciousCount: 2,
        },
        {
          seed: config.seed,
          playerBehavior,
          monsterBehavior: 'evil',
          batchSize,
          totalRuns: batchSize,
          playerWinRate: 0.25,
          goblinWinRate: 0.75,
          mutualAnnihilationRate: 0,
          smartPlayerWinRate: 0.32,
          dumbPlayerWinRate: 0.18,
          smartRunCount: Math.ceil(batchSize / 2),
          dumbRunCount: Math.floor(batchSize / 2),
          averageRounds: 6.8,
          averageFighterDeaths: 1.5,
          averageGoblinsKilled: 3.2,
          averageRemainingFighterHp: 5.6,
          averageRemainingGoblinHp: 36.0,
          stableButUnconsciousCount: 1,
        },
      ],
    };
  }

  const smartRunCount =
    playerBehavior === 'balanced' ? Math.ceil(batchSize / 2) : playerBehavior === 'smart' ? batchSize : 0;
  const dumbRunCount =
    playerBehavior === 'balanced' ? Math.floor(batchSize / 2) : playerBehavior === 'dumb' ? batchSize : 0;

  return {
    seed: config.seed,
    playerBehavior,
    monsterBehavior,
    batchSize,
    totalRuns: batchSize,
    playerWinRate: 1,
    goblinWinRate: 0,
    mutualAnnihilationRate: 0,
    smartPlayerWinRate: smartRunCount > 0 ? 1 : null,
    dumbPlayerWinRate: dumbRunCount > 0 ? 1 : null,
    smartRunCount,
    dumbRunCount,
    averageRounds: 5,
    averageFighterDeaths: 0,
    averageGoblinsKilled: 6,
    averageRemainingFighterHp: 18,
    averageRemainingGoblinHp: 0,
    stableButUnconsciousCount: 0,
    combinationSummaries: null,
  };
}

describe('App', () => {
  beforeEach(() => {
    const batchJobs = new Map<
      string,
      {
        pollCount: number;
        summary: BatchSummary;
        startedAt: string;
        totalRuns: number;
        currentMonsterBehavior: string;
      }
    >();
    let nextBatchJobId = 1;

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const requestUrl =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.pathname
              : input.url;
        const config = init?.body ? (JSON.parse(String(init.body)) as EncounterConfig) : null;

        if (requestUrl.endsWith('/api/encounters/run')) {
          return new Response(JSON.stringify(buildEncounterResult(config!)), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.endsWith('/api/encounters/batch')) {
          return new Response(JSON.stringify(buildBatchSummary(config!)), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.endsWith('/api/encounters/batch-jobs')) {
          const summary = buildBatchSummary(config!);
          const jobId = `job-${nextBatchJobId}`;
          nextBatchJobId += 1;
          const startedAt = new Date().toISOString();
          const currentMonsterBehavior =
            !config?.monsterBehavior || config.monsterBehavior === 'combined' ? 'kind' : config.monsterBehavior;

          batchJobs.set(jobId, {
            pollCount: 0,
            summary,
            startedAt,
            totalRuns: summary.totalRuns,
            currentMonsterBehavior,
          });

          return new Response(
            JSON.stringify({
              jobId,
              status: 'running',
              completedRuns: 0,
              totalRuns: summary.totalRuns,
              progressRatio: 0,
              startedAt,
              finishedAt: null,
              elapsedSeconds: 0,
              currentMonsterBehavior,
              batchSummary: null,
              error: null,
            }),
            {
              status: 200,
              headers: {
                'Content-Type': 'application/json',
              },
            },
          );
        }

        if (requestUrl.endsWith('/api/catalog/enemies')) {
          return new Response(JSON.stringify(TEST_ENEMY_CATALOG), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.endsWith('/api/catalog/classes')) {
          return new Response(JSON.stringify(TEST_PLAYER_CATALOG), {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
            },
          });
        }

        if (requestUrl.includes('/api/encounters/batch-jobs/')) {
          const jobId = requestUrl.split('/').pop()!;
          const job = batchJobs.get(jobId);

          if (!job) {
            return new Response(JSON.stringify({ detail: `Unknown job ${jobId}` }), {
              status: 404,
              headers: {
                'Content-Type': 'application/json',
              },
            });
          }

          job.pollCount += 1;

          if (job.pollCount === 1) {
            const completedRuns = Math.max(1, Math.ceil(job.totalRuns / 3));

            return new Response(
              JSON.stringify({
                jobId,
                status: 'running',
                completedRuns,
                totalRuns: job.totalRuns,
                progressRatio: completedRuns / job.totalRuns,
                startedAt: job.startedAt,
                finishedAt: null,
                elapsedSeconds: 1,
                currentMonsterBehavior: job.currentMonsterBehavior,
                batchSummary: null,
                error: null,
              }),
              {
                status: 200,
                headers: {
                  'Content-Type': 'application/json',
                },
              },
            );
          }

          return new Response(
            JSON.stringify({
              jobId,
              status: 'completed',
              completedRuns: job.totalRuns,
              totalRuns: job.totalRuns,
              progressRatio: 1,
              startedAt: job.startedAt,
              finishedAt: new Date().toISOString(),
              elapsedSeconds: 2,
              currentMonsterBehavior: null,
              batchSummary: job.summary,
              error: null,
            }),
            {
              status: 200,
              headers: {
                'Content-Type': 'application/json',
              },
            },
          );
        }

        return new Response(JSON.stringify({ detail: `Unexpected request to ${requestUrl}` }), {
          status: 404,
          headers: {
            'Content-Type': 'application/json',
          },
        });
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('opens with the default layout already loaded and ready to run', async () => {
    render(<App />);

    expect(await screen.findByText(/10 \/ 10 units placed/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /batch run/i })).toBeEnabled();
    expect(screen.getByRole('combobox', { name: /player behavior/i })).toHaveValue('balanced');
    expect(screen.getByRole('combobox', { name: /dm behavior/i })).toHaveValue('combined');
    const enemyPresetSelect = screen.getByRole('combobox', { name: /enemy preset/i });
    expect(enemyPresetSelect).toHaveValue('goblin_screen');
    expect(within(enemyPresetSelect).queryByRole('option', { name: 'Giant Toad' })).not.toBeInTheDocument();
    expect(within(enemyPresetSelect).getByRole('option', { name: 'Marsh Predators' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /batch size/i })).toHaveValue(100);
    expect(screen.getByRole('grid', { name: /placement grid/i })).toBeInTheDocument();
  });

  it('renders the preset rock and blocks placement onto that square', async () => {
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    const rockSquare = screen.getByRole('button', { name: /square 5,8 contains rock terrain/i });

    expect(rockSquare).toBeDisabled();
  });

  it('uses batch size 1 as a replayable single encounter run', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    await user.selectOptions(screen.getByRole('combobox', { name: /dm behavior/i }), 'balanced');
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '1');
    await user.click(screen.getByRole('button', { name: /batch run/i }));

    expect(await screen.findByText(/Replay Frame 1/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /combat grid/i })).toBeInTheDocument();
    expect(screen.getByText(/Per-Round Event Log/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Level 2 Fighter Sample Build/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Enemy Preset/i).length).toBeGreaterThan(0);
  });

  it('lets the user return from replay to edit the layout', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    await user.selectOptions(screen.getByRole('combobox', { name: /dm behavior/i }), 'balanced');
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '1');
    await user.click(screen.getByRole('button', { name: /batch run/i }));
    await screen.findByRole('img', { name: /combat grid/i });

    await user.click(screen.getByRole('button', { name: /edit layout/i }));

    expect(screen.getByRole('grid', { name: /placement grid/i })).toBeInTheDocument();
    expect(screen.getByText(/Selected unit:/i)).toBeInTheDocument();
    expect(screen.queryByText(/Replay Frame 1/i)).not.toBeInTheDocument();
  });

  it('shows combined DM summaries for balanced players in a batch run', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/10 \/ 10 units placed/i);
    const batchSizeInput = screen.getByRole('spinbutton', { name: /batch size/i });
    await user.clear(batchSizeInput);
    await user.type(batchSizeInput, '2');
    await user.click(screen.getByRole('button', { name: /batch run/i }));

    expect(await screen.findByText(/Batch Progress/i)).toBeInTheDocument();
    expect(screen.getByText(/Elapsed:/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/Smart Player Win Rate/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Dumb Player Win Rate/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Player Policy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Kind DM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Balanced DM/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Evil DM/i).length).toBeGreaterThan(0);
  });
});
