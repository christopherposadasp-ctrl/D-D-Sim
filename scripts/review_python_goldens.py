from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.engine import run_batch, run_encounter, summarize_encounter
from backend.engine.models.state import EncounterConfig

CaseKind = Literal["run", "batch"]
Classification = Literal["pending", "intended", "unexpected"]

DEFAULT_CASE_NAMES = (
    "goblin-screen-default",
    "orc-push-evil",
    "wolf-harriers-balanced-batch",
    "marsh-predators-combined-batch",
)
DEFAULT_FIXTURE_PATH = REPO_ROOT / "tests" / "golden" / "python_golden_fixtures.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "pass1" / "golden_review"
DEFAULT_JSON_PATH = DEFAULT_REPORT_DIR / "python_goldens_review_latest.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_REPORT_DIR / "python_goldens_review_latest.md"


@dataclass(frozen=True)
class FixtureCase:
    kind: CaseKind
    name: str
    index: int
    payload: dict[str, object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review and selectively refresh drifting Python golden cases.")
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Path to tests/golden/python_golden_fixtures.json.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_names",
        default=None,
        help="Golden case name to review. Repeat for multiple cases.",
    )
    parser.add_argument(
        "--classify",
        action="append",
        dest="classifications",
        default=None,
        help="Classification override in the form case_name=intended|unexpected.",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help="Path for the machine-readable review report.",
    )
    parser.add_argument(
        "--markdown-path",
        type=Path,
        default=DEFAULT_MARKDOWN_PATH,
        help="Path for the Markdown review report.",
    )
    parser.add_argument(
        "--write-fixture",
        action="store_true",
        help="Rewrite only the reviewed fixture entries after all selected drifts are classified intended.",
    )
    return parser.parse_args()


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def load_fixture_payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected fixture root object in {path}")
    return payload


def iter_fixture_cases(fixtures: dict[str, object]) -> list[FixtureCase]:
    cases: list[FixtureCase] = []
    run_cases = fixtures.get("runCases", [])
    if isinstance(run_cases, list):
        for index, payload in enumerate(run_cases):
            if isinstance(payload, dict):
                cases.append(FixtureCase("run", str(payload.get("name", f"run-{index}")), index, payload))
    batch_cases = fixtures.get("batchCases", [])
    if isinstance(batch_cases, list):
        for index, payload in enumerate(batch_cases):
            if isinstance(payload, dict):
                cases.append(FixtureCase("batch", str(payload.get("name", f"batch-{index}")), index, payload))
    return cases


def parse_classification_overrides(raw_entries: list[str] | None) -> dict[str, Classification]:
    overrides: dict[str, Classification] = {}
    for raw_entry in raw_entries or []:
        case_name, separator, raw_value = raw_entry.partition("=")
        if not separator:
            raise ValueError(f"Invalid --classify value `{raw_entry}`; expected case_name=intended|unexpected.")
        normalized_value = raw_value.strip().lower()
        if normalized_value not in {"intended", "unexpected"}:
            raise ValueError(f"Invalid classification `{raw_value}` for case `{case_name}`.")
        overrides[case_name.strip()] = normalized_value  # type: ignore[assignment]
    return overrides


def diff_scalar_fields(expected: dict[str, object], actual: dict[str, object]) -> list[str]:
    keys = sorted(set(expected) | set(actual))
    changed: list[str] = []
    for key in keys:
        if expected.get(key) != actual.get(key):
            changed.append(key)
    return changed


def find_first_divergent_event(expected_events: list[object], actual_events: list[object]) -> dict[str, object] | None:
    compared = min(len(expected_events), len(actual_events))
    for index in range(compared):
        expected_event = expected_events[index]
        actual_event = actual_events[index]
        if expected_event != actual_event:
            if isinstance(expected_event, dict) and isinstance(actual_event, dict):
                return {
                    "index": index,
                    "expectedEventType": expected_event.get("eventType"),
                    "actualEventType": actual_event.get("eventType"),
                    "expectedActorId": expected_event.get("actorId"),
                    "actualActorId": actual_event.get("actorId"),
                    "expectedText": expected_event.get("textSummary"),
                    "actualText": actual_event.get("textSummary"),
                }
            return {"index": index, "expected": expected_event, "actual": actual_event}

    if len(expected_events) != len(actual_events):
        return {
            "index": compared,
            "expectedEventCount": len(expected_events),
            "actualEventCount": len(actual_events),
            "expectedText": None,
            "actualText": None,
        }
    return None


