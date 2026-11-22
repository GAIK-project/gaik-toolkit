"use client";

import { useEffect, useSyncExternalStore } from "react";
import {
  isReasoningEffort,
  isServerModelId,
  type ReasoningEffort,
} from "./model-settings";

export interface ServerModel {
  id: string;
  provider: string;
  model: string;
  label: string;
  /** False when the model has no speech-to-text: GPT transcribes audio first. */
  audio: boolean;
  /** False for a text-only model: it cannot read page images. */
  vision: boolean;
  /** CSC Aitta only: "running", or "offline" for a model that starts on demand. */
  status: string | null;
  /** A costlier model for the GAIK project team only. */
  staff: boolean;
  /** Whether this user may run it. */
  allowed: boolean;
}
/** One of Aitta's helper models and its state ("running", "offline", …). */
export interface AittaHelper {
  model: string;
  status: string | null;
}
/** The kind of model a report demo's model field names. */
export type ReportModelKind = "chat" | "transcription";
export interface ServerModels {
  default: string | null;
  models: ServerModel[];
  /**
   * The names the report demos' model fields accept for this user, from the lists
   * their routes check (api/utils/model_allow_list.py). Absent from an older API.
   */
  report_models?: Partial<Record<ReportModelKind, string[]>> | null;
  /** With an Aitta model picked, these transcribe and embed. */
  aitta?: { speech: AittaHelper; embedding: AittaHelper } | null;
  /** Where the server's own models run, in the deployment's words. */
  note?: string | null;
}

// The choice is not a secret: keep it across reloads in this browser.
const KEY = "gaik:server-model";
const EFFORT_KEY = "gaik:reasoning-effort";
let selected: string | null = null;
let effort: ReasoningEffort | null = null;
let loadedFromStorage = false;
let catalog: ServerModels | null = null;
let catalogRequest: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}
function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function readStorage() {
  if (loadedFromStorage || typeof window === "undefined") return;
  loadedFromStorage = true;
  try {
    const stored = window.localStorage.getItem(KEY);
    if (isServerModelId(stored)) selected = stored;
    const storedEffort = window.localStorage.getItem(EFFORT_KEY);
    if (isReasoningEffort(storedEffort)) effort = storedEffort;
  } catch {
    // Storage blocked: the choice lasts until reload.
  }
}

/** The picked server model, or null for the server default. */
export function getServerModel(): string | null {
  readStorage();
  if (!selected) return null;
  // Drop a stale choice once the server no longer offers it.
  if (catalog && !catalog.models.some((m) => m.id === selected && m.allowed))
    return null;
  return selected;
}

export function setServerModel(id: string | null): void {
  selected = id && isServerModelId(id) ? id : null;
  try {
    if (selected) window.localStorage.setItem(KEY, selected);
    else window.localStorage.removeItem(KEY);
  } catch {
    // Storage blocked: keep it in memory.
  }
  emit();
}

export function useServerModel(): string | null {
  return useSyncExternalStore(subscribe, getServerModel, () => null);
}

/** The picked reasoning effort, or null for Auto: each model's own default. */
export function getReasoningEffort(): ReasoningEffort | null {
  readStorage();
  return effort;
}

export function setReasoningEffort(value: ReasoningEffort | null): void {
  effort = isReasoningEffort(value) ? value : null;
  try {
    if (effort) window.localStorage.setItem(EFFORT_KEY, effort);
    else window.localStorage.removeItem(EFFORT_KEY);
  } catch {
    // Storage blocked: keep it in memory.
  }
  emit();
}

export function useReasoningEffort(): ReasoningEffort | null {
  return useSyncExternalStore(subscribe, getReasoningEffort, () => null);
}

// The API can be restarting when the page loads (a deploy, a cold start). An
// empty list would then hide the model menu until a reload, so a failed load
// is tried again a few times.
let catalogRetries = 0;
/** Counts the lists forgotten, so that a request sent before is not taken. */
let catalogGeneration = 0;

/**
 * Load the server's list for this user, once; a failed load is tried again. Resolves
 * when the request ends (at once when there is nothing to load).
 */
export function loadServerModels(): Promise<void> {
  if (catalogRequest) return catalogRequest;
  if (typeof window === "undefined") return Promise.resolve();
  if (catalog && (catalog.models.length > 0 || catalogRetries === 0))
    return Promise.resolve();
  const generation = catalogGeneration;
  const current = () => generation === catalogGeneration;
  const request = fetch("/api/model-settings/server")
    .then((response) => (response.ok ? response.json() : null))
    .then((data: ServerModels | null) => {
      if (!current()) return;
      if (data && Array.isArray(data.models)) {
        catalog = data;
        catalogRetries = 0;
        return;
      }
      throw new Error("no model list");
    })
    .catch(() => {
      if (!current()) return;
      catalog = { default: null, models: [] };
      catalogRetries = catalogRetries === 0 ? 3 : catalogRetries - 1;
      if (catalogRetries > 0)
        window.setTimeout(() => {
          if (current()) void loadServerModels();
        }, 8000);
    })
    .finally(() => {
      if (!current()) return;
      catalogRequest = null;
      emit();
    });
  catalogRequest = request;
  return request;
}

/**
 * Forget the loaded list, as on sign-out: it holds this user's names, team-only ones
 * for the team. The next user's list is loaded afresh, and a request still running is
 * not taken.
 */
export function forgetServerModels(): void {
  catalogGeneration += 1;
  catalog = null;
  catalogRequest = null;
  catalogRetries = 0;
  emit();
}

/** The loaded list, or null while it loads; null as well when `enabled` is false. */
export function getServerModels(enabled = true): ServerModels | null {
  return enabled ? catalog : null;
}

/** The names a report demo's model field of this kind accepts; empty until known. */
export function reportModelNames(
  catalog: ServerModels | null,
  kind: ReportModelKind,
): string[] {
  const names = catalog?.report_models?.[kind];
  return Array.isArray(names)
    ? names.filter((name) => typeof name === "string" && name !== "")
    : [];
}

/**
 * The server's models, or null while they load. Empty when it offers none. Null when
 * not `enabled` (signed out): a list loaded before sign-out is not read.
 */
export function useServerModels(enabled = true): ServerModels | null {
  useEffect(() => {
    if (enabled) void loadServerModels();
  }, [enabled]);
  return useSyncExternalStore(
    subscribe,
    () => getServerModels(enabled),
    () => null,
  );
}

/** The server model requests run on now: the picked one, else the default. */
export function useActiveServerModel(): ServerModel | null {
  const catalog = useServerModels(true);
  const picked = useServerModel();
  if (!catalog) return null;
  const id = picked ?? catalog.default;
  return catalog.models.find((model) => model.id === id) ?? null;
}

/** The same outside React, for a request. Null until the list has loaded. */
export function getActiveServerModel(): ServerModel | null {
  const id = getServerModel() ?? catalog?.default;
  return catalog?.models.find((model) => model.id === id) ?? null;
}
