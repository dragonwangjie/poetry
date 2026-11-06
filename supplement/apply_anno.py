"""Fill 译文/注释/简介 for the 补录 rows only, from /root/anno/anno.ndjson.

Scoped on purpose: apply.py deletes and re-inserts the 补录 rows after
add_translation2.py last ran, so those rows lost their annotations while the rest of the
corpus kept theirs. add_translation2.py itself rewrites trans/note/intro for every matched
poem in the DB, which would blank handwritten fields elsewhere -- so here we only touch
source='补录' and only columns that are currently empty.

Cascade mirrors add_translation2.py: normalized body > (title, author) > title with
其一/parenthetical stripped > first 10 chars + author > title when unique on both sides.
"""
import collections
import json
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
    s = TAG.sub('', s or '').replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'[ \t]+', ' ', s)
    return re.sub(r'\n{2,}', '\n', s).strip()


def bigrams(s):
    return set(s[i:i + 2] for i in range(len(s) - 1))


def similar(a, b):
    """Gate for the weak (title-based) tiers: comparable length, then opening/overlap.

    Without this, a shared title pastes one poem's 译文 onto another author's poem
    (《七夕》杨朴 picked up 李贺's), and a 其一 annotation lands on a merged 其二 edition
    whose text is twice as long. Body-tier matches skip the gate by construction.
    """
    if not a or not b:
        return False
    if 1.0 * min(len(a), len(b)) / max(len(a), len(b)) < 0.6:
        return False                      # different editions, not a usable annotation
    if a[:8] and a[:8] in b:
        return True
    x, y = bigrams(a), bigrams(b)
    if not x or not y:
        return False
    return 2.0 * len(x & y) / (len(x) + len(y)) >= 0.6


def load(path):
    out = []
    for line in open(path, encoding='utf8'):
        if not line.strip():
            continue
        r = json.loads(line)
        tr = clean(r.get('Translation') or r.get('trans') or '')
        nt = clean(r.get('Annotation') or r.get('note') or '')
        ii = clean(r.get('Intro') or r.get('intro') or '')
        if not (tr or nt or ii):
            continue
        rec = dict(title=norm(r.get('Title') or r.get('title') or ''),
                   author=norm(r.get('Author') or r.get('author') or ''),
                   body=norm(r.get('Content') or r.get('content') or ''),
                   trans=tr, note=nt, intro=ii)
        # Rows fetched per poem (crawl_gushiwen.py) already know their target row; keep the
        # id so they are applied directly instead of re-matched by title.
        if r.get('poem_id'):
            rec['poem_id'] = r['poem_id']
        out.append(rec)
    return out


def main(apply, paths=None):
    recs = []
    for p in (paths or [SRC]):
        recs.extend(load(p))
    db = sqlite3.connect(DB)
    c = db.cursor()
    rows = c.execute("SELECT p.id,p.body,p.title_s,a.name_s FROM poem p"
                     " JOIN author a ON a.id=p.author_id WHERE p.source='补录'").fetchall()
    by_body, by_ta, by_t2a, by_fa, by_title = {}, {}, {}, {}, {}
    body_of = {}
    for pid, body, title, author in rows:
        nb, nt, na = norm(body), norm(title), norm(author)
        body_of[pid] = body
        by_body.setdefault(nb, []).append(pid)
        by_ta.setdefault((nt, na), []).append(pid)
        by_t2a.setdefault((tkey(nt), na), []).append(pid)
        by_fa.setdefault((nb[:10], na), []).append(pid)
        by_title.setdefault(nt, []).append(pid)
    cnt = collections.Counter(r['title'] for r in recs)
    stat = collections.Counter()
    upd = {}
    # Direct hits first: records crawled per poem carry their own row id and were already
    # body-gated at crawl time, so they skip title matching entirely.
    for r in recs:
        pid = r.get('poem_id')
        if pid in body_of:
            stat['direct'] += 1
            cur = upd.get(pid, ('', '', ''))
            upd[pid] = (cur[0] or r['trans'], cur[1] or r['note'], cur[2] or r['intro'])
    for r in recs:
        if r.get('poem_id'):
            continue
        ids, how = None, None
        if r['body'] in by_body:
            ids, how = by_body[r['body']], 'body'
        else:
            tiers = (((r['title'], r['author']), by_ta, 'title+author'),
                     ((tkey(r['title']), r['author']), by_t2a, 'title-stripped+author'),
                     ((r['body'][:10], r['author']), by_fa, 'first10+author'))
            for i in range(4):
                if i < 3:
                    key, table, label = tiers[i]
                    cands = table.get(key)
                else:
                    label = 'title-only'
                    cands = by_title[r['title']] if len(by_title.get(r['title'], [])) == 1 \
                        and cnt[r['title']] == 1 else None
                if cands and similar(r['body'], norm(body_of[cands[0]])):
                    ids, how = cands, label
                    break
        if not ids:
            stat['miss'] += 1
            continue
        stat[how] += 1
        cur = upd.get(ids[0], ('', '', ''))
        upd[ids[0]] = (cur[0] or r['trans'], cur[1] or r['note'], cur[2] or r['intro'])
    print('corpus with payload:', len(recs), '| matched:', dict(stat))

    filled = collections.Counter()
    writes = []
    for pid, (tr, nt, ii) in upd.items():
        o_tr, o_nt, o_ii = c.execute('SELECT trans,note,intro FROM poem WHERE id=?',
                                     (pid,)).fetchone()
        n_tr = tr if not (o_tr or '').strip() else None
        n_nt = nt if not (o_nt or '').strip() else None
        n_ii = ii if not (o_ii or '').strip() else None
        filled['trans'] += bool(n_tr)
        filled['note'] += bool(n_nt)
        filled['intro'] += bool(n_ii)
        if n_tr or n_nt or n_ii:
            writes.append((n_tr, n_nt, n_ii, pid))
    print('would fill:', dict(filled), 'rows to write:', len(writes))
    left = c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
                     " AND (trans IS NULL OR trans='')").fetchone()[0]
    print('补录 without trans now: %d -> after: %d' % (left, left - filled['trans']))
    if not apply:
        print('DRY RUN (pass --apply to write)')
        return
    # Only-ever-fill: each SET is guarded so an existing value can never be blanked.
    c.executemany("UPDATE poem SET trans=COALESCE(NULLIF(trans,''),?), "
                  "note=COALESCE(NULLIF(note,''),?), intro=COALESCE(NULLIF(intro,''),?)"
                  " WHERE id=?", writes)
    db.commit()
    print('after: 补录 trans=%d note=%d intro=%d of' % (
        c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
                  " AND trans IS NOT NULL AND trans!=''").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
                  " AND note IS NOT NULL AND note!=''").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
                  " AND intro IS NOT NULL AND intro!=''").fetchone()[0]),
        c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'").fetchone()[0])
    print('other sources untouched, trans count:',
          c.execute("SELECT COUNT(*) FROM poem WHERE source!='补录'"
                    " AND trans IS NOT NULL AND trans!=''").fetchone()[0])
    db.close()


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    main('--apply' in sys.argv, args or None)