from __future__ import annotations


def assert_attack_action_core(action: dict[str, object] | None, *, target_id: str, weapon_id: str) -> None:
    assert action is not None
    assert action["kind"] == "attack"
    assert action["target_id"] == target_id
    assert action["weapon_id"] == weapon_id
