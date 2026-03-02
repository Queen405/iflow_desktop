"""Qt 样式表 - 现代暗色主题。"""


def get_stylesheet() -> str:
    return """
/* ========== 全局 ========== */
QMainWindow {
    background-color: #1e1e2e;
    font-family: "Segoe UI", "Microsoft YaHei UI", "Noto Sans SC", sans-serif;
}

QWidget {
    color: #cdd6f4;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", "Noto Sans SC", sans-serif;
}

/* ========== 侧边栏 ========== */
#Sidebar {
    background-color: #161622;
    border-right: 1px solid #26263a;
}

#Sidebar[collapsed="false"] {
    min-width: 200px;
    max-width: 200px;
}

#Sidebar[collapsed="true"] {
    min-width: 68px;
    max-width: 68px;
}

#SidebarLogo {
    color: #dde2ff;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.2px;
    padding: 0 0 0 6px;
}

#SidebarVersion {
    color: #9fa6cb;
    font-size: 12px;
    padding: 0 12px 10px 16px;
}

#SidebarToggleBtn {
    background-color: #202034;
    border: 1px solid #3a3b56;
    border-radius: 8px;
    color: #c5cdf4;
    font-size: 12px;
    font-weight: 700;
    padding: 0;
}

#SidebarToggleBtn:hover {
    background-color: #2c2d43;
    border-color: #55597c;
}

#SidebarBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    color: #9fa4c4;
    font-size: 14px;
    font-weight: 500;
    text-align: left;
    padding: 10px 14px;
    margin: 2px 10px;
}

#SidebarBtn[collapsed="true"] {
    text-align: center;
    padding: 10px 4px;
    margin: 2px 8px;
    font-size: 16px;
}

#SidebarBtn:hover {
    background-color: rgba(180, 190, 254, 0.08);
    color: #d8def8;
    border: 1px solid rgba(180, 190, 254, 0.24);
}

#SidebarBtn[active="true"] {
    background-color: rgba(180, 190, 254, 0.16);
    color: #c7d3ff;
    border: 1px solid rgba(180, 190, 254, 0.34);
}

/* ========== 内容区域 ========== */
#ContentArea {
    background-color: #1a1a28;
}

#CustomTitleBar {
    background-color: #161622;
    border-bottom: 1px solid #26263a;
}

#WindowTitleText {
    color: #d7dcf7;
    font-size: 12px;
    font-weight: 600;
}

#TitleBarBtn {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #a6adc8;
    font-size: 12px;
    font-weight: 600;
    padding: 0;
}

#TitleBarBtn:hover {
    background-color: #2b2c41;
}

#TitleBarCloseBtn {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #f38ba8;
    font-size: 12px;
    font-weight: 600;
    padding: 0;
}

#TitleBarCloseBtn:hover {
    background-color: rgba(243, 139, 168, 0.24);
}

#PageTitle {
    color: #cdd6f4;
    font-size: 18px;
    font-weight: 700;
    padding: 8px 0;
    letter-spacing: -0.3px;
}

#PageSubtitle {
    color: #8c91af;
    font-size: 12px;
    padding-bottom: 12px;
}

/* ========== 卡片 ========== */
#Card {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 12px;
    padding: 20px;
}

#CardTitle {
    color: #cdd6f4;
    font-size: 14px;
    font-weight: 600;
    padding-bottom: 10px;
    border-bottom: 1px solid #313244;
    margin-bottom: 8px;
}

#CardLabel {
    color: #6c7086;
    font-size: 12px;
}

#CardValue {
    color: #cdd6f4;
    font-size: 13px;
    font-weight: 500;
}

/* ========== 状态标签 ========== */
#StatusGreen { color: #a6e3a1; font-weight: 600; font-size: 14px; }
#StatusRed { color: #f38ba8; font-weight: 600; }
#StatusYellow { color: #f9e2af; font-weight: 600; }
#StatusDim { color: #6c7086; font-size: 14px; }

/* ========== 按钮 ========== */
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 8px;
    color: #cdd6f4;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton:disabled {
    background-color: #181825;
    color: #45475a;
    border-color: #313244;
}

#PrimaryBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}

#PrimaryBtn:hover {
    background-color: #b4befe;
}

#PrimaryBtn:disabled {
    background-color: #45475a;
    color: #6c7086;
}

#DangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}

#DangerBtn:hover {
    background-color: #eba0ac;
}

#SuccessBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    border: none;
    font-weight: 600;
}

#SuccessBtn:hover {
    background-color: #94e2d5;
}

#TestConnBtn {
    background-color: rgba(137, 180, 250, 0.15);
    border: 1px solid rgba(137, 180, 250, 0.3);
    border-radius: 6px;
    color: #89b4fa;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 12px;
}

#TestConnBtn:hover {
    background-color: rgba(137, 180, 250, 0.25);
    border-color: #89b4fa;
}

#TestConnBtn:disabled {
    background-color: #181825;
    color: #45475a;
    border-color: #313244;
}

/* ========== 输入框 ========== */
QLineEdit, QPlainTextEdit {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #cdd6f4;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: rgba(137, 180, 250, 0.3);
    selection-color: #cdd6f4;
}

QLineEdit:focus, QPlainTextEdit:focus {
    border-color: #89b4fa;
}

/* ========== 下拉框 ========== */
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 8px;
    color: #cdd6f4;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 100px;
}

QComboBox:hover {
    border-color: #585b70;
}

QComboBox:focus {
    border-color: #89b4fa;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #6c7086;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: rgba(137, 180, 250, 0.2);
    selection-color: #cdd6f4;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}

/* ========== 复选框 ========== */
QCheckBox {
    spacing: 8px;
    color: #cdd6f4;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background: #11111b;
}

QCheckBox::indicator:hover {
    border-color: #89b4fa;
}

QCheckBox::indicator:checked {
    background: #89b4fa;
    border-color: #89b4fa;
}

/* ========== 滚动条 ========== */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 3px;
    min-height: 40px;
}

QScrollBar::handle:vertical:hover {
    background: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 6px;
}

QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 3px;
}

QScrollBar::handle:horizontal:hover {
    background: #585b70;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ========== 表格 ========== */
QTableWidget {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    gridline-color: #313244;
    color: #cdd6f4;
    outline: none;
}

QTableWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #313244;
}

QTableWidget::item:selected {
    background-color: rgba(137, 180, 250, 0.15);
    color: #89b4fa;
}

QHeaderView::section {
    background-color: #181825;
    color: #6c7086;
    border: none;
    border-bottom: 1px solid #313244;
    padding: 10px 12px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ========== Tab ========== */
QTabWidget::pane {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-top: none;
    border-radius: 0 0 8px 8px;
}

QTabBar::tab {
    background-color: transparent;
    color: #6c7086;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    margin-right: 0;
    font-weight: 500;
}

QTabBar::tab:selected {
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    color: #bac2de;
    border-bottom: 2px solid #45475a;
}

/* ========== 对话 - 会话侧边面板 ========== */
#SessionPanel {
    background-color: #171726;
    border-right: 1px solid #2c2c42;
}

#SessionPanelTitle {
    color: #9095b3;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 4px 0;
}

#NewChatBtn {
    background-color: #b4befe;
    color: #1a1b2a;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    font-size: 13px;
}

#NewChatBtn:hover {
    background-color: #c7ceff;
}

#SessionList {
    background-color: transparent;
    border: none;
    color: #a6adc8;
    font-size: 12px;
    outline: none;
}

#SessionList::item {
    background: transparent;
    padding: 0;
    margin: 3px 0;
}

#SessionList::item:hover {
    background-color: transparent;
}

#SessionList::item:selected {
    background-color: transparent;
    color: #a6adc8;
}

#SessionItem {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
}

#SessionItem:hover {
    background-color: rgba(180, 190, 254, 0.08);
    border-color: rgba(180, 190, 254, 0.18);
}

#SessionItem[active="true"] {
    background-color: rgba(180, 190, 254, 0.16);
    border-color: rgba(180, 190, 254, 0.34);
}

#SessionItemMeta {
    color: #9ca2c3;
    font-size: 11px;
}

#SessionItemSummary {
    color: #c7ccef;
    font-size: 12px;
    font-weight: 500;
}

#SessionDeleteBtn {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #8f95b8;
    font-size: 11px;
    font-weight: 700;
    padding: 0;
}

#SessionDeleteBtn:hover {
    background-color: rgba(243, 139, 168, 0.18);
    color: #f6b0c2;
}

#SessionRefreshBtn {
    background: #1f1f2f;
    border: 1px solid #373851;
    border-radius: 10px;
    color: #9aa0bf;
    font-size: 14px;
    padding: 0;
}

#SessionRefreshBtn:hover {
    background: #2a2b41;
    color: #d7ddf9;
    border-color: #4a4c6b;
}

/* ========== 对话 - 工具栏 ========== */
#ChatToolbar {
    background-color: #171726;
    border-bottom: 1px solid #2f3047;
}

#ChatTitle {
    color: #e3e7ff;
    font-size: 16px;
    font-weight: 600;
}

#ToolbarLabel {
    color: #9ca2c3;
    font-size: 12px;
    margin-right: 4px;
}

#ToolbarHint {
    color: #7f86a8;
    font-size: 12px;
}

#WorkspaceBtn {
    background: #1f1f2f;
    border: 1px solid #36384f;
    border-radius: 8px;
    color: #cdd6f4;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
}

#WorkspaceBtn:hover {
    background: #2a2b41;
    border-color: #4a4d6f;
}

#ModelCombo {
    background-color: #1d1e2d;
    border: 1px solid #3b3d58;
    border-radius: 8px;
    color: #cdd6f4;
    padding: 6px 10px;
    font-size: 12px;
    font-family: "Cascadia Code", "Consolas", monospace;
}

#ModelCombo:focus {
    border-color: #89b4fa;
}

#ThinkingToggle {
    color: #8d93b8;
    font-size: 12px;
    font-weight: 600;
    spacing: 6px;
}

#ThinkingToggle::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #484b6a;
    background: #11111b;
}

#ThinkingToggle::indicator:checked {
    background: #b4befe;
    border-color: #b4befe;
}

#ThinkingToggle:checked {
    color: #c7ceff;
}

/* ========== 对话 - 聊天显示区 ========== */
#ChatDisplay {
    background-color: #1a1a28;
    border: none;
    color: #cdd6f4;
    font-size: 14px;
    padding: 16px;
    selection-background-color: rgba(137, 180, 250, 0.3);
    selection-color: #cdd6f4;
}

#ChatScroll {
    background-color: #1a1a28;
    border: none;
}

#ChatScrollContainer {
    background-color: #1a1a28;
}

#UserBubble, #BotBubble {
    background: transparent;
    border: none;
}

#UserContent {
    background-color: #b4befe;
    color: #161622;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    font-size: 14px;
    font-weight: 500;
}

#BotContent, #BotBody {
    background-color: #202033;
    color: #cdd6f4;
    border-radius: 18px 18px 18px 4px;
    padding: 14px 16px;
    font-size: 14px;
    border: 1px solid #3a3b56;
    selection-background-color: rgba(137, 180, 250, 0.3);
    selection-color: #cdd6f4;
}

#BotMarkdown {
    background: transparent;
    border: none;
    padding: 0;
}

#UserRole {
    color: #89b4fa;
    font-weight: 600;
    font-size: 12px;
}

#BotRole {
    color: #a6e3a1;
    font-weight: 600;
    font-size: 12px;
}

#BubbleTs {
    color: #7d82a1;
    font-size: 11px;
}

#BubbleModel {
    color: #7d82a1;
    font-size: 10px;
}

#SystemMsg {
    color: #9095b2;
    font-size: 12px;
    padding: 9px 16px;
}

/* ========== 对话 - 输入框区域 ========== */
#ChatInputFrame {
    background-color: #171726;
    border-top: 1px solid #2f3047;
}

#ChatInputBox {
    background-color: #1d1e2d;
    border: 1px solid #3b3d58;
    border-radius: 12px;
    color: #cdd6f4;
    padding: 9px 12px;
    font-size: 14px;
    selection-background-color: rgba(137, 180, 250, 0.3);
    selection-color: #cdd6f4;
}

#ChatInputBox:focus {
    border-color: #b4befe;
}

#ChatSendBtn {
    background-color: #b4befe;
    border: none;
    border-radius: 20px;
    color: #1a1b2a;
    font-weight: 700;
    font-size: 15px;
    padding: 0;
}

#ChatSendBtn:hover {
    background-color: #c7ceff;
}

#ChatSendBtn:disabled {
    background-color: #313244;
    color: #45475a;
}

#ChatCancelBtn {
    background-color: #f6a0b8;
    border: none;
    border-radius: 20px;
    color: #1a1b2a;
    font-weight: 700;
    font-size: 13px;
    padding: 0;
}

#ChatCancelBtn:hover {
    background-color: #f7b3c5;
}

#ChatMainArea {
    background-color: #1a1a28;
}

/* ========== 日志查看器 ========== */
#LogViewer {
    background-color: #11111b;
    color: #a6adc8;
    border: 1px solid #313244;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 12px;
}

/* ========== 分隔线 ========== */
#Separator {
    background-color: #313244;
    max-height: 1px;
    margin: 8px 0;
}

/* ========== SpinBox ========== */
QSpinBox {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 6px 12px;
}

QSpinBox:focus {
    border-color: #89b4fa;
}

/* ========== GroupBox ========== */
QGroupBox {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 16px;
    padding: 16px;
    padding-top: 32px;
    font-weight: 600;
    color: #cdd6f4;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: #89b4fa;
    font-size: 13px;
}

/* ========== ToolTip ========== */
QToolTip {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 6px 10px;
    font-size: 12px;
}

/* ========== Dialog ========== */
QDialog {
    background-color: #1e1e2e;
}

QDialogButtonBox QPushButton {
    min-width: 80px;
}

/* ========== Splitter ========== */
QSplitter::handle {
    background-color: #2f3047;
    width: 2px;
}

QSplitter::handle:hover {
    background-color: #89b4fa;
}

/* ========== QScrollArea ========== */
QScrollArea {
    background-color: #1e1e2e;
    border: none;
}

QScrollArea > QWidget {
    background-color: #1e1e2e;
}

QScrollArea > QWidget > QWidget {
    background-color: #1e1e2e;
}

/* ========== QTextBrowser (Markdown) ========== */
QTextBrowser {
    background-color: transparent;
    border: none;
    color: #cdd6f4;
    selection-background-color: rgba(137, 180, 250, 0.3);
    selection-color: #cdd6f4;
}

/* ========== QListWidget ========== */
QListWidget {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #cdd6f4;
    outline: none;
}

QListWidget::item {
    padding: 6px 12px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: rgba(137, 180, 250, 0.15);
    color: #89b4fa;
}

QListWidget::item:hover {
    background-color: rgba(137, 180, 250, 0.08);
}

/* ========== QTextEdit ========== */
QTextEdit {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #cdd6f4;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: rgba(137, 180, 250, 0.3);
    selection-color: #cdd6f4;
}

QTextEdit:focus {
    border-color: #89b4fa;
}

/* ========== 工具调用（嵌入 Bot 气泡内） ========== */
#ToolCallWidget {
    background-color: rgba(137, 180, 250, 0.08);
    border: 1px solid rgba(137, 180, 250, 0.15);
    border-radius: 8px;
    margin: 2px 0;
}

#ToolCallName {
    color: #89b4fa;
    font-size: 13px;
    font-weight: 600;
}

#ToolCallParams {
    color: #a6adc8;
    font-size: 12px;
    font-family: "Cascadia Code", "Consolas", monospace;
    background-color: rgba(17, 17, 27, 0.5);
    border-radius: 6px;
    padding: 6px 10px;
}

#ToolIcon {
    font-size: 14px;
}

#ToolToggle {
    color: #6c7086;
    font-size: 11px;
    padding: 0 2px;
}

#ToolDetailFrame {
    background-color: rgba(17, 17, 27, 0.5);
    border-radius: 6px;
    padding: 4px 8px;
}

/* ========== 工具返回结果（嵌入 Bot 气泡内） ========== */
#ToolResultWidget {
    background-color: rgba(166, 227, 161, 0.06);
    border: 1px solid rgba(166, 227, 161, 0.12);
    border-radius: 8px;
    margin: 2px 0;
}

#ToolResultName {
    color: #a6e3a1;
    font-size: 13px;
    font-weight: 600;
}

#ToolResultContent {
    color: #a6adc8;
    font-size: 12px;
    font-family: "Cascadia Code", "Consolas", monospace;
    background-color: rgba(17, 17, 27, 0.5);
    border-radius: 6px;
    padding: 6px 10px;
}

/* ========== 思考内容（嵌入 Bot 气泡内） ========== */
#ThinkingWidget {
    background-color: rgba(203, 166, 247, 0.06);
    border: 1px solid rgba(203, 166, 247, 0.12);
    border-radius: 8px;
    margin: 2px 0;
}

#ThinkingName {
    color: #cba6f7;
    font-size: 13px;
    font-weight: 600;
}

#ThinkingContent {
    color: #a6adc8;
    font-size: 12px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    background-color: rgba(17, 17, 27, 0.5);
    border-radius: 6px;
    padding: 6px 10px;
    line-height: 1.5;
}

#ThinkingDetailFrame {
    background-color: rgba(17, 17, 27, 0.5);
    border-radius: 6px;
    padding: 4px 8px;
}

#WaitingIndicator {
    color: #bac2de;
    font-size: 13px;
    padding: 4px 6px;
}

/* ========== 渠道配置卡片 ========== */
#ChannelCard {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 12px;
    padding: 0;
}

#ChannelCard:hover {
    border-color: #45475a;
}

#ChannelIcon {
    font-size: 18px;
}

#ChannelName {
    color: #cdd6f4;
    font-size: 14px;
    font-weight: 600;
}

#ChannelToggle {
    color: #a6adc8;
    font-size: 12px;
}

#ChannelSep {
    background-color: #313244;
    max-height: 1px;
}

#ChannelFieldLabel {
    color: #6c7086;
    font-size: 12px;
    min-width: 90px;
}

#ChannelFieldEdit {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 5px 8px;
    font-size: 12px;
}

#ChannelFieldEdit:focus {
    border-color: #89b4fa;
}
"""


