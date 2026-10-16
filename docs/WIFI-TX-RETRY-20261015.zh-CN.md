# MU300 Wi-Fi 发送错误：现场记录与修复（2026-10-15）

本次只分析 Wi-Fi PCIe 发送与特殊报文命令错误。用户确认手机会休眠，
因此不把手机 ICMP 未回应作为无线丢包或卡顿的证据。

## 修复前现场

设备为 F50/MU300，OpenWrt 25.12.5，Linux 7.2.8 #24，
5 GHz 信道 36、80 MHz，USB 管理地址 192.168.77.1。
采集从新加坡时间 19:14:52 开始，计划持续 1,800 秒。
原始日志保存在本机忽略目录 `logs-netdiag-20261015-191452/`，
设备副本在 `/mnt/mu300-disk/logs-netdiag-20261015-191452/`。
设备 syslog 使用 UTC+3，比本文时间早五小时；内核 uptime 可用于精确对齐。

19:25 左右核对到：

- 19:21:29，`CMD_TX_DATA` 收到 `SPRD_CMD_STATUS_ERROR`。
- 19:22:53，通道 10 的 EDMA pending ring 满，连续三次拒绝提交；
  同时记录 `push link fail: -1` 与 `tx return err`。
- 19:25:14，再次拒绝提交。采集起点到此时，`push_failures` 和
  EDMA ch10 计数均从 8 增至 12。
- 同期没有 firmware credit 耗尽，BA reorder timeout 计数保持零。
  这些是提交尝试/重排诊断计数，不能直接换算成丢包数。

整轮于 19:44:56 自动结束，最终仍为 12 次累计提交失败，即本轮新增 4 次；
`CMD_TX_DATA` 通用错误共一次，BA timeout/zero-credit 计数均未增长。
结束后两项诊断开关恢复为 N，采集进程、临时 trace 实例及探针均已清理。
19:45:03 完成本机最终同步与 `SHA256SUMS`，原始文件可据此核验。

额外的 300 秒临时 kprobe 在 19:36:44–19:41:44 记录了
97 次 `sprd_send_data2cmd` 及 97 次应答，全部应答成功。
组播样本的真实描述符位于 5 字节前缀之后，`off=11, lut=4, tid=0`。
探针只记录长度、描述符、EtherType 和协议/端口字段，没有记录业务载荷。
trace buffer 无 overrun/dropped events，结束后实例和探针已删除。
该短窗口没有复现通用错误，不能推断此前失败报文的类型。

采集没有读取 modem 的二进制 spool；原有 `modem-log-drain` 继续运行。
蜂窝诊断来源是内核、AT/URC、vendor 日志与连接状态。

## 与 E5 对照

核对 `D:/Git/e5-linux` 的 `devices/wifi-common.py`、
`devices/t551m/wifi.py` 和 `docs/WIFI-DOWNLOAD-RECOVERY-20261013.zh-CN.md`，
以及本机 `_enceka_wlan_build/modules/sprd_wlan_combo/sc2355/cmdevt.c`
中的 E5 系列 SDIO 实现：

1. E5 已修复 RX 的 IP 组播重复转发、AP ARP/DNS 命令压力问题。
   MU300 已有对应修复，本次没有重复导入或改动这些分流规则。
2. E5 的 `sc2355_xmit_data2cmd_wq` 在添加 SDIO transport flag 之前，
   用 `skb->data + hif->dscr_rsvd` 定位描述符，再设置组播 BK TID。
3. MU300 的 PCIe DMA pending ring 与 E5 的 SDIO 总线不同。
   通道 10 的容量和完成时序需要在 MU300 PCIe 路径修复，不能照搬 SDIO。

本次没有修改 E5 仓库。

## 两项修复

### 特殊报文描述符位置

MU300 的 PCIe fill 函数先写 11 字节 MSDU 描述符，再在前面加
`MSDU_DSCR_RSVD=5` 字节地址前缀。SDIO 则在 fill 后额外添加 5 字节 flag。
原 `sprd_xmit_data2cmd_wq` 在添加前缀后直接把 `skb->data` 当成描述符，
把真实描述符的 offset 字节（11）误读成 LUT，因而没有执行组播 BK 分支。

