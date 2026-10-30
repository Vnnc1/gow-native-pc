# A small real compiler/cache round trip, isolated from the player's cache and statistics.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$CompilerCache = 'sccache'
. (Join-Path $root 'tools/pipeline/modules/common.ps1')
. (Join-Path $root 'tools/pipeline/modules/tools.ps1')
. (Join-Path $root 'tools/pipeline/modules/toolchain.ps1')
Use-Clang
$folder = Join-Path $root ('data/cache-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$env:SCCACHE_SERVER_PORT = "$($listener.LocalEndpoint.Port)"
$listener.Stop()
$env:SCCACHE_DIR = Join-Path $folder 'cache'
$source = Join-Path $folder 'sample.cpp'
$object = Join-Path $folder 'sample.obj'
[IO.File]::WriteAllText($source, "#include <vector>`n#include <algorithm>`nint sum(std::vector<int> x) { std::sort(x.begin(), x.end()); return x.empty() ? 0 : x.back(); }`n")
try {
    $times = @()
    $hashes = @()
    for ($run = 0; $run -lt 2; ++$run) {
        if (Test-Path $object) { Remove-Item -LiteralPath $object }
        $watch = [Diagnostics.Stopwatch]::StartNew()
        Native $script:cacheExe @((Join-Path $script:llvmBin 'clang++.exe'), '-O2', '-c', $source, '-o', $object) 'cache smoke compile'
        $times += $watch.Elapsed.TotalSeconds
        $hashes += (Get-FileHash $object -Algorithm SHA256).Hash
    }
    $raw = & $script:cacheExe --show-stats --stats-format json
    if ($LASTEXITCODE -ne 0) { throw 'cache statistics failed' }
    [IO.File]::WriteAllText((Join-Path $folder 'stats.json'), ($raw -join "`n"))
    $stats = ($raw -join "`n") | ConvertFrom-Json
    $hits = ($stats.stats.cache_hits.counts.PSObject.Properties.Value | Measure-Object -Sum).Sum
    if ($hits -lt 1 -or $hashes[0] -ne $hashes[1]) { throw 'Expected a cache hit with an identical object' }
    $result = [ordered]@{ coldSeconds=$times[0]; warmSeconds=$times[1]; hits=$hits; objectHash=$hashes[0] }
    [IO.File]::WriteAllText((Join-Path $folder 'result.json'), ($result | ConvertTo-Json))
    Write-Host "PASS: identical object, cache hit; evidence: $folder"
    $result | ConvertTo-Json
    # A profile replaced at the same path must miss independently of the Ninja revision define.
    $pgoSource = Join-Path $folder 'pgo.cpp'
    $pgoExe = Join-Path $folder 'training.exe'
    $rawProfile = Join-Path $folder 'training.profraw'
    $profile = Join-Path $folder 'training.profdata'
    $pgoObject = Join-Path $folder 'pgo.obj'
    $directObject = Join-Path $folder 'direct.obj'
    [IO.File]::WriteAllText($pgoSource, "int work(int x) { if (x < 10) return x * 5; if (x < 100) return x * 3; return x * 2; }`nint main(int argc, char**) { volatile int x = work(argc); return x < 0; }`n")
    $cxx = Join-Path $script:llvmBin 'clang++.exe'
    Native $cxx @('-O2', '-static', '-fprofile-instr-generate', $pgoSource, '-o', $pgoExe) 'instrumented fixture'
    $oldProfileEnv = $env:LLVM_PROFILE_FILE
    try {
        $env:LLVM_PROFILE_FILE = $rawProfile
        $previousProfile = ''
        for ($training = 0; $training -lt 2; ++$training) {
            if (Test-Path $rawProfile) { Remove-Item -LiteralPath $rawProfile }
            $arguments = if ($training -eq 0) { 'first' } else { (1..20 | ForEach-Object { 'argument' }) -join ' ' }
            $process = Start-Process -FilePath $pgoExe -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
            if ($process.ExitCode -ne 0) { throw 'PGO fixture failed' }
            Native (Join-Path $script:llvmBin 'llvm-profdata.exe') @('merge', '-o', $profile, $rawProfile) 'fixture profile merge'
            $profileHash = (Get-FileHash $profile -Algorithm SHA256).Hash
            if ($profileHash -eq $previousProfile) { throw 'Training profiles unexpectedly identical' }
            $previousProfile = $profileHash
            $flags = @('-O2', "-fprofile-instr-use=$profile", '-c', $pgoSource)
            Native $script:cacheExe (@($cxx) + $flags + @('-o', $pgoObject)) 'profile-use cache compile'
            if ($training -eq 0) {
                Remove-Item -LiteralPath $pgoObject
                Native $script:cacheExe (@($cxx) + $flags + @('-o', $pgoObject)) 'profile-use cache hit'
            }
        }
        Native $cxx ($flags + @('-o', $directObject)) 'uncached profile-use control'
        $cachedBytes = [IO.File]::ReadAllBytes($pgoObject)
        $directBytes = [IO.File]::ReadAllBytes($directObject)
        # COFF objects carry wall-clock timestamps at bytes 4..7; all other bytes must match.
        foreach ($offset in 4..7) { $cachedBytes[$offset] = 0; $directBytes[$offset] = 0 }
        if (-not [Linq.Enumerable]::SequenceEqual($cachedBytes, $directBytes)) { throw 'PGO cache returned a stale object' }
        $raw = & $script:cacheExe --show-stats --stats-format json
        $stats = ($raw -join "`n") | ConvertFrom-Json
        $hits = ($stats.stats.cache_hits.counts.PSObject.Properties.Value | Measure-Object -Sum).Sum
        $misses = ($stats.stats.cache_misses.counts.PSObject.Properties.Value | Measure-Object -Sum).Sum
        if ($hits -ne 2 -or $misses -ne 3) { throw "Expected two hits and three misses including PGO; got $hits / $misses" }
        [IO.File]::WriteAllText((Join-Path $folder 'pgo-stats.json'), ($raw -join "`n"))
        Write-Host 'PASS: same-path PGO replacement missed cache and matched uncached compilation'
    } finally {
        [Environment]::SetEnvironmentVariable('LLVM_PROFILE_FILE', $oldProfileEnv, 'Process')
    }
} finally {
    Native $script:cacheExe @('--stop-server') 'stop isolated cache server'
}
