from __future__ import annotations

from scripts import run_pc_tuning_sample


def test_pc_tuning_sample_defaults_to_paladin_standard_battery() -> None:
    assert run_pc_tuning_sample.PROFILE_CHOICES == ("paladin", "rogue", "fighter", "wizard")
    assert run_pc_tuning_sample.DEFAULT_PROFILE == "paladin"
    assert run_pc_tuning_sample.DEFAULT_UNIT_ID == "F2"
    assert run_pc_tuning_sample.PROFILE_DEFAULT_UNIT_IDS["rogue"] == "F3"
    assert run_pc_tuning_sample.PROFILE_DEFAULT_UNIT_IDS["fighter"] == "F1"
    assert run_pc_tuning_sample.PROFILE_DEFAULT_UNIT_IDS["wizard"] == "F4"
    assert run_pc_tuning_sample.PARTY_PROFILE_ORDER == ("fighter", "paladin", "rogue", "wizard")
    assert run_pc_tuning_sample.PARTY_PROFILE_UNIT_IDS == {
        "fighter": "F1",
        "paladin": "F2",
        "rogue": "F3",
        "wizard": "F4",
    }
    assert run_pc_tuning_sample.DEFAULT_RUNS_PER_SCENARIO == 60
    assert run_pc_tuning_sample.DEFAULT_PLAYER_BEHAVIOR == "smart"
    assert run_pc_tuning_sample.FIGHTER_DEFAULT_PLAYER_BEHAVIOR == "both"
    assert run_pc_tuning_sample.DEFAULT_MONSTER_BEHAVIOR == "balanced"
    assert run_pc_tuning_sample.DEFAULT_LAY_ON_HANDS_DOWNED_PERCENT == 30
    assert run_pc_tuning_sample.DEFAULT_LAY_ON_HANDS_ALLY_PERCENT == 55
    assert run_pc_tuning_sample.DEFAULT_LAY_ON_HANDS_SELF_PERCENT == 65
    assert run_pc_tuning_sample.DEFAULT_LAY_ON_HANDS_REMAINDER_PERCENT == 20
    assert run_pc_tuning_sample.DEFAULT_SCENARIO_IDS == (
        "reaction_bastion",
        "skyhunter_pincer",
        "hobgoblin_command_screen",
        "berserker_overrun",
    )