现在在添加 SDIO flag 之前定位真实描述符：PCIe 跳过地址前缀，
SDIO 使用当前数据起点。与 E5 的处理顺序一致。
修改保留 transport 前缀、Ethernet 内容、其他描述符字段和单播 TID。
这修复了确定的字段定位错误，但还不能证明先前的通用固件错误全部由它造成。

### EDMA 暂满的错误分类和完成唤醒

通道 10 的 pending ring 大小配置为 4，以一个空槽区分满/空，
所以最多保存三条 pending 提交，另有正在 DMA 的提交。
队列满时没有接受新链表，原 WLAN 代码会撤回待完成列表、释放地址 mbuf，
业务数据仍归 WLAN 的待发队列所有。这不是已经证实的数据泄漏。

问题是拒绝提交返回通用 `-1`，WLAN 把它算进连续硬错误计数，
超过 50 次便 flush 待发列表；原 DMA 完成回调也没有专门唤醒这个重试者，
只能依赖其他 TX/固件 credit 事件。是否在本次现场达到 flush 阈值尚无证据。

修改为：

- WCN 对 pending ring 暂满返回 `-EAGAIN`，不接管链表。
- WLAN 保留原来的列表撤回和 mbuf 释放，不增加硬错误预算，
  不因暂满触发 50 次失败的 flush。
- 提交前设置原子等待标记；总线在完成并处理 pending queue 后，
  通过 `tx_complete` 回调唤醒等待的 TX 线程。
  提交前设置标记用于覆盖“完成先于提交返回/线程睡眠”的竞争。
- 成功或非临时错误清除标记，真实硬错误保留原处理。

没有扩大 pending ring、提高 firmware credit、增加常驻轮询或更改蜂窝设置。
WCN 与 WLAN 模块应配套使用，完整修复依赖新的返回码约定。

## 验证和产物

`tests/test_wifi_tx_retry.py` 执行提取自实际源码的 C 函数，启用 ASan/UBSan，
覆盖 PCIe/SDIO、AP/GO/STA、组播/单播、前缀和报文保持、
50,000 次连续暂满、真实硬错误预算，以及完成发生在提交中/提交后的竞争。
两个关键测试用原代码运行时均可重现断言失败，修改后通过。

相关 Wi-Fi 测试命令：

```sh
python3 -m unittest discover -s tests -p 'test_wifi*.py' -v
```

6.18.54 和 7.2.8 的 WCN/WLAN 均编译成功，vermagic 与各自内核匹配，
模块保留 BTF。5.4 vendor WLAN 补丁整组应用及模块编译成功；
5.4 WCN pressure-stats + backpressure 补丁在对应 ZTE 源文件上顺序应用成功。
没有重编完整 5.4 内核映像。
三项 backport 位于 `kernel/patches/`，WCN 补丁已接入 `kernel/build-all.sh`。

本地产物目录为 `work/netdiag/build/<kernel>/`。最初为设备 7.2.8 准备的产物（当时尚未部署）：

| 模块 | SHA256 |
| --- | --- |
| sprd_wlan_combo.ko | ddc9973b141daba55b3c24e1c41ff453b470f95739d067cec6383a3fb77bf9b7 |
| wcn_bsp.ko | ed5fb5952d2ad5a8b75eb52b747ef23048184e2314f387a1f3ab8c61b42cc869 |

本次没有把新模块加载到设备，也没有重启或替换启动镜像。
下一步实机验证应比较同一设备、相近业务负荷下的描述符 TID、
暂满后的重试推进、CMD_TX_DATA 应答及用户感知卡顿。
短时间没有日志错误不能作为所有卡顿已解决的结论。

## 抓取完整性

最初 60 秒的 `timeout logread/ip` 被 BusyBox 的同名 applet 接管而退出；
之后使用绝对路径启动 `system-live.log` 与 `network-events-live.log`。
最初用户态日志仅有环形缓冲的上下文副本，不能声称完整连续捕获了每个事件。
内核起始快照及后续周期快照保留了相关内核错误。
重复内核快照在本机同步过程中按大小分段，以免超过设备的单文件限制。

## 二次审查补齐与实机部署（20:09）

审查确认上述两项修复有代码依据，同时发现原有描述符填充函数中的 skb 所有权缺陷：
PCIe/SDIO 在头部空间不足时释放旧 skb，但新指针只保存在局部变量，
调用者仍继续使用旧对象；分配失败时还可能由调用者再次释放。
提取真实 PCIe 填充函数和命令调用者，低 headroom 输入已用 ASan 复现释放后使用。
这不是本次补丁引入的问题，也尚不能证明它导致了此前那一次固件错误。

