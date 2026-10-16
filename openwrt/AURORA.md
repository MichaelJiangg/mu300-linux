# Built-in Aurora packages

`build-rootfs.sh` installs the official Aurora theme 1.4.0 and its configuration
app 1.2.5 into the rootfs. This is shared by TF and other OpenWrt installation
methods using this builder. Bootstrap remains available; Aurora remains the
default theme.

The configuration app is available under **System → Aurora Theme Design**.
English is built into the app; Chinese (Simplified) and Turkish translation
packages are included. No first-boot package download is needed.

Official source and pinned release:

- https://github.com/eamonxg/luci-app-aurora-config/releases/tag/v1.2.5
- `aurora-config-packages.sha256` pins the three official release assets.

Downloads are cached under `work/` and verified before installation. To update,
review the upstream theme/config compatibility, update the release URL, package
mounts and checksum manifest together, then rebuild. Missing UI, menu, ACL or
translation files fail both rootfs and TF package validation.

The MU300 dashboard remains a separate plugin and does not depend on this
configuration app. Its existing Aurora and standard LuCI theme support is
unchanged.
