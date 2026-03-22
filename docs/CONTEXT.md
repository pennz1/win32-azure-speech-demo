# CONTEXT — Azure AI 语音演示台

## 项目概述
Windows x86-64 桌面 Demo（.exe），面向售前工程师向客户演示 Azure AI 语音能力。
Flet (Material Design 3) 深色/浅色/跟随系统主题可切换，Azure 蓝 #0078D4。

## 技术栈
| 层级 | 选型 |
|------|------|
| UI | Flet **0.82+** (MD3 深色/浅色/跟随系统可切换) |
| 语音转写 | azure-cognitiveservices-speech ≥1.37 (ConversationTranscriber + Diarization) |
| AI 纪要 | openai SDK → Azure OpenAI GPT-4o (stream) |
| 实时对话 | openai SDK (beta.realtime) → Azure OpenAI GPT-4o Realtime (WebSocket) |
| 录音 | sounddevice + scipy → 16kHz mono .wav |
| 配置加密 | cryptography (Fernet)，密钥 ~/.azure_ai_demo/.encryption_key |
| 打包 | `flet pack`（底层 PyInstaller），也可手动 `pyinstaller build.spec` |
| 安装包 | NSIS 3.11（安装向导 + 开始菜单 + 桌面快捷方式 + 卸载） |
| Python | 开发/打包：**3.14**（当前 Windows 环境），兼容 3.11+ |

## 文件结构
```
├── main.py                  # Flet 入口，壳层 + Tabs + 设置弹窗
├── transcription_tab.py     # Tab 1: 录音转写 + AI 纪要
├── interpreter_tab.py       # Tab 3: 同声传译 Live Interpreter
├── realtime_tab.py          # Tab 2: Voice Live 实时语音对话
├── audio_recorder.py        # 麦克风录音器 (sounddevice, 16kHz)
├── config_manager.py        # 加密配置读写 (Fernet)
├── app_paths.py             # 统一路径：dev 模式 / PyInstaller frozen
├── config.json              # 运行时加密配置（.gitignore 已排除）
├── requirements.txt         # 依赖清单（flet>=0.82.0）
├── build.spec               # PyInstaller 打包配置（含 flet pack 推荐命令）
├── AzureAISpeechDemo.spec   # PyInstaller 自动生成的 spec（含 ICO 支持）
├── installer.nsi            # NSIS 安装包脚本（安装向导/快捷方式/卸载）
├── build_installer.ps1      # 一键构建脚本（exe + 安装包）
├── README.md                # 项目 README（新增）
├── .github/workflows/       # GitHub Actions Windows 打包
├── Azure_AI_Demo_PRD_v2.0.md
├── ISSUES.md                # 问题追踪
└── CONTEXT.md               # ← 本文件
```

## 模块总览
| 模块 | 状态 |
|------|------|
| 主应用壳层 + 导航框架 | ✅ 已完成 |
| Tab 1 录音转写 + AI 会议总结 | ✅ 已完成 |
| Tab 2 VoiceLive 实时语音对话 | ✅ 已完成 |
| Tab 3 同声传译 Live Interpreter | ✅ 已完成 |

## 主应用壳层 — 已完成
- Flet 暗色主题 + 三 Tab 导航（会议转写 & 总结 / 实时对话 VoiceLive / 同声传译）
- 顶部标题栏 + ⚙️ 设置按钮 + 🌗 主题切换
- 底部状态栏（Azure 连接状态绿/黄/红 + 区域 + 版本）
- **主题切换**（v2.0.0322.4）：深色/浅色/跟随系统三种模式循环切换，图标按钮形式（🌙/☀️/◑），点击立即生效，偏好持久化到 config.json `theme_mode` 字段
- **浅色主题专项优化**（v2.0.0322.7）：
  - 全面替换硬编码深色 hex 颜色为 Flet MD3 ColorScheme token（`ft.Colors.SURFACE_CONTAINER`、`ft.Colors.OUTLINE_VARIANT` 等），深浅主题自动适配
  - 浅色主题配置独立 `ColorScheme`：强化 `on_surface` 对比度（#1a1a1a 近黑）、surface 层级清晰（#f5f6fa 页面 / #eaebf0 容器 / #ffffff 最低层）、`outline` 可见边框（#c4c7cc）
  - 卡片/面板添加 `border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)` 边框，浅色主题下视觉层级清晰
  - AI 会议纪要区域添加 `border=ft.Border(left=ft.BorderSide(3, ft.Colors.PRIMARY))` 左侧主色标记，一眼识别 AI 输出
  - 对话气泡使用 scheme 色：用户气泡 `PRIMARY_CONTAINER`、AI 气泡 `TERTIARY_CONTAINER`（含左侧 `TERTIARY` 边框），深浅主题均可读
  - 次要按钮（复制/导出/选择文件/转写文件）统一使用 `SURFACE_CONTAINER_HIGH` + `ON_SURFACE` 色，避免浅色主题下灰色按钮不可读
  - Banner 使用 `SECONDARY_CONTAINER` / `ERROR_CONTAINER`，自动适配主题
  - 状态栏使用 `SURFACE_CONTAINER`，同步适配
- 设置弹窗：Speech Key / **部署区域 Region**（紧随 Speech Key 下方）/ OpenAI Endpoint+Key+Deployment / **Voice Live Endpoint+Key** / Region
- config_manager.py：Fernet 加密 API Key，config.json 持久化
- app_paths.py：统一支持 dev 模式与 PyInstaller frozen 模式

## Tab 1 录音转写 & AI 纪要 — 已完成
- F1-01 音频文件上传（FilePicker async, .wav/.mp3/.m4a）
- F1-02 实时麦克风录制（sounddevice → 16kHz mono .wav）
- F1-03/04 Azure Speech 转写 + Diarization（ConversationTranscriber）
- F1-05 转写进度条（indeterminate → 完成 100%）
- F1-06 转写结果：Speaker 彩色气泡卡片 + 时间戳，ListView 自动滚动
- F1-07/08 GPT-4o 流式纪要生成（结构化 Markdown）
- F1-09 一键复制到剪贴板（Clipboard 控件）
- F1-10 导出 .txt（转写原文 + 纪要）
- F1-11 配置状态 Banner（4 态：全配置 / 仅 Speech / 仅 OpenAI / 未配置）
- **Word-level 时间戳**（v2.0.0322.9）：`speech_config.request_word_level_timestamps()` 启用逐词偏移量/时长，提升时间精度
- **语义分段**（v2.0.0322.9）：`Speech_SegmentationStrategy = "Semantic"`（SDK ≥1.41）基于语义智能断句，替代固定静音时长分段
- **性能指标底栏**（v2.0.0322.9）：pill 标签式设计，与其他 Tab 一致
  - **识别延迟**：最后一次 `recognizing` → `recognized` 时间差（ms），实时显示 + 平均值
  - **说话人数**：根据 Diarization Speaker ID 去重统计
  - **词数统计**：累计所有 `recognized` 事件的词数
  - **音频时长**：根据 recognized 事件 offset+duration 计算
