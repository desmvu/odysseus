"""Unknown tool dispatch: near-miss names get a "did you mean" suggestion.

Covers BUG-2026-09-18T101500 — a hallucinated/typo'd tool name previously got
a bare "Unknown tool: X" error with no hint toward the real name, so a model
(especially a small one) had no signal to self-correct within the turn.
"""
import pytest

from src.agent_tools import ToolBlock
from src.tool_execution import execute_tool_block, NO_TOOL_SECURITY_CONTEXT


@pytest.mark.asyncio
async def test_near_miss_tool_name_gets_did_you_mean_suggestion():
    _desc, result = await execute_tool_block(
        ToolBlock("read_fiel", "{}"),
        security_context=NO_TOOL_SECURITY_CONTEXT,
    )
    assert result.get("exit_code") == 1
    error = result.get("error", "")
    assert "Unknown tool" in error
    assert "did you mean" in error.lower()
    assert "read_file" in error


@pytest.mark.asyncio
async def test_no_close_match_leaves_plain_unknown_tool_error():
    _desc, result = await execute_tool_block(
        ToolBlock("totally_made_up_capability_xyz", "{}"),
        security_context=NO_TOOL_SECURITY_CONTEXT,
    )
    assert result.get("exit_code") == 1
    error = result.get("error", "")
    assert error == "Unknown tool: totally_made_up_capability_xyz"
    assert "did you mean" not in error.lower()
