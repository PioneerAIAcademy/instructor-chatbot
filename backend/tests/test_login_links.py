"""Sign-in link annotator (CLAUDE.md §8.3, §7 Phase 3)."""

import pytest

from app.engine.login_links import annotate_login_links, needs_sign_in

SP = "https://byupathwayworldwideprod.sharepoint.com/sites/onlineinstructor/SitePages/Group-Setup-in-Canvas.aspx"
ONEDRIVE = "https://webmailbyui-my.sharepoint.com/:v:/g/personal/x/abc"
PUBLIC = "https://www.byupathway.edu/student-support"


@pytest.fixture(autouse=True)
def _default_hosts(monkeypatch):
    monkeypatch.delenv("LOGIN_LINK_HOSTS", raising=False)


def test_adds_the_note_once_after_a_markdown_link():
    out = annotate_login_links(f"See [Group Setup]({SP}) [^1].")
    assert out.text == f"See [Group Setup]({SP}) (sign-in required) [^1]."
    assert out.added == 1


def test_bare_url_keeps_its_trailing_punctuation_outside():
    out = annotate_login_links(f"Open {SP}.")
    assert out.text == f"Open {SP} (sign-in required)."


def test_is_idempotent():
    once = annotate_login_links(f"See [Group Setup]({SP}) and {ONEDRIVE}")
    twice = annotate_login_links(once.text)
    assert once.added == 2
    assert twice.text == once.text and twice.added == 0


@pytest.mark.parametrize(
    "after",
    [" (sign-in required)", " (requires sign in)", " (requires a BYU login)", " **(sign-in required)**",
     " (requer login)", " (로그인 필요)", "（需要登录）"],
)
def test_skips_links_already_noted(after):
    text = f"[Course directory](https://pathwayadmin.byui.edu/x){after}"
    out = annotate_login_links(text)
    assert out.text == text and out.added == 0


def test_note_far_after_the_link_does_not_count():
    text = f"[Course directory](https://pathwayadmin.byui.edu/x). " + "x" * 50 + " sign in"
    assert annotate_login_links(text).added == 1


def test_a_later_links_note_is_not_mistaken_for_this_ones():
    text = f"[A]({SP}) [B](https://companion.byupathway.edu/home) (sign-in required)"
    out = annotate_login_links(text)
    assert out.added == 1 and out.links == 2
    assert out.text.startswith(f"[A]({SP}) (sign-in required) [B]")


@pytest.mark.parametrize(
    "url",
    [PUBLIC, "https://community.canvaslms.com/t5/x", "https://notsharepoint.com/x", "https://sharepoint.com.evil.io/x"],
)
def test_skips_non_login_hosts(url):
    text = f"See [the page]({url})."
    out = annotate_login_links(text)
    assert out.text == text and out.added == 0


@pytest.mark.parametrize(
    "url,expected",
    [
        (SP, True),
        (ONEDRIVE, True),
        ("https://portal.byupathway.edu/academics", True),
        ("https://companion.byupathway.edu/", True),
        ("https://pathwayadmin.byui.edu/directory", True),
        (PUBLIC, False),
        ("not a url", False),
    ],
)
def test_needs_sign_in_matches_hosts_on_domain_boundaries(url, expected):
    assert needs_sign_in(url) is expected


def test_links_inside_a_draft_fence_are_left_alone():
    text = (
        f"Use the guide's template [^1]. The checklist is [here]({SP}).\n\n"
        f"```message\nHi [Student Name], see {SP} for details.\n```"
    )
    out = annotate_login_links(text)
    assert out.added == 1
    assert f"[here]({SP}) (sign-in required)" in out.text
    assert f"```message\nHi [Student Name], see {SP} for details.\n```" in out.text


def test_label_follows_the_reply_language():
    out = annotate_login_links(f"Veja [o guia]({SP}).", "pt")
    assert out.text == f"Veja [o guia]({SP}) (requer login)."


def test_unknown_language_falls_back_to_english():
    assert "(sign-in required)" in annotate_login_links(SP, "xx").text


def test_hosts_come_from_login_link_hosts(monkeypatch):
    monkeypatch.setenv("LOGIN_LINK_HOSTS", "docs.google.com")
    assert annotate_login_links("https://docs.google.com/document/d/1").added == 1
    assert annotate_login_links(SP).added == 0


def test_text_without_links_is_untouched():
    out = annotate_login_links("Grades are due Tuesday of Week 07 [^1].")
    assert out.text == "Grades are due Tuesday of Week 07 [^1]." and out.added == 0


# --- scripts/ask.py checks ------------------------------------------------------------

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402