- **LIVE 文本指示器移除**（v2.0.0322.9）：实时转录按钮旁的"LIVE"文本+红色圆点整行移除，改为仅保留 subtle 红色小圆点图标
- **生成纪要按钮状态感知**（v2.0.0322.9）：未转写时按钮置灰（`bgcolor=OUTLINE` + `opacity=0.5` + `disabled=True`），转写完成后点亮为蓝色（`#0078D4`），通过 `_set_summary_enabled()` 统一控制视觉+交互状态
- **清除转写结果**（v2.0.0322.9）：转写完成后底栏出现「清除」按钮（`DELETE_OUTLINE` 图标），点击清空转写原文+纪要+性能指标，重置所有按钮状态
- **复制按钮拆分**（v2.0.0322.9）：原单一「复制」按钮拆为「复制原文」+「复制纪要」两个独立按钮，消除歧义。复制原文在转写完成后可用，复制纪要在纪要生成后可用
- **文件选择互斥**（v2.0.0322.9）：选择文件后实时转录按钮置灰禁用（`bgcolor=OUTLINE` + `opacity=0.5`），文件旁显示 ✕ 清除按钮（`IconButton CLOSE`），清除后恢复实时转录可用

## UI 重构（2026-03-22，v2.0.0322.1）
**设计目标**：① 一眼看懂流程"上传→转写→AI总结" ② AI 会议总结是视觉核心 ③ 页面简洁、有留白、层级清晰 ④ 适合暗色模式现代 UI ⑤ Demo 时 2 分钟讲清价值
- **步骤流程指示器**：顶部 ① 上传或录制 → ② 语音转写 → ③ AI 总结，编号 pill + 箭头连接，active 态 Azure 蓝
- **输入区 Card**（#161B22 圆角 12px）：选择文件（带上传图标）+ 录制（带麦克风图标）+ 文件状态 + 开始转写（蓝色 Play 按钮），水平一行紧凑排列
- **结果区主从布局**：
  - 副区（expand=1）：转写原文，弱化标题（opacity 0.45），深色内嵌背景 #0D1117，紧凑气泡（10px padding、小字 13px、speaker badge 10px）
  - 主区（expand=2）：AI 会议纪要，星标图标 + 粗体标题，深色内嵌背景，宽松 padding（20px），独立占位状态（大图标 + 提示文字）
- **底部操作栏**：右对齐，生成纪要（蓝色主按钮）+ 复制（灰色次按钮带图标）+ 导出（灰色次按钮带图标）
- **配置 Banner**：全配置时 `visible=False` 完全隐藏不占空间
- **视觉规范统一**（v2.0.0322.7 全局对齐）：
  - **主功能按钮**：`border_radius=25`（圆角胶囊），`padding=(h=32, v=12)`，`text_size=15`，`icon_size=20`，`FontWeight.BOLD`，`bgcolor=#0078D4`，停止态 `#D32F2F`
  - **次要按钮**：`border_radius=8`，`padding=(h=16, v=8~10)`，`text_size=13`，`FontWeight.W_500`，`bgcolor=SURFACE_CONTAINER_HIGH`
  - **Config Banner**：`border_radius=8`，`padding=(h=14, v=8)`，`icon_size=18`，`text_size=13`，`spacing=10`
  - **布局**：`padding=Padding(l=16, t=12, r=16, b=8)`，`Column spacing=8`
  - **IconButton**：`icon_size=18` 统一
  - 背景色使用 Flet MD3 scheme token 自适应（`SURFACE_CONTAINER_LOWEST` / `SURFACE_CONTAINER` / `SURFACE_CONTAINER_HIGH`），深浅主题自动切换
  - 卡片使用 `OUTLINE_VARIANT` 边框，AI 纪要区左侧 `PRIMARY` 色边框标识
  - 按钮均带图标 + 文字

## Tab 2 Voice Live 实时语音对话
### 已完成
- realtime_tab.py，基于 azure-ai-voicelive 1.1.0 (GA)，包含：
  - Voice Live WebSocket 连接管理（async with connect，独立 asyncio 线程）
  - 麦克风一键启停按钮（Container+Text 方案）
  - **停止按钮即时响应**：点击停止后立即更新 UI、关闭 WebSocket
  - 连接中 ProgressRing 动画 + "连接已建立" 提示
  - AI 状态指示器：正在收听 / AI 说话中 / 空闲
  - **连接状态指示灯**：绿色已连接 / 红色已断开，停止时立即更新
  - 对话气泡左右布局 + 用户占位气泡机制
  - **AI 气泡"..."占位动画**：RESPONSE_CREATED 时显示"..."斜体占位
  - **错误自动断连**：Voice Live ERROR 事件触发时自动中断
  - **UI 刷新机制**：使用 `page.run_task()` 将 `page.update()` 调度到 Flet 事件循环（线程安全）
  - 流式音频播放（sounddevice + queue，chunk_size=1200=50ms）
  - 内置降噪 / 回声消除 / 语义 VAD
  - **主动参与模式**（Proactive Engagement）：开关控制，AI 主动打招呼
  - **丰富语音选择**：18 种 Azure Neural 语音（中/英/日/韩），通过 `AzureStandardVoice` 配置
  - **声音温度**：Slider 0~1（步长 0.1，默认 1.0），旁显数值文本实时更新，控制 `AzureStandardVoice.temperature`
  - **说话速率**：5 档（极慢/慢速/正常/快速/极快），控制 `AzureStandardVoice.rate`
  - 模型下拉 / AI 角色预设 / 配置状态 Banner
  - **设置变更通知**：对话中修改任何设置时，SnackBar 提示"设置已更新，将在下次对话时生效"
  - **UI 布局重构**：
    - hero_bar 顶栏：「开始对话」按钮左上角 + AI 状态 + 连接状态胶囊 + 清除按钮（对齐其他 Tab 布局风格，v2.0.0322.6）
    - 可折叠设置面板（"对话设置"），点击收起/展开，默认展开
    - 对话区占据主体空间（expand），scheme 色 `SURFACE_CONTAINER_LOWEST` 背景
    - 配置 Banner 仅在未配置时显示（已配置时 `visible=False`）
    - 所有下拉框使用 `dense=True` 减少高度
    - Switch 控件使用 `label_text_style` 缩小标签字号
    - 整体 padding/spacing 缩减，间距统一为 6px
- main.py 已导入 realtime_tab 并注册到 Tab 2
- 设置弹窗已新增 Voice Live Endpoint / API Key
- **全局 UI 统一**：所有模块按钮统一使用 Container+Text 样式
- **Emoji 精简**：全局去除按钮和文本描述中的 emoji，仅保留对话气泡中的 👤/🤖 作为说话人标识
- **性能指标 UI 重构**（v2.0.0322.7）：
  - 从大数字卡片式改为紧凑 pill 标签式，对齐同声传译 Tab 延迟 UI 设计风格
  - 性能指标移至底部信息条（bottom_bar），与清除按钮并排，给对话窗口更多显示空间
  - TTFT pill（首字节延迟 + avg）+ E2E pill（端到端延迟 + avg）+ Token pill（累计消耗）
  - 布局从 `[config_banner, hero_bar, settings_panel, perf_panel, chat_panel]` 改为 `[config_banner, hero_bar, settings_panel, chat_panel, bottom_bar]`
