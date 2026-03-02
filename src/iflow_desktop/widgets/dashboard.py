"""仪表盘页面。"""

from __future__ import annotations
import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QScrollArea,
)
from PySide6.QtCore import Qt

from iflow_desktop.core.cli_bridge import CLIBridge, IFlowSettings


class StatusCard(QFrame):
    """状态信息卡片。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(8)

        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._layout.addWidget(self._title)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)
        self._layout.addLayout(self._rows_layout)

        self._labels: dict[str, QLabel] = {}

    def set_row(self, key: str, label: str, value: str, status: str = ""):
        if key not in self._labels:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("CardLabel")
            lbl.setFixedWidth(120)
            val = QLabel(value)
            val.setObjectName("CardValue")
            if status:
                val.setObjectName(f"Status{status.capitalize()}")
            row.addWidget(lbl)
            row.addWidget(val, 1)
            self._rows_layout.addLayout(row)
            self._labels[key] = val
        else:
            self._labels[key].setText(value)
            if status:
                self._labels[key].setObjectName(f"Status{status.capitalize()}")
                self._labels[key].style().unpolish(self._labels[key])
                self._labels[key].style().polish(self._labels[key])


class DashboardPage(QWidget):
    """仪表盘。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        # 不再使用自己的 QTimer，由 StatusMonitor 推送数据

    def on_status_update(self, data: dict):
        """接收 StatusMonitor 推送的状态数据，更新 UI（零阻塞）。"""
        installed = data.get("iflow_installed", False)
        self._iflow_card.set_row(
            "installed", "安装状态",
            "✅ 已安装" if installed else "❌ 未安装",
            "green" if installed else "red",
        )
        if installed:
            ver = data.get("iflow_version", "—")
            self._iflow_card.set_row("version", "版本", ver)
            logged = data.get("iflow_logged_in", False)
            self._iflow_card.set_row(
                "login", "登录状态",
                "✅ 已认证" if logged else "⚠️ 未认证",
                "green" if logged else "yellow",
            )
            auth_info = data.get("auth_info", {})
            auth_type = auth_info.get("auth_type", "")
            if auth_type:
                self._iflow_card.set_row("auth_type", "认证方式", auth_type)
        else:
            self._iflow_card.set_row("version", "版本", "—")
            self._iflow_card.set_row("login", "登录状态", "—", "dim")

        gw_running = data.get("gateway_running", False)
        gw_pid = data.get("gateway_pid")
        if gw_running:
            self._gw_card.set_row("status", "运行状态",
                                  f"✅ 运行中 (PID: {gw_pid})", "green")
        else:
            self._gw_card.set_row("status", "运行状态", "⏹ 未运行", "dim")

        channels = data.get("enabled_channels", [])
        self._gw_card.set_row("channels", "活跃渠道",
                              ", ".join(channels) if channels else "无")

        self._model_card.set_row("model", "当前模型",
                                 data.get("current_model", "—"))
        thinking = data.get("thinking", False)
        self._model_card.set_row("thinking", "思考模式",
                                 "🧠 开启" if thinking else "关闭",
                                 "green" if thinking else "dim")
        config = data.get("config", {})
        mode = config.get("driver", {}).get("mode", "stdio")
        self._model_card.set_row("mode", "通信模式", mode.upper())
        self._sys_card.set_row("workspace", "工作空间",
                               data.get("workspace", "—"))

        # MCP / Skills / Agents / Commands 计数
        mcp_count = len(data.get("mcp_servers", []))
        skills_count = len(data.get("skills", []))
        agents_count = len(data.get("agents", []))
        commands_count = len(data.get("commands", []))
        self._ext_card.set_row("mcp", "MCP 服务器", f"{mcp_count} 个")
        self._ext_card.set_row("skills", "技能", f"{skills_count} 个")
        self._ext_card.set_row("agents", "代理", f"{agents_count} 个")
        self._ext_card.set_row("commands", "命令", f"{commands_count} 个")

        self._last_refresh.setText(
            f"上次刷新: {datetime.now().strftime('%H:%M:%S')}"
        )

    def _init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(32, 24, 32, 24)
        main_layout.setSpacing(20)

        title = QLabel("仪表盘")
        title.setObjectName("PageTitle")
        main_layout.addWidget(title)

        subtitle = QLabel("iFlow CLI 运行状态总览")
        subtitle.setObjectName("PageSubtitle")
        main_layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(16)

        self._iflow_card = StatusCard("iFlow CLI 状态")
        self._iflow_card.set_row("installed", "安装状态", "检测中...", "dim")
        self._iflow_card.set_row("version", "版本", "—")
        self._iflow_card.set_row("login", "登录状态", "—", "dim")
        grid.addWidget(self._iflow_card, 0, 0)

        self._gw_card = StatusCard("iFlow Bot 网关")
        self._gw_card.set_row("status", "运行状态", "检测中...", "dim")
        self._gw_card.set_row("channels", "活跃渠道", "—")
        grid.addWidget(self._gw_card, 0, 1)

        self._model_card = StatusCard("模型配置 (iFlow CLI)")
        self._model_card.set_row("model", "当前模型", "—")
        self._model_card.set_row("thinking", "思考模式", "—")
        self._model_card.set_row("mode", "通信模式", "—")
        grid.addWidget(self._model_card, 1, 0)

        self._sys_card = StatusCard("系统信息")
        self._sys_card.set_row("python", "Python", sys.version.split()[0])
        self._sys_card.set_row("platform", "平台", sys.platform)
        self._sys_card.set_row("config_path", "配置文件", str(IFlowSettings.get_path()))
        self._sys_card.set_row("workspace", "工作空间", "—")
        grid.addWidget(self._sys_card, 1, 1)

        self._ext_card = StatusCard("iFlow 扩展")
        self._ext_card.set_row("mcp", "MCP 服务器", "检测中...")
        self._ext_card.set_row("skills", "技能", "检测中...")
        self._ext_card.set_row("agents", "代理", "检测中...")
        self._ext_card.set_row("commands", "命令", "检测中...")
        grid.addWidget(self._ext_card, 2, 0)

        main_layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._last_refresh = QLabel("等待后台状态更新...")
        self._last_refresh.setObjectName("CardLabel")
        btn_row.addWidget(self._last_refresh)

        main_layout.addLayout(btn_row)
        main_layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
