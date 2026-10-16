"""Exercise actual descriptor fillers and their command caller under ASan."""
import unittest

import test_wifi_tx_retry as retry
from test_wifi_tx_logging import function

WLAN = retry.WLAN


class SkbHeadroom(unittest.TestCase):
    run_c = retry.TxRetry.run_c

    def test_actual_fillers_preserve_skb_ownership_and_packet(self):
        hdr = (WLAN / 'tx.h').read_text()
        desc = hdr[hdr.index('struct tx_msdu_dscr {'):]
        desc = desc[:desc.index('} __packed;') + len('} __packed;')]
        fillers = '\n'.join(function((WLAN / f).read_text(), name) for f, name in (
            ('pcie.c', 'sc2355_pcie_hif_fill_msdu_dscr'),
            ('sdio.c', 'sc2355_hif_fill_msdu_dscr')))
        caller = function((WLAN / 'cmdevt.c').read_text(), 'sprd_xmit_data2cmd_wq')
        send = function((WLAN / 'tx.c').read_text(), 'sc2355_send_data')
        self.run_c(r'''
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <arpa/inet.h>
typedef uint8_t u8;
#define __packed __attribute__((packed))
#define ETH_ALEN 6
#define ETH_P_ARP 0x806
#define ETH_P_TDLS 0x890d
#define ETH_P_PREAUTH 0x88c7
#define ETH_P_IPV6 0x86dd
#define SPRD_TYPE_CMD 0
#define SPRD_TYPE_DATA 1
#define SPRD_HW_SC2355_PCIE 1
#define SPRD_MODE_AP 3
#define SPRD_MODE_P2P_GO 4
#define MSDU_DSCR_RSVD 5
#define DSCR_LEN 11
#define INTF_IS_PCIE (hif->hw_type == SPRD_HW_SC2355_PCIE)
#define SPRD_MH_ADDRESS_BIT 0x8000000000UL
#define CHECKSUM_PARTIAL 1
#define SPRD_CMD_TX_DATA 16
#define prio_1 1
#define pr_err(...) ((void)0)
#define pr_err_ratelimited(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
#define pr_debug_ratelimited(...) ((void)0)
''' + desc + r'''
struct ethhdr { u8 d[6],s[6]; uint16_t h_proto; } __packed;
struct ipv6hdr { u8 nexthdr; };
struct iphdr { u8 protocol; };
struct sprd_hif { int hw_type,hif_offset,tdls_flow_count_enable; u8 skb_da[6]; };
struct sprd_chip { int unused; };
struct sprd_priv { struct sprd_hif hif; struct sprd_chip chip; };
struct sprd_vif { struct sprd_priv *priv; int mode,ctx_id,sm_state; };
struct net_device { struct sprd_vif *vif; };
struct sk_buff {
    u8 *storage,*data; int len,ip_summed,transport_header,mac_header,cloned;
};
struct sprd_work { struct sprd_vif *vif; int id; u8 data[256]; };
static struct sprd_work output;
static int cow_fail, cow_calls, frees, queued;
static u8 *shared_storage;
static struct iphdr ip = { IPPROTO_TCP };
static struct ipv6hdr ip6 = { IPPROTO_UDP };
static void *netdev_priv(struct net_device *d) { return d->vif; }
static int skb_headroom(struct sk_buff *s) { return s->data-s->storage; }
static int skb_header_cloned(struct sk_buff *s) { return s->cloned; }
static u8 *skb_push(struct sk_buff *s,int n) {
    assert(skb_headroom(s) >= n);
    s->data-=n;s->len+=n;return s->data;
}
static int skb_cow_head(struct sk_buff *s,int n) {
    ++cow_calls;
    if (cow_fail) return -ENOMEM;
    u8 *p=calloc(1,s->len+n); assert(p);
    memcpy(p+n,s->data,s->len);
    if (!s->cloned) free(s->storage);
    else { assert(!shared_storage); shared_storage=s->storage; }
    s->storage=p;s->data=p+n;s->cloned=0;return 0;
}
static void kfree_skb(struct sk_buff *s) {
    ++frees;free(s->storage);free(s);
}
#define dev_kfree_skb kfree_skb
static bool sc2355_is_vowifi_pkt(struct sk_buff *s,bool *b) { return false; }
static u8 sc2355_pcie_find_lut_index(struct sprd_hif *h,struct sprd_vif *v) {
    return 4;
}
#define sc2355_find_lut_index sc2355_pcie_find_lut_index
static bool sc2355_is_group(u8 *p) { return *p & 1; }
#define virt_to_phys(p) ((unsigned long)(p))
#define cpu_to_le16(x) (x)
#define ipv6_hdr(s) (&ip6)
#define ip_hdr(s) (&ip)
static struct sprd_work *sprd_alloc_work(int n) {
    assert(n <= sizeof(output.data)); return &output;
}
static void sprd_queue_work(struct sprd_priv *p,struct sprd_work *w) {
    assert(w == &output);++queued;
}
static struct sk_buff *packet(int headroom, int cloned) {
    struct sk_buff *s=calloc(1,sizeof(*s));assert(s);
    s->len=64;s->storage=calloc(1,headroom+64);assert(s->storage);
    s->data=s->storage+headroom;s->cloned=cloned;
    memset(s->data,0x5a,64);s->data[0]=1;
    ((struct ethhdr *)s->data)->h_proto=htons(ETH_P_IPV6);
    s->ip_summed=CHECKSUM_PARTIAL;return s;
}
struct sprd_msg { int unused; };
static u8 expected[64];
#define SPRD_CONNECTED 2
static void sprd_fill_msg(struct sprd_msg *m,struct sk_buff *s,u8 *d,int n) {
    assert(s->data==d && s->len==n);
}
static int sc2355_tcp_ack_filter_send(struct sprd_priv *p,struct sprd_msg *m,
                                    u8 *buf,int n) {
    assert(n==64 && !memcmp(expected,buf,64));return 1;
}
static int sprd_chip_tx(struct sprd_chip *c,struct sprd_msg *m) { return 0; }
static void sc2355_tdls_count_flow(struct sprd_vif *v,u8 *p,int n) {}
''' + fillers + '\n' + caller + '\n' + send + r'''
int main(void) {
    for (int bus=1;bus<=2;bus++)
    for (int room=0;room<=64;room+=64)
    for (int clone=0;clone<=1;clone++)
    for (int offset=0;offset<=7;offset+=7) {
        struct sprd_priv p={.hif={.hw_type=bus,.hif_offset=bus==1?0:4}};
        struct sprd_vif v={&p,SPRD_MODE_AP,1};struct net_device dev={&v};
        struct sk_buff *s=packet(room,clone), *original=s;
        u8 payload[64];memcpy(payload,s->data,64);
        cow_fail=0;cow_calls=0;
        int ret=bus==1 ? sc2355_pcie_hif_fill_msdu_dscr(&v,s,SPRD_TYPE_CMD,offset)
                       : sc2355_hif_fill_msdu_dscr(&v,s,SPRD_TYPE_CMD,offset);
        assert(!ret && s==original && cow_calls==(room==0 || clone));
        int prefix=bus==1 ? 5:0;
        struct tx_msdu_dscr *d=(void *)(s->data+prefix);
        assert(d->sta_lut_index==4 && d->common.interface==1);
        assert(d->tx_ctrl.checksum_offload && !d->tx_ctrl.checksum_type);
        assert(!memcmp(payload,s->data+prefix+sizeof(*d)+offset,64));
        kfree_skb(s);free(shared_storage);shared_storage=NULL;

        /* The real caller must use and release the same skb object once. */
        s=packet(room,clone);memcpy(payload,s->data,64);
        int old_frees=frees;queued=0;
        assert(!sprd_xmit_data2cmd_wq(s,&dev));
        assert(frees==old_frees+1 && queued==1);
        d=(void *)(output.data+5);
        assert(d->buffer_info.msdu_tid==prio_1 && d->sta_lut_index==4);
        assert(!memcmp(payload,output.data+16,64));
        free(shared_storage);shared_storage=NULL;

        /* Normal data callers also need to refresh payload after cow. */
        s=packet(room,clone);memcpy(expected,s->data,64);
        struct sprd_msg msg;
        assert(!sc2355_send_data(&v,&msg,s,SPRD_TYPE_DATA,offset,true));
        kfree_skb(s);free(shared_storage);shared_storage=NULL;

        /* Failed preparation retains caller ownership; no double-free. */
        s=packet(0,0);u8 *original_data=s->data;cow_fail=1;old_frees=frees;
        ret=bus==1 ? sc2355_pcie_hif_fill_msdu_dscr(&v,s,SPRD_TYPE_CMD,0)
                   : sc2355_hif_fill_msdu_dscr(&v,s,SPRD_TYPE_CMD,0);
        assert(ret==-ENOMEM && s->data==original_data && frees==old_frees);
        kfree_skb(s);
        s=packet(0,0);old_frees=frees;queued=0;
        assert(sprd_xmit_data2cmd_wq(s,&dev)==-EPERM);
        assert(frees==old_frees+1 && !queued);
    }
    return 0;
}
''')
