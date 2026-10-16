# OpenWrt Installer

## 中文

完整解压安装包，双击根目录的 **OpenWrt-Installer.exe**。保留全部子目录，不要只复制 EXE。Windows 无需另装 Python、Node 或 Rust；如果提示缺少 WebView2，请按提示安装后重新打开。

安装前备份重要文件，确认安装包适用于你的机型，并保持设备稳定供电。在 Android 中开启 USB 调试，允许这台电脑调试，并准备好 Magisk/root。

只有无线 ADB 时，先将电脑连接到设备所在网络，展开设备选择区的“无线 ADB 连接”，填写 `192.168.0.1` 并点击“连接”。地址或端口不同请填写实际值，例如 `192.168.0.1:5555`。设备需已开启无线 ADB；Android 要求配对时，先按设备提示完成配对。

也可手动运行 `adb connect 192.168.0.1`。Windows 可在安装包目录打开 PowerShell，运行 `.\tools\adb.exe connect 192.168.0.1`。

Linux、macOS 或需要命令行操作时，可使用 **OpenWrt-Installer.py**，需另行安装 Python 和依赖。使用 Magisk 安装时，直接选择完整 ZIP；这会部署到 TF 卡并清空选定目标，请先备份卡内数据。

### 选择用途

- **安装 OpenWrt**：首次安装到 TF 卡或独立内置分区。校验安装包，选择设备并检查，然后核对安装计划。
- **更新 OpenWrt**：保留已有设置和容量更新系统。设备需运行 OpenWrt，电脑需连接它的网络，并提供管理地址和 SSH root 密码。
- **继续未完成的安装**：选择原安装记录，接着完成中断的安装或 Android 重置后的续装。
- **临时启动已安装的 OpenWrt**：从 Android 切换到已安装的 OpenWrt，仅本次启动生效，不会设为默认系统。完成后按提示重启。
- **高级选项**：重装已有内置分区，或使用 userdata 镜像。重装会替换原 OpenWrt 系统和设置，保留 Android。**userdata 镜像是实验性功能，可能损坏 Android F2FS 文件系统**，建议优先选择 TF 卡或独立内置分区。

连接多台设备时，请核对型号和序列号末四位，明确选择本次要操作的设备。

### TF 卡

插入已备份、可以清空的 TF 卡。安装计划会显示目标分区和容量，请确认后再开始。

优先安装到卡的第一分区；没有分区时使用整卡。所选目标会被格式化，其他分区保留。不重新划分 TF 卡，没有 32 GiB 容量上限。

若提示 TF 卡无法释放挂载，请停止使用卡内文件的 Android 应用，再重试；不要跳过提示强行格式化。

### 独立内置分区

选择需要分给 OpenWrt 的容量。安装器优先使用已有未分配空间；不足时才需要缩小 Android 用户数据分区。最终计划会列出 Android 保留空间、OpenWrt 分配空间，以及是否会清空数据。

**“使用全部已分配的 OpenWrt 分区容量”建议保持开启**：例如分配 10 GiB，安装完成后便使用这 10 GiB，不会额外占用 Android 的剩余空间。

首次启动会进行离线分区准备，可能需要数分钟，完成后设备会自动重启一次。数据较多时可能更久，请保持供电，不要因暂时没有画面而强制重启。

已有内置 OpenWrt、只想重新安装时，在高级选项中选择“重装已有内置分区”，无需插入 TF 卡。

### 加密 userdata：重置后自动续装

如果加密的 Android 用户数据分区必须缩容，**Android 应用、账号、照片和内部存储会全部清空**。请先自行备份个人数据，并仔细核对安装计划中的重置提示。

1. 保持安装器运行及设备供电，等待分区准备和恢复出厂完成。设备可能重启多次。
2. 进入 Android 后，完成初始设置。
3. 开启开发者选项和 USB 调试，在设备上允许这台电脑调试。
4. 打开 Magisk 检查 root。只有 root 丢失时才需安装或恢复 Magisk；出现 root 授权请求时请允许。
5. 安装器检测到原设备且 root 可用后，会继续安装。

完成初始设置和授权没有固定时限。等待中请按页面指引操作，不要重新创建首次安装任务。若已关闭安装器，重新打开后选择“继续未完成的安装”。

