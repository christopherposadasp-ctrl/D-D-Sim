# Monster Modeling Reference

This document summarizes the current monster model used by the simulator. It is based on the content-driven monster definitions in `backend/content/enemies.py`, the shared monster traits in `backend/content/monster_traits.py`, the special-action registries in `backend/content/special_actions.py`, and the broad AI profiles in `backend/engine/ai/profiles.py`.

The simulator models monster variants, not just base creature names. For example, Goblins, Hobgoblins, Kobolds, and Bandits have separate melee/ranged/leader variants where those variants behave differently in combat.

## Current Monster Inventory

This table lists every current `MonsterDefinition` variant. `Traits` are reusable trait ids. `Special Actions` are non-standard actions resolved outside ordinary weapon attacks. `Notes` includes damage defenses, creature identity tags, movement metadata, and condition-immunity metadata.

| Variant ID | Display Name | AI Profile | AC | HP | Size | Traits | Special Actions | Notes |
|---|---|---:|---:|---:|---|---|---|---|
| `adult_red_dragon` | Adult Red Dragon | `dragon` | 19 | 256 | huge | opening_flight_landing, legendary_resistance | fire_breath, scorching_ray, command, fireball | immune fire; creature tags: dragon; movement: walk, climb, fly |
| `adult_white_dragon` | Adult White Dragon | `dragon` | 18 | 200 | huge | ice_walk, opening_flight_landing, legendary_resistance | cold_breath | immune cold; creature tags: dragon; movement: walk, burrow, fly, swim |
| `animated_armor` | Animated Armor | `melee_brute` | 18 | 33 | medium | - | - | immune poison, psychic |
| `ankylosaurus` | Ankylosaurus | `melee_brute` | 15 | 68 | huge | - | - | - |
| `ape` | Ape | `melee_brute` | 12 | 19 | medium | - | - | - |
| `archelon` | Archelon | `melee_brute` | 17 | 90 | huge | - | - | - |
| `awakened_shrub` | Awakened Shrub | `melee_brute` | 9 | 10 | small | - | - | resist piercing; vulnerable fire |
| `awakened_tree` | Awakened Tree | `melee_brute` | 13 | 59 | huge | - | - | resist bludgeoning, piercing; vulnerable fire |
| `axe_beak` | Axe Beak | `melee_brute` | 11 | 19 | large | - | - | - |
| `baboon` | Baboon | `pack_hunter` | 12 | 3 | small | pack_tactics | - | - |
| `badger` | Badger | `melee_brute` | 11 | 5 | tiny | - | - | resist poison |
| `bandit_archer` | Bandit Archer | `ranged_skirmisher` | 12 | 11 | medium | - | - | - |
| `bandit_captain` | Bandit Captain | `ranged_skirmisher` | 15 | 52 | medium | - | - | - |
| `bandit_melee` | Bandit Melee | `melee_brute` | 12 | 11 | medium | - | - | - |
| `berserker` | Berserker | `melee_brute` | 13 | 67 | medium | bloodied_frenzy | - | - |
| `black_bear` | Black Bear | `melee_brute` | 11 | 19 | medium | - | - | - |
| `boar` | Boar | `melee_brute` | 11 | 13 | medium | bloodied_fury, charge | - | - |
| `brown_bear` | Brown Bear | `melee_brute` | 11 | 22 | large | - | - | - |
| `bugbear_warrior` | Bugbear Warrior | `grappling_brute` | 14 | 33 | medium | - | - | - |
| `camel` | Camel | `melee_brute` | 10 | 17 | large | - | - | - |
| `cat` | Cat | `melee_brute` | 12 | 2 | tiny | jumper | - | - |
| `centaur_trooper` | Centaur Trooper | `line_holder` | 16 | 45 | large | - | - | - |
| `commoner` | Commoner | `melee_brute` | 10 | 4 | medium | - | - | - |
| `crab` | Crab | `melee_brute` | 11 | 3 | tiny | - | - | - |
| `crocodile` | Crocodile | `grappling_brute` | 12 | 13 | large | - | - | - |
| `cultist` | Cultist | `melee_brute` | 12 | 9 | medium | - | - | - |
| `deer` | Deer | `melee_brute` | 13 | 4 | medium | agile | - | - |
| `dire_wolf` | Dire Wolf | `pack_hunter` | 14 | 22 | large | pack_tactics | - | - |
| `draft_horse` | Draft Horse | `melee_brute` | 10 | 15 | large | - | - | - |
| `giant_badger` | Giant Badger | `melee_brute` | 13 | 15 | medium | - | - | resist poison |
| `giant_crab` | Giant Crab | `grappling_brute` | 15 | 13 | medium | - | - | - |
| `giant_fire_beetle` | Giant Fire Beetle | `melee_brute` | 13 | 4 | small | - | - | resist fire |
| `giant_hyena` | Giant Hyena | `melee_brute` | 12 | 45 | large | rampage | - | - |
| `giant_lizard` | Giant Lizard | `melee_brute` | 12 | 19 | large | - | - | - |
| `giant_rat` | Giant Rat | `pack_hunter` | 13 | 7 | small | pack_tactics | - | - |
| `giant_toad` | Giant Toad | `swallow_predator` | 11 | 39 | large | - | swallow | - |
| `giant_weasel` | Giant Weasel | `melee_brute` | 13 | 9 | medium | - | - | - |
| `gnoll_warrior` | Gnoll Warrior | `ranged_skirmisher` | 15 | 27 | medium | rampage | - | - |
| `goblin_archer` | Goblin Archer | `ranged_skirmisher` | 15 | 10 | small | nimble_escape | - | - |
| `goblin_boss` | Goblin Boss | `ranged_skirmisher` | 17 | 21 | small | nimble_escape | - | - |
| `goblin_minion` | Goblin Minion | `ranged_skirmisher` | 12 | 7 | small | nimble_escape | - | - |
| `goblin_raider` | Goblin Raider | `melee_brute` | 15 | 10 | small | nimble_escape | - | - |
| `grick` | Grick | `melee_brute` | 14 | 54 | medium | - | - | - |
| `griffon` | Griffon | `melee_brute` | 12 | 59 | large | opening_flight_landing | - | - |
| `grimlock` | Grimlock | `melee_brute` | 11 | 11 | medium | - | - | - |
| `guard` | Guard | `line_holder` | 16 | 11 | medium | - | - | - |
| `guard_captain` | Guard Captain | `ranged_skirmisher` | 18 | 75 | medium | - | - | - |
| `hippopotamus` | Hippopotamus | `melee_brute` | 14 | 82 | large | - | - | - |
| `hobgoblin_archer` | Hobgoblin Archer | `ranged_skirmisher` | 18 | 11 | medium | pack_tactics | - | - |
| `hobgoblin_captain` | Hobgoblin Captain | `line_holder` | 17 | 58 | medium | aura_of_authority | - | - |
| `hobgoblin_warrior` | Hobgoblin Warrior | `melee_brute` | 18 | 11 | medium | pack_tactics | - | - |
| `hyena` | Hyena | `pack_hunter` | 11 | 5 | medium | pack_tactics | - | - |
| `jackal` | Jackal | `melee_brute` | 12 | 3 | small | - | - | - |
| `knight` | Knight | `line_holder` | 18 | 52 | medium | - | - | condition immune frightened |
| `kobold_dragonshield` | Kobold Dragonshield | `line_holder` | 15 | 44 | small | pack_tactics, sunlight_sensitivity, heart_of_the_dragon | - | resist cold |
| `kobold_scale_sorcerer` | Kobold Scale Sorcerer | `ranged_skirmisher` | 15 | 27 | small | pack_tactics, sunlight_sensitivity | - | - |
| `kobold_slinger` | Kobold Slinger | `ranged_skirmisher` | 14 | 7 | small | pack_tactics, sunlight_sensitivity | - | - |
| `kobold_warrior` | Kobold Warrior | `pack_hunter` | 14 | 7 | small | pack_tactics, sunlight_sensitivity | - | - |
| `lemure` | Lemure | `melee_brute` | 9 | 9 | medium | - | - | resist cold; immune fire, poison |
| `mastiff` | Mastiff | `melee_brute` | 12 | 5 | medium | - | - | - |
| `mule` | Mule | `melee_brute` | 10 | 11 | medium | - | - | - |
| `noble` | Noble | `melee_brute` | 15 | 9 | medium | - | - | - |
| `ogre` | Ogre | `ranged_skirmisher` | 11 | 68 | large | - | - | - |
| `ogre_zombie` | Ogre Zombie | `melee_brute` | 8 | 85 | large | undead_fortitude | - | immune poison; creature tags: undead |
| `orc_warrior` | Orc Warrior | `melee_brute` | 13 | 15 | medium | aggressive | - | - |
| `owlbear` | Owlbear | `melee_brute` | 13 | 59 | large | - | - | - |
| `polar_bear` | Polar Bear | `melee_brute` | 12 | 42 | large | - | - | resist cold |
| `pony` | Pony | `melee_brute` | 10 | 11 | medium | - | - | - |
| `riding_horse` | Riding Horse | `melee_brute` | 11 | 13 | large | - | - | - |
| `saber_toothed_tiger` | Saber-Toothed Tiger | `melee_brute` | 13 | 52 | large | nimble_escape | - | - |
| `satyr` | Satyr | `ranged_skirmisher` | 13 | 31 | medium | magic_resistance | mockery | - |
| `scout` | Scout | `ranged_skirmisher` | 13 | 16 | medium | - | - | - |
| `skeleton` | Skeleton | `ranged_skirmisher` | 14 | 13 | medium | - | - | immune poison; vulnerable bludgeoning; creature tags: undead |
| `tiger` | Tiger | `melee_brute` | 13 | 30 | large | nimble_escape | - | - |
| `tough` | Tough | `ranged_skirmisher` | 12 | 32 | medium | pack_tactics | - | - |
| `violet_fungus` | Violet Fungus | `melee_brute` | 5 | 18 | medium | - | - | - |
| `warhorse_skeleton` | Warhorse Skeleton | `melee_brute` | 13 | 22 | large | - | - | immune poison; vulnerable bludgeoning; condition immune exhaustion, poisoned; creature tags: undead |
| `warrior_infantry` | Warrior Infantry | `line_holder` | 13 | 9 | medium | pack_tactics | - | - |
| `warrior_veteran` | Warrior Veteran | `line_holder` | 17 | 65 | medium | - | - | - |
| `weasel` | Weasel | `melee_brute` | 13 | 1 | tiny | - | - | - |
| `white_guard_drake` | White Guard Drake | `line_holder` | 14 | 60 | medium | - | - | resist cold; movement: walk, burrow, climb |
| `wolf` | Wolf | `pack_hunter` | 13 | 11 | medium | pack_tactics | - | - |
| `worg` | Worg | `melee_brute` | 13 | 26 | large | - | - | - |
| `young_red_dragon` | Young Red Dragon | `dragon` | 18 | 178 | large | opening_flight_landing | fire_breath | immune fire; creature tags: dragon; movement: walk, climb, fly |
| `young_white_dragon` | Young White Dragon | `dragon` | 17 | 123 | large | ice_walk, opening_flight_landing | cold_breath | immune cold; creature tags: dragon; movement: walk, burrow, fly, swim |
| `young_white_dragon_boss` | Young White Dragon Boss | `dragon` | 18 | 178 | huge | ice_walk, opening_flight_landing, legendary_resistance | cold_breath | immune cold; creature tags: dragon; movement: walk, burrow, fly, swim |
| `zombie` | Zombie | `melee_brute` | 8 | 15 | medium | undead_fortitude | - | immune poison; creature tags: undead |

