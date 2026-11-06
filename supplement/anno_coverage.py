"""How many 补录 rows could be annotated from /root/anno/anno.ndjson?

Dry run only: prints hit counts per match tier, mirroring the cascade used by
add_translation2.py (normalized full text > (title, author) > title > first line).
"""
import json
import re
import sqlite3
import sys

DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]\r\n\t ')
TAG = re.compile(r'<[^>]+>')
ANNO = sys.argv[1] if len(sys.argv) > 1 else '/root/anno/anno.ndjson'
DB = sys.argv[2] if len(sys.argv) > 2 else '/root/poetry/out/poetry_lite.db'


def norm(s):
    return ''.join(ch for ch in TAG.sub('', s or '') if ch not in DROP)


by_text, by_ta, by_title = {}, {}, {}
for line in open(ANNO, encoding='utf8'):
    if not line.strip():
        continue
    d = json.loads(line)
    if not any(d.get(k) for k in ('trans', 'note', 'intro',
                                  'Translation', 'Annotation', 'Intro')):
        continue
    t, a = (d.get('title') or '').strip(), (d.get('author') or '').strip()
    if len(norm(d.get('content'))) >= 4:
        by_text.setdefault(norm(d['content']), (t, a))
    by_ta.setdefault((t, a), 1)
    by_title.setdefault(t, []).append(a)
print('annotation corpus: text=%d  (title,author)=%d  title=%d'
      % (len(by_text), len(by_ta), len(by_title)))

c = sqlite3.connect(DB).cursor()
rows = c.execute('SELECT p.id, p.title_s, p.body, a.name_s FROM poem p'
                 ' JOIN author a ON a.id=p.author_id WHERE p.source=\'补录\'').fetchall()
tier = {'text': 0, 'title_author': 0, 'title_unique': 0, 'none': 0}
missing = []
for pid, title, body, au in rows:
    if norm(body) in by_text:
        tier['text'] += 1
    elif (title, au) in by_ta or (norm(title), au) in by_ta:
        tier['title_author'] += 1
    elif len(by_title.get(title, [])) == 1:
        tier['title_unique'] += 1
    else:
        tier['none'] += 1
        missing.append('%s / %s' % (title, au))
print('补录 rows=%d -> %s' % (len(rows), tier))
print('no candidate (%d), first 8:' % len(missing))
for m in missing[:8]:
    print('   ', m)