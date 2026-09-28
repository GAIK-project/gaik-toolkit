"""Prompts of the ReportSynthesizer writer and the section checks of its reviewer."""

from __future__ import annotations

from gaik.software_components.knowledge_curator.models import SectionSpec

WRITER_SYSTEM_PROMPT = """\
You are a professional report writer. You write ONE section of a larger report from the \
material the user provides: the curated knowledge of the section, or, for a section that \
summarizes or builds on other sections, the finished text of those sections.

VERY IMPORTANT:
- Use only facts in the provided material, and invent nothing: no facts, figures, names, \
dates or events of your own, and no conclusions the material does not state.
- A FORMAT REFERENCE, if given, is a sample report, usually about a completely DIFFERENT \
subject. Copy its shape, never its content. Never reuse its facts, topic, names, numbers, \
examples or wording.
- Use simple, direct language without fluff, filler phrases or em dashes (—).
- Maintain a neutral and professional tone.

Rules:
- Write ONLY the body of the requested section. Do NOT start with a heading: the section \
heading is added automatically.
- Follow the section instructions and cover every required item.
- Missing data: for each item in the knowledge's "missing" list, and for each required \
item the material does not cover, write the marker (missing: <item>) in the text, e.g. \
(missing: latest sewer camera inspection). Never fill a gap with a guess.
- Conflicts: for a conflict with status "unresolved", state both sides and mark it with \
"Unresolved:". For a "resolved" conflict, follow the side its description gives.
- Sources: cite and attribute sources as the report instructions say. Each fact unit \
gives source.file, source.locator, source_class and time_qualifier for this. If the \
report instructions say nothing about citations, cite the file and locator in \
parentheses, e.g. (renovation_report_1998.pdf, page 3).
- The report instructions take precedence over the FORMAT REFERENCE.
- FORMAT: If a FORMAT REFERENCE is given, find its section that corresponds to this one \
and reproduce its formatting: internal structure, list style (prose, bullets or \
numbered), the approximate number of paragraphs or items, their length and bold lead-ins. \
Match its length and density, not shorter and not longer, and do not pad. If it has no \
corresponding section, follow its overall tone and style. Without a FORMAT REFERENCE, \
write in a clean, professional report format and cover all relevant material.
- Use domain-specific terminology where appropriate, but prefer simpler terms when they \
communicate the same meaning."""


def _required(section: SectionSpec) -> str:
    return "\n".join(f"- {item}" for item in section.required_items) or "(none listed)"


def _report_instructions(instructions: str) -> str:
    return f"<report_instructions>\n{instructions.strip() or '(none)'}\n</report_instructions>"


def build_writer_prompt(
    section: SectionSpec,
    material: str,
    *,
    title: str,
    language: str,
    instructions: str,
    sample_report: str | None,
) -> str:
    """Return the writer request for one section.

    ``material`` is the section's knowledge JSON, or for a derived section the texts of
    its prerequisite sections.
    """
    parts = [
        f"Report: {title}\nWrite the section in: {language}",
        _report_instructions(instructions),
    ]
    if sample_report is not None:
        parts.append(
            "FORMAT REFERENCE (inside <format_reference>): a sample report, most likely "
            "about a DIFFERENT subject. It governs structure, length and tone and "
            "contributes ZERO content: take none of its facts, names, numbers or wording.\n"
            f"<format_reference>\n{sample_report}\n</format_reference>"
        )
    if section.derived:
        parts.append(
            "The finished sections this section is written from (inside "
            "<prerequisite_sections>) are the ONLY source of facts. Summarize or build on "
            "them; do not contradict them.\n"
            f"<prerequisite_sections>\n{material}\n</prerequisite_sections>"
        )
    else:
        parts.append(
            "The curated knowledge of this section (inside <knowledge>) is the ONLY source "
            f"of facts.\n<knowledge>\n{material}\n</knowledge>"
        )
    parts.append(
        f'<section_to_write id="{section.id}">\nTitle: {section.title}\n'
        f"Instructions: {section.instructions.strip() or '(none)'}\n"
        f"Required items:\n{_required(section)}\n</section_to_write>"
    )
    parts.append(
        f'Now write the body of the section "{section.title}" from the material above '
        "only. Do not start with a heading."
    )
    return "\n\n".join(parts)


def build_review_checks(section: SectionSpec, instructions: str) -> str:
    """Return the checks the reviewer applies to one section; they replace its defaults."""
    knowledge_checks = (
        ""
        if section.derived
        else '- Every item in the knowledge\'s "missing" list must carry a (missing: <item>) '
        'marker. A conflict with status "unresolved" must give both sides and be marked '
        '"Unresolved:".\n'
    )
    return f"""\
- Every factual claim must be supported by the reference material. Correct or remove \
claims it does not support.
- Correct numbers, years, dates, names and attributions (which source says what) that \
contradict the reference.
- Each required item of the section that the reference does not cover must carry a \
(missing: <item>) marker in the text. Add a marker that is absent, and never remove one \
for an item the reference does not cover.
{knowledge_checks}\
- Hierarchy phrasing (e.g. narrated observations versus attributed documents) and the \
citation format must follow the report instructions below.
- The text must follow the section instructions below.
- Make only the changes these checks call for. Do not rewrite the style, do not reorder \
the content and do not shorten or expand the text for any other reason.

Section "{section.title}"
Instructions: {section.instructions.strip() or "(none)"}
Required items:
{_required(section)}

{_report_instructions(instructions)}"""
