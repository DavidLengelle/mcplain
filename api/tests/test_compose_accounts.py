"""Tests that read compose.yaml: each secret of the accounts reaches one service only, and Mailpit stays in development"""

import re

from helpers import REPOSITORY, compose_services, uncommented

SECRET_OWNERS: dict[str, set[str]] = {
    "BETTER_AUTH_SECRET": {"guichet"},
    "MCPLAIN_ALTCHA_HMAC_KEY": {"api"},
    "MCPLAIN_SMTP_USER": {"facteur"},
    "MCPLAIN_SMTP_PASSWORD": {"facteur"},
    "MCPLAIN_SMTP_HOST": {"facteur"},
    "MCPLAIN_ANTHROPIC_API_KEY": {"redacteur"},
    "MCPLAIN_GUICHET_DB_PASSWORD": {"guichet", "migrate"},
    "MCPLAIN_FACTEUR_DB_PASSWORD": {"facteur", "migrate"},
    "MCPLAIN_APP_DB_PASSWORD": {"api", "dispatcher", "redacteur", "migrate"},
    "POSTGRES_PASSWORD": {"postgres", "migrate"},
}
CLOSED_SERVICES: tuple[str, ...] = ("guichet", "facteur", "migrate", "mailpit")
DEVELOPMENT_ONLY = "mailpit"
VARIABLE = re.compile(r"\$\{([A-Z0-9_]+)")


def variables_of(block: str) -> set[str]:
    """Return every variable of .env that a service block reads"""

    return set(VARIABLE.findall(uncommented(block)))


def test_each_secret_reaches_its_services_only() -> None:
    """BETTER_AUTH_SECRET to the counter, SMTP to the postman, the ALTCHA key to the API, the Anthropic key to the writer"""

    services = compose_services()
    for secret, owners in SECRET_OWNERS.items():
        readers = {name for name, block in services.items() if secret in variables_of(block) or secret in uncommented(block)}
        assert readers == owners, secret


def test_the_website_has_no_secret_and_no_database() -> None:
    """The website reads no variable of .env except its port, and never names PostgreSQL"""

    block = uncommented(compose_services()["web"])
    assert variables_of(block) == {"MCPLAIN_WEB_PORT"}
    assert "postgres" not in block.lower()
    assert "SECRET" not in block and "PASSWORD" not in block


def test_mailpit_is_in_the_dev_profile_only() -> None:
    """Mailpit has the dev profile, its port is bound to 127.0.0.1, it is pinned by digest, and no other service has a profile dev"""

    services = compose_services()
    block = uncommented(services[DEVELOPMENT_ONLY])
    assert re.search(r"^    profiles:\n      - dev$", block, re.MULTILINE)
    assert "@sha256:" in block
    ports = re.findall(r'^      - "([^"]+)"$', block, re.MULTILINE)
    assert ports and all(port.startswith("127.0.0.1:") for port in ports)
    for name, other in services.items():
        if name != DEVELOPMENT_ONLY:
            assert "- dev" not in uncommented(other), name
    text = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert len(re.findall(r"^  mailpit:$", text, re.MULTILINE)) == 1
    assert text.count("axllent/mailpit") == 1


def test_new_services_are_closed() -> None:
    """The counter, the postman, the migrations and Mailpit: read-only, no capability, no new privilege, no socket, no mount"""

    services = compose_services()
    for name in CLOSED_SERVICES:
        block = uncommented(services[name])
        assert "read_only: true" in block, name
        assert "cap_drop:\n      - ALL" in block, name
        assert "no-new-privileges:true" in block, name
        assert "docker.sock" not in block, name
        assert "volumes:" not in block, name
        assert "user:" in block or name == "migrate", name


def test_the_networks_of_the_new_services() -> None:
    """The counter is on front and back; the postman and the migrations on back only"""

    services = compose_services()

    def networks(name: str) -> list[str]:
        block = uncommented(services[name])
        lines = block.split("    networks:\n", 1)[1].splitlines()
        found = []
        for line in lines:
            if not line.startswith("      - "):
                break
            found.append(line.removeprefix("      - "))
        return found

    assert networks("guichet") == ["front", "back"]
    assert networks("facteur") == ["back"]
    assert networks("migrate") == ["back"]
    assert networks("web") == ["front"]


def test_the_owner_password_stays_in_the_migrations() -> None:
    """The API, the dispatcher and the writer connect with mcplain_app, never with the owner of the database"""

    services = compose_services()
    for name in ("api", "dispatcher", "redacteur"):
        block = uncommented(services[name])
        assert "mcplain_app:${MCPLAIN_APP_DB_PASSWORD" in block, name
        assert "POSTGRES_PASSWORD" not in block, name
    assert "mcplain_guichet:${MCPLAIN_GUICHET_DB_PASSWORD" in services["guichet"]
    assert "mcplain_facteur:${MCPLAIN_FACTEUR_DB_PASSWORD" in services["facteur"]


def test_no_github_file_holds_a_real_secret() -> None:
    """The files of .github/ name no secret of the accounts, and their test values say test only"""

    for path in (REPOSITORY / ".github").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            for name in ("BETTER_AUTH_SECRET", "MCPLAIN_ALTCHA_HMAC_KEY", "PASSWORD"):
                if name in line and ":" in line:
                    assert "test-only" in line or "secrets." not in line, (path.name, line)
        assert "secrets.BETTER_AUTH" not in text
        assert "secrets.MCPLAIN_SMTP" not in text
