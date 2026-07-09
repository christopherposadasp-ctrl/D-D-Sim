# Player Character Classes Modeled

This document summarizes the player character class content currently modeled in
the Python backend. The source of truth is the backend content registry:

- `backend/content/class_definitions.py`
- `backend/content/class_progressions.py`
- `backend/content/feature_definitions.py`
- `backend/content/player_loadouts.py`
- `backend/content/spell_definitions.py`

The default player preset is `martial_mixed_party`, currently:

| Slot | Loadout | Role |
|---|---|---|
| F1 | `fighter_level5_sample_build` | Battle Master great-weapon striker |
| F2 | `paladin_level5_sample_build` | Oath of the Ancients support tank |
| F3 | `rogue_ranged_level5_assassin_sample_build` | ranged Assassin striker |
| F4 | `wizard_level5_evoker_sample_build` | Evoker artillery caster |

## Support Matrix

| Class | Supported Levels | Main Modeled Path | Notes |
|---|---:|---|---|
| Fighter | 1-5 | Battle Master great-weapon striker | Greatsword primary, Great Weapon Master, Extra Attack, Tactical Shift |
| Rogue | 1-5 ranged, 1-2 melee | ranged Assassin, melee skirmisher | Shortbow Vex for ranged Rogues, Rapier Vex for melee Rogues |
| Barbarian | 1-2 | melee berserker | Rage, Reckless Attack, Danger Sense |
| Monk | 1-2 | unarmed martial artist | Martial Arts, Focus Points, bonus movement/defense options |
| Paladin | 1-5 | Oath of the Ancients support tank | plate and shield, Lay on Hands, Bless, Smite, Nature's Wrath, Sentinel, Extra Attack |
| Wizard | 1-5 | Evoker artillery caster | Magic Missile, Shield, Burning Hands, Shatter, Scorching Ray, Fireball, Haste, Counterspell |

## Fighter

The Fighter is modeled through level 5 as a Battle Master great-weapon striker.
The sample path uses a greatsword as the primary weapon, flail as the secondary
melee weapon, and javelins as a fallback ranged weapon.

### Fighter Sample Progression

| Level | Sample Stats | Features and Resources | Live Behavior |
|---:|---|---|---|
| 1 | HP 13, AC 16, STR +3 | `second_wind`, 2 Second Wind uses | self-heal bonus action; greatsword/flail/javelin loadout |
| 2 | HP 21, AC 16, STR +3 | +`action_surge`, 1 Action Surge use | extra action once per encounter |
| 3 | HP 29, AC 18, STR +3 | +`combat_superiority`, `student_of_war`, 4 d8 Superiority Dice | Battle Master maneuvers: Precision Attack, Trip Attack, Riposte |
| 4 | HP 37, AC 18, STR +4 | +`great_weapon_master` | heavy weapon damage bonus and Hew bonus-action attack |
| 5 | HP 45, AC 18, STR +4 | +`extra_attack`, `tactical_shift`, 3 Second Wind uses | two attacks per Attack action; Second Wind can add Tactical Shift movement |

### Fighter Feature Notes

- `great_weapon_fighting`: the current simulator model upgrades two-handed melee
  weapon damage dice that roll 1 or 2 to 3.
- `savage_attacker`: once per turn, weapon damage can be rolled twice and the
  better result kept.
- `weapon_mastery_graze`: missed mastered attacks can still deal Graze damage.
- `weapon_mastery_sap`: hits can impose disadvantage on the target's next attack.
- `weapon_mastery_slow`: hits can reduce the target's speed.
- `combat_superiority`: grants four d8 Superiority Dice and the fixed maneuver
  package `precision_attack`, `trip_attack`, and `riposte`.
- `great_weapon_master`: adds passive heavy-weapon damage on eligible Attack
  action hits and enables Hew bonus-action attacks on eligible kills/crits.
- `tactical_shift`: when Second Wind is used, the Fighter can reposition up to
  half speed without provoking opportunity attacks.

## Rogue

Rogue support has two player paths:

