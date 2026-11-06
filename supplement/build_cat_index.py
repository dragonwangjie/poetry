"""Index the downloaded 古诗文网 category pages: norm(title) -> [(id, title, author)].

Format on those pages is <span><a href="/shiwenv_ID.aspx" target="_blank">题名</a>(作者)</span>
repeated inside genre sections, so title and author come out of adjacent text, not nested tags.
Writes cat_index.json.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
_ANNO = __import__('os').environ.get('POETRY_ANNO') or '/root/anno'
_BAK = __import__('os').environ.get('POETRY_BAK') or '/root/backup'
import collections
import glob
import json
import re
import sys

sys.path.insert(0, f'{_ROOT}/supplement')
from apply_anno import norm  # noqa: E402

LINK = re.compile(r'<a href="/shiwenv_([0-9a-f]{12})\.aspx"[^>]*>(.*?)</a>\s*'
                  r'(?:\(([^)]{1,20})\))?', re.S)
idx = collections.defaultdict(list)
seen = set()
good = 0
for p in sorted(glob.glob(f'{_ANNO}2/cats/*.html')) + [f'{_ANNO}2/ts.html']:
    h = open(p, encoding='utf8', errors='ignore').read()
    if len(h) < 4000:                       # APP-redirect stub, not a real listing
        continue
    good += 1
    for pid, txt, au in LINK.findall(h):
        title = re.sub(r'<[^>]+>', '', txt).strip()
        author = (au or '').strip()
        if not title or (pid, title) in seen:
            continue
        seen.add((pid, title))
        idx[norm(title)].append([pid, title, author])
json.dump(idx, open(f'{_ROOT}/supplement/cat_index.json', 'w', encoding='utf8'), ensure_ascii=False)
print('pages with content: %d | distinct (id,title): %d | distinct titles: %d'
      % (good, len(seen), len(idx)))