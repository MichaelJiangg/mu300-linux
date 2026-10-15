# MU300 / F50 / V50 / U30Air：OpenWrt 使用指南

**电脑安装和维护从根目录的 `OpenWrt-Installer.exe` 或 `OpenWrt-Installer.py` 开始。**
不用寻找或手动运行子目录内的安装脚本。保留整个解压目录，不要只复制 EXE／PY。

## 1. 打开主安装器

Windows：双击 **`OpenWrt-Installer.exe`**。不需要另装 Python。

也可以在解压目录打开 PowerShell：

```powershell
.\OpenWrt-Installer.exe
```

Linux、macOS 或使用源码入口：

```sh
python3 OpenWrt-Installer.py
```

PY 入口需要 Python 3.10+ 和 `paramiko`、`lz4`：

```sh
python3 -m pip install paramiko lz4
```

首次安装、续装、切回 OpenWrt 均从已 root 的 Android 连接 ADB。
启用 USB 调试、授权电脑，并允许 Shell 使用 root。安装 Android platform-tools，
把 `adb` 加入 PATH；若包内含 `tools/adb.exe`，Windows 安装器也可直接使用。
只连接一台待操作设备，或用 `--serial SERIAL` 明确选择。

### 主菜单怎么选

| 菜单 | 用途 | 数据变化 |
| --- | --- | --- |
| 1 — TF card | 首次安装到 TF 卡 | 清空第一分区；没有分区时清空整卡 |
| 2 — Userdata image【实验性】 | 在未加密 userdata 内创建镜像文件 | 占用所选容量，旧镜像保留为备份；可能损坏 Android F2FS |
| 3 — Independent internal partition | 安装到独立内置分区，通常推荐 | 优先使用未分配空间；不足才考虑缩容，必要时清空 Android |
| 4 — Reinstall internal system | 重装已有内置 OpenWrt | 清空原 OpenWrt 分区和配置，不重复缩容 userdata |
| 5 — Resume after Android reset | 加密 data 缩容、重置 Android 后续装 | 写入已准备的分区，不重新执行缩容 |
| 6 — Update OpenWrt | 保留配置更新正在运行的 OpenWrt | 替换系统和内核，完成后重启 |
| 7 — Boot OpenWrt once | Android 临时启动已安装的 OpenWrt | 仅修改 misc；成功后手动重启，不改默认启动设置 |

**菜单 2 是实验性功能：userdata 镜像模式可能破坏 Android 的 F2FS 文件系统。**
一般选 TF 卡或独立内置分区。它只接受确认未加密、未经过加密映射的 userdata。
EXPERIMENTAL: userdata-image installation may damage Android's F2FS filesystem.

菜单号码以本 MU300 包为准，与 E5 仓库的安装器不同。

## 2. 安装前准备

1. 使用对应设备和内核系列的完整包，安装前自行备份重要数据。
2. 确认设备已解锁、root 可用，Android A／B 槽会由安装器识别，Linux 写入另一槽。
3. 保持稳定供电，不要同时运行多个安装器、Android OTA 或其他分区工具。
4. 热点密码在输入时明文显示；名称和密码留空可尝试导入 Android 配置。
5. 固件、运行库由安装器按目标设备提取，不要替换成其他机器的文件。
6. 电脑的网络、网卡和防火墙不会由安装器擅自调整。

只验证包文件、不连接机器：

```powershell
.\OpenWrt-Installer.exe --check
```

```sh
python3 OpenWrt-Installer.py --check
```

## 3. TF 卡安装：菜单 1

插好可清空的 TF 卡，启动根目录安装器，选 **1**。按提示设置热点与 APN，
核对目标分区并确认。先完成校验、提取本机固件和释放 TF 挂载，再格式化、安装。

优先使用 `/dev/block/mmcblk1p1`，没有分区才用整卡。不重新划分 TF 分区，
使用所选目标的全部容量，不保留额外 OTA 空间。看到成功状态后手动重启。

## 4. 内置分区安装：菜单 3

启动根目录安装器，选 **3**，输入需要的 OpenWrt 分区大小，例如 8 GiB。
分区大小与文件系统容量会一致：**默认使用所选分区的全部空间**，
安装时使用的初始 2 GiB 镜像不是最终容量。

### 有足够的未分配空间

安装器检查物理容量和 GPT，优先使用连续、对齐且没有已知旧系统占用的空闲区域。
这条路径不缩小或格式化 userdata，包括已加密的 Android data。
所选空闲区域的原始内容会被覆盖；完成后按最终提示手动重启。

### 需要缩容，且保留 Android 数据

未加密 userdata 才可选择保数据缩容。安装器在 Android 中准备并校验载荷，
再重启到 initramfs，离线检查、缩容、建分区并写入 OpenWrt。

