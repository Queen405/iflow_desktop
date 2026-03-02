# iFlow Bot Desktop

🤖 iFlow Bot 桌面客户端 — 基于 PySide6 (Qt) 的原生图形化管理界面。

## 功能

| 页面 | 功能说明 |
|------|---------|
| 📊 **仪表盘** | 查看 iFlow CLI 安装状态、Gateway 运行状态、模型配置、系统信息 |
| 💬 **对话** | 直接与 iFlow AI 对话，支持模型切换、思考模式、流式输出 |
| 🌐 **网关管理** | 启动/停止/重启 Gateway 服务，查看渠道状态 |
| ⚙️ **配置** | 可视化编辑 Driver、渠道配置，支持原始 JSON 编辑 |
| 📋 **会话管理** | 查看并管理渠道用户与 iFlow 会话的映射关系 |
| ⏰ **定时任务** | 创建和管理 AI 定时任务调度 |
| 📄 **日志** | 实时查看 Gateway 运行日志 |

## 安装

### 1. 安装依赖

```bash
cd iflow-desktop
pip install -e .
```

或手动安装:

```bash
pip install PySide6 pydantic pydantic-settings
```

### 2. 前置要求

- **Python** >= 3.10
- **iFlow CLI** 已安装并登录 (`npm install -g @iflow-ai/iflow-cli@latest`)
- **iflow-bot** 如需使用网关功能需安装 iflow-bot (`pip install iflow-bot`)

### 3. 运行

```bash
# 方式一：通过入口命令
iflow-desktop

# 方式二：通过 Python 模块
python -m iflow_desktop

# 方式三：直接运行
python src/iflow_desktop/app.py
```

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
        ├── main_window.py         # 主窗口
        ├── core/
        │   ├── __init__.py
        │   └── cli_bridge.py      # CLI 命令封装
        ├── widgets/
        │   ├── __init__.py
        │   ├── sidebar.py         # 侧边栏导航
        │   ├── dashboard.py       # 仪表盘
        │   ├── chat.py            # 对话界面
        │   ├── gateway.py         # 网关管理
        │   ├── config_editor.py   # 配置编辑
        │   ├── sessions.py        # 会话管理
        │   ├── cron.py            # 定时任务
        │   └── log_viewer.py      # 日志查看
        └── resources/
            ├── __init__.py
            └── style.py           # 暗色主题样式表
```

## 配置文件

桌面端使用与 iflow-bot CLI 相同的配置路径：

- 配置文件: `~/.iflow-bot/config.json`
- 工作空间: `~/.iflow-bot/workspace/`
- 会话映射: `~/.iflow-bot/session_mappings.json`
- 定时任务: `~/.iflow-bot/data/cron/jobs.json`
- Gateway 日志: `~/.iflow-bot/gateway.log`

## 打包为可执行文件

可使用 PyInstaller 打包为独立可执行文件:

```bash
pip install pyinstaller
pyinstaller --name "iFlow Desktop" --windowed --onefile src/iflow_desktop/app.py
```

## 技术栈

- **PySide6** (Qt 6) — 原生桌面 GUI 框架
- **Python 3.10+** — 编程语言
- **Catppuccin Mocha** — 暗色主题配色
