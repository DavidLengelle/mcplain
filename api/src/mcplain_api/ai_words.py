"""The only list of reassuring words the AI may never write; accents count, so "sur" is not "sûr\""""

import re
import unicodedata

FORBIDDEN_WORDS: tuple[str, ...] = (
    "sûr",
    "sûre",
    "sûrs",
    "sûres",
    "sécurisé",
    "sécurisée",
    "sécurisés",
    "sécurisées",
    "sans danger",
    "sans risque",
    "aucun risque",
    "inoffensif",
    "inoffensifs",
    "inoffensive",
    "inoffensives",
    "fiable",
    "fiables",
    "certifié",
    "certifiée",
    "certifiés",
    "certifiées",
    "vérifié",
    "vérifiée",
    "vérifiés",
    "vérifiées",
    "garanti",
    "garantie",
    "garantis",
    "garanties",
    "officiel",
    "officielle",
    "officiels",
    "officielles",
    "de confiance",
    "safe",
    "secure",
    "harmless",
    "risk-free",
    "no risk",
    "trusted",
    "trustworthy",
    "certified",
    "verified",
    "guaranteed",
    "official",
)
FORBIDDEN_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in FORBIDDEN_WORDS) + r")(?!\w)",
    re.IGNORECASE,
)


def has_forbidden_word(text: str) -> bool:
    """Tell whether a text holds a reassuring word, as a whole word, in any case, with its exact accents"""

    return FORBIDDEN_PATTERN.search(unicodedata.normalize("NFC", text)) is not None
