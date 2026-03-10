---
name: train-ticket-search
description: "列车/火车票班次查询：根据用户问题查火车票、高铁、动车班次。Use for: 查火车票、查高铁、查动车、某地到某地火车、出发日期、按价格或时间排序。Triggers: 火车票、列车、高铁、动车、G/D/Z/T/K、某地到某地、出发站、出发地、到达站、目的地、出发日期、最便宜、按价格排序、按时间排序、历时。请务必在用户询问火车/列车/高铁/动车票、班次、时刻、票价时使用本 skill，即使用户未明确说「火车」也可在语境为铁路出行时使用。"
---

# 列车班次查询

根据用户问题查询列车班次与车票：**原始问题中需包含标准格式**的出发/到达时间（`yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm`，起止用逗号分隔，如 `2025-03-11 08:00, 2025-03-11 18:00`）。本 skill **仅从问题中提取**出发站、到达站、以及该格式的出发时间范围与可选到达时间范围、车型、排序等，并原样传给脚本；**不做任何时间转化或推算**。

**参数不足时**：若用户未提供出发站、到达站或出发时间任一项，**先向用户发起澄清**（列出缺失项并请用户补充），**不要**调用脚本；待用户补全后再调用 `run_train_search.py`。

## 1. 何时使用本 Skill

- 用户要**查火车票、列车班次、高铁、动车**，或问「某地到某地怎么坐火车」「有没高铁」等。
- 用户或上游**已给出标准格式时间**（`yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm`），或可经澄清后得到该格式。本 skill **不负责**把「明天」「下午」等自然语言转为标准格式。
- 用户给出**出发地、目的地、日期**（或其一），且语境为**铁路出行**（即便未说「火车」）。

## 2. 工作流程

```
用户问题（其中需已包含标准格式时间，如「北京到上海 2025-03-11 08:00, 2025-03-11 18:00 的高铁」）
    │
    ├─ 从问题中**提取**：出发站、到达站、**标准格式**的出发时间、到达时间（若有）、车型、排序
    ├─ 若缺少必填项（出发站 / 到达站 / 出发时间任一）→ 先向用户澄清，不要调用脚本
    ├─ 若问题中无标准格式时间 → 通过澄清要求用户补全或由上游提供，本 skill 不做时间转化
    │
    ├─ 调用脚本：run_train_search.py <出发站> <到达站> "<出发时间范围>" [--arrival-time "<到达时间范围>"] ...
    │       └─ 输出：{ success, trains[], total_count, need_clarification?, missing_params?, error? }
    │
    └─ success 为 true 时用 trains 整理回复；为 false 时根据 error 或 need_clarification 说明原因或继续向用户澄清
```

## 3. 你需要做的事

### 3.1 提取查询条件与澄清

从用户问题中提取并确认：

| 参数 | 说明 | 示例 |
|------|------|------|
| 出发站/出发地 from_station | **必填**，缺则先澄清 | 城市或站点名，如：北京、北京南、上海虹桥 |
| 到达站/目的地 to_station | **必填**，缺则先澄清 | 城市或站点名，如：上海、杭州东 |
| 出发时间 departure_time | **必填**，缺则先澄清；格式见下 | 标准格式范围，如：2025-03-11 08:00, 2025-03-11 23:59 |
| 到达时间 arrival_time | 可选 | 同上格式，如：2025-03-11 14:00, 2025-03-11 20:00 |
| 车型 train_type | 可选 | 见下方**车型枚举**（固定 8 种） |
| 排序 sort_by | 可选 | 仅当用户明确说「按价格」「按时间」「最快」等时传入 |

**时间格式**：**原始问题中需包含标准格式**的出发/到达时间（`yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm`，起止用逗号分隔）。本 skill **只做该格式时间的提取**，原样传入脚本，不做转化。

**缺参澄清**：若用户未提供出发站、到达站或出发时间中的任一项，**先向用户发起澄清**（说明缺少哪几项并请用户补充），**不要**调用 `run_train_search.py`；待用户补全后再调用。

**车型枚举（train_type，固定）**：`[G(高铁/城际), D(动车), Z(直达特快), T(特快), K(快速), O(其他), F(复兴号), S(智能动车组)]`。用户说「高铁/城际」→ G，「动车」→ D，以此类推。可传多个，如 `--train-type G --train-type D`。

