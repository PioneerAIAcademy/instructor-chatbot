"""Prompt lock (CLAUDE.md §7 Phase 3): the load-bearing sentences of the
instructor prompts. If one of these fails, the wording changed. Change it
only on purpose, and update this file in the same commit.
"""

import pytest

from app.engine.prompts import CONDENSE_PROMPT_TEMPLATE, CONTEXT_PROMPT, build_system_prompt

SYSTEM = " ".join(build_system_prompt("October 19, 2026 at 9:00 AM UTC").split())
CONTEXT = " ".join(CONTEXT_PROMPT.split())


@pytest.mark.parametrize(
    "sentence",
    [
        # Grounding
        "Answer only from the numbered contexts.",
        "Never answer from general knowledge.",
        # Escalation steps are never dropped (Phase 6 eval #11)
        "always include that step, as the last step, with its link if the context gives one.",
        # Citation format
        "Put [^N] right after the sentence it supports.",
        "Never cite a context for a claim it doesn't make.",
        "Never put [^N] inside a drafted message.",
        "never the letter N itself.",
        # Sign-in links: the model hasn't read them, and must say so
        "You have NOT read those pages.",
        "Don't write a sign-in note after the link yourself",
        "Never summarize, quote, or describe what such a page says unless a context contains that text.",
        "Never say you opened, read, checked, or reviewed a linked page.",
        "cite the guide it came from with [^N]",
        "A link's title is not a description",
        "If the guide only lists the link",
        # External pages and institutions
        "Say whose page it is: in the sentence that uses one, name its owner",
        "follow the guide and mention the difference",
        "give both (labeled) or ask which institution the course belongs to",
        # FERPA
        "Never ask for a student's name, ID, grades, or other records.",
        "don't repeat them back",
        # Drafts, links, scope
        "put only the send-ready text in a ```message or ```email fence",
        "Only give URLs that appear in the contexts.",
        "Refuse briefly and stop.",
        # Audience and voice
        'Speak to the instructor as "you".',
        "Answer in the language of the instructor's question.",
    ],
)
def test_system_prompt_keeps_load_bearing_sentence(sentence):
    assert sentence in SYSTEM


def test_system_prompt_has_todays_date_and_no_missionary_persona():
    assert SYSTEM.startswith("Today's date is October 19, 2026 at 9:00 AM UTC.")
    lowered = SYSTEM.lower()
    for word in ("missionar", "gathering", "acm", "englishconnect", "learners"):
        assert word not in lowered, word


def test_terms_are_vocabulary_not_facts():
    # The glossary may define ACL/AIM/TGL, but facts about them must come from contexts.
    assert "ACL (Assistant Course Lead)" in SYSTEM
    assert "never from here" in SYSTEM


def test_context_prompt_keeps_the_covenant():
    assert "{context_str}" in CONTEXT_PROMPT
    assert "Never answer from training memory" in CONTEXT
    assert "Cite each sentence with [^N] inline" in CONTEXT


def test_condense_prompt_has_its_placeholders():
    assert "{chat_history}" in CONDENSE_PROMPT_TEMPLATE
    assert "{question}" in CONDENSE_PROMPT_TEMPLATE


def test_language_rule_defaults_to_the_question():
    assert "Answer in the language of the instructor's question." in SYSTEM


def test_language_rule_names_the_settings_pick():
    for code, name in (("es", "Spanish"), ("pt", "Portuguese")):
        prompt = " ".join(build_system_prompt("today", code).split())
        assert f"Answer in {name}: it's the language the instructor chose in settings" in prompt
        assert "Answer in the language of the instructor's question." not in prompt
    # An unknown code keeps the default rule.
    assert "Answer in the language of the instructor's question." in build_system_prompt("today", "zz")
