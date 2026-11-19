# MarocAssist backend image: API (uvicorn), worker, migrations and the
# SaaS-OS local-identity bootstrap all run from this one image.
#
# Build context: backend/. Dependencies come only from uv.lock
# (`uv sync --locked`), which pins SaaS-OS to commit cdede95 (v0.15.0).
# Development image: no secrets are baked in; configuration comes from the
# environment at run time.

FROM python:3.13-slim AS build
# git: uv fetches the pinned SaaS-OS commit over HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --no-create-home app
WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "marocassist.app:app", "--host", "0.0.0.0", "--port", "8000"]
