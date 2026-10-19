import asyncio
import sys
import types


def _install_test_stubs() -> None:
    # The real langfuse (4.x) is installed and disables itself without keys,
    # so it needs no stub. (A stub here used to replace the real module for
    # every test that ran afterwards.)
    if "llama_index.core.llms" not in sys.modules:
        llama_index_module = types.ModuleType("llama_index")
        core_module = types.ModuleType("llama_index.core")
        llms_module = types.ModuleType("llama_index.core.llms")
        settings_module = types.ModuleType("llama_index.core.settings")

        class ChatMessage:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        class MessageRole:
            SYSTEM = "system"
            USER = "user"

        class Settings:
            llm = None

        llms_module.ChatMessage = ChatMessage
        llms_module.MessageRole = MessageRole
        settings_module.Settings = Settings

        llama_index_module.core = core_module
        core_module.llms = llms_module
        core_module.settings = settings_module

        sys.modules["llama_index"] = llama_index_module
        sys.modules["llama_index.core"] = core_module
        sys.modules["llama_index.core.llms"] = llms_module
        sys.modules["llama_index.core.settings"] = settings_module


try:
    from app.api.services import draft_edit
except ModuleNotFoundError:
    _install_test_stubs()
    from app.api.services import draft_edit


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeResponse:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeLLM:
    def __init__(self, outputs: list[str]):
        self._outputs = list(outputs)
        self.call_count = 0

    async def achat(self, messages):
        self.call_count += 1
        if self._outputs:
            return _FakeResponse(self._outputs.pop(0))
        return _FakeResponse("")


class _FakeSettings:
    """Stand-in for ``llama_index`` ``Settings`` carrying a fake ``llm``.

    ``draft_edit.py`` reads ``Settings.llm.achat(...)``. The real
    ``Settings.llm`` is a property-backed singleton whose getter lazily
    resolves a live OpenAI client (and raises without ``OPENAI_API_KEY``),
    so ``monkeypatch.setattr(Settings, "llm", ...)`` cannot override it.
    Replacing the module-level ``draft_edit.Settings`` name with this fake
    instead makes every test environment-independent — it runs identically
    whether or not the real ``llama_index`` package is installed.
    """

    def __init__(self, llm: _FakeLLM):
        self.llm = llm


def _install_fake_llm(monkeypatch, fake_llm: _FakeLLM) -> None:
    """Route ``draft_edit`` through ``fake_llm`` and silence Langfuse."""
    monkeypatch.setattr(draft_edit, "Settings", _FakeSettings(fake_llm))
    monkeypatch.setattr(
        draft_edit.langfuse,
        "update_current_span",
        lambda *args, **kwargs: None,
    )


def _run(coro):
    return asyncio.run(coro)


def test_retry_metadata_for_word_level_edit(monkeypatch):
    fake_llm = _FakeLLM(
        outputs=[
            "Looking forward to seeing all of you there!",
            "all",
        ]
    )

    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="email",
            instruction="replace this word with a synonym",
            selected_text="everyone",
            full_content="Looking forward to seeing everyone there!",
            subject="Gathering reminder",
        )
    )

    assert rejection is None
    assert edited == "all"
    assert telemetry["granularity"] == "word"
    assert telemetry["attempt_count"] == 2
    assert telemetry["retry_used"] is True
    assert telemetry["terminal_reason"] == "ok"
    assert fake_llm.call_count == 2


def test_rejected_metadata_when_retry_still_invalid(monkeypatch):
    fake_llm = _FakeLLM(
        outputs=[
            "Looking forward to seeing all of you there!",
            "Looking forward to seeing all of you there!",
        ]
    )

    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="email",
            instruction="replace this word with a synonym",
            selected_text="everyone",
            full_content="Looking forward to seeing everyone there!",
            subject="Gathering reminder",
        )
    )

    assert edited is None
    assert rejection == "Please select the exact text you want to change and try again."
    assert telemetry["attempt_count"] == 2
    assert telemetry["retry_used"] is True
    assert telemetry["terminal_reason"] == "model_rejected"
    assert telemetry["validation_error"]


def test_no_edit_metadata(monkeypatch):
    fake_llm = _FakeLLM(outputs=["__NO_EDIT__"])

    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="message",
            instruction="replace this word",
            selected_text="Hi",
            full_content="Hi",
            subject=None,
        )
    )

    assert edited is None
    assert "Please provide an edit instruction" in rejection
    assert telemetry["terminal_reason"] == "model_no_edit"
    assert telemetry["attempt_count"] == 1


