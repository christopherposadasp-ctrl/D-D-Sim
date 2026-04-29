from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts import run_audit_validation as audit_validation


def test_extracts_dev_tasks_and_runbook_direct_equivalents() -> None:
    dev_text = '[ValidateSet("check-fast", "audit-validation")] [string]$Task'
    runbook_text = "\n- `check-fast`: `py -3.13 -m pytest`\n- `audit-validation`: `py -3.13 .\\scripts\\run_audit_validation.py`\n"

    assert audit_validation.extract_dev_tasks(dev_text) == ["check-fast", "audit-validation"]
    assert audit_validation.extract_runbook_direct_equivalents(runbook_text) == {
        "check-fast": "py -3.13 -m pytest",
        "audit-validation": "py -3.13 .\\scripts\\run_audit_validation.py",
    }


def test_command_coverage_detects_doc_mismatch() -> None:
    coverage = audit_validation.build_command_coverage(
        wrapper_tasks=["check-fast", "audit-validation"],
        runbook_mappings={"check-fast": "py -3.13 -m pytest"},
    )

    assert "audit-validation" in coverage["missingRunbookDirectEquivalent"]
    assert "audit-validation" in coverage["undocumentedWrapperTasks"]


def test_summarize_json_report_extracts_status_runtime_and_coverage(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    payload = {
        "overallStatus": "warn",
        "elapsedSeconds": 12.5,
        "scenarioIds": ["goblin_screen"],
        "playerPresetIds": ["martial_mixed_party"],
        "warnings": ["sample warning"],
        "rows": [{"status": "pass"}, {"status": "warn"}],
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = audit_validation.summarize_json_report(
        report_path,
        now=datetime.now(tz=UTC),
        stale_days=14,
    )

    assert summary["status"] == "warn"
    assert summary["elapsedSeconds"] == 12.5
    assert summary["rowCount"] == 2
    assert summary["warningCount"] == 2
    assert summary["scenarioIds"] == ["goblin_screen"]
    assert summary["playerPresetIds"] == ["martial_mixed_party"]


def test_missing_report_lowers_confidence_without_failing_row() -> None:
    mechanism = audit_validation.AuditMechanism(
        task="example-audit",
        purpose="example",
        recommended_gate_level="checkpoint",
        report_paths=("reports/does_not_exist/audit.json",),
        overlap_candidates=(),
    )

    row = audit_validation.build_mechanism_row(
        mechanism=mechanism,
        wrapper_tasks=["example-audit"],
        runbook_mappings={"example-audit": "py example.py"},
        now=datetime.now(tz=UTC),
        stale_days=14,
    )

    assert row["status"] == "warn"
    assert row["validationConfidence"] == "low"
    assert "json_report_missing" in row["confidenceReasons"]


def test_segmented_class_summary_satisfies_class_evidence(tmp_path: Path) -> None:
    summary_path = tmp_path / "fighter_barbarian_quick_latest.json"
    summary_path.write_text(
        json.dumps({"overallStatus": "warn", "results": [{"status": "pass"}, {"status": "warn"}]}),
        encoding="utf-8",
    )
    mechanism = audit_validation.AuditMechanism(
        task="class-audit-slices",
        purpose="canonical class evidence",
        recommended_gate_level="checkpoint",
        report_paths=(str(summary_path),),
        overlap_candidates=(),
    )

    row = audit_validation.build_mechanism_row(
        mechanism=mechanism,
        wrapper_tasks=["class-audit-slices"],
        runbook_mappings={"class-audit-slices": "py -3.13 .\\scripts\\run_class_audit_slices.py"},
        now=datetime.now(tz=UTC),
        stale_days=14,
    )

    assert row["validationConfidence"] == "high"
    assert row["status"] == "pass"
    assert row["latestStatus"] == "warn"


def test_failed_segmented_class_summary_needs_refresh(tmp_path: Path) -> None:
    summary_path = tmp_path / "fighter_barbarian_quick_latest.json"
    summary_path.write_text(json.dumps({"overallStatus": "fail", "results": [{"status": "timeout"}]}), encoding="utf-8")
    mechanism = audit_validation.AuditMechanism(
        task="class-audit-slices",
        purpose="canonical class evidence",
        recommended_gate_level="checkpoint",
        report_paths=(str(summary_path),),
        overlap_candidates=(),
    )

    row = audit_validation.build_mechanism_row(
        mechanism=mechanism,
        wrapper_tasks=["class-audit-slices"],
        runbook_mappings={"class-audit-slices": "py -3.13 .\\scripts\\run_class_audit_slices.py"},
        now=datetime.now(tz=UTC),
        stale_days=14,
    )
    recommendations = audit_validation.build_recommendations([row])

    assert row["validationConfidence"] == "low"
    assert "canonical_class_evidence_failed" in row["confidenceReasons"]
    assert recommendations["needsLaterValidation"] == ["class-audit-slices"]
    assert recommendations["needsEvidenceRefresh"] == ["class-audit-slices"]


def test_legacy_fighter_report_is_not_required_for_confidence() -> None:
    mechanism = next(item for item in audit_validation.MECHANISMS if item.task == "fighter-audit-quick")

    row = audit_validation.build_mechanism_row(
        mechanism=mechanism,
        wrapper_tasks=["fighter-audit-quick"],
        runbook_mappings={"fighter-audit-quick": "py -3.13 .\\scripts\\run_fighter_audit.py"},
        now=datetime.now(tz=UTC),
        stale_days=14,
    )

    assert row["recommendedGateLevel"] == "forensic"
    assert row["validationConfidence"] == "high"
    assert row["reportArtifacts"] == []


def test_heavy_smoke_measurement_is_skipped_without_include_heavy() -> None:
    rows = [
        {
            "task": "pass2-stability",
            "status": "pass",
            "validationConfidence": "high",
            "confidenceReasons": [],
            "reportArtifacts": [],
        }
    ]

    audit_validation.maybe_measure_rows(
        rows=rows,
        mechanisms=audit_validation.MECHANISMS,
        measure_smoke=True,
        include_heavy=False,
        timeout_seconds=300,
    )

    assert rows[0]["smokeMeasurement"]["status"] == "skipped"
    assert "Heavy command skipped" in rows[0]["smokeMeasurement"]["reason"]


def test_coverage_review_assigns_risk_areas_to_every_known_mechanism() -> None:
    rows = [
        {
            "task": mechanism.task,
            "recommendedGateLevel": mechanism.recommended_gate_level,
            "inferredRuntimeClass": "unknown",
            "overlapCandidates": list(mechanism.overlap_candidates),
        }
        for mechanism in audit_validation.MECHANISMS
    ]

    review = audit_validation.build_coverage_review(rows)

    assert {entry["task"] for entry in review["mechanisms"]} == {mechanism.task for mechanism in audit_validation.MECHANISMS}
    assert all(entry["riskAreas"] for entry in review["mechanisms"])
    assert any(entry["id"] == "nightly.scenario_quick" for entry in review["trimCandidates"])
    assert any(entry["id"] == "nightly.code_health" for entry in review["trimCandidates"])


def test_coverage_review_classifies_nightly_steps_individually() -> None:
    review = audit_validation.build_coverage_review([])
    nightly_by_id = {entry["stepId"]: entry for entry in review["nightlySteps"]}

    assert set(nightly_by_id) == {
        "branch_gate",
        "check_fast",
        "npm_test",
        "npm_build",
        "scenario_quick",
        "code_health",
        "rotating_slice",
    }
    assert nightly_by_id["scenario_quick"]["candidateAction"] == "measure_more"
    assert nightly_by_id["check_fast"]["candidateAction"] == "measure_more"


def write_nightly_runtime_report(tmp_path: Path, total_seconds: float, slowest_step_id: str = "scenario_quick") -> None:
    report_path = tmp_path / "reports/nightly/nightly_audit_latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"runtimeSummary": {"totalMeasuredSeconds": total_seconds, "slowestStepId": slowest_step_id}}),
        encoding="utf-8",
    )


def build_nightly_row() -> dict[str, object]:
    return {
        "task": "nightly-audit",
        "recommendedGateLevel": "release",
        "inferredRuntimeClass": "medium",
        "overlapCandidates": ["check-fast", "audit-quick", "audit-health"],
        "reportArtifacts": [{"path": "reports/nightly/nightly_audit_latest.json", "exists": True}],
    }


def test_under_budget_nightly_keeps_scenario_quick(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit_validation, "REPO_ROOT", tmp_path)
    write_nightly_runtime_report(tmp_path, 2256.0)

    review = audit_validation.build_coverage_review([build_nightly_row()])
    nightly_by_id = {entry["stepId"]: entry for entry in review["nightlySteps"]}

    assert review["runtimeBudgetStatus"] == "pass"
    assert review["latestNightlyRuntimeSeconds"] == 2256.0
    assert nightly_by_id["scenario_quick"]["candidateAction"] == "keep"
    assert not any(entry["id"] == "nightly.scenario_quick" for entry in review["trimCandidates"])
    assert "under the 1-hour budget" in review["decisionSummary"]


def test_warning_zone_nightly_measures_scenario_quick(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit_validation, "REPO_ROOT", tmp_path)
    write_nightly_runtime_report(tmp_path, 3200.0)

    review = audit_validation.build_coverage_review([build_nightly_row()])
    nightly_by_id = {entry["stepId"]: entry for entry in review["nightlySteps"]}

    assert review["runtimeBudgetStatus"] == "warn"
    assert nightly_by_id["scenario_quick"]["candidateAction"] == "measure_more"
    assert nightly_by_id["code_health"]["candidateAction"] == "measure_more"


def test_over_budget_nightly_flags_scenario_and_code_health_trim_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit_validation, "REPO_ROOT", tmp_path)
    write_nightly_runtime_report(tmp_path, 3700.0)

    review = audit_validation.build_coverage_review([build_nightly_row()])
    nightly_by_id = {entry["stepId"]: entry for entry in review["nightlySteps"]}
    trim_ids = {entry["id"] for entry in review["trimCandidates"]}

    assert review["runtimeBudgetStatus"] == "over_budget"
    assert nightly_by_id["scenario_quick"]["candidateAction"] == "trim_candidate"
    assert nightly_by_id["code_health"]["candidateAction"] == "trim_candidate"
    assert "nightly.scenario_quick" in trim_ids
    assert "nightly.code_health" in trim_ids


