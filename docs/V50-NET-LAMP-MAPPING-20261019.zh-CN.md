# V50 NET1／NET2 对应修正（2026-10-19）

用户观察：同一张卡在 Android 亮 NET2，而在 OpenWrt 亮 NET1。

## 已确认原因

现有物理 LED 引脚组经过此前点灯确认，不需要交换驱动中的 NET1/NET2 名称。
问题在 `v50-led-status.network()`：之前把逻辑卡槽 0/1 直接用于
`net$((slot+1))`，错误地假定 SIM1 对应 NET1、SIM2 对应 NET2。

核对已有本机原厂 V50 B15 固件：

- 版本 `V50_V1.0.0B15`，Android 指纹
  `ZTE/MU3351/MU3351:13/TP1A.220624.014/20250527.235207:user/release-keys`。
- `system/framework/services.jar` SHA-256：
  `b305826bb767f3753e9a8a4d7d98ab8c0944da8ae37b9e3de8e750fd91fd44d9`。
- 直接分析 `classes2.dex` 中
  `NotificationManagerService.setNetLight()` 及其构造函数，不依据相似机型推测。

构造函数的 NET1 颜色编码前缀为 `0x01000000`，NET2 为 `0x02000000`。
`setNetLight()` 读取物理选择 `zte_webserver_sim_slot_id`，分支对应为：

| 原厂物理卡 ID | 卡 | 逻辑槽位 | 原厂目标灯 |
| --- | --- | --- | --- |
| 0 | 内置卡 1 | SIM1 / SPACTCARD=0 | NET2 |
| 1 | 内置卡 2 | SIM2 / SPACTCARD=1 | NET1 |
| 2 | 内置卡 3 | SIM2 / SPACTCARD=1 | NET1 |
| 3 | 外置卡 | SIM1 / SPACTCARD=0 | NET2 |

Dalvik 方法内关键位置：物理卡 0 的 `0x0288` 起设置 NET2 并清除 NET1；
物理卡 2 的 `0x02e6` 起设置 NET1 并清除 NET2；物理卡 1 的
`0x033c` 起设置 NET1 并清除 NET2；外置卡分支 `0x0358` 起
清除 NET1 并设置 NET2。颜色条件另由原厂 `sim_network_rules` 决定，本次
不把这一条件混作物理灯位，也不根据运营商猜测用户改装卡槽的接线。

原始分析及反汇编位于忽略目录 `work/v50-card-topology/stock-led-policy.asm`；
没有展开新的完整系统镜像或建立额外的 WSL 构建副本。

## 修正范围

- V50 用户态灯控改为 SIM1→NET2、SIM2→NET1；所有注册事件、缺卡、数据
  状态、启动、设置刷新与温度告警仍通过同一个 `network()` 入口执行。
- `signal`／`signal_brightness` 继续控制物理 NET1，`signal2` 对应物理 NET2。
  不交换用户已保存的亮度和开关；网页的中／英／土 SIM 标注同步纠正。
- 状态缓存继续按逻辑卡槽保存，不交换卡槽、上网接口、物理选卡 GPIO 或 AT
  指令，不增加 AT 查询、轮询或服务。Wi-Fi 灯与其他型号没有修改。
- 保留此前双卡分别显示注册状态和 LTE 蓝／NR 白的行为；这里只纠正灯位，
  不宣称完整重现原厂选中卡的所有颜色／熄灭策略。

V50 假 sysfs 回归已按原厂对应更新，验证两卡独立、亮度、关闭灯、Wi-Fi
独立、缺卡、短注册事件和温度告警。尚未对本次改动做 V50 实机点灯验证，
未热部署、未编译打包、未提交。