def test_pc_tuning_sample_summary_tracks_paladin_resources_and_feature_rates() -> None:
    metrics = run_pc_tuning_sample.new_metrics()
    metrics["runs"] = 2
    metrics["wins"].update({"fighters": 1, "goblins": 1})
    metrics["rounds"].extend([5, 7])
    metrics["endingSpellSlots"].extend([0, 3])
    metrics["endingSpellSlotsLevel1"].extend([0, 2])
    metrics["endingSpellSlotsLevel2"].extend([0, 1])
    metrics["endingLayOnHands"].extend([0, 4])
    metrics["aidCasts"] = 1
    metrics["aidTargets"] = 3
    metrics["aidHpBonusTotal"] = 15
    metrics["divineSmites"] = 3
    metrics["sentinelGuardianTriggers"] = 4
    metrics["sentinelHaltApplied"] = 2
    metrics["naturesWrathUses"] = 2
    metrics["naturesWrathTargets"].extend([4, 6])
    metrics["naturesWrathRestrained"].extend([2, 3])
    metrics["layOnHandsUses"] = 3
    metrics["layOnHandsTotalHealing"] = 21
    metrics["layOnHandsHeals"].extend([4, 7, 10])
    metrics["layOnHandsDownedPickups"] = 2
    metrics["layOnHandsPolicySignatures"].update({"downed30_ally55_self65_remainder20": 3})
    metrics["layOnHandsUsesByCategory"].update({"downed": 2, "living_ally": 1})
    metrics["layOnHandsTotalHealingByCategory"].update({"downed": 11, "living_ally": 10})
    metrics["layOnHandsHealsByCategory"]["downed"].extend([4, 7])
    metrics["layOnHandsHealsByCategory"]["living_ally"].append(10)
    metrics["layOnHandsDownedPickupsByCategory"].update({"downed": 2})
    metrics["layOnHandsTargetIdsByCategory"]["downed"].update({"F3": 2})
    metrics["layOnHandsTargetClassesByCategory"]["downed"].update({"rogue": 2})
    metrics["layOnHandsTargetIdsByCategory"]["living_ally"].update({"F1": 1})
    metrics["layOnHandsTargetClassesByCategory"]["living_ally"].update({"fighter": 1})
    metrics["cureWoundsUses"] = 1
    metrics["cureWoundsTotalHealing"] = 8
    metrics["cureWoundsHeals"].append(8)

    summary = run_pc_tuning_sample.summarize_metrics(metrics)

    assert summary["playerWinRate"] == 50.0
    assert summary["averageRounds"] == 6
    assert summary["runsWithUnusedSpellSlots"] == 1
    assert summary["averageEndingSpellSlots"] == 1.5
    assert summary["averageEndingSpellSlotsLevel1"] == 1
    assert summary["averageEndingSpellSlotsLevel2"] == 0.5
    assert summary["runsWithUnusedLayOnHands"] == 1
    assert summary["averageEndingLayOnHands"] == 2
    assert summary["aidCasts"] == 1
    assert summary["aidAverageTargets"] == 3
    assert summary["aidHpBonusTotal"] == 15
    assert summary["divineSmites"] == 3
    assert summary["sentinelHaltPerGuardianRate"] == 50.0
    assert summary["naturesWrathAverageTargets"] == 5
    assert summary["naturesWrathAverageRestrained"] == 2.5
    assert summary["naturesWrathRestrainedTargetRate"] == 50.0
    assert summary["layOnHandsAverageHeal"] == 7
    assert summary["layOnHandsDownedPickups"] == 2
    assert summary["layOnHandsPolicySignatureDistribution"] == {"downed30_ally55_self65_remainder20": 3}
    assert summary["layOnHandsByCategory"]["downed"]["uses"] == 2
    assert summary["layOnHandsByCategory"]["downed"]["healingTotal"] == 11
    assert summary["layOnHandsByCategory"]["downed"]["averageHeal"] == 5.5
    assert summary["layOnHandsByCategory"]["downed"]["pickups"] == 2
    assert summary["layOnHandsByCategory"]["downed"]["targetIds"] == {"F3": 2}
    assert summary["layOnHandsByCategory"]["downed"]["targetClasses"] == {"rogue": 2}
    assert summary["layOnHandsByCategory"]["living_ally"]["uses"] == 1
    assert summary["layOnHandsByCategory"]["living_ally"]["targetClasses"] == {"fighter": 1}
    assert summary["cureWoundsAverageHeal"] == 8


def test_pc_tuning_sample_resolves_profile_default_units() -> None:
    assert run_pc_tuning_sample.resolve_profile_unit_id("paladin", None) == "F2"
    assert run_pc_tuning_sample.resolve_profile_unit_id("rogue", None) == "F3"
    assert run_pc_tuning_sample.resolve_profile_unit_id("fighter", None) == "F1"
    assert run_pc_tuning_sample.resolve_profile_unit_id("wizard", None) == "F4"
    assert run_pc_tuning_sample.resolve_profile_unit_id("rogue", "F4") == "F4"


def test_pc_tuning_sample_resolves_default_behavior_by_profile() -> None:
    assert run_pc_tuning_sample.resolve_profile_player_behavior("paladin", None) == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("rogue", None) == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("wizard", None) == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("fighter", None) == "both"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("fighter", "smart") == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("fighter", "dumb") == "dumb"


def test_pc_tuning_sample_builds_lay_on_hands_policy_and_seed_offset() -> None:
    policy = run_pc_tuning_sample.build_lay_on_hands_policy(
        downed_percent=30,
        ally_percent=60,
        self_percent=65,
        remainder_percent=20,
    )

    assert policy == {
        "downedPercent": 30,
        "allyPercent": 60,
        "selfPercent": 65,
        "remainderPercent": 20,
        "signature": "downed30_ally60_self65_remainder20",
    }
    assert run_pc_tuning_sample.lay_on_hands_policy_config_kwargs(policy) == {
        "lay_on_hands_downed_percent": 30,
        "lay_on_hands_ally_percent": 60,
        "lay_on_hands_self_percent": 65,
        "lay_on_hands_remainder_percent": 20,
    }
    assert (
        run_pc_tuning_sample.sample_seed("pc-tuning-party", "hobgoblin_kill_box", 3, 10000, "smart")
        == "pc-tuning-party-smart-hobgoblin_kill_box-10003"
    )


