# ============================================================
# FraudShield MLOps — Frontend (Next.js 14) Dockerfile
# Multi-stage build using Next.js standalone output.
# ============================================================

# ---------- Stage 1: install deps ----------
FROM node:20-alpine AS deps
WORKDIR /app

# Trust the host's corporate root CAs (handles TLS-intercepting proxies).
# Node uses NODE_EXTRA_CA_CERTS in addition to its built-in trust store —
# no apk add needed (and that would itself fail behind the same proxy).
COPY certs/ca-bundle.pem /etc/ssl/certs/host-ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/host-ca-bundle.pem

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ---------- Stage 2: build ----------
FROM node:20-alpine AS builder
WORKDIR /app

COPY certs/ca-bundle.pem /etc/ssl/certs/host-ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/host-ca-bundle.pem

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* env vars are inlined into the JS bundle at build time —
# they must be set BEFORE `npm run build` to take effect. The compose file
# passes the current value as a build arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- Stage 3: runtime ----------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
