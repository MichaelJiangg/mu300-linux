# F50 原厂 SIPA/Wi-Fi 对照与重试适配（2026-10-15）

## 范围与结论

只处理 MU300 仓库。用户要求停止抓取，现有设备采集、诊断开关及临时探针均已停止/
恢复；额外续抓任务已经取消。离线分析没有切换 Android 或改写 NV；用户随后要求
应用实机，部署阶段进行了正常重启，详见末节。

现有日志能够证明 Wi-Fi 的 PCIe 暂满不再触发原先的硬错误清队列路径；
不能证明所有接入卡顿、SIPA 错误码或移动网络故障均已解决。
原厂正常使用体验值得作为对照，但原厂驱动也包含历史缺陷，不能整段替换照搬。

## 原厂样本与逆向证据

使用本机既有的 **F50 B09 原厂样本**，没有把其他型号或开源重编模块当成原厂：

| 模块 | SHA256 |
| --- | --- |
| sipa-core.ko | `c486af35edf9122a07ae2f5dd6751c358505c88852900b403954bf953d4cf75d` |
| sipa_eth.ko | `0bde5887bfb9f977ab4b1e3b9bfd11934fe253605d788f144ed196ff74502934` |
| sprd_wlan_combo.ko | `c43c02e387fcb6073e691541d9033325285fb6e0ea5ca574601285a448b3435b` |
| wcn_bsp.ko | `8ec00055d6988ed5fdabdf94e7a59433630baf830599a2f10f05852723dc056e` |

源文件路径、大小及哈希保存在 `work/netdiag/stock-compare/stock-modules.json`。
使用 AArch64 objdump 的带重定位反汇编，不依赖网上推测的伪代码。
原厂 F50 B16 目录里的 vendor_boot 镜像为空文件，未把它当作可分析样本。
IDA 插件当前未连接，因此本轮没有声称进行 Hex-Rays 反编译。

原厂可核验的函数与地址：

- `sipa_eth_start_xmit`，`sipa_eth.ko +0xaa8`：`+0xb94..0xbc0` 判断 headroom
  与 mac/network header，相等则 push 14 字节；`+0xbc4..0xbd4` 调用 `sipa_nic_tx`；
  错误路径 `+0xc3c..0xc9c` 最终返回 BUSY（0x10），没有把新增头部 pull 回去。
- `sipa_sender_notify_cb`，`sipa-core.ko +0xbd78`：测试 `0x70000` 后统一打印
  overflow，增加计数并唤醒回收线程。与当前开源代码相同，不能只按日志名称解释。
- `sipa_free_sent_items`，`sipa-core.ko +0xc04c`：`+0xc270..0xc27c` 提取节点
  低四位错误码，非零仍进入警告和正常回收路径；`+0xc1cc..0xc1d4` 释放对应 skb。
  没有发现针对 err=2 的业务包重新提交分支。该编号的具体硬件含义仍未知。
- `sipa_skb_sender_send_data`，`sipa-core.ko +0xc7f0`：使用 skb head DMA 地址、
  length、headroom offset、netid/src/dst 构造描述符，行为与当前实现一致。
- `sprd_xmit_data2cmd_wq`，原厂 Wi-Fi `+0x2171c`：同样在 transport prefix 后从
  skb 起点误取描述符字段（`+0x217c4..0x217cc`）。原厂旧版本也有这一历史缺陷，
  因而保留本仓库已验证的描述符位置修正。

反汇编文本保存在 `work/netdiag/stock-compare/*.asm`。
原厂 Android IPA 状态另参考仓库已有 `docs/reference/android-ipa-state.txt`。
这些证据不等于已经逆向了基带/WCN 固件内部的硬件错误码表。

## 修正 DHCP 延迟的判断

本轮关联到 DHCP ACK 约四秒，前三次 Discover 后 dnsmasq 才集中输出 Offer。
同窗口有六条 SIPA err=2，因此之前记录把它列为关联线索；不能据此认定因果。
进一步只读检查发现，当前 dnsmasq 配置没有 `no-ping`，也没有显式设置 UCI noping。
其分配地址前的 ICMP 冲突检测会等待约三秒，这与现场时序相符。
维护者对此行为有明确解释：
https://lists.thekelleys.org.uk/pipermail/dnsmasq-discuss/2019q1/012833.html