def test_missing_nightly_runtime_keeps_conservative_measure_more() -> None:
    review = audit_validation.build_coverage_review([])
    nightly_by_id = {entry["stepId"]: entry for entry in review["nightlySteps"]}

    assert review["runtimeBudgetStatus"] == "unknown"
    assert nightly_by_id["scenario_quick"]["candidateAction"] == "measure_more"
    assert "runtime is unavailable" in review["decisionSummary"]


def test_coverage_review_keeps_legacy_class_audits_forensic_and_non_required() -> None:
    rows = [
        {
            "task": "fighter-audit-quick",
            "recommendedGateLevel": "forensic",
            "inferredRuntimeClass": "fast",
            "overlapCandidates": ["class-audit-slices"],
        }
    ]

    review = audit_validation.build_coverage_review(rows)
    entry = review["mechanisms"][0]

    assert entry["recommendedPlacement"] == "forensic"
    assert entry["overlapClassification"] == "duplicative"
    assert entry["candidateAction"] == "demote_candidate"


def test_report_payload_and_markdown_include_recommendations(tmp_path: Path) -> None:
    rows = [
        {
            "task": "check-fast",
            "status": "pass",
            "recommendedGateLevel": "inner_loop",
            "validationConfidence": "high",
            "latestStatus": "unreported",
            "inferredRuntimeClass": "unmeasured",
            "reportArtifacts": [],
        },
        {
            "task": "missing-audit",
            "status": "warn",
            "recommendedGateLevel": "checkpoint",
            "validationConfidence": "low",
            "latestStatus": "missing",
            "inferredRuntimeClass": "unknown",
            "reportArtifacts": [],
        },
    ]
    coverage = {
        "wrapperTasks": ["check-fast", "missing-audit"],
        "runbookDirectEquivalentTasks": ["check-fast", "missing-audit"],
        "missingFromWrapper": [],
        "missingRunbookDirectEquivalent": [],
        "undocumentedWrapperTasks": [],
        "unknownWrapperTasks": [],
    }

    payload = audit_validation.build_report_payload(
        context={"generatedAt": "2026-04-28T00:00:00+00:00", "branch": "integration", "commit": "abc123", "gitStatusShort": []},
        rows=rows,
        command_coverage=coverage,
        measure_smoke=False,
        include_heavy=False,
        timeout_seconds=300,
        stale_days=14,
        json_path=tmp_path / "audit_validation.json",
        markdown_path=tmp_path / "audit_validation.md",
    )
    markdown = audit_validation.format_report_markdown(payload)

    assert payload["overallStatus"] == "warn"
    assert payload["recommendations"]["keepInDefaultGate"] == ["check-fast"]
    assert payload["recommendations"]["needsLaterValidation"] == ["missing-audit"]
    assert payload["legacyClassAuditCommands"] == list(audit_validation.LEGACY_CLASS_AUDIT_COMMANDS)
    assert payload["canonicalClassEvidence"]["task"] == "class-audit-slices"
    assert "Audit Validation Report" in markdown
    assert "Needs later validation" in markdown
    assert "Canonical Class Evidence" in markdown


