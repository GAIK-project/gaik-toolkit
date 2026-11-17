# EU AI Act reference for screening

```
last_verified: 2026-11-16
instrument: Regulation (EU) 2024/1689 (AI Act), as amended by the Digital Omnibus on AI
            (Regulation (EU) 2026/1744, OJ L 24 July 2026)
```

A working summary for screening GAIK use cases, in plain words. It is not the legal text.
Cite provisions by the labels used here (for example `Art. 6(3)`, `Annex III(4)(a)`).
Points marked **verify** changed recently or were confirmed from secondary sources only;
check them against the official text before relying on them in a decision.

## Contents

1. Scope
2. Roles
3. Prohibited practices
4. High-risk: products
5. High-risk: Annex III
6. The Art. 6(3) exception
7. Transparency
8. General-purpose AI models
9. Obligations by role
10. Application dates
11. Penalties and SME relief
12. Adjacent law
13. Official sources
14. Citable provisions

## 1. Scope

- **Art. 3(1)** — An AI system is a machine-based system that operates with some autonomy
  and infers from its input how to generate outputs such as predictions, content,
  recommendations or decisions. Any pipeline built on an LLM, a speech-to-text model or an
  embedding model meets this.
- **Art. 3(34)** — Biometric data: personal data from specific technical processing of a
  person's physical, physiological or behavioural characteristics, such as facial images or
  fingerprints. Voice analysed for tone, pitch or prosody counts; the words of a transcript do
  not.
- **Art. 3(39)** — An emotion recognition system identifies or infers emotions or intentions
  of natural persons **on the basis of their biometric data**. Sentiment or emotion labels
  inferred from text, including a transcript, are not emotion recognition under the Act.
- **Art. 2(1)** — The Act applies to providers placing systems on the EU market or putting
  them into service, to deployers established in the EU, and to providers and deployers
  outside the EU when the output is used in the EU.
- **Art. 2(8)** — Research, testing and development before a system is placed on the market
  or put into service are outside the Act. Testing in real-world conditions is not covered
  by this exclusion. A PoC run on sample data is development; screen the **intended
  production use**, and say that the PoC stage itself is outside scope.
- **Art. 2(10)** — Purely personal, non-professional use by a natural person is excluded.
- **Art. 2(12)** — Systems released under free and open-source licences are excluded unless
  they are high-risk, prohibited, or fall under Art. 50.

## 2. Roles

- **Art. 3(3)** — **Provider**: develops an AI system, or has one developed, and places it
  on the market or puts it into service under its own name or trademark, paid or free.
- **Art. 3(4)** — **Deployer**: uses an AI system under its authority in a professional
  activity.
- An organisation that builds a solution with the GAIK toolkit for its own use is normally
  both: it puts the system into service under its own name (provider) and uses it
  (deployer). One that builds it for clients is the provider; the client is the deployer.
- **Art. 25(1)** — A deployer or distributor becomes the provider of a high-risk system when
  it puts its own name on it, substantially modifies it, or changes the intended purpose of
  a system so that it becomes high-risk.

## 3. Prohibited practices

**Art. 5(1)** prohibits placing on the market, putting into service or using AI systems for:

- **Art. 5(1)(a)** — subliminal, manipulative or deceptive techniques that materially
  distort behaviour and cause or are likely to cause significant harm.
- **Art. 5(1)(b)** — exploiting vulnerabilities due to age, disability or social or economic
  situation, with the same effect.
- **Art. 5(1)(c)** — social scoring that leads to detrimental treatment in unrelated
  contexts or treatment disproportionate to the behaviour.
- **Art. 5(1)(d)** — assessing the risk that a person commits a crime based solely on
  profiling or personality traits.
- **Art. 5(1)(e)** — building facial recognition databases by untargeted scraping of images.
- **Art. 5(1)(f)** — inferring emotions of people **in the workplace or in education** from
  their biometric data (Art. 3(34), 3(39)), except for medical or safety reasons. Relevant to
  GAIK: analysing the tone or prosody of employee or student voice recordings to infer
  emotions. A sentiment field extracted from the **transcript text** is not this practice;
  check the pipeline's input to the step, not the field name.
- **Art. 5(1)(g)** — biometric categorisation that deduces race, political opinions,
  trade-union membership, religion, sex life or sexual orientation.
- **Art. 5(1)(h)** — real-time remote biometric identification in public spaces for law
  enforcement, outside narrow exceptions.