def test_pc_tuning_sample_orders_selected_profile_last() -> None:
    assert run_pc_tuning_sample.ordered_party_profiles("wizard") == ("fighter", "paladin", "rogue", "wizard")
    assert run_pc_tuning_sample.ordered_party_profiles("fighter") == ("paladin", "rogue", "wizard", "fighter")


def test_pc_tuning_sample_summary_tracks_rogue_damage_reliability_and_defense() -> None:
    metrics = run_pc_tuning_sample.new_metrics("rogue")
    metrics["runs"] = 2
    metrics["wins"].update({"fighters": 1, "goblins": 1})
    metrics["rounds"].extend([4, 6])
    metrics["endingRogueHp"].extend([10, 0])
    metrics["rogueDownAtEnd"] = 1
    metrics["rogueAttacks"] = 4
    metrics["rogueHits"] = 3
    metrics["rogueCrits"] = 1
    metrics["rogueDamageToHp"] = 60
    metrics["rogueWeaponAttacks"].update({"shortbow": 3, "shortsword": 1})
    metrics["rogueAttackModeCounts"].update({"advantage": 2, "normal": 2})
    metrics["rogueAdvantageAttacks"] = 2
    metrics["rogueAdvantageSourceCounts"].update({"steady_aim": 1, "hidden": 1, "assassinate": 1})
    metrics["sneakAttackApplications"] = 2
    metrics["sneakAttackDamage"] = 30
    metrics["sneakAttackDiceRolled"] = 6
    metrics["hitsWithoutSneakAttack"] = 1
    metrics["assassinateAdvantageAttacks"] = 1
    metrics["assassinateDamageApplications"] = 1
    metrics["assassinateDamageTotal"] = 5
    metrics["steadyAimUses"] = 1
    metrics["attacksWithSteadyAim"] = 1
    metrics["hideAttempts"] = 2
    metrics["hideSuccesses"] = 1
    metrics["attacksFromHidden"] = 1
    metrics["sharpshooterApplications"] = 3
    metrics["sharpshooterCoverIgnoredEvents"] = 1
    metrics["sharpshooterCoverAcIgnoredTotal"] = 2
    metrics["sharpshooterIgnoredDisadvantageSourceCounts"].update({"long_range": 2, "adjacent_enemy": 1})
    metrics["uncannyDodgeUses"] = 1
    metrics["uncannyDodgeDamagePrevented"] = 4
    metrics["incomingAttackHits"] = 2
    metrics["incomingDamageToHp"] = 12
    metrics["damagingHitsTakenWithoutUncannyDodge"] = 1
    metrics["movementEvents"] = 2
    metrics["movementSquares"] = 5
    metrics["disengageMovementEvents"] = 1

    summary = run_pc_tuning_sample.summarize_metrics(metrics)

    assert summary["playerWinRate"] == 50.0
    assert summary["averageEndingRogueHp"] == 5
    assert summary["rogueDownAtEndRate"] == 50.0
    assert summary["rogueHitRate"] == 75.0
    assert summary["averageRogueDamagePerRun"] == 30
    assert summary["averageRogueDamagePerAttack"] == 15
    assert summary["shortbowAttackRate"] == 75.0
    assert summary["sneakAttackHitRate"] == 66.7
    assert summary["hitsWithoutSneakAttackRate"] == 33.3
    assert summary["steadyAimAttackFollowThroughRate"] == 100.0
    assert summary["hideSuccessRate"] == 50.0
    assert summary["hiddenAttackPerHideSuccessRate"] == 100.0
    assert summary["sharpshooterApplicationRate"] == 75.0
    assert summary["sharpshooterIgnoredDisadvantageSourceCounts"] == {"adjacent_enemy": 1, "long_range": 2}
    assert summary["uncannyDodgeUseRatePerIncomingHit"] == 50.0
    assert summary["averageUncannyDodgeDamagePrevented"] == 4
    assert summary["averageMovementSquaresPerRun"] == 2.5


