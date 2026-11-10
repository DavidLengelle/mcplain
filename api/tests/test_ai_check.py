"""Tests of the control of what the AI wrote: one test per rule, and the accepted false positives, by name"""

import json
from typing import Any

import pytest

from mcplain_api.ai_check import (
    Checked,
    OutputRejected,
    RejectReason,
    check_notice,
    check_translation,
)
from mcplain_api.ai_words import FORBIDDEN_WORDS, has_forbidden_word

FORM: dict[str, Any] = {
    "tools": [{"name": "get_weather", "capabilities": {"secrets": True}}],
    "domains_cited_in_code": ["api.github.com"],
}


def notice(**values: Any) -> str:
    """Return the text of a notice, good unless the test changes a field"""

    fields = {
        "summary": "Ce serveur donne la météo.",
        "use_cases": ["Demander le temps de demain."],
        "tool_titles": [{"name": "get_weather", "title": "Donner la météo", "sentence": "Il dit le temps."}],
        "mismatch": False,
        "alert": "",
    }
    fields.update(values)
    return json.dumps(fields)


def rejected(text: str) -> RejectReason:
    """Return the reason why a notice is rejected"""

    with pytest.raises(OutputRejected) as caught:
        check_notice(text, FORM)
    return caught.value.reason


def titled(title: str = "Titre", sentence: str = "Phrase.", name: str = "get_weather") -> list[dict[str, str]]:
    """Return tool_titles with one entry"""

    return [{"name": name, "title": title, "sentence": sentence}]


def test_a_good_notice_passes() -> None:
    """A plain notice goes through as written, without an alert"""

    checked = check_notice(notice(), FORM)
    assert checked.content["summary"] == "Ce serveur donne la météo."
    assert checked.content["tool_titles"][0]["title"] == "Donner la météo"
    assert checked.content["alert"] is None
    assert checked.dropped is None


@pytest.mark.parametrize(
    "fields",
    [
        {"summary": "x" * 601},
        {"use_cases": ["a", "b", "c", "d"]},
        {"use_cases": ["x" * 161]},
        {"mismatch": True, "alert": "x" * 241},
    ],
)
def test_too_long_rejects_the_notice(fields: dict[str, Any]) -> None:
    """Above the limits of the summary, the use cases and the alert, the whole notice goes"""

    assert rejected(notice(**fields)) is RejectReason.LENGTH


def test_limits_are_inclusive() -> None:
    """Exactly at the limit is accepted"""

    text = notice(summary="x" * 600, use_cases=["y" * 160] * 3, tool_titles=titled("t" * 40, "s" * 160))
    checked = check_notice(text, FORM)
    assert checked.dropped is None
    assert len(checked.content["tool_titles"]) == 1


@pytest.mark.parametrize("entry", [titled("t" * 41), titled("Titre", "s" * 161), titled("  ")])
def test_a_title_out_of_limits_falls_back_to_the_technical_name(entry: list[dict[str, str]]) -> None:
    """Only that title goes; the site then shows the technical name"""

    checked = check_notice(notice(tool_titles=entry), FORM)
    assert checked.content["tool_titles"] == []
    assert checked.dropped is RejectReason.LENGTH


def test_an_unknown_tool_is_dropped() -> None:
    """tool_titles keeps only the names of the form"""

    checked = check_notice(notice(tool_titles=titled(name="send_money")), FORM)
    assert checked.content["tool_titles"] == []
    assert checked.dropped is RejectReason.UNKNOWN_TOOL


def test_a_missing_title_is_not_an_error() -> None:
    """Without a title, the tool keeps its technical name"""

    checked = check_notice(notice(tool_titles=[]), FORM)
    assert checked.content["tool_titles"] == []
    assert checked.dropped is None


@pytest.mark.parametrize("word", FORBIDDEN_WORDS)
def test_every_forbidden_word_is_caught_in_any_case(word: str) -> None:
    """Each word of the list, as a whole word, in lower and upper case"""

    assert has_forbidden_word(f"Ceci est {word}.")
    assert has_forbidden_word(f"Ceci est {word.upper()}.")


