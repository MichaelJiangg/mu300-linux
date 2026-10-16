# 2026-10-16：U30 Air 原厂电量、空闲省电及注册事件恢复

## 修复

- `0019-power-UMP9620-battery-board-isolation.patch`：vendor BQ、UMP9620 FGU
  在首次硬件操作前要求原厂启用的 `/charger_policy_service`。
  同一条件用于 UMP9620 PD 入口，覆盖主、备用 I²C 地址。
  无电池 F50/V50 不进入 U30 Air 的电池管理路径。
- `0020-power-UMP9620-stock-retained-soc.patch`：合法原厂格式保存值直接恢复，
  删除低电流下“旧格式歧义”猜测；锁存寄存器恢复原厂 masked RMW，
  保留关机前读取实际库仑计并保存。
- 满电校准移除任意 OCV 70% 条件，使用真实 charger Full 和原厂 battery 节点的
  `fullbatt-voltage/current`。连接 U30 Air 对应 4.2 V、120 mA。
  本轮不修改充电器电压、电流限制。
- SIPC 全局调试类改为模块初始化一次创建，避免多个 IPC 子设备重复创建同名节点、
  覆盖原指针。补驱动注册失败清理。
- 看板空列表增加 hostapd JSON 回退，仅统计已关联 MAC；
  AP 不再用 STA/整接口指标冒充客户端数据，未知速率保持为空。

## 原厂依据

从已连接 U30 Air 的 Android A 槽只读提取模块，在电脑离线分析：

| 模块 | SHA-256 |
| --- | --- |
| sc27xx_fuel_gauge.ko | b677aef2019ac95da686bbf80ce72f2a3f12f22bc5a151e9f6bd187f1e13f074 |
| sqc_bq2560x.ko | ce42c87c42f9ed7e5b5aba8277d4245c03c2c41a569e8ca24d749f07bc3a0efc |
| charger_policy_service.ko | 808b23dce5aee9886df868cd796c8382105b9d99cc80bd2240f8a93fc7b2ac1e |

原厂版本 `5.4.254-android12-9-g9444efdc6885`。
FGU probe `0x1bd0` 为低字节整数百分比、高 nibble 小数；
`save_last_cap 0x4ba4` 使用 masked RMW、200 μs 级等待。原厂模块不进入安装包。

合法保存值如 `580/0x244`（原厂格式 68.2%）不应被当成旧格式并在静置时重算。
现仅无效保存值走 OCV，没有强制校准、99% 上限或重设电池数据。
未声称完整复刻 SQC/CAS、老化学习及全部 JEITA 策略。

## F50/TR3000 报告

原 0016 仅保护 0x1a 备用地址，主地址有响应时仍可能初始化电池路径；
FGU/PD 也缺少统一入口，这是已确认源码问题。
连接 F50 的充电器当前未绑定，但 FGU 暴露虚假电池状态。
本轮 F50 只读检查，未刷入，也未在 TR3000 上复现。
不能把全部启动失败都认定由此造成，也不能认定只是电源问题。

## 验证与部署

- 6.18.54、7.2.8 的 BQ/FGU/PD 对象编译通过；
  7.2.8 完整 Image、BTF 配套根模块及 initramfs 模块已编译、部署。
- `python3 tests/stock_power_driver.py KERNEL_TREE`：4096 电量编码、
  合法值不迁移、电气边界、I/O 错误和无电池入口测试通过。
- `test_u30air_pd.py` 3 项、`test_u30air_integration.py` 8 项、
  `test_power_supply.py` 6 项、`test_fgu_shutdown.py`、
  `test_sipc_debug_once.py` 通过。
- U30 Air 已启动，蜂窝 IP、热点、USB 管理正常；
  SIPC 重复注册告警消失，未见 BTF 或存储异常。
- hostapd 回退已热部署，在实际 ucode 上验证 JSON 和空 dump 分支。

操作检查 `mu300-device=u30air` 和 eMMC 身份，通过独立 IPv6 管理地址连接，
避免两台机器共用 192.168.77.1 时误写 F50。

