"use client";

import { useEffect, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Check,
  ChevronDown,
  Box,
  KeyRound,
  Loader2,
  Lock,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Azure } from "@/components/ui/svgs/azure";
import { Openai } from "@/components/ui/svgs/openai";
import { Csc } from "@/components/ui/svgs/csc";
import { Gemma } from "@/components/ui/svgs/gemma";
import { Claude } from "@/components/ui/svgs/claude";
import { Gemini } from "@/components/ui/svgs/gemini";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api-client";
import {
  MODEL_SETTINGS_HEADER,
  encodeModelSettings,
  pageUsesModelSettings,
  type ModelProvider,
  type ModelSettings,
} from "@/lib/model-settings";
import { setModelSettings, useModelSettings } from "@/lib/model-settings-store";
import {
  setServerModel,
  useServerModel,
  useServerModels,
  type ServerModel,
} from "@/lib/server-model-store";
import {
  AITTA_SPEECH_MODEL,
  aittaName,
  aittaReadsImages,
  modelUse,
  type ActiveModel,
} from "@/lib/model-use";
import { useRunAccess } from "@/components/run-access";

const LABELS = { openai: "OpenAI", azure: "Azure OpenAI", aitta: "CSC Aitta" };
const CUSTOM = "__custom__";
const OPEN_EVENT = "gaik:open-model-settings";

type IconType = ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
type Preset = { id: string; label: string; note?: string; Icon?: IconType };
const GPT_PRESETS: Preset[] = [
  { id: "gpt-6-luna", label: "GPT-6 Luna", note: "default", Icon: Openai },
  { id: "gpt-6-sol", label: "GPT-6 Sol", Icon: Openai },
  { id: "gpt-6.1-sol", label: "GPT-6.1 Sol", note: "newest", Icon: Openai },
  { id: "gpt-6-astra", label: "GPT-6 Astra", Icon: Openai },
  { id: "gpt-5.6-terra", label: "GPT-5.6 Terra", Icon: Openai },
];
// Azure deployment names are chosen per resource; these match the model names.
const PRESETS: Record<ModelProvider, Preset[]> = {
  openai: GPT_PRESETS,
  azure: GPT_PRESETS,
  aitta: [
    {
      id: "google/gemma-4-31b-it",
      label: "Gemma 4 31B",
      note: "reads images",
      Icon: Gemma,
    },
    {
      id: "openai/gpt-oss-120b",
      label: "gpt-oss 120B",
      note: "fastest, text only",
      Icon: Openai,
    },
    { id: "Qwen/Qwen3.8-27B", label: "Qwen 3.8 27B", note: "reads images" },
  ],
};

const PROVIDERS: {
  id: ModelProvider;
  label: string;
  Icon: IconType;
}[] = [
  { id: "openai", label: "OpenAI", Icon: Openai },
  { id: "azure", label: "Azure", Icon: Azure },
  { id: "aitta", label: "CSC Aitta", Icon: Csc },
];

function emptyDraft(provider: ModelProvider = "openai"): ModelSettings {
  return { provider, model: PRESETS[provider][0].id, apiKey: "" };
}
const EMPTY = emptyDraft();

function isPreset(provider: ModelProvider, model: string): boolean {
  return PRESETS[provider].some((preset) => preset.id === model);
}

