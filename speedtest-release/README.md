# MU300 SpeedTest

一个可选装的 LuCI 网络测速插件，入口为「服务 → SpeedTest」。打开页面时会通过 IP.SB 查询公网 IP 与估计城市；用户点击开始后，浏览器直连所选公网测速节点，显示延迟、下载和上传读数，并在当前浏览器保存最近的测速历史。它测量的是浏览器经设备热点到公网节点的链路，不是路由器内部独立测速。

本发行候选在中兴 U30 Air、MU300 OpenWrt 25.12.6 上验证过页面和实际测速。其他设备及固件版本尚未验证。插件已提交[上游 PR #489](https://github.com/dikeckaan/mu300-linux/pull/489)，是否合入主版本由上游决定；此独立发布分支提供选装包。

## 一行安装

先连接 U30 Air 的 OP 网络，以 `root` 身份进入设备终端。设备需已有 MU300 LuCI 面板，并能访问 GitHub。复制以下整行：

```sh
installer_file=$(mktemp /tmp/mu300-speedtest-setup.XXXXXX) && curl -fL --connect-timeout 15 --max-time 60 -o "$installer_file" https://raw.githubusercontent.com/MichaelJiangg/mu300-linux/speedtest-v1.0.0-r13/speedtest-release/dist/setup.sh && [ "$(sha256sum "$installer_file" | cut -d ' ' -f1)" = "88b3866524686a94be61746c587b7ce68128282b2b99d37f19d59d8367a8fa6f" ] && sh "$installer_file"
```

这条命令先核对安装脚本的 SHA-256，再运行脚本。脚本从固定版本的 GitHub 发布分支下载 APK，核对文件大小和 SHA-256，用 `apk add --no-network --allow-untrusted` 安装，并调用 `mu300-user-packages keep` 登记系统更新后的恢复副本。没有通过下载或校验时不会安装。安装完成后打开「服务 → SpeedTest」。

再次安装相同版本会交给 `apk` 处理；升级旧版本时，`keep` 会替换**本插件**的旧版恢复副本。登记功能来自 MU300 系统，跨固件版本的实际恢复仍待验证。脚本不清 LuCI 缓存、不重启服务，也不修改网络或蜂窝设置。

尚未安装 OP 的用户，请先阅读 [MU300 OpenWrt 官方安装说明](https://github.com/dikeckaan/mu300-linux/blob/main/wiki/Installation.md)。该流程涉及设备 Root、USB 调试及引导镜像条件，和本插件的安装是两件事。

## 发行文件与源码

- `setup.sh`：固定 `v1.0.0-r13` 的设备端安装脚本。
- `luci-app-mu300-speedtest-1.0.0-r13.apk`：经过 U30 Air 真机验证的本地构建；SHA-256 为 `9f586638e1be7b594b0584aa1499a3311dde2bc7bacee2382ad7e7e9aed0e408`。
- `COPYING`：LibreSpeed 的 LGPL v3 所引用的 GNU GPL v3 条款。
- `SHA256SUMS`：安装脚本、APK 和 `COPYING` 的校验值。
- `device/luci-app-mu300-speedtest/` 和 `opendesign/mockups/u30-speedtest/`：与 r13 对应的插件和页面源码。
- `third_party/librespeed/`：LibreSpeed Go v1.1.5 浏览器引擎源码及许可证；`speedtest_worker.js` 已应用本仓库记录的香港节点兼容补丁。

`device/luci-app-mu300-speedtest/README.md` 记录构建方式、资源来源和补丁。项目代码按 [MIT 许可证](LICENSE) 提供；LibreSpeed 组件按 [LGPL v3](third_party/librespeed/LICENSE) 提供，其引用的 [GNU GPL v3 条款](third_party/librespeed/COPYING) 也随发行提供。详情见 [第三方说明](THIRD_PARTY.md)。
