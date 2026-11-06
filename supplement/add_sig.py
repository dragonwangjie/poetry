#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add poem.sig: opaque fingerprint of the whole poem text.

The ranker breaks ties by author fame, which fixes double-attributed copies
(白日依山尽 sits in the 全唐诗 twice: 朱斌《登楼》 and 王之涣《登鹳雀楼》). Fame alone is too
blunt -- for two *different* poems sharing one line, the more prolific author would
wrongly win. sig says whether two hits are the same poem under two attributions,
and fame is only consulted then. The value is only compared against its own column,
so the app never recomputes it and no shared normalisation is needed. Punctuation is
stripped (same set as PoemDb.PUNCT) so copies differing only in punctuation match.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import hashlib, sqlite3, sys
PUNCT = set(' \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]')
def main(path):
    db = sqlite3.connect(path); c = db.cursor()
    if 'sig' not in [r[1] for r in c.execute('PRAGMA table_info(poem)')]:
        c.execute('ALTER TABLE poem ADD COLUMN sig TEXT'); print('added sig column')
    rows = c.execute('SELECT id, body FROM poem').fetchall()
    c.executemany('UPDATE poem SET sig=? WHERE id=?',
        [(hashlib.md5(''.join(ch for ch in b or '' if ch not in PUNCT)
          .encode('utf-8')).hexdigest(), i) for i, b in rows])
    # No index on sig: the app only compares fingerprints of rows it already fetched,
    # never searches by it. The index cost 11 MB of APK-compressed payload for no query.
    c.execute('DROP INDEX IF EXISTS poem_sig')
    db.commit()
    c.execute('VACUUM')
    db.commit()
    print('sig set on %d poems' % c.execute('SELECT COUNT(*) FROM poem WHERE sig IS NOT NULL').fetchone()[0])
    print('texts shared by 2+ copies:', c.execute(
        'SELECT COUNT(*) FROM (SELECT sig FROM poem GROUP BY sig HAVING COUNT(*)>1)').fetchone()[0])
    for r in c.execute("SELECT p.id,p.title_s,a.name_s,a.poem_count FROM poem p"
                       " JOIN author a ON a.id=p.author_id WHERE p.sig=("
                       "SELECT sig FROM poem WHERE title_s='登鹳雀楼'"
                       " AND author_id=(SELECT id FROM author WHERE name_s='王之涣'))"):
        print('   登鹳雀楼 group:', r)
    print('integrity:', c.execute('PRAGMA integrity_check').fetchone()[0])
    db.close()
if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else f'{_ROOT}/out/poetry_lite.db')
