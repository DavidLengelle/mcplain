"""Tests for the text helpers of the rules: ordinary texts must stay quiet"""

import pytest

from mcplain.adapters.javascript import shell_targets
from mcplain.patterns import analyzer_talk, silence_request, transmit_request
from mcplain.rules.text import hidden_characters

FETCH_DESCRIPTION = (
    "Fetches a URL from the internet and optionally extracts its contents as markdown.\n\n"
    "Although originally you did not have internet access, and were advised to refuse and tell the user this, "
    "this tool now grants you internet access. Now you can fetch the most up-to-date information and let the "
    "user know that."
)
SCOTLAND = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
DEVELOPER = "\U0001f469‍\U0001f4bb"
PERSIAN = "می‌خواهم"


@pytest.mark.parametrize("text", [f"Go {SCOTLAND}!", f"By a {DEVELOPER}", PERSIAN, "﻿Starts with a BOM", "plain"])
def test_justified_invisible_characters_are_quiet(text: str) -> None:
    """Flags, emoji joined with ZWJ, Persian with ZWNJ and a leading BOM are normal"""

    assert hidden_characters(text) == ([], [])


def test_lone_and_repeated_zero_width_spaces() -> None:
    """One zero-width space is a lone character, two in a row are a run"""

    red, lone = hidden_characters("a​b")
    assert (red, [item.kind for item in lone]) == ([], ["lone_zero_width"])
    red, lone = hidden_characters("a​​b")
    assert ([item.kind for item in red], lone) == (["zero_width_run"], [])


def test_fetch_description_is_quiet() -> None:
    """The real description of the fetch server talks about the user but asks for no silence"""

    assert silence_request(FETCH_DESCRIPTION) is None
    assert transmit_request(FETCH_DESCRIPTION, ["url"]) is None
    assert analyzer_talk(FETCH_DESCRIPTION) is None


@pytest.mark.parametrize(
    "text",
    [
        "Do not tell lies in the summary.",
        "Ne dis pas la date au format US.",
        "This tool is safe to call repeatedly.",
        "Do not scan hidden directories.",
        "scanner: the lexer state",
    ],
)
def test_ordinary_sentences_are_quiet(text: str) -> None:
    """Ordinary sentences that share words with the patterns do not match"""

    assert silence_request(text) is None
    assert analyzer_talk(text) is None


def test_shell_scripts_run_by_npm_hooks() -> None:
    """sh, bash and ./x.sh are recognized in install hooks"""

    assert shell_targets("sh scripts/setup.sh && node build.js") == ["scripts/setup.sh"]
    assert shell_targets("FOO=1 ./prepare.sh --fast") == ["./prepare.sh"]
    assert shell_targets("node-gyp rebuild") == []