- **性能表现数据**（v2.0.0322.4）：
  - **TTFT 首字节延迟**：大数字实时显示 + 平均值（RESPONSE_CREATED → 首个 RESPONSE_AUDIO_DELTA 的时间差）
  - **端到端延迟**：小字实时显示 + 平均值（SPEECH_STOPPED → 首个 RESPONSE_AUDIO_DELTA 的时间差）
  - **Token 消耗**：累计显示总 token 数（从 RESPONSE_DONE 事件的 `response.usage` 提取 `input_tokens` + `output_tokens`）
  - 清除对话时同步重置性能指标
  - **数据来源**：基于 Azure Voice Live SDK（azure-ai-voicelive 1.1.0）`ServerEventType.RESPONSE_DONE` 事件中 `Response.usage: TokenUsage` 对象

### 设置生效时机
所有对话设置（模型、语音、温度、速率、VAD、降噪、回声消除、主动参与、AI 角色）均在 **建立连接时** 通过 `session.update()` 一次性应用，**不支持会话中动态更新**。修改设置后需重新开始对话才能生效。对话进行中修改设置会弹出 SnackBar 通知用户。

### 自适应抖动缓冲 v1 (v2.0.0322.8) — 已被 v2 取代
- 初版方案：基于 Queue[_PlaybackPacket] 包队列 + 包计数预缓冲
- **问题**：日志显示 jitter=346ms, underruns=86。初始预缓冲 5 包（250ms）远不足以覆盖高达 346ms 的网络抖动。包队列方案在预缓冲释放后无法防止后续 underrun

### 自适应抖动缓冲 v2 (v2.0.0322.9) — 当前方案
- **根因分析**（基于日志）：
  - 实测 jitter = 346ms（包间到达时间标准差），远超初版 5 包（250ms）预缓冲
  - 86 次 underrun：每次 underrun 填充 `b"\x00"` 硬切静音 → 听感为"一个字一个字"
  - VPN 切换后 WebSocket 路由改变，RTT 增大且不稳定
- **架构重写**（3 大改进）：
  1. **连续字节缓冲替代包队列**：`_AudioBuffer` 类用 `bytearray` + `threading.Lock` 替代 `Queue[_PlaybackPacket]`。消除包分片开销，支持精确字节级别缓冲检查
  2. **平滑淡入淡出替代硬切静音**（Packet Loss Concealment）：
     - underrun 时保存最后 240 采样点（10ms），用 `np.linspace(1→0)` 指数衰减淡出，而非 `b"\x00"` 硬切
     - 从 underrun 恢复时，对新数据开头用 `np.linspace(0→1)` 淡入
     - 消除硬切产生的 click/pop 噪声，underrun 变得几乎不可察觉
  3. **输出 blocksize 增大 4 倍**：`OUT_BLOCKSIZE = 4800`（200ms），回调频率从 20次/秒降到 5次/秒。每次回调消费更多数据，但给了更长的"数据积累窗口"，大幅减少 underrun 概率
- **自适应策略改进**：
  - 预缓冲单位从"包数"改为"毫秒"：`_PREBUF_MS_DEFAULT = 800`（默认 800ms）
  - 范围 300ms ~ 1500ms（覆盖 2.5× 实测最高 jitter）
  - 基于 2.5×jitter 计算目标值，加上 underrun 频率惩罚（>5次 +200ms，>0次 +100ms）
  - 网络良好（jitter < 30ms 且无 underrun）时递减 50ms/轮，逐步降低延迟
- **日志增强**：
  - 音频 delta 包大小（bytes）记录
  - TTFT 时记录首个音频包大小
  - RESPONSE_AUDIO_DONE 时输出总 chunk 数和总 bytes
  - 预缓冲释放时输出实际缓冲量
- **数据流**：`WebSocket AUDIO_DELTA → _write_audio(bytes) → _AudioBuffer.write() → bytearray.extend() → [预缓冲完成后] → _playback_callback() → _AudioBuffer.read() → sounddevice output`
- **Buf pill 阈值调整**：绿色 < 30ms jitter / 橙色 30~80ms / 橙红色 > 80ms
- **日志增强**：音频 delta 包大小、TTFT 首包、总 chunk/bytes、预缓冲释放量
- **问题**：日志显示 jitter=224~342ms 且 underruns=0（实际存在 underrun 但未被跟踪）。`_AudioBuffer.read()` 内部处理 underrun 但不反馈给 `buf_ctl`，自适应算法无法感知并增大缓冲。且初始预缓冲释放后无保护机制，缓冲逐渐耗尽导致"前面不卡后面卡"

### 自适应抖动缓冲 v3 (v2.0.0322.11) — 当前方案
- **根因分析**（基于 v2 日志）：
  - 实测 jitter = 224~342ms，但日志始终报告 underruns=0
  - **核心 BUG**：`_AudioBuffer.read()` 内部的 `self._in_underrun` 仅用于淡入淡出，**从未将 underrun 计数暴露给 `buf_ctl`**。`buf_ctl["underrun_ts"]` 始终为空，自适应算法认为网络良好而持续降低预缓冲
  - 初始预缓冲释放后无再次保护，播放开始后遇到迟到的 chunk 就缓冲耗尽→卡顿
- **3 大改进**：
  1. **二次预缓冲 (Re-prebuffer)**：当播放过程中缓冲耗尽（underrun），自动重新进入预缓冲状态（阈值 400ms），积累足够数据后才恢复播放。将多次微小断裂（"一个字一个字"）合并为一次 ~400ms 短暂停顿，听感显著改善
  2. **Underrun 计数暴露**：`_AudioBuffer` 新增 `underrun_count` 属性，`RESPONSE_AUDIO_DONE` 时读取并记录到 `buf_ctl["underrun_ts"]`，自适应算法终于能拿到真实数据
  3. **策略参数上调**：
     - 默认预缓冲 800ms → **1000ms**
     - 范围 300~1500ms → **400~2000ms**
     - jitter 乘数 2.5× → **3.0×**（覆盖 ~99% 的延迟波动）
     - underrun 惩罚：>3次 +300ms（原 >5次 +200ms），>0次 +150ms（原 +100ms）
- **数据流**：`AUDIO_DELTA → _write_audio() → _AudioBuffer.write() → [预缓冲/二次预缓冲] → _playback_callback() → _AudioBuffer.read() → sounddevice`

