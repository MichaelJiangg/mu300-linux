# VoWiFi (Wi-Fi calling) on Linux: feasibility study

Date: 2026-10-11. Status: research only. Nothing was implemented and the modem received no set commands.

Boards: U30 Air (OpenWrt 25.12.5, kernel 7.2.9, Vodafone TR SIM, PLMN 286/02, IMS-registered over LTE:
`+CIREG:0,1,0`, `+CAVIMS:1`, `+CEVDP:3`). F50-B (192.168.79.1) did not answer ssh during this study, so the
Android side was read from the U30 Air's full eMMC backup (`backup/u30air-20260927-205614/super.img.gz`, slot `_a`,
EROFS partitions unpacked with a small LP-metadata parser plus `fsck.erofs --extract`). The F50 build is the same
ZTE/Unisoc UMS9620 MBB base. The Linux-side Android subset under `/opt/mu300/android` holds only what
`modem_control` needs, so it contains no IMS or VoWiFi files.

## Summary

**The modem already has a complete VoWiFi client.** Unisoc offers two VoWiFi designs. In "AP VoWiFi", the
`com.spreadtrum.vowifi*` apps do IKEv2 and SIP on the application processor. In "CP VoWiFi", also called "single
IMS stack", the modem firmware does ePDG discovery, IKEv2, EAP-AKA against the SIM, ESP and the IMS registration
over Wi-Fi. The AP only carries packets between the modem and `wlan0` through the `ims_bridge` driver, and steers
the modem with a handful of AT commands. These boards use CP VoWiFi (`persist.vendor.sys.single.imsstack=true`),
and the `nr_modem` firmware contains the IKEv2, EAP-AKA and ePDG code. ZTE switched the feature off on the Android
side.

**Recommendation: GO for a time-boxed proof of concept, on two tracks.**
- **Track 1** is a Linux-side SWu tunnel with strongSwan plus a small EAP-AKA card plugin that uses AT+CSIM. It
  proves that the carrier accepts this SIM and device over Wi-Fi, and it is mostly standard, documented
  technology.
- **Track 2** is the product path: re-enable the modem's own CP VoWiFi by reimplementing the AP half (the
  `ims_bridge` relay plus the AT control sequence). If it works, calls and SMS keep using the modem's IMS stack
  and the audio path that `mu300-voice` already drives.

A Linux IMS client (doubango, baresip or similar) is a NO-GO as the product: it duplicates what the modem already
does, and IMS sec-agree, AMR-WB/EVS and emergency handling would turn it into a project of several months.

## 1. How VoWiFi works on these Unisoc Android builds

### 1.1 What is on the image (U30 Air backup, slot a)

| Item | Where | Meaning |
|---|---|---|
| `persist.vendor.sys.single.imsstack=true` | `vendor/build.prop` | Selects **CP VoWiFi**. In `ims.apk` the constant `PROP_KEY_CP_VOWIFI` is exactly this property (seen with `dexdump`). |
| `persist.sys.wfc.supp_dual_sim=true` | `vendor/build.prop` | Wi-Fi calling (WFC) supported on dual SIM |
| `gsm.sys.vowifi.state=[0,0]`, `gsm.sys.volte.state=[1,0]` | runtime getprop | VoLTE is on, VoWiFi is off |
| `vendor/etc/init/vowifi.rc` | vendor | Only maps `persist.sys.vowifi.whitelist` / `persist.sys.vowifi.lab.sim` to `persist.dbg.wfc_avail_ovr` (the WFC availability override) |
| `vendor/etc/init/hw/init.vendor.rc:72` | vendor (ZTE) | `# disable vowifi service` / `stop srmi_proxyd` |
| `system_ext/priv-app/ims/ims.apk` (`com.spreadtrum.ims`) | system_ext | IMS service; holds both the AP-VoWiFi glue (`com.spreadtrum.ims.vowifi.*`) and the CP-VoWiFi glue (`com.spreadtrum.ims.n3am.vowifi.*`, `IwlanDataService`, `WFCStateMonitorService`) |
| `system_ext/bin/srmi_proxyd`, `priv-app/Srmi`, `libsrmi*.so` | system_ext | "SRMI", a generic message pipe between the modem and the AP (`ro.vendor.modem.srmi.read`). `ims.apk` uses it through `n3am/srmi/SrmiManager`. |
| `system_ext/lib64/libimsbrd.so` | system_ext | Userspace control of the IMS bridge over netlink: `imsbrd_add_spi`/`del_spi`, `add_tuple`, `get_oseq_by_spi`, `set_callstate`, `set_lp_state` |
| `vendor_dlkm/lib/modules/ims_bridge.ko` | vendor_dlkm | Kernel `sprd-imsbr`: relays packets between the modem (SIPC sblock channels 2 "imsbr data" and 3 "imsbr control") and the AP network stack |
| `com.android.ipsec.capex` (Android IKE library) | system | Present but unused: no AOSP Iwlan app (`com.google.android.iwlan`) is installed |
| `com.spreadtrum.vowifi`, `com.spreadtrum.vowifi.sec` (AP VoWiFi service, S2b "SecurityService") | **absent** | `ims.apk` binds to them only in AP-VoWiFi mode |

