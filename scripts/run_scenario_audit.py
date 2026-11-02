from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine.services.scenario_audit import (
    ScenarioAuditConfig,
    ScenarioAuditRow,
    audit_scenario,
    build_full_scenario_audit_config,
    build_quick_scenario_audit_config,
    build_report_payload,
    format_scenario_audit_report,
    get_active_scenario_ids,
)

DEFAULT_REPORT_PATH = REPO_ROOT / "reports" / "scenario_audit_latest.json"


class ScenarioAuditConsoleProgress:
    """Emit concise progress updates for long-running scenario audits."""

    def __init__(self) -> None:
        self.last_counts: dict[tuple[str, str], int] = {}

    def __call__(self, preset_id: str, stage: str, details: dict[str, object]) -> None:
        status = details.get("status")
        if stage == "structural":
            self._print_stage_status(preset_id, "structural", status, details)
            return

        if stage == "smoke":
            if status:
                self._print_stage_status(preset_id, "smoke", status, details)
                return
            self._print_counter(
                preset_id,
                stage,
                int(details.get("current", 0)),
                int(details.get("total", 0)),
                suffix=f" ({details.get('playerBehavior', 'balanced')})",
            )
            return

        if stage == "mechanic":
            if status:
                self._print_stage_status(preset_id, "mechanic", status, details)
                return
            self._print_counter(
                preset_id,
                stage,
                int(details.get("current", 0)),
                int(details.get("total", 0)),
            )
            return

        if stage == "health":
            if status:
                self._print_stage_status(preset_id, "health", status, details)
                return
            monster_behavior = str(details.get("monsterBehavior", "combined"))
            self._print_counter(
                preset_id,
                stage,
                int(details.get("current", 0)),
                int(details.get("total", 0)),
                suffix=f" ({monster_behavior})",
            )
            return

        if stage == "complete":
            print(
                f"[{preset_id}] complete: {details.get('status', 'pass')} "
                f"with {details.get('warningCount', 0)} warning(s)."
            )

    def _print_stage_status(self, preset_id: str, stage: str, status: object, details: dict[str, object]) -> None:
        if status == "start":
            print(f"[{preset_id}] {stage} pass...")
            return

        if status == "complete":
            if stage == "structural":
                print(f"[{preset_id}] structural pass complete ({details.get('issueCount', 0)} issue(s)).")
            elif stage == "smoke":
                print(f"[{preset_id}] smoke pass complete ({details.get('issueCount', 0)} issue(s)).")
            elif stage == "mechanic":
                print(
                    f"[{preset_id}] mechanic pass complete "
                    f"(minimum signature count {details.get('signatureMechanicCount', 0)})."
                )
            elif stage == "health":
                player_win_rate = float(details.get("playerWinRate", 0.0)) * 100
                enemy_win_rate = float(details.get("enemyWinRate", 0.0)) * 100
                print(
                    f"[{preset_id}] health pass complete "
                    f"(players {player_win_rate:.1f}%, enemies {enemy_win_rate:.1f}%)."
                )

    def _print_counter(self, preset_id: str, stage: str, current: int, total: int, suffix: str = "") -> None:
        if total <= 0 or current <= 0:
            return

        key = (preset_id, stage)
        if not self._should_emit(stage, current, total):
            return

        if self.last_counts.get(key) == current:
            return

        self.last_counts[key] = current
        print(f"[{preset_id}] {stage}: {current}/{total}{suffix}")

    def _should_emit(self, stage: str, current: int, total: int) -> bool:
        if current == total or current == 1:
            return True

        if stage == "smoke":
            interval = 1
        elif stage == "mechanic":
            interval = max(1, total // 5)
        else:
            interval = max(1, total // 10)

        return current % interval == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the scenario function audit across the active preset catalog.")
    parser.add_argument("--scenario", action="append", dest="scenario_ids", help="Audit only the specified scenario id. Repeat to run more than one.")
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument("--quick", action="store_true", help="Use the quick audit profile. This is the default.")
    profile_group.add_argument("--full", action="store_true", help="Use the full audit profile.")
    parser.add_argument("--smart-smoke-runs", type=int, default=None, help="Override the number of smart-player smoke runs per scenario.")
    parser.add_argument("--dumb-smoke-runs", type=int, default=None, help="Override the number of dumb-player smoke runs per scenario.")
    parser.add_argument("--mechanic-runs", type=int, default=None, help="Override the number of balanced-vs-balanced runs used for signature checks.")
    parser.add_argument("--health-batch-size", type=int, default=None, help="Override the combined-batch size used for the scenario health pass.")
    parser.add_argument("--json", action="store_true", help="Print the audit payload as JSON instead of a markdown table.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH, help="Write rolling partial and final results to this JSON file.")
    parser.add_argument("--no-report", action="store_true", help="Skip writing rolling reports under reports/.")
    return parser.parse_args()


def build_config_from_args(args: argparse.Namespace) -> tuple[str, ScenarioAuditConfig]:
    mode = "full" if args.full else "quick"
    config = build_full_scenario_audit_config() if mode == "full" else build_quick_scenario_audit_config()

    if args.smart_smoke_runs is not None:
        config = replace(config, smart_smoke_runs=args.smart_smoke_runs)
    if args.dumb_smoke_runs is not None:
        config = replace(config, dumb_smoke_runs=args.dumb_smoke_runs)
    if args.mechanic_runs is not None:
        config = replace(config, mechanic_runs=args.mechanic_runs)
    if args.health_batch_size is not None:
        config = replace(config, health_batch_size=args.health_batch_size)

    return mode, config


def build_partial_report_payload(
    rows: list[ScenarioAuditRow],
    config: ScenarioAuditConfig,
    mode: str,
    selected_ids: tuple[str, ...],
    completed_ids: list[str],
) -> dict[str, object]:
    payload = build_report_payload(rows, config)
    payload["mode"] = mode
    payload["selectedScenarioIds"] = list(selected_ids)
    payload["completedScenarioIds"] = list(completed_ids)
    payload["pendingScenarioIds"] = [preset_id for preset_id in selected_ids if preset_id not in completed_ids]
    return payload


def write_report(
    report_path: Path,
    rows: list[ScenarioAuditRow],
    config: ScenarioAuditConfig,
    mode: str,
    selected_ids: tuple[str, ...],
    completed_ids: list[str],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_partial_report_payload(rows, config, mode, selected_ids, completed_ids)
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    mode, config = build_config_from_args(args)
    selected_ids = tuple(args.scenario_ids) if args.scenario_ids else get_active_scenario_ids()

    print(
        f"Running scenario audit in {mode} mode across {len(selected_ids)} scenario(s): "
        f"{', '.join(selected_ids)}"
    )
    print(
        "Config:"
        f" smart smoke {config.smart_smoke_runs},"
        f" dumb smoke {config.dumb_smoke_runs},"
        f" mechanic {config.mechanic_runs},"
        f" health batch {config.health_batch_size}"
    )

    rows: list[ScenarioAuditRow] = []
    completed_ids: list[str] = []
    progress = ScenarioAuditConsoleProgress()

    if not args.no_report:
        write_report(args.report_path, rows, config, mode, selected_ids, completed_ids)
        print(f"Writing rolling report to {args.report_path}")

    for preset_id in selected_ids:
        row = audit_scenario(preset_id, config, progress_callback=progress)
        rows.append(row)
        completed_ids.append(preset_id)
        if not args.no_report:
            write_report(args.report_path, rows, config, mode, selected_ids, completed_ids)

    payload = build_partial_report_payload(rows, config, mode, selected_ids, completed_ids)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("")
        print(format_scenario_audit_report(rows))


if __name__ == "__main__":
    main()
