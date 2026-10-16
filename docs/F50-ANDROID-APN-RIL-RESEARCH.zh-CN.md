# F50 Android APN 服务与 RIL 静态逆向报告

日期：2026-10-12。对象：本地 `f50_b09` 原厂 Android 解包；对照当前 `clean-tf-7.2` 分支的 APN 管理实现。

## 1. 结论先行

当前插件的 APN 列表管理可用，但与原厂 Android 相比，拨号配置能力还不完整。建议分批补齐，而不是把 Android 的 RIL 服务搬进 OpenWrt。

1. **“APN 留空”不等于 Android 的“自动 APN”。** 原厂从运营商 APN 数据库选择记录，经过 SIM/运营商匹配后设置 preferred APN；还会按 ICCID 恢复手动选择。我们目前只是向调制解调器提交空 APN，让网络/模组决定默认值。
2. **普通数据拨号的鉴权路径已找到：`AT+CGPCO`。** 不应凭其他品牌的实现直接添加 `CGAUTH`。这份 RIL 的可达拨号分支在 `CGDCONT` 之后、`CGDATA` 之前下发用户名、密码、CID 和鉴权类型。
3. **初始附着 APN 是另一条路径：`AT+SPCGAPNCFG`。** 它包含 APN、本地协议、漫游协议与鉴权，不能和普通 PDP 配置混为一谈，也不能把其首个常量 `1` 直接当成任意业务 CID。
4. **应按 SIM 身份保存选择，不能只保留一个全局 WAN APN。** 原厂“按 ICCID 记忆”的思路可以借鉴，但其 Web 服务存在默认订阅/单卡假设，不能照抄进我们的双卡控制逻辑。
5. **配置提交、AT 接受、PDP 建立、互联网可达必须分开表示。** 原厂部分 RIL 分支本身也忽略 AT 发送结果；不能把 Android 回调成功当作可靠的回读确认范本。

本轮只做静态分析与报告：没有连接实机，没有发 AT，没有切 APN、重启服务、改网络或热部署新行为。现有已暂存的 APN/挂载点代码未改动。

## 2. 样本、方法和证据等级

解包根目录：`D:\随身WiFi\F50相关\F50_B15研究\f50_b09`。

方法：JADX 1.5.5 反编译 Java；pyelftools 读取 ELF 符号、重定位和 `.eh_frame` 函数边界；Capstone/AArch64 objdump 核对指令、参数装载、跳转表及调用顺序。**不是只搜索 AT 字符串后猜用途。**

证据分为：

- **已证实（静态）**：本样本的可读 Java 逻辑，或原生指令及调用链可直接支持。
- **推断/建议**：结合当前 OpenWrt 实现得出的移植设计，尚未实现。
- **待实测**：模组实际接受的命令/字符范围、不同 SIM/运营商效果，以及运行时采用的 Android 数据库内容。

JADX 对部分复杂方法未完整还原，包括 Provider 的 `initDatabase()` 等；生成的 `UnsupportedOperationException("Method not decompiled...")` 是反编译占位，**不是 Android 原程序真的会抛该异常**。这些方法没有被当作已闭合证据。

### 2.1 样本 SHA-256

下列路径相对于解包根目录；地址均为相应 ELF 的虚拟地址，不是 ASLR 后的运行地址。

| 样本 | SHA-256 |
| --- | --- |
| `system_a/system/priv-app/ZteWebServer/ZteWebServer.apk` | `738419dd8254804b0b21ea129f9eadcf6819f800cfb1fe25834cc0b2d6c6e4c1` |
| `system_a/system/priv-app/TelephonyProvider/TelephonyProvider.apk` | `bed4ef63f3fde40cfc37d0f604c80c05c43a0f735cee45504005391b017aa78f` |
| `system_a/system/framework/telephony-common.jar` | `fa83ad3e143620af01b0ef8888299a816b61d2271b004e6ab7a93894156c3be4` |
| `vendor_a/lib64/librilcore.so` | `cb68b650d52e1a2bc4f645c0db6ecf077c0044d36233d03bc1b80c9f0cf8c050` |
| `vendor_a/lib64/libimpl-ril.so` | `a0e8e71fa1f4afda302f7471abd419f9f861256ebe7a63a4421c00cdb0c8b3ec` |
| `system_a/system/etc/apns-conf.xml` | `8b4e40028675e37e7d80ddcf95158ac0b2439ea805491fd9f3628cd023668f37` |
| `product_a/etc/apns-conf.xml` | `70930b91100e0d515a58670baf630c02bfbc29accfb73dcb72f80813c9fca9a3` |

