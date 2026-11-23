import { describe, expect, it } from "vitest";
import { captionHtml, laneHeaderCaptionHtml, stepAboveCaptionHtml } from "./caption-html";

describe("captionHtml", () => {
  it("renders the short text, escapes the full text, and defaults to the step variant", () => {
    const html = captionHtml({ short: "Review", full: 'Manager <review> & "sign-off"' });
    expect(html).toContain("bpmn-caption--step");
    expect(html).toContain(">Review<");
    expect(html).toContain("Manager &lt;review&gt; &amp; &quot;sign-off&quot;");
  });

  it("adds an inline width style only when width is given", () => {
    expect(captionHtml({ short: "A", full: "A" })).not.toContain("style=");
    expect(captionHtml({ short: "A", full: "A", width: 120 })).toContain(
      'style="width:120px;max-width:120px"',
    );
  });

  it("supports the lane and pool variants", () => {
    expect(captionHtml({ short: "L", full: "L", variant: "lane" })).toContain(
      "bpmn-caption--lane",
    );
  });
});

describe("laneHeaderCaptionHtml", () => {
  it("joins multi-line lane names and sets the fixed width", () => {
    const html = laneHeaderCaptionHtml("Customer\nservice", 200);
    expect(html).toContain("Customer · service");
    expect(html).toContain("width:200px");
  });
});

describe("stepAboveCaptionHtml", () => {
  it("renders one span per caption line and marks bracketed component lines", () => {
    const html = stepAboveCaptionHtml("Retrieval\n[RAG]", 150);
    expect(html).toContain('class="bpmn-caption__line">Retrieval<');
    expect(html).toContain('bpmn-caption__line--component">[RAG]<');
  });

  it("infers a role suffix line for a single-line UserTask name", () => {
    const html = stepAboveCaptionHtml("Manager review", 150, "bpmn:UserTask");
    expect(html).toContain("Manager review");
    expect(html).toContain("[Human review]");
  });
});
