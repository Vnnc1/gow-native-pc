# Compare lean/full call dispatch in the same binary. This does not emulate another Git branch.
# Fixed rendering settings, alternating order, fresh private cards, frames-only diagnostics and raw evidence.
param([string]$Game = 'gow1', [ValidateRange(1, 10)][int]$Runs = 3,
      [ValidateRange(90, 600)][int]$Seconds = 120, [ValidateRange(20, 300)][int]$Warmup = 60,
      [ValidateRange(1, 4)][int]$Scale = 1)
$ErrorActionPreference = 'Stop'
if ($Warmup -ge $Seconds - 10) { throw 'Leave at least ten seconds after warm-up' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $root 'data/_tools/python/python.exe'
$profile = (& $python -I (Join-Path $root 'tools/pipeline/profile.py') $Game | Out-String | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Cannot load game profile' }
$data = Join-Path $root "data/$Game"
$elf = (Get-Content (Join-Path $data 'languages.json') -Raw -Encoding UTF8 | ConvertFrom-Json).recompile_elf
$build = (Get-Content (Join-Path $root 'data/build-root.txt') -Raw).Trim() + '-clang'
$runner = Join-Path $build 'ps2xRuntime/ps2EntryRunner.exe'
if (-not (Test-Path $runner)) { throw 'Build the Clang game first' }
. (Join-Path $root 'tools/pipeline/modules/process.ps1')
$output = Join-Path $data ('logs/perf-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $output | Out-Null
$machine = [ordered]@{cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name);
    memoryBytes=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;
    powerPlan=((& "$env:SystemRoot/System32/powercfg.exe" /getactivescheme) -join ' ')}
$original = @{}
# Keep inherited diagnostics, cheats and renderer options from contaminating the comparison.
foreach ($entry in Get-ChildItem env: | Where-Object { $_.Name -match '^(GOW_|PS2X_|TOBIICHI_)' }) {
    $original[$entry.Name] = $entry.Value
    Remove-Item "env:$($entry.Name)"
}
$results = @()
$process = $null
try {
    $settings = @{ GOW_VU1N_X64='1'; GOW_VU1N_DIAG='1'; GOW_PERF_DIAG='frames'; GOW_PERF_FRAME_PC=$profile.diagnostics.frame_pc;
        GOW_PAD_TEST='1'; GOW_FAST_BOOT='1'; GOW_SKIP_FMV='1'; GOW_AUDIO='0'; GOW_WINDOW_HIDDEN='1';
        GOW_PAD_GUION=$profile.optimize.pad_script; GOW_PAD_CAPTURAS='80';
        GOW_VU1_SIN_COMPILAR='1'; GOW_VU1_CAPTURE_MISSES='0'; PS2X_GS_HW='1'; PS2X_GS_WORKER='1';
        GOW_GS_FINISH_ASINCRONO='1'; PS2X_GS_ESCALA="$Scale"; PS2X_GS_HW_SCALE="$Scale";
        PS2X_GS_ESCALA_DINAMICA='0'; TOBIICHI_ANCHO='1280'; TOBIICHI_ALTO='720';
        TOBIICHI_PANORAMICO='16:9'; TOBIICHI_FXAA='0'; TOBIICHI_VENTANA_FPS='120';
        PS2X_GS_SHADER_CACHE_DIR=(Join-Path $data 'perf-shader-cache') }
    foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }
    New-Item -ItemType Directory -Force $settings.PS2X_GS_SHADER_CACHE_DIR | Out-Null
    for ($round = 1; $round -le $Runs; ++$round) {
        $order = if ($round % 2) { @('lean', 'full') } else { @('full', 'lean') }
        foreach ($mode in $order) {
            $folder = Join-Path $output "$round-$mode"
            New-Item -ItemType Directory -Path $folder | Out-Null
            $env:GOW_MC0 = Join-Path $folder 'card.ps2'
            $env:GOW_DISPATCH_FULL = if ($mode -eq 'full') { '1' } else { '0' }
            $stderr = Join-Path $folder 'stderr.log'
            Write-Host "Benchmark $round/$Runs ${mode}: $Seconds seconds; $folder"
            $process = Start-Process -FilePath $runner -ArgumentList "`"$elf`"" -WorkingDirectory $folder -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput (Join-Path $folder 'stdout.log') -RedirectStandardError $stderr
            $null = $process.Handle
            for ($t = 0; $t -lt $Seconds -and -not $process.HasExited; $t += 5) { Start-Sleep 5 }
            if (-not $process.HasExited) { $null = Close-GameWindow $process.Id; $null = $process.WaitForExit(15000) }
            if (-not $process.HasExited) { throw "Benchmark $mode did not close gracefully" }
            $log = [IO.File]::ReadAllText($stderr)
            $samples = @()
            foreach ($match in [regex]::Matches($log, '\[gow-perf\] t=([\d.]+) window=([\d.]+).*?guest_flip_hz=([\d.]+) host_hz=([\d.]+)')) {
                $time = [double]::Parse($match.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture)
                $window = [double]::Parse($match.Groups[2].Value, [Globalization.CultureInfo]::InvariantCulture)
                if ($time - $window -lt $Warmup) { continue }
                $samples += [ordered]@{ time=$time; window=$window;
                    guestFlipHz=[double]::Parse($match.Groups[3].Value, [Globalization.CultureInfo]::InvariantCulture);
                    hostHz=[double]::Parse($match.Groups[4].Value, [Globalization.CultureInfo]::InvariantCulture) }
            }
            $gameplay = $log -match 'state=11.*levelReady=1'
            $valid = $process.ExitCode -eq 0 -and $gameplay -and $samples.Count -ge 3
            $results += [ordered]@{round=$round; dispatch=$mode; valid=$valid; exitCode=$process.ExitCode;
                gameplay=$gameplay; samples=$samples; log=$stderr}
            $report = [ordered]@{schema=1; description='Same binary, lean versus full call dispatch; not a main-branch comparison';
                runner=$runner; runnerHash=(Get-FileHash $runner -Algorithm SHA256).Hash; elf=$elf;
                machine=$machine; settings=$settings;
                scale=$Scale; audio=$false; warmup=$Warmup; seconds=$Seconds; diagnostics='frames'; results=$results}
            [IO.File]::WriteAllText((Join-Path $output 'summary.json'), ($report | ConvertTo-Json -Depth 8))
            if (-not $valid) { throw "Benchmark did not reach gameplay or collect enough samples: $folder" }
        }
    }
    Write-Host "PASS: comparison evidence in $output/summary.json"
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    Get-ChildItem env: | Where-Object { $_.Name -match '^(GOW_|PS2X_|TOBIICHI_)' } | ForEach-Object { Remove-Item "env:$($_.Name)" }
    foreach ($key in $original.Keys) { [Environment]::SetEnvironmentVariable($key, $original[$key], 'Process') }
}
