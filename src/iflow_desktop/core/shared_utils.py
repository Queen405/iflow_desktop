"""共享工具函数（子进程参数、解码、模型展示、思考块提取）。"""

from __future__ import annotations

import platform
import re
import subprocess


def get_selected_model_from_combo(combo) -> str:
    """通用：从 QComboBox 获取当前选中的模型名称（去除来源前缀）。"""
    text = combo.currentText().strip()
    idx = combo.currentIndex()
    data = combo.currentData()
    from iflow_desktop.core.cli_bridge import CLIBridge
    if data and idx >= 0:
        item_text = combo.itemText(idx).strip()
        if text == item_text:
            return CLIBridge.normalize_model_name(data)
    if data and not text:
        return CLIBridge.normalize_model_name(data)
    for prefix in ("[CLI] ", "[API] "):
        if text.startswith(prefix):
            return CLIBridge.normalize_model_name(text[len(prefix):])
    return CLIBridge.normalize_model_name(text)


def subprocess_kwargs(capture: bool = True, cwd: str | None = None) -> dict:
    """构建跨平台 subprocess 参数。"""
    kwargs: dict = {"cwd": cwd}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def decode_bytes(raw: bytes) -> str:
    """安全解码 bytes -> str，优先 utf-8，回退 gbk，最后 replace。"""
    for enc in ("utf-8", "utf-8-sig", "gb18030", "cp936", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def model_display_name(model_name: str) -> str:
    """模型显示名（保留底层模型 ID）。"""
    alias_map = {
        "glm-4.7": "GLM-4.7",
        "glm-5": "GLM-5",
        "kimi-k2.5": "Kimi2.5",
        "minimax-m2.5": "MiniMax-M2.5",
    }
    return alias_map.get(model_name, model_name)


def extract_thinking_blocks(text: str) -> tuple[str, list[str]]:
    """提取 <think>/<thinking>/<reasoning>/<reasoning_content> 块，返回净文本与思考块列表。"""
    blocks: list[str] = []

    def _collect(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if content:
            blocks.append(content)
        return ""

    clean = re.sub(
        r"<(?:think|thinking|reasoning|reasoning_content)>(.*?)</(?:think|thinking|reasoning|reasoning_content)>",
        _collect,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Also handle <|thinking|>...</|thinking|> format used by some models
    clean = re.sub(
        r"<\|(?:thinking|reasoning)\|>(.*?)<\|/(?:thinking|reasoning)\|>",
        _collect,
        clean,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return clean.strip(), blocks


def extract_thinking_from_message(msg_obj: dict) -> str:
    """从 assistant 消息对象中提取消息级别的思考/推理文本（如 reasoning_content 字段）。"""
    if not isinstance(msg_obj, dict):
        return ""
    for key in (
        "reasoning_content", "reasoningContent",
        "thinking", "thinking_content", "thinkingContent",
        "reasoning", "reasoning_text", "thought", "thoughts",
    ):
        val = msg_obj.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list):
            texts = []
            for item in val:
                if isinstance(item, str) and item.strip():
                    texts.append(item.strip())
                elif isinstance(item, dict):
                    t = item.get("text", "")
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
            joined = "\n".join(texts).strip()
            if joined:
                return joined

    # 递归扫描：尽可能从嵌套结构中抓取“思考/推理”字段
    def _walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                key = str(k).lower()
                if any(x in key for x in ("thinking", "reasoning", "thought")):
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                    if isinstance(v, dict):
                        t = v.get("text", "") or v.get("content", "")
                        if isinstance(t, str) and t.strip():
                            return t.strip()
                nested = _walk(v)
                if nested:
                    return nested
        elif isinstance(value, list):
            for item in value:
                nested = _walk(item)
                if nested:
                    return nested
        return ""

    return _walk(msg_obj)


def extract_thinking_from_content_part(part: dict) -> str:
    """从 assistant content part 中提取思考/推理文本。"""
    if not isinstance(part, dict):
        return ""

    p_type = str(part.get("type", "")).lower()
    candidate_keys = [
        "thinking", "reasoning", "reasoning_content", "thinking_content",
        "text", "content", "output", "thought", "thoughts",
    ]

    def _pick_text(value) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            texts: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    texts.append(item.strip())
                elif isinstance(item, dict):
                    t = item.get("text", "")
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
            return "\n".join(texts).strip()
        if isinstance(value, dict):
            for key in ("text", "content", "value", "reasoning", "thinking"):
                t = value.get(key, "")
                if isinstance(t, str) and t.strip():
                    return t.strip()
        return ""

    likely_thinking_type = p_type in {
        "thinking", "reasoning", "reasoning_content", "thinking_content", "thought", "thoughts",
    }
    if likely_thinking_type:
        for key in candidate_keys:
            text = _pick_text(part.get(key, ""))
            if text:
                return text

    for key in ("reasoning", "reasoning_content", "thinking", "thinking_content"):
        text = _pick_text(part.get(key, ""))
        if text:
            return text

    return ""