- ranged Rogue through level 5, ending as a ranged Assassin
- melee Rogue through level 2, ending as a Cunning Action melee skirmisher

### Rogue Sample Progression

| Level | Sample Stats | Features and Resources | Live Behavior |
|---:|---|---|---|
| 1 | ranged HP 10 AC 14, melee HP 10 AC 14, DEX +3 | `sneak_attack`, `expertise_stealth`, `weapon_mastery`, Sneak Attack 1d6 | ranged shortbow or melee rapier Sneak Attack package |
| 2 | ranged HP 18 AC 14, melee HP 18 AC 14 | +`cunning_action` | bonus Dash, Disengage, and Hide |
| 3 | ranged Assassin HP 26 AC 15 | +`steady_aim`, `assassinate`, `assassin_tools`, Sneak Attack 2d6 | ranged Assassin with Studded Leather, first-round Assassin pressure, Steady Aim |
| 4 | ranged Assassin HP 34 AC 16, DEX +4 | +`sharpshooter`, Sneak Attack 2d6 | ranged reliability through cover, long range, and adjacent pressure |
| 5 | ranged Assassin HP 42 AC 16, DEX +4 | +`cunning_strike`, `uncanny_dodge`, Sneak Attack 3d6 | Uncanny Dodge reaction; Cunning Strike rules exist but are not normal AI preferences |

### Rogue Feature Notes

- `sneak_attack`: once per turn on qualifying finesse or ranged hits.
- `expertise_stealth`: Stealth uses doubled proficiency.
- `weapon_mastery`: Rogue loadouts now model Vex mastery for the relevant primary
  weapon.
- Ranged Rogue shortbows use `mastery="vex"` from level 1 through level 5.
- Melee Rogue rapiers use `mastery="vex"` at levels 1 and 2.
- `cunning_action`: bonus Dash, Disengage, and Hide.
- `steady_aim`: bonus-action advantage when the Rogue does not move.
- `assassinate`: initiative advantage and first-round Assassin damage/advantage
  support.
- `assassin_tools`: metadata-only support for Disguise Kit and Poisoner's Kit.
- `sharpshooter`: modeled as a Dex half-feat and ranged reliability feature, not
  the old -5/+10 damage option.
- `cunning_strike`: Poison, Trip, and Withdraw resolver support exists, but the
  normal Rogue AI does not select Cunning Strike yet.
- `uncanny_dodge`: automatic reaction that halves qualifying incoming attack-roll
  damage using the shared Rogue threshold policy.

## Barbarian

The Barbarian is modeled through level 2 as a melee berserker. It remains
catalog-visible and available in its own presets, but it is no longer in the
default mixed party.

### Barbarian Sample Progression

| Level | Sample Stats | Features and Resources | Live Behavior |
|---:|---|---|---|
| 1 | HP 15, unarmored defense, STR +3, CON +3 | `rage`, `unarmored_defense`, 2 Rage uses, 4 handaxes | Rage temp HP, Rage damage, weapon-damage resistance, greataxe/handaxe package |
| 2 | HP 25 | +`reckless_attack`, `danger_sense` | Reckless Attack and Dexterity-save advantage while conscious |

### Barbarian Feature Notes

- `rage`: bonus-action combat mode with temp HP, melee damage bonus, and
  weapon-damage resistance while maintained.
- `unarmored_defense`: AC is modeled directly from the Barbarian's unarmored
  formula.
- `reckless_attack`: can grant advantage on Strength attacks, with incoming
  advantage against the Barbarian until the next turn.
- `danger_sense`: advantage on Dexterity saving throws while conscious.
- The sample greataxe uses Cleave mastery, and handaxes use Vex mastery.

## Monk

The Monk is modeled through level 2 as an unarmored martial artist. It remains
catalog-visible and available in its own presets, but it is not part of the
default mixed party.

### Monk Sample Progression

