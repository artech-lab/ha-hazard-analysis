# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project: Hazard Analysis

Home Assistant custom integration (`custom_components/hazard_analysis`) that sends camera images of an area to
an AI Task entity, scores five hazard categories from 0 to 4 and raises alerts, with a bundled dashboard card.
Distributed through HACS (category `integration`; from Home Assistant 2026.11 HACS is built in as the
Marketplace).

Answer the maintainer in the language they write in. Code, comments, commit messages, entity IDs and the README
stay in English. User-facing strings exist in English and Italian.

## Commands

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements_test.txt   # once (Python 3.13)
scripts/check.sh                   # everything CI runs: ruff, card syntax, pytest
scripts/check.sh -k hysteresis     # extra arguments go to pytest
python scripts/screenshots.py      # rebuilds images/*.png from scripts/preview.html (demo data, needs playwright)
```

Slash commands: `/publish` (first publication) and `/release X.Y.Z` (later versions).

## Layout

| Path | Content |
| --- | --- |
| `const.py` | Every constant: config keys, cadence tables, timeout, alert level. Tuning happens here |
| `analysis.py` | Pure functions, no Home Assistant imports: response validation and clamping, hysteresis, cadence |
| `prompt.py` | Pure: the instructions and the structured output sent to `ai_task.generate_data` |
| `monitor.py` | `HazardMonitor`: schedule, AI call with timeout and fallback, state, alerts, evidence, storage |
| `notify_text.py` | Alert texts in English and Italian (translation files have no section for them) |
| `entity.py`, `sensor.py`, `binary_sensor.py`, `button.py`, `switch.py` | Thin entities reading the monitor; no logic |
| `config_flow.py` | One setup form and one options form |
| `frontend/hazard-analysis-card.js` | The card: one dependency-free ES module, no build step |
| `translations/en.json`, `it.json` | Integration strings (the card has its own `STRINGS` table) |
| `tests/` | `test_analysis.py` (pure), `test_monitor.py` (fake AI answers in, entities and alerts out, on a real Home Assistant core), `test_config_flow.py`, `test_consistency.py` |

## Rules that keep it maintainable

- **One version**: `manifest.json` -> `version`. The integration appends it to the card URL (`?v=`), the card
  reads it from `import.meta.url`. Never hard-code it elsewhere (a test checks).
- **One release step**: pushing a new manifest version to `main` makes the `Release` job of
  `.github/workflows/validate.yml` create the tag and the GitHub release after all checks pass.
- **Few options**: cameras, engines and context entities. Cadence, timeout and thresholds are constants.
  Do not add options without a strong reason.
- **Logic only in `analysis.py`, `prompt.py` and `monitor.py`**. The card displays what the integration
  computes and discovers its entities from the device of the risk level sensor (`translation_key` -> role).
- **Structured output**: no `min`/`max` on number fields (some providers reject them with HTTP 400); ranges are
  enforced by `parse_reading`. A test checks.
- **Never block forever**: every AI call stays inside `asyncio.timeout(ANALYSIS_TIMEOUT_S)`.
- **Translations**: a new string goes in both `en.json` and `it.json`, in both languages of `STRINGS` in the
  card or of `notify_text.py` (tests compare the key sets). Entity IDs are always English: `entity.py` sets
  them from the entry title and the description key.
- A new entity needs: a description in its platform file, a name in both translation files, an icon in
  `icons.json` and, if the card shows it, an entry in the card's `ROLES` table (a test checks).
- Changing the prompt: keep the field names, run the tests, describe the change in the changelog (levels
  before and after may not be comparable).
- No personal data in the repository (names, e-mail addresses, entity IDs or camera names of a real
  installation, camera images or photos of real places). The README images come only from
  `scripts/preview.html`, whose data is fictional.
- License: GPL-3.0-or-later. New source files start with `# SPDX-License-Identifier: GPL-3.0-or-later`.
