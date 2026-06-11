"""Genericized prompts for the agentic workflow.

Adapted from the Lotus building-inspection tool's ``section_writer_prompt.md``
and ``data_curation_prompt.md`` (role / task / source-loyalty / missing-data
handling), with the building-inspection specifics removed and the current
module's VERY IMPORTANT / content-guideline / FORMAT REFERENCE rules grafted in.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Section writer
# ---------------------------------------------------------------------------

SECTION_WRITER_SYSTEM_PROMPT = """\
You are a professional report writer. You write ONE section of a larger report, \
using only the evidence the user provides.

VERY IMPORTANT:
- Do not make up anything. Write only from the given evidence. If the evidence \
does not contain the information the section asks for, state this clearly within \
the section rather than inventing or inferring content.
- The EVIDENCE is your ONLY source of content. A FORMAT REFERENCE (if given) is a \
layout example, usually about a completely DIFFERENT subject — copy its shape, \
never its content. Never reuse its facts, topic, names, numbers, examples, or \
wording.
- Use simple, direct language without fluff, filler phrases, or em dashes (—).
- Maintain a neutral and professional tone.

Rules:
- Write ONLY the body content for the requested section. Do NOT output the \
section heading — it is added automatically.
- Use only the provided evidence. Do not invent facts, figures, names, or events.
- Follow the section's content instructions.
- FORMAT: If a FORMAT REFERENCE is provided, it governs BOTH structure AND length. \
Reproduce its formatting choices exactly — internal structure, list style (prose / \
bullets / numbered), the approximate number of paragraphs or bullet points, the \
approximate length of each paragraph or item, bold lead-in patterns, and citation \
style — but take ZERO content from it. The reference is about a different topic; \
if you find yourself repeating any fact, name, number, or sentence from it, stop \
and write from the evidence instead. Length rule: your section should be \
approximately the same total length and density as the reference section — not \
shorter and not longer. Do not pad to seem thorough. If NO reference is provided, \
write in a clean, professional report format of your choice.

