from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_common import (
    collect_git_context,
    output_tail,
    relative_path,
    write_json_report,
    write_text_report,
)

Status = Literal["pass", "warn", "fail", "skipped"]
GateLevel = Literal["inner_loop", "checkpoint", "release", "forensic", "unknown"]
Confidence = Literal["high", "medium", "low"]
OverlapClassification = Literal["unique", "overlapping", "duplicative", "unclear"]
RecommendedPlacement = Literal["default", "nightly", "checkpoint", "release", "forensic"]
CandidateAction = Literal["keep", "measure_more", "trim_candidate", "demote_candidate"]

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "audit_validation"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "audit_validation_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "audit_validation_latest.md"
DEFAULT_TEST_LEDGER_JSON_PATH = DEFAULT_REPORT_DIR / "test_coverage_ledger_latest.json"
DEFAULT_TEST_LEDGER_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "test_coverage_ledger_latest.md"
DEFAULT_STALE_DAYS = 14
NIGHTLY_RUNTIME_WARNING_SECONDS = 3000.0
NIGHTLY_RUNTIME_BUDGET_SECONDS = 3600.0
STATUS_FIELD_NAMES = {"status", "overallStatus", "reportStatus"}
BLOCKING_REPORT_STATUSES = {"fail", "timeout"}
PYTEST_LEDGER_TARGETS = ("tests/rules", "tests/golden", "tests/integration")
PYTEST_RUNTIME_BASELINE_FILES = (
    "tests/rules/test_monster_behavior.py",
    "tests/rules/test_rules.py",
    "tests/rules/test_monster_benchmarks.py",
    "tests/rules/test_ai.py",
    "tests/rules/test_monster_content.py",
)
CANONICAL_CLASS_EVIDENCE_PATHS = (
    "reports/class_audit/fighter_barbarian_quick_latest.json",
    "reports/class_audit/fighter_barbarian_quick_latest.md",
)
LEGACY_CLASS_AUDIT_COMMANDS = (
    "fighter-audit-quick",
    "fighter-audit-full",
    "barbarian-audit-quick",
    "barbarian-audit-full",
)


@dataclass(frozen=True)
class AuditMechanism:
    task: str
    purpose: str
    recommended_gate_level: GateLevel
    report_paths: tuple[str, ...]
    overlap_candidates: tuple[str, ...]
    heavy: bool = False
    smoke_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmokeMeasurement:
    status: Status
    command: list[str]
    exit_code: int | None
    elapsed_seconds: float
    timeout_seconds: int
    output_tail: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "command": self.command,
            "exitCode": self.exit_code,
            "elapsedSeconds": round(self.elapsed_seconds, 3),
            "timeoutSeconds": self.timeout_seconds,
            "outputTail": self.output_tail,
        }


@dataclass(frozen=True)
class PytestCollection:
    command: list[str]
    status: Status
    total_count: int
    selected_count: int
    deselected_count: int
    node_ids: tuple[str, ...]
    elapsed_seconds: float
    output_tail: tuple[str, ...]