补充修改：

- 使用 `skb_cow_head` 扩展头部、处理共享头部，始终保留调用者持有的 skb 对象；
  失败时不释放对象，由调用者统一处理。
- 预留空间包含 offset；扩展后重新取得以太网头和数据路径的载荷指针，
  避免 SDIO 路径在数据缓冲区移动后使用旧地址。
- 组播 BK 分支逐包 `pr_info` 降为 `pr_debug`。
- 新增 `tests/test_wifi_skb_headroom.py`，执行真实 PCIe/SDIO 填充函数、
  命令调用者与普通数据调用者，覆盖头部不足、克隆头部、非零 offset、
  CHECKSUM_PARTIAL 以及分配失败，启用 ASan/UBSan。
- 同步 5.4 `wlan_combo-skb-headroom.patch`；整组 WLAN backport 应用检查通过。
  本轮未重编 5.4 内核。

本轮 Wi-Fi 测试共 35 项：34 项通过，1 项因未设置 OpenWrt 测试镜像跳过。

已部署到 USB 连接的 F50/MU300，地址 `192.168.77.1`，运行内核
`7.2.8 #24`。没有刷写启动镜像或改变基带配置。
现有构建目录已更新到另一份内核，BTF 与实机不同，因此为本次部署单独准备构建目录，
采用实机 `/proc/config.gz` 生成头文件，并以实机 `/sys/kernel/btf/vmlinux`
作为 split BTF 基表；内核未开启 MODVERSIONS。没有关闭模块 BTF 校验。

实机 BTF SHA256：`709c7cdc76557f3c1b90cfe2a551c79f88b9fb4d25530d54d19da0379a5830d5`。
配套 WCN/WLAN 编译后保留 BTF，写入后回读 SHA256、sync，再正常重启。
启动后读取 `/sys/module/*/notes/.note.gnu.build-id`，与新产物核对一致：

| 模块 | SHA256 | 已加载 Build ID |
| --- | --- | --- |
| wcn_bsp.ko | `093bd086040e131889cc173896900775adca608e075a8ebde7c7c9b945ef070f` | `772ce6f971f0396f44383ee1ea78b1b26727fa00` |
| sprd_wlan_combo.ko | `c6097e0ab052e4708043955e62f22c4368dfdae927029c842344bb0b1508023c` | `a667274bb21ccf5e81811f28fdd04b6de4138910` |

原模块备份：`/mnt/mu300-disk/wifi-txfix-backup-20261015-200555`。
本轮实机专用产物：`work/netdiag/txfix-live/`。
此目录产物仅用于当前匹配 BTF 的内核，不能直接替换到后续重新链接的同版本内核。

启动确认热点 `F50_SP_minikano`、信道 36/VHT80、USB 管理和蜂窝 IP 正常；
设备直连外网 3 次 ping 均成功。未出现模块 BTF、符号加载或新的文件系统错误。
早期 SIPC 重复注册 class 的告警在替换前已存在，本轮未处理。
这些启动检查不等于已完成实际手机负载验收。

已开启下一轮 30 分钟临时抓取，自动结束于新加坡时间
`2026-10-15T20:39:21+08:00`，目录 `/mnt/mu300-disk/logs-netdiag-20261015-200921`；
前 10 分钟同时记录命令描述符与应答，不记录业务载荷。
不再 ping 固定的旧手机地址，避免把休眠或地址变化误判为无线掉线。
抓取结束恢复诊断开关、移除临时探针，没有新增开机服务。

## 部署后日志复核（20:28–20:31，阶段性）

手机于新加坡时间 20:23:13 接入，截止本轮检查没有 Wi-Fi 断开、AP 消失、
WCN assert、`CMD_TX_DATA` 通用错误或 BA timeout。
20:27:48 和 20:27:56 各发生一次 EDMA ch10 暂满，返回为 `-EAGAIN/-11`，
没有原来的 `tx return err` 或 flush；两次事件前后五秒采样中 WLAN TX、
SIPA RX 均继续增加，WLAN TX 从约 25.3 MB 增长至 53.7 MB。
这支持“暂满后仍能继续发送”，但不等于有逐包重试时延或丢包率的证明。

