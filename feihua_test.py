_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import sqlite3, time, random, collections
DB = f'{_ROOT}/out/poetry_lite.db'
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
_cache = {}

def decode(blob):
    out = []
    x = 0
    sh = 0
    prev = 0
    for b in blob:
        x |= (b & 0x7f) << sh
        if b & 0x80:
            sh += 7
        else:
            prev += x
            out.append(prev)
            x = 0
            sh = 0
    return out

def postings(ch, pos=None):
    key = (ch, pos)
    if key in _cache:
        return _cache[key]
    if pos is None:
        row = db.execute('SELECT ids FROM char_index WHERE ch=?', (ch,)).fetchone()
    else:
        row = db.execute('SELECT ids FROM char_pos WHERE ch=? AND pos=?', (ch, pos)).fetchone()
    res = decode(row['ids']) if row else None
    _cache[key] = res
    return res

def variants(ch):
    v = [ch]
    r = db.execute('SELECT s FROM t2s_map WHERE t=?', (ch,)).fetchone()
    if r and r['s'] not in v:
        v.append(r['s'])
    for row in db.execute('SELECT t FROM t2s_map WHERE s=?', (ch,)).fetchall():
        if row['t'] not in v:
            v.append(row['t'])
    return v

def find_char(ch, pos=None):
    for c in variants(ch):
        p = postings(c, pos)
        if p:
            return c, p
    for c in variants(ch):
        if pos is not None:
            p = postings(c)
            if p:
                return c, p
    return None, None

def lines_of(ids, n=5, offset=0):
    ph = ','.join('?' * min(n, len(ids)))
    sel = ids[offset:offset + n]
    rows = db.execute('SELECT l.id, l.text, p.title_s, p.source, a.name_s FROM line l JOIN poem p ON p.id=l.poem_id JOIN author a ON a.id=p.author_id WHERE l.id IN (' + ph + ')', sel).fetchall()
    return [dict(r) for r in rows]

print('== 1 简体直接命中')
t0 = time.time()
c, p = find_char('月')
print(' ', c, len(p), '%.0fms' % ((time.time()-t0)*1000), lines_of(p, 2))
print('== 2 繁体输入 風 → 风')
t0 = time.time()
c, p = find_char('風')
print(' variants', variants('風'), '->', c, len(p) if p else 0, '%.0fms' % ((time.time()-t0)*1000))
print('== 3 繁体输入 花(同形) / 漢→汉 / 鶯→莺')
for ch in ['漢', '鶯', '鈴', '鐘']:
    c, p = find_char(ch)
    print(' ', ch, '->', c, len(p) if p else 0)
print('== 4 位置：花 第2字 / 尾字')
for pos in (1, 2, 4):
    c, p = find_char('花', pos)
    print('  pos', pos, c, len(p) if p else 0, lines_of(p, 2)[0]['text'] if p else '-')
print('== 5 末字（用len推算）：句末=花')
row = db.execute('SELECT ids FROM char_pos WHERE ch=? AND pos=?', ('花', 6)).fetchone()
tail = db.execute("SELECT COUNT(*) c FROM line WHERE text LIKE '%花'").fetchone()['c']
print('  pos6 count', len(decode(row['ids'])) if row else 0, ' LIKE %花 ->', tail, '(七言末字)')
print('== 6 多字交集 月+明')
t0 = time.time()
a = set(find_char('月')[1] or [])
b = set(find_char('明')[1] or [])
inter = sorted(a & b)
print(' ', len(a), len(b), 'inter', len(inter), '%.0fms' % ((time.time()-t0)*1000))
print(' ', lines_of(inter, 3))
print('== 7 冷僻字 / 无结果')
for ch in ['鹏', '鑫', '㊙', 'a']:
    c, p = find_char(ch)
    print(' ', repr(ch), '->', c, len(p) if p else 0)
print('== 8 AI 随机作答 100 次耗时（排除已用）')
random.seed(1)
used = set()
t0 = time.time()
c, p = find_char('月')
ok = 0
for i in range(100):
    pick = random.choice(p)
    if pick in used:
        continue
    used.add(pick)
    ok += 1
print('  answered', ok, 'of 100 in %.1fms' % ((time.time()-t0)*1000))
print('== 9 作者检索 杜甫')
a = db.execute("SELECT id,name_s,dynasty,poem_count,short_bio FROM author WHERE name_s LIKE ? ORDER BY poem_count DESC LIMIT 5", ('%甫%',)).fetchall()
print([dict(x) for x in a])
print('== 10 作者诗集分页 李白 offset 100 limit 3')
aid = db.execute("SELECT id FROM author WHERE name_s='李白'").fetchone()['id']
r = db.execute('SELECT id,title_s,line_count FROM poem WHERE author_id=? ORDER BY id LIMIT 3 OFFSET 100', (aid,)).fetchall()
print([dict(x) for x in r])
print('== 11 诗详情')
pid = r[0]['id']
d = db.execute('SELECT p.title_s,p.body,p.source,p.rhythmic,a.name_s FROM poem p JOIN author a ON a.id=p.author_id WHERE p.id=?', (pid,)).fetchone()
print(dict(d))
print('== 12 词牌 top')
print(db.execute("SELECT rhythmic, COUNT(*) c FROM poem WHERE source='全宋词' GROUP BY rhythmic ORDER BY c DESC LIMIT 5").fetchall())
print('== 13 高频字表（飞花令选题）')
print(db.execute("SELECT ch, cnt FROM char_index WHERE length(ch)=1 ORDER BY cnt BETWEEN 300 AND 3000 LIMIT 12").fetchall())