"""Language adapters, one per supported language"""

from mcplain.adapters.base import Adapter
from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.config import DEFAULT_LIMITS, Limits

ADAPTERS: dict[str, type[Adapter]] = {
    "python": PythonAdapter,
    "javascript": JavaScriptAdapter,
    "typescript": JavaScriptAdapter,
}


def adapter_for(language: str, limits: Limits = DEFAULT_LIMITS) -> Adapter | None:
    """Return the adapter for a language, or None when it is not supported"""

    adapter_class = ADAPTERS.get(language)
    if adapter_class is None:
        return None
    return adapter_class(limits)
