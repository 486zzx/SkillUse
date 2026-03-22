"""
Skill 内置 HTTP 客户端（独立副本）。
提供统一异步 get/post，返回 (status 字符串, body dict)。
具体传输由 RequestsHttpClient（内置 requests）或后续 ExtHttpClient 等实现。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse


def _normalize_query_params(params: dict[str, Any]) -> dict[str, Any]:
    """
    规范化 GET query：去掉值为 None 的项（表示不传该参数）；list/tuple 内的 None 一并去掉。
    若过滤后无键，返回 {}。
    """
    out: dict[str, Any] = {}
    for k, v in params.items():
        if k is None:
            continue
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            seq = [x for x in v if x is not None]
            if not seq:
                continue
            out[k] = seq
        else:
            out[k] = v
    return out


class HttpClientBase(ABC):
    @abstractmethod
    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10,
    ) -> tuple[str, dict[str, Any]]:
        ...

    @abstractmethod
    async def post(
        self,
        url: str,
        *,
        data: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10,
    ) -> tuple[str, dict[str, Any]]:
        ...


def _build_url_with_params(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    clean = _normalize_query_params(params)
    if not clean:
        return url
    query = urlencode(clean, doseq=True)
    parsed = urlparse(url)
    new_query = f"{parsed.query}&{query}" if parsed.query else query
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


class RequestsHttpClient(HttpClientBase):
    """使用 requests 的实现；requests 仅在实例化本类时导入。"""

    def __init__(self, manual_url_encode: bool = False) -> None:
        try:
            import requests as _requests
        except ImportError as e:
            raise ImportError(
                "使用 RequestsHttpClient 需要安装 requests: pip install requests"
            ) from e
        self._requests = _requests
        self._manual_url_encode = manual_url_encode

    @staticmethod
    def _body_from_response(r: Any) -> dict[str, Any]:
        """将响应体规范为 dict：JSON 对象原样；数组等包为 _json；非 JSON 为 {text: ...}。"""
        try:
            data = r.json()
            if isinstance(data, dict):
                return data
            return {"_json": data}
        except Exception:
            return {"text": r.text or ""}

    @staticmethod
    def _tuple_from_response(r: Any) -> tuple[str, dict[str, Any]]:
        return str(r.status_code), RequestsHttpClient._body_from_response(r)

    def _get_url_and_kwargs(
        self,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        timeout: float,
    ) -> tuple[str, dict]:
        if not params:
            return url, {"headers": headers or {}, "timeout": timeout}
        if self._manual_url_encode:
            full_url = _build_url_with_params(url, params)
            return full_url, {"headers": headers or {}, "timeout": timeout}
        clean = _normalize_query_params(params)
        if not clean:
            return url, {"headers": headers or {}, "timeout": timeout}
        return url, {"params": clean, "headers": headers or {}, "timeout": timeout}

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10,
    ) -> tuple[str, dict[str, Any]]:
        request_url, kwargs = self._get_url_and_kwargs(url, params, headers, timeout)
        r = await asyncio.to_thread(self._requests.get, request_url, **kwargs)
        return self._tuple_from_response(r)

    async def post(
        self,
        url: str,
        *,
        data: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10,
    ) -> tuple[str, dict[str, Any]]:
        r = await asyncio.to_thread(
            self._requests.post,
            url,
            data=data,
            headers=headers or {},
            timeout=timeout,
        )
        return self._tuple_from_response(r)


class ExtHttpClient(RequestsHttpClient):
    """占位：URL 手工编码。后续若改为非 requests 传输，应继承 HttpClientBase 自行实现 get/post。"""

    def __init__(self) -> None:
        super().__init__(manual_url_encode=True)
