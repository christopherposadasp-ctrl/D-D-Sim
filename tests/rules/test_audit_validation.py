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
    assert review["coverageMapSummary"]["riskAreaCount"] == 17
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


def test_coverage_map_assigns_primary_owner_to_every_known_risk_area() -> None:
    coverage_map = audit_validation.build_coverage_map()
    by_risk = {entry["riskArea"]: entry for entry in coverage_map["riskAreaCoverage"]}

    assert set(by_risk) == {
        "rule correctness",
        "focused AI decisions",
        "monster behavior",
        "content integrity",
        "golden drift",
        "API contract",
        "frontend contract",
        "scenario behavior",
        "class behavior",
        "Rogue behavior",
        "determinism",
        "async reliability",
        "code health",
        "benchmark diagnostics",
        "docs/runbook consistency",
        "report freshness",
        "forensic traces",
    }
    assert all(entry["primaryOwner"] for entry in by_risk.values())
    assert by_risk["rule correctness"]["primaryOwner"] == "unit/rules tests"
    assert by_risk["benchmark diagnostics"]["overlapPolicy"] == "needs_canary"
    assert coverage_map["summary"]["primaryPhase3CanaryTarget"] == "monster_benchmarks_vs_audit_health"


def test_coverage_map_distinguishes_intentional_overlap_from_duplicates_and_canaries() -> None:
    coverage_map = audit_validation.build_coverage_map()
    by_group = {entry["groupId"]: entry for entry in coverage_map["overlapGroups"]}
    decisions = {entry["id"]: entry for entry in coverage_map["candidateDecisions"]}

    assert by_group["goldens_vs_pass2"]["overlapPolicy"] == "intentional"
    assert by_group["goldens_vs_pass2"]["primaryOwner"] == "Pass 2 stability"
    assert by_group["segmented_vs_monolithic_class_audits"]["overlapPolicy"] == "candidate_duplicate"
    assert by_group["segmented_vs_monolithic_class_audits"]["primaryOwner"] == "class-audit-slices"
    assert by_group["monster_benchmarks_vs_audit_health"]["overlapPolicy"] == "needs_canary"
    assert decisions["segmented_vs_monolithic_class_audits"]["recommendedAction"] == "demote_candidate"
    assert decisions["monster_benchmarks_vs_audit_health"]["recommendedAction"] == "canary_validate"
    assert "different failure modes" in decisions["monster_benchmarks_vs_audit_health"]["rationale"]


def test_monster_benchmark_canary_validation_maps_expected_capabilities() -> None:
    validation = audit_validation.build_monster_benchmark_canary_validation()
    canaries = {entry["canaryId"]: entry for entry in validation["canaries"]}
    mechanisms = {entry["mechanismId"]: entry for entry in validation["mechanisms"]}

    assert validation["target"] == "monster_benchmarks_vs_audit_health"
    assert validation["preliminaryDecision"]["status"] == "do_not_trim_yet"
    assert set(canaries) == {
        "benchmark_preset_layout_broken",
        "monster_primary_behavior_drift",
        "benchmark_batch_health_invalid",
        "code_health_benchmark_runtime_regression",
        "root_artifact_or_large_module_regression",
    }
    assert set(mechanisms) == {
        "pytest_non_slow",
        "pytest_slow_monster_benchmarks",
        "audit_health",
        "nightly_code_health",
    }
    assert canaries["benchmark_preset_layout_broken"]["expectedCatchers"] == ["pytest_non_slow"]
    assert "audit_health" in canaries["benchmark_preset_layout_broken"]["expectedNonCatchers"]
    assert canaries["code_health_benchmark_runtime_regression"]["expectedCatchers"] == [
        "audit_health",
        "nightly_code_health",
    ]