原先十分钟的命令探针在手机接入前已结束，因此另开一个五分钟、自动清理的
`command2` 窗口，覆盖当前真实手机会话，保留原窗口记录。
当前会话捕获的组播描述符 `lut=4, tid=1`，应答尚无非零状态。
详细数量与两路外网探测统计保存在
`work/netdiag/txfix-live/review-202843/review-summary.json`。

仍有一个独立线索：手机接入后 uptime 1023.62–1025.81 秒出现六次
`sipa overflow on ep:1 evt=0x10000`，同时记录 `node transfer err=2`。
按当前源码，`0x10000` 对应 `SIPA_HAL_ERRORCODE_IN_TX_FIFO`，
真正的 TXFIFO overflow 位是 `0x20000`，full 位是 `0x40000`；
现有日志把几种事件统一写成 overflow，不能凭名称就认定队列满。
该窗口内 SIPA RX/TX 均有进展，外网 ICMP 连续有回应，没有复现分钟级停滞。
`err_code=2` 的硬件具体含义及出错报文类型尚未确定，不能认定已修复或属于正常现象。
本轮只读日志并补充临时探针，没有重启、修改 Wi-Fi 配置或触碰蜂窝工作模式。

20:31 更新：EDMA 暂满累计增至 14 次，仍为 `-11`；当前手机会话命令探针 61 次发送、61 次成功应答，两路 ICMP 各 649 次应答，序号无缺口。

## 继续分析现有日志（截至 20:34:02）

用户纠正“继续抓”实际是要求继续分析，因此取消了额外安排的下一轮采集及其电脑端
同步进程；原轮次与已有日志保持原样，未切换 Wi-Fi、基带或设备工作模式。

本轮数据进一步表明：

1. EDMA ch10 拒绝提交累计 128 次，全为 `-EAGAIN/-11`。计数增长时 WLAN TX、
   SIPA RX 同步增长，五秒采样 WLAN TX 最高约 40.8 Mbps，接口 TX error/drop
   仍为零，没有 `tx return err`、清队列、WCN assert 或重新关联。
   这是 PCIe 提交背压得到继续推进的证据，不是每个业务包都无损的证明，也不能把
   提交拒绝数当作射频重传或丢包率。未观察到 firmware credit 耗尽。
2. BA 重排超时从零增至 1 次，对应计数 packets=135876。
   一次重排超时不能推出固件卡死，也不能用它直接计算空口丢包率。
3. 手机已接入时的 command2 窗口捕获 136 次发送及 136 次零状态应答，组播 TID=1；
   未出现本次修复前那类通用固件错误。该窗口晚于最初接入，不能覆盖最初的 DHCP 时序。
4. 两路外网 ping 各 739 次应答，序号均无缺口；均值约 48.62/53.28 ms，
   P99 约 112.38/126.25 ms。未见“只发不收”的长时间停滞。
5. 最初接入存在实际延迟线索：关联约在 uptime 1022.38 秒，三次 TX DISCOVER
   日志约为 1022.71、1023.79、1025.93 秒；dnsmasq 在 1026.32 秒集中给出 OFFER，
   ACK 约在 1026.33 秒。从关联到 DHCP 完成约 4 秒。
   SIPA 的六次 err=2 恰好落在 1023.62–1025.81 秒，与该重发窗口重合。
   这使接入期的 SIPA/报文交付路径值得优先检查，但日志不足以证明 err=2
   对应的就是 DHCP 报文，也不能据此确定是驱动、配置重载还是其他调度延迟。

源码还表明 `sipa_free_sent_items()` 的 `retry_cnt=10` 是地址/发送列表查找的重试
变量，并不表示硬件已经对该包重发了十次。当前代码在找到对应 skb 后释放它，
没有按 err=2 自动重发业务包的逻辑；该错误不能草率归类为无害提示。
硬件 err=2 的确切定义仍缺少证据，当前不改写数据面来掩盖它。

离线分析快照：`work/netdiag/txfix-live/review-final-203400/analysis-summary.json`。

## 原厂对比后的判断更新

SIPA err=2 与 DHCP 重发同时发生仍只是时间关联。进一步检查发现 dnsmasq 开启了
地址分配前 ICMP 冲突检测，其约三秒等待足以解释本轮 DHCP 延迟；没有直接关闭
该功能。原厂 F50 B09 二进制中的错误回收与当前实现相同，未发现 err=2 自动重发。
已修复另一个由原厂函数和实际回归测试确认的 BUSY 返回时 skb 未恢复缺陷。
完整原厂证据、修复边界和编译结果见 [SIPA 原厂对比](SIPA-STOCK-COMPARE-20261015.zh-CN.md)。