def test_pc_tuning_sample_summary_tracks_wizard_spell_quality_and_survival() -> None:
    metrics = run_pc_tuning_sample.new_metrics("wizard")
    metrics["runs"] = 2
    metrics["wins"].update({"fighters": 1, "goblins": 1})
    metrics["rounds"].extend([4, 6])
    metrics["endingSpellSlots"].extend([0, 1])
    metrics["endingSpellSlotsLevel1"].extend([0, 1])
    metrics["endingSpellSlotsLevel2"].extend([0, 0])
    metrics["endingSpellSlotsLevel3"].extend([0, 0])
    metrics["endingWizardHp"].extend([8, 0])
    metrics["wizardDownAtEnd"] = 1
    metrics["wizardIncomingAttackHits"] = 3
    metrics["wizardIncomingDamageToHp"] = 18
    metrics["wizardDamagingHitsTaken"] = 2
    metrics["wizardAttacks"] = 5
    metrics["wizardHits"] = 3
    metrics["wizardCrits"] = 1
    metrics["wizardDamageToHp"] = 42
    metrics["wizardSpellCasts"].update(
        {
            "fire_bolt": 2,
            "magic_missile": 1,
            "burning_hands": 1,
            "scorching_ray": 2,
            "shatter": 1,
            "shield": 1,
            "shocking_grasp": 1,
        }
    )
    metrics["wizardSpellDamage"].update(
        {
            "fire_bolt": 12,
            "magic_missile": 9,
            "burning_hands": 16,
            "scorching_ray": 18,
            "shatter": 11,
            "shocking_grasp": 5,
        }
    )
    metrics["wizardSpellSlotsSpent"] = 7
    metrics["wizardSpellSlotsSpentBySpell"].update(
        {"magic_missile": 1, "burning_hands": 1, "scorching_ray": 2, "shatter": 1, "shield": 1}
    )
    metrics["wizardSpellSlotsSpentByLevel"].update({"1": 3, "2": 3, "3": 1})
    metrics["wizardCantripDamage"] = 17
    metrics["wizardSlottedSpellDamage"] = 54
    metrics["wizardAttackModeCounts"].update({"normal": 4, "disadvantage": 1})
    metrics["fireBoltCasts"] = 2
    metrics["fireBoltHits"] = 1
    metrics["fireBoltDamage"] = 12
    metrics["shockingGraspCasts"] = 1
    metrics["shockingGraspHits"] = 1
    metrics["shockingGraspDamage"] = 5
    metrics["shockingGraspNoReactionApplications"] = 1
    metrics["shockingGraspRetreats"] = 1
    metrics["magicMissileCasts"] = 1
    metrics["magicMissileDamage"] = 9
    metrics["magicMissileKillSecures"] = 1
    metrics["magicMissileOverkillDamage"] = 2
    metrics["magicMissileCastsByLevel"].update({"1": 1})
    metrics["magicMissileProjectiles"] = 3
    metrics["magicMissileSplitCasts"] = 0
    metrics["burningHandsCasts"] = 1
    metrics["burningHandsCastsByLevel"].update({"2": 1})
    metrics["burningHandsTargetDamageEvents"] = 3
    metrics["burningHandsDamage"] = 16
    metrics["burningHandsEnemyTargets"].append(3)
    metrics["burningHandsAllyTargets"].append(0)
    metrics["burningHandsSaveSuccesses"] = 1
    metrics["burningHandsSaveFailures"] = 2
    metrics["scorchingRayCasts"] = 2
    metrics["scorchingRayRayAttacks"] = 6
    metrics["scorchingRayHits"] = 4
    metrics["scorchingRayDamage"] = 18
    metrics["scorchingRayKillSecures"] = 2
    metrics["scorchingRaySplitCasts"] = 1
    metrics["scorchingRayUniqueTargets"].extend([1, 2])
    metrics["shatterCasts"] = 1
    metrics["shatterTargetDamageEvents"] = 2
    metrics["shatterDamage"] = 11
    metrics["shatterTargetCounts"].append(2)
    metrics["shatterSaveSuccesses"] = 1
    metrics["shatterSaveFailures"] = 1
    metrics["shieldCasts"] = 1
    metrics["shieldPreventedHits"] = 1
    metrics["daggerFallbackAttacks"] = 1
    metrics["daggerFallbackHits"] = 0
    metrics["wizardMovementEvents"] = 2
    metrics["wizardMovementSquares"] = 5

    summary = run_pc_tuning_sample.summarize_metrics(metrics)

    assert summary["playerWinRate"] == 50.0
    assert summary["averageEndingWizardHp"] == 4
    assert summary["wizardDownAtEndRate"] == 50.0
    assert summary["wizardHitRate"] == 60.0
    assert summary["averageWizardDamagePerRun"] == 21
    assert summary["wizardSpellCasts"]["fire_bolt"] == 2
    assert summary["wizardSpellCasts"]["magic_missile"] == 1
    assert summary["wizardSpellDamage"]["burning_hands"] == 16
    assert summary["wizardSpellSlotsSpentPerRun"] == 3.5
    assert summary["wizardSpellSlotsSpentByLevel"] == {"1": 3, "2": 3, "3": 1}
    assert summary["wizardDamagePerSlotSpent"] == 7.71
    assert summary["runsWithUnusedSpellSlotsLevel1"] == 1
    assert summary["runsWithUnusedSpellSlotsLevel2"] == 0
    assert summary["runsWithUnusedSpellSlotsLevel3"] == 0
    assert summary["fireBoltHitRate"] == 50.0
    assert summary["shockingGraspRetreatRate"] == 100.0
    assert summary["magicMissileKillSecureRate"] == 100.0
    assert summary["magicMissileCastsByLevel"] == {"1": 1}
    assert summary["magicMissileProjectiles"] == 3
    assert summary["magicMissileProjectilesPerCast"] == 3
    assert summary["magicMissileSplitCastRate"] == 0.0
    assert summary["burningHandsAverageEnemyTargets"] == 3
    assert summary["burningHandsCastsByLevel"] == {"2": 1}
    assert summary["burningHandsAverageAllyTargets"] == 0
    assert summary["burningHandsFriendlyFireRate"] == 0.0
    assert summary["burningHandsFailedSaveRate"] == 66.7
    assert summary["scorchingRayCasts"] == 2
    assert summary["scorchingRayRayAttacks"] == 6
    assert summary["scorchingRayHitRate"] == 66.7
    assert summary["scorchingRayAverageDamagePerCast"] == 9
    assert summary["scorchingRayRayAttacksPerCast"] == 3
    assert summary["scorchingRayKillSecureRate"] == 33.3
    assert summary["scorchingRaySplitCastRate"] == 50.0
    assert summary["scorchingRayUniqueTargetDistribution"] == {"1": 1, "2": 1}
    assert summary["shatterCasts"] == 1
    assert summary["shatterAverageTargets"] == 2
    assert summary["shatterFailedSaveRate"] == 50.0
    assert summary["shieldPreventedHitRate"] == 100.0
    assert summary["daggerFallbackHitRate"] == 0.0
    assert summary["averageWizardMovementSquaresPerRun"] == 2.5


