# Exercise no-argument startup with diagnostics supplied only by the boot profile (patch 29a).
param([string]$Game = 'gow1', [ValidateRange(90, 600)][int]$Seconds = 100)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $root 'data/_tools/python/python.exe'
$profile = (& $python -I (Join-Path $root 'tools/pipeline/profile.py') $Game | Out-String | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Cannot load game profile' }
$data = Join-Path $root "data/$Game"
$build = (Get-Content (Join-Path $root 'data/build-root.txt') -Raw).Trim() + '-clang'
$runner = Join-Path $build 'ps2xRuntime/ps2EntryRunner.exe'
$boot = Join-Path (Split-Path $runner) 'gow-native.boot'
$originalBoot = [IO.File]::ReadAllBytes($boot)
$elf = (Get-Content (Join-Path $data 'languages.json') -Raw -Encoding UTF8 | ConvertFrom-Json).recompile_elf
$output = Join-Path $data ('logs/standalone-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $output | Out-Null
. (Join-Path $root 'tools/pipeline/modules/process.ps1')
$original = @{}
$process = $null
try {
    foreach ($entry in Get-ChildItem env: | Where-Object { $_.Name -match '^(GOW_|PS2X_|TOBIICHI_)' }) {
        $original[$entry.Name] = $entry.Value
        Remove-Item "env:$($entry.Name)"
    }
    $settings = @{GOW_VU1N_X64='1'; GOW_VU1N_VERIFY='2000'; GOW_PERF_DIAG='frames';
        GOW_PERF_FRAME_PC=$profile.diagnostics.frame_pc; GOW_DISPATCH_FULL='1';
        GOW_PAD_TEST='1'; GOW_FAST_BOOT='1'; GOW_SKIP_FMV='1'; GOW_AUDIO='0'; GOW_WINDOW_HIDDEN='1';
        GOW_PAD_GUION=$profile.optimize.pad_script; GOW_PAD_TEST_NO_CAPTURE='1';
        GOW_MC0=(Join-Path $output 'card.ps2'); GOW_VU1_SIN_COMPILAR='1'; GOW_VU1_CAPTURE_MISSES='0';
        PS2X_GS_HW='1'; PS2X_GS_WORKER='1'; GOW_GS_FINISH_ASINCRONO='1'; PS2X_GS_HW_SCALE='1';
        PS2X_GS_ESCALA='1'; PS2X_GS_ESCALA_DINAMICA='0'; TOBIICHI_ANCHO='1280'; TOBIICHI_ALTO='720'}
    $text = "GOW_NATIVE_BOOT_V1`n$elf`n" + (($settings.Keys | Sort-Object | ForEach-Object { "$_=$($settings[$_])" }) -join "`n") + "`n"
    [IO.File]::WriteAllText($boot, $text, (New-Object Text.UTF8Encoding($false)))
    $process = Start-Process -FilePath $runner -WorkingDirectory $output -WindowStyle Hidden -PassThru
    $null = $process.Handle
    for ($elapsed = 0; $elapsed -lt $Seconds -and -not $process.HasExited; $elapsed += 5) { Start-Sleep 5 }
    if (-not $process.HasExited) { $null = Close-GameWindow $process.Id; $null = $process.WaitForExit(15000) }
    if (-not $process.HasExited) { throw 'Standalone game did not close gracefully' }
    $logPath = Join-Path $output 'standalone.log'
    Copy-Item -LiteralPath (Join-Path (Split-Path $runner) 'standalone.log') -Destination $logPath
    $log = [IO.File]::ReadAllText($logPath)
    $result = [ordered]@{exitCode=$process.ExitCode; bootProfile=($log -match 'Using per-build gow-native.boot');
        gameplay=($log -match 'state=11.*levelReady=1'); verified=($log -match '2000 runs checked, 0 mismatches');
        guestFrames=($log -match 'guest_flip_hz=[1-9]'); diagnosticsFromBootOnly=$true;
        runnerHash=(Get-FileHash $runner -Algorithm SHA256).Hash}
    [IO.File]::WriteAllText((Join-Path $output 'summary.json'), ($result | ConvertTo-Json))
    if ($process.ExitCode -ne 0 -or -not $result.bootProfile -or -not $result.gameplay -or -not $result.verified -or -not $result.guestFrames) {
        throw "Standalone validation failed: $output"
    }
    Write-Host "PASS: standalone boot-only diagnostics, gameplay and VU1 parity: $output"
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    [IO.File]::WriteAllBytes($boot, $originalBoot)
    foreach ($key in $original.Keys) { [Environment]::SetEnvironmentVariable($key, $original[$key], 'Process') }
}
