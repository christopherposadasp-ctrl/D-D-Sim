from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine import run_batch
from backend.engine.models.state import EncounterConfig
from scripts.audit_common import relative_path, write_json_report, write_text_report

LIVE_SOURCE_ROOTS = (
    REPO_ROOT / "backend",
    REPO_ROOT / "src" / "ui",
    REPO_ROOT / "src" / "shared",
)
FRONTEND_ROOT = REPO_ROOT / "src"
LEGACY_ENGINE_IMPORT_MARKERS = ("../engine", "./engine")
ROOT_ARTIFACT_PATTERNS = (
    "scenario_*.json",
    "scenario_*.jsonl",
    "audit_*.json",
    "audit_*.jsonl",
    "benchmark_*.json",
    "benchmark_*.jsonl",
)
BENCHMARK_PRESET_IDS = ("goblin_screen", "orc_push", "marsh_predators")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a manual code-health audit for the live simulator.")
    parser.add_argument("--benchmark-batch-size", type=int, default=300, help="Batch size used for each scenario benchmark.")
    parser.add_argument("--largest-limit", type=int, default=10, help="Number of largest live modules to report.")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON.")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write the report to reports/code_health_audit.json as well as printing it.",
    )
    return parser.parse_args()


def count_lines(path: Path) -> int:
    return sum(1 for _ in path.read_text().splitlines())


def get_largest_live_modules(limit: int) -> list[dict[str, object]]:
    source_files: list[Path] = []
    for root in LIVE_SOURCE_ROOTS:
        if not root.exists():
            continue
        for suffix in ("*.py", "*.ts", "*.tsx"):
            source_files.extend(path for path in root.rglob(suffix) if path.is_file())

    ranked = sorted(source_files, key=count_lines, reverse=True)
    return [
        {
            "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "lineCount": count_lines(path),
        }
        for path in ranked[:limit]
    ]


def find_legacy_frontend_imports() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    if not FRONTEND_ROOT.exists():
        return findings

    for path in FRONTEND_ROOT.rglob("*.ts*"):
        if not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if any(marker in line for marker in LEGACY_ENGINE_IMPORT_MARKERS):
                findings.append(
                    {
                        "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )
    return findings


def find_root_artifacts() -> list[str]:
    artifacts: list[str] = []
    for pattern in ROOT_ARTIFACT_PATTERNS:
        artifacts.extend(path.name for path in REPO_ROOT.glob(pattern) if path.is_file())
    return sorted(set(artifacts))


def run_benchmark(preset_id: str, batch_size: int) -> dict[str, object]:
    config = EncounterConfig(
        seed=f"code-health-{preset_id}",
        enemy_preset_id=preset_id,
        batch_size=batch_size,
        player_behavior="balanced",
        monster_behavior="combined",
    )

    started_at = time.perf_counter()
    summary = run_batch(config)
    elapsed_seconds = time.perf_counter() - started_at
    total_runs = summary.total_runs

    return {
        "scenarioId": preset_id,
        "batchSize": batch_size,
        "totalRuns": total_runs,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "runsPerSecond": round(total_runs / elapsed_seconds, 2) if elapsed_seconds > 0 else None,
    }


def build_report(batch_size: int, largest_limit: int) -> dict[str, object]:
    return {
        "largestLiveModules": get_largest_live_modules(largest_limit),
        "legacyFrontendImports": find_legacy_frontend_imports(),
        "rootArtifacts": find_root_artifacts(),
        "benchmarks": [run_benchmark(preset_id, batch_size) for preset_id in BENCHMARK_PRESET_IDS],
    }


def format_report(report: dict[str, object]) -> str:
    lines = ["# Code Health Audit", ""]

    lines.append("## Largest Live Modules")
    for entry in report["largestLiveModules"]:
        lines.append(f"- {entry['path']}: {entry['lineCount']} lines")
    if not report["largestLiveModules"]:
        lines.append("- none")

    lines.append("")
    lines.append("## Legacy Frontend Imports")
    for entry in report["legacyFrontendImports"]:
        lines.append(f"- {entry['path']}:{entry['line']} -> {entry['text']}")
    if not report["legacyFrontendImports"]:
        lines.append("- none")

    lines.append("")
    lines.append("## Root Artifacts")
    for artifact in report["rootArtifacts"]:
        lines.append(f"- {artifact}")
    if not report["rootArtifacts"]:
        lines.append("- none")

    lines.append("")
    lines.append("## Benchmarks")
    for entry in report["benchmarks"]:
        lines.append(
            f"- {entry['scenarioId']}: {entry['elapsedSeconds']}s for {entry['totalRuns']} runs "
            f"({entry['runsPerSecond']} runs/sec)"
        )

    return "\n".join(lines)


def maybe_write_report(report: dict[str, object]) -> tuple[Path, Path]:
    json_path = REPO_ROOT / "reports" / "code_health_audit.json"
    markdown_path = REPO_ROOT / "reports" / "code_health_audit.md"
    write_json_report(json_path, report)
    write_text_report(markdown_path, format_report(report))
    return json_path, markdown_path


def main() -> None:
    args = parse_args()
    report = build_report(args.benchmark_batch_size, args.largest_limit)

    if args.write_report:
        json_path, markdown_path = maybe_write_report(report)
        print(f"Wrote {relative_path(json_path)} and {relative_path(markdown_path)}")

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(format_report(report))


if __name__ == "__main__":
    main()
