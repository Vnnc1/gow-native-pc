low-spec renderer tier for the launcher — RETIRED (superseded)

This patch used to add one "Low-spec" tier to the launcher: it set the whole rendering
profile in one place (0.5x internal resolution, a 640x360 window, bilinear stretch, no
sharpening, no FXAA, no anisotropy, the in-process VU1 x86-64 JIT and a 60 fps cap) and
added a resolution step below 1x.

It is retired because the launcher and the runtime now offer the same thing in a shape
that works, and the patch no longer applied to the current sources (the graphics tab
changed: the "dynamic resolution" switch was removed because nothing read it).

What replaced it:

  * The launcher already has the quick profiles of the graphics tab (launcher/qml/
    PaginaGrafico.qml), and the "bajo" one is the low-spec profile: 0.5x internal
    resolution, bilinear, no FXAA, no anisotropy.
  * The internal resolution accepts 0.25x..4x, which is the range the render-target
    renderer reads (PS2X_GS_HW_SCALE). The steps below 1x that this patch introduced are
    in the launcher already.
  * The software rasterizer exists now: the runtime has GSSwBackend (gs_sw_backend.h and
    gs_sw_backend.cpp, recovered from the GSCpuBackend of commit 00b3ca5 and adapted to
    the current GSRasterBackend interface). It is chosen with PS2X_GS_RENDERER=sw, or with
    PS2X_GS_HW=0, and the runtime falls back to it on its own when OpenGL 4.3 is not
    available. The launcher exposes it in the graphics tab ("Hardware rendering" off).
  * The "auto" resolution step of the old patch was never possible: the renderer has no
    frame-rate ladder, and PS2X_GS_HW_SCALE=auto was read as 0 (atof) and clamped to 0.25x.

Files: none. This file only records what happened to the proposal.

See docs/OPENGL-LOWSPEC-RENDERER-DESIGN-2026-11-05.zh-CN.md for the design.
