# D&D Encounter Simulator

This repository now contains:

- the React + TypeScript frontend in `src/`
- shared frontend simulation helpers in `src/shared/`
- the Python simulation engine and API in `backend/`
- golden, rules, and API tests in `tests/`

## Current State

- Local-first React frontend implemented in `src/`
- Python V4.0 parity backend implemented in `backend/`
- V4.2-A player-content foundation implemented with backend-owned class, progression, feature, loadout, and player-preset registries
- The Python backend is the live simulation authority; the frontend consumes backend catalogs plus replay/state transport types
- Deterministic replay and batch simulation
- Grid combat, flanking, opportunity attacks, player behavior, and DM behavior settings
- Browser UI built with React + Vite and wired to the Python API
- FastAPI layer for Python `run`, `batch`, async `batch-jobs`, and catalog endpoints
- Backend-owned preset, enemy, and player catalog data consumed or exposed at runtime

## Live Content Snapshot

Current live martial class support:

- Fighter supported to level 5 as a Battle Master great-weapon striker with Extra Attack and Tactical Shift
- Barbarian supported to level 2
- Rogue supported to level 5 for the ranged Assassin path and level 2 for the melee path
- Monk supported to level 2
- Wizard supported to level 4 as an Evoker with an Intelligence ASI, Potent Cantrip, Scorching Ray, Shatter, and Mage Armor metadata/manual support
- Paladin supported to level 5 as an Oath of the Ancients plate-and-shield support tank with Extra Attack, level 2 Bless, Aid rules support, Lay on Hands, Cure Wounds, Divine Smite, Channel Divinity, Nature's Wrath, and Sentinel

Current default player preset:

- `martial_mixed_party`
- level 5 Battle Master fighter
- level 5 Oath of the Ancients paladin
- level 5 ranged Assassin rogue
- level 4 Evoker wizard

Active enemy presets:

- `goblin_screen`
- `bandit_ambush`
- `mixed_patrol`
- `orc_push`
- `wolf_harriers`
- `marsh_predators`
- `hobgoblin_kill_box`
- `predator_rampage`
- `bugbear_dragnet`
- `deadwatch_phalanx`
- `captains_crossfire`

## Planned Direction

The long-term direction is:

- Python backend engine for all simulation logic
- Non-Python user interface
- Final target scope: broader class, monster, and spell support

The working roadmap and design decisions are tracked in:

- [docs/MASTER_NOTES.md](docs/MASTER_NOTES.md)
- [docs/V4_ARCHITECTURE.md](docs/V4_ARCHITECTURE.md)
- [docs/CONTENT_BACKLOG.md](docs/CONTENT_BACKLOG.md)
- [docs/PLAYER_CLASS_IMPLEMENTATION.md](docs/PLAYER_CLASS_IMPLEMENTATION.md)

## Repository Layout

- `src/` React frontend
- `src/shared/` frontend transport types and placement/grid helpers
- `backend/` Python engine, rules, AI, and API
- `tests/` Python golden, rules, and integration tests
- `scripts/run_code_health_audit.py` manual code-health and benchmark audit
- `docs/` planning, notes, and reference material
- `docs/reference/` source PDFs and static reference documents

For new class work, start with [docs/PLAYER_CLASS_IMPLEMENTATION.md](docs/PLAYER_CLASS_IMPLEMENTATION.md).

## Frontend Commands

```powershell
npm install
npm run dev
```

The frontend now sends simulation requests to the Python backend through the Vite dev proxy, so run the API server in a second PowerShell window before using the UI.

Build and test:

```powershell
npm run test
npm run build
```

## Python Commands

Install Python dependencies:

```powershell
py -3.13 -m pip install -e .[dev]
```

## Named Audit Commands

Use the PowerShell task runner for the standard checks:

