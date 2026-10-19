"""Tests for the presentation-only grounding guard.

As of 2026-05-21 this module holds NO topic-specific answer text. Grounding
judgement lives in the agentic loop (retrieval + critics). The guard only
makes citations visible. These tests lock in that the guard never rewrites,
removes, or substitutes answer content — it only attaches `[^N]` markers.
"""

from types import SimpleNamespace

from app.engine.grounding_guard import (
    apply_grounding_guards,
    decluster_citations,
    enforce_link_integrity,
    ensure_citation_coverage,
    normalize_citation_markers,
)


def _node(text: str):
    return SimpleNamespace(text=text)


def _lnode(url, text=""):
    return {"id": "x", "text": text, "metadata": {"url": url}}


def test_link_integrity_strips_fabricated_markdown_link():
    nodes = [_lnode("https://byupathway.edu/real")]
    out = enforce_link_integrity("See [the form](https://fake.example.com/x) now.", nodes)
    assert "(https://fake.example.com/x)" not in out
    assert "the form" in out  # label kept as plain text


def test_link_integrity_keeps_in_context_markdown_link():
    nodes = [_lnode("https://byupathway.edu/real")]
    txt = "Open [the page](https://byupathway.edu/real)."
    assert enforce_link_integrity(txt, nodes) == txt


def test_link_integrity_keeps_url_found_in_node_text():
    nodes = [_lnode("unknown", text="download at https://englishconnect.org/ec3 today")]
    txt = "Visit [EC3](https://englishconnect.org/ec3)."
    assert enforce_link_integrity(txt, nodes) == txt


def test_link_integrity_strips_bare_fabricated_url_keeps_citation():
    nodes = [_lnode("https://byupathway.edu/real")]
    out = enforce_link_integrity("Info[^1] at https://made-up.example.com/page.", nodes)
    assert "made-up.example.com" not in out
    assert "[^1]" in out  # citation markers untouched


def test_link_integrity_handles_nodewithscore_shape():
    nws = SimpleNamespace(
        node=SimpleNamespace(metadata={"url": "https://byupathway.edu/p"}, get_text=lambda: ""),
    )
    txt = "Go [here](https://byupathway.edu/p)."
    assert enforce_link_integrity(txt, [nws]) == txt


def test_apply_grounding_guards_runs_link_integrity():
    nodes = [_lnode("https://byupathway.edu/real", text="real content here")]
    out = apply_grounding_guards("X [bad](https://evil.example.com/y).", nodes)
    assert "evil.example.com" not in out


# --- ensure_citation_coverage ---------------------------------------------


def test_citation_coverage_adds_marker_to_uncited_substantive_lines():
    draft = (
        "### Heading\nGrades are due Tuesday of Week 07 [^2].\n"
        "Students should correct gathering assignments.\n- Do this promptly."
    )
    guarded = ensure_citation_coverage(draft, [_node("source")])

    assert "### Heading" in guarded  # headings untouched
    assert "Students should correct gathering assignments. [^1]" in guarded
    assert "- Do this promptly. [^1]" in guarded


def test_citation_coverage_leaves_wholly_uncited_answer_alone():
    # A refusal or an ungrounded reply: stamping [^1] would fake a source.
    draft = "That's not something the guides cover.\nTry the Online Instructor Support Line."
    assert ensure_citation_coverage(draft, [_node("source")]) == draft


def test_citation_coverage_skips_caveat_lines_in_a_cited_answer():
    draft = "You are paid on the 8th and 23rd [^1].\nThe guides don't include the per-block schedule."
    assert ensure_citation_coverage(draft, [_node("source")]) == draft


def test_citation_coverage_skips_fenced_drafts():
    draft = (
        "Here is a welcome message based on the guide [^1].\n\n"
        "```message\nHi [Student Name], welcome to [Course]!\nSee you in Week 01.\n```\n"
        "Send it before the block starts."
    )
    guarded = ensure_citation_coverage(draft, [_node("source")])

    assert "```message\nHi [Student Name], welcome to [Course]!\nSee you in Week 01.\n```" in guarded
    assert "Send it before the block starts. [^1]" in guarded


def test_citation_coverage_leaves_already_cited_lines_alone():
    draft = "Block 3 starts March 2 [^2]."
    assert ensure_citation_coverage(draft, [_node("source")]) == draft


def test_citation_coverage_skips_link_lines():
    draft = "**Link:** [Academic Exceptions](https://example.com)"
    guarded = ensure_citation_coverage(draft, [_node("source")])
    assert "[^1]" not in guarded


def test_citation_coverage_appends_marker_inside_table_cell():
    draft = "Credits by program [^1]:\n| Program | Credits |\n|---|---|\n| Applied Health | 60 |"
    guarded = ensure_citation_coverage(draft, [_node("source")])
    assert "| 60 [^1]|" in guarded  # marker lands in the last non-empty cell
    assert "|---|---|" in guarded  # separator row untouched


