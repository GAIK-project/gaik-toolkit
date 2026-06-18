"use client";

import "driver.js/dist/driver.css";
import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { TOUR_STEPS } from "./tour-steps";
import { WelcomeTourDialog } from "./welcome-tour-dialog";
import { WizardAccessDialog } from "./wizard-access-dialog";

const TOUR_SEEN_KEY = "gaik-tour-seen";
// Small delay before any auto-opened modal so the streamed page below the root
// provider finishes hydrating first (otherwise Radix's aria-hidden lands on a
// still-hydrating node and React warns about a hydration mismatch).
const AUTO_OPEN_DELAY_MS = 250;

interface OnboardingContextValue {
  /** Open the "how to get Solution Wizard access" dialog. */
  openWizardAccess: () => void;
  /** Start the guided home-page tour. */
  startTour: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext);
  if (!ctx) {
    throw new Error("useOnboarding must be used within <OnboardingProvider>");
  }
  return ctx;
}

function hasSeenTour(): boolean {
  try {
    return localStorage.getItem(TOUR_SEEN_KEY) === "1";
  } catch {
    return true; // storage blocked → don't nag
  }
}

function markTourSeen(): void {
  try {
    localStorage.setItem(TOUR_SEEN_KEY, "1");
  } catch {
    // storage unavailable (private mode) — nothing to persist
  }
}

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [welcomeOpen, setWelcomeOpen] = useState(false);

  // Flip `mounted` a tick after first paint so auto-opened modals wait for the
  // page below to finish hydrating (see AUTO_OPEN_DELAY_MS).
  useEffect(() => {
    const id = window.setTimeout(() => setMounted(true), AUTO_OPEN_DELAY_MS);
    return () => window.clearTimeout(id);
  }, []);

  // A bounced Wizard visitor lands on /?wizard=denied. Explain how to get
  // access, then strip the param so a refresh doesn't reopen the dialog.
  useEffect(() => {
    if (!mounted) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("wizard") !== "denied") return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reacting to a URL param, not a render cascade
    setWizardOpen(true);
    params.delete("wizard");
    const query = params.toString();
    window.history.replaceState(
      null,
      "",
      window.location.pathname + (query ? `?${query}` : ""),
    );
  }, [mounted]);

  // First-time visitors on the home page get the welcome invite, once.
  useEffect(() => {
    if (!mounted || pathname !== "/") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("wizard") === "denied" || params.get("tour") === "1") return;
    if (hasSeenTour()) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time first-visit prompt from localStorage
    setWelcomeOpen(true);
  }, [mounted, pathname]);

  const startTour = useCallback(async () => {
    setWelcomeOpen(false);
    markTourSeen();
    // The tour targets home-page anchors; send the user home first if needed
    // (it auto-starts there via the ?tour=1 effect below).
    if (window.location.pathname !== "/") {
      window.location.assign("/?tour=1");
      return;
    }
    const { driver } = await import("driver.js");
    driver({
      showProgress: true,
      popoverClass: "gaik-tour",
      nextBtnText: "Next",
      prevBtnText: "Back",
      doneBtnText: "Done",
      steps: TOUR_STEPS,
    }).drive();
  }, []);

  // Cross-page "Take a tour": links elsewhere send the user to /?tour=1; once
  // home has mounted, auto-start the tour and strip the param.
  useEffect(() => {
    if (!mounted || pathname !== "/") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("tour") !== "1") return;
    params.delete("tour");
    const query = params.toString();
    window.history.replaceState(
      null,
      "",
      window.location.pathname + (query ? `?${query}` : ""),
    );
    void startTour();
  }, [mounted, pathname, startTour]);

  const dismissWelcome = useCallback(() => {
    setWelcomeOpen(false);
    markTourSeen();
  }, []);

  const openWizardAccess = useCallback(() => setWizardOpen(true), []);

  const value = useMemo(
    () => ({ openWizardAccess, startTour }),
    [openWizardAccess, startTour],
  );

  return (
    <OnboardingContext.Provider value={value}>
      {children}
      {mounted && (
        <>
          <WelcomeTourDialog
            open={welcomeOpen}
            onStart={startTour}
            onDismiss={dismissWelcome}
          />
          <WizardAccessDialog open={wizardOpen} onOpenChange={setWizardOpen} />
        </>
      )}
    </OnboardingContext.Provider>
  );
}
