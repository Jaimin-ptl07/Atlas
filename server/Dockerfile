# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app


# ---------------------------------------------------------
# Builder
# ---------------------------------------------------------

FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-install-project


# ---------------------------------------------------------
# Development
# ---------------------------------------------------------

FROM base AS development

COPY --from=builder /app/.venv /app/.venv
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --locked

COPY app ./app
COPY tests ./tests

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ---------------------------------------------------------
# Production
# ---------------------------------------------------------

FROM base AS production

COPY --from=builder /app/.venv /app/.venv

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]