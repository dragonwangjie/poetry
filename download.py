import json, os, sys, time, urllib.request, concurrent.futures as cf

RAW = '/root/poetry/raw'
TREE = json.load(open('/root/poetry/tree_all.json'))
BLOBS = {t['path']: t['sha'] for t in TREE['tree'] if t['type'] == 'blob'}
BASE = 'https://api.github.com/repos/chinese-poetry/chinese-poetry/git/blobs/'
HDR = {'Accept': 'application/vnd.github.raw', 'User-Agent': 'poetry-etl'}

SMALL = ('诗经', '楚辞', '元曲', '曹操诗集', '纳兰性德', '五代诗词', '蒙学')

def want(p):
    if p.startswith('全唐诗/poet.tang.') and 'error' not in p:
        return True
    if p.startswith('全唐诗/authors.tang.json') or p.startswith('全唐诗/authors.song.json'):
        return True
    if p.startswith('全唐诗/唐诗三百首.json') or p.startswith('全唐诗/唐诗补录.json'):
        return True
    if p.startswith('宋词/ci.song.') or p.startswith('宋词/author.song.json'):
        return True
    if p.split('/')[0] in SMALL and p.endswith('.json'):
        return True
    return False

def song_want(p):
    return p.startswith('全唐诗/poet.song.') and 'error' not in p

def fetch(arg):
    path, sha = arg
    dest = os.path.join(RAW, path)
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and dest.endswith('.json'):
        try:
            json.load(open(dest, encoding='utf-8'))
            return ('skip', path, os.path.getsize(dest))
        except Exception:
            os.remove(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(BASE + sha, headers=HDR)
            data = urllib.request.urlopen(req, timeout=180).read()
            json.loads(data.decode('utf-8'))
            tmp = dest + '.part'
            open(tmp, 'wb').write(data)
            os.replace(tmp, dest)
            return ('ok', path, len(data))
        except Exception as e:
            last = str(e)[:80]
            time.sleep(2 + attempt * 3)
    return ('fail', path, last)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'core'
    sel = [t['path'] for t in TREE['tree'] if t['type'] == 'blob']
    paths = [(p, BLOBS[p]) for p in sel if (song_want(p) if mode == 'song' else want(p))]
    paths.sort(key=lambda x: x[0])
    total = sum(os.path.getsize(os.path.join(RAW, p)) if os.path.exists(os.path.join(RAW, p)) else 0 for p, _ in paths)
    print('tasks', len(paths), 'cached bytes', total, flush=True)
    t0 = time.time()
    ok = fail = 0
    got = 0
    with cf.ThreadPoolExecutor(6) as ex:
        for i, r in enumerate(ex.map(fetch, paths), 1):
            if r[0] == 'fail':
                fail += 1
                print('FAIL', r[1], r[2], flush=True)
            else:
                ok += 1
                got += r[2] if r[0] == 'ok' else 0
            if i % 20 == 0 or i == len(paths):
                el = time.time() - t0
                print(f'{i}/{len(paths)} ok={ok} fail={fail} newMB={got/1e6:.1f} {el:.0f}s', flush=True)
    print('DONE', ok, fail, flush=True)

main()
