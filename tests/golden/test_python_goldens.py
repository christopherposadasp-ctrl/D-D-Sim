from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.engine import run_batch, run_encounter, summarize_encounter
from backend.engine.models.state import EncounterConfig

FIXTURE_PATH = Path(__file__).with_name("python_golden_fixtures.json")


def load_fixtures() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.mark.parametrize("case", load_fixtures()["runCases"], ids=lambda case: case["name"])
def test_python_run_cases_match_python_goldens(case) -> None:
    config = EncounterConfig.model_validate(case["config"])
    result = run_encounter(config)

    assert result.model_dump(mode="json", by_alias=True) == case["result"]
    assert summarize_encounter(result.final_state).model_dump(mode="json", by_alias=True) == case["summary"]


@pytest.mark.parametrize("case", load_fixtures()["batchCases"], ids=lambda case: case["name"])
def test_python_batch_cases_match_python_goldens(case) -> None:
    config = EncounterConfig.model_validate(case["config"])
    summary = run_batch(config)

    assert summary.model_dump(mode="json", by_alias=True) == case["summary"]
