from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
Status = Literal["pass", "warn", "fail", "skipped"]


def run_git(args: list[str], repo_root: Path = REPO_ROOT) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else completed.stderr


def collect_git_context(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    commit = run_git(["rev-parse", "--short", "HEAD"], repo_root)
    status = run_git(["status", "--short"], repo_root)
    return {
        "generatedAt": datetime.now(tz=UTC).isoformat(),
        "branch": branch.strip(),
        "commit": commit.strip(),
        "gitStatusShort": [line for line in status.splitlines() if line.strip()],
    }


def relative_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def split_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return [line for line in text.splitlines() if line.strip()]


def output_tail(stdout: str | None, stderr: str | None, limit: int = 12) -> list[str]:
    return [*split_lines(stdout), *split_lines(stderr)][-limit:]


def text_tail(text: str | None, limit: int = 24) -> list[str]:
    return split_lines(text)[-limit:]


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Expected report file was not created: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content.endswith("\n") else f"{content}\n", encoding="utf-8")


def build_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "fail": 0, "skipped": 0}
    for row in rows:
        status = row.get("status")
        if status in counts:
            counts[status] += 1
    return counts
