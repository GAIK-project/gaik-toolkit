"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Blueprint } from "@/lib/mock-sessions";
import type { Dict } from "@/lib/i18n";
import { refusalOf } from "@/lib/blueprint-ops";
import { fieldName } from "@/lib/blueprint-field-names";
import { fillTemplate } from "@/lib/chat-template";
import {
  blueprintFileName,
  changedReadonlySection,
  draftText,
  parseDraftText,
  readFullBlueprint,
  readonlyRanges,
  downloadText,
  mergeDrafts,
  withoutAiMark,
  type Draft,
  type FullBlueprint,
} from "@/lib/full-blueprint";
import { Icon } from "@/components/icons";

// CodeMirror comes only when the advanced editor is opened.
const CodeEditor = dynamic(() => import("@/components/code-editor"), { ssr: false });

type Load =
  | { kind: "loading" }
  | { kind: "needsApi" }
  | { kind: "noDraft" }
  | { kind: "error" }
  | { kind: "ready"; full: FullBlueprint };

/** The advanced editor open: the text it started with, and the draft that text was made from. */
type Editing = { text: string; loaded: Draft; ranges: { from: number; to: number }[]; key: number };

type Status =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "unchanged" }
  | { kind: "changed" }
  | { kind: "kept" }
  /** The newer draft and the text both changed these sections: only "load the newer version" is offered. */
  | { kind: "conflict"; sections: string[] }
  | { kind: "error"; message: string };

export type FullBlueprintSaved = {
  /** The session's blueprint as the workspace shows it, when the answer had one. */
  blueprint: Blueprint | null;
  version: number;
  bpmnChanged: boolean;
};

