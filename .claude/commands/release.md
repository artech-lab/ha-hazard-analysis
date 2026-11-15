---
description: Release a new version (bump manifest.json, changelog, checks, push; CI publishes it)
argument-hint: "X.Y.Z"
---

Release version `$ARGUMENTS`. If no version was given, propose one following Semantic Versioning from the
`Unreleased` section of `CHANGELOG.md` (fix: patch, new feature: minor, breaking change: major) and ask
the maintainer to confirm it. Speak the maintainer's language and stop at the first error to explain it.

1. Preconditions: on branch `main`, working tree clean, up to date with `origin/main`, the repository
   already published (otherwise run `/publish` first), tag `v<version>` not existing yet.
2. `CHANGELOG.md`: the `Unreleased` section must describe the changes; if it is empty, draft it from
   `git log <last tag>..HEAD` and ask the maintainer to approve it. Rename it to
   `## [<version>] - <today, YYYY-MM-DD>` and add a new empty `## [Unreleased]` above it.
3. Set `"version": "<version>"` in `custom_components/hazard_analysis/manifest.json`. This is the only
   place where the version is written.
4. Run `scripts/check.sh`. If the look of the card changed, run `python scripts/screenshots.py` and show
   the new images to the maintainer.
5. Show `git diff`, ask for confirmation, then commit `Release <version>` and push.
6. Watch the **Validate** workflow (`gh run watch <id> --exit-status`): when HACS, Hassfest and the tests
   pass, its `Release` job creates the tag and the GitHub release with the changelog section as notes.
   Check with `gh release view v<version>`. HACS offers the update to users within a few hours.
