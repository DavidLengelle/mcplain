"""Tests of the guards around the AI: settings, where the key goes, where it never goes, and who may ask for a text"""

import logging
import re
import socket
from pathlib import Path

import pytest
from helpers import make_settings, report, tool_report
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from mcplain_api.ai_client import build_body, call_api
from mcplain_api.ai_logging import SecretFilter
from mcplain_api.db import AiAdminAlert, AiState, AiText, Analysis, Base, make_engine, make_sessions
from mcplain_api.redacteur import NO_KEY, Redacteur
from mcplain_api.settings import Settings

REPOSITORY = Path(__file__).resolve().parents[2]
SERVICE_LINE = re.compile(r"^  ([a-z_]+):\s*$")
KEY_ONLY_SERVICE = "redacteur"
EVERY_OTHER_SERVICE: tuple[str, ...] = ("postgres", "api", "dispatcher", "web", "atelier")
CANARY_KEY = "sk-ant-test-CANARY"


def compose_services() -> dict[str, str]:
    """Return the text of every service of compose.yaml, cut at its two-space indented name"""

    services: dict[str, list[str]] = {}
    inside = False
    current = None
    for line in (REPOSITORY / "compose.yaml").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith(" "):
            inside = line == "services:"
            current = None
            continue
        match = SERVICE_LINE.match(line)
        if inside and match is not None:
            current = match.group(1)
            services[current] = []
        elif current is not None:
            services[current].append(line)
    return {name: "\n".join(lines) for name, lines in services.items()}


def uncommented(block: str) -> str:
    """Remove the comment lines of a service"""

    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every AI setting has its documented variable and default"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    for name in ("MCPLAIN_ANTHROPIC_API_KEY", "MCPLAIN_AI_DAILY_FUSE_USD", "MCPLAIN_AI_MONTHLY_BUDGET_USD"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.anthropic_api_key is None
    assert (settings.ai_model, settings.ai_effort, settings.ai_thinking) == ("claude-sonnet-5-5", "low", "between_tools")
    assert (settings.ai_max_tokens, settings.ai_translation_max_tokens) == (3500, 6000)
    assert (settings.ai_api_version, settings.ai_timeout_s) == ("2026-10-21", 60)
    assert (settings.ai_price_input_per_mtok, settings.ai_price_output_per_mtok) == (2, 10)
    assert (settings.ai_monthly_budget_usd, settings.daily_fuse()) == (10, 0.5)


def test_empty_values_from_compose_mean_no_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """compose passes empty variables: no key, and the fuse computed from the budget"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("MCPLAIN_ANTHROPIC_API_KEY", " ")
    monkeypatch.setenv("MCPLAIN_AI_DAILY_FUSE_USD", "")
    monkeypatch.setenv("MCPLAIN_AI_MONTHLY_BUDGET_USD", "40")
    settings = Settings()
    assert settings.anthropic_api_key is None
    assert settings.daily_fuse() == 2
    monkeypatch.setenv("MCPLAIN_AI_DAILY_FUSE_USD", "1.5")
    assert Settings().daily_fuse() == 1.5
    monkeypatch.setenv("MCPLAIN_AI_DAILY_FUSE_USD", "-1")
    with pytest.raises(ValidationError):
        Settings()


def test_the_model_name_is_written_only_in_the_settings() -> None:
    """Outside settings.py, the code reads the model from the settings"""

    for path in (REPOSITORY / "api" / "src").rglob("*.py"):
        if path.name != "settings.py":
            assert "claude-" not in path.read_text(encoding="utf-8"), path


def test_env_example_has_an_empty_key_and_the_warning() -> None:
    """The example holds no key, says where it must never go, and says what to change with the model"""

    text = (REPOSITORY / ".env.example").read_text(encoding="utf-8")
    assert "MCPLAIN_ANTHROPIC_API_KEY=\n" in text
    assert "never put this key in GitHub" in text
    assert "only exists on Claude Sonnet 5.5" in text


def test_env_file_is_ignored_by_git() -> None:
    """Git ignores .env"""

    assert (REPOSITORY / ".gitignore").read_text(encoding="utf-8").splitlines().count(".env") == 1


def test_only_the_writer_receives_the_key() -> None:
    """No other compose service receives a variable holding ANTHROPIC, and no service reads a whole env file"""

    services = compose_services()
    assert set(EVERY_OTHER_SERVICE) | {KEY_ONLY_SERVICE} <= set(services)
    for name in EVERY_OTHER_SERVICE:
        assert "ANTHROPIC" not in uncommented(services[name]).upper(), name
    assert "MCPLAIN_ANTHROPIC_API_KEY" in services[KEY_ONLY_SERVICE]
    for block in services.values():
        assert "env_file" not in block


def test_the_writer_container_is_closed() -> None:
    """The writer has no socket, no mount, no port, no root, no capability, and is on the back network only"""

    block = uncommented(compose_services()[KEY_ONLY_SERVICE])
    assert "docker.sock" not in block
    assert "volumes:" not in block
    assert "ports:" not in block
    assert "group_add" not in block
    assert 'user: "10002:10002"' in block
    assert "read_only: true" in block
    assert "- ALL" in block.split("cap_drop:")[1]
    assert "no-new-privileges:true" in block
    assert block.split("networks:")[1].split("read_only")[0].split() == ["-", "back"]
    assert "image: mcplain-api:dev" in block
    assert '["mcplain-redacteur"]' in block


def test_github_never_mentions_anthropic() -> None:
    """No file of .github holds the word, in any case"""

    files = [path for path in (REPOSITORY / ".github").rglob("*") if path.is_file()]
    assert files
    for path in files:
        assert "anthropic" not in path.read_text(encoding="utf-8").lower(), path


def test_the_bench_never_asks_for_a_text() -> None:
    """The code of bench never calls the notice or the translation routes"""

    files = [path for path in (REPOSITORY / "bench").glob("*.py")]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "/notice" not in text, path
        assert "/translation" not in text, path


def test_the_key_never_reaches_a_log_line() -> None:
    """The filter hides the key and anything shaped like a key, in the message, its arguments and its traceback"""

    record = logging.LogRecord("x", logging.ERROR, "x", 1, "key %s and %s", (CANARY_KEY, "sk-ant-other-Key_1"), None)
    record.exc_text = CANARY_KEY
    assert SecretFilter(CANARY_KEY).filter(record)
    assert record.getMessage() == "key [hidden] and [hidden]"
    assert record.exc_text is None


def test_a_real_call_fails_in_the_tests() -> None:
    """Without a simulated answer, a call to the API stops on the socket guard of the tests"""

    settings = make_settings(anthropic_api_key=CANARY_KEY)
    body = build_body(settings, "system", "message", 10)
    with pytest.raises(RuntimeError, match="network access is not allowed"):
        call_api(settings, body, sleep=lambda seconds: None)
    with pytest.raises(RuntimeError, match="network access is not allowed"):
        socket.create_connection(("api.anthropic.com", 443))


def test_no_key_means_disabled_and_no_call(respx_mock: object) -> None:
    """Without a key, the writer records disabled, a waiting text is disabled, and no request leaves"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions: sessionmaker = make_sessions(engine)
    with sessions.begin() as session:
        session.add(Analysis(input_raw="uvx demo", state="done", result=report([tool_report("get_time")])))
        session.add(AiText(kind="notice", lang="fr", hash="0" * 64, prompt_version="notice-v1", model="m", status="pending"))
    redacteur = Redacteur(make_settings(), sessions, sleep=lambda seconds: None)
    redacteur.start()
    assert redacteur.run_once() is False
    with sessions() as session:
        assert session.get(AiState, 1).disabled_reason == NO_KEY
        assert session.query(AiText).one().status == "disabled"
        assert session.query(AiAdminAlert).count() == 0
    assert respx_mock.calls.call_count == 0


