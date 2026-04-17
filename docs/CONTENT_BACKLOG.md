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

## V4.2 Martial Classes

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

### Support Goal

Target support should extend through level 11 for included base classes, but milestone sequencing should favor rules simplicity first.

## V4.3 Non-Spell Monster Framework

Status: `approved`

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

## V4.4 Spell Framework Primitives

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

## V4.5 Healer/Caster AI and Reaction Magic

Status: `approved`

### AI Capabilities To Add

| Capability | Status | Notes |
|---|---|---|
| ally healing priority | approved | core healer behavior |
| concentration preservation | approved | caster decision quality |
| AoE spell valuation | approved | must avoid random spell use |
| counterspell timing | blocked | requires spell/reaction primitives |
| reaction spell choice | blocked | depends on legal action framework |

## V4.6 Trimmed SRD Intake

Status: `blocked`

This milestone depends on the curated lists being prepared separately.

### Expected Monster Intake Format

Use a structured list with fields like:

- `monster_id`
- `display_name`
- `include`
- `reason`
- `difficulty_tag`
- `needs_special_rules`
- `depends_on`

### Expected Spell Intake Format

Use a structured list with fields like:

- `spell_id`
- `display_name`
- `include`
- `reason`
- `combat_relevance`
- `complexity_tag`
- `needs_special_rules`
- `depends_on`

### Suggested Complexity Tags

- `easy`
- `medium`
- `hard`
- `special_case`

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
- whether Ranger and Paladin should partially enter before full general spell support
- whether early V4 should support only curated presets or also free-form encounter building