def test_test_signal_review_flags_low_signal_patterns_without_removing_tests() -> None:
    full = make_collection(
        [
            "tests/rules/test_ai.py::test_level5_fighter_opens_with_dash_then_action_surge_extra_attack_from_default_layout",
            "tests/rules/test_monster_benchmarks.py::test_monster_benchmark_batches_report_health_metrics[wolf]",
            "tests/rules/test_monster_benchmarks.py::test_benchmark_presets_build_valid_layout_and_emit_first_step[wolf]",
            "tests/golden/test_python_goldens.py::test_python_run_cases_match_python_goldens",
            "tests/rules/test_rules.py::test_rage_activation_consumes_a_use_and_grants_temp_hp",
        ]
    )
    not_slow = make_collection(
        [
            "tests/rules/test_ai.py::test_level5_fighter_opens_with_dash_then_action_surge_extra_attack_from_default_layout",
            "tests/rules/test_monster_benchmarks.py::test_benchmark_presets_build_valid_layout_and_emit_first_step[wolf]",
            "tests/golden/test_python_goldens.py::test_python_run_cases_match_python_goldens",
            "tests/rules/test_rules.py::test_rage_activation_consumes_a_use_and_grants_temp_hp",
        ],
        total_count=5,
        deselected_count=1,
    )

    review = audit_validation.build_test_signal_review(full, not_slow)
    by_name = {row["testName"]: row for row in review["reviewRows"]}

    assert review["status"] == "advisory"
    assert "candidate_remove_after_canary" not in review["summary"]["candidateActionCounts"]
    assert by_name["test_level5_fighter_opens_with_dash_then_action_surge_extra_attack_from_default_layout"][
        "candidateAction"
    ] == "rewrite_behavior_level"
    assert by_name["test_monster_benchmark_batches_report_health_metrics"]["candidateAction"] == "demote_to_checkpoint"
    assert by_name["test_python_run_cases_match_python_goldens"]["candidateAction"] == "keep"
    assert "Do not remove" in review["decisionRule"]


def test_test_coverage_ledger_includes_unmeasured_monster_benchmark_runtime_by_default(tmp_path: Path) -> None:
    full = make_collection(["tests/rules/test_monster_benchmarks.py::test_benchmark_presets_build_valid_layout_and_emit_first_step[wolf]"])
    not_slow = make_collection(["tests/rules/test_monster_benchmarks.py::test_benchmark_presets_build_valid_layout_and_emit_first_step[wolf]"])

    payload = audit_validation.build_test_coverage_ledger(
        context={"branch": "integration", "commit": "abc123", "generatedAt": "now", "gitStatusShort": []},
        full_collection=full,
        not_slow_collection=not_slow,
        json_path=tmp_path / "ledger.json",
        markdown_path=tmp_path / "ledger.md",
    )
    markdown = audit_validation.format_test_coverage_ledger_markdown(payload)

    assert payload["monsterBenchmarkRuntime"]["status"] == "not_measured"
    assert {entry["sliceId"] for entry in payload["monsterBenchmarkRuntime"]["slices"]} == {
        "benchmark_structure_non_slow",
        "benchmark_batch_health_slow",
        "benchmark_primary_behavior_slow",
    }
    assert "Monster Benchmark Runtime Slices" in markdown
    assert "`not_measured`" in markdown


