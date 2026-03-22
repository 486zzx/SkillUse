---
name: train-ticket-search
description: "列车/火车票班次查询：根据用户问题查火车票、高铁、动车班次。Use for: 查火车票、查高铁、查动车、某地到某地火车、出发日期、按价格或时间排序。Triggers: 火车票、列车、高铁、动车、G/D/Z/T/K、某地到某地、出发站、出发地、到达站、目的地、出发日期、最便宜、按价格排序、按时间排序、历时。请务必在用户询问火车/列车/高铁/动车票、班次、时刻、票价时使用本 skill，即使用户未明确说「火车」也可在语境为铁路出行时使用。"
---

# 列车班次查询

通过 **`scripts/run_train_search.py`** 或 **函数 `train_search()`** 查询列车班次与车票：传入出发站、到达站、出发时间（必填）及可选到达时间、车型、排序方式，输出 JSON。仅支持单段行程。

**时间参数**（与航班一致）：支持两种形式（出发/到达相同）：
- **数组**：`["起始时间", "终止时间"]`，格式 `yyyy-MM-dd HH:mm`。
- **单值**：单个日期 `yyyy-MM-dd` 视为当日 00:00–23:59；单个日期时间 `yyyy-MM-dd HH:mm` 视为该时刻到当日 23:59。

skill 默认不解析「3月5号」「明天」等自然语言，调用方须先转为标准格式再传入（或开启 config 中的 `PARSE_NATURAL_LANGUAGE_TIME`）。

## 1. 输入与输出

- **输入**：出发站、到达站（城市或站点名）；**出发时间**（必填，数组 `[起始, 终止]` 或单日期/日期时间）；可选到达时间、`train_type`、`sort_by`。
- **输出**：成功为 `{success: true, trains, total_count}`；失败为 `{success: false, error, message}`。查询摘要（query_summary）仅写入日志，不返回给调用方。参数问题会提前校验并退出：**澄清**（缺参/格式不对）为 `clarification_needed: true` 且带 `missing`、`message`；**参数值不合法**（如出发日期早于今天、车型非法）为 `clarification_needed: true` 且带 `invalid`、`message`，提示用户修正后重试。
- **缺参澄清**：若用户未提供出发站、到达站或出发时间任一项，先向用户发起澄清，不要调用脚本；待用户补全后再调用 `run_train_search.py` 或 `train_search()`。
- **日期限制**：**仅支持查询今天及之后的列车，不能查询昨天及更早的日期**，否则接口会报错。调用方传入的出发日期须 ≥ 当日。
- **结果展示**：根据 `trains`、`total_count` 完整展示全部车次，不得折叠或截断。若 `trains` 为空表示该日期/线路上暂无班次，需向用户说明并建议改日期或线路。
- **报错规范**：**参数问题**（缺参、格式错误、日期过早、车型非法、站点无匹配等）→ 澄清 `clarification_needed: true` + `missing`/`invalid` + `message`；`error`/`message` 会标明**具体是哪个参数**（如参数「出发站」、参数「到达站」、参数「出发时间」、参数「车型」）以及**具体原因**（缺少、无匹配、格式不正确、不合法等）。**API/服务异常**及**其他异常**→ 对用户统一返回「服务异常，请稍后再试」，详细原因仅写入日志。

## 2. 函数调用（推荐在代码中直接调用）

```python
from run_train_search import train_search

# 时间用数组
result = train_search("北京", "上海", ["2025-03-11 00:00", "2025-03-11 23:59"])

# 时间用单日期（当日 00:00–23:59）
result = train_search("北京", "上海", "2025-03-11", sort_by="price_asc")

# 排序：出发时间、到达时间、耗时、价格，升序/降序
# sort_by: departure_asc, departure_desc, arrival_asc, arrival_desc, duration_asc, duration_desc, price_asc, price_desc
result = train_search("杭州", "南京", "2025-03-05", sort_by="duration_asc")
```

返回与命令行输出一致的 `dict`，可直接用 `result["success"]`、`result["trains"]` 等处理。

## 3. 命令行参数

