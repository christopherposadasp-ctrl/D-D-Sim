from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.engine import run_batch, run_encounter
from backend.engine.constants import DEFAULT_POSITIONS
from backend.engine.models.state import EncounterConfig
from backend.engine.services.catalog import get_enemy_catalog, get_player_catalog

ACTIVE_SCENARIO_IDS = [
    "goblin_screen",
    "bandit_ambush",
    "mixed_patrol",
    "orc_push",
    "wolf_harriers",
    "marsh_predators",
    "hobgoblin_kill_box",
    "predator_rampage",
    "bugbear_dragnet",
    "deadwatch_phalanx",
    "captains_crossfire",
]

ACTIVE_PLAYER_PRESET_IDS = [
    "fighter_sample_trio",
    "fighter_level2_sample_trio",
    "rogue_ranged_trio",
    "rogue_melee_trio",
    "rogue_level2_ranged_trio",
    "rogue_level2_melee_trio",
    "barbarian_sample_trio",
    "barbarian_level2_sample_trio",
    "monk_sample_trio",
    "monk_level2_sample_trio",
    "wizard_sample_trio",
    "martial_mixed_party",
]

CURRENT_MARSH_PREDATORS_UNITS = [
    {"unitId": "E1", "variantId": "giant_toad", "position": {"x": 9, "y": 7}},
    {"unitId": "E2", "variantId": "crocodile", "position": {"x": 1, "y": 1}},
    {"unitId": "E3", "variantId": "crocodile", "position": {"x": 4, "y": 1}},
    {"unitId": "E4", "variantId": "crocodile", "position": {"x": 2, "y": 4}},
    {"unitId": "E5", "variantId": "giant_toad", "position": {"x": 9, "y": 10}},
    {"unitId": "E6", "variantId": "crocodile", "position": {"x": 7, "y": 1}},
    {"unitId": "E7", "variantId": "crocodile", "position": {"x": 5, "y": 4}},
]

CURRENT_MARTIAL_MIXED_PARTY_UNITS = [
    {"unitId": "F1", "loadoutId": "fighter_level2_sample_build"},
    {"unitId": "F2", "loadoutId": "barbarian_level2_sample_build"},
    {"unitId": "F3", "loadoutId": "rogue_ranged_level2_sample_build"},
    {"unitId": "F4", "loadoutId": "rogue_melee_level2_sample_build"},
]


def build_trio_placements():
    return {key: value.model_dump() for key, value in DEFAULT_POSITIONS.items() if key != "F4"}


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_endpoint_matches_service_layer() -> None:
    client = TestClient(app)
    config = {"seed": "api-run", "placements": {key: value.model_dump() for key, value in DEFAULT_POSITIONS.items()}}

    response = client.post("/api/encounters/run", json=config)

    assert response.status_code == 200
    expected = run_encounter(EncounterConfig.model_validate(config)).model_dump(by_alias=True)
    assert response.json() == expected


def test_catalog_endpoint_matches_service_layer() -> None:
    client = TestClient(app)

    response = client.get("/api/catalog/enemies")

    assert response.status_code == 200
    expected = get_enemy_catalog().model_dump(by_alias=True)
    assert response.json() == expected


def test_enemy_catalog_exposes_fixed_rock_for_each_preset() -> None:
    client = TestClient(app)

    response = client.get("/api/catalog/enemies")

    assert response.status_code == 200
    payload = response.json()
    for preset in payload["enemyPresets"]:
        assert preset["terrainFeatures"] == [
            {
                "featureId": "rock_1",
                "kind": "rock",
                "position": {"x": 5, "y": 8},
                "footprint": {"width": 1, "height": 1},
            }
        ]


def test_enemy_catalog_exposes_frozen_active_scenario_surface() -> None:
    client = TestClient(app)

    response = client.get("/api/catalog/enemies")

    assert response.status_code == 200
    payload = response.json()
    assert [preset["id"] for preset in payload["enemyPresets"]] == ACTIVE_SCENARIO_IDS
    assert len(payload["enemyPresets"]) == 11

    presets_by_id = {preset["id"]: preset for preset in payload["enemyPresets"]}
    assert presets_by_id["marsh_predators"]["units"] == CURRENT_MARSH_PREDATORS_UNITS


def test_player_catalog_endpoint_matches_service_layer() -> None:
    client = TestClient(app)

    response = client.get("/api/catalog/classes")

    assert response.status_code == 200
    expected = get_player_catalog().model_dump(by_alias=True)
    assert response.json() == expected


