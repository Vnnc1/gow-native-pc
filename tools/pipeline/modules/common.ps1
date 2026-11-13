$script:stepTimings = [Collections.Generic.List[object]]::new()
$script:currentStep = $null
$script:gameBuildProfiles = [Collections.Generic.List[object]]::new()
$script:configuredGameProfile = $null
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
    # Legacy pgoHash describes an available file, never evidence that a build used it.
    $result.pgoHashMeaning = 'available-profile-not-application'
    if ($pgoProfile -and (Test-Path $pgoProfile)) {
        $result.availablePgoHash = (Get-FileHash $pgoProfile -Algorithm SHA256).Hash
        $result.pgoHash = $result.availablePgoHash
    }
    $result.gameBuildProfiles = @($script:gameBuildProfiles.ToArray())
    $result.pgoAppliedScope = 'last-successful-game-build'
    $result.pgoApplied = if ($script:gameBuildProfiles.Count) { $script:gameBuildProfiles[-1].pgoApplied } else { $null }
    $result.patches = @(Get-RuntimePatches | ForEach-Object {
        [ordered]@{name=$_.Name; sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
    })
    $name = 'pipeline-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'
    [IO.File]::WriteAllText((Join-Path $logs $name), ($result | ConvertTo-Json -Depth 6))
}

function Need($p, $what) { if (-not (Test-Path $p)) { throw "Missing $what : $p" } }
function Barra($p) { $p -replace '\\', '/' }
# --- gow-native.boot (engine/patches/25, zzz-326) -------------------------------------------------------------------
# The installation can be moved or copied, so the boot profile records the installation root relative to its own folder
# and every path inside the installation '@'-relative to that root; the runtime resolves them without knowing where the
# installation is. Anything outside it (a player's ISO, AppData) stays absolute, and another Windows drive has no
# relative form at all, so it stays absolute too.
function Get-GowRelativePath([string]$desde, [string]$ruta) {
    if (-not $desde -or -not $ruta) { return '' }
    try {
        $sep = [IO.Path]::DirectorySeparatorChar
        $alt = [IO.Path]::AltDirectorySeparatorChar
        # A bare POSIX path reads as a *relative* Uri, so build the file URI explicitly on every host.
        $comoUri = {
            param([string]$p)
            $p = $p -replace '\\', '/'
            if ($p -match '^[a-zA-Z]:') { $p = '/' + $p }
            return [Uri]("file://$p")
        }
        $desdeAbsoluto = [IO.Path]::GetFullPath($desde).TrimEnd($sep, $alt)
        $rutaAbsoluta = [IO.Path]::GetFullPath($ruta).TrimEnd($sep, $alt)
        if ($desdeAbsoluto -eq $rutaAbsoluta) { return '.' } # the boot file sits in the installation root itself
        $base = & $comoUri ($desdeAbsoluto + $sep)
        $destino = & $comoUri $rutaAbsoluta
        if ($base.Scheme -ne $destino.Scheme -or $base.Host -ne $destino.Host) { return '' }
        $relativa = [Uri]::UnescapeDataString($base.MakeRelativeUri($destino).ToString())
        # Another drive has no relative form: MakeRelativeUri returns an absolute URI there.
        if ($relativa -match '^[a-zA-Z][a-zA-Z0-9+.-]*:' -or $relativa.StartsWith('/')) { return '' }
        return ($relativa -replace '\\', '/')
    } catch { return '' }
}
# '@'-relative to the installation when the path is inside it, otherwise unchanged (absolute paths keep working).
function Get-BootProfilePath([string]$raiz, [string]$ruta) {
    if (-not $ruta) { return '' }
    $relativa = Get-GowRelativePath $raiz $ruta
    if (-not $relativa -or $relativa -eq '.' -or $relativa.StartsWith('../') -or $relativa.StartsWith('..\\')) { return $ruta }
    return '@' + $relativa
}
function Format-BootProfile([string]$carpetaBoot, [string]$raiz, [string]$elf, [string[]]$lineas = @()) {
    $raizRelativa = Get-GowRelativePath $carpetaBoot $raiz
    if (-not $raizRelativa) { $raizRelativa = [IO.Path]::GetFullPath($raiz) } # another drive: absolute still resolves
    $texto = "GOW_NATIVE_BOOT_V2`n$raizRelativa`n$(Get-BootProfilePath $raiz $elf)`n"
    foreach ($linea in $lineas) { if ($linea) { $texto += "$linea`n" } }
    return $texto
}
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

