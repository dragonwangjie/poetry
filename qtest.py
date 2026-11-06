_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import sqlite3, time, json, sys
DB = f'{_ROOT}/out/poetry_core.db'
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

def decode_ids(blob):
    out = []
    x = 0
    shift = 0
    prev = 0
    for b in blob:
        x |= (b & 0x7f) << shift
        if b & 0x80:
            shift += 7
        else:
            prev += x
            out.append(prev)
            x = 0
            shift = 0
    return out

print('--- row counts')
for t in ['author', 'poem', 'line', 'char_index', 'char_pos', 'pos_stats']:
    n = db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
    print('  %-12s rows=%d' % (t, n))

t0 = time.time()
for ch in ['月', '花', '春', '东', '鹏', '露']:
    row = db.execute('SELECT cnt, ids FROM char_index WHERE ch=?', (ch,)).fetchone()
    if not row:
        print(ch, 'none')
        continue
    ids = decode_ids(row['ids'])
    t1 = time.time()
    ph = ','.join('?' * min(len(ids), 30))
    rows = db.execute('SELECT l.text, p.title_s, a.name_s FROM line l JOIN poem p ON p.id=l.poem_id JOIN author a ON a.id=p.author_id WHERE l.id IN (' + ph + ') LIMIT 5', ids[:30]).fetchall()
    print('%s: cnt=%d decoded=%d total=%.0fms fetch=%.1fms ex=%s | %s' % (ch, row['cnt'], len(ids), (time.time()-t0)*1000, (time.time()-t1)*1000, rows[0]['text'] if rows else '-', rows[0]['name_s'] if rows else ''))

print('--- positional 第3字=花')
t0 = time.time()
r = db.execute('SELECT cnt, ids FROM char_pos WHERE ch=? AND pos=?', ('花', 2)).fetchone()
print('cnt', r['cnt'], '%.1fms' % ((time.time()-t0)*1000))

print('--- author 李白')
t0 = time.time()
a = db.execute("SELECT * FROM author WHERE name_s='李白'").fetchone()
d = dict(a)
d['bio_s'] = (d['bio_s'] or '')[:60]
print(d, '%.1fms' % ((time.time()-t0)*1000))
n = db.execute('SELECT COUNT(*) FROM poem WHERE author_id=?', (a['id'],)).fetchone()[0]
print('李白 poems', n)
r = db.execute('SELECT p.title_s, COUNT(l.id) c FROM poem p JOIN line l ON l.poem_id=p.id WHERE p.author_id=? AND l.text LIKE ? GROUP BY p.id LIMIT 5', (a['id'], '%月%')).fetchall()
print('李白含月诗', [dict(x) for x in r])

print('--- size by table')
try:
    for r in db.execute('SELECT name, SUM(pgsize)/1048576.0 mb FROM dbstat GROUP BY name ORDER BY mb DESC LIMIT 10'):
        print('  %-14s %.1fMB' % (r[0], r[1]))
except Exception as e:
    print(' dbstat unavailable', e)