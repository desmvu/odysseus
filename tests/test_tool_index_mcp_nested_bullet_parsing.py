"""Regression: `ToolIndex.index_mcp_tools()` (src/tool_index.py) parsed MCP
tool entries by checking `line.startswith("- ")` on the *stripped* line,
losing the 2-space-indent signal that distinguishes a genuine top-level tool
line (`get_tool_descriptions_for_prompt()` always emits `f"  - {name}: ..."`)
from a deeper-indented nested bullet inside a tool's own multi-line
description (observed: Seerr tool docs embedding param lines like
`    - type: ...`). Since multiple real tools can share the same nested param
name, this produced duplicate chromadb IDs (e.g. repeated `mcp_type`) and
broke the entire upsert batch, silently degrading tool-RAG retrieval for
every query that didn't hit an exact keyword/skill match.

Fix: the parser now checks the RAW (unstripped) line for exactly the 2-space
indent (`raw_line.startswith("  - ") and not raw_line.startswith("   ")`)
before treating a line as a top-level tool entry.
"""

from src.embedding_lanes import LANE_CUSTOM, LANE_FASTEMBED, EmbeddingLane
from src.tool_index import ToolIndex
from tests.helpers.embedding_lanes import FakeCollection, FakeEmbedder


class _FakeMcpManager:
    def __init__(self, prompt_text, generation=1):
        self._prompt_text = prompt_text
        self._generation = generation

    def get_tool_descriptions_for_prompt(self, disabled_map=None):
        return self._prompt_text


def _index():
    ti = ToolIndex.__new__(ToolIndex)
    ti._mcp_generation = -1
    custom_lane = EmbeddingLane(
        name=LANE_CUSTOM,
        client=FakeEmbedder(768, "nomic", "http://embeddings/v1"),
        collection=FakeCollection("odysseus_tool_index_custom", metadata={"embedding_lane": "custom"}),
        collection_name="odysseus_tool_index_custom",
        model="nomic",
        url="http://embeddings/v1",
        dimension=768,
        fingerprint="custom",
    )
    fast_lane = EmbeddingLane(
        name=LANE_FASTEMBED,
        client=FakeEmbedder(384, "mini", "local://fastembed"),
        collection=FakeCollection("odysseus_tool_index_fastembed", metadata={"embedding_lane": "fastembed"}),
        collection_name="odysseus_tool_index_fastembed",
        model="mini",
        url="local://fastembed",
        dimension=384,
        fingerprint="fast",
    )
    ti._lanes = [custom_lane, fast_lane]
    return ti


# Mirrors a real multi-line tool description embedding a deeper-indented
# nested param bullet, the exact shape that triggered the bug (Seerr).
PROMPT_TEXT = (
    "**seerr:**\n"
    "  - request_media: Request a movie or show.\n"
    "    - type: movie or tv\n"
    "  - approve_request: Approve a pending request.\n"
)


def test_nested_description_bullet_is_not_indexed_as_a_phantom_tool():
    ti = _index()
    mgr = _FakeMcpManager(PROMPT_TEXT)

    ti.index_mcp_tools(mgr)

    ids = set(ti._lanes[0].collection.rows.keys())
    assert "mcp_type" not in ids, "nested '- type: ...' bullet must not become its own tool entry"


def test_genuine_top_level_tools_are_still_indexed():
    ti = _index()
    mgr = _FakeMcpManager(PROMPT_TEXT)

    ti.index_mcp_tools(mgr)

    ids = set(ti._lanes[0].collection.rows.keys())
    assert ids == {"mcp_request_media", "mcp_approve_request"}


def test_two_tools_sharing_a_nested_param_name_do_not_collide():
    """The concrete failure mode: two DIFFERENT tools whose descriptions both
    embed a nested '- type: ...' line used to collapse into one duplicate
    'mcp_type' id and silently corrupt the whole upsert batch."""
    ti = _index()
    prompt = (
        "**seerr:**\n"
        "  - request_media: Request a movie or show.\n"
        "    - type: movie or tv\n"
        "  - search_media: Search the catalog.\n"
        "    - type: search filter\n"
    )
    mgr = _FakeMcpManager(prompt)

    ti.index_mcp_tools(mgr)

    ids = set(ti._lanes[0].collection.rows.keys())
    assert ids == {"mcp_request_media", "mcp_search_media"}
    assert ti._mcp_generation == 1
