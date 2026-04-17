export type Faction = 'fighters' | 'goblins';
export type CombatRole = 'fighter' | 'goblin_melee' | 'goblin_archer';
export type Winner = Faction | 'mutual_annihilation';
export type PlayerBehavior = 'smart' | 'dumb' | 'balanced';
export type ResolvedPlayerBehavior = Exclude<PlayerBehavior, 'balanced'>;
export type MonsterBehavior = 'kind' | 'balanced' | 'evil';
export type MonsterBehaviorSelection = MonsterBehavior | 'combined';
export type RoleTag = 'healer' | 'caster';
export type AttackId = 'greatsword' | 'flail' | 'javelin' | 'scimitar' | 'shortbow';
export type MasteryType = 'graze' | 'sap' | 'slow';
export type AttackMode = 'normal' | 'advantage' | 'disadvantage';
export type EventType =
  | 'turn_start'
  | 'effect_expired'
  | 'death_save'
  | 'heal'
  | 'move'
  | 'attack'
  | 'stabilize'
  | 'phase_change'
  | 'skip';

export interface GridPosition {
  x: number;
  y: number;
}

export interface AbilityModifiers {
  str: number;
  dex: number;
  con: number;
  int: number;
  wis: number;
  cha: number;
}

export interface ConditionState {
  unconscious: boolean;
  prone: boolean;
  dead: boolean;
}

export interface ResourceState {
  secondWindUses: number;
  javelins: number;
}

export interface DiceSpec {
  count: number;
  sides: number;
}

export interface WeaponProfile {
  id: AttackId;
  displayName: string;
  attackBonus: number;
  abilityModifier: number;
  damageDice: DiceSpec[];
  damageModifier: number;
  damageType: string;
  mastery?: MasteryType;
  kind: 'melee' | 'ranged';
  twoHanded?: boolean;
  range?: {
    normal: number;
    long: number;
  };
  advantageDamageDice?: DiceSpec[];
}

export interface SapEffect {
  kind: 'sap';
  sourceId: string;
  expiresAtTurnStartOf: string;
}

export interface SlowEffect {
  kind: 'slow';
  sourceId: string;
  expiresAtTurnStartOf: string;
  penalty: number;
}

export interface HiddenEffect {
  kind: 'hidden';
  sourceId?: string;
  expiresAtTurnStartOf?: string;
}

export interface InvisibleEffect {
  kind: 'invisible';
  sourceId?: string;
  expiresAtTurnStartOf?: string;
}

export type TemporaryEffect = SapEffect | SlowEffect | HiddenEffect | InvisibleEffect;

export interface UnitState {
  id: string;
  faction: Faction;
  combatRole: CombatRole;
  templateName: string;
  roleTags: RoleTag[];
  currentHp: number;
  maxHp: number;
  ac: number;
  speed: number;
  effectiveSpeed: number;
  initiativeMod: number;
  initiativeScore: number;
  abilityMods: AbilityModifiers;
  passivePerception: number;
  conditions: ConditionState;
  deathSaveSuccesses: number;
  deathSaveFailures: number;
  stable: boolean;
  resources: ResourceState;
  position?: GridPosition;
  temporaryEffects: TemporaryEffect[];
  reactionAvailable: boolean;
  attacks: Record<AttackId, WeaponProfile | undefined>;
  medicineModifier: number;
}

export type EventFieldValue = number | string | boolean | null | number[] | string[];

export interface DamageCandidate {
  rawRolls: number[];
  adjustedRolls: number[];
  subtotal: number;
}

export interface DamageDetails {
  weaponId: AttackId;
  weaponName: string;
  damageType: string;
  primaryCandidate: DamageCandidate | null;
  savageCandidate: DamageCandidate | null;
  chosenCandidate: 'primary' | 'savage' | null;
  criticalApplied: boolean;
  criticalMultiplier: number;
  flatModifier: number;
  advantageBonusCandidate: DamageCandidate | null;
  masteryApplied: MasteryType | null;
  masteryNotes: string | null;
  totalDamage: number;
  hpDelta: number;
}

export interface CombatEvent {
  round: number;
  actorId: string;
  targetIds: string[];
  eventType: EventType;
  rawRolls: Record<string, EventFieldValue>;
  resolvedTotals: Record<string, EventFieldValue>;
  movementDetails: {
    start?: GridPosition;
    end?: GridPosition;
    path?: GridPosition[];
    distance?: number;
  } | null;
  damageDetails: DamageDetails | null;
  conditionDeltas: string[];
  textSummary: string;
}

export interface EncounterState {
  seed: string;
  playerBehavior: ResolvedPlayerBehavior;
  monsterBehavior: MonsterBehavior;
  rngState: number;
  round: number;
  initiativeOrder: string[];
  initiativeScores: Record<string, number>;
  activeCombatantIndex: number;
  units: Record<string, UnitState>;
  combatLog: CombatEvent[];
  winner: Winner | null;
  terminalState: 'ongoing' | 'rescue' | 'complete';
  rescueSubphase: boolean;
}

export interface ReplayFrame {
  index: number;
  round: number;
  activeCombatantId: string;
  state: EncounterState;
  events: CombatEvent[];
}

export interface EncounterConfig {
  seed: string;
  placements?: Record<string, GridPosition>;
  batchSize?: number;
  playerBehavior?: PlayerBehavior;
  monsterBehavior?: MonsterBehaviorSelection;
}

export interface RunEncounterResult {
  finalState: EncounterState;
  events: CombatEvent[];
  replayFrames: ReplayFrame[];
}

export interface EncounterSummary {
  seed: string;
  playerBehavior: ResolvedPlayerBehavior;
  monsterBehavior: MonsterBehavior;
  winner: Winner | null;
  rounds: number;
  fighterDeaths: number;
  goblinsKilled: number;
  remainingFighterHp: number;
  remainingGoblinHp: number;
  stableUnconsciousFighters: number;
  consciousFighters: number;
}

export interface BatchCombinationSummary {
  seed: string;
  playerBehavior: PlayerBehavior;
  monsterBehavior: MonsterBehavior;
  batchSize: number;
  totalRuns: number;
  playerWinRate: number;
  goblinWinRate: number;
  mutualAnnihilationRate: number;
  smartPlayerWinRate: number | null;
  dumbPlayerWinRate: number | null;
  smartRunCount: number;
  dumbRunCount: number;
  averageRounds: number;
  averageFighterDeaths: number;
  averageGoblinsKilled: number;
  averageRemainingFighterHp: number;
  averageRemainingGoblinHp: number;
  stableButUnconsciousCount: number;
}

export interface BatchSummary {
  seed: string;
  playerBehavior: PlayerBehavior;
  monsterBehavior: MonsterBehaviorSelection;
  batchSize: number;
  totalRuns: number;
  playerWinRate: number;
  goblinWinRate: number;
  mutualAnnihilationRate: number;
  smartPlayerWinRate: number | null;
  dumbPlayerWinRate: number | null;
  smartRunCount: number;
  dumbRunCount: number;
  averageRounds: number;
  averageFighterDeaths: number;
  averageGoblinsKilled: number;
  averageRemainingFighterHp: number;
  averageRemainingGoblinHp: number;
  stableButUnconsciousCount: number;
  combinationSummaries: BatchCombinationSummary[] | null;
}

export interface StepEncounterResult {
  state: EncounterState;
  events: CombatEvent[];
  done: boolean;
}
