"""Regression: the agent tool-RAG domain classifier had no `finance` domain,
so plain financial statements ("spent 500k on X", "my savings account",
"invest in gold") matched no domain bucket, were flagged low_signal, and the
agent silently reused whatever MCP tools were relevant to the PREVIOUS,
unrelated turn instead of re-running tool retrieval — observed: an investment
log landed in manage_notes with the Budget MCP never even offered, because the
prior turn had only Gold MCP tools loaded.

Root cause: `_classify_agent_request` in src/agent_loop.py builds `domains`
from regex buckets with no finance bucket; `low_signal = not continuation and
not domains` then skipped retrieval for financial statements.

The classifier is deterministic string matching (no embeddings / no DB), so it
can be exercised directly, same as test_tool_rag_contacts_domain.py.
"""

from src.agent_loop import _classify_agent_request


def _classify(text):
    return _classify_agent_request([{"role": "user", "content": text}], text)


def test_spending_statements_get_finance_domain():
    prompts = [
        "spent 500k on a new laptop",
        "I earned income from freelancing this month",
        "track my expenses for groceries",
        "set a budget for next month",
        "paid my rent yesterday",
    ]
    for p in prompts:
        intent = _classify(p)
        assert "finance" in intent["domains"], f"expected finance domain for: {p!r}"
        assert intent["low_signal"] is False, f"must not be low_signal: {p!r}"


def test_investing_and_savings_statements_get_finance_domain():
    for p in ("invest in gold", "my savings account is growing", "what's my net worth",
              "I made a deposit today", "withdraw money from the bank"):
        intent = _classify(p)
        assert "finance" in intent["domains"], f"expected finance domain for: {p!r}"


def test_bare_currency_amount_gets_finance_domain():
    """The currency-amount pattern alone (no vocabulary word) must also match —
    `has()` is an OR across its pattern args, not an AND."""
    intent = _classify("500000 vnd")
    assert "finance" in intent["domains"]


def test_non_finance_requests_do_not_match_finance_domain():
    """Guard against over-triggering: ordinary prompts must not be flagged finance."""
    assert "finance" not in _classify("what is the capital of France")["domains"]
    assert "finance" not in _classify("reply to the latest email in my inbox")["domains"]
    assert "finance" not in _classify("generate an image of a sunset")["domains"]
    assert "finance" not in _classify("what's the weather today")["domains"]
