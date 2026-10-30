# --- fetch: the runtime -------------------------------------------------------------------------------------------
if ($Stages -contains 'fetch') {
    Step 'runtime (PS2Recomp + Tobiichi)'
    if (-not $git) { throw 'git not found: install Git for Windows' }
    if (-not (Test-Path (Join-Path $rec 'CMakeLists.txt'))) {
        Write-Host "cloning $runtimeRepo -> engine\runtime"
        Native $git @('clone', '--quiet', $runtimeRepo, $rt) 'git clone of the runtime'
    }
    $ErrorActionPreference = 'Continue'
    $head = & $git -C $rt rev-parse HEAD 2>$null
    $ErrorActionPreference = 'Stop'
    if ("$head".Trim() -ne $runtimeCommit) {
        $dirty = & $git -C $rt status --porcelain --untracked-files=no
        if ($dirty) { throw "engine\runtime has local changes and is not at ${runtimeCommit}: delete engine\runtime and run fetch again" }
        Native $git @('-C', $rt, 'fetch', '--quiet', 'origin') 'git fetch'
        Native $git @('-C', $rt, 'checkout', '--quiet', $runtimeCommit) 'git checkout'
    }
    # Which patches are in? Patches can touch the same file (01 and 07: ReleaseMode.cmake), so a per-patch reverse check
    # fails once a later one is in. Instead, in a temporary index (the files are not touched): the tree after 0..N
    # patches on the pinned commit, and the tree of the files as they are; the matching prefix tells what is left.
    $patches = @(Get-RuntimePatches)
    $index = Join-Path $env:TEMP "gow-patch-index-$PID"
    $oldIndex = $env:GIT_INDEX_FILE
    $ErrorActionPreference = 'Continue'
    try {
        $env:GIT_INDEX_FILE = $index
        & $git -C $rt read-tree HEAD
        $trees = @("$(& $git -C $rt write-tree)".Trim())
        foreach ($patch in $patches) {
            & $git -C $rt apply --cached $patch.FullName 2>$null
            if ($LASTEXITCODE -ne 0) { throw "patch $($patch.Name) does not apply to runtime commit $runtimeCommit" }
            $trees += "$(& $git -C $rt write-tree)".Trim()
        }
        $touched = @(& $git -C $rt diff --name-only HEAD $trees[-1])
        & $git -C $rt read-tree HEAD
        & $git -C $rt add -u 2>$null
        # New files in a later patch may not exist yet. One absent path makes `git add` reject the whole list.
        $present = @($touched | Where-Object { Test-Path (Join-Path $rt $_) })
        if ($present.Count) { & $git -C $rt add -A -- $present 2>$null }
        $current = "$(& $git -C $rt write-tree)".Trim()
    }
    finally {
        $env:GIT_INDEX_FILE = $oldIndex
        Remove-Item $index -Force -ErrorAction SilentlyContinue
        $ErrorActionPreference = 'Stop'
    }
    $done = [array]::IndexOf($trees, $current)
    if ($done -lt 0) { throw 'engine\runtime differs from the patch chain: preserve local work and compare it with engine\patches before retrying' }
    for ($i = 0; $i -lt $patches.Count; $i++) {
        if ($i -lt $done) { Write-Host "patch $($patches[$i].Name): applied"; continue }
        Native $git @('-C', $rt, 'apply', $patches[$i].FullName) "patch $($patches[$i].Name)"
        Write-Host "patch $($patches[$i].Name): applied now"
    }
}

# --- discs ----------------------------------------------------------------------------------------------------------
if ($Stages -contains 'discs') {
    Step 'discs'
    $list = @($Discs -split '\|' | Where-Object { $_ })
    if (-not $list) { throw 'no disc given (-Discs "<iso>|<iso>")' }
    Native $python (@('-I', (Join-Path $root 'tools\disc\prepare.py'), '--game', $Game, '--data', (Join-Path $root 'data')) + $list) 'disc preparation'
}

# --- vu1disc: VU1 microcode from the disc (experimental) -------------------------------------------------------------
if ($Stages -contains 'vu1disc') {
    Step 'VU1 microcode from the disc'
    $genPy = Join-Path $rt $prof.runtime.vu1_native_generator
    Need $genPy 'runtime (run the fetch stage)'
    $discDir = Split-Path (Languages).recompile_elf
    New-Item -ItemType Directory -Force $vu1 | Out-Null
    Native $python @('-I', (Join-Path $root 'tools\disc\vu1_from_disc.py'), '--game', $Game, '--gen', $genPy, $discDir, $vu1) 'VU1 microcode from the disc'
}

