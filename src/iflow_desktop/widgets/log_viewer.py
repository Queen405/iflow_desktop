"""日志查看器页面。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QSpinBox, QComboBox,
)

from iflow_desktop.core.cli_bridge import CLIBridge


class LogViewerPage(QWidget):
    """日志查看。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._init_ui()
        # 由 StatusMonitor 推送日志, 也保留手动刷新

    def on_status_update(self, data: dict):
        """接收 StatusMonitor 推送的日志内容。"""
        # 仅当展示“全部”时使用后台推送，其他来源由本页主动读取
        if hasattr(self, "_source_combo") and self._source_combo.currentData() != "all":
            return
        text = data.get("log_text", "")
        self._log_view.setPlainText(text)
        if self._auto_scroll:
            sb = self._log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(32, 24, 32, 24)
        main.setSpacing(12)

        header = QHBoxLayout()

        title = QLabel("日志查看")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("行数:"))
        self._lines_spin = QSpinBox()
        self._lines_spin.setRange(50, 5000)
        self._lines_spin.setValue(200)
        self._lines_spin.setSingleStep(50)
        header.addWidget(self._lines_spin)

        header.addWidget(QLabel("来源:"))
        self._source_combo = QComboBox()
        self._source_combo.addItem("全部", "all")
        self._source_combo.addItem("iflow CLI", "iflow")
        self._source_combo.addItem("iflow-bot", "iflow-bot")
        self._source_combo.currentIndexChanged.connect(lambda _: self._refresh())
        header.addWidget(self._source_combo)

        refresh_btn = QPushButton("🔄  刷新")
        refresh_btn.setObjectName("PrimaryBtn")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)

        clear_btn = QPushButton("🗑️  清空日志文件")
        clear_btn.setObjectName("DangerBtn")
        clear_btn.clicked.connect(self._clear_log)
        header.addWidget(clear_btn)

        main.addLayout(header)

        log_path = QLabel("日志文件: iflow-bot + iflow CLI (~/.iflow/log/*.log)")
        log_path.setObjectName("PageSubtitle")
        main.addWidget(log_path)

        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName("LogViewer")
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        main.addWidget(self._log_view, 1)

    def _refresh(self):
        source = self._source_combo.currentData() if hasattr(self, "_source_combo") else "all"
        text = CLIBridge.read_log(self._lines_spin.value(), source=source)
        self._log_view.setPlainText(text)
        if self._auto_scroll:
            sb = self._log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _clear_log(self):
        source = self._source_combo.currentData() if hasattr(self, "_source_combo") else "all"
        CLIBridge.clear_log(source=source)
        self._refresh()
