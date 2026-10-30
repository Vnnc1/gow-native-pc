$profileJson = & $python -I (Join-Path $root 'tools\pipeline\profile.py') $Game
if ($LASTEXITCODE -ne 0) { throw "no game profile '$Game' (games\$Game\game.toml)" }
$prof = $profileJson | Out-String | ConvertFrom-Json
if ($prof.status -eq 'planned') { throw "$($prof.title) is not supported yet (games\$Game\README.md)" }
$runtimeToml = Get-Content (Join-Path $root 'engine\runtime.toml') -Raw
$runtimeRepo = [regex]::Match($runtimeToml, '(?m)^repository\s*=\s*"([^"]+)"').Groups[1].Value
$runtimeCommit = [regex]::Match($runtimeToml, '(?m)^commit\s*=\s*"([^"]+)"').Groups[1].Value
$rt = Join-Path $root 'engine\runtime'
$rec = Join-Path $rt 'PS2Recomp'
$data = Join-Path $root "data\$Game"
$logs = Join-Path $data 'logs'
$gen = Join-Path $data 'recomp'
$vu1 = Join-Path $data 'vu1_capture'
$iopMods = Join-Path $data 'iop_modules'
# Build folder of this copy, remembered in data\build-root.txt (the launcher reads it too). C:\gow-build unless another
# copy (a development checkout, a second installation) already configured it: CMake refuses a cache made from another
# source folder, so this copy then takes C:\gow-build-<hash of its folder>.
$buildRootFile = Join-Path $root 'data\build-root.txt'
$md5 = [Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant()))
$ownRoot = 'C:\gow-build-' + (($md5[0..3] | ForEach-Object { $_.ToString('x2') }) -join '')
# a build folder configured from another copy's runtime (CMake refuses its cache)
function Test-ForeignCache([string]$folder) {
    $cache = Join-Path $folder 'CMakeCache.txt'
    if (-not (Test-Path $cache)) { return $false }
    $home_ = [regex]::Match((Get-Content $cache -Raw), '(?m)^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$').Groups[1].Value.Trim()
    return $home_ -ne (Barra $rec)
}
if (-not $BuildRoot -and (Test-Path $buildRootFile)) { $BuildRoot = (Get-Content $buildRootFile -Raw).Trim() }
if (-not $BuildRoot) {
    $BuildRoot = 'C:\gow-build'
    # every folder of the root (MSVC, clang, dev configuration) must be this copy's or unused
    foreach ($folder in @($BuildRoot, "$BuildRoot-clang", "$BuildRoot-dev", "$BuildRoot-dev-clang", "$BuildRoot-clang-pgogen", "$BuildRoot-verify-clang")) {
        if (Test-ForeignCache $folder) { $BuildRoot = $ownRoot; break }
    }
    New-Item -ItemType Directory -Force (Split-Path $buildRootFile) | Out-Null
    [IO.File]::WriteAllText($buildRootFile, $BuildRoot)
}
# Keep the existing clang build directory, but stop producing new MSVC game builds.
$toolchainFile = Join-Path $root 'data/toolchain.txt'
$oldToolchain = if (Test-Path $toolchainFile) { (Get-Content $toolchainFile -Raw).Trim() } else { '' }
if ($Toolchain -eq 'msvc' -or $oldToolchain -eq 'msvc') {
    Write-Host '@@status migrating this copy to clang; previous build files are preserved'
}
$Toolchain = 'clang'
$bld = if ($Config -eq 'Release') { "$BuildRoot-clang" } else { "$BuildRoot-dev-clang" }
# The recorded root can since have been taken by another copy (a test checkout configured C:\gow-build-clang): this copy
# moves to its own root, where the next build starts from scratch (a full build)
if ((Test-ForeignCache $bld) -or (Test-ForeignCache "$bld-pgogen")) {
    if ($BuildRoot -eq $ownRoot) { throw "$bld was configured from another copy of the project: delete that folder and run again" }
    Write-Host "build folder $bld belongs to another copy of the project: this copy now uses $ownRoot (the next build is a full one)"
    $bld = $bld.Replace($BuildRoot, $ownRoot)
    $BuildRoot = $ownRoot
    [IO.File]::WriteAllText($buildRootFile, $BuildRoot)
}
$pgoDir = Join-Path $root "data\$Game\pgo"
$pgoProfile = Join-Path $pgoDir 'gow.profdata'
$runnerExe = Join-Path $bld 'ps2xRuntime\ps2EntryRunner.exe'
New-Item -ItemType Directory -Force $data, $logs | Out-Null
# git settings for this process only (the user's git config is not changed): long paths (the dependencies'
# checkouts), and engine\runtime trusted as ours — on drives without file owners (exFAT/FAT32 USB disks, some network
# shares) git otherwise stops with "detected dubious ownership in repository"
$env:GIT_CONFIG_COUNT = '2'
$env:GIT_CONFIG_KEY_0 = 'core.longpaths'; $env:GIT_CONFIG_VALUE_0 = 'true'
$env:GIT_CONFIG_KEY_1 = 'safe.directory'; $env:GIT_CONFIG_VALUE_1 = (Barra $rt)
# parallel compilers: two logical cores stay free for Windows (a build on every core froze the machine), at most one
# compiler per 1.0 GB above 4 GB (paging defeats parallelism). Measured 2026-10-30 on the game build (unity batch 16,
# Release, PGO): 7 compilers used 3.4 GB together, the largest one 0.64 GB; register_functions.cpp, the only outlier,
# builds at -O1 since runtime patch 41. The former 1.6 GB per compiler left 16 GB machines at 7 of 18 usable cores.
$ramGb = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
$jobs = [int][math]::Max(1, [math]::Min([Environment]::ProcessorCount - 2, [math]::Floor(($ramGb - 4) / 1.0)))
# the whole pipeline (clang, ninja, python) runs below normal priority so the desktop stays usable; the recorded test
# game goes back to normal priority in the optimize stage
try { (Get-Process -Id $PID).PriorityClass = 'BelowNormal' } catch { }