## 增量：原厂空闲时钟与失去覆盖恢复

再次只读提取本机 Android A 槽 boot，确认原厂启用 NO_HZ_IDLE、
HIGH_RES_TIMERS、HZ=250、PSCI idle/menu。原 OpenWrt 7.2.8 却是 HZ_PERIODIC，
本次在公共配置恢复空闲停表，保留 HZ=250 和业务轮询频率。
这是有原厂依据的时钟配置对齐，不是新增整机休眠，不包含相机、显示电源域修改。

原厂 boot SHA-256：
`e952f155ad9999f9791cbf0098c5ebb8ba2b95d515adf58c383169fdec99c530`；
提取配置 SHA-256：
`c5983d710b35a013d2a0ee63364719e168bbccc3c5520849d959d8b0f220f087`。
原厂 F50 B09 配置也启用了同类 idle tick 策略，因此放在 MU 公共内核配置，
没有给无电池板加入 U30 的充电逻辑。

公共 `mu300-network-recovery` 利用现有 AT owner 的 CEREG 变化，
在当前上网槽恢复 EPS 注册后通知 netifd，继续之前未完成的自动拨号。
新增服务空闲阻塞，不新增串口或 AT 查询；不会插入第二次 SFUN，
不改 APN、CGACT、CGCONTRDP、CGDATA 及预拨号回放顺序。
首次等待无覆盖使用专用退出码 5，区别于无模块、射频需重启和取 IP 失败。
本机原有 CEREG mode=2，已在 nr0 发注册 URC，本次不增加初始化 AT。

U30 的 `mu300-radio-freeze` 在 native 双卡正常工作时也会保留，
用于禁止旧 SFUN 初始化；不能仅凭该文件阻止 PDP 恢复。
新实现要求 native radio-ready，保留切卡和 active-unknown 保护，
尊重手动断网、autostart=false，且只处理当前实际卡槽。

验证：7 项解析/卡槽与 protocol 分支测试、30 项实际 ucode 策略检查、
真实 ubusd/uloop 订阅与退出测试通过；原有移动性 15 项、U30 integration 8 项、
PD 3 项回归通过。7.2.8 完整 Image、26 个 initramfs 模块记录、
根模块树 213 个文件配套重编译，正常重启后确认：

- 实际配置 NO_HZ_IDLE/HIGH_RES_TIMERS 生效，HZ 仍为 250；
- PSCI governor 从 ladder 变为 menu，WFI/core-sleep-lit/cluster-pd 可用；
- 注册缓存由 owner 正常产生，服务运行，WAN 自动取得 IPv4；
- hostapd AP-ENABLED，5 GHz/80 MHz 热点、USB 管理及根分区读写正常；
- 无新的 BTF、Oops、SIPC class 重复注册和存储错误；
- 原 init、cmdline、vendor fallback、48 MiB 后启动日志区和 misc 均保留。

本轮仅对 U30 Air 部署，未刷 F50/V50。备份目录：
`/root/update-backups/stock-power-20261016-184201`。
部署回执保存在工作区 `work/u30air-nohz-recovery-20261016/`。
没有把短时运行检查解释为长时间续航提升或外场无覆盖测试已完成。
后续新机型请使用 [原厂对照与适配清单](NEW-DEVICE-STOCK-ADAPTATION.zh-CN.md)。

收尾：6.18.54 也完成完整 Image 和全部配套模块构建，NO_HZ_IDLE、
HIGH_RES_TIMERS 和 HZ=250 均从最终配置核验；两个版本 Image/config 校验通过。
静态脚本 11 项、SIPC 与 FGU shutdown 回归通过。
静态主题测试同步兼容已有的 apk_retry 包装，保留主题必须内置的检查。
U30 恢复服务实际 RSS 约 1.4 MiB、单线程，空闲阻塞在 epoll。
本次未生成发行安装包，未把 6.18 内核刷到正在使用 7.2.8 的 U30。
未修改 NV、Android A 槽、网络配置或灯控制。
实际充放电、弱电源启动及 PD 扩展坞插拔留给用户验证。