- **Art. 5 (2026 amendment)** — generating child sexual abuse material or non-consensual
  sexual or intimate content of identifiable people; providers must have safeguards.
  Applies from 2 December 2026. **verify** the paragraph number.

Prohibitions (a) to (h) have applied since 2 February 2025.

## 4. High-risk: products

- **Art. 6(1)** — A system is high-risk when it is a safety component of a product, or is
  itself a product, covered by the EU product legislation in **Annex I**, and that product
  must undergo third-party conformity assessment. Annex I includes medical devices, in vitro
  diagnostics, toys, lifts, radio equipment, pressure equipment, vehicles and aviation.
- 2026 amendment: machinery moved from Annex I Section A to Section B, so AI in machinery is
  regulated mainly through the Machinery Regulation; a system serving only non-safety
  purposes generally is not a safety component. **verify**
- GAIK document and audio pipelines are rarely safety components. Ask only when the use case
  sits inside a regulated product (for example a medical device).

## 5. High-risk: Annex III

**Art. 6(2)** — A system is high-risk when its **intended purpose** falls in an area listed
in Annex III. Test the purpose and the use of the output, not the technology.

Every point below is a separate high-risk use case. Areas 1, 6 and 7 apply only in so far
as the use is permitted under Union or national law. Wording is condensed; check the official
text for a decision.

- **Annex III(1) Biometrics** —
  (a) remote biometric identification systems; not systems whose sole purpose is to verify
  that a person is who they claim to be;
  (b) biometric categorisation according to sensitive or protected attributes or
  characteristics inferred from them;
  (c) emotion recognition systems (Art. 3(39): from biometric data).
- **Annex III(2) Critical infrastructure** — safety components in the management and
  operation of critical digital infrastructure, road traffic, or the supply of water, gas,
  heating or electricity.
- **Annex III(3) Education and vocational training** —
  (a) determining access or admission, or assigning people to institutions at any level;
  (b) evaluating learning outcomes, including when used to steer the learning process;
  (c) assessing the appropriate level of education a person will receive or can access;
  (d) monitoring and detecting prohibited behaviour of students during tests.
- **Annex III(4) Employment, workers' management and access to self-employment** —
  (a) recruitment or selection: placing targeted job advertisements, analysing and filtering
  applications, evaluating candidates;
  (b) decisions affecting terms of work relationships, promotion or termination; allocating
  tasks based on individual behaviour or personal traits; monitoring and evaluating the
  performance and behaviour of people in work relationships.
- **Annex III(5) Access to essential private and public services and benefits** —
  (a) used by or for public authorities to evaluate eligibility for essential public
  assistance benefits and services, including healthcare, or to grant, reduce, revoke or
  reclaim them;
  (b) evaluating the creditworthiness of natural persons or establishing their credit score,
  except systems used to detect financial fraud;
  (c) risk assessment and pricing for natural persons in life and health insurance;
  (d) evaluating and classifying emergency calls, dispatching or prioritising emergency first
  response services (police, firefighters, medical aid), and emergency healthcare patient
  triage.
- **Annex III(6) Law enforcement** (by or for law enforcement authorities) —
  (a) assessing the risk of a natural person becoming the victim of criminal offences;
  (b) polygraphs and similar tools;
  (c) evaluating the reliability of evidence;
  (d) assessing the risk of offending or re-offending not solely on the basis of profiling,
  or assessing personality traits or past criminal behaviour;
  (e) profiling of natural persons in the detection, investigation or prosecution of
  criminal offences.
- **Annex III(7) Migration, asylum and border control management** (by or for competent
  public authorities) —
  (a) polygraphs and similar tools;
  (b) assessing a security, irregular-migration or health risk posed by a person who intends
  to enter or has entered a Member State;
  (c) assisting the examination of applications for asylum, visas or residence permits and
  related complaints, including assessing the reliability of evidence;
  (d) detecting, recognising or identifying natural persons, except verifying travel
  documents.
- **Annex III(8) Administration of justice and democratic processes** —
  (a) used by or for a judicial authority to research and interpret facts and the law and to
  apply the law to facts, or used in a similar way in alternative dispute resolution;
  (b) intended to influence the outcome of an election or referendum or people's voting
  behaviour; not tools whose output people are not directly exposed to, such as tools to
  organise, optimise or structure political campaigns administratively or logistically.

Typical GAIK borderlines:

