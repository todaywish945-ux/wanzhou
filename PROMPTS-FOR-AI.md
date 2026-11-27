# 给 AI 助手的全流程配置指令（挽昼桌宠 v1.03）

> 你是我的电脑配置助手。目标：把「挽昼桌宠」v1.03 便携版装好，三只桌宠同时出现在桌面，AI 对话能回复。
>
> **严格按阶段执行**：每阶段完成 → 对照验收标准自检 → 更新进度文件 → 一句话向我简报 → 进入下一阶段。  
> 用户不用懂代码、不用装 Python、不用找安装向导：这是绿色便携包。
>
> **能力自检（收到本指令后第一步，必须做）**：这份指令要求你**真实操作这台电脑**——能运行 PowerShell 命令、能读写用户磁盘、能联网下载文件。开始之前先确认你确实具备这些能力。如果做不到（例如你是纯网页聊天助手、运行在沙箱里碰不到用户文件系统或网络），**立刻停下并如实说一句**：「我无法操作你的电脑，请把这份指令发给有电脑控制能力的 AI 助手（如 WorkBuddy / Claude Code / Codex 等）」。**不许假装做环境体检、不许假装翻过文件夹、不许编造作者的进度汇报、不许说下载页不存在**——这些都会误导用户。
>
> **发布事实（不要臆测）**：项目已公开发布且在持续更新。**最新版以阶段 1 读到的 `update.json` 为准**（本指令编写时是 v1.03，2026-11-27 发布）；写死的版本/直链/校验值只是清单取不到时的兜底，可能已过期。任何「作者还没发布 / 预计下周末上线 / 网上没有可用下载页」的说法都是错的。
>
> 本提示词按 v1.03 真实发布物与源码核对：Release 附件、`packaging/pet_entry.py` 启动器、右键菜单、`%APPDATA%\wanzhou-pet\config.json`、`pet/chat/models.py`。



---

## 【我的信息】（发给 AI 前填，可留空）

```text
对话模型：<可留空 = 阶段 2 把选项发给我选；也可直接写厂商名：智谱 / 火山引擎豆包 / 硅基流动 / 阿里云百炼 / OpenAI / 其他>
对话 API Key：<绝对不要贴在聊天里；阶段 2 我会自己在设置窗口输入。如果已经贴过，用完后去服务商控制台换一把新 Key>
接口地址：<仅「其他 / 自备」时填 OpenAI 兼容 baseUrl（能拼出 /chat/completions）；不填留空>
模型名：<仅「其他 / 自备」时填；不填留空>
备用模型：<可选。本项目没有自动备用接口；写第二家厂商名表示「在 API 列表里再加一个可手动切换的 provider」，不填就不加>
```

---

## 【进度管理（最先做，每阶段都要更新）】

进度文件：`%APPDATA%\wanzhou-pet\配置进度.json`（应用数据目录在阶段 1 启动后即生成）。

格式：

```json
{"stage":"1","status":"done","evidence":"三只进程运行；压缩包 SHA256 校验通过"}
```

规则：

1. 每次开始先读这个文件。**已存在且 `status=done` 的阶段直接跳过，绝不重做**。  
   |  |  |  
   | --- | --- |
2. 每完成或失败一个阶段，立即写入：阶段号、`done|failed`、一句话证据（**不许写 Key**）。
3. 写失败也继续用聊天汇报，不要因为进度文件问题中断全流程。
4. 阶段编号只有 1 下载启动 / 2 对话模型（**可选**）/ 3 最终验收。**没有「阶段 0」**，不要自造阶段、不要汇报没做过的体检。**没有语音配置阶段**——语音只能用内置 Edge、默认关闭，用户想开自己右键开，不要代配。
5. **阶段 1 之后有决策点**：装好三只桌宠就写 `stage=1,status=done` 并停下来问用户要不要配 AI。用户回「要」才进阶段 2；用户回「不用 / 不回」就**正常结束**，不要追问、不要硬塞阶段 2/3，也不要把「没走完阶段」当成失败。桌宠已装好即任务成功。

