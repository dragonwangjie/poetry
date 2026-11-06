"""Replicate PoemDb.searchTitles against the real DB.

The SQL is pulled out of PoemDb.java rather than retyped here: the method builds one of
two statements with ternaries, so the string literals are collected in source order and
re-assembled per branch. If the Java query changes shape, this harness has to change with
it (or an assertion fires), which is the point.

Usage: import it; see test_title_search.py. DB path via argv[1] or title_sql_harness.DB.
"""
import os, re, sqlite3, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', 'app', 'src', 'com', 'poetry', 'app', 'PoemDb.java')
src = open(os.path.abspath(SRC), encoding='utf8').read()
i = src.index('private List<VerseHit> titleRows')
j = src.index('while (c.moveToNext())', i)
L = [m.group(1).replace("\\'", "'")
     for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', src[i:j])]


def idx(sub, lo=0):
    for k in range(lo, len(L)):
        if sub in L[k]:
            return k
    raise AssertionError('missing SQL literal: %r' % sub)


sel = idx('SELECT p.id,p.title_s,a.name_s')
frm = idx(' FROM poem p JOIN author a')
dyw = idx(" WHERE (?='' OR IFNULL(a.dynasty,'')=?)")
exw = idx(' AND (p.title_s=? OR p.title=?)')
liw = idx(' AND (p.title_s LIKE ? OR p.title LIKE ?)')
neu = idx(' AND p.title_s<>? AND p.title<>?')
ord_ = idx(' ORDER BY')
pre = idx(' LIKE ? OR p.title LIKE ? THEN 1', ord_)   # prefix-tier CASE, loose branch only
lim = idx('p.id LIMIT ?')
assert sel < frm < dyw < exw < liw < neu < ord_ < pre < lim, (
    sel, frm, dyw, exw, liw, neu, ord_, pre, lim)

head = ''.join(L[sel:frm + 1]) + L[dyw]
# The prefix-tier CASE is only concatenated in the loose branch (Java's exactOnly ternary),
# so the exact statement must leave it out or the placeholder count would not match.
order_loose = ''.join(L[ord_:pre] + L[pre:lim]) + L[lim]
order_exact = ''.join(L[ord_:pre] + L[pre + 1:lim]) + L[lim]
SQL_EXACT = head + L[exw] + order_exact
SQL_LOOSE = head + L[liw] + L[neu] + order_loose
FETCH = 200   # mirrors Math.max(200, limit * 8) in titleRows
assert SQL_EXACT.count('?') == 5, SQL_EXACT.count('?')
assert SQL_LOOSE.count('?') == 9, SQL_LOOSE.count('?')

PUNCT = set(' \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]')
collapse = lambda s: ''.join(ch for ch in s if ch not in PUNCT)


def longest_chunk(s):
    best, start = '', 0
    for k in range(len(s) + 1):
        if k < len(s) and s[k] not in PUNCT:
            continue
        if k - start > len(best):
            best = s[start:k]
        start = k + 1
    return best


DB = sys.argv[1] if len(sys.argv) > 1 else '/tmp/inapk13.db'
db = sqlite3.connect(DB)


def title_rows(q, raw, limit, exact_only, dynasty=''):
    n = str(max(FETCH, limit * 8))
    if exact_only:
        args, sql = [dynasty, dynasty, q, raw, n], SQL_EXACT
    else:
        args = [dynasty, dynasty, '%' + q + '%', '%' + raw + '%', q, raw,
                q + '%', raw + '%', n]
        sql = SQL_LOOSE
    return [{'id': r[0], 'title': r[1], 'author': r[2], 'fame': r[3], 'dynasty': r[5]}
            for r in db.execute(sql, args)]


def pick_titles(q, raw, limit, dynasty=''):
    out, by_author = [], {}
    exact_cap = max(2, limit // 2)
    for p in (0, 1):
        for h in title_rows(q, raw, limit, p == 0, dynasty):
            if len(out) >= (exact_cap if p == 0 else limit):
                break
            n = by_author.get(h['author'], 0)
            if n >= 2:
                continue
            by_author[h['author']] = n + 1
            out.append(h)
    return out


def search_titles(raw, limit, dynasty=''):
    q = collapse(raw)
    if len(q) < 2:
        return []
    out = pick_titles(q, raw.strip(), limit, dynasty)
    if len(out) >= 4:
        return out
    best = longest_chunk(raw)
    if len(best) >= 2 and best != q:
        ids = {h['id'] for h in out}
        out += [h for h in pick_titles(best, best, limit, dynasty) if h['id'] not in ids]
    return out[:limit]