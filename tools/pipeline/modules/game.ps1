# --- profile-guided data shipped with the release -------------------------------------------------------------------
# The generated game code depends only on the runtime (engine/runtime.toml, engine/patches), the game profile
# (games/<id>, without its pgo folder) and the code of the recompiled executable: its .text section (a fan translation
# changes text and data, not code: the PT-BR translation's .text is byte-identical to the USA one). A profile trained on
# one installation therefore fits every installation with the same identity. A trained profile gets a manifest
# (<profile>.json) with that identity; the release package ships one (games/<id>/pgo/shipped.profdata + .json) and a
# configure without a fitting local profile takes it: the install then needs no instrumented build and no training run.
function Get-ElfTextHash([string]$elf) {
    $d = [IO.File]::ReadAllBytes($elf)
    $shoff = [BitConverter]::ToUInt32($d, 0x20)
    $entsize = [BitConverter]::ToUInt16($d, 0x2E); $count = [BitConverter]::ToUInt16($d, 0x30); $strndx = [BitConverter]::ToUInt16($d, 0x32)
    $strings = [BitConverter]::ToUInt32($d, $shoff + $strndx * $entsize + 16)
    for ($i = 0; $i -lt $count; $i++) {
        $h = $shoff + $i * $entsize
        $at = $strings + [BitConverter]::ToUInt32($d, $h)
        $name = [Text.Encoding]::ASCII.GetString($d, $at, [Array]::IndexOf($d, [byte]0, $at) - $at)
        if ($name -eq '.text') {
            $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($d, [BitConverter]::ToUInt32($d, $h + 16), [BitConverter]::ToUInt32($d, $h + 20))
            return [BitConverter]::ToString($hash).Replace('-', '')
        }
    }
    throw "no .text section in $elf"
}
function Get-ProfileIdentity {
    $sha = { param($text) [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($text))).Replace('-', '') }
    # ordinal order on every host (Sort-Object follows the system culture: another Windows language would hash differently)
    $patches = (Get-RuntimePatches | ForEach-Object { "$($_.Name):$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)" }) -join ';'
    $gameDir = Join-Path $root "games\$Game"
    [string[]]$files = @(Get-ChildItem $gameDir -Recurse -File | Where-Object { $_.FullName -notlike (Join-Path $gameDir 'pgo\*') } |
        ForEach-Object { $_.FullName.Substring($gameDir.Length + 1) })
    [Array]::Sort($files, [StringComparer]::Ordinal)
    $profileFiles = ($files | ForEach-Object { "${_}:$((Get-FileHash (Join-Path $gameDir $_) -Algorithm SHA256).Hash)" }) -join ';'
    return [ordered]@{
        runtime = (Get-FileHash (Join-Path $root 'engine\runtime.toml') -Algorithm SHA256).Hash
        patches = & $sha $patches
        game = & $sha $profileFiles
        code = Get-ElfTextHash (Languages).recompile_elf
    }
}
# $true when the manifest's identity is this installation's (no prepared disc yet: $false)
function Test-ProfileManifest([string]$manifest) {
    if (-not (Test-Path $manifest)) { return $false }
    try {
        $id = Get-ProfileIdentity
        $m = Get-Content $manifest -Raw | ConvertFrom-Json
    } catch { return $false }
    return ($m.runtime -eq $id.runtime) -and ($m.patches -eq $id.patches) -and ($m.game -eq $id.game) -and ($m.code -eq $id.code)
}
function Write-ProfileManifest([string]$source) {
    $m = Get-ProfileIdentity
    $m.source = $source
    $m.created_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    [IO.File]::WriteAllText("$pgoProfile.json", ($m | ConvertTo-Json))
}
# $true when the local profile fits this installation, after taking the release's one if the local one did not
function Use-ReleaseProfile {
    if ((Test-Path $pgoProfile) -and (Test-ProfileManifest "$pgoProfile.json")) { return $true }
    $shipped = Join-Path $root "games\$Game\pgo\shipped.profdata"
    if (-not ((Test-Path $shipped) -and (Test-ProfileManifest "$shipped.json"))) { return $false }
    New-Item -ItemType Directory -Force $pgoDir | Out-Null
    Copy-Item $shipped $pgoProfile -Force
    Copy-Item "$shipped.json" "$pgoProfile.json" -Force
    Remove-Item (Join-Path $root 'data\pgo-stale.txt') -ErrorAction SilentlyContinue
    Write-Host "profile-guided: the release's profile fits this runtime and game code ($pgoProfile)"
    return $true
}

