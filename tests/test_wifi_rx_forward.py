"""Run the production AP RX forwarding branch with mocked kernel primitives."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

RX = TOP / 'upstream/modules/sprd_wlan_combo/sc2355/rx.c'


def forwarding_branch(text):
    start = text.index('\tif ((vif->mode == SPRD_MODE_AP ||\n'
                       '\t     vif->mode == SPRD_MODE_P2P_GO) && msdu_desc->uc_w2w_flag)')
    return text[start:text.index('\n\t\t/* skb->data MUST point to ETH HDR */', start)]


class RxForwarding(unittest.TestCase):
    def run_branch(self, branch, old=False):
        if not shutil.which('cc'):
            self.skipTest('requires a host C compiler')
        code = r'''
#include <arpa/inet.h>
#include <assert.h>
#include <stdbool.h>
#define SPRD_MODE_AP 2
#define SPRD_MODE_P2P_GO 3
#define SPRD_MODE_STATION 1
#define ETH_P_IP 0x0800
#define ETH_P_IPV6 0x86dd
#define ETH_P_ARP 0x0806
#define GFP_ATOMIC 0
#define likely(x) (x)
struct ethhdr { unsigned short h_proto; };
struct sk_buff { void *dev, *data; };
struct vif { int mode; };
struct desc { int uc_w2w_flag, bc_mc_w2w_flag; };
static struct sk_buff copied;
static int forwarded, delivered, copies, fail_copy;
static struct sk_buff *pskb_copy(struct sk_buff *s, int flags) {
    copies++;
    if (fail_copy) return 0;
    copied = *s; return &copied;
}
static void dev_queue_xmit(struct sk_buff *s) { assert(s->dev); forwarded++; }
static void run(int mode, int uc, int bc, unsigned short proto) {
    struct vif v = {mode}, *vif = &v;
    struct desc d = {uc, bc}, *msdu_desc = &d;
    struct ethhdr h = {htons(proto)};
    struct sk_buff s = {.data=&h}, *skb = &s, *tx_skb;
    void *ndev = &h;
    forwarded = delivered = copies = 0;
''' + branch + r'''
        delivered++;
    }
}
int main(int argc, char **argv) {
    if (argc > 1) {
        if (htons(ETH_P_IP) == ETH_P_IP) return 0;
        run(SPRD_MODE_AP, 0, 1, ETH_P_IP);
        assert(forwarded == 1 && delivered == 1 && copies == 1);
        return 0;
    }
    for (int mode = SPRD_MODE_AP; mode <= SPRD_MODE_P2P_GO; mode++) {
        for (int ip = 0; ip < 2; ip++) {
            run(mode, 0, 1, ip ? ETH_P_IPV6 : ETH_P_IP);
            assert(forwarded == 0 && delivered == 1 && copies == 0);
        }
        run(mode, 0, 1, ETH_P_ARP);
        assert(forwarded == 1 && delivered == 1 && copies == 1);
        fail_copy = 1; run(mode, 0, 1, ETH_P_ARP);
        assert(forwarded == 0 && delivered == 1 && copies == 1); fail_copy = 0;
        run(mode, 1, 0, ETH_P_IP);
        assert(forwarded == 1 && delivered == 0 && copies == 0);
        run(mode, 0, 0, ETH_P_IP);
        assert(forwarded == 0 && delivered == 1 && copies == 0);
    }
    run(SPRD_MODE_STATION, 0, 1, ETH_P_IPV6);
    assert(forwarded == 0 && delivered == 1 && copies == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='mu300-rx-forward-') as temp:
            src, exe = Path(temp) / 'check.c', Path(temp) / 'check'
            src.write_text(code)
            subprocess.run(['cc', '-std=c11', '-fsanitize=address,undefined',
                            str(src), '-o', str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)] + (['old'] if old else []), check=True, timeout=5)

    def test_ap_go_ip_multicast_is_stack_only_and_other_forwarding_survives(self):
        self.run_branch(forwarding_branch(RX.read_text()))

    def test_original_vendor_branch_reproduces_the_extra_copy(self):
        branch = forwarding_branch(RX.read_text())
        branch = branch.replace('htons(ETH_P_IP)', 'ETH_P_IP')
        branch = branch.replace('htons(ETH_P_IPV6)', 'ETH_P_IPV6')
        self.run_branch(branch, old=True)

    def test_legacy_patch_applies_and_matches_the_production_branch(self):
        if not shutil.which('patch'):
            self.skipTest('requires patch')
        text = RX.read_text()
        fixed = forwarding_branch(text)
        old = fixed.replace('\t\t\t/* IP multicast is forwarded by the host network stack. */\n', '')
        old = old.replace('eth->h_proto != htons(ETH_P_IP)', 'eth->h_proto != ETH_P_IP')
        old = old.replace('eth->h_proto != htons(ETH_P_IPV6)', 'eth->h_proto != ETH_P_IPV6')
        original = text.replace(fixed, old, 1)
        with tempfile.TemporaryDirectory(prefix='mu300-legacy-forward-') as temp:
            source = Path(temp) / 'sc2355/rx.c'
            source.parent.mkdir(); source.write_text(original)
            patch = (TOP / 'kernel/patches/wlan_combo-rx-ip-multicast-endian.patch').read_bytes()
            subprocess.run(['patch', '-p1', '--batch'], input=patch, cwd=temp,
                           check=True, capture_output=True)
            self.assertEqual(source.read_text(), text)
            self.run_branch(forwarding_branch(source.read_text()))
