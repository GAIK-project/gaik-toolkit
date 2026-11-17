import { expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  componentSourceFor,
  componentSourceRoutes,
  installCommand,
} from "./component-sources";

const APP = join(import.meta.dir, "..");
const REPO = join(APP, "..", "..");
const SOURCE_PREFIX =
  "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/";
const DEMO_PREFIX =
  "https://github.com/GAIK-project/gaik-toolkit/blob/main/implementation_layer/toolkit_demo_app/";
const DOCS_PREFIX = "https://gaik-project.github.io/gaik-toolkit/";

// github-slugger, as Fumadocs uses it for heading anchors.
function slug(heading: string): string {
  return heading
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, "")
    .replace(/ /g, "-");
}

function docsPage(page: string): string {
  return join(REPO, "guidance_layer/website/content/docs", `${page}.mdx`);
}

function docsAnchors(page: string): Set<string> {
  const mdx = readFileSync(docsPage(page), "utf8");
  return new Set(
    [...mdx.matchAll(/^#{2,4} (.+)$/gm)].map((match) => slug(match[1].trim())),
  );
}

function pipExtras(): Set<string> {
  const toml = readFileSync(join(REPO, "pyproject.toml"), "utf8");
  const block = toml
    .split("[project.optional-dependencies]")[1]
    .split("\n[")[0];
  return new Set([...block.matchAll(/^([a-z0-9-]+) = \[/gm)].map((m) => m[1]));
}

test("every listed route is a demo page", () => {
  for (const route of componentSourceRoutes) {
    expect(existsSync(join(APP, "app/(demos)", route, "page.tsx"))).toBe(true);
  }
});

test("every install command names pip extras gaik defines", () => {
  const extras = pipExtras();
  for (const route of componentSourceRoutes) {
    for (const extra of componentSourceFor(route)!.extras) {
      expect(extras.has(extra)).toBe(true);
    }
  }
});

test("every source link points at a gaik package or demo file that exists", () => {
  for (const route of componentSourceRoutes) {
    const { sourceUrl } = componentSourceFor(route)!;
    if (sourceUrl.startsWith(DEMO_PREFIX)) {
      expect(existsSync(join(APP, sourceUrl.slice(DEMO_PREFIX.length)))).toBe(
        true,
      );
      continue;
    }
    expect(sourceUrl.startsWith(SOURCE_PREFIX)).toBe(true);
    const folder = sourceUrl.slice(SOURCE_PREFIX.length);
    expect(
      existsSync(
        join(REPO, "implementation_layer/src/gaik", folder, "__init__.py"),
      ),
    ).toBe(true);
  }
});

test("every docs link lands on a heading of its docs page", () => {
  for (const route of componentSourceRoutes) {
    const { docsUrl } = componentSourceFor(route)!;
    if (!docsUrl) continue;
    expect(docsUrl.startsWith(DOCS_PREFIX)).toBe(true);
    const [path, anchor] = docsUrl.slice(DOCS_PREFIX.length).split("#");
    const page = path.replace(/\/$/, "");
    expect(existsSync(docsPage(page))).toBe(true);
    if (anchor) expect(docsAnchors(page)).toContain(anchor);
  }
});

test("an unlisted page and a trailing slash are handled", () => {
  expect(componentSourceFor("/solution-wizard")).toBeNull();
  expect(componentSourceFor("/vision-extractor/")?.extras).toEqual([
    "vision-extract",
  ]);
});

test("the install command quotes the extras for zsh", () => {
  expect(installCommand(["parser"])).toBe('pip install "gaik[parser]"');
  expect(installCommand(["parser", "extract"])).toBe(
    'pip install "gaik[parser,extract]"',
  );
});
