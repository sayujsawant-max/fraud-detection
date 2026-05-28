# ============================================================
# FraudShield MLOps — Frontend (Next.js 14) Dockerfile
# ============================================================
# Three-stage multi-arch build using Next.js standalone output. Like the
# backend image, the corporate-proxy CA bundle is optional — the COPY
# uses a glob so CI builds (which don't carry the bundle) still succeed.

# ---------- Stage 1: install deps ----------
FROM node:20-alpine AS deps
WORKDIR /app

# Optional CA bundle. The glob + ``.gitkeep`` pattern makes the COPY
# non-fatal when no PEMs are present; the export-ca-bundle.ps1 helper
# drops a ``ca-bundle.pem`` here for corporate-proxy builds.
COPY certs/ /tmp/host-cas/
RUN set -eux; \
    for pem in /tmp/host-cas/*.pem; do \
        [ -f "$pem" ] || continue; \
        cp "$pem" /etc/ssl/certs/host-ca-bundle.pem; \
        echo "NODE_EXTRA_CA_CERTS=/etc/ssl/certs/host-ca-bundle.pem" > /tmp/host-cas/node-ca-env; \
    done; \
    [ -f /tmp/host-cas/node-ca-env ] && cat /tmp/host-cas/node-ca-env >> /etc/environment || true
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/host-ca-bundle.pem

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ---------- Stage 2: build ----------
FROM node:20-alpine AS builder
WORKDIR /app

COPY certs/ /tmp/host-cas/
RUN set -eux; \
    for pem in /tmp/host-cas/*.pem; do \
        [ -f "$pem" ] || continue; \
        cp "$pem" /etc/ssl/certs/host-ca-bundle.pem; \
    done
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/host-ca-bundle.pem

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* env vars are inlined into the JS bundle at build time —
# they must be set BEFORE ``npm run build`` to take effect. The compose
# file passes the current value as a build arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8001
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- Stage 3: runtime ----------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN apk add --no-cache curl \
    && addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

# Probe the Next.js root route. ``server.js`` serves the App-Router shell
# so a 200 here confirms both the runtime and the bundled pages are up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
