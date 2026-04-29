# Spell Development

## Purpose

This guide is the default workflow for adding combat spell support to the simulator.

Spell work should stay:

- data-first where metadata is enough
- deterministic under test overrides
- compatible with existing encounter action payloads
- focused on one spell slice at a time

## File Ownership

- Spell metadata lives in `backend/content/spell_definitions.py`.
- Spell runtime mechanics live in `backend/engine/rules/spell_resolvers.py`.
- Shared rules DTOs and small neutral helpers live in `backend/engine/rules/combat_support.py`.
- Generic combat primitives stay in `backend/engine/rules/combat_rules.py`.
- Turn sequencing and action dispatch stay in `backend/engine/combat/engine.py`.

Do not put new spell-specific mechanics in `combat_rules.py` unless they must become a generic combat primitive.
Reaction spells can require a small dispatch hook in `engine.py`, but their eligibility checks, resource spend,
and event payload construction should still live in `spell_resolvers.py`.

## Typical Spell Slice

1. Add or update the spell definition metadata.
2. Add the minimum resolver behavior in `spell_resolvers.py`.
3. Reuse existing attack, save, damage, concentration, range, and condition helpers.
4. Add focused deterministic tests for availability, resource spend, core effect, invalid casts, and event payloads.
5. Update the modeled spreadsheet only after focused tests pass.
6. Report rules interpretation, limitations, files changed, tests run, and the next queued spell.

## Resolver Guidance

- Keep public encounter action payloads stable.
- Spend spell slots only after legality checks that should prevent a cast.
- Emit clear `spellId` and spell-result fields in combat events.
- Prefer adding small support helpers to `combat_support.py` only when both combat and spell modules need them.
- Leave broader rules expansion documented as a limitation when the engine has no state model for it yet.
