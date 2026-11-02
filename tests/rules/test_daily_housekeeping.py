from __future__ import annotations

from scripts import run_daily_housekeeping as housekeeping


def test_clean_tree_classifies_as_clean() -> None:
    classification = housekeeping.classify_repo_state([])

    assert classification.status == "clean"
    assert classification.files_to_stage == []
    assert classification.files_to_avoid == []


def test_docs_only_changes_classify_as_safe_proposed() -> None:
    entries = housekeeping.parse_porcelain_status(" M README.md\n M docs/MASTER_NOTES.md\n")

    classification = housekeeping.classify_repo_state(entries)

    assert classification.status == "safeProposed"
    assert classification.files_to_stage == ["README.md", "docs/MASTER_NOTES.md"]
    assert classification.files_to_avoid == []


def test_code_change_classifies_as_needs_review() -> None:
    entries = housekeeping.parse_porcelain_status(" M backend/engine/combat/engine.py\n")

    classification = housekeeping.classify_repo_state(entries)

    assert classification.status == "needsReview"
    assert classification.files_to_avoid == ["backend/engine/combat/engine.py"]


def test_untracked_spreadsheet_classifies_as_needs_review() -> None:
    entries = housekeeping.parse_porcelain_status("?? docs/reference/TrimmedSpellListV2.xlsx\n")

    classification = housekeeping.classify_repo_state(entries)

    assert classification.status == "needsReview"
    assert classification.files_to_avoid == ["docs/reference/TrimmedSpellListV2.xlsx"]


def test_staged_and_unstaged_same_file_classifies_as_needs_review() -> None:
    entries = housekeeping.parse_porcelain_status("MM backend/engine/models/state.py\n")

    classification = housekeeping.classify_repo_state(entries)

    assert classification.status == "needsReview"
    assert "both staged and unstaged edits" in classification.reasons[0]


def test_missing_dev_command_in_docs_is_detected() -> None:
    findings = housekeeping.find_missing_doc_tasks(
        ["check-fast", "party-validation"],
        readme_text="check-fast",
        audit_runbook_text="check-fast",
    )

    assert len(findings) == 1
    assert "`party-validation`" in findings[0].message
    assert "README.md" in str(findings[0].path)
    assert "docs/AUDIT_RUNBOOK.md" in str(findings[0].path)


def test_stale_class_level_snapshot_is_detected() -> None:
    findings = housekeeping.find_class_support_drift(
        {"Fighter": 5, "Wizard": 1},
        docs_text="Fighter supported to level 2. Wizard supported to level 1.",
    )

    assert len(findings) == 1
    assert "Fighter" in findings[0].message
    assert "level 5" in findings[0].message


def test_stale_default_party_text_is_detected() -> None:
    findings = housekeeping.find_default_party_drift(
        "martial_mixed_party",
        [{"unitId": "F1", "classDisplayName": "Fighter", "level": 5}],
        docs_text="The default preset is martial_mixed_party with a level 2 Fighter.",
    )

    assert len(findings) == 1
    assert "F1" in findings[0].message


def test_party_validation_scenario_drift_is_detected() -> None:
    findings = housekeeping.find_party_validation_drift(
        ("hobgoblin_kill_box", "deadwatch_phalanx"),
        docs_text="party-validation covers hobgoblin_kill_box only.",
    )

    assert len(findings) == 1
    assert "deadwatch_phalanx" in findings[0].message


def test_safe_commit_recommendation_is_docs_message() -> None:
    classification = housekeeping.RepoClassification(
        status="safeProposed",
        reasons=["Only docs/admin/test tracked changes were detected."],
        files_to_stage=["README.md", "docs/AUDIT_RUNBOOK.md"],
        files_to_avoid=[],
    )

    recommendation = housekeeping.build_commit_recommendation(classification, [])

    assert recommendation["recommended"] is True
    assert recommendation["message"] == "Update project documentation"
