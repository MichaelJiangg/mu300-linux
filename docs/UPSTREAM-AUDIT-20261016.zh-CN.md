# MU300 上游扫描与适配（2026-10-16）

上游基线：[main 2c13e7bb](https://github.com/dikeckaan/mu300-linux/commit/2c13e7bb5227055561363c5a8150350e9a518058)。
扫描获取了 main 的 1162 条提交元数据、60 个 issue 和 205 个 PR；
另保存当前 main 相对本分支的提交标题，并按当前架构核对相关实现。
原始快照在被忽略的 `work/upstream-audit-20261016/`；本页与旁边的 JSON 索引保留可提交记录。
这是功能/缺陷适用性扫描，不等于对 205 个 PR 的每一行代码做了安全审计。

上游审查部分只改 MU300 仓库；后续追加的 SIM 事件要求在两仓库分别实现。
E5 仓库另行后台编译 E5/M8/T551M。
已有等价或更新实现的内容不重复导入。下面列出的缺口均修改现有处理入口，
不另外启动一套拨号、AT owner 或硬件恢复服务；旧配置仅做首次迁移，当前配置随后为唯一来源。
普通启动、RIL 握手、已有 AT 归属、预拨号锁回放与 CGACT/CGCONTRDP/CGDATA 顺序不增加固定等待，
不新增正常启动 AT 查询；不以关闭 HS400、全局禁止 eMMC 休眠、预装 Docker/VPN 来掩盖问题。

## 用户指定的问题

| 来源 | 结论及本轮处理 |
| --- | --- |
| [#225 / PR #232](https://github.com/dikeckaan/mu300-linux/issues/225) F50 路由器 USB 口重启 | 已有 0016 与新增于上一轮的 0019 覆盖。后者在 vendor BQ、FGU、PD 首次硬件操作前检查本板启用的 charger_policy_service，覆盖主地址与备用地址；不重复导入同一补丁。不能采用已被上游放弃的“part=0 就拒绝”，真实 SGM41513 的 part 可为 0。没有在本轮假装复测 TR3000。 |
| [#231](https://github.com/dikeckaan/mu300-linux/issues/231) 广电大小写翻译 | 当前 common.js 已将国内运营商名去空格/横线/下划线并转大写映射；新增 CHINA BROADNET、China Broadnet、china_broadnet、CHN-BG 及国外运营商原样保留回归。不覆盖已有三语言实现。 |
| [#259](https://github.com/dikeckaan/mu300-linux/issues/259) 企业微信 Webhook | 当前编辑器已有企业微信独立预设（msgtype/text/content）、errcode=0，后端按 JSON 标量校验；与上游旧页面不同。实际 OpenWrt 隔离测试验证，无真实短信或外部发送。修正旧测试夹具与公共电池发现库的接口，不改变业务配置。 |
| [#253](https://github.com/dikeckaan/mu300-linux/issues/253) U30 缺电后的冷启动无模组 | 没有可直接证明本报告根因的日志或上游确定修复。保留已有 SIPC sbuf-ready 入口；补“节点存在但首次 open 返回 ENODEV”有界重试。成功描述符始终保留，不在线重启 AT owner，不自动循环 SFUN。不能把这写成所有欠压冷启动已实测解决。 |
| [#226](https://github.com/dikeckaan/mu300-linux/issues/226) AT 服务冷启动失败 | 既有节点等待之外，补首次 open 失败重试和有效 stderr；正常第一次 open 成功不运行 date/sleep。URC 首次 open 同样处理，成功后 EOF 仍不重开。issue 后续已明确报告 eMMC HS400ES -84、无 mmcblk0；此时固件不存在，AT 等待不能修复存储。既有 ordered MMIO / DLL phase 修复保留，不凭报告统一禁用高速模式。 |
| [#194](https://github.com/dikeckaan/mu300-linux/issues/194) 内置卡可识别却不能用 | U30 native 双卡已接入，不再使用上游旧的“仅 F50 支持 slot1”限制。F50 本分支已按卡槽寻址并在 PDP 前选择/回读 SPSWDATA、使用 sipa_eth8。本轮补当前 data_sim 未设置时，旧 network.wan.sim_slot=1 的首次迁移，以及明确选择 data_sim=1 却仍 sim_slots=1 的能力迁移；在 AT owner 布局建立前执行。不会把所有 F50 强制变成双卡。具体额外预制命令、混刷基带/锁频段及特定内置卡的注册问题，仍需要该硬件证据，不能伪称已全部修好。 |

## 从其他 PR / main 补入的缺口

- [PR #260](https://github.com/dikeckaan/mu300-linux/pull/260)：
  U30 同槽选择在数据手动关闭时不等待 IP；各失败/回退路径保留断网标记。
  F50/V50 普通数据卡切换同样尊重 netifd autostart=false，避免主动关网后被切卡打开。
  已选择但无套餐/信号的卡仍允许保留，不能把“选卡”变成强制外网连通性测试。
- [PR #263](https://github.com/dikeckaan/mu300-linux/pull/263)：
  本分支已经修过命令锁返回值与 EBUSY，本轮补两个 blocked 窗口回复长度清零，
  get_station 回复结构初始化，防止未发送/短回复带出旧栈字节。
  保留已有 WPA3 和发送队列修复，不导入另一套实验性 SAE 配置或强制退回 WPA2。
- [PR #230](https://github.com/dikeckaan/mu300-linux/pull/230)：
  mu300-update 与 Android 安装/更新路径均保留 /etc/crontabs。
  桌面更新继续调用同一库；真实 apply_one 的隔离夹具确认用户计划任务保留。
- [PR #264](https://github.com/dikeckaan/mu300-linux/pull/264)：
  镜像构建移除 uhttpd key/crt，发布审计拒绝私钥；
  导入上游已发布私钥的 SHA-256 名单及一次性迁移，仅删除匹配的已知共享密钥，
  自建密钥不动。检查到本地六份历史/基础归档均没有该 key，
  不能把上游已发布包的影响范围直接宣称成我方全部旧包受影响。
- 上游 main 的 SIPA 初始化顺序：
  runtime PM 在启动可能立即收到 ENABLE 的 delegate 线程前启用，
  启动失败撤销 enable；不增加等待，也不改变基带 AT 握手。
- 上游 UMP9620 watchdog 系统挂起修复：
  仅 system suspend_noirq 保存运行状态并停表，resume_noirq 重装计数并恢复；
  不开启新的整机睡眠策略、不改变运行时喂狗、正常启动超时或 radio 时序。
  本地增加寄存器读取失败返回，未知状态不能被当作已停表。

## 没有照搬的内容

| 来源 | 原因 |
| --- | --- |
| PR #261 电量保存 | 已有 shutdown 保存及后续原厂 masked RMW 修正。上游此 PR 仍沿用早期 force-write 版本，不能覆盖本分支的实机依据。 |
| PR #256 / #258 全量模块、Docker | 现有 KVM/Docker 内核依赖已通过本分支检查，xt_nat 等已包含。不为同步而升全部内核/加入三千余模块，更不预装 Docker/VPN 引擎。 |
| PR #237 / #257 实验 SAE 路线 | 本分支有经用户验证的 WPA3 实现，保留其流程。上游关于 PMK 关联 IE 来源的疑问需要单独验证，既不宣称已排除，也不因未证实疑问砍掉功能。 |
| PR #248 漫游开关 | 是新用户策略/API，不是修复已有回归；本分支 APN 字段与其 roaming 含义不同，且其退出码 4 与本地双卡异常码冲突。本轮不直接 cherry-pick 整套拨号脚本或新增轮询，避免改变已测试握手。 |
| PR #224 / #266 完整 lossless-update/增量硬链接更新 | 更新布局、清单、回滚与桌面后端与本分支不同；先补确认缺失的 crontabs，不用上游旧安装器替换现有 Tauri、独立分区和安全检查。 |
| PR #265 镜像源回退、#244 网页设备管理 | 新功能和不同宿主安装器，不覆盖现有实现；不混入本轮硬件修复。 |
| issue #229、5.4 专用补丁 | 按此前用户范围，不继续维护/编译 5.4。 |
| issue #220/#170 无 CP / 早期硬挂、#54 USB3、#188 T780、#202 VPN | 不把 DMA 警告、mbox 日志当作已证实原因；保留已有权限/驱动排序修复。其他 SoC、接口硬件能力及 VPN 模块并非本轮可凭报告直接修好的项目。 |

## 验证与限制

另按本轮追加要求补入 SIM 状态事件：现有 URC owner 筛选原厂 ECIND type 3，
已有恢复服务经对应卡槽 AT owner 确认 CPIN。只缓存明确的无卡/ready/locked，
不把 timeout、busy、另一槽或无作用域 CPIN 当成无卡。
U30 的 SIM 未上电也会返回 CME 10，故还核对现有上电事务；明确关电后撤销空卡结论，
避免缓存阻止下次正常上电。事件确认也不早于 SMMSWAP、预拨号回放与 native 切卡序列。
确认无卡后 netifd 等待可用性事件，短信服务停止空卡查询和 SIM 存储操作；
插卡后仍走原拨号/短信初始化，不增加正常启动 AT 查询或另外一套守护服务。
没有关闭整颗 CP 或强制改变 U30 native 双卡的 RF 管理顺序。
硬件不提供插拔通知时不能假装支持热插拔；尤其 native RF 混合状态的已知安全限制仍保留。
E5 仓库的原厂二进制证据和边界记录于 `docs/SIM-EVENTS-20261016.zh-CN.md`。

- 首次 open 的真实 shell 行为分别在 dash、bash、BusyBox ash 验证：
  立即成功不读时钟、不 sleep；首次失败后保留成功 FD；永久失败按预算退出。
- F50/V50 选卡、U30 native 切卡、同槽手动断网、平台配置迁移及正常默认值分别回归。
- 上游 TLS 指纹迁移测试验证仅删除匹配项，个人密钥与空文件保留。
- 实际 OpenWrt jshn/ucode 夹具验证短信转发与服务成功响应，传输均为本地 stub。
- SIPA 初始化及 watchdog 挂起函数使用真实 C 函数抽取编译、假硬件测试，
  不是只匹配源码关键字。
- Wi-Fi（WCN 依赖与 sprd_wlan_combo）、SIPA sprd_modem 模块、watchdog 对象
  分别在 6.18.54、7.2.8 编译通过。没有把对象/模块验证说成已完成新的 MU 全量发布包。
- 本轮相关回归通过：AT 首次 open 3、选卡 7、双卡上电 5、平台迁移 8、
  U30 热切换 34、TLS 密钥迁移 9、真实 C 电源回调 2；注册 7、移动性 15、
  静态 11、SIM 事件 5、作用域 5、短信容量 11。
  OpenWrt ucode 的注册/SIM 策略 37 项及实际 ubus 订阅测试通过。
- 本轮没有向连接设备自动刷入这些 MU 修复，没有切卡、发短信或改写 NV；
  软件及构建验证不替代特定 F50 内置卡、TR3000、欠压后冷启动的实物复测。