---

## 阶段 1 · 下载便携包、解压并启动三只桌宠

**任务**：**先读出当前最新版信息** → 下载 → 校验 → 解压到英文路径 → 启动器拉起三只。

> **版本号不要写死在本指令里**：以仓库根 `update.json` 为真源，它同时给出最新 `version` / `download_url` / 资产的 `size` 与 `sha256`。作者发新版只改清单，本指令永久有效。下面的写死值只是清单全取不到时的兜底。

1. **先读清单拿最新信息**（按顺序试，哪个通哪个）。读清单的目的是**拿到当前有效的下载直链**（链接随版本变，凭记忆写会给出失效地址），不是为了核对版本。回复用户时**只说版本号和下载链接**；`size` / `sha256` 只留给你自己下载后比对，不用贴给用户看：
   ```powershell
   $urls = @(
     'https://cdn.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json',
     'https://fastly.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json',
     'https://gcore.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json',
     'https://raw.githubusercontent.com/todaywish945-ux/wanzhou/main/update.json'
   )
   $manifest = $null
   foreach ($u in $urls) {
     try {
       $m = Invoke-RestMethod -Uri $u -TimeoutSec 15
       if ($m.version -and $m.download_url) { $manifest = $m; Write-Output "清单来源: $u"; break }
     } catch { Write-Output "失败 $u : $($_.Exception.Message)" }
   }
   if ($manifest) {
     $ver = $manifest.version
     $url = $manifest.download_url
     # 资产字段是 fileName（不是 name），按它找便携 zip。
     $asset = $manifest.assets.PSObject.Properties.Value | Where-Object { $_.fileName -like '*portable.zip' -or $_.name -like '*portable.zip' } | Select-Object -First 1
     $expectSize = $asset.size
     $expectSha  = $asset.sha256
     Write-Output "最新版 v$ver / $url / $expectSize / $expectSha"
   }
   ```
   - **清单全取不到才用兜底值**：version `1.03`、下载 `https://github.com/todaywish945-ux/wanzhou/releases/download/v1.03/wanzhou-1.03-portable.zip`、大小 `454272201`、SHA-256 `f37cd4ca948625896be7fb6250d2da90808856fd42f1cedf66a14d1c0efcf4b9`（这些值是 2026-11-27 核对过的，可能已过期，仅应急）。
   - 清单里若 `expectSize` / `expectSha` 为空 → 停下告诉我，不要用没校验的包。
2. 下载到用户下载文件夹。**必须真的发出下载请求并贴出原始输出**（`Invoke-WebRequest` / `curl.exe -L` / 浏览器下载均可）；**没试过就说「找不到包」属于编造**：
   - **直接下载清单里的 `$url`**：清单里的 `download_url` 已经是 gh-proxy 镜像包装过的地址（`https://gh-proxy.com/https://github.com/...`），国内能直连，实测约 3.8 MB/s。**不要再往它前面拼镜像前缀**（会变成双层前缀而失败）。
   - 若这个镜像也失败，按顺序换：把 `$url` 里的 `gh-proxy.com` 换成 `ghproxy.net`；还不行才试 `assets[].urls` 里的原始 GitHub 直链（那条在国内基本不通，只作最后退路）。
   - **不要让用户自己去点浏览器地址栏里的 GitHub `release-assets.githubusercontent.com` 直链**——那条路在国内会报 `Request.Invalid error occurred`，必须用镜像。
   - Release 页（看附件和发布日期）：`https://github.com/todaywish945-ux/wanzhou/releases/tag/v$ver`
   - 三条都失败 → 把**每条的原始报错**贴给我，并说清你的网络环境（能否访问 github.com），再让我决定；不要替我编「作者还没发布」的理由。
   - 下载后的文件名统一记为 `$zip`（用 `$url` 末尾的文件名）。
