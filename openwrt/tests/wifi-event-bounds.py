#!/usr/bin/env python3
"""Compile the real event callback/channel checks; no wireless hardware needed."""
from pathlib import Path
import runpy
import subprocess
import tempfile

TOP = Path(__file__).resolve().parents[2]


def function(text, name):
    start = text.index(name + '(')
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[brace + 1:end - 1]


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    adapter = TOP / 'devices/common/wifi-events.py'
    if adapter.exists():
        base = tmp / 'drivers/unisoc_platform/sprd_wlan_combo'
        (base / 'common').mkdir(parents=True)
        (base / 'sc2355').mkdir()
        (base / 'common/cfg80211.c').write_text('''int sprd_cfg80211_mgmt_tx(void) {
struct ieee80211_channel *chan = params->chan;
\t*cookie = ++mgmt_index;
}''')
        (base / 'sc2355/cmdevt.c').write_text('''void cmdevt_report_new_station_evt(void) {
struct evt_new_station *sta = (struct evt_new_station *)data;
\tsprd_report_softap(vif, sta->is_connect, sta->mac, sta->ie,
\t\t\t   sta->ie_len);
}''')
        apply = runpy.run_path(str(adapter))['apply']
        apply(tmp)
        before = {p: p.read_bytes() for p in base.rglob('*.c')}
        apply(tmp)
        assert all(p.read_bytes() == data for p, data in before.items())
    else:
        base = TOP / 'upstream/modules/sprd_wlan_combo'
    event = function((base / 'sc2355/cmdevt.c').read_text(), 'cmdevt_report_new_station_evt')
    mgmt = function((base / 'common/cfg80211.c').read_text(), 'sprd_cfg80211_mgmt_tx')
    # Exercise exactly the pre-cookie checks, without mocking the transmit path.
    checks = mgmt[mgmt.index('if (!chan)'):mgmt.index('*cookie = ++mgmt_index;')]
    code = r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
#include <stddef.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,18,54)
#define NL80211_IFTYPE_AP 1
#define NL80211_IFTYPE_P2P_GO 2
#define le16_to_cpu(x) (x)
struct sprd_vif { int unused; };
struct evt_new_station { u8 is_connect, mac[6]; u16 ie_len; u8 ie[]; } __attribute__((packed));
static int calls, last_len;
static void sprd_report_softap(struct sprd_vif *v, int connected, u8 *mac, u8 *ies, int len)
{ (void)v; (void)connected; (void)mac; (void)ies; calls++; last_len = len; }
static void event(struct sprd_vif *vif, u8 *data, u16 len) { EVENT }
struct ieee80211_channel { int freq; };
struct wireless_dev { int iftype, valid_links;
 struct { struct { struct { struct ieee80211_channel *chan; } chandef; } ap; } links[1]; };
struct params { bool offchan; int link_id; };
static int channel(struct wireless_dev *wdev, struct params *params, struct ieee80211_channel *chan)
{ CHECKS return chan->freq; }
int main(void) {
 unsigned char buf[64] = {0}; struct evt_new_station *s = (void *)buf;
 for (int i=0; i<7; i++) { event(NULL, buf, i); assert(calls==0); }
 event(NULL,buf,7); assert(calls==1 && last_len==0);
 s->is_connect=1;
 for(int i=0;i<9;i++) { event(NULL,buf,i); assert(calls==1); }
 s->ie_len=65535; event(NULL,buf,64); assert(calls==1);
 s->ie_len=56; event(NULL,buf,64); assert(calls==1);
 s->ie_len=55; event(NULL,buf,64); assert(calls==2 && last_len==55);
 s->ie_len=0; event(NULL,buf,9); assert(calls==3 && last_len==0);
 struct ieee80211_channel c = {5180}; struct wireless_dev w = {.iftype=1}; struct params p={0};
 assert(channel(&w,&p,NULL)==-ENODATA);
 w.links[0].ap.chandef.chan=&c; assert(channel(&w,&p,NULL)==5180);
 p.offchan=1; assert(channel(&w,&p,NULL)==-EINVAL); p.offchan=0;
 p.link_id=1; assert(channel(&w,&p,NULL)==-EINVAL); p.link_id=0;
 w.valid_links=1; assert(channel(&w,&p,NULL)==-EINVAL); w.valid_links=0;
 w.iftype=0; assert(channel(&w,&p,NULL)==-EINVAL);
 w.iftype=2; assert(channel(&w,&p,NULL)==5180);
 assert(channel(&w,&p,&c)==5180);
}
'''.replace('EVENT', event).replace('CHECKS', checks)
    cfile = tmp / 'test.c'
    cfile.write_text(code)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(cfile), '-o', str(tmp / 'test')], check=True)
    subprocess.run([str(tmp / 'test')], check=True)
print('SC2355 event bounds/channel checks passed (compiled C; no hardware)')
