"""Assertions that lock the two mis-pairings found by audit_anno.py.

Run against a scratch copy of the DB:
    rm -f /tmp/anno_t.db && cp out/poetry_lite.db /tmp/anno_t.db
    sed 's|^DB = .*|DB = "/tmp/anno_t.db"|' supplement/apply_anno.py > /tmp/aa.py
    python3 /tmp/aa.py --apply && python3 supplement/test_anno.py /tmp/anno_t.db
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import sqlite3
import sys

sys.path.insert(0, f'{_ROOT}/supplement')
from apply_anno import norm, similar  # noqa: E402

QIXI_YANGPU = '未会牵牛意若何，须邀织女弄金梭。年年乞与人间巧，不道人间巧已多。'
QIXI_LIHE = '别浦今朝暗，罗帷午夜愁。鹊辞穿线月，花入曝衣楼。'
LUXIAN_ONE = '风卷江湖雨暗村，四山声作海涛翻，溪柴火软蛮毡暖，我与狸奴不出门'
LUXIAN_MERGED = ('风卷江湖雨暗村，四山声作海涛翻。溪柴火软蛮毡暖，我与狸奴不出门。'
                 '僵卧孤村不自哀，尚思为国戍轮台。夜阑卧听风吹雨，铁马冰河入梦来。')
CHUNXIAO = '春宵一刻值千金，花有清香月有阴。歌管楼台声细细，秋千院落夜沈沈。'

fails = []


def check(name, cond):
    print('%s %s' % ('ok  ' if cond else 'FAIL', name))
    if not cond:
        fails.append(name)


check('gate rejects 其一 annotation vs merged 二首 edition',
      not similar(norm(LUXIAN_ONE), norm(LUXIAN_MERGED)))
check('gate rejects 李贺《七夕》 annotation for 杨朴《七夕》',
      not similar(norm(QIXI_LIHE), norm(QIXI_YANGPU)))
check('gate still accepts an identical text (title-variant tier)',
      similar(norm(CHUNXIAO), norm(CHUNXIAO)))

if len(sys.argv) > 1:
    c = sqlite3.connect(sys.argv[1]).cursor()

    def field(title, author, col):
        r = c.execute('SELECT p.%s FROM poem p JOIN author a ON a.id=p.author_id'
                      ' WHERE p.title_s=? AND a.name_s=?' % col, (title, author)).fetchone()
        return (r[0] or '') if r else ''

    check('杨朴《七夕》没有被贴上李贺的译文', '罗帷' not in field('七夕', '杨朴', 'trans'))
    # First written when the merged row had no 译文 at all, so it could only say "don't
    # paste the single-poem one". The site now serves a two-poem 译文 for it, so the
    # assertion can state the real requirement in both directions.
    merged = field('十一月四日风雨大作二首', '陆游', 'trans')
    check('合并本《十一月四日风雨大作二首》译文覆盖两首（第一首的猫 + 第二首的战马都在）',
          '猫' in merged and '战马' in merged)
    check('单首《…二首 其二》未被贴上合并本译文（不含第一首的猫）',
          '猫' not in field('十一月四日风雨大作二首 其二', '陆游', 'trans'))
    check('苏轼《春宵》仍然补上了译文（门控没有误杀）', bool(field('春宵', '苏轼', 'trans')))
    filled = c.execute("SELECT COUNT(*) FROM poem WHERE source='补录'"
                       " AND trans IS NOT NULL AND trans!=''").fetchone()[0]
    check('补录 译文 覆盖率过半（实际 %d/163）' % filled, filled > 81)
    other = c.execute("SELECT COUNT(*) FROM poem WHERE source!='补录'"
                      " AND trans IS NOT NULL AND trans!=''").fetchone()[0]
    check('未波及其它 source（译文仍为 2715，实际 %d）' % other, other == 2715)

print('FAILED: %s' % fails if fails else 'ALL PASS')
sys.exit(1 if fails else 0)