# U30 Air 无线空闲延迟：原厂低延迟策略与 CPU idle 对照

日期：2026-10-19。承接 [逐包定位记录](U30AIR-WIFI-ADB-20261019.zh-CN.md)。

## 已确认的差别

同一台 U30 Air、同一无线固件下，原厂 Android 并没有采用与 OpenWrt
相同的 CPU idle 策略。本机原厂 `/vendor/etc/init/init.md.rc` 明确包含：

```rc
# zte add for feimao lowlatency
on property:sys.boot_completed=1
    write /sys/devices/system/cpu/cpu0/cpuidle/state0/disable 1
    write /sys/devices/system/cpu/cpu0/cpuidle/state1/disable 1
    write /sys/devices/system/cpu/cpu0/cpuidle/state2/disable 1
```

这里连 cpuidle 的 WFI 状态条目都禁用了，不只是关闭 PCIe ASPM。实机读回
CPU0 三项均为 1。禁用 cpuidle 条目不等于证明 CPU 持续忙等；架构默认
idle 的回退行为须另外核对，不能据这三个 sysfs 值推算 CPU 占用或功耗。
另外，原厂 Power HAL 的 `mtp_usb` 场景会关闭全部 CPU 的 state1；不能把
USB 连接时的原厂测试当作所有省电条件均与 OpenWrt 相同的基准。

证据来自本机 Android，而非另一机型的通用源码：

- Android fingerprint：
  `ZTE/U30Air/U30Air:13/TP1A.220624.014/20241127.203422:user/release-keys`。
- 内核：`5.4.254-android12-9-g9444efdc6885`。
- `init.md.rc` SHA-256：
  `232fbde02ba4409f2e219cbb09c48503ae115dbd1e7fe93f5dd3b5a59c179f11`。
- `power_scene_config.xml` SHA-256：
  `c4f4fa23af0464ba0f21221156439a6949d8ff572e9da510918fe1681f09bb18`。
- 无线固件和两份板级 INI 与 OpenWrt 相同，详见前序记录。

## 双向 A/B/A 验证

在 OpenWrt 上仅短时改变 CPU0 的 state1/state2，保留 WFI、其他 CPU 和
原无线设置；同一实验中始终用同一时钟偏移基准统计固件接收事件时间戳的
相对交付等待。每段 22 秒，设备端 trap 自动恢复原设置。

| 阶段 | 事件数 | 平均相对等待 | 最大相对等待 |
| --- | ---: | ---: | ---: |
| 原 idle 设置 A | 38 | 34.404 ms | 99.751 ms |
| CPU0 仅 WFI | 41 | 0.619 ms | 1.966 ms |
| 恢复原设置 B | 25 | 22.500 ms | 73.059 ms |

随后在原厂 Android 上反向验证：保存 CPU0 原始三个 disable=1，短时改为
0，再恢复 1。每段 20 秒，亦由设备端 trap 恢复。

| 阶段 | 事件数 | 平均相对等待 | 最大相对等待 |
| --- | ---: | ---: | ---: |
| 原厂设置 A | 39 | 0.613 ms | 1.200 ms |
| 允许 CPU0 idle | 31 | 6.658 ms | 81.121 ms |
| 恢复原厂设置 B | 45 | 1.201 ms | 1.746 ms |

OpenWrt 同轮手机普通 ping 的三个约 22 包窗口，平均 RTT 分别约
75.9 / 35.2 / 58.9 ms，也随 CPU0 策略变化。原厂反向实验的手机 RTT
窗口约 30.2 / 31.6 / 27.1 ms，没有出现与事件时间戳同幅度的变化。
因此只能确认原厂策略不同、OpenWrt 此轮实际 RTT 存在相关变化，不能
把原厂事件时间戳的 81 ms 直接称作手机新增了 81 ms 延迟，更不能认定
CPU idle 已解释全部差别。固件时间戳具体生成位置仍未完整逆向；表中数值是
同一实验内的相对等待，不能冒充手机完整 RTT、绝对固件处理时间或功耗。
普通手机 ping 还包含手机自身省电、发送调度和下行等待。

## 中断与 DMA 排查

- 原厂与 OpenWrt 的接收中断均默认在 CPU0 执行，不能单凭绑核不同解释。
- 原厂 43 秒接收事件时间戳相对等待的最大变化为 1.694 ms。
- 只读采样 OpenWrt Root Port MSI pending 状态，每 2 ms、限时 40 秒，
  没观察到连续几十毫秒的 pending；该采样会影响 idle 驻留，不能据此排除
  未采样时的唤醒问题，更不能把持续采样作为修复。
- 对比原厂与 OpenWrt 的 SC2355 EDMA 状态寄存器，关联客户端后 RX 地址
  通道的信号量均接近 100。未关联时的低值不是已证实的接收缓冲泄漏。