def test_citation_coverage_noop_without_sources():
    draft = "Students should correct gathering assignments."
    assert ensure_citation_coverage(draft, []) == draft


# --- apply_grounding_guards: pure passthrough -----------------------------


def test_apply_grounding_guards_does_not_remove_or_substitute_content():
    """The de-hardcoded guard must NEVER replace answer PROSE. A draft about
    refunds/progress keeps every sentence — the hallucination critic, not a
    keyword guard, owns unsupported-claim removal. (Redundant citation
    markers may be de-clustered — that's presentation, not content.)"""
    draft = (
        "If a student drops EnglishConnect, refund handling can vary [^1]. "
        "They may also lose course progress [^1]."
    )
    guarded = apply_grounding_guards(
        draft,
        [_node("EnglishConnect drop policy and refund details.")],
        user_question="Do students lose progress or get a refund?",
    )
    # Both sentences (the content) survive untouched.
    assert "refund handling can vary" in guarded
    assert "lose course progress" in guarded
    # The two consecutive [^1] markers de-cluster to one.
    assert guarded.count("[^1]") == 1


def test_apply_grounding_guards_only_adds_citation_coverage():
    draft = "Auto-drop is a policy [^1].\n\nStudents may be auto-dropped after the 8th day."
    guarded = apply_grounding_guards(
        draft,
        [_node("Auto-Drop policy support article.")],
        user_question="tell me about the auto drop exemption form",
    )
    # No substitution, no hardcoded caveat — just a visible marker.
    assert guarded == "Auto-drop is a policy [^1].\n\nStudents may be auto-dropped after the 8th day. [^1]"
    assert "couldn't find" not in guarded
    assert "Who to Contact" not in guarded


def test_apply_grounding_guards_does_not_inject_machinery_phrasing():
    """Regression: the guard must never emit 'I don't have retrieved source
    text' or similar internal-machinery narration."""
    draft = "Auto-Drop removes students who never access their course [^1]."
    guarded = apply_grounding_guards(
        draft,
        [_node("Auto-Drop policy article.")],
        user_question="So where's the form?",
        chat_history=[{"role": "user", "content": "auto drop exemption form"}],
    )
    assert "retrieved source text" not in guarded.lower()
    assert "should not claim" not in guarded.lower()


# --- decluster_citations -------------------------------------------------


def test_decluster_collapses_repeated_citation_in_a_list():
    """A list where every item cites the same source keeps the marker only
    on the LAST item."""
    draft = (
        "- Apply and register for courses [^1]\n"
        "- Complete the self-reliance lesson [^1]\n"
        "- Maintain enrollment [^1]"
    )
    out = decluster_citations(draft)
    assert out.count("[^1]") == 1
    assert out.strip().endswith("[^1]")  # kept on the last item


def test_decluster_keeps_marker_when_source_changes():
    draft = "First fact [^1]\nSecond fact [^1]\nThird fact [^2]\nFourth fact [^2]"
    out = decluster_citations(draft)
    # run of [^1] -> one [^1]; run of [^2] -> one [^2]
    assert out.count("[^1]") == 1
    assert out.count("[^2]") == 1


def test_decluster_allows_citation_to_reappear_after_a_different_one():
    draft = "A fact [^1]\nB fact [^2]\nC fact [^1]"
    out = decluster_citations(draft)
    # [^1] ... [^2] ... [^1]: none are a consecutive same-run, all kept.
    assert out.count("[^1]") == 2
    assert out.count("[^2]") == 1


def test_decluster_re_anchors_after_paragraph_break():
    draft = "Fact one [^1].\n\nA later paragraph with the same source [^1]."
    out = decluster_citations(draft)
    # paragraph break re-anchors — both [^1] kept.
    assert out.count("[^1]") == 2


def test_decluster_leaves_adjacent_distinct_citations_intact():
    draft = "Block 3 starts March 2 [^1][^2]."
    assert decluster_citations(draft) == draft


def test_decluster_strips_leading_space_cleanly():
    out = decluster_citations("First sentence [^1].\nSecond sentence [^1].")
    assert "First sentence." in out  # no double space, no dangling space


# --- link integrity on sign-in links (Phase 3) -----------------------------------

_SP = "https://byupathwayworldwideprod.sharepoint.com/sites/onlineinstructor/SitePages/Group-Setup-in-Canvas.aspx"


