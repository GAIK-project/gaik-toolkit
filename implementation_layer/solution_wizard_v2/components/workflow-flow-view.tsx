"use client";

import {
  createContext,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  BaseEdge,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { BpmnZoomControls } from "@/components/bpmn-viewer-toolbar";
import { FlowEditingNote, FlowLockedNote, FlowUpdatedLine } from "@/components/flow-status";
import { Icon, type IconName } from "@/components/icons";
import { STEP_TYPE_ICON, STEP_TYPE_TEXT, StepNumber, StepTypeTag, stepTypeLabels } from "@/components/step-type";
import { saveRefusal } from "@/lib/blueprint-ops";
import {
  blueprintBaseTag,
  blueprintPayload,
  blueprintPayloadKey,
  restoreStep,
} from "@/lib/blueprint-draft";
import type { BlueprintUpdate } from "@/lib/blueprint-update";
import { hasBpmnDraft, subscribeBpmnDrafts } from "@/lib/bpmn-session-drafts";
import { askInChat } from "@/lib/chat-events";
import { fillTemplate } from "@/lib/chat-template";
import type { Dict } from "@/lib/i18n";
import type { Blueprint, BlueprintStep, BlueprintStepType } from "@/lib/mock-sessions";
import { stepChatReference } from "@/lib/step-reference";
import {
  buildFlow,
  chooseColumns,
  fitViewport,
  insertStepAfter,
  layoutFlow,
  newStepId,
  placeMenu,
  processFromBpmn,
  removeStep,
  renameStep,
  roundedPath,
  type BpmnModel,
  type FlowOutcome,
  type FlowOutcomes,
  type FlowProcess,
  type FlowStep,
  type Point,
  type Size,
  type Viewport,
} from "@/lib/workflow-flow";

const MIN_ZOOM = 0.3;
const MAX_ZOOM = 2;
/** From this canvas width down (a phone) a long flow scrolls rather than shrinks. */
const NARROW_CANVAS = 480;
const MENU_WIDTH = 328;
const ARROW_ID = "simple-flow-arrow";

/** React Flow marks every node "node" for screen readers; the node is a button with its own name. */
const NO_ROLE_DESCRIPTION = { "aria-roledescription": undefined };
const HIDDEN_FROM_READERS = { "aria-hidden": true, "aria-roledescription": undefined };

type StepNodeType = Node<{ step: FlowStep; outcomesId: string | null }, "step">;
type OutcomesNodeType = Node<{ outcomes: FlowOutcomes; next: number | null; domId: string }, "outcomes">;
type FlowEdgeType = Edge<{ points: Point[]; label: Point | null }, "flow">;

/** What the nodes need from the view around them. */
type Ui = {
  t: Dict;
  typeLabel: Record<BlueprintStepType, string>;
  selectedId: string | null;
  /** `byKeyboard`: the focus then goes into the step's menu. */
  onSelect: (stepId: string, byKeyboard: boolean) => void;
};
const UiContext = createContext<Ui | null>(null);

function useUi(): Ui {
  const ui = useContext(UiContext);
  if (!ui) throw new Error("flow node outside its view");
  return ui;
}

/** One step: its number in the type's colour, its name, and who or what does it. */
function StepNode({ data }: NodeProps<StepNodeType>) {
  const { t, typeLabel, selectedId, onSelect } = useUi();
  const { step, outcomesId } = data;
  const selected = selectedId === step.id;
  const name = step.name.trim() || step.id;
  const type = typeLabel[step.type];
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <button
        type="button"
        // React Flow takes the pointer from a node it can neither select nor drag; the button takes it back.
        className={`pointer-events-auto flex h-full w-full items-center gap-2.5 rounded-xl border px-3 text-left shadow-xs transition-[border-color,background-color] duration-150 ${
          selected ? "border-brand bg-brand-soft" : "border-border-strong bg-surface hover:border-brand/70"
        }`}
        aria-pressed={selected}
        aria-describedby={outcomesId ?? undefined}
        onClick={(e) => onSelect(step.id, e.detail === 0)}
        data-testid={`simple-flow-node-${step.index}`}
        data-step-id={step.id}
      >
        <StepNumber n={step.index + 1} type={step.type} />
        <span className="min-w-0 flex-1">
          {/* Read out as "Vaihe 2: Data extraction GenAI, Tekoäly": the words on screen, in their
              order, with the number and the type the eye gets from the badge and the icon. */}
          <span className="line-clamp-2 break-words text-[13px] font-semibold leading-[1.25] text-text-strong">
            <span className="sr-only">{fillTemplate(t.bpmnStepTitle, { n: String(step.index + 1) })}: </span>
            {name}
          </span>
          <span className="mt-0.5 flex min-w-0 items-center gap-1 text-[11px] leading-4 text-text-muted">
            <Icon name={STEP_TYPE_ICON[step.type]} size={13} className={STEP_TYPE_TEXT[step.type]} />
            <span className="truncate">{step.actor ?? type}</span>
            {step.actor && <span className="sr-only">, {type}</span>}
          </span>
        </span>
      </button>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </>
  );
}

