#!/usr/bin/env python3
"""A minimal client of the MU300 voice API (docs/voice-api.md): print every call event, and answer incoming calls.

    voice_client.py [--answer] [--socket /run/mu300-voice/events.sock]

Run it as root, or as a member of the mu300voice group (the socket is 0660 root:mu300voice); --answer then needs
the call commands through sudo (contrib/voice-api/sudoers.mu300voice). Standard library only: the device images do
not carry Python, this is the reference for a client in any language - one JSON object per line, the first one the
current state ("snapshot"), then "call" and "audio" events as they happen.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys

SOCKET = '/run/mu300-voice/events.sock'
VOICE = '/opt/mu300/bin/mu300-voice'
# what a member of mu300voice runs through sudo, by its full path: that is what sudoers.mu300voice allows
VOICE_API = '/opt/mu300/bin/mu300-voice-api'


def mask(text):
    """Numbers out of what is printed: +905321234540 -> +90********40 (the same rule as mu300-voice's logs)."""
    def m(match):
        n = match.group(0)
        keep = 3 if n.startswith('+') else 0
        return n[:keep] + '*' * (len(n) - keep - 2) + n[-2:]
    return re.sub(r'\+?\d{5,}', m, text)


def describe(ev):
    if ev.get('event') == 'call':
        who = ev.get('number') or 'hidden number'
        return mask(f"call {ev['id']} ({ev['dir']}): {ev['prev']} -> {ev['state']}, {who}")
    if ev.get('event') == 'audio':
        a = ev.get('audio', {})
        return f"audio {ev['state']}: {a.get('format')} {a.get('rate')} Hz, play {a.get('playback')}, " \
               f"capture {a.get('capture')}, pipes {a.get('pipes')}"
    if ev.get('event') == 'snapshot':
        return mask(f"now: {len(ev.get('calls', []))} call(s) {json.dumps(ev.get('calls', []))}")
    return json.dumps(ev)


def action(ev, answer):
    """The command to run for EV, or None: answer a call the moment it starts ringing."""
    if answer and ev.get('event') == 'call' and ev.get('state') == 'incoming' and ev.get('prev') == 'none':
        return [VOICE, 'answer', str(ev['id']), '--json']
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--answer', action='store_true', help='answer every incoming call')
    ap.add_argument('--socket', default=SOCKET)
    args = ap.parse_args()
    s = socket.socket(socket.AF_UNIX)
    s.connect(args.socket)
    for line in s.makefile('r', encoding='utf-8'):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get('v') != 1:
            continue                      # a future format: not ours to guess at
        print(describe(ev), flush=True)
        cmd = action(ev, args.answer)
        if cmd:
            if os.geteuid() != 0:
                cmd = ['sudo', '-n', VOICE_API] + cmd[1:]
            r = subprocess.run(cmd, capture_output=True, text=True)
            print('  ->', r.stdout.strip() or r.stderr.strip(), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
