"""iFlow Bot 服务管理页面 - Gateway、渠道、定时任务、会话映射。"""

from __future__ import annotations

import json
import uuid
import time
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QTabWidget,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QGridLayout,
    QDialog, QDialogButtonBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal

from iflow_desktop.core.cli_bridge import CLIBridge


# =====================================================================
# 添加 Cron 任务对话框
# =====================================================================
class AddCronDialog(QDialog):
    """添加定时任务对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加定时任务")
        self.setFixedWidth(500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        grid = QGridLayout()

        grid.addWidget(QLabel("任务名称:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如: 每日总结")
        grid.addWidget(self.name_edit, 0, 1)

        grid.addWidget(QLabel("消息内容:"), 1, 0)
        self.message_edit = QLineEdit()
        self.message_edit.setPlaceholderText("发送给 AI 的消息")
        grid.addWidget(self.message_edit, 1, 1)

        grid.addWidget(QLabel("调度类型:"), 2, 0)
        self.schedule_combo = QComboBox()
        self.schedule_combo.addItems(["每隔 N 秒", "Cron 表达式"])
        grid.addWidget(self.schedule_combo, 2, 1)

        grid.addWidget(QLabel("间隔 (秒):"), 3, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 86400 * 30)
        self.interval_spin.setValue(3600)
        grid.addWidget(self.interval_spin, 3, 1)

        grid.addWidget(QLabel("Cron 表达式:"), 4, 0)
        self.cron_edit = QLineEdit()
        self.cron_edit.setPlaceholderText("0 9 * * *")
        grid.addWidget(self.cron_edit, 4, 1)

        self.deliver_cb = QCheckBox("投递响应到渠道")
        grid.addWidget(self.deliver_cb, 5, 0, 1, 2)

        grid.addWidget(QLabel("目标渠道:"), 6, 0)
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("telegram / discord / ...")
        grid.addWidget(self.channel_edit, 6, 1)

        grid.addWidget(QLabel("目标 ID:"), 7, 0)
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("用户ID 或 群组ID")
        grid.addWidget(self.to_edit, 7, 1)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        schedule_type = self.schedule_combo.currentText()
        data = {
            "name": self.name_edit.text(),
            "message": self.message_edit.text(),
            "deliver": self.deliver_cb.isChecked(),
            "channel": self.channel_edit.text(),
            "to": self.to_edit.text(),
        }
        if "秒" in schedule_type:
            data["schedule"] = {
                "kind": "every",
                "every_ms": self.interval_spin.value() * 1000,
            }
        else:
            data["schedule"] = {
                "kind": "cron",
                "expr": self.cron_edit.text(),
            }
        return data


# =====================================================================
# 渠道连通性测试线程
# =====================================================================
class ChannelTestWorker(QThread):
    """后台线程测试渠道连通性。"""
    finished = Signal(str, bool, str)  # channel_type, success, message

    def __init__(self, channel_type: str, config: dict, parent=None):
        super().__init__(parent)
        self.channel_type = channel_type
        self.config = config

    def run(self):
        try:
            success, msg = CLIBridge.test_channel_connection(
                self.channel_type, self.config
            )
            self.finished.emit(self.channel_type, success, msg)
        except Exception as e:
            self.finished.emit(self.channel_type, False, str(e))


# =====================================================================
# Bot 管理页面 (合并 Gateway + 渠道配置 + Cron + 会话映射)
# =====================================================================
class BotManagerPage(QWidget):
    """iFlow Bot 服务管理 - 包含 Gateway、渠道、定时任务、会话映射。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._test_workers: dict[str, ChannelTestWorker] = {}
        self._test_buttons: dict[str, QPushButton] = {}
        self._init_ui()
        self._refresh_all()

    def on_status_update(self, data: dict):
        """接收 StatusMonitor 推送数据。"""
        # Gateway 状态
        running = data.get("gateway_running", False)
        pid = data.get("gateway_pid")
        if running:
            self._gw_status.setText(f"✅ Gateway 运行中 (PID: {pid})")
            self._gw_status.setObjectName("StatusGreen")
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
        else:
            self._gw_status.setText("⏹ Gateway 未运行")
            self._gw_status.setObjectName("StatusDim")
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
        self._gw_status.style().unpolish(self._gw_status)
        self._gw_status.style().polish(self._gw_status)

        channels = data.get("enabled_channels", [])
        if channels:
            self._ch_label.setText(f"活跃渠道: {', '.join(channels)}")
        else:
            self._ch_label.setText("未启用任何渠道")

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

        title = QLabel("iFlow Bot 服务")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)

        header_layout.addStretch()

        desc = QLabel("管理 iFlow Bot 多渠道网关服务")
        desc.setObjectName("PageSubtitle")
        header_layout.addWidget(desc)

        main.addWidget(header_frame)

        # Tab
        tabs = QTabWidget()
        tabs.addTab(self._create_gateway_tab(), "🌐 网关")
        tabs.addTab(self._create_channels_tab(), "📡 渠道配置")
        tabs.addTab(self._create_cron_tab(), "⏰ 定时任务")
        tabs.addTab(self._create_sessions_tab(), "📋 会话映射")
        main.addWidget(tabs, 1)

    # ------------------------------------------------------------------
    # Gateway Tab
    # ------------------------------------------------------------------
    def _create_gateway_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)

        # 状态卡片
        status_card = QFrame()
        status_card.setObjectName("Card")
        sc_layout = QVBoxLayout(status_card)

        sc_title = QLabel("运行状态")
        sc_title.setObjectName("CardTitle")
        sc_layout.addWidget(sc_title)

        self._gw_status = QLabel("检测中...")
        self._gw_status.setStyleSheet("font-size: 15px; padding: 8px 0;")
        sc_layout.addWidget(self._gw_status)

        self._ch_label = QLabel("")
        self._ch_label.setObjectName("CardValue")
        sc_layout.addWidget(self._ch_label)

        layout.addWidget(status_card)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._start_btn = QPushButton("▶  启动网关")
        self._start_btn.setObjectName("SuccessBtn")
        self._start_btn.setFixedHeight(40)
        self._start_btn.clicked.connect(self._start_gateway)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("⏹  停止网关")
        self._stop_btn.setObjectName("DangerBtn")
        self._stop_btn.setFixedHeight(40)
        self._stop_btn.clicked.connect(self._stop_gateway)
        btn_row.addWidget(self._stop_btn)

        restart_btn = QPushButton("🔄  重启网关")
        restart_btn.setFixedHeight(40)
        restart_btn.clicked.connect(self._restart_gateway)
        btn_row.addWidget(restart_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 配置编辑器
        config_card = QFrame()
        config_card.setObjectName("Card")
        cc_layout = QVBoxLayout(config_card)

        cc_title = QLabel("iflow-bot 配置")
        cc_title.setObjectName("CardTitle")
        cc_layout.addWidget(cc_title)

        cc_path = QLabel(f"配置文件: {CLIBridge.get_bot_config_path()}")
        cc_path.setObjectName("CardLabel")
        cc_layout.addWidget(cc_path)

        cfg_grid = QGridLayout()

        cfg_grid.addWidget(QLabel("通信模式:"), 0, 0)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["stdio", "cli", "acp"])
        cfg_grid.addWidget(self._mode_combo, 0, 1)

        cfg_grid.addWidget(QLabel("iflow 路径:"), 1, 0)
        self._iflow_path_edit = QLineEdit()
        self._iflow_path_edit.setPlaceholderText("iflow")
        cfg_grid.addWidget(self._iflow_path_edit, 1, 1)

        cfg_grid.addWidget(QLabel("工作空间:"), 2, 0)
        ws_row = QHBoxLayout()
        self._workspace_edit = QLineEdit()
        ws_row.addWidget(self._workspace_edit)
        ws_browse = QPushButton("...")
        ws_browse.setFixedWidth(40)
        ws_browse.clicked.connect(self._browse_workspace)
        ws_row.addWidget(ws_browse)
        cfg_grid.addLayout(ws_row, 2, 1)

        self._yolo_cb = QCheckBox("YOLO 模式 (自动确认)")
        cfg_grid.addWidget(self._yolo_cb, 3, 0, 1, 2)

        cc_layout.addLayout(cfg_grid)

        save_cfg_btn = QPushButton("💾  保存 Bot 配置")
        save_cfg_btn.setObjectName("PrimaryBtn")
        save_cfg_btn.setFixedHeight(36)
        save_cfg_btn.clicked.connect(self._save_bot_config)
        cc_layout.addWidget(save_cfg_btn)

        layout.addWidget(config_card)

        # 命令参考
        cmd_card = QFrame()
        cmd_card.setObjectName("Card")
        cmd_layout = QVBoxLayout(cmd_card)
        cmd_title = QLabel("命令参考")
        cmd_title.setObjectName("CardTitle")
        cmd_layout.addWidget(cmd_title)
        cmd_text = QLabel(
            "iflow-bot gateway start      # 后台启动\n"
            "iflow-bot gateway run         # 前台运行 (debug)\n"
            "iflow-bot gateway stop        # 停止\n"
            "iflow-bot status              # 查看状态"
        )
        cmd_text.setObjectName("LogViewer")
        cmd_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cmd_layout.addWidget(cmd_text)

        layout.addWidget(cmd_card)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # Channels Tab
    # ------------------------------------------------------------------
    def _create_channels_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 16, 24, 16)

        self._channel_widgets = {}
        # 渠道图标与颜色映射
        channel_defs = [
            ("telegram", "Telegram", "✈️", "#229ED9", [("token", "Bot Token")]),
            ("discord", "Discord", "🎮", "#5865F2", [("token", "Bot Token")]),
            ("slack", "Slack", "💼", "#4A154B", [("bot_token", "Bot Token"), ("app_token", "App Token")]),
            ("feishu", "飞书", "🐦", "#3370FF", [("app_id", "App ID"), ("app_secret", "App Secret"),
                                ("encrypt_key", "Encrypt Key"), ("verification_token", "Verification Token")]),
            ("dingtalk", "钉钉", "💬", "#0089FF", [("client_id", "Client ID"), ("client_secret", "Client Secret")]),
            ("qq", "QQ", "🐧", "#12B7F5", [("app_id", "App ID"), ("secret", "Secret")]),
            ("whatsapp", "WhatsApp", "📱", "#25D366", [("bridge_url", "Bridge URL"), ("bridge_token", "Bridge Token")]),
            ("email", "邮件", "📧", "#EA4335", [("imap_host", "IMAP Host"), ("imap_username", "IMAP 用户名"),
                                ("imap_password", "IMAP 密码"), ("smtp_host", "SMTP Host"),
                                ("smtp_username", "SMTP 用户名"), ("smtp_password", "SMTP 密码"),
                                ("from_address", "发件地址")]),
            ("mochat", "MoChat", "💭", "#7C3AED", [("base_url", "Base URL"), ("claw_token", "Claw Token"),
                                   ("agent_user_id", "Agent User ID")]),
        ]

        # 使用两列 grid 布局渠道卡片
        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)

        for idx, (ch_key, ch_name, icon, accent, fields) in enumerate(channel_defs):
            card = QFrame()
            card.setObjectName("ChannelCard")
            card.setProperty("accent", accent)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(10)

            # 卡片头部：图标 + 名称 + 开关 + 测试按钮
            header = QHBoxLayout()
            header.setSpacing(10)

            icon_label = QLabel(icon)
            icon_label.setObjectName("ChannelIcon")
            icon_label.setFixedSize(32, 32)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet(
                f"background-color: {accent}22; border-radius: 8px; font-size: 18px;"
            )
            header.addWidget(icon_label)

            name_label = QLabel(ch_name)
            name_label.setObjectName("ChannelName")
            header.addWidget(name_label)

            header.addStretch()

            cb = QCheckBox("启用")
            cb.setObjectName("ChannelToggle")
            header.addWidget(cb)

            test_btn = QPushButton("🔗 测试")
            test_btn.setObjectName("TestConnBtn")
            test_btn.setFixedSize(80, 28)
            test_btn.setCursor(Qt.PointingHandCursor)
            test_btn.clicked.connect(lambda checked, k=ch_key: self._test_channel(k))
            header.addWidget(test_btn)
            self._test_buttons[ch_key] = test_btn

            card_layout.addLayout(header)

            # 分割线
            sep = QFrame()
            sep.setObjectName("ChannelSep")
            sep.setFixedHeight(1)
            card_layout.addWidget(sep)

            # 配置字段区域
            field_widgets = {"enabled": cb}
            fields_grid = QGridLayout()
            fields_grid.setContentsMargins(0, 0, 0, 0)
            fields_grid.setSpacing(6)
            fields_grid.setColumnStretch(1, 1)

            for i, (fk, fl) in enumerate(fields):
                label = QLabel(fl)
                label.setObjectName("ChannelFieldLabel")
                fields_grid.addWidget(label, i, 0)
                edit = QLineEdit()
                edit.setObjectName("ChannelFieldEdit")
                edit.setPlaceholderText(fl)
                if "password" in fk or "secret" in fk or "token" in fk:
                    edit.setEchoMode(QLineEdit.Password)
                fields_grid.addWidget(edit, i, 1)
                field_widgets[fk] = edit

            card_layout.addLayout(fields_grid)

            self._channel_widgets[ch_key] = field_widgets

            row = idx // 2
            col = idx % 2
            cards_grid.addWidget(card, row, col)

        layout.addLayout(cards_grid)

        save_ch_btn = QPushButton("💾  保存渠道配置")
        save_ch_btn.setObjectName("PrimaryBtn")
        save_ch_btn.setFixedHeight(40)
        save_ch_btn.clicked.connect(self._save_channels)
        layout.addWidget(save_ch_btn)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # ------------------------------------------------------------------
    # Cron Tab
    # ------------------------------------------------------------------
    def _create_cron_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕  添加任务")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.clicked.connect(self._add_cron_job)
        btn_row.addWidget(add_btn)

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.clicked.connect(self._refresh_cron)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._cron_table = QTableWidget()
        self._cron_table.setColumnCount(6)
        self._cron_table.setHorizontalHeaderLabels(["ID", "名称", "调度", "投递", "状态", "下次运行"])
        self._cron_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._cron_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for i in range(2, 6):
            self._cron_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._cron_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cron_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._cron_table, 1)

        hint = QLabel("提示：定时任务需要 Gateway 运行才能执行")
        hint.setObjectName("CardLabel")
        layout.addWidget(hint)

        return page

    # ------------------------------------------------------------------
    # Sessions Tab
    # ------------------------------------------------------------------
    def _create_sessions_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.setObjectName("PrimaryBtn")
        refresh_btn.clicked.connect(self._refresh_sessions)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        desc = QLabel("渠道用户到 iflow 会话的映射关系")
        desc.setObjectName("CardLabel")
        layout.addWidget(desc)

        self._mapping_table = QTableWidget()
        self._mapping_table.setColumnCount(3)
        self._mapping_table.setHorizontalHeaderLabels(["渠道:用户", "Session ID", "操作"])
        self._mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._mapping_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._mapping_table.horizontalHeader().resizeSection(2, 100)
        self._mapping_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._mapping_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._mapping_table, 1)

        return page

    # ------------------------------------------------------------------
    # 数据刷新
    # ------------------------------------------------------------------
    def _refresh_all(self):
        self._load_bot_config()
        self._refresh_cron()
        self._refresh_sessions()

    def _load_bot_config(self):
        cfg = CLIBridge.load_bot_config()
        driver = cfg.get("driver", {})
        self._mode_combo.setCurrentText(driver.get("mode", "stdio"))
        self._iflow_path_edit.setText(driver.get("iflow_path", "iflow"))
        self._workspace_edit.setText(driver.get("workspace", ""))
        self._yolo_cb.setChecked(driver.get("yolo", True))

        # 渠道
        channels = cfg.get("channels", {})
        for ch_key, widgets in self._channel_widgets.items():
            ch_data = channels.get(ch_key, {})
            for fk, widget in widgets.items():
                if isinstance(widget, QCheckBox):
                    widget.setChecked(ch_data.get(fk, False))
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(ch_data.get(fk, "")))

    def _refresh_cron(self):
        jobs = CLIBridge.get_cron_jobs()
        self._cron_table.setRowCount(len(jobs))
        for i, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            jid = str(job.get("id", ""))
            self._cron_table.setItem(i, 0, QTableWidgetItem(jid[:12]))
            self._cron_table.setItem(i, 1, QTableWidgetItem(job.get("name", "")))

            schedule = job.get("schedule", {})
            kind = schedule.get("kind", "")
            if kind == "every":
                ms = schedule.get("every_ms", 0)
                secs = ms // 1000
                if secs >= 86400:
                    sched_str = f"每 {secs // 86400} 天"
                elif secs >= 3600:
                    sched_str = f"每 {secs // 3600} 小时"
                elif secs >= 60:
                    sched_str = f"每 {secs // 60} 分钟"
                else:
                    sched_str = f"每 {secs} 秒"
            elif kind == "cron":
                sched_str = f"cron: {schedule.get('expr', '')}"
            else:
                sched_str = kind
            self._cron_table.setItem(i, 2, QTableWidgetItem(sched_str))

            payload = job.get("payload", {})
            deliver = f"{payload['channel']}" if payload.get("deliver") and payload.get("channel") else "—"
            self._cron_table.setItem(i, 3, QTableWidgetItem(deliver))

            enabled = job.get("enabled", True)
            self._cron_table.setItem(i, 4, QTableWidgetItem("✅ 启用" if enabled else "⏸ 禁用"))

            state = job.get("state", {})
            next_ms = state.get("next_run_at_ms")
            next_str = datetime.fromtimestamp(next_ms / 1000).strftime("%m-%d %H:%M") if next_ms else "—"
            self._cron_table.setItem(i, 5, QTableWidgetItem(next_str))

    def _refresh_sessions(self):
        mappings = CLIBridge.get_session_mappings()
        self._mapping_table.setRowCount(len(mappings))
        for i, (key, sid) in enumerate(mappings.items()):
            self._mapping_table.setItem(i, 0, QTableWidgetItem(key))
            display_sid = sid[:40] + "..." if len(sid) > 40 else sid
            self._mapping_table.setItem(i, 1, QTableWidgetItem(display_sid))

            del_btn = QPushButton("🗑️ 删除")
            del_btn.setObjectName("DangerBtn")
            del_btn.setFixedHeight(28)
            del_btn.clicked.connect(lambda checked, k=key: self._delete_mapping(k))
            self._mapping_table.setCellWidget(i, 2, del_btn)

    # ------------------------------------------------------------------
    # 渠道连通性测试
    # ------------------------------------------------------------------
    def _gather_channel_config(self, ch_key: str) -> dict:
        """从 UI 控件中收集当前渠道配置值。"""
        widgets = self._channel_widgets.get(ch_key, {})
        config: dict = {}
        for fk, widget in widgets.items():
            if isinstance(widget, QCheckBox):
                config[fk] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                config[fk] = widget.text()
        return config

    def _test_channel(self, ch_key: str):
        """启动后台线程测试渠道连通性。"""
        config = self._gather_channel_config(ch_key)
        if ch_key in self._test_workers:
            old = self._test_workers[ch_key]
            if old.isRunning():
                old.quit()
                old.wait(2000)
        if ch_key in self._test_buttons:
            self._test_buttons[ch_key].setText("⏳ 测试中...")
            self._test_buttons[ch_key].setEnabled(False)
        worker = ChannelTestWorker(ch_key, config, parent=self)
        worker.finished.connect(self._on_channel_test_result)
        self._test_workers[ch_key] = worker
        worker.start()

    def _on_channel_test_result(self, ch_type: str, success: bool, message: str):
        """渠道连通性测试结果回调。"""
        if ch_type in self._test_buttons:
            self._test_buttons[ch_type].setText("🔗 测试连接")
            self._test_buttons[ch_type].setEnabled(True)
        if success:
            QMessageBox.information(self, "连接成功", f"✅ {ch_type}\n{message}")
        else:
            QMessageBox.warning(self, "连接失败", f"❌ {ch_type}\n{message}")

    # ------------------------------------------------------------------
    # 操作方法
    # ------------------------------------------------------------------
    def _start_gateway(self):
        ok, msg = CLIBridge.start_gateway()
        QMessageBox.information(self, "启动成功" if ok else "启动失败", msg)

    def _stop_gateway(self):
        ok, msg = CLIBridge.stop_gateway()
        QMessageBox.information(self, "操作结果", msg)

    def _restart_gateway(self):
        ok, msg = CLIBridge.restart_gateway()
        QMessageBox.information(self, "操作结果", msg)

    def _save_bot_config(self):
        cfg = CLIBridge.load_bot_config()
        driver = cfg.setdefault("driver", {})
        driver["mode"] = self._mode_combo.currentText()
        driver["iflow_path"] = self._iflow_path_edit.text() or "iflow"
        driver["workspace"] = self._workspace_edit.text()
        driver["yolo"] = self._yolo_cb.isChecked()
        CLIBridge.save_bot_config(cfg)
        QMessageBox.information(self, "保存成功", "Bot 配置已保存。如已启动网关，请重启使配置生效。")

    def _save_channels(self):
        cfg = CLIBridge.load_bot_config()
        channels = cfg.setdefault("channels", {})
        for ch_key, widgets in self._channel_widgets.items():
            ch = channels.setdefault(ch_key, {})
            for fk, widget in widgets.items():
                if isinstance(widget, QCheckBox):
                    ch[fk] = widget.isChecked()
                elif isinstance(widget, QLineEdit):
                    ch[fk] = widget.text()
        CLIBridge.save_bot_config(cfg)
        QMessageBox.information(self, "保存成功", "渠道配置已保存。请重启网关使配置生效。")

    def _browse_workspace(self):
        d = QFileDialog.getExistingDirectory(self, "选择工作空间")
        if d:
            self._workspace_edit.setText(d)

    def _add_cron_job(self):
        dialog = AddCronDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["name"] or not data["message"]:
                QMessageBox.warning(self, "缺少信息", "请填写任务名称和消息内容。")
                return

            jobs_path = CLIBridge.get_bot_data_dir() / "cron" / "jobs.json"
            jobs_path.parent.mkdir(parents=True, exist_ok=True)
            existing_jobs = []
            raw_data: list | dict = []
            if jobs_path.exists():
                try:
                    with open(jobs_path, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    if isinstance(raw_data, dict):
                        existing_jobs = raw_data.get("jobs", []) or []
                    elif isinstance(raw_data, list):
                        existing_jobs = raw_data
                except Exception:
                    raw_data = []

            now_ms = int(time.time() * 1000)
            schedule = data["schedule"]
            next_run = now_ms + schedule.get("every_ms", 3600000) if schedule["kind"] == "every" else 0

            job = {
                "id": str(uuid.uuid4())[:8],
                "name": data["name"],
                "schedule": schedule,
                "payload": {
                    "message": data["message"],
                    "deliver": data["deliver"],
                    "channel": data["channel"],
                    "to": data["to"],
                },
                "enabled": True,
                "state": {
                    "last_run_at_ms": None,
                    "next_run_at_ms": next_run or None,
                    "run_count": 0,
                },
                "created_at_ms": now_ms,
            }
            existing_jobs.append(job)
            with open(jobs_path, "w", encoding="utf-8") as f:
                if isinstance(raw_data, dict):
                    raw_data["jobs"] = existing_jobs
                    json.dump(raw_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(existing_jobs, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "添加成功", f"任务 {data['name']} 已创建。")
            self._refresh_cron()

    def _delete_mapping(self, key: str):
        parts = key.split(":", 1)
        if len(parts) != 2:
            return
        channel, chat_id = parts
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除会话映射 {key} 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            CLIBridge.clear_session(channel, chat_id)
            self._refresh_sessions()
