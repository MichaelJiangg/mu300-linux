# APN profiles and safe mount-point discovery

## APN page

`Cellular → Access points (APN)` uses the standalone dashboard's dialogs,
toasts, theme bridge and Chinese/English/Turkish translations. It supports
adding, editing, deleting and explicitly applying up to 32 profiles.

Profiles live in `/etc/config/unisoc_apn` (a package conffile). Saving a profile
only changes the list. Applying defaults to remembering the choice by the current
SIM's ICCID. The platform dialer resolves this binding on every bearer setup;
switching cards does not inherit the other card's private APN or credentials.
An unbound SIM uses the global network settings. With the remember checkbox
unchecked, applying updates the global interface instead. Automatic selection
is also per SIM: a small, independently maintained Chinese public-carrier list
uses IMSI; unknown carriers fall back to an empty SIM-default APN. IoT/private
networks must be configured manually. Applying asks netifd to reload and cycle
only `unisoc_modem.main.data_interface` (default `wan`). It does not
restart the network service, USB, Wi-Fi or switch the data SIM. Existing DNS,
IPv6 and LAN settings are preserved. Configuration selection is displayed
separately from the interface's actual connected/pending state.

The current profile is matched against the saved SIM binding or network configuration, not
an independent active-profile flag. An active or SIM-bound profile cannot be deleted. Editing
it is save-only; click Switch to apply the new settings. Empty APN means SIM
default and explicitly clears the old modem APN on the next netifd setup.

The backend currently supports `mu300cell` and its existing IPv4/dual-stack
bearers (`IP`, `IPV4V6`). It does not advertise unsupported IPv6-only bearers.
Authentication supports none/PAP/CHAP/PAP-or-CHAP using
the Android B09 RIL's `CGDCONT → CGPCO → CGDATA` path. Optional advanced initial
attach configuration uses `SPCGAPNCFG`, is off by default, and never touches IMS
CID 11. Commands require exact OK before dial continuation; errors never include
credentials. Passwords are write-only in RPC/UI, preserved on blank edits unless
explicitly cleared; the conffile is root-only. A successful Apply means configuration was saved and
netifd accepted the request, not that the carrier has granted internet access.
Failed apply requests report whether the configuration was already saved.
Pending LuCI/UCI network edits are never silently committed or discarded.

No AT queries or periodic polling are needed to display this page. Remembered
selection writes read ICCID once through the configured standalone AT adapter;
the dialer reads IMSI only for an automatic binding. Writes use
the existing data-SIM switch gate to exclude concurrent card changes, and defer
while an interactive modem lock operation is running.

## Safe block-mount

fstools scans `/dev/sd*` even for `block info /dev/specific-device`. On Unisoc,
that glob also matches communication character devices. Filtering LuCI's result
or passing an explicit disk path cannot prevent the underlying probe from
opening such a channel.

`openwrt/patches/fstools-probe-device-types.patch` checks device type before
`probe_path()`: block devices and regular files (including swapfiles) are allowed;
character devices are allowed only if sysfs identifies their subsystem as UBI.
FIFOs, sockets, directories and other character devices are skipped without
opening them. Device names alone are not trusted to identify UBI.

`openwrt/build-block-mount.sh` builds a real patched APK with the checksum-pinned
OpenWrt 25.12.5 ARM64 SDK and matching fstools revision. The SDK uses a separate
Docker cache; parallel rootfs builds serialize SDK access. Its output cache is
keyed by source/build-script contents and verifies the APK checksum before reuse.
The normal OpenWrt/TF/release build installs this APK (including fstab scripts
and libblkid-tiny), and verifies the required payloads. It never temporarily
installs an unsafe block binary on a live router. Package dependency checking
is retained; incompatible base libraries must fail the build.

This adds mount-point management, not blanket auto-mount/format behavior.
Existing fstab settings are unchanged. Upgrading block-mount independently from
an unpatched package feed can remove the guard; regenerate the custom package
when updating the base fstools/SDK version.

## Regression checks

```
python3 -m unittest discover -s tests -p 'test_apn*.py' -v
python3 -m unittest discover -s tests -p 'test_mu300_i18n.py' -v
python3 -m unittest discover -s tests -p 'test_block_probe.py' -v
ucode -L 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/*.uc' tests/apn.uc
```

`apn.uc` uses a temporary real libuci database. The optional Playwright test
(`MU300_BROWSER_TESTS=1`, optional `MU300_BROWSER_CHANNEL=msedge`) uses real UI
components with isolated fake RPC, never the router. Actual carrier acceptance
of a user's APN still needs testing with that carrier/SIM.