Android also creates `vowifi_tun0` and `vowifi_tun1` (see `docs/reference/android-ipa-state.txt`). They carried
0 bytes, which fits with VoWiFi being off.

Strings in `ims_bridge.ko` show how the data path works: `this is ike packet !!!`,
`output skb=%p is ike pkt, go to wlan0`, `imsbr_packet_relay2cp`, `input skb=%p relay to cp`,
`output spi %x matched, update seq to %d`, `xfrm_lookup_fail`, `cptuple-add`, `call switch to [%s] ... ho=%s->%s`,
`ho-wifi2lte`, and `version conflict! AP is %u but CP is %u!`. From these: the modem generates the IKE and ESP
traffic itself, and the AP sends it out of `wlan0`. Packets that match a "cptuple" or an ESP SPI come back in from
Wi-Fi and are relayed to the modem. The AP tracks ESP sequence numbers so that the two sides can hand a call over.

### 1.2 What is inside the modem firmware (`nr_modem_a`)

The firmware has a full ePDG client:

- ePDG FQDN templates `epdg.epc.mnc[MNC].mcc[MCC].pub.3gppnetwork.org` and
  `%s%s.mnc%03d.mcc%03d.pub.3gppnetwork.org`, plus NV/config keys `epdg_hplmn_addr`, `epdg_vplmn_addr`,
  `epdg_static_addr`, `epdg_prior_ipv4`, `epdg_apn_ims|ss|mms|sos`, `epdg_cached`, `epdg_last_used_addr` and
  `IKE_EPDG_CONFIG`. It also parses 5G URSP "N3AN node selection" (`HOME_EPDG_ID_CFG`).
- Identity `0[IMSI]@nai.epc.mnc[MNC].mcc[MCC].3gppnetwork.org` and `IKE: generate idi failed, fmt %s, imsi %s`.
- An EAP-AKA and EAP-AKA' state machine (`EapAkaIdleOnEapAkaChlgMsg`, re-auth, sync failure) and IKE sessions
  with MOBIKE (`Ike_processMobikeReq`).
- Connection-manager states `CmcpStateVowifiEnable`, `CmcpStateVowifiPdn`, `CmcpStateHoVowifiPending`, plus
  `CMCP_SIG_HO_TO_VOWIFI_IND` and `APP_MN_VOWIFI_IMS_ATTACH_STATE_IND`.

### 1.3 AT commands (strings in the RIL `libimpl-ril.so`/`librilcore.so` and the modem's AT table)

