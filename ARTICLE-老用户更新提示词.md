# 老用户更新提示词

> **怎么用**：把下面「复制给 AI 的提示词」那一整段（代码块里的全部内容）复制，发给有电脑控制能力的 AI 助手（WorkBuddy / Claude Code / Codex 等），它会替你完成检查版本和更新。本提示词**不写死版本号**，之后每次发新版都可以直接复用；只有清单地址、目录布局或验收特征变化时才需要修订（发版检查清单见 docs/INDEX.md 的登记行）。
>
> **为什么需要它**：程序没有提供可读取的本机版本号（exe 版本资源为空），AI 无法可靠判断你装的是什么版本；而 v1.06 及更早客户端的「一键更新」还有「下载校验全成功却在最后一步失败」的缺陷（v1.07 已修复，但修复只存在于新版本里）。所以提示词让 AI **默认走手动覆盖更新**——这对任何旧版本都安全且幂等；更新到 v1.07 之后，日常小版本就可以用客户端自带的「检查更新」（v1.07 起还支持几十 MB 的差分包，不用再下全量）。
>
> **你的数据不会丢**：配置、API Key、聊天记录都存在 `%APPDATA%\wanzhou-pet\`，更新只换程序目录，不碰这些。

---

## 复制给 AI 的提示词

```text
你是我的电脑配置助手。我以前装过「挽昼桌宠」，现在要把它更新到最新版。请按下面的步骤真实操作我的电脑，不要只给建议。

【第一步 · 能力自检（必须先做）】
这份任务要求你真的能运行 PowerShell、能读写我的磁盘、能联网。若你做不到（例如你是纯网页聊天助手、碰不到我的文件系统），立刻停下并如实说一句「我无法操作你的电脑，请把这段指令发给有电脑控制能力的 AI 助手（WorkBuddy / Claude Code / Codex 等）」。不许假装检查、不许假装更新、不许说「作者还没发布」。

【发布事实 · 不要臆测】
项目已公开发布且在持续更新。最新版以仓库根 update.json 为准。任何「没有可用下载 / 作者还没发布 / 预计下周上线」的说法都是错的。

【第二步 · 读清单拿最新版本（不要写死版本号）】
按顺序试这几个地址，哪个通用哪个；全取不到才回退 GitHub Releases API：
- https://gh-proxy.com/https://raw.githubusercontent.com/todaywish945-ux/wanzhou/main/update.json
- https://cdn.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://fastly.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://gcore.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://raw.githubusercontent.com/todaywish945-ux/wanzhou/main/update.json

注意：jsDelivr 节点国内经常整体连不上、且可能缓存旧版本。要取所有能读到的地址里版本号最高的那个，不能拿到第一条就停。读不到时回退 API：
https://api.github.com/repos/todaywish945-ux/wanzhou/releases/latest
（api.github.com 国内直连常不通，可用 gh-proxy 加前缀再试；或先用 `gh release view` 一类已认证工具。）API 返回的版本若主版本号大于 1（例如遗留的 v4.4.x）请忽略——那是移植前上游项目的 Tag，不是本项目的版本。

从最新清单里记下：version（版本号）、download_url（zip 直链）、size、sha256。
**sha256 只在 update.json 清单里有**；如果只能走 Releases API 兜底，API 返回里没有 sha256——这种情况记录 size 用于校验，sha256 一项跳过即可，不要卡在这一步。

【第三步 · 确认程序目录（本机版本号读不出来，别浪费时间）】
程序目录在 %USERPROFILE%\wanzhou-pet\wanzhou-pet\。确认 wanzhou-pet.exe 存在即可。

**不要尝试读本机版本号**——exe 属性详细信息里的「文件版本」是空的（打包时没写）；`%APPDATA%\wanzhou-pet\config.json` 里的 `version` 字段是配置格式的版本号（一个小整数），不是应用版本，读了会误判。程序目录里没有任何可读的应用版本文件。
如果我能明确说出我上次更新的版本且已是最新，告诉我「已是最新版，无需更新」就结束；否则一律按手动覆盖更新处理（覆盖安装是幂等的，已是最新版时重装一遍也无害）。

