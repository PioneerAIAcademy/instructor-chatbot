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

# Install dependencies. On Linux the lock's torch is the CUDA build, which pulls a dozen
# NVIDIA packages (several GB) this CPU-only service never uses. In the same layer, so the
# CUDA files never reach the image, swap in the CPU build of the same torch version, and
# clear Poetry's and pip's download caches (Poetry keeps ~2.6 GB there despite --no-cache).
COPY ./pyproject.toml ./poetry.lock* /app/
RUN poetry install --no-root --no-cache --only main && \
    cuda=$(pip list --format=freeze | grep -iE '^(nvidia-|triton=)' | cut -d= -f1) && \
    { [ -z "$cuda" ] || pip uninstall -y $cuda; } && \
    pip install --no-cache-dir --force-reinstall --no-deps \
        --index-url https://download.pytorch.org/whl/cpu torch==2.2.2 && \
    python -c "import torch; assert not torch.cuda.is_available(); print('torch', torch.__version__)" && \
    rm -rf /root/.cache

# The prompt-injection detector's model (protectai/deberta-v3-base-prompt-injection, about
# 714 MB), downloaded once here so a deploy doesn't fetch it from Hugging Face at every
# start. It lives outside /app so the chown below doesn't copy it into another layer.
# BAKE_INJECTION_MODEL=0 skips it; the server then downloads it at startup instead.
ARG BAKE_INJECTION_MODEL=1
ENV HF_HOME=/opt/hf
RUN if [ "$BAKE_INJECTION_MODEL" = "1" ]; then \
        python -c "import pytector; pytector.PromptInjectionDetector(); print('injection model cached')" && \
        chmod -R a+rX /opt/hf; \
    fi

# ====================================
FROM build AS release

# Only main.py and app/ (see .dockerignore): never .env or local files.
COPY . .

# Safe defaults; the host's settings override them. ENVIRONMENT=prod means JSON
# logs and no dev-only behavior even if the host forgets to set it.
ENV ENVIRONMENT=prod
# With the model built in, never reach out to Hugging Face at runtime (1 = offline).
# (An ARG doesn't carry over from the build stage, so it's declared again here.)
ARG BAKE_INJECTION_MODEL=1
ENV HF_HUB_OFFLINE=${BAKE_INJECTION_MODEL} TRANSFORMERS_OFFLINE=${BAKE_INJECTION_MODEL}
# The git commit, for Langfuse and Sentry (§9.1): docker build --build-arg APP_VERSION=$(git rev-parse --short HEAD)
ARG APP_VERSION=""
ENV APP_VERSION=${APP_VERSION}

# Drop root: run the app as a non-privileged user. It owns /app so the runtime
# dirs the app writes stay writable.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Use gunicorn with UvicornWorker for production (Step 1)
# WEB_CONCURRENCY workers (default 2): each holds its own copy of the injection model
# (about 0.5 GB), so 2 fit a 2 GB instance.
# Worker rotation prevents memory leaks by restarting workers after 500 requests
# Listens on all interfaces, on $PORT if the host sets one (Render, Cloud Run,
# Heroku-style hosts) and 8000 otherwise. Without --bind, gunicorn listens on
# 127.0.0.1 only, which nothing outside the container can reach.
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} --bind 0.0.0.0:${PORT:-8000} --max-requests 500 --max-requests-jitter 100 --timeout 120 --graceful-timeout 120 --keep-alive 10 --log-level info --access-logfile -"]
