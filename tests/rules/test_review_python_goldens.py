from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.engine.models.state import HasteEffect

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "review_python_goldens.py"
MODULE_SPEC = importlib.util.spec_from_file_location("review_python_goldens", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
review_python_goldens = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = review_python_goldens
MODULE_SPEC.loader.exec_module(review_python_goldens)


def test_find_first_divergent_event_returns_expected_texts() -> None:
    diff = review_python_goldens.find_first_divergent_event(
        [
            {"eventType": "move", "actorId": "F1", "textSummary": "Expected move."},
            {"eventType": "attack", "actorId": "F1", "textSummary": "Expected attack."},
        ],
        [
            {"eventType": "move", "actorId": "F1", "textSummary": "Expected move."},
            {"eventType": "dash", "actorId": "F1", "textSummary": "Actual dash."},
        ],
    )

    assert diff == {
        "index": 1,
        "expectedEventType": "attack",
        "actualEventType": "dash",
        "expectedActorId": "F1",
        "actualActorId": "F1",
        "expectedText": "Expected attack.",
        "actualText": "Actual dash.",
    }


def test_validate_fixture_write_requires_classification_and_clean_scope() -> None:
    report = {
        "missingSelectedCases": [],
        "unselectedDrifts": [],
        "reviews": [
            {"name": "goblin-screen-default", "kind": "run", "driftDetected": True, "classification": "pending", "deterministic": True},
            {"name": "wolf-harriers-balanced-batch", "kind": "batch", "driftDetected": True, "classification": "intended", "deterministic": True},
        ],
    }

    errors = review_python_goldens.validate_fixture_write(report)

    assert errors == ["Classify drifting cases before writing fixtures: goblin-screen-default."]


@pytest.mark.parametrize("kind", ("run", "batch"))
def test_validate_fixture_write_rejects_nondeterministic_drift(kind: str) -> None:
    report = {
        "reviews": [{"name": "unstable", "kind": kind, "driftDetected": True,
                     "classification": "intended", "deterministic": False}],
    }
    assert review_python_goldens.validate_fixture_write(report) == [
        "Golden drift was not deterministic on repeat run: unstable."
    ]


def test_run_review_detects_nondeterministic_results(monkeypatch) -> None:
    def result(round_number):
        payload = {"finalState": {"round": round_number}, "events": [], "replayFrames": []}
        return SimpleNamespace(final_state=None, model_dump=lambda **kwargs: payload)

    results = iter((result(1), result(2)))
    monkeypatch.setattr(review_python_goldens, "run_encounter", lambda config: next(results))
    monkeypatch.setattr(
        review_python_goldens, "summarize_encounter",
        lambda state: SimpleNamespace(model_dump=lambda **kwargs: {"rounds": 1}),
    )
    case = review_python_goldens.FixtureCase(
        "run", "unstable", 0,
        {"config": {"seed": "unstable"}, "result": {}, "summary": {}},
    )
    review = review_python_goldens.review_run_case(case, "intended")
    assert review["deterministic"] is False


def test_run_review_compares_json_compatible_haste_actions(monkeypatch) -> None:
    effect = HasteEffect(kind="haste", source_id="F4", ac_bonus=2, speed_multiplier=2)
    result = SimpleNamespace(
        final_state=None,
        model_dump=lambda **kwargs: {"haste": effect.model_dump(**kwargs)},
    )
    monkeypatch.setattr(review_python_goldens, "run_encounter", lambda config: result)
    monkeypatch.setattr(
        review_python_goldens, "summarize_encounter",
        lambda state: SimpleNamespace(model_dump=lambda **kwargs: {"rounds": 1}),
    )
    case = review_python_goldens.FixtureCase(
        "run", "haste-json", 0,
        {"config": {"seed": "haste-json"},
         "result": {"haste": effect.model_dump(mode="json", by_alias=True)},
         "summary": {"rounds": 1}},
    )
    review = review_python_goldens.review_run_case(case, "intended")
    assert review["driftDetected"] is False
    assert review["deterministic"] is True


def test_apply_review_updates_changes_only_selected_entries() -> None:
    fixtures = {
        "runCases": [
            {
                "name": "run-a",
                "config": {"seed": "a"},
                "result": {"winner": "old"},
                "summary": {"winner": "old"},
            },
            {
                "name": "run-b",
                "config": {"seed": "b"},
                "result": {"winner": "keep"},
                "summary": {"winner": "keep"},
            },
        ],
        "batchCases": [
            {
                "name": "batch-a",
                "config": {"seed": "c"},
                "summary": {"playerWinRate": 0.4},
            }
        ],
    }
    reviews = [
        {
            "name": "run-a",
            "kind": "run",
            "driftDetected": True,
            "actualResult": {"winner": "new"},
            "actualSummary": {"winner": "new"},
        },
        {
            "name": "batch-a",
            "kind": "batch",
            "driftDetected": True,
            "actualSummary": {"playerWinRate": 1.0},
        },
    ]

    updated = review_python_goldens.apply_review_updates(fixtures, reviews)

    assert updated["runCases"][0]["result"] == {"winner": "new"}
    assert updated["runCases"][0]["summary"] == {"winner": "new"}
    assert updated["runCases"][1]["result"] == {"winner": "keep"}
    assert updated["batchCases"][0]["summary"] == {"playerWinRate": 1.0}
