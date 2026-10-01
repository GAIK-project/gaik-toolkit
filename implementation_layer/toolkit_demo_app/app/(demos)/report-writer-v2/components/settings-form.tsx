"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  ModelKey,
  RunSettings,
  StepKey,
} from "@/lib/report-writer/workspace";

import { Row, SwitchRow } from "../../report-writer/components/options-form";

const EFFORTS = ["none", "low", "medium", "high", "xhigh", "max"];

interface SettingsFormProps {
  models: Record<ModelKey, string | null>;
  onModelsChange: (models: Record<ModelKey, string | null>) => void;
  settings: RunSettings;
  onSettingsChange: (settings: RunSettings) => void;
  disabled?: boolean;
}

export function SettingsForm({
  models,
  onModelsChange,
  settings,
  onSettingsChange,
  disabled,
}: SettingsFormProps) {
  const set = (patch: Partial<RunSettings>) =>
    onSettingsChange({ ...settings, ...patch });

  const model = (key: ModelKey, label = "Model") => (
    <Row label={label}>
      <Input
        placeholder="server default"
        value={models[key] ?? ""}
        onChange={(e) =>
          onModelsChange({ ...models, [key]: e.target.value || null })
        }
        disabled={disabled}
        className="h-8 font-mono text-sm"
      />
    </Row>
  );

  const count = (key: "curator_workers" | "review_attempts") => (
    <Input
      type="number"
      min={1}
      step={1}
      value={settings[key]}
      onChange={(e) => set({ [key]: Number(e.target.value) })}
      disabled={disabled}
      className="h-8 text-sm"
    />
  );

  const step = (key: StepKey) => {
    const opts = settings[key];
    const effort = opts.reasoning_effort ?? "default";
    return (
      <>
        <Row label="Reasoning effort">
          <Select
            value={effort}
            onValueChange={(v) =>
              set({
                [key]: {
                  ...opts,
                  reasoning_effort: v === "default" ? null : v,
                },
              })
            }
            disabled={disabled}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[...new Set(["default", ...EFFORTS, effort])].map((v) => (
                <SelectItem key={v} value={v}>
                  {v === "default" ? "model default" : v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Row>
        <Row label="Temperature">
          <Input
            type="number"
            min={0}
            max={2}
            step={0.1}
            placeholder="model default"
            value={opts.temperature ?? ""}
            onChange={(e) =>
              set({
                [key]: {
                  ...opts,
                  temperature:
                    e.target.value === "" ? null : Number(e.target.value),
                },
              })
            }
            disabled={disabled}
            className="h-8 text-sm"
          />
        </Row>
      </>
    );
  };

  const panel = (value: string, title: string, children: React.ReactNode) => (
    <AccordionItem value={value} className="rounded-lg border px-3">
      <AccordionTrigger className="py-3 text-sm hover:no-underline">
        {title}
      </AccordionTrigger>
      <AccordionContent className="space-y-3 pb-3">{children}</AccordionContent>
    </AccordionItem>
  );

  const language = settings.transcription_language;

  return (
    <Accordion type="multiple" className="space-y-1">
      {panel(
        "normalize",
        "1. Normalize",
        <>
          {model("vision", "Vision model")}
          {model("transcription", "Transcription model")}
          <Row label="Transcription language">
            <Select
              value={language}
              onValueChange={(v) => set({ transcription_language: v })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[...new Set(["auto", "en", "fi", language])].map((v) => (
                  <SelectItem key={v} value={v}>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </>,
      )}
      {panel(
        "curate",
        "2. Curate",
        <>
          {model("curator")}
          {step("curator")}
          <Row label="Parallel sections">{count("curator_workers")}</Row>
        </>,
      )}
      {panel(
        "synthesize",
        "3. Synthesize",
        <>
          <p className="text-muted-foreground text-xs font-medium">Writer</p>
          {model("writer")}
          {step("writer")}
          <p className="text-muted-foreground text-xs font-medium">Reviewer</p>
          {model("reviewer")}
          {step("reviewer")}
          <Row label="Review attempts">{count("review_attempts")}</Row>
          <SwitchRow
            label="Citations"
            description="Cite the source file and place of each fact. Off writes plain statements, even if the report instructions ask for citations"
            checked={settings.citations}
            onCheckedChange={(v) => set({ citations: v })}
            disabled={disabled}
          />
          <SwitchRow
            label="Strict review"
            description="Fail the stage when a reviewer edit can't be applied"
            checked={settings.strict_review}
            onCheckedChange={(v) => set({ strict_review: v })}
            disabled={disabled}
          />
          <p className="text-muted-foreground text-xs">
            GPT-6 models ignore temperature unless reasoning effort is none.
          </p>
        </>,
      )}
      {panel(
        "output",
        "Output",
        <SwitchRow
          label="Generate DOCX"
          description="Also write report.docx next to report.md"
          checked={settings.docx}
          onCheckedChange={(v) => set({ docx: v })}
          disabled={disabled}
        />,
      )}
    </Accordion>
  );
}
