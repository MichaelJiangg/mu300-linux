/* On-device smoke test; no daemon, interface attachment, guest boot or mounts.
 * Build: aarch64-linux-gnu-gcc -static -O2 -Wall -Wextra -o probe this-file.c
 * Run as root, preferably under timeout. All resources close on process exit.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/bpf.h>
#include <linux/kvm.h>
#include <linux/perf_event.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static void fail(const char *what) { perror(what); exit(1); }
static int bpf_call(enum bpf_cmd cmd, union bpf_attr *attr)
{
    return syscall(__NR_bpf, cmd, attr, sizeof(*attr));
}

static void check_bpf(void)
{
    struct bpf_insn code[] = {
        { .code = BPF_ALU64 | BPF_MOV | BPF_K, .dst_reg = BPF_REG_0, .imm = 64 },
        { .code = BPF_JMP | BPF_EXIT },
    };
    char log[8192] = {0};
    union bpf_attr attr = {0};
    attr.prog_type = BPF_PROG_TYPE_SOCKET_FILTER;
    attr.insn_cnt = sizeof(code) / sizeof(code[0]);
    attr.insns = (uintptr_t)code;
    attr.license = (uintptr_t)"GPL";
    attr.log_buf = (uintptr_t)log;
    attr.log_size = sizeof(log);
    attr.log_level = 1;
    int fd = bpf_call(BPF_PROG_LOAD, &attr);
    if (fd < 0) { fprintf(stderr, "%s", log); fail("BPF_PROG_LOAD"); }
    struct bpf_prog_info info = {0};
    memset(&attr, 0, sizeof(attr));
    attr.info.bpf_fd = fd;
    attr.info.info_len = sizeof(info);
    attr.info.info = (uintptr_t)&info;
    if (bpf_call(BPF_OBJ_GET_INFO_BY_FD, &attr) < 0) fail("BPF prog info");
    if (!info.jited_prog_len) { fprintf(stderr, "BPF program was not JIT compiled\n"); exit(1); }
    unsigned char packet[64] = {0};
    packet[12] = 8; packet[14] = 0x45; packet[17] = 50;
    memset(&attr, 0, sizeof(attr));
    attr.test.prog_fd = fd;
    attr.test.data_in = (uintptr_t)packet;
    attr.test.data_size_in = sizeof(packet);
    attr.test.repeat = 1;
    if (bpf_call(BPF_PROG_TEST_RUN, &attr) < 0) fail("BPF_PROG_TEST_RUN");
    if (attr.test.retval != 64) { fprintf(stderr, "BPF wrong return value\n"); exit(1); }
    printf("PASS eBPF load/JIT/test-run: JIT bytes=%u return=%u\n", info.jited_prog_len, attr.test.retval);
    close(fd);
}

static void check_kvm(void)
{
    int fd = open("/dev/kvm", O_RDWR | O_CLOEXEC);
    if (fd < 0) fail("open /dev/kvm");
    int api = ioctl(fd, KVM_GET_API_VERSION, 0);
    if (api != KVM_API_VERSION) { fprintf(stderr, "Unexpected KVM API %d\n", api); exit(1); }
    int vm = ioctl(fd, KVM_CREATE_VM, 0);
    if (vm < 0) fail("KVM_CREATE_VM");
    struct kvm_vcpu_init init = {0};
    if (ioctl(vm, KVM_ARM_PREFERRED_TARGET, &init) < 0) fail("KVM_ARM_PREFERRED_TARGET");
    int cpu = ioctl(vm, KVM_CREATE_VCPU, 0);
    if (cpu < 0) fail("KVM_CREATE_VCPU");
    if (ioctl(cpu, KVM_ARM_VCPU_INIT, &init) < 0) fail("KVM_ARM_VCPU_INIT");
    printf("PASS KVM API=%d VM/vCPU creation and ARM init (no guest boot)\n", api);
    close(cpu); close(vm); close(fd);
}

static void check_perf(void)
{
    struct perf_event_attr attr = {0};
    attr.size = sizeof(attr);
    attr.type = PERF_TYPE_SOFTWARE;
    attr.config = PERF_COUNT_SW_CPU_CLOCK;
    attr.disabled = 1;
    int fd = syscall(__NR_perf_event_open, &attr, 0, -1, -1, 0);
    if (fd < 0) fail("perf_event_open");
    close(fd);
    puts("PASS perf_event_open (disabled event closed)");
}

static void check_namespaces(void)
{
    fflush(stdout);
    pid_t pid = fork();
    if (pid < 0) fail("fork");
    if (pid == 0) {
        if (unshare(CLONE_NEWNET | CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWCGROUP) < 0)
            fail("isolated namespaces");
        _exit(0);
    }
    int status;
    if (waitpid(pid, &status, 0) < 0) fail("waitpid");
    if (!WIFEXITED(status) || WEXITSTATUS(status)) exit(1);
    puts("PASS isolated net/mount/UTS/IPC/cgroup namespaces");
}

int main(void)
{
    check_bpf(); check_kvm(); check_perf(); check_namespaces();
    return 0;
}