### 2.2 本地证据索引

以下反编译/反汇编产物位于忽略跟踪的 `work/`，不把完整厂商代码放进 Git：

- `work/msisdn-static/zte-web/sources/com/zte/web/module/apn/`：`ApnModule.java`、`ApnHandler.java`、`ApnAutoConfigJobService.java`、`SimCardApnRecordsContract.java`、`SimCardApnRecordsDBHelper.java`。
- 同一 `zte-web/sources/` 下 `com/zte/web/module/network/SimStateChangedReceiver.java`。
- `work/msisdn-static/telephony/sources/com/android/internal/telephony/`：`RIL.java`、`RILUtils.java`、`RadioDataProxy.java`、`data/DataProfileManager.java`、`dataconnection/DcTracker.java`。
- 本轮重新反编译的 `work/apn-android-research/ApnHandler.java`，与之前缓存版本比对一致。
- 本轮生成的 `work/apn-android-research/provider/sources/com/android/providers/telephony/TelephonyProvider.java`。
- `work/apn-android-research/{native,core}/disassembly.txt`、`string-refs.txt`、`function-ranges.txt`，分别对应 libimpl-ril / librilcore。
- 本轮 ELF 辅助脚本：`work/apn-ril-static.py`。自动字符串注释仅用于导航；关键分支另核对指令，不能把线性寄存器追踪当作完整反编译器。

## 3. 原厂调用链

```text
ZteWebServer 的 APN 页面请求
  → ApnModule（save / delete / set_default / auto）
  → ApnHandler
  → TelephonyProvider 的 carriers / preferapn / sim_apn_list
  → Android 电话框架的数据配置/拨号管理
  → RIL.java → RadioDataProxy → Radio HAL
  → librilcore.so（AIDL 参数转原生结构）
  → libimpl-ril.so（processDataRequest）
  → AT 通道 → 基带

SIM 状态事件
  → SimStateChangedReceiver → ApnAutoConfigJobService
  → 按 ICCID 查历史选择 → 恢复 preferred APN
```

`vendor_a/etc/init/unisoc.rild.rc:1` 定义 `vendor.ril-daemon /vendor/bin/hw/urild`。本样本的 librilcore 含 AIDL `RadioData::setInitialAttachApn`、`setupDataCall` 等具体实现，Java `RadioDataProxy` 同时保留 AIDL/HIDL 分支。没有 Android 运行日志，因此不宣称每次启动必然走哪一个框架兼容分支。

**对 OpenWrt 的含义：** 数据库选择机制和 AT 参数映射值得移植，Android 的电话服务、Binder、RIL 进程不应因此一起启动；否则会和现有 AT 管理器争用通道、混淆拨号所有权。

## 4. Web 服务：APN 不只是一个名称

### 4.1 保存和应用是不同操作

证据：`ApnModule.java:35–86`；`ApnHandler.java:79–160,282–341`。

- `save`：插入/更新 `Telephony.Carriers.CONTENT_URI`。
- `set_default`：把记录 ID 写入 `carriers/preferapn`。
- `auto`：先挑选自动候选记录，再写 preferred APN，不是写一个空字符串。
- `delete`：按记录 ID 删除。
- 用户编辑项包括名称、APN、PDP 协议、用户名、密码、鉴权；原厂同时接受 `ipv6_*` 形式的兼容字段。
- 保存时附上 SIM 的 MCC、MNC、numeric，类型设为 `default,supl`。

原厂字段名中出现 `ppp_username`、`ppp_passwd`，**不代表本机数据路径使用 PPP**；native 拨号可见的是 `M-ETHER`。

### 4.2 鉴权枚举

`ApnHandler.saveApn()` 将 none/pap/chap 转为 0/1/2，其他输入落到 -1；因此不能仅凭 Web 代码里声明了常量 3，就说这个入口完整支持 PAP/CHAP 自动协商。

