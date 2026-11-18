import { actorId } from "@/lib/actor-id";
import { logger } from "@/lib/logger";
import { getTraceId } from "@/lib/request-context";

export type AuditOutcome = "success" | "denied" | "error";

/**
 * The agreed Sprint 3 audit event set (docs/2026-08-logging/, issue S3-10).
 * blueprint.ops / blueprint.version.restore are declared for forward
 * compatibility with the change-ops work (#66/#67) — not emitted yet, since
 * that functionality doesn't exist in this branch.
 */
export type AuditEvent =
  | "auth.login"
  | "auth.logout"
  | "auth.denied"
  | "session.create"
  | "session.delete"
  | "session.rename"
  | "session.export"
  | "blueprint.update"
  | "blueprint.ops"
  | "blueprint.version.restore"
  | "bpmn.sync"
  | "poc.generate"
  | "poc.download"
  | "poc.deployable"
  | "poc.file.save"
  | "poc.input.upload"
  | "poc.input.delete"
  | "case.create"
  | "case.delete"
  | "case.input.upload"
  | "case.input.delete"
  | "case.submit"
  | "case.step"
  | "case.review";

export type AuditFields = {
  /**
   * Who — pass the signed-in user's email; the log line gets its stable
   * pseudonym (`lib/actor-id.ts`), never the address itself. Never log
   * passwords/tokens/cookies here.
   */
  actor?: string;
  /** What was acted on. */
  resource?: { type: string; id: string };
  /** Free-text action detail — keep it to identifiers/counts, not content. */
  action?: string;
  outcome: AuditOutcome;
  traceId?: string;
  [key: string]: unknown;
};

/**
 * Audit trail (S3-10 Vaihe 2) — who did what, when, with what outcome.
 * Tagged `type: "audit"` so it can be filtered out of operational logs.
 * Stdout JSON only this sprint; persistence/retention is Vaihe 3, out of
 * scope for #82.
 */
export function audit(event: AuditEvent, fields: AuditFields): void {
  const { traceId, actor, ...rest } = fields;
  logger.info(
    {
      type: "audit",
      event,
      traceId: traceId ?? getTraceId(),
      ...(actor === undefined ? {} : { actor: actorId(actor) }),
      ...rest,
    },
    `audit.${event}`,
  );
}
