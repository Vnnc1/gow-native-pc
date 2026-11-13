# data/<game>/languages.json records the prepared-disc paths relative to the checkout root (tools/disc/prepare.py), so a
# moved or copied installation still finds its discs. Languages() must hand the pipeline absolute paths either way: a
# relative entry is resolved against the root, an absolute one (a player's own manifest, an older preparation) is kept.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
. (Join-Path $root 'tools/pipeline/modules/process.ps1')
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('gow-languages-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $scratch | Out-Null
try {
    $data = $scratch
    $relative = 'data/gow1/discs/usa/SCUS_973.99'
    $outside = Join-Path $scratch 'elsewhere/SCES_531.33'
    $manifest = [ordered]@{
        game = 'gow1'; title = 'fixture'; recompile_elf = $relative
        languages = @(
            [ordered]@{ language = 'en'; label = 'USA'; edition = 'usa'; quality = 'original'; elf = $relative },
            [ordered]@{ language = 'de'; label = 'Europe'; edition = 'europe'; quality = 'standalone'; elf = $outside }
        )
    }
    $file = Join-Path $data 'languages.json'
    [IO.File]::WriteAllText($file, ($manifest | ConvertTo-Json -Depth 4))
    $before = [IO.File]::ReadAllText($file)

    $m = Languages
    if ($m.recompile_elf -ne (Join-Path $root $relative)) {
        throw "Languages must resolve recompile_elf against the checkout root: got $($m.recompile_elf)"
    }
    if ($m.languages[0].elf -ne (Join-Path $root $relative)) {
        throw "A root-relative disc path must resolve against the root: got $($m.languages[0].elf)"
    }
    if ($m.languages[1].elf -ne $outside) {
        throw "A path outside the root must pass through unchanged: got $($m.languages[1].elf)"
    }
    if ([IO.File]::ReadAllText($file) -ne $before) {
        throw 'Languages must not rewrite the manifest: prepare.py stays its only writer'
    }
    Write-Host 'PASS: root-relative disc paths resolve for the pipeline, absolute ones pass through unchanged'
} finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
