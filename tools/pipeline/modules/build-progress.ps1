# Ninja can regenerate its build graph and run nested dependency builds first.
# Their [done/total] counters do not describe the requested game target.
function New-GameBuildProgress([string]$directory) {
    return @{ directory = [IO.Path]::GetFullPath($directory).Replace('\', '/').TrimEnd('/'); configuring = $false; lastPercent = -1 }
}

function Read-GameBuildProgress([hashtable]$state, [string]$line) {
    if ($line -match '^\[\d+/\d+\]\s+Re-running CMake') {
        $state.configuring = $true
        return
    }
    if ($state.configuring) {
        # Nested CMake projects also print this marker; resume only for the outer build directory.
        if ($line -match '^-- Build files have been written to:\s*(.+)$') {
            $directory = $Matches[1].Trim().Replace('\', '/').TrimEnd('/')
            if ($directory -eq $state.directory) { $state.configuring = $false }
        }
        return
    }
    if ($line -notmatch '^\[(\d+)/(\d+)\]\s+(.+)$') { return }
    $done = [long]$Matches[1]; $total = [long]$Matches[2]; $action = $Matches[3]
    if ($total -le 0 -or $done -lt 0 -or $done -gt $total -or $action -like 'Re-checking globbed directories*') { return }
    $percent = [int][math]::Floor(100.0 * $done / $total)
    $changed = $percent -ne $state.lastPercent
    $state.lastPercent = $percent
    return [pscustomobject]@{ done = $done; total = $total; changed = $changed; linking = $action -like 'Linking CXX executable*' }
}