def test_test_coverage_ledger_can_include_measured_monster_benchmark_runtime(tmp_path: Path) -> None:
    full = make_collection(["tests/rules/test_monster_benchmarks.py::test_benchmark_presets_build_valid_layout_and_emit_first_step[wolf]"])
    not_slow = make_collection(["tests/rules/test_monster_benchmarks.py::test_benchmark_presets_build_valid_layout_and_emit_first_step[wolf]"])
    runtime = {
        "target": "tests/rules/test_monster_benchmarks.py",
        "status": "pass",
        "totalElapsedSeconds": 12.5,
        "slowestSliceId": "benchmark_batch_health_slow",
        "interpretation": "sample interpretation",
        "slices": [
            {
                "sliceId": "benchmark_batch_health_slow",
                "label": "Benchmark batch health metrics",
                "nodeId": "tests/rules/test_monster_benchmarks.py::test_monster_benchmark_batches_report_health_metrics",
                "signal": "aggregate sanity",
                "candidateAction": "demote_to_checkpoint",
                "status": "pass",
                "elapsedSeconds": 12.5,
            }
        ],
    }

    payload = audit_validation.build_test_coverage_ledger(
        context={"branch": "integration", "commit": "abc123", "generatedAt": "now", "gitStatusShort": []},
        full_collection=full,
        not_slow_collection=not_slow,
        monster_benchmark_runtime=runtime,
        json_path=tmp_path / "ledger.json",
        markdown_path=tmp_path / "ledger.md",
    )
    markdown = audit_validation.format_test_coverage_ledger_markdown(payload)

    assert payload["monsterBenchmarkRuntime"]["totalElapsedSeconds"] == 12.5
    assert payload["monsterBenchmarkRuntime"]["slowestSliceId"] == "benchmark_batch_health_slow"
    assert "benchmark_batch_health_slow" in markdown
    assert "12.5" in markdown


def test_parse_pytest_collection_extracts_selected_and_deselected_counts() -> None:
    collection = audit_validation.parse_pytest_collection(
        "\n".join(
            [
                "tests/rules/test_rules.py::test_one",
                "tests/rules/test_ai.py::test_two",
                "2/4 tests collected (2 deselected) in 0.10s",
            ]
        ),
        ["py", "-m", "pytest", "--collect-only"],
        0.1,
    )

    assert collection.total_count == 4
    assert collection.selected_count == 2
    assert collection.deselected_count == 2
    assert collection.node_ids == ("tests/rules/test_rules.py::test_one", "tests/rules/test_ai.py::test_two")


def make_collection(node_ids: list[str], total_count: int | None = None, deselected_count: int = 0) -> audit_validation.PytestCollection:
    return audit_validation.PytestCollection(
        command=["py", "-m", "pytest", "--collect-only"],
        status="pass",
        total_count=total_count if total_count is not None else len(node_ids),
        selected_count=len(node_ids),
        deselected_count=deselected_count,
        node_ids=tuple(node_ids),
        elapsed_seconds=0.1,
        output_tail=(),
    )


def test_pytest_file_rows_group_counts_risks_and_overlap() -> None:
    full = make_collection(
        [
            "tests/rules/test_rules.py::test_core_rule",
            "tests/rules/test_monster_benchmarks.py::test_variant[wolf]",
            "tests/rules/test_monster_benchmarks.py::test_variant[goblin]",
            "tests/golden/test_python_goldens.py::test_python_run_cases_match_python_goldens",
            "tests/integration/test_api.py::test_health_endpoint_returns_ok",
        ]
    )
    not_slow = make_collection(
        [
            "tests/rules/test_rules.py::test_core_rule",
            "tests/rules/test_monster_benchmarks.py::test_variant[wolf]",
            "tests/golden/test_python_goldens.py::test_python_run_cases_match_python_goldens",
            "tests/integration/test_api.py::test_health_endpoint_returns_ok",
        ],
        total_count=5,
        deselected_count=1,
    )

    rows = audit_validation.build_pytest_file_rows(full, not_slow)
    by_path = {row["path"]: row for row in rows}

    assert by_path["tests/rules/test_monster_benchmarks.py"]["totalCount"] == 2
    assert by_path["tests/rules/test_monster_benchmarks.py"]["slowDeselectedCount"] == 1
    assert by_path["tests/rules/test_monster_benchmarks.py"]["parametrizedItemCount"] == 2
    assert by_path["tests/rules/test_monster_benchmarks.py"]["candidateAction"] == "measure_more"
    assert by_path["tests/golden/test_python_goldens.py"]["overlapWith"] == ["pass2-stability"]
    assert "API contract" in by_path["tests/integration/test_api.py"]["riskAreas"]