/** The own-key dialog; `showTrigger={false}` leaves opening it to the model menu. */
export function ModelSettingsButton({
  showTrigger = true,
}: { showTrigger?: boolean } = {}) {
  const settings = useModelSettings();
  const pathname = usePathname();
  const usedHere = pageUsesModelSettings(pathname);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ModelSettings>(EMPTY);
  const [custom, setCustom] = useState(false);
  const [message, setMessage] = useState("");
  const [testing, setTesting] = useState(false);
  const requestNumber = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const customInput = useRef<HTMLInputElement>(null);
  const focusCustom = useRef(false);
  const changeOpenRef = useRef<(next: boolean) => void>(() => {});

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

  useEffect(() => {
    const openDialog = () => changeOpenRef.current(true);
    window.addEventListener(OPEN_EVENT, openDialog);
    return () => window.removeEventListener(OPEN_EVENT, openDialog);
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

  changeOpenRef.current = changeOpen;

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
      {showTrigger && (
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "relative gap-1.5",
            settings
              ? "border-primary/50 bg-primary/10 text-primary hover:bg-primary/15"
              : "text-foreground",
          )}
          onClick={() => changeOpen(true)}
          aria-label={
            settings
              ? `Model settings, own model on${usedHere ? "" : " (not used on this page)"}`
              : "Model settings"
          }
          title={
            settings
              ? usedHere
                ? "Own model on"
                : "Own model set, not used on this page"
              : "Use your own key"
          }
        >
          <KeyRound className="h-4 w-4" />
          <span className="hidden sm:inline">
            {settings
              ? `Model settings · ${LABELS[settings.provider]}`
              : "Model settings"}
          </span>
          {settings && (
            <span
              aria-hidden="true"
              className={cn(
                "ring-card absolute top-1.5 right-1.5 size-2 rounded-full ring-2",
                usedHere ? "bg-emerald-500" : "bg-muted-foreground/50",
              )}
            />
          )}
        </Button>
      )}
      <Dialog open={open} onOpenChange={changeOpen}>
        <DialogContent
          className="ph-no-capture ph-mask max-h-[90dvh] overflow-y-auto sm:max-w-lg"
          data-private
        >
          <DialogHeader>
            <DialogTitle>Use your own key</DialogTitle>
            <DialogDescription>
              Your key stays in this tab and is cleared on reload.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {settings && (
              <p
                role="status"
                className="bg-primary/10 text-primary rounded-md px-3 py-2 text-sm"
              >
                In use: <strong>{LABELS[settings.provider]}</strong> ·{" "}
                {settings.model}
              </p>
            )}
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
                  className="data-[state=on]:border-primary/40 data-[state=on]:bg-primary/10 data-[state=on]:text-primary gap-1.5 px-2 text-xs sm:gap-2 sm:text-sm"
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
                      {preset.Icon && (
                        <preset.Icon className="size-4" aria-hidden />
                      )}
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
                Recordings are transcribed by {AITTA_SPEECH_MODEL} on Aitta with
                the same token. An idle model can take minutes to start. Aitta
                is a research service: do not send personal data.
              </p>
            )}
            {message && (
              <p role="status" className="text-sm">
                {message}
              </p>
            )}
          </div>
          <DialogFooter className="flex-wrap gap-2 sm:justify-between">
            {settings ? (
              <Button
                variant="ghost"
                onClick={() => {
                  setModelSettings(null);
                  changeOpen(false);
                }}
                disabled={testing}
              >
                Clear own model
              </Button>
            ) : (
              <span />
            )}
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
                Use this key
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ProviderIcon({
  provider,
  model = "",
  className,
}: {
  provider: string;
  /** Aitta serves models of many makers: the icon follows the model. */
  model?: string;
  className?: string;
}) {
  if (provider.startsWith("anthropic"))
    return <Claude className={className} aria-hidden />;
  if (provider === "google" || provider === "vertex")
    return <Gemini className={className} />;
  if (provider === "aitta") {
    const id = model.toLowerCase();
    if (id.startsWith("google/gemma"))
      return <Gemma className={className} aria-hidden />;
    if (id.startsWith("openai/"))
      return <Openai className={className} aria-hidden />;
    return <Box className={className} aria-hidden />;
  }
  return <Openai className={className} aria-hidden />;
}

