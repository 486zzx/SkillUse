---
name: flight-search
description: "国内航班查询：地点→IATA、出发/到达时间范围为 yyyy-MM-dd HH:mm、通过 run_flight_search.py 查询、可选筛选排序。Capabilities: 城市/机场/省份解析、直飞、多长参数调用。Use for: 查机票、查航班、某地到某地、出发时间范围、按价格或时间排序。Scope: 中国境内（含大陆与台湾）；境外不查并提示。Triggers: 查机票、查航班、飞机票、某地到某地、出发地目的地、出发时间、直飞、价格排序、起飞时间"
---

# 国内航班查询

通过入口 **`scripts/run_flight_search.py`** 查询国内单段航班：传入出发地、目的地、出发时间范围（必填）及可选到达时间范围、价格上限、排序方式，输出压缩 JSON。仅支持单段行程。

**时间格式**：**仅接受**上游传入的标准格式 **yyyy-MM-dd HH:mm**，时间为范围 `[开始, 结束]`。skill 不解析「3月5号」「明天」等自然语言，调用方须先转为标准格式再传入。

## 1. 输入与输出

- **输入**：出发地、目的地（城市或机场名）；**出发时间范围**（必填，格式 `[yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm]`）；可选到达时间范围、`--max-price`、`--sort-by`。
- **输出**：成功为 `{success: true, result: {flightInfo, flightCount}}`；失败为 `{success: false, error}`；参数不足为 `{success: false, clarification_needed: true, missing, message}`，需向用户澄清后再次调用。
- **范围**：中国境内（含大陆与台湾）。境外不查并提示仅支持境内。
- **结果展示**：根据 `result.flightInfo`、`result.flightCount` 完整展示全部航班，不得折叠或截断。若 `flightInfo` 为空表示该日期/航线上暂无航班，需向用户说明并建议改日期或航线。

## 2. 入口参数

**必填**：第 1 个参数 出发地、第 2 个 目的地；`--departure-time "yyyy-MM-dd HH:mm" "yyyy-MM-dd HH:mm"`（开始、结束）。

**可选**（仅用户明确要求时传入）：

| 参数 | 说明 |
|------|------|
| `--arrival-time "开始" "结束"` | 到达时间范围，格式同出发 |
| `--max-price N` | 只保留票价 ≤ N 的航班 |
| `--sort-by` | `price_asc` / `price_desc` / `departure_asc` / `departure_desc` / `duration_asc` |

工作目录为项目根或 `scripts` 所在目录。

**示例**

```bash
python scripts/run_flight_search.py 上海 北京 --departure-time "2026-03-11 00:00" "2026-03-11 23:59"
python scripts/run_flight_search.py 上海 成都 --departure-time "2026-03-11 00:00" "2026-03-11 23:59" --max-price 2000 --sort-by price_asc
```

## 3. 命令示例

时间均以标准格式 **yyyy-MM-dd HH:mm** 传入，不得使用「3月5号」「明天」等。

| 场景 | 命令 |
|------|------|
| 2026-03-11 上海到成都 | `run_flight_search.py 上海 成都 --departure-time "2026-03-11 00:00" "2026-03-11 23:59"` |
| 2026-03-05 虹桥到天府，价格不超过 1500 | `run_flight_search.py 虹桥 天府 --departure-time "2026-03-05 00:00" "2026-03-05 23:59" --max-price 1500` |
| 2026-03-11 上海到成都，按价格从低到高 | `run_flight_search.py 上海 成都 --departure-time "2026-03-11 00:00" "2026-03-11 23:59" --sort-by price_asc` |
| 2026-03-11 08:00–23:59 上海飞成都 | `run_flight_search.py 上海 成都 --departure-time "2026-03-11 08:00" "2026-03-11 23:59"` |

## 4. 配置与依赖

- 数据目录、超时等均在 **`scripts/config.py`** 中配置，无需环境变量。
- 可选依赖：`pip install -r requirements.txt`。
