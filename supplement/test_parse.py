"""Parser + candidate-selection tests for the 古诗文网 source (no network).

fixtures/xiangcun_siyue.html is a real www.gushiwen.cn detail page saved during this
project, so parse_desktop is exercised against production markup rather than a mock. The
site's own search page needs a login, so candidate lookup goes through the category index
(build_cat_index.py) instead; the interesting case there is that many of our missing rows
share a title with a DIFFERENT poem, and only the body comparison keeps them apart.
"""
_ROOT = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
if __import__('os').path.basename(_ROOT) == 'supplement':
    _ROOT = __import__('os').path.dirname(_ROOT)
import json
import sys

sys.path.insert(0, f'{_ROOT}/supplement')
from crawl_gushiwen import candidates, parse_desktop  # noqa: E402

FIX = f'{_ROOT}/supplement/fixtures/xiangcun_siyue.html'
INDEX = f'{_ROOT}/supplement/cat_index.json'

fails = []


def check(name, cond, extra=''):
    print('%s %s%s' % ('ok  ' if cond else 'FAIL', name, (' | ' + extra) if extra else ''))
    if not cond:
        fails.append(name)


f = parse_desktop(open(FIX, encoding='utf8', errors='ignore').read())
check('body parsed', f['body'].startswith('绿遍山原白满川'), f['body'][:20])
check('trans parsed', f['trans'].startswith('初夏季节'), 'len=%d' % len(f['trans']))
check('no 注释 label leaked into trans', '注释' not in f['trans'])
check('note parsed, one term per line',
      f['note'].startswith('山原') and '\n' in f['note'] and '川：河流' in f['note'],
      repr(f['note'][:34]))
check('intro (简析) parsed', '七言绝句' in f['intro'], 'len=%d' % len(f['intro']))
check('no HTML left in any field',
      all('<' not in f[k] for k in ('body', 'trans', 'note', 'intro')))

# The XHR that serves the 译文/注释 the desktop page withholds behind a login click.
# Its fields are colour-coded rather than labelled, so the assertions below are about the
# colour split holding: green -> trans, gold-with-a-colon -> note, plain -> body.
from crawl_gushiwen import ajax_idjm, parse_ajax  # noqa: E402

ax = parse_ajax(open(f'{_ROOT}/supplement/fixtures/ajax_yizhu.txt',
                     encoding='utf8', errors='ignore').read())
check('ajax body is verse only (no 译文 mixed in)',
      ax['body'].startswith('自河南经乱') and len(ax['body']) < 200
      and '战乱灾荒' not in ax['body'], 'len=%d' % len(ax['body']))
check('ajax trans is the green per-line gloss',
      ax['trans'].startswith('自从河南') and '战乱灾荒祖先产业荡然空' in ax['trans'],
      'len=%d' % len(ax['trans']))
check('ajax note keeps glosses', '河南：唐时河南道' in ax['note'], 'len=%d' % len(ax['note']))
check('ajax note drops pinyin-only runs', '(jī)' not in ax['note'])
check('ajax trans line count matches verse line count',
      len(ax['trans'].split('\n')) == len(ax['body'].split('\n')),
      'trans=%d body=%d' % (len(ax['trans'].split('\n')), len(ax['body'].split('\n'))))
check('ajax_idjm reads the key off the real page',
      ajax_idjm(open(FIX, encoding='utf8', errors='ignore').read(),
                'zzzzzzzzzzzz') == '07f5e3403665')
check('ajax_idjm falls back to cid when no handler', ajax_idjm('<html/>', 'ab12cd34ef56') == 'ab12cd34ef56')

# The anonymous search-suggest endpoint (gushiwen_so), fixture: q=田家.
from gushiwen_so import queries as so_queries, so_rows  # noqa: E402

so = so_rows(open(f'{_ROOT}/supplement/fixtures/so_tianjia.html',
                  encoding='utf8', errors='ignore').read())
check('so rows carry id + title + author',
      so[0] == ('343a059d32c7', '田家元日', '孟浩然') and len(so) == 3, repr(so[:1]))
check('so rows skip 名句 links (they point at /mingju/, not a poem)',
      all(cid != 'juv_f994dcce56d6' for cid, _, _ in so), 'n=%d' % len(so))
check('so queries try a title stem the site can prefix-match',
      '观书有感' in so_queries('观书有感二首·其一', ''), repr(so_queries('观书有感二首·其一', '')))
check('so queries keep the bare title first', so_queries('小池', '')[0] == '小池')

idx = json.load(open(INDEX, encoding='utf8'))
check('category index loaded', len(idx) > 5000, 'titles=%d' % len(idx))

# 七夕 is a title collision: our row is 杨朴's, the anthology lists 白居易's.
c = candidates('七夕', '杨朴', idx)
check('collision title still yields candidates', len(c) >= 1, 'n=%d' % len(c))
if c:
    # Contract is "same author first", not a total order: the other hands all tie at the
    # same rank and stay in index order. Ordering only saves fetches -- correctness comes
    # from the body gate in main(), which is why 杨朴 must lead.
    check('our own author is tried before the colliding ones',
          c[0][2] == '杨朴' and [x[2] for x in c].index('白居易') > 0,
          str([x[2] for x in c][:4]))
same = candidates('竹石', '郑燮', idx)
check('same-author candidate ranked first',
      bool(same) and same[0][2] in ('郑燮', '郑板桥'), str(same[:1]))
# 洪适 拟古十三首: the listing only has the 古诗十九首 originals under the short title.
hong = candidates('拟古十三首 行行重行行', '洪适', idx)
check('series-prefix title resolves via the short form', len(hong) >= 1, 'n=%d' % len(hong))
if hong:
    check('...and that candidate is NOT attributed to 洪适 (body gate must reject it)',
          hong[0][2] != '洪适', 'author=%s' % hong[0][2])
check('unknown title yields nothing', candidates('完全没有这首诗的题目某某', '某某', idx) == [])

print('\ntrans head:', f['trans'].replace('\n', '/')[:52])
print('note       :', f['note'].replace('\n', '/')[:52])
print('FAILED: %s' % fails if fails else 'ALL PASS')
sys.exit(1 if fails else 0)