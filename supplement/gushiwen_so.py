"""Candidates for gushiwen.cn rows that the category index does not list.

Why this exists: crawl_gushiwen.py finds a poem by looking its title up in cat_index.json,
built from the 69 category/anthology listing pages. That covers most textbook poems but not
all -- 观书有感二首·其一, 饮湖上初晴后雨二首 其二, 初夏睡起, 泛舟(朱熹) are not on any of
those pages, and their DB titles differ from the site's anyway (the site files them as
观书有感·其一 / 闲居初夏午睡起·其一).

The site's search page needs a login (search.aspx 302s to /user/login.aspx, so. subdomain
too), but the autocomplete endpoint behind the search box does not:
GET /shiwen2017/ajaxSearchSoD.aspx?valuekey=<q> with a desktop UA answers anonymously.
It returns up to three 诗文 rows as <a href="/shiwenv_ID">TITLE - AUTHOR</a> plus a 名句
block; those 名句 links point at /mingju/juv_* rather than a poem, so they are dropped.

Limits worth knowing before relying on it: prefix matching only, three rows, not
author-aware (q=田家 gives 孟浩然/聂夷中/欧阳修, never 范成大), and it does not tokenise a
multi-word query (q="田家 范成大" returns nothing). So it supplements cat_index rather than
replacing it, and every candidate still has to pass the body comparison in crawl_gushiwen.
"""
import hashlib
import html
import os
import re
import time
import urllib.parse

# crawl_gushiwen imports this module, so the dependency must stay one-way: the few helpers
# needed here (CACHE, DESKTOP, get, strip) are pulled in lazily inside so_query().

SO_API = 'https://www.gushiwen.cn/shiwen2017/ajaxSearchSoD.aspx?valuekey='
SO_LINK = re.compile(r'<a[^>]*href="/shiwenv_([0-9a-f]{12})\.aspx"[^>]*>(.*?)</a>', re.S)


def _g():
    """Resolve crawl_gushiwen lazily (it imports this module -- see header)."""
    import crawl_gushiwen
    return crawl_gushiwen


def so_rows(page):
    """-> [(id, title, author)] out of one suggestion response.

    Split on ' - ' before stripping: strip() collapses whitespace (these are Chinese
    texts), so stripping first would glue the separator into the title.
    """
    strip = _g().strip
    out = []
    for cid, label in SO_LINK.findall(page):
        txt = html.unescape(re.sub(r'<[^>]+>', '', label)).strip()
        t, sep, a = txt.rpartition(' - ')
        out.append((cid, strip(t if sep else txt), strip(a)))
    return out


def so_query(q, sleep=time.sleep):
    """-> [(id, title, author)] for one query string, cached under pages/so_*.html."""
    g = _g()
    cp = os.path.join(g.CACHE, 'so_' + hashlib.md5(q.encode('utf8')).hexdigest()[:16] + '.html')
    if os.path.exists(cp):
        return so_rows(open(cp, encoding='utf8', errors='ignore').read())
    html = g.get(SO_API + urllib.parse.quote(q), g.DESKTOP,
                 'https://www.gushiwen.cn/') or ''
    if html:
        os.makedirs(g.CACHE, exist_ok=True)
        open(cp, 'w', encoding='utf8').write(html)
    sleep(1.5)
    return so_rows(html)


def queries(title, body):
    """Query strings worth spending a request on, in order.

    Prefix matching means the DB title is usually too long or punctuated differently:
    the site files 观书有感二首·其一 as 观书有感·其一, so only a truncated stem
    (观书有感) prefix-matches. Hence: as stored, without parentheses, with the 其一/其二
    tail gone, with a trailing 二首/三首 gone, and finally the part after · or a space
    (题 X 间壁 style titles have no useful prefix). The endpoint matches titles only --
    a verse clause returns nothing -- so body is not queried, and each row costs at most
    len(queries) requests, all cached.
    """
    from apply_anno import PAREN, SEQ
    strip = _g().strip
    base = strip(PAREN.sub('', title))
    qs = [base]
    for q in (strip(SEQ.sub('', base).rstrip('·')),
              re.sub(r'[一二三四五六七八九十]+首$', '', base),
              re.sub(r'[一二三四五六七八九十]+首$', '', strip(SEQ.sub('', base).rstrip('·')))):
        qs.append(q)
    for sep in ('·', ' '):
        if sep in base:
            qs.append(strip(base.split(sep)[-1]))
    return [q for q in dict.fromkeys(qs) if len(q) >= 2]


def search_candidates(title, body):
    """Deduplicated candidate list across all queries for one row."""
    out, seen = [], set()
    for q in queries(title, body):
        for c in so_query(q):
            if c[0] not in seen:
                seen.add(c[0])
                out.append(c)
    return out
