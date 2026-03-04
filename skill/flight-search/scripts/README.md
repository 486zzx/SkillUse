# 航班查询脚本说明

脚本在 `scripts/` 目录下运行；数据目录由环境变量 **FLIGHT_DATA_DIR** 指定或使用默认路径。**所有脚本仅通过命令行长参数接收输入**，不使用 stdin。

## 0. 总入口（推荐）

**脚本**：`run_flight_search.py`

一次调用完成：地点→IATA、日期→yyyy-mm-dd、调用 API、可选筛选排序；**每次执行仅查询一段航班**。**多长参数**，无需传 JSON。

- **必填（位置参数）**：第 1 个 出发地、第 2 个 目的地、第 3 个 日期。
- **可选**：`--max-segments 1`、`--max-price 2000`、`--sort-by price_asc`、`--min-departure-time 08:00`、`--max-departure-time 22:00`、`--equipment-contains 738`。
- **输出**：成功为 `{"success":true,"result":{"flightInfo":[...],"flightCount":N}}`；失败为 `{"success":false,"error":"..."}`。
- **用法**：`python run_flight_search.py 上海 北京 明天` 或 `python run_flight_search.py 上海 北京 明天 --max-price 2000 --sort-by price_asc`

## 1. 地点 → IATA 三字码

**脚本**：`location_to_iata.py`

- 读取 `city_map.json`、`province_map.json`、`airport_list.json`。解析优先级：机场 > 城市 > 省份。
- 用法：`python location_to_iata.py "上海" "北京"` 或 `python location_to_iata.py --json "[\"西安\", \"广东\"]"`
- 输出：`{"iata":"SHA","source":"city","raw":"上海"}` 或数组。

## 2. 日期 → yyyy-mm-dd

**脚本**：`normalize_date.py`

- 已安装 jionlp 时优先使用其解析，否则使用内置规则（今天/明天/后天、N月M日、下周一等）。
- 用法：`python normalize_date.py "明天"` 或 `python normalize_date.py "3月5号" --base 2026-03-01`
- 输出：`{"date":"2026-03-02","source":"simple","raw":"明天"}` 或数组。

## 3. 多段行程标准化

**脚本**：`parse_multi_segment.py`

- 输入：`[{"origin":"上海","destination":"西安","date":"明天"}, ...]` 作为**长参数**传入。
- 输出：`[{"departure":"SHA","arrival":"SIA","departureDate":"2026-03-02"}, ...]`
- 用法：`python parse_multi_segment.py '[{"origin":"上海","destination":"西安","date":"明天"}]'`

## 4. 航班数量

**`query_flight_api.py`** 的返回中已包含 **`result.flightCount`**，直接使用即可。

## 5. 筛选与排序

**脚本**：`filter_sort_flights.py`

- 仅当用户**明确要求**筛选或排序时调用。输入为 **长参数 JSON** 或 `--file <path>`。
- 输入：`{"flightInfo": [...], "options": {"max_price": 2000, "sort_by": "price_asc"}}`
- 用法：`python filter_sort_flights.py '{"flightInfo":[...],"options":{...}}'` 或 `python filter_sort_flights.py --file api_response.json`

## 6. 调用航班 API

**脚本**：`query_flight_api.py`

- 输入：`{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","maxSegments":"1"}` 作为**长参数**传入。用户未指定航段时 maxSegments 传 `"1"`（直飞）。
- 输出：聚合 API 完整响应 JSON；成功时 **`result`** 中附带 **`flightCount`**。
- 用法：`python query_flight_api.py '{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","maxSegments":"1"}'`

## Windows 控制台编码

脚本内已将 stdout/stderr 重设为 UTF-8。建议运行前设置 `PYTHONIOENCODING=utf-8`（PowerShell：`$env:PYTHONIOENCODING='utf-8'`），避免中文乱码。

## 依赖

- 可选：`jionlp`（日期解析）。见上级目录 `requirements.txt`。机场数据来自 `airport_list.json`，无需 Excel 与 openpyxl。
