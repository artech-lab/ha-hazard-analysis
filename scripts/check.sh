#!/usr/bin/env bash
# Every check CI runs, in one command: lint, format, card syntax, tests.
set -euo pipefail
cd "$(dirname "$0")/.."

# The integration depends on core components whose Python requirements are not
# part of pytest-homeassistant-custom-component: install the versions pinned by
# the installed Home Assistant (no-op when already present).
python - <<'PY'
import importlib.util, json, pathlib, subprocess, sys
import homeassistant.components as components
root = pathlib.Path(components.__file__).parent
needed = []
for name in ("frontend", "camera", "conversation"):
    for requirement in json.loads((root / name / "manifest.json").read_text()).get("requirements", []):
        module = {"home-assistant-frontend": "hass_frontend", "PyTurboJPEG": "turbojpeg",
                  "home-assistant-intents": "home_assistant_intents"}.get(requirement.split("==")[0],
                                                                         requirement.split("==")[0].lower())
        if importlib.util.find_spec(module) is None:
            needed.append(requirement)
if needed:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *needed])
PY

ruff check .
ruff format --check .
# The card is an ES module: check its syntax as one.
cp custom_components/hazard_analysis/frontend/hazard-analysis-card.js "${TMPDIR:-/tmp}/hazard-analysis-card.mjs"
node --check "${TMPDIR:-/tmp}/hazard-analysis-card.mjs"
pytest -q "$@"
