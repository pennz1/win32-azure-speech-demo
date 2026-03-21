# Azure AI 语音演示台

> Windows x86-64 桌面应用，面向售前工程师向客户演示 Azure AI 语音能力。
> Flet 0.82 · Material Design 3 · 深色/浅色/跟随系统主题 · Azure 蓝 #0078D4

---

## 功能模块

| Tab | 模块 | 核心能力 | 所需 Azure 服务 |
|-----|------|---------|----------------|
| 1 | **录音转写 & AI 会议总结** | 上传/录音 → 转写 → GPT 纪要 | Azure Speech + Azure OpenAI |
| 2 | **Voice Live 实时语音对话** | 全双工语音对话 · 打断 · 多角色 | Azure Voice Live (azure-ai-voicelive) |
| 3 | **同声传译 Live Interpreter** | 实时翻译 · TTS 播报 · 6 语种 | Azure Speech Translation |

### Tab 1 — 录音转写 & AI 纪要
- 支持**上传音频文件**（.wav / .mp3 / .m4a）或**实时麦克风录音**（16kHz mono）
- Azure Speech **说话人分离（Diarization）** + 语义分段 + 逐词时间戳
- GPT-4o **流式纪要生成**（结构化 Markdown）
- 一键复制 / 导出 .txt（用户可选保存位置）
- 性能指标：识别延迟 · 说话人数 · 词数 · 音频时长

### Tab 2 — Voice Live 实时语音对话
- 基于 **azure-ai-voicelive 1.1.0** SDK（WebSocket 全双工）
- 18 种 Azure Neural 语音（中/英/日/韩），温度 · 速率可调
- AI 角色预设（玩具助手 / 耳机助手 / 企业客服）
- 语义 VAD / 标准 VAD 可选，自动打断
- **自适应抖动缓冲 v3**：二次预缓冲 + underrun 计数反馈 + 3×jitter 自适应
- **客户端回声门控**：RMS 能量检测，AI 播放期间抑制麦克风回声
- 内置降噪 / 服务端回声消除 / 主动参与模式
- 性能指标：TTFT · E2E 延迟 · Token 用量 · 缓冲健康

### Tab 3 — 同声传译 Live Interpreter
- Azure Speech Translation 连续实时翻译
- 自动语言检测（中/英/日/韩，At-start LID 4 语种上限）
- 目标语言 6 种（中/英/日/韩/德/法），运行中切换自动重启
- **边说边译 Live Bubble**：说话过程中实时显示译文
- Azure Neural TTS 译文语音播放（复用 Synthesizer 降低延迟）
- 男/女声切换 + 具体音色可选（每语种 3男3女）
- 性能指标：翻译延迟 · 句数 · 检测语言 · 延迟趋势图

---

## 技术栈

| 层级 | 选型 |
|------|------|
| UI | Flet **0.82+**（MD3 深色/浅色/跟随系统） |
| 语音转写 | azure-cognitiveservices-speech ≥1.37（ConversationTranscriber + Diarization） |
| 实时对话 | azure-ai-voicelive ≥1.1.0（WebSocket 全双工） |
| AI 纪要 | openai SDK → Azure OpenAI GPT-4o（stream） |
| 音频 | sounddevice（采集 16kHz）+ numpy（PCM 处理 24kHz） |
| 配置加密 | cryptography（Fernet），密钥 `~/.azure_ai_demo/.encryption_key` |
| 打包 | PyInstaller（onefile .exe） |
| 安装包 | NSIS 3.11（安装向导 + 快捷方式 + 卸载） |
| Python | **3.11+**（推荐 3.14，当前验证环境） |

---

## 快速开始

### 1. 克隆 & 安装依赖

```powershell
git clone https://github.com/pennz1/win32-azure-speech-demo.git
cd win32-azure-speech-demo

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 运行

```powershell
python main.py
```

### 3. 配置 Azure 凭据

启动后点击右上角 ⚙️ **设置**，填写：

| 字段 | 说明 |
|------|------|
| Speech API Key | Azure Speech 服务密钥 |
| Region | Speech 服务区域（如 `eastus`） |
| OpenAI Endpoint | 形如 `https://xxx.openai.azure.com/` |
| OpenAI API Key | Azure OpenAI 服务密钥 |
| GPT-4o 部署名 | Chat 部署名（默认 `gpt-4o`） |
| Voice Live Endpoint | Voice Live 端点 |
| Voice Live API Key | Voice Live 密钥 |

