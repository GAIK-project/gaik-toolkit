import type { NextConfig } from "next";
import { securityHeaders } from "./lib/security-headers";
import { JSON_ROUTE_CSP } from "./lib/csp";

// The BPMN save route (/api/sessions/[id]/bpmn/sync) lints the diagram by
// spawning scripts/lint-bpmn.mjs as a child process. Next's standalone tracer
// only bundles node_modules it sees imported from the app graph, and a spawned
// script is invisible to it, so bpmnlint + bpmn-moddle and their transitive
// deps were dropped from the image and the linter could not start on Rahti.
// List the script, its .bpmnlintrc, and the exact dependency closure (derived
// from package-lock.json) so the standalone image ships everything the child
// process requires and linting actually runs. The route also tolerates a
// missing linter (it logs and proceeds), so this only restores validation.
const BPMN_LINT_TRACE = [
  "./scripts/lint-bpmn.mjs",
  "./.bpmnlintrc",
  ...[
    "@bpmn-io/moddle-utils",
    "ansi-colors",
    "bpmn-moddle",
    "bpmnlint",
    "bpmnlint-utils",
    "cli-table",
    "color-support",
    "colors",
    "globalyzer",
    "globrex",
    "min-dash",
    "moddle",
    "moddle-xml",
    "mri",
    "pluralize",
    "saxen",
    "tiny-glob",
  ].map((pkg) => `./node_modules/${pkg}/**`),
];

const nextConfig: NextConfig = {
  output: "standalone",
  // The stack e2e browser reaches `next dev` by its compose service name;
  // Next 16 blocks dev resources to any other host, so the page never hydrates.
  allowedDevOrigins: ["wizard-ui-stack-e2e", "wizard-ui-e2e"],
  // `next dev` would write AGENTS.md (pointers to the bundled docs) into this
  // folder; the repository has its own agent instructions at its root.
  agentRules: false,
  // Stop advertising the stack in every response (#133).
  poweredByHeader: false,
  // In development Next's own indicator sits in a corner of the window. Its
  // default corner, bottom left, is where the sidebar has the language switch
  // and the sign-out, which it would cover.
  devIndicators: { position: "top-right" },
  outputFileTracingIncludes: {
    // The key is a glob over the route, so the brackets are escaped. With a
    // bare [id] the Turbopack build (Next.js 16) matched no route and left the
    // linter out of the standalone output without a word.
    "/api/sessions/\\[id\\]/bpmn/sync": BPMN_LINT_TRACE,
  },
  async headers() {
    return [
      { source: "/:path*", headers: [...securityHeaders] },
      // The middleware sets a nonce CSP on every request it sees (lib/csp.ts).
      // Its matcher leaves out the file uploads (middleware.ts), so they get a
      // static one here; they answer JSON and load nothing.
      ...["/api/sessions/:id/poc/input", "/api/sessions/:id/cases/:caseId/inputs"].map(
        (source) => ({
          source,
          headers: [{ key: "Content-Security-Policy", value: JSON_ROUTE_CSP }],
        }),
      ),
    ];
  },
};

export default nextConfig;
