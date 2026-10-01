"use client";

// The settings of the Vision Extractor and the pieces that show its outcome. Shared by
// the Vision Extractor demo and by demos that offer vision extraction as an option.

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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api-client";
import { Info } from "lucide-react";
import { useEffect, useState } from "react";

export type VisionProvider = "openai" | "claude" | "google";
export type ReasoningEffort = "low" | "medium" | "high";

export const VISION_PROVIDERS: VisionProvider[] = [
  "openai",
  "claude",
  "google",
];

// The models come from the server's catalogue: none is named here.
export const VISION_PROVIDER_MODELS: Record<VisionProvider, readonly string[]> =
  {
    openai: [],
    claude: [],
    google: [],
  };

export interface VisionSettings {
  provider: VisionProvider;
  /** null means the provider's default model. */
  model: string | null;
  reasoningEffort: ReasoningEffort;
  mergeTable: boolean;
  additionalInstructions: string;
  includeVerification: boolean;
}

export const DEFAULT_VISION_SETTINGS: VisionSettings = {
  provider: "openai",
  model: null,
  reasoningEffort: "medium",
  mergeTable: false,
  additionalInstructions: "",
  includeVerification: false,
};

export interface VisionModelCatalogue {
  choices: Record<VisionProvider, readonly string[]>;
  defaultModel: string | null;
}

/** The models the server offers for each provider, with the bundled list as fallback. */
export function useVisionModels(): VisionModelCatalogue {
  const [catalogue, setCatalogue] = useState<VisionModelCatalogue>({
    choices: VISION_PROVIDER_MODELS,
    defaultModel: null,
  });

  useEffect(() => {
    let active = true;
    void apiFetch("/api/extract-vision/models")
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!active || !body?.models) return;
        const valid = VISION_PROVIDERS.every(
          (name) =>
            Array.isArray(body.models[name]) &&
            body.models[name].length > 0 &&
            body.models[name].every(
              (value: unknown) => typeof value === "string",
            ),
        );
        if (!valid) return;
        setCatalogue({
          choices: body.models,
          defaultModel: typeof body.default === "string" ? body.default : null,
        });
      })
      .catch(() => {
        /* Keep the bundled suggestions if the catalogue is unavailable. */
      });
    return () => {
      active = false;
    };
  }, []);

  return catalogue;
}

/** The model to use: the chosen one, else the default of the provider, else none. */
export function resolveVisionModel(
  settings: VisionSettings,
  catalogue: VisionModelCatalogue,
): string {
  if (settings.model) return settings.model;
  if (settings.provider === "openai" && catalogue.defaultModel)
    return catalogue.defaultModel;
  return catalogue.choices[settings.provider][0] ?? "";
}

/** Adds the settings to the request of POST /api/extract-vision. */
export function appendVisionSettings(
  formData: FormData,
  settings: VisionSettings,
  model: string,
): void {
  formData.append("model_provider", settings.provider);
  // With no model the server uses its own.
  if (model) formData.append("model", model);
  formData.append("reasoning_effort", settings.reasoningEffort);
  formData.append("merge_table", settings.mergeTable ? "true" : "false");
  formData.append("additional_instructions", settings.additionalInstructions);
  formData.append(
    "include_verification",
    settings.includeVerification ? "true" : "false",
  );
}

export function HelpTooltip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="More information"
          className="text-muted-foreground hover:text-foreground inline-flex"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-72">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

