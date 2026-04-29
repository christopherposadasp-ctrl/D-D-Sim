from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.player_loadouts import DEFAULT_PLAYER_PRESET_ID
from backend.content.scenario_definitions import get_scenario_definition
from backend.engine import run_encounter
from backend.engine.models.state import EncounterConfig, RunEncounterResult
from scripts.audit_common import collect_git_context, write_json_report, write_text_report
from scripts.run_party_validation import DEFAULT_SCENARIO_IDS

PROFILE_CHOICES = ("paladin", "rogue", "fighter", "wizard")
PROFILE_DEFAULT_UNIT_IDS = {"paladin": "F2", "rogue": "F3", "fighter": "F1", "wizard": "F4"}
PARTY_PROFILE_ORDER = ("fighter", "paladin", "rogue", "wizard")
PARTY_PROFILE_UNIT_IDS = {"fighter": "F1", "paladin": "F2", "rogue": "F3", "wizard": "F4"}
DEFAULT_PROFILE = "paladin"
DEFAULT_UNIT_ID = PROFILE_DEFAULT_UNIT_IDS[DEFAULT_PROFILE]
DEFAULT_RUNS_PER_SCENARIO = 60
DEFAULT_PLAYER_BEHAVIOR = "smart"
FIGHTER_DEFAULT_PLAYER_BEHAVIOR = "both"
DEFAULT_MONSTER_BEHAVIOR = "balanced"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pc_tuning"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "pc_tuning_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "pc_tuning_latest.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run event-level PC tuning samples for the current party.")
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default=DEFAULT_PROFILE, help="PC tuning profile to run.")
    parser.add_argument(
        "--unit",
        default=None,
        help="Unit id to analyze. Defaults to the current-party unit for the selected profile.",
    )
    parser.add_argument("--player-preset", default=DEFAULT_PLAYER_PRESET_ID, help="Player preset id to validate.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        help="Scenario id to sample. Repeat to include more. Defaults to the standard party-validation set.",
    )
    parser.add_argument(
        "--runs-per-scenario",
        type=int,
        default=DEFAULT_RUNS_PER_SCENARIO,
        help="Deterministic event-level replays per scenario.",
    )
    parser.add_argument(
        "--player-behavior",
        choices=("smart", "dumb", "both"),
        default=None,
        help="Player behavior to sample. Fighter defaults to both; other profiles default to smart.",
    )
    parser.add_argument(
        "--monster-behavior",
        choices=("kind", "balanced", "evil"),
        default=DEFAULT_MONSTER_BEHAVIOR,
        help="Monster behavior to sample.",
    )
    parser.add_argument("--json", action="store_true", help="Print the final JSON payload to stdout.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH, help="Write the JSON report here.")
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH, help="Write the Markdown report here.")
    return parser.parse_args()


def validate_scenarios(scenario_ids: tuple[str, ...]) -> None:
    for scenario_id in scenario_ids:
        get_scenario_definition(scenario_id)


def percent(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 1) if denominator else 0.0


def average(values: list[int | float]) -> float:
    return round(mean(values), 2) if values else 0.0


def distribution(values: list[int]) -> dict[str, int]:
    return {str(value): count for value, count in sorted(Counter(values).items())}


def resolve_profile_unit_id(profile: str, unit_id: str | None) -> str:
    return unit_id or PROFILE_DEFAULT_UNIT_IDS[profile]


def resolve_profile_player_behavior(profile: str, player_behavior: str | None) -> str:
    if player_behavior:
        return player_behavior
    return FIGHTER_DEFAULT_PLAYER_BEHAVIOR if profile == "fighter" else DEFAULT_PLAYER_BEHAVIOR


def ordered_party_profiles(selected_profile: str) -> tuple[str, ...]:
    if selected_profile not in PARTY_PROFILE_ORDER:
        raise ValueError(f"Unsupported PC tuning profile `{selected_profile}`.")
    return tuple(profile for profile in PARTY_PROFILE_ORDER if profile != selected_profile) + (selected_profile,)


