from __future__ import annotations

from backend.engine.rules.combat_rules import (
    AttackRollOverrides as legacy_attack_roll_overrides,
)
from backend.engine.rules.combat_rules import (
    resolve_cast_spell as legacy_resolve_cast_spell,
)
from backend.engine.rules.combat_support import AttackRollOverrides as support_attack_roll_overrides
from backend.engine.rules.spell_resolvers import resolve_cast_spell as direct_resolve_cast_spell


def test_spell_resolver_import_boundary_preserves_legacy_combat_rules_imports() -> None:
    assert legacy_resolve_cast_spell is direct_resolve_cast_spell
    assert legacy_resolve_cast_spell.__module__ == "backend.engine.rules.spell_resolvers"
    assert legacy_attack_roll_overrides is support_attack_roll_overrides
