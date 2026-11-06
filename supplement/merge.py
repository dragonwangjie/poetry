"""Merge the anthology supplements into one deduplicated candidate list.

Sources: the huajianji checkout files in raw/ (教科书选诗 / 千家诗 / 唐诗三百首 /
宋词三百首 / 蒙学 / 古诗十九首) plus poems lifted verbatim from the big local
checkout by curate.py. Everything is simplified with the same OpenCC map the
original ETL used, split into 分句 exactly like build_db.py, then checked against
the live line table so a poem already present (静夜思 shows up in three anthologies)
is never inserted twice.

文言文 files are skipped on purpose: this library holds poetry, and prose paragraphs
would break the per-clause ruby layout.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import glob
import json
import os
import re
import sqlite3
import sys
import unicodedata

from opencc import OpenCC

ROOT = f'{_ROOT}'
DB = f'{ROOT}/out/poetry_lite.db'
RAW = f'{ROOT}/supplement/raw'
OUT = f'{ROOT}/supplement/new_poems.json'

cc = OpenCC('t2s')
SEP = re.compile('[\n\u2028\u2029\r]')
CLAUSE = re.compile(r'[，。！？；：,.!?:;、\u3000 ]')
DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]')
JUNK = re.compile(r'[□ㄋ︰\[\]]')
# 说文人语 not verse
SKIP_FILE = re.compile(r'文言文|介绍|convert')

DYN = {'两汉': '汉', '汉代': '汉', '汉': '汉', '先秦': '先秦', '秦': '先秦', '战国': '先秦',
       '魏晋': '魏晋', '六朝': '魏晋', '南北朝': '南北朝', '晋': '魏晋', '宋': '宋',
       '南宋': '宋', '北宋': '宋', '唐代': '唐', '唐': '唐', '五代': '五代',
       '元代': '元', '元': '元', '明代': '明', '明': '明', '清代': '清', '清': '清'}


def t2s(s):
    return cc.convert(s) if s else s


def clauses(raw):
    out = []
    for seg in SEP.split(raw):
        seg = seg.strip()
        if not seg:
            continue
        for c in CLAUSE.split(seg):
            c = c.strip()
            if c:
                out.append(c)
    return out


def norm(c):
    c = t2s(c)
    return ''.join(ch for ch in c if ch not in DROP)


def is_cjk(ch):
    try:
        return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(ch)
    except ValueError:
        return False


def clean_title(t):
    t = t2s(t or '').strip()
    t = re.sub(r'^[0-9a-zA-Z]\.|^\d+', '', t)
    return t.strip()


def load_source_rows():
    """yield (priority, file, title, author, dynasty, paragraphs, notes)"""
    for f in sorted(glob.glob(f'{RAW}/*.json')) + [f'{ROOT}/supplement/corpus.json']:
        base = os.path.basename(f)
        if SKIP_FILE.search(base):
            continue
        try:
            data = json.load(open(f, encoding='utf8'))
        except Exception as e:
            print('skip', base, e)
            continue
        if not isinstance(data, list):
            continue
        if 'curate' in base:
            prio = 5
        elif '教科书选诗' in base:
            prio = 0
        elif '古诗十九首' in base or 'g19' in base:
            prio = 1
        elif '宋词三百首' in base or '唐诗三百首' in base:
            prio = 2
        elif '千家诗' in base or 'qjs' in base:
            prio = 3
        else:
            prio = 4
        for p in data:
            if not isinstance(p, dict):
                continue
            paras = p.get('paragraphs') or p.get('paras') or p.get('content') or []
            paras = [x for x in paras if isinstance(x, str) and x.strip()]
            if not paras:
                continue
            yield (prio, base, clean_title(p.get('title') or p.get('title_cite') or ''),
                   t2s(p.get('author') or '佚名').strip(),
                   DYN.get((p.get('dynasty') or '').strip(), (p.get('dynasty') or '').strip()),
                   paras, p.get('notes') or [])


def main():
    db = sqlite3.connect(DB)
    c = db.cursor()
    known_titles = {r[0] for r in c.execute('SELECT DISTINCT title_s FROM poem')}

    # a verse probe index: build a set of every stored 分句 is too big (845k) but a
    # covering check per candidate only needs a few lookups, so query as we go.
    def in_db(clauses_norm):
        """True when the corpus already holds most of these clauses."""
        if not clauses_norm:
            return True
        hits = 0
        checked = 0
        probes = clauses_norm[:2] + clauses_norm[-2:]
        for cl in probes:
            checked += 1
            if c.execute('SELECT 1 FROM line WHERE text=? LIMIT 1', (cl,)).fetchone():
                hits += 1
        return checked and hits >= max(2, len(probes) - 1)

    cands = {}
    for prio, fname, title, author, dyn, paras, notes in load_source_rows():
        cls = []
        for raw in paras:
            for cl in clauses(raw):
                n = norm(cl)
                if n and len(n) <= 40 and not JUNK.search(n) and all(is_cjk(x) for x in n):
                    cls.append(n)
        if not cls:
            continue
        key = (title, author)
        rec = {'title': title, 'author': author, 'dynasty': dyn, 'clauses': cls,
               'notes': [t2s(x) for x in notes if isinstance(x, str)],
               'src': fname, 'orig': [t2s(x).strip() for x in paras]}
        old = cands.get(key)
        if old is None or (len(rec['clauses']), len(rec['notes'])) > (len(old['clauses']), len(old['notes'])):
            cands[key] = rec

    print('candidates after internal dedupe:', len(cands))
    fresh, dup_title, dup_verse = [], 0, 0
    for key, rec in cands.items():
        if rec['title'] in known_titles:
            dup_title += 1
            continue
        if in_db(rec['clauses']):
            dup_verse += 1
            continue
        fresh.append(rec)
    print('already have by title: %d | already have by verse: %d | NEW: %d'
          % (dup_title, dup_verse, len(fresh)))
    fresh.sort(key=lambda r: (r['dynasty'], r['author'], r['title']))
    json.dump(fresh, open(OUT, 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    print('-> %s' % OUT)
    by_src = {}
    for r in fresh:
        by_src[r['src']] = by_src.get(r['src'], 0) + 1
    for k, v in sorted(by_src.items(), key=lambda kv: -kv[1]):
        print('   %4d  %s' % (v, k))
    print('sample:')
    for r in fresh[:12]:
        print('   %s / %s / %s : %s' % (r['title'], r['author'], r['dynasty'],
                                        ' / '.join(r['clauses'][:2])[:36]))


if __name__ == '__main__':
    sys.exit(main())