def test_non_english_instruction_reaches_llm(monkeypatch):
    """Spanish instruction with zero English verbs must reach the LLM.

    Pre-refactor, the English-keyword regex gate rejected this as
    `invalid_instruction` without ever calling the LLM. This is the
    regression lock for the core bug.
    """
    fake_llm = _FakeLLM(outputs=["Estimado estudiante,"])
    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="email",
            instruction="hazlo más formal",
            selected_text="Hola estudiante,",
            full_content="Hola estudiante, gracias por tu mensaje.",
            subject="Saludo",
        )
    )

    assert rejection is None
    assert edited == "Estimado estudiante,"
    assert fake_llm.call_count == 1
    assert telemetry["terminal_reason"] == "ok"


def test_japanese_instruction_reaches_llm(monkeypatch):
    """Non-Latin-script (Japanese) instruction must reach the LLM."""
    fake_llm = _FakeLLM(outputs=["拝啓 学生の皆様"])
    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="email",
            instruction="もっと丁寧にして",
            selected_text="こんにちは学生の皆さん",
            full_content="こんにちは学生の皆さん、お元気ですか。",
            subject="ご挨拶",
        )
    )

    assert rejection is None
    assert edited == "拝啓 学生の皆様"
    assert fake_llm.call_count == 1
    assert telemetry["terminal_reason"] == "ok"


def test_paraphrased_english_instruction_reaches_llm(monkeypatch):
    """Paraphrased English with no magic verb must reach the LLM."""
    fake_llm = _FakeLLM(outputs=["Hello there, friends!"])
    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="message",
            instruction="a little warmer please",
            selected_text="Hello, students.",
            full_content="Hello, students. See you at the gathering.",
            subject=None,
        )
    )

    assert rejection is None
    assert edited == "Hello there, friends!"
    assert fake_llm.call_count == 1
    assert telemetry["terminal_reason"] == "ok"


def test_no_edit_sentinel_still_rejects_cleanly(monkeypatch):
    """The LLM's __NO_EDIT__ sentinel is the SOLE supportability mechanism.

    A non-edit instruction (here a question) reaches the LLM, which returns
    __NO_EDIT__; the service returns a clean rejection tagged
    `terminal_reason="model_no_edit"`.
    """
    fake_llm = _FakeLLM(outputs=["__NO_EDIT__"])
    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="email",
            instruction="what is PathwayConnect?",
            selected_text="Dear student,",
            full_content="Dear student, welcome.",
            subject="Welcome",
        )
    )

    assert edited is None
    assert rejection
    assert telemetry["terminal_reason"] == "model_no_edit"
    # The LLM was actually consulted — there is no pre-LLM gate anymore.
    assert fake_llm.call_count == 1


def test_granularity_word_level_by_selection_length():
    """A 1-token selection classifies WORD regardless of instruction wording."""
    assert (
        draft_edit._infer_edit_granularity("everyone")
        == draft_edit.EditGranularity.WORD
    )
    # Non-English single-token selection — still WORD (length-only).
    assert (
        draft_edit._infer_edit_granularity("estudiante")
        == draft_edit.EditGranularity.WORD
    )


def test_granularity_short_span_by_selection_length():
    """Length alone decides; the dropped keyword promotion no longer applies.

    A 3-token selection is SHORT_SPAN; a 6-token selection is LONG_SPAN.
    Pre-refactor, an English word-level keyword hint could promote a 5-6
    token selection from LONG_SPAN to SHORT_SPAN — that branch is gone.
    """
    assert (
        draft_edit._infer_edit_granularity("see you soon")
        == draft_edit.EditGranularity.SHORT_SPAN
    )
    assert (
        draft_edit._infer_edit_granularity("we will see all of you")
        == draft_edit.EditGranularity.LONG_SPAN
    )


def test_empty_instruction_guard_no_regex(monkeypatch):
    """Whitespace-only instruction is rejected by the non-semantic guard.

    Defense-in-depth: the Pydantic `DraftEditRequest` validator also rejects
    empty instructions, but the service keeps its own non-regex guard.
    """
    fake_llm = _FakeLLM(outputs=["should not be used"])
    _install_fake_llm(monkeypatch, fake_llm)

    edited, rejection, telemetry = _run(
        draft_edit.rewrite_selected_text_with_llm(
            draft_type="email",
            instruction="   ",
            selected_text="Dear student,",
            full_content="Dear student, welcome.",
            subject="Welcome",
        )
    )

    assert edited is None
    assert rejection
    assert telemetry["terminal_reason"] == "instruction_missing"
    # The LLM was never called — the guard is non-semantic and runs first.
    assert fake_llm.call_count == 0


def test_is_supported_edit_instruction_removed():
    """The English-keyword supportability gate must not be reintroduced.

    If a future change re-adds a regex gate under this name, CI fails here.
    """
    assert not hasattr(draft_edit, "is_supported_edit_instruction")
    assert not hasattr(draft_edit, "_EDIT_INTENT_PATTERN")
    assert not hasattr(draft_edit, "_WORD_LEVEL_REQUEST_PATTERN")