# --- configure ------------------------------------------------------------------------------------------------------
# -MaySkip: when the cmake arguments and the configure-time inputs are those of the last configure of $dir (signature in
# $dir\gow-configure.sig), the configure is skipped: Ninja itself re-runs CMake when a CMakeLists.txt or a CONFIGURE_DEPENDS
# glob (recorded microcode, runtime and IOP native sources) changes. The only configure-time input outside those is whether
# vu1n_heads.txt exists (the VU1 generator rule depends on it only then). The explicit configure stage always runs.
function Configure([string]$dir = $bld, [string]$pgo = 'auto', [switch]$MaySkip) {
    $script:configuredGameProfile = $null
    Use-Toolchain
    Need (Join-Path $rec 'CMakeLists.txt') 'runtime (run the fetch stage)'
    $profileReady = $false
    if ($pgo -eq 'auto') {
        $profileReady = if ($dir -eq $bld) { Use-ReleaseProfile } else {
            (Test-Path $pgoProfile) -and (Test-ProfileManifest "$pgoProfile.json")
        }
        if (-not $profileReady -and (Test-Path $pgoProfile)) {
            Write-Host '@@status local PGO profile has no matching manifest; building without it (profile preserved)'
        }
    }
    $ltcgValue = if ($Ltcg) { 'ON' } else { 'OFF' }
    $pdbValue = if ($Pdb) { 'ON' } else { 'OFF' }
    $extra = @()
    if (Get-ChildItem -Path $vu1 -Filter *.bin -ErrorAction SilentlyContinue | Select-Object -First 1) {
        # the runtime's CMake reads the extra VU1 block heads from vu1n_heads.txt next to the capture folder: the profile's
        # list plus the entries the game met without native code while recording (vu1n_heads_seen.txt, see
        # VU1NativeAccess::recordMissHead); written only when the set changes (a change regenerates the native VU1 code)
        $headList = @()
        if ($prof.runtime.vu1_native_heads) { $headList += Join-Path $rt $prof.runtime.vu1_native_heads }
        $headList += Join-Path $vu1 'vu1n_heads_seen.txt'
        $headSet = @($headList | Where-Object { Test-Path $_ } | ForEach-Object { Get-Content $_ } |
            ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ -match '^[0-9a-f]+$' } | Sort-Object -Unique)
        $headsDst = Join-Path $data 'vu1n_heads.txt'
        $headsText = ($headSet -join "`n") + "`n"
        if (-not ((Test-Path $headsDst) -and ((Get-Content $headsDst -Raw) -eq $headsText))) {
            [IO.File]::WriteAllText($headsDst, $headsText)
            Write-Host "VU1 block heads: $($headSet.Count)"
        }
        $extra += "-DPS2X_VU1_MICROCODE_DIR=$(Barra $vu1)"
        $extra += "-DPS2X_VU1_GENERATOR_SOURCE=$(Barra (Join-Path $rt $prof.runtime.vu1_generator))"
        $extra += "-DPS2X_VU1N_GEN_OVERRIDE=$(Barra (Join-Path $rt $prof.runtime.vu1_native_generator))"
    }
    # Generated EE code requires wrapping integers and conservative aliasing.
    $flags = '-fno-strict-aliasing -fwrapv -fno-math-errno -fno-trapping-math'
    # AVX2-class builds are explicit; keep the runtime's portable baseline available.
    $cpuArch = if ($CpuTarget -eq 'x86-64-v3') { 'x86-64-v3' } else { 'x86-64-v2' }
    $extra += "-DPS2X_CPU_ARCH=$cpuArch"
    $flags += " -march=$cpuArch"
    $link = '-static'
    if ($Pdb) {
        # The upstream PS2X_RELEASE_PDB option only handles MSVC. llvm-mingw needs CodeView + lld's PDB output.
        $flags += ' -g -gcodeview'
        $link += ' -Wl,--pdb='
    }
    if ($Ltcg) { $link += " -Wl,--thinlto-jobs=$([math]::Max(1, $jobs))" }
    if ($pgo -eq 'generate') {
        $flags += ' -fprofile-instr-generate'; $link += ' -fprofile-instr-generate'
        # Keep the configuration's -O3 here. A -O1 training build (2.2x faster to compile) gave a profile whose final
        # build was measured slower: 45.0 vs 49.7 FPS mean on the save route, 3 of 3 alternating pairs (2026-10-30).
    }
    elseif ($profileReady) {
        $profileHash = (Get-FileHash $pgoProfile -Algorithm SHA256).Hash
        Write-Host "profile-guided: $pgoProfile ($profileHash)"
        # The digest changes Ninja commands and cache keys when the same profile path gets new contents.
        $flags += " -fprofile-instr-use=`"$(Barra $pgoProfile)`" -DGOW_PGO_REVISION=$profileHash -Wno-profile-instr-unprofiled -Wno-profile-instr-out-of-date"
    }
    # Always explicit: a value once passed stays in CMakeCache.txt, so an omitted one would silently keep it.
    $extra += @('-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG', '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG')
    $extra += Clang-CMakeArgs -NoCache:($pgo -eq 'generate')
    # The pipeline owns launcher selection, including disabling cache for instrumented objects.
    # The upstream numeric -flto=N job limit is GCC-only. lld's job limit above is used for Clang.
    $extra += @('-DPS2X_ENABLE_SCCACHE=OFF', '-DPS2X_LTO_JOBS=', "-DCMAKE_C_FLAGS=$flags", "-DCMAKE_CXX_FLAGS=$flags", "-DCMAKE_EXE_LINKER_FLAGS=$link")
    $extra += "-DPython3_EXECUTABLE=$(Barra $python)"
    # Reusing pinned dependencies needs no network update. An explicit fetch run permits new revisions again.
    # Initial dependency downloads still work with UPDATES_DISCONNECTED (unlike FULLY_DISCONNECTED).
    $dependencyUpdates = if ($Stages -contains 'fetch') { 'OFF' } else { 'ON' }
    $extra += "-DFETCHCONTENT_UPDATES_DISCONNECTED=$dependencyUpdates"
    # Another build folder (the instrumented one) reads the dependencies the main folder already cloned: a fresh folder
    # otherwise clones them again (raylib and toml11 are full clones, ~1 GB), on one core and the network
    if ($dir -ne $bld) {
        foreach ($src in @(Get-ChildItem (Join-Path $bld '_deps') -Directory -Filter '*-src' -ErrorAction SilentlyContinue)) {
            $extra += "-DFETCHCONTENT_SOURCE_DIR_$($src.Name.Substring(0, $src.Name.Length - 4).ToUpper())=$(Barra $src.FullName)"
        }
    }
    $cmakeArgs = @('-S', $rec, '-B', $dir, '-G', 'Ninja', "-DCMAKE_BUILD_TYPE=$Config", "-DPS2X_RELEASE_LTCG=$ltcgValue", "-DPS2X_RELEASE_PDB=$pdbValue",
        '-DPS2X_ENABLE_RUNTIME_LOGS=OFF', '-DPS2X_ENABLE_AGRESSIVE_LOGS=OFF', '-DPS2X_ENABLE_IOP_RPC_TRACE=OFF',
        '-DPS2X_ENABLE_FFMPEG=OFF',
        '-DPS2X_BUILD_STUDIO=OFF', '-DPS2X_BUILD_ANALYZER=OFF', '-DPS2X_BUILD_TEST=OFF', '-DPS2X_SHOW_WINDOWS_CONSOLE=OFF',
        "-DPS2X_RUNNER_UNITY_BUILD_BATCH_SIZE=$(if ($prof.build -and $prof.build.unity_batch -and $ramGb -ge 14) { $prof.build.unity_batch } else { 8 })") + $extra
    $sigFile = Join-Path $dir 'gow-configure.sig'
    $sigText = ($cmakeArgs -join "`n") + "`nheads=$(Test-Path (Join-Path $data 'vu1n_heads.txt'))`nrec=$(Barra $rec)"
    $sha = [Security.Cryptography.SHA256]::Create()
    $sig = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($sigText))) -replace '-', '').ToLower()
    $sha.Dispose()
    $configuredProfile = [ordered]@{buildRoot=$dir; mode=$(if ($pgo -eq 'generate') { 'generate' } elseif ($profileReady) { 'use' } else { 'off' });
        pgoApplied=[bool]$profileReady; appliedPgoHash=$(if ($profileReady) { $profileHash } else { $null })}
    if ($MaySkip -and (Test-Path (Join-Path $dir 'build.ninja')) -and (Test-Path (Join-Path $dir 'CMakeCache.txt')) -and
        (Test-Path $sigFile) -and ((Get-Content $sigFile -Raw).Trim() -eq $sig)) {
        Write-Host 'cmake configure: inputs unchanged, skipped (Ninja re-runs CMake itself when CMake files or globbed sources change)'
        $script:configuredGameProfile = $configuredProfile
        return
    }
    Remove-Item $sigFile -ErrorAction SilentlyContinue # a failed configure must not leave the old signature behind
    Native 'cmake' $cmakeArgs 'cmake configure'
    [IO.File]::WriteAllText($sigFile, $sig)
    $script:configuredGameProfile = $configuredProfile
}
if ($Stages -contains 'configure') { Step "configure ($Config, $bld)"; Configure }

