"""Who is signed in: the API hands the session cookie to the counter (guichet) and keeps its answer for 30 seconds"""

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie

import httpx

from mcplain_api.settings import Settings

SESSION_PATH = "/api/auth/get-session"
COOKIE_PREFIXES: tuple[str, ...] = ("mcplain.", "__Secure-mcplain.")
CACHE_SECONDS = 30.0
CACHE_MAX_ENTRIES = 10_000
TIMEOUT_SECONDS = 3.0
ROLE_ADMIN = "admin"
ROLE_USER = "user"


@dataclass(frozen=True)
class CurrentUser:
    """Class that holds what the API needs to know about a signed-in visitor"""

    id: str
    email_verified: bool
    role: str


def account_cookies(cookie_header: str | None) -> str | None:
    """Keep only the cookies of the accounts, in a stable order, or None when there is none"""

    if not cookie_header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except CookieError:
        return None
    kept = sorted(f"{name}={morsel.coded_value}" for name, morsel in jar.items() if name.startswith(COOKIE_PREFIXES))
    if not kept:
        return None
    return "; ".join(kept)


def user_from_answer(body: object) -> CurrentUser | None:
    """Read the user of a get-session answer; anything unexpected means nobody"""

    if not isinstance(body, dict):
        return None
    user = body.get("user")
    if not isinstance(user, dict):
        return None
    identifier = user.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    role = ROLE_USER
    if user.get("role") == ROLE_ADMIN:
        role = ROLE_ADMIN
    return CurrentUser(id=identifier, email_verified=user.get("emailVerified") is True, role=role)


class SessionReader:
    """Class that asks the counter who owns a session cookie, with a short cache keyed by the fingerprint of the cookie"""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Keep the address of the counter, an HTTP client without proxy nor redirect, and an empty cache"""

        self.url = settings.guichet_url.rstrip("/") + SESSION_PATH
        if client is None:
            client = httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False, trust_env=False)
        self.client = client
        self.clock = clock
        self.cache: dict[str, tuple[float, CurrentUser | None]] = {}

    def current_user(self, cookie_header: str | None) -> CurrentUser | None:
        """Return the signed-in user of a Cookie header, or None; an error of the counter means nobody and is not kept"""

        cookies = account_cookies(cookie_header)
        if cookies is None:
            return None
        key = hashlib.sha256(cookies.encode("utf-8")).hexdigest()
        now = self.clock()
        cached = self.cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            response = self.client.get(self.url, headers={"Cookie": cookies, "Accept": "application/json"})
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            user = user_from_answer(response.json())
        except ValueError:
            return None
        self.remember(key, now, user)
        return user

    def remember(self, key: str, now: float, user: CurrentUser | None) -> None:
        """Keep an answer for 30 seconds, dropping the expired ones, then the oldest, when the cache is full"""

        if len(self.cache) >= CACHE_MAX_ENTRIES:
            self.cache = {name: item for name, item in self.cache.items() if item[0] > now}
        if len(self.cache) >= CACHE_MAX_ENTRIES:
            del self.cache[next(iter(self.cache))]
        self.cache[key] = (now + CACHE_SECONDS, user)
