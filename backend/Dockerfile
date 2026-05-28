# ============================================================
# FraudShield MLOps — Backend (FastAPI) Dockerfile
# ============================================================
# Two-stage build:
#   * ``deps`` — installs build-time system packages + pip wheels
#   * ``runtime`` — slim image, non-root user, no compilers
#
# The corporate-proxy CA bundle is **optional**: if ``certs/`` is empty
# the build still works (used in CI). The dev machine drops a real
# ``ca-bundle.pem`` into ``backend/certs/`` so pip can reach PyPI
# through a TLS-intercepting proxy without falling over.

FROM python:3.11-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build-time system packages: psycopg2-binary needs libpq, xgboost/lightgbm
# need libgomp1, healthcheck wants curl. ca-certificates is the trust store
# we may layer the corporate bundle on top of.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libgomp1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional CA bundle. Using a glob + a guaranteed-present ``.gitkeep``
# keeps the COPY non-fatal when the bundle is absent (e.g. CI). The
# subsequent shell block trusts whatever PEMs are present.
COPY certs/ /tmp/host-cas/
RUN set -eux; \
    for pem in /tmp/host-cas/*.pem; do \
        [ -f "$pem" ] || continue; \
        cp "$pem" "/usr/local/share/ca-certificates/$(basename "$pem" .pem).crt"; \
    done; \
    update-ca-certificates; \
    rm -rf /tmp/host-cas

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --retries 10 --timeout 180 -r requirements.txt

# ---------- Runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Runtime needs only the shared libraries + curl for the healthcheck.
# Skipping build-essential here trims ~300 MB off the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        libgomp1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the installed Python environment + ca-certificates from the
# deps stage. We keep the user-installed system CAs so requests/MLflow
# can hit any internal services that present custom certs.
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --from=deps /etc/ssl/certs /etc/ssl/certs

# Application source. ``scripts/`` is also included so smoke + retraining
# scripts can be exec'd inside the container.
COPY src ./src
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# Non-root runtime user. UID 1001 mirrors the frontend image, which makes
# bind-mounted host directories interoperate consistently across services.
RUN groupadd --system --gid 1001 fraudshield \
    && useradd --system --uid 1001 --gid fraudshield --home /app fraudshield \
    && chown -R fraudshield:fraudshield /app

USER fraudshield

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
