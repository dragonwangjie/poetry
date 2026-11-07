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
