import pino from "pino";

const LOG_LEVEL =
  process.env.LOG_LEVEL ?? (process.env.NODE_ENV === "production" ? "info" : "debug");

/**
 * Shared structured JSON logger (S3-10). Always plain JSON — no pino
 * `transport` (worker-thread) option, since Next.js's server bundling has
 * already broken a similar spawn mechanism once in this repo (bpmnlint had
 * to move outside webpack, see git history). For a readable stream locally,
 * pipe the dev server through pino-pretty instead:
 *
 *   npm run dev | npx pino-pretty
 *
 * GDPR / PII: never log passwords, tokens, cookies, full chat messages, or
 * full blueprint bodies — only identifiers, counts, and outcomes. `redact`
 * below is a backstop, not the primary control; callers must not pass
 * sensitive fields in the first place.
 */
export const logger = pino({
  level: LOG_LEVEL,
  base: { service: "solution-wizard-v2" },
  redact: {
    paths: [
      "password",
      "*.password",
      "token",
      "*.token",
      "cookie",
      "*.cookie",
      "req.headers.authorization",
      "req.headers.cookie",
    ],
    remove: true,
  },
});
