# Standard Party-Validation Scenario Battery

This document describes the focused scenario battery used by `scripts/run_party_validation.py`.
The source of truth for the default list is `DEFAULT_SCENARIO_IDS` in that script.

Current default validation settings:

| Setting | Value |
| --- | --- |
| Player preset | `martial_mixed_party` |
| Party shape | level 5 Battle Master fighter, level 5 paladin, level 5 ranged Assassin rogue, level 5 Evoker wizard |
| Scenario count | 5 |
| Batch size | 300 encounters per scenario |
| Player behavior | `balanced` |
| Monster behavior | `combined` split across `kind`, `balanced`, and `evil` |
| Replay smoke | 2 encounters per scenario |

Current standard battery:

| Scenario | Primary Model |
| --- | --- |
| `reaction_bastion` | Elite defensive wall, parry reactions, multiattack pressure |
| `skyhunter_pincer` | Backline breach, large-body pressure, split-threat crossfire |
| `hobgoblin_command_screen` | Dense command screen, layered target priority, protected ranged captains |
| `berserker_overrun` | Many weak bodies plus hard melee hammers |
| `frostfall_courtyard` | Staged capstone with kobold opener and delayed dragon boss |

## `reaction_bastion`

Display name: Reaction Bastion

Description: Knights and veterans lock the center while a guard captain and scouts punish any attempted break.

Enemy roster:

| Count | Variant | Main Modeled Role |
| ---: | --- | --- |
| 1 | `knight` | AC 18 line holder with two-step multiattack and `parry` |
| 3 | `warrior_veteran` | Durable AC 17 line holder with two-step multiattack and `parry` |
| 1 | `guard_captain` | AC 18 captain with multiattack and `parry` |
| 1 | `bandit_archer` | Light ranged chip pressure |
| 1 | `scout` | Ranged multiattack support |

Starting layout:

| Unit | Variant | Position |
| --- | --- | --- |
| `E1` | `knight` | `(10, 6)` |
| `E2` | `warrior_veteran` | `(10, 10)` |
| `E3` | `warrior_veteran` | `(12, 6)` |
| `E4` | `warrior_veteran` | `(12, 10)` |
| `E5` | `guard_captain` | `(14, 8)` |
| `E6` | `bandit_archer` | `(15, 4)` |
| `E7` | `scout` | `(15, 12)` |

Terrain:

| Feature | Kind | Position | Footprint |
| --- | --- | --- | --- |
| `rock_1` | `rock` | `(5, 8)` | `1x1` |

Behaviors tested or modeled:

- Tests whether melee PCs stay disciplined into immediate high-AC blockers instead of overreaching.
- Exercises `parry` as a repeated defensive tax against melee and ranged hit thresholds.
- Exercises enemy multiattack from elite line holders and a captain.
- Keeps light ranged pressure in the back so the party still has to make target-priority decisions.
- Gives the rogue and wizard the fixed rock lane, but does not let cover solve the encounter by itself.

Scenario audit expectations:

| Expectation ID | What It Checks |
| --- | --- |
| `elite_line_holder_multiattack` | Multiattack from `knight`, `warrior_veteran`, or `guard_captain` |
| `parry_reaction` | `parry` reactions from reaction-capable elite humanoids |
| `scout_multiattack` | Scout multiattack appears in logged combat |

## `skyhunter_pincer`

Display name: Skyhunter Pincer

Description: A griffon dives onto the back line while centaurs and skirmishers stretch the party into a crossfire.

Enemy roster:

| Count | Variant | Main Modeled Role |
| ---: | --- | --- |
| 1 | `griffon` | Large flying opener with landing behavior, rend multiattack, and grapple rider |
| 2 | `centaur_trooper` | Large reach/ranged hybrid with two-step multiattack |
| 2 | `scout` | Ranged multiattack support |
| 1 | `guard_captain` | Durable captain with multiattack and `parry` |
| 1 | `knight` | High-AC line holder with multiattack and `parry` |

Starting layout:

| Unit | Variant | Position |
| --- | --- | --- |
| `E1` | `griffon` | `(14, 8)` |
| `E2` | `centaur_trooper` | `(10, 5)` |
| `E3` | `centaur_trooper` | `(10, 10)` |
| `E4` | `scout` | `(14, 4)` |
| `E5` | `scout` | `(14, 12)` |
| `E6` | `guard_captain` | `(12, 8)` |
| `E7` | `knight` | `(11, 8)` |

Terrain:

| Feature | Kind | Position | Footprint |
| --- | --- | --- | --- |
| `rock_1` | `rock` | `(5, 8)` | `1x1` |

Behaviors tested or modeled:

- Tests immediate backline peel decisions when the griffon creates turn-one pressure.
- Exercises large-footprint movement and landing behavior in a normal scenario, not just a monster benchmark.
- Forces the party to choose between the central captain/knight anchor and the flying breach.
- Exercises centaur hybrid pressure: reach melee when close, longbow when lanes stay open.
- Tests whether ranged PCs help peel the breach or continue deleting backline support.