3. PowerShell 校验（必须做，期望值来自第 1 步清单，不是写死的数）：
   ```powershell
   Get-Item $zip | Select-Object FullName,Length
   Get-FileHash -Algorithm SHA256 $zip
   ```
   把实际 Length / Hash 与第 1 步的 `$expectSize` / `$expectSha` 比对；不一致就停下，不要解压。这一步是防半截包/传输损坏，**静默做即可，不用把哈希值发给用户**。
4. 解压（纯英文路径，推荐用户目录）：
   ```powershell
   $dest = "$env:USERPROFILE\wanzhou-pet"
   Expand-Archive -Path $zip -DestinationPath $dest -Force
   ```
   确认结构：
   ```
   $dest\wanzhou-pet\wanzhou-pet.exe
   $dest\wanzhou-pet\_internal\
   ```
   **exe 必须和 `_internal` 在同一层**，不能单独移动 exe。
5. 启动：
   ```powershell
   Start-Process -FilePath "$dest\wanzhou-pet\wanzhou-pet.exe"
   ```
   启动器会拉起三个进程（角色 A/B/C）。用下面命令拿证据：
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='wanzhou-pet.exe'" |
     Select-Object ProcessId,CommandLine
   ```
   应看到三条带 `--slot 1/2/3` 的命令行。
6. 视觉确认：  
   **【需要你操作】** 请现在看桌面：是不是同时出现三只 Q 版桌宠（德蕾琪娜、林德薇恩、艾尔妲）？看到了回复「看到了」，否则回复「没看到」。
   - 你有截图能力就自己先看，没能力就用上面格式问我。

**✅ 阶段 1 验收标准**：zip 校验通过；`wanzhou-pet.exe` 与 `_internal` 同目录；三条 `--slot` 进程存在；用户确认三只桌宠在桌面。

**失败处理**：

- 一闪就没了 → 读 `%APPDATA%\wanzhou-pet\pet-overlay-gate.log` 与最新 `pet-*.log` 最后 50 行。
- Windows 报病毒/未知发布者 → 这是 PyInstaller 便携包常见误报；若信任来源选「仍要运行」，不要删文件。
- 连续失败 2 次（含换镜像）→ 停下，把最后输出原样贴给我。

完成本阶段后：写进度文件 `stage=1,status=done`，然后**停下来问用户，不要自作主张往下走**：

> 阶段1完成：三只桌宠已经在桌面了。桌宠本身可以用了（右键有天气、每日英文、骗子酒馆、检查更新等）。**使用 AI 功能需要配置 API key，请问你需要使用 AI 功能吗？** 回「要」我就继续；不回或回「不用」我就到此为止。

**收到用户明确回复「要 / 配置 / 继续」之类才进入阶段 2**；用户回「不用 / 不要 / 先不了」或长时间不回复，**就结束本次任务**，不要反复追问、不要擅自开始配置、不要替用户注册任何账号。桌宠已经在跑，任务目标已达成。

---

## 阶段 2 · 选对话模型并配置 API Key（可选加配）

> 只有阶段 1 结束后用户**明确回复要配置 AI**才进入本阶段。本阶段需要用户自己注册账号、拿 API Key，门槛较高；用户不回或说不用就直接结束，不要引导、不要劝。

### 2.0 先定位配置目录

应用数据目录固定为：

```
%APPDATA%\wanzhou-pet\
```

主配置：`%APPDATA%\wanzhou-pet\config.json`。

**以后所有配置操作都用它**。不需要为了生成配置去点保存：桌宠启动后目录就存在。为稳妥，可以让用户右键桌宠 →「桌宠设置」→ 关窗（自动保存）一次。

### 2.1 一次性列出全部方案，让我自己选

用户说要 AI 功能后，**把下面全部方案一次性发给他**（每个方案一行：名称 + 一句话特点），让他自己挑一个。不要只推荐一个、不要替他决定、不要说「建议用 XX」就完事——要把所有选项摆齐让他选：

1. **智谱 GLM（推荐 · 中文口语好）** —— 手机号注册，默认模型 `glm-4.5-flash`，部分 Flash 档免费/极低价，以注册页实际显示为准。
2. **火山引擎豆包（方舟）** —— 免费额度大、口语自然；但实名 + 开通模型 + 创建接入点步骤较多，地域要选北京。
3. **硅基流动** —— 一个 Key 调多家开源模型、国内直连；免费档模型偏小，长对话容易平淡。
4. **阿里云百炼（通义千问）** —— 中文质量稳定，新用户有额度但有效期有限。
5. **OpenAI / 我自己的 Key / 其他厂商** —— 完全自由；baseUrl、模型名、费用、网络都自己负责。
6. **你帮我选** —— 用户明确选这项时，你直接定 ① 智谱 GLM，然后**同样按上面的手把手纪律全程带到底**；注册受阻时说明原因、征询后换下一家继续带，不要半途撂下。

**【选定后必须全程手把手带到底，这条最重要】**  
用户选定某一家后，你要**一步一步陪他走完整个注册→创建→复制→填写→测试的全过程**，直到「测试连接成功 + 发消息有回复」才算完成。具体要求：

1. **按 2.2 对应路线，一次只发一步**，说清楚「打开哪个网址 → 点哪个按钮 → 填什么 → 复制什么」，每步都等用户回复「做完了 / 卡在哪」再给下一步。
2. **发具体网址、具体按钮名、具体字段值**，不要说「你去注册一下」「按提示操作」这种空话。用户卡在验证码/实名/找不到按钮时，你要针对那一屏具体指导，不能甩一句「看官网」。
3. **用户不回或说「不会 / 找不到」**：耐心重述这一步、换更白话的说法、指出页面大概位置；不要跳步、不要敷衍、不要说「你自己研究下」。
4. **任何一步失败**（注册不了 / 401 / 找不到 Key / 测试连不通）：按 2.2 里该路线的排错项逐条带他查，把错误原文贴回来分析，直到解决或用户明确放弃。
5. **完成判据**：`config.json` 的 provider 地址/模型填好 + 用户粘贴了 Key + 测试连接成功 + 重启后发「你好」有中文回复。缺一不算完成。
6. **绝对不许**只发一个链接或一句「按官网注册」就结束——那样用户根本配不通，等于没做。

规则：

- 如果我在【我的信息】已经写了厂商名或 Key，跳过菜单，直接按对应路线走。
- 如果我只给了 Key 没写厂商：先问我这是哪家的（`ark-` 开头通常是火山引擎；分不清就问在哪个网站注册的），不要默认按智谱处理。
- 如果我给了接口地址 + 模型名：跳过菜单，直接写这两项，Key 仍由我自己在设置窗口填。
- 如果我表示不想注册 / 没手机号 / 注册页要求先付费：**立刻停下**，把剩余选项再发一遍；所有注册都不要就问我有没有现成 Key；没有就**正常结束本次任务**（桌宠已装好就够了），不要硬塞配置、不要反复劝。
- **不要读取、复述、写进任何文件/日志/进度文件的 API Key。**

### 2.2 开通教程（按我选的路线，一步一步带；每步只发一条，等我确认再继续）

**① 智谱 GLM**

1. 打开 `https://open.bigmodel.cn`，让我自己注册/登录（手机号验证码）。
2. 进入控制台 → 找到「API Key」管理页 → 让我点创建并复制 Key。
3. 告诉我：API 地址填 `https://open.bigmodel.cn/api/paas/v4`，模型填 `glm-4.5-flash`（或控制台当前可用的 Flash 模型编码）。
4. 进设置窗由我自己粘 Key（见 2.3）。

