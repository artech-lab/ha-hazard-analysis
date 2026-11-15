"""Guards that keep the package easy to maintain."""

import json
from pathlib import Path
import re

from custom_components.hazard_analysis import notify_text
from custom_components.hazard_analysis.binary_sensor import BINARY_SENSORS
from custom_components.hazard_analysis.button import BUTTON
from custom_components.hazard_analysis.sensor import SENSORS
from custom_components.hazard_analysis.switch import SWITCH

ROOT = Path(__file__).parents[1] / "custom_components" / "hazard_analysis"
CARD = ROOT / "frontend" / "hazard-analysis-card.js"
PLATFORMS = {
    "sensor": [d.key for d in SENSORS],
    "binary_sensor": [d.key for d in BINARY_SENSORS],
    "button": [BUTTON.key],
    "switch": [SWITCH.key],
}


def _keys(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _keys(value, f"{prefix}.{key}")
    else:
        yield prefix


def test_integration_translations_have_same_keys() -> None:
    en = json.loads((ROOT / "translations" / "en.json").read_text())
    it = json.loads((ROOT / "translations" / "it.json").read_text())
    assert set(_keys(en)) == set(_keys(it))


def test_every_entity_has_a_name_and_an_icon() -> None:
    names = json.loads((ROOT / "translations" / "en.json").read_text())["entity"]
    icons = json.loads((ROOT / "icons.json").read_text())["entity"]
    for platform, keys in PLATFORMS.items():
        assert set(names[platform]) == set(keys), platform
        assert set(icons[platform]) == set(keys), platform


def test_notification_texts_have_same_keys() -> None:
    assert set(notify_text.STRINGS["en"]) == set(notify_text.STRINGS["it"])


def test_card_translations_have_same_keys() -> None:
    card = CARD.read_text()
    english, italian = re.search(
        r"const STRINGS = \{\n  en: \{(.*?)\n  \},\n  it: \{(.*?)\n  \}\n\};", card, re.S
    ).groups()
    keys = [set(re.findall(r"^    (\w+):", block, re.M)) for block in (english, italian)]
    assert keys[0] and keys[0] == keys[1]


def test_card_knows_every_entity_role() -> None:
    roles = set(re.findall(r'^  (\w+): "\w+"', re.search(r"const ROLES = \{(.*?)\};", CARD.read_text(), re.S)[1], re.M))
    assert roles == {key for keys in PLATFORMS.values() for key in keys} - {"ai_engine", "analysis_duration"}


def test_version_lives_only_in_the_manifest() -> None:
    version = json.loads((ROOT / "manifest.json").read_text())["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    for path in [*ROOT.glob("*.py"), CARD]:
        assert version not in path.read_text(), f"hard-coded version in {path.name}"
