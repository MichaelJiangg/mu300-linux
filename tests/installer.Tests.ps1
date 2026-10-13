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
$want = 'LoadLanguage', 'T', 'NormalizeAnswer', 'Gib', 'ChooseStorage', 'StorageDefault', 'InternalOverCard', 'SdState', 'SdKernelOk', 'InstallEnvText', 'ChooseOpenWrt', 'AdbPubKey', 'BootchainLine', 'BootchainRefused'
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

# ---- ChooseStorage: internal region or SD card -------------------------------------------------------------------
Check 'no card'            (ChooseStorage '' 0 30GB '' '') 'internal'
Check 'card, default'      (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' '') 'internal'
Check 'card, answer sd'    (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' 'sd') 'sd'
Check 'small internal'     (ChooseStorage '/dev/block/mmcblk1p1' 62GB 100MB '' '') 'sd'
Check 'forced internal'    (ChooseStorage '/dev/block/mmcblk1p1' 62GB 100MB 'internal' '') 'internal'
Check 'forced sd'          (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB 'sd' '') 'sd'
$threw = $false; try { ChooseStorage '' 0 30GB 'sd' '' | Out-Null } catch { $threw = $true }
Check 'forced sd, no card' $threw $true
$threw = $false; try { ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' 'usb' | Out-Null } catch { $threw = $true }
Check 'invalid answer'     $threw $true
$threw = $false; try { ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB 'usb' '' | Out-Null } catch { $threw = $true }
Check 'invalid forced'     $threw $true

# ---- ChooseOpenWrt: plain OpenWrt or with the MU300 control panel (install.sh's choose_systems) --------------------
Check 'owrt 3 + 2'         ((ChooseOpenWrt @('ubuntu', 'openwrt') '' '2') -join ' ') 'ubuntu openwrt-luci'
Check 'owrt 2 + 1'         ((ChooseOpenWrt @('openwrt') '' '1') -join ' ') 'openwrt'
Check 'owrt default'       ((ChooseOpenWrt @('openwrt') '' '') -join ' ') 'openwrt'
Check 'owrt preset luci'   ((ChooseOpenWrt @('openwrt') 'luci' '') -join ' ') 'openwrt-luci'
Check 'owrt preset plain'  ((ChooseOpenWrt @('ubuntu', 'openwrt') 'plain' '2') -join ' ') 'ubuntu openwrt'
Check 'owrt one element'   (@(ChooseOpenWrt @('openwrt') 'luci' '').Count) 1
$threw = $false; try { ChooseOpenWrt @('openwrt') 'x' '' | Out-Null } catch { $threw = $true }
Check 'owrt bad preset'    $threw $true
$threw = $false; try { ChooseOpenWrt @('openwrt') '' '7' | Out-Null } catch { $threw = $true }
Check 'owrt bad answer'    $threw $true
# a one-system result unrolls to a plain string, so the call site must wrap it in @() or $OSES[0] is one letter
$bare = ChooseOpenWrt @('openwrt') 'luci' ''
Check 'owrt bare result unrolls'  ($bare -is [string]) $true
$site = [IO.File]::ReadAllText((Join-Path $Top 'install.ps1'))
Check 'owrt call site wraps in @()'  ($site -match '\$OSES = @\(ChooseOpenWrt ') $true
foreach ($pair in @(@('', 'openwrt'), @('luci', 'openwrt-luci'))) {
    $OSES = @(ChooseOpenWrt @('openwrt') $pair[0] '')
    Check "owrt single [$($pair[1])] first"  $OSES[0] $pair[1]
    Check "owrt single [$($pair[1])] count"  $OSES.Count 1
}
# the boot question accepts the names that were chosen: 'openwrt' is not one of them after the second answer
$o = ChooseOpenWrt @('ubuntu', 'openwrt') '' '2'
Check 'boot openwrt-luci ok'  ('openwrt-luci' -in $o) $true
Check 'boot openwrt refused'  ('openwrt' -in $o) $false
# a card that holds an installation already is the default: init starts it before anything internal
Check 'installed card, default'    (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' '' 'yes') 'sd'
Check 'blank card, default'        (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' '' 'no') 'internal'
Check 'foreign card, default'      (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' '' 'foreign') 'internal'
Check 'installed card, internal'   (ChooseStorage '/dev/block/mmcblk1p1' 62GB 30GB '' 'internal' 'yes') 'internal'
Check 'StorageDefault installed'   (StorageDefault 30GB 'yes') 'sd'
Check 'StorageDefault small'       (StorageDefault 100MB 'no') 'sd'
Check 'StorageDefault room'        (StorageDefault 30GB 'no') 'internal'
Check 'internal over card'         (InternalOverCard 'internal' 'yes') $true
Check 'internal, blank card'       (InternalOverCard 'internal' 'no') $false
Check 'internal, foreign card'     (InternalOverCard 'internal' 'foreign') $false
Check 'sd over card'               (InternalOverCard 'sd' 'yes') $false
$src = [IO.File]::ReadAllText((Join-Path $Top 'install.ps1'))
$iO = $src.IndexOf('if (InternalOverCard $where $sdEx) {')
$iA = $src.IndexOf("if ((Ask (T 'Type internal to install to internal storage anyway') 'no') -ne 'internal') { Die (T 'cancelled') }")
Check 'internal over card asks'    ($iO -ge 0 -and $iA -gt $iO -and $iA - $iO -lt 600) $true

# ---- SdState: what is on the card already (ext4 magic at 1080, label at 1144) -------------------------------------
Check 'sd mu300sd'         (SdState '53ef' 'mu300sd') 'yes'
Check 'sd other label'     (SdState '53ef' 'data') 'foreign'
Check 'sd no label'        (SdState '53ef' '') 'foreign'
Check 'sd root label'      (SdState '53ef' 'mu300root') 'foreign'
Check 'sd not ext4'        (SdState '0000' 'mu300sd') 'no'
Check 'sd unreadable'      (SdState '' '') 'no'

# ---- SdKernelOk: a card installation needs a bundle that lists sdcard in ./features ------------------------------
$kd = Join-Path ([IO.Path]::GetTempPath()) ('mu300-k-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $kd | Out-Null
Check 'sd kernel, no features'      (SdKernelOk 1 $kd) $false
Check 'internal, no features'       (SdKernelOk 0 $kd) $true
[IO.File]::WriteAllText((Join-Path $kd 'features'), "other`n")
Check 'sd kernel, other features'   (SdKernelOk 1 $kd) $false
[IO.File]::WriteAllText((Join-Path $kd 'features'), "sdcard`n")
Check 'sd kernel, sdcard'           (SdKernelOk 1 $kd) $true
Remove-Item -Recurse -Force $kd
$src = [IO.File]::ReadAllText((Join-Path $Top 'install.ps1'))
$iUnpack = $src.IndexOf('& tar -xzf "$REL\mu300-kernel-$KERNEL.tar.gz" -C $KMAIN')
$iCheck = $src.IndexOf('if (-not (SdKernelOk $SD_MODE $KMAIN))')
Check 'sd kernel check after unpack' ($iUnpack -ge 0 -and $iCheck -gt $iUnpack) $true

# ---- InstallEnvText: mu300-install.env, the same text tools/storage.sh's write_install_env writes ------------------
$common = @{ OFF = [int64]27762098176; FORMAT = 1; OSES = @('ubuntu', 'openwrt'); WIPE_LEGACY = 0; UPDATE = 0
    BOOT_OS = 'openwrt'; DEFAULT_LINUX = 1; BOOT_ATTEMPTS = 5; IMPORT_HOTSPOT = 1; KERNEL = '6.18'; SYNC_BOOTCHAIN = 1
    PWHASH = '$6$salt$hash/x.y' }
$sdEnv = $common.Clone(); $sdEnv.SIZE = [int64]31914967040; $sdEnv.INT_SIZE = [int64]34776023040; $sdEnv.SD_MODE = 1
$sdEnv.SD_DEV = '/dev/block/mmcblk1p1'; $sdEnv.INTERNAL_EXISTS = 1
$inEnv = $common.Clone(); $inEnv.SIZE = [int64]34776023040; $inEnv.INT_SIZE = [int64]0; $inEnv.SD_MODE = 0
$inEnv.SD_DEV = ''; $inEnv.INTERNAL_EXISTS = 0; $inEnv.FORMAT = 0; $inEnv.UPDATE = 1
$inEnv.ADB = 1; $inEnv.ADB_KEY = ('QAAAA' + ('A' * 694) + '= me@host')
$t = InstallEnvText $sdEnv
Check 'env sd: region'      ($t -match "(?m)^OFF=27762098176\nSIZE=34776023040\nOFF_S=54222848\nSIZE_S=67921920\n") $true
Check 'env sd: card'        ($t -match "(?m)^SD_MODE=1\nSD_DEV=/dev/block/mmcblk1p1\nINTERNAL_EXISTS=1\n") $true
Check 'env sd: format'      ($t -match "(?m)^FORMAT=1\n" -and $t -match "(?m)^UPDATE=0\n") $true
Check 'env sd: oses'        ($t -match '(?m)^OSES="ubuntu openwrt"\n') $true
Check 'env sd: hash'        ($t.EndsWith("SYNC_BOOTCHAIN=1`nPWHASH='`$6`$salt`$hash/x.y'`n")) $true
Check 'env sd: no CR'       ($t.Contains("`r")) $false
$t = InstallEnvText $inEnv
Check 'env internal'        ($t -match "(?m)^OFF=27762098176\nSIZE=34776023040\nOFF_S=54222848\nSIZE_S=67921920\nFORMAT=0\n") $true
Check 'env internal: sd'    ($t -match "(?m)^UPDATE=1\n" -and $t -match "(?m)^SD_MODE=0\nSD_DEV=\nINTERNAL_EXISTS=0\n") $true
Check 'env internal: adb'   ($t -match ("(?m)^ADB=1\nADB_KEY='QAAAA" + ('A' * 694) + "= me@host'\nSYNC_BOOTCHAIN=1\nPWHASH=")) $true
Check 'env sd: adb off'     ((InstallEnvText $sdEnv) -match "(?m)^ADB=0\nADB_KEY=''\n") $true

# ---- AdbPubKey: the installing computer's adb key, safe inside single quotes --------------------------------------
$key = 'QAAAA' + ('A' * 694) + '='
$kf = Join-Path ([IO.Path]::GetTempPath()) "mu300-adbkey-$PID.pub"
[IO.File]::WriteAllText($kf, "$key me@my-pc")
Check 'adbkey: plain'       (AdbPubKey $kf) "$key me@my-pc"
[IO.File]::WriteAllText($kf, "$key evil'`$(reboot) `n")
Check 'adbkey: name cleaned' (AdbPubKey $kf) "$key evilreboot"
[IO.File]::WriteAllText($kf, $key)
Check 'adbkey: no name'     (AdbPubKey $kf) "$key installer"
[IO.File]::WriteAllText($kf, "ssh-rsa AAAAB3NzaC1yc2E me@my-pc")
Check 'adbkey: not adb'     (AdbPubKey $kf) ''
[IO.File]::WriteAllText($kf, ($key.Substring(1)) + ' x')
Check 'adbkey: short'       (AdbPubKey $kf) ''
Remove-Item $kf
Check 'adbkey: missing'     (AdbPubKey $kf) ''

if (Get-Command sh -CommandType Application -ErrorAction SilentlyContinue) {
    foreach ($e in $sdEnv, $inEnv) {
        $vars = (($e.Keys | Sort-Object | ForEach-Object { "$_='$(@($e[$_]) -join ' ')'" }) -join '; ')
        if ($e.SD_MODE -eq 0) { $vars += "; INT_SIZE=''" }
        $shText = ((& sh -c ($vars + '; . ./tools/storage.sh; write_install_env')) -join "`n") + "`n"
        Check "env = storage.sh (SD_MODE=$($e.SD_MODE))" (InstallEnvText $e) $shText
    }
}

# ---- BootchainLine / BootchainRefused: the plan's line from android-bootchain.sh check (storage.sh's bootchain_line) --
LoadLanguage 'en'
Check 'bootchain identical' (BootchainLine "BOOTCHAIN-PLAN a b`r`nboot chain: identical on both slots") 'boot chain:     identical on both slots'
Check 'bootchain differ'    (BootchainLine "BOOTCHAIN-PLAN b a sml trustos`nx") "boot chain:     sml, trustos differ between the slots; Android's slot b is copied to slot a (backed up first)"
Check 'bootchain refused'   (BootchainLine 'BOOTCHAIN-REFUSED: uboot_a and uboot_b differ in size (1 and 2 bytes)') ''
Check 'bootchain reason'    (BootchainRefused "x`nBOOTCHAIN-REFUSED: uboot_a and uboot_b differ in size (1 and 2 bytes)") 'uboot_a and uboot_b differ in size (1 and 2 bytes)'
Check 'bootchain no answer' (BootchainRefused '') 'no answer from the device'

# ---- uninstall.ps1: what is on the card, and the command that erases it -----------------------------------------
$uast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Top "uninstall.ps1"), [ref]$null, [ref]$null)
$udefs = $uast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and @('SdState', 'SdEraseCommand') -contains $n.Name }, $true)
foreach ($d in $udefs) { . ([scriptblock]::Create($d.Extent.Text)) }
Check 'uninstall sd mu300sd'    (SdState '53ef' 'mu300sd') 'yes'
Check 'uninstall sd other'      (SdState '53ef' 'mu300root') 'foreign'
Check 'uninstall sd not ext4'   (SdState '0000' 'mu300sd') 'no'
foreach ($dev in '/dev/block/mmcblk0p1', '/dev/block/mmcblk0', '/dev/block/sda1', '/dev/block/mmcblk1p1 x', '') {
    $threw = $false; try { SdEraseCommand $dev | Out-Null } catch { $threw = $true }
    Check "erase refuses [$dev]" $threw $true
}
$cmd = SdEraseCommand '/dev/block/mmcblk1p1'
Check 'erase command quotes'    ($cmd -match "[`"']") $false
Check 'erase command target'    ($cmd -match ' of=/dev/block/mmcblk1p1 bs=1048576 count=64 ') $true
# the same text tools/storage.sh's sd_erase_cmd builds (and tests/test_installer.py runs against stubs)
if (Get-Command sh -CommandType Application -ErrorAction SilentlyContinue) {
    foreach ($dev in '/dev/block/mmcblk1p1', '/dev/block/mmcblk1') {
        $shCmd = (& sh -c ('unset MU300_SYSFS MU300_MOUNTS; . ./tools/storage.sh; sd_erase_cmd ' + $dev)) -join "`n"
        Check "erase command = storage.sh ($dev)" (SdEraseCommand $dev) $shCmd
    }
}

# ---- the VPN question: yes by default over a system whose VPN is on ---------------------------------------------
$vdefs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and @('VpnOnSystems', 'VpnDefault') -contains $n.Name }, $true)
foreach ($d in $vdefs) { . ([scriptblock]::Create($d.Extent.Text)) }
$T = '/data/local/tmp'
function PushUnix($src, $dst) { $true }
$script:suCmd = ''
$script:suOut = "ubuntu`r`n"
function SuDo($cmd) { $script:suCmd = $cmd; $script:suOut }
Check 'vpn on: ubuntu'          ((VpnOnSystems @('ubuntu', 'openwrt') 'yes' 0 '' 123 456) -join ' ') 'ubuntu'
Check 'vpn on: default yes'     (VpnDefault @(VpnOnSystems @('ubuntu', 'openwrt') 'yes' 0 '' 123 456)) 'yes'
Check 'vpn on: read only'       ($script:suCmd -match '^MU300_OFF=123 MU300_SIZE=456 MU300_RO=1 sh /data/local/tmp/android-mount-mu300root.sh ') $true
Check 'vpn on: no quotes'       ($script:suCmd -match "'") $false
Check 'vpn on: loop variable'   ($script:suCmd -match 'vpn_killswitch_wanted /data/local/tmp/mu300probe/\$o; then echo \$o:ks;') $true
Check 'vpn on: orphan lib'      ($script:suCmd -match '\. /data/local/tmp/vpn-orphan\.sh;') $true
$script:suOut = "ubuntu`nopenwrt:ks`n"
Check 'vpn on: kill switch'     ((VpnOnSystems @('ubuntu', 'openwrt') 'yes' 0 '' 123 456) -join ' ') 'ubuntu openwrt:ks'
Check 'vpn ks: default yes'     (VpnDefault @(VpnOnSystems @('openwrt') 'yes' 0 '' 123 456)) 'yes'
$script:suOut = "ubuntu`r`n"
$null = VpnOnSystems @('ubuntu') 'yes' 1 '/dev/block/mmcblk1p1' 0 0
Check 'vpn on: the card'        ($script:suCmd -match '^MU300_SD_DEV=/dev/block/mmcblk1p1 MU300_RO=1 ') $true
$script:suOut = ''
Check 'vpn off: default no'     (VpnDefault @(VpnOnSystems @('ubuntu', 'openwrt') 'yes' 0 '' 123 456)) 'no'
$script:suOut = "openwrt`n"
Check 'vpn on elsewhere: no'    (VpnDefault @(VpnOnSystems @('ubuntu') 'yes' 0 '' 123 456)) 'no'
$script:suCmd = ''
Check 'no install: default no'  (VpnDefault @(VpnOnSystems @('ubuntu') 'no' 0 '' 123 456)) 'no'
Check 'no install: no probe'    $script:suCmd ''

# ---- making room (issue #32): install.sh's offer_repartition, here OfferRepartition -------------------------------
$rnames = 'Quiet', 'FreeRegion', 'GptShow', 'RepartitionPlan', 'RepartitionSectors', 'LayoutFigures', 'GptTool', 'GptDump', 'OfferRepartition'
$rdefs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $rnames -contains $n.Name }, $true)
foreach ($d in $rdefs) { . ([scriptblock]::Create($d.Extent.Text)) }
foreach ($w in $rnames) {
    if (-not (Get-Command $w -CommandType Function -ErrorAction SilentlyContinue)) { Write-Host "FAIL: $w not found in install.ps1"; exit 99 }
}
LoadLanguage 'en'
# The figures of the 64 GB eMMC (FINDINGS #9): 122159104 sectors, last usable LBA 122155007, userdata from sector
# 12275712, 20 GiB of it at the factory. Issue #32 gives no sectors: its layout is this one with userdata extended to
# the last usable LBA (tests/fakegpt.py's vendor64).
[int64]$D64 = 122159104; [int64]$U64 = 122155007; [int64]$F64 = 12275712
# the free region: the factory gap, and the table that ends at the end of the disk
$r = FreeRegion 54218752 $D64
Check 'region factory: start'   $r.Start 54222848
Check 'region factory: end'     $r.End 122150912
# userdata up to the last usable sector: the two boundaries cross by 4 MiB, the "-4 MiB" of the issue ...
Check 'region #32: the boundaries cross'  (([math]::Floor(($D64 - 34) / 4096 - 1) * 4096 - [math]::Floor(($U64 + 1) / 4096 + 1) * 4096) * 512 / 1MB) (-4)
# ... and that is an empty region at the end of the disk, not a negative one
$r = FreeRegion ($U64 + 1) $D64
Check 'region #32: start'       $r.Start $D64
Check 'region #32: size'        ($r.End - $r.Start) 0
$r = FreeRegion 33550336 33554432                       # issue #65: 2 MiB behind the last partition of a 16 GiB eMMC
Check 'region #65: size'        ($r.End - $r.Start) 0
$r = FreeRegion 113766400 $D64                          # #32 after 4 GiB were made: 4 MiB of them go to the alignment
Check 'region after the shrink' (($r.End - $r.Start) * 512 / 1MB) 4092