- 以上寄存器读取未写 BAR、未重映射固件内存、未修改 DMA 或中断状态。
- 短时将 MSI 父中断从 CPU0 路由到 CPU1，探针确认回调实际在 CPU1
  执行，恢复后回到 CPU0；手机 RTT 三个约 20 包窗口平均约
  39.4 / 48.6 / 45.1 ms，无稳定改善。临时模块包含 45 秒自动恢复，
  实际已正常卸载并恢复，未加入发行模块。该实验的固件时间戳相对基线
  还呈明显漂移，进一步说明它不能直接替代手机 RTT。

## 手机实际 RTT 的进一步交叉验证

为减少手机自身省电的干扰，在整个 A/B/A 窗口内临时关闭手机 Wi-Fi
power_save，结束由手机端 trap 恢复为原 on。热点保留全部原始设置，
只在中间 22 秒窗口短时改变 CPU0 idle 选择。以下按热点实际收到的
ICMP 标识和序号匹配手机 ping，排除了其他 ICMP 流量，没有拿固件
timestamp 差值代替 RTT。

| 实验 | 原状态 A，22 包 | 中间状态，22 包 | 恢复原状态 B，21 包 |
| --- | --- | --- | --- |
| CPU0 仅保留 WFI | 平均 12.758 / 最大 53.5 ms | 平均 7.318 / 最大 12.0 ms | 平均 43.347 / 最大 126.0 ms |
| CPU0 仅暂时避开 cluster-pd，保留 core-sleep-lit | 平均 27.376 / 最大 64.2 ms | 平均 7.434 / 最大 9.75 ms | 平均 14.104 / 最大 30.1 ms |

这给出了继续优化的具体方向：无需照搬原厂连 WFI 都禁用的做法，
保留核心浅休眠的对照亦能显著减少此轮长尾。但两次普通窗口本身也有
明显波动，手机 power_save 关闭是实验条件，尚不能承诺所有客户端、
所有固件与手机默认省电开启时都达到 10 ms 内。也没有测量该策略的
续航代价，不能把“保留浅休眠”写成“与原策略功耗完全相同”。

两个实验结束后 CPU0 state1/state2 的 disable 均恢复 0，手机恢复
power_save on，未把临时设置写入开机脚本或持久配置。

## 修复边界

前述诊断结束时没有永久改变 idle 设置，亦未证明网络全路径延迟已经解决。
随后用户明确要求将原厂 lowlatency 策略用于 MU300 全部机型，现已按该要求
加入公共启动流程：`mu300-lowlatency` 仅将 CPU0 各 cpuidle 状态的 disable
写成 1，CPU1–CPU7 原样保留；没有按板型限制，不增加轮询、等待或新服务。
缺少 cpuidle 节点的内核直接跳过。

OpenWrt 由 `mu300-hw` 调用，systemd 根由 `mu300-fixups.service` 调用；
两类根文件系统构建入口均明确设置该公共脚本的可执行权限。TF、userdata
镜像和内置独立分区使用同一根文件系统策略，正常更新并重启后同样生效。
此为用户选择的原厂低延迟策略，不能承诺功耗与原先允许深度 idle 时完全
相同；续航仍需实际测量，不能据一次短 ping 宣称所有机型均硬件验证成功。

新增实现已在 dash、bash、BusyBox ash 下完成 9 次实际执行检查：CPU0
所有状态置 1、其他 CPU 保持原值、重复执行不改变结果、无节点正常跳过；
相关启动及构建脚本语法检查和 `git diff --check` 通过。

连接的 U30 Air 已热部署公共脚本及 OpenWrt 启动调用，文件 SHA-256 回读
一致，脚本连续执行两次后 CPU0 各状态均为 1，CPU1–CPU7 与执行前逐项
一致。备份位于 `/root/hotfix-backups/20261019-lowlatency`，未重启或重开
无线/蜂窝。热点仍为 5180 MHz / 80 MHz，WAN up=true、pending=false。
手机维持默认 Wi-Fi power_save on、协商 SAE，20 个普通一秒间隔 ping
全部应答，最小/平均/最大为 **17.911 / 33.841 / 45.797 ms**。
这是单机短测，不是续航或全部机型的验证；开机调用尚未通过重启实测。

本机此前确认的 RX-push 游标判空缺陷仍保留修复，和本次 idle 策略发现
分开记录；不能把两个问题混作同一个已完成的延迟修复。

诊断原始数据位于忽略目录
`work/u30air-wifi-latency-20261019/`，不进入固件或安装包。
本轮未修改 NV、AT 顺序或基带初始化；其他机型仅公共源码同步，未实机部署。
