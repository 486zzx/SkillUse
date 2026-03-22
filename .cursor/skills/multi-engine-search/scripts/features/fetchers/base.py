"""
Fetcher 协议与注册表。支持几十～上百个搜索源：通过注册 + 配置启用列表，aggregate 只遍历当前启用的引擎。
每个 fetcher 自行定义默认的 max_results、timeout，便于按引擎设置不同参数。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# 从 scripts 根目录加载统一配置（入口为 scripts/aggregate_search.py 时 path 含 scripts）
try:
    import config as _config
except ImportError:
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    import config as _config


@runtime_checkable
class Fetcher(Protocol):
    """搜索引擎抽象：输入 query，异步返回 (source_id, items, error)。"""

    async def fetch(
        self,
        query: str,
        *,
        max_results: int = 5,
        timeout: float = 10,
        client: Any,
    ) -> tuple[str, list[dict], str]:
        """
        执行搜索（异步）。
        max_results: 单次最多返回条数，默认由各实现指定（如 5）。
        timeout: 请求超时秒数，默认由各实现指定（如 0.5 表示 500ms）。
        返回 (source_id, items, error)。
        item 至少含 title, url, content, source；可选 score, date。
        """
        ...


class Registry:
    """注册表：按 id 注册 Fetcher，按配置返回当前启用的列表。"""

    _fetchers: dict[str, Fetcher]
    _enabled_ids: list[str] | None  # None 表示用默认或环境变量

    def __init__(self) -> None:
        self._fetchers = {}
        self._enabled_ids = None

    def register(self, id: str, fetcher: Fetcher) -> None:
        self._fetchers[id] = fetcher

    def set_enabled(self, ids: list[str]) -> None:
        """显式设置启用列表（测试或配置用）。"""
        self._enabled_ids = ids

    def get_enabled(self, ids_override: list[str] | None = None) -> list[Fetcher]:
        """返回当前启用的 Fetcher 实例列表，顺序与启用列表一致。"""
        if ids_override is not None:
            ids = ids_override
        elif self._enabled_ids is not None:
            ids = self._enabled_ids
        else:
            ids = _config.get_aggregate_engines()
        return [self._fetchers[id] for id in ids if id in self._fetchers]


# 全局单例，各引擎模块 import 后调用 registry.register(...)
registry = Registry()


def get_fetchers(engine_ids: list[str] | None = None):
    """返回当前启用的 Fetcher 实例列表（顺序与 AGGREGATE_ENGINES 或默认一致）。"""
    return registry.get_enabled(ids_override=engine_ids)


# 触发各引擎注册（import 时执行 registry.register）
from . import baidu  # noqa: F401
from . import tavily  # noqa: F401
from . import zhipu  # noqa: F401
from . import bocha  # noqa: F401
