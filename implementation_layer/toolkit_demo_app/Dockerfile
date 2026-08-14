# -----------------------------------------------------------------------------
# Dockerfile - Bun-based build optimized for CSC Rahti 2 (OpenShift)
# For Node.js/pnpm alternative, use Dockerfile.pnpm
# -----------------------------------------------------------------------------

# Use Bun's official image for build stages
FROM oven/bun:1 AS base

WORKDIR /app

# Disable Next.js telemetry
ENV NEXT_TELEMETRY_DISABLED=1

# ----------------------------
# Dependencies stage
# ----------------------------
FROM base AS deps

COPY package.json bun.lock* ./
RUN bun install --no-save --frozen-lockfile

# ----------------------------
# Builder stage
# ----------------------------
FROM base AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* vars are inlined at build time by Next.js
# .env.production contains only public/publishable values (no secrets)
COPY .env.production .env.production

# Bun 1.3.14 (linux x64 baseline) segfaults while tearing down its build workers
# *after* `next build` has already finished: the log ends with the complete route
# table and "Generating static pages (31/31)", then Bun's own crash handler prints
# "this indicates a bug in Bun, not your code". The panic still sets a non-zero
# exit code, which would fail this layer despite a good build. The same build runs
# clean on Bun for Windows, so this is platform-specific to the container.
#
# So don't trust the exit status here — verify the artifacts the runner stage
# actually copies. A real build failure never writes them, so this still fails
# loudly; it only tolerates a crash that happens after the output is on disk.
RUN bun run build || echo "next build exited non-zero - verifying build output below"; \
    test -f .next/standalone/server.js && test -d .next/static

# ----------------------------
# Runner stage (CSC Rahti 2 / OpenShift optimized)
# Uses slim image for smaller footprint (~45MB vs ~520MB)
# ----------------------------
FROM oven/bun:1-slim AS runner

# Metadata
LABEL maintainer="GAIK Project"
LABEL description="GAIK Demo Frontend"
LABEL version="1.0.0"

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Copy public folder
COPY --from=builder /app/public ./public

# Copy Next.js standalone output and static files
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# OpenShift arbitrary UID support
# CSC Rahti 2 assigns random UIDs but always GID=0 (root group)
# Files must be owned by root group and writable by GID=0
RUN chgrp -R 0 /app && chmod -R g=u /app

# Run as non-root user (OpenShift will assign arbitrary UID)
USER 1001

EXPOSE 3000

CMD ["bun", "./server.js"]
