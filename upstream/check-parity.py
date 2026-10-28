#!/usr/bin/env python3
"""Nothing the 5.4 kernel has may be missing from mainline without saying so (upstream/parity-5.4.txt).

    check-parity.py                                  the repository: CI (tests/test_parity.py) and anyone
    check-parity.py --mainline OUT [--record]        a mainline build (build-modules.sh, make-bundle.sh), or
                                                     a kernel bundle (OUT = mu300-kernel-X.Y.tar.gz)
    check-parity.py --5.4 OUT                        a 5.4 build (kernel/build-all.sh): records it, then checks

What 5.4 has, three kinds of items:
  * module NAME / builtin NAME - every module of the 5.4 build (out/modules, out/modules-u30air) and every object of
    its modules.builtin, recorded in parity/5.4-build.list by the 5.4 build together with a hash of what the 5.4
    build is made from (kernel/: config, fragments, build scripts). A change there without a new record fails here.
  * extra NAME - the modules kernel/build-display.sh builds for the 5.4 display experiment.
  * what a board shows at run time, from parity-inventory.sh: drivers with a bound device, thermal zones, devfreq,
    cpufreq, power supplies, Type-C ports, LEDs, regulators, misc devices, input devices, ... (parity/BOARD-5.4.inv,
    compared with the same board's mainline inventory, parity/BOARD-X.Y.inv).
An item that mainline has under the same name - a module or built-in object of that name in every mainline series
of parity/mainline.list, or the same line in the board's mainline inventory - needs no entry. Every other one needs a
line in parity-5.4.txt:
    KIND NAME ok REF...            covered; REF: = (a module/built-in of the same name), ko:NAME, cfg:SYMBOL (=y or
                                   =m), A|B (either), and as run-time proof bind:BUS/DRIVER or has:KIND/NAME (in a
                                   mainline inventory). At least one ko:/cfg:/= - the mainline build checks those.
    KIND NAME missing group:G boards:B[,B] # why     not on mainline yet (the porting list)
    KIND NAME na [boards:B] # why                    not applicable, with the technical reason
The mainline build fails when a ko:/cfg:/= of an ok line, or a same-name match, is not in what it built; --record
writes what it built into parity/mainline.list (the names this file and the 5.4 lists use).
"""
import hashlib
import os
import re
import sys
from pathlib import Path

UP = Path(__file__).resolve().parent
TOP = UP.parent
PARITY = UP / 'parity-5.4.txt'
DIR = UP / 'parity'
BUILD54 = DIR / '5.4-build.list'
MAINLINE = DIR / 'mainline.list'
# what the 5.4 build is made from: a change to any of them can change its set of modules
INPUTS54 = ['kernel/f50-stock-B09.config', 'kernel/mu300-linux.fragment', 'kernel/u30air.fragment',
            'kernel/build-all.sh', 'kernel/build-linux.sh', 'kernel/build-u30air.sh', 'kernel/build-wlan.sh',
            'kernel/build-mali.sh', 'kernel/build-display.sh']
DEVICE_KINDS = {'driver', 'tz', 'cooling', 'devfreq', 'cpufreq', 'cpuidle', 'hwrng', 'psy', 'typec', 'extcon', 'led',
                'regulator', 'misc', 'udc', 'input', 'class'}
KINDS = {'module', 'builtin', 'extra'} | DEVICE_KINDS
BOARDS = {'f50', 'u30air', 'v50'}


def norm(name):
    return name.replace('-', '_')


def inputs_hash(top=TOP):
    h = hashlib.sha256()
    for f in INPUTS54:
        h.update(f.encode() + b'\0' + (top / f).read_bytes() + b'\0')
    return h.hexdigest()


class Entry:
    def __init__(self, kind, name, status, refs, reason, line):
        self.kind, self.name, self.status, self.refs, self.reason, self.line = kind, name, status, refs, reason, line

    def field(self, key):
        return next((r[len(key) + 1:] for r in self.refs if r.startswith(key + ':')), None)