def test_pc_tuning_sample_summary_tracks_fighter_action_economy_and_maneuvers() -> None:
    metrics = run_pc_tuning_sample.new_metrics("fighter")
    metrics["runs"] = 2
    metrics["wins"].update({"fighters": 1, "goblins": 1})
    metrics["rounds"].extend([5, 7])
    metrics["endingFighterHp"].extend([20, 0])
    metrics["fighterDownAtEnd"] = 1
    metrics["endingSuperiorityDice"].extend([0, 2])
    metrics["endingActionSurgeUses"].extend([0, 1])
    metrics["endingSecondWindUses"].extend([1, 2])
    metrics["fighterAttacks"] = 5
    metrics["fighterHits"] = 4
    metrics["fighterCrits"] = 1
    metrics["fighterDamageToHp"] = 100
    metrics["fighterWeaponAttacks"].update({"greatsword": 4, "javelin": 1})
    metrics["fighterAttackSourceCounts"].update({"attack_action": 2, "action_surge": 2, "riposte": 1})
    metrics["fighterDamageBySource"].update({"attack_action": 40, "action_surge": 45, "riposte": 15})
    metrics["fighterAttackModeCounts"].update({"advantage": 2, "normal": 3})
    metrics["fighterAdvantageSourceCounts"].update({"target_prone": 2})
    metrics["actionSurgeUses"] = 1
    metrics["actionSurgeAttacks"] = 2
    metrics["actionSurgeDamageToHp"] = 45
    metrics["superiorityDiceSpent"] = 4
    metrics["maneuverCounts"].update({"precision_attack": 2, "trip_attack": 1, "riposte": 1})
    metrics["precisionUses"] = 2
    metrics["precisionConverted"] = 1
    metrics["precisionFailed"] = 1
    metrics["precisionMissMargins"].extend([2, 6])
    metrics["precisionOnRiposteUses"] = 1
    metrics["tripAttackUses"] = 1
    metrics["tripSaveFailures"] = 1
    metrics["tripProneApplied"] = 1
    metrics["tripFollowUpAttacks"] = 2
    metrics["riposteTriggers"] = 1
    metrics["riposteAttacks"] = 1
    metrics["riposteHits"] = 1
    metrics["riposteDamageToHp"] = 15
    metrics["opportunityAttacks"] = 1
    metrics["opportunityHits"] = 0
    metrics["greatWeaponMasterDamageApplications"] = 3
    metrics["greatWeaponMasterDamageTotal"] = 9
    metrics["hewTriggers"] = 1
    metrics["hewAttacks"] = 1
    metrics["hewHits"] = 1
    metrics["hewDamageToHp"] = 12
    metrics["secondWindUses"] = 1
    metrics["secondWindTotalHealing"] = 8
    metrics["secondWindHeals"].append(8)
    metrics["tacticalShiftUses"] = 1
    metrics["tacticalShiftSquares"] = 3

    summary = run_pc_tuning_sample.summarize_metrics(metrics)

    assert summary["playerWinRate"] == 50.0
    assert summary["averageEndingFighterHp"] == 10
    assert summary["fighterDownAtEndRate"] == 50.0
    assert summary["averageEndingSuperiorityDice"] == 1
    assert summary["runsWithUnusedSuperiorityDice"] == 1
    assert summary["averageEndingActionSurgeUses"] == 0.5
    assert summary["averageEndingSecondWindUses"] == 1.5
    assert summary["fighterAttacksPerRun"] == 2.5
    assert summary["fighterHitRate"] == 80.0
    assert summary["averageFighterDamagePerRun"] == 50
    assert summary["averageFighterDamagePerAttack"] == 20
    assert summary["greatswordAttackRate"] == 80.0
    assert summary["javelinAttackRate"] == 20.0
    assert summary["actionSurgeDamagePerRun"] == 22.5
    assert summary["superiorityDiceSpentPerRun"] == 2
    assert summary["precisionConversionRate"] == 50.0
    assert summary["precisionMissMarginDistribution"] == {"2": 1, "6": 1}
    assert summary["tripProneRate"] == 100.0
    assert summary["tripFollowUpAttacks"] == 2
    assert summary["riposteHitRate"] == 100.0
    assert summary["opportunityHitRate"] == 0.0
    assert summary["hewHitRate"] == 100.0
    assert summary["secondWindAverageHeal"] == 8
    assert summary["averageTacticalShiftSquares"] == 3


