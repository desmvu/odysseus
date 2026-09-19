---
bug_id: BUG-2026-09-20T000000
status: resolved
severity: high
priority: high
scope: host-infra
title: Qwen3-14B (llama-server) silently falls back to CPU after host reboot -- stale NVIDIA CDI spec, not an Odysseus regression
---

# BUG-2026-09-20T000000: Qwen3-14B falls back to CPU/RAM after host reboot

## Problem

User reported that after the `41c87b54` Dockerfile/docker-compose.yml rework (minimal CUDA apt
package set + GPU compose overlay dedup), the previously-GPU-served Qwen3-14B Q5_K_M model was now
"using CPU and RAM" instead of the GPU. Suspicion fell on that commit since it was the most recent
change to touch CUDA/GPU-adjacent files.

Expected: `llama-server -ngl 99 ...` loads all layers onto the RTX 4080 Super's VRAM.
Actual: `llama-server` logs `ggml_cuda_init: failed to initialize CUDA: unknown error`, silently
warns `no usable GPU found, --gpu-layers option will be ignored`, and continues running the full
14B model on CPU -- consuming ~9:55 CPU-minutes at 263% CPU before eventually dying (zombie
process), which is consistent with heavy CPU-bound inference rather than GPU offload.

## Root Cause Analysis

**Security impact: NONE** -- purely a host device-permission staleness issue, no exploit path.

1. **Reproduce:** Killed the zombie `llama-server` (pid 314) and relaunched the exact saved preset
   command manually inside the container. Reproduced the same `ggml_cuda_init: ... unknown error`
   consistently on every retry (not transient) -- 8 threads, no GPU offload, listening on CPU only.

2. **Isolate -- ruled out Odysseus entirely:** Spun up a fresh, unrelated `nvidia/cuda:13.0.0-devel`
   and `nvidia/cuda:12.4.1-devel` container (`docker run --rm --gpus all ...`, zero Odysseus code
   involved) and ran a minimal `cudaGetDeviceCount()` C program. Both failed identically:
   `cudaGetDeviceCount: err=999 (unknown error), count=0` -- while `nvidia-smi -L` inside the same
   containers correctly listed the RTX 4080 SUPER. This proves the failure is host/Docker-runtime
   wide, not specific to CUDA 13.4 (which the reworked Dockerfile pulls) vs 12.4 (the old pinned
   wheel index), and not specific to any Odysseus image content.

3. **Hypothesize and narrow:** `nvidia-smi` (NVML) working while `cudaGetDeviceCount` (full CUDA
   driver API) fails is the classic signature of a container device-access gap, not a driver/
   toolkit/GPU hardware problem. Bisected which `docker run` flag fixes it:
   - `--privileged` alone: **fixes it** (err=0, count=1, GPU correctly identified).
   - `--security-opt seccomp=unconfined` alone: no effect (still err=999).
   - `--cap-add SYS_ADMIN` alone: no effect.
   - `--cap-add ALL` alone: no effect.
   - `--security-opt apparmor=unconfined` alone: no effect.
   - `--device-cgroup-rule='c *:* rmw'` alone (device cgroup access only, no capability/seccomp/
     apparmor change): **fixes it** (err=0, count=1).

   This isolates the cause to the container's **device cgroup rules** specifically, not capabilities,
   seccomp, or apparmor.

4. **Verify:** Host's `/etc/cdi/nvidia.yaml` (the NVIDIA Container Device Interface spec that
   `nvidia-container-toolkit` uses to compute each container's device cgroup allow-list) has mtime
   **17 Sep 17:16** -- three days stale. The host rebooted today (`journalctl -k`: NVIDIA open-kernel
   driver 615.71.09 loaded at **20 Sep 00:22**), which reassigned kernel device major numbers on
   reload. The stale CDI spec lists `/dev/nvidia-uvm` at **major 235**, but the currently running
   driver instance created it at **major 234** (confirmed via `ls -la /dev/nvidia*` inside the
   Odysseus container, mtime `19 Sep 18:04`). Docker grants the container access to major 235 (no
   longer valid), so any open of the real `/dev/nvidia-uvm` (major 234) is silently denied at the
   cgroup level -- `nvidia-smi`/NVML doesn't need `/dev/nvidia-uvm` at all, only `/dev/nvidiactl` +
   `/dev/nvidia0` (whose major numbers, 195, happened not to change), so NVML keeps working while
   real CUDA context creation (which does need UVM) fails with the generic `cudaErrorUnknown` (999).

   Root cause fully confirmed, independent of any repo code: the CDI spec just needs regenerating
   against the post-reboot device numbers.

## Fix

No code change in this repository -- this is a host machine-state issue outside the Odysseus repo
and outside Docker's control. Fix is a one-time host command (needs the user's own sudo password,
which this session does not have):

```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

To prevent recurrence after every future host reboot, consider one of:
- A systemd unit/oneshot that runs `nvidia-ctk cdi generate` after `nvidia-persistenced.service`
  or the driver module load, before `docker.service` starts any GPU containers.
- Simply re-running the command by hand after each host reboot, before relying on GPU containers.

`41c87b54` (the Dockerfile/docker-compose.yml CUDA rework under investigation) is exonerated: the
same host-wide `cudaErrorUnknown` reproduces in completely stock, unrelated `nvidia/cuda` images
with both CUDA 12.4 and 13.4 toolkits, with zero Odysseus code involved.

## Acceptance Criteria

- [ ] User runs `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml` on the host.
- [ ] `docker run --rm --gpus all nvidia/cuda:12.4.1-devel-ubuntu22.04 nvidia-smi` and a real CUDA
      context test both succeed post-fix (re-verified live, see Resolution).
- [ ] Odysseus container's `llama-server` preset relaunch shows `ggml_cuda_init` succeeding and
      GPU VRAM usage in `nvidia-smi` while serving, not CPU/RAM.

## Resolution

User ran `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml` on the host, confirmed the fix
worked, and the Qwen3-14B `llama-server` preset now correctly offloads to the RTX 4080 SUPER's VRAM.

Added `/etc/systemd/system/nvidia-cdi-generate.service` (oneshot, `Before=docker.service`,
`WantedBy=multi-user.target`) so the CDI spec is regenerated against the current device major
numbers on every boot, before Docker starts any GPU container -- prevents recurrence after future
host reboots without manual intervention.
