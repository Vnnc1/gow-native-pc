$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$Stages = @()
. "$root/tools/pipeline/modules/common.ps1"
. "$root/tools/pipeline/modules/game.ps1"
$scratch = Join-Path ([IO.Path]::GetTempPath()) ("gow-pgo-test-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $scratch | Out-Null
$bld = "$scratch/build"
$rec = "$scratch/runtime"
New-Item -ItemType Directory -Force $rec | Out-Null
[IO.File]::WriteAllText("$rec/CMakeLists.txt", "# synthetic")
$data = $scratch
$pgoProfile = "$scratch/stale.profdata"
$Game = 'gow1'
$Config = 'Release'
$ramGb = 8
$CompilerCache = 'none'
$CpuTarget = 'portable'
$jobs = 1
$script:cacheExe = ''
$prof = [pscustomobject]@{build=[pscustomobject]@{unity_batch=16}}
function Use-Toolchain {}
function Clang-CMakeArgs { @() }
function Barra($p) { "$p".Replace('\','/') }
function Get-ProfileIdentity { @{runtime='current';patches='current';game='current';code='current';src='current';unity=8} }
function Native($exe,[string[]]$a,$what) { $script:captured=$a; New-Item -ItemType Directory -Force $bld | Out-Null }
[IO.File]::WriteAllText($pgoProfile,'synthetic stale profile, not passed to any compiler')
[IO.File]::WriteAllText("$pgoProfile.json",'{"runtime":"old"}')
Configure
if ($script:captured -match 'fprofile-instr-use') { throw 'Stale PGO was applied' }; Write-Output 'PASS: stale profile is not applied'
# Exercise the real pgo-check path with valid eligibility/coverage stubs.
. "$root/tools/pipeline/modules/optimize.ps1"
function Test-ProfileManifest { $true }
function Show-ProfileCoverage {}
$hash = (Get-FileHash $pgoProfile).Hash
[IO.File]::WriteAllText("$bld/build.ninja", "-fprofile-instr-use=synthetic -DGOW_PGO_REVISION=$hash")
New-Item -ItemType Directory -Force "$bld/ps2xRuntime", "$scratch/bin" | Out-Null
[IO.File]::WriteAllText("$bld/ps2xRuntime/ps2EntryRunner.exe", 'synthetic, never executed')
[IO.File]::WriteAllText("$pgoProfile.json", '{"src":"current","unity":8}')
$script:llvmBin = "$scratch/bin"
Invoke-PgoCheck
Write-Output 'PASS: pgo-check accepts real file paths and matching profile hash'

Configure
if (-not ($script:captured -match 'fprofile-instr-use')) { throw 'Eligible profile was not applied' }
Write-Output 'PASS: eligible profile remains enabled'