def test_pc_tuning_sample_builds_fighter_behavior_delta() -> None:
    smart = {
        "playerWinRate": 70.0,
        "averageFighterDamagePerRun": 50.0,
        "fighterAttacksPerRun": 4.0,
        "superiorityDiceSpentPerRun": 2.0,
        "precisionConversionRate": 80.0,
        "tripProneRate": 50.0,
        "actionSurgeDamagePerRun": 20.0,
        "averageEndingSuperiorityDice": 1.0,
        "averageEndingActionSurgeUses": 0.0,
        "averageEndingSecondWindUses": 1.0,
    }
    dumb = {
        "playerWinRate": 60.0,
        "averageFighterDamagePerRun": 44.5,
        "fighterAttacksPerRun": 3.5,
        "superiorityDiceSpentPerRun": 3.0,
        "precisionConversionRate": 40.0,
        "tripProneRate": 25.0,
        "actionSurgeDamagePerRun": 14.0,
        "averageEndingSuperiorityDice": 0.0,
        "averageEndingActionSurgeUses": 0.5,
        "averageEndingSecondWindUses": 0.0,
    }

    behavior_delta = run_pc_tuning_sample.build_fighter_behavior_delta(smart, dumb)

    assert behavior_delta == {
        "playerWinRate": 10.0,
        "averageFighterDamagePerRun": 5.5,
        "fighterAttacksPerRun": 0.5,
        "superiorityDiceSpentPerRun": -1.0,
        "precisionConversionRate": 40.0,
        "tripProneRate": 25.0,
        "actionSurgeDamagePerRun": 6.0,
        "averageEndingSuperiorityDice": 1.0,
        "averageEndingActionSurgeUses": -0.5,
        "averageEndingSecondWindUses": 1.0,
    }