async function fetchFull(sessionId: string): Promise<Load> {
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/blueprint/full`, { cache: "no-store" });
    const body = (await res.json().catch(() => null)) as unknown;
    if (res.ok) {
      const full = readFullBlueprint(body);
      return full ? { kind: "ready", full } : { kind: "error" };
    }
    const code = refusalOf(body)?.code;
    if (code === "needs_wizard_api") return { kind: "needsApi" };
    if (code === "no_draft") return { kind: "noDraft" };
    return { kind: "error" };
  } catch {
    return { kind: "error" };
  }
}

/**
 * The Blueprint tab's "Full blueprint": the session's whole draft, each
 * section folded and read-only, a download of it as JSON, and "Advanced: edit
 * JSON", the draft in the code editor with the sections only the wizard
 * writes locked. A save is checked here first (the JSON parses, no locked
 * section changed) and sent whole, on the version and digest it was read
 * with; wizard_api checks it again. Without wizard_api, or before the wizard
 * has written a draft, a note says so.
 */
export function FullBlueprintView({
  sessionId,
  version,
  t,
  onSaved,
  onDirtyChange,
}: {
  sessionId: string;
  /** The workspace's active version: a new one is read again while the editor is closed. */
  version: number | null;
  t: Dict;
  onSaved: (saved: FullBlueprintSaved) => void;
  /** Whether the advanced editor holds text not saved: the panel asks before leaving the view. */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [editing, setEditing] = useState<Editing | null>(null);
  // What the next save is made on: the draft as read, or as read again after "Keep editing".
  const [base, setBase] = useState<FullBlueprint | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [attention, setAttention] = useState<string[]>([]);
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());
  const textRef = useRef("");
  const [dirty, setDirty] = useState(false);
  const onDirtyChangeRef = useRef(onDirtyChange);
  useEffect(() => {
    onDirtyChangeRef.current = onDirtyChange;
  });
  useEffect(() => {
    onDirtyChangeRef.current?.(dirty);
  }, [dirty]);
  // Whether the editor is open, for the reads that answer after it was opened.
  const editingRef = useRef(editing);
  useEffect(() => {
    editingRef.current = editing;
  }, [editing]);
  const loadedVersion = load.kind === "ready" ? load.full.version : null;

  const reload = useCallback(async () => {
    const next = await fetchFull(sessionId);
    setLoad(next);
    setBase(next.kind === "ready" ? next.full : null);
    return next;
  }, [sessionId]);

  useEffect(() => {
    // The editor's text is the user's: a version written meanwhile is met on save.
    if (editingRef.current) return;
    if (loadedVersion !== null && loadedVersion === version) return;
    let live = true;
    void fetchFull(sessionId).then((next) => {
      if (!live || editingRef.current) return;
      setLoad(next);
      setBase(next.kind === "ready" ? next.full : null);
    });
    return () => {
      live = false;
    };
    // loadedVersion is read, not followed: a load must not start another.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, version]);

  function startEditing(full: FullBlueprint) {
    const text = draftText(full.draft);
    textRef.current = text;
    setDirty(false);
    setBase(full);
    setStatus({ kind: "idle" });
    setAttention([]);
    setEditing({
      text,
      loaded: full.draft,
      ranges: readonlyRanges(text, full.readonlySections),
      key: (editing?.key ?? 0) + 1,
    });
  }

  function download(full: FullBlueprint) {
    const url = URL.createObjectURL(new Blob([downloadText(full.draft)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = blueprintFileName(full.draft);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  const name = (path: string) => fieldName(path, t.locale);

  async function save() {
    if (!editing || !base || status.kind === "saving") return;
    const parsed = parseDraftText(textRef.current);
    if (!parsed.ok) {
      setStatus({
        kind: "error",
        message:
          parsed.line === null
            ? t.fullBpNotObject
            : fillTemplate(t.fullBpParseError, { line: String(parsed.line), column: String(parsed.column) }),
      });
      return;
    }
    // A downloaded file pasted back carries the AI mark: it is not part of the blueprint.
    const mine = withoutAiMark(parsed.draft);
    const locked = changedReadonlySection(editing.loaded, mine, base.readonlySections);
    if (locked) {
      setStatus({ kind: "error", message: fillTemplate(t.wsJsonReadonlySection, { field: name(locked) }) });
      return;
    }
    // On the draft as the server has it now: after "Keep editing" what the
    // wizard changed meanwhile stays, unless the text changed the same section.
    const merged = mergeDrafts(editing.loaded, base.draft, mine, base.readonlySections);
    if (!merged.ok) {
      setStatus({ kind: "conflict", sections: merged.conflicts });
      return;
    }
    setStatus({ kind: "saving" });
    let res: Response;
    let body: unknown;
    try {
      res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/blueprint/full`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_version: base.version,
          base_digest: base.draftDigest,
          draft: merged.draft,
        }),
      });
      body = (await res.json().catch(() => null)) as unknown;
    } catch {
      setStatus({ kind: "error", message: t.wsJsonSaveError });
      return;
    }
    if (!res.ok) {
      setStatus(refusedStatus(res.status, body));
      return;
    }
    const data = (body ?? {}) as {
      session?: { blueprint?: Blueprint; active_version?: number } | null;
      warnings?: unknown;
      needs_attention?: unknown;
      bpmn_changed?: boolean;
    };
    const savedVersion = typeof data.session?.active_version === "number" ? data.session.active_version : base.version;
    const notes = [data.warnings, data.needs_attention]
      .flatMap((list) => (Array.isArray(list) ? list : []))
      .filter((s): s is string => typeof s === "string" && s.trim() !== "");
    setEditing(null);
    editingRef.current = null;
    setDirty(false);
    setAttention(notes);
    setStatus({ kind: savedVersion === base.version ? "unchanged" : "saved" });
    await reload();
    if (savedVersion !== base.version) {
      onSaved({
        blueprint: data.session?.blueprint ?? null,
        version: savedVersion,
        bpmnChanged: Boolean(data.bpmn_changed),
      });
    }
  }

  function refusedStatus(httpStatus: number, body: unknown): Status {
    const refusal = refusalOf(body);
    if (refusal?.code === "changed_elsewhere") return { kind: "changed" };
    if (refusal?.code === "agent_busy") return { kind: "error", message: t.fullBpAgentBusy };
    if (refusal?.code === "no_draft") return { kind: "error", message: t.fullBpNoDraft };
    if (refusal?.code === "readonly_section" && refusal.field) {
      return { kind: "error", message: fillTemplate(t.wsJsonReadonlySection, { field: name(refusal.field) }) };
    }
    if (refusal?.code === "invalid_draft" && refusal.field) {
      const where = fillTemplate(t.wsJsonInvalidDraft, { field: name(refusal.field) });
      return { kind: "error", message: refusal.message ? `${where} ${refusal.message}` : where };
    }
    if (refusal?.field && refusal.message) {
      return { kind: "error", message: fillTemplate(t.fullBpRefused, { field: name(refusal.field), message: refusal.message }) };
    }
    if (refusal?.message && httpStatus < 500) return { kind: "error", message: refusal.message };
    return { kind: "error", message: t.wsJsonSaveError };
  }

  async function discardForNewer() {
    setEditing(null);
    editingRef.current = null;
    setDirty(false);
    setStatus({ kind: "idle" });
    await reload();
  }

  async function keepEditing() {
    // The next save is made on the draft as it is now, not on the one the text came from.
    const next = await fetchFull(sessionId);
    if (next.kind !== "ready") {
      setStatus({ kind: "error", message: next.kind === "noDraft" ? t.fullBpNoDraft : t.fullBpLoadError });
      return;
    }
    setBase(next.full);
    setStatus({ kind: "kept" });
  }

  if (load.kind !== "ready") {
    const text =
      load.kind === "loading"
        ? t.fullBpLoading
        : load.kind === "needsApi"
          ? t.fullBpNeedsApi
          : load.kind === "noDraft"
            ? t.fullBpNoDraft
            : t.fullBpLoadError;
    return (
      <div className="flex flex-wrap items-center gap-3 py-2" data-testid="full-blueprint-view">
        <p
          className="flex min-w-0 items-start gap-2 text-sm text-text-secondary"
          role="status"
          data-testid="full-blueprint-note"
          data-kind={load.kind}
        >
          <Icon
            name={load.kind === "loading" ? "loaderCircle" : "info"}
            size={16}
            className={`mt-0.5 shrink-0 text-text-muted ${load.kind === "loading" ? "animate-spin" : ""}`}
          />
          <span>{text}</span>
        </p>
        {load.kind === "error" && (
          <button type="button" className="btn-secondary" onClick={() => void reload()}>
            {t.editorRetry}
          </button>
        )}
      </div>
    );
  }

  const full = load.full;
  const statusText =
    status.kind === "saving"
      ? t.wsJsonSaving
      : status.kind === "saved"
        ? t.wsJsonSaved
        : status.kind === "unchanged"
          ? t.fullBpUnchanged
          : status.kind === "changed"
            ? t.fullBpChangedElsewhere
            : status.kind === "conflict"
              ? fillTemplate(t.fullBpConflict, { sections: status.sections.map(name).join(", ") })
            : status.kind === "kept"
              ? t.fullBpKeptEditing
              : status.kind === "error"
                ? status.message
                : null;
  const statusIsProblem = status.kind === "error" || status.kind === "changed" || status.kind === "conflict";

  return (
    <div className="flex flex-col gap-3 pb-2" data-testid="full-blueprint-view" data-mode={editing ? "edit" : "read"}>
      {/* The row stays at the top of the tab as it scrolls: Save is in view at any line. */}
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-end gap-x-3 gap-y-1.5 bg-surface pb-2">
        <p
          role={statusIsProblem ? "alert" : "status"}
          className={`min-w-0 flex-1 basis-64 text-sm empty:hidden ${statusIsProblem ? "text-danger-text" : "text-text-secondary"}`}
          data-testid="full-blueprint-status"
          data-state={status.kind}
        >
          {statusText}
        </p>
        {(status.kind === "changed" || status.kind === "conflict") && editing && (
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void discardForNewer()}
              data-testid="full-blueprint-reload"
            >
              {t.fullBpReload}
            </button>
            {status.kind === "changed" && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void keepEditing()}
                data-testid="full-blueprint-keep-editing"
              >
                {t.fullBpKeepEditing}
              </button>
            )}
          </>
        )}
        {editing ? (
          <>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setEditing(null);
                editingRef.current = null;
                setDirty(false);
                setStatus({ kind: "idle" });
                // A version written while the editor was open was not read: the view would show the old one.
                if (version !== loadedVersion) void reload();
              }}
              data-testid="full-blueprint-cancel"
            >
              {t.fullBpCancel}
            </button>
            <button
              type="button"
              className="btn-brand"
              onClick={() => void save()}
              disabled={status.kind === "saving" || status.kind === "changed" || status.kind === "conflict"}
              data-testid="full-blueprint-save"
            >
              <Icon name="save" size={16} />
              {t.fullBpSave}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => download(full)}
              data-testid="full-blueprint-download"
            >
              <Icon name="download" size={16} />
              {t.fullBpDownload}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => startEditing(full)}
              data-testid="full-blueprint-advanced"
            >
              <Icon name="codeXml" size={16} />
              {t.fullBpAdvanced}
            </button>
          </>
        )}
      </div>

      {attention.length > 0 && !editing && (
        <div className="text-sm text-text-secondary" data-testid="full-blueprint-attention">
          <p>{t.fullBpAttention}</p>
          <ul className="mt-1 list-disc pl-5">
            {attention.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {editing ? (
        <>
          <p className="flex items-start gap-1.5 text-xs text-text-secondary">
            <Icon name="lock" size={13} className="mt-0.5 shrink-0 text-text-muted" />
            <span>{t.fullBpEditHelp}</span>
          </p>
          <div className="rounded-lg border border-border" data-testid="full-blueprint-editor">
            <CodeEditor
              key={editing.key}
              value={editing.text}
              language="json"
              lockedRanges={editing.ranges}
              label={t.fullBpEditorLabel}
              onChange={(text) => {
                textRef.current = text;
                setDirty(text !== editing.text);
              }}
              onSave={() => void save()}
            />
          </div>
        </>
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
          {Object.entries(full.draft).map(([section, value]) => {
            const readOnly = full.readonlySections.includes(section);
            const isOpen = open.has(section);
            return (
              <li key={section}>
                <details
                  open={isOpen}
                  onToggle={(e) => {
                    const nowOpen = (e.currentTarget as HTMLDetailsElement).open;
                    setOpen((prev) => {
                      if (prev.has(section) === nowOpen) return prev;
                      const next = new Set(prev);
                      if (nowOpen) next.add(section);
                      else next.delete(section);
                      return next;
                    });
                  }}
                  data-testid={`full-blueprint-section-${section}`}
                >
                  <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium text-text-strong">
                    <Icon
                      name={isOpen ? "chevronDown" : "chevronRight"}
                      size={14}
                      className="shrink-0 text-text-muted"
                    />
                    <span>{name(section)}</span>
                    {readOnly && (
                      <span className="inline-flex items-center gap-1 text-xs font-normal text-text-muted">
                        <Icon name="lock" size={12} />
                        {t.fullBpReadonly}
                      </span>
                    )}
                  </summary>
                  {/* Drawn only while open: a whole draft can be a megabyte. */}
                  {isOpen && (
                    <pre className="whitespace-pre-wrap break-words px-3 pb-3 font-mono text-xs text-text">
                      {JSON.stringify(value, null, 2)}
                    </pre>
                  )}
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
