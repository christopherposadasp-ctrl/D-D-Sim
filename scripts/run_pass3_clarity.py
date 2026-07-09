from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.content.enemies import ACTIVE_ENEMY_PRESET_IDS
from backend.content.player_loadouts import ACTIVE_PLAYER_PRESET_IDS
from scripts.audit_common import (
    Status,
    build_status_counts,
    collect_git_context,
    load_json_object,
    relative_path,
    write_json_report,
    write_text_report,
)
from scripts.audit_findings import get_active_waivers, get_monitored_findings

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pass3"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "pass3_clarity_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "pass3_clarity_latest.md"
ALLOWED_REPORT_STATUSES = {"pass", "warn", "fail", "skipped", "waived", "monitored"}
STATUS_FIELD_NAMES = {"status", "overallStatus", "reportStatus"}


@dataclass(frozen=True)
class CanonicalReport:
    report_id: str
    path: Path
    report_type: Literal["json", "markdown"]
    required_keys: tuple[str, ...] = ()
    required_text: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandDocRequirement:
    command: str
    direct_tokens: tuple[str, ...]


@dataclass(frozen=True)
class ClarityCheck:
    check_id: str
    area: str
    status: Status
    detail: str
    evidence_path: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "checkId": self.check_id,
            "area": self.area,
            "status": self.status,
            "detail": self.detail,
        }
        if self.evidence_path:
            payload["evidencePath"] = self.evidence_path
        return payload


CANONICAL_REPORTS = (
    CanonicalReport(
        "pass1_readiness",
        REPO_ROOT / "reports" / "pass1" / "pass1_readiness_2026-04-23.md",
        "markdown",
        required_text=("pass1_closed_with_warnings_and_waivers",),
    ),
    CanonicalReport(
        "pass2_stability",
        REPO_ROOT / "reports" / "pass2" / "pass2_stability_latest.json",
        "json",
        required_keys=("overallStatus", "context", "statusCounts", "knownWarnings", "waivers"),
    ),
    CanonicalReport(
        "scenario_audit",
        REPO_ROOT / "reports" / "scenario_audit_latest.json",
        "json",
        required_keys=("rows",),
    ),
    CanonicalReport(
        "rogue_audit",
        REPO_ROOT / "reports" / "rogue_audit" / "rogue_audit_latest.json",
        "json",
        required_keys=("overallStatus",),
    ),
    CanonicalReport(
        "code_health",
        REPO_ROOT / "reports" / "code_health_audit.json",
        "json",
        required_keys=("largestLiveModules", "legacyFrontendImports", "rootArtifacts", "benchmarks"),
    ),
    CanonicalReport(
        "code_health_markdown",
        REPO_ROOT / "reports" / "code_health_audit.md",
        "markdown",
        required_text=("Code Health Audit",),
    ),
    CanonicalReport(
        "mixed_party_class_refresh",
        REPO_ROOT / "reports" / "pass1" / "class_slices" / "martial_mixed_party_refresh_2026-04-23.json",
        "json",
        required_keys=("overallStatus", "statusCounts", "results"),
    ),
)

DOC_REQUIREMENTS = {
    "README.md": (
        "Wizard",
        "rogue-audit-quick",
        "class-audit-slices",
        "nightly-audit",
        "pass2-stability",
        "pass3-clarity",
    ),
    "docs/MASTER_NOTES.md": (
        "Pass 1 closed",
        "Pass 2 stability",
        "warnings and waivers",
    ),
    "docs/CONTENT_BACKLOG.md": (
        "V4.3-C",
        "complete",
        "monster_audit_runner_missing",
    ),
    "docs/AUDIT_RUNBOOK.md": (
        "Pass 1",
        "Pass 2",
        "Pass 3",
        "nightly-audit",
        "pass3-clarity",
    ),
}

