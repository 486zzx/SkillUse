# 航班查询脚本说明

脚本在 `scripts/` 目录下运行；数据目录由 **config.py** 配置（环境变量 **FLIGHT_DATA_DIR** 可覆盖）。**所有脚本仅通过命令行长参数接收输入**，不使用 stdin。

## 0. 总入口（推荐）

**脚本**：`run_flight_search.py`

一次调用完成：地点→IATA、按出发时间范围调用 API、可选筛选排序；**每次执行仅查询一段航班**。**多长参数**，无需传 JSON。

- **必填**：第 1 个 出发地、第 2 个 目的地；`--departure-time "yyyy-MM-dd HH:mm" "yyyy-MM-dd HH:mm"`（开始、结束）。
- **可选**：`--arrival-time`、`--max-price 2000`、`--sort-by price_asc`、`--direct`、`--flights-format markdown|json`（默认 markdown 时 `flightInfo` 为 Markdown 表格字符串以节省 token）。
- **输出**：成功为 `{"success":true,"flightInfo":"<Markdown 表或 JSON 数组>","flightCount":N}`；失败为 `{"success":false,"error":"..."}`；参数不足为 `{"success":false,"clarification_needed":true,"missing":[...],"message":"..."}`。
- **用法**：`python run_flight_search.py 上海 北京 --departure-time "2026-03-11 00:00" "2026-03-11 23:59"` 或追加 `--max-price 2000 --sort-by price_asc`

## 1. 地点 → IATA 三字码

**脚本**：`location_to_iata.py`

- 读取 `city_map.json`、`province_map.json`、`airport_list.json`。解析优先级：机场 > 城市 > 省份。
- 用法：`python location_to_iata.py "上海" "北京"` 或 `python location_to_iata.py --json "[\"西安\", \"广东\"]"`
- 输出：`{"iata":"SHA","source":"city","raw":"上海"}` 或数组。

## 2. 日期（自然语言 → yyyy-mm-dd，储备）

自然语言日期解析已移至 **`reserve/time-conversion/`**，主流程默认时间格式正确。若需使用「明天」「3月5号」等，见 `reserve/time-conversion/README.md`。

## 3. 多段行程标准化

**脚本**：`parse_multi_segment.py`

- 输入：`[{"origin":"上海","destination":"西安","date":"2026-03-02"}, ...]`，**date 须为标准日期 yyyy-mm-dd**。
- 输出：`[{"departure":"SHA","arrival":"SIA","departureDate":"2026-03-02"}, ...]`
- 用法：`python parse_multi_segment.py '[{"origin":"上海","destination":"西安","date":"2026-03-02"}]'`

## 4. 航班数量

**`query_flight_api.py`** 的返回中已包含 **`result.flightCount`**，直接使用即可。

## 5. 筛选与排序

**脚本**：`filter_sort_flights.py`

- 输入为 **长参数 JSON** 或 `--file <path>`。options 可含 `departure_time_range`、`arrival_time_range`（均为 `[start, end]` 的 yyyy-MM-dd HH:mm）、`max_price`、`sort_by`。
- 用法：`python filter_sort_flights.py '{"flightInfo":[...],"options":{...}}'` 或 `python filter_sort_flights.py --file api_response.json`

## 6. 调用航班 API

**脚本**：`query_flight_api.py`

- 输入：`{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","maxSegments":"1"}` 作为**长参数**传入。maxSegments 固定为 `"1"`（直飞）。
- 输出：聚合 API 完整响应 JSON；成功时 **`result`** 中附带 **`flightCount`**。
- 用法：`python query_flight_api.py '{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","maxSegments":"1"}'`

## 7. 配置

统一配置在 **`config.py`** 中：API URL、Key 环境变量、超时、数据目录、默认 max_segments、时间格式等。修改配置请编辑该文件。

## Windows 控制台编码

脚本内已将 stdout/stderr 重设为 UTF-8。建议运行前设置 `PYTHONIOENCODING=utf-8`（PowerShell：`$env:PYTHONIOENCODING='utf-8'`），避免中文乱码。

## 依赖

- 可选：`jionlp`（日期解析，用于 normalize_date/parse_multi_segment）。见上级目录 `requirements.txt`。机场数据来自 `airport_list.json`，无需 Excel 与 openpyxl。
