import re
p = '/root/poetry/build_db.py'
s = open(p, encoding='utf-8').read()

# 1. build a char-level t2s map once, and make norm() use it (identical to Android side)
old = """def t2s(s):
    return cc.convert(s) if s else s"""
new = """_CMAP = {}

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
    return ''.join(m.get(c, c) for c in s)"""
assert old in s
s = s.replace(old, new, 1)

# 2. call build_cmap() at start of build()
s = s.replace("def build():\n    t0 = time.time()", "def build():\n    t0 = time.time()\n    build_cmap()", 1)

# 3. cmap persist loop can reuse _CMAP
old2 = s[s.index('    cmap = []'):s.index("    db.executemany('INSERT OR REPLACE INTO t2s_map VALUES(?,?)', cmap)")+len("    db.executemany('INSERT OR REPLACE INTO t2s_map VALUES(?,?)', cmap)")]
s = s.replace(old2, "    cmap = list(_CMAP.items())\n    db.executemany('INSERT OR REPLACE INTO t2s_map VALUES(?,?)', cmap)", 1)

open(p, 'w', encoding='utf-8').write(s)
import ast
ast.parse(s)
print('patched ok')