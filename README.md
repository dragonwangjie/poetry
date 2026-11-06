# 诗海 — 离线全量诗词检索 Android 应用

单 APK、无网络、无服务端：SQLite 全库（79,831 首 / 846,471 句 / 5,185 位作者）压进 assets
（66.9 MB gz，解压后 126 MB），首启解压约 100s。检索同时覆盖诗人名、诗题名、诗句正文。

## 验证（先看这个）

```bash
cd supplement
SKIP_DEVICE=1 bash verify.sh   # 离线三套测试，约 3s
bash verify.sh                 # 追加 adb install + 7 项设备端渲染文本断言，约 2-4 分钟
```

`verify.sh` 的离线测试用的库是从**最终 APK 里解出来的**，不是读 `out/` 里的工作库，
所以它证明的是即将装机那份包的行为。设备端断言读 `uiautomator` 的真实屏幕文本，
读不到界面一律 SKIP 且返回非 0 —— SKIP 不算通过。

`git commit` 会自动跑 `SKIP_DEVICE=1 verify.sh`（`.git/hooks/pre-commit`）。设备端断言不在钩子里：
它要手机连着且屏幕亮着，耗时是分钟级，发货前手动跑一次。

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
- `out/` — 构建产物与中间库（git 忽略，仅 `verify_search.py` 例外，它是 CHANGELOG 的验证入口）
- 根目录 `*.py` — 建库与注译流水线（`build_db.py` 是总入口）
- `docs/upstream-chinese-poetry.md` — 语料上游的原 README

`app/CHANGELOG.md` 写给下一个接手的人：每个版本改了什么、为什么、以及踩过的坑
（gzip 被超时打断留下的残档曾被当成新库打进 APK；`am start` 热启动不重跑 `onCreate`
导致断言读到上一例的残留页；MIUI 息屏层抢走 `uiautomator` 窗口）。

## 签名密钥

`app/release.keystore` **故意不入库**（`build.sh` 里密码是明文，仓库会被拷来拷去）。
别名 `poetry`，store/key 密码同为 `poetry123`。丢了就无法覆盖升级，只能卸载重装。

指纹：`sha256 4b095586867b49ad…`（`sha256sum` 前 16 位），PKCS12，1 个条目。

副本分布（只有 `secure-backup` 分支那份在机器之外）：

| 位置 | 形态 |
|---|---|
| `app/release.keystore` | 明文，构建用 |
| `/sdcard/Download/release.keystore`、`/root/backup/release.keystore` | 明文，同一台机器 |
| 私有仓库 `dragonwangjie/poetry` 分支 `secure-backup` 的 `release.keystore.enc` | AES-256-CBC / pbkdf2 200k |

解密（口令不在仓库任何分支，本机存在 `/root/backup/keystore_backup_password.txt`，
应另存进密码管理器；重装系统前务必先把它抄走）：

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in release.keystore.enc -out release.keystore -pass file:口令文件
sha256sum release.keystore | head -c16   # 应为 4b095586867b49ad
```

已实测：从 API 下载 → 解密 → sha 一致 → `keytool -list` 能打开。
注意 `secure-backup` 是无父提交的孤立分支，`secure-backup` 的祖先里没有源码，
`main` 里也搜不到任何 keystore 材料（都已核对）。

新克隆的仓库里没有 keystore，而 `build.sh` 发现文件不存在会**静默生成一个新的**——包能装，
但之后 `adb install -r` 会报签名不符，看着像装机问题、其实是签名换了。所以打包前先确认
`app/release.keystore` 的 sha256 是上面那个值。

## 远端

`origin = https://github.com/dragonwangjie/poetry`（私有，271 个文件约 10 MB）。
`git push` 时通时不通：这台机器只稳定通 `api.github.com`，`github.com:443` 经常直连失败
（实测 `git push` 第一次成功、随后 `ls-remote` 连接超时）。推不动就走 API：
`git credential helper` 里已有令牌（`/root/.config/git/credentials`，不要打印内容），
用 `/git/blobs` + `/git/trees` + `/git/commits` + `/git/refs` 四步提交，孤立分支传 `parents: []`。

## 语料许可

数据来自 [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry)（MIT）。