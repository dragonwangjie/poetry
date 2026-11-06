#!/usr/bin/env python3
"""Add pinyin (with tone marks) for every poem title and body line.

Word segmentation is forward maximum matching against the pinyin-pro modern dict, so
polyphones follow the phrase reading (还 huán in 还乡, hái as a lone character). The
result lands in poem.title_py and poem.py, one pinyin line per body line.
"""
import json
import re
import sqlite3
import sys
import time

DB = '/root/poetry/out/poetry_lite.db'
DICT = '/root/poetry/pydict/modern-dict.json'
SINGLE_JS = '/root/poetry/pydict/pinyin_dict_withtone.js'
HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
# Readings that the dictionary mis-handles often enough to be worth pinning.
OVERRIDE = {
    '单于': 'chán yú', '可汗': 'kè hán', '莫邪': 'mò yé', '萧萧': 'xiāo xiāo',
    '漫漫': 'màn màn', '帖帖': 'tiē tiē', '藉': 'jiè', '卷': 'juàn',
    '还乡': 'huán xiāng', '还家': 'huán jiā', '还来': 'huán lái', '飞将': 'fēi jiàng',
    '不教': 'bù jiào', '胡马': 'hú mǎ', '天涯': 'tiān yá', '分明': 'fēn míng',
}
# Characters outside the U+4E00..U+9FA5 block that the codepoint table cannot cover.
RARE = {
    '䜩': 'yàn', '㶉': 'xī', '䕷': 'téng', '䴖': 'jīng', '䴔': 'jiāo', '䍠': 'jùn',
    '㴩': 'xiāo', '䯄': 'guā', '䴙': 'pì', '䗖': 'dì', '㔉': 'chú', '㧑': 'huī',
    '䙰': 'bì', '㬠': 'shàn', '䝙': 'chū', '䒠': 'méng', '䆗': 'tiǎo', '㭊': 'yà',
    '䝟': 'měi', '㸌': 'huò', '䲡': 'qiū', '䅉': 'yà', '㗫': 'wā', '㒿': 'ruò',
    '䑳': 'xún', '㾕': 'lái', '䍥': 'xūn', '䨴': 'duì', '䏶': 'fèi', '㟧': 'è',
    '㮰': 'ní', '䪥': 'páo', '鬬': 'dòu', '㸃': 'diǎn', '䔤': 'chóu', '䓞': 'dí',
    '㛑': 'làn', '䢼': 'lì', '䬃': 'sè', '䧟': 'xiàn', '䑕': 'shǔ', '䢱': 'dú',
    '㷇': 'qióng', '䕡': 'niè', '㬠': 'shàn', '䧤': 'qún', '䢅': 'zhāo', '㫤': 'shū',
    '䢂': 'xiè', '㶏': 'wēi', '㳝': 'yǒu', '䓍': 'shào', '䢙': 'hóu', '㔙': 'hú',
    '䬘': 'lí', '㾀': 'guǐ', '䶉': 'xī', '䳍': 'lí', '㶑': 'yì', '䑋': 'běi',
}
MAXW = 8


def load_single():
    """pinyin_dict_withtone.js lists one entry per codepoint from U+4E00 upward."""
    s = open(SINGLE_JS, encoding='utf-8').read()
    if s.startswith('\ufeff'):
        s = s[1:]
    s = s[s.index('=') + 1:].strip().rstrip(';').strip('"')
    arr = s.split(',')
    out = {}
    for i, v in enumerate(arr):
        v = v.strip()
        if v:
            out[chr(0x4E00 + i)] = v.split()[0]
    return out


def load():
    raw = json.load(open(DICT, encoding='utf8'))
    word = {}
    for w, v in raw.items():
        if isinstance(v, list) and v and isinstance(v[0], str):
            word[w] = v[0]
    for w, p in OVERRIDE.items():
        word[w] = p
    single = load_single()
    single.update(RARE)
    single.update({w: p for w, p in word.items() if len(w) == 1})
    return word, single


def line_pinyin(text, word, single):
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if not HAN.match(ch):
            i += 1
            continue
        got = None
        for L in range(min(MAXW, n - i), 1, -1):
            p = word.get(text[i:i + L])
            if p and len(p.split()) == L:
                got = p
                i += L
                break
        if got is None:
            p = single.get(ch)
            if p is None:
                return ''      # unknown reading: drop the line rather than mis-align it
            got = p
            i += 1
        out.append(got)
    return ' '.join(out)


def main():
    t0 = time.time()
    word, single = load()
    print('dict words %d, single %d' % (len(word), len(single)))
    db = sqlite3.connect(DB)
    c = db.cursor()
    cols = [r[1] for r in c.execute('PRAGMA table_info(poem)')]
    if 'py' not in cols:
        c.execute('ALTER TABLE poem ADD COLUMN py TEXT')
    if 'title_py' not in cols:
        c.execute('ALTER TABLE poem ADD COLUMN title_py TEXT')
    rows = c.execute('SELECT id,title_s,body FROM poem').fetchall()
    print('poems', len(rows))
    batch = []
    done = miss = 0
    for pid, title, body in rows:
        tp = line_pinyin(title or '', word, single)
        lines = [x.strip() for x in (body or '').split('\n') if x.strip()]
        pys = [line_pinyin(x, word, single) for x in lines]
        joined = '\n'.join(pys)
        if any(p == '' for p in pys):
            miss += 1
        batch.append((tp or None, joined or None, pid))
        if len(batch) >= 5000:
            c.executemany('UPDATE poem SET title_py=?, py=? WHERE id=?', batch)
            batch = []
            done += 5000
            print('  %d poems, %.0fs' % (done, time.time() - t0), flush=True)
    c.executemany('UPDATE poem SET title_py=?, py=? WHERE id=?', batch)
    db.commit()
    print('lines with no reading at all: %d' % miss)
    print('coverage', c.execute(
        'SELECT SUM(py IS NOT NULL), SUM(title_py IS NOT NULL), COUNT(*) FROM poem').fetchone())
    c.execute('VACUUM')
    db.commit()
    import os
    print('db MB', round(os.path.getsize(DB) / 1e6, 1), 'secs', round(time.time() - t0))


if __name__ == '__main__':
    sys.exit(main())