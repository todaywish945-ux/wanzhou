# 给 AI 助手的全流程安装指令模板

> 配套「挽昼桌宠」v1.00 便携版使用。
> 用户不需要懂代码、不需要装 Python：把下面的指令卡**按顺序**复制给 AI 助手（能操作电脑/浏览器的那种），AI 负责下载、解压、启动、填配置；**只有必须本人做的事才让用户做**。
>
> 本提示词基于 v1.00 真实发布物与配置路径核对过：Release 附件、exe 启动器、右键菜单名、`%APPDATA%\wanzhou-pet\config.json`、智谱 GLM 默认参数。
> 相关的发布与更新说明见 [`README.md`](README.md)。

---

## 使用说明（先读）

1. 假设用户电脑是 **Windows 10/11 64 位**。所有 `<尖括号>` 处替换成真实值。
2. **按 卡0 → 卡1 → 卡2 → 卡3 → 卡4 顺序执行**，不要跳步。卡4.5（换模型）、卡5/卡6 可选，卡7 是排障，卡8 是懒人总指令。
3. 每张卡都有「✅ 成功标准」。AI 每完成一步，必须**贴出证据**：命令输出、文件路径、窗口标题，或截图（如果你有截图能力）。
4. **AI 的行为边界**：
   - 能自己做的（下载、校验、解压、运行、改配置、点按钮、读日志）全部自己做。
   - **只有这些必须让用户做**：注册/登录网站、短信/邮箱验证码、实名认证、创建并复制 API Key、同意用户协议、付费确认、以及任何需要账号密码的操作。
   - 需要用户操作时，用固定格式说：
     > **【需要你操作】** 请现在做：…… 做完回复「继续」。
     用户回复前不要往下走，也不要替用户猜 Key。
5. 不建议让用户把 API Key 贴在聊天里；更推荐用户**自己在设置窗里输入**，避免 Key 留在对话记录中。若用户坚持贴给你，填完后不要再复述这个 Key。
6. 出问题先走卡7，不许重装系统、不许改源码、不许删除 `%APPDATA%\wanzhou-pet` 里的配置。

---

## 卡0 · 下载发布包并校验（AI 全自动）

**📋 给 AI 的指令（复制）**

```text
请帮我下载挽昼桌宠 v1.00 的便携包并安装准备。你来做，不用问我技术细节。

1. 用 PowerShell 下载：
   $url = "https://github.com/todaywish945-ux/wanzhou/releases/download/v1.00/wanzhou-1.00-portable.zip"
   $zip = "$env:USERPROFILE\Downloads\wanzhou-1.00-portable.zip"
   Invoke-WebRequest -Uri $url -OutFile $zip
2. 校验文件（必须做）：
   Get-Item $zip | Select-Object FullName,Length
   Get-FileHash -Algorithm SHA256 $zip
   期望大小：405253253 字节
   期望 SHA-256：7ce737d07b4b9ab7e2e2906fb91f61f09836466102b73c8b829383dd194a15a0
   不一致就停下来告诉我，不要继续解压。
3. 校验通过后告诉我：文件完整、路径和大小。

注意：这是绿色便携包，没有 setup.exe、不需要安装向导、不需要 Python。
```

**✅ 成功标准**：文件大小和 SHA-256 与上面一致。

**⚠️ 失败时补一句**：「网络慢就多等一会儿；若 GitHub 直连失败，把 Release 页 `https://github.com/todaywish945-ux/wanzhou/releases/tag/v1.00` 发给我，让我自己在浏览器里下载后告诉你新文件路径。」

---

## 卡1 · 解压并启动三只桌宠（AI 全自动，用户只做视觉确认）

**📋 给 AI 的指令（复制）**

```text
发布包已下载在 <卡0 得到的 zip 路径>。请继续：

1. 解压到一个纯英文路径，推荐：
   $dest = "$env:USERPROFILE\wanzhou-pet"
   Expand-Archive -Path "<zip 路径>" -DestinationPath $dest -Force
   解压后目录结构应是：
   <dest>\wanzhou-pet\wanzhou-pet.exe
   <dest>\wanzhou-pet\_internal\
2. 确认 exe 和 _internal 在同一层目录。不要把 exe 单独移走——移走就跑不起来。
3. 启动：
   Start-Process -FilePath "$dest\wanzhou-pet\wanzhou-pet.exe"
4. 启动器会拉起三个独立进程（角色 A/B/C），桌面上应该同时出现三只桌宠。
   如果你有截图能力就自己看；没有就按下面格式让我确认。

【需要你操作】请现在看桌面：是不是同时出现了三只 Q 版桌宠（德蕾琪娜、林德薇恩、艾尔妲）？
看到了回复「看到了」，没看到回复「没看到」。
```

