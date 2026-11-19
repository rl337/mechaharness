"""Every generated footnote definition must have an actual inline reference."""

from __future__ import annotations

import re

import pytest

from tests.stories.commands.sync_guide import GUIDE_PATH, _render_footnotes


@pytest.mark.parametrize(
    "prose,definitions,listed",
    [
        ({"narrative": "No inline citations"}, set(), {"first", "second"}),
        ({"narrative": "Both sources[^first][^second]"}, {"first", "second"}, set()),
        ({"narrative": "One source[^first]"}, {"first"}, {"second"}),
        ({"implementation": "Implementation source[^second]"}, {"second"}, {"first"}),
        ({"validation": "Validation source[^first]"}, {"first"}, {"second"}),
    ],
    ids=["no-inline", "all-inline", "mixed", "implementation", "validation"],
)
def test_attribution_keeps_cited_definitions_and_uncited_source_links(prose, definitions, listed):
    story = {
        **prose,
        "footnotes": [
            {"id": name, "label": name, "url": f"https://example.com/{name}"}
            for name in ("first", "second")
        ],
    }
    rendered = "\n".join(_render_footnotes(story))
    assert set(re.findall(r"^\[\^([^\]]+)\]:", rendered, flags=re.MULTILINE)) == definitions
    for name in listed:
        assert re.search(rf"^\d+\. \[{name}\]", rendered, flags=re.MULTILINE)
    for name in ("first", "second"):
        assert f"https://example.com/{name}" in rendered


def test_generated_guide_has_no_unreferenced_footnote_definitions():
    text = GUIDE_PATH.read_text()
    definitions = set(re.findall(r"^\[\^([^\]]+)\]:", text, flags=re.MULTILINE))
    prose = re.sub(r"^\[\^[^\]]+\]:.*$", "", text, flags=re.MULTILINE)
    references = set(re.findall(r"\[\^([^\]]+)\]", prose))
    assert not definitions - references, (
        f"Unreferenced footnotes: {sorted(definitions - references)}"
    )
