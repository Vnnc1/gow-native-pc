# --- launcher (development) -----------------------------------------------------------------------------------------
if ($Stages -contains 'launcher') {
    Step 'launcher (Qt 6)'
    Use-Clang
    . (Join-Path $root 'tools/pipeline/modules/qt.ps1')
    $qt = Get-ClangQt
    $lb = Join-Path $root 'launcher/build-clang'
    $launcherArgs = @('-S', (Join-Path $root 'launcher'), '-B', $lb, '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_PREFIX_PATH=$(Barra $qt)") + (Clang-CMakeArgs)
    Native $cmakeExe $launcherArgs 'launcher configure'
    Native $cmakeExe @('--build', $lb, '--parallel', "$jobs") 'launcher build'
    $builtExe = Join-Path $lb 'gow-launcher.exe'
    $deploy = Join-Path $lb 'deploy'
    if (Test-Path $deploy) {
        $resolved = (Resolve-Path -LiteralPath $deploy).Path
        if ($resolved -ne [IO.Path]::GetFullPath($deploy) -or (Get-Item -LiteralPath $deploy).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe launcher deployment path' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    New-Item -ItemType Directory -Path $deploy | Out-Null
    Copy-Item -LiteralPath $builtExe -Destination $deploy
    Copy-Item -LiteralPath (Join-Path $lb 'gow-session.exe') -Destination $deploy
    $exe = Join-Path $deploy 'gow-launcher.exe'
    # This SDK contains Release only. Auto detection avoids treating lld PE debug entries as a Debug CRT build.
    Native (Join-Path $qt 'bin\windeployqt.exe') @('--no-translations', '--no-compiler-runtime',
        '--qmldir', (Join-Path $root 'launcher\qml'), $exe) 'windeployqt'
    # Qt and the launcher share llvm-mingw's C++ runtime. Deploy it explicitly (windeployqt can expect GCC names).
    foreach ($dll in @('libc++.dll', 'libunwind.dll')) {
        $path = Join-Path $script:llvmBin $dll
        if (Test-Path $path) { Copy-Item -LiteralPath $path -Destination $deploy -Force }
    }
    # shortcut in the repository root, so the built launcher is one double-click away
    $lnk = Join-Path $root 'God of War Launcher.lnk'
    $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $sc.TargetPath = $exe; $sc.WorkingDirectory = $deploy; $sc.IconLocation = "$exe,0"; $sc.Description = 'God of War Native PC'
    $sc.Save()
    Write-Host "OK: $exe"
    Write-Host "shortcut: $lnk"
}
# --- package: the release zip (GitHub Releases) ---------------------------------------------------------------------
# launcher/bin = the built launcher + its Qt DLLs; the rest is this repository without generated data. Users unzip it
# anywhere and start launcher\bin\gow-launcher.exe (it finds the repository root by games\<id>\game.toml above it).
if ($Stages -contains 'package' -or ($Stages -contains 'installer' -and -not (Test-Path (Join-Path $root 'data\_package\gow-native-pc')))) {
    Step 'release package'
    $lb = Join-Path $root 'launcher/build-clang/deploy'
    $exe = Join-Path $lb 'gow-launcher.exe'
    Need $exe 'built launcher (run the launcher stage)'
    $stage = Join-Path $root 'data\_package\gow-native-pc'
    if (Test-Path $stage) {
        $resolved = (Resolve-Path -LiteralPath $stage).Path
        $expected = [IO.Path]::GetFullPath((Join-Path $root 'data/_package/gow-native-pc'))
        if ($resolved -ne $expected -or (Get-Item -LiteralPath $stage).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe package staging path' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    New-Item -ItemType Directory -Force (Join-Path $stage 'launcher\bin') | Out-Null
    # Only the clean deployment directory is packaged, never CMake objects or generated build sources.
    Get-ChildItem -LiteralPath $lb | Copy-Item -Destination (Join-Path $stage 'launcher\bin') -Recurse -Force
    foreach ($item in @('README.md', 'README.pt-BR.md', 'CREDITS.md', 'LICENSE', 'AGENTS.md', 'CLAUDE.md', 'build.cmd', 'docs', 'games', 'tools')) {
        Copy-Item (Join-Path $root $item) $stage -Recurse -Force
    }
    New-Item -ItemType Directory -Force (Join-Path $stage 'engine') | Out-Null
    Copy-Item (Join-Path $root 'engine\runtime.toml'), (Join-Path $root 'engine\README.md') (Join-Path $stage 'engine')
    Copy-Item (Join-Path $root 'engine\patches') (Join-Path $stage 'engine') -Recurse
    # Generated Python bytecode is not part of a source release.
    Get-ChildItem $stage -Recurse -File -Filter '*.pyc' | Remove-Item -Force
    $zip = Join-Path $root 'data\_package\gow-native-pc-windows.zip'
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path $stage -DestinationPath $zip
    Write-Host ("OK: {0} ({1:N0} MB)" -f $zip, ((Get-Item $zip).Length / 1MB))
}
# --- installer: one .exe for GitHub Releases ------------------------------------------------------------------------
# installer/setup.cpp (Win32, no Qt) packs the package folder into a copy of itself (LZMS); the result installs per user,
# makes Start menu / desktop shortcuts and an Apps entry, and removes itself (uninstall.exe).
if ($Stages -contains 'installer') {
    Step 'installer'
    Use-Clang
    $stage = Join-Path $root 'data\_package\gow-native-pc'
    Need (Join-Path $stage 'launcher\bin\gow-launcher.exe') 'release package (run the package stage)'
    $ib = Join-Path $root 'data/_tools/installer-build-clang'
    Native $cmakeExe (@('-S', (Join-Path $root 'installer'), '-B', $ib, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release') + (Clang-CMakeArgs)) 'installer configure'
    Native 'ninja' @('-C', $ib) 'installer build'
    $setup = Join-Path $root 'data\_package\gow-native-pc-setup.exe'
    Write-Host "@@status packing (LZMS, about a minute)"
    Native (Join-Path $ib 'gow-setup.exe') @('--pack', $stage, $setup) 'installer pack'
    Write-Host ("OK: {0} ({1:N0} MB)" -f $setup, ((Get-Item $setup).Length / 1MB))
}