def test_the_engine_does_not_read_any_ai_output() -> None:
    """The engine and the dispatcher never import the writer's modules: no AI output can reach a verdict or their cache"""

    roots = [REPOSITORY / "engine" / "src", REPOSITORY / "api" / "src" / "mcplain_api" / "dispatcher.py"]
    roots.append(REPOSITORY / "api" / "src" / "mcplain_api" / "launcher.py")
    pattern = re.compile(r"\bai_(?:texts?|view|check|client|form|prompts)\b|AiText|redacteur")
    for root in roots:
        paths = [root]
        if root.is_dir():
            paths = list(root.rglob("*.py"))
        for path in paths:
            assert pattern.search(path.read_text(encoding="utf-8")) is None, path


def test_the_smoke_script_never_shows_the_key() -> None:
    """The script only tests that the line is filled; it never loads .env, nor prints a variable holding the key"""

    text = (REPOSITORY / "scripts" / "notice-smoke.sh").read_text(encoding="utf-8")
    assert "grep -Eq '^MCPLAIN_ANTHROPIC_API_KEY=.+' .env" in text
    for shown in ("cat .env", ". .env", "source .env", "$MCPLAIN_ANTHROPIC_API_KEY", "set -x", "x-api-key"):
        assert shown not in text


def test_the_diagnosis_script_never_shows_the_key_nor_writes() -> None:
    """It reads the key in Python, hides it in what it prints, and never touches the AI tables"""

    text = (REPOSITORY / "scripts" / "notice-diagnose.sh").read_text(encoding="utf-8")
    assert "grep -Eq '^MCPLAIN_ANTHROPIC_API_KEY=.+' .env" in text
    assert 'replace(KEY, "[hidden]")' in text
    for shown in ("cat .env", ". .env", "source .env", "$MCPLAIN_ANTHROPIC_API_KEY", "set -x", "print(KEY", "ai_texts", "INSERT", "UPDATE"):
        assert shown not in text
    assert "Redacteur" not in text
    assert "notice_body(settings, form, \"fr\", with_format=MODE == \"with-format\")" in text
    for copied in ("build_body", "NOTICE_SYSTEM", "NOTICE_SCHEMA", "JSON_ONLY"):
        assert copied not in text


def test_the_smoke_script_stops_on_an_old_image() -> None:
    """It shows the prompt versions and the image commit, and stops when the image is not built from the last commit"""

    smoke = (REPOSITORY / "scripts" / "notice-smoke.sh").read_text(encoding="utf-8")
    assert smoke.index('scripts/image-commit.sh"') < smoke.index("python3 -")
    assert "NOTICE_PROMPT_VERSION" in smoke
    check = (REPOSITORY / "scripts" / "image-commit.sh").read_text(encoding="utf-8")
    assert "older than the last commit" in check
    assert "exit 1" in check