def test_explain_coverage_adds_advisory_review_without_changing_status(tmp_path: Path) -> None:
    rows = [
        {
            "task": "check-fast",
            "status": "pass",
            "recommendedGateLevel": "inner_loop",
            "validationConfidence": "high",
            "latestStatus": "unreported",
            "inferredRuntimeClass": "unmeasured",
            "reportArtifacts": [],
            "overlapCandidates": ["nightly-audit"],
        }
    ]
    coverage = {
        "wrapperTasks": ["check-fast"],
        "runbookDirectEquivalentTasks": ["check-fast"],
        "missingFromWrapper": [],
        "missingRunbookDirectEquivalent": [],
        "undocumentedWrapperTasks": [],
        "unknownWrapperTasks": [],
    }

    payload = audit_validation.build_report_payload(
        context={"generatedAt": "2026-04-28T00:00:00+00:00", "branch": "integration", "commit": "abc123", "gitStatusShort": []},
        rows=rows,
        command_coverage=coverage,
        measure_smoke=False,
        include_heavy=False,
        timeout_seconds=300,
        stale_days=14,
        json_path=tmp_path / "audit_validation.json",
        markdown_path=tmp_path / "audit_validation.md",
        explain_coverage=True,
    )
    markdown = audit_validation.format_report_markdown(payload)

    assert payload["overallStatus"] == "pass"
    assert "coverageReview" in payload
    assert payload["coverageReview"]["mechanisms"][0]["riskAreas"]
    assert "Coverage Redundancy Review" in markdown
    assert "| command | risks | overlap | placement | action | reason |" in markdown


