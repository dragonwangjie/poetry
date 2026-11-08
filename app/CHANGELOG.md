# v1.7 (versionCode 8)

检索排序：并列命中改由「作者存世作品数」定序（PoemDb.Row.fame，LINE_SELECT 里
LEFT JOIN author 取 poem_count）。全唐诗把《登鹳雀楼》双署朱斌《登楼》与王之涣
《登鹳雀楼》，四句完全相同，旧排序退化为 line id 序，朱斌 id 小故胜出；现在王之涣
(7 首) 压过朱斌 (1 首)。adjacentHits 同步：对句按联文本收进 map，保留名气高的副本，
末尾统一按 fame 排序。verify_search.py 已同步同一套 tie-break，20/20 通过。

# v1.6 (versionCode 7)

补录 163 首（79 668 -> 79 831 首，845 122 -> 846 471 分句，5 151 -> 5 185 位诗人）。
数据全部来自 chinese-poetry / huajianji 官方 JSON：教科书必背、古诗十九首、唐诗三百首、
宋词三百首、千家诗、蒙学。流程 supplement/collect.py -> curate.py -> merge2.py ->
apply.py（幂等：先删 source=补录 行，密集重编号 line id，再全量重建
char_index / char_pos / pos_stats，约 12s）。

数据清洗规则（apply.py）：
- NOTE 在「版本二」「一作」处截断：七步诗带第二版本、竹石尾随「坚劲一作韧」。
- garbled() 剔除含康熙部首碎片的分句（扫描件把「亻赞」拆成两个部首）。
- PROSE 排除词话/诗话（人间词话七则 是评论不是词）。
- MAX_CLAUSES=140 排除套数（中吕・山坡羊 207 分句，OCR 已坏）。
- DYN 归一「宋代->宋」，FIX 纠正 敕勒歌->南北朝·佚名、七步诗->魏晋·曹植。
- 佚名 按朝代拆行；否则古诗十九首 23 首会落进“先秦”筛选桶。

朝代筛选栏加了 魏晋 / 南北朝 / 明（MainActivity.DYNASTIES），新补的 4/3/5 首原本无处可筛。

# 构建坑（已修）

build.sh 原先只看 mtime 决定是否重压 poetry_lite.db.gz。一次 gzip 被超时无断打断，
留下 42 MB 残档且比 db 更新，于是残缺库被打进 APK（包 42 MB / 应为 67 MB）。现在改为
解压后字节数比对 + gzip -t，不匹配就重压并 exit 1。同理：adb install 前必须把 APK
复制到 /sdcard（proot 的 /root 路径 adb 读不到）。

# 验证入口

- 一条命令：bash supplement/verify.sh  ->  test_parse + test_anno + test_title_search
  （离线，库从最终 APK 内解出）+ adb install + 7 项设备端渲染文本断言 -> verify: ALL GREEN
  只跑离线部分：SKIP_DEVICE=1 bash supplement/verify.sh
- 设备断言单独跑：bash supplement/test_ui_device.sh（要求屏幕能亮；读不到界面一律 SKIP
  并返回非 0，SKIP 不算通过）
- 检索回归：python3 out/verify_search.py out/poetry_lite.db  ->  pass 20 / 20
- 索引一致性：随机抽 char，比对 char_index 解出的 line id 与 LIKE 直查结果（6/6 相等）
- 装机：cp app/build/poetry.apk /sdcard/Download/ && adb install -r /sdcard/Download/poetry.apk
- 首启会解压 129 MB 库，约 100s；解压期间首页 toast「书库尚在解压，请稍候」

# v1.8 (versionCode 9, DB_VERSION 8)

体裁误分类修正。原先按「标题含 ·」判词，把组诗当成了词：陶渊明《归园田居·其三》在
诗页显示「词牌「归园田居」」，屏幕上真实出现过（uiautomator 抓到 陶渊明 · 补录 · 词牌「归园田居」）。
现改为查语料自带的词牌表（SELECT DISTINCT rhythmic FROM poem WHERE form=词，1462 个）
判定，标题里的 · 只代表副标题。补录 163 首的最终体裁：曲 5 / 词 12 / 诗 146。

- 新增曲牌表（天净沙/山坡羊/寿阳曲/朝天子 等 14 个），5 首元明小令由「词」改「曲」。
- alias 映射只用于判形，rhythmic 保留标题原写法：鹊踏枝·叵耐灵鹊多谩语 -> 词牌「鹊踏枝」
  （不写成别名 蝶恋花）。
- PoemActivity.addMeta 按 form 输出 词牌/曲牌，曲不再被叫作词牌。

验证边界：数据侧已核对（曲5/词12/诗146，integrity ok，APK 内嵌库同样正确），
fame tie-break 与朝代筛选此前已在真机截图确认。v1.8 的 词牌/曲牌 文字尚未截到屏幕：
该模拟器 mCurrentFocus 长期停在 NotificationShade，省电策略把 app 甩后台（SmartPower
adj=700），uiautomator dump 8 次只抓到 systemui/home；PoemActivity 未 exported 故无法
深链；adb input text 不支持中文。要在屏上确认，需手动打开《天净沙·秋思》与《归园田居·其三》。

# v1.9 (versionCode 10, DB_VERSION 9)

收窄 fame tie-break：只有两首诗正文完全相同（同一首诗被双重署名）时，才用作者存世
作品数定序。上一版无条件比较 fame，会让杜甫(1491 首)的任何同句副本压过小诗人的原作。

实现：poem.sig = md5(整首正文去标点)。sig 只与同列取值互相比较，app 端从不重算，所以
两侧无需同一套归一化，也无需索引（按 sig 索引白花 11 MB 包体，已 DROP INDEX + VACUUM）。
PoemDb 新增 sameText(...)；searchVerses 的去重改为 LinkedHashMap 保序，重复行仅当
sameText 且 fame 更高才替换保留项；adjacentHits 同理，并恢复「首个有命中的切点即止」。
DB 129.0 -> 131.9 MB（指纹本体），APK 69.8 MB。

验证（verify_search.py 已同步门控）：
- 双署仍归名篇：白日依山尽 / 欲穷千里目更上一层楼 -> 《登鹳雀楼》王之涣(7首)，
  非 朱斌《登楼》(1首)；原 20 条用例 20/20。
- 跨首共享行不再被 fame 抢位：寿丘惟旧迹 / 悬弧亦在兹 -> 《幸武功庆善宫》太宗皇帝(101首)，
  而不是 舞曲歌辞 功成庆善乐舞词（不详，885首）。两条候选 sig 分别 4b94a6d2 / f18ca1fe，
  证明门控确实生效而非碰巧同类。
- 全库符合「共享同一整行、整首却不同、且对方产量高 3 倍以上」的组合共 3745 条，均受此保护。