def test_pc_tuning_sample_builds_party_breakdown_payload() -> None:
    overall_metrics = {profile: run_pc_tuning_sample.new_metrics(profile) for profile in run_pc_tuning_sample.PARTY_PROFILE_ORDER}
    overall_metrics["fighter"]["runs"] = 1
    overall_metrics["fighter"]["wins"].update({"fighters": 1})
    overall_metrics["fighter"]["rounds"].append(3)
    scenario_rows = {profile: [] for profile in run_pc_tuning_sample.PARTY_PROFILE_ORDER}
    scenario_rows["fighter"].append({"scenarioId": "hobgoblin_kill_box", "runs": 1})
    party_breakdown = run_pc_tuning_sample.build_party_breakdown_payload(
        profile_unit_ids=dict(run_pc_tuning_sample.PARTY_PROFILE_UNIT_IDS),
        overall_metrics_by_profile=overall_metrics,
        scenario_rows_by_profile=scenario_rows,
        missing_reasons={"wizard": "Unit `F4` is not present in final encounter state."},
    )

    assert tuple(party_breakdown) == run_pc_tuning_sample.PARTY_PROFILE_ORDER
    assert party_breakdown["fighter"]["unitId"] == "F1"
    assert party_breakdown["fighter"]["missing"] is False
    assert party_breakdown["fighter"]["overall"]["runs"] == 1
    assert party_breakdown["wizard"]["missing"] is True
    assert "F4" in party_breakdown["wizard"]["reason"]


def test_pc_tuning_sample_report_payload_preserves_selected_summary_and_party_breakdown() -> None:
    selected_overall = {"runs": 1, "playerWinRate": 100.0}
    selected_scenarios = [{"scenarioId": "hobgoblin_kill_box", "runs": 1}]
    party_breakdown = {
        "fighter": {"unitId": "F1", "overall": {"runs": 1}, "scenarios": []},
        "paladin": {"unitId": "F2", "overall": {"runs": 1}, "scenarios": []},
        "rogue": {"unitId": "F3", "overall": {"runs": 1}, "scenarios": []},
        "wizard": {"unitId": "F4", "overall": selected_overall, "scenarios": selected_scenarios},
    }

    payload = run_pc_tuning_sample.build_report_payload(
        profile="wizard",
        unit_id="F4",
        player_preset_id="martial_mixed_party",
        scenario_ids=("hobgoblin_kill_box",),
        runs_per_scenario=1,
        player_behavior="smart",
        monster_behavior="balanced",
        elapsed_seconds=0.1,
        overall=selected_overall,
        scenarios=selected_scenarios,
        party_breakdown=party_breakdown,
        seed_offset=10000,
        lay_on_hands_policy=run_pc_tuning_sample.build_lay_on_hands_policy(ally_percent=55),
    )

    assert payload["overall"] is selected_overall
    assert payload["scenarios"] is selected_scenarios
    assert payload["partyBreakdown"] is party_breakdown
    assert payload["seedOffset"] == 10000
    assert payload["layOnHandsPolicy"]["signature"] == "downed30_ally55_self65_remainder20"