**第一次开机正在执行缩容安装，通常需要数分钟，数据多或闪存慢时会更久。**
它不同于平时开机；保持供电，不要因暂时没有桌面或百分比而强制重启。
**缩容安装完成后会自动重启一次，再进入 OpenWrt。**

离线阶段可通过 `http://192.168.77.1:8089/progress.txt` 查看进度；
U30Air 为 `http://192.168.77.1:8089/progress.txt`。需电脑 USB 网卡启用且可访问设备。
看不到进度页不代表可以中断安装，应以安装器输出和设备实际阶段为准。

### 加密 userdata，或主动选择格式化

**会清除 Android 用户数据并恢复出厂。** 第一阶段只携带准备工具和设备绑定计划，
重启后离线调整分区，随后重启进入原厂 recovery 清空 data，再回 Android。
这一阶段通常也要数分钟；原厂恢复出厂可能另外重启，请保持供电并等待。

回到 Android 后完成初始设置，重新启用 USB 调试、授权电脑，恢复 root 并允许 Shell。
重新打开根目录 EXE／PY，选 **5**，使用原来的 `transaction.json` 续装。
不要再次选 3 重做第一次缩容。

续装记录和备份默认位于电脑的 `~/mu300-backups/日期-标识/`，不是手机 data，
请保留整个备份目录及相邻 `package-manifest.json`。可以明确指定记录：

```powershell
.\OpenWrt-Installer.exe --resume --transaction "C:\Users\你的用户名\mu300-backups\日期-标识\transaction.json"
```

```sh
python3 OpenWrt-Installer.py --resume --transaction "/path/to/transaction.json"
```

记录丢失时先保留设备现状，从电脑备份恢复原记录；当前续装入口需要该文件，
不会凭设备上的分区名自动猜测安装计划。不要手工编造 token 或恢复别台机器的 GPT。
续装会核对机器、槽位、容量和关键载荷；换了系统载荷不能直接续装。

## 5. 更新、重装和切换系统

- **更新（6）**：设备运行 OpenWrt，通过 USB 网络连接电脑。输入实际 root 密码，
  电脑经 SSH 上传、验证并更新系统，保留配置和原容量，完成后重启。
  重要文件仍需事先备份；旧的无分区表原始偏移安装不适用此桌面更新入口。
- **重装（4）**：设备运行 Android，仅覆盖已有 `mu300root` 和 Linux 启动镜像。
  原 OpenWrt 配置会清除，Android userdata 不重新缩容。
- **切回 OpenWrt（7）**：设备运行 Android，检查另一槽的 Linux 启动镜像后选择它，
  仅修改并回读 misc 的 32 字节启动控制块，成功后按提示手动重启。
  不挂载／修复 OpenWrt 分区，不改根选择文件、默认启动设置，不自动同步启动链。
  启动后沿用原有默认启动策略；永久默认启动需在 OpenWrt 中另行设置。
- **回 Android**：在网页系统切换入口选择 Android，再按提示重启。

管理地址通常是 `http://192.168.77.1`，U30Air 为 `http://192.168.77.1`。
热点名称／密码以安装输出为准，登录后设置自己的管理密码。更新需填写当前实际密码。
包提供容器所需的内核支持，没有预装 Docker，用户可按需安装。

## 6. 执行结束怎么看

安装器最后显示 **成功、失败、已取消、校验通过或仍需下一步**，以及耗时和下一步操作。
“仍需下一步”表示可能正在离线安装或等待恢复 Android 后续装，不表示已经进入 OpenWrt。
交互窗口会等待回车退出；退出前保存输出、热点密码和备份路径。

安装器报错时不要反复选择首次安装，不要跳过校验直接刷分区。
保留完整输出、包版本、电脑备份和续装记录，核对是否连错机器或需要恢复 USB／root 授权。

## 7. 文件与 Magisk 入口

```text
OpenWrt-Installer.exe    Windows 主安装器（若包含）
OpenWrt-Installer.py     跨平台主安装器
START-HERE.md           本指南
module.prop/customize.sh Magisk 模块入口，请勿手动运行
payload/                唯一一份系统镜像、启动镜像和原 Magisk 部署文件
desktop/                安装器内部代码、校验清单和离线工具
launchers/              可选快捷入口；通常直接用根目录主安装器
tools/                  可选 ADB
docs/                   补充技术说明
```

也可在 Android 的 Magisk 中直接安装完整 ZIP，沿用原有 TF 部署流程，
无需运行电脑 EXE／PY。它会清空所选 TF 目标并部署系统；不要为了日常切换系统反复安装此完整 ZIP。
文件名保持英文，整个目录需要一起保留。更换 EXE／PY 后不能忽略清单或源码指纹不匹配。
