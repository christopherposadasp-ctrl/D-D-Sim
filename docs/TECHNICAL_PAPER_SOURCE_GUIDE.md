# Technical Paper Source Guide

This guide explains how to use the project Markdown files and selected source
files as evidence for a 10-page technical paper on the D&D encounter simulator.
It is written for a ChatGPT Pro project-file packet: upload this guide first,
then upload the referenced documents and code files.

## Recommended Paper Focus

A strong technical paper should present the simulator as a deterministic,
backend-owned combat simulation system for comparing D&D encounter behavior
under different party and DM assumptions.

The central thesis can be:

> This project models D&D-style tactical encounters by separating combat rules,
> content definitions, AI policy, API transport, and UI replay, allowing the
> same backend engine to produce deterministic single-run replays and aggregate
> batch comparisons across player and DM behavior settings.

The paper should not try to describe every implemented rule. It should explain
the system architecture, the simulation method, the behavior settings, the
content model, one representative scenario, and the validation strategy.

## Minimum Markdown Packet

Upload these Markdown files first. Together, they are detailed enough to support
a 10-page paper when combined with a small set of source files.

| File | Use In The Paper | Why It Matters |
| --- | --- | --- |
| `README.md` | Project overview, current capabilities, local stack, commands | Gives the broad project framing and current feature snapshot |
| `docs/V4_ARCHITECTURE.md` | Architecture and design rationale | Explains backend authority, module boundaries, replay model, API, and tests |
| `docs/PYTHON_FLOW_GUIDE.md` | Implementation walkthrough | Explains how the backend files fit together during a single encounter and batch run |
| `docs/DM_PLAYER_SETTINGS.md` | Experimental variables | Explains Smart/Dumb/Balanced players and Kind/Balanced/Evil DMs |
| `docs/STANDARD_BATTERY_SCENARIOS.md` | Scenario methodology and Frostfall case study | Explains the standard scenario set and what each scenario is designed to test |
| `docs/PLAYER_CHARACTER_CLASSES.md` | Player content model | Explains modeled classes, class features, progressions, and party presets |
| `docs/MONSTER_MODELING.md` | Enemy content model | Explains monster variants, AI profiles, runtime features, and limitations |
| `docs/MODELED_SPELLS.md` | Spell content model | Explains which spells are actively resolved and which are metadata-only |

## Source Files To Upload For Evidence

The Markdown files explain the design. These source files prove how the design
is implemented.

| Source File | What It Proves |
| --- | --- |
| `backend/engine/combat/setup.py` | Encounter creation, seed normalization, placements, initiative rolls, and behavior resolution |
| `backend/engine/combat/engine.py` | Main combat loop, turn sequencing, action resolution, replay-frame creation, and terminal-state handling |
| `backend/engine/models/state.py` | Core simulation data model: encounter state, units, events, actions, effects, and replay frames |
| `backend/engine/ai/profiles.py` | Monster behavior profiles such as melee brute, ranged skirmisher, pack hunter, grappler, and dragon |
| `backend/engine/ai/decision.py` | Player and DM decision logic, including target selection and tactical behavior |
| `backend/engine/rules/combat_rules.py` | Shared combat rules such as attack support, cover/flanking interactions, reactions, saves, and state checks |
| `backend/engine/rules/spell_resolvers.py` | Runtime spell resolution for spells that affect combat outcomes |
| `backend/content/scenario_definitions.py` | Scenario layouts, terrain, enemy rosters, delayed arrivals, and Frostfall Courtyard setup |
| `backend/content/player_loadouts.py` | Party composition and player preset definitions |
| `backend/content/enemies.py` | Enemy and monster stat/content definitions |
| `public/presentation/frostfall_courtyard_variant_party_victory_fireball_haste_paladin_pickup_low_hp_seed_frostfall-variant-0034.json` | Concrete fixed-seed replay evidence for the Frostfall presentation case study |

## Suggested 10-Page Structure

Use this structure to keep the paper technical without becoming a code dump.

| Page Range | Section | Main Sources |
| --- | --- | --- |
| 1 | Introduction and project goal | `README.md`, `docs/V4_ARCHITECTURE.md` |
| 2 | System architecture | `docs/V4_ARCHITECTURE.md`, `docs/PYTHON_FLOW_GUIDE.md` |
| 3 | Simulation state and deterministic replay | `backend/engine/models/state.py`, `backend/engine/combat/setup.py`, `backend/engine/combat/engine.py` |
| 4 | Combat turn pipeline | `docs/PYTHON_FLOW_GUIDE.md`, `backend/engine/combat/engine.py`, `backend/engine/rules/combat_rules.py` |
| 5 | Player and DM behavior settings | `docs/DM_PLAYER_SETTINGS.md`, `backend/engine/ai/decision.py`, `backend/engine/ai/profiles.py` |
| 6 | Player, monster, and spell content modeling | `docs/PLAYER_CHARACTER_CLASSES.md`, `docs/MONSTER_MODELING.md`, `docs/MODELED_SPELLS.md` |
| 7 | Scenario battery methodology | `docs/STANDARD_BATTERY_SCENARIOS.md`, `backend/content/scenario_definitions.py` |
| 8 | Frostfall Courtyard case study | `docs/STANDARD_BATTERY_SCENARIOS.md`, Frostfall replay JSON |
| 9 | Testing, validation, and reproducibility | `docs/V4_ARCHITECTURE.md`, `README.md`, `tests/`, `scripts/run_party_validation.py` |
| 10 | Limitations, future work, and conclusion | `docs/V4_ARCHITECTURE.md`, `docs/MONSTER_MODELING.md`, `docs/MODELED_SPELLS.md`, `docs/MASTER_NOTES.md` |