def review_run_case(case: FixtureCase, classification: Classification) -> dict[str, object]:
    config = EncounterConfig.model_validate(case.payload["config"])
    result = run_encounter(config)
    actual_result = result.model_dump(by_alias=True)
    actual_summary = summarize_encounter(result.final_state).model_dump(by_alias=True)

    expected_result = case.payload["result"]
    expected_summary = case.payload["summary"]
    if not isinstance(expected_result, dict) or not isinstance(expected_summary, dict):
        raise ValueError(f"Run case `{case.name}` is missing result or summary.")

    expected_events = expected_result.get("events", [])
    actual_events = actual_result.get("events", [])
    expected_replay_frames = expected_result.get("replayFrames", [])
    actual_replay_frames = actual_result.get("replayFrames", [])
    expected_final_state = expected_result.get("finalState", {})
    actual_final_state = actual_result.get("finalState", {})

    return {
        "name": case.name,
        "kind": case.kind,
        "classification": classification,
        "driftDetected": actual_result != expected_result or actual_summary != expected_summary,
        "config": case.payload["config"],
        "expectedSummary": expected_summary,
        "actualSummary": actual_summary,
        "summaryDiffFields": diff_scalar_fields(expected_summary, actual_summary),
        "expectedRound": expected_final_state.get("round") if isinstance(expected_final_state, dict) else None,
        "actualRound": actual_final_state.get("round") if isinstance(actual_final_state, dict) else None,
        "expectedRngState": expected_final_state.get("rngState") if isinstance(expected_final_state, dict) else None,
        "actualRngState": actual_final_state.get("rngState") if isinstance(actual_final_state, dict) else None,
        "expectedEventCount": len(expected_events) if isinstance(expected_events, list) else None,
        "actualEventCount": len(actual_events) if isinstance(actual_events, list) else None,
        "expectedReplayFrameCount": len(expected_replay_frames) if isinstance(expected_replay_frames, list) else None,
        "actualReplayFrameCount": len(actual_replay_frames) if isinstance(actual_replay_frames, list) else None,
        "firstDivergentEvent": find_first_divergent_event(
            expected_events if isinstance(expected_events, list) else [],
            actual_events if isinstance(actual_events, list) else [],
        ),
        "actualResult": actual_result,
    }


def review_batch_case(case: FixtureCase, classification: Classification) -> dict[str, object]:
    config = EncounterConfig.model_validate(case.payload["config"])
    actual_summary = run_batch(config).model_dump(by_alias=True)
    repeat_summary = run_batch(config).model_dump(by_alias=True)

    expected_summary = case.payload["summary"]
    if not isinstance(expected_summary, dict):
        raise ValueError(f"Batch case `{case.name}` is missing summary.")

    return {
        "name": case.name,
        "kind": case.kind,
        "classification": classification,
        "driftDetected": actual_summary != expected_summary,
        "config": case.payload["config"],
        "expectedSummary": expected_summary,
        "actualSummary": actual_summary,
        "summaryDiffFields": diff_scalar_fields(expected_summary, actual_summary),
        "deterministic": actual_summary == repeat_summary,
        "repeatSummary": repeat_summary,
    }


def review_fixture_cases(
    cases: list[FixtureCase],
    selected_case_names: set[str],
    classification_overrides: dict[str, Classification],
) -> tuple[list[dict[str, object]], list[str]]:
    selected_reviews: list[dict[str, object]] = []
    unselected_drifts: list[str] = []
    for case in cases:
        classification = classification_overrides.get(case.name, "pending")
        if case.kind == "run":
            review = review_run_case(case, classification)
        else:
            review = review_batch_case(case, classification)

        if case.name in selected_case_names:
            selected_reviews.append(review)
        elif bool(review["driftDetected"]):
            unselected_drifts.append(case.name)
    return selected_reviews, sorted(unselected_drifts)


def build_report(
    fixture_path: Path,
    selected_reviews: list[dict[str, object]],
    selected_case_names: set[str],
    unselected_drifts: list[str],
) -> dict[str, object]:
    reviewed_names = {str(review["name"]) for review in selected_reviews}
    missing_selected = sorted(selected_case_names - reviewed_names)
    status = "pass"
    if unselected_drifts:
        status = "fail"
    elif any(bool(review["driftDetected"]) for review in selected_reviews):
        status = "warn"

    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "fixturePath": relative_path(fixture_path),
        "selectedCases": sorted(selected_case_names),
        "selectedCaseCount": len(selected_case_names),
        "reviewedCaseCount": len(selected_reviews),
        "missingSelectedCases": missing_selected,
        "unselectedDrifts": unselected_drifts,
        "overallStatus": status,
        "reviews": selected_reviews,
    }