数据侧写入点：build_db.py（全量重建）与 supplement/apply.py（补录）都写 sig，
存量库用 supplement/add_sig.py 原地补列 + VACUUM。

补测（同版本）：
- 回归用例 20 -> 22 条，新增两条门控守卫：寿丘惟旧迹 / 悬弧亦在兹 必须归《幸武功庆善宫》
  太宗皇帝(101首)，而不是同句的 舞曲歌辞 功成庆善乐舞词（不详，885首）。当前 22/22。
- 变异测试验得上这条用例真的在守：把门控改回无条件比 fame（verify_search.py 第 142 行
  改成 `if old is None or r[4] > old[4]`）后，恰好这 2 条转 BAD（pass 20 / 22）。
- supplement/check_sig.py：校验两条写入路径（apply.py 写补录、add_sig.py 全表重算）的
  sig 一致 —— 补录 163 行 + 全唐诗 400 行 全部与重算值相符，空值 0，双署组 416 组，
  库与 APK 内嵌库均通过（exit 0）。
- dex 侧核对：classes.dex 里的 LINE_SELECT / fillPoem 已含 IFNULL(p.sig,'')，LinkedHashMap
  已在常量池中；类数 74 -> 73 是删掉了 adjacentHits 末尾那个按 fame 排序的匿名 Comparator
  （排序已不需要，保序由 LinkedHashMap 承担）。

设备端已验（v1.9 装机后，uiautomator 抓屏，卡片文本逐条读出）：
- 欲穷千里目更上一层楼 -> 「欲穷千里目 / 更上一层楼」《登鹳雀楼》王之涣 · 相邻两句（对句分支）
- 白日依山尽 -> 《登鹳雀楼》王之涣（同文双署，fame 生效，未落到朱斌《登楼》）
- 床前明月光（chip）-> 卡片显示「床前看月光」《静夜思》李白 · 近似（原文或有异文）；
  本库正文作「床前看月光」（早期文本异文，通行本为「明」），故输入通行本首句走近似匹配分支
  （chip 已复原为原文案）
- 寿丘惟旧迹 -> 《幸武功庆善宫》太宗皇帝（共享行而整首不同，fame 被门控挡住，
  未落到同句的 舞曲歌辞 功成庆善乐舞词/不详 885 首）—— 这条与上一条例句是本次改动的靶子。
验证手法（此前失败的真正原因）：设备长期处于 Dozing/MIUI AOD，且宿主 Operit 会在两次 adb
之间抢回前台，故 dump 全空。可用配方见 /root/probe.sh —— 常亮（dumpsys battery set ac 1 +
svc power stayon true）+ 关 AOD + 整条点击链在一个脚本里连续跑，别用 KEYCODE_HOME。
为点出对抗用例，临时把 VerseActivity.SUGGEST 首条换成「寿丘惟旧迹」出了个探针包（只改文案，
manifest 未动），验证完已改回原文案、重建并把 poetry-v10.apk 覆盖回正式产物、重装 Success。
adb input text 不支持中文、ADBKeyboard 被 MIUI 拒装（INSTALL_FAILED_USER_RESTRICTED）、
VerseActivity 未导出（intent 传 query 被 SecurityException 拦，未为此放宽 exported）。

## v1.10 (versionCode 11, DB_VERSION 10) — 补录释文

问题：精选补录的 163 首（source='补录'）译文/简介全空，注释只有 31 条。
成因：apply.py 是删行重插，跑在 add_translation2.py 之后，把这些行的
trans/note/intro 一起擦掉了；add_translation2.py 之后再没重跑过。

做法：新增 supplement/apply_anno.py —— 只碰 source='补录'、只填空字段
（UPDATE ... = COALESCE(NULLIF(col,''), ?)），不重跑 add_translation2.py
（它会重写全表匹配到的 trans，会把别处手写的译文清掉）。
匹配沿用 add_translation2.py 的层级：正文归一化 > 题名+作者 > 去「其一」题名+作者
> 首十字+作者 > 题名唯一。注释语料 /root/anno/anno.ndjson（11476 条带 payload，
字段名是小写 trans/note/intro，不是 Translation）。

结果：译文 0 -> 95，注释 31 -> 112，简介 0 -> 98（共 163）。其它 source 一条没动
（全库 trans 仍 2715，其中本次新增在补录内）。库 132MB -> gz 70,074,316。

坑与门控（supplement/audit_anno.py 抓出来的两处错配）：
1. 题名相同、诗不同：《七夕》杨朴 会被贴李贺《七夕》的译文；
2. 版本不等长：陆游《十一月四日风雨大作二首》（本库是二首合并的八行本）
   会被贴「其一」单首的译文。
修法：similar() 门控只对弱档生效（正文档天然同文，不需门）—— 长度比 < 0.6 直接拒，
再看前八字包含或二元组 overlap >= 0.6。上目前弱档命中 title-only 32 -> 2、
title-stripped 10 -> 0（宁缺勿错）。
supplement/test_anno.py 8 条断言锁住这两个错配 + 不误杀 + 不波及其它 source：ALL PASS。

设备侧（v1.10 已装，versionName=1.10）：查诗句「峰峦如聚」-> 《山坡羊·潼关怀古》张养浩，
点入诗词页顶栏显示「张养浩 · 补录 · 曲牌「山坡羊」」—— 补录条目可正常到达。
释文卡片本身没能在屏上读到：PoemActivity 的正文/释文是自绘 View（dump 只有 3 个
TextView + 13 个 android.view.View），uiautomator 取不到文本；无 tesseract，
且 root executor 不可用、app 非 debuggable，screencap 拉不出来。改用 APK 内嵌库取证：
unzip assets/poetry.db.gz 解出 e.db，补录 trans/note/intro = 95/112/98，
潼关怀古 (116,543,230) 字，sig 空值 0，integrity ok；addCard() 对空串直接 return，
所以未补上的条目不会留空卡片。
验证用的 chip 换字（SUGGEST 首条改「峰峦如聚」）已改回原文案并重建，探针 APK 已删；
重建产物与探针前的正式包只差 zip 时间戳（byte 69830544 后），APK 内 '峰峦如聚' 0 处。
检索回归仍 22/22。设备设置已复原（battery reset、常亮关、息屏 60s、AOD 开、输入法讯飞）。

仍剩：163 条里 68 条无译文、46 条三字段全空（古诗十九首一部分、毛泽东 2 首、
程颢/王淇/朱熹部分等），语料里没这些篇目的译注，需手写或另找源。
列表见 /tmp/miss61.txt 与 supplement/probe_filled.py。

## v1.11 (versionCode 12, DB_VERSION 11) — 补录释文第二批：新增古诗文网语料

用户要求：先扩大译注语料源，再跑一轮自动匹配。

