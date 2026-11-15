---
description: First publication on GitHub, first release and (optionally) the HACS default store
argument-hint: "[github-owner]"
---

Publish this repository for the first time. Speak the maintainer's language, ask for confirmation before
anything that is visible outside this machine, and stop at the first error to explain it.

1. `gh auth status` must succeed (otherwise ask the maintainer to run `gh auth login`).
2. Owner: the repository is prepared for `artech-lab`. If `$ARGUMENTS`
   names another owner, or the maintainer asks for one, replace it everywhere and check nothing is left:
   `grep -rl artech-lab --exclude-dir=.git --exclude-dir=.claude . | xargs sed -i "s/artech-lab/<owner>/g"`
   (macOS: `sed -i ''`).
3. Run `scripts/check.sh` (Python 3.13 virtualenv with `pip install -r requirements_test.txt`).
4. Check that no personal data is in the repository (names, e-mail addresses, entity IDs or device names
   of the maintainer's own installation); the git author is the maintainer's choice: show
   `git config user.name` / `user.email` and ask before the first commit.
5. `git init -b main`, commit `Initial release`, then create the repository WITHOUT pushing yet:
   `gh repo create <owner>/ha-hazard-analysis --public --source . --description "AI safety monitoring of a lab, workshop or garage from its cameras, with a bundled dashboard card for Home Assistant"`
6. HACS requirements, before the first push:
   `gh repo edit <owner>/ha-hazard-analysis --enable-issues --add-topic home-assistant,hacs,homeassistant-integration,ai-task,safety,hazard-detection,computer-vision,lovelace-card`
7. `git push -u origin main`, then watch the **Validate** workflow. When it is green its `Release` job
   publishes `v1.0.0` by itself. Fix and push again if a check fails.
8. Ask the maintainer to try it on their own instance: add the repository to HACS / Marketplace as a
   custom repository of type Integration, install, restart, add the integration and the card.
9. Optional, only if the maintainer asks: inclusion in the default store. Fork `hacs/default`, create a
   branch from `master`, add `<owner>/ha-hazard-analysis` to the file `integration` keeping the
   alphabetical order, open the pull request filling in its template. Then replace the README badge
   `HACS-Custom` with `HACS-Default`.