def test_player_catalog_exposes_frozen_active_player_surface() -> None:
    client = TestClient(app)

    response = client.get("/api/catalog/classes")

    assert response.status_code == 200
    payload = response.json()

    classes_by_id = {player_class["id"]: player_class for player_class in payload["classes"]}
    assert "wizard" in classes_by_id
    assert classes_by_id["wizard"]["maxSupportedLevel"] == 1
    assert [preset["id"] for preset in payload["playerPresets"]] == ACTIVE_PLAYER_PRESET_IDS
    assert len(payload["playerPresets"]) == 12

    presets_by_id = {preset["id"]: preset for preset in payload["playerPresets"]}
    assert presets_by_id["martial_mixed_party"]["units"] == CURRENT_MARTIAL_MIXED_PARTY_UNITS


def test_batch_endpoint_matches_service_layer() -> None:
    client = TestClient(app)
    config = {
        "seed": "api-batch",
        "batchSize": 2,
        "placements": {key: value.model_dump() for key, value in DEFAULT_POSITIONS.items()},
        "playerBehavior": "balanced",
        "monsterBehavior": "combined",
    }

    response = client.post("/api/encounters/batch", json=config)

    assert response.status_code == 200
    expected = run_batch(EncounterConfig.model_validate(config)).model_dump(by_alias=True)
    assert response.json() == expected


def test_run_endpoint_supports_preset_defaults_without_manual_placements() -> None:
    client = TestClient(app)
    config = {
        "seed": "api-preset-run",
        "enemyPresetId": "goblin_screen",
        "playerBehavior": "balanced",
        "monsterBehavior": "balanced",
    }

    response = client.post("/api/encounters/run", json=config)

    assert response.status_code == 200
    payload = response.json()
    assert sorted(payload["finalState"]["units"]) == ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "F1", "F2", "F3", "F4"]
    assert payload["replayFrames"][0]["state"]["units"]["E1"]["position"] == {"x": 14, "y": 6}
    assert payload["replayFrames"][0]["state"]["units"]["F1"]["position"] == {"x": 1, "y": 7}
    assert payload["replayFrames"][0]["state"]["units"]["F4"]["position"] == {"x": 1, "y": 10}


def test_run_endpoint_accepts_player_preset_selection() -> None:
    client = TestClient(app)
    config = {
        "seed": "api-player-preset-run",
        "placements": build_trio_placements(),
        "playerPresetId": "rogue_melee_trio",
    }

    response = client.post("/api/encounters/run", json=config)

    assert response.status_code == 200
    payload = response.json()
    assert payload["finalState"]["units"]["F1"]["templateName"] == "Level 1 Melee Rogue Sample Build"
    assert sorted(payload["finalState"]["units"]["F1"]["attacks"]) == ["rapier", "shortbow"]


def test_invalid_placements_fail_validation() -> None:
    client = TestClient(app)
    config = {"seed": "bad-layout", "placements": {"F1": {"x": 1, "y": 1}}}

    response = client.post("/api/encounters/run", json=config)

    assert response.status_code == 400


def test_batch_job_endpoint_reports_progress_and_result() -> None:
    client = TestClient(app)
    config = {
        "seed": "api-batch-job",
        "batchSize": 2,
        "placements": {key: value.model_dump() for key, value in DEFAULT_POSITIONS.items()},
        "playerBehavior": "balanced",
        "monsterBehavior": "combined",
    }

    create_response = client.post("/api/encounters/batch-jobs", json=config)

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["status"] in {"queued", "running"}
    assert payload["totalRuns"] == 6

    job_id = payload["jobId"]
    final_payload = payload
    for _ in range(200):
        status_response = client.get(f"/api/encounters/batch-jobs/{job_id}")
        assert status_response.status_code == 200
        final_payload = status_response.json()
        if final_payload["status"] == "completed":
            break
        time.sleep(0.01)

    assert final_payload["status"] == "completed"
    assert final_payload["completedRuns"] == final_payload["totalRuns"] == 6
    expected = run_batch(EncounterConfig.model_validate(config)).model_dump(by_alias=True)
    assert final_payload["batchSummary"] == expected


def test_openapi_schema_uses_swagger_friendly_nullable_shape() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"] == "3.0.3"
    assert '"type": "null"' not in response.text
