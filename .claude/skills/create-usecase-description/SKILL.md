---
name: create-usecase-description
description: >-
  Creates a use-case description page under guidance_layer/website/content/docs/use-cases/
  following the established GAIK format (business layer → strategy → no-code → code-based →
  components → evaluation → resources). Accepts user-provided context and marks any missing
  sections as Coming Soon. Updates meta.json to register the new page.
argument-hint: "[use-case-name] [context: components, workflow, business value, demo link]"
---

# Create Use-Case Description

Generates a use-case documentation page under `guidance_layer/website/content/docs/use-cases/` following the structure and style established by `incident-reporting.mdx` (gold-standard reference — read it before generating any content).

**Requires user-provided context** — the user supplies the use-case details (business value, workflow, components, example output, demo link). This skill structures and formats that content into a properly formatted MDX page. It does not invent content beyond what the user provides.

**Handles both new pages and stub promotion** — if a Coming Soon stub already exists for this use case, it promotes it to a full page.

---

## What this skill creates

| File | Action |
|------|--------|
| `guidance_layer/website/content/docs/use-cases/{slug}.mdx` | Create (new) or promote (stub → full) |
| `guidance_layer/website/content/docs/use-cases/meta.json` | Update if slug not yet registered |

---

## Workflow

### Phase 1 — Context Parsing

1. **Read `incident-reporting.mdx`** — the gold-standard reference. Understand its exact structure, heading names, value-type format, diagram style, step format, and evaluation link format before generating anything.
2. Derive the page slug from the use-case name (lowercase, hyphens, e.g. `construction-site-diary-creation`).
3. Check whether a `.mdx` file already exists for this slug:
   - **Fully documented** → warn the user and ask for explicit confirmation before overwriting.
   - **Stub** → proceed; the stub will be replaced.
   - **Does not exist** → create new.
4. Map the user-provided context against the **required and optional sections** defined in `references/mdx-template.md`.
5. For each section where no context was provided, ask:
   > "No content for **[Section Name]**. Supply it now, or mark it Coming Soon?"
   - User supplies → incorporate before generating.
   - User skips → section gets `<Callout type="warn">**Coming Soon:** [one-sentence placeholder]</Callout>`
6. Ask once: **"Is there a live demo link to include?"**
   - If yes → add `<Callout type="info">` with the link near the end of the Software Module section, matching the incident-reporting pattern.

### Phase 2 — Outline

Present a section-by-section status table before writing anything:

```
Section                                    Status
────────────────────────────────────────── ──────────
Frontmatter + H1 heading                   ✅
Intro paragraph                            ✅ / Coming Soon
Business layer                             ✅ / Coming Soon
Strategy layer                             ✅ / Coming Soon
Implementation — No-Code                   ✅ / Coming Soon
  (Structure A: single asset)              or
  (Structure B: Prompt-based + Claude Skill)
Implementation — Code-Based (diagram)      ✅ / Coming Soon
Software Components (N GAIK components)    ✅ / Coming Soon
  Downstream tasks subsection              ✅ / omit
Defining What to Extract                   ✅ / omit
Software Module (diagram + outputs)        ✅ / Coming Soon / omit
Adaptable to Other Domains                 ✅ / Coming Soon
Evaluation Methods                         ✅ / Coming Soon
Related Resources                          ✅
meta.json                                  update / no change needed
```

### Phase 3 — Plan Review *(never skip)*

Present the outline to the user and wait for explicit approval before writing any files. Adjust based on feedback.

### Phase 4 — Generate Content

Run both sub-steps in order. Do not commit.

**4a — MDX Page**

Follow `references/mdx-template.md` for the exact section order, heading names, and formatting rules. All diagrams follow `references/mermaid-guide.md`.

**Opening (before first H2):**

```mdx
---
title: {Use Case Display Name}
description: {One-sentence description}
---
# {Use Case Display Name} Generic Use Case (Cross-Cutting Use Case)

{1–2 sentence business context intro.}
```

The H1 heading always ends with "Generic Use Case (Cross-Cutting Use Case)".

**Business layer (`## Business layer – use case specification`):**
- Opening paragraph describing what the use case covers and who the users are
- Bullet list: "Concrete example fragments reflected in the use case design include:" — 3–5 bullets describing the scenario
- Closing sentence explaining what the canvas provides
- Canvas image reference: `![GenAI Product Description for {Use Case}](/images/{filename}.png)` — if image provided
- PowerPoint download link — if provided

