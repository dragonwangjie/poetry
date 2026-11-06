"""Fill-rate report for the annotation columns, split by source."""
import sqlite3
import sys

db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else '/root/poetry/out/poetry_lite.db')
c = db.cursor()
cols = [r[1] for r in c.execute('PRAGMA table_info(poem)')]
fields = [x for x in ('trans', 'note', 'intro', 'prologue') if x in cols]
srcs = [r[0] for r in c.execute('SELECT DISTINCT source FROM poem')]
print('%-8s %6s %s' % ('source', 'rows', '  '.join('%-12s' % f for f in fields)))
for s in srcs + ['<all>']:
    w = 'source=?' if s != '<all>' else '1=1'
    a = (s,) if s != '<all>' else ()
    total = c.execute('SELECT COUNT(*) FROM poem WHERE ' + w, a).fetchone()[0]
    cells = []
    for f in fields:
        n = c.execute("SELECT COUNT(*) FROM poem WHERE %s AND %s IS NOT NULL AND %s != ''"
                      % (w, f, f), a).fetchone()[0]
        cells.append('%-12s' % ('%d (%.0f%%)' % (n, 100.0 * n / total if total else 0)))
    print('%-8s %6d %s' % (s, total, '  '.join(cells)))
print('\n补录 samples with empty trans:')
for t, tr in c.execute("SELECT title_s, trans FROM poem WHERE source='补录'"
                       ' AND (trans IS NULL OR trans=\'\') LIMIT 5').fetchall():
    print('   ', t)
print('\n全唐诗 sample with trans (shape reference):')
r = c.execute("SELECT title_s, trans, note FROM poem WHERE source!='补录'"
              " AND trans IS NOT NULL AND trans != '' LIMIT 1").fetchone()
if r:
    print('   《%s》 trans: %s' % (r[0], (r[1] or '')[:90]))
    print('              note : %s' % (r[2] or '')[:90])
db.close()