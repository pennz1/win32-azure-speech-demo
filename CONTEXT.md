# CONTEXT — Azure AI 语音演示台

## 项目概述
Windows x86-64 桌面 Demo（.exe），面向售前工程师向客户演示 Azure AI 语音能力。
Flet (Material Design 3) 暗色主题，Azure 蓝 #0078D4。

## 技术栈
| 层级 | 选型 |
|------|------|
| UI | Flet 0.28+ (MD3 暗色) |
| 语音转写 | azure-cognitiveservices-speech ≥1.37 (ConversationTranscriber + Diarization) |
| AI 纪要 | openai SDK → Azure OpenAI GPT-4o (stream) |
| 录音 | sounddevice + scipy → 16kHz mono .wav |
| 配置加密 | cryptography (Fernet)，密钥 ~/.azure_ai_demo/.encryption_key |
| 打包 | PyInstaller (build.spec)，GitHub Actions (.github/workflows/build-windows.yml) |
| Python | 开发：3.9+，打包建议 3.11+ |

## 文件结构
```
├── main.py                  # Flet 入口，壳层 + Tabs + 设置弹窗
├── transcription_tab.py     # Phase 1: 录音转写 + AI 纪要 Tab
├── audio_recorder.py        # 麦克风录音器 (sounddevice)
├── config_manager.py        # 加密配置读写 (Fernet)
├── app_paths.py             # 统一路径：dev 模式 / PyInstaller frozen
├── config.json              # 运行时加密配置（.gitignore 已排除）
├── requirements.txt         # 依赖清单
├── build.spec               # PyInstaller 打包配置
├── .github/workflows/       # GitHub Actions Windows 打包
├── Azure_AI_Demo_PRD_v2.0.md
├── ISSUES.md                # 问题追踪
└── CONTEXT.md               # ← 本文件
```

## PRD 阶段总览
| 阶段 | 模块 | 状态 |
|------|------|------|
| Phase 0 | 主应用壳层 + 导航框架 | ✅ 已完成 |
| Phase 1 | 录音转写 + AI 会议总结 | ✅ 功能主体完成，细节收尾中 |
| Phase 2 | GPT-4o Realtime 实时语音对话 | ⏳ 未开始 |
| Phase 3 | 同声传译 Live Interpreter | ⏳ 未开始 |

## Phase 0 — 已完成
- Flet 暗色主题 + 三 Tab 导航（转写 / 实时对话占位 / 同声传译占位）
- 顶部标题栏 + ⚙️ 设置按钮
- 底部状态栏（Azure 连接状态绿/黄/红 + 区域 + 版本）
- 设置弹窗：Speech Key / OpenAI Endpoint+Key+Deployment / Region
- config_manager.py：Fernet 加密 API Key，config.json 持久化
- app_paths.py：统一支持 dev 模式与 PyInstaller frozen 模式
- Python 3.9 Flet Tab 兼容性 monkey-patch（main.py 顶部）

## Phase 1 — 当前阶段
### 已完成
- F1-01 音频文件上传（FilePicker, .wav/.mp3/.m4a）
- F1-02 实时麦克风录制（sounddevice → 16kHz mono .wav）
- F1-03/04 Azure Speech 转写 + Diarization（ConversationTranscriber）
- F1-05 转写进度条（indeterminate → 完成 100%）
- F1-06 转写结果：Speaker 彩色气泡卡片 + 时间戳，ListView 自动滚动
- F1-07/08 GPT-4o 流式纪要生成（结构化 Markdown）
- F1-09 一键复制到剪贴板
- F1-10 导出 .txt（转写原文 + 纪要）
- F1-11 配置状态 Banner（4 态：全配置 / 仅 Speech / 仅 OpenAI / 未配置）

### 最近修复 (2026-03-20)
- Banner 从 3 态扩展为 4 态；修复"只配 OpenAI 未配 Speech"时仍显示笼统提示
- 用直接回调机制替代 pubsub 通知，修复"前往设置"按钮和保存后 Banner 不刷新
- Speech Key 缺失时，转写区域显示醒目红色提示而非仅弹 snackbar
- 按钮增加 tooltip 说明禁用原因

