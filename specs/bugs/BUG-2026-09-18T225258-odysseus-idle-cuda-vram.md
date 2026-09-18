---
bug_id: BUG-2026-09-18T225258
status: investigating
severity: medium
priority: high
scope: cookbook-gpu-runtime
title: Odysseus retains a large CUDA allocation while no model server is visible
---

# BUG-2026-09-18T225258: Odysseus retains a large CUDA allocation while no model server is visible

## Problem

The host `nvidia-smi` shows the Odysseus Uvicorn process using 1854 MiB of RTX 4080 SUPER VRAM. No `llama-server`, vLLM, SGLang, Ollama, or diffusion-server process is visible. This reduces the VRAM available for a local model and is not merely a Cookbook display/preflight warning.

Expected behavior: the Odysseus web application must not retain substantial CUDA VRAM unless a user explicitly runs a GPU-backed Odysseus feature. A temporary feature allocation must be attributable and releasable.

Reproduction observed on 2026-09-18:
1. Start Odysseus with the NVIDIA Compose overlay.
2. Run `nvidia-smi` on the host.
3. Observe `/usr/local/bin/python3 /app/.local/bin/uvicorn app:app --host 0.0.0.0 --port 7000` using 1854 MiB as a compute process.
4. Confirm no separate local model-server process is visible.

Security impact: NONE. No security exploit path identified.

## Root Cause Analysis

### Reproduce

Confirmed from host GPU telemetry: PID 1337598 is the Odysseus Uvicorn process and owns 1854 MiB of compute VRAM. It has `/dev/nvidia0`, `/dev/nvidiactl`, and `/dev/nvidia-uvm` open, plus Torch, TorchVision, CUDA, cuDNN, NCCL, and ONNX Runtime CUDA libraries mapped.

### Isolate

The earlier Cookbook fix only excluded the application process from the *preflight warning*. It did not release or prevent the CUDA context. The active process has a real allocation. No standalone serve process accounts for it.

Potential allocation paths that can run inside Uvicorn include GPU-accelerated image masking/background removal (Torch/Transformers/rembg) and CUDA-capable ONNX embedding/runtime paths. Both can retain their provider/model cache in the long-lived application process.

### Hypothesize

1. **Most likely:** a previously invoked local image operation initialized a Torch or ONNX CUDA session in the Uvicorn process and retained its model/provider cache. Falsification: restart Odysseus, measure baseline VRAM before image operations, then invoke one candidate image operation at a time and remeasure.
2. **Possible:** local embedding initialization selects CUDA implicitly through ONNX Runtime. Falsification: on a fresh process, initialize the embedding path only and compare GPU memory.
3. **Less likely:** application startup itself initializes CUDA despite no GPU feature use. Falsification: measure immediately after a clean boot before any requests beyond readiness.

### Verify

Verified with a clean Docker restart. Uvicorn fell from 1854 MiB to 580 MiB, proving the earlier high allocation included a cached feature allocation. The 580 MiB baseline remained immediately after normal application startup.

Startup logs show local FastEmbed being instantiated four times for RAG and memory. The process maps ONNX Runtime's CUDA provider and holds the NVIDIA device files. `FastEmbedClient` left FastEmbed's `cuda` argument at its AUTO default, allowing its local embedding sessions to create the persistent CUDA context. The root cause is implicit AUTO GPU selection for embeddings in the long-lived web process.

Risk level: Medium. It can make otherwise fitting local models fail or perform poorly from VRAM pressure.

## TDD Fix Plan

1. **RED:** Add a focused test proving that embedding initialization requests an explicit CPU execution provider unless a GPU embedding mode is explicitly enabled.
   **GREEN:** Make the local embedding runtime provider explicit and CPU-first by default.
   **verify:** `./venv/bin/python -m pytest tests/test_embeddings*.py`

2. **RED:** Add tests proving that local image transformations do not silently select CUDA, and that an explicit GPU image operation exposes an attributable lifecycle/release path.
   **GREEN:** Make the device/provider selection explicit; keep optional GPU model ownership out of the web process or provide an unload action.
   **verify:** `./venv/bin/python -m pytest tests/test_gallery*.py`

3. **RED:** Add an integration-level check for a clean Odysseus process with no GPU-serving task: it must report no meaningful self-owned CUDA allocation after readiness.
   **GREEN:** Remove the confirmed implicit initializer or isolate it to a disposable worker process.
   **verify:** host `nvidia-smi` after Docker restart and app readiness.

**REFACTOR:** Keep Cookbook preflight reporting honest; do not hide a real app allocation with a UI-only exclusion.

## Acceptance Criteria

- [ ] Clean Odysseus startup does not consume meaningful compute VRAM without an explicitly requested GPU feature.
- [ ] Any intentionally GPU-backed feature declares the owning process and can release its VRAM.
- [ ] Cookbook reports app-owned VRAM accurately and does not misrepresent it as harmless.
- [ ] New targeted tests pass.
- [ ] Existing tests still pass.

## Resolution

**Fixed:** 2026-09-18
**Root cause confirmed:** FastEmbed AUTO device selection initialized persistent CUDA/ONNX Runtime state inside the Uvicorn web process during RAG and memory startup.
**Fix applied:** Passed `cuda=False` to every in-process `TextEmbedding` construction, including the one-off embedding-model download endpoint.
**Hardening added:** Regression tests assert CPU-only construction for both the long-lived embedding client and the download route; a two-match sweep is recorded in `specs/verifications/generalize-sweep-BUG-2026-09-18T225258-idle-cuda-vram.json`.
**Behavioral evidence:** After a clean Docker rebuild, `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits` lists no Odysseus Python compute process. Before the fix it listed Uvicorn at 1854 MiB; after an intermediate clean boot it listed Uvicorn at 580 MiB.
**Targeted evidence:** `./venv/bin/python -m pytest tests/test_embeddings.py tests/test_embedding_cache_confinement.py -q` — 7 passed.
**Full-suite note:** Full `./venv/bin/python -m pytest` remains red with 21 unrelated pre-existing failures in agent routing, MCP reconnect/timeout, GPU Compose, settings JS, and token-cache tests. The existing generalize-sweep verification script is also absent, so that artifact was recorded manually.
**Commit:** `fix(embeddings): keep local FastEmbed off the serving GPU`
