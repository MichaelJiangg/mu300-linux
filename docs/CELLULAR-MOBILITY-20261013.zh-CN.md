# MU300 蜂窝移动续租修复

本次只修改仓库代码、完成离线验证，没有部署或测试 MU300 实机。

## 发现的问题

MU300 已有 CGEV 驱动的原地 IP/DNS 更新，架构与 E5/T551M 的 ModemManager
不同；没有相同的 15 秒注册丢失保护，因此没有移植 45 秒超时修改。

但 OpenWrt 的纯 IPv4 分支没有启动该监视器。现有 30 秒看门狗发现基带
IP 与网口 IP 不同时，也直接进入重拨路径；查询失败还可能被当成上下文
失活或射频关闭。这些是相近的实现缺口，不代表已实测 MU300 有相同的
户外掉线表现。

## 修复

- IPv4 和双栈都启动一个 netifd 管理的事件监视器。
- 补齐 ACT、DETACH、SPPCODATA 触发；合并事件突发，冷却期间的新提示
  保留到下一轮。校时回退不会产生长时间等待。
- 移动换 IP、DNS 或内核丢失地址时先增加新地址，更新路由和 netifd 快照，
  最后删除旧地址。失败保留旧快照，后续可以重试。
- CGACT 明确失活时先等待三轮、每轮两秒，再交回 netifd 恢复；AT 失败、
  空值或无法识别的返回保留现有连接，不相信旧 CGCONTRDP 地址。
- 看门狗发现仍激活的上下文地址不一致时调用 WAN renew，避免重拨。
  查询失败不增加掉线计数；CFUN 必须明确返回 0 才重新开启射频。
- 校验 IPv4、连续掩码和 DNS，兼容零 DNS、带引号及双行 IPv4/IPv6 返回。
- 保留 external 报告方式、SLAAC/RA 有限生命周期、双卡寻址、原有 30 秒
  看门狗周期及显式关机/切卡门控，没有新增定期 AT 轮询。

## 验证

新增 `tests/test_cellular_mobility.py`，覆盖原地更新顺序、更新失败后重试、
AT 失败隔离、明确失活、缺失内核地址、两张 SIM、IPv4/双栈启动监视器、
事件合并、IPv6 生命周期、看门狗 renew/重连及明确射频关闭修复。

```sh
PYTHONPATH=tests python3 -m unittest test_cellular_mobility test_registration_scope \
  test_static.Rules.test_tf_bundle_keeps_usb_and_cellular_handoffs
```

20 项通过，新续租行为在 dash、bash、BusyBox ash 下均执行。
再用 dash/bash 执行相邻 IPv6 前缀撤回、路由修复回归，共 35 项通过。
现有 IPv6 测试在本机 BusyBox 下会由内置 ip 绕过 PATH 中的测试桩；新增
测试使用显式函数桩隔离这一差异，没有把这些环境性失败当作设备故障。

真实 URC 上报、跨基站/跨 RAT、运营商地址变化和恢复耗时仍待实机验证。
