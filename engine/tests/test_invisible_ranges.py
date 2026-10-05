"""Tests of the invisible character list shared with the website"""

import json
from pathlib import Path

from mcplain.adapters.common import INVISIBLE_RANGES
from mcplain.invisible_ranges import WEB_FILE, invisible_ranges_json

REPOSITORY = Path(__file__).resolve().parents[2]


def test_website_list_is_the_engine_list() -> None:
    """web/src/lib/invisible-characters.json is exactly what the engine generates"""

    assert (REPOSITORY / WEB_FILE).read_text(encoding="utf-8") == invisible_ranges_json()


def test_json_keeps_every_range_and_family() -> None:
    """Each range of INVISIBLE_RANGES is in the document, in the same order"""

    document = json.loads(invisible_ranges_json())
    pairs = [(int(item["first"][2:], 16), int(item["last"][2:], 16), item["category"]) for item in document]
    assert pairs == [(low, high, category.value) for low, high, category in INVISIBLE_RANGES]