因此，四秒 DHCP 延迟现在有独立且更直接的解释；尚未逐包证明这次等待就是该检查，
不能把 SIPA err=2 说成已证实的 DHCP 故障。没有为缩短时间直接关闭地址冲突检测。

## 已实施的公共修复

修改 `upstream/modules/sprd_modem/sipa_v3/sipa_eth.c`，MU300/F50/V50/U30Air
的 6.18/7.2 构建共用，未修改 E5 仓库：

1. 只有提交被接受时保留新增的 Ethernet headroom；未接受、返回 BUSY 前恢复
   skb data 与 length，避免 qdisc 用同一 skb 重试时重复 prepend 头部。
2. CHECKSUM_PARTIAL 发送前仍按原厂清零相应 TCP/UDP 字段，但 BUSY 前恢复原始
   校验和 seed，避免未接管报文被留在已修改状态。
3. `skb_linearize` 失败且已经释放 skb 时返回 NETDEV_TX_OK，明确告知上层已经
   消费报文，而不是返回不属于 ndo_start_xmit 合约的负数。
4. 发送与流控回调把 IRQ flags 局部化，作为上下文整理；未把旧的共享变量认定为
   本轮已复现的故障或根因。

没有改变成功提交的格式、SIPA 错误后的未知硬件行为、射频参数、队列容量、
firmware credit、基带拨号或 NV。不会按未知 err=2 直接重发，以免重复投递。

## 验证与当前实机状态

`tests/test_sipa_tx_retry.py` 抽取实际 `sipa_eth_start_xmit` 函数，用 ASan/UBSan
执行 IPv4/IPv6、TCP/UDP、Raw IP/已有 Ethernet 头、部分校验和的 16 种组合，
每种组合交替返回 EAGAIN/EINPROGRESS 共 50 次后接受，验证报文与校验和保持。
同时验证接口关闭和线性化失败时的消费/返回语义。

同一测试运行原函数，成功编译后在首次 Raw IP BUSY 返回时触发
`skb.data==original_data && skb.len==original_len` 断言；修复后通过。
与已有 Wi-Fi 回归一起运行共 13 项，全部通过。

Linux 7.2.8 与 6.18.54 的整套 sprd_modem 编译成功，sipa_eth.ko 保留 BTF、
vermagic 匹配各自构建内核，产物位于 `work/netdiag/stock-compare/build/<version>/`。
这些使用当前构建目录，**不能直接替换运行中的 7.2.8 #24**（其 BTF 基表不同）。

## 实机部署结果

用户要求应用后，已部署到连接的 F50，保留运行中的 **7.2.8 #24** 内核。
新模块使用该内核对应的配置、生成头文件及精确 BTF 基表重新编译，未使用上述
当前构建目录里的不同内核产物。BTF 基表 SHA256 为
`709c7cdc76557f3c1b90cfe2a551c79f88b9fb4d25530d54d19da0379a5830d5`。

根分区模块先更新后发现 SIPA 在 initramfs 提前加载，因此同时更新 Linux B 槽
启动镜像中的 `linux-modules/sipa_eth.ko`。通过追加一个 ramdisk 段覆盖该文件，
解析校验所有有效条目，确认只有该模块变化；内核、原 ramdisk 内容、Android A 槽、
misc 和 NV 保持原样。写入前备份、写入后回读校验，保留 48–56 MiB 的启动日志区。

重启后从实际加载模块的 GNU Build ID 核验：

| 模块 | 已加载 Build ID |
| --- | --- |
| sipa_eth | `a71036b7885a85cee498bd51a6555690c865ed26` |
| wcn_bsp | `772ce6f971f0396f44383ee1ea78b1b26727fa00` |
| sprd_wlan_combo | `a667274bb21ccf5e81811f28fdd04b6de4138910` |

USB 管理连接、LuCI 登录页正常；热点保留原配置（36 信道、80 MHz）；蜂窝获取
IPv4，外网三次 ping 无丢包，平均约 58.7 ms。未发现模块格式/BTF 加载错误、
未知符号、EXT4 错误或内核崩溃记录。部署信息、备份和读回结果位于
`work/netdiag/sipa-live/`，设备备份位于
`/mnt/mu300-disk/sipa-tx-backup-20261015-205456/`。

没有重新开启采集或进行新的手机接入/大流量压力测试。SIPA err=2 的报文类型
与硬件含义仍未完成确认，不能把本次重试合约修复宣称为它的已证实根因。
