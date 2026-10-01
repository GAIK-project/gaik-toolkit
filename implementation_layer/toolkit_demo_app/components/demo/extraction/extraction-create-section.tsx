"use client";

import { FileUpload } from "@/components/demo/file-upload";
import { SectionGuide } from "@/components/demo/section-guide";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import {
  Camera,
  ClipboardPaste,
  FileCode2,
  FileUp,
  Keyboard,
  Loader2,
  Mic,
  Plus,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import type { ExtractionConfig } from "./config";
import { ExtractionResults } from "./extraction-results";
import { RunProgress } from "./run-progress";
import { SchemaPanel } from "./schema-panel";
import { useSessionSchema } from "./use-session-schema";
import {
  useExtractionPipeline,
  type ExtractionInput,
} from "./use-extraction-pipeline";
import type { OwnField } from "./config";

type InputMode = "text" | "audio" | "photo";
type PromptTab = "fields" | "edit" | "own";

const INPUT_MODES: { id: InputMode; label: string; icon: typeof Mic }[] = [
  { id: "text", label: "Text", icon: Keyboard },
  { id: "audio", label: "Audio recording", icon: Mic },
  { id: "photo", label: "Photo or scan", icon: Camera },
];

function SectionTitle({ n, children }: { n: number; children: string }) {
  return (
    <h3 className="flex items-center gap-2 text-sm font-semibold">
      <span className="bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-full text-xs">
        {n}
      </span>
      {children}
    </h3>
  );
}

export function ExtractionCreateSection({ demo }: { demo: ExtractionConfig }) {
  const [mode, setMode] = useState<InputMode>("text");
  const [text, setText] = useState("");
  const [audio, setAudio] = useState<File | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);

  const [tab, setTab] = useState<PromptTab>("fields");
  const [selected, setSelected] = useState<string[]>(demo.defaultFieldIds);
  const [own, setOwn] = useState<OwnField[]>([]);
  const [edited, setEdited] = useState<string | null>(null);
  const [ownPrompt, setOwnPrompt] = useState("");
  const [language, setLanguage] = useState<string>(demo.languages[0]);
  const [enhanced, setEnhanced] = useState(demo.enhancedDefault);
  const [generatePdf, setGeneratePdf] = useState(true);

  const pipeline = useExtractionPipeline(demo);

  const fieldsPrompt = demo.composePrompt(selected, own);
  const basePrompt =
    tab === "fields"
      ? fieldsPrompt
      : tab === "edit"
        ? (edited ?? fieldsPrompt)
        : ownPrompt;
  const prompt = demo.withLanguage(basePrompt, language);
  const fieldCount = selected.length + own.filter((f) => f.name.trim()).length;
  const promptReady =
    tab === "own"
      ? ownPrompt.trim().length > 0
      : tab === "edit" || fieldCount > 0;

  const sessionSchema = useSessionSchema(prompt);

  const input: ExtractionInput | null =
    mode === "text" && text.trim()
      ? { kind: "text", text }
      : mode === "audio" && audio
        ? { kind: "audio", file: audio }
        : mode === "photo" && photo
          ? { kind: "photo", file: photo }
          : null;

  const config = () => ({
    prompt,
    schemaKey: null,
    schemaId: sessionSchema.schema?.id ?? null,
    enhanced,
    generatePdf,
  });

  const toggleField = (id: string) =>
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );

  const updateOwn = (index: number, patch: Partial<OwnField>) =>
    setOwn((current) =>
      current.map((field, i) => (i === index ? { ...field, ...patch } : field)),
    );

  const useExample = async () => {
    pipeline.reset();
    if (mode === "text") {
      setText(demo.sampleText);
    } else if (mode === "audio") {
      try {
        const response = await fetch(demo.sampleAudioUrl);
        if (!response.ok) throw new Error("Could not load the example audio");
        const blob = await response.blob();
        setAudio(
          new File([blob], demo.sampleAudioUrl.split("/").pop() ?? "sample", {
            type: blob.type || "audio/mp4",
          }),
        );
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed");
      }
    }
  };

  const reset = () => {
    pipeline.reset();
    setText("");
    setAudio(null);
    setPhoto(null);
    setSelected(demo.defaultFieldIds);
    setOwn([]);
    setEdited(null);
    setOwnPrompt("");
    setLanguage(demo.languages[0]);
    sessionSchema.clear();
  };

  const canExtract = Boolean(input) && promptReady && sessionSchema.isCurrent;

  const extract = () => {
    if (!input || !canExtract) return;
    void pipeline.run(input, config());
  };

  const busy = pipeline.isLoading;
  const working = busy || sessionSchema.isGenerating;
  const hint = !promptReady
    ? "Choose at least one field, or write a prompt."
    : !sessionSchema.isCurrent
      ? sessionSchema.schema
        ? "The prompt changed. Regenerate the schema first."
        : "Generate the schema first."
      : !input
        ? "Add a report to extract from."
        : "Ready. The report is read with the schema above.";

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to test your own use case"
        steps={demo.createGuide.steps}
        notes={demo.createGuide.notes}
      />

      <Card className="border-primary/30 scroll-mt-24 border-2">
        <CardContent className="space-y-8 pt-6">
          <CardDescription className="text-base">
            {demo.createGuide.intro}
          </CardDescription>

          {/* 1. The report */}
          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <SectionTitle n={1}>Add a report</SectionTitle>
              {mode !== "photo" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={useExample}
                  disabled={busy}
                >
                  <ClipboardPaste className="size-4" />
                  Use example
                </Button>
              )}
            </div>
            <ToggleGroup
              type="single"
              value={mode}
              onValueChange={(value) => value && setMode(value as InputMode)}
              className="flex-wrap justify-start"
              aria-label="Kind of report"
            >
              {INPUT_MODES.filter(
                (m) => demo.allowPhoto || m.id !== "photo",
              ).map(({ id, label, icon: Icon }) => (
                <ToggleGroupItem key={id} value={id} className="gap-2 px-4">
                  <Icon className="size-4" />
                  {label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>

            {mode === "text" && (
              <div className="space-y-1">
                <Textarea
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder={demo.textPlaceholder}
                  rows={9}
                  maxLength={20000}
                  disabled={busy}
                  aria-label="Report text"
                />
                {text && (
                  <button
                    type="button"
                    onClick={() => setText("")}
                    className="text-muted-foreground text-xs hover:underline"
                  >
                    Clear text
                  </button>
                )}
              </div>
            )}
            {mode === "audio" && (
              <FileUpload
                accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
                maxSize={50}
                file={audio}
                onFileSelect={setAudio}
                onFileRemove={() => setAudio(null)}
                disabled={busy}
              />
            )}
            {mode === "photo" && (
              <div className="space-y-2">
                <FileUpload
                  accept=".jpg,.jpeg,.png,.webp,.pdf"
                  maxSize={20}
                  file={photo}
                  onFileSelect={setPhoto}
                  onFileRemove={() => setPhoto(null)}
                  disabled={busy}
                />
                <p className="text-muted-foreground text-xs">
                  Read with vision extraction, which suits photos, scans and
                  handwritten or stamped forms. Up to 20 MB.
                </p>
              </div>
            )}
          </section>

          {/* 2. What to extract */}
          <section className="space-y-3">
            <SectionTitle n={2}>What to extract</SectionTitle>
            <Tabs
              value={tab}
              onValueChange={(value) => setTab(value as PromptTab)}
            >
              <TabsList className="h-auto w-full flex-wrap justify-start">
                <TabsTrigger value="fields">Choose fields</TabsTrigger>
                <TabsTrigger value="edit">
                  Edit the extraction prompt
                </TabsTrigger>
                <TabsTrigger value="own">
                  Create your own extraction prompt
                </TabsTrigger>
              </TabsList>

              <TabsContent value="fields" className="space-y-4 pt-3">
                {(["core", "extra"] as const).map((group) => (
                  <div key={group} className="space-y-2">
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      {group === "core"
                        ? "Standard fields"
                        : "Analysis fields (the model judges these)"}
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {demo.fields
                        .filter((f) => f.group === group)
                        .map((field) => {
                          const on = selected.includes(field.id);
                          return (
                            <label
                              key={field.id}
                              className={cn(
                                "flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 text-sm transition-colors",
                                on
                                  ? "border-primary/50 bg-primary/5"
                                  : "hover:border-primary/30",
                              )}
                            >
                              <input
                                type="checkbox"
                                checked={on}
                                onChange={() => toggleField(field.id)}
                                disabled={busy}
                                className="accent-primary mt-1"
                              />
                              <span>
                                <span className="block font-medium">
                                  {field.label}
                                </span>
                                <span className="text-muted-foreground block text-xs">
                                  {field.meaning}
                                </span>
                              </span>
                            </label>
                          );
                        })}
                    </div>
                  </div>
                ))}

                <div className="space-y-2">
                  <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                    Your own fields
                  </p>
                  {own.map((field, index) => (
                    <div key={index} className="flex gap-2">
                      <Input
                        value={field.name}
                        onChange={(event) =>
                          updateOwn(index, { name: event.target.value })
                        }
                        placeholder="Field, e.g. Shift"
                        maxLength={60}
                        aria-label={`Own field ${index + 1} name`}
                        className="sm:max-w-56"
                      />
                      <Input
                        value={field.meaning}
                        onChange={(event) =>
                          updateOwn(index, { meaning: event.target.value })
                        }
                        placeholder="What it means (optional)"
                        maxLength={200}
                        aria-label={`Own field ${index + 1} meaning`}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Remove field"
                        onClick={() =>
                          setOwn((current) =>
                            current.filter((_, i) => i !== index),
                          )
                        }
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={own.length >= demo.maxOwnFields}
                    onClick={() =>
                      setOwn((current) => [
                        ...current,
                        { name: "", meaning: "" },
                      ])
                    }
                  >
                    <Plus className="size-4" />
                    Add field
                  </Button>
                </div>
              </TabsContent>

              <TabsContent value="edit" className="space-y-2 pt-3">
                <p className="text-muted-foreground text-sm">
                  This is the prompt built from your chosen fields. Change any
                  part of it.
                </p>
                <Textarea
                  value={edited ?? fieldsPrompt}
                  onChange={(event) => setEdited(event.target.value)}
                  rows={11}
                  maxLength={demo.maxPromptChars}
                  disabled={busy}
                  className="font-mono text-sm"
                  aria-label="Extraction prompt"
                />
                {edited !== null && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEdited(null)}
                  >
                    <RotateCcw className="size-4" />
                    Reset to the chosen fields
                  </Button>
                )}
              </TabsContent>

              <TabsContent value="own" className="space-y-2 pt-3">
                <p className="text-muted-foreground text-sm">
                  Write the whole prompt yourself: what to extract and how.
                </p>
                <Textarea
                  value={ownPrompt}
                  onChange={(event) => setOwnPrompt(event.target.value)}
                  placeholder={demo.ownPromptPlaceholder}
                  rows={9}
                  maxLength={demo.maxPromptChars}
                  disabled={busy}
                  className="font-mono text-sm"
                  aria-label="Your own extraction prompt"
                />
                <p className="text-muted-foreground text-right text-xs">
                  {ownPrompt.length} / {demo.maxPromptChars}
                </p>
              </TabsContent>
            </Tabs>
          </section>

          {/* 3. Options */}
          <section className="space-y-4">
            <SectionTitle n={3}>Options</SectionTitle>
            <div className="space-y-2">
              <Label>Language of the extracted values</Label>
              <ToggleGroup
                type="single"
                value={language}
                onValueChange={(value) => value && setLanguage(value)}
                className="flex-wrap justify-start"
                aria-label="Language of the extracted values"
              >
                {demo.languages.map((item) => (
                  <ToggleGroupItem key={item} value={item} className="px-3">
                    {item}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {mode === "audio" && (
                <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
                  <div>
                    <Label htmlFor="extraction-enhanced">
                      Enhanced transcript
                    </Label>
                    <p className="text-muted-foreground text-xs">
                      {demo.enhancedHint}
                    </p>
                  </div>
                  <Switch
                    id="extraction-enhanced"
                    checked={enhanced}
                    onCheckedChange={setEnhanced}
                    disabled={busy}
                  />
                </div>
              )}
              <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
                <div>
                  <Label htmlFor="extraction-pdf">Create a PDF report</Label>
                  <p className="text-muted-foreground text-xs">
                    Preview it and download it with the result
                  </p>
                </div>
                <Switch
                  id="extraction-pdf"
                  checked={generatePdf}
                  onCheckedChange={setGeneratePdf}
                  disabled={busy}
                />
              </div>
            </div>
          </section>

          {/* 4. The schema */}
          <section className="space-y-3">
            <SectionTitle n={4}>Generate the schema</SectionTitle>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant={sessionSchema.isCurrent ? "outline" : "default"}
                onClick={() => void sessionSchema.generate()}
                disabled={working || !promptReady}
              >
                {sessionSchema.isGenerating ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <FileCode2 className="size-4" />
                )}
                {sessionSchema.isGenerating
                  ? "Generating..."
                  : sessionSchema.schema
                    ? "Regenerate schema"
                    : "Generate schema"}
              </Button>
              <p className="text-muted-foreground text-sm">
                The schema is made from the prompt above and kept for this
                session only.
              </p>
            </div>
            <SchemaPanel
              fields={sessionSchema.schema?.fields ?? null}
              isCurrent={sessionSchema.isCurrent}
            />
          </section>

          <div className="flex flex-wrap items-center gap-3 border-t pt-4">
            <Button
              size="lg"
              onClick={extract}
              disabled={working || !canExtract}
            >
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {busy ? "Processing..." : "Extract"}
            </Button>
            <Button
              variant="outline"
              size="lg"
              onClick={reset}
              disabled={working}
            >
              <RotateCcw className="size-4" />
              Reset
            </Button>
            <p className="text-muted-foreground text-sm">{hint}</p>
          </div>
        </CardContent>
      </Card>

      {busy && <RunProgress steps={pipeline.steps} />}
      {pipeline.result && !busy && (
        <ExtractionResults
          config={demo}
          result={pipeline.result}
          seconds={pipeline.seconds}
          busy={busy}
          onRerun={(edit) => {
            if (!sessionSchema.isCurrent) {
              toast.error("Regenerate the schema first, then extract again.");
              return;
            }
            void pipeline.run({ kind: "text", text: edit }, config());
          }}
        />
      )}
    </div>
  );
}
