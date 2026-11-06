"""Scan every local candidate source for translation payload + coverage of the
still-uncovered 补录 rows, so we know whether a download is even needed.

Handles .json (list of dict), .ndjson, .jsonl, .npy (object array of dict or structured),
and directories of those. A record counts as usable if any translation-ish field is non-empty.
Matching against 补录 rows is by title only at this stage -- this is a ceiling estimate to
pick a source, not the final pairing (that stays with apply_anno.py's gated cascade).
"""
import collections
import json
import os
import re
import sqlite3

ROOTS = ['/root/anno', '/root/poetry/raw', '/root/poetry/sample']
TR_KEYS = ('trans', 'Translation', 'translation', '译文', 'translate', 'translate_s')
NT_KEYS = ('note', 'Annotation', 'annotation', '注释')
IN_KEYS = ('intro', 'Intro', '赏析', 'appreciation', '简介')
DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]\r\n\t ')
norm = lambda s: ''.join(c for c in re.sub(r'<[^>]+>', '', s or '') if c not in DROP)


def pick(r, keys):
    for k in keys:
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def iter_records(path):
    """Yield dicts from one file in whatever shape it is stored."""
    try:
        if path.endswith(('.ndjson', '.jsonl')):
            with open(path, encoding='utf8', errors='ignore') as fh:
                for line in fh:
                    if line.strip():
                        d = json.loads(line)
                        if isinstance(d, dict):
                            yield d
            return
        if path.endswith('.npy'):
            import numpy as np
            w = np.load(path, allow_pickle=True)
            for el in w:
                if isinstance(el, dict):
                    yield el
                elif hasattr(w, 'dtype') and w.dtype.names:
                    yield {n: el[i] for i, n in enumerate(w.dtype.names)}
            return
        if path.endswith('.json'):
            with open(path, encoding='utf8', errors='ignore') as fh:
                d = json.load(fh)
            if isinstance(d, dict):
                d = list(d.values())
            if isinstance(d, list):
                for r in d:
                    if isinstance(r, dict):
                        yield r
    except Exception as e:                       # unreadable / wrong shape
        print('   ! %-52s %s' % (os.path.basename(path), type(e).__name__))


def scan(path):
    """-> (rows, usable, title_index) for one file."""
    rows = usable = 0
    idx = collections.defaultdict(list)
    for r in iter_records(path):
        rows += 1
        tr, nt, ii = pick(r, TR_KEYS), pick(r, NT_KEYS), pick(r, IN_KEYS)
        if not (tr or nt or ii):
            continue
        usable += 1
        t = pick(r, ('title', 'Title', 'title_s', ' poemTitle', 'poem_title')) or \
            str(r.get('title') or '').strip()
        if t:
            idx[norm(t)].append((t, r.get('author') or r.get('Author') or '', tr, nt, ii))
        if rows % 200000 == 0:
            print('   ... %s %d rows' % (os.path.basename(path), rows))
    return rows, usable, idx


want = sqlite3.connect('/root/poetry/out/poetry_lite.db').execute(
    "SELECT p.title_s, a.name_s, p.body FROM poem p JOIN author a ON a.id=p.author_id"
    " WHERE p.source='补录' AND (trans IS NULL OR trans='')").fetchall()
print('uncovered 补录 rows:', len(want))

seen_files = 0
agg = collections.defaultdict(list)
for root in ROOTS:
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if not fn.endswith(('.json', '.ndjson', '.jsonl', '.npy')):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.getsize(p) < 1024:
                continue
            seen_files += 1
            rows, usable, idx = scan(p)
            if not usable:
                continue
            hit = sum(1 for t, _a, _b in want if norm(t) in idx)
            print('%-58s rows=%-8d usable=%-7d covers=%d' % (
                p.replace('/root/', ''), rows, usable, hit))
            for k, v in idx.items():
                agg[k].extend(v)
        if seen_files > 400:
            break

hit = [(t, a, len(agg.get(norm(t), []))) for t, a, _b in want if agg.get(norm(t))]
print('\nfiles scanned:', seen_files, '| aggregated annotated records:', len(agg))
print('union coverage of the %d uncovered 补录 rows: %d' % (len(want), len(hit)))
for t, a, n in hit[:12]:
    print('   %-20s %-6s candidates=%d' % (t, a, n))