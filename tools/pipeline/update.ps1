# Launcher updates from GitHub Releases (Vnnc1/gow-native-pc). The launcher runs it; it can also be run by hand.
#   -Check                       prints one JSON line: {"version","tag","url","sha256","notes","page"} of the latest release
#                                (its gow-native-pc-windows.zip), or {"error": "..."}
#   -Apply -Url <zip> [-Sha256 <hex>] [-WaitPid <launcher pid>] [-Version <x.y.z>]
#                                waits for the launcher to close, downloads the zip, checks its SHA-256, unpacks it over
#                                this copy and starts the launcher again. data\ (game, saves, tools, recorded code, build
#                                choices) and engine\runtime are never touched. When engine\patches changed, it writes
#                                data\needs-rebuild.txt: the launcher then offers to rebuild the game (build.ps1 removes the
#                                file after a successful build from the runtime that run fetched), and data\pgo-stale.txt:
#                                the launcher recommends training the profile again (removed by a new profile trained on
#                                the current runtime). Log: data\_update\update.log.
param(
    [switch]$Check,
    [switch]$Apply,
    [string]$Url = '',
    [string]$Sha256 = '',
    [int]$WaitPid = 0,
    [string]$Version = ''
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$repo = 'Vnnc1/gow-native-pc'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'

if ($Check) {
    try {
        $r = Invoke-RestMethod -UseBasicParsing -Headers @{ 'User-Agent' = 'gow-native-pc-launcher'; 'Accept' = 'application/vnd.github+json' } `
            "https://api.github.com/repos/$repo/releases/latest"
        $zip = $r.assets | Where-Object { $_.name -eq 'gow-native-pc-windows.zip' } | Select-Object -First 1
        $sha = if ($zip -and $zip.digest -match '^sha256:([0-9a-f]{64})$') { $Matches[1] } else { '' }
        [pscustomobject]@{
            version = ($r.tag_name -replace '^v', ''); tag = $r.tag_name; page = $r.html_url
            url = if ($zip) { $zip.browser_download_url } else { '' }; sha256 = $sha
            notes = "$($r.body)"
        } | ConvertTo-Json -Compress
    }
    catch { [pscustomobject]@{ error = $_.Exception.Message } | ConvertTo-Json -Compress }
    exit 0
}

if (-not $Apply) { throw 'use -Check or -Apply' }
$work = Join-Path $root 'data\_update'
New-Item -ItemType Directory -Force $work | Out-Null
$log = Join-Path $work 'update.log'
function Log($m) { $line = "[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $m; Add-Content -Path $log -Value $line; Write-Host $line }
$launcher = Join-Path $root 'launcher\bin\gow-launcher.exe'
try {
    Log "update to $Version from $Url"
    if (-not $Url) { throw 'no download address' }
    # the launcher's files can only be replaced once it has closed
    if ($WaitPid -gt 0) {
        $p = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
        if ($p -and -not $p.WaitForExit(60000)) { throw 'the launcher did not close' }
    }
    $zip = Join-Path $work 'update.zip'
    Invoke-WebRequest -UseBasicParsing $Url -OutFile $zip
    if ($Sha256) {
        $got = (Get-FileHash $zip -Algorithm SHA256).Hash
        if ($got -ne $Sha256) { throw "unexpected SHA-256 ($got)" }
    }
    $unpacked = Join-Path $work 'unpacked'
    if (Test-Path $unpacked) { Remove-Item -Recurse -Force $unpacked }
    New-Item -ItemType Directory -Force $unpacked | Out-Null
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) { & $tar -xf $zip -C $unpacked; if ($LASTEXITCODE -ne 0) { throw "unpacking failed ($LASTEXITCODE)" } }
    else { Expand-Archive -Path $zip -DestinationPath $unpacked -Force }
    # the release zip holds one folder (gow-native-pc) with the launcher, tools, games, engine and docs
    $src = Get-ChildItem $unpacked -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'games') } | Select-Object -First 1
    if (-not $src) { throw 'unexpected zip layout' }
    $patchesHash = { param($dir) (Get-ChildItem (Join-Path $dir 'engine\patches') -Filter *.patch -ErrorAction SilentlyContinue |
        Sort-Object Name | ForEach-Object { "$($_.Name):$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)" }) -join ';' }
    $before = & $patchesHash $root
    $after = & $patchesHash $src.FullName
    # copy over this copy: data\ (and the runtime checkout) stay as they are; patches removed upstream are removed here
    & robocopy $src.FullName $root /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP /XD (Join-Path $root 'data') (Join-Path $root 'engine\runtime') | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copy failed (robocopy $LASTEXITCODE)" }
    Get-ChildItem (Join-Path $root 'engine\patches') -Filter *.patch | Where-Object { -not (Test-Path (Join-Path $src.FullName "engine\patches\$($_.Name)")) } |
        ForEach-Object { Remove-Item $_.FullName; Log "removed $($_.Name)" }
    # files new in this version join the uninstaller's list
    $lst = Join-Path $root 'uninstall.lst'
    if (Test-Path $lst) {
        $known = @{}
        foreach ($l in Get-Content $lst -Encoding Unicode) { $known[$l] = $true }
        $add = Get-ChildItem $src.FullName -Recurse -File | ForEach-Object { $_.FullName.Substring($src.FullName.Length + 1) } | Where-Object { -not $known[$_] }
        if ($add) { Add-Content -Path $lst -Value $add -Encoding Unicode }
    }
    if ($before -ne $after) {
        [IO.File]::WriteAllText((Join-Path $root 'data\needs-rebuild.txt'), "$Version")
        # the profile-guided data describes the former runtime: the launcher recommends training it again (a rebuild with
        # it still works; the functions the new patches changed just lose their profile)
        [IO.File]::WriteAllText((Join-Path $root 'data\pgo-stale.txt'), "$Version")
        Log 'runtime patches changed: the game needs a rebuild'
    }
    Remove-Item -Recurse -Force $unpacked, $zip
    Log "updated to $Version"
}
catch { Log "ERROR: $($_.Exception.Message)" }
if (Test-Path $launcher) { Start-Process -FilePath $launcher -WorkingDirectory (Split-Path $launcher) }
