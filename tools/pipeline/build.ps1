# The build pipeline: from disc images to a native PC game, driven by a game profile (games/<id>/game.toml).
# The launcher's Install tab runs it; build.cmd runs it from a terminal. Stages (run in this order, any subset):
#   tools      the build tools into data/_tools (portable Git, Python, CMake, Ninja and the clang compiler, each
#              downloaded once and checked against its SHA-256); every other stage also fetches what it needs
#   fetch      engine/runtime: clone engine/runtime.toml's repository at its commit, apply engine/patches/*.patch
#   discs      -Discs "<iso>|<iso>": tools/disc/prepare.py -> data/<game>/discs/*, languages.json, one memory card
#   vu1disc    experimental: usable VU1 uploads read from the prepared disc (tools/disc/vu1_from_disc.py; partial coverage)
#              into data/<game>/vu1_capture, so the next configure + build compiles it without playing (run "native")
#   configure  CMake + Ninja in -BuildRoot (a short path: the runtime's dependencies exceed MAX_PATH in long folders),
#              with the recorded VU1 microcode (data/<game>/vu1_capture) when there is some
#   recomp     ps2_recomp: the profile's executable (languages.json: recompile_elf) -> C++ (data/<game>/recomp)
#   sync       generated C++ + the profile's overrides into the runtime's runner (only changed files)
#   build      ps2EntryRunner (log: data/<game>/logs/build.log)
#   pgo        clang only: an instrumented build plays the [optimize] pad script, its profile goes to
#              data/<game>/pgo/gow.profdata, and the game is rebuilt with it (profile-guided optimisation)
#   tune       install path with first-play preparation: one instrumented -O1 build plays the pad script once,
#              recording the VU1/IOP code (as optimize) and the profile (as pgo); one final build uses both
#   optimize   the game plays itself (profile [optimize]: pad script, seconds), hidden and muted (engine/patches/15), recording
#              the VU1 microcode and IOP modules it uses, then "native" (only the VU1 / IOP code is rebuilt: patch 16)
#   native     the recorded VU1 microcode and IOP modules compiled into the game (the launcher records new microcode
#              while you play, so this makes visited areas faster); configure + build
#   verify     pipeline, guest-call and codegen regression tests (no ISO needed)
#   launcher   the Qt launcher into launcher/build-clang (matching Qt sources built once into data/_tools), plus the
#              shortcut "God of War Launcher.lnk" in the repository root to start it
#   package    the release zip for GitHub Releases (data/_package): launcher/bin + tools, games, engine (no runtime), docs
#   installer  the release setup (data/_package/gow-native-pc-setup.exe): installer/ built and packed with the package
# Output protocol for the launcher: "=== <step> ===", "@@progress <done> <all>", "@@status <text>", other lines = log.
# usage: powershell -ExecutionPolicy Bypass -File tools\pipeline\build.ps1 [-Game gow1] [-Stages fetch,discs,configure,
#        recomp,sync,build] [-Discs "<iso>|<iso>"] [-Config Release|RelWithDebInfo] [-Ltcg] [-Pdb] [-BuildRoot <folder>]
# -BuildRoot: default C:\gow-build (or C:\gow-build-<hash> when another copy uses it), kept in data\build-root.txt
# -Pdb: Release with debug information (ps2EntryRunner.pdb) for profilers; the optimised code is the same
# -CpuTarget: portable (x86-64-v2, default) or x86-64-v3 (explicit AVX2-class build).
# -Codegen locals (default): recomp stage with register-locals code generation (engine/patches/08, ~22 % less EE
#        thread time); -Codegen classic generates the code as before patch 08
# All components use pinned llvm-mingw. -Toolchain msvc is accepted only to migrate old scripts to clang.
# -CompilerCache none disables the local object cache; -ForceRecomp regenerates EE code even on a content match.
# -Stages verify runs pipeline and runtime/codegen regression tests without an ISO.
param(
    [string]$Game = 'gow1',
    [string[]]$Stages = @('fetch', 'discs', 'configure', 'recomp', 'sync', 'build'),
    [string]$Discs = '',
    [ValidateSet('Release', 'RelWithDebInfo')][string]$Config = 'Release',
    [switch]$Ltcg,
    [switch]$Pdb,
    [ValidateSet('portable', 'x86-64-v3')][string]$CpuTarget = 'portable',
    [ValidateSet('classic', 'locals')][string]$Codegen = 'locals',
    [string]$BuildRoot = '',
    [ValidateSet('', 'msvc', 'clang')][string]$Toolchain = '', # msvc is a migration alias
    [ValidateSet('sccache', 'none')][string]$CompilerCache = 'sccache',
    [switch]$ForceRecomp,
    [int]$Seconds = 0
)
if ($PSVersionTable.PSVersion.Major -lt 6) { $env:PSModulePath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\Modules" }
$ErrorActionPreference = 'Stop'
trap { Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Stages = @(($Stages -join ',') -split ',' | Where-Object { $_ })
. (Join-Path $PSScriptRoot 'modules/common.ps1')
$allowedStages = @('tools','fetch','discs','vu1disc','configure','recomp','sync','build','pgo','tune','optimize','native','verify','launcher','package','installer')
foreach ($stage in $Stages) { if ($stage -notin $allowedStages) { throw "Unknown stage '$stage'" } }
# One writer per checkout: caches and generated outputs must never be updated concurrently.
New-Item -ItemType Directory -Force (Join-Path $root 'data') | Out-Null
try { $pipelineLock = [IO.File]::Open((Join-Path $root 'data/pipeline.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
catch { throw 'Another pipeline is using this checkout. Wait for it to finish.' }
$pipelineWatch = [Diagnostics.Stopwatch]::StartNew()
$pipelineSucceeded = $false
try {
    foreach ($module in @('tools','context','toolchain','process')) { . (Join-Path $PSScriptRoot "modules/$module.ps1") }
    if ($Stages -contains 'tools') { Step 'build tools'; Use-Clang }
    foreach ($module in @('runtime','game','optimize','verify','distribution')) { . (Join-Path $PSScriptRoot "modules/$module.ps1") }
    $pipelineSucceeded = $true
    Write-Host "`nDone." -ForegroundColor Green
} finally {
    try { Write-PipelineMetrics } finally { $pipelineLock.Dispose() }
}
