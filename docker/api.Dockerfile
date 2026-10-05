FROM ghcr.io/astral-sh/uv:0.11.31@sha256:ecd4de2f060c64bea0ff8ecb182ddf46ba3fcccdc8a60cfdbaf20d1a047d7437 AS uv

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS build
COPY --from=uv /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/opt/mcplain-api \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY engine/pyproject.toml engine/uv.lock engine/.python-version /src/engine/
COPY engine/src /src/engine/src
COPY api/pyproject.toml api/uv.lock api/.python-version /src/api/
WORKDIR /src/api
RUN uv sync --frozen --no-dev --no-editable --no-install-project
COPY api/src /src/api/src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d
RUN groupadd --system --gid 10002 mcplain \
    && useradd --system --uid 10002 --gid 10002 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin mcplain
COPY --from=build /opt/mcplain-api /opt/mcplain-api
COPY api/alembic.ini /app/alembic.ini
COPY api/migrations /app/migrations
WORKDIR /app
ENV PATH=/opt/mcplain-api/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10002:10002
EXPOSE 8000
CMD ["mcplain-api"]
