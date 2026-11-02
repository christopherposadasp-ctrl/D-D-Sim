from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_common, audit_findings, run_pass3_clarity


def test_audit_common_report_helpers_round_trip_json_and_count_statuses(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    payload = {"overallStatus": "warn", "rows": [{"status": "pass"}, {"status": "fail"}]}

    audit_common.write_json_report(report_path, payload)

    assert audit_common.load_json_object(report_path) == payload
    assert audit_common.build_status_counts(payload["rows"]) == {
        "pass": 1,
        "warn": 0,
        "fail": 1,
        "skipped": 0,
    }


def test_audit_common_output_tail_and_json_errors(tmp_path: Path) -> None:
    assert audit_common.text_tail("a\n\nb\nc", limit=2) == ["b", "c"]

    missing_path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        audit_common.load_json_object(missing_path)

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(["not", "object"]), encoding="utf-8")
    with pytest.raises(ValueError):
        audit_common.load_json_object(bad_path)


def test_audit_findings_have_unique_ids_and_required_fields() -> None:
    findings = audit_findings.get_monitored_findings()
    waivers = audit_findings.get_active_waivers()
    checks = run_pass3_clarity.validate_findings_shape(findings, waivers)

    assert {check.status for check in checks} == {"pass"}
    assert len({finding["id"] for finding in findings}) == len(findings)
    assert len({waiver["id"] for waiver in waivers}) == len(waivers)


def test_pass3_missing_canonical_report_is_a_failure(tmp_path: Path) -> None:
    checks = run_pass3_clarity.validate_canonical_report(
        run_pass3_clarity.CanonicalReport(
            "missing_report",
            tmp_path / "missing.json",
            "json",
            required_keys=("overallStatus",),
        )
    )

    assert checks[0].status == "fail"
    assert "missing" in checks[0].detail.lower()


def test_pass3_rejects_unknown_report_status(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    payload = {"overallStatus": "complete", "rows": [{"status": "pass"}]}
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    checks = run_pass3_clarity.validate_canonical_report(
        run_pass3_clarity.CanonicalReport("bad_status", report_path, "json", required_keys=("overallStatus",))
    )

    status_check = next(check for check in checks if check.check_id == "bad_status_status_vocabulary")
    assert status_check.status == "fail"
    assert "complete" in status_check.detail


def test_pass3_missing_doc_text_is_a_failure() -> None:
    checks = run_pass3_clarity.validate_docs({"docs/DOES_NOT_EXIST.md": ("required text",)})

    assert checks == [
        run_pass3_clarity.ClarityCheck(
            "docs/DOES_NOT_EXIST.md",
            "docs",
            "fail",
            "Document is missing.",
            "docs/DOES_NOT_EXIST.md",
        )
    ]


def test_pass3_known_findings_and_waivers_produce_warn_not_fail() -> None:
    status = run_pass3_clarity.determine_overall_status(
        checks=[{"status": "pass"}],
        monitored_findings=[{"id": "finding"}],
        active_waivers=[{"id": "waiver"}],
    )

    assert status == "warn"


def test_pass3_report_payload_and_markdown_include_artifacts_and_waivers(tmp_path: Path) -> None:
    payload = run_pass3_clarity.build_report_payload(
        context={
            "generatedAt": "2026-04-23T12:00:00+00:00",
            "branch": "integration",
            "commit": "b227375",
            "gitStatusShort": [],
        },
        checks=[{"checkId": "docs", "area": "docs", "status": "pass", "detail": "ok"}],
        monitored_findings=audit_findings.get_monitored_findings(),
        active_waivers=audit_findings.get_active_waivers(),
        json_path=tmp_path / "pass3.json",
        markdown_path=tmp_path / "pass3.md",
    )

    markdown = run_pass3_clarity.format_report_markdown(payload)

    assert payload["overallStatus"] == "warn"
    assert payload["context"]["branch"] == "integration"
    assert "pass3.json" in payload["artifactPaths"]["json"]
    assert "monster_audit_runner_missing" in {waiver["id"] for waiver in payload["activeWaivers"]}
    assert "Overall status: `warn`" in markdown
    assert "Canonical Reports" in markdown