## Paper-Ready Technical Claims

These claims are supported by the Markdown packet and source files.

1. The Python backend is the simulation authority.
   - Evidence: `docs/V4_ARCHITECTURE.md`, `README.md`, `backend/engine/combat/engine.py`.
   - Explanation: The frontend consumes backend-produced catalogs, state payloads, and replay frames. It does not own combat rules.

2. The simulator uses deterministic seeded execution.
   - Evidence: `docs/V4_ARCHITECTURE.md`, `backend/engine/combat/setup.py`, `backend/engine/utils/rng.py`.
   - Explanation: Encounter creation normalizes a seed into RNG state, and combat rolls advance that state. Fixed seeds allow reproducible scenarios and replays.

3. Combat is replay-first.
   - Evidence: `docs/V4_ARCHITECTURE.md`, `docs/PYTHON_FLOW_GUIDE.md`, `backend/engine/combat/engine.py`.
   - Explanation: The engine produces structured events and replay frames. The UI can scrub or present those frames without rerunning the simulation.

4. Player behavior and DM behavior are separate experimental controls.
   - Evidence: `docs/DM_PLAYER_SETTINGS.md`, `backend/engine/combat/setup.py`, `backend/engine/combat/batch.py`, `backend/engine/ai/decision.py`.
   - Explanation: Player Behavior controls party decision policy. DM Style controls enemy target pressure. Balanced Players is a run-selection mode, while Balanced DM is one concrete enemy policy.

5. Content is modeled through registries and shared handlers.
   - Evidence: `docs/V4_ARCHITECTURE.md`, `docs/PLAYER_CHARACTER_CLASSES.md`, `docs/MONSTER_MODELING.md`, `docs/MODELED_SPELLS.md`, `backend/content/`.
   - Explanation: Classes, monsters, spells, traits, and scenarios are defined in backend content modules. Shared rules handlers resolve common mechanics.

6. The Frostfall scenario is a representative capstone case study.
   - Evidence: `docs/STANDARD_BATTERY_SCENARIOS.md`, `backend/content/scenario_definitions.py`, Frostfall replay JSON.
   - Explanation: Frostfall combines a kobold opener, fixed terrain, delayed dragon arrival, spell/resource decisions, large-creature geometry, cold breath, and replay presentation.

7. Validation uses a mix of golden tests, narrow rules tests, integration tests, audits, and batch scenario runs.
   - Evidence: `docs/V4_ARCHITECTURE.md`, `README.md`, `tests/`, `scripts/run_party_validation.py`.
   - Explanation: The test strategy checks both small mechanics and whole-scenario behavior.

## How To Use The Markdown Files

The documents should be treated as complementary sources:

- Use `README.md` for project scope and current capability claims.
- Use `V4_ARCHITECTURE.md` for design choices and module ownership.
- Use `PYTHON_FLOW_GUIDE.md` when the paper needs implementation-level file flow.
- Use `DM_PLAYER_SETTINGS.md` for the paper's behavior-setting explanation.
- Use `STANDARD_BATTERY_SCENARIOS.md` for experimental/scenario methodology.
- Use `PLAYER_CHARACTER_CLASSES.md`, `MONSTER_MODELING.md`, and `MODELED_SPELLS.md`
  for the modeled content scope and boundaries.

The best paper will quote or paraphrase these files for design intent, then cite
source files for implementation evidence.

## Known Limitations To Discuss

The paper should explicitly acknowledge these boundaries.

- The simulator is not a full D&D rules engine. It models a selected tactical
  slice of classes, monsters, spells, terrain, and combat rules.
- Some content is metadata-only or partially modeled, especially where full D&D
  behavior would require broad non-combat systems.
- Enemy initiative currently uses a simplified opposing-force roll at encounter
  creation, while player characters roll individually.
- AI behavior is heuristic and deterministic under a seed. It is not a learned
  model and does not represent all possible human tabletop choices.
- The UI replay is a visualization of backend-generated frames. It is not a
  separate simulation authority.
- Batch results depend on the selected scenario battery, party preset, behavior
  settings, and seed/run configuration.

## Recommended ChatGPT Pro Instruction

After uploading the packet, give ChatGPT Pro an instruction like this:

```text
You are helping me write a 10-page technical paper on this D&D encounter
simulation project. Use TECHNICAL_PAPER_SOURCE_GUIDE.md as the routing document.
Ground claims in the uploaded Markdown files and source files. Explain the
architecture, deterministic simulation method, combat turn loop, behavior
settings, content model, Frostfall Courtyard case study, validation strategy,
limitations, and future work. Do not invent unsupported D&D rules or project
features.
```

