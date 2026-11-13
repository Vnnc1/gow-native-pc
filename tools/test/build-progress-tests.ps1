$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $root 'tools/pipeline/modules/build-progress.ps1')
$directory = Join-Path ([IO.Path]::GetTempPath()) 'gow progress fixture'
$state = New-GameBuildProgress $directory
$lines = @(
    '[0/2] Re-checking globbed directories...',
    '[1/2] Re-running CMake...',
    '[0/7] Performing update step for raylib-populate',
    "-- Build files have been written to: $directory/_deps/raylib-subbuild",
    '[7/7] Completed raylib-populate',
    '[0/7] Performing update step for imgui-populate',
    '[7/7] Completed imgui-populate',
    "-- Build files have been written to: $directory",
    '[0/4] Re-checking globbed directories...',
    '[1/558] Building CXX object first.cpp.obj',
    '[2/558] Building CXX object second.cpp.obj',
    '[6/558] Building CXX object next.cpp.obj',
    '[558/558] Linking CXX executable ps2EntryRunner.exe'
)
$events = @($lines | ForEach-Object { Read-GameBuildProgress $state $_ })
if ($events.Count -ne 4 -or $events[0].done -ne 1 -or $events[0].total -ne 558 -or -not $events[-1].linking) {
    throw 'Nested dependency/glob counters must not reach game progress'
}
if (-not $events[0].changed -or $events[1].changed -or -not $events[2].changed) {
    throw 'Emit once per integer percent, starting with the real build counter'
}
foreach ($line in @('[0/0] invalid', '[9/3] invalid', 'ninja: no work to do.', '[not/a] counter')) {
    if ($null -ne (Read-GameBuildProgress $state $line)) { throw "Unexpected progress: $line" }
}
# A second CMake regeneration must suspend progress again, without changing the actual counters.
$null = Read-GameBuildProgress $state '[1/2] Re-running CMake...'
if ($null -ne (Read-GameBuildProgress $state '[1/1] Building CXX object nested.cpp.obj')) { throw 'Nested compiler output leaked' }
$null = Read-GameBuildProgress $state "-- Build files have been written to: $directory"
$revised = Read-GameBuildProgress $state '[10/600] Building CXX object revised.cpp.obj'
if ($revised.done -ne 10 -or $revised.total -ne 600) { throw 'Revised real totals must remain truthful' }
$fresh = New-GameBuildProgress $directory
if ($null -eq (Read-GameBuildProgress $fresh '[1/1] Linking CXX executable game.exe')) { throw 'One-file rebuilds must report progress' }
Write-Host 'PASS: build progress ignores CMake sub-builds, resumes at outer graph and preserves real totals'

# Exercise Build-Game's actual output path without starting Ninja, CMake or the game.
$scratch = Join-Path $root ('data/build-progress-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
$Stages = @()
. (Join-Path $root 'tools/pipeline/modules/common.ps1')
. (Join-Path $root 'tools/pipeline/modules/game.ps1')
function Use-Toolchain {}
function Need($path, $what) {}
function Configure($dir, $profile, [switch]$MaySkip) {
    $script:configuredGameProfile = [ordered]@{buildRoot=$dir; mode=$profile;
        pgoApplied=[bool]$script:fakeProfileHash; appliedPgoHash=$script:fakeProfileHash}
}
function Write-CompilerCacheStats($what) {}
function Languages { return @{ recompile_elf = '' } }
$bld = Join-Path $scratch 'unused'
$logs = $scratch
$jobs = 1
$script:fakeLines = $lines
$script:fakeExit = 0
function ninja { $script:fakeLines; $global:LASTEXITCODE = $script:fakeExit }
$output = @(Build-Game $directory 6>&1 | ForEach-Object { "$_" })
$progress = @($output | Where-Object { $_ -like '@@progress *' })
if (($progress -join '|') -ne '@@progress 1 558|@@progress 6 558|@@progress 558 558|@@progress 1 1') {
    throw "Unexpected Build-Game protocol: $progress"
}
$script:fakeLines = @('ninja: no work to do.')
$output = @(Build-Game $directory 6>&1 | ForEach-Object { "$_" })
if ('@@progress 1 1' -notin $output) { throw 'Successful no-op build must finish the step' }
$script:fakeExit = 7
$failed = $false
$output = [Collections.Generic.List[string]]::new()
try { Build-Game $directory 6>&1 | ForEach-Object { $output.Add("$_") } } catch { $failed = $_.Exception.Message -match 'rc=7' }
if (-not $failed -or '@@progress 1 1' -in $output) { throw 'Failed build must preserve its failure and not emit completion' }
if ($script:gameBuildProfiles.Count -ne 2 -or $script:gameBuildProfiles[-1].pgoApplied) {
    throw 'Only successful game builds may record applied profile metadata'
}
$script:fakeExit = 0
$script:fakeProfileHash = 'profile-used'
Build-Game $directory
$script:fakeProfileHash = 'profile-from-failed-build'
$script:fakeExit = 7
try { Build-Game $directory } catch { }
if ($script:gameBuildProfiles.Count -ne 3 -or $script:gameBuildProfiles[-1].appliedPgoHash -ne 'profile-used') {
    throw 'Failed builds must not replace the last successful build profile hash'
}

$pipelineWatch = [Diagnostics.Stopwatch]::StartNew()
$pipelineSucceeded = $false
$pgoProfile = Join-Path $scratch 'available.profdata'
[IO.File]::WriteAllText($pgoProfile, 'different available profile')
Write-PipelineMetrics
$metrics = Get-Content (Get-ChildItem $logs -Filter 'pipeline-*.json' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName -Raw | ConvertFrom-Json
if ($metrics.pgoHash -ne $metrics.availablePgoHash -or $metrics.pgoHashMeaning -ne 'available-profile-not-application' -or
    $metrics.gameBuildProfiles.Count -ne 3 -or $metrics.gameBuildProfiles[-1].appliedPgoHash -ne 'profile-used' -or -not $metrics.pgoApplied) {
    throw 'Metrics must separate the available profile from successful actual game builds'
}
$script:gameBuildProfiles.Clear()
$Stages = @('verify')
Write-PipelineMetrics
$metrics = Get-Content (Get-ChildItem $logs -Filter 'pipeline-*.json' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName -Raw | ConvertFrom-Json
if ($null -ne $metrics.pgoApplied -or $metrics.gameBuildProfiles.Count -ne 0 -or -not $metrics.availablePgoHash) {
    throw 'No recorded game build must leave PGO application unknown even when a profile file exists'
}
Write-Host 'PASS: Build-Game emits filtered progress, completes no-op builds and preserves failures'