### 客户端回声门控 (v2.0.0322.11)
- **问题**：使用音箱外放时，音箱声音被麦克风拾取，服务端 VAD 误判为"用户说话"触发 `SPEECH_STARTED` 事件，导致 AI 反复被打断（日志显示快速循环：用户开始说话→打断 AI→用户停止→AI 回复→打断...）
- **方案**：在 `_mic_cb` 中实现能量门控 (Energy Gate)：
  - 当 AI 音频正在播放 (`audio_buf.is_outputting`) 或处于冷却期内，计算麦克风输入的 RMS 能量
  - RMS < 800 (回声级别) → 不发送到服务端，抑制回声
  - RMS ≥ 800 (真实说话级别) → 正常发送，允许 barge-in 打断
  - AI 停止播放后 0.6s 冷却期，避免残余回声触发 VAD
- **参数**：`_ECHO_GATE_RMS = 800`（int16 量级），`_ECHO_COOLDOWN_SEC = 0.6`
- **与服务端回声消除的关系**：服务端 `server_echo_cancellation` 对大延迟（1000ms+ 预缓冲）场景效果不佳，客户端门控作为补充层

### 导出功能改进 (v2.0.0322.9)
- **会议纪要导出**：`export_txt()` 改为 `async def`，使用 `FilePicker.save_file()` 弹出系统“另存为”对话框，用户自选保存位置和文件名
- **传译记录导出**：`_export_record()` 同理改为 `async def` + `save_file()`
- **旧方案**：自动保存到 `get_data_dir("exports")/` 固定目录，用户不知道文件存哪
- **新方案**：弹出系统文件保存对话框，默认文件名带时间戳（`meeting_notes_20260322_xxxx.txt` / `translation_20260322_xxxx.txt`），用户可自选任意位置
- **取消处理**：用户取消保存对话框时 SnackBar 提示"已取消导出"
- **移除 `get_data_dir` 依赖**：两个 tab 的 `from app_paths import get_data_dir` 已移除

### 待完成
- 运行测试（需要 Azure Voice Live 部署）
- 连接失败后自动重连逻辑
- 主动参与的静默期自动响应（沉默后 AI 主动发起话题）

### 踩坑记录
- **❗ voice temperature 范围**：`AzureStandardVoice.temperature` 允许 0~1（API 校验 ≤1），不是 0~2。超出报错 "Input should be less than or equal to 1" 并断连
- **❗ Slider 数值显示**：Flet Slider 的 `label="{value}"` 仅在拖拽时以 tooltip 显示，不够直观。需额外添加 Text 控件 + `on_change` 回调实时更新数值文本
- **❗ Switch.label_style 不存在**：Flet 0.82 的 Switch 关键字是 `label_text_style`（不是 `label_style`）
- **❗ 后台线程 page.update() 不可靠**：从非 Flet 线程调用 `page.update()` 无法可靠触发 Flutter 渲染刷新，表现为"拖拽窗口才更新"。正确做法是 `page.run_task()` 调度 async 函数到 Flet 的 asyncio 事件循环
- **❗ page.open() 不适用于 SnackBar**：Flet 0.82 中 `page.open()` 对 SnackBar 无效（不显示），必须使用 `page.show_dialog(ft.SnackBar(...))`。全项目统一使用 `page.show_dialog()` 显示 SnackBar
- **❗ Dropdown 没有 on_change**：Flet 0.82 的 Dropdown 事件是 `on_select`（不是 `on_change`）。`on_change` 不存在于 Dropdown 类，赋值不会报错但也不会触发。Switch 和 Slider 仍使用 `on_change`
- **❗ Tooltip 没有 content 参数**：Flet 0.82 的 `ft.Tooltip` 不接受 `content` 关键字参数（不是包装组件）。要给按钮加 tooltip 应使用 `IconButton(tooltip="...")` 属性
- **❗ IconButton 没有 content 参数**：Flet 0.82 的 `ft.IconButton` 不接受 `content` 参数。必须使用 `icon=ft.Icons.XXX` 属性设置图标
- **❗ 音频重构后定义遗漏**（v2.0.0322.10）：v2.0.0322.9 将音频播放从 `Queue[_PlaybackPacket]` 重构为 `_AudioBuffer` 连续字节缓冲，但 `OUT_BLOCKSIZE` 常量和 `_AudioBuffer` 类定义未写入模块级作用域（仍保留旧的 `_PlaybackPacket` 类），导致运行时 `NameError: name 'OUT_BLOCKSIZE' is not defined` 和 `NameError: name 'audio_buf' is not defined`。修复：将 `_AudioBuffer` 类和 `OUT_BLOCKSIZE = 4800` 定义放在模块级（`build_realtime_tab` 函数外），移除旧的 `_PlaybackPacket` 类和 `import queue`
- **❗ PyInstaller onefile 模式遗漏 ctypes DLL（v2.0.0322.12）**：
  - **症状**：MSI 安装包运行后，Tab 1 实时转录和 Tab 3 同声传译点击启动立即报错 `Failed to load dynlib/dll 'C:\\Users\\xxx\\AppData\\Local\\Temp\\_MEI226762\\azure\\cognitiveservices\\speech\\Microsoft.CognitiveServices.Speech.core.dll'`。直接 `python main.py` 运行正常
  - **根因**：Azure Speech SDK 的 `interop.py` 通过 `ctypes.windll.LoadLibrary(os.path.join(os.path.dirname(__file__), library_name))` 动态加载 `Microsoft.CognitiveServices.Speech.core.dll`。PyInstaller 的依赖分析只扫描 Python import，不扫描 ctypes 调用，因此这 4 个 DLL 不会被自动包含。旧 spec 中 `binaries=[]` 为空，导致所有 Azure Speech SDK 原生 DLL 缺失
  - **修复**：在 `AzureAISpeechDemo.spec` 中用 glob 动态收集 DLL 并以正确子目录加入 `binaries`：
    ```python
    _sp = Path(SPECPATH) / '.venv' / 'Lib' / 'site-packages'
    _speech_bins = [(str(f), 'azure/cognitiveservices/speech') for f in (_sp / 'azure' / 'cognitiveservices' / 'speech').glob('*.dll')]
    _sd_bins = [(str(f), '_sounddevice_data/portaudio-binaries') for f in (_sp / '_sounddevice_data' / 'portaudio-binaries').glob('*.dll')]
    binaries = _speech_bins + _sd_bins
    ```
  - **关键点**：目标路径必须与包的 `__file__` 路径结构匹配，否则 ctypes 找不到 DLL
  - **同类问题**：sounddevice 的 portaudio DLL 也相同原理，同步修复
  - **打包结果**：exe 从 131.8 MB 降至 106.5 MB（UPX 压缩后 DLL 体积更小）

