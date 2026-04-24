export type Faction = 'fighters' | 'goblins';
export type CombatRole = string;
export type Winner = Faction | 'mutual_annihilation';
export type PlayerBehavior = 'smart' | 'dumb' | 'balanced';
export type ResolvedPlayerBehavior = Exclude<PlayerBehavior, 'balanced'>;
export type MonsterBehavior = 'kind' | 'balanced' | 'evil';
export type MonsterBehaviorSelection = MonsterBehavior | 'combined';
export type BatchJobState = 'queued' | 'running' | 'completed' | 'failed';
export type RoleTag = 'healer' | 'caster' | 'controller';
export type AttackId = string;
export type SizeCategory = 'tiny' | 'small' | 'medium' | 'large' | 'huge' | 'gargantuan';
export type MasteryType = 'graze' | 'sap' | 'slow' | 'cleave' | 'vex';
export type AttackMode = 'normal' | 'advantage' | 'disadvantage';
export type EventType =
  | 'turn_start'
  | 'effect_expired'
  | 'death_save'
  | 'saving_throw'
  | 'heal'
  | 'move'
  | 'attack'
  | 'ongoing_damage'
  | 'stabilize'
  | 'phase_change'
  | 'skip';

export interface GridPosition {
  x: number;
  y: number;
}

export interface Footprint {
  width: number;
  height: number;
}

export type TerrainFeatureKind = 'rock';

export interface TerrainFeature {
  featureId: string;
  kind: TerrainFeatureKind;
  position: GridPosition;
  footprint: Footprint;
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
  rageUses: number;
  handaxes: number;
  actionSurgeUses: number;
  focusPoints: number;
  uncannyMetabolismUses: number;
  spellSlotsLevel1: number;
}

export interface DiceSpec {
  count: number;
  sides: number;
}

export interface WeaponDamageComponent {
  damageType: string;
  damageDice: DiceSpec[];
  damageModifier: number;
}

export interface OnHitEffect {
  kind: 'prone_on_hit' | 'grapple_on_hit' | 'grapple_and_restrain';
  escapeDc?: number;
  maxTargetSize?: SizeCategory;
}

