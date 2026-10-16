# MU300：对齐 T551M 接入诊断中的 Wi-Fi 修复

只修改 MU300 仓库并离线验证，没有部署 MU300 实机。T551M 上运行的诊断
继续抓取，不修改它的联网配置或重开热点。

## 对比结果

MU300 主线 Wi-Fi 的 `sc2355/rx.c` 存在完全相同的字节序错误：
`eth->h_proto` 是网络字节序，AP/GO 广播组播分支却直接比较 `ETH_P_IP` 和
`ETH_P_IPV6`。小端 CPU 上 IPv4/IPv6 会误入原本只用于非 IP 的额外复制
转发分支，随后原包仍交给网络栈。固件 W2W 标志与桥接 hairpin 允许转发时，
会多发一份组播；是否在 MU300 实机触发，不能用 T551M 的抓取代替验证。

PCIe 和 SDIO 的过期单播 LUT 丢弃仍逐包 `pr_err`，成功查到组播 LUT 也
逐包 `pr_info`，上层 TX 失败再输出 `netdev_err`。这些输出可能在大流量
客户端离线时放大处理负担，不据此声称 MU300 已发生相同的固件卡死。

MU300 已有 `FW_ERROR` 事件和 `wcn-reopen`，也有互斥、按驱动/PHY/路径
选择无线设备、忽略禁用 radio 的逻辑。无需再移植 E5 的另一套恢复通知。
但原脚本只在恢复前检查 disabled，用户在 down 期间关闭无线时仍会被 up。

蜂窝实现使用 `mobile-data`，已有 CGEV 原地更新机制，架构不等同于 E5
的 ModemManager。前一轮已补齐 IPv4 监视器、SPPCODATA/ACT/DETACH 触发、
原地换地址、AT 失败隔离和 watchdog renew；没有搬入不适用的 MM 注册
保护时间。[对应记录](CELLULAR-MOBILITY-20261013.zh-CN.md)。

## 修改

- 主线 RX 比较使用 `htons(ETH_P_IP)` / `htons(ETH_P_IPV6)`，IP 组播交给
  网络栈，保留非 IP、固件单播 W2W、AP/GO、STA 和复制失败处理。
- PCIe/SDIO 的过期客户端丢弃及正常组播 LUT 查找改为
  `pr_debug_ratelimited`；上层 TX 错误通过 `net_ratelimit()` 限速，错误级别
  和释放 skb/message 的路径保留。不改队列、credit、返回值或协议分类。
- 5.4 原厂驱动补齐 `wlan_combo-rx-ip-multicast-endian.patch` 和
  `wlan_combo-stale-tx-ratelimit.patch`；现有 `wlan_combo-*.patch` 构建入口
  自动应用它们。6.18/7.2 使用同一份修改后的主线模块源码。
- `wcn-reopen` 在 down 后重新加载配置、复查 disabled，尊重用户在恢复
  期间关闭 Wi-Fi；保留 down 失败仍尝试 up 的既有策略。

没有新增常驻轮询、复位等待时间或系统重启策略；不关闭 IPv6、hairpin、
mDNS 或客户端互通。

## 离线验证

34 项相关测试通过，覆盖 RX、PCIe/SDIO 丢弃、TX 释放/限速、WCN 恢复与
此前蜂窝续租；shell 行为在测试环境可用的 dash/bash/BusyBox ash 下运行。

RX 测试执行生产转发分支，启用 ASan/UBSan：旧比较重现额外复制，修正版
验证 AP/GO IPv4/IPv6 只交给栈，单播、ARP、复制失败和 STA 行为保留。
实际旧版 patch 应用结果也与主线转发分支一致。
TX 测试在 50,000 次模拟失败中确认每次都释放 skb/message，日志被抑制
不会跳过清理；PCIe/SDIO 的 LUT 拒绝结果保持原样。

从缓存的 realme `4381465ccaf87fcf3215b9cd42f4a685df40e5e0` 原始厂商
源码开始，实际顺序应用全部 5.4 Wi-Fi 补丁成功，不依赖已改过的驱动树。
实机首次接入体验、多客户端和持续下载仍待 MU300 硬件验证。

6.18.54 与 7.2.8 分别在已有内核构建树中重新编译 WCN 依赖和 Wi-Fi
模块成功，使用独立 scratch 目录，未替换现有发布包或实机模块。
vermagic 分别为 `6.18.54`、`7.2.8`，剥离调试符号后 BTF/BTF.base 仍在。
产物保存在忽略目录 `work/wifi-forward-20261013/<version>/`：

| 内核 | Wi-Fi 模块 SHA256 |
| --- | --- |
| 6.18.54 | `07c920ef9ce24bb2fd0b810e339b9b401b5efec17a9b1a43c429ecae70035a93` |
| 7.2.8 | `992f65a333c8264fca79a1d7fc3fb2d40eb67d9f82e464c763884f022e95bbd9` |

5.4 本轮验证的是原始厂商源码的整套补丁应用，未执行完整内核/模块构建。