| Command | Seen as | Probe on U30 Air (read and test forms only) | Probable role |
|---|---|---|---|
| `AT+VOWIFIEN=%d` | RIL | `?` gives CME ERROR 4; `=?` gives `+VOWIFIEN:(0-1)` | enable CP VoWiFi |
| `AT+IMSHOWFINF=%d,"%s"` | RIL | `?` gives ERR 4; `=?` gives `+IMSHOWFINF:(1-6),()` | Wi-Fi state (1-6) plus info string (local IP / BSSID) passed to the modem |
| `AT+IMSWFATT=%d` | RIL | `?` gives ERR 4; `=?` gives `+IMSWFATT:(0-255)` | start or stop the S2b attach over Wi-Fi |
| `+IKEATTU:%d,"%s"[,%d]` | RIL/modem URC | – | IKE attach progress or result (unsolicited) |
| `AT+IKEATT` | modem table, `(0,1),("MMS","mms")` | `=?` gives CME ERROR 65536014 | attach a second ePDG PDN (MMS) |
| `AT+VOWFREG=%d` | RIL | `?` gives ERR 4; `=?` gives `+VOWFREG:(0-255)` | IMS registration over Wi-Fi |
| `AT+VOWIFIPCSCF=%s` | RIL | `?` gives ERR 4 | P-CSCF for the Wi-Fi registration |
| `AT+IMSHO=%d` / `+IMSHO:` / `+IMSHOU` | RIL | `?`/`=?` give ERR 4 | LTE to Wi-Fi handover |
| `AT+IMSHONWINF?` | RIL | **`+IMSHONWINF: 4,28602c3000e07f53,9`** | current network info (PLMN 28602, TAC C300, cell 00E07F53) |
| `AT+IMSHORST`, `+IMSHORSTU`, `+IMSHOLTEINFU`, `AT+IMSHOCALLEND` | RIL | – | handover reset, LTE info and call-end notifications |
| `AT+IMSHODATAROUTER=1` | RIL | `=?` gives `+IMSHODATAROUTER:()` | switch the media data router (the `ims_bridge` path) |
| `AT+WIFIPARAM=%d,0,0,0,0` | RIL | `=?` gives 11 fields | Wi-Fi quality (RSSI and others) reports for handover decisions |
| `AT+VOWIFCALLINF=%s` | RIL / modem table | – | call info during handover |
| `AT+PCSCF?` | standard | `+PCSCF: 10.138.40.4,10.139.52.68` | current (LTE) P-CSCFs |
| `AT+CSIM`, `AT+CRSM`, `AT+CCHO`, `AT+CGLA` | 27.007 | all `=?` give OK | raw SIM access for an AP-side EAP-AKA |
| `AT+CGDCONT?` | – | cid 11 = `IMS` APN, IPV4V6 | IMS PDN on LTE |

No `AT+SPVOWIFI*` or `AT+SPIMSHO*` names exist. Unisoc uses the unprefixed `+VOWIFI*`, `+IMSHO*` and `+IMSWF*`
family. The CME ERROR 4 replies to `?` most likely mean "read form not supported", not "feature absent", because
the test forms do answer. Nothing in the probe changed any state.

### 1.4 Reconstructed Android flow (CP VoWiFi)

From the `ims.apk` strings (`EVENT_NOTIFY_CP_VOWIFI_ATTACH_SUCCESSED`, `notifyCPVowifiAttachSucceed`,
`handleUpdateDataRouterFinished`, `createCallSession dialEmergencyCall over cpvowifi`,
`Cp VoWiFi solution does not support 'setVoWifiUnavailable'`) and the RIL request names
(`IMS_REQUEST_WIFI_ENABLE`, `IMS_REQUEST_HANDOVER`, `IMS_REQUEST_SET_PCSCF_ADDR`,
`IMS_REQUEST_ENABLE_WIFI_PARAM_REPORT`, `IMS_UNSOL_VOWIFI_ATTACH_STATE_CHANGED`), the flow is:

1. The user enables WFC, so `ims.apk` sends `AT+VOWIFIEN=1`, then `AT+WIFIPARAM=1,...` to turn on quality reports.
2. Wi-Fi connects. `AT+IMSHOWFINF=<state>,"<wifi info>"` tells the modem that Wi-Fi is usable, and `libimsbrd`
   programs `ims_bridge` (the local Wi-Fi address, the MACs and the call state).
