from __future__ import annotations

from scripts import run_pc_tuning_sample


def test_pc_tuning_sample_defaults_to_paladin_standard_battery() -> None:
    assert run_pc_tuning_sample.PROFILE_CHOICES == ("paladin", "rogue", "fighter")
    assert run_pc_tuning_sample.DEFAULT_PROFILE == "paladin"
    assert run_pc_tuning_sample.DEFAULT_UNIT_ID == "F2"
    assert run_pc_tuning_sample.PROFILE_DEFAULT_UNIT_IDS["rogue"] == "F3"
    assert run_pc_tuning_sample.PROFILE_DEFAULT_UNIT_IDS["fighter"] == "F1"
    assert run_pc_tuning_sample.DEFAULT_RUNS_PER_SCENARIO == 60
    assert run_pc_tuning_sample.DEFAULT_PLAYER_BEHAVIOR == "smart"
    assert run_pc_tuning_sample.FIGHTER_DEFAULT_PLAYER_BEHAVIOR == "both"
    assert run_pc_tuning_sample.DEFAULT_MONSTER_BEHAVIOR == "balanced"
    assert run_pc_tuning_sample.DEFAULT_SCENARIO_IDS == (
        "hobgoblin_kill_box",
        "bugbear_dragnet",
        "deadwatch_phalanx",
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
    assert summary["divineSmites"] == 3
    assert summary["sentinelHaltPerGuardianRate"] == 50.0
    assert summary["naturesWrathAverageTargets"] == 5
    assert summary["naturesWrathAverageRestrained"] == 2.5
    assert summary["naturesWrathRestrainedTargetRate"] == 50.0
    assert summary["layOnHandsAverageHeal"] == 7
    assert summary["layOnHandsDownedPickups"] == 2
    assert summary["cureWoundsAverageHeal"] == 8


def test_pc_tuning_sample_resolves_profile_default_units() -> None:
    assert run_pc_tuning_sample.resolve_profile_unit_id("paladin", None) == "F2"
    assert run_pc_tuning_sample.resolve_profile_unit_id("rogue", None) == "F3"
    assert run_pc_tuning_sample.resolve_profile_unit_id("fighter", None) == "F1"
    assert run_pc_tuning_sample.resolve_profile_unit_id("rogue", "F4") == "F4"


def test_pc_tuning_sample_resolves_default_behavior_by_profile() -> None:
    assert run_pc_tuning_sample.resolve_profile_player_behavior("paladin", None) == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("rogue", None) == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("fighter", None) == "both"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("fighter", "smart") == "smart"
    assert run_pc_tuning_sample.resolve_profile_player_behavior("fighter", "dumb") == "dumb"


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
