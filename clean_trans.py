#!/usr/bin/env python3
"""Keep only source-backed payload that the poem text actually confirms.

The first attach pass also matched on (title, author), which is unreliable for 词牌
and for common titles. Walk every poem that carries trans/note/intro, re-match it to
the annotation source by text alone, then either overwrite with the confirmed payload
or clear the fields. Handwritten translations (keyed by our own poem id) are exempt.
"""
import collections
import difflib
import glob
import json
import sqlite3

DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]\r\n\t ')
ALIAS = {'后主煜': '李煜', '南唐嗣主李璟': '李璟', '李后主': '李煜'}


def norm(s):
    return ''.join(ch for ch in (s or '') if ch not in DROP)


def akey(a):
    return ALIAS.get(norm(a), norm(a))


payload = [json.loads(l) for l in open('/root/anno/anno.ndjson', encoding='utf8')
           if ('"trans": "' in l or '"note": "' in l or '"intro": "' in l)]
for r in payload:
    r['_b'] = norm(r['content'])
exact = {}
head = collections.defaultdict(list)
byauthor = collections.defaultdict(list)
for r in payload:
    exact.setdefault(r['_b'], r)
    head[r['_b'][:8]].append(r)
    byauthor[akey(r['author'])].append(r)
print('source records with payload', len(payload))

hand = {}
for f in glob.glob('/root/poetry/out/tr/*.jsonl'):
    for l in open(f, encoding='utf8'):
        if l.strip():
            d = json.loads(l)
            hand[d['id']] = d['trans']

db = sqlite3.connect('/root/poetry/out/poetry_lite.db')
c = db.cursor()
rows = c.execute('SELECT p.id,a.name_s,p.title_s,p.body,p.trans,p.note,p.intro FROM poem p'
                 ' JOIN author a ON a.id=p.author_id WHERE p.trans IS NOT NULL'
                 ' OR p.note IS NOT NULL OR p.intro IS NOT NULL').fetchall()
print('poems carrying payload', len(rows))

stat = collections.Counter()
for pid, author, title, body, tr, nt, ii in rows:
    nb, na = norm(body), akey(author)
    hit = exact.get(nb)
    how = 'exact'
    if hit is None:
        cand = [r for r in head.get(nb[:8], []) if akey(r['author']) == na] or head.get(nb[:8], [])
        if len(cand) == 1:
            hit, how = cand[0], 'head'
        else:
            cont = [r for r in byauthor.get(na, [])
                    if nb and (nb in r['_b'] or (len(nb) > 24 and r['_b'] in nb))]
            if len(cont) == 1:
                hit, how = cont[0], 'contain'
            elif cont:
                best = max(cont, key=lambda r: difflib.SequenceMatcher(
                    None, nb[:300], r['_b'][:300]).ratio())
                if difflib.SequenceMatcher(None, nb[:300], best['_b'][:300]).ratio() >= 0.9:
                    hit, how = best, 'fuzzy'
    if hit is not None:
        want = (hit['trans'] or None, hit['note'] or None, hit['intro'] or None)
        if want != (tr, nt, ii):
            c.execute('UPDATE poem SET trans=?, note=?, intro=? WHERE id=?',
                      (want[0], want[1], want[2], pid))
            stat['rewritten:' + how] += 1
        else:
            stat['confirmed'] += 1
    elif pid in hand:
        if tr != hand[pid]:
            c.execute('UPDATE poem SET trans=? WHERE id=?', (hand[pid], pid))
        stat['handwritten'] += 1
    else:
        c.execute('UPDATE poem SET trans=NULL, note=NULL, intro=NULL WHERE id=?', (pid,))
        stat['cleared'] += 1
db.commit()
print(dict(stat))
print('now trans=%d note=%d intro=%d'
      % (c.execute('SELECT COUNT(*) FROM poem WHERE trans IS NOT NULL').fetchone()[0],
         c.execute('SELECT COUNT(*) FROM poem WHERE note IS NOT NULL').fetchone()[0],
         c.execute('SELECT COUNT(*) FROM poem WHERE intro IS NOT NULL').fetchone()[0]))
for tag in ('唐诗三百首', '宋词三百首'):
    print(tag, c.execute('SELECT COUNT(*), SUM(trans IS NOT NULL) FROM poem WHERE tags LIKE ?',
                         ('%' + tag + '%',)).fetchone())
c.execute('VACUUM')
db.commit()
import os
print('db MB', round(os.path.getsize('/root/poetry/out/poetry_lite.db') / 1e6, 1))