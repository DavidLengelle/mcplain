FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS build
COPY --from=uv /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/opt/mcplain \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src/engine
COPY engine/pyproject.toml engine/uv.lock engine/.python-version ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project
COPY engine/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d
RUN groupadd --system --gid 10001 atelier \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin atelier
COPY --from=build /opt/mcplain /opt/mcplain
ENV PATH=/opt/mcplain/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["mcplain-analyze"]