MECHANISMS: tuple[AuditMechanism, ...] = (
    AuditMechanism(
        "check-fast",
        "Fast backend correctness gate: Ruff plus non-slow golden/rules/integration tests.",
        "inner_loop",
        (),
        ("party-validation", "pass2-stability"),
    ),
    AuditMechanism(
        "daily-housekeeping",
        "Report-only repo hygiene, doc drift, and safe commit recommendation check.",
        "inner_loop",
        ("reports/housekeeping/daily_housekeeping_latest.json", "reports/housekeeping/daily_housekeeping_latest.md"),
        ("pass3-clarity",),
        smoke_args=("daily-housekeeping",),
    ),
    AuditMechanism(
        "party-validation",
        "Focused current-party behavior gate for the default party path.",
        "inner_loop",
        ("reports/party_validation/party_validation_latest.json", "reports/party_validation/party_validation_latest.md"),
        ("audit-quick", "pc-tuning-sample", "class-audit-slices"),
        smoke_args=(
            "party-validation",
            "--scenario",
            "reaction_bastion",
            "--batch-size",
            "6",
            "--skip-rules-gate",
            "--json-path",
            "reports/audit_validation/smoke_party_validation.json",
            "--markdown-path",
            "reports/audit_validation/smoke_party_validation.md",
        ),
    ),
    AuditMechanism(
        "pc-tuning-sample",
        "Event-level PC tuning sample for current party profiles.",
        "forensic",
        ("reports/pc_tuning/pc_tuning_latest.json", "reports/pc_tuning/pc_tuning_latest.md"),
        ("party-validation", "rogue-audit-quick"),
        smoke_args=(
            "pc-tuning-sample",
            "--profile",
            "rogue",
            "--scenario",
            "reaction_bastion",
            "--runs-per-scenario",
            "1",
            "--json-path",
            "reports/audit_validation/smoke_pc_tuning.json",
            "--markdown-path",
            "reports/audit_validation/smoke_pc_tuning.md",
        ),
    ),
    AuditMechanism(
        "audit-quick",
        "Scenario behavior and signature audit using the quick profile.",
        "checkpoint",
        ("reports/scenario_audit_latest.json",),
        ("party-validation", "pass2-stability", "nightly-audit"),
        smoke_args=(
            "audit-quick",
            "--scenario",
            "goblin_screen",
            "--smart-smoke-runs",
            "1",
            "--dumb-smoke-runs",
            "1",
            "--mechanic-runs",
            "1",
            "--health-batch-size",
            "3",
            "--report-path",
            "reports/audit_validation/smoke_scenario_audit.json",
        ),
    ),
    AuditMechanism(
        "audit-full",
        "Slower full scenario behavior and signature audit.",
        "release",
        ("reports/scenario_audit_latest.json",),
        ("audit-quick", "nightly-audit"),
        heavy=True,
    ),
    AuditMechanism(
        "audit-health",
        "Code-health and benchmark-style diagnostic report.",
        "checkpoint",
        ("reports/code_health_audit.json", "reports/code_health_audit.md"),
        ("daily-housekeeping", "pass3-clarity"),
        smoke_args=("audit-health", "--benchmark-batch-size", "1", "--largest-limit", "3"),
    ),
    AuditMechanism(
        "audit-validation",
        "Measure-first report on audit command coverage, report freshness, runtime evidence, and overlap candidates.",
        "checkpoint",
        ("reports/audit_validation/audit_validation_latest.json", "reports/audit_validation/audit_validation_latest.md"),
        ("daily-housekeeping", "pass3-clarity"),
    ),
    AuditMechanism(
        "fighter-audit-quick",
        "Legacy targeted Fighter quick audit; canonical Fighter matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("class-audit-slices", "party-validation"),
        smoke_args=(
            "fighter-audit-quick",
            "--scenario",
            "goblin_screen",
            "--player-preset",
            "fighter_level2_sample_trio",
            "--fixed-seed-runs",
            "1",
            "--behavior-batch-size",
            "3",
            "--health-batch-size",
            "3",
            "--skip-rules-gate",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "fighter-audit-full",
        "Legacy targeted Fighter full audit; canonical Fighter matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("fighter-audit-quick", "class-audit-slices"),
        heavy=True,
    ),
    AuditMechanism(
        "barbarian-audit-quick",
        "Legacy targeted Barbarian quick audit; canonical Barbarian matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("class-audit-slices", "party-validation"),
        smoke_args=(
            "barbarian-audit-quick",
            "--scenario",
            "goblin_screen",
            "--player-preset",
            "barbarian_level2_sample_trio",
            "--fixed-seed-runs",
            "1",
            "--behavior-batch-size",
            "3",
            "--health-batch-size",
            "3",
            "--skip-rules-gate",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "barbarian-audit-full",
        "Legacy targeted Barbarian full audit; canonical Barbarian matrix evidence uses class-audit-slices.",
        "forensic",
        (),
        ("barbarian-audit-quick", "class-audit-slices"),
        heavy=True,
    ),
    AuditMechanism(
        "rogue-audit-quick",
        "Dedicated level 2 ranged Rogue quick audit.",
        "checkpoint",
        ("reports/rogue_audit/rogue_audit_latest.json", "reports/rogue_audit/rogue_audit_latest.md"),
        ("party-validation", "pc-tuning-sample"),
        smoke_args=(
            "rogue-audit-quick",
            "--scenario",
            "goblin_screen",
            "--signature-probe-runs",
            "1",
            "--health-batch-size",
            "3",
            "--skip-rules-gate",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "rogue-audit-full",
        "Dedicated Rogue full audit.",
        "release",
        ("reports/rogue_audit/rogue_audit_latest.json", "reports/rogue_audit/rogue_audit_latest.md"),
        ("rogue-audit-quick",),
        heavy=True,
    ),
    AuditMechanism(
        "class-audit-slices",
        "Canonical timeout-safe segmented Fighter/Barbarian class audit evidence route.",
        "checkpoint",
        CANONICAL_CLASS_EVIDENCE_PATHS,
        ("fighter-audit-quick", "barbarian-audit-quick", "pass2-stability"),
        smoke_args=("class-audit-slices", "--dry-run", "--max-slices", "2"),
    ),
    AuditMechanism(
        "behavior-diagnostics",
        "Focused smart-vs-dumb investigation helper.",
        "forensic",
        (),
        ("fighter-audit-quick", "barbarian-audit-quick"),
        smoke_args=(
            "behavior-diagnostics",
            "--class",
            "fighter",
            "--player-preset",
            "fighter_level2_sample_trio",
            "--scenario",
            "goblin_screen",
            "--monster-behavior",
            "balanced",
            "--sample-size",
            "1",
            "--detail-limit",
            "0",
            "--no-report",
        ),
    ),
    AuditMechanism(
        "nightly-audit",
        "Layered nightly safety net on the integration branch.",
        "release",
        ("reports/nightly/nightly_audit_latest.json", "reports/nightly/nightly_audit_latest.md"),
        ("check-fast", "audit-quick", "audit-health"),
        heavy=True,
    ),
    AuditMechanism(
        "pass2-stability",
        "Determinism, repeatability, async batch, and long-audit stability gate.",
        "release",
        ("reports/pass2/pass2_stability_latest.json", "reports/pass2/pass2_stability_latest.md"),
        ("check-fast", "audit-quick", "class-audit-slices"),
        heavy=True,
        smoke_args=(
            "pass2-stability",
            "--scenario",
            "orc_push",
            "--player-preset",
            "rogue_level2_ranged_trio",
            "--skip-async",
            "--skip-long-audits",
            "--determinism-batch-size",
            "1",
            "--json-path",
            "reports/audit_validation/smoke_pass2_stability.json",
            "--markdown-path",
            "reports/audit_validation/smoke_pass2_stability.md",
        ),
    ),
    AuditMechanism(
        "pass3-clarity",
        "Docs, report, runner consistency, and audit-maintainability gate.",
        "checkpoint",
        ("reports/pass3/pass3_clarity_latest.json", "reports/pass3/pass3_clarity_latest.md"),
        ("daily-housekeeping",),
        smoke_args=(
            "pass3-clarity",
            "--json-path",
            "reports/audit_validation/smoke_pass3_clarity.json",
            "--markdown-path",
            "reports/audit_validation/smoke_pass3_clarity.md",
        ),
    ),
)

COVERAGE_RULES: dict[str, dict[str, Any]] = {
    "check-fast": {
        "riskAreas": ("lint", "backend behavior", "frontend contract"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "default",
        "candidateAction": "keep",
        "reason": "This remains the fastest broad backend gate and is intentionally duplicated by heavier release checks.",
    },
    "daily-housekeeping": {
        "riskAreas": ("docs/runbook consistency", "report freshness"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "default",
        "candidateAction": "keep",
        "reason": "It catches lightweight repo hygiene issues before broader clarity checks.",
    },
    "party-validation": {
        "riskAreas": ("backend behavior", "class behavior"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "default",
        "candidateAction": "keep",
        "reason": "It is the focused current-party gate and is cheaper than scenario or class matrix audits.",
    },
    "pc-tuning-sample": {
        "riskAreas": ("class behavior", "forensic traces"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "forensic",
        "candidateAction": "keep",
        "reason": "It provides event-level tuning evidence, not release-gate coverage.",
    },
    "audit-quick": {
        "riskAreas": ("scenario behavior",),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "keep",
        "reason": "It remains the canonical checkpoint path for broad scenario behavior.",
    },
    "audit-full": {
        "riskAreas": ("scenario behavior",),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "release",
        "candidateAction": "keep",
        "reason": "It is a release-scale scenario pass and should stay outside nightly/default gates.",
    },
    "audit-health": {
        "riskAreas": ("code health", "benchmark diagnostics"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "keep",
        "reason": "It is the source of truth for code-health and diagnostic benchmark evidence.",
    },
    "audit-validation": {
        "riskAreas": ("report freshness", "docs/runbook consistency"),
        "overlapClassification": "unique",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "keep",
        "reason": "It uniquely validates the audit system itself.",
    },
    "fighter-audit-quick": {
        "riskAreas": ("class behavior", "forensic traces"),
        "overlapClassification": "duplicative",
        "recommendedPlacement": "forensic",
        "candidateAction": "demote_candidate",
        "reason": "Segmented class slices are the canonical Fighter evidence route.",
    },
    "fighter-audit-full": {
        "riskAreas": ("class behavior", "forensic traces"),
        "overlapClassification": "duplicative",
        "recommendedPlacement": "forensic",
        "candidateAction": "demote_candidate",
        "reason": "Full monolithic Fighter audit is superseded by timeout-safe segmented evidence.",
    },
    "barbarian-audit-quick": {
        "riskAreas": ("class behavior", "forensic traces"),
        "overlapClassification": "duplicative",
        "recommendedPlacement": "forensic",
        "candidateAction": "demote_candidate",
        "reason": "Segmented class slices are the canonical Barbarian evidence route.",
    },
    "barbarian-audit-full": {
        "riskAreas": ("class behavior", "forensic traces"),
        "overlapClassification": "duplicative",
        "recommendedPlacement": "forensic",
        "candidateAction": "demote_candidate",
        "reason": "Full monolithic Barbarian audit is superseded by timeout-safe segmented evidence.",
    },
    "rogue-audit-quick": {
        "riskAreas": ("Rogue behavior",),
        "overlapClassification": "unique",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "keep",
        "reason": "It uniquely covers the dedicated ranged level-2 Rogue audit surface.",
    },
    "rogue-audit-full": {
        "riskAreas": ("Rogue behavior",),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "release",
        "candidateAction": "keep",
        "reason": "It is the release-scale extension of the dedicated Rogue audit.",
    },
    "class-audit-slices": {
        "riskAreas": ("class behavior",),
        "overlapClassification": "unique",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "keep",
        "reason": "It is the canonical timeout-safe Fighter/Barbarian matrix route.",
    },
    "behavior-diagnostics": {
        "riskAreas": ("forensic traces",),
        "overlapClassification": "unique",
        "recommendedPlacement": "forensic",
        "candidateAction": "keep",
        "reason": "It captures paired smart-vs-dumb evidence that gate audits do not preserve.",
    },
    "nightly-audit": {
        "riskAreas": ("lint", "backend behavior", "frontend contract", "scenario behavior", "class behavior", "code health"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "nightly",
        "candidateAction": "measure_more",
        "reason": "It is intentionally layered, but its internal step costs need timing evidence before trimming.",
    },
    "pass2-stability": {
        "riskAreas": ("determinism", "async reliability"),
        "overlapClassification": "unique",
        "recommendedPlacement": "release",
        "candidateAction": "keep",
        "reason": "It uniquely gates replay, batch, and async stability.",
    },
    "pass3-clarity": {
        "riskAreas": ("docs/runbook consistency", "report freshness"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "keep",
        "reason": "It is the canonical clarity gate even though it overlaps lightweight housekeeping.",
    },
}

NIGHTLY_STEP_COVERAGE: tuple[dict[str, Any], ...] = (
    {
        "stepId": "branch_gate",
        "riskAreas": ("report freshness",),
        "overlapClassification": "unique",
        "recommendedPlacement": "nightly",
        "candidateAction": "keep",
        "reason": "Branch validation is cheap and prevents auditing the wrong integration target.",
    },
    {
        "stepId": "check_fast",
        "riskAreas": ("lint", "backend behavior", "frontend contract"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "nightly",
        "candidateAction": "measure_more",
        "reason": "It duplicates the default gate; trim only if step timing proves it dominates nightly runtime.",
    },
    {
        "stepId": "npm_test",
        "riskAreas": ("frontend contract",),
        "overlapClassification": "unique",
        "recommendedPlacement": "nightly",
        "candidateAction": "keep",
        "reason": "Frontend test execution is not covered by backend-only gates.",
    },
    {
        "stepId": "npm_build",
        "riskAreas": ("frontend contract",),
        "overlapClassification": "unique",
        "recommendedPlacement": "nightly",
        "candidateAction": "keep",
        "reason": "The production build catches TypeScript/Vite failures that test-only checks can miss.",
    },
    {
        "stepId": "scenario_quick",
        "riskAreas": ("scenario behavior",),
        "overlapClassification": "duplicative",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "measure_more",
        "reason": "Broad scenario coverage should be preserved while nightly remains under the runtime budget.",
    },
    {
        "stepId": "code_health",
        "riskAreas": ("code health", "benchmark diagnostics"),
        "overlapClassification": "duplicative",
        "recommendedPlacement": "checkpoint",
        "candidateAction": "measure_more",
        "reason": "Benchmark-heavy code-health is the first trim candidate only if more nightly runtime needs to be recovered.",
    },
    {
        "stepId": "rotating_slice",
        "riskAreas": ("class behavior", "scenario behavior"),
        "overlapClassification": "overlapping",
        "recommendedPlacement": "nightly",
        "candidateAction": "keep",
        "reason": "A bounded rotating slice gives nightly targeted drift coverage without running a full release matrix.",
    },
)

RISK_AREA_COVERAGE: tuple[dict[str, Any], ...] = (
    {
        "riskArea": "rule correctness",
        "primaryOwner": "unit/rules tests",
        "secondaryOwners": ("golden tests", "scenario audits"),
        "canonicalGateLevel": "inner_loop",
        "overlapPolicy": "intentional",
        "rationale": "Focused tests own exact rule invariants; broader audits only prove those rules appear in live play.",
    },
    {
        "riskArea": "focused AI decisions",
        "primaryOwner": "unit/rules AI tests",
        "secondaryOwners": ("class audits", "behavior-diagnostics"),
        "canonicalGateLevel": "inner_loop",
        "overlapPolicy": "intentional",
        "rationale": "AI unit tests isolate one decision at a time while audits observe aggregate behavior.",
    },
    {
        "riskArea": "monster behavior",
        "primaryOwner": "monster behavior tests",
        "secondaryOwners": ("scenario audits", "audit-health", "monster benchmarks"),
        "canonicalGateLevel": "inner_loop",
        "overlapPolicy": "intentional",
        "rationale": "Monster tests own stat/action correctness; scenario audits own live encounter exposure.",
    },
    {
        "riskArea": "content integrity",
        "primaryOwner": "content and preset tests",
        "secondaryOwners": ("API catalog tests", "scenario audits"),
        "canonicalGateLevel": "inner_loop",
        "overlapPolicy": "intentional",
        "rationale": "Content tests catch registry drift before catalog/API or scenario checks consume that content.",
    },
    {
        "riskArea": "golden drift",
        "primaryOwner": "golden tests",
        "secondaryOwners": ("Pass 2 stability",),
        "canonicalGateLevel": "inner_loop",
        "overlapPolicy": "intentional",
        "rationale": "Goldens provide cheap exact fixture drift checks while Pass 2 proves broader repeatability.",
    },
    {
        "riskArea": "API contract",
        "primaryOwner": "API integration tests",
        "secondaryOwners": ("frontend tests", "Pass 2 async checks"),
        "canonicalGateLevel": "inner_loop",
        "overlapPolicy": "intentional",
        "rationale": "API tests own route/catalog contracts before frontend or async checks depend on them.",
    },
    {
        "riskArea": "frontend contract",
        "primaryOwner": "npm test and npm build",
        "secondaryOwners": ("API integration tests", "nightly-audit"),
        "canonicalGateLevel": "nightly",
        "overlapPolicy": "intentional",
        "rationale": "Frontend gates own browser-facing compilation/test coverage; backend API fixtures only support them.",
    },
    {
        "riskArea": "scenario behavior",
        "primaryOwner": "audit-quick",
        "secondaryOwners": ("audit-full", "nightly scenario_quick", "Pass 2 stability"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "intentional",
        "rationale": "Scenario quick is the checkpoint owner; full/nightly/Pass 2 rerun it at different cadence and depth.",
    },
    {
        "riskArea": "class behavior",
        "primaryOwner": "class-audit-slices",
        "secondaryOwners": ("party-validation", "legacy monolithic class audits", "nightly rotating_slice"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "candidate_duplicate",
        "rationale": "Segmented slices are canonical; monolithic Fighter/Barbarian audits are retained only as forensic legacy tools.",
    },
    {
        "riskArea": "Rogue behavior",
        "primaryOwner": "rogue-audit-quick",
        "secondaryOwners": ("rogue-audit-full", "party-validation", "pc-tuning-sample"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "intentional",
        "rationale": "The Rogue runner owns the dedicated ranged Rogue surface; other checks provide smoke or tuning context.",
    },
    {
        "riskArea": "determinism",
        "primaryOwner": "Pass 2 stability",
        "secondaryOwners": ("golden tests",),
        "canonicalGateLevel": "release",
        "overlapPolicy": "intentional",
        "rationale": "Pass 2 owns broad replay and batch determinism while goldens remain cheap exact sentinels.",
    },
    {
        "riskArea": "async reliability",
        "primaryOwner": "Pass 2 stability",
        "secondaryOwners": ("API integration tests",),
        "canonicalGateLevel": "release",
        "overlapPolicy": "intentional",
        "rationale": "Pass 2 owns long async job reliability; API tests only prove the endpoint contract works.",
    },
    {
        "riskArea": "code health",
        "primaryOwner": "audit-health",
        "secondaryOwners": ("nightly code_health", "Pass 3 clarity"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "intentional",
        "rationale": "Audit-health owns code-health evidence; nightly repeats it while runtime remains under budget.",
    },
    {
        "riskArea": "benchmark diagnostics",
        "primaryOwner": "audit-health",
        "secondaryOwners": ("monster benchmark tests", "nightly code_health"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "needs_canary",
        "rationale": "Benchmark checks overlap heavily and need canary/runtime proof before deciding what can be trimmed.",
    },
    {
        "riskArea": "docs/runbook consistency",
        "primaryOwner": "Pass 3 clarity",
        "secondaryOwners": ("daily-housekeeping", "audit-validation"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "intentional",
        "rationale": "Pass 3 owns full docs/runbook consistency; housekeeping provides cheap daily drift detection.",
    },
    {
        "riskArea": "report freshness",
        "primaryOwner": "audit-validation",
        "secondaryOwners": ("daily-housekeeping", "Pass 3 clarity"),
        "canonicalGateLevel": "checkpoint",
        "overlapPolicy": "intentional",
        "rationale": "Audit-validation owns report evidence freshness; housekeeping and Pass 3 provide supporting checks.",
    },
    {
        "riskArea": "forensic traces",
        "primaryOwner": "behavior-diagnostics",
        "secondaryOwners": ("pc-tuning-sample", "legacy monolithic class audits"),
        "canonicalGateLevel": "forensic",
        "overlapPolicy": "intentional",
        "rationale": "Forensic tools preserve detailed traces for investigations and should not be treated as release gates.",
    },
)

OVERLAP_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "groupId": "unit_rules_vs_behavior_audits",
        "title": "Unit/rules tests vs scenario/class audits",
        "members": ("unit/rules tests", "audit-quick", "class-audit-slices"),
        "overlapPolicy": "intentional",
        "primaryOwner": "unit/rules tests",
        "decision": "keep",
        "rationale": "Unit tests own exact mechanics; audits own live exposure and aggregate behavior.",
    },
    {
        "groupId": "goldens_vs_pass2",
        "title": "Golden tests vs Pass 2 stability",
        "members": ("golden tests", "pass2-stability"),
        "overlapPolicy": "intentional",
        "primaryOwner": "Pass 2 stability",
        "decision": "keep",
        "rationale": "Goldens are cheap exact sentinels and Pass 2 is the release-scale determinism owner.",
    },
    {
        "groupId": "scenario_quick_full_nightly",
        "title": "Scenario quick/full/nightly cadence",
        "members": ("audit-quick", "audit-full", "nightly scenario_quick"),
        "overlapPolicy": "intentional",
        "primaryOwner": "audit-quick",
        "decision": "keep",
        "rationale": "These checks differ by cadence and sample depth; keep while nightly stays under one hour.",
    },
    {
        "groupId": "segmented_vs_monolithic_class_audits",
        "title": "Segmented class slices vs monolithic Fighter/Barbarian audits",
        "members": ("class-audit-slices", "fighter-audit-quick/full", "barbarian-audit-quick/full"),
        "overlapPolicy": "candidate_duplicate",
        "primaryOwner": "class-audit-slices",
        "decision": "demote_monolithic",
        "rationale": "Segmented slices are timeout-safe canonical evidence; monoliths should remain forensic.",
    },
    {
        "groupId": "monster_benchmarks_vs_audit_health",
        "title": "Monster benchmarks vs audit-health",
        "members": ("tests/rules/test_monster_benchmarks.py", "audit-health", "nightly code_health"),
        "overlapPolicy": "needs_canary",
        "primaryOwner": "audit-health",
        "decision": "canary_validate",
        "rationale": "Benchmark overlap is the first Phase 3 target because ownership is plausible but not proven by canaries.",
    },
    {
        "groupId": "housekeeping_vs_pass3",
        "title": "Daily housekeeping vs Pass 3 clarity",
        "members": ("daily-housekeeping", "pass3-clarity"),
        "overlapPolicy": "intentional",
        "primaryOwner": "pass3-clarity",
        "decision": "keep",
        "rationale": "Housekeeping is the cheap daily check and Pass 3 is the checkpoint clarity gate.",
    },
    {
        "groupId": "party_validation_vs_class_slices",
        "title": "Party validation vs class slices",
        "members": ("party-validation", "class-audit-slices"),
        "overlapPolicy": "intentional",
        "primaryOwner": "class-audit-slices",
        "decision": "keep",
        "rationale": "Party validation owns current-party smoke confidence and class slices own class matrix evidence.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the current audit and testing mechanisms without trimming them.")
    parser.add_argument("--measure-smoke", action="store_true", help="Run bounded smoke measurements for cheap/scoped commands.")
    parser.add_argument("--include-heavy", action="store_true", help="Allow heavy release commands to run in smoke measurement mode.")
    parser.add_argument("--explain-coverage", action="store_true", help="Add an advisory redundancy map without changing audit behavior.")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Per-command timeout for smoke measurements.")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS, help="Report age that lowers confidence.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-path", type=Path, default=DEFAULT_MARKDOWN_PATH)
    return parser.parse_args()


def extract_dev_tasks(dev_ps1_text: str) -> list[str]:
    match = re.search(r"ValidateSet\((.*?)\)\]\s*\[string\]\$Task", dev_ps1_text, flags=re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def extract_runbook_direct_equivalents(runbook_text: str) -> dict[str, str]:
    mappings: dict[str, str] = {}
    pattern = re.compile(r"^- `([^`]+)`: `([^`]+)`", flags=re.MULTILINE)
    for match in pattern.finditer(runbook_text):
        mappings[match.group(1)] = match.group(2)
    return mappings


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_pytest_collection(stdout: str, command: list[str], elapsed_seconds: float, status: Status = "pass") -> PytestCollection:
    node_ids = tuple(line.strip() for line in stdout.splitlines() if line.startswith(("tests/", "tests\\")) and "::" in line)
    summary_lines = [line.strip() for line in stdout.splitlines() if "tests collected" in line or "test collected" in line]
    summary = summary_lines[-1] if summary_lines else ""
    selected_count = len(node_ids)
    total_count = selected_count
    deselected_count = 0
    filtered_match = re.search(r"(\d+)/(\d+) tests? collected \((\d+) deselected\)", summary)
    total_match = re.search(r"(\d+) tests? collected", summary)
    if filtered_match:
        selected_count = int(filtered_match.group(1))
        total_count = int(filtered_match.group(2))
        deselected_count = int(filtered_match.group(3))
    elif total_match:
        total_count = int(total_match.group(1))
        selected_count = total_count
    return PytestCollection(
        command=command,
        status=status,
        total_count=total_count,
        selected_count=selected_count,
        deselected_count=deselected_count,
        node_ids=node_ids,
        elapsed_seconds=round(elapsed_seconds, 3),
        output_tail=tuple(output_tail(stdout, None, limit=8)),
    )


def collect_pytest_inventory(mark_expression: str | None = None, targets: tuple[str, ...] = PYTEST_LEDGER_TARGETS) -> PytestCollection:
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", *targets]
    if mark_expression:
        command.extend(["-m", mark_expression])
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed_seconds = time.perf_counter() - started
    status: Status = "pass" if completed.returncode == 0 else "fail"
    return parse_pytest_collection(
        "\n".join(part for part in (completed.stdout, completed.stderr) if part),
        command,
        elapsed_seconds,
        status,
    )


def normalize_node_path(node_id: str) -> str:
    return node_id.split("::", 1)[0].replace("\\", "/")


def infer_test_file_risk_areas(path: str) -> list[str]:
    name = Path(path).name
    if path.startswith("tests/golden/"):
        return ["determinism", "golden drift"]
    if path.startswith("tests/integration/"):
        return ["API contract", "frontend contract"]
    if name == "test_pass2_stability.py":
        return ["determinism", "async reliability", "audit tooling"]
    if name == "test_pass3_clarity.py":
        return ["docs/runbook consistency", "report freshness", "audit tooling"]
    if name in {"test_rules.py", "test_grapple_rules.py", "test_spatial.py", "test_crocodile.py", "test_giant_toad.py"}:
        return ["rule correctness", "backend behavior"]
    if name == "test_ai.py":
        return ["focused AI decisions", "class behavior"]
    if name in {"test_monster_behavior.py", "test_monster_content.py"}:
        return ["monster behavior", "content integrity"]
    if name == "test_monster_benchmarks.py":
        return ["benchmark diagnostics", "monster behavior"]
    if "audit" in name or name in {"test_party_validation.py", "test_pc_tuning_sample.py", "test_daily_housekeeping.py"}:
        return ["audit tooling", "report freshness"]
    if name in {"test_smart_logic_matrix.py", "test_smart_vs_dumb_diagnostics.py"}:
        return ["focused AI decisions", "forensic traces"]
    if name == "test_spell_import_boundaries.py":
        return ["import boundaries", "spell workflow"]
    if name in {"test_player_framework.py", "test_presets.py"}:
        return ["content integrity", "player preset behavior"]
    return ["backend behavior"]


def infer_test_file_overlap(path: str) -> tuple[str, list[str], str, str, str]:
    name = Path(path).name
    if path.startswith("tests/golden/"):
        return (
            "overlapping",
            ["pass2-stability"],
            "inner_loop",
            "keep",
            "Exact goldens overlap Pass 2 determinism, but they are cheap fixed-fixture drift locks.",
        )
    if path.startswith("tests/integration/"):
        return (
            "unique",
            ["nightly.npm_build", "pass2-stability async checks"],
            "inner_loop",
            "keep",
            "API route and catalog contract checks catch interface regressions before browser/frontend gates.",
        )
    if name == "test_monster_benchmarks.py":
        return (
            "overlapping",
            ["audit-health", "monster benchmark fixtures"],
            "checkpoint",
            "measure_more",
            "Benchmark-heavy monster checks need runtime and canary evidence before staying in the default gate.",
        )
    if name in {"test_scenario_audit.py", "test_fighter_audit.py", "test_barbarian_audit.py", "test_rogue_audit.py"}:
        return (
            "overlapping",
            ["audit-quick", "class-audit-slices", "rogue-audit-quick"],
            "inner_loop",
            "keep",
            "Runner unit tests protect audit report logic; broad behavior remains owned by the audit commands.",
        )
    if name in {"test_pass2_stability.py", "test_nightly_audit.py", "test_audit_validation.py"}:
        return (
            "unique",
            ["audit-validation"],
            "inner_loop",
            "keep",
            "Audit-runner tests protect orchestration behavior that gameplay tests do not cover.",
        )
    if name in {"test_pass3_clarity.py", "test_daily_housekeeping.py"}:
        return (
            "overlapping",
            ["pass3-clarity", "daily-housekeeping"],
            "inner_loop",
            "keep",
            "These checks overlap on docs/report hygiene but guard different runner contracts.",
        )
    if name in {"test_party_validation.py", "test_pc_tuning_sample.py", "test_class_audit_slices.py"}:
        return (
            "overlapping",
            ["party-validation", "class-audit-slices", "pc-tuning-sample"],
            "inner_loop",
            "keep",
            "Runner tests protect scoped gate behavior while the commands own live behavior evidence.",
        )
    if name in {"test_smart_logic_matrix.py", "test_smart_vs_dumb_diagnostics.py"}:
        return (
            "unique",
            ["behavior-diagnostics"],
            "forensic",
            "keep",
            "These files protect diagnostic-only AI comparison tooling and should not gate normal gameplay changes.",
        )
    if name in {"test_rules.py", "test_ai.py", "test_monster_behavior.py", "test_monster_content.py"}:
        return (
            "overlapping",
            ["scenario audits", "class audits", "golden tests"],
            "inner_loop",
            "keep",
            "Focused tests overlap broad audits intentionally because they isolate exact rule or AI failures.",
        )
    if name in {
        "test_player_framework.py",
        "test_presets.py",
        "test_spatial.py",
        "test_grapple_rules.py",
        "test_crocodile.py",
        "test_giant_toad.py",
        "test_review_python_goldens.py",
        "test_spell_import_boundaries.py",
    }:
        return (
            "unique",
            ["check-fast"],
            "inner_loop",
            "keep",
            "Focused low-cost tests document specific invariants that broader audits only observe indirectly.",
        )
    return (
        "unknown",
        [],
        "inner_loop",
        "measure_more",
        "This file needs a canary expectation before any trim decision.",
    )


def build_pytest_file_rows(full_collection: PytestCollection, not_slow_collection: PytestCollection) -> list[dict[str, Any]]:
    full_by_file: dict[str, list[str]] = {}
    not_slow_by_file: dict[str, list[str]] = {}
    for node_id in full_collection.node_ids:
        full_by_file.setdefault(normalize_node_path(node_id), []).append(node_id)
    for node_id in not_slow_collection.node_ids:
        not_slow_by_file.setdefault(normalize_node_path(node_id), []).append(node_id)

    rows: list[dict[str, Any]] = []
    for path in sorted(full_by_file):
        full_nodes = full_by_file[path]
        selected_nodes = not_slow_by_file.get(path, [])
        parametrized_count = sum(1 for node_id in full_nodes if "[" in node_id.rsplit("::", 1)[-1])
        overlap, overlaps_with, placement, action, reason = infer_test_file_overlap(path)
        rows.append(
            {
                "path": path,
                "totalCount": len(full_nodes),
                "notSlowSelectedCount": len(selected_nodes),
                "slowDeselectedCount": len(full_nodes) - len(selected_nodes),
                "parametrizedItemCount": parametrized_count,
                "riskAreas": infer_test_file_risk_areas(path),
                "overlapClassification": overlap,
                "overlapWith": overlaps_with,
                "recommendedPlacement": placement,
                "candidateAction": action,
                "uniqueFailureValue": reason,
                "runtimeSeconds": None,
                "runtimeSource": "not_measured",
            }
        )
    rows.sort(key=lambda row: (-int(row["totalCount"]), row["path"]))
    return rows


def build_risk_area_coverage() -> list[dict[str, Any]]:
    return [
        {
            "riskArea": entry["riskArea"],
            "primaryOwner": entry["primaryOwner"],
            "secondaryOwners": list(entry["secondaryOwners"]),
            "canonicalGateLevel": entry["canonicalGateLevel"],
            "overlapPolicy": entry["overlapPolicy"],
            "rationale": entry["rationale"],
        }
        for entry in RISK_AREA_COVERAGE
    ]


def build_overlap_groups() -> list[dict[str, Any]]:
    return [
        {
            "groupId": entry["groupId"],
            "title": entry["title"],
            "members": list(entry["members"]),
            "overlapPolicy": entry["overlapPolicy"],
            "primaryOwner": entry["primaryOwner"],
            "decision": entry["decision"],
            "rationale": entry["rationale"],
        }
        for entry in OVERLAP_GROUPS
    ]


def build_candidate_decisions(overlap_groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    decisions: list[dict[str, str]] = [
        {
            "id": "keep_core_unit_golden_api_tests",
            "recommendedAction": "keep",
            "source": "riskAreaCoverage",
            "rationale": "Core unit, golden, and API tests remain cheap primary owners for exact regressions.",
        },
        {
            "id": "keep_nightly_scenario_breadth",
            "recommendedAction": "keep",
            "source": "nightlyRuntimeBudget",
            "rationale": "Broad nightly scenario coverage stays under the one-hour runtime budget.",
        },
        {
            "id": "keep_segmented_class_slices",
            "recommendedAction": "keep",
            "source": "classAuditEvidence",
            "rationale": "Segmented class slices remain canonical Fighter/Barbarian evidence.",
        },
        {
            "id": "measure_nightly_check_fast_and_code_health",
            "recommendedAction": "measure_more",
            "source": "coverageReview",
            "rationale": "These nightly steps are candidates only if runtime approaches or exceeds the one-hour budget.",
        },
    ]
    for group in overlap_groups:
        if group["overlapPolicy"] == "candidate_duplicate":
            decisions.append(
                {
                    "id": group["groupId"],
                    "recommendedAction": "demote_candidate",
                    "source": "overlapGroups",
                    "rationale": group["rationale"],
                }
            )
        elif group["overlapPolicy"] == "needs_canary":
            decisions.append(
                {
                    "id": group["groupId"],
                    "recommendedAction": "canary_validate",
                    "source": "overlapGroups",
                    "rationale": group["rationale"],
                }
            )
    return decisions


def build_coverage_map() -> dict[str, Any]:
    risk_area_coverage = build_risk_area_coverage()
    overlap_groups = build_overlap_groups()
    candidate_decisions = build_candidate_decisions(overlap_groups)
    needs_canary = [group["groupId"] for group in overlap_groups if group["overlapPolicy"] == "needs_canary"]
    candidate_duplicates = [
        group["groupId"] for group in overlap_groups if group["overlapPolicy"] == "candidate_duplicate"
    ]
    return {
        "riskAreaCoverage": risk_area_coverage,
        "overlapGroups": overlap_groups,
        "candidateDecisions": candidate_decisions,
        "summary": {
            "riskAreaCount": len(risk_area_coverage),
            "overlapGroupCount": len(overlap_groups),
            "candidateDecisionCount": len(candidate_decisions),
            "needsCanary": needs_canary,
            "candidateDuplicates": candidate_duplicates,
            "primaryPhase3CanaryTarget": "monster_benchmarks_vs_audit_health",
        },
    }


def build_canary_specs() -> list[dict[str, str]]:
    return [
        {
            "mechanism": "unit/rules tests",
            "defectToCatch": "Break a focused rule invariant such as resource spending, damage resistance, or action legality.",
            "expectedFailureSignal": "A small deterministic pytest subset fails with an exact node id.",
        },
        {
            "mechanism": "golden tests",
            "defectToCatch": "Change replay/result serialization or deterministic batch summary output.",
            "expectedFailureSignal": "The golden fixture comparison fails before scenario/class audits are needed.",
        },
        {
            "mechanism": "scenario audits",
            "defectToCatch": "Remove or disconnect a required live scenario signature mechanic.",
            "expectedFailureSignal": "Scenario audit reports a structural/signature failure for the affected scenario.",
        },
        {
            "mechanism": "class audits",
            "defectToCatch": "Regress class-specific behavior such as Fighter Action Surge, Barbarian Rage, or Rogue Sneak Attack.",
            "expectedFailureSignal": "The relevant segmented class or Rogue audit row fails or warns with a behavior-specific message.",
        },
        {
            "mechanism": "Pass 2 stability",
            "defectToCatch": "Introduce nondeterministic replay state, batch drift, async desync, crash, hang, or timeout.",
            "expectedFailureSignal": "Pass 2 reports deterministic mismatch, async failure, command timeout, or malformed artifact.",
        },
    ]


def build_test_coverage_ledger(
    *,
    context: dict[str, Any],
    full_collection: PytestCollection,
    not_slow_collection: PytestCollection,
    mechanism_rows: list[dict[str, Any]] | None = None,
    json_path: Path = DEFAULT_TEST_LEDGER_JSON_PATH,
    markdown_path: Path = DEFAULT_TEST_LEDGER_MARKDOWN_PATH,
) -> dict[str, Any]:
    file_rows = build_pytest_file_rows(full_collection, not_slow_collection)
    dominant_files = [row for row in file_rows if row["path"] in PYTEST_RUNTIME_BASELINE_FILES]
    coverage_map = build_coverage_map()
    summary = {
        "totalCollected": full_collection.total_count,
        "notSlowSelected": not_slow_collection.selected_count,
        "notSlowDeselected": not_slow_collection.deselected_count,
        "fileCount": len(file_rows),
        "largestFiles": [row["path"] for row in file_rows[:5]],
        "dominantRuntimeBaselineFiles": [row["path"] for row in dominant_files],
    }
    status: Status = "fail" if full_collection.status == "fail" or not_slow_collection.status == "fail" else "pass"
    return {
        "overallStatus": status,
        "context": context,
        "artifactPaths": {
            "json": relative_path(json_path),
            "markdown": relative_path(markdown_path),
        },
        "pytestInventory": {
            "targets": list(PYTEST_LEDGER_TARGETS),
            "fullCollection": {
                "status": full_collection.status,
                "command": full_collection.command,
                "totalCount": full_collection.total_count,
                "selectedCount": full_collection.selected_count,
                "deselectedCount": full_collection.deselected_count,
                "elapsedSeconds": full_collection.elapsed_seconds,
                "outputTail": list(full_collection.output_tail),
            },
            "notSlowCollection": {
                "status": not_slow_collection.status,
                "command": not_slow_collection.command,
                "totalCount": not_slow_collection.total_count,
                "selectedCount": not_slow_collection.selected_count,
                "deselectedCount": not_slow_collection.deselected_count,
                "elapsedSeconds": not_slow_collection.elapsed_seconds,
                "outputTail": list(not_slow_collection.output_tail),
            },
        },
        "summary": summary,
        "testFiles": file_rows,
        "auditMechanisms": [build_coverage_mechanism_review(row) for row in mechanism_rows] if mechanism_rows else [],
        "riskAreaCoverage": coverage_map["riskAreaCoverage"],
        "overlapGroups": coverage_map["overlapGroups"],
        "candidateDecisions": coverage_map["candidateDecisions"],
        "coverageMapSummary": coverage_map["summary"],
        "canarySpecs": build_canary_specs(),
    }


def format_test_coverage_ledger_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Test Coverage Ledger",
        "",
        f"- Overall status: `{payload['overallStatus']}`",
        f"- Total collected: `{summary['totalCollected']}`",
        f"- Not-slow selected: `{summary['notSlowSelected']}`",
        f"- Not-slow deselected: `{summary['notSlowDeselected']}`",
        f"- Test files: `{summary['fileCount']}`",
        "",
        "## Test Files",
        "",
        "| file | total | not slow | slow | parametrized | risks | overlap | placement | action |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for row in payload["testFiles"]:
        lines.append(
            f"| `{row['path']}` | {row['totalCount']} | {row['notSlowSelectedCount']} | "
            f"{row['slowDeselectedCount']} | {row['parametrizedItemCount']} | "
            f"{', '.join(row['riskAreas'])} | `{row['overlapClassification']}` | "
            f"`{row['recommendedPlacement']}` | `{row['candidateAction']}` |"
        )
    if payload["auditMechanisms"]:
        lines.extend(
            [
                "",
                "## Audit Mechanisms",
                "",
                "| command | risks | overlap | placement | action |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in payload["auditMechanisms"]:
            lines.append(
                f"| `{row['task']}` | {', '.join(row['riskAreas'])} | `{row['overlapClassification']}` | "
                f"`{row['recommendedPlacement']}` | `{row['candidateAction']}` |"
            )
    lines.extend(
        [
            "",
            "## Risk Ownership",
            "",
            "| risk area | primary owner | secondary owners | gate | overlap policy | rationale |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["riskAreaCoverage"]:
        lines.append(
            f"| `{row['riskArea']}` | `{row['primaryOwner']}` | {', '.join(row['secondaryOwners']) or '-'} | "
            f"`{row['canonicalGateLevel']}` | `{row['overlapPolicy']}` | {row['rationale']} |"
        )
    lines.extend(
        [
            "",
            "## Overlap Groups",
            "",
            "| group | members | policy | primary owner | decision | rationale |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["overlapGroups"]:
        lines.append(
            f"| `{row['groupId']}` | {', '.join(row['members'])} | `{row['overlapPolicy']}` | "
            f"`{row['primaryOwner']}` | `{row['decision']}` | {row['rationale']} |"
        )
    lines.extend(["", "## Candidate Decisions", ""])
    for decision in payload["candidateDecisions"]:
        lines.append(
            f"- `{decision['id']}`: `{decision['recommendedAction']}` - {decision['rationale']}"
        )
    lines.extend(["", "## Canary Specs", ""])
    for spec in payload["canarySpecs"]:
        lines.append(
            f"- `{spec['mechanism']}`: {spec['defectToCatch']} Expected signal: {spec['expectedFailureSignal']}"
        )
    return "\n".join(lines)


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


def collect_key_values(value: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys:
                values.append(child)
            values.extend(collect_key_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            values.extend(collect_key_values(child, keys))
    return values


def flatten_string_values(values: list[Any]) -> list[str]:
    strings: list[str] = []
    for value in values:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, list | tuple | set):
            strings.extend(str(item) for item in value if isinstance(item, str))
    return sorted(set(strings))


def count_rows(payload: dict[str, Any]) -> int:
    row_keys = (
        "rows",
        "results",
        "checks",
        "issues",
        "signatureProbes",
        "replayDeterminismRows",
        "batchDeterminismRows",
        "asyncJobRows",
        "longAuditRows",
    )
    total = 0
    for key in row_keys:
        value = payload.get(key)
        if isinstance(value, list):
            total += len(value)
    return total


def first_number(values: list[Any]) -> float | None:
    for value in values:
        if isinstance(value, int | float):
            return float(value)
    return None


def summarize_json_report(path: Path, now: datetime, stale_days: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": relative_path(path),
            "exists": False,
            "status": "missing",
            "confidenceImpact": "missing_report",
        }

    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    age_hours = round((now - modified_at).total_seconds() / 3600, 2)
    summary: dict[str, Any] = {
        "path": relative_path(path),
        "exists": True,
        "modifiedAt": modified_at.isoformat(),
        "ageHours": age_hours,
        "stale": age_hours > stale_days * 24,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Report JSON root is not an object.")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        summary.update({"status": "malformed", "error": str(error), "confidenceImpact": "malformed_report"})
        return summary

    status_values = iter_status_values(payload)
    status = str(payload.get("overallStatus") or payload.get("status") or payload.get("reportStatus") or "unknown")
    warning_count = sum(1 for value in status_values if value == "warn")
    failure_count = sum(1 for value in status_values if value in {"fail", "timeout"})
    elapsed_seconds = first_number(collect_key_values(payload, {"elapsedSeconds", "totalElapsedSeconds"}))
    scenario_ids = flatten_string_values(collect_key_values(payload, {"scenarioId", "scenarioIds"}))
    player_preset_ids = flatten_string_values(collect_key_values(payload, {"playerPresetId", "playerPresetIds"}))
    warning_strings = flatten_string_values(collect_key_values(payload, {"warnings", "knownWarnings", "issues"}))[:12]

    summary.update(
        {
            "status": status,
            "statusFields": sorted(set(status_values)),
            "rowCount": count_rows(payload),
            "warningCount": warning_count,
            "failureCount": failure_count,
            "elapsedSeconds": elapsed_seconds,
            "scenarioIds": scenario_ids[:20],
            "playerPresetIds": player_preset_ids[:20],
            "warningSamples": warning_strings,
        }
    )
    if summary["stale"]:
        summary["confidenceImpact"] = "stale_report"
    return summary


def summarize_text_report(path: Path, now: datetime, stale_days: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": relative_path(path),
            "exists": False,
            "status": "missing",
            "confidenceImpact": "missing_report",
        }
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    age_hours = round((now - modified_at).total_seconds() / 3600, 2)
    return {
        "path": relative_path(path),
        "exists": True,
        "modifiedAt": modified_at.isoformat(),
        "ageHours": age_hours,
        "stale": age_hours > stale_days * 24,
        "lineCount": len(path.read_text(encoding="utf-8").splitlines()),
        "confidenceImpact": "stale_report" if age_hours > stale_days * 24 else None,
    }


def summarize_report(path_text: str, now: datetime, stale_days: int) -> dict[str, Any]:
    path = REPO_ROOT / path_text
    if path.suffix.lower() == ".json":
        return summarize_json_report(path, now, stale_days)
    return summarize_text_report(path, now, stale_days)


def direct_command_for(mechanism: AuditMechanism, runbook_mappings: dict[str, str]) -> str:
    if mechanism.task in runbook_mappings:
        return runbook_mappings[mechanism.task]
    return ""


def infer_runtime_class(elapsed_seconds: float | None, report_count: int, heavy: bool) -> str:
    if elapsed_seconds is None:
        return "unknown" if report_count == 0 else "unmeasured"
    if elapsed_seconds < 60:
        return "fast"
    if elapsed_seconds < 600:
        return "medium"
    if heavy or elapsed_seconds >= 600:
        return "slow"
    return "medium"


def determine_confidence(
    mechanism: AuditMechanism,
    in_wrapper: bool,
    direct_command: str,
    report_summaries: list[dict[str, Any]],
) -> tuple[Confidence, list[str]]:
    reasons: list[str] = []
    if not in_wrapper:
        reasons.append("wrapper_missing")
    if not direct_command:
        reasons.append("runbook_direct_equivalent_missing")

    json_reports = [summary for summary in report_summaries if summary["path"].endswith(".json")]
    if mechanism.report_paths and not any(summary.get("exists") for summary in json_reports):
        reasons.append("json_report_missing")
    if any(summary.get("status") == "malformed" for summary in report_summaries):
        reasons.append("report_malformed")
    if any(summary.get("stale") for summary in report_summaries):
        reasons.append("report_stale")
    if mechanism.task == "class-audit-slices" and any(
        summary.get("status") in BLOCKING_REPORT_STATUSES for summary in json_reports
    ):
        reasons.append("canonical_class_evidence_failed")

    if not reasons:
        return "high", ["wrapper, runbook mapping, and report evidence are present"]
    if "wrapper_missing" in reasons or "report_malformed" in reasons:
        return "low", reasons
    if (
        "json_report_missing" in reasons
        or "runbook_direct_equivalent_missing" in reasons
        or "report_stale" in reasons
        or "canonical_class_evidence_failed" in reasons
    ):
        return "low", reasons
    return "medium", reasons


def row_status(confidence: Confidence, report_summaries: list[dict[str, Any]]) -> Status:
    if any(summary.get("status") == "malformed" for summary in report_summaries):
        return "fail"
    if confidence == "low":
        return "warn"
    if any(summary.get("status") == "fail" for summary in report_summaries):
        return "warn"
    return "pass"


def build_powershell_command(args: tuple[str, ...]) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "scripts" / "dev.ps1"), *args]


def run_smoke_measurement(mechanism: AuditMechanism, timeout_seconds: int) -> SmokeMeasurement:
    if not mechanism.smoke_args:
        return SmokeMeasurement(
            status="skipped",
            command=[],
            exit_code=0,
            elapsed_seconds=0.0,
            timeout_seconds=timeout_seconds,
            output_tail=["No bounded smoke command is configured for this mechanism."],
        )

    command = build_powershell_command(mechanism.smoke_args)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        elapsed = time.perf_counter() - started
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else error.stdout
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        return SmokeMeasurement(
            status="fail",
            command=command,
            exit_code=None,
            elapsed_seconds=elapsed,
            timeout_seconds=timeout_seconds,
            output_tail=output_tail(stdout, stderr),
        )

    elapsed = time.perf_counter() - started
    return SmokeMeasurement(
        status="pass" if completed.returncode == 0 else "fail",
        command=command,
        exit_code=completed.returncode,
        elapsed_seconds=elapsed,
        timeout_seconds=timeout_seconds,
        output_tail=output_tail(completed.stdout, completed.stderr),
    )


def build_mechanism_row(
    mechanism: AuditMechanism,
    wrapper_tasks: list[str],
    runbook_mappings: dict[str, str],
    now: datetime,
    stale_days: int,
) -> dict[str, Any]:
    report_summaries = [summarize_report(path, now, stale_days) for path in mechanism.report_paths]
    in_wrapper = mechanism.task in wrapper_tasks
    direct_command = direct_command_for(mechanism, runbook_mappings)
    confidence, confidence_reasons = determine_confidence(mechanism, in_wrapper, direct_command, report_summaries)
    latest_json_report = next((summary for summary in report_summaries if summary["path"].endswith(".json") and summary.get("exists")), None)
    elapsed_seconds = first_number([summary.get("elapsedSeconds") for summary in report_summaries])

    return {
        "task": mechanism.task,
        "status": row_status(confidence, report_summaries),
        "wrapperCommand": f".\\scripts\\dev.ps1 {mechanism.task}",
        "directCommand": direct_command,
        "wrapperPresent": in_wrapper,
        "runbookDirectEquivalentPresent": bool(direct_command),
        "expectedPurpose": mechanism.purpose,
        "recommendedGateLevel": mechanism.recommended_gate_level,
        "heavy": mechanism.heavy,
        "latestStatus": latest_json_report.get("status") if latest_json_report else "unreported",
        "observedElapsedSeconds": elapsed_seconds,
        "inferredRuntimeClass": infer_runtime_class(elapsed_seconds, len(report_summaries), mechanism.heavy),
        "reportArtifacts": report_summaries,
        "overlapCandidates": list(mechanism.overlap_candidates),
        "validationConfidence": confidence,
        "confidenceReasons": confidence_reasons,
    }


def maybe_measure_rows(
    rows: list[dict[str, Any]],
    mechanisms: tuple[AuditMechanism, ...],
    measure_smoke: bool,
    include_heavy: bool,
    timeout_seconds: int,
) -> None:
    if not measure_smoke:
        return
    by_task = {mechanism.task: mechanism for mechanism in mechanisms}
    for row in rows:
        mechanism = by_task[row["task"]]
        if mechanism.heavy and not include_heavy:
            row["smokeMeasurement"] = {
                "status": "skipped",
                "reason": "Heavy command skipped without --include-heavy.",
            }
            continue
        measurement = run_smoke_measurement(mechanism, timeout_seconds)
        row["smokeMeasurement"] = measurement.to_payload()
        row["observedElapsedSeconds"] = measurement.elapsed_seconds
        row["inferredRuntimeClass"] = infer_runtime_class(measurement.elapsed_seconds, len(row["reportArtifacts"]), mechanism.heavy)
        if measurement.status == "fail":
            row["status"] = "fail"
            row["validationConfidence"] = "low"
            row["confidenceReasons"] = [*row["confidenceReasons"], "smoke_measurement_failed"]


def build_recommendations(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    default_gate = [
        row["task"]
        for row in rows
        if row["recommendedGateLevel"] == "inner_loop" and row["validationConfidence"] != "low"
    ]
    checkpoint_or_release = [
        row["task"]
        for row in rows
        if row["recommendedGateLevel"] in {"checkpoint", "release"} and row["validationConfidence"] != "low"
    ]
    forensic = [
        row["task"]
        for row in rows
        if row["recommendedGateLevel"] == "forensic" and row["validationConfidence"] != "low"
    ]
    needs_validation = [row["task"] for row in rows if row["validationConfidence"] == "low"]
    needs_evidence_refresh = [
        row["task"]
        for row in rows
        if row["validationConfidence"] == "low"
        or any(
            artifact.get("confidenceImpact") in {"missing_report", "stale_report", "malformed_report"}
            or artifact.get("status") in BLOCKING_REPORT_STATUSES
            for artifact in row["reportArtifacts"]
        )
    ]
    return {
        "keepInDefaultGate": default_gate,
        "checkpointOrReleaseOnly": checkpoint_or_release,
        "forensicOnly": forensic,
        "needsLaterValidation": needs_validation,
        "needsEvidenceRefresh": needs_evidence_refresh,
    }


def build_canonical_class_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    class_row = next((row for row in rows if row["task"] == "class-audit-slices"), None)
    return {
        "task": "class-audit-slices",
        "summaryJsonPath": CANONICAL_CLASS_EVIDENCE_PATHS[0],
        "summaryMarkdownPath": CANONICAL_CLASS_EVIDENCE_PATHS[1],
        "status": class_row["status"] if class_row else "missing",
        "validationConfidence": class_row["validationConfidence"] if class_row else "low",
        "reportArtifacts": class_row["reportArtifacts"] if class_row else [],
    }


def build_command_coverage(wrapper_tasks: list[str], runbook_mappings: dict[str, str]) -> dict[str, Any]:
    known_tasks = [mechanism.task for mechanism in MECHANISMS]
    return {
        "wrapperTasks": wrapper_tasks,
        "runbookDirectEquivalentTasks": sorted(runbook_mappings),
        "missingFromWrapper": [task for task in known_tasks if task not in wrapper_tasks],
        "missingRunbookDirectEquivalent": [task for task in known_tasks if task not in runbook_mappings],
        "undocumentedWrapperTasks": [task for task in wrapper_tasks if task not in runbook_mappings],
        "unknownWrapperTasks": [task for task in wrapper_tasks if task not in known_tasks],
    }


def build_coverage_mechanism_review(row: dict[str, Any]) -> dict[str, Any]:
    rule = COVERAGE_RULES.get(
        row["task"],
        {
            "riskAreas": ("unknown",),
            "overlapClassification": "unclear",
            "recommendedPlacement": "checkpoint",
            "candidateAction": "measure_more",
            "reason": "No explicit coverage rule is defined for this mechanism.",
        },
    )
    return {
        "task": row["task"],
        "riskAreas": list(rule["riskAreas"]),
        "overlapClassification": rule["overlapClassification"],
        "recommendedPlacement": rule["recommendedPlacement"],
        "candidateAction": rule["candidateAction"],
        "reason": rule["reason"],
        "overlapCandidates": list(row.get("overlapCandidates", [])),
        "currentGateLevel": row.get("recommendedGateLevel", "unknown"),
        "runtimeClass": row.get("inferredRuntimeClass", "unknown"),
    }


def extract_latest_nightly_runtime(rows: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    nightly_row = next((row for row in rows if row["task"] == "nightly-audit"), None)
    if nightly_row is None:
        return None, None
    nightly_json = next(
        (
            artifact
            for artifact in nightly_row.get("reportArtifacts", [])
            if artifact.get("path") == "reports/nightly/nightly_audit_latest.json" and artifact.get("exists")
        ),
        None,
    )
    if nightly_json is None:
        return None, None

    report_path = REPO_ROOT / "reports/nightly/nightly_audit_latest.json"
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    runtime_summary = payload.get("runtimeSummary")
    if not isinstance(runtime_summary, dict):
        return None, None
    total_seconds = runtime_summary.get("totalMeasuredSeconds")
    slowest_step = runtime_summary.get("slowestStepId")
    return (
        float(total_seconds) if isinstance(total_seconds, int | float) else None,
        slowest_step if isinstance(slowest_step, str) else None,
    )


def runtime_budget_status(latest_runtime_seconds: float | None) -> str:
    if latest_runtime_seconds is None:
        return "unknown"
    if latest_runtime_seconds > NIGHTLY_RUNTIME_BUDGET_SECONDS:
        return "over_budget"
    if latest_runtime_seconds >= NIGHTLY_RUNTIME_WARNING_SECONDS:
        return "warn"
    return "pass"


def budget_adjust_nightly_step(step: dict[str, Any], budget_status: str, slowest_step_id: str | None) -> dict[str, Any]:
    adjusted = dict(step)
    step_id = str(adjusted["stepId"])
    if budget_status == "pass":
        if step_id == "scenario_quick":
            adjusted["candidateAction"] = "keep"
            adjusted["reason"] = "Broad scenario coverage is intentionally preserved while nightly remains under 1 hour."
        elif step_id == "code_health":
            adjusted["candidateAction"] = "measure_more"
            adjusted["reason"] = "Keep for now; code-health is the first trim candidate only if runtime approaches the 1-hour budget."
    elif budget_status == "warn":
        if step_id == "scenario_quick":
            adjusted["candidateAction"] = "measure_more"
            adjusted["reason"] = "Nightly is nearing the 1-hour budget; keep scenario breadth but watch this dominant step."
        elif step_id == "code_health":
            adjusted["candidateAction"] = "measure_more"
            adjusted["reason"] = "Nightly is nearing the 1-hour budget; benchmark-heavy code-health may be trimmed first if needed."
    elif budget_status == "over_budget":
        if step_id in {"scenario_quick", "code_health"}:
            adjusted["candidateAction"] = "trim_candidate"
            adjusted["reason"] = "Nightly is over the 1-hour budget, so this duplicative checkpoint-style work should be reduced."
        elif step_id == "check_fast" and slowest_step_id == "check_fast":
            adjusted["candidateAction"] = "trim_candidate"
            adjusted["reason"] = "Nightly is over budget and check-fast is the slowest step, so a smaller backend nightly gate should be considered."
    else:
        if step_id in {"scenario_quick", "code_health"}:
            adjusted["candidateAction"] = "measure_more"
            adjusted["reason"] = "Latest nightly runtime is unavailable, so keep measuring before trimming coverage."
    return adjusted


def build_coverage_decision_summary(runtime_status: str, latest_runtime_seconds: float | None) -> str:
    if runtime_status == "pass":
        return (
            f"Latest nightly runtime is {latest_runtime_seconds:.1f}s, under the 1-hour budget; "
            "preserve broad scenario coverage and only revisit code-health if runtime needs to be recovered."
        )
    if runtime_status == "warn":
        return (
            f"Latest nightly runtime is {latest_runtime_seconds:.1f}s, approaching the 1-hour budget; "
            "measure another run before trimming broad scenario coverage."
        )
    if runtime_status == "over_budget":
        return (
            f"Latest nightly runtime is {latest_runtime_seconds:.1f}s, over the 1-hour budget; "
            "reduce duplicative nightly scenario/code-health work before changing unique gates."
        )
    return "Latest nightly runtime is unavailable; keep broad coverage and gather another timed nightly before trimming."


def build_coverage_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mechanism_reviews = [build_coverage_mechanism_review(row) for row in rows]
    coverage_map = build_coverage_map()
    latest_runtime_seconds, slowest_step_id = extract_latest_nightly_runtime(rows)
    budget_status = runtime_budget_status(latest_runtime_seconds)
    nightly_steps = [
        budget_adjust_nightly_step(dict(step), budget_status, slowest_step_id)
        for step in NIGHTLY_STEP_COVERAGE
    ]
    candidates = [
        {
            "id": f"mechanism.{entry['task']}",
            "candidateAction": entry["candidateAction"],
            "reason": entry["reason"],
        }
        for entry in mechanism_reviews
        if entry["candidateAction"] in {"trim_candidate", "demote_candidate", "measure_more"}
    ]
    candidates.extend(
        {
            "id": f"nightly.{entry['stepId']}",
            "candidateAction": entry["candidateAction"],
            "reason": entry["reason"],
        }
        for entry in nightly_steps
        if entry["candidateAction"] in {"trim_candidate", "demote_candidate", "measure_more"}
    )
    return {
        "mechanisms": mechanism_reviews,
        "nightlySteps": nightly_steps,
        "trimCandidates": candidates,
        "nightlyRuntimeBudgetSeconds": NIGHTLY_RUNTIME_BUDGET_SECONDS,
        "nightlyRuntimeWarningSeconds": NIGHTLY_RUNTIME_WARNING_SECONDS,
        "latestNightlyRuntimeSeconds": latest_runtime_seconds,
        "latestNightlySlowestStepId": slowest_step_id,
        "runtimeBudgetStatus": budget_status,
        "decisionSummary": build_coverage_decision_summary(budget_status, latest_runtime_seconds),
        "coverageMapSummary": coverage_map["summary"],
    }


def determine_overall_status(rows: list[dict[str, Any]], command_coverage: dict[str, Any]) -> Status:
    if command_coverage["missingFromWrapper"]:
        return "fail"
    if any(row["status"] == "fail" for row in rows):
        return "fail"
    if command_coverage["missingRunbookDirectEquivalent"] or any(row["status"] == "warn" for row in rows):
        return "warn"
    return "pass"


def build_report_payload(
    *,
    context: dict[str, Any],
    rows: list[dict[str, Any]],
    command_coverage: dict[str, Any],
    measure_smoke: bool,
    include_heavy: bool,
    timeout_seconds: int,
    stale_days: int,
    json_path: Path,
    markdown_path: Path,
    explain_coverage: bool = False,
    test_coverage_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recommendations = build_recommendations(rows)
    status_counts = {
        "pass": sum(1 for row in rows if row["status"] == "pass"),
        "warn": sum(1 for row in rows if row["status"] == "warn"),
        "fail": sum(1 for row in rows if row["status"] == "fail"),
        "skipped": sum(1 for row in rows if row["status"] == "skipped"),
    }
    payload = {
        "overallStatus": determine_overall_status(rows, command_coverage),
        "context": context,
        "config": {
            "measureSmoke": measure_smoke,
            "includeHeavy": include_heavy,
            "explainCoverage": explain_coverage,
            "timeoutSeconds": timeout_seconds,
            "staleDays": stale_days,
        },
        "artifactPaths": {
            "json": relative_path(json_path),
            "markdown": relative_path(markdown_path),
        },
        "commandCoverage": command_coverage,
        "canonicalClassEvidence": build_canonical_class_evidence(rows),
        "legacyClassAuditCommands": list(LEGACY_CLASS_AUDIT_COMMANDS),
        "statusCounts": status_counts,
        "recommendations": recommendations,
        "rows": rows,
    }
    if explain_coverage:
        payload["coverageReview"] = build_coverage_review(rows)
    if test_coverage_ledger is not None:
        payload["testCoverageLedger"] = {
            "overallStatus": test_coverage_ledger["overallStatus"],
            "json": test_coverage_ledger["artifactPaths"]["json"],
            "markdown": test_coverage_ledger["artifactPaths"]["markdown"],
            "totalCollected": test_coverage_ledger["summary"]["totalCollected"],
            "notSlowSelected": test_coverage_ledger["summary"]["notSlowSelected"],
            "notSlowDeselected": test_coverage_ledger["summary"]["notSlowDeselected"],
            "fileCount": test_coverage_ledger["summary"]["fileCount"],
        }
        if test_coverage_ledger["overallStatus"] == "fail":
            payload["overallStatus"] = "fail"
        elif payload["overallStatus"] == "pass" and test_coverage_ledger["overallStatus"] == "warn":
            payload["overallStatus"] = "warn"
    return payload


def format_report_markdown(payload: dict[str, Any]) -> str:
    recommendations = payload["recommendations"]
    lines = [
        "# Audit Validation Report",
        "",
        f"- Overall status: `{payload['overallStatus']}`",
        f"- Branch: `{payload['context']['branch']}`",
        f"- Commit: `{payload['context']['commit']}`",
        f"- Measure smoke: `{payload['config']['measureSmoke']}`",
        f"- Include heavy: `{payload['config']['includeHeavy']}`",
        f"- JSON report: `{payload['artifactPaths']['json']}`",
        f"- Markdown report: `{payload['artifactPaths']['markdown']}`",
        "",
        "## Recommendations",
        "",
        f"- Keep in default gate: `{', '.join(recommendations['keepInDefaultGate']) or 'none'}`",
        f"- Checkpoint/release only: `{', '.join(recommendations['checkpointOrReleaseOnly']) or 'none'}`",
        f"- Forensic only: `{', '.join(recommendations['forensicOnly']) or 'none'}`",
        f"- Needs later validation: `{', '.join(recommendations['needsLaterValidation']) or 'none'}`",
        f"- Needs evidence refresh: `{', '.join(recommendations['needsEvidenceRefresh']) or 'none'}`",
        "",
        "## Canonical Class Evidence",
        "",
        f"- Task: `{payload['canonicalClassEvidence']['task']}`",
        f"- Status: `{payload['canonicalClassEvidence']['status']}`",
        f"- Confidence: `{payload['canonicalClassEvidence']['validationConfidence']}`",
        f"- JSON: `{payload['canonicalClassEvidence']['summaryJsonPath']}`",
        f"- Markdown: `{payload['canonicalClassEvidence']['summaryMarkdownPath']}`",
        f"- Legacy class commands: `{', '.join(payload['legacyClassAuditCommands'])}`",
        "",
        "## Mechanisms",
        "",
        "| command | status | gate | confidence | latest status | runtime | report evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        report_paths = ", ".join(
            f"`{artifact['path']}`"
            for artifact in row["reportArtifacts"]
            if artifact.get("exists")
        )
        lines.append(
            f"| `{row['task']}` | `{row['status']}` | `{row['recommendedGateLevel']}` | "
            f"`{row['validationConfidence']}` | `{row['latestStatus']}` | "
            f"`{row['inferredRuntimeClass']}` | {report_paths or '`none`'} |"
        )

    coverage_review = payload.get("coverageReview")
    if isinstance(coverage_review, dict):
        lines.extend(
            [
                "",
                "## Coverage Redundancy Review",
                "",
                f"- Decision summary: {coverage_review['decisionSummary']}",
                f"- Nightly runtime budget seconds: `{coverage_review['nightlyRuntimeBudgetSeconds']}`",
                f"- Nightly runtime warning seconds: `{coverage_review['nightlyRuntimeWarningSeconds']}`",
                f"- Latest nightly runtime seconds: `{coverage_review['latestNightlyRuntimeSeconds']}`",
                f"- Latest nightly slowest step: `{coverage_review['latestNightlySlowestStepId']}`",
                f"- Runtime budget status: `{coverage_review['runtimeBudgetStatus']}`",
                f"- Coverage map risk areas: `{coverage_review['coverageMapSummary']['riskAreaCount']}`",
                f"- Coverage map needs canary: `{', '.join(coverage_review['coverageMapSummary']['needsCanary']) or 'none'}`",
                "",
                "| command | risks | overlap | placement | action | reason |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in coverage_review["mechanisms"]:
            risks = ", ".join(entry["riskAreas"])
            lines.append(
                f"| `{entry['task']}` | {risks} | `{entry['overlapClassification']}` | "
                f"`{entry['recommendedPlacement']}` | `{entry['candidateAction']}` | {entry['reason']} |"
            )

        lines.extend(
            [
                "",
                "## Nightly Step Review",
                "",
                "| step | risks | overlap | placement | action | reason |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for entry in coverage_review["nightlySteps"]:
            risks = ", ".join(entry["riskAreas"])
            lines.append(
                f"| `{entry['stepId']}` | {risks} | `{entry['overlapClassification']}` | "
                f"`{entry['recommendedPlacement']}` | `{entry['candidateAction']}` | {entry['reason']} |"
            )

        lines.extend(["", "## Candidate Trims", ""])
        for entry in coverage_review["trimCandidates"]:
            lines.append(f"- `{entry['id']}`: `{entry['candidateAction']}` - {entry['reason']}")

    test_ledger = payload.get("testCoverageLedger")
    if isinstance(test_ledger, dict):
        lines.extend(
            [
                "",
                "## Test Coverage Ledger",
                "",
                f"- Status: `{test_ledger['overallStatus']}`",
                f"- JSON: `{test_ledger['json']}`",
                f"- Markdown: `{test_ledger['markdown']}`",
                f"- Total collected: `{test_ledger['totalCollected']}`",
                f"- Not-slow selected: `{test_ledger['notSlowSelected']}`",
                f"- Not-slow deselected: `{test_ledger['notSlowDeselected']}`",
                f"- Test files: `{test_ledger['fileCount']}`",
            ]
        )

    coverage = payload["commandCoverage"]
    lines.extend(
        [
            "",
            "## Command Coverage",
            "",
            f"- Missing from wrapper: `{', '.join(coverage['missingFromWrapper']) or 'none'}`",
            f"- Missing runbook direct equivalent: `{', '.join(coverage['missingRunbookDirectEquivalent']) or 'none'}`",
            f"- Undocumented wrapper tasks: `{', '.join(coverage['undocumentedWrapperTasks']) or 'none'}`",
            f"- Unknown wrapper tasks: `{', '.join(coverage['unknownWrapperTasks']) or 'none'}`",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    now = datetime.now(tz=UTC)
    dev_ps1_text = read_text(REPO_ROOT / "scripts" / "dev.ps1")
    runbook_text = read_text(REPO_ROOT / "docs" / "AUDIT_RUNBOOK.md")
    wrapper_tasks = extract_dev_tasks(dev_ps1_text)
    runbook_mappings = extract_runbook_direct_equivalents(runbook_text)
    command_coverage = build_command_coverage(wrapper_tasks, runbook_mappings)
    rows = [
        build_mechanism_row(
            mechanism=mechanism,
            wrapper_tasks=wrapper_tasks,
            runbook_mappings=runbook_mappings,
            now=now,
            stale_days=args.stale_days,
        )
        for mechanism in MECHANISMS
    ]
    maybe_measure_rows(
        rows=rows,
        mechanisms=MECHANISMS,
        measure_smoke=args.measure_smoke,
        include_heavy=args.include_heavy,
        timeout_seconds=args.timeout_seconds,
    )
    context = collect_git_context()
    test_coverage_ledger: dict[str, Any] | None = None
    if args.explain_coverage:
        full_collection = collect_pytest_inventory()
        not_slow_collection = collect_pytest_inventory('not slow')
        test_coverage_ledger = build_test_coverage_ledger(
            context=context,
            full_collection=full_collection,
            not_slow_collection=not_slow_collection,
            mechanism_rows=rows,
        )
        write_json_report(DEFAULT_TEST_LEDGER_JSON_PATH, test_coverage_ledger)
        write_text_report(DEFAULT_TEST_LEDGER_MARKDOWN_PATH, format_test_coverage_ledger_markdown(test_coverage_ledger))
    payload = build_report_payload(
        context=context,
        rows=rows,
        command_coverage=command_coverage,
        measure_smoke=args.measure_smoke,
        include_heavy=args.include_heavy,
        timeout_seconds=args.timeout_seconds,
        stale_days=args.stale_days,
        json_path=args.json_path,
        markdown_path=args.markdown_path,
        explain_coverage=args.explain_coverage,
        test_coverage_ledger=test_coverage_ledger,
    )
    write_json_report(args.json_path, payload)
    write_text_report(args.markdown_path, format_report_markdown(payload))
    print(format_report_markdown(payload))


if __name__ == "__main__":
    main()
