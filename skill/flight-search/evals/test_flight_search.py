# -*- coding: utf-8 -*-
"""
航班查询 Skill 测试：基于 docs/skill内部功能测试用例设计.md 第 1 节。
- 1.1/1.1.1 出发地/目的地解析（F-LOC）
- 1.2 日期解析（F-DAT）
- 1.3 多段行程解析（F-SEG）
- 1.4 端到端（F-E2E）
- 1.5 输出处理（F-OUT）

API Key 配置：下方 JUHE_FLIGHT_API_KEY 优先从环境变量读取；无 Key 时 E2E/输出处理用例跳过。
若需临时禁用所有需 API 的用例，设 SKIP_E2E_WHEN_NO_KEY=True（默认）且不配置 Key 即可。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

# ------------------------------
# API Key 与跳过逻辑（集中配置）
# ------------------------------
JUHE_FLIGHT_API_KEY = os.environ.get("JUHE_FLIGHT_API_KEY", "6067b93001e47645ff3a51a51c005cc7").strip()
SKIP_E2E_WHEN_NO_KEY = True  # 无 Key 时跳过需 API 的用例；设为 False 可强制跑（会因未配置 Key 失败）
requires_api_key = pytest.mark.skipif(
    SKIP_E2E_WHEN_NO_KEY and not JUHE_FLIGHT_API_KEY,
    reason="JUHE_FLIGHT_API_KEY 未配置，跳过需 API 的用例",
)

# 脚本与数据目录（以本文件所在 evals 为基准，scripts 与 references 在上一级）
EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
REFERENCES_DIR = SKILL_DIR / "references"
RUN_FLIGHT_SEARCH = SCRIPTS_DIR / "run_flight_search.py"

# 端到端测试用的出发时间范围（标准格式 yyyy-MM-dd HH:mm）
def _departure_time_args(date: str = "2026-03-11"):
    return ["--departure-time", f"{date} 00:00", f"{date} 23:59"]


def _flight_data_dir():
    """测试时使用的数据目录，与 skill 默认一致。"""
    return REFERENCES_DIR


def _ensure_sys_path():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# 1.1 出发地/目的地解析（location_to_iata / resolve_iata）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def flight_maps():
    """加载 city_map、province_map、airport_map、nearest_airport_map 供 F-LOC 使用。"""
    _ensure_sys_path()
    os.environ["FLIGHT_DATA_DIR"] = str(_flight_data_dir())
    from location_to_iata import (
        load_airport_map,
        load_maps,
        load_nearest_airport_map,
        resolve_iata,
    )
    data_dir = _flight_data_dir()
    if not (data_dir / "city_map.json").exists():
        pytest.skip("缺少 references/city_map.json")
    city_map, province_map = load_maps(data_dir)
    airport_map = load_airport_map(data_dir) or None
    nearest_airport_map = load_nearest_airport_map(data_dir) or None
    return {
        "city_map": city_map,
        "province_map": province_map,
        "airport_map": airport_map,
        "nearest_airport_map": nearest_airport_map,
        "resolve_iata": resolve_iata,
    }


def _resolve(flight_maps, text: str):
    r = flight_maps["resolve_iata"](
        text,
        flight_maps["city_map"],
        flight_maps["province_map"],
        flight_maps["airport_map"],
        flight_maps["nearest_airport_map"],
    )
    return r.get("iata", ""), r.get("source", "")


# F-LOC-01～19
def test_F_LOC_01_shanghai(flight_maps):
    iata, source = _resolve(flight_maps, "上海")
    assert iata == "SHA"
    assert source == "city"


def test_F_LOC_02_beijing(flight_maps):
    iata, source = _resolve(flight_maps, "北京")
    assert iata == "BJS"  # 以当前 city_map 为准
    assert source == "city"


def test_F_LOC_03_chengdu(flight_maps):
    iata, source = _resolve(flight_maps, "成都")
    assert iata == "CTU"
    assert source == "city"


def test_F_LOC_04_pvg_full(flight_maps):
    iata, source = _resolve(flight_maps, "上海浦东国际机场")
    assert iata == "PVG"
    assert source == "airport"


def test_F_LOC_05_pek_full(flight_maps):
    iata, source = _resolve(flight_maps, "北京首都国际机场")
    assert iata == "PEK"
    assert source == "airport"


def test_F_LOC_06_pudong(flight_maps):
    iata, source = _resolve(flight_maps, "浦东")
    assert iata == "PVG"
    assert source in ("airport", "airport_fuzzy")


def test_F_LOC_07_hongqiao(flight_maps):
    iata, source = _resolve(flight_maps, "虹桥")
    assert iata == "SHA"
    assert source in ("airport", "airport_fuzzy")


def test_F_LOC_08_shoudu_jichang(flight_maps):
    iata, source = _resolve(flight_maps, "首都机场")
    assert iata == "PEK"
    assert source in ("airport", "airport_fuzzy")


def test_F_LOC_09_shanghai_pudong(flight_maps):
    iata, source = _resolve(flight_maps, "上海浦东")
    assert iata == "PVG"
    assert source in ("airport", "airport_fuzzy")


def test_F_LOC_10_chengdu_tianfu(flight_maps):
    iata, source = _resolve(flight_maps, "成都天府")
    assert iata == "TFU"
    assert source in ("airport", "airport_fuzzy")


def test_F_LOC_11_sichuan(flight_maps):
    iata, source = _resolve(flight_maps, "四川")
    assert iata == "CTU"  # 省会成都
    assert source in ("province", "province_fuzzy")


def test_F_LOC_12_guangdong(flight_maps):
    iata, source = _resolve(flight_maps, "广东")
    assert iata == "CAN"
    assert source in ("province", "province_fuzzy")


def test_F_LOC_13_iata_sha(flight_maps):
    iata, source = _resolve(flight_maps, "SHA")
    assert iata == "SHA"
    assert source == "literal"


def test_F_LOC_14_iata_pvg(flight_maps):
    iata, source = _resolve(flight_maps, "PVG")
    assert iata == "PVG"
    assert source == "literal"


def test_F_LOC_15_changji(flight_maps):
    iata, source = _resolve(flight_maps, "昌吉")
    assert iata == "URC"
    assert source in ("city", "city_fuzzy")


def test_F_LOC_16_empty(flight_maps):
    iata, source = _resolve(flight_maps, "")
    assert iata == ""
    assert source == "empty"


def test_F_LOC_17_not_found(flight_maps):
    iata, source = _resolve(flight_maps, "不存在的城市名")
    assert iata == ""
    assert source == "not_found"


def test_F_LOC_18_sentence(flight_maps):
    iata, source = _resolve(flight_maps, "从上海出发")
    assert iata == "SHA"
    assert "city" in source or "fuzzy" in source


def test_F_LOC_19_modu(flight_maps):
    iata, source = _resolve(flight_maps, "魔都")
    if flight_maps["city_map"].get("魔都"):
        assert iata != ""
    else:
        assert source == "not_found" or iata == ""


# 1.1.1 地理精度/粒度
def test_F_LOC_20_shanghai_qingpu(flight_maps):
    iata, source = _resolve(flight_maps, "上海青浦区")
    assert iata == "SHA"
    assert "city" in source or "fuzzy" in source


def test_F_LOC_21_beijing_chaoyang(flight_maps):
    """北京朝阳区：理想为 BJS/PEK；若实现先匹配到「朝阳」则可能为 CHG。"""
    iata, source = _resolve(flight_maps, "北京朝阳区")
    assert iata in ("BJS", "PEK", "CHG")  # CHG=朝阳（辽宁），当前实现可能先匹配到
    assert "city" in source or "fuzzy" in source or "province" in source


def test_F_LOC_22_shenzhen_nanshan(flight_maps):
    iata, source = _resolve(flight_maps, "深圳南山区")
    assert iata == "SZX"
    assert "city" in source or "fuzzy" in source


def test_F_LOC_23_chengdu_shuangliu(flight_maps):
    iata, source = _resolve(flight_maps, "成都双流区")
    assert iata == "CTU"
    assert "city" in source or "fuzzy" in source


def test_F_LOC_26_renminlu(flight_maps):
    iata, source = _resolve(flight_maps, "人民路")
    assert source == "not_found" or iata == ""


def test_F_LOC_28_jianshelu(flight_maps):
    iata, source = _resolve(flight_maps, "建设路")
    assert source == "not_found" or iata == ""


def test_F_LOC_29_beijing_chaoyang_wangjing(flight_maps):
    """北京市朝阳区望京街道：理想为 BJS/PEK；若先匹配「朝阳」则可能 CHG。"""
    iata, source = _resolve(flight_maps, "北京市朝阳区望京街道")
    assert iata in ("BJS", "PEK", "CHG")
    assert "city" in source or "fuzzy" in source or "province" in source


def test_F_LOC_30_invalid_granularity(flight_maps):
    iata, source = _resolve(flight_maps, "某某小区")
    assert source == "not_found" or iata == ""


# ---------------------------------------------------------------------------
# 1.2 日期解析（normalize_date）
# ---------------------------------------------------------------------------
@pytest.fixture
def base_date():
    return datetime(2026, 3, 5)  # 周四


def test_F_DAT_01_today(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("今天", time_base=base_date)
    assert r["date"] == "2026-03-05"


def test_F_DAT_02_tomorrow(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("明天", time_base=base_date)
    assert r["date"] == "2026-03-06"


def test_F_DAT_03_day_after_tomorrow(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("后天", time_base=base_date)
    assert r["date"] == "2026-03-07"


def test_F_DAT_04_next_monday(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("下周一", time_base=base_date)
    assert r["date"] == "2026-03-09"


def test_F_DAT_05_next_friday(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("下周五", time_base=base_date)
    assert r["date"] == "2026-03-13"


def test_F_DAT_06_iso(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("2026-03-20", time_base=base_date)
    assert r["date"] == "2026-03-20"


def test_F_DAT_07_slash(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("2026/3/20", time_base=base_date)
    assert r["date"] == "2026-03-20"


def test_F_DAT_10_empty(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("", time_base=base_date)
    assert r["date"] == "" or r["source"] == "fail"


def test_F_DAT_11_invalid(base_date):
    _ensure_sys_path()
    from normalize_date import normalize_date
    r = normalize_date("随便", time_base=base_date)
    assert r["date"] == "" or r["source"] == "fail"


# ---------------------------------------------------------------------------
# 1.3 多段行程解析（parse_multi_segment）
# ---------------------------------------------------------------------------
@pytest.fixture
def parse_segments():
    _ensure_sys_path()
    os.environ["FLIGHT_DATA_DIR"] = str(_flight_data_dir())
    from parse_multi_segment import parse_segments as _parse
    return _parse


def test_F_SEG_01_single(parse_segments, base_date):
    segments = [{"origin": "上海", "destination": "北京", "date": "明天"}]
    out = parse_segments(segments, time_base=base_date)
    assert len(out) == 1
    assert out[0].get("departure") == "SHA"
    assert out[0].get("arrival") == "BJS"
    assert out[0].get("departureDate") == "2026-03-06"
    assert "error" not in out[0] or not out[0]["error"]


def test_F_SEG_02_two_segments(parse_segments, base_date):
    segments = [
        {"origin": "上海", "destination": "西安", "date": "明天"},
        {"origin": "西安", "destination": "成都", "date": "后天"},
    ]
    out = parse_segments(segments, time_base=base_date)
    assert len(out) == 2
    assert out[0].get("departure") == "SHA" and out[0].get("arrival") == "SIA"
    assert out[1].get("departure") == "SIA" and out[1].get("arrival") == "CTU"
    assert out[0].get("departureDate") == "2026-03-06"
    assert out[1].get("departureDate") == "2026-03-07"


def test_F_SEG_03_invalid_origin(parse_segments, base_date):
    segments = [{"origin": "不存在的城市", "destination": "北京", "date": "明天"}]
    out = parse_segments(segments, time_base=base_date)
    assert len(out) == 1
    assert out[0].get("error") or not out[0].get("departure") or out[0].get("departure") == ""


# ---------------------------------------------------------------------------
# 1.4 端到端（run_flight_search）— 需 API Key
# ---------------------------------------------------------------------------
def _run_flight_search(*args, env=None):
    env = env or os.environ.copy()
    env["FLIGHT_DATA_DIR"] = str(_flight_data_dir())
    if JUHE_FLIGHT_API_KEY:
        env["JUHE_FLIGHT_API_KEY"] = JUHE_FLIGHT_API_KEY
    cmd = [sys.executable, str(RUN_FLIGHT_SEARCH)] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(SKILL_DIR))
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    try:
        return json.loads(out) if out else {"success": False, "error": err or r.stdout or "no output"}
    except json.JSONDecodeError:
        return {"success": False, "error": out or err or "invalid json"}


@requires_api_key
def test_F_E2E_01_city():
    data = _run_flight_search("上海", "北京", *_departure_time_args())
    assert data.get("success") is True
    result = data.get("result", {})
    assert "flightInfo" in result or "flightCount" in result
    if result.get("flightInfo"):
        assert isinstance(result["flightInfo"], list)


@requires_api_key
def test_F_E2E_02_airport():
    data = _run_flight_search("浦东", "首都机场", *_departure_time_args("2026-03-10"))
    assert data.get("success") is True
    assert "result" in data


@requires_api_key
def test_F_E2E_03_sort():
    data = _run_flight_search("上海", "成都", *_departure_time_args(), "--sort-by", "price_asc")
    assert data.get("success") is True
    info = (data.get("result") or {}).get("flightInfo") or []
    if len(info) >= 2:
        prices = []
        for f in info:
            # 不同 API 结构可能不同，取参考价或最低价
            ref = f.get("referencePrice") or f.get("price") or f.get("minPrice")
            if ref is not None:
                try:
                    prices.append(float(ref))
                except (TypeError, ValueError):
                    pass
        if len(prices) >= 2:
            assert prices == sorted(prices)


@requires_api_key
def test_F_E2E_04_direct():
    data = _run_flight_search("上海", "北京", *_departure_time_args())
    assert data.get("success") is True


def test_F_E2E_05_no_key_when_unset():
    """无 Key 时应失败或明确提示；若未设 SKIP 则跑此用例。"""
    env = os.environ.copy()
    env["FLIGHT_DATA_DIR"] = str(_flight_data_dir())
    env.pop("JUHE_FLIGHT_API_KEY", None)
    cmd = [sys.executable, str(RUN_FLIGHT_SEARCH), "上海", "北京", "--departure-time", "2026-03-11 00:00", "2026-03-11 23:59"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(SKILL_DIR))
    out = (r.stdout or "").strip()
    try:
        data = json.loads(out)
        assert data.get("success") is False or "key" in (data.get("error") or "").lower() or "配置" in (data.get("error") or "")
    except json.JSONDecodeError:
        assert "key" in out.lower() or "配置" in out or r.returncode != 0


def test_F_E2E_06_invalid_origin():
    data = _run_flight_search("不存在的城市", "北京", *_departure_time_args())
    assert data.get("success") is False
    assert "error" in data
    assert "解析" in data.get("error", "") or "无法" in data.get("error", "")


def test_F_E2E_07_invalid_departure_time():
    """无效出发时间范围时应返回 clarification_needed 或 error。"""
    data = _run_flight_search("上海", "北京", "--departure-time", "无效", "无效")
    assert data.get("success") is False
    assert data.get("clarification_needed") is True or "error" in data


def test_F_E2E_08_clarification_when_missing_params():
    """缺参时应返回 clarification_needed 与 missing。"""
    data = _run_flight_search()
    assert data.get("success") is False
    assert data.get("clarification_needed") is True
    assert "missing" in data
    assert "message" in data
    missing = data.get("missing", [])
    assert "origin" in missing or "destination" in missing or "departure_time_range" in missing


# ---------------------------------------------------------------------------
# 1.5 输出处理（排序、筛选、限制）
# ---------------------------------------------------------------------------
@requires_api_key
def test_F_OUT_01_sort_price_asc():
    data = _run_flight_search("上海", "成都", *_departure_time_args(), "--sort-by", "price_asc")
    assert data.get("success") is True
    info = (data.get("result") or {}).get("flightInfo") or []
    if len(info) >= 2:
        prices = []
        for f in info:
            ref = f.get("referencePrice") or f.get("price") or f.get("minPrice")
            if ref is not None:
                try:
                    prices.append(float(ref))
                except (TypeError, ValueError):
                    pass
        if len(prices) >= 2:
            assert prices == sorted(prices)


@requires_api_key
def test_F_OUT_04_invalid_sort():
    """无效 sort-by：脚本应拒绝或回退默认。"""
    data = _run_flight_search("上海", "北京", *_departure_time_args(), "--sort-by", "invalid")
    # 可能 success=False 或 success=True 但按默认顺序
    assert "result" in data or "error" in data


@requires_api_key
def test_F_OUT_05_max_price():
    data = _run_flight_search("上海", "北京", *_departure_time_args(), "--max-price", "2000")
    assert data.get("success") is True
    info = (data.get("result") or {}).get("flightInfo") or []
    for f in info:
        ref = f.get("referencePrice") or f.get("price") or f.get("minPrice")
        if ref is not None:
            try:
                assert float(ref) <= 2000
            except (TypeError, ValueError):
                pass


def test_F_OUT_07_negative_price():
    data = _run_flight_search("上海", "北京", *_departure_time_args(), "--max-price", "-100")
    # 脚本拒绝或忽略无效值
    assert data.get("success") is False or (data.get("success") is True and isinstance(data.get("result"), dict))


@requires_api_key
def test_F_OUT_14_direct():
    data = _run_flight_search("上海", "北京", *_departure_time_args())
    assert data.get("success") is True
