#!/usr/bin/env python3
"""飞花令 offline checks: dial geometry (mirrors DialView.java) + strict position lookup.

Nothing here renders anything; these guard the arithmetic that the on-screen dial depends on,
which uiautomator cannot see (a View draws itself, so wedges never appear as nodes).
"""
import math
import os
import re
import sqlite3
import sys

SRC = os.environ.get('POETRY_SRC', '/root/poetry/app/src/com/poetry/app/')
DB = sys.argv[1] if len(sys.argv) > 1 else '/root/poetry/out/poetry_lite.db'
fails = []


def ck(cond, msg):
    if not cond:
        fails.append(msg)


def read(name):
    with open(SRC + name, encoding='utf8') as f:
        return f.read()


dial = read('DialView.java')
act = read('FeihuaActivity.java')

# --- constants must agree with what the mirror below assumes -------------------------------
ck('SLOTS = 8' in dial, 'DialView.SLOTS changed; update this mirror')
slots = 8
step = 360.0 / slots

# --- 1. wedge -> pos mapping is total and invertible ---------------------------------------
for s in range(slots):
    pos = None if s <= 0 else s - 1                      # posOf
    back = 0 if pos is None else min(7, max(0, pos + 1))  # slotOf (clamped like the Java)
    ck(back == s, 'posOf/slotOf roundtrip broke at slot %d' % s)

# --- 2/3/3b. Evaluate the REAL Java expressions, not a re-implementation -------------------
# A mirror written in Python proves nothing about the shipped code (it stayed green while the
# Java landed 22.5deg off the wedge and while the countdown floored to 0). So each formula is
# scraped out of DialView.java, translated mechanically and eval'd here.
def py(e):
    # Drop the (int) casts rather than translate them: both scraped expressions wrap a
    # floor/ceil, which already return whole numbers in Python. has_int_cast() guards that
    # assumption, so if someone swaps floor for a bare division the scrape fails loudly.
    e = re.sub(r'\(\s*int\s*\)', '', e)
    e = e.replace('Math.floor', 'math.floor').replace('Math.ceil', 'math.ceil')
    return re.sub(r'(?<=[\d)])([df])(?![a-zA-Z])', '', e)      # 360d/360f -> 360


def cast_ok(e, what):
    ck('(int)' not in e or 'Math.floor' in e or 'Math.ceil' in e,
       '%s casts to int without floor/ceil; py() would mis-evaluate it' % what)


def grab(pattern, src, what):
    m = re.search(pattern, src)
    ck(m is not None, 'could not scrape %s from DialView.java' % what)
    if m: cast_ok(m.group(1), what)
    return m.group(1) if m else None


n_slots = int(re.search(r'SLOTS = (\d+)', dial).group(1))
step = 360.0 / n_slots
spin_ms = float(re.search(r'SPIN_MS = (\d+)', dial).group(1))
hit_e = grab(r'int hit = (.*);', dial, 'the wedge hit test')
delta_e = grab(r'float delta = (.*);', dial, 'the sweep delta')
target_e = grab(r'float target = (.*);', dial, 'the sweep target')
secs_e = grab(r'int secs = (.*);', dial, 'the countdown tick')
ck(all(s is not None for s in (hit_e, delta_e, target_e, secs_e)), 'formula scraping incomplete')
ck(n_slots == slots, 'DialView.SLOTS is %d but this mirror assumes %d' % (n_slots, slots))
ck(spin_ms == 5000.0, 'DialView.SPIN_MS is %s, the feature promises 5s' % spin_ms)

env0 = {'math': math, 'STEP': step, 'SLOTS': n_slots}


def hit(deg):
    return eval(py(hit_e), dict(env0, deg=deg))


