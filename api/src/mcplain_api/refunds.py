"""The one table that tells, for each failure code, whether the token of the analysis is given back or kept"""

from enum import StrEnum
from typing import Any

from mcplain.models import AnalysisStatus

from mcplain_api.db import AnalysisState
from mcplain_api.outcomes import FETCH_ERROR


class Refund(StrEnum):
    """Class that tells who caused a failure: MCPlain gives the token back, the link keeps it"""

    GIVE_BACK = "give_back"
    KEEP = "keep"


GIVE_BACK = Refund.GIVE_BACK
KEEP = Refund.KEEP

REFUND_BY_CODE: dict[str, Refund] = {
    "internal_error": GIVE_BACK,
    "interrupted": GIVE_BACK,
    "atelier_timeout": GIVE_BACK,
    "atelier_invalid_result": GIVE_BACK,
    "atelier_error": GIVE_BACK,
    "fetch.timeout": GIVE_BACK,
    "fetch.network_error": GIVE_BACK,
    "fetch.http_error": GIVE_BACK,
    "fetch.github_rate_limited": GIVE_BACK,
    "fetch.unexpected_response": GIVE_BACK,
    "fetch.invalid_json": GIVE_BACK,
    "fetch.integrity_missing": GIVE_BACK,
    "fetch.integrity_mismatch": GIVE_BACK,
    "fetch.not_found": KEEP,
    "fetch.npm_not_found": KEEP,
    "fetch.pypi_not_found": KEEP,
    "fetch.github_repo_not_found": KEEP,
    "fetch.github_ref_not_found": KEEP,
    "fetch.pypi_no_files": KEEP,
    "fetch.too_large": KEEP,
    "fetch.host_not_allowed": KEEP,
    "fetch.insecure_url": KEEP,
    "fetch.bad_redirect": KEEP,
    "fetch.too_many_redirects": KEEP,
    "analyze.subdir_not_found": KEEP,
    "analyze.not_a_directory": KEEP,
    "analyze.job_invalid": GIVE_BACK,
    "analyze.job_version_mismatch": GIVE_BACK,
    "analyze.archive_mismatch": GIVE_BACK,
    "archive.absolute_path": KEEP,
    "archive.bad_name": KEEP,
    "archive.compression_ratio": KEEP,
    "archive.corrupted": KEEP,
    "archive.duplicate_entry": KEEP,
    "archive.encrypted": KEEP,
    "archive.file_too_large": KEEP,
    "archive.invalid_layout": KEEP,
    "archive.link": KEEP,
    "archive.path_traversal": KEEP,
    "archive.special_file": KEEP,
    "archive.too_large": KEEP,
    "archive.too_many_files": KEEP,
    "archive.unknown_format": KEEP,
    "input.control_characters": KEEP,
    "input.credentials_in_url": KEEP,
    "input.empty": KEEP,
    "input.invalid_npm_name": KEEP,
    "input.invalid_npm_version": KEEP,
    "input.invalid_owner": KEEP,
    "input.invalid_path": KEEP,
    "input.invalid_pypi_name": KEEP,
    "input.invalid_pypi_version": KEEP,
    "input.invalid_reference": KEEP,
    "input.invalid_repository": KEEP,
    "input.invalid_selection": KEEP,
    "input.missing_package": KEEP,
    "input.missing_reference": KEEP,
    "input.missing_repository": KEEP,
    "input.npm_not_registry": KEEP,
    "input.path_traversal": KEEP,
    "input.pypi_extras_unsupported": KEEP,
    "input.reference_not_found": KEEP,
    "input.too_long": KEEP,
    "input.unexpected_arguments": KEEP,
    "input.unexpected_url_parts": KEEP,
    "input.unrecognized": KEEP,
    "input.unsupported_github_path": KEEP,
    "input.unsupported_host": KEEP,
    "input.unsupported_scheme": KEEP,
    "input.version_range_unsupported": KEEP,
}


def refund_of(code: str | None) -> Refund:
    """Return what the table says for a code; a code missing from the table gives the token back"""

    if code is None:
        return GIVE_BACK
    return REFUND_BY_CODE.get(code, GIVE_BACK)


def failure_code(error_code: str | None, result: dict[str, Any] | None) -> str | None:
    """Return the code that decides a failure: the engine code of a download error, otherwise the failure code"""

    if error_code != FETCH_ERROR:
        return error_code
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return str(error["code"])
    return None


def gives_back(state: str, error_code: str | None, result: dict[str, Any] | None, from_cache: bool) -> bool:
    """Tell whether a finished analysis gives its token back: cache, list of several servers, or a failure of MCPlain"""

    if state == AnalysisState.FAILED.value:
        return refund_of(failure_code(error_code, result)) is GIVE_BACK
    if from_cache:
        return True
    if isinstance(result, dict) and result.get("status") == AnalysisStatus.MULTIPLE_SERVERS.value:
        return True
    return False
