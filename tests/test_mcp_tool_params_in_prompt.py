"""Regression for issue #2509 — MCP tools must expose their input parameters.

``McpManager.get_tool_descriptions_for_prompt()`` previously emitted only
``- name: description`` per MCP tool, so agents (notably on the fenced-block
tool path used by Ollama models) never saw a tool's declared inputs and guessed
argument names from the description alone. ``get_all_tools()`` also dropped the
``input_schema`` entirely. These tests pin that the inputs now reach both
surfaces.
"""

from src.mcp_manager import McpManager


def _mgr_with_tool() -> McpManager:
    mgr = McpManager()
    mgr._tools = {
        "srv1": [
            {
                "name": "fetch_doc",
                "description": "Fetch a document by path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "file path"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            }
        ]
    }
    mgr._connections = {"srv1": {"status": "connected", "name": "Files", "identity": ""}}
    return mgr


def test_get_all_tools_carries_input_schema():
    tools = _mgr_with_tool().get_all_tools()
    assert tools and tools[0]["input_schema"]["properties"]["path"]["type"] == "string"


def test_explicit_mcp_server_reference_keeps_its_tools_visible():
    mgr = _mgr_with_tool()

    selected = mgr.get_tools_for_explicit_server_reference(
        "Use the Files MCP tool to fetch a document."
    )

    assert selected == {"mcp__srv1__fetch_doc"}


def test_explicit_mcp_server_reference_prioritizes_named_tool_identifiers():
    mgr = McpManager()
    mgr._tools = {"seerr": [
        {"name": "seerr_search", "description": "Search media."},
        {"name": "seerr_discover", "description": "Browse discovery pages."},
        {"name": "seerr_requests", "description": "Create or list requests."},
    ]}
    mgr._connections = {"seerr": {"name": "Seerr", "identity": ""}}

    selected = mgr.get_tools_for_explicit_server_reference(
        "Use Seerr's seerr_search, then seerr_requests to request the movie."
    )

    assert selected == {
        "mcp__seerr__seerr_search",
        "mcp__seerr__seerr_requests",
    }


def test_explicit_mcp_server_reference_keeps_search_and_request_workflow_together():
    mgr = McpManager()
    mgr._tools = {"seerr": [
        {"name": "seerr_search", "description": "Search media."},
        {"name": "seerr_discover", "description": "Browse discovery pages."},
        {"name": "seerr_requests", "description": "Create or list requests."},
    ]}
    mgr._connections = {"seerr": {"name": "Seerr", "identity": ""}}

    selected = mgr.get_tools_for_explicit_server_reference(
        "Request Toy Story 5 on Seerr."
    )

    assert selected == {
        "mcp__seerr__seerr_search",
        "mcp__seerr__seerr_requests",
    }


def test_explicit_nextcloud_folder_listing_excludes_unrelated_tools():
    mgr = McpManager()
    mgr._tools = {"nextcloud": [
        {"name": "nc_webdav_list_directory", "description": "List directory contents."},
        {"name": "deck_attach_file", "description": "Attach a file to a Deck card."},
        {"name": "deck_get_stacks", "description": "List stacks."},
    ]}
    mgr._connections = {"nextcloud": {"name": "Nextcloud", "identity": ""}}

    assert mgr.get_tools_for_explicit_server_reference(
        "List files inside Work on Nextcloud."
    ) == {"mcp__nextcloud__nc_webdav_list_directory"}


def test_explicit_nextcloud_file_read_prefers_read_file_over_list_directory():
    mgr = McpManager()
    mgr._tools = {"nextcloud": [
        {"name": "nc_webdav_list_directory", "description": "List directory contents."},
        {"name": "nc_webdav_read_file", "description": "Read a file's contents."},
        {"name": "deck_attach_file", "description": "Attach a file to a Deck card."},
    ]}
    mgr._connections = {"nextcloud": {"name": "Nextcloud", "identity": ""}}

    assert mgr.get_tools_for_explicit_server_reference(
        "show me the contents of STREAM IDEAS.md on nextcloud"
    ) == {"mcp__nextcloud__nc_webdav_read_file"}


def test_explicit_soulseek_lookup_keeps_search_and_results_together():
    mgr = McpManager()
    mgr._tools = {"soulseek": [
        {"name": "slskd_create_search", "description": "Create a search."},
        {"name": "slskd_get_search_results", "description": "Read results."},
        {"name": "slskd_create_transfers_downloads", "description": "Queue a download."},
        {"name": "slskd_delete_search", "description": "Delete a search."},
    ]}
    mgr._connections = {"soulseek": {"name": "Soulseek", "identity": ""}}

    assert mgr.get_tools_for_explicit_server_reference("Find this song on Soulseek.") == {
        "mcp__soulseek__slskd_create_search",
        "mcp__soulseek__slskd_get_search_results",
    }


def test_explicit_soulseek_download_adds_only_the_queue_tool():
    mgr = McpManager()
    mgr._tools = {"soulseek": [
        {"name": "slskd_create_search", "description": "Create a search."},
        {"name": "slskd_get_search_results", "description": "Read results."},
        {"name": "slskd_create_transfers_downloads", "description": "Queue a download."},
        {"name": "slskd_delete_search", "description": "Delete a search."},
    ]}
    mgr._connections = {"soulseek": {"name": "Soulseek", "identity": ""}}

    assert mgr.get_tools_for_explicit_server_reference("Download this song from Soulseek.") == {
        "mcp__soulseek__slskd_create_search",
        "mcp__soulseek__slskd_get_search_results",
        "mcp__soulseek__slskd_create_transfers_downloads",
    }


def test_explicit_mcp_server_reference_returns_a_bounded_relevant_set():
    mgr = McpManager()
    mgr._tools = {"nextcloud": [
        {"name": "webdav_list_directory", "description": "List directory contents."},
        {"name": "webdav_create_file", "description": "Create a file."},
    ]}
    mgr._connections = {"nextcloud": {"name": "Nextcloud MCP", "identity": ""}}

    selected = mgr.get_tools_for_explicit_server_reference(
        "Use the Nextcloud MCP to list my root folder contents. Read-only: do not create files.",
        max_tools=1,
    )

    assert selected == {"mcp__nextcloud__webdav_list_directory"}


def test_explicit_mcp_server_reference_respects_disabled_tools_and_names():
    mgr = _mgr_with_tool()

    disabled = mgr.get_tools_for_explicit_server_reference(
        "Use Files MCP", {"srv1": {"fetch_doc"}}
    )
    unrelated = mgr.get_tools_for_explicit_server_reference("Use Nextcloud MCP")

    assert disabled == set()
    assert unrelated == set()


def test_prompt_descriptions_surface_param_names_and_required():
    text = _mgr_with_tool().get_tool_descriptions_for_prompt()
    assert "mcp__srv1__fetch_doc" in text
    assert "path" in text and "limit" in text   # inputs are surfaced to the model
    assert "required" in text                   # required-ness is surfaced


def test_prompt_descriptions_only_include_selected_mcp_tools():
    mgr = _mgr_with_tool()
    mgr._tools["srv1"].append({"name": "delete_doc", "description": "Delete a document."})

    text = mgr.get_tool_descriptions_for_prompt(tool_names={"mcp__srv1__fetch_doc"})

    assert "mcp__srv1__fetch_doc" in text
    assert "mcp__srv1__delete_doc" not in text


def test_format_mcp_params_handles_no_params():
    from src.mcp_manager import _format_mcp_params

    assert _format_mcp_params({}) == ""
    assert _format_mcp_params(None) == ""
    assert _format_mcp_params({"type": "object", "properties": {}}) == ""


def test_format_mcp_params_marks_required_and_types():
    from src.mcp_manager import _format_mcp_params

    out = _format_mcp_params(
        {
            "type": "object",
            "properties": {"q": {"type": "string"}, "n": {"type": "integer"}},
            "required": ["q"],
        }
    )
    assert '"q": string (required)' in out
    assert '"n": integer' in out
    assert '"n": integer (required)' not in out  # optional param not marked required
