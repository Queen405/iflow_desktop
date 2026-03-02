"""侧边栏导航。"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Signal, Qt, QVariantAnimation, QEasingCurve


NAV_ITEMS = [
    ("chat",         "💬", "对话"),
    ("dashboard",    "📊", "仪表盘"),
    ("auth",         "🔑", "认证"),
    ("iflow_config", "⚙️", "设置"),
    ("bot",          "🤖", "Bot 服务"),
    ("logs",         "📄", "日志"),
]


class Sidebar(QWidget):
    """左侧导航栏（图标 + 文本）。"""

    page_changed = Signal(str)
    animation_started = Signal()
    animation_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._expanded_width = 200
        self._collapsed_width = 68
        self._collapsed = False
        self._width_anim: QVariantAnimation | None = None
        self._buttons: dict[str, QPushButton] = {}
        self._button_meta: dict[str, tuple[str, str]] = {}
        self._current = ""
        self._init_ui()
        self._apply_collapsed_state(False, animate=False)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo + 折叠按钮
        logo_row = QWidget()
        logo_row_layout = QHBoxLayout(logo_row)
        logo_row_layout.setContentsMargins(10, 0, 10, 0)
        logo_row_layout.setSpacing(6)

        self._logo = QLabel("iFlow Desktop")
        self._logo.setObjectName("SidebarLogo")
        self._logo.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._logo.setFixedHeight(44)
        logo_row_layout.addWidget(self._logo, 1)

        self._toggle_btn = QPushButton("◀")
        self._toggle_btn.setObjectName("SidebarToggleBtn")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.clicked.connect(self._toggle_collapsed)
        logo_row_layout.addWidget(self._toggle_btn, 0, Qt.AlignVCenter)

        layout.addWidget(logo_row)

        # self._ver = QLabel("AI 工作台")
        # self._ver.setObjectName("SidebarVersion")
        # self._ver.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # self._ver.setFixedHeight(18)
        # layout.addWidget(self._ver)

        # 分隔线
        sep = QWidget()
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        layout.addSpacing(4)

        # 导航按钮
        for key, icon, label in NAV_ITEMS:
            btn = QPushButton(f"{icon}  {label}")
            btn.setObjectName("SidebarBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("active", False)
            btn.setProperty("collapsed", False)
            btn.setToolTip(label)
            btn.setFixedHeight(42)
            btn.clicked.connect(lambda checked, k=key: self._on_click(k))
            layout.addWidget(btn)
            self._buttons[key] = btn
            self._button_meta[key] = (icon, label)

        layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        self._bottom = QLabel("Powered by iFlow")
        self._bottom.setObjectName("SidebarVersion")
        self._bottom.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._bottom.setFixedHeight(32)
        layout.addWidget(self._bottom)

    def _toggle_collapsed(self):
        self._apply_collapsed_state(not self._collapsed, animate=True)

    def _apply_collapsed_state(self, collapsed: bool, animate: bool = True):
        self._collapsed = collapsed
        target_width = self._collapsed_width if collapsed else self._expanded_width
        if animate:
            self._animate_width(target_width, on_finished=lambda: self._sync_collapsed_visuals(collapsed))
        else:
            self.setFixedWidth(target_width)
            self._sync_collapsed_visuals(collapsed)

    def _sync_collapsed_visuals(self, collapsed: bool):
        self.setProperty("collapsed", collapsed)
        self._toggle_btn.setText("▶" if collapsed else "◀")

        self._logo.setText("iFlow" if collapsed else "iFlow Desktop")
        # self._ver.setVisible(not collapsed)
        self._bottom.setVisible(not collapsed)

        for key, btn in self._buttons.items():
            icon, label = self._button_meta[key]
            btn.setText(icon if collapsed else f"{icon}  {label}")
            btn.setProperty("collapsed", collapsed)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.style().unpolish(self)
        self.style().polish(self)

    def _animate_width(self, target_width: int, on_finished=None):
        current_width = self.width() or self.maximumWidth() or self._expanded_width
        if self._width_anim is not None:
            self._width_anim.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(140)
        anim.setStartValue(int(current_width))
        anim.setEndValue(int(target_width))
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_value_changed(value):
            width = int(value)
            if width != self.width():
                self.setFixedWidth(width)

        def _on_finished():
            self.setFixedWidth(int(target_width))
            if on_finished is not None:
                on_finished()
            self.animation_finished.emit()

        anim.valueChanged.connect(_on_value_changed)
        anim.finished.connect(_on_finished)
        self.animation_started.emit()
        anim.start()
        self._width_anim = anim

    def _on_click(self, key: str):
        if key == self._current:
            return
        self.set_active(key)
        self.page_changed.emit(key)

    def set_active(self, key: str):
        self._current = key
        for k, btn in self._buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
