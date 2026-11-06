#!/usr/bin/env python3
"""Attach 译文/注释/简介 (vernacular translation, annotation, intro) to poems.

Incremental: adds three TEXT columns to `poem` in the existing poetry_lite.db
instead of rerunning the full ETL. Matching walks a cascade because the two
corpora differ in title style and wording:

  1. normalized full text            (strongest)
  2. (title, author)
  3. (title with 其一/parenthetical stripped, author)
  4. (first-10-chars of body, author)
  5. title alone, only when the title is unique in both corpora
"""
import collections
import glob
import json
import os
import re
import sqlite3
import sys

DB = '/root/poetry/out/poetry_lite.db'
SRC = '/root/anno/anno.ndjson'
DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]\r\n\t ')
TAG = re.compile(r'<[^>]+>')
SEQ = re.compile(r'(?:其[一二三四五六七八九十百\d]+|之一|之二|其一)$')
PAREN = re.compile(r'[（(][^（()）]*[)）]')


def norm(s):
    s = TAG.sub('', s or '')
    return ''.join(ch for ch in s if ch not in DROP)


def tkey(t):
    t = PAREN.sub('', t)
    t = SEQ.sub('', t)
    return t.strip()


def clean(s):
    s = TAG.sub('', s or '')
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'[ \t]+', ' ', s)
    return re.sub(r'\n{2,}', '\n', s).strip()


def load(paths):
    recs = []
    for p in paths:
        if p.endswith('.ndjson'):
            it = (json.loads(l) for l in open(p, encoding='utf8') if l.strip())
        else:
            it = json.load(open(p, encoding='utf8'))
        for r in it:
            if not isinstance(r, dict):
                continue
            tr = clean(r.get('Translation') or r.get('translation') or r.get('trans') or '')
            nt = clean(r.get('Annotation') or r.get('annotation') or r.get('note') or '')
            ii = clean(r.get('Intro') or r.get('intro') or '')
            if not (tr or nt or ii):
                continue
            recs.append(dict(title=norm(r.get('Title') or r.get('title') or ''),
                             author=norm(r.get('Author') or r.get('author') or ''),
                             body=norm(r.get('Content') or r.get('content') or ''),
                             trans=tr, note=nt, intro=ii))
    return recs


def main(paths, apply):
    recs = load(paths)
    print('source records with payload:', len(recs))
    db = sqlite3.connect(DB)
    c = db.cursor()
    cols = [r[1] for r in c.execute('PRAGMA table_info(poem)')]

    by_body, by_ta, by_t2a, by_fa, by_title = {}, {}, {}, {}, {}
    for pid, body, title, author in c.execute(
            'SELECT p.id,p.body,p.title_s,a.name_s FROM poem p JOIN author a ON a.id=p.author_id'):
        nb, nt, na = norm(body), norm(title), norm(author)
        by_body.setdefault(nb, []).append(pid)
        by_ta.setdefault((nt, na), []).append(pid)
        by_t2a.setdefault((tkey(nt), na), []).append(pid)
        by_fa.setdefault((nb[:10], na), []).append(pid)
        by_title.setdefault(nt, []).append(pid)

    stat = dict(body=0, ta=0, t2a=0, fa=0, title=0, miss=0)
    src_title_count = collections.Counter(r['title'] for r in recs)
    upd = {}
    for r in recs:
        ids, how = None, None
        if r['body'] in by_body:
            ids, how = by_body[r['body']], 'body'
        elif (r['title'], r['author']) in by_ta:
            ids, how = by_ta[(r['title'], r['author'])], 'ta'
        elif (tkey(r['title']), r['author']) in by_t2a:
            ids, how = by_t2a[(tkey(r['title']), r['author'])], 't2a'
        elif (r['body'][:10], r['author']) in by_fa:
            ids, how = by_fa[(r['body'][:10], r['author'])], 'fa'
        elif len(by_title.get(r['title'], [])) == 1 and src_title_count[r['title']] == 1:
            ids, how = by_title[r['title']], 'title'
        stat[how or 'miss'] += 1
        if not ids:
            continue
        pid = ids[0]
        prev = upd.get(pid, ('', '', ''))
        upd[pid] = (prev[0] or r['trans'], prev[1] or r['note'], prev[2] or r['intro'])
    print('matched', stat)
    print('distinct poems to update:', len(upd))
    print('with trans=%d note=%d intro=%d'
          % (sum(1 for v in upd.values() if v[0]), sum(1 for v in upd.values() if v[1]),
             sum(1 for v in upd.values() if v[2])))
    if not apply:
        print('DRY RUN (pass --apply to write)')
        return
    for col in ('trans', 'note', 'intro'):
        if col not in cols:
            c.execute('ALTER TABLE poem ADD COLUMN %s TEXT' % col)
    c.executemany('UPDATE poem SET trans=?, note=?, intro=? WHERE id=?',
                  [(v[0] or None, v[1] or None, v[2] or None, k) for k, v in upd.items()])
    db.commit()
    print('poems with trans now:',
          c.execute('SELECT COUNT(*) FROM poem WHERE trans IS NOT NULL').fetchone()[0])
    print('poems with note now:',
          c.execute('SELECT COUNT(*) FROM poem WHERE note IS NOT NULL').fetchone()[0])
    print('poems with intro now:',
          c.execute('SELECT COUNT(*) FROM poem WHERE intro IS NOT NULL').fetchone()[0])
    print('any of the three:',
          c.execute('SELECT COUNT(*) FROM poem WHERE trans IS NOT NULL OR note IS NOT NULL'
                    ' OR intro IS NOT NULL').fetchone()[0])
    c.execute('VACUUM')
    db.commit()
    print('db size', round(os.path.getsize(DB) / 1e6, 1), 'MB')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    paths = []
    for a in args or [SRC]:
        paths += sorted(glob.glob(a))
    main(paths, '--apply' in sys.argv)