def parse_parity(path=PARITY):
    entries, errors = {}, []
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        body, _, reason = raw.partition('#')
        t = body.split()
        if not t:
            continue
        where = '%s:%d' % (path.name, n)
        if len(t) < 3:
            errors.append('%s: want KIND NAME STATUS ...' % where)
            continue
        kind, name, status, refs = t[0], t[1], t[2], t[3:]
        if kind in ('module', 'builtin', 'extra'):
            name = norm(name)
        reason = reason.strip()
        if kind not in KINDS:
            errors.append('%s: unknown kind %s' % (where, kind))
        elif (kind, name) in entries:
            errors.append('%s: %s %s is listed twice' % (where, kind, name))
        e = Entry(kind, name, status, refs, reason, where)
        if status == 'ok':
            if not any(r == '=' or r.startswith(('ko:', 'cfg:')) for alt in refs for r in alt.split('|')):
                errors.append('%s: %s %s: an ok line needs a ko:, cfg: or = the mainline build can check' % (where, kind, name))
            for alt in refs:
                for r in alt.split('|'):
                    if r != '=' and not re.match(r'(ko|cfg|bind|has):\S+$', r):
                        errors.append('%s: %s %s: unknown reference %s' % (where, kind, name, r))
            if '=' in refs and kind not in ('module', 'builtin', 'extra'):
                errors.append('%s: = is for modules; use bind: or has:' % where)
        elif status in ('missing', 'na'):
            if not reason:
                errors.append('%s: %s %s is %s: say why after #' % (where, kind, name, status))
            if status == 'missing' and not e.field('group'):
                errors.append('%s: %s %s is missing: name its group:' % (where, kind, name))
            b = e.field('boards')
            if status == 'missing' and not b:
                errors.append('%s: %s %s is missing: name the boards: it affects' % (where, kind, name))
            if b and not set(b.split(',')) <= BOARDS:
                errors.append('%s: boards: %s (known: %s)' % (where, b, ','.join(sorted(BOARDS))))
            for r in refs:
                if not r.startswith(('group:', 'boards:')):
                    errors.append('%s: %s %s: a %s line takes group: and boards: only' % (where, kind, name, status))
        else:
            errors.append('%s: status %s (ok, missing or na)' % (where, status))
        entries[(kind, name)] = e
    return entries, errors


def read_build54(path=BUILD54):
    items, digest = set(), None
    for l in path.read_text().splitlines():
        if l.startswith('# inputs '):
            digest = l.split()[2]
        elif l.strip() and not l.startswith('#'):
            k, n = l.split()
            items.add((k, n))
    return items, digest


def display_extras(top=TOP):
    s = (top / 'kernel/build-display.sh').read_text()
    return {('extra', norm(m)) for m in re.findall(r'([\w-]+)\.ko\b', s)}


def read_inv(path):
    items = set()
    for l in path.read_text().splitlines():
        if l.strip() and not l.startswith('#'):
            k, _, n = l.partition(' ')
            items.add((k, n.strip().replace(' ', '_')))
    return items


def inventories(d=DIR):
    """{board: {kernel: items}} from BOARD-KERNEL.inv"""
    out = {}
    for f in sorted(d.glob('*.inv')):
        board, _, kernel = f.stem.rpartition('-')
        out.setdefault(board, {})[kernel] = read_inv(f)
    return out


def read_mainline(path=MAINLINE):
    """{series: {'ko': set, 'cfg': set}}"""
    out = {}
    if not path.exists():
        return out
    for l in path.read_text().splitlines():
        if not l.strip() or l.startswith('#'):
            continue
        kind, name, *series = l.split()
        for s in series:
            out.setdefault(s, {'ko': set(), 'cfg': set()})[kind].add(name)
    return out


def names(ko_files, builtin_text, config_text):
    """what a mainline build has: ko (module and built-in object names) and cfg (symbols =y/=m), and its series"""
    ko, cfg, series = set(), set(), None
    for f in ko_files:
        if f.endswith('.ko'):
            ko.add(norm(f[:-3]))
    for l in builtin_text.splitlines():
        if l.strip():
            ko.add(norm(l.strip().rsplit('/', 1)[-1].rsplit('.ko', 1)[0]))
    for l in config_text.splitlines():
        m = re.match(r'CONFIG_(\w+)=[ym]$', l)
        if m:
            cfg.add(m.group(1))
        m = re.match(r'# Linux/\w+ (\d+)\.(\d+)', l)
        if m and not series:
            series = '%s.%s' % m.groups()
    return {'ko': ko, 'cfg': cfg}, series


def build_names(modules_dir, builtin, config):
    """names() of a build directory (upstream/out: modules/*.ko, modules.builtin, kernel.config)"""
    return names(os.listdir(modules_dir), Path(builtin).read_text(), Path(config).read_text())


