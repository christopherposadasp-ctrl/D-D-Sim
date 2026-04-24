# Audit Runbook

## Current Audit State

- Pass 1 closed on `integration` at commit `01cecc3` with warnings and waivers.
- Pass 2 completed as stable-with-warnings: deterministic replay, deterministic batch, async batch jobs, and long audit commands passed with no blockers.
- Pass 3 is the current clarity and audit-maintainability gate.
- Nightly audit automation remains a pre-major-audit safety net, not a replacement for the full audit passes.

## Standard Commands

Run these from the repo root through the PowerShell wrapper:

```powershell
.\scripts\dev.ps1 check-fast
.\scripts\dev.ps1 audit-quick
.\scripts\dev.ps1 audit-full
.\scripts\dev.ps1 audit-health
.\scripts\dev.ps1 fighter-audit-quick
.\scripts\dev.ps1 fighter-audit-full
.\scripts\dev.ps1 barbarian-audit-quick
.\scripts\dev.ps1 barbarian-audit-full
.\scripts\dev.ps1 rogue-audit-quick
.\scripts\dev.ps1 rogue-audit-full
.\scripts\dev.ps1 class-audit-slices
.\scripts\dev.ps1 behavior-diagnostics
.\scripts\dev.ps1 nightly-audit
.\scripts\dev.ps1 pass2-stability
.\scripts\dev.ps1 pass3-clarity
```

Direct equivalents:

- `check-fast`: `py -3.13 -m ruff check backend tests scripts` and `py -3.13 -m pytest -q -m "not slow" tests\golden tests\rules tests\integration`
- `audit-quick`: `py -3.13 .\scripts\run_scenario_audit.py`
- `audit-full`: `py -3.13 .\scripts\run_scenario_audit.py --full`
- `audit-health`: `py -3.13 .\scripts\run_code_health_audit.py --write-report`
- `fighter-audit-quick`: `py -3.13 .\scripts\run_fighter_audit.py`
- `fighter-audit-full`: `py -3.13 .\scripts\run_fighter_audit.py --full`
- `barbarian-audit-quick`: `py -3.13 .\scripts\run_barbarian_audit.py`
- `barbarian-audit-full`: `py -3.13 .\scripts\run_barbarian_audit.py --full`
- `rogue-audit-quick`: `py -3.13 .\scripts\run_rogue_audit.py`
- `rogue-audit-full`: `py -3.13 .\scripts\run_rogue_audit.py --full`
- `class-audit-slices`: `py -3.13 .\scripts\run_class_audit_slices.py`
- `behavior-diagnostics`: `py -3.13 .\scripts\investigate_smart_vs_dumb.py`
- `nightly-audit`: `py -3.13 .\scripts\run_nightly_audit.py --integration-branch integration`
- `pass2-stability`: `py -3.13 .\scripts\run_pass2_stability.py`
- `pass3-clarity`: `py -3.13 .\scripts\run_pass3_clarity.py`

## Canonical Reports

- Pass 1 readiness: `reports/pass1/pass1_readiness_2026-04-23.md`
- Scenario audit: `reports/scenario_audit_latest.json`
- Rogue audit: `reports/rogue_audit/rogue_audit_latest.json`
- Mixed-party class refresh: `reports/pass1/class_slices/martial_mixed_party_refresh_2026-04-23.json`
- Code health: `reports/code_health_audit.json` and `reports/code_health_audit.md`
- Pass 2 stability: `reports/pass2/pass2_stability_latest.json` and `reports/pass2/pass2_stability_latest.md`
- Pass 3 clarity: `reports/pass3/pass3_clarity_latest.json` and `reports/pass3/pass3_clarity_latest.md`

## Monitored Findings

- Scenario smart-under-dumb warning in `hobgoblin_kill_box`.
- Rogue monitored notes in `wolf_harriers` and `marsh_predators`.
- Mixed-party Fighter warnings in `orc_push`, `predator_rampage`, and `captains_crossfire`.
- Mixed-party Barbarian warning in `wolf_harriers`.

## Active Waivers

- `monk_audit_runner_missing`: retire by implementing a dedicated Monk audit runner.
- `wizard_audit_runner_missing`: retire by implementing a dedicated Wizard audit runner.
- `monster_audit_runner_missing`: retire by implementing a dedicated Monster audit runner.

## Closeout Rule

Pass 3 can close with `warn` while monitored findings and waivers remain active. It cannot close if canonical reports are missing, docs are stale, runner mappings are broken, or standard gates fail.
