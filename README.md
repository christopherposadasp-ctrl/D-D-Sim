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

- Fighter supported to level 2
- Barbarian supported to level 2
- Rogue supported to level 2
- Monk supported to level 2

Current default player preset:

- `martial_mixed_party`
- level 2 fighter
- level 2 barbarian
- level 2 ranged rogue
- level 2 melee rogue

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
.\scripts\dev.ps1 audit-quick
.\scripts\dev.ps1 audit-full
.\scripts\dev.ps1 audit-health
```

These map to:

- `check-fast`: `ruff` plus the full `pytest` suite
- `audit-quick`: the lighter scenario audit profile with live progress and rolling reports
- `audit-full`: the slower full scenario audit profile
- `audit-health`: the code-health and benchmark audit

The task runner passes through extra arguments to the underlying script. Examples:

```powershell
.\scripts\dev.ps1 audit-quick --scenario goblin_screen
.\scripts\dev.ps1 audit-full --json
```

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
