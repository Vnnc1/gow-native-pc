# Replay a disc movie with PCM recording and a private card copy.
# -NewGame replaces the intro; completion then means reaching gameplay instead of the menu.
param([Parameter(Mandatory=$true)][string]$Runner,
      [Parameter(Mandatory=$true)][string]$Elf,
      [Parameter(Mandatory=$true)][string]$Card,
      [ValidatePattern('^[A-Za-z0-9_]+$')][string]$Movies='A01MP02',
      [string]$Warp='',
      [int]$Seconds=90,
      [switch]$NewGame,
      [switch]$RequireCompletion,
      [switch]$Visible,
      [int]$ExpectedLastPicture=-1,
      [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
if ($Warp -and ($NewGame -or $RequireCompletion)) { throw 'Warp cannot be combined with NewGame or RequireCompletion' }
$Runner=(Resolve-Path -LiteralPath $Runner).Path
$Elf=(Resolve-Path -LiteralPath $Elf).Path
$Card=(Resolve-Path -LiteralPath $Card).Path
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new output directory' }
$out=(New-Item -ItemType Directory -Path $OutputDirectory).FullName
Copy-Item -LiteralPath $Card -Destination (Join-Path $out 'card.ps2')
. (Join-Path $PSScriptRoot '../pipeline/modules/process.ps1')
$settings=@{GOW_MC0=(Join-Path $out 'card.ps2');GOW_AUDIO='0';GOW_AUDIO_PCM=(Join-Path $out 'output.s16le');GOW_AUDIO_RAW=(Join-Path $out 'mixed.s16le');GOW_AUDIO_STATS='1';GOW_MPEG_DIAG='1';GOW_PAD_TEST='1';GOW_PAD_GUION='99999:select';GOW_PAD_CAPTURAS='20,40,80';GOW_FAST_BOOT='0';GOW_SKIP_FMV='0';GOW_WINDOW_HIDDEN='1';GOW_MOVIE_OVERRIDE=$Movies;GOW_BONUS_MOVIE='24';GOW_BONUS_MOVIE_DELAY='8';GOW_VU1N_X64='1';PS2X_GS_HW='1';PS2X_GS_WORKER='1';TOBIICHI_PANORAMICO='16:9'}
if ($Visible) { $settings.GOW_WINDOW_HIDDEN='0'; $settings.GOW_AUDIO='1' }
if ($ExpectedLastPicture -ge 0) { $settings.GOW_MPEG_PICDUMP=[string]$ExpectedLastPicture }
# FAST_BOOT is presence-based; the intro route must leave it unset.
if ($NewGame) {
    $settings.Remove('GOW_FAST_BOOT'); $settings.Remove('GOW_BONUS_MOVIE')
    Remove-Item env:GOW_FAST_BOOT,env:GOW_BONUS_MOVIE -ErrorAction SilentlyContinue
    $settings.GOW_PAD_GUION='5:start,12:x,18:x,24:x,30:x,36:x,42:x,48:x'
} else { $settings.GOW_FAST_BOOT='1' }
if ($Warp) {
    $settings.Remove('GOW_MOVIE_OVERRIDE'); $settings.Remove('GOW_BONUS_MOVIE')
    Remove-Item env:GOW_MOVIE_OVERRIDE,env:GOW_BONUS_MOVIE -ErrorAction SilentlyContinue
    $settings.GOW_WARP=$Warp
    $settings.GOW_PAD_GUION='5:start,12:x,18:x,24:x,30:x,36:x,42:x,48:x'
    $settings.GOW_PAD_CAPTURAS='10,80,140'
}
foreach($key in $settings.Keys) { Set-Item "env:$key" $settings[$key] }
$p=Start-Process -FilePath $Runner -ArgumentList ('"'+$Elf+'"') -WorkingDirectory $out -WindowStyle Hidden -RedirectStandardOutput (Join-Path $out 'stdout.log') -RedirectStandardError (Join-Path $out 'stderr.log') -PassThru
$null=$p.Handle
Write-Output "Movie test: $out; PID=$($p.Id)"
for($t=0;$t -lt $Seconds -and -not $p.HasExited;$t+=5) { Start-Sleep 5 }
if(-not $p.HasExited) { $null=Close-GameWindow $p.Id; $null=$p.WaitForExit(15000) }
$forced=-not $p.HasExited
if($forced) { Stop-Process -Id $p.Id; $p.WaitForExit() }
$p.Refresh()
$log=Get-Content (Join-Path $out 'stderr.log') -Raw
$loads=[regex]::Matches($log, '(?im)^\[gow-fmv\].*' + [regex]::Escape($Movies) + '\s*$')
$played=$loads.Count -gt 0 -and $log.Substring($loads[0].Index) -match '\[MPEG:sync\] frame=30 '
$completed=$loads.Count -gt 0 -and $log.Substring($loads[0].Index) -match '\[gow-fmv\] menu sees movie state (10|11) -> 0'
if ($NewGame) {
    $completed=$loads.Count -gt 0 -and $log.Substring($loads[0].Index) -match '\[gow-pad2:test\] state=11 .*levelReady=1 .*movie=0'
}
$guestError=$log -match 'guest-branch:missing-target|Unhandled|access violation'
$lastPicture=$ExpectedLastPicture -lt 0 -or (Test-Path -LiteralPath (Join-Path $out "mpeg_pic_$ExpectedLastPicture.ppm"))
@{exitCode=$p.ExitCode;forced=$forced;movies=$Movies;warp=$Warp;seconds=$Seconds;elf=$Elf;played=$played;completed=$completed;newGame=[bool]$NewGame;requireCompletion=[bool]$RequireCompletion;visible=[bool]$Visible;guestError=$guestError;expectedLastPicture=$ExpectedLastPicture;lastPicture=$lastPicture} | ConvertTo-Json | Set-Content (Join-Path $out 'summary.json')
if($forced -or $p.ExitCode -ne 0 -or -not $played -or ($RequireCompletion -and -not $completed) -or -not $lastPicture -or $guestError) { exit 1 }