def new_metrics(profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    return {
        "profile": profile,
        "runs": 0,
        "wins": Counter(),
        "rounds": [],
        "endingSpellSlots": [],
        "endingSpellSlotsLevel1": [],
        "endingSpellSlotsLevel2": [],
        "endingSpellSlotsLevel3": [],
        "endingLayOnHands": [],
        "paladinDownAtEnd": 0,
        "paladinEvents": 0,
        "blessCasts": 0,
        "divineSmites": 0,
        "sentinelGuardianTriggers": 0,
        "sentinelHaltApplied": 0,
        "naturesWrathUses": 0,
        "naturesWrathTargets": [],
        "naturesWrathRestrained": [],
        "layOnHandsUses": 0,
        "layOnHandsTotalHealing": 0,
        "layOnHandsHeals": [],
        "layOnHandsDownedPickups": 0,
        "cureWoundsUses": 0,
        "cureWoundsTotalHealing": 0,
        "cureWoundsHeals": [],
        "cureWoundsDownedPickups": 0,
        "endingWizardHp": [],
        "wizardDownAtEnd": 0,
        "wizardEvents": 0,
        "wizardTurns": 0,
        "wizardDeathSaves": 0,
        "wizardSkipTurns": 0,
        "wizardIncomingAttackHits": 0,
        "wizardIncomingDamageToHp": 0,
        "wizardDamagingHitsTaken": 0,
        "wizardAttacks": 0,
        "wizardHits": 0,
        "wizardCrits": 0,
        "wizardDamageToHp": 0,
        "wizardSpellCasts": Counter(),
        "wizardSpellDamage": Counter(),
        "wizardSpellSlotsSpent": 0,
        "wizardSpellSlotsSpentBySpell": Counter(),
        "wizardSpellSlotsSpentByLevel": Counter(),
        "wizardCantripDamage": 0,
        "wizardSlottedSpellDamage": 0,
        "wizardAttackModeCounts": Counter(),
        "wizardAdvantageSourceCounts": Counter(),
        "wizardDisadvantageSourceCounts": Counter(),
        "fireBoltCasts": 0,
        "fireBoltHits": 0,
        "fireBoltDamage": 0,
        "shockingGraspCasts": 0,
        "shockingGraspHits": 0,
        "shockingGraspDamage": 0,
        "shockingGraspNoReactionApplications": 0,
        "shockingGraspRetreats": 0,
        "magicMissileCasts": 0,
        "magicMissileDamage": 0,
        "magicMissileKillSecures": 0,
        "magicMissileOverkillDamage": 0,
        "magicMissileBlockedByShield": 0,
        "magicMissileCastsByLevel": Counter(),
        "magicMissileProjectiles": 0,
        "magicMissileSplitCasts": 0,
        "burningHandsCasts": 0,
        "burningHandsTargetDamageEvents": 0,
        "burningHandsDamage": 0,
        "burningHandsEnemyTargets": [],
        "burningHandsAllyTargets": [],
        "burningHandsLowValueCasts": 0,
        "burningHandsFriendlyFireCasts": 0,
        "burningHandsSaveSuccesses": 0,
        "burningHandsSaveFailures": 0,
        "scorchingRayCasts": 0,
        "scorchingRayRayAttacks": 0,
        "scorchingRayHits": 0,
        "scorchingRayDamage": 0,
        "scorchingRayKillSecures": 0,
        "scorchingRaySplitCasts": 0,
        "scorchingRayUniqueTargets": [],
        "shatterCasts": 0,
        "shatterTargetDamageEvents": 0,
        "shatterDamage": 0,
        "shatterTargetCounts": [],
        "shatterSaveSuccesses": 0,
        "shatterSaveFailures": 0,
        "shieldCasts": 0,
        "shieldPreventedHits": 0,
        "shieldFailedToStopHits": 0,
        "shieldMagicMissileBlocks": 0,
        "mageArmorCasts": 0,
        "mageArmorAcChanged": 0,
        "daggerFallbackAttacks": 0,
        "daggerFallbackHits": 0,
        "daggerFallbackDamage": 0,
        "wizardMovementEvents": 0,
        "wizardMovementSquares": 0,
        "endingRogueHp": [],
        "rogueDownAtEnd": 0,
        "rogueEvents": 0,
        "rogueAttacks": 0,
        "rogueHits": 0,
        "rogueCrits": 0,
        "rogueDamageToHp": 0,
        "rogueWeaponAttacks": Counter(),
        "rogueAttackModeCounts": Counter(),
        "rogueAdvantageSourceCounts": Counter(),
        "rogueDisadvantageSourceCounts": Counter(),
        "rogueAdvantageAttacks": 0,
        "rogueDisadvantageAttacks": 0,
        "sneakAttackApplications": 0,
        "sneakAttackDamage": 0,
        "sneakAttackDiceRolled": 0,
        "hitsWithoutSneakAttack": 0,
        "assassinateAdvantageAttacks": 0,
        "assassinateDamageApplications": 0,
        "assassinateDamageTotal": 0,
        "steadyAimUses": 0,
        "attacksWithSteadyAim": 0,
        "hideAttempts": 0,
        "hideSuccesses": 0,
        "attacksFromHidden": 0,
        "sharpshooterApplications": 0,
        "sharpshooterCoverIgnoredEvents": 0,
        "sharpshooterCoverAcIgnoredTotal": 0,
        "sharpshooterIgnoredDisadvantageSourceCounts": Counter(),
        "cunningStrikeUses": 0,
        "cunningStrikeCounts": Counter(),
        "cunningStrikeSneakDiceSpent": 0,
        "uncannyDodgeUses": 0,
        "uncannyDodgeDamagePrevented": 0,
        "incomingAttackHits": 0,
        "incomingDamageToHp": 0,
        "damagingHitsTakenWithoutUncannyDodge": 0,
        "movementEvents": 0,
        "movementSquares": 0,
        "disengageMovementEvents": 0,
        "endingFighterHp": [],
        "endingSuperiorityDice": [],
        "endingActionSurgeUses": [],
        "endingSecondWindUses": [],
        "fighterDownAtEnd": 0,
        "fighterEvents": 0,
        "fighterAttacks": 0,
        "fighterHits": 0,
        "fighterCrits": 0,
        "fighterDamageToHp": 0,
        "fighterWeaponAttacks": Counter(),
        "fighterAttackSourceCounts": Counter(),
        "fighterDamageBySource": Counter(),
        "fighterAttackModeCounts": Counter(),
        "fighterAdvantageSourceCounts": Counter(),
        "fighterDisadvantageSourceCounts": Counter(),
        "actionSurgeUses": 0,
        "actionSurgeAttacks": 0,
        "actionSurgeDamageToHp": 0,
        "superiorityDiceSpent": 0,
        "maneuverCounts": Counter(),
        "precisionUses": 0,
        "precisionConverted": 0,
        "precisionFailed": 0,
        "precisionMissMargins": [],
        "precisionOnRiposteUses": 0,
        "tripAttackUses": 0,
        "tripSaveSuccesses": 0,
        "tripSaveFailures": 0,
        "tripProneApplied": 0,
        "tripFollowUpAttacks": 0,
        "riposteTriggers": 0,
        "riposteAttacks": 0,
        "riposteHits": 0,
        "riposteDamageToHp": 0,
        "opportunityAttacks": 0,
        "opportunityHits": 0,
        "greatWeaponMasterDamageApplications": 0,
        "greatWeaponMasterDamageTotal": 0,
        "hewTriggers": 0,
        "hewAttacks": 0,
        "hewHits": 0,
        "hewDamageToHp": 0,
        "secondWindUses": 0,
        "secondWindTotalHealing": 0,
        "secondWindHeals": [],
        "tacticalShiftUses": 0,
        "tacticalShiftSquares": 0,
    }


def add_metric(counter: dict[str, Any], key: str, value: int = 1) -> None:
    counter[key] = int(counter.get(key, 0)) + value


def record_paladin_run(metrics: dict[str, Any], result: RunEncounterResult, unit_id: str) -> None:
    final_state = result.final_state
    paladin = final_state.units[unit_id]
    metrics["runs"] += 1
    metrics["wins"][final_state.winner] += 1
    metrics["rounds"].append(final_state.round)
    ending_level_1_slots = paladin.resources.spell_slots_level_1
    ending_level_2_slots = paladin.resources.spell_slots_level_2
    metrics["endingSpellSlots"].append(ending_level_1_slots + ending_level_2_slots)
    metrics["endingSpellSlotsLevel1"].append(ending_level_1_slots)
    metrics["endingSpellSlotsLevel2"].append(ending_level_2_slots)
    metrics["endingLayOnHands"].append(paladin.resources.lay_on_hands_points)
    if paladin.current_hp <= 0 or paladin.conditions.dead or paladin.conditions.unconscious:
        add_metric(metrics, "paladinDownAtEnd")

    previous_unconscious: dict[str, bool] = {}
    if result.replay_frames:
        for current_unit_id, unit in result.replay_frames[0].state.units.items():
            previous_unconscious[current_unit_id] = unit.conditions.unconscious or unit.current_hp <= 0

    for frame in result.replay_frames[1:]:
        for event in frame.events:
            resolved_totals = event.resolved_totals or {}
            text = (event.text_summary or "").lower()
            is_actor = event.actor_id == unit_id
            is_reaction = (
                resolved_totals.get("reactionActorId") == unit_id
                or resolved_totals.get("defenseReactionActorId") == unit_id
            )
            if not (is_actor or is_reaction):
                continue

            add_metric(metrics, "paladinEvents")
            if resolved_totals.get("spellId") == "bless" or "casts bless" in text:
                add_metric(metrics, "blessCasts")
            if resolved_totals.get("divineSmiteApplied") is True:
                add_metric(metrics, "divineSmites")
            if resolved_totals.get("reaction") == "sentinel_guardian":
                add_metric(metrics, "sentinelGuardianTriggers")
            if resolved_totals.get("sentinelHaltApplied") is True:
                add_metric(metrics, "sentinelHaltApplied")
            if resolved_totals.get("specialAction") == "natures_wrath":
                add_metric(metrics, "naturesWrathUses")
                metrics["naturesWrathTargets"].append(len(resolved_totals.get("affectedTargetIds") or []))
                metrics["naturesWrathRestrained"].append(len(resolved_totals.get("restrainedTargetIds") or []))

            if event.event_type != "heal" or not is_actor:
                continue

            healing_total = int(resolved_totals.get("healingTotal") or 0)
            target_id = event.target_ids[0] if event.target_ids else None
            was_down = bool(target_id and previous_unconscious.get(target_id))
            is_lay_on_hands = "lay on hands" in text or "layOnHandsPointsRemaining" in resolved_totals
            is_cure_wounds = resolved_totals.get("spellId") == "cure_wounds" or "cure wounds" in text

            if is_lay_on_hands:
                add_metric(metrics, "layOnHandsUses")
                add_metric(metrics, "layOnHandsTotalHealing", healing_total)
                metrics["layOnHandsHeals"].append(healing_total)
                if was_down:
                    add_metric(metrics, "layOnHandsDownedPickups")
            elif is_cure_wounds:
                add_metric(metrics, "cureWoundsUses")
                add_metric(metrics, "cureWoundsTotalHealing", healing_total)
                metrics["cureWoundsHeals"].append(healing_total)
                if was_down:
                    add_metric(metrics, "cureWoundsDownedPickups")

        for current_unit_id, unit in frame.state.units.items():
            previous_unconscious[current_unit_id] = unit.conditions.unconscious or unit.current_hp <= 0


def get_event_damage_to_hp(event: Any) -> int:
    if not event.damage_details:
        return 0
    return int(event.damage_details.final_damage_to_hp or 0)


def record_wizard_spell_slot_spend(metrics: dict[str, Any], spell_id: str, resolved_totals: dict[str, Any]) -> None:
    spell_level = int(resolved_totals.get("spellLevel") or 0)
    if spell_level <= 0:
        return
    add_metric(metrics, "wizardSpellSlotsSpent")
    metrics["wizardSpellSlotsSpentBySpell"][spell_id] += 1
    metrics["wizardSpellSlotsSpentByLevel"][str(spell_level)] += 1


def record_wizard_attack(metrics: dict[str, Any], event: Any) -> None:
    resolved_totals = event.resolved_totals or {}
    raw_rolls = event.raw_rolls or {}
    damage_details = event.damage_details
    spell_id = str(resolved_totals.get("spellId") or "")
    weapon_id = damage_details.weapon_id if damage_details else "unknown"
    damage_to_hp = get_event_damage_to_hp(event)
    hit = resolved_totals.get("hit") is True
    attack_mode = str(resolved_totals.get("attackMode") or "normal")

    add_metric(metrics, "wizardAttacks")
    metrics["wizardAttackModeCounts"][attack_mode] += 1
    metrics["wizardAdvantageSourceCounts"].update(list(raw_rolls.get("advantageSources") or []))
    metrics["wizardDisadvantageSourceCounts"].update(list(raw_rolls.get("disadvantageSources") or []))
    if hit:
        add_metric(metrics, "wizardHits")
    if resolved_totals.get("critical") is True:
        add_metric(metrics, "wizardCrits")

    add_metric(metrics, "wizardDamageToHp", damage_to_hp)
    if spell_id:
        metrics["wizardSpellDamage"][spell_id] += damage_to_hp
        if int(resolved_totals.get("spellLevel") or 0) <= 0:
            add_metric(metrics, "wizardCantripDamage", damage_to_hp)
        else:
            add_metric(metrics, "wizardSlottedSpellDamage", damage_to_hp)
    elif weapon_id == "dagger":
        add_metric(metrics, "daggerFallbackAttacks")
        add_metric(metrics, "daggerFallbackDamage", damage_to_hp)
        if hit:
            add_metric(metrics, "daggerFallbackHits")

    if spell_id == "fire_bolt":
        add_metric(metrics, "fireBoltCasts")
        add_metric(metrics, "fireBoltDamage", damage_to_hp)
        if hit:
            add_metric(metrics, "fireBoltHits")
    elif spell_id == "shocking_grasp":
        add_metric(metrics, "shockingGraspCasts")
        add_metric(metrics, "shockingGraspDamage", damage_to_hp)
        if hit:
            add_metric(metrics, "shockingGraspHits")
        if any("cannot take reactions" in delta.lower() for delta in event.condition_deltas):
            add_metric(metrics, "shockingGraspNoReactionApplications")
    elif spell_id == "magic_missile":
        if resolved_totals.get("spellCastEvent") is not False:
            add_metric(metrics, "magicMissileCasts")
            spell_level = int(resolved_totals.get("spellLevel") or 1)
            metrics["magicMissileCastsByLevel"][str(spell_level)] += 1
            add_metric(metrics, "magicMissileProjectiles", int(resolved_totals.get("dartCount") or 0))
            if int(resolved_totals.get("projectileGroupCount") or 1) > 1:
                add_metric(metrics, "magicMissileSplitCasts")
        add_metric(metrics, "magicMissileDamage", damage_to_hp)
        if resolved_totals.get("targetDroppedToZero") is True:
            add_metric(metrics, "magicMissileKillSecures")
        total_damage = int(damage_details.total_damage or 0) if damage_details else 0
        add_metric(metrics, "magicMissileOverkillDamage", max(0, total_damage - damage_to_hp))
        if resolved_totals.get("blockedByShield") is True:
            add_metric(metrics, "magicMissileBlockedByShield")
    elif spell_id == "burning_hands":
        add_metric(metrics, "burningHandsTargetDamageEvents")
        add_metric(metrics, "burningHandsDamage", damage_to_hp)
        if resolved_totals.get("saveSucceeded") is True:
            add_metric(metrics, "burningHandsSaveSuccesses")
        else:
            add_metric(metrics, "burningHandsSaveFailures")
    elif spell_id == "scorching_ray":
        add_metric(metrics, "scorchingRayRayAttacks")
        add_metric(metrics, "scorchingRayDamage", damage_to_hp)
        if hit:
            add_metric(metrics, "scorchingRayHits")
        if resolved_totals.get("targetDroppedToZero") is True:
            add_metric(metrics, "scorchingRayKillSecures")
    elif spell_id == "shatter":
        add_metric(metrics, "shatterTargetDamageEvents")
        add_metric(metrics, "shatterDamage", damage_to_hp)
        if resolved_totals.get("saveSucceeded") is True:
            add_metric(metrics, "shatterSaveSuccesses")
        else:
            add_metric(metrics, "shatterSaveFailures")


def record_wizard_run(metrics: dict[str, Any], result: RunEncounterResult, unit_id: str) -> None:
    final_state = result.final_state
    wizard = final_state.units[unit_id]
    metrics["runs"] += 1
    metrics["wins"][final_state.winner] += 1
    metrics["rounds"].append(final_state.round)
    ending_level_1_slots = wizard.resources.spell_slots_level_1
    ending_level_2_slots = wizard.resources.spell_slots_level_2
    ending_level_3_slots = getattr(wizard.resources, "spell_slots_level_3", 0)
    metrics["endingSpellSlots"].append(ending_level_1_slots + ending_level_2_slots + ending_level_3_slots)
    metrics["endingSpellSlotsLevel1"].append(ending_level_1_slots)
    metrics["endingSpellSlotsLevel2"].append(ending_level_2_slots)
    metrics["endingSpellSlotsLevel3"].append(ending_level_3_slots)
    metrics["endingWizardHp"].append(max(0, wizard.current_hp))
    if wizard.current_hp <= 0 or wizard.conditions.dead or wizard.conditions.unconscious:
        add_metric(metrics, "wizardDownAtEnd")

    pending_shocking_grasp_retreat = False

    for frame in result.replay_frames[1:]:
        for event in frame.events:
            resolved_totals = event.resolved_totals or {}
            spell_id = resolved_totals.get("spellId")
            is_actor = event.actor_id == unit_id
            targets_wizard = unit_id in event.target_ids and event.actor_id != unit_id

            if is_actor:
                add_metric(metrics, "wizardEvents")

            if is_actor and event.event_type == "turn_start":
                add_metric(metrics, "wizardTurns")
                pending_shocking_grasp_retreat = False
                continue

            if is_actor and event.event_type == "death_save":
                add_metric(metrics, "wizardDeathSaves")
                continue

            if is_actor and event.event_type == "skip":
                add_metric(metrics, "wizardSkipTurns")
                continue

            if is_actor and event.event_type == "movement":
                add_metric(metrics, "wizardMovementEvents")
                if event.movement_details and event.movement_details.distance:
                    add_metric(metrics, "wizardMovementSquares", int(event.movement_details.distance))
                if pending_shocking_grasp_retreat:
                    add_metric(metrics, "shockingGraspRetreats")
                    pending_shocking_grasp_retreat = False
                continue

            if is_actor and spell_id == "burning_hands" and event.event_type == "phase_change":
                spell_id_text = str(spell_id)
                metrics["wizardSpellCasts"][spell_id_text] += 1
                record_wizard_spell_slot_spend(metrics, spell_id_text, resolved_totals)
                add_metric(metrics, "burningHandsCasts")
                enemy_targets = int(resolved_totals.get("enemyTargetCount") or 0)
                ally_targets = int(resolved_totals.get("allyTargetCount") or 0)
                metrics["burningHandsEnemyTargets"].append(enemy_targets)
                metrics["burningHandsAllyTargets"].append(ally_targets)
                if enemy_targets < 2:
                    add_metric(metrics, "burningHandsLowValueCasts")
                if ally_targets > 0:
                    add_metric(metrics, "burningHandsFriendlyFireCasts")
                continue

            if is_actor and spell_id == "scorching_ray" and event.event_type == "phase_change":
                spell_id_text = str(spell_id)
                metrics["wizardSpellCasts"][spell_id_text] += 1
                record_wizard_spell_slot_spend(metrics, spell_id_text, resolved_totals)
                add_metric(metrics, "scorchingRayCasts")
                ray_target_ids = list(resolved_totals.get("rayTargetIds") or [])
                unique_target_count = len(set(ray_target_ids))
                metrics["scorchingRayUniqueTargets"].append(unique_target_count)
                if unique_target_count > 1:
                    add_metric(metrics, "scorchingRaySplitCasts")
                continue

            if is_actor and spell_id == "shatter" and event.event_type == "phase_change":
                spell_id_text = str(spell_id)
                metrics["wizardSpellCasts"][spell_id_text] += 1
                record_wizard_spell_slot_spend(metrics, spell_id_text, resolved_totals)
                add_metric(metrics, "shatterCasts")
                metrics["shatterTargetCounts"].append(int(resolved_totals.get("targetCount") or 0))
                continue

            if is_actor and resolved_totals.get("reaction") == "shield" and event.event_type == "phase_change":
                spell_id_text = "shield"
                metrics["wizardSpellCasts"][spell_id_text] += 1
                add_metric(metrics, "wizardSpellSlotsSpent")
                metrics["wizardSpellSlotsSpentBySpell"][spell_id_text] += 1
                metrics["wizardSpellSlotsSpentByLevel"]["1"] += 1
                add_metric(metrics, "shieldCasts")
                continue

            if is_actor and spell_id == "mage_armor" and event.event_type == "phase_change":
                spell_id_text = str(spell_id)
                metrics["wizardSpellCasts"][spell_id_text] += 1
                record_wizard_spell_slot_spend(metrics, spell_id_text, resolved_totals)
                add_metric(metrics, "mageArmorCasts")
                if resolved_totals.get("acChanged") is True:
                    add_metric(metrics, "mageArmorAcChanged")
                continue

            if is_actor and event.event_type == "attack":
                spell_cast_event = resolved_totals.get("spellCastEvent") is not False
                if spell_id and spell_id not in {"burning_hands", "scorching_ray", "shatter"} and spell_cast_event:
                    metrics["wizardSpellCasts"][str(spell_id)] += 1
                    record_wizard_spell_slot_spend(metrics, str(spell_id), resolved_totals)
                elif spell_id == "shatter" and int(resolved_totals.get("targetCount") or 0) <= 1 and spell_cast_event:
                    metrics["wizardSpellCasts"][str(spell_id)] += 1
                    record_wizard_spell_slot_spend(metrics, str(spell_id), resolved_totals)
                    add_metric(metrics, "shatterCasts")
                    metrics["shatterTargetCounts"].append(1)
                record_wizard_attack(metrics, event)
                if spell_id == "shocking_grasp" and resolved_totals.get("hit") is True:
                    pending_shocking_grasp_retreat = True
                continue

            if targets_wizard and event.event_type == "attack" and resolved_totals.get("hit") is True:
                add_metric(metrics, "wizardIncomingAttackHits")
                incoming_damage = get_event_damage_to_hp(event)
                add_metric(metrics, "wizardIncomingDamageToHp", incoming_damage)
                if incoming_damage > 0:
                    add_metric(metrics, "wizardDamagingHitsTaken")

            if (
                resolved_totals.get("defenseReaction") == "shield"
                and resolved_totals.get("defenseReactionActorId") == unit_id
            ):
                if resolved_totals.get("hit") is True:
                    add_metric(metrics, "shieldFailedToStopHits")
                else:
                    add_metric(metrics, "shieldPreventedHits")
            if resolved_totals.get("blockedByShield") is True and targets_wizard:
                add_metric(metrics, "shieldMagicMissileBlocks")


def record_rogue_attack(metrics: dict[str, Any], event: Any) -> None:
    resolved_totals = event.resolved_totals or {}
    raw_rolls = event.raw_rolls or {}
    damage_details = event.damage_details
    weapon_id = damage_details.weapon_id if damage_details else "unknown"
    advantage_sources = list(raw_rolls.get("advantageSources") or [])
    disadvantage_sources = list(raw_rolls.get("disadvantageSources") or [])
    ignored_disadvantage_sources = list(raw_rolls.get("sharpshooterIgnoredDisadvantageSources") or [])
    attack_mode = str(resolved_totals.get("attackMode") or "normal")
    hit = resolved_totals.get("hit") is True

    add_metric(metrics, "rogueAttacks")
    metrics["rogueWeaponAttacks"][weapon_id] += 1
    metrics["rogueAttackModeCounts"][attack_mode] += 1
    metrics["rogueAdvantageSourceCounts"].update(advantage_sources)
    metrics["rogueDisadvantageSourceCounts"].update(disadvantage_sources)
    metrics["sharpshooterIgnoredDisadvantageSourceCounts"].update(ignored_disadvantage_sources)

    if attack_mode == "advantage":
        add_metric(metrics, "rogueAdvantageAttacks")
    if attack_mode == "disadvantage":
        add_metric(metrics, "rogueDisadvantageAttacks")
    if "steady_aim" in advantage_sources:
        add_metric(metrics, "attacksWithSteadyAim")
    if "hidden" in advantage_sources:
        add_metric(metrics, "attacksFromHidden")
    if "assassinate" in advantage_sources:
        add_metric(metrics, "assassinateAdvantageAttacks")

    if hit:
        add_metric(metrics, "rogueHits")
    if resolved_totals.get("critical") is True:
        add_metric(metrics, "rogueCrits")

    damage_to_hp = get_event_damage_to_hp(event)
    add_metric(metrics, "rogueDamageToHp", damage_to_hp)

    sneak_components = [
        component
        for component in (damage_details.damage_components if damage_details else [])
        if component.damage_type == "precision"
    ]
    if sneak_components:
        add_metric(metrics, "sneakAttackApplications")
        add_metric(metrics, "sneakAttackDamage", sum(component.total_damage for component in sneak_components))
        add_metric(metrics, "sneakAttackDiceRolled", sum(len(component.raw_rolls) for component in sneak_components))
    elif hit:
        add_metric(metrics, "hitsWithoutSneakAttack")

    assassinate_damage = int(resolved_totals.get("assassinateDamageBonus") or 0)
    if assassinate_damage > 0:
        add_metric(metrics, "assassinateDamageApplications")
        add_metric(metrics, "assassinateDamageTotal", assassinate_damage)

    if resolved_totals.get("sharpshooterApplied") is True:
        add_metric(metrics, "sharpshooterApplications")
    ignored_cover = int(resolved_totals.get("sharpshooterIgnoredCoverAcBonus") or 0)
    if ignored_cover > 0:
        add_metric(metrics, "sharpshooterCoverIgnoredEvents")
        add_metric(metrics, "sharpshooterCoverAcIgnoredTotal", ignored_cover)

    cunning_strike_id = resolved_totals.get("cunningStrikeId")
    if cunning_strike_id:
        add_metric(metrics, "cunningStrikeUses")
        metrics["cunningStrikeCounts"][str(cunning_strike_id)] += 1
        add_metric(metrics, "cunningStrikeSneakDiceSpent", int(resolved_totals.get("sneakAttackDiceSpent") or 0))


def record_rogue_run(metrics: dict[str, Any], result: RunEncounterResult, unit_id: str) -> None:
    final_state = result.final_state
    rogue = final_state.units[unit_id]
    metrics["runs"] += 1
    metrics["wins"][final_state.winner] += 1
    metrics["rounds"].append(final_state.round)
    metrics["endingRogueHp"].append(max(0, rogue.current_hp))
    if rogue.current_hp <= 0 or rogue.conditions.dead or rogue.conditions.unconscious:
        add_metric(metrics, "rogueDownAtEnd")

    for frame in result.replay_frames[1:]:
        for event in frame.events:
            resolved_totals = event.resolved_totals or {}
            is_actor = event.actor_id == unit_id
            targets_rogue = unit_id in event.target_ids and event.actor_id != unit_id

            if is_actor:
                add_metric(metrics, "rogueEvents")
                if resolved_totals.get("steadyAim") is True:
                    add_metric(metrics, "steadyAimUses")
                if "hidden" in resolved_totals:
                    add_metric(metrics, "hideAttempts")
                    if resolved_totals.get("hidden") is True:
                        add_metric(metrics, "hideSuccesses")
                if event.event_type == "movement":
                    add_metric(metrics, "movementEvents")
                    if event.movement_details and event.movement_details.distance:
                        add_metric(metrics, "movementSquares", int(event.movement_details.distance))
                    if resolved_totals.get("disengageApplied") is True:
                        add_metric(metrics, "disengageMovementEvents")
                if event.event_type == "attack":
                    record_rogue_attack(metrics, event)

            if targets_rogue and event.event_type == "attack" and resolved_totals.get("hit") is True:
                add_metric(metrics, "incomingAttackHits")
                add_metric(metrics, "incomingDamageToHp", get_event_damage_to_hp(event))
                if resolved_totals.get("defenseReaction") != "uncanny_dodge":
                    add_metric(metrics, "damagingHitsTakenWithoutUncannyDodge")

            if (
                resolved_totals.get("defenseReaction") == "uncanny_dodge"
                and resolved_totals.get("defenseReactionActorId") == unit_id
            ):
                add_metric(metrics, "uncannyDodgeUses")
                add_metric(metrics, "uncannyDodgeDamagePrevented", int(resolved_totals.get("uncannyDodgeDamagePrevented") or 0))


def get_fighter_attack_count(unit: Any) -> int:
    return 2 if unit.class_id == "fighter" and (unit.level or 0) >= 5 else 1


def get_precision_miss_margin(event: Any) -> int | None:
    resolved_totals = event.resolved_totals or {}
    superiority_rolls = list((event.raw_rolls or {}).get("superiorityDiceRolls") or [])
    if not superiority_rolls:
        return None
    attack_total = resolved_totals.get("attackTotal")
    target_ac = resolved_totals.get("targetAc")
    if attack_total is None or target_ac is None:
        return None
    pre_precision_total = int(attack_total) - int(superiority_rolls[0])
    return max(0, int(target_ac) - pre_precision_total)


def record_fighter_attack(metrics: dict[str, Any], event: Any, source: str, trip_prone_targets: set[str]) -> None:
    resolved_totals = event.resolved_totals or {}
    raw_rolls = event.raw_rolls or {}
    damage_details = event.damage_details
    weapon_id = damage_details.weapon_id if damage_details else "unknown"
    damage_to_hp = get_event_damage_to_hp(event)
    hit = resolved_totals.get("hit") is True
    maneuver_id = resolved_totals.get("maneuverId")
    precision_used = maneuver_id == "precision_attack" or resolved_totals.get("precisionManeuverId") == "precision_attack"
    target_id = event.target_ids[0] if event.target_ids else None
    advantage_sources = list(raw_rolls.get("advantageSources") or [])
    disadvantage_sources = list(raw_rolls.get("disadvantageSources") or [])

    add_metric(metrics, "fighterAttacks")
    metrics["fighterWeaponAttacks"][weapon_id] += 1
    metrics["fighterAttackSourceCounts"][source] += 1
    metrics["fighterDamageBySource"][source] += damage_to_hp
    metrics["fighterAttackModeCounts"][str(resolved_totals.get("attackMode") or "normal")] += 1
    metrics["fighterAdvantageSourceCounts"].update(advantage_sources)
    metrics["fighterDisadvantageSourceCounts"].update(disadvantage_sources)
    add_metric(metrics, "fighterDamageToHp", damage_to_hp)

    if hit:
        add_metric(metrics, "fighterHits")
    if resolved_totals.get("critical") is True:
        add_metric(metrics, "fighterCrits")

    if source == "action_surge":
        add_metric(metrics, "actionSurgeAttacks")
        add_metric(metrics, "actionSurgeDamageToHp", damage_to_hp)
    if source == "riposte":
        add_metric(metrics, "riposteAttacks")
        add_metric(metrics, "riposteDamageToHp", damage_to_hp)
        if hit:
            add_metric(metrics, "riposteHits")
    if source == "opportunity":
        add_metric(metrics, "opportunityAttacks")
        if hit:
            add_metric(metrics, "opportunityHits")
    if source == "hew":
        add_metric(metrics, "hewAttacks")
        add_metric(metrics, "hewDamageToHp", damage_to_hp)
        if hit:
            add_metric(metrics, "hewHits")

    superiority_rolls = list(raw_rolls.get("superiorityDiceRolls") or [])
    add_metric(metrics, "superiorityDiceSpent", len(superiority_rolls))

    if maneuver_id:
        metrics["maneuverCounts"][str(maneuver_id)] += 1
    if precision_used:
        add_metric(metrics, "precisionUses")
        margin = get_precision_miss_margin(event)
        if margin is not None:
            metrics["precisionMissMargins"].append(margin)
        if hit:
            add_metric(metrics, "precisionConverted")
        else:
            add_metric(metrics, "precisionFailed")
        if maneuver_id == "riposte":
            add_metric(metrics, "precisionOnRiposteUses")

    if maneuver_id == "trip_attack":
        add_metric(metrics, "tripAttackUses")
        if resolved_totals.get("maneuverSaveSuccess") is True:
            add_metric(metrics, "tripSaveSuccesses")
        elif resolved_totals.get("maneuverSaveSuccess") is False:
            add_metric(metrics, "tripSaveFailures")
        if resolved_totals.get("maneuverProneApplied") is True:
            add_metric(metrics, "tripProneApplied")
            if target_id:
                trip_prone_targets.add(str(target_id))

    if target_id in trip_prone_targets and "target_prone" in advantage_sources:
        add_metric(metrics, "tripFollowUpAttacks")

    gwm_damage = int(resolved_totals.get("greatWeaponMasterDamageBonus") or 0)
    if gwm_damage > 0:
        add_metric(metrics, "greatWeaponMasterDamageApplications")
        add_metric(metrics, "greatWeaponMasterDamageTotal", gwm_damage)
    if resolved_totals.get("greatWeaponMasterHewingTrigger") is True:
        add_metric(metrics, "hewTriggers")


def record_fighter_run(metrics: dict[str, Any], result: RunEncounterResult, unit_id: str) -> None:
    final_state = result.final_state
    fighter = final_state.units[unit_id]
    metrics["runs"] += 1
    metrics["wins"][final_state.winner] += 1
    metrics["rounds"].append(final_state.round)
    metrics["endingFighterHp"].append(max(0, fighter.current_hp))
    metrics["endingSuperiorityDice"].append(fighter.resources.superiority_dice)
    metrics["endingActionSurgeUses"].append(fighter.resources.action_surge_uses)
    metrics["endingSecondWindUses"].append(fighter.resources.second_wind_uses)
    if fighter.current_hp <= 0 or fighter.conditions.dead or fighter.conditions.unconscious:
        add_metric(metrics, "fighterDownAtEnd")

    attack_count = get_fighter_attack_count(fighter)
    trip_prone_targets: set[str] = set()

    for frame in result.replay_frames[1:]:
        surge_attacks_remaining = 0
        hewing_next_attack = False
        for event in frame.events:
            resolved_totals = event.resolved_totals or {}
            is_actor = event.actor_id == unit_id

            if is_actor:
                add_metric(metrics, "fighterEvents")

            if is_actor and resolved_totals.get("actionSurgeUsesRemaining") is not None:
                add_metric(metrics, "actionSurgeUses")
                surge_attacks_remaining = attack_count
                continue

            if is_actor and resolved_totals.get("bonusAction") == "great_weapon_master_hewing":
                hewing_next_attack = True
                continue

            if is_actor and resolved_totals.get("reaction") == "riposte":
                add_metric(metrics, "riposteTriggers")
                continue

            if is_actor and event.event_type == "heal" and resolved_totals.get("secondWindUsesRemaining") is not None:
                healing_total = int(resolved_totals.get("healingTotal") or 0)
                add_metric(metrics, "secondWindUses")
                add_metric(metrics, "secondWindTotalHealing", healing_total)
                metrics["secondWindHeals"].append(healing_total)
                continue

            if is_actor and event.event_type == "movement" and resolved_totals.get("tacticalShiftApplied") is True:
                add_metric(metrics, "tacticalShiftUses")
                if event.movement_details and event.movement_details.distance:
                    add_metric(metrics, "tacticalShiftSquares", int(event.movement_details.distance))
                continue

            if not (is_actor and event.event_type == "attack"):
                continue

            if hewing_next_attack:
                source = "hew"
                hewing_next_attack = False
            elif resolved_totals.get("maneuverId") == "riposte":
                source = "riposte"
            elif resolved_totals.get("opportunityAttack") is True:
                source = "opportunity"
            elif surge_attacks_remaining > 0:
                source = "action_surge"
                surge_attacks_remaining -= 1
            else:
                source = "attack_action"

            record_fighter_attack(metrics, event, source, trip_prone_targets)


def record_profile_run(profile: str, metrics: dict[str, Any], result: RunEncounterResult, unit_id: str) -> None:
    if profile == "fighter":
        record_fighter_run(metrics, result, unit_id)
        return
    if profile == "paladin":
        record_paladin_run(metrics, result, unit_id)
        return
    if profile == "rogue":
        record_rogue_run(metrics, result, unit_id)
        return
    if profile == "wizard":
        record_wizard_run(metrics, result, unit_id)
        return
    raise ValueError(f"Unsupported PC tuning profile `{profile}`.")


def get_profile_recording_skip_reason(result: RunEncounterResult, profile: str, unit_id: str) -> str | None:
    unit = result.final_state.units.get(unit_id)
    if not unit:
        return f"Unit `{unit_id}` is not present in final encounter state."
    if unit.class_id != profile:
        return f"Unit `{unit_id}` is `{unit.class_id}`, not `{profile}`."
    return None


def summarize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    runs = int(metrics["runs"])
    ending_slots = list(metrics["endingSpellSlots"])
    ending_level_1_slots = list(metrics["endingSpellSlotsLevel1"])
    ending_level_2_slots = list(metrics["endingSpellSlotsLevel2"])
    ending_level_3_slots = list(metrics["endingSpellSlotsLevel3"])
    ending_lay_on_hands = list(metrics["endingLayOnHands"])
    natures_wrath_targets = list(metrics["naturesWrathTargets"])
    natures_wrath_restrained = list(metrics["naturesWrathRestrained"])
    lay_on_hands_heals = list(metrics["layOnHandsHeals"])
    cure_wounds_heals = list(metrics["cureWoundsHeals"])
    ending_wizard_hp = list(metrics["endingWizardHp"])
    burning_hands_enemy_targets = list(metrics["burningHandsEnemyTargets"])
    burning_hands_ally_targets = list(metrics["burningHandsAllyTargets"])
    scorching_ray_casts = int(metrics["scorchingRayCasts"])
    scorching_ray_attacks = int(metrics["scorchingRayRayAttacks"])
    shatter_casts = int(metrics["shatterCasts"])
    shatter_target_counts = list(metrics["shatterTargetCounts"])
    wizard_attacks = int(metrics["wizardAttacks"])
    wizard_hits = int(metrics["wizardHits"])
    shield_casts = int(metrics["shieldCasts"])
    burning_hands_casts = int(metrics["burningHandsCasts"])
    shocking_grasp_hits = int(metrics["shockingGraspHits"])
    spell_slots_spent = int(metrics["wizardSpellSlotsSpent"])
    ending_rogue_hp = list(metrics["endingRogueHp"])
    rogue_attacks = int(metrics["rogueAttacks"])
    rogue_hits = int(metrics["rogueHits"])
    sneak_attack_applications = int(metrics["sneakAttackApplications"])
    incoming_hits = int(metrics["incomingAttackHits"])
    ending_fighter_hp = list(metrics["endingFighterHp"])
    ending_superiority_dice = list(metrics["endingSuperiorityDice"])
    ending_action_surge = list(metrics["endingActionSurgeUses"])
    ending_second_wind = list(metrics["endingSecondWindUses"])
    fighter_attacks = int(metrics["fighterAttacks"])
    fighter_hits = int(metrics["fighterHits"])
    precision_uses = int(metrics["precisionUses"])
    trip_uses = int(metrics["tripAttackUses"])
    riposte_attacks = int(metrics["riposteAttacks"])
    hew_attacks = int(metrics["hewAttacks"])
    second_wind_heals = list(metrics["secondWindHeals"])

    summary = {
        "runs": runs,
        "wins": dict(metrics["wins"]),
        "playerWinRate": percent(metrics["wins"].get("fighters", 0), runs),
        "enemyWinRate": percent(metrics["wins"].get("goblins", 0), runs),
        "averageRounds": average(metrics["rounds"]),
        "endingSpellSlotsDistribution": distribution(ending_slots),
        "endingSpellSlotsLevel1Distribution": distribution(ending_level_1_slots),
        "endingSpellSlotsLevel2Distribution": distribution(ending_level_2_slots),
        "endingSpellSlotsLevel3Distribution": distribution(ending_level_3_slots),
        "runsWithUnusedSpellSlots": sum(value > 0 for value in ending_slots),
        "runsWithUnusedSpellSlotsRate": percent(sum(value > 0 for value in ending_slots), runs),
        "averageEndingSpellSlots": average(ending_slots),
        "averageEndingSpellSlotsLevel1": average(ending_level_1_slots),
        "averageEndingSpellSlotsLevel2": average(ending_level_2_slots),
        "averageEndingSpellSlotsLevel3": average(ending_level_3_slots),
        "endingLayOnHandsDistribution": distribution(ending_lay_on_hands),
        "runsWithUnusedLayOnHands": sum(value > 0 for value in ending_lay_on_hands),
        "runsWithUnusedLayOnHandsRate": percent(sum(value > 0 for value in ending_lay_on_hands), runs),
        "averageEndingLayOnHands": average(ending_lay_on_hands),
        "paladinDownAtEnd": metrics["paladinDownAtEnd"],
        "paladinDownAtEndRate": percent(metrics["paladinDownAtEnd"], runs),
        "paladinEvents": metrics["paladinEvents"],
        "blessCasts": metrics["blessCasts"],
        "divineSmites": metrics["divineSmites"],
        "sentinelGuardianTriggers": metrics["sentinelGuardianTriggers"],
        "sentinelHaltApplied": metrics["sentinelHaltApplied"],
        "sentinelHaltPerGuardianRate": percent(
            metrics["sentinelHaltApplied"],
            metrics["sentinelGuardianTriggers"],
        ),
        "naturesWrathUses": metrics["naturesWrathUses"],
        "naturesWrathUseRate": percent(metrics["naturesWrathUses"], runs),
        "naturesWrathAverageTargets": average(natures_wrath_targets),
        "naturesWrathAverageRestrained": average(natures_wrath_restrained),
        "naturesWrathRestrainedTargetRate": percent(sum(natures_wrath_restrained), sum(natures_wrath_targets)),
        "naturesWrathTargetDistribution": distribution(natures_wrath_targets),
        "naturesWrathRestrainedDistribution": distribution(natures_wrath_restrained),
        "layOnHandsUses": metrics["layOnHandsUses"],
        "layOnHandsTotalHealing": metrics["layOnHandsTotalHealing"],
        "layOnHandsAverageHeal": average(lay_on_hands_heals),
        "layOnHandsDownedPickups": metrics["layOnHandsDownedPickups"],
        "layOnHandsHealDistribution": distribution(lay_on_hands_heals),
        "cureWoundsUses": metrics["cureWoundsUses"],
        "cureWoundsTotalHealing": metrics["cureWoundsTotalHealing"],
        "cureWoundsAverageHeal": average(cure_wounds_heals),
        "cureWoundsDownedPickups": metrics["cureWoundsDownedPickups"],
        "cureWoundsHealDistribution": distribution(cure_wounds_heals),
    }
    summary.update(
        {
            "endingWizardHpDistribution": distribution(ending_wizard_hp),
            "averageEndingWizardHp": average(ending_wizard_hp),
            "wizardDownAtEnd": metrics["wizardDownAtEnd"],
            "wizardDownAtEndRate": percent(metrics["wizardDownAtEnd"], runs),
            "wizardEvents": metrics["wizardEvents"],
            "wizardTurns": metrics["wizardTurns"],
            "wizardDeathSaves": metrics["wizardDeathSaves"],
            "wizardSkipTurns": metrics["wizardSkipTurns"],
            "wizardActionSkips": metrics["wizardSkipTurns"],
            "wizardIncomingAttackHits": metrics["wizardIncomingAttackHits"],
            "wizardIncomingDamageToHp": metrics["wizardIncomingDamageToHp"],
            "wizardDamagingHitsTaken": metrics["wizardDamagingHitsTaken"],
            "wizardAttacks": wizard_attacks,
            "wizardHits": wizard_hits,
            "wizardHitRate": percent(wizard_hits, wizard_attacks),
            "wizardCrits": metrics["wizardCrits"],
            "wizardDamageToHp": metrics["wizardDamageToHp"],
            "averageWizardDamagePerRun": round(float(metrics["wizardDamageToHp"]) / runs, 2) if runs else 0.0,
            "averageWizardDamagePerAttack": round(float(metrics["wizardDamageToHp"]) / wizard_attacks, 2)
            if wizard_attacks
            else 0.0,
            "wizardSpellCasts": dict(sorted(metrics["wizardSpellCasts"].items())),
            "wizardSpellDamage": dict(sorted(metrics["wizardSpellDamage"].items())),
            "wizardSpellSlotsSpent": metrics["wizardSpellSlotsSpent"],
            "wizardSpellSlotsSpentPerRun": round(float(spell_slots_spent) / runs, 2) if runs else 0.0,
            "wizardSpellSlotsSpentBySpell": dict(sorted(metrics["wizardSpellSlotsSpentBySpell"].items())),
            "wizardSpellSlotsSpentByLevel": dict(sorted(metrics["wizardSpellSlotsSpentByLevel"].items())),
            "wizardCantripDamage": metrics["wizardCantripDamage"],
            "wizardSlottedSpellDamage": metrics["wizardSlottedSpellDamage"],
            "wizardDamagePerSlotSpent": round(float(metrics["wizardSlottedSpellDamage"]) / spell_slots_spent, 2)
            if spell_slots_spent
            else 0.0,
            "wizardAttackModeCounts": dict(sorted(metrics["wizardAttackModeCounts"].items())),
            "wizardAdvantageSourceCounts": dict(sorted(metrics["wizardAdvantageSourceCounts"].items())),
            "wizardDisadvantageSourceCounts": dict(sorted(metrics["wizardDisadvantageSourceCounts"].items())),
            "fireBoltCasts": metrics["fireBoltCasts"],
            "fireBoltHits": metrics["fireBoltHits"],
            "fireBoltHitRate": percent(metrics["fireBoltHits"], metrics["fireBoltCasts"]),
            "fireBoltDamage": metrics["fireBoltDamage"],
            "shockingGraspCasts": metrics["shockingGraspCasts"],
            "shockingGraspHits": shocking_grasp_hits,
            "shockingGraspHitRate": percent(shocking_grasp_hits, metrics["shockingGraspCasts"]),
            "shockingGraspDamage": metrics["shockingGraspDamage"],
            "shockingGraspNoReactionApplications": metrics["shockingGraspNoReactionApplications"],
            "shockingGraspRetreats": metrics["shockingGraspRetreats"],
            "shockingGraspRetreatRate": percent(metrics["shockingGraspRetreats"], shocking_grasp_hits),
            "magicMissileCasts": metrics["magicMissileCasts"],
            "magicMissileDamage": metrics["magicMissileDamage"],
            "magicMissileAverageDamage": round(
                float(metrics["magicMissileDamage"]) / metrics["magicMissileCasts"],
                2,
            )
            if metrics["magicMissileCasts"]
            else 0.0,
            "magicMissileKillSecures": metrics["magicMissileKillSecures"],
            "magicMissileKillSecureRate": percent(metrics["magicMissileKillSecures"], metrics["magicMissileCasts"]),
            "magicMissileOverkillDamage": metrics["magicMissileOverkillDamage"],
            "magicMissileBlockedByShield": metrics["magicMissileBlockedByShield"],
            "magicMissileCastsByLevel": dict(sorted(metrics["magicMissileCastsByLevel"].items())),
            "magicMissileProjectiles": metrics["magicMissileProjectiles"],
            "magicMissileProjectilesPerCast": round(
                float(metrics["magicMissileProjectiles"]) / metrics["magicMissileCasts"],
                2,
            )
            if metrics["magicMissileCasts"]
            else 0.0,
            "magicMissileSplitCasts": metrics["magicMissileSplitCasts"],
            "magicMissileSplitCastRate": percent(metrics["magicMissileSplitCasts"], metrics["magicMissileCasts"]),
            "burningHandsCasts": burning_hands_casts,
            "burningHandsTargetDamageEvents": metrics["burningHandsTargetDamageEvents"],
            "burningHandsDamage": metrics["burningHandsDamage"],
            "burningHandsAverageDamagePerCast": round(
                float(metrics["burningHandsDamage"]) / burning_hands_casts,
                2,
            )
            if burning_hands_casts
            else 0.0,
            "burningHandsAverageEnemyTargets": average(burning_hands_enemy_targets),
            "burningHandsAverageAllyTargets": average(burning_hands_ally_targets),
            "burningHandsEnemyTargetDistribution": distribution(burning_hands_enemy_targets),
            "burningHandsAllyTargetDistribution": distribution(burning_hands_ally_targets),
            "burningHandsLowValueCasts": metrics["burningHandsLowValueCasts"],
            "burningHandsLowValueCastRate": percent(metrics["burningHandsLowValueCasts"], burning_hands_casts),
            "burningHandsFriendlyFireCasts": metrics["burningHandsFriendlyFireCasts"],
            "burningHandsFriendlyFireRate": percent(metrics["burningHandsFriendlyFireCasts"], burning_hands_casts),
            "burningHandsSaveSuccesses": metrics["burningHandsSaveSuccesses"],
            "burningHandsSaveFailures": metrics["burningHandsSaveFailures"],
            "burningHandsFailedSaveRate": percent(
                metrics["burningHandsSaveFailures"],
                metrics["burningHandsSaveSuccesses"] + metrics["burningHandsSaveFailures"],
            ),
            "scorchingRayCasts": scorching_ray_casts,
            "scorchingRayRayAttacks": scorching_ray_attacks,
            "scorchingRayHits": metrics["scorchingRayHits"],
            "scorchingRayHitRate": percent(metrics["scorchingRayHits"], scorching_ray_attacks),
            "scorchingRayDamage": metrics["scorchingRayDamage"],
            "scorchingRayAverageDamagePerCast": round(
                float(metrics["scorchingRayDamage"]) / scorching_ray_casts,
                2,
            )
            if scorching_ray_casts
            else 0.0,
            "scorchingRayRayAttacksPerCast": round(float(scorching_ray_attacks) / scorching_ray_casts, 2)
            if scorching_ray_casts
            else 0.0,
            "scorchingRayKillSecures": metrics["scorchingRayKillSecures"],
            "scorchingRayKillSecureRate": percent(metrics["scorchingRayKillSecures"], scorching_ray_attacks),
            "scorchingRaySplitCasts": metrics["scorchingRaySplitCasts"],
            "scorchingRaySplitCastRate": percent(metrics["scorchingRaySplitCasts"], scorching_ray_casts),
            "scorchingRayUniqueTargetDistribution": distribution(list(metrics["scorchingRayUniqueTargets"])),
            "shatterCasts": shatter_casts,
            "shatterTargetDamageEvents": metrics["shatterTargetDamageEvents"],
            "shatterDamage": metrics["shatterDamage"],
            "shatterAverageDamagePerCast": round(float(metrics["shatterDamage"]) / shatter_casts, 2)
            if shatter_casts
            else 0.0,
            "shatterAverageTargets": average(shatter_target_counts),
            "shatterTargetDistribution": distribution(shatter_target_counts),
            "shatterSaveSuccesses": metrics["shatterSaveSuccesses"],
            "shatterSaveFailures": metrics["shatterSaveFailures"],
            "shatterFailedSaveRate": percent(
                metrics["shatterSaveFailures"],
                metrics["shatterSaveSuccesses"] + metrics["shatterSaveFailures"],
            ),
            "shieldCasts": shield_casts,
            "shieldPreventedHits": metrics["shieldPreventedHits"],
            "shieldFailedToStopHits": metrics["shieldFailedToStopHits"],
            "shieldPreventedHitRate": percent(metrics["shieldPreventedHits"], shield_casts),
            "shieldMagicMissileBlocks": metrics["shieldMagicMissileBlocks"],
            "mageArmorCasts": metrics["mageArmorCasts"],
            "mageArmorAcChanged": metrics["mageArmorAcChanged"],
            "daggerFallbackAttacks": metrics["daggerFallbackAttacks"],
            "daggerFallbackHits": metrics["daggerFallbackHits"],
            "daggerFallbackHitRate": percent(metrics["daggerFallbackHits"], metrics["daggerFallbackAttacks"]),
            "daggerFallbackDamage": metrics["daggerFallbackDamage"],
            "wizardMovementEvents": metrics["wizardMovementEvents"],
            "wizardMovementSquares": metrics["wizardMovementSquares"],
            "averageWizardMovementSquaresPerRun": round(float(metrics["wizardMovementSquares"]) / runs, 2)
            if runs
            else 0.0,
        }
    )
    summary.update(
        {
            "endingRogueHpDistribution": distribution(ending_rogue_hp),
            "averageEndingRogueHp": average(ending_rogue_hp),
            "rogueDownAtEnd": metrics["rogueDownAtEnd"],
            "rogueDownAtEndRate": percent(metrics["rogueDownAtEnd"], runs),
            "rogueEvents": metrics["rogueEvents"],
            "rogueAttacks": rogue_attacks,
            "rogueHits": rogue_hits,
            "rogueHitRate": percent(rogue_hits, rogue_attacks),
            "rogueCrits": metrics["rogueCrits"],
            "rogueDamageToHp": metrics["rogueDamageToHp"],
            "averageRogueDamagePerRun": round(float(metrics["rogueDamageToHp"]) / runs, 2) if runs else 0.0,
            "averageRogueDamagePerAttack": round(float(metrics["rogueDamageToHp"]) / rogue_attacks, 2)
            if rogue_attacks
            else 0.0,
            "rogueWeaponAttacks": dict(sorted(metrics["rogueWeaponAttacks"].items())),
            "shortbowAttackRate": percent(metrics["rogueWeaponAttacks"].get("shortbow", 0), rogue_attacks),
            "shortswordAttackRate": percent(metrics["rogueWeaponAttacks"].get("shortsword", 0), rogue_attacks),
            "rogueAttackModeCounts": dict(sorted(metrics["rogueAttackModeCounts"].items())),
            "rogueAdvantageAttacks": metrics["rogueAdvantageAttacks"],
            "rogueAdvantageAttackRate": percent(metrics["rogueAdvantageAttacks"], rogue_attacks),
            "rogueDisadvantageAttacks": metrics["rogueDisadvantageAttacks"],
            "rogueDisadvantageAttackRate": percent(metrics["rogueDisadvantageAttacks"], rogue_attacks),
            "rogueAdvantageSourceCounts": dict(sorted(metrics["rogueAdvantageSourceCounts"].items())),
            "rogueDisadvantageSourceCounts": dict(sorted(metrics["rogueDisadvantageSourceCounts"].items())),
            "sneakAttackApplications": sneak_attack_applications,
            "sneakAttackHitRate": percent(sneak_attack_applications, rogue_hits),
            "sneakAttackAttackRate": percent(sneak_attack_applications, rogue_attacks),
            "sneakAttackDamage": metrics["sneakAttackDamage"],
            "sneakAttackDiceRolled": metrics["sneakAttackDiceRolled"],
            "hitsWithoutSneakAttack": metrics["hitsWithoutSneakAttack"],
            "hitsWithoutSneakAttackRate": percent(metrics["hitsWithoutSneakAttack"], rogue_hits),
            "assassinateAdvantageAttacks": metrics["assassinateAdvantageAttacks"],
            "assassinateDamageApplications": metrics["assassinateDamageApplications"],
            "assassinateDamageTotal": metrics["assassinateDamageTotal"],
            "steadyAimUses": metrics["steadyAimUses"],
            "attacksWithSteadyAim": metrics["attacksWithSteadyAim"],
            "steadyAimAttackFollowThroughRate": percent(metrics["attacksWithSteadyAim"], metrics["steadyAimUses"]),
            "hideAttempts": metrics["hideAttempts"],
            "hideSuccesses": metrics["hideSuccesses"],
            "hideSuccessRate": percent(metrics["hideSuccesses"], metrics["hideAttempts"]),
            "attacksFromHidden": metrics["attacksFromHidden"],
            "hiddenAttackPerHideSuccessRate": percent(metrics["attacksFromHidden"], metrics["hideSuccesses"]),
            "sharpshooterApplications": metrics["sharpshooterApplications"],
            "sharpshooterApplicationRate": percent(metrics["sharpshooterApplications"], rogue_attacks),
            "sharpshooterCoverIgnoredEvents": metrics["sharpshooterCoverIgnoredEvents"],
            "sharpshooterCoverAcIgnoredTotal": metrics["sharpshooterCoverAcIgnoredTotal"],
            "sharpshooterIgnoredDisadvantageSourceCounts": dict(
                sorted(metrics["sharpshooterIgnoredDisadvantageSourceCounts"].items())
            ),
            "cunningStrikeUses": metrics["cunningStrikeUses"],
            "cunningStrikeCounts": dict(sorted(metrics["cunningStrikeCounts"].items())),
            "cunningStrikeSneakDiceSpent": metrics["cunningStrikeSneakDiceSpent"],
            "uncannyDodgeUses": metrics["uncannyDodgeUses"],
            "uncannyDodgeUseRatePerIncomingHit": percent(metrics["uncannyDodgeUses"], incoming_hits),
            "uncannyDodgeDamagePrevented": metrics["uncannyDodgeDamagePrevented"],
            "averageUncannyDodgeDamagePrevented": round(
                float(metrics["uncannyDodgeDamagePrevented"]) / metrics["uncannyDodgeUses"],
                2,
            )
            if metrics["uncannyDodgeUses"]
            else 0.0,
            "incomingAttackHits": incoming_hits,
            "incomingDamageToHp": metrics["incomingDamageToHp"],
            "damagingHitsTakenWithoutUncannyDodge": metrics["damagingHitsTakenWithoutUncannyDodge"],
            "movementEvents": metrics["movementEvents"],
            "movementSquares": metrics["movementSquares"],
            "averageMovementSquaresPerRun": round(float(metrics["movementSquares"]) / runs, 2) if runs else 0.0,
            "disengageMovementEvents": metrics["disengageMovementEvents"],
            "endingFighterHpDistribution": distribution(ending_fighter_hp),
            "averageEndingFighterHp": average(ending_fighter_hp),
            "fighterDownAtEnd": metrics["fighterDownAtEnd"],
            "fighterDownAtEndRate": percent(metrics["fighterDownAtEnd"], runs),
            "endingSuperiorityDiceDistribution": distribution(ending_superiority_dice),
            "averageEndingSuperiorityDice": average(ending_superiority_dice),
            "runsWithUnusedSuperiorityDice": sum(value > 0 for value in ending_superiority_dice),
            "runsWithUnusedSuperiorityDiceRate": percent(sum(value > 0 for value in ending_superiority_dice), runs),
            "averageEndingActionSurgeUses": average(ending_action_surge),
            "runsWithUnusedActionSurge": sum(value > 0 for value in ending_action_surge),
            "averageEndingSecondWindUses": average(ending_second_wind),
            "runsWithUnusedSecondWind": sum(value > 0 for value in ending_second_wind),
            "fighterEvents": metrics["fighterEvents"],
            "fighterAttacks": fighter_attacks,
            "fighterAttacksPerRun": round(float(fighter_attacks) / runs, 2) if runs else 0.0,
            "fighterHits": fighter_hits,
            "fighterHitRate": percent(fighter_hits, fighter_attacks),
            "fighterCrits": metrics["fighterCrits"],
            "fighterDamageToHp": metrics["fighterDamageToHp"],
            "averageFighterDamagePerRun": round(float(metrics["fighterDamageToHp"]) / runs, 2) if runs else 0.0,
            "averageFighterDamagePerAttack": round(float(metrics["fighterDamageToHp"]) / fighter_attacks, 2)
            if fighter_attacks
            else 0.0,
            "fighterWeaponAttacks": dict(sorted(metrics["fighterWeaponAttacks"].items())),
            "greatswordAttackRate": percent(metrics["fighterWeaponAttacks"].get("greatsword", 0), fighter_attacks),
            "flailAttackRate": percent(metrics["fighterWeaponAttacks"].get("flail", 0), fighter_attacks),
            "javelinAttackRate": percent(metrics["fighterWeaponAttacks"].get("javelin", 0), fighter_attacks),
            "fighterAttackSourceCounts": dict(sorted(metrics["fighterAttackSourceCounts"].items())),
            "fighterDamageBySource": dict(sorted(metrics["fighterDamageBySource"].items())),
            "fighterAttackModeCounts": dict(sorted(metrics["fighterAttackModeCounts"].items())),
            "fighterAdvantageSourceCounts": dict(sorted(metrics["fighterAdvantageSourceCounts"].items())),
            "fighterDisadvantageSourceCounts": dict(sorted(metrics["fighterDisadvantageSourceCounts"].items())),
            "actionSurgeUses": metrics["actionSurgeUses"],
            "actionSurgeAttacks": metrics["actionSurgeAttacks"],
            "actionSurgeDamageToHp": metrics["actionSurgeDamageToHp"],
            "actionSurgeDamagePerRun": round(float(metrics["actionSurgeDamageToHp"]) / runs, 2) if runs else 0.0,
            "superiorityDiceSpent": metrics["superiorityDiceSpent"],
            "superiorityDiceSpentPerRun": round(float(metrics["superiorityDiceSpent"]) / runs, 2) if runs else 0.0,
            "maneuverCounts": dict(sorted(metrics["maneuverCounts"].items())),
            "precisionUses": precision_uses,
            "precisionConverted": metrics["precisionConverted"],
            "precisionFailed": metrics["precisionFailed"],
            "precisionConversionRate": percent(metrics["precisionConverted"], precision_uses),
            "precisionMissMarginDistribution": distribution(list(metrics["precisionMissMargins"])),
            "averagePrecisionMissMargin": average(list(metrics["precisionMissMargins"])),
            "precisionOnRiposteUses": metrics["precisionOnRiposteUses"],
            "tripAttackUses": trip_uses,
            "tripSaveSuccesses": metrics["tripSaveSuccesses"],
            "tripSaveFailures": metrics["tripSaveFailures"],
            "tripProneApplied": metrics["tripProneApplied"],
            "tripProneRate": percent(metrics["tripProneApplied"], trip_uses),
            "tripFollowUpAttacks": metrics["tripFollowUpAttacks"],
            "riposteTriggers": metrics["riposteTriggers"],
            "riposteAttacks": riposte_attacks,
            "riposteHits": metrics["riposteHits"],
            "riposteHitRate": percent(metrics["riposteHits"], riposte_attacks),
            "riposteDamageToHp": metrics["riposteDamageToHp"],
            "opportunityAttacks": metrics["opportunityAttacks"],
            "opportunityHits": metrics["opportunityHits"],
            "opportunityHitRate": percent(metrics["opportunityHits"], metrics["opportunityAttacks"]),
            "greatWeaponMasterDamageApplications": metrics["greatWeaponMasterDamageApplications"],
            "greatWeaponMasterDamageTotal": metrics["greatWeaponMasterDamageTotal"],
            "hewTriggers": metrics["hewTriggers"],
            "hewAttacks": hew_attacks,
            "hewHits": metrics["hewHits"],
            "hewHitRate": percent(metrics["hewHits"], hew_attacks),
            "hewDamageToHp": metrics["hewDamageToHp"],
            "secondWindUses": metrics["secondWindUses"],
            "secondWindTotalHealing": metrics["secondWindTotalHealing"],
            "secondWindAverageHeal": average(second_wind_heals),
            "tacticalShiftUses": metrics["tacticalShiftUses"],
            "tacticalShiftSquares": metrics["tacticalShiftSquares"],
            "averageTacticalShiftSquares": round(float(metrics["tacticalShiftSquares"]) / metrics["tacticalShiftUses"], 2)
            if metrics["tacticalShiftUses"]
            else 0.0,
        }
    )
    return summary


def run_paladin_sample(
    *,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overall_metrics = new_metrics("paladin")
    scenario_rows: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        scenario_metrics = new_metrics("paladin")
        print(f"[{scenario_id}] {runs_per_scenario} event-level replay(s)")
        for run_index in range(runs_per_scenario):
            seed = f"pc-tuning-{unit_id}-{scenario_id}-{run_index:03d}"
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=monster_behavior,
                )
            )
            unit = result.final_state.units.get(unit_id)
            if not unit:
                raise ValueError(f"Unit `{unit_id}` is not present in final encounter state.")
            if unit.class_id != "paladin":
                raise ValueError(f"Paladin tuning profile requires a paladin unit; `{unit_id}` is `{unit.class_id}`.")

            record_paladin_run(overall_metrics, result, unit_id)
            record_paladin_run(scenario_metrics, result, unit_id)

        scenario_summary = summarize_metrics(scenario_metrics)
        scenario_summary["scenarioId"] = scenario_id
        scenario_rows.append(scenario_summary)

    return summarize_metrics(overall_metrics), scenario_rows


