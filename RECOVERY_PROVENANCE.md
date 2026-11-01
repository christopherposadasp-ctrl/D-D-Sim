# Original automation Git provenance

This commit extends recovery snapshot
`66315e4a675ce5c4e3617589ceec52a3a346f943` on
`recovery/automation-0db8-2026-07-09`. The source is the separate checkout at
`C:\Users\posad\OneDrive\Desktop\OR_Prog\_Archive\D&D_0db8_Automation_Repo_2026-07-09`.
Preservation was performed in an isolated staging copy. The original checkout,
its live Git metadata, and its retained artifacts were left intact.

## What the artifacts establish

`_git_index` is a valid version 2 Git index with a valid checksum and four
stage-zero entries. `_git_objects/` contains 12 loose, zlib-compressed Git
objects whose decompressed SHA-1 identities match their filenames: four blobs,
seven trees, and one commit.

The original commit is `4b2af799851e37b4ad40dbf71c6c5473b72779ca`, titled
`Add warrior veteran and knight CR3 monster pair`. It records Codex Automation
as author and committer, has no parent, and references tree
`5c6b67f754c7bdc4f0b7ad228a9d9ad751fa89ad`. Its tree contains only these files:

| Path | Original Git Blob ID |
| --- | --- |
| `backend/content/enemies.py` | `9936f34a60a5c62ff5ec518fea948d5202e9a3fb` |
| `docs/reference/srd_Creatures_Trimmed_V4.xlsx` | `6cc7cea1dd721f97398d7057b0157ed8f22f7618` |
| `tests/rules/monster_expectations.py` | `34d54106faecde06bf38b2deb8385787fb4e81da` |
| `tests/rules/test_monster_behavior.py` | `1b371f6aaf253b2ddbb5b7f10201d517e948a7c9` |

All four blob IDs also occur at these paths in published snapshot `66315e4`.
That snapshot is a separate root commit preserving 115 application files. It
preserved the four file versions, but did not include the original index,
original commit object, or loose-object layout as tracked artifacts.

## What this preservation adds

This commit tracks the original 668-byte index and all 12 compressed objects,
57,578 bytes in total, alongside this document, a manifest, and attributes that
disable text conversion for the raw artifacts. It leaves the snapshot's 115
previously tracked files unchanged.

`RECOVERY_MANIFEST.json` records artifact paths, byte counts, SHA-256 hashes,
parsed index entries, and decoded object identities. Verification checks the
index checksum, every object's identity, the original four-file tree, and the
published GitHub tree.

The original checkout still contains its own bytecode caches and empty pytest
temporary directories; those generated files are not part of this commit.
The preserved `_git_*` files are evidence, not active Git metadata. Keep their
original names and do not replace a live repository's index or object store
with them.

This recovery branch has independent historical roots. Do not merge it into
the live application. Any future selective recovery requires a comparison
with the current Python engine and tests.
