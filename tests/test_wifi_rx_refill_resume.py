"""Execute actual RX refill and PCIe completion code across recovery races."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from helpers import TOP
from test_wifi_tx_logging import function

WLAN = TOP / 'upstream/modules/sprd_wlan_combo/sc2355'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int atomic_t;
#define READ_ONCE(x) (x)
#define atomic_read(p) (*(p))
static unsigned int atomic_xchg(atomic_t *p, unsigned int v) {
    unsigned int old=*p; *p=v; return old;
}
#define atomic_add_return(v,p) (*(p)+=(v))
#define smp_load_acquire(p) (*(p))
#define SPRD_HW_SC2355_PCIE 3
#define SPRD_MAX_ADD_MH_BUF_ONCE 100U
#define SPRD_PCIE_RX_ALLOC_BUF 20
#define clamp(v,lo,hi) ((v)<(lo)?(lo):((v)>(hi)?(hi):(v)))
#define msecs_to_jiffies(x) (x)
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; bool pending; unsigned int delay; };
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define to_delayed_work(p) container_of(p, struct delayed_work, work)
struct mem_mgmt { atomic_t alloc_num; };
struct sprd_hif;
struct rx_mgmt {
    struct sprd_hif *hif;
    struct mem_mgmt mm_entry;
    bool stopping;
    struct delayed_work refill_retry;
    void *addr_trans_head;
    unsigned int refill_backoff_ms;
    bool refill_lock, refill_bus_waiting, refill_bus_ready;
};
struct tx_mgmt { atomic_t pcie_tx_waiting; unsigned int wakes; };
struct ops { int (*tx_addr_trans)(struct sprd_hif *, void *, int, bool); };
struct sprd_hif {
    struct rx_mgmt *rx_mgmt; struct tx_mgmt *tx_mgmt;
    struct ops *ops; void *priv; int hw_type, tx_data_port;
};
static struct sprd_hif *current_hif;
static unsigned int rcu_depth, submissions, rx_queued, allocated;
static unsigned int scheduled, cancelled, alloc_calls, retry_expired;
static int bus_result, completion_in_submit;
static bool stop_in_submit;
static void *system_wq;
#define rcu_read_lock() (++rcu_depth)
#define rcu_read_unlock() (--rcu_depth)
#define spin_lock_irqsave(p,f) do { assert(!*(p)); *(p)=true; (f)=0; } while (0)
#define spin_unlock_irqrestore(p,f) do { assert(*(p)); *(p)=false; (void)(f); } while (0)
static bool delayed_work_pending(struct delayed_work *w) { return w->pending; }
static void mod_delayed_work(void *q, struct delayed_work *w, unsigned int delay) {
    ++scheduled; w->pending=true; w->delay=delay;
}
static void queue_delayed_work(void *q, struct delayed_work *w, unsigned int delay) {
    assert(!w->pending); mod_delayed_work(q,w,delay);
}
static void cancel_delayed_work(struct delayed_work *w) { ++cancelled; w->pending=false; }
static unsigned int sc2355_mm_buffer_alloc(struct mem_mgmt *m, unsigned int n) {
    ++alloc_calls; assert(allocated<=n); return n-allocated;
}
static void sc2355_queue_rx_buff_work(void *priv, int id) {
    assert(id==SPRD_PCIE_RX_ALLOC_BUF);
    assert(!current_hif->rx_mgmt->refill_lock);
    ++rx_queued;
}
static struct sprd_hif *sc2355_pcie_get_hif(void) { return current_hif; }
static void sc2355_tx_up(struct tx_mgmt *t) { ++t->wakes; }
static int sc2355_pcie_tx_data_complete(int channel,int timeout);
static int submit(struct sprd_hif *h, void *p, int n, bool now) {
    assert(now && !h->rx_mgmt->refill_lock); ++submissions;
    if (completion_in_submit) {
        completion_in_submit=0;
        sc2355_pcie_tx_data_complete(h->tx_data_port,0);
    }
    if (stop_in_submit) h->rx_mgmt->stopping=true;
    if (!bus_result) h->rx_mgmt->addr_trans_head=NULL;
    return bus_result;
}
static void expire(struct rx_mgmt *rx);
'''

CASES = r'''
static void expire(struct rx_mgmt *rx) {
    assert(rx->refill_retry.pending);
    rx->refill_retry.pending=false;
    ++retry_expired;
    rx_refill_retry(&rx->refill_retry.work);
}
static void reset(struct rx_mgmt *rx,struct tx_mgmt *tx,struct sprd_hif *h,struct ops *ops) {
    memset(rx,0,sizeof(*rx)); memset(tx,0,sizeof(*tx));
    *h=(struct sprd_hif){.rx_mgmt=rx,.tx_mgmt=tx,.ops=ops,.hw_type=SPRD_HW_SC2355_PCIE,.tx_data_port=10};
    current_hif=h; rx->hif=h;
    submissions=rx_queued=allocated=scheduled=cancelled=alloc_calls=retry_expired=0;
    completion_in_submit=0; stop_in_submit=false; bus_result=-EAGAIN;
}
int main(void) {
    struct rx_mgmt rx; struct tx_mgmt tx; struct sprd_hif h;
    struct ops ops={.tx_addr_trans=submit};
    unsigned int previous[]={0,20,40,80,160,320,640,1000};
    unsigned int cases=0;
    for (unsigned int i=0;i<sizeof(previous)/sizeof(previous[0]);++i)
    for (unsigned int waiting=0;waiting<2;++waiting)
    for (unsigned int early=0;early<2;++early) {
        reset(&rx,&tx,&h,&ops);
        rx.addr_trans_head=&rx; rx.refill_backoff_ms=previous[i];
        tx.pcie_tx_waiting=waiting;
        completion_in_submit=early;
        assert(sc2355_mm_fill_buffer(&h)==0 && submissions==1);
        assert(rx.refill_retry.pending);
        if (!early) {
            assert(rx.refill_retry.delay>=20);
            sc2355_pcie_tx_data_complete(10,0);
        }
        /* Completion before timer arming and after timer arming both win. */
        assert(rx.refill_retry.delay==0);
        assert(tx.wakes==waiting && rx_queued==0);
        unsigned int before=scheduled;
        for (int duplicate=0;duplicate<100;++duplicate)
            sc2355_pcie_tx_data_complete(10,0);
        assert(scheduled==before); /* one pending RX retry, no IRQ storm */
        bus_result=0;
        expire(&rx);
        assert(rx_queued==1);
        sc2355_mm_fill_buffer(&h);
        assert(submissions==2 && rx.addr_trans_head==NULL);
        assert(!rx.refill_retry.pending && rx.refill_backoff_ms==0);
        before=scheduled;
        sc2355_pcie_tx_data_complete(10,0);
        assert(scheduled==before && !rx.refill_bus_waiting);
        assert(!rcu_depth); ++cases;
    }
    /* An RX work item already queued before the zero timer expires must also
     * be allowed through; a later timer must not restore the long delay. */
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx;
    sc2355_mm_fill_buffer(&h); sc2355_pcie_tx_data_complete(10,0);
    assert(rx.refill_retry.delay==0); bus_result=0;
    sc2355_mm_fill_buffer(&h);
    assert(submissions==2 && cancelled==1 && !rx.refill_retry.pending); ++cases;

    /* A completion is only an opportunity, not proof of submission success.
     * Losing capacity again re-arms a bounded timer instead of spinning. */
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx;
    sc2355_mm_fill_buffer(&h); sc2355_pcie_tx_data_complete(10,0);
    expire(&rx); sc2355_mm_fill_buffer(&h);
    assert(rx.refill_retry.pending && rx.refill_retry.delay==40);
    assert(submissions==2); ++cases;

    /* Lack of completions retains the original timer fallback. */
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx;
    unsigned int expected[]={20,40,80,160,320,640,1000,1000};
    for (unsigned int i=0;i<sizeof(expected)/sizeof(expected[0]);++i) {
        sc2355_mm_fill_buffer(&h);
        assert(rx.refill_retry.delay==expected[i]);
        unsigned int n=submissions;
        for (int event=0;event<8;++event) sc2355_mm_fill_buffer(&h);
        assert(submissions==n);
        expire(&rx);
    }
    ++cases;

    /* Allocation failure and hard submission failures must not be released by
     * unrelated bus completions. Neither is evidence that memory is available. */
    for (int error=0;error<2;++error) {
        reset(&rx,&tx,&h,&ops);
        if (error) { rx.addr_trans_head=&rx; bus_result=-EIO; }
        else { rx.mm_entry.alloc_num=101; bus_result=0; }
        sc2355_mm_fill_buffer(&h);
        assert(rx.refill_retry.delay==20 && !rx.refill_bus_waiting);
        unsigned int n=scheduled;
        sc2355_pcie_tx_data_complete(10,0);
        assert(rx.refill_retry.delay==20 && scheduled==n);
        ++cases;
    }
    /* Wrong channel, a timeout, and an SDIO context cannot provide RX progress. */
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx;
    sc2355_mm_fill_buffer(&h);
    sc2355_pcie_tx_data_complete(5,0);
    sc2355_pcie_tx_data_complete(10,1);
    assert(rx.refill_retry.delay==20); ++cases;
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx; h.hw_type=1;
    sc2355_mm_fill_buffer(&h); sc2355_pcie_tx_data_complete(10,0);
    assert(rx.refill_retry.delay==20 && !rx.refill_bus_waiting); ++cases;

    /* Allocation progress keeps the existing immediate serial refill path. */
    reset(&rx,&tx,&h,&ops); rx.mm_entry.alloc_num=201; allocated=1;
    sc2355_mm_fill_buffer(&h);
    assert(rx_queued==1 && scheduled==0 && rx.refill_backoff_ms==0); ++cases;

    /* Teardown wins against completions and an already-running submission. */
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx;
    sc2355_mm_fill_buffer(&h); rx.stopping=true;
    unsigned int n=scheduled;
    sc2355_pcie_tx_data_complete(10,0);
    assert(scheduled==n);
    expire(&rx); assert(rx_queued==0);
    sc2355_mm_fill_buffer(&h); assert(submissions==1); ++cases;
    reset(&rx,&tx,&h,&ops); rx.addr_trans_head=&rx; stop_in_submit=true;
    sc2355_mm_fill_buffer(&h);
    assert(!rx.refill_retry.pending && !rx.refill_bus_waiting); ++cases;

    /* Early init and late completion: published RX/TX contexts may be absent. */
    reset(&rx,&tx,&h,&ops); h.rx_mgmt=NULL;
    sc2355_pcie_tx_data_complete(10,0);
    h.tx_mgmt=NULL; sc2355_pcie_tx_data_complete(10,0);
    current_hif=NULL; sc2355_pcie_tx_data_complete(10,0);
    assert(!rcu_depth); ++cases;
    printf("%u RX completion/refill scenarios passed\n",cases);
    return 0;
}
'''


class RxRefillResume(unittest.TestCase):
    def code(self, baseline=False):
        rx, pcie = (WLAN/'rx.c').read_text(), (WLAN/'pcie.c').read_text()
        if baseline:
            # Recreate the old missing connection without depending on the
            # checkout's HEAD (the regression remains useful after commit).
            self.assertEqual(pcie.count('sc2355_rx_bus_complete(hif);'),1)
            pcie=pcie.replace('sc2355_rx_bus_complete(hif);','(void)hif;')
        constants='\n'.join(s for s in rx.splitlines() if s.startswith('#define SPRD_REFILL_BACKOFF_'))
        notify=function(rx,'sc2355_rx_bus_complete') if 'void sc2355_rx_bus_complete(' in rx else ''
        return (HARNESS + '\n' + constants + '\n' + notify + '\n' +
                function(rx,'rx_refill_retry') + '\n' + function(rx,'sc2355_mm_fill_buffer') + '\n' +
                function(pcie,'sc2355_pcie_tx_data_complete') + '\n' + CASES)

    def run_code(self, baseline=False):
        cc=shutil.which('cc')
        if not cc:self.skipTest('requires a host C compiler')
        with tempfile.TemporaryDirectory(prefix='mu300-rx-resume-') as tmp:
            src,exe=Path(tmp)/'check.c',Path(tmp)/'check'
            src.write_text(self.code(baseline))
            p=subprocess.run([cc,'-std=gnu11','-Wall','-Werror','-Wno-unused-function',
                              '-fsanitize=address,undefined','-fno-pie','-no-pie',
                              str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            return subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)

    def test_completion_resumes_rx_and_preserves_fault_backoff(self):
        result=self.run_code()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('RX completion/refill scenarios passed',result.stdout)

    def test_missing_completion_hook_reproduces_old_delay(self):
        result=self.run_code(baseline=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('rx.refill_retry.delay==0',result.stderr)

    def test_completion_lifetime_and_shutdown_order(self):
        rx=(WLAN/'rx.c').read_text()
        pcie=(WLAN/'pcie.c').read_text()
        callback=function(pcie,'sc2355_pcie_tx_data_complete')
        self.assertLess(callback.index('rcu_read_lock()'),callback.index('sc2355_pcie_get_hif()'))
        self.assertLess(callback.index('sc2355_rx_bus_complete'),callback.index('rcu_read_unlock()'))
        init=function(rx,'sc2355_rx_init')
        self.assertLess(init.index('spin_lock_init'),init.index('smp_store_release'))
        self.assertLess(init.index('rx_mgmt->hif = hif'),init.index('smp_store_release'))
        close=function(rx,'sc2355_rx_deinit')
        order=['spin_lock_irqsave','WRITE_ONCE(rx_mgmt->stopping, true)',
               'spin_unlock_irqrestore','cancel_delayed_work_sync','sprd_clean_work',
               'smp_store_release(&hif->rx_mgmt, NULL)','synchronize_rcu()','kfree(rx_mgmt)']
        offsets=[close.index(s) for s in order]
        self.assertEqual(offsets,sorted(offsets))
        self.assertLess(close.index('sprd_clean_work'),close.rindex('cancel_delayed_work_sync'))


if __name__=='__main__':
    unittest.main()