未加密的用户数据分区可以保留数据进行离线缩容；是否需要清空，以最终安装计划为准。

### 更新与自动重启

将电脑连接到目标 OpenWrt 的 USB 网络或热点，选择“更新 OpenWrt”，填写当前管理地址和 SSH root 密码。重要配置和文件仍建议提前备份。

更新提交后设备会自动重启，期间网络暂时断开。保持供电，等待安装器重新连接并校验。**不要因为重启期间连接不上而重新执行更新。**

若设备已经开机却一直等待，请核对电脑连接的设备网络、管理地址和密码，然后点击“我已进入 OpenWrt，开始校验”。地址或密码改过时，填写实际值。

### 暂停、关闭与失败恢复

需要退出时，点击“在安全边界暂停”，等待页面显示已暂停后再关闭。正在进行的写入需要先完成；设备已开始离线准备时，即使电脑上的任务已暂停，也请继续为设备供电。

重新打开安装器，选择“继续未完成的安装”，使用原记录继续。不要因断线或报错重新发起首次分区安装。安装包可以整体移动或重命名；换用修复版时，若提示不兼容，请保留原包和记录，按提示处理。

安装记录和备份自动保存在电脑上。点击“打开事务目录”查看，或用“导出事务与备份”保存完整 ZIP。**这些备份不能替代安装前对照片等个人文件的备份。** 换电脑续装时，先解压导出的 ZIP，再用“导入恢复目录”选择包含 `transaction.json` 的完整目录。请妥善保管备份，不要公开上传。

出错时展开“详细日志”，点击“复制诊断信息给开发者”，并说明机型、安装方式和出错前的操作。日志也可以导出。若提示需要从备份恢复，请保留设备现状和完整备份，联系开发者协助。

文件传输显示 100% 后，可能仍需提取固件、安装或校验，请以当前阶段说明为准。检查、格式化和扩容期间没有百分比时，请保持供电并等待。

需要手动重启时，页面会提示“请现在手动重启设备”；已在重启或已进入 OpenWrt 时，不必重复重启。进入 OpenWrt 后，将电脑连接到目标设备的 USB 网络或热点，核对管理地址和 SSH root 密码，再点击“我已进入 OpenWrt，开始校验”。连接了多台 OpenWrt 时，注意默认地址冲突，确认电脑访问的是目标设备。

看到完成页面后，按显示的管理地址访问设备，检查服务并修改管理员与无线密码。E5/M8/T551M 默认地址为 `http://192.168.9.1`，MU300/F50/V50/U30Air 为 `http://192.168.77.1`；修改过地址时使用实际值。保留安装记录和备份，以便后续恢复。

**全新安装的管理页面和 SSH 登录用户名为 `root`，默认密码为 `root`。** 登录后请修改密码。更新会保留原密码；之前改过密码的设备，请使用当前密码。

### 连接与常见问题

#### 第一次使用，从哪里开始？

完整解压后打开根目录 EXE，先看新手引导，再按用途选择操作。首页可以重看引导；右上角“帮助与使用指南”或 F1 可打开本指南。

#### 没有发现设备，或者同时连接了多台设备？

确认 USB 线支持数据传输，Android 已开启 USB 调试，然后点击“刷新设备”。仍无设备时，尝试更换线缆或 USB 口，并在 Windows 设备管理器中检查 USB 驱动。多台设备会显示在设备列表中，请核对型号和序列号末四位后选择。

只有无线 ADB 时，展开“无线 ADB 连接”，填写地址并连接。未授权时请在设备上允许调试；离线时检查设备调试状态后刷新。多台设备连接时，列表会显示无线设备的地址，请选准目标。

要断开某台无线设备，先在列表中选择它，再点击“断开所选无线设备”。USB 设备不能用此按钮断开；任务执行中需要先暂停。重置 Android 后等待重连时，也可在当前页面重新连接原设备的无线 ADB。

#### 显示“等待调试授权”或“离线”？

解锁 Android，允许“USB 调试”请求。没有弹窗时，确认 USB 调试已开启，再重新插拔数据线并刷新。设备正在重启时先等待开机；已有安装任务时保留原记录。

#### 已经安装 Magisk，为什么还在等待 root？