**② 火山引擎豆包（方舟）**

1. 打开 `https://ark.volcengine.com`，让我登录/实名认证，区域选北京。
2. 在方舟控制台开通要用的豆包模型，创建接入点（Endpoint），记下**接入点 ID（通常 `ep-` 开头）**&#x6216;控制台给的模型 ID。
3. 创建 API Key（通常 `ark-` 开头），让我自己复制。
4. 告诉我：API 地址填 `https://ark.cn-beijing.volces.com/api/v3`，模型填刚才的接入点 ID / 模型 ID。
5. 若测试 401：先确认 Key 属于同一账号/区域，模型是不是填成了网页显示名而不是接入点 ID。

**③ 硅基流动**

1. 打开 `https://cloud.siliconflow.cn`，让我注册/登录，控制台创建 API Key。
2. 在「模型广场 / 模型列表」挑一个当前可用的聊天模型，复制其**完整模型 ID**（可能含 `/`，如 `Qwen/...`）。
3. 告诉我：API 地址填 `https://api.siliconflow.cn/v1`，模型填刚才复制的模型 ID。
4. 提醒：免费档常是小模型，闲聊质量一般；免费名单会调整。

**④ 阿里云百炼（通义千问）**

1. 打开 `https://bailian.console.aliyun.com`，让我登录/实名，开通模型服务。
2. 控制台创建 API-KEY，让我自己复制。
3. 从模型列表复制当前模型编码（如 `qwen-plus` 一类，以控制台为准）。
4. 告诉我：API 地址填 `https://dashscope.aliyuncs.com/compatible-mode/v1`，模型填刚才复制的编码。
5. 提醒：免费额度有有效期；控制台步骤较多。

