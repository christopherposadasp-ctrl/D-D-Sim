# Content Backlog

## Purpose

This document tracks planned content growth for V4.

It is the working backlog for:

- enemy roster expansion
- preset encounter mixes
- class support
- monster traits
- spell-system primitives
- trimmed SRD spell/monster intake

## Status Labels

- `approved`: confirmed for the current roadmap
- `candidate`: good fit, not locked
- `deferred`: intentionally delayed
- `blocked`: depends on another milestone

## V4.0 Parity Backlog

Status: `approved`

Must reproduce the current proof of concept:

- current fighter build
- current goblin melee/archer split
- current player behaviors
- current DM behaviors
- current grid rules
- current flanking interpretation
- current opportunity attack logic
- current replay and batch summary shape

## V4.1 Starter Enemy Roster

Status: `approved`

### Starter Eight

| Enemy | Variant Type | Status | Notes |
|---|---|---|---|
| Goblin Raider | melee | approved | baseline skirmisher |
| Goblin Archer | ranged | approved | ranged goblin baseline |
| Bandit Melee | melee | approved | simple humanoid melee |
| Bandit Archer | ranged | approved | simple humanoid ranged |
| Guard | melee | approved | defensive humanoid |
| Scout | ranged/mobile | approved | ranged skirmisher baseline |
| Orc Warrior | melee | approved | brute pressure test |
| Wolf | melee | approved | pack/animal behavior test |

### Roster Notes

- use explicit melee/archer variants where plausible
- do not force artificial variants for creatures that clearly fit one role
- this roster is meant for easy implementation and test variety, not final breadth

## V4.1 Preset Mixes

Status: `approved`

### Starter Five Presets

| Preset | Composition | Status | Purpose |
|---|---|---|---|
| Goblin Screen | 3 Goblin Raiders, 3 Goblin Archers | approved | skirmish and range pressure |
| Bandit Ambush | 2 Bandit Melee, 2 Bandit Archers, 1 Scout | approved | mixed humanoid baseline |
| Mixed Patrol | 2 Guards, 2 Goblin Archers, 1 Bandit Melee, 1 Scout | candidate | mixed-role early test |
| Orc Push | 4 Orc Warriors, 2 Goblin Archers | approved | frontline pressure plus ranged support |
| Wolf Harriers | 3 Wolves, 2 Goblin Archers, 1 Goblin Raider | approved | mobility and focus-fire test |

### Preset Design Rules

- presets should feel different in play
- presets should avoid requiring spell support in V4.1
- presets should cover melee-heavy, ranged-heavy, and mixed-role cases

## V4.2 Martial Classes Up To Level 2

Status: `approved`

### Priority Order

| Class | Status | Notes |
|---|---|---|
| Fighter | approved | already represented in V3 concept |
| Rogue | approved | high-value target and mobility testing |
| Barbarian | approved | resource/rage and durability pressure |
| Monk | approved | mobility and action-economy stress |
| Ranger | deferred | better after spell framework exists |
| Paladin | deferred | spell-adjacent even before broader casting support |

### Framework Goal

Use V4.2 to establish the player-content framework:

- class definitions
- class progressions
- feature definitions
- player loadouts
- player presets
- minimal reusable resource and hook primitives

### Current Live Snapshot

- Fighter is live to level 2
- Barbarian is live to level 2
- Rogue is live to level 2
- Monk is live to level 2 in `V4.2-C`
- Wizard is live to level 1 as a narrow combat-only slice with `fire_bolt`, `shocking_grasp`, `magic_missile`, `shield`, `burning_hands`, and tracked spell access counts
- The current default mixed party is:
  - level 2 fighter
  - level 2 barbarian
  - level 2 ranged rogue
  - level 2 melee rogue

### V4.2 Phase Targets

| Phase | Scope | Status |
|---|---|---|
| V4.2-A | framework and current fighter sample build on registries | approved |
| V4.2-B | Fighter and Rogue | approved |
| V4.2-C | Barbarian and Monk | approved |

## V4.3 Non-Spell Monsters Below CR 3

Status: `approved`

### Scope Target

- add 50 non-spellcasting monsters below CR 3
- add 5 new scenarios
- group monsters by reusable behavior shape instead of one-off branches

### Trait/Ability Backlog

| Trait or Ability Shape | Status | Notes |
|---|---|---|
| Pack tactics style bonus | candidate | useful for wolves/goblins if included |
| Formation/combat discipline bonus | candidate | useful for guards/hobgoblin-like enemies |
| Charge/impact opener | candidate | melee monster pressure pattern |
| Bonus damage rider | approved | already familiar from goblin advantage rider |
| Grapple/shove style rider | candidate | useful for variety without spells |
| Multiattack support | approved | needed for scaling monster roster |
| Recharge action support | deferred | not needed for earliest easy roster |

### V4.3 Phase Targets

| Phase | Scope | Status |
|---|---|---|
| V4.3-A | monster intake schema, trait library, audit checklist | approved |
| V4.3-B | first 25 monsters | approved |
| V4.3-C | second 25 monsters plus 5 scenarios | approved |

## V4.4 Spellcaster Classes Up To Level 2

Status: `approved`

### Must Exist Before Broad Spell Intake

| Primitive | Status | Notes |
|---|---|---|
| concentration | approved | foundational |
| duration tracking | approved | foundational |
| saving throws | approved | foundational |
| AoE targeting | approved | foundational |
| buff/debuff application | approved | foundational |
| ongoing effects | approved | foundational |
| forced movement | candidate | likely needed early |
| upcasting/scaling | approved | required for many spells |
| reaction hooks | approved | required for later reaction magic |

### Class Scope

- Wizard
- Sorcerer
- Cleric
- Bard
- Druid
- Warlock

### V4.4 Phase Targets

| Phase | Scope | Status |
|---|---|---|
| V4.4-A | spell slots, preparation, combat spell catalog, targeting, saves, concentration | approved |
| V4.4-B | Wizard, Sorcerer, Cleric | approved |
| V4.4-C | Bard, Druid, Warlock | approved |

## V4.5 Half-Caster Classes Up To Level 2

Status: `approved`

### Class Scope

- Paladin
- Ranger

### V4.5 Phase Targets

| Phase | Scope | Status |
|---|---|---|
| V4.5-A | Paladin and Ranger class packages on the shared spell framework | approved |
| V4.5-B | class AI tuning, presets, and mixed-party validation | approved |

### AI Capabilities To Reuse and Extend

| Capability | Status | Notes |
|---|---|---|
| ally healing priority | approved | core healer behavior |
| concentration preservation | approved | caster decision quality |
| AoE spell valuation | approved | must avoid random spell use |
| counterspell timing | blocked | requires spell/reaction primitives |
| reaction spell choice | blocked | depends on legal action framework |

## Deferred/Not Immediate

### Deferred Until After Core Stability

- summon-heavy spell families
- transformation-heavy spell families
- illusion-heavy spells
- terrain-editing spells
- very high-interpretation monster abilities

These are not rejected. They are delayed until the engine primitives are stable enough to support them cleanly.

## Open Backlog Questions

- which trimmed monster list should land first after V4.3
- which trimmed spell list should land first after V4.4
- whether early V4 should support only curated presets or also free-form encounter building
