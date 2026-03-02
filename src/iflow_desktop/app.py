"""iFlow Desktop 应用入口。"""

import os
import sys

# 抑制 Qt DirectWrite 字体警告（Fixedsys, Modern 等老旧字体）
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from iflow_desktop.main_window import MainWindow
from iflow_desktop.resources import get_app_icon_path


def main():
    # 高DPI支持 - 必须在 QApplication 创建之前调用
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("iFlow Desktop")
    app.setApplicationVersion("0.2.0")
    app.setOrganizationName("iFlow")
    app.setWindowIcon(QIcon(str(get_app_icon_path())))

    # 默认字体
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    # 加载样式
    from iflow_desktop.resources.style import get_stylesheet
    app.setStyleSheet(get_stylesheet())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
