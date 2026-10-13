/* mu300-hfp: a minimal Bluetooth Hands-Free audio gateway (HFP AG) for one paired headset, so a cellular call's
 * audio can go to it. Raw BlueZ kernel sockets, no libbluetooth, no D-Bus: it builds static for Ubuntu and OpenWrt.
 *
 *   mu300-hfp [-c CHANNEL] [-C FIFO] [-a ANSWER_CMD] [-x HANGUP_CMD] [-r|-l] BDADDR
 *     -r  report what arrives over the SCO socket (bytes and the loudest sample, once a second): a microphone
 *         test; -l also plays it back to the headset. With the PCM route (below) nothing arrives: measured on
 *         F50-B with a Xiaomi Sound Pocket, 30 s of SCO up, 0 bytes.
 *
 * It connects to the headset (BlueZ must already have paired it - bluetoothctl pair/trust), finds the headset's
 * Hands-Free RFCOMM channel by SDP unless -c gives it, and runs the service level connection: the AT exchange a
 * headset expects from a phone (BRSF, CIND, CMER ...). The audio itself never passes through this program. On
 * the UMS9620 the Bluetooth controller's PSKey has g_sys_sco_transmit_mode = 0, which sends SCO audio over its PCM
 * pins to the audio DSP's IIS3, not over HCI (kanoqwq/e5-linux FINDINGS 58-59 measured exactly that on the same
 * controller), so all this does is open and hold the SCO link while the DSP moves the call audio
 * (mu300-voice audio start bt).
 *
 * Control, one line at a time, through the FIFO (default /run/mu300-hfp.ctl):
 *   sco on | sco off          open / close the SCO audio link
 *   call 0|1                  call indicator (1 = a call is up)
 *   setup 0|1|2|3             callsetup indicator (none, incoming, outgoing, alerting)
 *   ring [NUMBER]             RING (+CLIP) to the headset, once; send it every few seconds while it rings
 *   quit
 * The headset's buttons come back as commands: ATA runs ANSWER_CMD, AT+CHUP runs HANGUP_CMD (both through
 * /bin/sh -c, in the background). Status goes to stdout, one line per event.
 *
 * Security. It never listens: it only connects out, to the one address it is given, and only if BlueZ holds a
 * link key for that address (a bonded device, /var/lib/bluetooth/<adapter>/<address>/info with [LinkKey]). The
 * RFCOMM link is opened at BT_SECURITY_MEDIUM - authenticated with that key and encrypted - and the peer address is
 * checked again after the connect. What the headset sends is matched against a strict allow-list (at_classify);
 * nothing from it ever reaches the modem: ATA and AT+CHUP run the two fixed commands given on the command line,
 * dialling (ATD, AT+BLDN) and voice dial are refused, anything unknown gets ERROR. The control FIFO is 0600.
 *
 * Only CVSD (8 kHz narrowband) is offered: no codec negotiation is advertised, so a headset never switches to
 * mSBC and VBC_SRC_BT_DAC/ADC stay at 8000. */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* the few BlueZ kernel ABI definitions this needs, so no libbluetooth headers are required */
#ifndef AF_BLUETOOTH
#define AF_BLUETOOTH 31
#endif
#define BTPROTO_L2CAP 0
#define BTPROTO_SCO 2
#define BTPROTO_RFCOMM 3
#define SOL_BLUETOOTH 274
#define BT_VOICE 11
#define BT_VOICE_CVSD_16BIT 0x0060
#define BT_SECURITY 4
#define BT_SECURITY_MEDIUM 2     /* authenticated (bonded) and encrypted link */
struct bt_security { uint8_t level; uint8_t key_size; };
typedef struct { uint8_t b[6]; } __attribute__((packed)) bdaddr_t;
struct sockaddr_l2 { sa_family_t l2_family; uint16_t l2_psm; bdaddr_t l2_bdaddr; uint16_t l2_cid; uint8_t l2_bdaddr_type; };
struct sockaddr_rc { sa_family_t rc_family; bdaddr_t rc_bdaddr; uint8_t rc_channel; };
struct sockaddr_sco { sa_family_t sco_family; bdaddr_t sco_bdaddr; };
struct bt_voice { uint16_t setting; };

