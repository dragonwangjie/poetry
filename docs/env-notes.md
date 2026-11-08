# 环境注意事项

## 不要删 `.git` 里的 `.l2s.tmp_*` 文件
这个设备的存储层会把文件数据卸到同目录的隐藏侧车文件（`.l2s.tmp_obj_*` / `.l2s.tmp_pack_*`），
而 sha1 命名的 git 对象文件本身只是一个指向侧车的符号链接。删侧车 = 删对象本体，
`git fsck` 会立刻报 `object corrupt or missing`，`git log` 直接 `bad object HEAD`。

`git fsck` 对 loose 对象目录里的侧车会刷一串 `bad sha1 file: .../objects/xx/.l2s.tmp_obj_*`，
那只是命名不合法，不是损坏。真要让 fsck 安静，用 `git gc` 把对象打进 pack（pack 侧车落在
`objects/pack/`，fsck 不看），而不是删文件。

## 这个文件系统上 `mv` 目录不搬数据
`mv .git /somewhere` 之后新位置是指向旧位置侧车的符号链接；一删旧位置，仓库就没了。
所以 git 仓库**只在最终位置创建**（`git init` + `git fetch` + `git reset --hard`），
不要 clone 到 /tmp 再往回搬。

## 出网限制
只通 `api.github.com` 与 `github.com`（git 协议）。`objects.githubusercontent.com`（
REST blob 下载的重定向目标）被拒，所以别用 `curl` 拉 blob 验证，用 `git clone` 后本地比哈希。

## git 对 github.com 推不动时用 HTTP/1.1
`git push` 会报 `GnuTLS recv error (-110)` 或 `Failed to connect to github.com port 443`，
同时 `curl https://github.com/` 却是 200 —— 是 HTTP/2 + 大 postbuffer 在这条链路上断 TLS。
本仓库已 `git config http.version HTTP/1.1`（仅 local，不随 clone 传播），新机器上再遇到就手动设一次。

本局实测：即使设了 HTTP/1.1，`git push` / `git clone` 仍会随机出现 `Failed to connect to github.com port 443`
（同一时刻 `git ls-remote` 可能成功）。这是链路抖动，不是仓库问题——直接重试，一般 2~3 次内成功。

## 设备侧像素验证（v1.18 实测总结）

自绘 View 的颜色只能靠像素验。`adb exec-out screencap` 直接出 raw RGBA8888（16 字节头，
1280x2772 共 14MB，拉回 0.6s），本地按下标取点即可，不需 PIL（本机没装）。

- 几何不要从像素反推。页面上别处也有同色（拿奶油色 bbox 反算把圆心定到 (781,959)，而屏心是 640）。
  从 uiautomator 布局树拿：“包含两颗中枢圆钮、又不是整页”的节点就是表盘块，
  centre=节点中心，outerR=min(w,h)/2-22dp，与 DialView.outerR() 同一算法。
- 采样半径要先算清其他同色图元的覆盖环带。倒计时徽标也是 0xFF8B3A2B，圆心 0.762*outer、
  半径 0.118*outer，扫起来覆盖 0.64-0.88，正好压在 0.78 采样环上，把“变色时刻”从 6.6s 假报成 2.7s。
  挑半径后还要打印每格票数：静止时应“恰好一格高票、其余全 0”，否则分类器不可信。
- 改设备设置（如 screen_off_timeout）必须在收尾还原成用户原值。写死 60000 把下一轮埋了，
  表现为“屏每分钟必睡”，很容易误归为 MIUI 冻结进程。这台机 AC/USB/Wireless 全 false（无线 adb），
  `svc power stayon` 因此完全无效，只能靠长超时。
- `uiautomator dump` 前必须亮屏且已解锁，否则拿到 8245 字节的空壳（mCurrentFocus=NotificationShade，
  mDreamingLockscreen=true）。空壳会让 `all(x not in texts)` 这类“已消失”断言空洞地为真，不算证据。
- 自轮询条件要选“只在完成后才出现”的文本。等「剩余句数」无效（初始页就有），害得 5s 抽签在 1s
  就被拍下一帧、误报“没开局”；等按钮回到「开始」才对（beginPlay 两条路径都做这步）。
