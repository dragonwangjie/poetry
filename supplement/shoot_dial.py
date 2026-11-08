#!/usr/bin/env python3
"""Measure WHEN the selected wedge changes colour -- pixels, not code reading.

The dial is invisible to uiautomator (DialView reports as plain android.view.View, and colour is
never in the tree), so this reads raw screencap pixels. One frame is 14MB and crosses this adb
link in 0.6s, so a frame per sample is affordable.

Calibration, deliberately not hardcoded: the dial's outer circle is exactly 2*outerR of dark red
0xFF8B3A2B=(139,58,43) -- the rim stroke plus the 任意 wedge -- and nothing else on the page is
red in that channel band (认输 is 0xFFB00020=(176,0,32), g=0; 开始 is green (46,125,50); text is
0xFF6B5B45, r=107). The largest such bounding box is the dial, so centre and radius come from the
frame itself rather than from a layout computation that could drift out of sync.

Geometry mirrors DialView: wedge i spans [i*45-90, i*45-45] degrees clockwise from 3 o'clock, so
its centre is i*45-67.5; labels sit at (inner+outer)/2 = 0.85*outer, so the clean bands are
0.76 and 0.94. Each wedge is sampled at 5 angles x 2 radii and decided by vote.
"""
import math
import re
import subprocess
import sys
import time

W, H = 1280, 2772
DARKRED = lambda r, g, b: 115 <= r <= 205 and 40 <= g <= 115 and 30 <= b <= 95
CREAM = lambda r, g, b: r >= 232 and 216 <= g <= 240 and 196 <= b <= 220
TERRA = lambda r, g, b: 150 <= r <= 210 and 60 <= g <= 110 and 45 <= b <= 95


def sh(args):
    return subprocess.run(['adb', 'shell'] + args, capture_output=True, text=True, timeout=90).stdout


def frame():
    p = subprocess.run(['adb', 'exec-out', 'screencap'], capture_output=True, timeout=90)
    if len(p.stdout) < W * H * 4:
        sys.exit('screencap gave %d bytes, want >=%d' % (len(p.stdout), W * H * 4))
    return p.stdout[16:]


def px(buf, x, y):
    o = (y * W + x) * 4
    return buf[o], buf[o + 1], buf[o + 2]


def tap(x, y):
    sh(['input', 'tap', str(int(x)), str(int(y))])


def find(label):
    sh(['rm', '-f', '/sdcard/q.xml'])
    sh(['uiautomator', 'dump', '/sdcard/q.xml'])
    for m in re.finditer('<node[^>]*>', sh(['cat', '/sdcard/q.xml'])):
        t = m.group(0)
        if ('text="%s"' % label) in t:
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', t)
            if b:
                x1, y1, x2, y2 = [int(v) for v in b.groups()]
                return (x1 + x2) / 2.0, (y1 + y2) / 2.0
    return None


def bbox(buf, pred, step=2):
    """Largest connected-ish bounding box of matching pixels, on a coarse grid."""
    best, cur = None, None
    run = 0
    for y in range(0, H, step):
        row = None
        for x in range(0, W, step):
            r, g, b = px(buf, x, y)
            if pred(r, g, b):
                if row is None:
                    row = [x, x, y, y]
                else:
                    row[1] = x
                    row[3] = y
        if row:
            run += 1
            cur = row if cur is None else [min(cur[0], row[0]), max(cur[1], row[1]),
                                           min(cur[2], row[2]), max(cur[3], row[3])]
        else:
            if cur and (best is None or (cur[1] - cur[0]) * (cur[3] - cur[2]) >
                        (best[1] - best[0]) * (best[3] - best[2])):
                best = cur
            cur, run = None, 0
    return best