def test_link_integrity_keeps_a_sharepoint_link_found_in_the_guide_text():
    # The guide's PDF URL is the node url; the SharePoint link only appears inline in its text.
    nodes = [_lnode("https://missionaries.prod.byu-pathway.psdops.com/group-setup-in-canvas-ia",
                    text=f"Follow the [I-Learn Canvas Group Setup]({_SP}) steps.")]
    out = enforce_link_integrity(f"Use [Group Setup]({_SP}) [^1].", nodes)
    assert f"[Group Setup]({_SP})" in out


def test_link_integrity_strips_an_invented_sharepoint_link():
    nodes = [_lnode("https://missionaries.prod.byu-pathway.psdops.com/group-setup-in-canvas-ia",
                    text=f"Follow the [I-Learn Canvas Group Setup]({_SP}) steps.")]
    invented = "https://byupathwayworldwideprod.sharepoint.com/sites/onlineinstructor/SitePages/Made-Up.aspx"
    out = enforce_link_integrity(f"See [the page]({invented}) [^1].", nodes)
    assert invented not in out and "the page" in out


# --- shared link parser (Phase 3 review) -------------------------------------------


def test_link_integrity_keeps_a_citation_glued_to_an_allowed_url():
    nodes = [_lnode(_SP)]
    assert enforce_link_integrity(f"Open {_SP}[^1].", nodes) == f"Open {_SP}[^1]."


def test_link_integrity_drops_an_invented_url_but_keeps_its_citation():
    out = enforce_link_integrity("Open https://fake.example.com/x[^1].", [_lnode(_SP)])
    assert out == "Open [^1]."


def test_link_integrity_handles_titled_and_autolinks():
    nodes = [_lnode(_SP)]
    titled = f'[form]({_SP} "Form")'
    assert enforce_link_integrity(titled, nodes) == titled
    assert enforce_link_integrity('[form](https://fake.example.com/x "Form")', nodes) == "form"
    assert enforce_link_integrity(f"See <{_SP}>.", nodes) == f"See <{_SP}>."


def test_link_integrity_keeps_bold_and_code_urls_found_in_the_guide():
    nodes = [_lnode("https://p.example", text=f"See **{_SP}** for details.")]
    assert enforce_link_integrity(f"Go to **{_SP}** now", nodes) == f"Go to **{_SP}** now"
    assert enforce_link_integrity(f"Use `{_SP}` here", nodes) == f"Use `{_SP}` here"


def test_link_integrity_copies_a_nested_link_once():
    nodes = [_lnode("https://p.example", text="https://b.com/y and https://a.com/x")]
    text = "[<https://b.com/y>](https://a.com/x) tail"
    assert enforce_link_integrity(text, nodes) == text


def test_link_integrity_keeps_cjk_text_after_an_allowed_url():
    nodes = [_lnode("https://p.example", text=f"Open {_SP} first.")]
    assert enforce_link_integrity(f"请打开 {_SP}。", nodes) == f"请打开 {_SP}。"


def test_link_integrity_leaves_indentation_drafts_and_hard_breaks_alone():
    nodes = [_lnode(_SP)]
    text = "1. Open Canvas\n   - Go to People\nLine one  \nLine two\n```message\nHi,  there\n    indented\n```"
    assert enforce_link_integrity(text, nodes) == text


def test_link_integrity_tidies_only_the_seam_of_a_removed_url():
    out = enforce_link_integrity("See https://fake.example.com/x now.\n   - nested", [_lnode(_SP)])
    assert out == "See now.\n   - nested"


def test_coverage_after_an_unclosed_fence_still_applies():
    draft = "Intro [^1].\n```message\nHi\nA real claim here."
    assert "A real claim here. [^1]" in ensure_citation_coverage(draft, [_node("source")])


def test_near_miss_citation_markers_are_repaired():
    # "[^1^]" came back live in the Phase 6 eval (#6) and counted as uncited.
    assert normalize_citation_markers("Check Turnitin[^1^]. Ask first [^ 2 ].") == "Check Turnitin[^1]. Ask first [^2]."
    assert normalize_citation_markers("Already fine [^3].") == "Already fine [^3]."
    assert normalize_citation_markers("A footnote ^1 or [1] is left alone.") == "A footnote ^1 or [1] is left alone."


def test_repaired_markers_reach_the_final_answer():
    answer = "1. Collect evidence first[^1^].\n2. Keep an open mind[^1^]."
    out = apply_grounding_guards(answer, [_node("Collect evidence. Keep an open mind.")])
    # (decluster then keeps one [^1] for the run, as for any repeated citation)
    assert "[^1^]" not in out and out.endswith("open mind[^1].")


def test_literal_placeholder_markers_are_dropped():
    # "[^N]" copied from the prompt came back live in the Phase 6 eval (#6).
    assert normalize_citation_markers("Use Turnitin[^N]. Ask first [^n].") == "Use Turnitin. Ask first."
    assert normalize_citation_markers("Paid on the 8th [^1].") == "Paid on the 8th [^1]."
