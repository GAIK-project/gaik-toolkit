"use client";

import { useSyncExternalStore } from "react";
import { type ModelSettings, validateModelSettings } from "./model-settings";

// Deliberately memory-only: never serialize into storage, cookies, URLs or analytics.
let current: Readonly<ModelSettings> | null = null;
const listeners = new Set<() => void>();

export function getModelSettings(): Readonly<ModelSettings> | null {
  return current;
}
export function setModelSettings(settings: ModelSettings | null): void {
  current = settings ? Object.freeze(validateModelSettings(settings)) : null;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useModelSettings(): Readonly<ModelSettings> | null {
  return useSyncExternalStore(subscribe, getModelSettings, () => null);
}