3. `AT+IMSWFATT=<type>` starts the attach. The modem resolves the ePDG, runs IKEv2 and EAP-AKA against its own
   SIM, and sends the IKE packets through `ims_bridge` out of `wlan0`. The result comes back as `+IKEATTU`.
4. `ims_bridge` installs ESP SPIs and tuples, and `AT+VOWFREG` / `AT+VOWIFIPCSCF` register IMS through the tunnel.
   Handover uses `AT+IMSHO`, `+IMSHOU`, `AT+IMSHODATAROUTER=1` and `AT+VOWIFCALLINF`.
5. SRMI (`srmi_proxyd`) carries the modem's requests to the AP. ZTE stops `srmi_proxyd`, so the modem cannot ask
   the AP for anything, and VoWiFi never starts.

The exact argument values in steps 1-4 are not known yet. Getting them is Track 2, phase 2a.

## 2. What Linux would need

### 2.1 Track 2: re-enable the modem's own VoWiFi (product path)

- **The data path.** Linux already exposes both IMS-bridge SIPC channels to userspace. The DT nodes
  `/sipc-virt/core@5/channel@2` and `channel@3` (labels `imsbr_data` and `imsbr_ctrl`) are bound to the generic
  `sprd,spool` driver, which shows up as `/dev/imsbr_data` and `/dev/imsbr_ctrl` (char 502:0 and 501:0). Two ways
  to drive them:
  - (a) Port `ims_bridge.ko` to the 7.2 kernel. It is GPL, so the source is in Unisoc's 5.4 kernel trees (the path
    is `net/ims_bridge/`, from the module strings `net/ims_bridge/imsbr_sipc.c` and `imsbr_netlink.c`) and in
    OEM GPL releases. The DT channels would then move from `spool` to it.
  - (b) Write a userspace relay that reads and writes the spool devices and uses raw sockets / nftables on `wlan0`.
    Option (a) is the faithful one, because the protocol (packet headers, the AP and CP version handshake) lives
    in that source. Option (b) needs the same knowledge, re-coded.
- **The control path.** A small daemon (`mu300-vowifi`) that follows Wi-Fi state and sends the
  `+VOWIFIEN/+IMSHOWFINF/+IMSWFATT/+VOWFREG` sequence through `mu300-at`. It handles `+IKEATTU`, `+IMSHOU` and
  `+IMSHORSTU`, and drives the bridge netlink commands that `libimsbrd` sends (SPI, tuple, call state, MAC).
  SRMI may also be needed: the modem may ask the AP for things such as DNS resolution, the local IP or the Wi-Fi
  state through it. `libsrmi.so` and `srmi_proxyd` are small (28 to 44 KB) and readable, but whether the modem
  needs SRMI in CP mode is still an open question.
- **Wi-Fi in client mode.** For the ePDG to be reachable, `wlan0` (or a second STA interface) must reach the
  internet. The repo's `wifi-client` covers that. The SC2355 Wi-Fi driver already knows about VoWiFi packets
  (`sc2355_is_vowifi_pkt`, `vowifi_enabled` in `upstream/modules/sprd_wlan_combo/sc2355/tx.c`): it marks them for
  QoS and power saving.
- **Audio and SMS.** These do not change. Calls appear as ordinary `+CLCC` calls and audio uses the AGDSP voice
  path that `mu300-voice` already drives. SMS over IMS keeps working the way it does today.

### 2.2 Track 1: Linux-side SWu with strongSwan (proof of concept and diagnostic)

- **strongSwan** is packaged on both systems: Ubuntu `libcharon-extra-plugins` and OpenWrt `strongswan-*`.
  Needed: `eap-aka`, the `p-cscf` plugin (it asks for P-CSCF addresses in the CP payload, RFC 7651,
  `charon.plugins.p-cscf.enable.<conn>=yes`), and `kernel-netlink`.