| Use case | Likely reading |
|---|---|
| Incident or safety-observation report from a voice message, reviewed by a manager | Not Annex III: it documents an event. Becomes Annex III(4)(b) if the output is used to evaluate or discipline the worker. |
| CV or application extraction into a structured form | Annex III(4)(a) when used to filter or rank applicants. Check Art. 6(3). |
| Site diary, purchase order, invoice extraction | Not Annex III. |
| Extracting student work into grades or feedback | Annex III(3)(b). |
| RAG assistant over internal documents | Not Annex III unless it serves one of the listed decisions. Check Art. 50(1). |
| Meeting or call transcription with performance summaries of named staff | Annex III(4)(b). |

## 6. The Art. 6(3) exception

- **Art. 6(3)** — An Annex III system is **not** high-risk when it poses no significant risk
  of harm to health, safety or fundamental rights, including by not materially influencing
  the outcome of decision-making. This holds when at least one condition is met:
  (a) it performs a narrow procedural task;
  (b) it improves the result of a previously completed human activity;
  (c) it detects decision patterns or deviations from them and is not meant to replace or
  influence the human assessment without proper human review;
  (d) it performs a preparatory task for an assessment relevant to an Annex III use case.
- **Profiling override** — A system that profiles natural persons is always high-risk under
  Annex III, whatever conditions (a) to (d) say.
- **Art. 6(4)** — A provider relying on the exception documents its assessment before
  placing the system on the market and registers the system (**Art. 49(2)**). The 2026
  amendment kept this registration, in a lighter form. **verify**
- Pure field extraction that a human then assesses can fit (a) or (d). It stops fitting once
  the system scores, ranks or recommends about a person. A `human_review` step supports the
  exception but does not create it.

## 7. Transparency

Art. 50 duties apply whatever the risk class, including to high-risk systems.

- **Art. 50(1)** — Providers of systems that interact directly with people design them so
  people know they are dealing with an AI system, unless that is obvious. (Chatbots, voice
  agents, RAG assistants used by customers or the public.)
- **Art. 50(2)** — Providers of systems generating synthetic text, audio, image or video
  mark the output as artificially generated in a machine-readable, detectable way. Not
  required where the system only assists standard editing or does not substantially alter
  the input or its meaning. (Extraction and faithful transcription usually fall under this
  carve-out; free-text report generation may not.)
- **Art. 50(3)** — Deployers of emotion recognition or biometric categorisation systems
  inform the people exposed.
- **Art. 50(4)** — Deployers disclose deepfakes, and disclose AI-generated text published to
  inform the public on matters of public interest unless it had human review and someone
  holds editorial responsibility.
- **Art. 50(5)** — The information is given clearly, at the latest at first interaction or
  exposure.

Art. 50 applies from 2 August 2026. For Art. 50(2), systems already on the market before
that date have until 2 December 2026.

## 8. General-purpose AI models

- **Art. 3(63)** — A general-purpose AI (GPAI) model can perform a wide range of tasks and
  be integrated into many systems (GPT, Claude, Gemini, Mistral and similar).
- **Art. 53** — Duties on **GPAI model providers** (technical documentation, information for
  downstream providers, copyright policy, training-data summary) have applied since
  2 August 2025. **Art. 55** adds duties for models with systemic risk.
- A GAIK user who calls such a model through an API is a downstream provider or deployer of
  an AI **system**, not a GPAI model provider, and can rely on the model provider's
  documentation. Record the model and provider from the blueprint's `models`.
- Fine-tuning or otherwise modifying a GPAI model can make the user a provider of the
  modified model for that modification. Flag it; do not decide it.

## 9. Obligations by role

**Everyone**

- **Art. 4** — AI literacy: providers and deployers take measures so that staff operating
  AI systems have sufficient AI literacy. Applies since 2 February 2025. The 2026 amendment
  softened the wording toward supporting the development of literacy and gave the
  Commission and Member States a guidance role. **verify**
- **Art. 50** — transparency, when section 7 applies.

**Deployers of high-risk systems**

- **Art. 26(1)** — use the system according to its instructions.
- **Art. 26(2)** — assign human oversight to competent, trained people with authority.
- **Art. 26(4)** — ensure input data is relevant and representative, where they control it.
- **Art. 26(5)** — monitor operation; inform the provider and authorities of risks and
  serious incidents.
- **Art. 26(6)** — keep automatically generated logs for at least six months.
- **Art. 26(7)** — employers inform workers' representatives and affected workers before
  using a high-risk system at the workplace.
- **Art. 26(11)** — inform natural persons that they are subject to a high-risk system that
  makes or assists decisions about them.
