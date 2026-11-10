"""ALTCHA proof of work, version 2 (PBKDF2/SHA-256): new challenges, and solutions accepted only once"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from altcha import Payload, create_challenge, verify_solution
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mcplain_api.db import AltchaUse
from mcplain_api.settings import Settings

ALGORITHM = "PBKDF2/SHA-256"
PAYLOAD_MAX_CHARS = 4096


def new_challenge(settings: Settings, moment: datetime) -> dict[str, Any] | None:
    """Return a signed challenge that expires after the configured lifetime, or None without a key"""

    if settings.altcha_hmac_key is None:
        return None
    expires_at = moment + timedelta(seconds=settings.altcha_lifetime_s)
    challenge = create_challenge(
        ALGORITHM,
        settings.altcha_cost,
        expires_at=expires_at,
        hmac_secret=settings.altcha_hmac_key.get_secret_value(),
    )
    return challenge.to_dict()


def signature_hash(payload: Payload) -> str | None:
    """Return the fingerprint of the signature of a solved challenge"""

    signature = payload.challenge.signature
    if not isinstance(signature, str) or not signature:
        return None
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def accept_solution(session: Session, settings: Settings, text: str | None, moment: datetime) -> bool:
    """Tell whether a solution is valid, signed, not expired and never used, then record it as used"""

    session.execute(delete(AltchaUse).where(AltchaUse.expires_at < moment))
    if settings.altcha_hmac_key is None or not text or len(text) > PAYLOAD_MAX_CHARS:
        return False
    result = verify_solution(text, settings.altcha_hmac_key.get_secret_value())
    if not result.verified:
        return False
    try:
        payload = Payload.from_base64(text)
    except (ValueError, KeyError, TypeError):
        return False
    fingerprint = signature_hash(payload)
    expires_at = payload.challenge.parameters.expires_at
    if fingerprint is None or not isinstance(expires_at, int):
        return False
    try:
        with session.begin_nested():
            session.add(AltchaUse(signature_hash=fingerprint, expires_at=datetime.fromtimestamp(expires_at, UTC)))
    except IntegrityError:
        return False
    return True
