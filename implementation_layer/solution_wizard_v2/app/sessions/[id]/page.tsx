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
  locked: "bg-neutral-bg border border-neutral-border text-neutral-text",
  pending: "bg-warning-bg border border-warning-border text-warning-text",
  approved: "bg-brand-soft border border-brand-soft-border text-brand-text",
  rejected: "bg-danger-bg border border-danger-border text-danger-text",
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

  // Phase group (rough grouping for progress)
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
      {/* ===== Top bar + hex logo ===== */}
      <header className="h-[52px] shrink-0 px-5 flex items-center justify-between bg-surface/70 backdrop-blur-md border-b border-white/10">
        <div className="flex items-center gap-3.5 min-w-0">
          {/* GAIK hex logo */}
          <span className="flex items-center gap-2.5 shrink-0">
            <span className="relative flex h-[30px] w-[30px] items-center justify-center drop-shadow-[0_0_6px_rgba(214,184,120,0.3)]">
              <span className="hex absolute inset-0 bg-gold" />
              <span className="hex absolute inset-[2px] bg-surface" />
              <span className="relative z-[1] font-display text-[13px] font-extrabold text-gold">
                G
              </span>
            </span>
            <span className="text-[15px] font-bold tracking-tight text-text">
              GAIK <span className="font-medium text-text-muted">Wizard</span>
            </span>
          </span>
          <span className="h-4 w-px bg-border-strong" />
          <Link
            href="/"
            className="text-sm text-text-muted hover:text-brand-strong transition-colors shrink-0"
          >
            {t.backToSessions}
          </Link>
          <span className="h-4 w-px bg-border-strong" />
          <span className="text-[15px] font-semibold tracking-tight text-text truncate">
            {session.title}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm text-text-secondary">
          <LocaleSwitcher locale={locale} />
          <span className="text-text-muted">{user?.email}</span>
          <span className="h-4 w-px bg-border-strong" />
          <form action={signOut}>
            <button className="text-sm font-medium text-text-muted hover:text-danger-text transition-colors">
              {t.signOut}
            </button>
          </form>
        </div>
      </header>

      {/* ===== Stepper row: progress | hex stepper | status ===== */}
      <div className="shrink-0 flex items-stretch bg-surface/70 backdrop-blur-md border-b border-white/10">
        {/* Left flank: progress */}
        <div className="w-[188px] shrink-0 px-[18px] py-3.5 border-r border-border flex flex-col justify-center">
          <div className="text-[11px] font-bold tracking-wide text-text-muted">
            {t.phaseUpper} {session.step} / {PHASE_COUNT}
          </div>
          <div className="text-[13px] font-semibold text-text mt-0.5">
            {group}
          </div>
          <div className="h-1.5 bg-surface-muted rounded-full mt-2.5 overflow-hidden">
            <span
              className="block h-full rounded-full bg-gradient-to-r from-gold to-gold-strong"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="text-[11px] text-text-muted mt-1.5">
            {pct} % {t.done.toLowerCase()}
          </div>
        </div>

        {/* Center: hex stepper (horizontal scroll) */}
        <nav className="flex-1 min-w-0 overflow-x-auto px-5 py-3.5">
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
                  className="relative flex w-[92px] shrink-0 flex-col items-center text-center"
                >
                  {/* Connecting line */}
                  {!isLast && (
                    <span
                      aria-hidden
                      className={`absolute top-4 left-[calc(50%+17px)] h-0.5 w-[calc(100%-34px)] ${
                        isDone ? "bg-brand" : "bg-border-strong"
                      }`}
                    />
                  )}

                  {/* Hexagon dot */}
                  <div
                    className={`relative flex h-[34px] w-[30px] items-center justify-center ${
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
                      className={`hex absolute inset-[2px] ${
                        isDone
                          ? "bg-brand"
                          : isCurrent
                            ? "bg-gold"
                            : "bg-surface"
                      }`}
                    />
                    <span
                      className={`relative z-[1] text-[12px] font-semibold ${
                        isDone
                          ? "text-[#07231f]"
                          : isCurrent
                            ? "text-[#2a2008]"
                            : "text-text-muted"
                      }`}
                    >
                      {isDone ? "✓" : step}
                    </span>
                  </div>

                  <span
                    className={`mt-2 text-[11px] leading-tight max-w-[86px] ${
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
                    <span
                      className={`mt-1 inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${GATE_BADGE[gate]}`}
                    >
                      {t.gates[gate]}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>

        {/* Right flank: status */}
        <div className="shrink-0 px-[18px] py-3.5 border-l border-border flex flex-col items-end justify-center gap-2">
          {gatePending ? (
            <div className="flex items-center gap-2 rounded-full bg-warning-bg px-3 py-1.5 text-xs font-semibold text-warning-text whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-warning-text" />
              {t.gateWaiting}
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-full bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand-text whitespace-nowrap">
              <span className="h-2 w-2 rounded-full bg-brand-strong" />
              {t.saved}
            </div>
          )}
        </div>
      </div>

      {/* ===== Two columns: workspace | chat dock ===== */}
      <div className="flex flex-1 min-h-0">
        {/* Left: workspace */}
        <main className="relative overflow-hidden flex-1 flex flex-col min-w-0 min-h-0">
          {/* Hex watermark */}
          <div
            aria-hidden
            className="pointer-events-none absolute right-[-40px] top-1/2 z-0 flex h-[420px] w-[380px] -translate-y-1/2 items-center justify-center text-[200px] font-extrabold italic text-[rgba(214,184,120,0.06)]"
          >
            <span className="hex absolute inset-0 bg-[rgba(214,184,120,0.035)]" />
            G
          </div>

          {/* Title row */}
          <div className="relative z-10 shrink-0 flex items-center justify-between px-6 py-3.5 border-b border-border">
            <div className="flex items-baseline gap-3">
              <span className="text-[11px] font-bold uppercase tracking-wide text-gold">
                {t.workspace}
              </span>
              <span className="text-xl font-bold tracking-tight text-text">
                {currentPhase}
              </span>
            </div>
            <span className="text-xs text-text-muted">
              {t.activeBlueprint} v{session.activeVersion} ·{" "}
              {session.versions.length} {t.versions}
            </span>
          </div>

          {/* Content: gate notice + workspace tabs */}
          <div className="relative z-10 flex-1 min-h-0 flex flex-col p-6">
            {gatePending && (
              <div className="shrink-0 mb-4 rounded-md border border-warning-border bg-warning-bg px-3 py-2.5 text-[13px] text-warning-text flex items-start gap-2">
                <span className="h-1.5 w-1.5 mt-1.5 rounded-full bg-warning-text shrink-0" />
                <span>{t.gateNotice}</span>
              </div>
            )}

            <WorkspacePanel
              sessionId={session.id}
              blueprint={session.blueprint}
              t={t}
            />
          </div>

          {/* Phase controls */}
          <div className="relative z-10 shrink-0 flex items-center justify-between px-6 py-3.5 border-t border-border">
            <form action={regress}>
              <input type="hidden" name="id" value={session.id} />
              <button
                type="submit"
                disabled={session.step <= 1}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border-strong px-4 py-2 text-sm font-medium text-text transition-colors hover:border-brand hover:text-brand-strong disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t.previous}
              </button>
            </form>

            {gatePending ? (
              <form action={approve}>
                <input type="hidden" name="id" value={session.id} />
                <button
                  type="submit"
                  className="inline-flex items-center justify-center gap-1.5 rounded-md bg-gold px-4 py-2 text-sm font-semibold text-[#2a2008] shadow-xs transition-[filter] hover:brightness-110 active:brightness-95"
                >
                  {t.approveGate}
                </button>
              </form>
            ) : (
              <form action={advance}>
                <input type="hidden" name="id" value={session.id} />
                <button
                  type="submit"
                  disabled={atEnd}
                  className="inline-flex items-center justify-center gap-1.5 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-[#06231f] shadow-xs transition-colors hover:bg-brand-hover active:bg-brand-active disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
                >
                  {atEnd ? t.ready : t.nextPhase}
                </button>
              </form>
            )}
          </div>
        </main>

        {/* Right: chat dock (handle + collapse) */}
        <ChatDock
          sessionId={session.id}
          initialMessages={session.messages}
          chatTitle={t.chat}
          greeting={t.chatGreeting}
          inputPlaceholder={t.chatInputPlaceholder}
          sendLabel={t.chatSend}
          railBadge={`${t.phaseUpper} ${session.step}`}
          userInitial={(user?.email?.[0] ?? "K").toUpperCase()}
        />
      </div>
    </div>
  );
}
