# Multi-stage Dockerfile for redesign_service (development)

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock* README.md* ./

RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

COPY src/ ./src/

RUN uv sync --frozen --no-dev || uv sync --no-dev

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update && apt-get install -y \
    libpq5 \
    curl \
    # Playwright/Chromium runtime deps
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 redesignservice && \
    mkdir -p /app /app/logs /app/data && \
    chown -R redesignservice:redesignservice /app

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=redesignservice:redesignservice /app/.venv /app/.venv

# Copy application code
COPY --chown=redesignservice:redesignservice . .

ENV PATH="/app/.venv/bin:$PATH"

# Install Playwright Chromium browser
RUN PLAYWRIGHT_BROWSERS_PATH=/home/redesignservice/.cache/ms-playwright \
    python -m playwright install --with-deps chromium

USER 1000:1000

# Port 6306 (Redesign Service)
EXPOSE 6306

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:6306/health || exit 1

CMD ["python", "-m", "src.asgi"]