| Level | Sample Stats | Features and Resources | Live Behavior |
|---:|---|---|---|
| 1 | HP 10, unarmored defense, speed 30, DEX +3, WIS +2 | `martial_arts`, `unarmored_defense`, martial arts die d6 | Dexterity martial attacks and bonus unarmed strike |
| 2 | HP 18, speed 40 | +`monks_focus`, `unarmored_movement`, `uncanny_metabolism`, 2 Focus Points, 1 Uncanny Metabolism use | Focus-powered bonus actions, speed increase, recovery/heal support |

### Monk Feature Notes

- `martial_arts`: supports Monk weapon/unarmed combat and the bonus unarmed
  strike flow.
- `unarmored_defense`: AC is modeled from the Monk unarmored formula.
- `monks_focus`: Focus Points support Monk bonus-action options such as Flurry,
  Patient Defense, Step of the Wind, bonus Dash, and bonus Disengage.
- `unarmored_movement`: represented in the level 2 Monk's increased speed.
- `uncanny_metabolism`: once-per-encounter recovery/healing support.

## Paladin

The Paladin is modeled through level 5 as a plate-and-shield Oath of the
Ancients support tank. The sample uses a longsword with Sap mastery and javelins
with Slow mastery.

### Paladin Sample Progression

| Level | Sample Stats | Features and Resources | Live Behavior |
|---:|---|---|---|
| 1 | HP 13, AC 20, STR +3, CHA +2 | `lay_on_hands`, `spellcasting`, `weapon_mastery`, 5 Lay on Hands points, 2 level 1 slots | Bless, Cure Wounds, Lay on Hands, longsword/javelin |
| 2 | HP 22, AC 21 | +`fighting_style_defense`, `paladins_smite`, 10 Lay on Hands points | Defense style AC, Divine Smite after melee hits |
| 3 | HP 31, AC 21 | +`channel_divinity`, `oath_of_the_ancients`, `natures_wrath`, `oath_spells_ancients`, 15 Lay on Hands, 3 level 1 slots, 2 Channel Divinity uses | Nature's Wrath restraint control; Ancients identity |
| 4 | HP 40, AC 21, STR +4 | +`sentinel`, 20 Lay on Hands | Sentinel Guardian reaction and Halt on opportunity hits |
| 5 | HP 49, AC 21, STR +4 | +`extra_attack`, `faithful_steed`, 25 Lay on Hands, 4 level 1 slots, 2 level 2 slots | two attacks per Attack action; Aid support; level 2 Bless option |

### Paladin Feature Notes

- `lay_on_hands`: bonus-action healing pool. The current default policy is
  downed targets to 30%, living allies to 55%, self to 65%, with low-remainder
  spend behavior at 20% of the pool.
- `spellcasting`: the combat spell package is Bless, Cure Wounds, and Aid at
  level 5.
- `weapon_mastery`: longsword uses Sap and javelin uses Slow.
- `fighting_style_defense`: represented directly in the sample AC.
- `paladins_smite`: Divine Smite spends spell slots after qualifying melee hits.
- `channel_divinity`: fuels Oath actions.
- `natures_wrath`: Channel Divinity action that can restrain nearby enemies that
  fail Strength saves.
- `sentinel`: Guardian reaction attacks and Halt speed reduction on opportunity
  attack hits.
- `extra_attack`: two attacks per Attack action at level 5.
- `faithful_steed`: metadata-only in the current player path; mounted combat is
  not modeled.
- Smart precombat Aid support exists for Paladin 5: the Paladin can spend a
  level 2 slot before initiative to apply Aid to Paladin, Fighter, and Wizard.

## Wizard

The Wizard is modeled through level 5 as an Evoker artillery caster. The sample
uses Fire Bolt and Shocking Grasp as live cantrips, with a growing prepared spell
package through level 5.

### Wizard Sample Progression

