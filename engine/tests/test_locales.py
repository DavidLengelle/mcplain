"""Tests that every user-facing text exists in English and French"""

import json
import re
from pathlib import Path

import pytest

from mcplain.capabilities import SENSITIVE_PATH_PATTERNS, Capability, PathKind
from mcplain.i18n import Translator
from mcplain.models import (
    AnalysisStatus,
    DeclarationKind,
    InvisibleCategory,
    LocationKind,
    OutsideKind,
    SourceKind,
    SourceOrigin,
    TrackingGap,
)

SOURCE = Path(__file__).parents[1] / "src" / "mcplain"
LOCALES = SOURCE / "locales"
CODE_PATTERN = re.compile(r"[\"']((?:input|fetch|archive|analyze|source|note)\.[a-z_]+)[\"']")
CAVEAT_PATTERN = re.compile(r"[\"'](caveat\.[a-z_]+)[\"']")


def catalog(language: str) -> dict[str, str]:
    """Load one locale file"""

    return json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))


def test_both_languages_have_the_same_keys() -> None:
    """English and French define exactly the same messages"""

    assert set(catalog("en")) == set(catalog("fr"))


def test_placeholders_match() -> None:
    """A message uses the same placeholders in both languages"""

    english = catalog("en")
    french = catalog("fr")
    for key, text in english.items():
        assert set(re.findall(r"\{(\w+)\}", text)) == set(re.findall(r"\{(\w+)\}", french[key])), key


def test_every_code_used_in_the_engine_is_translated() -> None:
    """Error, source and note codes written in the code all have a message"""

    keys = set(catalog("en"))
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for code in CODE_PATTERN.findall(text):
            assert code in keys, f"{code} from {path.name}"
        for code in CAVEAT_PATTERN.findall(text):
            assert f"reason.{code}" in keys, f"{code} from {path.name}"


@pytest.mark.parametrize("language", ["en", "fr"])
def test_enumerations_are_translated(language: str) -> None:
    """Every enumerated value shown to the user has a message"""

    keys = set(catalog(language))
    expected = [f"capability.{item.value}" for item in Capability]
    expected += [f"reason.capability.{item.value}" for item in Capability]
    expected += [f"status.{item.value}" for item in AnalysisStatus]
    expected += [f"reason.status.{item.value}" for item in AnalysisStatus if item is not AnalysisStatus.OK]
    expected += [f"declaration.{item.value}" for item in DeclarationKind]
    expected += [f"invisible.{item.value}" for item in InvisibleCategory]
    expected += [f"location.{item.value}" for item in LocationKind]
    expected += [f"source_kind.{item.value}" for item in SourceKind]
    expected += [f"origin.{item.value}" for item in SourceOrigin]
    expected += [f"sensitive.{entry.category}" for entry in SENSITIVE_PATH_PATTERNS]
    expected += [f"path_kind.{item.value}" for item in PathKind]
    expected += [f"gap.{item.value}" for item in TrackingGap]
    expected += [f"cli.outside.{item.value}" for item in OutsideKind]
    missing = [key for key in expected if key not in keys]
    assert missing == []


def test_translator_falls_back_and_formats() -> None:
    """Unknown languages fall back to English and parameters are filled in"""

    assert Translator("de").language == "en"
    assert Translator("fr")("cli.places", count=3) == "3 endroit(s)"
    assert Translator("en")("no.such.key") == "no.such.key"


@pytest.mark.parametrize("language", ["en", "fr"])
def test_urls_are_never_called_contacted(language: str) -> None:
    """No message claims that a server contacts a site: MCPlain only sees URLs quoted in the code"""

    for text in catalog(language).values():
        assert "contact" not in text.lower()
