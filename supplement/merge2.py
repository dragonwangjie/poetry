"""Build the final supplement list: deduped, source-prioritised, imitations removed.

Dedup rules (learned the hard way by merge.py):
 * Match against the live corpus by 分句 overlap, never by title alone — the corpus has
   its own 清明 (王禹偁) and 山行, which must not swallow 杜牧's poems.
 * Imitations are real poems but not what a reader searches for: 洪适《拟古·行行重行行》
   repeats the 古诗十九首 text verbatim, so the later author loses.
 * Same text under several anthology titles (饮湖上初晴后雨 / 饮湖上初晴后雨二首·其二)
   keeps one entry, preferring the textbook title, then the anthology, then the raw dump.
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
SKIP_FILE = re.compile(r'文言文|介绍|convert')
IMITATION = re.compile(r'拟古|拟陶|效陶|学陶|集句')
# Anthology misattributions worth correcting, keyed on the opening 分句. 千家诗 in this
# checkout prints 毕竟西湖六月中 under 苏轼 and 黄梅时节家家雨 under 司马光.
CANON = {
    '毕竟西湖六月中': ('晓出净慈寺送林子方', '杨万里', '宋'),
    '泉眼无声惜细流': ('小池', '杨万里', '宋'),
    '黄梅时节家家雨': ('约客', '赵师秀', '宋'),
    '清明时节雨纷纷': ('清明', '杜牧', '唐'),
    '锄禾日当午': ('悯农', '李绅', '唐'),
    '春眠不觉晓': ('春晓', '孟浩然', '唐'),
}

DYN = {'两汉': '汉', '汉代': '汉', '汉': '汉', '先秦': '先秦', '秦': '先秦', '战国': '先秦',
       '魏晋': '魏晋', '六朝': '魏晋', '南北朝': '南北朝', '晋': '魏晋', '宋': '宋',
       '南宋': '宋', '北宋': '宋', '唐代': '唐', '唐': '唐', '五代': '五代',
       '元代': '元', '元': '元', '明代': '明', '明': '明', '清代': '清', '清': '清'}

# how early a source is trusted for the canonical title
def priority(base):
    if '教科书选诗' in base:
        return 0
    if '古诗十九首' in base or 'g19' in base:
        return 1
    if '宋词三百首' in base or '唐诗三百首__' in base:
        return 2
    if '蒙学' in base:
        return 3
    if '千家诗' in base or 'qjs' in base:
        return 4
    if 'corpus' in base:
        return 6
    return 5


def t2s(s):
    return cc.convert(s) if s else s


def clauses_of(paras):
    out = []
    for raw in paras:
        for seg in SEP.split(raw):
            seg = seg.strip()
            if not seg:
                continue
            for cl in CLAUSE.split(seg):
                cl = cl.strip()
                if not cl:
                    continue
                n = ''.join(ch for ch in t2s(cl) if ch not in DROP)
                if (n and len(n) <= 40 and not JUNK.search(n)
                        and all(is_cjk(x) for x in n)):
                    out.append(n)
    return out


def is_cjk(ch):
    try:
        return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(ch)
    except ValueError:
        return False


def clean_title(t):
    t = t2s(t or '').strip()
    t = re.sub(r'^[0-9a-zA-Z]\.|^\d+', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def main():
    c = sqlite3.connect(DB).cursor()
    have = {}
    for title, author, cl in c.execute(
            'SELECT p.title_s, a.name_s, p.body FROM poem p'
            ' JOIN author a ON a.id=p.author_id'):
        have.setdefault((title, author), cl)
    # every stored 分句, for text-level dedup (845k strings, ~40 MB of hashes)
    stored = set(r[0] for r in c.execute('SELECT text FROM line'))
    print('corpus lines: %d' % len(stored))

    cands = {}
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
        for p in data:
            if not isinstance(p, dict):
                continue
            paras = p.get('paragraphs') or p.get('paras') or p.get('content') or []
            paras = [x for x in paras if isinstance(x, str) and x.strip()]
            title = clean_title(p.get('title') or p.get('title_cite') or '')
            author = t2s(p.get('author') or '佚名').strip()
            cls = clauses_of(paras)
            if not title or len(cls) < 2:
                continue
            if cls[0] in CANON:
                title, author, dyn = CANON[cls[0]]
            else:
                dyn = DYN.get((p.get('dynasty') or '').strip(),
                              (p.get('dynasty') or '').strip())
            rec = {'title': title, 'author': author, 'dynasty': dyn,
                   'clauses': cls, 'notes': [t2s(x) for x in (p.get('notes') or [])
                                             if isinstance(x, str)],
                   'src': base, 'prio': priority(base)}
            key = (title, author)
            old = cands.get(key)
            if old is None or (rec['prio'], -len(rec['clauses'])) < (old['prio'], -len(old['clauses'])):
                cands[key] = rec
    print('candidates: %d' % len(cands))

    # drop imitations of a poem the corpus already has
    fresh = []
    dropped_im = dropped_dup = kept_by_db = 0
    seen_text = {}
    for rec in sorted(cands.values(), key=lambda r: (r['prio'], r['title'])):
        cls = rec['clauses']
        overlap = sum(1 for cl in cls if cl in stored)
        if overlap >= max(2, (len(cls) + 1) // 2):
            kept_by_db += 1
            continue
        # 拟古/效陶: same text as an earlier poem, either already in the corpus or
        # accepted a moment ago from 古诗十九首.
        sig = tuple(cls[:3])
        if IMITATION.search(rec['title']) and (overlap > 0 or sig in seen_text):
            dropped_im += 1
            continue
        if sig in seen_text:
            dropped_dup += 1
            continue
        seen_text[sig] = rec['title']
        fresh.append(rec)
    print('already in corpus: %d | imitations dropped: %d | same-text dup: %d | NEW: %d'
          % (kept_by_db, dropped_im, dropped_dup, len(fresh)))
    fresh.sort(key=lambda r: (r['dynasty'], r['author'], r['title']))
    json.dump(fresh, open(OUT, 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    print('-> %s' % OUT)
    want = ['敕勒歌', '木兰诗', '归园田居', '饮酒', '七步诗', '赠从弟', '游园不值', '三衢道中',
            '题临安邸', '天净沙', '山坡羊', '石灰吟', '竹石', '所见', '惠崇春江晚景',
            '和子由渑池怀旧', '饮湖上初晴后雨', '观书有感', '蜂', '雪', '清明', '山行', '江上渔者']
    titles = [r['title'] for r in fresh]
    print('curated present:', [w for w in want if any(w in t for t in titles)])
    print('curated absent :', [w for w in want if not any(w in t for t in titles)])


if __name__ == '__main__':
    sys.exit(main())