/* AG features: bit 5, the ability to reject a call. No three-way calling, no codec negotiation (CVSD only). */
#define AG_FEATURES 32

static bdaddr_t peer;
static const char *answer_cmd, *hangup_cmd;
static int rc = -1, sco = -1;
static int ind_call, ind_setup, ind_service = 1, ind_signal = 4, ind_roam, ind_batt = 5, ind_held;
static int cmer;          /* the headset asked for indicator events */
static int clip;          /* the headset asked for caller id */

static int str2ba(const char *s, bdaddr_t *ba)
{
	unsigned int v[6];
	if (sscanf(s, "%2x:%2x:%2x:%2x:%2x:%2x", &v[5], &v[4], &v[3], &v[2], &v[1], &v[0]) != 6) return -1;
	for (int i = 0; i < 6; i++) ba->b[i] = v[i];
	return 0;
}

static void say(const char *fmt, const char *a)
{
	printf(fmt, a ? a : ""); putchar('\n'); fflush(stdout);
}

static void send_at(const char *line)
{
	char buf[256];
	int n = snprintf(buf, sizeof buf, "\r\n%s\r\n", line);
	if (rc >= 0 && write(rc, buf, n) != n) say("write to headset failed: %s", strerror(errno));
}

static void run_bg(const char *cmd)
{
	if (!cmd || !*cmd) return;
	pid_t p = fork();
	if (p == 0) {
		/* the command gets none of the links: a slow mu300-at must not hold the headset's sockets open */
		for (int fd = 3; fd < 64; fd++) close(fd);
		setsid(); execl("/bin/sh", "sh", "-c", cmd, (char *)NULL); _exit(127);
	}
}

static void ciev(int idx, int val)
{
	char b[32];
	if (!cmer) return;
	snprintf(b, sizeof b, "+CIEV: %d,%d", idx, val);
	send_at(b);
}

/* The headset's Hands-Free RFCOMM channel, from its SDP record: a ServiceSearchAttributeRequest for the Handsfree
 * UUID (0x111E) asking only for the ProtocolDescriptorList, and the channel is the uint8 that follows the RFCOMM
 * UUID (0x0003) in it. No continuation handling: one short attribute fits in one response. */
static int sdp_hf_channel(void)
{
	int s = socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
	if (s < 0) return -1;
	struct sockaddr_l2 a; memset(&a, 0, sizeof a);
	a.l2_family = AF_BLUETOOTH; a.l2_psm = 1; a.l2_bdaddr = peer;
	/* a headset may refuse the first SDP connection right after the ACL link comes up (AirPods Pro: ECONNREFUSED
	 * once, then fine, as sdptool browse shows too): three tries */
	int tries = 3;
	while (connect(s, (struct sockaddr *)&a, sizeof a) < 0) {
		close(s);
		if (--tries == 0) return -1;
		usleep(700000);
		s = socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
		if (s < 0) return -1;
	}
	static const uint8_t req[] = {
		0x06, 0x00, 0x01, 0x00, 0x0d,          /* ServiceSearchAttributeRequest, tid 1, 13 bytes follow */
		0x35, 0x03, 0x19, 0x11, 0x1e,          /* search pattern: UUID16 Handsfree */
		0xff, 0xff,                            /* max attribute bytes */
		0x35, 0x03, 0x09, 0x00, 0x04,          /* attribute: ProtocolDescriptorList */
		0x00 };                                /* no continuation */
	uint8_t rsp[1024];
	int ch = -1;
	if (write(s, req, sizeof req) == (ssize_t)sizeof req) {
		struct pollfd p = { s, POLLIN, 0 };
		if (poll(&p, 1, 5000) > 0) {
			ssize_t n = read(s, rsp, sizeof rsp);
			for (ssize_t i = 0; i + 4 < n; i++)
				if (rsp[i] == 0x19 && rsp[i + 1] == 0x00 && rsp[i + 2] == 0x03 && rsp[i + 3] == 0x08)
					{ ch = rsp[i + 4]; break; }
		}
	}
	close(s);
	return ch;
}