- **The SIM backend is the gap.** strongSwan's `eap-aka` gets AKA vectors from a `simaka_card_t` provider.
  - `eap-aka-3gpp` and `eap-aka-3gpp2` are *software* Milenage. They need K and OPc, which we do not have, so
    they are unusable with a real SIM.
  - `eap-sim-pcsc` only does GSM triplets (EAP-SIM) through a PC/SC reader, so it does not fit either.
  - What is needed is a new plugin, `eap-aka-atcsim` (about 300-500 lines of C). It implements
    `get_quintuplet()` by sending the USIM AUTHENTICATE APDU through `AT+CSIM`:
    `00 88 00 81 22 10<RAND> 10<AUTN>`, then `GET RESPONSE`, which returns `DB` RES/CK/IK or `DC` AUTS for
    resync. It also implements `resync()` and talks to `mu300-atd` instead of opening the tty. If the USIM's basic
    channel is busy, it can open a logical channel with `AT+CCHO` / `AT+CGLA` on the USIM AID.
  - osmocom's "FOSS IMS client" project wrote an equivalent for its modified strongSwan: an "AKA socket" with
    PC/SC or AT+CSIM providers. It was tested against the T-Mobile DE ePDG.
- **An alternative for the first experiment:** fasferraz's `SWu-IKEv2` (Python 3, GPL-3.0). It already gets
  RES/CK/IK from "a USB modem supporting AT+CSIM", a PC/SC reader or an HTTPS helper, and brings the tunnel up on a
  TUN device. Pointing it at a small `mu300-at` shim is about one day of work. It is a test tool, not something
  to ship.
