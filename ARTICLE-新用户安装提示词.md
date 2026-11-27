# 新用户安装提示词

> **怎么用**：把下面「复制给 AI 的提示词」那一整段（代码块里的全部内容）复制，发给有电脑控制能力的 AI 助手（WorkBuddy / Claude Code / Codex 等），它会一步步帮你把桌宠装好。
>
> **这是什么**：挽昼桌宠是《绝区零》三姐妹（德蕾琪娜 / 林德薇恩 / 艾尔妲）的非官方粉丝桌宠，绿色便携包，不用装 Python、不用找安装向导。解压双击就出三只。
>
> **AI 对话功能**：需要你自己的 API Key（在主程序设置窗口里填，不要贴在聊天里）。没有 Key 也能用桌宠、看天气、玩牌局，只是不能聊天。

---

## 复制给 AI 的提示词

```text
你是我的电脑配置助手。帮我把「挽昼桌宠」便携版装好，让三只桌宠出现在桌面。请真实操作我的电脑，不要只给建议。

【第一步 · 能力自检（必须先做）】
这份任务要求你真的能运行 PowerShell、能读写我的磁盘、能联网。若你做不到（例如你是纯网页聊天助手、碰不到我的文件系统），立刻停下并如实说一句「我无法操作你的电脑，请把这段指令发给有电脑控制能力的 AI 助手」。不许假装检查、不许假装安装、不许说「下载页不存在」。

【发布事实 · 不要臆测】
项目已公开发布。最新版以仓库根 update.json 为准。任何「作者还没发布 / 网上没有下载 / 预计下周上线」的说法都是错的。

【第二步 · 读清单拿最新下载链接（不要写死版本号）】
按顺序试，哪个通用哪个；全取不到才回退 GitHub Releases API：
- https://cdn.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://fastly.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://gcore.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json
- https://raw.githubusercontent.com/todaywish945-ux/wanzhou/main/update.json

取所有能读到的地址里版本号最高的那个，别拿到第一条就停。API 兜底：https://api.github.com/repos/todaywish945-ux/wanzhou/releases/latest
若 API 版本主号大于 1（如遗留的 v4.4.x）请忽略，那是上游项目的旧 Tag。

记下最新清单的：download_url（zip 直链）、assets 里 fileName 含 portable.zip 那条的 size 和 sha256、html_url（Release 页）。

【第三步 · 下载并校验】
下载 download_url 到我的下载文件夹。**默认走国内镜像**（GitHub 直链在国内基本连不上，浏览器会报「无法下载 - 网络问题」）：把 download_url 完整拼到镜像前缀后面，按顺序试，哪个通用哪个：
- https://gh-proxy.com/ + download_url（实测可用）
- https://ghproxy.net/ + download_url
- download_url 原样（仅前两条都失败时才试）
不要让我自己去点浏览器里的 GitHub 直链下载。必须真的发出下载请求。
下载后校验：Get-Item 看 Length 是否等于 size，Get-FileHash -Algorithm SHA256 是否等于 sha256。不一致就停下告诉我，不要解压。校验静默做，不用把哈希念给我。

【第四步 · 解压并启动】
解压到纯英文路径，推荐 %USERPROFILE%\wanzhou-pet\。确认 wanzhou-pet.exe 和 _internal\ 在同一层（exe 不能单独移动）。
双击 wanzhou-pet.exe —— 这个 exe 是启动器，会自动拉起三个进程（slot 1/2/3 = 角色 A/B/C），三只桌宠一起出现。
用 Get-CimInstance Win32_Process -Filter "Name='wanzhou-pet.exe'" 确认有三条带 --slot 的命令行。

【第五步 · 验收】
请我人眼看桌面：是不是同时出现三只 Q 版桌宠？看到了回复「看到了」，否则回复「没看到」。
有截图能力就自己先看，没有就按上面格式问我。

【第六步 · 可选的 AI 对话（我不要求就不做）】
右键任意桌宠 →「桌宠设置」→「AI 与对话」→「API 列表」。默认有智谱 GLM，可改 API 地址和模型；要用别家就点「添加」。
API Key 由我自己在该输入框粘贴——不要读取、复述我的 Key，也不要写进任何文件。我粘贴完回复「填好了」，你再点「测试连接」，把结果原文告诉我（Key 打码）。没有 Key 可以跳过这步，桌宠其余功能照常用。

【全局规则】
- 这是绿色便携包，不是安装包；不要去找安装向导、不要重装系统软件。
- 数据目录是 %APPDATA%\wanzhou-pet\，配置、Key、聊天记录都在里面，任何步骤都不要删改它。
- 任何一步连续失败 2 次，停下，把最后一次的原始报错贴给我，不要编造理由。
- API Key 在任何输出里都打码或写 <已设置>。
```