@pytest.mark.parametrize(
    "text",
    [
        "Clique sur le bouton.",
        "Il travaille sur tes fichiers.",
        "Tu es sure de toi ?",
        "Un fichier sans dangers.",
        "Il a un coffre-fortsafe.",
        "unsafe",
        "Il vérifie la météo.",
        "Il sécurise",
        "unofficial",
    ],
)
def test_accents_and_whole_words_count(text: str) -> None:
    """Sur is not sûr, and a word inside a longer one is not that word"""

    assert not has_forbidden_word(text)


def test_a_decomposed_accent_is_still_caught() -> None:
    """A word written with a separate accent is the same word"""

    assert has_forbidden_word("Ce serveur est sûr.")


@pytest.mark.parametrize(
    "fields",
    [
        {"summary": "Ce serveur est fiable."},
        {"use_cases": ["Un usage sans risque."]},
        {"tool_titles": titled("Outil officiel")},
        {"tool_titles": titled("Titre", "Une phrase trusted.")},
        {"mismatch": True, "alert": "Ce serveur est safe."},
    ],
)
def test_one_forbidden_word_rejects_the_whole_notice(fields: dict[str, Any]) -> None:
    """In the summary, the use cases, the titles, the sentences or the alert"""

    assert rejected(notice(**fields)) is RejectReason.FORBIDDEN_WORD


def test_false_positive_accepted_secure_connection_is_rejected() -> None:
    """Accepted by David: an honest sentence with sécurisée is rejected, and the fallback notice shows"""

    summary = "Il se connecte à GitHub par une connexion sécurisée (HTTPS)."
    assert rejected(notice(summary=summary)) is RejectReason.FORBIDDEN_WORD


def test_false_positive_accepted_weather_with_secrets_shows_the_alert() -> None:
    """Accepted by David: the alert shows even if the server only reads its own API key; the color does not change"""

    sentence = "Un outil de météo qui touche aux secrets, c'est étonnant."
    checked = check_notice(notice(mismatch=True, alert=sentence), FORM)
    assert checked.content["alert"] == sentence
    assert "color" not in checked.content
    assert "verdict" not in checked.content


def test_click_on_the_button_is_not_rejected() -> None:
    """The preposition sur is not the adjective sûr"""

    assert check_notice(notice(summary="Clique sur le bouton."), FORM).content["summary"] == "Clique sur le bouton."


@pytest.mark.parametrize(
    "summary",
    [
        "Voir http://example.com ici.",
        "Voir https://example.com ici.",
        "Voir WWW.example.com ici.",
        "Un texte <b>gras</b>.",
        "Un texte a > b.",
        "Un [lien](quelque).",
        "Écris à quelqu'un@example.org.",
        "Il va sur evil.example.org.",
        "Il va sur sub.api.github.com.",
        "Il va sur other-github.com.",
    ],
)
def test_links_and_unknown_domains_are_rejected(summary: str) -> None:
    """Link marks, e-mail addresses, and a domain that is neither in the form nor a parent of it"""

    assert rejected(notice(summary=summary)) is RejectReason.LINK


@pytest.mark.parametrize(
    "summary",
    [
        "Il parle à api.github.com.",
        "Il parle à github.com.",
        "Il lit package.json et Node.js.",
        "Par exemple, e.g. ceci, version 1.2.3.",
    ],
)
def test_form_domains_their_parents_and_file_names_pass(summary: str) -> None:
    """A domain of the form, its parent, a file name or a version is not a link"""

    assert check_notice(notice(summary=summary), FORM).content["summary"] == summary


@pytest.mark.parametrize("character", ["\u200b", "\u202e", "\U000e0041", "\u00ad", "\x07"])
def test_invisible_characters_are_rejected(character: str) -> None:
    """The same list as R01 and O07"""

    assert rejected(notice(summary=f"Un{character} texte.")) is RejectReason.INVISIBLE


