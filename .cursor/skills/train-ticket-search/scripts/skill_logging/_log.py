"""
自包含日志：对外只暴露模块级函数；实现为 LogBase 子类。
默认 ``JsonlFileLogBackend``（写本地 JSONL，不依赖 skill_sdk）。
宿主已提供 ``skill_sdk`` 时，可在入口最早处 ``set_log_backend(SkillSdkLogBackend())``，仅通过 ``skill_sdk.Logger()`` 打日志。
换框架时新建 LogBase 子类，只实现 init_logger + emit_record，再改 _default_backend()。
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# 对外契约（抽象）：子类只须实现「身份初始化」+「如何把一条 record 交出去」
# ---------------------------------------------------------------------------


class LogBase(ABC):
    """
    对外稳定 API 的抽象：业务只通过模块级 init_logger / log_event / log_call / trace_call / serialize_full 调用。
    子类实现 init_logger、emit_record；路径/文件/SDK 等细节不得散落在模块顶层函数里。
    """

    def serialize_full(
        self,
        obj: Any,
        *,
        sort_keys: bool = False,
        ensure_ascii: bool = False,
        default: Callable[[Any], Any] | None = None,
    ) -> str:
        def _d(o: Any) -> str:
            return str(o)

        try:
            return json.dumps(obj, ensure_ascii=ensure_ascii, sort_keys=sort_keys, default=default or _d)
        except Exception:
            return str(obj)

    @abstractmethod
    def init_logger(self, module: str) -> None:
        """只接收模块标识；具体资源由子类创建。"""

    @abstractmethod
    def emit_record(self, record: dict[str, Any], *, level: str = "INFO") -> None:
        """子类唯一与「投递/持久化」相关的实现点。"""

    def log_event(
        self,
        function: str,
        event: str,
        *,
        level: str = "INFO",
        input: dict | None = None,
        output_summary: dict | None = None,
        latency_ms: float | None = None,
        success: bool | None = None,
        error: str = "",
        detail: str = "",
        request_body: Any = "",
        response_body: Any = "",
        result_body: Any = "",
    ) -> None:
        record = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(),
            "level": level,
            "module": self._module,
            "function": function,
            "event": event,
            "input": input or {},
            "output_summary": output_summary or {},
            "latency_ms": round(latency_ms, 3) if latency_ms is not None else None,
            "success": success,
            "error": error or "",
        }
        if detail:
            record["detail"] = detail
        if request_body != "":
            record["request_body"] = request_body
        if response_body != "":
            record["response_body"] = response_body
        if result_body != "":
            record["result_body"] = result_body
        self.emit_record(record, level=level)

    def log_call(
        self,
        function: str,
        *,
        input: dict,
        output_summary: dict,
        latency_ms: float,
        success: bool,
        error: str = "",
        result_body: str = "",
    ) -> None:
        record = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(),
            "level": "ERROR" if not success else "INFO",
            "module": self._module,
            "function": function,
            "event": "call_error" if not success else "call_complete",
            "input": input,
            "output_summary": {**(output_summary or {}), "success": success},
            "latency_ms": round(latency_ms, 3),
            "success": success,
            "error": error or "",
            "result_body": result_body,
        }
        self.emit_record(record, level=record["level"])

    @staticmethod
    def _input_from_call(func: Any, args: tuple, kwargs: dict) -> dict:
        try:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            return {k: v for k, v in bound.arguments.items()}
        except Exception:
            out: dict[str, Any] = {}
            if args:
                out["args"] = list(args)
            if kwargs:
                out.update(dict(kwargs))
            return out

    @staticmethod
    def _output_summary(result: Any) -> dict:
        if result is None:
            return {}
        if isinstance(result, dict):
            summary = {"keys": list(result.keys())[:15]}
            if "count" in result:
                summary["count"] = result.get("count")
            return summary
        return {"type": type(result).__name__}

    def trace_call(self, f: Any) -> Any:
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            full_input = self._input_from_call(f, args, kwargs)
            self.log_event(
                f.__name__, "call_start", input=full_input, output_summary={}, latency_ms=None, success=None, error=""
            )
            try:
                result = f(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                call_success = True
                call_error = ""
                if isinstance(result, dict) and "success" in result:
                    call_success = bool(result.get("success"))
                    if not call_success:
                        call_error = str(result.get("error") or "")
                out_summary = self._output_summary(result)
                out_summary["success"] = call_success
                self.log_event(
                    f.__name__,
                    "call_complete",
                    level="INFO" if call_success else "ERROR",
                    input=full_input,
                    output_summary=out_summary,
                    latency_ms=elapsed_ms,
                    success=call_success,
                    error=call_error,
                    result_body=self.serialize_full(result),
                )
                return result
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                self.log_call(
                    function=f.__name__,
                    input=full_input,
                    output_summary={},
                    latency_ms=elapsed_ms,
                    success=False,
                    error=str(e),
                    result_body="",
                )
                raise

        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            full_input = self._input_from_call(f, args, kwargs)
            self.log_event(
                f.__name__, "call_start", input=full_input, output_summary={}, latency_ms=None, success=None, error=""
            )
            try:
                result = await f(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                call_success = True
                call_error = ""
                if isinstance(result, dict) and "success" in result:
                    call_success = bool(result.get("success"))
                    if not call_success:
                        call_error = str(result.get("error") or "")
                out_summary = self._output_summary(result)
                out_summary["success"] = call_success
                self.log_event(
                    f.__name__,
                    "call_complete",
                    level="INFO" if call_success else "ERROR",
                    input=full_input,
                    output_summary=out_summary,
                    latency_ms=elapsed_ms,
                    success=call_success,
                    error=call_error,
                    result_body=self.serialize_full(result),
                )
                return result
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                self.log_call(
                    function=f.__name__,
                    input=full_input,
                    output_summary={},
                    latency_ms=elapsed_ms,
                    success=False,
                    error=str(e),
                    result_body="",
                )
                raise

        if asyncio.iscoroutinefunction(f):
            return functools.wraps(f)(_async_wrapper)
        return functools.wraps(f)(_sync_wrapper)


class JsonlFileLogBackend(LogBase):
    """默认实现：本地 JSONL + 可选 mirror 到 logging；所有路径/写文件逻辑仅在此类。"""

    def __init__(self) -> None:
        import logging as _logging

        self._logging = _logging
        self._module = ""
        self._log_dir: str | None = None
        self._logger = _logging.getLogger("skill_log")
        self._file_enabled = True
        self._sink: Callable[[str], None] | None = None
        self._emit_to_logger = False

    def init_logger(self, module: str) -> None:
        self._module = module
        self._log_dir = None
        self._file_enabled = True
        self._sink = None
        self._emit_to_logger = False
        self._logger.setLevel(self._logging.INFO)
        if not self._emit_to_logger:
            for _h in list(self._logger.handlers):
                if isinstance(_h, self._logging.StreamHandler):
                    self._logger.removeHandler(_h)
        elif not any(isinstance(h, self._logging.StreamHandler) for h in self._logger.handlers):
            h = self._logging.StreamHandler()
            h.setLevel(self._logging.INFO)
            self._logger.addHandler(h)

    def set_sink_for_tests(self, sink: Callable[[str], None] | None) -> None:
        self._sink = sink

    def _default_log_dir(self) -> str:
        """优先 SKILL_LOG_DIR；否则从本文件向上找仓库根（含 docs/ 或 .git），再使用 <根>/logs。"""
        override = os.environ.get("SKILL_LOG_DIR", "").strip()
        if override:
            return str(Path(override).expanduser().resolve())
        p = Path(__file__).resolve()
        for _ in range(16):
            p = p.parent
            if not p.is_dir() or p == p.parent:
                break
            if (p / "docs").is_dir() or (p / ".git").exists():
                return str((p / "logs").resolve())
        return str((Path.cwd() / "logs").resolve())

    def _today_file_path(self, event: str = "") -> str:
        base = self._log_dir or self._default_log_dir()
        Path(base).mkdir(parents=True, exist_ok=True)
        # 日志文件名按「本地日历日」滚动，避免 UTC 与本地差一天（如国内 22 号仍写成 api_log_20260321）
        today = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")
        ev = (event or "").strip().lower()
        if ev.startswith("api_"):
            filename = f"api_log_{today}.jsonl"
        else:
            filename = f"tool_log_{today}.jsonl"
        return os.path.join(base, filename)

    def _write_line(self, line: str, event: str = "") -> None:
        path = self._today_file_path(event=event)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _emit_line(self, line: str, level: str = "INFO", event: str = "") -> None:
        if not self._module:
            return
        if self._file_enabled:
            self._write_line(line, event=event)
        if self._sink is not None:
            try:
                self._sink(line)
            except Exception:
                pass
        if self._emit_to_logger:
            msg = line.rstrip()
            if level == "ERROR":
                self._logger.error(msg)
            else:
                self._logger.info(msg)

    def emit_record(self, record: dict[str, Any], *, level: str = "INFO") -> None:
        # 勿 deepcopy：trace_call 的 input 含 http_client 等，deepcopy 可能失败且异常被吞，导致 tool_log 无记录
        try:
            raw = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            self._emit_line(raw, level=level, event=str(record.get("event", "")))
        except Exception:
            pass


class SkillSdkLogBackend(LogBase):
    """
    仅使用 ``skill_sdk.Logger()``（info / warning / error）；每条记录为单行 JSON 字符串。
    不读文件、不写本地 JSONL。依赖宿主已安装 ``skill_sdk`` 并配置好 PYTHONPATH；``import`` 失败时 ``emit_record`` 静默跳过。
    """

    def __init__(self) -> None:
        self._module = ""

    def init_logger(self, module: str) -> None:
        self._module = module

    def emit_record(self, record: dict[str, Any], *, level: str = "INFO") -> None:
        try:
            from skill_sdk import Logger

            L = Logger()
            line = json.dumps(record, ensure_ascii=False, default=str)
            lvl = (level or "INFO").upper()
            if lvl == "ERROR":
                L.error("%s", line)
            elif lvl == "WARNING":
                L.warning("%s", line)
            else:
                L.info("%s", line)
        except Exception:
            pass


class ZxsfaLogBackend(LogBase):
    """
    使用 ``zxsfa.Logger`` 的类方法（``Logger.info`` / ``Logger.error`` / …）；每条记录为单行 JSON 字符串。
    **首次 ``emit_record`` 时**在方法内 ``from zxsfa import Logger``，避免未安装时影响默认 ``JsonlFileLogBackend`` 的模块加载。

    启用方式（在入口最早处，于 import 业务模块之前）::

        from <your_skill>.scripts.skill_logging._log import ZxsfaLogBackend, set_log_backend
        set_log_backend(ZxsfaLogBackend())
    """

    def __init__(self) -> None:
        self._module = ""
        self._Logger_cls: Any | None = None

    def _ensure_zxsfa_logger(self) -> Any:
        if self._Logger_cls is None:
            try:
                from zxsfa import Logger
            except ImportError as e:
                raise ImportError(
                    "未安装 zxsfa，无法使用 ZxsfaLogBackend；请安装依赖或继续使用 JsonlFileLogBackend"
                ) from e
            self._Logger_cls = Logger
        return self._Logger_cls

    def init_logger(self, module: str) -> None:
        self._module = module

    def emit_record(self, record: dict[str, Any], *, level: str = "INFO") -> None:
        Logger = self._ensure_zxsfa_logger()
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
            lvl = (level or "INFO").upper()
            if lvl == "ERROR":
                Logger.error(line)
            elif lvl == "WARNING" and hasattr(Logger, "warning"):
                Logger.warning(line)
            elif lvl == "DEBUG" and hasattr(Logger, "debug"):
                Logger.debug(line)
            else:
                Logger.info(line)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 模块级门面：默认后端可在此切换
# ---------------------------------------------------------------------------

_impl: LogBase | None = None


def _default_backend() -> LogBase:
    # 若默认改为 zxsfa：return ZxsfaLogBackend()
    return JsonlFileLogBackend()


def _get() -> LogBase:
    global _impl
    if _impl is None:
        _impl = _default_backend()
    return _impl


def set_log_backend(backend: LogBase | None) -> None:
    """替换整颗后端（单测或接入新框架时）；传 None 则下次恢复默认 JsonlFileLogBackend。"""
    global _impl
    _impl = backend


def init_logger(module: str) -> None:
    return _get().init_logger(module)


def set_log_sink_for_tests(sink: Callable[[str], None] | None) -> None:
    """仅供单元测试：将每条 JSONL 行副本交给 sink。"""
    b = _get()
    if isinstance(b, JsonlFileLogBackend):
        b.set_sink_for_tests(sink)


def emit_jsonl_record(record: dict, *, level: str = "INFO") -> None:
    return _get().emit_record(record, level=level)


def log_event(*args: Any, **kwargs: Any) -> None:
    return _get().log_event(*args, **kwargs)


def log_call(*args: Any, **kwargs: Any) -> None:
    return _get().log_call(*args, **kwargs)


def serialize_full(obj: Any, **kwargs: Any) -> str:
    return _get().serialize_full(obj, **kwargs)


def trace_call(f: Any) -> Any:
    return _get().trace_call(f)


def silence_stdlib_root_logging() -> None:
    """屏蔽标准库 ``logging`` 根 logger 的控制台输出（第三方库可能仍使用）；业务诊断请用 ``log_event``。"""
    import logging as _stdlib_logging

    _stdlib_logging.root.handlers = [_stdlib_logging.NullHandler()]


__all__ = [
    "LogBase",
    "JsonlFileLogBackend",
    "SkillSdkLogBackend",
    "ZxsfaLogBackend",
    "init_logger",
    "log_event",
    "log_call",
    "trace_call",
    "serialize_full",
    "emit_jsonl_record",
    "set_log_backend",
    "set_log_sink_for_tests",
    "silence_stdlib_root_logging",
]
