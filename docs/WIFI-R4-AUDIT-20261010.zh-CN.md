# MU300 r4 Wi-Fi 故障排查与上游核对

## 核对范围

2026-10-10 拉取 `dikeckaan/mu300-linux` 的 main，最新为 `5582413`。
用户报告的包为 `mu300-linux-openwrt-tf-7.2-20261008-r4.zip`，并非当前工作树。
本地同名 ZIP 的 SHA256：
`d3fab024e7cb19b93593c899472010241a789b30f3683967f94ded8fa7ec0d9c`。
用户此前同名 r4 曾重新打包；只有哈希相同才能认定是同一个文件。

## 已确认的内容

- 实际检查 ZIP 内的 rootfs，存在 `lib/firmware/wcnmodem.bin`（986032 字节）、
  `wifi_board_config.ini`（7557 字节）、`wifi_board_config_ab.ini`（6831 字节）。
- ZIP 内安装脚本还会从本机 Android 的 `/odm/firmware`、`/vendor/firmware`、
  `/vendor/etc` 依次查找并复制这些文件；未找到非空文件会中止，不是静默略过。
  这只能证明包和安装逻辑，不代表故障设备磁盘上的文件一定完整或固件适配成功。
- 当前主线驱动的未知项目分支已选择 MU300 的 `wifi_board_config.ini`，
  5.4 对应 `wlan_combo-default-board-config.patch`；不能仅看模块里含有
  `wifi_board_config_hulk.ini` 字符串就认定选错，因为其他项目分支仍合法引用它。
- 本地 r4 中 7.2.8 模块：
  `wcn_bsp.ko` SHA256 `ebfc075de429070f280bfdc9385afab7698dded69787633f7b4b611fc39e4a89`；
  `sprd_wlan_combo.ko` SHA256 `2db2f25642b4a073c1737a30070e644f9f74158813a895d0c67dd27bd373cc1c`。
  它们与 10 月 10 日重建的模块不同，不能把当前源码/重建结果算作 r4 已携带的修复。
- 上游 WCN 上下电串行化/RX 上下文保护 `1f6e825`、PCIe 通道失败清理 `1196cf2`、
  固件日志策略 `f0323bf` 已在本分支 `f092671` 移植；见 `UPSTREAM-SYNC-20261010.md`。
  不重新引入已撤掉的无线速率实验代码，不改已验证的 IPv6 软件校验和路径。

## 本轮补入的上游修复

来源：<https://github.com/dikeckaan/mu300-linux/commit/f7df326eb044bd204c0eb2ab075c2187b94037a6>。

`mu300-update` 仍使用 `cp -an old/vendor/. new/vendor/` 并忽略错误。
OpenWrt BusyBox 会跳过已存在的目标目录，在线升级可能漏掉 WCN 固件、INI、
Android 运行库和旧内核模块。老 BusyBox 不支持 `-n` 时也会被 `|| true` 吞掉。

移植 `copy_missing`：合并缺失项、保留新版已有文件，不进入目标符号链接；
复制或建目录失败则中止，尚未交换旧系统。另加目标根目录检查。
保留本分支已有的 `etc/unisoc-modem` 用户配置和 CPU 模块索引处理。

此问题属于在线升级路径。TF Magisk 全新安装使用另一套复制流程，
不能用它解释所有全新安装失败，更不能据此确定朋友机器的故障原因。

## PCIe 与其他报错的边界

当前 PCIe host 已读取 DT 的 `num-vectors`；WCN 驱动使用 MSI，legacy INTx 默认关闭。
`of_irq_parse_pci`/传统中断映射告警与 MSI 分配失败不是同一件事。
需结合 `pci_enable_msi_range` 返回值、`request_irq`、`/proc/interrupts` 的实际增长，
以及最早一条固件/INI 错误判断；不应为了消除日志盲目添加 interrupt-map。

没有故障设备完整日志，不能证明 TX/重排序错误是固件缺失导致，
也不能把 SIPA、MMC2、hostapd 的全部报错归为同一连锁反应。
特别是 MMC I/O 错误可能反过来导致 TF 中的固件/模块读取失败。

## 验证与部署状态

- `tests/test_update.py` 的隔离测试覆盖已有目录合并、保留新版文件、设备配置、
  隐藏文件、源符号链接、目标符号链接与断链、失败前不交换旧系统。
- `tests/update_vendor_busybox_fixture.sh` 在 `mu300-openwrt-base:25.12.5`
  只读/无网络容器中复现旧 BusyBox 漏拷贝，验证新复制逻辑，不访问实机。
- 本轮实机 SSH 超时，没有加载/卸载 Wi-Fi 驱动，没有重启，也没有更改网络。
- 未生成新 ZIP，已有 r4 文件未改动。故障机的修复确认仍需开机完整日志及实测。

## 后续实机只读核对（用户正在 iperf3 打流）

用户重新接通管理连接后，实机可访问，内核运行 7.2.8。以下只针对这台设备、
这次开机及采样窗口，不替代朋友故障机的日志：

- 热点为 5 GHz、36 信道、80 MHz，hostapd 状态 `ENABLED`。
- 启动日志两次显示读取 `wifi_board_config.ini`，长度 `0x1d85`，解析返回 0；
  同时存在 `CMD_DOWNLOAD_INI / SPRD_CMD_STATUS_UNKNOWN_ERROR`，不能将“文件解析成功”
  写成“固件明确接受了全部配置”。源码对此未知状态仅打印，CRC/索引/长度错误才触发该处理分支的 assert。
