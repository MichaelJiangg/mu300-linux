# U30 Air OTA 后回退 Android 与系统切换核对（2026-10-21）

## 实机证据

- 设备：U30 Air / U30Air / ums9620，Android 实际运行 A，OpenWrt 运行 B。
- OpenWrt 内核：7.2.8，#51，2026-10-19；故障持久日志及 pstore 均确认
  `rootfs-unavailable` → `tf-root-unavailable (returning to Android; eMMC root probe skipped)`。
  约 13 秒主动恢复 Android，并非本轮已证实的内核崩溃或 ext4 损坏。
- 内置 `/dev/mmcblk0p76` 的 ext4 魔数与卷标 `mu300root` 正常。
  通过只读远程块读取和 ext4 解析器检查元数据，未挂载或修改 Android userdata。
- 根系统版本为 `mu300-r20261021.101839-gb8d4f222-sc0c0b6fb`，OTA journal 状态 complete。
- 安装中的 boot B 带 OTA recovery v2 钩子及 `etc/mu300-root-target=sd`，
  却不含 `etc/mu300-desktop-root-mode`。公共 OTA Binder 只保留槽位角色，
  漏掉存储选择，是这次内置系统被当作 TF-only 启动的已确认缺陷。

## 修复

两个仓库共用的 `boot.py` 保留 MU300 的 root-target、desktop-root-mode、
desktop-identity。原先不存在的字段以空覆盖保留其原有缺省行为，避免
旧版 generic 内置启动继承新发布镜像的 TF-only 限制。不保留安装／卸载任务请求。
E5 原有槽位、命令行与诊断尾部保护保持原逻辑。

实机保留原内核、init、诊断尾部，只在 boot B 追加已核验的 `part` 存储选择。
写入前后完整 SHA-256 一致性核验通过；未写 Android boot A、GPT、userdata 或 NV。
经已校验 misc 一次启动恢复 OpenWrt，根分区与 WAN IPv4/IPv6 恢复正常。
仅当原 journal 的 boot-after 签名精确匹配修复前镜像时，将其更新为修复后签名，
保留原始 boot 备份和全部撤销冲突检查，不使用强制撤销绕过校验。

## 临时启动提示与插件

实机保存的 `/etc/mu300/default-boot` 为 linux，启动提示返回 temporary=false
与现有策略一致。从 Android 点一次启动不应抹掉此前明确保存的默认 OpenWrt。
此处不是已确认的提示漏显，未修改永久默认选择或强制弹提示。

JS 切换插件另有已确认的过度拦截：当前 Android 槽位来自 getprop，misc 是
下次启动意图；另一槽优先级更高不等于当前运行槽变了。v6 允许在验证目标
OpenWrt 镜像后重新选择已被预选的 OpenWrt。仍检查 CRC、Android 健康位、
待安装／卸载镜像、槽位变化、并发锁、写前快照及回读；仅写 misc 的 32 字节。
尚无证据证明当前版本 getprop 在这台机器上返回了错误的运行槽。

## 验证与交付边界

- 两仓库分别通过 11 项 OTA 全流程／启动绑定测试及 15 项插件测试。
- MU300 额外通过 2 项真实 init 存储选择模拟测试。
- 真实 7.2.8 与 6.18.54 发布 boot 镜像离线绑定到实机修复镜像，均保留
  part、现有命令行及诊断区域。这不是 6.18 实机刷入验证。
- Windows/macOS 安装器的未编译 boot.py 数据完成受校验刷新；两份 Windows
  Diff Studio 已在原目录刷新，没有重编无变化的 GUI 或复制新运行环境目录。
- 已生成的旧差异包包含自己的旧运行环境，必须用新工具重新生成。
  现有完整发布 ZIP 没有重打；用户自己创建的 7z 分发归档未修改。