**✅ 成功标准**：桌面三只都在；任务栏/托盘有应用图标；exe 路径与 `_internal` 同目录。

**⚠️ 失败时补一句**：
- 「没看到三只」→ 检查是否把 exe 单独复制出去；重新完整解压再启动。
- 「Windows 提示病毒/未知发布者」→ 这是 PyInstaller 便携包常见误报，若你信任来源请选择「仍要运行」；不要删文件。
- 「一闪就没了」→ 读 `%APPDATA%\wanzhou-pet\pet-overlay-gate.log` 和最新的 `pet-*.log` 最后 50 行，把报错贴给我，不要重装。

---

## 卡2 · 注册智谱账号并拿到 API Key（必须用户参与）

> 桌宠默认使用智谱 GLM（`https://open.bigmodel.cn/api/paas/v4`，模型 `glm-4.5-flash`）。没有 Key 时三只桌宠照常显示，但 AI 对话不会回复。
> 注册、登录、验证码、创建 Key 是账号操作，AI 不能替你完成，必须让用户做。

**📋 给 AI 的指令（复制）**

```text
现在要拿到 AI 对话用的 API Key。大部分是账号操作，需要我本人做，请你一步步指导我，不要替我猜。

1. 打开浏览器到 https://open.bigmodel.cn
2. 【需要你操作】请现在自己注册/登录智谱开放平台（可能要手机号验证码、实名认证）。
   完成后回复「登录好了」。
3. 登录后进入控制台，找到「API Key」管理页（不同版本可能在「我的密钥 / API 密钥」下）。
   【需要你操作】请自己点「创建新的 API Key」，复制生成的 Key。
   为了不把 Key 留在聊天记录里，请**先不要贴给我**，等下一步我让你直接填进桌宠设置窗。
   完成后回复「Key 已复制」。
4. 告诉我你已经拿到 Key 了；接下来走卡3。
```

**✅ 成功标准**：用户确认已登录智谱并复制了 API Key（Key 本身不必出现在对话里）。

**⚠️ 失败时补一句**：「如果找不到 API Key 页面，把当前控制台截图/页面文字发我，我按你看到的内容告诉你点哪里；不要去改桌宠源码。」

---

## 卡3 · 把 Key 填进桌宠并测试连接（AI 操作界面，用户只填 Key）

> 桌宠设置窗里 API Key 会存到 **Windows 凭据管理器**（服务名 `dsh-pet-standalone`，条目 `provider/openai-main`），不写进明文配置；设置是自动保存的，没有保存按钮。

**📋 给 AI 的指令（复制）**

```text
Key 已经拿到了。请你操作桌宠界面把它填进去并验证，Key 让我自己输入。

1. 右键任意一只桌宠 →「桌宠设置」；或者右键托盘图标 →「AI 设置」。
2. 在设置窗左侧点「AI 与对话」域。找到「模型与连接」分组，确认：
   Provider 名称：智谱 GLM
   Base URL：https://open.bigmodel.cn/api/paas/v4
   模型：glm-4.5-flash
   API Key：先留空，等我输入。
   这些默认值不要改，除非我明确说要用别的模型服务。
3. 【需要你操作】请现在把刚才复制的 API Key 粘贴到「API Key」输入框里，粘贴完回复「填好了」。
   如果输入框把 Key 显示成圆点，是正常的。
4. 你（AI）点击「测试连接」，等结果。
   成功：告诉我「测试连接通过」。
   失败：把窗口里显示的报错原文读给我，不要自己改配置或重装。
5. 关掉设置窗（关闭即自动保存，不需要保存按钮）。

注意：不要把 Key 写进 README、update.json 或任何项目文件；不要把它贴回聊天里。
```

**✅ 成功标准**：「测试连接」显示成功；设置窗已关闭；`%APPDATA%\wanzhou-pet\config.json` 里 `chat.providers` 下当前 provider 存在但 `api_key` 为空（凭据在 Windows 凭据管理器里，这是正常的）。

