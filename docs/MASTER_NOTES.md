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
- [Player Class Implementation](PLAYER_CLASS_IMPLEMENTATION.md)
- [Reference PDFs](reference/)

## Current Snapshot

### Live App Snapshot

- Current implementation: React + Vite frontend with Python API backend
- Current frontend: React UI in `src/ui`
- Current backend: FastAPI app and Python engine in `backend/`
- Current shared frontend helpers: `src/shared/sim`
- Current frontend test suite: `src/test`
- Current Python test suite: `tests/`
- Current mode: local browser app with deterministic replay and batch simulation through the Python API

### Current V4.0 Backend Work

- Python parity backend implemented in `backend/`
- FastAPI API implemented for encounter run, batch, async batch-job execution, and backend-owned enemy catalog reads
- React UI now calls the Python API instead of executing simulations directly in the browser
- Python-native golden fixtures implemented in `tests/golden/python_golden_fixtures.json`
- Python golden, rules, and API tests implemented in `tests/`
- Parallel batch execution and progress reporting are implemented for practical local use
- Legacy TypeScript engine/runtime scaffolding has been removed from the live repo surface

### Current V4.1 Content Work

- V4.1 preset enemy roster is implemented in `backend/content/enemies.py`
- The frontend now exposes an enemy preset selector and dynamic placement validation
- Preset-driven encounters can run without a manually entered placement map because the default layout is loaded from the selected preset
- V4.1 preserves the V4.0 backend contract while expanding the active enemy roster beyond the original goblin-only setup
- The active UI and audit scenario set excludes `giant_toad_solo`; that preset remains as a focused backend rules fixture

### Current V4.1.5 Content Architecture Work

- Monster content now carries:
  - base creature ids
  - variant ids
  - AI profile ids
  - trait ids
  - action ids
  - bonus action ids
  - reaction ids
- Reusable combat-action metadata is implemented in `backend/content/combat_actions.py`
- Reusable monster traits are implemented in `backend/content/monster_traits.py`
- Shared monster AI profiles are implemented in `backend/engine/ai/profiles.py`
- The decision layer now resolves monster combat style from content metadata instead of hardcoded role-name lists
- Goblin `nimble_escape` and orc `aggressive` are now modeled through the reusable trait / action system

### Current V4.2 Foundation Work

- Player-side framework work has started on top of the live V4.1.5 engine
- New backend content registries now exist for:
  - class definitions
  - class progressions
  - feature definitions
  - player loadouts
  - spell definitions
  - scenario definitions
- The current player party is instantiated from a backend-owned player preset and loadout registry rather than a hardcoded fighter template
- Runtime player metadata is now tracked internally for:
  - `class_id`
  - `level`
  - `loadout_id`
  - `feature_ids`
  - `resource_pools`
  - `behavior_profile`
- The live martial class baseline is now:
  - Fighter supported to level 5 as a Battle Master great-weapon striker with Great Weapon Master, Extra Attack, and Tactical Shift
  - Barbarian supported to level 2
  - Rogue supported to level 5 for the ranged Assassin path and level 2 for the melee path
  - Monk supported to level 2
  - Paladin supported to level 5 as an Oath of the Ancients plate-and-shield support tank
- A narrow combat-only Wizard level 1 slice is also live with:
  - cantrips: `fire_bolt`, `shocking_grasp`
  - prepared combat spells: `magic_missile`, `shield`, `burning_hands`
  - level 1 prepared-spell and cantrip counts tracked as runtime metadata
- Rogue level 2 now includes combat-only Cunning Action support with:
  - bonus-action Dash
  - bonus-action Disengage
  - bonus-action Hide
  - terrain-based Hide support around the fixed rock feature
- The default player preset is now the four-PC mixed martial party:
  - one level 5 Battle Master fighter
  - one level 5 Oath of the Ancients paladin
  - one level 5 ranged Assassin rogue
  - one level 2 melee rogue
