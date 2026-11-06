"""Find which famous poems the app lacks, then recover them verbatim from the checkout.

Probing is verse-based, not title-based: the corpus keeps anthology prefixes inside the
title (鹿柴 is stored as 辋川集 鹿柴), so a title probe reports false gaps. Each probe is
a line that can only have come from one poem.

Anything the local chinese-poetry checkout has is copied out unchanged into corpus.json.
What is printed as NEED_SOURCE is what that dataset genuinely does not cover (汉乐府,
古诗十九首, 北朝乐府, 陶渊明, 曹植, 清诗 ...) and must come from another source.
"""
import glob
import json
import os
import sqlite3
import sys

ROOT = '/root/poetry'
DB = f'{ROOT}/out/poetry_lite.db'
OUT = f'{ROOT}/supplement/corpus.json'

# (probe verse, cited title, dynasty, author)
PROBES = [
    ('江南可采莲', '江南', '汉', '佚名'),
    ('上邪', '上邪', '汉', '佚名'),
    ('青青园中葵', '长歌行', '汉', '佚名'),
    ('日出东南隅', '陌上桑', '汉', '佚名'),
    ('孔雀东南飞', '孔雀东南飞', '汉', '佚名'),
    ('十五从军征', '十五从军征', '汉', '佚名'),
    ('涉江采芙蓉', '涉江采芙蓉', '汉', '佚名'),
    ('行行重行行', '行行重行行', '汉', '佚名'),
    ('青青河畔草', '青青河畔草', '汉', '佚名'),
    ('迢迢牵牛星', '迢迢牵牛星', '汉', '佚名'),
    ('明月何皎皎', '明月何皎皎', '汉', '佚名'),
    ('客从远方来', '客从远方来', '汉', '佚名'),
    ('生年不满百', '生年不满百', '汉', '佚名'),
    ('驱车上东门', '驱车上东门', '汉', '佚名'),
    ('庭中有奇树', '庭中有奇树', '汉', '佚名'),
    ('回车驾言迈', '回车驾言迈', '汉', '佚名'),
    ('今日良宴会', '今日良宴会', '汉', '佚名'),
    ('西北有高楼', '西北有高楼', '汉', '佚名'),
    ('敕勒川', '敕勒歌', '南北朝', '佚名'),
    ('唧唧复唧唧', '木兰诗', '南北朝', '佚名'),
    ('少无适俗韵', '归园田居', '魏晋', '陶渊明'),
    ('种豆南山下', '归园田居', '魏晋', '陶渊明'),
    ('结庐在人境', '饮酒', '魏晋', '陶渊明'),
    ('归去来兮', '归去来兮辞', '魏晋', '陶渊明'),
    ('荆轲饮燕市', '咏荆轲', '魏晋', '陶渊明'),
    ('对酒当歌', '短歌行', '魏晋', '曹操'),
    ('东临碣石', '观沧海', '魏晋', '曹操'),
    ('神龟虽寿', '龟虽寿', '魏晋', '曹操'),
    ('白骨露于野', '蒿里行', '魏晋', '曹操'),
    ('煮豆持作羹', '七步诗', '魏晋', '曹植'),
    ('白马饰金羁', '白马篇', '魏晋', '曹植'),
    ('高树多悲风', '野田为行', '魏晋', '曹植'),
    ('明月照高楼', '七哀诗', '魏晋', '曹植'),
    ('弱冠弄柔翰', '咏史', '魏晋', '左思'),
    ('夜中不能寐', '咏怀', '魏晋', '阮籍'),
    ('蝉噪林逾静', '入若耶溪', '南北朝', '王籍'),
    ('风萧萧兮易水寒', '易水歌', '先秦', '荆轲'),
    ('力拔山兮气盖世', '垓下歌', '先秦', '项羽'),
    ('大风起兮云飞扬', '大风歌', '汉', '刘邦'),
    ('帝子降兮北渚', '九歌', '先秦', '屈原'),
    ('操吴戈兮被犀甲', '九歌', '先秦', '屈原'),
    ('悲哉秋之为气也', '九辩', '先秦', '宋玉'),
    ('蒹葭苍苍', '蒹葭', '先秦', '佚名'),
    ('桃之夭夭', '桃夭', '先秦', '佚名'),
    ('王于兴师', '无衣', '先秦', '佚名'),
    ('七月流火', '七月', '先秦', '佚名'),
    ('式微式微', '式微', '先秦', '佚名'),
    ('昔我往矣', '采薇', '先秦', '佚名'),
    ('关关雎鸠', '关雎', '先秦', '佚名'),
    ('锄禾日当午', '悯农', '唐', '李绅'),
    ('春种一粒粟', '悯农', '唐', '李绅'),
    ('劝君更尽一杯酒', '送元二使安西', '唐', '王维'),
    ('日照香炉生紫烟', '望庐山瀑布', '唐', '李白'),
    ('小时不识月', '古朗月行', '唐', '李白'),
    ('鹅鹅鹅', '咏鹅', '唐', '骆宾王'),
    ('此地别燕丹', '于易水送人', '唐', '骆宾王'),
    ('春江潮水连海平', '春江花月夜', '唐', '张若虚'),
    ('年年岁岁花相似', '代悲白头翁', '唐', '刘希夷'),
    ('近乡情更怯', '渡汉江', '唐', '宋之问'),
    ('前不见古人', '登幽州台歌', '唐', '陈子昂'),
    ('落霞与孤鹜齐飞', '滕王阁诗', '唐', '王勃'),
    ('有花堪折直须折', '金缕衣', '唐', '杜秋娘'),
    ('空山不见人', '鹿柴', '唐', '王维'),
    ('红豆生南国', '相思', '唐', '王维'),
    ('独在异乡为异客', '九月九日忆山东兄弟', '唐', '王维'),
    ('秦时明月汉时关', '出塞', '唐', '王昌龄'),
    ('黄沙百战穿金甲', '从军行', '唐', '王昌龄'),
    ('黄河远上白云间', '凉州词', '唐', '王之涣'),
    ('少小离家老大回', '回乡偶书', '唐', '贺知章'),
    ('碧玉妆成一树高', '咏柳', '唐', '贺知章'),
    ('慈母手中线', '游子吟', '唐', '孟郊'),
    ('远上寒山石径斜', '山行', '唐', '杜牧'),
    ('清明时节雨纷纷', '清明', '唐', '杜牧'),
    ('千里莺啼绿映红', '江南春', '唐', '杜牧'),
    ('天阶夜色凉如水', '秋夕', '唐', '杜牧'),
    ('京口瓜洲一水间', '泊船瓜洲', '宋', '王安石'),
    ('爆竹声中一岁除', '元日', '宋', '王安石'),
    ('墙角数枝梅', '梅花', '宋', '王安石'),
    ('飞来山上千寻塔', '登飞来峰', '宋', '王安石'),
    ('茅檐长扫净无苔', '书湖阴先生壁', '宋', '王安石'),
    ('江上往来人', '江上渔者', '宋', '范仲淹'),
    ('生当作人杰', '夏日绝句', '宋', '李清照'),
    ('横看成岭侧成峰', '题西林壁', '宋', '苏轼'),
    ('水光潋滟晴方好', '饮湖上初晴后雨', '宋', '苏轼'),
    ('竹外桃花三两枝', '惠崇春江晚景', '宋', '苏轼'),
    ('春宵一刻值千金', '春夜', '宋', '苏轼'),
    ('荷尽已无擎雨盖', '赠刘景文', '宋', '苏轼'),
    ('应似飞鸿踏雪泥', '和子由渑池怀旧', '宋', '苏轼'),
    ('春色满园关不住', '游园不值', '宋', '叶绍翁'),
    ('知有儿童挑促织', '夜书所见', '宋', '叶绍翁'),
    ('绿遍山原白满川', '乡村四月', '宋', '翁卷'),
    ('等闲识得东风面', '春日', '宋', '朱熹'),
    ('半亩方塘一鉴开', '观书有感', '宋', '朱熹'),
    ('死去元知万事空', '示儿', '宋', '陆游'),
    ('三万里河东入海', '秋夜将晓出篱门迎凉有感', '宋', '陆游'),
    ('僵卧孤村不自哀', '十一月四日风雨大作', '宋', '陆游'),
    ('莫笑农家腊酒浑', '游山西村', '宋', '陆游'),
    ('古人学问无遗力', '冬夜读书示子聿', '宋', '陆游'),
    ('泉眼无声惜细流', '小池', '宋', '杨万里'),
    ('毕竟西湖六月中', '晓出净慈寺送林子方', '宋', '杨万里'),
    ('篱落疏疏一径深', '宿新市徐公店', '宋', '杨万里'),
    ('夜热依然午热同', '夏夜追凉', '宋', '杨万里'),
    ('梅子金黄杏子肥', '四时田园杂兴', '宋', '范成大'),
    ('昼出耘田夜绩麻', '四时田园杂兴', '宋', '范成大'),
    ('草满池塘水满陂', '村晚', '宋', '雷震'),
    ('梅子黄时日日晴', '三衢道中', '宋', '曾几'),
    ('岐王宅里寻常见', '江南逢李龟年', '唐', '杜甫'),
    ('枯藤老树昏鸦', '天净沙', '元', '马致远'),
    ('峰峦如聚', '山坡羊', '元', '张养浩'),
    ('孤村落日残霞', '天净沙', '元', '白朴'),
    ('不要人夸好颜色', '墨梅', '元', '王冕'),
    ('咬定青山不放松', '竹石', '清', '郑燮'),
    ('白日不到处', '苔', '清', '袁枚'),
    ('牧童骑黄牛', '所见', '清', '袁枚'),
    ('我劝天公重抖擞', '己亥杂诗', '清', '龚自珍'),
    ('千锤万凿出深山', '石灰吟', '明', '于谦'),
]

