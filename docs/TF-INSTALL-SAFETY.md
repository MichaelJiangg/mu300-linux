# TF Magisk installer: reliability and failure handling

This is still a **fresh, destructive installation** of the selected TF
partition, not a keep-data upgrade. No 32 GiB cap is applied. The whole selected
partition is formatted with Android e2fsprogs, lazy inode/journal initialization
and `nodiscard`. Small cards get an explicit minimum inode count calculated
from the rootfs archive; large cards retain the sparse inode layout.

## Installation order

1. Enter Android init's mount namespace with the bundled BusyBox. Acquire an
   installer lock for this Android boot; keep persistent logs under
   `/data/local/tmp/mu300-tf-install/log.*`.
2. Verify SHA256 of rootfs, boot image and generated requirements/readback
   manifests. Check Android mke2fs, TF/boot/misc capacity and Android staging
   space. Collect the device's vendor files **before formatting**. Check their
   actual size/inode count and space for the boot readback.
3. Ask vold to release only the selected device's `public:major,minor` volume
   (all child partitions only when formatting a whole card). Inspect mountinfo
   by device number, not path, including other mount namespaces. Reject leftover
   mounts and stacked/device-mapper holders. Never force/lazy-unmount a busy card.
   `unmountable` is not a mounted state: existing Linux filesystems may have
   this Android public-volume status. Both it and `unmounted` still require
   the full mountinfo check. An exited/zombie task with no remaining mount
   namespace may return EINVAL for mountinfo; only that verified case (or a
   vanished task) is skipped, not unreadable live-process namespaces.
4. Read the superblock using bounded, aligned reads. A failed or short read is
   an error, never evidence of an empty card. Format at full capacity, then
   check usable free space and inodes.
5. Extract to `openwrt.new`, verify critical files, add the preflighted vendor
   tree and device configuration, then publish `openwrt`. Write boot settings,
   unmount successfully, remount read-only to check critical content, all staged
   vendor regular-file hashes and settings,
   then unmount again. Only now emit `MU300-INSTALL-OK`.
6. Write and fsync the opposite boot slot, perform bounded readback/SHA256,
   then arm that slot via a verified 32-byte misc update. Never globally sync
   all Android filesystems just to write misc. Return to Magisk with its original
   shell options preserved.

Package SHA256 is an integrity check, **not a signature/authenticity guarantee**.
Readback verifies selected boot-critical files, not every TF sector or long-term
card health. Successful unmount/readback cannot guarantee survival of defective
media or power loss during a subsequent operation.

## Timeouts and recovery

The supervisor uses an independent process group and checks every two seconds.
It streams command output, prints elapsed progress every ten seconds, and stops
after 120 seconds without output or TF block-I/O counter progress. Hard limits:
preflight/vendor staging 180 seconds each, final staging-space check 30 seconds,
rootfs transaction 1200 seconds, and boot write/readback/slot arming 60 seconds
each. These are installation deadlines, **not added system-boot delays**.

Failure never starts another write stage. Timeout sends TERM/KILL to the stage
group and does not wait indefinitely, globally sync, or retry the failed I/O.
Any failed transaction retains a boot-scoped lock: reboot Android before
retrying. Existing logs remain for diagnosis. A driver stuck in uninterruptible
kernel I/O may not respond to signals; the script cannot cure that driver hang
and explicitly asks for a reboot. On error, the TF may remain mounted or contain
an incomplete install; do not assume the previous rootfs was preserved.

## Boot target protection

TF packages put `/etc/mu300-root-target` (`sd`) in the **device-specific** ramdisk
segment. Generic kernel updates leave that marker intact. Missing/broken TF
roots return to Android instead of probing the unused eMMC region or continuing
the standalone vendor boot. Generic images without the marker retain internal
root support, but verify partition ends, device size and backup-GPT bounds
before any root-region read or loop attachment. The offset reported in
[issue #65](https://github.com/dikeckaan/mu300-linux/issues/65) is rejected before I/O.

## Offline verification

`python3 -m unittest discover -s tests -p 'test_tf_*.py' -v` covers namespace
alias identification, selected-volume isolation, residual mounts, short reads,
out-of-range eMMC probes, extraction/checksum/unmount failures, watchdog timeout,
stage gating, retry locks, A/B selection and package metadata. Where e2fsprogs is
available it also formats **regular sparse files** of 512 MiB and 128 GiB and
checks geometry/inodes. No physical disk, live device or rootfs rebuild is used.

Real-device validation is still required for Android/vold variants, defective
cards, interrupted power, cold boot and the Magisk app's final success display.