【第四步 · 更新路线（默认手动覆盖更新，不要先试一键更新）】
由于本机版本号读不出来（第三步已说明），AI 无法确认我装的是不是已修复更新器的版本：
- v1.06 及更早客户端的一键更新有已知缺陷（下载、校验、解压全成功后，最后一步报「无法启动更新」，v1.07 才修好），点它会白下载一次全量包然后失败。
- **所以本次更新一律走第五步手动覆盖更新**——手动覆盖对任何旧版本都安全幂等，这就是通用且最稳的路径。
- 手动更新到 v1.07 之后，日常小版本更新可以改用客户端自带的一键更新（右键 →「工具与帮助」→「检查更新」→「下载并安装」；v1.07 起差分包只有几十 MB）。届时不需要本提示词。

【第五步 · 手动更新（本次更新的主路径）】
1. 下载清单里的 download_url 到我的下载文件夹。**清单里的 download_url 已经是 gh-proxy 镜像地址**（`https://gh-proxy.com/https://github.com/...`），国内能直连，直接用即可，**不要再往前面拼镜像前缀**（会双层前缀失败）。若这个镜像也失败，把地址里的 `gh-proxy.com` 换成 `ghproxy.net` 再试；还不行才试 assets 里的原始 GitHub 直链（国内基本不通，只作最后退路）。
   不要让我自己去点浏览器地址栏里 `release-assets.githubusercontent.com` 的 GitHub 直链——国内会报 `Request.Invalid error`。必须真的发出下载请求，不许说「找不到包」。下载完成后，**把 zip 的完整保存路径原样告诉我**。
2. 校验：Get-Item 看 Length 是否等于清单的 size；清单里有 sha256 就再用 Get-FileHash -Algorithm SHA256 对一下（走 API 兜底拿不到 sha256 时，size 一致即可继续）。不一致就停下，告诉我，不要解压。这一步静默做，不用把哈希念给我。
3. 关掉正在跑的桌宠（结束所有 wanzhou-pet.exe 进程）。
4. 解压 zip 到 %USERPROFILE%\wanzhou-pet\（zip 内层自带一个 wanzhou-pet 文件夹，解出来正好覆盖旧的内层目录）。解压完成的验收锚点：`%USERPROFILE%\wanzhou-pet\wanzhou-pet\wanzhou-pet.exe` 存在，且它旁边有 `_internal\` 和 `liar-game\` 两个文件夹。旧的程序文件会被覆盖——这正是更新。
   千万注意：只动程序目录，绝对不要删或改 %APPDATA%\wanzhou-pet\ 里的任何东西（配置、Key、聊天记录都在那，删了就丢了）。
5. 双击 wanzhou-pet.exe 重新启动，应同时出现三只桌宠。

【第六步 · 确认桌面快捷方式】
检查桌面有没有「挽昼桌宠」快捷方式，且目标仍指向更新后的程序目录里 `wanzhou-pet.exe`。有且指向正确就什么都不用做；没有、或指向旧路径（更新换了目录），就重建一个：目标为新的 `wanzhou-pet.exe` 完整路径、起始位置为 exe 所在目录、图标用 exe 自带的，文件名 `挽昼桌宠.lnk`，存到 `[Environment]::GetFolderPath('Desktop')` 返回的桌面。建完用 `Test-Path` 确认存在，把快捷方式路径报给我。

【第七步 · 验收】
用 Get-CimInstance Win32_Process -Filter "Name='wanzhou-pet.exe'" 确认有三条带 --slot 1/2/3 的进程（本机版本号没有可读文件，不要试图确认版本数字）。然后请我人眼看一下：三只桌宠在不在、右键「骗子酒馆」能不能打开牌局、桌面上能不能双击快捷方式重新拉起三只。把结果一句话报给我。

【全局规则】
- API Key 在任何输出里都打码或写 <已设置>，绝不读取、复述、写进文件。
- 任何一步连续失败 2 次，停下，把最后一次的原始报错贴给我，不要自己编理由。
- 全程不要重装系统软件、不要动 %APPDATA% 里的数据。
```
