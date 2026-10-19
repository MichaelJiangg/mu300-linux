# 自动模式兼容性保存失败修复（2026-10-20）

## 实机确认

当前连接 `192.168.77.1` 的设备由 `/run/mu300/device` 确认为 **F50**，
运行内核 `7.2.8`，发布版本 `r20261019.140236-g2d3f7438-s0d889a70`。
本轮通过真正的 HTTP `/ubus` 接口登录 root 并测试，不是仅执行 SSH 下的 UCI 命令。

修复前，当前会话的 `uci.set` 方法及 `unisoc_modem` 配置写权限均为 true，
而 `uci.commit` 方法权限为 false。实际 commit 返回 JSON-RPC `-32002 / Access denied`。
网页已将配置写入会话暂存区，但没有权限提交到磁盘；前端因此停止网络模式应用。

LuCI 默认 ACL 提供 set，不提供 commit。不能依赖其他可选插件偶然授予 commit
权限；例如测试基础镜像中的 attendedsysupgrade 会授予该权限，可能掩盖缺口。
UCI 配置权限和 ubus 方法权限是两层检查，两者不能相互替代。

## 修复范围

- 两仓库 `luci-app-mu300.json` 的 write.ubus 增加 `uci: ["commit"]`。
  保留原有配置范围，不授予新的 UCI 配置或任意 ubus 方法访问权限。
- 保存仍按 set → commit → 原网络模式任务执行；失败不发送模式 AT。
  不改全局 uci.apply、AT 所有者、开机回放或切卡顺序。
- 页面保留真实底层错误文字，避免所有失败都只剩同一句笼统提示。
- ACL 在新登录时读入，已登录的旧会话需退出后重新登录才能取得新增权限。

## 实机部署与验证

F50 已热部署 ACL 和 `auto-mode.js`，传输后按 SHA-256 回读核对，备份在
`/root/hotfix-backups/20261020-auto-mode-acl`。未重启网络、基带、Wi-Fi 或系统。

新登录会话的 commit 权限变为 true；依次通过真实 HTTP 接口保存 134、152、
default、重复 default，均成功，且独立新会话能够读到已提交的值。
测试后恢复原来“未显式设置 auto_work_mode”的状态，整个 `unisoc_modem` 文件
SHA-256 与测试前一致，其他配置未改变。网络和无线配置哈希、启动 ID 保持一致，WAN up=true。

本轮没有调用锁定或切网络模式任务，所以不能将保存验证称为本轮 RF 切换／重连实测。
E5、T551M、M8、T512N 同步公共源码和测试，未在这些设备上热部署。
原始实机结果位于 E5 仓库忽略目录 `work/auto-mode-acl-20261020/live-result.json`。

## 回归

- 新增两仓库共用的真实 rpcd + uhttpd + UCI HTTP 集成测试，运行于已有、禁网、
  不映射主机端口的临时 OpenWrt 容器，结束自动删除；不下载镜像、不复制构建树。
- 测试登录仅允许 luci-base 和本插件，排除其他插件授予 commit 而误掩盖缺陷。
  旧 ACL 必须复现拒绝；修正后 134/152/default/重复值持久化，新会话读取成功，
  其他配置和未登录写入仍被拒绝。E5、MU300 两份实际 ACL 都通过。
- 原实际网络锁定页面 24 组回归通过，覆盖三语言、双尺寸、确认／取消、失败不执行模式任务、
  慢保存时切换查看卡槽的防串卡，以及先保存后单次应用。
- 当前发布 ZIP 未重打包，本轮热修复只在上述 F50 生效。

原理参考：[rpcd UCI 配置权限检查](https://raw.githubusercontent.com/openwrt/rpcd/master/uci.c)、
[rpcd ACL 加载](https://raw.githubusercontent.com/openwrt/rpcd/master/session.c)；
结论同时由本机 ACL 与 HTTP 结果确认，不以最新上游源码替代现场验证。
