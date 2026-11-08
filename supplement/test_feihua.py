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

# --- 2. hit test: touching the centre of wedge i selects i, whatever the band angle --------
def hit(deg, angle):
    rel = ((deg - angle) % 360.0 + 360.0) % 360.0
    return int(math.floor(rel / step + 0.5)) % slots


for angle in (0.0, -45.0, -90.0, -135.0, -225.0, -315.0, 30.0, 359.9):
    for i in range(slots):
        centre = angle + i * step
        ck(hit(centre, angle) == i, 'wedge %d not picked at band %.1f' % (i, angle))
        for off in (-15, 15):
            want = int(round((centre + off - angle) / step)) % slots
            ck(hit(centre + off, angle) == want, 'edge wedge %d off %+d at %.1f' % (i, off, angle))

# --- 3. spinTo lands the requested wedge under the top pointer (touch deg 0) ---------------
for s in range(slots):
    ck(hit(0.0, -s * step) == s, 'spinTo(%d) would not stop under the pointer' % s)

# --- 4. hub: three round buttons, three distinct colours, shared hub radius ---------------
colours = set(c.lower() for c in re.findall(r'roundBtn\("[^"]+",\s*(0x[0-9A-Fa-f]{8})', act))
ck(len(colours) == 3, 'expected 3 distinct round-button colours, got %s' % sorted(colours))
for label in ('开始', '停止', '认输'):
    ck('roundBtn("%s"' % label in act, 'hub is missing the %s button' % label)
inner_frac = re.search(r'innerR\(\)\s*\{\s*return outerR\(\)\s*\*\s*([0-9.]+)f', dial)
ck(inner_frac is not None, 'innerR() shape changed')
frac = float(inner_frac.group(1))
# draw and touch must use the SAME accessor, else the dead zone drifts from the visible hub
ck(dial.count('innerR()') >= 3, 'draw and touch should share innerR()')
# the three 52dp circles have to fit inside the hole: worst corner of the top row
hub = frac * (min(262, 320) / 2.0 - 22)                 # dp, hub block 262dp tall, narrow phone
btn, gap = 52.0, 4.0
row_cy = (110.0 / 2.0 - btn / 2.0)                       # rowA centre above hub centre
far = math.hypot(btn / 2.0 + gap, row_cy) + btn / 2.0
ck(far <= hub, 'round buttons overflow the hub: %.1fdp > %.1fdp' % (far, hub))
# labels must not be rotated any more (rotation flipped the lower wedges upside down)
ck('c.rotate(band' not in dial, 'DialView still rotates wedge labels; lower half renders upside down')

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