def test_pc_tuning_sample_fighter_both_payload_includes_party_breakdown_per_behavior() -> None:
    behavior_summaries = {
        "smart": {
            "overall": {"playerWinRate": 100.0},
            "scenarios": [],
            "partyBreakdown": {"fighter": {"unitId": "F1"}},
        },
        "dumb": {
            "overall": {"playerWinRate": 0.0},
            "scenarios": [],
            "partyBreakdown": {"fighter": {"unitId": "F1"}},
        },
    }

    payload = run_pc_tuning_sample.build_behavior_comparison_payload(
        profile="fighter",
        unit_id="F1",
        player_preset_id="martial_mixed_party",
        scenario_ids=("hobgoblin_kill_box",),
        runs_per_scenario=1,
        monster_behavior="balanced",
        elapsed_seconds=0.1,
        behavior_summaries=behavior_summaries,
        behavior_delta={"playerWinRate": 100.0},
        seed_offset=250,
        lay_on_hands_policy=run_pc_tuning_sample.build_lay_on_hands_policy(ally_percent=55),
    )

    assert payload["behaviorSummaries"]["smart"]["partyBreakdown"]["fighter"]["unitId"] == "F1"
    assert payload["behaviorSummaries"]["dumb"]["partyBreakdown"]["fighter"]["unitId"] == "F1"
    assert payload["seedOffset"] == 250
    assert payload["layOnHandsPolicy"]["signature"] == "downed30_ally55_self65_remainder20"


def test_pc_tuning_sample_party_sampler_records_current_party_profiles() -> None:
    overall, scenarios, party_breakdown = run_pc_tuning_sample.run_party_profile_sample(
        selected_profile="wizard",
        selected_unit_id="F4",
        player_preset_id=run_pc_tuning_sample.DEFAULT_PLAYER_PRESET_ID,
        scenario_ids=("hobgoblin_kill_box",),
        runs_per_scenario=1,
        player_behavior="smart",
        monster_behavior="balanced",
    )

    assert overall == party_breakdown["wizard"]["overall"]
    assert scenarios == party_breakdown["wizard"]["scenarios"]
    assert tuple(party_breakdown) == run_pc_tuning_sample.PARTY_PROFILE_ORDER
    for profile in run_pc_tuning_sample.PARTY_PROFILE_ORDER:
        assert party_breakdown[profile]["missing"] is False
        assert party_breakdown[profile]["overall"]["runs"] == 1
    compact_lines = run_pc_tuning_sample.format_compact_party_console_lines(
        party_breakdown,
        "wizard",
        include_selected=True,
    )
    assert all("down " in line for line in compact_lines)


def test_pc_tuning_sample_compact_party_console_lines_skip_selected_until_detail() -> None:
    party_breakdown = {
        "fighter": {"unitId": "F1", "missing": True, "reason": "missing fighter", "overall": {}, "scenarios": []},
        "paladin": {"unitId": "F2", "missing": True, "reason": "missing paladin", "overall": {}, "scenarios": []},
        "rogue": {"unitId": "F3", "missing": True, "reason": "missing rogue", "overall": {}, "scenarios": []},
        "wizard": {"unitId": "F4", "missing": True, "reason": "missing wizard", "overall": {}, "scenarios": []},
    }

    lines = run_pc_tuning_sample.format_compact_party_console_lines(party_breakdown, "wizard")
    all_lines = run_pc_tuning_sample.format_compact_party_console_lines(
        party_breakdown,
        "wizard",
        include_selected=True,
    )

    assert [line.split()[1] for line in lines] == ["fighter", "paladin", "rogue"]
    assert [line.split()[1] for line in all_lines] == ["fighter", "paladin", "rogue", "wizard"]
