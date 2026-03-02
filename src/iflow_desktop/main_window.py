"""主窗口。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QFrame, QLabel, QPushButton,
)
from PySide6.QtCore import Qt, QSize, QPoint, QEvent
from PySide6.QtGui import QIcon

from iflow_desktop.widgets.sidebar import Sidebar
from iflow_desktop.core.cli_bridge import StatusMonitor
from iflow_desktop.resources import get_app_icon_path


class MainWindow(QMainWindow):
    """iFlow Desktop 主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("iFlow Desktop")
        self.setWindowIcon(QIcon(str(get_app_icon_path())))
        self.setMinimumSize(QSize(1100, 700))
        self.resize(1360, 820)
        self._dragging = False
        self._drag_position = QPoint()

        # 延迟导入的页面类映射
        self._page_classes: dict[str, type] = {}
        self._pages: dict[str, QWidget] = {}

        self._init_ui()

        # 后台状态监控 - 所有耗时操作在后台线程运行
        self._monitor = StatusMonitor(interval_s=15, parent=self)
        self._monitor.status_updated.connect(self._on_status_update)
        self._monitor.start()

        # 默认显示对话页面
        self._sidebar.set_active("chat")
        self._switch_page("chat")

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 自定义标题栏
        title_bar = QFrame()
        title_bar.setObjectName("CustomTitleBar")
        title_bar.setFixedHeight(36)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 6, 0)
        tb_layout.setSpacing(8)

        self._title_icon = QLabel()
        self._title_icon.setObjectName("TitleBarIcon")
        self._title_icon.setFixedSize(16, 16)
        icon = self.windowIcon()
        if not icon.isNull():
            self._title_icon.setPixmap(icon.pixmap(16, 16))
        tb_layout.addWidget(self._title_icon)

        self._title_label = QLabel("iFlow Desktop")
        self._title_label.setObjectName("WindowTitleText")
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()

        self._min_btn = QPushButton("—")
        self._min_btn.setObjectName("TitleBarBtn")
        self._min_btn.setFixedSize(34, 26)
        self._min_btn.clicked.connect(self.showMinimized)
        tb_layout.addWidget(self._min_btn)

        self._max_btn = QPushButton("□")
        self._max_btn.setObjectName("TitleBarBtn")
        self._max_btn.setFixedSize(34, 26)
        self._max_btn.clicked.connect(self._toggle_max_restore)
        tb_layout.addWidget(self._max_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setObjectName("TitleBarCloseBtn")
        self._close_btn.setFixedSize(34, 26)
        self._close_btn.clicked.connect(self.close)
        tb_layout.addWidget(self._close_btn)

        title_bar.installEventFilter(self)
        self._title_label.installEventFilter(self)
        self._title_icon.installEventFilter(self)
        self._title_bar = title_bar
        layout.addWidget(title_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 侧边栏
        self._sidebar = Sidebar()
        self._sidebar.page_changed.connect(self._switch_page)
        self._sidebar.animation_started.connect(self._on_sidebar_animation_started)
        self._sidebar.animation_finished.connect(self._on_sidebar_animation_finished)
        body_layout.addWidget(self._sidebar)

        # 页面堆栈
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentArea")
        body_layout.addWidget(self._stack, 1)
        layout.addWidget(body, 1)

    def _toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self._max_btn.setText("□")
        else:
            self.showMaximized()
            self._max_btn.setText("❐")

    def eventFilter(self, watched, event):
        if watched in (self._title_bar, self._title_label, self._title_icon):
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self._toggle_max_restore()
                return True

            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._dragging = True
                self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True

            if event.type() == QEvent.MouseMove and self._dragging:
                if not self.isMaximized():
                    self.move(event.globalPosition().toPoint() - self._drag_position)
                return True

            if event.type() == QEvent.MouseButtonRelease:
                self._dragging = False
                return True

        return super().eventFilter(watched, event)

    def _get_page_class(self, key: str):
        """延迟导入页面类，避免启动时加载所有模块。"""
        if not self._page_classes:
            from iflow_desktop.widgets.chat import ChatPage
            from iflow_desktop.widgets.dashboard import DashboardPage
            from iflow_desktop.widgets.auth import AuthPage
            from iflow_desktop.widgets.iflow_config import IFlowConfigPage
            from iflow_desktop.widgets.bot_manager import BotManagerPage
            from iflow_desktop.widgets.log_viewer import LogViewerPage

            self._page_classes = {
                "chat": ChatPage,
                "dashboard": DashboardPage,
                "auth": AuthPage,
                "iflow_config": IFlowConfigPage,
                "bot": BotManagerPage,
                "logs": LogViewerPage,
            }
        return self._page_classes.get(key)

    def _ensure_page(self, key: str) -> QWidget | None:
        """懒加载页面：首次切换时才创建。"""
        if key not in self._pages:
            cls = self._get_page_class(key)
            if cls is None:
                return None
            page = cls()
            self._pages[key] = page
            self._stack.addWidget(page)
        return self._pages[key]

    def _switch_page(self, key: str):
        page = self._ensure_page(key)
        if page:
            self._stack.setCurrentWidget(page)

    def _on_sidebar_animation_started(self):
        if hasattr(self, "_stack") and self._stack is not None:
            self._stack.setUpdatesEnabled(False)

    def _on_sidebar_animation_finished(self):
        if hasattr(self, "_stack") and self._stack is not None:
            self._stack.setUpdatesEnabled(True)
            self._stack.update()

    def _on_status_update(self, data: dict):
        """将后台收集到的状态数据分发到已创建的页面。"""
        for key, page in self._pages.items():
            if hasattr(page, "on_status_update"):
                try:
                    page.on_status_update(data)
                except Exception:
                    pass

    def closeEvent(self, event):
        """窗口关闭时停止后台线程。"""
        self._monitor.stop()
        self._monitor.wait(3000)
        super().closeEvent(event)
