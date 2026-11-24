import type { DriveStep } from "driver.js";

/**
 * Guided tour stops on the home page. Each `element` selector points at a
 * `data-tour` anchor rendered by the hero (hero.tsx), the model menu in the nav
 * (model-settings.tsx, signed-in users only), the Wizard's block under the hero
 * (solution-tools.tsx) and the demo grid (demo-cards.tsx), in page order. A stop
 * whose anchor is not on screen is left out (onboarding-provider.tsx). Each stop
 * says what the page itself does not: the welcome dialog has already greeted.
 */
export const TOUR_STEPS: DriveStep[] = [
  {
    element: '[data-tour="hero"]',
    popover: {
      title: "Start with one demo",
      description:
        "Every demo has a built-in example one press away, so you see a result before you upload anything of your own.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="models"]',
    popover: {
      title: "The model that answers",
      description:
        "Pick one of the server's models here, or run the demos on your own API key. On a demo page the menu shows whether that demo uses it.",
      side: "bottom",
      align: "end",
    },
  },
  {
    element: '[data-tour="wizard"]',
    popover: {
      title: "Your own use case",
      description:
        "Describe it to the Wizard. Its page says how to get access.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="use-cases"]',
    popover: {
      title: "Finished flows",
      description:
        "Each one chains several of the building blocks below into a whole task, from the input to the finished result.",
      side: "top",
      align: "start",
    },
  },
  {
    element: '[data-tour="components"]',
    popover: {
      title: "In your own code",
      description:
        "Each one is part of the gaik Python package. Its page has the install command and links to the code and the docs.",
      side: "top",
      align: "start",
    },
  },
];