/** The model that runs requests now: the user's key, else the picked or default server model. */
function useActiveModel(loggedIn: boolean): ActiveModel | null {
  const catalog = useServerModels(loggedIn);
  const picked = useServerModel();
  const settings = useModelSettings();
  if (settings)
    return {
      own: true,
      provider: settings.provider,
      model: settings.model,
      label: settings.model,
      vision: settings.provider !== "aitta" || aittaReadsImages(settings.model),
      audio: true,
      isDefault: false,
    };
  // A page can load the list for its own use; a signed-out visitor still runs nothing.
  if (!loggedIn || !catalog) return null;
  const id = picked ?? catalog.default;
  const model = catalog.models.find((m) => m.id === id) ?? catalog.models[0];
  if (!model) return null;
  return {
    own: false,
    provider: model.provider,
    model: model.model,
    label: model.label,
    vision: model.vision,
    audio: model.audio,
    isDefault: model.id === catalog.default,
    teamOnly: model.staff,
    ...(model.provider === "aitta" && catalog.aitta
      ? {
          aittaSpeech: helperState(catalog.aitta.speech),
          aittaEmbedding: helperState(catalog.aitta.embedding),
        }
      : {}),
  };
}

function helperState(helper: { model: string; status: string | null }) {
  // No status means the catalog did not answer: say nothing rather than guess.
  return {
    model: helper.model,
    idle: helper.status !== null && helper.status !== "running",
  };
}

/**
 * Set when Aitta's Whisper transcribes the recordings of this page: its name,
 * such as "Whisper large v3 on CSC Aitta". The audio pages use it to say which
 * of their options then apply, since those belong to the HH Whisper server.
 */
export function useAittaSpeech(): string | null {
  const pathname = usePathname();
  const { loggedIn } = useRunAccess();
  const active = useActiveModel(loggedIn);
  if (!active || active.provider !== "aitta") return null;
  if (!modelUse(pathname, active).runsHere) return null;
  return active.aittaSpeech
    ? aittaName(active.aittaSpeech.model)
    : `${AITTA_SPEECH_MODEL} on CSC Aitta`;
}

function ModelRow({
  model,
  isDefault,
}: {
  model: ServerModel;
  isDefault: boolean;
}) {
  const tags: string[] = [];
  if (isDefault) tags.push("default");
  if (!model.vision) tags.push("text only");
  // Aitta starts an idle model on its first request.
  if (model.status === "failed") tags.push("unavailable");
  else if (model.status && model.status !== "running") tags.push("idle");
  return (
    <DropdownMenuRadioItem
      value={model.id}
      disabled={!model.allowed}
      title={
        !model.allowed
          ? "For the GAIK project team"
          : tags.includes("unavailable")
            ? "Aitta reports that this model failed to start"
            : tags.includes("idle")
              ? "Idle on Aitta: the first request starts it, which can take minutes"
              : undefined
      }
    >
      <ProviderIcon
        provider={model.provider}
        model={model.model}
        className="size-4"
      />
      <span className="whitespace-nowrap">{model.label}</span>
      <span className="text-muted-foreground ml-auto flex items-center gap-1.5 text-xs">
        {tags.join(" · ")}
        {!model.allowed && <Lock className="size-3.5" aria-label="Team only" />}
      </span>
    </DropdownMenuRadioItem>
  );
}

/**
 * The model menu in the nav. A signed-in user sees the model in use and can
 * switch among the server's models without a key; their own key stays an
 * advanced option. Signed out it renders nothing: the nav shows Sign in, and
 * every run needs an account. A clone with no server keys gets the plain
 * own-key button.
 */
