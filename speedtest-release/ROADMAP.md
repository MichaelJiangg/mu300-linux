# MU300 SpeedTest GitHub release progress

## Current stage

The `v1.0.0-r13` source and release candidate is prepared locally for the existing public `MichaelJiangg/mu300-linux` fork, in a separate `speedtest-v1.0.0-r13` branch under `speedtest-release/`. That branch does not exist yet, so the one-line download command is not live. No device installation was performed by this candidate.

## Verified

- The candidate plugin source and page source match the local r13 files byte-for-byte. The r13 APK is 31,208 bytes and its SHA-256 matches the recorded device-tested artifact: `9f586638e1be7b594b0584aa1499a3311dde2bc7bacee2382ad7e7e9aed0e408`.
- The bundled LibreSpeed v1.1.5 sources reproduce the recorded engine SHA-256 values after applying the Hong Kong upload patch. LGPL v3 and its referenced GPL v3 text are included separately.
- `setup.sh` pins the release URL and APK digest, checks the MU300 LuCI environment, rejects a newer installed version, verifies the installed version before registering the retained APK, and avoids network package indexes during unsigned APK installation.
- `sh -n` passed for the setup and package scripts. JavaScript syntax checks passed for the page and engine files. The release `SHA256SUMS` verifies `setup.sh`, the APK and `COPYING`. The README's setup digest matches the candidate script.
- Invoking the script with an unexpected argument or on this non-root macOS host exits before download or installation. A targeted credential and device-identifier scan found no matches in the public candidate.

## Pending

- Owner confirmation for creating the `speedtest-v1.0.0-r13` branch in the existing public fork and uploading the matching source, setup script, APK, licenses, and checksums under `speedtest-release/`.
- After publication, verify anonymous downloads and hashes from the actual GitHub URLs, then test the one-line flow on an authorized U30 Air. The r13 APK was previously tested on a U30 Air, but this GitHub installer path has not been run on the device.
- Firmware-version upgrade restoration has been registered on the test device but has not been validated across an actual firmware upgrade.

## Latest validation

2026-11-05：本地源码、脚本语法、页面 JavaScript、发行校验清单和脚本拒绝路径已核对。GitHub 发布、公开下载及真实设备一键安装仍待确认与验证。