**Strategy layer (`## Strategy layer – value evaluation and monitoring`):**
- Link to the Value Evaluation Framework
- Value type blocks, each formatted exactly as:
  ```
  {Value type} value (primary / secondary):
  "Fragment 1", "Fragment 2", "Fragment 3"
  → Outcome: {outcome sentence}
  ```
  Use **however many value types the user-provided value model contains** — the model may include 3 (Functional, Informational, Emotional) or up to 5–6 (also Financial, Social, Operational, etc.). Do not limit to exactly 3.
- Value evaluation image — if provided
- PowerPoint download link — if provided
- Closing sentence about using the model before and after deployment

**Implementation — No-Code (`## Implementation layer using No-Code`):**

This section can take two different structures depending on what no-code assets exist for the use case.

*Structure A — Single asset (one Claude Skill or one set of prompt templates):*
- Opening paragraph
- Numbered list of 1–3 GitHub asset links (prompt templates, agent skills)
- Explanation of what the no-code assets do
- **"What the business user sets up (once):"** — prose + bullet list
- **"What happens in daily work:"** — numbered steps with bold `**Step N – description**` headers and nested bullets
- **"Example of what the business gets out:"** — intro sentence + structured bullet list of output fields
- Closing 4-bullet list: easy to paste / safe to store / reliable for analytics / suitable for audits

*Structure B — Two co-existing approaches (prompt-based AND Claude Skill):*
- Opening paragraph introducing both approaches and when to use each
- `### Prompt-based approach` subsection — describe the prompt(s) briefly, what they do, GitHub link
- `### Claude Skill` subsection — brief introduction (2–4 sentences) covering what it does, when to prefer it over the prompt-based approach, and GitHub link; **do not** include detailed setup steps or daily workflow — link to the documentation instead
- Use **"Claude Skill"** as the term — not "Claude Desktop agent skill", not "Claude Desktop Skill"

Use Structure B when both `implementation_layer/no-code-assets/prompts/` and `implementation_layer/no-code-assets/agent-skills/` assets exist for the use case. Use Structure A for all other cases.

**Implementation — Code-Based (`## Implementation Layer Using Code-Based Method.`):**
- Note: heading ends with a period — match exactly
- 1–2 sentence overview naming the GAIK components used and noting any downstream (non-GenAI) steps
- `flowchart LR` Mermaid diagram with subgraph for the GAIK extraction pipeline — follow `references/mermaid-guide.md` diagram style (emojis, stroke colors, subgraph pattern)
- If the pipeline output feeds into downstream org-specific steps (pricing, ERP, document generation), add a downstream node **after** the GAIK output in the diagram, styled yellow (`fill:#fefce8`) or green (`fill:#dcfce7`), and labelled clearly as downstream/org-specific
- `---` divider after this section

**Software Components (`## Software Components`):**
- **Only list actual GAIK software components** — i.e. classes/modules from `implementation_layer/src/gaik/software_components/` or `software_modules/`. Do NOT list business-specific logic (pricing calculators, PDF renderers, ERP connectors) as software components — these belong in the "Downstream tasks" subsection instead.
- One `###` per component, numbered: `### 1. ComponentName`
- Each component gets:
  1. 2–3 sentence description
  2. `flowchart LR` or `flowchart TD` Mermaid diagram with subgraph — use emojis and stroke colors
  3. GitHub source link: `> 📁 [\`path/to/component/\`](https://github.com/GAIK-project/gaik-toolkit/tree/main/...)`
  4. `---` divider after each component

**Downstream tasks (`### Downstream tasks`)** *(add when the use case involves post-extraction non-GenAI steps)*:
- Add this unnumbered subsection after the last software component when the pipeline output feeds into business-specific or conventional (non-AI) processing steps
- Describe what happens to the structured output: price calculation, document generation, ERP integration, database storage, etc.
- Clarify that these steps are outside the GenAI pipeline and may require organisation-specific customisation
- Do NOT add a diagram for downstream tasks — prose only

**Defining What to Extract (`## Defining What to Extract: User Requirements`)** *(include when the use case involves schema-guided extraction with user-defined fields; omit for other use cases)*:
- 1–2 sentence intro explaining that fields are specified in plain language
- Plain-text code block showing the field specification in the exact format used in `incident-reporting.mdx` (field name + optional constraint in brackets, followed by output rules)
- Output rules as a bullet list inside the code block

