"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
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

const EMPTY: ModelSettings = { provider: "openai", model: "", apiKey: "" };
const LABELS = { openai: "OpenAI", azure: "Azure OpenAI", aitta: "CSC Aitta" };

export function ModelSettingsButton() {
  const settings = useModelSettings();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ModelSettings>(EMPTY);
  const [message, setMessage] = useState("");
  const [testing, setTesting] = useState(false);
  const requestNumber = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const clear = () => {
      requestNumber.current += 1;
      activeRequest.current?.abort();
      activeRequest.current = null;
      setTesting(false);
      setMessage("");
      setModelSettings(null);
      setDraft(EMPTY);
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
    setMessage("");
  }

  function updateDraft(changes: Partial<ModelSettings>) {
    setDraft((previous) => ({ ...previous, ...changes }));
    setMessage("");
  }

  function selectProvider(provider: ModelProvider) {
    setDraft({
      provider,
      model: provider === "aitta" ? "google/gemma-4-31b-it" : "",
      apiKey: "",
    });
    setMessage("");
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
      setMessage(
        "Connection works. Use these settings to apply them to this tab.",
      );
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
        variant={settings ? "secondary" : "ghost"}
        size="sm"
        onClick={() => changeOpen(true)}
        aria-label="Model settings"
        title="Model settings"
      >
        <KeyRound className="h-4 w-4" />
        {/* Icon only while the desktop nav needs the room (md to xl). */}
        <span className="hidden sm:inline md:hidden xl:inline">
          {settings ? "Own model" : "Model settings"}
        </span>
      </Button>
      <Dialog open={open} onOpenChange={changeOpen}>
        <DialogContent
          className="ph-no-capture ph-mask max-h-[90dvh] overflow-y-auto sm:max-w-lg"
          data-private
        >
          <DialogHeader>
            <DialogTitle>Use your own model</DialogTitle>
            <DialogDescription>
              Optional. The demo uses its configured models by default. Your key
              stays in this tab&apos;s memory and is sent to our backend only
              when running a supported operation. It is cleared on reload or
              sign-out.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="model-provider">Provider</Label>
              <Select
                value={draft.provider}
                disabled={testing}
                onValueChange={(value) =>
                  selectProvider(value as ModelProvider)
                }
              >
                <SelectTrigger id="model-provider" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="azure">Azure OpenAI</SelectItem>
                  <SelectItem value="aitta">CSC Aitta</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-id">
                {draft.provider === "azure" ? "Deployment name" : "Model ID"}
              </Label>
              <Input
                id="model-id"
                value={draft.model}
                disabled={testing}
                onChange={(e) => updateDraft({ model: e.target.value })}
                placeholder={
                  draft.provider === "azure"
                    ? "Your Azure deployment name"
                    : "Model available to your account"
                }
                autoComplete="off"
              />
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
            <p className="text-muted-foreground text-sm">
              Applies to Extractor, Vision Extractor, Schema Generator,
              Classifier, the Parser&apos;s vision options, single-model LLM
              Judge, PostgreSQL Agent, and Wizard image attachments. Choose a
              model that supports structured output; images also need a vision
              model.
            </p>
            <p className="text-muted-foreground text-sm">
              Other demos and the judge panel keep their server settings. The
              Wizard conversation uses the hosted Claude model; describe your
              preferred PoC provider in the conversation. Clear your settings
              before uploading Wizard audio attachments. Keys are never added to
              its conversation or generated files.
            </p>
            {draft.provider === "aitta" && (
              <p className="text-muted-foreground text-sm">
                Aitta uses a fixed CSC endpoint. Select a model that supports
                your task; model startup can take several minutes.
              </p>
            )}
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
