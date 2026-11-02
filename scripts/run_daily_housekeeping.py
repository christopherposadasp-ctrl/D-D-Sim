from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_common import collect_git_context, write_json_report, write_text_report

HousekeepingStatus = Literal["clean", "safeProposed", "needsReview", "blocked"]
FindingSeverity = Literal["info", "warn", "fail"]

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "housekeeping"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "daily_housekeeping_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "daily_housekeeping_latest.md"
DOC_PATHS = (
    "README.md",
    "docs/MASTER_NOTES.md",
    "docs/CONTENT_BACKLOG.md",
    "docs/V4_ARCHITECTURE.md",
    "docs/AUDIT_RUNBOOK.md",
    "docs/PLAYER_CLASS_IMPLEMENTATION.md",
)
SAFE_TRACKED_PREFIXES = ("docs/", "tests/")
SAFE_TRACKED_FILES = {"README.md", "scripts/dev.ps1"}
SUSPICIOUS_SUFFIXES = (
    ".xlsx",
    ".xls",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".zip",
    ".pyc",
)
CONFLICT_STATUSES = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}


@dataclass(frozen=True)
class GitStatusEntry:
    status_code: str
    path: str
    original_path: str | None = None

    @property
    def index_status(self) -> str:
        return self.status_code[0]

    @property
    def worktree_status(self) -> str:
        return self.status_code[1]

    @property
    def is_ignored(self) -> bool:
        return self.status_code == "!!"

    @property
    def is_untracked(self) -> bool:
        return self.status_code == "??"

    @property
    def is_staged(self) -> bool:
        return self.index_status not in {" ", "?", "!"}

    @property
    def is_unstaged(self) -> bool:
        return self.worktree_status not in {" ", "?", "!"}

    @property
    def has_conflict(self) -> bool:
        return self.status_code in CONFLICT_STATUSES or "U" in self.status_code

    @property
    def staged_and_unstaged(self) -> bool:
        return self.is_staged and self.is_unstaged


@dataclass(frozen=True)
class HousekeepingFinding:
    severity: FindingSeverity
    section: str
    message: str
    path: str | None = None
    recommendation: str | None = None


@dataclass(frozen=True)
class RepoClassification:
    status: HousekeepingStatus
    reasons: list[str]
    files_to_stage: list[str]
    files_to_avoid: list[str]


def run_command(args: list[str], repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": " ".join(args),
        "exitCode": completed.returncode,
        "status": "pass" if completed.returncode == 0 else "fail",
        "stdoutTail": [line for line in completed.stdout.splitlines() if line.strip()][-12:],
        "stderrTail": [line for line in completed.stderr.splitlines() if line.strip()][-12:],
    }


def parse_porcelain_status(output: str) -> list[GitStatusEntry]:
    entries: list[GitStatusEntry] = []
    for raw_line in output.splitlines():
        if not raw_line:
            continue
        status_code = raw_line[:2]
        path_text = raw_line[3:] if len(raw_line) > 3 else ""
        original_path: str | None = None
        if " -> " in path_text:
            original_path, path_text = path_text.split(" -> ", 1)
        entries.append(GitStatusEntry(status_code=status_code, path=path_text.replace("\\", "/"), original_path=original_path))
    return entries


def is_safe_tracked_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in SAFE_TRACKED_FILES or normalized.startswith(SAFE_TRACKED_PREFIXES)


def is_suspicious_path(path: str) -> bool:
    normalized = path.lower().replace("\\", "/")
    return normalized.endswith(SUSPICIOUS_SUFFIXES)