**必填**：第 1 个参数出发站、第 2 个到达站；`--departure-time` 支持：
- 数组（JSON）：`--departure-time '["2025-03-11 00:00","2025-03-11 23:59"]'`
- 单日期或单日期时间：`--departure-time "2025-03-11"`
- 两个独立参数：`--departure-time "2025-03-11 00:00" "2025-03-11 23:59"`

**可选**（仅用户明确要求时传入）：

| 参数 | 说明 |
|------|------|
| `--arrival-time` | 到达时间范围，格式同出发（数组 / 单值 / 两参数） |
| `--train-type G` | 车型筛选，可多次指定（G/D/Z/T/K/O/F/S） |
| `--sort-by` | 出发时间 `departure_asc`/`departure_desc`、到达时间 `arrival_asc`/`arrival_desc`、耗时 `duration_asc`/`duration_desc`、价格 `price_asc`/`price_desc` |
| `--trains-format json` | 默认返回 Markdown 表格字符串；传 `json` 时返回车次对象数组，便于程序解析 |

工作目录为项目根或 `scripts` 所在目录。

**示例**

```bash
# 数组形式
python scripts/run_train_search.py 北京 上海 --departure-time '["2026-03-18 00:00","2026-03-18 23:59"]'
# 单日期（当日全天，推荐在 Windows PowerShell 下使用以避免引号被拆开）
python scripts/run_train_search.py 北京 上海 --departure-time "2026-03-18" --sort-by price_asc
# 两参数形式（Windows 下最稳妥）
python scripts/run_train_search.py 杭州 南京 --departure-time "2026-03-18 08:00" "2026-03-18 23:59"
```
在 Windows PowerShell 中，若 `--departure-time '["start","end"]'` 报“缺少出发时间范围”，可改用单日期 `"2025-03-11"` 或两参数 `"开始" "结束"`。

## 4. 命令示例

| 场景 | 命令 |
|------|------|
| 2025-03-11 北京到上海 | `run_train_search.py 北京 上海 --departure-time "2025-03-11"` 或 `'["2025-03-11 00:00","2025-03-11 23:59"]'` |
| 杭州到南京，只要高铁，按价格升序 | `run_train_search.py 杭州 南京 --departure-time "2025-03-11" --train-type G --sort-by price_asc` |
| 按出发时间升序 | `--sort-by departure_asc` |
| 按到达时间降序 | `--sort-by arrival_desc` |
| 按耗时升序 | `--sort-by duration_asc` |

## 5. 脚本输出结构（约定）

```yaml
success: true/false
trains: string   # 默认：Markdown 表格字符串（由 config.TRAINS_AS_MARKDOWN 控制）；加 --trains-format json 或 config.TRAINS_AS_MARKDOWN=False 时为车次对象数组
total_count: number
clarification_needed: true   # 可选，参数不足或参数值不合法时为 true
missing: [ "from_station", ... ]   # 可选，缺失的必填参数名
invalid: [ "departure_time", "train_type", ... ]   # 可选，值不合法的参数名（如日期早于今天、车型非法）
error: "" 或错误说明（API/服务异常时统一为「服务异常，请稍后再试」，详情见日志）
message: "" 或提示文案
```

## 6. 何时使用本 Skill

- 用户要**查火车票、列车班次、高铁、动车**，或问「某地到某地怎么坐火车」「有没高铁」等。
- 用户或上游**已给出标准格式时间**（数组或 `yyyy-MM-dd HH:mm`），或可经澄清后得到该格式。
- 用户给出**出发地、目的地、日期**（或其一），且语境为**铁路出行**（即便未说「火车」）。

## 7. 车型与排序

**车型（train_type，固定）**：`G(高铁/城际), D(动车), Z(直达特快), T(特快), K(快速), O(其他), F(复兴号), S(智能动车组)`。可传多个，如 `--train-type G --train-type D`。

**排序（sort_by）**：出发时间、到达时间、耗时、价格，各支持升序/降序：`departure_asc`/`departure_desc`、`arrival_asc`/`arrival_desc`、`duration_asc`/`duration_desc`、`price_asc`/`price_desc`。
