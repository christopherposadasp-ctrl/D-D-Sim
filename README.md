# D&D Encounter Simulator

This repository currently contains a TypeScript/React proof of concept encounter simulator and the planning notes for the Python-based V4 rewrite.

## Current State

- Local-first V3 proof of concept implemented in `src/`
- Deterministic replay and batch simulation
- Grid combat, flanking, opportunity attacks, player behavior, and DM behavior settings
- Browser UI built with React + Vite

## Planned Direction

The long-term direction is:

- Python backend engine for all simulation logic
- Non-Python user interface
- Final target scope: broader class, monster, and spell support

The working roadmap and design decisions are tracked in [docs/MASTER_NOTES.md](docs/MASTER_NOTES.md).

## Repository Layout

- `src/` current TypeScript proof of concept
- `docs/` planning, notes, and reference material
- `docs/reference/` source PDFs and static reference documents

## Current Commands

```powershell
npm install
npm run dev
```

Build and test:

```powershell
npm run test
npm run build
```