def bundle_names(path):
    """names() of a kernel bundle (make-bundle.sh, a release's mu300-kernel-X.Y.tar.gz) - read from the archive, not
    unpacked: xt_HL.ko and xt_hl.ko are two modules, and a file system that ignores case keeps one (FINDINGS 212)"""
    import tarfile
    with tarfile.open(path) as t:
        get = lambda n: t.extractfile(t.getmember('./' + n)).read().decode()
        return names(get('modules.list').split(), get('modules.builtin'), get('kernel.config'))


def has_ref(r, name, have):
    """does a build (have: {'ko','cfg'}) have reference r (one of A|B) of the item called name?"""
    for alt in r.split('|'):
        if alt == '=' and name in have['ko']:
            return True
        if alt.startswith('ko:') and norm(alt[3:]) in have['ko']:
            return True
        if alt.startswith('cfg:') and alt[4:] in have['cfg']:
            return True
    return False


def build_refs(e):
    """the references of an ok line a build can check (bind:/has: need a board)"""
    out = []
    for r in e.refs:
        alts = [a for a in r.split('|') if a == '=' or a.startswith(('ko:', 'cfg:'))]
        if alts:
            out.append('|'.join(alts))
    return out


def items54(d=DIR):
    return read_build54(d / '5.4-build.list')[0]


def check_build(entries, items, have, label):
    """a mainline build against the file: every ok reference there, every unlisted 5.4 module/built-in there by name"""
    errors = []
    for e in entries.values():
        if e.status != 'ok':
            continue
        for r in build_refs(e):
            if not has_ref(r, e.name, have):
                errors.append('%s %s (%s): %s is not in %s' % (e.kind, e.name, e.line, r, label))
    for k, n in sorted(items):
        if k in ('module', 'builtin', 'extra') and (k, n) not in entries and n not in have['ko']:
            errors.append('%s %s of 5.4 is not in %s under that name: map it in %s' % (k, n, label, PARITY.name))
    return errors


def check_repo(top=TOP, d=DIR, parity=None):
    """everything that needs no build: the file, the recorded 5.4 build and mainline builds, the board inventories"""
    entries, errors = parse_parity(parity or d.parent / 'parity-5.4.txt')
    b54, digest = read_build54(d / '5.4-build.list')
    if digest != inputs_hash(top):
        errors.append('parity/5.4-build.list was recorded from other 5.4 build inputs (%s): build 5.4 with '
                      'kernel/build-all.sh, which records it again' % ', '.join(INPUTS54))
    mainline = read_mainline(d / 'mainline.list')
    if not mainline:
        errors.append('parity/mainline.list is empty: check-parity.py --mainline OUT --record after a mainline build')
    invs = inventories(d)
    mainline_inv = set()
    for board, kernels in invs.items():
        for k, items in kernels.items():
            if k != '5.4':
                mainline_inv |= {('%s/%s' % i) for i in items}

    def covered(kind, name):
        if kind in ('module', 'builtin', 'extra'):
            return all(name in s['ko'] for s in mainline.values()) and bool(mainline)
        return False

    want = set(b54)
    every54 = set(b54)
    if {i for i in b54 if i[0] == 'extra'} != display_extras(top):
        errors.append('parity/5.4-build.list does not have the modules of kernel/build-display.sh as extra lines')
    for board, kernels in invs.items():
        if '5.4' not in kernels:
            continue
        others = [v for k, v in kernels.items() if k != '5.4']
        if not others:
            errors.append('parity/%s-5.4.inv has no mainline inventory of the same board next to it' % board)
        every54 |= kernels['5.4']
        for item in kernels['5.4']:
            if not any(item in o for o in others):
                want.add(item)
    for kind, name in sorted(want):
        if (kind, name) not in entries and not covered(kind, name):
            errors.append('%s %s: 5.4 has it, mainline has nothing of that name, and %s does not say what '
                          'stands for it' % (kind, name, PARITY.name))
    for (kind, name), e in sorted(entries.items()):
        if (kind, name) not in every54:
            errors.append('%s: %s %s is not an item of the 5.4 build or a 5.4 inventory (any more)' % (e.line, kind, name))
        if e.status == 'ok':
            for series, have in sorted(mainline.items()):
                for r in build_refs(e):
                    if not has_ref(r, name, have):
                        errors.append('%s: %s %s: %s is not in mainline %s (parity/mainline.list)' % (e.line, kind, name, r, series))
            for r in e.refs:
                for alt in r.split('|'):
                    if alt.startswith(('bind:', 'has:')):
                        it = alt[5:] if alt.startswith('bind:') else alt[4:]
                        it = ('driver/' + it) if alt.startswith('bind:') else it
                        if it not in mainline_inv:
                            errors.append('%s: %s %s: %s is in no mainline inventory (parity/*.inv)' % (e.line, kind, name, alt))
        elif e.status == 'missing' and covered(kind, name):
            errors.append('%s: %s %s is marked missing, but mainline has it by name now' % (e.line, kind, name))
    return entries, errors


