"use client";

import Link, { useLinkStatus } from "next/link";
import { useEffect, useLayoutEffect, useRef, useState, useTransition } from "react";
import { renameSession } from "@/app/actions";
import type { DeleteSessionLabels } from "@/components/delete-session-dialog";
import { GateTrack } from "@/components/gate-track";
import { Icon } from "@/components/icons";
import { SessionRowMenu, type RowMenuLabels } from "@/components/session-row-menu";
import { GLIDE_EASING } from "@/lib/motion";
import {
  fillQuery,
  matchesSearch,
  showsSearch,
  type GateMark,
  type SessionDay,
  type Standing,
} from "@/lib/session-list";

/** One session as the sidebar lists it. The layout fills in every text on the
 *  server, so the browser formats no dates and renders what the server did. */
export type SessionRow = {
  id: string;
  title: string;
  day: SessionDay;
  marks: GateMark[];
  standing: Standing;
  /** "Vaihe 6/13" */
  stepLabel: string;
  /** The phase the session is on; empty once it is done. */
  phase: string;
  updatedIso: string;
  /** Short, by day group: "14.32", "pe 6.11.", "30.10.2026". */
  updated: string;
  updatedFull: string;
};

export type SessionListLabels = {
  /** The list's name as a landmark. */
  nav: string;
  days: Record<SessionDay, string>;
  search: string;
  searchPlaceholder: string;
  /** "{q}" is the search. */
  noResults: string;
  clearSearch: string;
  empty: string;
  loadFailed: string;
  done: string;
  waiting: string;
  rejected: string;
  updated: string;
  /** The rename field's name, and what it says when the name was not saved. */
  nameLabel: string;
  renameFailed: string;
  menu: RowMenuLabels;
  remove: DeleteSessionLabels;
};

const DAYS: SessionDay[] = ["today", "yesterday", "week", "earlier"];
const QUERY_MAX = 100;
const NAME_MAX = 80;

/**
 * Rows and day headings glide to their new place when the list itself changes
 * (a search narrows it, a session is deleted or started) instead of jumping.
 * `signature` names what is listed, not its order: after every reply the open
 * session moves to the top of today, and that is not something to animate.
 * Positions are read from the layout, not the screen, so a glide in progress
 * does not skew the next one.
 */
function useGlide(signature: string) {
  const root = useRef<HTMLDivElement>(null);
  const tops = useRef(new Map<string, number>());
  const listed = useRef(signature);
  useLayoutEffect(() => {
    const container = root.current;
    const changed = listed.current !== signature;
    listed.current = signature;
    if (!container) {
      tops.current = new Map();
      return;
    }
    const still = !changed || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const next = new Map<string, number>();
    container.querySelectorAll<HTMLElement>("[data-glide]").forEach((el) => {
      const key = el.dataset.glide!;
      const top = el.offsetTop;
      next.set(key, top);
      const before = tops.current.get(key);
      if (still || before === undefined || before === top || !el.animate) return;
      el.animate(
        [{ transform: `translateY(${before - top}px)` }, { transform: "translateY(0)" }],
        { duration: 260, easing: GLIDE_EASING },
      );
    });
    tops.current = next;
  });
  return root;
}

/** A spinner on the row that was pressed, while its session page loads. */
function Opening() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return (
    <span className="session-opening inline-flex">
      <Icon name="loaderCircle" size={13} className="animate-spin text-brand" />
    </span>
  );
}

/** What a row says in words beside its gates: only a standing the user acts
 *  on (it waits for them) or a final one. A session simply under way shows its
 *  gates alone; its phase is the gates' tooltip and part of the description. */
function StandingText({ row, labels }: { row: SessionRow; labels: SessionListLabels }) {
  if (row.standing === "open") return <span className="sr-only">{row.phase}</span>;
  const [text, tone] =
    row.standing === "done"
      ? [labels.done, "text-success-text"]
      : row.standing === "waiting"
        ? [labels.waiting, "text-brand-text"]
        : [labels.rejected, "text-danger-text"];
  return (
    <span data-testid="session-standing" title={text} className={`min-w-0 truncate font-medium ${tone}`}>
      {text}
    </span>
  );
}

/** The gates, the standing and the time of a row: its second line. The row's
 *  link is named by the session's title and described by this line. */
