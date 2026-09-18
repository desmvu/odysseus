---
bug_id: BUG-2026-09-18T033314
status: resolved
severity: high
scope: calendar-tasks-notes
title: No default-calendar preference, and Quick Add could fail silently
---

# BUG-2026-09-18T033314: No default-calendar preference, and Quick Add could fail silently

## Problem

**Actual behavior (two related issues, same root area):**
1. **No default calendar preference / wrong implicit target:** creating an event without explicitly naming a calendar (`calendar_href` absent) picked whatever the CalDAV server happened to list first. CalDAV collection order is server-defined and commonly returned a read-only collection (e.g. "Contact birthdays") before any real writable calendar — so implicit event creation could silently fail or land in the wrong place, and the user had no way to set which calendar should be the default.
2. **Quick Add silent failure:** Quick Add's model-parse route could fail after already building the event object, and the UI showed nothing — as if the request had never happened, with no error surfaced to the user.

**Expected behavior:** The user can choose a default calendar in Settings, implicit event creation respects that choice (falling back sensibly to a calendar literally named "Personal", then any owned calendar, then a lazily created default), specifying a calendar by name in a Quick Add prompt should route to that exact calendar, and any Quick Add failure should be visible in the UI rather than silent.

**How to reproduce (pre-fix):**
1. Have more than one CalDAV calendar, including a read-only one like Contact birthdays.
2. Create an event without specifying a calendar; observe it may land in the read-only/wrong collection.
3. Trigger a Quick Add parse failure (e.g. malformed model output) and observe the UI shows nothing.

**Security impact:** NONE — data-correctness/UX bug, not an auth or exposure issue. (`_default_calendar_pref` does have an owner-isolation nuance noted below, itself a defensive fix within this same change.)

## Root Cause Analysis

- `_ensure_default_calendar()` (the prior implicit-target resolver) had no preference ordering — it used server-returned collection order, which is not guaranteed to put writable/personal calendars first.
- There was no per-user setting to declare a default calendar at all, so users with multiple calendars had no way to control implicit-target behavior.
- Quick Add's async event-creation path used a `.then()` chain whose rejection was not observed by any handler — a failure after the event object was already built simply vanished, leaving the UI showing nothing and the user unable to tell whether the request had been processed.
- A related correctness nuance found and fixed in the same change: `_default_calendar_pref(owner)` needed to correctly map the auth-disabled fallback owner (`FALLBACK_OWNER`) to the single-user prefs slot (`prefs_user = None`), otherwise it could read/leak another user's preference in an auth-disabled deployment.
- Risk level: Medium (silent failure hides a real problem from the user; wrong implicit calendar target can misfile or fail to create events).

## TDD Fix Plan

1. **RED**: A test asserting that with no `calendar_href` given and no user preference set, `_preferred_calendar()` returns a calendar named "Personal" over other calendars when one exists, and falls back to any owned calendar, then a lazily created default, when it doesn't.
   **GREEN**: `routes/calendar_routes.py` / `src/tools/calendar.py` — added `_preferred_calendar(db, owner)`: orders by (1) the user's `default_calendar_id` preference, (2) a calendar named "Personal" (case-insensitive), (3) any owned calendar, (4) `_ensure_default_calendar()` as the lazy-creation fallback. Replaced the direct `_ensure_default_calendar()` call at the implicit-target call site with `_preferred_calendar()`.
2. **RED**: A test asserting that `_default_calendar_pref()` reads the correct prefs slot for the auth-disabled fallback owner, not a different/incorrect user's preference.
   **GREEN**: `_default_calendar_pref(owner)` maps `owner in (None, FALLBACK_OWNER)` to `prefs_user = None` before calling `_load_for_user`.
3. **RED**: A test asserting that Quick Add's `quick_parse` route only ever echoes back a calendar name the caller actually owns (not an arbitrary/wrong-owner name), and that naming a specific calendar in the prompt (added `"calendar"` field to the model's JSON-parse schema) routes the created event to that exact calendar.
   **GREEN**: `quick_parse` now looks up the caller's own calendar names and only echoes one the caller owns; the model-parse prompt gained a `"calendar": "<exact calendar name from the list below, or empty>"` field, populated from the caller's own calendar list, so an explicit calendar name in the Quick Add text is honored.
4. **RED**: A test asserting that a Quick Add failure surfaces an inline error in the UI instead of vanishing silently.
   **GREEN**: `static/js/calendar.js` — Quick Add's `_createEvent` converted to `async`/`await` so a rejection is caught and shown inline, instead of being swallowed by a dangling `.then()` chain with no `.catch()`.
5. **RED/GREEN (supporting UI)**: added a Settings → Integrations control to choose the default calendar, shown only when the user has more than one calendar (`static/index.html`, `static/js/settings.js`).

**REFACTOR**: None beyond the above; all changes are additive to the existing calendar-resolution and Quick Add flow.

## Acceptance Criteria

- [x] Implicit event creation (no calendar named) respects: user preference → "Personal" calendar → any owned calendar → lazily created default, in that order.
- [x] `_default_calendar_pref` does not leak another user's preference for the auth-disabled fallback owner.
- [x] Quick Add can route to an explicitly named calendar from the prompt text.
- [x] `quick_parse` never echoes a calendar name the caller does not own.
- [x] A Quick Add failure is shown inline in the UI, not silent.
- [x] Settings exposes a default-calendar picker when more than one calendar exists.
- [x] New tests added: `tests/test_calendar_preferred_calendar.py`, `tests/test_calendar_quick_parse.py` (preference precedence, stale-pref fallback, owner isolation, quick-parse JSON recovery/ownership checks).

## Resolution

**Fix applied (commit `aedc3984`, "fix(calendar): fix Quick Add silent failure, default calendar pref"):**
- `routes/calendar_routes.py`, `src/tools/calendar.py`: added `_preferred_calendar()` and `_default_calendar_pref()` with the ordering and owner-isolation described above; `quick_parse` echoes only owned calendar names; added `"calendar"` field to the Quick Add model-parse JSON schema.
- `static/js/calendar.js`: Quick Add surfaces failures inline; `_createEvent` uses async/await.
- `static/index.html`, `static/js/settings.js`: new Settings → Integrations default-calendar control (shown only with >1 calendar).
- `tests/test_calendar_preferred_calendar.py`, `tests/test_calendar_quick_parse.py`: new coverage.

**Status:** Resolved and merged (commit `aedc3984d77902faa0b816c4247c83df8411f73c`).
