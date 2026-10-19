# V50 多版本选卡与 U30 Air 制式灯（2026-10-19）

## 提交基线

按要求先提交两个仓库此前全部工作区更改：

- E5：`fd47cfc1`，T512N 及公共射频、安装、构建修复。
- MU300：`cf4dcd61`，SFUN 射频策略、自动制式选择、Wi-Fi RX 恢复等。

本轮 V50 / U30 修改只在 MU300 仓库实施，没有移入 E5 仓库。

## 原厂证据

离线来源：已有的 `V50_B15_Oem_Lock_20250726174705.7z`，没有从相似机型猜测选卡指令。
系统版本 `V50_V1.0.0B15`，指纹：
`ZTE/MU3351/MU3351:13/TP1A.220624.014/20250527.235207:user/release-keys`。

| 文件 | SHA-256 |
| --- | --- |
| ZteWebServerPlus.apk | `59e0d22a85bbbf0b302baa318328b2ac256152610c4ccd29b16ea782453f8b0a` |
| uni-telephony-common.jar | `cb54c678b5448f5c3feb2f87f7386f80b609ee40fa39e431d8f03941d8f36847` |
| vendor-telephony-framework.jar | `b5189f6e42a4f8b6d97f0bdffc82074498a572af68e04eff752ac74c6031bef7` |
| sim_gpio_ctl.ko | `88570f6401bdf5a4f01ddd8c59bd5170e8968fd5daeabc65f5e6de916d326513` |
| zte_card_holder_det.ko | `aa7443ab656c933b7d00ce1d1b3b1889d7ee9b6e1b62fb505a46351e65586df9` |

证据文件及逐方法 Dalvik / ARM64 反汇编留在忽略目录
`work/v50-card-topology/`。原厂 super 仅临时展开到 RAM，提取后删除，
没有另建 WSL 内核树、对象树或长期保留另一套系统分区镜像。

`ElfDeviceManager` 的四个常量及 `isSupportEsimCu()`、物理卡支持判断给出：

| board_id | 原厂硬件类型 | 可选物理卡 ID |
| --- | --- | --- |
| 0 | 3 内置卡 | 0、1、2 |
| 1 | 3 内置卡＋1 外置卡 | 0、1、2、3 |
| 2 | 2 内置卡＋1 外置卡 | 0、1、3 |
| 3 | 2 内置卡 | 0、1 |

APK 读取 `/proc/driver/board_id`。现连 V50 的只读检查确认：
`/proc/cmdline` 没有 `androidboot.zte_boardid`，而设备树 `chosen/bootargs`
保留 `androidboot.zte_boardid=3`。新识别顺序为原厂 proc 节点、内核命令行、
设备树原始启动参数；未知值不猜作其他板型。

## 物理卡和逻辑槽位分开

| 物理 ID | 页面名称 | 基带逻辑槽位 | 实际选择器 |
| --- | --- | --- | --- |
| 0 | 内置 SIM 1 | SIM1 / `SPACTCARD=0` | `soft-psim-switch=0` |
| 1 | 内置 SIM 2 | SIM2 / `SPACTCARD=1` | `esim2-esim3-switch=0` |
| 2 | 内置 SIM 3 | SIM2 / `SPACTCARD=1` | `esim2-esim3-switch=1` |
| 3 | 外置 SIM | SIM1 / `SPACTCARD=0` | `soft-psim-switch=1` |

原厂 Web APK 本身只保存选卡 ID 并发广播；真正的切换实现在
`UniSubscriptionInfoUpdater.dealWithThreeSimSwitch/dealWithFourSimSwitch`，
`VendorTelephonyManager.setProtocolStack()` 则给出 AT 顺序：

1. 受影响的逻辑槽位执行 `SFUN=5`，再 `SFUN=3`。
2. 改对应 GPIO，原厂事件延迟 **5 秒**。
3. `SFUN=2` 恢复卡电源，再按射频权限执行 `SFUN=4`。

这不是新增第三、第四套 AT 栈。上网接口仍是 `sipa_eth0` / `sipa_eth8`。
`zte_card_holder_det` 是检测输入，不是选卡开关；`sim_gpio_ctl` 的 GPIO0 也
是输入。新驱动只允许修改两个真实选择输出，不对检测 GPIO 做写操作。

