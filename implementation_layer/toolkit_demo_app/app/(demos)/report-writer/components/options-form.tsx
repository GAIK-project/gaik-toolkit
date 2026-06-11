"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

export interface ReportOptions {
  // Parsing
  parserChoice: string;
  // Transcription
  transcriptionModel: string;
  language: string;
  enhancedTranscript: boolean;
  diarization: boolean;
  speakerCount: string;
  initialPrompt: string;
  // Images
  imageMode: string;
  imageRequirements: string;
  // Writer
  writerModel: string;
  temperature: number;
  reasoningEffort: string;
  // Agentic
  agentic: boolean;
  curate: boolean;
  polish: boolean;
  strictReview: boolean;
  reviewModel: string;
  // Output
  reportLanguage: string;
  includeSourceRefs: boolean;
  outputDocx: boolean;
  maxEvidenceChars: string;
}

interface OptionsFormProps {
  options: ReportOptions;
  onChange: (patch: Partial<ReportOptions>) => void;
  disabled?: boolean;
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <Label className="text-sm shrink-0">{label}</Label>
      <div className="flex-1 max-w-[55%]">{children}</div>
    </div>
  );
}

function SwitchRow({
  label,
  checked,
  onCheckedChange,
  disabled,
  description,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  disabled?: boolean;
  description?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <Label className="text-sm">{label}</Label>
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        )}
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
    </div>
  );
}

