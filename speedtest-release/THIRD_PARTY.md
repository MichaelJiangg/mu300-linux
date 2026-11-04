# Third-party notices

The browser measurement engine is from [LibreSpeed Go v1.1.5](https://github.com/librespeed/speedtest-go/tree/v1.1.5/web/assets), licensed under GNU LGPL v3. Its upstream LGPL text is included at `third_party/librespeed/LICENSE`; the referenced GNU GPL v3 terms are included at `third_party/librespeed/COPYING`.

The source files `speedtest.js` and `speedtest_worker.js` came from that pinned tag. The latter has only the two changes in `device/luci-app-mu300-speedtest/librespeed-hong-kong.patch`: the Hong Kong upload endpoint omits `Content-Encoding: identity`.

SHA-256 after applying the patch:

| File | SHA-256 |
| --- | --- |
| `speedtest.js` | `55cfa1af1c421f9a0e1544c9975732f79b67eccc155d8443baaf9b2f1ee5bcd0` |
| `speedtest_worker.js` | `58244812791d4995d2edc9dc6fb25f51cd16b9e49354094d6a15a84b3eef1ac9` |

The MU300 project is [MIT licensed](https://github.com/dikeckaan/mu300-linux/blob/main/LICENSE). The matching package code follows that license.
