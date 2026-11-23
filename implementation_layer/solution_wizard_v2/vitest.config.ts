import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts", "app/**/*.test.ts"],
    coverage: {
      provider: "v8",
      // Coverage is scoped to lib/ — our own application/business logic
      // (session state machine, blueprint parsing, the wizard_api client,
      // etc.). Pages, components, and API routes are deliberately validated
      // through Playwright E2E instead of unit tests (see e2e/), not left
      // untested — including them here would just misrepresent an
      // intentional testing-strategy split as a coverage gap.
      include: ["lib/**"],
      exclude: [
        "lib/**/*.test.ts",
        "lib/supabase/**", // thin Supabase SDK wrappers, no logic of ours
        // diagram-js/bpmn-js SVG renderer integrations — need a real
        // diagram-js rendering context, same category as React components.
        "lib/bpmn/custom-renderer.module.ts",
        "lib/bpmn/diagram-enrichment.module.ts",
      ],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