def classify_repo_state(entries: list[GitStatusEntry]) -> RepoClassification:
    active_entries = [entry for entry in entries if not entry.is_ignored]
    if not active_entries:
        return RepoClassification(status="clean", reasons=[], files_to_stage=[], files_to_avoid=[])

    reasons: list[str] = []
    files_to_stage: list[str] = []
    files_to_avoid: list[str] = []

    for entry in active_entries:
        if entry.has_conflict:
            reasons.append(f"Merge conflict status {entry.status_code} on {entry.path}.")
            files_to_avoid.append(entry.path)
        elif entry.staged_and_unstaged:
            reasons.append(f"{entry.path} has both staged and unstaged edits.")
            files_to_avoid.append(entry.path)
        elif entry.is_untracked:
            reasons.append(f"{entry.path} is untracked and needs review before any commit recommendation.")
            files_to_avoid.append(entry.path)
        elif is_suspicious_path(entry.path):
            reasons.append(f"{entry.path} has a binary/generated-looking extension.")
            files_to_avoid.append(entry.path)
        elif not is_safe_tracked_path(entry.path):
            reasons.append(f"{entry.path} is outside docs/admin/test-only safe paths.")
            files_to_avoid.append(entry.path)
        else:
            files_to_stage.append(entry.path)

    if any(entry.has_conflict for entry in active_entries):
        return RepoClassification(
            status="blocked",
            reasons=reasons,
            files_to_stage=sorted(set(files_to_stage)),
            files_to_avoid=sorted(set(files_to_avoid)),
        )

    if files_to_avoid:
        return RepoClassification(
            status="needsReview",
            reasons=reasons,
            files_to_stage=sorted(set(files_to_stage)),
            files_to_avoid=sorted(set(files_to_avoid)),
        )

    return RepoClassification(
        status="safeProposed",
        reasons=["Only docs/admin/test tracked changes were detected."],
        files_to_stage=sorted(set(files_to_stage)),
        files_to_avoid=[],
    )


def extract_dev_tasks(dev_ps1_text: str) -> list[str]:
    match = re.search(r"ValidateSet\((.*?)\)\]\s*\[string\]\$Task", dev_ps1_text, flags=re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def find_missing_doc_tasks(dev_tasks: list[str], readme_text: str, audit_runbook_text: str) -> list[HousekeepingFinding]:
    findings: list[HousekeepingFinding] = []
    for task in dev_tasks:
        missing_paths = []
        if task not in readme_text:
            missing_paths.append("README.md")
        if task not in audit_runbook_text:
            missing_paths.append("docs/AUDIT_RUNBOOK.md")
        if missing_paths:
            findings.append(
                HousekeepingFinding(
                    severity="warn",
                    section="docDrift",
                    path=", ".join(missing_paths),
                    message=f"`{task}` exists in scripts/dev.ps1 but is missing from {', '.join(missing_paths)}.",
                    recommendation="Update the command list or intentionally document why it is omitted.",
                )
            )
    return findings


def find_class_support_drift(class_support: dict[str, int], docs_text: str) -> list[HousekeepingFinding]:
    lower_docs = docs_text.lower()
    findings: list[HousekeepingFinding] = []
    for display_name, max_level in sorted(class_support.items()):
        class_name = display_name.lower()
        accepted_fragments = (
            f"{class_name} supported to level {max_level}",
            f"{class_name} is live through level {max_level}",
            f"{class_name} is live to level {max_level}",
            f"{class_name} live to level {max_level}",
        )
        if not any(fragment in lower_docs for fragment in accepted_fragments):
            findings.append(
                HousekeepingFinding(
                    severity="warn",
                    section="docDrift",
                    message=f"Docs do not appear to state `{display_name}` support through level {max_level}.",
                    recommendation="Update the live class-support snapshot if the backend registry is authoritative.",
                )
            )
    return findings


def find_default_party_drift(
    default_player_preset_id: str,
    party_members: list[dict[str, Any]],
    docs_text: str,
) -> list[HousekeepingFinding]:
    lower_docs = docs_text.lower()
    findings: list[HousekeepingFinding] = []
    if default_player_preset_id.lower() not in lower_docs:
        findings.append(
            HousekeepingFinding(
                severity="warn",
                section="docDrift",
                message=f"Docs do not mention default player preset `{default_player_preset_id}`.",
                recommendation="Update the default party section in project docs.",
            )
        )

    for member in party_members:
        class_name = str(member["classDisplayName"]).lower()
        level = int(member["level"])
        member_patterns = (
            rf"level\s+{level}[^\n.:-]*{re.escape(class_name)}",
            rf"{re.escape(class_name)}[^\n.:-]*level\s+{level}",
        )
        if not any(re.search(pattern, lower_docs) for pattern in member_patterns):
            findings.append(
                HousekeepingFinding(
                    severity="warn",
                    section="docDrift",
                    message=f"Docs do not appear to mention the default-party member `{member['unitId']}` as level {level} {member['classDisplayName']}.",
                    recommendation="Update the default player preset description if the registry is authoritative.",
                )
            )
    return findings


def find_party_validation_drift(scenario_ids: tuple[str, ...], docs_text: str) -> list[HousekeepingFinding]:
    lower_docs = docs_text.lower()
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id.lower() not in lower_docs]
    if not missing:
        return []
    return [
        HousekeepingFinding(
            severity="warn",
            section="docDrift",
            message=f"Docs do not mention focused party-validation scenarios: {', '.join(missing)}.",
            recommendation="Update README.md and docs/AUDIT_RUNBOOK.md if the script defaults changed.",
        )
    ]


