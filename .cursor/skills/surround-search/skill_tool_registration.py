"""
将 surround-search 注册到 skill_sdk：params 与 run_surround_search.py 一致。
示例：三里屯 --keyword 餐厅 --city 北京
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

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
from features.surround_service import normalize_surround_contract, surround_search


class SurroundSearchTool(skill_sdk.ToolInstance):
    """周边搜索"""

    def Invoke(
        self,
        request: skill_sdk.CallRequest,
        context: skill_sdk.ToolContext,
    ) -> Optional[skill_sdk.CallResponse]:
        skill_sdk.Logger().info("Invoke")
        try:
            argv = split_params_to_argv(request.params)
            parser = argparse.ArgumentParser()
            parser.add_argument("location", nargs="?", default="")
            parser.add_argument("--city", default=None)
            parser.add_argument("--keyword", default=None)
            args = parser.parse_args(argv)
            client = request.http_client or RequestsHttpClient()
            out_raw = asyncio.run(
                surround_search(
                    args.location,
                    args.keyword or "",
                    args.city,
                    http_client=client,
                )
            )
            result = normalize_surround_contract(
                out_raw,
                address=args.location or "",
                keywords=args.keyword or "",
                city=args.city,
            )
            return response_from_result(result)
        except Exception as e:
            skill_sdk.Logger().error("Invoke failed: %s", e)
            return skill_sdk.CallResponse(
                message=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
                code=-1,
            )


__all__ = ["SurroundSearchTool"]
