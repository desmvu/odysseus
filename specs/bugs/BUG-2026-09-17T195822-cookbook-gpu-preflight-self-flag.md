---
bug_id: BUG-2026-09-17T195822
status: resolved
severity: medium
scope: cookbook
title: GPU-preflight falsely warns of existing VRAM load from Odysseus's own process
---

# BUG-2026-09-17T195822: GPU-preflight falsely warns of existing VRAM load from Odysseus's own process

## Problem

**Actual behavior:** Cookbook's GPU-preflight check (shown before launching a model serve) persistently warned about existing GPU memory usage attributed to a `python3` process, even with no other model running — the warning never cleared.

**Expected behavior:** Preflight should only warn about genuinely competing GPU load from other processes, not Odysseus's own baseline overhead.

**Security impact:** NONE.

## Root Cause Analysis

- `shutil.which("llama-server")` (used by `routes/shell_routes.py` and `routes/cookbook_routes.py`) could not find the prebuilt binary because the Dockerfile built `llama-server` at `/app/llama.cpp/build/bin/llama-server` but never added that directory to `PATH`.
- Without a discoverable binary, Cookbook's dependency check fell back to an in-process `import llama_cpp` probe to detect GPU capability. That import pins a CUDA context in the main Odysseus app process for the rest of its lifetime.
- The pinned context shows up in `nvidia-smi`-style process listings as VRAM used by `python3` (Odysseus's own PID), which the GPU-preflight check then reported as "existing load" competing for VRAM — a false positive that could never be cleared without restarting the whole app.
- A missing binary on `PATH` also meant a serve launch fell back to the ~15-20 minute from-source build bootstrap instead of using the binary already present in the image.
- Risk level: Low (cosmetic/confusing warning + slower serve launches; no data loss or crash).

## TDD Fix Plan

1. **RED**: Reproduce by building the image without the `PATH` addition and confirming `shutil.which("llama-server")` returns `None`, then launching a serve to observe the in-process `llama_cpp` import and a persistent self-attributed GPU-preflight warning.
   **GREEN**: `Dockerfile` — added `ENV PATH="/app/llama.cpp/build/bin:${PATH}"` immediately after the `llama.cpp` build step, so the prebuilt binary is always discoverable.
2. **RED**: With the binary discoverable, confirm the preflight still incorrectly flags Odysseus's own process if it retains any GPU handle.
   **GREEN**: `routes/cookbook_routes.py` — tag the current process's GPU-process entry with `"is_self": True` when `pid == os.getpid()` (local target only; a remote host's PID namespace is unrelated to `os.getpid()`), so preflight can exclude Odysseus's own baseline usage from the "existing load" calculation.
   **verify**: launch Cookbook GPU-preflight against a clean GPU (no other models running) and confirm no self-attributed warning appears.

**REFACTOR**: None needed.

## Acceptance Criteria

- [x] `llama-server` binary is discoverable via `PATH` inside the container.
- [x] Cookbook prefers the prebuilt binary over the from-source build bootstrap when present.
- [x] GPU-preflight no longer attributes Odysseus's own process VRAM usage as competing external load.

## Resolution

**Root cause:** missing `PATH` entry for the prebuilt `llama-server` binary caused a fallback to an in-process GPU probe that permanently pinned a CUDA context in the main app process, which GPU-preflight then misreported as external load.

**Fix applied:** `Dockerfile` PATH addition (commit `e6069c48`, part of a combined commit "llama-server PATH fix, GPU-preflight self-process filter, text-size zoom scaling fixes"); `routes/cookbook_routes.py` self-process tagging in the GPU-process listing logic.

**Status:** Resolved and merged (commit `e6069c48481c94eba939ab8369ea38a27e2a99f9`).
