#!/usr/bin/env python3
"""
周边搜索脚本的单元测试与集成测试。
- 单元测试：integrate_pois、geocode/around 通过 mock 不请求真实 API。
- 集成测试：main() 通过 subprocess 调用脚本，需配置 AMAP_KEY。
运行方式（在 skill 根目录下）：
  python -m pytest evals/test_run_surround_search.py -v
  或: python evals/test_run_surround_search.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 将 scripts 加入路径以便导入
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_surround_search as script


class TestIntegratePois(unittest.TestCase):
    """测试高德 POI 列表转为统一结构的逻辑。"""

    def test_empty_list(self) -> None:
        self.assertEqual(script.integrate_pois([]), [])
        self.assertEqual(script.integrate_pois(None), [])

    def test_single_poi(self) -> None:
        amap = [
            {
                "name": "测试餐厅",
                "address": "朝阳区某某路1号",
                "location": "116.48,39.99",
                "distance": "500",
                "type": "餐饮服务",
            }
        ]
        out = script.integrate_pois(amap)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "测试餐厅")
        self.assertEqual(out[0]["address"], "朝阳区某某路1号")
        self.assertEqual(out[0]["distance"], 500)
        self.assertEqual(out[0]["poi_type"], "餐饮服务")
        self.assertEqual(out[0]["location"], {"lng": 116.48, "lat": 39.99})

    def test_multiple_pois(self) -> None:
        amap = [
            {"name": "A", "address": "addr1", "location": "116.1,39.1", "distance": "100", "type": "餐饮"},
            {"name": "B", "address": "addr2", "location": "116.2,39.2", "distance": "200", "type": "餐饮"},
        ]
        out = script.integrate_pois(amap)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["name"], "A")
        self.assertEqual(out[1]["distance"], 200)

    def test_missing_location_fallback(self) -> None:
        amap = [{"name": "X", "pname": "北京市", "cityname": "朝阳区", "adname": "望京"}]
        out = script.integrate_pois(amap)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "X")
        self.assertEqual(out[0]["location"], None)
        self.assertEqual(out[0]["address"], "北京市朝阳区望京")

    def test_invalid_location_returns_none(self) -> None:
        amap = [{"name": "Y", "location": "not-a-coord", "distance": ""}]
        out = script.integrate_pois(amap)
        self.assertEqual(out[0]["location"], None)
        # 空字符串 distance 脚本不转为数字，可能为 "" 或 None
        self.assertIn(out[0]["distance"], (None, ""))


class TestGeocode(unittest.TestCase):
    """测试地理编码（mock HTTP）。"""

    @patch.object(script, "_http_get")
    def test_geocode_success(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {
            "status": "1",
            "geocodes": [{"location": "116.473168,39.993015"}],
        }
        result = script.geocode("fake_key", "北京西站", "北京")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("location"), "116.473168,39.993015")

    @patch.object(script, "_http_get")
    def test_geocode_fail_status(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"status": "0", "info": "INVALID_KEY"}
        result = script.geocode("bad_key", "北京西站", None)
        self.assertFalse(result.get("ok"))
        self.assertIn("info", result)

    @patch.object(script, "_http_get")
    def test_geocode_empty_geocodes(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"status": "1", "geocodes": []}
        result = script.geocode("key", "不存在的地址", "北京")
        self.assertFalse(result.get("ok"))


class TestAround(unittest.TestCase):
    """测试周边搜索（mock HTTP）。"""

    @patch.object(script, "_http_get")
    def test_around_success(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {
            "status": "1",
            "pois": [
                {"name": "咖啡店A", "address": "某路1号", "location": "116.48,39.99", "distance": "300", "type": "咖啡"}
            ],
        }
        result = script.around(
            "key", "116.473168,39.993015", "咖啡店", "北京",
            radius=2000, sortrule="distance", offset=10,
        )
        self.assertEqual(result.get("status"), "1")
        self.assertEqual(len(result.get("pois", [])), 1)
        self.assertEqual(result["pois"][0]["name"], "咖啡店A")


class TestMainIntegration(unittest.TestCase):
    """集成测试：通过 subprocess 调用脚本，需配置 AMAP_KEY。"""

    def _run_script(self, *args: str, timeout: int = 20) -> tuple[int, dict, str]:
        cmd = [sys.executable, str(SCRIPTS / "run_surround_search.py")] + list(args)
        proc = subprocess.run(
            cmd,
            cwd=str(SKILL_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=os.environ.copy(),
        )
        out = proc.stdout.strip() if proc.stdout else ""
        stderr = (proc.stderr or "").strip()
        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError:
            data = {"error": stderr or "stdout 非 JSON: " + (out[:200] if out else "无输出")}
        return proc.returncode, data, stderr

    def test_main_missing_location(self) -> None:
        # 空地址：脚本可能通过 argparse 拒绝（无位置参数会报错），或我们传空字符串
        code, data, _ = self._run_script("")
        # 若传 "" 为位置参数，脚本会输出 success: false, error 含「不能为空」
        self.assertIn("success", data)
        if data.get("success") is False:
            self.assertIn("error", data)

    def test_main_real_api_beijing_restaurant(self) -> None:
        """真实 API：北京西站附近餐厅，最多 3 条。"""
        if not os.environ.get("AMAP_KEY", "your-key"):
            self.skipTest("AMAP_KEY 未配置，跳过集成测试")
        code, data, stderr = self._run_script(
            "北京西站", "--city", "北京", "--keyword", "餐厅", "--max-results", "3",
            timeout=60,
        )
        err_msg = data.get("error", "") or stderr or "无错误信息"
        self.assertEqual(code, 0, msg=f"exit code 非 0. error: {err_msg}\nstderr: {stderr}")
        self.assertTrue(data.get("success"), msg=err_msg)
        self.assertIn("pois", data)
        self.assertIsInstance(data["pois"], list)
        self.assertLessEqual(len(data["pois"]), 3)
        if data["pois"]:
            p = data["pois"][0]
            self.assertIn("name", p)
            self.assertIn("address", p)

    def test_main_real_api_sanlitun_coffee(self) -> None:
        """真实 API：三里屯周边咖啡店，半径 2km。"""
        if not os.environ.get("AMAP_KEY", "b9295f94ee648dd05551a5e8c4951820"):
            self.skipTest("AMAP_KEY 未配置，跳过集成测试")
        code, data, stderr = self._run_script(
            "三里屯", "--city", "北京", "--keyword", "咖啡店", "--radius", "2000", "--max-results", "5",
            timeout=60,
        )
        err_msg = data.get("error", "") or stderr
        self.assertEqual(code, 0, msg=f"error: {err_msg}\nstderr: {stderr}")
        self.assertTrue(data.get("success"), msg=err_msg or "unknown")
        self.assertLessEqual(len(data.get("pois", [])), 5)
        self.assertEqual(data.get("query_summary", {}).get("radius"), 2000)


if __name__ == "__main__":
    unittest.main()