**⚠️ 失败时补一句**：
- 「测试连接 401 / 无效 Key」→ 让用户回智谱控制台确认 Key 是否复制完整、是否停用。
- 「读不到凭据」→ 说明系统钥匙串不可用；这时配置会自动退化为明文保存，仍可先用；不要反复删配置。
- 「找不到 AI 与对话」→ 用托盘「AI 设置」直接进入 AI 设置对话框，效果一样。

---

## 卡4 · 验收对话与常用设置（AI 操作 + 用户确认效果）

**📋 给 AI 的指令（复制）**

```text
配置完了，请按下面顺序验收，每一步都报告结果：

1. 右键任意一只桌宠 →「AI 对话」，打开聊天窗。
2. 【需要你操作】请在聊天窗发一句「你好」，看她是否回复。
   有回复回复「通过了」，没回复回复「没反应」。
3. 如果你有截图能力，确认三只桌宠都还在桌面上、没有被聊天气泡挡住后消失。
4. 试一下右键菜单能不能打开：「桌宠设置」「检查更新」「天气」「每日英文」这几项点开不报错即可，不用真的改。
5. 告诉我当前版本：右键 →「工具与帮助」→「检查更新」，气泡应显示「已经是最新版本（1.00）」。

全部通过后给我一份清单：三只是否出现、对话是否通、菜单是否正常、版本是否正确。
```

**✅ 成功标准**：三只桌宠在；发「你好」有中文回复；右键菜单可打开；检查更新显示 1.00 已是最新。

**⚠️ 失败时补一句**：「对话没反应先回卡3 重测连接；菜单点了没反应先看是不是桌宠被隐藏了，从托盘恢复。」

---

## 卡4.5 · 换成其他模型服务（可选）

> 为什么默认是智谱：项目出厂只预置了一个 provider（`openai-main` = 智谱 GLM），这样小白用户只需要注册一个账号。
> 但设置页支持**添加多个 provider**，每个都有自己的 API 地址和 Key 凭据，切换时选中对应项即可。下面这张卡只在用户明确想换模型时执行。

**📋 给 AI 的指令（复制）**

```text
我不想用默认智谱，想换成 <服务名，例如 DeepSeek / OpenAI / 其他 OpenAI 兼容服务>。
请你操作设置窗，不要改项目源码：

1. 右键桌宠 →「桌宠设置」→ 左侧「AI 与对话」域 →「API 列表」分组。
2. 点「添加」，系统会复制当前 provider 生成一个新项（如 api-2），并自动选中它。
3. 只改这四项，其他都不动：
   Provider 名称：<服务名>
   API 地址：<见下方对照表>
   模型：<见下方对照表>
   API Key：让我自己输入。
4. 【需要你操作】请现在把你在这个服务官网拿到的 API Key 粘贴到「API Key」输入框，完成后回复「填好了」。
5. 你点「测试连接」，把结果原文告诉我。通过后关闭设置窗（自动保存）。
6. 以后想切回智谱：在「API 列表」下拉里选「智谱 GLM」即可，Key 不会丢。
```

**常见服务对照表**

| 服务 | Provider 名称 | API 地址（填在「API 地址」框） | 低价/入门模型 | 高强度/付费模型示例 | Key 从哪来 |
|---|---|---|---|---|---|
| 智谱 GLM（默认） | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4.5-flash`（Flash 档，免费/极低价，以控制台为准） | 旗舰/Plus 档，如控制台「模型概览」里标为旗舰的模型编码 | bigmodel.cn |
| DeepSeek | DeepSeek | `https://api.deepseek.com/v1` | `deepseek-flash` / 旧名 `deepseek-chat`（低价，仍按量计费） | `deepseek-v4-pro`（高强度、更贵，官方当前在售） | platform.deepseek.com |
| OpenAI | OpenAI | `https://api.openai.com/v1` | `gpt-5-mini`（低价档，按量计费） | `gpt-5.5`（旗舰档，明显更贵） | platform.openai.com |
| 其他兼容服务 | 自定义 | 服务商给的 Base URL（通常带 `/v1`） | 服务商给的入门模型 ID | 服务商给的旗舰模型 ID | 服务商控制台 |

