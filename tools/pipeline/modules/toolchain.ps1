# All shipped components use the same pinned llvm-mingw compiler and C++ runtime.
function Use-Clang {
    if ($script:clangReady) { return }
    $clang = Get-PortableTool 'clang'
    $script:llvmBin = Split-Path $clang
    foreach ($v in 'INCLUDE', 'LIB', 'LIBPATH', 'VCINSTALLDIR') { Remove-Item "env:$v" -ErrorAction SilentlyContinue }
    $env:PATH = $script:llvmBin + ';' + $env:PATH
    $script:cacheExe = ''
    if ($CompilerCache -ne 'none') {
        $script:cacheExe = Get-PortableTool 'sccache'
        # Keep this cache local; never inherit credentials or remote storage from the host shell.
        Get-ChildItem env:SCCACHE_* | Remove-Item -ErrorAction SilentlyContinue
        $env:SCCACHE_CONF = Join-Path $toolsDir 'sccache-local.toml'
        [IO.File]::WriteAllText($env:SCCACHE_CONF, "# Pipeline-owned local configuration; storage is selected by SCCACHE_DIR.`n")
        $env:SCCACHE_DIR = Join-Path $root 'data/compiler-cache'
        # Avoid reusing another project's daemon, which may have a different storage backend.
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant())) } finally { $sha.Dispose() }
        $env:SCCACHE_SERVER_PORT = "$(30000 + ([BitConverter]::ToUInt32($bytes, 0) % 20000))"
        $env:SCCACHE_CACHE_SIZE = '5G'
        $env:SCCACHE_IDLE_TIMEOUT = '600'
        $env:PATH = (Split-Path $script:cacheExe) + ';' + $env:PATH
    }
    $script:clangReady = $true
}
function Use-Toolchain { Use-Clang } # compatibility for stages and developer scripts
function Write-CompilerCacheStats([string]$name) {
    if (-not $script:cacheExe) { return }
    $ErrorActionPreference = 'Continue'
    $raw = & $script:cacheExe --show-stats --stats-format json 2>$null
    if ($LASTEXITCODE -eq 0) { [IO.File]::WriteAllText((Join-Path $logs "cache-$name.json"), ($raw -join "`n")) }
}
function Clang-CMakeArgs([switch]$NoCache) {
    Use-Clang
    $cache = if ($NoCache) { '' } else { $script:cacheExe }
    return @("-DCMAKE_C_COMPILER=$(Barra (Join-Path $script:llvmBin 'clang.exe'))",
        "-DCMAKE_CXX_COMPILER=$(Barra (Join-Path $script:llvmBin 'clang++.exe'))",
        "-DCMAKE_RC_COMPILER=$(Barra (Join-Path $script:llvmBin 'llvm-rc.exe'))",
        "-DCMAKE_MAKE_PROGRAM=$(Barra $ninjaExe)",
        "-DCMAKE_C_COMPILER_LAUNCHER=$(Barra $cache)", "-DCMAKE_CXX_COMPILER_LAUNCHER=$(Barra $cache)")
}