本地已无未开发语料（supplement/scan_all_sources.py 扫 /root/anno + poetry/raw + sample）：
works.npy 842,966 行里带释文的正好是 anno.ndjson 那 11,476 条，同一批数据两种封装。
另更正上一轮一处判断：supplement/why_rejected.py 逐条核对显示，门控当时放行的 8 条
正文 overlap 0.93-1.00 全是真匹配（《竹石》郑燮 vs 郑板桥 是同人异名，正确放行），
被拒的 11 条全是真冲突题名（落花/朱淑贞 vs 李商隐、七夕/杨朴 vs 李贺、清明/黄庭坚 vs 杜牧
等）。这 8 条之所以仍无译文，是语料侧本来只有注释/赏析没有译文 —— 不是门槛过严，
门控参数不动。

取新料的约束（逐条实测，别再重试）：api.github.com 本机出口 IP 已限流（search 直接 403，
core 60/时）；raw.githubusercontent.com 不通（http=000）；codeload.github.com 通但 ~35KB/s，
90s 只落 3MB；jsDelivr 单包限 50MB，找到的候选仓库（shenyunhang/gushiwen-crawler-data、
VMIJUNV/chinese-poetry-and-prose）都超限；huggingface/statically 不通。
可用的是站点本身：www.gushiwen.cn 直连 http=200、约 120KB/s。

站点侧的坑：检索页要登录（search.aspx 302 到 /user/login.aspx；so. 子域同样；
m 站跳 APP 下载页），作者页正文走 XHR（0 个 shiwenv id）。免登录可枚举的只有分类/选本页
（gushi/tangshi.aspx 等 69 个，从页面内链现取，不猜 URL），抓到 9,659 个 shiwenv id、
9,325 个题名 -> supplement/cat_index.json。详情页桌面版直出 译文/注释/简析；
另有一部分（望月有感、新秋、观公孙大娘弟子舞剑器行…）译文在 OnYiwenDetail 的 XHR 后、
需 gsw2017user cookie，拿不到。赏析被服务端截尾，所以简介用「简析」。

新增 supplement/build_cat_index.py（分类页 -> 题名索引）与 supplement/crawl_gushiwen.py
（按行找候选 -> 抓详情 -> 解析 -> 正文比对门控 -> gushiwen.ndjson）。
候选排序只求少发请求（同作者优先），正确性仍由 similar() 正文门控负责：
46 条目标里 25 条能在分类页命中，其中一半是同名异诗（闻笛 赵嘏 vs 张巡、七夕 杨朴 vs 白居易、
秋月 程颢 vs 朱熹、田家 范成大 vs 郑獬、新竹 陆游 vs 郑板桥、中秋 李朴 vs 司空图、
洪适拟古十三首 vs 古诗十九首原作），门控把它们全部挡下 —— 实测 gushiwen.ndjson 里洪适 0 条、
而佚名原作自己拿到了注。
apply_anno.py 改动：可收多语料参数，带 poem_id 的记录走直连档（direct）不再按题名重匹配。

结果：补录 译文 95 -> 117，注释 112 -> 120，简介 114（共 163）；其它 source 仍 2715 条未被碰。
匹配明细 direct=22, body=81, title+author=16, first10=9, title-only=1。
测试：supplement/test_parse.py 12 项（真页面 fixture + 同名异诗候选排序）ALL PASS，
supplement/test_anno.py 8 项 ALL PASS，检索回归 22/22，check_sig.py integrity ok。
库 132MB -> gz 70,083,875。

装机：versionName=1.11 Success，进程存活、crash buffer 0 条、无 SQLite 报错；
APK 内嵌库解包核对 补录 trans/note/intro = 117/120/114、integrity ok。
屏上仍未读到新释文：先是 PoemActivity 正文/释文为自绘 View（uiautomator 取不到文本），
这次设备上 MIUI 距离传感器遮罩 ScreenOnProximitySensorGuide 长期占住 mCurrentFocus
（手机被遮挡/俯放），dump 拿不到 app 节点 —— 属设备物理状态，非 app 故障。
下次验机：手机正放、光离开口袋，再跑 /root/probe4.sh。

