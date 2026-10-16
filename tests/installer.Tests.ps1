# Tests for install.ps1's own functions, under Windows PowerShell 5.1 and PowerShell 7 (no Pester needed):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\installer.Tests.ps1
# The functions are taken out of install.ps1 with the PowerShell parser and defined here, so the installer itself
# never runs. Exit code: the number of failed checks.
$ErrorActionPreference = 'Stop'
$Top = Split-Path -Parent $PSScriptRoot
$script:failed = 0
$script:passed = 0
function Check($name, $got, $want) {
    if ([string]$got -ceq [string]$want) { $script:passed++ }
    else { $script:failed++; Write-Host "FAIL $name`n  got:  [$got]`n  want: [$want]" -ForegroundColor Red }
}

# the functions under test, straight from install.ps1
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Top "install.ps1"), [ref]$null, [ref]$null)
$want = 'LoadLanguage', 'T', 'NormalizeAnswer', 'Gib', 'RegionOnDisk'
$defs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $want -contains $n.Name }, $true)
foreach ($d in $defs) { . ([scriptblock]::Create($d.Extent.Text)) }
foreach ($w in 'LoadLanguage', 'T', 'NormalizeAnswer') {
    if (-not (Get-Command $w -CommandType Function -ErrorAction SilentlyContinue)) { Write-Host "FAIL: $w not found in install.ps1"; exit 99 }
}
$script:Msg = New-Object 'System.Collections.Generic.Dictionary[string,string]'

# ---- T: every translation, every placeholder --------------------------------------------------------------------
$argsT = 'A1', 'B2', 'C3', 'D4', 'E5', 'F6'
foreach ($lang in 'tr', 'zh') {
    LoadLanguage $lang
    $lines = [IO.File]::ReadAllLines((Join-Path (Join-Path $Top "i18n") "$lang.tsv"), [Text.Encoding]::UTF8)
    foreach ($line in $lines) {
        $i = $line.IndexOf("`t")
        if ($i -le 0 -or $line.StartsWith('#')) { continue }
        $key = $line.Substring(0, $i); $val = $line.Substring($i + 1)
        for ($k = 1; $k -le 6; $k++) { $val = $val.Replace("{$k}", $argsT[$k - 1]) }
        Check "T $lang $key" (T $key @argsT) $val
    }
}
LoadLanguage 'en'
Check 'T english' (T 'device: {1}' 'F50 / MU300') 'device: F50 / MU300'
Check 'T untranslated' (T 'nobody translated {1} {2}' 'x' 'y') 'nobody translated x y'
Check 'T no args' (T 'plain {1}') 'plain {1}'
# the dictionary is case-sensitive: two messages may differ only in case
LoadLanguage 'tr'
Check 'T case' (T 'DEVICE: {1}' 'x') 'DEVICE: x'

# ---- NormalizeAnswer --------------------------------------------------------------------------------------------
$cases = @{
    'evet' = 'yes'; 'e' = 'yes'; 'y' = 'yes'; "$([char]0x662F)" = 'yes'
    ('hay' + [char]0x131 + 'r') = 'no'; 'hayir' = 'no'; 'n' = 'no'; "$([char]0x5426)" = 'no'
    ('g' + [char]0xFC + 'ncelle') = 'update'; 'guncelle' = 'update'; "$([char]0x66F4)$([char]0x65B0)" = 'update'
    'sil' = 'wipe'; 'INSTALL' = 'INSTALL'; 'overwrite' = 'overwrite'; '6.18' = '6.18'
}
foreach ($k in $cases.Keys) { Check "NormalizeAnswer $k" (NormalizeAnswer $k) $cases[$k] }

# ---- Gib (the sizes the free-space check prints) ----------------------------------------------------------------
if (Get-Command Gib -ErrorAction SilentlyContinue) {
    Check 'Gib' ((Gib 34828075008) -replace ',', '.') '32.4 GiB'
}

# Only evaluate the extracted guard/loop, never execute an installer or adb.
$disk = [int64]33554432
foreach ($case in @(@(-1, $false), @(0, $true), @(17179867136, $true), @(17179867137, $false), @(27762098176, $false))) {
    Check "RegionOnDisk $($case[0])" (RegionOnDisk $case[0]) $case[1]
}
$uninstallText = [IO.File]::ReadAllText((Join-Path $Top 'uninstall.ps1'))
$guard = ($uninstallText -split "`n" | Where-Object { $_ -match 'if \(\$cand -lt 0 -or' })
Check 'uninstall bounds guard exists' ([bool]$guard) $true
if ($guard) {
    $loop = 'foreach ($cand in @(-1, 0, 17179867136, 17179867137, 27762098176)) { ' + $guard + '; $cand }'
    Check 'uninstall bounded probes' ((& ([scriptblock]::Create($loop))) -join ',') '0,17179867136'
}

Write-Host "$script:passed passed, $script:failed failed"
exit $script:failed
