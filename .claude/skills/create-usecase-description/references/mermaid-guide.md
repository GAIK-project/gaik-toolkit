# Mermaid Diagram Guide — GAIK Use-Case Pages

All Mermaid diagrams in GAIK use-case pages use the `flowchart` keyword (not `graph`), include emojis in node labels, and apply `stroke:` colors in style lines. Follow `incident-reporting.mdx` as the exact reference for diagram style.

---

## Keyword

Always use `flowchart`, never `graph`:

```
flowchart LR   ← linear pipelines
flowchart TD   ← multi-step internal pipelines, module diagrams
```

---

## Color Palette

| Role | Fill | Stroke | Text | Usage |
|------|------|--------|------|-------|
| **Input** | `#dbeafe` | `#3b82f6` | `#1e3a5f` | Audio files, documents, user requirements |
| **Processing subgraph** | `#f5f3ff` | `#7c3aed` | `#2e1065` | Individual components (Transcriber, Extractor) |
| **Module wrapper** | `#f0f4ff` | `#6366f1` | `#1e1b4b` | Top-level software module container |
| **Nested step subgraph** | `#faf5ff` | `#9333ea` | `#2e1065` | Step 1, Step 2 inside a module |
| **Final output** | `#dcfce7` | `#16a34a` | `#14532d` | Structured results, validated data, schemas |
| **Intermediate output** | `#fefce8` | `#ca8a04` | `#713f12` | Raw transcript, partially processed data |

Apply as: `style NodeId fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f`

Optional steps use: `style NodeId stroke-dasharray: 5 5`

---

## Node Emojis

Use emojis to make nodes visually scannable — match these conventions:

| Emoji | Use for |
|-------|---------|
| 🎙️ | Audio input, voice recording |
| 📋 | Configuration, requirements, field specs |
| 📄 | Text output, raw transcript |
| ✨ | Enhanced/processed output |
| ✅ | Final structured output, validated result |
| 🗂️ | Schema, reusable artifact |
| 🤖 | AI/LLM processing step |
| 🎧 | Transcription model step |

---

## Orientation Rules

| Use when | Directive |
|----------|-----------|
| Linear A → B → C pipeline | `flowchart LR` |
| Component with internal stages | `flowchart TD` inside a subgraph |
| Module with multiple sub-components | `flowchart TD` with nested subgraphs |

---

## Node Shape Conventions

| Shape | Syntax | Usage |
|-------|--------|-------|
| Rounded rectangle | `A("Label")` | All nodes — preferred throughout |
| Bracket rectangle | `A["Label"]` | Internal sub-step nodes inside subgraphs |

Use `("Label")` for inputs/outputs and `["Label"]` for internal processing steps.

---

## Diagram Skeletons

### 1. Module Overview — `flowchart LR` with subgraph (Code-Based section)

```mermaid
flowchart LR
    A("🎙️ Audio Recording") --> B

    subgraph B["Audio to Structured Data"]
        direction TB
        T["🎧 Transcriber<br/>Speech-to-Text"]
        E["✨ AI Enhancement (optional)<br/>Clean & Format Transcript"]
        X["🤖 Extractor<br/>Structured Field Extraction"]
        T --> E --> X
    end

    C("📋 Field Requirements<br/>Plain language description") --> B
    B --> D("✅ Structured Output")

    style A fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style C fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style D fill:#dcfce7,stroke:#16a34a,color:#14532d
    style B fill:#f0f4ff,stroke:#6366f1,color:#1e1b4b
    style E stroke-dasharray: 5 5
```

### 2. Component with Two Outputs — `flowchart LR` (Software Components section)

```mermaid
flowchart LR
    A("🎙️ Audio File<br/>e.g. recording.mp3") --> B

    subgraph B["Transcriber"]
        direction TB
        W["Transcription Model<br/>Speech-to-Text"]
        G["Enhancement<br/>Clean & Format"]
        W --> G
    end

    B --> C("📄 Raw Transcript")
    B --> D("✨ Enhanced Transcript")

    style A fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style C fill:#fefce8,stroke:#ca8a04,color:#713f12
    style D fill:#dcfce7,stroke:#16a34a,color:#14532d
    style B fill:#f5f3ff,stroke:#7c3aed,color:#2e1065
```

