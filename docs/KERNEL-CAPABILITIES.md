# MU300 6.18 / 7.2 内核能力

两套主线内核使用同一个 `upstream/mu300-mainline.config`。
本次对齐 E5 的 eBPF、追踪与可选容器网络能力；**不内置 Docker、containerd、runc，
也不创建容器网络或启动采集任务**。这不是看板插件依赖，安装看板不会启用追踪。

## 能力范围

- KVM：ARM64 硬件虚拟化、vhost-net、vhost-vsock。KVM 内建，可选设备按需加载。
- 容器：cgroup v2、memory/CPU/IO/pids 控制器、namespace、seccomp、OverlayFS、
  veth、bridge/netfilter、IPVS、macvtap/ipvlan/vxlan 等。
- eBPF：syscall、cgroup BPF、JIT、BPF events、stream parser、内核与模块 BTF。
  `CONFIG_BPF_UNPRIV_DEFAULT_OFF=y` 保留非特权 BPF 默认限制。
- 追踪：perf / ARM PMU、kprobe/uprobe events、ftrace、function / function graph、
  dynamic ftrace、syscall tracing 和完整 kallsyms。功能编译进内核，不自动启动会话。
- 可选网络诊断/流控模块：FQ、HTB、TBF、PRIO、NETEM，u32/flower/matchall 分类器，
  BPF/mirred/police/gact/skbedit/ct 动作，IFB、socket diagnostics、IPVTAP、Geneve。
  不替换正在使用的 qdisc，不修改 USB、Wi-Fi、SIPA 或 fw4 的运行配置。

## 构建与防漏

构建镜像增加 `pahole` 以生成 BTF。先重新构建工具镜像：

```sh
docker build -t mu300-mainline-build upstream
```

然后使用现有 `upstream/build.sh` 和 `upstream/build-modules.sh`，分别设置
`KV=6.18.54` 或 `KV=7.2.8`，每个版本使用自己的 `OUTDIR`。
两个版本的模块构建不得并行共享同一个 `/src/mod-build`。

本轮产物单独保存在 `upstream/out-features-6.18`、`upstream/out-features-7.2`，
未覆盖旧的已验证产物。后续 TF / bundle 打包时，使用 `MU300_UPSTREAM_OUT`
明确指定对应目录；单独构建 OpenWrt rootfs 时用 `MU300_MAINLINE_OUT`。
不要把新 Image 与旧目录中的同版本模块混用。

- `build.sh` 验证请求的 Kconfig 是否真正生效；不能静默丢弃不支持的选项。
- `check-container-support.py` 检查实际构建配置、Image/模块清单和必要模块。
  TF 包、内核 bundle、OpenWrt rootfs 都沿用该检查，旧的缺功能内核会被拒绝。
- 内核自带模块用 `INSTALL_MOD_STRIP=1`；vendor 模块也移除 DWARF，保留 `.BTF`。
  构建后逐一检查实际模块的 `.BTF` 段，防止缺少 vmlinux 时跳过生成却继续打包。
  检查管道读完整个 `readelf` 输出，避免 `grep -q` 在 `pipefail` 下造成 SIGPIPE 误报。
- 不向 initramfs 的模块列表加入追踪或容器网络模块。

内核能力不能通过替换网页或脚本热应用。需要用匹配的 Image 和整套模块更新并重启，
不可将新模块单独混入仍运行旧内核的机器，即使 `uname -r` 相同。

## 验证边界

2026-10-11 本地构建验证：

- Linux 6.18.54：Image 28,669,960 字节，82 个模块；Image、模块 BTF 与清单检查通过。
- Linux 7.2.8：Image 30,107,656 字节，84 个模块；Image、模块 BTF 与清单检查通过。
- 使用实际设备输入分别生成本地 TF 启动镜像作容量验证（未写入设备）。
  6.18 / 7.2 有效负载末端分别为 40,614,144 / 42,051,840 字节，
  均未覆盖从 50,331,648 字节开始的持久日志区。
- 全量仓库回归测试 283 项：280 通过、3 跳过。BTF 管道修正后专项 15 项重新通过。
- 首次构建阶段没有构建 rootfs / Magisk ZIP，也没有更新或重启实机。

构建通过只证明编译与产物完整性。实机应在更新内核后另行检查
`/sys/kernel/btf/vmlinux`、JIT 功能、可加载 BPF 程序、可用的 trace events，
并验证 KVM ioctl/虚拟机和实际容器。只看到 `/dev/kvm` 或打开配置项不等于所有负载已测。
默认不需要开 tracer、加载 BPF 程序或安装 Docker 来使用路由器。

## 2026-10-11 实机应用与验收

用户随后授权将 DNS 修复与新内核一起落地。F50 从 7.2.8 `#7` 更新到 `#10`，
通过本地 kernel bundle 更新 Linux 所在的 boot_b 和匹配的 84 个模块；未重装 rootfs。
写入后逐个校验模块 SHA-256，并确认 network、wireless、cpu.json 三份配置未改变。
保留 TF 卡完整 boot_b、旧模块和 boot 元数据备份，也下载了一份到本机。
同版本号不代表模块兼容，回滚时必须恢复旧 boot **以及旧模块目录**。

实机通过：

- eBPF 程序加载、JIT 编译（测试程序产生 56 字节机器码）、test-run 返回值校验。
- KVM API 12、创建 VM/vCPU、ARM vCPU 初始化。没有运行完整客户机 OS。
- `perf_event_open`；独立 net/mount/UTS/IPC/cgroup namespace 的创建与退出。
- 内核 BTF、WLAN/温控模块 BTF、syscall trace events 存在，默认 tracer 为 `nop`。
- `vhost_net`、`act_bpf` 可加载且带 BTF；测试后卸载，不留常驻诊断任务。
- USB 管理、5 GHz/80 MHz 热点、AT `OK`、IPv4/IPv6 HTTPS 均通过；
  持续运行超过五分钟，默认启动仍为 Linux，连续失败计数为 0。

用于这些有限范围验证的程序在 `tests/kernel_capabilities_probe.c`。
Docker/containerd/runc 没有安装；完整虚拟机、Docker 容器及长时间压力测试仍未进行。
日志仍有供应商 SIPC 重复注册 sysfs 调试目录的提示和 GICv2 emulation 不可用提示，
不能把本次基本功能验收理解为所有驱动日志都已消除。

DNS 显示空值的原因是旧 `sed` 只识别单行数组，ubus 实际返回多行 JSON。
看板现在用 `jsonfilter` 读取已有 WAN/WAN6 快照的顶层 `dns-server`，合并去重；
不取 inactive 项，不拿本机 loopback resolver 冒充上游 DNS，不新增 RPC/AT 请求或缓存。
`tests/dashboard_dns_fixture.sh` 已在 OpenWrt 容器和 F50 上通过真实 jsonfilter 验证。

本次 DNS 修复后的完整测试在 WSL 的 `MU300_TEST_SHELLS=dash,bash` 下为
285 项、281 通过、4 跳过。WSL BusyBox 1.30.1 和 Windows 原生运行 Unix 测试的
尝试出现兼容性失败，未将其算作通过；真实 OpenWrt ash/jsonfilter 的 DNS fixture 单独通过。
