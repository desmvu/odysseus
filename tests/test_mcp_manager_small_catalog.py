"""Regression: `get_tools_for_explicit_server_reference` (src/mcp_manager.py)
ran a named server's tool catalog through the same lexical-ranking + max_tools
cap designed for hundred-tool servers (Nextcloud/slskd), even when the server
only exposes a handful of tools. Ranking a short natural-language query
against a small catalog can drop the one tool the model actually needed.

Observed: a 9-tool YouTube analytics server queried with "last 10 videos"
ranked yt_channel_info/yt_channel_overview/yt_audience_retention above
yt_top_videos, which the model then reported as "not available".

Fix: servers with <= 12 enabled tools bypass lexical ranking/max_tools
entirely and hand back their whole catalog (`small_catalog_tools`).
"""

from src.mcp_manager import McpManager


def _mgr_with_server(server_id, tool_names):
    mgr = McpManager()
    mgr._tools = {server_id: [{"name": name} for name in tool_names]}
    return mgr


def test_small_catalog_bypasses_ranking_and_returns_whole_catalog():
    tool_names = [
        "yt_channel_info", "yt_channel_overview", "yt_audience_retention",
        "yt_top_videos", "yt_video_stats", "yt_comments", "yt_search",
        "yt_playlist_items", "yt_subscribers",
    ]
    mgr = _mgr_with_server("yt_analytics", tool_names)

    result = mgr.get_tools_for_explicit_server_reference(
        "last 10 videos", server_ids={"yt_analytics"}, max_tools=3,
    )

    assert result == {f"mcp__yt_analytics__{name}" for name in tool_names}
    # The specific regression: the model-needed tool must survive even though
    # max_tools=3 would have capped a ranked result down to 3 entries.
    assert "mcp__yt_analytics__yt_top_videos" in result


def test_small_catalog_threshold_is_inclusive_of_twelve():
    tool_names = [f"tool_{i}" for i in range(12)]
    mgr = _mgr_with_server("srv", tool_names)

    result = mgr.get_tools_for_explicit_server_reference(
        "do something", server_ids={"srv"}, max_tools=3,
    )

    assert result == {f"mcp__srv__{name}" for name in tool_names}


def test_large_catalog_above_threshold_still_gets_ranked_and_capped():
    tool_names = [f"tool_{i}" for i in range(13)] + ["do_something_special"]
    mgr = _mgr_with_server("big_srv", tool_names)

    result = mgr.get_tools_for_explicit_server_reference(
        "do something special", server_ids={"big_srv"}, max_tools=3,
    )

    assert len(result) <= 3
    assert result != {f"mcp__big_srv__{name}" for name in tool_names}
