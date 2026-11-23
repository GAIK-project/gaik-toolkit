"use client";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import type { Blueprint, BlueprintStep, BlueprintStepType } from "@/lib/mock-sessions";
import { parseBlueprintJson } from "@/lib/blueprint-parse";
import {
  BLUEPRINT_AUTOSAVE_DELAY_MS,
  BLUEPRINT_CHANGED_ELSEWHERE,
  BLUEPRINT_KEEPALIVE_MAX_BYTES,
  blueprintBaseTag,
  blueprintDraftProblem,
  blueprintPayload,
  blueprintPayloadKey,
  renameSetting,
  restoreStep,
} from "@/lib/blueprint-draft";
import { fillTemplate } from "@/lib/chat-template";
import { scrollClip, scrollTarget } from "@/lib/scroll-ancestor";
import type { Dict } from "@/lib/i18n";
import { BlueprintModeBar } from "@/components/blueprint-mode-bar";
import { Icon } from "@/components/icons";
import {
  AskStepButton,
  STEP_TYPES,
  STEP_TYPE_ICON,
  STEP_TYPE_TEXT,
  StepNumber,
  StepTypeTag,
  stepTypeLabels,
} from "@/components/step-type";

/** How long "Vaihe poistettu · Kumoa" stays after a step is deleted. */
const UNDO_DELETE_MS = 5000;
/** A dragged step scrolls its list while the pointer is this near an edge, this much a frame. */
const DRAG_SCROLL_EDGE = 48;
const DRAG_SCROLL_STEP = 12;

function newStepId(existing: BlueprintStep[]): string {
  const ids = new Set(existing.map((s) => s.id));
  let candidate = "";
  do {
    candidate = `step_${Math.random().toString(36).slice(2, 8)}`;
  } while (ids.has(candidate));
  return candidate;
}

function settingsEntries(step: BlueprintStep): [string, string][] {
  return Object.entries(step.settings ?? {});
}

/** What the server has: its content as a key, and the steps the wizard can be asked about. */
function savedState(blueprint: Blueprint) {
  return { key: blueprintPayloadKey(blueprint), stepIds: new Set(blueprint.steps.map((s) => s.id)) };
}

/**
 * A setting's key. It is typed freely and takes effect when the field is
 * left; a key that is empty or already another setting's is not taken, and
 * the field shows the setting's own key again.
 */
function SettingKeyInput({
  settingKey,
  canRenameTo,
  onRename,
  ...props
}: {
  settingKey: string;
  canRenameTo: (key: string) => boolean;
  onRename: (key: string) => void;
  className: string;
  placeholder: string;
  "aria-label": string;
  "data-testid": string;
}) {
  const [text, setText] = useState(settingKey);
  // The row now stands for another setting (one above it was removed), or the rename went through.
  useEffect(() => setText(settingKey), [settingKey]);
  return (
    <input
      type="text"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const next = text.trim();
        if (next && next !== settingKey && canRenameTo(next)) onRename(next);
        else setText(settingKey);
      }}
      {...props}
    />
  );
}

/**
 * The blueprint as a form: its name, goal and description, and the process
 * steps in order, as one page the tab scrolls. A step opens in place: its
 * name, description and type, its component and settings behind "Tekniset
 * asetukset", and what can be done with the step itself (move, add one after
 * it, ask the wizard, remove). The form saves by itself a moment after the
 * last edit and when a field is left, as long as every step has a name; the
 * line beside `control` says where the draft stands.
 */
