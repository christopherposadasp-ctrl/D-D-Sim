from __future__ import annotations

from backend.engine.models.state import DiceSpec

FNV_OFFSET = 2_166_136_261
FNV_PRIME = 16_777_619
UINT32_MASK = 0xFFFFFFFF


def _imul(left: int, right: int) -> int:
    """Match JavaScript's 32-bit integer multiply semantics."""
    return (left * right) & UINT32_MASK


def normalize_seed(seed: str) -> int:
    hash_value = FNV_OFFSET

    for character in seed:
        hash_value ^= ord(character)
        hash_value = _imul(hash_value, FNV_PRIME)

    return hash_value or 1


def next_rng_state(state: int) -> int:
    return (_imul(state, 1_664_525) + 1_013_904_223) & UINT32_MASK


def roll_die(state: int, sides: int) -> tuple[int, int]:
    next_state = next_rng_state(state)
    value = (next_state % sides) + 1
    return value, next_state


def roll_dice(state: int, specs: list[DiceSpec]) -> tuple[list[int], int, int]:
    values: list[int] = []
    total = 0
    working_state = state

    for spec in specs:
        for _ in range(spec.count):
            value, working_state = roll_die(working_state, spec.sides)
            values.append(value)
            total += value

    return values, total, working_state
