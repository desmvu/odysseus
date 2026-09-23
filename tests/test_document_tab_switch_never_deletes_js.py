"""Regression test: switching tabs must not delete the document being left.

A stale/empty editor DOM could make ``saveCurrentToMap()`` overwrite the cached
previous document with blank content. ``switchToDoc()`` then treated that stale
state as an empty draft and issued DELETE for the real previous document whenever
users created or opened another document. Tab switching is navigation, not an
explicit discard action; only close/discard flows may delete empty drafts.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_JS = (ROOT / "static/js/document.js").read_text()


def _function_body(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    # Find the function body's opening brace, not an object-destructuring
    # brace that may appear in the parameter list.
    cursor = src.index(") {", start) + 2
    while cursor < len(src):
        if src[cursor] == "{":
            depth += 1
        elif src[cursor] == "}":
            depth -= 1
            if depth == 0:
                return src[start : cursor + 1]
        cursor += 1
    raise AssertionError(f"unbalanced braces after {signature!r}")


def test_switching_tabs_never_issues_document_delete():
    switch_to_doc = _function_body(DOC_JS, "function switchToDoc(docId)")
    assert "api/document/${prevId}" not in switch_to_doc
    assert "method: 'DELETE'" not in switch_to_doc


def test_empty_draft_deletion_remains_limited_to_explicit_close_flow():
    detach_doc = _function_body(DOC_JS, "function _detachDocFromSession(docId")
    assert "method: 'DELETE'" in detach_doc


def test_missing_doc_entry_bails_out_before_the_delete_branch():
    """If docs.get(docId) already returned undefined (the Map lost this entry
    to a prior/concurrent call), hasContent/hasTitle would previously read as
    undefined (falsy) and silently fall through to the DELETE branch for a
    document _detachDocFromSession never actually inspected — confirmed live
    via a DELETE /api/document/<id> 200 OK on a document the user never
    touched (see BUG doc for this fix). A missing doc must return before any
    hasContent/hasTitle check, not rely on them coincidentally being falsy.
    """
    detach_doc = _function_body(DOC_JS, "function _detachDocFromSession(docId")
    guard_idx = detach_doc.index("if (!doc) {")
    delete_idx = detach_doc.index("method: 'DELETE'")
    assert guard_idx != -1
    assert guard_idx < delete_idx, "the !doc guard must appear before the delete branch"
    guard_body = detach_doc[guard_idx:detach_doc.index("}", guard_idx) + 1]
    assert "return;" in guard_body
    assert "DELETE" not in guard_body
