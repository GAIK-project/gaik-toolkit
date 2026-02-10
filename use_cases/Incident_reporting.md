# Incident Report Writing Use Case

## Business Context

In industrial environments, employees must report unusual events — equipment failures, leaks, injuries, near-misses — accurately and promptly. Traditional methods (manual notes or online forms) create friction that leads to underreporting and incomplete data.

This use case lets an employee **record a voice message** at the scene, and the system automatically extracts all required fields to generate a structured incident report. Reporting friction reduces to a single step: **press record, describe, submit**.

---

## How GAIK Toolkit Enables This Use Case

Two software components — **Transcriber** and **Extractor** — are combined into the **Audio to Structured Data** module to handle this use case end-to-end.

```mermaid
flowchart LR
    A("🎙️ Audio Recording") --> B["Audio to Structured Data"]
    C("📋 Field Requirements<br/>Plain language description") --> B
    B --> D("✅ Structured Incident Report")

    style A fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style C fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style D fill:#dcfce7,stroke:#16a34a,color:#14532d
    style B fill:#f0f4ff,stroke:#6366f1,color:#1e1b4b
```

---

## Software Components

### 1. Transcriber

Converts an audio recording into text using OpenAI's speech-to-text model, with an enhancement step that cleans up the raw transcript — correcting speech artefacts and improving readability.

```mermaid
flowchart LR
    A("🎙️ Audio File<br/>e.g. incident_recording.mp3") --> B

    subgraph B["Transcriber"]
        direction TB
        W["Transcription Model<br/>Speech-to-Text"]
        G["Enhancement<br/>Clean & Format"]
        W --> G
    end

    B --> C("📄 Raw Transcript<br/>Direct output of transcription model")
    B --> D("✨ Enhanced Transcript<br/>Formatted, readable text")

    style A fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style C fill:#fefce8,stroke:#ca8a04,color:#713f12
    style D fill:#dcfce7,stroke:#16a34a,color:#14532d
    style B fill:#f5f3ff,stroke:#7c3aed,color:#2e1065
```

> 📁 [`implementation_layer/src/gaik/software_components/transcriber/`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/transcriber)

---

### 2. Extractor

Takes the transcript and a plain-language field specification, then returns structured data. Internally it runs three steps: the **Requirement Parser** identifies fields and constraints from your description; the **Schema Generator** builds a typed data schema; the **Data Extractor** uses an LLM to fill in each field from the transcript.

The schema is generated once and **saved for reuse** — future reports skip regeneration entirely.

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

    EXT --> C("✅ Structured Fields<br/>Report type, observer, location…")
    EXT --> D("🗂️ Generated Schema<br/>Reusable for future reports")

    style A fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style B fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f
    style C fill:#dcfce7,stroke:#16a34a,color:#14532d
    style D fill:#dcfce7,stroke:#16a34a,color:#14532d
    style EXT fill:#f5f3ff,stroke:#7c3aed,color:#2e1065
```

> 📁 [`implementation_layer/src/gaik/software_components/extractor/`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/extractor)

---

## Defining What to Extract: User Requirements

Fields are specified in plain language — no code, no schema configuration. Each line names a field and optionally defines allowed values or extraction rules:

```
Extract the following fields from the incident report.
- Report type [Choose one from: Safety, Environmental protection, Energy efficiency, ""]
- Observer name
- Observer organization [ABC Pori Oy; ABC Helsinki Oy; Other]
- Observer is a summer employee [output "Yes" only if it is explicitly stated that the reporter is a summer employee; otherwise ""]
- Event time [date text exactly as written in source; do not normalize to ISO]
- Location information
- Photo count [number of photos uploaded; if none mentioned, output ""]
- The event was serious [Yes, No]
- Description of the event area
- Possible consequences
- Implemented measures
- Proposal
```

---

## Software Module: Audio to Structured Data

Packages both components into a single workflow. Provide an audio file and field requirements — the module returns transcripts, structured fields, and the reusable schema.

```mermaid
flowchart TD
    IN1("🎙️ Audio File") --> MOD
    IN2("📋 User Requirements") --> MOD

    subgraph MOD["Audio-to-Structured-Data Module"]
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
    MOD --> O3("✅ Structured incident Fields")
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

Example output for an incident recording:

```
Report type:               Safety
Observer name:             Anna Virtanen
Observer organization:     ABC Pori Oy
Observer is summer employee: ""
Event time:                15.3.2024 klo 14:30
Location information:      Halli 3, linja B, puristimen alue
Photo count:               2
The event was serious:     Yes
Description of event area: Hydrauliputki vaurioitunut, öljyvuoto lattialla
Possible consequences:     Liukastumisriski, tulipaloriski
Implemented measures:      Alue eristetty, öljy imeytetty
Proposal:                  Hydrauliputki tarkistettava ennen käyttöönottoa
```

> 📁 [`implementation_layer/src/gaik/software_modules/audio_to_structured_data/`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_modules/audio_to_structured_data)
> 📁 [`implementation_layer/examples/software_modules/`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_modules)

---

## Adaptable to Other Domains

The same pipeline applies to any domain requiring structured extraction from spoken descriptions — only the **User Requirements** definition changes:

- Construction site diaries, field service reports, quality inspection notes, healthcare incident reports

---

## Related Resources

| Resource | Link |
|----------|------|
| Transcriber component | [GitHub →](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/transcriber) |
| Extractor component | [GitHub →](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/extractor) |
| Audio to Structured Data module | [GitHub →](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_modules/audio_to_structured_data) |
| Module usage examples | [GitHub →](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_modules) |
| GenAI Product Canvas (Incident Reporting) | [Download →](https://github.com/GAIK-project/gaik-toolkit/blob/main/business_layer/genAI_product_canvas/GenAI_product_canvas_Incident%20reporting_v0.1.pptx) |
| Implementation Layer overview | [GitHub →](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer) |
