# BPMN reference comparison (#50) — 2026-07-27

Compares **V2 wizard generation** (adapter + `bpmn_generator`) against customer reference XML under `docs/6.7_demo/extracted/`.

Scope: structural inventory (lanes, tasks, data, events). Not a claim of diagram identity — customer refs are multi-pool / domain-specific; the wizard emits a single-pool GenAI use-case diagram.

## Case: `audio_to_structured`

- Reference: `Use_Case_Audio-to-Structured.bpmn`
- V2 use-case name: **Incident reporting**

| Aspect | Customer reference | V2 generated |
|--------|--------------------|--------------|
| lanes | Observer, GenAI, Safety Manager, GAIK tool, Observer, ERP, HSEQ ((Health, Safety, Environment, and Quality), Observer… | Business User, GenAI, Reviewer |
| tasks | Record Voice Description, Review the incident report (including, GenAI&#39;s), Record&#10;Photo &#38; Voice Description, Evaluate produced report, Upload to incident reporting DB, Edit the produced report, Task Activity: done by HUMAN + SOFTWARE, Record&#10;Photo &#38; Voice Description… | Record Voice Description, Review Report, [STR] Transcribe Audio, [SE] Extract Structured Data |
| gateways | Too high inconsistency with the policy?, Good quality?, Do you&#10;edit it?, Is it likely that text misses key points about real process?, XOR gateway (ONLY ONE PATH POSSIBLE), Good quality?, Do you&#10;edit it?, Compare with &#34;Ideal&#34; report (given the situation) =&#62; 0.8 | Approved? |
| starts | Started&#10;Incident&#10;Reporting, Started&#10;Reporting, Started Evaluating the Reports, Started&#10;Reporting | Started Incident reporting |
| ends | Finished&#10;Incident&#10;Reporting, Finished&#10;Incident&#10;Reporting, Finished&#10;Incident&#10;Reporting, Incident reporting sent to rework, Finished&#10;Incident&#10;Reporting, Incident reporting sent to rework | Incident reporting completed, Rejected |
| data | Audio Recording, Report, Audio&#10;Recording&#10;and Photo, Data Object: SHORT-term (ONLY for this process), Audio&#10;Recording&#10;and Photo, Report | Record Voice Description, Transcribe Audio, Extract Structured Data, Review Report |
| stores | Incident Reporting Database, Reporting Schema, Template (Prompt), Quality assessment checklist, Reporting Database (ERP), Data Store: LONG-term persistence (OUTSIDE this process), Reporting Schema, Template (Prompt), Quality assessment checklist, Reporting Database (ERP) | — |

## Case: `transcription_subtitling`

- Reference: `Use_Case_Transcription-Subtitling.bpmn`
- V2 use-case name: **Transcription and subtitling**

| Aspect | Customer reference | V2 generated |
|--------|--------------------|--------------|
| lanes | GenAI, Requester / Content Owner, Reviewer / Accessibility or QA manager | Business User, GenAI |
| tasks | Upload Audio/Video File, Review Transcript and Subtitle Files, Apply Corrections &#38; Re-run, Store Transcript and Subtitle Files, Publish / Make Files Available, Notify Upload Error / Request Re-upload, Validate File and Read Metadata | Upload Media File, [STR] Transcribe Audio, [ENH] Enhance Transcript, [STR] Generate Subtitle Files |
| gateways | Human Review Requried?, Corrections needed?, Supported file and valid request? | — |
| starts | Started Video Transcription Request | Started Transcription and subtitling |
| ends | Finished Transcription and Subtitle Generation, Transcription Request Rejected | Transcription and subtitling completed |
| data | Media File, 1) Transcript&#10;2) SRT&#10;3) VTT file&#10;4*)Translated&#10;Subtitles | Upload Media File, Transcribe Audio, Enhance Transcript, Generate Subtitle Files |
| stores | — | — |

## Known gaps (PO review)

1. **Role-specific lanes** (Observer, Safety Manager, ERP, …) vs wizard generic **Business User / GenAI / Reviewer** — by design for a configurable SME flow.
2. **Multiple pools / collaboration** and **message flows** in references are not emitted from the V2 simplified blueprint.
3. **Data stores / repositories** appear in references; V2 currently emphasizes in-process **data objects**.
4. Customer diagrams include rich annotations and alternative paths; V2 generates the happy path + approval gateway from `human_review`.
5. Exact task wording in references is domain-authored; V2 uses step names from the session blueprint (agent/UI).

## Conclusion

V2 generation is **directionally aligned** with GAIK modeling conventions (official shapes, GenAI lane, verb–object tasks, `[CODE]` prefixes, descriptive events, data objects). It is **not** a clone of the hand-built reference diagrams. Acceptable for Sprint 2 demo if PO agrees; deeper parity is Sprint 3+ (#48 topology, domain lane packs).
