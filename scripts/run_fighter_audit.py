from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine.services.fighter_audit import (
    FighterAuditConfig,
    audit_fighter_profiles,
    build_full_fighter_audit_config,
    build_level1_fighter_comparison,
    build_preset_aggregates,
    build_quick_fighter_audit_config,
    build_report_payload,
    format_fighter_audit_report,
    get_fighter_audit_player_preset_ids,
    get_fighter_audit_scenario_ids,
)

DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "fighter_audit"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "fighter_audit_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "fighter_audit_latest.md"
RULES_GATE_TARGETS = (
    "tests/rules/test_player_framework.py",
    "tests/rules/test_ai.py",
    "tests/rules/test_rules.py",
    "tests/rules/test_fighter_audit.py",
    "-k",
    "fighter or action_surge",
    "-q",
)


class FighterAuditConsoleProgress:
    def __init__(self) -> None:
        self.last_counts: dict[tuple[str, str], int] = {}

    def __call__(self, label: str, stage: str, details: dict[str, object]) -> None:
        status = details.get("status")
        if status == "start":
            print(f"[{label}] {stage} pass...")
            return
        if status == "complete":
            print(
                f"[{label}] {stage} complete"
                f"{self._format_completion_suffix(stage, details)}."
            )
            return

        current = int(details.get("current", 0))
        total = int(details.get("total", 0))
        if total <= 0 or current <= 0:
            return

        key = (label, stage)
        if self.last_counts.get(key) == current:
            return
        if not self._should_emit(stage, current, total):
            return

        self.last_counts[key] = current
        suffix = ""
        if "playerBehavior" in details:
            suffix = f" ({details['playerBehavior']})"
        elif "monsterBehavior" in details:
            suffix = f" ({details['monsterBehavior']})"
        print(f"[{label}] {stage}: {current}/{total}{suffix}")

    def _should_emit(self, stage: str, current: int, total: int) -> bool:
        if current == 1 or current == total:
            return True
        interval = 1 if stage == "replay" else max(1, total // 5)
        return current % interval == 0

    def _format_completion_suffix(self, stage: str, details: dict[str, object]) -> str:
        if stage == "complete":
            return (
                f" ({details.get('status', 'pass')}, "
                f"{details.get('warningCount', 0)} warning(s), "
                f"{details.get('failureCount', 0)} failure(s))"
            )
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Fighter verification audit.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenario_ids",
        help="Audit only the specified scenario id. Repeat to include more.",
    )
    parser.add_argument(
        "--player-preset",
        action="append",
        dest="player_preset_ids",
        help="Audit only the specified player preset id. Repeat to include more.",
    )
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument("--quick", action="store_true", help="Use a lighter audit profile. This is the default.")
    profile_group.add_argument("--full", action="store_true", help="Use the full audit profile.")
    parser.add_argument(
        "--fixed-seed-runs",
        type=int,
        default=None,
        help="Override the number of fixed-seed smart/dumb replay checks per scenario.",
    )
    parser.add_argument(
        "--behavior-batch-size",
        type=int,
        default=None,
        help="Override the serial behavior sanity batch size.",
    )
    parser.add_argument(
        "--health-batch-size",
        type=int,
        default=None,
        help="Override the combined health batch size.",
    )
    parser.add_argument("--skip-rules-gate", action="store_true", help="Skip the targeted pytest rules gate.")
    parser.add_argument("--json", action="store_true", help="Print the final JSON payload to stdout.")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH, help="Write the JSON report to this path.")
    parser.add_argument(
        "--markdown-path",
        type=Path,
        default=DEFAULT_MARKDOWN_PATH,
        help="Write the Markdown report to this path.",
    )
    parser.add_argument("--no-report", action="store_true", help="Skip writing report artifacts under reports/.")
    return parser.parse_args()


def build_config_from_args(args: argparse.Namespace) -> tuple[str, FighterAuditConfig]:
    mode = "full" if args.full else "quick"
    config = build_full_fighter_audit_config() if mode == "full" else build_quick_fighter_audit_config()

    if args.fixed_seed_runs is not None:
        config = replace(config, fixed_seed_runs=args.fixed_seed_runs)
    if args.behavior_batch_size is not None:
        config = replace(config, behavior_batch_size=args.behavior_batch_size)
    if args.health_batch_size is not None:
        config = replace(config, health_batch_size=args.health_batch_size)

    return mode, config


