# V4 Architecture

## Purpose

This document captures the recommended architecture for the Python-based V4 rewrite.

It is intended to answer:

- what stays from the proof of concept
- what moves to Python
- how the UI should talk to the engine
- how content should be modeled
- how the repository should be organized as V4 work begins

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
    classes/
    monsters/
    presets/
    spells/
    traits/
  engine/
    actions/
    ai/
    combat/
    effects/
    models/
    rules/
    services/
    utils/
frontend/
tests/
  golden/
  integration/
  rules/
docs/
  MASTER_NOTES.md
  V4_ARCHITECTURE.md
  CONTENT_BACKLOG.md
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

### `backend/engine/actions`

Owns legal combat actions and action resolution entry points.

Examples:

- move
- attack
- dash
- stabilize
- cast spell
- ready/use reaction

### `backend/engine/effects`

Owns effect primitives and duration management.

Examples:

- condition application
- concentration
- buffs/debuffs
- forced movement
- AoE resolution
- ongoing effects

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

- classes
- class features
- monsters
- enemy variants
- actions
- traits
- spells
- presets

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

### Catalog Endpoints

- `GET /api/catalog/classes`
- `GET /api/catalog/monsters`
- `GET /api/catalog/spells`
- `GET /api/catalog/presets`

### Comparison/Planning Endpoints

- `POST /api/analysis/compare`
- `POST /api/analysis/preset-batch`

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

Add martial class progression and martial-only player features.

### `V4.3`

Add a generalized non-spell monster trait/action system.

### `V4.4`

Add spell primitives and core combat spell support.

### `V4.5`

Add healer/caster AI and reaction-timing intelligence.

### `V4.6`

Load broader trimmed SRD content.

### `V4.7`

Optimize, package, and harden the product.

## Migration Strategy

Recommended sequence:

1. keep the current TypeScript version intact as the proof of concept
2. create a fresh Python backend alongside it
3. reproduce current deterministic outputs first
4. shift future content growth into the Python engine
5. keep the current UI as a behavior reference while the frontend evolves

## Open Decisions

- final frontend technology confirmation
- exact Python dependency set
- whether local desktop packaging is required before or after V4.6
- exact SRD trim list for monsters
- exact SRD trim list for combat spells
