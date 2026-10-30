# Repeatable local game validation. Reads all game-specific values from the game profile.
param([ValidateSet('hybrid', 'jit', 'calls')][string]$Mode = 'hybrid',
      [ValidateRange(90, 600)][int]$Seconds = 100, [string]$Game = 'gow1', [switch]$Visible,
      [switch]$Audio, [string]$DiscElf = '', [string]$PadScript = '', [switch]$AllowMenu,
      [switch]$Standalone)

$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot)
$build = (Get-Content (Join-Path $root 'data/build-root.txt') -Raw).Trim()
if ((Get-Content (Join-Path $root 'data/toolchain.txt') -Raw).Trim() -eq 'clang') { $build += '-clang' }
$data = Join-Path $root "data/$Game"
$elf = (Get-Content (Join-Path $data 'languages.json') -Raw | ConvertFrom-Json).recompile_elf
if ($DiscElf) { $elf = (Resolve-Path -LiteralPath $DiscElf).Path }
$python = Join-Path $root 'data/_tools/python/python.exe'
$profile = (& $python -I (Join-Path $root 'tools/pipeline/profile.py') $Game | Out-String | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read game profile' }
$runDir = Join-Path $data ('logs/jit-' + $Mode + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory $runDir | Out-Null
. (Join-Path $root 'tools/pipeline/modules/process.ps1')
$vars = @{ GOW_VU1N_X64='1'; GOW_VU1N_DIAG='1'; GOW_VU1N_VERIFY='2000'; GOW_PERF_DIAG='1'; GOW_PAD_TEST='1'; GOW_FAST_BOOT='1'; GOW_SKIP_FMV='1'; GOW_AUDIO='0'; GOW_WINDOW_HIDDEN='1'; PS2X_GS_HW='1'; PS2X_GS_WORKER='1'; GOW_GS_FINISH_ASINCRONO='1'; TOBIICHI_ANCHO='1280'; TOBIICHI_ALTO='720'; GOW_PAD_GUION=$profile.optimize.pad_script; GOW_PAD_CAPTURAS='10,80' }
$vars.GOW_PERF_FRAME_PC = $profile.diagnostics.frame_pc
if ($Audio) {
    $vars.GOW_AUDIO = '1'
    $vars.GOW_AUDIO_STATS = '1'
    $vars.GOW_IOP_DRIFT = '1'
    $vars.GOW_AUDIO_RAW = Join-Path $runDir 'mixed.s16le'
}
if ($PadScript) { $vars.GOW_PAD_GUION = $PadScript }
$vars.GOW_VU1X_ONLY = $(if ($Mode -eq 'hybrid') { '0' } else { '1' })
$vars.GOW_VU1X_INLINE = $(if ($Mode -eq 'calls') { '0' } else { '1' })
$vars.GOW_VU1_CAPTURE_MISSES = '1'
$vars.GOW_VU1_CAPTURA = Join-Path $data 'jit-validation-capture'
$vars.GOW_VU1_SIN_COMPILAR = '1'
# These switches are presence/path based: the string "0" does not disable them.
Remove-Item env:GOW_VU1_NATIVE_OFF, env:GOW_VU1N_JIT -ErrorAction SilentlyContinue
$vars.PS2X_GS_ESCALA = '2'
$vars.PS2X_GS_HW_SCALE = '2'
$vars.PS2X_GS_ESCALA_DINAMICA = '1'
$vars.TOBIICHI_PANORAMICO = '16:9'
$vars.TOBIICHI_FXAA = '1'
$vars.TOBIICHI_VENTANA_FPS = '120'
$vars.PS2X_GS_SHADER_CACHE_DIR = Join-Path $data 'shader-test-cache'
if ($Visible) { $vars.GOW_WINDOW_HIDDEN = '0' }
New-Item -ItemType Directory -Force $vars.GOW_VU1_CAPTURA, $vars.PS2X_GS_SHADER_CACHE_DIR | Out-Null
foreach ($k in $vars.Keys) { Set-Item "env:$k" $vars[$k] }
$start = @{ FilePath=(Join-Path $build 'ps2xRuntime/ps2EntryRunner.exe'); WorkingDirectory=$runDir; WindowStyle='Hidden';
    RedirectStandardOutput=(Join-Path $runDir 'stdout.log'); RedirectStandardError=(Join-Path $runDir 'stderr.log'); PassThru=$true }
if ($Standalone) {
    if ($DiscElf -or $Mode -ne 'hybrid') { throw 'Standalone uses its recorded disc and runtime settings; do not combine with DiscElf or non-hybrid mode.' }
    $boot = Get-Content (Join-Path $build 'ps2xRuntime/gow-native.boot')
    if ($boot[0] -ne 'GOW_NATIVE_BOOT_V1') { throw 'Missing or invalid standalone profile' }
    $elf = $boot[1]
} else { $start.ArgumentList = ('"' + $elf + '"') }
$p = Start-Process @start
$null = $p.Handle
Write-Output "Run directory: $runDir; PID: $($p.Id)"
for ($t = 0; $t -lt $Seconds -and -not $p.HasExited; $t += 5) { Start-Sleep 5; Write-Output "Smoke test: $($t + 5)/$Seconds seconds" }
if (-not $p.HasExited) { $null = Close-GameWindow $p.Id; $null = $p.WaitForExit(15000) }
$forced = -not $p.HasExited
if ($forced) { Stop-Process -Id $p.Id; $p.WaitForExit(); Write-Output 'Process required forced termination after WM_CLOSE.' }
$p.Refresh()
Write-Output "Exit code: $($p.ExitCode)"
if ($Standalone) { Copy-Item (Join-Path $build 'ps2xRuntime/standalone.log') (Join-Path $runDir 'stderr.log') }
Get-Content (Join-Path $runDir 'stderr.log') -Tail 35
$log = Get-Content (Join-Path $runDir 'stderr.log') -Raw
$summary = @{ mode=$Mode; seconds=$Seconds; standalone=[bool]$Standalone; audio=[bool]$Audio; elf=$elf; menuAllowed=[bool]$AllowMenu; exitCode=$p.ExitCode; forcedTermination=$forced; gameplay=($log -match 'state=11.*levelReady=1');
    verified=($log -match '2000 runs checked, 0 mismatches');
    jitCompiled=($log -match '\[vu1x\] compiled=[1-9]');
    captures=@(Get-ChildItem $vars.GOW_VU1_CAPTURA -Filter '*.bin').Count }
$summary | ConvertTo-Json | Set-Content (Join-Path $runDir 'summary.json') -Encoding UTF8
if ($forced -or $p.ExitCode -ne 0 -or (-not $AllowMenu -and -not $summary.gameplay) -or -not $summary.verified -or ($Mode -ne 'hybrid' -and -not $summary.jitCompiled)) { exit 1 }
