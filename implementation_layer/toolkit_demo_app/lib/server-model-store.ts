"use client";

import { useEffect, useSyncExternalStore } from "react";
import { isServerModelId } from "./model-settings";

export interface ServerModel {
  id: string;
  provider: string;
  model: string;
  label: string;
  /** False when the model has no speech-to-text: GPT transcribes audio first. */
  audio: boolean;
  /** A costlier model for the GAIK project team only. */
  staff: boolean;
  /** Whether this user may run it. */
  allowed: boolean;
}
export interface ServerModels {
  default: string | null;
  models: ServerModel[];
}

// The choice is not a secret: keep it across reloads in this browser.
const KEY = "gaik:server-model";
let selected: string | null = null;
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

function loadCatalog() {
  if (catalog || catalogRequest || typeof window === "undefined") return;
  catalogRequest = fetch("/api/model-settings/server")
    .then((response) => (response.ok ? response.json() : null))
    .then((data: ServerModels | null) => {
      if (data && Array.isArray(data.models)) catalog = data;
      else catalog = { default: null, models: [] };
    })
    .catch(() => {
      catalog = { default: null, models: [] };
    })
    .finally(() => {
      catalogRequest = null;
      emit();
    });
}

/** The server's models, or null while they load. Empty when it offers none. */
export function useServerModels(enabled = true): ServerModels | null {
  useEffect(() => {
    if (enabled) loadCatalog();
  }, [enabled]);
  return useSyncExternalStore(
    subscribe,
    () => catalog,
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
