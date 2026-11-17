"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FileIcon } from "@/components/file-icon";
import { Icon } from "@/components/icons";
import { envExampleKeyValues } from "@/lib/env-file";
import type { Dict } from "@/lib/i18n";
import {
  ENV_EXAMPLE_NAME,
  MAX_POC_FILE_BYTES,
  editorLanguage,
  pocFileFrom,
  pocFileSavedFrom,
  utf8Bytes,
  type PocFile,
  type PocFileSaved,
} from "@/lib/poc-file";

// CodeMirror and its languages: fetched when the first file is opened.
const CodeEditor = dynamic(() => import("@/components/code-editor"), { ssr: false });

type Problem = { code: string; message: string; variables?: string[] };

async function problemOf(res: Response): Promise<Problem> {
  const body = (await res.json().catch(() => null)) as {
    detail?: { error?: unknown; message?: unknown; variables?: unknown };
  } | null;
  const detail = body?.detail;
  const variables = Array.isArray(detail?.variables)
    ? detail.variables.filter((v): v is string => typeof v === "string")
    : undefined;
  return {
    code: typeof detail?.error === "string" ? detail.error : "",
    message: typeof detail?.message === "string" ? detail.message : "",
    ...(variables?.length ? { variables } : {}),
  };
}

/**
 * One file of the PoC package, opened from the package's tree: read with
 * syntax highlighting, and edited and saved where wizard_api allows it.
 *
 * A dialog over the workspace, wide on a desktop and the whole screen on a
 * phone. Closing with unsaved changes asks first; a save over a file the
 * wizard has rewritten meanwhile is refused by the api (409) and said here,
 * with the user's text left in the editor.
 */