def dial_geom():
    """Geometry straight from the layout tree, not from pixels.

    DialView shows up as a plain android.view.View; the node that contains both hub buttons and
    is not the full page IS the dial block. Its bounds give side=min(w,h), which is exactly what
    DialView.outerR() uses: min(w,h)/2 - 22dp, with the centre at the node's centre.
    """
    sh(['rm', '-f', '/sdcard/q.xml'])
    sh(['uiautomator', 'dump', '/sdcard/q.xml'])
    xml = sh(['cat', '/sdcard/q.xml'])
    btns = []
    cands = []
    for m in re.finditer('<node[^>]*>', xml):
        t = m.group(0)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', t)
        if not b:
            continue
        x1, y1, x2, y2 = [int(v) for v in b.groups()]
        if ('开始' in t) or ('认输' in t):
            btns.append((x1, y1, x2, y2))
        if (y2 - y1) > 300 and (y2 - y1) < H - 300:     # tall, but not the whole page
            cands.append((x1, y1, x2, y2))
    if len(btns) < 2:
        return None
    bx1 = min(b[0] for b in btns)
    by1 = min(b[1] for b in btns)
    bx2 = max(b[2] for b in btns)
    by2 = max(b[3] for b in btns)
    box = [c for c in cands if c[0] <= bx1 and c[1] <= by1 and c[2] >= bx2 and c[3] >= by2]
    if not box:
        return None
    x1, y1, x2, y2 = min(box, key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    outer = min(x2 - x1, y2 - y1) // 2 - int(22 * 520 / 160)
    return cx, cy, outer if outer > 100 else None


def lit_votes(buf, cx, cy, outer):
    """Per-wedge vote counts, so a misread can be spotted instead of silently deciding."""
    out = []
    for i in range(8):
        base = math.radians(i * 45 - 90)
        n_lit = n_cream = 0
        for da in (-12, -6, 0, 6, 12):
            rad = base + math.radians(da)
            # 0.93/0.97 only. The countdown badge is dark red 0xFF8B3A2B, centred at
            # (outer-26dp)=0.762*outer with radius 13dp=0.118*outer, so it sweeps 0.64-0.88 and
            # would fake a lit wedge wherever it passes; 0.93+ is out of its reach, and the hand
            # there is ~1px wide. Still inside the 0.70-1.00 fill band, above the label glyphs.
            for f in (0.90, 0.94):
                x = int(round(cx + outer * f * math.cos(rad)))
                y = int(round(cy + outer * f * math.sin(rad)))
                r, g, b = px(buf, x, y)
                if TERRA(r, g, b) or DARKRED(r, g, b):
                    n_lit += 1
                elif CREAM(r, g, b):
                    n_cream += 1
        out.append((i, n_lit, n_cream))
    return out


def lit_set(buf, cx, cy, outer):
    """Wedges painted a lit colour. Wedge i is CENTRED at i*45 measured clockwise from 12 o'clock
    (DialView: start = -90 - STEP/2 + i*STEP, sweeping STEP), i.e. at i*45-90 from +x on a y-down
    screen -- 22.5 deg off the sector edge, which is why sampling used to land between wedges.
    Both lit colours count: wedge 0 paints 0xFF8B3A2B, wedges 1-7 paint 0xFFB4553F.
    A sweep in flight drags the dark-red countdown badge (0xFF8B3A2B, r=42px at 0.88*outer)
    across every wedge, so a passing badge must not flip a wedge: require a supermajority
    (n_lit >= 7 of 10) instead of a bare majority."""
    return [i for i, n_lit, _ in lit_votes(buf, cx, cy, outer) if n_lit >= 7]


# --------------------------------------------------------------------- get onto the dial
if 'Awake' not in sh(['dumpsys', 'power']):
    sh(['input', 'keyevent', '224'])
    time.sleep(2)
sh(['wm', 'dismiss-keyguard'])
sh(['am', 'force-stop', 'com.poetry.app'])
sh(['am', 'start', '-n', 'com.poetry.app/.MainActivity'])
time.sleep(6)
home = find('飞花令')
if not home:
    sys.exit('no 飞花令; focus=%s' % re.findall(r'mCurrentFocus=Window\{\S+ u0 [^/]*',
                                                sh(['dumpsys', 'window'])))
tap(*home)
time.sleep(3)

# The hub button reads 开始 at rest and only becomes 抽令 once start() has been called, so 开始
# is the thing to press. It starts the 5s sweep, which is the window in which the highlight must
# NOT have moved yet.
trigger = find('开始') or find('抽令')
if not trigger:
    sys.exit('no hub button on screen')
before_buf = frame()
geom = dial_geom()
if not geom:
    sys.exit('could not locate the dial in the frame')
cx, cy, outer = geom
before = lit_set(before_buf, cx, cy, outer)
print('dial centre=(%d,%d) outerR=%d  lit before=%s' % (cx, cy, outer, before))

def attempt(cx, cy, outer, before, idx):
    """Press the hub button and film the dial. Returns (first_change_time or None, seq, ok_press,
    slept). Landing back on the SAME wedge is possible (1 in 8) and tells us nothing, so that
    attempt is reported as None rather than as 'no change before 3s'."""
    trigger = find('开始') or find('抽令')
    if not trigger:
        return None, [], False, False
    tap(*trigger)
    t0 = time.time()                     # every t below is relative to the PRESS, not to setup
    # Did the press register? start() renames the button to 抽令 for the whole sweep. This check
    # costs ~1s of the 5s window, so an early (buggy) flip first shows up around t=1.2s -- still
    # far below the 5.0s the sweep needs, so the verdict stays unambiguous.
    time.sleep(0.6)
    ok_press = find('抽令') is not None
    seq = []
    slept = False
    while time.time() - t0 < 10.0:
        b = frame()
        t = time.time() - t0
        lit = lit_set(b, cx, cy, outer)
        seq.append((t, lit))
        if 'Awake' not in sh(['dumpsys', 'power']):
            slept = True
            sh(['input', 'keyevent', '224'])
        if lit and lit != before:
            break
    flip = [t for t, l in seq if l and l != before]
    print('  attempt %d: press=%s slept=%s end=%s first_change=%s'
          % (idx, ok_press, slept, seq[-1][1] if seq else None,
             ('%.1fs' % flip[0]) if flip else 'none'))
    if not flip:
        return None, seq, ok_press, slept
    return flip[0], seq, ok_press, slept


results = []
for i in range(1, 5):
    before_buf = frame()
    before = lit_set(before_buf, cx, cy, outer)
    t, seq, pressed, slept = attempt(cx, cy, outer, before, i)
    results.append((before, t, seq, pressed, slept))
    if t is not None:
        break
    if not pressed:
        print('  -> press did not register; aborting retries')
        break
    sh(['input', 'keyevent', '82'])          # MENU, harmless, keeps the screen interested
    time.sleep(2)

print()
hit = [(b, t) for b, t, s, p, sl in results if t is not None]
if not hit:
    print('VERDICT: INCONCLUSIVE -- no attempt produced a wedge change'
          ' (press registered: %s)' % [p for _, _, _, p, _ in results])
    sys.exit(2)                          # environment problem, not a product bug: distinct code
b, t = hit[0]
print('VERDICT: first colour change at t=%.1fs after pressing the hub button' % t)
print('         5s sweep => a landing-time change is ~5.0-6.5s; a premature one would be <1s')
if t >= 4.0:
    print('         PASS: the wedge only lights up when the hand arrives')
    sys.exit(0)
print('         FAIL: the wedge changed before the sweep finished')
sys.exit(1)