Scenario audit expectations:

| Expectation ID | What It Checks |
| --- | --- |
| `griffon_opening_landing` | Griffon movement event using `landing` mode |
| `griffon_grapple` | Griffon `grapple_on_hit` rider appears |
| `centaur_multiattack` | Centaur multiattack appears |
| `scout_multiattack` | Scout multiattack appears |

## `hobgoblin_command_screen`

Display name: Hobgoblin Command Screen

Description: Hobgoblin captains direct a layered shell of disciplined warriors while archers punish any premature dive on the command layer.

Enemy roster:

| Count | Variant | Main Modeled Role |
| ---: | --- | --- |
| 9 | `hobgoblin_warrior` | AC 18 melee screen with `pack_tactics` |
| 2 | `hobgoblin_captain` | Command-layer threats with greatsword/longbow multiattack |
| 4 | `hobgoblin_archer` | AC 18 ranged pressure with longbow |

Starting layout:

| Unit | Variant | Position |
| --- | --- | --- |
| `E1` | `hobgoblin_warrior` | `(8, 4)` |
| `E2` | `hobgoblin_warrior` | `(8, 8)` |
| `E3` | `hobgoblin_warrior` | `(8, 12)` |
| `E4` | `hobgoblin_warrior` | `(9, 6)` |
| `E5` | `hobgoblin_warrior` | `(9, 10)` |
| `E6` | `hobgoblin_warrior` | `(10, 8)` |
| `E7` | `hobgoblin_warrior` | `(10, 5)` |
| `E8` | `hobgoblin_warrior` | `(10, 11)` |
| `E9` | `hobgoblin_warrior` | `(11, 6)` |
| `E10` | `hobgoblin_captain` | `(11, 10)` |
| `E11` | `hobgoblin_captain` | `(11, 8)` |
| `E12` | `hobgoblin_archer` | `(12, 4)` |
| `E13` | `hobgoblin_archer` | `(12, 7)` |
| `E14` | `hobgoblin_archer` | `(12, 10)` |
| `E15` | `hobgoblin_archer` | `(12, 13)` |

Terrain:

| Feature | Kind | Position | Footprint |
| --- | --- | --- | --- |
| `rock_1` | `rock` | `(5, 8)` | `1x1` |
| `command_low_wall_1` | `low_wall` | `(7, 6)` | `2x1` |
| `command_low_wall_2` | `low_wall` | `(7, 10)` | `2x1` |
| `command_boulder_1` | `boulder` | `(6, 4)` | `1x1` |

Behaviors tested or modeled:

- Tests whether melee PCs clear the screen instead of tunneling protected captains.
- Tests ranged target selection into a dense command shell where backline targets are important but not always immediately reachable.
- Exercises hobgoblin AC, `pack_tactics`, longsword pressure, and longbow pressure at scale.
- Exercises captain multiattack as protected midline/ranged pressure.
- Uses extra low walls and a boulder to make the approach more structured than the basic fixed-rock map.

Scenario audit expectations:

| Expectation ID | What It Checks |
| --- | --- |
| `hobgoblin_captain_multiattack` | Captain multiattack appears |
| `hobgoblin_captain_longbow_attack` | Captain longbow attack appears |
| `hobgoblin_longsword_attack` | Hobgoblin longsword attack appears |
| `hobgoblin_longbow_attack` | Hobgoblin longbow attack appears |

## `berserker_overrun`

Display name: Berserker Overrun

Description: A staggered goblin wave floods the lane while berserkers crash through any gap the party leaves open.

Enemy roster:

| Count | Variant | Main Modeled Role |
| ---: | --- | --- |
| 9 | `goblin_raider` | Weak melee bodies with `nimble_escape` |
| 2 | `hobgoblin_captain` | Durable multiattack/ranged pressure behind the wave |
| 2 | `berserker` | High-HP melee hammer with greataxe pressure and `bloodied_frenzy` |
| 2 | `hobgoblin_archer` | Longbow pressure from the rear corners |

Starting layout:

| Unit | Variant | Position |
| --- | --- | --- |
| `E1` | `goblin_raider` | `(8, 4)` |
| `E2` | `goblin_raider` | `(8, 6)` |
| `E3` | `goblin_raider` | `(8, 8)` |
| `E4` | `goblin_raider` | `(8, 10)` |
| `E5` | `goblin_raider` | `(8, 12)` |
| `E6` | `goblin_raider` | `(9, 5)` |
| `E7` | `goblin_raider` | `(9, 7)` |
| `E8` | `goblin_raider` | `(9, 9)` |
| `E9` | `goblin_raider` | `(9, 11)` |
| `E10` | `hobgoblin_captain` | `(11, 5)` |
| `E11` | `hobgoblin_captain` | `(11, 10)` |
| `E12` | `berserker` | `(10, 7)` |
| `E13` | `berserker` | `(10, 9)` |
| `E14` | `hobgoblin_archer` | `(14, 4)` |
| `E15` | `hobgoblin_archer` | `(14, 12)` |

