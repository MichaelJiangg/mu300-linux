# 原厂低电量关机：E5、T551M、VIPME M8、U30 Air

2026-10-18。第 1～5 节记录最初的只读原厂分析；随后实现见第 6 节。未给实机放电做关机实测。

## 结论与证据范围

正常低电量关机由原厂电量/充电驱动、Health HAL、Android `BatteryService` 和系统关机流程共同完成。不能只保留电量显示、等待电池硬件掉电，也不能任意增加一个 5% 或 1% 阈值替代原厂判断。

- E5、M8：已经直接反汇编各自原厂 `services.jar`，确认 `shouldShutdownLocked()` 和 `shutdownIfNoPowerLocked()` 的有效指令逻辑一致。
- 四款机型：均反汇编本机原厂 `sprd-charger-manager.ko`；确认欠压判断、默认关机模式及 Android 模式的通知行为。
- T551M、U30 Air：这轮没有取得对应的 `services.jar`，不把 E5/M8 的上层判断称为这两款机型已经逐指令验证的结果。
- 原厂电压、关机模式来自本机二进制与原厂 DT；相近 vendor 源码仅用于辅助命名和结构解释。

## 1. Android 的正常低电量关机判断

以下来自 E5/M8 本机 `services.jar`，不是直接套用 AOSP 默认值。

`BatteryService.shouldShutdownLocked()` 可概括为：

```text
如果 Health HAL 支持 batteryCapacityLevel：
    仅当它为 CRITICAL 时请求关机
否则：
    batteryLevel <= 0
    且 batteryPresent 为 true
    且 batteryStatus 不是 CHARGING
```

要特别注意：上层支持 `capacity_level` 时，不会再额外用“插着 USB 就不关机”或“百分比必须等于 0”覆盖它。原厂驱动负责在计算 CRITICAL 时考虑有效充电、电流、电压等条件。

条件成立后，`shutdownIfNoPowerLocked()` 向 Handler 投递任务；任务检查 Android 系统已 ready，发送 `com.android.internal.intent.action.REQUEST_SHUTDOWN`：

- `android.intent.extra.KEY_CONFIRM=false`，不要求用户确认；
- `android.intent.extra.REASON="battery"`；
- 经正常系统关机流程，而不是在界面程序里直接强制断电。

E5 原厂 `ShutdownThread.run()` 可见关机广播、ActivityManager/PackageManager 关闭、关闭无线，最后进入 `rebootOrShutdown()` 和 `PowerManagerService.lowLevelShutdown()`。这轮未进一步逐指令分析 Android init 的全部文件系统卸载实现，不能把它与 OpenWrt 的 procd 当作同一实现。

`processValuesLocked()` 已调用上述判断；不是依靠短信、网页或用户操作才触发。具体 HAL 更新频率不据 AOSP 默认定时器作推断。

## 2. 内核的持续欠压路径

四款机型的原厂 DT 都给出 `cm-shutdown-voltage=3100000`，即 3.10 V。它是欠压路径的一个阈值，不代表系统只有低于 3.10 V 才可能因正常电量耗尽关机。

从各自原厂 `.ko` 的 `cm_uvlo_check_work` 可确认：

1. 成功读取实际电池端电压；读取错误不按一个有效的 0 V 样本参与比较。
2. 电压不超过 `shutdown_voltage + 120000 µV` 时累计，否则清零。
3. 累计至少 5 次后，如果内部显示 SOC 四舍五入后的百分比不大于 1，进入关机处理；否则还要端电压不超过 `shutdown_voltage` 才进入关机处理，并走原有写入 0 电量的分支。
4. 低压期间以 200 jiffies 排队复查。四份原厂配置都为 `CONFIG_HZ=250`，对应约 800 ms，实际调度可能更晚。不能笼统写成“电量低于 1% 持续 4 秒就关机”，因为它还有电压条件和首次任务调度。

原厂欠压任务继续复查的电压门槛存在机型差异：

| 机型 | 原厂复查条件 | 原厂最终欠压阈值 | 连续计数 |
| --- | --- | --- | --- |
| E5 | 端电压小于 3.20 V | 3.10 V | 至少 5 次 |
| T551M | 端电压小于 3.40 V | 3.10 V | 至少 5 次 |
| VIPME M8 | 端电压小于 3.40 V | 3.10 V | 至少 5 次 |
| U30 Air | 端电压小于 3.40 V | 3.10 V | 至少 5 次 |

门槛来自函数末尾的复查分支。首次进入欠压任务的全部调用点和各机型温度特例尚未逐一完成二进制核对，不把此表当作完整电池保护策略。

