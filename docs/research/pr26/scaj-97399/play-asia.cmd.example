@echo off
rem Play the Asia SCAJ-97399 disc (Chinese shell) on its registered Japan build.
rem The paths and hashes live in data\gow1\regional-builds.json; the launcher offers the same edition.
rem
rem SETTINGS: this script starts the runner with an explicit ELF argument, so main.cpp takes the "argv boot
rem path" and never reads gow-native.boot. Launcher settings (including the effect switches) do NOT reach the
rem game from here. Either play from the launcher (it also refreshes gow-native.boot), or set the same
rem variables by hand before calling this script, e.g.
rem   set "GOW_FX_NO_ADDITIVE3D=1"        rain / spray / glow off (the most visible switch)
rem   set "GOW_FX_NO_SHADOWS=1"           character shadows off
rem   set "GOW_FX_NO_TEXTURE_FILTER=1"    nearest-neighbour textures
rem Anything already defined in the environment is left alone below, so command-line overrides win.
rem
rem Internal resolution. 0.7x measured the same guest rate as 0.5x on the i3-4170 (29.0 vs 29.1 fps, 25 s, opening
rem level): the GPU goes from ~6.3 to ~13.2 ms per frame ([gs-gpu], GOW_GS_GPU_PROFILE=1), which is exactly the pixel
rem area doubling, and the frame is still bound by VU1 (~24 ms), so the extra work is absorbed. ~2x the pixels for no
rem frames. Drop to 0.5 if a heavier scene starts to hitch; 1.0x is not free (GPU would reach ~27 ms).
if not defined PS2X_GS_HW_SCALE set "PS2X_GS_HW_SCALE=0.7"
if not defined GOW_VU1N_X64 set "GOW_VU1N_X64=1"
rem Run VIF1 -> VU1 -> GIF -> GS on the worker thread, with the GS frontend pipelined behind VU1 on its own stage
rem (PS2X_GS_WORKER=1). Without it every draw lands inline on the EE thread and the three stages serialise: measured
rem 25 -> 35 guest fps on the i3-4170 at 0.5x. The launcher already sets this; a manual play must set it too.
if not defined PS2X_GS_WORKER set "PS2X_GS_WORKER=1"
rem Fast VU semantics on the x64 JIT (patch 60): title/attract 60 guest fps on the i3-4170 instead of ~53-56.
if not defined GOW_VU1_FAST set "GOW_VU1_FAST=1"
if not defined GOW_PERF_FRAME_PC set "GOW_PERF_FRAME_PC=0x183BB8"
cd /d "C:\gow-jpn-data\gow1\discs\asia-97399"
start "" "C:\gow-build-jpn\ps2xRuntime\ps2EntryRunner.exe" "SLPM_670.10"