export interface WeaponProfile {
  id: AttackId;
  displayName: string;
  attackBonus: number;
  abilityModifier: number;
  attackAbility?: 'str' | 'dex';
  damageDice: DiceSpec[];
  damageModifier: number;
  damageType?: string | null;
  damageComponents?: WeaponDamageComponent[];
  mastery?: MasteryType;
  kind: 'melee' | 'ranged';
  finesse?: boolean;
  twoHanded?: boolean;
  reach?: number;
  range?: {
    normal: number;
    long: number;
  };
  advantageDamageDice?: DiceSpec[];
  onHitEffects?: OnHitEffect[];
  locksToGrappledTarget?: boolean;
  resourcePoolId?: string;
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

export interface NoReactionsEffect {
  kind: 'no_reactions';
  sourceId: string;
  expiresAtTurnStartOf: string;
}

export interface HiddenEffect {
  kind: 'hidden';
  sourceId?: string;
  expiresAtTurnStartOf?: string;
}

export interface DodgingEffect {
  kind: 'dodging';
  sourceId: string;
  expiresAtTurnStartOf: string;
}

export interface ShieldEffect {
  kind: 'shield';
  sourceId: string;
  expiresAtTurnStartOf: string;
  acBonus: number;
}

export interface InvisibleEffect {
  kind: 'invisible';
  sourceId?: string;
  expiresAtTurnStartOf?: string;
}

export interface GrappledEffect {
  kind: 'grappled_by';
  sourceId: string;
  escapeDc: number;
}

export interface RestrainedEffect {
  kind: 'restrained_by';
  sourceId: string;
  escapeDc: number;
}

export interface BlindedEffect {
  kind: 'blinded_by';
  sourceId: string;
}

export interface RageEffect {
  kind: 'rage';
  sourceId: string;
  damageBonus: number;
  remainingRounds: number;
}

export interface RecklessAttackEffect {
  kind: 'reckless_attack';
  sourceId: string;
  expiresAtTurnStartOf: string;
}

export interface SwallowedEffect {
  kind: 'swallowed_by';
  sourceId: string;
}

export interface VexEffect {
  kind: 'vex';
  sourceId: string;
  targetId: string;
  expiresAtTurnEndOf: string;
  expiresAtRound: number;
}

export type TemporaryEffect =
  | SapEffect
  | SlowEffect
  | NoReactionsEffect
  | HiddenEffect
  | DodgingEffect
  | ShieldEffect
  | InvisibleEffect
  | GrappledEffect
  | RestrainedEffect
  | BlindedEffect
  | RageEffect
  | RecklessAttackEffect
  | SwallowedEffect
  | VexEffect;

export interface UnitState {
  id: string;
  faction: Faction;
  combatRole: CombatRole;
  templateName: string;
  roleTags: RoleTag[];
  currentHp: number;
  maxHp: number;
  temporaryHitPoints: number;
  ac: number;
  speed: number;
  effectiveSpeed: number;
  initiativeMod: number;
  initiativeScore: number;
  abilityMods: AbilityModifiers;
  passivePerception: number;
  sizeCategory: SizeCategory;
  footprint: Footprint;
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
  components: DamageComponentResult[];
  rawRolls: number[];
  adjustedRolls: number[];
  subtotal: number;
}

export interface DamageComponentResult {
  damageType: string;
  rawRolls: number[];
  adjustedRolls: number[];
  subtotal: number;
  flatModifier: number;
  totalDamage: number;
}

export interface DamageDetails {
  weaponId: AttackId;
  weaponName: string;
  damageComponents: DamageComponentResult[];
  primaryCandidate: DamageCandidate | null;
  savageCandidate: DamageCandidate | null;
  chosenCandidate: 'primary' | 'savage' | null;
  criticalApplied: boolean;
  criticalMultiplier: number;
  flatModifier: number;
  advantageBonusCandidate: DamageCandidate | null;
  masteryApplied: MasteryType | null;
  masteryNotes: string | null;
  attackRidersApplied?: Array<'prone_on_hit' | 'grapple_on_hit' | 'grapple_and_restrain'>;
  totalDamage: number;
  resistedDamage: number;
  temporaryHpAbsorbed: number;
  finalDamageToHp: number;
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
  enemyPresetId?: string;
  playerPresetId?: string;
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

export interface BatchJobStatus {
  jobId: string;
  status: BatchJobState;
  completedRuns: number;
  totalRuns: number;
  progressRatio: number;
  startedAt: string;
  finishedAt: string | null;
  elapsedSeconds: number;
  currentMonsterBehavior: MonsterBehavior | null;
  batchSummary: BatchSummary | null;
  error: string | null;
}

export interface StepEncounterResult {
  state: EncounterState;
  events: CombatEvent[];
  done: boolean;
}

export interface EnemyVariantCatalogEntry {
  id: string;
  displayName: string;
  maxHp: number;
  footprint: Footprint;
}

export interface EnemyPresetUnitCatalogEntry {
  unitId: string;
  variantId: string;
  position: GridPosition;
}

export interface EnemyPresetCatalogEntry {
  id: string;
  displayName: string;
  description: string;
  units: EnemyPresetUnitCatalogEntry[];
  terrainFeatures: TerrainFeature[];
}

export interface EnemyCatalogResponse {
  defaultEnemyPresetId: string;
  enemyVariants: EnemyVariantCatalogEntry[];
  enemyPresets: EnemyPresetCatalogEntry[];
}

export type PlayerClassCategory = 'martial' | 'spellcaster' | 'half_caster';

export interface PlayerClassCatalogEntry {
  id: string;
  displayName: string;
  category: PlayerClassCategory;
  maxSupportedLevel: number;
}

export interface PlayerLoadoutCatalogEntry {
  id: string;
  displayName: string;
  classId: string;
  level: number;
  maxHp: number;
  featureIds: string[];
  weaponIds: string[];
}

export interface PlayerPresetUnitCatalogEntry {
  unitId: string;
  loadoutId: string;
}

export interface PlayerPresetCatalogEntry {
  id: string;
  displayName: string;
  description: string;
  units: PlayerPresetUnitCatalogEntry[];
}

export interface PlayerCatalogResponse {
  defaultPlayerPresetId: string;
  classes: PlayerClassCatalogEntry[];
  loadouts: PlayerLoadoutCatalogEntry[];
  playerPresets: PlayerPresetCatalogEntry[];
}
