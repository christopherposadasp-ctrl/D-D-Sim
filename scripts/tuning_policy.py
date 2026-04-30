from __future__ import annotations

from typing import Any

DEFAULT_LAY_ON_HANDS_DOWNED_PERCENT = 30
DEFAULT_LAY_ON_HANDS_ALLY_PERCENT = 55
DEFAULT_LAY_ON_HANDS_SELF_PERCENT = 65
DEFAULT_LAY_ON_HANDS_REMAINDER_PERCENT = 20

LayOnHandsPolicy = dict[str, int | str]


def build_lay_on_hands_policy(
    *,
    downed_percent: int = DEFAULT_LAY_ON_HANDS_DOWNED_PERCENT,
    ally_percent: int = DEFAULT_LAY_ON_HANDS_ALLY_PERCENT,
    self_percent: int = DEFAULT_LAY_ON_HANDS_SELF_PERCENT,
    remainder_percent: int = DEFAULT_LAY_ON_HANDS_REMAINDER_PERCENT,
) -> LayOnHandsPolicy:
    policy: LayOnHandsPolicy = {
        "downedPercent": downed_percent,
        "allyPercent": ally_percent,
        "selfPercent": self_percent,
        "remainderPercent": remainder_percent,
        "signature": (
            f"downed{downed_percent}_ally{ally_percent}"
            f"_self{self_percent}_remainder{remainder_percent}"
        ),
    }
    validate_lay_on_hands_policy(policy)
    return policy


def validate_lay_on_hands_policy(policy: dict[str, Any]) -> None:
    for key in ("downedPercent", "allyPercent", "selfPercent", "remainderPercent"):
        value = int(policy[key])
        if value < 1 or value > 100:
            raise ValueError(f"Lay on Hands policy `{key}` must be between 1 and 100.")


def lay_on_hands_policy_config_kwargs(policy: dict[str, Any]) -> dict[str, int]:
    return {
        "lay_on_hands_downed_percent": int(policy["downedPercent"]),
        "lay_on_hands_ally_percent": int(policy["allyPercent"]),
        "lay_on_hands_self_percent": int(policy["selfPercent"]),
        "lay_on_hands_remainder_percent": int(policy["remainderPercent"]),
    }
