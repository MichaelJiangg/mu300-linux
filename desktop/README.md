New installations use username `root` and password `root`. Updates preserve the existing password.
首次安装默认账号／密码为 `root`／`root`；保留配置更新沿用原密码。

User instructions: open **START-HERE.md** at the package root, then run **OpenWrt-Installer.exe** or **OpenWrt-Installer.py**. This document describes technical details.

# MU300 desktop deployment

The same ZIP has two entry points. Installing it in Magisk runs the original
TF deployment script through a small path wrapper. Extracting it on a computer
exposes the desktop installer. The deployment steps are unchanged.
Desktop code is not added to the original Magisk TF boot image.
The ZIP contains only one `payload/mu300-openwrt.tar.gz`. Desktop internal installation
and SSH updates prepare a temporary filtered archive on the computer, excluding
the build machine's proprietary firmware and Android runtime. It is removed
after upload, including when upload fails. TF deployment uses the original
archive directly.

`OpenWrt-Installer.exe`, `OpenWrt-Installer.py`, `START-HERE.md`, `module.prop` and the
Magisk `customize.sh` entry are top-level files. Original deployment files live
in `payload/`, shortcut scripts in `launchers/`, the user guide at the root, technical notes in `docs/`, and
desktop helpers and ADB in `desktop/` and `tools/`.

| Launcher (.cmd for Windows, .sh for Linux/macOS) | Action |
| --- | --- |
| start-installer | Choose a method |
| install-to-tf-card | Original TF worker; format the first TF partition, or the whole unpartitioned card |
| install-to-userdata-image | EXPERIMENTAL plaintext userdata image; may damage Android F2FS |
| install-to-internal-storage | Independent `mu300root`; use unallocated eMMC first, otherwise offline userdata shrink |
| reinstall-internal-system | Erase and reinstall only existing `mu300root` |
| resume-internal-install | Continue after encrypted-data preparation and Android reset |
| switch-to-openwrt | Verify misc and restart into installed Linux |
| update-openwrt | SSH upload, preserve settings/capacity, then reboot |

Windows uses `OpenWrt-Installer.exe` when included. Otherwise install Python
3.10+ and `pip install paramiko lz4`. Install Android platform-tools and put adb
on PATH, or pass `--adb PATH`. Unix launchers use Python and system adb.
Builders can include Windows platform-tools by setting
`MU300_DESKTOP_ADB_DIR` to a directory containing adb.exe and its two API DLLs.
English filenames are used throughout. Prompts include English and Chinese.
Use `--serial SERIAL` when more than one Android is online.
At the end, the installer shows a final success, failure, cancellation or
next-step status with elapsed time and the next action. Interactive runs wait
for Enter before exiting. A prepared offline-install stage is explicitly
marked as needing another step. `--no-pause` skips the wait for automation;
`--pause` forces it even with redirected input. Windows CMD shortcuts provide
one closing prompt of their own, without a second installer pause.

V50 is accepted only as the exact `V50` / `MU3351` product on `ums9620`.
It shares the F50 kernel family and LAN address; its AW9523B LED controller
needs a kernel built with `CONFIG_LEDS_AW9523B=y`. Historical preview images
without that driver do not provide V50 lighting. Always extract this device's
own firmware. Its tested Android uses FBE. If GPT has enough unused space,
installation preserves encrypted Android data; otherwise it uses reset/resume.

`OpenWrt-Installer.py --check` verifies package files without accessing hardware.
`--check-boot` additionally builds trial desktop boots on the computer to check
the repacker, boot-size limit and unchanged kernel, also without device access.
`--check-rootfs` tests temporary archive preparation without accessing a device.
`--check-resume` checks a connected Android and saved transaction without
uploading payloads or writing the device. Repair packages can resume older
transactions when the boot, rootfs and filesystem tool checksums match. Device,
slot, partition geometry and the on-device token must still match. New records
also save a `package-manifest.json` beside `transaction.json` for portability.
`--probe --serial SERIAL` checks the connected Android's model, encryption,
storage and binary DTB/A/B reads without staging files or writing partitions.
`--size 10` selects 10 GiB. `--host 192.168.77.1` selects U30Air for updates.
The installer never changes the computer's network or firewall settings.
Hotspot keys use visible input. Android image mounting resolves BusyBox's
`/dev/loopN` to Android's real `/dev/block/loopN` before attachment. Reboot
requests use the ADB reboot service rather than waiting for a disconnecting
root shell to return an exit status.

## Storage and encryption

The desktop installer validates both GPT headers and tables against physical
capacity, then measures contiguous, 1 MiB aligned unallocated ranges. These are
different from free space inside `/data`. When a range fits the chosen size,
it installs there without shrinking, formatting or resetting Android, including
FBE/FDE devices. GPT changes, userdata changes and encryption are separate decisions.
`--probe` reports physical capacity and usable GPT gaps without writes.