export function BlueprintJsonEditor({
  sessionId,
  blueprint,
  onSaved,
  onStuckChange,
  pocNoteLabel = null,
  control,
  controlNote = null,
  t,
}: {
  sessionId: string;
  blueprint: Blueprint;
  onSaved: (blueprint: Blueprint) => void;
  /**
   * Whether the form holds a draft it cannot save by itself: a step or the
   * blueprint has no name, the JSON does not parse, a save failed, or the
   * blueprint changed elsewhere and the user has not chosen. The form says
   * why itself; whoever can hide the form keeps it in view meanwhile.
   */
  onStuckChange?: (stuck: boolean) => void;
  /** Shown while saved changes are not in the PoC package yet. */
  /** Said after a save while the PoC package lacks it, with the control that generates the package again. */
  pocNoteLabel?: ReactNode;
  /** What closes the form ("Valmis"); the save status sits beside it. */
  control: ReactNode;
  /** A line under that row, e.g. why the form did not close. */
  controlNote?: ReactNode;
  t: Dict;
}) {
  const router = useRouter();
  const [draft, setDraft] = useState<Blueprint>(() => structuredClone(blueprint));
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [jsonText, setJsonText] = useState(() => JSON.stringify(blueprint, null, 2));
  const jsonFocused = useRef(false);
  const [parseError, setParseError] = useState(false);
  const parseErrorRef = useRef(parseError);
  parseErrorRef.current = parseError;
  const [saveState, setSaveState] = useState<"idle" | "saving" | "error">("idle");
  const [saved, setSaved] = useState(() => savedState(blueprint));
  const savedRef = useRef(saved);
  savedRef.current = saved;
  // Step cards are collapsed by default; expand on demand or when just added.
  const [openSteps, setOpenSteps] = useState<Set<string>>(new Set());
  // The blueprint was replaced (agent, Workflow tab) while this draft had unsaved edits.
  const [changedElsewhere, setChangedElsewhere] = useState(false);
  const newer = useRef<Blueprint | null>(null);
  // A save reached the server while that choice was open: the server then
  // holds the draft, not the newer version.
  const savedOverNewer = useRef(false);
  // The step deleted last, while "Kumoa" can still bring it back.
  const [removed, setRemoved] = useState<{ step: BlueprintStep; index: number } | null>(null);
  const uid = useId();
  const typeLabel = stepTypeLabels(t);
  const saving = useRef(false);
  /** The save on its way: its content, a way to cancel it, and a promise that resolves when it has ended, however it ended. */
  const sending = useRef<{ key: string; ended: Promise<void>; cancel: () => void } | null>(null);
  /** The draft a save last failed on: it is not sent again until it changes or the user retries. */
  const failedKey = useRef<string | null>(null);

  /** Takes `next` into the form. `unsaved`: the server does not hold it, so it is left for the form to save. */
  function adopt(next: Blueprint, { unsaved = false }: { unsaved?: boolean } = {}) {
    newer.current = null;
    savedOverNewer.current = false;
    failedKey.current = null;
    setDraft(structuredClone(next));
    setJsonText(JSON.stringify(next, null, 2));
    if (!unsaved) setSaved(savedState(next));
    setOpenSteps((prev) => new Set([...prev].filter((id) => next.steps.some((s) => s.id === id))));
    setParseError(false);
    setSaveState("idle");
    setChangedElsewhere(false);
    setRemoved(null);
  }

  // A new blueprint from outside (the agent wrote a version, the Workflow tab
  // saved one): a draft without unsaved edits takes it; an edited draft is
  // kept, and the user chooses which one stays.
  const baseRef = useRef(blueprint);
  useEffect(() => {
    if (baseRef.current === blueprint) return;
    baseRef.current = blueprint;
    const incoming = blueprintPayloadKey(blueprint);
    if (incoming === savedRef.current.key) return;
    const mine = blueprintPayloadKey(draftRef.current);
    if (mine === savedRef.current.key || mine === incoming) {
      adopt(blueprint);
      return;
    }
    newer.current = blueprint;
    savedOverNewer.current = false;
    setChangedElsewhere(true);
    // Only a new blueprint is compared; draft edits must not re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blueprint]);

  // Keep the raw JSON escape hatch in sync with form edits, unless the user
  // is actively typing in the textarea (avoids fighting the cursor). JSON
  // that did not parse is replaced by the form's draft, so it is valid again.
  useEffect(() => {
    if (!jsonFocused.current) {
      setJsonText(JSON.stringify(draft, null, 2));
      setParseError(false);
    }
  }, [draft]);

  const draftKey = useMemo(() => blueprintPayloadKey(draft), [draft]);
  const dirty = draftKey !== saved.key;
  const problem = parseError ? "json" : blueprintDraftProblem(draft);

  // A draft the form cannot save by itself; see `onStuckChange`.
  const stuck = parseError || (dirty && (problem !== null || saveState === "error" || changedElsewhere));
  const onStuck = useRef(onStuckChange);
  onStuck.current = onStuckChange;
  useEffect(() => {
    onStuck.current?.(stuck);
  }, [stuck]);

  // `base`: the tag of the blueprint the edit was made on (see blueprintBaseTag).
  function sendBlueprint(payload: Blueprint, signal?: AbortSignal, base?: string) {
    const body = JSON.stringify({ content: payload, note: "Blueprint päivitetty lomake-editorista", ...(base ? { base } : {}) });
    return fetch(`/api/sessions/${sessionId}/blueprint`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body,
      signal,
      // The request outlives the page, so a reload or a closed tab does not
      // cancel a save. Browsers allow it only for a small body, counted in
      // bytes; a larger one is sent the ordinary way, and the browser's own
      // question before the page closes is what protects it.
      keepalive: new Blob([body]).size <= BLUEPRINT_KEEPALIVE_MAX_BYTES,
    });
  }

  async function save({ overNewer = false }: { overNewer?: boolean } = {}) {
    if (saving.current || parseErrorRef.current) return;
    const current = draftRef.current;
    if (blueprintDraftProblem(current)) return;
    if (newer.current && !overNewer) return;
    const payload = blueprintPayload(current);
    const key = JSON.stringify(payload);
    if (key === savedRef.current.key && !overNewer) return;
    saving.current = true;
    let ended!: () => void;
    const controller = new AbortController();
    sending.current = {
      key,
      ended: new Promise<void>((resolve) => (ended = resolve)),
      cancel: () => controller.abort(),
    };
    setSaveState("saving");
    try {
      // Sent over a newer version only by the user's choice; by itself, only
      // on the version the form last read.
      const res = await sendBlueprint(
        payload,
        controller.signal,
        overNewer ? undefined : blueprintBaseTag(baseRef.current),
      );
      if (res.status === 409) {
        const refused = (await res.json().catch(() => null)) as { error?: string } | null;
        if (refused?.error === BLUEPRINT_CHANGED_ELSEWHERE) {
          // The agent (or another tab) wrote a version since: the page reads it,
          // and the form asks which one stays, as when it arrives by itself.
          // This draft is not sent again by itself meanwhile.
          failedKey.current = key;
          setSaveState("idle");
          router.refresh();
          return;
        }
      }
      if (!res.ok) throw new Error("save failed");
      const data = (await res.json()) as { blueprint: Blueprint };
      failedKey.current = null;
      // Only the user's choice ("keep mine") settles a newer version. One
      // that arrived while this save was on its way is still to be chosen
      // between: the save was not sent over it knowingly.
      if (overNewer) {
        newer.current = null;
        savedOverNewer.current = false;
        setChangedElsewhere(false);
      } else if (newer.current) {
        savedOverNewer.current = true;
      }
      // What was typed stays in the fields as typed; only "what is saved" moves on.
      const next = { key, stepIds: new Set(payload.steps.map((s) => s.id)) };
      savedRef.current = next;
      setSaved(next);
      baseRef.current = data.blueprint;
      setSaveState("idle");
      onSaved(data.blueprint);
    } catch {
      failedKey.current = key;
      setSaveState("error");
    } finally {
      saving.current = false;
      sending.current = null;
      ended();
    }
  }
  const saveRef = useRef(save);
  saveRef.current = save;

  /**
   * "Ota uudempi". When a save landed while the choice was open, the server
   * holds the draft that save sent, so the version picked is written back at
   * once; shown as saved without that, a reload would bring the draft back.
   */
  function takeNewer() {
    const theirs = newer.current;
    if (!theirs) return;
    const unsaved = savedOverNewer.current;
    adopt(theirs, { unsaved });
    if (unsaved) {
      flushNow.current = true;
      setFlushTick((n) => n + 1);
    }
  }

  /**
   * The page may be closing (`gone` false: the browser is still asking) or is
   * closing (`gone` true): what is unsaved goes out now, since nothing can
   * wait any more.
   */
  function saveOnLeave(gone: boolean) {
    if (!saving.current) {
      void saveRef.current();
      return;
    }
    // A save is on its way with an older draft. While the browser is still
    // asking, it is left to finish: if the user stays, the form saves the
    // rest as usual. Once the page is going, the older save is cancelled and
    // the newer draft sent in its place, so two saves are not on their way
    // at once with nothing to say which the server takes last.
    if (!gone) return;
    const current = draftRef.current;
    if (parseErrorRef.current || blueprintDraftProblem(current) || newer.current) return;
    const payload = blueprintPayload(current);
    if (JSON.stringify(payload) === sending.current?.key) return;
    sending.current?.cancel();
    sendBlueprint(payload).catch(() => {});
  }
  const saveOnLeaveRef = useRef(saveOnLeave);
  saveOnLeaveRef.current = saveOnLeave;

  // Saving by itself: a moment after the last edit, or at once when a field
  // is left. Not while the draft cannot be saved, and not over a newer
  // version the user has not chosen between yet.
  const flushNow = useRef(false);
  const [flushTick, setFlushTick] = useState(0);
  useEffect(() => {
    const flush = flushNow.current;
    flushNow.current = false;
    if (!dirty || problem || changedElsewhere || saveState === "saving") return;
    if (failedKey.current === draftKey) return;
    // A deleted step is not written as a version while "Kumoa" can still
    // bring it back; the save follows when the note has gone.
    if (removed) return;
    if (flush) {
      void saveRef.current();
      return;
    }
    const timer = window.setTimeout(() => void saveRef.current(), BLUEPRINT_AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [draftKey, dirty, problem, changedElsewhere, saveState, flushTick, removed]);

  // Leaving the form (the session's page closing) saves what is still
  // waiting, after a save on its way: an edit typed during that save was
  // dropped when this returned at once.
  useEffect(
    () => () => {
      void (sending.current?.ended ?? Promise.resolve()).then(() => saveRef.current());
    },
    [],
  );

  // A reload or a closed tab unmounts nothing: the draft is sent as the page
  // goes, and while something is unsaved the browser asks before it goes.
  useEffect(() => {
    const onHide = () => saveOnLeaveRef.current(true);
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, []);
  const unsaved = dirty || parseError;
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => {
      // Sent here already, before the next page is asked for, so a reload shows the edit.
      saveOnLeaveRef.current(false);
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  useEffect(() => {
    if (!removed) return;
    const timer = window.setTimeout(() => setRemoved(null), UNDO_DELETE_MS);
    return () => window.clearTimeout(timer);
  }, [removed]);

  function patchDraft(next: Partial<Blueprint>) {
    setDraft((d) => ({ ...d, ...next }));
  }

  function patchStep(index: number, patch: Partial<BlueprintStep>) {
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    }));
  }

  // The name field of a step just added takes the cursor: a step needs a name to be saved.
  const focusName = useRef<string | null>(null);
  useEffect(() => {
    if (!focusName.current) return;
    document.getElementById(`${uid}-step-${focusName.current}-name`)?.focus();
    focusName.current = null;
  });

  /** A new step at `at`: after the step it was asked from, or last. */
  function addStep(at = draft.steps.length) {
    const id = newStepId(draft.steps);
    setDraft((d) => {
      const steps = [...d.steps];
      steps.splice(at, 0, { id, name: "", type: "io" as BlueprintStepType });
      return { ...d, steps };
    });
    setOpenSteps((prev) => new Set(prev).add(id));
    focusName.current = id;
  }

  function toggleStep(id: string) {
    setOpenSteps((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function removeStep(index: number) {
    const step = draft.steps[index];
    if (!step) return;
    setDraft((d) => ({ ...d, steps: d.steps.filter((s) => s.id !== step.id) }));
    setRemoved({ step, index });
  }

  function undoRemove() {
    if (!removed) return;
    const { step, index } = removed;
    setDraft((d) => ({ ...d, steps: restoreStep(d.steps, step, index) }));
    setRemoved(null);
  }

  // The control to focus once a step moved from the keyboard or by its
  // buttons has been drawn in its new place: React moves the row in the page,
  // and a moved row loses focus. A button that the move disabled (the step is
  // now first or last) hands the focus to its pair.
  const focusAfterMove = useRef<{ index: number; via: "drag" | "up" | "down" } | null>(null);
  useLayoutEffect(() => {
    const moved = focusAfterMove.current;
    if (!moved) return;
    focusAfterMove.current = null;
    const control = (via: string) =>
      stepListRef.current?.querySelector<HTMLButtonElement>(
        `[data-testid="blueprint-step-${moved.index}-${via}"]`,
      );
    const wanted = control(moved.via);
    (wanted?.disabled ? control(moved.via === "up" ? "down" : "up") : wanted)?.focus();
  });

  function moveStep(index: number, dir: -1 | 1, via: "drag" | "up" | "down") {
    const target = index + dir;
    if (target < 0 || target >= draft.steps.length) return;
    focusAfterMove.current = { index: target, via };
    setDraft((d) => {
      if (target >= d.steps.length) return d;
      const steps = [...d.steps];
      [steps[index], steps[target]] = [steps[target], steps[index]];
      return { ...d, steps };
    });
  }

  function moveStepTo(from: number, to: number) {
    if (from === to) return;
    setDraft((d) => {
      const steps = [...d.steps];
      const [moved] = steps.splice(from, 1);
      steps.splice(to, 0, moved);
      return { ...d, steps };
    });
  }

  // Dragging a step by its handle. `dropAt` is the gap the step would land in:
  // 0 is above the first step, steps.length below the last.
  //
  // The drag is seen as it happens: the dragged row follows the pointer, and
  // the rows it passes step aside into the place it left (a transform each,
  // 150 ms). The rows keep their order in the page until the drop, since a row
  // moved in the page mid-drag would lose the pointer it has captured; the
  // drop then writes the order the rows already show.
  const stepListRef = useRef<HTMLOListElement>(null);
  const [drag, setDrag] = useState<{
    from: number;
    dropAt: number;
    pointerId: number;
    startY: number;
    /** Where the list's top was on screen as the drag began: it moves when the tab scrolls. */
    startListTop: number;
    /** How far a row steps aside: the dragged row's height and the gap between rows. */
    shift: number;
    /** The pointer has moved far enough to count as a drag, not a click. */
    moved: boolean;
  } | null>(null);
  const pointerY = useRef(0);
  const dragRef = useRef(drag);
  dragRef.current = drag;

  // The rows as the page lays them out, without the transforms a drag puts on
  // them: a row that has stepped aside still counts where it stands in the order.
  function gapAt(clientY: number): number {
    const list = stepListRef.current;
    if (!list) return 0;
    const rows = [...list.children] as HTMLElement[];
    const y = clientY - list.getBoundingClientRect().top;
    const below = rows.findIndex((row) => y < row.offsetTop + row.offsetHeight / 2);
    return below === -1 ? rows.length : below;
  }

  // The dragged row under the pointer, also while the tab scrolls beneath it,
  // and never past the list's own ends: a row carried below the last one would
  // make the tab longer, and the scroll at its edge would never end.
  // Written to the row itself: a pointer move does not draw the form again.
  function placeDragged() {
    const d = dragRef.current;
    const list = stepListRef.current;
    const row = d?.moved ? (list?.children[d.from] as HTMLElement | undefined) : undefined;
    if (!d || !list || !row) return;
    const y = pointerY.current - d.startY - (list.getBoundingClientRect().top - d.startListTop);
    const least = -row.offsetTop;
    const most = list.clientHeight - row.offsetTop - row.offsetHeight;
    row.style.transform = `translateY(${Math.round(Math.min(Math.max(y, least), most))}px)`;
  }

  function dropDragged(from: number) {
    const row = stepListRef.current?.children[from] as HTMLElement | undefined;
    if (row) row.style.transform = "";
    setDrag(null);
  }

  // One pointer drives a drag; a second finger or pen is ignored until it ends.
  function startDrag(e: React.PointerEvent<HTMLButtonElement>, index: number) {
    if (e.button !== 0 || drag || draft.steps.length < 2) return;
    e.preventDefault();
    e.currentTarget.focus();
    e.currentTarget.setPointerCapture(e.pointerId);
    pointerY.current = e.clientY;
    const list = stepListRef.current;
    const rows = [...(list?.children ?? [])] as HTMLElement[];
    const row = rows[index];
    const gap = rows.length > 1 ? rows[1].offsetTop - rows[0].offsetTop - rows[0].offsetHeight : 0;
    setDrag({
      from: index,
      dropAt: index,
      pointerId: e.pointerId,
      startY: e.clientY,
      startListTop: list?.getBoundingClientRect().top ?? 0,
      shift: (row?.offsetHeight ?? 0) + Math.max(gap, 0),
      moved: false,
    });
  }

  function moveDrag(e: React.PointerEvent<HTMLButtonElement>) {
    if (!drag || e.pointerId !== drag.pointerId) return;
    pointerY.current = e.clientY;
    const moved = drag.moved || Math.abs(e.clientY - drag.startY) > 4;
    if (!moved) return;
    const dropAt = gapAt(e.clientY);
    if (dropAt !== drag.dropAt || !drag.moved) {
      const next = { ...drag, dropAt, moved };
      dragRef.current = next;
      setDrag(next);
    }
    placeDragged();
  }

  function endDrag(e: React.PointerEvent<HTMLButtonElement>) {
    if (!drag || e.pointerId !== drag.pointerId) return;
    if (drag.moved) {
      const dropAt = gapAt(e.clientY);
      moveStepTo(drag.from, dropAt > drag.from ? dropAt - 1 : dropAt);
    }
    dropDragged(drag.from);
  }

  // While dragging, the list scrolls when the pointer is held near the edge
  // of what it is seen through, and the gap under the pointer follows any
  // scroll (the wheel too), so a step can reach a place that is not on screen.
  // What scrolls is found from the page as it is (lib/scroll-ancestor): the
  // nearest ancestor that can still move that way, the page itself last. The
  // edges are those of the nearest ancestor that clips the list, kept inside
  // the window, with the top one under the row that stays at the tab's top.
  const barRef = useRef<HTMLDivElement>(null);
  const draggingMoved = drag?.moved === true;
  useEffect(() => {
    if (!draggingMoved) return;
    const list = stepListRef.current;
    const page = document.scrollingElement as HTMLElement | null;
    let frame = 0;
    const tick = () => {
      if (list) {
        const clip = scrollClip<HTMLElement>(list);
        const view = clip && clip !== page && clip !== document.body ? clip.getBoundingClientRect() : null;
        const top = Math.max(view?.top ?? 0, 0, barRef.current?.getBoundingClientRect().bottom ?? 0);
        const bottom = Math.min(view?.bottom ?? window.innerHeight, window.innerHeight);
        const y = pointerY.current;
        const direction = y < top + DRAG_SCROLL_EDGE ? -1 : y > bottom - DRAG_SCROLL_EDGE ? 1 : 0;
        const scroller = direction ? scrollTarget<HTMLElement>(list, direction, page) : null;
        if (scroller) scroller.scrollTop += direction * DRAG_SCROLL_STEP;
      }
      setDrag((d) => {
        if (!d) return d;
        const dropAt = gapAt(pointerY.current);
        return dropAt === d.dropAt ? d : { ...d, dropAt };
      });
      placeDragged();
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // gapAt and placeDragged read only refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draggingMoved]);

  // A step's technical settings: key/value pairs for its component.
  function addSetting(index: number) {
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, i) => {
        if (i !== index) return s;
        const entries = settingsEntries(s);
        let n = entries.length + 1;
        let key = `setting_${n}`;
        while (entries.some(([k]) => k === key)) key = `setting_${++n}`;
        return { ...s, settings: { ...s.settings, [key]: "" } };
      }),
    }));
  }

  function renameSettingKey(index: number, oldKey: string, newKey: string) {
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, i) => {
        if (i !== index || !s.settings) return s;
        const settings = renameSetting(s.settings, oldKey, newKey);
        return settings === s.settings ? s : { ...s, settings };
      }),
    }));
  }

  function patchSettingValue(index: number, key: string, value: string) {
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, i) =>
        i === index ? { ...s, settings: { ...s.settings, [key]: value } } : s,
      ),
    }));
  }

  function removeSetting(index: number, key: string) {
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s, i) => {
        if (i !== index || !s.settings) return s;
        const next = { ...s.settings };
        delete next[key];
        return { ...s, settings: next };
      }),
    }));
  }

  function onJsonChange(value: string) {
    setJsonText(value);
    const parsed = parseBlueprintJson(value);
    if (parsed) {
      setParseError(false);
      setDraft(parsed);
    } else {
      setParseError(true);
    }
  }

  // Where the draft stands, as one quiet line beside the heading.
  let status: { state: "saved" | "saving" | "unsaved" | "error"; body: ReactNode };
  if (saveState === "saving") {
    status = {
      state: "saving",
      body: (
        <>
          <Icon name="loaderCircle" size={14} className="motion-safe:animate-spin" />
          {t.wsJsonSaving}
        </>
      ),
    };
  } else if (problem) {
    status = {
      state: "unsaved",
      body: (
        <span className="text-warning-text">
          {problem === "json" ? t.wsJsonInvalid : problem === "stepName" ? t.formUnsavedStepName : t.formUnsavedName}
        </span>
      ),
    };
  } else if (saveState === "error" && dirty) {
    status = {
      state: "error",
      body: (
        <span className="inline-flex items-center gap-2 text-danger-text">
          {t.wsJsonSaveError}
          <button
            type="button"
            className="font-medium underline underline-offset-2"
            onClick={() => void save({ overNewer: changedElsewhere })}
            data-testid="blueprint-save-retry"
          >
            {t.editorRetry}
          </button>
        </span>
      ),
    };
  } else if (dirty) {
    // Waiting for the typing to stop, or for the user to choose over a newer version.
    status = { state: "unsaved", body: changedElsewhere ? null : t.wsJsonSaving };
  } else {
    status = {
      state: "saved",
      body: (
        <>
          <Icon name="check" size={14} className="text-success-text" />
          {t.wsJsonSaved}
        </>
      ),
    };
  }

  const fieldLabel = "text-xs font-medium text-text-strong";
  const disclosure =
    "inline-flex cursor-pointer list-none items-center gap-1 rounded text-xs font-medium text-text-muted transition-colors duration-150 hover:text-text [&::-webkit-details-marker]:hidden";
  const disclosureMark = "transition-transform duration-150 ease-out group-open:rotate-90 motion-reduce:transition-none";

  return (
    // One page with the read view's width: the tab scrolls it, nothing inside it does.
    <div
      className="@container flex max-w-4xl flex-col gap-4 pb-2 pr-1"
      onBlur={(e) => {
        const tag = (e.target as HTMLElement).tagName;
        if (tag !== "INPUT" && tag !== "TEXTAREA") return;
        flushNow.current = true;
        setFlushTick((n) => n + 1);
      }}
      data-testid="blueprint-form"
    >
      <BlueprintModeBar ref={barRef} mode="edit" control={control}>
        <span
          className="inline-flex min-w-0 items-center gap-1.5 text-xs text-text-muted"
          role="status"
          data-testid="blueprint-save-status"
          data-state={status.state}
        >
          {status.body}
        </span>
      </BlueprintModeBar>
      <div className="flex flex-col gap-3">
        {controlNote}
        {pocNoteLabel && (
          <p
            role="status"
            className="flex items-start gap-1.5 text-xs text-text-muted"
            data-testid="blueprint-saved-poc-note"
          >
            <Icon name="info" size={14} className="mt-px" />
            <span>{pocNoteLabel}</span>
          </p>
        )}
        {changedElsewhere && (
          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-xs text-warning-text"
            role="status"
            data-testid="blueprint-changed-elsewhere"
          >
            <span className="min-w-0 flex-1 basis-56">{t.wsJsonChangedElsewhere}</span>
            <button
              type="button"
              className="btn-secondary px-3 py-1 text-xs"
              onClick={takeNewer}
              data-testid="blueprint-take-newer"
            >
              {t.formTakeNewer}
            </button>
            <button
              type="button"
              className="btn-secondary px-3 py-1 text-xs"
              onClick={() => void save({ overNewer: true })}
              disabled={Boolean(problem) || saveState === "saving"}
              data-testid="blueprint-keep-mine"
            >
              {t.formKeepMine}
            </button>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label htmlFor={`${uid}-name`} className={fieldLabel}>
            {t.wsFormName}
          </label>
          <input
            id={`${uid}-name`}
            type="text"
            className="input-field"
            value={draft.name}
            aria-invalid={!draft.name.trim() || undefined}
            onChange={(e) => patchDraft({ name: e.target.value })}
            data-testid="blueprint-field-name"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`${uid}-goal`} className={fieldLabel}>
            {t.wsBlueprintGoal}
          </label>
          <textarea
            id={`${uid}-goal`}
            className="input-field min-h-[52px] resize-y"
            value={draft.goal ?? ""}
            onChange={(e) => patchDraft({ goal: e.target.value })}
            data-testid="blueprint-field-goal"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`${uid}-description`} className={fieldLabel}>
            {t.wsFormDescription}
          </label>
          <textarea
            id={`${uid}-description`}
            className="input-field min-h-[72px] resize-y"
            value={draft.description ?? ""}
            onChange={(e) => patchDraft({ description: e.target.value })}
            data-testid="blueprint-field-description"
          />
        </div>
      </div>

      <section className="mt-2 flex min-w-0 flex-col gap-2" aria-labelledby={`${uid}-steps`}>
        <h3 id={`${uid}-steps`} className="text-sm font-semibold text-text-strong" data-testid="blueprint-steps-heading">
          {t.wsFormSteps} <span className="font-normal text-text-muted">({draft.steps.length})</span>
        </h3>

        {draft.steps.length === 0 && <p className="text-sm text-text-muted">{t.wsFormEmptySteps}</p>}

        <ol ref={stepListRef} className="relative flex flex-col gap-2">
          {draft.steps.map((step, index) => {
            const base = `${uid}-step-${step.id}`;
            const named = step.name.trim().length > 0;
            const stepLabel = named ? step.name.trim() : fillTemplate(t.bpmnStepTitle, { n: String(index + 1) });
            const isOpen = openSteps.has(step.id);
            const settings = settingsEntries(step);
            const dragging = drag?.moved === true;
            const dragged = dragging && drag.from === index;
            // Where the dragged row would land, and so which rows are in its way:
            // those between its place and that one step into the place it left.
            const landsAt = dragging ? (drag.dropAt > drag.from ? drag.dropAt - 1 : drag.dropAt) : index;
            const aside =
              !dragging || dragged
                ? 0
                : drag.from < index && index <= landsAt
                  ? -drag.shift
                  : landsAt <= index && index < drag.from
                    ? drag.shift
                    : 0;
            // A single step has no other place to go: the handle says so.
            const onlyStep = draft.steps.length < 2;
            return (
              <li
                key={step.id}
                className={`rounded-lg border bg-surface focus-within:border-brand/60 ${
                  isOpen ? "border-border-strong" : "border-border"
                } ${
                  dragged
                    ? "relative z-[1] shadow-md"
                    : dragging
                      ? "transition-transform duration-150 ease-out motion-reduce:transition-none"
                      : "transition-[box-shadow,border-color] duration-150"
                }`}
                // The dragged row's own transform is written as the pointer moves (placeDragged).
                style={dragging && !dragged ? { transform: `translateY(${aside}px)` } : undefined}
                aria-label={`${index + 1}. ${stepLabel}`}
                data-testid={`blueprint-step-${index}`}
                data-dragging={dragged || undefined}
              >
                <div className="flex items-center gap-1 p-1.5">
                  <button
                    type="button"
                    className={`flex h-8 w-6 shrink-0 touch-none items-center justify-center rounded text-text-muted transition-colors duration-150 ${
                      onlyStep
                        ? "cursor-not-allowed opacity-50"
                        : "cursor-grab hover:bg-surface-muted hover:text-text active:cursor-grabbing"
                    }`}
                    aria-label={`${t.wsFormDragStep} — ${stepLabel}`}
                    aria-disabled={onlyStep || undefined}
                    title={onlyStep ? t.wsFormDragOnly : t.wsFormDragStep}
                    onPointerDown={(e) => startDrag(e, index)}
                    onPointerMove={moveDrag}
                    onPointerUp={endDrag}
                    onPointerCancel={(e) => {
                      if (drag?.pointerId === e.pointerId) dropDragged(drag.from);
                    }}
                    onLostPointerCapture={(e) => {
                      if (drag?.pointerId === e.pointerId) dropDragged(drag.from);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
                        e.preventDefault();
                        moveStep(index, e.key === "ArrowUp" ? -1 : 1, "drag");
                      }
                    }}
                    data-testid={`blueprint-step-${index}-drag`}
                  >
                    <Icon name="gripVertical" size={16} />
                  </button>
                  {/* The whole row opens the step: its number, name and type, and the mark that it opens. */}
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-3 rounded-md py-1 pl-1 pr-1.5 text-left"
                    aria-expanded={isOpen}
                    aria-controls={`${base}-body`}
                    aria-label={`${isOpen ? t.wsFormCollapseStep : t.wsFormExpandStep} — ${stepLabel}`}
                    onClick={() => toggleStep(step.id)}
                    data-testid={`blueprint-step-${index}-toggle`}
                  >
                    <StepNumber n={index + 1} type={step.type} />
                    <span className="min-w-0 flex-1">
                      <span
                        className={`block truncate text-sm font-medium ${named ? "text-text-strong" : "text-text-muted"}`}
                      >
                        {stepLabel}
                      </span>
                      <span className="flex min-w-0 items-center gap-1.5 text-xs text-text-muted">
                        <StepTypeTag type={step.type} label={typeLabel[step.type]} />
                        {step.description?.trim() && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span className="truncate">{step.description}</span>
                          </>
                        )}
                      </span>
                    </span>
                    <Icon
                      name="chevronDown"
                      size={16}
                      className={`shrink-0 text-text-muted transition-transform duration-150 motion-reduce:transition-none ${isOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                </div>

                <div
                  id={`${base}-body`}
                  className={`${isOpen ? "flex" : "hidden"} flex-col gap-3 border-t border-border px-3 pb-2 pt-3`}
                >
                  <div className="flex flex-col gap-1">
                    <label htmlFor={`${base}-name`} className={fieldLabel}>
                      {t.wsFormName}
                    </label>
                    <input
                      id={`${base}-name`}
                      type="text"
                      className="input-field"
                      value={step.name}
                      aria-invalid={!named || undefined}
                      onChange={(e) => patchStep(index, { name: e.target.value })}
                      data-testid={`blueprint-step-${index}-name`}
                    />
                  </div>

                  <div className="flex flex-col gap-1">
                    <label htmlFor={`${base}-description`} className={fieldLabel}>
                      {t.wsFormStepDescription}
                    </label>
                    <textarea
                      id={`${base}-description`}
                      className="input-field min-h-[48px] resize-y"
                      value={step.description ?? ""}
                      onChange={(e) => patchStep(index, { description: e.target.value })}
                      data-testid={`blueprint-step-${index}-description`}
                    />
                  </div>

                  <div
                    className="flex flex-col gap-1.5"
                    role="radiogroup"
                    aria-labelledby={`${base}-type`}
                    title={t.wsFormTypeHint}
                  >
                    <span id={`${base}-type`} className={fieldLabel}>
                      {t.wsFormStepType}
                    </span>
                    <div
                      className="inline-flex flex-wrap gap-0.5 self-start rounded-lg border border-border bg-surface-muted p-0.5"
                      data-testid={`blueprint-step-${index}-type`}
                      data-value={step.type}
                    >
                      {STEP_TYPES.map((type) => (
                        <label
                          key={type}
                          className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors duration-150 has-[:focus-visible]:shadow-[0_0_0_3px_rgb(2_119_192/0.30)] ${
                            step.type === type
                              ? "bg-surface text-text-strong shadow-xs"
                              : "text-text-muted hover:text-text"
                          }`}
                        >
                          <input
                            type="radio"
                            className="sr-only"
                            name={`${base}-type`}
                            value={type}
                            checked={step.type === type}
                            onChange={() => patchStep(index, { type })}
                            data-testid={`blueprint-step-${index}-type-${type}`}
                          />
                          <Icon name={STEP_TYPE_ICON[type]} size={14} className={STEP_TYPE_TEXT[type]} />
                          {typeLabel[type]}
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* The component's code name and its key and value pairs: for whoever needs them, closed for the rest. */}
                  <details className="group">
                    <summary className={disclosure} data-testid={`blueprint-step-${index}-tech`}>
                      <Icon name="chevronRight" size={13} className={disclosureMark} />
                      {t.formTechDetails}
                    </summary>
                    <div className="mt-2 flex flex-col gap-3 pl-[18px]">
                      <div className="flex flex-col gap-1">
                        <label htmlFor={`${base}-component`} className={fieldLabel} title={t.wsFormComponentHint}>
                          {t.wsFormStepComponent}
                        </label>
                        <input
                          id={`${base}-component`}
                          type="text"
                          className="input-field"
                          value={step.component ?? ""}
                          placeholder={t.wsFormStepComponentNone}
                          title={t.wsFormComponentHint}
                          onChange={(e) => patchStep(index, { component: e.target.value })}
                          data-testid={`blueprint-step-${index}-component`}
                        />
                      </div>

                      <div className="flex flex-col gap-1.5" role="group" aria-label={t.wsFormStepSettings}>
                        {settings.length > 0 && (
                          <ul className="flex flex-col gap-2 @md:gap-1.5">
                            {settings.map(([key, value], settingIndex) => (
                              // The row is its place in the list: a rename keeps the row and the
                              // focus, and every field shows the draft, so a row that moves up
                              // after a removal shows its own setting. Narrow, the value goes
                              // under its key; the fields keep their order for the Tab key.
                              <li
                                key={settingIndex}
                                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-1.5 @md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto]"
                              >
                                <SettingKeyInput
                                  className="input-field min-w-0 font-mono text-xs"
                                  settingKey={key}
                                  canRenameTo={(next) =>
                                    renameSetting(step.settings ?? {}, key, next) !== step.settings
                                  }
                                  onRename={(next) => renameSettingKey(index, key, next)}
                                  placeholder={t.wsFormSettingKeyPlaceholder}
                                  aria-label={`${t.wsFormStepSettings} — key ${settingIndex + 1}`}
                                  data-testid={`blueprint-step-${index}-setting-${settingIndex}-key`}
                                />
                                <input
                                  type="text"
                                  className="input-field order-3 col-span-2 min-w-0 text-xs @md:order-none @md:col-span-1"
                                  value={value}
                                  placeholder={t.wsFormSettingValuePlaceholder}
                                  aria-label={`${t.wsFormStepSettings} — value for ${key}`}
                                  onChange={(e) => patchSettingValue(index, key, e.target.value)}
                                  data-testid={`blueprint-step-${index}-setting-${settingIndex}-value`}
                                />
                                <button
                                  type="button"
                                  className="icon-btn hover:text-danger-text"
                                  onClick={() => removeSetting(index, key)}
                                  aria-label={`${t.wsFormSettingRemove} — ${key}`}
                                  title={t.wsFormSettingRemove}
                                  data-testid={`blueprint-step-${index}-setting-${settingIndex}-remove`}
                                >
                                  <Icon name="x" size={14} />
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                        <button
                          type="button"
                          className="btn-ghost self-start px-2 py-1 text-xs"
                          onClick={() => addSetting(index)}
                          data-testid={`blueprint-step-${index}-setting-add`}
                        >
                          <Icon name="plus" size={14} />
                          {t.wsFormSettingAdd}
                        </button>
                      </div>
                    </div>
                  </details>

                  {/* What can be done with the step itself, where the step is. */}
                  <div className="-mx-1.5 flex flex-wrap items-center gap-x-1 gap-y-1 border-t border-border pt-2">
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => moveStep(index, -1, "up")}
                      disabled={index === 0}
                      aria-label={`${t.formMoveStepUp} — ${stepLabel}`}
                      title={t.formMoveStepUp}
                      data-testid={`blueprint-step-${index}-up`}
                    >
                      <Icon name="arrowUp" size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => moveStep(index, 1, "down")}
                      disabled={index === draft.steps.length - 1}
                      aria-label={`${t.formMoveStepDown} — ${stepLabel}`}
                      title={t.formMoveStepDown}
                      data-testid={`blueprint-step-${index}-down`}
                    >
                      <Icon name="arrowDown" size={16} />
                    </button>
                    <button
                      type="button"
                      className="btn-ghost px-2 py-1 text-xs"
                      onClick={() => addStep(index + 1)}
                      data-testid={`blueprint-step-${index}-add-after`}
                    >
                      <Icon name="plus" size={14} />
                      {t.flowAddStepAfter}
                    </button>
                    {/* The wizard knows a step once it is saved. */}
                    {saved.stepIds.has(step.id) && (
                      <AskStepButton step={step} index={index} t={t} withLabel testId={`blueprint-step-${index}-ask`} />
                    )}
                    <button
                      type="button"
                      className="btn-ghost ml-auto px-2 py-1 text-xs hover:text-danger-text"
                      onClick={() => removeStep(index)}
                      aria-label={`${t.wsFormRemoveStep} — ${stepLabel}`}
                      data-testid={`blueprint-step-${index}-remove`}
                    >
                      <Icon name="trash2" size={14} />
                      {t.wsFormRemoveStep}
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

        <button
          type="button"
          className="btn-ghost self-start px-3 py-1.5 text-xs"
          onClick={() => addStep()}
          data-testid="blueprint-step-add"
        >
          <Icon name="plus" size={14} />
          {t.wsFormAddStep}
        </button>
      </section>

      <details className="group">
        <summary className={disclosure} data-testid="blueprint-json-toggle">
          <Icon name="chevronRight" size={13} className={disclosureMark} />
          {t.wsFormDevJson}
        </summary>
        <textarea
          className="input-field mt-2 min-h-[280px] w-full resize-y font-mono text-xs leading-5"
          value={jsonText}
          onFocus={() => {
            jsonFocused.current = true;
          }}
          onBlur={() => {
            jsonFocused.current = false;
            if (!parseError) setJsonText(JSON.stringify(draft, null, 2));
          }}
          onChange={(e) => onJsonChange(e.target.value)}
          spellCheck={false}
          aria-label={t.wsFormDevJson}
          aria-invalid={parseError || undefined}
          data-testid="blueprint-json-editor"
        />
      </details>

      {/* Over the form's last lines, wherever the tab has been scrolled to; it takes no room of its own. */}
      {removed && (
        <div className="pointer-events-none sticky bottom-3 z-10 flex h-0 items-end justify-center">
          <div
            className="pop-in pointer-events-auto flex items-center gap-3 rounded-lg bg-text-strong px-3.5 py-2 text-sm text-surface shadow-lg"
            role="status"
            data-testid="blueprint-step-removed"
          >
            {t.formStepDeleted}
            <button
              type="button"
              className="rounded font-semibold underline underline-offset-2 hover:no-underline"
              onClick={undoRemove}
              data-testid="blueprint-step-undo"
            >
              {t.formUndo}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
