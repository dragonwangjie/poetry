"""For each still-uncovered 补录 row that the corpus has a same-title record for,
show why the gate accepted or rejected it: length ratio, opening-8 containment,
bigram overlap, plus the first lines of both texts.

This distinguishes a genuinely different poem (correct rejection) from an over-strict
threshold that throws away a real match.
"""
import json
import sqlite3
import sys

sys.path.insert(0, '/root/poetry/supplement')
from apply_anno import bigrams, clean, norm, similar  # noqa: E402


def detail(a, b):
    ratio = 1.0 * min(len(a), len(b)) / max(len(a), len(b)) if a and b else 0.0
    x, y = bigrams(a), bigrams(b)
    ov = 2.0 * len(x & y) / (len(x) + len(y)) if x and y else 0.0
    return ratio, (bool(a[:8]) and a[:8] in b), ov


corpus = {}
for line in open('/root/anno/anno.ndjson', encoding='utf8'):
    if not line.strip():
        continue
    r = json.loads(line)
    tr, nt, ii = (clean(r.get('trans') or ''), clean(r.get('note') or ''),
                  clean(r.get('intro') or ''))
    if not (tr or nt or ii):
        continue
    corpus.setdefault(norm(r.get('title') or ''), []).append(
        (str(r.get('author') or '').strip(), norm(r.get('content') or ''), tr))

want = sqlite3.connect('/root/poetry/out/poetry_lite.db').execute(
    "SELECT p.title_s, a.name_s, p.body FROM poem p JOIN author a ON a.id=p.author_id"
    " WHERE p.source='补录' AND (trans IS NULL OR trans='')").fetchall()
print('uncovered 补录 rows: %d' % len(want))
rescue = []
for t, a, body in want:
    cands = corpus.get(norm(t))
    if not cands:
        continue
    nb = norm(body)
    for ca, cb, tr in cands:
        ratio, head, ov = detail(nb, cb)
        verdict = 'ACCEPT' if similar(nb, cb) else 'reject'
        if verdict == 'ACCEPT':
            rescue.append((t, a, ratio, ov, tr))
        print('%-22s %-5s vs 语料作者=%-6s len_ratio=%.2f head8=%-5s overlap=%.2f %s'
              % (t[:22], a, ca[:6], ratio, head, ov, verdict))
        if verdict == 'reject':
            print('      db  : %s' % (body or '').split('\n')[0][:34])
            print('      anno: %s' % cb[:34])
        break
print('\ngate currently accepts %d of these title hits' % len(rescue))
for t, a, r, o, tr in rescue:
    print('   %-20s %-5s ratio=%.2f overlap=%.2f | %s' % (t[:20], a, r, o, tr[:30]))