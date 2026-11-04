# MU300 网络测速

在 OpenWrt 25.12 的 LuCI 中打开「服务 → SpeedTest」。LuCI 提供页面，浏览器在用户点击开始后直连所选测速节点。界面首次按浏览器首选语言显示，手动语言和测速历史保存在当前浏览器的 LuCI 地址下。

插件按需安装。节点按城市或省级分组，当前可手选上海电信、广东移动、中国香港和美国洛杉矶。广东移动是省级节点。洛杉矶节点由 Clouvider 提供，用于查看跨境链路表现。 [LibreSpeed 节点清单](https://librespeed.org/backend-servers/servers.php)

测速服务器默认在打开页面时从中国大陆节点匹配，顺序为同城同运营商、同省同运营商、同城可用节点、国内节点响应速度。展开「测速服务器」可修改匹配城市、运营商，或直接指定一个节点。城市和运营商偏好只在当前浏览器保存。

「当前网络」和「测速服务器」并排显示。打开页面时使用 [IP.SB](https://ip.sb/api/) 查询公网 IP 和估计城市。当前网络卡显示公网 IP 与 MU300 的蜂窝驻网运营商，公网 IP 仅用于当页显示。自动匹配优先参考近期驻网运营商，缺少驻网信息时参考公网 IP 查询结果，同城跨运营商回退会标明。代理、VPN 或多线路可能让出口与驻网信息不同。下载和上传测速由「开始测速」按钮触发。

## 源码和构建

- `root/` 注册菜单，`htdocs/` 提供 LuCI 页面，`po/` 保存菜单翻译。
- `stage-assets.sh` 从 `opendesign/mockups/u30-speedtest/` 暂存实测页面，并加入固定版本的 LibreSpeed 资源。暂存过程无需改动设计预览。
- `build-apk.sh ENGINE_SOURCE_DIR [OUTPUT_DIR]` 使用带 `mkpkg` 的 apk-tools 3 构建 `.apk` 和 SHA256。可以用 `APK` 指定构建工具。中文菜单由 `po2lmo` 编译，也可预先生成 `lmo/mu300-speedtest.zh-cn.lmo`。使用 OpenWrt SDK 时，向包编译命令传入绝对路径 `ENGINE_SOURCE_DIR`。
- 每次发布页面改动时，菜单中的视图模块名和静态资源目录都使用该版本的新路径。菜单文件的修改时间由包修订号决定，让 LuCI 同时刷新其菜单索引。

引擎源目录应包含 `speedtest.js`、`speedtest_worker.js` 和 `LICENSE`。当前使用 [LibreSpeed Go v1.1.5](https://github.com/librespeed/speedtest-go/tree/v1.1.5) 的 `web/assets/` 脚本及根目录许可证。官方源码压缩包的 SHA256 为 `a65bbb94868d9ad73f85950264cb18fafb2ba5cf4788ac67981d78b863ca67c4`，可对照 [OpenWrt 软件包定义](https://github.com/openwrt/packages/blob/openwrt-25.12/net/librespeed-go/Makefile)。构建前在引擎源目录对 `speedtest_worker.js` 应用 `librespeed-hong-kong.patch`。该补丁让香港节点的跨域上传请求省略其不接受的 `Content-Encoding` 请求头。

## MU300 升级恢复

安装并验证后，使用 `mu300-user-packages keep FILE.apk` 保存安装包。在启用软件包恢复的正常系统升级中，MU300 会在软件源找不到插件时尝试使用保留的安装包。升级完成后，在「系统 → 更新后的软件包」确认恢复状态，再打开测速菜单。浏览器在独立 `:8989` 页面保存的历史属于另一个地址。
