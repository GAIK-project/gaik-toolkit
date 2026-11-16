import { notFound } from "next/navigation";
import { getCurrentUser } from "@/lib/current-user";
import { getI18n } from "@/lib/i18n";
import { OpenChatButton } from "@/components/chat-dock";
import { SessionChatDock } from "@/components/session-chat-dock";
import { Icon } from "@/components/icons";
import { WorkspacePanel } from "@/components/workspace-panel";
import { GateTimeline, type TimelineGuide } from "@/components/gate-timeline";
import { SessionBar } from "@/components/session-bar";
import { StepsDisclosure } from "@/components/steps-disclosure";
import { Gate1Review, gate1Missing } from "@/components/gate1-review";
import { GateDecisionBar, type GateDecisionLabels } from "@/components/gate-decision-bar";
import { Gate1MissingForm } from "@/components/gate1-missing-form";
import { GatheringView } from "@/components/gathering-view";
import { ForgetWizardRelease, ReleaseWizardWhenDone } from "@/components/release-wizard";
import { ShowInWorkspaceButton } from "@/components/show-in-workspace-button";
import { FieldSchemaEditor } from "@/components/field-schema-editor";
import { fieldSpecsFromTargetOutput } from "@/lib/target-output-spec";
import { getSessionForUser } from "@/lib/session-access";
import { PHASE_COUNT, getPackageDigest, isGateStep } from "@/lib/sessions";
import { packageChangedSinceRun } from "@/lib/poc-result-state";
import { shouldCollapseChatByDefault } from "@/lib/bpmn-spike";
import { GATE_STEPS, gateNumber } from "@/lib/wizard-state-machine";
import { nowLine } from "@/lib/gate-guide";
import { decisionGateStep, specificationGathered, workspaceStep } from "@/lib/gate-decision";
import { GATE_MOVED_NOTICE, PACKAGE_CHANGED_NOTICE } from "@/lib/step-redirect";
import { parseTabParam } from "@/lib/workspace-tab-follow";
import { chatLeads } from "@/lib/session-start";

