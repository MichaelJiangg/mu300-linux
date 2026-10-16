# 2026-10-12：无线、升级和 TF 启动链的选择性移植

基于本地 `clean-tf-7.2`，核对上游 main 到
`c47e2c9c935b6c573589ae07e8c7411e7be5911c`。不是全量合并 main，也没有替换看板。

## 用户可见变化

- Wi-Fi 驱动卸载时完整注销并停止看门狗、扫描与 ACK 定时器，避免卸载后访问已释放内存。
- 正常的无线扫描统计、广播查表、重传及 ACK 过滤不再作为错误刷屏；真实错误仍保留。
- 保配置更新保留已有设置，同时补入新版新增的配置文件，不再因整目录覆盖漏掉新功能配置。
- 更新记录用户自行安装的软件包，开机后台尝试重装并恢复其配置和服务状态；不阻塞系统启动。
  无网络会有界重试，并保留失败记录；自行安装且软件源中没有的包仍需用户提供安装文件。
- 对丢失插件留下的失效 DNS 转发项做归属检查、监听检查和提示；不擅自绕过 VPN 或改用运营商 DNS。
- 在线更新、回滚、清理等写操作互斥；拿不到安全锁就停止，不会无锁继续。
- 内核补丁记录内容 SHA256，修复后续补丁修改前序上下文后，再次编译误报补丁失败的问题。
- Android OTA 后，安装前检查两槽启动链，只向 Linux 槽同步有差异的五个启动链分区，先备份再写入、回读。
- SC2355 不具备 DFS 雷达检测能力，热点避开 DFS 信道；有能力的其他驱动仍可使用 DFS。

## 上游来源

| 范围 | 提交 |
| --- | --- |
| 无线卸载 | `f34bf50` |
| 无线常规日志及 5.4 补丁依赖 | `48a9c43`、`13838f5` 的 wlan_combo 部分 |
| 配置文件合并 | `a3ae608` |
| 用户软件包、DNS、Ubuntu 软件源和服务状态 | `355caaa`，及 `383d363`、`c199020`、`67adabc` 等后续修正 |
| 更新器并发保护 | `1f6db8c`、`7106ed9` |
| 重复编译 | `1731406` |
| Android OTA 启动链 | `30c6dae` |
| DFS 热点 | `47d9463` |

## 本分支适配

- 保留 `etc/unisoc-modem`、双卡/AT/短信逻辑、现有 USB 重枚举与低延迟优化。
- 保留本分支 5 GHz 默认配置；新增配置生成器补丁直接接入 OpenWrt 构建，非仅放在安装包 fixes 目录。
- OpenWrt/Ubuntu 构建记录 `etc/mu300/image-packages`，启用后台 `mu300-user-packages` 服务。
  TF 与常规 release 的文件清单检查新增 helper、服务、包列表和 Wi-Fi 配置生成器，缺失则构建失败。
- Android 保配置更新还保留旧账号密码，不设置新 root 密码。
- 更新器自更新 `exec` 复用已持有的 flock 文件描述符，避免重开文件导致短暂解锁。
- TF 安装沿用分阶段校验、容量检查、超时中止及二次读回，不覆盖原实现；新增启动链预检先于格式化。
- TF Magisk 在 Android A/B 槽均可使用。原有桌面 `install.sh` / `install.ps1` 仍要求 Android 在 A 槽，
  本次只补启动链检查/同步，未悄悄扩大其槽位支持范围。

## 启动链写入范围和恢复

仅允许 `uboot sml teecfg trustos vbmeta`，从当前已成功启动的 Android 槽复制到另一槽。
不写 Android 当前槽、不写 NV/校准、GPT、userdata 或 modem 分区。
待完成的 Android OTA、未知机型、分区缺失/尺寸不一致等会拒绝。

备份在 Linux/TF 文件系统的 `.mu300/bootchain/<时间>/`，包含有差异分区的两槽镜像和 `SHA256SUMS`；
安装器另保留 Android 暂存备份，桌面安装器会尝试拉回工作目录。
写入或回读失败会恢复本轮已写的 Linux 槽分区；恢复也失败则明确停止并保留备份，不继续写 boot 或切槽。
软件回滚不能保证应对突然断电，安装时仍应保持稳定供电。

专家可设置 `MU300_SYNC_BOOTCHAIN=0`，Windows 桌面安装也支持 `-NoBootchainSync`。
手动查看/同步可用 Android 的 `mu300-linux bootchain` / `mu300-linux bootchain sync`。