def test_test_coverage_ledger_records_inventory_and_canary_specs(tmp_path: Path) -> None:
    full = make_collection(
        [
            "tests/rules/test_rules.py::test_core_rule",
            "tests/golden/test_python_goldens.py::test_python_run_cases_match_python_goldens",
        ]
    )
    not_slow = make_collection(["tests/rules/test_rules.py::test_core_rule"], total_count=2, deselected_count=1)

    payload = audit_validation.build_test_coverage_ledger(
        context={"branch": "integration", "commit": "abc123", "generatedAt": "now", "gitStatusShort": []},
        full_collection=full,
        not_slow_collection=not_slow,
        mechanism_rows=[
            {
                "task": "pass2-stability",
                "recommendedGateLevel": "release",
                "inferredRuntimeClass": "slow",
                "overlapCandidates": ["check-fast"],
            }
        ],
        json_path=tmp_path / "ledger.json",
        markdown_path=tmp_path / "ledger.md",
    )
    markdown = audit_validation.format_test_coverage_ledger_markdown(payload)

    assert payload["overallStatus"] == "pass"
    assert payload["summary"]["totalCollected"] == 2
    assert payload["summary"]["notSlowSelected"] == 1
    assert payload["summary"]["notSlowDeselected"] == 1
    assert {spec["mechanism"] for spec in payload["canarySpecs"]} == {
        "unit/rules tests",
        "golden tests",
        "scenario audits",
        "class audits",
        "Pass 2 stability",
    }
    assert payload["auditMechanisms"][0]["task"] == "pass2-stability"
    assert payload["auditMechanisms"][0]["riskAreas"] == ["determinism", "async reliability"]
    assert payload["coverageMapSummary"]["riskAreaCount"] == 17
    assert payload["coverageMapSummary"]["needsCanary"] == ["monster_benchmarks_vs_audit_health"]
    assert payload["canaryValidation"]["preliminaryDecision"]["status"] == "do_not_trim_yet"
    assert payload["testSignalReview"]["status"] == "advisory"
    assert payload["testSignalReview"]["summary"]["reviewedTestCount"] == 2
    assert payload["monsterBenchmarkRuntime"]["status"] == "not_measured"
    assert "Test Coverage Ledger" in markdown
    assert "Audit Mechanisms" in markdown
    assert "Risk Ownership" in markdown
    assert "Overlap Groups" in markdown
    assert "Canary Validation: Monster Benchmarks vs Audit Health" in markdown
    assert "Capability Table" in markdown
    assert "Test Signal Review" in markdown
    assert "Top Signal Review Candidates" in markdown
    assert "Monster Benchmark Runtime Slices" in markdown
    assert "Canary Specs" in markdown


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


def test_report_payload_links_test_coverage_ledger_when_supplied(tmp_path: Path) -> None:
    ledger = {
        "overallStatus": "pass",
        "artifactPaths": {"json": "reports/audit_validation/test_coverage_ledger_latest.json", "markdown": "reports/audit_validation/test_coverage_ledger_latest.md"},
        "summary": {"totalCollected": 1329, "notSlowSelected": 1187, "notSlowDeselected": 142, "fileCount": 28},
    }
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
        rows=[],
        command_coverage=coverage,
        measure_smoke=False,
        include_heavy=False,
        timeout_seconds=300,
        stale_days=14,
        json_path=tmp_path / "audit_validation.json",
        markdown_path=tmp_path / "audit_validation.md",
        explain_coverage=True,
        test_coverage_ledger=ledger,
    )
    markdown = audit_validation.format_report_markdown(payload)

    assert payload["testCoverageLedger"]["totalCollected"] == 1329
    assert "Test Coverage Ledger" in markdown
    assert "Not-slow deselected: `142`" in markdown


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
