import json, os, glob, collections, re

R = '/root/poetry/repo'

def head(p, n=1):
    with open(p, encoding='utf-8') as f:
        d = json.load(f)
    return d

def probe(p, label):
    d = head(p)
    if isinstance(d, dict):
        print(f'[{label}] dict keys={list(d.keys())[:8]}')
        k = list(d.keys())[0]
        v = d[k]
        print('  sample:', json.dumps(v, ensure_ascii=False)[:300] if not isinstance(v, list) else json.dumps(v[:2], ensure_ascii=False)[:300])
        return
    print(f'[{label}] list len={len(d)} keys={list(d[0].keys())}')
    print('  sample:', json.dumps(d[0], ensure_ascii=False)[:400])

probe(f'{R}/全唐诗/poet.tang.0.json', 'tang')
probe(f'{R}/全唐诗/poet.song.0.json', 'song')
probe(f'{R}/全唐诗/authors.tang.json', 'authors.tang')
probe(f'{R}/宋词/ci.song.0.json', 'ci')
probe(f'{R}/宋词/author.song.json', 'ci.authors')
probe(f'{R}/诗经/shijing.json', 'shijing')
probe(f'{R}/楚辞/chuci.json', 'chuci')
probe(f'{R}/元曲/yuanqu.json', 'yuanqu')
probe(f'{R}/曹操诗集/caocao.json', 'caocao')
probe(f'{R}/纳兰性德/纳兰性德诗集.json', 'nalan')
probe(f'{R}/五代诗词/huajianji/huajianji-1-juan.json', 'huajianji')
probe(f'{R}/五代诗词/nantang/poetrys.json', 'nantang')
probe(f'{R}/蒙学/tangshisanbaishou.json', 'tang300-mengxue')
probe(f'{R}/全唐诗/唐诗三百首.json', 'tang300')
probe(f'{R}/蒙学/qianjiashi.json', 'qianjiashi')

print('\n=== file inventory')
for pat in ['全唐诗/poet.tang.*.json', '全唐诗/poet.song.*.json', '宋词/ci.song.*.json']:
    fs = glob.glob(f'{R}/{pat}')
    fs = [f for f in fs if '/error/' not in f]
    print(pat, len(fs), round(sum(os.path.getsize(f) for f in fs) / 1e6, 1), 'MB')
err = glob.glob(f'{R}/全唐诗/error/*.json')
print('error files', len(err), round(sum(os.path.getsize(f) for f in err) / 1e6, 1), 'MB')

print('\n=== error dir sample')
if err:
    d = json.load(open(err[0], encoding='utf-8'))
    print(err[0], type(d).__name__, len(d))
    print(json.dumps(d[0], ensure_ascii=False)[:300] if isinstance(d, list) else list(d.items())[:2])
