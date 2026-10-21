"""Tests for _resolve_user_language in chat.py.

Precedence (per user directive 2026-06-01): the PROMPT's language wins when it
can be CONFIDENTLY detected; the SettingsMenu gear pick is only a BACKUP for
when the prompt is too short/ambiguous to detect. Then the detected code
(upstream's geo tiebreaker is not ported). `_resolve_user_language` drives both the answer language and
the suggested-question language.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.api.routers.chat import _resolve_user_language


def _data(user_lang_pref):
    """Build a ChatData-shaped object with the given pref in data.data."""
    return SimpleNamespace(data={"user_language_pref": user_lang_pref})


def _conf(lang, confident):
    """Patch detect_language_confident -> (lang, confident)."""
    return patch(
        "app.api.routers.chat.LocalizationManager.detect_language_confident",
        return_value=(lang, confident),
    )


# ----- Prompt detection wins when confident -----


def test_confident_prompt_detection_beats_gear_pref():
    # The reported bug: French prompt, gear set to English -> must answer French.
    with _conf("fr", True):
        assert _resolve_user_language(_data("en"), "Comment ça marche?") == "fr"


def test_confident_english_beats_gear_pref():
    with _conf("en", True):
        assert _resolve_user_language(_data("es"), "How does this work?") == "en"


# ----- Gear pref is the BACKUP when detection is not confident -----


def test_gear_pref_used_when_detection_not_confident():
    with _conf("en", False):  # short/ambiguous prompt
        assert _resolve_user_language(_data("es"), "ok") == "es"


def test_gear_pref_normalizes_region_code():
    with _conf("en", False):
        assert _resolve_user_language(_data("es-MX"), "ok") == "es"


def test_auto_pref_not_confident_falls_through():
    with _conf("en", False):
        assert _resolve_user_language(_data("auto"), "ok") == "en"


def test_unsupported_pref_ignored():
    with _conf("en", False):
        assert _resolve_user_language(_data("xx"), "ok") == "en"


def test_empty_pref_falls_through():
    with _conf("en", False):
        assert _resolve_user_language(_data(""), "ok") == "en"


# ----- data safety -----


def test_missing_data_field_is_safe():
    with _conf("en", False):
        assert _resolve_user_language(SimpleNamespace(data=None), "ok") == "en"


def test_non_dict_data_is_safe():
    with _conf("en", False):
        assert _resolve_user_language(SimpleNamespace(data="x"), "ok") == "en"


# ----- Whether the settings pick decided (the prompt then names the language) -----


def test_pick_decides_only_when_the_prompt_is_undetectable():
    from app.api.routers.chat import _resolve_language

    with _conf("en", False):
        assert _resolve_language(_data("pt"), "ok") == ("pt", True)
    with _conf("en", True):
        # A clearly English question keeps English, even with Portuguese picked.
        assert _resolve_language(_data("pt"), "How do I get paid?") == ("en", False)
    with _conf("en", False):
        # No pick: the detected fallback, and the prompt keeps its default rule.
        assert _resolve_language(_data("auto"), "ok") == ("en", False)
