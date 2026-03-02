# iFlow Desktop

🤖 iFlow CLI 桌面客户端 — 基于 PySide6 (Qt 6) 的原生图形化管理界面。

提供对 iFlow CLI 的可视化管理，支持 AI 对话、模型配置、会话管理、Gateway 管理等功能。

## 功能

| 页面 | 功能说明 |
|------|---------|
| 📊 **仪表盘** | 查看 iFlow CLI 安装状态、版本、登录状态、Gateway 运行状态、当前模型、系统信息 |
| 💬 **对话** | 与 AI 进行流式对话，支持模型切换、思考模式(Thinking)、会话历史管理 |
| 🔐 **认证** | 配置 API Key 和 Base URL，支持 API 模型列表获取 |
| 🤖 **Bot 管理** | 启动/停止/重启 Gateway 服务，配置工作空间 |
| ⚙️ **配置** | 可视化编辑 iFlow 设置（模型、MCP 服务器、Skills、Agents、自定义指令） |
| 📋 **日志** | 实时查看 iFlow CLI 和 Gateway 的运行日志 |

## 核心特性

- **流式对话**: 实时显示 AI 回复，支持思考过程展示
- **多模型支持**: 支持 CLI 内置模型和 API 模型列表（可切换模型源）
- **会话管理**: 自动保存对话历史，支持多会话切换和恢复
- **MCP 服务器**: 可视化配置和管理 MCP 服务器
- **Gateway 管理**: 一键启停 iflow-bot Gateway 服务
- **跨平台**: 支持 Windows、macOS、Linux

## 安装

### 1. 环境要求

- **Python** >= 3.10
- **Node.js** >= 16 (用于安装 iFlow CLI)

### 2. 安装 iFlow CLI

```bash
npm install -g @iflow-ai/iflow-cli@latest
```

### 3. 安装桌面客户端

```bash
cd iflow-desktop
pip install -e .
```

或手动安装依赖:

```bash
pip install PySide6>=6.6.0 pydantic>=2.0.0 pydantic-settings>=2.0.0
```

### 4. 运行

```bash
# 方式一：通过入口命令
iflow-desktop

# 方式二：通过 Python 模块
python -m iflow_desktop

# 方式三：直接运行
python src/iflow_desktop/app.py
```

## CLI 对接机制

本项目通过 `cli_bridge.py` 模块与 `iflow` CLI 进行深度集成：

### 1. 命令调用层 (`CLIBridge`)

- **智能命令查找**: 自动检测 iflow 安装路径，支持 npm 全局安装、本地开发等多种方式
- **跨平台执行**: Windows 使用 `CREATE_NO_WINDOW`，Unix 使用标准子进程
- **配置同步**: 直接读写 `~/.iflow/settings.json` 保持与 CLI 配置一致

### 2. 对话执行 (`IFlowChatWorker`)

- **后台线程**: 继承 `QThread`，避免阻塞 GUI
- **流式输出**: 使用 `os.read()` 实时读取 stdout，支持逐字显示
- **会话恢复**: 支持 `--resume` 参数继续历史对话

### 3. 状态监控 (`StatusMonitor`)

- **定时轮询**: 每 15 秒自动收集系统状态
- **多源数据**: 同时监控 CLI 状态、Gateway 状态、模型列表、MCP 服务器等

### 4. 模型管理

- **双源支持**: 支持 CLI Bundle 内置模型和 API 模型列表
- **智能缓存**: 模型列表缓存 10 分钟，减少重复请求
- **别名处理**: 自动规范化模型名称（如 glm5 → glm-5）

## 项目结构

```
iflow-desktop/
├── pyproject.toml                 # 项目配置
├── README.md
└── src/
    └── iflow_desktop/
        ├── __init__.py
        ├── __main__.py            # python -m 入口
        ├── app.py                 # 应用启动入口
        ├── main_window.py         # 主窗口和页面路由
        ├── core/
        │   ├── __init__.py
        │   ├── cli_bridge.py      # CLI 命令封装、配置管理、后台线程
        │   └── shared_utils.py    # 共享工具函数（解码、思考块提取等）
        ├── widgets/
        │   ├── __init__.py
        │   ├── sidebar.py         # 侧边栏导航
        │   ├── dashboard.py       # 仪表盘（系统状态概览）
        │   ├── chat.py            # 对话界面（流式输出、会话管理）
        │   ├── auth.py            # API 认证配置
        │   ├── iflow_config.py    # iFlow 配置（模型、MCP、Skills等）
        │   ├── bot_manager.py     # Gateway 管理
        │   └── log_viewer.py      # 日志查看器
        └── resources/
            ├── __init__.py
            ├── style.py           # 暗色主题样式表（Catppuccin Mocha）
            └── assets/            # 图标等资源文件
```

## 配置文件

### iFlow CLI 配置

- **配置目录**: `~/.iflow/`
- **设置文件**: `~/.iflow/settings.json` — 存储模型、Thinking 模式、MCP 服务器等
- **会话目录**: `~/.iflow/projects/<workspace>/session-*.jsonl`
- **日志目录**: `~/.iflow/log/`

### iFlow Bot 配置（可选，用于 Gateway）

- **配置目录**: `~/.iflow-bot/`
- **配置文件**: `~/.iflow-bot/config.json` — Gateway 配置、渠道设置
- **数据目录**: `~/.iflow-bot/data/`
- **日志文件**: `~/.iflow-bot/gateway.log`
- **PID 文件**: `~/.iflow-bot/gateway.pid`

## 技术栈

- **PySide6** (Qt 6.6+) — 原生桌面 GUI 框架
- **Python 3.10+** — 编程语言
- **Catppuccin Mocha** — 暗色主题配色方案

## 开发

### 运行测试

```bash
pytest
```

### 项目入口

```python
# 主入口
iflow_desktop.app:main

# 模块入口
python -m iflow_desktop
```

## 许可证

MIT License