> 配置使用 Fernet 加密保存到本地 `config.json`，密钥存于 `~/.azure_ai_demo/.encryption_key`。

---

## 构建 & 打包

### 一键构建（exe + 安装包）

```powershell
.\build_installer.ps1
```

### 仅构建 exe

```powershell
pyinstaller AzureAISpeechDemo.spec -y
```

### 仅打包安装程序（需先有 exe）

```powershell
makensis installer.nsi
```

产出：
- `dist/AzureAISpeechDemo.exe`（~132 MB 单文件）
- `dist/AzureAISpeechDemo_Setup_x.x.x.exe`（~131 MB 安装包）

---

## 项目结构

```
├── main.py                  # Flet 入口 + Tabs + 设置弹窗
├── transcription_tab.py     # Tab 1: 录音转写 + AI 纪要
├── realtime_tab.py          # Tab 2: Voice Live 实时语音对话
├── interpreter_tab.py       # Tab 3: 同声传译 Live Interpreter
├── audio_recorder.py        # 麦克风录音器 (sounddevice, 16kHz)
├── config_manager.py        # 加密配置读写 (Fernet)
├── app_paths.py             # 统一路径 (dev / frozen)
├── requirements.txt         # Python 依赖
├── AzureAISpeechDemo.spec   # PyInstaller 打包配置
├── installer.nsi            # NSIS 安装包脚本
├── build_installer.ps1      # 一键构建脚本
├── build.spec               # PyInstaller 备用 spec
├── app.ico                  # 应用图标
├── docs/
│   ├── CONTEXT.md           # 项目上下文 & 技术决策
│   ├── ISSUES.md            # 问题追踪
│   └── Azure_AI_Demo_PRD_v2.0.md  # 产品需求文档
└── .github/workflows/       # GitHub Actions 自动构建
```

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| `Unknown control: FilePicker` | Flet 0.82 中 FilePicker 是 Service，需注册到 `page.services` |
| 中文显示方块/乱码 | 设置 `page.fonts` 指定中文字体路径 |
| PowerShell 无法执行 .ps1 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Azure Speech 连接失败 | 检查 Region 格式（如 `eastus`，不含 `https://`） |
| GPT-4o 调用失败 | Endpoint 末尾需带 `/`，部署名需与 Portal 一致 |
| AI 语音卡顿 | 自适应缓冲会在 2~3 轮对话后自动调优；高 jitter 网络建议使用 VPN |
| 音箱回声打断 AI | 客户端回声门控已启用，建议使用耳机或调低音箱音量 |

---

## 安全说明

- `config.json`（加密 API Key）已加入 `.gitignore`，不提交到 Git
- 加密密钥存储于用户主目录 `~/.azure_ai_demo/`，不在项目目录中
- 本程序为内部演示 Demo，无需代码签名

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v2.0.0322.11 | 2026-03-22 | 自适应抖动缓冲 v3 + 客户端回声门控 |
| v2.0.0322.10 | 2026-03-22 | 修复 OUT_BLOCKSIZE / audio_buf 未定义 |
| v2.0.0322.9 | 2026-03-22 | 自适应抖动缓冲 v2 + 导出路径选择 |
| v2.0.0322.7 | 2026-03-22 | 浅色主题优化 + 性能指标 pill 重构 |
| v2.0.0322.4 | 2026-03-22 | 主题切换 + TTFT/E2E/Token 指标 |
| v2.0.0322.2 | 2026-03-22 | 边说边译 Live Bubble + 流式翻译优化 |
| v2.0.0322.1 | 2026-03-22 | UI 重构（三步骤流程 + 主从布局） |
| v0.4 | 2026-03-21 | Phase 2 + Phase 3 完成 |
| v0.1 | 2026-03-20 | Phase 0 壳层 + Phase 1 全功能 |

---

## 许可

内部项目，仅供演示使用。
| v0.5 | 2026-03-21 | Flet 0.82 全量 API 迁移；flet pack 打包 .exe 成功（136MB） |
| v0.7 | 2026-03-21 | Phase 2 realtime_tab 集成；Phase 3 interpreter_tab 全功能开发 |
| v0.8 | 2026-03-21 | 修复 Service 注册问题（FilePicker/Clipboard）；修复中文字体渲染 |