def get_live_class_support() -> dict[str, int]:
    from backend.content.class_definitions import CLASS_DEFINITIONS

    return {
        class_definition.display_name: class_definition.max_supported_level
        for class_definition in CLASS_DEFINITIONS.values()
    }


def get_default_party_snapshot() -> tuple[str, list[dict[str, Any]]]:
    from backend.content.class_definitions import get_class_definition
    from backend.content.player_loadouts import DEFAULT_PLAYER_PRESET_ID, get_player_loadout, get_player_preset

    preset = get_player_preset(DEFAULT_PLAYER_PRESET_ID)
    members: list[dict[str, Any]] = []
    for unit in preset.units:
        loadout = get_player_loadout(unit.loadout_id)
        class_display_name = get_class_definition(loadout.class_id).display_name
        members.append(
            {
                "unitId": unit.unit_id,
                "loadoutId": unit.loadout_id,
                "classId": loadout.class_id,
                "classDisplayName": class_display_name,
                "level": loadout.level,
                "displayName": loadout.display_name,
            }
        )
    return DEFAULT_PLAYER_PRESET_ID, members


def get_party_validation_defaults() -> tuple[str, tuple[str, ...]]:
    from scripts.run_party_validation import DEFAULT_PLAYER_BEHAVIOR, DEFAULT_SCENARIO_IDS

    return DEFAULT_PLAYER_BEHAVIOR, DEFAULT_SCENARIO_IDS


def read_text_file(repo_root: Path, relative_path: str) -> str:
    return (repo_root / relative_path).read_text(encoding="utf-8")