- `of_irq_parse_pci rc=-22` 之后有 `pci_enable_msi_range 32 ok`，
  `legacy 0 msi_en 1`、IRQ 50–81 全部申请成功、使能掩码 `0xffffffff`。
  sysfs 确有 32 路 MSI。15.54 秒采样中 IRQ 71 从 84344 增至 93475，
  IRQ 72 从 84758 增至 100808；不存在这次采样中“MSI 没有映射/没有工作”的证据。
- 同窗口 wlan0 TX 从 6699553930 增至 8015505836 字节，约 677 Mbit/s
  （接口计数推算，非 iperf 应用层成绩），RX/TX error/drop 均未增长。
- 磁盘上的两份 7.2 模块哈希匹配 10 月 10 日重建产物，不是原 r4 的模块；
  `image-version` 仍写 r4，因此不能用这个版本标签判断是否带过热更新。
  内核没有暴露模块 srcversion/build-id 文件，未以文件哈希冒充加载态证明。
- 确实出现 `CMD_TX_DATA ... ERROR`，以及 `edma_pending_q_buffer(10) full`。
  后一个 51.27 秒日志窗口中队列满 72 行，未见 TX 命令错误/重排序错误/assert，
  但环形日志会覆盖历史，不能把计数下降解释为错误恢复。
- 同窗口共 46585 行，其中 46155 行是 `sc2355_pcie_fc_test_send_num`：
  源码在发送配额限制分支逐次 `pr_err`，约 900 行/秒，挤掉了启动证据。
  这是可以单独处理的日志噪声/开销问题，不等于固件崩溃；队列满仍需区分流控和实际丢包。
- MMC2 原文为无命令时收到 command interrupt，`Timeout: 0x00000000`
  是随后的 SDHCI 寄存器转储字段，不能据此认定 I/O 超时。
  MMC2 对应 `22220000.sdio`，当前 TF 根挂载在 `mmcblk1p1`。

全程没有改热点/驱动/日志参数，没有重启，iperf3 服务保持运行。

## TX 流控刷屏修复与受控部署

以上只读核对后，用户要求修复并批准安装、重启。此次只替换 WLAN/WCN 模块：

- 配额限制/无 credit 分支不再逐次打印错误，改为限频 debug；新增只读累计计数，
  不新增定时器或轮询，不改 credit 算法、等待时间、队列容量或返回值。
- DMA pending 队列满按通道计数，警告限为每 5 秒最多 1 条（所有通道共享），
  实际 push 失败仍保留限频错误日志。计数是拒绝提交/检查次数，不是丢包数。
- 满队列不接管调用者链表，原有重排队/释放逻辑保留。不能将减少日志等同于消除队列压力。
- 6.18.54、7.2.8 两套模块编译通过，位于 `upstream/out-voltage-*`；
  5.4 对应补丁完成 dry-run，未执行 5.4 全量编译。
- TF 与 kernel bundle 打包入口同时检查 WLAN/WCN 源码是否比模块新，避免误用旧二进制。
  这只是原有时间戳防漏检查的扩展，不替代模块清单/哈希校验。
- 三项回归测试验证生产 credit 函数返回值、5 万次满队列拒绝后的所有权及恢复，
  以及只读诊断/构建接入。限频器在隔离测试中使用替身，并非内核计时实测。

实机 7.2.8 部署备份：`/etc/mu300/backup/wifi-pressure-PjNJMd`。
新模块 SHA256：

- WCN：`16fe4bdd694ba2af1866e679af14a0552c68495142e949f3a14f0ffe05536031`
- WLAN：`f1013a06f725d70702f0bd2dfe79b38ad092bf9d9ed4f942d0c92bd6675c255a`

重启后两个新 sysfs 参数存在，证明已加载新代码；hostapd 状态 ENABLED，
5 GHz/36 信道，32 路 MSI 分配成功。网络、无线、防火墙、DHCP、CPU 电压配置及
USB 重枚举脚本均通过部署前后的哈希一致性检查，CPU 偏移仍为 `0,0,0`。
iperf3 已恢复监听 `192.168.77.1:5201`。高负载效果仍待相同条件打流复测；
未重新打包 rootfs/TF ZIP，也未宣称 INI 未知状态或队列压力根因已解决。

部署后本地完整回归：274 项，272 通过、2 项因缺少指定 OpenWrt 集成环境跳过；
6.18/7.2 构建清单校验均通过。

用户重新从手机启动反向打流，开机 138.13–158.14 秒采样：

- wlan0 TX 1466850219 → 3191337865 字节，约 689 Mbit/s（接口计数推算），
  TX errors/dropped 维持 0；不是应用层吞吐或端到端无丢包的证明。
- credit_limited_checks 13954 → 38182，zero_credit_checks 2498 → 6643；
  流控仍在实际触发，日志不再逐次输出。
- push_failures 与 EDMA ch10 同增 36（510 → 546），说明队列压力仍存在；
  不能写成“DMA 队列满已彻底修复”。
- 20.01 秒内总日志 174 行、原流控刷屏 0 行、队列满警告 4 行、
  push 失败 33 行、限频摘要 5 行。窗口内未匹配到 BUG/Oops/panic/ASSERT/
  CMD_TX_DATA ERROR。修复前约 900 行/秒的特定刷屏在真实负载下消除。
