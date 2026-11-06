import json, os, glob, re, collections

R = '/root/poetry/repo'
files_tang = sorted(glob.glob(f'{R}/全唐诗/poet.tang.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
authors_tang = json.load(open(f'{R}/全唐诗/authors.tang.json', encoding='utf-8'))
print('tang files', len(files_tang))

names = collections.Counter()
paras_total = 0
poems = 0
tagged = 0
keyset = collections.Counter()
for f in files_tang:
    for p in json.load(open(f, encoding='utf-8')):
        poems += 1
        names[p.get('author', '')] += 1
        paras_total += len(p.get('paragraphs', []))
        keyset[tuple(sorted(p.keys()))] += 1
        if p.get('tags'):
            tagged += 1
print('tang poems', poems, 'lines', paras_total, 'tagged', tagged)
print('tang unique authors in poems', len(names))
print('keysets', keyset.most_common(4))
an = {a['name'] for a in authors_tang}
print('authors.tang entries', len(an))
miss = {n: c for n, c in names.items() if n not in an}
print('poem authors NOT in authors.tang:', len(miss), 'poems affected', sum(miss.values()))
print('  top missing', sorted(miss.items(), key=lambda x: -x[1])[:8])
print('  sample missing names', list(miss)[:10])
noauthor = sum(c for n, c in names.items() if not n.strip())
print('empty author poems', noauthor)
print('dup-ish names with space/suffix', [n for n in list(names)[:4000] if re.search(r'[ 0-9（(]', n)][:10])

# ci
ci_files = sorted(glob.glob(f'{R}/宋词/ci.song.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
cn = collections.Counter()
cp = 0
cl = 0
ckey = collections.Counter()
for f in ci_files:
    for p in json.load(open(f, encoding='utf-8')):
        cp += 1
        cn[p.get('author', '')] += 1
        cl += len(p.get('paragraphs', []))
        ckey[tuple(sorted(p.keys()))] += 1
cia = json.load(open(f'{R}/宋词/author.song.json', encoding='utf-8'))
print('\nci poems', cp, 'lines', cl, 'unique authors', len(cn))
print('ci keysets', ckey.most_common(4))
cian = {a['name'] for a in cia}
print('ci author entries', len(cian), 'poem authors missing bio', len([n for n in cn if n not in cian]))
print('ci rhythmic distinct', len({1 for _ in [0]}))