- **Art. 27** — fundamental rights impact assessment before first use, for public bodies,
  private entities providing public services, and deployers under Annex III(5)(b) and (c).
- **Art. 86** — affected persons can ask for an explanation of the system's role in a
  decision with legal or similarly significant effects.

**Providers of high-risk systems**

- **Art. 9** risk management system · **Art. 10** data governance · **Art. 11** technical
  documentation · **Art. 12** automatic logging · **Art. 13** instructions for deployers ·
  **Art. 14** human oversight by design · **Art. 15** accuracy, robustness, cybersecurity.
- **Art. 16** — the provider's overall duties, including **Art. 17** quality management,
  **Art. 43** conformity assessment, **Art. 47** EU declaration of conformity, **Art. 48**
  CE marking, **Art. 49** registration in the EU database.
- **Art. 72** post-market monitoring · **Art. 73** serious incident reporting.

**Systems that are not high-risk** — Art. 4 always applies. Art. 50 applies whenever its
conditions are met (section 7), whatever the class. An Annex III system exempt under
Art. 6(3) keeps the assessment and registration duties of **Art. 6(4)** and **Art. 49(2)**.
Voluntary codes of conduct are encouraged (**Art. 95**).

What a wizard pack already supports, when present: a `human_review` step (Art. 14, 26(2));
`governance.data_handling.audit_log_required` (Art. 12, 26(6)); the evaluation plan and
LLMJudge checks (Art. 15); the technical specification and blueprint (Art. 11, in part).
These are supporting evidence, not proof that a duty is met.

## 10. Application dates

| Date | What applies |
|---|---|
| 2 February 2025 | Prohibited practices (Art. 5(1)(a)–(h)); AI literacy (Art. 4) |
| 2 August 2025 | GPAI model duties (Art. 53, 55); governance; penalties |
| 2 August 2026 | General application, including Art. 50 transparency |
| 2 December 2026 | Art. 50(2) for systems already on the market before 2 August 2026; the new Art. 5 prohibition on non-consensual intimate content and CSAM |
| 2 August 2027 | GPAI models placed on the market before 2 August 2025; national regulatory sandboxes operational |
| 2 December 2027 | High-risk duties for Annex III systems (Art. 6(2)) — moved from 2 August 2026 |
| 2 August 2028 | High-risk duties for Annex I product systems (Art. 6(1)) — moved from 2 August 2027 |

**Art. 113** sets when the Act applies; the dates in this table are the ones it and its 2026
amendment set.

High-risk systems already on the market before their date are generally caught only when
their design changes significantly afterwards (**Art. 111(2)**).

When stating a date for a user, give the date and whether it has passed relative to today.

## 11. Penalties and SME relief

- **Art. 99(3)** — prohibited practices: up to EUR 35 million or 7% of worldwide turnover.
- **Art. 99(4)** — most other duties, including high-risk and Art. 50: up to EUR 15 million
  or 3%.
- **Art. 99(5)** — incorrect or misleading information to authorities: up to EUR 7.5
  million or 1%.
- **Art. 99(6)** — for SMEs and start-ups, the lower of the two amounts applies.
- 2026 amendment: SME simplifications (simplified technical documentation, proportionate
  quality management, sandbox priority) extend to small mid-caps. **verify** the thresholds.

Mention penalties only when the class is prohibited or high-risk, in one line.

## 12. Adjacent law

Flag these; do not analyse them. Cite them with `instrument` set, not as AI Act provisions.

- **GDPR Art. 6, 9** — legal basis; special-category data (health, biometric, trade-union,
  and so on). Incident reports naming injured persons contain health data.
- **GDPR Art. 22** — decisions based solely on automated processing with legal or similarly
  significant effects.
- **GDPR Art. 35** — data protection impact assessment for high-risk processing.
- **GDPR Art. 28, 44** — processors and transfers, when `external_model_api_allowed` is true.
- **AI Act Art. 4a** (2026 amendment) — special-category data may be processed for bias
  detection and correction under strict conditions. **verify**
- National workplace rules when employees are monitored or assessed. In Finland: the Act on
  the Protection of Privacy in Working Life and the co-operation procedure for introducing
  technical monitoring. **verify** for the user's country.

## 13. Official sources

- Consolidated AI Act on EUR-Lex: `https://eur-lex.europa.eu/eli/reg/2024/1689`
- European Commission AI Act pages and guidelines (prohibited practices, AI system
  definition, GPAI; high-risk classification guidance is due in 2027):
  `https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai`