# what the tool says about the table
$g = GptShow @('disk            122159104 sectors (58.25 GiB)', 'LAST_NAME=userdata', "LAST_FIRST=$F64", "LAST_END=$U64`r", "USABLE_END=$U64")
Check 'show: first'             $g.First $F64
Check 'show: end'               $g.End $U64
Check 'show: usable end'        $g.UsableEnd $U64
Check 'show: one missing'       ($null -eq (GptShow @("LAST_FIRST=$F64", "LAST_END=$U64"))) $true
Check 'show: nothing'           ($null -eq (GptShow @())) $true
Check 'show: not a number'      ($null -eq (GptShow @("LAST_FIRST=$F64", 'LAST_END=x', "USABLE_END=$U64"))) $true

# the split: 4 GiB stay with Android, Linux needs 800 MiB
$p = RepartitionPlan $F64 $U64 $U64
Check 'plan #32: to share'      $p.Total 109879296
Check 'plan #32: free'          $p.Free 0
Check 'plan #32: most for Linux' $p.MaxLinux 101490688
Check 'plan #32: ok'            $p.Ok $true
Check 'plan #32: missing'       $p.Missing 0
Check 'plan: Android keeps'     $p.MinAndroid 8388608
Check 'plan: Linux needs'       $p.MinLinux 1638400
Check 'plan factory: free'      (RepartitionPlan $F64 54218751 $U64).Free 67936256
$p = RepartitionPlan 113766400 $U64 $U64                # 4 GiB of userdata in all
Check 'plan small: ok'          $p.Ok $false
Check 'plan small: missing'     $p.Missing 1638400
$p = RepartitionPlan ($U64 - 8388608 - 1638400 + 1) $U64 $U64      # exactly 4 GiB + 800 MiB
Check 'plan exact: ok'          $p.Ok $true
Check 'plan exact: most'        $p.MaxLinux 1638400

