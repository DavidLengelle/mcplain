"""Database: the analyses table, which is also the job queue"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    create_engine,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

INPUT_MAX_CHARS = 500
SELECT_MAX_CHARS = 500
SOURCE_KEY_MAX_CHARS = 600
SHA256_HEX_CHARS = 64
SQLITE_PREFIX = "sqlite"
MEMORY_SQLITE_URLS: frozenset[str] = frozenset({"sqlite://", "sqlite:///:memory:"})


class AnalysisState(StrEnum):
    """Class that lists the states of an analysis in the queue"""

    QUEUED = "queued"
    FETCHING = "fetching"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"


RUNNING_STATES: tuple[str, ...] = (AnalysisState.FETCHING.value, AnalysisState.ANALYZING.value)
STATE_CHECK = "state IN ('queued', 'fetching', 'analyzing', 'done', 'failed')"


class AiKind(StrEnum):
    """Class that lists what the AI can write"""

    NOTICE = "notice"
    TRANSLATION = "translation"


class AiStatus(StrEnum):
    """Class that lists the states of a text asked from the AI"""

    PENDING = "pending"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"
    PAUSED = "paused"
    DISABLED = "disabled"


AI_STATUS_CHECK = "status IN ('pending', 'ready', 'rejected', 'failed', 'paused', 'disabled')"
AI_STATE_ROW = 1


def utc_now() -> datetime:
    """Return the current time in UTC"""

    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Class that holds the metadata of every table"""


class Analysis(Base):
    """Class that maps one requested analysis, its state in the queue and its result"""

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(STATE_CHECK, name="analyses_state_valid"),
        Index("ix_analyses_state_created_at", "state", "created_at"),
        Index("ix_analyses_source_key", "source_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    input_raw: Mapped[str] = mapped_column(String(INPUT_MAX_CHARS))
    select: Mapped[str | None] = mapped_column(String(SELECT_MAX_CHARS))
    state: Mapped[str] = mapped_column(String(16), default=AnalysisState.QUEUED.value)
    source_key: Mapped[str | None] = mapped_column(String(SOURCE_KEY_MAX_CHARS))
    reputation_sha256: Mapped[str | None] = mapped_column(String(SHA256_HEX_CHARS))
    error_code: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    engine_version: Mapped[str | None] = mapped_column(String(32))
    rules_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class AiText(Base):
    """Class that maps one text asked from the AI: the cache, the queue of the writer and the record of what it cost"""

    __tablename__ = "ai_texts"
    __table_args__ = (
        UniqueConstraint("kind", "lang", "hash", "prompt_version", "model", name="ai_texts_cache_key"),
        CheckConstraint(AI_STATUS_CHECK, name="ai_texts_status_valid"),
        Index("ix_ai_texts_status_created_at", "status", "created_at"),
        Index("ix_ai_texts_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    lang: Mapped[str] = mapped_column(String(8))
    hash: Mapped[str] = mapped_column(String(SHA256_HEX_CHARS))
    prompt_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=AiStatus.PENDING.value)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    reject_reason: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    request_id: Mapped[str | None] = mapped_column(String(128))
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AiAdminAlert(Base):
    """Class that maps one alert for the admin; its details never hold the key nor a text of a third party"""

    __tablename__ = "ai_admin_alerts"
    __table_args__ = (Index("ix_ai_admin_alerts_code_created_at", "code", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))


class AiState(Base):
    """Class that maps the single row telling whether the writer is paused or cut off"""

    __tablename__ = "ai_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=AI_STATE_ROW)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(32))


def make_engine(url: str) -> Engine:
    """Create the database engine; an in-memory SQLite database is shared by every thread of the process"""

    if url in MEMORY_SQLITE_URLS:
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url.startswith(SQLITE_PREFIX):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def make_sessions(engine: Engine) -> sessionmaker:
    """Return the session factory used by the API and the dispatcher"""

    return sessionmaker(engine, expire_on_commit=False)


def as_utc(value: datetime | None) -> datetime | None:
    """Return a stored time in UTC; SQLite gives it back without its time zone"""

    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
