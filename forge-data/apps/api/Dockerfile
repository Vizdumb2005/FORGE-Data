# ── Development stage ────────────────────────────────────────────────────────
FROM python:3.11-slim AS development

WORKDIR /app

# System deps: libpq for asyncpg, build-essential for compiled extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgomp1 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying source (layer cache)
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --retries 10 --timeout 1200 -r requirements.txt -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Builder (dependency snapshot) ────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --retries 10 --timeout 1200 --prefix=/install -r requirements.txt

# ── Production stage ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Runtime libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create a non-root system user
RUN addgroup --system forge && adduser --system --ingroup forge --no-create-home forge

# Copy application source
COPY --chown=forge:forge . .

USER forge

EXPOSE 8000

# 4 workers — tune via WEB_CONCURRENCY env var
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
