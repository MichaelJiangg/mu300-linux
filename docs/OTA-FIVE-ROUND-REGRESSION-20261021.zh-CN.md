# OTA 五轮验证记录（2026-10-21）

范围：E5、MU300 两仓库共用的差异生成、电脑更新器、设备 OTA 引擎与 LuCI 系统补丁页。
结论：下列 OTA 测试在修复后通过；这不是所有机型、任意第三方插件及真实断电条件下“绝对零缺陷”的证明。

## 五轮结果

| 轮次 | 实际执行 | 结果 |
| --- | --- | --- |
| 1：功能与基线回归 | Windows 完整安装器测试：E5 295 项（43 项跳过）、MU300 289 项（45 项跳过）；Linux OTA 两仓库各 81 项、无跳过。 | 通过。Windows 的平台相关跳过项不算已验证，Linux OTA 独立运行覆盖设备文件系统逻辑。 |
| 2：异常与探查 | 在真实 LuCI 视图源码上注入开始失败、响应丢失但设备仍在更新、回滚失败、连续状态查询失败及恢复；桌面测试旧事务重复查询。 | 先复现缺陷，再修复并通过。验证写入中保持禁用、确认空闲后恢复按钮、同一掉线不反复弹通知。 |
| 3：界面与完整迁移 | 浏览器测试亮暗主题、三种窗口尺寸、长错误与文件列表独立滚动、中英文、自动/手动重启、失败状态、回滚、慢请求、换设备、无效补丁。另从真实 MU300 两版发行 ZIP 重新生成补丁，在 QEMU ARM64 临时根目录执行首次引导、后台更新和回滚。 | 通过。693 项变更、202 条安装包记录；旧根没有 Python/OTA 也能引导。用户插件、数据、Wi-Fi 配置、本机固件、Android 槽均保留。假 boot 是普通文件，不是真实分区断电试验。 |
| 4：成品冒烟 | 两仓库重新编译 Windows GUI/后端；各自以冻结后端读取真实 E5 ext4 发布包、生成组合包并检查去重。两套 Diff Studio 及其导出的更新器分别运行 30 秒后关闭。Apple Silicon 原生构建、后端 smoke 及导入指纹校验。 | 通过。组合包中一份 update.ota，不额外嵌入 boot/rootfs 副本。Mac 只确认原生构建及后端 smoke，没有本地 Mac 人工点击验证。 |
| 5：实机与最终扩散回归 | 当前 192.168.77.1 设备：认证后连续 10 次 HTTP status、未登录访问 4 个方法被拒绝、未知参数被拒绝、刷新与取消回滚；最新冻结更新器连续两次查询并检查激活状态。修复后重新执行 Linux 两仓库各 81 项、Windows 完整测试及浏览器/视图测试。 | 通过。事务始终保持 complete；本轮不重新刷入已经完成的更新，不执行实机回滚或重复重启。当前真实补丁页没有 RPC 错误和 JS 异常。 |

## 本轮实际修复

1. LuCI 开始更新请求失败或响应丢失后，原先可能永远禁用导入。现在重新读取设备事务；确认仍运行就继续等待，确认空闲才恢复。回滚也采用相同处理并在请求期间阻止重复操作。
2. 旧补丁已完成、插件已重载时，电脑端第二次查询原先丢失 activation.ready。现在复用已验证结果，避免状态前后不一致或反复重载。
3. 手动查询失败事务原先可能显示“设备状态已读取”的成功提示。现在显示真实失败原因。
4. 电脑端每两秒发起一次查询，遇到慢 SSH 可能重叠并排队。现在等待前一次返回或失败后，再延时发起下一次。
5. 回滚完成后原先没有电脑端直接重启按钮。现在与更新完成一样可直接重启。
6. 更换设备地址、凭据或补丁时清除旧的重启入口；无效补丁不再保留上一份补丁的版本信息。

以上生产代码及测试已同步两仓库。增加 `installer/tests/ota_luci.js`，扩展 `test_ota_desktop.py` 和 `ota_browser.py`。

## 产物与证据

- 两仓库最新 Windows 工具：`out/tools/OpenWrt-Diff-Studio-verified/`。
- MU300 本次生成的更新器：`out/tools/OpenWrt-Updater-verified/`，旁有完整 ZIP。当前连接设备已经完成升级，**仅检查状态即可，不要再次应用同一目标版本**。
- 两仓库 `installer/artifacts/windows`、`installer/artifacts/macos-arm64` 与当前生产源码指纹一致。未借此次测试重新编译内核或组装所有机型完整包。
- Windows 构建日志：E5 仓库 `out/build-logs/20261020-225603-ota-five-windows-30180/`。
- Mac 导入日志：E5 仓库 `out/build-logs/20261020-230152-ota-five-macos-import-47385/`；各仓库 `out/build-state/macos-ota-five-import.json`。
- 实机网页检查：E5 仓库 `out/build-state/ota-five-live.json`、`out/diagnostics/ota-five-live.png`。诊断 HTML 的会话标识已脱敏。
- 真实发行包 ARM64 验证脚本：`installer/tests/ota_release_migration.py`；新生成的测试补丁位于 E5 `out/diagnostics/ota-five-migration.ota`。

## 单独记录的现存问题与边界

未登录的主题登录页会产生一次 `"%s/%s.js%s".format is not a function` 控制台告警；它发生在登录页初始化，不是认证后的系统补丁视图。测试分离记录了登录页、系统补丁页和状态概览，后两者没有该异常，登录和 OTA 页面操作正常。本轮没有修改登录主题；不能将这条现存告警隐去后宣称整个固件无缺陷。

没有实测每种机型的更新中掉电、真实闪存损坏或所有第三方二进制插件的 ABI 兼容性；这些不属于自动回归通过的承诺。本轮实机只访问 192.168.77.1，不改 NV、AT 顺序、射频、充电或网络配置。

## 复查命令

```text
python -m unittest discover -s installer/tests -p test_*.py
python3 -m unittest discover -s installer/tests -p 'test_ota*.py'  # Linux，安装 ota-requirements.txt
node installer/tests/ota_luci.js
python installer/tests/ota_browser.py                         # 本地前端服务运行时
python installer/tests/ota_frozen_smoke.py <tool-directory> --e5-release <E5-full.zip> --native
python3 installer/tests/ota_release_migration.py --patch <update.ota> --old <MU300-old.zip> --bootstrap-probe
```
