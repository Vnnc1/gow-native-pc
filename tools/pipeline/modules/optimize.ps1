# --- pgo: profile-guided optimisation (clang) -----------------------------------------------------------------------
# An instrumented copy of the game (its own build folder) plays the [optimize] pad script with the hardware renderer and
# the sound path running, like a player, but hidden and silent (GOW_WINDOW_HIDDEN, engine/patches/15; GOW_AUDIO=0 with
# GOW_AUDIO_PCM=NUL keeps the audio stream paced at volume 0); closing its window writes the profile (engine/patches/12),
# which is merged into gow.profdata and used by later clang builds with a matching manifest. Unmatched profiles stay
# on disk but are not applied automatically; a fitting shipped profile or new training restores PGO.
# A launcher update that changed the runtime patches marks the profile stale (data\pgo-stale.txt, tools/pipeline/update.ps1;
# the launcher then recommends this step again). A new profile clears it when it was trained on the current runtime: this
# run fetched it, or no rebuild after an update is pending.
# The same condition says what the new profile was trained on: the current runtime gets a manifest (Write-ProfileManifest,
# game.ps1: what lets a configure, and the release package, recognise it), an older one none.
function Clear-StaleProfile {
    if (($Stages -contains 'fetch') -or -not (Test-Path (Join-Path $root 'data\needs-rebuild.txt'))) {
        Remove-Item (Join-Path $root 'data\pgo-stale.txt') -ErrorAction SilentlyContinue
        Write-ProfileManifest 'trained'
    }
    else { Remove-Item "$pgoProfile.json" -ErrorAction SilentlyContinue }
}
if ($Stages -contains 'pgo') {
    $genBld = "$bld-pgogen"
    Step 'profile-guided optimisation: instrumented build'
    Configure $genBld 'generate' -MaySkip
    Build-Game $genBld
    $secs = if ($Seconds -gt 0) { $Seconds } else { [int]$prof.optimize.seconds }
    Step "profile-guided optimisation: the game plays itself for $secs s (hidden, in the background)"
    $elf = (Languages).recompile_elf
    New-Item -ItemType Directory -Force $pgoDir | Out-Null
    Get-ChildItem $pgoDir -Filter '*.profraw' -ErrorAction SilentlyContinue | Remove-Item
    $vars = @{ LLVM_PROFILE_FILE = (Join-Path $pgoDir 'run-%p.profraw'); GOW_SKIP_FMV = '1'; GOW_PAD_TEST = '1'; GOW_PAD_TEST_NO_CAPTURE = '1'
               PS2X_GS_WORKER = '1'; GOW_GS_FINISH_ASINCRONO = '1'; GOW_GS_EARLY_FINISH = '1'; GOW_WINDOW_HIDDEN = '1'
               TOBIICHI_PANORAMICO = '16:9'; TOBIICHI_FXAA = '1'; PS2X_GS_HW_SCALE = '2'
               GOW_VU1_FAST = '0'; GOW_VU1N_X64 = '1'; GOW_AUDIO = '0'; GOW_AUDIO_PCM = 'NUL'; GOW_PAD_GUION = $prof.optimize.pad_script }
    if (Get-ChildItem -Path $vu1 -Filter *.bin -ErrorAction SilentlyContinue | Select-Object -First 1) { $vars.GOW_VU1_CAPTURA = $vu1 }
    Invoke-GameRecording (Join-Path $genBld 'ps2xRuntime/ps2EntryRunner.exe') $elf $secs $vars 60000
    # Second segment: the title / legal / menu path. The pad script reaches it first, but 240 s of ship deck is ~95 % of
    # the sample, so a short dedicated run keeps those functions represented (and proves the profile covers both paths).
    $menuVars = $vars.Clone()
    $menuVars.GOW_PAD_GUION = '4:start,8:circulo,12:circulo'
    Invoke-GameRecording (Join-Path $genBld 'ps2xRuntime/ps2EntryRunner.exe') $elf ([math]::Max(10, [int]($secs / 20))) $menuVars 60000
    $raw = @(Get-ChildItem $pgoDir -Filter '*.profraw' | Where-Object Length -gt 0)
    if (-not $raw) { throw 'the instrumented game wrote no profile' }
    Native (Join-Path $script:llvmBin 'llvm-profdata.exe') (@('merge', '-o', $pgoProfile) + @($raw.FullName)) 'llvm-profdata merge'
    $raw | Remove-Item
    Write-Host ("profile: {0} ({1:N0} MB)" -f $pgoProfile, ((Get-Item $pgoProfile).Length / 1MB))
    Show-ProfileCoverage
    Clear-StaleProfile
    Step "rebuild with the profile ($Config, clang)"
    Configure -MaySkip
    Build-Game
}

