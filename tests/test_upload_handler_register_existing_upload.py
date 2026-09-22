"""Regression: PDF email attachments opened as Documents via the
attachment-as-doc route (routes/email_routes.py) were written to disk with
`shutil.copyfile()` but never indexed into uploads.json. `resolve_upload()`/
`reserve_upload()` (src/upload_handler.py) only ever consult the uploads.json
index — never a filesystem scan — so the file was genuinely present on disk
but permanently reported "Source PDF not found" on every later read,
including the page-render requests the Document pane's PDF viewer relies on.

Fix: `UploadHandler.register_existing_upload()` indexes a file the server
already wrote to disk by another path, mirroring `save_upload()`'s metadata
shape, guarded by `validate_upload_id()` and `_inside_upload_dir()`.
"""

import json
import os
from pathlib import Path

from src.upload_handler import UploadHandler


def _make_handler(tmp_path: Path) -> UploadHandler:
    base = tmp_path / "base"
    upload = tmp_path / "uploads"
    base.mkdir()
    upload.mkdir()
    return UploadHandler(base_dir=str(base), upload_dir=str(upload))


def _db_path(handler: UploadHandler) -> str:
    return os.path.join(handler.upload_dir, "uploads.json")


def _write_upload_file(handler: UploadHandler, file_id: str, content: bytes = b"%PDF-1.4 fake pdf bytes") -> str:
    """Mirrors the attachment-as-doc flow: bytes copied directly to a dated
    dir inside upload_dir, with no index entry created by the write itself."""
    upload_day = Path(handler.upload_dir) / "2026" / "06" / "09"
    upload_day.mkdir(parents=True, exist_ok=True)
    path = upload_day / file_id
    path.write_bytes(content)
    return str(path)


def test_register_existing_upload_makes_file_resolvable():
    """Reproduces the bug directly: a file written to disk by shutil.copyfile
    (simulated here) is unresolvable until register_existing_upload indexes
    it, then becomes resolvable exactly like a save_upload()-created file."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        handler = _make_handler(Path(td))
        file_id = "a" * 32 + ".pdf"
        path = _write_upload_file(handler, file_id)

        # Before registration: file exists on disk but is not resolvable —
        # this is the exact "Source PDF not found" bug being pinned.
        assert handler.resolve_upload(file_id, owner="alice") is None

        metadata = handler.register_existing_upload(
            file_id, path, owner="alice", mime="application/pdf", original_name="attachment.pdf",
        )

        assert metadata is not None
        assert metadata["id"] == file_id
        assert metadata["mime"] == "application/pdf"
        assert metadata["owner"] == "alice"

        resolved = handler.resolve_upload(file_id, owner="alice")
        assert resolved is not None
        assert resolved["id"] == file_id
        assert resolved["path"] == path


def test_register_existing_upload_writes_index_entry_matching_save_upload_shape():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        handler = _make_handler(Path(td))
        file_id = "b" * 32 + ".pdf"
        path = _write_upload_file(handler, file_id)

        handler.register_existing_upload(
            file_id, path, owner="bob", mime="application/pdf", original_name="report.pdf",
        )

        index = json.loads(Path(_db_path(handler)).read_text(encoding="utf-8"))
        entries = list(index.values())
        assert len(entries) == 1
        entry = entries[0]
        for key in ("id", "path", "mime", "size", "name", "hash", "checksum_sha256",
                    "original_name", "uploaded_at", "last_accessed", "owner"):
            assert key in entry, f"missing key {key!r} in indexed metadata"
        assert entry["id"] == file_id
        assert entry["path"] == path
        assert entry["original_name"] == "report.pdf"


def test_register_existing_upload_rejects_path_outside_upload_dir(tmp_path):
    handler = _make_handler(tmp_path)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"not in upload dir")

    result = handler.register_existing_upload(
        "c" * 32 + ".pdf", str(outside), owner="carol", mime="application/pdf",
    )

    assert result is None
    assert handler.resolve_upload("c" * 32 + ".pdf", owner="carol") is None


def test_register_existing_upload_rejects_missing_file(tmp_path):
    handler = _make_handler(tmp_path)
    missing_path = Path(handler.upload_dir) / "2026" / "06" / "09" / ("d" * 32 + ".pdf")

    result = handler.register_existing_upload(
        "d" * 32 + ".pdf", str(missing_path), owner="dave", mime="application/pdf",
    )

    assert result is None


def test_register_existing_upload_rejects_invalid_upload_id(tmp_path):
    handler = _make_handler(tmp_path)
    path = _write_upload_file(handler, "not-a-valid-id")

    result = handler.register_existing_upload(
        "../../etc/passwd", path, owner="eve", mime="application/pdf",
    )

    assert result is None
