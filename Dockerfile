# Stage 1: builder — install dependencies into a wheel cache
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ ./src/

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /dist

# Stage 2: runtime — minimal image
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser

# Install wheel from builder
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy config (can be overridden via volume mount)
COPY config/ /app/config/

USER appuser

# Terminal UI by default; override with DD_UI=web for web UI
ENV DD_UI=terminal
ENV DD_POLLING_INTERVAL_SECONDS=60

CMD ["download-detector"]
