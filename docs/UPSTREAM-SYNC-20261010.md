# Selective upstream stability integration

Reviewed `dikeckaan/mu300-linux` main at `a5da67f` against local `0d93695`.
Their merge base is `1a69a41`; 352 upstream-side commits are not ancestors of
this branch. This is a **selective backport**, not a full main merge.

## Applied

| Upstream source | Integration |
| --- | --- |
| `1f6e825` | WCN power-transition mutex, safe probe/remove ordering, failed power-on cleanup, RX NULL guard and context publication. Shared 6.18/7.2 sources plus the 5.4 patch. |
| `1196cf2` | Unwind every PCIe channel including the failed channel and channel zero; allow deinit when a pool was never allocated. Both kernel families. |
| `f0323bf` | Default firmware ARM logging off; resume preserves the chosen state. Shared mainline WCN sources. |
| `f4f5e76` | Our AP ARP/DNS data-queue fix was already present. Move its DNS bypass before the command-path checksum manipulation, as reviewed upstream. |
| `b0e9595` | Recreate legacy Wi-Fi/Bluetooth build trees when patch hashes change. Also reject an outdated hash in standalone `build-wlan.sh` instead of silently accepting it. |
| `bde23d0`, `486856c` | Adapt eMMC probe bounds to this branch's existing shell/PowerShell installers, uninstallers and reset-password tool (there is no upstream `storage.sh` here). Clamp empty regions to zero. Move RNDIS bridging before address cleanup and handle differing preinit prefixes. |

These changes retain the fork's independent LuCI plugin, TF installer, active
slot handling, USB host settings, NCM startup re-enumeration and fast modem
startup. No kernel version/configuration change is included.

## Deliberately not imported

- `b951035` / `6e616ab`: our tested `CHECKSUM_NONE` path already prevents the
  IPv6 RX drops. Keep stack verification for all packets rather than change
  checksum policy as part of a stability backport.
- `3435100` and the larger suspend/power-profile series: default WoWLAN and
  automatic idle/radio policy need a separate end-to-end suspend evaluation.
  Firmware log suppression above does not enable system sleep.
- `760d561`: our startup/module-loading paths already carry the fork fixes;
  do not add another hotspot restart or extend waits.
- Upstream's LAN-hotplug rebind loop: keep our existing procd-managed USB
  endpoint recovery; do not introduce a second re-enumeration owner.
- Upstream SMS pooling/deletion: our local storage, direct receive and
  archive-before-delete implementation also integrates forwarding/history
  barriers. Replacing it would discard fork-specific behavior.
- VPN toolkit, power pages, release workflow, updater/boot rollback and APK
  upgrades: these are separate feature/build changes, not dependencies of
  the selected fixes. Existing TF packages remain unchanged.
- Existing BA latency tuning, IPv6 behavior and dashboard presentation are
  preserved; withdrawn wireless rate/signal experiments are not restored.

## Verification

- Rebuilt `wcn_bsp` and `sprd_wlan_combo` for **6.18.54** and **7.2.8** in
  `upstream/out-kvm-6.18` / `upstream/out-kvm-7.2`. Both builds succeeded;
  module vermagic and the existing configuration/hash checks passed.
- Applied the complete 5.4 WLAN patch set to a disposable pristine vendor
  source copy; dry-ran the WCN pool patch against the existing kernel source.
  This is patch applicability, **not** a new full 5.4 kernel build.
- Added offline regressions for lock/lifetime safeguards, PCIe unwind,
  firmware logging, DNS ordering, eMMC boundaries and RNDIS address handoff.
- Full local Python suite: **176 passed** with `MU300_TEST_SHELLS=dash,bash`;
  PowerShell 7 installer checks: **417 passed**. BusyBox's standalone applets
  bypass this host's command mocks, so it was excluded from the full suite.
- No device was contacted, flashed, rebooted or runtime-tested. These are
  repository/build checks; runtime boot-cycle acceptance remains outstanding.
- No rootfs/ZIP rebuild or remote push. Old r4 packages do not contain these
  changes; rebuilt module directories do.

## Follow-up: vendor preservation during online updates

Reviewed main again at `5582413`. Backported `f7df326` into `mu300-update`:
merge missing vendor files instead of BusyBox `cp -an`, preserve image entries
and target symlinks, and abort before the directory swap on copy failure.
This narrowly updates the earlier decision to leave the updater untouched;
it does not import unrelated VPN, suspend or boot-policy changes.
See `WIFI-R4-AUDIT-20261010.zh-CN.md` for the inspected r4 payload, validation
and the limits of attributing the reported Wi-Fi failure without device logs.
