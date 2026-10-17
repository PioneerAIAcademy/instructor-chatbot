"""Tests for the short-text English-bias guard in detect_language().

Lesson #19 / localization-audit Gap #2: `langdetect` confidently
mislabels short English messages (typos, a stray accented token) as
Dutch/French/German/Italian. `detect_language()` now requires a
non-English detection on short text (<40 chars) to be corroborated by
foreign-language word indicators; otherwise it biases to English.

These tests assert the OUTCOME of detect_language(), which the bias
logic forces deterministically regardless of langdetect's noisy raw
guess — so they are stable even though langdetect itself is not seeded.
"""

import pytest

from app.utils.localization import LocalizationManager


def _detect(text: str) -> str:
    return LocalizationManager.detect_language(text)


# --------------------------------------------------------------------------
# 1. English-with-noise — short messages that MUST now resolve to English.
#    These are the lesson-#19 failure cases (typos / a stray token tripping
#    langdetect into nl/fr/de/it).
# --------------------------------------------------------------------------

ENGLISH_NOISE_CASES = [
    "wen does block 3 start",      # typo "wen"
    "is registraton open",         # typo "registraton"
    "hi how r u",                  # txt-speak
    "wut time is graduation",      # typo "wut"
    "block 3 dates",               # bare domain words
    "when is graduation",          # clean short English
    "how do i pay tuition",        # English function + domain words
    "pls help with my calendar",   # "pls" + domain word
    "whcih term am i in",          # typo "whcih"
    "café hours today",            # English with ONE stray accent — must NOT flip
]


@pytest.mark.parametrize("text", ENGLISH_NOISE_CASES)
def test_short_english_noise_resolves_to_english(text):
    assert _detect(text) == "en", f"{text!r} should bias to English"


# --------------------------------------------------------------------------
# 2. Short Spanish / Portuguese — MUST still detect correctly (proof we did
#    NOT over-correct). These clear the bar via foreign word indicators.
# --------------------------------------------------------------------------

SHORT_SPANISH_CASES = [
    "Hola",
    "Gracias",
    "Buenos días",
    "¿Cuándo abre el registro?",
]

SHORT_PORTUGUESE_CASES = [
    "Bom dia",
    "Obrigado",
    "Olá, preciso de ajuda",
    "Quando começa o bloco 3?",
]


@pytest.mark.parametrize("text", SHORT_SPANISH_CASES)
def test_short_spanish_still_detected(text):
    assert _detect(text) == "es", f"{text!r} should still detect as Spanish"


@pytest.mark.parametrize("text", SHORT_PORTUGUESE_CASES)
def test_short_portuguese_still_detected(text):
    assert _detect(text) == "pt", f"{text!r} should still detect as Portuguese"


# --------------------------------------------------------------------------
# 3. Long (>=40 char) non-English — the length path must still allow
#    confident non-English detection without needing the indicator bar.
# --------------------------------------------------------------------------

def test_long_spanish_detected():
    text = "Quisiera saber cuando abre el registro para el proximo semestre por favor"
    assert _detect(text) == "es"


def test_long_portuguese_detected():
    text = "Eu gostaria de saber quando comeca o registro para o proximo semestre por favor"
    assert _detect(text) == "pt"


def test_long_french_detected():
    text = "Je voudrais savoir quand les inscriptions ouvrent pour le prochain semestre"
    assert _detect(text) == "fr"


# --------------------------------------------------------------------------
# 4. Edge cases — empty / whitespace fall back to English.
# --------------------------------------------------------------------------

def test_empty_text_falls_back():
    assert _detect("") == "en"


def test_whitespace_only_falls_back():
    assert _detect("   ") == "en"


# --------------------------------------------------------------------------
# 5. The threshold constants exist and have sane values.
# --------------------------------------------------------------------------

def test_threshold_constants_present():
    assert LocalizationManager.SHORT_TEXT_CONFIDENCE_CHARS == 40
    assert LocalizationManager.MIN_FOREIGN_INDICATORS >= 2


# --------------------------------------------------------------------------
# detect_language_confident — used by per-request language resolution to let a
# confident PROMPT detection win over the gear-menu pref (pref is the backup).
# --------------------------------------------------------------------------


def test_confident_long_french_is_confident():
    lang, confident = LocalizationManager.detect_language_confident(
        "Comment passer du programme PathwayConnect à un programme menant à un diplôme?"
    )
    assert lang == "fr" and confident is True


def test_confident_long_english_is_confident():
    lang, confident = LocalizationManager.detect_language_confident(
        "How do I transition from PathwayConnect to a degree-seeking program?"
    )
    assert lang == "en" and confident is True


def test_short_english_with_indicator_is_confident():
    # "what is this" carries English indicators -> confident English.
    lang, confident = LocalizationManager.detect_language_confident("what is this")
    assert lang == "en" and confident is True


def test_short_ambiguous_is_not_confident():
    # A 2-char token with no English/foreign evidence -> bias-to-en fallback,
    # i.e. "couldn't tell" -> NOT confident (defer to the gear pref).
    lang, confident = LocalizationManager.detect_language_confident("ok")
    assert lang == "en" and confident is False


def test_empty_text_is_not_confident():
    lang, confident = LocalizationManager.detect_language_confident("")
    assert confident is False
