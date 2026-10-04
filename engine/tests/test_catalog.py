"""Tests for the rule catalog: the --rules option and the generated docs"""

from pathlib import Path

import pytest

from mcplain.catalog import render_catalog
from mcplain.cli import main
from mcplain.i18n import Translator
from mcplain.verdict import DEFAULT_REGISTRY

DOCS = Path(__file__).parents[2] / "docs"


@pytest.mark.parametrize(("language", "name"), [("en", "rules.md"), ("fr", "rules.fr.md")])
def test_docs_are_up_to_date(language: str, name: str) -> None:
    """docs/rules.md and docs/rules.fr.md are exactly what --rules prints"""

    expected = render_catalog(Translator(language)) + "\n"
    command = "uv run mcplain --rules" + {"en": "", "fr": " --lang fr"}[language]
    assert (DOCS / name).read_text(encoding="utf-8") == expected, f"regenerate: cd engine && {command} > ../docs/{name}"


def test_rules_option_prints_every_rule(capsys: pytest.CaptureFixture[str]) -> None:
    """--rules prints the catalog in the chosen language, one section per registered rule"""

    assert main(["--rules", "--lang", "fr"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("# Règles de MCPlain\n")
    for rule in DEFAULT_REGISTRY.rules():
        assert f"\n## {rule.identifier} {rule.slug}\n" in output
        for source in rule.sources:
            assert source.url in output


def test_catalog_says_when_an_author_is_probably_honest() -> None:
    """The serious flaw kind is explained in the catalog"""

    text = render_catalog(Translator("en"))
    section = text[text.index("## R09 command-injection") : text.index("## R10")]
    assert "serious flaw: the author is probably honest, but the flaw is serious" in section
