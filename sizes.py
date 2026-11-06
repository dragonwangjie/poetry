import json
d = json.load(open('/root/poetry/tree_all.json'))
B = [t for t in d['tree'] if t['type'] == 'blob']

def sz(pre, excl=()):
    s = [t for t in B if t['path'].startswith(pre) and not any(e in t['path'] for e in excl)]
    return len(s), round(sum(t.get('size', 0) for t in s) / 1e6, 1)

groups = [('全唐诗/poet.tang.', ()), ('全唐诗/poet.song.', ()), ('全唐诗/error/', ()),
          ('全唐诗/', ('poet.',)), ('strains/json/poet.tang.', ()), ('strains/json/poet.song.', ()),
          ('rank/', ()), ('御定全唐詩/', ()), ('宋词/ci.song', ()), ('宋词/', ('ci.song',)),
          ('蒙学/', ()), ('五代诗词/', ()), ('诗经/', ()), ('楚辞/', ()), ('元曲/', ()),
          ('曹操诗集/', ()), ('纳兰性德/', ()), ('论语/', ()), ('四书五经/', ()),
          ('幽梦影/', ()), ('水墨唐诗/', ())]
for pre, ex in groups:
    n, m = sz(pre, ex)
    print(f'{m:7.1f}MB {n:5d}  {pre}')
print('---- v1 core (tang+ci+small, no 宋诗/error)')
core = [t for t in B if (t['path'].startswith('全唐诗/poet.tang.') and 'error' not in t['path'])
        or t['path'].startswith('全唐诗/authors') or t['path'].startswith('宋词/ci.song')
        or t['path'].startswith('宋词/author')
        or t['path'].split('/')[0] in ('诗经', '楚辞', '元曲', '曹操诗集', '纳兰性德', '五代诗词', '论语', '幽梦影')]
print('files', len(core), 'MB', round(sum(t['size'] for t in core) / 1e6, 1))
