"""What is actually in the local annotation sources, and how much is unused?

anno.ndjson has 11476 rows; works.npy / works.zip may hold more. Count rows, payload
presence and per-field fill, then report how many still-uncovered 补录 rows each source
could serve by title.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
_ANNO = __import__('os').environ.get('POETRY_ANNO') or '/root/anno'
_BAK = __import__('os').environ.get('POETRY_BAK') or '/root/backup'
import collections
import json
import os
import sqlite3

import numpy as np

anno = [json.loads(l) for l in open(f'{_ANNO}/anno.ndjson', encoding='utf8') if l.strip()]
print('anno.ndjson rows=%d  with_trans=%d' % (
    len(anno), sum(1 for r in anno if (r.get('trans') or '').strip())))

for p in (f'{_ANNO}/works.npy', f'{_ANNO}/works.zip'):
    print(p, round(os.path.getsize(p) / 1e6, 1), 'MB')

w = np.load(f'{_ANNO}/works.npy', allow_pickle=True)
names = w.dtype.names or ()
print('works.npy rows:', len(w), 'fields:', names)
for f in ('Translation', 'Annotation', 'Intro'):
    if f in names:
        print('   %-12s non-empty: %d' % (f, sum(1 for x in w[f] if str(x).strip())))
if 'Kind' in names:
    print('   Kind:', collections.Counter(str(k) for k in w['Kind']).most_common(6))

c = sqlite3.connect(f'{_ROOT}/out/poetry_lite.db').cursor()
missing = c.execute("SELECT p.title_s, a.name_s FROM poem p JOIN author a ON a.id=p.author_id"
                    " WHERE p.source='补录' AND (trans IS NULL OR trans='')").fetchall()
titles = collections.Counter()
if 'Title' in names:
    for i in range(len(w)):
        tr = str(w['Translation'][i]) if 'Translation' in names else ''
        nt = str(w['Annotation'][i]) if 'Annotation' in names else ''
        if tr.strip() or nt.strip():
            titles[str(w['Title'][i]).strip()] += 1
hit = sum(1 for t, _ in missing if t in titles)
print('works.npy title-covers %d of the %d still-uncovered 补录 rows' % (hit, len(missing)))
for t, a in missing[:6]:
    print('   %-18s %-6s in_works=%s' % (t, a, t in titles))