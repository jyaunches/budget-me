# syntax=docker/dockerfile:1

# =============================================================================
# Build Stage: Install dependencies with uv
# =============================================================================
FROM python:3.12-slim AS builder

# Copy a version-pinned uv binary from its official container image.
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Environment settings for uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Copy dependency files first (for layer caching)
# README.md is needed by hatchling during package build
COPY pyproject.toml uv.lock README.md ./

# Install dependencies (without the project itself for better caching)
# Install only runtime dependencies in the production image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# =============================================================================
# Runtime Stage: Minimal production image
# =============================================================================
FROM python:3.12-slim AS runtime

# Install runtime dependencies (curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy virtual environment and code from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY scripts/generate_secrets.py /app/scripts/generate_secrets.py
RUN chmod -R u=rwX,go=rX /app/src /app/alembic \
    && chmod u=rw,go=r /app/alembic.ini /app/scripts/generate_secrets.py

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Streamlit configuration
# Render uses port 10000 by default
ENV STREAMLIT_SERVER_PORT=10000 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 10000

# Health check using Streamlit's built-in endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:10000/_stcore/health || exit 1

# Start Streamlit (generate secrets first, then start app)
CMD ["sh", "-c", "python scripts/generate_secrets.py && exec streamlit run src/budget_me/streamlit_app/app.py"]
