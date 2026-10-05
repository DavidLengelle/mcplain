"""The invisible character ranges of the engine as JSON, the only list the website uses to show them"""

import json
import sys

from mcplain.adapters.common import INVISIBLE_RANGES

WEB_FILE = "web/src/lib/invisible-characters.json"


def codepoint_text(codepoint: int) -> str:
    """Return the U+XXXX form of a code point"""

    return f"U+{codepoint:04X}"


def invisible_ranges_json() -> str:
    """Return every invisible range with its family, in the order of INVISIBLE_RANGES"""

    document = [
        {"first": codepoint_text(low), "last": codepoint_text(high), "category": category.value}
        for low, high, category in INVISIBLE_RANGES
    ]
    return json.dumps(document, indent=2) + "\n"


def main() -> int:
    """Print the JSON document"""

    sys.stdout.write(invisible_ranges_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