for i in range(n_slots):
    centre = i * step
    ck(hit(centre) == i, 'wedge %d centre at %.1f picked as %d' % (i, centre, hit(centre)))
    for off in (-20, -10, 10, 20):
        want = int(round((centre + off) / step)) % n_slots
        ck(hit(centre + off) == want, 'wedge %d touched %+d -> %d, want %d'
           % (i, off, hit(centre + off), want))
ck(hit(359.9) == 0 and hit(-0.1) == 0, 'wrap-around at the top pointer is wrong')


def sweep(hand, slot, turns):
    env = dict(env0, handAngle=hand, slot=slot, turns=turns)
    env['delta'] = eval(py(delta_e), env)
    return eval(py(target_e), env)


for hand in (0.0, 17.0, 44.9, 90.0, 180.0, 359.0, 723.4):
    for slot in range(n_slots):
        for turns in (0, 1, 4):
            tgt = sweep(hand, slot, turns)
            ck(abs((tgt % 360.0) - slot * step) < 1e-4,
               'hand %.1f -> slot %d lands %.4f deg off the wedge centre' % (hand, slot, tgt % 360.0))
            ck(tgt >= hand, 'hand rewound: %.1f -> %.1f' % (hand, tgt))
            ck(tgt - hand >= turns * 360.0, 'sweep fell short of its %d turns' % turns)

# 4 whole turns on the timed spin, and the hand must still be centred on its wedge
ck('SPIN_MS, 1.25f, 4)' in dial.replace('\n', ' '), '开始 should spin 4 turns, not fewer')

# --- 3c. the spin must end even if the screen sleeps mid-sweep ------------------------------
# ObjectAnimator runs off frame callbacks. A MIUI screen that drops to Dozing produces no frames,
# onAnimationEnd never fires, and the hub stays on 抽令 with no 出句 dealt -- that was a real bug
# caught by the device suite. The escape hatch is a View.postDelayed timer, so assert it is wired.
ck('postDelayed(settleTimer' in dial, 'no timer escape hatch: a sleeping screen would strand the spin')
ck('if (!settled' in dial or 'if (settled) return' in dial, 'settle() must run exactly once')
ck('onAnimationEnd(android.animation.Animator a) { settle(); }' in dial,
   'the animator ending must route through settle(), not fire the callback directly')
ck(re.search(r'void settle\(\)\s*\{.*?cb\.onSettled\(selected\)', dial, re.S) is not None,
   'settle() should hand the landed wedge to the callback')
# removeCallbacks(null) on an attached view clears every message on the view root
ck(re.search(r'void clearSettleTimer\(\)\s*\{\s*if \(settleTimer != null\) \{', dial) is not None,
   'removeCallbacks must never be called with a null Runnable')
ck('removeCallbacks(settleTimer)' in dial and dial.count('removeCallbacks(') == 1,
   'clearSettleTimer should be the only removeCallbacks call site')


class _Anim:
    """Stands in for ValueAnimator inside the scraped countdown expression."""
    def __init__(self, f): self.f = f
    def getAnimatedFraction(self): return self.f


def tick(frac):
    return eval(py(secs_e), dict(env0, SPIN_MS=spin_ms, v=_Anim(frac)))


ticks = [tick(f) for f in (0.0, 0.2, 0.4, 0.6, 0.8, 0.99)]
ck(ticks == [5, 4, 3, 2, 1, 1], 'countdown ticks %s over %ds, want [5, 4, 3, 2, 1, 1]'
   % (ticks, spin_ms / 1000))
ck(tick(1.0) == 0, 'countdown must reach 0 only as the hand settles')

