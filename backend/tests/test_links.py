"""The shared link and fence parser (app/utils/links.py)."""

import pytest

from app.utils.links import find_links, split_fences

SP = "https://x.sharepoint.com/A.aspx"


def _kinds(text):
    return [(link.kind, link.url) for link in find_links(text)]


def test_finds_markdown_titled_autolink_and_bare_links_in_order():
    text = f'[a]({SP}) and [b]({SP}?2 "Title") and <{SP}?3> and {SP}?4.'
    assert _kinds(text) == [
        ("markdown", SP), ("markdown", f"{SP}?2"), ("autolink", f"{SP}?3"), ("bare", f"{SP}?4"),
    ]


def test_bare_url_stops_before_a_citation_and_trailing_punctuation():
    assert _kinds(f"Open {SP}[^1].") == [("bare", SP)]
    assert _kinds(f"Open {SP}.") == [("bare", SP)]


def test_url_inside_a_markdown_link_is_not_found_twice():
    assert len(find_links(f"[{SP}]({SP})")) == 1


@pytest.mark.parametrize(
    "text",
    [
        "plain\ntext\n",
        "before\n```message\nHi there\n```\nafter\n",
        "intro\n```email\nunclosed draft\nstill draft",
        "```\ncode\n```",
    ],
)
def test_split_fences_round_trips(text):
    assert "".join(seg for _, seg in split_fences(text)) == text


def test_split_fences_marks_fence_lines_and_bodies():
    runs = split_fences("before\n```message\nHi\n```\nafter")
    assert runs == [(False, "before\n"), (True, "```message\nHi\n```\n"), (False, "after")]


# --- Phase 4 review --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [f"Go to **{SP}** now", f"Use `{SP}` here", f"See __{SP}__.", f"Old: ~~{SP}~~"],
)
def test_bare_url_excludes_emphasis_and_code_markers(text):
    assert _kinds(text) == [("bare", SP)]


def test_a_link_nested_inside_another_is_not_found_separately():
    links = find_links("[<https://b.com/y>](https://a.com/x) tail")
    assert [(link.kind, link.url) for link in links] == [("markdown", "https://a.com/x")]


def test_links_never_overlap():
    text = f"[<{SP}>]({SP}?2) and [{SP}?3]({SP}?4) and <{SP}?5> and {SP}?6"
    links = find_links(text)
    for a, b in zip(links, links[1:]):
        assert a.end <= b.start


# --- PR #4 review ------------------------------------------------------------------------


@pytest.mark.parametrize("text", [f"请打开 {SP}。", f"（见 {SP}）", f"{SP}，然后"])
def test_bare_url_stops_at_cjk_punctuation(text):
    assert _kinds(text) == [("bare", SP)]


def test_a_one_line_code_span_is_not_a_fence():
    runs = split_fences("```Week 07``` is the last week\nSee the link.\n")
    assert runs == [(False, "```Week 07``` is the last week\nSee the link.\n")]


def test_an_unclosed_fence_is_ordinary_text():
    text = "Intro\n```message\nHi there\n\nNow see the link.\n"
    assert split_fences(text) == [(False, text)]


def test_fence_info_reads_the_tag():
    from app.utils.links import fence_info

    assert fence_info("```message\n") == "message"
    assert fence_info("   ```Email") == "email"
    assert fence_info("```") == ""
    assert fence_info("```Week 07``` is the last week") is None
    assert fence_info("    ```message") is None  # 4 spaces: indented code, not a fence