## 软件包恢复

- 查看：`mu300-user-packages status`
- 重试：`mu300-user-packages retry`
- 暂停恢复：`mu300-user-packages skip`
- 更新时跳过重装：`mu300-update apply --no-reinstall`
- 只有孤立 DNS 转发项且无替代服务器时，只提示不自动降级；用户确认后可执行
  `mu300-user-packages repair-dns`。

配置仍在 `etc/mu300/orphaned-config` 中。内核模块不从 OpenWrt 通用软件源恢复，避免 ABI 不匹配。
TF Magisk 仍是全新安装、格式化卡的流程；此处保配置功能用于明确选择 UPDATE 的安装/在线更新，
不是把刷 TF ZIP 改成了无损升级。

## 验证与边界

- 在现有内核构建树分别编译 WCN/Wi-Fi 模块：6.18.54、7.2.8 均成功。只做验证，不替换发布产物。
- 5.4 的整个 wlan_combo 补丁序列已在干净 vendor 源副本上应用成功。
- OpenWrt 25.12.5 容器实际测试 wifi-scripts 生成的 hostapd 配置：有/无雷达能力、自动信道、国家限制和频宽。
- 隔离测试覆盖升级新旧配置合并、软件包恢复/DNS、防并发、自更新持锁、两槽启动链备份/写入失败恢复、重复编译补丁。
- 最后一轮本批专项回归 95 项全部通过，无跳过，包含真实 OpenWrt 容器内的 wifi-scripts 验证。
- 第一轮全仓 404 项通过（5 项跳过）；补齐测试后的全仓 409 项中，原有
  `test_at_client_boundary.test_termination_exits_and_releases_own_lock` 偶发失败，单独复跑 9 项通过。
  当前 AT 客户端先发布锁 PID，随后才安装 EXIT/TERM trap，提前收到 SIGTERM 会留下锁目录。
  该代码不在本批改动中，且用户之前已有暂存修改，未混入修改；不能据此声称全仓完全无问题。
- 没有刷实机、没有进行真实分区故障注入，也未生成新 rootfs/ZIP；驱动卸载的硬件压力测试仍需安排维护窗口。
- 本轮不提交、不推送；此前已暂存的 AT 数据优先配置保持原样，新移植改动留在工作区。

## 后续补齐：IPv6 relay 多前缀路由

核对发现 `23361ce` 已适配 `a2b6d35` 的旧前缀弃用，但遗漏其前置修复
`0f381e9`：旧、新 SLAAC /64 同时存在时，原 `ndp-learn` 只取第一项。

- 现在读取、去重并维护 bearer 上全部公网 /64，逐项补回 LAN 路由；只移除已经离开的前缀。
- 弃用逻辑改为前缀集合差集：仍在使用的前缀绝不弃用，同一批弃用最多三轮，
  WAN 短暂断开后相同前缀返回不误弃用。NAT6/server 模式不注入 relay RA。
- 清理各有效前缀内错误的 WAN /128；保留 LAN 邻居路由优化，但仅为有效前缀添加，
  避免残留邻居把已清理的旧 /128 加回来。匹配支持 IPv6 压缩、补零和大小写形式。
- 保留原有 10 秒轮询、网关寿命保护、地址自恢复和 sipa_eth0 接口选择；
  未改 USB 重枚举、双卡选择或拨号逻辑，也不增加启动等待。
- 增加 `--prefix` 与 `--once` 供诊断和隔离测试，正常服务调用不变。

验证：前缀/弃用和双卡回归共 21 项通过（dash、bash）；另以 BusyBox 检查前缀提取
和地址规范化。WSL BusyBox 的 standalone applet 会绕过测试的 ip/ifdown mock，
因此不把它的模拟路由测试作为通过依据。真实 OpenWrt 25.12.5 容器中的
`runtime_ipv6_prefix_routes.sh` 使用隔离 dummy 网卡与真实路由/邻居表通过；
`runtime_ra_deprecate.sh` 的隔离 veth RA 抓包也通过，校验和、Hop Limit 255、
网关寿命和旧前缀 preferred lifetime 0 均正确。

这是仓库修复及隔离网络验证，不是运营商实际换前缀验收；未热部署、未打包或提交。

## 后续实机部署（用户授权全部部署并重启）

