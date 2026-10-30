# Build only the Qt modules used by the launcher, with the same C++ ABI as the game tools.
# Source archives and checksums are pinned in toolchains.json. No Visual Studio or system Python required.
function Expand-QtSource([string]$archive, [string]$work) {
    # Older Windows tar builds delegate XZ to an external executable that may not exist.
    # The pinned Python includes liblzma; stream to a private tar file with bounded RAM.
    $uncompressed = Join-Path $work ('qt-source-' + [guid]::NewGuid().ToString('N') + '.tar')
    try {
        $code = "import lzma, shutil, sys`nwith lzma.open(sys.argv[1], 'rb') as source, open(sys.argv[2], 'wb') as output:`n    shutil.copyfileobj(source, output, 1024 * 1024)"
        Native $python @('-I', '-c', $code, $archive, $uncompressed) 'Qt source decompression'
        Native (Join-Path $env:SystemRoot 'System32/tar.exe') @('-xf', $uncompressed, '-C', $work) 'Qt source extraction'
    } finally {
        Remove-Item -LiteralPath $uncompressed -Force -ErrorAction SilentlyContinue
    }
}

function Get-ClangQt {
    Use-Clang
    $version = $toolManifest.qt.version
    $compilerId = $portable['clang'].sha.Substring(0, 12)
    $prefix = Join-Path $toolsDir "qt/$version/clang-$compilerId"
    $signature = (Get-FileHash (Join-Path $root 'tools/pipeline/toolchains.json') -Algorithm SHA256).Hash + ':' +
        (Get-FileHash $PSCommandPath -Algorithm SHA256).Hash + ':' +
        (Get-FileHash (Join-Path $root 'tools/pipeline/compat/qt-sequence-sort.h') -Algorithm SHA256).Hash + ':' +
        (Get-FileHash (Join-Path $root 'tools/test/qt-sequence-sort.cpp') -Algorithm SHA256).Hash
    $stamp = Join-Path $prefix 'gow-qt.sig'
    if ((Test-Path $stamp) -and (Get-Content $stamp -Raw).Trim() -eq $signature -and
        (Test-Path (Join-Path $prefix 'lib/cmake/Qt6QuickControls2/Qt6QuickControls2Config.cmake'))) { return $prefix }
    $work = $BuildRoot + '-qt'
    $existingCache = Join-Path $work 'qtbase-build/CMakeCache.txt'
    if (Test-Path $existingCache) {
        $existingPrefix = [regex]::Match((Get-Content $existingCache -Raw), '(?m)^CMAKE_INSTALL_PREFIX:PATH=(.*)$').Groups[1].Value.Trim()
        if ($existingPrefix -ne (Barra $prefix)) {
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $id = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root + '|' + $prefix))) -replace '-', '').Substring(0, 8) }
            finally { $sha.Dispose() }
            $work += '-' + $id
        }
    }
    New-Item -ItemType Directory -Force $work, $prefix | Out-Null
    foreach ($module in $toolManifest.qt.modules) {
        $source = Join-Path $work ($module.name + '-everywhere-src-' + $version)
        if (-not (Test-Path (Join-Path $source 'CMakeLists.txt'))) {
            $archive = Join-Path $toolsDir ([IO.Path]::GetFileName($module.url))
            if (-not (Test-Path $archive) -or (Get-FileHash $archive -Algorithm SHA256).Hash -ne $module.sha) {
                Write-Host "@@status downloading $($module.name) $version sources"
                $ProgressPreference = 'SilentlyContinue'
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest -UseBasicParsing $module.url -OutFile $archive
            }
            if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne $module.sha) { throw "$($module.name): source checksum mismatch" }
            Expand-QtSource $archive $work
        }
        $qtBuild = Join-Path $work ($module.name + '-build')
        if ($module.name -eq 'qtbase') {
            # Qt 6.8.3 relied on a transitive standard-library include removed in libc++ 23.
            $syncqt = Join-Path $source 'src/tools/syncqt/main.cpp'
            $text = [IO.File]::ReadAllText($syncqt)
            if ($text -notmatch '#include <algorithm>') { [IO.File]::WriteAllText($syncqt, "#include <algorithm>`n" + $text) }
            # These two Qt sources disagree on the declaration's export attribute when merged in one Clang TU.
            # Preserve upstream declarations by compiling qwidgetwindow.cpp separately, as in a non-unity build.
            $widgets = Join-Path $source 'src/widgets/CMakeLists.txt'
            $widgetText = [IO.File]::ReadAllText($widgets)
            $exclude = 'set_source_files_properties(kernel/qwidgetwindow.cpp PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)'
            if (-not $widgetText.Contains($exclude)) { [IO.File]::WriteAllText($widgets, $widgetText + "`n$exclude`n") }
        }
        if ($module.name -eq 'qtdeclarative') {
            # Qt's proxy iterator lacks operator[] and default construction required by libc++ algorithms.
            # Sort owned variants and write back through Qt's iterator, without changing the QtCore ABI.
            $sequence = Join-Path $source 'src/qml/jsruntime/qv4sequenceobject.cpp'
            $sequenceText = [IO.File]::ReadAllText($sequence)
            $fixedSequence = $sequenceText -replace 'std::sort\(QSequentialIterable::(?:RandomAccess|Bidirectional)Iterator\(iterable.mutableBegin\(\)\),\s+QSequentialIterable::(?:RandomAccess|Bidirectional)Iterator\(iterable.mutableEnd\(\)\),\s+compare\);', 'GowQtCompat::sortSequence(iterable, compare);'
            if ([regex]::Matches($fixedSequence, 'GowQtCompat::sortSequence\(iterable, compare\);').Count -ne 2) { throw 'Qt sequence sort source changed; review the compatibility adjustment' }
            if (-not $fixedSequence.Contains('#include "gow_sequence_sort.h"')) { $fixedSequence = "#include `"gow_sequence_sort.h`"`n" + $fixedSequence }
            if ($fixedSequence -ne $sequenceText) { [IO.File]::WriteAllText($sequence, $fixedSequence) }
            $compat = Join-Path $root 'tools/pipeline/compat/qt-sequence-sort.h'
            $compatDst = Join-Path (Split-Path $sequence) 'gow_sequence_sort.h'
            if (-not (Test-Path $compatDst) -or (Get-FileHash $compatDst).Hash -ne (Get-FileHash $compat).Hash) { Copy-Item $compat $compatDst -Force }
        }
        $args_ = @('-S', $source, '-B', $qtBuild, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
            "-DCMAKE_INSTALL_PREFIX=$(Barra $prefix)", "-DCMAKE_PREFIX_PATH=$(Barra $prefix)",
            '-DQT_BUILD_TESTS=OFF', '-DQT_BUILD_EXAMPLES=OFF', '-DQT_BUILD_BENCHMARKS=OFF',
            '-DQT_UNITY_BUILD=ON', '-DQT_UNITY_BUILD_BATCH_SIZE=16') + (Clang-CMakeArgs)
        # Release only, shared Qt with its bundled third-party libraries, no optional external SDKs.
        if ($module.name -eq 'qtbase') { $args_ += @('-DFEATURE_sql=OFF', '-DFEATURE_testlib=OFF', '-DFEATURE_openssl=OFF') }
        Write-Host "@@status configuring $($module.name) with clang"
        Native $cmakeExe $args_ "$($module.name) configure"
        Write-Host "@@status building $($module.name) (first launcher build only)"
        Native $cmakeExe @('--build', $qtBuild, '--parallel', "$jobs") "$($module.name) build"
        Native $cmakeExe @('--install', $qtBuild) "$($module.name) install"
    }
    Write-Host '@@status validating Qt sequence sorting with the pinned C++ library'
    $compatTest = Join-Path $work 'qt-sequence-sort.exe'
    Native (Join-Path $script:llvmBin 'clang++.exe') @('-O2', '-std=c++17', '-Wno-ignored-attributes',
        "-I$(Barra $prefix)/include", "-I$(Barra $prefix)/include/QtCore", (Join-Path $root 'tools/test/qt-sequence-sort.cpp'),
        "-L$(Barra $prefix)/lib", '-lQt6Core', '-o', $compatTest) 'Qt sequence test build'
    $previousPath = $env:PATH
    try { $env:PATH = (Join-Path $prefix 'bin') + ';' + $env:PATH; Native $compatTest @() 'Qt sequence sorting regression' }
    finally { $env:PATH = $previousPath }
    [IO.File]::WriteAllText($stamp, $signature)
    return $prefix
}
