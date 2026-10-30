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
# native tools print progress on stderr; under 'Stop' PowerShell 5.1 may turn that into an exception
function Native($exe, [string[]]$a, $what) {
    $null = Get-Command $exe -ErrorAction Stop
    $ErrorActionPreference = 'Continue'
    # Native processes update the global automatic variable. A local assignment shadows that result on PS 5.1.
    $global:LASTEXITCODE = 0
    & $exe @a 2>&1 | ForEach-Object { $s = "$_"; if ($s -ne 'System.Management.Automation.RemoteException') { Write-Host $s } }
    if ($global:LASTEXITCODE -ne 0) { throw "$what failed (rc=$global:LASTEXITCODE)" }
}

