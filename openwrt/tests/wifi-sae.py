#!/usr/bin/env python3
"""Exercise actual SAE bridge C code, wire encoding and generated AP policy.

Linux + cc; no device access. Also copied to the MU300 repository.
"""
from pathlib import Path
import os
import subprocess
import tempfile

TOP = Path(__file__).resolve().parents[2]
WIFI = TOP / 'openwrt'
driver = TOP / 'devices/common/wifi-sae.h'
if not driver.exists():
    driver = TOP / 'upstream/modules/sprd_wlan_combo/sc2355/sae.h'

NATIVE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint16_t __le16;
#define __packed __attribute__((packed))
#define cpu_to_le16(x) ((uint16_t)(x))
#define SPRD_EXTEND_SOATAP_WPA3 64
#define SPRD_CAPA_AP_SME 8
#define SPRD_STD_11W 64
#define SPRD_SAE_PASSWORD_ENTRY 2
#define CMD_SET_SAE_PARAM 85
#define WLAN_AKM_SUITE_SAE 0x000fac08u
#define WLAN_AKM_SUITE_FT_OVER_SAE 0x000fac09u
#define NL80211_SAE_PWE_HASH_TO_ELEMENT 2
#define NL80211_SAE_PWE_BOTH 3
struct cfg80211_crypto_settings { int n_akm_suites; uint32_t akm_suites[3];
 const u8 *sae_pwd; int sae_pwd_len, sae_pwe; };
