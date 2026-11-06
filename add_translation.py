#!/usr/bin/env python3
"""Attach vernacular translation (译文) / annotation (注释) / intro (简介) to poems.

Incremental: adds three columns to `poem` in the existing poetry_lite.db instead of
rerunning the full ETL (which rebuilds 845k lines + reverse indexes).
Match order: normalized full text > (title, author) > title + first line.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import glob
import json
import os
import re
import sqlite3
import sys

DB = f'{_ROOT}/out/poetry_lite.db'
DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]\r\n\t ')
TAG = re.compile(r'<[^>]+>')


def norm(s):
    s = TAG.sub('', s or '')
    return ''.join(ch for ch in s if ch not in DROP)


def clean(s):
    s = TAG.sub('', s or '')
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{2,}', '\n', s)
    return s.strip()


def iter_raw(p):
    """Yield record dicts from either a JSON array file or an NDJSON file."""
    if p.endswith('.ndjson'):
        with open(p, encoding='utf8') as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return
    d = json.load(open(p, encoding='utf8'))
    if isinstance(d, dict):
        d = d.get('works') or d.get('data') or []
    for r in d:
        yield r


def load_records(paths):
    recs = []
    for p in paths:
        try:
            it = list(iter_raw(p))
        except Exception as e:
            print('skip', p, repr(e)[:60])
            continue
        for r in it:
            if not isinstance(r, dict):
                continue
            content = r.get('Content') or r.get('content') or ''
            trans = r.get('Translation') or r.get('translation') or r.get('trans') or ''
            note = r.get('Annotation') or r.get('annotation') or r.get('note') or ''
            intro = r.get('Intro') or r.get('intro') or ''
            if not (clean(trans) or clean(note) or clean(intro)):
                continue
            recs.append(dict(title=r.get('Title') or r.get('title') or '',
                             author=r.get('Author') or r.get('author') or '',
                             content=content, trans=clean(trans),
                             note=clean(note), intro=clean(intro)))
    return recs


def main(paths, dry=True):
    recs = load_records(paths)
    print('source records with annotation payload:', len(recs))
    db = sqlite3.connect(DB)
    c = db.cursor()
    cols = [r[1] for r in c.execute('PRAGMA table_info(poem)')]
    print('poem columns', cols)
    by_body = {}
    by_ta = {}
    by_tl = {}
    for pid, body, title, author in c.execute(
            'SELECT p.id,p.body,p.title_s,a.name_s FROM poem p JOIN author a ON a.id=p.author_id'):
        by_body.setdefault(norm(body), []).append(pid)
        by_ta.setdefault((norm(title), norm(author)), []).append(pid)
        first = norm(body).split('\n')[0][:12]
        by_tl.setdefault((norm(title), first), []).append(pid)
    print('index sizes', len(by_body), len(by_ta), len(by_tl))

    m_body = m_ta = m_tl = miss = 0
    upd = {}
    for r in recs:
        nb = norm(r['content'])
        nt = norm(r['title'])
        na = norm(r['author'])
        ids = by_body.get(nb)
        if ids:
            m_body += 1
        else:
            ids = by_ta.get((nt, na))
            if ids:
                m_ta += 1
            else:
                ids = by_tl.get((nt, nb[:12]))
                if ids:
                    m_tl += 1
        if not ids:
            miss += 1
            continue
        pid = ids[0]
        prev = upd.get(pid, ('', '', ''))
        upd[pid] = (prev[0] or r['trans'], prev[1] or r['note'], prev[2] or r['intro'])
    print('matched body=%d title+author=%d title+line=%d miss=%d (coverage %.1f%%)'
          % (m_body, m_ta, m_tl, miss, 100.0 * (m_body + m_ta + m_tl) / max(len(recs), 1)))
    print('distinct poems to update:', len(upd))
    have_t = sum(1 for v in upd.values() if v[0])
    have_n = sum(1 for v in upd.values() if v[1])
    have_i = sum(1 for v in upd.values() if v[2])
    print('poems gaining trans=%d note=%d intro=%d' % (have_t, have_n, have_i))
    if dry:
        print('DRY RUN (pass --apply to write)')
        return
    for col in ('trans', 'note', 'intro'):
        if col not in cols:
            c.execute('ALTER TABLE poem ADD COLUMN %s TEXT' % col)
    c.executemany('UPDATE poem SET trans=?, note=?, intro=? WHERE id=?',
                  [(v[0] or None, v[1] or None, v[2] or None, k) for k, v in upd.items()])
    db.commit()
    print('rows with trans now:', c.execute('SELECT COUNT(*) FROM poem WHERE trans IS NOT NULL').fetchone()[0])
    print('rows with note now:', c.execute('SELECT COUNT(*) FROM poem WHERE note IS NOT NULL').fetchone()[0])
    c.execute('VACUUM')
    db.commit()
    print('vacuumed', round(os.path.getsize(DB) / 1e6, 1), 'MB')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--apply' not in sys.argv
    paths = []
    for a in args:
        paths += sorted(glob.glob(a))
    main(paths, dry)