- These new player-build fields are intentionally kept out of the live run/batch API payload for now so the current UI contract remains stable during the framework transition
- A backend-owned player catalog endpoint now exists at `GET /api/catalog/classes`
- Scenario audit expectations now resolve through a scenario-definition registry instead of being fully hardcoded inside the audit service

### Current Audit Snapshot

- Pass 1 closed on `integration` at commit `01cecc3` with warnings and waivers.
- Pass 2 stability completed on top of the Pass 1 closure snapshot with deterministic replay, deterministic batch, async job, and long-audit evidence.
- Pass 3 clarity is the current audit-maintainability pass; it is behavior-preserving and does not change gameplay, scenario balance, API payloads, or catalog data.
- Phase A added the focused `party-validation` command as the default day-to-day party behavior gate.
- Batch health checks now use the normal multicore `run_batch` path by default, capped at 8 workers, with serial mode reserved for deterministic replay/debug checks.
- The focused party-validation scenario battery is `hobgoblin_kill_box`, `bugbear_dragnet`, and `deadwatch_phalanx`.
- Active monitored findings remain the scenario smart-under-dumb warning, Rogue notes, and mixed-party Fighter/Barbarian warnings documented in the audit reports.
- Active waivers remain for dedicated Monk, Wizard, and Monster audit runners until those focused runners are implemented.

### Current V4.1.x Large-Creature and Control Work

- The live roster now also includes:
  - Giant Toad
  - Crocodile
- Large-creature support is implemented with:
  - true `2x2` occupancy
  - anchor-square placement
  - large-creature movement and overlap validation
  - large-creature flanking, cover, reach, and opportunity-attack checks
- Stateful control flows now covered in the live engine include:
  - crocodile bite grapples
  - giant toad bite grapple/restrain
  - giant toad swallow
  - swallowed-target acid damage and release on death
- The current `marsh_predators` layout is:
  - `E1` giant toad at `(9, 7)`
  - `E5` giant toad at `(9, 10)`
  - `E2` crocodile at `(1, 1)`
  - `E3` crocodile at `(4, 1)`
  - `E4` crocodile at `(2, 4)`

### Current Simulator Capabilities

- seeded deterministic simulation
- replay-first execution
- batch summaries
- async batch jobs with progress polling
- grid combat
- flanking rule: any angle greater than 90 degrees qualifies
- opportunity attacks
- encounter ends immediately when all PCs are down or all enemies are dead
- player behavior modes: `smart`, `dumb`, `balanced`
- DM behavior modes: `kind`, `balanced`, `evil`, `combined` for batches
- combined DM batches default to three splits: kind, balanced, evil
- preset-driven enemy rosters with dynamic unit counts and default layouts
- current preset roster includes:
  - Goblin Raider
  - Goblin Archer
  - Bandit Melee
  - Bandit Archer
  - Guard
  - Scout
  - Orc Warrior
  - Wolf
  - Giant Toad
  - Crocodile
- current preset mixes include:
  - Goblin Screen
  - Bandit Ambush
  - Mixed Patrol
  - Orc Push
  - Wolf Harriers
  - Marsh Predators
- backend-only focused rules preset:
  - Giant Toad Solo
- notable current mechanics beyond the original goblin proof of concept:
  - large `2x2` creatures
  - terrain features with movement blocking and half cover
  - pack tactics
  - prone-on-hit rider
  - reusable multiattack action sequences
  - grapple-locked monster targeting
  - swallowed-target combat flow
  - combat-only terrain-based Hide for player rogues

## Versioning

### Current Working Version

- Current class path: Fighter is live to level 5 as a Battle Master; ranged Rogue is live to level 5 as an Assassin; Paladin is live to level 5 as an Oath of the Ancients support tank with Extra Attack, Sentinel, level 2 Bless, and Aid rules support; Barbarian, melee Rogue, and Monk remain live up to level 2
- Wizard level 1 is live as a narrow combat-only spellcasting slice, not a full `V4.4` spell framework rollout
- Immediate project path is now focused on one presentation-ready level 5 party rather than broad class coverage:
  - Fighter: Battle Master
  - ranged Rogue: Assassin
  - Wizard: Evoker
  - Paladin: Oath of the Ancients
  - optional stretch: Life Cleric

