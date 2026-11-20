"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { BLUEPRINT_CHANGED_ELSEWHERE, blueprintBaseTag } from "@/lib/blueprint-draft";
import {
  BpmnModeler,
  type BpmnEditState,
  type BpmnModelerHandle,
  type BpmnSelectionInfo,
} from "@/components/bpmn-modeler";
import { BpmnZoomControls } from "@/components/bpmn-viewer-toolbar";
import { FlowEditingNote, FlowLockedNote, FlowUpdatedLine } from "@/components/flow-status";
import { AskStepButton, StepNumber, StepTypeTag, stepTypeLabels } from "@/components/step-type";
import { Icon } from "@/components/icons";
import {
  deleteBpmnDraft,
  getBpmnDraft,
  hasBpmnDraft,
  setBpmnDraft,
} from "@/lib/bpmn-session-drafts";
import {
  bpmnSemantics,
  stepIdToBpmnId,
  stepIndexForBpmnId,
  stripTaskCodePrefixes,
  type ModdleElement,
} from "@/lib/bpmn-edit-state";
import type { BlueprintUpdate } from "@/lib/blueprint-update";
import { fillTemplate } from "@/lib/chat-template";
import type { Dict } from "@/lib/i18n";
import type { Blueprint, BlueprintStep } from "@/lib/mock-sessions";

const NO_EDITS: BpmnEditState = { kind: "none", problems: { unconnected: [], unnamed: [] } };

/** How long a rename in the name field waits for more typing before it saves itself. */
const RENAME_SAVE_DELAY_MS = 800;

/** From this canvas width (Tailwind's @lg container, 32rem) the properties panel is a column at the right. */
const PROPS_WIDE = 512;

type SaveState = "idle" | "saving" | "saved" | "error" | "lint";