function outcomeLine(line: FlowOutcome, t: Dict): { icon: IconName; tone: string; text: string } {
  if (line.outcome === "approved") return { icon: "check", tone: "text-success-text", text: t.flowOutcomeDone };
  if (line.returnsTo === null) return { icon: "x", tone: "text-danger-text", text: t.flowOutcomeEnds };
  return {
    icon: "rotateCcw",
    tone: "text-warning-text",
    text: fillTemplate(t.flowOutcomeReturns, { n: String(line.returnsTo + 1) }),
  };
}

/** What a review leads to besides the next step: the box under it. */
function OutcomesNode({ data }: NodeProps<OutcomesNodeType>) {
  const { t } = useUi();
  const { outcomes, next, domId } = data;
  return (
    <>
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <ul
        id={domId}
        className="flex h-full w-full flex-col justify-center rounded-lg border border-dashed border-border-strong bg-surface-muted/70 px-2 text-[11px] leading-5 text-text-secondary"
        data-testid="simple-flow-outcomes"
      >
        {/* The arrow says this to the eye; a screen reader hears it with the review. */}
        {next !== null && (
          <li className="sr-only">{fillTemplate(t.flowOutcomeNext, { n: String(next + 1) })}</li>
        )}
        {outcomes.lines.map((line) => {
          const { icon, tone, text } = outcomeLine(line, t);
          return (
            <li key={line.outcome} className="flex min-w-0 items-center gap-1.5">
              <Icon name={icon} size={12} className={tone} />
              <span className="truncate">{text}</span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** An arrow along the line the layout gave it, with the review's "approves" on it. */
function FlowEdge({ id, data }: EdgeProps<FlowEdgeType>) {
  const { t } = useUi();
  if (!data) return null;
  return (
    <>
      <BaseEdge id={id} path={roundedPath(data.points)} markerEnd={`url(#${ARROW_ID})`} interactionWidth={0} />
      {data.label && (
        <EdgeLabelRenderer>
          <span
            className="absolute rounded-full border border-border bg-surface px-1.5 text-[11px] font-medium leading-4 text-text-secondary"
            style={{ transform: `translate(-50%, -50%) translate(${data.label.x}px, ${data.label.y}px)` }}
            aria-hidden="true"
          >
            {t.flowOutcomeApproved}
          </span>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const NODE_TYPES = { step: StepNode, outcomes: OutcomesNode };
const EDGE_TYPES = { flow: FlowEdge };

type Status =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  // `message`: the server's own words for a save it refused; without it the generic line.
  | { kind: "error"; retry: () => void; message?: string }
  | { kind: "removed"; step: BlueprintStep; index: number }
  | { kind: "changed" };

function MenuButton({
  icon,
  tone = "text-text-secondary hover:bg-surface-muted hover:text-text",
  onClick,
  testId,
  buttonRef,
  children,
}: {
  icon: IconName;
  tone?: string;
  onClick: () => void;
  testId: string;
  buttonRef?: React.Ref<HTMLButtonElement>;
  children: ReactNode;
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] font-medium transition-colors duration-150 ${tone}`}
      onClick={onClick}
      data-testid={testId}
    >
      <Icon name={icon} size={15} />
      {children}
    </button>
  );
}

/**
 * A step's name in its menu. It is saved when Enter is pressed or the field is
 * left; an empty name is not taken, and the saved one comes back.
 */
function NameField({
  name,
  label,
  inputRef,
  onCommit,
}: {
  name: string;
  label: string;
  inputRef: React.Ref<HTMLInputElement>;
  onCommit: (name: string) => void;
}) {
  const [draft, setDraft] = useState(name);
  // The saved name, also one the wizard gave meanwhile, replaces what the field shows.
  useEffect(() => setDraft(name), [name]);
  function commit() {
    const next = draft.trim();
    if (!next) setDraft(name);
    else if (next !== name.trim()) onCommit(next);
  }
  return (
    <input
      ref={inputRef}
      type="text"
      className="input-field min-w-0 flex-1 px-2.5 py-1.5 text-sm"
      aria-label={label}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        } else if (e.key === "Escape" && draft !== name) {
          // The first Escape gives up the typing; the next closes the menu.
          e.stopPropagation();
          setDraft(name);
        }
      }}
      data-testid="simple-flow-name"
    />
  );
}

/**
 * The Workflow tab's simple flow: one node a step, arrows in order, a review's
 * outcomes under it. Drawn from the blueprint; the BPMN is only read, for who
 * does each step. A click on a step opens its menu: rename it, add a step or
 * a review after it, remove it, or ask the wizard to change it. Each edit is
 * saved to the blueprint at once, the way the Blueprint form saves. A version
 * written elsewhere (the wizard's, from the chat) is drawn as it arrives, and
 * the status line says so.
 */
export function WorkflowFlowView({
  sessionId,
  blueprint,
  baseVersion = null,
  bpmnXml,
  locked,
  onUnlock,
  onLock,
  update = null,
  pocNoteLabel = null,
  selectedStepId,
  onSelectedStepChange,
  onSaved,
  fullView,
  t,
}: {
  sessionId: string;
  blueprint: Blueprint;
  /** The session's active version as the page read it: an edit is made on it. */
  baseVersion?: number | null;
  /** The diagram at the size of the window, and the control that takes it there and back. */
  fullView?: { on: boolean; toggle: () => void };
  /** The diagram the server generated from the blueprint; null until it has loaded, or when it cannot be. */
  bpmnXml: string | null;
  /** Edits are off, and the canvas says why; "ask the wizard" stays. */
  locked: boolean;
  onUnlock: () => void;
  /** Closes the flow for edits again after "Muokkaa kaaviota"; only where it was locked. */
  onLock?: () => void;
  /** The blueprint is one the page brought, not a save made here: from the chat, or from elsewhere. */
  update?: BlueprintUpdate | null;
  /** Shown while saved changes are not in the PoC package yet. */
  /** Said after a save while the PoC package lacks it, with the control that generates the package again. */
  pocNoteLabel?: ReactNode;
  selectedStepId: string | null;
  onSelectedStepChange: (stepId: string | null) => void;
  /** After a save: the blueprint as the server has it now. */
  onSaved: (blueprint: Blueprint, via: "save" | "undo", version?: number) => void;
  t: Dict;
}) {
  const router = useRouter();
  const uid = useId();
  const typeLabel = useMemo(() => stepTypeLabels(t), [t]);
  const paneRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [process, setProcess] = useState<FlowProcess | null>(null);
  // The view the user chose by panning or zooming; null shows the whole flow.
  const [chosenView, setChosenView] = useState<Viewport | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  const steps = blueprint.steps;
  const selectedIndex = steps.findIndex((s) => s.id === selectedStepId);
  const selected = selectedIndex >= 0 ? steps[selectedIndex] : null;

  // The newest blueprint known here: the page's, or the answer to a save that
  // the page has not drawn yet. Every edit is made on it.
  const latest = useRef(blueprint);
  const shown = useRef(blueprint);
  if (shown.current !== blueprint) {
    shown.current = blueprint;
    latest.current = blueprint;
  }
  // Its version, the same way: the page's, or the one the last save wrote.
  const latestVersion = useRef(baseVersion);
  useEffect(() => {
    latestVersion.current = baseVersion;
  }, [baseVersion]);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  // A version the page brought is what the flow shows now: "Tallennettu" and
  // "Vaihe poistettu" were about the one before it. A save on its way, a
  // failed one and a refused one still have something to say.
  const [seenUpdate, setSeenUpdate] = useState(update);
  if (seenUpdate !== update) {
    setSeenUpdate(update);
    if (update && (status.kind === "saved" || status.kind === "removed")) setStatus({ kind: "idle" });
  }
  const selectRef = useRef(onSelectedStepChange);
  selectRef.current = onSelectedStepChange;

  useLayoutEffect(() => {
    const el = paneRef.current;
    if (!el) return;
    const measure = () =>
      setSize((prev) =>
        prev && prev.width === el.clientWidth && prev.height === el.clientHeight
          ? prev
          : { width: el.clientWidth, height: el.clientHeight },
      );
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Who does each step: read from the diagram. While a new one loads, the last one stands.
  useEffect(() => {
    if (!bpmnXml) return;
    let cancelled = false;
    import("bpmn-moddle")
      .then(({ BpmnModdle }) => new BpmnModdle().fromXML(bpmnXml))
      .then(({ rootElement }) => {
        if (!cancelled) setProcess(processFromBpmn(rootElement as BpmnModel));
      })
      .catch(() => {
        if (!cancelled) setProcess(null);
      });
    return () => {
      cancelled = true;
    };
  }, [bpmnXml]);

  const model = useMemo(() => buildFlow(steps, process), [steps, process]);
  const narrow = size !== null && size.width < NARROW_CANVAS;
  // What the zoom controls and React Flow's own mark cover.
  const inset = useMemo(() => ({ top: 56, right: 14, bottom: 22, left: 14 }), []);
  const minZoom = narrow ? 0.85 : 0.5;
  const columns = useMemo(
    () =>
      size
        ? chooseColumns(
            model,
            { width: size.width - inset.left - inset.right, height: size.height - inset.top - inset.bottom },
            minZoom,
          )
        : 1,
    [model, size, inset, minZoom],
  );
  const layout = useMemo(() => layoutFlow(model, columns), [model, columns]);
  const fitted = useMemo(
    () => (size ? fitViewport(layout.bounds, size, inset, { minZoom }) : { x: 0, y: 0, zoom: 1 }),
    [layout, size, inset, minZoom],
  );
  const viewport = chosenView ?? fitted;

  // A step added or removed: the whole flow is shown again, so the change is in view.
  // So it is when the diagram moves to the window's size or back.
  const stepIds = steps.map((s) => s.id).join("\n");
  const fullViewOn = fullView?.on ?? false;
  useEffect(() => setChosenView(null), [stepIds, fullViewOn]);

  const nodes = useMemo(
    () =>
      model.nodes.map((node): StepNodeType | OutcomesNodeType => {
        const box = layout.boxes.get(node.id) ?? { x: 0, y: 0, width: 0, height: 0 };
        const place = {
          id: node.id,
          position: { x: box.x, y: box.y },
          width: box.width,
          height: box.height,
          domAttributes: NO_ROLE_DESCRIPTION,
        };
        const domId = (stepId: string) => `${uid}-outcomes-${steps.findIndex((s) => s.id === stepId)}`;
        if (node.kind === "step") {
          const outcomes = model.nodes.some((n) => n.kind === "outcomes" && n.of === node.id);
          return { ...place, type: "step", data: { step: node, outcomesId: outcomes ? domId(node.id) : null } };
        }
        const of = steps.findIndex((s) => s.id === node.of);
        return {
          ...place,
          type: "outcomes",
          data: { outcomes: node, next: of >= 0 && of < steps.length - 1 ? of + 1 : null, domId: domId(node.of) },
        };
      }),
    [model, layout, steps, uid],
  );
  const edges = useMemo(
    () =>
      model.edges.flatMap((edge): FlowEdgeType[] => {
        const line = layout.edges.get(edge.id);
        if (!line) return [];
        return [
          {
            id: edge.id,
            source: edge.from,
            target: edge.to,
            type: "flow",
            data: line,
            // The arrows are for the eye: the order is the nodes' own, and a
            // review's outcomes are read out with the review.
            domAttributes: HIDDEN_FROM_READERS,
          },
        ];
      }),
    [model, layout],
  );

  // -- saving --------------------------------------------------------------------

  const queue = useRef<Promise<void>>(Promise.resolve());
  /**
   * Saves `edit` applied to the newest blueprint, after any save already on
   * its way. The save names the blueprint the edit was made on, and is
   * refused when the server holds a newer one (the agent wrote a version).
   */
  function save(
    edit: (current: Blueprint) => Blueprint,
    { via = "save", then }: { via?: "save" | "undo"; then?: () => void } = {},
  ) {
    const run = async () => {
      const base = latest.current;
      const baseVersion = latestVersion.current;
      const next = edit(base);
      if (blueprintPayloadKey(next) === blueprintPayloadKey(base)) return;
      setStatus({ kind: "saving" });
      try {
        const res = await fetch(`/api/sessions/${sessionId}/blueprint`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            content: blueprintPayload(next),
            note: t.flowSaveNote,
            base: blueprintBaseTag(base),
            ...(typeof baseVersion === "number" ? { base_version: baseVersion } : {}),
          }),
        });
        if (res.status === 409 || res.status === 422) {
          const refused = saveRefusal(res.status, await res.json().catch(() => null));
          if (refused?.kind === "changed") {
            // The page reads the newer version, and the flow is drawn from it.
            setStatus({ kind: "changed" });
            router.refresh();
            return;
          }
          if (refused?.kind === "refused") {
            setStatus({ kind: "error", retry: () => save(edit, { via, then }), message: refused.message });
            return;
          }
        }
        if (!res.ok) throw new Error("save failed");
        const data = (await res.json()) as { blueprint?: Blueprint; version?: number };
        if (!data.blueprint) throw new Error("save failed");
        latest.current = data.blueprint;
        if (typeof data.version === "number") latestVersion.current = data.version;
        setStatus({ kind: "saved" });
        onSavedRef.current(data.blueprint, via, data.version);
        then?.();
      } catch {
        setStatus({ kind: "error", retry: () => save(edit, { via, then }) });
      }
    };
    // A save that throws is told on the canvas; the next one still gets its turn.
    queue.current = queue.current.then(run).catch(() => {});
  }

  // A kept BPMN draft is still an unsaved edit of the same blueprint: "Lopeta
  // muokkaus" waits for it instead of locking only for the BPMN tab to unlock
  // again when opened (#234).
  const bpmnDraftPending = useSyncExternalStore(
    subscribeBpmnDrafts,
    () => hasBpmnDraft(sessionId),
    () => false,
  );

  // -- a step's menu ---------------------------------------------------------------

  const menuRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const askRef = useRef<HTMLButtonElement>(null);
  const undoRef = useRef<HTMLButtonElement>(null);
  const [menuHeight, setMenuHeight] = useState(0);
  // What takes the focus once the menu of the step just picked is drawn.
  const focusNext = useRef<"menu" | "name" | "undo" | null>(null);
  const selectedId = selected?.id ?? null;

  useLayoutEffect(() => {
    setMenuHeight(menuRef.current?.offsetHeight ?? 0);
  }, [selectedId, locked, size]);

  const box = selected ? layout.boxes.get(selected.id) : undefined;
  const anchor = box && {
    x: box.x * viewport.zoom + viewport.x,
    y: box.y * viewport.zoom + viewport.y,
    width: box.width * viewport.zoom,
    height: box.height * viewport.zoom,
  };
  const menuWidth = size ? Math.min(MENU_WIDTH, size.width - 16) : MENU_WIDTH;
  const menuAt =
    anchor && size
      ? placeMenu(anchor, { width: menuWidth, height: menuHeight || (locked ? 110 : 210) }, size)
      : null;

  // On a small canvas the menu can have room neither under nor over its step:
  // the view then moves the step to the top once, and the menu opens under it.
  const movedFor = useRef<string | null>(null);
  const covers = menuAt?.covers ?? false;
  const anchorTop = anchor ? anchor.y : null;
  useLayoutEffect(() => {
    if (!selectedId) movedFor.current = null;
    if (!selectedId || !covers || anchorTop === null || menuHeight === 0 || movedFor.current === selectedId) return;
    movedFor.current = selectedId;
    setChosenView({ ...viewport, y: viewport.y + inset.top - anchorTop });
  }, [selectedId, covers, anchorTop, menuHeight, viewport, inset.top]);

  useEffect(() => {
    const target = focusNext.current;
    if (!target) return;
    if (target === "undo") {
      if (!undoRef.current) return;
      undoRef.current.focus();
    } else {
      if (!selectedId || !menuRef.current) return;
      const field = locked ? null : nameRef.current;
      (field ?? askRef.current)?.focus();
      if (target === "name") field?.select();
    }
    focusNext.current = null;
  });

  function focusNode(stepId: string) {
    paneRef.current?.querySelector<HTMLElement>(`[data-step-id="${CSS.escape(stepId)}"]`)?.focus();
  }

  function closeMenu({ refocus = false }: { refocus?: boolean } = {}) {
    const id = selectedId;
    selectRef.current(null);
    if (refocus && id) focusNode(id);
  }

  function rename(stepId: string, name: string) {
    save((current) => renameStep(current, stepId, name));
  }

  function addAfter(type: BlueprintStepType) {
    if (!selected && steps.length > 0) return;
    const step: BlueprintStep = {
      id: newStepId(latest.current.steps),
      name: type === "human_review" ? t.wsStepHuman : t.flowNewStepName,
      type,
    };
    const after = selected?.id ?? null;
    save((current) => insertStepAfter(current, after, step), {
      then: () => {
        // The new step is picked, its name ready to be typed over.
        focusNext.current = "name";
        selectRef.current(step.id);
      },
    });
  }

  function remove() {
    if (!selected) return;
    const step = selected;
    const index = selectedIndex;
    selectRef.current(null);
    save((current) => removeStep(current, step.id), {
      then: () => {
        focusNext.current = "undo";
        setStatus({ kind: "removed", step, index });
      },
    });
  }

  function undoRemove(step: BlueprintStep, index: number) {
    save((current) => ({ ...current, steps: restoreStep(current.steps, step, index) }), { via: "undo" });
  }

  const ui = useMemo<Ui>(
    () => ({
      t,
      typeLabel,
      selectedId,
      onSelect: (stepId, byKeyboard) => {
        if (stepId === selectedId) {
          selectRef.current(null);
          return;
        }
        if (byKeyboard) focusNext.current = "menu";
        selectRef.current(stepId);
      },
    }),
    [t, typeLabel, selectedId],
  );

  function zoomBy(factor: number) {
    if (!size) return;
    const zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, viewport.zoom * factor));
    const centre = { x: size.width / 2, y: size.height / 2 };
    const scale = zoom / viewport.zoom;
    setChosenView({
      zoom,
      x: centre.x - (centre.x - viewport.x) * scale,
      y: centre.y - (centre.y - viewport.y) * scale,
    });
  }

  const selectedActor = selected
    ? model.nodes.find((n): n is FlowStep => n.kind === "step" && n.id === selected.id)?.actor
    : null;

  // The one line that says where a save stands; nothing when there is nothing to say.
  let statusLine: ReactNode = null;
  if (status.kind === "saving") {
    statusLine = (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Icon name="loaderCircle" size={14} className="motion-safe:animate-spin" />
        {t.wsBpmnSaving}
      </span>
    );
  } else if (status.kind === "saved") {
    statusLine = (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Icon name="check" size={14} className="text-success-text" />
        {t.wsBpmnSaved}
      </span>
    );
  } else if (status.kind === "error") {
    statusLine = (
      <span className="inline-flex items-center gap-2 text-danger-text">
        {status.message ?? t.wsBpmnSaveError}
        <button type="button" className="font-medium underline underline-offset-2" onClick={status.retry}>
          {t.editorRetry}
        </button>
      </span>
    );
  } else if (status.kind === "removed") {
    const { step, index } = status;
    statusLine = (
      <span className="inline-flex items-center gap-2 text-text-secondary">
        {t.formStepDeleted}
        <button
          ref={undoRef}
          type="button"
          className="rounded font-semibold underline underline-offset-2 hover:no-underline"
          onClick={() => undoRemove(step, index)}
          data-testid="simple-flow-undo"
        >
          {t.formUndo}
        </button>
      </span>
    );
  } else if (status.kind === "changed") {
    statusLine = <span className="text-warning-text">{t.flowChangedElsewhere}</span>;
  } else if (update) {
    statusLine = <FlowUpdatedLine update={update} testId="simple-flow-updated" t={t} />;
  }

  return (
    <section
      className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-border bg-surface"
      aria-label={t.wsTabFlow}
      onKeyDown={(e) => {
        if (e.key === "Escape" && selected) {
          e.stopPropagation();
          closeMenu({ refocus: true });
        }
      }}
      data-testid="simple-flow"
      data-columns={columns}
    >
      <div ref={paneRef} className="simple-flow @container relative min-h-0 flex-1">
        {/* The arrowhead every arrow ends in. */}
        <svg className="pointer-events-none absolute h-0 w-0" aria-hidden="true" focusable="false">
          <defs>
            <marker
              id={ARROW_ID}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="9"
              markerHeight="9"
              markerUnits="userSpaceOnUse"
              orient="auto"
            >
              <path d="M 0 1 L 9.5 5 L 0 9 z" className="fill-text-muted" />
            </marker>
          </defs>
        </svg>

        {size && size.width > 0 && size.height > 0 && steps.length > 0 && (
          <UiContext.Provider value={ui}>
            <ReactFlow
              className="absolute inset-0"
              aria-label={t.flowCanvasLabel}
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              edgeTypes={EDGE_TYPES}
              viewport={viewport}
              onViewportChange={setChosenView}
              onPaneClick={() => closeMenu()}
              minZoom={MIN_ZOOM}
              maxZoom={MAX_ZOOM}
              // The wheel moves the view and Ctrl + wheel zooms, as on the BPMN canvas.
              panOnScroll
              zoomOnScroll={false}
              zoomOnDoubleClick={false}
              // The flow is read and clicked, not drawn: no dragging, connecting or selecting by React Flow.
              nodesDraggable={false}
              nodesConnectable={false}
              nodesFocusable={false}
              edgesFocusable={false}
              elementsSelectable={false}
              disableKeyboardA11y
              deleteKeyCode={null}
              selectionKeyCode={null}
              multiSelectionKeyCode={null}
              panActivationKeyCode={null}
            />
          </UiContext.Provider>
        )}

        {steps.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
            <p className="text-sm text-text-muted">{t.wsFormEmptySteps}</p>
            {!locked && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => addAfter("io")}
                data-testid="simple-flow-add-first"
              >
                <Icon name="plus" size={16} />
                {t.wsFormAddStep}
              </button>
            )}
          </div>
        )}

        <BpmnZoomControls
          className="absolute right-3 top-3 z-10"
          zoom={size ? viewport.zoom : null}
          onZoomIn={() => zoomBy(1.25)}
          onZoomOut={() => zoomBy(1 / 1.25)}
          onFit={() => setChosenView(null)}
          zoomInLabel={t.wsBpmnZoomIn}
          zoomOutLabel={t.wsBpmnZoomOut}
          fitLabel={t.bpmnFitView}
          groupLabel={t.wsBpmnToolbar}
          expanded={fullViewOn}
          onToggleExpanded={fullView?.toggle}
          expandLabel={t.flowFullView}
          collapseLabel={t.flowFullViewExit}
          testId="simple-flow-zoom"
        />

        {selected && menuAt && (
          <div
            ref={menuRef}
            role="group"
            aria-label={fillTemplate(t.bpmnStepTitle, { n: String(selectedIndex + 1) })}
            className="pop-in absolute z-20 rounded-lg border border-border bg-surface p-2.5 shadow-md"
            style={{ left: menuAt.x, top: menuAt.y, width: menuWidth }}
            data-testid="simple-flow-menu"
          >
            <div className="flex items-center gap-2">
              <StepNumber n={selectedIndex + 1} type={selected.type} />
              {locked ? (
                <p
                  className="min-w-0 flex-1 break-words text-sm font-semibold text-text-strong"
                  data-testid="simple-flow-name-text"
                >
                  {selected.name}
                </p>
              ) : (
                <NameField
                  // A field of its own for each step: it opens with that step's name.
                  key={selected.id}
                  name={selected.name}
                  label={t.wsBpmnPropertiesName}
                  inputRef={nameRef}
                  onCommit={(name) => rename(selected.id, name)}
                />
              )}
              <button
                type="button"
                className="icon-btn h-7 w-7"
                onClick={() => closeMenu({ refocus: true })}
                aria-label={t.wsBpmnPropertiesClose}
                title={t.wsBpmnPropertiesClose}
              >
                <Icon name="x" size={14} />
              </button>
            </div>
            <p className="mt-1.5 flex min-w-0 items-center gap-1.5 pl-8 text-xs text-text-muted">
              <StepTypeTag type={selected.type} label={typeLabel[selected.type]} />
              {selectedActor && (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="truncate">{selectedActor}</span>
                </>
              )}
            </p>
            <div className="mt-2 flex flex-col border-t border-border pt-1.5">
              <MenuButton
                buttonRef={askRef}
                icon="messageSquareText"
                tone="text-brand-text hover:bg-brand-soft"
                onClick={() => {
                  askInChat(stepChatReference(selected, selectedIndex, t));
                  closeMenu();
                }}
                testId="simple-flow-ask"
              >
                {t.flowAskWizard}
              </MenuButton>
              {!locked && (
                <>
                  <MenuButton icon="plus" onClick={() => addAfter("io")} testId="simple-flow-add-step">
                    {t.flowAddStepAfter}
                  </MenuButton>
                  <MenuButton icon="userCheck" onClick={() => addAfter("human_review")} testId="simple-flow-add-review">
                    {t.flowAddReviewAfter}
                  </MenuButton>
                  <MenuButton
                    icon="trash2"
                    tone="text-text-secondary hover:bg-danger-bg hover:text-danger-text"
                    onClick={remove}
                    testId="simple-flow-remove"
                  >
                    {t.wsFormRemoveStep}
                  </MenuButton>
                </>
              )}
            </div>
          </div>
        )}

        {/* Beside the zoom controls, in the band the flow is kept out of; on a
            narrow canvas that band is the controls', and the line goes to the bottom. */}
        {statusLine && (
          <div
            role="status"
            className="pop-in absolute bottom-3 left-3 z-10 max-w-[calc(100%-1.5rem)] rounded-lg border border-border bg-surface/95 px-3 py-2 text-xs shadow-sm backdrop-blur-sm @lg:bottom-auto @lg:top-3 @lg:max-w-[calc(100%-14.5rem)]"
            data-testid="simple-flow-status"
          >
            {statusLine}
          </div>
        )}
      </div>

      {/* A save writes a new blueprint version; the PoC package stays as it was. */}
      {!locked && pocNoteLabel && (
        <p
          className="flex shrink-0 items-start gap-1.5 border-t border-border bg-surface-muted/50 px-3 py-2 text-xs text-text-muted"
          data-testid="simple-flow-poc-note"
        >
          <Icon name="info" size={13} className="mt-0.5" />
          <span>{pocNoteLabel}</span>
        </p>
      )}
      {locked && <FlowLockedNote onUnlock={onUnlock} testId="simple-flow" t={t} />}
      {!locked && onLock && (
        <FlowEditingNote
          help={t.flowEditHelp}
          // "Kumoa" after a removal is an edit too: it goes with the lock.
          onLock={() => {
            if (bpmnDraftPending) return;
            setStatus({ kind: "idle" });
            onLock();
          }}
          lockWaits={status.kind === "saving" || bpmnDraftPending}
          testId="simple-flow"
          t={t}
        />
      )}
    </section>
  );
}
