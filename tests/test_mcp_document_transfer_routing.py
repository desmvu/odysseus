"""Regression coverage for Nextcloud/MCP file-to-Library transfers."""

from pathlib import Path

from src.agent_loop import _is_mcp_document_transfer_request

SOURCE = Path("src/agent_loop.py")


def test_mcp_document_transfer_request_keeps_library_writer_available():
    assert _is_mcp_document_transfer_request(
        "Use Nextcloud MCP to import this file into a new document in my Library"
    )


def test_vietnamese_mcp_document_transfer_request_is_detected():
    assert _is_mcp_document_transfer_request(
        "Dùng Nextcloud để tạo tài liệu trong thư viện từ tệp này"
    )


def test_reading_an_mcp_document_does_not_imply_a_library_write():
    assert not _is_mcp_document_transfer_request(
        "Use Nextcloud MCP to read this document"
    )


def test_every_mcp_narrowing_path_preserves_document_creation():
    source = SOURCE.read_text(encoding="utf-8")

    # Explicit-server, follow-up, and matching-skill narrowing all happen
    # independently. Each must retain the local writer for a transfer.
    assert source.count('"create_document"') >= 3
    assert "_sk_local_toolsets = {t for t in _sk_toolsets if t in _known}" in source
    assert "schema_names = set(route_relevant_tools)" in source
    assert "else set())" not in source  # dead-code guard removed, not just moved


def test_skill_declared_local_toolsets_survive_mcp_narrowing():
    # A skill mixing a local writer with a remote server name in
    # requires_toolsets (e.g. ["create_document", "nextcloud"]) must keep
    # the local tool when the MCP branch replaces _relevant_tools, not only
    # for create_document specifically — any local toolset a skill declares.
    source = SOURCE.read_text(encoding="utf-8")

    assert "| _sk_local_toolsets" in source


def test_transfer_tools_survive_every_narrowing_reassignment():
    # Live bug: explicit-server narrowing correctly added create_document,
    # but a SECOND matched skill (operate-nextcloud-mcp-effectively, which
    # declares only requires_toolsets: [nextcloud], no create_document) ran
    # afterward in the skill loop and reassigned _relevant_tools from
    # scratch, dropping create_document again. Qwen3-14B then hallucinated
    # success via manage_memory instead of ever calling create_document.
    # _mcp_document_transfer_tools must be computed once, unconditionally,
    # and unioned into every reassignment site (explicit-server, follow-up,
    # and skill-triggered), not just the first two.
    source = SOURCE.read_text(encoding="utf-8")

    assert source.count("| _mcp_document_transfer_tools") == 3
    def_idx = source.index("_mcp_document_transfer_tools = (")
    first_use_idx = source.index("| _mcp_document_transfer_tools")
    assert def_idx < first_use_idx
