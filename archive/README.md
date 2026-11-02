# Historical snapshots

`snapshots/2026-05-31_D-D-Sim-GUI-download/` preserves nonduplicate material from:

`C:\Users\posad\OneDrive\Documents\archived downloads\D-D-Sim-GUI\D-D-Sim-GUI`

The downloaded snapshot was dated May 31, 2026 and was moved here on August 13, 2026. Before archival, exact byte-for-byte duplicates of the active D&D Sim project were recycled, including the archived dependency installation, along with all `.DS_Store` metadata. The retained payload contains 12 historical alternatives to current source files and 50 archive-only or nonmatching generated files.

These files are historical reference material, not current application source. Do not merge them into the active project without reviewing their contents and provenance.

## Preservation backup

The backup is published on its own GitHub branch with independent history. The
isolated local checkout remains in `reports/git_preservation/gui-snapshot/`:

- GitHub branch: [`codex/archive-gui-snapshot-2026-05-31`](https://github.com/christopherposadasp-ctrl/D-D-Sim/tree/codex/archive-gui-snapshot-2026-05-31)
- Verified commit: [`7c52f1c07667c8b3f8111d465f9ccb21645ded8d`](https://github.com/christopherposadasp-ctrl/D-D-Sim/commit/7c52f1c07667c8b3f8111d465f9ccb21645ded8d)
- Payload: 62 files totaling 20,504,990 bytes, with per-file SHA-256 values in `manifest.json`
- Attributes preserve the original payload bytes, including historical line endings.

Local SHA-256 checks and the published GitHub tree confirm that all 62 payload
files retain their original bytes. The remote verification receipt is recorded
locally in `reports/git_preservation/archive_remote_verification.json`.

The separate automation recovery branch also preserves the original Git index,
12 loose objects, and their provenance manifest at verified commit
[`98df67d8d3d59ec6c30cb720ce64935a9be79813`](https://github.com/christopherposadasp-ctrl/D-D-Sim/commit/98df67d8d3d59ec6c30cb720ce64935a9be79813).
Its original recovery checkout remains unchanged. Keep both preservation
branches separate from application integration and release PRs.

The recorded snapshot and move dates above are inherited provenance. This
preservation pass verified the retained files rather than reconstructing past
recycling or move operations. `/archive/snapshots/` remains ignored in the
application branch; this README remains tracked. Git ignore rules leave local
files intact and do not themselves provide a remote backup.
