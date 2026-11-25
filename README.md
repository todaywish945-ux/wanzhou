# 晚昼桌宠

三个 Q 版桌宠，对应《绝区零》「挽昼」三姐妹——德蕾琪娜（小妹）、林德薇恩（二姐）、艾尔妲（大姐）。角色素材来自 X 用户 [@mask_robot](https://x.com/mask_robot/status/2123840697035878568) 的 Sunbriggers 表情包（AI 超分 2 倍 + 透明背景处理），框架移植自开源项目 [MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)（MIT，感谢原作者与上游 PC2005-cloud/dsh-pet），动画保留本项目的 GIF 表情路线。

三位桌宠的人设（身份、性格、说话风格）写在各自的 `assets/characters/角色X/manifest.json` 的 `chat.system_prompt` 里，AI 对话会按角色读取；显示名同在该文件的 `name` 字段。角色身份为同人设定，仅用于桌宠陪伴与对话，版权归米哈游。

## 启动

双击对应 bat（三只可同时运行，互不干扰）：

- `启动-角色A.bat` —— **德蕾琪娜·挽昼**（小挽昼，算理中枢局总务官；待机 / 欢呼 / 开心 / 犯困）
- `启动-角色B.bat` —— **林德薇恩·挽昼**（中挽昼，空域巡戍局总务官；待机 / 大笑 / 震惊 / 生气）
- `启动-角色C.bat` —— **艾尔妲·挽昼**（大挽昼，罗斯凯利法最高执政官；待机 / 微笑 / 不满 / 汗颜）

每只进程占独立配置档案（`--slot 1/2/3`），位置、缩放、角色各自记忆，互不覆盖。

三只同时运行时**身体会互相碰撞**：可以拖着互撞、把一只甩到另一只身上；锁定位置的桌宠作为固定障碍，隐藏的桌宠自动退出碰撞。开关与弹力/摩擦/体重/撞击力度/音效在「桌宠设置 → 动作与碰撞 → 多开碰撞」。

## 交互（移植自 dsh-pet 框架，比旧版丰富很多）

| 操作 | 效果 |
|---|---|
| 左键单击 | 点击回应动画 + 气泡 + 可选音效 |
| 按住拖动 | 移动；松手有**惯性**，快速甩出会**抛掷飞行**（弹道物理） |
| 右键 | 完整菜单：AI 对话 / 骗子酒馆 / 表情 / 大小 / 天气 / 每日一签 / 开机自启 / 设置 |
| 滚轮/菜单 | 缩放（脚底锚定，不飘） |
| 托盘图标 | 右键菜单；桌宠找不到时从这里找回 |

窗口置顶有**看门狗**（资源管理器重启/休眠唤醒后自动恢复置顶）；全屏看视频时自动隐藏（可在设置关）；「直播捕获兼容模式」可让 OBS/直播姬的窗口捕获列表看到桌宠。

设置窗口每个页头右上角都有「功能地图 · 找不到设置？」（或按 `Ctrl+K`）：按域名、页内标签、分组逐层浏览全部设置，也能直接搜「网速」「开机启动」这类口语说法，双击结果就跳回原来的设置位置。

设置改动会**自动保存**：停止操作约 0.7 秒后落盘，侧栏下方显示「已自动保存」；直接关窗（X / Esc）也会保存，设置里没有单独的保存按钮。每只桌宠的设置各自独立（如点击黄金回旋），自动保存失败时会显示状态，关窗时再按原逻辑询问是否放弃改动。

## 右键菜单功能

- **🃏 骗子酒馆**：启动 `../骗子酒馆/liar_game.py` 牌局，三只桌宠自动入座、按牌局事件做表情、散场回原位（协议沿用旧版 `联动事件.json`）。
- **AI 对话**：OpenAI 兼容接口（默认智谱 GLM）。首次使用：菜单 → AI 设置 → 粘贴 API Key → 测试连接。支持流式输出、多会话、按角色隔离。
- **天气**：中国天气网 / open-meteo，免 API Key，右键 → 天气。
- **每日一签**：同一天必得同一支（日期种子），可配 TTS 念签文。
- **点击音效**：winmm 直放 wav，可在设置开关。

## 配置与数据

- 数据目录：`%APPDATA%\wanzhou-pet\`（config.json 全局 + `config-slot-N.json` 每宠档案 + `sessions/` 聊天会话）
- 角色：`assets/characters/<角色ID>/`，`videos/idle|click|random/` 放 GIF，`manifest.json` 写显示名；放进 `%APPDATA%\wanzhou-pet\characters\<新角色>\` 可**热加载**（右键菜单重开即见）
- 日志：同目录 `pet-*.log`（7 天自动清理）

## 环境

- Python 3.13 + **PySide6**（venv 已装好，依赖见 `requirements.txt`）
- 手动运行：`venv\Scripts\pythonw.exe -m pet --slot 1 --instance A --character A`（B/C 换 2/B/B、3/C/C）
- 测试：`$env:QT_QPA_PLATFORM="offscreen"; venv\Scripts\python.exe -m pytest -q tests`

## 从旧版（300 行单文件版）迁移

- 旧 `设置_角色X.json` 的位置/缩放不再读取，启动后重新摆放一次即可。
- GIF 素材已迁移到 `assets/characters/<角色>/videos/` 布局；`gif/` 目录保留一份原素材备份。
- 框架裁剪说明：overlay 灵动岛 / 音乐歌词桌面 / 待办 / 节日 / WebM 动画栈未随移植携带（`pet/_removed.py` 提供惰性桩，feature 门永不激活）。DeepSeek / DSH Harness / Agent 联动相关功能已移除，项目专注于绝区零桌宠与 AI 对话。主动识屏（`pet/proactive/`）可用但默认关闭，相关配置在「桌宠设置」中开启。

## 发布与更新

**已经下载过的用户怎么收到新版**：客户端启动时过 10 秒查一次，运行中每 12 小时再查（三只桌宠共用 `%APPDATA%\wanzhou-pet\updates\auto-check.json`，全产品一天只查一次）。有新版会弹右下角可点击通知 + 桌宠气泡，点开就是更新窗，里面直接显示百度网盘链接和提取码，点「打开下载页」就能去下新版压缩包。同一版本只打扰一次，三天后才再提醒；右键菜单「检查更新」任何时候都能手动查。不想自动查可在 `config.json` 顶层写 `"auto_check_update": false`。

- 发布仓库：[todaywish945-ux/wanzhou](https://github.com/todaywish945-ux/wanzhou)。**版本真源是仓库根目录 `update.json`**（jsDelivr 三条镜像），GitHub Releases API 只在清单全取不到时兜底——仓库里遗留的上游 v4.4.x Tag 不能拿来当本项目版本。
- 发 exe：① 同步改 `pet/__init__.py::__version__` 与 `update.json.version`；② 装构建依赖 `venv\Scripts\python.exe -m pip install -r scripts\requirements-build.txt`，跑 `powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1`；③ 得到 `dist\wanzhou-<版本>-portable.zip`（里面是 `wanzhou-pet\` 目录 + `wanzhou-pet.exe`），传百度网盘；④ 跑 `python scripts/make_update_manifest.py --version <版本> --notes "更新说明" --download-url "https://pan.baidu.com/s/xxx" --download-code <提取码> --archive dist\wanzhou-<版本>-portable.zip` 写回清单；⑤ 代码推 main，在 GitHub 建 `v<版本>` Release（正文贴网盘链接+提取码），提交 `update.json` 到 main，等 jsDelivr 同步几分钟。完整步骤见 `update.json` 的 `_publish_steps`。
- 用户解压后**双击 `wanzhou-pet.exe` 就会同时出现三只桌宠**：这个 exe 是启动器，会拉起三个独立进程（slot 1/2/3 = 角色 A/B/C），各自记位置、缩放和设置；三个进程共用一个托盘区。不需要 Python、不需要 venv、不需要 bat。
- 这是绿色便携包，不是 Inno Setup 安装包：没有自动覆盖安装，`update.json.assets` 里是便携 zip 而非 exe 安装器，所以「下载并安装」按钮禁用，用户走「打开下载页」手动下载解压；通知与提取码仍然自动送到。

## 参考与许可

- 框架：[MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)（MIT），本地参考副本在 `../_参考/dsh-pet-indesktop`
- 素材：[@mask_robot](https://x.com/mask_robot/status/2123840697035878568)