def run_rules_gate() -> dict[str, object]:
    command = [sys.executable, "-m", "pytest", *RULES_GATE_TARGETS]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    stderr_lines = [line for line in completed.stderr.splitlines() if line.strip()]
    tail = (stdout_lines + stderr_lines)[-12:]

    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": " ".join(command),
        "exitCode": completed.returncode,
        "stdoutTail": tail,
    }


def write_report(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def main() -> None:
    args = parse_args()
    mode, config = build_config_from_args(args)
    selected_scenarios = tuple(args.scenario_ids) if args.scenario_ids else get_fighter_audit_scenario_ids()
    selected_player_presets = tuple(args.player_preset_ids) if args.player_preset_ids else get_fighter_audit_player_preset_ids()

    print(
        f"Running Fighter audit in {mode} mode for "
        f"{len(selected_player_presets)} preset(s) across {len(selected_scenarios)} scenario(s)."
    )
    print(
        "Config:"
        f" fixed seeds {config.fixed_seed_runs},"
        f" behavior batch {config.behavior_batch_size},"
        f" health batch {config.health_batch_size}"
    )

    rules_gate = {"status": "skipped", "command": "", "exitCode": 0, "stdoutTail": []}
    if not args.skip_rules_gate:
        print("Running targeted Fighter rules gate...")
        rules_gate = run_rules_gate()
        print(f"Rules gate: {rules_gate['status']}")

    if rules_gate["status"] == "fail":
        payload = {
            "mode": mode,
            "config": {
                "fixedSeedRuns": config.fixed_seed_runs,
                "behaviorBatchSize": config.behavior_batch_size,
                "healthBatchSize": config.health_batch_size,
            },
            "playerPresetIds": list(selected_player_presets),
            "scenarioIds": list(selected_scenarios),
            "overallStatus": "fail",
            "rulesGate": rules_gate,
            "rows": [],
            "presetAggregates": [],
            "comparisons": {},
        }
        markdown = "\n".join(
            [
                "## Rules Gate",
                f"- Status: {rules_gate['status']}",
                f"- Command: `{rules_gate['command']}`",
                *(f"- {line}" for line in rules_gate["stdoutTail"]),
                "",
                "Audit stopped before replay and batch passes because the deterministic Fighter rules gate failed.",
            ]
        )
        if not args.no_report:
            write_report(args.json_path, json.dumps(payload, indent=2) + "\n")
            write_report(args.markdown_path, markdown + "\n")
            print(f"Wrote failure reports to {args.json_path} and {args.markdown_path}")
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(markdown)
        raise SystemExit(1)

    progress = FighterAuditConsoleProgress()
    rows = audit_fighter_profiles(
        config=config,
        player_preset_ids=selected_player_presets,
        scenario_ids=selected_scenarios,
        progress_callback=progress,
    )
    comparisons = {
        "fighterLevel2TrioVsFighterLevel1Trio": build_level1_fighter_comparison(
            rows,
            config,
            progress_callback=progress,
        ),
    }
    payload = build_report_payload(rows, config, rules_gate, comparisons=comparisons)
    payload["mode"] = mode
    payload["selectedPlayerPresetIds"] = list(selected_player_presets)
    payload["selectedScenarioIds"] = list(selected_scenarios)

    aggregates = build_preset_aggregates(rows)
    markdown = format_fighter_audit_report(
        rows,
        aggregates,
        rules_gate=rules_gate,
        fighter_comparison=comparisons["fighterLevel2TrioVsFighterLevel1Trio"],
    )

    if not args.no_report:
        write_report(args.json_path, json.dumps(payload, indent=2) + "\n")
        write_report(args.markdown_path, markdown + "\n")
        print(f"Wrote reports to {args.json_path} and {args.markdown_path}")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("")
        print(markdown)


if __name__ == "__main__":
    main()
