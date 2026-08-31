import Link from "next/link";
import { notFound } from "next/navigation";
import { getCurrentUser } from "@/lib/current-user";
import { getI18n } from "@/lib/i18n";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { signOut } from "@/app/login/actions";
import { ChatDock } from "@/components/chat-dock";
import { WorkspacePanel } from "@/components/workspace-panel";
import { advance, regress, approve } from "./actions";
import {
  getSession,
  PHASE_COUNT,
  isGateStep,
  type GateStatus,
} from "@/lib/mock-sessions";

const GATE_BADGE: Record<GateStatus, string> = {
  locked: "badge-gate bg-neutral-bg border-neutral-border text-neutral-text",
  pending: "badge-gate bg-warning-bg border-warning-border text-warning-text",
  approved: "badge-gate bg-brand-soft border-brand-soft-border text-brand-text",
  rejected: "badge-gate bg-danger-bg border-danger-border text-danger-text",
};

export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getCurrentUser();
  const { locale, t } = await getI18n();
  const session = getSession(id);

  if (!session) notFound();

  const currentPhase = t.phases[session.step - 1];
  const onGate = isGateStep(session.step);
  const gatePending = onGate && session.gateStatus[session.step] === "pending";
  const atEnd = session.step >= PHASE_COUNT;
  const pct = Math.round(((session.step - 1) / (PHASE_COUNT - 1)) * 100);

  const GROUPS =
    locale === "en"
      ? ["Definition", "Design", "Build", "Finalize"]
      : ["Määrittely", "Suunnittelu", "Toteutus", "Viimeistely"];
  const group =
    session.step <= 4
      ? GROUPS[0]
      : session.step <= 9
        ? GROUPS[1]
        : session.step <= 11
          ? GROUPS[2]
          : GROUPS[3];

  return (
    <div className="h-screen flex flex-col">
      <header className="h-14 shrink-0 px-5 flex items-center justify-between bg-surface/70 backdrop-blur-md border-b border-white/10">
        <div className="flex items-center gap-3.5 min-w-0">
          <span className="flex items-center gap-2.5 shrink-0" aria-hidden>
            <span className="relative flex h-8 w-8 items-center justify-center drop-shadow-[0_0_6px_rgba(214,184,120,0.3)]">
              <span className="hex absolute inset-0 bg-gold" />
              <span className="hex absolute inset-0.5 bg-surface" />
              <span className="relative z-[1] font-display text-sm font-extrabold text-gold">
                G
              </span>
            </span>
            <span className="text-base font-bold tracking-tight text-text">
              GAIK <span className="font-medium text-text-muted">Wizard</span>
            </span>
          </span>
          <span className="h-4 w-px bg-border-strong" aria-hidden />
          <Link
            href="/"
            className="text-sm text-text-muted hover:text-brand-strong transition-colors shrink-0"
          >
            {t.backToSessions}
          </Link>
          <span className="h-4 w-px bg-border-strong" aria-hidden />
          <h1 className="text-base font-semibold tracking-tight text-text truncate">
            {session.title}
          </h1>
        </div>
        <div className="flex items-center gap-4 text-sm text-text-secondary">
          <LocaleSwitcher locale={locale} />
          <span className="text-text-muted">{user?.email}</span>
          <span className="h-4 w-px bg-border-strong" aria-hidden />
          <form action={signOut}>
            <button
              type="submit"
              className="text-sm font-medium text-text-muted hover:text-danger-text transition-colors"
            >
              {t.signOut}
            </button>
          </form>
        </div>
      </header>

      <div className="shrink-0 flex items-stretch bg-surface/70 backdrop-blur-md border-b border-white/10">
        <div className="w-[var(--width-progress-sidebar)] shrink-0 px-5 py-3.5 border-r border-border flex flex-col justify-center">
          <div className="text-xs font-bold tracking-wide text-text-muted">
            {t.phaseUpper} {session.step} / {PHASE_COUNT}
          </div>
          <div className="text-sm font-semibold text-text mt-0.5">{group}</div>
          <div
            className="h-1.5 bg-surface-muted rounded-full mt-2.5 overflow-hidden"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${pct}% ${t.done.toLowerCase()}`}
          >
            <span
              className="block h-full rounded-full bg-gradient-to-r from-gold to-gold-strong"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="text-xs text-text-muted mt-1.5">
            {pct} % {t.done.toLowerCase()}
          </div>
        </div>

        <nav
          aria-label={t.phaseProgressNav}
          className="flex-1 min-w-0 overflow-x-auto px-5 py-3.5"
        >
          <ol className="flex items-start min-w-max">
            {t.phases.map((phase, i) => {
              const step = i + 1;
              const isCurrent = step === session.step;
              const isDone = step < session.step;
              const isLast = step === t.phases.length;
              const gate = isGateStep(step)
                ? session.gateStatus[step]
                : undefined;

              return (
                <li
                  key={step}
                  aria-current={isCurrent ? "step" : undefined}
                  className="relative flex w-[var(--width-step-cell)] shrink-0 flex-col items-center text-center"
                >
                  {!isLast && (
                    <span
                      aria-hidden
                      className={`absolute top-4 left-[calc(50%+17px)] h-0.5 w-[calc(100%-34px)] ${
                        isDone ? "bg-brand" : "bg-border-strong"
                      }`}
                    />
                  )}

                  <div
                    className={`relative flex h-9 w-8 items-center justify-center ${
                      isCurrent
                        ? "drop-shadow-[0_0_9px_rgba(214,184,120,0.5)]"
                        : ""
                    }`}
                  >
                    <span
                      className={`hex absolute inset-0 ${
                        isDone
                          ? "bg-brand"
                          : isCurrent
                            ? "bg-gold"
                            : "bg-border-strong"
                      }`}
                    />
                    <span
                      className={`hex absolute inset-0.5 ${
                        isDone
                          ? "bg-brand"
                          : isCurrent
                            ? "bg-gold"
                            : "bg-surface"
                      }`}
                    />
                    <span
                      className={`relative z-[1] text-xs font-semibold ${
                        isDone
                          ? "text-on-brand-muted"
                          : isCurrent
                            ? "text-on-gold"
                            : "text-text-muted"
                      }`}
                    >
                      {isDone ? "✓" : step}
                    </span>
                  </div>

                  <span
                    className={`mt-2 text-xs leading-tight max-w-20 ${
                      isCurrent
                        ? "text-gold font-semibold"
                        : isDone
                          ? "text-text"
                          : "text-text-muted"
                    }`}
                  >
                    {phase}
                  </span>

                  {gate && (
                    <span className={GATE_BADGE[gate]}>{t.gates[gate]}</span>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="shrink-0 px-5 py-3.5 border-l border-border flex flex-col items-end justify-center gap-2">
          {gatePending ? (
            <div className="badge-warning whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-warning-text" aria-hidden />
              {t.gateWaiting}
            </div>
          ) : (
            <div className="badge bg-brand-soft border-brand-soft-border text-brand-text whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-brand-strong" aria-hidden />
              {t.saved}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <main
          id="main-content"
          className="relative overflow-hidden flex-1 flex flex-col min-w-0 min-h-0"
        >
          <div
            aria-hidden
            className="pointer-events-none absolute right-[-40px] top-1/2 z-0 flex h-[420px] w-[var(--width-chat)] -translate-y-1/2 items-center justify-center text-[200px] font-extrabold italic text-[rgba(214,184,120,0.06)]"
          >
            <span className="hex absolute inset-0 bg-[rgba(214,184,120,0.035)]" />
            G
          </div>

          <div className="relative z-10 shrink-0 flex items-center justify-between px-6 py-3.5 border-b border-border">
            <div className="flex items-baseline gap-3">
              <span className="section-kicker">{t.workspace}</span>
              <h2 className="text-xl font-bold tracking-tight text-text">
                {currentPhase}
              </h2>
            </div>
            <span className="text-xs text-text-muted">
              {t.activeBlueprint} v{session.activeVersion} ·{" "}
              {session.versions.length} {t.versions}
            </span>
          </div>

          <div className="relative z-10 flex-1 min-h-0 flex flex-col p-6">
            {gatePending && (
              <div
                role="status"
                className="shrink-0 mb-4 rounded-md border border-warning-border bg-warning-bg px-3 py-2.5 text-sm text-warning-text flex items-start gap-2"
              >
                <span
                  className="h-1.5 w-1.5 mt-1.5 rounded-full bg-warning-text shrink-0"
                  aria-hidden
                />
                <span>{t.gateNotice}</span>
              </div>
            )}

            <WorkspacePanel
              sessionId={session.id}
              blueprint={session.blueprint}
              t={t}
            />
          </div>

          <div className="relative z-10 shrink-0 flex items-center justify-between px-6 py-3.5 border-t border-border">
            <form action={regress}>
              <input type="hidden" name="id" value={session.id} />
              <button type="submit" disabled={session.step <= 1} className="btn-ghost">
                {t.previous}
              </button>
            </form>

            {gatePending ? (
              <form action={approve}>
                <input type="hidden" name="id" value={session.id} />
                <button type="submit" className="btn-gold">
                  {t.approveGate}
                </button>
              </form>
            ) : (
              <form action={advance}>
                <input type="hidden" name="id" value={session.id} />
                <button type="submit" disabled={atEnd} className="btn-brand">
                  {atEnd ? t.ready : t.nextPhase}
                </button>
              </form>
            )}
          </div>
        </main>

        <ChatDock
          sessionId={session.id}
          initialMessages={session.messages}
          chatTitle={t.chat}
          greeting={t.chatGreeting}
          inputPlaceholder={t.chatInputPlaceholder}
          inputLabel={t.chatInputLabel}
          sendLabel={t.chatSend}
          streamFailedLabel={t.streamFailed}
          hideChatLabel={t.hideChat}
          showChatLabel={t.showChat}
          railBadge={`${t.phaseUpper} ${session.step}`}
          userInitial={(user?.email?.[0] ?? "K").toUpperCase()}
        />
      </div>
    </div>
  );
}
