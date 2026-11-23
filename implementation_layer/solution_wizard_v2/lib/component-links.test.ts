import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import catalog from "./gaik-components.generated.json";
import { cardPlacement, componentLine, componentNamed, withComponentLinks } from "./component-links";
import { dictionary, LOCALES } from "./i18n";
import { renderMarkdown } from "./markdown";

const fi = dictionary("fi").chatActivity.components;
const en = dictionary("en").chatActivity.components;

const links = (markdown: string, labels = fi) => withComponentLinks(renderMarkdown(markdown), labels, "m1");
const count = (html: string, needle: string) => html.split(needle).length - 1;

describe("withComponentLinks", () => {
  it("turns a component's name into its card: name, one line, documentation link", () => {
    const html = links("Käytetään komponenttia VisionExtractor laskujen lukemiseen.");
    expect(html).toContain('<button type="button" class="cmp-name"');
    expect(html).toContain('<span class="cmp-card-name">VisionExtractor</span>');
    expect(html).toContain("Ottaa: PDF, kuva, dokumentti. Tuottaa: jäsennelty data.");
    expect(html).toContain(`href="${componentNamed("VisionExtractor")!.docs}"`);
    expect(html).toContain('target="_blank" rel="noreferrer noopener"');
    expect(html).toContain(">Dokumentaatio<");
    // The name is described by the card's line, for a screen reader.
    const id = /aria-describedby="([^"]+)"/.exec(html)![1];
    expect(html).toContain(`<span class="cmp-card-line" id="${id}">`);
  });

  it("uses the reader's language", () => {
    expect(links("SchemaGenerator", en)).toContain("Takes: text. Produces: structured data.");
    expect(links("SchemaGenerator", en)).toContain(">Documentation<");
  });

  it("links the first mention of each component only", () => {
    const html = links("Transcriber kirjoittaa puheen tekstiksi. Transcriber ja DataExtractor riittävät.");
    expect(count(html, 'class="cmp-name"')).toBe(2);
    expect(count(html, "Transcriber")).toBe(3); // the name, the card's title, one plain mention
  });

  it("matches whole names, the longest first", () => {
    const html = links("LLMJudgePanel, MyExtractor, Extractors and extractor.");
    expect(count(html, 'class="cmp-name"')).toBe(1);
    expect(html).toContain('<span class="cmp-card-name">LLMJudgePanel</span>');
  });

  it("finds a name written as inline code, in a list and in a table", () => {
    expect(links("Valitsin `DocumentClassifier`-komponentin.")).toContain(
      '<code><span class="cmp"><button',
    );
    expect(count(links("- Retriever\n- Ranker"), 'class="cmp-name"')).toBe(2);
    expect(count(links("| Vaihe | Komponentti |\n| --- | --- |\n| 1 | PyMuPDFParser |"), 'class="cmp-name"')).toBe(1);
  });

  it("leaves links, code blocks and diagrams as they are", () => {
    const inLink = links("[Transcriber](https://example.com/transcriber)");
    expect(inLink).not.toContain("cmp-name");
    const inBlock = links("```python\nfrom gaik import Transcriber\n```");
    expect(inBlock).not.toContain("cmp-name");
    const inDiagram = links("```mermaid\nflowchart LR\n  A[Transcriber] --> B[DataExtractor]\n```");
    expect(inDiagram).not.toContain("cmp-name");
    // A name after the block is still found.
    expect(links("```\nTranscriber\n```\n\nSitten Embedder.")).toContain('<span class="cmp-card-name">Embedder</span>');
  });

  it("changes nothing without labels or without a component", () => {
    const html = renderMarkdown("Ei komponentteja, vain **tekstiä** ja `koodia`.");
    expect(withComponentLinks(html, fi, "m1")).toBe(html);
    const named = renderMarkdown("Transcriber");
    expect(withComponentLinks(named, undefined, "m1")).toBe(named);
  });

  it("gives each card its own id within a message", () => {
    const html = links("Embedder, Retriever ja AnswerGenerator.");
    const ids = [...html.matchAll(/aria-describedby="([^"]+)"/g)].map((m) => m[1]);
    expect(new Set(ids).size).toBe(3);
  });
});

describe("the component catalog", () => {
  it("is in step with the wizard's registry", () => {
    // The registry is beside the web app in the repository; an image built
    // from this folder alone has only the generated file.
    const registryPath = path.resolve(__dirname, "../../solution_wizard/registries/gaik_component_registry.json");
    if (!existsSync(registryPath)) return;
    const registry = JSON.parse(readFileSync(registryPath, "utf8")) as {
      name: string;
      input_artifact_types: string[];
      output_artifact_types: string[];
    }[];
    // A registry change (a new or renamed component) needs no code change
    // here, only the generated file written again.
    const stale = "lib/gaik-components.generated.json is stale: run `npm run component-catalog` and commit it";
    expect(catalog.components.map((c) => c.name).sort(), stale).toEqual(registry.map((c) => c.name).sort());
    for (const entry of registry) {
      const component = componentNamed(entry.name)!;
      expect(component.inputs, entry.name).toEqual(entry.input_artifact_types);
      expect(component.outputs, entry.name).toEqual(entry.output_artifact_types);
      expect(component.docs, entry.name).toMatch(
        /^https:\/\/(github\.com\/GAIK-project\/gaik-toolkit\/blob\/main\/.+\/README\.md|gaik-project\.github\.io\/gaik-toolkit\/toolkit\/[a-z-]+\/)$/,
      );
    }
  });

  for (const locale of LOCALES) {
    it(`${locale}: every component's line is in plain words`, () => {
      const labels = dictionary(locale).chatActivity.components;
      for (const component of catalog.components) {
        const line = componentLine(component, labels);
        expect(line, component.name).not.toMatch(/_/);
        expect(line, component.name).not.toMatch(/\{\w+\}/);
        for (const type of [...component.inputs, ...component.outputs]) {
          expect(labels.artifacts[type], `${component.name}: ${type}`).toBeTruthy();
        }
      }
    });
  }
});

describe("cardPlacement", () => {
  const within = { left: 20, right: 380, top: 100, bottom: 600 };
  const card = { width: 280, height: 110 };

  it("puts the card under the name, at its left edge", () => {
    const name = { left: 40, right: 140, top: 200, bottom: 220 };
    expect(cardPlacement(name, card, within)).toEqual({ left: 40, top: 220, above: false });
  });

  it("moves the card left when the name is near the right edge", () => {
    const name = { left: 300, right: 370, top: 200, bottom: 220 };
    expect(cardPlacement(name, card, within).left).toBe(100);
  });

  it("never starts left of the column, even when the card is wider than it", () => {
    const name = { left: 30, right: 130, top: 200, bottom: 220 };
    expect(cardPlacement(name, { width: 400, height: 110 }, within).left).toBe(20);
  });

  it("goes above the name when the message field is in the way below", () => {
    const name = { left: 40, right: 140, top: 540, bottom: 560 };
    expect(cardPlacement(name, card, within)).toEqual({ left: 40, top: 430, above: true });
  });

  it("stays below when there is no room above either", () => {
    const name = { left: 40, right: 140, top: 150, bottom: 170 };
    const low = { ...within, bottom: 200 };
    expect(cardPlacement(name, card, low).above).toBe(false);
  });
});
