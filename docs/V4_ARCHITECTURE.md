# V4 Architecture

## Purpose

This document captures the live backend-first architecture for the Python-based V4 simulator.

It is intended to answer:

- which layer owns simulation authority
- how the current repository is organized
- where combat logic and content live today
- how the UI should talk to the engine
- how content should be modeled
- how future class and content work should fit into the current structure

## V4 Design Goals

- move all simulation logic to Python
- preserve deterministic seeded simulation
- preserve replay-first execution
- support gradual rules/content expansion without rewriting the engine
- keep the UI intuitive while making the backend easier to extend
- support local/offline use

## Recommended Stack

### Backend

- Python 3.12+
- FastAPI for local API/service orchestration
- Pydantic for validation and typed payloads
- pytest for testing

### Frontend

- React + TypeScript
- Vite for local development

### Packaging Later

- Python packaged with PyInstaller
- optional desktop shell later if desired

## Architectural Recommendation

Use a strict separation between:

- rules engine
- content data
- AI policy
- API transport
- UI rendering

The Python engine should never depend on the frontend. The frontend should never own combat rules.

## Core Principles

- engine state transitions should be deterministic
- replay data should be generated from the same state/event pipeline used by the simulator
- content should be data-first where possible
- AI policy should be separate from legal action generation
- special-case behavior should be isolated behind handlers rather than spread across the whole engine

## Target Repository Layout

```text
backend/
  api/
  content/
    attack_sequences.py
    class_definitions.py
    class_progressions.py
    combat_actions.py
    enemies.py
    feature_definitions.py
    monster_traits.py
    player_loadouts.py
    scenario_definitions.py
    special_actions.py
    spell_definitions.py
  engine/
    ai/
    combat/
    models/
    rules/
    services/
    utils/
src/
  shared/
  ui/
tests/
  golden/
  rules/
  api/
scripts/
docs/
  MASTER_NOTES.md
  V4_ARCHITECTURE.md
  CONTENT_BACKLOG.md
  PLAYER_CLASS_IMPLEMENTATION.md
  reference/
```

## Backend Module Boundaries

### `backend/engine/models`

Owns typed domain objects.

Examples:

- encounter state
- unit state
- action request
- action result
- effect instance
- replay frame
- batch summary

### `backend/engine/utils`

Owns generic helpers.

Examples:

- seeded RNG
- math/grid helpers
- serialization helpers
- identifier generation

### `backend/engine/combat`

Owns encounter lifecycle and turn sequencing.

Examples:

- create encounter
- step encounter
- run encounter
- run batch
- phase transitions
- initiative handling

### `backend/engine/rules`

Owns reusable rules logic.

Examples:

- attack context
- flanking
- cover
- opportunity attacks
- saving throws
- death saves
- concentration checks

Current implementation note:

- combat-action metadata currently lives in `backend/content/combat_actions.py`
- action resolution and temporary-effect handling currently live mainly in:
  - `backend/engine/combat/engine.py`
  - `backend/engine/rules/combat_rules.py`
- splitting those further is optional future cleanup, not a requirement for new class work

### `backend/engine/ai`

Owns behavior policies, not rule legality.

Examples:

- player behavior selection
- DM behavior selection
- target evaluation
- spell heuristics
- movement heuristics

### `backend/engine/services`

Owns orchestration that composes multiple engine modules.

Examples:

- encounter replay generation
- batch runner
- scenario runner
- comparison runner

## Content Layer

The content layer should be mostly data-driven.

Recommended content buckets:

- class definitions
- class progressions
- feature definitions
- player loadouts
- monsters / enemy variants
- actions
- traits
- spells
- scenarios / presets

### Data-First Rule

If two pieces of content differ only by numbers, tags, action lists, or a small rules profile, keep them in data.

Use Python handlers only when content cannot be cleanly represented through shared primitives.

## Enemy Variant Convention

When a base creature can plausibly be used as both ranged and melee, create explicit variants.

Examples:

- `goblin_raider`
- `goblin_archer`
- `bandit_melee`
- `bandit_archer`

Recommended variant fields:

- `base_creature_id`
- `variant_id`
- `display_name`
- `combat_role`
- `equipped_actions`
- `behavior_profile`
- `role_tags`

## Combat Pipeline

Recommended run flow:

1. load content definitions
2. construct encounter config
3. instantiate encounter state
4. resolve legal actions for active unit
5. AI selects one action plan from legal options
6. resolve action into structured events
7. mutate state through explicit state transition
8. append replay frame/event data
9. continue until terminal state

## Replay Model

Replay should remain precomputed.

Recommended output model:

- `final_state`
- `events`
- `replay_frames`
- `summary`

The UI should consume stored replay data and never re-simulate while scrubbing.

## API Recommendation

### Simulation Endpoints

- `POST /api/encounters/run`
- `POST /api/encounters/batch`
- `POST /api/encounters/validate`

### Current Active Endpoints

- `GET /health`
- `GET /api/catalog/enemies`
- `GET /api/catalog/classes`
- `POST /api/encounters/run`
- `POST /api/encounters/batch`
- `POST /api/encounters/batch-jobs`
- `GET /api/encounters/batch-jobs/{job_id}`

API stability rule:

- the Python backend owns the live run, batch, replay, and catalog contracts
- frontend and `src/shared/` changes should follow backend needs, not lead them
- prefer keeping run and batch payload shapes stable unless a new backend capability truly needs a transport change

## Testing Strategy

### Golden Tests

Use golden tests to prove parity with V3 during `V4.0`.

Examples:

- fixed seed encounter log
- fixed seed replay frames
- fixed seed batch summaries

### Rules Tests

Use narrow tests for:

- flanking
- movement legality
- opportunity attacks
- target selection
- death saves
- concentration
- spell area resolution

### Integration Tests

Use end-to-end tests for:

- preset encounters
- mixed enemy compositions
- martial class feature usage
- spellcasting turns
- batch comparison output

## Milestone Mapping

### `V4.0`

Build Python parity for current behavior and summaries.

### `V4.1`

Add starter enemy content and preset-mix support without changing engine fundamentals.

### `V4.2`

Add martial classes up to level 2 through a player-content framework:

- `V4.2-A` player schema, progressions, features, loadouts, presets, and hook foundation
- `V4.2-B` Fighter and Rogue
- `V4.2-C` Barbarian and Monk

Current implementation snapshot:

- Fighter is live through level 5 as a Battle Master great-weapon striker with Great Weapon Master, Extra Attack, and Tactical Shift
- Ranged Rogue is live through level 5 as an Assassin; melee Rogue, Barbarian, and Monk are live through level 2
- Wizard is live at level 1 as a narrow combat-only spellcasting slice
- Paladin is live at level 1 as a plate-and-shield support tank with Lay on Hands, Bless, Cure Wounds, and concentration support

## Backend Authority Status

- the Python backend is the live simulation authority
- React consumes backend-owned catalogs and replay/state transport data
- the old TypeScript engine/runtime is no longer part of the live simulation path
- new combat rules should not be added back into `src/`

## Current Framework Direction

The live repo should converge on four reusable content layers:

- classes and progression
- actions, features, and traits
- monsters and scenarios
- spells and effects

The important implementation rule is that new content should prefer registry entries and shared handlers over new creature-specific or class-specific branches.

## Open Decisions

- whether to split action/effect resolution into additional backend modules later
- how much observer-specific stealth/search simulation should exist beyond the current combat-only Hide model
- when to expose more player catalog controls in the frontend
- whether local desktop packaging is required before or after V4.6
- exact SRD trim list for monsters
- exact SRD trim list for combat spells
