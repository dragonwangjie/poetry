_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import sqlite3
db = sqlite3.connect(f'{_ROOT}/out/poetry_lite.db')
for pos in (0, 1, -1, -2):
    r = db.execute('SELECT cnt FROM char_pos WHERE ch="花" AND pos=?', (pos,)).fetchone()
    print('pos', pos, 'cnt', r[0] if r else 0)
print('tail sample', db.execute('SELECT text FROM line WHERE id IN (SELECT id FROM char_pos WHERE ch="花" AND pos=-1 LIMIT 4)').fetchall())
print('char_pos rows', db.execute('SELECT COUNT(*) FROM char_pos').fetchone()[0])
print('pos -2 sample', db.execute('SELECT text FROM line WHERE id IN (SELECT id FROM char_pos WHERE ch="花" AND pos=-2 LIMIT 3)').fetchall())
