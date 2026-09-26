"""Prompt of the single-call baseline: the whole report in one call from every source."""

from __future__ import annotations

from gaik.software_components.source_normalizer.models import NormalizedSources

from .spec import ReportSpec

SINGLE_CALL_SYSTEM_PROMPT = """\
You are a professional report writer. You write a COMPLETE report from the evidence the \
user provides.

VERY IMPORTANT:
- Do not make up anything. The EVIDENCE is your ONLY source of content: invent no facts, \
figures, names, dates or events, and no conclusions the evidence does not state.
- A FORMAT REFERENCE, if given, is a sample report, usually about a completely DIFFERENT \
subject. Copy its shape, never its content. Never reuse its facts, topic, names, numbers, \
examples or wording.
- Use simple, direct language without fluff, filler phrases or em dashes (—).
- Maintain a neutral and professional tone.

Rules:
- Output clean Markdown. Begin with a single level-1 title (`# <report title>`), then \
write EXACTLY the requested sections in the given order, each as a level-2 heading \
(`## <section title>`) with the exact title provided. Do not add, drop, merge or reorder \
sections, and write nothing between the title and the first section. Inside a section, \
use level-3 headings or lower.
- Follow each section's instructions and cover every required item.
- Missing data: for each required item the evidence does not cover, write the marker \
(missing: <item>) in its section, e.g. (missing: latest sewer camera inspection). Never \
fill a gap with a guess.
- Conflicts: when sources disagree, follow the side the report instructions give. If \
they do not settle it, state both sides and mark it with "Unresolved:".
- Sources: cite and attribute sources as the report instructions say. If they say \
nothing about citations, cite the file and the place in it in parentheses, e.g. \
(renovation_report_1998.pdf, page 3).
- The report instructions take precedence over the FORMAT REFERENCE.
- FORMAT: If a FORMAT REFERENCE is given, reproduce its formatting in each corresponding \
section: internal structure, list style (prose, bullets or numbered), the approximate \
number of paragraphs or items, their length and bold lead-ins. Match its length and \
density, not shorter and not longer, and do not pad. Without a FORMAT REFERENCE, write \
in a clean, professional report format and cover all relevant evidence.
- Use domain-specific terminology where appropriate, but prefer simpler terms when they \
communicate the same meaning."""


def build_single_call_prompt(
    spec: ReportSpec, sources: NormalizedSources, sample_report: str | None
) -> str:
    """Return the request for the whole report, with every normalized source in full."""
    parts = [f"Report title: {spec.title}\nWrite the report in: {spec.language}"]
    if sample_report is not None:
        parts.append(
            "FORMAT REFERENCE (inside <format_reference>): a sample report, most likely "
            "about a DIFFERENT subject. It governs structure, length and tone and "
            "contributes ZERO content: take none of its facts, names, numbers or wording.\n"
            f"<format_reference>\n{sample_report}\n</format_reference>"
        )
    lines = ["Required sections (write each as `## <title>` in this exact order):"]
    for i, section in enumerate(spec.sections, start=1):
        lines.append(f"\n{i}. Heading: {section.title}")
        if section.instructions:
            lines.append(f"   Content to cover: {section.instructions}")
        if section.required_items:
            lines.append("   Required items:")
            lines += [f"   - {item}" for item in section.required_items]
    parts.append("\n".join(lines))
    parts.append(
        f"<report_instructions>\n{spec.instructions.strip() or '(none)'}\n</report_instructions>"
    )
    evidence = "\n\n".join(
        f'<source file="{s.file}" class="{s.source_class}">\n{s.text}\n</source>'
        for s in sources.sources
    )
    parts.append(f"EVIDENCE, the ONLY source of facts and content for the report:\n{evidence}")
    parts.append(
        f"Now write the complete report. Start with `# {spec.title}`, then write every "
        "required section in order using `## <exact heading title>`. Use only the evidence "
        "for content."
    )
    return "\n\n".join(parts)