export default async function SessionPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ wake?: string; notice?: string; tab?: string }>;
}) {
  const { id } = await params;
  const { wake, notice, tab } = await searchParams;
  const user = await getCurrentUser();
  const { locale, t } = await getI18n();
  const session = user ? await getSessionForUser(id, user.email) : undefined;

  if (!session) notFound();

  // Gate 1–4 on a gate step, 0 elsewhere.
  const gate = gateNumber(session.step) ?? 0;
  const gateBlocking = gate > 0 && session.gateStatus[session.step] !== "approved";
  // After a gate approval in the panel the chat tells the agent (#173).
  // Only for a gate that is approved: the address alone (a link in a reply,
  // say) must not tell the agent a pending gate was approved.
  const wokenGate = /^[1-4]$/.test(wake ?? "") ? Number(wake) : undefined;
  const wakeMessage =
    wokenGate !== undefined && session.gateStatus[GATE_STEPS[wokenGate - 1]] === "approved"
      ? t.gateApprovedWake.replace("{n}", String(wokenGate))
      : undefined;
  // The wizard is replying, or is about to be told of the approval just given.
  const replyAhead = Boolean(session.pendingTurn) || wakeMessage !== undefined;
  // The gate whose decision is offered now: the one the session stands on, or
  // the one ahead in its stage once what it reviews is there (lib/gate-decision).
  // Not the gate after the one approved a moment ago, before the wizard has
  // heard of that approval.
  const decisionStep = decisionGateStep({ ...session, pendingTurn: replyAhead ? true : null });
  const decisionGate = decisionStep ? (gateNumber(decisionStep) ?? 0) : 0;
  // Gate 3 approves a test run of the package that is there. wizard_api keeps
  // the digest of the package the run that passed was started on and refuses
  // the gate once the package has another: the page reads the same two digests,
  // so the approval waits with its reason before it is pressed, on every tab
  // and after a reload. An api that keeps no digest is not asked.
  const packageChanged =
    decisionGate === 3 && session.lastSuccessfulRunPackage
      ? packageChangedSinceRun(await getPackageDigest(session.id), session.lastSuccessfulRunPackage)
      : false;
  // Gate 2 offered from a step before it: the page is the gate's.
  const currentPhase = t.phases[(decisionGate === 2 && decisionStep ? decisionStep : session.step) - 1];
  const points = session.requirements?.points ?? [];
  const answers = session.requirements?.answers ?? [];
  // The wizard has recorded what Gate 1 reviews. A session can stand before
  // Gate 1 with that (it was stepped back): the review and its decision are
  // then shown there too, since the wizard asks for the approval.
  const gathered = specificationGathered(session);
  // Standing on Gate 1 with the gate approved, the session is in the next
  // stage: it shows the workspace, as every step after Gate 1 does.
  const isGate1 =
    (gate === 1 && gateBlocking) ||
    decisionGate === 1 ||
    (gathered && session.step <= 2 && points.length === 0);
  const isSpec = session.step === 3;
  const isGathering = session.step <= 3;
  // While requirements are gathered the session happens in the chat. With no
  // checklist and nothing recorded to show beside it, the chat is the page's
  // main content; the workspace comes in with the specification, and is there
  // whenever a gate waits for a decision.
  const chatIsPage = chatLeads(session.step, points, { gathered, gateWaiting: Boolean(decisionStep) });
  const atEnd = session.step >= PHASE_COUNT;
  // Gate 4 approved: nothing is left to do in the wizard but take the package.
  const solutionDone = atEnd && !gateBlocking;
  // The steps between gates have no buttons: they carry no decision of the
  // user's, and wizard_api moves the session as the wizard writes its files.
  // A session standing on a gate that is already approved (not the last) is
  // in the next stage, so the line under the title is that stage's.
  const now = nowLine(
    t,
    // A gate offered from a step before it: the line is the gate's.
    (decisionGate === 1 || decisionGate === 2) && decisionStep
      ? decisionStep
      : gate > 0 && !gateBlocking && !atEnd
        ? session.step + 1
        : session.step,
    session.gateStatus,
    Boolean(session.lastSuccessfulRun),
  );

  // The requirement questions come from the backend (session.requirements) and
  // reach the user as chat messages — the opening question is a real seeded
  // message. The greeting stays a stable welcome; it no longer embeds a question.
  const chatGreeting = t.chatGreeting;

  // A refused gate approval comes back as ?notice= (actions.ts).
  const noticeText =
    notice === "agent_busy"
      ? t.noticeAgentBusy
      : notice === "gate_not_ready"
        ? t.noticeGateNotReady
        : notice === PACKAGE_CHANGED_NOTICE
          ? t.noticePackageChanged
          : notice === GATE_MOVED_NOTICE
            ? t.noticeGateMoved
            : undefined;
  // The package changed after the run that passed: the way on is the test run
  // on the PoC tab, so the notice takes the user there.
  const noticeAction = notice === PACKAGE_CHANGED_NOTICE && (
    <ShowInWorkspaceButton place="test-run" label={t.noticePackageChangedAction} />
  );

  const gateSteps = Array.from({ length: PHASE_COUNT }, (_, i) => i + 1).filter(
    isGateStep,
  );

  const timelineGuide: TimelineGuide = {
    topics: t.gateTopics,
    decisions: t.gateDecisions,
    checks: t.gateChecks,
    checksTitle: t.gateChecksTitle,
    change: t.gateChange,
    changeLabel: t.gateChangeLabel,
    chip: t.gateChip,
    changePrefix: t.gateChangePrefix,
    reopen: t.gateReopen,
  };
  // A gate reopened for a change: said above the workspace until it is approved again.
  const reopened = session.gateReopened ?? null;
  const reopenedText = reopened
    ? {
        user: t.gateReopenedByUser,
        agent: t.gateReopenedByWizard,
        change: t.gateReopenedByChange,
      }[reopened.by]
        .replace("{n}", String(reopened.gate))
        .replace("{topic}", t.gateTopics[reopened.gate - 1] ?? "")
    : undefined;
  const timeline = {
    sessionId: session.id,
    locale,
    step: session.step,
    phases: t.phases,
    gateSteps,
    gateStatus: session.gateStatus,
    phaseCount: PHASE_COUNT,
    guide: timelineGuide,
  };

  const decisionLabels: GateDecisionLabels | null = decisionGate
    ? {
        approve: t.gateDecisions[decisionGate - 1],
        approveShort: t.gateApproveShort,
        approving: t.approving,
        note: t.gateApproveNotes[decisionGate - 1],
        requestChanges: t.gateRequestChanges,
        topics: t.gateTopics,
        chip: t.gateChip,
        requestPrefix: t.gateRequestPrefix,
        rejected: t.gateRejected,
        staleResult: t.gateStaleResult,
      }
    : null;
  // Gate 1 is approvable once the wizard has the core business framing.
  const missing = isGate1 ? gate1Missing(session.businessContext, t) : [];

  // The reopened gate is said in one of two places: above the chat while it is
  // the page, else above the workspace's decision bar.
  const reopenedNotice = reopenedText && (
    <p
      role="status"
      data-testid="gate-reopened"
      className="mx-4 mt-3 flex shrink-0 items-start gap-2 rounded-md border border-brand-soft-border bg-brand-soft px-3 py-2 text-sm text-brand-text sm:mx-6"
    >
      <Icon name="rotateCcw" size={16} className="mt-0.5 shrink-0" />
      <span>{reopenedText}</span>
    </p>
  );
  // A reopened gate and a refused action, above the chat while it is the page.
  const leadNotices = (
    <>
      {reopenedNotice}
      {noticeText && (
        <p
          role="status"
          data-testid="action-notice"
          className="mx-4 mt-3 shrink-0 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-text sm:mx-6"
        >
          {noticeText}
        </p>
      )}
    </>
  );
  const stepsDisclosure = (
    <StepsDisclosure
      summary={t.phaseOf
        .replace("{n}", String(session.step))
        .replace("{total}", String(PHASE_COUNT))}
      // Above the chat that is the page, the step line has no chat button beside it.
      besideButton={!chatIsPage}
    >
      <GateTimeline variant="inline" {...timeline} />
    </StepsDisclosure>
  );

  return (
    // Keyed by the session: opening another one from the sidebar gives a new
    // page, not this one with other content. That is also the one moment its
    // bar and its content arrive with a short rise (session-in); an update of
    // the open session keeps these elements, so nothing moves then.
    <div key={session.id} className="flex min-h-0 flex-1 flex-col">
      {/* Not finished (yet, or again after its last gate was reopened): the
          next finish releases the wizard, whatever an earlier one did. */}
      {!solutionDone && <ForgetWizardRelease sessionId={session.id} />}
      {/* The session's name is the page's heading; the four gates beside it
          say how far the session is, each opening its stage on a press. */}
      <SessionBar title={session.title} className="session-in">
        <GateTimeline variant="row" {...timeline} />
      </SessionBar>

      <div data-session-content className="session-in flex min-h-0 flex-1">
        {/* overflow-clip, not overflow-hidden: a hidden box is still a scroll
            container, and content reaching past its edge let a scrollIntoView
            shift the whole workspace sideways (#35). */}
        {!chatIsPage && (
        <main
          id="main-content"
          className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-clip"
        >
          <div className="@container relative shrink-0 border-b border-border px-4 py-2 max-xl:min-h-[2.875rem] sm:px-6">
            {/* The chat button sits in the corner, beside the step line and
                the title only, so the line under them has the full width. */}
            <OpenChatButton
              label={t.chat}
              className="btn-secondary absolute right-4 top-1.5 px-3 py-1.5 sm:right-6 xl:hidden"
            />
            {/* A phone has no room for the gate row of the session bar; the
                step line here opens the stages under the title. */}
            {stepsDisclosure}
            {/* One compact row: the title, and what to do now beside it where
                the workspace is wide enough (about 1024 px, asked of the
                workspace, since the chat dock changes its width), under the
                title where it is not. */}
            <div className="flex flex-wrap items-baseline gap-x-3">
              <h2
                data-testid="workspace-phase"
                className="min-w-0 max-w-[calc(100%-9rem)] truncate text-base font-semibold tracking-tight text-text xl:max-w-full"
              >
                {currentPhase}
              </h2>
              {/* What to do now, and where: one line instead of a banner. Where
                  the chat is not docked beside the workspace, the line keeps
                  clear of the chat button. A finished solution says what there
                  is to do in its own card below. */}
              {!solutionDone && (
                <p
                  data-testid="now-line"
                  className="w-full text-sm text-text-secondary md:max-xl:pr-36 @5xl:w-auto @5xl:min-w-0 @5xl:flex-1"
                >
                  {now}
                </p>
              )}
            </div>
          </div>

          {/* The finished solution is said where the eye lands first: the
              heading, the two things to do with it on one line, and beside
              the download what the package leaves out. Without a run there is
              no package to take yet, and the line says how to get one. */}
          {solutionDone && (
            <section
              role="status"
              aria-labelledby="solution-done-title"
              data-testid="solution-done"
              className="mx-4 mt-4 shrink-0 rounded-lg border border-success-border bg-success-bg px-4 py-3 sm:mx-6"
            >
              <h3
                id="solution-done-title"
                className="flex items-center gap-2 text-sm font-semibold text-text"
              >
                <Icon name="circleCheck" size={18} className="shrink-0 text-success-text" />
                {t.solutionDoneTitle}
              </h3>
              {session.lastSuccessfulRun ? (
                <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
                  <a
                    href={`/api/sessions/${session.id}/poc/deployable`}
                    download
                    className="btn-brand"
                  >
                    <Icon name="download" size={16} />
                    {t.solutionDoneDownload}
                  </a>
                  <a href={`/sessions/${session.id}/cases`} className="btn-secondary">
                    <Icon name="users" size={16} />
                    {t.solutionDoneTry}
                  </a>
                  <p className="text-xs text-text-secondary">{t.solutionDone}</p>
                </div>
              ) : (
                <p className="mt-1 text-sm text-text-secondary">{t.solutionDoneNoRun}</p>
              )}
              {/* The wizard held for the session is released by the page. */}
              <ReleaseWizardWhenDone sessionId={session.id} replyAhead={replyAhead} />
            </section>
          )}

          {/* Why the step line and the gates went back: read before the
              workspace it changes, not found under it. It was between the
              workspace and the decision bar, where a long diagram or a result
              pushed it to the bottom of the page. */}
          {reopenedNotice}

          <div className="scroll-thin relative flex min-h-0 flex-1 flex-col overflow-y-auto p-4 sm:p-6">
            {isSpec ? (
              // The fields first; the review Gate 1 decides on under them, when
              // the wizard has recorded one and the decision is offered here.
              <>
                <FieldSchemaEditor fields={fieldSpecsFromTargetOutput(session.targetOutputSpec)} t={t} />
                {isGate1 && (
                  <div className="mt-6">
                    <Gate1Review
                      points={points}
                      answers={answers}
                      businessContext={session.businessContext}
                      assumptions={session.assumptions}
                      t={t}
                    />
                  </div>
                )}
              </>
            ) : isGate1 ? (
              <Gate1Review
                points={points}
                answers={answers}
                businessContext={session.businessContext}
                assumptions={session.assumptions}
                t={t}
              />
            ) : isGathering ? (
              <GatheringView
                points={points}
                answers={answers}
                t={t}
              />
            ) : (
              <WorkspacePanel
                sessionId={session.id}
                sessionTitle={session.title}
                // As far on as the wizard's files reach within the stage, so
                // the Workflow tab is there once the diagram is.
                wizardStep={workspaceStep(session)}
                gate2Approved={session.gateStatus[GATE_STEPS[1]] === "approved"}
                blueprint={session.blueprint}
                blueprintVersion={session.activeVersion}
                hasSuccessfulRun={Boolean(session.lastSuccessfulRun)}
                latestRun={session.latestRun ?? null}
                wizardReplying={Boolean(session.pendingTurn)}
                reopenedAt={reopened ? (reopened.at ?? `gate-${reopened.gate}`) : null}
                outputFields={fieldSpecsFromTargetOutput(session.targetOutputSpec)}
                initialTab={parseTabParam(tab)}
                t={t}
              />
            )}
          </div>

          {/* The answer to a button in the bar below (a refused approval)
              stays beside that bar. */}
          {noticeText && (
            <p
              role="status"
              data-testid="action-notice"
              className="mx-4 mt-3 flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-text sm:mx-6"
            >
              <span className="min-w-0 flex-1 basis-64">{noticeText}</span>
              {noticeAction}
            </p>
          )}
          {decisionStep && decisionLabels && (
            <GateDecisionBar
              // A new gate gets a new bar.
              key={decisionStep}
              sessionId={session.id}
              gate={decisionGate}
              gateStep={decisionStep}
              rejected={session.gateStatus[decisionStep] === "rejected"}
              blocked={missing.length > 0}
              missing={
                missing.length > 0 && (
                  <Gate1MissingForm
                    // New fields when what is missing changes.
                    key={missing.join("|")}
                    items={missing}
                    labels={{ intro: t.gate1MissingContext, ...t.gate1Answer }}
                  />
                )
              }
              hadNotice={Boolean(noticeText)}
              packageChanged={packageChanged}
              labels={decisionLabels}
            />
          )}
        </main>
        )}

        <SessionChatDock
          key={session.id}
          sessionId={session.id}
          packageChanged={packageChanged}
          initialMessages={session.messages}
          autoSend={wakeMessage}
          busyLabel={t.chatBusy}
          errorLabels={t.chatErrors}
          activityLabels={t.chatActivity}
          chatTitle={t.chat}
          greeting={chatGreeting}
          aiNotice={t.chatAiNotice}
          assistantLabel={t.chatAssistantLabel}
          inputPlaceholder={t.chatInputPlaceholder}
          inputLabel={t.chatInputLabel}
          sendLabel={t.chatSend}
          streamFailedLabel={t.streamFailed}
          thinkingLabel={t.chatThinking}
          startingLabel={t.chatStarting}
          wizardLive={session.agentLive}
          wide={isGathering}
          lead={chatIsPage}
          leadHeader={
            chatIsPage && (
              <>
                {/* A phone has no room for the gate row; the step line here
                    opens the stages, as it does above the workspace. */}
                <div className="shrink-0 px-4 pt-3 sm:px-6 md:hidden">{stepsDisclosure}</div>
                {leadNotices}
              </>
            )
          }
          hideChatLabel={t.hideChat}
          showChatLabel={t.showChat}
          resizeLabel={t.chatResize}
          questionLabels={t.chatQuestions}
          pendingTurn={session.pendingTurn ?? null}
          defaultOpen={!shouldCollapseChatByDefault(session.step, gateBlocking)}
          // The wizard's reply asks for the approval, so the reply carries it.
          // Not while Gate 1 lacks what it needs: the bar says what is missing.
          gateAction={
            decisionStep && decisionLabels && missing.length === 0
              ? {
                  gateStep: decisionStep,
                  label: decisionLabels.approve,
                  pendingLabel: decisionLabels.approving,
                  hadNotice: Boolean(noticeText),
                  show: { label: t.gateShowMe, name: t.gateShowMeName },
                }
              : undefined
          }
        />
      </div>
    </div>
  );
}
