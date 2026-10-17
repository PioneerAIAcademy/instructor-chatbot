FROM python:3.12-slim as build

WORKDIR /app

ENV PYTHONPATH=/app

# Install curl for Poetry installation
# Note: python:3.12-slim doesn't include curl by default (unlike python:3.11)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

# Install dependencies
COPY ./pyproject.toml ./poetry.lock* /app/
RUN poetry install --no-root --no-cache --only main

# ====================================
FROM build as release

COPY . .

# Drop root: run the app as a non-privileged user. It owns /app so the runtime
# dirs the app writes stay writable.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Use gunicorn with UvicornWorker for production (Step 1)
# 2 workers for memory-constrained environments (torch + llama_index are heavy)
# Worker rotation prevents memory leaks by restarting workers after 500 requests
CMD [ \
    "gunicorn", \
    "main:app", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "-w", "2", \
    "--max-requests", "500", \
    "--max-requests-jitter", "100", \
    "--timeout", "120", \
    "--graceful-timeout", "120", \
    "--keep-alive", "10", \
    "--log-level", "info", \
    "--access-logfile", "-" \
]