# --- tune: first-play preparation and profile-guided optimisation in one pass -----------------------------------------
# The install's former path built the game, recorded VU1 code, rebuilt, then (pgo) built an instrumented copy, played it
# again and rebuilt once more: four builds and two recorded runs. Here one instrumented build plays the game once,
# recording the VU1 micro-memories and IOP modules (as optimize) and the profile (as pgo) together; one final build
# uses both. VU1 blocks first met in this run are not in the profile (they are compiled from it afterwards).
# With a profile that already fits this runtime and game code (the release's one, games/<id>/pgo/shipped.profdata, or an
# earlier training: Use-ReleaseProfile in game.ps1) there is nothing to train: the game is built once with it and the
# optimize stage below records the VU1 / IOP code on that build (the install then compiles the game once, not twice).
$tuneWithProfile = $false
if ($Stages -contains 'tune' -and (Use-ReleaseProfile)) {
    Step "rebuild with the profile ($Config, clang): the profile fits this runtime and game code, no training run"
    Configure -MaySkip
    Build-Game
    $tuneWithProfile = $true
}
if ($Stages -contains 'tune' -and -not $tuneWithProfile) {
    $genBld = "$bld-pgogen"
    Step 'profile-guided optimisation: instrumented build (also records VU1 code)'
    Configure $genBld 'generate' -MaySkip
    Build-Game $genBld
    $secs = if ($Seconds -gt 0) { $Seconds } else { [int]$prof.optimize.seconds }
    Step "profile-guided optimisation: the game plays itself for $secs s (hidden, records VU1 code and the profile)"
    $elf = (Languages).recompile_elf
    New-Item -ItemType Directory -Force $vu1, $iopMods, $pgoDir | Out-Null
    Get-ChildItem $pgoDir -Filter '*.profraw' -ErrorAction SilentlyContinue | Remove-Item
    $vars = @{ LLVM_PROFILE_FILE = (Join-Path $pgoDir 'run-%p.profraw'); GOW_SKIP_FMV = '1'; GOW_PAD_TEST = '1'; GOW_PAD_TEST_NO_CAPTURE = '1'
               PS2X_GS_WORKER = '1'; GOW_GS_FINISH_ASINCRONO = '1'; GOW_GS_EARLY_FINISH = '1'; GOW_WINDOW_HIDDEN = '1'
               TOBIICHI_PANORAMICO = '16:9'; TOBIICHI_FXAA = '1'; PS2X_GS_HW_SCALE = '2'
               GOW_VU1_FAST = '0'; GOW_VU1N_X64 = '1'; GOW_AUDIO = '0'; GOW_AUDIO_PCM = 'NUL'; GOW_PAD_GUION = $prof.optimize.pad_script
               GOW_VU1_CAPTURA = $vu1; PS2X_IOP_DUMP_MODULES = $iopMods; GOW_VU1_CAPTURE_MISSES = '1' }
    Invoke-GameRecording (Join-Path $genBld 'ps2xRuntime/ps2EntryRunner.exe') $elf $secs $vars 60000
    $raw = @(Get-ChildItem $pgoDir -Filter '*.profraw' | Where-Object Length -gt 0)
    if (-not $raw) { throw 'the instrumented game wrote no profile' }
    Native (Join-Path $script:llvmBin 'llvm-profdata.exe') (@('merge', '-o', $pgoProfile) + @($raw.FullName)) 'llvm-profdata merge'
    $raw | Remove-Item
    Write-Host ("profile: {0} ({1:N0} MB)" -f $pgoProfile, ((Get-Item $pgoProfile).Length / 1MB))
    Show-ProfileCoverage
    Clear-StaleProfile
    Step 'native VU1 and IOP code'
    $nVu1 = @(Get-ChildItem $vu1 -Filter *.bin -ErrorAction SilentlyContinue).Count
    $nIop = @(Get-ChildItem $iopMods -Filter *.bin -ErrorAction SilentlyContinue).Count
    Write-Host "recorded: $nVu1 VU1 micro-memories, $nIop IOP modules"
    if ($nIop -gt 0) { Native $python @('-I', (Join-Path $rt $prof.runtime.iop_native_generator), $iopMods, (Join-Path $rec 'ps2xIOP\src\native')) 'IOP native code' }
    Step "rebuild with the profile ($Config, clang)"
    Configure -MaySkip
    Build-Game
    Set-Content -Path (Join-Path $data 'native.stamp') -Value "$nVu1" -Encoding ASCII
}

