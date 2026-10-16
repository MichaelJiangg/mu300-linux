# MU300 双用途安装包移植记录（2026-10-13）

## 范围

把 E5 桌面部署方案迁入 MU300 仓库。ZIP 既可以直接交给 Magisk
执行原 TF 部署，也可以解压后运行英文命名的 Windows/Unix 入口。
MU300 的 `/openwrt` 容器布局、A/B 启动控制和原生更新机制均保留。
没有移植屏幕程序、E5/T551M/M8 驱动或它们的启动镜像。

原 Magisk 的部署脚本、安装 worker、启动链同步、内核、TF init
和原始校验文件内容保留。新版混合包将原部署文件移入 `payload/`，
顶层 `customize.sh` 设置对应 MODPATH 后执行原脚本，再恢复 MODPATH；
仅改变文件位置，部署步骤不变。
`MU300_DESKTOP_INSTALLER=0` 仍然可以生成原来的纯 Magisk 包。
桌面 TF 自定义项使用上传到手机的私有脚本副本，不改原包成员。

## 入口

| 文件名（Windows `.cmd`，Unix `.sh`） | 功能 |
| --- | --- |
| start-installer | 选择部署方式 |
| install-to-tf-card | TF 安装，复用原 worker 的释放挂载、格式化、校验及写 boot 顺序 |
| install-to-userdata-image | 未加密 userdata 内创建指定大小的 ext4 镜像，保留已有镜像备份 |
| install-to-internal-storage | 离线缩小 userdata，建立 `mu300root` 独立分区 |
| reinstall-internal-system | 重装已有独立 OpenWrt 分区 |
| resume-internal-install | Android 格式化完成后的第二阶段续装 |
| switch-to-openwrt | 选择已安装的 Linux 启动槽，完成后手动重启 |
| update-openwrt | 电脑发起 SSH 上传，保配置和容量更新，成功后重启 |

Windows 有 EXE 时直接运行，否则使用 Python。可随包加入 adb.exe
及两个 DLL；Linux/macOS 使用 Python 和系统 adb。多个 Android 在线时
必须显式给 `--serial`，设备模型只接受 MU300/F50/U30Air。
`--check` 检查包；`--check-boot` 在电脑上构造启动镜像，不访问设备。

## userdata 安装

未加密的 F2FS/ext4 默认保数据，也可以明确选择格式化。
先检查完整载荷、GPT 两份表及分配计划，再离线检查和缩小文件系统；
文件系统缩小成功后才更改 GPT。完整写入镜像、回读验证，再离线扩容
到整个分区并核对超级块容量，避免用户选了 10 GiB 却只有 2 GiB。
失败停在安装环境保留日志，不用自动重启掩盖错误。

FBE/FDE 必须走格式化两阶段：

1. 电脑保存 boot、misc、两份完整 GPT 和两槽 BSP 五分区备份，建立
   CID/序列号/槽位/几何位置绑定的续装记录。
2. 桌面启动镜像的 ramdisk 携带工具和准备请求；不从加密 `/data`
   读取安装载荷。建立独立分区后，请原厂 recovery 格式化缩小的 userdata。
3. 用户完成新 Android 设置、重新启用 USB 调试并恢复/授权 su，运行续装入口。
4. 核对设备、Android 槽、userdata 和 root 几何位置，以及独立分区里的
   准备 token。再从当前 Android 提取固件/运行库，构建、写入、校验
   并扩容独立系统，最后写另一个 boot 槽并选择 Linux。

续装记录和备份默认在电脑 `~/mu300-backups`。userdata 内镜像法明确
拒绝加密数据；不尝试在 initramfs 解密 Android 数据。
GPT 备份按真实表项数量计算长度，支持超过 128 项的表，不固定只备份 34 扇区。

## 启动及进度

桌面启动镜像在原 MU300 boot 后追加 LZ4/CPIO 段，内核和
`loglevel=5` 启动标记不变；目标模式、准备请求和维护工具放在 ramdisk，
不依赖可能被 `CONFIG_CMDLINE_FORCE` 忽略的额外启动参数。
A/B 控制块从目标机现场 32 字节生成，保留 OEM 字节、重新计算 CRC。
镜像必须在 48 MiB 持久日志区之前结束。

离线步骤每两秒显示真实阶段和耗时；复制时显示实际字节进度。
该次 initramfs 同时提供只读进度：F50/MU300 的
`http://192.168.77.1:8089/progress.txt`，U30Air 的 `192.168.78.1`。
失败状态立即更新，进系统后没有常驻进度轮询服务。

## 更新

