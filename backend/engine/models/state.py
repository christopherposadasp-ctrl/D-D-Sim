from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_serializer


def to_camel(value: str) -> str:
    """Convert snake_case field names to the camelCase API shape used by the TS app."""
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    """Shared base model with camelCase aliases for API transport."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


Faction: TypeAlias = Literal["fighters", "goblins"]
CombatRole: TypeAlias = str
Winner: TypeAlias = Literal["fighters", "goblins", "mutual_annihilation"]
PlayerBehavior: TypeAlias = Literal["smart", "dumb", "balanced"]
ResolvedPlayerBehavior: TypeAlias = Literal["smart", "dumb"]
MonsterBehavior: TypeAlias = Literal["kind", "balanced", "evil"]
MonsterBehaviorSelection: TypeAlias = Literal["kind", "balanced", "evil", "combined"]
RoleTag: TypeAlias = Literal["healer", "caster", "controller"]
AttackId: TypeAlias = str
SizeCategory: TypeAlias = Literal["tiny", "small", "medium", "large", "huge", "gargantuan"]
TerrainFeatureKind: TypeAlias = Literal["rock"]
MasteryType: TypeAlias = Literal["graze", "sap", "slow", "cleave", "vex"]
AttackRiderType: TypeAlias = Literal["prone_on_hit", "grapple_on_hit", "grapple_and_restrain", "harry_target"]
AttackMode: TypeAlias = Literal["normal", "advantage", "disadvantage"]
EventType: TypeAlias = Literal[
    "turn_start",
    "effect_expired",
    "death_save",
    "saving_throw",
    "heal",
    "move",
    "attack",
    "ongoing_damage",
    "stabilize",
    "phase_change",
    "skip",
]
EventFieldValue: TypeAlias = int | str | bool | None | list[int] | list[str]
TerminalState: TypeAlias = Literal["ongoing", "rescue", "complete"]
BatchJobState: TypeAlias = Literal["queued", "running", "completed", "failed"]


class GridPosition(CamelModel):
    x: int
    y: int


class Footprint(CamelModel):
    width: int
    height: int


class TerrainFeature(CamelModel):
    feature_id: str
    kind: TerrainFeatureKind
    position: GridPosition
    footprint: Footprint


class AbilityModifiers(CamelModel):
    str: int
    dex: int
    con: int
    int: int
    wis: int
    cha: int


class ConditionState(CamelModel):
    unconscious: bool
    prone: bool
    dead: bool


RESOURCE_FIELD_BY_POOL = {
    "second_wind": "second_wind_uses",
    "javelins": "javelins",
    "rage": "rage_uses",
    "handaxes": "handaxes",
    "action_surge": "action_surge_uses",
    "superiority_dice": "superiority_dice",
    "focus_points": "focus_points",
    "uncanny_metabolism": "uncanny_metabolism_uses",
    "spell_slots_level_1": "spell_slots_level_1",
    "lay_on_hands": "lay_on_hands_points",
}


class ResourceState(CamelModel):
    second_wind_uses: int
    javelins: int
    rage_uses: int
    handaxes: int
    action_surge_uses: int
    superiority_dice: int
    focus_points: int
    uncanny_metabolism_uses: int
    spell_slots_level_1: int
    lay_on_hands_points: int

    def get_pool(self, pool_id: str) -> int:
        field_name = RESOURCE_FIELD_BY_POOL.get(pool_id)
        if not field_name:
            return 0
        return getattr(self, field_name, 0)

    def set_pool(self, pool_id: str, amount: int) -> None:
        field_name = RESOURCE_FIELD_BY_POOL.get(pool_id)
        if not field_name:
            raise ValueError(f"Unknown resource pool '{pool_id}'.")
        setattr(self, field_name, max(0, amount))

    def spend_pool(self, pool_id: str, amount: int = 1) -> bool:
        current_amount = self.get_pool(pool_id)
        if current_amount < amount:
            return False
        self.set_pool(pool_id, current_amount - amount)
        return True


class DiceSpec(CamelModel):
    count: int
    sides: int


class WeaponRange(CamelModel):
    normal: int
    long: int


class WeaponDamageComponent(CamelModel):
    damage_type: str
    damage_dice: list[DiceSpec]
    damage_modifier: int = 0


class OnHitEffect(CamelModel):
    kind: AttackRiderType
    escape_dc: int | None = None
    max_target_size: SizeCategory | None = None


class WeaponProfile(CamelModel):
    id: AttackId
    display_name: str
    attack_bonus: int
    ability_modifier: int
    attack_ability: Literal["str", "dex"] | None = None
    damage_dice: list[DiceSpec] = Field(default_factory=list)
    damage_modifier: int = 0
    damage_type: str | None = None
    selectable_damage_types: list[str] | None = None
    damage_components: list[WeaponDamageComponent] | None = None
    mastery: MasteryType | None = None
    kind: Literal["melee", "ranged"]
    finesse: bool | None = None
    two_handed: bool | None = None
    reach: int | None = None
    range: WeaponRange | None = None
    advantage_damage_dice: list[DiceSpec] | None = None
    advantage_damage_components: list[WeaponDamageComponent] | None = None
    advantage_against_self_grappled_target: bool | None = None
    on_hit_effects: list[OnHitEffect] | None = None
    locks_to_grappled_target: bool | None = None
    resource_pool_id: str | None = None

    @model_serializer(mode="wrap")
    def serialize_without_undefined_fields(self, handler):
        data = handler(self)
        # Match JSON.stringify on the TypeScript side: optional weapon properties are omitted,
        # while explicit nulls elsewhere in the event/state payload stay present.
        return {key: value for key, value in data.items() if value is not None}


class SapEffect(CamelModel):
    kind: Literal["sap"]
    source_id: str
    expires_at_turn_start_of: str


class SlowEffect(CamelModel):
    kind: Literal["slow"]
    source_id: str
    expires_at_turn_start_of: str
    penalty: int


class NoReactionsEffect(CamelModel):
    kind: Literal["no_reactions"]
    source_id: str
    expires_at_turn_start_of: str


class PoisonedEffect(CamelModel):
    kind: Literal["poisoned"]
    source_id: str
    save_dc: int
    remaining_rounds: int


class BlessedEffect(CamelModel):
    kind: Literal["blessed"]
    source_id: str


class ConcentrationEffect(CamelModel):
    kind: Literal["concentration"]
    source_id: str
    spell_id: str
    remaining_rounds: int


class HiddenEffect(CamelModel):
    kind: Literal["hidden"]
    source_id: str | None = None
    expires_at_turn_start_of: str | None = None


class DodgingEffect(CamelModel):
    kind: Literal["dodging"]
    source_id: str
    expires_at_turn_start_of: str


class ShieldEffect(CamelModel):
    kind: Literal["shield"]
    source_id: str
    expires_at_turn_start_of: str
    ac_bonus: int


class InvisibleEffect(CamelModel):
    kind: Literal["invisible"]
    source_id: str | None = None
    expires_at_turn_start_of: str | None = None


class GrappledEffect(CamelModel):
    kind: Literal["grappled_by"]
    source_id: str
    escape_dc: int
    maintain_reach_feet: int | None = None


class RestrainedEffect(CamelModel):
    kind: Literal["restrained_by"]
    source_id: str
    escape_dc: int


class BlindedEffect(CamelModel):
    kind: Literal["blinded_by"]
    source_id: str


class RageEffect(CamelModel):
    kind: Literal["rage"]
    source_id: str
    damage_bonus: int
    remaining_rounds: int


class RecklessAttackEffect(CamelModel):
    kind: Literal["reckless_attack"]
    source_id: str
    expires_at_turn_start_of: str


class SwallowedEffect(CamelModel):
    kind: Literal["swallowed_by"]
    source_id: str


class VexEffect(CamelModel):
    kind: Literal["vex"]
    source_id: str
    target_id: str
    expires_at_turn_end_of: str
    expires_at_round: int


class HarriedEffect(CamelModel):
    kind: Literal["harried_by"]
    source_id: str
    target_id: str
    expires_at_turn_start_of: str


TemporaryEffect: TypeAlias = (
    SapEffect
    | SlowEffect
    | NoReactionsEffect
    | PoisonedEffect
    | BlessedEffect
    | ConcentrationEffect
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
    | VexEffect
    | HarriedEffect
)


class UnitState(CamelModel):
    id: str
    faction: Faction
    combat_role: CombatRole
    template_name: str
    role_tags: list[RoleTag]
    current_hp: int
    max_hp: int
    temporary_hit_points: int = 0
    ac: int
    speed: int
    effective_speed: int
    initiative_mod: int
    initiative_score: int
    ability_mods: AbilityModifiers
    passive_perception: int
    size_category: SizeCategory
    footprint: Footprint
    conditions: ConditionState
    death_save_successes: int
    death_save_failures: int
    stable: bool
    resources: ResourceState
    position: GridPosition | None = None
    temporary_effects: list[TemporaryEffect]
    reaction_available: bool
    attacks: dict[AttackId, WeaponProfile]
    medicine_modifier: int
    damage_resistances: tuple[str, ...] = Field(default=(), exclude=True)
    damage_immunities: tuple[str, ...] = Field(default=(), exclude=True)
    damage_vulnerabilities: tuple[str, ...] = Field(default=(), exclude=True)
    condition_immunities: tuple[str, ...] = Field(default=(), exclude=True)
    creature_tags: tuple[str, ...] = Field(default=(), exclude=True)
    # These player-build fields are runtime-only for now. They are kept out of
    # the live API payload until the UI is ready to select classes/loadouts
    # directly, but the engine can already use them internally.
    class_id: str | None = Field(default=None, exclude=True)
    level: int | None = Field(default=None, exclude=True)
    loadout_id: str | None = Field(default=None, exclude=True)
    feature_ids: list[str] = Field(default_factory=list, exclude=True)
    resource_pools: dict[str, int] = Field(default_factory=dict, exclude=True)
    behavior_profile: str | None = Field(default=None, exclude=True)
    combat_skill_modifiers: dict[str, int] = Field(default_factory=dict, exclude=True)
    combat_cantrip_ids: list[str] = Field(default_factory=list, exclude=True)
    prepared_combat_spell_ids: list[str] = Field(default_factory=list, exclude=True)
    cantrips_known: int = Field(default=0, exclude=True)
    spellbook_spells: int = Field(default=0, exclude=True)
    prepared_spells: int = Field(default=0, exclude=True)
    # This is runtime-only AI memory. It is intentionally kept out of the
    # serialized API shape so the frontend and old parity fixtures do not gain
    # extra state fields just to support local monster behavior.
    _committed_to_melee: bool = PrivateAttr(default=False)
    # Rage upkeep is checked at the end of the barbarian's turn, but the
    # qualifying attack-or-damage signal is gathered across the full round.
    _rage_qualified_since_turn_end: bool = PrivateAttr(default=False)
    _rage_extended_this_turn: bool = PrivateAttr(default=False)
    _cleave_used_this_turn: bool = PrivateAttr(default=False)
    _bonus_action_used_this_turn: bool = PrivateAttr(default=False)
    _great_weapon_master_hewing_used_this_turn: bool = PrivateAttr(default=False)
    _savage_attacker_used_this_turn: bool = PrivateAttr(default=False)
    _reckless_attack_available_this_turn: bool = PrivateAttr(default=False)
    _steady_aim_active_this_turn: bool = PrivateAttr(default=False)
    # Standing from prone consumes movement on the current turn, but that cost
    # should not leak into serialized encounter state.
    _turn_stand_up_cost_squares: int = PrivateAttr(default=0)


class DamageCandidate(CamelModel):
    components: list["DamageComponentResult"] = Field(default_factory=list)
    raw_rolls: list[int]
    adjusted_rolls: list[int]
    subtotal: int


class DamageComponentResult(CamelModel):
    damage_type: str
    raw_rolls: list[int]
    adjusted_rolls: list[int]
    subtotal: int
    flat_modifier: int
    total_damage: int


class DamageDetails(CamelModel):
    weapon_id: AttackId
    weapon_name: str
    damage_components: list[DamageComponentResult]
    primary_candidate: DamageCandidate | None
    savage_candidate: DamageCandidate | None
    chosen_candidate: Literal["primary", "savage"] | None
    critical_applied: bool
    critical_multiplier: int
    flat_modifier: int
    advantage_bonus_candidate: DamageCandidate | None
    mastery_applied: MasteryType | None
    mastery_notes: str | None
    maneuver_applied: str | None = None
    maneuver_notes: str | None = None
    attack_riders_applied: list[AttackRiderType] | None = None
    total_damage: int
    resisted_damage: int
    amplified_damage: int | None = None
    temporary_hp_absorbed: int
    final_damage_to_hp: int
    hp_delta: int

    @model_serializer(mode="wrap")
    def serialize_optional_attack_riders(self, handler):
        data = handler(self)
        if data.get("attackRidersApplied") is None:
            data.pop("attackRidersApplied", None)
        if data.get("maneuverApplied") is None:
            data.pop("maneuverApplied", None)
        if data.get("maneuverNotes") is None:
            data.pop("maneuverNotes", None)
        if data.get("amplifiedDamage") is None:
            data.pop("amplifiedDamage", None)
        return data


class MovementDetails(CamelModel):
    start: GridPosition | None = None
    end: GridPosition | None = None
    path: list[GridPosition] | None = None
    distance: int | None = None


class CombatEvent(CamelModel):
    round: int
    actor_id: str
    target_ids: list[str]
    event_type: EventType
    raw_rolls: dict[str, EventFieldValue]
    resolved_totals: dict[str, EventFieldValue]
    movement_details: MovementDetails | None
    damage_details: DamageDetails | None
    condition_deltas: list[str]
    text_summary: str


class EncounterState(CamelModel):
    seed: str
    player_behavior: ResolvedPlayerBehavior
    monster_behavior: MonsterBehavior
    rng_state: int
    round: int
    initiative_order: list[str]
    initiative_scores: dict[str, int]
    active_combatant_index: int
    units: dict[str, UnitState]
    combat_log: list[CombatEvent]
    winner: Winner | None = None
    terminal_state: TerminalState
    rescue_subphase: bool
    # Terrain is runtime-only for now. The engine needs it for pathing and cover,
    # while the UI reads fixed terrain from the preset catalog instead of combat state.
    terrain_features: list[TerrainFeature] = Field(default_factory=list, exclude=True)


class ReplayFrame(CamelModel):
    index: int
    round: int
    active_combatant_id: str
    state: EncounterState
    events: list[CombatEvent]


class EncounterConfig(CamelModel):
    seed: str
    placements: dict[str, GridPosition] | None = None
    batch_size: int | None = None
    player_behavior: PlayerBehavior | None = None
    monster_behavior: MonsterBehaviorSelection | None = None
    enemy_preset_id: str | None = None
    player_preset_id: str | None = None


class RunEncounterResult(CamelModel):
    final_state: EncounterState
    events: list[CombatEvent]
    replay_frames: list[ReplayFrame]


class EncounterSummary(CamelModel):
    seed: str
    player_behavior: ResolvedPlayerBehavior
    monster_behavior: MonsterBehavior
    winner: Winner | None = None
    rounds: int
    fighter_deaths: int
    goblins_killed: int
    remaining_fighter_hp: int
    remaining_goblin_hp: int
    stable_unconscious_fighters: int
    conscious_fighters: int


class BatchCombinationSummary(CamelModel):
    seed: str
    player_behavior: PlayerBehavior
    monster_behavior: MonsterBehavior
    batch_size: int
    total_runs: int
    player_win_rate: int | float
    goblin_win_rate: int | float
    mutual_annihilation_rate: int | float
    smart_player_win_rate: int | float | None
    dumb_player_win_rate: int | float | None
    smart_run_count: int
    dumb_run_count: int
    average_rounds: int | float
    average_fighter_deaths: int | float
    average_goblins_killed: int | float
    average_remaining_fighter_hp: int | float
    average_remaining_goblin_hp: int | float
    stable_but_unconscious_count: int


class BatchSummary(CamelModel):
    seed: str
    player_behavior: PlayerBehavior
    monster_behavior: MonsterBehaviorSelection
    batch_size: int
    total_runs: int
    player_win_rate: int | float
    goblin_win_rate: int | float
    mutual_annihilation_rate: int | float
    smart_player_win_rate: int | float | None
    dumb_player_win_rate: int | float | None
    smart_run_count: int
    dumb_run_count: int
    average_rounds: int | float
    average_fighter_deaths: int | float
    average_goblins_killed: int | float
    average_remaining_fighter_hp: int | float
    average_remaining_goblin_hp: int | float
    stable_but_unconscious_count: int
    combination_summaries: list[BatchCombinationSummary] | None


class BatchJobStatus(CamelModel):
    job_id: str
    status: BatchJobState
    completed_runs: int
    total_runs: int
    progress_ratio: int | float
    started_at: datetime
    finished_at: datetime | None = None
    elapsed_seconds: int | float
    current_monster_behavior: MonsterBehavior | None = None
    batch_summary: BatchSummary | None = None
    error: str | None = None


class StepEncounterResult(CamelModel):
    state: EncounterState
    events: list[CombatEvent]
    done: bool