## Variant Families

Several base creatures intentionally have multiple variants because their battlefield role changes substantially.

- Goblins: `goblin_raider`, `goblin_archer`, `goblin_minion`, and `goblin_boss`.
- Bandits: `bandit_melee`, `bandit_archer`, and `bandit_captain`.
- Hobgoblins: `hobgoblin_warrior`, `hobgoblin_archer`, and `hobgoblin_captain`.
- Kobolds: `kobold_warrior`, `kobold_slinger`, `kobold_dragonshield`, and `kobold_scale_sorcerer`.
- Dragons: young, adult, and boss variants are separate entries because breath profiles, legendary resources, footprint, and AI priorities differ.

## Monster AI Profiles

AI profiles are broad behavior classes. Specific monster behavior still depends on legal attacks, traits, reactions, special actions, resource pools, and the configured DM behavior (`kind`, `balanced`, or `evil`).

### `melee_brute`

General close-and-fight behavior.

- Picks a melee weapon and tries to move into legal melee range.
- Uses DM behavior as target ordering: kind prefers less cruel target selection, balanced tends toward practical low-HP pressure, and evil may pressure high-value/downed targets when legal.
- If no melee attack is reachable, it dashes toward a target.
- Does not preserve formation and does not have special ranged fallback logic.

### `line_holder`

