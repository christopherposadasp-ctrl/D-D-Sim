# DM Styles and Player Behaviors

This document explains the simulator settings that appear as **Player Behavior**
and **DM Style** in the UI. They sound similar, but they control different sides
of the encounter.

## Short version

| Setting group | What it controls | Available settings |
| --- | --- | --- |
| Player Behavior | How the party chooses targets, movement, spells, and resource use | Smart Players, Dumb Players, Balanced |
| DM Style | How enemies choose targets and pressure the party | Kind DM, Balanced DM, Evil DM |

**Player Behavior** changes the party AI.

**DM Style** changes the enemy targeting policy.

**Balanced** does not mean the same thing in both menus. For players, Balanced
is a batch-mode mix of Smart and Dumb runs. For DMs, Balanced is one middle
targeting policy between Kind and Evil.

## Source definitions

The shared TypeScript model defines the public options:

```ts
PlayerBehavior = 'smart' | 'dumb' | 'balanced'
ResolvedPlayerBehavior = 'smart' | 'dumb'
MonsterBehavior = 'kind' | 'balanced' | 'evil'
MonsterBehaviorSelection = MonsterBehavior | 'combined'
```

The Python engine uses only resolved player behaviors during combat:

- `smart`
- `dumb`

`balanced` is a request mode. It is resolved before a run starts.

The DM side uses three true combat behaviors:

- `kind`
- `balanced`
- `evil`

`combined` is a batch-only convenience option, not a fourth DM style.

## Player Behavior

Player Behavior determines how the party side makes decisions. It affects target
priority, movement, spell use, and some resource timing.

### Smart Players

Smart Players use the highest-tactics party logic.

Smart target selection considers:

- Whether a target can probably be killed this turn.
- Whether a target can threaten allies now or next turn.
- Whether a target is a high-value backline target, such as a caster, healer,
  controller, grappler, or other pressure unit.
- Whether the target is already damaged.
- Hit probability and expected damage.
- Distance and positioning.

Smart movement tries to turn those priorities into legal attacks. For melee
characters, the engine evaluates reachable melee squares, target priority, flank
creation, ally adjacency, and path position. For ranged characters and casters,
the engine favors clean attack lines and useful spell targeting.

Examples of Smart behavior in the current engine:

- Fighters use a stricter Second Wind threshold: a smart fighter waits until
  roughly 40 percent HP or lower, instead of using it at half HP.
- Smart target sorting prefers killable, dangerous, high-value, or already
  damaged enemies rather than simply attacking the closest unit.
- Smart front-line characters avoid bad ranged attacks when a better melee plan
  or advance is available.
- Smart spell logic can split Magic Missile darts or Scorching Ray rays across
  targets when doing so can secure kills.
- Smart wizard logic can choose Haste for a fighter when the setup is valid.
- Smart movement can support later flanking or body-blocking options when those
  feature flags are enabled.

Smart Players are useful when the goal is to estimate what a capable party could
do with the available rules and resources.

### Dumb Players

Dumb Players use a simpler party policy.

The key difference is target priority. Dumb target sorting is primarily:

1. Closest target.
2. Stable unit-id tie break.

Dumb Players still follow legal combat rules. They can move, attack, cast, use
class features, and spend resources if the general decision tree allows it. The
word "dumb" does not mean illegal or random. It means less tactical.

Examples of Dumb behavior in the current engine:

- Dumb target selection does not use the full smart priority stack.
- Dumb spell targeting tends to concentrate repeated spell attacks on the
  primary target instead of distributing hits for optimized kill probability.
- Dumb fighters use Second Wind at a broader half-HP threshold.
- Dumb players do not use smart-only movement support for flanking or body
  blocking.

Dumb Players are useful as a lower-skill or baseline party assumption.

### Balanced Players

Balanced Players is not a third combat AI. It is a request mode that resolves to
Smart or Dumb.

In batch runs, Balanced alternates by run index:

- Even run index: Smart.
- Odd run index: Dumb.

The batch summary tracks both sides:

- Smart run count.
- Dumb run count.
- Smart player win rate.
- Dumb player win rate.
- Combined overall player win rate.

For a single encounter, the same resolver receives run index `0`, so a requested
Balanced player behavior resolves to Smart for that one run. The batch view is
where Balanced is most meaningful because it includes both Smart and Dumb runs.

Balanced Players are useful when the goal is to compare a scenario against a
mixed player-skill assumption.

## DM Style

DM Style determines how enemies choose targets. It does not replace each
monster's own AI profile. A monster can still be a melee brute, line holder,
ranged skirmisher, pack hunter, dragon, swallow predator, or grappling brute.
DM Style changes which party member that monster tries to pressure.

