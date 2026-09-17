"""Implicit event targets must never be the first CalDAV collection.

CalDAV returns collections in server order, which commonly puts a read-only
``Contact birthdays`` calendar first. Events created without an explicit
``calendar_href`` follow the user's Default Calendar preference, then a
calendar named ``Personal``.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from tests.helpers.import_state import clear_fake_database_modules

clear_fake_database_modules()

import core.database as cdb  # noqa: E402
import routes.calendar_routes as calendar_routes  # noqa: E402
import routes.prefs_routes as prefs_routes  # noqa: E402
from core.database import CalendarCal  # noqa: E402

OWNER = "alice"


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'calendar.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(calendar_routes, "SessionLocal", factory)
    monkeypatch.setattr(prefs_routes, "PREFS_FILE", str(tmp_path / "prefs.json"))
    session = factory()
    for index, name in enumerate(["Contact birthdays", "Personal", "Work"]):
        session.add(CalendarCal(id=f"caldav-{index}", owner=OWNER, name=name, source="caldav"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _write_pref(tmp_path, owner, calendar_id):
    (tmp_path / "prefs.json").write_text(
        json.dumps({"_users": {owner: {"default_calendar_id": calendar_id}}}),
        encoding="utf-8",
    )


def test_prefers_personal_over_the_first_caldav_collection(db):
    assert calendar_routes._preferred_calendar(db, OWNER).name == "Personal"


def test_default_calendar_preference_wins(db, tmp_path):
    _write_pref(tmp_path, OWNER, "caldav-2")

    assert calendar_routes._preferred_calendar(db, OWNER).name == "Work"


def test_stale_preference_falls_back_to_personal(db, tmp_path):
    _write_pref(tmp_path, OWNER, "caldav-deleted")

    assert calendar_routes._preferred_calendar(db, OWNER).name == "Personal"


def test_another_users_preference_is_not_applied(db, tmp_path):
    _write_pref(tmp_path, "bob", "caldav-2")

    assert calendar_routes._preferred_calendar(db, OWNER).name == "Personal"


def test_owner_without_calendars_gets_a_created_default(db):
    assert calendar_routes._preferred_calendar(db, "carol").name == "Personal"