static void sco_open(void)
{
	if (sco >= 0) return;
	sco = socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_SCO);
	if (sco < 0) { say("SCO socket: %s", strerror(errno)); return; }
	struct bt_voice v = { BT_VOICE_CVSD_16BIT };
	setsockopt(sco, SOL_BLUETOOTH, BT_VOICE, &v, sizeof v);
	struct sockaddr_sco a; memset(&a, 0, sizeof a);
	a.sco_family = AF_BLUETOOTH; a.sco_bdaddr = peer;
	if (connect(sco, (struct sockaddr *)&a, sizeof a) < 0) {
		say("SCO connect failed: %s", strerror(errno));
		close(sco); sco = -1; return;
	}
	say("sco up%s", "");
}

static int sco_report, sco_loop, rx_peak;
static long rx_bytes;
static time_t rx_t;

static void sco_close(void)
{
	if (sco < 0) return;
	shutdown(sco, SHUT_RDWR); close(sco); sco = -1;
	say("sco down%s", "");
}

/* The headset's AT commands this gateway takes, and nothing else. */
enum at_action { AT_ERROR, AT_OK, AT_BRSF, AT_CIND_TEST, AT_CIND_READ, AT_CMER, AT_CHLD_TEST, AT_CLIP, AT_ANSWER,
	AT_HANGUP, AT_COPS_READ, AT_CLCC };

/* s is all of [0-9,] and at most n characters, and not empty */
static int numeric(const char *s, size_t n)
{
	size_t i = 0;
	for (; s[i]; i++) if (i >= n || !((s[i] >= '0' && s[i] <= '9') || s[i] == ',')) return 0;
	return i > 0;
}

static enum at_action at_classify(const char *l)
{
	if (!strncmp(l, "AT+BRSF=", 8)) return numeric(l + 8, 10) ? AT_BRSF : AT_ERROR;
	if (!strcmp(l, "AT+CIND=?")) return AT_CIND_TEST;
	if (!strcmp(l, "AT+CIND?")) return AT_CIND_READ;
	if (!strncmp(l, "AT+CMER=", 8)) return numeric(l + 8, 16) ? AT_CMER : AT_ERROR;
	if (!strcmp(l, "AT+CHLD=?")) return AT_CHLD_TEST;
	if (!strcmp(l, "AT+CLIP=0") || !strcmp(l, "AT+CLIP=1")) return AT_CLIP;
	if (!strcmp(l, "ATA")) return AT_ANSWER;
	if (!strcmp(l, "AT+CHUP")) return AT_HANGUP;
	if (!strcmp(l, "AT+COPS?")) return AT_COPS_READ;
	if (!strcmp(l, "AT+CLCC")) return AT_CLCC;
	/* settings the gateway acknowledges and ignores: gains, echo cancelling, error format, indicators */
	if (!strncmp(l, "AT+VGS=", 7) || !strncmp(l, "AT+VGM=", 7)) return numeric(l + 7, 2) ? AT_OK : AT_ERROR;
	if (!strncmp(l, "AT+NREC=", 8) || !strncmp(l, "AT+CMEE=", 8) || !strncmp(l, "AT+CCWA=", 8))
		return numeric(l + 8, 1) ? AT_OK : AT_ERROR;
	if (!strncmp(l, "AT+BIA=", 7)) return numeric(l + 7, 32) ? AT_OK : AT_ERROR;
	if (!strcmp(l, "AT+COPS=3,0")) return AT_OK;
	/* ATD..., AT+BLDN, AT+BVRA, AT+CHLD=n, AT+VTS, AT+BTRH, anything else */
	return AT_ERROR;
}

