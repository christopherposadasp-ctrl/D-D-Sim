"""Public Python engine surface.

This module intentionally uses lazy wrappers instead of eager imports. Content
modules import engine submodules for shared models, and the old eager package
init path made those imports vulnerable to circular-import failures.
"""

from __future__ import annotations

from typing import Any


def create_encounter(*args: Any, **kwargs: Any):
    from backend.engine.combat.engine import create_encounter as create_encounter_impl

    return create_encounter_impl(*args, **kwargs)


def step_encounter(*args: Any, **kwargs: Any):
    from backend.engine.combat.engine import step_encounter as step_encounter_impl

    return step_encounter_impl(*args, **kwargs)


def run_encounter(*args: Any, **kwargs: Any):
    from backend.engine.combat.engine import run_encounter as run_encounter_impl

    return run_encounter_impl(*args, **kwargs)


def summarize_encounter(*args: Any, **kwargs: Any):
    from backend.engine.combat.engine import summarize_encounter as summarize_encounter_impl

    return summarize_encounter_impl(*args, **kwargs)


def run_batch(*args: Any, **kwargs: Any):
    from backend.engine.combat.engine import run_batch as run_batch_impl

    return run_batch_impl(*args, **kwargs)


__all__ = ["create_encounter", "run_batch", "run_encounter", "step_encounter", "summarize_encounter"]