Terrain:

| Feature | Kind | Position | Footprint |
| --- | --- | --- | --- |
| `rock_1` | `rock` | `(5, 8)` | `1x1` |

Behaviors tested or modeled:

- Tests whether the party can spend actions efficiently into many weak enemies without losing tempo to overkill.
- Tests wizard area-control and area-damage value against a staggered wave, without making one perfect cone solve the whole fight.
- Tests frontliner triage: clear goblins, brace for berserkers, or push toward captains.
- Exercises the interaction between weak-body congestion and stronger melee hammers.
- Keeps longbow pressure live so the party cannot safely ignore the backline.

Scenario audit expectations:

| Expectation ID | What It Checks |
| --- | --- |
| `berserker_greataxe_attack` | Berserker greataxe attack appears |
| `goblin_melee_engagement` | Goblin melee scimitar engagement appears |
| `hobgoblin_captain_multiattack` | Captain multiattack appears |
| `hobgoblin_captain_longbow_attack` | Captain longbow attack appears |
| `hobgoblin_longbow_attack` | Hobgoblin longbow attack appears |

## `frostfall_courtyard`

Display name: Frostfall Courtyard

Description: Kobolds draw the party into a frozen ruined courtyard before the white dragon boss descends through the storm.

Enemy roster:

| Count | Variant | Main Modeled Role |
| ---: | --- | --- |
| 10 | `kobold_warrior` | Low-HP melee swarm bodies with `pack_tactics` |
| 2 | `kobold_scale_sorcerer` | Chromatic-bolt multiattack support |
| 4 | `kobold_dragonshield` | Tougher kobold flankers with spear multiattack and `heart_of_the_dragon` |
| 1 delayed | `young_white_dragon_boss` | Huge dragon boss arriving on round 3 |

Opening layout:

| Unit | Variant | Position |
| --- | --- | --- |
| `E1` | `kobold_warrior` | `(14, 7)` |
| `E2` | `kobold_warrior` | `(14, 8)` |
| `E3` | `kobold_warrior` | `(14, 9)` |
| `E4` | `kobold_warrior` | `(14, 10)` |
| `E5` | `kobold_warrior` | `(14, 11)` |
| `E6` | `kobold_warrior` | `(14, 12)` |
| `E7` | `kobold_warrior` | `(15, 7)` |
| `E8` | `kobold_warrior` | `(15, 8)` |
| `E9` | `kobold_scale_sorcerer` | `(15, 9)` |
| `E10` | `kobold_scale_sorcerer` | `(15, 10)` |
| `E11` | `kobold_warrior` | `(15, 11)` |
| `E12` | `kobold_warrior` | `(15, 12)` |
| `E13` | `kobold_dragonshield` | `(5, 5)` |
| `E14` | `kobold_dragonshield` | `(5, 12)` |
| `E15` | `kobold_dragonshield` | `(14, 6)` |
| `E16` | `kobold_dragonshield` | `(14, 13)` |

Delayed boss:

| Unit | Variant | Arrival Round | Preferred Position | Notes |
| --- | --- | ---: | --- | --- |
| `E17` | `young_white_dragon_boss` | 3 | `(9, 8)` | Uses delayed arrival with `opening_landing_uses` set to `0` |

Fixed player placements:

| Unit | Party Member | Position |
| --- | --- | --- |
| `F1` | Fighter | `(3, 7)` |
| `F2` | Paladin | `(3, 12)` |
| `F3` | Ranged rogue | `(1, 5)` |
| `F4` | Wizard | `(1, 13)` |

Terrain:

| Feature | Kind | Position | Footprint |
| --- | --- | --- | --- |
| `rock_1` | `rock` | `(5, 8)` | `1x1` |
| `courtyard_column_1` | `column` | `(3, 5)` | `1x1` |
| `courtyard_column_2` | `column` | `(3, 11)` | `1x1` |
| `courtyard_column_3` | `column` | `(5, 6)` | `1x1` |
| `courtyard_column_4` | `column` | `(5, 10)` | `1x1` |
| `courtyard_low_wall_1` | `low_wall` | `(7, 5)` | `2x1` |
| `courtyard_low_wall_2` | `low_wall` | `(7, 11)` | `2x1` |

Behaviors tested or modeled:

- Tests a staged encounter flow: a kobold opener first, then a delayed boss arrival on round 3.
- Tests whether the party spends early resources fast enough without being depleted when the dragon lands.
- Tests wizard area damage into a distant visible kobold cluster.
- Tests frontliner protection and flanking behavior against dragonshields near the player side.
- Exercises the dragon boss package: huge footprint, cold breath, legendary resistance, `pounce`, `icy_retreat`, and enhanced rend pressure.
- Uses courtyard columns and low walls to prevent the dragon from simply landing on top of the party and to create meaningful line/landing geometry.

Scenario audit expectations:

| Expectation ID | What It Checks |
| --- | --- |
| none | This capstone currently relies on preset construction, delayed-arrival tests, and party-validation results rather than scenario-audit signatures |