function RowState({ row, labels }: { row: SessionRow; labels: SessionListLabels }) {
  const step = row.phase ? `${row.stepLabel}: ${row.phase}` : row.stepLabel;
  return (
    <span id={`row-state-${row.id}`} className="mt-1 flex min-h-4 items-center gap-2 text-xs text-text-muted">
      <GateTrack marks={row.marks} title={step} />
      <span className="sr-only">{row.stepLabel}</span>
      <StandingText row={row} labels={labels} />
      <span className="ml-auto inline-flex shrink-0 items-center gap-1.5">
        <Opening />
        <time dateTime={row.updatedIso} title={row.updatedFull} className="text-[11px] tabular-nums">
          <span className="sr-only">{labels.updated} </span>
          {row.updated}
        </time>
      </span>
    </span>
  );
}

/**
 * The row's name as a field. Enter and leaving the field save, Esc cancels.
 * A name that could not be saved stays in the field, with the reason under it.
 */
function RenameField({
  row,
  title,
  labels,
  onDone,
}: {
  row: SessionRow;
  title: string;
  labels: SessionListLabels;
  /** `saved` is the new name; `byKey` says the keyboard ended it, so focus goes back to the row. */
  onDone: (outcome: { saved?: string; byKey: boolean }) => void;
}) {
  const [value, setValue] = useState(title);
  const [failed, setFailed] = useState(false);
  const [saving, startSaving] = useTransition();
  const field = useRef<HTMLInputElement>(null);
  // Enter saves and then the field loses focus as it goes: one save, not two.
  const settled = useRef(false);
  useEffect(() => {
    field.current?.focus();
    field.current?.select();
  }, []);

  const finish = (outcome: { saved?: string; byKey: boolean }) => {
    settled.current = true;
    onDone(outcome);
  };
  const save = (byKey: boolean) => {
    if (settled.current || saving) return;
    const name = value.replace(/\s+/g, " ").trim();
    // Nothing to save: an emptied field keeps the name it had.
    if (!name || name === title) return finish({ byKey });
    startSaving(async () => {
      const result = await renameSession(row.id, name).catch(() => null);
      if (result?.ok) finish({ saved: result.title, byKey });
      else setFailed(true);
    });
  };

  return (
    <div className="rounded-lg border border-border bg-surface px-2.5 py-2">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save(true);
        }}
      >
        <label htmlFor={`rename-${row.id}`} className="sr-only">
          {labels.nameLabel}
        </label>
        <input
          ref={field}
          id={`rename-${row.id}`}
          data-testid="rename-session-input"
          value={value}
          maxLength={NAME_MAX}
          readOnly={saving}
          autoComplete="off"
          aria-invalid={failed || undefined}
          aria-describedby={failed ? `rename-failed-${row.id}` : undefined}
          onChange={(e) => {
            setValue(e.target.value);
            setFailed(false);
          }}
          onBlur={() => save(false)}
          onKeyDown={(e) => {
            if (e.key !== "Escape") return;
            e.preventDefault();
            // Not for the drawer this row may be in: Esc ends the rename only.
            e.stopPropagation();
            finish({ byKey: true });
          }}
          // As tall as the title it stands in for, so the rows below stay put.
          className="-mx-1 -my-0.5 block w-[calc(100%+0.5rem)] rounded border border-border-strong bg-surface px-1 py-px text-[13.5px] font-medium leading-snug text-text outline-none focus:border-brand"
        />
      </form>
      <RowState row={row} labels={labels} />
      {failed && (
        <p id={`rename-failed-${row.id}`} role="alert" className="mt-1 text-xs text-danger-text">
          {labels.renameFailed}
        </p>
      )}
    </div>
  );
}

/**
 * The user's sessions, grouped by the day they were last touched. A row opens
 * its session; its rename, download, end and delete are behind one button.
 */