**Software Module (`## Software Module: {ModuleName}`)** *(if a combined GAIK module is used)*:
- 1–2 sentence description
- `flowchart TD` Mermaid diagram with nested subgraphs (Step 1, Step 2 pattern) — follow incident-reporting pattern
- Example output: if screenshot images are available, use side-by-side JSX:
  ```jsx
  <p>
    <img src="/gaik-toolkit/images/image1.png" alt="..." style={{ width: "45%", height: "auto", display: "inline-block" }} />
    <img src="/gaik-toolkit/images/image2.png" alt="..." style={{ width: "45%", height: "auto", display: "inline-block" }} />
  </p>
  ```
- GitHub module and examples links with `📁` prefix
- Demo link as inline text: "To test ... please visit the [GAIK demo link](...)"
- `---` divider after this section

**Adaptable to Other Domains (`## Adaptable to Other Domains`):**
- 1 sentence framing
- Single bullet line listing 3–5 domains, comma-separated
- `---` divider after

**Evaluation Methods (`## Evaluation Methods`):**
- Opening sentence: "The quality of this use case is evaluated by assessing each software component independently:"
- One `###` per evaluator. Each gets:
  - 1–2 sentence description of what is measured and the key metric
  - `> 📊 **{Title}:** [\`path/\`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/eval_methods/{folder}/)` link
- `---` divider after

**Related Resources (`## Related Resources`):**
- 2-column Markdown table — `| Resource | Link |` — **NOT 3 columns**
- List all key components, modules, examples, canvas, and implementation layer overview

**General rules:**
- `---` horizontal dividers between all major H2 sections
- Missing sections → `<Callout type="warn">**Coming Soon:** [placeholder]</Callout>`

**4b — Update `meta.json`**

If the slug is not already in `guidance_layer/website/content/docs/use-cases/meta.json`, insert it in the `pages` array at the appropriate position.

### Phase 5 — Verification Summary

After writing, print:

```
Files created / modified:
  ✓ guidance_layer/website/content/docs/use-cases/{slug}.mdx  (N lines)
  ✓ guidance_layer/website/content/docs/use-cases/meta.json   (updated / unchanged)

Sections marked Coming Soon: [list or "none"]

To verify:
  cd guidance_layer/website && pnpm dev
  → /use-cases/{slug}   (confirm renders, all Mermaid diagrams visible)
```

---

## Hard Rules

- **Never skip Phase 3.** Always wait for explicit approval before writing any files.
- **Never overwrite a fully-documented page** without explicit user confirmation.
- **`meta.json` slug must exactly match the `.mdx` filename** (minus `.mdx`). A mismatch silently breaks sidebar navigation.
- **`<Callout type="warn">` only for Coming Soon sections.** Use `<Callout type="info">` for demo links and helpful tips.
- **Do not commit.** Leave all changes uncommitted for user review.
- **Do not fabricate content.** Only generate diagrams, code, and prose derivable from the user-provided context. Generic placeholders must be clearly marked.
- **Mermaid must use `flowchart` keyword** (not `graph`). Use subgraphs, emojis in labels, and `stroke:` colors per `references/mermaid-guide.md`. Test mentally that all node IDs are unique and subgraph blocks are closed.
- **H1 heading always ends with "Generic Use Case (Cross-Cutting Use Case)".**
- **Related Resources table is 2 columns** (`Resource | Link`), not 3.
- **Use cases must be generic.** Never mention a specific company name, organization name, client name, or proprietary product name. If the user's context references a named organization, replace it with a generic description (e.g. "a manufacturing company", "an enterprise client", "a partner organization"). This applies to all sections.

---

## References

- `references/mdx-template.md` — canonical section order, heading names, value-type format, diagram templates, evaluation link format
- `references/mermaid-guide.md` — `flowchart` syntax, subgraph patterns, emoji usage, stroke color conventions

**Pattern references (read before generating — do not skip):**
- `guidance_layer/website/content/docs/use-cases/incident-reporting.mdx` — gold-standard reference; follow its structure, style, and diagram approach exactly
- `guidance_layer/website/content/docs/use-cases/purchase-order-processing.mdx` — alternative component set
- `guidance_layer/website/content/docs/use-cases/dental-transcription-close-captioning.mdx` — shorter format
