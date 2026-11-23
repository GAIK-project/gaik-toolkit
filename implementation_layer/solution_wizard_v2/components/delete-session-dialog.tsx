"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { removeSession, type RemoveSessionState } from "@/app/actions";

export type DeleteSessionLabels = {
  open: string;
  title: string;
  body: string;
  confirmLabel: string;
  confirm: string;
  cancel: string;
  mismatch: string;
  busy: string;
  protected: string;
  failed: string;
};

const INITIAL: RemoveSessionState = { error: null };

/**
 * Asks for a session's name before deleting it. The sidebar renders one for
 * the row whose menu asked, and it opens as it mounts: a dialog inside the
 * menu would close with it.
 */
export function DeleteSessionDialog({
  sessionId,
  title,
  current,
  labels,
  onClose,
}: {
  sessionId: string;
  title: string;
  /** The session is the one open on the page; deleting it leads to the start. */
  current: boolean;
  labels: DeleteSessionLabels;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [typed, setTyped] = useState("");
  const [state, action, pending] = useActionState(removeSession, INITIAL);
  const error = state.error ? labels[state.error] : null;

  useEffect(() => {
    const el = dialog.current;
    if (el && !el.open) el.showModal();
  }, []);
  // Deleted: the row is gone from the list, and the question with it.
  useEffect(() => {
    if (state.deleted) dialog.current?.close();
  }, [state]);

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      aria-labelledby="delete-session-title"
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-lg border border-border bg-surface p-5 text-text shadow-lg backdrop:bg-black/40"
    >
      <form action={action} className="space-y-3">
        <h2 id="delete-session-title" className="text-base font-semibold text-text-strong">
          {labels.title}
        </h2>
        <p className="text-sm leading-relaxed text-text-secondary">{labels.body}</p>
        <p className="break-words text-sm font-semibold text-text-strong">{title}</p>
        <input type="hidden" name="sessionId" value={sessionId} />
        {current && <input type="hidden" name="current" value="1" />}
        <label className="block text-sm text-text-secondary">
          {labels.confirmLabel}
          <input
            name="confirmation"
            data-testid="delete-session-confirmation"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            className="input-field mt-1 w-full"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-danger-text">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => dialog.current?.close()} className="btn-secondary">
            {labels.cancel}
          </button>
          <button
            type="submit"
            data-testid="delete-session-confirm"
            disabled={pending || typed.trim() !== title.trim()}
            className="rounded-lg bg-danger-text px-3 py-2 text-sm font-semibold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          >
            {labels.confirm}
          </button>
        </div>
      </form>
    </dialog>
  );
}