# the answer to "How many GiB for Linux?"
foreach ($c in @(@('4', 'ok', 8388608), @('2.5', 'ok', 5242880), @('2.', 'ok', 4194304), @('48.39', 'ok', 101478400),
        @('0.79', 'ok', 1654784), @('0.5', 'small', 1048576), @('.5', 'small', 1048576), @('0', 'small', 0),
        @('48.4', 'large', 101498880), @('100', 'large', 209715200), @('99999999999999999999', 'large', 0),
        @('', 'nan', 0), @('abc', 'nan', 0), @('4,5', 'nan', 0), @('1.2.3', 'nan', 0), @('.', 'nan', 0),
        @('-4', 'nan', 0), @('4 GiB', 'nan', 0), @('1e3', 'nan', 0))) {
    $s = RepartitionSectors $c[0] 1638400 101490688
    Check "sectors [$($c[0])] state"    $s.State $c[1]
    Check "sectors [$($c[0])] sectors"  $s.Sectors $c[2]
}
# a point is a point where the computer writes numbers with a comma
$culture = [Threading.Thread]::CurrentThread.CurrentCulture
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('tr-TR')
$s = RepartitionSectors '2.5' 1638400 101490688
[Threading.Thread]::CurrentThread.CurrentCulture = $culture
Check 'sectors 2.5 in Turkish'  $s.Sectors 5242880

