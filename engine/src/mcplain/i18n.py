"""User-facing messages loaded from the locale files"""

import json
from functools import cache
from importlib.resources import files

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "fr")
DEFAULT_LANGUAGE = "en"


@cache
def load_catalog(language: str) -> dict[str, str]:
    """Read the messages of one language"""

    text = files("mcplain").joinpath("locales", f"{language}.json").read_text(encoding="utf-8")
    data = json.loads(text)
    return {str(key): str(value) for key, value in data.items()}


class Translator:
    """Class that returns messages in one language, falling back to English"""

    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        """Load the catalogs of the chosen language and of English"""

        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE
        self.language = language
        self._catalog = load_catalog(language)
        self._fallback = load_catalog(DEFAULT_LANGUAGE)

    def has(self, key: str) -> bool:
        """Tell whether a message exists for a key"""

        return key in self._catalog or key in self._fallback

    def __call__(self, key: str, **params: object) -> str:
        """Return the message for a key with its parameters filled in"""

        template = self._catalog.get(key) or self._fallback.get(key)
        if template is None:
            return key
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return template
