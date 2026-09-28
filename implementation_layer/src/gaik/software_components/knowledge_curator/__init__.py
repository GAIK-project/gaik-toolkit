"""Knowledge Curator

Stage 2 of CURACT report writing: for each non-derived report section, extracts fact
units with a verbatim quote from normalized sources, lists the required items no source
covers and the conflicts between sources. Every quote is checked against its source.

Main Classes:
    - KnowledgeCurator: curate normalized sources into a KnowledgeBase
    - KnowledgeBase: the curated knowledge, one SectionKnowledge per section

Configuration:
    - get_llm_config: Get the LLM provider configuration

Example:
    >>> from gaik.software_components.knowledge_curator import (
    ...     KnowledgeCurator, SectionSpec, get_llm_config,
    ... )
    >>> curator = KnowledgeCurator(get_llm_config())
    >>> knowledge = curator.curate(sources, [SectionSpec(id="roof", title="Roof")])
    >>> knowledge.save("workspace/knowledge")
"""

from gaik.software_components.llm import get_llm_config

from .knowledge_curator import KnowledgeCurator
from .models import (
    Conflict,
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
    check_sections,
    quote_in_text,
)

__all__ = [
    "KnowledgeCurator",
    "SectionSpec",
    "check_sections",
    "SourceRef",
    "FactUnit",
    "Conflict",
    "SectionKnowledge",
    "KnowledgeBase",
    "quote_in_text",
    "get_llm_config",
]

__version__ = "0.1.0"
