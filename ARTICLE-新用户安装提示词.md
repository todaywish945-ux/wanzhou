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
下载清单里的 download_url 到我的下载文件夹。**清单里的 download_url 已经是 gh-proxy 镜像地址**（`https://gh-proxy.com/https://github.com/...`），国内能直连，直接用即可，**不要再往前面拼镜像前缀**（会双层前缀失败）。若这个镜像也失败，把地址里的 `gh-proxy.com` 换成 `ghproxy.net` 再试；还不行才试 assets 里的原始 GitHub 直链（国内基本不通，只作最后退路）。
不要让我自己去点浏览器地址栏里 `release-assets.githubusercontent.com` 的 GitHub 直链——国内会报 `Request.Invalid error`。必须真的发出下载请求。
下载完成后，**把 zip 的完整保存路径原样告诉我**（例如 `C:\Users\我的名字\Downloads\wanzhou-1.03-portable.zip`），我要知道文件落在哪。
下载后校验：Get-Item 看 Length 是否等于 size，Get-FileHash -Algorithm SHA256 是否等于 sha256。不一致就停下告诉我，不要解压。校验静默做，不用把哈希念给我。

【第四步 · 解压并启动】
解压到纯英文路径，推荐 %USERPROFILE%\wanzhou-pet\。确认 wanzhou-pet.exe 和 _internal\ 在同一层（exe 不能单独移动）。
双击 wanzhou-pet.exe —— 这个 exe 是启动器，会自动拉起三个进程（slot 1/2/3 = 角色 A/B/C），三只桌宠一起出现。
用 Get-CimInstance Win32_Process -Filter "Name='wanzhou-pet.exe'" 确认有三条带 --slot 的命令行。

【第五步 · 在桌面创建快捷方式】
在桌面创建一个名为「挽昼桌宠」的快捷方式，指向程序目录里的 `wanzhou-pet.exe`（这个 exe 是启动器，不带任何参数双击就会同时拉起三只）。用 PowerShell 创建：
- 目标路径：解压目录里的 `wanzhou-pet.exe` 完整路径
- 起始位置（WorkingDirectory）：解压目录（exe 所在文件夹，不能空，否则找不到 `_internal\`）
- 快捷方式保存位置：`[Environment]::GetFolderPath('Desktop')` 返回的桌面路径，文件名 `挽昼桌宠.lnk`
- 图标用 exe 自带图标即可
创建后用 `Test-Path` 确认这个 .lnk 文件存在，把结果和快捷方式的完整路径报给我。若桌面路径取不到就停下问我，不要自己猜一个路径。

【第六步 · 验收】
请我人眼看桌面：是不是同时出现三只 Q 版桌宠？看到了回复「看到了」，否则回复「没看到」，并确认桌面上有「挽昼桌宠」快捷方式。
有截图能力就自己先看，没有就按上面格式问我。

【第七步 · 可选的 AI 对话（先主动问我，我要才配）】
先停下来问我一句：「桌宠已经装好了。使用 AI 功能需要配置 API key，请问你需要使用 AI 功能吗？回『要』我就一步步带你配；不回或回『不用』我就到此为止。」
- 我回「不用」或不回：正常结束本次任务，不要追问、不要替我注册任何账号，更不要说「因为你没有要求」这种把责任推给我的话。
- 我回「要」：一次性把下面全部方案列给我，让我自己选，不要只推荐一个：
  ① 智谱 GLM ② 豆包 / 火山方舟 ③ 硅基流动 ④ 阿里云百炼（通义千问） ⑤ OpenAI ⑥ 你帮我选
  等我回复选哪个之后再动手，不许自己替我定。

【选定后 · 手把手带到底（这条最重要）】
我选定后，你必须全程一步步带我配置到能用，不许只发个链接或一句「按官网注册」就结束：
1. 一次只发一步：说清打开哪个网址、点哪个按钮、填什么、复制什么，每步等我确认。
2. 发具体网址、按钮名、字段值；不许说「你去注册一下」「按提示操作」这种空话。
3. 我说不会或没看懂：换白话重述、指出页面位置，不跳步、不敷衍。
4. 失败（401 / 找不到 Key / 连不通）：逐条带我排查，直到解决或我明确放弃。
5. 完成判据：地址和模型填好 + 我本人粘贴 Key + 测试连接成功 + 重启后发「你好」有回复，缺一不算完成。

Key 只能我自己在设置窗口里粘贴：右键任意桌宠 →「桌宠设置」→「AI 与对话」→「API 列表」。不要读取或复述我的 Key，也不要写进任何文件；任何输出里 Key 都打码或写 <已设置>。没有 Key 也能用桌宠，只是不能聊天。

【全局规则】
- 这是绿色便携包，不是安装包；不要去找安装向导、不要重装系统软件。
- 数据目录是 %APPDATA%\wanzhou-pet\，配置、Key、聊天记录都在里面，任何步骤都不要删改它。
- 任何一步连续失败 2 次，停下，把最后一次的原始报错贴给我，不要编造理由。
- API Key 在任何输出里都打码或写 <已设置>。
```