打开 Magisk，确认 root 环境正常，并允许 Shell 的 root 请求。只有 Magisk 应用、没有可用 root 时，需要恢复 root 环境；重置后也可能需要重新授权。

#### 安装记录丢失了怎么办？

先检查原电脑上的事务目录，以及是否导出过完整备份。**电脑记录和导出备份都丢失时，当前版本无法仅凭设备自动重建续装记录。** 请保留设备现状，联系开发者，不要新建分区任务代替原记录。已经安装好的 OpenWrt，日常更新或临时启动不需要上一次安装的记录。

#### 什么时候会清空数据？

TF 安装清空选定卡分区；重装替换已有 OpenWrt 及其设置；加密 userdata 必须缩容时会清空 Android。请以最终安装计划为准，确认备份后再开始。

## English

Extract the complete package and run **OpenWrt-Installer.exe** at its root. Keep all adjacent folders. Windows users do not need to install Python, Node or Rust. If prompted to install WebView2, follow the instructions and reopen the installer.

Back up important files, check that the package matches your model and keep the device powered. Enable USB debugging in Android, authorize this computer and have Magisk/root ready.

For wireless ADB only, connect the computer to the device’s network, expand Wireless ADB connection, enter `192.168.0.1` and select Connect. Use the actual address and port if different, for example `192.168.0.1:5555`. Wireless ADB must already be enabled. If Android requires pairing, complete it on the device first.

Alternatively, manually run `adb connect 192.168.0.1`. On Windows, open PowerShell in the package folder and run `.\tools\adb.exe connect 192.168.0.1`.

For Linux, macOS or command-line use, run **OpenWrt-Installer.py** with Python and its dependencies installed. To install through Magisk, select the complete ZIP. This installs to the TF card and erases the selected target, so back up the card first.

### Choose your purpose

- **Install OpenWrt**: install to a TF card or an independent internal partition. Verify the package, select and inspect the device, then review the plan.
- **Update OpenWrt**: update while keeping settings and capacity. OpenWrt must be running, and the computer must be connected to its network. Enter its management address and SSH root password.
- **Continue an unfinished installation**: select the original record to resume an interrupted installation or continue after an Android reset.
- **Boot installed OpenWrt once**: switch from Android to the installed OpenWrt for one boot, without changing the default system. Restart when prompted.
- **Advanced options**: reinstall an existing internal partition or use a userdata image. Reinstallation replaces OpenWrt and its settings while keeping Android. **Userdata image installation is experimental and may damage Android F2FS.** Prefer a TF card or an independent internal partition.

With multiple devices connected, check the model and last four serial characters and select the intended device.

### Storage and capacity

For TF installation, insert a backed-up card that can be erased. Check the target partition and capacity in the plan. The first partition is used when present; otherwise the whole card is used. The selected target is formatted, other partitions are kept, and the card is not repartitioned. There is no 32 GiB limit. If Android cannot release the card, close apps using it and retry.

For internal installation, choose the capacity to allocate to OpenWrt. Available unallocated space is used first; Android userdata is resized only when needed. The plan shows retained Android space, OpenWrt capacity and whether data will be erased.

Leave **Use all allocated OpenWrt partition capacity** enabled to fill the chosen allocation. For example, allocating 10 GiB gives OpenWrt that 10 GiB without taking additional space from Android.

The first boot performs offline partition preparation. This may take several minutes or longer with more data, then the device restarts automatically. Keep power connected and do not force a restart because the screen is temporarily blank.

To replace an existing internal OpenWrt installation, choose Reinstall internal partition under Advanced options. No TF card is needed.

### Encrypted userdata and reset

If encrypted Android userdata must be resized, **all Android apps, accounts, photos and internal storage will be erased**. Back up personal files first and review the reset warning in the installation plan.

1. Keep the installer running and the device powered while partition preparation and factory reset finish. The device may restart more than once.
2. Complete Android initial setup.
3. Enable developer options and USB debugging, then authorize this computer.
4. Check root in Magisk. Restore or install Magisk only if root is unavailable, and allow any root request.
5. Installation continues when the original device reconnects with working root.

Setup and authorization have no fixed deadline. Follow the waiting instructions and do not create a new first-install task. If you closed the installer, reopen it and choose Continue an unfinished installation.