### Approved V4 Roadmap

#### `V4.0`

Python engine parity with the current simulator.

Deliverables:

- Python engine reproduces current seeded outcomes for fixed golden cases
- parity for replay structure and batch summaries
- parity for current player and DM behavior rules
- FastAPI transport for `run`, `batch`, and async `batch-jobs`
- React frontend cut over to the Python API with backend-owned catalog data

#### `V4.1`

Create a list of 8 different but easy enemy types, with 5 preset mixes for variety in testing.

Implemented roster:

- Goblin Raider
- Goblin Archer
- Bandit Melee
- Bandit Archer
- Guard
- Scout
- Orc Warrior
- Wolf

Implemented presets:

- Goblin Screen
- Bandit Ambush
- Mixed Patrol
- Orc Push
- Wolf Harriers

Implementation notes:

- presets use dynamic enemy unit ids such as `E1` through `E6`
- backend output field names remain compatible with the V4.0 API surface
- the UI presents these as enemy presets rather than as hardcoded goblin slots

#### `V4.1.5`

Refactor the current monster content model so the simulator can scale from the current preset roster to a large SRD-style roster without turning monster behavior into hardcoded per-creature branching.

Key goals:

- keep `UnitState` as the generic runtime combat model
- keep monster entries data-driven rather than class-per-monster
- replace hardcoded monster behavior switches with:
  - trait registries
  - action registries
  - AI profile registries
- model special monster features such as goblin bonus-action disengage and orc rush as reusable legal options, not bespoke monster subclasses
- preserve current simulation results for the existing V4.1 roster as closely as practical while changing the structure underneath

Planned outputs:

- `MonsterDefinition`-style content entries with:
  - base creature id
  - variant id
  - attacks
  - trait ids
  - action ids
  - bonus action ids
  - reaction ids
  - AI profile id
  - tags / role tags
- reusable monster trait handlers such as:
  - `nimble_escape`
  - `aggressive`
- reusable AI profiles such as:
  - melee brute
  - ranged skirmisher
  - guard / line holder
- current V4.1 roster migrated onto the new structure before further monster expansion

#### `V4.2`

Martial classes up to level 2.

Implementation phases:

- `V4.2-A`
  - player content schema
  - class progression tables
  - feature definitions
  - player loadouts and player presets
  - minimal resource/hook foundation for future spell and half-caster work
- `V4.2-B`
  - Fighter and Rogue
  - party preset support beyond the current fighter trio
- `V4.2-C`
  - Barbarian and Monk
  - rage, ki, and other martial action-economy hooks

Acceptance target:

- all four martial classes run deterministic seeded encounters and batch audits without relying on a fighter-specific fallback path

#### `V4.3`

Add 50 non-spellcasting monsters below CR 3 and 5 new scenarios.

Implementation phases:

- `V4.3-A`
  - monster intake schema
  - reusable trait library
  - audit checklist for new monster entries
- `V4.3-B`
  - first 25 monsters covering the main behavior shapes
- `V4.3-C`
  - second 25 monsters plus 5 new scenarios and updated scenario-health baselines

Acceptance target:

- new monsters should reuse shared action and trait primitives wherever possible, with new primitives justified only when they unlock multiple future entries

#### `V4.4`

Spellcaster classes up to level 2.

Implementation phases:

- `V4.4-A`
  - spell slot and preparation model
  - combat spell catalog
  - spell targeting, saves, concentration, and scoring hooks
- `V4.4-B`
  - Wizard, Sorcerer, and Cleric
- `V4.4-C`
  - Bard, Druid, and Warlock

Acceptance target:

- only cantrips and 1st-level combat spells are in scope; non-combat utility magic remains out of scope

#### `V4.5`

Half-caster classes up to level 2.

Implementation phases:

- `V4.5-A`
  - Ranger and Paladin class packages built on the V4.4 spell layer