# --- 4. hub: 开始 + 认输 only, two distinct colours, shared hub radius ---------------------
colours = re.findall(r'roundBtn\("([^"]+)",\s*(0x[0-9A-Fa-f]{8})', act)
ck([c[0] for c in colours] == ['开始', '认输'], 'hub buttons should be 开始 then 认输, got %s' % [c[0] for c in colours])
ck('roundBtn("停止"' not in act, '停止 button should be gone')
ck('private void stop()' not in act, 'the stop() handler should be gone')
ck(len(set(c[1].lower() for c in colours)) == 2, 'the two buttons must not share a colour')
inner_frac = re.search(r'innerR\(\)\s*\{\s*return outerR\(\)\s*\*\s*([0-9.]+)f', dial)
ck(inner_frac is not None, 'innerR() shape changed')
frac = float(inner_frac.group(1))
ck(dial.count('innerR()') >= 3, 'draw and touch should share innerR()')
# two stacked 52dp circles, 8dp apart: the upper circle's centre sits (26+8/2)=30dp above the
# hub centre, so its farthest point is hypot(26,30)+26 from the middle.
hub_r = frac * (min(262, 320) / 2.0 - 22)               # dp, narrow phone, block 262dp tall
btn, gap = 52.0, 8.0
upper_cy = btn / 2.0 + gap / 2.0
far = math.hypot(btn / 2.0, upper_cy) + btn / 2.0
ck(far <= hub_r, 'round buttons overflow the hub: %.1fdp > %.1fdp' % (far, hub_r))
ck('c.rotate(' not in dial, 'labels must stay upright; rotation flipped the lower wedges')
ck('spinRandom' in dial and 'spinRandom(' in act, '开始 should drive a timed random spin')
ck('isSpinning() return true' in dial or 'if (isSpinning()) return true' in dial,
   'taps during the spin should be swallowed')

# --- 5. strict lookup: no fall back from a position to "anywhere" --------------------------
db = open(SRC + 'PoemDb.java', encoding='utf8').read()
head = db[db.index('public int[] findLines'):]
i = head.index('if (pos != null)')
j = head.index('{', i)                      # brace-match the pos branch: the first `for` lives
depth, k = 0, j                             # INSIDE it, so a naive slice cut it short
while k < len(head):
    if head[k] == '{':
        depth += 1
    elif head[k] == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1
branch = head[j:k]
ck('return new int[0]' in branch, 'findLines fell back to any-position when pos is empty')
ck('postings(v, null)' not in branch, 'pos branch should only query fixed positions')


def decode(blob):
    out, shift, x, prev = [], 0, 0, 0
    for b in blob:
        b = b if isinstance(b, int) else b[0]
        x |= (b & 0x7f) << shift
        if b & 0x80:
            shift += 7
        else:
            prev += x
            out.append(prev)
            x = shift = 0
    return out


con = sqlite3.connect(DB)


def pool(ch, pos):
    if pos is None:
        r = con.execute('SELECT ids FROM char_index WHERE ch=?', (ch,)).fetchone()
    else:
        r = con.execute('SELECT ids FROM char_pos WHERE ch=? AND pos=?', (ch, str(pos))).fetchone()
    return 0 if r is None else len(decode(r[0]))


for ch in ('月', '花', '春', '山', '人', '风', '之'):
    sizes = [pool(ch, None)] + [pool(ch, p) for p in range(7)]
    ck(all(n > 0 for n in sizes), '令字 %s has an empty dial slot: %s' % (ch, sizes))
    for p in range(7):
        ck(pool(ch, p) <= pool(ch, None), '第%d字 pool for %s exceeds the any-position pool' % (p + 1, ch))

# a position that genuinely has nothing must yield 0, not the any-position pool
empty = con.execute('SELECT ch FROM char_pos GROUP BY ch HAVING MIN(CASE WHEN pos IN (\'20\',\'21\') '
                    'THEN 1 ELSE 0 END)=0').fetchone()
if empty:
    ch = empty[0]
    ck(pool(ch, 20) == 0 and pool(ch, None) > 0,
       'cannot demonstrate strictness on %s' % ch)

print('feihua dial + rule checks: %s' % ('ALL PASS' if not fails else 'FAIL'))
for f in fails:
    print('  FAIL ' + f)
sys.exit(1 if fails else 0)
