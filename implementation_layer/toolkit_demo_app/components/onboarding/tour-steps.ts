import type { DriveStep } from "driver.js";

/**
 * Guided tour stops on the home page. Each `element` selector points at a
 * `data-tour` anchor rendered by the hero (hero.tsx) and the demo grid
 * (demo-cards.tsx).
 */
export const TOUR_STEPS: DriveStep[] = [
  {
    element: '[data-tour="hero"]',
    popover: {
      title: "Welcome to the GAIK Toolkit",
      description:
        "A hub of live, runnable demos for GAIK's AI toolkit. Here's a 60-second look around.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="use-cases"]',
    popover: {
      title: "Real-world use cases",
      description:
        "End-to-end demos like incident reporting, construction diaries, and video transcription. Click any card to try it.",
      side: "top",
      align: "start",
    },
  },
  {
    element: '[data-tour="components"]',
    popover: {
      title: "The building blocks",
      description:
        "The software components behind the use cases — extractors, parsers, transcribers, a PostgreSQL agent, and more.",
      side: "top",
      align: "start",
    },
  },
  {
    element: '[data-tour="wizard"]',
    popover: {
      title: "Solution Configuration Wizard",
      description:
        "Describe a use case in plain language and the Wizard designs a validated proof of concept. It's in private beta — click the badge to request access.",
      side: "bottom",
      align: "start",
    },
  },
];
