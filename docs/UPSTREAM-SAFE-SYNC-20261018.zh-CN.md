# 上游变更筛选与适配（2026-10-18）

## 范围

- E5 上游：[main 5ac9d504](https://github.com/sprd-linux-devs/e5-linux/commit/5ac9d504c984d47c46378c0373a1c49909e66e8d)。该分支发生过强制更新，采用设备/公共组件拆分布局。
- MU300 上游：[main 2c06845c](https://github.com/dikeckaan/mu300-linux/commit/2c06845c11da6e76653558566d3a74f4929e4ed1)。相对上次审查记录的 2c13e7bb，有 141 条非合并提交；先按标题和修改路径筛选，再逐行审查本次采用的补丁。
- 这不是全部历史/全部新代码的安全审计，也没有整分支合并。MU300 继续维护 `clean-tf-7.2`，未改另一工作树的 main，未向任何远端推送。

## 本次补入

| 来源 | 适配结果 |
| --- | --- |
| E5 [720e21c3](https://github.com/sprd-linux-devs/e5-linux/commit/720e21c35254e1739a92869ffae0fa44af1e8761) | 两个 kernel build 入口在输出目录运行 merge_config，避免在源码目录创建临时文件；本地 native 输出目录额外转为绝对路径，兼容用户传相对路径。保留现有共享硬件适配器。 |
| E5 [053bd469](https://github.com/sprd-linux-devs/e5-linux/commit/053bd469) | hostapd 容器使用宿主架构，空缓存先构建 host tools/toolchain。E5 的 BlueZ 同用一个构建卷，原先硬编码 ARM64，故也统一架构。MU300 的同源 hostapd 构建脚本同步。未知架构明确报错。 |
| E5 [5ac9d504](https://github.com/sprd-linux-devs/e5-linux/commit/5ac9d504c984d47c46378c0373a1c49909e66e8d) | E5 bootctl 以打包用户 UID/GID 编译，并提前检查文件归属，避免非 root 打包时 chmod 失败。其他机型的 Python 构建入口本来就在宿主编译，不额外套容器。 |
| MU300 [b5a7bc55](https://github.com/dikeckaan/mu300-linux/commit/b5a7bc55cab8bd62ff14dbba93e11c8120bc6133) / PR #282 | AP 未给 mgmt_tx 信道时使用自身有效信道，拒绝无信道的 off-channel/非 AP/MLO 请求；station 加入/离开事件先校验实际缓冲区长度，按小端解析 IE 长度并检查上界。保留本地 SAE/发送修复。E5 接入公共适配器，E5/T551M/M8 和 upstream 两种构建入口都经现有 wifi-stations 入口调用，幂等、不依赖开启 SAE。 |
| MU300 [be60c552](https://github.com/dikeckaan/mu300-linux/commit/be60c5524d85d6d4fc7f95214403aa6758adfa21) / PR #321 | 两个旧 vendor kernel 构建辅助脚本保留 make 的退出码，不能因 grep/tail 成功而误报构建成功、收集旧模块。仅修脚本错误传播，不开启或编译 5.4 发布版本。现有 mainline build 入口已有 pipefail。 |

以上没有新运行时服务、额外正常启动 AT、SFUN、启动等待、无线参数默认值或充电/电量算法变更。

## 跳过或保留待单独评估

- **已有本地对应实现**：HS400 初始化失败降级（5558eef5）、U30 电量保存（6a084453）、无卡事件、射频禁用/VoLTE/VoNR 回放、U30 灯、AP station 数据、ICCID/APN、独立分区发现及 ext4 检查。不能用上游较早实现覆盖本地后续修复；尤其电量保存不能恢复已纠正的 force-write 行为。
- **E5 布局与内核源码迁移**：68593473、735f169d、72f4ac4a 将本地修复重新落到拆分组件并改变 CI/source baseline。需要整套组件与发布工作流迁移，不能把 gitlink、旧版本号设置和本地模型配置直接混合。没有直接导入或删除本地构建时驱动适配。
- **E5 CI/QEMU/缓存和 macOS 大小写说明**：0d0bfc15、2f34516a 主要面向拆分后的 release 仓库。macOS 平铺 `xt_RATEEST.ko`/`xt_rateest.ko` 的风险值得保留，但文档里“不是构建错误”不能当作忽略模块覆盖的理由。本次没有放宽模块校验。
- **MU300 大型音频/Cockpit 栈**：e893ec58、6e30d08a 等涉及大量新驱动和用户空间，不适合作为简单补丁替换现有 E5 已验证通话路径；没有向无屏设备强制加入新面板/通话栈。
- **MU300 lossless/delta 更新**：用户已取消增量更新功能；不引入另一套增量、硬链接、模块回滚和包恢复实现。0c3cefa5 所修的可选参数函数在本地旧布局更新器中不存在，不凭名称套补丁。
- **MU300 android-run UID 统一（0c63d0a4）**：依赖上游此前的专用用户隔离架构。本地仍由 vendor daemon 自身切 UID，不存在该提交描述的“节点归专用用户、daemon 仍为 1000”组合，不增加未适配的 setpriv 路径。
- **MU300 温控趋势算法（4c47e53e）**：涉及新的采样历史、斜率、释放阈值和降频节奏；不是机械修正。没有当前各板原厂对照证据，按硬件修复原则暂不采用上游新增的数值策略。
- **MU300 SIPA/WCN 降噪（6d2796e6）**：本地有既有错误分类、重试与限频实现；上游同时调整若干错误分支日志和 logd 容量，需独立区分正常频繁日志与真实传输失败，不能整体覆盖本地发送路径或一概压成 debug。
- **MU300 U30 禁用 SAE（29b4c81a）**：用户已明确要求找到可信密钥通道前不改变该功能，本次不改认证策略，也不声称固件密钥来源疑问已解决。
- **MU300 zram、extras、下载镜像/备份、SMS 隐私路径**：是独立功能/架构修改；本次未照搬。SMS stdin/权限加固涉及发送者、编码器和转发目录的联动，不能仅取一部分声称完成。
- **内核升级与默认模块扩充**：保留当前 6.18.54/7.2.8 及模型配置，不预装 Docker、VPN，不增大现有发布包。上游 #299 也吸收了我方部分 Wi-Fi/电量修复，不能再次当成全新补丁叠加。

## 验证与实际限制

- E5：实际执行构建脚本的架构选择/容器参数片段，模拟 x86_64/aarch64/arm64；校验空缓存补建顺序、已有工具不重复构建、带空格源码/输出路径的 merge cwd 和 bootctl 所有者参数。
- E5 原有 hybrid-package 8 项测试通过；相关 shell 语法检查通过。
- 两仓库：抽取实际 station callback 和信道检查编译运行 C 测试，覆盖截断事件、短 leave、过长 IE、合法空 IE、AP/P2P、自身信道缺失、off-channel 和 MLO 拒绝。
- E5：公共适配器在本地实际 E5 内核源码副本上重复应用成功。所有模型现有入口共用 wifi-stations，不新增独立分支实现。
- MU300：改动后的 cfg80211/cmdevt 对象分别按真实 6.18.54 和 7.2.8 内核配置交叉编译通过；只编译对象，未替换现有发布模块/镜像。
- MU300：上游构建错误传播测试 2 项通过，包含真实 shell 下 mock make 失败/成功退出码。
- 本次未热部署、未刷机、未重打包，未做新的 Wi-Fi/低电量实机验证。现有 ZIP 不会因源码修改自动更新。