struct cfg80211_ap_settings { struct cfg80211_crypto_settings crypto; };
struct sprd_priv { int extend_feature, fw_capa, fw_std; };
struct sprd_vif { int unused; };
struct sprd_msg { void *data; };
static int sent, alloc_fail, send_rc;
static unsigned char wire[100];
static size_t wire_len;
static struct sprd_msg message;
static struct sprd_msg *get_cmdbuf(struct sprd_priv *p,struct sprd_vif *v,size_t n,int id) {
 assert(id==85); if(alloc_fail)return NULL;
 message.data=malloc(n);assert(message.data);memset(message.data,0xa5,n);wire_len=n;return &message;
}
static int send_cmd_recv_rsp(struct sprd_priv *p,struct sprd_msg *m,void *r,void *len) {
 assert(wire_len<=sizeof(wire));memcpy(wire,m->data,wire_len);free(m->data);sent++;return send_rc;
}
#include "driver.h"
int main(void) {
 struct sprd_priv p={64,8,64};struct sprd_vif v={0};
 struct cfg80211_ap_settings a={.crypto={.n_akm_suites=1,.akm_suites={0x000fac08},.sae_pwd_len=8}};
 unsigned char password[64];memset(password,0x71,sizeof(password));a.crypto.sae_pwd=password;
 for(int n=1;n<=63;n++) {
  a.crypto.sae_pwd_len=n;assert(sc2355_prepare_sae(&p,&v,&a)==0);
  /* Android ABI: request2, ENTRY(type0,len0), PWD(type7,lenN), END(type255,len0). */
  assert(wire_len==(size_t)(14+n));
  assert(!memcmp(wire,"\x02\0\0\0\0\0\x07\0",8));
  assert(wire[8]==n && wire[9]==0 && !memcmp(wire+10,password,n));
  assert(!memcmp(wire+10+n,"\xff\0\0\0",4));
 }
 assert(sent==63);
 a.crypto.sae_pwd_len=64;assert(sc2355_prepare_sae(&p,&v,&a)==-EINVAL);
 a.crypto.sae_pwd_len=0;assert(sc2355_prepare_sae(&p,&v,&a)==-EINVAL);
 a.crypto.sae_pwd_len=8;a.crypto.sae_pwd=NULL;assert(sc2355_prepare_sae(&p,&v,&a)==-EINVAL);
 a.crypto.sae_pwd=password;
 p.extend_feature=0;assert(sc2355_prepare_sae(&p,&v,&a)==-EOPNOTSUPP);p.extend_feature=64;
 p.fw_capa=0;assert(sc2355_prepare_sae(&p,&v,&a)==-EOPNOTSUPP);p.fw_capa=8;
 p.fw_std=0;assert(sc2355_prepare_sae(&p,&v,&a)==-EOPNOTSUPP);p.fw_std=64;
 for(int n=2;n<=3;n++){a.crypto.sae_pwe=n;assert(sc2355_prepare_sae(&p,&v,&a)==-EOPNOTSUPP);}
 a.crypto.sae_pwe=0;a.crypto.akm_suites[0]=0x000fac09;assert(sc2355_prepare_sae(&p,&v,&a)==-EOPNOTSUPP);
 a.crypto.akm_suites[0]=0x000fac02;assert(sc2355_prepare_sae(&p,&v,&a)==0 && sent==63);
 a.crypto.akm_suites[1]=0x000fac08;a.crypto.n_akm_suites=2;
 alloc_fail=1;assert(sc2355_prepare_sae(&p,&v,&a)==-ENOMEM);alloc_fail=0;
 send_rc=-EIO;assert(sc2355_prepare_sae(&p,&v,&a)==-EIO && sent==64);
 /* Real mixed mode carries PSK, PSK-SHA256 and SAE, not just two suites. */
 send_rc=0;a.crypto.n_akm_suites=3;
 a.crypto.akm_suites[1]=0x000fac06;a.crypto.akm_suites[2]=0x000fac08;
 assert(sc2355_prepare_sae(&p,&v,&a)==0 && sent==65);
}
'''

HOST = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char u8;
#define CONFIG_SAE 1
#define SAE_PMK_LEN 32
#define PMKID_LEN 16
#define WPA_KEY_MGMT_SAE 8
#define WPA_KEY_MGMT_PSK 2
#define WPA_CAPABILITY_MFPC 128
#define WPA_DRIVER_FLAGS2_SAE_OFFLOAD_AP 1
#define WLAN_EID_RSN 48
#define WLAN_AUTH_OPEN 0
#define WLAN_AUTH_SAE 3
#define SAE_ACCEPTED 3
#define os_memcpy memcpy
static int alloc_fail, cache_fail, cache_valid, added, alg, pmkid_set;
static void *os_zalloc(size_t n){return alloc_fail?NULL:calloc(1,n);}
static void bin_clear_free(void *p,size_t n){memset(p,0,n);free(p);}
struct sae_data { u8 pmk[64],pmkid[16];size_t pmk_len;int akmp,state; };
struct wpa_ie_data { int key_mgmt,capabilities,num_pmkid;const u8 *pmkid; };
static struct wpa_ie_data parsed={8,128,0,NULL};
struct rsn_pmksa_cache_entry { int akmp; size_t pmk_len;u8 pmk[32],pmkid[16]; };
static struct rsn_pmksa_cache_entry cache;
struct configuration { int unisoc_sae,wpa_key_mgmt,disable_pmksa_caching; };
struct interface { int drv_flags2; };
struct hostapd_data { struct configuration *conf;struct interface *iface;void *wpa_auth; };
struct sta_info { u8 addr[6];struct sae_data *sae;int auth_alg,vlan_id;void *wpa_sm; };
static const u8 *get_ie(const u8 *p,size_t len,int id) {
 for(size_t i=0;i+2<=len;) {size_t n=p[i+1]+2;if(n>len-i)return NULL;if(p[i]==id)return p+i;i+=n;}return NULL;
}
static const u8 *get_vendor_ie(const u8 *p,size_t len,uint32_t id) {
 for(size_t i=0;i+2<=len;) {size_t n=p[i+1]+2;if(n>len-i)return NULL;
 if(p[i]==221 && n>=6 && (((uint32_t)p[i+2]<<24)|((uint32_t)p[i+3]<<16)|((uint32_t)p[i+4]<<8)|p[i+5])==id)return p+i;i+=n;}return NULL;
}
static int wpa_parse_wpa_ie_rsn(const u8 *p,size_t len,struct wpa_ie_data *out){*out=parsed;return 0;}
static struct rsn_pmksa_cache_entry *wpa_auth_pmksa_get(void *a,const u8 *s,const u8 *id){return cache_valid&&!memcmp(id,cache.pmkid,16)?&cache:NULL;}
static int wpa_auth_pmksa_add_sae(void *a,const u8 *s,const u8 *pmk,size_t len,const u8 *id,int akm,bool ml,int vlan) {
 if(cache_fail)return -1;assert(len==32 && akm==8 && !ml);memcpy(cache.pmk,pmk,32);memcpy(cache.pmkid,id,16);
 cache.pmk_len=len;cache.akmp=akm;cache_valid=1;added++;return 0;
}
static void sae_clear_data(struct sae_data *p){}
static void wpa_auth_set_auth_alg(void *s,int n){alg=n;}
static void wpa_auth_add_sae_pmkid(void *s,const u8 *id){pmkid_set++;}
#include "host.h"
static void clear(struct sta_info *s){if(s->sae){bin_clear_free(s->sae,sizeof(*s->sae));s->sae=NULL;}}
int main(void) {
 struct configuration c={1,8,0};struct interface f={1};struct hostapd_data h={&c,&f,NULL};struct sta_info sta={0};
 u8 ie[128]={48,0,221,52,0x40,0x45,0xda,4};for(int i=0;i<48;i++)ie[8+i]=(u8)(i+1);
 assert(unisoc_sae_import(&h,&sta,ie,56)==0 && sta.auth_alg==3 && alg==3 && added==1 && pmkid_set==1);
 assert(sta.sae->pmk_len==32 && !memcmp(sta.sae->pmk,ie+8,32) && !memcmp(sta.sae->pmkid,ie+40,16));
 parsed.num_pmkid=1;parsed.pmkid=ie+40;
 assert(unisoc_sae_import(&h,&sta,ie,2)==0); /* Genuine cached reassociation. */
 cache_valid=0;assert(unisoc_sae_import(&h,&sta,ie,2)<0);
 parsed.num_pmkid=0;clear(&sta);
 for(int n=0;n<54;n++)assert(unisoc_sae_import(&h,&sta,ie,2+n)<0);
 ie[3]=51;assert(unisoc_sae_import(&h,&sta,ie,56)<0);ie[3]=52;
 memcpy(ie+56,ie+2,54);assert(unisoc_sae_import(&h,&sta,ie,110)<0);
 parsed.capabilities=0;assert(unisoc_sae_import(&h,&sta,ie,56)<0);parsed.capabilities=128;
 f.drv_flags2=0;assert(unisoc_sae_import(&h,&sta,ie,56)<0);f.drv_flags2=1;
 alloc_fail=1;assert(unisoc_sae_import(&h,&sta,ie,56)<0);alloc_fail=0;
 cache_fail=1;assert(unisoc_sae_import(&h,&sta,ie,56)<0);cache_fail=0;
 c.disable_pmksa_caching=1;int before=added;
 assert(unisoc_sae_import(&h,&sta,ie,56)==0 && added==before);
 /* A spoofed firmware IE on a WPA2 reassociation cannot supply its PSK. */
 parsed.key_mgmt=2;assert(unisoc_sae_import(&h,&sta,ie,56)==0 && !sta.sae && sta.auth_alg==0 && alg==0 && added==before);
 parsed.key_mgmt=8;c.unisoc_sae=0;assert(unisoc_sae_import(&h,&sta,ie,56)==0 && !sta.sae);
 clear(&sta);
}
'''