# Markdown 文档默认样式（用于 QTextBrowser 内部 HTML 渲染）
MARKDOWN_DOC_CSS = """
body {
    color: #cdd6f4;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 14px;
    line-height: 1.6;
    margin: 0;
    padding: 0;
}
code {
    background-color: #313244;
    color: #f38ba8;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 13px;
}
pre {
    background-color: #11111b;
    color: #cdd6f4;
    padding: 14px 18px;
    border-radius: 10px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 13px;
    margin: 8px 0;
    overflow-x: auto;
    border: 1px solid #313244;
}
pre code {
    background: transparent;
    color: #cdd6f4;
    padding: 0;
    font-size: 13px;
}
a {
    color: #89b4fa;
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}
h1, h2, h3, h4, h5, h6 {
    color: #cdd6f4;
    margin-top: 16px;
    margin-bottom: 8px;
    font-weight: 600;
}
h1 { font-size: 20px; }
h2 { font-size: 18px; }
h3 { font-size: 16px; }
blockquote {
    border-left: 3px solid #89b4fa;
    padding-left: 14px;
    color: #a6adc8;
    margin: 8px 0;
    font-style: italic;
}
p {
    margin: 6px 0;
}
ul, ol {
    margin: 6px 0 6px 20px;
}
li {
    margin: 2px 0;
}
table {
    border-collapse: collapse;
    margin: 8px 0;
    width: 100%;
}
th, td {
    border: 1px solid #45475a;
    padding: 8px 14px;
    text-align: left;
}
th {
    background-color: #313244;
    color: #cdd6f4;
    font-weight: 600;
}
td {
    background-color: #181825;
}
hr {
    border: none;
    border-top: 1px solid #313244;
    margin: 12px 0;
}
img {
    max-width: 100%;
    border-radius: 8px;
}
"""
