import base64, json, os, sys, urllib.request, urllib.parse
BASE = 'https://api.github.com/repos/chinese-poetry/huajianji/contents/data/'
os.makedirs('raw', exist_ok=True)
DIRS = ['教科书选诗', '千家诗', '唐诗三百首·蒙学', '唐诗三百首', '宋词三百首', '古诗十九首']
fails = []
for d in DIRS:
    url = BASE + urllib.parse.quote(d) + '?ref=master'
    try:
        items = json.load(urllib.request.urlopen(url, timeout=40))
    except Exception as e:
        print('DIR FAIL', d, e); continue
    for it in items:
        if it['type'] != 'file' or not it['name'].endswith('.json'):
            continue
        out = 'raw/%s__%s' % (d.replace('·', '-'), it['name'])
        if os.path.exists(out) and os.path.getsize(out) == it['size']:
            continue
        try:
            j = json.load(urllib.request.urlopen(it['url'], timeout=60))
            open(out, 'wb').write(base64.b64decode(j['content']))
            print('ok %8d %s' % (it['size'], os.path.basename(out)), flush=True)
        except Exception as e:
            fails.append((it['name'], str(e)))
            print('FAIL', it['name'], e, flush=True)
print('files now:', len(os.listdir('raw')), 'fails:', len(fails))