def test_french_spaces_and_line_breaks_are_not_invisible() -> None:
    """A no-break space before a colon is normal French"""

    summary = "Un texte : voilà, et\nla suite."
    assert check_notice(notice(summary=summary), FORM).content["summary"] == summary


def test_mismatch_false_ignores_the_alert_entirely() -> None:
    """Never a good word: with mismatch false, the alert is not read, even when it would be rejected"""

    checked = check_notice(notice(mismatch=False, alert="Tout va bien, c'est sûr."), FORM)
    assert checked.content["alert"] is None
    assert "mismatch" not in checked.content


def test_mismatch_true_with_an_empty_alert_shows_nothing() -> None:
    """Nothing to show means nothing shown"""

    assert check_notice(notice(mismatch=True, alert="  "), FORM).content["alert"] is None


@pytest.mark.parametrize("text", ["pas du json", "[]", '{"summary": ""}', notice(summary=""), notice(extra="x"), notice(mismatch="oui")])
def test_bad_json_is_rejected(text: str) -> None:
    """Text, the wrong shape, an empty summary, an extra field or the wrong type"""

    assert rejected(text) is RejectReason.BAD_JSON


def test_a_rejection_never_carries_the_text() -> None:
    """The exception holds the code only: the text can't be stored or logged through it"""

    with pytest.raises(OutputRejected) as caught:
        check_notice(notice(summary="Ce serveur est fiable."), FORM)
    assert str(caught.value) == "forbidden_word"
    assert "fiable" not in repr(caught.value)
    assert caught.value.__cause__ is None


ITEMS = [{"id": "tool_0", "text": "Reads https://example.com/doc now."}, {"id": "tool_1", "text": "Two."}]


def translated(*items: tuple[str, str]) -> str:
    """Return the text of a translation"""

    return json.dumps({"items": [{"id": identifier, "text": text} for identifier, text in items]})


def test_a_good_translation_passes_with_the_authors_words() -> None:
    """The reassuring words are the author's: the list does not apply to a translation"""

    text = translated(("tool_0", "Lit https://example.com/doc maintenant. C'est sûr et officiel."), ("tool_1", "Deux."))
    checked: Checked = check_translation(text, ITEMS)
    assert [item["id"] for item in checked.content["items"]] == ["tool_0", "tool_1"]
    assert checked.dropped is None


@pytest.mark.parametrize(
    ("translation", "reason"),
    [
        ("x" * (3 * len("Two.") + 51), RejectReason.LENGTH),
        ("Va sur https://autre.example.com.", RejectReason.LINK),
        ("Va sur www.autre.example.com.", RejectReason.LINK),
        ("Deux\u200b.", RejectReason.INVISIBLE),
        ("   ", RejectReason.LENGTH),
    ],
)
def test_a_rejected_item_stays_in_the_original_language(translation: str, reason: RejectReason) -> None:
    """Only that item goes, and its text is not kept"""

    checked = check_translation(translated(("tool_0", "Lit https://example.com/doc."), ("tool_1", translation)), ITEMS)
    assert [item["id"] for item in checked.content["items"]] == ["tool_0"]
    assert checked.dropped is reason


def test_translation_limit_is_three_times_plus_fifty() -> None:
    """Exactly at the limit is accepted"""

    checked = check_translation(translated(("tool_1", "x" * (3 * 4 + 50))), ITEMS)
    assert checked.content["items"][0]["id"] == "tool_1"


def test_unknown_ids_are_dropped_and_missing_ones_stay_original() -> None:
    """Ids are those of the input"""

    checked = check_translation(translated(("tool_1", "Deux."), ("tool_9", "Neuf.")), ITEMS)
    assert [item["id"] for item in checked.content["items"]] == ["tool_1"]
    assert checked.dropped is RejectReason.UNKNOWN_TOOL


