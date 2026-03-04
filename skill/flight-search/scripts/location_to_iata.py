#!/usr/bin/env python3
"""
地点 → IATA 三字码。读取 city_map.json、province_map.json、airport_list.json、nearest_airport_map.json。
优先级：机场 > 城市（city_map）> 城市最近机场（nearest_airport_map）> 省份。数据目录由 FLIGHT_DATA_DIR 指定。
用法：python location_to_iata.py "上海" "北京" ；或 --json "[\"西安\",\"广东\"]"
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 默认数据目录：本 skill 下的 references（可通过环境变量 FLIGHT_DATA_DIR 覆盖）
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = SKILL_DIR / "references"


def _ensure_utf8_io() -> None:
    """避免 Windows 控制台 GBK 导致 print 报错或乱码，强制 stdout/stderr 使用 UTF-8。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def get_data_dir() -> Path:
    return Path(os.environ.get("FLIGHT_DATA_DIR", str(DEFAULT_DATA_DIR)))


def load_maps(data_dir: Path) -> tuple[dict, dict]:
    data_dir = Path(data_dir)
    with open(data_dir / "city_map.json", "r", encoding="utf-8") as f:
        city_map = json.load(f)
    with open(data_dir / "province_map.json", "r", encoding="utf-8") as f:
        province_map = json.load(f)
    return city_map, province_map


def load_nearest_airport_map(data_dir: Path) -> dict[str, str]:
    """城市（无机场）→ 最近机场三字码。从 nearest_airport_map.json 读取，格式 [{"城市":"昌吉","机场三字码":"URC"}, ...]。"""
    path = Path(data_dir) / "nearest_airport_map.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, list):
        return {}
    out = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        city = (item.get("城市") or "").strip()
        code = (item.get("机场三字码") or "").strip().upper()
        if not city or len(code) != 3 or not code.isalpha():
            continue
        out[city] = code
    return out


def load_airport_map(data_dir: Path) -> dict[str, str]:
    """机场名 → 三字码。从 airport_list.json 读取（格式 [{"iata":"PVG","name_zh":"上海浦东国际机场"}, ...]）。"""
    data_dir = Path(data_dir)
    try:
        with open(data_dir / "city_map.json", "r", encoding="utf-8") as f:
            city_map = json.load(f)
    except Exception:
        city_map = {}
    path = data_dir / "airport_list.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            list_data = json.load(f)
    except Exception:
        return {}
    if not isinstance(list_data, list):
        return {}
    out = {}
    for item in list_data:
        if not isinstance(item, dict):
            continue
        code_s = (item.get("iata") or "").strip().upper()
        name_s = (item.get("name_zh") or "").strip()
        if len(code_s) != 3 or not code_s.isalpha() or not name_s:
            continue
        out[name_s] = code_s
        for suffix in ("国际机场", "机场"):
            if name_s.endswith(suffix):
                short = name_s[: -len(suffix)].strip()
                if short and short not in out:
                    out[short] = code_s
                city_prefix = None
                for city in city_map:
                    if short.startswith(city) and (city_prefix is None or len(city) > len(city_prefix)):
                        city_prefix = city
                if city_prefix and len(short) > len(city_prefix):
                    rest = short[len(city_prefix):]
                    if rest not in out:
                        out[rest] = code_s
                    if suffix == "国际机场" and len(rest) >= 2:
                        alias = rest + "国际机场"
                        if alias not in out:
                            out[alias] = code_s
                break
    return out


def resolve_iata(
    text: str,
    city_map: dict,
    province_map: dict,
    airport_map: dict | None = None,
    nearest_airport_map: dict | None = None,
) -> dict:
    """
    将单个地点文本解析为 IATA 三字码。
    优先级：机场 > 城市（city_map）> 城市最近机场（nearest_airport_map）> 省份（省会）。
    返回 {"iata": "SHA", "source": "airport|city|province|literal", "raw": "..."}
    """
    raw = text.strip()
    if not raw:
        return {"iata": "", "source": "empty", "raw": raw}

    # 1. 已是三字码（3 位英文字母 A-Z，避免「石家庄」等三字中文被误判为 literal）
    if len(raw) == 3 and raw.isascii() and raw.isalpha():
        return {"iata": raw.upper(), "source": "literal", "raw": raw}

    # 2. 机场（最具体，优先）
    if airport_map and raw in airport_map:
        return {"iata": airport_map[raw], "source": "airport", "raw": raw}

    # 3. 城市（有机场的城市，city_map）
    if raw in city_map:
        return {"iata": city_map[raw], "source": "city", "raw": raw}

    # 4. 城市最近机场（无机场城市，nearest_airport_map）
    if nearest_airport_map and raw in nearest_airport_map:
        return {"iata": nearest_airport_map[raw], "source": "city", "raw": raw}

    # 5. 省份 → 省会（范围最大，最后）
    if raw in province_map:
        return {"iata": province_map[raw], "source": "province", "raw": raw}

    # 6. 模糊：机场 > 城市 > 最近机场城市 > 省份
    if airport_map:
        for name, code in airport_map.items():
            if len(name) >= 2 and (name in raw or raw in name):
                return {"iata": code, "source": "airport_fuzzy", "raw": raw}
    for name, code in city_map.items():
        if name in raw or raw in name:
            return {"iata": code, "source": "city_fuzzy", "raw": raw}
    if nearest_airport_map:
        for name, code in nearest_airport_map.items():
            if name in raw or raw in name:
                return {"iata": code, "source": "city_fuzzy", "raw": raw}
    for name, code in province_map.items():
        if name in raw or raw in name:
            return {"iata": code, "source": "province_fuzzy", "raw": raw}

    return {"iata": "", "source": "not_found", "raw": raw}


def main() -> None:
    _ensure_utf8_io()
    data_dir = get_data_dir()
    if not (data_dir / "city_map.json").exists():
        print(json.dumps({"error": f"数据目录不存在或缺少 city_map.json: {data_dir}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    city_map, province_map = load_maps(data_dir)
    airport_map = load_airport_map(data_dir) or None
    nearest_airport_map = load_nearest_airport_map(data_dir) or None

    if "--json" in sys.argv:
        i = sys.argv.index("--json")
        try:
            json_str = sys.argv[i + 1].strip()
            texts = json.loads(json_str)
        except (IndexError, json.JSONDecodeError):
            texts = []
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        texts = [t.strip().strip('"') for t in sys.argv[1:] if not t.startswith("-") and t.strip()]
    else:
        print(json.dumps({"error": "缺少输入：请用位置参数传入地点，或 --json 传入 JSON 数组"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    if not texts:
        print(json.dumps({"error": "缺少输入：请用位置参数传入地点，或 --json 传入 JSON 数组"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    results = []
    for t in texts:
        r = resolve_iata(t, city_map, province_map, airport_map, nearest_airport_map)
        results.append(r)

    if len(results) == 1:
        print(json.dumps(results[0], ensure_ascii=False))
    else:
        print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
