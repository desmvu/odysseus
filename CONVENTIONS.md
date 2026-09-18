# Odysseus Conventions

## Purpose

Odysseus is a self-hosted AI workspace.

This document defines shared rules for every coding agent.

## Commands

| Action | Command |
|---|---|
| Run | `docker compose up -d --build` |
| Test | `./venv/bin/python -m pytest` |
| Fast test | `./venv/bin/python -m pytest --fast` |
| Syntax | `./venv/bin/python -m compileall -q app.py core routes src services scripts tests` |
| Frontend syntax | `node --check static/js/<changed-file>.js` |
| Preflight | `./venv/bin/python -m pytest && ./venv/bin/python -m compileall -q app.py core routes src services scripts tests` |
| Compose validation | `docker compose config` |

ALWAYS use `./venv/bin/python` for Python tests.

DO NOT use system Python for project tests.

DO NOT declare frontend work verified without a browser screenshot.

## Always Green / Shift Left

Run the relevant mechanical checks before handoff.

Run Preflight before committing or opening a pull request.

Keep Preflight and CI green before starting unrelated work.

A failure costs least during development and most after release.

DO NOT dismiss a reproducible gate failure.

## Discovered Defects

Fix a reproducible defect before continuing when it blocks a required gate.

Log a defect when fixing it requires a separate scoped change.

Use a separate Conventional Commit for an independently discovered defect.

DO NOT use scope reduction to waive an Always Green requirement.

| Banned phrase | Required action |
|---|---|
| "pre-existing" | Reproduce, fix, or log the defect. |
| "unrelated to this session" | Reproduce, fix, or log the defect. |
| "not introduced by my changes" | Reproduce, fix, or log the defect. |
| "out of scope" | Reproduce, fix, or log the defect. |

## Repository Rules

Target pull requests to `dev`.

Use Conventional Commits: `feat(scope): summary` or `fix(scope): summary`.

Read `CLAUDE.md` before changing code.

Keep routes thin and delegate business logic to `src/` or `services/`.

Use `owner_filter` for data-owning route queries.

Use `require_user`, `require_privilege`, or `require_authenticated_request` for route access control.

Add owner-scope tests for data-owning endpoints.

Use constants from `src/constants.py` for persisted paths.

DO NOT read `ODYSSEUS_DATA_DIR` outside `src/constants.py`.

DO NOT hardcode `/app`, relative data paths, or `http://localhost:7000`.

Use `internal_api_base()` for internal Odysseus URLs.

Read `static/js/MODULE_SUMMARY.md` before adding or tracing frontend modules.

Use existing CSS variables and shared UI classes.

DO NOT add Unicode emoji to UI or code.

## Defensive Code

Apply defensive controls where a risk exists.

- Rate limit public and expensive operations.
- Retry transient external failures with bounded attempts.
- Use circuit breakers for repeatedly failing external dependencies.
- Set explicit timeouts for network and subprocess operations.
- Degrade gracefully when optional integrations fail.

DO NOT retry authentication, validation, or permission failures.

DO NOT hide degraded behavior from users or logs.

## Testing

Write regression tests for every bug fix.

Test behavior through public interfaces.

Keep tests fast, isolated, repeatable, and deterministic.

Run focused tests during development.

Run the full suite before handoff when practical.

## Git and Scope

Keep changes limited to the requested outcome.

DO NOT reformat or reorganize unrelated files.

DO NOT force-push, reset hard, clean, or delete branches without explicit approval.

DO NOT commit secrets, `.env` values, or access tokens.

## Planning Output

Write new planning artifacts under `specs/`.

Use `specs/product/` for product scope and vision.

Use `specs/tech-architecture/` for architecture, security, test, design, refactor, and impact records.

Use `specs/epics/` for implementation plans.

Use `specs/verifications/` for verification evidence.

Use `specs/bugs/registry.yaml` for tracked defects.
