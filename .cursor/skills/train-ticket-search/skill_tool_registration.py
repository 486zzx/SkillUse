"""
将 train-ticket-search 注册到 skill_sdk：params 与 run_train_search.py CLI 一致，调用 run_train_cli。
"""

from __future__ import annotations

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
from run_train_search import run_train_cli


class TrainTicketSearchTool(skill_sdk.ToolInstance):
    """火车票查询：params 例如：上海 北京 --departure-time 2026-03-23"""

    def Invoke(
        self,
        request: skill_sdk.CallRequest,
        context: skill_sdk.ToolContext,
    ) -> Optional[skill_sdk.CallResponse]:
        skill_sdk.Logger().info("Invoke")
        try:
            argv = split_params_to_argv(request.params)
            client = request.http_client
            result = asyncio.run(run_train_cli(argv, http_client=client))
            return response_from_result(result)
        except Exception as e:
            skill_sdk.Logger().error("Invoke failed: %s", e)
            return skill_sdk.CallResponse(
                message=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
                code=-1,
            )


__all__ = ["TrainTicketSearchTool"]
