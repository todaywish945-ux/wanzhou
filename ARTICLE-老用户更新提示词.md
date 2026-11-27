# 老用户更新提示词

> **怎么用**：把下面「复制给 AI 的提示词」那一整段（代码块里的全部内容）复制，发给有电脑控制能力的 AI 助手（WorkBuddy / Claude Code / Codex 等），它会替你完成检查版本和更新。
>
> **为什么需要它**：你之前下载过桌宠（v1.00 / v1.01 / v1.02），新版 v1.03 修好了骗子酒馆玩不了、绝区零找不到、以及收不到更新通知的问题。但老版本客户端的更新按钮有的是灰的（只认旧的安装包格式），所以让它帮你判断该走哪条路最省事。
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
- https://cdn.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://fastly.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://gcore.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://raw.githubusercontent.com/todaywish945-ux/wanzhou/main/update.json

注意：jsDelivr 节点可能缓存旧版本。要取所有能读到的地址里版本号最高的那个，不能拿到第一条就停。读不到时回退 API：
https://api.github.com/repos/todaywish945-ux/wanzhou/releases/latest
API 返回的版本若主版本号大于 1（例如遗留的 v4.4.x）请忽略——那是移植前上游项目的 Tag，不是本项目的版本。

从最新清单里记下：version（版本号）、download_url（zip 直链）、assets 里 fileName 含 portable.zip 那条的 size 和 sha256、html_url（Release 页）。

【第三步 · 查我本机现在是什么版本】
程序目录通常在 %USERPROFILE%\wanzhou-pet\wanzhou-pet\。找 wanzhou-pet.exe，右键→属性→详细信息看「文件版本」；或读同目录的版本信息。把本机版本报给我。

若本机版本已经等于清单里的 version，直接告诉我「已是最新版，无需更新」，结束，不要重复折腾。

【第四步 · 判断走哪条更新路】
先看我本机版本：
- 若我装的是 v1.02 或更新：优先用客户端自带的一键更新。启动桌宠（双击 wanzhou-pet.exe 会同时起三只）→ 右键任意桌宠 →「工具与帮助」→「检查更新」→ 打开更新窗 → 看「下载并安装」按钮是否可点。可点就点它，它会自动下载、校验、替换并重启三只。
- 若按钮是灰的，或我装的是 v1.00 / v1.01：这些老客户端只认旧的 exe 安装包，一键更新用不了，走手动更新（第五步）。

【第五步 · 手动更新（仅当一键更新不可用）】
1. 下载清单里的 download_url 到我的下载文件夹。**清单里的 download_url 已经是 gh-proxy 镜像地址**（`https://gh-proxy.com/https://github.com/...`），国内能直连，直接用即可，**不要再往前面拼镜像前缀**（会双层前缀失败）。若这个镜像也失败，把地址里的 `gh-proxy.com` 换成 `ghproxy.net` 再试；还不行才试 assets 里的原始 GitHub 直链（国内基本不通，只作最后退路）。
   不要让我自己去点浏览器地址栏里 `release-assets.githubusercontent.com` 的 GitHub 直链——国内会报 `Request.Invalid error`。必须真的发出下载请求，不许说「找不到包」。
2. 校验：Get-Item 看 Length 是否等于清单的 size，Get-FileHash -Algorithm SHA256 是否等于清单的 sha256。不一致就停下，告诉我，不要解压。这一步静默做，不用把哈希念给我。
3. 关掉正在跑的桌宠（结束所有 wanzhou-pet.exe 进程）。
4. 解压 zip 到程序目录（例如 %USERPROFILE%\wanzhou-pet\），让 wanzhou-pet.exe 和 _internal\ 在同一层。旧的程序文件会被覆盖——这正是更新。
   千万注意：只动程序目录，绝对不要删或改 %APPDATA%\wanzhou-pet\ 里的任何东西（配置、Key、聊天记录都在那，删了就丢了）。
5. 双击 wanzhou-pet.exe 重新启动，应同时出现三只桌宠。

【第六步 · 验收】
用 Get-CimInstance Win32_Process -Filter "Name='wanzhou-pet.exe'" 确认有三条带 --slot 1/2/3 的进程；再确认程序版本已变成清单里的 version。然后请我人眼看一下：三只桌宠在不在、右键「骗子酒馆」能不能打开牌局。把结果一句话报给我。

【全局规则】
- API Key 在任何输出里都打码或写 <已设置>，绝不读取、复述、写进文件。
- 任何一步连续失败 2 次，停下，把最后一次的原始报错贴给我，不要自己编理由。
- 全程不要重装系统软件、不要动 %APPDATA% 里的数据。
```
