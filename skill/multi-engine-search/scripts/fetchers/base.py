"""
Fetcher 协议与注册表。支持几十～上百个搜索源：通过注册 + 配置启用列表，aggregate 只遍历当前启用的引擎。
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetcher(Protocol):
    """搜索引擎抽象：输入 query，返回 (source_id, items, error)。"""

    def fetch(self, query: str) -> tuple[str, list[dict], str]:
        """
        执行搜索。
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

    def get_enabled(self) -> list[Fetcher]:
        """返回当前启用的 Fetcher 实例列表，顺序与启用列表一致。"""
        if self._enabled_ids is not None:
            ids = self._enabled_ids
        else:
            env = os.environ.get("AGGREGATE_ENGINES", "").strip()
            ids = [x.strip() for x in env.split(",") if x.strip()] if env else ["baidu", "tavily"]
        return [self._fetchers[id] for id in ids if id in self._fetchers]


# 全局单例，各引擎模块 import 后调用 registry.register(...)
registry = Registry()
