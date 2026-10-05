"""Gray results of failed analyses: every failed analysis carries a gray verdict and the code of its reason"""

from typing import Any

from mcplain.analyze import error_result
from mcplain.errors import McplainError
from mcplain.models import AnalysisResult, AnalyzedSource, VerdictColor

FETCH_ERROR = "fetch_error"
INTERNAL_ERROR = "internal_error"
INTERRUPTED = "interrupted"
JOB_PREFIX = "job."
FAILURE_CODES: frozenset[str] = frozenset(
    {
        FETCH_ERROR,
        INTERNAL_ERROR,
        INTERRUPTED,
        "atelier_timeout",
        "atelier_invalid_result",
        "atelier_error",
    }
)


def failure_result(
    error_code: str,
    detail_code: str | None = None,
    params: dict[str, str] | None = None,
    source: AnalyzedSource | None = None,
) -> AnalysisResult:
    """Build the gray result of a failed analysis; detail_code is the engine code of a download error"""

    code = detail_code or JOB_PREFIX + error_code
    return error_result(McplainError(code, **(params or {})), source)


def stored_failure(error_code: str | None, result: dict[str, Any] | None) -> dict[str, Any]:
    """Return the stored result of a failed analysis, or a gray one when it is missing or not gray"""

    if result is not None:
        try:
            parsed = AnalysisResult.model_validate(result)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.verdict.color is VerdictColor.GRAY:
            return result
    return failure_result(error_code or INTERNAL_ERROR).model_dump(mode="json")