## Tab 3 同声传译 Live Interpreter — 已完成
### 已完成
- interpreter_tab.py 全功能创建，包含：
  - Azure Speech Translation 实时翻译（TranslationRecognizer + 连续识别）
  - 自动语言检测（AutoDetectSourceLanguageConfig，At-start LID，支持 zh-CN/en-US/ja-JP/ko-KR 共 4 种）
  - **目标语言** 6 种可选（中/英/日/韩/德/法），不受 LID 限制
  - 实时原文字幕（左侧 ListView）
  - 实时译文字幕（右侧 ListView，与原文对齐）
  - 目标语言切换（中/英/日/韩/德/法 6 种，运行中切换自动重启识别器）
  - Azure Neural TTS 译文语音播放（**复用 SpeechSynthesizer** 降低延迟）
  - TTS 开关控制
  - 延迟指标 pill 标签（延迟 / 句数 / 检测语言）
  - 延迟趋势柱状图（最近 10 次）
  - 配置状态 Banner（Speech Key 检测，已配置时自动隐藏）
  - 会话记录导出（原文+译文双栏 .txt 文件）
  - 清除记录功能
- main.py 已集成 interpreter_tab 到 Tab 3
- 设置弹窗已有 Speech API Key 和 Region 配置（复用）

### UI 重构（2026-03-22）
**设计目标**：① 一眼看懂"实时同声传译" ② 一眼看出"Azure = 低延迟" ③ 操作极简"开始/停止"
- **三层布局**：Hero 按钮区 → 主舞台字幕区（80%空间）→ 底部信息条
- **Hero 区**：大号蓝色「开始传译」按钮（带图标 + 阴影），LIVE 状态指示，语言检测 pill → 目标语言选择
- **主舞台字幕**：
  - 去掉硬边框/时间戳，沉浸式字幕体验
  - scheme 色背景 `SURFACE_CONTAINER`，圆角 16px，`OUTLINE_VARIANT` 边框
  - 译文面板左侧绿色边框 `#00C853` 标识
  - 大号字体（17px），原文继承主题色、译文 `#00C853` 绿色，非日志风格
  - 中间结果显示为半透明斜体
- **底部信息条**：延迟 pill + 句数 pill + 趋势图紧凑一行，工具按钮右侧低调放置
- **配置 Banner**：已配置时完全隐藏，不占空间
- **视觉统一**：圆角 pill 标签、scheme 色自适应边框、统一暗/浅色调

### 延迟优化（2026-03-22）
- **复用 SpeechSynthesizer**：避免每句译文都重新建立 WebSocket 连接（官方最佳实践 "Pre-connect and reuse"），显著降低 TTS 首字节延迟
- **Synthesizer 线程安全**：通过 `synth_lock` 保护，语言切换时自动 invalidate 并重建
- **字幕渲染简化**：移除时间戳渲染、减少 Container 嵌套，降低 UI 渲染开销
- **分段静音超时优化**：设置 `Speech_SegmentationSilenceTimeoutMs=300`，将语音端点检测从默认 ~500-2000ms 缩短到 300ms，显著降低“说完到译文出现”的延迟
- **Pre-connect TTS**：开始传译时后台线程预连接 `SpeechSynthesizer`（`Connection.from_speech_synthesizer + open(True)`），降低首次播报延迟
- **延迟指标优化**：改用“最后一次 recognizing → recognized”计算延迟（更准确反映“说完到译文”的实际延迟，而非包含说话时长）

### Bug 修复（2026-03-21 ~ 03-22）
- **修复 "Language identification only supports 4 languages in DetectAudioAtStart mode" 错误**
  - **根因**：`TranslationRecognizer` 仅支持 **At-start LID** 模式（Continuous LID 仅适用于 `SpeechRecognizer`），At-start LID 最多支持 **4 种**候选语言，但原代码配置了 6 种（zh-CN/en-US/ja-JP/ko-KR/de-DE/fr-FR），导致 Azure 服务端报错 1007 断连
  - **第一次修复尝试（03-21）**：设置 `SpeechServiceConnection_LanguageIdMode=Continuous` — **无效**，因为 Continuous LID 不适用于 TranslationRecognizer
  - **最终修复（03-22）**：将 SOURCE_LANGUAGES 缩减为 4 种（zh-CN/en-US/ja-JP/ko-KR），满足 At-start LID 上限；移除无效的 Continuous LID 设置。de-DE/fr-FR 仍可作为目标语言使用
  - **参考**：[Azure 语言识别文档](https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/language-identification?pivots=programming-language-python) — 连续语言标识仅支持语音转文本，不支持语音翻译
- **修复停止传译后 TTS 音频未停止**
  - **根因**：`_stop_translation()` 只停止了 `TranslationRecognizer`，未停止正在播放的 `SpeechSynthesizer`
  - **修复**：停止时调用 `synth.stop_speaking_async()` 立即中断 TTS 播放，并重置 synthesizer
  - `_speak_tts` 增加 `state["running"]` 检查，停止后不再播报新句
- **修复 Dropdown on_change 无效问题**
  - **根因**：Flet 0.82 的 Dropdown 事件是 `on_select`，不是 `on_change`。`on_change` 赋值不会报错但也不会触发，导致男声音色选择、目标语言切换等操作无效
  - **修复**：将 `voice_gender_dropdown.on_change`、`voice_dropdown.on_change`、`target_lang_dropdown.on_change` 全部改为 `on_select`
  - **踩坑记录**：Dropdown 的 `on_change` bug 是静默失败（silent failure），不报错但回调不触发，非常难排查

### 流式翻译优化（2026-03-22 v2.0.0322.2）
- **边说边译 Live Bubble 机制**：完全重构字幕显示算法，从"说完整句才翻译"改为"边说边翻译"
  - **旧算法**：`recognizing` 事件显示在独立的淡化 interim 容器（位于 ListView 外部，opacity=0.5，斤体），`recognized` 事件才添加到字幕列表
  - **新算法**：`recognizing` 事件直接在 ListView 内创建 "live bubble"（左侧蓝/绿色边框 + 半透明斜体），实时更新文本；`recognized` 事件将 live bubble "定稿"（移除边框、恢复正常样式）
  - **视觉效果**：用户说话时，原文和译文同时在字幕区"打字机式"流式显现，说完后自动变为正常样式
  - **延迟感知**：显著降低"说完到看到译文"的感知延迟，因为译文在说话过程中就已开始显示
  - **技术细节**：移除了独立的 `_interim_source_container` / `_interim_target_container`，改用 `_live` 状态字典跟踪当前 live bubble（含 Container 和 Text 引用）
- **设置变更通知机制**（对齐 Voice Live 方案）：
  - 切换音色性别/具体音色/TTS开关 → SnackBar 通知"设置已更新，下一句传译时生效"（传译中）或"设置已更新"（空闲）
  - 音色变更通过 invalidate synthesizer 实现，下一次 TTS 调用时自动重建

### 踩坑记录补充（2026-03-22）
- **❗ Dropdown on_change 静默失败**：Flet 0.82 的 Dropdown 事件是 `on_select`，`on_change` 赋值不会报错但回调永远不触发。这导致男声音色选择无效、目标语言切换无效等多个功能失灵，且难以排查（无报错信息）。**全项目 Dropdown 必须统一使用 `on_select`**

### 待完成
- 运行测试（需要 Azure Speech 服务部署）
- 延迟趋势 pyqtgraph 折线图（暂用文字柱状图替代）