```powershell
.\scripts\dev.ps1 check-fast
.\scripts\dev.ps1 daily-housekeeping
.\scripts\dev.ps1 party-validation
.\scripts\dev.ps1 pc-tuning-sample
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

These map to:

- `check-fast`: `ruff` plus the non-slow backend `pytest` suite
- `daily-housekeeping`: conservative repo status, doc-drift, and safe commit recommendation report with no automatic staging or commits
- `party-validation`: focused current-party validation for `martial_mixed_party` against `reaction_bastion`, `skyhunter_pincer`, `hobgoblin_command_screen`, and `berserker_overrun`
- `pc-tuning-sample`: event-level PC tuning sample across the standard validation scenarios; every run reports current-party Fighter `F1`, Paladin `F2`, ranged Rogue `F3`, and Wizard `F4`, with the selected profile shown last in detail
- `audit-quick`: the lighter scenario audit profile with live progress and rolling reports
- `audit-full`: the slower full scenario audit profile
- `audit-health`: the code-health and benchmark audit
- `fighter-audit-quick`: the dedicated Fighter audit quick profile
- `fighter-audit-full`: the dedicated Fighter audit full profile
- `barbarian-audit-quick`: the dedicated Barbarian audit quick profile
- `barbarian-audit-full`: the dedicated Barbarian audit full profile
- `rogue-audit-quick`: the dedicated level 2 ranged Rogue audit
- `rogue-audit-full`: the dedicated Rogue audit full profile
- `class-audit-slices`: timeout-safe segmented Fighter/Barbarian audit slices
- `behavior-diagnostics`: smart-vs-dumb behavior investigation helper
- `nightly-audit`: the nightly layered audit protocol
- `pass2-stability`: the deterministic replay/batch and async stability gate
- `pass3-clarity`: the clarity, docs, report, and audit-maintainability gate

The task runner passes through extra arguments to the underlying script. Examples:

```powershell
.\scripts\dev.ps1 party-validation --workers 4
.\scripts\dev.ps1 pc-tuning-sample --runs-per-scenario 20
.\scripts\dev.ps1 pc-tuning-sample --profile rogue --runs-per-scenario 20
.\scripts\dev.ps1 pc-tuning-sample --profile fighter --player-behavior both --runs-per-scenario 20
.\scripts\dev.ps1 pc-tuning-sample --profile wizard --runs-per-scenario 20
.\scripts\dev.ps1 audit-quick --scenario goblin_screen
.\scripts\dev.ps1 audit-full --json
```

Routine development should usually run:

```powershell
.\scripts\dev.ps1 check-fast
.\scripts\dev.ps1 party-validation
```

Use the broader audit commands before major merges, broad rules changes, or release checkpoints.

## Direct Python Commands

Run the Python tests directly:

```powershell
py -3.13 -m pytest
```

Run the quick scenario audit across the active preset catalog:

```powershell
py -3.13 .\scripts\run_scenario_audit.py
```

Run the full scenario audit:

```powershell
py -3.13 .\scripts\run_scenario_audit.py --full
```

Run focused party validation directly:

```powershell
py -3.13 .\scripts\run_party_validation.py
```

Run conservative daily housekeeping directly:

```powershell
py -3.13 .\scripts\run_daily_housekeeping.py
```

Run the focused PC tuning sample directly:

```powershell
py -3.13 .\scripts\run_pc_tuning_sample.py
py -3.13 .\scripts\run_pc_tuning_sample.py --profile rogue
py -3.13 .\scripts\run_pc_tuning_sample.py --profile fighter --player-behavior both
py -3.13 .\scripts\run_pc_tuning_sample.py --profile wizard
```

Run the manual code-health audit:

```powershell
py -3.13 .\scripts\run_code_health_audit.py --write-report
```

Run the Python static checks:

```powershell
py -3.13 -m ruff check backend tests scripts
```

Run the Python API locally:

```powershell
py -3.13 -m uvicorn backend.api.app:app --reload
```

Swagger/OpenAPI docs are then available at:

- `http://127.0.0.1:8000/docs`

## Local Development Flow

Use two PowerShell windows from the repo root:

```powershell
py -3.13 -m uvicorn backend.api.app:app --reload
```

```powershell
npm run dev
```

Then open the Vite URL shown in the terminal. The frontend will proxy `/api/*` requests to `http://127.0.0.1:8000`.