### 3. Multi-Step Component — `flowchart TD` (Software Components section)

```mermaid
flowchart TD
    A("📄 Transcript Text") --> DE
    B("📋 User Requirements<br/>Plain language field definitions") --> RP

    subgraph EXT["Extractor"]
        direction TB
        RP["Requirement Parser<br/>Identify fields & constraints"]
        SG["Schema Generator<br/>Build typed data schema"]
        DE["Data Extractor<br/>LLM-powered field extraction"]
        RP -.->|"parsed fields"| SG
        SG -.->|"typed schema"| DE
    end

    EXT --> C("✅ Structured Fields")
    EXT --> D("🗂️ Generated Schema<br/>Reusable for future runs")

    style A fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style B fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style C fill:#dcfce7,stroke:#16a34a,color:#14532d
    style D fill:#dcfce7,stroke:#16a34a,color:#14532d
    style EXT fill:#f5f3ff,stroke:#7c3aed,color:#2e1065
```

### 4. Full Module — `flowchart TD` with nested subgraphs (Software Module section)

```mermaid
flowchart TD
    IN1("🎙️ Audio File") --> MOD
    IN2("📋 User Requirements") --> MOD

    subgraph MOD["Audio-to-Structured-Data"]
        direction TB

        subgraph T["Step 1 · Transcriber"]
            direction LR
            W["Transcription Model<br/>Speech-to-Text"] --> G["Transcript<br/>Enhancement"]
        end

        subgraph X["Step 2 · Extractor"]
            direction LR
            RP["Requirement<br/>Parser"] --> SG["Schema<br/>Generator"] --> DE["Data<br/>Extractor"]
        end

        T -->|"transcript text"| X
    end

    MOD --> O1("📄 Raw Transcript")
    MOD --> O2("✨ Enhanced Transcript")
    MOD --> O3("✅ Structured Output")
    MOD --> O4("🗂️ Reusable Schema")

    style IN1 fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style IN2 fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style O1 fill:#fefce8,stroke:#ca8a04,color:#713f12
    style O2 fill:#fefce8,stroke:#ca8a04,color:#713f12
    style O3 fill:#dcfce7,stroke:#16a34a,color:#14532d
    style O4 fill:#dcfce7,stroke:#16a34a,color:#14532d
    style MOD fill:#f0f4ff,stroke:#6366f1,color:#1e1b4b
    style T fill:#faf5ff,stroke:#9333ea,color:#2e1065
    style X fill:#faf5ff,stroke:#9333ea,color:#2e1065
```

---

## Syntax Rules

- **Always** `flowchart LR` or `flowchart TD` — never just `flowchart` or `graph`
- **Node IDs** — short alphanumeric: `A`, `B`, `IN1`, `RP`, `MOD`
- **Labels** — wrap in `("...")` for inputs/outputs, `["..."]` for internal steps
- **Line breaks in labels** — use `<br/>` inside quoted labels
- **`direction TB`** — add inside every subgraph to control internal flow direction
- **Style lines** — one per node, always after all arrows
- **Subgraph syntax** — `subgraph ID["Display Label"]` ... `end`; title in quotes if it contains spaces
- **No semicolons** required
- **Optional steps** — use `stroke-dasharray: 5 5` in the style line

---

## Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| Using `graph LR` | Use `flowchart LR` |
| Missing stroke color in style | Always include both `fill:` and `stroke:` |
| Subgraph without `direction TB` | Add `direction TB` as first line inside subgraph |
| Node ID reused | Use unique IDs: `IN1`, `IN2`, `O1`, `O2` |
| Unclosed subgraph | Every `subgraph` block needs a matching `end` |
| Style applied before arrows | Put all `style` lines after all arrow definitions |
