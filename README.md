# 诗海 — 离线全量诗词检索 Android 应用

单 APK、无网络、无服务端：SQLite 全库（79,831 首 / 846,471 句 / 5,185 位作者）压进 assets
（66.9 MB gz，解压后 126 MB），首启解压约 100s。检索同时覆盖诗人名、诗题名、诗句正文。

## 验证（先看这个）

```bash
cd supplement
SKIP_DEVICE=1 bash verify.sh   # 离线三套测试，约 3s
bash verify.sh                 # 追加 adb install + 7 项设备端渲染文本断言，约 2-4 分钟
```

仓库不假设自己装在 `/root/poetry`：`.py` 用 `__file__` 推仓库根，`build.sh` 同理，
所以克隆到任意目录 `bash app/build.sh` + `bash supplement/verify.sh` 都能跑。
例外是流水线第 4 步的注译语料，默认 `/root/anno/anno.ndjson`，换机器用
`POETRY_ANNO=/path/anno.ndjson` 指过去。

`verify.sh` 的离线测试用的库是从**最终 APK 里解出来的**，不是读 `out/` 里的工作库，
所以它证明的是即将装机那份包的行为。设备端断言读 `uiautomator` 的真实屏幕文本，
读不到界面一律 SKIP 且返回非 0 —— SKIP 不算通过。

`git commit` 会自动跑 `SKIP_DEVICE=1 verify.sh`（`.git/hooks/pre-commit`）。设备端断言不在钩子里：
它要手机连着且屏幕亮着，耗时是分钟级，发货前手动跑一次。
## 只打包 APK（不重建数据库）— 默认路径

```bash
git clone ... && cd poetry && bash app/build.sh    # 产物 app/build/poetry.apk
```

`out/poetry_lite.db.gz`（66.9 MB）**已在版本控制里**，clone 下来就直接带库，
不需要语料、词典、注译语料，也不需要 `repo/`。`build.sh` 找不到未压缩的
`out/poetry_lite.db` 时，就用已提交的 `.gz` 原样打包，打包前 inflate 一遍并跑
`PRAGMA integrity_check` + 诗数下限校验。装好后首启自己从 assets 解压，
用户不会碰到任何"重新获取数据"。

改了库（注音、注译、补录）才需要走下面的重建路径，跑完记得
`git add -f out/poetry_lite.db.gz` 把新库一起提交。

## 重建路径

| 步 | 命令 | 产出 |
|---|---|---|
| 1 语料 | chinese-poetry 解压到 `repo/`（`repo.tar.gz` 是下载包，git 忽略） | `repo/全唐诗`、`repo/宋词` … |
| 2 建库 | `python3 build_db.py lite` | `out/poetry_lite.db`（不含元曲、不建二级索引；`core`/`song` 是另两种模式） |
| 3 注音 | `python3 build_pinyin.py`（需要 `pydict/`） | `poem.py`（诗句拼音）+ `poem.title_py` |
| 4 注译 | `add_translation.py` → `fix_trans.py` → `clean_trans.py`，再 `python3 supplement/apply.py` 加补录 | `poem.trans/note/intro` + `poem.sig`（飞花令反查） |
| 5 打包 | `bash app/build.sh` | `app/build/poetry.apk`（66.7 MB） |
| 6 验证 | `cd supplement && bash verify.sh` | `verify: ALL GREEN` |

第 2-4 步都直接原地改写 `out/poetry_lite.db`（3、4 只 `ALTER`/`UPDATE poem` 的列，不碰 `line`），
所以第 2 步必须最先跑、第 5 步必须最后跑。以前每步留一份 `poetry_lite.db.bak-preanno*` 快照，
2026-11-06 已清掉（6 份 721 MB，没有任何脚本读它们）；现在重跑流水线前要自己先 `cp` 一份。

依赖：`aapt2` + build-tools 36（d8 / apksigner）+ android-34 `android.jar` + python3（`opencc`）。
不用 Gradle —— `app/build.sh` 是 aapt2 / javac / d8 / 塞 assets / zipalign / 签名 七步手写。

## 目录

- `app/` — Android 源码（纯 Java + 手写 View，无 androidx）、`build.sh`、`CHANGELOG.md`
- `supplement/` — 注译抓取 + 全部测试；`verify.sh`、`test_ui_device.sh` 是验证入口
- `out/` — 构建产物与中间库（git 忽略），**两个例外**：`verify_search.py`（CHANGELOG 的验证入口）
  与 `poetry_lite.db.gz`（~70 MB 成品库，故意入库，见下「只打包 APK」）
- 根目录 `*.py` — 建库与注译流水线（`build_db.py` 是总入口）
- `docs/upstream-chinese-poetry.md` — 语料上游的原 README

`app/CHANGELOG.md` 写给下一个接手的人：每个版本改了什么、为什么、以及踩过的坑
（gzip 被超时打断留下的残档曾被当成新库打进 APK；`am start` 热启动不重跑 `onCreate`
导致断言读到上一例的残留页；MIUI 息屏层抢走 `uiautomator` 窗口）。