### 音色选择功能（2026-03-22）
- **男/女声切换**：实时切换 TTS 音色性别，每种目标语言提供 3 个男声 + 3 个女声
- **具体音色可选**：下拉框选择具体 Azure Neural 语音（如晓晓/云希/Jenny/Guy 等）
- **支持的音色**：
  - 中文：女（晓晓/晓伊/晓辰） 男（云希/云健/云扬）
  - 英语：女（Jenny/Aria/Ava） 男（Guy/Davis/Brian）
  - 日语：女（七海/葵/まゆ） 男（圭太/大智/直紀）
  - 韩语：女（선히/지민/유진） 男（인준/봉진/국민）
  - 德语：女（Katja/Amala/Klarissa） 男（Conrad/Bernd/Kasper）
  - 法语：女（Denise/Coralie/Brigitte） 男（Henri/Claude/Alain）
- **音色自动联动**：切换目标语言或性别时自动更新可选音色列表，invalidate synthesizer
- **技术说明**：Azure Speech SDK 不支持自动检测说话人性别/音色匹配（没有内置的 speaker gender detection → TTS voice matching API），因此采用手动选择方案让用户自行指定男/女声

## 发布记录

### v2.0.0322.12 — GitHub Release（2026-03-22）
- **推送到 GitHub**：`main` 分支，commit `2c53783`（DLL 修复）+ `5fd37d3`（版本号单一来源）
- **Release**：[v2.0.0322.12](https://github.com/pennz1/win32-azure-speech-demo/releases/tag/v2.0.0322.12)
- **安装包**：`AzureAISpeechDemo_Setup_2.0.0322.12.exe`（~106 MB，含完整 DLL）
- **修复 1**：PyInstaller onefile 遗漏 Azure Speech SDK ctypes DLL 导致 Tab 1/3 启动报错
- **修复 2**（本次）：安装向导版本号与实际版本不一致问题
  - **根因**：版本号在 `main.py`、`installer.nsi`、`build_installer.ps1` 三处硬编码，每次升版需手动同步，容易遗漏
  - **解决方案**：以 `main.py` 的 `VERSION` 为单一来源
    - `build_installer.ps1` 用正则 `VERSION\s*=\s*"v?([\d\.]+)"` 从 `main.py` 读取版本，不再硬编码 `$Version`
    - NSIS 调用改为 `makensis /DPRODUCT_VERSION=$Version installer.nsi` 外部传入
    - `installer.nsi` 改为 `!ifndef PRODUCT_VERSION ... !define PRODUCT_VERSION "备用值" ... !endif`，支持外部覆盖
  - **今后只需改 `main.py` 的 `VERSION`**，打包脚本自动同步到安装向导版本号
- **修复 3**（本次）：移除安装向导欢迎页中 `Windows 10/11 x64` 系统要求文案

### v2.0.0322.11 — GitHub Release（2026-03-22）
- **推送到 GitHub**：`main` 分支，commit `d10a55e`
- **Release**：[v2.0.0322.11](https://github.com/pennz1/win32-azure-speech-demo/releases/tag/v2.0.0322.11)
- **安装包**：`AzureAISpeechDemo_Setup_2.0.0322.11.exe`（~131 MB，DLL 未打包，已被 v2.0.0322.12 修复替代）
- **README 重构**：全面更新，反映 Phase 2 Voice Live + Phase 3 等最新功能
- **.gitignore 更新**：排除运行时日志，允许 `AzureAISpeechDemo.spec`
- **不推送的文件**：`_build_exe.py`、`_check_braces.py`（临时脚本）/ 日志 / `dist/` / `build/` / `config.json`

## Flet 0.82 迁移摘要（2026-03-21 本次完成）
### 背景
Windows 机器上使用 Python 3.14 + Flet 0.82.2（pip 安装的最新版），Flet API 从 0.28 大幅变更。

### 主要迁移项
| 旧 API | 新 API | 影响文件 |
|--------|--------|---------|
| `ft.app(target=main)` | `ft.run(main)` | main.py |
| `ft.ElevatedButton` | `ft.Button`（ElevatedButton 标记 deprecated） | main.py, transcription_tab.py |
| `ft.Tab(text=..., content=...)` | `ft.Tabs(content=Column([TabBar(tabs=[Tab(label=...)]), TabBarView(controls=[...])]), length=N)` | main.py |
| `ft.FilePicker(on_result=callback)` | `FilePicker()` + `await file_picker.pick_files()` 返回结果 | transcription_tab.py |
| `page.set_clipboard(text)` | `Clipboard()` 控件 + `await clipboard.set(text)` | transcription_tab.py |
| `page.snack_bar = ...; page.snack_bar.open = True` | `page.show_dialog(ft.SnackBar(...))` | main.py, transcription_tab.py |
| `page.open(dialog)` / `page.close(dialog)` | `page.show_dialog(dialog)` / `page.pop_dialog()` | main.py |
| `ft.alignment.center` | `ft.Alignment(0, 0)` | main.py, transcription_tab.py |
| `ft.padding.symmetric(...)` | `ft.Padding.symmetric(...)` | main.py, transcription_tab.py |
| `ft.border.all(...)` | `ft.Border.all(...)` | transcription_tab.py |
| `page.overlay.append(picker/clipboard)` | `page.services.append(picker/clipboard)` | transcription_tab.py |
| `Dropdown(on_change=...)` | `Dropdown(on_select=...)` — Flet 0.82 Dropdown 没有 `on_change` | realtime_tab.py, interpreter_tab.py |
| Python 3.9 monkey-patch (flet.core.tabs) | **已删除**（flet.core 模块不存在于 0.82） | main.py |

### 注意事项
- `FilePicker.pick_files()` 和 `Clipboard.set()` 是 **async** 方法，事件处理函数需用 `async def`
- `ft.Tabs` 在 0.82 中变为组合控件：需同时设置 `content`（包含 TabBar + TabBarView）和 `length`
- `page.pop_dialog()` 不接受参数，弹出最顶层对话框
- Flet 0.82 **没有内置图表控件**（LineChart 等已移除），需用第三方库或文字/ProgressBar 替代
- **❗ Service vs Overlay 坑点**：Flet 0.82 中 `FilePicker`、`Clipboard` 等控件的基类从 `Control` 变为 `Service`，必须注册到 `page.services`，**不能**用 `page.overlay`（否则报 "Unknown control: FilePicker/Clipboard"）
- **❗ 中文字体**：Flet 0.82 使用 Flutter 渲染引擎，默认不走系统字体。需通过 `page.fonts` 注册字体**文件路径**（不是字体名），再通过 `theme.font_family` 引用：
  ```python
  page.fonts = {"MicrosoftYaHei": "C:/Windows/Fonts/msyh.ttc"}
  page.theme = ft.Theme(color_scheme_seed="#0078D4", font_family="MicrosoftYaHei")
  ```

## Windows .exe 打包（已验证 v2.0.0322.3）
### 打包方式
由于 `flet pack` CLI 在某些环境下无法找到 venv 中的 PyInstaller，采用 **Python API** 直接调用。等效于 `flet pack` 但从 venv Python 进程内执行：

```powershell
cd "d:\Users\项目\win32-azure-speech-demo"
& ".\.venv\Scripts\python.exe" -c "
import sys, os, shutil
from flet.utils import is_windows
import flet_cli.__pyinstaller.config as hook_config
from flet_cli.__pyinstaller.utils import copy_flet_bin

pyi_args = [
    'main.py', '--noconfirm', '--noconsole', '--onefile',
    '--name', 'AzureAISpeechDemo',
    '--hidden-import', 'azure.cognitiveservices.speech',
    '--hidden-import', 'openai',
    '--hidden-import', 'sounddevice',
    '--hidden-import', 'scipy.io.wavfile',
    '--hidden-import', 'cryptography.fernet',
    '--hidden-import', 'azure.ai.voicelive',
    '--hidden-import', 'azure.ai.voicelive.aio',
    '--hidden-import', 'azure.ai.voicelive.models',
    '--hidden-import', 'numpy',
    '--hidden-import', 'azure.core.credentials',
    '--hidden-import', 'aiohttp',
    '--exclude-module', 'tkinter',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'PIL',
    '--exclude-module', 'cv2',
    '--exclude-module', 'torch',
    '--exclude-module', 'tensorflow',
    '--exclude-module', 'pytest',
]

hook_config.temp_bin_dir = copy_flet_bin()
if hook_config.temp_bin_dir:
    fletd = os.path.join(hook_config.temp_bin_dir, 'fletd.exe')
    if os.path.exists(fletd): os.remove(fletd)
    from flet_cli.__pyinstaller.win_utils import update_flet_view_version_info
    exe_path = os.path.join(hook_config.temp_bin_dir, 'flet', 'flet.exe')
    if os.path.exists(exe_path):
        vi = update_flet_view_version_info(exe_path=exe_path,
            product_name='Azure AI Speech Demo', file_description='Azure AI Speech Demo',
            product_version='2.0.0322.3', file_version='2.0.322.3',
            company_name=None, copyright=None)
        pyi_args.extend(['--version-file', vi])

import PyInstaller.__main__
PyInstaller.__main__.run(pyi_args)
if hook_config.temp_bin_dir and os.path.exists(hook_config.temp_bin_dir):
    shutil.rmtree(hook_config.temp_bin_dir, ignore_errors=True)
"
```

### 结果
- 产出：`dist/AzureAISpeechDemo.exe`，约 **132 MB**（单文件）
- 已验证：exe 中不包含 config.json、API Key 等敏感数据
- 用户首次运行需在设置中填写 Azure API Key
- flet_desktop 运行时资源（~95 MB）是体积主要组成部分，无法进一步压缩
- 排除了 tkinter/matplotlib/PIL/cv2/torch/tensorflow/pytest 等未使用模块

### 安全保证
- config.json 不打包进 exe，运行时由用户在程序中配置并自动创建
- API Key 使用 Fernet 加密存储在用户目录 `~/.azure_ai_demo/.encryption_key`
- 加密密钥按用户隔离，每台机器独立生成

## NSIS 安装包（v2.0.0322.5）
### 功能
- **安装向导**：欢迎页 → 安装目录选择 → 安装 → 完成（可选立即运行）
- **开始菜单快捷方式**：`开始菜单\Azure AI 语音演示台\` 下创建程序快捷方式 + 卸载快捷方式
- **桌面快捷方式**：自动创建桌面图标
- **卸载功能**：控制面板"程序和功能"可卸载，清理程序文件和快捷方式（保留用户配置）
- **VC++ 运行库检查**：安装后检测 VCRUNTIME140.dll，缺失时提示用户下载
- **多语言**：支持简体中文 + English

### ICO 图标使用
将 `.ico` 文件放在项目根目录命名为 `app.ico`，构建时自动应用到：
- PyInstaller exe 图标
- NSIS 安装包图标
- 安装/卸载向导图标

启用方法：在 `installer.nsi` 中取消注释以下行：
```nsi
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
File "app.ico"
```

### 构建命令
```powershell
# 一键构建（自动检测 app.ico）
.\build_installer.ps1

# 指定图标文件
.\build_installer.ps1 -Icon "path\to\icon.ico"

# 仅构建 exe（跳过安装包）
.\build_installer.ps1 -SkipInstaller

# 仅打安装包（已有 exe）
.\build_installer.ps1 -SkipBuild

# 手动 NSIS
makensis /INPUTCHARSET UTF8 installer.nsi
```

### 产出
- `dist\AzureAISpeechDemo.exe` — 单文件可执行程序（~132 MB）
- `dist\AzureAISpeechDemo_Setup_x.x.x.exe` — NSIS 安装包（~131 MB）

## DLL 依赖与错误处理（v2.0.0322.5）
### 启动时检查
main.py 启动时自动检测以下 DLL：
- `MSVCP140.dll`
- `VCRUNTIME140.dll`
- `VCRUNTIME140_1.dll`

缺失时弹出 Windows MessageBox 提示用户安装 VC++ Redistributable，并提供下载链接：
`https://aka.ms/vs/17/release/vc_redist.x64.exe`

### 双重保护
1. **安装时**：NSIS 安装包完成后检测 VCRUNTIME140.dll，缺失则提示下载
2. **运行时**：exe 启动前 DLL 检查，缺失弹出 MessageBox 并退出

## 工程化状态
| 项目 | 状态 |
|------|------|
| .gitignore | ✅ 已创建 |
| Git 本地仓库 | ✅ 已创建 |
| GitHub 远程仓库 | ✅ 已创建并已首推 |
| build.spec | ✅ 已纳入 Git，已更新含 flet pack 命令 |
| GitHub Actions (Windows) | ✅ 工作流配置存在（需更新为 flet pack） |
| README | ✅ 已创建 |
| Windows 冒烟测试 | ✅ 已通过（dev 模式 + .exe 打包） |
| Python venv | ✅ .venv 已创建（Python 3.14, d:\Users\项目\win32-azure-speech-demo\.venv） |

## Windows 开发指南
### 环境
- Python 3.14 x64（C:\Users\Penn\AppData\Local\Python\pythoncore-3.14-64\python.exe）
- 虚拟环境：`d:\Users\项目\win32-azure-speech-demo\.venv`
- 激活方式：先 `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`，再 `.venv\Scripts\Activate.ps1`
- 或直接使用：`& "d:\Users\项目\win32-azure-speech-demo\.venv\Scripts\python.exe" main.py`

### 运行
```powershell
cd "d:\Users\项目\win32-azure-speech-demo"
& ".\.venv\Scripts\python.exe" main.py
```

## 关键决策
- 内部 Demo，**不需要**代码签名
- API Key **不写死**，设置页可配置 + Fernet 加密本地存储
- Windows 开发 + 打包（不再跨平台 macOS→Windows）
- GPT-4o 部署名可配置（默认 gpt-4o）
- Realtime 部署名可配置（默认 gpt-4o-realtime-preview）
- Speech 不使用 Endpoint 字段，仅 Region + Key
- 打包使用 `flet pack` 而非手动 pyinstaller（自动处理 Flet 运行时资源）
- Flet 0.82 无内置图表 → TTFT 趋势用文字柱状图替代

## 变更日志

| 日期 | 版本 | 本次完成内容 | 负责人 |
|------|------|-------------|--------|
| 2026-03-20 | v0.1 | 应用壳层 + 录音转写全功能实现 | 张鹏程 |
| 2026-03-20 | v0.2 | 修复 Banner 4 态、pubsub 回调、转写缺 Key 提示、按钮 tooltip | 张鹏程 |
| 2026-03-21 | v0.3 | 初始化 Git、本地首提、创建 GitHub 仓库并完成首推；补充 Windows 接续开发说明 | 张鹏程 |
| 2026-03-21 | v0.4 | 将 build.spec 纳入版本控制，修复 Windows/CI 打包配置缺失风险 | 张鹏程 |
| 2026-03-21 | v0.5 | **Flet 0.82 全量迁移**：修复 Tabs/FilePicker/Clipboard/SnackBar/Dialog/Button 等 12 处 API 变更；删除 Python 3.9 monkey-patch；Windows 冒烟测试通过；`flet pack` 打包 .exe 成功（136MB）；创建 README.md；更新 requirements.txt 和 build.spec | Copilot |
| 2026-03-21 | v0.7 | realtime_tab 集成到 main.py Tab 2（修复 `_safe_update` 作用域问题）；interpreter_tab.py 全功能开发并集成到 Tab 3；config_manager 添加 `realtime_deployment` 默认值；三 Tab 冒烟测试通过 | Copilot |
| 2026-03-21 | v0.8 | 修复 Flet 0.82 Service 注册问题：FilePicker/Clipboard 从 `page.overlay` 迁移到 `page.services`（解决 "Unknown control" 报错）；修复中文字体渲染（`page.fonts` 需指向字体文件路径 msyh.ttc，不能用字体名）；全面排查并消除所有 `page.overlay` 用法 | Copilot |
| 2026-03-21 | v0.9 | **Voice Live 性能与体验大修**：① 音频卡顿根治（事件处理不再调用 page.update，用 _mark_dirty + 后台刷新线程）；② 气泡顺序修复（用户占位气泡机制）；③ 移除指标面板，对话区全宽；④ 按钮用 Container+Text 替代 ft.Button | Copilot |
| 2026-03-22 | v2.0.0322.1 | **传译优化**：① 修复停止传译 TTS 音频未停止（stop_speaking_async）；② 多音色可选功能（6语言×2性别×3音色=36种）；③ 翻译延迟优化（分段静音超时300ms + Pre-connect TTS + 延迟指标优化）；④ 版本号 v2.0.0322.1 | Copilot |
| 2026-03-22 | v2.0.0322.2 | **流式翻译+音色修复**：① 边说边译 Live Bubble 流式字幕（实时显示识别和翻译中间结果）；② 修复 Dropdown on_change→on_select 静默失败 BUG（男声音色/目标语言切换无效）；③ 设置变更 SnackBar 通知机制（对齐 Voice Live） | Copilot |
| 2026-03-22 | v2.0.0322.4 | **主题切换+性能指标**：① 深色/浅色/跟随系统三种主题循环切换（图标式，点击立即生效，持久化到 config）；② Voice Live 性能表现区域（TTFT 首字节延迟大数字+平均、端到端延迟+平均、Token 消耗统计）；③ 基于 Voice Live SDK RESPONSE_DONE.response.usage 提取 token 统计 | Copilot |
| 2026-03-22 | v2.0.0322.5 | **NSIS 安装包+DLL 保护**：① NSIS 安装向导（欢迎页→目录→安装→完成，含开始菜单/桌面快捷方式、卸载功能）；② DLL 依赖启动检查（MSVCP140/VCRUNTIME140/VCRUNTIME140_1，缺失弹 MessageBox 指引安装 VC++ Redist）；③ ICO 图标支持（PyInstaller + NSIS 双路径）；④ 一键构建脚本 build_installer.ps1（含安全检查）；⑤ 安装包含 VC++ 运行库检测提示 | Copilot |
| 2026-03-22 | v2.0.0322.6 | **UI 统一+Banner 优化**：① Voice Live 布局重构（去掉标题，"开始对话"按钮挪至左上角 hero_bar，对齐其他 Tab 布局风格）；② Tab 标签"实时对话 GPT-4o"改为"实时对话 VoiceLive"；③ Voice Live 配置 Banner 改为仅异常时显示（已配置时 visible=False，对齐其他 Tab） | Copilot |
| 2026-03-22 | v2.0.0322.7 | **全局 UI 样式统一**：① 主功能按钮统一规范（border_radius=25 圆角胶囊、padding=h32v12、text_size=15、icon_size=20、BOLD），三 Tab 全对齐；② Voice Live 开始对话按钮增加 MIC 图标（与其他 Tab 对齐）；③ 传译主按钮去除 shadow 和过大尺寸；④ Config Banner 三 Tab 统一（border_radius=8、icon 18px、text 13px、padding h14v8、spacing 10）；⑤ 传译导出按钮增加图标统一风格（icon+text、border_radius=8）；⑥ 设置弹窗保存按钮 border_radius 20→8 统一方角风格；⑦ Tab 1 外层 padding/spacing 对齐 Voice Live/3（24→Padding(l16,t12,r16,b8)、spacing 16→8） | Copilot |
| 2026-03-22 | v2.0.0322.8 | **浅色主题优化+导出弹窗**：① 全面替换硬编码深色 hex 颜色为 Flet MD3 ColorScheme token，深浅主题自动适配；② Tab 1/3 导出改为 FilePicker.save_file() 系统"另存为"对话框；③ Voice Live 自适应抖动缓冲 v2（连续字节缓冲 + 淡入淡出 PLC + OUT_BLOCKSIZE 4800） | Copilot |
| 2026-03-22 | v2.0.0322.9 | **Tab 1 增强**：① 移除实时转录 LIVE 文本指示器（仅保留 subtle 红色小圆点）；② 微软文档研究：启用 word-level timestamps（`request_word_level_timestamps()`）+ 语义分段（`Speech_SegmentationStrategy=Semantic`）；③ 性能指标底栏（识别延迟+avg、说话人数、词数、音频时长）pill 标签式 UI 匹配其他 Tab 设计；④ 修复 realtime_tab.py 缺失 `import queue`；⑤ 设置弹窗 UI 调整：Region 下拉移至 Speech Key 下方、Voice Live 标题去除"(Phase 2)"；⑥ 生成纪要按钮未转写时置灰；⑦ 清除转写结果按钮；⑧ 复制按钮拆分为「复制原文」+「复制纪要」；⑨ 文件选择后实时转录按钮互斥置灰+清除已选文件按钮 | Copilot |