All three DM styles generally deprioritize hidden targets before applying their
style-specific priority.

### Kind DM

Kind DM is the least punishing enemy targeting policy.

Kind target sorting prefers:

1. Non-hidden targets.
2. Higher HP ratio.
3. Closer targets.
4. Higher current HP.
5. Stable unit-id tie break.

In practical terms, Kind DM tends to pressure healthier or front-line characters
instead of focusing weak, downed, healer, or caster targets. It avoids the
downed-target finishing behavior used by Evil DM.

Kind DM is useful when the encounter should model a less ruthless enemy side or
when you want to give the party more survivability.

### Balanced DM

Balanced DM is the middle enemy targeting policy.

Balanced target sorting prefers:

1. Non-hidden targets.
2. Lower current HP.
3. Closer targets.
4. Stable unit-id tie break.

For melee choices, Balanced DM can also prefer attacks that create flanking,
then lower-HP targets, then shorter movement.

Balanced DM pressures wounded conscious characters, but it does not use the Evil
DM downed-target finishing policy. This makes it harsher than Kind DM but less
punishing than Evil DM.

Balanced DM is the default single-run DM behavior.

### Evil DM

Evil DM is the most punishing enemy targeting policy.

Evil target sorting for conscious targets prefers:

1. Non-hidden targets.
2. Healers.
3. Casters.
4. Lower HP ratio.
5. Closer targets.
6. Stable unit-id tie break.

For melee choices, Evil DM also weighs:

- Healer priority.
- Caster priority.
- Low HP ratio.
- Flank creation.
- Shorter movement.

Evil DM has extra hostile behavior for downed party members:

- If an adjacent downed fighter is available, melee enemies can attack that
  target.
- If no better conscious target is available, evil melee enemies can pursue
  downed targets.
- Evil ranged enemies can attack downed targets when they have a legal shot.

Evil monsters may also risk opportunity attacks to pressure a healer or caster,
but not just to finish a downed target.

Evil DM is useful for stress testing party durability, evaluating rescue logic,
or demonstrating worst-case enemy focus.

## Combined Batch

The UI also exposes **Combined Batch** under DM Style. This is not a fourth DM
style.

Combined Batch expands one batch request into all three DM styles:

1. Kind DM.
2. Balanced DM.
3. Evil DM.

If the batch size is `N`, Combined Batch runs `N` simulations for each DM style,
for `3N` total runs. The summary includes per-style combination summaries and an
overall aggregate.

Combined Batch pairs naturally with Balanced Players:

- Balanced Players alternates Smart and Dumb player behavior inside each style.
- Combined Batch repeats the full batch across Kind, Balanced, and Evil DM
  styles.

Together, they answer: "How does this scenario perform across player skill
assumptions and DM pressure assumptions?"

## What Balanced means on each side

| Menu | Balanced means | Combat behavior used |
| --- | --- | --- |
| Player Behavior | Alternate Smart and Dumb in batch mode | Resolves to Smart or Dumb before each run |
| DM Style | One middle enemy targeting policy | Stays Balanced for the run |

This is the most important distinction:

- **Balanced Players** is a blend of two player policies.
- **Balanced DM** is one enemy policy.

## Defaults

The current engine defaults are:

| Context | Player default | DM default |
| --- | --- | --- |
| Single encounter | Smart Players | Balanced DM |
| Batch encounter | Balanced Players | Combined Batch |

The batch defaults are designed to give comparison data without requiring the
user to manually run every combination.

## Practical interpretation

Use **Smart Players + Kind DM** to show the most party-favorable assumptions.

Use **Smart Players + Balanced DM** for a capable party against a fair enemy
policy. This is the setting used by the prepared presentation replay.

Use **Balanced Players + Combined Batch** when comparing scenarios because it
produces a broader aggregate across both player and DM assumptions.

Use **Dumb Players + Evil DM** to stress test the encounter under unfavorable
party decisions and ruthless enemy pressure.

## Implementation references

- `src/shared/sim/types.ts` defines the public behavior types.
- `src/ui/components.tsx` defines the visible Player Behavior and DM Style
  dropdown options.
- `backend/engine/combat/setup.py` resolves requested player and monster
  behavior before combat.
- `backend/engine/combat/batch.py` expands Balanced Players and Combined Batch
  into concrete simulation runs and summary metrics.
- `backend/engine/ai/decision.py` contains the target sorting and decision logic
  for Smart/Dumb players and Kind/Balanced/Evil DMs.
- `backend/engine/ai/profiles.py` defines broad monster profiles that operate
  alongside DM Style.
