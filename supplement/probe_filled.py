"""Pick 补录 rows whose 释文 was filled, and how to reach them from a search box."""
import sqlite3
import sys

c = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1
                    else '/root/poetry/out/poetry_lite.db').cursor()
rows = c.execute(
    "SELECT a.name_s, a.poem_count, COUNT(*),"
    " SUM(CASE WHEN p.trans IS NOT NULL AND p.trans != '' THEN 1 ELSE 0 END) AS f,"
    " group_concat(p.title_s, ' | ') FROM poem p JOIN author a ON a.id = p.author_id"
    " WHERE p.source='补录' GROUP BY p.author_id HAVING f > 0"
    " ORDER BY f DESC, a.poem_count ASC").fetchall()
for r in rows[:6]:
    print('%-6s 总=%-5s 补录=%-3s 填=%-3s %s' % (r[0], r[1], r[2], r[3], (r[4] or '')[:56]))
print()
for t in ('山坡羊·潼关怀古', '天净沙·秋思', '观书有感二首·其一', '饮酒·其五', '春宵',
          '沁园春·长沙', '茅檐', '泛舟'):
    r = c.execute("SELECT substr(body,1,12), length(trans), length(note), length(intro)"
                  " FROM poem WHERE source='补录' AND title_s=?", (t,)).fetchone()
    print('%-14s %s' % (t, r))
print('\n补录 totals: trans=%d note=%d intro=%d of %d' % (
    c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
              " AND trans IS NOT NULL AND trans!=''").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
              " AND note IS NOT NULL AND note!=''").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
              " AND intro IS NOT NULL AND intro!=''").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'").fetchone()[0]))