COMMAND_REQUIREMENTS = (
    CommandDocRequirement("check-fast", ("ruff check", "pytest")),
    CommandDocRequirement("audit-quick", ("scripts\\run_scenario_audit.py", "scripts/run_scenario_audit.py")),
    CommandDocRequirement("audit-full", ("run_scenario_audit.py", "--full")),
    CommandDocRequirement("audit-health", ("scripts\\run_code_health_audit.py", "scripts/run_code_health_audit.py")),
    CommandDocRequirement("fighter-audit-quick", ("scripts\\run_fighter_audit.py", "scripts/run_fighter_audit.py")),
    CommandDocRequirement("fighter-audit-full", ("run_fighter_audit.py", "--full")),
    CommandDocRequirement("barbarian-audit-quick", ("scripts\\run_barbarian_audit.py", "scripts/run_barbarian_audit.py")),
    CommandDocRequirement("barbarian-audit-full", ("run_barbarian_audit.py", "--full")),
    CommandDocRequirement("rogue-audit-quick", ("scripts\\run_rogue_audit.py", "scripts/run_rogue_audit.py")),
    CommandDocRequirement("rogue-audit-full", ("run_rogue_audit.py", "--full")),
    CommandDocRequirement("class-audit-slices", ("scripts\\run_class_audit_slices.py", "scripts/run_class_audit_slices.py")),
    CommandDocRequirement("behavior-diagnostics", ("scripts\\investigate_smart_vs_dumb.py", "scripts/investigate_smart_vs_dumb.py")),
    CommandDocRequirement("nightly-audit", ("scripts\\run_nightly_audit.py", "scripts/run_nightly_audit.py")),
    CommandDocRequirement("pass2-stability", ("scripts\\run_pass2_stability.py", "scripts/run_pass2_stability.py")),
    CommandDocRequirement("pass3-clarity", ("scripts\\run_pass3_clarity.py", "scripts/run_pass3_clarity.py")),
)


def validate_canonical_report(report: CanonicalReport) -> list[ClarityCheck]:
    if not report.path.exists():
        return [
            ClarityCheck(
                report.report_id,
                "canonicalReports",
                "fail",
                "Canonical report is missing.",
                relative_path(report.path),
            )
        ]

    checks = [
        ClarityCheck(
            f"{report.report_id}_exists",
            "canonicalReports",
            "pass",
            "Canonical report exists.",
            relative_path(report.path),
        )
    ]
    try:
        if report.report_type == "json":
            payload = load_json_object(report.path)
            missing_keys = [key for key in report.required_keys if key not in payload]
            if missing_keys:
                checks.append(
                    ClarityCheck(
                        f"{report.report_id}_shape",
                        "canonicalReports",
                        "fail",
                        f"Report is missing required keys: {', '.join(missing_keys)}.",
                        relative_path(report.path),
                    )
                )
            else:
                checks.append(
                    ClarityCheck(
                        f"{report.report_id}_shape",
                        "canonicalReports",
                        "pass",
                        "Report has the required top-level shape.",
                        relative_path(report.path),
                    )
                )
            checks.extend(validate_status_vocabulary(report.report_id, payload, report.path))
        else:
            text = report.path.read_text(encoding="utf-8")
            missing_text = [token for token in report.required_text if token not in text]
            checks.append(
                ClarityCheck(
                    f"{report.report_id}_text",
                    "canonicalReports",
                    "fail" if missing_text else "pass",
                    (
                        f"Report is missing required text: {', '.join(missing_text)}."
                        if missing_text
                        else "Report contains required text."
                    ),
                    relative_path(report.path),
                )
            )
    except (OSError, ValueError) as error:
        checks.append(
            ClarityCheck(
                f"{report.report_id}_parse",
                "canonicalReports",
                "fail",
                f"Report could not be parsed: {error}",
                relative_path(report.path),
            )
        )
    return checks


def validate_status_vocabulary(report_id: str, payload: Any, report_path: Path) -> list[ClarityCheck]:
    invalid_statuses = sorted(
        {
            value
            for value in iter_status_values(payload)
            if value not in ALLOWED_REPORT_STATUSES
        }
    )
    if invalid_statuses:
        return [
            ClarityCheck(
                f"{report_id}_status_vocabulary",
                "statusVocabulary",
                "fail",
                f"Report uses unsupported status values: {', '.join(invalid_statuses)}.",
                relative_path(report_path),
            )
        ]
    return [
        ClarityCheck(
            f"{report_id}_status_vocabulary",
            "statusVocabulary",
            "pass",
            "Status fields use the supported audit vocabulary.",
            relative_path(report_path),
        )
    ]


