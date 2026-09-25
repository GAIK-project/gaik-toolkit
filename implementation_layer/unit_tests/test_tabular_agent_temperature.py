"""TabularAgent's default temperature must not break GPT-6 on the raw OpenAI path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("duckdb")

from gaik.software_components.tabular_agent.agent import TabularAgent  # noqa: E402
from gaik.software_components.tabular_agent.models import (  # noqa: E402
    GeneratedSQL,
    QueryResult,
)


class _RawOpenAIClient:
    """Stands in for ``OpenAI``/``AzureOpenAI``: not a ``ProviderClient``."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        message = SimpleNamespace(
            content="an answer", parsed=GeneratedSQL(sql="SELECT 1", reasoning="stub")
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        def record(**kwargs):
            self.calls.append(kwargs)
            return response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=record))
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=record)))


@pytest.mark.parametrize(
    ("model", "config", "expected"),
    [
        ("gpt-6-luna", None, {}),
        ("gpt-6-sol", {"reasoning_effort": "none"}, {"temperature": 0.0}),
        ("gpt-5.4", None, {"temperature": 0.0}),
    ],
)
def test_raw_openai_path_adapts_default_temperature_to_the_model(tmp_path, model, config, expected):
    csv = tmp_path / "sales.csv"
    csv.write_text("region,total\nnorth,1\n", encoding="utf-8")
    agent = TabularAgent(csv, model=model, config=config)
    agent._llm_client = client = _RawOpenAIClient()

    agent._parse_structured([{"role": "user", "content": "q"}], GeneratedSQL)
    agent._synthesize_answer(
        "how many?",
        QueryResult(question="how many?", sql="SELECT 1", rows=[{"n": 1}], row_count=1),
    )

    assert len(client.calls) == 2
    for call in client.calls:
        assert {k: v for k, v in call.items() if k == "temperature"} == expected
