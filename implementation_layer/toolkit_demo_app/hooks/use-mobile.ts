import { useSyncExternalStore } from "react";

const MOBILE_BREAKPOINT = 768;

const query = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`;
function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(query);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
const clientSnapshot = () => window.matchMedia(query).matches;
const serverSnapshot = () => false;

export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
}
