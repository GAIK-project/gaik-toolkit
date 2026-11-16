"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CaseStrings } from "@/lib/case-strings";
import {
  type Case,
  type CaseModel,
  type CaseRecord,
  type OutputSpec,
  type ProcessNode,
  type StepSegment,
  currentTask,
  isLastInput,
  fieldProblem,
  formFields,
  formatOf,
  humanize,
  isAudioInput,
  isDocument,
  isList,
  isStructured,
  isTable,
  parseInput,
  problemCount,
  rowProblems,
  shapeProcess,
  show,
  stepSegments,
  tableColumns,
  toCsv,
  toMarkdown,
  uncertainField,
} from "@/lib/case-process";
import { AI_FRONT_MATTER, AI_GENERATOR, AI_RECORD_MARK } from "@/lib/ai-marking";
import { caseChatReference, keepChatReference } from "@/lib/case-chat";
import { type AcceptedInput, acceptAttribute, acceptedPhrase, caseErrorText } from "@/lib/case-error";
import { formatValue, valueText } from "@/lib/case-value";
import { fillTemplate } from "@/lib/chat-template";
import { clock, recordingToWav } from "@/lib/recording-wav";
import { formatSize } from "@/lib/poc-run-output";
import { FileIcon } from "./file-icon";
import { GroundingNote, ResultFields } from "./result-value";
import { Icon, type IconName } from "./icons";

type Props = {
  sessionId: string;
  strings: CaseStrings;
  dateLocale: string;
  /** The localized "sandbox is busy" text (lib/i18n pocRunBusy), shown for a 429. */
  busyMessage: string;
};

/** `number` is the api's: a case keeps it when an earlier one is removed. */
type ListedCase = { id: string; created_at: string; status: Case["status"]; round: number; number?: number };

/** What goes along to the wizard's chat with the open case (lib/case-chat). */
type ChatAsk = {
  /** A failed run's own message. */
  failure?: string | null;
  /** What the reviewer wrote when returning the case, or the user when running it again. */
  comment?: string | null;
  /** The comment is the user's own note on a case being run again. */
  rerun?: boolean;
  /** Words put in the chat's field, for the user to send or change. */
  draft?: string;
};

const NO_ACCEPTED: AcceptedInput[] = [];

/** From this many cases still waiting for their input, they fold under one row of the list. */
const FOLD_DRAFTS_FROM = 3;

/**
 * A status as a mark: an icon that says whose turn it is (a file to add, the
 * AI at work, a person to decide) on a disc in the status's colour. A row of
 * the list and the open case's heading carry the same mark.
 */
const STATUS_MARK: Record<Case["status"], { icon: IconName; tone: string; spin?: boolean }> = {
  draft: { icon: "upload", tone: "bg-neutral-bg text-text-muted" },
  running: { icon: "loaderCircle", tone: "bg-brand-soft text-brand", spin: true },
  review: { icon: "userCheck", tone: "bg-warning-bg text-warning-text" },
  returned: { icon: "rotateCcw", tone: "bg-warning-bg text-warning-text" },
  failed: { icon: "circleAlert", tone: "bg-danger-bg text-danger-text" },
  approved: { icon: "check", tone: "bg-success-bg text-success-text" },
  completed: { icon: "check", tone: "bg-success-bg text-success-text" },
  rejected: { icon: "x", tone: "bg-neutral-bg text-text-muted" },
};

function StatusMark({ status, small }: { status: Case["status"]; small?: boolean }) {
  const mark = STATUS_MARK[status];
  return (
    <span className={`flex shrink-0 items-center justify-center rounded-full ${small ? "h-6 w-6" : "h-8 w-8"} ${mark.tone}`} aria-hidden="true">
      <Icon name={mark.icon} size={small ? 13 : 16} className={mark.spin ? "animate-spin" : ""} />
    </span>
  );
}

/** The time now, ticking each second while `active`: for the recording and run clocks. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function download(name: string, type: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/**
 * The icon for a file a step asks for, from the name the blueprint gave it
 * ("Voice Message Audio", "Delivery Note Txt", "Purchase Order PDF").
 */
function wantedIcon(name: string): IconName {
  if (isAudioInput(name)) return "fileHeadphone";
  const lower = name.toLowerCase();
  if (/\b(xlsx?|csv|excel|taulukko|spreadsheet|workbook)\b/.test(lower)) return "fileSpreadsheet";
  if (/\b(png|jpe?g|image|kuva|photo|valokuva|scan)\b/.test(lower)) return "fileImage";
  if (/\bjson\b/.test(lower)) return "fileBraces";
  return "fileText";
}

/** "10.42" for a case made today, "4.11." for an older one: the list needs no more. */
function shortWhen(iso: string, locale: string): string {
  const at = new Date(iso);
  return at.toDateString() === new Date().toDateString()
    ? at.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })
    : at.toLocaleDateString(locale, { day: "numeric", month: "numeric" });
}

