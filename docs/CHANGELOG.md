# 变更日志 (Changelog)

本文档归档记录了 Azure AI 语音演示台每个版本的详细演进历史与发布细则。核心/精简版更新日志请参阅 `README.md`。

## 发布细则归档

### v2.0.0322.13（2026-03-22）
- **回声消除优化**：客户端回声门控参数上调 — `_ECHO_GATE_RMS` 800→1500、`_ECHO_COOLDOWN_SEC` 0.6→1.2，降噪/回声消除开关默认开启，角色指令追加防回声规则
- **转写语言推断**：`input_audio_transcription` 从 `whisper-1`（自动检测）改为 `gpt-4o-transcribe` + 根据语音名前缀固定 `language` 参数，解决首句中文被误判为其他语言的问题
- **再见自动断开**：定义 `FunctionTool("end_conversation")`，用户说再见时 AI 主动调用工具断开连接。处理 `RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE` 事件，发送工具确认后等 3 秒再断开

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

## 主要版本迭代历史

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
| 2026-03-22 | v2.0.0322.12 | **Voice Live 三项优化**： 回声门控参数调优（RMS 阈值 8001500，冷却时间 0.6s1.2s），更有效抑制扬声器回声打断 AI； 转写模型 whisper-1gpt-4o-transcribe + `language` 参数按语音自动推断（zh/en/ja/ko），解决首句文本语言误检问题； FunctionTool `end_conversation` 自动断开用户说再见/拜拜/goodbye时 AI 先礼貌告别，再通过工具调用触发客户端主动断开（含 3s 延迟等待告别语音播完）；所有角色预设追加 anti-echo + goodbye 指令后缀 | Copilot |
| 2026-03-22 | v2.0.0322.15 | **Voice Live 终结点与模型优化**：① 终结点切换 East US 2 → SEA（pengchengvoice-sea-resource.cognitiveservices.azure.com），日志确认连接成功；② 发现 gpt-realtime 在 SEA 不可用，gpt-4.1 管线模型音频突发卡顿（jitter=1595ms）；③ MODEL_OPTIONS 从 5→8 个模型，分类标注"原生音频"vs"管线模式"；④ 不可用模型自动检测 + 下拉列表标记 ⊘ + 自动切换可用模型；⑤ 管线模型音频缓冲策略：预缓冲 ≥1500ms、二次预缓冲 1200ms（原 400ms）、自适应最小 1200ms、上限 3000ms | Copilot |
| 2026-03-22 | v2.0.0322.16 | **区域感知模型可用性 & 置灰禁选**：① 新增 `_REGION_MODEL_SUPPORT` 静态区域-模型矩阵（覆盖 20+ 区域，来源 MS Learn 文档）；② `_extract_region_from_endpoint()` 从 URL 主机名 + config.region 推断区域；③ 终结点变更时自动识别区域 → 查矩阵 → 不可用模型 `disabled=True` 置灰禁选（Flet dropdown.Option 原生支持）；④ 区域变更清除旧运行时缓存；⑤ `_on_start()` 增加预检拦截已知不可用模型，避免无效连接；⑥ 保留运行时错误检测 (`not supported in this region`) 作为矩阵补充 | Copilot |
| 2026-03-22 | v2.0.0322.17 | **管线模型抖动过滤修复**：① 管线模型 jitter 计算过滤 >300ms 到达间隔（排除 TTS 句间停顿），仅用突发内 ~50ms 间隔计算真实抖动；② 管线模型 reprebuf=0（不做二次预缓冲）；③ 移除管线模型 1200ms min_ms 地板和 1500ms 初始 prebuf 地板，统一 400ms 下限；④ 新增 underrun_start_t 追踪；⑤ 日志增强：管线模型额外记录 TTS 句间间隔统计 | Copilot |
| 2026-03-22 | v2.0.0322.18 | **SEA 区域矩阵修正 & 预检增强**：① `_REGION_MODEL_SUPPORT["southeastasia"]` 移除 gpt-4o、gpt-4o-mini（实测 6+ 次 "not supported" 错误），仅保留 gpt-4.1/gpt-4.1-mini/phi4-mm-realtime/phi4-mini；② `_on_start()` 预检同时检查静态矩阵和运行时错误缓存 `_endpoint_unsupported_models`，双重拦截不可用模型；③ 调查 Azure AI Portal 操场语音技术（AudioWorklet 零预缓冲 FIFO 直通方案），确认剩余 TTFT 波动（512ms-5826ms）为服务端 LLM 推理延迟，客户端无法优化 | Copilot |
