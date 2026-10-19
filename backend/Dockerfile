FROM python:3.12-slim AS build

WORKDIR /app

ENV PYTHONPATH=/app

# Install curl for Poetry installation
# Note: python:3.12-slim doesn't include curl by default (unlike python:3.11)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Poetry, pinned to the version CI uses and that wrote poetry.lock
# (lock-version 2.1). It lives in its own venv under /opt/poetry, apart from
# the app's packages.
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry POETRY_VERSION=2.4.1 python - && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

# Install dependencies
COPY ./pyproject.toml ./poetry.lock* /app/
RUN poetry install --no-root --no-cache --only main

# ====================================
FROM build AS release

# Only main.py and app/ (see .dockerignore): never .env or local files.
COPY . .

# Safe defaults; the host's settings override them. ENVIRONMENT=prod means JSON
# logs and no dev-only behavior even if the host forgets to set it.
ENV ENVIRONMENT=prod
# The git commit, for Langfuse and Sentry (§9.1): docker build --build-arg APP_VERSION=$(git rev-parse --short HEAD)
ARG APP_VERSION=""
ENV APP_VERSION=${APP_VERSION}

# Drop root: run the app as a non-privileged user. It owns /app so the runtime
# dirs the app writes stay writable.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Use gunicorn with UvicornWorker for production (Step 1)
# 2 workers for memory-constrained environments (torch + llama_index are heavy)
# Worker rotation prevents memory leaks by restarting workers after 500 requests
# Listens on all interfaces, on $PORT if the host sets one (Render, Cloud Run,
# Heroku-style hosts) and 8000 otherwise. Without --bind, gunicorn listens on
# 127.0.0.1 only, which nothing outside the container can reach.
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn main:app -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:${PORT:-8000} --max-requests 500 --max-requests-jitter 100 --timeout 120 --graceful-timeout 120 --keep-alive 10 --log-level info --access-logfile -"]
