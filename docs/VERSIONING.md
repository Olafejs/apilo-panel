# Versioning Workflow

This project now uses three layers of change tracking:

1. `git` commits for exact file diffs.
2. `VERSION` for the current application version shown in the UI.
3. `CHANGELOG.md` for human-readable "what changed in which version".

## Recommended workflow for changes

1. Create a branch (use the `codex/` prefix), e.g. `codex/fix-sync-locking`.
2. Make changes and run smoke tests.
3. Update `CHANGELOG.md` in `Unreleased`.
4. Commit with a clear message (`fix:`, `feat:`, `chore:`).

## Releasing a version

1. Decide the next version (e.g. `1.0.1`).
2. Update `VERSION`.
3. Move relevant entries from `Unreleased` into a new version section in `CHANGELOG.md`.
4. Commit and create a Git tag:

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: release 1.0.1"
git tag -a v1.0.1 -m "Release 1.0.1"
```

This gives a clear mapping: `VERSION` -> `CHANGELOG.md` -> Git tag -> exact diff.
