# SRD Usage In This Project

## Purpose

This document explains how the D&D Encounter Simulator uses the System Reference
Document (SRD) as source material. The short version is that the SRD is a
reference corpus, not a runtime dependency. The simulator does not load the SRD
PDF during combat. Instead, selected SRD creatures, spells, classes, actions,
and combat mechanics are manually reduced into backend content registries and
shared rules handlers.

For a technical paper, the most accurate framing is:

> The SRD provided the bounded rules-and-content reference set. The project then
> implemented a selected combat-focused subset as deterministic Python data
> structures, rule resolvers, AI policies, scenarios, and validation tests.

## Local SRD Reference Files

The local reference material lives in `docs/reference/`.

| File | Role In The Project |
| --- | --- |
| `SRD_CC_v5.2.1.pdf` | Main SRD reference document used for rules, spells, monsters, classes, and attribution/licensing context |
| `srd_Creatures_Trimmed_V4.xlsx` | Working creature-intake workbook used to track which SRD creatures are candidates and which are modeled |
| `TrimmedSpellListV2.xlsx` | Working spell-intake workbook used to track which SRD spells are candidates and which are modeled |
| `dnd_2024_encounter_sim_prd.pdf` | Project/product requirements reference, separate from the SRD itself |

The SRD PDF identifies SRD 5.2.1 as provided under the Creative Commons
Attribution 4.0 International license. If project material is distributed
publicly, the attribution language from the SRD PDF should be included in the
distributed artifact. This document is an engineering summary, not legal advice.

## Trimmed SRD Intake

The project narrows the full SRD into combat-relevant implementation queues.
Those queues are maintained in spreadsheets rather than by copying the whole SRD
into the codebase.

### Creature Intake

`docs/reference/srd_Creatures_Trimmed_V4.xlsx` has one sheet, `SRD Creatures`.
The workbook tracks 289 creature rows with columns for:

- creature name
- challenge rating
- creature type
- SRD section/page reference
- size
- movement modes and speeds
- hover capability
- Pack Tactics
- Multiattack
- whether the creature is simple enough for straightforward modeling
- source URL
- modeled status

The current workbook status is:

| Modeled Status | Count |
| --- | ---: |
| `Yes` | 82 |
| `No` | 194 |
| blank | 13 |

This workbook is an intake and traceability tool. It helps answer, "Which SRD
creatures have been reviewed or modeled?" The live simulator still uses
`backend/content/enemies.py` as the runtime source of truth.

### Spell Intake

`docs/reference/TrimmedSpellListV2.xlsx` has one sheet, `SRD Spells`. The
workbook tracks 202 spell rows with columns for:

- spell name
- spell level
- school
- modeled status
- class access flags for Bard, Cleric, Druid, Paladin, Ranger, Sorcerer,
  Warlock, and Wizard

The current workbook status is:

| Modeled Status | Count |
| --- | ---: |
| `Yes` | 23 |
| `No` | 179 |

As with creatures, the spell workbook is an intake and planning artifact. The
runtime spell registry is `backend/content/spell_definitions.py`, and the
runtime spell behavior is resolved mainly through `backend/engine/rules` and the
combat engine.

## How SRD Material Becomes Simulator Content

The project uses a staged intake process:

1. Identify candidate SRD material in the PDF and trimmed workbooks.
2. Decide whether the item is useful for tactical combat simulation.
3. Convert the item into the project's typed backend model.
4. Implement only the mechanics needed for the simulator's current scope.
5. Attach the item to reusable AI profiles, combat actions, spell resolvers, or
   special-action handlers.
6. Add targeted tests, audit expectations, or scenario coverage.
7. Mark the trimmed workbook row as modeled when the implementation is
   represented in the simulator.

This means the SRD is not copied wholesale. The implementation extracts
combat-relevant structure and translates it into the project's own data model.

## Runtime Implementation Sources

The backend content registries are the source of truth during simulation.

| Runtime Area | Main File | Current Role |
| --- | --- | --- |
| Monsters and enemy presets | `backend/content/enemies.py` | Monster definitions, attacks, traits, spellcasting hooks, terrain helpers, enemy presets, benchmark presets |
| Spells | `backend/content/spell_definitions.py` | Spell metadata and combat-relevant spell fields |
| Classes | `backend/content/class_definitions.py` | Supported class identities and basic class metadata |
| Progressions | `backend/content/class_progressions.py` | Level-based features, resources, proficiency, dice, and scalar values |
| Features | `backend/content/feature_definitions.py` | Combat features and granted actions/maneuvers |
| Actions | `backend/content/combat_actions.py` | Reusable action vocabulary such as attack, dash, hide, rage, Second Wind, and class/spell actions |
| Maneuvers | `backend/content/maneuver_definitions.py` | Battle Master maneuver metadata and helper calculations |
| Special actions | `backend/content/special_actions.py` | Dragon breath, legendary/fear/sphere actions, and other nonstandard monster actions |
| Scenarios | `backend/content/scenario_definitions.py` | Scenario presets, placements, terrain, delayed arrivals, and standard battery definitions |

The current backend contains:

