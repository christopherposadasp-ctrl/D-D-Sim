# Modeled Spells

This document summarizes spells that have live combat behavior in the simulator. Spell metadata lives in
`backend/content/spell_definitions.py`; most runtime spell mechanics live in
`backend/engine/rules/spell_resolvers.py`. Some reactions, area dispatch, monster spellcasting, and attack riders
also use hooks in `backend/engine/combat/engine.py` or `backend/engine/rules/combat_rules.py`.

`detect_magic` is intentionally excluded because it is metadata-only in combat.

## General Modeling Notes

- Spell definitions use `targeting_mode` to route into runtime behavior.
- Leveled spells spend spell slots only after basic legality checks pass. Cantrips spend no slots.
- Most spell events include `spellId`, `spellLevel`, resource remaining fields, and key effect fields in
  `resolved_totals`.
- Concentration effects use temporary effects plus concentration cleanup in the combat rules.
- Duration cleanup exists for several combat effects, but long-duration spells can effectively persist for the
  encounter when no explicit cleanup is modeled.
- Public encounter action payloads remain stable. Most action spell casts use `{"kind": "cast_spell", "spell_id": ..., "target_id": ...}`.

## Cantrips

| Spell | Model | Important details and limitations |
| --- | --- | --- |
| `fire_bolt` | Ranged spell attack, fire damage. | Uses normal attack roll, range, cover, advantage/disadvantage, resistance/vulnerability, and damage application. Evoker Potent Cantrip can apply minimum damage on miss where supported. |
| `shocking_grasp` | Melee spell attack, lightning damage, no-reactions rider. | On hit, applies a timed `no_reactions` effect that prevents opportunity attacks until the target turn-start cleanup. Potent Cantrip miss damage does not apply the rider. |
| `ray_of_frost` | Ranged spell attack, cold damage, speed penalty. | On hit, applies a timed slow effect and recalculates effective Speed. Misses do not apply the rider. |
| `chill_touch` | Ranged spell attack, necrotic damage, healing block. | On hit, applies a timed healing-block effect. The model blocks HP restoration through supported healing helpers; broader regeneration-style mechanics are limited to what the engine models. |
| `poison_spray` | Single-target Constitution save, poison damage. | Failed save deals damage; successful save deals no damage. Poison immunity/resistance follows normal damage application where present. |
| `acid_splash` | One or two target Dexterity save, acid damage. | Supports a second target only when it is within the configured target cluster. Successful saves take no damage. |

## Level 1

| Spell | Model | Important details and limitations |
| --- | --- | --- |
| `magic_missile` | Auto-hit force darts. | Can target one or multiple creatures, supports upcasting for extra darts, and spends the chosen slot level. Shield can fully block it as a reaction. |
| `chromatic_orb` | Ranged spell attack with selectable damage type. | Uses a selectable elemental damage type and can prefer vulnerable damage where the decision logic supports that. Misses still spend the slot. |
| `ray_of_sickness` | Ranged spell attack plus poison rider save. | On hit, damage resolves first, then a separate Constitution `saving_throw` event may apply a timed poisoned effect. No save is rolled on miss, poison immunity, dead target, or already poisoned target. |
| `shield` | Automatic defensive reaction. | Can turn a stoppable hit into a miss and blocks Magic Missile. Smart behavior skips natural 20s and unstoppably high hits; dumb behavior can overuse it. Effect lasts until the next turn-start cleanup. |
| `burning_hands` | Self-origin cone Dexterity save. | Uses one shared damage roll across targets, half damage on successful saves, can hit allies, and supports upcasting. Cone targeting and legality are engine-routed. |
| `bless` | Concentration ally buff. | Adds 1d4 to supported attack rolls and saving throws. Supports higher-level target counts where modeled. Ends through concentration cleanup. |
| `cure_wounds` | Touch healing. | Heals 2d8 plus spellcasting modifier and spends a level 1 slot. Healing is blocked by supported healing-block effects. |
| `mage_armor` | Self AC floor. | Sets base AC to `13 + Dex modifier` only if better. The engine has no worn-armor field, so it cannot reject armored targets; it applies only when beneficial. Long duration is metadata/effect persistence for the encounter. |
| `false_life` | Self temporary HP. | Grants `2d4 + 4` temporary HP and does not replace a higher existing temporary HP value. |
| `longstrider` | Touch ally speed buff. | Grants a non-stacking 10-foot speed bonus and recalculates effective Speed. Duration is long, non-concentration encounter persistence. |
| `shield_of_faith` | Bonus-action concentration AC buff. | Grants +2 AC to a living ally/self within range. Ends through concentration cleanup and affects incoming attack target AC. |
| `heroism` | Touch concentration temp HP and frightened support. | Applies a Heroism effect, clears existing frightened where supported, grants start-of-turn temporary HP, and models frightened immunity through the effect. Ends through concentration cleanup. |
| `divine_favor` | Bonus-action concentration weapon rider. | Adds 1d4 radiant damage to the caster's supported weapon hits. Misses do not apply the rider. Ends through concentration cleanup. |
| `command` | Monster spellcasting Wisdom save command. | Implemented for monster spellcasting special actions, including multi-target monster Command. Failed saves apply the supported command effect. Undead immunity is modeled. Normal player `cast_spell` Command is not the primary path. |
| `divine_smite` | Paladin melee-hit spell slot rider. | Modeled as an attack rider rather than a normal `cast_spell` action. It spends a slot on eligible melee hits, adds radiant d8s, scales by slot level, adds an extra die against fiends/undead, and does not trigger on ranged/opportunity cases that are explicitly excluded. |

## Level 2

| Spell | Model | Important details and limitations |
| --- | --- | --- |
| `aid` | Multi-ally HP increase. | Increases current and maximum HP for up to three allies, spends a level 2 slot, and is non-concentration. Long duration persists for the encounter. |
| `shatter` | Area Constitution save thunder damage. | Targets a cluster, rolls thunder damage, applies half damage on successful saves, spends a level 2 slot, and rejects intentional ally targeting in the player spell path. |
| `scorching_ray` | Three ranged spell attacks. | Spends one level 2 slot, resolves separate rays, can split rays across targets, and stops remaining rays when appropriate after a target drops. Also reused by monster spellcasting. |

## Level 3

| Spell | Model | Important details and limitations |
| --- | --- | --- |
| `fireball` | Point-origin Dexterity save fire sphere. | Spends a level 3 slot, targets all legal units in the sphere, excludes the caster where configured, uses one damage roll, and applies half damage on successful saves. Also reused by monster limited-use spellcasting. |
| `counterspell` | Automatic hostile spell interruption reaction. | Can interrupt hostile leveled spell casts within 60 ft when the counterspeller is conscious, has line of sight, has a reaction, knows/prepared Counterspell, and has a level 3 slot. Auto-succeeds against spells level 3 or lower; higher-level check support exists. Does not auto-counter cantrips, recursive Counterspell chains, Shield reactions, breath weapons, or legendary actions. Countered spells still spend their triggering resource. |
| `haste` | Concentration ally/self combat buff. | Grants +2 AC, doubled effective Speed, Dexterity save advantage, and one restricted hasted action per turn. Supported hasted actions are attack, dash, disengage, hide, and use object; use object currently emits an unsupported skip. When Haste ends, the target gets lethargy that skips actions and movement until its next turn ends. |

