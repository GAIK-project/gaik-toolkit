"use client";

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  OperationRefused,
  postOperations,
  postUndo,
  type BlueprintOperation,
  type StepType,
} from "@/lib/blueprint-ops";
import { fieldInPlainWords } from "@/lib/blueprint-field-names";
import { BpmnModeler, type BpmnModelerHandle, type BpmnSelectionInfo } from "@/components/bpmn-modeler";
import { BpmnZoomControls } from "@/components/bpmn-viewer-toolbar";
import { FlowEditingNote, FlowLockedNote, FlowUpdatedLine } from "@/components/flow-status";
import { AskStepButton, StepNumber, stepTypeLabels } from "@/components/step-type";
import { BpmnStepPanel } from "@/components/bpmn-step-panel";
import { BpmnBranchDialog, BpmnReworkDialog } from "@/components/bpmn-branch-dialog";
import { Icon } from "@/components/icons";
import { stepIdToBpmnId, stepIndexForBpmnId } from "@/lib/bpmn-edit-state";
import type {
  BpmnDecisionRequest,
  BpmnReworkRequest,
  BpmnEditorOps,
  BpmnLayoutChange,
  BpmnStepLaneChange,
} from "@/lib/bpmn-editor-module";
import {
  decisionOf,
  decisionProblem,
  exceptionOf,
  opForRework,
  reworkProblem,
  reworkTargets,
  laneIdOf,
  opForDecision,
  mappingFitsSteps,
  performedByOf,
  isDecisionStep,
  stepIdOf,
  type BpmnMapping,
  type DecisionValues,
  type ReworkValues,
} from "@/lib/bpmn-canvas-ops";
import {
  keptEditOps,
  keptPanelEdits,
  mergeKeptEdits,
  panelFields,
  panelOps,
  waitsForVersion,
  type KeptPanelEdit,
  type PanelValues,
} from "@/lib/step-panel-model";
import type { BlueprintUpdate } from "@/lib/blueprint-update";
import { bpmnDataObjectsQuery } from "@/lib/bpmn-show-data";
import { fillTemplate } from "@/lib/chat-template";
import type { Dict } from "@/lib/i18n";
import type { Blueprint, BlueprintStep } from "@/lib/mock-sessions";

/** How long dragged shapes wait for more dragging before their places are kept. */
const LAYOUT_SAVE_DELAY_MS = 800;

/** From this canvas width (Tailwind's @lg container, 32rem) the properties panel is a column at the right. */
const PROPS_WIDE = 512;

/** A step's description: the server's diagram draws it (`<bpmn:documentation>`), the page's step may carry it. */
function descriptionOf(step: BlueprintStep, drawn: string | null | undefined): string {
  return drawn || step.description || "";
}

/**
 * Whether edits can be sent: `on` once the server's mapping for the diagram
 * has come, `off` where there is no wizard_api to send them to (the mock
 * store answers 503 needs_wizard_api), `no_draft` while the agent has not
 * written its blueprint yet (wizard_api refuses every operation then),
 * `unknown` until the first answer.
 */
type OpsState = "unknown" | "on" | "off" | "no_draft";

type Status =
  | { kind: "idle" }
  | { kind: "saving" }
  /** `warnings`: what the server said the edit also did (a step's artifacts removed with it), as it said it. */
  | { kind: "saved"; warnings?: string[] }
  | { kind: "undone" }
  | { kind: "error"; message: string; retry?: () => void };

/** Which element stands for what in the server's diagram, and whether the agent's draft is there. */
type ServerMapping = { mapping: BpmnMapping; hasDraft: boolean };

/** The diagram as the server draws it now, and its mapping. */
type ServerDiagram = { xml: string } & ServerMapping;