/* one AT command from the headset */
static void handle_at(char *l)
{
	char b[160];
	enum at_action act = at_classify(l);
	/* refused lines are not logged verbatim: a dial attempt would put a number in the log */
	if (act == AT_ERROR) printf("< refused (%zu bytes)\n", strlen(l)); else say("< %s", l);
	fflush(stdout);
	switch (act) {
	case AT_BRSF:
		snprintf(b, sizeof b, "+BRSF: %d", AG_FEATURES); send_at(b); send_at("OK"); break;
	case AT_CIND_TEST:
		send_at("+CIND: (\"call\",(0,1)),(\"callsetup\",(0-3)),(\"service\",(0,1)),(\"signal\",(0-5)),"
			"(\"roam\",(0,1)),(\"battchg\",(0-5)),(\"callheld\",(0-2))");
		send_at("OK"); break;
	case AT_CIND_READ:
		snprintf(b, sizeof b, "+CIND: %d,%d,%d,%d,%d,%d,%d", ind_call, ind_setup, ind_service, ind_signal,
			 ind_roam, ind_batt, ind_held);
		send_at(b); send_at("OK"); break;
	case AT_CMER: {
		/* AT+CMER=3,0,0,1: the fourth field switches indicator events on - and ends the SLC setup */
		const char *p = strrchr(l, ',');
		cmer = p && p[1] == '1';
		send_at("OK");
		say("service level connection up%s", "");
		break;
	}
	case AT_CHLD_TEST: send_at("+CHLD: (0,1,2,3)"); send_at("OK"); break;
	case AT_CLIP: clip = l[8] == '1'; send_at("OK"); break;
	case AT_ANSWER: send_at("OK"); say("headset: answer%s", ""); run_bg(answer_cmd); break;
	case AT_HANGUP: send_at("OK"); say("headset: hang up%s", ""); run_bg(hangup_cmd); break;
	case AT_COPS_READ: send_at("+COPS: 0,0,\"\""); send_at("OK"); break;
	case AT_CLCC: case AT_OK: send_at("OK"); break;
	case AT_ERROR: default: send_at("ERROR"); break;
	}
}

static void handle_ctl(char *l)
{
	/* "ring NUMBER" carries the caller's number: log the command only */
	say("ctl: %s", strncmp(l, "ring", 4) ? l : "ring");
	if (!strcmp(l, "sco on")) sco_open();
	else if (!strcmp(l, "sco off")) sco_close();
	else if (!strncmp(l, "call ", 5)) { int v = atoi(l + 5) ? 1 : 0; if (v != ind_call) { ind_call = v; ciev(1, v); } }
	else if (!strncmp(l, "setup ", 6)) { int v = atoi(l + 6); if (v < 0 || v > 3) v = 0;
		if (v != ind_setup) { ind_setup = v; ciev(2, v); } }
	else if (!strncmp(l, "ring", 4)) {
		send_at("RING");
		if (clip && l[4] == ' ' && l[5] && strspn(l + 5, "+0123456789*#") == strlen(l + 5)) {
			char b[96]; snprintf(b, sizeof b, "+CLIP: \"%.40s\",%d", l + 5, l[5] == '+' ? 145 : 129);
			send_at(b);
		}
	} else if (!strcmp(l, "quit")) { sco_close(); exit(0); }
}

/* split a byte stream into lines on \r or \n */
static void feed(char *acc, size_t *len, size_t cap, const char *in, ssize_t n, void (*fn)(char *))
{
	for (ssize_t i = 0; i < n; i++) {
		char c = in[i];
		if (c == '\r' || c == '\n') {
			if (*len) { acc[*len] = 0; fn(acc); *len = 0; }
		} else if (*len < cap - 1) acc[(*len)++] = c;
	}
}

static void on_term(int s) { (void)s; sco_close(); _exit(0); }