> **「免费」要说清楚**：表里 Flash / mini 档不是统一免费；智谱部分 Flash 模型可免费调用，DeepSeek/OpenAI 的低价档也是**按量计费，只是单价低**。想用旗舰/推理模型，必须先到服务商控制台确认余额、模型名和价格，别直接照抄网上的旧教程。模型名会变，**一律以控制台「模型概览 / 模型列表」里能复制的模型编码为准**。

**付费/高强度模型的额外设置**（用户明确要更强效果时再做）：
1. 在「AI 与对话」域找到「深度思考」：选「开启深度思考」；思考强度按需要选低/高/最大。
2. 「最大输出 Token」建议调到 `8192` 以上；思考过程也计入输出，太小会被截断。
3. 旗舰模型更慢、更贵；先让用户设好服务商账单/余额上限，再测试连接。
4. 视觉模型（「看看屏幕」）是另一条配置：设置里「视觉模型复用聊天模型」默认开；若聊天换成不支持视觉的付费模型，要单独填视觉模型地址与模型 ID（如智谱 `glm-4.6v-flash`），否则「看看屏幕」会失败。

**✅ 成功标准**：新 provider 出现在「API 列表」下拉里；选中它时「测试连接」成功；关窗后卡4 的对话验收仍能通过。

**⚠️ 失败时补一句**：
- 「测试连接认证失败」→ 确认 Key 是否复制完整、是否属于同一个服务；不要把智谱 Key 填到 DeepSeek 里。
- 「404 / 路径不对」→ 把 API 地址结尾补上 `/v1` 再试；智谱本身带 `/v4`，不要再加 `/v1`。
- 「想删掉刚加的项」→ 在「API 列表」点「删除」，但至少保留一个 provider。

---

## 卡5 · 可选设置（用户说要再做）

**📋 给 AI 的指令（复制）**

```text
基础功能已经通了。现在按我的要求做这些可选设置（没提到的不要动）：

- 开机自启：右键任意桌宠 →「桌宠控制」→「开机自启」，打开。
- 想让三只更小/更大：右键 →「大小」，按我说的档位调。
- 不想全屏看视频时被隐藏：右键 →「桌宠设置」→「显示」→ 关掉「全屏自动隐藏」。
- 想让桌宠不跟着鼠标穿插：右键 →「桌宠设置」→「动作与碰撞」→ 调整多开碰撞。
- 想恢复隐藏的桌宠：右键托盘图标 →「显示 / 隐藏」。
- 想退出：右键 →「退出」；或者只退一只用托盘对应项。

做完逐项告诉我结果。
```

---

## 卡6 · 通用排障模板（万能卡）

**📋 给 AI 的指令（复制）**

```text
桌宠出问题了。现象：<一句话描述，例如"三只没出来"/"对话不回复"/"点设置没反应">。

请你按这个流程处理：
1. 先确认 exe 和 _internal 是否还在同一目录：<dest>\wanzhou-pet\。
2. 读 %APPDATA%\wanzhou-pet\ 下最新的 pet-*.log 最后 50 行，以及 pet-overlay-gate.log 最后 20 行。
3. 从日志定位直接原因，用中文向我复述你的判断，不要先动手。
4. 提出最小修复方案，等我回复「可以」后再做。
5. 修完按卡4 的四项标准重新验收。

禁止：重装系统软件、删除整个 %APPDATA%\wanzhou-pet、改项目源码、把 Key 贴到聊天里。
```

**常见现象 → 先查什么**
- 三只没出来 → exe 是否被单独移走；`pet-overlay-gate.log` 是否写了拒绝原因
- 对话不回复 → 卡3 的 Key/测试连接；配置是否被新版本重置
- 更新提示一直不出现 → 右键「检查更新」手动查；确认 `update.json` 版本大于 1.00
- 窗口不见了 → 托盘右键「显示 / 隐藏」；不要重复双击 exe 造成多开

---

## 卡7 · 一键总指令（懒人版）

> 适合已经拿到 Key、想一口气跑完的人。AI 每完成一步停下来向你汇报证据，任何一步失败就停。

