"""资源模块。"""

from __future__ import annotations

from pathlib import Path


def get_app_icon_path() -> Path:
	"""返回应用图标路径。"""
	base = Path(__file__).resolve().parent
	ico = base / "app_icon.ico"
	if ico.exists():
		return ico
	return base / "app_icon.xpm"