def build_doc_drift_findings(repo_root: Path = REPO_ROOT) -> list[HousekeepingFinding]:
    findings: list[HousekeepingFinding] = []
    missing_docs = [path for path in DOC_PATHS if not (repo_root / path).exists()]
    for path in missing_docs:
        findings.append(
            HousekeepingFinding(
                severity="fail",
                section="docDrift",
                path=path,
                message=f"Required project doc `{path}` is missing.",
                recommendation="Restore the required doc before making housekeeping recommendations.",
            )
        )
    if missing_docs:
        return findings

    docs_by_path = {path: read_text_file(repo_root, path) for path in DOC_PATHS}
    all_docs_text = "\n".join(docs_by_path.values())

    dev_ps1_path = repo_root / "scripts" / "dev.ps1"
    if not dev_ps1_path.exists():
        return [
            HousekeepingFinding(
                severity="fail",
                section="docDrift",
                path="scripts/dev.ps1",
                message="scripts/dev.ps1 is missing.",
                recommendation="Restore the PowerShell command wrapper before checking docs.",
            )
        ]

    dev_tasks = extract_dev_tasks(dev_ps1_path.read_text(encoding="utf-8"))
    findings.extend(find_missing_doc_tasks(dev_tasks, docs_by_path["README.md"], docs_by_path["docs/AUDIT_RUNBOOK.md"]))

    try:
        findings.extend(find_class_support_drift(get_live_class_support(), all_docs_text))
        preset_id, party_members = get_default_party_snapshot()
        findings.extend(find_default_party_drift(preset_id, party_members, all_docs_text))
        _, party_validation_scenarios = get_party_validation_defaults()
        findings.extend(find_party_validation_drift(party_validation_scenarios, all_docs_text))
    except Exception as error:  # pragma: no cover - defensive report path
        findings.append(
            HousekeepingFinding(
                severity="fail",
                section="docDrift",
                message=f"Could not derive live registry snapshots: {error}",
                recommendation="Fix import/runtime errors before relying on doc drift checks.",
            )
        )

    return findings