电脑经认证 SSH 上传，不要求设备反向访问 Windows HTTP 服务，
避免入站防火墙造成的 `Operation not permitted`。
用原生 `mu300-update` 的同一互斥锁、配置/账号/用户软件包迁移和
目录切换逻辑；新系统检查成功才更换 boot 并选择 Linux。
保留 `openwrt.old`，失败时尝试恢复旧 root、boot 和 misc。

包内只携带一份 `mu300-openwrt.tar.gz`，不再打入第二份 `desktop/files/rootfs.tar.gz`。
桌面内置安装和 SSH 更新在电脑临时生成公共 tar，上传成功或失败后均清理临时文件；
原 Magisk／TF 流程继续直接使用原包。公共 tar 排除构建机的 Android 运行库和专有固件；这些文件从
已安装系统迁移。使用非递归 bind 视图避开活动的 vendor `/dev`、`/proc`
等挂载，避免复制实时设备节点。boot 更新保留 48 MiB 的持久日志区域，
单独更新 AVB footer。成功清理上传目录前必须卸载 bind 视图。
传统原始 eMMC 空闲区域布局由原生 updater 继续处理，桌面更新不猜布局。

## 验证

- 新桌面回归 13 项：FBE 判断、尺寸、GPT 备份范围、A/B CRC/OEM 字节、
  错设备续装拒绝、字符串转义、固件来源隔离、boot 重打包和真实原生更新事务。
- 原 TF 回归 19 项；启动链回归 32 项（dash/bash/sh）；原更新和锁回归 17 项；
  用户软件包回归 34 项。合计 115 项通过。
- 宿主 BusyBox 的独立 applet 查找会绕过启动链测试的假 `dd`，导致该组
  故障注入断言失败；没有为让测试通过而改动原启动链。其他列出的测试正常通过。
- 6.18 和 7.2 双用途 ZIP 的 CRC、文件 SHA256 和原 Magisk 18 个成员逐项核对通过。
- 两套包实际运行 Python 和冻结 EXE 的 `--check-boot`；从含空格目录运行
  CMD 入口通过。全程无设备写入。

预览包在 `work/desktop-preview/*-20261013-r2.zip`，详细哈希在同目录
`VALIDATION.json`。它们使用已有的 `20261012-2afe136` 运行时包，
不是最新固件全量重编结果。新构建脚本已接上双用途组装。
**MU300 实机缩容、原厂 recovery 重置/续装、完整部署后的重启和更新仍待验证。**

### 2026-10-14：共用一份 rootfs

最新预览包为 `work/desktop-preview/*-20261014-single-rootfs.zip`，
SHA256 和核验结果见同目录 `SINGLE-ROOTFS-VALIDATION.json`。
每包仅含一份 `mu300-openwrt.tar.gz`；原来的 18 个 Magisk 成员逐项校验保持一致。

| 内核系列 | 去重前 | 去重后 | 减少 |
| --- | ---: | ---: | ---: |
| 6.18 | 165.85 MiB | 103.05 MiB | 62.80 MiB |
| 7.2 | 166.47 MiB | 103.61 MiB | 62.86 MiB |

Windows、WSL 分别通过 17 项桌面测试，覆盖 TF 原包复用、内置安装临时过滤、
上传失败清理、更新保留本机固件，以及包内不产生第二份 tar。
两套包的 Python 和冻结 EXE 都通过 `--check-boot`、`--check-rootfs`，
实际临时过滤约 9–10 秒，过程中显示进度，整个检查没有设备写入。
这些仍为历史运行时的安装器预览包，不是重新编译的完整新固件。

### 2026-10-14：Android loop 与续装修复

续装修复包在 `work/desktop-preview/*-20261014-resume-fix.zip`，
报告为同目录 `RESUME-FIX-VALIDATION.json`。仍只携带一份 rootfs，
原 18 个 Magisk 文件保持一致；两套包均通过 Python/EXE 的 boot 和 rootfs 检查。
Windows/WSL 各通过 21 项测试，新增 Android loop 路径解析、可见 Wi-Fi 密码、
ADB reboot 调用以及空错误诊断覆盖。

V50 上已验证实际镜像挂载、完整临时镜像构建和只读复验，现有 8 GiB 分区可继续续装。
第一阶段完成后遇到此问题不需重新缩容。用户当前旧包已做代码修补和经核验的
本地续装绑定更新，旧文件及记录已备份；不要直接换另一份包绕过原记录校验。

### 2026-10-14：修复版续装兼容和精简目录

