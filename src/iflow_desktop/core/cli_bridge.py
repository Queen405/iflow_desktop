"""CLI Bridge - 封装对 iflow-bot / iflow CLI 命令的调用。"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import importlib.util
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Signal, QThread

from iflow_desktop.core.shared_utils import (
    decode_bytes as _decode,
    extract_thinking_from_content_part as _extract_thinking_from_content_part,
    extract_thinking_from_message as _extract_thinking_from_message,
    subprocess_kwargs as _subprocess_kwargs,
)


def _normalize_model_name(name: str) -> str:
    """规范化常见模型别名，兼容历史配置。"""
    if not name:
        return ""
    raw = str(name).strip()
    key = raw.lower()
    alias_map = {
        "glm5": "glm-5",
        "glm-5": "glm-5",
        "glm4.7": "glm-4.7",
        "glm-4.7": "glm-4.7",
        "kimi2.5": "kimi-k2.5",
        "kimi-k2.5": "kimi-k2.5",
        "minimaxm2.5": "minimax-m2.5",
        "minimax-m2.5": "minimax-m2.5",
    }
    return alias_map.get(key, raw)


class IFlowSettings:
    """管理 ~/.iflow/settings.json - iflow CLI 核心配置。"""

    @staticmethod
    def get_dir() -> Path:
        return Path.home() / ".iflow"

    @staticmethod
    def get_path() -> Path:
        return IFlowSettings.get_dir() / "settings.json"

    @staticmethod
    def load() -> dict:
        path = IFlowSettings.get_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def save(data: dict) -> None:
        path = IFlowSettings.get_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # -- Model --
    @staticmethod
    def get_model() -> str:
        return _normalize_model_name(IFlowSettings.load().get("modelName", ""))

    @staticmethod
    def set_model(name: str) -> None:
        data = IFlowSettings.load()
        data["modelName"] = _normalize_model_name(name)
        IFlowSettings.save(data)

    # -- Thinking --
    @staticmethod
    def get_thinking() -> bool:
        return IFlowSettings.load().get("thinking", False)

    @staticmethod
    def set_thinking(enabled: bool) -> None:
        data = IFlowSettings.load()
        data["thinking"] = enabled
        IFlowSettings.save(data)

    # -- Chat Workspace --
    @staticmethod
    def get_chat_workspace() -> str:
        data = IFlowSettings.load()
        ws = str(data.get("chatWorkspace", "")).strip()
        if ws:
            return str(Path(ws).expanduser())
        return ""

    @staticmethod
    def set_chat_workspace(workspace: str) -> None:
        data = IFlowSettings.load()
        ws = str(workspace or "").strip()
        if ws:
            data["chatWorkspace"] = str(Path(ws).expanduser())
        else:
            data.pop("chatWorkspace", None)
        IFlowSettings.save(data)

    # -- MCP Servers --
    @staticmethod
    def get_mcp_servers() -> dict:
        """获取 MCP 服务器配置 {name: {command, args, ...}}。"""
        return IFlowSettings.load().get("mcpServers", {})

    @staticmethod
    def set_mcp_servers(servers: dict) -> None:
        data = IFlowSettings.load()
        data["mcpServers"] = servers
        IFlowSettings.save(data)

    @staticmethod
    def add_mcp_server(name: str, config: dict) -> None:
        servers = IFlowSettings.get_mcp_servers()
        servers[name] = config
        IFlowSettings.set_mcp_servers(servers)

    @staticmethod
    def remove_mcp_server(name: str) -> None:
        servers = IFlowSettings.get_mcp_servers()
        servers.pop(name, None)
        IFlowSettings.set_mcp_servers(servers)

    # -- Custom Instructions --
    @staticmethod
    def get_custom_instructions() -> str:
        return IFlowSettings.load().get("customInstructions", "")

    @staticmethod
    def set_custom_instructions(text: str) -> None:
        data = IFlowSettings.load()
        data["customInstructions"] = text
        IFlowSettings.save(data)

    # -- Use API Models --
    @staticmethod
    def get_use_api_models() -> bool:
        """是否使用 API Key 管理的在线模型列表，默认 False（使用 CLI bundle 内置模型）。"""
        return IFlowSettings.load().get("useApiModels", False)

    @staticmethod
    def set_use_api_models(enabled: bool) -> None:
        data = IFlowSettings.load()
        data["useApiModels"] = enabled
        IFlowSettings.save(data)


class CLIBridge:
    """封装 iflow CLI / iflow-bot 命令。"""

    _models_cache: list[str] = []
    _models_cache_time: float = 0
    _models_with_source_cache: list[dict] = []
    _models_with_source_cache_time: float = 0
    _CLI_MODELS: list[str] = [
        "glm-4.7",
        "glm-5",
        "kimi-k2.5",
        "minimax-m2.5",
    ]
    _session_brief_cache: dict[str, dict] = {}
    _session_list_cache: dict[str, dict] = {}
    _session_messages_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # iflow CLI 路径
    # ------------------------------------------------------------------
    @staticmethod
    def _get_iflow_cmd() -> str:
        """获取 iflow 命令路径（带多候选回退，避免 Windows 误判未安装）。"""
        cfg = CLIBridge.load_bot_config()
        configured = str(cfg.get("driver", {}).get("iflow_path", "")).strip()

        candidates: list[str] = []
        if configured:
            candidates.append(configured)
            p = Path(configured).expanduser()
            suffix = p.suffix.lower()
            if suffix == ".ps1":
                candidates.append(str(p.with_suffix(".cmd")))
                candidates.append(str(p.with_suffix(".exe")))
            elif not suffix:
                candidates.append(configured + ".cmd")
                candidates.append(configured + ".exe")

        candidates.extend(["iflow", "iflow.cmd", "iflow.exe"])

        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                npm_bin = Path(appdata) / "npm"
                candidates.extend([
                    str(npm_bin / "iflow.cmd"),
                    str(npm_bin / "iflow.exe"),
                    str(npm_bin / "iflow"),
                ])

        seen: set[str] = set()
        for raw in candidates:
            c = str(raw or "").strip()
            if not c or c in seen:
                continue
            seen.add(c)

            resolved = shutil.which(c)
            if resolved:
                return resolved

            p = Path(c).expanduser()
            if p.exists():
                return str(p)

        return configured or "iflow"

    # ------------------------------------------------------------------
    # iflow-bot 配置 (bot 服务专用)
    # ------------------------------------------------------------------
    @staticmethod
    def get_bot_config_dir() -> Path:
        return Path.home() / ".iflow-bot"

    @staticmethod
    def get_bot_config_path() -> Path:
        return CLIBridge.get_bot_config_dir() / "config.json"

    @staticmethod
    def get_pid_file() -> Path:
        return CLIBridge.get_bot_config_dir() / "gateway.pid"

    @staticmethod
    def get_log_file() -> Path:
        return CLIBridge.get_bot_config_dir() / "gateway.log"

    @staticmethod
    def get_iflow_log_dir() -> Path:
        return IFlowSettings.get_dir() / "log"

    @staticmethod
    def get_latest_iflow_log_file() -> Path | None:
        log_dir = CLIBridge.get_iflow_log_dir()
        if not log_dir.exists():
            return None
        files = sorted(
            log_dir.glob("*.log"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        return files[0] if files else None

    @staticmethod
    def get_bot_data_dir() -> Path:
        d = CLIBridge.get_bot_config_dir() / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # Keep backward compatibility aliases
    @staticmethod
    def get_iflow_dir() -> Path:
        return IFlowSettings.get_dir()

    # ------------------------------------------------------------------
    # iflow-bot 配置读写
    # ------------------------------------------------------------------
    @staticmethod
    def load_bot_config() -> dict:
        path = CLIBridge.get_bot_config_path()
        if path.exists():
            for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "cp936"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
        return {}

    @staticmethod
    def save_bot_config(data: dict) -> None:
        path = CLIBridge.get_bot_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # iflow 检查
    # ------------------------------------------------------------------
    @staticmethod
    def check_iflow_installed() -> bool:
        try:
            iflow_cmd = CLIBridge._get_iflow_cmd()
            kw = _subprocess_kwargs(capture=True)
            r = subprocess.run([iflow_cmd, "--version"], timeout=10, **kw)
            return r.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_iflow_version() -> str:
        try:
            iflow_cmd = CLIBridge._get_iflow_cmd()
            kw = _subprocess_kwargs(capture=True)
            r = subprocess.run([iflow_cmd, "--version"], timeout=10, **kw)
            if r.returncode == 0:
                return _decode(r.stdout).strip()
        except Exception:
            pass
        return "未安装"

    @staticmethod
    def check_iflow_auth() -> dict:
        """检查 iflow 认证状态，返回 {logged_in, auth_type, has_api_key}。"""
        settings = IFlowSettings.load()
        api_key = settings.get("apiKey", "")
        auth_type = settings.get("selectedAuthType", "")
        has_projects = CLIBridge.check_iflow_logged_in()
        return {
            "logged_in": bool(api_key) or has_projects,
            "auth_type": auth_type,
            "has_api_key": bool(api_key),
        }

    @staticmethod
    def _find_local_iflow_bot_project() -> Path | None:
        """查找本地 iflow_bot 项目目录。"""
        config = CLIBridge.load_bot_config()
        configured = config.get("driver", {}).get("iflow_bot_project", "")

        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured).expanduser())

        env_path = os.environ.get("IFLOW_BOT_PROJECT", "")
        if env_path:
            candidates.append(Path(env_path).expanduser())

        # 约定目录：iflow-desktop 与 iflow_bot 同级
        try:
            desktop_root = Path(__file__).resolve().parents[3]
            candidates.append(desktop_root.parent / "iflow_bot")
        except Exception:
            pass

        for candidate in candidates:
            try:
                root = candidate.resolve()
            except Exception:
                continue
            if (root / "pyproject.toml").exists() and (root / "src" / "iflow_bot" / "__init__.py").exists():
                return root
        return None

    @staticmethod
    def _get_iflow_bot_execution() -> tuple[list[str], str | None, dict | None] | None:
        """检测 iflow-bot 可执行入口。返回 (命令前缀, cwd, env)。"""
        import sys

        if importlib.util.find_spec("iflow_bot") is not None:
            return [sys.executable, "-m", "iflow_bot"], None, None

        local_project = CLIBridge._find_local_iflow_bot_project()
        if local_project is not None:
            if platform.system() == "Windows":
                local_python = local_project / ".venv" / "Scripts" / "python.exe"
            else:
                local_python = local_project / ".venv" / "bin" / "python"

            py_cmd = str(local_python if local_python.exists() else Path(sys.executable))

            env = os.environ.copy()
            src_path = str(local_project / "src")
            old_python_path = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{src_path}{os.pathsep}{old_python_path}" if old_python_path else src_path

            return [py_cmd, "-m", "iflow_bot"], str(local_project), env

        try:
            kw = _subprocess_kwargs(capture=True)
            r = subprocess.run(["iflow-bot", "--version"], timeout=5, **kw)
            if r.returncode == 0:
                return ["iflow-bot"], None, None
        except Exception:
            pass
        return None

    @staticmethod
    def check_iflow_logged_in() -> bool:
        """检查是否已登录（有 API key 或有项目文件）。"""
        settings = IFlowSettings.load()
        if settings.get("apiKey"):
            return True
        iflow_dir = IFlowSettings.get_dir()
        if not iflow_dir.exists():
            return False
        projects = iflow_dir / "projects"
        if projects.exists():
            try:
                if any(projects.iterdir()):
                    return True
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------
    # iflow 模型列表
    # ------------------------------------------------------------------
    @staticmethod
    def normalize_model_name(name: str) -> str:
        """规范化模型名称（兼容历史别名）。"""
        return _normalize_model_name(name)

    @staticmethod
    def get_iflow_models() -> list[str]:
        """获取 iflow 可用模型列表 (带缓存)。
        根据 useApiModels 设置决定模型源：
        - False (默认): 从 CLI bundle 解析内置模型列表
        - True: 通过 API Key 从 /v1/models 接口获取"""
        now = time.time()
        if CLIBridge._models_cache and now - CLIBridge._models_cache_time < 600:
            return list(CLIBridge._models_cache)

        use_api = IFlowSettings.get_use_api_models()

        if use_api:
            # 从 API 获取模型列表
            api_models = CLIBridge.fetch_models_from_api()
            if api_models:
                current = CLIBridge.get_iflow_current_model()
                if current and current not in api_models:
                    api_models.insert(0, current)
                CLIBridge._models_cache = api_models
                CLIBridge._models_cache_time = now
                return list(api_models)

        # 从 iflow CLI bundle 解析硬编码模型列表（严格 CLI 源）
        cli_models = CLIBridge._parse_cli_bundle_models()
        if cli_models:
            CLIBridge._models_cache = cli_models
            CLIBridge._models_cache_time = now
            return list(cli_models)

        # 回退到本地配置
        models = CLIBridge._get_models_from_local()
        CLIBridge._models_cache = models
        CLIBridge._models_cache_time = now
        return list(models)

    @staticmethod
    def invalidate_models_cache() -> None:
        """清空模型缓存，下次获取时重新加载。"""
        CLIBridge._models_cache = []
        CLIBridge._models_cache_time = 0
        CLIBridge._models_with_source_cache = []
        CLIBridge._models_with_source_cache_time = 0

    @staticmethod
    def invalidate_session_caches() -> None:
        """清空会话相关缓存，工作区切换时调用。"""
        CLIBridge._session_brief_cache.clear()
        CLIBridge._session_list_cache.clear()
        CLIBridge._session_messages_cache.clear()

    @staticmethod
    def get_iflow_models_with_source() -> list[dict]:
        """获取模型列表(带来源标签): [{name: str, source: 'cli'|'api'}]。"""
        now = time.time()
        if (
            CLIBridge._models_with_source_cache
            and now - CLIBridge._models_with_source_cache_time < 600
        ):
            return [dict(item) for item in CLIBridge._models_with_source_cache]

        result: list[dict] = []
        seen: set[str] = set()

        cli_models_list = CLIBridge._parse_cli_bundle_models()
        if not cli_models_list:
            cli_models_list = CLIBridge._get_models_from_local()

        api_models_list: list[str] = []
        if IFlowSettings.get_use_api_models():
            api_models_list = CLIBridge.fetch_models_from_api()
        api_models_set = set(api_models_list)

        # 优先显示 CLI（按 CLI 官方列表顺序）
        for model_name in cli_models_list:
            if model_name and model_name not in seen:
                seen.add(model_name)
                result.append({"name": model_name, "source": "cli"})

        # 追加 API（仅 URL 返回，且不覆盖 CLI）
        for model_name in api_models_list:
            if model_name and model_name not in seen:
                seen.add(model_name)
                result.append({"name": model_name, "source": "api"})

        current = IFlowSettings.get_model()
        if current and current not in seen:
            if current in api_models_set:
                result.insert(0, {"name": current, "source": "api"})
            elif current in CLIBridge._CLI_MODELS:
                result.insert(0, {"name": current, "source": "cli"})

        if not result:
            result = [{"name": "glm-5", "source": "cli"}]
        CLIBridge._models_with_source_cache = [dict(item) for item in result]
        CLIBridge._models_with_source_cache_time = now
        return result

    @staticmethod
    def fetch_models_from_api() -> list[str]:
        """通过 iflow API Key 从 /v1/models 接口获取可用模型列表。"""
        import urllib.request
        import urllib.error

        settings = IFlowSettings.load()
        api_key = settings.get("apiKey", "")
        base_url = settings.get("baseUrl", "https://apis.iflow.cn/v1")

        if not api_key:
            return []

        url = f"{base_url.rstrip('/')}/models"
        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            models: list[str] = []
            seen: set[str] = set()
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if model_id and model_id not in seen:
                    seen.add(model_id)
                    models.append(model_id)
            models.sort()
            return models
        except Exception:
            return []

    @staticmethod
    def _find_iflow_bundle_dirs() -> list[Path]:
        """查找 iflow CLI bundle 目录。"""
        dirs: list[Path] = []

        def _append_if_exists(p: Path) -> None:
            try:
                resolved = p.resolve()
            except Exception:
                resolved = p
            if resolved.exists() and resolved.is_dir() and resolved not in dirs:
                dirs.append(resolved)

        # 1) 标准 npm 全局安装路径
        for bundle_dir in [
            Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@iflow-ai" / "iflow-cli" / "bundle",
            Path("/usr/local/lib/node_modules/@iflow-ai/iflow-cli/bundle"),
            Path("/usr/lib/node_modules/@iflow-ai/iflow-cli/bundle"),
        ]:
            _append_if_exists(bundle_dir)

        # 2) 从 iflow-bot 配置中的 iflow_path 推断
        cfg = CLIBridge.load_bot_config()
        iflow_path = cfg.get("driver", {}).get("iflow_path", "")
        if iflow_path:
            try:
                p = Path(iflow_path).expanduser().resolve()
                candidate_dirs = [
                    p.parent / "node_modules" / "@iflow-ai" / "iflow-cli" / "bundle",
                    p.parent.parent / "node_modules" / "@iflow-ai" / "iflow-cli" / "bundle",
                ]
                for candidate_dir in candidate_dirs:
                    _append_if_exists(candidate_dir)
            except Exception:
                pass

        # 3) 通过 where/which 定位 iflow 执行文件再推断
        try:
            if platform.system() == "Windows":
                kw = _subprocess_kwargs(capture=True)
                r = subprocess.run(["where", "iflow.cmd"], timeout=5, **kw)
                if r.returncode != 0:
                    r = subprocess.run(["where", "iflow"], timeout=5, **kw)
            else:
                kw = _subprocess_kwargs(capture=True)
                r = subprocess.run(["which", "iflow"], timeout=5, **kw)

            if r.returncode == 0:
                for raw_line in _decode(r.stdout).splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    p = Path(line).resolve()
                    candidate_dirs = [
                        p.parent / "node_modules" / "@iflow-ai" / "iflow-cli" / "bundle",
                        p.parent.parent / "node_modules" / "@iflow-ai" / "iflow-cli" / "bundle",
                    ]
                    for candidate_dir in candidate_dirs:
                        _append_if_exists(candidate_dir)
        except Exception:
            pass

        return dirs

    @staticmethod
    def _collect_iflow_bundle_js_files() -> list[Path]:
        """收集 iflow CLI bundle 下的 JS 文件（优先 iflow.js、entry.js）。"""
        files: list[Path] = []
        for bundle_dir in CLIBridge._find_iflow_bundle_dirs():
            preferred = [bundle_dir / "iflow.js", bundle_dir / "entry.js"]
            for p in preferred:
                if p.exists() and p.is_file() and p not in files:
                    files.append(p)
            for p in sorted(bundle_dir.glob("*.js")):
                if p.exists() and p.is_file() and p not in files:
                    files.append(p)
        return files

    @staticmethod
    def _is_valid_cli_model_name(model_name: str) -> bool:
        """判断字符串是否像 iflow CLI 模型名。"""
        import re

        if not model_name:
            return False
        if len(model_name) < 4 or len(model_name) > 120:
            return False
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", model_name):
            return False

        lower = model_name.lower()
        if lower.startswith("ide-"):
            return False

        # 过滤明显非模型字段
        blocked_prefixes = (
            "aws-",
            "utf-",
            "http-",
            "https-",
            "tree-sitter-",
            "xterm-",
            "node-",
            "pdfjs-",
            "home-",
            "root-",
            "global-",
            "initial-",
        )
        if lower.startswith(blocked_prefixes):
            return False

        allowed_prefixes = (
            "glm-",
            "gpt-",
            "claude",
            "deepseek",
            "qwen",
            "kimi",
            "minimax",
            "gemini",
            "moonshot",
            "doubao",
            "iflow-",
            "o1",
            "o3",
            "o4",
        )
        return lower.startswith(allowed_prefixes)

    @staticmethod
    def _parse_cli_bundle_models() -> list[str]:
        """从 iflow CLI 的 JS bundle 中解析硬编码的模型列表。"""
        import re

        js_files = CLIBridge._collect_iflow_bundle_js_files()
        if not js_files:
            return list(CLIBridge._CLI_MODELS)

        try:
            models: list[str] = []
            seen: set[str] = set()

            # 严格提取 CLI 官方 NAe 列表，避免混入非 CLI 模型
            nae_pattern = r"NAe\s*=\s*\[(.*?)\](?=\s*[),;])"
            value_pattern = r"value\s*:\s*['\"]([^'\"]+)['\"]"

            for js_file in js_files:
                content = js_file.read_text(encoding="utf-8", errors="replace")
                for arr_content in re.findall(nae_pattern, content, flags=re.DOTALL):
                    for model_name in re.findall(value_pattern, arr_content):
                        if not CLIBridge._is_valid_cli_model_name(model_name):
                            continue
                        if model_name in seen:
                            continue
                        seen.add(model_name)
                        models.append(model_name)

            if models:
                parsed_set = set(models)
                filtered = [m for m in CLIBridge._CLI_MODELS if m in parsed_set]
                return filtered or list(CLIBridge._CLI_MODELS)
            return list(CLIBridge._CLI_MODELS)
        except Exception:
            return list(CLIBridge._CLI_MODELS)

    @staticmethod
    def _get_models_from_local() -> list[str]:
        """从本地配置读取模型列表 (无网络请求)。"""
        known: list[str] = []
        current = IFlowSettings.get_model()
        if current:
            known.append(current)
        for model_name in CLIBridge._CLI_MODELS:
            if model_name not in known:
                known.append(model_name)
        return known

    @staticmethod
    def get_iflow_current_model() -> str:
        """获取当前模型（从 iflow settings.json）。"""
        return IFlowSettings.get_model() or "glm-5"

    # ------------------------------------------------------------------
    # iflow 资源 (MCP, Skills, Agents)
    # ------------------------------------------------------------------
    @staticmethod
    def get_mcp_servers_list() -> list[dict]:
        """获取已配置的 MCP 服务器列表（列表格式）。"""
        servers = IFlowSettings.get_mcp_servers()
        result = []
        for name, cfg in servers.items():
            result.append({
                "name": name,
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "description": cfg.get("description", ""),
                "disabled": cfg.get("disabled", False),
            })
        return result

    @staticmethod
    def get_skills() -> list[dict]:
        """获取已安装的 skills。"""
        skills_dir = IFlowSettings.get_dir() / "skills"
        if not skills_dir.exists():
            return []
        result = []
        try:
            for d in skills_dir.iterdir():
                if d.is_dir():
                    result.append({"name": d.name, "path": str(d)})
        except Exception:
            pass
        return result

    @staticmethod
    def get_agents() -> list[dict]:
        """获取已配置的 agents。"""
        agents_dir = IFlowSettings.get_dir() / "agents"
        if not agents_dir.exists():
            return []
        result = []
        try:
            for f in agents_dir.iterdir():
                if f.is_file() and f.suffix == ".md":
                    result.append({"name": f.stem, "path": str(f)})
        except Exception:
            pass
        return result

    @staticmethod
    def get_commands() -> list[dict]:
        """获取已安装的 commands。"""
        cmds_dir = IFlowSettings.get_dir() / "commands"
        if not cmds_dir.exists():
            return []
        result = []
        try:
            for f in cmds_dir.iterdir():
                if f.is_file():
                    result.append({"name": f.stem, "path": str(f)})
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # 在线仓库列表 (MCP / Skills / Agents / Commands)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_json_from_output(text: str) -> dict | list | None:
        """从 CLI 输出中尽力解析 JSON。"""
        raw = (text or "").strip()
        if not raw:
            return None

        try:
            return json.loads(raw)
        except Exception:
            pass

        decoder = json.JSONDecoder()
        for i, ch in enumerate(raw):
            if ch not in "[{":
                continue
            try:
                obj, _ = decoder.raw_decode(raw[i:])
                return obj
            except Exception:
                continue
        return None

    @staticmethod
    def _get_nested_value(data: dict, path: str):
        current = data
        for key in path.split("."):
            if not isinstance(current, dict):
                return None
            if key not in current:
                return None
            current = current[key]
        return current

    @staticmethod
    def _extract_items_total(payload: dict | list) -> tuple[list[dict], int]:
        """兼容不同返回结构，提取 items 与 total。"""
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)], len(payload)

        if not isinstance(payload, dict):
            return [], 0

        candidate_paths = [
            "items", "list", "records", "rows",
            "data.items", "data.list", "data.records", "data.rows",
            "result.items", "result.list", "result.records", "result.rows",
        ]

        items: list[dict] = []
        for path in candidate_paths:
            value = CLIBridge._get_nested_value(payload, path)
            if isinstance(value, list):
                items = [x for x in value if isinstance(x, dict)]
                break

        if not items:
            for value in payload.values():
                if isinstance(value, list):
                    items = [x for x in value if isinstance(x, dict)]
                    if items:
                        break

        total = None
        for path in (
            "total", "totalCount", "count",
            "data.total", "data.totalCount", "data.count",
            "result.total", "result.totalCount", "result.count",
        ):
            value = CLIBridge._get_nested_value(payload, path)
            if isinstance(value, int):
                total = value
                break

        if total is None:
            total = len(items)
        return items, total

    @staticmethod
    def _run_iflow_json_candidates(candidates: list[list[str]]) -> tuple[list[dict], int, str]:
        """按候选命令依次尝试，返回解析后的列表结果。"""
        iflow_cmd = CLIBridge._get_iflow_cmd()
        last_error = ""

        for args in candidates:
            try:
                kw = _subprocess_kwargs(capture=True)
                r = subprocess.run([iflow_cmd, *args], timeout=12, **kw)
                stdout = _decode(r.stdout).strip() if r.stdout else ""
                stderr = _decode(r.stderr).strip() if r.stderr else ""

                if r.returncode != 0:
                    last_error = stderr or stdout or f"命令失败: {' '.join(args)}"
                    continue

                payload = CLIBridge._parse_json_from_output(stdout)
                if payload is None:
                    last_error = f"命令未返回有效 JSON: {' '.join(args)}"
                    continue

                items, total = CLIBridge._extract_items_total(payload)
                return items, total, ""
            except Exception as e:
                last_error = str(e)

        return [], 0, last_error

    @staticmethod
    def _parse_text_list_items(text: str) -> list[dict]:
        """解析 CLI 文本列表输出为简化 items（至少包含 name 字段）。"""
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        items: list[dict] = []
        seen: set[str] = set()
        current_item: dict | None = None

        def _flush_current():
            nonlocal current_item
            if not current_item:
                return
            name = str(current_item.get("name", "")).strip()
            if not name or name in seen:
                current_item = None
                return
            seen.add(name)
            items.append(current_item)
            current_item = None

        for ln in lines:
            lower = ln.lower()
            if lower.startswith(("name", "名称", "total", "共", "usage", "用法", "提示", "tip")):
                continue
            if ln.startswith(("正在加载在线代理", "正在加载在线命令", "正在加载在线技能")):
                continue
            if ln.startswith(("在线代理", "在线命令", "在线技能", "online agents", "online commands", "online skills")):
                continue
            if ln.startswith(("总计：", "总计:", "要安装", "to install")):
                continue
            if set(ln) <= set("-|+ "):
                continue

            # Bullet entry: • xxx (ID: n)
            if ln.startswith("• "):
                _flush_current()
                entry = ln[2:].strip()
                name = entry
                item_id = ""
                if "(ID:" in entry:
                    left, right = entry.split("(ID:", 1)
                    name = left.strip()
                    item_id = right.strip().rstrip(")").strip()
                current_item = {"name": name}
                if item_id:
                    current_item["id"] = item_id
                continue

            # Detail lines for bullet entry
            if current_item is not None:
                if ln.startswith(("描述:", "描述：")):
                    current_item["description"] = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    continue
                if ln.startswith(("类别:", "类别：", "分类:", "分类：")):
                    current_item["category"] = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    continue
                if ln.startswith(("模型:", "模型：")):
                    current_item["modelName"] = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    continue
                if ln.startswith(("标签:", "标签：")):
                    current_item["tags"] = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    continue
                if ln.startswith(("作者:", "作者：", "author:", "author：")):
                    current_item["authorId"] = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    continue
                if ln.startswith(("版本:", "版本：", "version:", "version：")):
                    current_item["version"] = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    continue

            # 优先取第一列或第一个 token 作为名称
            name = ""
            if "|" in ln:
                parts = [p.strip() for p in ln.split("|") if p.strip()]
                if parts:
                    name = parts[0]
            if not name:
                name = ln.split()[0] if ln.split() else ""

            if not name:
                continue
            if len(name) > 120:
                continue
            if name in seen:
                continue
            seen.add(name)
            items.append({"name": name, "description": ln})

        _flush_current()

        return items

    @staticmethod
    def _run_iflow_text_candidates(candidates: list[list[str]]) -> tuple[list[dict], str]:
        """按候选命令依次尝试，解析文本输出（非 JSON）。"""
        iflow_cmd = CLIBridge._get_iflow_cmd()
        last_error = ""

        for args in candidates:
            try:
                kw = _subprocess_kwargs(capture=True)
                r = subprocess.run([iflow_cmd, *args], timeout=10, **kw)
                stdout = _decode(r.stdout).strip() if r.stdout else ""
                stderr = _decode(r.stderr).strip() if r.stderr else ""

                if r.returncode != 0:
                    last_error = stderr or stdout or f"命令失败: {' '.join(args)}"
                    continue

                stdout = CLIBridge._strip_ansi(stdout)
                items = CLIBridge._parse_text_list_items(stdout)
                if items:
                    return items, ""

                last_error = f"命令返回为空或不可解析: {' '.join(args)}"
            except Exception as e:
                last_error = str(e)

        return [], last_error

    @staticmethod
    def _run_iflow_online_listing(repo_type: str, page: int, size: int, search: str) -> tuple[list[dict], int | None, str]:
        """针对新版 CLI 的在线仓库命令（agent/commands online）。"""
        iflow_cmd = CLIBridge._get_iflow_cmd()
        rt = (repo_type or "").strip().lower()
        cmd_map: dict[str, list[str]] = {
            "agents": ["agent", "online"],
            "commands": ["commands", "online"],
        }
        base = cmd_map.get(rt)
        if not base:
            return [], None, ""

        args = [
            *base,
            "-p", str(max(1, int(page or 1))),
            "-s", str(max(1, int(size or 20))),
        ]
        if search:
            args.extend(["--search", search])

        try:
            kw = _subprocess_kwargs(capture=True)
            r = subprocess.run([iflow_cmd, *args], timeout=10, **kw)
            stdout = _decode(r.stdout).strip() if r.stdout else ""
            stderr = _decode(r.stderr).strip() if r.stderr else ""
            if r.returncode != 0:
                return [], None, stderr or stdout or f"命令失败: {' '.join(args)}"
            total_match = re.search(r"共\s*(\d+)\s*个", stdout)
            total = int(total_match.group(1)) if total_match else None
            stdout = CLIBridge._strip_ansi(stdout)
            items = CLIBridge._parse_text_list_items(stdout)
            if items:
                return items, total, ""
            return [], total, "在线列表为空或解析失败"
        except Exception as e:
            return [], None, str(e)

    @staticmethod
    def _contains_search(item: dict, keyword: str) -> bool:
        if not keyword:
            return True
        key = keyword.lower()

        def _walk(v) -> bool:
            if isinstance(v, str):
                return key in v.lower()
            if isinstance(v, dict):
                return any(_walk(x) for x in v.values())
            if isinstance(v, list):
                return any(_walk(x) for x in v)
            return False

        return _walk(item)

    @staticmethod
    def _fetch_online_repo(repo_type: str, page: int = 1, size: int = 15, search: str = "") -> dict:
        """统一获取在线仓库数据，并在本地做搜索与分页兜底。"""
        rt = (repo_type or "").strip().lower()
        already_paged = False
        remote_total: int | None = None
        # 兼容旧版 CLI 的 JSON 候选
        candidates_map: dict[str, list[list[str]]] = {
            "agents": [
                ["agent", "list", "--online", "--json"],
                ["agents", "list", "--online", "--json"],
                ["agent", "list", "--json", "--online"],
                ["marketplace", "list", "--type", "agents", "--json"],
            ],
            "skills": [
                ["marketplace", "list", "--type", "skills", "--json"],
            ],
            "commands": [
                ["commands", "list", "--online", "--json"],
                ["command", "list", "--online", "--json"],
                ["commands", "list", "--json", "--online"],
                ["marketplace", "list", "--type", "commands", "--json"],
            ],
            "mcp": [
                ["mcp", "list", "--online", "--json"],
                ["mcp", "servers", "list", "--online", "--json"],
                ["mcp", "list", "--json"],
                ["marketplace", "list", "--type", "mcp", "--json"],
            ],
        }
        text_candidates_map: dict[str, list[list[str]]] = {
            "agents": [
                ["agent", "list", "--online"],
                ["agents", "list", "--online"],
                ["marketplace", "list", "--type", "agents"],
            ],
            "skills": [
                ["marketplace", "list", "--type", "skills"],
            ],
            "commands": [
                ["commands", "list", "--online"],
                ["command", "list", "--online"],
                ["marketplace", "list", "--type", "commands"],
            ],
            "mcp": [
                ["mcp", "list", "--online"],
                ["mcp", "servers", "list", "--online"],
                ["marketplace", "list", "--type", "mcp"],
            ],
        }

        # 1) 新版 CLI 专用在线命令（优先）
        items, remote_total, error = CLIBridge._run_iflow_online_listing(rt, page, max(size, 20), search)
        if items:
            already_paged = True

        # 对 mcp/skills 优先尝试 HTTP，减少旧命令链失败带来的延迟
        if not items and rt in ("mcp", "skills"):
            http_items, http_total, http_paged = CLIBridge._fetch_online_repo_http(rt, page, max(size, 20), search)
            if http_items:
                items = http_items
                error = ""
                already_paged = http_paged
                remote_total = http_total if isinstance(http_total, int) else len(http_items)

        # 2) 旧版 JSON 命令
        if not items:
            candidates = candidates_map.get(rt, [])
            items, _total_remote, error = CLIBridge._run_iflow_json_candidates(candidates)

        # CLI 失败时尝试 HTTP API 回退
        if error and not items:
            http_items, http_total, http_paged = CLIBridge._fetch_online_repo_http(rt, page, max(size, 20), search)
            if http_items:
                items = http_items
                error = ""
                already_paged = http_paged
                remote_total = http_total if isinstance(http_total, int) else len(http_items)

        # 仍失败时，尝试解析 CLI 文本输出
        if error and not items:
            text_items, text_err = CLIBridge._run_iflow_text_candidates(
                text_candidates_map.get(rt, [])
            )
            if text_items:
                items = text_items
                error = ""
            elif text_err:
                error = text_err

        # Skills 在当前 CLI 版本通常不支持在线浏览（仅支持 add）
        if rt == "skills" and not items and error:
            error = (
                "当前 iflow CLI 版本不支持 skills 在线列表（仅支持 iflow skill add <name-or-id>）。"
                "已尝试所有兼容命令与 HTTP 回退，仍未获取到列表。"
            )

        if error and not items:
            return {"items": [], "total": 0, "error": error}

        filtered = [x for x in items if CLIBridge._contains_search(x, search or "")]
        if already_paged:
            return {
                "items": filtered,
                "total": remote_total if isinstance(remote_total, int) and remote_total > 0 else len(filtered),
            }

        page_num = max(1, int(page or 1))
        page_size = max(1, int(size or 15))
        start = (page_num - 1) * page_size
        end = start + page_size

        return {
            "items": filtered[start:end],
            "total": len(filtered),
        }

    @staticmethod
    def _fetch_online_repo_http(repo_type: str, page: int = 1, size: int = 20, search: str = "") -> tuple[list[dict], int | None, bool]:
        """通过 HTTP API 直接获取在线仓库数据（CLI 失败时的回退方案）。"""
        import urllib.request
        import urllib.error
        import urllib.parse

        settings = IFlowSettings.load()
        api_key = settings.get("apiKey", "")
        base_url = settings.get("baseUrl", "https://apis.iflow.cn/v1").rstrip("/")

        # 构建候选 URL
        type_map = {
            "agents": "agents",
            "skills": "skills",
            "commands": "commands",
            "mcp": "mcp-servers",
        }
        resource = type_map.get(repo_type, repo_type)

        def _parse_i18n_json_field(value: str) -> str:
            if not isinstance(value, str):
                return str(value)
            txt = value.strip()
            if not txt.startswith("{"):
                return value
            try:
                obj = json.loads(txt)
                if isinstance(obj, dict):
                    return str(obj.get("zh") or obj.get("en") or value)
            except Exception:
                pass
            return value

        if repo_type == "skills":
            try:
                payload = json.dumps({
                    "page": max(1, int(page or 1)),
                    "size": max(1, int(size or 20)),
                    "search": search or "",
                }).encode("utf-8")
                skills_urls = [
                    f"{base_url}/skills/list",
                    "https://apis.iflow.cn/v1/skills/list",
                ]

                data = None
                for skills_url in skills_urls:
                    try:
                        req = urllib.request.Request(
                            skills_url,
                            data=payload,
                            method="POST",
                        )
                        req.add_header("Content-Type", "application/json")
                        req.add_header("Accept", "application/json")
                        with urllib.request.urlopen(req, timeout=12) as resp:
                            data = json.loads(resp.read().decode("utf-8", errors="replace"))
                        if data:
                            break
                    except Exception:
                        continue

                if data is None:
                    return [], None, False

                raw_items = []
                total: int | None = None
                if isinstance(data, dict):
                    root = data.get("data", {})
                    if isinstance(root, dict):
                        raw_items = root.get("data", []) or root.get("list", []) or []
                        if isinstance(root.get("total"), int):
                            total = int(root.get("total"))
                    if total is None and isinstance(data.get("total"), int):
                        total = int(data.get("total"))

                items: list[dict] = []
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    items.append({
                        "id": str(item.get("id", "")),
                        "skillId": item.get("skillId") or item.get("id", ""),
                        "name": _parse_i18n_json_field(str(item.get("name", ""))),
                        "description": _parse_i18n_json_field(str(item.get("description", ""))),
                        "category": _parse_i18n_json_field(str(item.get("category", ""))),
                        "tags": _parse_i18n_json_field(str(item.get("tags", ""))),
                        "version": item.get("version", ""),
                        "authorId": item.get("authorId", ""),
                    })
                if items:
                    return items, total if isinstance(total, int) else len(items), True
            except Exception:
                pass

        base_candidate_urls = [
            f"{base_url}/marketplace/{resource}",
            f"{base_url}/{resource}",
            f"{base_url.replace('/v1', '/api')}/marketplace/{resource}",
            f"{base_url.replace('/v1', '')}/api/marketplace?type={repo_type}",
        ]

        params_obj = {
            "page": max(1, int(page or 1)),
            "size": max(1, int(size or 20)),
            "search": search or "",
            "q": search or "",
        }
        params = urllib.parse.urlencode(params_obj)
        candidate_urls = [f"{u}{'&' if '?' in u else '?'}{params}" for u in base_candidate_urls]

        for url in candidate_urls:
            try:
                req = urllib.request.Request(url)
                if api_key:
                    req.add_header("Authorization", f"Bearer {api_key}")
                req.add_header("Content-Type", "application/json")
                req.add_header("Accept", "application/json")

                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                items, _total = CLIBridge._extract_items_total(data)
                if items:
                    return items, _total if isinstance(_total, int) else len(items), True
            except Exception:
                continue

        return [], None, False

    @staticmethod
    def fetch_online_agents(page: int = 1, size: int = 15, search: str = "") -> dict:
        return CLIBridge._fetch_online_repo("agents", page, size, search)

    @staticmethod
    def fetch_online_skills(page: int = 1, size: int = 15, search: str = "") -> dict:
        return CLIBridge._fetch_online_repo("skills", page, size, search)

    @staticmethod
    def fetch_online_commands(page: int = 1, size: int = 15, search: str = "") -> dict:
        return CLIBridge._fetch_online_repo("commands", page, size, search)

    @staticmethod
    def fetch_online_mcp_servers(page: int = 1, size: int = 15, search: str = "") -> dict:
        return CLIBridge._fetch_online_repo("mcp", page, size, search)

    # ------------------------------------------------------------------
    # Gateway 管理
    # ------------------------------------------------------------------
    @staticmethod
    def _get_gateway_port() -> int:
        """获取网关监听端口（默认 8090）。"""
        cfg = CLIBridge.load_bot_config()
        raw = cfg.get("driver", {}).get("acp_port", 8090)
        try:
            port = int(raw)
        except Exception:
            port = 8090
        if port <= 0 or port > 65535:
            port = 8090
        return port

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """跨平台检查进程是否存活。"""
        if pid <= 0:
            return False
        try:
            if platform.system() == "Windows":
                kw = _subprocess_kwargs(capture=True)
                result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=6, **kw)
                out = _decode(result.stdout).strip()
                for line in out.splitlines():
                    line = line.strip()
                    if not line or line.startswith(("信息", "INFO")):
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) == pid:
                        return True
                return False
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    @staticmethod
    def _find_listening_pids_by_port(port: int) -> list[int]:
        """查找正在监听指定端口的 PID 列表。"""
        if port <= 0:
            return []

        pids: list[int] = []
        seen: set[int] = set()

        if platform.system() == "Windows":
            try:
                kw = _subprocess_kwargs(capture=True)
                r = subprocess.run(["netstat", "-ano", "-p", "tcp"], timeout=10, **kw)
                text = _decode(r.stdout) if r.stdout else ""
                for raw in text.splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    parts = line.split()
                    # 典型格式: TCP 0.0.0.0:8090 0.0.0.0:0 LISTENING 1234
                    if len(parts) < 5:
                        continue
                    state = parts[3].upper()
                    if state != "LISTENING":
                        continue
                    local_addr = parts[1]
                    if not local_addr.endswith(f":{port}"):
                        continue
                    pid_raw = parts[-1]
                    if not pid_raw.isdigit():
                        continue
                    pid = int(pid_raw)
                    if pid > 0 and pid not in seen:
                        seen.add(pid)
                        pids.append(pid)
            except Exception:
                pass
            return pids

        # 非 Windows：尽量用 lsof 获取 PID
        try:
            kw = _subprocess_kwargs(capture=True)
            r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], timeout=10, **kw)
            text = _decode(r.stdout) if r.stdout else ""
            for line in text.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 2:
                    continue
                if parts[1].isdigit():
                    pid = int(parts[1])
                    if pid > 0 and pid not in seen:
                        seen.add(pid)
                        pids.append(pid)
        except Exception:
            pass
        return pids

    @staticmethod
    def is_gateway_running() -> tuple[bool, Optional[int]]:
        pid_file = CLIBridge.get_pid_file()
        # 1) 先看 PID 文件（快路径）
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if CLIBridge._is_pid_alive(pid):
                    return True, pid
                # PID 文件陈旧，清理后继续端口探测
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass

        # 2) 端口探测：兼容手动启动/多实例/无 PID 文件
        port = CLIBridge._get_gateway_port()
        pids = CLIBridge._find_listening_pids_by_port(port)
        if pids:
            chosen_pid = pids[0]
            try:
                pid_file.parent.mkdir(parents=True, exist_ok=True)
                pid_file.write_text(str(chosen_pid), encoding="utf-8")
            except Exception:
                pass
            return True, chosen_pid

        return False, None

    @staticmethod
    def start_gateway() -> tuple[bool, str]:
        """启动 Gateway。自动检测 iflow-bot 安装方式并校验结果。"""
        try:
            execution = CLIBridge._get_iflow_bot_execution()
            if execution is None:
                return False, (
                    "iflow-bot 未安装，无法启动网关。\n\n"
                    "可选修复方式：\n"
                    "  1) pip install iflow-bot\n"
                    "  2) 在配置中设置 driver.iflow_bot_project\n"
                    "  3) 设置环境变量 IFLOW_BOT_PROJECT"
                )

            base_cmd, cmd_cwd, cmd_env = execution
            kw = _subprocess_kwargs(capture=True, cwd=cmd_cwd)
            if cmd_env is not None:
                kw["env"] = cmd_env
            result = subprocess.run([*base_cmd, "gateway", "start"], timeout=30, **kw)
            if result.returncode != 0:
                stdout_text = _decode(result.stdout).strip()
                stderr_text = _decode(result.stderr).strip()
                detail = stderr_text or stdout_text or "未知错误"
                return False, f"启动失败: {detail}"

            time.sleep(1)
            running, pid = CLIBridge.is_gateway_running()
            if running:
                return True, f"Gateway 已启动 (PID: {pid})"
            return True, "Gateway 启动命令执行完成，请查看日志确认运行状态。"
        except Exception as e:
            return False, f"启动失败: {e}"

    @staticmethod
    def stop_gateway() -> tuple[bool, str]:
        pid_file = CLIBridge.get_pid_file()
        try:
            execution = CLIBridge._get_iflow_bot_execution()
            if execution is not None:
                base_cmd, cmd_cwd, cmd_env = execution
                kw = _subprocess_kwargs(capture=True, cwd=cmd_cwd)
                if cmd_env is not None:
                    kw["env"] = cmd_env
                r = subprocess.run([*base_cmd, "gateway", "stop"], timeout=20, **kw)
                if r.returncode == 0:
                    pid_file.unlink(missing_ok=True)
                    return True, "Gateway 已停止"

            if not pid_file.exists():
                return False, "Gateway 未运行"

            pid = int(pid_file.read_text().strip())
            if platform.system() == "Windows":
                kw = _subprocess_kwargs(capture=True)
                subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], timeout=10, **kw)
            else:
                import signal as sig
                os.kill(pid, sig.SIGTERM)
            pid_file.unlink(missing_ok=True)
            return True, f"Gateway 已停止 (PID: {pid})"
        except Exception as e:
            pid_file.unlink(missing_ok=True)
            return False, f"停止失败: {e}"

    @staticmethod
    def restart_gateway() -> tuple[bool, str]:
        CLIBridge.stop_gateway()
        import time; time.sleep(1)
        return CLIBridge.start_gateway()

    # ------------------------------------------------------------------
    # 模型 / Thinking (使用 IFlowSettings)
    # ------------------------------------------------------------------
    @staticmethod
    def set_model(name: str) -> None:
        """设置模型（写入 iflow settings.json）。"""
        IFlowSettings.set_model(name)

    @staticmethod
    def get_model() -> str:
        """获取模型（从 iflow settings.json）。"""
        return IFlowSettings.get_model() or "glm-5"

    @staticmethod
    def set_thinking(enabled: bool) -> None:
        IFlowSettings.set_thinking(enabled)

    @staticmethod
    def get_thinking() -> bool:
        return IFlowSettings.get_thinking()

    # ------------------------------------------------------------------
    # 工作空间
    # ------------------------------------------------------------------
    @staticmethod
    def get_workspace() -> str:
        """获取工作空间路径（优先 bot 配置，回退默认）。"""
        cfg = CLIBridge.load_bot_config()
        ws = cfg.get("driver", {}).get("workspace", "")
        if not ws:
            ws = str(Path.home())
        return ws

    @staticmethod
    def get_chat_workspace() -> str:
        """获取对话使用的工作空间路径（独立于 Bot 配置）。"""
        ws = IFlowSettings.get_chat_workspace()
        if ws:
            return ws
        ws = CLIBridge.get_workspace()
        if ws:
            return ws
        return str(Path.home())

    @staticmethod
    def set_chat_workspace(workspace: str) -> str:
        """设置对话工作空间路径并返回最终保存的绝对路径。"""
        ws = str(Path(os.path.abspath(str(Path(workspace).expanduser()))))
        IFlowSettings.set_chat_workspace(ws)
        return ws

    @staticmethod
    def _workspace_to_project_name(workspace: str) -> str:
        """将工作空间路径转换为 iflow 项目名（与 iflow CLI 当前规则一致）。

        CLI 规则: /[^\\p{L}\\p{N}\\-_.]/gu（保留 Unicode 字母/数字含中文，其余→'-'）。
        """
        ws_path = Path(os.path.abspath(str(Path(workspace).expanduser())))
        name = str(ws_path).replace("\\", "-").replace("/", "-").replace(":", "-")
        name = re.sub(r"\s+", "-", name)
        name = "".join(ch if (ch.isalnum() or ch in "-_.") else "-" for ch in name)
        name = re.sub(r"-+", "-", name).strip("-")
        return f"-{name}" if name else "-root"

    @staticmethod
    def _workspace_to_project_name_legacy(workspace: str) -> str:
        """旧版 ASCII-only 目录名（用于兼容旧版 CLI 创建的会话目录）。

        旧版代码查除首部 '-'、保留尾部，可能生成如 '-E-15732-Desktop-ai-' 的名称。
        """
        ws_path = Path(os.path.abspath(str(Path(workspace).expanduser())))
        name = str(ws_path).replace("\\", "-").replace("/", "-").replace(":", "-")
        name = re.sub(r"\s+", "-", name)
        name = re.sub(r"[^A-Za-z0-9._-]", "-", name)
        name = re.sub(r"-+", "-", name).lstrip("-")
        return f"-{name}" if name else "-root"

    @staticmethod
    def _get_candidate_session_dirs(workspace: str | None = None) -> list[Path]:
        """返回当前工作区所有候选 session 目录（去重，Unicode 主目录在前）。

        同时尝试旧版 lstrip 和 full-strip 两种变体，尽量覆盖不同旧版创建的目录名。
        """
        ws = workspace or CLIBridge.get_chat_workspace()
        projects_root = IFlowSettings.get_dir() / "projects"
        primary = projects_root / CLIBridge._workspace_to_project_name(ws)
        legacy = projects_root / CLIBridge._workspace_to_project_name_legacy(ws)
        # 全 strip 变体（防止某些旧版术双向 strip）
        ws_path = Path(os.path.abspath(str(Path(ws).expanduser())))
        _n = str(ws_path).replace("\\", "-").replace("/", "-").replace(":", "-")
        _n = re.sub(r"\s+", "-", _n)
        _n = re.sub(r"[^A-Za-z0-9._-]", "-", _n)
        _n = re.sub(r"-+", "-", _n).strip("-")
        legacy_full_strip = projects_root / (f"-{_n}" if _n else "-root")

        seen: list[Path] = []
        for d in [primary, legacy, legacy_full_strip]:
            if str(d) not in [str(x) for x in seen]:
                seen.append(d)
        return seen

    @staticmethod
    def find_session_file(session_id: str) -> Path | None:
        """在所有候选 session 目录中查找指定 session 文件，返回 Path 或 None。"""
        if not session_id:
            return None
        for d in CLIBridge._get_candidate_session_dirs():
            sf = d / f"{session_id}.jsonl"
            if sf.exists():
                return sf
        return None

    # ------------------------------------------------------------------
    # 会话管理 (iflow 原生 session)
    # ------------------------------------------------------------------
    @staticmethod
    def get_chat_sessions_dir() -> Path:
        """获取对话使用的 sessions 目录（基于 chat workspace）。

        返回当前 CLI 规则对应的主目录（Unicode 名）。新建会话时 CLI 会写入该目录。
        读取历史会话请用 list_iflow_sessions()，它会自动合并所有候选目录。
        """
        workspace = CLIBridge.get_chat_workspace()
        projects_root = IFlowSettings.get_dir() / "projects"
        primary = projects_root / CLIBridge._workspace_to_project_name(workspace)
        return primary

    @staticmethod
    def _parse_session_brief(sf: Path, stat) -> dict | None:
        """解析单个 session 文件摘要。"""
        session_id = sf.stem
        first_user_msg = ""
        last_model = ""
        msg_count = 0
        json_loads = json.loads

        try:
            with open(sf, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    msg_count += 1
                    try:
                        entry = json_loads(line)
                    except json.JSONDecodeError:
                        continue
                    entry_type = entry.get("type")
                    if entry_type not in ("user", "assistant"):
                        continue
                    msg_obj = entry.get("message", {})
                    if entry_type == "user" and not first_user_msg:
                        content = msg_obj.get("content", "")
                        if isinstance(content, str) and content:
                            first_user_msg = content[:80]
                    elif entry_type == "assistant":
                        model_name = msg_obj.get("model", "")
                        if model_name:
                            last_model = model_name
        except Exception:
            return None

        return {
            "id": session_id,
            "file": str(sf),
            "summary": first_user_msg or "(空会话)",
            "model": last_model,
            "messages": msg_count,
            "modified": stat.st_mtime,
            "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime("%m-%d %H:%M"),
            "size": stat.st_size,
        }

    @staticmethod
    def list_iflow_sessions() -> list[dict]:
        """列出所有 iflow 会话，解析摘要。

        会自动合并当前工作区所有候选目录（Unicode 主目录 + 旧版 ASCII 目录），
        以确保中文路径旧版历史会话和新建会话都能正确显示。
        """
        candidate_dirs = CLIBridge._get_candidate_session_dirs()

        # 构建合并签名（=所有目录存在的文件的(名,mtime,size)元组集合）
        file_stats: list[tuple[Path, object]] = []
        signature_parts: list[tuple[str, int, int]] = []
        seen_ids: set[str] = set()

        for sessions_dir in candidate_dirs:
            if not sessions_dir.exists():
                continue
            for sf in sorted(sessions_dir.glob("session-*.jsonl"), key=lambda p: p.name):
                sid = sf.stem
                if sid in seen_ids:
                    continue  # 同名 session 只取先扫到的（主目录优先）
                seen_ids.add(sid)
                try:
                    stat = sf.stat()
                except Exception:
                    continue
                file_stats.append((sf, stat))
                signature_parts.append((str(sf), int(stat.st_mtime_ns), int(stat.st_size)))

        if not file_stats:
            return []

        composite_key = "|".join(str(d) for d in candidate_dirs)
        signature = tuple(signature_parts)
        cached_list = CLIBridge._session_list_cache.get(composite_key)
        if cached_list and cached_list.get("signature") == signature:
            return list(cached_list.get("sessions", []))

        sessions: list[dict] = []
        for sf, stat in file_stats:
            cache_key = str(sf)
            cached_brief = CLIBridge._session_brief_cache.get(cache_key)
            if (
                cached_brief
                and cached_brief.get("mtime_ns") == int(stat.st_mtime_ns)
                and cached_brief.get("size") == int(stat.st_size)
            ):
                sessions.append(dict(cached_brief["data"]))
                continue

            parsed = CLIBridge._parse_session_brief(sf, stat)
            if parsed is None:
                continue

            CLIBridge._session_brief_cache[cache_key] = {
                "mtime_ns": int(stat.st_mtime_ns),
                "size": int(stat.st_size),
                "data": parsed,
            }
            sessions.append(dict(parsed))

        sessions.sort(key=lambda x: x["modified"], reverse=True)
        CLIBridge._session_list_cache[composite_key] = {
            "signature": signature,
            "sessions": [dict(item) for item in sessions],
        }
        return sessions

    @staticmethod
    def load_session_messages(session_id: str) -> list[dict]:
        """加载会话完整消息列表。"""
        session_file = CLIBridge.find_session_file(session_id)
        if session_file is None:
            return []

        try:
            stat = session_file.stat()
            cache_key = str(session_file)
            cached = CLIBridge._session_messages_cache.get(cache_key)
            if (
                cached
                and cached.get("mtime_ns") == int(stat.st_mtime_ns)
                and cached.get("size") == int(stat.st_size)
            ):
                return list(cached.get("messages", []))
        except Exception:
            stat = None
            cache_key = str(session_file)

        messages = []
        json_loads = json.loads
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json_loads(line)
                    msg_type = entry.get("type", "")
                    msg_obj = entry.get("message", {})
                    timestamp = entry.get("timestamp", "")

                    if msg_type == "user":
                        content = msg_obj.get("content", "")

                        # 普通用户文本
                        user_text = ""
                        if isinstance(content, str):
                            user_text = content
                        elif isinstance(content, list):
                            text_parts = []
                            for p in content:
                                if not isinstance(p, dict):
                                    continue
                                if p.get("type") == "text":
                                    t = p.get("text", "")
                                    if isinstance(t, str) and t:
                                        text_parts.append(t)
                            user_text = "\n".join(text_parts)

                        if user_text:
                            messages.append({
                                "role": "user",
                                "content": user_text,
                                "timestamp": timestamp,
                            })

                        # 工具返回（由 iflow 记录在 user + toolUseResult 上）
                        tool_result_info = entry.get("toolUseResult")
                        if tool_result_info:
                            tool_name = tool_result_info.get("toolName", "")
                            status = tool_result_info.get("status", "")
                            result_text = ""

                            if isinstance(content, list):
                                for p in content:
                                    if not isinstance(p, dict) or p.get("type") != "tool_result":
                                        continue
                                    c = p.get("content", {})
                                    if isinstance(c, dict):
                                        resp = c.get("functionResponse", {}).get("response", {})
                                        out = resp.get("output", "")
                                        if out:
                                            result_text = str(out)
                                    elif isinstance(c, str):
                                        result_text = c

                            messages.append({
                                "role": "tool_result",
                                "tool_name": tool_name,
                                "status": status,
                                "content": result_text,
                                "timestamp": timestamp,
                            })
                    elif msg_type == "assistant":
                        raw_content = msg_obj.get("content", "")
                        tool_calls: list[dict] = []
                        content_events: list[dict] = []
                        thinking_blocks: list[str] = []

                        if isinstance(raw_content, list):
                            text_parts = []
                            for p in raw_content:
                                if not isinstance(p, dict):
                                    continue
                                thinking_text = _extract_thinking_from_content_part(p)
                                if thinking_text:
                                    thinking_blocks.append(thinking_text)
                                    content_events.append({
                                        "type": "thinking",
                                        "content": thinking_text,
                                    })
                                p_type = p.get("type")
                                if p_type == "text":
                                    t = p.get("text", "")
                                    if isinstance(t, str) and t:
                                        text_parts.append(t)
                                        content_events.append({
                                            "type": "text",
                                            "content": t,
                                        })
                                elif p_type == "tool_use":
                                    tc = {
                                        "tool_name": p.get("name", ""),
                                        "input": p.get("input", {}),
                                    }
                                    tool_calls.append(tc)
                                    content_events.append({
                                        "type": "call",
                                        "tool_name": tc["tool_name"],
                                        "input": tc["input"],
                                    })
                            content = "\n".join(text_parts)
                        elif isinstance(raw_content, str):
                            content = raw_content
                            if content:
                                content_events.append({
                                    "type": "text",
                                    "content": content,
                                })
                        else:
                            content = str(raw_content)
                            if content:
                                content_events.append({
                                    "type": "text",
                                    "content": content,
                                })

                        if "<" in content and "</" in content:
                            import re as _re
                            extra_thinking = _re.findall(
                                r'<(?:think|thinking|reasoning|reasoning_content)>(.*?)</(?:think|thinking|reasoning|reasoning_content)>',
                                content,
                                flags=_re.DOTALL,
                            )
                            for tb in extra_thinking:
                                cleaned = tb.strip()
                                if cleaned:
                                    thinking_blocks.append(cleaned)

                        # Message-level thinking (e.g. reasoning_content in OpenAI-compat format)
                        msg_level_thinking = _extract_thinking_from_message(msg_obj)
                        if msg_level_thinking:
                            thinking_blocks.append(msg_level_thinking)
                            content_events.append({
                                "type": "thinking",
                                "content": msg_level_thinking,
                            })

                        dedup_thinking: list[str] = []
                        seen_thinking: set[str] = set()
                        for tb in thinking_blocks:
                            normalized = (tb or "").strip()
                            if not normalized or normalized in seen_thinking:
                                continue
                            seen_thinking.add(normalized)
                            dedup_thinking.append(normalized)

                        if content or tool_calls or dedup_thinking:
                            messages.append({
                                "role": "assistant",
                                "content": content,
                                "model": msg_obj.get("model", ""),
                                "tool_calls": tool_calls,
                                "content_events": content_events,
                                "thinking": dedup_thinking,
                                "timestamp": timestamp,
                            })
                except json.JSONDecodeError:
                    continue

        if stat is not None:
            CLIBridge._session_messages_cache[cache_key] = {
                "mtime_ns": int(stat.st_mtime_ns),
                "size": int(stat.st_size),
                "messages": list(messages),
            }
        return messages

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """删除 iflow CLI 会话文件。"""
        if not session_id:
            return False
        session_file = CLIBridge.find_session_file(session_id)
        if session_file is None:
            return False
        try:
            sessions_dir = session_file.parent
            session_file.unlink()
            cache_key = str(session_file)
            CLIBridge._session_brief_cache.pop(cache_key, None)
            CLIBridge._session_messages_cache.pop(cache_key, None)
            # 清除所有候选目录的列表缓存
            composite_key = "|".join(str(d) for d in CLIBridge._get_candidate_session_dirs())
            CLIBridge._session_list_cache.pop(composite_key, None)
            CLIBridge._session_list_cache.pop(str(sessions_dir), None)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 渠道映射会话
    # ------------------------------------------------------------------
    @staticmethod
    def get_session_mappings() -> dict:
        path = Path.home() / ".iflow-bot" / "session_mappings.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def clear_session(channel: str, chat_id: str) -> bool:
        path = Path.home() / ".iflow-bot" / "session_mappings.json"
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            key = f"{channel}:{chat_id}"
            if key in data:
                del data[key]
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # 渠道信息
    # ------------------------------------------------------------------
    @staticmethod
    def get_enabled_channels() -> list[str]:
        cfg = CLIBridge.load_bot_config()
        enabled = []
        channels = cfg.get("channels", {})
        for name in ["telegram", "discord", "whatsapp", "feishu",
                      "slack", "dingtalk", "qq", "email", "mochat"]:
            ch = channels.get(name, {})
            if ch.get("enabled", False):
                enabled.append(name)
        return enabled

    @staticmethod
    def test_channel_connection(channel_type: str, config: dict) -> tuple[bool, str]:
        """测试渠道配置连通性（轻量级校验）。"""
        import socket
        import urllib.request

        ch = (channel_type or "").strip().lower()
        cfg = config if isinstance(config, dict) else {}

        required_fields: dict[str, list[str]] = {
            "telegram": ["token"],
            "discord": ["token"],
            "slack": ["bot_token", "app_token"],
            "feishu": ["app_id", "app_secret"],
            "dingtalk": ["client_id", "client_secret"],
            "qq": ["app_id", "secret"],
            "whatsapp": ["bridge_url", "bridge_token"],
            "email": ["imap_host", "smtp_host", "imap_username", "smtp_username"],
            "mochat": ["base_url", "claw_token", "agent_user_id"],
        }

        missing = [
            k for k in required_fields.get(ch, [])
            if not str(cfg.get(k, "")).strip()
        ]
        if missing:
            return False, f"缺少必要字段: {', '.join(missing)}"

        def _check_url(url: str) -> tuple[bool, str]:
            target = (url or "").strip()
            if not target:
                return False, "URL 为空"
            if not target.startswith(("http://", "https://")):
                return False, "URL 必须以 http:// 或 https:// 开头"
            try:
                req = urllib.request.Request(target, method="GET")
                with urllib.request.urlopen(req, timeout=6) as resp:
                    status = getattr(resp, "status", 200)
                if status >= 400:
                    return False, f"HTTP 状态异常: {status}"
                return True, f"HTTP 可达: {status}"
            except Exception as e:
                msg = str(e)
                if "401" in msg or "403" in msg:
                    return True, "服务可达（鉴权失败属于预期）"
                return False, f"连接失败: {msg}"

        if ch == "whatsapp":
            return _check_url(str(cfg.get("bridge_url", "")))

        if ch == "mochat":
            return _check_url(str(cfg.get("base_url", "")))

        if ch == "email":
            try:
                socket.getaddrinfo(str(cfg.get("imap_host", "")), 993)
                socket.getaddrinfo(str(cfg.get("smtp_host", "")), 465)
                return True, "IMAP/SMTP 主机解析成功"
            except Exception as e:
                return False, f"邮件服务器解析失败: {e}"

        if ch in ("dingtalk", "qq", "telegram", "discord", "slack", "feishu"):
            return True, "配置校验通过（该渠道需在网关启动后验证实际回调/推送）"

        return True, "配置校验通过"

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_ansi(text: str) -> str:
        ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
        return ansi_pattern.sub("", text)

    @staticmethod
    def _read_text_with_fallback(path: Path) -> str:
        raw = path.read_bytes()
        for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "cp936", "latin-1"):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _tail_text(text: str, lines: int) -> str:
        all_lines = text.splitlines()
        return "\n".join(all_lines[-lines:])

    @staticmethod
    def _read_single_log(path: Path, lines: int) -> str:
        if not path.exists():
            return ""
        try:
            text = CLIBridge._read_text_with_fallback(path)
            text = CLIBridge._strip_ansi(text)
            return CLIBridge._tail_text(text, lines)
        except Exception:
            return ""

    @staticmethod
    def read_log(lines: int = 200, source: str = "all") -> str:
        """读取日志。

        source: all | iflow | iflow-bot
        """
        source = (source or "all").strip().lower()
        bot_file = CLIBridge.get_log_file()
        iflow_file = CLIBridge.get_latest_iflow_log_file()

        if source == "iflow-bot":
            text = CLIBridge._read_single_log(bot_file, lines)
            return text or "(暂无 iflow-bot 日志)"

        if source == "iflow":
            if iflow_file is None:
                return "(暂无 iflow CLI 日志)"
            text = CLIBridge._read_single_log(iflow_file, lines)
            return text or "(暂无 iflow CLI 日志)"

        # all
        bot_text = CLIBridge._read_single_log(bot_file, lines)
        iflow_text = CLIBridge._read_single_log(iflow_file, lines) if iflow_file else ""

        parts: list[str] = []
        if iflow_file is not None:
            parts.append(f"===== iflow CLI 日志: {iflow_file.name} =====")
            parts.append(iflow_text or "(暂无 iflow CLI 日志)")
        else:
            parts.append("===== iflow CLI 日志 =====")
            parts.append("(暂无 iflow CLI 日志)")

        parts.append("")
        parts.append(f"===== iflow-bot 日志: {bot_file.name} =====")
        parts.append(bot_text or "(暂无 iflow-bot 日志)")
        return "\n".join(parts)

    @staticmethod
    def clear_log(source: str = "all") -> bool:
        source = (source or "all").strip().lower()
        ok = True

        if source in ("all", "iflow-bot"):
            bot_file = CLIBridge.get_log_file()
            try:
                bot_file.parent.mkdir(parents=True, exist_ok=True)
                bot_file.write_text("", encoding="utf-8")
            except Exception:
                ok = False

        if source in ("all", "iflow"):
            latest = CLIBridge.get_latest_iflow_log_file()
            if latest is not None:
                try:
                    latest.write_text("", encoding="utf-8")
                except Exception:
                    ok = False

        return ok

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @staticmethod
    def get_cron_jobs() -> list[dict]:
        path = CLIBridge.get_bot_data_dir() / "cron" / "jobs.json"
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("jobs", [])
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []


class IFlowChatWorker(QThread):
    """后台线程调用 iflow CLI 对话，bytes 模式读取避免编码错误。"""

    chunk_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, message: str, workspace: str = "",
                 model: str = "", thinking: bool = False,
                 model_source: str = "cli",
                 session_id: str = "", resume: bool = False,
                 parent=None):
        super().__init__(parent)
        self.message = message
        self.workspace = workspace or str(Path.home())
        self.model = model or IFlowSettings.get_model() or "glm-5"
        self.model_source = model_source or "cli"
        self.thinking = thinking
        self.session_id = session_id
        self.resume = resume
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    def run(self):
        try:
            import codecs

            iflow_cmd = CLIBridge._get_iflow_cmd()
            cmd = [iflow_cmd, "-p", self.message, "--model", self.model, "--yolo"]
            if self.thinking:
                cmd.append("--thinking")
            if self.resume and self.session_id:
                cmd.extend(["--resume", self.session_id])

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            # 减少子进程格式化输出，可能有助于改善流式刷新
            env["NO_COLOR"] = "1"
            env["FORCE_COLOR"] = "0"

            kwargs: dict = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "cwd": str(Path(self.workspace)),
                "env": env,
                "bufsize": 0,
            }
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            Path(self.workspace).mkdir(parents=True, exist_ok=True)
            self._process = subprocess.Popen(cmd, **kwargs)
            full_output: list[str] = []
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

            stdout_fd = self._process.stdout.fileno()
            # bytes 模式读取，使用 os.read 确保即时返回可用数据
            while True:
                if self._cancelled:
                    break
                try:
                    raw = os.read(stdout_fd, 4096)
                except OSError:
                    break
                if not raw:
                    break
                text = decoder.decode(raw, final=False)
                if text:
                    full_output.append(text)
                    self.chunk_received.emit(text)

            tail_text = decoder.decode(b"", final=True)
            if tail_text:
                full_output.append(tail_text)
                self.chunk_received.emit(tail_text)

            self._process.wait()

            if self._cancelled:
                self.error.emit("已取消")
                return

            result = "".join(full_output).strip()
            if self._process.returncode != 0:
                raw_err = self._process.stderr.read()
                stderr_text = _decode(raw_err) if raw_err else ""
                self.error.emit(stderr_text.strip() or result or "iflow 执行失败")
                return
            self.finished.emit(result)

        except FileNotFoundError:
            self.error.emit("未找到 iflow 命令，请确保已安装 iflow CLI\n安装: npm install -g @iflow-ai/iflow-cli@latest")
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
        if self._process:
            try:
                if platform.system() == "Windows":
                    kw = _subprocess_kwargs(capture=True)
                    subprocess.run(["taskkill", "/PID", str(self._process.pid), "/F", "/T"], **kw)
                else:
                    self._process.terminate()
            except Exception:
                pass


class StatusMonitor(QThread):
    """后台线程定期收集系统状态，避免 UI 线程阻塞。"""

    status_updated = Signal(dict)

    def __init__(self, interval_s: int = 15, parent=None):
        super().__init__(parent)
        self._running = True
        self._interval = interval_s

    def run(self):
        while self._running:
            try:
                data = self._collect_all()
                self.status_updated.emit(data)
            except Exception:
                pass
            # 以 100ms 为步进休眠，方便快速退出
            for _ in range(self._interval * 10):
                if not self._running:
                    break
                self.msleep(100)

    def _collect_all(self) -> dict:
        installed = CLIBridge.check_iflow_installed()
        version = CLIBridge.get_iflow_version() if installed else "未安装"
        logged_in = CLIBridge.check_iflow_logged_in() if installed else False
        auth_info = CLIBridge.check_iflow_auth() if installed else {}
        gw_running, gw_pid = CLIBridge.is_gateway_running()
        channels = CLIBridge.get_enabled_channels()
        config = CLIBridge.load_bot_config()
        model = IFlowSettings.get_model() or "glm-5"
        thinking = IFlowSettings.get_thinking()
        workspace = CLIBridge.get_workspace()
        log_text = CLIBridge.read_log(200)

        # 后台获取模型列表（带来源，供聊天页/配置页直接使用）
        models_with_source = CLIBridge.get_iflow_models_with_source()

        # 读取 MCP / Skills / Agents
        mcp_servers = CLIBridge.get_mcp_servers_list()
        skills = CLIBridge.get_skills()
        agents = CLIBridge.get_agents()
        commands = CLIBridge.get_commands()

        return {
            "iflow_installed": installed,
            "iflow_version": version,
            "iflow_logged_in": logged_in,
            "auth_info": auth_info,
            "gateway_running": gw_running,
            "gateway_pid": gw_pid,
            "enabled_channels": channels,
            "config": config,
            "current_model": model,
            "thinking": thinking,
            "workspace": workspace,
            "log_text": log_text,
            "models_with_source": models_with_source,
            "mcp_servers": mcp_servers,
            "skills": skills,
            "agents": agents,
            "commands": commands,
        }

    def stop(self):
        self._running = False