原厂 `vendor.unisoc.hardware.radio.data.ApnAuthTypeExt` 则明确有 0/1/2/3；与 [AOSP Radio 的 ApnAuthType 定义](https://android.googlesource.com/platform/hardware/interfaces/+/340619c703511a09422ac77fe005f4465a835da7/radio/1.0/types.hal) 一致：

| 值 | 含义 |
| --- | --- |
| 0 | 不进行 PAP/CHAP |
| 1 | PAP |
| 2 | CHAP |
| 3 | PAP 或 CHAP，由基带能力决定 |

建议新配置采用显式枚举，不把数据库的“未指定”值 -1 原样当成 AT 鉴权参数。具体归一化策略需要结合用户名是否为空及兼容测试确定。

### 4.3 原厂自动选择的局限

`ApnHandler.getAutoConfigApnId():362` 查询 `SIM_APN_URI`，附加条件为：

```sql
user_visible = 1 AND user_editable = 0
AND type != 'ims' AND type != 'mms'
```

然后取第一条。这依赖 Provider 先筛选运营商；Web 层本身不是一个完整 APN 排序器。

`type != 'ims'` 是完整字符串比较，不能等价理解为严格的 APN 类型集合过滤。移植应明确识别 `default`/`*` 等业务类型，避免把 IMS、MMS、测试或专用承载误当上网 APN。

## 5. 配置来源与自动匹配

### 5.1 两份 XML 不能混为一份

实数统计（XML 记录数，包括非上网 APN）：

| 解包文件 | 总数 | IP | IPV4V6 | IPV6 |
| --- | ---: | ---: | ---: | ---: |
| `system_a/system/etc/apns-conf.xml` | 1583 | 540 | 1037 | 6 |
| `product_a/etc/apns-conf.xml` | 3193 | 355 | 2775 | 63 |

Provider `DatabaseHelper.getApnConfFile():474–477` 的外部配置选择路径是：

```text
/system/etc/apns-conf.xml
  被存在的 /oem/telephony/apns-conf.xml 覆盖
  再被存在的 /data/misc/apns/apns-conf.xml 覆盖
```

**该方法没有直接选择 `/product/etc/apns-conf.xml`。** 完整初始化还有 APK 资源和数据库处理，部分方法反编译不完整；未读取运行中的 Android 数据库，不能断言任一 XML 就等于用户最终使用的所有记录。

`system` 库里实际包含 cmiot、联通不同地域的 `unim2m.*`、测试 APN 等；与 `product` 库的候选并不一致。只按运营商品牌硬编码一个 APN，不能覆盖物联卡/专网。

### 5.2 Provider 不是只看 MCC/MNC

证据：Provider `getSubscriptionMatchingAPNList()`，约 `2034–2149`；`getMvnoTypeIntFromString():2588`。

- 先检查订阅有效性，并按 subId 创建 TelephonyManager。
- 读取 SIM 的 numeric 和 SIM-specific carrier ID。
- 处理 MVNO match 类型/数据，通过 `matchesCurrentSimOperator()` 判断。
- 优先使用匹配的 MVNO 候选，否则使用 MNO 候选；还处理 carrier ID 候选。
- 过滤已删除等状态的数据库记录。

样本含 Telstra/CMI 特例分支，但开关来自 `Feature.getBoolean()`；**仅发现分支不证明 F50 当前启用了该特例**，不应直接迁移品牌特判。

建议 OpenWrt：SIM 身份明确时离线匹配候选；人工选择最高优先级。多条专网候选无法仅凭 numeric 判定时，让用户选择，不靠反复拨号“试遍 APN”。导入厂商整库前应确认分发许可、过滤测试/非上网条目，或维护有明确来源的精简规则库。

## 6. 双卡与持久化

证据：`SimCardApnRecordsDBHelper.java:33`、`SimCardApnRecordsContract.java:157–184,224–235`、`ApnAutoConfigJobService.java`、`SimStateChangedReceiver.java`。

- 原厂单独建 `ApnRecord` 表，以 ICCID 查询历史，存 auto/manual 和 APN 记录 ID。
- 收到 SIM 状态事件后排入后台任务，SIM 状态满足条件才恢复选择。
- 有有效手动历史则恢复相应 ID；没有记录或记录为 auto 则走自动选择。
- 后台任务的调度窗口是 500–1000 ms，这不是 AT 重试/注册超时，不应直接翻译成 OpenWrt 的固定 `sleep`。

**不可直接照抄的部分：** 写历史时使用 `getDefaultSubscriptionId()`；部分 URI 不显式带 subId；状态接收器有“只剩一个槽位”的处理。可借鉴按卡记忆，但不能因此认定这套 Web 服务已满足我们的双卡要求。

建议绑定 ICCID 身份键并明确 slot/data-SIM：

- profile 是可复用模板；每张 SIM 单独保存 auto/manual 和所选 profile ID。
- 插入新卡不自动继承同槽位上一张卡的专网 APN。
- 切上网卡时，先解析该卡配置，再交给同一次拨号事务；不能先按旧 APN 拨上，再后台改 APN。
- 查看另一张 SIM 不改变正在拨号的 APN。
- ICCID 不完整时保留“身份未确认”，不要把短前缀当成可靠身份；展示脱敏，不向普通日志输出完整卡号。

## 7. Native RIL：已闭合的 AT 路径

### 7.1 初始附着 APN

`librilcore.so` 的 `RadioData::setInitialAttachApn()`：`0x64e80–0x650a4`。在 `0x64ec8/0x65030` 写请求号 111 (`0x6f`)；可见复制 APN、protocol、roamingProtocol、auth、user、password 至原生结构。

`libimpl-ril.so` 的 `processDataRequest()`：`0x52ee0–0x53adc`。跳转表解码：请求 111 → `0x52f6c`。关键参数装载位于 `0x52fa0–0x52fdc`，格式串在 `0x15b5b`：

```text
AT+SPCGAPNCFG=1,"<apn>","<protocol>","<roamingProtocol>",0,"<user>","<password>",<auth>
```

APN 为空/空指针时，`0x53824–0x53840` 组装：

```text
AT+SPCGAPNCFG=1,""
```

支持的 APN 类型位会先检查，不满足时打印 `SetInitialAttachAPN RIL_APN_TYPE_DEFAULT or RIL_APN_TYPE_IA error!`。

需要注意：

- 首参数常量 1 的**命令级含义/配置槽**尚无完整厂商规格确认，不把它当作已证实的业务 CID。
- `at_send_command` 的 socket 参数来自当前请求的 SIM/socket 上下文，并不是由上面那个 1 选择 SIM。
- `0x539d0–0x539fc` 发送后没有依据返回值判断成功，直接走成功回调。移植不能继承这种假成功行为。
- 未在这条已核对分支中发现“必须先关闭射频”的命令；也不能反向推断任意在线修改都不会影响驻网。

### 7.2 普通数据拨号与鉴权

`librilcore.so` 的 `RadioData::setupDataCall()` 从 `0x650b0` 开始，请求号 27 (`0x1b`)。libimpl-ril 跳转表将 27 分到 `0x53040`，其中一条普通数据路径经 `0x53714` 调用 `sub_53c00`。

可核对的普通 PDP 配置分支：

```text
sub_53c00
  → sub_5cb40：组装/处理 CGDCONT，检查结果
  → sub_5cde0：先写 CGPCO 鉴权
  → CGDATA="M-ETHER",<cid>，继续检查数据连接结果
```

`sub_5cb40` 的 `0x5cbc8` 引用格式串 `0x12761`：

```text
AT+CGDCONT=<cid>,"<protocol>","<apn>","",0,0,0,0,1
```

`sub_5cde0` 的 `0x5ce24–0x5cea0`，格式串地址 `0x1827d`：

```text
AT+CGPCO=0,"<user>","<password>",<cid>,<auth>
```

参数证据：用户名/密码从配置结构 `+0x20/+0x28` 加载到 x4/x5，auth 从 `+0x18` 加载到 w7，动态 CID 放 w6。随后 `0x5cf44–0x5cf74` 组装并发送 `CGDATA`。这里的前三个零/枚举等含义不能通过其他厂商 AT 手册套用。

该分支发送 `CGPCO` 时没有接收响应结构，也没有立刻检查返回值。我们应做有界响应检查和错误分类，但不应因此添加大段固定等待或循环重启基带。

本轮确认的是上述**可达分支**，不是“所有网络类型只有这一种序列”。样本另有切片、IMS、双 PDP 兼容分支，不能为图省事全盘复制。

### 7.3 IMS 配置不要混进上网 APN

`processDataRequest` 请求 128（setDataProfile）入口在 `0x53108`；其中 IMS 分支在 `0x53870` 打印 `requestSetDataProfile found ims apn!`，随后用 CID **11** 配置 CGDCONT，并写 CGPCO。

这不表示上网 APN 应改用 CID 11。当前 OpenWrt `mobile-data` 的数据 CID 为 1；迁移 APN 管理时必须保留业务分工，避免覆盖 IMS/SMS 使用的上下文。

### 7.4 长度与凭据安全

上述若干 RIL 命令构造点使用 `0x80`（128 字节）输出缓冲区。它证明 Android 这几处实现存在缓冲长度约束，**不证明基带统一只接受 128 字节 AT**。

新实现需要限制完整编码后命令长度、拒绝不支持的引号/换行等注入字符、验证转义规则；不能只各自限制 APN 和密码长度后任由组合超长。APN 密码应使用受限配置文件权限，读取 API 默认掩码/只返回 has-password；日志禁止明文凭据，避免原厂 Web `ContentValues` 调试打印的做法。

## 8. Android 电话框架提供的额外语义

证据：`DataProfileManager.java:152–222,362–406`；`RILUtils.java:1177–1225`；`RadioDataProxy.java:201–255`。

- preferred profile、initial attach profile、所有 data profiles 是不同概念。
- initial attach 按允许的 APN 类型筛选，preferred 影响优先级；没有变化时避免重复设置。
- profile 保留 protocol 和 roamingProtocol，另外有 auth/user/password、APN 类型位图、MTU v4/v6 等字段。
- `RILUtils` 对数据连接结果另外解析地址、DNS、网关、MTU、失败原因和建议重试时间；保存 APN 配置并不能保证这些结果已经有效。

当前框架同时包含旧 DcTracker 与新 DataProfileManager 实现；本轮不把“类存在”写成“本机一定启用新数据栈”。这里只提取两类配置职责与已找到的传参证据。

## 9. 与当前 OpenWrt 实现的差距

对照位置：

- `openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/apn.uc`
- `openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/apn`
- `openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/apn.js`
- `openwrt/overlay/lib/netifd/proto/mu300cell.sh`
- `rootfs/overlay/opt/mu300/bin/mobile-data`，特别是 `configure_pdp_context()` 与 `up_locked()`。

| 项目 | 当前实现 | 建议 |
| --- | --- | --- |
| 列表管理 | 名称/APN/IP 协议，保存与应用分离 | 保留现有交互、主题、多语言 |
| 自动模式 | 空 APN，显示 SIM 默认 | 区分“网络默认（空 APN）”与“自动匹配配置库” |
| 鉴权 | 未向拨号层传递 | 增加 none/PAP/CHAP/PAP-or-CHAP、用户名/密码，映射 CGPCO |
| 初始附着 | 本插件没有 SPCGAPNCFG 集成 | 作为明确能力接入拨号生命周期，先验证在线和开机行为 |
| 分卡选择 | 一个 WAN 配置，跟随当前上网卡 | profile + 按 ICCID 的选择记录，显式 slot |
| 漫游协议 | 未独立设置 | 默认继承主协议，可选单独配置；不要与“允许漫游”混为一项 |
| IPv6-only | 页面拒绝，拨号脚本仍要求 IPv4 | 不能只放开下拉框；先补 IPv6-only 地址/路由/DNS成功条件 |
| 当前状态 | UCI 值匹配表示 current | 区分已选配置、AT 配置成功、PDP 状态及失败原因 |
| 超时与恢复 | 保存后让 netifd 应用 | 后台事务有界执行，保存失败/AT 拒绝/注册失败分开报告 |

`up_locked()` 当前顺序为：radio_on → 选择数据卡 → 等注册 → configure_pdp_context → CGACT → 取地址 → CGDATA。**没有由本 APN 插件设置初始附着参数。** 对要求专用附着 APN 的网络，这可能是兼容性缺口；但需要实测，不能据此断言此前二十多秒空隙就是它导致。

目前“current”表示持久化配置匹配，不是 modem 的实时 APN 回读。页面无需为此持续轮询 AT：后台拨号阶段可发布状态快照/事件，显示时读本地结构化状态即可。

## 10. 建议实施顺序

### 第一批：鉴权与结果语义

1. 扩展 profile、RPC、netifd 和 mobile-data 的参数链，所有层一致支持凭据。
2. 在正确 SIM 的同一次 PDP 配置事务中下发 CGDCONT + CGPCO，再开始业务连接；这是有依赖的数据配置，不能为“异步”把鉴权放到拨号之后。
3. UI 保存仍不拨号；应用动作后台运行，及时返回任务 ID，不占住网页请求等待网络。
4. 应用 none 时处理旧凭据残留，拒绝凭据未成功下发却提示已联网。安全默认值及旧配置迁移需写回归测试。
5. 两个相同 APN/协议但鉴权不同的配置可能合法，现有去重键要同步调整。

### 第二批：按卡选择与自动匹配

1. profile 与 SIM 选择记录分离，保留现有全局配置的兼容迁移规则。
2. 自动匹配以 SIM 归属运营商标识为基础，不拿漫游时 COPS 的访问网替代。
3. 加入已验证的 MVNO 规则；不完整的识别信息不能强行匹配。
4. 切卡与 APN 应用共用互斥机制，捕获任务开始时的卡身份，写入前再次检查；网络注册失败不妨碍用户选择卡/保存配置。

### 第三批：初始附着和漫游配置

1. 调制解调器已就绪、SIM 身份明确后尽早处理，绝不放到 initramfs 阶段。
2. 验证 SPCGAPNCFG 的回读方式、在线更新影响及是否涉及持久化；未确认前不要宣称它是安全无扰动操作。
3. 不靠延长启动等待解决时序问题，不引入无限重试或注册失败就反复 SFUN 重启。
4. 不破坏现有异步 CEUS/CEMODE 数据优先设置和有限重试；它们与 APN 凭据的依赖关系不同。
5. 纯 IPv6、MTU、运营商 DNS作为后续完整链路适配，不只新增表单字段。

插件继续通过平台适配层调用能力；Unisoc/F50 专用 AT 放在后端适配器中，LuCI 不硬编码 CID、AT 通道或 Android 服务。

## 11. 后续验证清单（本轮未执行）

### 2026-10-12 移植进度

已在独立插件与 MU300 平台适配层实现：none/PAP/CHAP/自动鉴权、用户名及写入式密码、按 ICCID 保存手动/自动选择、国内公网运营商小型规则表、可选的初始附着 APN。未知运营商或 IMSI 暂不可读时使用 SIM 默认；专网/物联卡保留手动覆盖。不导入 Android 的 IMS/MMS 数据库，不改 IMS CID 11。

普通拨号接入 CGPCO，初始附着默认关闭；均检查精确 OK，不增加固定启动等待。页面只读 UCI/运行状态，没有周期 AT 查询。构建清单已加入身份读取适配器，6.x/7.x 与其他安装方式使用同一套源文件。

已通过真实 ARM64 ucode/libuci 的 62 项核心断言、三语言浏览器回归和 POSIX 环境全套 427 项测试（6 项跳过）；覆盖凭据脱敏、保留/清除、非法输入、按卡绑定与重启持久化。拨号命令顺序使用隔离 AT 桩验证，不能代替带 PAP/CHAP 鉴权的实际运营商测试。WSL BusyBox 的直接全套运行不能正确使用部分测试桩（如 id），不计为已通过。

实机管理连接恢复后，已通过 `work/deploy-apn-ril.ps1` 热部署到 MU300LINUX-324950664950（Linux 7.2.8），备份为 `/etc/mu300/backup/apn-ril-OalpOb`，本地备份为 `work/apn-ril-before.tgz`。八个部署文件逐项 SHA-256 校验通过，network/wireless/unisoc_modem/unisoc_apn 四份配置内容保持原样；未重启网络、设备或切卡。真实 RPC 返回 connected=true，SIM 身份适配器实际读取成功，认证后的 APN 页面与移动端布局通过浏览器验证。没有操作实际 APN 切换或 PAP/CHAP 运营商鉴权，不能将这些项目视为实测通过。

- 正常公网卡：空 APN、手动 APN、切回空 APN，检查旧 APN/凭据是否残留。
- 有鉴权的测试卡：none/PAP/CHAP/自动、正确与错误密码；应区分模组接受配置和运营商接受鉴权。
- 同 APN 不同账户、边界长度、引号/换行等非法输入；密码不出现在日志/RPC列表/命令错误回显中。
- 开机默认卡、SIM1→SIM2→SIM1、换一张卡、欠费卡；分别检查模板、按卡历史和实际拨号参数。
- APN 任务中途切卡或重复点击；失败可解释、不互相覆盖、不持续空转。
- 漫游协议、初始附着设置前后行为，以及 IPv4/双栈/纯 IPv6 的成功判据。
- 保留上网 CID 与 IMS CID，验证短信/转发无回归；不因 APN 更新重启 USB/Wi-Fi。
- 复测启动时间、AT 消费量和 CPU；无延长固定等待、无页面 AT 洪泛。

只有完成对应卡与网络的实测，才能把“静态可支持”升级成“本环境已支持”。当前网络可用的 SIM 并不能代替 PAP/CHAP 或专网卡验证。

## 12. 复现入口

### 实机 APN 验证补充

2026-10-12 在目标 F50（324950664950 / Linux 7.2.8）使用真实 RPC 执行保存、编辑、密码保留与清除、删除、非法输入拦截和当前配置删除保护。随后实测联通 `3gnet` 的全局 IPv4、按 SIM 绑定的 IPv4/IPv6、联通自动匹配及恢复原 SIM-default 配置；各次拨号约 3.7–5.4 秒后通过上下文回读和出站 ping，双栈场景 IPv4/IPv6 均通。测试备份 `/etc/mu300/backup/apn-live-test.pmBOcb`；network/unisoc_apn/wireless/unisoc_modem 四份配置 SHA-256 与测试前一致，无残留测试 profile/selection。

测试发现并修正两项：热部署后旧 netifd 参数表会忽略新鉴权选项，平台拨号改为读取保存的全局 APN 参数（无绑定时不查询 SIM）；netifd 成功的 ubus 调用可能没有回复体，改按 ubus 错误码判断，避免错误显示“应用失败”。两项均同步仓库并热部署。

仍未验证：真实要求 PAP/CHAP 的运营商账号、初始附着高级开关及漫游网络行为、断电重启后的自动选取。当前公网卡能拨号，不证明这些场景都已通过。代理/IMS 编辑仍不在现有页面的支持范围内。

Windows 使用 pwsh。示例只读取本地样本并输出反编译产物，不操作设备：

```powershell
$fw = 'D:/随身WiFi/F50相关/F50_B15研究/f50_b09'
$jadx = 'work/tools/jadx-1.5.5/lib/jadx-1.5.5-all.jar'
java -cp $jadx jadx.cli.JadxCLI --config none --disable-plugins jadx-ai-mcp `
  --no-res --single-class com.zte.web.module.apn.ApnHandler `
  --single-class-output work/apn-android-research/ApnHandler.java `
  "$fw/system_a/system/priv-app/ZteWebServer/ZteWebServer.apk"
java -cp $jadx jadx.cli.JadxCLI --config none --disable-plugins jadx-ai-mcp `
  --no-res -j 2 -d work/apn-android-research/provider `
  "$fw/system_a/system/priv-app/TelephonyProvider/TelephonyProvider.apk"
```

WSL 的 `aarch64-linux-gnu-objdump -d --start-address=0x52ee0 --stop-address=0x53adc <libimpl-ril.so>` 可核对请求分发；区间 `0x5cb40–0x5d180` 可核对普通 PDP/鉴权顺序；librilcore 的 `0x64e80–0x6541c` 可核对 AIDL 附着/拨号参数传递。

地址仅对上述 SHA-256 的样本有效。换固件后必须重新定位，不能把这些偏移直接当作运行时补丁地址。
