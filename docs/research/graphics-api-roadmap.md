# Future graphics backends and automatic selection

Requested 2026-11-04. Proposal only: this checkout implements OpenGL. No Vulkan
or Direct3D backend, hardware benchmark, automatic backend selector or performance
support claim is introduced by this document.

## Objective

Investigate lower driver CPU overhead, bounded resource use, stable guest frame
pacing and presentation latency on different hardware. A new API does not improve
image quality or VU1 execution automatically. Preserve the same GS semantics,
resolution, filtering, effects, game speed and audio when comparing backends.

## Sequence

1. Preserve OpenGL as the working reference and fallback. First establish a stable
   command/state boundary and synthetic rendering oracle; maintain the current GS
   transfer/readback, CLUT, texture hazards, depth, alpha, blend and presentation order.
2. Prototype Vulkan in a separate build with explicit memory/resource lifetimes,
   bounded queues, synchronization, shader/pipeline caches and device-loss recovery.
   It must support the intended Windows/Linux GPUs, not merely compile successfully.
3. Evaluate Direct3D 12 as a Windows alternative after profiling shows a reason.
   Consider Direct3D 11 only for a concrete compatibility/driver target. Do not add
   APIs simply to increase the backend list; each multiplies correctness testing.
4. Compare the same synthetic inputs and visible gameplay across AMD, NVIDIA and
   Intel, including weaker laptops. Require color/depth/alpha parity, sound, cold
   shader/pipeline behavior, sustained frame tails and memory/CPU pressure.

## Launcher automatic choice

A future launcher may enumerate adapters, driver versions, API capabilities,
required formats/extensions and available memory. GPU vendor/model alone is not
sufficient evidence that one backend is faster. Prefer a validated compatibility
matrix and a short local, deterministic synthetic probe with explicit bounds.
Do not use a player's save or launch an unbounded benchmark during startup.

Choose only among compatible, validated backends. Cache a decision using adapter,
driver, renderer version and relevant settings; revalidate when those change.
Prefer conservative OpenGL when evidence is absent or inconclusive. Recover from
startup/shader/device failures through a bounded fallback and retain a useful local
log. A manual override may exist for troubleshooting, but ordinary installation
and Play must work without additional tools, switches or repeated recompilation.

## Measurement gates

- Compare guest FPS, new displayed frames, repeated frames and pacing separately.
- Measure CPU milliseconds per guest frame, GPU execution time where available,
  memory pressure, queue waits and audio missing frames. Utilization alone is not
  energy consumption; no watts/temperature claim without appropriate telemetry.
- A capped 60-FPS scene can still show an efficiency benefit. Require sufficient
  samples, stable scene alignment, unchanged quality and no tail/latency regression.
- Include unsupported devices and failed/neutral tests in the matrix. Do not infer
  notebook gains from RX580 results or claim universal 60 FPS.

References: [Vulkan synchronization](https://docs.vulkan.org/guide/latest/synchronization.html)
and [Direct3D command queue design](https://learn.microsoft.com/en-us/windows/win32/direct3d12/design-philosophy-of-command-queues-and-command-lists).