Disciplined front-line behavior for guards, soldiers, captains, and defensive monsters.

- If already adjacent to a conscious PC, attacks an adjacent PC instead of abandoning the line.
- When not adjacent, prefers nearby/frontline reachable targets.
- Prefers melee over ranged.
- Uses a ranged weapon only when melee is not reachable.
- If no melee or ranged option exists, dashes toward the closest/frontline threat.
- Does not intentionally provoke opportunity attacks for backline pressure.

### `ranged_skirmisher`

Ranged-first behavior for archers, scouts, casters, and hybrid ranged monsters.

- Opens with the preferred ranged weapon or special ranged action when it has a clean shot.
- Moves to create or preserve ranged attacks.
- Can attack at long range if no normal-range shot exists.
- If pinned adjacent and it lacks bonus-action Disengage, it commits to melee.
- If it has `nimble_escape`, it can Disengage before repositioning for ranged pressure.
- Some ranged skirmishers are still hybrid monsters with legal melee fallbacks.

### `pack_hunter`

Melee behavior for wolves, rats, hyenas, and similar pack attackers.

- Still moves and attacks like a melee creature.
- Prefers targets that already have allied monster support.
- Prefers attack squares that create or join supported/flanking positions.
- Keeps DM behavior as a tie-breaker after support preference.
- Does not gain extra attacks or movement; distinctiveness comes from target and square selection.

