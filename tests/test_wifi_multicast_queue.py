"""Run real special-packet filters: IPv6 multicast must retain data-queue flow control."""
import unittest

import test_wifi_tx_retry as retry
from test_wifi_tx_logging import function

WLAN = retry.WLAN

class MulticastQueue(unittest.TestCase):
    run_c = retry.TxRetry.run_c

    def test_multicast_data_and_control_packet_routing(self):
        text = (WLAN / 'tx.c').read_text(encoding='utf-8')
        body = '\n'.join(function(text, name) for name in (
            'tx_mc_pkt', 'tx_filter_ip_pkt', 'sprd_tx_filter_packet',
            'sprd_tx_special_data'))
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <arpa/inet.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <linux/udp.h>
typedef unsigned char u8;
#define __force
#define cpu_to_be16 htons
#define ETHER_HDR_LEN ETH_HLEN
#define SPRD_HW_SC2355_PCIE 1
#define SPRD_HW_SC2355_SDIO 2
#define SPRD_MODE_AP 3
#define SPRD_MODE_P2P_GO 4
#define SPRD_MODE_STATION 5
#define SPRD_CIPHER_NONE 0
#define SPRD_NPI_NORMAL_ALL 0
#define SPRD_NPI_NORMAL_UNENCRYP 1
#define DHCP_SERVER_PORT 67
#define DHCP_CLIENT_PORT 68
#define DHCP_SERVER_PORT_IPV6 547
#define DHCP_CLIENT_PORT_IPV6 546
#define DNS_SERVER_PORT 53
#define CHECKSUM_PARTIAL 1
#define CHECKSUM_NONE 0
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 16
#define WAPI_TYPE 0x88b4
#define pr_info(...) ((void)0)
#define pr_debug(...) ((void)0)
#define spin_lock_bh(...) ((void)0)
#define spin_unlock_bh(...) ((void)0)
struct sprd_peer_entry { int ip_acquired,ba_tx_done_map,vowifi_enabled,vowifi_pkt_cnt; };
struct sprd_hif { int hw_type; u8 skb_da[ETH_ALEN]; struct sprd_peer_entry peer_entry[8]; };
struct sprd_priv { struct sprd_hif hif; };
struct sprd_vif { struct sprd_priv *priv; int mode,prwise_crypto; };
struct net_device { struct sprd_vif *vif; };
struct sk_buff { u8 *data; int len,ip_summed; uint16_t protocol; };
static struct { int adap_lock,special_data_flag; } adap_info;
static int commands,mc_checksum_calls;
static bool vowifi_command;
static void *netdev_priv(struct net_device *d) { return d->vif; }
static int tx_is_multicast_mac_addr(const u8 *p) { return p[0]!=0xff && (p[0]&1); }
static int tx_mc_pkt_checksum(struct sk_buff *s,struct net_device *d) {
    mc_checksum_calls++; return 0;
}
static int sprd_xmit_data2cmd_wq(struct sk_buff *s,struct net_device *d) {
    commands++; return 0;
}
static bool sc2355_is_group(const u8 *p) { return p[0]&1; }
static u8 sc2355_find_lut_index(struct sprd_hif *h,struct sprd_vif *v) {
    return sc2355_is_group(h->skb_da) ? 4 : 6;
}
#define sc2355_pcie_find_lut_index sc2355_find_lut_index
static bool sc2355_is_vowifi_pkt(struct sk_buff *s,bool *cmd) {
    *cmd=vowifi_command; return vowifi_command;
}
static void sc2355_vowifi_data_protection(struct sprd_vif *v) {}
static int ip_hdrlen(struct sk_buff *s) { return 20; }
static unsigned int tx_do_csum(const unsigned char *p,int len) { return 0xffff; }
static void dev_kfree_skb(struct sk_buff *s) { assert(!"unexpected drop"); }
''' + body + r'''
int main(void) {
    struct sprd_priv priv = {0};
    struct sprd_vif vif = {&priv,SPRD_MODE_AP,0};
    struct net_device dev = {&vif};
    unsigned char storage[386] __attribute__((aligned(16))),before[384];
    unsigned char *packet=storage+2;
    struct sk_buff skb = {packet,sizeof(before),CHECKSUM_PARTIAL,htons(ETH_P_IPV6)};
    struct ethhdr *eth=(void *)packet;
    struct ipv6hdr *ip6=(void *)(packet+ETH_HLEN);
    struct udphdr *udp=(void *)(packet+ETH_HLEN+sizeof(*ip6));
    priv.hif.hw_type=SPRD_HW_SC2355_PCIE;
    for (int i=0;i<8;i++) priv.hif.peer_entry[i].ip_acquired=1;
    for (int source=0;source<2;source++)
    for (int mode=SPRD_MODE_AP;mode<=SPRD_MODE_STATION;mode++)
    for (int proto=0;proto<4;proto++) {
        memset(packet,0,sizeof(before));
        eth->h_dest[0]=source ? 0x02 : 0x33;
        eth->h_proto=htons(ETH_P_IPV6);
        ip6->version=6;
        ip6->nexthdr=(int[]){IPPROTO_UDP,IPPROTO_TCP,IPPROTO_ICMPV6,0}[proto];
        udp->source=htons(5353); udp->dest=htons(5353);
        vif.mode=mode;commands=mc_checksum_calls=0;
        skb.ip_summed=CHECKSUM_PARTIAL;
        memcpy(before,packet,sizeof(before));
        assert(sprd_tx_special_data(&skb,&dev)==1);
        assert(commands==0 && mc_checksum_calls==0);
        assert(skb.ip_summed==CHECKSUM_PARTIAL);
        assert(!memcmp(before,packet,sizeof(before)));
    }
    // DHCPv6, VoWiFi and EAPOL retain their control-plane command routes.
    vif.mode=SPRD_MODE_AP;
    ip6->nexthdr=IPPROTO_UDP;eth->h_dest[0]=0x33;
    for (int port=546;port<=547;port++) {
        udp->source=htons(port);commands=0;skb.ip_summed=CHECKSUM_NONE;
        assert(sprd_tx_special_data(&skb,&dev)==NETDEV_TX_OK && commands==1);
    }
    vowifi_command=true;udp->source=udp->dest=htons(4500);commands=0;
    assert(sprd_tx_special_data(&skb,&dev)==NETDEV_TX_OK && commands==1);
    vowifi_command=false;
    skb.protocol=htons(ETH_P_PAE);commands=0;
    assert(sprd_tx_special_data(&skb,&dev)==NETDEV_TX_OK && commands==1);
    // SDIO's existing multicast workaround is deliberately preserved.
    skb.protocol=htons(ETH_P_IPV6);udp->source=udp->dest=htons(5353);
    priv.hif.hw_type=SPRD_HW_SC2355_SDIO;commands=mc_checksum_calls=0;
    assert(sprd_tx_special_data(&skb,&dev)==NETDEV_TX_OK);
    assert(commands==1 && mc_checksum_calls==1);
    return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