**排序（sort_by）**：仅当用户明确要求时传。取值示例：`price_asc`（最便宜）、`price_desc`、`departure_asc`（尽早出发）、`departure_desc`、`arrival_asc`、`arrival_desc`、`duration_asc`（耗时最短）、`duration_desc`。

### 3.2 调用班次查询脚本

脚本位于**本 skill 根目录**下的 `scripts/run_train_search.py`（与 SKILL.md 同级的 `scripts` 子目录）。以当前环境中本 skill 的安装路径为基准拼接。

**推荐调用方式**（位置参数 + 可选键值）：

```bash
python scripts/run_train_search.py <出发站> <到达站> "<出发时间范围>" [--arrival-time "<到达时间范围>"] [--train-type G] [--sort-by price_asc]
```

- **出发时间范围**：必填，标准格式 `yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm`，如 `2025-03-11 08:00, 2025-03-11 23:59`。
- **到达时间范围**：可选，格式同上，传入 `--arrival-time`。

示例：

```bash
# 2025-03-11 全天 北京到上海
python scripts/run_train_search.py 北京 上海 "2025-03-11 00:00, 2025-03-11 23:59"

# 杭州到南京，出发 17:00 后，到达 18:00 前
python scripts/run_train_search.py 杭州 南京 "2025-03-12 17:00, 2025-03-12 23:59" --arrival-time "2025-03-12 18:00, 2025-03-12 23:59"

# 只要高铁，按价格从低到高
python scripts/run_train_search.py 杭州 南京 "2025-03-11 08:00, 2025-03-11 18:00" --train-type G --sort-by price_asc

# 按出发时间从早到晚
python scripts/run_train_search.py 广州 深圳 "2025-12-25 00:00, 2025-12-25 23:59" --sort-by departure_asc
```

**规则**：前三个参数依次为出发站、到达站、出发时间范围（**固定格式**）。出发地/目的地可为城市名或具体站点名，脚本会按 station.json 解析。可选：`--arrival-time`（同格式）、`--train-type`、`--sort-by`。多段行程需多次调用，每次一段。

### 3.3 根据脚本输出回复用户

- **success 为 true**：用返回的 `trains` 列表整理成表格或列表，包含车次、出发/到达站、出发/到达时刻、历时、席别与票价（若有）。**完整展示所有车次**，不要折叠或「部分省略」。
- **success 为 false**：根据 `error` 说明原因。若返回中有 `need_clarification: true` 或 `missing_params`，可据此向用户澄清并请其补全后再次调用。
- **success 为 true 但 trains 为空**：说明已按条件查询但该日期/线路上暂无班次，建议改日期或线路。

## 4. 脚本输出结构（约定）

脚本标准输出为 JSON，结构约定如下：

```yaml
success: true/false
trains: [ { train_no, from_station, to_station, departure_time, arrival_time, duration, seat_types[], ... }, ... ]
total_count: number
query_summary: { ... }   # 可选
need_clarification: true   # 可选，参数不足时为 true
missing_params: [ "from_station", ... ]   # 可选，缺失的必填参数名
error: "" 或错误说明
```

单条车次至少包含：车次号、出发站、到达站、出发时刻、到达时刻、历时；席别与票价在 `seat_types` 或等价字段中。你只需解析该 JSON 并组织成用户可读的回复，无需再调用其他接口或做二次聚合。

## 5. 执行流程小结

1. 从用户问题提取：出发站、到达站、出发时间、到达时间（若有）、车型、排序。**若任一项必填缺失，先向用户澄清，不要调用脚本。**
2. **问题中需已包含标准格式时间**（`yyyy-MM-dd HH:mm, yyyy-MM-dd HH:mm`）；本 skill **仅做提取**后调用 `scripts/run_train_search.py <出发站> <到达站> "<出发时间范围>" [--arrival-time "…"] [--train-type …] [--sort-by …]`。
3. 若 success 为 true：用 `trains` 与 `total_count` 完整呈现车次列表；若为 false：根据 `error` 或 `need_clarification`/`missing_params` 说明原因或继续澄清。
