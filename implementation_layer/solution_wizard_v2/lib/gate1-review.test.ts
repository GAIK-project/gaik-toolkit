import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Gate1Review } from "@/components/gate1-review";
import { dictionary } from "./i18n";

const fi = dictionary("fi");
const en = dictionary("en");

const render = (props: Partial<Parameters<typeof Gate1Review>[0]>, t = fi) =>
  renderToStaticMarkup(createElement(Gate1Review, { points: [], answers: [], t, ...props }));

/** The page's text without its markup. */
const textOf = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ");

describe("Gate1Review", () => {
  it("says so when the wizard has recorded nothing, in place of an empty sheet", () => {
    const html = render({ businessContext: null, assumptions: [] });
    expect(html).toContain('data-testid="gate1-review-empty"');
    expect(html).toContain(fi.gate1ReviewEmpty);
    expect(html).not.toContain('data-testid="gate1-review"');
  });

  it("shows the agent's identifiers in plain words, in both languages", () => {
    const props = {
      businessContext: {
        currentProcess: "Invoices are typed in by hand.",
        painPoints: [],
        intendedUsers: [],
        reviewers: [],
        expectedValue: ["Less typing"],
        knowledgeProcesses: ["knowledge_capture", "knowledge_access", "audit_trail"],
        domain: "accounts_payable",
      },
      assumptions: [
        { id: "a1", text: "PDF only.", status: "unconfirmed" as const, impact: "component_selection" },
        { id: "a2", text: "EUR only.", status: "confirmed" as const, impact: "schema" },
        { id: "a3", text: "Six years.", status: "confirmed" as const, impact: "data_retention_policy" },
      ],
    };
    const inFinnish = textOf(render(props));
    expect(inFinnish).toContain("Toimiala: Accounts payable");
    // Each known process stands with one plain line on what it means.
    expect(inFinnish).toContain(`Tiedon tallentaminen ${fi.bcKnowledgeProcessHelp.knowledge_capture}`);
    expect(inFinnish).toContain(`Tiedon haku ${fi.bcKnowledgeProcessHelp.knowledge_access}`);
    expect(inFinnish).toContain("Audit trail");
    expect(inFinnish).toContain("Vaikutus: komponenttien valinta");
    expect(inFinnish).toContain("Vaikutus: tietorakenne");
    expect(inFinnish).toContain("Vaikutus: data retention policy");
    expect(inFinnish).not.toMatch(/[a-z]_[a-z]/);

    const inEnglish = textOf(render(props, en));
    expect(inEnglish).toContain(`Capturing knowledge ${en.bcKnowledgeProcessHelp.knowledge_capture}`);
    expect(inEnglish).toContain(`Finding knowledge ${en.bcKnowledgeProcessHelp.knowledge_access}`);
    expect(inEnglish).toContain("Audit trail");
    expect(inEnglish).toContain("Affects: component selection");
    expect(inEnglish).not.toMatch(/[a-z]_[a-z]/);
  });

  it("gives each assumption one status and lists what is not known as rows that can be filled in", () => {
    const html = render({
      businessContext: {
        currentProcess: "unknown",
        painPoints: [],
        intendedUsers: ["Finance team"],
        reviewers: [],
        expectedValue: ["Less typing"],
        knowledgeProcesses: [],
        domain: "",
      },
      assumptions: [
        { id: "a1", text: "PDF only.", status: "unconfirmed", impact: "" },
        { id: "a2", text: "EUR only.", status: "confirmed", impact: "low" },
      ],
    });
    expect(html.match(/data-testid="assumption-status"/g)).toHaveLength(2);
    // Each missing item is a row of the list, with the control that adds it.
    expect(html.match(/data-testid="bc-not-known"/g)).toHaveLength(2);
    expect(textOf(html)).toContain(`${fi.bcCurrentProcess} ${fi.bcAdd} ${fi.bcNotKnown}`);
    for (const item of [fi.bcCurrentProcess, fi.bcPainPoints]) {
      expect(html).toContain(`aria-label="${fi.bcAddItem.replace("{item}", item)}"`);
    }
    expect(html).not.toContain(`aria-label="${fi.bcAddItem.replace("{item}", fi.bcExpectedValue)}"`);
    // One sheet: no card inside it.
    expect(html.match(/rounded-xl/g)).toHaveLength(1);
    // The requirement list is the mock store's: without points it is left out.
    expect(html).not.toContain(fi.gate1ChecklistTitle);
  });

  it("gives every assumption and business-context item a control that is always in view", () => {
    const html = render({
      businessContext: {
        currentProcess: "Invoices are typed in by hand.",
        painPoints: [],
        intendedUsers: [],
        reviewers: [],
        expectedValue: ["Less typing"],
        knowledgeProcesses: [],
        domain: "",
      },
      assumptions: [
        { id: "a1", text: "PDF only.", status: "unconfirmed", impact: "" },
        { id: "a2", text: "EUR only.", status: "confirmed", impact: "low" },
      ],
    });
    for (const name of ["Muuta: Oletus 1", "Muuta: Oletus 2", "Muuta: Nykyprosessi", "Muuta: Odotettu arvo"]) {
      expect(html).toContain(`aria-label="${name}"`);
    }
    // Nothing waits for a pointer to hover: a touch screen has none.
    expect(html).not.toMatch(/group-hover|opacity-0/);
    // The field opens on a press; until then the sheet has no form.
    expect(html).not.toContain("<form");
  });

  it("numbers an assumption once: the list's own number, with none written into the row", () => {
    const html = render({
      assumptions: [
        { id: "a1", text: "User skipped the question about languages.", status: "unconfirmed", impact: "requirements" },
        { id: "a2", text: "EUR only.", status: "confirmed", impact: "" },
      ],
    });
    // An ordered list, so its items are numbered by the list itself.
    expect(html).toMatch(/<ol[^>]*data-testid="gate1-assumptions"/);
    // The number in view is drawn from an attribute: it is not text in the row.
    expect(html).toContain('data-n="1."');
    expect(html).toContain('data-n="2."');
    const text = textOf(html);
    expect(text).not.toMatch(/\d\.\s*User skipped/);
    // The row's parts are apart: the text, then the status and what it affects.
    expect(text).toContain("User skipped the question about languages. Vahvistamaton · Vaikutus: vaatimukset");
    expect(html.match(/data-testid="assumption-impact"/g)).toHaveLength(1);
  });

  it("shows what an assumption affects in the page's words, and an unknown value as written", () => {
    const impactOf = (impact: string, t = fi) =>
      textOf(render({ assumptions: [{ id: "a1", text: "PDF only.", status: "unconfirmed", impact }] }, t));
    expect(impactOf("requirements")).toContain("Vaikutus: vaatimukset");
    expect(impactOf("data structure")).toContain("Vaikutus: tietorakenne");
    expect(impactOf("Component Selection")).toContain("Vaikutus: komponenttien valinta");
    expect(impactOf("workflow")).toContain("Vaikutus: työnkulku");
    expect(impactOf("workflow", en)).toContain("Affects: workflow");
    expect(impactOf("data structure", en)).toContain("Affects: data structure");
    expect(impactOf("Pricing rules")).toContain("Vaikutus: Pricing rules");
    expect(impactOf("  ")).not.toContain("Vaikutus");
  });

  it("lists a knowledge process once, also when the agent names it twice in different words", () => {
    const text = textOf(
      render({
        businessContext: {
          currentProcess: "By hand.",
          painPoints: [],
          intendedUsers: [],
          reviewers: [],
          expectedValue: ["Less typing"],
          knowledgeProcesses: ["knowledge_capture", "Knowledge capture", "unknown"],
          domain: "",
        },
      }),
    );
    expect(text.match(/Tiedon tallentaminen/g)).toHaveLength(1);
    expect(text).toContain(fi.bcKnowledgeProcessHelp.knowledge_capture);
  });
});
