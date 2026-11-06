import json, os, glob, re, collections, unicodedata
from opencc import OpenCC
cc = OpenCC('t2s')
R = '/root/poetry/repo'
SEP = re.compile('[\n\u2028\u2029\r]')
PUNCT = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]')

def t2s(s):
    return cc.convert(s)

def clauses(raw):
    out = []
    for seg in SEP.split(raw):
        seg = seg.strip()
        if not seg:
            continue
        for c in re.split(r'[，。！？；：,.!?:;、]', seg):
            c = c.strip()
            if c:
                out.append(c)
    return out

def is_cjk(ch):
    try:
        return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(ch)
    except ValueError:
        return False

def norm(s):
    s = t2s(s)
    return ''.join(ch for ch in s if ch not in PUNCT)

def stats(files, tag, collect_chars=True):
    cnt = collections.Counter()
    chars = collections.Counter()
    bad = []
    for f in files:
        for pi, p in enumerate(json.load(open(f, encoding='utf-8'))):
            for raw in p.get('paragraphs') or p.get('para') or p.get('content') or []:
                cnt['raw'] += 1
                cls = clauses(raw)
                cnt['clause'] += len(cls)
                if SEP.search(raw):
                    cnt['multiline_raw'] += 1
                for c in cls:
                    n = norm(c)
                    if n and all(is_cjk(x) for x in n) and len(n) <= 60:
                        cnt['good'] += 1
                        if collect_chars:
                            for ch in set(n):
                                chars[ch] += 1
                    else:
                        cnt['bad'] += 1
                        if len(bad) < 8:
                            bad.append(n or repr(c))
    print(f'== {tag}', dict(cnt))
    print('   bad samples', bad[:6])
    return cnt, chars

tang = sorted(glob.glob(f'{R}/全唐诗/poet.tang.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
_, ch_t = stats(tang, 'tang')
ci = sorted(glob.glob(f'{R}/宋词/ci.song.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
_, ch_c = stats(ci, 'ci')
song = sorted(glob.glob(f'{R}/全唐诗/poet.song.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
_, ch_s = stats(song[:20], 'song(sample 20 files)')

chars = ch_t + ch_c
print('distinct chars tang+ci', len(chars), 'postings', sum(chars.values()))
vals = sorted(chars.values(), reverse=True)
print('top20', [(c, v) for c, v in chars.most_common(20)])
print('p50', vals[len(vals)//2], 'chars>1000', sum(1 for v in vals if v > 1000))
print('chars==1', sum(1 for v in vals if v == 1))
# 常见字表对比：统计 3500 常用字覆盖
print('postings of 之乎者也以不有人', {c: chars.get(c, 0) for c in '之乎者也以不有人一二三'})