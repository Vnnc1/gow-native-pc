# --- tools -----------------------------------------------------------------------------------------------------------
# Portable copies in data\_tools, used instead of whatever the machine has installed (no installer, no admin rights, no
# PATH changes; an old system Python without tomllib or a Microsoft Store stub cannot get in the way). Each is downloaded
# once from its official release and checked against the SHA-256 published there.
$toolsDir = Join-Path $root 'data\_tools'
$toolManifest = Get-Content (Join-Path $root 'tools/pipeline/toolchains.json') -Raw | ConvertFrom-Json
$portable = @{}
foreach ($entry in $toolManifest.tools.PSObject.Properties) { $portable[$entry.Name] = $entry.Value }
# Unpacks a zip with Windows' own tar.exe (bsdtar, Windows 10 1803+): a few seconds where Expand-Archive took minutes on
# archives of thousands of small files. skip: path patterns left out (documentation, unused targets).
function Expand-Zip([string]$zip, [string]$dest, [string[]]$skip = @(), [switch]$Strip) {
    New-Item -ItemType Directory -Force $dest | Out-Null
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) {
        $a = @('-xf', $zip, '-C', $dest)
        if ($Strip) { $a += '--strip-components=1' }
        foreach ($x in $skip) { $a += @('--exclude', $x) }
        & $tar @a
        if ($LASTEXITCODE -eq 0) { return }
        Write-Host "tar failed (rc=$LASTEXITCODE), unpacking with Expand-Archive"
    }
    if ($Strip) { throw 'Windows tar.exe is required to unpack this toolchain' }
    Expand-Archive -Path $zip -DestinationPath $dest -Force
}
function Get-PortableTool([string]$name) {
    $t = $portable[$name]
    $dest = Join-Path $toolsDir $t.dir
    $exe = Join-Path $dest $t.exe
    if (Test-Path $exe) { return $exe }
    New-Item -ItemType Directory -Force $toolsDir | Out-Null
    $zip = Join-Path $toolsDir ([IO.Path]::GetFileName($t.url))
    if (-not (Test-Path $zip) -or (Get-FileHash $zip -Algorithm SHA256).Hash -ne $t.sha) {
        Write-Host "@@status downloading $name (about $($t.mb) MB, once)"
        Write-Host "downloading $name : $($t.url)"
        $ProgressPreference = 'SilentlyContinue'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing $t.url -OutFile $zip
        if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $t.sha) { Remove-Item $zip; throw "$name download: unexpected SHA-256 (try again)" }
    }
    Write-Host "@@status unpacking $name"
    Expand-Zip $zip $dest $(if ($t.skip) { $t.skip } else { @() }) -Strip:([bool]$t.strip)
    Remove-Item $zip
    # the embeddable Python's ._pth file would keep each script's own folder off sys.path
    if ($name -eq 'python') { Get-ChildItem $dest -Filter '*._pth' | Remove-Item }
    if (-not (Test-Path $exe)) { throw "$name : $exe missing after unpacking" }
    return $exe
}
$python = Get-PortableTool 'python'
$git = Get-PortableTool 'git'
$cmakeExe = Get-PortableTool 'cmake'
$ninjaExe = Get-PortableTool 'ninja'
# Git for CMake's dependency downloads (FetchContent), CMake and Ninja for every build
$env:PATH = (@((Split-Path $git), (Split-Path $cmakeExe), (Split-Path $ninjaExe)) -join ';') + ';' + $env:PATH
