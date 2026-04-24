from __future__ import annotations

from typing import Any

MONITORED_FINDINGS: tuple[dict[str, str], ...] = (
    {
        "id": "scenario_hobgoblin_kill_box_smart_under_dumb",
        "area": "scenario",
        "status": "monitored",
        "summary": "Scenario smart-under-dumb warning in hobgoblin_kill_box remains monitored.",
        "evidenceReference": "reports/scenario_audit_latest.json",
        "nextAction": "Keep as a monitored balance note unless a future scenario pass reproduces a larger gap.",
    },
    {
        "id": "rogue_wolf_harriers_monitored_note",
        "area": "rogue",
        "status": "monitored",
        "summary": "Rogue wolf_harriers note remains monitored from Pass 1.",
        "evidenceReference": "reports/rogue_audit/rogue_audit_latest.json",
        "nextAction": "Recheck after the next Rogue behavior or scenario-balance change.",
    },
    {
        "id": "rogue_marsh_predators_hide_effectiveness",
        "area": "rogue",
        "status": "monitored",
        "summary": "Rogue marsh_predators hide-effectiveness warning remains monitored.",
        "evidenceReference": "reports/rogue_audit/rogue_audit_latest.json",
        "nextAction": "Revisit only if Rogue hiding changes or marsh_predators is retuned.",
    },
    {
        "id": "fighter_martial_mixed_party_orc_push",
        "area": "fighter",
        "status": "monitored",
        "summary": "Mixed-party Fighter orc_push warning remains monitored.",
        "evidenceReference": "reports/pass1/class_slices/martial_mixed_party_refresh_2026-04-23.json",
        "nextAction": "Carry into the next Fighter behavior review unless a larger direct audit reproduces it.",
    },
    {
        "id": "fighter_martial_mixed_party_predator_rampage",
        "area": "fighter",
        "status": "monitored",
        "summary": "Mixed-party Fighter predator_rampage warning remains monitored.",
        "evidenceReference": "reports/pass1/class_slices/martial_mixed_party_refresh_2026-04-23.json",
        "nextAction": "Carry into the next Fighter behavior review unless a larger direct audit reproduces it.",
    },
    {
        "id": "fighter_martial_mixed_party_captains_crossfire",
        "area": "fighter",
        "status": "monitored",
        "summary": "Mixed-party Fighter captains_crossfire warning remains monitored.",
        "evidenceReference": "reports/pass1/class_slices/martial_mixed_party_refresh_2026-04-23.json",
        "nextAction": "Carry into the next Fighter behavior review unless a larger direct audit reproduces it.",
    },
    {
        "id": "barbarian_martial_mixed_party_wolf_harriers",
        "area": "barbarian",
        "status": "monitored",
        "summary": "Mixed-party Barbarian wolf_harriers warning remains monitored.",
        "evidenceReference": "reports/pass1/class_slices/martial_mixed_party_refresh_2026-04-23.json",
        "nextAction": "Carry into the next Barbarian behavior review unless a larger direct audit reproduces it.",
    },
)

ACTIVE_WAIVERS: tuple[dict[str, str], ...] = (
    {
        "id": "monk_audit_runner_missing",
        "area": "classAudit",
        "status": "waived",
        "summary": "Dedicated Monk audit runner remains waived; live Monk preset is still covered by determinism.",
        "reason": "Monk behavior is covered by scenario and Pass 2 determinism, but not by a dedicated class audit runner.",
        "alternateEvidence": "reports/pass2/pass2_stability_latest.json",
        "retirementCondition": "Implement and gate a dedicated Monk audit runner.",
    },
    {
        "id": "wizard_audit_runner_missing",
        "area": "classAudit",
        "status": "waived",
        "summary": "Dedicated Wizard audit runner remains waived; live Wizard preset is still covered by determinism.",
        "reason": "The live Wizard is a level-1 combat slice covered by scenario/API/determinism evidence.",
        "alternateEvidence": "reports/pass2/pass2_stability_latest.json",
        "retirementCondition": "Implement and gate a dedicated Wizard audit runner.",
    },
    {
        "id": "monster_audit_runner_missing",
        "area": "monsterAudit",
        "status": "waived",
        "summary": "Dedicated Monster audit runner remains waived; live monsters are still covered by scenario/batch determinism.",
        "reason": "Monster behavior is covered by scenario signatures and determinism, but not by a dedicated integrity runner.",
        "alternateEvidence": "reports/scenario_audit_latest.json",
        "retirementCondition": "Implement and gate a dedicated Monster audit runner.",
    },
)


def get_monitored_findings() -> list[dict[str, Any]]:
    return [dict(item) for item in MONITORED_FINDINGS]


def get_active_waivers() -> list[dict[str, Any]]:
    return [dict(item) for item in ACTIVE_WAIVERS]
