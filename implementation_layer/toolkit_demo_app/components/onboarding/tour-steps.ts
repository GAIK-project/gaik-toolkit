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
        "Demos open with an example ready to run, so you see a result before you upload anything of your own.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="models"]',
    popover: {
      title: "The model that answers",
      description:
        "Pick one of the server's models here, or run the demos on your own API key. The menu says whether the page you are on uses it.",
      side: "bottom",
      align: "end",
    },
  },
  {
    element: '[data-tour="wizard"]',
    popover: {
      title: "Your own use case",
      description:
        "Describe it to the Wizard. Its page shows the two versions and how to get access to each.",
      side: "bottom",
      align: "start",
    },
  },
  {
    element: '[data-tour="use-cases"]',
    popover: {
      title: "Finished flows",
      description:
        "Each one runs a whole task, such as a purchase order into a priced sales order. Open a card to run it.",
      side: "top",
      align: "start",
    },
  },
  {
    element: '[data-tour="components"]',
    popover: {
      title: "In your own code",
      description:
        "Each component is a class in the gaik Python package. Its page has the install command and links to the code and the docs.",
      side: "top",
      align: "start",
    },
  },
];
