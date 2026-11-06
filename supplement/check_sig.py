"""Check poem.sig is consistent for rows written by either path (apply.py or add_sig.py).

apply.py deletes and re-inserts the 补录 rows, so after a re-run their fingerprints come
from apply.py's own poem_sig(); every other row still carries the value add_sig.py wrote.
If the two implementations disagreed, a double attribution spanning both sources would
stop matching and silently lose the fame tie-break.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import hashlib
import sqlite3
import sys

PUNCT = set(' \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]')


def expect(body):
    return hashlib.md5(''.join(ch for ch in body or '' if ch not in PUNCT).encode('utf-8')).hexdigest()


db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else f'{_ROOT}/out/poetry_lite.db')
c = db.cursor()
bad = 0
for src in ('补录', '全唐诗'):
    rows = c.execute('SELECT id, body, sig FROM poem WHERE source=? LIMIT 400', (src,)).fetchall()
    wrong = [i for i, b, s in rows if s != expect(b)]
    bad += len(wrong)
    print('%-6s checked %d, mismatched %d' % (src, len(rows), len(wrong)))
null = c.execute('SELECT COUNT(*) FROM poem WHERE sig IS NULL OR sig=\'\'').fetchone()[0]
print('rows without sig:', null)
groups = c.execute('SELECT COUNT(*) FROM (SELECT sig FROM poem GROUP BY sig'
                   " HAVING COUNT(*)>1 AND COUNT(DISTINCT author_id)>1)").fetchone()[0]
print('double-attributed texts still grouped:', groups)
print('integrity:', c.execute('PRAGMA integrity_check').fetchone()[0])
db.close()
sys.exit(1 if bad or null else 0)