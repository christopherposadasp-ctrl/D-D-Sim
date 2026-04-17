# Master Notes

## Purpose

This file is the running project record for versioning, scope decisions, implementation milestones, and content planning as the simulator evolves.

It should be updated whenever one of these changes:

- version scope
- architecture direction
- AI/rules interpretation
- content inclusion plan
- repository structure

## Related Docs

- [V4 Architecture](V4_ARCHITECTURE.md)
- [Content Backlog](CONTENT_BACKLOG.md)
- [Reference PDFs](reference/)

## Current Snapshot

### Live Proof of Concept

- Current implementation: TypeScript + React + Vite
- Current engine: pure TypeScript combat engine in `src/engine`
- Current UI: React UI in `src/ui`
- Current test suite: `src/test`
- Current mode: local browser app with deterministic replay and batch simulation

### Current V3 Capabilities

- seeded deterministic simulation
- replay-first execution
- batch summaries
- grid combat
- flanking rule: any angle greater than 90 degrees qualifies
- opportunity attacks
- player behavior modes: `smart`, `dumb`, `balanced`
- DM behavior modes: `kind`, `balanced`, `evil`, `combined` for batches
- combined DM batches default to three splits: kind, balanced, evil

## Versioning

### Current Working Version

- `V3`: TypeScript proof of concept

### Approved V4 Roadmap

#### `V4.0`

Python engine parity with the current simulator.

Deliverables:

- Python engine reproduces current seeded outcomes for fixed golden cases
- parity for replay structure and batch summaries
- parity for current player and DM behavior rules

#### `V4.1`

Create a list of 8 different but easy enemy types, with 5 preset mixes for variety in testing.

Current direction:

- use melee and archer variants when the base creature plausibly supports both roles
- presets should be composition-first and easy to reason about

Starter roster candidates:

- Goblin Raider
- Goblin Archer
- Bandit Melee
- Bandit Archer
- Guard
- Scout
- Orc Warrior
- Wolf

Starter preset candidates:

- Goblin Screen
- Bandit Ambush
- Mixed Patrol
- Orc Push
- Wolf Harriers

#### `V4.2`

Martial classes and non-spell player features.

Recommended early class focus:

- Fighter
- Rogue
- Barbarian
- Monk

#### `V4.3`

Non-spell monster framework and expanded non-spell monster roster.

Key goal:

- content-driven monster traits and actions instead of hardcoded special cases

#### `V4.4`

Core combat spell framework.

Required primitives before large spell expansion:

- concentration
- durations
- AoE targeting/templates
- saving throws
- buff/debuff effects
- ongoing effects
- forced movement
- reaction hooks
- upcasting/scaling

#### `V4.5`

Healer/caster AI and reaction magic.

Key goal:

- separate legal action generation from AI choice policy

#### `V4.6`

Broader SRD content completion.

Planned coordination:

- trimmed monster and spell lists will be prepared separately and then merged into this roadmap

#### `V4.7`

Performance, packaging, and polish.

## Architecture Direction

### Current Recommendation

Use:

- Python backend engine for simulation
- non-Python UI for interaction

Preferred final architecture:

- Python core engine
- Python content/data layer
- Python API/orchestration layer
- separate UI frontend

### Recommended UI Direction

Primary recommendation:

- React + TypeScript frontend on top of a Python backend

Alternative:

- PySide6/QML desktop UI on top of Python

Reason:

- all backend logic can live in Python
- UI can stay intuitive without forcing the simulation engine into frontend code

## Rules and AI Decisions To Carry Forward

### Flanking

- Flanking is always on
- A melee attack gains flanking when the attacker and an adjacent conscious ally form an angle greater than 90 degrees relative to the target

### Opportunity Attacks

- Opportunity attacks are active
- Baseline policy is to avoid willingly provoking
- Smart players only have exception hooks for future high-value targets
- Evil monsters may use exception hooks against downed or tagged high-value targets

### Player Behavior

- `smart`: seeks better targeting and flanking
- `dumb`: simple targeting and no flanking-seeking
- `balanced`: alternates smart and dumb by run in batch mode

### DM Behavior

- `kind`: targets the healthiest conscious PC by HP percentage and ignores downed PCs
- `balanced`: uses baseline targeting, ignores downed PCs, and prefers already-available flanking attacks without moving specifically to create flanking
- `evil`: finishes adjacent downed PCs first, then prioritizes `healer`, then `caster`, then lowest HP percentage, and seeks flanking
- `combined`: batch-only mode that runs kind, balanced, and evil splits

## Content Modeling Guidance

### Enemy Variant Rule

When a creature could plausibly be fielded as either ranged or melee, prefer explicit variants.

Examples:

- Goblin Raider
- Goblin Archer
- Bandit Melee
- Bandit Archer

Reason:

- cleaner AI
- clearer testing
- simpler balancing

### Data Modeling Direction For V4

Plan to represent content with:

- `base_creature_id`
- `variant_id`
- `combat_role`
- `equipped_actions`
- `behavior_profile`
- `role_tags`

## Repository Organization

### Current Layout

- `src/` current TypeScript implementation
- `docs/` project notes and references
- `docs/reference/` PDFs and source reference material

### Planned V4 Layout

- `backend/engine`
- `backend/content`
- `backend/api`
- `frontend`
- `tests/golden`
- `tests/rules`
- `tests/integration`

## Open Inputs Still Expected

- trimmed spell list
- trimmed monster list
- final exact SRD scope for the Python rewrite
- final decision on UI technology for V4

## Change Log

### 2026-04-17

- Added DM behavior system to the current proof of concept
- Set default batch mode to balanced players plus combined DM splits
- Established V4 milestone roadmap
- Decided to maintain master notes in this file