- **ePDG discovery** (resolved from the Mac, through the user's VPN):
  - `epdg.epc.mnc002.mcc286.pub.3gppnetwork.org` gives A **217.31.231.85, 217.31.231.69, 217.31.231.77** (no
    AAAA). whois: "VODAFONE TURKEY IP ADDRESS POOL", TR. These IPs do not answer ICMP, which is normal for an ePDG.
  - The two-digit form `mnc02` gives 127.0.0.1: the wildcard has to be avoided, and the three-digit MNC is correct.
  - `sos.epdg...` and `ss.epdg...` return nothing.
  - For comparison, Turkcell (mnc001) and Türk Telekom (mnc003) also publish ePDGs.
- **The IKEv2 profile carriers use:** IDi `0<IMSI>@nai.epc.mnc002.mcc286.3gppnetwork.org` (a `6<IMSI>` prefix for
  EAP-AKA'), IDr = APN `ims`, EAP-AKA with no client certificate. Proposals are usually AES-CBC-128/256 or
  AES-GCM, SHA1/SHA256 and MODP1024/2048. The CP request asks for INTERNAL_IP4/6_ADDRESS, INTERNAL_IP4/6_DNS and
  P_CSCF_IP4/6_ADDRESS. The ePDG authenticates with a certificate (often not verifiable from public CAs, so a test
  leaves it unchecked) or with EAP-only auth (RFC 5998). NAT-T on UDP 4500, MOBIKE optional.
- **Using the tunnel for IMS.** There is no supported way to make the modem's IMS stack use a tunnel that Linux
  owns: it registers only over its own PDNs or its own SWu. A Track 1 tunnel therefore feeds either a Linux IMS
  client or nothing (a pure diagnostic).
  - Linux IMS client: Kamailio is a server, not a UE. UE candidates are a modified doubango (the osmocom work) and
    baresip with IMS AKA patches. All of them need IMS AKA a second time (ISIM or USIM via AT+CSIM), sec-agree
    IPsec to the P-CSCF, AMR-WB (and EVS for HD), and RTP into the AGDSP voice path, which is a modem-side PCM
    path, so packet audio from Linux is a different path again.
  - That is several months of work, and it would still leave emergency calls and handover unsolved.

## 3. Prior art

- **fasferraz/SWu-IKEv2** (GPL-3.0, Python): an IKEv2/IPsec UE toward ePDGs. AKA via AT+CSIM modem, PC/SC or
  HTTPS. Builds a TUN interface. The quickest way to get a tunnel. The same author also has related IMS and S2b
  test tools.
- **osmocom FOSS IMS client** (`projects/foss-ims-client`): modified strongSwan (SWu with an external USIM over
  the "AKA socket SIM interface", whose providers are pcsc-lite or AT+CSIM) plus modified doubango (IMS REGISTER
  with sec-agree, tested against Kamailio). SWu was established against the T-Mobile DE ePDG.
- **osmocom osmo-epdg** (Erlang plus modified strongSwan): the network side. Useful for building a lab ePDG to
  test against without the carrier.
- **strongSwan**: `eap-aka`, `eap-aka-3gpp` (software Milenage), `eap-sim-pcsc` (triplets only) and `p-cscf`.
  Mailing-list threads (2015-2016) ask for "EAP-AKA with a real USIM" and none was merged upstream.
- **Unisoc-specific:** no public reverse-engineering of the CP VoWiFi AT and `ims_bridge` interface was found.
  The kernel half is GPL (`sprd-imsbr`) and the AP control half is the closed `libimsbrd`, `ims.apk` and RIL,
  documented in section 1 above.

## 4. Risks

- **Carrier gating (high).** Vodafone TR offers Wi-Fi calling only on approved handsets. Entitlement is usually
  decided per IMEI TAC, sometimes per subscription. The ePDG can still let the tunnel up and then refuse IMS
  registration over Wi-Fi, or refuse at IKE_AUTH with a 3GPP notify such as `NON_3GPP_ACCESS_TO_EPC_NOT_ALLOWED`
  (9000) or `USER_UNKNOWN`. The modem image ships `imsUserAgent.xml` with only Mexican PLMNs, and ZTE disabled the
  feature, so no Vodafone TR VoWiFi profile is likely to be in NV. Phase 1 settles this question cheaply.
- **SIM access concurrency (medium).** AT+CSIM on the basic channel can race with the modem's own USIM and ISIM
  use, and a USIM AUTHENTICATE moves the SIM's SQN forward. Normal SQN window handling (an array of 32 values)
  tolerates this, and a sync failure gets an AUTS resync. Mitigations: use a logical channel (`AT+CCHO`), run AKA
  only during an IKE_AUTH, and go through `mu300-atd` so that no other AT command interleaves.
- **Emergency calls (must not regress).** 112 has to stay on CS or LTE. Track 1 never touches the modem's call
  handling. In Track 2, the modem's own logic (`dialEmergencyCall over cpvowifi`, `KEY_CARRIER_DEREG_VOWIFI_BEFORE_ECALL`)
  decides; default to "cellular preferred" and leave the SOS ePDG unused. An E911-style address entitlement is
  not required in TR.
- **Breaking the working VoLTE and SMS (medium).** Track 2 drives handover state in the modem. A wrong
  `+IMSHO` / `+IMSWFATT` value could deregister IMS until reboot. Use a cellular-preferred mode, test only on the
  U30, and reset with `AT+VOWIFIEN=0` and an IMS re-attach.
- **Battery (U30).** An IKE keepalive and NAT-T keepalive every 20 s, plus Wi-Fi in client mode, plus SIP
  re-registration. Expect a few percent per day while idle. The modem-side path is cheaper than running a Linux
  IMS client.
- **Maintenance.** Track 2 depends on undocumented Unisoc interfaces that could change with a modem firmware
  update (the `ims_bridge` "version conflict AP vs CP" check). Keep the port pinned to the firmware version.
  Track 1 depends only on strongSwan and 3GPP standards.
- **Board rule.** `/etc/mu300/vpn.conf` and the Wi-Fi passphrase stay untouched. VoWiFi in client mode uses its
  own STA config.

## 5. Phased plan

| Phase | Goal | Effort | Exit criterion |
|---|---|---|---|
| **1. SWu tunnel with the real SIM** (Track 1) | IKE_AUTH succeeds against 217.31.231.x and the CP payload returns an inner IP and P-CSCFs | 2-4 days | tunnel up, P-CSCF list logged; or a clean carrier refusal code |
| 2a. Learn the CP-VoWiFi protocol | Get the `ims_bridge` source (Unisoc 5.4 GPL tree or the ZTE F50 GPL release) and decompile `ims.apk` n3am, `libimsbrd` and the RIL argument encodings; optionally capture `logcat -b radio` on an Android unit with `persist.sys.vowifi.lab.sim=true` and `srmi_proxyd` started | 3-5 days | documented AT sequence and bridge message format |
| 2b. Data path on Linux | Port `ims_bridge` to 7.2 and rebind DT channels 2/3, or write a userspace relay | 1-2 weeks | IKE packets from the modem appear on `wlan0` |
| 2c. Control daemon | `mu300-vowifi`: Wi-Fi state, then VOWIFIEN, IMSHOWFINF, IMSWFATT and VOWFREG; URC handling; OpenWrt and Ubuntu packaging | 1 week | `+IKEATTU` reports success, `+CIREG` stays registered with LTE data off, SMS works over Wi-Fi |
| 2d. Calls and handover | Voice over Wi-Fi with `mu300-voice`; LTE↔Wi-Fi handover; check that 112 stays on cellular | 1-2 weeks | MO and MT call on Wi-Fi; 112 test on a test number only |

Total: about 1 week to a go/no-go answer (phases 1 and 2a), then 4-6 weeks for the full Track 2.

**Go/no-go gates:**
- After phase 1: if Vodafone TR refuses the SIM or device at IKE_AUTH or IMS, stop. The modem path would hit the
  same refusal.
- After 2a: if the bridge protocol cannot be recovered (no GPL source, opaque framing), stop Track 2 and leave
  Track 1 as a diagnostic tool.

### Phase 1 in detail (read-only to the modem except the AKA challenge)

1. Use the U30 Air on its normal LTE data, or, in the user's region, through a path where 217.31.231.85:500/4500
   is reachable (see the VPN note in `test-device-access`). Wi-Fi client mode is not needed to prove the tunnel:
   the ePDG accepts IKE from any IP.
2. Build an `mu300-at`-backed AKA helper: `aka RAND AUTN`. It selects the USIM (`AT+CSIM` SELECT by AID from
   EF_DIR, read with `AT+CRSM`), sends `00 88 00 81 22 …` and parses `DB`/`DC`. This APDU is the only
   state-changing step, and only for the SIM's SQN. No modem set commands are sent.
3. Run `SWu-IKEv2` (fastest) or strongSwan with the new `eap-aka-atcsim` plugin from Ubuntu or a host that sees
   the board:
   - IDi `0<IMSI>@nai.epc.mnc002.mcc286.3gppnetwork.org`, IDr `ims`, APN `ims`.
   - Proposals: `aes128-sha1-modp1024`, `aes256-sha256-modp2048`.
   - CP request for P-CSCF v4/v6, IP and DNS.
   - Peer authentication unchecked in the test.
4. Record the IKE_SA_INIT and IKE_AUTH exchange (a pcap is fine; it is encrypted after INIT), the EAP rounds and
   the CP reply.
5. Tear down. Confirm `+CIREG:0,1,0` is unchanged and SMS still works.

## Appendix: how the evidence was obtained

- `super.img` (U30 Air backup, 2 GiB) was unpacked with a 60-line LP-metadata parser. `system_a`, `system_ext_a`,
  `vendor_a`, `product_a`, `odm_a` and `vendor_dlkm_a` are EROFS and were extracted with `fsck.erofs --extract`
  (Debian trixie container). `ims.apk` was disassembled with `dexdump`. The modem strings come from
  `nr_modem_a.img`.
- The AT probe ran on the U30 Air through `mu300-at -t 5`, with `?` and `=?` forms only.
- The DNS lookups and whois ran from the Mac through the user's VPN.
- None of the proprietary files are added to the repository.
