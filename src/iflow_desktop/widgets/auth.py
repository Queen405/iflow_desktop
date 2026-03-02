"""登录认证页面 - iflow auth 管理。"""

from __future__ import annotations

import subprocess
import platform
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QMessageBox, QLineEdit, QGridLayout,
    QGroupBox,
)
from PySide6.QtCore import Qt, QThread, Signal

from iflow_desktop.core.cli_bridge import CLIBridge, IFlowSettings


class AuthLoginWorker(QThread):
    """后台线程执行 iflow auth login。"""
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            iflow_cmd = CLIBridge._get_iflow_cmd()
            # iflow 没有 auth login 子命令，使用 API key 方式认证
            # 先检查是否已有 API key
            settings = IFlowSettings.load()
            if settings.get("apiKey"):
                self.finished.emit(True, "已通过 API Key 认证")
            else:
                self.finished.emit(False, "请在下方配置 API Key 进行认证")
        except Exception as e:
            self.finished.emit(False, str(e))


class AuthPage(QWidget):
    """iFlow 认证管理页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._refresh_status()

    def on_status_update(self, data: dict):
        """接收 StatusMonitor 推送的状态数据。"""
        installed = data.get("iflow_installed", False)
        version = data.get("iflow_version", "未安装")
        logged_in = data.get("iflow_logged_in", False)

        if installed:
            self._install_label.setText(f"✅ iFlow CLI 已安装 ({version})")
            self._install_label.setObjectName("StatusGreen")
        else:
            self._install_label.setText("❌ iFlow CLI 未安装")
            self._install_label.setObjectName("StatusRed")
        self._install_label.style().unpolish(self._install_label)
        self._install_label.style().polish(self._install_label)

        if logged_in:
            self._login_status.setText("✅ 已认证")
            self._login_status.setObjectName("StatusGreen")
        else:
            self._login_status.setText("⚠️ 未认证")
            self._login_status.setObjectName("StatusYellow")
        self._login_status.style().unpolish(self._login_status)
        self._login_status.style().polish(self._login_status)

    def _init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        main = QVBoxLayout(container)
        main.setContentsMargins(32, 24, 32, 24)
        main.setSpacing(20)

        title = QLabel("登录认证")
        title.setObjectName("PageTitle")
        main.addWidget(title)

        subtitle = QLabel("管理 iFlow CLI 认证状态和 API 密钥")
        subtitle.setObjectName("PageSubtitle")
        main.addWidget(subtitle)

        # 状态卡片
        status_card = QFrame()
        status_card.setObjectName("Card")
        sc_layout = QVBoxLayout(status_card)

        sc_title = QLabel("认证状态")
        sc_title.setObjectName("CardTitle")
        sc_layout.addWidget(sc_title)

        self._install_label = QLabel("检测中...")
        self._install_label.setStyleSheet("font-size: 14px; padding: 4px 0;")
        sc_layout.addWidget(self._install_label)

        self._login_status = QLabel("检测中...")
        self._login_status.setStyleSheet("font-size: 14px; padding: 4px 0;")
        sc_layout.addWidget(self._login_status)

        self._account_info = QLabel("")
        self._account_info.setObjectName("CardValue")
        self._account_info.setWordWrap(True)
        sc_layout.addWidget(self._account_info)

        main.addWidget(status_card)

        # API Key 配置
        api_card = QFrame()
        api_card.setObjectName("Card")
        api_layout = QVBoxLayout(api_card)

        api_title = QLabel("API 配置")
        api_title.setObjectName("CardTitle")
        api_layout.addWidget(api_title)

        api_desc = QLabel("iFlow 使用 API Key 进行认证，请在 iflow.cn 获取您的 API Key")
        api_desc.setObjectName("CardLabel")
        api_desc.setWordWrap(True)
        api_layout.addWidget(api_desc)

        grid = QGridLayout()
        grid.setSpacing(12)

        grid.addWidget(QLabel("认证方式:"), 0, 0)
        self._auth_type_label = QLabel("—")
        self._auth_type_label.setObjectName("CardValue")
        grid.addWidget(self._auth_type_label, 0, 1)

        grid.addWidget(QLabel("Base URL:"), 1, 0)
        self._base_url_edit = QLineEdit()
        self._base_url_edit.setPlaceholderText("https://apis.iflow.cn/v1")
        grid.addWidget(self._base_url_edit, 1, 1)

        grid.addWidget(QLabel("API Key:"), 2, 0)
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        grid.addWidget(self._api_key_edit, 2, 1)

        api_layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        save_btn = QPushButton("💾  保存认证配置")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_auth)
        btn_row.addWidget(save_btn)

        show_key_btn = QPushButton("👁  显示密钥")
        show_key_btn.setFixedHeight(40)
        show_key_btn.clicked.connect(self._toggle_key_visibility)
        btn_row.addWidget(show_key_btn)

        btn_row.addStretch()

        clear_btn = QPushButton("🗑️  清除认证")
        clear_btn.setObjectName("DangerBtn")
        clear_btn.setFixedHeight(40)
        clear_btn.clicked.connect(self._clear_auth)
        btn_row.addWidget(clear_btn)

        api_layout.addLayout(btn_row)
        main.addWidget(api_card)

        # 安装指南
        guide_card = QFrame()
        guide_card.setObjectName("Card")
        guide_layout = QVBoxLayout(guide_card)

        guide_title = QLabel("安装指南")
        guide_title.setObjectName("CardTitle")
        guide_layout.addWidget(guide_title)

        guide_text = QLabel(
            "1. 安装 Node.js (v18+)\n"
            "2. 运行: npm install -g @iflow-ai/iflow-cli@latest\n"
            "3. 验证: iflow --version\n"
            "4. 在上方配置 API Key 即可开始使用\n\n"
            "获取 API Key: https://iflow.cn"
        )
        guide_text.setObjectName("CardValue")
        guide_text.setWordWrap(True)
        guide_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        guide_layout.addWidget(guide_text)

        main.addWidget(guide_card)
        main.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _refresh_status(self):
        """刷新认证状态。"""
        settings = IFlowSettings.load()

        auth_type = settings.get("selectedAuthType", "")
        self._auth_type_label.setText(auth_type or "未设置")

        base_url = settings.get("baseUrl", "")
        self._base_url_edit.setText(base_url)

        api_key = settings.get("apiKey", "")
        self._api_key_edit.setText(api_key)

        if api_key:
            masked = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
            self._account_info.setText(f"API Key: {masked}")
        else:
            self._account_info.setText("未配置 API Key")

        # 账户信息
        accounts_path = IFlowSettings.get_dir() / "iflow_accounts.json"
        if accounts_path.exists():
            try:
                with open(accounts_path, "r", encoding="utf-8") as f:
                    accounts = json.load(f)
                active = accounts.get("active")
                if active:
                    self._account_info.setText(f"活跃账户: {active}")
            except Exception:
                pass

    def _save_auth(self):
        """保存认证配置到 settings.json。"""
        settings = IFlowSettings.load()

        base_url = self._base_url_edit.text().strip()
        api_key = self._api_key_edit.text().strip()

        if base_url:
            settings["baseUrl"] = base_url
        if api_key:
            settings["apiKey"] = api_key
            settings["searchApiKey"] = api_key
            settings["selectedAuthType"] = "iflow"

        IFlowSettings.save(settings)
        self._refresh_status()
        QMessageBox.information(self, "保存成功", "认证配置已保存。")

    def _clear_auth(self):
        """清除认证信息。"""
        reply = QMessageBox.question(
            self, "确认清除",
            "确定要清除所有认证信息吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            settings = IFlowSettings.load()
            settings.pop("apiKey", None)
            settings.pop("searchApiKey", None)
            settings.pop("selectedAuthType", None)
            IFlowSettings.save(settings)
            self._refresh_status()

    def _toggle_key_visibility(self):
        """切换 API Key 可见性。"""
        if self._api_key_edit.echoMode() == QLineEdit.Password:
            self._api_key_edit.setEchoMode(QLineEdit.Normal)
        else:
            self._api_key_edit.setEchoMode(QLineEdit.Password)
