import base64, json, os, urllib.request, urllib.parse
TOK = os.environ.get('GHT')
BASE = 'https://api.github.com/repos/chinese-poetry/huajianji/contents/data/'
NEED = [('唐诗三百首·蒙学', 'a4.五言古詩.json'), ('唐诗三百首·蒙学', 'a5.七言古詩.json'),
        ('唐诗三百首·蒙学', 'a6.樂府.json'), ('唐诗三百首', '0.唐诗三百首.json'),
        ('宋词三百首', '0.宋词三百首.json')]
def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'poet-app', 'Accept': 'application/vnd.github+json'})
    if TOK:
        req.add_header('Authorization', 'Bearer ' + TOK)
    return json.load(urllib.request.urlopen(req, timeout=60))
for d, name in NEED:
    out = 'raw/%s__%s' % (d.replace('·', '-'), name)
    if os.path.exists(out):
        print('have', name); continue
    try:
        it = [x for x in get(BASE + urllib.parse.quote(d) + '?ref=master') if x['name'] == name][0]
        j = get(it['url'])
        open(out, 'wb').write(base64.b64decode(j['content']))
        print('ok %8d %s' % (it['size'], name), flush=True)
    except Exception as e:
        print('FAIL', name, e, flush=True)
