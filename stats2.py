import json, os, glob, re, collections, unicodedata
from opencc import OpenCC
cc = OpenCC('t2s')
R = '/root/poetry/repo'

PUNCT = '，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—… \n'
def norm(s):
    s = cc.convert(s)
    return ''.join(ch for ch in s if ch not in PUNCT)

def is_cjk(ch):
    try:
        return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(ch)
    except ValueError:
        return False

tang = sorted(glob.glob(f'{R}/全唐诗/poet.tang.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
ci = sorted(glob.glob(f'{R}/宋词/ci.song.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))

lines = []
def feed(paras, src, pid, ai):
    for idx, ln in enumerate(paras):
        n = norm(ln)
        if not n:
            continue
        lines.append((n, src, pid, idx, ai))

def han_only(n):
    return all(is_cjk(c) for c in n) and 0 < len(n) <= 80

nlines = collections.Counter()
han_ratio = collections.Counter()
char_lines = collections.Counter()
for f in tang:
    arr = json.load(open(f, encoding='utf-8'))
    pid0 = os.path.basename(f)
    for pi, p in enumerate(arr):
        pid = f'{pid0}#{pi}'
        for ln in p.get('paragraphs', []):
            n = norm(ln)
            nlines['all'] += 1
            if han_only(n):
                nlines['han'] += 1
                for c in set(n):
                    char_lines[c] += 1
            else:
                if nlines['han'] < 3 and nlines['bad'] < 6:
                    pass
                nlines['bad'] += 1
                if nlines['bad'] <= 6:
                    print('BAD', repr(n)[:120])
for f in ci:
    arr = json.load(open(f, encoding='utf-8'))
    pid0 = os.path.basename(f)
    for pi, p in enumerate(arr):
        for ln in p.get('paragraphs', []):
            n = norm(ln)
            nlines['all'] += 1
            if han_only(n):
                nlines['han'] += 1
            else:
                nlines['bad'] += 1
                if nlines['bad'] <= 12 and nlines['bad'] > 6:
                    print('BADci', repr(n)[:120])
print('lines', dict(nlines))
print('distinct chars (tang han lines)', len(char_lines))
top = char_lines.most_common(15)
print('top chars', top)
tot = sum(char_lines.values())
print('total char->line postings (tang only) approx', tot)
big = [c for c, v in char_lines.items() if v > 2000]
print('chars with >2000 lines', len(big))
import statistics
vals = sorted(char_lines.values(), reverse=True)
print('median postings', vals[len(vals)//2], 'sum', sum(vals))
# 长度分布
print('sample normalized line', repr(norm('秦川雄帝宅，函谷壯皇居。')))
print('ci sample', repr(norm('气和玉烛，睿化著鸿明。')))