"""Quick-add parsing contract: tolerate imperfect model output, trust nothing.

The parser must recover a JSON object wrapped in prose and may only echo a
calendar name the caller actually owns, since the client preselects it.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from tests.helpers.import_state import clear_fake_database_modules

clear_fake_database_modules()

import core.database as cdb  # noqa: E402
import routes.calendar_routes as calendar_routes  # noqa: E402
import src.endpoint_resolver as endpoint_resolver  # noqa: E402
import src.llm_core as llm_core  # noqa: E402
from core.database import CalendarCal  # noqa: E402

OWNER = "alice"


class _Request:
    def __init__(self, payload):
        self._payload = payload
        self.state = SimpleNamespace(current_user=OWNER)

    async def json(self):
        return self._payload


@pytest.fixture
def quick_parse(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'calendar.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    for index, name in enumerate(["Personal", "Work"]):
        session.add(CalendarCal(id=f"cal-{index}", owner=OWNER, name=name, source="caldav"))
    session.commit()
    session.close()

    monkeypatch.setattr(calendar_routes, "SessionLocal", factory)
    monkeypatch.setattr(
        endpoint_resolver,
        "resolve_endpoint",
        lambda *a, **k: ("http://model.test/v1/chat/completions", "test-model", {}),
    )
    router = calendar_routes.setup_calendar_routes()
    endpoint = next(
        route.endpoint for route in router.routes if route.path.endswith("/quick-parse")
    )
    try:
        yield endpoint
    finally:
        engine.dispose()


def _reply(monkeypatch, *responses):
    """Serve one canned model response per call, for the repair-retry path."""
    remaining = list(responses)
    calls = []

    async def fake_llm_call_async(**kwargs):
        calls.append(kwargs)
        return remaining.pop(0)

    monkeypatch.setattr(llm_core, "llm_call_async", fake_llm_call_async)
    return calls


def _event_json(**overrides):
    payload = {
        "summary": "Standup",
        "dtstart": "2126-02-03T09:00:00",
        "dtend": "2126-02-03T09:30:00",
        "all_day": False,
        "location": "",
        "description": "",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return json.dumps(payload)


def _parse(quick_parse, text="standup tomorrow 9am"):
    return asyncio.run(quick_parse(_Request({"text": text, "tz_offset": 0})))


def test_echoes_a_calendar_the_caller_owns(quick_parse, monkeypatch):
    _reply(monkeypatch, _event_json(calendar="Work"))

    result = _parse(quick_parse)

    assert result["ok"] is True
    assert result["event"]["calendar"] == "Work"


def test_drops_a_calendar_the_caller_does_not_own(quick_parse, monkeypatch):
    _reply(monkeypatch, _event_json(calendar="Someone else's calendar"))

    assert _parse(quick_parse)["event"]["calendar"] == ""


def test_recovers_json_wrapped_in_prose(quick_parse, monkeypatch):
    _reply(monkeypatch, f"Sure! {{not json}} here you go:\n{_event_json()}\nHope that helps.")

    result = _parse(quick_parse)

    assert result["ok"] is True
    assert result["event"]["summary"] == "Standup"


def test_retries_once_when_the_first_response_has_no_json(quick_parse, monkeypatch):
    calls = _reply(monkeypatch, "I think you want an event.", _event_json())

    result = _parse(quick_parse)

    assert result["ok"] is True
    assert len(calls) == 2


def test_reports_failure_when_the_retry_also_fails(quick_parse, monkeypatch):
    _reply(monkeypatch, "no json here", "still no json")

    result = _parse(quick_parse)

    assert result["ok"] is False
    assert result["error"] == "Could not parse calendar details"
