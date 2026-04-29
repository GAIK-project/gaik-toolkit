"""Validators

Components that check the output of other GAIK components against the
underlying source. Today the category contains a multi-provider LLM-as-judge
(``LLMJudge`` + ``LLMJudgePanel``); future siblings can include rule-based or
schema-only validators.
"""

__all__: list[str] = []

# LLM-as-judge validator (requires google-genai and/or anthropic via gaik[llm-judge])
try:
    from .llm_judge import (
        CalibrationItem,
        CalibrationReport,
        FewShotExample,
        JudgePanelResult,
        JudgeUsage,
        LLMJudge,
        LLMJudgePanel,
        PairwiseResult,
        ValidationFlag,
        ValidationResult,
        ValidationRubric,
        calibrate_against_human_labels,
        compare_pairwise,
    )

    __all__.extend(
        [
            "LLMJudge",
            "LLMJudgePanel",
            "ValidationFlag",
            "ValidationRubric",
            "ValidationResult",
            "JudgeUsage",
            "JudgePanelResult",
            "FewShotExample",
            "CalibrationItem",
            "CalibrationReport",
            "PairwiseResult",
            "calibrate_against_human_labels",
            "compare_pairwise",
        ]
    )
except ImportError:
    pass