## IPv6 组播突发的 CMD_TX_DATA 拒绝（21:51 后）

SIPA 修复部署后的十分钟轻量采集没有掉线，两路 ICMP 各 301 次回复、无序号
缺口，但有五次 `CMD_TX_DATA / SPRD_CMD_STATUS_ERROR`。两次错误时间簇没有
对应 EDMA 拒绝、firmware credit 耗尽或蜂窝收包停滞。此前十分钟没有保留命令
报文头，因此不能追溯断言那五个报文的具体类型。

进一步在同一 F50 上，以只记录协议头的临时 kprobe 核对命令请求/应答：

- 电脑经 USB LAN 发送合法 IPv6 链路本地组播 `ff02::fb:5353`，每批八个、
  六批、批间一秒；每包为 12 字节空 DNS 查询，只有少量局域网流量。
- 每批前六个应答成功、后两个状态 `-6`，六批共十二次错误；`-6` 正是
  `SPRD_CMD_STATUS_ERROR`。报文 EtherType、IPv6/UDP 长度、LUT=4、TID=1
  和描述符 offset=11 保持正确，同批字节相同的报文既有成功也有失败。
- 该时段 108 个命令与 108 个应答完整配对，十二个错误均落在上述重放；
  trace 没有 overrun/dropped events。这证明合法普通组播突发能够触发此错误，
  支持命令发送路径缺少适当背压的判断，不是已查明固件内部队列的实现/深度。

`tx_mc_pkt()` 原先把热点的所有 IPv6 组播转为同步固件命令；异步工作队列
不因固件返回非零而保存这些业务包。修改 PCIe 路径，让它返回 IP 分类器：
普通 IPv6 组播与 IPv4 组播一样使用现有数据队列，沿用 firmware credit、
EDMA 完成唤醒和 group BK/TID=1 调度；DHCPv6/VoWiFi 仍可由后续分类器选择
原命令路径，EAPOL 也保持原样。没有屏蔽错误日志、盲目重发未知命令、丢弃
IPv6 组播、增加队列容量或增加常驻轮询。SDIO 的原组播兼容路径暂不变。

实机重新编译使用运行中的 7.2.8 #24 对应配置、生成头文件和 BTF 基表，只
替换根分区 WLAN 模块，备份后正常重启。实际已加载 Build ID 为
`59d4ee2bf0ec9ed532387ead07d29596ca129627`；SIPA/WCN 模块保留前述修复版本。

验收结果：

- 手机重新接入的两次 EAPOL、两次 DHCPv4、两次 DHCPv6 命令全部零状态应答。
- 同样 48 个重放报文全部出现在普通数据发送路径，未进入 CMD_TX_DATA；随后
  连续一批 64 个也全部进入数据路径，合计 112 个；新启动未出现 CMD_TX_DATA 错误。
- 删除设备上仅针对该手机的 IPv6 邻居缓存后，重新经组播邻居发现获得正确 MAC，
  手机 IPv6 五次 ping 全部成功，证明没有把邻居发现组播直接丢弃。
- 更大突发曾触发一次 EDMA `-EAGAIN`，已有背压处理继续发送，没有硬错误清队列。
  外网三次 ping 全部成功，平均约 49 ms；热点维持原 SSID、36 信道/80 MHz。
- 6.18.54、7.2.8 的 WCN/WLAN 模块编译通过，保留 BTF；十四项相关回归通过。
  新测试执行实际四个报文分类函数，覆盖普通组播、IPv6 扩展头、DHCPv6、
  VoWiFi、EAPOL 和 SDIO 保持；去掉新分支后用同一测试复现断言失败。
- 5.4 的对应补丁加入已有 `wlan_combo-*.patch` 流程，整组补丁应用通过；
  没有重新编译或部署完整 5.4 内核。
- 验证结束后三轮临时 trace 实例及其 kprobe 均已删除，原有诊断开关仍为 N。

原始协议头、编译记录、回归结果和实机备份信息保存在
`work/netdiag/cmd-error/`。这轮验证修复的是已复现的突发拒绝路径，不把它
扩展为所有 Wi-Fi 固件错误、大流量或多客户端问题均已解决的结论。