/** Provider, model, reasoning effort, table merging, instructions and verification. */
export function VisionSettingsFields({
  settings,
  catalogue,
  disabled,
  idPrefix = "vision",
  onChange,
}: {
  settings: VisionSettings;
  catalogue: VisionModelCatalogue;
  disabled: boolean;
  idPrefix?: string;
  onChange: (next: VisionSettings) => void;
}) {
  const set = (patch: Partial<VisionSettings>) =>
    onChange({ ...settings, ...patch });
  const model = resolveVisionModel(settings, catalogue);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${idPrefix}-provider`}>Model Provider</Label>
          <HelpTooltip text="Selects the service used for the document extraction call. OpenAI / Azure automatically uses Azure when Azure credentials are configured; Claude and Google use their configured provider credentials." />
        </div>
        <Select
          value={settings.provider}
          onValueChange={(value) =>
            set({ provider: value as VisionProvider, model: null })
          }
          disabled={disabled}
        >
          <SelectTrigger id={`${idPrefix}-provider`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="openai">OpenAI / Azure</SelectItem>
            <SelectItem value="claude">Claude</SelectItem>
            <SelectItem value="google">Google</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${idPrefix}-model`}>Extraction Model</Label>
          <HelpTooltip text="Selects the model or deployment used to read the uploaded documents. Available choices are limited to the selected provider." />
        </div>
        <Select
          value={model}
          onValueChange={(value) => set({ model: value })}
          disabled={disabled}
        >
          <SelectTrigger id={`${idPrefix}-model`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {catalogue.choices[settings.provider].map((modelName) => (
              <SelectItem key={modelName} value={modelName}>
                {modelName}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${idPrefix}-reasoning-effort`}>
            Reasoning Effort
          </Label>
          <HelpTooltip text="Controls how much reasoning the model uses. Higher effort can improve difficult cross-document matching but usually increases latency and token usage." />
        </div>
        <Select
          value={settings.reasoningEffort}
          onValueChange={(value) =>
            set({ reasoningEffort: value as ReasoningEffort })
          }
          disabled={disabled}
        >
          <SelectTrigger id={`${idPrefix}-reasoning-effort`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="high">High</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${idPrefix}-merge-table`}>Merge Split Tables</Label>
          <HelpTooltip text="Adds an instruction to combine a table that continues across pages into one logical table." />
        </div>
        <div className="flex h-9 items-center gap-3 rounded-md border px-3">
          <Switch
            id={`${idPrefix}-merge-table`}
            checked={settings.mergeTable}
            onCheckedChange={(checked) => set({ mergeTable: checked })}
            disabled={disabled}
          />
          <span className="text-muted-foreground text-sm">
            {settings.mergeTable ? "Merge tables" : "Off"}
          </span>
        </div>
      </div>

      <div className="space-y-2 sm:col-span-2">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${idPrefix}-additional-instructions`}>
            Additional Instructions
          </Label>
          <HelpTooltip text="Appended to the extraction prompt to guide how values are read. To add or remove output fields, edit the extraction task and generate a new schema instead." />
        </div>
        <Textarea
          id={`${idPrefix}-additional-instructions`}
          value={settings.additionalInstructions}
          onChange={(event) =>
            set({ additionalInstructions: event.target.value })
          }
          placeholder="Optional guidance, e.g. prefer the value in the final totals table."
          disabled={disabled}
          rows={3}
        />
      </div>

      <div className="space-y-2 sm:col-span-2">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${idPrefix}-verification`}>
            Per-field Verification
          </Label>
          <HelpTooltip text="Adds a confidence score and explanation for each scalar field. This improves reviewability but uses more output tokens and may take longer." />
        </div>
        <div className="flex h-9 items-center gap-3 rounded-md border px-3">
          <Switch
            id={`${idPrefix}-verification`}
            checked={settings.includeVerification}
            onCheckedChange={(checked) => set({ includeVerification: checked })}
            disabled={disabled}
          />
          <span className="text-muted-foreground text-sm">
            {settings.includeVerification ? "Show confidence" : "Off"}
          </span>
        </div>
      </div>
    </div>
  );
}

export interface VerificationEntry {
  value: unknown;
  confidence_score?: number;
  confidence_reason?: string;
}

export interface VisionUsage {
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  thinking_tokens?: number | null;
  total_tokens?: number | null;
  cost_usd?: number | null;
}

/** The tokens and cost of a vision extraction. */
export function UsageStats({ usage }: { usage: VisionUsage }) {
  const stats: Array<{ label: string; value: string; bold?: boolean }> = [];
  if (usage.total_tokens != null) {
    stats.push({
      label: "Tokens",
      value: usage.total_tokens.toLocaleString(),
      bold: true,
    });
  }
  if (usage.input_tokens != null) {
    stats.push({ label: "Input", value: usage.input_tokens.toLocaleString() });
  }
  if (usage.output_tokens != null) {
    stats.push({
      label: "Output",
      value: usage.output_tokens.toLocaleString(),
    });
  }
  if (usage.cost_usd != null) {
    stats.push({
      label: "Cost",
      value: `$${usage.cost_usd.toFixed(4)}`,
      bold: true,
    });
  }

  if (stats.length === 0) return null;

  return (
    <div className="bg-muted/40 mb-4 grid grid-cols-2 gap-2 rounded-md border p-3 text-xs sm:grid-cols-4">
      {stats.map((stat) => (
        <div key={stat.label}>
          <p className="text-muted-foreground">{stat.label}</p>
          <p className={`font-mono ${stat.bold ? "font-medium" : ""}`}>
            {stat.value}
          </p>
        </div>
      ))}
    </div>
  );
}