# the numbers of a refusal
$f = @(LayoutFigures $D64 ($U64 + 1) 0 $null $null)
Check 'figures: two lines'      $f.Count 2
Check 'figures: the eMMC'       ($f[0] -match '^  eMMC: 58[.,]\d GiB \(122159104 sectors\); the partitions end at sector 122155008; free after them: 0 MiB$') $true
Check 'figures: missing'        $f[1] '  needed behind the partitions: 700 MiB; missing: 700 MiB'
Check 'figures: part missing'   (@(LayoutFigures $D64 ($U64 + 1) (100MB + 1) $null $null)[1]) '  needed behind the partitions: 700 MiB; missing: 600 MiB'
$i = @{ First = [int64]113766400; End = $U64; UsableEnd = $U64 }
$f = @(LayoutFigures $D64 ($U64 + 1) 0 $i (RepartitionPlan $i.First $i.End $i.UsableEnd))
Check 'figures: four lines'     $f.Count 4
Check 'figures: userdata'       ($f[2] -match '^  userdata now:         4[.,]0 GiB \(sectors 113766400\.\.122155007\)$') $true
Check 'figures: the split'      $f[3] '  to share by shrinking it: 4096 MiB up to sector 122155007; needed: 4896 MiB (4096 MiB Android + 800 MiB Linux); missing: 800 MiB'