# --- optimize / native ----------------------------------------------------------------------------------------------
if ($Stages -contains 'optimize' -or $tuneWithProfile) {
    $secs = if ($Seconds -gt 0) { $Seconds } else { [int]$prof.optimize.seconds }
    Step "record: the game plays itself for $secs s (hidden, in the background)"
    Need $runnerExe 'built game (run the build stage)'
    $elf = (Languages).recompile_elf
    New-Item -ItemType Directory -Force $vu1, $iopMods | Out-Null
    # The render-target renderer as the player has it (it has no on/off switch and no shader cache). The window stays
    # hidden (engine/patches/15): the GPU draws as usual, nothing shows on the desktop and no key can reach the game
    $vars = @{ GOW_VU1_CAPTURA = $vu1; PS2X_IOP_DUMP_MODULES = $iopMods; GOW_SKIP_FMV = '1'; GOW_PAD_TEST = '1'; GOW_AUDIO = '0'
               GOW_PAD_TEST_NO_CAPTURE = '1'; PS2X_GS_WORKER = '1'; GOW_GS_FINISH_ASINCRONO = '1'
               GOW_WINDOW_HIDDEN = '1'; GOW_VU1N_X64 = '1'; GOW_VU1_CAPTURE_MISSES = '1'; GOW_PAD_GUION = $prof.optimize.pad_script }
    Invoke-GameRecording $runnerExe $elf $secs $vars

}
if ($Stages -contains 'optimize' -or $Stages -contains 'native' -or $tuneWithProfile) {
    Step 'native VU1 and IOP code'
    $nVu1 = @(Get-ChildItem $vu1 -Filter *.bin -ErrorAction SilentlyContinue).Count
    $nIop = @(Get-ChildItem $iopMods -Filter *.bin -ErrorAction SilentlyContinue).Count
    Write-Host "recorded: $nVu1 VU1 micro-memories, $nIop IOP modules"
    if ($nIop -gt 0) { Native $python @('-I', (Join-Path $rt $prof.runtime.iop_native_generator), $iopMods, (Join-Path $rec 'ps2xIOP\src\native')) 'IOP native code' }
    Configure -MaySkip
    Step "rebuild ($Config)"
    Build-Game
    Set-Content -Path (Join-Path $data 'native.stamp') -Value "$nVu1" -Encoding ASCII
}

# --- pgo-check: prove that a build really uses a profile that fits it -------------------------------------------------
# Clang silently accepts a stale or empty profile (options can disable the warnings), so a "PGO build" can be a plain
# build. This stage is the single place that checks, in order: the manifest identity (runtime, patches, game code,
# source tree, unity batch), the profile's function coverage, the compile flags in build.ninja (use, not generate),
# and the linked runner (no profiling runtime).
function Invoke-PgoCheck {
    Need $pgoProfile "profile-guided data (run the pgo stage)"
    if (-not (Test-ProfileManifest "$pgoProfile.json")) {
        throw 'the profile does not fit this runtime/game code (stale manifest): re-run the pgo stage'
    }
    Show-ProfileCoverage
    $ninja = Join-Path $bld 'build.ninja'
    Need $ninja "configured build folder ($bld)"
    if (-not (Select-String -Path $ninja -SimpleMatch '-fprofile-instr-use' -List)) { throw "$bld was built without the profile (no -fprofile-instr-use)" }
    if (Select-String -Path $ninja -SimpleMatch '-fprofile-instr-generate' -List) { throw "$bld is the instrumented (generate) build, not the profile-use build" }
    $hash = (Get-FileHash $pgoProfile -Algorithm SHA256).Hash
    if (-not (Select-String -Path $ninja -SimpleMatch "-DGOW_PGO_REVISION=$hash" -List)) { throw 'the build used a different profile (stale configure): re-run configure' }
    $runner = Join-Path $bld 'ps2xRuntime\ps2EntryRunner.exe'
    Need $runner "runner ($runner)"
    $nmPath = Join-Path $script:llvmBin 'llvm-nm.exe'
    if (Test-Path $nmPath) {
        $nm = & $nmPath $runner 2>$null | Out-String
        # profile-instr-generate links the profiling runtime, which defines __llvm_profile_write_file (T). A profile-use
        # build has no definition (the runtime's own write hook stays undefined/weak, engine/patches/12).
        if ($nm -match '(?m)^\s*\S+\s+[Tt]\s+__llvm_profile_write_file') { throw 'the runner links the profiling runtime (instrumented build)' }
    }
    $manifest = Get-Content "$pgoProfile.json" -Raw | ConvertFrom-Json
    Write-Host ("pgo check: profile fits ({0} source hash {1}..., unity batch {2}), used by the build, no instrumentation runtime" -f
        $pgoProfile, $manifest.src.Substring(0, [math]::Min(12, $manifest.src.Length)), $manifest.unity)
}
if ($Stages -contains 'pgo-check') { Step 'pgo check'; Invoke-PgoCheck }

