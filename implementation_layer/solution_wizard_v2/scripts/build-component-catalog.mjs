#!/usr/bin/env node
// Writes lib/gaik-components.generated.json from the Solution Wizard's
// component registry: each component's name, the artifact types it takes and
// produces, and where its documentation is. The chat shows these behind a
// component's name (lib/component-links.ts). The web app's image is built from
// this folder alone, so the registry is read here, not at run time.
//
//   node scripts/build-component-catalog.mjs          write the file
//   node scripts/build-component-catalog.mjs --check  fail when it is stale

import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SOURCE = "implementation_layer/solution_wizard/registries/gaik_component_registry.json";
const registryPath = path.resolve(here, "../../solution_wizard/registries/gaik_component_registry.json");
const outPath = path.resolve(here, "../lib/gaik-components.generated.json");

const README_BASE = "https://github.com/GAIK-project/gaik-toolkit/blob/main/";
const DOCS_BASE = "https://gaik-project.github.io/gaik-toolkit/toolkit/";

/** The component's own README when the registry names one, else its page on the docs site. */
function docsUrl(entry) {
  const readme = entry.readme_path ?? "";
  if (/(^|\/)README\.md$/.test(readme)) return README_BASE + readme;
  if (entry.type === "software_module") return `${DOCS_BASE}software-modules/`;
  if ((entry.source_path ?? "").includes("/evaluators")) return `${DOCS_BASE}evaluators/`;
  return `${DOCS_BASE}software-components/`;
}

export function buildCatalog(registry) {
  const components = registry
    .filter((entry) => typeof entry.name === "string" && entry.name)
    .map((entry) => ({
      name: entry.name,
      inputs: entry.input_artifact_types ?? [],
      outputs: entry.output_artifact_types ?? [],
      docs: docsUrl(entry),
    }))
    .sort((a, b) => a.name.localeCompare(b.name, "en"));
  return { source: SOURCE, components };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const registry = JSON.parse(readFileSync(registryPath, "utf8"));
  const next = `${JSON.stringify(buildCatalog(registry), null, 2)}\n`;
  if (process.argv.includes("--check")) {
    let current = "";
    try {
      current = readFileSync(outPath, "utf8").replace(/\r\n/g, "\n");
    } catch {
      // No file yet: stale.
    }
    if (current !== next) {
      console.error("lib/gaik-components.generated.json is stale: run `npm run component-catalog`.");
      process.exit(1);
    }
    console.log("lib/gaik-components.generated.json is up to date.");
  } else {
    writeFileSync(outPath, next);
    console.log(`Wrote ${path.relative(process.cwd(), outPath)}`);
  }
}
