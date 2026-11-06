import json,urllib.request,time,concurrent.futures as cf,base64,os
D=json.load(open('tree_all.json'))
sel=[t for t in D['tree'] if t['type']=='blob' and t['path'].startswith('全唐诗/poet.tang.')]
sel.sort(key=lambda t:t['path'])
targets=[t for t in sel if 'error' not in t['path']][:8]
BASE='https://api.github.com/repos/chinese-poetry/chinese-poetry/git/blobs/'
def get(t):
    req=urllib.request.Request(BASE+t['sha'],headers={'Accept':'application/vnd.github.raw','User-Agent':'x'})
    t0=time.time()
    try:
        d=urllib.request.urlopen(req,timeout=120).read()
        return t['path'],len(d),time.time()-t0
    except Exception as e:
        return t['path'],-1,str(e)[:60]
for n in (1,4,8):
    batch=targets[:n] if n<=len(targets) else targets
    t0=time.time()
    with cf.ThreadPoolExecutor(n) as ex:
        res=list(ex.map(get,batch))
    tot=sum(r[1] for r in res if r[1]>0)
    el=time.time()-t0
    print(f'par={n} bytes={tot} elapsed={el:.1f}s agg={tot/el/1024:.0f}KB/s', 'ERR' if any(r[1]<0 for r in res) else '')
    for r in res: print('   ',r[0],r[1],round(time.time()*0+ (r[2] if isinstance(r[2],float) else 0),1))
