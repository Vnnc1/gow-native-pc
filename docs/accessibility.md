# Accessibility and texture packs

The launcher's **Accessibility** page groups input assistance and visual mods in
v0.5.0. Keyboard bindings remain on **Controls**; resolution, filtering and
borderless mode remain on **Graphics**.

## Texture packs

Choose the directory containing your PCSX2-format PNG replacements on Accessibility
and enable the pack before launching the game. Original game assets are preserved;
replacement images are loaded at runtime. Packs are not included or downloaded by
the project. Higher-resolution textures can increase GPU memory use and loading work;
they do not guarantee higher FPS or compatibility with every disc edition.

Some enemies were observed with holes/transparency with a replacement pack while
the same scene without replacements was opaque. The exact cause is unresolved:
replacement alpha data and renderer handling are both possible. No general alpha
override was applied. If this occurs:

1. Disable the pack and compare the same scene with identical graphics settings.
2. Record the disc edition, pack version and affected area.
3. If available, compare that pack and scene in PCSX2 to help isolate compatibility.
4. Export a [session report](reporting-bugs.md). Do not bundle game files or the pack
   in the diagnostic report.

## Held-button assistance

**Hold instead of mashing** repeats a selected held button after its initial delay.
L1, L2, R1 and R2 are individually opt-in because repetition can interrupt blocking,
grabbing and other held actions. Repetition pauses during multi-button chords;
shoulder repetition also pauses during stick movement. Disable assistance if a
particular minigame needs different timing. There is no automatic QTE detection.

## Keyboard stick gestures and chords

Choose shake or rotate assistance and hold the assigned stick-assist binding
(G by default) when the game requests that gesture. Release it to resume normal
movement. Assistance stops on focus loss and does not override connected gamepads.
It is disabled by default and is not automatically activated when an enemy grabs
Kratos or Medusa petrifies him.

The default Ctrl binding remains R2. Ctrl + Space and Ctrl + WASD are preserved
for held game actions; keyboard evade uses Alt + WASD. Check custom bindings for
conflicts. Migration leaves Alt/G unassigned if those keys were already occupied.

## Upscaling

Internal resolution, bicubic sharpening, FXAA and anisotropic filtering are existing
graphics options. Borderless mode allows external capture/scaling tools to see the
game window. It does not integrate DLSS (including DLSS 5), FSR 2–3 or XeSS, and
generated display frames are not additional guest simulation frames. See the
[graphics overview](../README.md#upscaling-and-external-tools).