新包为 `work/desktop-preview/*-20261014-clean-layout.zip`，核验结果见
`CLEAN-LAYOUT-VALIDATION.json`。顶层只保留四个文件：
`OpenWrt-Installer.exe`、`OpenWrt-Installer.py`、`module.prop`、`customize.sh`。
部署载荷放在 `payload/`，快捷入口在 `launchers/`，说明在 `docs/`，
桌面程序资产与 ADB 分别在 `desktop/`、`tools/`。
18 个原部署文件逐项核验内容不变，Magisk 薄入口的 MODPATH 切换/恢复已通过测试。

续装不再要求整个安装器清单逐字节相同，而是比较独立的关键载荷身份：
原 boot、rootfs、关键文件校验表、容量要求、BusyBox、所有文件系统工具及内核系列。
路径搬迁、EXE、输入提示或说明的更改不会改变该身份；系统/内核/工具变化会拒绝。
设备、槽位、分区起点/容量和设备上的准备令牌检查保持原样。

旧记录必须先找回其绑定哈希完全一致的清单，才能推导关键载荷身份，
不能只因同为 7.2 或同机型就放行。当前 V50 原目录已删除，
已利用保留的原清单与修补版文件哈希重建那份清单，验证 SHA256 完全等于
旧记录绑定值，并保存为备份目录中的 `package-manifest.json`。
新版 EXE 对旧记录进行只读续装预检，通过 8.00 GiB 分区、身份、令牌及载荷校验。
没有再次缩容或写独立分区。

新记录同时保存关键载荷身份、源目录及 `package-manifest.json`，
无需长期保留解压目录；记录及备份全部遗失时仍需人工核对恢复，当前没有自动恢复入口。
兼容检查现在先于 rootfs 准备/上传，失败不再白等压缩和传输。
FBE 第一阶段只上传准备工具，不再上传暂时不使用的完整 rootfs。

Windows、WSL 各通过 23 项测试；两套新包通过清单、顶层目录、
Python/EXE boot 构建、实际临时 rootfs 生成及含空格路径的 CMD 入口检查。

### 2026-10-14：优先使用 eMMC 未分配空间

此前新独立分区路径直接按 userdata 大小计算缩容，未查看它后面的 GPT 空闲区。
V50 实机读取显示约 58.25 GiB 总容量；现有 userdata 与 8 GiB OpenWrt 之后
仍有约 32.39 GiB 未分配空间，原安装不必为这 8 GiB 重置 Android。

新流程先校验两份 GPT 的头/表 CRC、边界、分区重叠及可用表项，测量连续对齐空闲区。
能放下所选容量时，使用有 offset/size limit 的原生 Android loop 写系统，
扩容并校验文件、文件系统后再提交 GPT，回读两份副本，最后写 boot 和切槽。
不会在 Android 使用 userdata 时执行整盘重读分区表；新节点在重启后出现。
检测到已知原始偏移的旧 ext4/F2FS 系统会排除相应空闲区。

该路径适用于 FBE/FDE，保持 userdata 大小及数据不变。
只在无足够连续空间时才进入原缩容/重置流程。TF/Magisk 路径保持不变。
已有 `mu300root` 仍要求重装/更新；未知或冲突 GPT 不静默修正。
安装中再次比对原始 GPT 快照，有变化即停止，boot 尚未修改。

新增 GPT/FBE/失败阻断 5 项测试，以及 opt-in Linux root 稀疏文件测试 3 项：
真实 ext4 写入/扩容/校验、错文件不提交 GPT、GPT 中途变化不写空闲区。
后者只作用于临时虚拟磁盘，不访问用户硬盘。27 项既有桌面测试也通过。
新路径目前只有实机只读探测及虚拟磁盘执行验证；没有在现有 V50 再建分区。
历史补充 ZIP 未重打；新版源文件、EXE 需在下次组装时一并纳入校验清单。

## 来源及维护

四个 E5 来源文件的输入 SHA256 记在 `desktop/PORT-SOURCES.json`。
移植后的脚本改用 MU300 名称、容器路径、动态槽位和原生启动确认。
维护工具只要求通用 ARM64 musl 文件，通过 `MU300_DESKTOP_TOOLS` 输入；
代码不依赖 E5 仓库路径。Windows EXE 检查源文件指纹，编译中源码变化
或打包时 EXE 过期都会拒绝。

主要实现：`desktop/installer.py`、`boot_image.py`、`boot/`、
`android-image.sh`、`android-write-part.sh`、`android-write-free.sh`、`local-update.sh`。
组装：`desktop/package.py`、`tools/add-desktop-installer.py`。
验证：`tools/verify-desktop-installer.py`、`tests/test_desktop_installer.py`。
