"""ETL: chinese-poetry JSON -> SQLite (poet collections + feihua reverse index)."""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import hashlib
import json, os, glob, re, sys, sqlite3, time, collections, unicodedata
from array import array
from opencc import OpenCC

R = f'{_ROOT}/repo'
OUT = f'{_ROOT}/out'
MODE = sys.argv[1] if len(sys.argv) > 1 else 'core'   # core | song | lite (lite = what ships: no 元曲, no secondary indexes)
cc = OpenCC('t2s')
SEP = re.compile('[\n\u2028\u2029\r]')
CLAUSE = re.compile(r'[，。！？；：,.!?:;、\u3000 ]')
DROP = set('，。！？；：、「」『』“”‘’（）《》,.!?;:() 　·—…-_~*[]')
JUNK = re.compile(r'[□ㄋ︰\[\]]')
TAGNUM = re.compile(r'\u3016[^\u3017]*\u3017|\u3014[^\u3015]*\u3015')

_CMAP = {}

def build_cmap():
    for o in range(0x3400, 0xA000):
        ch = chr(o)
        v = cc.convert(ch)
        if v and v != ch and len(v) == 1:
            _CMAP[ch] = v
    for extra in '麵麵髮麯乾餘後的裡裡醜後蘇週':
        v = cc.convert(extra)
        if v and v != extra and len(v) == 1:
            _CMAP[extra] = v
    return _CMAP

def t2s(s):
    if not s:
        return s
    m = _CMAP
    if not m:
        build_cmap()
        m = _CMAP
    return ''.join(m.get(c, c) for c in s)

def clauses(raw):
    out = []
    for seg in SEP.split(raw):
        seg = seg.strip()
        if not seg:
            continue
        for c in CLAUSE.split(seg):
            c = c.strip()
            if c:
                out.append(c)
    return out

def norm(c):
    c = t2s(c)
    return ''.join(ch for ch in c if ch not in DROP)

def is_cjk(ch):
    try:
        return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(ch)
    except ValueError:
        return False

def clean_name(n):
    return TAGNUM.sub('', n or '').strip()

def varint(x):
    out = bytearray()
    while True:
        b = x & 0x7F
        x >>= 7
        out.append(b | (0x80 if x else 0))
        if not x:
            break
    return bytes(out)

def encode_ids(ids):
    prev = 0
    buf = bytearray()
    for i in ids:
        buf += varint(i - prev)
        prev = i
    return bytes(buf)

SCHEMA = '''
PRAGMA journal_mode=OFF;
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE author(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_s TEXT, dynasty TEXT,
  bio TEXT, bio_s TEXT, short_bio TEXT, sources TEXT, poem_count INTEGER DEFAULT 0);
CREATE INDEX author_name ON author(name_s);
CREATE TABLE poem(
  id INTEGER PRIMARY KEY, author_id INTEGER, title TEXT, title_s TEXT,
  source TEXT, form TEXT, rhythmic TEXT, prologue TEXT, tags TEXT, line_count INTEGER,
  body TEXT, sig TEXT);
CREATE INDEX poem_author ON poem(author_id);
CREATE INDEX poem_source ON poem(source);
CREATE TABLE line(
  id INTEGER PRIMARY KEY, poem_id INTEGER, idx INTEGER, text TEXT, len INTEGER);
CREATE INDEX line_poem ON line(poem_id);
CREATE TABLE char_index(ch TEXT PRIMARY KEY, cnt INTEGER, ids BLOB);
CREATE TABLE char_pos(ch TEXT, pos INTEGER, cnt INTEGER, ids BLOB, PRIMARY KEY(ch,pos));
CREATE TABLE pos_stats(pos INTEGER PRIMARY KEY, cnt INTEGER);
CREATE TABLE t2s_map(t TEXT PRIMARY KEY, s TEXT);
'''

# poem.sig: whole-poem fingerprint, so the search ranker may only break ties by author
# fame between genuine double attributions (see supplement/add_sig.py).
PUNCT = set(' \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]')
def poem_sig(body):
    return hashlib.md5(''.join(ch for ch in body or '' if ch not in PUNCT).encode('utf-8')).hexdigest()


def open_db(path):
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db

