# The local voice API

What a service on the device - a SIP server, a dialer for the round screen, a messaging bridge - can use to place
and take cellular calls, hear and speak in them, and send and receive SMS, without opening the modem itself. It is
local only: commands, a unix socket and files under `/run/mu300-voice`, nothing on the network. Version 1; every
JSON object carries `"v":1`, and a reader ignores objects with another `v` and fields it does not know.

| | how | who |
|---|---|---|
| AT commands | `mu300-at` (nr1 - nr4 with the F50's internal SIM selected - and the shared lock) | root |
| call control | `mu300-voice call / answer / hangup / dtmf / status --json` | root; the `mu300voice` group as `sudo mu300-voice-api ...` |
| call events | `/run/mu300-voice/events.sock`, `events.jsonl`, `state.json`, `mu300-voice events` | root, `mu300voice` |
| call event hooks | `/etc/mu300/voice.d/*.sh` | root's files, run as root |
| call audio | ALSA `hw:<card>,<FE_ST_VOICE_PCM_P>` / `hw:<card>,<FE_ST_VOICE_C>`, or the fifos `/run/mu300-voice/audio/{downlink,uplink}` | root, `audio` / `mu300voice` |
| SMS | `sms send`, `sms watch HOOK` (Ubuntu); `mu300-sms send`, `/etc/mu300/sms-hook` (OpenWrt with the panel) | root |
| SIP ports | `/etc/mu300/firewall.d/*.nft` (Ubuntu), fw4 rules (OpenWrt): the LAN only | root |
| the service | `contrib/voice-api/dikecphone.service`, `dikecphone.init` | |

The events, hooks and audio need `mu300-voice watch` running: `systemctl enable --now mu300-voice` (Ubuntu),
`/etc/init.d/mu300-voice enable && /etc/init.d/mu300-voice start` (OpenWrt). It is not on in the images: it asks
the modem about calls every few seconds, which only a device that takes calls needs.

## Access

Nothing here is reachable from the network, and nothing is wider than root unless the system has the group:

    groupadd --system mu300voice            # OpenWrt: echo 'mu300voice:x:950:' >> /etc/group
    usermod -aG mu300voice,audio dikecphone # the service's user

With the group, `mu300-voice` opens exactly these to it: `/run/mu300-voice` 0710 (enter, not list),
`events.sock` 0660, `events.jsonl` and `state.json` 0640, `audio/` 0710 with `downlink` 0640 and `uplink` 0620.
Without the group every one of them is root's alone (0700/0600). The group name is `VOICE_GROUP` in
`/etc/mu300/voice.conf` (`rootfs/overlay/etc/mu300/voice.conf.example`).

The AT channel is not given to the group by any of this: an AT command can do anything to the modem (radio, SIM,
data, SMS), so `mu300-at` stays root's. A service that is not root places and answers calls through the commands
below, which check every argument, as `sudo -n /opt/mu300/bin/mu300-voice-api ...`: that is the one command
`contrib/voice-api/sudoers.mu300voice` allows the group (and, commented out, `sms send`). `mu300-voice-api` is
`mu300-voice` with two things taken away:

* the caller's environment, all of it (`env -i`): no `MU300_*` variable - another voice.conf, another AT
  directory - and no `PATH` of the caller's reaches a command that runs as root, whatever the system's sudo keeps;
* everything but the API's grammar: `status`, `call NUMBER`, `answer [ID] [--wait S]`, `hangup [ID]`,
  `dtmf DIGITS` (each with `--json`). Anything else - `--demo`, `audio`, `watch`, `events`, an unknown option, an
  extra argument - is refused with exit 2 before the modem is touched. sudoers wildcards match extra words, so the
  grammar is enforced there, in the command, not in sudoers.

The restriction is on that name, not on sudo: the administrator's `sudo mu300-voice watch` or `sudo mu300-voice
audio start bt` is the whole command. Never put `mu300-voice` itself into a sudoers line for a service. OpenWrt has
no sudo: there a service that places or answers calls runs as root (and may still call `mu300-voice-api` for the
strict grammar).

`/run` takes files from every user on these images, so `mu300-voice` uses `/run/mu300-voice` only when it is root's
own directory that nobody else may write (not a symlink, not one somebody made first) and refuses to run otherwise.

Phone numbers are never written to a log in full - `mu300-voice` masks them (`+905321234540` -> `+90********40`)
in everything it logs. The API itself carries them in full (that is its job: a dialer shows who is calling), in
the events, the snapshot and the hooks' environment; the feed is in RAM, at most 16 KiB (`events.jsonl` and the
previous `events.jsonl.1`), and nothing is kept as a call history.

## (a) AT commands

The modem's AT channels are SIPC ttys that take one reader each; opening one that `mu300-atd` holds, or closing
one while the modem runs, leaves it silent until a reboot (FINDINGS 13b). So a service never opens
`/dev/stty_nr*` itself - not `kano_at_daemon` either - and goes through the daemons:

| channel | daemon | used by |
|---|---|---|
| nr0 | read by mu300-atd (nr1's) into `/run/mu300-at/urc/stty_nr0.log` | the modem's unsolicited lines: RING, +CLIP, +CMTI, NO CARRIER |
| nr1 | `mu300-atd`, `/run/mu300-at` | `mu300-at` - everything: the panel, SMS, mu300-voice, toolkit |
| nr2 | `mu300-atd` (second instance), `/run/mu300-at2` | mobile-data only (AT+CGDATA blocks its channel for 10-20 s) |

Use nr1, through `mu300-at`:

    mu300-at "AT+CSQ"            # the reply, ending in OK / ERROR / +CME ERROR...; exit 0 only with a final result
    mu300-at -t 20 "AT+COPS?"    # wait up to 20 s (1-99) for the reply

`mu300-at` serialises every client with one lock (`/run/mu300-at/lock`), so a command may wait behind another
(the panel's collector, an SMS send; `AT+SFUN=4` takes ~20 s). Keep commands short and one per call, never hold
the lock across several, and never touch nr2: a dial there would wait behind mobile data. One command per
`mu300-at` call: a line feed, or a CR outside `AT+CMGS=<n><CR><PDU><Ctrl-Z>`, is refused. `mu300-at` needs root.

There is no channel reserved for voice. Calls work from nr1 and the commands they need are quick (ATD, ATA,
AT+CHUP, AT+VTS, AT+CLCC answer in well under a second); a third daemon on another SIPC channel would be one more
reader that can wedge, and is not worth it until a measurement says otherwise.

For dikecphone's sipserver: its `requestATDaemon` (one JSON request per unix connection to `kano_at_daemon`)
becomes `exec mu300-at -t <s> <command>` - stdout is the reply, exit status 0 means a final result code came. For
the call commands use `mu300-voice` below rather than raw ATD/ATA/CHUP/VTS: it validates and reports in JSON.

## (b) Call control

    mu300-voice status --json
    mu300-voice call NUMBER --json          # NUMBER: 3-20 digits, a leading + allowed; no emergency numbers
    mu300-voice answer [ID] [--wait SECONDS] --json
    mu300-voice hangup [ID] --json
    mu300-voice dtmf DIGITS --json          # 0-9 * # A-D, at most 32, one AT+VTS each

Each prints one JSON line and exits 0 on success, 1 on failure (2: a usage error):

    {"v":1,"action":"call","ok":true,"id":1}
    {"v":1,"action":"answer","ok":false,"error":"no incoming call"}
    {"v":1,"action":"hangup","ok":false,"error":"+CME ERROR: 3"}
    {"v":1,"action":"dtmf","ok":true,"sent":4}

`error` is mu300-voice's own text or the modem's final result code, never other text. What the commands do:

* `call` sends `ATD<number>;` (a voice call) and returns once the modem took it; `id` is the new call's id when
  AT+CLCC already shows it. The call's progress (dialing, alerting, active, ended) comes as events. No `*` or
  `#` in a number (MMI/USSD codes are not calls; tones go by `dtmf`), no spaces, dashes, CLIR prefixes (`*31#`,
  `#31#`, `*67`) or suffixes, no non-ASCII digits: refused, not cleaned up. Then two more layers, both failing
  closed (a check that cannot run refuses the call):
  * **`CALL_ALLOW`** in `/etc/mu300/voice.conf`: the numbers `call` may dial, space-separated, exactly as they
    will be given. Empty, or no voice.conf: **no number is called** - configure the numbers your service calls.
    The file is read again at the moment of every call, never from what a running `watch` saw, and only when it
    is root's and writable by nobody else (it is shell, read by root); otherwise it counts as absent. List the
    numbers the service calls (a SIP trunk's outbound numbers, a test line), or `CALL_ALLOW=any` to lift this
    layer.
  * **emergency numbers, never**, even when listed: a fixed list (112, 911, 999, 000, 08, 110, 118, 119,
    100-108, 122, 155-158, 177, 184, ...) plus the network's (`AT+CEN?`) and the SIM's (EF_ECC through
    `AT+CRSM`), read from the modem afresh before every call, never cached - if the modem does not give them
    now, the call is refused, whatever an earlier read said; the fixed list applies either way
    (`the emergency lists could not be read from the modem`). A number matches as dialled, with a national 0, or
    after a `+` / `00` / `0` prefix and up to three digits of country or trunk code (`+90112`, `0090112`,
    `090112`).

  Every argument is checked exactly as it goes into the AT command; a refused value is never echoed back.
* `answer` answers the incoming call (`ATA`), or a waiting one (`AT+CHLD=2`: the active call goes on hold). With
  an `ID`, only that call. `--wait S` waits up to S seconds for one to ring first.
* `hangup` ends every call (`AT+CHUP`, also rejects a ringing one), or with an `ID` that call alone
  (`AT+CHLD=1<id>`).
* `dtmf` sends tones into the active call.
* Without `--json` they say nothing on success and the error on stderr.
* `--demo` (call, answer) is the audio bring-up test of `mu300-voice`: after the call connects it plays a melody and
  echoes the caller back. Not for services.

`status --json`:

    {"v":1,"event":"status","time":1760000000,"modem":true,
     "calls":[{"id":1,"dir":"in","state":"active","number":"+905321234540","multiparty":false}],
     "audio":{"available":true,"running":true,"output":"dsp","format":"S16_LE","rate":8000,"channels":1,
              "period_frames":160,"playback":"hw:0,53","capture":"hw:0,9",
              "pipes":{"downlink":"/run/mu300-voice/audio/downlink","uplink":"/run/mu300-voice/audio/uplink"}},
     "api":{"socket":"/run/mu300-voice/events.sock","socket_up":true,"feed":"/run/mu300-voice/events.jsonl",
            "hooks":"/etc/mu300/voice.d"}}

(one line in reality). `modem` false (exit 1) when the modem did not answer; `calls` is then the empty list and
means nothing. `number` is null when the caller is hidden. A call's `state` is one of `dialing`, `alerting`,
`incoming`, `waiting`, `active`, `held` (3GPP 27.007 +CLCC 2, 3, 4, 5, 0, 1); its `id` is the modem's call index
(1-7), valid until that call has ended. Only voice calls are listed. `audio.available` false: no sound card (a
kernel without the audio drivers); then `playback`, `capture` and `pipes` are null.

## (c) Call events

`mu300-voice watch` follows the calls (AT+CLCC every second during a call, every 3 s without one, and at once
when the modem says anything on nr0 - a RING is seen within a quarter second) and produces one event per change.

**The socket** `/run/mu300-voice/events.sock` (stream, 0660 root:mu300voice), served by `mu300-voice-events`
(`tools/voice-events`, started by watch). Connect and read lines; each line is one JSON object. The first line is
the current state, then each event as it happens. Anything a client writes is read and thrown away: the socket only
tells, the commands act. A client that does not read (its socket buffer full) is disconnected rather than waited
for; reconnect, and the snapshot brings it up to date.

**The feed** `/run/mu300-voice/events.jsonl` (0640): the same event lines, appended. `mu300-voice events` prints the
state and then follows the feed - the socket's stream for a client without a socket library, or before
`mu300-voice-events` is installed.

**The snapshot** `/run/mu300-voice/state.json`: `status --json` as of the last change, with `"event":"snapshot"`.

Events:

    {"v":1,"event":"snapshot","time":1760000000,"modem":true,"calls":[...],"audio":{...},"api":{...}}
    {"v":1,"event":"call","time":1760000001,"id":1,"state":"incoming","prev":"none","dir":"in","number":"+905321234540","multiparty":false}
    {"v":1,"event":"call","time":1760000004,"id":1,"state":"active","prev":"incoming","dir":"in","number":"+905321234540","multiparty":false}
    {"v":1,"event":"audio","time":1760000005,"state":"up","audio":{...as in status...}}
    {"v":1,"event":"call","time":1760000060,"id":1,"state":"ended","prev":"active","dir":"in","number":"+905321234540","multiparty":false}
    {"v":1,"event":"audio","time":1760000060,"state":"down","audio":{...}}

* `call`: `state` is a call state above or `ended`; `prev` is the state before, `none` for a call first seen.
  States the poll did not see (a call that rang and was answered within a second) are skipped, so a client follows
  `state`, not a fixed sequence. A watch that cannot reach the modem emits nothing - a silent modem is never taken
  for "the call ended".
* `audio`: the call scene came up (open the ALSA devices or the pipes now) or went down. Only with the sound card
  and the DSP (below).

**The hooks** `/etc/mu300/voice.d/*.sh`: for every `call` event, each executable hook in name order, as root, with

| variable | |
|---|---|
| `CALL_EVENT` | `call` |
| `CALL_STATE` | the new state (`incoming` ... `ended`) |
| `CALL_PREV_STATE` | the state before, `none` for a new call |
| `CALL_ID` | the call's id |
| `CALL_DIR` | `in` or `out` |
| `NUMBER`, `CALL_NUMBER` | the number, empty when hidden |
| `CALL_JSON` | the event's JSON line |

stdin, stdout and stderr are `/dev/null`; a hook is stopped after 30 s. Because they run as root, a hook - and the
directory - must be owned by root and writable by nobody else, or it is not run (and the log says so). The hooks
of one event run after the previous event's have finished, in the background: a slow hook never delays the
watch, and "ended" never runs before "incoming". Example: `contrib/voice-api-example/10-log-call.sh`. The SMS
equivalent is `/etc/mu300/sms-hook` (below).

## (d) Call audio

The call's audio is in the Unisoc audio DSP; the AP reaches it through two taps that `mu300-voice audio start
dsp` (and watch, by itself, with `OUTPUT=dsp`) opens while a call is up:

| | ALSA device (name in `/proc/asound/pcm`) | fifo | |
|---|---|---|---|
| downlink: what the far end says | capture `hw:<card>,FE_ST_VOICE_C` | `/run/mu300-voice/audio/downlink` - read | 0640 |
| uplink: what the far end hears | playback `hw:<card>,FE_ST_VOICE_PCM_P` | `/run/mu300-voice/audio/uplink` - write | 0620 |

Both are raw `S16_LE`, mono, 8000 Hz (`rate` in status), 20 ms periods (`period_frames` 160). The device numbers
differ between builds of the card: take them from `status --json` (`playback`, `capture`) or by name from
`/proc/asound/pcm`, as sipserver's `alsa.go` already does. The uplink replaces the (absent) microphone
(`VBC_DSP_VOICE_PCM_PLAY_MODE` = UPLINK_ONLY) and the capture is the downlink alone (`VBC_DSP_VOICE_CAPTURE_TYPE`
= DOWNLINK), so a SIP bridge gets no echo of itself from the DSP.

* **ALSA**: open the two devices when the `audio` `up` event comes, close them on `down` (or when the call ends).
  `/dev/snd/*` is root:audio on Ubuntu: the service's user needs the `audio` group. Lowest latency.
* **The fifos**: `AUDIO_PIPES=1` in voice.conf (or `mu300-voice audio start dsp --pipes`). For a client that
  would rather not do ALSA: read `downlink`, write `uplink`, continuously in 20 ms frames (write silence when there
  is nothing to say). Each side is an arecord/aplay that opens its fifo when the client does, so a client may
  come and go during a call; the fifos are removed when the scene stops. Use one way or the other, not both: each
  ALSA device takes one stream.

16 kHz: `MU300_VOICE_RATE=16000` makes the scene and both ways 16 kHz with 320-frame periods; it is in the API but
untested - the network's wideband needs the DSP's WB profile, which follows the DSP's bandwidth message.

What this depends on - none of it is in the releases yet:

* the 5.4 kernel's audio drivers with the patches of PR #145 (`kernel/build-audio.sh`: the period timer, the
  AGCP-safe pointer, the front-end formats); the mainline kernels have no driver for this audio DSP;
* `pcmhost` (`tools/pcmhost`) and `ctlset` (`tools/ctlset`) on the device, `mu300-voice-events` for the socket;
* an AGDSP firmware image, which this project does not ship (`mu300-audio-dsp install FILE`; FINDINGS 24, 24c).
  Without it the DSP does not run, there is no audio, and a call without audio is dropped after ~20 s by some
  networks (VoLTE; FINDINGS 24b).

Without them calls, events, hooks, DTMF and SMS all work; `audio.available` is false or the scene does not start
(the log says why), and no `audio` event comes.

## (e) SMS

Received messages are already an API:

* Ubuntu (and the other systemd images): `sms watch COMMAND` runs COMMAND for each new message with `SMS_FROM`,
  `SMS_DATE`, `SMS_TEXT`, `SMS_INDEX`; send with `sms send NUMBER TEXT...` (any text; it picks GSM 7-bit or UCS-2).
* OpenWrt with the panel: `mu300-smsd` moves every message into the pool and runs `/etc/mu300/sms-hook` (when
  executable) with `SMS_FROM`, `SMS_DATE`, `SMS_TEXT`, `SMS_ID`; send with `mu300-sms send NUMBER TEXT...` or
  `mu300-sms send --stdin NUMBER` (text on stdin: no quoting, no length limit of a command line), which also keeps
  it in the pool. Use these there, not `sms watch`: the pool takes messages off the SIM within seconds.

Both run as root (they go through `mu300-at`); for a service user, the sudoers template has the line for
`sms send`.

## (f) SIP ports: the LAN only

A SIP server listens on the LAN; it must never be reachable from the cellular side, the Wi-Fi uplink or a tunnel.

* **Ubuntu**: the base rules (`/etc/mu300/firewall.nft`) close the cellular side and leave the LAN open; drop-ins
  in `/etc/mu300/firewall.d/*.nft` are loaded after them by `mu300-firewall.service`, each on its own - a broken
  drop-in is reported and skipped, and never takes the base rules with it. `contrib/voice-api/sip-lan.nft` drops
  the SIP server's ports (5060 UDP/TCP, 5080, 8088, RTP 20000-20200 and 20400-20800 - sipserver's; edit them) on
  every interface that is not the LAN (`br-lan`, `usb0`, `rndis0`, `lo`):

      sudo install -m 644 contrib/voice-api/sip-lan.nft /etc/mu300/firewall.d/50-sip-lan.nft
      sudo systemctl restart mu300-firewall

* **OpenWrt**: fw4's lan zone takes input and the wan zone (cellular, and wlan0 as an uplink) rejects it, so the
  ports are already LAN-only. `contrib/voice-api/openwrt-fw4-sip-lan.sh` adds named `src lan` ACCEPT rules for
  them (idempotent), which keeps it so if the lan zone is ever tightened. Never add a rule for them with `src wan`.

Nothing in the voice API itself listens on the network.

## (g) Running as a service

* `contrib/voice-api/dikecphone.service`: a systemd unit for the service under its own user, with the
  `mu300voice` and `audio` groups, after `mu300-voice.service`.
* `contrib/voice-api/dikecphone.init`: the procd init script for OpenWrt (root; START after mu300-voice).
* `contrib/voice-api/sudoers.mu300voice`: the call commands for the group (`mu300-voice-api`).

## Examples

`contrib/voice-api-example/`:

* `voice_client.py` - prints every event and, with `--answer`, answers each incoming call (`mu300-voice answer ID
  --json`; `sudo -n mu300-voice-api answer ID --json` when not root). Standard library only; the device images do not carry Python
  (`apt install python3`), it is the reference for a client in any language.
* `voice-events.sh` - the same in shell, from the socket (socat or `nc -U`) or `mu300-voice events`.
* `10-log-call.sh` - a hook: one syslog line per call event, the number masked.

A first check on the device, without a call:

    sudo mu300-voice status --json
    sudo systemctl start mu300-voice && sudo mu300-voice events      # the snapshot, then events (^C)

## Not yet

* `pcmhost`, `ctlset`, `mu300-hfp` and `mu300-voice-events` are built by hand (`tools/*/build.sh`, static arm64,
  into `/opt/mu300/bin`), not by the release build.
* No hold/swap/conference command: `mu300-at "AT+CHLD=..."` as root.
* One SIM at a time: the slot chosen at boot (`mu300-sim`, docs/SIM-SELECTION.md); `mu300-at` and the URC log
  follow it, and so does everything here.
