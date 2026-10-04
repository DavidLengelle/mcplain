"""Safe reading of project manifests as plain data"""

import json
import re
import tomllib
from configparser import ConfigParser
from configparser import Error as ConfigError
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 1024 * 1024
REQUIREMENT_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def read_text(path: Path) -> str | None:
    """Read a small text file, decoding invalid bytes as replacement characters"""

    try:
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def load_json_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON object, or None when the file is missing or invalid"""

    text = read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        return data
    return None


def load_toml(path: Path) -> dict[str, Any] | None:
    """Read a TOML document, or None when the file is missing or invalid"""

    text = read_text(path)
    if text is None:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


def load_setup_cfg(path: Path) -> ConfigParser | None:
    """Read a setup.cfg file without interpolation"""

    text = read_text(path)
    if text is None:
        return None
    parser = ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except ConfigError:
        return None
    return parser


def table(data: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    """Walk nested dictionaries and return an empty one when a level is missing"""

    current: Any = data or {}
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    if isinstance(current, dict):
        return current
    return {}


def requirement_name(spec: str) -> str | None:
    """Return the normalized project name at the start of a PEP 508 requirement"""

    match = REQUIREMENT_NAME_PATTERN.match(spec)
    if match is None:
        return None
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def string_list(value: Any) -> list[str]:
    """Return the strings of a list value, ignoring anything else"""

    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []
