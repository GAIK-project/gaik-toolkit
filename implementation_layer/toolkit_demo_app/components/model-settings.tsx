"use client";

import { useEffect, useRef, useState, type ComponentType } from "react";
import { usePathname } from "next/navigation";
import { KeyRound, Loader2, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Azure } from "@/components/ui/svgs/azure";
import { Openai } from "@/components/ui/svgs/openai";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch } from "@/lib/api-client";
import {
  MODEL_SETTINGS_HEADER,
  encodeModelSettings,
  pageUsesModelSettings,
  type ModelProvider,
  type ModelSettings,
} from "@/lib/model-settings";
import { setModelSettings, useModelSettings } from "@/lib/model-settings-store";

const LABELS = { openai: "OpenAI", azure: "Azure OpenAI", aitta: "CSC Aitta" };
const CUSTOM = "__custom__";

type Preset = { id: string; label: string; note?: string };
const GPT_PRESETS: Preset[] = [
  { id: "gpt-6-luna", label: "GPT-6 Luna", note: "default" },
  { id: "gpt-6-sol", label: "GPT-6 Sol" },
  { id: "gpt-6-astra", label: "GPT-6 Astra" },
  { id: "gpt-5.6-terra", label: "GPT-5.6 Terra" },
];
// Azure deployment names are chosen per resource; these match the model names.
const PRESETS: Record<ModelProvider, Preset[]> = {
  openai: GPT_PRESETS,
  azure: GPT_PRESETS,
  aitta: [
    { id: "google/gemma-4-31b-it", label: "Gemma 4 31B", note: "tested" },
    {
      id: "LumiOpen/Llama-Poro-2-70B-Instruct",
      label: "Poro 2 70B",
      note: "Finnish, simple schemas",
    },
  ],
};

const PROVIDERS: {
  id: ModelProvider;
  label: string;
  Icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
}[] = [
  { id: "openai", label: "OpenAI", Icon: Openai },
  { id: "azure", label: "Azure", Icon: Azure },
  { id: "aitta", label: "CSC Aitta", Icon: Server },
];

function emptyDraft(provider: ModelProvider = "openai"): ModelSettings {
  return { provider, model: PRESETS[provider][0].id, apiKey: "" };
}
const EMPTY = emptyDraft();

function isPreset(provider: ModelProvider, model: string): boolean {
  return PRESETS[provider].some((preset) => preset.id === model);
}

