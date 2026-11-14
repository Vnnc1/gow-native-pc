# Test configure invalidation and process cleanup without configuring or running a game.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build-root-tests.ps1')
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
& (Join-Path $PSScriptRoot 'build-progress-tests.ps1')
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
# The process must receive each argument whole: a quoted path with spaces inside a flag list (the PGO profile of an
# install in "E:\God of War") once reached CMake cut at the first space.
$argvFile = Join-Path ([IO.Path]::GetTempPath()) ('gow-argv-' + [guid]::NewGuid().ToString('N') + '.json')
$sent = @('-DCMAKE_CXX_FLAGS=-O3 -fprofile-instr-use="E:/God of War/data/gow1/pgo/gow.profdata" -DX=1',
          'C:\dir with space\', 'plain', '-I"C:/no-space"', 'a "b c" \"d\" e\\')
Native $python (@('-I', '-c', "import json, sys; open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps(sys.argv[2:]))", $argvFile) + $sent) 'argument passing probe'
# not piped: Windows PowerShell 5.1 emits a piped JSON array as one item
$received = ConvertFrom-Json ([IO.File]::ReadAllText($argvFile))
Remove-Item -LiteralPath $argvFile
$expected = @($sent[0], $sent[1], $sent[2], '-IC:/no-space', $sent[4])
if ($received.Count -ne $expected.Count) { throw "Native must pass each argument whole: got $($received.Count) arguments" }
for ($i = 0; $i -lt $expected.Count; ++$i) {
    if ($received[$i] -cne $expected[$i]) { throw "Native argument $i arrived as [$($received[$i])], expected [$($expected[$i])]" }
}
Write-Host 'PASS: native arguments with spaces, inner quotes and trailing backslashes arrive whole'
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
# The fixture supplies identity only; production manifest parsing and profile selection remain under test.
function Get-ProfileIdentity { return @{ runtime='runtime'; patches='patches'; game='game'; code='code' } }
$Game = '__pipeline_fixture'
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
if ($script:configuredGameProfile.mode -ne 'off' -or $script:configuredGameProfile.pgoApplied -or
    $null -ne $script:configuredGameProfile.appliedPgoHash) { throw 'Unprofiled configure metadata must remain unprofiled on a configure skip' }
if ('-DPS2X_ENABLE_FFMPEG=OFF' -notin $script:configured[0]) {
    throw 'Windows builds must clear a cached FFmpeg opt-in and use the bundled MPEG decoder'
}
[IO.File]::WriteAllText($pgoProfile, 'profile-one')
[IO.File]::WriteAllText("$pgoProfile.json", ((Get-ProfileIdentity) | ConvertTo-Json))
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
if ($script:configuredGameProfile.mode -ne 'use' -or -not $script:configuredGameProfile.pgoApplied -or
    $script:configuredGameProfile.appliedPgoHash -ne (Get-FileHash $pgoProfile -Algorithm SHA256).Hash) {
    throw 'Configure metadata must capture the hash actually put into compiler flags'
}
Configure $bld 'generate' -MaySkip
if ($script:configuredGameProfile.mode -ne 'generate' -or $script:configuredGameProfile.pgoApplied -or
    $null -ne $script:configuredGameProfile.appliedPgoHash) { throw 'Instrumented training must not claim to use the available profile' }
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

$validManifest = [IO.File]::ReadAllText("$pgoProfile.json")
foreach ($invalid in @('missing', '{invalid json', '{"runtime":"runtime","patches":"patches","game":"game","code":"other"}',
                      '{"runtime":"runtime","patches":"patches","game":"game"}')) {
    if ($invalid -eq 'missing') { Remove-Item -LiteralPath "$pgoProfile.json" }
    else { [IO.File]::WriteAllText("$pgoProfile.json", $invalid) }
    Configure -MaySkip
    if ($script:configured[-1] -match 'CXX_FLAGS=.*-fprofile-instr-use=') {
        throw 'Missing, malformed and other-game-code manifests must not apply a local PGO profile'
    }
    if ($script:configuredGameProfile.pgoApplied -or $null -ne $script:configuredGameProfile.appliedPgoHash) {
        throw 'Rejected profiles must not appear as applied in configure metadata'
    }
    if ([IO.File]::ReadAllText($pgoProfile) -ne 'profile-two') { throw 'Rejected profiles must remain untouched' }
}
# Same game code, earlier runtime/patches/game profile: still applied, clang drops the changed functions' counts.
[IO.File]::WriteAllText("$pgoProfile.json", '{"runtime":"old","patches":"old","game":"old","code":"code"}')
if ((Get-ProfileFit "$pgoProfile.json") -ne 'code') { throw 'A profile of this game code on an earlier runtime must fit by code' }
Configure -MaySkip
if (-not ($script:configured[-1] -match 'CXX_FLAGS=.*-fprofile-instr-use=') -or -not $script:configuredGameProfile.pgoApplied) {
    throw 'A profile trained on an earlier runtime must keep PGO for the unchanged game code'
}
if ($script:configured[-1] -match 'Werror=profile-instr-out-of-date' -or -not ($script:configured[-1] -match 'Wno-error=profile-instr-out-of-date')) {
    throw 'Functions changed since training must be a warning, never a build error'
}
# Exact text of the pinned clang (23.1.4) for one function changed under a 3-function profile.
$stale = [ordered]@{ objects = 0; functions = 0; mismatched = 0 }
Add-ProfileStaleWarning $stale 'warning: profile data may be out of date: of 3 functions, 1 has mismatched data that will be ignored [-Wprofile-instr-out-of-date]'
Add-ProfileStaleWarning $stale 'a.cpp: warning: profile data may be out of date: of 1200 functions, 40 have mismatched data that will be ignored [-Wprofile-instr-out-of-date]'
Add-ProfileStaleWarning $stale '1 warning generated.'
if ($stale.objects -ne 2 -or $stale.functions -ne 1203 -or $stale.mismatched -ne 41) { throw 'Stale-profile warnings must sum into the build coverage' }
Write-Host 'PASS: a profile of this game code survives runtime changes; stale functions are a counted warning'
[IO.File]::WriteAllText("$pgoProfile.json", $validManifest)
if ((Get-ProfileFit "$pgoProfile.json") -ne 'exact') { throw 'The trained identity must be an exact fit' }
Configure -MaySkip
if (-not ($script:configured[-1] -match 'CXX_FLAGS=.*-fprofile-instr-use=')) {
    throw 'A matching local profile must restore PGO and invalidate configure'
}
$savedRoot = $root
try {
    $root = $scratch
    $pgoDir = Split-Path $pgoProfile
    $shippedDir = Join-Path $root "games/$Game/pgo"
    New-Item -ItemType Directory -Force $shippedDir | Out-Null
    [IO.File]::WriteAllText((Join-Path $shippedDir 'shipped.profdata'), 'shipped-profile')
    [IO.File]::WriteAllText((Join-Path $shippedDir 'shipped.profdata.json'), $validManifest)
    [IO.File]::WriteAllText("$pgoProfile.json", '{invalid json')
    if (-not (Use-ReleaseProfile) -or [IO.File]::ReadAllText($pgoProfile) -ne 'shipped-profile') {
        throw 'A matching shipped profile must recover from an invalid local manifest'
    }
    if (-not (Use-ReleaseProfile)) { throw 'The restored profile must remain eligible for tune training reuse' }
} finally { $root = $savedRoot }
Write-Host 'PASS: PGO manifest rejection, preserved data, valid recovery and shipped-profile reuse'

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