def compile_and_run(directory, name, code):
    source = directory / (name + '.c')
    source.write_text(code)
    binary = directory / name
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-misleading-indentation',
                    '-fsanitize=address,undefined', '-g', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


with tempfile.TemporaryDirectory(prefix='unisoc-sae-') as directory:
    d = Path(directory)
    (d / 'driver.h').write_bytes(driver.read_bytes())
    (d / 'host.h').write_bytes((WIFI / 'hostapd-unisoc-sae.h').read_bytes())
    (d / 'pmksa_cache_auth.h').write_text('/* mocked cache API above */\n')
    compile_and_run(d, 'native', NATIVE)
    compile_and_run(d, 'host', HOST)

    shell = d / 'policy.sh'
    shell.write_text('''set -eu
. "$1"
auth_type="$2"; ieee80211w="$3"; sae_pwe="$4"; test_module="$5"
phy=phy0; bss_conf=; N='|'
readlink() { printf '%s\\n' "$test_module"; }
append() { bss_conf="${bss_conf}${2}|"; }
set_default() { eval "case \\"\\${$1-}\\" in '') $1=\\\"\\$2\\\" ;; esac"; }
unisoc_sae_bss_options
printf '%s/%s/%s' "$ieee80211w" "$sae_pwe" "$bss_conf"
''')
    cases = [('sae', '0', '', 'sprd_wlan_combo', '2/0/unisoc_sae=1|'),
             ('sae', '1', '', 'sprd_wlan_combo', '2/0/unisoc_sae=1|'),
             ('sae-missing', '', '', 'sprd_wlan_combo', '//'),
             ('sae', '', '', 'sprd_wlan_combo', '/0/unisoc_sae=1|'),
             ('psk-sae', '0', '', 'sprd_wlan_combo', '1/0/unisoc_sae=1|'),
             ('psk-sae', '2', '1', 'sprd_wlan_combo', '2/1/unisoc_sae=1|'),
             ('psk', '0', '', 'sprd_wlan_combo', '0//'),
             ('sae', '0', '', 'mt76', '2//'),
             ('psk-sae', '0', '', 'mt76', '1//')]
    for auth, pmf, pwe, module, expected in cases:
        actual = subprocess.check_output(['sh', str(shell), str(WIFI / 'hostapd-unisoc.sh'),
                                          auth, pmf, pwe, '/drivers/' + module], text=True)
        assert actual == expected, (auth, pmf, actual, expected)

print('PASS: SAE wire ABI, 1..63-byte passwords, capability/error paths, PMK/PMKID import, '
      'all truncated indications, duplicate keys, PMF, PMKSA reuse, WPA2 transition and non-Unisoc isolation')
