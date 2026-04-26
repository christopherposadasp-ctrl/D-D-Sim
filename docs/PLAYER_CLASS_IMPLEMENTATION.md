# Player Class Implementation

## Purpose

This guide is the default checklist for adding or extending player classes in the live simulator.

It exists to keep class work:

- backend-first
- data-driven
- deterministic
- testable without snapshot guesswork

## Ground Rules

- The Python backend is the simulation authority.
- The React frontend consumes backend catalogs and replay/state transport types.
- Do not add live combat rules back into `src/`.
- Prefer reusable content metadata, action plumbing, and AI helpers over class-specific hardcoded branches.
- Keep run, batch, and replay payload shapes stable unless a new backend capability truly needs a transport change.

## Current Class Support Snapshot

- Fighter is live through level 5 as a Battle Master great-weapon striker with Extra Attack and Tactical Shift.
- Ranged Rogue is live through level 5 as an Assassin; melee Rogue is live through level 2.
- Barbarian and Monk are live through level 2.
- Wizard is live at level 1 as a narrow combat spellcasting slice.
- Paladin is live at level 5 as an Oath of the Ancients plate-and-shield support tank with Extra Attack, level 2 Bless, Aid rules support, Lay on Hands, Cure Wounds, Divine Smite, Channel Divinity, Nature's Wrath, and Sentinel.
- The default `martial_mixed_party` starts with the level 5 Battle Master Fighter, level 5 Oath of the Ancients Paladin, level 5 ranged Assassin Rogue, and level 1 Wizard.

## Primary Backend Files

Class work usually starts in these files:

- `backend/content/class_definitions.py`
- `backend/content/class_progressions.py`
- `backend/content/feature_definitions.py`
- `backend/content/player_loadouts.py`
- `backend/content/attack_sequences.py`
- `backend/content/combat_actions.py`
- `backend/engine/ai/decision.py`
- `backend/engine/combat/engine.py`
- `backend/engine/rules/combat_rules.py`
- `backend/engine/rules/combat_support.py`
- `backend/engine/rules/spell_resolvers.py`
- `backend/engine/rules/spatial.py`
- `backend/engine/models/state.py`
- `backend/engine/services/catalog.py`

Not every class needs all of them. Start with the minimum set and expand only where the class actually needs new runtime behavior.

## Typical Workflow

1. Inspect the closest live class implementation first.
2. Add or extend class metadata and progression content.
3. Add feature metadata before writing rule branches.
4. Add or reuse combat-action metadata if the class changes action economy.
5. Extend runtime state only if the feature cannot be modeled with existing state and temporary effects.
6. Wire AI behavior after legal action plumbing exists.
7. Add deterministic targeted tests before touching goldens.
8. Refresh goldens only after the narrow rule and AI tests are already green.

## Content Checklist

- Add or update the class definition entry.
- Add the class progression row for the new level.
- Add feature definitions and any granted action metadata.
- Add new loadouts or presets instead of silently mutating older sample builds when level separation matters.
- Confirm the player catalog exposes the new class level and loadouts correctly.

## Runtime Checklist

- Check whether the feature can be modeled through existing temporary effects, resources, or action metadata.
- Keep action sequencing inside the normal turn executor where possible.
- Reuse attack-mode, movement-budget, cover, and effect-expiration pipelines instead of bypassing them.
- Add centralized cleanup helpers when a new effect can break from multiple causes.
- Put spell-specific runtime behavior in `backend/engine/rules/spell_resolvers.py`; keep generic combat primitives in `combat_rules.py` or shared support helpers in `combat_support.py`.

## AI Checklist

- Decide whether the class meaningfully changes target selection, movement, bonus-action usage, or fallback behavior.
- If behavior differs by archetype or loadout, make that difference explicit through content tags or behavior profiles.
- Test smart and dumb behavior separately when the class adds decision complexity.
- Do not give player-only class behavior to monsters unless that is a deliberate content change.

## Frontend and Shared Types

Frontend or `src/shared/` changes are only needed when at least one of these is true:

- the backend exposes a genuinely new catalog shape
- replay/state payloads need to surface a new field for UI use
- frontend controls must send a new config choice to the backend

If the feature is fully internal to backend simulation, avoid frontend work.

## Default Test Surface

The normal class implementation test pass should review these modules:

- `tests/rules/test_player_framework.py`
- `tests/rules/test_rules.py`
- `tests/rules/test_ai.py`
- `tests/rules/test_spatial.py` when terrain, cover, movement, or hide/pathing changes
- `tests/golden/test_python_goldens.py` after targeted rules are green

Use deterministic seeds, fixed placements, and explicit roll overrides for rule and AI tests.

## Recommended Verification Order

1. Run the narrow player framework tests.
2. Run the targeted rules and AI modules touched by the feature.
3. Run any scenario smoke tests affected by the default mixed party or active presets.
4. Refresh and rerun Python goldens only after the targeted tests pass.
5. Run the broader `pytest` suite when the class work changes shared combat plumbing.

## Before Starting the Next Class

- Make sure the current backend-first baseline is committed or otherwise checkpointed cleanly.
- Update docs when the live class-support matrix changes.
- Keep `README.md`, `docs/MASTER_NOTES.md`, and this file aligned so the next class starts from an accurate repo snapshot.
