# Test configure invalidation and process cleanup without configuring or running a game.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$CompilerCache = 'sccache'
. (Join-Path $root 'tools/pipeline/modules/common.ps1')
. (Join-Path $root 'tools/pipeline/modules/tools.ps1')
. (Join-Path $root 'tools/pipeline/modules/toolchain.ps1')
. (Join-Path $root 'tools/pipeline/modules/process.ps1')
$nativeFailed = $false
try { Native $python @('-c', "import sys; print('expected failure on stderr', file=sys.stderr); sys.exit(7)") 'failure probe' }
catch { $nativeFailed = $_.Exception.Message -match 'rc=7' }
if (-not $nativeFailed) { throw 'Native must propagate the exit code of a failing piped command' }
Native $python @('-c', 'pass') 'success after failure'
$missingFailed = $false
try { Native (Join-Path $root 'data/nonexistent-native-probe.exe') @() 'missing executable' }
catch { $missingFailed = $true }
if (-not $missingFailed) { throw 'Native must reject a missing executable' }
Write-Host 'PASS: native process failure, success after failure and missing executable'
$patchNames = @((Get-RuntimePatches).Name)
if ([array]::IndexOf($patchNames, '29-recomp-dispatch-trim.patch') -ge [array]::IndexOf($patchNames, '29a-call-diagnostics-init.patch')) {
    throw 'Dependent runtime patches must follow their base patch on Windows PowerShell 5.1'
}
Write-Host 'PASS: deterministic runtime patch order'
$scratch = Join-Path $root ('data/pipeline-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
. (Join-Path $root 'tools/pipeline/modules/qt.ps1')
$archive = Join-Path $scratch 'qt-fixture.tar.xz'
$archiveCode = "import io, sys, tarfile`nwith tarfile.open(sys.argv[1], 'w:xz') as archive:`n    member = tarfile.TarInfo('qt-fixture/CMakeLists.txt')`n    member.size = 7`n    archive.addfile(member, io.BytesIO(b'fixture'))"
Native $python @('-I', '-c', $archiveCode, $archive) 'Qt source extraction fixture'
Expand-QtSource $archive $scratch
if ([IO.File]::ReadAllText((Join-Path $scratch 'qt-fixture/CMakeLists.txt')) -ne 'fixture' -or
    @(Get-ChildItem $scratch -Filter 'qt-source-*.tar').Count -ne 0) {
    throw 'Qt extraction must work without an external XZ executable and clean up its temporary tar'
}
Write-Host 'PASS: Qt XZ source extraction with the pinned Python and Windows tar'
$bld = Join-Path $scratch 'build'
$rt = Join-Path $root 'engine/runtime'
$rec = Join-Path $rt 'PS2Recomp'
$data = $scratch
$logs = $scratch
$vu1 = Join-Path $scratch 'vu1'
$pgoProfile = Join-Path $scratch 'profile with spaces.profdata'
$Config = 'Release'
$Stages = @()
. (Join-Path $root 'tools/pipeline/modules/game.ps1')
$script:configured = @()
# Record the real Configure arguments; only the external CMake process is replaced.
function Native($exe, [string[]]$a, $what) {
    $script:configured += ,$a
    $dir = $a[[array]::IndexOf($a, '-B') + 1]
    New-Item -ItemType Directory -Force $dir | Out-Null
    [IO.File]::WriteAllText((Join-Path $dir 'build.ninja'), '')
    [IO.File]::WriteAllText((Join-Path $dir 'CMakeCache.txt'), '')
}
Configure -MaySkip
Configure -MaySkip
if ($script:configured.Count -ne 1) { throw 'Unchanged configure should be skipped' }
[IO.File]::WriteAllText($pgoProfile, 'profile-one')
Configure -MaySkip
$stamp = (Get-Item $pgoProfile).LastWriteTimeUtc
[IO.File]::WriteAllText($pgoProfile, 'profile-two')
(Get-Item $pgoProfile).LastWriteTimeUtc = $stamp
Configure -MaySkip
if ($script:configured.Count -ne 3) { throw 'Changed PGO contents must invalidate configure' }
$previous = $script:configured[1] | Where-Object { $_ -like '-DCMAKE_CXX_FLAGS=*' }
$current = $script:configured[2] | Where-Object { $_ -like '-DCMAKE_CXX_FLAGS=*' }
if ($previous -eq $current -or $current -notmatch 'GOW_PGO_REVISION=' -or $current -notmatch 'use="[^"]+"') {
    throw 'PGO digest and quoted path must reach compiler commands'
}
Configure $bld 'generate' -MaySkip
$instrumented = $script:configured[-1]
if ('-DCMAKE_CXX_COMPILER_LAUNCHER=' -notin $instrumented -or '-DPS2X_ENABLE_SCCACHE=OFF' -notin $instrumented) {
    throw 'Instrumented builds must bypass compiler caches'
}
$script:cacheExe = ''
Configure -MaySkip
if ('-DCMAKE_CXX_COMPILER_LAUNCHER=' -notin $script:configured[-1]) { throw 'Cache opt-out must clear launcher' }
Write-Host 'PASS: configure skip, profile-content invalidation, quoted paths, instrumentation and cache opt-out'
$Pdb = $true
Configure -MaySkip
if (-not ($script:configured[-1] -match 'CXX_FLAGS=.*-gcodeview') -or -not ($script:configured[-1] -match 'EXE_LINKER_FLAGS=.*--pdb=')) {
    throw 'Clang profiling builds must request CodeView and a per-executable PDB'
}
Write-Host 'PASS: Clang profiling flags'
$Ltcg = $true
$jobs = 3
Configure -MaySkip
if ('-DPS2X_LTO_JOBS=' -notin $script:configured[-1] -or -not ($script:configured[-1] -match 'EXE_LINKER_FLAGS=.*--thinlto-jobs=3')) {
    throw 'Clang ThinLTO must use lld job control, not numeric -flto=N'
}
Write-Host 'PASS: opt-in ThinLTO job control'
$CpuTarget = 'portable'
Configure -MaySkip
if ($script:configured[-1] -match 'CXX_FLAGS=.*-march=x86-64-v3') { throw 'Portable builds must not require x86-64-v3' }
$beforeCpuChange = $script:configured.Count
$CpuTarget = 'x86-64-v3'
Configure -MaySkip
if ($script:configured.Count -ne $beforeCpuChange + 1 -or -not ($script:configured[-1] -match 'CXX_FLAGS=.*-march=x86-64-v3')) {
    throw 'CPU target must reach compiler flags and invalidate configure'
}
$prof = [pscustomobject]@{ build = [pscustomobject]@{ unity_batch = 16 } }
$ramGb = 16
Configure -MaySkip
if ('-DPS2X_RUNNER_UNITY_BUILD_BATCH_SIZE=16' -notin $script:configured[-1]) { throw 'Profile unity batch should apply with enough RAM' }
$ramGb = 8
Configure -MaySkip
if ('-DPS2X_RUNNER_UNITY_BUILD_BATCH_SIZE=8' -notin $script:configured[-1]) { throw 'Low-memory builds must retain the smaller unity batch' }
Write-Host 'PASS: CPU target and RAM-aware unity batch configure invalidation'

$probe = Join-Path $scratch 'probe.py'
[IO.File]::WriteAllText($probe, "import os, sys`nsys.exit(0 if os.environ.get('GOW_FOUNDATION_PROBE') == 'temporary' else 2)`n")
$original = $env:GOW_FOUNDATION_PROBE
try {
    $env:GOW_FOUNDATION_PROBE = 'original'
    Invoke-GameRecording $python $probe 1 @{GOW_FOUNDATION_PROBE='temporary'}
    if ($env:GOW_FOUNDATION_PROBE -ne 'original') { throw 'Recording did not restore original environment' }
    [IO.File]::WriteAllText($probe, "raise SystemExit(7)`n")
    $failed = $false
    try { Invoke-GameRecording $python $probe 1 @{GOW_FOUNDATION_PROBE='temporary'} } catch { $failed = $true }
    if (-not $failed -or $env:GOW_FOUNDATION_PROBE -ne 'original') { throw 'Failed recording must fail and restore environment' }
    Write-Host 'PASS: recording environment restored on success and failure'
} finally {
    [Environment]::SetEnvironmentVariable('GOW_FOUNDATION_PROBE', $original, 'Process')
}