四份原厂 `charger_manager_probe` 都先将 `cm-uvlo-shutdown-mode` 默认初始化为 **2（Android）**，再尝试读取 DT 覆盖；已有四份原厂 DT 未设置该属性。E5/T551M/U30 Air 可见独立 `cm_shutdown_handle`，M8 对应逻辑被编译器内联到欠压函数中。

Android 模式下会停止容量更新工作、把对外 UI 容量置为 0，并执行 `power_supply_changed()`，将关机决定交给上层。模式 0 是 `orderly_poweroff`，模式 1 是 `kernel_power_off`，不能把“二进制包含这两个符号”误当作原厂正常情况下直接采用它们。

U30 Air 的 `cm_shutdown_handle` 还有一个全局状态为 1 时直接进入 `kernel_power_off()` 的分支。这轮尚未完成该全局状态所有写入点的追踪，不能将它随意等同于 USB 在线或正常运行的默认行为。

## 3. 为什么不能仅参照相近源码

E5 原厂 `charger_get_property` 确实暴露 `CAPACITY_LEVEL`；原厂 Health 服务中也保留了读取 `capacity_level` 的路径和状态转换字符串。

核对 E5 `.ko` 内联的临界电量充电例外时，发现实际指令中的电压比较是 3.00 V / 3.40 V，而留存相近源码的宏是 3.30 V / 3.20 V。欠压复查门槛也有原厂 E5 3.20 V 与当前移植源码 3.25 V 的差异。

因此不能把源码里的宏直接标成“E5 原厂参数”。后续修改应优先利用原厂等效的 `capacity_level` 决策，在确实缺少该状态的机型中按本机驱动证据补齐；不要全机型硬塞同一电压门槛。

## 4. 初次审查时 OpenWrt 的缺口

- E5/T551M/M8 移植侧保留了充电管理和 Android 式容量通知，但没有 Android `BatteryService`，目前没有找到接管这一正常关机请求的公共服务。
- U30 Air 的 mainline FGU 有低压中断、容量校准和 `power_supply_changed()`，其驱动 `.shutdown` 回调用于“系统已经关机时保存 SOC”，并非主动发起低电量关机。当前 7.2 配置没有启用 `CONFIG_CHARGER_MANAGER`，也没有找到对应用户态低电量关机接管。
- 适配方向应是接入电源事件，按本机可用的临界状态/原厂条件，调用 OpenWrt 正常关机流程；无电池的 F50/V50 不进入这条策略。不要改 AT 顺序、NV、SOC 编码或用任意固定百分比盖过驱动状态。
- 上述为实现前的审查结论；后续实现、验证与尚未完成的实机验证见第 6 节。

## 5. 固件来源及复核标识

| 机型 | 原厂版本标识 | `sprd-charger-manager.ko` SHA-256 |
| --- | --- | --- |
| E5 | Android 13；`UNISOC/ums9158_1h10_cmcc/ums9158_1h10:13/TP1A.220624.014/2024112822:user/release-keys`；内核 `5.15.119-android13-8-gf0c1c2c751e6-dirty` | `45dd82b92ff16626ccac77fe802c06fccdd3eda68ba0175b17a41c9a0f828d07` |
| T551M | `onetouch/TYT_00CM_FIH/TYT:13/TP1A.220624.014/551MCM08:user/release-keys`；内核 `5.15.123-android13-8-g2054f18da766-ab10` | `bf2717c9ea32e8fe6b1c08e90f5c3cb74c96be9c383d77271291c27dbd157ae6` |
| VIPME M8 | Android 13；`UNISOC/ums9157_2h10_native/ums9157_2h10:13/TP1A.220624.014/wangqingpeng01181306:user/release-keys`；内核 `5.4.210` | `e74ad1138aa269fd2b8394ccdd587ebd95e82512b6ca440475707f1999298dc9` |
| U30 Air | 已留存本机 Android A 槽模块；内核 `5.4.254-android12-9-g9444efdc6885` | `b192f17e0be983b4e9a6a4310b8bb4bab12a93a334b364883dcd42d4967ce05e` |

`services.jar` SHA-256：

- E5：`865cdef80249bd3c98edb4a226f357651a0990afa3ee858aba4cf211553c9aec`
- M8：`7dce09f3a90e6487ab00a8627dfd967f65ceb79d361f8b7eba72c264f33da752`

离线反汇编和函数地址保存在 WSL `/home/kano/low-battery-stock-20261018/`，其中 `stock-module-evidence.json` 记录四款模块的来源、哈希和函数范围。E5 `cm_uvlo_check_work=0xdb7c`、`cm_shutdown_handle=0xdd28`；T551M 分别为 `0xd634`、`0xd7e4`；U30 Air 分别为 `0x5e84`、`0x6048`；M8 内联逻辑位于 `cm_uvlo_check_work=0xcdfc`。

