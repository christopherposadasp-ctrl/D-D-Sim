from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock, Thread
from uuid import uuid4

from backend.engine import run_batch
from backend.engine.constants import DEFAULT_BATCH_MONSTER_BEHAVIOR, DEFAULT_BATCH_SIZE, MONSTER_BEHAVIORS
from backend.engine.models.state import BatchJobStatus, BatchSummary, EncounterConfig, MonsterBehavior


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_total_runs(config: EncounterConfig) -> int:
    batch_size = config.batch_size or DEFAULT_BATCH_SIZE
    monster_behavior = config.monster_behavior or DEFAULT_BATCH_MONSTER_BEHAVIOR
    return batch_size * len(MONSTER_BEHAVIORS) if monster_behavior == "combined" else batch_size


def get_initial_monster_behavior(config: EncounterConfig) -> MonsterBehavior:
    monster_behavior = config.monster_behavior or DEFAULT_BATCH_MONSTER_BEHAVIOR
    return MONSTER_BEHAVIORS[0] if monster_behavior == "combined" else monster_behavior


@dataclass
class BatchJobRecord:
    job_id: str
    config: EncounterConfig
    total_runs: int
    status: str = "queued"
    completed_runs: int = 0
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    current_monster_behavior: MonsterBehavior | None = None
    batch_summary: BatchSummary | None = None
    error: str | None = None
    lock: Lock = field(default_factory=Lock)

    def to_model(self) -> BatchJobStatus:
        with self.lock:
            finished_at = self.finished_at
            elapsed_seconds = ((finished_at or utc_now()) - self.started_at).total_seconds()
            return BatchJobStatus(
                job_id=self.job_id,
                status=self.status,
                completed_runs=self.completed_runs,
                total_runs=self.total_runs,
                progress_ratio=(self.completed_runs / self.total_runs) if self.total_runs > 0 else 0,
                started_at=self.started_at,
                finished_at=finished_at,
                elapsed_seconds=elapsed_seconds,
                current_monster_behavior=self.current_monster_behavior,
                batch_summary=self.batch_summary,
                error=self.error,
            )


_BATCH_JOBS: dict[str, BatchJobRecord] = {}
_BATCH_JOBS_LOCK = Lock()


def _store_batch_job(record: BatchJobRecord) -> None:
    with _BATCH_JOBS_LOCK:
        _BATCH_JOBS[record.job_id] = record


def _get_batch_job_record(job_id: str) -> BatchJobRecord:
    with _BATCH_JOBS_LOCK:
        record = _BATCH_JOBS.get(job_id)

    if not record:
        raise KeyError(job_id)

    return record


def get_batch_job_status(job_id: str) -> BatchJobStatus:
    return _get_batch_job_record(job_id).to_model()


def _update_batch_job_progress(
    job_id: str,
    completed_runs: int,
    total_runs: int,
    current_monster_behavior: MonsterBehavior,
) -> None:
    record = _get_batch_job_record(job_id)

    with record.lock:
        record.status = "running"
        record.completed_runs = completed_runs
        record.total_runs = total_runs
        record.current_monster_behavior = current_monster_behavior


def _run_batch_job(job_id: str) -> None:
    record = _get_batch_job_record(job_id)

    try:
        with record.lock:
            record.status = "running"

        summary = run_batch(
            record.config,
            progress_callback=lambda completed_runs, total_runs, current_monster_behavior: _update_batch_job_progress(
                job_id,
                completed_runs,
                total_runs,
                current_monster_behavior,
            ),
        )

        with record.lock:
            record.status = "completed"
            record.completed_runs = record.total_runs
            record.finished_at = utc_now()
            record.current_monster_behavior = None
            record.batch_summary = summary
    except Exception as error:  # pragma: no cover - failure path is exercised via API-level checks
        with record.lock:
            record.status = "failed"
            record.finished_at = utc_now()
            record.error = str(error)


def create_batch_job(config: EncounterConfig) -> BatchJobStatus:
    record = BatchJobRecord(
        job_id=uuid4().hex,
        config=config.model_copy(deep=True),
        total_runs=get_total_runs(config),
        current_monster_behavior=get_initial_monster_behavior(config),
    )
    _store_batch_job(record)

    worker = Thread(target=_run_batch_job, args=(record.job_id,), daemon=True)
    worker.start()
    return record.to_model()