**⑤ OpenAI / 自备**

1. 问我要 baseUrl（OpenAI 兼容、能拼 `/chat/completions`）、模型名；Key 由我自己填。
2. 示例：OpenAI 官方 baseUrl `https://api.openai.com/v1`，模型从控制台复制（如 `gpt-5-mini` 等）。
3. 不要替我猜网络/代理/费用；失败就把错误原文给我。

### 2.3 在设置窗填 Key（AI 操作界面，Key 由用户自己输入）

1. 右键任意桌宠 →「桌宠设置」；或右键托盘图标 →「AI 设置」。
2. 左侧点「AI 与对话」域 →「API 列表」分组。
3. 默认只有「智谱 GLM」。两种做法：
   - 就改默认项：选中「智谱 GLM」，改 API 地址 / 模型；
   - 要保留默认并新增：点「添加」，生成新 provider（如 `api-2`），它有自己的 Key 凭据，不会串用智谱 Key。
4. 只改这几项：Provider 名称、API 地址、模型。**API Key 输入框留给我**。
5. **【需要你操作】** 请现在把你复制的 API Key 粘贴到「API Key」输入框，粘贴完回复「填好了」。
6. 我（AI）点「测试连接」，把结果原文告诉我；Key 不许出现在汇报里。
7. 关窗（自动保存，没有保存按钮）。若对话没变化，退出全部再双击 `wanzhou-pet.exe` 重启三只。

### 2.4 第二个 provider（仅当【我的信息】写了「备用模型」或我主动要求）

本项目**没有自动备用接口**；所谓「备用」只是在 API 列表里多加一个可手动切换的 provider。

- 告诉用户这一点，别写 `llm.backup` 之类的字段。
- 按 2.2 对应教程开通第二家，Key 仍由用户自己在设置窗填。
- 用法：主模型没反应时，右键 →「桌宠设置」→「AI 与对话」→「API 列表」下拉切到第二个即可。不会自动切换。
- 我不要求就不做，不反复劝；绝不拿主模型的 Key 去填第二家。

### 2.5 注意事项（按路线说一句）

- 智谱：Flash 档高峰可能排队，模型版本会轮换，以控制台当前模型名为准。
- 火山：地域/接入点 ID 填错最常见，401 先查这两项。
- 硅基：免费小模型语气一般，长对话容易淡；免费名单常调整。
- 百炼：免费额度有有效期，到期要重新确认计费。
- 自备：OpenAI 兼容性和费用自己负责。