Free-space installation backs up GPT and both-slot boot-chain files first.
It writes a verified device-specific image through a bounded raw loop, grows
ext4 to the full chosen capacity, checks filesystem and file hashes, then commits
the new GPT entry and verifies both copies. Existing entries and userdata stay
unchanged. Only after these checks does it write the opposite boot and select
OpenWrt. Android is not asked to reread its mounted disk's partition table;
the new partition node appears after reboot. Android Toybox's bounded losetup
is required; BusyBox's unbounded version cannot be substituted.

Detected legacy raw ext4/F2FS systems at known MU300 offsets or gap starts are
excluded from allocation. Unallocated does not guarantee all bytes are empty:
the confirmation warns that the selected raw range is overwritten. Invalid or
disagreeing GPT copies stop installation; the installer does not silently move
the backup GPT or widen its usable bounds. An existing `mu300root` still requires
the reinstall/update action. `--format-userdata` is rejected for a free-gap install.

Only when no suitable gap fits the selected size is userdata shrink considered.
Plaintext F2FS/ext4 uses the preserving workflow: verify a complete image with
this device's runtime, stage it, boot a desktop-only initramfs, check and shrink
the unmounted filesystem, change GPT, write/read back the root, and expand ext4
to the full partition by default. The initial 2 GiB image is not the installed capacity.
The first offline boot may take several minutes or longer, then reboots once into OpenWrt; keep power connected.
Offline operations print a two-second stage/elapsed heartbeat; copying also
reports bytes. Progress is exposed during that boot at
`http://192.168.77.1:8089/progress.txt` (U30Air: `192.168.77.1`).
USB networking must be enabled to view it. No permanent polling service is added.

FBE/FDE or `--format-userdata` uses two stages. **Android userdata is erased.**
Stage one carries tools and a device-bound plan in the ramdisk; it never tries
to decrypt/read `/data`. It carves the root partition and asks stock Android
recovery to format the smaller userdata. Finish fresh Android setup, re-enable
USB debugging and restore/grant root, then run `resume-internal-install`.
CID, serial, Android slot, geometry and the preparation token must match before
writing the root. Firmware is extracted again from the current Android.
Resume records and pre-install GPT/misc/boot/both-slot boot-chain backups are
stored on the computer under `~/mu300-backups`. Use `--transaction FILE` to
choose a record. Unknown encryption states stop a preserving shrink.

Only the opposite boot slot and differing opposite-slot
`uboot/sml/teecfg/trustos/vbmeta` are written, with backups and readback checks.
Current Android boot and NV/calibration are not overwritten. Deleting a root
partition or blindly restoring a GPT backup is not a rollback. Arbitrary
partition editing is not offered.

## Updates

The computer initiates SSH uploads, avoiding inbound Windows firewall rules.
SSH keys are accepted per connection without a persistent host-key cache, so
swapping devices at the same USB management address does not block updates.
Root-password authentication remains required. Updating uses
MU300's native mutex, config/account preservation, user-package migration and
`openwrt.new`/`openwrt.old` swap. The old directory remains for native rollback.
Runtime firmware comes from the existing installation. A plain filesystem
view excludes live vendor device/proc mounts during copying. Root/boot checks
precede slot selection; boot failures attempt root and boot restoration.
The persistent boot log and filesystem capacity are preserved.
Use the package for the intended kernel family. Legacy eMMC hidden-area installs
are also supported after verifying the live OpenWrt container, its loop backing,
ext4 identity, GPT boundaries and boot-discovery offset. Updating preserves that
layout and capacity; it does not create a partition or resize Android. An
unrecognized or inconsistent layout stops before uploading or writing.

## Building

`tools/build-openwrt-tf-magisk.sh` adds desktop deployment by default.
Set `MU300_DESKTOP_TOOLS=/path/to/ARM64-musl-tool-root`; required F2FS,
e2fsprogs and ucode files are listed in `prepare-tools.py`. An ARM64 OpenWrt
root with these packages can provide them. ELF architecture and checksums are
checked. These tools go only into the desktop boot supplement.
`MU300_DESKTOP_INSTALLER=0` builds the original pure Magisk ZIP.

On Windows, install PyInstaller, paramiko and lz4, then run
`python desktop/build-exe.py`. Pass `MU300_DESKTOP_EXE=.../OpenWrt-Installer.exe`
when packaging; the adjacent source fingerprint is required and stale EXEs are
rejected. Python source is always included.

An existing Magisk staging tree can be augmented with
`python desktop/package.py --stage DIR --tools TOOL_ROOT --kernel 7.2`.
All original deployment file contents remain identical; `magisk_layout` maps
their original names to the new locations. `desktop/manifest.json` records
these hashes and every addition, including the Magisk path wrapper.

Hardware installation, especially stock-recovery reset/resume, still needs
real MU300 validation before a release. ZIPs augmented from historical packages
remain historical runtime builds; they must not be advertised as fresh firmware.