def iter_status_values(value: Any) -> list[str]:
    statuses: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in STATUS_FIELD_NAMES and isinstance(child, str):
                statuses.append(child)
            else:
                statuses.extend(iter_status_values(child))
    elif isinstance(value, list):
        for child in value:
            statuses.extend(iter_status_values(child))
    return statuses


def validate_findings_shape(findings: list[dict[str, Any]], waivers: list[dict[str, Any]]) -> list[ClarityCheck]:
    checks: list[ClarityCheck] = []
    checks.extend(validate_unique_ids("monitored_findings", findings))
    checks.extend(validate_unique_ids("active_waivers", waivers))
    finding_required = ("id", "area", "status", "summary", "evidenceReference", "nextAction")
    waiver_required = ("id", "area", "status", "summary", "reason", "alternateEvidence", "retirementCondition")
    checks.extend(validate_required_fields("monitored_findings", findings, finding_required))
    checks.extend(validate_required_fields("active_waivers", waivers, waiver_required))
    return checks


def validate_unique_ids(label: str, rows: list[dict[str, Any]]) -> list[ClarityCheck]:
    ids = [str(row.get("id", "")) for row in rows]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    return [
        ClarityCheck(
            f"{label}_unique_ids",
            "findings",
            "fail" if duplicates else "pass",
            f"Duplicate ids: {', '.join(duplicates)}." if duplicates else "Ids are unique.",
        )
    ]


def validate_required_fields(
    label: str,
    rows: list[dict[str, Any]],
    required_fields: tuple[str, ...],
) -> list[ClarityCheck]:
    missing = [
        f"{row.get('id', '<missing id>')}:{field}"
        for row in rows
        for field in required_fields
        if not row.get(field)
    ]
    return [
        ClarityCheck(
            f"{label}_required_fields",
            "findings",
            "fail" if missing else "pass",
            f"Missing required fields: {', '.join(missing)}." if missing else "Required fields are present.",
        )
    ]


def validate_docs(requirements: dict[str, tuple[str, ...]] = DOC_REQUIREMENTS) -> list[ClarityCheck]:
    checks: list[ClarityCheck] = []
    for relative_doc_path, tokens in requirements.items():
        path = REPO_ROOT / relative_doc_path
        if not path.exists():
            checks.append(ClarityCheck(relative_doc_path, "docs", "fail", "Document is missing.", relative_doc_path))
            continue
        text = path.read_text(encoding="utf-8")
        missing = [token for token in tokens if token not in text]
        checks.append(
            ClarityCheck(
                relative_doc_path,
                "docs",
                "fail" if missing else "pass",
                f"Missing required current-state text: {', '.join(missing)}." if missing else "Document is current.",
                relative_doc_path,
            )
        )
    return checks


def validate_command_docs(
    dev_ps1_text: str,
    runbook_text: str,
    requirements: tuple[CommandDocRequirement, ...] = COMMAND_REQUIREMENTS,
) -> list[ClarityCheck]:
    checks: list[ClarityCheck] = []
    for requirement in requirements:
        command_in_wrapper = requirement.command in dev_ps1_text
        command_in_docs = requirement.command in runbook_text
        direct_token_in_docs = any(token in runbook_text for token in requirement.direct_tokens)
        missing: list[str] = []
        if not command_in_wrapper:
            missing.append("dev.ps1 command")
        if not command_in_docs:
            missing.append("runbook command")
        if not direct_token_in_docs:
            missing.append("direct script equivalent")
        checks.append(
            ClarityCheck(
                f"command_{requirement.command}",
                "runnerConsistency",
                "fail" if missing else "pass",
                f"Missing {', '.join(missing)}." if missing else "Wrapper and runbook command mapping are present.",
            )
        )
    return checks


def determine_overall_status(
    checks: list[dict[str, Any]],
    monitored_findings: list[dict[str, Any]],
    active_waivers: list[dict[str, Any]],
) -> Status:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if monitored_findings or active_waivers:
        return "warn"
    return "pass"


