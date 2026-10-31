# The runtime patch stack as git commits, to move engine/patches to a newer runtime commit with git's 3-way merges
# instead of hand-editing context lines. git apply --3way cannot do this: most patch files have no "index" lines.
#   start [-Onto <commit>]   worktree engine/runtime-patches (of engine/runtime), branch gow-patches: one commit per
#                            engine/patches file on engine/runtime.toml's commit. -Onto <commit or ref> (e.g. origin/main)
#                            fetches the runtime's origin and rebases the stack onto it; on a conflict, resolve the files
#                            in engine/runtime-patches, `git add` them and `git rebase --continue` there, then export
#   export                   engine/patches from the stack: a patch whose file still applies exactly is left byte for byte
#                            (header and context lines unchanged); a dropped commit (already upstream) removes its file;
#                            runtime.toml's commit becomes the stack's base. The result is checked: applied in file-name
#                            order on that base, engine/patches give the branch's tree
#   drop                     removes the worktree, the branch and the base ref (engine/patches keeps what was exported)
# Each commit's message is "<name>\n\n<patch header>\n\nPatch: <name>"; a new patch is a new commit with that form (its
# name sorting after the one before it). Edit a patch: `git commit --fixup` + `git rebase -i --autosquash` in the
# worktree, or amend. A header line starting with '#' is lost if git opens an editor for that commit (comment cleanup).
# After export, engine/runtime still holds the old patched tree: reset it (git -C engine/runtime reset --hard; clean -fd,
# which loses local runtime edits) and run the fetch stage.
# usage: powershell -ExecutionPolicy Bypass -File tools\pipeline\patches.ps1 start|export|drop [-Onto <commit>]
param(
    [Parameter(Mandatory = $true, Position = 0)][ValidateSet('start', 'export', 'drop')][string]$Action,
    [string]$Onto = '',
    # tests: other folders than this repository's
    [string]$Root = '',
    [string]$Runtime = ''
)
if ($PSVersionTable.PSVersion.Major -lt 6) { $env:PSModulePath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\Modules" }
$ErrorActionPreference = 'Stop'
trap { Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
$root = $Root
. (Join-Path $PSScriptRoot 'modules/common.ps1')
$rt = if ($Runtime) { $Runtime } else { Join-Path $root 'engine\runtime' }
$wt = "$rt-patches"
$branch = 'gow-patches'
$baseRef = 'refs/gow/patch-base'
$patchDir = Join-Path $root 'engine\patches'
$tomlPath = Join-Path $root 'engine\runtime.toml'
$runtimeCommit = [regex]::Match([IO.File]::ReadAllText($tomlPath), '(?m)^commit\s*=\s*"([^"]+)"').Groups[1].Value
$utf8 = New-Object Text.UTF8Encoding $false
# Runtime sources and patch headers are UTF-8; Windows PowerShell would decode git's output in the OEM code page.
[Console]::OutputEncoding = $utf8

$git = $null
$toolManifest = Get-Content (Join-Path $PSScriptRoot 'toolchains.json') -Raw | ConvertFrom-Json
$portableGit = Join-Path $root "data\_tools\$($toolManifest.tools.git.dir)\$($toolManifest.tools.git.exe)"
if (Test-Path $portableGit) { $git = $portableGit }
elseif (Get-Command git -ErrorAction SilentlyContinue) { $git = (Get-Command git).Source }
else { throw 'git not found: install Git for Windows or run the tools stage' }

# git in folder $dir; returns stdout lines, throws on failure unless -Allow
function G([string]$dir, [string[]]$a, [switch]$Allow) {
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = 0
    $out = @(& $git -C $dir @a 2>&1)
    $rc = $global:LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $text = @($out | Where-Object { $_ -isnot [Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
    if ($rc -ne 0 -and -not $Allow) {
        $err = @($out | ForEach-Object { "$_" }) -join "`n"
        throw "git $($a -join ' ') failed (rc=$rc): $err"
    }
    $script:gitRc = $rc
    return $text
}
function Rev([string]$what) { return "$(G $wt @('rev-parse', '--verify', '--quiet', $what) -Allow)".Trim() }
function Test-Rebase {
    foreach ($d in @('rebase-merge', 'rebase-apply')) {
        $p = "$(G $wt @('rev-parse', '--git-path', $d))".Trim()
        if (-not [IO.Path]::IsPathRooted($p)) { $p = Join-Path $wt $p }
        if (Test-Path $p) { return $true }
    }
    return $false
}
# Header of a patch file: the text before its first file diff ("diff --git", or "---"/"+++" in the files 29c-29f
# wrote without it), without trailing blank lines
function Get-PatchHeader([string]$path) {
    $text = [IO.File]::ReadAllText($path, $utf8) -replace "`r`n", "`n"
    $m = [regex]::Match($text, '(?m)^(diff --git |--- .*\n\+\+\+ )')
    if (-not $m.Success) { throw "$path has no file diff" }
    return $text.Substring(0, $m.Index).TrimEnd("`n")
}
# Tree after applying $files in order on $commit, in a temporary index (no file is touched); '' when one does not apply
function Get-AppliedTree([string]$commit, [string[]]$files) {
    $index = Join-Path $env:TEMP "gow-patches-index-$PID"
    $old = $env:GIT_INDEX_FILE
    try {
        $env:GIT_INDEX_FILE = $index
        $null = G $wt @('read-tree', $commit)
        foreach ($f in $files) {
            $null = G $wt @('apply', '--cached', $f) -Allow
            if ($script:gitRc -ne 0) { return '' }
        }
        return "$(G $wt @('write-tree'))".Trim()
    }
    finally {
        $env:GIT_INDEX_FILE = $old
        Remove-Item $index -Force -ErrorAction SilentlyContinue
    }
}

if ($Action -eq 'start') {
    if (-not (Test-Path (Join-Path $rt '.git'))) { throw "no runtime checkout at $rt (run the fetch stage)" }
    if (Test-Path $wt) { throw "$wt exists: export or drop the stack in progress first" }
    $null = G $rt @('rev-parse', '--verify', '--quiet', "refs/heads/$branch") -Allow
    if ($script:gitRc -eq 0) { throw "branch $branch exists in $rt (drop it first)" }
    $null = G $rt @('worktree', 'add', '--quiet', '-b', $branch, $wt, $runtimeCommit)
    $null = G $wt @('update-ref', $baseRef, $runtimeCommit)
    $msgFile = Join-Path $env:TEMP "gow-patches-msg-$PID.txt"
    # The generated commits need no identity of the user; commits they make in the worktree use their own.
    $saved = @{}
    foreach ($v in 'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL') { $saved[$v] = [Environment]::GetEnvironmentVariable($v) }
    try {
        $env:GIT_AUTHOR_NAME = 'gow-native-pc patches'; $env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME
        $env:GIT_AUTHOR_EMAIL = 'patches@gow-native-pc.invalid'; $env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL
        foreach ($p in @(Get-RuntimePatches)) {
            $null = G $wt @('apply', '--index', '--whitespace=nowarn', $p.FullName)
            $header = Get-PatchHeader $p.FullName
            [IO.File]::WriteAllText($msgFile, "$($p.Name)`n`n$header`n`nPatch: $($p.Name)`n", $utf8)
            $null = G $wt @('commit', '--quiet', '--no-verify', '--allow-empty', '--cleanup=verbatim', '-F', $msgFile)
            Write-Host "commit $($p.Name)"
        }
    }
    catch {
        # the worktree was made by this run: nothing of the user's is in it yet
        $null = G $wt @('reset', '--quiet', '--hard') -Allow
        throw "$($_.Exception.Message)`n(the stack is incomplete: run patches.ps1 drop)"
    }
    finally {
        foreach ($v in $saved.Keys) { [Environment]::SetEnvironmentVariable($v, $saved[$v]) }
        Remove-Item $msgFile -Force -ErrorAction SilentlyContinue
    }
    if ($Onto) {
        $null = G $rt @('fetch', '--quiet', 'origin')
        $target = Rev "$Onto^{commit}"
        if (-not $target) { throw "$Onto is not a commit of the runtime repository" }
        $null = G $wt @('update-ref', $baseRef, $target)
        Write-Host "rebasing $(@(G $wt @('rev-list', "$runtimeCommit..$branch")).Count) patches onto $target"
        $out = G $wt @('rebase', '--onto', $target, $runtimeCommit, $branch) -Allow
        $out | ForEach-Object { Write-Host $_ }
        if ($script:gitRc -ne 0) {
            Write-Host "`nconflict: resolve the files in $wt, git add them and run git rebase --continue there" -ForegroundColor Yellow
            Write-Host "(git rebase --skip drops that patch, git rebase --abort goes back); then: patches.ps1 export"
            exit 2
        }
    }
    Write-Host "stack ready: $wt (branch $branch); next: patches.ps1 export"
    exit 0
}

if ($Action -eq 'export') {
    if (-not (Test-Path $wt)) { throw "no stack in progress ($wt): run start first" }
    if (Test-Rebase) { throw "a rebase is in progress in ${wt}: finish it (git rebase --continue) or abort it" }
    if (@(G $wt @('status', '--porcelain', '--untracked-files=no')).Count) { throw "${wt} has uncommitted changes: commit them into the stack first" }
    $base = Rev $baseRef
    if (-not $base) { throw "$baseRef is missing: drop the stack and start again" }
    if (@(G $wt @('rev-list', '--merges', "$base..$branch")).Count) { throw "the stack has merge commits: keep it linear" }
    $commits = @(G $wt @('rev-list', '--reverse', "$base..$branch"))
    $stack = @()
    foreach ($c in $commits) {
        $lines = @((G $wt @('log', '-1', '--format=%B', $c)) | ForEach-Object { $_.TrimEnd("`r") })
        while ($lines.Count -and -not $lines[-1]) { $lines = @($lines | Select-Object -First ($lines.Count - 1)) }
        $m = if ($lines.Count) { [regex]::Match($lines[-1], '^Patch:\s*([0-9A-Za-z][\w.-]*\.patch)\s*$') }
        if (-not $m -or -not $m.Success) { throw "commit $c ($($lines[0])) has no 'Patch: NN-name.patch' last line" }
        $body = if ($lines.Count -gt 3) { @($lines[2..($lines.Count - 2)]) } else { @() }
        $stack += [pscustomobject]@{ commit = $c; name = $m.Groups[1].Value; header = (($body -join "`n").TrimEnd("`n")) }
    }
    $names = [string[]]@($stack | ForEach-Object { $_.name })
    $sorted = [string[]]$names.Clone(); [Array]::Sort($sorted, [StringComparer]::Ordinal)
    if (($names -join '|') -cne ($sorted -join '|')) { throw "patch names must sort (ordinal) in stack order, as fetch applies them: $($names -join ', ')" }
    if (@($names | Select-Object -Unique).Count -ne $names.Count) { throw "two commits name the same patch file" }

    $tmp = Join-Path $env:TEMP "gow-patches-diff-$PID.patch"
    $files = @()
    $changed = 0
    try {
        foreach ($s in $stack) {
            $path = Join-Path $patchDir $s.name
            $files += $path
            # A file that still gives exactly this commit's tree on its parent stays as it is.
            if ((Test-Path $path) -and (Get-AppliedTree "$($s.commit)^" @($path)) -eq (Rev "$($s.commit)^{tree}")) { continue }
            $null = G $wt @('-c', 'core.quotePath=false', 'diff', '--no-color', '--no-ext-diff', '--no-textconv', '--no-renames',
                '--binary', '--src-prefix=a/', '--dst-prefix=b/', "--output=$tmp", "$($s.commit)^", $s.commit)
            $diff = [IO.File]::ReadAllBytes($tmp)
            $head = $utf8.GetBytes($(if ($s.header) { "$($s.header)`n`n" } else { '' }))
            $all = New-Object byte[] ($head.Length + $diff.Length)
            [Array]::Copy($head, 0, $all, 0, $head.Length); [Array]::Copy($diff, 0, $all, $head.Length, $diff.Length)
            [IO.File]::WriteAllBytes($path, $all)
            Write-Host "patch $($s.name): written"
            $changed++
        }
    }
    finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
    foreach ($p in @(Get-RuntimePatches)) {
        if ($names -notcontains $p.Name) { Remove-Item -LiteralPath $p.FullName; Write-Host "patch $($p.Name): removed (not in the stack)"; $changed++ }
    }
    if ($base -ne $runtimeCommit) {
        $date = "$(G $wt @('log', '-1', '--format=%cs', $base))".Trim()
        $toml = [IO.File]::ReadAllText($tomlPath, $utf8)
        $toml = [regex]::Replace($toml, '(?m)^commit\s*=\s*"[^"]*"[^\r\n]*', "commit = `"$base`"   # $date")
        [IO.File]::WriteAllText($tomlPath, $toml, $utf8)
        Write-Host "runtime.toml: commit $runtimeCommit -> $base"
    }
    $expect = Rev "$branch^{tree}"
    if ((Get-AppliedTree $base @(Get-RuntimePatches | ForEach-Object { $_.FullName })) -ne $expect) {
        throw "engine/patches applied on $base do not give the branch's tree: compare them with the stack"
    }
    Write-Host "export checked: $($stack.Count) patches on $base give the stack's tree ($changed files changed)"
    exit 0
}

if ($Action -eq 'drop') {
    if (Test-Path $wt) {
        if (Test-Rebase) { throw "a rebase is in progress in ${wt}: abort it first" }
        if (@(G $wt @('status', '--porcelain', '--untracked-files=no')).Count) { throw "${wt} has uncommitted changes" }
        # without --force: git keeps a worktree with untracked files (a new file not yet added to a commit)
        $null = G $rt @('worktree', 'remove', $wt)
    }
    $null = G $rt @('worktree', 'prune')
    $null = G $rt @('branch', '-D', $branch) -Allow
    $null = G $rt @('update-ref', '-d', $baseRef) -Allow
    Write-Host "stack dropped"
    exit 0
}
