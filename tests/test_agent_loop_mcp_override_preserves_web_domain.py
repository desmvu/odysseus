"""Regression: `_relevant_tools` gets wholesale-replaced (not unioned) at
three points in src/agent_loop.py whenever an MCP tool selection is narrower
than generic tool-RAG: an explicitly-named server, a resource follow-up, and
a skill-triggered MCP toolset. Before this fix, none of the three carried
forward WEB_TOOL_NAMES ({web_search, web_fetch}) even when the domain
classifier (`_classify_agent_request`) had already detected "web" intent for
the same message — a turn like "check Gold MCP, and also look up today's
headline" would silently lose web_search once the Gold MCP override fired.

Fix: a single `_web_domain_tools` set (WEB_TOOL_NAMES if "web" in domains
else empty) is computed once and unioned into all three replacement sites,
mirroring the existing `_mcp_document_transfer_tools` carve-out.

The three sites live inside one large async streaming function with no
standalone entry point cheap to unit-test in isolation, so this is a
source-level regression test (same pattern as
tests/test_email_pdf_dock_overlap_js.py) asserting the exact invariant: a
single web-domain gate defined once, unioned into every MCP-override site.
"""

from pathlib import Path

AGENT_LOOP_PY = (Path(__file__).resolve().parents[1] / "src/agent_loop.py").read_text()


def test_web_domain_tools_gate_is_defined_once_from_the_domain_classifier():
    assert (
        '_web_domain_tools = WEB_TOOL_NAMES if "web" in (_intent.get("domains") or set()) else set()'
        in AGENT_LOOP_PY
    )


def test_explicit_mcp_server_override_carries_web_domain_tools_forward():
    block = AGENT_LOOP_PY[
        AGENT_LOOP_PY.index("_explicit_mcp_tools = mcp_mgr.get_tools_for_explicit_server_reference")
        : AGENT_LOOP_PY.index("_explicit_mcp_tools = mcp_mgr.get_tools_for_explicit_server_reference") + 900
    ]
    assert "| _mcp_document_transfer_tools" in block
    assert "| _web_domain_tools" in block


def test_mcp_resource_followup_override_carries_web_domain_tools_forward():
    block = AGENT_LOOP_PY[
        AGENT_LOOP_PY.index("_mcp_followup_tools = mcp_mgr.get_tools_for_explicit_server_reference")
        : AGENT_LOOP_PY.index("_mcp_followup_tools = mcp_mgr.get_tools_for_explicit_server_reference") + 900
    ]
    assert "| _mcp_document_transfer_tools" in block
    assert "| _web_domain_tools" in block


def test_skill_triggered_mcp_override_carries_web_domain_tools_forward():
    block = AGENT_LOOP_PY[
        AGENT_LOOP_PY.index("_skill_mcp_tools = mcp_mgr.get_tools_for_explicit_server_reference")
        : AGENT_LOOP_PY.index("_skill_mcp_tools = mcp_mgr.get_tools_for_explicit_server_reference") + 1400
    ]
    assert "| _mcp_document_transfer_tools" in block
    assert "| _web_domain_tools" in block


def test_web_domain_gate_reuses_the_shared_web_tool_names_constant():
    """Guards against a future edit hardcoding {"web_search", "web_fetch"}
    inline instead of the shared WEB_TOOL_NAMES constant, which is also what
    the plain "web" domain seeding path (non-MCP) already uses."""
    assert "WEB_TOOL_NAMES if \"web\" in" in AGENT_LOOP_PY
