$script:stepTimings = [Collections.Generic.List[object]]::new()
$script:currentStep = $null
function End-Step {
    if ($script:currentStep) {
        $script:stepTimings.Add([ordered]@{step=$script:currentStep; seconds=[math]::Round($script:stepWatch.Elapsed.TotalSeconds, 3)})
        $script:currentStep = $null
    }
}
function Step($m) {
    End-Step
    $script:currentStep = $m
    $script:stepWatch = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "`n=== $m ===" -ForegroundColor Cyan
}
function Write-PipelineMetrics {
    End-Step
    if (-not $logs -or -not (Test-Path $logs)) { return }
    $result = [ordered]@{schema=1; success=$pipelineSucceeded; game=$Game; stages=$Stages; compiler='clang';
        compilerCache=$CompilerCache; configuration=$Config; codegen=$Codegen; buildRoot=$BuildRoot;
        thinLto=[bool]$Ltcg; debugSymbols=[bool]$Pdb;
        runtimeCommit=$runtimeCommit; totalSeconds=[math]::Round($pipelineWatch.Elapsed.TotalSeconds,3); steps=@($script:stepTimings.ToArray())}
    if ($portable) { $result.compilerPackage = $portable['clang'].dir; $result.cachePackage = $portable['sccache'].dir }
    if ($pgoProfile -and (Test-Path $pgoProfile)) { $result.pgoHash = (Get-FileHash $pgoProfile -Algorithm SHA256).Hash }
    $result.patches = @(Get-RuntimePatches | ForEach-Object {
        [ordered]@{name=$_.Name; sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
    })
    $name = 'pipeline-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'
    [IO.File]::WriteAllText((Join-Path $logs $name), ($result | ConvertTo-Json -Depth 6))
}

function Need($p, $what) { if (-not (Test-Path $p)) { throw "Missing $what : $p" } }
function Barra($p) { $p -replace '\\', '/' }
function Get-RuntimePatches {
    # Windows PowerShell 5.1 sorts punctuation differently from PowerShell 7.
    # Ordinal order guarantees 29-... precedes its dependent 29a/29b follow-ups on both hosts.
    [string[]]$paths = @(Get-ChildItem (Join-Path $root 'engine/patches/*.patch') | ForEach-Object { $_.FullName })
    [Array]::Sort($paths, [StringComparer]::Ordinal)
    foreach ($path in $paths) { Get-Item -LiteralPath $path }
}
# Windows PowerShell 5.1 (and PowerShell 7 before 7.3, or in Legacy mode) wraps an argument that contains whitespace
# in double quotes but passes its inner double quotes unescaped, so they end the quoting early: with the install in
# "E:\God of War", -DCMAKE_CXX_FLAGS=... -fprofile-instr-use="E:/God of War/..." reached CMake cut at "E:/God" and every
# compile failed. For such arguments, escape the inner quotes (and the backslashes before them, and trailing ones before
# the closing quote PowerShell adds) the way the C runtime parses a command line. An argument that already starts
# with a quote is passed unwrapped and left alone.
function ConvertTo-NativeArgument([string]$s) {
    $legacy = $PSVersionTable.PSVersion -lt [version]'7.3' -or $PSNativeCommandArgumentPassing -eq 'Legacy'
    if (-not $legacy -or $s -notmatch '\s' -or $s.StartsWith('"')) { return $s }
    $s = [regex]::Replace($s, '(\\*)"', { param($m) $m.Groups[1].Value * 2 + '\"' })
    return [regex]::Replace($s, '(\\+)$', { param($m) $m.Groups[1].Value * 2 })
}
# native tools print progress on stderr; under 'Stop' PowerShell 5.1 may turn that into an exception
function Native($exe, [string[]]$a, $what) {
    $null = Get-Command $exe -ErrorAction Stop
    $ErrorActionPreference = 'Continue'
    [string[]]$a = @($a | ForEach-Object { ConvertTo-NativeArgument $_ })
    # Native processes update the global automatic variable. A local assignment shadows that result on PS 5.1.
    $global:LASTEXITCODE = 0
    & $exe @a 2>&1 | ForEach-Object { $s = "$_"; if ($s -ne 'System.Management.Automation.RemoteException') { Write-Host $s } }
    if ($global:LASTEXITCODE -ne 0) { throw "$what failed (rc=$global:LASTEXITCODE)" }
}