export function ModelPicker({ loggedIn }: { loggedIn: boolean }) {
  const catalog = useServerModels(loggedIn);
  const picked = useServerModel();
  const settings = useModelSettings();
  const pathname = usePathname();
  const active = useActiveModel(loggedIn);

  if (!loggedIn) return null;
  // While the list loads, hold the button's place instead of showing the
  // own-key button for a moment and then swapping it.
  if (!catalog && !settings)
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        className="gap-1.5"
        aria-label="Loading the models"
      >
        <Loader2 className="size-4 animate-spin" aria-hidden />
        <span className="hidden sm:inline">Model</span>
      </Button>
    );
  if (!catalog || catalog.models.length === 0 || !active)
    return <ModelSettingsButton />;

  const use = modelUse(pathname, active);
  const label = settings ? `Own · ${settings.model}` : active.label;
  const pickedModel = catalog.models.find((m) => m.id === picked);
  const activeId = settings
    ? ""
    : (pickedModel?.id ?? catalog.default ?? catalog.models[0].id);
  const serverModels = catalog.models.filter((m) => m.provider !== "aitta");
  const aittaModels = catalog.models.filter((m) => m.provider === "aitta");
  const someLocked = catalog.models.some((m) => !m.allowed);
  const status = use.problem ?? use.summary;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className={cn(
              "relative max-w-56 gap-1.5",
              settings &&
                "border-primary/50 bg-primary/10 text-primary hover:bg-primary/15",
            )}
            aria-label={`Model: ${label}. ${status}`}
            title={status}
          >
            {settings ? (
              <KeyRound className="size-4 shrink-0" aria-hidden />
            ) : (
              <ProviderIcon
                provider={active.provider}
                model={active.model}
                className="size-4 shrink-0"
              />
            )}
            <span className="hidden truncate sm:inline">{label}</span>
            <ChevronDown className="size-3.5 opacity-60" aria-hidden />
            <span
              aria-hidden="true"
              className={cn(
                "ring-card absolute top-1 right-1 size-2 rounded-full ring-2",
                use.problem
                  ? "bg-amber-500"
                  : use.runsHere
                    ? "bg-emerald-500"
                    : "bg-muted-foreground/50",
              )}
            />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-80">
          <div className="space-y-0.5 px-2 py-1.5 text-xs" role="status">
            <p
              className={cn(
                "font-medium",
                use.problem && "text-amber-700 dark:text-amber-400",
              )}
            >
              {status}
            </p>
            {use.details.map((detail) => (
              <p key={detail} className="text-muted-foreground">
                {detail}
              </p>
            ))}
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={activeId}
            onValueChange={(id) => {
              setModelSettings(null);
              setServerModel(id === catalog.default ? null : id);
              // Aitta stops idle models: start its speech and embedding models
              // now, so that they are up when a recording or document arrives.
              if (id.startsWith("aitta:"))
                void apiFetch("/api/model-settings/aitta/warm", {
                  method: "POST",
                }).catch(() => {});
            }}
          >
            {serverModels.length > 0 && (
              <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
                GAIK server models
              </DropdownMenuLabel>
            )}
            {serverModels.map((model) => (
              <ModelRow
                key={model.id}
                model={model}
                isDefault={model.id === catalog.default}
              />
            ))}
            {serverModels.length > 0 && catalog.note && (
              <p className="text-muted-foreground px-2 pt-1 pb-1.5 text-xs">
                {catalog.note}
              </p>
            )}
            {aittaModels.length > 0 && (
              <>
                {serverModels.length > 0 && <DropdownMenuSeparator />}
                <DropdownMenuLabel className="text-muted-foreground flex items-center gap-2 text-xs font-normal">
                  <Csc className="h-4 w-auto shrink-0" aria-hidden />
                  CSC Aitta · open models hosted in Finland
                </DropdownMenuLabel>
                {aittaModels.map((model) => (
                  <ModelRow
                    key={model.id}
                    model={model}
                    isDefault={model.id === catalog.default}
                  />
                ))}
                <p className="text-muted-foreground px-2 pt-1 pb-1.5 text-xs">
                  Runs at CSC in Finland, speech and embeddings included. Slower
                  than the server models: a run takes from 20 seconds to
                  minutes. A research service: no personal data.
                </p>
              </>
            )}
          </DropdownMenuRadioGroup>
          {someLocked && (
            <p className="text-muted-foreground px-2 pt-1 pb-1.5 text-xs">
              Locked models: ask an admin for access.
            </p>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => window.dispatchEvent(new Event(OPEN_EVENT))}
          >
            <KeyRound className="size-4" aria-hidden />
            {settings ? "Own key settings…" : "Use your own key…"}
            {settings && <Check className="ml-auto size-4" aria-hidden />}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ModelSettingsButton showTrigger={false} />
    </>
  );
}

