from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.openapi.utils import get_openapi

from backend.api.batch_jobs import create_batch_job, get_batch_job_status
from backend.engine import run_batch, run_encounter
from backend.engine.models.catalog import EnemyCatalogResponse, PlayerCatalogResponse
from backend.engine.models.state import BatchJobStatus, BatchSummary, EncounterConfig, RunEncounterResult
from backend.engine.services.catalog import get_enemy_catalog, get_player_catalog

app = FastAPI(title="D&D Simulator Backend", version="0.1.0", openapi_version="3.0.3")


def _convert_nullable_branches(node):
    """Rewrite Pydantic-style `anyOf[..., {type: null}]` into OpenAPI 3.0 nullable schemas.

    Swagger UI is more reliable with `nullable: true` than with explicit `type: null`
    branches inside large response models.
    """

    if isinstance(node, list):
        for item in node:
            _convert_nullable_branches(item)
        return

    if not isinstance(node, dict):
        return

    for value in node.values():
        _convert_nullable_branches(value)

    any_of = node.get("anyOf")
    if not isinstance(any_of, list):
        return

    null_branches = [entry for entry in any_of if isinstance(entry, dict) and entry.get("type") == "null"]
    if not null_branches:
        return

    non_null_branches = [entry for entry in any_of if not (isinstance(entry, dict) and entry.get("type") == "null")]
    node.pop("anyOf", None)
    node["nullable"] = True

    if len(non_null_branches) == 1:
        branch = non_null_branches[0]

        # `$ref` cannot safely be merged inline with sibling keys for all tooling,
        # so wrap it in `allOf` and attach `nullable` to the containing schema.
        if isinstance(branch, dict) and set(branch.keys()) == {"$ref"}:
            node["allOf"] = [branch]
        else:
            node.update(branch)
        return

    node["anyOf"] = non_null_branches


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    schema["openapi"] = "3.0.3"
    _convert_nullable_branches(schema)
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/catalog/enemies", response_model=EnemyCatalogResponse)
def get_enemy_catalog_endpoint() -> EnemyCatalogResponse:
    return get_enemy_catalog()


@app.get("/api/catalog/classes", response_model=PlayerCatalogResponse)
def get_player_catalog_endpoint() -> PlayerCatalogResponse:
    return get_player_catalog()


@app.post("/api/encounters/run", response_model=RunEncounterResult)
def run_encounter_endpoint(config: EncounterConfig) -> RunEncounterResult:
    try:
        return run_encounter(config)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/encounters/batch", response_model=BatchSummary)
def run_batch_endpoint(config: EncounterConfig) -> BatchSummary:
    try:
        return run_batch(config)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/encounters/batch-jobs", response_model=BatchJobStatus)
def create_batch_job_endpoint(config: EncounterConfig) -> BatchJobStatus:
    try:
        return create_batch_job(config)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/encounters/batch-jobs/{job_id}", response_model=BatchJobStatus)
def get_batch_job_status_endpoint(job_id: str) -> BatchJobStatus:
    try:
        return get_batch_job_status(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Batch job not found.") from error
