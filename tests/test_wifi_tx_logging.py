"""TX-pressure logging must not change credits, ownership, or error returns."""
import shutil
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

WLAN = TOP / 'upstream/modules/sprd_wlan_combo/sc2355'
WCN = TOP / 'upstream/modules/wcn_bsp/pcie/edma_engine.c'


def function(text, name):
    start = re.search(r'(?m)^(?:static )?(?:inline )?(?:int|void) ' + re.escape(name) + r'\(', text).start()
    return text[start:text.index('\n}', start) + 2]


class TxPressureLogging(unittest.TestCase):
    def test_stale_peer_logging_keeps_pcie_and_sdio_rejection(self):
        for backend in ('pcie', 'sdio'):
            text = (WLAN / (backend + '.c')).read_text()
            start = text.index('\tif (lut_index < 6 && (!sc2355_is_group(hif->skb_da))) {')
            branch = text[start:text.index('\n\t}', start) + 3]
            self.assertIn('pr_debug_ratelimited(', branch)
            self.assertNotIn('pr_err(', branch)
            self.run_c(r'''
#include <assert.h>
#include <errno.h>
#define pr_debug_ratelimited(...) ((void)0)
struct sprd_hif { unsigned char skb_da[6]; };
static int sc2355_is_group(unsigned char *addr) { return addr[0] & 1; }
static int check(int lut_index, struct sprd_hif *hif) {
''' + branch + r'''
    return 0;
}
int main(void) {
    struct sprd_hif h = {0};
    for (int group = 0; group < 2; group++) {
        h.skb_da[0] = group;
        for (int lut = 0; lut < 8; lut++)
            assert(check(lut, &h) == ((lut < 6 && !group) ? -EPERM : 0));
    }
    return 0;
}
''')

    def test_tx_failure_frees_each_packet_even_when_logging_is_limited(self):
        text = (WLAN.parent / 'common/iface.c').read_text()
        start = text.index('\tif (ret) {', text.index('\tret = sprd_send_data(vif->priv, vif, msg, skb,'))
        branch = text[start:text.index('\n\t}', start) + 3]
        self.run_c(r'''
#include <assert.h>
#define NETDEV_TX_OK 0
static int logs, checks, freed, messages;
static int net_ratelimit(void) { return checks++ < 10; }
#define netdev_err(...) (++logs)
static void dev_kfree_skb(void *p) { ++freed; }
static void sprd_chip_free_msg(void *p, void *msg) { ++messages; }
struct priv { int chip; };
struct vif { struct priv *priv; };
static int check(int ret, struct vif *vif) {
    void *skb = vif, *msg = vif;
''' + branch + r'''
    return 99;
}
int main(void) {
    struct priv p = {0}; struct vif v = {&p};
    assert(check(0, &v) == 99 && !freed && !messages && !checks);
    for (int i = 0; i < 50000; i++) assert(check(-1, &v) == NETDEV_TX_OK);
    assert(freed == 50000 && messages == 50000 && logs == 10 && checks == 50000);
    return 0;
}
''')

    def run_c(self, code):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('requires a host C compiler')
        with tempfile.TemporaryDirectory(prefix='mu300-tx-pressure-') as tmp:
            source, binary = Path(tmp) / 'check.c', Path(tmp) / 'check'
            source.write_text(code)
            subprocess.run([cc, '-std=gnu11', '-Wall', '-Werror', str(source), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_production_credit_functions_keep_limits_and_count_pressure(self):
        text = (WLAN / 'pcie.c').read_text()
        funcs = '\n'.join(function(text, name) for name in (
            'sc2355_pcie_note_credit_limit', 'sc2355_pcie_fc_get_send_num', 'sc2355_pcie_fc_test_send_num'))
        self.assertNotIn('pr_err(', funcs)
        self.run_c(r'''
#include <assert.h>
typedef long long atomic64_t;
static atomic64_t tx_credit_limited, tx_zero_credit;
#define atomic64_inc(p) (++*(p))
#define atomic_read(p) (*(p))
#define pr_debug_ratelimited(...) ((void)0)
enum sprd_mode { SPRD_MODE_NONE, SPRD_MODE_AP };
struct tx_mgmt { struct { int free_num; } xmit_msg_list; };
struct sprd_hif { struct tx_mgmt *tx_mgmt; };
static unsigned int get_max_fw_tx_dscr(void) { return 1024; }
static unsigned int pcie_get_tx_buf_num(void) { return 1024; }
''' + funcs + r'''
int main(void) {
    struct tx_mgmt tx = {0}; struct sprd_hif hif = {&tx};
    long long limited = 0, zero = 0;
    for (int queued = 0; queued <= 1024; queued += 16) {
        tx.xmit_msg_list.free_num = queued;
        for (int wanted = -1; wanted <= 1200; wanted++) {
            int expected = wanted <= 0 ? 0 : (wanted < 1024-queued ? wanted : 1024-queued);
            if (wanted > 0 && queued+wanted >= 1024) {
                limited += 2;
                if (queued == 1024) zero += 2;
            }
            assert(sc2355_pcie_fc_get_send_num(&hif, SPRD_MODE_AP, wanted) == expected);
            assert(sc2355_pcie_fc_test_send_num(&hif, SPRD_MODE_AP, wanted) == expected);
            assert(tx.xmit_msg_list.free_num == queued);
            assert(sc2355_pcie_fc_get_send_num(&hif, SPRD_MODE_NONE, wanted) == 0);
            assert(sc2355_pcie_fc_test_send_num(&hif, SPRD_MODE_NONE, wanted) == 0);
        }
    }
    assert(tx_credit_limited == limited && tx_zero_credit == zero);
    return 0;
}
''')

    def test_full_queue_refuses_ownership_and_recovers_without_wait(self):
        text = WCN.read_text()
        body = function(text, 'edma_pending_q_buffer')
        self.assertNotIn('sleep', body)
        self.run_c(r'''
#include <assert.h>
#include <string.h>
#include <errno.h>
typedef long long atomic64_t;
static atomic64_t edma_pending_full[32];
#define atomic64_inc(p) (++*(p))
#define atomic64_read(p) (*(p))
#define DEFAULT_RATELIMIT_INTERVAL 5
#define DEFINE_RATELIMIT_STATE(name, interval, burst) int name = 0
static int warnings;
#define pr_warn(...) (warnings++)
static int __ratelimit(int *state) { return !(*state)++; }
#define ERROR (-1)
#define OK 0
#define INCR_RING_BUFF_INDX(i,n) (((i)+1)%(n))
struct entry { void *head, *tail; int num; };
struct edma_pending_q { int wt, rd, max; struct entry ring[4]; };
struct edma_info { struct { struct edma_pending_q pending_q; } chn_sw[32]; };
static struct edma_info edma;
static struct edma_info *edma_info(void) { return &edma; }
''' + body + r'''
int main(void) {
    struct edma_pending_q *q = &edma.chn_sw[10].pending_q;
    q->max = 4; q->wt = 3; q->rd = 0;
    struct edma_pending_q before = *q;
    int head = 1, tail = 2;
    for (int i = 0; i < 50000; i++)
        assert(edma_pending_q_buffer(10, &head, &tail, 2) == -EAGAIN);
    assert(!memcmp(&before, q, sizeof(before)));
    assert(edma_pending_full[10] == 50000 && warnings == 1);
    for (int i = 0; i < 32; i++) if (i != 10) assert(edma_pending_full[i] == 0);
    q->rd = 1;  /* completion frees capacity; same caller-owned list retries */
    assert(edma_pending_q_buffer(10, &head, &tail, 2) == OK);
    assert(q->wt == 0 && q->rd == 1);
    assert(q->ring[3].head == &head && q->ring[3].tail == &tail && q->ring[3].num == 2);
    assert(edma_pending_full[10] == 50000);
    return 0;
}
''')

    def test_diagnostics_read_only_and_legacy_build_wired(self):
        wlan, wcn = (WLAN / 'pcie.c').read_text(), WCN.read_text()
        self.assertIn('module_param_cb(mu300_tx_fc_stats, &mu300_tx_fc_stats_ops, NULL, 0444)', wlan)
        self.assertIn('module_param_cb(mu300_edma_stats, &mu300_edma_stats_ops, NULL, 0444)', wcn)
        push = function(wlan, 'sc2355_pcie_push_link')
        self.assertIn('pr_err_ratelimited', push)
        self.assertIn('return ret;', push)
        self.assertIn('sprdwl_list_cut_to_send_list(tx_head,', wlan)
        self.assertIn('if (!ret) {\n\t\t\trx_mgmt->addr_trans_head = NULL;', wlan)
        self.assertNotIn('pr_err("%s, %d: _fc_ no credit!', (WLAN / 'tx.c').read_text())
        self.assertIn('sprdwcn-edma-pressure-stats', (TOP / 'kernel/build-all.sh').read_text())
        for name in ('sprdwcn-edma-pressure-stats', 'wlan_combo-tx-pressure-logging'):
            self.assertTrue((TOP / f'kernel/patches/{name}.patch').is_file())
        for path in ('tools/build-openwrt-tf-magisk.sh', 'upstream/make-bundle.sh'):
            packaging = (TOP / path).read_text()
            self.assertIn('for wireless_driver in sprd_wlan_combo wcn_bsp mu300_thermal; do', packaging)
            self.assertIn('-newer "$wireless_module"', packaging)