- The national market surveillance authority of the user's Member State.

When this file is updated, change `last_verified` and remove **verify** marks that were
checked against the official text.

## 14. Citable provisions

`scripts/check_screening.py` accepts a citation only when its `ref` matches a line below
exactly, for its instrument. Cite the most specific line that fits. To cite a provision not
listed, add it here with its summary above, in the same change.

- AI Act: Art. 2(1)
- AI Act: Art. 2(8)
- AI Act: Art. 2(10)
- AI Act: Art. 2(12)
- AI Act: Art. 3(1)
- AI Act: Art. 3(3)
- AI Act: Art. 3(4)
- AI Act: Art. 3(34)
- AI Act: Art. 3(39)
- AI Act: Art. 3(63)
- AI Act: Art. 4
- AI Act: Art. 4a
- AI Act: Art. 5
- AI Act: Art. 5(1)(a)
- AI Act: Art. 5(1)(b)
- AI Act: Art. 5(1)(c)
- AI Act: Art. 5(1)(d)
- AI Act: Art. 5(1)(e)
- AI Act: Art. 5(1)(f)
- AI Act: Art. 5(1)(g)
- AI Act: Art. 5(1)(h)
- AI Act: Art. 6(1)
- AI Act: Art. 6(2)
- AI Act: Art. 6(3)
- AI Act: Art. 6(3)(a)
- AI Act: Art. 6(3)(b)
- AI Act: Art. 6(3)(c)
- AI Act: Art. 6(3)(d)
- AI Act: Art. 6(4)
- AI Act: Art. 9
- AI Act: Art. 10
- AI Act: Art. 11
- AI Act: Art. 12
- AI Act: Art. 13
- AI Act: Art. 14
- AI Act: Art. 15
- AI Act: Art. 16
- AI Act: Art. 17
- AI Act: Art. 25(1)
- AI Act: Art. 26(1)
- AI Act: Art. 26(2)
- AI Act: Art. 26(4)
- AI Act: Art. 26(5)
- AI Act: Art. 26(6)
- AI Act: Art. 26(7)
- AI Act: Art. 26(11)
- AI Act: Art. 27
- AI Act: Art. 43
- AI Act: Art. 47
- AI Act: Art. 48
- AI Act: Art. 49
- AI Act: Art. 49(2)
- AI Act: Art. 50(1)
- AI Act: Art. 50(2)
- AI Act: Art. 50(3)
- AI Act: Art. 50(4)
- AI Act: Art. 50(5)
- AI Act: Art. 53
- AI Act: Art. 55
- AI Act: Art. 72
- AI Act: Art. 73
- AI Act: Art. 86
- AI Act: Art. 95
- AI Act: Art. 99(3)
- AI Act: Art. 99(4)
- AI Act: Art. 99(5)
- AI Act: Art. 99(6)
- AI Act: Art. 111(2)
- AI Act: Art. 113
- AI Act: Annex I
- AI Act: Annex III
- AI Act: Annex III(1)
- AI Act: Annex III(1)(a)
- AI Act: Annex III(1)(b)
- AI Act: Annex III(1)(c)
- AI Act: Annex III(2)
- AI Act: Annex III(3)
- AI Act: Annex III(3)(a)
- AI Act: Annex III(3)(b)
- AI Act: Annex III(3)(c)
- AI Act: Annex III(3)(d)
- AI Act: Annex III(4)
- AI Act: Annex III(4)(a)
- AI Act: Annex III(4)(b)
- AI Act: Annex III(5)
- AI Act: Annex III(5)(a)
- AI Act: Annex III(5)(b)
- AI Act: Annex III(5)(c)
- AI Act: Annex III(5)(d)
- AI Act: Annex III(6)
- AI Act: Annex III(6)(a)
- AI Act: Annex III(6)(b)
- AI Act: Annex III(6)(c)
- AI Act: Annex III(6)(d)
- AI Act: Annex III(6)(e)
- AI Act: Annex III(7)
- AI Act: Annex III(7)(a)
- AI Act: Annex III(7)(b)
- AI Act: Annex III(7)(c)
- AI Act: Annex III(7)(d)
- AI Act: Annex III(8)
- AI Act: Annex III(8)(a)
- AI Act: Annex III(8)(b)
- GDPR: Art. 6
- GDPR: Art. 9
- GDPR: Art. 22
- GDPR: Art. 28
- GDPR: Art. 35
- GDPR: Art. 44
