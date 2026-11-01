# Historical GUI snapshot

This branch preserves the retained, nonduplicate portion of the May 31, 2026
GUI download. It has independent history and is a reference archive rather than
a runnable or complete application checkout.

The original download was recorded at
`C:\Users\posad\OneDrive\Documents\archived downloads\D-D-Sim-GUI\D-D-Sim-GUI`.
The application archive README records that it was moved into the project's
local archive on August 13, 2026, after exact duplicates and `.DS_Store` files
had been recycled. Those dates and past actions are recorded provenance, not
independently reconstructed by this preservation pass.

The payload lives in `snapshots/2026-05-31_D-D-Sim-GUI-download/` and contains
62 files totaling 20,504,990 bytes. Twelve are alternatives to same-path source
files in application commit `67a6a6a6b9ad68ba66a7295b9159cffff45ae32a`;
the remaining 50 include archive-only source, artwork, build outputs, and
generated metadata. The archive retains all of them exactly as found.

`manifest.json` records every payload path, byte count, and SHA-256. The
attributes file disables text conversion for the payload so Git retains the
recorded bytes. Preservation also verifies the staged objects and published
GitHub tree against the local source.

Application development continues on `codex/monster-development` and
`integration`. Keep this archive branch separate from their histories. Review
individual historical files and their dependencies before selectively reusing
anything; do not merge this branch into the application.