### `grappling_brute`

Melee behavior for monsters that lock down a victim.

- Uses normal melee behavior until it has a grappled target.
- Once it has an active grapple, keeps pressure on that target when a legal follow-up attack exists.
- Bugbear Warrior uses this to grab first, then gain advantage with hammer attacks against its own grappled target.

### `swallow_predator`

Specialized grappler/swallow behavior.

- If it has a valid current grappled target of swallowable size, it uses `swallow`.
- Otherwise it falls back to normal melee behavior.

### `dragon`

Dragon-specific behavior layered on top of grounded melee behavior.

- Uses configured breath actions first when it can safely hit at least two conscious PCs without allies.
- Can use the one-time `opening_flight_landing` abstraction to land in a legal square and immediately use breath or melee.
- Adult Red can choose Fireball after breath when it can safely hit multiple PCs.
- Adult Red can use mixed Rend/Scorching Ray/Rend when tactically useful.
- Falls back to grounded melee once opening landing and high-value actions are not useful.

## Runtime Monster Features

### Weapon And Attack Modeling

- `WeaponProfile` stores attack bonus, range or reach, damage dice, damage type, split damage components, selectable damage types, and on-hit effects.
- Multiattack is data-driven through attack sequences: fixed sequences, repeated same-weapon attacks, or repeated choices across allowed weapons.
- Split damage components are used for attacks like slashing plus necrotic, piercing plus poison, or slashing plus elemental damage.
- Advantage-only damage components are supported for features such as Hobgoblin Archer poison on advantaged longbow hits.
- Selectable damage types are supported for effects such as Chromatic Bolt, choosing a type to exploit vulnerability or avoid resistance/immunity.

### Damage Defenses

Damage defenses are runtime-modeled per damage component.

- Immunity reduces that component to 0.
- Resistance halves that component once, rounded down.
- Vulnerability doubles that component once.
- Resistance and vulnerability cancel for the same component.
- Rage resistance and static resistance do not stack past one halving.
- Damage logs preserve pre-mitigation rolled components and report resisted or amplified damage separately.

### Condition And Creature Metadata

- `creature_tags` are internal identity tags used for targeting rules, such as `undead` and `dragon`.
- `condition_immunities` currently exist as metadata and are enforced only where specific runtime support exists.
- Movement modes such as `fly`, `burrow`, `climb`, and `swim` are metadata unless a specific abstraction exists.
- True vertical movement, burrow routing, climb routing, swim routing, and lair terrain rules are not generally modeled.

### On-Hit Riders

Current on-hit effect types include:

- `prone_on_hit`: knocks legal targets prone, respecting max target size.
- `grapple_on_hit`: applies a grapple with an escape DC and max target size.
- `grapple_and_restrain`: applies grapple plus restrained.
- `harry_target`: makes the next attack against that target gain advantage before the effect expires.
- `push_away_on_hit`: pushes a target straight away up to the configured number of squares, stopping at blocked, occupied, or out-of-bounds spaces.