## v1.12 (versionCode 13, DB_VERSION 12) — 补录释文第三批：登录墙后的 XHR 其实不验 cookie
更正 v1.11 的一处判断：当时认定「译文在 OnYiwenDetail 的 XHR 后、需 gsw2017user cookie，
拿不到」—— 那只成立于浏览器里。jsd_skin.js 读下来，客户端确实先查 getCookie('gsw2017user')
再决定跳不跳登录页，但它请求的 /nocdn/ajaxshiwenDetailCont.aspx 服务端不查：带桌面 UA +
Referer 的裸 GET 直接 200，未登录也能拿全量内容。
value 取值实测：yi=仅译文，yizhu=译文+注释，yizhushang=再加赏析尾段+参考文献，cont=纯正文。
取 yizhu —— yizhushang 会把赏析和参考文献混进正文（实测 body 1045 vs 128 字）。
该返回是逐句交错、靠颜色而非标签分段：原句 / 绿(#518564)该句译文 / 金(#af9100)该句注释。
金 span 同时装着重号 ¹²³ 与拼音 (jī)，所以注释只收带全角冒号的 run，正文则把金/绿 span
整段剔掉再取文本。请求 key 由 ajax_idjm() 从详情页 onclick 参数里读（两参数历来同值，
取第二个 12 位 hex；读不到就退回 cid），不硬编码。逐句粒度比桌面页的整块译文更细，
且桌面页缺的这里常有。
crawl_gushiwen.py 改动：parse_ajax() + fetch_ajax()（按 idjm 缓存 pages/idjm.yizhu.html）+
main() 里在正文门控已过的前提下，只补 trans/note 为空的字段，页面自带的不动。
本轮 fetched=15 / skip=31，XHR 回退 15 次全部命中，语料 22 -> 37 条（distinct poem_id 37）。
安全复核（同名异诗是这个库最大的风险）：杨朴《七夕》拿到的是自己那首「未会牵牛意若何」的译文，
不是白居易/李贺同名作的；刘桢《赠从弟》三首全文译文齐；洪适名下带补录且**有**译文仍 0 条。
库内发现 3 条洪适《拟古十三首》source=补录 但 trans 为 NULL —— 与本次前的备份逐条比对是同一批
（补录工程当初新增的行，正文就是洪适自作的拟古诗，没贴错文字），只是译文一直没抓到，非本次缺陷。
结果：补录 译文 117 -> 132，注释 120 -> 130，简介 127（共 163），无译文 46 -> 31；
其它 source 仍 2715 条未被碰。匹配档位 direct=37, body=81, title+author=16, first10=9, title-only=1。
测试：test_parse.py 18 项（新增 6 项 ajax 断言：颜色分离、拼音不入注、译文行数与诗句行数对齐、
idjm 读取与回退）ALL PASS；test_anno.py 含「杨朴不被贴李贺译文」「合并本不被贴单首译文」
「苏轼《春宵》未被误杀」ALL PASS；check_sig.py integrity ok，双署分组仍 416。
构建：gz 70,097,757（sha256 4f553533ab0793be…，APK 内 assets/poetry.db.gz 与之逐字节相同），
APK 69,894,682 已签名，adb install Success，dumpsys versionCode=13 / versionName=1.12。
APK 内嵌库解包核对：poem 79,831 行、补录带译文 132、杨朴七夕 trans/note/intro=91/191/151、
刘桢赠从弟 96/68/125、李朴中秋 143/144/134、毛泽东沁园春·长沙 309/1441/217。
验机限制（本轮再确认，别再重试）：release 包 run-as 报 not debuggable；本机无 su/root
（super_admin:shell 报 ROOT unavailable）；uiautomator dump 拿到的是前台其它 app 的树。
能确证的是 monkey 拉起后列表页正常渲染（5 185 位作者 · 79 831 首 · 846 471 句可检索）、无崩溃。
屏上读到具体某首新译文仍需手动打开；数据侧证据见上一段。
工具坑一条：edit_file 写含 " 的 Python 正则里的引号会被转义打断字符串（SyntaxError），
改走 terminal heredoc + 先取 onclick 参数串再抽 hex token 的写法绕过。
剩余 31 条：绝大多数是 cands=0（题名不在 69 个分类/选本页里，如 泛舟/朱熹、饮湖上初晴后雨二首·其二、
观书有感二首·其一、田家/范成大），下一步该扩枚举源而不是放宽门控。
## v1.13 (versionCode 14, DB_VERSION 13) — 补录释文第四批：匿名搜索建议接口扩候选源
上一轮结束时剩 31 条无译文，几乎全是 cands=0：题名不在 cat_index 覆盖的 69 个分类/选本页里。
这轮先证明「搜索页要登录」也只挡浏览器：skin.js 里搜索框的自动补全走
GET /shiwen2017/ajaxSearchSoD.aspx?valuekey=<q>，带桌面 UA 裸 GET 匿名返回 200，
结构是 <a href="/shiwenv_ID">题名 - 作者</a>（另有名句段，链接指向 /mingju/juv_*，不可用，丢掉）。
接口限制（都实测过）：前缀匹配、最多 3 条、不按作者过滤（q=田家 给 孟浩然/聂夷中/欧阳修，
永远轮不到范成大）、不切词（q="田家 范成大" 空）、只匹配题名（诗句整句查不到）。
所以它是 cat_index 的补充而非替代，正确性仍交给正文门控。
新增 supplement/gushiwen_so.py：so_rows() 解析、queries() 出候选查询词、search_candidates() 汇总去重。
queries() 是这轮真正有价值的部分：库里题名和站内题名格式不一致 ——
观书有感二首·其一（库）vs 观书有感·其一（站），整串前缀匹配 0 命中，
必须同时试 原样 / 去括号 / 去其一其二 / 去结尾 N首 / 取 · 或空格后半 五种形态。
crawl_gushiwen.py 改动：抽出 fetch_candidate() + try_candidates()（两个候选源共用同一套门控），
main() 里索引档没命中再走搜索档；SO_SKIP 留一个手工刹车（默认为空）。
抓到的题名和库里不同也没关系 —— apply_anno 走 poem_id 直连档。
fetched=8（观书有感二首·其一、饮湖上初晴后雨二首 其二、初夏睡起、暮春即事、冷泉亭、
干戈、茅檐、十一月四日风雨大作二首），语料 37 -> 46 条，distinct poem_id 46，无空译文。
两条低相似度都手工核过：初夏睡起 sim=0.71（库里题名是简称，站内《闲居初夏午睡起·其一》，正文同）；
茅檐 sim=0.71（王安石《茅檐》即《书湖阴先生壁》，同一首）。
test_anno.py 一条断言改写：《十一月四日风雨大作二首》合并本原来只能断言「别贴单首译文」
（当时库里根本没有它的两首全译），现在站内给了两首全译，改成双向断言 ——
合并本译文同时含第一首的「猫」和第二首的「战马」，而《…二首 其二》单首行不含「猫」。
库里两条实测：合并本 body67/trans156，其二 body33/trans95，各归各位。
结果：补录 译文 132 -> 141，注释 130 -> 137，简介 127 -> 136（共 163），无译文 31 -> 22；
其它 source 仍 2715 条未被碰，check_sig.py integrity ok，双署分组 416。
测试：test_parse.py 22 项（新增 4 项搜索接口断言：id+题名+作者解析、丢弃名句链接、
题名词干可前缀命中、原样题名排首位）ALL PASS；test_anno.py 9 项 ALL PASS。
过程中修掉四个自己的 bug，记下来免得重犯：
1) 模块名 html 被函数参数 html 遮蔽（AttributeError: 'str' object has no attribute 'unescape'）；
2) so_query 里 CACHE/get/DESKTOP 换惰性 _g() 时漏改一处（会 NameError）；
3) main() 里用 got 接结果，撞了已有计数器 got（TypeError: can only concatenate tuple）；
4) crawl_gushiwen <-> gushiwen_so 循环导入，依赖方向改成 crawl 引 so、so 里惰性 import。
构建：gz sha256 8f5ce37a47297601…，APK 内 assets/poetry.db.gz 与 out 逐字节相同，
APK 69,902,874 已签名。装机：adb device offline 一次，kill-server/start-server 后
install Success，dumpsys versionCode=14 / versionName=1.13。
APK 内嵌库解包核对：poem 79,831、补录带译文 141、观书有感二首·其一 67/7/180、
饮湖上初晴后雨二首 其二 81/89/165、初夏睡起 68/149/140、十一月四日风雨大作二首 156/233/139。
验机环境这轮变了：adb 只剩 emulator-5554（production build，adb root 被拒、
run-as not debuggable、UI 自动化包和 screencap 都要 root），设备还停在 Dozing、
mCurrentFocus 长期是 NotificationShade，dumpsys deviceidle disable + svc power stayon
之后才 Awake 但焦点不还给 app，所以屏上文本仍未读到。
能确证的：进程存活（pidof 有值）、crash buffer 0 条、
dumpsys dbinfo 显示 /data/user/0/com.poetry.app/files/poetry.db 已 Open、只读、
27 条语句全部 succeeded（含 SELECT COUNT(*) FROM line），无 SQLiteException。
即库确实被重解压并正常打开；具体某首新译文上屏仍需手动打开确认。
剩余 22 条：多为站内确实没有的（送天师/朱权、负暄四首 其四/刘敞、八月十四夜神泉官满再别同官/吴泳、
入直召对选德殿赐茶而退/周必大），以及同名抢占被门控挡下的（田家/范成大、新竹/陆游 ——
搜索接口 top-3 里根本没有这两位的那首，放宽阈值就是贴错译文，不该动）。