def build_report_payload(
    *,
    context: dict[str, Any],
    checks: list[dict[str, Any]],
    monitored_findings: list[dict[str, Any]],
    active_waivers: list[dict[str, Any]],
    json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    return {
        "overallStatus": determine_overall_status(checks, monitored_findings, active_waivers),
        "context": {
            **context,
            "activeScenarioCount": len(ACTIVE_ENEMY_PRESET_IDS),
            "activePlayerPresetCount": len(ACTIVE_PLAYER_PRESET_IDS),
        },
        "artifactPaths": {
            "json": relative_path(json_path),
            "markdown": relative_path(markdown_path),
        },
        "statusCounts": build_status_counts(checks),
        "canonicalReports": [
            {
                "reportId": report.report_id,
                "path": relative_path(report.path),
                "type": report.report_type,
            }
            for report in CANONICAL_REPORTS
        ],
        "checks": checks,
        "monitoredFindings": monitored_findings,
        "activeWaivers": active_waivers,
        "commandRequirements": [
            {"command": requirement.command, "directTokens": list(requirement.direct_tokens)}
            for requirement in COMMAND_REQUIREMENTS
        ],
    }


def format_report_markdown(payload: dict[str, Any]) -> str:
    context = payload["context"]
    lines = [
        "# Pass 3 Clarity Report",
        "",
        f"- Overall status: `{payload['overallStatus']}`",
        f"- Branch: `{context['branch']}`",
        f"- Commit: `{context['commit']}`",
        f"- Active scenarios: `{context['activeScenarioCount']}`",
        f"- Active player presets: `{context['activePlayerPresetCount']}`",
        f"- JSON report: `{payload['artifactPaths']['json']}`",
        f"- Markdown report: `{payload['artifactPaths']['markdown']}`",
        "",
        "## Check Counts",
        "",
        f"- `{payload['statusCounts']}`",
        "",
        "## Monitored Findings",
        "",
    ]
    if payload["monitoredFindings"]:
        lines.extend(
            f"- `{finding['id']}`: {finding['summary']} Next: {finding['nextAction']}"
            for finding in payload["monitoredFindings"]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Active Waivers", ""])
    if payload["activeWaivers"]:
        lines.extend(
            f"- `{waiver['id']}`: {waiver['summary']} Retirement: {waiver['retirementCondition']}"
            for waiver in payload["activeWaivers"]
        )
    else:
        lines.append("- None.")

    failures = [check for check in payload["checks"] if check["status"] == "fail"]
    lines.extend(["", "## Blockers", ""])
    if failures:
        lines.extend(f"- `{check['checkId']}`: {check['detail']}" for check in failures[:20])
        if len(failures) > 20:
            lines.append(f"- {len(failures) - 20} additional blocker(s) omitted from Markdown summary.")
    else:
        lines.append("- None.")

    lines.extend(["", "## Canonical Reports", ""])
    lines.extend(f"- `{entry['reportId']}`: `{entry['path']}`" for entry in payload["canonicalReports"])
    lines.append("")
    return "\n".join(lines)


def run_clarity_checks() -> list[ClarityCheck]:
    checks: list[ClarityCheck] = []
    for report in CANONICAL_REPORTS:
        checks.extend(validate_canonical_report(report))
    checks.extend(validate_findings_shape(get_monitored_findings(), get_active_waivers()))
    checks.extend(validate_docs())

    dev_ps1_text = (REPO_ROOT / "scripts" / "dev.ps1").read_text(encoding="utf-8")
    runbook_path = REPO_ROOT / "docs" / "AUDIT_RUNBOOK.md"
    runbook_text = runbook_path.read_text(encoding="utf-8") if runbook_path.exists() else ""
    checks.extend(validate_command_docs(dev_ps1_text, runbook_text))
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Pass 3 clarity and audit-maintainability gate.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checks = [check.to_payload() for check in run_clarity_checks()]
    payload = build_report_payload(
        context=collect_git_context(),
        checks=checks,
        monitored_findings=get_monitored_findings(),
        active_waivers=get_active_waivers(),
        json_path=args.json_path,
        markdown_path=args.markdown_path,
    )
    markdown = format_report_markdown(payload)
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, markdown)
    print(f"Wrote {relative_path(args.json_path)}")
    print(f"Wrote {relative_path(args.markdown_path)}")
    print(f"Overall status: {payload['overallStatus']}")
    if payload["overallStatus"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
