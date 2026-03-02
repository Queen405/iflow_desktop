"""iFlow 设置页面 - 管理 iflow CLI 配置（模型、MCP、Skills、Agents、Commands）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QCheckBox,
    QGroupBox, QGridLayout, QMessageBox, QTabWidget,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QTextEdit,
    QFileDialog, QSpinBox, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal

from iflow_desktop.core.cli_bridge import CLIBridge, IFlowSettings
from iflow_desktop.core.shared_utils import decode_bytes as _decode, model_display_name, subprocess_kwargs


# =====================================================================
# MCP 服务器编辑对话框
# =====================================================================
class MCPServerDialog(QDialog):
    """添加/编辑 MCP 服务器对话框。"""

    def __init__(self, name: str = "", config: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑 MCP 服务器" if name else "添加 MCP 服务器")
        self.setMinimumWidth(500)
        self._editing_name = name
        self._init_ui(name, config or {})

    def _init_ui(self, name: str, config: dict):
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("名称:"), 0, 0)
        self._name_edit = QLineEdit(name)
        self._name_edit.setPlaceholderText("如: my-mcp-server")
        if name:
            self._name_edit.setReadOnly(True)
        grid.addWidget(self._name_edit, 0, 1)

        grid.addWidget(QLabel("命令:"), 1, 0)
        self._command_edit = QLineEdit(config.get("command", ""))
        self._command_edit.setPlaceholderText("如: npx, uvx, node, python")
        grid.addWidget(self._command_edit, 1, 1)

        grid.addWidget(QLabel("参数:"), 2, 0)
        self._args_edit = QLineEdit(
            " ".join(config.get("args", []))
        )
        self._args_edit.setPlaceholderText("空格分隔，如: -y @iflow-mcp/server-name")
        grid.addWidget(self._args_edit, 2, 1)

        grid.addWidget(QLabel("描述:"), 3, 0)
        self._desc_edit = QLineEdit(config.get("description", ""))
        self._desc_edit.setPlaceholderText("可选描述")
        grid.addWidget(self._desc_edit, 3, 1)

        grid.addWidget(QLabel("环境变量:"), 4, 0)
        self._env_edit = QPlainTextEdit()
        self._env_edit.setMaximumHeight(80)
        self._env_edit.setPlaceholderText("每行一个: KEY=VALUE")
        env = config.get("env", {})
        if env:
            self._env_edit.setPlainText(
                "\n".join(f"{k}={v}" for k, v in env.items())
            )
        grid.addWidget(self._env_edit, 4, 1)

        self._disabled_cb = QCheckBox("禁用此服务器")
        self._disabled_cb.setChecked(config.get("disabled", False))
        grid.addWidget(self._disabled_cb, 5, 0, 1, 2)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, dict]:
        name = self._name_edit.text().strip()
        args_text = self._args_edit.text().strip()
        args = args_text.split() if args_text else []

        env = {}
        for line in self._env_edit.toPlainText().strip().splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

        config: dict = {
            "command": self._command_edit.text().strip(),
            "args": args,
        }
        if self._desc_edit.text().strip():
            config["description"] = self._desc_edit.text().strip()
        if env:
            config["env"] = env
        if self._disabled_cb.isChecked():
            config["disabled"] = True

        return name, config


# =====================================================================
# Agent 编辑对话框
# =====================================================================
class AgentEditDialog(QDialog):
    """编辑/创建 Agent 对话框。"""

    def __init__(self, name: str = "", content: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑代理" if name else "创建代理")
        self.setMinimumSize(600, 400)
        self._init_ui(name, content)

    def _init_ui(self, name: str, content: str):
        layout = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("代理名称:"))
        self._name_edit = QLineEdit(name)
        self._name_edit.setPlaceholderText("agent-name (不含 .md 后缀)")
        if name:
            self._name_edit.setReadOnly(True)
        name_row.addWidget(self._name_edit, 1)
        layout.addLayout(name_row)

        layout.addWidget(QLabel("代理指令 (Markdown):"))
        self._content_edit = QPlainTextEdit()
        self._content_edit.setPlainText(content)
        self._content_edit.setPlaceholderText("在此编写代理的系统指令...")
        layout.addWidget(self._content_edit, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, str]:
        return self._name_edit.text().strip(), self._content_edit.toPlainText()


# =====================================================================
# 在线仓库加载线程
# =====================================================================
class _OnlineFetchWorker(QThread):
    """后台线程加载在线仓库数据，避免阻塞 UI。"""
    finished = Signal(dict)  # {items, total} or {error}

    def __init__(self, repo_type: str, page: int, size: int, search: str, parent=None):
        super().__init__(parent)
        self.repo_type = repo_type
        self.page = page
        self.size = size
        self.search = search

    def run(self):
        try:
            if self.repo_type == "agents":
                result = CLIBridge.fetch_online_agents(self.page, self.size, self.search)
            elif self.repo_type == "skills":
                result = CLIBridge.fetch_online_skills(self.page, self.size, self.search)
            elif self.repo_type == "commands":
                result = CLIBridge.fetch_online_commands(self.page, self.size, self.search)
            elif self.repo_type == "mcp":
                result = CLIBridge.fetch_online_mcp_servers(self.page, self.size, self.search)
            else:
                result = {"items": [], "total": 0}
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({"items": [], "total": 0, "error": str(e)})


# =====================================================================
# 在线仓库浏览对话框
# =====================================================================
class OnlineRepoBrowser(QDialog):
    """在线仓库浏览与安装对话框，支持 agents / skills / commands / mcp。"""

    # install_requested 信号: (repo_type, name_or_id, config_dict)
    install_requested = Signal(str, str, dict)

    _TITLES = {
        "agents": "在线代理仓库",
        "skills": "在线技能仓库",
        "commands": "在线命令市场",
        "mcp": "在线 MCP 服务器",
    }
    _PAGE_SIZE = 15

    def __init__(self, repo_type: str, parent=None):
        super().__init__(parent)
        self.repo_type = repo_type
        self.setWindowTitle(self._TITLES.get(repo_type, "在线仓库"))
        self.setMinimumSize(900, 600)
        self._current_page = 1
        self._total = 0
        self._items: list[dict] = []
        self._worker: _OnlineFetchWorker | None = None
        self._init_ui()
        self._fetch_page(1)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 搜索栏
        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索...")
        self._search_edit.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_edit, 1)

        search_btn = QPushButton("🔍 搜索")
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        # 主区域: 左列表 + 右预览
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)

        # 左: 列表
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._table.verticalHeader().setVisible(False)
        self._table.currentCellChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._table, 1)

        # 分页
        page_row = QHBoxLayout()
        self._prev_btn = QPushButton("◀ 上一页")
        self._prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self._prev_btn)
        self._page_label = QLabel("第 1 页")
        page_row.addWidget(self._page_label)
        self._next_btn = QPushButton("下一页 ▶")
        self._next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self._next_btn)
        page_row.addStretch()
        self._total_label = QLabel("")
        page_row.addWidget(self._total_label)
        left_layout.addLayout(page_row)

        splitter.addWidget(left)

        # 右: 预览 + 安装
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self._preview_title = QLabel("选择一项查看详情")
        self._preview_title.setObjectName("PageTitle")
        self._preview_title.setWordWrap(True)
        right_layout.addWidget(self._preview_title)

        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        right_layout.addWidget(self._preview_text, 1)

        self._install_btn = QPushButton("📥  安装")
        self._install_btn.setObjectName("PrimaryBtn")
        self._install_btn.setFixedHeight(36)
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._on_install)
        right_layout.addWidget(self._install_btn)

        splitter.addWidget(right)
        splitter.setSizes([500, 400])
        layout.addWidget(splitter, 1)

        # 状态
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # 设置列
        self._setup_columns()

    def _setup_columns(self):
        if self.repo_type == "mcp":
            self._table.setColumnCount(4)
            self._table.setHorizontalHeaderLabels(["名称", "描述", "传输", "语言"])
        elif self.repo_type == "agents":
            self._table.setColumnCount(4)
            self._table.setHorizontalHeaderLabels(["名称", "描述", "类别", "模型"])
        elif self.repo_type == "skills":
            self._table.setColumnCount(3)
            self._table.setHorizontalHeaderLabels(["名称", "描述", "类别"])
        else:  # commands
            self._table.setColumnCount(4)
            self._table.setHorizontalHeaderLabels(["名称", "描述", "类别", "模型"])

        header = self._table.horizontalHeader()
        header.setSectionsMovable(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in range(2, self._table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

    def _fetch_page(self, page: int):
        self._status_label.setText("⏳ 正在加载...")
        self._table.setRowCount(0)
        self._current_page = page

        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

        self._worker = _OnlineFetchWorker(
            self.repo_type, page, self._PAGE_SIZE,
            self._search_edit.text().strip(), parent=self
        )
        self._worker.finished.connect(self._on_data_loaded)
        self._worker.start()

    def _on_data_loaded(self, result: dict):
        self._items = result.get("items", [])
        self._total = result.get("total", 0)
        error = result.get("error", "")

        if error:
            self._status_label.setText(f"❌ 加载失败: {error}")
            return

        total_pages = max(1, (self._total + self._PAGE_SIZE - 1) // self._PAGE_SIZE)
        self._page_label.setText(f"第 {self._current_page}/{total_pages} 页")
        self._total_label.setText(f"共 {self._total} 项")
        self._prev_btn.setEnabled(self._current_page > 1)
        self._next_btn.setEnabled(self._current_page < total_pages)
        self._status_label.setText("")

        self._table.setRowCount(len(self._items))
        for i, item in enumerate(self._items):
            if self.repo_type == "mcp":
                self._table.setItem(i, 0, QTableWidgetItem(item.get("name", "")))
                desc = item.get("description", "")
                self._table.setItem(i, 1, QTableWidgetItem(desc[:60] + "..." if len(desc) > 60 else desc))
                self._table.setItem(i, 2, QTableWidgetItem(", ".join(item.get("transports", []))))
                self._table.setItem(i, 3, QTableWidgetItem(", ".join(item.get("languages", []))))
            elif self.repo_type == "agents":
                self._table.setItem(i, 0, QTableWidgetItem(item.get("nameZh") or item.get("name", "")))
                desc = item.get("descriptionZh") or item.get("description", "")
                self._table.setItem(i, 1, QTableWidgetItem(desc[:60] + "..." if len(desc) > 60 else desc))
                self._table.setItem(i, 2, QTableWidgetItem(item.get("categoryZh") or item.get("category", "")))
                self._table.setItem(i, 3, QTableWidgetItem(item.get("modelName", "")))
            elif self.repo_type == "skills":
                self._table.setItem(i, 0, QTableWidgetItem(item.get("name", "")))
                desc = item.get("description", "")
                self._table.setItem(i, 1, QTableWidgetItem(desc[:60] + "..." if len(desc) > 60 else desc))
                self._table.setItem(i, 2, QTableWidgetItem(item.get("category", "")))
            else:  # commands
                self._table.setItem(i, 0, QTableWidgetItem(item.get("nameZh") or item.get("name", "")))
                desc = item.get("descriptionZh") or item.get("description", "")
                self._table.setItem(i, 1, QTableWidgetItem(desc[:60] + "..." if len(desc) > 60 else desc))
                self._table.setItem(i, 2, QTableWidgetItem(item.get("category", "")))
                self._table.setItem(i, 3, QTableWidgetItem(item.get("modelName", "")))

        self._preview_title.setText("选择一项查看详情")
        self._preview_text.clear()
        self._install_btn.setEnabled(False)

    def _on_selection_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        self._install_btn.setEnabled(True)

        # 生成预览
        if self.repo_type == "mcp":
            title = item.get("name", "")
            self._preview_title.setText(title)
            lines = [
                f"**描述:** {item.get('description', '无')}",
                "",
                f"**传输方式:** {', '.join(item.get('transports', []))}",
                "",
                f"**语言:** {', '.join(item.get('languages', []))}",
                "",
                f"**平台:** {item.get('platform', '-')}",
                "",
                "---",
                "",
                "**安装配置:**",
                "",
                f"```",
                f"命令: {item.get('command', '')}",
                f"参数: {' '.join(item.get('args', []))}",
            ]
            env = item.get("env", {})
            if env:
                lines.append("环境变量:")
                for k, v in env.items():
                    lines.append(f"  {k}={v}")
            lines.append("```")
        elif self.repo_type == "agents":
            title = item.get("nameZh") or item.get("name", "")
            self._preview_title.setText(f"{title} (ID: {item.get('id', '')})")
            desc = item.get("descriptionZh") or item.get("description", "")
            lines = [
                f"**名称:** {item.get('name', '')}",
                "",
                f"**中文名:** {item.get('nameZh', '')}",
                "",
                f"**描述:** {desc}",
                "",
                f"**类别:** {item.get('categoryZh') or item.get('category', '')}",
                "",
                f"**标签:** {', '.join(item.get('tagsZh') or item.get('tags', []))}",
                "",
                f"**推荐模型:** {item.get('modelName', '-')}",
                "",
                f"**版本:** {item.get('version', '')}",
                "",
                f"**作者:** {item.get('authorId', '')}",
            ]
            detail = item.get("detailContext", "")
            if detail:
                lines.extend(["", "---", "", "**代理指令预览:**", "", detail[:1000]])
                if len(detail) > 1000:
                    lines.append("...(截断)")
        elif self.repo_type == "skills":
            title = item.get("name", "")
            self._preview_title.setText(f"{title} (ID: {item.get('skillId') or item.get('id', '')})")
            lines = [
                f"**名称:** {title}",
                "",
                f"**描述:** {item.get('description', '')}",
                "",
                f"**类别:** {item.get('category', '')}",
                "",
                f"**标签:** {item.get('tags', '')}",
                "",
                f"**版本:** {item.get('version', '')}",
                "",
                f"**作者:** {item.get('authorId', '')}",
            ]
        else:  # commands
            title = item.get("nameZh") or item.get("name", "")
            self._preview_title.setText(f"{title} (ID: {item.get('id', '')})")
            desc = item.get("descriptionZh") or item.get("description", "")
            lines = [
                f"**名称:** {item.get('name', '')}",
                "",
                f"**中文名:** {item.get('nameZh', '')}",
                "",
                f"**描述:** {desc}",
                "",
                f"**类别:** {item.get('category', '')}",
                "",
                f"**推荐模型:** {item.get('modelName', '-')}",
                "",
                f"**标签:** {', '.join(item.get('tags', []))}",
                "",
                f"**版本:** {item.get('version', '')}",
                "",
                f"**作者:** {item.get('authorId', '')}",
            ]

        self._preview_text.setMarkdown("\n".join(lines))

    def _on_search(self):
        self._fetch_page(1)

    def _prev_page(self):
        if self._current_page > 1:
            self._fetch_page(self._current_page - 1)

    def _next_page(self):
        total_pages = max(1, (self._total + self._PAGE_SIZE - 1) // self._PAGE_SIZE)
        if self._current_page < total_pages:
            self._fetch_page(self._current_page + 1)

    def _on_install(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]

        if self.repo_type == "mcp":
            name = item.get("configName") or item.get("name", "")
            config = {
                "command": item.get("command", ""),
                "args": item.get("args", []),
            }
            env = item.get("env", {})
            if env:
                config["env"] = env
            desc = item.get("description", "")
            if desc:
                config["description"] = desc[:100]
            self.install_requested.emit(self.repo_type, name, config)
        else:
            name_or_id = str(item.get("name") or item.get("skillId") or item.get("id", ""))
            self.install_requested.emit(self.repo_type, name_or_id, item)


# =====================================================================
# iFlow 设置页面
# =====================================================================
class IFlowConfigPage(QWidget):
    """iFlow CLI 设置管理页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._load_all()

    def on_status_update(self, data: dict):
        """接收 StatusMonitor 推送的模型列表。"""
        models_ws = data.get("models_with_source", [])
        if models_ws and hasattr(self, "_model_combo"):
            current = self._get_selected_model()
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            for m in models_ws:
                prefix = "CLI" if m["source"] == "cli" else "API"
                display_name = model_display_name(m["name"])
                self._model_combo.addItem(f"[{prefix}] {display_name}", m["name"])
            for i in range(self._model_combo.count()):
                if self._model_combo.itemData(i) == current:
                    self._model_combo.setCurrentIndex(i)
                    break
            else:
                if current:
                    self._model_combo.setCurrentText(current)
            self._model_combo.blockSignals(False)

    def _init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # 标题栏
        header_frame = QFrame()
        header_frame.setObjectName("ChatToolbar")
        header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(32, 0, 32, 0)

        title = QLabel("iFlow 设置")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)

        header_layout.addStretch()

        save_btn = QPushButton("💾  保存全部")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save_general)
        header_layout.addWidget(save_btn)

        reload_btn = QPushButton("🔄  重新加载")
        reload_btn.setFixedHeight(36)
        reload_btn.clicked.connect(self._load_all)
        header_layout.addWidget(reload_btn)

        main.addWidget(header_frame)

        subtitle = QLabel(f"    配置文件: {IFlowSettings.get_path()}")
        subtitle.setObjectName("PageSubtitle")
        main.addWidget(subtitle)

        # Tab 页
        self._tabs = QTabWidget()
        self._tabs.addTab(self._create_general_tab(), "🔧 常规设置")
        self._tabs.addTab(self._create_mcp_tab(), "🔌 MCP 服务器")
        self._tabs.addTab(self._create_skills_tab(), "🛠️ 技能")
        self._tabs.addTab(self._create_agents_tab(), "🤖 代理")
        self._tabs.addTab(self._create_commands_tab(), "📦 命令")
        main.addWidget(self._tabs, 1)

    # ------------------------------------------------------------------
    # 常规设置 Tab
    # ------------------------------------------------------------------
    def _create_general_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 16, 24, 16)

        # 模型设置
        model_group = QGroupBox("模型设置")
        mg = QGridLayout(model_group)

        mg.addWidget(QLabel("当前模型:"), 0, 0)
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumWidth(200)
        mg.addWidget(self._model_combo, 0, 1)

        self._use_api_models_cb = QCheckBox("使用 API Key 管理的在线模型列表")
        self._use_api_models_cb.setToolTip(
            "启用后通过 API Key 从 /v1/models 接口获取模型列表，\n"
            "关闭时使用 iflow CLI 内置的模型列表（默认）"
        )
        self._use_api_models_cb.stateChanged.connect(self._on_api_models_toggled)
        mg.addWidget(self._use_api_models_cb, 1, 0, 1, 2)

        self._api_model_hint = QLabel("")
        self._api_model_hint.setObjectName("CardLabel")
        self._api_model_hint.setWordWrap(True)
        mg.addWidget(self._api_model_hint, 2, 0, 1, 2)

        self._thinking_cb = QCheckBox("启用思考模式 (Thinking)")
        mg.addWidget(self._thinking_cb, 3, 0, 1, 2)

        self._checkpointing_cb = QCheckBox("启用检查点 (Checkpointing)")
        mg.addWidget(self._checkpointing_cb, 4, 0, 1, 2)

        layout.addWidget(model_group)

        # 界面设置
        ui_group = QGroupBox("界面设置")
        ug = QGridLayout(ui_group)

        ug.addWidget(QLabel("语言:"), 0, 0)
        self._language_combo = QComboBox()
        self._language_combo.addItems(["zh-CN", "en-US", "ja-JP"])
        ug.addWidget(self._language_combo, 0, 1)

        ug.addWidget(QLabel("偏好编辑器:"), 1, 0)
        self._editor_combo = QComboBox()
        self._editor_combo.addItems(["vscode", "cursor", "windsurf", "vim"])
        ug.addWidget(self._editor_combo, 1, 1)

        layout.addWidget(ui_group)

        # 自定义指令
        inst_group = QGroupBox("自定义指令")
        ig = QVBoxLayout(inst_group)

        inst_desc = QLabel("为 AI 提供额外的系统指令，每次对话都会附带这些指令")
        inst_desc.setObjectName("CardLabel")
        inst_desc.setWordWrap(True)
        ig.addWidget(inst_desc)

        self._instructions_edit = QPlainTextEdit()
        self._instructions_edit.setPlaceholderText("在此输入自定义指令...")
        self._instructions_edit.setMaximumHeight(120)
        ig.addWidget(self._instructions_edit)

        layout.addWidget(inst_group)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ------------------------------------------------------------------
    # MCP 服务器 Tab
    # ------------------------------------------------------------------
    def _create_mcp_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        desc = QLabel("管理 MCP (Model Context Protocol) 服务器，为 AI 提供额外工具能力")
        desc.setObjectName("CardLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕  添加服务器")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.clicked.connect(self._add_mcp_server)
        btn_row.addWidget(add_btn)

        browse_btn = QPushButton("🌐  浏览在线仓库")
        browse_btn.clicked.connect(lambda: self._open_online_browser("mcp"))
        btn_row.addWidget(browse_btn)

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.clicked.connect(self._load_mcp)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._mcp_table = QTableWidget()
        self._mcp_table.setColumnCount(5)
        self._mcp_table.setHorizontalHeaderLabels(["名称", "命令", "状态", "描述", "操作"])
        self._mcp_table.horizontalHeader().setStretchLastSection(False)
        self._mcp_table.horizontalHeader().setSectionsMovable(False)
        self._mcp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._mcp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._mcp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._mcp_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._mcp_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._mcp_table.horizontalHeader().resizeSection(4, 240)
        self._mcp_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._mcp_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._mcp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._mcp_table.verticalHeader().setVisible(False)
        layout.addWidget(self._mcp_table, 1)

        return page

    # ------------------------------------------------------------------
    # Skills Tab
    # ------------------------------------------------------------------
    def _create_skills_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        desc = QLabel("管理已安装的 Skills，Skills 为 AI 提供特定领域的能力")
        desc.setObjectName("CardLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕  安装技能")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.clicked.connect(self._install_skill)
        btn_row.addWidget(add_btn)

        browse_btn = QPushButton("🌐  浏览在线仓库")
        browse_btn.clicked.connect(lambda: self._open_online_browser("skills"))
        btn_row.addWidget(browse_btn)

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.clicked.connect(self._load_skills)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._skills_table = QTableWidget()
        self._skills_table.setColumnCount(3)
        self._skills_table.setHorizontalHeaderLabels(["名称", "路径", "操作"])
        self._skills_table.horizontalHeader().setStretchLastSection(False)
        self._skills_table.horizontalHeader().setSectionsMovable(False)
        self._skills_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._skills_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._skills_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._skills_table.horizontalHeader().resizeSection(2, 120)
        self._skills_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._skills_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._skills_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._skills_table.verticalHeader().setVisible(False)
        layout.addWidget(self._skills_table, 1)

        hint = QLabel("提示：使用 iflow skill add <name-or-id> 从在线仓库安装技能")
        hint.setObjectName("CardLabel")
        layout.addWidget(hint)

        return page

    # ------------------------------------------------------------------
    # Agents Tab
    # ------------------------------------------------------------------
    def _create_agents_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        desc = QLabel("管理 Agents (代理)，每个代理是一个 Markdown 文件定义的特定角色")
        desc.setObjectName("CardLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕  创建代理")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.clicked.connect(self._create_agent)
        btn_row.addWidget(add_btn)

        browse_btn = QPushButton("🌐  浏览在线仓库")
        browse_btn.clicked.connect(lambda: self._open_online_browser("agents"))
        btn_row.addWidget(browse_btn)

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.clicked.connect(self._load_agents)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._agents_table = QTableWidget()
        self._agents_table.setColumnCount(3)
        self._agents_table.setHorizontalHeaderLabels(["名称", "路径", "操作"])
        self._agents_table.horizontalHeader().setStretchLastSection(False)
        self._agents_table.horizontalHeader().setSectionsMovable(False)
        self._agents_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._agents_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._agents_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._agents_table.horizontalHeader().resizeSection(2, 220)
        self._agents_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._agents_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._agents_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._agents_table.verticalHeader().setVisible(False)
        layout.addWidget(self._agents_table, 1)

        return page

    # ------------------------------------------------------------------
    # Commands Tab
    # ------------------------------------------------------------------
    def _create_commands_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        desc = QLabel("管理自定义命令，命令可以从 iFlow 市场安装或本地创建")
        desc.setObjectName("CardLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕  安装命令")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.clicked.connect(self._install_command)
        btn_row.addWidget(add_btn)

        browse_btn = QPushButton("🌐  浏览在线市场")
        browse_btn.clicked.connect(lambda: self._open_online_browser("commands"))
        btn_row.addWidget(browse_btn)

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.clicked.connect(self._load_commands)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._commands_table = QTableWidget()
        self._commands_table.setColumnCount(3)
        self._commands_table.setHorizontalHeaderLabels(["名称", "路径", "操作"])
        self._commands_table.horizontalHeader().setStretchLastSection(False)
        self._commands_table.horizontalHeader().setSectionsMovable(False)
        self._commands_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._commands_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._commands_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._commands_table.horizontalHeader().resizeSection(2, 120)
        self._commands_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._commands_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._commands_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._commands_table.verticalHeader().setVisible(False)
        layout.addWidget(self._commands_table, 1)

        hint = QLabel("CLI: iflow commands add <name-or-id> | iflow commands list --online")
        hint.setObjectName("CardLabel")
        layout.addWidget(hint)

        return page

    # ------------------------------------------------------------------
    # 模型列表辅助方法
    # ------------------------------------------------------------------
    def _populate_model_combo(self, selected_model: str = ""):
        """加载模型列表到下拉框（带来源标签）。"""
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        models = CLIBridge.get_iflow_models_with_source()
        for m in models:
            prefix = "CLI" if m["source"] == "cli" else "API"
            display_name = model_display_name(m["name"])
            self._model_combo.addItem(f"[{prefix}] {display_name}", m["name"])
        if selected_model:
            for i in range(self._model_combo.count()):
                if self._model_combo.itemData(i) == selected_model:
                    self._model_combo.setCurrentIndex(i)
                    break
            else:
                self._model_combo.setCurrentText(selected_model)
        self._model_combo.blockSignals(False)

    def _get_selected_model(self) -> str:
        """获取当前选中的模型名称（去除来源前缀）。"""
        from iflow_desktop.core.shared_utils import get_selected_model_from_combo
        return get_selected_model_from_combo(self._model_combo)

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _load_all(self):
        """加载所有配置。"""
        self._load_general()
        self._load_mcp()
        self._load_skills()
        self._load_agents()
        self._load_commands()

    def _load_general(self):
        settings = IFlowSettings.load()
        model = settings.get("modelName", "")

        # 模型源开关
        use_api = IFlowSettings.get_use_api_models()
        self._use_api_models_cb.blockSignals(True)
        self._use_api_models_cb.setChecked(use_api)
        self._use_api_models_cb.blockSignals(False)
        self._update_api_model_hint(use_api)

        self._populate_model_combo(model)

        self._thinking_cb.setChecked(settings.get("thinking", False))

        checkpointing = settings.get("checkpointing", {})
        self._checkpointing_cb.setChecked(
            checkpointing.get("enabled", False) if isinstance(checkpointing, dict) else bool(checkpointing)
        )

        self._language_combo.setCurrentText(settings.get("language", "zh-CN"))
        self._editor_combo.setCurrentText(settings.get("preferredEditor", "vscode"))
        self._instructions_edit.setPlainText(
            settings.get("customInstructions", "")
        )

    def _load_mcp(self):
        servers = IFlowSettings.get_mcp_servers()
        self._mcp_table.setRowCount(len(servers))
        for i, (name, cfg) in enumerate(servers.items()):
            self._mcp_table.setItem(i, 0, QTableWidgetItem(name))

            cmd = cfg.get("command", "")
            args = " ".join(cfg.get("args", []))
            self._mcp_table.setItem(i, 1, QTableWidgetItem(f"{cmd} {args}".strip()))

            disabled = cfg.get("disabled", False)
            status_text = "⏸ 禁用" if disabled else "✅ 启用"
            self._mcp_table.setItem(i, 2, QTableWidgetItem(status_text))

            desc = cfg.get("description", "")
            if len(desc) > 40:
                desc = desc[:40] + "..."
            self._mcp_table.setItem(i, 3, QTableWidgetItem(desc))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)
            btn_widget.setMinimumWidth(220)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(56, 26)
            edit_btn.clicked.connect(lambda checked, n=name: self._edit_mcp_server(n))
            btn_layout.addWidget(edit_btn)

            toggle_btn = QPushButton("禁用" if not disabled else "启用")
            toggle_btn.setFixedSize(56, 26)
            toggle_btn.clicked.connect(lambda checked, n=name: self._toggle_mcp_server(n))
            btn_layout.addWidget(toggle_btn)

            del_btn = QPushButton("删除")
            del_btn.setObjectName("DangerBtn")
            del_btn.setFixedSize(56, 26)
            del_btn.clicked.connect(lambda checked, n=name: self._remove_mcp_server(n))
            btn_layout.addWidget(del_btn)

            btn_layout.addStretch()
            self._mcp_table.setRowHeight(i, 45)

            self._mcp_table.setCellWidget(i, 4, btn_widget)

    def _load_skills(self):
        skills = CLIBridge.get_skills()
        self._skills_table.setRowCount(len(skills))
        for i, s in enumerate(skills):
            self._skills_table.setItem(i, 0, QTableWidgetItem(s["name"]))
            self._skills_table.setItem(i, 1, QTableWidgetItem(s["path"]))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(6, 2, 6, 2)
            btn_layout.setSpacing(0)
            btn_layout.addStretch()

            del_btn = QPushButton("🗑️ 删除")
            del_btn.setObjectName("DangerBtn")
            del_btn.setFixedSize(78, 26)
            del_btn.clicked.connect(lambda checked, name=s["name"]: self._remove_skill(name))
            btn_layout.addWidget(del_btn)
            btn_layout.addStretch()

            self._skills_table.setRowHeight(i, 45)
            self._skills_table.setCellWidget(i, 2, btn_widget)

    def _load_agents(self):
        agents = CLIBridge.get_agents()
        self._agents_table.setRowCount(len(agents))
        for i, a in enumerate(agents):
            self._agents_table.setItem(i, 0, QTableWidgetItem(a["name"]))
            self._agents_table.setItem(i, 1, QTableWidgetItem(a["path"]))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)
            btn_widget.setMinimumWidth(200)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(70, 26)
            edit_btn.clicked.connect(lambda checked, name=a["name"]: self._edit_agent(name))
            btn_layout.addWidget(edit_btn)

            del_btn = QPushButton("删除")
            del_btn.setObjectName("DangerBtn")
            del_btn.setFixedSize(70, 26)
            del_btn.clicked.connect(lambda checked, name=a["name"]: self._remove_agent(name))
            btn_layout.addWidget(del_btn)

            btn_layout.addStretch()
            self._agents_table.setRowHeight(i, 45)

            self._agents_table.setCellWidget(i, 2, btn_widget)

    def _load_commands(self):
        commands = CLIBridge.get_commands()
        self._commands_table.setRowCount(len(commands))
        for i, c in enumerate(commands):
            self._commands_table.setItem(i, 0, QTableWidgetItem(c["name"]))
            self._commands_table.setItem(i, 1, QTableWidgetItem(c["path"]))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(6, 2, 6, 2)
            btn_layout.setSpacing(0)
            btn_layout.addStretch()

            del_btn = QPushButton("🗑️ 删除")
            del_btn.setObjectName("DangerBtn")
            del_btn.setFixedSize(78, 26)
            del_btn.clicked.connect(lambda checked, name=c["name"]: self._remove_command(name))
            btn_layout.addWidget(del_btn)
            btn_layout.addStretch()

            self._commands_table.setRowHeight(i, 45)
            self._commands_table.setCellWidget(i, 2, btn_widget)

    # ------------------------------------------------------------------
    # API 模型源切换
    # ------------------------------------------------------------------
    def _on_api_models_toggled(self, state):
        """用户切换 API 模型源开关。"""
        enabled = bool(state)
        IFlowSettings.set_use_api_models(enabled)
        CLIBridge.invalidate_models_cache()
        self._update_api_model_hint(enabled)

        # 重新加载模型列表
        current_model = self._get_selected_model()
        self._populate_model_combo(current_model)

    def _update_api_model_hint(self, use_api: bool):
        """更新 API 模型源的提示文字。"""
        if use_api:
            settings = IFlowSettings.load()
            api_key = settings.get("apiKey", "")
            base_url = settings.get("baseUrl", "https://apis.iflow.cn/v1")
            if api_key:
                masked = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                self._api_model_hint.setText(
                    f"📡 在线模式：从 {base_url}/models 获取模型列表 (Key: {masked})"
                )
            else:
                self._api_model_hint.setText(
                    "⚠️ 未配置 API Key，请先在「登录认证」页面设置 API Key"
                )
        else:
            self._api_model_hint.setText(
                "📦 离线模式：使用 iflow CLI 内置的模型列表"
            )

    # ------------------------------------------------------------------
    # 保存操作
    # ------------------------------------------------------------------
    def _save_general(self):
        settings = IFlowSettings.load()
        settings["modelName"] = self._get_selected_model()
        settings["thinking"] = self._thinking_cb.isChecked()
        settings["checkpointing"] = {"enabled": self._checkpointing_cb.isChecked()}
        settings["language"] = self._language_combo.currentText()
        settings["preferredEditor"] = self._editor_combo.currentText()
        settings["useApiModels"] = self._use_api_models_cb.isChecked()

        instructions = self._instructions_edit.toPlainText().strip()
        if instructions:
            settings["customInstructions"] = instructions
        else:
            settings.pop("customInstructions", None)

        IFlowSettings.save(settings)
        CLIBridge.invalidate_models_cache()
        QMessageBox.information(self, "保存成功", "iFlow 设置已保存。")

    # ------------------------------------------------------------------
    # MCP 操作
    # ------------------------------------------------------------------
    def _add_mcp_server(self):
        dialog = MCPServerDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            name, config = dialog.get_data()
            if not name:
                QMessageBox.warning(self, "缺少信息", "请填写服务器名称。")
                return
            if not config.get("command"):
                QMessageBox.warning(self, "缺少信息", "请填写命令。")
                return
            IFlowSettings.add_mcp_server(name, config)
            self._load_mcp()

    def _edit_mcp_server(self, name: str):
        servers = IFlowSettings.get_mcp_servers()
        config = servers.get(name, {})
        dialog = MCPServerDialog(name=name, config=config, parent=self)
        if dialog.exec() == QDialog.Accepted:
            _, new_config = dialog.get_data()
            IFlowSettings.add_mcp_server(name, new_config)
            self._load_mcp()

    def _toggle_mcp_server(self, name: str):
        servers = IFlowSettings.get_mcp_servers()
        if name in servers:
            servers[name]["disabled"] = not servers[name].get("disabled", False)
            IFlowSettings.set_mcp_servers(servers)
            self._load_mcp()

    def _remove_mcp_server(self, name: str):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 MCP 服务器 '{name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            IFlowSettings.remove_mcp_server(name)
            self._load_mcp()

    # ------------------------------------------------------------------
    # Skills 操作
    # ------------------------------------------------------------------
    def _install_skill(self):
        """通过 CLI 安装 skill。"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "安装技能",
            "请输入技能名称或 ID (来自 iflow 在线仓库):",
        )
        if ok and name.strip():
            self._run_iflow_command(["skill", "add", name.strip()], "安装技能")
            self._load_skills()

    def _remove_skill(self, name: str):
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除技能 '{name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # 删除 skills 目录
            import shutil
            skill_path = IFlowSettings.get_dir() / "skills" / name
            if skill_path.exists():
                shutil.rmtree(skill_path, ignore_errors=True)
            self._load_skills()

    # ------------------------------------------------------------------
    # Agents 操作
    # ------------------------------------------------------------------
    def _create_agent(self):
        dialog = AgentEditDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            name, content = dialog.get_data()
            if not name:
                QMessageBox.warning(self, "缺少信息", "请填写代理名称。")
                return
            agents_dir = IFlowSettings.get_dir() / "agents"
            agents_dir.mkdir(parents=True, exist_ok=True)
            agent_file = agents_dir / f"{name}.md"
            agent_file.write_text(content, encoding="utf-8")
            self._load_agents()

    def _edit_agent(self, name: str):
        agent_file = IFlowSettings.get_dir() / "agents" / f"{name}.md"
        content = ""
        if agent_file.exists():
            content = agent_file.read_text(encoding="utf-8")
        dialog = AgentEditDialog(name=name, content=content, parent=self)
        if dialog.exec() == QDialog.Accepted:
            _, new_content = dialog.get_data()
            agent_file.write_text(new_content, encoding="utf-8")
            self._load_agents()

    def _remove_agent(self, name: str):
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除代理 '{name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            agent_file = IFlowSettings.get_dir() / "agents" / f"{name}.md"
            if agent_file.exists():
                agent_file.unlink()
            self._load_agents()

    # ------------------------------------------------------------------
    # Commands 操作
    # ------------------------------------------------------------------
    def _install_command(self):
        """通过 CLI 安装 command。"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "安装命令",
            "请输入命令名称或 ID (来自 iflow 在线市场):",
        )
        if ok and name.strip():
            self._run_iflow_command(["commands", "add", name.strip()], "安装命令")
            self._load_commands()

    def _remove_command(self, name: str):
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除命令 '{name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_iflow_command(["commands", "remove", name], "删除命令")
            self._load_commands()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _run_iflow_command(self, args: list[str], action_name: str):
        """执行 iflow CLI 命令。"""
        try:
            iflow_cmd = CLIBridge._get_iflow_cmd()
            cmd = [iflow_cmd] + args
            kw = subprocess_kwargs(capture=True)
            result = subprocess.run(cmd, timeout=30, **kw)
            stdout = _decode(result.stdout).strip() if result.stdout else ""
            stderr = _decode(result.stderr).strip() if result.stderr else ""

            if result.returncode == 0:
                msg = stdout or f"{action_name}成功"
                QMessageBox.information(self, "成功", msg)
            else:
                msg = stderr or stdout or f"{action_name}失败"
                QMessageBox.warning(self, "失败", msg)
        except FileNotFoundError:
            QMessageBox.critical(self, "错误", "未找到 iflow 命令，请确保已安装 iflow CLI")
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    # ------------------------------------------------------------------
    # 在线仓库浏览
    # ------------------------------------------------------------------
    def _open_online_browser(self, repo_type: str):
        """打开在线仓库浏览对话框。"""
        dialog = OnlineRepoBrowser(repo_type, parent=self)
        dialog.install_requested.connect(self._on_online_install)
        dialog.exec()

    def _on_online_install(self, repo_type: str, name_or_id: str, config: dict):
        """处理在线仓库安装请求。"""
        if repo_type == "mcp":
            # 直接将 MCP 服务器配置写入 settings.json
            reply = QMessageBox.question(
                self, "确认安装",
                f"确定要添加 MCP 服务器 '{name_or_id}' 吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                IFlowSettings.add_mcp_server(name_or_id, config)
                self._load_mcp()
                QMessageBox.information(self, "添加成功", f"MCP 服务器 '{name_or_id}' 已添加到配置。")
        elif repo_type == "agents":
            self._run_iflow_command(["agent", "add", name_or_id], "安装代理")
            self._load_agents()
        elif repo_type == "skills":
            self._run_iflow_command(["skill", "add", name_or_id, "--scope", "global"], "安装技能")
            self._load_skills()
        elif repo_type == "commands":
            self._run_iflow_command(["commands", "add", name_or_id], "安装命令")
            self._load_commands()