### Reactions

- `opportunity_attack`: default reaction on most monsters.
- `parry`: auto-fires only when the +2 AC would turn an eligible melee hit into a miss.
- `redirect_attack`: used by Goblin Boss to swap with an eligible adjacent ally and redirect an incoming attack.

### Special Actions

- `swallow`: swallows a creature already grappled in the monster's mouth.
- `cold_breath` and `fire_breath`: cone save actions with recharge support.
- `scorching_ray`: shared spell definition used through monster spellcasting for Adult Red Dragon.
- `command`: shared spell definition modeled as a monster flee command for Adult Red Dragon.
- `fireball`: shared spell definition used as Adult Red Dragon's limited-use sphere save action.
- `freezing_burst`: Adult White legendary sphere action with cold damage and speed-zero on failed save.
- `frightful_presence`: Adult White legendary cone fear action.
- `mockery`: Satyr single-target WIS save psychic damage action.
- `natures_wrath`: player-side special action that appears in the shared special-action registry, not a monster action.

### Legendary And Dragon-Specific Features

- `legendary_resistance`: automatic failed-save override when uses remain.
- `legendary_action_uses`: resets at dragon turn start.
- `pounce`: legendary action movement plus one Rend if a legal attack can be made.
- `freezing_burst`: Adult White legendary action, one use between dragon turns.
- `frightful_presence`: Adult White legendary action applying frightened through Fear-like concentration.
- `fiery_rays`: Adult Red legendary action that resolves Scorching Ray.
- `commanding_presence`: Adult Red legendary action that applies the modeled Command flee behavior.

### Frightened And Commanded Runtime

- Frightened attackers have disadvantage against the fear source while the source is visible.
- A frightened creature that can see the source Dashes away and skips normal action behavior.
- Frightened creatures can save at turn end only when line of sight is broken.
- Fear concentration cleanup removes frightened effects from that source.
- Commanded creatures Dash away on their next turn, skip normal action behavior, and the effect expires at the end of that turn.
- Undead are immune to the modeled Command effect.

### Monster Traits

Runtime-modeled traits:

- `nimble_escape`: grants bonus-action Disengage.
- `aggressive`: grants bonus-action movement toward an enemy.
- `pack_tactics`: grants attack advantage when a conscious allied monster is adjacent to the target.
- `aura_of_authority`: grants attack and saving throw advantage to the captain and allied monsters within 10 feet.
- `bloodied_frenzy`: grants attack and saving throw advantage while Bloodied.
- `bloodied_fury`: grants attack advantage while Bloodied.
- `rampage`: one-use follow-up move plus melee attack after damaging an already-Bloodied target.
- `undead_fortitude`: lets eligible undead survive lethal non-radiant, non-critical damage on a CON save.
- `opening_flight_landing`: one-time landing abstraction from any legal fitting board position.
- `legendary_resistance`: enables failed-save override using resource pools.

Metadata-only or partial traits:

- `sunlight_sensitivity`: lighting is not modeled.
- `heart_of_the_dragon`: fear/paralysis support metadata only.
- `agile`: opportunity-attack immunity is not generally modeled.
- `jumper`: tactical jumping is not modeled.
- `magic_resistance`: metadata-only until magical save sources are consistently tagged.
- `charge`: movement-path charge riders are deferred.
- `ice_walk`: ice terrain rules are not modeled.
- `detect_magic`: non-combat spell metadata only.

## Benchmark And Test Surface

Most modeled monsters have generated test-only benchmark presets.

- Benchmark preset id format: `<variant_id>_benchmark`.
- Benchmark enemy count uses `max(1, min(15, round(100 / monster_hp)))`.
- Benchmark parties use `monster_benchmark_duo`.
- Benchmark presets stay out of active scenario lists unless explicitly promoted.
- Monster tests generally cover roster/content exactness, attack math, special mechanics, benchmark structure, and smoke behavior across DM behaviors.

## Important Modeling Boundaries

- The public encounter/scenario API is intentionally kept stable while monster content grows.
- Non-tactical traits are retained as metadata instead of being over-modeled.
- Spell-like monster abilities may reference shared spell definitions while still using monster-specific casting values.
- Active scenarios and benchmark presets are separate surfaces. Adding a monster to benchmarks does not make it active scenario content.
- Ranged variants are separate monster ids when inventory or behavior differs enough that one generic stat block would be misleading.