## 实现与隔离

- `zte-v50-sim` 只绑定原厂 `zte,sim_gpio_ctrl`，另核验 V50 的 AW9523B DT 节点。
  输出初始化对齐原厂 `androidboot.simswitch` / `androidboot.psimswitch`；
  未提供参数时使用原厂默认值，所有 GPIO 编号来自本机 DT。
- 新增“蜂窝 → SIM 卡管理”的物理卡选择，按 board_id 生成选项，配齐三语言。
  看板、AT、锁频和射频仍使用两个逻辑槽位；选择外置卡后查看 SIM1，第三张
  内置卡则查看 SIM2，不把物理 ID 2/3 传给 `SPACTCARD`。
- 复用现有 SIM 切换门和 RF 互斥，AT 只经过持有端口的 broker。RF 关闭、
  卡电源关闭、GPIO 切换、早期锁定回放和恢复 RF 按顺序执行。
- 保持其他槽位的射频权限。选择 SIM2 上的物理卡仍通过现有控制器完成用户
  对 SIM2 的显式启用。用户手动关闭的数据连接不会被切卡顺带打开。
- 成功后保存 `v50_card` 和既有逻辑上网卡；重启时在原 RIL 首次握手后、原
  双卡模式及回放流程之前恢复需要变化的物理选择。选择器已正确时不重复
  发送 SFUN，不增加固定等待。5 秒只用于真正发生的多路器切换。
- 卡上电后等待有限次 CPIN 就绪，避免把 ATR 尚未完成当作无卡。保存的外置
  卡不在机器上时，不因此阻止另一逻辑槽位完成启动。
- 失败尝试恢复原物理路由、实际逻辑上网卡及原开机偏好；恢复未完成则明确
  报错并保留未完成标记。没有以互联网是否能通作为选卡成功条件。
- 更换同一逻辑槽位上的物理卡会使其旧服务小区、APN 身份及看板身份缓存
  失效。RAM 代次标记阻止旧采集任务在切卡后重新发布旧身份；不删除用户
  锁定设置、短信或流量历史。

F50、MU300 和 U30 Air 不进入此选卡实现；E5 仓库未改变。

## U30 Air 网络灯

静态确认两个问题：

1. 原实现使用 `CEREG?` **最后一个字段**作为制式，实际上拒绝原因及定时器等
   可选字段可以排在 AcT 后面。
2. U30 原生运行卡槽 `/run/mu300/sim-slot` 可以与“下次开机默认卡”不同，
   LED 事件路径原先只读保存的 `data_sim`，可能查看到另一槽位。

修改为复用拨号器的当前卡槽映射，解析固定 AcT 字段并同时读取 `C5GREG?`：
EPS 仍报告 LTE、NR 已确认注册时，显示 5G。空回复、错误或无法判断的回复
保留原灯色，不直接猜成 4G。复用已有拨号完成、网络事件及 watchdog 的更新
时机，不新增定时器或后台 AT 轮询进程。

没有修改电池呼吸灯、亮度、充电常亮、拔插延迟或自动熄灭逻辑。

## 验证边界

- 两套现有缓存内核（7.2.8、6.18.54）均实际交叉编译通过新驱动对象。
- 离线测试覆盖四个 board_id、不存在的卡、未知板型、其他机型隔离、共享
  基带映射、SFUN 顺序、迟到的 CPIN、失败恢复、数据关闭保持以及旧缓存隔离。
- 155 项相关扩散回归通过；最终 V50 / U30 专项复测 16 项通过（与扩散集
  有重叠，不将两者相加冒充独立测试数），另有 14 项看板语言检查通过。
- 页面测试覆盖四种物理卡列表、物理卡 ID 到查看槽位映射，原 U30 控件测试
  继续运行；三语言检查通过。
- 当前 V50 仅做了身份、DT 与 GPIO 的只读检查。**尚未部署新内核，也未实测
  四种板型的真实选卡或 U30 Air 的灯色变化**。不能把离线通过写成硬件验证。
- 已验证的表来自上述 B15 固件；若未来出现其他 board_id 或不同 GPIO 布局，
  应提取该版本原厂 APK / telephony / driver 后扩展映射，不自动套用相似板型。
