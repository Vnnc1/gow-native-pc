# Asks the game to close the way its window's close button does (WM_CLOSE to its GLFW window), which also works while the
# window is hidden (GOW_WINDOW_HIDDEN, engine/patches/15): Process.CloseMainWindow only finds visible windows. Returns the
# number of windows asked.
function Close-GameWindow([int]$procId) {
    if (-not ('GowWindows' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class GowWindows {
    delegate bool EnumProc(IntPtr hwnd, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc proc, IntPtr lParam);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder name, int size);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    public static int Close(uint pid) {
        int asked = 0;
        EnumWindows(delegate (IntPtr hwnd, IntPtr lParam) {
            uint owner;
            GetWindowThreadProcessId(hwnd, out owner);
            var name = new StringBuilder(64);
            GetClassName(hwnd, name, name.Capacity);
            // GLFW30 = the game window (GLFW's helper window has another class)
            if (owner == pid && name.ToString() == "GLFW30") { PostMessage(hwnd, 0x0010 /* WM_CLOSE */, IntPtr.Zero, IntPtr.Zero); asked++; }
            return true;
        }, IntPtr.Zero);
        return asked;
    }
}
'@
    }
    return [GowWindows]::Close([uint32]$procId)
}
function Languages {
    $f = Join-Path $data 'languages.json'
    if (-not (Test-Path $f)) { throw 'no prepared disc: run the "discs" stage with your ISO' }
    return Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Invoke-GameRecording([string]$exe, [string]$elf, [int]$seconds, [hashtable]$variables, [int]$closeTimeout = 15000) {
    $saved = @{}
    $process = $null
    try {
        foreach ($key in $variables.Keys) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, $variables[$key], 'Process')
        }
        $process = Start-Process -FilePath $exe -ArgumentList "`"$elf`"" -WorkingDirectory $logs -WindowStyle Hidden -PassThru
        # Retain the process handle so Windows PowerShell can read ExitCode after the process exits.
        $null = $process.Handle
        try { $process.PriorityClass = 'Normal' } catch { }
        for ($elapsed = 0; $elapsed -lt $seconds -and -not $process.HasExited; $elapsed += 5) {
            Start-Sleep 5
            Write-Host "@@progress $([math]::Min($elapsed + 5, $seconds)) $seconds"
        }
        if (-not $process.HasExited) {
            $null = Close-GameWindow $process.Id
            $null = $process.WaitForExit($closeTimeout)
        }
        if (-not $process.HasExited) { throw 'Recording did not close gracefully; no successful optimization is recorded' }
        if ($process.ExitCode -ne 0) { throw "Recording failed (rc=$($process.ExitCode))" }
    } finally {
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }
}