export function SidebarSessions({
  rows,
  activeId,
  loadFailed,
  labels,
  onDelete,
}: {
  rows: SessionRow[];
  /** The session open on the page, if one is. */
  activeId: string | null;
  loadFailed: boolean;
  labels: SessionListLabels;
  /** The row's menu asked to delete it; the sidebar asks for the confirmation. */
  onDelete: (row: { id: string; title: string }) => void;
}) {
  const [typed, setTyped] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  // A name just saved, shown until the list read from the server carries it.
  const [renamed, setRenamed] = useState<{ id: string; from: string; to: string } | null>(null);
  const titleOf = (row: SessionRow) =>
    renamed && renamed.id === row.id && renamed.from === row.title ? renamed.to : row.title;

  const searchShown = showsSearch(rows.length, typed.trim());
  const query = searchShown ? typed.trim() : "";
  const shown = query ? rows.filter((row) => matchesSearch(titleOf(row), query)) : rows;
  const groups = DAYS.map((day) => ({ day, rows: shown.filter((row) => row.day === day) })).filter(
    (group) => group.rows.length > 0,
  );
  const list = useGlide(
    `${query}\n${shown
      .map((row) => row.id)
      .sort()
      .join(" ")}`,
  );

  const endRename = (row: SessionRow, outcome: { saved?: string; byKey: boolean }) => {
    if (outcome.saved) setRenamed({ id: row.id, from: row.title, to: outcome.saved });
    setRenaming(null);
    if (!outcome.byKey) return;
    // The field is gone; the row it stood on takes the focus back.
    requestAnimationFrame(() => {
      list.current?.querySelector<HTMLElement>(`[data-row-link="${row.id}"]`)?.focus();
    });
  };

  return (
    <>
      {searchShown && (
        <form role="search" onSubmit={(e) => e.preventDefault()} className="relative shrink-0 px-2 pb-2">
          <label htmlFor="session-search" className="sr-only">
            {labels.search}
          </label>
          <Icon
            name="search"
            size={14}
            className="pointer-events-none absolute left-[18px] top-[9px] text-text-muted"
          />
          <input
            id="session-search"
            type="search"
            value={typed}
            maxLength={QUERY_MAX}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={labels.searchPlaceholder}
            className="input-field py-1.5 pl-8 text-[13px]"
          />
        </form>
      )}

      <nav aria-label={labels.nav} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loadFailed ? (
          <p role="status" className="px-2.5 py-2 text-[13px] text-warning-text">
            {labels.loadFailed}
          </p>
        ) : rows.length === 0 ? (
          <p className="px-2.5 py-2 text-[13px] text-text-muted">{labels.empty}</p>
        ) : shown.length === 0 ? (
          <p className="px-2.5 py-2 text-[13px] leading-relaxed text-text-secondary">
            {fillQuery(labels.noResults, query)}{" "}
            <button
              type="button"
              onClick={() => {
                setTyped("");
                document.getElementById("session-search")?.focus();
              }}
              className="rounded-sm font-medium text-brand-text underline"
            >
              {labels.clearSearch}
            </button>
          </p>
        ) : (
          <div ref={list} className="relative space-y-4">
            {groups.map(({ day, rows: dayRows }) => (
              <section key={day} aria-labelledby={`day-${day}`}>
                <h2
                  id={`day-${day}`}
                  data-glide={`day-${day}`}
                  className="px-2.5 pb-1 text-[11px] font-medium text-text-muted"
                >
                  {labels.days[day]}
                </h2>
                <ul className="space-y-0.5">
                  {dayRows.map((row) => {
                    const active = row.id === activeId;
                    const title = titleOf(row);
                    return (
                      <li
                        key={row.id}
                        data-glide={row.id}
                        data-active={active || undefined}
                        className="session-row relative"
                      >
                        {renaming === row.id ? (
                          <RenameField
                            row={row}
                            title={title}
                            labels={labels}
                            onDone={(outcome) => endRename(row, outcome)}
                          />
                        ) : (
                          <>
                            <Link
                              href={`/sessions/${row.id}`}
                              data-testid="session-card"
                              data-row-link={row.id}
                              aria-current={active ? "page" : undefined}
                              // Named by the title alone; the gates' step, the
                              // standing and the time are its description.
                              aria-label={title}
                              aria-describedby={`row-state-${row.id}`}
                              className={`block rounded-lg border px-2.5 py-2 transition-colors duration-150 ${
                                active
                                  ? "border-border bg-surface"
                                  : "border-transparent hover:bg-surface-muted/70 active:bg-surface-muted"
                              }`}
                            >
                              <span
                                title={title}
                                className={`session-row-title block truncate text-[13.5px] leading-snug ${
                                  active ? "font-semibold text-text-strong" : "font-medium text-text"
                                }`}
                              >
                                {title}
                              </span>
                              <RowState row={row} labels={labels} />
                            </Link>
                            <SessionRowMenu
                              sessionId={row.id}
                              title={title}
                              labels={labels.menu}
                              onRename={() => setRenaming(row.id)}
                              onDelete={() => onDelete({ id: row.id, title })}
                            />
                          </>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        )}
      </nav>
    </>
  );
}
