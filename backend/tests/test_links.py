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
