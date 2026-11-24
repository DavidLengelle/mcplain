"""The accounts desk of the admin: the API asks the internal routes of the counter (guichet) to find, ban and unban an account"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx

from mcplain_api.settings import Settings

ACCOUNTS_PATH = "/internal/accounts"
BAN_PATH = "/internal/accounts/ban"
UNBAN_PATH = "/internal/accounts/unban"
CREATED_PER_DAY_PATH = "/internal/accounts/created-per-day"
DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMEOUT_SECONDS = 5.0
EMAIL_MAX_CHARS = 320
BAN_REASON_MAX_CHARS = 200
ACCOUNT_FIELDS: tuple[str, ...] = (
    "id",
    "email",
    "role",
    "email_verified",
    "two_factor",
    "created_at",
    "banned_at",
    "ban_reason",
)


class DeskOutcome(StrEnum):
    """Class that lists how the counter answered a change of an account"""

    DONE = "done"
    NOT_FOUND = "not_found"
    IS_ADMIN = "is_admin"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Lookup:
    """Class that holds the answer of a search: the account found, or why there is none"""

    outcome: DeskOutcome
    account: dict[str, Any] | None = None


class AccountDesk(Protocol):
    """Class protocol for the accounts desk: the counter in production, a fake in the tests"""

    def find(self, email: str) -> Lookup:
        """Return the account of one exact email address"""

    def ban(self, user_id: str, reason: str | None) -> DeskOutcome:
        """Ban an account and kill its sessions"""

    def unban(self, user_id: str) -> DeskOutcome:
        """Lift the ban of an account"""

    def created_per_day(self, days: int) -> dict[str, int] | None:
        """Return how many accounts were created on each UTC day, or None when the counter does not answer"""


def account_of(body: object) -> dict[str, Any] | None:
    """Keep only the known fields of an account answered by the counter, or None when the answer is strange"""

    if not isinstance(body, dict):
        return None
    account = body.get("account")
    if not isinstance(account, dict) or not isinstance(account.get("id"), str):
        return None
    return {name: account.get(name) for name in ACCOUNT_FIELDS}


def counts_of(body: object) -> dict[str, int] | None:
    """Keep only the dates and the numbers of the accounts created per day, or None when the answer is strange"""

    if not isinstance(body, dict) or not isinstance(body.get("days"), list):
        return None
    counts: dict[str, int] = {}
    for item in body["days"]:
        if not isinstance(item, dict):
            return None
        day = item.get("day")
        count = item.get("count")
        if not isinstance(day, str) or not DAY_PATTERN.fullmatch(day):
            return None
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return None
        counts[day] = count
    return counts


class GuichetDesk:
    """Class that reaches the internal account routes of the counter, on the back network, without proxy nor redirect"""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        """Keep the address of the counter and an HTTP client"""

        self.base = settings.guichet_url.rstrip("/")
        if client is None:
            client = httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False, trust_env=False)
        self.client = client

    def find(self, email: str) -> Lookup:
        """Ask the counter for the account of one exact email address"""

        try:
            response = self.client.get(self.base + ACCOUNTS_PATH, params={"email": email})
        except httpx.HTTPError:
            return Lookup(DeskOutcome.UNAVAILABLE)
        if response.status_code == 404:
            return Lookup(DeskOutcome.NOT_FOUND)
        if response.status_code != 200:
            return Lookup(DeskOutcome.UNAVAILABLE)
        try:
            account = account_of(response.json())
        except ValueError:
            return Lookup(DeskOutcome.UNAVAILABLE)
        if account is None:
            return Lookup(DeskOutcome.UNAVAILABLE)
        return Lookup(DeskOutcome.DONE, account)

    def change(self, path: str, body: dict[str, object]) -> DeskOutcome:
        """Post a change of an account to the counter and read its outcome"""

        try:
            response = self.client.post(self.base + path, json=body)
        except httpx.HTTPError:
            return DeskOutcome.UNAVAILABLE
        if response.status_code == 200:
            return DeskOutcome.DONE
        if response.status_code == 404:
            return DeskOutcome.NOT_FOUND
        if response.status_code == 409:
            return DeskOutcome.IS_ADMIN
        return DeskOutcome.UNAVAILABLE

    def ban(self, user_id: str, reason: str | None) -> DeskOutcome:
        """Ask the counter to ban an account and kill its sessions"""

        return self.change(BAN_PATH, {"user_id": user_id, "reason": reason})

    def unban(self, user_id: str) -> DeskOutcome:
        """Ask the counter to lift the ban of an account"""

        return self.change(UNBAN_PATH, {"user_id": user_id})

    def created_per_day(self, days: int) -> dict[str, int] | None:
        """Ask the counter how many accounts were created on each UTC day: dates and numbers only"""

        try:
            response = self.client.get(self.base + CREATED_PER_DAY_PATH, params={"days": str(days)})
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            return counts_of(response.json())
        except ValueError:
            return None