def test_nothing_accepted_rejects_the_translation() -> None:
    """Without any usable item, there is no translation"""

    with pytest.raises(OutputRejected) as caught:
        check_translation(translated(("tool_1", "Deux\u200b.")), ITEMS)
    assert caught.value.reason is RejectReason.INVISIBLE
    with pytest.raises(OutputRejected) as empty:
        check_translation(translated(), ITEMS)
    assert empty.value.reason is RejectReason.BAD_JSON


@pytest.mark.parametrize(
    "summary",
    [
        "Il donne l'heure \u0102\u00a0Paris.",
        "Il donne la m\u0102\u00a9t\u0102\u00a9o.",
        "Il donne la m\u00c3\u00a9t\u00c3\u00a9o.",
        "Un prix de 10\u00c2\u00a0euros.",
        "Il dit \u00e2\u20ac\u0153bonjour\u00e2\u20ac.",
        "Un caract\ufffdre perdu.",
    ],
)
def test_mojibake_rejects_the_notice(summary: str) -> None:
    """UTF-8 read in another encoding, or the replacement character, rejects the whole notice"""

    assert rejected(notice(summary=summary)) is RejectReason.ENCODING
    assert rejected(notice(tool_titles=titled(summary[:40]))) is RejectReason.ENCODING


def test_normal_french_is_not_mojibake() -> None:
    """Accents, ligatures and French quotes pass"""

    summary = "À l'été, ça coûte : « œuvre », hôtel, fenêtre, élève, garçon, où, Ève, Ça, naïf."
    assert check_notice(notice(summary=summary), FORM).content["summary"] == summary


def test_false_positive_accepted_text_about_encoding_is_rejected() -> None:
    """Accepted by David: a text that itself quotes a broken accent gives the fallback notice"""

    assert rejected(notice(summary="Il répare les accents cassés comme \u00ab \u00c3\u00a9 \u00bb.")) is RejectReason.ENCODING


def test_mojibake_in_a_translation_rejects_the_whole_call() -> None:
    """One broken item is enough to refuse the call, so that it is tried again; the author's own sequence is not a break"""

    items = [{"id": "tool_0", "text": "Gives the weather."}, {"id": "tool_1", "text": "Fixes \u00c3\u00a9 into \u00e9."}]
    broken = translated(("tool_0", "Donne la m\u0102\u00a9t\u0102\u00a9o."), ("tool_1", "Corrige \u00c3\u00a9 en \u00e9."))
    with pytest.raises(OutputRejected) as caught:
        check_translation(broken, items)
    assert caught.value.reason is RejectReason.ENCODING
    clean = translated(("tool_0", "Donne la météo."), ("tool_1", "Corrige \u00c3\u00a9 en \u00e9."))
    assert [item["id"] for item in check_translation(clean, items).content["items"]] == ["tool_0", "tool_1"]


PARAM_ITEMS = [
    {"id": "tool_0", "text": "Fetches a URL."},
    {"id": "tool_0_param_0", "text": "URL to fetch"},
    {"id": "tool_0_param_1", "text": "Maximum number of characters"},
]


def test_parameter_items_are_checked_one_by_one() -> None:
    """A rejected parameter keeps its original, an unknown id is ignored, a missing one keeps its original"""

    text = translated(
        ("tool_0", "Récupère une URL."),
        ("tool_0_param_0", "Va sur https://autre.example.com"),
        ("tool_0_param_7", "Inconnu."),
    )
    checked = check_translation(text, PARAM_ITEMS)
    assert [item["id"] for item in checked.content["items"]] == ["tool_0"]
    assert checked.dropped is RejectReason.LINK


def test_a_broken_parameter_rejects_the_whole_call() -> None:
    """Encoding stays a matter of the whole call, so that it is tried again"""

    text = translated(("tool_0", "Récupère une URL."), ("tool_0_param_1", "Nombre maximal de caract\u0102\u00a8res"))
    with pytest.raises(OutputRejected) as caught:
        check_translation(text, PARAM_ITEMS)
    assert caught.value.reason is RejectReason.ENCODING