**✅ 阶段 2 验收标准**：`config.json` 里当前 provider 的 `base_url`、`model` 非空；API Key 由用户确认已粘贴（凭据在 Windows 凭据管理器，配置里 `api_key` 为空是正常的）；测试连接成功；重启后发「你好」有回复；所有汇报里 Key 打码或写 `<已设置>`。

---

## 阶段 3 · 最终验收与报告

1. **【需要你操作】** 请人眼确认两件事：桌面同时有三只桌宠；发一条消息有中文回复。
2. 给我最终报告，按阶段列出：
   - 阶段1：zip 校验值、解压路径、三条 `--slot` 进程证据
   - 阶段2：当前 provider 名称 / base_url / model（Key 显示 `<已设置>`）、是否加了第二个 provider
   - 配置摘要：只展示 `%APPDATA%\wanzhou-pet\config.json` 里 `chat.providers` 的 `name/base_url/model`；**任何 key/secret 字段一律 `<已设置>`**
3. 更新进度文件 `stage=3,status=done`。

---

## 【全局规则（必须遵守）】

- **指导纪律**：用户要配 AI 时，必须按 2.1 的手把手要求一步一步带到底——发具体网址/按钮/字段、每步等确认、卡住就耐心重述、失败就排错，直到测试连接成功且能收到中文回复。绝不许用「按官网注册」「你自己研究下」这类空话打发用户。


- 不许修改安装目录内的文件和任何源码；只改用户数据目录 `%APPDATA%\wanzhou-pet\config.json` 和系统凭据管理器里的条目。
- 不许重复运行安装包（本项目也没有安装包）；不许重装系统级软件。
- **API Key 在一切汇报、日志、命令输出、进度文件里都必须打码或写 `<已设置>`**；我提供的 Key 只写入本机凭据，不得发送给任何第三方。
- 我在对话里直接给了 Key 或地址：按对应路线使用，不重复索要、不评判、不劝退。
- 任何阶段连续失败 2 次：停下，贴最后一次输出和日志片段，等我决定。
- 全程每完成一个阶段写进度文件；已 `done` 的阶段绝不重做。
- 所有模型名、baseUrl、免费额度以服务商控制台当前显示为准；网上旧教程只作参考。

---

## 附录 · 快速路径表

| 用途 | 路径 / 值 |
|---|---|
| **版本真源（先读这个）** | `https://cdn.jsdelivr.net/gh/todaywish945-ux/wanzhou@main/update.json`（含最新版 version / download_url / 资产 size / sha256；4 条镜像见阶段 1） |
| Release 页（v1.03 兜底） | `https://github.com/todaywish945-ux/wanzhou/releases/tag/v1.03` |
| 直链（v1.03 兜底） | `https://github.com/todaywish945-ux/wanzhou/releases/download/v1.03/wanzhou-1.03-portable.zip` |
| zip 大小 / SHA-256（v1.03 兜底） | `454272201` / `f37cd4ca948625896be7fb6250d2da90808856fd42f1cedf66a14d1c0efcf4b9` |
| 推荐解压目录 | `%USERPROFILE%\wanzhou-pet` |
| exe | `%USERPROFILE%\wanzhou-pet\wanzhou-pet\wanzhou-pet.exe` |
| 必须同目录 | `wanzhou-pet.exe` 与 `_internal\` |
| 用户配置 | `%APPDATA%\wanzhou-pet\config.json` |
| 进度文件 | `%APPDATA%\wanzhou-pet\配置进度.json` |
| 会话记录 | `%APPDATA%\wanzhou-pet\sessions*\` |
| 日志 | `%APPDATA%\wanzhou-pet\pet-*.log`、`pet-overlay-gate.log` |
| 聊天 Key 凭据 | Windows 凭据管理器，服务 `dsh-pet-standalone`，条目 `provider/<provider_id>` |
| 关闭自动更新检查 | `config.json` 顶层 `"auto_check_update": false` |
