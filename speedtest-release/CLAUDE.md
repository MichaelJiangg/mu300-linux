# MU300 SpeedTest release candidate

## Scope

Prepare a standalone, reviewable GitHub source and release candidate for the optional MU300 LuCI SpeedTest plugin. The validated device is a U30 Air running MU300 OpenWrt 25.12.6. Do not claim support for other devices or firmware versions without verification.

## Directory conventions

- `device/luci-app-mu300-speedtest/`: matching r13 package source and build scripts.
- `opendesign/mockups/u30-speedtest/`: matching r13 page source required by `stage-assets.sh`.
- `third_party/librespeed/`: pinned LibreSpeed v1.1.5 browser engine source and its license, with the project's documented Hong Kong upload patch applied.
- `dist/`: versioned script, APK, licenses, and checksums to publish under the release branch.
- `README.md`: public installation and source instructions.
- `ROADMAP.md`: actual preparation and verification state.

## Release rules

- Pin every download to version `v1.0.0-r13` and verify the APK SHA-256 before installation.
- Verify the downloaded setup script in the user-facing command before executing it.
- Keep package installation local with `apk add --no-network --allow-untrusted`; require `luci-base` to be installed already.
- Register the installed APK using `mu300-user-packages keep` for firmware update restoration.
- No credentials, device identifiers, local backups, or private project files enter the public candidate.
- Publishing the repository, release assets, or tag requires the owner's separate confirmation.
