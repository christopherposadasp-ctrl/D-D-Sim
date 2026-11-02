# Python Golden Baseline

These six fixed-seed cases cover three replay encounters and three batch
summaries. Each case has its own pytest id so a failure does not hide later cases.
They exercise the live default party, not a permanently frozen historical party.

## Reviewed Update: 2026-11-02

The previous fixture blob `b845da6b38eaf51835472ecbd82c5b212ba60761` last
changed in `3b99e6c` (2026-04-28). Both original golden tests passed when run
against that exact historical engine and fixture. Its later failures were
baseline maintenance drift, not a regression introduced by the Satyr fix.

Subsequent intentional changes explain the reviewed differences:

| Change | Commit | Evidence |
| --- | --- | --- |
| Smart precombat Aid | `00c1efc` | +5 current/max HP on Fighter, Paladin, Wizard; one level-2 Paladin slot spent |
| Smart precombat Mage Armor | `79c98a7` | Wizard AC 12 to 15; one level-1 slot spent |
| Rogue Vex mastery | `c90465a` | Initial Shortbow mastery and first attack's Vex log |
| Wizard Fireball | `9b39d7a` | Custom-layout Wizard opener changes from Shatter to Fireball |
| Smart Haste priority | `ea0d113` | Current spell-selection rules after Fireball |

All three replay cases and all three batch cases were reviewed with
`scripts/review_python_goldens.py`. The relevant Aid, Mage Armor, Vex,
Fireball, and Haste rules/AI tests passed independently. Repeated replay and
batch runs must match exactly before the selective writer permits an update.
Case names, seeds, configurations, and placements were preserved; only the
reviewed result/summary blocks changed. No combat code was changed for this
baseline repair, and saved presentation replays remain unchanged.

Historical fixtures remain recoverable from Git. Detailed before/after review
reports and the byte-exact historical checkout are generated under ignored
`reports/git_preservation/`; those are evidence, not application dependencies.

A second mismatch became visible when current replays exercised Haste:
`HasteEffect.allowed_action_kinds` is a Python tuple, but JSON represents it as
an array. Goldens and the review tool now compare `model_dump(mode="json")`
against the stored JSON. Every field remains compared; no replay fields are
dropped or ignored. A focused Haste serialization regression covers this
boundary. This is a test/serialization correction, not a gameplay change.

## Future Changes

Run the review tool without `--write-fixture` first, inspect each drifting case,
trace it to intended behavior, and run independent rule tests. Select every
drifting case and classify it explicitly before writing. The writer rejects
unreviewed drift, missing classifications, unexpected changes, and inconsistent
repeat results. Never update fixtures merely to make a failing test green.