/* the adapter's own address, as BlueZ names its directory: HCIGETDEVINFO on hci0 (sysfs has no address file);
 * MU300_BT_ADAPTER_FILE names a file with it instead, for tests */
#define BTPROTO_HCI 1
#define HCIGETDEVINFO _IOR('H', 211, int)
struct hci_dev_info_min {
	uint16_t dev_id; char name[8]; bdaddr_t bdaddr; uint32_t flags; uint8_t type; uint8_t features[8];
	uint32_t pkt_type, link_policy, link_mode; uint16_t acl_mtu, acl_pkts, sco_mtu, sco_pkts; uint32_t stat[10];
};
static int adapter_address(char out[18])
{
	const char *tf = getenv("MU300_BT_ADAPTER_FILE");
	if (tf) {
		FILE *f = fopen(tf, "r");
		if (!f || !fgets(out, 18, f)) { if (f) fclose(f); return 0; }
		fclose(f);
	} else {
		struct hci_dev_info_min di; memset(&di, 0, sizeof di);
		int h = socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI);
		if (h < 0) return 0;
		if (ioctl(h, HCIGETDEVINFO, &di) < 0) { close(h); return 0; }
		close(h);
		snprintf(out, 18, "%02X:%02X:%02X:%02X:%02X:%02X", di.bdaddr.b[5], di.bdaddr.b[4], di.bdaddr.b[3],
		         di.bdaddr.b[2], di.bdaddr.b[1], di.bdaddr.b[0]);
	}
	out[17] = 0;
	for (size_t i = 0; i < 17; i++) {
		if (out[i] >= 'a' && out[i] <= 'f') out[i] -= 32;
		if (i % 3 == 2 ? out[i] != ':' : !((out[i] >= '0' && out[i] <= '9') || (out[i] >= 'A' && out[i] <= 'F')))
			return 0;
	}
	return 1;
}

/* BlueZ keeps a bonded device's link key in /var/lib/bluetooth/<adapter>/<ADDRESS>/info, section [LinkKey],
 * Key=<32 hex>. Only the adapter in use counts (its address from /sys/class/bluetooth/hci0/address: this
 * controller gets a new one at every boot, so the store holds stale directories whose keys the kernel would never
 * use), and only a section that carries a key. Read directly, no shell: main() ignores SIGCHLD, under which
 * system() can never collect its child's status - the first board test ended in "not bonded" with the key there.
 * The kernel enforces the security level on the RFCOMM socket either way; this is the early, clear answer. */
static int bonded(const char *addr, const char *store)
{
	char up[18], adapter[18], path[256], line[256];
	size_t i;
	FILE *f;
	int in_key = 0, found = 0;
	for (i = 0; i < 17 && addr[i]; i++) up[i] = (addr[i] >= 'a' && addr[i] <= 'f') ? addr[i] - 32 : addr[i];
	up[i] = 0;
	if (strlen(up) != 17) return 0;
	if (!adapter_address(adapter)) return 0;
	snprintf(path, sizeof path, "%s/%s/%s/info", store, adapter, up);
	f = fopen(path, "r");
	if (!f) return 0;
	while (fgets(line, sizeof line, f)) {
		if (line[0] == '[') { in_key = !strncmp(line, "[LinkKey]", 9); continue; }
		if (in_key && !strncmp(line, "Key=", 4)) {
			for (i = 4; i < 36 && line[i]; i++)
				if (!((line[i] >= '0' && line[i] <= '9') || (line[i] >= 'A' && line[i] <= 'F') || (line[i] >= 'a' && line[i] <= 'f'))) break;
			if (i == 36) { found = 1; break; }
		}
	}
	fclose(f);
	return found;
}

#ifndef MU300_HFP_TEST

