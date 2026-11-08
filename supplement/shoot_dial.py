#!/usr/bin/env python3
"""Pixel-level proof of WHEN the wedge colour changes.

The dial is self-drawn so uiautomator cannot see it; screencap can. Wedges paint 0xFFF1E7D3 when
idle and 0xFFB4553F (0xFF8B3A2B for 任意) when selected -- far enough apart to classify by channel
values alone, no image decoding needed. screencap on this device emits raw RGBA8888 with a 16-byte
header, which dd can slice on-device so only the sampled bytes cross the wire.

Geometry mirrors DialView: outer = side/2 - 22dp, inner = 0.70*outer, wedge i spans
[i*45-90, i*45-45] degrees clockwise from 3 o'clock, so its middle sits at i*45-67.5.
"""
import re
import subprocess
import sys
import time

W, H = 1280, 2772
DENSITY = 520 / 160.0


def sh(args):
    return subprocess.run(['adb', 'shell'] + args, capture_output=True, text=True, timeout=60).stdout


def tap(x, y):
    sh(['input', 'tap', str(int(x)), str(int(y))])


def nodes(label):
    sh(['rm', '-f', '/sdcard/q.xml'])
    sh(['uiautomator', 'dump', '/sdcard/q.xml'])
    xml = sh(['cat', '/sdcard/q.xml'])
    out = []
    for m in re.finditer('<node[^>]*>', xml):
        t = m.group(0)
        if ('text="%s"' % label) in t or ('class="com.poetry.app.DialView"') in t:
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', t)
            if b:
                out.append(((int(b.group(1)) + int(b.group(3))) / 2.0,
                            (int(b.group(2)) + int(b.group(4))) / 2.0, b.group(0)))
    return out


def wedge_colors(cx, cy, outer):
    """All 16 samples in ONE adb round trip: on-device dd is milliseconds, the wire is not."""
    import math
    offs = []
    for i in range(8):
        rad = math.radians(i * 45 - 67.5)
        # 0.74/0.92 of outerR: inside the 0.70-1.00 ring band and off the label glyphs, which are
        # painted 0xFF6B5B45 -- dark enough that a sample landing on one would read as "lit".
        for f in (0.74, 0.92):
            x = int(round(cx + outer * f * math.cos(rad)))
            y = int(round(cy + outer * f * math.sin(rad)))
            offs.append((i, y * W + x + 4))     # bs=4 units: the 16-byte header is 4 pixels
    cmd = ';'.join("dd if=/sdcard/s.raw bs=4 skip=%d count=1 2>/dev/null | od -An -tu1" % off
                   for _, off in offs)
    h = sh([cmd])       # adb joins its args, so the device shell still sees the pipes/semicolons
    rows = [[int(z) for z in line.split()] for line in h.splitlines() if line.strip()]
    rows = [r for r in rows if len(r) >= 4]
    return [(offs[k][0], r[0], r[1], r[2]) for k, r in enumerate(rows) if k < len(offs)]


def lit_wedges(outer, cx, cy):
    lit = set()
    for i, r, g, b in wedge_colors(cx, cy, outer):
        if 0 <= r < 215 and 0 <= b < 175:      # cream is (241,231,211); both lit colours are darker
            lit.add(i)
    return sorted(lit)


# ------------------------------------------------------------------ get to the dial
if 'Awake' not in sh(['dumpsys', 'power']):
    sh(['input', 'keyevent', '224'])
    time.sleep(2)
sh(['input', 'swipe', '540', '2100', '540', '700', '300'])
sh(['wm', 'dismiss-keyguard'])
time.sleep(1)
sh(['am', 'force-stop', 'com.poetry.app'])
sh(['am', 'start', '-n', 'com.poetry.app/.MainActivity'])
time.sleep(5)

hits = nodes('飞花令')
if not hits:
    sys.exit('no 飞花令 button on screen')
tap(hits[0][0], hits[0][1])
time.sleep(3)

# DialView matched by CLASS only: text="" would also match every text-less container, whose
# bounds are the whole page and would put the sample points far outside the dial.
sh(['rm', '-f', '/sdcard/q.xml'])
sh(['uiautomator', 'dump', '/sdcard/q.xml'])
xml = sh(['cat', '/sdcard/q.xml'])
dial, start = [], [n for n in nodes('开始') if 'DialView' not in n[2]]
for m in re.finditer('<node[^>]*>', xml):
    t = m.group(0)
    if 'DialView' in t:
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', t)
        if b:
            ax, ay, bx, by = [int(v) for v in b.groups()]
            if bx > ax and by > ay:
                dial.append(((ax + bx) / 2.0, (ay + by) / 2.0, min(bx - ax, by - ay)))
if not dial or not start:
    sys.exit('dial=%s start=%s nodes=%s' % (dial, bool(start),
                                            re.findall(r'class="([^"]*)"', xml)[-6:]))
cx, cy, side = dial[0]
outer = side / 2.0 - 22 * DENSITY
print('dial centre=(%.0f,%.0f) side=%.0f outer=%.0f' % (cx, cy, side, outer))

sh(['screencap', '/sdcard/s.raw'])            # must exist before the first dd sample
print('raw rgb:', [(i, r, g, b) for i, r, g, b in wedge_colors(cx, cy, outer)][::2])
before = lit_wedges(outer, cx, cy)
print('t=-0.0s lit=%s' % before)

tap(start[0][0], start[0][1])
t0 = time.time()
timeline = []
while time.time() - t0 < 9.0:
    sh(['screencap', '/sdcard/s.raw'])
    t = time.time() - t0
    lit = lit_wedges(outer, cx, cy)
    timeline.append((t, lit))
    print('t=%.1fs lit=%s' % (t, lit))
    time.sleep(0.45)

sh(['rm', '-f', '/sdcard/s.raw'])
flips = [(t, lit) for t, lit in timeline if lit != before]
if not flips:
    print('VERDICT: highlight never moved -- the spin never landed')
else:
    print('VERDICT: first change at t=%.1fs -> %s (was %s)'
          % (flips[0][0], flips[0][1], before))
    print('        a correct build flips only after the 5s sweep, not at t<1s')