/**
 * On a demo page, says which model runs it once the user has left the server
 * default: their own key or another server model. Also says when the demo does
 * not take that model, and when the model cannot do what the demo needs.
 */
export function ModelSettingsNotice({
  loggedIn = true,
}: { loggedIn?: boolean } = {}) {
  const pathname = usePathname();
  const active = useActiveModel(loggedIn);
  if (!active || (!active.own && active.isDefault)) return null;
  const use = modelUse(pathname, active);
  const aitta = active.provider === "aitta" && use.runsHere;
  return (
    <div
      role="status"
      data-testid="model-use-notice"
      className={cn(
        "mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm",
        use.problem
          ? "border-amber-500/40 bg-amber-500/10"
          : "border-border bg-muted/40",
      )}
    >
      <div className="min-w-0 flex-1 basis-64 space-y-0.5">
        <p className="flex items-center gap-2">
          {use.problem ? (
            <TriangleAlert
              className="size-4 shrink-0 text-amber-600 dark:text-amber-400"
              aria-hidden
            />
          ) : (
            use.runsHere && (
              <ProviderIcon
                provider={active.provider}
                model={active.model}
                className="size-4 shrink-0"
              />
            )
          )}
          <span>
            {use.problem ?? use.summary}
            {use.runsHere && active.own && (
              <span className="text-muted-foreground">
                {" "}
                ({LABELS[active.provider as ModelProvider]})
              </span>
            )}
          </span>
        </p>
        {[
          ...use.details,
          ...(aitta
            ? [
                "CSC Aitta runs at CSC in Finland. It is a research service: do not send personal data. Its models are slower: a run takes from 20 seconds to minutes.",
              ]
            : []),
        ].map((line) => (
          <p key={line} className="text-muted-foreground text-xs">
            {line}
          </p>
        ))}
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() =>
          active.own ? setModelSettings(null) : setServerModel(null)
        }
      >
        {active.own ? "Clear own key" : "Use the default model"}
      </Button>
    </div>
  );
}

/**
 * Tells visitors who cannot run a demo yet how to: sign in, and once signed in,
 * use their own key. A pending user on the trial allowance is told the daily
 * limit instead.
 */
export function AccessNotice({
  loggedIn,
  unlocked,
  trialRunsPerDay = null,
}: {
  loggedIn: boolean;
  unlocked: boolean;
  /** Set when the user is pending approval and on the trial allowance. */
  trialRunsPerDay?: number | null;
}) {
  const settings = useModelSettings();
  const pathname = usePathname();
  if (unlocked) return null;
  // An own key runs a demo for a signed-in user (lib/api-access.ts).
  const ownKeyWorks = loggedIn && pageUsesModelSettings(pathname);
  if (ownKeyWorks && settings) return null;
  if (trialRunsPerDay)
    return (
      <div
        role="status"
        className="border-border bg-muted/40 mb-6 rounded-lg border px-4 py-3 text-sm"
      >
        <p>
          <strong>Trial access.</strong> You can run demos now, up to{" "}
          {trialRunsPerDay} runs a day, while your account is reviewed.
        </p>
      </div>
    );
  return (
    <div
      role="status"
      className="border-border bg-muted/40 mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm"
    >
      <p>
        <strong>View only.</strong>{" "}
        {loggedIn
          ? "Your access is pending approval, so running demos is off for now."
          : "Sign in to run this demo."}
        {ownKeyWorks ? " You can also run it with your own model key." : ""}
      </p>
      <div className="flex gap-2">
        {!loggedIn && (
          <Button asChild size="sm">
            <Link href="/sign-in">Sign in</Link>
          </Button>
        )}
        {ownKeyWorks && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}
          >
            Use own key
          </Button>
        )}
      </div>
    </div>
  );
}
