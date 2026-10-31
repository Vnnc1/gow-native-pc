# tools/pipeline/patches.ps1 on a small throwaway runtime: the stack is rebased onto a newer upstream commit, then
# exported. A patch that only moved keeps its file byte for byte, one whose context changed is rewritten under its
# header, one already upstream is removed, and runtime.toml follows the new base.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script = Join-Path $root 'tools/pipeline/patches.ps1'
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('gow-patch-stack-' + [guid]::NewGuid().ToString('N'))
$utf8 = New-Object Text.UTF8Encoding $false
# no declared parameter: PowerShell would bind a git flag such as -D to it by prefix
function Tgit {
    $ErrorActionPreference = 'Continue'
    $dir, $rest = $args
    $out = & git -C $dir -c user.name=test -c user.email=test@invalid -c core.autocrlf=false @rest 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $args failed: $out" }
    $out | Where-Object { $_ -isnot [Management.Automation.ErrorRecord] }
}
function Lines([int[]]$n, [hashtable]$edit = @{}) { (@($n | ForEach-Object { if ($edit.ContainsKey($_)) { $edit[$_] } else { "line $_" } }) -join "`n") + "`n" }
function Write-Text([string]$path, [string]$text) { [IO.File]::WriteAllText($path, $text, $utf8) }
function Run([string]$action, [string[]]$extra = @()) {
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $script $action -Root $fake -Runtime $rt @extra 2>&1
    $script:rc = $LASTEXITCODE
    return ($out | ForEach-Object { "$_" }) -join "`n"
}
try {
    $up = Join-Path $scratch 'upstream'; $fake = Join-Path $scratch 'repo'; $rt = Join-Path $fake 'engine\runtime'
    New-Item -ItemType Directory -Force $up, (Join-Path $fake 'engine\patches') | Out-Null
    $null = Tgit $up init --quiet -b main
    Write-Text (Join-Path $up 'a.txt') (Lines (1..30))
    $null = Tgit $up add -A; $null = Tgit $up commit --quiet -m base
    $c0 = "$(Tgit $up rev-parse HEAD)".Trim()
    $null = Tgit $scratch clone --quiet $up $rt

    # three patches on the base, written as patch files the way engine/patches has them
    $null = Tgit $rt switch --quiet -c scratch
    $edits = @(@{5 = 'line 5 patched'}, @{15 = 'line 15 patched'}, @{25 = 'line 25 patched'})
    $names = @('01-move.patch', '02-context.patch', '03-upstream.patch')
    $headers = @("Patch one moves.`nSecond header line.", 'Patch two: the upstream changes its context.', 'Patch three goes upstream.')
    $all = @{}
    for ($i = 0; $i -lt 3; $i++) {
        foreach ($k in $edits[$i].Keys) { $all[$k] = $edits[$i][$k] }
        Write-Text (Join-Path $rt 'a.txt') (Lines (1..30) $all)
        $diff = (Tgit $rt diff --no-color) -join "`n"
        Write-Text (Join-Path $fake "engine\patches\$($names[$i])") "$($headers[$i])`n`n$diff`n"
        $null = Tgit $rt commit --quiet -am "p$i"
    }
    $null = Tgit $rt switch --quiet --detach $c0; $null = Tgit $rt branch -D scratch
    $before01 = [IO.File]::ReadAllBytes((Join-Path $fake 'engine\patches\01-move.patch'))
    Write-Text (Join-Path $fake 'engine\runtime.toml') "repository = `"$up`"`ncommit = `"$c0`"   # 2026-01-01`n"

    # upstream: two lines on top (patch 01 moves), line 13 changed (patch 02's context), patch 03 taken as is
    Write-Text (Join-Path $up 'a.txt') ("new 1`nnew 2`n" + (Lines (1..30) @{13 = 'line 13 upstream'; 25 = 'line 25 patched'}))
    $null = Tgit $up commit --quiet -am newer
    $c1 = "$(Tgit $up rev-parse HEAD)".Trim()

    $out = Run 'start' @('-Onto', 'origin/main')
    if ($rc -ne 0) { throw "start -Onto failed (rc=$rc): $out" }
    $out = Run 'export'
    if ($rc -ne 0) { throw "export failed (rc=$rc): $out" }
    $p = Join-Path $fake 'engine\patches'
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes("$p\01-move.patch")) -ne [Convert]::ToBase64String($before01)) { throw 'a patch that only moved must keep its file' }
    $two = [IO.File]::ReadAllText("$p\02-context.patch", $utf8)
    if (-not $two.StartsWith("$($headers[1])`n`ndiff --git a/a.txt b/a.txt`n") -or $two -notmatch 'line 13 upstream') { throw "patch 02 must be rewritten under its header: $two" }
    if (Test-Path "$p\03-upstream.patch") { throw 'a patch already upstream must be removed' }
    if ([IO.File]::ReadAllText((Join-Path $fake 'engine\runtime.toml')) -notmatch "(?m)^commit = `"$c1`"   # \d{4}-\d\d-\d\d$") { throw 'runtime.toml must name the new base' }
    $out = Run 'drop'
    if ($rc -ne 0 -or (Test-Path "$rt-patches")) { throw "drop failed (rc=$rc): $out" }
    Write-Host 'PASS: patch stack rebase keeps moved patches, rewrites changed ones, drops upstreamed ones'

    # a conflict stops start with rc 2 and leaves the rebase to finish by hand
    Write-Text (Join-Path $up 'a.txt') ("new 1`nnew 2`n" + (Lines (1..30) @{5 = 'line 5 upstream'; 13 = 'line 13 upstream'; 25 = 'line 25 patched'}))
    $null = Tgit $up commit --quiet -am conflict
    $out = Run 'start' @('-Onto', 'origin/main')
    if ($rc -ne 2) { throw "a conflicting rebase must stop with rc 2 (rc=$rc): $out" }
    $out = Run 'export'
    if ($rc -eq 0 -or $out -notmatch 'rebase is in progress') { throw "export must refuse during a rebase: $out" }
    $null = Tgit "$rt-patches" rebase --abort
    $out = Run 'drop'
    if ($rc -ne 0) { throw "drop after abort failed: $out" }
    Write-Host 'PASS: patch stack conflict stops for manual resolution'
}
finally {
    if (Test-Path $scratch) { Remove-Item -Recurse -Force $scratch }
}