- `V4.5-B`
  - class AI tuning
  - preset parties
  - mixed-party scenario validation

Acceptance target:

- no second spell engine is introduced; half-casters reuse the same spell/effect framework built for `V4.4`

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

### Current Validation Workflow

Use this as the routine backend gate before focused party work:

- `.\scripts\dev.ps1 check-fast`
- `.\scripts\dev.ps1 party-validation`

Notes:

- The monolithic `py -3.13 -m pytest` command can be noisy and unreliable in this shell capture environment even when the underlying tests are healthy.
- Full-catalog scenario audits are still useful for slower validation passes, but `party-validation` is the practical inner-loop gate for the current class path.
- Use deeper audit commands before major merges, broad rules changes, or release checkpoints.

### Pre-Barbarian Checkpoint

- Frozen local baseline report:
  - `reports/baselines/pre_barbarian_baseline_2026-04-20.json`
- Baseline generation command:
  - `py -3.13 .\scripts\freeze_baseline_report.py --batch-size 300 --seed-prefix pre-barbarian --output .\reports\baselines\pre_barbarian_baseline_2026-04-20.json`
- Baseline config:
  - player preset `martial_mixed_party`
  - player behavior `balanced`
  - monster behavior `combined`
  - batch size `300`
  - scenarios:
    - `goblin_screen`
    - `orc_push`
    - `marsh_predators`
- Top-line frozen results:
  - `goblin_screen`: players `69.0%`, enemies `31.0%`
  - `orc_push`: players `22.2%`, enemies `77.8%`
  - `marsh_predators`: players `63.0%`, enemies `37.0%`
- Git checkpoint at freeze time:
  - branch `main`
  - commit `f44fe42`
  - local worktree already had `32` changed paths, so this checkpoint was recorded in notes/report instead of as a broad catch-all commit

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
- Evil monsters may use exception hooks against tagged high-value targets, but not merely to reach a downed target

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

- player-side content:
  - `class_id`
  - `level`
  - `loadout_id`
  - `feature_ids`
  - `resource_pools`
  - `behavior_profile`
- monster-side content:
  - `base_creature_id`
  - `variant_id`
  - `combat_role`
  - `equipped_actions`
  - `behavior_profile`
  - `role_tags`

## Repository Organization

### Current Layout

- `src/` React frontend
- `src/shared/` frontend simulation helpers and transport types
- `backend/` Python engine and API
- `tests/` Python golden, rules, and API tests
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
- final decision on UI technology for V4 after the current React frontend stops being the default

## Change Log

### 2026-04-17

- Added DM behavior system to the current proof of concept
- Set default batch mode to balanced players plus combined DM splits
- Established V4 milestone roadmap
- Decided to maintain master notes in this file
- Wired the React UI to call the Python FastAPI backend for run and batch execution
- Completed V4.0 Python parity backend verification and frontend cutover
- Added async batch-job progress polling for longer Python batch runs

### 2026-04-18

- Added `V4.1.5` as the approved intermediate refactor milestone between preset roster expansion and broader class / monster work
- Locked in the architecture direction of data-driven monster definitions plus reusable trait, action, and AI-profile registries
- Implemented `V4.1.5` registries for monster traits, combat actions, and AI profiles
- Migrated the current 8-monster roster onto the new content model without changing the external API shape

### 2026-04-19

- Added giant toad and crocodile content on top of the V4.1.5 monster architecture
- Added large-creature occupancy, swallow-state combat flow, and crocodile grapple behavior to the live simulator
- Promoted `marsh_predators` into the active scenario set and kept `giant_toad_solo` as a backend-only focused rules fixture
- Updated the marsh layout to two giant toads plus a three-crocodile northwest cluster
- Standardized the recommended backend validation workflow around `ruff`, targeted Python test suites, and saved scenario audit reports
- Started `V4.2-A` by introducing backend-owned class, progression, feature, loadout, spell, and scenario registries
- Replaced the hardcoded fighter template with a content-defined player sample build and player preset
- Added a backend-owned player catalog endpoint while keeping the live run/batch payload stable
