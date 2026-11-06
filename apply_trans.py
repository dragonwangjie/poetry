#!/usr/bin/env python3
"""Apply 唐诗三百首/宋词三百首 translations (auto match preferred, handwritten fallback)."""
import glob
import json
import re
import sqlite3

auto = {}
for line in open('/root/poetry/out/trans_auto.ndjson', encoding='utf8'):
    d = json.loads(line)
    if d.get('trans'):
        auto[d['id']] = d
hand = {}
for f in sorted(glob.glob('/root/poetry/out/tr/b*.jsonl')):
    for line in open(f, encoding='utf8'):
        if line.strip():
            d = json.loads(line)
            hand[d['id']] = d['trans']
print('auto with trans', len(auto), 'handwritten', len(hand))

db = sqlite3.connect('/root/poetry/out/poetry_lite.db')
c = db.cursor()
todo = c.execute("SELECT p.id FROM poem p WHERE (p.tags LIKE '%唐诗三百首%'"
                 " OR p.tags LIKE '%宋词三百首%') AND p.trans IS NULL").fetchall()
todo = [t[0] for t in todo]
print('poems still without trans in the two anthologies:', len(todo))

setq = []
for pid in todo:
    if pid in auto:
        d = auto[pid]
        cur = c.execute('SELECT note,intro FROM poem WHERE id=?', (pid,)).fetchone()
        note = cur[0] or (d.get('note') or '') or None
        intro = cur[1] or (d.get('intro') or '') or None
        setq.append((d['trans'], note, intro, pid))
    elif pid in hand:
        setq.append((hand[pid], None, None, pid))
c.executemany('UPDATE poem SET trans=?, note=COALESCE(?,note), intro=COALESCE(?,intro) WHERE id=?',
              setq)
db.commit()
print('updated rows', len(setq))
for tag in ('唐诗三百首', '宋词三百首'):
    tot, have = c.execute("SELECT COUNT(*), SUM(trans IS NOT NULL) FROM poem"
                          " WHERE tags LIKE ?", ('%' + tag + '%',)).fetchone()
    print('%s: %d/%d (%.0f%%)' % (tag, have, tot, 100.0 * have / tot))
lat = [r[0] for r in c.execute(
    "SELECT id FROM poem WHERE (tags LIKE '%唐诗三百首%' OR tags LIKE '%宋词三百首%')"
    " AND trans IS NOT NULL")]
bad = 0
for pid in lat:
    t = c.execute('SELECT trans FROM poem WHERE id=?', (pid,)).fetchone()[0]
    if re.search(r'[a-zA-Z]{2,}', t or ''):
        bad += 1
print('latin leftovers', bad)