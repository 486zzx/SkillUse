---
name: flight-search
description: "国内航班查询：地点→IATA、出发/到达时间范围为 yyyy-MM-dd HH:mm、通过 run_flight_search.py 查询、可选筛选排序。Capabilities: 城市/机场/省份解析、直飞、多长参数调用。Use for: 查机票、查航班、某地到某地、出发时间范围、按价格或时间排序。Scope: 中国境内（含大陆与台湾）；境外不查并提示。Triggers: 查机票、查航班、飞机票、某地到某地、出发地目的地、出发时间、直飞、价格排序、起飞时间"
---

# 国内航班查询

通过 **`scripts/run_flight_search.py`** 或 **函数 `search_flights()`** 查询国内单段航班：传入出发地、目的地、出发时间（必填）及可选到达时间、价格上限、排序方式，输出压缩 JSON。仅支持单段行程。

**时间参数**：支持两种形式（出发/到达相同）：
- **数组**：`["起始时间", "终止时间"]`，格式 `yyyy-MM-dd HH:mm`。
- **单值**：单个日期 `yyyy-MM-dd` 视为当日 00:00–23:59；单个日期时间 `yyyy-MM-dd HH:mm` 视为该时刻到当日 23:59。

skill 默认不解析「3月5号」「明天」等自然语言，调用方须先转为标准格式再传入。自然语言时间转化已移至 **reserve/time-conversion/** 作储备，需用时见该目录下 README。

## 1. 输入与输出

- **输入**：出发地、目的地（城市或机场名）；**出发时间**（必填，数组 `[起始, 终止]` 或单日期/日期时间）；可选到达时间、`max_price`、`sort_by`。
- **输出**：成功为 `{success: true, flightInfo: "<Markdown 表格字符串>", flightCount: N}`（默认以 Markdown 表节省 token）；可选 `--flights-format json` 时 `flightInfo` 为 JSON 数组。若 Markdown 转换异常则自动退回原本的 JSON 数组。失败为 `{success: false, error, message}`。参数问题会提前校验并退出：**澄清**（缺参/格式不对）为 `clarification_needed: true` 且带 `missing` 或 `invalid`、`message`，提示用户补全或修正后重试；**参数值不合法**（如出发日期早于今天、max_price 非正数、sort_by 非法）同样返回 `clarification_needed: true` 与 `invalid`、`message`，不发起请求。
- **范围**：中国境内（含大陆与台湾）。境外不查并提示仅支持境内。
- **日期限制**：**仅支持查询今天及之后的航班**；不能查询昨天及更早的日期，否则接口会报错（如「行程出发日期格式不正确或为空」）。调用方传入的出发日期须 ≥ 当日。
- **结果展示**：根据 `flightInfo`、`flightCount` 完整展示全部航班，不得折叠或截断。若 `flightInfo` 为空表示该日期/航线上暂无航班，需向用户说明并建议改日期或航线。
- **共享航班合并**：对所有 `isCodeShare=true` 的项，在同组（同航线、同起降时刻）内寻找合并项（即 `isCodeShare=false` 的实际承运）；有则将该组合并为一条并带 `codeShareFlightNos`（同组可能没有实际承运，全为共享时也合并；代表优先取实际承运，否则取票价最低）。组内有多条实际承运时，按 flightNo 规范号合并：如 `3U5169(MU5105)` 与 `MU5105` 同规范号则合并为一条，否则各条保留。
- **直飞时精简字段**：当配置 `config.DIRECT_ONLY=True` 或命令行传入 `--direct` 时，每条航班中会去掉 `segments`、`transferNum` 等对直飞无用的字段。**直飞与输出格式**由 `config.DIRECT_ONLY`、`config.FLIGHTS_AS_MARKDOWN` 控制，命令行可覆盖。

**报错约定**：
- **参数问题（澄清）**：缺参、格式错误、参数值不合法（如出发日期早于今天、max_price 非正数、sort_by 非法）、无法解析出发地/目的地。返回 `success: false, clarification_needed: true`，并带 `missing`/`invalid` 与具体 `message`，提示用户补全或修正后重试。
- **服务异常**：API 请求失败、网络异常、API 返回业务错误、数据目录缺失、模块加载失败等。对用户统一返回 `error`/`message` 为「服务异常，请稍后再试」；详细原因仅写入日志（`flight_search.run_flight_search`、`flight_search.query_flight_api`），便于排查。

除此以外无其他面向用户的报错类型；查询成功但无航班时 `success: true` 且 `flightCount` 为 0，并带提示文案。

## 2. 函数调用（推荐在代码中直接调用）

```python
from run_flight_search import search_flights

# 时间用数组
result = search_flights("上海", "北京", ["2026-03-11 00:00", "2026-03-11 23:59"])

# 时间用单日期（当日 00:00–23:59）
result = search_flights("上海", "成都", "2026-03-11", max_price=2000, sort_by="price_asc")

# 排序：出发时间、到达时间、耗时、价格，升序/降序
# sort_by: departure_asc, departure_desc, arrival_asc, arrival_desc, duration_asc, duration_desc, price_asc, price_desc
result = search_flights("虹桥", "天府", "2026-03-05", sort_by="duration_asc")

# 直飞、输出格式等由 config 控制（scripts/config.py）：
# config.DIRECT_ONLY = True   # 仅直飞并精简字段
# config.FLIGHTS_AS_MARKDOWN = False  # flightInfo 为 JSON 数组
result = search_flights("上海", "北京", "2026-03-11")
```

返回与命令行输出一致的 `dict`，可直接用 `result["success"]`、`result["result"]` 等处理。

## 3. 命令行参数

**必填**：第 1 个参数出发地、第 2 个目的地；`--departure-time` 支持：
- 数组（JSON）：`--departure-time '["2026-03-11 00:00","2026-03-11 23:59"]'`
- 单日期或单日期时间：`--departure-time "2026-03-11"`
- 两个独立参数：`--departure-time "2026-03-11 00:00" "2026-03-11 23:59"`

**可选**（仅用户明确要求时传入）：

| 参数 | 说明 |
|------|------|
| `--arrival-time` | 到达时间范围，格式同出发（数组 / 单值 / 两参数） |
| `--max-price N` | 只保留票价 ≤ N 的航班 |
| `--sort-by` | 出发时间 `departure_asc`/`departure_desc`、到达时间 `arrival_asc`/`arrival_desc`、耗时 `duration_asc`/`duration_desc`、价格 `price_asc`/`price_desc` |
| `--direct` | 指定仅查直飞时，从每条航班中移除 `segments`、`transferNum` 等无用字段 |
| `--flights-format` | `markdown`（默认）或 `json`；为 markdown 时 `flightInfo` 为表格字符串以节省 token |

工作目录为项目根或 `scripts` 所在目录。

**示例**

```bash
# 数组形式
python scripts/run_flight_search.py 上海 北京 --departure-time '["2026-03-11 00:00","2026-03-11 23:59"]'
# 单日期（当日全天，推荐在 Windows PowerShell 下使用以避免引号被拆开）
python scripts/run_flight_search.py 上海 成都 --departure-time "2026-03-11" --max-price 2000 --sort-by price_asc
# 两参数形式（Windows 下最稳妥）
python scripts/run_flight_search.py 上海 成都 --departure-time "2026-03-11 08:00" "2026-03-11 23:59"
```
在 Windows PowerShell 中，若 `--departure-time '["start","end"]'` 报“缺少出发时间范围”，可改用单日期 `"2026-03-11"` 或两参数 `"开始" "结束"`。

## 4. 命令示例

| 场景 | 命令 |
|------|------|
| 2026-03-11 上海到成都 | `run_flight_search.py 上海 成都 --departure-time "2026-03-11"` 或 `'["2026-03-11 00:00","2026-03-11 23:59"]'` |
| 虹桥到天府，价格≤1500，按价格升序 | `run_flight_search.py 虹桥 天府 --departure-time "2026-03-05" --max-price 1500 --sort-by price_asc` |
| 按出发时间升序 | `--sort-by departure_asc` |
| 按到达时间降序 | `--sort-by arrival_desc` |
| 按耗时升序 | `--sort-by duration_asc` |

## 5. 配置与依赖

- 数据目录、超时等均在 **`scripts/config.py`** 中配置，无需环境变量。
- 可选依赖：`pip install -r requirements.txt`。