### 最近工程操作 (2026-03-21)
- 已初始化本地 Git 仓库，默认分支为 main
- 已创建 GitHub 远程仓库：https://github.com/pennz1/win32-azure-speech-demo
- 当前远程 origin：https://github.com/pennz1/win32-azure-speech-demo.git
- 已完成首个提交并推送：b8cdde9 (Initial commit)
- 已将 build.spec 纳入版本控制，Windows 与 GitHub Actions 可复用统一打包配置
- config.json 继续保留在 .gitignore 中，未上传到 GitHub
- 当前工作区无未提交代码变更，可直接在 Windows clone 后继续开发

### 待完成 / 已知问题
- 拖拽上传（F1-01 DragTarget）未实现，当前仅 FilePicker
- 转写预估剩余时间（F1-05 P1）未实现
- macOS 上 ConversationTranscriber Diarization 可能有限制，需 Windows 验证
- 录音权限：macOS 需手动授权麦克风

## 工程化状态
| 项目 | 状态 |
|------|------|
| .gitignore | ✅ 已创建 |
| Git 本地仓库 | ✅ 已创建 |
| GitHub 远程仓库 | ✅ 已创建并已首推 |
| build.spec | ✅ 已纳入 Git |
| GitHub Actions (Windows) | ✅ 工作流与打包配置已对齐 |
| README / onboarding 文档 | ❌ 待补充 |
| 冒烟测试 | ❌ 无 |

## Windows 接续开发指南
### 1. 获取代码
- clone 仓库：git clone https://github.com/pennz1/win32-azure-speech-demo.git
- 进入目录：cd win32-azure-speech-demo

### 2. 配置 Python 环境
- 建议 Python 3.11 x64
- 创建虚拟环境：python -m venv .venv
- 激活环境（PowerShell）：.venv\Scripts\Activate.ps1
- 安装依赖：pip install -r requirements.txt

### 3. 恢复本地配置
- config.json 没有上传到 GitHub，Windows 上首次运行时需要重新在设置页填写 Azure Speech / Azure OpenAI 配置
- 如果想直接沿用 Mac 上的加密配置，必须同时迁移两份文件：项目根目录下的 config.json，以及用户目录下的 .azure_ai_demo/.encryption_key
- 仅复制 config.json 不够，因为 API Key 使用 Fernet 加密；如果 Windows 上没有同一把密钥，load_config() 会把敏感字段回退为空字符串

### 4. 启动方式
- 开发模式运行：python main.py
- 首次在 Windows 上重点验证：麦克风权限、ConversationTranscriber 分离说话人效果、录音文件落盘、AI 纪要流式输出

### 5. 接下来优先事项
- 补 README / onboarding，避免后续在新机器重复排查环境问题
- 在 Windows 真机做一次完整冒烟测试，重点覆盖录音、转写、纪要、导出四条链路

## 关键决策
- 内部 Demo，**不需要**代码签名
- API Key **不写死**，设置页可配置 + Fernet 加密本地存储
- 开发 macOS，最终打包 Windows x86-64
- GPT-4o 部署名可配置（默认 gpt-4o）
- Speech 不使用 Endpoint 字段，仅 Region + Key

## 变更日志

| 日期 | 版本 | 本次完成内容 | 负责人 |
|------|------|-------------|--------|
| 2026-03-20 | v0.1 | Phase 0 壳层 + Phase 1 全部功能主体实现 | 张鹏程 |
| 2026-03-20 | v0.2 | 修复 Banner 4 态、pubsub 回调、转写缺 Key 提示、按钮 tooltip | 张鹏程 |
| 2026-03-21 | v0.3 | 初始化 Git、本地首提、创建 GitHub 仓库并完成首推；补充 Windows 接续开发说明 | 张鹏程 |
| 2026-03-21 | v0.4 | 将 build.spec 纳入版本控制，修复 Windows/CI 打包配置缺失风险 | 张鹏程 |