def record_mainline(have, series, entries, items, path=MAINLINE):
    """parity/mainline.list keeps, per series, the names that matter: every 5.4 module/built-in and every reference"""
    names = {'ko': {n for k, n in items if k in ('module', 'builtin', 'extra')}, 'cfg': set()}
    for e in entries.values():
        for r in e.refs:
            for alt in r.split('|'):
                if alt.startswith('ko:'):
                    names['ko'].add(norm(alt[3:]))
                elif alt.startswith('cfg:'):
                    names['cfg'].add(alt[4:])
                elif alt == '=':
                    names['ko'].add(e.name)
    old = {}
    if path.exists():
        for l in path.read_text().splitlines():
            if l.strip() and not l.startswith('#'):
                kind, name, *ss = l.split()
                old[(kind, name)] = set(ss) - {series}
    for kind in ('ko', 'cfg'):
        for n in names[kind]:
            s = old.setdefault((kind, n), set())
            if n in have[kind]:
                s.add(series)
    key = lambda v: [int(x) for x in v.split('.')]
    lines = ['# check-parity.py --mainline OUT --record: per mainline series, which of the names parity-5.4.txt and',
             '# the 5.4 build use it has (ko: a module or built-in object; cfg: a symbol =y or =m)']
    for (kind, n), ss in sorted(old.items()):
        if ss:
            lines.append(' '.join([kind, n] + sorted(ss, key=key)))
    path.write_text('\n'.join(lines) + '\n')


def record_54(out, path=BUILD54, top=TOP):
    out = Path(out)
    items = set()
    for d in ('modules', 'modules-u30air'):
        for f in (out / d).glob('*.ko'):
            items.add(('module', norm(f.name[:-3])))
    for l in (out / 'modules.builtin').read_text().splitlines():
        if l.strip():
            items.add(('builtin', norm(l.strip().rsplit('/', 1)[-1].rsplit('.ko', 1)[0])))
    lines = ['# check-parity.py --5.4 OUT (kernel/build-all.sh): the modules (F50 and U30 Air sets) and built-in',
             '# objects of the 5.4 build', '# inputs %s' % inputs_hash(top)]
    lines += ['%s %s' % i for i in sorted(items | display_extras(top))]
    path.write_text('\n'.join(lines) + '\n')


def main(argv):
    if argv[:1] == ['--5.4']:
        record_54(argv[1])
        entries, errors = check_repo()
    elif argv[:1] == ['--mainline']:
        out = Path(argv[1])
        rest = argv[2:]
        builtin = out / 'modules.builtin'
        config = out / 'kernel.config'
        while rest and rest[0] in ('--builtin', '--config'):
            if rest[0] == '--builtin':
                builtin = Path(rest[1])
            else:
                config = Path(rest[1])
            rest = rest[2:]
        entries, errors = parse_parity()
        if out.name.endswith('.tar.gz'):
            have, series = bundle_names(out)
        else:
            have, series = build_names(out / 'modules', builtin, config)
        items = items54()
        errors += check_build(entries, items, have, 'mainline %s' % series)
        # what it has is recorded whether or not the file is complete for it: the repository's check then shows
        # what is missing in which series
        if '--record' in rest:
            record_mainline(have, series, entries, items)
    else:
        entries, errors = check_repo()
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit('check-parity: %d problem(s): nothing 5.4 has may go missing on mainline unsaid (%s)'
                 % (len(errors), PARITY.relative_to(TOP)))
    n = {}
    for e in entries.values():
        n[e.status] = n.get(e.status, 0) + 1
    print('check-parity: %d mapped items of 5.4: %d ok, %d missing, %d not applicable'
          % (len(entries), n.get('ok', 0), n.get('missing', 0), n.get('na', 0)))


if __name__ == '__main__':
    main(sys.argv[1:])
