"""Fetch 译文/注释/简析 for the uncovered 补录 rows from 古诗文网 (m./www.gushiwen.cn).

Why this source: the local corpus is exhausted (works.npy's 842,966 rows carry exactly the
same 11,476 annotated records as anno.ndjson), GitHub API is rate-limited from this egress
IP, raw.githubusercontent.com is blocked, codeload runs at ~35KB/s, and jsDelivr caps repos
at 50MB -- every bulk dump we found is over the cap. The site itself answers over plain HTTPS
at ~120KB/s, and its desktop page carries 译文/注释/简析 untruncated (only 赏析 is truncated
by the server, and 简析 covers that need).

Flow per row: mobile search by title -> candidate ids -> score each by (title, author) and
body similarity against our own text -> fetch the winner's desktop page -> parse fields.
Nothing is written to the DB here; this only produces gushiwen.ndjson for apply_anno.py's
gated cascade. Pages are cached under pages/ so re-runs are free.

Usage: python3 crawl_gushiwen.py [--limit N] [--all-missing]
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import html as htmlmod
from urllib.parse import quote

sys.path.insert(0, f'{_ROOT}/supplement')
from gushiwen_so import search_candidates
from apply_anno import bigrams, norm  # noqa: E402

DB = f'{_ROOT}/out/poetry_lite.db'
OUT = f'{_ROOT}/supplement/gushiwen.ndjson'
CACHE = f'{_ROOT}/supplement/pages'
INDEX = f'{_ROOT}/supplement/cat_index.json'
MOBILE = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) ' \
         'Chrome/120 Mobile Safari/537.36'
DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ' \
          'Chrome/120 Safari/537.36'
SLEEP = 1.5
strip = lambda s: re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', s or ''))


def get(url, ua, referer=None):
    """curl through the shell: python urllib has no working path to these hosts here."""
    cmd = ['curl', '-s', '-m', '30', '-A', ua]
    if referer:
        cmd += ['-e', referer]
    cmd.append(url)
    for attempt in range(3):
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 500:
            return r.stdout.decode('utf8', errors='ignore')
        time.sleep(2 + 3 * attempt)          # backoff; the site throttles bursts
    return ''


def search(title, html=None):
    """-> [(id, title, author, body)] from the mobile search page.

    html may be supplied by tests to exercise the parsing without touching the network.
    """
    html = html or get('https://m.gushiwen.cn/shiwens/default.aspx?value=' + quote(title), MOBILE)
    if not html:
        return []
    out = []
    for m in re.finditer(r'<div id="zhengwen([0-9a-f]{12})">(.*?)</div>\s*</div>', html, re.S):
        pid, blk = m.group(1), m.group(2)
        t = re.search(r'/shiwenv_%s\.aspx"><b>(.*?)</b>' % pid, blk, re.S)
        a = re.search(r'/authorv\.aspx\?name=[^"]*">\s*(?:<img[^>]*>\s*)?([^<]{1,14})</a>',
                      blk, re.S)
        b = re.search(r'class="contson"[^>]*>(.*?)</div>', blk, re.S)
        out.append((pid, strip(t.group(1)) if t else '', strip(a.group(1)) if a else '',
                    strip(b.group(1)) if b else ''))
    return out


def body_score(a, b):
    """Similarity between our text and the site's snippet (which may be only the first
    lines), so containment of the site snippet in ours is what matters."""
    if not a or not b:
        return 0.0
    if b[:12] and b[:12] in a:
        return 1.0
    x, y = bigrams(a), bigrams(b)
    return 2.0 * len(x & y) / (len(x) + len(y)) if x and y else 0.0


def text(html):
    """HTML -> readable text: <br>/<p> become newlines, other tags vanish.

    Newlines are kept on purpose: 注释 is one term per line on the site, and the app
    renders note/trans verbatim, so flattening them into one line would read badly.
    """
    s = re.sub(r'<br\s*/?>', '\n', html or '')
    s = re.sub(r'</p>', '\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = htmlmod.unescape(s).replace('\u3000', ' ')
    lines = [ln.strip() for ln in s.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def parse_desktop(html):
    """-> dict(body, trans, note, intro) from a www.gushiwen.cn/shiwenv_*.aspx page.

    The desktop template emits one <p> per block:
    <p><strong>译文<br /></strong>...</p> then <p><strong>注释<br /></strong>term<br />...</p>,
    with 简析 in its own <div class="contyishang">. 赏析 is served truncated (its tail is
    behind an XHR), which is why 简析 fills the 简介 slot.
    """
    b = re.search(r'class="contson"[^>]*>(.*?)</div>', html, re.S)

    def block(label):
        m = re.search(r'<strong>\s*%s\s*(?:及注释)?<br\s*/?>\s*</strong>(.*?)</p>' % label,
                      html, re.S)
        return text(m.group(1)) if m else ''

    trans, note = block('译文'), block('注释')
    jian = re.search(r'>简析</span></h2>.*?<p>(.*?)</p>', html, re.S)
    return dict(body=text(b.group(1)).replace('\n', '') if b else '',
                trans=trans, note=note, intro=text(jian.group(1)) if jian else '')


def parse_ajax(html):
    """-> dict(body, trans, note, intro) from /nocdn/ajaxshiwenDetailCont.aspx?value=yizhu.

    That endpoint is the 译文/注释 the desktop page hides behind a login click, but it does
    not actually check for the cookie -- it answers plain GETs. Its shape is per-line
    interleave, colour-coded rather than labelled:

        <p>原句<br /><span style="color:#518564">该句译文<br /></span>
              <span style="color:#af9100">该句注释</span></p>

    so green is 译文 and gold is 注释 (the same gold also marks ¹²³ footnotes and pinyin
    inside the verse line, which is why the verse has to be read with the gold spans
    stripped rather than by taking the block's text). Lines are rejoined with newlines,
    giving a 译文 that reads in the same order as the poem. intro stays empty: 简析 lives
    on the page, not here, and the trailing 参考文献 block is dropped on purpose.
    """
    SUP = '\u00b9\u00ba\u00bb\u2070-\u209c'
    coloured = lambda s, col: re.findall(r'<span style="color:%s[^"]*"[^>]*>(.*?)</span>' % col,
                                         s, re.S)
    drop = lambda s, col: re.sub(r'<span style="color:%s[^"]*"[^>]*>.*?</span>' % col, '', s,
                                 flags=re.S)
    blocks = re.findall(r'<p>(.*?)</p>', html, re.S)
    verse, trans, note = [], [], []
    for b in blocks:
        plain = strip(drop(drop(b, '#af9100'), '#518564'))
        if not plain:
            continue
        verse.append(plain)
        green = coloured(b, '#518564')
        if green:
            trans.append(strip(re.sub(r'<[^>]+>', '', ' '.join(green))))
        # Gold marks footnote markers and pinyin as well as annotations, so keep only runs
        # that actually read like a gloss: they carry a ： after the headword.
        runs = [strip(re.sub(r'<[^>]+>', '', g)) for g in coloured(b, '#af9100')]
        runs = [r for r in runs if '：' in r and not all(c in SUP for c in r)]
        if runs:
            note.append(' '.join(runs))
    joined = lambda xs: '\n'.join(x for x in xs if x)
    return dict(body=joined(verse), trans=joined(trans), note=joined(note), intro='')


def ajax_idjm(html, cid):
    """The key the yizhu/zhushi XHR wants, read off the detail page's own onclick handler.

    The handler is OnYiwenDetail(a, b) with both arguments quoted, but the quoting differs
    between templates, so the argument list is matched loosely and the 12-hex tokens inside
    it are taken from there: two were always the same value on the pages seen so far, and
    the second is the one the JS passes as the request id. Anything unexpected falls back
    to cid rather than guessing.
    """
    m = re.search(r'OnYiwen\w*\(([^)]{0,200})\)', html)
    if not m:
        return cid
    toks = re.findall(r'[0-9a-f]{12}', m.group(1))
    return toks[1] if len(toks) > 1 else (toks[0] if toks else cid)

def fetch_ajax(cid, idjm):
    """-> parsed dict from the 译文/注释 XHR, or None. Cached like the pages."""
    cp = os.path.join(CACHE, '%s.yizhu.html' % idjm)
    if os.path.exists(cp):
        html = open(cp, encoding='utf8', errors='ignore').read()
    else:
        html = get('https://www.gushiwen.cn/nocdn/ajaxshiwenDetailCont.aspx'
                   '?id=%s&value=yizhu' % idjm, DESKTOP,
                   'https://www.gushiwen.cn/shiwenv_%s.aspx' % cid)
        if html:
            open(cp, 'w', encoding='utf8').write(html)
        time.sleep(SLEEP)
    return parse_ajax(html) if html else None


def candidates(title, author, index):
    """(id, title, author) candidates for one of our rows, from the category index.

    The site's own search page needs a login (it 302s to /user/login.aspx), so candidates
    come from the category/anthology listing pages we downloaded instead -- see
    build_cat_index.py. Title matching is loose (series prefix, ·-subtitle, 其一 suffix,
    parenthetical all produce variants); every candidate still has to survive the body
    comparison in main(), because these lists are full of same-title-different-poem hits
    (七夕 杨朴 vs 白居易, 秋月 程颢 vs 朱熹, 田家 范成大 vs 郑獬, 洪适拟古 vs the
    古诗十九首 original...).
    """
    from apply_anno import PAREN, SEQ
    base = PAREN.sub('', title)
    keys = {norm(title), norm(base), norm(SEQ.sub('', base))}
    if '·' in base:
        keys |= {norm(base.split('·')[-1]), norm(base.replace('·', ''))}
    if ' ' in base:                       # 拟古十三首 今日良宴会 -> also try the last part
        keys.add(norm(base.split()[-1]))
    out = []
    for k in keys:
        for pid, t, a in index.get(k, []):
            if pid not in [c[0] for c in out]:
                out.append((pid, t, a))
    # Prefer same-author candidates: fewer fetches before the gate is satisfied.
    def rank(c):
        a = c[2]
        return (0 if (author and a and (author in a or a in author)) else
                1 if (not a or author in ('佚名',)) else 2)
    return sorted(out, key=rank)


# Titles to keep out of the search-suggest fallback (empty by default; the gate makes
# the fallback safe, this is only a manual brake if it ever misbehaves).
SO_SKIP = set()


def fetch_candidate(cid):
    """Detail page for one candidate id, cached under pages/<id>.html."""
    cp = os.path.join(CACHE, cid + '.html')
    if os.path.exists(cp):
        return open(cp, encoding='utf8', errors='ignore').read()
    html = get('https://www.gushiwen.cn/shiwenv_%s.aspx' % cid, DESKTOP,
               'https://www.gushiwen.cn/')
    if html:
        open(cp, 'w', encoding='utf8').write(html)
    time.sleep(SLEEP)
    return html


def try_candidates(nb, cands, cap=4):
    """-> (picked (cid, fields, sim) or None, ajax_fallbacks_used).

    Shared by the two candidate sources (category index, then search suggest) so both are
    gated identically -- the gate is what keeps 七夕/杨朴 from picking up 白居易's 译文.
    """
    got_ajax = 0
    for cid, ct, ca in cands[:cap]:
        html = fetch_candidate(cid)
        if not html:
            continue
        f = parse_desktop(html)
        # Gate on the fetched text, not on the listing: these anthologies are full of
        # same-title poems by other hands, and a shared title must not paste someone
        # else's 译文 onto our poem.
        sim = body_score(nb, norm(f['body']))
        if sim >= 0.5 and (not f['trans'] or not f['note']):
            # The page hides 译文/注释 behind a login-only click, but the XHR it calls
            # does not check the cookie -- and it is finer-grained anyway (per line).
            # Only the empty fields are filled: whatever the page already served stays.
            a = fetch_ajax(cid, ajax_idjm(html, cid))
            if a:
                f['trans'] = f['trans'] or a['trans']
                f['note'] = f['note'] or a['note']
                f['body'] = f['body'] or a['body']
                got_ajax += 1
        if f['trans'] and sim >= 0.5:
            return (cid, f, sim), got_ajax
    return None, got_ajax


def main():
    os.makedirs(CACHE, exist_ok=True)
    limit = 0
    args = sys.argv[1:]
    if '--limit' in args:
        limit = int(args[args.index('--limit') + 1])
    q = ("SELECT p.id,p.title_s,a.name_s,p.body FROM poem p JOIN author a ON a.id=p.author_id"
         " WHERE p.source='补录' AND (trans IS NULL OR trans='')"
         if '--all-missing' in args else
         "SELECT p.id,p.title_s,a.name_s,p.body FROM poem p JOIN author a ON a.id=p.author_id"
         " WHERE p.source='补录' AND (trans IS NULL OR trans='')"
         " AND (note IS NULL OR note='') AND (intro IS NULL OR intro='')")
    want = sqlite3.connect(DB).execute(q).fetchall()
    if limit:
        want = want[:limit]
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf8'):
            try:
                done.add(json.loads(line)['poem_id'])
            except Exception:
                pass
    print('targets=%d already_fetched=%d' % (len(want), len(done)))

    index = json.load(open(INDEX, encoding='utf8')) if os.path.exists(INDEX) else {}
    if not index:
        sys.exit('no %s -- run build_cat_index.py first' % INDEX)
    print('category index titles: %d' % len(index))

    fh = open(OUT, 'a', encoding='utf8')
    got = miss = got_ajax = 0
    for pid, title, author, body in want:
        if pid in done:
            continue
        nb = norm(body)
        cands = candidates(title, author, index)
        picked, used = try_candidates(nb, cands)
        got_ajax += used
        if not picked and title not in SO_SKIP:
            # The category index only covers 69 listing pages; the anonymous search-suggest
            # endpoint covers the rest (观书有感·其一, 闲居初夏午睡起·其一, ...). Same gate.
            picked2, used = try_candidates(nb, search_candidates(title, body))
            picked = picked or picked2
            got_ajax += used
        if not picked:
            print('  MISS   %-24s %-6s cands=%d' % (title[:24], author, len(cands)))
            miss += 1
            continue
        cid, f, sim = picked
        fh.write(json.dumps({'poem_id': pid, 'title': title, 'author': author,
                             'content': f['body'], 'trans': f['trans'], 'note': f['note'],
                             'intro': f['intro'],
                             'url': 'https://www.gushiwen.cn/shiwenv_%s.aspx' % cid},
                            ensure_ascii=False) + '\n')
        fh.flush()
        got += 1
        print('  OK     %-24s %-6s trans=%d note=%d intro=%d sim=%.2f'
              % (title[:24], author, len(f['trans']), len(f['note']), len(f['intro']), sim))
        time.sleep(SLEEP)
    fh.close()
    print('fetched=%d skipped=%d (xhr fallback used %d times)' % (got, miss, got_ajax))


if __name__ == '__main__':
    main()