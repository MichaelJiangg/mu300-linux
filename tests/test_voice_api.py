"""The local voice API (docs/voice-api.md): mu300-voice's call commands and their --json answers, the CLCC parser,
the events (feed, snapshot) and the hook runner of `mu300-voice watch`, the event socket (tools/voice-events), the
example clients, and the firewall drop-ins. A stub mu300-at plays the modem: it records every command it is given
and answers AT+CLCC from a script of replies, one per round."""
import grp
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import BIN, TOP, ShellTest

VOICE = BIN / 'mu300-voice'
EVENTS_C = TOP / 'tools' / 'voice-events' / 'mu300-voice-events.c'
EXAMPLE = TOP / 'contrib' / 'voice-api-example'
TEMPLATES = TOP / 'contrib' / 'voice-api'

NUM = '+905321234540'
INCOMING = f'+CLCC: 1,1,4,0,0,"{NUM}",145\nOK\n'
ACTIVE = f'+CLCC: 1,1,0,0,0,"{NUM}",145\nOK\n'
NONE = 'OK\n'
ECC_QUERIES = ['AT+CEN?', 'AT+CRSM=178,28599,1,4,0']

# AT+CLCC answers from $STUBLOG/clcc.1, .2, ... in turn (the last one again after the end); any other command
# answers with $STUBLOG/reply when there is one, else OK. Every command goes to $STUBLOG/at.log.
STUB_AT = r'''
[ "$1" = -t ] && shift 2
printf '%s\n' "$1" >> "$STUBLOG/at.log"
case $1 in
AT+CLCC)
    n=$(cat "$STUBLOG/clcc.n" 2>/dev/null || echo 0); n=$((n + 1))
    if [ -f "$STUBLOG/clcc.$n" ]; then echo "$n" > "$STUBLOG/clcc.n"; else n=$((n - 1)); fi
    [ -f "$STUBLOG/clcc.$n" ] && cat "$STUBLOG/clcc.$n" || echo OK ;;
*)
    f=$STUBLOG/at.$(printf '%s' "$1" | tr -c 'A-Za-z0-9' _)
    if [ -f "$f" ]; then cat "$f"
    elif [ -f "$STUBLOG/reply" ]; then cat "$STUBLOG/reply"; else echo OK; fi ;;
esac
'''