export function CaseWorkflow({ sessionId, strings: s, dateLocale, busyMessage }: Props) {
  const base = `/api/sessions/${sessionId}/cases`;
  const back = `/sessions/${sessionId}?tab=poc`;
  const router = useRouter();
  const [model, setModel] = useState<CaseModel | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [cases, setCases] = useState<ListedCase[]>([]);
  const [current, setCurrent] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const accepted = model?.accepted_inputs ?? NO_ACCEPTED;
  // A refusal in the page's language (lib/case-error); the model may arrive
  // after the callbacks that report one were made, hence the ref.
  const acceptedRef = useRef(accepted);
  acceptedRef.current = accepted;
  const detailOf = useCallback(
    async (res: Response) =>
      caseErrorText(res.status, await res.json().catch(() => ({})), s, busyMessage, acceptedRef.current),
    [s, busyMessage],
  );

  const shaped = useMemo(() => (model ? shapeProcess(model.process, model.reviewer) : null), [model]);
  // A case's number is the api's; from an api that gives none, its place in
  // the list, oldest first.
  const numberOf = useMemo(() => new Map(cases.map((c, i) => [c.id, c.number ?? cases.length - i])), [cases]);

  const loadCases = useCallback(async () => {
    const res = await fetch(base, { cache: "no-store" });
    if (!res.ok) return [];
    const listed = ((await res.json()) as { cases: ListedCase[] }).cases;
    setCases(listed);
    return listed;
  }, [base]);

  // Only the latest case asked for is shown: a slower answer to an earlier
  // request must not replace the case the user opened since. Returns whether
  // this answer was the one shown.
  const caseRequest = useRef(0);
  // Set once the user opens or creates a case; the newest case is then not
  // opened for them on load.
  const userPicked = useRef(false);
  const loadCase = useCallback(
    async (id: string): Promise<boolean> => {
      const request = ++caseRequest.current;
      const res = await fetch(`${base}/${id}`, { cache: "no-store" });
      if (request !== caseRequest.current) return false;
      if (!res.ok) {
        setError(await detailOf(res));
        return false;
      }
      const data = (await res.json()) as Case;
      if (request !== caseRequest.current) return false;
      setCurrent(data);
      return true;
    },
    [base, detailOf],
  );

  useEffect(() => {
    (async () => {
      const res = await fetch(`${base}/model`, { cache: "no-store" });
      if (!res.ok) return setModelError(await detailOf(res));
      setModel((await res.json()) as CaseModel);
      const listed = await loadCases();
      // Open the newest case, as a click on it would: the page said "No cases
      // yet" beside a list that had them. Not when the user has opened one.
      if (listed[0] && !userPicked.current) await loadCase(listed[0].id);
    })();
  }, [base, loadCases, loadCase, detailOf]);

  // A running case settles on the server when its run has finished; ask until it has.
  useEffect(() => {
    if (current?.status !== "running") return;
    const timer = setInterval(() => void loadCase(current.id), 4000);
    return () => clearInterval(timer);
  }, [current?.status, current?.id, loadCase]);

  // The other running cases: a case settles only when it is asked for, so one
  // that was sent and left stayed "AI processing" in the list long after its
  // run had finished. Each is asked for until it has settled; the open case
  // has its own, faster clock above.
  const runningElsewhere = cases
    .filter((c) => c.status === "running" && c.id !== current?.id)
    .map((c) => c.id)
    .join(",");
  useEffect(() => {
    if (!runningElsewhere) return;
    const timer = setInterval(async () => {
      await Promise.all(
        runningElsewhere.split(",").map((id) => fetch(`${base}/${id}`, { cache: "no-store" }).catch(() => null)),
      );
      void loadCases();
    }, 8000);
    return () => clearInterval(timer);
  }, [runningElsewhere, base, loadCases]);

  // The list says each case's status, so it is read again when the open case
  // moves on. Keyed on the task, not only the status: one person's input step
  // done moves the case to the next person while it stays a draft.
  const task = shaped && current ? currentTask(shaped, current.status, current.steps_done) : undefined;
  const prevStatus = useRef<string | null>(null);
  useEffect(() => {
    const key = current ? `${current.status}:${task?.id ?? ""}` : null;
    if (!current || prevStatus.current === key) return;
    prevStatus.current = key;
    void loadCases();
  }, [current, task, loadCases]);

  async function act(fn: () => Promise<Response>) {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      if (!res.ok) {
        setError(await detailOf(res));
        return null;
      }
      return res;
    } catch {
      // The request never got an answer (no network, the relay is down).
      setError(s.networkError);
      return null;
    } finally {
      setBusy(false);
    }
  }

  // The open case has nothing in it yet: another "New case" would only add a
  // second empty one. Fourteen empty cases came from one burst of clicks, since
  // the button was free again between the request and the list's reload.
  const openCaseEmpty =
    current?.status === "draft" && current.inputs.length === 0 && !(current.steps_done ?? []).length;
  const [creating, setCreating] = useState(false);

  async function newCase() {
    if (creating || openCaseEmpty) return;
    userPicked.current = true;
    setCreating(true);
    try {
      const res = await act(() => fetch(base, { method: "POST" }));
      if (!res) return;
      const c = (await res.json()) as Case;
      prevStatus.current = null;
      await loadCase(c.id);
      await loadCases();
    } finally {
      setCreating(false);
    }
  }

  function openCase(id: string) {
    userPicked.current = true;
    prevStatus.current = null;
    void loadCase(id);
  }

  // A case still waiting for its input can be removed: nothing else closes
  // one, and each counts against the session's open cases. Asked first, in the
  // row itself; the api refuses a case that has been sent since.
  const [removeAsk, setRemoveAsk] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removedNote, setRemovedNote] = useState<string | null>(null);
  // Where the focus goes when the question closes: back to the row's button
  // after "Cancel", to the list (or the page's title) once the row is gone.
  const refocusRemove = useRef<string | null>(null);
  const listHeading = useRef<HTMLHeadingElement>(null);
  const pageTitle = useRef<HTMLHeadingElement>(null);

  async function removeCase(id: string) {
    const number = numberOf.get(id);
    const wasOpen = current?.id === id;
    // Its own "busy", not the page's: the open case's send button would say
    // "Lähetetään…" while another case is removed.
    setRemoving(true);
    setError(null);
    try {
      let res: Response;
      try {
        res = await fetch(`${base}/${id}`, { method: "DELETE" });
      } catch {
        // No answer: the question stays open, to try again.
        setError(s.networkError);
        return;
      }
      setRemoveAsk(null);
      // Read again either way: a refused case shows the status it has now.
      const listed = await loadCases();
      if (!res.ok) {
        setError(await detailOf(res));
        return;
      }
      setRemovedNote(fillTemplate(s.caseRemoved, { n: String(number ?? "") }));
      if (wasOpen) {
        // An answer still on its way for the removed case must not bring it back.
        caseRequest.current += 1;
        prevStatus.current = null;
        setCurrent(null);
        if (listed[0]) await loadCase(listed[0].id);
      }
      (listHeading.current ?? pageTitle.current)?.focus();
    } finally {
      setRemoving(false);
    }
  }

  // The solution itself is changed in the wizard's chat (lib/case-chat): the
  // open case goes along as the chip above the field, and a failed run's
  // message or the reviewer's comment as the quote, with words the user can
  // send as they are.
  function changeInChat({ failure, comment, rerun, draft }: ChatAsk = {}) {
    const number = current ? numberOf.get(current.id) : undefined;
    const reference = caseChatReference(
      sessionId,
      current && number ? { number, status: s.status[current.status], failure, comment, rerun } : null,
      s.chat,
    );
    const words = draft ?? (failure ? s.askFixDraft : undefined);
    keepChatReference(sessionId, words ? { ...reference, draft: words } : reference);
    router.push(back);
  }

  const head = (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
      <Link href={back} className="icon-btn -ml-1.5" aria-label={s.back} title={s.back} data-testid="case-back">
        <Icon name="arrowLeft" size={18} />
      </Link>
      <h2
        ref={pageTitle}
        tabIndex={-1}
        className="min-w-0 flex-1 basis-56 text-xl font-semibold tracking-tight text-text [overflow-wrap:anywhere] focus:outline-none"
      >
        {model?.title}
      </h2>
      {model && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => changeInChat()}
            title={s.changeInChatHint}
            data-testid="case-change-in-chat"
          >
            <Icon name="messageSquareText" size={16} />
            {s.changeInChat}
          </button>
          <button
            type="button"
            className="btn-brand"
            onClick={newCase}
            disabled={busy || creating || openCaseEmpty || !model.package_ready}
            title={openCaseEmpty ? s.emptyCase : undefined}
            aria-describedby={openCaseEmpty ? "case-new-why" : undefined}
            data-testid="case-new"
          >
            <Icon name={creating ? "loaderCircle" : "plus"} size={16} className={creating ? "animate-spin" : ""} />
            {s.newCase}
          </button>
          {openCaseEmpty && (
            <span id="case-new-why" className="sr-only">
              {s.emptyCase}
            </span>
          )}
        </div>
      )}
    </div>
  );

  if (modelError) {
    return (
      <div className="flex flex-col gap-4">
        {head}
        <p className="rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-text" role="alert">
          {s.loadError} {modelError}
        </p>
      </div>
    );
  }
  if (!model || !shaped) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        {head}
        <div className="h-40 animate-pulse rounded-lg border border-border bg-surface" />
      </div>
    );
  }

  const roleName = (id: string | null | undefined) =>
    model.process.lanes.find((l) => l.id === id)?.name ?? s.aiRole;

  // Cases still waiting for their input are the least interesting rows, and a
  // session can hold dozens of them. From a few up they fold under one row;
  // the open case always stays in sight.
  const waiting = cases.filter((c) => c.status === "draft" && c.id !== current?.id);
  const fold = waiting.length >= FOLD_DRAFTS_FROM;
  const listed = fold ? cases.filter((c) => c.status !== "draft" || c.id === current?.id) : cases;
  const row = (c: ListedCase, plain = false) => {
    const open = current?.id === c.id;
    const number = numberOf.get(c.id);
    if (removeAsk === c.id) {
      const cancel = () => {
        refocusRemove.current = c.id;
        setRemoveAsk(null);
      };
      return (
        <li key={c.id}>
          <div
            role="group"
            aria-labelledby={`case-remove-ask-${c.id}`}
            onKeyDown={(e) => {
              if (e.key === "Escape") cancel();
            }}
            className="case-in rounded-lg border border-danger-border bg-danger-bg px-2.5 py-2 text-sm"
            data-testid="case-remove-ask"
          >
            <p id={`case-remove-ask-${c.id}`} className="text-text">
              {fillTemplate(s.removeCaseAsk, { n: String(number ?? "") })}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-secondary px-3 py-1.5 text-danger-text"
                disabled={removing}
                onClick={() => void removeCase(c.id)}
                data-testid="case-remove-confirm"
              >
                <Icon name={removing ? "loaderCircle" : "trash2"} size={15} className={removing ? "animate-spin" : ""} />
                {s.remove}
              </button>
              {/* The focus lands on the way out, not on the removal. */}
              <button type="button" className="btn-ghost px-3 py-1.5" autoFocus onClick={cancel} data-testid="case-remove-cancel">
                {s.cancel}
              </button>
            </div>
          </div>
        </li>
      );
    }
    return (
      // The row is one surface: the case and, on a waiting one, its bin.
      <li
        key={c.id}
        className={`group/row flex items-center rounded-lg border transition-colors duration-150 ${
          open ? "border-brand-soft-border bg-brand-soft" : "border-transparent hover:bg-surface-muted"
        }`}
      >
        <button
          type="button"
          onClick={() => openCase(c.id)}
          aria-current={open ? "true" : undefined}
          title={new Date(c.created_at).toLocaleString(dateLocale, { dateStyle: "short", timeStyle: "short" })}
          data-testid="case-row"
          className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-lg text-left transition-transform duration-150 active:scale-[0.99] ${plain ? "px-2 py-1.5" : "px-2 py-2"}`}
        >
          <StatusMark status={c.status} small={plain} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium tabular-nums text-text">
              {s.caseLabel} {number}
            </span>
            <span className={plain ? "sr-only" : "block truncate text-xs text-text-muted"}>{s.status[c.status]}</span>
          </span>
          <time dateTime={c.created_at} className="shrink-0 text-xs tabular-nums text-text-muted">
            {shortWhen(c.created_at, dateLocale)}
          </time>
        </button>
        {/* Only a case that was never sent: one with a run or a decision stays. */}
        {c.status === "draft" && (
          <button
            type="button"
            ref={(el) => {
              if (el && refocusRemove.current === c.id) {
                refocusRemove.current = null;
                el.focus();
              }
            }}
            className="icon-btn mr-1 h-7 w-7 hover:bg-danger-bg hover:text-danger-text"
            aria-label={`${s.removeCase} ${number}`}
            title={s.removeCase}
            onClick={() => setRemoveAsk(c.id)}
            data-testid="case-remove"
          >
            <Icon name="trash2" size={14} />
          </button>
        )}
      </li>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {head}

      {!model.package_ready && (
        <p className="rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-text">
          {s.notReady} {model.package_problems.join("; ")}
        </p>
      )}
      {error && (
        <p className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-sm text-danger-text" role="alert">
          {error}
        </p>
      )}
      {/* Mounted empty, as the review's note is: the row is gone, and this says which. */}
      <p role="status" className="sr-only" data-testid="case-removed">
        {removedNote}
      </p>

      {/* One case needs no list: the list is for choosing between cases. */}
      <div className={`grid items-start gap-4 ${cases.length > 1 ? "lg:grid-cols-[288px_minmax(0,1fr)]" : ""}`}>
        {cases.length > 1 && (
          <aside className="rounded-lg border border-border bg-surface p-2 lg:sticky lg:top-4" data-testid="case-list">
            <h3 ref={listHeading} tabIndex={-1} className="px-2 pb-1.5 pt-1 text-sm font-semibold text-text focus:outline-none">
              {s.cases}
            </h3>
            {/* Above the task on a narrow screen: a long list scrolls in its
                own box there, so the task is not fifteen rows down the page. */}
            <div className="scroll-thin max-h-44 overflow-y-auto lg:max-h-[calc(100dvh-11rem)]">
              <ul className="flex flex-col gap-1">{listed.map((c) => row(c))}</ul>
              {fold && (
                <details className="group mt-1 border-t border-border pt-1" data-testid="case-waiting">
                  <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md px-2 py-1.5 text-sm text-text-muted transition-colors hover:bg-surface-muted [&::-webkit-details-marker]:hidden">
                    <Icon name="chevronRight" size={14} className="shrink-0 transition-transform group-open:rotate-90" />
                    <span className="min-w-0 flex-1 truncate">{s.status.draft}</span>
                    <span className="text-xs tabular-nums">{waiting.length}</span>
                  </summary>
                  <ul className="flex flex-col gap-0.5">{waiting.map((c) => row(c, true))}</ul>
                </details>
              )}
            </div>
          </aside>
        )}

        {current ? (
          <CaseView
            key={current.id}
            caseData={current}
            number={numberOf.get(current.id)}
            model={model}
            shaped={shaped}
            roleName={roleName}
            base={`${base}/${current.id}`}
            accepted={accepted}
            s={s}
            dateLocale={dateLocale}
            busy={busy}
            act={act}
            problemOf={detailOf}
            changeInChat={changeInChat}
            reload={async () => {
              await loadCase(current.id);
            }}
          />
        ) : (
          <div className="rounded-lg border border-dashed border-border-strong p-8 text-center text-sm text-text-muted">
            {cases.length > 0 ? s.pickCase : s.noCases}
          </div>
        )}
      </div>
    </div>
  );
}

type ViewProps = {
  caseData: Case;
  /** The case's number in the list; absent until the list has it. */
  number?: number;
  model: CaseModel;
  shaped: ReturnType<typeof shapeProcess>;
  roleName: (id: string | null | undefined) => string;
  base: string;
  /** The file types an input upload accepts; empty when the api named none. */
  accepted: AcceptedInput[];
  s: CaseStrings;
  dateLocale: string;
  busy: boolean;
  act: (fn: () => Promise<Response>) => Promise<Response | null>;
  /** A refusal in the page's language (lib/case-error). */
  problemOf: (res: Response) => Promise<string>;
  /** Back to the wizard's chat, to change the solution; with a failed run's message or the reviewer's comment. */
  changeInChat: (ask?: ChatAsk) => void;
  reload: () => Promise<void>;
};

/**
 * Where the case is: each person's step, and the AI's steps between them as
 * one segment. Every segment is a bar; only the current one is written out,
 * since that is the one the page is about. The others say what they are on
 * hover and to a screen reader.
 */
function Stepper({ segments, roleName, s }: { segments: StepSegment[]; roleName: ViewProps["roleName"]; s: CaseStrings }) {
  // A finished or rejected case has no current segment: its bars share the row.
  const anyCurrent = segments.some((seg) => seg.state === "current");
  return (
    <ol className="flex gap-1.5 px-4 pb-4 pt-3 sm:px-5" aria-label={s.steps} data-testid="case-steps">
      {segments.map((seg) => {
        const current = seg.state === "current";
        const done = seg.state === "done";
        const label = seg.human ? seg.nodes[0].name : s.aiRole;
        const detail = seg.human ? roleName(seg.nodes[0].lane) : seg.nodes.map((n) => n.name).join(", ");
        return (
          <li
            key={seg.key}
            aria-current={current ? "step" : undefined}
            title={`${label}: ${detail}`}
            className={`min-w-0 ${current ? "flex-[4]" : anyCurrent ? "flex-1 max-sm:w-7 max-sm:flex-none" : "flex-1"}`}
          >
            <span className={`block h-1 rounded-full ${done ? "bg-success-text" : current ? "bg-brand" : "bg-border"}`} />
            <span className={`mt-2 flex items-start gap-1.5 text-xs ${current ? "" : "sr-only"}`}>
              <Icon
                name={done ? "check" : seg.human ? "userCheck" : "brain"}
                size={14}
                className={`mt-px shrink-0 ${done ? "text-success-text" : current ? "text-brand" : "text-text-muted"}`}
              />
              <span className="min-w-0">
                <span className={`block truncate ${current ? "font-semibold text-text" : "text-text-secondary"}`}>{label}</span>
                <span className="block truncate text-text-muted">{detail}</span>
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function CaseView(p: ViewProps) {
  const { caseData: c, shaped, s } = p;
  const task = currentTask(shaped, c.status, c.steps_done);
  // While the input is being given or corrected, the files of that step are
  // in the form itself: beside it they were listed, and played, a second
  // time. The source beside the task keeps the rest: the other steps' files
  // and what the last run made of them (the transcript), which the person
  // correcting a returned case reads the comment against.
  const editing = c.status === "draft" || c.status === "returned" || c.status === "failed";
  const firstInput = shaped.inputTasks[0];
  const beside =
    c.status === "draft"
      ? []
      : editing
        ? c.inputs.filter((f) => (f.task ?? firstInput?.id) !== task?.id)
        : c.inputs;
  const hasSource = beside.length > 0 || (c.status !== "draft" && Boolean(c.result?.transcript));
  // With no source to show, what is left (the events) goes under the task.
  const eventsOnly = editing && !hasSource;
  const hasSide = eventsOnly ? c.events.length > 0 : hasSource || Boolean(c.record) || c.events.length > 0;
  // What the last review did, said once for a screen reader: the view switches
  // to the result or back to the input, and its heading says the rest.
  const [reviewed, setReviewed] = useState<ReviewAction | null>(null);
  // Since the case was sent to the AI: a wait of minutes needs a clock.
  const running = c.status === "running";
  const now = useNow(running);
  const sentAt = running ? c.events.findLast((e) => e.action === "submit")?.at : undefined;
  const reviewNote =
    reviewed && REVIEW_STATUS[reviewed] === c.status
      ? reviewed === "approve"
        ? s.reviewedApprove
        : reviewed === "reject"
          ? s.reviewedReject
          : reviewed === "rerun"
            ? s.reviewedRerun
            : s.reviewedReturn
      : null;

  return (
    <section className="case-in min-w-0 rounded-lg border border-border bg-surface" aria-labelledby="case-heading">
      <header className="flex items-center gap-3 px-4 pt-4 sm:px-5">
        <StatusMark status={c.status} />
        <div className="min-w-0">
          <h3 id="case-heading" className="font-semibold leading-tight text-text">
            {s.caseLabel}
            {p.number ? ` ${p.number}` : ""}
          </h3>
          <p className="text-sm text-text-muted" data-testid="case-status">
            {s.status[c.status]}
            {c.round > 1 ? `, ${s.roundLabel} ${c.round}` : ""}
          </p>
        </div>
      </header>
      <Stepper segments={stepSegments(shaped, c.status, c.steps_done)} roleName={p.roleName} s={s} />

      {/* The source and the events beside the task only once there are some:
          empty, they left the task in half the width beside a blank column. */}
      <div className={`grid border-t border-border ${hasSide && !eventsOnly ? "xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]" : ""}`}>
        <div className="min-w-0 p-4 sm:p-5">
          {/* Mounted empty: a live region that arrives with its text is often not read out. */}
          <p role="status" className="sr-only" data-testid="case-reviewed">
            {reviewNote}
          </p>
          {running ? (
            <div data-testid="case-running">
              {/* The status is announced once; the clock below ticks every
                  second and stays outside the live region, or a screen reader
                  would read it out each time. */}
              <div role="status">
                <h4 className="flex items-center gap-2 font-semibold text-text">
                  <Icon name="loaderCircle" size={16} className="animate-spin text-brand" />
                  {s.aiRunning}
                </h4>
                <p className="mt-1 text-sm text-text-muted">{c.run_phase === "pending" ? s.aiQueued : s.aiRunningHint}</p>
              </div>
              {sentAt && (
                <p className="mt-2 text-xs tabular-nums text-text-muted" data-testid="case-elapsed">
                  {s.elapsed} {clock((now - new Date(sentAt).getTime()) / 1000)}
                </p>
              )}
            </div>
          ) : c.status === "approved" || c.status === "rejected" || c.status === "completed" ? (
            <DoneView {...p} />
          ) : task && shaped.inputTasks.includes(task) ? (
            <InputView key={task.id} {...p} task={task} />
          ) : c.status === "review" ? (
            <ReviewView {...p} onReviewed={setReviewed} />
          ) : (
            // A process that starts with an AI step has no input task: nothing
            // here is a person's to do, and a failed run still says why.
            <div data-testid="case-no-task">
              <p className="text-sm text-text-secondary">{s.noTask}</p>
              {c.status === "failed" && (
                <p className="mt-2 rounded-md border-l-4 border-danger-border bg-danger-bg px-3 py-2 text-sm [overflow-wrap:anywhere]">
                  <b>{s.failed}:</b> {c.run_message}
                </p>
              )}
              <button
                type="button"
                className="mt-3 inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-brand-text underline-offset-2 hover:underline"
                onClick={() => p.changeInChat({ failure: c.status === "failed" ? c.run_message || s.status.failed : null })}
              >
                <Icon name="messageSquareText" size={14} />
                {s.changeInChat}
              </button>
            </div>
          )}
        </div>
        {hasSide && <SourceView {...p} files={beside} eventsOnly={eventsOnly} />}
      </div>
    </section>
  );
}

function InputView(p: ViewProps & { task: ProcessNode }) {
  const { caseData: c, s, base } = p;
  const [note, setNote] = useState(c.notes?.[p.task.id] ?? "");
  const first = p.shaped.inputTasks[0];
  // A file belongs to the step that uploaded it; untagged files to the first step.
  const mine = c.inputs.filter((f) => (f.task ?? first?.id) === p.task.id);
  const last = isLastInput(p.shaped, p.task);
  const earlier = p.shaped.inputTasks.filter((n) => n !== p.task && (c.steps_done ?? []).includes(n.id));
  const returnedHere = c.status === "returned" && (c.return_to ?? first?.id) === p.task.id;
  // Run again by the person's own choice (the api says which it was): there
  // is something to tell only when they left themselves a note.
  const rerun = Boolean(c.rerun);
  const showReturned = returnedHere && (!rerun || Boolean(c.comment?.trim()));
  // Who returned it: the role the decision was posted under.
  const returnedBy = returnedHere ? c.events.findLast((e) => e.action === "return")?.role?.trim() : undefined;
  const [uploading, setUploading] = useState(false);
  const [recorder, setRecorder] = useState<MediaRecorder | null>(null);
  const [recordedFrom, setRecordedFrom] = useState(0);
  const [micProblem, setMicProblem] = useState<string | null>(null);
  const now = useNow(!!recorder);
  const fileRef = useRef<HTMLInputElement>(null);
  // A recording is sent as WAV, so it is offered only where WAV is accepted
  // (an api that names no types is taken at the step's word).
  const audio =
    p.task.outputs.some(isAudioInput) &&
    (p.accepted.length === 0 || p.accepted.some((a) => a.extensions.includes(".wav")));
  const acceptedTypes = acceptedPhrase(p.accepted, s.or);

  // A refused file is said here, under the buttons that added it: the page's
  // own error line is above the list, out of sight of the person at this box.
  const [uploadProblem, setUploadProblem] = useState<string | null>(null);

  async function upload(files: File[]) {
    setUploading(true);
    setUploadProblem(null);
    try {
      for (const f of files) {
        const form = new FormData();
        form.append("file", f, f.name);
        form.append("task", p.task.id);
        const res = await fetch(`${base}/inputs`, { method: "POST", body: form });
        if (!res.ok) {
          const problem = `${f.name}: ${await p.problemOf(res)}`;
          setUploadProblem((earlier) => (earlier ? `${earlier}\n${problem}` : problem));
        }
      }
    } catch {
      // The request got no answer (no network): the buttons stayed disabled
      // under "Ladataan…" until the page was reloaded.
      setUploadProblem(s.networkError);
    } finally {
      setUploading(false);
    }
    await p.reload();
  }

  async function record() {
    setMicProblem(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecorder(null);
        // The browser records WebM, Ogg or MP4; the input check takes WAV, MP3
        // and M4A, so the recording is written as WAV before it is sent.
        setUploading(true);
        try {
          const wav = await recordingToWav(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
          await upload([wav]);
        } catch {
          setMicProblem(s.recordingFailed);
          setUploading(false);
        }
      };
      rec.start();
      setRecordedFrom(Date.now());
      setRecorder(rec);
    } catch {
      // Said on the page, beside the buttons: an alert box stopped the page
      // and named no place to go on from.
      setMicProblem(s.micError);
    }
  }

  const [dragging, setDragging] = useState(false);
  const [noteOpen, setNoteOpen] = useState(Boolean(c.notes?.[p.task.id]));
  const wanted = p.task.outputs.filter(Boolean);
  // Who reads a note: the next person in the input steps, or the reviewer. A
  // "message to the approver" named nobody, and was offered to a person who
  // reviews their own input.
  const nextTask = last ? p.shaped.reviewTask : p.shaped.inputTasks[p.shaped.inputTasks.indexOf(p.task) + 1];
  // By name: two lanes can carry one role's name.
  const reader = nextTask && p.roleName(nextTask.lane) !== p.roleName(p.task.lane) ? p.roleName(nextTask.lane) : null;
  const blocked = uploading || !!recorder;

  return (
    <div className="flex flex-col gap-4" data-testid="case-input">
      {/* The stepper above already names the step; a second visible heading
          said it twice. */}
      <h4 className="sr-only">{p.task.name}</h4>
      {/* Why the case is back at this step, in plain text above the input:
          who said what, and the other way on when the input is not at fault. */}
      {showReturned && (
        <div className="flex gap-2.5 border-b border-border pb-4 text-sm" data-testid="case-returned">
          <Icon name="rotateCcw" size={16} className="mt-0.5 shrink-0 text-warning-text" />
          <div className="min-w-0">
            <p className="font-medium text-text">{rerun ? s.rerunNote : returnedBy ? fillTemplate(s.returnedBy, { role: returnedBy }) : s.returned}</p>
            <p className="mt-0.5 text-text-secondary [overflow-wrap:anywhere]" data-testid="case-returned-comment">{c.comment}</p>
            {/* New input cures a wrong recording or document. When the comment
                asks for another field, step or rule, the solution is what must
                change, and that is asked of the wizard: the comment goes along
                as a quote, as a failed run's error does below. */}
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-1.5 rounded-sm font-medium text-brand-text underline-offset-2 hover:underline"
              onClick={() => p.changeInChat({ comment: c.comment, rerun, draft: s.askFixReturnedDraft })}
              data-testid="case-ask-fix-returned"
            >
              <Icon name="messageSquareText" size={14} />
              {s.askFix}
            </button>
          </div>
        </div>
      )}
      {c.status === "failed" && (
        <div className="flex gap-2.5 border-b border-border pb-4 text-sm" data-testid="case-failed">
          <Icon name="circleAlert" size={16} className="mt-0.5 shrink-0 text-danger-text" />
          <div className="min-w-0">
            <p className="font-medium text-text">{s.failed}</p>
            <p className="mt-0.5 text-text-secondary [overflow-wrap:anywhere]">{c.run_message}</p>
            {/* A run that fails on good input is the solution's fault, and the
                solution is changed in the chat: the error goes along as a quote. */}
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-1.5 rounded-sm font-medium text-brand-text underline-offset-2 hover:underline"
              onClick={() => p.changeInChat({ failure: c.run_message || s.status.failed })}
              data-testid="case-ask-fix"
            >
              <Icon name="messageSquareText" size={14} />
              {s.askFix}
            </button>
          </div>
        </div>
      )}
      {earlier.length > 0 && (
        <div className="text-sm" data-testid="case-earlier">
          <span className="font-medium text-text-secondary">{s.earlierSteps}</span>
          <ul className="mt-1 flex flex-col gap-0.5 text-text-muted">
            {earlier.map((n) => (
              <li key={n.id}>
                <span className="text-text">{p.roleName(n.lane)}</span>, {n.name}: {c.inputs.filter((f) => (f.task ?? first?.id) === n.id).map((f) => f.name).join(", ") || "—"}
                {c.notes?.[n.id] ? ` · “${c.notes[n.id]}”` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {/* One box for the step's input: the files added so far as its rows,
          and under them the row that adds one. A file can be dropped anywhere
          on the box. */}
      <div>
        <div
          onDragOver={(e) => {
            if (!e.dataTransfer.types.includes("Files")) return;
            // Always, or the browser opens the dropped file in this tab and a
            // recording under way is lost.
            e.preventDefault();
            if (!blocked) setDragging(true);
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (blocked) return;
            const files = Array.from(e.dataTransfer.files);
            if (files.length) void upload(files);
          }}
          className={`rounded-lg border transition-colors ${dragging ? "border-brand bg-brand-soft" : "border-border-strong bg-app"}`}
          data-testid="case-drop"
        >
          {mine.length > 0 && (
            <ul className="divide-y divide-border border-b border-border" data-testid="case-inputs">
              {mine.map((f) => (
                <li key={f.name} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 text-sm">
                  <FileIcon name={f.name} size={16} />
                  <span className="min-w-0 flex-1 font-mono text-xs [overflow-wrap:anywhere]">{f.name}</span>
                  <span className="shrink-0 text-xs tabular-nums text-text-muted">{formatSize(f.bytes)}</span>
                  <button
                    type="button"
                    className="icon-btn h-7 w-7 hover:text-danger-text"
                    aria-label={`${s.remove} ${f.name}`}
                    title={s.remove}
                    onClick={async () => { await p.act(() => fetch(`${base}/inputs/${encodeURIComponent(f.name)}`, { method: "DELETE" })); await p.reload(); }}
                  >
                    <Icon name="trash2" size={15} />
                  </button>
                  {/* The player takes its own row: beside the name it squeezed the name to one letter a line. */}
                  {/\.(wav|mp3|m4a|ogg|webm)$/i.test(f.name) && (
                    <audio controls src={`${base}/inputs/${encodeURIComponent(f.name)}`} className="h-8 w-full basis-full" />
                  )}
                </li>
              ))}
            </ul>
          )}
          {/* What is needed on the left, the ways to add it on the right; the
              row is taller while the box is empty, as the step's one target. */}
          <div className={`flex flex-wrap items-center gap-x-4 gap-y-3 px-3 ${mine.length > 0 ? "py-2.5" : "py-6 sm:px-5"}`}>
            <Icon name={dragging ? "upload" : wantedIcon(String(wanted[0] ?? ""))} size={mine.length > 0 ? 16 : 22} className="shrink-0 text-brand-text" />
            <div className="min-w-0 flex-1 basis-40">
              {wanted.length > 0 && (
                <p className="text-sm font-medium text-text" data-testid="case-needs">
                  {wanted.join(", ")}
                </p>
              )}
              {/* Dropping needs a pointer; a touch screen has only the buttons. */}
              <p className="text-sm text-text-muted max-sm:hidden">{s.dropHint}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {audio && (recorder ? (
                <button type="button" className="btn-secondary text-danger-text" onClick={() => recorder.stop()} data-testid="case-record-stop">
                  <span className="h-2.5 w-2.5 rounded-full bg-danger-text animate-pulse" /> {s.stop}
                  <span className="tabular-nums">{clock((now - recordedFrom) / 1000)}</span>
                </button>
              ) : (
                <button type="button" className="btn-secondary" onClick={record} disabled={uploading} data-testid="case-record">
                  <Icon name="mic" size={16} />
                  {s.record}
                </button>
              ))}
              <button type="button" className="btn-secondary" onClick={() => fileRef.current?.click()} disabled={blocked} data-testid="case-upload">
                <Icon name={uploading ? "loaderCircle" : "upload"} size={16} className={uploading ? "animate-spin" : ""} />
                {uploading ? s.uploading : s.upload}
              </button>
              <input
                ref={fileRef}
                type="file"
                multiple
                hidden
                accept={acceptAttribute(p.accepted) || undefined}
                data-testid="case-file"
                onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; if (files.length) void upload(files); }}
              />
            </div>
          </div>
        </div>
        {micProblem && (
          <p className="mt-2 text-sm text-danger-text" role="alert" data-testid="case-mic-problem">{micProblem}</p>
        )}
        {uploadProblem && (
          <p className="mt-2 flex items-start gap-1.5 whitespace-pre-line text-sm text-danger-text [overflow-wrap:anywhere]" role="alert" data-testid="case-upload-problem">
            <Icon name="circleAlert" size={15} className="mt-0.5 shrink-0" />
            {uploadProblem}
          </p>
        )}
        <p className="mt-2 text-xs text-text-muted" data-testid="case-upload-reminder">
          {acceptedTypes && <span data-testid="case-accepted-types">{s.acceptedTypes}: {acceptedTypes}. </span>}
          {s.uploadReminder}
          {/* Which files a task takes is the solution's, so another type is a
              change to ask the wizard for: its chat opens with the words begun. */}
          {acceptedTypes && (
            <>
              {" "}
              <button
                type="button"
                className="rounded font-medium text-brand-text underline-offset-2 hover:underline"
                onClick={() => p.changeInChat({ draft: s.askFileTypesDraft })}
                data-testid="case-ask-file-types"
              >
                {s.askFileTypes}
              </button>
            </>
          )}
        </p>
      </div>
      {noteOpen && reader && (
        <label className="block">
          <span className="field-label">{fillTemplate(s.note, { role: reader })}</span>
          {/* Opened by its button, so the cursor goes where the button promised. */}
          <textarea className="input-field min-h-16" value={note} onChange={(e) => setNote(e.target.value)} autoFocus={!c.notes?.[p.task.id]} data-testid="case-note" />
        </label>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          className="btn-brand"
          data-testid="case-submit"
          disabled={p.busy || blocked || mine.length === 0}
          title={mine.length === 0 ? s.inputMissing : undefined}
          onClick={async () => {
            const body = JSON.stringify({ task: p.task.id, role: p.roleName(p.task.lane), note });
            const res = await p.act(() =>
              fetch(`${base}/${last ? "submit" : "step"}`, { method: "POST", headers: { "Content-Type": "application/json" }, body }),
            );
            if (res) await p.reload();
          }}
        >
          <Icon name={p.busy ? "loaderCircle" : last ? "send" : "arrowRight"} size={16} className={p.busy ? "animate-spin" : ""} />
          {p.busy ? s.submitting : last ? s.submit : s.stepDone}
        </button>
        {reader && !noteOpen && (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-text-secondary underline-offset-2 transition-colors hover:text-brand-text hover:underline"
            onClick={() => setNoteOpen(true)}
            data-testid="case-add-note"
          >
            <Icon name="plus" size={14} />
            {fillTemplate(s.addNote, { role: reader })}
          </button>
        )}
      </div>
    </div>
  );
}

type ReviewAction = "approve" | "return" | "rerun" | "reject";
/** The status a review action leaves the case in (case_service.review). */
const REVIEW_STATUS: Record<ReviewAction, Case["status"]> = {
  approve: "approved",
  return: "returned",
  rerun: "returned",
  reject: "rejected",
};

function ReviewView(p: ViewProps & { onReviewed: (action: ReviewAction) => void }) {
  const { caseData: c, model, s, base } = p;
  const original = (c.result?.record ?? {}) as CaseRecord | CaseRecord[];
  const [rec, setRec] = useState<CaseRecord | CaseRecord[]>(() => structuredClone(c.record ?? original));
  const [ask, setAsk] = useState<null | "return" | "reject">(null);
  const [comment, setComment] = useState("");
  const [returnTo, setReturnTo] = useState<string>(p.shaped.inputTasks[0]?.id ?? "");
  const doc = isDocument(rec);
  const bad = doc ? docProblems(rec as CaseRecord) : problemCount(model.spec, rec);
  // The diagram may have lost its review task since the case settled: the
  // decision is still a person's, so it is not posted under the AI's name.
  const reviewer = p.shaped.reviewTask ? p.roleName(p.shaped.reviewTask.lane) : (p.shaped.roles[0]?.name ?? s.reviewTitle);

  async function send(action: ReviewAction) {
    const res = await p.act(() =>
      fetch(`${base}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          role: reviewer,
          comment: comment.trim(),
          record: action === "approve" ? rec : null,
          return_to: action === "return" || action === "rerun" ? returnTo : null,
        }),
      }),
    );
    if (!res) return;
    p.onReviewed(action);
    await p.reload();
  }

  // Something to undo: the reviewer's values differ from the AI's.
  const changed = JSON.stringify(rec) !== JSON.stringify(original);

  return (
    <div className="flex flex-col gap-4" data-testid="case-review">
      <h4 className="font-semibold text-text">{p.shaped.reviewTask?.name ?? s.reviewTitle}</h4>
      {p.shaped.inputTasks
        .filter((n) => c.notes?.[n.id] || (n === p.shaped.inputTasks.at(-1) && c.note && !c.notes?.[n.id]))
        .map((n) => (
          <p key={n.id} className="rounded-md border-l-4 border-info-border bg-info-bg px-3 py-2 text-sm">
            {p.roleName(n.lane)}: “{c.notes?.[n.id] || c.note}”
          </p>
        ))}
      {doc ? (
        <DocumentEditor rec={rec as CaseRecord} original={original as CaseRecord} setRec={setRec} s={s} />
      ) : Array.isArray(rec) ? (
        <div className="flex flex-col gap-4">
          {rec.map((item, i) => (
            <fieldset key={i} className="rounded-md border border-border p-3">
              <legend className="px-1 text-sm font-semibold">{s.item} {i + 1}</legend>
              <RecordForm
                spec={model.spec}
                rec={item}
                original={((original as CaseRecord[])[i] ?? {}) as CaseRecord}
                setRec={(next) => setRec(rec.map((x, j) => (j === i ? next : x)))}
                s={s}
              />
            </fieldset>
          ))}
        </div>
      ) : (
        <RecordForm spec={model.spec} rec={rec} original={original as CaseRecord} setRec={setRec} s={s} />
      )}
      {/* What a person trying the solution does with a result: it is done,
          or it is run again on other input. Rejecting belongs to the process's
          reviewer role and is rarely wanted, so it sits behind "Muut". What
          stands in the way of "Valmis" is said beside it. */}
      <div className="flex flex-col gap-3 border-t border-border pt-4">
        {bad > 0 && (
          <p className="flex items-center gap-1.5 text-sm text-danger-text" data-testid="case-problems">
            <Icon name="circleAlert" size={15} className="shrink-0" />
            {bad === 1 ? s.fixOne : fillTemplate(s.fixMany, { n: String(bad) })}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-brand" data-testid="case-approve" aria-describedby="case-hint-approve" disabled={p.busy || bad > 0} onClick={() => send("approve")}>
            <Icon name="check" size={16} />
            {s.approve}
          </button>
          <button type="button" className="btn-secondary" data-testid="case-return" aria-describedby="case-hint-return" aria-expanded={ask === "return"} onClick={() => { setAsk(ask === "return" ? null : "return"); setComment(""); }}>
            <Icon name="rotateCcw" size={16} />
            {s.returnForFix}
          </button>
          {changed && (
            <button
              type="button"
              className="ml-auto rounded-sm text-sm font-medium text-text-secondary underline-offset-2 transition-colors hover:text-text hover:underline"
              onClick={() => setRec(structuredClone(original))}
              data-testid="case-restore-all"
            >
              {s.restoreAll}
            </button>
          )}
        </div>
        {/* What each of the two leads to, each the description of its button. */}
        <ul className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-text-muted" data-testid="case-decision-hints">
          {(["approve", "return"] as const).map((action) => (
            <li key={action} id={`case-hint-${action}`}>
              <span className="font-medium text-text-secondary">{s.decisionHints[action].lead}:</span>{" "}
              {s.decisionHints[action].text}
            </li>
          ))}
        </ul>
      </div>
      {ask && (
        <div className="case-in flex flex-col gap-2 rounded-lg border border-border-strong p-3">
          <label className="field-label mb-0" htmlFor="case-comment">{ask === "return" ? s.askReturn : s.askReject}</label>
          <textarea id="case-comment" className="input-field" value={comment} onChange={(e) => setComment(e.target.value)} autoFocus />
          {ask === "return" && p.shaped.inputTasks.length > 1 && (
            <label className="block">
              <span className="field-label">{s.returnTo}</span>
              <select className="input-field" value={returnTo} onChange={(e) => setReturnTo(e.target.value)} data-testid="case-return-to">
                {p.shaped.inputTasks.map((n) => (
                  <option key={n.id} value={n.id}>{p.roleName(n.lane)} – {n.name}</option>
                ))}
              </select>
            </label>
          )}
          <div className="flex gap-2">
            {/* Running again needs no reason; rejecting does (the api asks for one). */}
            <button type="button" className="btn-brand" data-testid="case-confirm" disabled={(ask === "reject" && !comment.trim()) || p.busy} onClick={() => send(ask === "return" ? "rerun" : "reject")}>
              {ask === "return" ? s.rerunConfirm : s.confirm}
            </button>
            <button type="button" className="btn-ghost" onClick={() => setAsk(null)}>{s.cancel}</button>
          </div>
        </div>
      )}
      <details className="group text-sm" data-testid="case-more">
        <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-sm text-text-muted transition-colors hover:text-text [&::-webkit-details-marker]:hidden">
          <Icon name="chevronRight" size={14} className="shrink-0 transition-transform group-open:rotate-90" />
          {s.moreActions}
        </summary>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <button type="button" className="btn-secondary px-3 py-1.5 text-danger-text" data-testid="case-reject" aria-describedby="case-hint-reject" aria-expanded={ask === "reject"} onClick={() => { setAsk(ask === "reject" ? null : "reject"); setComment(""); }}>
            <Icon name="x" size={15} />
            {s.reject}
          </button>
          <span id="case-hint-reject" className="text-xs text-text-muted">{s.decisionHints.reject.text}</span>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-sm font-medium text-brand-text underline-offset-2 hover:underline"
            onClick={() => p.changeInChat()}
            data-testid="case-review-ask-wizard"
          >
            <Icon name="messageSquareText" size={14} />
            {s.changeInChat}
          </button>
        </div>
      </details>
    </div>
  );
}

type Section = { id?: string; title?: string; text?: string };
const docProblems = (rec: CaseRecord) =>
  ((rec.sections as Section[]) ?? []).filter((x) => !String(x.text ?? "").trim()).length;

function DocumentEditor({ rec, original, setRec, s }: { rec: CaseRecord; original: CaseRecord; setRec: (r: CaseRecord) => void; s: CaseStrings }) {
  const sections = (rec.sections as Section[]) ?? [];
  const before = (original.sections as Section[]) ?? [];
  return (
    <div className="flex flex-col gap-3">
      {typeof rec.title === "string" && <h4 className="text-lg font-bold">{rec.title}</h4>}
      {sections.map((sec, i) => {
        const edited = (before[i]?.text ?? "") !== (sec.text ?? "");
        return (
          <label key={sec.id ?? i} className="block">
            <span className="field-label flex items-center gap-2">
              {sec.title ?? sec.id}
              {edited && <span className="badge-info">{s.edited}</span>}
              {!String(sec.text ?? "").trim() && <span className="text-danger-text text-xs">{s.required}</span>}
            </span>
            <textarea
              className="input-field font-mono text-xs min-h-28"
              value={sec.text ?? ""}
              onChange={(e) => {
                const next = sections.map((x, j) => (j === i ? { ...x, text: e.target.value } : x));
                setRec({ ...rec, sections: next });
              }}
            />
          </label>
        );
      })}
    </div>
  );
}

function RecordForm({ spec, rec, original, setRec, s }: { spec: OutputSpec; rec: CaseRecord; original: CaseRecord; setRec: (r: CaseRecord) => void; s: CaseStrings }) {
  const unc = uncertainField(spec);
  const uncertain = new Set(unc ? ((original[unc] as string[]) ?? []) : []);
  // What the reviewer is typing, shown as typed. Parsing trims the text and
  // splits lists at commas, so a field showing the parsed value dropped a space
  // or a comma the moment it was typed. The parsed value goes to the record at
  // once; the field shows it when the reviewer leaves the field.
  const [typing, setTyping] = useState<Record<string, string>>({});
  return (
    <div className="flex flex-col gap-3">
      {formFields(spec).map((f) => {
        const problem = fieldProblem(spec, rec, f);
        const edited = show(rec[f]) !== show(original[f]);
        const allowed = spec.allowed_values?.[f];
        // From the extracted value, not the edited one: switching from an input to a
        // textarea at the 61st typed character replaced the field and lost the focus.
        const long = /description|actions|notes|summary/.test(f) || show(original[f]).length > 60;
        const common = {
          id: `case-f-${f}`,
          "data-testid": `case-field-${f}`,
          className: `input-field ${problem ? "border-danger-text" : edited ? "border-brand" : uncertain.has(f) ? "border-warning-text" : ""}`,
        };
        const change = (raw: string) => {
          setTyping((t) => ({ ...t, [f]: raw }));
          setRec({ ...rec, [f]: parseInput(spec, f, raw) });
        };
        const leave = () =>
          setTyping((t) => {
            const next = { ...t };
            delete next[f];
            return next;
          });
        const value = typing[f] ?? show(rec[f]);
        return (
          <div key={f}>
            <label htmlFor={common.id} className="field-label flex flex-wrap items-center gap-2">
              {humanize(f)}
              {(spec.required_fields ?? []).includes(f) && <span className="text-danger-text">*</span>}
              {uncertain.has(f) && <span className="badge-warning">{s.uncertain}</span>}
              {edited && <span className="badge-info">{s.edited}</span>}
              {original[f] == null && !edited && <span className="badge">{s.notStated}</span>}
            </label>
            <p className="text-xs text-text-muted mb-1">
              {spec.field_descriptions?.[f]}
              {isList(spec, f) && !isStructured(rec[f]?.[0 as never]) && !/list\[(dict|list)/.test(spec.field_types?.[f] ?? "") ? ` · ${s.listHint}` : ""}
            </p>
            {isTable(rec[f]) || (Array.isArray(rec[f]) && /list\[dict\]/.test(spec.field_types?.[f] ?? "")) ? (
              <TableEditor rows={(rec[f] as CaseRecord[]) ?? []} onChange={(rows) => setRec({ ...rec, [f]: rows })} s={s} testId={common["data-testid"]} />
            ) : isStructured(rec[f]) && !(Array.isArray(rec[f]) && (rec[f] as unknown[]).every((x) => typeof x !== "object")) ? (
              <JsonField value={rec[f]} onChange={(v) => setRec({ ...rec, [f]: v })} className={common.className} testId={common["data-testid"]} />
            ) : allowed ? (
              <select {...common} value={show(rec[f])} onChange={(e) => change(e.target.value)}>
                <option value="" />
                {allowed.map((a) => <option key={a}>{a}</option>)}
              </select>
            ) : long ? (
              <textarea {...common} value={value} onChange={(e) => change(e.target.value)} onBlur={leave} />
            ) : (
              <input {...common} value={value} placeholder={formatOf(spec, f)} onChange={(e) => change(e.target.value)} onBlur={leave} />
            )}
            {edited && (
              <p className="text-xs text-text-muted mt-1">
                {s.ai} <em>{isStructured(original[f]) ? "…" : show(original[f]) || "—"}</em> ·{" "}
                <button type="button" className="underline" onClick={() => setRec({ ...rec, [f]: structuredClone(original[f]) })}>{s.restore}</button>
              </p>
            )}
            {rowProblems(spec, rec)
              .filter((rp) => rp.table === f)
              .map((rp) => (
                <p key={`${rp.row}-${rp.column}`} className="text-xs text-danger-text mt-1">
                  {humanize(rp.column)} #{rp.row}:{" "}
                  {rp.problem.kind === "required" ? s.required : rp.problem.kind === "allowed" ? `${s.allowed} ${rp.problem.detail}` : `${s.format} ${rp.problem.detail}`}
                </p>
              ))}
            {problem && (
              <p className="text-xs text-danger-text mt-1">
                {problem.kind === "required" ? s.required : problem.kind === "allowed" ? `${s.allowed} ${problem.detail}` : `${s.format} ${problem.detail}`}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** A list of objects as an editable table: one row per item, a column per key. */
function TableEditor({ rows, onChange, s, testId }: { rows: CaseRecord[]; onChange: (rows: CaseRecord[]) => void; s: CaseStrings; testId?: string }) {
  const cols = tableColumns(rows);
  const set = (i: number, k: string, v: unknown) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="overflow-x-auto rounded-md border border-border-strong" data-testid={testId}>
      <table className="w-full text-xs">
        <thead className="bg-surface-muted">
          <tr>
            {cols.map((k) => <th key={k} className="px-2 py-1 text-left font-semibold">{humanize(k)}</th>)}
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border align-top">
              {cols.map((k) => (
                <td key={k} className="p-1 min-w-[110px]">
                  {isStructured(r[k]) ? (
                    <JsonField value={r[k]} onChange={(v) => set(i, k, v)} className="input-field text-xs" />
                  ) : (
                    <textarea
                      rows={Math.min(4, Math.max(1, Math.ceil(show(r[k]).length / 40)))}
                      className="input-field text-xs px-2 py-1"
                      value={show(r[k])}
                      onChange={(e) => set(i, k, e.target.value === "" ? null : e.target.value)}
                    />
                  )}
                </td>
              ))}
              <td className="p-1">
                <button type="button" className="text-danger-text text-xs underline" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                  {s.removeRow}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        className="m-1 text-xs underline text-brand-strong"
        onClick={() => onChange([...rows, Object.fromEntries(cols.map((k) => [k, null]))])}
      >
        + {s.addRow}
      </button>
    </div>
  );
}

/** A structured value edited as JSON; kept as text until it parses again. */
function JsonField({ value, onChange, className, testId }: { value: unknown; onChange: (v: unknown) => void; className?: string; testId?: string }) {
  const [text, setText] = useState(() => JSON.stringify(value));
  const [bad, setBad] = useState(false);
  return (
    <textarea
      data-testid={testId}
      className={`${className ?? ""} font-mono ${bad ? "border-danger-text" : ""}`}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        try {
          onChange(JSON.parse(e.target.value));
          setBad(false);
        } catch {
          setBad(true);
        }
      }}
    />
  );
}

function DoneView(p: ViewProps) {
  const { caseData: c, model, s } = p;
  const raw = c.record ?? {};
  const list = Array.isArray(raw) ? raw : [raw];
  const rec = list[0] ?? {};
  const doc = isDocument(raw);
  const words = { yes: s.yes, no: s.no, none: s.none };
  const name = (model.spec.schema_name || "result").toLowerCase();
  const stamp = c.events.at(-1)?.at;
  const approved = c.status === "approved";
  const reviewed: CaseRecord | CaseRecord[] = approved
    ? Array.isArray(raw) ? raw.map((r) => ({ ...r, review_status: r.review_status ?? "approved" })) : { ...raw, review_status: "approved", approved_at: stamp }
    : raw;
  const exported: CaseRecord | CaseRecord[] = Array.isArray(reviewed)
    ? reviewed.map((r) => ({ ...r, ...AI_RECORD_MARK }))
    : { ...reviewed, ...AI_RECORD_MARK };

  function printPdf() {
    const w = window.open("", "_blank");
    if (!w) return;
    const esc = (t: string) => t.replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[ch] as string);
    const body = doc
      ? `<pre style="white-space:pre-wrap;font:11pt/1.45 Helvetica,Arial">${esc(toMarkdown(rec))}</pre>`
      : list
          .map(
            (r) => `<table style="border-collapse:collapse;width:100%;font:11pt Helvetica,Arial;margin-bottom:18px">${formFields(model.spec)
              .map((f) => `<tr><td style="border-bottom:1px solid #bbb;padding:6px;font-weight:bold;width:28%;vertical-align:top">${esc(humanize(f))}</td><td style="border-bottom:1px solid #bbb;padding:6px;white-space:pre-wrap">${esc(valueText(formatValue(r[f], words)))}</td></tr>`)
              .join("")}</table>`,
          )
          .join("");
    const when = (stamp ? new Date(stamp) : new Date()).toLocaleString(p.dateLocale);
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><meta name="ai-generated" content="true"><meta name="generator" content="${AI_GENERATOR}"><title>${esc(model.title)}</title></head><body style="margin:32px"><h2 style="font-family:Helvetica,Arial">${esc(model.title)}</h2><p style="font-family:Helvetica,Arial">${approved ? s.approvedTitle : s.completedTitle} ${esc(when)}</p>${body}<p style="font:9pt Helvetica,Arial;color:#555">${esc(s.aiMade)}</p></body></html>`);
    w.document.close();
    w.focus();
    w.print();
  }

  if (c.status === "rejected") {
    return (
      <div data-testid="case-done">
        <h4 className="flex items-center gap-2 font-semibold text-text">
          <Icon name="x" size={16} className="text-text-muted" />
          {s.rejectedTitle}
        </h4>
        {c.comment && <p className="mt-1 text-sm text-text-muted">{c.comment}</p>}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4" data-testid="case-done">
      <h4 className="flex items-center gap-2 font-semibold text-text">
        <Icon name="circleCheck" size={16} className="text-success-text" />
        {approved ? s.approvedTitle : s.completedTitle}
      </h4>
      {doc ? (
        <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-app p-3 text-xs">{toMarkdown(rec)}</pre>
      ) : (
        list.map((r, i) => (
          // Several results are parted by a rule and numbered, not boxed.
          <div key={i} className={list.length > 1 ? "border-t border-border pt-4 first:border-t-0 first:pt-0" : ""} data-testid="case-result">
            {list.length > 1 && <p className="mb-2 text-xs font-medium text-text-muted">{s.item} {i + 1}</p>}
            <ResultFields
              fields={formFields(model.spec).map((f) => ({ field: f, label: humanize(f), shown: formatValue(r[f], words) }))}
              labels={s}
              testId="case"
            />
          </div>
        ))
      )}
      {/* One "Vie" for the three formats, not the word three times; each
          button carries its file type's mark and is named in full. */}
      <div role="group" aria-label={s.export} className="flex flex-wrap items-center gap-2 border-t border-border pt-4" data-testid="case-export">
        <span className="mr-1 text-sm text-text-muted" aria-hidden="true">{s.export}</span>
        <button type="button" className="btn-secondary" aria-label={fillTemplate(s.exportAs, { format: "JSON" })} onClick={() => download(`${name}.json`, "application/json", JSON.stringify(exported, null, 2))}>
          <FileIcon kind="json" size={16} />
          JSON
        </button>
        {doc ? (
          <button type="button" className="btn-secondary" aria-label={fillTemplate(s.exportAs, { format: "Markdown" })} onClick={() => download(`${name}.md`, "text/markdown;charset=utf-8", AI_FRONT_MATTER + toMarkdown(rec))}>
            <FileIcon kind="markdown" size={16} />
            Markdown
          </button>
        ) : (
          <button type="button" className="btn-secondary" aria-label={fillTemplate(s.exportAs, { format: "CSV" })} onClick={() => download(`${name}.csv`, "text/csv;charset=utf-8", toCsv(exported))}>
            <FileIcon kind="csv" size={16} />
            CSV
          </button>
        )}
        <button type="button" className="btn-secondary" aria-label={fillTemplate(s.exportAs, { format: "PDF" })} onClick={printPdf}>
          <FileIcon kind="pdf" size={16} />
          PDF
        </button>
      </div>
    </div>
  );
}

/** Beside the task: what the case was made from, the source check, and what has happened to it. */
function SourceView(p: ViewProps & { files: Case["inputs"]; eventsOnly?: boolean }) {
  const { caseData: c, s, base } = p;
  const validation = c.record && !p.eventsOnly ? c.result?.validation : null;
  return (
    <aside
      className={`flex min-w-0 flex-col gap-4 border-t border-border sm:px-5 ${p.eventsOnly ? "px-4 py-3" : "p-4 sm:py-5 xl:border-l xl:border-t-0"}`}
      data-testid="case-side"
    >
      {!p.eventsOnly && (p.files.length > 0 || c.result?.transcript) && (
        <div data-testid="case-source">
          <h4 className="mb-2 text-sm font-semibold text-text">{s.source}</h4>
          <ul className="flex flex-col gap-2 text-sm">
            {p.files.map((f) => (
              <li key={f.name}>
                {/\.(wav|mp3|m4a|ogg|webm)$/i.test(f.name) ? (
                  <audio controls src={`${base}/inputs/${encodeURIComponent(f.name)}`} className="w-full" />
                ) : (
                  <a className="inline-flex items-center gap-1.5 font-mono text-xs text-brand-strong underline [overflow-wrap:anywhere]" href={`${base}/inputs/${encodeURIComponent(f.name)}`} target="_blank" rel="noreferrer">
                    <FileIcon name={f.name} size={15} />
                    {f.name}
                  </a>
                )}
              </li>
            ))}
          </ul>
          {c.result?.transcript && (
            <>
              <h5 className={`mb-1 text-xs font-medium text-text-muted ${p.files.length > 0 ? "mt-3" : ""}`}>{s.transcript}</h5>
              <p className="whitespace-pre-wrap rounded-md border border-border bg-app p-2 text-sm">{c.result.transcript}</p>
            </>
          )}
        </div>
      )}
      {/* The values the check could not find in the source, when it names them. */}
      <GroundingNote
        validation={validation}
        words={{ yes: s.yes, no: s.no, none: s.none }}
        labels={{
          showRaw: s.showRaw,
          page: s.page,
          ok: s.groundingOk,
          bad: s.groundingBad,
          checkThese: s.groundingCheckThese,
          checkResult: s.groundingCheckResult,
        }}
        testId="case-grounding"
      />
      {/* The log is for looking something up, so it stays closed until asked for. */}
      {c.events.length > 0 && (
        <details className="group text-sm">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-sm font-medium text-text-secondary transition-colors hover:text-text [&::-webkit-details-marker]:hidden">
            <Icon name="chevronRight" size={14} className="shrink-0 transition-transform group-open:rotate-90" />
            {s.events}
            <span className="font-normal tabular-nums text-text-muted">{c.events.length}</span>
          </summary>
          <ul className="mt-2 flex flex-col-reverse gap-1 text-xs text-text-muted" data-testid="case-events">
            {c.events.map((e, i) => (
              <li key={i}>
                {new Date(e.at).toLocaleTimeString(p.dateLocale, { hour: "2-digit", minute: "2-digit" })}{" "}
                <span className="font-medium text-text">{e.role === "ai" ? s.aiRole : e.role}</span> {s.actions[e.action] ?? e.action}
                {e.detail ? ` “${e.detail}”` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </aside>
  );
}