export function ModelSettingsButton() {
  const settings = useModelSettings();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ModelSettings>(EMPTY);
  const [custom, setCustom] = useState(false);
  const [message, setMessage] = useState("");
  const [testing, setTesting] = useState(false);
  const requestNumber = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const customInput = useRef<HTMLInputElement>(null);
  const focusCustom = useRef(false);

  useEffect(() => {
    const clear = () => {
      requestNumber.current += 1;
      activeRequest.current?.abort();
      activeRequest.current = null;
      setTesting(false);
      setMessage("");
      setModelSettings(null);
      setDraft(EMPTY);
      setCustom(false);
    };
    window.addEventListener("pagehide", clear);
    return () => {
      window.removeEventListener("pagehide", clear);
      requestNumber.current += 1;
      activeRequest.current?.abort();
    };
  }, []);

  function changeOpen(next: boolean) {
    // Closing remains possible during an Aitta cold start. Its eventual result
    // must not update a fresh draft if the dialog is opened again.
    requestNumber.current += 1;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setTesting(false);
    setOpen(next);
    setDraft(next && settings ? { ...settings } : EMPTY);
    setCustom(
      next && settings ? !isPreset(settings.provider, settings.model) : false,
    );
    setMessage("");
  }

  function updateDraft(changes: Partial<ModelSettings>) {
    setDraft((previous) => ({ ...previous, ...changes }));
    setMessage("");
  }

  function selectProvider(provider: ModelProvider) {
    setDraft(emptyDraft(provider));
    setCustom(false);
    setMessage("");
  }

  function selectModel(value: string) {
    if (value === CUSTOM) {
      focusCustom.current = true;
      setCustom(true);
      updateDraft({ model: "" });
      return;
    }
    setCustom(false);
    updateDraft({ model: value });
  }

  async function testConnection() {
    const currentRequest = ++requestNumber.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setMessage("");
    try {
      const header = encodeModelSettings(draft);
      setTesting(true);
      const response = await apiFetch("/api/model-settings/test", {
        method: "POST",
        headers: { [MODEL_SETTINGS_HEADER]: header },
        signal: controller.signal,
      });
      if (currentRequest !== requestNumber.current) return;
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        if (currentRequest !== requestNumber.current) return;
        setMessage(
          result.detail ||
            result.error ||
            "Connection failed. Check your settings.",
        );
        return;
      }
      setMessage("Connection works.");
    } catch (error) {
      if (currentRequest !== requestNumber.current || controller.signal.aborted)
        return;
      setMessage(error instanceof Error ? error.message : "Connection failed.");
    } finally {
      if (currentRequest === requestNumber.current) {
        activeRequest.current = null;
        setTesting(false);
      }
    }
  }

  function applySettings() {
    try {
      setModelSettings(draft);
      changeOpen(false);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Check your settings.",
      );
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="text-muted-foreground hover:text-foreground relative"
        onClick={() => changeOpen(true)}
        aria-label={
          settings ? "Model settings (own model in use)" : "Model settings"
        }
        title={settings ? "Own model in use" : "Use your own model"}
      >
        <KeyRound className="h-4 w-4" />
        {settings && (
          <span
            aria-hidden="true"
            className="bg-primary ring-card absolute top-1.5 right-1.5 size-2 rounded-full ring-2"
          />
        )}
      </Button>
      <Dialog open={open} onOpenChange={changeOpen}>
        <DialogContent
          className="ph-no-capture ph-mask max-h-[90dvh] overflow-y-auto sm:max-w-lg"
          data-private
        >
          <DialogHeader>
            <DialogTitle>Use your own model</DialogTitle>
            <DialogDescription>
              Optional. Your key stays in this tab, is sent only with supported
              requests and is cleared on reload.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <ToggleGroup
              type="single"
              variant="outline"
              aria-label="Provider"
              className="grid w-full grid-cols-3"
              value={draft.provider}
              disabled={testing}
              onValueChange={(value) =>
                value && selectProvider(value as ModelProvider)
              }
            >
              {PROVIDERS.map(({ id, label, Icon }) => (
                <ToggleGroupItem
                  key={id}
                  value={id}
                  className="gap-1.5 px-2 text-xs sm:gap-2 sm:text-sm"
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <div className="space-y-2">
              <Label htmlFor="model-id">
                {draft.provider === "azure" ? "Deployment" : "Model"}
              </Label>
              <Select
                value={custom ? CUSTOM : draft.model}
                disabled={testing}
                onValueChange={selectModel}
              >
                <SelectTrigger id="model-id" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent
                  onCloseAutoFocus={(event) => {
                    // Radix returns focus to the trigger; after "Other…" the
                    // user's next step is typing the ID.
                    if (!focusCustom.current) return;
                    focusCustom.current = false;
                    event.preventDefault();
                    customInput.current?.focus();
                  }}
                >
                  {PRESETS[draft.provider].map((preset) => (
                    <SelectItem key={preset.id} value={preset.id}>
                      {preset.label}
                      {preset.note && (
                        <span className="text-muted-foreground">
                          {preset.note}
                        </span>
                      )}
                    </SelectItem>
                  ))}
                  <SelectItem value={CUSTOM}>
                    {draft.provider === "azure"
                      ? "Other deployment…"
                      : "Other model ID…"}
                  </SelectItem>
                </SelectContent>
              </Select>
              {custom && (
                <Input
                  ref={customInput}
                  aria-label={
                    draft.provider === "azure" ? "Deployment name" : "Model ID"
                  }
                  value={draft.model}
                  disabled={testing}
                  onChange={(e) => updateDraft({ model: e.target.value })}
                  placeholder={
                    draft.provider === "azure"
                      ? "Your deployment name"
                      : draft.provider === "aitta"
                        ? "Model ID from the Aitta catalog"
                        : "e.g. gpt-5.4"
                  }
                  autoComplete="off"
                />
              )}
            </div>
            {draft.provider === "azure" && (
              <div className="space-y-2">
                <Label htmlFor="model-endpoint">Azure resource endpoint</Label>
                <Input
                  id="model-endpoint"
                  value={draft.azureEndpoint ?? ""}
                  disabled={testing}
                  onChange={(e) =>
                    updateDraft({ azureEndpoint: e.target.value })
                  }
                  placeholder="https://your-resource.openai.azure.com"
                  autoComplete="off"
                />
                <p className="text-muted-foreground text-xs">
                  Public openai.azure.com or services.ai.azure.com resource
                  URLs.
                </p>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="model-key">
                {draft.provider === "aitta" ? "Aitta API token" : "API key"}
              </Label>
              <Input
                id="model-key"
                type="password"
                className="ph-no-capture ph-mask"
                value={draft.apiKey}
                disabled={testing}
                onChange={(e) => updateDraft({ apiKey: e.target.value })}
                autoComplete="off"
                spellCheck={false}
                data-private
              />
            </div>
            {draft.provider === "aitta" && (
              <p className="text-muted-foreground text-xs">
                The first request can take a few minutes while Aitta starts the
                model.
              </p>
            )}
            <p className="text-muted-foreground text-xs">
              Used by Extractor, Vision Extractor, Schema Generator, Classifier,
              Parser (vision), LLM Judge, PostgreSQL Agent and Wizard images.
              Pick a model with structured output; images need vision.
            </p>
            {message && (
              <p role="status" className="text-sm">
                {message}
              </p>
            )}
          </div>
          <DialogFooter className="flex-wrap gap-2 sm:justify-between">
            <Button
              variant="ghost"
              onClick={() => {
                setModelSettings(null);
                changeOpen(false);
              }}
              disabled={testing}
            >
              Use server defaults
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={testConnection}
                disabled={testing}
              >
                {testing && <Loader2 className="h-4 w-4 animate-spin" />}Test
                connection
              </Button>
              <Button onClick={applySettings} disabled={testing}>
                Use settings
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function ModelSettingsNotice() {
  const settings = useModelSettings();
  const pathname = usePathname();
  if (!settings) return null;
  return (
    <div className="border-border bg-muted/40 mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm">
      <p>
        {pageUsesModelSettings(pathname) ? (
          <>
            Own model: <strong>{LABELS[settings.provider]}</strong> ·{" "}
            {settings.model}
            {pathname === "/solution-wizard"
              ? " (image attachments only; conversation uses hosted Claude)"
              : ""}
          </>
        ) : (
          "This demo uses server settings. Your own model is active on supported demos."
        )}
      </p>
      <Button variant="ghost" size="sm" onClick={() => setModelSettings(null)}>
        Clear own key
      </Button>
    </div>
  );
}
