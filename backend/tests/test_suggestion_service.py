import asyncio
import os

os.environ.setdefault("VOYAGE_API_KEY", "test-key")

from app.api.routers.models import Message
from app.api.services import suggestion
from app.api.services.suggestion import NextQuestionSuggestion
from llama_index.core.settings import Settings


def test_suggestion_generator_receives_user_language(monkeypatch):
    captured = {}

    class FakeLlm:
        async def astructured_predict(self, response_cls, **kwargs):
            captured.update(kwargs)
            return suggestion.NextQuestions(questions=["¿Pregunta siguiente?"])

    monkeypatch.setattr(Settings, "_llm", FakeLlm(), raising=False)

    questions = asyncio.run(
        NextQuestionSuggestion.suggest_next_questions(
            [
                Message(role="user", content="¿Cuándo me pagan?"),
                Message(role="assistant", content="Los pagos son el 8 y el 23 de cada mes."),
            ],
            user_language="es",
        )
    )

    assert questions == ["¿Pregunta siguiente?"]
    assert "detected language" in captured["language_instruction"]
    assert "'es'" in captured["language_instruction"]


def test_openai_structured_output_program_can_be_built():
    """Regression: Phase 0's dependency trim dropped llama-index-program-openai /
    agent-openai, so astructured_predict raised "No module named
    'llama_index.agent'" and suggested questions silently came back empty
    (the other tests stub the LLM, so nothing noticed)."""
    from llama_index.core.program.utils import get_program_for_llm
    from llama_index.llms.openai import OpenAI

    program = get_program_for_llm(
        suggestion.NextQuestions,
        suggestion.NEXT_QUESTIONS_SUGGESTION_PROMPT,
        OpenAI(model="gpt-4o-mini", api_key="placeholder"),
    )
    assert program is not None
