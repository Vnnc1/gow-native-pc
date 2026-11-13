# gow-native.boot (engine/patches/zzz-326): the pipeline's first-run defaults and the launcher both write the file, and
# the runtime resolves it at startup. The installation root is recorded relative to the boot file's own folder and every
# path inside the installation '@'-relative to that root, so a copied or moved installation still starts on its own.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $root 'tools/pipeline/modules/common.ps1')
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('gow-boot-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $scratch | Out-Null
try {
    $instalacion = Join-Path $scratch 'God of War'
    $bootDir = Join-Path $scratch 'build/ps2xRuntime'
    New-Item -ItemType Directory -Force $bootDir | Out-Null
    $elf = Join-Path $instalacion 'data/gow1/discs/usa/SCUS_973.99'
    $capturas = Join-Path $instalacion 'data/gow1/vu1_capture'
    $iso = Join-Path $scratch 'isos/game.iso' # a player's own ISO: outside the installation
    $texto = Format-BootProfile $bootDir $instalacion $elf @(
        "GOW_VU1_CAPTURA=$(Get-BootProfilePath $instalacion $capturas)",
        "GOW_ISO=$(Get-BootProfilePath $instalacion $iso)",
        'PS2X_GS_WORKER=1')
    $lineas = $texto -split "`n"
    if ($lineas[0] -ne 'GOW_NATIVE_BOOT_V2') { throw "unexpected header: $($lineas[0])" }
    # The root must resolve to the installation from the boot file's folder alone, without knowing its full path.
    $resuelta = [IO.Path]::GetFullPath((Join-Path $bootDir $lineas[1])).TrimEnd('\', '/')
    if ($resuelta -ne [IO.Path]::GetFullPath($instalacion).TrimEnd('\', '/')) {
        throw "the recorded root must resolve to the installation: $($lineas[1]) -> $resuelta"
    }
    if ($lineas[2] -ne '@data/gow1/discs/usa/SCUS_973.99') { throw "the ELF must be installation-relative: $($lineas[2])" }
    if ($lineas[3] -ne 'GOW_VU1_CAPTURA=@data/gow1/vu1_capture') { throw "a path inside the installation must be '@'-relative: $($lineas[3])" }
    if ($lineas[4] -ne "GOW_ISO=$iso") { throw "a path outside the installation must stay absolute: $($lineas[4])" }
    if ($lineas[5] -ne 'PS2X_GS_WORKER=1') { throw "a plain value must stay unchanged: $($lineas[5])" }
    # A boot file inside the installation anchors the root to its own folder.
    $dentro = Format-BootProfile $instalacion $instalacion $elf @()
    if (($dentro -split "`n")[1] -ne '.') { throw "a boot file inside the installation must anchor with '.': $(($dentro -split "`n")[1])" }
    Write-Host 'PASS: boot profile records the installation root relative to itself and makes paths inside it relative'
} finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