export function BpmnDiagramPanel({
  sessionId,
  xml,
  baseVersion = null,
  steps,
  pocNoteLabel = null,
  reloading = false,
  locked = false,
  onUnlock,
  onLock,
  update = null,
  focusRequest = null,
  onSelectedStepChange,
  onSynced,
  fullView,
  showData = true,
  onShowDataChange,
  t,
}: {
  sessionId: string;
  /**
   * The diagram is drawn with its data objects; off, a compact one without
   * them. The page fetches `xml` accordingly and keeps the choice.
   */
  showData?: boolean;
  /** "Show data" was switched: the page fetches the diagram again. */
  onShowDataChange?: (show: boolean) => void;
  /** The diagram at the size of the window, and the control that takes it there and back. */
  fullView?: { on: boolean; toggle: () => void };
  /** The diagram as the server generated it from the blueprint. */
  xml: string;
  /** The session's active version as the page read it: an edit is made on it. */
  baseVersion?: number | null;
  /** The blueprint's steps: their numbers, types, the chat reference, and the ids the mapping points at. */
  steps: BlueprintStep[];
  /** Said after an edit while the PoC package lacks it, with the control that generates the package again. */
  pocNoteLabel?: ReactNode;
  /** The blueprint changed elsewhere and `xml` is being generated again. */
  reloading?: boolean;
  /**
   * Edits are off, as on the simple flow after Gate 2: the diagram can be
   * read and a step picked to ask the wizard about, and "Muokkaa" opens it.
   */
  locked?: boolean;
  onUnlock?: () => void;
  /** Closes the diagram for edits again ("Lopeta muokkaus"), where `locked` applies. */
  onLock?: () => void;
  /** The blueprint is one the page brought, not an edit made here: from the chat, or from elsewhere. */
  update?: BlueprintUpdate | null;
  /** Select and centre this step's task (a click on the step list). */
  focusRequest?: { stepId: string; seq: number } | null;
  /** The step whose task is selected on the canvas, for the step list. */
  onSelectedStepChange?: (stepId: string | null) => void;
  /**
   * After an edit or an undo: the blueprint and diagram as the server has
   * them now, and the version it wrote. `via` says which, for the PoC note.
   */
  /** `xml` is the diagram the server drew after the edit; null when it could not be read. */
  onSynced: (result: { blueprint: Blueprint; xml: string | null; version?: number; via?: "save" | "undo" }) => void;
  t: Dict;
}) {
  const modelerRef = useRef<BpmnModelerHandle>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const propsTitleId = useId();
  const router = useRouter();

  const [shownXml, setShownXml] = useState(xml);
  const [importKey, setImportKey] = useState(0);
  // The server's diagram on the canvas: a diagram the page brings that is
  // this one changes nothing.
  const propXml = useRef(xml);
  // A diagram the page brought while a name was being typed in place: it is
  // put on the canvas once the typing has ended.
  const waitingXml = useRef<string | null>(null);

  // Which element stands for which step, for the diagram on the canvas.
  const [ops, setOps] = useState<OpsState>("unknown");
  // In a ref for the editor's tools, which read it when they are used, and in
  // state for the properties panel, which draws from it.
  const mappingRef = useRef<{ forXml: string; mapping: BpmnMapping } | null>(null);
  const [mapping, setMappingState] = useState<{ forXml: string; mapping: BpmnMapping } | null>(null);
  function setMapping(next: { forXml: string; mapping: BpmnMapping } | null) {
    mappingRef.current = next;
    setMappingState(next);
  }
  const mappingSeq = useRef(0);
  const [mappingError, setMappingError] = useState(false);
  const stepsRef = useRef<BlueprintStep[]>(steps);
  useEffect(() => {
    stepsRef.current = steps;
    modelerRef.current?.refreshOps();
    // A rename kept over a version written elsewhere goes out once the page has its steps.
    latest.current?.flushPending();
  }, [steps]);

  // The version the next edit is made on: the page's, or the one the last edit wrote.
  const canvasVersion = useRef(baseVersion);
  // Set when an edit was refused as changed elsewhere: until the page has read
  // the newer version, an edit would be made on the old one and refused again.
  const waitingForVersion = useRef(false);
  // The page's version as it is now, for a refusal that comes after the page already read a newer one.
  const pageVersion = useRef(baseVersion);
  const reverting = useRef(false);
  useEffect(() => {
    canvasVersion.current = baseVersion;
    pageVersion.current = baseVersion;
    waitingForVersion.current = false;
    // A rename kept over that refusal goes out now, on the newer version: once
    // the page has also handed over that version's steps, which it does in an
    // effect of its own after this one.
    const timer = window.setTimeout(() => latest.current?.flushPending(), 0);
    return () => window.clearTimeout(timer);
  }, [baseVersion]);
  const showDataRef = useRef(showData);
  useEffect(() => {
    showDataRef.current = showData;
  }, [showData]);

  const busy = useRef(false);
  const [working, setWorking] = useState(false);
  // The branch dialog: open for a new decision after a step, or for a decision to edit.
  const [decisionDialog, setDecisionDialog] = useState<BpmnDecisionRequest | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  // The path dialog: open for a new rework or rejection path on a step, or for a path to edit.
  const [reworkDialog, setReworkDialog] = useState<BpmnReworkRequest | null>(null);
  const [reworkError, setReworkError] = useState<string | null>(null);
  // What the last refused edit said, for the branch dialog, which stays open over it.
  const lastRefusal = useRef<string | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  // A version written elsewhere refused the last edit: the canvas shows the newer diagram.
  const [changedElsewhere, setChangedElsewhere] = useState(false);
  const [labelEditing, setLabelEditingState] = useState(false);
  // Read by the editor's tools: no other edit starts while a name is typed in place.
  const typing = useRef(false);
  function setLabelEditing(active: boolean) {
    typing.current = active;
    setLabelEditingState(active);
  }

  const readOnly = locked || ops !== "on";

  const [selection, setSelection] = useState<BpmnSelectionInfo>(null);
  /** The lanes the canvas draws, top to bottom: the step panel's lane select lists them. */
  const [canvasLanes, setCanvasLanes] = useState<{ id: string; name: string }[]>([]);
  const [propsClosed, setPropsClosed] = useState(false);
  const [zoom, setZoom] = useState<number | null>(null);
  const pendingFocus = useRef<string | null>(null);
  // The names, descriptions and types given steps and refused as changed
  // elsewhere (or given while the canvas could not take them), not sent yet:
  // one entry a step, so an edit of another step does not replace them.
  const pendingEdits = useRef<KeptPanelEdit[]>([]);
  // What the last edit left for the wizard to complete (wizard_api's needs_attention):
  // in state for the step panel, in a ref for the type menu, which reads it when it opens.
  const [needsAttention, setNeedsAttentionState] = useState<string[]>([]);
  const needsAttentionRef = useRef<string[]>([]);
  function setNeedsAttention(next: string[]) {
    needsAttentionRef.current = next;
    setNeedsAttentionState(next);
  }
  // Places of dragged shapes and bent flows not sent yet, per drawing mode.
  const pendingLayout = useRef<{ dataObjects: boolean; layout: BpmnLayoutChange } | null>(null);
  const layoutTimer = useRef<number | null>(null);
  // The layout on its way: the next edit, or a diagram read again, waits for it.
  const layoutSending = useRef<Promise<void>>(Promise.resolve());

  /** The mapping of the diagram on the canvas, when the page's steps are the ones it was drawn from. */
  function opsContext() {
    const current = mappingRef.current;
    if (!current || busy.current || typing.current || current.forXml !== propXml.current) return null;
    if (!mappingFitsSteps(current.mapping, stepsRef.current)) return null;
    return { mapping: current.mapping, steps: stepsRef.current };
  }

  async function readMapping(dataObjects: boolean): Promise<ServerMapping | "unavailable"> {
    const res = await fetch(`/api/sessions/${sessionId}/bpmn/mapping${bpmnDataObjectsQuery(dataObjects)}`, {
      cache: "no-store",
    });
    if (res.status === 503) {
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (body?.error === "needs_wizard_api") return "unavailable";
    }
    if (!res.ok) throw new Error(`mapping ${res.status}`);
    const body = (await res.json()) as { mapping?: BpmnMapping; has_draft?: boolean };
    return {
      mapping: body.mapping && typeof body.mapping === "object" ? body.mapping : {},
      // Said by wizard_api since the operations need the draft; an answer without it has one.
      hasDraft: body.has_draft !== false,
    };
  }

  /** Edits on, or off until the agent has written its draft. */
  function takeMapping(forXml: string, read: ServerMapping) {
    setMapping({ forXml, mapping: read.mapping });
    setOps(read.hasDraft ? "on" : "no_draft");
  }

  /** Reads the mapping of `forXml`, the diagram the page brought. */
  function loadMapping(forXml: string) {
    const seq = ++mappingSeq.current;
    setMappingError(false);
    readMapping(showDataRef.current)
      .then((read) => {
        if (seq !== mappingSeq.current) return;
        if (read === "unavailable") {
          setMapping(null);
          setOps("off");
          return;
        }
        takeMapping(forXml, read);
        modelerRef.current?.refreshOps();
        // A kept rename waited for the mapping of the diagram now on the canvas.
        latest.current?.flushPending();
      })
      .catch(() => {
        if (seq === mappingSeq.current) setMappingError(true);
      });
  }

  /** The diagram and its mapping as the server has them now, for the "Show data" mode on screen. */
  async function readServerDiagram(): Promise<ServerDiagram> {
    const query = bpmnDataObjectsQuery(showDataRef.current);
    const [diagram, read] = await Promise.all([
      fetch(`/api/sessions/${sessionId}/bpmn${query}`, { cache: "no-store" }).then((res) => {
        if (!res.ok) throw new Error(`bpmn ${res.status}`);
        return res.text();
      }),
      readMapping(showDataRef.current),
    ]);
    if (!diagram.trim() || read === "unavailable") throw new Error("no diagram");
    return { xml: diagram, ...read };
  }

  function showDiagram(next: ServerDiagram) {
    waitingXml.current = null;
    propXml.current = next.xml;
    mappingSeq.current += 1;
    takeMapping(next.xml, next);
    setShownXml(next.xml);
    // Also when the text is the same: what was drawn on the canvas meanwhile goes.
    setImportKey((k) => k + 1);
    modelerRef.current?.refreshOps();
  }

  /** A diagram the page brought (a version from the chat, "Show data" switched). */
  function showPageDiagram(next: string) {
    // Drags not sent yet go now: the page's diagram replaces the canvas.
    void flushLayout();
    waitingXml.current = null;
    propXml.current = next;
    setShownXml(next);
    setImportKey((k) => k + 1);
    loadMapping(next);
  }

  useEffect(() => {
    loadMapping(xml);
    // Once, for the diagram the panel opened with; later ones come with showPageDiagram.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A new diagram from the page replaces the canvas, unless an edit's own
  // reload is on its way (it reads the newest one) or a name is being typed.
  useEffect(() => {
    if (xml === propXml.current) return;
    if (busy.current) return;
    if (modelerRef.current?.isEditing()) {
      waitingXml.current = xml;
      return;
    }
    showPageDiagram(xml);
    // showPageDiagram reads refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [xml, sessionId]);

  function onEditingEnd() {
    const next = waitingXml.current;
    if (next && !busy.current && !modelerRef.current?.isEditing()) showPageDiagram(next);
    // A name typed in the field meanwhile waited for the typing on the canvas to end.
    else latest.current?.flushPending();
  }

  /** The server's diagram goes back on the canvas: after a refused edit, or a change no operation describes. */
  async function revert() {
    // An edit on its way draws the server's diagram itself when it is answered.
    if (busy.current) return;
    // Until the server's diagram is back, a kept rename would be matched against the old one.
    reverting.current = true;
    try {
      // A drag made before it is kept, and the diagram read back has it.
      await flushLayout();
      showDiagram(await readServerDiagram());
    } catch {
      // The diagram the canvas stood on, drawn again.
      setImportKey((k) => k + 1);
    } finally {
      reverting.current = false;
    }
    latest.current?.flushPending();
  }

  /** What a refused edit says, in the UI language: never wizard_api's own (English) words. */
  function refusalMessage(err: unknown): string {
    if (!(err instanceof OperationRefused)) return t.wsBpmnSaveError;
    switch (err.code) {
      case "agent_busy":
        return t.bpmnAgentBusy;
      case "nothing_to_undo":
        return t.bpmnNothingToUndo;
      case "cannot_undo":
        return t.bpmnCannotUndo;
      case "no_draft":
        return t.bpmnNeedsDraft;
      case "too_large":
        return t.bpmnTooLarge;
      case "invalid_operation":
      case "unsupported_edit":
      case "readonly_section": {
        if (err.reason === "lane_in_use") return t.bpmnLaneInUse;
        if (err.reason === "cycle") return t.bpmnLoopRefused;
        if (err.reason === "second_producer") return t.bpmnDataSecondProducer;
        if (err.reason === "still_used") return t.bpmnDataStillUsed;
        if (err.reason === "only_producer") return t.bpmnDataOnlyProducer;
        if (err.reason === "already_linked") return t.bpmnDataAlreadyLinked;
        const field = fieldInPlainWords(err.field, t);
        return field ? fillTemplate(t.bpmnOpRefusedField, { field }) : t.bpmnOpRefused;
      }
      default:
        return t.bpmnOpRefused;
    }
  }

  /**
   * One edit: sent at once on the version the canvas shows, then the server's
   * diagram and mapping are read again. A refusal puts the server's diagram
   * back; a version written elsewhere meanwhile is read by the page too.
   * `afterMade` runs once the edit is made, before the diagram is read again
   * (a lane change drops the step's kept place then, and only then).
   */
  async function run(
    kind: "ops" | "undo",
    operations: BlueprintOperation[] = [],
    afterMade?: () => Promise<void>,
  ): Promise<boolean> {
    // The one gate every edit passes (palette, context pad, keys, the name
    // field, Kumoa): none starts while a name is typed in place, or the
    // diagram drawn after it would be imported over the typed name.
    lastRefusal.current = null;
    if (busy.current || typing.current) return false;
    const base = canvasVersion.current;
    busy.current = true;
    setWorking(true);
    setStatus({ kind: "saving" });
    setChangedElsewhere(false);
    modelerRef.current?.refreshOps();
    try {
      await flushLayout();
      if (typeof base !== "number") throw new Error("no version to edit");
      const result =
        kind === "undo"
          ? { ...(await postUndo(sessionId, base)), via: "undo" as const }
          : { ...(await postOperations(sessionId, base, operations)), via: "save" as const };
      canvasVersion.current = result.version;
      stepsRef.current = result.blueprint.steps;
      // What this edit left for the wizard (an AI step without a component); an undo leaves nothing said.
      setNeedsAttention("needsAttention" in result ? result.needsAttention : []);
      if (afterMade) await afterMade();
      let next: ServerDiagram | null = null;
      try {
        next = await readServerDiagram();
      } catch {
        next = null;
      }
      busy.current = false;
      if (next) showDiagram(next);
      onSynced({ blueprint: result.blueprint, xml: next?.xml ?? null, version: result.version, via: result.via });
      // Made, but its diagram did not come: the way to read it again.
      const warnings = "warnings" in result ? result.warnings : [];
      setStatus(
        next
          ? kind === "undo"
            ? { kind: "undone" }
            : { kind: "saved", ...(warnings.length ? { warnings } : {}) }
          : { kind: "error", message: t.wsBpmnError, retry: () => void latest.current?.revert() },
      );
      return true;
    } catch (err) {
      busy.current = false;
      if (err instanceof OperationRefused && err.code === "no_draft") {
        // The agent has not written its blueprint yet: the editor waits for it, as the note says.
        setStatus({ kind: "idle" });
        setOps("no_draft");
        lastRefusal.current = t.bpmnNeedsDraft;
      } else if (err instanceof OperationRefused && err.code === "changed_elsewhere") {
        // What the user gave the step (a name, a description, a type) is not
        // given up: it is made again on the newer version once the page has it.
        // What the user typed for the same step meanwhile is newer and stays.
        pendingEdits.current = mergeKeptEdits(pendingEdits.current, keptPanelEdits(operations), { older: true });
        // The page may have read the newer version while the edit was on its
        // way: then no newer one comes, and the kept edits go out on it now.
        waitingForVersion.current = waitsForVersion(base, pageVersion.current);
        lastRefusal.current = t.wsJsonChangedElsewhere;
        setChangedElsewhere(true);
        setStatus({ kind: "idle" });
        // The page reads the newer version and its number; the canvas draws its diagram now.
        router.refresh();
      } else {
        lastRefusal.current = refusalMessage(err);
        setStatus({ kind: "error", message: lastRefusal.current });
      }
      await revert();
      return false;
    } finally {
      busy.current = false;
      setWorking(false);
      modelerRef.current?.refreshOps();
      flushPending();
    }
  }

  /**
   * A drag or a bent flow: merged with the others of the last 800 ms and
   * kept with the drawing mode on screen. It writes no version and draws
   * nothing again. The editor's rules let no move start while an edit is on
   * its way, and `run` sends what is pending before its edit.
   */
  function sendLayout(change: BpmnLayoutChange) {
    const dataObjects = showDataRef.current;
    const pending = pendingLayout.current;
    if (pending && pending.dataObjects !== dataObjects) void flushLayout();
    const into = pendingLayout.current ?? { dataObjects, layout: { shapes: {}, edges: {} } };
    Object.assign(into.layout.shapes, change.shapes);
    Object.assign(into.layout.edges, change.edges);
    pendingLayout.current = into;
    if (layoutTimer.current) window.clearTimeout(layoutTimer.current);
    layoutTimer.current = window.setTimeout(() => void flushLayout(), LAYOUT_SAVE_DELAY_MS);
  }

  /**
   * Keeps the places of dragged shapes and bent flows (`PUT /bpmn/layout`);
   * no blueprint version is written. Resolves once what was pending, and any
   * layout already on its way, has been answered: a diagram read after it has
   * the places.
   */
  function flushLayout(): Promise<void> {
    if (layoutTimer.current) window.clearTimeout(layoutTimer.current);
    layoutTimer.current = null;
    const pending = pendingLayout.current;
    pendingLayout.current = null;
    if (!pending) return layoutSending.current;
    const sending = layoutSending.current.then(async () => {
      try {
        const res = await fetch(
          `/api/sessions/${sessionId}/bpmn/layout?data_objects=${pending.dataObjects ? 1 : 0}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(pending.layout),
            keepalive: true,
          },
        );
        if (!res.ok) throw new Error(`layout ${res.status}`);
      } catch {
        setStatus({ kind: "error", message: t.wsBpmnSaveError });
      }
    });
    layoutSending.current = sending;
    return sending;
  }

  /**
   * Drops the kept places of `shapes` and the routes of `edges`, in both
   * drawing modes (`null` resets an id): a step put in another lane is drawn
   * where its new lane puts it. Sent after what is pending.
   */
  function resetLayout(shapes: string[], edges: string[]): Promise<void> {
    if (!shapes.length && !edges.length) return layoutSending.current;
    void flushLayout();
    const body = JSON.stringify({
      shapes: Object.fromEntries(shapes.map((id) => [id, null])),
      edges: Object.fromEntries(edges.map((id) => [id, null])),
    });
    const sending = layoutSending.current.then(async () => {
      try {
        for (const mode of [0, 1]) {
          const res = await fetch(`/api/sessions/${sessionId}/bpmn/layout?data_objects=${mode}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body,
          });
          if (!res.ok) throw new Error(`layout ${res.status}`);
        }
      } catch {
        // The server ignores a kept place outside the step's own lane, so the step is drawn in its lane anyway.
      }
    });
    layoutSending.current = sending;
    return sending;
  }

  /**
   * A step put in another lane, dragged on the canvas or picked in its panel:
   * `set_step_lane` through `run`, and once it is made the step's kept place
   * and its flows' routes go, before the diagram is read again. A refused
   * change keeps them. While nothing can be sent the server's diagram goes
   * back on the canvas.
   */
  async function moveStepToLane(change: BpmnStepLaneChange): Promise<boolean> {
    if (busy.current || typing.current || !opsContext()) {
      void revert();
      return false;
    }
    return run("ops", [change.op], () => resetLayout(change.shapes, change.edges));
  }

  /** A step's "Add decision after" or a decision's Edit: the branch dialog opens, while the canvas can take an edit. */
  function openDecision(request: BpmnDecisionRequest) {
    if (!opsContext()) return;
    setDecisionError(null);
    setDecisionDialog(request);
  }

  /** The branch dialog's Save: one edit through `run`. A refusal keeps the dialog open and says why. */
  async function saveDecision(values: DecisionValues): Promise<boolean> {
    const request = decisionDialog;
    if (!request || decisionProblem(values)) return false;
    const op = opForDecision(values, request);
    // An edit that changes nothing: the dialog closes, nothing is sent.
    if (!op) return true;
    setDecisionError(null);
    const made = await run("ops", [op]);
    if (!made) setDecisionError(lastRefusal.current ?? t.bpmnOpRefused);
    return made;
  }

  /** A step's "Add rework path" or a path's Edit: the path dialog opens, while the canvas can take an edit. */
  function openRework(request: BpmnReworkRequest) {
    if (!opsContext()) return;
    setReworkError(null);
    setReworkDialog(request);
  }

  /** The path dialog's Save: one edit through `run`. A refusal keeps the dialog open and says why. */
  async function saveRework(values: ReworkValues): Promise<boolean> {
    const request = reworkDialog;
    if (!request || reworkProblem(values)) return false;
    const op = opForRework(values, request);
    // An edit that changes nothing: the dialog closes, nothing is sent.
    if (!op) return true;
    setReworkError(null);
    const made = await run("ops", [op]);
    if (!made) setReworkError(lastRefusal.current ?? t.bpmnOpRefused);
    return made;
  }

  // Dragged shapes are kept before the page goes: another page, or a reload
  // of this one (keepalive lets the request outlive it).
  useEffect(() => {
    const onPageHide = () => void latest.current?.flushLayout();
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      void flushLayout();
    };
    // flushLayout reads refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The functions above close over this render's props (t, onSynced): the
  // editor holds one object for its life, which calls the latest of them.
  const latest = useRef<{
    opsContext: typeof opsContext;
    run: typeof run;
    revert: typeof revert;
    sendLayout: typeof sendLayout;
    flushLayout: typeof flushLayout;
    flushPending: () => void;
    stepTypeOf: (stepId: string) => StepType | null;
    moveStepToLane: typeof moveStepToLane;
    openDecision: typeof openDecision;
    openRework: typeof openRework;
  } | null>(null);
  const stableOps = useMemo<BpmnEditorOps>(
    () => ({
      context: () => latest.current?.opsContext() ?? null,
      onOperation: (list) => void latest.current?.run("ops", list),
      onRevert: () => void latest.current?.revert(),
      onLayout: (change) => latest.current?.sendLayout(change),
      onStepLane: (change) => void latest.current?.moveStepToLane(change),
      onDecision: (request) => latest.current?.openDecision(request),
      onRework: (request) => latest.current?.openRework(request),
      stepType: (stepId) => latest.current?.stepTypeOf(stepId) ?? null,
    }),
    [],
  );

  const selectedId = selection?.id ?? null;
  const stepIndex = stepIndexForBpmnId(steps, selectedId);
  const step = stepIndex >= 0 ? steps[stepIndex] : null;
  const typeLabel = stepTypeLabels(t);
  // The mapping of the diagram on the canvas, when the page's steps are the ones it was drawn from.
  const fitting = mapping && !working && mappingFitsSteps(mapping.mapping, steps) ? mapping.mapping : null;
  // The element's step, as the mapping names it: only a step's name can be edited here.
  const editableStep = !readOnly && selectedId && fitting ? stepIdOf(selectedId, fitting, steps) : null;

  // A newly picked element opens its properties.
  useEffect(() => {
    setPropsClosed(false);
  }, [selectedId]);

  const stepId = step?.id ?? null;
  const onSelectedStep = useRef(onSelectedStepChange);
  onSelectedStep.current = onSelectedStepChange;
  useEffect(() => {
    onSelectedStep.current?.(stepId);
  }, [stepId]);

  /**
   * What the properties panel covers once a step is picked, so the step is
   * centred beside it: the panel sits at the canvas's right edge, or across
   * its top when the canvas is narrow (PROPS_WIDE, the panel's own breakpoint).
   */
  function propsCover() {
    const width = canvasRef.current?.clientWidth ?? 0;
    return width >= PROPS_WIDE ? { right: 312 } : { top: 300 };
  }

  useEffect(() => {
    if (!focusRequest) return;
    const id = stepIdToBpmnId(focusRequest.stepId);
    if (!modelerRef.current?.focusElement(id, propsCover())) pendingFocus.current = id;
  }, [focusRequest]);

  function onImported() {
    const m = modelerRef.current;
    if (!m) return;
    setCanvasLanes(m.lanes());
    if (pendingFocus.current && m.focusElement(pendingFocus.current, propsCover())) pendingFocus.current = null;
  }

  /**
   * The step panel's values for `step` as the server has it now: its
   * description as the canvas draws it.
   */
  function savedFields(step: BlueprintStep) {
    const drawn = modelerRef.current?.documentationOf(stepIdToBpmnId(step.id));
    return panelFields({ ...step, description: descriptionOf(step, drawn) }, needsAttentionRef.current);
  }

  /** The type a step has now, for the type menu: as the panel shows it. */
  function stepTypeOf(stepId: string): StepType | null {
    const step = stepsRef.current.find((s) => s.id === stepId);
    return step ? savedFields(step).type : null;
  }

  /**
   * Sends what was typed for a step and kept, once nothing else is on its
   * way. While the canvas cannot take it (an edit is answered, the page has
   * not read the version a refusal named yet) it is kept, and sent when it can
   * be: on the newer version, where its step is still there.
   */
  function flushPending() {
    const kept = pendingEdits.current;
    if (!kept.length || busy.current || reverting.current || typing.current || waitingForVersion.current) return;
    const context = opsContext();
    if (!context) return;
    pendingEdits.current = [];
    const isDecision = (stepId: string) =>
      Object.keys(context.mapping).some(
        (elementId) =>
          isDecisionStep(elementId, context.mapping) && stepIdOf(elementId, context.mapping, context.steps) === stepId,
      );
    const { ops, gone, decisionTypes } = keptEditOps(kept, stepsRef.current, savedFields, isDecision);
    // Removed meanwhile, elsewhere: what was typed has nowhere to go, and the
    // user hears so. A step that became a decision keeps its type: a type
    // change would turn its gateway into a task.
    const notes = [
      ...gone.map((edit) =>
        edit.name !== undefined ? fillTemplate(t.bpmnRenameStepGone, { name: edit.name.trim() }) : t.bpmnEditStepGone,
      ),
      ...decisionTypes.map(({ step }) => fillTemplate(t.bpmnTypeStepIsDecision, { name: step.name })),
    ];
    const tell = () => {
      if (notes.length) setStatus({ kind: "error", message: notes.join(" ") });
    };
    if (!ops.length) {
      tell();
      return;
    }
    void run("ops", ops).then((made) => {
      if (made) tell();
    });
  }

  /**
   * The step panel saved: what changed against the step as the server has
   * it, as one edit through the same gate as the canvas's (`run`). Typed text
   * that cannot go now is kept and sent later (flushPending). True once the
   * edit is made, or when there was nothing to change.
   */
  /** The step panel's lane select: the lanes the mapping names a participant for, top to bottom. */
  const laneOptions = fitting
    ? canvasLanes.flatMap((lane) => {
        const id = laneIdOf(lane.id, fitting);
        return id ? [{ id, name: lane.name || id }] : [];
      })
    : [];

  /** The lane select picked `laneId` (null: the lane of the step's type). */
  async function saveLane(laneId: string | null): Promise<boolean> {
    if (!selectedId || !editableStep) return false;
    const current = fitting ? performedByOf(selectedId, fitting) : "";
    if ((laneId ?? "") === current) return true;
    return moveStepToLane({
      op: { op: "set_step_lane", step_id: editableStep, lane_id: laneId },
      shapes: [selectedId],
      edges: modelerRef.current?.edgesOf(selectedId) ?? [],
    });
  }

  async function savePanel(after: PanelValues): Promise<boolean> {
    const step = stepsRef.current.find((s) => s.id === after.stepId);
    if (!step || editableStep !== after.stepId) return false;
    const ops = panelOps(savedFields(step), after);
    if (!ops.length) return true;
    if (busy.current || typing.current || reverting.current || waitingForVersion.current) {
      pendingEdits.current = mergeKeptEdits(pendingEdits.current, keptPanelEdits(ops));
      return false;
    }
    return run("ops", ops);
  }

  useEffect(() => {
    latest.current = {
      opsContext,
      run,
      revert,
      sendLayout,
      flushLayout,
      flushPending,
      stepTypeOf,
      moveStepToLane,
      openDecision,
      openRework,
    };
  });

  /** "Lopeta muokkaus": the canvas is read-only again, as it opened. */
  function lock() {
    if (busy.current || modelerRef.current?.isEditing()) return;
    onLock?.();
  }

  const showProps = Boolean(selection) && !propsClosed;
  const typeName = (type: string) => t.wsBpmnTypeNames[`bpmn:${type}`] ?? type;

  // The one line that says where the diagram stands; nothing when there is nothing to say.
  let statusLine: ReactNode = null;
  if (status.kind === "saving") {
    statusLine = (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Icon name="loaderCircle" size={14} className="motion-safe:animate-spin" />
        {t.wsBpmnSaving}
      </span>
    );
  } else if (status.kind === "error") {
    statusLine = (
      <span className="inline-flex items-center gap-2 text-danger-text">
        {status.message}
        {status.retry && (
          <button type="button" className="font-medium underline underline-offset-2" onClick={status.retry}>
            {t.editorRetry}
          </button>
        )}
      </span>
    );
  } else if (mappingError && ops !== "off") {
    statusLine = (
      <span className="inline-flex items-center gap-2 text-danger-text">
        {t.wsBpmnError}
        <button
          type="button"
          className="font-medium underline underline-offset-2"
          onClick={() => loadMapping(propXml.current)}
        >
          {t.editorRetry}
        </button>
      </span>
    );
  } else if ((status.kind === "saved" || status.kind === "undone") && !changedElsewhere) {
    statusLine = (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Icon name="check" size={14} className="text-success-text" />
        {/* When the wizard hears of it: wizard_api tells the agent with the next chat message. */}
        {status.kind === "undone" ? t.bpmnUndone : t.bpmnSaved}
        {status.kind === "saved" && status.warnings?.length ? (
          <span data-testid="bpmn-warnings" className="text-warning-text">
            {status.warnings.join(" ")}
          </span>
        ) : null}
      </span>
    );
  } else if (update && !reloading && !changedElsewhere) {
    // The canvas shows the diagram of a version written elsewhere.
    statusLine = <FlowUpdatedLine update={update} testId="bpmn-updated" t={t} />;
  }

  // A version the page brought after an edit made here: "Tallennettu" was about the one before.
  const [seenUpdate, setSeenUpdate] = useState(update);
  if (seenUpdate !== update) {
    setSeenUpdate(update);
    if (update && (status.kind === "saved" || status.kind === "undone")) setStatus({ kind: "idle" });
    // What the last edit here left for the wizard may be done in that version.
    if (update) setNeedsAttentionState([]);
  }
  useEffect(() => {
    needsAttentionRef.current = needsAttention;
  }, [needsAttention]);

  const opsOn = ops === "on" && !locked;

  // The canvas turned read-only (locked, no wizard_api, no draft): the branch dialog goes with its tools.
  if (decisionDialog && !opsOn) setDecisionDialog(null);
  if (reworkDialog && !opsOn) setReworkDialog(null);

  return (
    <section
      className="relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-border bg-surface"
      aria-label={t.wsTabFlow}
      data-testid="bpmn-panel"
      data-locked={locked}
      data-ops={ops}
    >
      <div ref={canvasRef} className="@container relative min-h-0 flex-1 overflow-hidden">
        <BpmnModeler
          ref={modelerRef}
          xml={shownXml}
          importKey={importKey}
          readOnly={readOnly}
          ariaLabel={t.wsTabFlow}
          loadErrorLabel={t.wsBpmnError}
          editorLabels={{
            addTask: t.bpmnPaletteAddTask,
            connect: t.bpmnPaletteConnect,
            rename: t.bpmnPadRename,
            changeType: t.bpmnPadChangeType,
            stepTypes: {
              user_task: typeLabel.io,
              automated_task: typeLabel.ai,
              human_review: typeLabel.human_review,
            },
            remove: t.bpmnPadDelete,
            append: t.bpmnPadAppend,
            moveEarlier: t.bpmnPadMoveEarlier,
            moveLater: t.bpmnPadMoveLater,
            connectFrom: t.bpmnPadConnect,
            derived: t.bpmnDerivedElement,
            newStepName: t.flowNewStepName,
            addLane: t.bpmnPaletteAddLane,
            newLaneName: t.bpmnNewLaneName,
            renameLane: t.bpmnPadRenameLane,
            removeLane: t.bpmnPadRemoveLane,
            addDecision: t.bpmnPadAddDecision,
            editDecision: t.bpmnPadEditDecision,
            removeDecision: t.bpmnPadRemoveDecision,
            addRework: t.bpmnPadAddRework,
            editRework: t.bpmnPadEditRework,
            removeRework: t.bpmnPadRemoveRework,
            renameDataObject: t.bpmnPadRenameDataObject,
            connectData: t.bpmnPadConnectData,
          }}
          ops={stableOps}
          onSelectionChange={setSelection}
          onZoomChange={setZoom}
          onDirectEditingChange={setLabelEditing}
          onImported={onImported}
          onEditingEnd={onEditingEnd}
          minimapLabel={t.bpmnMinimap}
          onToggleFullscreen={fullView?.toggle}
        />

        <div className="absolute right-3 top-3 z-10 flex items-center gap-2">
          {onShowDataChange && (
            // Switching redraws the diagram from the server, so not while an edit is on its way or a name is typed.
            <button
              type="button"
              className="flex h-[34px] items-center gap-1.5 rounded-lg border border-border bg-surface/95 px-2.5 text-xs font-medium text-text-secondary shadow-sm backdrop-blur-sm hover:text-text-strong disabled:cursor-not-allowed disabled:opacity-60"
              aria-pressed={showData}
              onClick={() => {
                void flushLayout();
                onShowDataChange(!showData);
              }}
              disabled={working || labelEditing || reloading}
              data-testid="bpmn-show-data"
            >
              <Icon name={showData ? "eye" : "eyeOff"} size={14} />
              {t.bpmnShowData}
            </button>
          )}
          <BpmnZoomControls
            zoom={zoom}
            onZoomIn={() => modelerRef.current?.zoomIn()}
            onZoomOut={() => modelerRef.current?.zoomOut()}
            onFit={() => modelerRef.current?.fit()}
            zoomInLabel={t.wsBpmnZoomIn}
            zoomOutLabel={t.wsBpmnZoomOut}
            fitLabel={t.bpmnFitView}
            groupLabel={t.wsBpmnToolbar}
            expanded={fullView?.on ?? false}
            onToggleExpanded={fullView?.toggle}
            expandLabel={t.flowFullView}
            collapseLabel={t.flowFullViewExit}
          />
        </div>

        {showProps && selection && (
          <aside
            className="pop-in absolute inset-x-3 top-14 z-10 rounded-lg border border-border bg-surface p-3 shadow-md @lg:left-auto @lg:w-72"
            aria-labelledby={propsTitleId}
            data-testid="bpmn-properties"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 id={propsTitleId} className="flex min-w-0 items-center gap-2 text-sm font-semibold text-text-strong">
                {step ? (
                  <>
                    <StepNumber n={stepIndex + 1} type={step.type} />
                    {fillTemplate(t.bpmnStepTitle, { n: String(stepIndex + 1) })}
                  </>
                ) : (
                  typeName(selection.type)
                )}
              </h4>
              <div className="flex shrink-0 items-center gap-1.5">
                {step && <AskStepButton step={step} index={stepIndex} t={t} withLabel testId="bpmn-ask-step" />}
                <button
                  type="button"
                  className="icon-btn h-7 w-7"
                  onClick={() => setPropsClosed(true)}
                  aria-label={t.wsBpmnPropertiesClose}
                  title={t.wsBpmnPropertiesClose}
                >
                  <Icon name="x" size={14} />
                </button>
              </div>
            </div>
            {step ? (
              // A step: its fields, read-only while the canvas is, or while an edit is on its way.
              <BpmnStepPanel
                key={step.id}
                fields={panelFields(
                  { ...step, description: descriptionOf(step, selection.documentation) },
                  needsAttention,
                )}
                disabled={!editableStep || working || labelEditing}
                onSave={savePanel}
                lanes={editableStep && fitting ? laneOptions : null}
                lane={selectedId && fitting ? performedByOf(selectedId, fitting) : ""}
                onLaneChange={saveLane}
                t={t}
              />
            ) : (
              <p className="flex flex-col gap-1">
                <span className="text-xs font-medium text-text-muted">{t.wsBpmnPropertiesName}</span>
                <span
                  className="break-words text-sm font-medium text-text-strong"
                  data-testid="bpmn-property-name-text"
                >
                  {selection.name}
                </span>
              </p>
            )}
            {opsOn && !step && fitting && !decisionOf(selection.id, fitting) && !exceptionOf(selection.id, fitting) && (
              <p className="mt-2 text-xs text-text-muted" data-testid="bpmn-derived-note">
                {t.bpmnDerivedElement}
              </p>
            )}
          </aside>
        )}

        {(statusLine || changedElsewhere || pocNoteLabel) && (
          <div
            className="pop-in absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-col gap-1.5 rounded-lg border border-border bg-surface/95 px-3 py-2 text-xs shadow-sm backdrop-blur-sm sm:max-w-md"
            data-testid="bpmn-status"
          >
            {statusLine && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5" role="status">
                {statusLine}
              </div>
            )}
            {/* The edit was made on a version written elsewhere since: it was not made, and the newer one is shown. */}
            {changedElsewhere && (
              <p className="text-warning-text" role="status" data-testid="bpmn-changed-elsewhere">
                {t.wsJsonChangedElsewhere}
              </p>
            )}
            {/* An edit writes a new blueprint version; the PoC package stays as it was. */}
            {pocNoteLabel && (
              <p className="flex items-start gap-1.5 text-text-muted" data-testid="bpmn-saved-poc-note">
                <Icon name="info" size={13} className="mt-px" />
                <span>{pocNoteLabel}</span>
              </p>
            )}
          </div>
        )}
      </div>
      {decisionDialog && (
        <BpmnBranchDialog
          mode={"after" in decisionDialog ? "add" : "edit"}
          initial={
            "after" in decisionDialog
              ? { name: "", branches: [] }
              : { name: decisionDialog.decision.name, branches: decisionDialog.decision.branches }
          }
          steps={steps.map((s) => ({ id: s.id, name: s.name }))}
          busy={working}
          error={decisionError}
          onSave={saveDecision}
          onClose={() => setDecisionDialog(null)}
          t={t}
        />
      )}
      {reworkDialog && (
        <BpmnReworkDialog
          mode={"attachedTo" in reworkDialog ? "add" : "edit"}
          initial={
            "attachedTo" in reworkDialog
              ? { name: "", condition: "", outcome: "" }
              : {
                  name: reworkDialog.exception.name,
                  condition: reworkDialog.exception.condition,
                  outcome: reworkDialog.exception.outcome,
                }
          }
          steps={reworkTargets(
            "attachedTo" in reworkDialog ? reworkDialog.attachedTo : reworkDialog.exception.attached_to,
            steps,
          ).map((s) => ({ id: s.id, name: s.name }))}
          busy={working}
          error={reworkError}
          onSave={saveRework}
          onClose={() => setReworkDialog(null)}
          t={t}
        />
      )}
      {locked && onUnlock ? (
        <FlowLockedNote onUnlock={onUnlock} testId="bpmn" t={t} />
      ) : ops === "off" || ops === "no_draft" ? (
        // No wizard_api to send edits to, or no blueprint of the agent's to edit yet: the diagram is for reading.
        <FlowEditingNote
          help={ops === "off" ? t.bpmnNeedsWizardApi : t.bpmnNeedsDraft}
          icon="lock"
          onLock={onLock ? lock : undefined}
          testId="bpmn-readonly"
          t={t}
        />
      ) : opsOn ? (
        <FlowEditingNote
          help={t.bpmnEditHelp}
          actions={
            <button
              type="button"
              className="btn-secondary px-2.5 py-1 text-xs"
              onClick={() => void run("undo")}
              disabled={working || labelEditing}
              data-testid="bpmn-undo"
            >
              <Icon name="rotateCcw" size={13} />
              {t.bpmnUndo}
            </button>
          }
          onLock={onLock ? lock : undefined}
          lockWaits={working || labelEditing}
          testId="bpmn"
          t={t}
        />
      ) : null}
    </section>
  );
}