export function BpmnDiagramPanel({
  sessionId,
  xml,
  blueprint,
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
  t,
}: {
  sessionId: string;
  /** The diagram at the size of the window, and the control that takes it there and back. */
  fullView?: { on: boolean; toggle: () => void };
  /** The diagram as the server generated it from the blueprint. */
  xml: string;
  /** The session's blueprint as the page has it: `xml` is drawn from it. */
  blueprint: Blueprint;
  /** The blueprint's steps: their numbers, types and the chat reference. */
  steps: BlueprintStep[];
  /** Shown while saved changes are not in the PoC package yet. */
  /** Said after a save while the PoC package lacks it, with the control that generates the package again. */
  pocNoteLabel?: ReactNode;
  /**
   * The blueprint changed elsewhere and `xml` is being generated again: a
   * save now would write the canvas's older steps over that change.
   */
  reloading?: boolean;
  /**
   * Edits are off, as on the simple flow after Gate 2: the diagram can be
   * read and a step picked to ask the wizard about, and "Muokkaa" opens it.
   */
  locked?: boolean;
  onUnlock?: () => void;
  /**
   * Closes the diagram for edits again ("Lopeta muokkaus"): where `locked`
   * applies, the way back after "Muokkaa kaaviota".
   */
  onLock?: () => void;
  /** The blueprint is one the page brought, not a save made here: from the chat, or from elsewhere. */
  update?: BlueprintUpdate | null;
  /** Select and centre this step's task (a click on the step list). */
  focusRequest?: { stepId: string; seq: number } | null;
  /** The step whose task is selected on the canvas, for the step list. */
  onSelectedStepChange?: (stepId: string | null) => void;
  /** After a save: the blueprint and diagram as the server has them now. */
  onSynced: (result: { blueprint: Blueprint; xml: string }) => void;
  t: Dict;
}) {
  const modelerRef = useRef<BpmnModelerHandle>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const propsTitleId = useId();

  // The diagram on the canvas: the server's, a draft kept from before the tab
  // closed, or the server's answer to a save.
  const restored = useRef(getBpmnDraft(sessionId));
  // True until the restored draft has been compared with the diagram it was made on.
  const restoring = useRef(Boolean(restored.current));
  // Unsaved edits kept from before the tab closed are the user's to save or
  // give up: they never come back into a locked canvas, and the lock opens
  // for the simple flow beside it too.
  // Settled once the user closes the canvas again: the draft is gone by then.
  const [hadDraft, setHadDraft] = useState(() => hasBpmnDraft(sessionId));
  const readOnly = locked && !hadDraft;
  useEffect(() => {
    if (locked && hadDraft) onUnlock?.();
  }, [locked, hadDraft, onUnlock]);
  // Until the canvas stands on the server's diagram again, it is not the
  // version the page brought: the line that names that version waits.
  const [draftPending, setDraftPending] = useState(hadDraft);
  const [shownXml, setShownXml] = useState(restored.current?.xml ?? xml);
  const [importKey, setImportKey] = useState(0);
  // The server's diagram the canvas stands on: what its edits are compared with.
  const propXml = useRef(restored.current?.base ?? xml);
  // A diagram the server generated since, while the canvas had unsaved edits
  // (the agent wrote a blueprint version, the form saved one): the user
  // chooses which stays, as in the Blueprint form.
  const newerXml = useRef<string | null>(restored.current && restored.current.base !== xml ? xml : null);
  const [changedElsewhere, setChangedElsewhere] = useState(newerXml.current !== null);
  // The blueprint that newer diagram was drawn from. When a save reaches the
  // server while the choice is open, the server holds the canvas's diagram,
  // and "take the newer one" has to write this blueprint back.
  const blueprintRef = useRef(blueprint);
  blueprintRef.current = blueprint;
  // The blueprint the diagram on the canvas was drawn from: a save that starts
  // by itself names it, and is refused when the server holds a newer one.
  const canvasBlueprint = useRef(blueprint);
  const router = useRouter();
  const newerBlueprint = useRef<Blueprint | null>(newerXml.current !== null ? blueprint : null);
  const savedOverNewer = useRef(false);

  const [selection, setSelection] = useState<BpmnSelectionInfo>(null);
  const selectionRef = useRef<BpmnSelectionInfo>(null);
  selectionRef.current = selection;
  const [editName, setEditName] = useState("");
  const [propsClosed, setPropsClosed] = useState(false);
  const [edit, setEdit] = useState<BpmnEditState>(NO_EDITS);
  const editRef = useRef(edit);
  editRef.current = edit;
  // Bumped when an edit in place or a drag ends, with or without a change.
  const [editingEnded, setEditingEnded] = useState(0);
  const [zoom, setZoom] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [lint, setLint] = useState<{ errors: string[]; warnings: string[] }>({ errors: [], warnings: [] });
  const saving = useRef(false);
  const reloadingRef = useRef(reloading);
  reloadingRef.current = reloading;
  const pendingFocus = useRef<string | null>(null);
  // Set when the canvas is put back to a server diagram; the next selection gives the name field its name.
  const nameFromCanvas = useRef(false);

  /** Whether the canvas holds something an import would throw away. */
  function hasOwnEdits() {
    return (
      restoring.current ||
      saving.current ||
      editRef.current.kind !== "none" ||
      Boolean(modelerRef.current?.isEditing())
    );
  }

  function showServerDiagram(next: string) {
    nameFromCanvas.current = true;
    canvasBlueprint.current = blueprintRef.current;
    newerXml.current = null;
    newerBlueprint.current = null;
    savedOverNewer.current = false;
    setChangedElsewhere(false);
    propXml.current = next;
    deleteBpmnDraft(sessionId);
    setDraftPending(false);
    // What a save said was about the diagram this one replaces.
    setSaveState("idle");
    setLint({ errors: [], warnings: [] });
    setShownXml(next);
    // Also when the text is what the canvas was first given: its edits go.
    setImportKey((k) => k + 1);
  }

  // A new diagram from the server replaces the canvas only when the canvas has
  // nothing of the user's; otherwise it waits for the user's choice.
  useEffect(() => {
    if (newerXml.current === xml) return;
    if (propXml.current === xml) {
      // The server is back at the diagram the canvas stands on: nothing to
      // choose, unless a save of this canvas is what put it there.
      if (newerXml.current && !savedOverNewer.current) {
        newerXml.current = null;
        newerBlueprint.current = null;
        setChangedElsewhere(false);
      }
      return;
    }
    if (hasOwnEdits()) {
      newerXml.current = xml;
      newerBlueprint.current = blueprintRef.current;
      savedOverNewer.current = false;
      setChangedElsewhere(true);
    } else {
      showServerDiagram(xml);
    }
    // hasOwnEdits and showServerDiagram read refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [xml, sessionId]);

  // The edits went away while the choice was open (undone, or an edit in place
  // was given up): the newer diagram is the only one left.
  useEffect(() => {
    // Not after a save landed over the newer one: the canvas then shows what
    // the server holds, and the newer diagram is no longer there to show.
    if (!changedElsewhere || !newerXml.current || savedOverNewer.current || hasOwnEdits()) return;
    showServerDiagram(newerXml.current);
    // hasOwnEdits and showServerDiagram read refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changedElsewhere, edit, editingEnded]);

  // A version the page brought whose diagram is the one already on the canvas
  // (the change was not to the steps): "Tallennettu" was about the one before.
  const [seenUpdate, setSeenUpdate] = useState(update);
  if (seenUpdate !== update) {
    setSeenUpdate(update);
    if (update && saveState === "saved") setSaveState("idle");
  }

  const selectedId = selection?.id ?? null;
  const stepIndex = stepIndexForBpmnId(steps, selectedId);
  const step = stepIndex >= 0 ? steps[stepIndex] : null;
  const typeLabel = stepTypeLabels(t);

  // A new element in the name field; the same one keeps what is typed.
  useEffect(() => {
    setEditName(selection?.name ?? "");
    setPropsClosed(false);
    // Only a different element replaces the field's text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // The canvas was put back to a server diagram (Hylkää muutokset, Ota uudempi
  // versio, a version from the chat): the element stays selected, and the
  // field takes its name from that diagram instead of keeping what was typed.
  useEffect(() => {
    if (!nameFromCanvas.current) return;
    nameFromCanvas.current = false;
    setEditName(selection?.name ?? "");
  }, [selection]);

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
    return width >= PROPS_WIDE ? { right: 312 } : { top: 216 };
  }

  useEffect(() => {
    if (!focusRequest) return;
    const id = stepIdToBpmnId(focusRequest.stepId);
    if (!modelerRef.current?.focusElement(id, propsCover())) pendingFocus.current = id;
  }, [focusRequest]);

  function onImported() {
    const m = modelerRef.current;
    if (!m) return;
    // If nothing was selected across the import, the selection effect will not
    // run — clear the flag now so it cannot overwrite a name typed later (#234).
    if (nameFromCanvas.current && !selectionRef.current) {
      nameFromCanvas.current = false;
    }
    if (pendingFocus.current && m.focusElement(pendingFocus.current, propsCover())) pendingFocus.current = null;
    // A draft from before the tab closed: compare it with the server's diagram it was made on.
    const draft = restored.current;
    if (draft) {
      restored.current = undefined;
      import("bpmn-moddle")
        // Names as the canvas shows them, or every prefixed task would count as renamed.
        .then(({ BpmnModdle }) => new BpmnModdle().fromXML(stripTaskCodePrefixes(draft.base)))
        .then(({ rootElement }) => m.setBase(bpmnSemantics(rootElement as ModdleElement)))
        .catch(() => deleteBpmnDraft(sessionId))
        .finally(() => {
          restoring.current = false;
          setEditingEnded((n) => n + 1);
        });
    }
  }

  // Keep unsaved edits for when the tab opens again, and ask before the page closes on them.
  useEffect(() => {
    // A restored draft is still the one in store until it has been compared.
    if (restoring.current) return;
    if (edit.kind === "none") {
      deleteBpmnDraft(sessionId);
      return;
    }
    const base = propXml.current;
    modelerRef.current
      ?.saveXml()
      .then((draftXml) => {
        // Not when the edits went meanwhile (Hylkää muutokset, a save): the
        // draft would come back on the next visit to the tab.
        if (editRef.current.kind !== "none" && propXml.current === base) {
          setBpmnDraft(sessionId, { base, xml: draftXml });
        }
      })
      .catch(() => {});
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [edit, sessionId]);

  const blocked = edit.problems.unconnected.length > 0 || edit.problems.unnamed.length > 0;

  async function save({ overNewer = false }: { overNewer?: boolean } = {}) {
    const m = modelerRef.current;
    if (!m || saving.current) return;
    // Not over a blueprint that changed elsewhere, until the user has chosen.
    if ((newerXml.current || reloadingRef.current) && !overNewer) return;
    saving.current = true;
    setSaveState("saving");
    setLint({ errors: [], warnings: [] });
    const revision = m.revision();
    const sent = m.semantics();
    try {
      const body = await m.saveXml();
      const res = await fetch(`/api/sessions/${sessionId}/bpmn/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // By itself only over the version the canvas was drawn from; over a
        // newer one only by the user's choice.
        body: JSON.stringify(
          overNewer ? { xml: body } : { xml: body, base: blueprintBaseTag(canvasBlueprint.current) },
        ),
      });
      const data = (await res.json().catch(() => null)) as {
        blueprint?: Blueprint;
        xml?: string;
        lint?: {
          errors?: { rule: string; id: string; message: string }[];
          warnings?: { rule: string; id: string; message: string }[];
        };
        error?: string;
      } | null;
      const lines = (list?: { rule: string; id: string; message: string }[]) =>
        (list ?? []).map((e) => `${e.rule}${e.id ? ` (${e.id})` : ""}: ${e.message}`);

      if (res.status === 409 && (data as { error?: string } | null)?.error === BLUEPRINT_CHANGED_ELSEWHERE) {
        // A version written since the canvas was drawn: the page reads it, and
        // the newer diagram comes in as one to choose between.
        setSaveState("idle");
        router.refresh();
        return;
      }
      if (res.status === 422 && data?.error === "bpmn_lint_failed") {
        setLint({ errors: lines(data.lint?.errors), warnings: lines(data.lint?.warnings) });
        setSaveState("lint");
        return;
      }
      if (!res.ok || !data?.blueprint || !data.xml) throw new Error("sync failed");
      // The kept draft is what was saved, or it has edits made while the save
      // was on its way. Those stay, now on the diagram the server returned: the
      // tab may have been switched meanwhile, and nothing else keeps them.
      const kept = getBpmnDraft(sessionId);
      if (!kept || kept.xml === body) deleteBpmnDraft(sessionId);
      else setBpmnDraft(sessionId, { base: data.xml, xml: kept.xml });
      // Only the user's choice settles a newer diagram. One that arrived
      // while this save was on its way is still to be chosen between.
      if (overNewer) {
        newerXml.current = null;
        newerBlueprint.current = null;
        savedOverNewer.current = false;
        setChangedElsewhere(false);
      } else if (newerXml.current) {
        savedOverNewer.current = true;
      }
      onSynced({ blueprint: data.blueprint, xml: data.xml });
      setDraftPending(false);
      canvasBlueprint.current = data.blueprint;
      // The server's diagram, as the blueprint now generates it: what the
      // canvas stands on from here, also for a draft kept over a tab switch.
      propXml.current = data.xml;
      if (m.revision() === revision && !m.isEditing()) {
        setShownXml(data.xml);
        setImportKey((k) => k + 1);
      } else {
        // Editing went on during the save (a label being typed in place is no
        // command yet, so the revision does not count it): keep the canvas,
        // compared with what was saved.
        m.setBase(sent);
      }
      setSaveState("saved");
    } catch {
      setSaveState("error");
    } finally {
      saving.current = false;
    }
  }

  // A rename saves itself once the typing stops; other edits wait for "Tallenna muutokset".
  useEffect(() => {
    if (edit.kind !== "rename" || blocked || reloading || changedElsewhere) return;
    const timer = window.setTimeout(() => void save(), RENAME_SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // save reads refs and the current props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edit, blocked, reloading, changedElsewhere]);

  async function takeNewer() {
    const next = newerXml.current;
    if (!next || saving.current) return;
    setLint({ errors: [], warnings: [] });
    // A save of this canvas landed while the choice was open, so the server
    // holds the canvas's diagram: the version picked is written back first.
    // Shown without that, the canvas would show a diagram the server lacks.
    const theirs = savedOverNewer.current ? newerBlueprint.current : null;
    if (theirs) {
      saving.current = true;
      setSaveState("saving");
      try {
        const res = await fetch(`/api/sessions/${sessionId}/blueprint`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: theirs, note: "Uudempi versio otettu käyttöön Työnkulku-välilehdellä" }),
        });
        const data = (await res.json().catch(() => null)) as { blueprint?: Blueprint } | null;
        if (!res.ok || !data?.blueprint) throw new Error("save failed");
        onSynced({ blueprint: data.blueprint, xml: next });
      } catch {
        setSaveState("error");
        return;
      } finally {
        saving.current = false;
      }
    }
    setSaveState("idle");
    showServerDiagram(next);
  }
  // The choice is not offered while a save is on its way: its answer settles it.
  const choosing = changedElsewhere && saveState !== "saving";

  /** Back to the diagram last saved: the edits since then go, on the canvas and in the kept draft. */
  function discard() {
    if (saving.current) return;
    showServerDiagram(propXml.current);
  }

  /** "Lopeta muokkaus": the canvas is read-only again, as it opened. */
  function lock() {
    if (saving.current || hasOwnEdits()) return;
    setHadDraft(false);
    onLock?.();
  }

  function applyNameChange(next: string) {
    nameFromCanvas.current = false;
    setEditName(next);
    modelerRef.current?.updateSelectedName(next);
  }

  const showProps = Boolean(selection) && !propsClosed;
  const typeName = (type: string) => t.wsBpmnTypeNames[`bpmn:${type}`] ?? type;
  const problemText = edit.problems.unconnected.length
    ? fillTemplate(t.bpmnUnconnected, {
        // A task just dropped from the palette has no name: its id ("Activity_02hthtd") said nothing.
        names: edit.problems.unconnected.map((p) => p.name || t.bpmnUnnamedTask).join(", "),
      })
    : edit.problems.unnamed.length
      ? t.bpmnUnnamed
      : null;

  // The one line that says where the diagram stands; nothing when there is nothing to say.
  let status: ReactNode = null;
  if (saveState === "saving") {
    status = (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Icon name="loaderCircle" size={14} className="motion-safe:animate-spin" />
        {t.wsBpmnSaving}
      </span>
    );
  } else if (edit.kind !== "none" && problemText) {
    status = <span className="text-warning-text">{problemText}</span>;
  } else if (saveState === "lint") {
    status = <span className="text-danger-text">{t.wsBpmnLintBlocked}</span>;
  } else if (saveState === "error") {
    status = (
      <span className="inline-flex items-center gap-2 text-danger-text">
        {t.wsBpmnSaveError}
        <button
          type="button"
          className="font-medium underline underline-offset-2"
          onClick={() => void save({ overNewer: changedElsewhere })}
        >
          {t.editorRetry}
        </button>
      </span>
    );
  } else if (edit.kind === "structure") {
    status = (
      <span className="inline-flex items-center gap-1.5 text-text-secondary">
        <span className="h-2 w-2 rounded-full bg-warning-text" aria-hidden="true" />
        {t.bpmnUnsaved}
      </span>
    );
  } else if (saveState === "saved" && !choosing) {
    status = (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Icon name="check" size={14} className="text-success-text" />
        {/* When the wizard hears of it: wizard_api tells the agent with the next chat message. */}
        {t.bpmnSaved}
      </span>
    );
  } else if (update && !reloading && !draftPending && !changedElsewhere && edit.kind === "none") {
    // The canvas shows the diagram of a version written elsewhere, with nothing of the user's on it.
    status = <FlowUpdatedLine update={update} testId="bpmn-updated" t={t} />;
  }

  return (
    <section
      className="relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-border bg-surface"
      aria-label={t.wsTabFlow}
      data-testid="bpmn-panel"
      data-locked={readOnly}
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
            remove: t.bpmnPadDelete,
          }}
          onSelectionChange={setSelection}
          onEditStateChange={setEdit}
          onZoomChange={setZoom}
          onImported={onImported}
          onEditingEnd={() => setEditingEnded((n) => n + 1)}
        />

        <BpmnZoomControls
          className="absolute right-3 top-3 z-10"
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
            {readOnly ? (
              <p className="flex flex-col gap-1">
                <span className="text-xs font-medium text-text-muted">{t.wsBpmnPropertiesName}</span>
                <span
                  className="break-words text-sm font-medium text-text-strong"
                  data-testid="bpmn-property-name-text"
                >
                  {selection.name}
                </span>
              </p>
            ) : (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text-muted">{t.wsBpmnPropertiesName}</span>
                <input
                  type="text"
                  className="input-field w-full text-sm"
                  value={editName}
                  onChange={(e) => applyNameChange(e.target.value)}
                  data-testid="bpmn-property-name"
                />
              </label>
            )}
            {step && (
              <div className="mt-2.5 flex items-center justify-between gap-2">
                <span className="text-xs text-text-muted">
                  <span className="sr-only">{t.wsBpmnPropertiesType}: </span>
                  <StepTypeTag type={step.type} label={typeLabel[step.type]} />
                </span>
                <AskStepButton step={step} index={stepIndex} t={t} withLabel testId="bpmn-ask-step" />
              </div>
            )}
          </aside>
        )}

        {(status || edit.kind === "structure" || choosing || pocNoteLabel || lint.errors.length > 0) && (
          <div
            className="pop-in absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-col gap-1.5 rounded-lg border border-border bg-surface/95 px-3 py-2 text-xs shadow-sm backdrop-blur-sm sm:max-w-md"
            data-testid="bpmn-status"
          >
            {(status || edit.kind === "structure") && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5" role="status">
                {status}
                {edit.kind === "structure" && !choosing && (
                  <button
                    type="button"
                    className="btn-brand px-3 py-1 text-xs"
                    onClick={() => void save()}
                    disabled={blocked || reloading || saveState === "saving"}
                    data-testid="bpmn-save"
                  >
                    {t.wsBpmnSave}
                  </button>
                )}
                {/* The way back from an edit that cannot or should not be saved: a
                    task dropped beside the process, an emptied name, a rename the
                    validation refused. Without it the only way out was to undo each
                    step or leave the page. Not beside a rename saving itself. */}
                {edit.kind !== "none" && !choosing && (edit.kind === "structure" || saveState !== "saving") && (
                  <button
                    type="button"
                    className="btn-secondary px-3 py-1 text-xs"
                    onClick={discard}
                    disabled={saveState === "saving"}
                    data-testid="bpmn-discard"
                  >
                    {t.bpmnDiscard}
                  </button>
                )}
              </div>
            )}
            {/* The blueprint changed elsewhere under unsaved edits: which one stays is the user's call. */}
            {choosing && (
              <div
                className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-warning-text"
                role="status"
                data-testid="bpmn-changed-elsewhere"
              >
                <span className="basis-full">{t.wsJsonChangedElsewhere}</span>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1 text-xs"
                  onClick={() => void takeNewer()}
                  data-testid="bpmn-take-newer"
                >
                  {t.formTakeNewer}
                </button>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1 text-xs"
                  onClick={() => void save({ overNewer: true })}
                  disabled={blocked}
                  data-testid="bpmn-keep-mine"
                >
                  {t.formKeepMine}
                </button>
              </div>
            )}
            {lint.errors.length > 0 && (
              <ul className="max-h-32 list-disc space-y-0.5 overflow-auto pl-4 text-danger-text" role="alert">
                {lint.errors.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
            {lint.errors.length > 0 && lint.warnings.length > 0 && (
              <details className="text-text-muted">
                <summary className="cursor-pointer">{`${t.wsBpmnLintWarnings} (${lint.warnings.length})`}</summary>
                <ul className="mt-1 max-h-24 list-disc space-y-0.5 overflow-auto pl-4">
                  {lint.warnings.map((msg) => (
                    <li key={msg}>{msg}</li>
                  ))}
                </ul>
              </details>
            )}
            {/* A save writes a new blueprint version; the PoC package stays as it was. */}
            {pocNoteLabel && (
              <p className="flex items-start gap-1.5 text-text-muted" data-testid="bpmn-saved-poc-note">
                <Icon name="info" size={13} className="mt-px" />
                <span>{pocNoteLabel}</span>
              </p>
            )}
          </div>
        )}
      </div>
      {readOnly && onUnlock && <FlowLockedNote onUnlock={onUnlock} testId="bpmn" t={t} />}
      {!readOnly && (
        <FlowEditingNote
          help={t.bpmnEditHelp}
          onLock={onLock ? lock : undefined}
          lockWaits={edit.kind !== "none" || saveState === "saving"}
          testId="bpmn"
          t={t}
        />
      )}
    </section>
  );
}