int main(int argc, char **argv)
{
	int ch = 0, o;
	const char *fifo = "/run/mu300-hfp.ctl";
	while ((o = getopt(argc, argv, "c:C:a:x:rl")) != -1)
		switch (o) {
		case 'c': ch = atoi(optarg); break;
		case 'C': fifo = optarg; break;
		case 'a': answer_cmd = optarg; break;
		case 'x': hangup_cmd = optarg; break;
		case 'r': sco_report = 1; break;
		case 'l': sco_report = sco_loop = 1; break;
		default: goto usage;
		}
	if (optind >= argc || str2ba(argv[optind], &peer) < 0) {
usage:
		fprintf(stderr, "usage: %s [-c CHANNEL] [-C FIFO] [-a ANSWER_CMD] [-x HANGUP_CMD] BDADDR\n", argv[0]);
		return 2;
	}
	signal(SIGTERM, on_term); signal(SIGINT, on_term); signal(SIGCHLD, SIG_IGN); signal(SIGPIPE, SIG_IGN);

	if (!bonded(argv[optind], getenv("MU300_BT_STORE") ? getenv("MU300_BT_STORE") : "/var/lib/bluetooth")) {
		say("%s is not bonded (no link key in BlueZ's store): pair it first with bluetoothctl", argv[optind]);
		return 1;
	}
	if (!ch) ch = sdp_hf_channel();
	if (ch <= 0) { say("no Hands-Free service found on %s (is it on, paired and in range?)", argv[optind]); return 1; }
	rc = socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM);
	struct sockaddr_rc a; memset(&a, 0, sizeof a);
	a.rc_family = AF_BLUETOOTH; a.rc_bdaddr = peer; a.rc_channel = ch;
	/* authenticated with the bond's key and encrypted, or no connection at all */
	struct bt_security sec = { BT_SECURITY_MEDIUM, 0 };
	if (rc < 0 || setsockopt(rc, SOL_BLUETOOTH, BT_SECURITY, &sec, sizeof sec) < 0) {
		say("cannot require link security: %s", strerror(errno)); return 1;
	}
	if (connect(rc, (struct sockaddr *)&a, sizeof a) < 0) {
		say("RFCOMM connect failed: %s", strerror(errno)); return 1;
	}
	struct sockaddr_rc got; socklen_t gl = sizeof got;
	socklen_t sl = sizeof sec;
	if (getpeername(rc, (struct sockaddr *)&got, &gl) < 0 || memcmp(&got.rc_bdaddr, &peer, sizeof peer) ||
	    getsockopt(rc, SOL_BLUETOOTH, BT_SECURITY, &sec, &sl) < 0 || sec.level < BT_SECURITY_MEDIUM) {
		say("the link to %s is not the authenticated one asked for; closing", argv[optind]);
		close(rc); return 1;
	}
	printf("connected to %s, Hands-Free channel %d\n", argv[optind], ch); fflush(stdout);

	unlink(fifo);
	if (mkfifo(fifo, 0600) < 0) { say("mkfifo: %s", strerror(errno)); return 1; }
	int ctl = open(fifo, O_RDWR | O_NONBLOCK);   /* O_RDWR: no EOF when a writer closes */
	char rbuf[512], cbuf[256], tmp[256];
	size_t rlen = 0, clen = 0;
	for (;;) {
		struct pollfd p[3] = { { rc, POLLIN, 0 }, { ctl, POLLIN, 0 }, { sco, POLLIN, 0 } };
		if (poll(p, sco >= 0 ? 3 : 2, -1) < 0) { if (errno == EINTR) continue; break; }
		if (p[0].revents) {
			ssize_t n = read(rc, tmp, sizeof tmp);
			if (n <= 0) { say("headset disconnected%s", ""); break; }
			feed(rbuf, &rlen, sizeof rbuf, tmp, n, handle_at);
		}
		if (p[1].revents & POLLIN) {
			ssize_t n = read(ctl, tmp, sizeof tmp);
			if (n > 0) feed(cbuf, &clen, sizeof cbuf, tmp, n, handle_ctl);
		}
		if (sco >= 0 && (p[2].revents & (POLLHUP | POLLERR))) { say("sco closed by the headset%s", ""); close(sco); sco = -1; }
		else if (sco >= 0 && (p[2].revents & POLLIN)) {
			/* with the PCM route nothing should arrive over HCI; drain whatever does. -r reports what did
			 * (bytes and the loudest sample each second: a microphone test), -l also plays it back */
			ssize_t n = read(sco, tmp, sizeof tmp);
			if (n <= 0) { close(sco); sco = -1; }
			else if (sco_report) {
				const int16_t *sm = (const int16_t *)tmp;
				for (ssize_t i = 0; i < n / 2; i++) { int v = sm[i] < 0 ? -sm[i] : sm[i]; if (v > rx_peak) rx_peak = v; }
				rx_bytes += n;
				if (sco_loop) { ssize_t w = write(sco, tmp, n); (void)w; }
				if (time(NULL) != rx_t) { rx_t = time(NULL); char st[64]; snprintf(st, sizeof st, "%ld bytes, peak %d", rx_bytes, rx_peak); say("sco rx: %s", st); rx_bytes = 0; rx_peak = 0; }
			}
		}
	}
	sco_close();
	close(rc); close(ctl); unlink(fifo);
	return 0;
}
#else
/* the allow-list, checked on the build host: cc -DMU300_HFP_TEST tools/hfp/mu300-hfp.c && ./a.out */
int main(void)
{
	static const struct { const char *l; enum at_action a; } t[] = {
		{ "AT+BRSF=959", AT_BRSF }, { "AT+BRSF=", AT_ERROR }, { "AT+BRSF=1;ATD123;", AT_ERROR },
		{ "AT+CIND=?", AT_CIND_TEST }, { "AT+CIND?", AT_CIND_READ },
		{ "AT+CMER=3,0,0,1", AT_CMER }, { "AT+CMER=3,0,0,1;+CHUP", AT_ERROR },
		{ "AT+CHLD=?", AT_CHLD_TEST }, { "AT+CHLD=1", AT_ERROR },
		{ "AT+CLIP=1", AT_CLIP }, { "AT+CLIP=1x", AT_ERROR },
		{ "ATA", AT_ANSWER }, { "ATA;", AT_ERROR }, { "AT+CHUP", AT_HANGUP }, { "AT+CHUP;D112", AT_ERROR },
		{ "ATD112;", AT_ERROR }, { "ATD>1;", AT_ERROR }, { "AT+BLDN", AT_ERROR }, { "AT+BVRA=1", AT_ERROR },
		{ "AT+CFUN=0", AT_ERROR }, { "AT+CMGS=\"1\"", AT_ERROR }, { "AT", AT_ERROR }, { "", AT_ERROR },
		{ "AT+VGS=15", AT_OK }, { "AT+VGS=150", AT_ERROR }, { "AT+VGM=7", AT_OK },
		{ "AT+NREC=0", AT_OK }, { "AT+NREC=0;+CHUP", AT_ERROR }, { "AT+CMEE=1", AT_OK }, { "AT+CCWA=1", AT_OK },
		{ "AT+BIA=0,0,0,1,1,1,0", AT_OK }, { "AT+COPS=3,0", AT_OK }, { "AT+COPS?", AT_COPS_READ },
		{ "AT+CLCC", AT_CLCC }, { "at+chup", AT_ERROR },
	};
	int bad = 0;
	for (size_t i = 0; i < sizeof t / sizeof t[0]; i++)
		if (at_classify(t[i].l) != t[i].a) { printf("FAIL %s -> %d, want %d\n", t[i].l, at_classify(t[i].l), t[i].a); bad++; }
	struct bt_security sec = { BT_SECURITY_MEDIUM, 0 };
	if (sec.level != 2 || BT_SECURITY != 4 || sizeof sec != 2) { puts("FAIL BT_SECURITY ABI"); bad++; }
	printf("%zu allow-list cases, %d failed\n", sizeof t / sizeof t[0], bad);
	return bad != 0;
}
#endif
