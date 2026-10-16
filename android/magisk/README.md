# Magisk module: switch to Linux from Android

A one-tap way to start the Linux system from Android, for devices that already have Linux installed
(`./install.sh`). It replaces having a computer plugged in just to change the boot slot.

```sh
android/magisk/build.sh          # builds mu300-linux-switch.zip
```

Install the zip in the Magisk app (Modules → Install from storage), or from a computer:

```sh
adb push android/magisk/mu300-linux-switch.zip /data/local/tmp/
adb shell "su -c 'magisk --install-module /data/local/tmp/mu300-linux-switch.zip'"
adb reboot                      # Magisk applies a new module on the next boot
```

## Using it

* **Magisk app → Modules → MU300 Linux switch → Action.** The device arms the slot opposite Android and reboots into Linux.
* **From a terminal or adb:**

```sh
su -c mu300-linux               # switch to Linux now
su -c 'mu300-linux status'      # what is on each slot; changes nothing
su -c 'mu300-linux --dry-run'   # print the block it would write, write nothing
```

Going back needs nothing: Linux restores the Android slot block during its own boot, so the next reboot returns to
Android. From inside Linux, `mu300-next-boot linux` arms another Linux boot and `mu300-os <name>` picks which
system starts.

## What it writes

Exactly 32 bytes: the AOSP `bootloader_control` block at offset `0x800` of `misc`, with the Linux slot at the highest
priority and `tries_remaining = 2` (LK treats 1 as an already failed boot), while Android remains bootable and marked
successful. The GPT, `userdata` and every other partition are untouched, so the worst case of a
Linux that does not boot is that LK falls back to Android by itself.

The block is not a canned blob: the module reads the live one, changes the slot suffix and the two metadata bytes,
and recomputes the CRC32 (zlib, over the first 28 bytes) in `awk`, so it stays correct on a device whose block
differs. It refuses to do anything when the magic is not `BCAB`, or when the opposite boot partition is missing,
is not a boot image, or is just a copy of Android's boot image (no Linux installed).

## Checked on hardware

ZTE F50 / MU300, Magisk 30.7, Android 13: `status` and `--dry-run` produce exactly the trial block that
`boot/flash-trial.sh` computes on a computer, and the Action/`mu300-linux` path rebooted the device into Linux.
The Android-slot-B → Linux-slot-A path has automated block/CRC and switch-script tests, but has not yet been
boot-tested on the physical device. Keep an Android recovery path available for its first deployment.