| Registry | Count |
| --- | ---: |
| Monster definitions | 87 |
| Enemy presets | 97 |
| Spell definitions | 28 |
| Class definitions | 6 |
| Feature definitions | 51 |
| Combat actions | 21 |
| Maneuver definitions | 3 |
| Generic special actions | 10 |
| Dragon breath action definitions | 5 |

These counts are implementation counts, not claims that the full SRD is
complete.

## Creature Modeling

SRD creatures are translated into `MonsterDefinition` records and related
runtime structures. The simulator stores implementation-oriented fields such as:

- display name
- combat role
- size and footprint
- armor class and hit points
- speed and movement modes
- initiative modifier
- saving throw and ability modifiers where needed
- attacks and damage profiles
- available actions, bonus actions, and reactions
- creature tags and traits
- spellcasting or special-action hooks
- AI behavior profile

The project often creates explicit combat variants rather than treating the SRD
creature name as enough information. For example, a creature that can reasonably
support both melee and ranged roles can become separate melee and archer
variants. This keeps tactical behavior data-driven and avoids burying encounter
logic in creature-name branches.

The SRD provides the creature concept and baseline rules reference. The
simulator adds project-specific modeling choices such as tactical role,
positioning profile, scenario placement, and benchmark-preset behavior.

## Spell Modeling

SRD spells are translated into `SpellDefinition` entries and, when needed,
runtime resolver logic.

The project distinguishes between:

- metadata-only spells, which are known to the content system but do not yet
  have full combat behavior
- runtime-modeled spells, which have actual effects in combat simulation
- class-access metadata, which controls which class/loadout can know or prepare
  a spell
- special spell-like monster abilities, which may reuse spell definitions while
  still using monster-specific values

`backend/content/spell_definitions.py` records spell metadata. Combat behavior
is then implemented in shared places such as:

- `backend/engine/rules/spell_resolvers.py`
- `backend/engine/rules/combat_rules.py`
- `backend/engine/combat/engine.py`

This separation matters because it lets the project track SRD spell content
without pretending every listed spell has complete runtime mechanics.

## Class And Feature Modeling

The SRD informs the supported class concepts, but the project models only the
combat-relevant subset needed for the current simulator.

Current class definitions include:

- Barbarian
- Fighter
- Monk
- Paladin
- Rogue
- Wizard

The simulator does not attempt to be a full character builder. Instead, it uses:

- `class_definitions.py` for class identity
- `class_progressions.py` for level-based features and resources
- `feature_definitions.py` for combat features and granted actions
- `player_loadouts.py` for fixed sample builds

This supports repeatable encounters and paper-friendly comparisons because each
run uses controlled party definitions rather than arbitrary character sheets.

## Rules Modeling

The SRD provides the general rules reference, while the simulator implements a
selected tactical combat subset. Current modeled areas include concepts such as:

- seeded d20 rolls and damage rolls
- initiative and round progression
- attack rolls and damage resolution
- saving throws
- concentration support
- opportunity attacks
- death and rescue logic
- grid movement and positioning
- terrain, cover, and line interactions
- action, bonus-action, reaction, and multiattack behavior
- selected spell and special-action effects

Rules are implemented as executable state transitions rather than as copied SRD
text. The main rules files are:

- `backend/engine/combat/setup.py`
- `backend/engine/combat/engine.py`
- `backend/engine/rules/combat_rules.py`
- `backend/engine/rules/spell_resolvers.py`
- `backend/engine/rules/spatial.py`
- `backend/engine/utils/rng.py`

## Validation Against SRD Intake

The project uses tests and reports to keep SRD-derived content traceable.

Examples:

- `tests/rules/test_monster_content.py` loads
  `docs/reference/srd_Creatures_Trimmed_V4.xlsx` and checks that specific
  workbook rows marked as completed remain marked `Yes`.
- Monster-content tests compare implemented monster definitions against
  expectation tables.
- Spell and player-class docs separate runtime-modeled features from
  metadata-only or deferred features.
- Scenario validation and party-validation reports test whether modeled content
  actually appears in simulated encounters.

This is important for the paper because it shows that SRD intake is not merely a
list of inspirations. The project ties intake, implementation, and validation
together.

## What The SRD Does Not Mean Here

Using the SRD does not mean:

- every SRD monster is implemented
- every SRD spell is implemented
- every class feature is implemented
- non-combat D&D systems are modeled
- the simulator is a complete tabletop rules engine
- the UI interprets SRD text directly
- the SRD PDF is used as runtime data

The simulator is intentionally narrower. It focuses on deterministic tactical
combat, scenario comparison, replay, and batch validation.

## Recommended Paper Framing

For the technical paper, describe the SRD role this way:

1. The SRD established a publicly available reference set for D&D-style
   creatures, spells, classes, and combat rules.
2. The project trimmed that reference set into creature and spell workbooks.
3. The project manually converted selected rows into Python content registries.
4. The project implemented only combat-relevant behavior in shared rule
   handlers.
5. The project validated those implementations through tests, scenario audits,
   replay smoke checks, and party-validation batch reports.

This framing is accurate and defensible because it separates source reference,
implementation, and validation.

