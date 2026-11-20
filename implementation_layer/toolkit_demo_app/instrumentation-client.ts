import posthog from "posthog-js";

if (
  typeof window !== "undefined" &&
  process.env.NEXT_PUBLIC_POSTHOG_KEY &&
  process.env.NODE_ENV === "production"
) {
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY, {
    api_host: "/a",
    ui_host: "https://eu.posthog.com",
    person_profiles: "identified_only",
    // The privacy policy promises that Do Not Track opts a visitor out.
    respect_dnt: true,
    capture_pageview: true,
    capture_pageleave: true,
  });
}
