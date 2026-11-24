"""Tests of session 9c-2 on the running stack: the dashboard routes through the real relay, the low balance mail, the actions"""

import json
import os
import time
import uuid
from collections.abc import Iterator

import httpx
import pytest
from docker import DockerClient
from test_admin import admin_routes
from test_compose import DEFAULT_MAILPIT_PORT, MAILPIT_PORT_VARIABLE, compose_container, compose_port, postgres_lines
from test_compose_admin import Browser, accounts, browsers, client, make_account, new_browser, turn_on_two_factor

pytestmark = pytest.mark.docker

DIALS: tuple[str, ...] = ("spend", "ai", "analyses", "refusals", "accounts")
NOTE = "stack test 9c-2"
MAIL_WAIT_SECONDS = 120
ANALYSIS_WAIT_SECONDS = 120
BALANCE_SUBJECT = "solde estimé"
FIXTURES = (accounts, browsers, client)


def admin_browser(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> tuple[Browser, str]:
    """Return a browser signed in as an admin with its second factor, and its email"""

    browser = new_browser(browsers)
    email = make_account(client, browser, "admin", accounts)
    turn_on_two_factor(browser)
    return browser, email


def call(browser: Browser, method: str, path: str, origin: str | None = "site") -> httpx.Response:
    """Call one admin route through the website with a small JSON body"""

    if method == "GET":
        return browser.send(method, path, origin=origin, params={"days": "7", "email": "nobody@example.com"})
    return browser.send(method, path, origin=origin, json={})


def test_every_admin_route_is_closed_through_the_relay(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """Anonymous, normal account, bench account and admin without second factor: 403 on every admin route, new ones included"""

    routes = admin_routes()
    assert ("GET", "/api/admin/dashboard/spend") in routes
    assert ("POST", "/api/admin/credit") in routes
    anonymous = new_browser(browsers)
    user = new_browser(browsers)
    make_account(client, user, "user", accounts)
    bench = new_browser(browsers)
    make_account(client, bench, "bench", accounts)
    halfway = new_browser(browsers)
    make_account(client, halfway, "admin", accounts)
    for name, browser in (("anonymous", anonymous), ("user", user), ("bench", bench), ("admin without second factor", halfway)):
        for method, path in routes:
            answer = call(browser, method, path)
            assert answer.status_code == 403, (name, method, path, answer.text)
            assert answer.json()["error"]["code"] == "api.admin_required", (name, method, path)
    admin, _ = admin_browser(client, accounts, browsers)
    for method, path in routes:
        if method == "GET":
            continue
        for origin in (None, "https://attacker.invalid"):
            answer = call(admin, method, path, origin)
            assert answer.status_code == 403, (method, path, origin)
            assert answer.json()["error"]["code"] == "api.origin_refused", (method, path, origin)


def test_the_dials_answer_through_the_relay_with_totals_only(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """Each dial answers for 7 and 30 days, refuses another period, and never names the accounts it counts"""

    admin, email = admin_browser(client, accounts, browsers)
    admin_id = postgres_lines(client, f"SELECT id FROM auth.\"user\" WHERE email = '{email}';")[0]
    for name in DIALS:
        for days in ("7", "30"):
            answer = admin.send("GET", f"/api/admin/dashboard/{name}", params={"days": days})
            assert answer.status_code == 200, (name, answer.text)
            assert answer.headers["cache-control"] == "no-store"
            for secret in (email, admin_id, "req_"):
                assert secret not in answer.text, (name, secret)
        assert admin.send("GET", f"/api/admin/dashboard/{name}", params={"days": "5"}).status_code == 400
    created = admin.send("GET", "/api/admin/dashboard/accounts", params={"days": "7"}).json()
    assert created["per_day"][-1]["count"] >= 1
    assert created["total"] >= 1


@pytest.fixture
def ledger(client: DockerClient) -> Iterator[None]:
    """Keep the state of the low balance mail, then remove the entries and journal lines of the test and give the state back"""

    before = postgres_lines(client, "SELECT coalesce(sent_at::text, '') FROM balance_alert WHERE id = 1;")
    yield
    entries = f"SELECT id::text FROM credit_entries WHERE note = '{NOTE}'"
    postgres_lines(client, f"DELETE FROM admin_actions WHERE target_id IN ({entries}); DELETE FROM credit_entries WHERE note = '{NOTE}';")
    if before and before[0]:
        postgres_lines(client, f"UPDATE balance_alert SET sent_at = '{before[0]}' WHERE id = 1;")
    else:
        postgres_lines(client, "UPDATE balance_alert SET sent_at = NULL WHERE id = 1;")
    address = f"http://127.0.0.1:{compose_port(MAILPIT_PORT_VARIABLE, DEFAULT_MAILPIT_PORT)}"
    with httpx.Client(base_url=address, timeout=30, trust_env=False) as mailpit:
        found = mailpit.get("/api/v1/search", params={"query": f'subject:"{BALANCE_SUBJECT}"', "limit": "50"})
        identifiers = [message["ID"] for message in found.json().get("messages", [])]
        if identifiers:
            mailpit.request("DELETE", "/api/v1/messages", json={"IDs": identifiers}).raise_for_status()


def admin_address_is_set(client: DockerClient) -> bool:
    """Tell whether the postman has an admin address, without printing it"""

    exit_code, _ = compose_container(client, "facteur").exec_run(["sh", "-c", 'test -n "$MCPLAIN_ADMIN_EMAIL"'])
    return exit_code == 0


def test_a_low_statement_makes_the_postman_mail_once(client: DockerClient, accounts: list[str], browsers: list[Browser], ledger: None) -> None:
    """A statement under 2 dollars: the postman, with its own role, marks the mail sent once it went through Mailpit"""

    if not admin_address_is_set(client):
        if os.environ.get("CI") == "true":
            pytest.fail("the CI must give the postman a test address: the low balance mail is never skipped there")
        pytest.skip("set MCPLAIN_ADMIN_EMAIL in .env to check the low balance mail")
    postgres_lines(client, "UPDATE balance_alert SET sent_at = NULL WHERE id = 1;")
    admin, _ = admin_browser(client, accounts, browsers)
    added = admin.send("POST", "/api/admin/credit", json={"kind": "statement", "amount_usd": 0.5, "note": NOTE})
    assert added.status_code == 201, added.text
    assert added.json()["low"] is True
    deadline = time.monotonic() + MAIL_WAIT_SECONDS
    while postgres_lines(client, "SELECT sent_at IS NOT NULL FROM balance_alert WHERE id = 1;") != ["t"]:
        assert time.monotonic() < deadline, "the postman did not send the low balance mail"
        time.sleep(2)
    view = admin.send("GET", "/api/admin/credit").json()
    assert view["alert_sent_at"] is not None
    address = f"http://127.0.0.1:{compose_port(MAILPIT_PORT_VARIABLE, DEFAULT_MAILPIT_PORT)}"
    with httpx.Client(base_url=address, timeout=30, trust_env=False) as mailpit:
        found = mailpit.get("/api/v1/search", params={"query": f'subject:"{BALANCE_SUBJECT}"', "limit": "50"}).json()
    assert found["messages"], "no low balance mail in Mailpit"
    topped = admin.send("POST", "/api/admin/credit", json={"kind": "top_up", "amount_usd": 5, "note": NOTE})
    assert topped.json()["alert_sent_at"] is None


def test_asking_a_notice_again_is_refused_while_the_ai_is_off(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """The stack of the tests has no key: the writer is cut off, so the admin cannot queue a text either"""

    text_id = str(uuid.uuid4())
    postgres_lines(
        client,
        "INSERT INTO ai_texts (id, kind, lang, hash, prompt_version, model, status, reject_reason, analysis_id, created_at, updated_at) "
        f"VALUES ('{text_id}', 'notice', 'fr', '{uuid.uuid4().hex * 2}', 'stack-9c-2', 'stack', 'rejected', 'link', NULL, now(), now());",
    )
    try:
        admin, _ = admin_browser(client, accounts, browsers)
        answer = admin.send("POST", f"/api/admin/texts/{text_id}/retry", json={})
        assert (answer.status_code, answer.json()["error"]["code"]) == (409, "api.ai_disabled")
        assert postgres_lines(client, f"SELECT status FROM ai_texts WHERE id = '{text_id}';") == ["rejected"]
        assert postgres_lines(client, f"SELECT count(*) FROM admin_actions WHERE target_id = '{text_id}';") == ["0"]
    finally:
        postgres_lines(client, f"DELETE FROM ai_texts WHERE id = '{text_id}';")


def test_a_rerun_goes_through_the_real_dispatcher_and_into_the_journal(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """The rerun skips the cache and is processed by the running dispatcher; an input it refuses fails without any download"""

    target = str(uuid.uuid4())
    postgres_lines(
        client,
        "INSERT INTO analyses (id, input_raw, state, created_at, finished_at, from_cache, cache_only, ignore_cache) "
        f"VALUES ('{target}', 'this is not an mcp server', 'failed', now(), now(), false, false, false);",
    )
    created = None
    try:
        admin, _ = admin_browser(client, accounts, browsers)
        answer = admin.send("POST", f"/api/admin/analyses/{target}/rerun", json={})
        assert answer.status_code == 202, answer.text
        created = answer.json()["id"]
        deadline = time.monotonic() + ANALYSIS_WAIT_SECONDS
        while True:
            state = postgres_lines(client, f"SELECT state, ignore_cache, coalesce(error_code, '') FROM analyses WHERE id = '{created}';")
            if state and state[0].split("|")[0] in ("done", "failed"):
                break
            assert time.monotonic() < deadline, "the dispatcher did not process the rerun"
            time.sleep(1)
        assert state[0] == "failed|t|fetch_error"
        journal = admin.send("GET", "/api/admin/journal").json()["lines"]
        assert {"action": "analysis_rerun", "target_kind": "analysis", "target_id": created} in [
            {key: line[key] for key in ("action", "target_kind", "target_id")} for line in journal
        ]
        assert json.dumps(journal).count(created) == 1
    finally:
        postgres_lines(client, f"DELETE FROM analyses WHERE id = '{target}';")
        if created is not None:
            postgres_lines(client, f"DELETE FROM admin_actions WHERE target_id = '{created}'; DELETE FROM analyses WHERE id = '{created}';")