# --- recompile ------------------------------------------------------------------------------------------------------
if ($Stages -contains 'recomp') {
    Step 'recompile the executable'
    Use-Toolchain
    Need (Join-Path $bld 'CMakeCache.txt') 'configured build folder (run the configure stage)'
    Configure -MaySkip
    Native 'ninja' @('-C', $bld, "-j$jobs", 'ps2_recomp') 'ps2_recomp build'
    $recompArgs = @('-I', (Join-Path $root 'tools/pipeline/recompile.py'), 'recomp', '--root', $root,
        '--game', $Game, '--build', $bld, '--codegen', $Codegen)
    if ($ForceRecomp) { $recompArgs += '--force' }
    Native $python $recompArgs 'EE code generation'
}

if ($Stages -contains 'sync') {
    Step 'generated code into the runner'
    Native $python @('-I', (Join-Path $root 'tools/pipeline/recompile.py'), 'sync', '--root', $root, '--game', $Game) 'generated code synchronization'
}

# --- build ----------------------------------------------------------------------------------------------------------
. (Join-Path $PSScriptRoot 'build-progress.ps1')
function Build-Game([string]$dir = $bld) {
    Use-Toolchain
    Need (Join-Path $dir 'CMakeCache.txt') 'configured build folder (run the configure stage)'
    $profileMode = if ($dir -eq "$bld-pgogen") { 'generate' } else { 'auto' }
    Configure $dir $profileMode -MaySkip
    $buildProfile = $script:configuredGameProfile
    $log = Join-Path $logs 'build.log'
    Write-Host "$jobs compilers in parallel"
    $ErrorActionPreference = 'Continue'
    $writer = New-Object IO.StreamWriter($log, $false, (New-Object Text.UTF8Encoding($false)))
    $writer.AutoFlush = $true
    $progressState = New-GameBuildProgress $dir
    $errors = 0
    & ninja -C $dir "-j$jobs" ps2EntryRunner 2>&1 | ForEach-Object {
        $s = "$_"
        if ($s -eq 'System.Management.Automation.RemoteException') { return }
        $writer.WriteLine($s)
        $progress = Read-GameBuildProgress $progressState $s
        if ($progress) {
            if ($progress.changed) { Write-Host "@@progress $($progress.done) $($progress.total)" }
            if ($progress.linking) { Write-Host '@@status linking the executable' }
        }
        if ($s -match 'error C\d|error LNK|fatal error|FAILED:|error:') { if (++$errors -le 20) { Write-Host $s -ForegroundColor Red } }
    }
    $rc = $LASTEXITCODE
    $writer.Close()
    $ErrorActionPreference = 'Stop'
    if ($profileMode -ne 'generate') { Write-CompilerCacheStats 'game' }
    if ($rc -ne 0) { throw "build failed (rc=$rc), data\$Game\logs\build.log" }
    if ($null -ne $buildProfile) { $script:gameBuildProfiles.Add($buildProfile) }
    if ($dir -eq $bld) {
        [IO.File]::WriteAllText($toolchainFile, 'clang')
        [IO.File]::WriteAllText($buildRootFile, $BuildRoot)
        # a launcher update that changed the runtime patches asked for a rebuild (tools/pipeline/update.ps1): done once the
        # game was built from the runtime this run fetched (build, tune, optimize, pgo all end here), not by a build of
        # the runtime already on disk
        if ($Stages -contains 'fetch') { Remove-Item (Join-Path $root 'data\needs-rebuild.txt') -ErrorAction SilentlyContinue }
    }
    Write-Host "OK: $(Join-Path $dir 'ps2xRuntime\ps2EntryRunner.exe')"
    $bootFile = Join-Path $dir 'ps2xRuntime\gow-native.boot'
    $elf = (Languages).recompile_elf
    if ($dir -eq $bld -and $elf -and (Test-Path $elf) -and -not (Test-Path $bootFile)) {
        # A launcher session replaces these defaults with the selected disc and runtime settings.
        $bootText = "GOW_NATIVE_BOOT_V1`n$elf`nGOW_VU1N_X64=1`nGOW_VU1_CAPTURE_MISSES=1`nGOW_VU1_CAPTURA=$vu1`nPS2X_GS_WORKER=1`nGOW_GS_FINISH_ASINCRONO=1`nGOW_GS_EARLY_FINISH=1`nTOBIICHI_PANORAMICO=16:9`n"
        [IO.File]::WriteAllText($bootFile, $bootText, (New-Object Text.UTF8Encoding($false)))
    }
    # the background VU1 compiler (launcher: "Compile new areas while playing") builds modules with this compiler and the
    # build's flags; clang only (an MSVC game has another C++ library layout than llvm-mingw modules)
    if ($dir -eq $bld) {
        $jit = [ordered]@{ cxx = (Join-Path $script:llvmBin 'clang++.exe'); python = $python
                           generator = (Join-Path $rt $prof.runtime.vu1_native_generator)
                           flags = "-O3 -DNDEBUG -std=gnu++20 -march=native -ffp-contract=off -fno-strict-aliasing -fwrapv -I`"$(Barra (Join-Path $rec 'ps2xRuntime\include'))`"" }
        [IO.File]::WriteAllText((Join-Path $data 'vu1_jit.json'), ($jit | ConvertTo-Json))
    }
    # A successful no-op build emits no Ninja counter. Mark the step complete only after all work succeeded.
    Write-Host '@@progress 1 1'
}
if ($Stages -contains 'build') {
    Step "build the game ($Config, $Toolchain)"
    Build-Game
}