def get_git_status_entries(repo_root: Path = REPO_ROOT, *, include_ignored: bool = False) -> list[GitStatusEntry]:
    args = ["git", "status", "--porcelain=v1"]
    if include_ignored:
        args.append("--ignored")
    completed = subprocess.run(
        args,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git status failed")
    return parse_porcelain_status(completed.stdout)


def build_commit_recommendation(classification: RepoClassification, doc_findings: list[HousekeepingFinding]) -> dict[str, Any]:
    if classification.status != "safeProposed":
        return {
            "recommended": False,
            "message": None,
            "filesToStage": classification.files_to_stage,
            "filesToAvoid": classification.files_to_avoid,
            "reason": "Worktree is not safe for an automatic commit proposal.",
        }

    if any(finding.severity == "fail" for finding in doc_findings):
        return {
            "recommended": False,
            "message": None,
            "filesToStage": classification.files_to_stage,
            "filesToAvoid": classification.files_to_avoid,
            "reason": "Doc drift checks have blocking failures.",
        }

    if all(path.startswith("tests/") for path in classification.files_to_stage):
        message = "Update focused test coverage"
    elif any(path.startswith("docs/") or path == "README.md" for path in classification.files_to_stage):
        message = "Update project documentation"
    else:
        message = "Update project housekeeping"

    return {
        "recommended": True,
        "message": message,
        "filesToStage": classification.files_to_stage,
        "filesToAvoid": [],
        "reason": "Only safe docs/admin/test tracked changes were detected.",
    }


def run_lightweight_validation(classification: RepoClassification, repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    results = [run_command(["git", "status", "--short"], repo_root)]
    if classification.status == "safeProposed" and classification.files_to_stage:
        results.append(run_command(["git", "diff", "--check", "--", *classification.files_to_stage], repo_root))
    return results


def determine_overall_status(
    classification: RepoClassification,
    doc_findings: list[HousekeepingFinding],
    validation_results: list[dict[str, Any]],
) -> HousekeepingStatus:
    if classification.status == "blocked":
        return "blocked"
    if any(finding.severity == "fail" for finding in doc_findings):
        return "blocked"
    if any(result["status"] == "fail" for result in validation_results):
        return "blocked"
    return classification.status


def build_report(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    status_entries = get_git_status_entries(repo_root)
    ignored_entries = [entry for entry in get_git_status_entries(repo_root, include_ignored=True) if entry.is_ignored]
    classification = classify_repo_state(status_entries)
    doc_findings = build_doc_drift_findings(repo_root)
    validation_results = run_lightweight_validation(classification, repo_root)
    overall_status = determine_overall_status(classification, doc_findings, validation_results)
    commit_recommendation = build_commit_recommendation(classification, doc_findings)

    return {
        "overallStatus": overall_status,
        "generatedContext": collect_git_context(repo_root),
        "repoClassification": asdict(classification),
        "trackedChanges": [asdict(entry) for entry in status_entries],
        "ignoredGenerated": [entry.path for entry in ignored_entries],
        "docDriftFindings": [asdict(finding) for finding in doc_findings],
        "validationResults": validation_results,
        "suggestedCommit": commit_recommendation,
        "followUpCommands": build_follow_up_commands(commit_recommendation),
    }


def build_follow_up_commands(commit_recommendation: dict[str, Any]) -> list[str]:
    commands = [
        r".\scripts\dev.ps1 check-fast",
        r".\scripts\dev.ps1 party-validation",
    ]
    if commit_recommendation.get("recommended"):
        files = " ".join(commit_recommendation["filesToStage"])
        message = commit_recommendation["message"]
        commands.extend(
            [
                f"git add {files}",
                f'git commit -m "{message}"',
            ]
        )
    return commands


def format_markdown_report(payload: dict[str, Any]) -> str:
    classification = payload["repoClassification"]
    suggested_commit = payload["suggestedCommit"]
    lines = [
        "# Daily Housekeeping",
        "",
        f"- overallStatus: `{payload['overallStatus']}`",
        f"- branch: `{payload['generatedContext']['branch']}`",
        f"- commit: `{payload['generatedContext']['commit']}`",
        f"- repoStatus: `{classification['status']}`",
        "",
        "## Worktree",
        "",
    ]

    if payload["trackedChanges"]:
        for entry in payload["trackedChanges"]:
            lines.append(f"- `{entry['status_code']}` `{entry['path']}`")
    else:
        lines.append("- clean")

    lines.extend(["", "## Ignored Generated Artifacts", ""])
    if payload["ignoredGenerated"]:
        for path in payload["ignoredGenerated"][:25]:
            lines.append(f"- `{path}`")
        if len(payload["ignoredGenerated"]) > 25:
            lines.append(f"- ... {len(payload['ignoredGenerated']) - 25} more")
    else:
        lines.append("- none")

    lines.extend(["", "## Doc Drift", ""])
    if payload["docDriftFindings"]:
        for finding in payload["docDriftFindings"]:
            path = f" `{finding['path']}`" if finding.get("path") else ""
            lines.append(f"- `{finding['severity']}`{path}: {finding['message']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Suggested Commit", ""])
    lines.append(f"- recommended: `{suggested_commit['recommended']}`")
    if suggested_commit.get("message"):
        lines.append(f"- message: `{suggested_commit['message']}`")
    lines.append(f"- reason: {suggested_commit['reason']}")
    if suggested_commit["filesToStage"]:
        lines.append(f"- filesToStage: {', '.join(f'`{path}`' for path in suggested_commit['filesToStage'])}")
    if suggested_commit["filesToAvoid"]:
        lines.append(f"- filesToAvoid: {', '.join(f'`{path}`' for path in suggested_commit['filesToAvoid'])}")

    lines.extend(["", "## Validation", ""])
    for result in payload["validationResults"]:
        lines.append(f"- `{result['status']}` `{result['command']}`")

    lines.extend(["", "## Follow-Up Commands", ""])
    for command in payload["followUpCommands"]:
        lines.append(f"- `{command}`")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run conservative daily repo housekeeping.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH, help="Write JSON report here.")
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH, help="Write Markdown report here.")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_report(REPO_ROOT)
    markdown = format_markdown_report(payload)
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, markdown)
    print(f"Wrote JSON report: {args.json_path}")
    print(f"Wrote Markdown report: {args.markdown_path}")
    print(f"Overall status: {payload['overallStatus']}")
    print(f"Suggested commit: {payload['suggestedCommit']['recommended']}")
    if args.json:
        import json

        print(json.dumps(payload, indent=2))

    if payload["overallStatus"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
