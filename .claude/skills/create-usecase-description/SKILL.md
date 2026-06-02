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

Generates a use-case documentation page under `guidance_layer/website/content/docs/use-cases/` following the structure established by `incident-reporting.mdx` and `purchase-order-processing.mdx`.

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

1. Derive the page slug from the use-case name (lowercase, hyphens, e.g. `construction-site-diary-creation`).
2. Check whether a `.mdx` file already exists for this slug. If so, read it — determine if it is a stub (Coming Soon) or already fully documented.
   - **Fully documented** → warn the user and ask for explicit confirmation before overwriting.
   - **Stub** → proceed; the stub will be replaced.
   - **Does not exist** → create new.
3. Map the user-provided context against the **required and optional sections** defined in `references/mdx-template.md`.
4. For each section where no context was provided, ask:
   > "No content for **[Section Name]**. Supply it now, or mark it Coming Soon?"
   - User supplies → incorporate before generating.
   - User skips → section gets `<Callout type="warn">**Coming Soon:** [one-sentence placeholder describing what will be here]</Callout>`
5. Ask once: **"Is there a live demo link to include?"**
   - If yes → add `<Callout type="info">` with the link at the top of the page.

### Phase 2 — Outline

Present a section-by-section status table before writing anything:

```
Section                                Status
────────────────────────────────────── ──────────
Frontmatter (title, description)       ✅
Intro paragraph                        ✅ / Coming Soon
Live demo Callout                      ✅ / omit
Business layer                         ✅ / Coming Soon
Strategy layer                         ✅ / Coming Soon
Implementation — No-Code               ✅ / Coming Soon
Implementation — Code-Based            ✅ / Coming Soon
Software Components (N components)     ✅ / Coming Soon
Defining What to Extract               ✅ / Coming Soon / omit
Software Module                        ✅ / Coming Soon / omit
Adaptable to Other Domains             ✅ / Coming Soon
Evaluation Methods                     ✅ / Coming Soon
Related Resources                      ✅
meta.json                              update / no change needed
```

### Phase 3 — Plan Review *(never skip)*

Present the outline to the user and wait for explicit approval before writing any files. Adjust based on feedback.

### Phase 4 — Generate Content

Run both sub-steps in order. Do not commit.

**4a — MDX Page**

Follow `references/mdx-template.md` for exact section order, heading names, and formatting. Key rules:

- **Frontmatter**: only `title` and `description` — no other keys
- **Intro paragraph**: 1–2 sentences of business context, before the first H2
- **Demo Callout**: if a demo link exists, place `<Callout type="info">` immediately after the intro, before the first H2
- **Business layer**: canvas framing, concrete example bullet fragments (what the employee/user does), value outcomes grouped as functional / informational / emotional. Reference canvas image + PowerPoint download if provided.
- **Strategy layer**: value evaluation links. If not yet available, use `<Callout type="info">` to note where the framework link will go.
- **Implementation — No-Code**: written for non-technical business users. Structure as:
  - "What the business user sets up (once)" — bullet or numbered list
  - "What happens in daily work" — numbered steps
  - "Example of what the business gets out" — bullet list of output fields or result description
- **Implementation — Code-Based**: Mermaid LR flowchart of the full data pipeline, followed by prose naming the components. Follow `references/mermaid-guide.md` for color coding.
- **Software Components**: one `###` per component, in pipeline order. Each gets:
  1. 2–3 sentence prose description
  2. Mermaid diagram (LR for simple, TD for multi-step internal pipeline)
  3. Minimal Python usage example (5–15 lines, real imports)
  4. GitHub source link: `> 📁 [Source →](https://github.com/GAIK-project/gaik-toolkit/tree/main/...)`
- **Defining What to Extract** *(extraction use cases only)*: show plain-text requirements spec as a code block, followed by output rules as a bullet list
- **Software Module** *(if a combined GAIK module is used)*: Mermaid TD with subgraph nesting for the full module workflow; follow incident-reporting pattern for `AudioToStructuredData` or `DocumentsToStructuredData`
- **Adaptable to Other Domains**: 3–5 bullet examples of other contexts where the same pipeline applies
- **Evaluation Methods**: one `###` per relevant evaluator with a link to the `/toolkit/evals/` page and the GitHub eval folder
- **Related Resources**: 3-column Markdown table — `| Resource | Link | Notes |`
- `---` horizontal dividers between all major H2 sections
- Missing sections → `<Callout type="warn">**Coming Soon:** [placeholder]</Callout>` — never leave a section empty

**4b — Update `meta.json`**

If the slug is not already in `guidance_layer/website/content/docs/use-cases/meta.json`, insert it in the `pages` array at the appropriate position (after the last fully-documented page, before remaining stubs — or at the end if all pages are documented).

### Phase 5 — Verification Summary

After writing, print:

```
Files created / modified:
  ✓ guidance_layer/website/content/docs/use-cases/{slug}.mdx  (N lines)
  ✓ guidance_layer/website/content/docs/use-cases/meta.json   (updated / unchanged)

Sections marked Coming Soon: [list or "none"]

To verify:
  cd guidance_layer/website && pnpm dev
  → /use-cases/{slug}   (confirm renders, Mermaid diagrams visible, no Callout warn errors)
```

---

## Hard Rules

- **Never skip Phase 3.** Always wait for explicit approval before writing any files.
- **Never overwrite a fully-documented page** without explicit user confirmation.
- **`meta.json` slug must exactly match the `.mdx` filename** (minus `.mdx`). A mismatch silently breaks sidebar navigation.
- **`<Callout type="warn">` only for Coming Soon sections.** Use `<Callout type="info">` for demo links and helpful tips. Full pages must not have a top-level Coming Soon Callout.
- **Do not commit.** Leave all changes uncommitted for user review.
- **Do not fabricate content.** Only generate Mermaid diagrams, code examples, and prose that are directly derivable from the user-provided context. Generic placeholders must be clearly marked.
- **Mermaid syntax must be valid.** Test mentally that node IDs are unique, arrow syntax is correct, and subgraph blocks are closed. Follow `references/mermaid-guide.md`.

---

## References

- `references/mdx-template.md` — canonical 10-section page structure: heading names, order, when each section is required vs. optional, formatting rules, Callout usage, table format, GitHub link patterns
- `references/mermaid-guide.md` — GAIK color palette, LR vs. TD orientation rules, subgraph nesting pattern, node label conventions, and skeleton diagrams for common pipeline shapes

Pattern references (read when in doubt):
- `guidance_layer/website/content/docs/use-cases/incident-reporting.mdx` — most complete, gold-standard reference
- `guidance_layer/website/content/docs/use-cases/purchase-order-processing.mdx` — alternative component set, Callout usage
- `guidance_layer/website/content/docs/use-cases/dental-transcription-close-captioning.mdx` — shorter, feature-focused format
