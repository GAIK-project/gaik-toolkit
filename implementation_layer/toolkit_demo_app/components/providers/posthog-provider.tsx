"use client";

import { useEffect, useState } from "react";
import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    // Defer PostHog initialization to avoid blocking hydration
    const timer = setTimeout(() => {
      if (
        process.env.NEXT_PUBLIC_POSTHOG_KEY &&
        typeof window !== "undefined"
      ) {
        posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY, {
          api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
          capture_pageview: false,
          loaded: () => setIsInitialized(true),
        });
      }
    }, 2000); // 2s delay after hydration

    return () => clearTimeout(timer);
  }, []);

  // Always render children, PostHog will work once initialized
  return <PHProvider client={posthog}>{children}</PHProvider>;
}
