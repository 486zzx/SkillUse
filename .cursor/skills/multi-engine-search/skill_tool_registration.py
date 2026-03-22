"""
将 multi-engine-search 注册到 skill_sdk：params 与 aggregate_search.py CLI 一致。
示例：-k python --search-mode Fast --search-type 知识问答
"""

from __future__ import annotations

import argparse
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
from aggregate_search import run_aggregate_from_cli
from client.http_client import RequestsHttpClient


class MultiEngineSearchTool(skill_sdk.ToolInstance):
    """多引擎聚合搜索"""

    def Invoke(
        self,
        request: skill_sdk.CallRequest,
        context: skill_sdk.ToolContext,
    ) -> Optional[skill_sdk.CallResponse]:
        skill_sdk.Logger().info("Invoke")
        try:
            argv = split_params_to_argv(request.params)
            parser = argparse.ArgumentParser()
            parser.add_argument("--search-type", default=None, metavar="TYPE")
            parser.add_argument("--search-mode", default="Fast", metavar="MODE")
            parser.add_argument(
                "-k",
                "--keywords",
                action="append",
                default=None,
                metavar="KEYWORD",
            )
            args = parser.parse_args(argv)
            client = request.http_client or RequestsHttpClient()
            out, _exit_code = run_aggregate_from_cli(
                search_type_raw=args.search_type,
                search_mode_arg=args.search_mode,
                keywords=args.keywords,
                http_client=client,
            )
            return response_from_result(out)
        except Exception as e:
            skill_sdk.Logger().error("Invoke failed: %s", e)
            return skill_sdk.CallResponse(
                message=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False),
                code=-1,
            )


__all__ = ["MultiEngineSearchTool"]