def run_rogue_sample(
    *,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overall_metrics = new_metrics("rogue")
    scenario_rows: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        scenario_metrics = new_metrics("rogue")
        print(f"[{scenario_id}] {runs_per_scenario} event-level replay(s)")
        for run_index in range(runs_per_scenario):
            seed = f"pc-tuning-{unit_id}-{scenario_id}-{run_index:03d}"
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=monster_behavior,
                )
            )
            unit = result.final_state.units.get(unit_id)
            if not unit:
                raise ValueError(f"Unit `{unit_id}` is not present in final encounter state.")
            if unit.class_id != "rogue":
                raise ValueError(f"Rogue tuning profile requires a rogue unit; `{unit_id}` is `{unit.class_id}`.")

            record_rogue_run(overall_metrics, result, unit_id)
            record_rogue_run(scenario_metrics, result, unit_id)

        scenario_summary = summarize_metrics(scenario_metrics)
        scenario_summary["scenarioId"] = scenario_id
        scenario_rows.append(scenario_summary)

    return summarize_metrics(overall_metrics), scenario_rows


def run_fighter_sample(
    *,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overall_metrics = new_metrics("fighter")
    scenario_rows: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        scenario_metrics = new_metrics("fighter")
        print(f"[{scenario_id}] {runs_per_scenario} event-level replay(s), player={player_behavior}")
        for run_index in range(runs_per_scenario):
            seed = f"pc-tuning-{unit_id}-{player_behavior}-{scenario_id}-{run_index:03d}"
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=monster_behavior,
                )
            )
            unit = result.final_state.units.get(unit_id)
            if not unit:
                raise ValueError(f"Unit `{unit_id}` is not present in final encounter state.")
            if unit.class_id != "fighter":
                raise ValueError(f"Fighter tuning profile requires a fighter unit; `{unit_id}` is `{unit.class_id}`.")

            record_fighter_run(overall_metrics, result, unit_id)
            record_fighter_run(scenario_metrics, result, unit_id)

        scenario_summary = summarize_metrics(scenario_metrics)
        scenario_summary["scenarioId"] = scenario_id
        scenario_rows.append(scenario_summary)

    return summarize_metrics(overall_metrics), scenario_rows