## v1.14 (versionCode 15, DB_VERSION 13) — 搜索全面化：诗名 + 正文一起查
原来的「诗句查原文」只查 line 表（846,471 行），等于只搜正文：输「静夜思」查不到李白那首，
因为《静夜思》这首诗里根本没有「静夜思」三个字；登高、虞美人、乐游原同理。
line 表覆盖 79,831 首（每首都有行），正文侧本来就全，缺的只有标题 —— prologue 只有 6 条，可忽略。
PoemDb 新增 searchTitles + pickTitles + titleRows，searchAll 把两路合成（题名在前、诗句在后，
按 poemId 去重），searchVerses 保持原样不动，所以旧的近似/相邻两句逻辑零风险。
标题用 LIKE 全表扫，实测 79,831 行 34–100ms，无需建索引；title_s/title 两列都匹配，
输入繁体也能命中（normalize 把繁体折到简体列）。
排序调了三轮，每轮都是被具体查询证伪后改的：
1) 只按 poem_count 排 -> 虞美人 全是辛弃疾（他有 5 首同名），李煜看不见。
2) 加「精选集优先」压过精确层 -> 《明月》被挤掉，精确匹配必须永远在最前。
3) 定案：精确层与宽松层分两次查询。合成分支一次 ORDER BY 取 LIMIT 200 也不够 ——
   词牌精确行有 150+，窗口根本读不到 虞美人·春花秋月何时了。
   层内顺序：精选集（诗经/楚辞/南唐二主词/曹操诗集 > 花间集/纳兰性德/补录 > 全唐诗/全宋词）
   -> 有译文/注释/简介的 -> 无名氏后置 -> 短题优先 -> 作者产量。
