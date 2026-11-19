import type { DriveStep } from "driver.js";

/**
 * Guided tour stops on the home page. Each `element` selector points at a
 * `data-tour` anchor rendered by the hero (hero.tsx), the Wizard's block under
 * it (solution-tools.tsx) and the demo grid (demo-cards.tsx), in page order.
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
    element: '[data-tour="wizard"]',
    popover: {
      title: "Solution Configuration Wizard",
      description:
        "Describe a business problem in plain words and the Wizard builds a solution from GAIK components. Its page shows the two versions and how to get access to each.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="use-cases"]',
    popover: {
      title: "Real-world use cases",
      description:
        "End-to-end demos like purchase order processing, construction diaries, and video transcription. Click any card to try it.",
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
];