def test_coverage_markdown_includes_nightly_budget_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit_validation, "REPO_ROOT", tmp_path)
    write_nightly_runtime_report(tmp_path, 2256.0)
    rows = [
        {
            "task": "nightly-audit",
            "status": "pass",
            "recommendedGateLevel": "release",
            "validationConfidence": "high",
            "latestStatus": "warn",
            "inferredRuntimeClass": "medium",
            "reportArtifacts": [{"path": "reports/nightly/nightly_audit_latest.json", "exists": True}],
            "overlapCandidates": ["check-fast", "audit-quick", "audit-health"],
        }
    ]
    coverage = {
        "wrapperTasks": ["nightly-audit"],
        "runbookDirectEquivalentTasks": ["nightly-audit"],
        "missingFromWrapper": [],
        "missingRunbookDirectEquivalent": [],
        "undocumentedWrapperTasks": [],
        "unknownWrapperTasks": [],
    }

    payload = audit_validation.build_report_payload(
        context={"generatedAt": "2026-04-28T00:00:00+00:00", "branch": "integration", "commit": "abc123", "gitStatusShort": []},
        rows=rows,
        command_coverage=coverage,
        measure_smoke=False,
        include_heavy=False,
        timeout_seconds=300,
        stale_days=14,
        json_path=tmp_path / "audit_validation.json",
        markdown_path=tmp_path / "audit_validation.md",
        explain_coverage=True,
    )
    markdown = audit_validation.format_report_markdown(payload)

    assert payload["coverageReview"]["runtimeBudgetStatus"] == "pass"
    assert "Nightly runtime budget seconds" in markdown
    assert "Runtime budget status: `pass`" in markdown
    assert "Latest nightly runtime seconds: `2256.0`" in markdown
