# Win32AzureSpeech — 问题追踪与推进计划

最后更新：2026-03-20

## 已确认背景
- 最终打包目标：Windows x86-64（.exe）
- 打包方式：本地 Windows 机器 + GitHub Actions 均可用
- 协作方式：Git 仓库，多人协同开发
- 代码签名：**不需要**（内部演示 Demo）
- Azure OpenAI 部署名：**不写死，改为设置页可配置**

## 问题清单

| ID | 严重程度 | 领域 | 问题描述 | 影响 | 决策 | 下一步 | 负责人 | 状态 |
|---|---|---|---|---|---|---|---|---|
| P1-001 | 高 | 构建/发布 | PyInstaller 无法从 macOS ARM64 交叉编译到 Windows x86-64 | Mac 环境无法直接产出目标 .exe | 使用 Windows 机器做最终打包；GitHub Actions 作为 CI 打包通道 | 添加 Windows 打包脚本和 GitHub Actions 工作流 | Dev | **已处理** |
| P1-002 | 高 | 运行时路径 | 代码使用 `Path.cwd()` 作为录音/导出目录 | 打包后 .exe 的写入路径不确定，可能无写权限 | 引入统一路径工具类，基于 .exe 所在目录或用户数据目录 | 重构 `app_paths.py`，更新所有文件 IO 调用 | Dev | **已处理** |
| P1-003 | 中 | Python 兼容性 | 开发机 Python 3.9 存在 Flet Tab monkey-patch | 跨环境行为不一致，维护成本高 | Windows 打包统一使用 Python 3.11+ | 在 README 和 GitHub Actions 中固定 Python 版本 | Dev | 进行中 |
| P1-004 | 中 | 安全/仓库治理 | 生成的敏感文件可能被误提交 | 泄露风险，历史记录污染 | 已创建 `.gitignore` 排除 config.json、输出目录、构建产物 | 团队 onboarding 文档补充说明 | Dev | 进行中 |
| P1-005 | 中 | Azure OpenAI 配置 | GPT-4o 部署名硬编码为 `gpt-4o` | 客户部署名不同时直接报错 | 改为设置页可配置字段并持久化 | 扩展配置 schema 和 UI 字段 | Dev | **已处理** |
| P1-006 | 中 | Azure Speech 配置 | Speech Endpoint 字段被收集但未实际用于调用（运行时用 region+key） | 用户误解，配置不一致 | 删除 Endpoint 字段，仅保留 region+key；连接验证逻辑不变 | 清理 UI 字段和 config schema | Dev | **已处理** |

## 推进计划

### Phase A — 运行时稳定（当前）✅ 已完成
1. 新建 `app_paths.py`，统一管理 .exe 同目录 / 开发目录的路径解析。
2. 替换所有 `Path.cwd()` 为 `get_data_dir()` 工具函数。
3. macOS 和 Windows 开发环境均可正常运行。

### Phase B — 打包流水线（当前）✅ 已完成
1. 新建 `build.spec`（PyInstaller 配置文件）。
2. 新建 `.github/workflows/build-windows.yml`，push/tag 时自动在 Windows Runner 产出 .exe artifact。
3. 本地 Windows 打包命令写入 README。

### Phase C — 团队协作规范（后续）
1. 补充 README：环境搭建、运行、打包、故障排查。
2. 制定依赖锁定与升级策略（`pip-compile` 或 `requirements.lock`）。
3. 在打包前加入最小冒烟测试。

## 当前阻塞项
- 日常功能开发：**无阻塞**。
- 发布阻塞：打包流水线已搭建，剩余事项为 Phase C 团队规范。

## 待确认事项
- [ ] 离线/弱网演示场景是否需要支持？（影响错误处理设计）
- [ ] 是否需要支持多套 Azure 配置快速切换？（如：演示环境 vs 客户环境）