| Level | Sample Stats | Features and Resources | Live Behavior |
|---:|---|---|---|
| 1 | HP 8, AC 12, INT +3, DEX +2 | `spellcasting`, `ritual_adept`, `arcane_recovery`, 2 level 1 slots, counts 3/6/4 | Fire Bolt, Shocking Grasp, Magic Missile, Shield, Burning Hands, Mage Armor metadata/manual support |
| 2 | HP 14, AC 12, INT +3 | +`scholar`, 3 level 1 slots, counts 3/8/5 | Scholar metadata; same live spell package |
| 3 | HP 20, AC 12, INT +3 | +`evoker`, `evocation_savant`, `potent_cantrip`, 4 level 1 slots, 2 level 2 slots, counts 3/12/6 | Potent Cantrip, Scorching Ray, Shatter |
| 4 | HP 26, AC 12, INT +4 | +`ability_score_improvement`, 4 level 1 slots, 3 level 2 slots, counts 4/14/8 | higher spell attack and save DC from INT ASI |
| 5 | HP 32, AC 12, INT +4 | +`memorize_spell`, 4 level 1 slots, 3 level 2 slots, 2 level 3 slots, counts 4/17/9 | Fireball, Haste, Counterspell access; cantrips scale to two damage dice |

Wizard count notation is `cantrips_known/spellbook_spells/prepared_spells`.

### Wizard Feature Notes

- `spellcasting`: uses Intelligence for spell attacks and spell save DCs.
- `ritual_adept`, `arcane_recovery`, `scholar`, `evocation_savant`, and
  `memorize_spell` are mostly metadata/future-support features in the current
  combat path.
- `evoker`: fixed subclass identity from level 3 onward.
- `potent_cantrip`: missed damaging cantrips, or successful saves against
  damaging save cantrips, deal half rolled cantrip damage rounded down, minimum
  1.
- Level 5 cantrip scaling is modeled: Fire Bolt rolls 2d10 and Shocking Grasp
  rolls 2d8 for the level 5 Wizard.
- Smart precombat Mage Armor support exists: when useful, the smart Wizard can
  spend a level 1 slot before initiative to raise AC to `13 + Dex`.

### Wizard Spell Notes

- `fire_bolt`: default ranged spell attack cantrip.
- `shocking_grasp`: close-range escape spell; on a hit it can suppress reactions.
- `magic_missile`: guaranteed-force-damage spell with level 1 and level 2 use.
- `shield`: reaction spell used when it can change the result of an incoming hit.
- `burning_hands`: close cone save spell.
- `mage_armor`: manual/precombat support; not a normal in-combat offensive choice.
- `scorching_ray`: level 2 multi-ray spell; smart targeting can split rays.
- `shatter`: level 2 ally-safe cluster spell.
- `fireball`: level 3 ally-safe 3+ enemy blast in the Wizard AI ladder.
- `haste`: level 3 concentration buff support; smart Wizard can use it on the
  Fighter after Fireball is unavailable and when not already concentrating.
- `counterspell`: level 3 reaction spell support.

## Metadata-Only or Deferred Player Features

Some content is represented for class identity, catalog accuracy, or future
rules work but is not fully active in normal AI play:

| Class | Feature or Spell | Current Status |
|---|---|---|
| Fighter | `student_of_war` | metadata-only |
| Rogue | `assassin_tools` | metadata-only; no disguise/poison inventory system |
| Rogue | `cunning_strike` | resolver support exists, but normal AI does not select it |
| Paladin | `oath_spells_ancients` | metadata-only; no extra live oath spell added by this feature |
| Paladin | `faithful_steed` | metadata-only; no mounted combat |
| Wizard | `ritual_adept`, `arcane_recovery`, `scholar`, `evocation_savant`, `memorize_spell` | metadata/future-support in normal combat |

## Presets

Each modeled class path has catalog-visible trio presets where applicable:

- Fighter trios through `fighter_level5_sample_trio`
- Rogue ranged trios through `rogue_level5_ranged_assassin_trio`
- Rogue melee trios through `rogue_level2_melee_trio`
- Barbarian trios through `barbarian_level2_sample_trio`
- Monk trios through `monk_level2_sample_trio`
- Paladin trios through `paladin_level5_sample_trio`
- Wizard trios through `wizard_level5_evoker_sample_trio`

The mixed-party integration preset is `martial_mixed_party`.