## 签名密钥

`app/release.keystore` 故意不入库，口令也不入库（曾经在 `build.sh` 和本文里各存过一份明文，已移除）。别名 `poetry`，store/key 同一个口令，由 `build.sh` 通过 `POETRY_KS_PASS` 读取，未设置就直接报错。**丢了就无法覆盖升级，只能卸载重装。**

指纹：`sha256 4b095586867b49ad…`（`sha256sum` 前 16 位），PKCS12，1 个条目。

分发原则：明文私钥只在构建机与口令文件里流转，`.gitignore` 已排除 `release.keystore` / `*.keystore` / `*.jks`。离线备份是同一文件的 AES-256-CBC（pbkdf2 200k）加密副本，解密口令**不进仓库任何分支**，请自行存进密码管理器，重装系统前先抄走。

解密：

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in release.keystore.enc -out release.keystore -pass file:口令文件
sha256sum release.keystore | head -c16   # 应为 4b095586867b49ad
```

## 远端

`origin = https://github.com/dragonwangjie/poetry`（私有，281 个文件；pack 约 70 MB，几乎全是入库的 `out/poetry_lite.db.gz`）。
`git push` 时通时不通：这台机器只稳定通 `api.github.com`，`github.com:443` 经常直连失败
（实测 `git push` 第一次成功、随后 `ls-remote` 连接超时）。推不动就走 API：
`git credential helper` 里已有令牌（`/root/.config/git/credentials`，不要打印内容），
用 `/git/blobs` + `/git/trees` + `/git/commits` + `/git/refs` 四步提交，孤立分支传 `parents: []`。

## CI 构建 APK（GitHub Actions）

`.github/workflows/build-apk.yml`，两种触发：

```bash
git tag v1.19 && git push origin v1.19   # 推 tag 自动构建并发 Release（APK 作附件）
# 或 Actions 页 -> Build APK -> Run workflow（只传 artifact；勾选 make_release 才发 Release）
```

**普通提交推 main 不会构建**（只匹配 tag），免得每次 WIP 提交都产一个 70 MB 包。
每次运行本身还会把 APK 存成 artifact（`poetry-<versionName>`，留 30 天），所以想临时拿个包测试
就用手动触发，不必为此打个 tag。

**数据库不在 CI 重建**。`out/poetry_lite.db.gz` 已版本化，`build.sh` 找不到未压缩库时直接把它
打进 `assets/`；CI 只做校验（体积不是桩、gzip 完好、必需表齐全、行数 >79000）。所以 CI 只需要
JDK + aapt2 + android-34 的 `android.jar`，不需要 `repo/`、`pydict/`、注译语料。

步骤里的逻辑都在 `ci/` 下的脚本里（YAML 里不嵌 Python，heredoc 的块缩进会把缩进代码弄坏）：

| 脚本 | 作用 |
|---|---|
| `ci/setup_sdk.sh` | 探测并补齐 SDK（只缺什么装什么）；build-tools 逐个**实跑**挑选 |
| `ci/version.sh` | 版本唯一来源是 `app/AndroidManifest.xml`；tag 与它不符就失败 |
| `ci/check_db.py` | 校验入库的 `.gz`：能解压、`integrity_check` 通过、表齐、行数够 |
| `ci/check_apk.sh` | 从成品 APK 回读 versionCode/versionName、验签、比对 `assets/poetry.db.gz` 字节数 |
| `ci/check_release_tag.sh` | tag 已存在却指向别的 commit 就失败（否则今天的 APK 会挂到旧 Release） |

`make_release` 什么时候会放行：`v<versionName>` 这个 tag **还不存在**，或者**已经正好指向当前
commit**。否则守卫拦下（run #5 实测：在 main 上勾着它跑，失败落在 `Check the release tag`，
报 `tag v1.18 already exists and points at 2b9108b6, not at this build`，仓库 Release 数没变）。
这是有意的 —— action 会往已存在的 tag 上挂附件，那等于把新 APK 塞进旧版本的 Release。

改版本号的地方是 `app/AndroidManifest.xml` 的 `versionCode` / `versionName`（`build.sh` 读它，
不再自己写死）。发版顺序：改 manifest -> 提交 -> 打同版本 tag -> 推 tag。

模拟 CI（本机跑过，与 Actions 拿到的内容一致：只有 `.gz`、没有 keystore）：

```bash
rm -rf /tmp/ci-sim && git clone /root/poetry /tmp/ci-sim && cd /tmp/ci-sim
bash ci/setup_sdk.sh && python3 ci/check_db.py && bash ci/version.sh && bash app/build.sh \
  && bash ci/check_apk.sh 21 && SKIP_DEVICE=1 bash supplement/verify.sh
```

## 语料许可

数据来自 [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry)（MIT）。