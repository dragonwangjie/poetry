import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import title_sql_harness as sh

CASES = [('虞美人', '李煜'), ('浣溪沙', '李煜'), ('菩萨蛮', '李煜'),
         ('水调歌头', '苏轼'), ('登高', '杜甫'), ('静夜思', '李白'),
         ('春宵', '苏轼'), ('乐游原', '李商隐'), ('观书有感·其一', '朱熹'),
         ('江雪', '柳宗元'), ('黄鹤楼', '崔颢')]
fails = []
for raw, who in CASES:
    t = time.time()
    got = sh.search_titles(raw, 8)
    ms = (time.time() - t) * 1000
    has = any(who in h['author'] or who in h['title'] for h in got)
    if not has:
        fails.append(raw)
    print('%s %-14s %4.0fms -> %s' % ('ok  ' if has else 'FAIL', raw, ms,
          ' | '.join('%s/%s' % (h['title'][:13], h['author']) for h in got[:5])))

got = sh.search_titles('明月', 8)
print('first card 明月 = %s/%s' % (got[0]['title'], got[0]['author']))
if got[0]['title'] != '明月':
    fails.append('明月 exact must lead')
if len(sh.search_titles('静夜思', 8)) != 1:
    fails.append('静夜思 should be single card')
authors = [h['author'] for h in sh.search_titles('虞美人', 8)]
if max(authors.count(a) for a in set(authors)) > 2:
    fails.append('per-author cap broken')

# --- dynasty filter (the search box lives on the poet page, so the chips must filter too)
# 登高 is a 唐-only title in this corpus (all 56 rows), which is what the empty 宋 result
# below means -- asserted so that stays a data fact and not a silent filter regression.
for raw, dy, want in (('登高', '唐', True), ('登高', '宋', False), ('登高', '清', False),
                      ('虞美人', '宋', True), ('静夜思', '唐', True), ('静夜思', '宋', False)):
    got = sh.search_titles(raw, 8, dy)
    bad = [h for h in got if h['dynasty'] != dy]
    if bad:
        fails.append('%s/%s leaked %s' % (raw, dy, [h['dynasty'] for h in bad]))
    if want and not got:
        fails.append('%s/%s should have hits' % (raw, dy))
    if not want and got:
        fails.append('%s/%s should be empty, got %s' % (raw, dy, [h['title'] for h in got]))
    print('   filter %-8s %s -> %d rows: %s' % (raw, dy, len(got),
          ' | '.join('%s/%s(%s)' % (h['title'][:10], h['author'], h['dynasty']) for h in got[:3])))
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %s' % fails))