Java 侧再加两个 SQL 表达不了的限流：同一作者 ≤2 张卡片；精确同名 ≤半页。
结果（PoemDb.java 里那段 SQL 被测试脚本直接抽取执行，不是另写一遍）：
虞美人 -> 4 首精确同名后紧跟 李煜《虞美人·春花秋月何时了》；浣溪沙/菩萨蛮 同理出李煜；
水调歌头 -> 辛弃疾+苏轼并列（苏轼那首在库里标题就叫「水调歌头」，第一版精确层 LIMIT=limit
被辛弃疾 8 首占满，改成固定多取 200 才对）；静夜思 -> 只有李白 1 条；明月 -> 《明月》排第一。
题名写法不一致时的兜底：searchTitles 命中不足 4 条，就用 longestChunk（最长无标点片段）重试，
所以用户打「观书有感·其一」能命中库里的「观书有感二首·其一」。
UI：入口「查诗句」改「查诗词」，页头改「查诗词」，副标题/输入框提示/状态行都点明诗名也能搜，
示例 chip 第一个换成「静夜思」（它不是任何诗句，只有新分支能查到，本身就是教学）。
标题命中的卡片不重复显示书名号标题，改挂「· 题名命中」标记，避免读成《静夜思》 静夜思 李白。
测试 supplement/test_title_search.py + supplement/title_sql_harness.py：12 项 ALL PASS，
跑的是 APK 内解出来的库。过程中被工具坑到的两处：heredoc 写 python 会吞 [^"\] 这类转义
（改用 create_file）；中文串在 dex 里要用 grep -a 匹配，strings 默认不输出非 ASCII。
装机验证（emulator-5554，versionCode=15）：主页按钮显示「查诗词」；点进去
页头/副标题/提示/示例全部为新文案；点示例「静夜思」得
「3 条结果」= 静夜思 李白 · 题名命中 / 《同工部李侍郎适访司马子微》沈佺期 · 含此句 /
《送饶州张使君》贾岛 · 近似；点「床前明月光」仍得「1 处出处」床前看月光《静夜思》近似 ——
正文搜索未回归。
未做的：VerseActivity 未导出，adb am start --es query 走不通（SecurityException not exported），
所以只能点 UI 验证；这是正确的安全默认，不为测试放开。

## v1.15 (versionCode 16, DB_VERSION 13) — 搜索并入诗人页，删掉独立查诗词页
搜索框现在一词三查：诗人姓名、诗名、诗句，结果同屏分节显示（「诗人」「诗词」两个小标题），
点诗人进作者页、点诗词进诗页。VerseActivity 连同 manifest 声明一起删除，主页「查诗词」按钮删除。
MainActivity 改动：items 由 List<Author> 改为 List<Object>（Author / VerseHit / String 表头三态），
adapter 按类型分派渲染，getItemId 退回位置、areAllItemsEnabled=false 让表头不可点；
两路各自异步取数存 authorRows / poemRows，由 publish() 固定顺序合成，谁先回来都不打乱页面；
输入防抖 220ms（原来每敲一个字就查一次诗人表），IME 搜索键立即执行并收起键盘；
seq 序号守卫丢弃过期结果（先发的慢查询不能覆盖后发的）；authorsExhausted 让短页后不再空转翻页。
朝代筛选对诗词同样生效：标题查询把谓词下推进 SQL（WHERE (?='' OR IFNULL(a.dynasty,'')=?)，
空串自己匹配自己，因此一条语句形态服务两种情况）。没有下推的话，选「宋」会把一页全唐的
标题命中直接筛成空白，而不是继续往下找宋的那几条 —— 这是必须在 SQL 里做的原因。
正文命中在 Java 侧筛（倒排引擎不按朝代组织），筛时超取 6 倍以免筛空。
状态行分三种：正在检索诗词… / 「N 位诗人 · 搜诗词请至少输入两个字」（单字标题与正文引擎都要 2 字以上）/
「N 首诗词 · M 位诗人」，避免诗词还没回来就显示 0 首、被当成搜不到。
新增测试入口 am start -n com.poetry.app/.MainActivity --es query X：adb 输不了中文，
uiautomator 又被 MIUI 的 AOD/通知栏覆盖层挡住（mCurrentFocus 一直是 NotificationShade，
dump 出来全是 com.android.systemui），只能走 Intent + DB trace 取证。
supplement/test_title_search.py 扩到 18 项 ALL PASS：原 12 项排序用例 + 6 项朝代筛选
（登高/唐 8 条、虞美人/宋 全宋、静夜思/唐 1 条、登高/宋 与 登高/清 与 静夜思/宋 应为空）。
harness 里修了一处：精确层语句不能带宽松层专属的 prefix CASE，否则占位符数对不上（断言当场抓到）。
过程中一条断言先失败过 —— 我以为「登高/宋」该有结果，查库知道全 56 条登高* 都归唐，
是我的预期错而非筛选错，于是把这条改成明确断言空，钉住它是数据事实而不是筛选失灵。
设备验证（versionName 1.15）：apk 内 dex 有 searchAll/publish/poemRow 与「正在检索诗词」「首诗词」，
VerseActivity 字符串已为 0；am start --es query 虞美人 后 dumpsys dbinfo 抓到 20 条
fillPoem 语句、且都带本轮新加的 IFNULL(a.dynasty,'') 列 —— 20 = 标题层 ≤8 + 正文层 ≤12，
说明两路都跑了、跑的是新代码。
UI 文本已机读补验（supplement/test_ui_device.sh，7 项设备断言 ALL PASS）：
前一轮拿不到是 MIUI AOD 挡住渲染层，关 aod_display_enabled/doze_always_on 后唤醒即可，
脚本每次 force-stop 再冷启（am start 热启动不重跑 onCreate，query extra 不会更新）。
实测：静夜思->《静夜思》李白·唐 3 首；床前明月光->《静夜思》近似（回归通过）；
观书有感·其一->观书有感二首·其一/朱熹；虞美人->12 首且含李煜；明月->《明月》排诗词节
第一（诗人节同时给出 明月潭龙女）；单字 李->状态行「60 位诗人 · 搜诗词请至少输入两个字」
而不是 0 首；空框浏览态无分节头。点诗人行进 AuthorActivity、点诗词行进 PoemActivity
(topResumedActivity 直接验证)。虞美人+宋 chip：结果全部宋，无唐泄漏。
后续把这套断言接进 verify.sh 时踩到并修掉两处，都写进了 supplement/test_ui_device.sh 注释：
一是 force-stop 必须在 am start 之前 —— 热启动不重跑 onCreate，--es query 被忽略，我把它挪到
dump 之后，结果 7 例全 FAIL 且文本完全相同（都是上一例残留页）；「全例同文本的失败」即残留页指纹。
二是本机 KEYCODE_WAKEUP 无效，只有 POWER(26) 能唤且是切换键，wake() 于是先读 mWakefulness 再决定按不按。
另修一处假绿：设备读不到时原脚本仍打 ALL PASS（fails=0 而 skipped=7），现改为 skipped 非 0 即失败。

# v1.16 (versionCode 17)

飞花令重做（FeihuaActivity + 新增 DialView）：

- 三个输入框：令字、出句者、答句者。出句者默认「系统」，即由程序从库中随机抽句出句；答句者手写作答。
- 令字位置改成轮盘：任意位置 + 第1..第7字共 8 格，选中格转到顶部指针下（ObjectAnimator 反向角
  -slot*45deg，DecelerateInterpolator）；点格子即转。文字按格反向旋转，否则下半圈倒置。
- 轮盘中心留空洞，开始/停止（同一按钮切换，暂停后可继续）与认输浮在空洞里；DialView.onTouchEvent
  对半径 < inner 的触摸返回 false，事件才能落到按钮上。
- 底部对局记录占满剩余高度，每句都带「作者《篇名》」，ListView 以 stackFromBottom 自动跟到最新，
  轮次多了自己滚动。点任意句跳全诗。
- 答句校验三条：原文完全一致（matchLine）、令字确实在轮盘所指位置、本局未用过；不合格把原句送回
  输入框并说明原因，不计分。「提示」填一句合法句进输入框，只算提示、不计分。

PoemDb.findLines 改为严格：pos 给定时只在异体字里找该位置，找不到就返回空数组，不再回落到
「任意位置」。旧行为会让轮盘停在空档时系统出违反规则的句，而答句者却按规则被判错。调用方只有
飞花令一处（grep 确认），搜索路径不受影响；实测热字 40 个 × 7 档均非空，「之」等冷字各档也有句。

未做：新界面无自动化断言，轮盘观感与中心按钮命中区仍需目视确认。

# v1.16.1 (versionCode 18) 轮盘中枢三颗圆形按钮

开始（绿 0xFF2E7D32）/ 停止（橙 0xFFC77700）并排在上、认输（红 0xFFB00020）在下，全部画成圆：
OVAL GradientDrawable + 52dp 见方 LayoutParams + setStateListAnimator(null)（系统 Button 的高程
动画会按矩形裁剪，圆边被削掉）。

改圆时连修三处自己写进去的错：

1. roundBtn 原先写 `if (b.getLayoutParams() instanceof LinearLayout.LayoutParams)` —— new Button
   的 getLayoutParams() 是 null，条件恒假，尺寸从没设上过，两颗圆钮会被 LinearLayout 默认参数
   拉成整宽。改为直接 setLayoutParams(52dp 见方)。
2. 一个 toggle() 按钮拆成 start()/stop() 两个：开始只在未运行时开局（暂停后按它继续且不重新出
   句），停止只暂停不清盘；原先 startBtn.setText 的四处调用与字段一并删掉。
3. DialView 里 c.rotate(band, ...) 是错的：扇形本就用绝对弧角绘制，文字从未被斜置，再转反而把
   下半圈的第5/6/7字转到倒立。删掉旋转，标签全圈正立。

hub 半径 0.68 -> 0.70（空洞要装三颗圆钮），标签字号随环带 (outer-inner)*0.44 重算。几何复算：三档
屏宽（320/360/411dp）下 hub 半径 76.3dp，三钮最远角 67.7dp，均容得下；DialView.onTouchEvent 用同
一 innerR()，中心死区与绘制一致，事件才落得到按钮上。

仍未做：轮盘与三颗圆钮的实际观感依旧没目视验证——设备停在 MIUI 防误触模式
（ScreenOnProximitySensorGuide，mWakefulness=Dozing），且 FeihuaActivity 未导出，shell 无法 am start，
必须从主页点「飞花令」进。

# v1.16.1 补：飞花令离线回归 supplement/test_feihua.py

轮盘是自绘 View，uiautomator 里根本没有扇形节点，屏读断言看不到它；于是把这轮真正会错的东西
固化成第 4 个离线套件（已接进 verify.sh）：

- posOf/slotOf 双向映射 8 档全遍历；
- 命中判定镜像 onTouchEvent 的 round((deg-angle)/45)，8 个带角 × 8 格 × ±15° 共 192 次，
  以及 spinTo(0..7) 是否正好停在顶部指针下；
- 中枢要求三颗圆钮、三色互不相同、绘制与触摸共用同一 innerR()，并按 dp 复算三颗 52dp 圆是否
  真在空洞内（67.7dp <= 76.3dp）；
- 源码结构断言：findLines 的 pos 分支必须留着 return new int[0] 且不得出现 postings(v, null)
  ——用花括号配对取分支（第一版按 'for' 切片切早了，把自己误判成 FAIL）；
- 数据侧：月/花/春/山/人/风/之 七字 × 8 档池子全部非空，且各档不超过「任意位置」池子。

# v1.17 (versionCode 19) 改成钟表式：表盘固定，表针转 5 秒定位置

去掉停止按钮。中枢只剩两颗圆钮：开始（绿）在上、认输（红）在下。

- DialView 从「盘面转、指针不动」倒过来改成「盘面固定、表针转」：8 格固定在 i*45°，表针
  （handAngle，0=正上方，顺时针）扫过去。这才叫钟表盘。
- 点开始 = spinRandom()：随机选一格，表针转满 4 圈再减速停上去，历时 SPIN_MS=5000；表针上带
  一个倒数圆牌显示剩余秒数（5..1）。停稳后 SpinDone 回调 -> rebuild() 按新位置重抽池子 ->
  beginPlay() 立刻出第一句。所以「表针指向哪里，本局就按那个位置打」。
- 中途认输走 cancelSpin()：清掉回调再 cancel，避免动画结束的 onAnimationEnd 又把暂停中的局拉起来。
- 点格子仍是手动指定（600ms 转过去，无倒计时）；旋转中 onTouchEvent 直接吞掉点击。
- delta/target 改成「整圈数 + 顺时针补角」，表针永不倒着走。

test_feihua.py 里两段是空断言，被变异测试抓出来后重写：原先 section 3/3b 用 Python 自己把
公式重算一遍，Java 怎么改它都照绿（把落点改成偏 22.5°、把 ceil 改 floor，它都判 PASS）。现在
改成把 DialView.java 里的 hit/delta/target/secs 四条表达式用正则抠出来，机械转成 Python 再 eval，
参数（SLOTS/STEP/SPIN_MS）也从源码读；(int) 只删不转，并用 cast_ok 断言它一定包着 floor/ceil。
重跑 12 例变异：11 处改坏全部 CAUGHT（含此前 MISSED 的落点偏移、倒退、floor），基线通过。

# v1.17.1 (versionCode 20) 修表针不落地：设备侧验证暴露的真问题

设备断言补上后（supplement/test_feihua_device.py，走 adb+uiautomator：主页点「飞花令」→点中枢
「开始」→ 读屏断言），第一轮就抓出：按钮停在「抽令」，池子已加载（剩余 19570 句），但一局没开。

logcat 定位到断链位置：
  start() pendingStart=true → spinRandom target=4 → animateTo from=0.0 to=1620.0 → 之后再无日志
即 ObjectAnimator 起来了，但 onAnimationEnd 与自加的 postDelayed 兜底双双没跑。同一次实验里
1.2 秒的主线程探针也没打印 —— 进程被 MIUI 冻结了（息屏即冻），不是动画算术问题。
（另一半原因是测试自己的 bug：wake() 用 keyevent 26 是 POWER 切换，屏本来亮着，一发就按睡了。）

三处改动：
1. DialView.settle()：动画结束统一走它，settled 保证只跑一次；cancelSpin 一并吞掉挂起的结束回调。
2. 兜底定时器改用独立 main-looper Handler，不再用 View.postDelayed —— View.postDelayed 走 view root
   的 handler，视图 detach 或窗口不可见时行为不同；main.postDelayed(settleTimer, ms+400) 不依赖这个。
3. FeihuaActivity.onCreate 加 FLAG_KEEP_SCREEN_ON。这是面向真实用户的修法：表针转一半屏睡了，
   用户看到的正是「按了开始不出一句」。adb 的 svc power stayon 只在充电时生效，所以设备侧另用轮询
   中检测 mWakefulness 并 keyevent 224 唤醒（224 只唤不睡，26 会反着把屏按睡）。

测试端同时补：test_feihua.py 3c 段断言兜底链路（postDelayed(settleTimer / settle() 只跑一次 /
onAnimationEnd 走 settle / clearSettleTimer 内做 null 守卫）；device 脚本记录「测试期间屏睡了几次」，
睡过就把环境冻结写进 FAIL 文案，避免再把环境问题当成产品 bug。

证据边界要说清：v1.17 的落点随机性与「出句严格符合落点位置」是真跑过的 —— 5 轮分别落 任意/1/2/4/5，
出句 月色清且冷/阶前月色与蛩声/旅宿常待月/合围侔月晕/日月宜长寿，全部匹配。但 v1.17.1 这三处修复
尚未在设备上验证过：写完就再没能把屏唤醒（mWakefulness 停在 Dozing，keyevent 224 与
wm dismiss-keyguard 都无效，uiautomator 返回空）。verify.sh 离线三套 ALL GREEN，不等于修好了。

# v1.18 (versionCode 21) 去掉名字框与黑三角，高亮改在落点才跳

1. 删「出句者/答句者」两个输入框：askerName/answerName 字段、nameRow() 方法与
   outer.addView(nameRow()) 一并删除，orDefault() 随之无用也删。asker()/answerName() 保留但返回
   常量 —— 屏上原本显示的就是这两个词（「系统」「我」只是 hint，从没被输入过，一直走 orDefault
   兜底），所以比分行与日志措辞一字不变。
2. 删表盘顶部黑色小三角（onDraw 末尾那段 Path + 0xFF2B2B2B）。表针自己会指，不需要固定指针。
3. 高亮时机（真 bug）：animateTo 开头就 `selected = slot`，点下开始那一帧目标格即变色，5 秒抽签
   结果提前泄露。改为 animateTo 只写 landing，settle() 里才 `selected = landing`，表针停稳一刻
   颜色才跳。手动点格子仍当帧提交（onTouchEvent 里 `selected = hit`）：onSlotPicked -> rebuild()
   同步读 getSelected()，延后提交会按旧规则重抽。

test_feihua.py 补 4b/4c：body() 用花括号配对截方法体（防止被别处字符串提及糊弄），断言 animateTo
内不得出现 `selected = `、必须有 `landing = slot`；settle 内必须 `selected = landing`；onTouchEvent 内
必须 `selected = hit`；另断 0xFF2B2B2B 消失、onDraw 不再 drawPath、drawHand 仍只画一次、
nameRow/askerName/answerName/edit("系统")/edit("我") 全部不在。变异测试 5 例全 CAUGHT（改回
selected=slot / 重画三角 / 抽掉 settle 的提交 / 加回 nameRow / 加回 askerName 字段）。

test_feihua_device.py 也补断「系统」「我」两节点消失。但本轮上机验证未做成：mWakefulness 反复掉回
Dozing，keyevent 224/26 与 wm dismiss-keyguard 都留不住亮屏，屏睡计数报「测试期间屏幕睡了 20 次」，
FAIL 文案因此指向环境冻结而非产品逻辑。v1.18 这三处改动目前只有离线证据。

## v1.18 设备实测（补上一轮缺失的证据）

三项都在真机上确认，其中第三项只能靠像素：表盘自绘，uiautomator 把它报成普通 android.view.View，
既拿不到自定义类也拿不到颜色。

supplement/shoot_dial.py 的做法：adb exec-out screencap 出 raw RGBA8888（16 字节头），一帧 14MB、
拉回 0.6s，所以逐帧采样负担得起。几何不从像素反推——之前用奶油色 bbox 反算把圆心定到 (781,959)，
明显偏离屏心，因为页面上别处也有浅色。改为读布局树：包含两颗中枢圆钮、又不是整页的那个节点就是
表盘块，centre=节点中心、outerR=min(w,h)/2-22dp，与 DialView.outerR() 同一套算法；实测 (640,1102)、
outerR=355。角度也曾错 22.5 度：DialView 画的是 start=-90-STEP/2+i*STEP 扫 STEP，扇形中心在 i*45-90
（12 点起顺时针），不是 i*45-67.5。采样点每格 5 角 x 2 半径，静止时恰好一格拿到 9/10、其余 0/10，
说明分类器没读错。

第一次跑出一个假 FAIL（t=2.7s 变色）。原因是倒计时徽标：badge 也是暗红 0xFF8B3A2B，圆心在
(outer-26dp)=0.762*outer、半径 13dp=0.118*outer，扫起来覆盖 0.64-0.88，正好压在我原先 0.78 的采样
环上，扫针经过哪格就把哪格染红。半径挪到 0.90/0.94（badge 够不到，rim 在 1.00）并要求 n_lit>=7/10
才判亮。重跑：按下起 6.6s 才变色 —— 5s 扫针 + 约 1s 的按下确认与采样延迟，PASS；t<1s 才是 bug。

黑三角用同一帧验：删除位置是 rim 上方 y in [cy-outer-12dp, cy-outer+2dp]、|x-cx|<=7dp，实测该带内
暗像素 0 个，全是页面底色 (251,247,239)；改前那里有 ~200 像素实心 0xFF2B2B2B。

verify.sh 全绿：device assertions ran=7 ALL PASS、feihua device checks ALL PASS（含「系统」「我」
两节点已消失、抽签落点与出句位置相符）。

踩过的坑记一笔：之前几轮「屏每分钟必睡」不是 MIUI 冻结，是 keepawake(False) 把
screen_off_timeout 写回 60000，自己把下一轮埋掉；这台机 AC/USB/Wireless 全 false（无线 adb），
svc power stayon 因此完全无效，只能靠长超时。uiautomator dump 前必须先亮屏解锁，否则拿到的是
空的 8245 字节壳子——那次 gone-ok=True 是零节点造成的空洞为真，不算证据。

## v1.19 GitHub Actions 构建 APK

`.github/workflows/build-apk.yml`：手动 `workflow_dispatch` + 推 tag（`v*.*` / `v*.*.*` /
`release-*`）自动构建，产物上传为 Release 附件。**数据库不在 CI 重建** ——
`out/poetry_lite.db.gz`（~70 MB）本就版本化，`build.sh` 找不到未压缩库时直接把它打进 `assets/`；
CI 只校验（体积不是桩、gzip 完好、必需表齐、行数 >79000）。所以 CI 只要 JDK + aapt2 +
android-34 的 `android.jar`，不需要 `repo/`、`pydict/`、注译语料。

三个真实坑，都是跑出来的不是想出来的：

1. **`android-actions/setup-android@v3` 在 run #1 就挂**：`Warning: Failed to find package 'tools'`
   → sdkmanager 退 1。它装的是已停发的 legacy `tools` 包；日志前面那一大堆
   "Android SDK Preview…agree to the terms" 是 license 正文噪音，不是失败原因，很容易误读成
   需要接受预览协议。runner 镜像本就预装 SDK，于是改成 `ci/setup_sdk.sh` 只补缺的东西。
2. **校验清单必须照 build.sh 的真实依赖列，不能照 SDK 愿望清单**。第一版要求 `$BT/aapt2` 可执行，
   结果本机整套 build-tools 都被判死 —— 其实 build.sh 用的是 PATH 里的 `/usr/bin/aapt2`，
   zipalign 也走自带的 `app/zipalign.py`。真正要验的是：aapt2（PATH 优先，否则 `$BT/aapt2`）、
   `$BT/d8`、`java -jar $BT/lib/apksigner.jar`、`platforms/android-34/android.jar`、javac/python3/zip。
   build-tools 逐个**实跑**挑选而非取版本号最大：本机 `37.0.0-rc2/aapt2` 就因缺 loader 依赖
   `cannot execute: required file not found`，而隔壁 36.0.0 正常。
3. **`test_feihua.py` 的 `POETRY_SRC` 默认写死 `/root/poetry/...`**，本机绿、CI 上必炸。改为按
   `__file__` 推导（仓库已有这条约定，是我这次新增文件时漏守）。

版本号来源统一：`app/AndroidManifest.xml` 是 versionCode/versionName 的唯一来源，`build.sh` 从它
读并显式传给 aapt2（原来写死 `--version-code 1 --version-name 1.0`，实际生效的一直是 manifest
值，但那行读起来像它在做决定，且真生效就会造出自称 v1、无法覆盖升级的包）。tag 只做**一致性
校验**、不当取值：`v1.19` 必须等于 `android:versionName`（容忍 `-rcN` 后缀），否则 CI 直接失败 ——
APK 里的版本来自 manifest，让 Release 标题另取一源就会让下载文件和页面说的是两个版本。

`ci/check_release_tag.sh` 防的是：softprops/action-gh-release 会往**已存在**的 tag 上挂附件，
所以在 main 上勾着 make_release 重跑，会把今天的 APK 挂到上个月的 Release 上。tag 存在但不是
当前 commit 就失败（需要 `fetch-depth: 0`）。

签名：`POETRY_KEYSTORE`（base64）+ `POETRY_KS_PASS` 两个 secret 已配好；缺失时不静默换钥匙，而是
出 `::warning::` —— 新生成的钥匙签出的包能装但**无法覆盖升级**已装应用。

验证（都是真实运行，不是本地模拟）：
- run #1（dispatch）failure → 定位到 setup-android；run #2（dispatch）**success**，产物
  `poetry-1.18` 69,923,411 B；run #3（`git push origin v1.18`）**success**，全 14 步绿。
- Release v1.18 附件 `poetry.apk` 69,906,970 字节，与本机产物同大小；证书 SHA-256
  `22124039…473caa1a` 与本机完全一致；装回手机 `adb install -r` 返回 `Success`（覆盖升级成功
  才算签名对的）。sha256 与本机不同属正常：zip 里存了 mtime 与路径，构建不是逐字节可复现的。
- 另外用 `git clone` 出来的干净副本跑过完整链（check_db → version → build → check_apk →
  SKIP_DEVICE verify），那份副本只有 `.gz`、没有 keystore，和 Actions 拿到的环境一致。