def add_author(db, cache, name, dynasty, bio, source):
    key = (name, dynasty)
    if key in cache:
        return cache[key]
    cur = db.execute('INSERT INTO author(name,name_s,dynasty,bio,bio_s,short_bio,sources) VALUES(?,?,?,?,?,?,?)',
                     (name, t2s(name), dynasty, bio, t2s(bio) if bio else None, None, json.dumps([source], ensure_ascii=False)))
    cid = cur.lastrowid
    cache[key] = cid
    return cid

def iter_core():
    """yield dict rows normalized"""
    # ---- 全唐诗
    files = sorted(glob.glob(f'{R}/全唐诗/poet.tang.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
    for f in files:
        for p in json.load(open(f, encoding='utf-8')):
            yield dict(author=p.get('author', ''), title=p.get('title', ''), paras=p.get('paragraphs') or [],
                       source='全唐诗', form='诗', rhythmic=None, prologue=None, tags=p.get('tags'),
                       notes=None, cid=p.get('id'))
    for extra, tag in (('全唐诗/唐诗补录.json', '全唐诗补录'),):
        if os.path.exists(f'{R}/{extra}'):
            for p in json.load(open(f'{R}/{extra}', encoding='utf-8')):
                yield dict(author=p.get('author', ''), title=p.get('title', ''), paras=p.get('paragraphs') or [],
                           source=tag, form='诗', rhythmic=None, prologue=None, tags=p.get('tags'), notes=None, cid=p.get('id'))
    # ---- 宋词
    files = sorted(glob.glob(f'{R}/宋词/ci.song.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
    for f in files:
        for p in json.load(open(f, encoding='utf-8')):
            yield dict(author=p.get('author', ''), title=p.get('rhythmic', ''), paras=p.get('paragraphs') or [],
                       source='全宋词', form='词', rhythmic=p.get('rhythmic'), prologue=p.get('prologue'),
                       tags=p.get('tags'), notes=None, cid=None)
    # ---- 五代词
    for f in sorted(glob.glob(f'{R}/五代诗词/huajianji/*.json')):
        for p in json.load(open(f, encoding='utf-8')):
            if not isinstance(p, dict):
                continue
            yield dict(author=p.get('author', ''), title=p.get('title', ''), paras=p.get('paragraphs') or [],
                       source='花间集', form='词', rhythmic=p.get('rhythmic'), prologue=None, tags=None, notes=p.get('notes'), cid=None)
    nf = f'{R}/五代诗词/nantang/poetrys.json'
    if os.path.exists(nf):
        for p in json.load(open(nf, encoding='utf-8')):
            yield dict(author=p.get('author', ''), title=p.get('title', ''), paras=p.get('paragraphs') or [],
                       source='南唐二主词', form='词', rhythmic=p.get('rhythmic'), prologue=None, tags=None, notes=p.get('notes'), cid=None)
    # ---- 诗经 / 楚辞
    for path, src in ((f'{R}/诗经/shijing.json', '诗经'), (f'{R}/楚辞/chuci.json', '楚辞')):
        if not os.path.exists(path):
            continue
        for p in json.load(open(path, encoding='utf-8')):
            yield dict(author=p.get('author') or ('佚名' if src == '诗经' else '屈原'),
                       title=f"{p.get('section','')}·{p.get('title','')}" if src == '诗经' else p.get('title', ''),
                       paras=p.get('content') or [], source=src, form='诗',
                       rhythmic=None, prologue=None, tags=[p.get('chapter')] if p.get('chapter') else None, notes=None, cid=None)
    # ---- 曹操诗集 / 纳兰性德
    p_ = f'{R}/曹操诗集/caocao.json'
    if os.path.exists(p_):
        for p in json.load(open(p_, encoding='utf-8')):
            yield dict(author='曹操', title=p.get('title', ''), paras=p.get('paragraphs') or [], source='曹操诗集',
                       form='诗', rhythmic=None, prologue=None, tags=None, notes=None, cid=None)
    p_ = f'{R}/纳兰性德/纳兰性德诗集.json'
    if os.path.exists(p_):
        for p in json.load(open(p_, encoding='utf-8')):
            yield dict(author=p.get('author') or '纳兰性德', title=p.get('title', ''), paras=p.get('para') or [],
                       source='纳兰性德', form='词', rhythmic=None, prologue=None, tags=None, notes=None, cid=None)
    # ---- 元曲
    p_ = f'{R}/元曲/yuanqu.json'
    if os.path.exists(p_) and MODE != 'lite':
        for p in json.load(open(p_, encoding='utf-8')):
            yield dict(author=p.get('author', ''), title=p.get('title', ''), paras=p.get('paragraphs') or [],
                       source='元曲', form='曲', rhythmic=None, prologue=None, tags=None, notes=None, cid=None)

def iter_song():
    files = sorted(glob.glob(f'{R}/全唐诗/poet.song.*.json'), key=lambda p: int(re.findall(r'\d+', os.path.basename(p))[-1]))
    for f in files:
        for p in json.load(open(f, encoding='utf-8')):
            yield dict(author=p.get('author', ''), title=p.get('title', ''), paras=p.get('paragraphs') or [],
                       source='全宋诗', form='诗', rhythmic=None, prologue=None, tags=p.get('tags'), notes=None, cid=p.get('id'))

def load_authors():
    """name_s -> (dynasty, bio, short)"""
    out = {}
    def put(name, dynasty, bio, short=''):
        name = clean_name(name)
        if not name:
            return
        k = t2s(name)
        cur = out.get(k)
        if cur:
            if bio and len(bio) > len(cur[1] or ''):
                out[k] = (cur[0], bio, cur[2] or short)
        else:
            out[k] = (dynasty, bio or '', short)
    for a in json.load(open(f'{R}/全唐诗/authors.tang.json', encoding='utf-8')):
        put(a['name'], '唐', a.get('desc'))
    for a in json.load(open(f'{R}/全唐诗/authors.song.json', encoding='utf-8')):
        put(a['name'], '宋', a.get('desc'))
    for a in json.load(open(f'{R}/宋词/author.song.json', encoding='utf-8')):
        put(a['name'], '宋', a.get('description'), a.get('short_description'))
    return out

def build():
    t0 = time.time()
    build_cmap()
    os.makedirs(OUT, exist_ok=True)
    path = f'{OUT}/poetry_{MODE}.db'
    db = open_db(path)
    bios = load_authors()
    authors = {}          # name_s -> author_id
    char_idx = collections.defaultdict(lambda: array('L'))
    char_pos = collections.defaultdict(lambda: array('L'))
    n_poem = n_line = n_skip = 0
    pos_stats = collections.Counter()
    src_stats = collections.Counter()

    cur0 = db.execute('INSERT INTO author(name,name_s,dynasty) VALUES(?,?,?)', ('佚名', '佚名', ''))
    authors['佚名'] = cur0.lastrowid

    def get_author(name_raw):
        name = clean_name(name_raw)
        if not name:
            name = '佚名'
        k = t2s(name)
        aid = authors.get(k)
        if aid:
            return aid
        dynasty, bio, short = bios.get(k, ('', None, ''))
        cur = db.execute('INSERT INTO author(name,name_s,dynasty,bio,bio_s,short_bio) VALUES(?,?,?,?,?,?)',
                         (name, k, dynasty, bio, t2s(bio) if bio else None, short or None))
        aid = cur.lastrowid
        authors[k] = aid
        return aid

    rows_src = iter_song() if MODE == 'song' else iter_core()
    buf_lines = []
    for p in rows_src:
        aid = get_author(p['author'])
        raw_paras = [x.strip() for x in (p['paras'] or []) if isinstance(x, str) and x.strip()]
        cls = []
        for raw in raw_paras:
            cls += clauses(raw)
        good = []
        orig = []
        for c in cls:
            n = norm(c)
            if n and len(n) <= 40 and not JUNK.search(n) and all(is_cjk(x) for x in n):
                good.append(n)
                orig.append(c)
            else:
                n_skip += 1
        if not good:
            n_skip += 1
            continue
        title = (p['title'] or '').strip()
        body = '\n'.join(orig)
        tags = p.get('tags')
        final_body = SEP.sub('\n', t2s('\n'.join(raw_paras)))
        cur = db.execute('INSERT INTO poem(author_id,title,title_s,source,form,rhythmic,prologue,tags,line_count,body,sig) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                         (aid, title, t2s(title), p['source'], p['form'], p['rhythmic'],
                          (t2s(p['prologue']) if p['prologue'] else None),
                          json.dumps(tags, ensure_ascii=False) if tags else None, len(good),
                          final_body, poem_sig(final_body)))
        pid = cur.lastrowid
        for li, txt in enumerate(good):
            lid = n_line
            n_line += 1
            buf_lines.append((lid, pid, li, txt, len(txt)))
            L = len(txt)
            for pi, ch in enumerate(txt):
                char_pos[(ch, pi)].append(lid)
                char_pos[(ch, pi - L)].append(lid)
            for ch in set(txt):
                char_idx[ch].append(lid)
            pos_stats[len(txt)] += 1
        n_poem += 1
        src_stats[p['source']] += 1
        if len(buf_lines) >= 50000:
            db.executemany('INSERT INTO line(id,poem_id,idx,text,len) VALUES(?,?,?,?,?)', buf_lines)
            buf_lines.clear()
        if n_poem % 20000 == 0:
            db.commit()
            print(f'  poems={n_poem} lines={n_line} authors={len(authors)} {time.time()-t0:.0f}s', flush=True)
    db.executemany('INSERT INTO line(id,poem_id,idx,text,len) VALUES(?,?,?,?,?)', buf_lines)
    buf_lines.clear()
    db.commit()
    print('poems done', n_poem, f'{time.time()-t0:.0f}s', flush=True)

    db.executemany('UPDATE author SET poem_count=(SELECT COUNT(*) FROM poem WHERE author_id=?) WHERE id=?',
                   [(r[0], r[0]) for r in db.execute('SELECT id FROM author').fetchall()])
    for ch, ids in char_idx.items():
        db.execute('INSERT INTO char_index VALUES(?,?,?)', (ch, len(ids), encode_ids(ids)))
    items = list(char_pos.items())
    db.executemany('INSERT INTO char_pos VALUES(?,?,?,?)',
                   [(ch, pos, len(ids), encode_ids(ids)) for (ch, pos), ids in items])
    for pos, c in pos_stats.items():
        db.execute('INSERT INTO pos_stats VALUES(?,?)', (pos, c))
    cmap = list(_CMAP.items())
    db.executemany('INSERT OR REPLACE INTO t2s_map VALUES(?,?)', cmap)
    src_dynasty = {'全唐诗': '唐', '全唐诗补录': '唐', '全宋诗': '宋', '全宋词': '宋', '花间集': '五代',
                   '南唐二主词': '五代', '诗经': '先秦', '楚辞': '先秦', '曹操诗集': '汉', '元曲': '元', '纳兰性德': '清'}
    bysrc = collections.defaultdict(lambda: collections.defaultdict(int))
    for aid, src, c in db.execute('SELECT author_id, source, COUNT(*) FROM poem GROUP BY author_id, source').fetchall():
        bysrc[aid][src] = c
    upd = []
    for aid, d in bysrc.items():
        if not db.execute('SELECT 1 FROM author WHERE id=? AND (dynasty IS NULL OR dynasty="")', (aid,)).fetchone():
            continue
        top = max(d.items(), key=lambda kv: kv[1])[0]
        upd.append((src_dynasty.get(top, ''), aid))
    db.executemany('UPDATE author SET dynasty=? WHERE id=?', upd)
    meta = {'poems': n_poem, 'lines': n_line, 'authors': len(authors), 'skipped_clauses': n_skip,
            'sources': json.dumps(dict(src_stats), ensure_ascii=False), 'built_at': time.strftime('%F %T'),
            'schema_ver': '1', 'mode': MODE}
    db.executemany('INSERT OR REPLACE INTO meta VALUES(?,?)', list(meta.items()))
    db.commit()
    if MODE == 'lite':
        db.execute('DROP INDEX line_poem')
        db.execute('DROP INDEX poem_source')
    db.commit()
    print('index done', f'{time.time()-t0:.0f}s', flush=True)
    db.close()
    print('DONE', path, round(os.path.getsize(path) / 1e6, 1), 'MB', f'{time.time()-t0:.0f}s', meta, flush=True)

build()