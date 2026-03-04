"""
Fetchers：当前启用的搜索引擎列表，由注册表 + 配置决定。
新增引擎 = 新文件实现 Fetcher + 在此 import 触发注册（或按配置按名加载）。
"""

from __future__ import annotations

from . import baidu  # noqa: F401 - 触发注册
from . import tavily  # noqa: F401 - 触发注册
from .base import registry


def get_fetchers():
    """返回当前启用的 Fetcher 实例列表（顺序与 AGGREGATE_ENGINES 或默认一致）。"""
    return registry.get_enabled()