# where there is no room, room is offered - the refusal with "a different layout" is what OfferRepartition says of a
# table it does not know
$site = [IO.File]::ReadAllText((Join-Path $Top 'install.ps1'))
$iGate = $site.IndexOf('if ($SD_MODE -eq 0 -and $SIZE -lt 700MB) {')
$iOffer = $site.IndexOf("    OfferRepartition `$disk `$lastEnd `$SIZE")
Check 'no room: room is offered' ($iGate -ge 0 -and $iOffer -gt $iGate -and $iOffer - $iGate -lt 900) $true
Check 'no room: then it ends'   ($site.Substring($iOffer, 200) -match '^[^\n]*\n    exit 0\r?\n\}') $true
Check 'ERASE is the word itself' ($site -match "wipe Android''s data'\) ''\) -cne 'ERASE'\) \{ Die ") $true

# The whole path against a device that is three stubs: SuDoToFile reads the two pieces of the partition table, adb
# pushes files and reboots, SuDo runs what the installer sends as root - and counts everything else as a mistake.
# The table comes from tests/fakegpt.py and the real tools/resize-last-partition.py edits it, so Python is needed.
$py = $null
foreach ($n in 'python', 'python3', 'py') {
    foreach ($c in @(Get-Command $n -CommandType Application -ErrorAction SilentlyContinue)) {
        $exe = $(if ($c.Source) { $c.Source } else { $c.Path })
        $ok = $false
        try { & $exe -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>$null | Out-Null; $ok = ($LASTEXITCODE -eq 0) } catch { }
        if ($ok -and -not $py) { $py = $exe }
    }
}
if (-not $py) {
    if ($env:GITHUB_ACTIONS) { Check 'python for the make-room tests' 'none' 'found' }
    else { Write-Host 'no Python 3 here: the make-room path was not run against the fake device' }
} else {
    function Sha256Hex([byte[]]$b) {
        $h = [Security.Cryptography.SHA256]::Create()
        try { return (-join ($h.ComputeHash($b) | ForEach-Object { $_.ToString('x2') })) } finally { $h.Dispose() }
    }
    $fx = Join-Path ([IO.Path]::GetTempPath()) ('mu300-gpt-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $fx | Out-Null
    $T = '/data/local/tmp'
    function FakeDevice([string]$Layout, [switch]$SameWork) {
        & $py (Join-Path (Join-Path $Top 'tests') 'fakegpt.py') (Join-Path $fx 'dev') $Layout
        $script:dev = @{ disk = $D64; head = [IO.File]::ReadAllBytes((Join-Path $fx 'dev.head')); tail = [IO.File]::ReadAllBytes((Join-Path $fx 'dev.tail'))
            files = @{}; cmds = (New-Object System.Collections.ArrayList); bad = 0; rebooted = $false; wiped = $false
            shortPush = $false; deafDisk = $false; noRead = $false }
        $script:dev.head0 = Sha256Hex $script:dev.head; $script:dev.tail0 = Sha256Hex $script:dev.tail
        if (-not $SameWork) { $script:Work = Join-Path $fx ('work-' + [guid]::NewGuid()) }
    }
    function Python { & $py @args }
    function SuDoToFile($cmd, $path) {
        [void]$script:dev.cmds.Add("pull: $cmd")
        if ($script:dev.noRead) { return }
        if ($cmd -ceq 'dd if=/dev/block/mmcblk0 bs=512 count=34 2>/dev/null') { [IO.File]::WriteAllBytes($path, $script:dev.head) }
        elseif ($cmd -ceq "dd if=/dev/block/mmcblk0 bs=512 skip=$($script:dev.disk - 33) count=33 2>/dev/null") { [IO.File]::WriteAllBytes($path, $script:dev.tail) }
        else { $script:dev.bad++ }
    }
    function adb {
        [void]$script:dev.cmds.Add("adb: $($args -join ' ')")
        if ($args[0] -eq 'push' -and $args.Count -eq 3) {
            [byte[]]$b = [IO.File]::ReadAllBytes([string]$args[1])
            if ($script:dev.shortPush) { $b = [byte[]]($b[0..511]) }
            $script:dev.files[[string]$args[2]] = $b
        } elseif ($args[0] -eq 'reboot' -and $args.Count -eq 1) { $script:dev.rebooted = $true }
        else { $script:dev.bad++ }
    }
    function SuDo($cmd) {
        [void]$script:dev.cmds.Add("su: $cmd")
        $seek = $script:dev.disk - 33
        if ($cmd -cmatch '^sha256sum (/data/local/tmp/new\.(head|tail))$') {
            $f = $Matches[1]
            if ($script:dev.files.ContainsKey($f)) { return "$(Sha256Hex $script:dev.files[$f])  $f`r" } else { return '' }
        }
        if ($cmd -ceq "dd if=/data/local/tmp/new.tail of=/dev/block/mmcblk0 bs=512 seek=$seek conv=fsync 2>/dev/null") {
            if (-not $script:dev.deafDisk) { $script:dev.tail = $script:dev.files['/data/local/tmp/new.tail'] }
        } elseif ($cmd -ceq 'dd if=/data/local/tmp/new.head of=/dev/block/mmcblk0 bs=512 conv=fsync 2>/dev/null') {
            if (-not $script:dev.deafDisk) { $script:dev.head = $script:dev.files['/data/local/tmp/new.head'] }
        } elseif ($cmd -ceq 'dd if=/dev/zero of=/dev/block/by-name/userdata bs=1M count=32 conv=fsync 2>/dev/null') { $script:dev.wiped = $true }
        elseif ($cmd -cne 'sync; rm -f /data/local/tmp/new.head /data/local/tmp/new.tail' -and $cmd -cne 'rm -f /data/local/tmp/new.head /data/local/tmp/new.tail') { $script:dev.bad++ }
        return ''
    }
    function Die($m) { throw "DIE: $m" }
    function Say($m) { [void]$script:out.Add("==> $m") }
    function Ask($question, $default) {
        [void]$script:asked.Add([string]$question)
        if ($script:answers.Count -eq 0) { throw "a question nobody answers: $question" }
        $a = [string]$script:answers.Dequeue()
        if ([string]::IsNullOrWhiteSpace($a)) { return $default } else { return (NormalizeAnswer $a.Trim()) }
    }
    # what the installer prints is kept, not shown; a failed check still is
    function Write-Host {
        if ("$($args[0])" -like 'FAIL*') { Microsoft.PowerShell.Utility\Write-Host @args } else { [void]$script:out.Add("$($args[0])") }
    }
    function RunOffer([string[]]$Answers) {
        $script:answers = New-Object 'System.Collections.Generic.Queue[string]'
        foreach ($a in @($Answers)) { $script:answers.Enqueue($a) }
        $script:out = New-Object System.Collections.ArrayList
        $script:asked = New-Object System.Collections.ArrayList
        $script:died = ''
        try { OfferRepartition $script:dev.disk ($U64 + 1) 0 } catch { $script:died = "$($_.Exception.Message)" }
    }
    function Writes { @($script:dev.cmds | Where-Object { $_ -match ' of=' }) }
    function Untouched { ((Sha256Hex $script:dev.head) -eq $script:dev.head0) -and ((Sha256Hex $script:dev.tail) -eq $script:dev.tail0) -and -not $script:dev.wiped -and -not $script:dev.rebooted -and (Writes).Count -eq 0 }
    function Printed([string]$Pattern) { [bool](@($script:out | Where-Object { $_ -match $Pattern }).Count) }
    $tailDd = "su: dd if=/data/local/tmp/new.tail of=/dev/block/mmcblk0 bs=512 seek=$($D64 - 33) conv=fsync 2>/dev/null"
    $headDd = 'su: dd if=/data/local/tmp/new.head of=/dev/block/mmcblk0 bs=512 conv=fsync 2>/dev/null'
    $zeroDd = 'su: dd if=/dev/zero of=/dev/block/by-name/userdata bs=1M count=32 conv=fsync 2>/dev/null'

    # -Check: the figures, no question, nothing written
    $Check = $true
    FakeDevice 'vendor64'; RunOffer @()
    $Check = $false
    Check 'check: no error'         $script:died ''
    Check 'check: userdata'         (Printed '^  userdata now:         52[.,]4 GiB \(sectors 12275712\.\.122155007\)$') $true
    Check 'check: free behind it'   (Printed '^  free behind it:       0[.,]0 GiB$') $true
    Check 'check: to share'         (Printed '^  to share:             52[.,]4 GiB$') $true
    Check 'check: erases, it says'  (Printed 'ERASES everything in Android') $true
    Check 'check: says so'          ($script:out[$script:out.Count - 1]) '  -Check writes nothing. Run the installer without it to make room.'
    Check 'check: no question'      $script:asked.Count 0
    Check 'check: device untouched' (Untouched) $true
    Check 'check: reads the table only' (($script:dev.cmds -join '|')) "pull: dd if=/dev/block/mmcblk0 bs=512 count=34 2>/dev/null|pull: dd if=/dev/block/mmcblk0 bs=512 skip=$($D64 - 33) count=33 2>/dev/null"
    Check 'check: nothing unexpected' $script:dev.bad 0

    # the default answer is no
    FakeDevice 'vendor64'; RunOffer @('')
    Check 'no: nothing changed'     $script:died 'DIE: nothing was changed.'
    Check 'no: one question'        ($script:asked -join '|') 'Make room by shrinking userdata? (yes/no)'
    Check 'no: device untouched'    (Untouched) $true
    Check 'no: nothing pushed'      (@($script:dev.cmds | Where-Object { $_ -like 'adb:*' }).Count) 0

    # yes, a size, and then anything but ERASE (erase, yes, nothing at all)
    foreach ($word in 'erase', 'yes', '', 'ERASE!') {
        FakeDevice 'vendor64'; RunOffer @('yes', '4', $word)
        Check "not ERASE [$word]: nothing changed"   $script:died 'DIE: nothing was changed.'
        Check "not ERASE [$word]: device untouched"  (Untouched) $true
        Check "not ERASE [$word]: nothing pushed"    (@($script:dev.cmds | Where-Object { $_ -like 'adb:*' }).Count) 0
        Check "not ERASE [$word]: no new table made" (Test-Path (Join-Path (Join-Path $script:Work 'gpt') 'new.head')) $false
    }

    # yes, sizes that are refused, 4 GiB, ERASE, reboot
    FakeDevice 'vendor64'; RunOffer @('evet', 'abc', '0.5', '100', '', 'ERASE', '')
    $gd = Join-Path $script:Work 'gpt'
    Check 'shrink: no error'        $script:died ''
    Check 'shrink: not a number'    (Printed '^  give a number, like 4 or 2\.5$') $true
    Check 'shrink: too small'       (Printed '^  too small: Linux needs at least 0[.,]8 GiB$') $true
    Check 'shrink: too large'       (Printed '^  too large: Android would be left with less than 4[.,]0 GiB$') $true
    Check 'shrink: what Android keeps' (Printed '^  userdata \(Android\):   48[.,]4 GiB$') $true
    Check 'shrink: what Linux gets' (Printed '^  Linux region:         4[.,]0 GiB$') $true
    Check 'shrink: questions'       ($script:asked -join '|') ('Make room by shrinking userdata? (yes/no)|' + ('How many GiB for Linux? (the rest stays with Android)|' * 4) + "Type ERASE to rewrite the partition table and wipe Android's data|Reboot now? (yes/no)")
    # the backup copy of the table first, then the primary, then the start of userdata - and nothing else is written
    Check 'shrink: what is written' ((Writes) -join '|') "$tailDd|$headDd|$zeroDd"
    Check 'shrink: nothing unexpected' $script:dev.bad 0
    Check 'shrink: the table was kept'  ((Sha256Hex ([IO.File]::ReadAllBytes("$gd\gpt.head"))) + (Sha256Hex ([IO.File]::ReadAllBytes("$gd\gpt.tail")))) ($script:dev.head0 + $script:dev.tail0)
    Check 'shrink: the device has the new one' ((Sha256Hex $script:dev.head) + (Sha256Hex $script:dev.tail)) ((Sha256Hex ([IO.File]::ReadAllBytes("$gd\new.head"))) + (Sha256Hex ([IO.File]::ReadAllBytes("$gd\new.tail"))))
    Check 'shrink: it differs'      ((Sha256Hex $script:dev.head) -ne $script:dev.head0 -and (Sha256Hex $script:dev.tail) -ne $script:dev.tail0) $true
    $now = GptShow @(GptTool $gd @('after.head,after.tail', '--disk-sectors', "$D64", '--name', 'userdata', '--show'))
    Check 'shrink: userdata starts where it did' $now.First $F64
    Check 'shrink: userdata ends 4 GiB earlier'  $now.End ($U64 - 8388608)
    Check 'shrink: says where'      (Printed '^  userdata now ends at sector 113766399$') $true
    Check 'shrink: userdata cleared' $script:dev.wiped $true
    Check 'shrink: reboots'         $script:dev.rebooted $true
    Check 'shrink: the last thing'  ($script:dev.cmds[$script:dev.cmds.Count - 1]) 'adb: reboot'
    # no partition but userdata is named, and nothing but the partition table is read
    Check 'shrink: no other partition' (@($script:dev.cmds | Where-Object { $_ -match 'by-name/(?!userdata )|nvram|fixnv|runtimenv|prodnv|persist|miscdata|mmcblk0p' }).Count) 0
    Check 'shrink: reads'           (@($script:dev.cmds | Where-Object { $_ -like 'pull:*' } | Sort-Object -Unique).Count) 2

    # "no" to the reboot
    FakeDevice 'vendor64'; RunOffer @('yes', '2.5', 'ERASE', 'no')
    Check 'no reboot: no error'     $script:died ''
    Check 'no reboot: written'      ((Writes) -join '|') "$tailDd|$headDd|$zeroDd"
    Check 'no reboot: stays up'     $script:dev.rebooted $false

    # a push that stops halfway: what is on the device is not what was made, and nothing is written
    FakeDevice 'vendor64'; $script:dev.shortPush = $true; RunOffer @('yes', '4', 'ERASE')
    Check 'short push: refused'     $script:died 'DIE: the new partition table did not arrive on the device as it was made; nothing is changed'
    Check 'short push: device untouched' (Untouched) $true
    Check 'short push: cleaned up'  ($script:dev.cmds[$script:dev.cmds.Count - 1]) 'su: rm -f /data/local/tmp/new.head /data/local/tmp/new.tail'

    # a device whose table does not change: said, and userdata is not cleared
    FakeDevice 'vendor64'; $script:dev.deafDisk = $true; RunOffer @('yes', '4', 'ERASE')
    Check 'did not take: said'      $script:died 'DIE: the table did not take (userdata still ends at 122155007). Nothing else was changed.'
    Check 'did not take: userdata not cleared' ($script:dev.wiped -or $script:dev.rebooted) $false

    # a partition behind userdata: not a table to make room in. The tool's reason and the figures, no question
    FakeDevice 'nvlast64'; RunOffer @('yes', '4', 'ERASE')
    $lines = @($script:died -split "`n")
    Check 'other table: refused'    $lines[0] 'DIE: only 0 MiB of free space after the last partition: this device has a different layout, nothing is changed.'
    Check 'other table: why'        ($script:died -match "the last partition is 'l_fixnv2_a', not 'userdata': refusing") $true
    Check 'other table: the eMMC'   ($script:died -match '\n  eMMC: 58[.,]\d GiB \(122159104 sectors\); the partitions end at sector 122155008; free after them: 0 MiB\n') $true
    Check 'other table: missing'    ($script:died -match '\n  needed behind the partitions: 700 MiB; missing: 700 MiB\n') $true
    Check 'other table: report'     ($lines[$lines.Count - 1]) 'Please report the numbers above (eMMC size and where the partitions end); they identify the variant.'
    Check 'other table: no question' $script:asked.Count 0
    Check 'other table: device untouched' (Untouched) $true

    # a table that does not check (one bit of the backup entries): refused the same way
    FakeDevice 'vendor64'; $script:dev.tail[40] = $script:dev.tail[40] -bxor 1; $script:dev.tail0 = Sha256Hex $script:dev.tail
    RunOffer @('yes', '4', 'ERASE')
    Check 'bad CRC: refused'        ($script:died -match 'a different layout, nothing is changed\.\n  backup entry array CRC does not match; refusing to touch this table\n') $true
    Check 'bad CRC: device untouched' (Untouched) $true

    # userdata of 4 GiB in all: nothing to split, with what is missing
    FakeDevice 'small64'; RunOffer @('yes', '4', 'ERASE')
    Check 'small: refused'          (($script:died -split "`n")[0] -match '^DIE: there is not enough room to split: 4[.,]0 GiB in total,$') $true
    Check 'small: Android'          (($script:died -split "`n")[1] -match '^and Android needs at least 4[.,]0 GiB of it\. Nothing is changed\.$') $true
    Check 'small: userdata'         ($script:died -match '\(sectors 113766400\.\.122155007\)\n') $true
    Check 'small: missing'          ($script:died -match 'needed: 4896 MiB \(4096 MiB Android \+ 800 MiB Linux\); missing: 800 MiB$') $true
    Check 'small: no question'      $script:asked.Count 0
    Check 'small: device untouched' (Untouched) $true

    # a device that gives nothing, in a work directory that still holds the table of an earlier run: that one is
    # never taken for the device's
    FakeDevice 'vendor64'; RunOffer @('no')
    FakeDevice 'vendor64' -SameWork; $script:dev.noRead = $true; RunOffer @('yes', '4', 'ERASE')
    Check 'no table: refused'       (($script:died -split "`n")[0]) 'DIE: could not read the partition table'
    Check 'no table: the eMMC'      ($script:died -match 'the partitions end at sector 122155008; free after them: 0 MiB\n') $true
    Check 'no table: no question'   $script:asked.Count 0
    Check 'no table: device untouched' (Untouched) $true

    Remove-Item function:Write-Host
    Remove-Item -Recurse -Force $fx
}

Write-Host "$script:passed passed, $script:failed failed"
exit $script:failed