- 目标 F50，TF 根分区，OpenWrt 25.12.5 / 7.2.8；通过此前记录的 SSH 主机指纹确认。
- 部署 18 个文件：更新器及软件包恢复服务、无线信道 helper/配置生成器、IPv6 前缀维护/RA helper、
  WCN 恢复脚本和事件入口，以及配套 WCN/WLAN/蓝牙模块。此前暂存的异步 CEUS/CEMODE 与
  AT daemon-only 保护也一同部署，未修改这些暂存内容。
- 补装唯一缺失依赖 `ucode-mod-socket`（2026.01.16~85922056-r2），未升级其余软件包；
  不从当前安装列表伪造 image-packages 基线，旧镜像仍使用更新器已有的兼容回退。
- 三个驱动用当前源码、相同 7.2.8 配置重新编译，保留 BTF；实机与构建内核的
  BTF SHA256 相同。没有写 boot、misc 或 Android 启动链分区，没有热卸载运行中的驱动。
- 实机备份：`/etc/mu300/backup/live-upstream-20261012.afOKcL/`，含原文件归档、
  新文件清单、配置/文件哈希与前后日志；电脑副本在忽略目录 `work/live-sync-20261012/`。
- 一次授权重启后，运行中 WLAN/WCN Build ID 与新模块完全一致，`recovery_reboot=N`。
  从发出重启到首次复查约 43 秒时 USB 已通；这是抽样上界，不是精确启动性能量测。
- 热点恢复 5 GHz / 36 / 80 MHz，LuCI 实际登录 HTTP 200，AT 返回 OK。
  CEUS/CEMODE 各首次尝试即确认 OK（本次启动约 34 秒），WAN 正常联网。
- IPv4 到 223.5.5.5、IPv6 到 2400:3200::1 均 3/3 成功；到 Cloudflare IPv6 的
  ICMP 无响应，不能把单一目的地址不响应等同全网 IPv6 故障。
  USB 网关 5 次 ping 为 <1–1 ms，无丢包。网络、Wi-Fi、DHCP、双卡配置哈希保持不变。
- 当时 WLAN TX failure 与 WCN EDMA 拒绝计数均为 0，无新增模块 ABI/BTF 加载错误。
  启动早期有来自未更换的 SIPC 启动路径的重复 sysfs 类注册堆栈；重启前日志已不含
  完整启动记录，不能据此做前后数量比较，也未宣称所有内核日志均无异常。
- 相关主机回归 64 项通过。没有制造 WCN 故障、强卸载、在线升级或运营商改前缀来做破坏性验收。
  构建、安装器和 Android OTA 启动链修复只落在仓库，需未来新包使用，不在运行设备上执行安装器。
- 未打包、未 commit/push，原暂存区保持不变。

### DFS 回退策略调整（按用户最终要求）

- 不可用 DFS 信道固定回退到 **36**，保留已设置的 `htmode`：80/40/20 MHz 均不改变，
  不再自动选择 149，也不缩小或扩大带宽。正常非 DFS 手动选择和自动信道不被强制改到 36。
- 国家码及驱动的 disabled/NO-IR/radar/宽度限制仍生效；36 无法合法承载设定带宽时明确报错，
  不通过降低带宽或更换国家码来启动。初次从 Android 导入时没有独立带宽字段，沿用原有默认值。
- 更新开机配置脚本、共享信道 helper、Ubuntu hotspot-start 及 OpenWrt wifi-scripts 补丁；
  20 项测试通过，包含真实 OpenWrt 配置生成、80/40/20 保持、合法性失败及雷达能力分支。
- 四个文件已同步到实机，备份 `/etc/mu300/backup/dfs-width-preserve.hfNbkJ/`。
  实机 shell/ucode 编译与文件比对通过。随后按用户要求执行 `wifi reload radio0`，返回 0，
  hostapd 确认 Reloaded settings for phy phy0；无线 up=true、pending=false，仍为 36 / 80 MHz。
  无线 UCI 哈希未变，USB carrier=1、WAN up=true；未重启整机或重启网络服务。
  未在实机故意切 DFS 造成中断，因此不把这次正常信道重载称为实机 DFS 故障注入验证。

### 提交前复核

- 用户确认提交后，将此前暂存的 AT 数据优先配置与本批选择性移植一同提交。
- 复跑 AT 数据优先、TF 可靠性、启动链、保配置升级、IPv6 前缀、补丁重复应用、
  更新锁、软件包恢复及无线专项测试，共 134 项通过，无跳过；包含 OpenWrt 容器配置生成测试。
- 本次未生成安装包、未 push；TF Magisk 仍为全新格式化安装，不是保数据升级。