export function PocFileEditor({
  sessionId,
  path,
  gate3Approved,
  t,
  onClose,
  onSaved,
}: {
  sessionId: string;
  /** The file's path inside poc/. */
  path: string;
  /** Gate 3 is approved: a save that changes the tested package reopens it. */
  gate3Approved: boolean;
  t: Dict;
  onClose: () => void;
  onSaved: (saved: PocFileSaved) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<PocFile | null>(null);
  const [loadProblem, setLoadProblem] = useState<Problem | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveProblem, setSaveProblem] = useState<Problem | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [askDiscard, setAskDiscard] = useState(false);
  // Bumped to read the file again (after a conflict).
  const [revision, setRevision] = useState(0);
  // Bumped to give the editor the saved text again (discard).
  const [editorKey, setEditorKey] = useState(0);
  const url = `/api/sessions/${sessionId}/poc/file?path=${encodeURIComponent(path)}`;

  const dirty = file !== null && file.editable && draft !== file.content;
  const dirtyRef = useRef(dirty);
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);
  // Set when the user has said the changes may go.
  const leaving = useRef(false);

  useEffect(() => {
    const el = dialog.current;
    if (el && !el.open) el.showModal();
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(url, { cache: "no-store" })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          setLoadProblem(await problemOf(res));
          return;
        }
        const read = pocFileFrom(await res.json().catch(() => null));
        if (cancelled) return;
        if (!read) {
          setLoadProblem({ code: "", message: "" });
          return;
        }
        setFile(read);
        setDraft(read.content);
        setLoadProblem(null);
      })
      .catch(() => {
        if (!cancelled) setLoadProblem({ code: "", message: "" });
      });
    return () => {
      cancelled = true;
    };
  }, [url, revision]);

  // A reload or a closed tab with unsaved text asks the browser's own question.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const requestClose = useCallback(() => {
    if (dirtyRef.current && !leaving.current) {
      setAskDiscard(true);
      return;
    }
    dialog.current?.close();
  }, []);

  const save = useCallback(async () => {
    if (!file || !file.editable || saving || draft === file.content) return;
    if (utf8Bytes(draft) > MAX_POC_FILE_BYTES) {
      setSaveProblem({ code: "file_too_large", message: "" });
      return;
    }
    // A key typed into .env.example is refused here, before it leaves the
    // browser; wizard_api refuses it as well (key_value_not_stored).
    const valued = path.split("/").pop() === ENV_EXAMPLE_NAME ? envExampleKeyValues(draft) : [];
    if (valued.length > 0) {
      setJustSaved(false);
      setSaveProblem({ code: "key_value_not_stored", message: "", variables: valued });
      return;
    }
    setSaving(true);
    setSaveProblem(null);
    setJustSaved(false);
    try {
      const res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: draft, base_digest: file.digest }),
      });
      if (!res.ok) {
        setSaveProblem(await problemOf(res));
        return;
      }
      const saved = pocFileSavedFrom(await res.json().catch(() => null));
      if (!saved) {
        setSaveProblem({ code: "", message: "" });
        return;
      }
      // The editor keeps its text, cursor and undo history: only what counts
      // as saved moves.
      setFile({ ...file, content: draft, digest: saved.digest });
      setJustSaved(true);
      onSaved(saved);
    } catch {
      setSaveProblem({ code: "", message: "" });
    } finally {
      setSaving(false);
    }
  }, [draft, file, onSaved, path, saving, url]);

  function discard() {
    if (!file) return;
    setDraft(file.content);
    setSaveProblem(null);
    setAskDiscard(false);
    setEditorKey((n) => n + 1);
  }

  /** After a conflict: the file as it is now, in place of the user's text. */
  function openNewVersion() {
    setFile(null);
    setSaveProblem(null);
    setJustSaved(false);
    setRevision((n) => n + 1);
  }

  const name = path.split("/").pop() ?? path;
  const loadText = loadProblem
    ? ({
        file_not_text: t.pocFileNotText,
        file_too_large: t.pocFileTooLargeToOpen,
        secrets_not_stored: t.pocFileSecrets,
        not_found: t.pocFileNotFound,
        invalid_path: t.pocFileNotFound,
      }[loadProblem.code] ?? t.pocFileLoadFailed)
    : null;
  const conflict = saveProblem?.code === "file_changed";
  const saveText = saveProblem
    ? ({
        file_changed: t.pocFileConflict,
        wizard_responding: t.pocFileWizardBusy,
        file_too_large: t.pocFileTooLargeToSave,
        secrets_not_stored: t.pocFileSecrets,
        key_value_not_stored: t.pocFileKeyValue.replace("{names}", (saveProblem.variables ?? []).join(", ")),
        code_edit_needs_own_runner_key: t.pocFileCodeNeedsOwnKey,
        file_read_only: t.pocFileReadOnly,
        file_type_not_editable: t.pocFileTypeReadOnly,
        not_found: t.pocFileNotFound,
      }[saveProblem.code] ?? t.pocFileSaveFailed)
    : null;
  const readOnlyText =
    file && !file.editable
      ? ({
          file_type_not_editable: t.pocFileTypeReadOnly,
          // wizard_api's rule: code is saved only when the test runs use their own runner key.
          code_edit_needs_own_runner_key: t.pocFileCodeNeedsOwnKey,
        }[file.readOnlyReason ?? ""] ?? t.pocFileReadOnly)
      : null;
  // What a save sets off, said before it: only for a file the test run is tied to.
  const costText = file?.editable && file.affectsPackage ? (gate3Approved ? t.pocFileReopens : t.pocFileRetest) : null;

  // A modal dialog (showModal): the page behind is inert, focus stays inside
  // and Esc is the dialog's. Rendered at the end of <body>, not inside the
  // PoC pane: the pane is a size container that scrolls, and the dimmed
  // backdrop was not drawn for a dialog placed in it.
  return createPortal(
    <dialog
      ref={dialog}
      aria-labelledby="poc-file-title"
      data-testid="poc-file-editor"
      data-path={path}
      data-dirty={dirty ? "true" : undefined}
      // Esc: asks before unsaved text goes. A browser closes on a second Esc
      // whatever the first was answered, so a close that was not agreed opens
      // the dialog again with the text as it was.
      onCancel={(e) => {
        if (dirtyRef.current && !leaving.current) {
          e.preventDefault();
          setAskDiscard(true);
        }
      }}
      onClose={() => {
        if (dirtyRef.current && !leaving.current) {
          dialog.current?.showModal();
          setAskDiscard(true);
          return;
        }
        onClose();
      }}
      className="m-auto h-dvh max-h-none w-screen max-w-none overflow-hidden bg-surface p-0 text-text shadow-lg backdrop:bg-text/40 sm:h-[min(46rem,calc(100dvh-4rem))] sm:w-[min(64rem,calc(100vw-4rem))] sm:rounded-lg sm:border sm:border-border"
    >
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <FileIcon name={name} size={16} />
          <h2
            id="poc-file-title"
            className="min-w-0 flex-1 truncate font-mono text-sm font-medium text-text-strong"
            title={`poc/${path}`}
          >
            <span className="text-text-muted">poc/</span>
            {path}
          </h2>
          <button
            type="button"
            onClick={requestClose}
            className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-muted hover:text-text"
            aria-label={t.pocFileClose}
            title={t.pocFileClose}
            data-testid="poc-file-close"
          >
            <Icon name="x" size={18} />
          </button>
        </header>

        {(readOnlyText || costText) && (
          <p
            className="flex items-start gap-1.5 border-b border-border bg-app px-4 py-2 text-xs text-text-secondary"
            data-testid="poc-file-note"
          >
            <Icon name={readOnlyText ? "lock" : "info"} size={13} className="mt-0.5 text-text-muted" />
            <span>{readOnlyText ?? costText}</span>
          </p>
        )}

        <div className="min-h-0 flex-1">
          {loadText ? (
            <p className="px-4 py-6 text-sm text-text-secondary" role="alert" data-testid="poc-file-unavailable">
              {loadText}
            </p>
          ) : !file ? (
            <p className="flex items-center gap-2 px-4 py-6 text-sm text-text-muted" role="status">
              <Icon name="loaderCircle" size={16} className="animate-spin" />
              {t.pocFileLoading}
            </p>
          ) : (
            <CodeEditor
              key={`${path}:${revision}:${editorKey}`}
              value={file.content}
              language={editorLanguage(path)}
              readOnly={!file.editable}
              label={t.pocFileEditorLabel.replace("{name}", name)}
              onChange={(text) => {
                setDraft(text);
                setJustSaved(false);
              }}
              onSave={() => void save()}
            />
          )}
        </div>

        {saveText && (
          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-danger-border bg-danger-bg px-4 py-2.5 text-sm text-danger-text"
            role="alert"
            data-testid={conflict ? "poc-file-conflict" : "poc-file-save-error"}
          >
            <span className="min-w-0 flex-1 basis-64">{saveText}</span>
            {conflict && (
              <button
                type="button"
                className="btn-secondary"
                onClick={openNewVersion}
                data-testid="poc-file-open-new"
              >
                <Icon name="rotateCcw" size={16} />
                {t.pocFileConflictReload}
              </button>
            )}
          </div>
        )}

        {askDiscard ? (
          <div
            className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-4 py-3"
            role="group"
            aria-label={t.pocFileUnsaved}
            data-testid="poc-file-unsaved"
          >
            <span className="min-w-0 flex-1 basis-48 text-sm text-text-secondary">{t.pocFileUnsaved}</span>
            <button type="button" className="btn-secondary" autoFocus onClick={() => setAskDiscard(false)}>
              {t.pocFileKeepEditing}
            </button>
            <button
              type="button"
              className="rounded-lg bg-danger-text px-3 py-2 text-sm font-semibold text-white"
              onClick={() => {
                leaving.current = true;
                dialog.current?.close();
              }}
              data-testid="poc-file-discard-close"
            >
              {t.pocFileDiscardClose}
            </button>
          </div>
        ) : (
          file?.editable && (
            <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-4 py-3">
              <span className="min-w-0 flex-1 text-xs text-text-muted" role="status" data-testid="poc-file-status">
                {justSaved && !dirty ? (
                  <span className="inline-flex items-center gap-1 text-success-text">
                    <Icon name="check" size={13} />
                    {t.pocFileSaved}
                  </span>
                ) : null}
              </span>
              <button
                type="button"
                className="btn-ghost"
                onClick={discard}
                disabled={!dirty || saving}
                data-testid="poc-file-discard"
              >
                {t.pocFileDiscard}
              </button>
              <button
                type="button"
                className="btn-brand"
                onClick={() => void save()}
                disabled={!dirty || saving}
                data-testid="poc-file-save"
              >
                <Icon name={saving ? "loaderCircle" : "save"} size={16} className={saving ? "animate-spin" : ""} />
                {saving ? t.pocFileSaving : t.pocFileSave}
              </button>
            </footer>
          )
        )}
      </div>
    </dialog>,
    document.body,
  );
}