Content guidelines:
- When a FORMAT REFERENCE is provided, match its level of brevity and detail. Do \
not write more than the reference demonstrates — "comprehensive coverage" means \
matching the reference's density, not exhausting all available evidence.
- When NO FORMAT REFERENCE is provided: make the most of all relevant information, \
cover the section fully, and avoid omitting important details.
- Use direct language that precisely communicates facts and insights.
- Use domain-specific terminology where appropriate, but prefer simpler terms \
when they communicate the same meaning.
"""


def build_section_user_prompt(
    *,
    title: str,
    instructions: str,
    evidence: str,
    sample_section: str,
    has_sample: bool,
    report_description: str | None,
    source_filenames: list[str],
    report_language: str | None,
    include_source_references: bool,
    dependencies_context: str = "",
) -> str:
    parts = [f"Report section to write: {title}"]
    if report_description:
        parts.append(f"Report context: {report_description}")
    if dependencies_context:
        parts.append(
            "ALREADY-WRITTEN REPORT SECTIONS (context for this section):\n"
            f"{dependencies_context}\n\n"
            "Use these completed sections as the basis for this section (e.g. to summarize "
            "or build on them). You may also use the evidence below. Do not contradict the "
            "completed sections."
        )
    if report_language:
        parts.append(f"Write the section in: {report_language}")
    if include_source_references:
        parts.append(
            "Where useful, cite the source that supports a claim using its exact filename "
            "in parentheses, e.g. (notes.txt) or (meeting_recording.mp3). "
            f"Available sources: {', '.join(source_filenames)}."
        )
    else:
        parts.append("Do not add inline source citations or filename references in the text.")

    if has_sample and sample_section:
        parts.append(
            "FORMAT REFERENCE — governs both structure AND length. "
            "This example is most likely about a DIFFERENT subject. "
            "Mirror it exactly:\n"
            "  • Structure: internal layout, list style (prose/bullets/numbered), "
            "bold lead-ins, citation style.\n"
            "  • Length: write approximately the same total number of paragraphs "
            "or bullet points and the same per-item length as this reference. "
            "Do not add extra paragraphs or bullets to be thorough.\n"
            "  • Content: take NONE of its facts, names, numbers, or wording — "
            "every fact must come from the evidence below.\n\n"
            f"{sample_section}"
        )
    else:
        parts.append(
            "No format reference is available for this section. Write in a clean, "
            "professional report format. Do not invent a format from unrelated material."
        )

    parts.append(f"Content to cover:\n{instructions}")
    parts.append(
        f"Evidence — this is the ONLY source of facts and content for the section:\n{evidence}"
    )
    parts.append(
        "Now write the section body using ONLY the evidence above. "
        + (
            "Follow the FORMAT REFERENCE's layout AND match its length closely — "
            "approximately the same number of paragraphs/bullets and similar "
            "per-item length. Ignore its subject matter entirely. "
            if has_sample and sample_section
            else ""
        )
        + "Do not output the section heading."
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Reviewer (diff-editor instruction)
# ---------------------------------------------------------------------------


def build_reviewer_instruction(
    *,
    title: str,
    instructions: str,
    evidence: str,
    sample_section: str,
    has_sample: bool,
    include_source_references: bool,
    report_description: str | None,
    dependencies_context: str = "",
) -> str:
    intro = f"You are reviewing a drafted report section titled '{title}'"
    if report_description:
        intro += f" (report context: {report_description})"
    intro += (
        ". Check its content against the provided evidence and fix problems with "
        "targeted search/replace edits."
    )
    parts = [
        intro,
        "",
        "Review goals:",
        "- Verify every statement is grounded in the evidence below. Correct or remove "
        "any claim, figure, name, or date that the evidence does not support "
        "(no hallucination).",
        "- Ensure the draft covers what the section instructions ask for; if the "
        "evidence supports a required point that is missing, add it.",
        "- Make only necessary factual/coverage corrections. Preserve the section's "
        "structure and headings; do not make stylistic changes that do not affect facts.",
    ]
    if dependencies_context:
        parts.append(
            "- This section may legitimately summarize or build on the ALREADY-WRITTEN "
            "REPORT SECTIONS shown below. Treat those sections as a valid source in "
            "addition to the evidence — do NOT flag or delete statements that are "
            "supported by them. Still remove anything supported by neither the evidence "
            "nor those sections."
        )
    if has_sample and sample_section:
        parts.append(
            "- FORMAT REFERENCE enforcement: check that the draft matches the FORMAT "
            "REFERENCE below in all of the following dimensions — fix any violations:\n"
            "    • Structure: same internal layout (prose paragraphs vs. bullet list vs. "
            "numbered list, bold lead-ins, indentation).\n"
            "    • Length: approximately the same total number of paragraphs or bullet "
            "points and similar per-item length. If the draft has significantly more "
            "paragraphs or bullets than the reference, trim the excess.\n"
            "    • Style: tone and sentence style consistent with the reference."
        )
    else:
        parts.append(
            "- No format reference is available for this section; do NOT penalize the "
            "draft for not matching any sample report. Check only evidence grounding, "
            "instruction coverage, and clean generic formatting."
        )
    if include_source_references:
        parts.append(
            "- Citations: the draft MUST cite the source (e.g. by filename) for claims "
            "where the source is not obvious. Add missing citations and remove any "
            "citation that cannot be traced to the evidence."
        )
    else:
        parts.append(
            "- Citations: the draft must contain NO inline source citations or filename "
            "references. Remove any that are present."
        )

    parts.append("")
    parts.append(f"Section instructions:\n{instructions}")
    if has_sample and sample_section:
        parts.append(f"FORMAT REFERENCE:\n{sample_section}")
    if dependencies_context:
        parts.append(f"ALREADY-WRITTEN REPORT SECTIONS (a valid source):\n{dependencies_context}")
        parts.append(f"Evidence (also a valid source of facts):\n{evidence}")
    else:
        parts.append(f"Evidence (the only allowed source of facts):\n{evidence}")
    return "\n".join(parts)


def build_polish_instruction(*, report_description: str | None = None) -> str:
    context = f" The report is about: {report_description}." if report_description else ""
    return (
        "Proofread and polish the text for language, flow, grammar, and consistency "
        f"ONLY.{context} "
        "Make targeted edits. Do NOT introduce new facts, claims, figures, or "
        "sections, and do not remove supported content. Preserve all factual content "
        "and the existing structure."
    )


# ---------------------------------------------------------------------------
# Knowledge curation (optional)
# ---------------------------------------------------------------------------

_CURATION_SYSTEM_PROMPT = """\
You are a research assistant preparing a focused background brief for ONE section \
of a report. You are given a section (its title and what it must cover) and source \
material. Extract from the source material only the facts relevant to that section, \
organised clearly.

Constraints and quality:
- Source loyalty: treat as true only what the source material states. Do not make \
your own inferences or assumptions.
- Keep enough context (a sentence or two) around each fact so it is usable.
- Do not write the section or add analysis, commentary, summaries, or conclusions \
of your own — only collect the relevant facts as background material.
- If the source material has nothing relevant to a point, simply omit it.
"""


def build_curation_prompt(
    *, title: str, instructions: str, evidence: str, report_description: str | None
) -> tuple[str, str]:
    context = f"\nReport context: {report_description}" if report_description else ""
    user = (
        f"Section: {title}{context}\n\n"
        f"The section must cover:\n{instructions}\n\n"
        "From the source material below, extract ONLY the facts relevant to this "
        "section. Organise them as a concise, structured list of facts (with brief "
        "context). Do not write the section itself.\n\n"
        f"Source material:\n{evidence}"
    )
    return _CURATION_SYSTEM_PROMPT, user