```text
项目是挽昼桌宠 v1.00 便携版，请按顺序执行，每完成一步向我汇报证据后再继续：

第1步 下载并校验：
  下载 https://github.com/todaywish945-ux/wanzhou/releases/download/v1.00/wanzhou-1.00-portable.zip
  到 $env:USERPROFILE\Downloads，大小应为 405253253 字节，
  SHA-256 应为 7ce737d07b4b9ab7e2e2906fb91f61f09836466102b73c8b829383dd194a15a0。
第2步 解压启动：
  解压到 $env:USERPROFILE\wanzhou-pet，运行其中的 wanzhou-pet\wanzhou-pet.exe。
  让我确认桌面出现三只桌宠。
第3步 拿 Key：
  打开 https://open.bigmodel.cn，指导我登录并创建 API Key；
  让我自己在设置窗输入，Key 不进聊天记录。
第4步 填 Key 并测试：
  右键桌宠 →「桌宠设置」→「AI 与对话」→ 粘贴 Key →「测试连接」，报结果。
第5步 验收：
  发「你好」看回复；检查右键菜单；检查更新显示 1.00。

最后给我清单：每步结果 + 当前 exe 完整路径 + 是否三只都出现。
```

---

## 附录A · 路径与名称速查

| 项目 | 值 |
|---|---|
| 发布页 | `https://github.com/todaywish945-ux/wanzhou/releases/tag/v1.00` |
| 直链 | `https://github.com/todaywish945-ux/wanzhou/releases/download/v1.00/wanzhou-1.00-portable.zip` |
| 包大小 / SHA-256 | `405253253` / `7ce737d07b4b9ab7e2e2906fb91f61f09836466102b73c8b829383dd194a15a0` |
| 推荐解压目录 | `%USERPROFILE%\wanzhou-pet` |
| exe 路径 | `%USERPROFILE%\wanzhou-pet\wanzhou-pet\wanzhou-pet.exe` |
| 必须同目录 | `wanzhou-pet.exe` 和 `_internal\` |
| 用户配置目录 | `%APPDATA%\wanzhou-pet\` |
| 主配置 | `%APPDATA%\wanzhou-pet\config.json` |
| 会话记录 | `%APPDATA%\wanzhou-pet\sessions*\` |
| 更新状态 | `%APPDATA%\wanzhou-pet\updates\auto-check.json` |
| 日志 | `%APPDATA%\wanzhou-pet\pet-*.log`、`pet-overlay-gate.log` |
| Key 存储 | Windows 凭据管理器，服务 `dsh-pet-standalone`，条目 `provider/openai-main` |

## 附录B · 默认模型参数（不要随便改）

| 字段 | 默认值 |
|---|---|
| Provider | 智谱 GLM |
| Base URL | `https://open.bigmodel.cn/api/paas/v4` |
| Chat path | `/chat/completions` |
| 模型 | `glm-4.5-flash` |
| 请求超时 | 60 秒 |
| 最大输出 Token | 2048 |

如果用户明确要用其他 OpenAI 兼容服务（DeepSeek、OpenAI、智谱旗舰档等），按卡4.5 添加 provider，只改 Provider 名称 / Base URL / 模型 / Key；选高强度付费模型时再按卡4.5 的「付费/高强度模型的额外设置」调深度思考与最大输出 Token。**不要改 chat_path、超时等默认字段**；模型名一律以服务商控制台当前编码为准。

## 附录C · 版本与提醒

- 当前版本 **1.00**；已经是 1.00 的用户不会收到更新提示，这是正常的。
- 老用户收到新版通知的前提：仓库 `update.json` 的 `version` 大于 1.00，且已提交到 main 分支。
- 关闭自动检查：在 `%APPDATA%\wanzhou-pet\config.json` 顶层写 `"auto_check_update": false`。

## 附录D · 本提示词的核对来源

- 发布资产：GitHub Release `v1.00` 的 `wanzhou-1.00-portable.zip` 附件
- 启动器：`packaging/pet_entry.py`（无 `--slot` 时拉起 slot 1/2/3 三个进程）
- 设置入口：`pet/context_menus/registry.py`（「桌宠设置」「检查更新」）与 `pet/app.py`（托盘「AI 设置」）
- 配置字段：`pet/chat/models.py`（ProviderConfig / ChatSettings 默认值）
- 凭据存储：`pet/chat/models.py::SecretStore`（keyring，服务名 `dsh-pet-standalone`）
- 自动更新：`pet/updater.py` + 仓库根 `update.json`
