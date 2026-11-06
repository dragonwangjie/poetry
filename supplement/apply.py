"""Insert supplement poems into the live DB, then rebuild both inverted indexes.

Why a full index rebuild instead of merging postings: line ids must stay a dense
increasing sequence (posting blobs are varint deltas over them). A rerun deletes the
previous 补录 lines, which opens gaps; renumbering to close the gaps would invalidate
every existing blob. Rebuilding char_index / char_pos / pos_stats from the line table
takes a few minutes and is the same computation build_db.py already does, so there is
one code path and nothing to go stale.

Re-runnable by design: 补录 rows are wiped first, ids are renumbered densely, then
everything is appended from new_poems.json.
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from array import array

sys.path.insert(0, '/root/poetry')
from build_pinyin import line_pinyin, load as load_pinyin  # noqa: E402

DB = '/root/poetry/out/poetry_lite.db'
SRC = '/root/poetry/supplement/new_poems.json'
SUP_SRC = '补录'
ANTHOLOGY = [('教科书选诗', '教科书选诗'), ('古诗十九首', '古诗十九首'), ('g19', '古诗十九首'),
             ('宋词三百首', '宋词三百首'), ('唐诗三百首__', '唐诗三百首'),
             ('蒙学', '蒙学'), ('千家诗', '千家诗'), ('qjs', '千家诗'), ('corpus', '补遗')]


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
    prev, buf = 0, bytearray()
    for i in ids:
        buf += varint(i - prev)
        prev = i
    return bytes(buf)


def is_cjk(ch):
    try:
        return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(ch)
    except ValueError:
        return False


DYN = {'宋代': '宋', '唐代': '唐', '元代': '元', '明代': '明', '清代': '清',
       '两汉': '汉', '汉代': '汉', '南宋': '宋', '北宋': '宋'}
# 敕勒歌 credits the anthology it survives in, not a poet; 七步诗 is 曹植 (魏).
FIX = {'敕勒歌': ('佚名', '南北朝'), '七步诗': ('曹植', '魏晋')}
# 词话/诗话 are criticism, not verse: they read as prose and break the ruby layout.
PROSE = re.compile(r'词话|诗话')
# 校勘按语 that some textbook dumps leave inside 诗句: 「版本二」「一作」
NOTE = re.compile(r'^(版本[一二三四五六七八九十\d]*|一作|一名|又名|一说|一本|其[一二三四五六七八九十])$')
MAX_CLAUSES = 140


def garbled(text):
    """True when a 分句 contains a Kangxi-radical fragment (a botched scan of 讚 etc.)."""
    for ch in text:
        try:
            if 'RADICAL' in unicodedata.name(ch):
                return True
        except ValueError:
            return True
    return False


def clean_clauses(cls, ci):
    """Trim editorial apparatus out of a 分句 list.

    The cut happens at the first note marker (七步诗 carries a second recension after
    「版本二」), then trailing single-character 分句 are dropped for 诗 — those are the
    leftovers of a 「坚劲一作韧」 gloss. 词 and 曲 keep short lines, which are real there
    (山坡羊: 兴，百姓苦 / 亡，百姓苦).
    """
    out = []
    for cl in cls:
        if NOTE.match(cl):
            break
        out.append(cl)
    if not ci:
        while out and len(out[-1]) < 2:
            out.pop()
    return [cl for cl in out if 0 < len(cl) <= 40 and all(is_cjk(x) for x in cl)
            and not garbled(cl)]


def anthology_of(src):
    for key, label in ANTHOLOGY:
        if key in src:
            return label
    return '补遗'


def wipe_and_renumber(c):
    """Remove previous supplement rows, then make line ids dense again."""
    old = [r[0] for r in c.execute('SELECT id FROM poem WHERE source=?', (SUP_SRC,))]
    if old:
        ph = ','.join(map(str, old))
        n = c.execute('SELECT COUNT(*) FROM line WHERE poem_id IN (%s)' % ph).fetchone()[0]
        c.execute('DELETE FROM line WHERE poem_id IN (%s)' % ph)
        c.execute('DELETE FROM poem WHERE source=?', (SUP_SRC,))
        print('cleared previous run: %d poems / %d lines' % (len(old), n))
    rows = c.execute('SELECT COUNT(*), MAX(id) FROM line').fetchone()
    if rows[0] and rows[1] + 1 == rows[0]:
        print('line ids already dense: %d' % rows[0])
        return
    ordered = c.execute('SELECT id FROM line ORDER BY poem_id, idx').fetchall()
    shifted = [(i + 10000000, r[0]) for i, r in enumerate(ordered)]
    c.executemany('UPDATE line SET id=? WHERE id=?', shifted)
    final = [(i, i + 10000000) for i in range(len(ordered))]
    c.executemany('UPDATE line SET id=? WHERE id=?', final)
    print('lines renumbered densely: %d' % len(ordered))


def insert_poems(c, poems, word, single):
    max_line = c.execute('SELECT MAX(id) FROM line').fetchone()[0]
    next_line = (max_line + 1) if max_line is not None else 0
    authors = {}
    for aid, name, dyn in c.execute('SELECT id, name_s, dynasty FROM author'):
        authors[(name, dyn)] = aid
    # The corpus' own 词牌 registry (1462 values) is the authority for 词: a 「·」 in a
    # title only means "sub-title", so 归园田居·其三 (a 组诗) must not become 词.
    tunes = {r[0] for r in c.execute(
        "SELECT DISTINCT rhythmic FROM poem WHERE form='词' AND rhythmic IS NOT NULL")}
    # 曲牌 absent from that registry; 补录 brings four 元明小令.
    qupai = {'天净沙', '山坡羊', '寿阳曲', '朝天子', '醉太平', '四块玉', '卖花声',
             '凭栏人', '落梅风', '醉中天', '拨不断', '端正好', '滚绣球', '哨遍'}
    # 词牌 aliases the corpus normalises away; without these 鹊踏枝 falls back to 诗.
    alias = {'鹊踏枝': '蝶恋花', '凤栖梧': '蝶恋花', '百字令': '念奴娇',
             '酹江月': '念奴娇', '壶中天': '念奴娇', '忆江南': '望江南',
             '解佩令': '解佩令'}
    print('词牌 registry: %d, 曲牌: %d' % (len(tunes), len(qupai)))
    added_p = added_l = 0
    skipped = []
    for rec in poems:
        title = rec['title'].split(' / ')[0].strip()
        author = (rec['author'] or '佚名').split(' / ')[0].strip()
        dyn = DYN.get(rec['dynasty'] or '', rec['dynasty'] or '')
        if title in FIX:
            author, dyn = FIX[title]
        ci = ('·' in title) or ('・' in title)
        if PROSE.search(title):
            skipped.append((title, author, 'prose'))
            continue
        tune0 = title.split('·')[0].split('・')[0] if ci else None
        is_ci = ci and (tune0 in tunes or tune0 in qupai or alias.get(tune0) in tunes)
        cls = clean_clauses(rec['clauses'], is_ci)
        if len(cls) < 2:
            skipped.append((title, author, 'no usable clause'))
            continue
        if len(cls) > MAX_CLAUSES:
            skipped.append((title, author, '%d clauses' % len(cls)))
            continue
        tune = title.split('·')[0].split('・')[0] if ci else None
        # alias only decides 词/曲; keep the tune as the title spells it, so
        # 鹊踏枝·叵耐灵鹊多谩语 is labelled 词牌「鹊踏枝」 rather than 蝶恋花.
        tuneKey = alias.get(tune, tune)
        if tune in qupai:
            form, rhythmic = '曲', tune
        elif tuneKey in tunes:
            form, rhythmic = '词', tune
        else:
            form, rhythmic = '诗', None
        if not is_ci:
            # a lone 序/曰 left over from a prose preface is not a verse line
            cls = [cl for cl in cls if len(cl) > 1]
            if len(cls) < 2:
                continue
        # 佚名 is one row per dynasty: the corpus' existing 佚名 carries 诗经 (先秦), and
        # reusing it would bury 古诗十九首 and 敕勒歌 under the wrong dynasty filter.
        key = (author, dyn)
        if key not in authors:
            cur = c.execute('INSERT INTO author(name,name_s,dynasty) VALUES(?,?,?)',
                            (author, author, dyn))
            authors[key] = cur.lastrowid
        aid = authors[key]
        if form in ('词', '曲'):
            body_lines = list(cls)
        else:
            body_lines = ['，'.join(cls[i:i + 2]) + '。' for i in range(0, len(cls), 2)]
        body = '\n'.join(body_lines)
        pys = [line_pinyin(ln, word, single) for ln in body.split('\n')]
        tpy = line_pinyin(title, word, single)
        tags = ['补录'] + [anthology_of(rec['src'])]
        cur = c.execute(
            'INSERT INTO poem(author_id,title,title_s,source,form,rhythmic,prologue,tags,'
            'line_count,body,note,py,title_py,sig) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (aid, title, title, SUP_SRC, form,
             rhythmic, None,
             json.dumps(tags, ensure_ascii=False), len(cls), body,
             '\n'.join(rec['notes']) if rec.get('notes') else None,
             '\n'.join(pys) if all(pys) else None, tpy or None, poem_sig(body)))
        pid = cur.lastrowid
        for li, txt in enumerate(cls):
            c.execute('INSERT INTO line(id,poem_id,idx,text,len) VALUES(?,?,?,?,?)',
                      (next_line, pid, li, txt, len(txt)))
            next_line += 1
            added_l += 1
        added_p += 1
    for t, a, why in skipped:
        print('   skip %-18s %-6s %s' % (t[:18], a, why))
    return added_p, added_l


def rebuild_index(c):
    c.execute('DELETE FROM char_index')
    c.execute('DELETE FROM char_pos')
    c.execute('DELETE FROM pos_stats')
    char_idx = {}
    char_pos = {}
    stats = {}
    n = 0
    for lid, txt in c.execute('SELECT id, text FROM line ORDER BY id'):
        n += 1
        L = len(txt)
        for pi, ch in enumerate(txt):
            char_pos.setdefault((ch, pi), array('L')).append(lid)
            char_pos.setdefault((ch, pi - L), array('L')).append(lid)
        for ch in set(txt):
            char_idx.setdefault(ch, array('L')).append(lid)
        stats[L] = stats.get(L, 0) + 1
        if n % 200000 == 0:
            print('   indexed %d lines' % n, flush=True)
    c.executemany('INSERT INTO char_index VALUES(?,?,?)',
                  [(ch, len(ids), encode_ids(ids)) for ch, ids in char_idx.items()])
    items = list(char_pos.items())
    c.executemany('INSERT INTO char_pos VALUES(?,?,?,?)',
                  [(ch, pos, len(ids), encode_ids(ids)) for (ch, pos), ids in items])
    c.executemany('INSERT INTO pos_stats VALUES(?,?)', list(stats.items()))
    return n, len(char_idx), len(items)


# whole-poem fingerprint; only ever compared against its own column, so the app never
# recomputes it. See supplement/add_sig.py for why the ranker needs it.
PUNCT = set(' \t\r\n，。！？；：、,.!?;:·…—-（）()「」『』“”‘’《》〈〉【】[]')


def poem_sig(body):
    return hashlib.md5(''.join(ch for ch in body or '' if ch not in PUNCT).encode('utf-8')).hexdigest()


def main():
    t0 = time.time()
    if not os.path.exists(DB + '.bak'):
        print('backup ->', DB + '.bak')
        os.system('cp %s %s.bak' % (DB, DB))
    poems = json.load(open(SRC, encoding='utf8'))
    print('supplement poems: %d' % len(poems))
    db = sqlite3.connect(DB)
    c = db.cursor()
    wipe_and_renumber(c)
    db.commit()
    word, single = load_pinyin()
    ap, al = insert_poems(c, poems, word, single)
    db.commit()
    print('inserted %d poems / %d lines (%.0fs)' % (ap, al, time.time() - t0))
    c.execute('UPDATE author SET poem_count=(SELECT COUNT(*) FROM poem WHERE author_id=author.id)'
              ' WHERE poem_count<> (SELECT COUNT(*) FROM poem WHERE author_id=author.id)')
    # a poet whose only poem got filtered out (王国维: 人间词话 is criticism) is dead weight
    c.execute('DELETE FROM author WHERE id NOT IN (SELECT DISTINCT author_id FROM poem)')
    n, nch, ncp = rebuild_index(c)
    db.commit()
    print('index rebuilt: %d lines, %d chars, %d (char,pos) (%.0fs)'
          % (n, nch, ncp, time.time() - t0))
    tot = c.execute('SELECT (SELECT COUNT(*) FROM poem),(SELECT COUNT(*) FROM line),'
                    ' (SELECT COUNT(*) FROM author), (SELECT COUNT(*) FROM poem WHERE source=?)',
                    (SUP_SRC,)).fetchone()
    print('poems/lines/authors/supplement:', tot)
    for k, v in [('poems', tot[0]), ('lines', tot[1]), ('authors', tot[2])]:
        c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (k, str(v)))
    db.commit()
    db.close()
    print('DONE %.0fs, db %.1f MB' % (time.time() - t0, os.path.getsize(DB) / 1e6))


if __name__ == '__main__':
    main()