## 6. 低电量关机实现

两仓库使用同一份 `policy.uc`、`guard.uc`、`read.uc`、`events.uc`、`watch.uc`；板级差异保留在各自 `adapter.uc`，不共存另一套旧低电量关机逻辑。

- `unisoc-battery` 由 procd 管理，启动时先订阅事件再读取一次当前电池状态。
- `/etc/hotplug.d/power_supply/80-unisoc-battery` 将内核电源事件发送给监听器，监听器重新读取 sysfs，不信任事件附带的百分比或关机指令。
- 正常电量时阻塞等待 ubus/uloop，**没有定时轮询**。充电限制关闭或暂停不影响低电量保护。
- 有效 `capacity_level=Critical` 直接请求正常关机；该属性不可用时，使用有效的 0% + 电池存在 + 状态不是 Charging。属性存在但读取失败或值无效时，不擅自当成“不支持”改走另一条百分比判定。缺失/无效数值不转换为 0。
- 调用 `/sbin/poweroff`，没有 `-f`、直接 reboot 系统调用或人为缩短 procd 停服务/卸载流程。每个已接受的请求只执行一次；进程由 procd 在正常关机中停止，不留下磁盘锁或持久化标记。
- E5/T551M/M8 由已有 charger-manager 保留临界状态的充电例外、温度和欠压判断，本次不修改其电压宏、电量计保存或 AT/NV 路径。三个板级 stager 和公共完整 rootfs 构建均启用服务，旧基础镜像重组时也会安装所需文件及启动链接。

### U30 Air 的额外适配

mainline `sc27xx_fuel_gauge` 原来的低压/库仑计中断只在 suspend 路径启用，正常 headless 运行不能据此保证有电量事件。`0022-power-UMP9620-awake-battery-events.patch` 接通已有硬件事件：

- 仅 UMP9620，且此前已有的本机电池 policy probe 门槛仍先于硬件初始化；无电池 F50/V50 不进入这个 FGU 路径。
- 两个 IRQ handler 注册成功后启用已有的低压和 **1% 库仑计变化**中断，resume 恢复该掩码；实际电池取出时屏蔽，重新插入时开启。其他 PMIC 保持原行为。
- 不增加内核周期工作，不改电量表、保存格式、校准、充电电流或 AT 时序。库仑计中断通知可使低电量保护不再依赖用户打开看板读取 SOC。

用户态为 U30 Air 补上本机持续欠压条件：最终电压来自 DT `cm-shutdown-voltage`，偏移 120 mV、至少 5 个有效低压样本、800 ms 间隔；电压样本读取失败不计为低压，电压恢复则清空计数。

mainline 首次低压硬件告警使用电池 DT 的设计最低电压，本机为 3.45 V，略高于原厂复查门槛 3.40 V。因此适配中的**监测窗口**取两者较高值，在首次硬件告警后继续观察，避免清除一次中断后漏掉后续压降。这个窗口只决定什么时候暂时复查；**关机条件不提高**，仍是本机的持续低压计数及 SOC/3.10 V 条件。电压回升离开告警区即撤销定时器。

服务和事件入口都只允许 U30 Air，F50/V50 不启动守护进程、不运行充电操作，也不会因虚假 FGU 读数关机。

### 验证与发布状态

测试入口（Linux/WSL，使用本地已有 ARM64 OpenWrt 镜像且禁用测试容器网络）：

```sh
python3 openwrt/tests/battery-guard.py
```

- 各仓库 45 项真实固件 ucode 策略/输入解析检查；E5 另有 4 项板级适配，MU300 另有 9 项。
- 真实 hotplug → ubus → uloop 测试：正常状态无定时读取、内核入口事件可触发、重复事件只产生一次模拟关机、SIGTERM 正常退出。
- 真实 800 ms 定时器与事件突发交错测试，以及首次硬件告警后继续压降的回归；所有关机操作都是模拟回调。
- E5 三个 model stager、幂等启动链接及完整构建入口检查；MU300 init 中执行真实 model 门槛，确认 F50/V50 不启动。
- MU300 两套实际内核源码提取 C helper 编译运行测试：非 UMP 隔离、寄存器掩码、I/O 错误、插拔电池、IRQ 注册顺序、resume 恢复；6.18.54 和 7.2.8 的 FGU 对象均已交叉编译通过。

本次没有物理低电量放电、插拔电池或满载压降验证，不据离线测试宣称实机关机已验证。之前已生成的 `20261018-full-012536` 安装包未被修改，仍不含本功能。U30 Air 生效还需要重编译并配套安装 FGU 内核模块，不能只部署用户态脚本就声称完整生效。
