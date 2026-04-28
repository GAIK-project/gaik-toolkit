"""Validators

Components that check the output of other GAIK components against the
underlying source. Today the category contains a multi-provider LLM-as-judge;
future siblings can include rule-based or schema-only validators.
"""

__all__: list[str] = []

# LLM-as-judge validator (requires google-genai and/or anthropic via gaik[llm-judge])
try:
    from .llm_judge import (
        JudgeUsage,
        LLMJudge,
        ValidationFlag,
        ValidationResult,
        ValidationRubric,
    )

    __all__.extend(
        [
            "LLMJudge",
            "ValidationFlag",
            "ValidationRubric",
            "ValidationResult",
            "JudgeUsage",
        ]
    )
except ImportError:
    pass