export function OptionsForm({ options, onChange, disabled }: OptionsFormProps) {
  const set = (patch: Partial<ReportOptions>) => onChange(patch);

  return (
    <Accordion type="multiple" className="space-y-1">
      {/* Parsing */}
      <AccordionItem value="parsing" className="border rounded-lg px-3">
        <AccordionTrigger className="text-sm py-3 hover:no-underline">
          Parsing Options
        </AccordionTrigger>
        <AccordionContent className="space-y-3 pb-3">
          <Row label="PDF parser">
            <Select
              value={options.parserChoice}
              onValueChange={(v) => set({ parserChoice: v })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">auto (PyMuPDF)</SelectItem>
                <SelectItem value="pymupdf">pymupdf</SelectItem>
                <SelectItem value="vision">vision</SelectItem>
                <SelectItem value="multimodal">multimodal</SelectItem>
                <SelectItem value="docling">docling</SelectItem>
              </SelectContent>
            </Select>
          </Row>
        </AccordionContent>
      </AccordionItem>

      {/* Transcription */}
      <AccordionItem value="transcription" className="border rounded-lg px-3">
        <AccordionTrigger className="text-sm py-3 hover:no-underline">
          Transcription Options
        </AccordionTrigger>
        <AccordionContent className="space-y-3 pb-3">
          <Row label="Model">
            <Select
              value={options.transcriptionModel || "default"}
              onValueChange={(v) =>
                set({ transcriptionModel: v === "default" ? "" : v })
              }
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">default (from config)</SelectItem>
                <SelectItem value="gpt-4o-transcribe">gpt-4o-transcribe</SelectItem>
                <SelectItem value="whisper-1">whisper-1</SelectItem>
              </SelectContent>
            </Select>
          </Row>
          <Row label="Language">
            <Input
              placeholder="auto-detect"
              value={options.language}
              onChange={(e) => set({ language: e.target.value })}
              disabled={disabled}
              className="h-8 text-sm"
            />
          </Row>
          <SwitchRow
            label="Enhanced transcript"
            description="Second LLM pass to fix transcription errors"
            checked={options.enhancedTranscript}
            onCheckedChange={(v) => set({ enhancedTranscript: v })}
            disabled={disabled}
          />
          <SwitchRow
            label="Speaker diarization"
            description="Label individual speakers"
            checked={options.diarization}
            onCheckedChange={(v) => set({ diarization: v })}
            disabled={disabled}
          />
          {options.diarization && (
            <Row label="Speaker count">
              <Input
                type="number"
                placeholder="auto"
                value={options.speakerCount}
                onChange={(e) => set({ speakerCount: e.target.value })}
                disabled={disabled}
                className="h-8 text-sm"
                min={1}
              />
            </Row>
          )}
          <div className="space-y-1">
            <Label className="text-sm">Context hint</Label>
            <Textarea
              placeholder="e.g. Q2 product planning meeting"
              value={options.initialPrompt}
              onChange={(e) => set({ initialPrompt: e.target.value })}
              disabled={disabled}
              className="text-sm min-h-[56px] resize-none"
            />
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* Images */}
      <AccordionItem value="images" className="border rounded-lg px-3">
        <AccordionTrigger className="text-sm py-3 hover:no-underline">
          Image Options
        </AccordionTrigger>
        <AccordionContent className="space-y-3 pb-3">
          <Row label="Mode">
            <Select
              value={options.imageMode}
              onValueChange={(v) => set({ imageMode: v })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="parse">parse (general text/content)</SelectItem>
                <SelectItem value="structured">structured (field extraction)</SelectItem>
              </SelectContent>
            </Select>
          </Row>
          {options.imageMode === "structured" && (
            <div className="space-y-1">
              <Label className="text-sm">Extraction requirements</Label>
              <Textarea
                placeholder="e.g. Extract all measurements and labels."
                value={options.imageRequirements}
                onChange={(e) => set({ imageRequirements: e.target.value })}
                disabled={disabled}
                className="text-sm min-h-[56px] resize-none"
              />
            </div>
          )}
        </AccordionContent>
      </AccordionItem>

      {/* Writer */}
      <AccordionItem value="writer" className="border rounded-lg px-3">
        <AccordionTrigger className="text-sm py-3 hover:no-underline">
          Writer Options
        </AccordionTrigger>
        <AccordionContent className="space-y-3 pb-3">
          <Row label="Model">
            <Input
              placeholder="gpt-5.4"
              value={options.writerModel}
              onChange={(e) => set({ writerModel: e.target.value })}
              disabled={disabled}
              className="h-8 text-sm font-mono"
            />
          </Row>
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-sm">Temperature</Label>
              <span className="text-xs text-muted-foreground">{options.temperature}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={options.temperature}
              onChange={(e) => set({ temperature: parseFloat(e.target.value) })}
              disabled={disabled}
              className="w-full accent-primary"
            />
          </div>
          <Row label="Reasoning effort">
            <Select
              value={options.reasoningEffort || "none"}
              onValueChange={(v) => set({ reasoningEffort: v === "none" ? "" : v })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">not set</SelectItem>
                <SelectItem value="low">low</SelectItem>
                <SelectItem value="medium">medium</SelectItem>
                <SelectItem value="high">high</SelectItem>
              </SelectContent>
            </Select>
          </Row>
        </AccordionContent>
      </AccordionItem>

      {/* Agentic */}
      <AccordionItem value="agentic" className="border rounded-lg px-3">
        <AccordionTrigger className="text-sm py-3 hover:no-underline">
          Agentic Workflow
        </AccordionTrigger>
        <AccordionContent className="space-y-3 pb-3">
          <SwitchRow
            label="Agentic mode"
            description="Per-section drafting with mandatory reviewer repair"
            checked={options.agentic}
            onCheckedChange={(v) => set({ agentic: v })}
            disabled={disabled}
          />
          {options.agentic && (
            <>
              <SwitchRow
                label="Curate evidence"
                description="Section-specific evidence brief before drafting"
                checked={options.curate}
                onCheckedChange={(v) => set({ curate: v })}
                disabled={disabled}
              />
              <SwitchRow
                label="Polish"
                description="Final style/proofreading pass after reviewer repair"
                checked={options.polish}
                onCheckedChange={(v) => set({ polish: v })}
                disabled={disabled}
              />
              <SwitchRow
                label="Strict review"
                description="Raise instead of continuing when reviewer edits can't be applied"
                checked={options.strictReview}
                onCheckedChange={(v) => set({ strictReview: v })}
                disabled={disabled}
              />
              <Row label="Reviewer model">
                <Input
                  placeholder="same as writer"
                  value={options.reviewModel}
                  onChange={(e) => set({ reviewModel: e.target.value })}
                  disabled={disabled}
                  className="h-8 text-sm font-mono"
                />
              </Row>
            </>
          )}
        </AccordionContent>
      </AccordionItem>

      {/* Output */}
      <AccordionItem value="output" className="border rounded-lg px-3">
        <AccordionTrigger className="text-sm py-3 hover:no-underline">
          Output Options
        </AccordionTrigger>
        <AccordionContent className="space-y-3 pb-3">
          <Row label="Language">
            <Input
              placeholder="English"
              value={options.reportLanguage}
              onChange={(e) => set({ reportLanguage: e.target.value })}
              disabled={disabled}
              className="h-8 text-sm"
            />
          </Row>
          <SwitchRow
            label="Include source references"
            description="Cite filenames inline (auto-off for single-source)"
            checked={options.includeSourceRefs}
            onCheckedChange={(v) => set({ includeSourceRefs: v })}
            disabled={disabled}
          />
          <SwitchRow
            label="Generate DOCX"
            description="Requires Pandoc system binary"
            checked={options.outputDocx}
            onCheckedChange={(v) => set({ outputDocx: v })}
            disabled={disabled}
          />
          <Row label="Max evidence chars">
            <Input
              type="number"
              placeholder="no limit"
              value={options.maxEvidenceChars}
              onChange={(e) => set({ maxEvidenceChars: e.target.value })}
              disabled={disabled}
              className="h-8 text-sm"
            />
          </Row>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
