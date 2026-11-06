"""Audit which annotation rows landed on which 补录 poems, tier by tier.

Body-tier matches are safe by construction (identical normalized text), so the printout
concentrates on the weaker tiers where a title collision could paste one poem's 译文 onto
another. Prints DB side next to corpus side for eyeballing.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import collections
import sqlite3
import sys

sys.path.insert(0, f'{_ROOT}/supplement')
from apply_anno import norm, tkey, load, SRC  # noqa: E402

db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else '/tmp/t.db')
c = db.cursor()
rows = c.execute("SELECT p.id,p.body,p.title_s,a.name_s FROM poem p"
                 " JOIN author a ON a.id=p.author_id WHERE p.source='补录'").fetchall()
by_body, by_ta, by_t2a, by_fa, by_title = {}, {}, {}, {}, {}
info = {}
for pid, body, title, author in rows:
    nb, nt, na = norm(body), norm(title), norm(author)
    info[pid] = (title, author, body)
    by_body.setdefault(nb, []).append(pid)
    by_ta.setdefault((nt, na), []).append(pid)
    by_t2a.setdefault((tkey(nt), na), []).append(pid)
    by_fa.setdefault((nb[:10], na), []).append(pid)
    by_title.setdefault(nt, []).append(pid)
cnt = collections.Counter()
shown = collections.Counter()
seen = set()
for r in load(SRC):
    if r['body'] in by_body:
        how, ids = 'body', by_body[r['body']]
    elif (r['title'], r['author']) in by_ta:
        how, ids = 'title+author', by_ta[(r['title'], r['author'])]
    elif (tkey(r['title']), r['author']) in by_t2a:
        how, ids = 'title-stripped', by_t2a[(tkey(r['title']), r['author'])]
    elif (r['body'][:10], r['author']) in by_fa:
        how, ids = 'first10+author', by_fa[(r['body'][:10], r['author'])]
    elif len(by_title.get(r['title'], [])) == 1:
        how, ids = 'title-only', by_title[r['title']]
    else:
        continue
    cnt[how] += 1
    if ids[0] in seen or how == 'body' or shown[how] >= 4:
        seen.add(ids[0])
        continue
    seen.add(ids[0])
    shown[how] += 1
    t, a, body = info[ids[0]]
    print('[%s]\n   db     : 《%s》%s | %s' % (how, t, a, (body or '').split('\n')[0][:28]))
    print('   corpus : 《%s》%s | %s' % (r['title'], r['author'], r['body'][:28]))
    print('   trans  : %s' % (r['trans'] or '(none)')[:64])
print('tiers:', dict(cnt))
empty = c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
                  " AND (trans IS NULL OR trans='') AND (note IS NULL OR note='')").fetchone()[0]
print('补录 rows with neither trans nor note:', empty)
db.close()