FILES = (sorted(glob.glob(f'{ROOT}/repo/全唐诗/poet.tang.*.json'))
         + sorted(glob.glob(f'{ROOT}/repo/全唐诗/poet.song.*.json'))
         + sorted(glob.glob(f'{ROOT}/repo/宋词/ci.song.*.json'))
         + sorted(glob.glob(f'{ROOT}/repo/五代诗词/huajianji/*.json'))
         + [f'{ROOT}/repo/五代诗词/nantang/poetrys.json',
            f'{ROOT}/repo/诗经/shijing.json', f'{ROOT}/repo/楚辞/chuci.json',
            f'{ROOT}/repo/曹操诗集/caocao.json', f'{ROOT}/repo/元曲/yuanqu.json',
            f'{ROOT}/repo/纳兰性德/纳兰性德诗集.json'])


def main():
    c = sqlite3.connect(DB).cursor()
    m = {t: s for t, s in c.execute('SELECT t,s FROM t2s_map')}
    t2s = lambda x: ''.join(m.get(ch, ch) for ch in (x or ''))

    def in_db(verse):
        v = t2s(verse)
        return c.execute('SELECT 1 FROM line WHERE text LIKE ? LIMIT 1',
                         ('%' + v[:6] + '%',)).fetchone() is not None

    corpus = []
    for f in FILES:
        if not os.path.exists(f):
            continue
        try:
            data = json.load(open(f, encoding='utf8'))
        except Exception:
            continue
        if isinstance(data, list):
            corpus.append((os.path.basename(f), data))

    def locate(verse, author):
        v = t2s(verse)
        want = t2s(author) if author and author != '佚名' else None
        for fname, data in corpus:
            for p in data:
                if not isinstance(p, dict):
                    continue
                paras = [x for x in (p.get('paragraphs') or p.get('content')
                                     or p.get('para') or []) if isinstance(x, str)]
                if v[:6] not in t2s(''.join(paras)):
                    continue
                a = t2s(p.get('author') or '')
                if want and a and a != want:
                    continue
                return p, paras, fname
        return None, None, None

    found, need, present = {}, [], 0
    for verse, title, dyn, author in PROBES:
        key = (t2s(title), t2s(author))
        if key in found:
            continue
        if in_db(verse):
            present += 1
            continue
        p, paras, fname = locate(verse, author)
        if p is None:
            need.append((title, author, dyn, verse))
            continue
        ci = 'ci.song' in fname or 'huajianji' in fname or 'nantang' in fname
        found[key] = {
            'author': t2s(p.get('author') or author),
            'dynasty': dyn,
            'title': t2s(p.get('title') or p.get('rhythmic') or title),
            'title_cite': t2s(title),
            'source': '补录',
            'form': '词' if ci else '诗',
            'rhythmic': t2s(p['rhythmic']) if p.get('rhythmic') else None,
            'paras': [t2s(x) for x in paras],
        }
    json.dump(list(found.values()), open(OUT, 'w', encoding='utf8'),
              ensure_ascii=False, indent=1)
    print('probes %d | already in db %d | recoverable %d | NEED_SOURCE %d'
          % (len(PROBES), present, len(found), len(need)))
    for t, a, d, v in need:
        print('   NEED %s / %s / %s  [%s]' % (t, a, d, v[:10]))


if __name__ == '__main__':
    sys.exit(main())