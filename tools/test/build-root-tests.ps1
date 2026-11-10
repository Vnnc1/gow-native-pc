$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot)
$scratch = Join-Path $repo ('data/build-root-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $scratch | Out-Null
$source = [IO.File]::ReadAllText((Join-Path $repo 'tools/pipeline/modules/context.ps1'))
$begin = $source.IndexOf('$buildRootFile =')
$end = $source.IndexOf('$pgoDir =', $begin)
if ($begin -lt 0 -or $end -lt 0) { throw 'Build-root selection block missing' }
$selection = [scriptblock]::Create($source.Substring($begin, $end - $begin))
function Barra([string]$path) { return $path.Replace('\', '/') }
function Select-TestRoot([string]$explicit = '') {
    $root = Join-Path $scratch 'install'
    $rec = Join-Path $root 'engine/runtime/PS2Recomp'
    $Config = 'Release'; $Toolchain = 'clang'; $BuildRoot = $explicit
    . $selection
    return $BuildRoot
}
try {
    # A custom location must not fall back to the global C:\gow-build folder.
    $choice = Join-Path $scratch 'chosen'
    $foreign = Join-Path $scratch 'chosen-clang'
    New-Item -ItemType Directory -Force $foreign | Out-Null
    [IO.File]::WriteAllText((Join-Path $foreign 'CMakeCache.txt'), 'CMAKE_HOME_DIRECTORY:INTERNAL=Z:/unrelated')
    $actual = Select-TestRoot $choice
    if (-not $actual.StartsWith($choice + '-')) { throw "Collision changed selected drive: $actual" }
    if (-not (Test-Path (Join-Path $foreign 'CMakeCache.txt'))) { throw 'Foreign build was touched' }
    $stored = [IO.File]::ReadAllText((Join-Path $scratch 'install/data/build-root.txt'))
    if ($stored -ne $actual) { throw 'Explicit effective root was not persisted' }
    if ((Select-TestRoot) -ne $actual) { throw 'Recorded root was not reused' }
    $unicode = Join-Path $scratch ('build-' + [char]0x00e1)
    if ((Select-TestRoot $unicode) -ne $unicode -or (Select-TestRoot) -ne $unicode) { throw 'UTF-8 root did not round trip' }
    Write-Output 'PASS: selected-drive collision, ownership preservation, explicit persistence and UTF-8 root reuse'
} finally {
    $resolved = [IO.Path]::GetFullPath($scratch)
    $allowed = [IO.Path]::GetFullPath((Join-Path $repo 'data')) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
