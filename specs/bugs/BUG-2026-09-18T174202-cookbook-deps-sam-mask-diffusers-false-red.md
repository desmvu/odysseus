---
bug_id: BUG-2026-09-18T174202
status: resolved
severity: low
priority: medium
scope: cookbook-dependencies
title: Dependencies tab shows sam_mask/krea_diffusers as not-installed when only their dist-info metadata is undiscoverable
---

# BUG-2026-09-18T174202: sam_mask / diffusers show red Install despite being installed

## Problem

User reported: "in Cookbook settings, Dependencies tab, sam_mask and diffusers keep having red install button, although i have installed them."

## Root Cause

`routes/shell_routes.py:378` `_package_probe_script()` generates a Python probe run in the target environment (local or remote via SSH). Its `probe(n)` function checks two independent signals per dependency: `dist_status()` (via `importlib.metadata.version()`, needs discoverable dist-info) and `mod_status()` (via `importlib.util.find_spec()`, works off actual importability regardless of dist-info). `_package_installed_from_probe()` (`routes/shell_routes.py:150`) is written to accept EITHER signal as sufficient for `torch`/`transformers` — but the probe script only ever populated the `mod_status()` fallback for `torch` when checking `diffusers` specifically (`if n == 'diffusers': mods['torch'] = mod_status('torch')`). `sam_mask` (needs `transformers` + `torch`) and `krea_diffusers` (needs `diffusers` + `torch`) never got that same module-existence fallback, even though `_package_installed_from_probe` reads `modules.get('torch')`/`modules.get('transformers')` for them too. Any install where `importlib.metadata` can't find dist-info (conda envs, editable/`-e` installs, some vendored installs) would correctly recover via the module fallback for `diffusers` alone, while `sam_mask`/`krea_diffusers` fell through to a false "not installed" red state — matching the user's exact report of both being wrong together.

## First fix (partial — fixed diffusers, not sam_mask)

`routes/shell_routes.py` `_package_probe_script()`: extended the module-existence fallback so `krea_diffusers` gets `mods['torch']` (same as `diffusers`), and `sam_mask` gets both `mods['torch']` and `mods['transformers']`. User confirmed `diffusers` turned green after a pip install and this deploy, but reported `sam_mask` was **still red**.

## Second pass — the actual sam_mask bug

Live-verified as the real app user (`docker compose exec -T -u odysseus odysseus python3 -c '...'`, matching `HOME=/app` — an earlier check via plain `docker compose exec` defaulted to root/`HOME=/root` and gave false negatives) that `torch`, `transformers`, and `diffusers` were ALL correctly importable with discoverable dist-info: `torch find_spec=True version=2.13.0`, `transformers find_spec=True version=5.15.0`, `diffusers find_spec=True version=0.40.0`. So the first fix's premise (undiscoverable dist-info) didn't apply here — the real bug was elsewhere.

Root cause: `_package_probe_script()`/`_package_installed_from_probe()` (the code the first fix touched) is **only ever invoked for packages with `"target": "remote"`** (`routes/shell_routes.py` ~line 1455, `if host and remote_names: py = _package_probe_script(remote_names)`, gated on `pkg.get('target') == 'remote'`). `sam_mask`'s catalog entry (~line 1387) has `"target": "local"` — it never goes through that function at all when checked without an SSH host, so the first fix was dead code for its actual path. `diffusers`/`transformers` have `target: "remote"`, which is why that fix worked for diffusers.

The real local-target check (`routes/shell_routes.py` ~line 1633, the generic `else:` branch of the `for pkg in packages:` loop) does `_import_optional_dependency_for_status(pkg["name"])` → `importlib.import_module(pkg["name"])`. This works for packages whose catalog `name` is a real importable module (`playwright`, `rembg`, `realesrgan`) but `"sam_mask"` is a **synthetic feature-bundle name** — there is no Python module literally called `sam_mask`; it represents torch+transformers together (per its catalog `pip` field: `"torch torchvision transformers accelerate pillow"`). `import_module("sam_mask")` always raises `ImportError`, so this branch reported not-installed unconditionally, regardless of whether torch/transformers were actually present.

## Fix

1. `routes/shell_routes.py` `_package_probe_script()`: extended module-existence fallback for `krea_diffusers`/`sam_mask` (kept; harmless, correct for the SSH/remote path these packages can also take).
2. `routes/shell_routes.py`, the local-target package loop: added an explicit `elif pkg["name"] == "sam_mask":` branch before the generic `else:` fallback — checks `importlib.import_module("torch")` + `importlib.import_module("transformers")` and their `importlib_metadata.version()` directly (mirroring the SSH-path special-casing already used for diffusers/krea_diffusers/sam_mask in `_package_installed_from_probe`), instead of trying to import a module named `sam_mask` that doesn't exist.

## Verification

- `./venv/bin/python -m compileall -q routes/shell_routes.py` — passed.
- `./venv/bin/python -m pytest tests/test_cookbook_cpu_only_serve.py -q` — 15 passed, no regression.
- Rebuilt and deployed (`docker compose up -d --build odysseus`); container healthy.
- Live confirmation still needed: user should reopen Cookbook → Settings → Dependencies and confirm `sam_mask` now reports installed/green.