def format_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Python Golden Review",
        "",
        f"- Generated: `{report['generatedAt']}`",
        f"- Fixture: `{report['fixturePath']}`",
        f"- Overall status: `{report['overallStatus']}`",
        f"- Reviewed cases: `{report['reviewedCaseCount']}/{report['selectedCaseCount']}`",
    ]

    missing_selected = report.get("missingSelectedCases", [])
    if isinstance(missing_selected, list) and missing_selected:
        lines.append(f"- Missing selected cases: {', '.join(str(entry) for entry in missing_selected)}")

    unselected_drifts = report.get("unselectedDrifts", [])
    if isinstance(unselected_drifts, list) and unselected_drifts:
        lines.append(f"- Unselected drifts: {', '.join(str(entry) for entry in unselected_drifts)}")

    lines.extend(["", "## Reviewed Cases"])
    for review in report["reviews"]:
        lines.extend(
            [
                "",
                f"### {review['name']}",
                f"- Kind: `{review['kind']}`",
                f"- Classification: `{review['classification']}`",
                f"- Drift detected: `{review['driftDetected']}`",
                f"- Summary fields changed: `{', '.join(review['summaryDiffFields']) if review['summaryDiffFields'] else 'none'}`",
            ]
        )
        if review["kind"] == "run":
            lines.extend(
                [
                    f"- Round: `{review['expectedRound']}` -> `{review['actualRound']}`",
                    f"- RNG state: `{review['expectedRngState']}` -> `{review['actualRngState']}`",
                    f"- Event count: `{review['expectedEventCount']}` -> `{review['actualEventCount']}`",
                    f"- Replay frames: `{review['expectedReplayFrameCount']}` -> `{review['actualReplayFrameCount']}`",
                ]
            )
            first_diff = review.get("firstDivergentEvent")
            if isinstance(first_diff, dict):
                lines.append(f"- First divergent event index: `{first_diff.get('index')}`")
                lines.append(f"- Expected event: `{first_diff.get('expectedText')}`")
                lines.append(f"- Actual event: `{first_diff.get('actualText')}`")
        else:
            lines.append(f"- Deterministic on repeat run: `{review['deterministic']}`")
    lines.append("")
    return "\n".join(lines)


def validate_fixture_write(report: dict[str, object]) -> list[str]:
    errors: list[str] = []
    unselected_drifts = report.get("unselectedDrifts", [])
    if isinstance(unselected_drifts, list) and unselected_drifts:
        errors.append("Unselected golden cases also drifted; expand review scope before writing fixtures.")

    missing_selected = report.get("missingSelectedCases", [])
    if isinstance(missing_selected, list) and missing_selected:
        errors.append("One or more selected cases were not reviewed.")

    reviews = report.get("reviews", [])
    if not isinstance(reviews, list):
        errors.append("Review report is malformed.")
        return errors

    pending = [str(review.get("name")) for review in reviews if review.get("driftDetected") and review.get("classification") == "pending"]
    if pending:
        errors.append(f"Classify drifting cases before writing fixtures: {', '.join(pending)}.")

    unexpected = [
        str(review.get("name"))
        for review in reviews
        if review.get("driftDetected") and review.get("classification") == "unexpected"
    ]
    if unexpected:
        errors.append(f"Refusing to rewrite fixtures for cases classified unexpected: {', '.join(unexpected)}.")

    nondeterministic = [
        str(review.get("name"))
        for review in reviews
        if review.get("kind") == "batch" and review.get("driftDetected") and not review.get("deterministic")
    ]
    if nondeterministic:
        errors.append(f"Batch drift was not deterministic on repeat run: {', '.join(nondeterministic)}.")

    return errors


def apply_review_updates(fixtures: dict[str, object], selected_reviews: list[dict[str, object]]) -> dict[str, object]:
    updated = deepcopy(fixtures)
    run_cases = updated.get("runCases")
    batch_cases = updated.get("batchCases")
    if not isinstance(run_cases, list) or not isinstance(batch_cases, list):
        raise ValueError("Fixture payload is missing runCases or batchCases.")

    review_lookup = {str(review["name"]): review for review in selected_reviews}
    for case_list, kind in ((run_cases, "run"), (batch_cases, "batch")):
        for payload in case_list:
            if not isinstance(payload, dict):
                continue
            review = review_lookup.get(str(payload.get("name")))
            if not review or review["kind"] != kind or not review["driftDetected"]:
                continue
            if kind == "run":
                payload["result"] = review["actualResult"]
                payload["summary"] = review["actualSummary"]
            else:
                payload["summary"] = review["actualSummary"]
    return updated


def write_report_files(report: dict[str, object], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(format_markdown(report), encoding="utf-8")


def main() -> None:
    args = parse_args()
    fixtures = load_fixture_payload(args.fixture_path)
    selected_case_names = set(args.case_names or DEFAULT_CASE_NAMES)
    classification_overrides = parse_classification_overrides(args.classifications)

    all_cases = iter_fixture_cases(fixtures)
    known_case_names = {case.name for case in all_cases}
    unknown_selected = sorted(selected_case_names - known_case_names)
    if unknown_selected:
        raise SystemExit(f"Unknown golden case(s): {', '.join(unknown_selected)}")
    unknown_classifications = sorted(set(classification_overrides) - known_case_names)
    if unknown_classifications:
        raise SystemExit(f"Unknown classified case(s): {', '.join(unknown_classifications)}")

    selected_reviews, unselected_drifts = review_fixture_cases(all_cases, selected_case_names, classification_overrides)
    report = build_report(args.fixture_path, selected_reviews, selected_case_names, unselected_drifts)
    write_report_files(report, args.json_path, args.markdown_path)
    print(f"Wrote {args.json_path}")
    print(f"Wrote {args.markdown_path}")

    if args.write_fixture:
        errors = validate_fixture_write(report)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            raise SystemExit(1)
        updated_fixtures = apply_review_updates(fixtures, selected_reviews)
        args.fixture_path.write_text(json.dumps(updated_fixtures, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {args.fixture_path}")


if __name__ == "__main__":
    main()
