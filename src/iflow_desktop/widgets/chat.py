"""对话页面 - 支持 Markdown 渲染和流式输出。"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QCheckBox, QTextEdit,
    QListWidget, QListWidgetItem, QSizePolicy, QSplitter,
    QAbstractItemView, QTextBrowser, QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl, QThread, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QTextDocument, QDesktopServices, QFontMetrics
from PySide6.QtNetwork import QNetworkAccessManager

try:
    from shiboken6 import isValid as _isValid
except ImportError:
    def _isValid(obj) -> bool:  # type: ignore[misc]
        try:
            obj.objectName()
            return True
        except RuntimeError:
            return False

from iflow_desktop.core.cli_bridge import CLIBridge, IFlowChatWorker, IFlowSettings
from iflow_desktop.core.shared_utils import (
    extract_thinking_blocks as _extract_thinking_blocks,
    extract_thinking_from_content_part as _extract_thinking_from_content_part,
    extract_thinking_from_message as _extract_thinking_from_message,
    model_display_name,
)
from iflow_desktop.resources.style import MARKDOWN_DOC_CSS


# =====================================================================
# 会话历史侧边栏
# =====================================================================
class SessionItemWidget(QFrame):
    """会话列表项组件（含右上角删除按钮）。"""

    clicked = Signal(str)
    delete_clicked = Signal(str)

    def __init__(self, session_id: str, summary: str, model: str, modified_str: str, messages: int, parent=None):
        super().__init__(parent)
        self.setObjectName("SessionItem")
        self.setProperty("active", False)
        self.setFixedHeight(66)

        self._session_id = session_id
        self._summary_full = " ".join((summary or "").splitlines()).strip() or "(空会话)"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        model_display = model or "-"
        self._meta_label = QLabel(f"{model_display} · {modified_str} · {messages}条")
        self._meta_label.setObjectName("SessionItemMeta")
        self._meta_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        header.addWidget(self._meta_label, 1)

        self._delete_btn = QPushButton("✕")
        self._delete_btn.setObjectName("SessionDeleteBtn")
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.setFixedSize(16, 16)
        self._delete_btn.setToolTip("删除会话")
        self._delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self._session_id))
        header.addWidget(self._delete_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        self._summary_label = QLabel("")
        self._summary_label.setObjectName("SessionItemSummary")
        self._summary_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._summary_label.setWordWrap(False)
        layout.addWidget(self._summary_label)
        self._update_summary_elide()

    def summary(self) -> str:
        return self._summary_full

    def set_active(self, active: bool):
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._session_id)
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_summary_elide()

    def _update_summary_elide(self):
        metrics = QFontMetrics(self._summary_label.font())
        elided = metrics.elidedText(self._summary_full, Qt.ElideRight, max(40, self._summary_label.width() - 2))
        self._summary_label.setText(elided)


class SessionListLoadWorker(QThread):
    """后台加载会话列表，避免主线程卡顿。"""

    loaded = Signal(int, list)
    failed = Signal(int, str)

    def __init__(self, request_id: int, parent=None):
        super().__init__(parent)
        self.request_id = request_id

    def run(self):
        try:
            sessions = CLIBridge.list_iflow_sessions()
            self.loaded.emit(self.request_id, sessions)
        except Exception as e:
            self.failed.emit(self.request_id, str(e))


class SessionListPanel(QFrame):
    """左侧会话历史面板。"""

    session_selected = Signal(str)  # session_id
    new_chat_requested = Signal()
    session_deleted = Signal(str)  # session_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SessionPanel")
        self.setMinimumWidth(170)
        self.setMaximumWidth(420)
        self._titles: dict[str, str] = {}
        self._refresh_worker: SessionListLoadWorker | None = None
        self._refresh_request_id: int = 0
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部按钮行：新对话 + 刷新
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        new_btn = QPushButton("＋  新对话")
        new_btn.setObjectName("NewChatBtn")
        new_btn.setFixedHeight(40)
        new_btn.clicked.connect(self.new_chat_requested.emit)
        top_row.addWidget(new_btn, 1)

        self._refresh_btn = QPushButton("🔄")
        self._refresh_btn.setObjectName("SessionRefreshBtn")
        self._refresh_btn.setFixedSize(40, 40)
        self._refresh_btn.setToolTip("刷新列表")
        self._refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(self._refresh_btn)

        layout.addLayout(top_row)

        # 标题
        header = QLabel("历史会话")
        header.setObjectName("SessionPanelTitle")
        layout.addWidget(header)

        # 列表
        self._list = QListWidget()
        self._list.setObjectName("SessionList")
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setUniformItemSizes(True)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setWrapping(False)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.currentItemChanged.connect(lambda _c, _p: self._sync_item_states())
        layout.addWidget(self._list, 1)

    def refresh(self):
        self._refresh_request_id += 1
        request_id = self._refresh_request_id
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("…")

        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            self._refresh_worker.quit()
            self._refresh_worker.wait(1000)

        self._refresh_worker = SessionListLoadWorker(request_id, self)
        self._refresh_worker.loaded.connect(self._on_refresh_loaded)
        self._refresh_worker.failed.connect(self._on_refresh_failed)
        self._refresh_worker.start()

    def _on_refresh_loaded(self, request_id: int, sessions: list[dict]):
        if request_id != self._refresh_request_id:
            return
        self._list.clear()
        self._titles.clear()
        for s in sessions[:50]:
            session_id = s["id"]
            summary = s.get("summary", "")
            self._titles[session_id] = summary

            item = QListWidgetItem()
            item.setData(Qt.UserRole, session_id)
            item.setSizeHint(QSize(0, 70))
            item.setToolTip(
                f"ID: {s['id']}\n摘要: {s['summary']}\n消息: {s['messages']}条"
            )
            self._list.addItem(item)

            widget = SessionItemWidget(
                session_id=session_id,
                summary=summary,
                model=s.get("model", ""),
                modified_str=s.get("modified_str", ""),
                messages=int(s.get("messages", 0)),
            )
            widget.clicked.connect(self._on_item_widget_clicked)
            widget.delete_clicked.connect(self._on_item_delete_clicked)
            self._list.setItemWidget(item, widget)

        self._sync_item_states()
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("🔄")

    def _on_refresh_failed(self, request_id: int, _err: str):
        if request_id != self._refresh_request_id:
            return
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("🔄")

    def get_session_title(self, session_id: str) -> str:
        return self._titles.get(session_id, "")

    def _on_item_clicked(self, item: QListWidgetItem):
        session_id = item.data(Qt.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    def _on_item_widget_clicked(self, session_id: str):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == session_id:
                self._list.setCurrentItem(item)
                self.session_selected.emit(session_id)
                break

    def _on_item_delete_clicked(self, session_id: str):
        if CLIBridge.delete_session(session_id):
            self.session_deleted.emit(session_id)
            self.refresh()

    def _sync_item_states(self):
        current = self._list.currentItem()
        for i in range(self._list.count()):
            item = self._list.item(i)
            widget = self._list.itemWidget(item)
            if isinstance(widget, SessionItemWidget):
                widget.set_active(item is current)


# 全局网络管理器（用于 Markdown 中的网络图片加载）
_network_manager: QNetworkAccessManager | None = None


def _get_network_manager() -> QNetworkAccessManager:
    global _network_manager
    if _network_manager is None:
        _network_manager = QNetworkAccessManager()
    return _network_manager


# =====================================================================
# Markdown 渲染浏览器 (自动调整高度 + 网络图片)
# =====================================================================
class MarkdownBrowser(QTextBrowser):
    """支持 Markdown 渲染的自适应高度文本浏览器，带渲染节流和网络图片。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BotMarkdown")
        self.setOpenExternalLinks(False)  # 我们自己处理链接
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        # 设置文档默认 CSS
        self.document().setDefaultStyleSheet(MARKDOWN_DOC_CSS)
        self.document().contentsChanged.connect(self._update_height)
        self.setMinimumHeight(30)

        # 渲染节流：流式输出时最多每 80ms 渲染一次 Markdown，避免 UI 卡顿
        self._pending_text: str | None = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(50)
        self._render_timer.timeout.connect(self._flush_render)

        # 网络图片支持
        self._nam = _get_network_manager()
        self._loading_urls: set[str] = set()
        self._loaded_local_urls: set[str] = set()

        # 链接点击事件
        self.anchorClicked.connect(self._on_anchor_clicked)

        self._apply_base_url()

    @staticmethod
    def _normalize_markdown(text: str) -> str:
        """兼容 HTML img 标签，统一转换为 Markdown 图片语法。"""
        if not text:
            return text
        import re

        img_tag_pattern = re.compile(r"<img\b[^>]*>", flags=re.IGNORECASE)
        src_pattern = re.compile(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
        alt_pattern = re.compile(r"\balt\s*=\s*['\"]([^'\"]*)['\"]", flags=re.IGNORECASE)

        def _replace(match):
            tag = match.group(0)
            src_match = src_pattern.search(tag)
            if not src_match:
                return tag
            src = src_match.group(1).strip()
            alt_match = alt_pattern.search(tag)
            alt = alt_match.group(1).strip() if alt_match else ""
            return f"![{alt}]({src})"

        return img_tag_pattern.sub(_replace, text)

    def _apply_base_url(self):
        """设置文档基准目录，支持相对路径图片。"""
        base_dir = Path(CLIBridge.get_chat_workspace()).expanduser()
        try:
            resolved = base_dir.resolve()
        except Exception:
            resolved = base_dir
        self.setSearchPaths([str(resolved)])
        base_url = QUrl.fromLocalFile(str(resolved).rstrip("\\/") + "/")
        self.document().setBaseUrl(base_url)

    def _on_anchor_clicked(self, url: QUrl):
        """外部链接用系统浏览器打开。"""
        QDesktopServices.openUrl(url)

    def set_markdown(self, text: str):
        """设置 Markdown 内容并调整高度。"""
        self._pending_text = None
        self._render_timer.stop()
        self._apply_base_url()
        self.document().setMarkdown(self._normalize_markdown(text))
        self._load_remote_images()
        self._update_height()

    def set_markdown_throttled(self, text: str):
        """节流渲染：缓存文本，延迟渲染。用于流式输出。"""
        self._pending_text = text
        if not self._render_timer.isActive():
            self._render_timer.start()

    def flush_pending(self):
        """立即渲染待处理的文本（流式结束时调用）。"""
        self._render_timer.stop()
        if self._pending_text is not None:
            self._apply_base_url()
            self.document().setMarkdown(self._normalize_markdown(self._pending_text))
            self._pending_text = None
            self._load_remote_images()
            self._update_height()

    def _flush_render(self):
        """定时器回调：渲染缓存的 Markdown。"""
        if self._pending_text is not None:
            self.document().setMarkdown(self._normalize_markdown(self._pending_text))
            self._pending_text = None
            self._update_height()

    def _load_remote_images(self):
        """扫描文档中的图片，为远程 URL 发起网络请求。"""
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        img_name = fmt.toImageFormat().name()
                        if not img_name:
                            it += 1
                            continue
                        if img_name.startswith(("http://", "https://")):
                            if img_name not in self._loading_urls:
                                # 检查文档是否已有该图片的资源
                                res = doc.resource(QTextDocument.ImageResource, QUrl(img_name))
                                if res is None or (hasattr(res, 'isNull') and res.isNull()):
                                    self._loading_urls.add(img_name)
                                    self._fetch_image(img_name)
                        else:
                            self._try_load_local_image(img_name)
                it += 1
            block = block.next()

    def _try_load_local_image(self, img_name: str):
        """加载本地/相对路径图片。"""
        if not img_name or img_name in self._loaded_local_urls:
            return

        from urllib.parse import unquote

        base_dir = Path(CLIBridge.get_chat_workspace()).expanduser()
        candidate: Path | None = None

        url_obj = QUrl(img_name)
        if url_obj.isLocalFile():
            local_file = url_obj.toLocalFile()
            if local_file:
                candidate = Path(local_file)
        elif img_name.startswith("file://"):
            local_file = QUrl(img_name).toLocalFile()
            if local_file:
                candidate = Path(local_file)
        else:
            p = Path(unquote(img_name)).expanduser()
            candidate = p if p.is_absolute() else (base_dir / p)

        if candidate is None:
            return

        try:
            candidate = candidate.resolve()
        except Exception:
            pass

        if not candidate.exists() or not candidate.is_file():
            return

        from PySide6.QtGui import QImage

        img = QImage(str(candidate))
        if img.isNull():
            return

        max_w = max(120, min(self.viewport().width() - 40, 600))
        if img.width() > max_w:
            img = img.scaledToWidth(max_w, Qt.SmoothTransformation)

        doc = self.document()
        doc.addResource(QTextDocument.ImageResource, QUrl(img_name), img)
        doc.addResource(QTextDocument.ImageResource, QUrl.fromLocalFile(str(candidate)), img)
        self._loaded_local_urls.add(img_name)
        self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
        self._update_height()

    def _fetch_image(self, url: str):
        """异步下载图片并插入文档。"""
        from PySide6.QtNetwork import QNetworkRequest
        from PySide6.QtGui import QImage, QPixmap
        from PySide6.QtCore import QByteArray

        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(15000)
        reply = self._nam.get(request)

        def on_finished():
            self._loading_urls.discard(url)
            if reply.error():
                reply.deleteLater()
                return
            data = reply.readAll()
            reply.deleteLater()
            img = QImage()
            if not img.loadFromData(data):
                return
            # 限制最大宽度
            max_w = max(120, min(self.viewport().width() - 40, 600))
            if img.width() > max_w:
                img = img.scaledToWidth(max_w, Qt.SmoothTransformation)
            if not _isValid(self):
                return
            self.document().addResource(
                QTextDocument.ImageResource, QUrl(url), img
            )
            # 刷新文档显示
            self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
            self._update_height()

        reply.finished.connect(on_finished)

    def _update_height(self):
        """根据文档内容自动调整高度。"""
        doc = self.document()
        doc.setTextWidth(self.viewport().width() or 500)
        doc_height = doc.size().height()
        margins = self.contentsMargins()
        total = int(doc_height + margins.top() + margins.bottom() + 8)
        self.setMinimumHeight(max(total, 30))
        self.setMaximumHeight(max(total, 30))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_height()


# =====================================================================
# 聊天气泡
# =====================================================================
class ChatBubble(QFrame):
    """单条消息气泡，bot 消息支持 Markdown 渲染和嵌入工具调用显示。"""

    def __init__(
        self,
        role: str,
        text: str,
        model: str = "",
        timestamp: str = "",
        body_events: list | None = None,
        tool_calls: list | None = None,
        tool_results: list | None = None,
        tool_events: list | None = None,
        thinking_blocks: list[str] | None = None,
        show_waiting: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._role = role
        self._raw_text = text
        self._max_bubble_width = 820
        self._seen_thinking_texts: set[str] = set()
        self._streaming_thinking_widget: ThinkingWidget | None = None
        self._streaming_thinking_text: str = ""
        is_user = role == "user"
        self.setObjectName("UserBubble" if is_user else "BotBubble")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(2)

        # ---- Header: 角色 + 时间 ----
        header = QHBoxLayout()
        header.setSpacing(6)
        ts = timestamp or datetime.now().strftime("%H:%M:%S")

        if is_user:
            header.addStretch()
            ts_lbl = QLabel(ts)
            ts_lbl.setObjectName("BubbleTs")
            header.addWidget(ts_lbl)
            role_lbl = QLabel("你")
            role_lbl.setObjectName("UserRole")
            header.addWidget(role_lbl)
        else:
            role_lbl = QLabel("🤖 iFlow")
            role_lbl.setObjectName("BotRole")
            header.addWidget(role_lbl)
            if model:
                m_lbl = QLabel(f"· {model}")
                m_lbl.setObjectName("BubbleModel")
                header.addWidget(m_lbl)
            ts_lbl = QLabel(ts)
            ts_lbl.setObjectName("BubbleTs")
            header.addWidget(ts_lbl)
            header.addStretch()

        outer.addLayout(header)

        # ---- 气泡正文 ----
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)

        if is_user:
            content_row.addStretch(1)
            # 用户消息：普通 QLabel
            self._content = QLabel(text)
            self._content.setWordWrap(True)
            self._content.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._content.setObjectName("UserContent")
            self._content.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
            content_row.addWidget(self._content)
        else:
            # Bot 消息：思考内容 + 工具调用区 + Markdown 渲染
            bot_col = QVBoxLayout()
            bot_col.setContentsMargins(0, 0, 0, 0)
            bot_col.setSpacing(0)

            # Bot 统一气泡容器（工具和文本都在同一气泡内）
            self._bot_body = QFrame()
            self._bot_body.setObjectName("BotBody")
            self._bot_body.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
            body_layout = QVBoxLayout(self._bot_body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(6)

            self._waiting_label: QLabel | None = None
            self._waiting_frames: list[str] = []
            self._waiting_index = 0
            self._waiting_timer: QTimer | None = None
            if show_waiting:
                self._waiting_label = QLabel("⏳ 正在思考")
                self._waiting_label.setObjectName("WaitingIndicator")
                body_layout.addWidget(self._waiting_label)
                self._waiting_frames = [
                    "⏳ 正在思考",
                    "⏳ 正在思考.",
                    "⏳ 正在思考..",
                    "⏳ 正在思考...",
                ]
                self._waiting_timer = QTimer(self)
                self._waiting_timer.setInterval(320)
                self._waiting_timer.timeout.connect(self._on_waiting_tick)
                self._waiting_timer.start()

            # 顺序容器：文本/工具/思考统一按时序渲染
            self._sequence_container = QVBoxLayout()
            self._sequence_container.setContentsMargins(0, 0, 0, 0)
            self._sequence_container.setSpacing(6)
            body_layout.addLayout(self._sequence_container)

            self._text_segments: list[MarkdownBrowser] = []
            self._text_segment_texts: list[str] = []
            self._last_sequence_type: str = ""
            self._rendered_clean_text: str = ""

            # 初始化时按 body_events 顺序渲染（优先）
            if body_events:
                for event in body_events:
                    self.add_body_event(event)
                # 额外处理 thinking_blocks（可能在 content_events 中没有 thinking 事件时传入）
                # 这里不会重复添加，因为 add_thinking 有去重逻辑
                if thinking_blocks:
                    for tb in thinking_blocks:
                        self.add_thinking(tb)
            else:
                # 兼容旧参数：历史 thinking_blocks 先作为顺序事件渲染
                if thinking_blocks:
                    for tb in thinking_blocks:
                        self.add_thinking(tb)
                if text:
                    self._add_text_segment(text)
                # 兼容旧参数
                if tool_events:
                    for event in tool_events:
                        self.add_tool_event(event)
                else:
                    if tool_calls:
                        for tc in tool_calls:
                            self.add_tool_call(tc.get("tool_name", ""), tc.get("input", ""))
                    if tool_results:
                        for tr in tool_results:
                            self.add_tool_result(
                                tr.get("tool_name", ""),
                                tr.get("status", ""),
                                tr.get("content", ""),
                            )

            bot_col.addWidget(self._bot_body)
            bot_col.addStretch(1)

            content_row.addLayout(bot_col)
            content_row.addStretch(1)

        outer.addLayout(content_row)
        self._apply_width_constraints()

    # ---- 思考内容 / 工具调用嵌入方法（用于流式过程中实时插入） ----

    def add_thinking(self, thinking_text: str):
        """在气泡内添加思考内容显示。"""
        if self._role == "user" or not hasattr(self, "_sequence_container"):
            return
        normalized = (thinking_text or "").strip()
        if not normalized:
            return
        if normalized in self._seen_thinking_texts:
            return
        self._seen_thinking_texts.add(normalized)
        w = ThinkingWidget(normalized)
        self._sequence_container.addWidget(w)
        self._last_sequence_type = "thinking"
        self._streaming_thinking_widget = None
        self._streaming_thinking_text = ""
        self._mark_response_started()

    def append_thinking_delta(self, delta_text: str):
        """流式追加思考文本（默认折叠展示）。"""
        if self._role == "user" or not hasattr(self, "_sequence_container"):
            return
        if not delta_text:
            return
        normalized = delta_text.strip()
        if not normalized:
            return
        if self._streaming_thinking_widget is None or self._last_sequence_type != "thinking":
            self._streaming_thinking_text = normalized
            self._streaming_thinking_widget = ThinkingWidget(self._streaming_thinking_text)
            self._sequence_container.addWidget(self._streaming_thinking_widget)
            self._last_sequence_type = "thinking"
        else:
            if normalized.startswith(self._streaming_thinking_text):
                self._streaming_thinking_text = normalized
                self._streaming_thinking_widget.set_text(self._streaming_thinking_text)
            else:
                self._streaming_thinking_text += ("\n" + normalized)
                self._streaming_thinking_widget.set_text(self._streaming_thinking_text)
        self._mark_response_started()

    def add_tool_call(self, tool_name: str, tool_input: dict | str = ""):
        """在气泡内添加工具调用显示。"""
        if self._role != "user" and hasattr(self, "_sequence_container"):
            w = ToolCallWidget(tool_name, tool_input)
            self._sequence_container.addWidget(w)
            self._last_sequence_type = "tool"

    def add_tool_result(self, tool_name: str, status: str = "", content: str = ""):
        """在气泡内添加工具结果显示。"""
        if self._role != "user" and hasattr(self, "_sequence_container"):
            w = ToolResultWidget(tool_name, status, content)
            self._sequence_container.addWidget(w)
            self._last_sequence_type = "tool"

    def _add_text_segment(self, text: str):
        if self._role == "user" or not hasattr(self, "_sequence_container"):
            return
        if text and text.strip():
            self._mark_response_started()
        md = MarkdownBrowser()
        md.set_markdown(text)
        self._sequence_container.addWidget(md)
        self._text_segments.append(md)
        self._text_segment_texts.append(text)
        self._last_sequence_type = "text"

    def _append_text_delta(self, delta: str):
        if not delta:
            return
        if self._last_sequence_type == "text" and self._text_segments:
            idx = len(self._text_segments) - 1
            merged = self._text_segment_texts[idx] + delta
            self._text_segment_texts[idx] = merged
            self._text_segments[idx].set_markdown_throttled(merged)
        else:
            self._add_text_segment(delta)

    def add_body_event(self, event: dict):
        event_type = event.get("type", "")
        if event_type == "text":
            text = event.get("content", "")
            if text:
                self._add_text_segment(text)
        elif event_type == "thinking":
            self.add_thinking(event.get("content", ""))
        elif event_type == "call":
            self.add_tool_call(event.get("tool_name", ""), event.get("input", ""))
        elif event_type == "result":
            self.add_tool_result(
                event.get("tool_name", ""),
                event.get("status", ""),
                event.get("content", ""),
            )

    def add_tool_event(self, event: dict):
        """按顺序添加单个工具事件（call/result）。"""
        event_type = event.get("type", "")
        if event_type == "call":
            self.add_tool_call(event.get("tool_name", ""), event.get("input", ""))
        elif event_type == "result":
            self.add_tool_result(
                event.get("tool_name", ""),
                event.get("status", ""),
                event.get("content", ""),
            )

    def update_text(self, text: str):
        """更新气泡文本（流式时使用节流渲染）。
        自动提取 <think>/<thinking> 块作为思考内容显示。"""
        self._raw_text = text
        if self._role == "user":
            self._content.setText(text)
        else:
            clean, blocks = _extract_thinking_blocks(text)
            # 思考内容去重：只添加新发现的
            existing = getattr(self, "_seen_thinking_count", 0)
            if len(blocks) > existing:
                for tb in blocks[existing:]:
                    self.add_thinking(tb)
                self._seen_thinking_count = len(blocks)
            if clean.strip() or blocks:
                self._mark_response_started()
            if clean.startswith(self._rendered_clean_text):
                delta = clean[len(self._rendered_clean_text):]
                self._append_text_delta(delta)
            else:
                if self._text_segments:
                    self._text_segment_texts[0] = clean
                    self._text_segments[0].set_markdown_throttled(clean)
                    for idx in range(1, len(self._text_segments)):
                        self._text_segment_texts[idx] = ""
                        self._text_segments[idx].set_markdown_throttled("")
                else:
                    self._add_text_segment(clean)
            self._rendered_clean_text = clean
            self._apply_width_constraints()

    def finalize_text(self):
        """流式结束后刷新最终渲染。"""
        if self._role != "user":
            # 最终文本中再次提取思考块，确保完整
            clean, blocks = _extract_thinking_blocks(self._raw_text)
            existing = getattr(self, "_seen_thinking_count", 0)
            if len(blocks) > existing:
                for tb in blocks[existing:]:
                    self.add_thinking(tb)
                self._seen_thinking_count = len(blocks)
            if self._text_segments:
                for seg in self._text_segments:
                    seg.flush_pending()
            self._mark_response_started(force=True)
            self._apply_width_constraints()

    def _on_waiting_tick(self):
        if self._role == "user" or self._waiting_label is None or not self._waiting_frames:
            return
        self._waiting_index = (self._waiting_index + 1) % len(self._waiting_frames)
        self._waiting_label.setText(self._waiting_frames[self._waiting_index])

    def _mark_response_started(self, force: bool = False):
        if self._role == "user" or self._waiting_label is None:
            return
        has_response = force or bool(getattr(self, "_raw_text", "").strip())
        if not has_response and hasattr(self, "_sequence_container"):
            has_response = self._sequence_container.count() > 0
        if has_response:
            self._waiting_label.setVisible(False)
            if self._waiting_timer is not None:
                self._waiting_timer.stop()

    def get_raw_text(self) -> str:
        """获取原始文本。"""
        return self._raw_text

    def set_max_bubble_width(self, max_width: int):
        """设置气泡最大宽度（由聊天视图根据窗口宽度驱动）。"""
        min_width = 180 if self._role == "user" else 320
        self._max_bubble_width = max(min_width, max_width)
        self._apply_width_constraints()

    def _apply_width_constraints(self):
        """按角色固定气泡宽度：用户 50%，助手 75%（不足时也填满）。"""
        max_w = self._max_bubble_width
        if self._role == "user":
            target = max(180, max_w)
            if hasattr(self, "_content"):
                self._content.setMinimumWidth(target)
                self._content.setMaximumWidth(target)
        else:
            target = max(260, max_w)

            if hasattr(self, "_bot_body"):
                # 始终固定为 70% 宽度
                self._bot_body.setMinimumWidth(target)
                self._bot_body.setMaximumWidth(target)
            if hasattr(self, "_text_segments"):
                text_w = max(220, target - 8)
                for seg in self._text_segments:
                    seg.setMinimumWidth(220)
                    seg.setMaximumWidth(text_w)


class SystemMessage(QLabel):
    """系统提示消息（居中灰色）。"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("SystemMsg")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)


class ToolCallWidget(QFrame):
    """工具调用内联显示组件，详情默认折叠，点击展开/收起。嵌入在 Bot 气泡内。"""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict | str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("ToolCallWidget")
        self.setCursor(Qt.PointingHandCursor)
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header
        header = QHBoxLayout()
        header.setSpacing(4)
        self._toggle_lbl = QLabel("▶")
        self._toggle_lbl.setObjectName("ToolToggle")
        header.addWidget(self._toggle_lbl)
        icon = QLabel("🔧")
        icon.setObjectName("ToolIcon")
        header.addWidget(icon)
        name_lbl = QLabel(f"调用工具: {tool_name}")
        name_lbl.setObjectName("ToolCallName")
        name_lbl.setWordWrap(True)
        header.addWidget(name_lbl, 1)
        layout.addLayout(header)

        # 可折叠详情
        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("ToolDetailFrame")
        self._detail_frame.setMaximumHeight(0)
        self._detail_frame.setVisible(True)  # 始终可见，通过 maxHeight 控制
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(2)

        if tool_input:
            import json as _json
            if isinstance(tool_input, dict):
                param_text = _json.dumps(tool_input, ensure_ascii=False, indent=2)
            else:
                param_text = str(tool_input)
            if len(param_text) > 800:
                param_text = param_text[:800] + "..."
            param_lbl = QLabel(param_text)
            param_lbl.setObjectName("ToolCallParams")
            param_lbl.setWordWrap(True)
            param_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            detail_layout.addWidget(param_lbl)

        layout.addWidget(self._detail_frame)
        self._anim: QPropertyAnimation | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._toggle_lbl.setText("▼" if self._expanded else "▶")
            self._animate_toggle()
        super().mousePressEvent(event)

    def _animate_toggle(self):
        if self._anim is not None:
            self._anim.stop()
        target_h = self._detail_frame.sizeHint().height() if self._expanded else 0
        self._anim = QPropertyAnimation(self._detail_frame, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setStartValue(self._detail_frame.maximumHeight())
        self._anim.setEndValue(target_h)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if not self._expanded:
            self._anim.finished.connect(lambda: self._detail_frame.setMaximumHeight(0))
        else:
            # 动画完成后移除高度限制以自适应内容
            self._anim.finished.connect(lambda: self._detail_frame.setMaximumHeight(16777215))
        self._anim.start()


class ToolResultWidget(QFrame):
    """工具返回结果内联显示组件，详情默认折叠。嵌入在 Bot 气泡内。"""

    def __init__(
        self,
        tool_name: str,
        status: str = "",
        content: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("ToolResultWidget")
        self.setCursor(Qt.PointingHandCursor)
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header
        header = QHBoxLayout()
        header.setSpacing(4)
        self._toggle_lbl = QLabel("▶")
        self._toggle_lbl.setObjectName("ToolToggle")
        header.addWidget(self._toggle_lbl)
        status_icon = "✅" if status == "success" else "❌" if status == "error" else "📋"
        icon = QLabel(status_icon)
        icon.setObjectName("ToolIcon")
        header.addWidget(icon)
        status_text = "成功" if status == "success" else "失败" if status == "error" else "完成"
        name_lbl = QLabel(f"工具返回 ({tool_name}): {status_text}")
        name_lbl.setObjectName("ToolResultName")
        name_lbl.setWordWrap(True)
        header.addWidget(name_lbl, 1)
        layout.addLayout(header)

        # 可折叠详情
        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("ToolDetailFrame")
        self._detail_frame.setMaximumHeight(0)
        self._detail_frame.setVisible(True)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(2)

        if content:
            display_text = content
            try:
                import json as _json
                parsed = _json.loads(content)
                if isinstance(parsed, dict):
                    display_text = _json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception:
                pass
            if len(display_text) > 1000:
                display_text = display_text[:1000] + "..."
            result_lbl = QLabel(display_text)
            result_lbl.setObjectName("ToolResultContent")
            result_lbl.setWordWrap(True)
            result_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            detail_layout.addWidget(result_lbl)

        layout.addWidget(self._detail_frame)
        self._anim: QPropertyAnimation | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._toggle_lbl.setText("▼" if self._expanded else "▶")
            self._animate_toggle()
        super().mousePressEvent(event)

    def _animate_toggle(self):
        if self._anim is not None:
            self._anim.stop()
        target_h = self._detail_frame.sizeHint().height() if self._expanded else 0
        self._anim = QPropertyAnimation(self._detail_frame, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setStartValue(self._detail_frame.maximumHeight())
        self._anim.setEndValue(target_h)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if not self._expanded:
            self._anim.finished.connect(lambda: self._detail_frame.setMaximumHeight(0))
        else:
            self._anim.finished.connect(lambda: self._detail_frame.setMaximumHeight(16777215))
        self._anim.start()


class ThinkingWidget(QFrame):
    """思考内容内联显示组件，默认折叠，点击展开/收起。嵌入在 Bot 气泡内。"""

    def __init__(self, thinking_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ThinkingWidget")
        self.setCursor(Qt.PointingHandCursor)
        self._expanded = False
        self._full_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header
        header = QHBoxLayout()
        header.setSpacing(4)
        self._toggle_lbl = QLabel("▶")
        self._toggle_lbl.setObjectName("ToolToggle")
        header.addWidget(self._toggle_lbl)
        icon = QLabel("💭")
        icon.setObjectName("ToolIcon")
        header.addWidget(icon)
        name_lbl = QLabel("思考过程")
        name_lbl.setObjectName("ThinkingName")
        name_lbl.setWordWrap(True)
        header.addWidget(name_lbl, 1)
        layout.addLayout(header)

        # 可折叠详情
        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("ThinkingDetailFrame")
        self._detail_frame.setMaximumHeight(0)
        self._detail_frame.setVisible(True)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(2)

        self._content_lbl = QLabel("")
        self._content_lbl.setObjectName("ThinkingContent")
        self._content_lbl.setWordWrap(True)
        self._content_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self._content_lbl)

        if thinking_text:
            self.set_text(thinking_text)

        layout.addWidget(self._detail_frame)
        self._anim: QPropertyAnimation | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self._toggle_lbl.setText("▼" if self._expanded else "▶")
            self._animate_toggle()
        super().mousePressEvent(event)

    def _animate_toggle(self):
        if self._anim is not None:
            self._anim.stop()
        target_h = self._detail_frame.sizeHint().height() if self._expanded else 0
        self._anim = QPropertyAnimation(self._detail_frame, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setStartValue(self._detail_frame.maximumHeight())
        self._anim.setEndValue(target_h)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if not self._expanded:
            self._anim.finished.connect(lambda: self._detail_frame.setMaximumHeight(0))
        else:
            self._anim.finished.connect(lambda: self._detail_frame.setMaximumHeight(16777215))
        self._anim.start()

    def set_text(self, thinking_text: str):
        self._full_text = thinking_text or ""
        display = self._full_text
        if len(display) > 12000:
            display = display[:12000] + "..."
        self._content_lbl.setText(display)

    def append_text(self, delta: str):
        if not delta:
            return
        self.set_text((self._full_text + delta).strip())


# =====================================================================
# 聊天显示区域
# =====================================================================
class ChatScrollArea(QScrollArea):
    """聊天消息展示区域。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("ChatScroll")

        self._container = QWidget()
        self._container.setObjectName("ChatScrollContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(12)
        self._layout.addStretch()

        self.setWidget(self._container)
        self._streaming_bubble: ChatBubble | None = None
        self._streaming_text: str = ""
        self._widgets: list[QWidget] = []
        self._pending_bubbles: list[ChatBubble] = []
        self._scroll_scheduled = False
        self._suspend_layout_updates = False

    # ---- 公共 API ----

    def add_user_message(self, text: str, timestamp: str = ""):
        bubble = ChatBubble("user", text, timestamp=timestamp)
        self._insert_widget(bubble)

    def add_bot_message(
        self, text: str, model: str = "", timestamp: str = "",
        body_events: list | None = None,
        tool_calls: list | None = None,
        tool_results: list | None = None,
        tool_events: list | None = None,
        thinking_blocks: list[str] | None = None,
    ):
        # 从文本中提取思考块
        clean_text, extracted_blocks = _extract_thinking_blocks(text)
        all_thinking = (thinking_blocks or []) + extracted_blocks
        bubble = ChatBubble(
            "assistant", clean_text, model=model, timestamp=timestamp,
            body_events=body_events,
            tool_calls=tool_calls, tool_results=tool_results,
            tool_events=tool_events,
            thinking_blocks=all_thinking if all_thinking else None,
        )
        self._insert_widget(bubble)

    def add_system_message(self, text: str):
        msg = SystemMessage(text)
        self._insert_widget(msg)

    def begin_streaming(self):
        """开始流式输出：创建空的 bot 气泡。"""
        self._streaming_text = ""
        self._streaming_bubble = ChatBubble("assistant", "", show_waiting=True)
        self._insert_widget(self._streaming_bubble)

    def get_streaming_bubble(self) -> ChatBubble | None:
        """返回当前流式气泡（用于插入工具调用）。"""
        if self._streaming_bubble is not None and _isValid(self._streaming_bubble):
            return self._streaming_bubble
        return None

    def append_streaming(self, text: str):
        """追加流式文本到当前气泡（使用累加器，支持 Markdown 实时渲染）。"""
        if self._streaming_bubble is None:
            return
        if not _isValid(self._streaming_bubble):
            self._streaming_bubble = None
            return
        self._streaming_text += text
        try:
            self._streaming_bubble.update_text(self._streaming_text)
        except RuntimeError:
            self._streaming_bubble = None
            return
        self.scroll_to_bottom()

    def end_streaming(self):
        """结束流式输出，刷新最终 Markdown 渲染。"""
        if self._streaming_bubble is not None:
            try:
                if _isValid(self._streaming_bubble):
                    self._streaming_bubble.finalize_text()
            except RuntimeError:
                pass
        self._streaming_bubble = None
        self._streaming_text = ""

    def set_streaming_text(self, full_text: str):
        """直接设置流式文本（重新附加会话时使用）。"""
        if self._streaming_bubble is None:
            return
        if not _isValid(self._streaming_bubble):
            self._streaming_bubble = None
            return
        self._streaming_text = full_text
        try:
            self._streaming_bubble.update_text(full_text)
        except RuntimeError:
            self._streaming_bubble = None
            return
        self.scroll_to_bottom()

    def clear_all(self):
        """清除所有消息。"""
        self._streaming_bubble = None
        self._streaming_text = ""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._widgets.clear()

    def update_last_bot_text(self, text: str):
        """更新最后一个 bot 气泡的文本（用于去除 Execution Info）。"""
        for w in reversed(self._widgets):
            if isinstance(w, ChatBubble) and w._role == "assistant":
                if _isValid(w):
                    w.update_text(text)
                    w.finalize_text()
                break

    def scroll_to_bottom(self):
        if self._scroll_scheduled:
            return
        self._scroll_scheduled = True
        QTimer.singleShot(10, self._do_scroll)

    def begin_bulk_insert(self):
        self._suspend_layout_updates = True
        self._pending_bubbles.clear()

    def end_bulk_insert(self, update_widths: bool = True, auto_scroll: bool = True):
        self._suspend_layout_updates = False
        if update_widths:
            self._update_bubble_widths()
        else:
            self._update_specific_bubble_widths(self._pending_bubbles)
        self._pending_bubbles.clear()
        if auto_scroll:
            self.scroll_to_bottom()

    # ---- 内部 ----

    def _insert_widget(self, widget: QWidget):
        self._widgets.append(widget)
        count = self._layout.count()
        self._layout.insertWidget(count - 1, widget)
        if self._suspend_layout_updates and isinstance(widget, ChatBubble):
            self._pending_bubbles.append(widget)
        if not self._suspend_layout_updates:
            self._update_bubble_widths()
            self.scroll_to_bottom()

    def _do_scroll(self):
        self._scroll_scheduled = False
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_bubble_widths(self):
        """按当前视图宽度更新所有气泡宽度（用户 50%，助手 75%）。"""
        available = self.viewport().width()
        user_width = int(max(180, available * 0.50))
        assistant_width = int(max(320, available * 0.75))
        for w in self._widgets:
            if isinstance(w, ChatBubble):
                if w._role == "user":
                    w.set_max_bubble_width(user_width)
                else:
                    w.set_max_bubble_width(assistant_width)

    def _update_specific_bubble_widths(self, bubbles: list[ChatBubble]):
        """仅更新新增气泡宽度，避免恢复历史时反复全量 O(n^2) 刷新。"""
        if not bubbles:
            return
        available = self.viewport().width()
        user_width = int(max(180, available * 0.50))
        assistant_width = int(max(320, available * 0.75))
        for bubble in bubbles:
            if not _isValid(bubble):
                continue
            if bubble._role == "user":
                bubble.set_max_bubble_width(user_width)
            else:
                bubble.set_max_bubble_width(assistant_width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_bubble_widths()


# =====================================================================
# 输入框 (多行)
# =====================================================================
class ChatInput(QTextEdit):
    """多行输入框，Enter 发送，Shift+Enter 换行。"""

    send_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatInputBox")
        self.setPlaceholderText("给 iFlow 发送消息…（Enter 发送，Shift+Enter 换行）")
        self.setMaximumHeight(104)
        self.setMinimumHeight(40)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                text = self.toPlainText().strip()
                if text:
                    self.send_requested.emit(text)
                    self.clear()
        else:
            super().keyPressEvent(event)


class SessionLoadWorker(QThread):
    """后台加载会话消息，避免 UI 卡顿。"""

    loaded = Signal(str, list)
    failed = Signal(str, str)

    def __init__(self, session_id: str, parent=None):
        super().__init__(parent)
        self.session_id = session_id

    def run(self):
        try:
            messages = CLIBridge.load_session_messages(self.session_id)
            self.loaded.emit(self.session_id, messages)
        except Exception as e:
            self.failed.emit(self.session_id, str(e))


# =====================================================================
# 对话页面
# =====================================================================
class ChatPage(QWidget):
    """对话界面 - 应用核心功能。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: IFlowChatWorker | None = None
        self._session_loader: SessionLoadWorker | None = None
        self._current_session_id: str = ""
        self._session_titles: dict[str, str] = {}
        self._default_model: str = IFlowSettings.get_model() or "glm-5"
        self._session_model_overrides: dict[str, str] = {}
        self._chat_workspace: str = CLIBridge.get_chat_workspace()
        self._streaming_text = ""
        self._worker_session_id: str = ""   # worker 正在处理的 session ID
        self._worker_user_msg: str = ""     # 触发 worker 的用户消息
        self._worker_detached: bool = False  # 用户是否已切走到其他 session
        self._last_stdout_time: float = 0.0  # 上次收到 stdout 数据的时间
        self._response_started_at: float = 0.0  # 当前轮次开始时间
        self._stream_event_backlog: list[dict] = []  # 流式期间的思考/工具事件缓存
        self._stream_event_signatures: set[str] = set()  # 流式事件去重
        self._restore_render_items: list[dict] = []
        self._restore_render_index: int = 0
        self._restore_target_session_id: str = ""
        self._pending_live_reattach_session_id: str = ""
        self._last_models_with_source: list[tuple[str, str]] = []
        self._splitter_left_size: int = 280
        self._init_ui()

    def _init_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 会话列表与聊天区固定宽度分割（不可拖拽）
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setChildrenCollapsible(False)

        # 左侧：会话历史面板
        self._session_panel = SessionListPanel()
        self._session_panel.setMinimumWidth(self._splitter_left_size)
        self._session_panel.setMaximumWidth(self._splitter_left_size)
        self._session_panel.session_selected.connect(self._restore_session)
        self._session_panel.new_chat_requested.connect(self._new_chat)
        self._session_panel.session_deleted.connect(self._on_session_deleted)
        splitter.addWidget(self._session_panel)

        # 右侧：聊天区
        chat_area = QWidget()
        chat_area.setObjectName("ChatMainArea")
        chat_layout = QVBoxLayout(chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QFrame()
        toolbar.setObjectName("ChatToolbar")
        toolbar.setFixedHeight(60)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(20, 0, 20, 0)
        tb_layout.setSpacing(10)

        self._title_label = QLabel("新对话")
        self._title_label.setObjectName("ChatTitle")
        tb_layout.addWidget(self._title_label)

        self._workspace_btn = QPushButton()
        self._workspace_btn.setObjectName("WorkspaceBtn")
        self._workspace_btn.setFixedHeight(30)
        self._workspace_btn.clicked.connect(self._select_chat_workspace)
        tb_layout.addWidget(self._workspace_btn)

        self._workspace_hint = QLabel("")
        self._workspace_hint.setObjectName("ToolbarHint")
        self._workspace_hint.setFixedWidth(220)
        tb_layout.addWidget(self._workspace_hint)

        tb_layout.addStretch()

        # 模型选择
        model_label = QLabel("模型")
        model_label.setObjectName("ToolbarLabel")
        tb_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setObjectName("ModelCombo")
        self._model_combo.setEditable(True)
        self._model_combo.setFixedWidth(260)
        self._populate_model_combo(self._default_model)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        tb_layout.addWidget(self._model_combo)

        chat_layout.addWidget(toolbar)

        # 聊天显示区域
        self._display = ChatScrollArea()
        chat_layout.addWidget(self._display, 1)

        # 底部输入区
        input_frame = QFrame()
        input_frame.setObjectName("ChatInputFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 10, 16, 12)
        input_layout.setSpacing(8)

        thinking_row = QHBoxLayout()
        thinking_row.setContentsMargins(0, 0, 0, 0)
        thinking_row.setSpacing(6)

        self._thinking_cb = QCheckBox("💡 深度思考")
        self._thinking_cb.setObjectName("ThinkingToggle")
        self._thinking_cb.setChecked(IFlowSettings.get_thinking())
        thinking_row.addWidget(self._thinking_cb)
        thinking_row.addStretch()
        input_layout.addLayout(thinking_row)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(10)

        self._input = ChatInput()
        self._input.send_requested.connect(self._send)
        content_row.addWidget(self._input, 1)

        # 按钮列
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        btn_col.addStretch()

        self._send_btn = QPushButton("➜")
        self._send_btn.setObjectName("ChatSendBtn")
        self._send_btn.setFixedSize(40, 40)
        self._send_btn.clicked.connect(self._on_send_click)
        btn_col.addWidget(self._send_btn, 0, Qt.AlignHCenter)

        self._cancel_btn = QPushButton("■")
        self._cancel_btn.setObjectName("ChatCancelBtn")
        self._cancel_btn.setFixedSize(40, 40)
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel)
        btn_col.addWidget(self._cancel_btn, 0, Qt.AlignHCenter)

        btn_col.addStretch()
        content_row.addLayout(btn_col)

        input_layout.addLayout(content_row)

        chat_layout.addWidget(input_frame)

        splitter.addWidget(chat_area)
        splitter.setHandleWidth(0)
        splitter.setSizes([280, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # 禁止拖拽分割线：使 handle 不可交互
        handle = splitter.handle(1)
        if handle:
            handle.setEnabled(False)
            handle.setCursor(Qt.ArrowCursor)
        self._splitter = splitter
        outer.addWidget(splitter)

        # 欢迎
        self._display.add_system_message(
            "👋 欢迎使用 iFlow Desktop"
        )
        self._display.add_system_message(
            "左侧可切换历史会话；在「iFlow 设置」中管理 MCP、Skills 与代理。"
        )
        self._update_workspace_ui()

    def _on_splitter_moved(self, pos: int, _index: int):
        self._splitter_left_size = max(170, min(420, int(pos)))

    def _restore_splitter_position(self):
        if not hasattr(self, "_splitter"):
            return
        left = int(self._splitter_left_size or 280)
        self._session_panel.setMinimumWidth(left)
        self._session_panel.setMaximumWidth(left)
        total = max(800, self._splitter.size().width())
        right = max(300, total - left)
        self._splitter.setSizes([left, right])

    def _short_workspace_name(self, workspace: str) -> str:
        p = Path(workspace)
        return p.name or str(p)

    def _update_workspace_ui(self):
        ws = self._chat_workspace or CLIBridge.get_chat_workspace()
        self._chat_workspace = ws
        self._workspace_btn.setText(f"📁 {self._short_workspace_name(ws)}")
        self._workspace_btn.setToolTip(ws)
        self._workspace_hint.setText("聊天工作区")
        self._workspace_hint.setToolTip(ws)

    def _apply_chat_workspace(self, workspace: str, announce: bool = True):
        if not workspace:
            return
        try:
            resolved = str(Path(workspace).expanduser().resolve())
        except Exception:
            resolved = str(Path(workspace).expanduser())

        if resolved == self._chat_workspace:
            return

        self._chat_workspace = CLIBridge.set_chat_workspace(resolved)
        self._current_session_id = ""
        # 清除会话缓存，确保新工作区的会话列表正确加载
        CLIBridge.invalidate_session_caches()
        self._session_panel.refresh()
        self._new_chat()
        self._update_workspace_ui()
        if announce:
            self._display.add_system_message(f"📁 会话工作区已切换到: {self._chat_workspace}")

    def _select_chat_workspace(self):
        if self._worker is not None:
            QMessageBox.information(self, "提示", "请先等待当前对话完成后再切换工作区。")
            return
        current = self._chat_workspace or CLIBridge.get_chat_workspace()
        d = QFileDialog.getExistingDirectory(self, "选择对话工作区", current)
        if d:
            self._apply_chat_workspace(d, announce=True)

    # ------------------------------------------------------------------
    # 模型列表辅助方法
    # ------------------------------------------------------------------
    def _populate_model_combo(self, selected_model: str = ""):
        """加载模型列表到下拉框（带来源标签）。"""
        current = selected_model or self._get_selected_model() or self._default_model
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        models = CLIBridge.get_iflow_models_with_source()
        for m in models:
            prefix = "CLI" if m["source"] == "cli" else "API"
            display_name = model_display_name(m["name"])
            self._model_combo.addItem(f"[{prefix}] {display_name}", m["name"])
            idx = self._model_combo.count() - 1
            self._model_combo.setItemData(idx, m["source"], Qt.UserRole + 1)
        if current:
            for i in range(self._model_combo.count()):
                if self._model_combo.itemData(i) == current:
                    self._model_combo.setCurrentIndex(i)
                    break
            else:
                self._model_combo.setCurrentText(current)
        self._model_combo.blockSignals(False)

    def _get_selected_model(self) -> str:
        from iflow_desktop.core.shared_utils import get_selected_model_from_combo
        return get_selected_model_from_combo(self._model_combo)

    def _get_selected_model_source(self) -> str:
        """获取当前选中模型来源: cli | api。"""
        text = self._model_combo.currentText().strip()
        idx = self._model_combo.currentIndex()
        if idx >= 0:
            item_text = self._model_combo.itemText(idx).strip()
            source = self._model_combo.itemData(idx, Qt.UserRole + 1)
            if source in ("cli", "api") and text == item_text:
                return source
        if text.startswith("[API] "):
            return "api"
        if text.startswith("[CLI] "):
            return "cli"
        return "cli"

    def _on_model_changed(self, _text: str):
        """记录会话级模型覆盖，不影响默认模型。"""
        if self._current_session_id:
            self._session_model_overrides[self._current_session_id] = self._get_selected_model()

    @staticmethod
    def _build_session_title(text: str) -> str:
        title = " ".join((text or "").splitlines()).strip()
        if not title:
            return "新对话"
        if len(title) > 34:
            return title[:34] + "..."
        return title

    def _remember_session_title(self, session_id: str, title: str):
        if not session_id:
            return
        normalized = self._build_session_title(title)
        if normalized and normalized != "新对话":
            self._session_titles[session_id] = normalized

    def _resolve_session_title(self, session_id: str, fallback: str = "会话") -> str:
        if not session_id:
            return fallback
        title = self._session_titles.get(session_id, "")
        if not title:
            title = self._session_panel.get_session_title(session_id)
            if title:
                title = self._build_session_title(title)
                self._session_titles[session_id] = title
        return title or fallback

    def _set_current_session_title(self, session_id: str, fallback: str = "会话"):
        self._title_label.setText(self._resolve_session_title(session_id, fallback=fallback))

    # ------------------------------------------------------------------
    # StatusMonitor 更新模型列表
    # ------------------------------------------------------------------
    def on_status_update(self, data: dict):
        models_ws = data.get("models_with_source", [])
        if models_ws:
            signature = [(m.get("name", ""), m.get("source", "")) for m in models_ws]
            if signature == self._last_models_with_source:
                return

            current = self._get_selected_model()
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            for m in models_ws:
                prefix = "CLI" if m["source"] == "cli" else "API"
                display_name = model_display_name(m["name"])
                self._model_combo.addItem(f"[{prefix}] {display_name}", m["name"])
                idx = self._model_combo.count() - 1
                self._model_combo.setItemData(idx, m["source"], Qt.UserRole + 1)
            for i in range(self._model_combo.count()):
                if self._model_combo.itemData(i) == current:
                    self._model_combo.setCurrentIndex(i)
                    break
            else:
                if current:
                    self._model_combo.setCurrentText(current)
            self._model_combo.blockSignals(False)
            self._last_models_with_source = signature

    # ------------------------------------------------------------------
    # 发送消息
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_session_id(text: str) -> str:
        """从 iflow 输出中提取 session id，兼容多种 key 形式。"""
        if not text:
            return ""
        import re
        patterns = [
            r'"session-id"\s*:\s*"([^"]+)"',
            r'"session_id"\s*:\s*"([^"]+)"',
            r'"sessionId"\s*:\s*"([^"]+)"',
            r"'session-id'\s*:\s*'([^']+)'",
            r"'session_id'\s*:\s*'([^']+)'",
            r"'sessionId'\s*:\s*'([^']+)'",
        ]
        for p in patterns:
            m = re.search(p, text, re.DOTALL)
            if m:
                return m.group(1).strip()
        return ""

    def _on_send_click(self):
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self._send(text)

    def _send(self, text: str):
        if self._worker is not None:
            if self._worker_detached:
                from PySide6.QtWidgets import QMessageBox as _QMB
                _QMB.information(
                    self, "提示",
                    "后台仍有对话正在进行，请等待完成或切回该会话后停止。",
                )
            return

        self._display.add_user_message(text)
        self._set_busy(True)
        self._streaming_text = ""
        self._response_started_at = time.perf_counter()
        self._stream_event_backlog = []
        self._stream_event_signatures.clear()
        self._stdout_streaming_active = False

        # 记录 worker 与 session 的关联
        self._worker_session_id = self._current_session_id
        self._worker_user_msg = text
        self._worker_detached = False
        self._last_stdout_time = 0.0

        if not self._current_session_id:
            self._title_label.setText(self._build_session_title(text))

        model = self._get_selected_model()
        model_source = self._get_selected_model_source()
        thinking = self._thinking_cb.isChecked()
        workspace = self._chat_workspace or CLIBridge.get_chat_workspace()

        if self._current_session_id:
            self._session_model_overrides[self._current_session_id] = model

        # 记录发送前的时间戳，用于发送后检测新创建的 session
        self._send_timestamp = time.time()
        # 已知的 session JSONL 偏移（用于增量检测工具调用）
        # 初始化为当前文件末尾偏移，避免显示之前对话中的工具调用
        self._tool_monitor_offset = self._get_current_session_file_size()
        self._tool_monitor_partial = ""
        self._tool_monitor_sid = self._current_session_id

        self._display.begin_streaming()

        self._worker = IFlowChatWorker(
            message=text,
            workspace=workspace,
            model=model,
            model_source=model_source,
            thinking=thinking,
            session_id=self._current_session_id,
            resume=bool(self._current_session_id),
        )
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        # 启动工具调用实时监控
        self._start_tool_monitor()

    def _remember_stream_event(self, event: dict) -> bool:
        """记录流式事件并去重，返回是否为新事件。"""
        try:
            signature = json.dumps(event, ensure_ascii=False, sort_keys=True)
        except Exception:
            signature = str(event)
        if signature in self._stream_event_signatures:
            return False
        self._stream_event_signatures.add(signature)
        self._stream_event_backlog.append(dict(event))
        return True

    def _replay_stream_backlog(self, bubble: ChatBubble | None):
        """将流式期间缓存的事件重放到当前气泡。"""
        if bubble is None:
            return
        for event in self._stream_event_backlog:
            bubble.add_body_event(event)

    def _finalize_response_timing(self):
        """输出本轮响应耗时（开始到结束）。"""
        started = self._response_started_at
        self._response_started_at = 0.0
        if started <= 0:
            return
        elapsed = max(0.0, time.perf_counter() - started)
        if not self._worker_detached:
            self._display.add_system_message(f"⏱ 本次输出耗时: {elapsed:.2f}s")

    def _on_chunk(self, chunk: str):
        import time as _time
        if chunk:
            self._stdout_streaming_active = True
            self._last_stdout_time = _time.time()
        self._streaming_text += chunk
        if not self._worker_detached:
            self._display.append_streaming(chunk)

    def _on_finished(self, result: str):
        self._stop_tool_monitor()

        if self._worker_detached:
            # Worker 在用户查看其他 session 时完成，仅清理状态
            detected_sid = self._extract_session_id(self._streaming_text)
            if not detected_sid:
                detected_sid = self._extract_session_id(result)
            if detected_sid:
                self._worker_session_id = detected_sid
            elif not self._worker_session_id:
                sid = self._detect_new_session_id()
                if sid:
                    self._worker_session_id = sid
            self._cleanup_worker()
            self._finalize_response_timing()
            self._worker_detached = False
            QTimer.singleShot(500, self._session_panel.refresh)
            return

        # 正常流程：当前正在查看 worker 所属的 session
        # 最后做一次工具调用检查（在结束流式之前，确保没有遗漏）
        self._poll_tool_calls()

        # 最终思考内容提取：从 session JSONL 中提取完整的思考内容
        self._extract_final_thinking()

        self._display.end_streaming()

        # 从输出中提取 session-id（优先流式缓存，回退 worker 的 result）。
        import re
        detected_sid = self._extract_session_id(self._streaming_text)
        if not detected_sid:
            detected_sid = self._extract_session_id(result)

        if detected_sid:
            self._current_session_id = detected_sid
            self._worker_session_id = detected_sid
            self._remember_session_title(detected_sid, self._worker_user_msg)
            self._set_current_session_title(detected_sid)
            # session-id 明确后再做一次最终思考提取，避免首次提取时 session 尚未落盘
            self._extract_final_thinking()

        # 清除 Execution Info 块后重新渲染最终文本
        clean_text = re.sub(
            r'\s*<Execution Info>.*?</Execution Info>\s*',
            '', self._streaming_text, flags=re.DOTALL,
        ).strip()
        if clean_text != self._streaming_text.strip():
            self._display.update_last_bot_text(clean_text)

        self._finalize_response_timing()

        self._cleanup_worker()

        # 如果是新对话且未从 Execution Info 获取到 session-id，通过文件系统检测
        if not self._current_session_id:
            sid = self._detect_new_session_id()
            if sid:
                self._current_session_id = sid
                self._worker_session_id = sid
                self._remember_session_title(sid, self._worker_user_msg)
                self._set_current_session_title(sid)
                self._extract_final_thinking()

        QTimer.singleShot(500, self._session_panel.refresh)

    def _detect_new_session_id(self) -> str:
        """发送首条消息后，检测 iflow CLI 新创建的 session ID 并返回（不修改状态）。"""
        sessions_dir = CLIBridge.get_chat_sessions_dir()
        if not sessions_dir.exists():
            return ""
        # 查找发送开始之后被修改的最新 session 文件
        send_ts = getattr(self, "_send_timestamp", 0)
        best_file: Path | None = None
        best_mtime: float = 0
        for sf in sessions_dir.glob("session-*.jsonl"):
            try:
                mt = sf.stat().st_mtime
                if mt >= send_ts and mt > best_mtime:
                    best_mtime = mt
                    best_file = sf
            except Exception:
                continue
        return best_file.stem if best_file else ""

    def _extract_final_thinking(self):
        """从 session JSONL 中提取完整的思考内容，确保思考块不遗漏。"""
        import json as _json

        bubble = self._display.get_streaming_bubble()
        if bubble is None:
            return

        sid = (
            self._worker_session_id
            or self._current_session_id
            or getattr(self, "_tool_monitor_sid", "")
        )
        if not sid:
            sid = self._detect_new_session_id()
        if not sid:
            # 尝试从累积文本中提取 <think> 块
            _, text_blocks = _extract_thinking_blocks(self._streaming_text)
            for tb in text_blocks:
                bubble.add_thinking(tb)
            return

        sessions_dir = CLIBridge.get_chat_sessions_dir()
        sf = sessions_dir / f"{sid}.jsonl"
        if not sf.exists():
            return

        try:
            with open(sf, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return

        # 从后往前找最后一个 assistant 消息
        for raw_line in reversed(lines):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = _json.loads(raw_line)
            except _json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue

            msg_obj = entry.get("message", {})
            raw_content = msg_obj.get("content", "")

            # Message-level thinking
            msg_thinking = _extract_thinking_from_message(msg_obj)
            if msg_thinking:
                bubble.add_thinking(msg_thinking)

            # Content part thinking
            if isinstance(raw_content, list):
                for part in raw_content:
                    if not isinstance(part, dict):
                        continue
                    thinking_text = _extract_thinking_from_content_part(part)
                    if thinking_text:
                        bubble.add_thinking(thinking_text)

            # Text-embedded <think> tags
            text_content = ""
            if isinstance(raw_content, str):
                text_content = raw_content
            elif isinstance(raw_content, list):
                text_content = "\n".join(
                    p.get("text", "") for p in raw_content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            if text_content:
                _, text_blocks = _extract_thinking_blocks(text_content)
                for tb in text_blocks:
                    bubble.add_thinking(tb)

            # 原始 JSONL 行兜底：直接抓取 reasoning/thinking 字段字符串
            import re as _re
            for key in (
                "reasoning_content", "reasoningContent",
                "thinking", "thinking_content", "thinkingContent", "reasoning",
            ):
                pattern = rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"'
                for m in _re.findall(pattern, raw_line):
                    try:
                        txt = __import__("json").loads(f'"{m}"')
                    except Exception:
                        txt = m
                    if isinstance(txt, str) and txt.strip():
                        bubble.add_thinking(txt.strip())

            break  # Only process the last assistant message

    # ------------------------------------------------------------------
    # 实时工具调用监控（轮询 session JSONL）
    # ------------------------------------------------------------------
    def _start_tool_monitor(self):
        """启动定时器，轮询 session JSONL 文件检测新的工具调用。"""
        if not hasattr(self, "_tool_timer"):
            self._tool_timer = QTimer(self)
            self._tool_timer.timeout.connect(self._poll_tool_calls)
        self._tool_timer.start(150)  # 每 150ms 轮询一次，更快的流式响应

    def _stop_tool_monitor(self):
        """停止工具轮询。"""
        if hasattr(self, "_tool_timer"):
            self._tool_timer.stop()
        self._tool_monitor_partial = ""

    def _poll_tool_calls(self):
        """增量读取 session JSONL，检测新的工具调用/结果并实时插入到流式气泡内。"""
        import json as _json
        import time as _time

        # 确定 session ID（可能在流式过程中才创建）
        sid = (
            getattr(self, "_tool_monitor_sid", "")
            or self._worker_session_id
            or self._current_session_id
        )
        if not sid:
            detected = self._detect_new_session_id()
            if detected:
                self._worker_session_id = detected
                if not self._worker_detached:
                    self._current_session_id = detected
                    self._remember_session_title(detected, self._worker_user_msg)
                    self._set_current_session_title(detected)
                self._tool_monitor_sid = detected
                sid = detected
                # 新 session 被检测到，刷新侧边栏以便用户能切换回来
                QTimer.singleShot(300, self._session_panel.refresh)
        if not sid:
            return

        sessions_dir = CLIBridge.get_chat_sessions_dir()
        sf = sessions_dir / f"{sid}.jsonl"
        if not sf.exists():
            return

        try:
            file_size = sf.stat().st_size
            old_offset = getattr(self, "_tool_monitor_offset", 0)
            if file_size < old_offset:
                old_offset = 0
                self._tool_monitor_partial = ""

            with open(sf, "rb") as f:
                f.seek(old_offset)
                chunk = f.read()
                new_offset = f.tell()
        except Exception:
            return

        if not chunk:
            return

        self._tool_monitor_offset = new_offset
        text = getattr(self, "_tool_monitor_partial", "") + chunk.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if text and not text.endswith("\n"):
            self._tool_monitor_partial = lines.pop() if lines else text
        else:
            self._tool_monitor_partial = ""

        if not lines:
            return

        # 如果 worker 已脱离（用户查看其他 session），仅累加文本不更新显示
        detached = self._worker_detached
        bubble = self._display.get_streaming_bubble() if not detached else None

        # 判断 stdout 是否已“停滞”（超过 2 秒未收到新数据），若它停滞则允许 JSONL 文本通过
        stdout_active = getattr(self, "_stdout_streaming_active", False)
        stdout_stale = (
            stdout_active
            and self._last_stdout_time > 0
            and (_time.time() - self._last_stdout_time) > 2.0
        )
        use_jsonl_text = not stdout_active or stdout_stale

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except _json.JSONDecodeError:
                continue

            msg_type = entry.get("type", "")
            msg_obj = entry.get("message", {})

            if msg_type == "assistant":
                raw_content = msg_obj.get("content", "")
                if use_jsonl_text:
                    text_parts: list[str] = []
                    if isinstance(raw_content, list):
                        for part in raw_content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                t = part.get("text", "")
                                if isinstance(t, str) and t:
                                    text_parts.append(t)
                    elif isinstance(raw_content, str) and raw_content:
                        text_parts.append(raw_content)
                    if text_parts:
                        delta_text = "".join(text_parts)
                        self._streaming_text += delta_text
                        if not detached:
                            self._display.append_streaming(delta_text)

                # Message-level thinking (e.g. reasoning_content in OpenAI format)
                msg_thinking = _extract_thinking_from_message(msg_obj)
                if msg_thinking:
                    event = {"type": "thinking", "content": msg_thinking}
                    if self._remember_stream_event(event) and bubble is not None:
                        bubble.add_body_event(event)

                if isinstance(raw_content, list):
                    for part in raw_content:
                        if not isinstance(part, dict):
                            continue
                        thinking_text = _extract_thinking_from_content_part(part)
                        if thinking_text:
                            event = {"type": "thinking", "content": thinking_text}
                            if self._remember_stream_event(event) and bubble is not None:
                                bubble.add_body_event(event)
                        if part.get("type") == "tool_use":
                            tool_name = part.get("name", "")
                            tool_input = part.get("input", {})
                            event = {
                                "type": "call",
                                "tool_name": tool_name,
                                "input": tool_input,
                            }
                            if self._remember_stream_event(event) and bubble is not None:
                                bubble.add_body_event(event)

            elif msg_type == "user":
                tool_result_info = entry.get("toolUseResult")
                if tool_result_info:
                    tool_name = tool_result_info.get("toolName", "")
                    status = tool_result_info.get("status", "")
                    result_text = ""
                    content_raw = msg_obj.get("content", "")
                    if isinstance(content_raw, list):
                        for part in content_raw:
                            if isinstance(part, dict) and part.get("type") == "tool_result":
                                c = part.get("content", {})
                                if isinstance(c, dict):
                                    resp = c.get("functionResponse", {}).get("response", {})
                                    result_text = resp.get("output", str(resp))
                                elif isinstance(c, str):
                                    result_text = c
                    event = {
                        "type": "result",
                        "tool_name": tool_name,
                        "status": status,
                        "content": result_text,
                    }
                    if self._remember_stream_event(event) and bubble is not None:
                        bubble.add_body_event(event)

        if not detached:
            self._display.scroll_to_bottom()

    def _get_current_session_file_size(self) -> int:
        """获取当前 session JSONL 文件大小（字节），用于初始化工具监控偏移。"""
        sid = self._current_session_id
        if not sid:
            return 0
        sessions_dir = CLIBridge.get_chat_sessions_dir()
        sf = sessions_dir / f"{sid}.jsonl"
        if not sf.exists():
            return 0
        try:
            return sf.stat().st_size
        except Exception:
            return 0

    def _on_error(self, err: str):
        self._stop_tool_monitor()
        if not self._worker_detached:
            self._display.end_streaming()
            self._display.add_system_message(f"❌ {err}")
            self._finalize_response_timing()
        else:
            self._finalize_response_timing()
        self._cleanup_worker()
        self._worker_detached = False

    def _cancel(self):
        if self._worker:
            self._worker.cancel()

    def _cleanup_worker(self):
        if self._worker:
            self._worker.quit()
            self._worker.wait(3000)
            self._worker.deleteLater()
            self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._send_btn.setVisible(not busy)
        self._cancel_btn.setVisible(busy)
        self._input.setEnabled(not busy)
        self._model_combo.setEnabled(not busy)

    # ------------------------------------------------------------------
    # 恢复会话
    # ------------------------------------------------------------------
    def _restore_session(self, session_id: str):
        self._restore_splitter_position()
        QTimer.singleShot(0, self._restore_splitter_position)
        # 如果有正在运行的 worker，检查是否应该重新附加
        if self._worker is not None:
            worker_sid = (
                self._worker_session_id
                or getattr(self, "_tool_monitor_sid", "")
            )
            if worker_sid and session_id == worker_sid:
                # 切回正在流式输出的会话：先恢复历史，再接回流式输出
                self._worker_detached = False
                self._current_session_id = session_id
                self._pending_live_reattach_session_id = session_id
                self._set_current_session_title(session_id)
                self._set_busy(True)
            else:
                # 切到别的会话，将当前 worker 标记为脱离
                self._worker_detached = True
                self._pending_live_reattach_session_id = ""
                self._set_busy(False)

        self._cleanup_session_loader()
        self._restore_render_items = []
        self._restore_render_index = 0
        self._restore_target_session_id = session_id

        self._display.clear_all()
        self._display.add_system_message(f"⏳ 正在加载会话 {session_id[-12:]}...")

        self._session_loader = SessionLoadWorker(session_id, self)
        self._session_loader.loaded.connect(self._on_session_loaded)
        self._session_loader.failed.connect(self._on_session_load_failed)
        self._session_loader.start()

    def _cleanup_session_loader(self):
        if self._session_loader:
            self._session_loader.quit()
            self._session_loader.wait(2000)
            self._session_loader.deleteLater()
            self._session_loader = None

    @staticmethod
    def _format_msg_timestamp(msg: dict) -> str:
        ts = msg.get("timestamp", "")
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%m-%d %H:%M")
        except Exception:
            return ""

    def _build_restore_render_items(self, messages: list[dict]) -> list[dict]:
        """将消息转换为可分批渲染的项目列表。"""
        render_items: list[dict] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            ts = self._format_msg_timestamp(msg)
            role = msg.get("role", "")

            if role == "user":
                render_items.append({
                    "kind": "user",
                    "text": msg.get("content", ""),
                    "timestamp": ts,
                })
                i += 1
                continue

            if role == "assistant":
                pending_body_events: list[dict] = []
                thinking_blocks: list[str] = []
                if msg.get("content_events"):
                    pending_body_events.extend(msg.get("content_events", []))
                    has_thinking_event = any(
                        isinstance(ev, dict) and ev.get("type") == "thinking"
                        for ev in pending_body_events
                    )
                    if not has_thinking_event:
                        thinking_blocks.extend(msg.get("thinking", []))
                else:
                    if msg.get("content"):
                        pending_body_events.append({
                            "type": "text",
                            "content": msg.get("content", ""),
                        })
                    for tc in msg.get("tool_calls", []):
                        pending_body_events.append({
                            "type": "call",
                            "tool_name": tc.get("tool_name", ""),
                            "input": tc.get("input", ""),
                        })
                    thinking_blocks = list(msg.get("thinking", []))
                model = msg.get("model", "")

                j = i + 1
                while j < len(messages):
                    nxt = messages[j]
                    nxt_role = nxt.get("role", "")
                    if nxt_role == "user":
                        break
                    if nxt_role == "tool_result":
                        pending_body_events.append({
                            "type": "result",
                            "tool_name": nxt.get("tool_name", ""),
                            "status": nxt.get("status", ""),
                            "content": nxt.get("content", ""),
                        })
                        j += 1
                        continue
                    if nxt_role == "assistant":
                        if nxt.get("content_events"):
                            pending_body_events.extend(nxt.get("content_events", []))
                        else:
                            if nxt.get("content"):
                                pending_body_events.append({
                                    "type": "text",
                                    "content": nxt.get("content", ""),
                                })
                            for tc in nxt.get("tool_calls", []):
                                pending_body_events.append({
                                    "type": "call",
                                    "tool_name": tc.get("tool_name", ""),
                                    "input": tc.get("input", ""),
                                })
                            thinking_blocks.extend(nxt.get("thinking", []))
                        model = model or nxt.get("model", "")
                        nxt_ts = self._format_msg_timestamp(nxt)
                        if nxt_ts:
                            ts = nxt_ts
                    j += 1

                render_items.append({
                    "kind": "assistant",
                    "model": model,
                    "timestamp": ts,
                    "body_events": pending_body_events if pending_body_events else None,
                    "thinking_blocks": thinking_blocks if thinking_blocks else None,
                })
                i = j
                continue

            if role == "tool_result":
                render_items.append({
                    "kind": "assistant",
                    "model": "",
                    "timestamp": ts,
                    "body_events": [{
                        "type": "result",
                        "tool_name": msg.get("tool_name", ""),
                        "status": msg.get("status", ""),
                        "content": msg.get("content", ""),
                    }],
                    "thinking_blocks": None,
                })
                i += 1
                continue

            i += 1

        return render_items

    def _render_restore_batch(self):
        if self._restore_render_index >= len(self._restore_render_items):
            sid = self._restore_target_session_id
            if sid:
                self._set_current_session_title(sid)
                selected_model = self._session_model_overrides.get(sid, self._default_model)
                self._populate_model_combo(selected_model)
            # 历史恢复结束后仅做一次全量宽度与滚动更新
            self._display._update_bubble_widths()
            worker_sid = self._worker_session_id or getattr(self, "_tool_monitor_sid", "")
            is_live_session = bool(
                self._worker is not None
                and not self._worker_detached
                and sid
                and worker_sid == sid
            )
            if (
                is_live_session
                and sid
                and self._pending_live_reattach_session_id == sid
            ):
                self._display.begin_streaming()
                if self._streaming_text:
                    self._display.set_streaming_text(self._streaming_text)
                self._replay_stream_backlog(self._display.get_streaming_bubble())
                self._set_busy(True)
                self._pending_live_reattach_session_id = ""
            else:
                self._display.add_system_message("💡 继续发送消息将在此会话基础上对话")
            self._display.scroll_to_bottom()
            return

        # 时间片渲染：优先保证 UI 响应，不一次性塞太多组件
        max_batch_count = 28
        max_batch_ms = 12.0
        start = time.perf_counter()

        end = self._restore_render_index
        hard_end = min(self._restore_render_index + max_batch_count, len(self._restore_render_items))
        self._display.begin_bulk_insert()
        for idx in range(self._restore_render_index, hard_end):
            item = self._restore_render_items[idx]
            kind = item.get("kind", "")
            if kind == "user":
                self._display.add_user_message(item.get("text", ""), item.get("timestamp", ""))
            elif kind == "assistant":
                self._display.add_bot_message(
                    "",
                    model=item.get("model", ""),
                    timestamp=item.get("timestamp", ""),
                    body_events=item.get("body_events", None),
                    thinking_blocks=item.get("thinking_blocks", None),
                )
            end = idx + 1
            if (end - self._restore_render_index) >= 8:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if elapsed_ms >= max_batch_ms:
                    break

        # 每批只更新新增气泡宽度，不全量滚动
        self._display.end_bulk_insert(update_widths=False, auto_scroll=False)

        self._restore_render_index = end
        QTimer.singleShot(1, self._render_restore_batch)

    def _on_session_loaded(self, session_id: str, messages: list):
        self._cleanup_session_loader()
        if session_id != self._restore_target_session_id:
            return
        if not messages:
            self._display.clear_all()
            self._display.add_system_message("⚠️ 该会话为空或无法读取")
            return

        self._current_session_id = session_id
        for msg in messages:
            if msg.get("role") == "user" and msg.get("content"):
                self._remember_session_title(session_id, msg.get("content", ""))
                break
        self._display.clear_all()
        self._display.add_system_message(f"🔄 已恢复会话 {session_id[-12:]}")
        self._restore_render_items = self._build_restore_render_items(messages)
        self._restore_render_index = 0
        self._render_restore_batch()
        self._restore_splitter_position()
        QTimer.singleShot(0, self._restore_splitter_position)

    def _on_session_load_failed(self, session_id: str, err: str):
        self._cleanup_session_loader()
        if session_id != self._restore_target_session_id:
            return
        self._display.clear_all()
        self._display.add_system_message(f"❌ 会话加载失败: {err}")

    def _new_chat(self):
        if self._worker is not None:
            self._worker_detached = True
            self._set_busy(False)
        self._current_session_id = ""
        self._display.clear_all()
        self._title_label.setText("新对话")
        # 每次新建会话时从设置中读取最新默认模型
        self._default_model = IFlowSettings.get_model() or "glm-5"
        self._populate_model_combo(self._default_model)
        self._display.add_system_message("👋 新对话已创建，开始聊天吧！")
        self._restore_splitter_position()
        QTimer.singleShot(0, self._restore_splitter_position)

    def _on_session_deleted(self, session_id: str):
        """会话被删除后，如果当前正在显示该会话则重置。"""
        self._session_titles.pop(session_id, None)
        if self._current_session_id == session_id:
            self._new_chat()
