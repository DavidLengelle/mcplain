"""Database: the analyses table, which is also the job queue"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Index, String, Uuid, create_engine, false
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
