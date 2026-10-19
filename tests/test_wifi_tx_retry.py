"""Execute production TX code for prefixed commands and EDMA retry races."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP
from test_wifi_tx_logging import function

WLAN = TOP / 'upstream/modules/sprd_wlan_combo/sc2355'


class TxRetry(unittest.TestCase):
    def test_legacy_build_keeps_the_bus_and_wlan_retry_contract_together(self):
        build = (TOP / 'kernel/build-all.sh').read_text(encoding='utf-8')
        self.assertIn('sprdwcn-tx-pending-backpressure', build)
        patches = TOP / 'kernel/patches'
        self.assertIn('+\t\treturn -EAGAIN;',
                      (patches / 'sprdwcn-tx-pending-backpressure.patch').read_text(encoding='utf-8'))
        wlan = (patches / 'wlan_combo-tx-retry.patch').read_text(encoding='utf-8')
        self.assertIn('atomic_xchg(&tx_mgmt->pcie_tx_waiting, 0)', wlan)
        self.assertIn('ret == -EAGAIN', wlan)
        self.assertIn('MSDU_DSCR_RSVD : 0',
                      (patches / 'wlan_combo-special-data-prefix.patch').read_text(encoding='utf-8'))

    def run_c(self, code):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('requires a host C compiler')
        with tempfile.TemporaryDirectory(prefix='mu300-tx-retry-') as tmp:
            src, binary = Path(tmp) / 'check.c', Path(tmp) / 'check'
            src.write_text(code)
            result = subprocess.run([cc, '-std=gnu11', '-Wall', '-Werror', '-Wno-pointer-sign',
                            '-fsanitize=address,undefined', '-fno-pie', '-no-pie',
                            str(src), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_command_group_priority_skips_transport_prefix(self):
        hdr = (WLAN / 'tx.h').read_text(encoding='utf-8')
        desc = hdr[hdr.index('struct tx_msdu_dscr {'):]
        desc = desc[:desc.index('} __packed;') + len('} __packed;')]
        body = function((WLAN / 'cmdevt.c').read_text(encoding='utf-8'), 'sprd_xmit_data2cmd_wq')
        self.run_c(r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
typedef unsigned char u8;
#define __packed __attribute__((packed))
#define SPRD_HW_SC2355_PCIE 1
#define SPRD_HW_SC2355_SDIO 2
#define SPRD_MODE_AP 3
#define SPRD_MODE_P2P_GO 4
#define SPRD_MODE_STATION 5
#define SPRD_TYPE_CMD 0
#define MSDU_DSCR_RSVD 5
#define SPRD_CMD_TX_DATA 16
#define prio_1 1
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
#define pr_err(...) ((void)0)
''' + desc + r'''
struct sprd_hif { int hw_type; };
struct sprd_priv { struct sprd_hif hif; };
struct sprd_vif { struct sprd_priv *priv; int mode; };
struct net_device { struct sprd_vif *vif; };
struct sk_buff { u8 storage[256]; u8 *data; int len; };
struct sprd_work { u8 data[256]; struct sprd_vif *vif; int id; };
static struct sprd_work work;
static int frees, queued, fill_fail, alloc_fail, lut, initial_tid;
static void *netdev_priv(struct net_device *dev) { return dev->vif; }
static u8 *skb_push(struct sk_buff *skb, int len) {
    assert(skb->data - skb->storage >= len);
    skb->data -= len; skb->len += len; return skb->data;
}
static void dev_kfree_skb(struct sk_buff *skb) { ++frees; }
static int fill(struct sprd_vif *vif, struct sk_buff *skb, int type, int off) {
    if (fill_fail) return -EPERM;
    struct tx_msdu_dscr *d = (void *)skb_push(skb, sizeof(*d));
    memset(d, 0, sizeof(*d));
    d->common.interface = 1; d->offset = sizeof(*d);
    d->sta_lut_index = lut; d->buffer_info.msdu_tid = initial_tid;
    d->buffer_info.mac_data_offset = 10;
    d->pkt_len = 48;
    if (vif->priv->hif.hw_type == SPRD_HW_SC2355_PCIE)
        memset(skb_push(skb, MSDU_DSCR_RSVD), 0xa5, MSDU_DSCR_RSVD);
    return 0;
}
#define sc2355_pcie_hif_fill_msdu_dscr fill
#define sc2355_hif_fill_msdu_dscr fill
static struct sprd_work *sprd_alloc_work(int len) { return alloc_fail ? NULL : &work; }
static void sprd_queue_work(struct sprd_priv *priv, struct sprd_work *w) {
    assert(w == &work); ++queued;
}
''' + body + r'''
int main(void) {
    assert(sizeof(struct tx_msdu_dscr) == 11);
    for (int bus = 1; bus <= 2; bus++)
    for (int mode = 3; mode <= 5; mode++)
    for (lut = 4; lut <= 6; lut++)
    for (initial_tid = 0; initial_tid <= 7; initial_tid++) {
        struct sprd_priv priv = {.hif.hw_type = bus};
        struct sprd_vif vif = {&priv, mode}; struct net_device dev = {&vif};
        struct sk_buff skb = {.len = 48}; skb.data = skb.storage + 64;
        memset(skb.data, 0x5a, 48);
        frees = queued = 0;
        assert(sprd_xmit_data2cmd_wq(&skb, &dev) == 0);
        assert(frees == 1 && queued == 1 && work.vif == &vif && work.id == 16);
        assert(skb.len == 64);
        struct tx_msdu_dscr *d = (void *)(work.data + 5);
        int group = mode != SPRD_MODE_STATION && lut < 6;
        assert(d->buffer_info.msdu_tid == (group ? prio_1 : initial_tid));
        assert(d->common.interface == 1 && d->offset == 11 && d->pkt_len == 48);
        assert(d->sta_lut_index == lut && d->buffer_info.mac_data_offset == 10);
        for (int i = 0; i < 5; i++)
            assert(work.data[i] == (bus == 1 ? 0xa5 : '0' + i));
        for (int i = 16; i < 64; i++) assert(work.data[i] == 0x5a);
    }
    return 0;
}
''')

    def test_dma_completion_cannot_be_lost_around_refusal(self):
        text = (WLAN / 'pcie.c').read_text(encoding='utf-8')
        callback = function(text, 'sc2355_pcie_tx_data_complete')
        submit = function(text, 'sc2355_pcie_tx_data_push')
        self.run_c(r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
typedef int atomic_t;
#define atomic_set(p,v) (*(p)=(v))
static int atomic_xchg(int *p, int v) { int old=*p; *p=v; return old; }
#define smp_load_acquire(p) (*(p))
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
struct tx_mgmt { atomic_t pcie_tx_waiting; int wakeups; };
struct sprd_hif { void *tx_mgmt; int tx_data_port; };
struct mbuf_t { int owner; };
static struct sprd_hif *current_hif;
static int result, complete_during_push, submits;
static struct sprd_hif *sc2355_pcie_get_hif(void) { return current_hif; }
static void sc2355_tx_up(struct tx_mgmt *tx) { ++tx->wakeups; }
static void sc2355_rx_bus_complete(struct sprd_hif *hif) {}
static int sc2355_pcie_tx_data_pop_list(int c, struct mbuf_t *h, struct mbuf_t *t, int n) { return 0; }
''' + callback + r'''
static int sc2355_pcie_push_link(struct sprd_hif *hif, int ch,
        struct mbuf_t *head, struct mbuf_t *tail, int num,
        int (*pop)(int, struct mbuf_t *, struct mbuf_t *, int)) {
    assert(ch == 10 && num == 1 && head == tail);
    assert(head->owner == 0);
    ++submits;
    if (complete_during_push) sc2355_pcie_tx_data_complete(ch, 0);
    if (!result) head->owner = 1;
    return result;
}
''' + submit + r'''
int main(void) {
    struct tx_mgmt tx = {0}; struct sprd_hif hif = {&tx, 10};
    struct mbuf_t mbuf = {0}; current_hif = &hif;
    for (int race = 0; race < 2; race++) {
        tx.wakeups = 0; result = -EAGAIN; complete_during_push = race;
        assert(sc2355_pcie_tx_data_push(&hif, &mbuf, &mbuf, 1) == -EAGAIN);
        assert(mbuf.owner == 0);
        if (!race) {
            assert(tx.pcie_tx_waiting == 1 && tx.wakeups == 0);
            sc2355_pcie_tx_data_complete(10, 0);
        }
        assert(tx.pcie_tx_waiting == 0 && tx.wakeups == 1);
        sc2355_pcie_tx_data_complete(10, 0);
        assert(tx.wakeups == 1);
        result = 0; complete_during_push = 0;
        assert(sc2355_pcie_tx_data_push(&hif, &mbuf, &mbuf, 1) == 0);
        assert(mbuf.owner == 1 && tx.pcie_tx_waiting == 0);
        mbuf.owner = 0;
    }
    result = -EIO;
    assert(sc2355_pcie_tx_data_push(&hif, &mbuf, &mbuf, 1) == -EIO);
    assert(mbuf.owner == 0 && tx.pcie_tx_waiting == 0);
    result = -EAGAIN;
    sc2355_pcie_tx_data_push(&hif, &mbuf, &mbuf, 1);
    sc2355_pcie_tx_data_complete(10, 1);
    assert(tx.pcie_tx_waiting == 1); /* timeout is not newly freed capacity */
    sc2355_pcie_tx_data_complete(10, 0);
    hif.tx_mgmt = NULL; sc2355_pcie_tx_data_complete(10, 0);
    current_hif = NULL; sc2355_pcie_tx_data_complete(10, 0);
    assert(submits == 6);
    return 0;
}
''')
        ops = text[text.index('struct mchn_ops_t sc2355_pcie_hif_ops[]'):]
        ops = ops[:ops.index('\n};')]
        for port in ('PCIE_TX_DATA_PORT', 'PCIE_TX_ADDR_DATA_PORT'):
            entry = ops[ops.index('INIT_INTF_SC2355(' + port):].split('),', 1)[0]
            self.assertIn('sc2355_pcie_tx_data_complete', entry)

    def test_backpressure_does_not_consume_the_hard_error_budget(self):
        body = function((WLAN / 'tx.c').read_text(encoding='utf-8'), 'tx_handle_to_send_list')
        self.run_c(r'''
#include <assert.h>
#include <errno.h>
typedef unsigned char u8;
typedef int spinlock_t;
#define SPRD_HW_SC2355_PCIE 1
#define SPRD_AC_MAX 4
#define pr_err(...) ((void)0)
#define spin_lock_bh(p) ((void)(p))
#define spin_unlock_bh(p) ((void)(p))
enum sprd_mode { SPRD_MODE_AP };
struct list_head { int empty; };
struct sprd_msg_list { int unused; };
struct tx_mgmt {
    struct { struct list_head to_send_list; spinlock_t send_lock;
             enum sprd_mode mode; int failcount; } xmit_msg_list;
    struct sprd_msg_list tx_list_qos_pool;
};
struct sprd_hif { void *tx_mgmt; int coex_bt_on, hw_type; };
static int result, flushes;
static int list_empty(struct list_head *l) { return l->empty; }
static int sc2355_qos_get_list_num(struct list_head *l) { return 4; }
static int get_credit(struct sprd_hif *h, enum sprd_mode m, int n) { return n; }
#define sc2355_pcie_fc_get_send_num get_credit
#define sc2355_fc_get_send_num get_credit
static int submit(struct sprd_hif *h, struct list_head *l, struct list_head *o, int n, int a, u8 b) { return result; }
#define sc2355_pcie_hif_tx_list submit
#define sc2355_hif_tx_list submit
static void tx_return(struct sprd_hif *h, struct sprd_msg_list *l, int n, int r) {}
#define sc2355_pcie_handle_tx_return tx_return
#define sc2355_handle_tx_return tx_return
static void sc2355_flush_tosendlist(struct tx_mgmt *tx) { ++flushes; }
''' + body + r'''
int main(void) {
    struct tx_mgmt tx = {0}; struct sprd_hif h = {&tx, 0, 1};
    result = -EAGAIN;
    for (int i = 0; i < 50000; i++)
        assert(tx_handle_to_send_list(&h, SPRD_MODE_AP) == -EAGAIN);
    assert(tx.xmit_msg_list.failcount == 0 && flushes == 0);
    result = -EIO;
    for (int i = 0; i < 51; i++)
        assert(tx_handle_to_send_list(&h, SPRD_MODE_AP) == -ENOMEM);
    assert(tx.xmit_msg_list.failcount == 51 && flushes == 1);
    result = 0;
    assert(tx_handle_to_send_list(&h, SPRD_MODE_AP) == 0);
    assert(tx.xmit_msg_list.failcount == 0);
    return 0;
}
''')