def run_wizard_sample(
    *,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    overall_metrics = new_metrics("wizard")
    scenario_rows: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        scenario_metrics = new_metrics("wizard")
        print(f"[{scenario_id}] {runs_per_scenario} event-level replay(s)")
        for run_index in range(runs_per_scenario):
            seed = f"pc-tuning-{unit_id}-{scenario_id}-{run_index:03d}"
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=monster_behavior,
                )
            )
            unit = result.final_state.units.get(unit_id)
            if not unit:
                raise ValueError(f"Unit `{unit_id}` is not present in final encounter state.")
            if unit.class_id != "wizard":
                raise ValueError(f"Wizard tuning profile requires a wizard unit; `{unit_id}` is `{unit.class_id}`.")

            record_wizard_run(overall_metrics, result, unit_id)
            record_wizard_run(scenario_metrics, result, unit_id)

        scenario_summary = summarize_metrics(scenario_metrics)
        scenario_summary["scenarioId"] = scenario_id
        scenario_rows.append(scenario_summary)

    return summarize_metrics(overall_metrics), scenario_rows


def run_profile_sample(
    *,
    profile: str,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if profile == "paladin":
        return run_paladin_sample(
            unit_id=unit_id,
            player_preset_id=player_preset_id,
            scenario_ids=scenario_ids,
            runs_per_scenario=runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=monster_behavior,
        )
    if profile == "rogue":
        return run_rogue_sample(
            unit_id=unit_id,
            player_preset_id=player_preset_id,
            scenario_ids=scenario_ids,
            runs_per_scenario=runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=monster_behavior,
        )
    if profile == "fighter":
        return run_fighter_sample(
            unit_id=unit_id,
            player_preset_id=player_preset_id,
            scenario_ids=scenario_ids,
            runs_per_scenario=runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=monster_behavior,
        )
    if profile == "wizard":
        return run_wizard_sample(
            unit_id=unit_id,
            player_preset_id=player_preset_id,
            scenario_ids=scenario_ids,
            runs_per_scenario=runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=monster_behavior,
        )
    raise ValueError(f"Unsupported PC tuning profile `{profile}`.")


def build_party_breakdown_payload(
    *,
    profile_unit_ids: dict[str, str],
    overall_metrics_by_profile: dict[str, dict[str, Any]],
    scenario_rows_by_profile: dict[str, list[dict[str, Any]]],
    missing_reasons: dict[str, str],
) -> dict[str, dict[str, Any]]:
    party_breakdown: dict[str, dict[str, Any]] = {}
    for profile in PARTY_PROFILE_ORDER:
        missing_reason = missing_reasons.get(profile)
        party_breakdown[profile] = {
            "unitId": profile_unit_ids[profile],
            "missing": bool(missing_reason),
            "reason": missing_reason,
            "overall": summarize_metrics(overall_metrics_by_profile[profile]),
            "scenarios": scenario_rows_by_profile[profile],
        }
    return party_breakdown


def run_party_profile_sample(
    *,
    selected_profile: str,
    selected_unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    profile_unit_ids = dict(PARTY_PROFILE_UNIT_IDS)
    profile_unit_ids[selected_profile] = selected_unit_id
    overall_metrics_by_profile = {profile: new_metrics(profile) for profile in PARTY_PROFILE_ORDER}
    scenario_rows_by_profile: dict[str, list[dict[str, Any]]] = {profile: [] for profile in PARTY_PROFILE_ORDER}
    missing_reasons: dict[str, str] = {}

    for scenario_id in scenario_ids:
        scenario_metrics_by_profile = {profile: new_metrics(profile) for profile in PARTY_PROFILE_ORDER}
        print(f"[{scenario_id}] {runs_per_scenario} event-level replay(s), player={player_behavior}")
        for run_index in range(runs_per_scenario):
            seed = f"pc-tuning-party-{player_behavior}-{scenario_id}-{run_index:03d}"
            result = run_encounter(
                EncounterConfig(
                    seed=seed,
                    enemy_preset_id=scenario_id,
                    player_preset_id=player_preset_id,
                    player_behavior=player_behavior,
                    monster_behavior=monster_behavior,
                )
            )

            for profile in PARTY_PROFILE_ORDER:
                unit_id = profile_unit_ids[profile]
                skip_reason = get_profile_recording_skip_reason(result, profile, unit_id)
                if skip_reason:
                    missing_reasons.setdefault(profile, skip_reason)
                    continue
                record_profile_run(profile, overall_metrics_by_profile[profile], result, unit_id)
                record_profile_run(profile, scenario_metrics_by_profile[profile], result, unit_id)

        for profile in PARTY_PROFILE_ORDER:
            scenario_summary = summarize_metrics(scenario_metrics_by_profile[profile])
            scenario_summary["scenarioId"] = scenario_id
            if profile in missing_reasons:
                scenario_summary["missing"] = True
                scenario_summary["reason"] = missing_reasons[profile]
            scenario_rows_by_profile[profile].append(scenario_summary)

    party_breakdown = build_party_breakdown_payload(
        profile_unit_ids=profile_unit_ids,
        overall_metrics_by_profile=overall_metrics_by_profile,
        scenario_rows_by_profile=scenario_rows_by_profile,
        missing_reasons=missing_reasons,
    )
    selected_breakdown = party_breakdown[selected_profile]
    return selected_breakdown["overall"], selected_breakdown["scenarios"], party_breakdown


def delta(left: dict[str, Any], right: dict[str, Any], key: str) -> float:
    return round(float(left.get(key, 0.0)) - float(right.get(key, 0.0)), 2)


def build_fighter_behavior_delta(smart: dict[str, Any], dumb: dict[str, Any]) -> dict[str, float]:
    return {
        "playerWinRate": delta(smart, dumb, "playerWinRate"),
        "averageFighterDamagePerRun": delta(smart, dumb, "averageFighterDamagePerRun"),
        "fighterAttacksPerRun": delta(smart, dumb, "fighterAttacksPerRun"),
        "superiorityDiceSpentPerRun": delta(smart, dumb, "superiorityDiceSpentPerRun"),
        "precisionConversionRate": delta(smart, dumb, "precisionConversionRate"),
        "tripProneRate": delta(smart, dumb, "tripProneRate"),
        "actionSurgeDamagePerRun": delta(smart, dumb, "actionSurgeDamagePerRun"),
        "averageEndingSuperiorityDice": delta(smart, dumb, "averageEndingSuperiorityDice"),
        "averageEndingActionSurgeUses": delta(smart, dumb, "averageEndingActionSurgeUses"),
        "averageEndingSecondWindUses": delta(smart, dumb, "averageEndingSecondWindUses"),
    }


def run_fighter_behavior_comparison(
    *,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    monster_behavior: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    behavior_summaries: dict[str, dict[str, Any]] = {}
    for player_behavior in ("smart", "dumb"):
        overall, scenarios, party_breakdown = run_party_profile_sample(
            selected_profile="fighter",
            selected_unit_id=unit_id,
            player_preset_id=player_preset_id,
            scenario_ids=scenario_ids,
            runs_per_scenario=runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=monster_behavior,
        )
        behavior_summaries[player_behavior] = {
            "overall": overall,
            "scenarios": scenarios,
            "partyBreakdown": party_breakdown,
        }

    return behavior_summaries, build_fighter_behavior_delta(
        behavior_summaries["smart"]["overall"],
        behavior_summaries["dumb"]["overall"],
    )


def build_report_payload(
    *,
    profile: str,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    player_behavior: str,
    monster_behavior: str,
    elapsed_seconds: float,
    overall: dict[str, Any],
    scenarios: list[dict[str, Any]],
    party_breakdown: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "unitId": unit_id,
        "playerPresetId": player_preset_id,
        "scenarioIds": list(scenario_ids),
        "runsPerScenario": runs_per_scenario,
        "totalRuns": runs_per_scenario * len(scenario_ids),
        "playerBehavior": player_behavior,
        "monsterBehavior": monster_behavior,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "generatedContext": collect_git_context(REPO_ROOT),
        "overall": overall,
        "scenarios": scenarios,
        "partyBreakdown": party_breakdown or {},
    }


def build_behavior_comparison_payload(
    *,
    profile: str,
    unit_id: str,
    player_preset_id: str,
    scenario_ids: tuple[str, ...],
    runs_per_scenario: int,
    monster_behavior: str,
    elapsed_seconds: float,
    behavior_summaries: dict[str, dict[str, Any]],
    behavior_delta: dict[str, float],
) -> dict[str, Any]:
    return {
        "profile": profile,
        "unitId": unit_id,
        "playerPresetId": player_preset_id,
        "scenarioIds": list(scenario_ids),
        "runsPerScenario": runs_per_scenario,
        "totalRuns": runs_per_scenario * len(scenario_ids) * len(behavior_summaries),
        "playerBehavior": "both",
        "monsterBehavior": monster_behavior,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "generatedContext": collect_git_context(REPO_ROOT),
        "behaviorSummaries": behavior_summaries,
        "behaviorDelta": behavior_delta,
    }


def format_rogue_console_summary(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        (
            f"- overall: players {overall['playerWinRate']}%, enemies {overall['enemyWinRate']}%, "
            f"avg rounds {overall['averageRounds']}"
        ),
        (
            f"- attacks: {overall['rogueAttacks']} attack(s), hit {overall['rogueHitRate']}%, "
            f"advantage {overall['rogueAdvantageAttackRate']}%, shortbow {overall['shortbowAttackRate']}%, "
            f"avg damage/run {overall['averageRogueDamagePerRun']}"
        ),
        (
            f"- sneak attack: {overall['sneakAttackApplications']} application(s), "
            f"{overall['sneakAttackHitRate']}% of hits, {overall['sneakAttackDamage']} damage, "
            f"{overall['hitsWithoutSneakAttack']} hit(s) without Sneak Attack"
        ),
        (
            f"- advantage tools: Steady Aim {overall['steadyAimUses']} use(s), "
            f"Hide {overall['hideSuccesses']}/{overall['hideAttempts']} success(es), "
            f"hidden attacks {overall['attacksFromHidden']}, Assassinate advantage {overall['assassinateAdvantageAttacks']}"
        ),
        (
            f"- sharpshooter/defense: Sharpshooter {overall['sharpshooterApplications']} application(s), "
            f"ignored cover {overall['sharpshooterCoverIgnoredEvents']} time(s), "
            f"Uncanny Dodge {overall['uncannyDodgeUses']} use(s), "
            f"{overall['uncannyDodgeDamagePrevented']} damage prevented"
        ),
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"- {row['scenarioId']}: players {row['playerWinRate']}%, "
            f"attacks {row['rogueAttacks']}, Sneak {row['sneakAttackApplications']}, "
            f"Steady {row['steadyAimUses']}, Hide {row['hideSuccesses']}/{row['hideAttempts']}, "
            f"Uncanny {row['uncannyDodgeUses']}"
        )
    return "\n".join(lines)


def format_wizard_console_summary(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        (
            f"- overall: players {overall['playerWinRate']}%, enemies {overall['enemyWinRate']}%, "
            f"avg rounds {overall['averageRounds']}, Wizard down {overall['wizardDownAtEndRate']}%"
        ),
        (
            f"- damage: {overall['wizardDamageToHp']} HP total, "
            f"avg/run {overall['averageWizardDamagePerRun']}, "
            f"cantrip {overall['wizardCantripDamage']}, slotted {overall['wizardSlottedSpellDamage']}, "
            f"damage/slot {overall['wizardDamagePerSlotSpent']}"
        ),
        (
            f"- spells: Fire Bolt {overall['fireBoltHits']}/{overall['fireBoltCasts']} hit(s), "
            f"Magic Missile {overall['magicMissileCasts']} cast(s), "
            f"Scorching Ray {overall['scorchingRayCasts']} cast(s), "
            f"Shatter {overall['shatterCasts']} cast(s), "
            f"Burning Hands {overall['burningHandsCasts']} cast(s), "
            f"Shocking Grasp {overall['shockingGraspCasts']} cast(s), "
            f"Shield {overall['shieldCasts']} cast(s)"
        ),
        (
            f"- quality: unused slots {overall['runsWithUnusedSpellSlots']}/{overall['runs']}, "
            f"Magic Missile kills {overall['magicMissileKillSecures']} "
            f"(levels {overall['magicMissileCastsByLevel']}), "
            f"Scorching splits {overall['scorchingRaySplitCasts']}/{overall['scorchingRayCasts']}, "
            f"Shatter avg targets {overall['shatterAverageTargets']}, "
            f"Burning Hands avg enemies {overall['burningHandsAverageEnemyTargets']}, "
            f"friendly-fire casts {overall['burningHandsFriendlyFireCasts']}, "
            f"Shield prevented {overall['shieldPreventedHits']} hit(s), "
            f"failed {overall['shieldFailedToStopHits']}"
        ),
        (
            f"- fallback/survival: dagger {overall['daggerFallbackAttacks']} attack(s), "
            f"incoming hits {overall['wizardIncomingAttackHits']}, "
            f"incoming damage {overall['wizardIncomingDamageToHp']}, "
            f"avg ending HP {overall['averageEndingWizardHp']}"
        ),
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"- {row['scenarioId']}: players {row['playerWinRate']}%, "
            f"damage/run {row['averageWizardDamagePerRun']}, "
            f"slots spent {row['wizardSpellSlotsSpent']}, "
            f"Shield {row['shieldCasts']}, "
            f"Scorching {row['scorchingRayCasts']} ({row['scorchingRaySplitCasts']} split), "
            f"Shatter {row['shatterCasts']} (avg targets {row['shatterAverageTargets']}), "
            f"Burning Hands {row['burningHandsCasts']} "
            f"(avg enemies {row['burningHandsAverageEnemyTargets']}, allies {row['burningHandsAverageAllyTargets']}), "
            f"down {row['wizardDownAtEndRate']}%"
        )
    return "\n".join(lines)


def format_fighter_behavior_line(label: str, overall: dict[str, Any]) -> str:
    return (
        f"- {label}: players {overall['playerWinRate']}%, "
        f"damage/run {overall['averageFighterDamagePerRun']}, "
        f"attacks/run {overall['fighterAttacksPerRun']}, "
        f"hit {overall['fighterHitRate']}%, "
        f"Precision {overall['precisionConverted']}/{overall['precisionUses']} "
        f"({overall['precisionConversionRate']}%), "
        f"Trip prone {overall['tripProneApplied']}/{overall['tripAttackUses']}, "
        f"ending dice {overall['averageEndingSuperiorityDice']}"
    )


def format_fighter_console_summary(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        (
            f"- overall: players {overall['playerWinRate']}%, enemies {overall['enemyWinRate']}%, "
            f"avg rounds {overall['averageRounds']}"
        ),
        (
            f"- attacks: {overall['fighterAttacks']} attack(s), hit {overall['fighterHitRate']}%, "
            f"greatsword {overall['greatswordAttackRate']}%, avg damage/run {overall['averageFighterDamagePerRun']}"
        ),
        (
            f"- action economy: Action Surge {overall['actionSurgeUses']} use(s), "
            f"surge attacks {overall['actionSurgeAttacks']}, surge damage/run {overall['actionSurgeDamagePerRun']}, "
            f"Hew {overall['hewAttacks']} attack(s), Riposte {overall['riposteAttacks']} attack(s), "
            f"OA {overall['opportunityAttacks']}"
        ),
        (
            f"- maneuvers: dice spent {overall['superiorityDiceSpent']}, "
            f"ending dice avg {overall['averageEndingSuperiorityDice']}, "
            f"Precision {overall['precisionConverted']}/{overall['precisionUses']} converted, "
            f"Trip prone {overall['tripProneApplied']}/{overall['tripAttackUses']}, "
            f"Trip follow-ups {overall['tripFollowUpAttacks']}"
        ),
        (
            f"- sustain/GWM: Second Wind {overall['secondWindUses']} use(s), "
            f"Tactical Shift {overall['tacticalShiftUses']} move(s), "
            f"GWM +{overall['greatWeaponMasterDamageTotal']} damage across "
            f"{overall['greatWeaponMasterDamageApplications']} application(s)"
        ),
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"- {row['scenarioId']}: players {row['playerWinRate']}%, "
            f"damage/run {row['averageFighterDamagePerRun']}, "
            f"Precision {row['precisionConverted']}/{row['precisionUses']}, "
            f"Trip {row['tripProneApplied']}/{row['tripAttackUses']}, "
            f"Hew {row['hewAttacks']}, Riposte {row['riposteAttacks']}"
        )
    return "\n".join(lines)


def format_compact_party_line(profile: str, entry: dict[str, Any]) -> str:
    unit_id = entry.get("unitId", PARTY_PROFILE_UNIT_IDS.get(profile, "?"))
    if not entry or entry.get("missing"):
        return f"- {profile} ({unit_id}): missing - {entry.get('reason') or 'not recorded'}"

    overall = entry["overall"]
    if profile == "fighter":
        return (
            f"- fighter ({unit_id}): dmg/run {overall['averageFighterDamagePerRun']}, "
            f"attacks/run {overall['fighterAttacksPerRun']}, hit {overall['fighterHitRate']}%, "
            f"SD spent/run {overall['superiorityDiceSpentPerRun']}, "
            f"ending SD {overall['averageEndingSuperiorityDice']}, "
            f"Surge {overall['actionSurgeUses']}, Second Wind {overall['secondWindUses']}"
        )
    if profile == "paladin":
        return (
            f"- paladin ({unit_id}): Bless {overall['blessCasts']}, "
            f"LoH {overall['layOnHandsUses']} ({overall['layOnHandsDownedPickups']} pickups), "
            f"Cure {overall['cureWoundsUses']}, Smite {overall['divineSmites']}, "
            f"Nature {overall['naturesWrathUses']}, Sentinel {overall['sentinelGuardianTriggers']}, "
            f"ending slots {overall['averageEndingSpellSlots']}, ending LoH {overall['averageEndingLayOnHands']}"
        )
    if profile == "rogue":
        return (
            f"- rogue ({unit_id}): dmg/run {overall['averageRogueDamagePerRun']}, "
            f"attacks {overall['rogueAttacks']}, hit {overall['rogueHitRate']}%, "
            f"Sneak {overall['sneakAttackApplications']}, Steady {overall['steadyAimUses']}, "
            f"Hide {overall['hideSuccesses']}/{overall['hideAttempts']}, "
            f"Sharpshooter {overall['sharpshooterApplications']}, Uncanny {overall['uncannyDodgeUses']}"
        )
    if profile == "wizard":
        return (
            f"- wizard ({unit_id}): dmg/run {overall['averageWizardDamagePerRun']}, "
            f"slots spent {overall['wizardSpellSlotsSpent']}, unused-slot runs {overall['runsWithUnusedSpellSlots']}, "
            f"Fire Bolt {overall['fireBoltCasts']}, Magic Missile {overall['magicMissileCasts']}, "
            f"Scorching {overall['scorchingRayCasts']} ({overall['scorchingRaySplitCasts']} split), "
            f"Shatter {overall['shatterCasts']}, Burning Hands {overall['burningHandsCasts']}, "
            f"Shield {overall['shieldCasts']}, "
            f"down {overall['wizardDownAtEndRate']}%"
        )
    return f"- {profile} ({unit_id}): unsupported compact summary"


def format_compact_party_console_lines(
    party_breakdown: dict[str, dict[str, Any]],
    selected_profile: str,
    *,
    include_selected: bool = False,
) -> list[str]:
    if not party_breakdown:
        return []
    lines: list[str] = []
    for profile in ordered_party_profiles(selected_profile):
        if profile == selected_profile and not include_selected:
            continue
        lines.append(format_compact_party_line(profile, party_breakdown.get(profile, {})))
    return lines


def format_fighter_comparison_console_summary(payload: dict[str, Any]) -> str:
    smart = payload["behaviorSummaries"]["smart"]["overall"]
    dumb = payload["behaviorSummaries"]["dumb"]["overall"]
    delta_values = payload["behaviorDelta"]
    lines = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        "- playerBehavior: both",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        "- smart party breakdown:",
        *format_compact_party_console_lines(
            payload["behaviorSummaries"]["smart"].get("partyBreakdown", {}),
            "fighter",
            include_selected=True,
        ),
        "- dumb party breakdown:",
        *format_compact_party_console_lines(
            payload["behaviorSummaries"]["dumb"].get("partyBreakdown", {}),
            "fighter",
            include_selected=True,
        ),
        format_fighter_behavior_line("smart", smart),
        format_fighter_behavior_line("dumb", dumb),
        (
            f"- delta smart-dumb: win {delta_values['playerWinRate']}, "
            f"damage/run {delta_values['averageFighterDamagePerRun']}, "
            f"attacks/run {delta_values['fighterAttacksPerRun']}, "
            f"Precision conversion {delta_values['precisionConversionRate']}, "
            f"Trip prone {delta_values['tripProneRate']}, "
            f"surge damage/run {delta_values['actionSurgeDamagePerRun']}, "
            f"ending dice {delta_values['averageEndingSuperiorityDice']}"
        ),
    ]
    return "\n".join(lines)


def format_selected_console_summary(payload: dict[str, Any]) -> str:
    if payload["profile"] == "fighter" and payload.get("playerBehavior") == "both":
        return format_fighter_comparison_console_summary(payload)
    if payload["profile"] == "fighter":
        return format_fighter_console_summary(payload)
    if payload["profile"] == "rogue":
        return format_rogue_console_summary(payload)
    if payload["profile"] == "wizard":
        return format_wizard_console_summary(payload)

    overall = payload["overall"]
    lines = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        (
            f"- overall: players {overall['playerWinRate']}%, enemies {overall['enemyWinRate']}%, "
            f"avg rounds {overall['averageRounds']}"
        ),
        (
            f"- resources: avg ending slots {overall['averageEndingSpellSlots']}, "
            f"L1 {overall['averageEndingSpellSlotsLevel1']}, L2 {overall['averageEndingSpellSlotsLevel2']}; "
            f"unused slots {overall['runsWithUnusedSpellSlots']}/{overall['runs']}; "
            f"avg ending Lay on Hands {overall['averageEndingLayOnHands']}, "
            f"unused Lay on Hands {overall['runsWithUnusedLayOnHands']}/{overall['runs']}"
        ),
        (
            f"- healing: Lay on Hands {overall['layOnHandsUses']} use(s), "
            f"{overall['layOnHandsTotalHealing']} HP, {overall['layOnHandsDownedPickups']} downed pickup(s); "
            f"Cure Wounds {overall['cureWoundsUses']} use(s), {overall['cureWoundsTotalHealing']} HP"
        ),
        (
            f"- features: Divine Smite {overall['divineSmites']}, "
            f"Sentinel Guardian {overall['sentinelGuardianTriggers']}, "
            f"Sentinel Halt {overall['sentinelHaltApplied']}, "
            f"Nature's Wrath {overall['naturesWrathUses']} use(s), "
            f"avg restrained {overall['naturesWrathAverageRestrained']}"
        ),
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"- {row['scenarioId']}: players {row['playerWinRate']}%, "
            f"Smite {row['divineSmites']}, LoH {row['layOnHandsUses']}, "
            f"Nature {row['naturesWrathUses']}, Sentinel {row['sentinelGuardianTriggers']}"
        )
    return "\n".join(lines)


def format_console_summary(payload: dict[str, Any]) -> str:
    if payload["profile"] == "fighter" and payload.get("playerBehavior") == "both":
        return format_fighter_comparison_console_summary(payload)

    party_lines = format_compact_party_console_lines(payload.get("partyBreakdown", {}), payload["profile"])
    selected_summary = format_selected_console_summary(payload)
    if not party_lines:
        return selected_summary

    header = [
        "PC tuning sample:",
        f"- profile: {payload['profile']}",
        f"- unitId: {payload['unitId']}",
        f"- totalRuns: {payload['totalRuns']}",
        f"- playerBehavior: {payload['playerBehavior']}",
        f"- monsterBehavior: {payload['monsterBehavior']}",
        "- party breakdown:",
        *party_lines,
        "",
        "Selected profile detail:",
    ]
    return "\n".join(header + [selected_summary])


def format_rogue_markdown_report(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# PC Tuning Sample",
        "",
        f"- profile: `{payload['profile']}`",
        f"- unitId: `{payload['unitId']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- runsPerScenario: `{payload['runsPerScenario']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        f"- playerBehavior: `{payload['playerBehavior']}`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Player win rate | {overall['playerWinRate']}% |",
        f"| Average rounds | {overall['averageRounds']} |",
        f"| Rogue attacks | {overall['rogueAttacks']} |",
        f"| Rogue hit rate | {overall['rogueHitRate']}% |",
        f"| Rogue advantage attack rate | {overall['rogueAdvantageAttackRate']}% |",
        f"| Shortbow attack rate | {overall['shortbowAttackRate']}% |",
        f"| Rogue damage to HP | {overall['rogueDamageToHp']} |",
        f"| Average Rogue damage per run | {overall['averageRogueDamagePerRun']} |",
        f"| Sneak Attack applications | {overall['sneakAttackApplications']} |",
        f"| Sneak Attack hit rate | {overall['sneakAttackHitRate']}% |",
        f"| Sneak Attack damage | {overall['sneakAttackDamage']} |",
        f"| Hits without Sneak Attack | {overall['hitsWithoutSneakAttack']} |",
        f"| Steady Aim uses | {overall['steadyAimUses']} |",
        f"| Hide attempts | {overall['hideAttempts']} |",
        f"| Hide successes | {overall['hideSuccesses']} |",
        f"| Attacks from hidden | {overall['attacksFromHidden']} |",
        f"| Assassinate advantage attacks | {overall['assassinateAdvantageAttacks']} |",
        f"| Sharpshooter applications | {overall['sharpshooterApplications']} |",
        f"| Sharpshooter cover ignored events | {overall['sharpshooterCoverIgnoredEvents']} |",
        f"| Cunning Strike uses | {overall['cunningStrikeUses']} |",
        f"| Uncanny Dodge uses | {overall['uncannyDodgeUses']} |",
        f"| Uncanny Dodge damage prevented | {overall['uncannyDodgeDamagePrevented']} |",
        f"| Incoming attack hits | {overall['incomingAttackHits']} |",
        f"| Incoming damage to HP | {overall['incomingDamageToHp']} |",
        "",
        "## Scenarios",
        "",
        "| Scenario | Win Rate | Avg Rounds | Attacks | Hit Rate | Sneak | Steady | Hide | Sharpshooter | Uncanny | Damage/Run |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"| `{row['scenarioId']}` | {row['playerWinRate']}% | {row['averageRounds']} | "
            f"{row['rogueAttacks']} | {row['rogueHitRate']}% | {row['sneakAttackApplications']} | "
            f"{row['steadyAimUses']} | {row['hideSuccesses']}/{row['hideAttempts']} | "
            f"{row['sharpshooterApplications']} | {row['uncannyDodgeUses']} | "
            f"{row['averageRogueDamagePerRun']} |"
        )
    return "\n".join(lines)


def format_wizard_markdown_report(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# PC Tuning Sample",
        "",
        f"- profile: `{payload['profile']}`",
        f"- unitId: `{payload['unitId']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- runsPerScenario: `{payload['runsPerScenario']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        f"- playerBehavior: `{payload['playerBehavior']}`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Player win rate | {overall['playerWinRate']}% |",
        f"| Average rounds | {overall['averageRounds']} |",
        f"| Wizard down-at-end rate | {overall['wizardDownAtEndRate']}% |",
        f"| Average ending Wizard HP | {overall['averageEndingWizardHp']} |",
        f"| Wizard damage to HP | {overall['wizardDamageToHp']} |",
        f"| Average Wizard damage per run | {overall['averageWizardDamagePerRun']} |",
        f"| Cantrip damage | {overall['wizardCantripDamage']} |",
        f"| Slotted spell damage | {overall['wizardSlottedSpellDamage']} |",
        f"| Spell slots spent | {overall['wizardSpellSlotsSpent']} |",
        f"| Damage per slot spent | {overall['wizardDamagePerSlotSpent']} |",
        f"| Runs with unused spell slots | {overall['runsWithUnusedSpellSlots']} |",
        f"| Fire Bolt hits/casts | {overall['fireBoltHits']} / {overall['fireBoltCasts']} |",
        f"| Magic Missile casts | {overall['magicMissileCasts']} |",
        f"| Magic Missile casts by level | {overall['magicMissileCastsByLevel']} |",
        f"| Magic Missile projectiles | {overall['magicMissileProjectiles']} |",
        f"| Magic Missile split casts | {overall['magicMissileSplitCasts']} |",
        f"| Magic Missile kill secures | {overall['magicMissileKillSecures']} |",
        f"| Magic Missile overkill damage | {overall['magicMissileOverkillDamage']} |",
        f"| Scorching Ray casts | {overall['scorchingRayCasts']} |",
        f"| Scorching Ray split casts | {overall['scorchingRaySplitCasts']} |",
        f"| Scorching Ray ray attacks | {overall['scorchingRayRayAttacks']} |",
        f"| Scorching Ray hit rate | {overall['scorchingRayHitRate']}% |",
        f"| Scorching Ray kill secures | {overall['scorchingRayKillSecures']} |",
        f"| Shatter casts | {overall['shatterCasts']} |",
        f"| Shatter average targets | {overall['shatterAverageTargets']} |",
        f"| Shatter failed save rate | {overall['shatterFailedSaveRate']}% |",
        f"| Burning Hands casts | {overall['burningHandsCasts']} |",
        f"| Burning Hands average enemy targets | {overall['burningHandsAverageEnemyTargets']} |",
        f"| Burning Hands average ally targets | {overall['burningHandsAverageAllyTargets']} |",
        f"| Burning Hands friendly-fire casts | {overall['burningHandsFriendlyFireCasts']} |",
        f"| Burning Hands low-value casts | {overall['burningHandsLowValueCasts']} |",
        f"| Shocking Grasp casts | {overall['shockingGraspCasts']} |",
        f"| Shocking Grasp retreats | {overall['shockingGraspRetreats']} |",
        f"| Shield casts | {overall['shieldCasts']} |",
        f"| Shield prevented hits | {overall['shieldPreventedHits']} |",
        f"| Shield failed to stop hits | {overall['shieldFailedToStopHits']} |",
        f"| Mage Armor casts | {overall['mageArmorCasts']} |",
        f"| Dagger fallback attacks | {overall['daggerFallbackAttacks']} |",
        f"| Incoming attack hits | {overall['wizardIncomingAttackHits']} |",
        f"| Incoming damage to HP | {overall['wizardIncomingDamageToHp']} |",
        "",
        "## Spell Mix",
        "",
        "| Spell | Casts | Damage | Slots Spent |",
        "| --- | ---: | ---: | ---: |",
    ]
    spell_casts = overall["wizardSpellCasts"]
    spell_damage = overall["wizardSpellDamage"]
    spell_slots = overall["wizardSpellSlotsSpentBySpell"]
    for spell_id in sorted(set(spell_casts) | set(spell_damage) | set(spell_slots)):
        lines.append(
            f"| `{spell_id}` | {spell_casts.get(spell_id, 0)} | "
            f"{spell_damage.get(spell_id, 0)} | {spell_slots.get(spell_id, 0)} |"
        )

    lines.extend(
        [
            "",
            "## Scenarios",
            "",
            "| Scenario | Win Rate | Avg Rounds | Damage/Run | Slots Spent | Unused Slots | Shield | Magic Missile | Scorching | SR Split | Shatter | Shatter Targets | Burning Hands | BH Enemies | BH Allies | Down Rate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["scenarios"]:
        lines.append(
            f"| `{row['scenarioId']}` | {row['playerWinRate']}% | {row['averageRounds']} | "
            f"{row['averageWizardDamagePerRun']} | {row['wizardSpellSlotsSpent']} | "
            f"{row['runsWithUnusedSpellSlots']} | {row['shieldCasts']} | {row['magicMissileCasts']} | "
            f"{row['scorchingRayCasts']} | {row['scorchingRaySplitCasts']} | "
            f"{row['shatterCasts']} | {row['shatterAverageTargets']} | "
            f"{row['burningHandsCasts']} | {row['burningHandsAverageEnemyTargets']} | "
            f"{row['burningHandsAverageAllyTargets']} | {row['wizardDownAtEndRate']}% |"
        )
    return "\n".join(lines)


def append_fighter_markdown_sections(lines: list[str], overall: dict[str, Any], scenarios: list[dict[str, Any]]) -> None:
    lines.extend(
        [
            "## Overall",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Player win rate | {overall['playerWinRate']}% |",
            f"| Average rounds | {overall['averageRounds']} |",
            f"| Fighter attacks | {overall['fighterAttacks']} |",
            f"| Fighter hit rate | {overall['fighterHitRate']}% |",
            f"| Greatsword attack rate | {overall['greatswordAttackRate']}% |",
            f"| Fighter damage to HP | {overall['fighterDamageToHp']} |",
            f"| Average Fighter damage per run | {overall['averageFighterDamagePerRun']} |",
            f"| Action Surge uses | {overall['actionSurgeUses']} |",
            f"| Action Surge attacks | {overall['actionSurgeAttacks']} |",
            f"| Action Surge damage per run | {overall['actionSurgeDamagePerRun']} |",
            f"| Superiority Dice spent | {overall['superiorityDiceSpent']} |",
            f"| Average ending Superiority Dice | {overall['averageEndingSuperiorityDice']} |",
            f"| Precision converted | {overall['precisionConverted']} / {overall['precisionUses']} |",
            f"| Precision conversion rate | {overall['precisionConversionRate']}% |",
            f"| Trip prone applied | {overall['tripProneApplied']} / {overall['tripAttackUses']} |",
            f"| Trip follow-up attacks | {overall['tripFollowUpAttacks']} |",
            f"| Riposte attacks | {overall['riposteAttacks']} |",
            f"| Hew attacks | {overall['hewAttacks']} |",
            f"| GWM damage total | {overall['greatWeaponMasterDamageTotal']} |",
            f"| Second Wind uses | {overall['secondWindUses']} |",
            f"| Tactical Shift uses | {overall['tacticalShiftUses']} |",
            "",
            "## Scenarios",
            "",
            "| Scenario | Win Rate | Avg Rounds | Damage/Run | Attacks | Hit Rate | Precision | Trip | Hew | Riposte | Ending Dice |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in scenarios:
        lines.append(
            f"| `{row['scenarioId']}` | {row['playerWinRate']}% | {row['averageRounds']} | "
            f"{row['averageFighterDamagePerRun']} | {row['fighterAttacks']} | {row['fighterHitRate']}% | "
            f"{row['precisionConverted']}/{row['precisionUses']} | "
            f"{row['tripProneApplied']}/{row['tripAttackUses']} | {row['hewAttacks']} | "
            f"{row['riposteAttacks']} | {row['averageEndingSuperiorityDice']} |"
        )


def format_fighter_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# PC Tuning Sample",
        "",
        f"- profile: `{payload['profile']}`",
        f"- unitId: `{payload['unitId']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- runsPerScenario: `{payload['runsPerScenario']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        f"- playerBehavior: `{payload['playerBehavior']}`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
    ]
    append_fighter_markdown_sections(lines, payload["overall"], payload["scenarios"])
    return "\n".join(lines)


def format_fighter_comparison_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# PC Tuning Sample",
        "",
        f"- profile: `{payload['profile']}`",
        f"- unitId: `{payload['unitId']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- runsPerScenario: `{payload['runsPerScenario']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        "- playerBehavior: `both`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
        "## Smart Vs Dumb Delta",
        "",
        "| Metric | Smart - Dumb |",
        "| --- | ---: |",
    ]
    for key, value in payload["behaviorDelta"].items():
        lines.append(f"| {key} | {value} |")
    for behavior in ("smart", "dumb"):
        party_markdown = format_party_breakdown_markdown(
            payload["behaviorSummaries"][behavior].get("partyBreakdown", {}),
            "fighter",
            heading=f"## {behavior.title()} Party Breakdown",
        )
        if party_markdown:
            lines.extend(["", party_markdown])
        lines.extend(["", f"# {behavior.title()} Fighter", ""])
        append_fighter_markdown_sections(
            lines,
            payload["behaviorSummaries"][behavior]["overall"],
            payload["behaviorSummaries"][behavior]["scenarios"],
        )
    return "\n".join(lines)


def format_party_breakdown_markdown(
    party_breakdown: dict[str, dict[str, Any]],
    selected_profile: str,
    *,
    heading: str = "## Party Breakdown",
) -> str:
    if not party_breakdown:
        return ""
    lines = [
        heading,
        "",
        "| Class | Unit | Compact Summary |",
        "| --- | --- | --- |",
    ]
    for profile in ordered_party_profiles(selected_profile):
        entry = party_breakdown.get(profile, {})
        compact = format_compact_party_line(profile, entry)
        unit_id = entry.get("unitId", PARTY_PROFILE_UNIT_IDS.get(profile, "?"))
        lines.append(f"| {profile} | `{unit_id}` | {compact.removeprefix('- ')} |")
    return "\n".join(lines)


def format_selected_markdown_report(payload: dict[str, Any]) -> str:
    if payload["profile"] == "fighter" and payload.get("playerBehavior") == "both":
        return format_fighter_comparison_markdown_report(payload)
    if payload["profile"] == "fighter":
        return format_fighter_markdown_report(payload)
    if payload["profile"] == "rogue":
        return format_rogue_markdown_report(payload)
    if payload["profile"] == "wizard":
        return format_wizard_markdown_report(payload)

    overall = payload["overall"]
    lines = [
        "# PC Tuning Sample",
        "",
        f"- profile: `{payload['profile']}`",
        f"- unitId: `{payload['unitId']}`",
        f"- playerPresetId: `{payload['playerPresetId']}`",
        f"- scenarioIds: {', '.join(f'`{scenario_id}`' for scenario_id in payload['scenarioIds'])}",
        f"- runsPerScenario: `{payload['runsPerScenario']}`",
        f"- totalRuns: `{payload['totalRuns']}`",
        f"- playerBehavior: `{payload['playerBehavior']}`",
        f"- monsterBehavior: `{payload['monsterBehavior']}`",
        f"- elapsedSeconds: `{payload['elapsedSeconds']}`",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Player win rate | {overall['playerWinRate']}% |",
        f"| Average rounds | {overall['averageRounds']} |",
        f"| Average ending spell slots | {overall['averageEndingSpellSlots']} |",
        f"| Average ending 1st-level slots | {overall['averageEndingSpellSlotsLevel1']} |",
        f"| Average ending 2nd-level slots | {overall['averageEndingSpellSlotsLevel2']} |",
        f"| Runs with unused spell slots | {overall['runsWithUnusedSpellSlots']} |",
        f"| Average ending Lay on Hands | {overall['averageEndingLayOnHands']} |",
        f"| Runs with unused Lay on Hands | {overall['runsWithUnusedLayOnHands']} |",
        f"| Lay on Hands uses | {overall['layOnHandsUses']} |",
        f"| Lay on Hands total healing | {overall['layOnHandsTotalHealing']} |",
        f"| Lay on Hands downed pickups | {overall['layOnHandsDownedPickups']} |",
        f"| Cure Wounds uses | {overall['cureWoundsUses']} |",
        f"| Cure Wounds total healing | {overall['cureWoundsTotalHealing']} |",
        f"| Divine Smites | {overall['divineSmites']} |",
        f"| Sentinel Guardian triggers | {overall['sentinelGuardianTriggers']} |",
        f"| Sentinel Halt applied | {overall['sentinelHaltApplied']} |",
        f"| Nature's Wrath uses | {overall['naturesWrathUses']} |",
        f"| Nature's Wrath average targets | {overall['naturesWrathAverageTargets']} |",
        f"| Nature's Wrath average restrained | {overall['naturesWrathAverageRestrained']} |",
        "",
        "## Scenarios",
        "",
        "| Scenario | Win Rate | Avg Rounds | Smite | LoH Uses | Cure | Nature | Avg Restrained | Sentinel | Halt |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"| `{row['scenarioId']}` | {row['playerWinRate']}% | {row['averageRounds']} | "
            f"{row['divineSmites']} | {row['layOnHandsUses']} | {row['cureWoundsUses']} | "
            f"{row['naturesWrathUses']} | {row['naturesWrathAverageRestrained']} | "
            f"{row['sentinelGuardianTriggers']} | {row['sentinelHaltApplied']} |"
        )
    return "\n".join(lines)


def format_markdown_report(payload: dict[str, Any]) -> str:
    selected_report = format_selected_markdown_report(payload)
    if payload["profile"] == "fighter" and payload.get("playerBehavior") == "both":
        return selected_report

    party_markdown = format_party_breakdown_markdown(payload.get("partyBreakdown", {}), payload["profile"])
    if not party_markdown:
        return selected_report
    return f"{party_markdown}\n\n{selected_report}"


def main() -> None:
    args = parse_args()
    unit_id = resolve_profile_unit_id(args.profile, args.unit)
    player_behavior = resolve_profile_player_behavior(args.profile, args.player_behavior)
    if player_behavior == "both" and args.profile != "fighter":
        raise ValueError("--player-behavior both is only supported for the fighter profile.")
    scenario_ids = tuple(args.scenario_ids) if args.scenario_ids else DEFAULT_SCENARIO_IDS
    if args.runs_per_scenario <= 0:
        raise ValueError("--runs-per-scenario must be positive.")
    validate_scenarios(scenario_ids)

    started = time.perf_counter()
    if player_behavior == "both":
        behavior_summaries, behavior_delta = run_fighter_behavior_comparison(
            unit_id=unit_id,
            player_preset_id=args.player_preset,
            scenario_ids=scenario_ids,
            runs_per_scenario=args.runs_per_scenario,
            monster_behavior=args.monster_behavior,
        )
        elapsed = time.perf_counter() - started
        payload = build_behavior_comparison_payload(
            profile=args.profile,
            unit_id=unit_id,
            player_preset_id=args.player_preset,
            scenario_ids=scenario_ids,
            runs_per_scenario=args.runs_per_scenario,
            monster_behavior=args.monster_behavior,
            elapsed_seconds=elapsed,
            behavior_summaries=behavior_summaries,
            behavior_delta=behavior_delta,
        )
    else:
        overall, scenarios, party_breakdown = run_party_profile_sample(
            selected_profile=args.profile,
            selected_unit_id=unit_id,
            player_preset_id=args.player_preset,
            scenario_ids=scenario_ids,
            runs_per_scenario=args.runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=args.monster_behavior,
        )
        elapsed = time.perf_counter() - started
        payload = build_report_payload(
            profile=args.profile,
            unit_id=unit_id,
            player_preset_id=args.player_preset,
            scenario_ids=scenario_ids,
            runs_per_scenario=args.runs_per_scenario,
            player_behavior=player_behavior,
            monster_behavior=args.monster_behavior,
            elapsed_seconds=elapsed,
            overall=overall,
            scenarios=scenarios,
            party_breakdown=party_breakdown,
        )
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, format_markdown_report(payload))
    print(format_console_summary(payload))
    print(f"Wrote JSON report: {args.json_path}")
    print(f"Wrote Markdown report: {args.markdown_path}")
    if args.json:
        import json

        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
