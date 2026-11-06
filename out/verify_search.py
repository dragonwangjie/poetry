"""Regression battery for the verse lookup, mirroring PoemDb.searchVerses."""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import sqlite3
import sys
import time

DB = sys.argv[1] if len(sys.argv) > 1 else f'{_ROOT}/out/poetry_lite.db'
c = sqlite3.connect(DB).cursor()
PUNCT = set(' \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]')
s2t, ofs = {}, {}
for t, s in c.execute('SELECT t,s FROM t2s_map'):
    s2t[t] = s
    ofs.setdefault(s, []).append(t)
_coll = {}


def postings(ch):
    if ch not in _coll:
        r = c.execute('SELECT ids FROM char_index WHERE ch=?', (ch,)).fetchone()
        out, x, sh, prev = [], 0, 0, 0
        for by in (r[0] if r else b''):
            x |= (by & 0x7F) << sh
            if by & 0x80:
                sh += 7
            else:
                prev += x
                out.append(prev)
                x = sh = 0
        _coll[ch] = out
    return _coll[ch]


def char_lines(ch):
    acc = set(postings(ch))
    if ch in s2t:
        acc |= set(postings(s2t[ch]))
    for t in ofs.get(ch, []):
        acc |= set(postings(t))
    return sorted(acc)


def col(s):
    return ''.join(x for x in (s or '') if x not in PUNCT)


def rows(ids, cap):
    ids = sorted(ids)
    out = []
    for i in range(0, len(ids), 800):
        out += c.execute('SELECT l.id,l.poem_id,l.idx,l.text,IFNULL(a.poem_count,0),IFNULL(p.sig,\'\')'
                         ' FROM line l LEFT JOIN poem p ON p.id=l.poem_id'
                         ' LEFT JOIN author a ON a.id=p.author_id WHERE l.id IN(%s)'
                         % ','.join(map(str, ids[i:i + 800]))).fetchall()
        if len(out) >= cap:
            break
    return out[:cap]


def clause_lines(cl, cap):
    chars = list(dict.fromkeys(cl))
    L = [char_lines(x) for x in chars]
    if any(not p for p in L):
        return []
    L.sort(key=len)
    cand = set(L[0])
    for p in L[1:]:
        if not cand:
            break
        cand &= set(p)
    r = rows(cand, cap) if cand else []
    if r:
        return r
    if len(L) < 2:
        return r
    # union of the two rarest lists: when the intersection is empty the wanted line
    # can only live in one of them (mirrors PoemDb.clauseLines -> scanNear)
    anchor = sorted(set(L[0]) | (set(L[1]) if len(L) > 1 else set()))
    pool = rows(anchor, 60000)
    need = len(chars)
    out = []
    for x in pool:
        if sum(1 for ch in chars if ch in col(x[3])) >= need - 1:
            out.append(x)
            if len(out) >= 400:
                break
    return out


def cov(n, h):
    return sum(1 for ch in dict.fromkeys(n) if ch in h)


def kind(n, h):
    if h == n:
        return 0
    if n in h:
        return 1
    it = iter(h)
    return 2 if all(x in it for x in n) else 4


def search(raw, limit=20):
    q = col(''.join(s2t.get(x, x) for x in raw))
    out = []
    if len(q) < 2:
        return out
    if len(q) >= 8:
        mid = len(q) // 2
        pair = {}
        for d in range(4):
            for cut in ([mid] if d == 0 else [mid - d, mid + d]):
                if cut < 3 or cut > len(q) - 3:
                    continue
                f = clause_lines(q[:cut], 900)
                s = clause_lines(q[cut:], 900)
                nxt = {(r[1], r[2] + 1): r for r in f}
                for r in s:
                    p = nxt.get((r[1], r[2]))
                    if not p:
                        continue
                    key = p[3] + '|' + r[3]
                    # A wording found in two poems keeps the more prolific author's copy only
                    # when both poems have the identical full text (double attribution);
                    # otherwise the first hit stands (mirrors PoemDb.adjacentHits).
                    old = pair.get(key)
                    if old is not None and not (r[5] and r[5] == old[4] and r[4] > old[3]):
                        continue
                    pair[key] = (p[3] + ' / ' + r[3], 3, r[1], r[4], r[5])
        if pair:
            return [v[:3] for v in pair.values()][:limit]
    rs = clause_lines(q, 1200)
    sc = sorted(rs, key=lambda r: (-cov(q, col(r[3])), kind(q, col(r[3])), len(col(r[3]))))
    need = len(set(q))
    # one card per wording, in ranking order; a repeat may replace the keeper only when
    # both hits sit in poems with identical full text, i.e. a double attribution, and then
    # in favour of the more prolific author (mirrors PoemDb.searchVerses)
    best = {}
    for r in sc:
        st = col(r[3])
        if cov(q, st) < need - 1:
            continue
        old = best.get(st)
        if old is None or (r[5] and r[5] == old[5] and r[4] > old[4]):
            best[st] = r
    for st, r in best.items():
        out.append((r[3], kind(q, st), r[1]))
        if len(out) >= limit:
            break
    return out


EXPECT = {
    '床前明月光': '静夜思',
    '举头望明月': '静夜思',
    '欲穷千里目更上一层楼': '登鹳雀楼',
    '海内存知己天涯若比邻': '蜀州',
    '落霞与孤鹜齐飞': None,
    '但愿人长久': '水调歌头',
    '似曾相识燕归来': '浣溪沙',
    '大漠孤烟直': '使至塞上',
    '海上生明月': '望月怀远',
    '夕阳无限好': '乐游原',
    '春风又绿江南岸': '泊船瓜洲',
    '两个黄鹂鸣翠柳一行白鹭上青天': '绝句',
    '今人不见古时月': '把酒问月',
    '床前看月光': '静夜思',
    '明月': None,
    '白日依山尽': '登鹳雀楼',
    '春眠不觉晓': '春晓',
    '曾经沧海难为水': '离思',
    '此情可待成追忆': '锦瑟',
    '莫愁前路无知己': '别董大',
    # Guard the fame tie-break gate. 寿丘惟旧迹 opens two *different* poems: 太宗's
    # 幸武功庆善宫 (101 poems) and a 舞曲歌辞 credited to 不详 (885 poems). Only the
    # same-text case may be decided by fame, so the lower-id, lower-fame poem must win.
    '寿丘惟旧迹': '幸武功庆善宫',
    '悬弧亦在兹': '幸武功庆善宫',
}
ok = miss = 0
for q, want in EXPECT.items():
    t = time.time()
    h = search(q)
    ms = (time.time() - t) * 1000
    if not h:
        verdict = 'NONE'
        ok += want is None
        miss += 0 if want is None else 1
    else:
        ti, au = c.execute('SELECT p.title_s,a.name_s FROM poem p JOIN author a'
                           ' ON a.id=p.author_id WHERE p.id=?', (h[0][2],)).fetchone()
        good = want is None or want in ti
        verdict = 'ok ' if good else 'BAD'
        ok += 1 if good else 0
        miss += 0 if good else 1
        print('   top: 《%s》%s | %s' % (ti, au, h[0][0][:26]))
    print('%s %-18s %5.0fms  %s' % (verdict, q, ms, ''))
print('pass %d / %d (misses %d)' % (ok, len(EXPECT), miss))
