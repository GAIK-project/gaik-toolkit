# -----------------------------------------------------------------------------
# Dockerfile - Bun-based build (default, recommended)
# For Node.js/pnpm alternative, use Dockerfile.pnpm
# -----------------------------------------------------------------------------

# Use Bun's official image
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

# Copy build-time env (only NEXT_PUBLIC_* vars, no secrets)
# .env.production is Next.js standard for production builds
COPY .env.production .env.local

RUN bun run build

# ----------------------------
# Runner stage (OpenShift compatible)
# ----------------------------
FROM base AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Create OpenShift-compatible user/group
# OpenShift runs containers with arbitrary UIDs in root group
RUN groupadd --system --gid 1001 nodejs && \
    useradd --system --uid 1001 --no-log-init -g nodejs nextjs

# Copy public folder
COPY --from=builder /app/public ./public

# Copy Next.js standalone output and static files
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Ensure OpenShift-friendly permissions (writable by root group)
RUN chmod -R g+rwX /app

USER nextjs

EXPOSE 3000

CMD ["bun", "./server.js"]