Unencrypted userdata can be resized while preserving data. The final plan states whether a reset is needed.

### Updates and automatic restart

Connect the computer to the intended OpenWrt device’s USB network or hotspot. Choose Update OpenWrt and enter its current management address and SSH root password. Back up important configuration and files first.

After submission, the device restarts automatically and the network disconnects briefly. Keep it powered and wait for reconnection and verification. **Do not start another update because the device is unreachable during restart.**

If the device has started but the installer keeps waiting, check the connected network, address and password, then select OpenWrt is running — verify now. Use the actual address and password if they have changed.

### Recovery and results

To exit, select Pause at a safe boundary and wait until the task is paused before closing. An active write must finish first. Keep the device powered if offline preparation has already started, even while the computer task is paused.

Reopen the installer, choose Continue an unfinished installation and select the original record. Do not start partitioning again after a disconnect or error. You can move or rename the complete package folder. If a repair release is rejected as incompatible, keep the original package and record and follow the message.

Records and backups are saved automatically on the computer. Use Open transaction folder to find them or Export transaction and backups to save a complete ZIP. **These backups do not replace a personal backup of photos and other files.** To resume on another computer, extract the exported ZIP and import the complete directory containing `transaction.json`. Keep backups private.

On failure, expand Detailed logs and choose Copy diagnostics for the developer. Include the model, installation method and what you did before the error. You can also export the log. If backup recovery is required, preserve the device and full backup and contact the developer.

A file reaching 100% may still be followed by firmware preparation, installation or verification. Follow the current phase. Keep the device powered while checking, formatting or resizing, even when no percentage is shown.

When asked to restart manually, use the device’s normal restart control. Do not restart again if it is already restarting or running OpenWrt. Connect the computer to the intended device’s USB network or hotspot, check the management address and SSH root password, then select OpenWrt is running — verify now. With several routers connected, check for conflicting default addresses and make sure you are reaching the intended device.

After completion, open the management address shown, check services and change administrator and wireless passwords. Default addresses are `http://192.168.9.1` for E5/M8/T551M and `http://192.168.77.1` for MU300/F50/V50/U30Air. Use the actual address if changed. Keep the installation record and backups for recovery.

**A fresh installation uses username `root` and default password `root` for the management page and SSH.** Change the password after signing in. Updates preserve the existing password; use the current password if it has been changed.

### Connection and troubleshooting

#### Where should a beginner start?

Extract the complete package and open the root EXE. Read Getting started, then choose your purpose. Replay the introduction from the home page, or open this manual with Help and user guide or F1.

#### No devices, or several devices connected?

Use a data-capable USB cable, enable Android USB debugging and select Refresh devices. If the list stays empty, try another cable or USB port and check the USB driver in Windows Device Manager. With multiple devices, check the model and last four serial characters before selecting one.

For wireless ADB only, expand Wireless ADB connection, enter the address and connect. Allow debugging on the device if it is unauthorized; check debugging and refresh if offline. When several devices are connected, use the addresses shown in the list to select the intended wireless device.

To disconnect one wireless device, select it in the list and choose Disconnect selected wireless device. This button cannot disconnect USB devices. Pause an active task first. While waiting for Android after a reset, the current page also lets you reconnect the original device’s wireless ADB.

#### Awaiting debugging authorization, or offline?

Unlock Android and allow the USB debugging request. If no prompt appears, confirm debugging is enabled, reconnect the cable and refresh. Wait for startup if the device is restarting. Keep the original record for an installation already in progress.

#### Magisk is installed, but root is still pending?

Open Magisk, check that root is working and allow the Shell root request. Having only the Magisk app installed is not enough. Restore root if it is missing; a reset may also require granting permission again.

#### What if my installation record is missing?

Check the original computer’s transaction directory and any exported full backups. **If both computer records and exported backups are lost, this version cannot reconstruct a record from the device alone.** Preserve the device and contact the developer; do not create a new partitioning task instead. Updating or temporarily booting an installed OpenWrt does not require its previous installation record.

#### When is data erased?

TF installation erases the selected card target. Reinstallation replaces existing OpenWrt and its settings. Encrypted userdata that must be resized requires an Android reset. Review the final plan and back up data before confirming.