def _ask_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ask.py"
    spec = importlib.util.spec_from_file_location("ask_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(n, role="instructor"):
    return {"citation_node_id": str(n), "metadata": {"role": role, "slug": f"s{n}-ia"}}


def test_ask_parses_the_vercel_stream():
    ask = _ask_module()
    lines = ['0:""', '0:"Hello "', '0:"there"', "",
             '8:[{"type": "user_language", "data": {"language": "en"}, "trace_id": "t1"}]',
             '8:[{"type": "sources", "data": {"nodes": []}, "trace_id": "t1"}]']
    text, annotations, problems = ask.parse_stream(lines)
    assert text == "Hello there" and annotations[0]["trace_id"] == "t1" and problems == []


def test_ask_reports_a_stream_that_breaks_the_contract():
    ask = _ask_module()
    _, _, problems = ask.parse_stream(['0:"Hi"', "junk", '8:[{"type": "calendar_card", "data": {}, "trace_id": null}]'])
    assert any("unexpected line prefix" in p for p in problems)
    assert any("undocumented annotation type" in p for p in problems)
    assert any("missing sources" in p for p in problems)


def test_ask_checks_catch_unlabeled_links_reading_claims_and_bad_citations():
    ask = _ask_module()
    good = {"answer": f"Use [it]({SP}) (sign-in required) [^1].", "sources": [_source(1)]}
    assert ask.check(good) == []

    bad = {
        "answer": f"I opened [it]({SP}) and it says to wait [^2].",
        "sources": [_source(1, role="missionary")],
    }
    problems = ask.check(bad)
    assert any("without the note" in p for p in problems)
    assert any("reading claim" in p for p in problems)
    assert any("[^2] has no matching source" in p for p in problems)
    assert any("non-instructor source" in p for p in problems)


# --- review fixes -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "after",
    [", then sign in to WhatsApp Web.", " before signing the agreement.", ". Log in using your BYU-Idaho email.",
     " — you'll need to log in"],
)
def test_a_sentence_about_signing_in_is_not_a_label(after):
    out = annotate_login_links(f"[the page]({SP}){after}")
    assert out.added == 1
    assert out.text.startswith(f"[the page]({SP}) (sign-in required)")


def test_label_goes_before_a_citation_glued_to_a_bare_url():
    out = annotate_login_links(f"Open {SP}[^1].", "pt")
    assert out.text == f"Open {SP} (requer login)[^1]."


def test_label_goes_after_an_autolink():
    out = annotate_login_links(f"See <{SP}> now.")
    assert out.text == f"See <{SP}> (sign-in required) now."


def test_label_goes_after_a_titled_link():
    out = annotate_login_links(f'[form]({SP} "Form") now.')
    assert out.text == f'[form]({SP} "Form") (sign-in required) now.'


def test_links_counts_every_sign_in_link_even_when_none_needed_a_label():
    text = " ".join(f"[{i}]({SP}?{i}) (sign-in required)" for i in range(3))
    out = annotate_login_links(text)
    assert out.links == 3 and out.added == 0


def test_every_supported_language_has_a_label_and_nothing_else():
    from app.utils.localization import LocalizationManager, MessageType

    labels = LocalizationManager.FALLBACK_MESSAGES[MessageType.SIGN_IN_REQUIRED]
    assert set(labels) == set(LocalizationManager.SUPPORTED_LANGUAGES)
    for lang in LocalizationManager.SUPPORTED_LANGUAGES:
        label = annotate_login_links(SP, lang).text[len(SP) + 1:]
        assert label == labels[lang], lang


def test_ask_check_skips_drafts_and_knows_every_label():
    ask = _ask_module()
    in_draft = {"answer": f"Send this [^1].\n\n```message\nHi, see {SP}\n```", "sources": [_source(1)]}
    assert ask.check(in_draft) == []
    korean = {"answer": f"[가이드]({SP}) (로그인 필요) [^1].", "sources": [_source(1)]}
    assert ask.check(korean) == []


# --- Phase 4 review ---------------------------------------------------------------------


def test_a_note_after_a_citation_counts():
    text = f"See [Guide]({SP})[^1] (sign-in required)."
    out = annotate_login_links(text)
    assert out.text == text and out.links == 1 and out.added == 0
    ask = _ask_module()
    assert ask.check({"answer": text, "sources": [_source(1)]}) == []


def test_a_parenthesized_bare_url_gets_its_label_outside_the_parentheses():
    out = annotate_login_links(f"See ({SP}) ok")
    assert out.text == f"See ({SP}) (sign-in required) ok"
    assert annotate_login_links(out.text).added == 0  # still idempotent


def test_bold_sign_in_url_is_labeled_after_the_bold_marker_text():
    out = annotate_login_links(f"Go to **{SP}** now")
    assert out.added == 1 and "**" in out.text


def test_language_function_is_only_called_when_a_label_is_needed():
    calls = []

    def lang():
        calls.append(1)
        return "pt"

    annotate_login_links("No sign-in links here: https://www.byupathway.edu/x", lang)
    annotate_login_links(f"Labeled already: [x]({SP}) (sign-in required)", lang)
    assert calls == []
    assert "(requer login)" in annotate_login_links(f"[x]({SP}) and [y]({SP}?2)", lang).text
    assert calls == [1]  # resolved once for both links
