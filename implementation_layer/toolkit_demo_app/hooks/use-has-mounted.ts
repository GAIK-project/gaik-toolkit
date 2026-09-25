"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

/** Keep the server and hydration render identical before using browser-only UI. */
export function useHasMounted(): boolean {
  return useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
}