class VoiceTest(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('mu300-at', STUB_AT)
        self.run_dir = self.tmp / 'run'
        self.hooks = self.tmp / 'voice.d'
        self.asound = self.tmp / 'asound'
        self.asound.mkdir()
        self.conf = self.tmp / 'voice.conf'
        self.group = grp.getgrgid(os.getgid()).gr_name
        self.groupfile = self.tmp / 'group'
        self.groupfile.write_text(f'{self.group}:x:{os.getgid()}:\n')
        self.conf.write_text(f'VOICE_GROUP={self.group}\nWATCH_AUDIO=0\nCALL_ALLOW=any\n')
        # the modem's emergency lists, as a USIM without EF_ECC records answers: the network's list, then "no record"
        (self.tmp / 'at.AT_CRSM_178_28599_1_4_0').write_text('+CRSM: 106,131\nOK\n')

    def clcc(self, *replies):
        for i, r in enumerate(replies, 1):
            (self.tmp / f'clcc.{i}').write_text(r)

    def voice(self, shell, *args, **env):
        e = dict(MU300_VOICE_TMP=self.run_dir, MU300_VOICE_CONF=self.conf, MU300_VOICE_HOOKS=self.hooks,
                 MU300_ASOUND=self.asound, MU300_GROUP_FILE=self.groupfile, MU300_AT_DIR=self.tmp / 'at',
                 MU300_BUSYBOX='/nonexistent', MU300_VOICE_HOOK_UID=os.getuid(), MU300_VOICE_TICK='0.02',
                 MU300_VOICE_POLL=1, MU300_VOICE_IDLE_POLL=1)
        e.update(env)
        return self.script(shell, VOICE, *args, **e)

    def at_log(self):
        p = self.tmp / 'at.log'
        lines = p.read_text().splitlines() if p.exists() else []
        p.unlink(missing_ok=True)
        (self.tmp / 'clcc.n').unlink(missing_ok=True)
        return lines

    def reset(self):
        self.at_log()
        for p in self.tmp.glob('clcc.*'):
            p.unlink()
        (self.tmp / 'reply').unlink(missing_ok=True)
        shutil.rmtree(self.run_dir, ignore_errors=True)


class Parse(VoiceTest):
    def test_clcc_lines(self):
        src = VOICE.read_text()
        start = src.index('clcc_parse() {')
        fn = src[start:src.index('\n}\n', start) + 3]
        reply = ('+CLCC: 1,0,0,0,0,"05321234540",129\n'
                 '+CLCC: 2,1,5,0,1,"+441632960961",145,"",0\n'
                 '+CLCC: 3,1,4,1,0,"123",129\n'          # data call: not ours
                 '+CLCC: 4,1,4,0,0,"",128\n'             # hidden number
                 '+CLCC: 5,1,4,0,0,"1;+CFUN=0\\r",129\n'  # not a number: only what a number has is kept
                 'OK\n')
        for sh in self.each_shell():
            r = self.sh(sh, fn + 'clcc_parse', stdin=reply)
            self.assertEqual(r.stdout.splitlines(), [
                '1 out active 0 05321234540', '2 in waiting 1 +441632960961', '4 in incoming 0 -',
                '5 in incoming 0 1+0'])


class Commands(VoiceTest):
    def test_status_json(self):
        for sh in self.each_shell():
            self.reset()
            self.clcc(ACTIVE)
            r = self.voice(sh, 'status', '--json')
            self.assertEqual(r.returncode, 0, r.stderr)
            j = json.loads(r.stdout)
            self.assertEqual(j['v'], 1)
            self.assertTrue(j['modem'])
            self.assertEqual(j['calls'], [{'id': 1, 'dir': 'in', 'state': 'active', 'number': NUM,
                                           'multiparty': False}])
            self.assertEqual(j['audio']['available'], False)
            self.assertEqual((j['audio']['format'], j['audio']['rate'], j['audio']['channels']), ('S16_LE', 8000, 1))
            self.assertEqual(j['api']['socket'], f'{self.run_dir}/events.sock')
            self.assertEqual(self.at_log(), ['AT+CLCC'])

    def test_status_json_with_card(self):
        (self.asound / 'cards').write_text(' 0 [sprdphonesc273]: sprdphone-sc2730 - sprdphone-sc2730\n')
        (self.asound / 'pcm').write_text('00-05: FE_ST_VOICE (*) :  : playback 1 : capture 1\n'
                                         '00-09: FE_ST_VOICE_C (*) :  : capture 1\n'
                                         '00-53: FE_ST_VOICE_PCM_P (*) :  : playback 1\n')
        for sh in self.each_shell():
            self.reset()
            j = json.loads(self.voice(sh, 'status', '--json').stdout)
            self.assertEqual(j['calls'], [])
            a = j['audio']
            self.assertEqual((a['available'], a['running'], a['playback'], a['capture'], a['period_frames']),
                             (True, False, 'hw:0,53', 'hw:0,9', 160))

    def test_status_json_modem_silent(self):
        self.stub('mu300-at', 'echo "mu300-at: busy" >&2; exit 1')
        for sh in self.each_shell():
            r = self.voice(sh, 'status', '--json')
            self.assertEqual(r.returncode, 1)
            self.assertFalse(json.loads(r.stdout)['modem'])

    def test_call(self):
        for sh in self.each_shell():
            self.reset()
            self.clcc('+CLCC: 1,0,2,0,0,"4440000",129\nOK\n')
            r = self.voice(sh, 'call', '4440000', '--json')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), {'v': 1, 'action': 'call', 'ok': True, 'id': 1})
            # the modem's emergency lists are asked first (the network's, the SIM's), then the call
            self.assertEqual(self.at_log(), ECC_QUERIES + ['ATD4440000;', 'AT+CLCC'])

    # refused by every command that puts its argument into an AT command
    INJECTIONS = ('123;+CFUN=0', '123\rAT+CFUN=0', '123\nAT+CFUN=0', '123"', "123'", '1 2', 'AT', '+', '+CFUN=0',
                  '1+2', '١٢٣', '123\x1a', '1;', '1\r')

    def test_call_refuses_what_is_not_a_number(self):
        for sh in self.each_shell():
            # and for a call also MMI codes, and too short or too long
            for bad in self.INJECTIONS + ('*100#', '#31#5321234540', '12', '1' * 21, '12+3', '', 'abc', '-5'):
                self.reset()
                r = self.voice(sh, 'call', '--json', '--', bad) if bad.startswith('-') else \
                    self.voice(sh, 'call', bad, '--json')
                self.assertNotEqual(r.returncode, 0, bad)
                self.assertEqual(self.at_log(), [], bad)

    def test_no_injection_reaches_the_modem(self):
        for sh in self.each_shell():
            for bad in self.INJECTIONS:
                for cmd in ('dtmf', 'hangup', 'answer'):
                    with self.subTest(cmd=cmd, bad=bad):
                        self.reset()
                        self.clcc(INCOMING)
                        r = self.voice(sh, cmd, bad, '--json')
                        self.assertNotEqual(r.returncode, 0)
                        self.assertFalse([c for c in self.at_log() if c != 'AT+CLCC'])
                        if r.stdout:
                            # the answer stays one JSON object: the refused value is never echoed into it
                            self.assertFalse(json.loads(r.stdout)['ok'])
                            self.assertNotIn('CFUN', r.stdout)

    def test_emergency_numbers_are_not_called(self):
        for sh in self.each_shell():
            # every spelling: plain, with a country code, 00, a national 0; prefixes, separators, suffixes and
            # non-ASCII digits are refused before the list is even looked at
            for n in ('112', '+112', '911', '999', '155', '110', '000', '08', '122', '184', '+90112', '0090112',
                      '0112', '090112', '+44999', '+9008', '1 1 2', '*31#112', '#31#911', '112;', '\u0661\u0661\u0662',
                      '*67112', '112#', '(112)', '1-1-2', '+1911'):
                with self.subTest(n=n):
                    self.reset()
                    r = self.voice(sh, 'call', n, '--json')
                    self.assertEqual(r.returncode, 1, n)
                    self.assertFalse([c for c in self.at_log() if c.startswith('ATD')], n)
            self.reset()
            self.clcc('+CLCC: 1,0,2,0,0,"4440000",129\nOK\n')
            self.assertEqual(self.voice(sh, 'call', '4440000').returncode, 0)

    EMERGENCY_ERR = 'emergency numbers are not placed through mu300-voice'
    LISTS_ERR = 'the emergency lists could not be read from the modem; not calling'

    def at_reply(self, cmd, text):
        name = 'at.' + ''.join(c if c.isalnum() else '_' for c in cmd)
        p = self.tmp / name
        if text is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(text)

    def call_error(self, sh, n):
        self.reset()
        r = self.voice(sh, 'call', n, '--json')
        self.assertFalse([c for c in self.at_log() if c.startswith('ATD')], n)
        return json.loads(r.stdout)['error'] if r.stdout else r.returncode

    def test_the_modems_own_emergency_lists(self):
        # as F50-B's modem answers: unquoted. The network's +CEN2, the SIM's EF_ECC records (BCD, nibbles swapped:
        # 99 F1 FF is 991), read until the SIM says there is no further record
        self.at_reply('AT+CEN?', '+CEN1: 0,286,01F\n+CEN2: 4,110\n+CEN2: 1,7777\nOK\n')
        self.at_reply('AT+CRSM=178,28599,1,4,0', '+CRSM: 144,0,FFFFFFFF\nOK\n')
        self.at_reply('AT+CRSM=178,28599,2,4,0', '+CRSM: 144,0,99F1FF41\nOK\n')
        self.at_reply('AT+CRSM=178,28599,3,4,0', '+CRSM: 106,131\nOK\n')
        for sh in self.each_shell():
            for n in ('7777', '+907777', '07777', '991', '0991', '0090991'):
                with self.subTest(n=n):
                    self.assertEqual(self.call_error(sh, n), self.EMERGENCY_ERR)
            self.reset()
            self.assertEqual(self.voice(sh, 'call', '4440000').returncode, 0)
        # a 2G SIM: EF_ECC is transparent, five numbers of 3 bytes
        self.at_reply('AT+CRSM=178,28599,1,4,0', '+CRSM: 105,129\nOK\n')
        self.at_reply('AT+CRSM=176,28599,0,0,0', '+CRSM: 144,0,"11F2FF55F5FFFFFFFFFFFFFFFFFFFF"\nOK\n')
        for sh in self.each_shell():
            self.assertEqual(self.call_error(sh, '555'), self.EMERGENCY_ERR)

    def test_fails_closed(self):
        # every way the modem's lists can be missing refuses the call, and so does no CALL_ALLOW
        cases = [
            ('AT+CEN?', 'ERROR\n'),                          # the network's list not given
            ('AT+CEN?', '+CEN2: 1,7777\n'),                  # no final result
            ('AT+CRSM=178,28599,1,4,0', 'OK\n'),             # no +CRSM line
            ('AT+CRSM=178,28599,1,4,0', 'ERROR\n'),
            ('AT+CRSM=178,28599,1,4,0', '+CRSM: 0,0\nOK\n'),  # neither "here it is" nor "there is none"
            ('AT+CRSM=178,28599,1,4,0', '+CRSM: 105,129\nOK\n'),   # 2G fallback that fails in turn
        ]
        for sh in self.each_shell():
            for cmd, reply in cases:
                with self.subTest(cmd=cmd, reply=reply):
                    self.at_reply(cmd, reply)
                    self.assertEqual(self.call_error(sh, '4440000'), self.LISTS_ERR)
                    self.at_reply(cmd, None)
                    self.at_reply('AT+CRSM=178,28599,1,4,0', '+CRSM: 106,131\nOK\n')
            # the AT channel itself failing
            self.stub('mu300-at', 'echo "mu300-at: busy" >&2; exit 1')
            self.assertEqual(self.call_error(sh, '4440000'), self.LISTS_ERR)
            self.stub('mu300-at', STUB_AT)
        for conf in ('VOICE_GROUP=x\n', 'CALL_ALLOW=\n', 'CALL_ALLOW=" "\n'):
            self.conf.write_text(conf)
            for sh in self.each_shell():
                self.assertEqual(self.call_error(sh, '4440000'), 'not in CALL_ALLOW (voice.conf)')
        self.conf.unlink()
        for sh in self.each_shell():
            self.assertEqual(self.call_error(sh, '4440000'), 'not in CALL_ALLOW (voice.conf)')

    def test_allow_list(self):
        self.conf.write_text(self.conf.read_text() + 'CALL_ALLOW="4440000 +905320000000"\n')
        for sh in self.each_shell():
            self.reset()
            r = self.voice(sh, 'call', '4440001', '--json')
            self.assertEqual(json.loads(r.stdout)['error'], 'not in CALL_ALLOW (voice.conf)')
            self.assertEqual(self.at_log(), [])
            self.assertEqual(self.voice(sh, 'call', '+905320000000', '--json').returncode, 0)
            # exactly as written: another spelling of a listed number is not listed
            self.assertEqual(self.call_error(sh, '905320000000'), 'not in CALL_ALLOW (voice.conf)')
        # an emergency number stays refused even when listed
        self.conf.write_text(self.conf.read_text() + 'CALL_ALLOW="112 0090112"\n')
        for sh in self.each_shell():
            for n in ('112', '0090112'):
                self.assertEqual(self.call_error(sh, n), self.EMERGENCY_ERR)

    def test_through_sudo_only_the_api_grammar(self):
        for sh in self.each_shell():
            for args in (('call', '4440000', '--json', '--demo'), ('answer', '--demo', '--json'), ('audio', 'start'),
                         ('audio', 'stop'), ('watch',), ('demo',), ('tone',), ('echo',), ('events',),
                         ('call', '4440000', '--json', '--conf', '/tmp/x'), ('dtmf', '1', '--json', 'extra')):
                with self.subTest(args=args):
                    self.reset()
                    self.clcc(INCOMING)
                    r = self.voice(sh, *args, SUDO_USER='dikecphone')
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertEqual(self.at_log(), [])
            # the grammar itself still works through sudo
            self.reset()
            self.clcc(INCOMING)
            r = self.voice(sh, 'answer', '1', '--json', SUDO_USER='dikecphone')
            self.assertEqual(json.loads(r.stdout)['ok'], True)
            self.reset()
            r = self.voice(sh, 'dtmf', '12', '--json', SUDO_USER='dikecphone')
            self.assertEqual(json.loads(r.stdout)['sent'], 2)

    def test_call_modem_error(self):
        for sh in self.each_shell():
            self.reset()
            self.at_reply('ATD+904440000;', '+CME ERROR: 30\n')
            r = self.voice(sh, 'call', '+904440000', '--json')
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)['error'], '+CME ERROR: 30')
            r = self.voice(sh, 'call', '+904440000')
            self.assertEqual(r.stdout, '')
            self.assertIn('+CME ERROR: 30', r.stderr)
            # mu300-at's own refusal, as a user without the right to the AT channel gets it
            self.at_reply('ATD+904440000;', 'mu300-at: needs root (cannot write /run/mu300-at); try: sudo mu300-at\n')
            r = self.voice(sh, 'call', '+904440000', '--json')
            self.assertEqual(json.loads(r.stdout)['error'], 'mu300-at: needs root')

    def test_answer(self):
        for sh in self.each_shell():
            self.reset()
            self.clcc(INCOMING)
            r = self.voice(sh, 'answer', '--json')
            self.assertEqual(json.loads(r.stdout), {'v': 1, 'action': 'answer', 'ok': True, 'id': 1})
            self.assertEqual(self.at_log(), ['AT+CLCC', 'ATA'])
            # nothing ringing
            self.reset()
            r = self.voice(sh, 'answer', '--json')
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)['error'], 'no incoming call')
            self.assertNotIn('ATA', self.at_log())
            # a waiting call is taken with the active one put on hold
            self.reset()
            self.clcc(f'+CLCC: 1,0,0,0,0,"4440000",129\n+CLCC: 2,1,5,0,0,"{NUM}",145\nOK\n')
            r = self.voice(sh, 'answer', '2', '--json')
            self.assertEqual(json.loads(r.stdout)['id'], 2)
            self.assertEqual(self.at_log(), ['AT+CLCC', 'AT+CHLD=2'])

    def test_answer_waits(self):
        for sh in self.each_shell():
            self.reset()
            self.clcc(NONE, INCOMING)
            r = self.voice(sh, 'answer', '--wait', '5', '--json')
            self.assertEqual(json.loads(r.stdout)['ok'], True, r.stderr)
            self.assertEqual(self.at_log(), ['AT+CLCC', 'AT+CLCC', 'ATA'])

    def test_hangup_and_dtmf(self):
        for sh in self.each_shell():
            self.reset()
            self.assertEqual(json.loads(self.voice(sh, 'hangup', '--json').stdout)['ok'], True)
            self.assertEqual(self.at_log(), ['AT+CHUP'])
            self.assertEqual(json.loads(self.voice(sh, 'hangup', '2', '--json').stdout)['id'], 2)
            self.assertEqual(self.at_log(), ['AT+CHLD=12'])
            r = self.voice(sh, 'hangup', '1;+CFUN=0', '--json')
            self.assertEqual(r.returncode, 1)
            self.assertEqual(self.at_log(), [])
            r = self.voice(sh, 'dtmf', '1*#a', '--json')
            self.assertEqual(json.loads(r.stdout), {'v': 1, 'action': 'dtmf', 'ok': True, 'sent': 4})
            self.assertEqual(self.at_log(), ['AT+VTS=1', 'AT+VTS=*', 'AT+VTS=#', 'AT+VTS=A'])
            for bad in ('12;+CFUN=0', '1 2', 'E'):
                self.assertEqual(self.voice(sh, 'dtmf', bad).returncode, 1)
            self.assertEqual(self.at_log(), [])

    def test_usage(self):
        for sh in self.each_shell():
            r = self.voice(sh, 'nonsense')
            self.assertEqual(r.returncode, 2)
            for c in ('status', 'call NUMBER', 'answer', 'hangup', 'dtmf DIGITS', 'watch', 'events', 'audio start'):
                self.assertIn('mu300-voice ' + c, r.stderr)


