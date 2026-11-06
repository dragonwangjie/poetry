#!/usr/bin/env python3
"""Make the two anthologies' 译文 authoritative.

title+author matching is unsafe for 词牌 (one tune, many poems), so re-derive every
anthology translation from the source by text similarity only. Anything the source
does not contain falls back to the handwritten files; poems with neither become gaps.
"""
import collections
import difflib
import glob
import json
import sqlite3
import sys

DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]\r\n\t ')
ALIAS = {'后主煜': '李煜', '南唐嗣主李璟': '李璟', '李后主': '李煜'}


def norm(s):
    return ''.join(ch for ch in (s or '') if ch not in DROP)


def akey(a):
    return ALIAS.get(norm(a), norm(a))


src = [json.loads(l) for l in open('/root/anno/anno.ndjson', encoding='utf8')]
for r in src:
    r['_b'] = norm(r['content'])
by_body = collections.defaultdict(list)
by_author = collections.defaultdict(list)
by_head = collections.defaultdict(list)
for r in src:
    if r['_b']:
        by_body[r['_b']].append(r)
        by_author[akey(r['author'])].append(r)
        by_head[r['_b'][:6]].append(r)

hand = {}
for f in sorted(glob.glob('/root/poetry/out/tr/*.jsonl')):
    for l in open(f, encoding='utf8'):
        if l.strip():
            d = json.loads(l)
            hand[d['id']] = d['trans']


def find(nb, na):
    """Return (record, how) matched purely on text."""
    if nb in by_body:
        return by_body[nb][0], 'exact'
    cand = by_author.get(na) or by_head.get(nb[:6]) or []
    contain = [r for r in cand if nb and (nb in r['_b'] or (len(nb) > 20 and r['_b'] in nb))]
    if len(contain) == 1:
        return contain[0], 'contain'
    if len(contain) > 1:
        cand = contain
    best, score = None, 0.0
    for r in cand:
        s = difflib.SequenceMatcher(None, nb[:300], r['_b'][:300]).ratio()
        if s > score:
            best, score = r, s
    return (best, 'fuzzy%.2f' % score) if score >= 0.85 else (None, 'none')


db = sqlite3.connect('/root/poetry/out/poetry_lite.db')
c = db.cursor()
rows = c.execute("SELECT p.id,p.title_s,a.name_s,p.body,p.trans FROM poem p"
                 " JOIN author a ON a.id=p.author_id WHERE p.tags LIKE '%唐诗三百首%'"
                 " OR p.tags LIKE '%宋词三百首%'").fetchall()
print('anthology poems', len(rows), 'handwritten', len(hand))

stat = collections.Counter()
gaps = []
for pid, title, author, body, stored in rows:
    nb, na = norm(body), akey(author)
    hit, how = find(nb, na)
    if hit:
        new = hit['trans'] or hand.get(pid) or hit['note'] or hit['intro'] or ''
        stat['src:' + how[:5]] += 1
    elif pid in hand:
        new, how = hand[pid], 'hand'
        stat['hand'] += 1
    else:
        gaps.append((pid, title, author))
        continue
    if not new.strip():
        gaps.append((pid, title, author))
        continue
    # The source is the only trustworthy origin for note/intro: reset them from the
    # matched record instead of COALESCE, so earlier title+author mismatches cannot
    # leave a wrong annotation behind.
    old0 = c.execute('SELECT note,intro FROM poem WHERE id=?', (pid,)).fetchone()
    nnote = (hit['note'] or None) if hit else old0[0]
    nintro = (hit['intro'] or None) if hit else old0[1]
    old = old0
    if new != (stored or '') or nnote != old[0] or nintro != old[1]:
        stat['changed'] += 1
        c.execute('UPDATE poem SET trans=?, note=?, intro=? WHERE id=?',
                  (new, nnote, nintro, pid))
    else:
        stat['kept'] += 1
db.commit()
print('match sources', dict(stat))
print('gaps', len(gaps))
for g in gaps:
    print('   id=%d %s / %s' % g)
with open('/root/poetry/out/gaps.ndjson', 'w', encoding='utf8') as w:
    for pid, title, author in gaps:
        b = c.execute('SELECT body FROM poem WHERE id=?', (pid,)).fetchone()[0]
        w.write(json.dumps({'id': pid, 't': title, 'a': author,
                            'b': b.replace('\n', '/')}, ensure_ascii=False) + '\n')
for tag in ('唐诗三百首', '宋词三百首'):
    tot, have = c.execute("SELECT COUNT(*), SUM(trans IS NOT NULL) FROM poem WHERE tags LIKE ?",
                          ('%' + tag + '%',)).fetchone()
    print('%s %d/%d' % (tag, have, tot))