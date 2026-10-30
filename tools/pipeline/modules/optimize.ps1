# --- pgo: profile-guided optimisation (clang) -----------------------------------------------------------------------
# An instrumented copy of the game (its own build folder) plays the [optimize] pad script with the hardware renderer and
# the sound path running, like a player, but hidden and silent (GOW_WINDOW_HIDDEN, engine/patches/15; GOW_AUDIO=0 with
# GOW_AUDIO_PCM=NUL keeps the audio stream paced at volume 0); closing its window writes the profile (engine/patches/12),
# which is merged into gow.profdata and used by every later clang build. A new recompile leaves it partly stale (those
# functions are just not profiled).
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
               PS2X_GS_WORKER = '1'; GOW_GS_FINISH_ASINCRONO = '1'; GOW_WINDOW_HIDDEN = '1'
               TOBIICHI_PANORAMICO = '16:9'; TOBIICHI_FXAA = '1'; PS2X_GS_HW_SCALE = '2'
               GOW_VU1N_X64 = '1'; GOW_AUDIO = '0'; GOW_AUDIO_PCM = 'NUL'; GOW_PAD_GUION = $prof.optimize.pad_script }
    if (Get-ChildItem -Path $vu1 -Filter *.bin -ErrorAction SilentlyContinue | Select-Object -First 1) { $vars.GOW_VU1_CAPTURA = $vu1 }
    Invoke-GameRecording (Join-Path $genBld 'ps2xRuntime/ps2EntryRunner.exe') $elf $secs $vars 60000
    $raw = @(Get-ChildItem $pgoDir -Filter '*.profraw' | Where-Object Length -gt 0)
    if (-not $raw) { throw 'the instrumented game wrote no profile' }
    Native (Join-Path $script:llvmBin 'llvm-profdata.exe') (@('merge', '-o', $pgoProfile) + @($raw.FullName)) 'llvm-profdata merge'
    $raw | Remove-Item
    Write-Host ("profile: {0} ({1:N0} MB)" -f $pgoProfile, ((Get-Item $pgoProfile).Length / 1MB))
    Step "rebuild with the profile ($Config, clang)"
    Configure -MaySkip
    Build-Game
}

# --- optimize / native ----------------------------------------------------------------------------------------------
if ($Stages -contains 'optimize') {
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
if ($Stages -contains 'optimize' -or $Stages -contains 'native') {
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