class Watch(VoiceTest):
    HOOK = '#!/bin/sh\nprintf "%s|%s|%s|%s|%s|%s\\n" "$CALL_STATE" "$CALL_PREV_STATE" "$CALL_ID" "$CALL_DIR" ' \
           '"$NUMBER" "$CALL_EVENT" >> "$STUBLOG/hook.log"\n'

    def hook(self, name, body=None, mode=0o755):
        self.hooks.mkdir(exist_ok=True)
        os.chmod(self.hooks, 0o755)
        p = self.hooks / name
        p.write_text(body or self.HOOK)
        p.chmod(mode)
        return p

    def watch(self, sh, rounds):
        return self.voice(sh, 'watch', MU300_VOICE_ROUNDS=rounds)

    def test_events_and_hooks(self):
        self.hook('10-log.sh')
        self.hook('20-group-writable.sh', self.HOOK.replace('hook.log', 'bad.log'), 0o775)
        self.hook('30-not-executable.sh', self.HOOK.replace('hook.log', 'bad.log'), 0o644)
        for sh in self.each_shell():
            self.reset()
            (self.tmp / 'hook.log').unlink(missing_ok=True)
            self.clcc(NONE, INCOMING, ACTIVE, NONE)
            r = self.watch(sh, 4)
            self.assertEqual(r.returncode, 0, r.stderr)
            feed = [json.loads(l) for l in (self.run_dir / 'events.jsonl').read_text().splitlines()]
            calls = [(e['state'], e['prev'], e['id'], e['dir'], e['number']) for e in feed if e['event'] == 'call']
            self.assertEqual(calls, [('incoming', 'none', 1, 'in', NUM), ('active', 'incoming', 1, 'in', NUM),
                                     ('ended', 'active', 1, 'in', NUM)])
            self.assertEqual((self.tmp / 'hook.log').read_text().splitlines(), [
                f'incoming|none|1|in|{NUM}|call', f'active|incoming|1|in|{NUM}|call', f'ended|active|1|in|{NUM}|call'])
            self.assertFalse((self.tmp / 'bad.log').exists())
            self.assertIn('20-group-writable.sh not run', r.stderr)
            # the snapshot is the state at the end, the logs never have the number
            snap = json.loads((self.run_dir / 'state.json').read_text())
            self.assertEqual((snap['event'], snap['calls']), ('snapshot', []))
            self.assertNotIn(NUM, r.stderr + r.stdout)
            self.assertIn('+90********40', r.stderr)
            self.assertEqual(self.at_log()[0], 'AT+CLIP=1')

    def test_modem_silence_is_not_a_hangup(self):
        self.clcc(ACTIVE)
        for sh in self.each_shell():
            self.reset()
            self.clcc(ACTIVE, 'mu300-at: busy\n', ACTIVE)
            self.watch(sh, 3)
            states = [json.loads(l)['state'] for l in (self.run_dir / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(states, ['active'])

    def test_hidden_number_and_unsafe_hook_directory(self):
        self.hook('10-log.sh')
        for sh in self.each_shell():
            self.reset()
            (self.tmp / 'hook.log').unlink(missing_ok=True)
            self.clcc('+CLCC: 3,1,4,0,0,"",128\nOK\n', NONE)
            self.watch(sh, 2)
            feed = [json.loads(l) for l in (self.run_dir / 'events.jsonl').read_text().splitlines()]
            self.assertEqual([(e['id'], e['number']) for e in feed], [(3, None), (3, None)])
            self.assertEqual((self.tmp / 'hook.log').read_text().splitlines()[0], 'incoming|none|3|in||call')
        os.chmod(self.hooks, 0o777)
        try:
            for sh in self.each_shell():
                self.reset()
                (self.tmp / 'hook.log').unlink(missing_ok=True)
                self.clcc(INCOMING, NONE)
                r = self.watch(sh, 2)
                self.assertFalse((self.tmp / 'hook.log').exists())
                self.assertIn('none run', r.stderr)
        finally:
            os.chmod(self.hooks, 0o755)

    def test_permissions(self):
        for sh in self.each_shell():
            self.reset()
            self.clcc(INCOMING)
            self.watch(sh, 1)
            mode = lambda p: (p.stat().st_mode & 0o777, p.stat().st_gid)
            self.assertEqual(mode(self.run_dir), (0o710, os.getgid()))
            self.assertEqual(mode(self.run_dir / 'events.jsonl'), (0o640, os.getgid()))
            self.assertEqual(mode(self.run_dir / 'state.json'), (0o640, os.getgid()))
            # without the group on the system: root's alone
            self.reset()
            self.clcc(INCOMING)
            self.voice(sh, 'watch', MU300_VOICE_ROUNDS=1, MU300_GROUP_FILE=self.tmp / 'nogroup')
            self.assertEqual(self.run_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.run_dir / 'events.jsonl').stat().st_mode & 0o777, 0o600)

    def test_feed_rotates(self):
        for sh in self.each_shell():
            self.reset()
            self.clcc(INCOMING, ACTIVE, NONE, INCOMING, NONE)
            self.voice(sh, 'watch', MU300_VOICE_ROUNDS=5, MU300_VOICE_FEED_MAX=300)
            self.assertTrue((self.run_dir / 'events.jsonl.1').exists())
            for f in ('events.jsonl', 'events.jsonl.1'):
                for l in (self.run_dir / f).read_text().splitlines():
                    json.loads(l)


@unittest.skipUnless(shutil.which('cc'), 'no C compiler')
class EventSocket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp(prefix='mu300-ev-'))
        cls.exe = cls.d / 'mu300-voice-events'
        subprocess.run(['cc', '-Wall', '-Werror', '-O2', '-o', str(cls.exe), str(EVENTS_C)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def setUp(self):
        # short: a unix socket path has ~100 bytes
        self.run = Path(tempfile.mkdtemp(prefix='ve', dir='/tmp'))
        self.sock, self.feed, self.snap = self.run / 's', self.run / 'events.jsonl', self.run / 'state.json'
        self.snap.write_text('{"v":1,"event":"snapshot","calls":[]}\n')
        self.feed.write_text('{"old":1}\n')
        group = grp.getgrgid(os.getgid()).gr_name
        self.p = subprocess.Popen([str(self.exe), str(self.sock), str(self.feed), str(self.snap), group])
        for _ in range(100):
            if self.sock.exists():
                break
            time.sleep(0.02)

    def tearDown(self):
        self.p.terminate()
        self.p.wait(5)
        shutil.rmtree(self.run, ignore_errors=True)

    def client(self):
        c = socket.socket(socket.AF_UNIX)
        for _ in range(100):    # the file exists from bind(), the socket listens a moment later
            try:
                c.connect(str(self.sock))
                break
            except (ConnectionRefusedError, FileNotFoundError):
                time.sleep(0.02)
        c.settimeout(3)
        f = c.makefile('r')
        self.addCleanup(c.close)
        self.addCleanup(f.close)
        return c, f

    def append(self, *lines):
        with open(self.feed, 'a') as f:
            f.write(''.join(l + '\n' for l in lines))

    def test_snapshot_then_lines_to_every_reader(self):
        a, fa = self.client()
        # the mode is final before the first reader can connect
        self.assertEqual(self.sock.stat().st_mode & 0o777, 0o660)
        b, fb = self.client()
        for f in (fa, fb):
            self.assertEqual(json.loads(f.readline())['event'], 'snapshot')
        a.sendall(b'{"action":"call","number":"112"}\n' * 100)   # clients are never listened to
        self.append('{"n":1}', '{"n":2}')
        for f in (fa, fb):
            self.assertEqual([json.loads(f.readline())['n'] for _ in range(2)], [1, 2])
        b.close()
        self.append('{"n":3}')
        self.assertEqual(json.loads(fa.readline())['n'], 3)

    def test_rotation_and_partial_lines(self):
        a, fa = self.client()
        fa.readline()
        with open(self.feed, 'a') as f:
            f.write('{"n":')
            f.flush()
            time.sleep(0.3)
            f.write('1}\n')
        self.assertEqual(json.loads(fa.readline())['n'], 1)
        self.append('{"n":2}')
        os.rename(self.feed, str(self.feed) + '.1')
        self.feed.write_text('{"n":3}\n')
        self.assertEqual([json.loads(fa.readline())['n'] for _ in range(2)], [2, 3])

    def test_stops_and_removes_the_socket(self):
        self.p.terminate()
        self.p.wait(5)
        self.assertFalse(self.sock.exists())


class Examples(unittest.TestCase):
    def test_python_client_decides(self):
        sys.path.insert(0, str(EXAMPLE))
        try:
            import voice_client
        finally:
            sys.path.pop(0)
        ev = {'v': 1, 'event': 'call', 'id': 2, 'state': 'incoming', 'prev': 'none', 'dir': 'in', 'number': NUM}
        self.assertEqual(voice_client.action(ev, answer=True), ['/opt/mu300/bin/mu300-voice', 'answer', '2', '--json'])
        self.assertIsNone(voice_client.action(ev, answer=False))
        self.assertIsNone(voice_client.action(dict(ev, state='active'), answer=True))
        self.assertIsNone(voice_client.action({'v': 1, 'event': 'snapshot', 'calls': []}, answer=True))
        self.assertIn('+90********40', voice_client.describe(ev))

    def test_shell_examples_parse(self):
        for p in list(EXAMPLE.glob('*.sh')) + [TEMPLATES / 'openwrt-fw4-sip-lan.sh', TEMPLATES / 'dikecphone.init']:
            with self.subTest(p=p.name):
                self.assertEqual(subprocess.run(['sh', '-n', str(p)]).returncode, 0)


class Firewall(unittest.TestCase):
    def test_drop_ins_load_after_the_base_rules_and_never_instead(self):
        unit = (TOP / 'rootfs/overlay/etc/systemd/system/mu300-firewall.service').read_text()
        lines = [l for l in unit.splitlines() if l.startswith('ExecStart')]
        self.assertEqual(lines[0], 'ExecStart=/usr/sbin/nft -f /etc/mu300/firewall.nft')
        # a broken drop-in neither fails the unit nor takes the base rules with it
        self.assertTrue(lines[1].startswith('ExecStart=-/bin/sh -c'))
        self.assertIn('/etc/mu300/firewall.d/*.nft', lines[1])
        self.assertIn('$$f', lines[1])
        self.assertNotIn('include', (TOP / 'rootfs/overlay/etc/mu300/firewall.nft').read_text())

    def test_sip_drop_in_is_lan_only(self):
        nft = (TEMPLATES / 'sip-lan.nft').read_text()
        self.assertIn('table inet mu300_filter', nft)
        self.assertIn('hook input priority filter - 1', nft)
        self.assertIn('iifname $LAN_IFACES return', nft)
        # it only ever drops: no rule accepts (the chain's policy is accept, so the base rules still decide the rest)
        rules = [l.strip() for l in nft.splitlines() if l.strip() and not l.lstrip().startswith(('#', 'type '))]
        self.assertFalse([r for r in rules if r.endswith('accept')], rules)
        for port in ('5060', '20000-20200'):
            self.assertIn(port, nft)
        uci = (TEMPLATES / 'openwrt-fw4-sip-lan.sh').read_text()
        self.assertIn("src='lan'", uci)
        self.assertNotRegex(uci, r"src='(wan|\*)'")

    @unittest.skipUnless(shutil.which('nft') and os.geteuid() == 0, 'needs nft and root')
    def test_sip_drop_in_checks(self):
        base = TOP / 'rootfs/overlay/etc/mu300/firewall.nft'
        with tempfile.NamedTemporaryFile('w', suffix='.nft') as f:
            f.write(base.read_text() + '\n' + (TEMPLATES / 'sip-lan.nft').read_text())
            f.flush()
            r = subprocess.run(['nft', '-c', '-f', f.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


class Docs(unittest.TestCase):
    def test_the_contract_is_written_down(self):
        doc = (TOP / 'docs' / 'voice-api.md').read_text()
        for s in ('status --json', 'events.sock', 'events.jsonl', '/etc/mu300/voice.d', 'CALL_STATE', 'CALL_ID',
                  'NUMBER', 'mu300voice', 'downlink', 'uplink', 'S16_LE', 'firewall.d', 'mu300-at', 'nr1', 'nr2',
                  'mu300-sms send', 'sms send'):
            self.assertIn(s, doc)


if __name__ == '__main__':
    unittest.main()
