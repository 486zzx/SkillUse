"""
将 flight-search 注册到 skill_sdk：解析 CallRequest.params（与 run_flight_search.py CLI 一致），调用 search_flights。
使用前请将仓库根目录加入 PYTHONPATH（以便 import skill_sdk / skill_tool_helpers），或由 skill_tool_helpers.find_repo_root 自动注入。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# bootstrap：仓库根加入 sys.path
_repo = Path(__file__).resolve()
while _repo.parent != _repo:
    if (_repo / "skill_sdk" / "__init__.py").is_file():
        if str(_repo) not in sys.path:
            sys.path.insert(0, str(_repo))
        break
    _repo = _repo.parent
else:
    raise RuntimeError("skill_tool_registration: 未找到仓库根（skill_sdk）")

_SCRIPT = Path(__file__).resolve().parent / "scripts"
_s = str(_SCRIPT)
if _s in sys.path:
    sys.path.remove(_s)
sys.path.insert(0, _s)

import skill_sdk
from skill_tool_helpers import (
    clear_skill_import_shadows,
    response_from_result,
    split_params_to_argv,
)

clear_skill_import_shadows()
from client.http_client import RequestsHttpClient
from features.flight_search import config, search_flights
from run_flight_search import parse_flight_cli_args


class FlightSearchTool(skill_sdk.ToolInstance):
    """航班查询：params 与 CLI 一致，例如：上海 北京 --departure-time '["2026-03-23 00:00","2026-03-23 23:59"]'"""

    def Invoke(
        self,
        request: skill_sdk.CallRequest,
        context: skill_sdk.ToolContext,
    ) -> Optional[skill_sdk.CallResponse]:
        skill_sdk.Logger().info("Invoke")
        try:
            argv = split_params_to_argv(request.params)
            origin, destination, departure_range, arrival_range, options = (
                parse_flight_cli_args(argv)
            )
            if options.get("direct_only") is not None:
                config.DIRECT_ONLY = bool(options.get("direct_only"))
            if "flights_format" in options:
                config.FLIGHTS_AS_MARKDOWN = (
                    options.get("flights_format", "markdown").strip().lower() != "json"
                )
            client = request.http_client or RequestsHttpClient()
            result = asyncio.run(
                search_flights(
                    origin=origin,
                    destination=destination,
                    departure_time=departure_range,
                    arrival_time=arrival_range if arrival_range else None,
                    max_price=options.get("max_price"),
                    sort_by=options.get("sort_by"),
                    http_client=client,
                )
            )
            return response_from_result(result)
        except Exception as e:
            skill_sdk.Logger().error("Invoke failed: %s", e)
            return skill_sdk.CallResponse(
                message=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
                code=-1,
            )


__all__ = ["FlightSearchTool"]
