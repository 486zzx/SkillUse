---
name: flight-search
description: "国内航班查询：地点→IATA、日期→yyyy-mm-dd、调用聚合数据航班 API、可选筛选排序。Capabilities: 城市/机场/省份解析、自然语言日期、直飞与筛选、多长参数调用。Use for: 查机票、查航班、某地到某地、出发日期、直飞/中转、按价格或时间排序。Scope: 中国境内（含大陆与台湾）；境外不查并提示。Triggers: 查机票、查航班、飞机票、某地到某地、出发地目的地、出发日期、直飞、中转、多段行程、价格排序、起飞时间"
---

# 国内航班查询

根据用户自然语言查询国内航班：解析出发地、目的地与日期，转换为 IATA 与标准日期，调用航班 API，对结果筛选、排序后输出。**推荐**：直接调用总入口 **`scripts/run_flight_search.py`**，传入**多个长参数**（出发地、目的地、日期 为前三个位置参数，可选 `--max-price`、`--sort-by` 等）；每次执行仅查询一段航班。输出为压缩 JSON，模型可自行决定如何呈现。也可分步调用各子脚本，用法见 `scripts/README.md`。

所有脚本**仅通过命令行长参数**接收输入（多个字符串参数），不使用 stdin、不传 JSON。

## 1. 输入输出与范围

- **输入**：自然语言（出发地、目的地、日期、航段/价格/时间/机型等筛选、排序、多段行程）。
- **输出**：航班列表；无法查询或解析失败时给出清晰原因说明。
- **范围**：支持中国境内航班（含大陆与台湾）。**台湾在支持范围内**，如台北、高雄、台湾等均可正常查询；仅当出发地或目的地为**中国境外**（如其他国家/地区）时不发起查询并提示仅支持境内（含台湾）。
- **结果展示**：拿到 API 返回结果（`result.flightInfo`、`result.flightCount`）后，**即应由模型进行输出**，把航班信息呈现给用户。呈现格式不做要求（是否表格、字段详略等由模型自行决定），但**必须完整展示全部航班**：不得折叠航班列表、不得只输出一部分航班、不得用「部分航班」「其余省略」等方式截断。
- **成功但航班为空**：若返回 `success: true` 且 `result.flightInfo` 为空（或 `result.flightCount` 为 0），说明已按目标航线/日期正确调用了 API，但**该日期、该航线上当前没有查到航班**（可能是真的没有航班、或该日无直飞等）。此时应向用户说明「已按您的要求查询，该日期/该航线上暂无航班」，并建议尝试其他日期或航线，不要当作解析或接口错误。

## 2. 地点 → IATA 三字码

**优先调用**：`scripts/location_to_iata.py`。解析优先级为**机场 > 城市 > 省份**（从具体到宽泛），避免「四川成都天府机场」被误解析为省会。

- 数据：脚本从配置的数据目录读取 `city_map.json`、`province_map.json`、`airport_list.json`。
- 用法：**推荐位置参数**，如 `python scripts/location_to_iata.py "西安" "台湾"`。或用 `--json` 时传**双引号 JSON 数组**，如 `--json "[\"西安\",\"台湾\"]"`。勿用 `--json '["西安","台湾"]'`（Windows 下易编码错误得空结果）。
- 输出：`{"iata":"SHA","source":"city","raw":"上海"}` 或数组；`source` 为 airport/city/province/literal 等。

无脚本时，可自行按相同优先级查表：先机场、再城市、再省份。**台湾（台北、高雄等）在数据与支持范围内**，可正常解析并查询；仅当识别到**中国境外**（非大陆、非台湾）时才提示不支持、不发起查询。

## 3. 日期 → yyyy-mm-dd

**优先调用**：`scripts/normalize_date.py`。已安装 jionlp 时使用其解析，否则使用内置规则（今天/明天/后天、N月M日、yyyy-mm-dd）。

- 用法：`python scripts/normalize_date.py "明天"` 或 `python scripts/normalize_date.py "3月5号" --base 2026-03-01`。
- 输出：`{"date":"2026-03-02","source":"simple","raw":"明天"}`，统一得到 **yyyy-mm-dd** 供 API 使用。

API 仅支持按天查询；用户提「小时」「周」等时，先按天请求再在结果中筛选。多日查询时最多展示 **3 天**；跨度超过 3 天则取第一天、中间某天、最后一天。

## 4. 多段行程

用户要求多段（如「明天上海→西安，后天西安→东莞」）时，拆成多段后**每段单独执行一次** `run_flight_search.py`（每次仅查一段），再按行程顺序组织输出。也可用 `scripts/parse_multi_segment.py` 将多段标准化为 IATA + 日期，再对每段分别调 API。

## 5. 筛选与排序

**筛选**：当用户提出价格、起飞时段、机型等条件时，在请求 JSON 的 **`options`** 中只传入用户明确要求的项。**排序**：**仅当用户明确要求**「按价格」「按起飞时间」等时才在 `options` 中传入 `sort_by`；未要求时不要传 `sort_by`，保持 API 返回顺序。

### 5.1 options 参数一览（无需查脚本）

传给 `run_flight_search.py` 的输入 JSON 中，`options` 为可选对象，可包含下表任意组合（仅传用户明确要求的项）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `max_price` | 数字 | 过滤掉参考票价超过此值的航班（如 2000 表示只保留票价 ≤2000 元） |
| `min_departure_time` | 字符串 `"HH:MM"` | 只保留起飞时间**不早于**该时刻的航班（如 `"08:00"` 表示 8 点以后起飞） |
| `max_departure_time` | 字符串 `"HH:MM"` | 只保留起飞时间**不晚于**该时刻的航班 |
| `equipment_contains` | 字符串 | 只保留机型（equipment）中包含该关键词的航班 |
| `sort_by` | 字符串，见下 | 对结果排序；**仅当用户明确要求排序时**才传入 |

**`sort_by` 取值**（仅用户明确说「按价格」「按时间」等时使用）：

| 取值 | 含义 |
|------|------|
| `price_asc` | 按参考票价从低到高 |
| `price_desc` | 按参考票价从高到低 |
| `departure_asc` | 按起飞时间从早到晚 |
| `departure_desc` | 按起飞时间从晚到早 |
| `duration_asc` | 按飞行时长从短到长 |

示例：`"options": {"max_price": 2000, "sort_by": "price_asc"}` 表示只保留票价不超过 2000 元并按价格从低到高排序；`"options": {"min_departure_time": "08:00"}` 表示只保留 8 点以后起飞的航班。

**航班数量**：调用 `scripts/query_flight_api.py` 返回的 JSON 中，成功时 **`result.flightCount`** 即为航班条数，直接用于展示「共 N 班」。

**航段数**：用户**未明确说明**航段要求时，**默认直飞**，即 API 参数 `maxSegments` 传 **`1`**；用户明确说「可中转」「最多 N 段」等时再传 `2`/`3`/`0`。价格、起飞时段、机型等若 API 不支持，可在取得 `flightInfo` 后由该脚本在应用层筛选。**仅当用户明确要求排序时**才传入 `sort_by`，否则**不要对结果排序**，按 API/脚本返回顺序输出。

## 6. 调用航班 API

**优先调用**：`scripts/query_flight_api.py`。参数通过**命令行长参数**传入（整段 JSON）。

- 输入示例：`{"departure":"SHA","arrival":"SIA","departureDate":"2025-12-21","flightNo":"","maxSegments":"1"}`。用户未指定航段时**默认 maxSegments 为 1（直飞）**。
- 输出：聚合 API 完整响应的**压缩 JSON**；成功时含 **`result.flightInfo`** 与 **`result.flightCount`**。**成功但航班为空**：若 `flightInfo` 为空或 `flightCount` 为 0，表示已按条件请求 API 且无报错，但该日期/航线上暂无航班，需向用户说明并建议改日期或航线。失败时根据 `reason`/`error_code` 说明原因。

## 7. 执行流程

**方式一（推荐）**：调用总入口 **`scripts/run_flight_search.py`**，传入**多个长参数**（每次执行仅查一段）：前三个为**出发地、目的地、日期**，可选 `--max-segments`、`--max-price`、`--sort-by` 等。脚本输出压缩 JSON（`success`、`result`）后，**模型即应对用户进行输出**；呈现格式自定，但须**完整展示全部航班**，不得折叠、不得只显示一部分。

#### 7.1 执行命令构造（PowerShell / Linux）

**多长参数**：无需传 JSON，直接传字符串参数即可。

- **环境**：设置 **`FLIGHT_DATA_DIR`** 为本 skill 的 `references` 目录路径；工作目录为项目根或 `scripts` 所在目录均可。
- **必填（位置参数）**：第 1 个 出发地、第 2 个 目的地、第 3 个 日期。可为城市或机场名（如 上海、虹桥、北京）；日期支持「明天」「后天」「3月5号」「2026-03-02」等。
- **可选（--key 值）**：`--max-segments 1`（默认直飞）、`--max-price 2000`、`--sort-by price_asc`、`--min-departure-time 08:00`、`--max-departure-time 22:00`、`--equipment-contains 738`。仅当用户明确要求筛选/排序时才加对应参数。

**PowerShell**

```powershell
$env:FLIGHT_DATA_DIR = "path/to/skill/flight-search/references"
python scripts/run_flight_search.py 上海 北京 明天
python scripts/run_flight_search.py 上海 北京 明天 --max-price 2000 --sort-by price_asc
```

**Linux / Bash**

```bash
export FLIGHT_DATA_DIR="path/to/skill/flight-search/references"
python scripts/run_flight_search.py 上海 北京 明天
python scripts/run_flight_search.py 上海 北京 明天 --max-price 2000 --sort-by price_asc
```

**规则**：前三个参数依次为出发地、目的地、日期；有筛选/排序需求时追加 `--max-price`、`--sort-by` 等。多段行程需**多次执行**，每次传一段的三个参数。

**注意事项**：① 直飞默认：用户未说「可中转」时不传 `--max-segments`（默认 1）。② 排序：仅当用户明确说「按价格」「按时间」等时才加 `--sort-by`。

**方式二（分步）**：
1. 从用户输入提取：出发地、目的地、日期、航段数、筛选/排序、是否多段。
2. **地点 → IATA**：调用 `scripts/location_to_iata.py`。
3. **日期 → yyyy-mm-dd**：调用 `scripts/normalize_date.py`。
4. **多段**：调用 `scripts/parse_multi_segment.py` 得到段列表。
5. **调用 API**：对每段调用 `scripts/query_flight_api.py`。
6. **筛选与排序**：若有条件则调用 `scripts/filter_sort_flights.py`。
7. **直接输出**：根据 `result.flightInfo` 与 `result.flightCount` 在回复中用最简单表格列出。

## 8. 单段请求结构示例

```json
{
  "departure": "SHA",
  "arrival": "SIA",
  "departureDate": "2025-12-21",
  "flightNo": "",
  "maxSegments": "1"
}
```

多段时为多组上述结构。用户未指定航段时请求中 **maxSegments 填 "1"（直飞）**。筛选与排序仅在用户明确要求时在应用层执行。

**单段请求示例汇总**（多长参数，无需 JSON）：

| 用户说法 | 命令示例 |
|----------|----------|
| 明天上海到成都的机票 | `run_flight_search.py 上海 成都 明天` |
| 后天北京飞西安，只要直飞 | `run_flight_search.py 北京 西安 后天` |
| 3月5号虹桥到天府，价格不超过 1500 | `run_flight_search.py 虹桥 天府 3月5号 --max-price 1500` |
| 明天上海到成都，按价格从低到高 | `run_flight_search.py 上海 成都 明天 --sort-by price_asc` |
| 上海飞成都，明天早上 8 点以后起飞 | `run_flight_search.py 上海 成都 明天 --min-departure-time 08:00` |

## 9. 数据与配置

- **数据目录**：默认为本 skill 下 **references/**（含 `city_map.json`、`province_map.json`、`airport_list.json`）；可通过环境变量 **FLIGHT_DATA_DIR** 覆盖。
- **脚本依赖**：可选 `pip install -r requirements.txt`（jionlp 用于更丰富的日期解析）。

## 10. 脚本参数速查

**总入口**：`run_flight_search.py` — 单次调用完成全流程，输入 JSON（见下），输出最终结果 JSON，模型据此整理即可。

| 脚本 | 入口 | 关键参数/输入 | 输出 |
|------|------|----------------|------|
| **`run_flight_search.py`** | **多长参数** | **必填**：出发地 目的地 日期（三个位置参数）。**可选**：`--max-segments 1`、`--max-price N`、`--sort-by price_asc`、`--min-departure-time 08:00` 等。每次执行仅查一段。示例：`python run_flight_search.py 上海 北京 明天` | **压缩 JSON**：`{success, result: {flightInfo, flightCount}}`；失败 `{success:false, error}` |
| `location_to_iata.py` | **位置参数** 或 `--json` | 多个地点：位置参数 `"西安" "台湾"` 或 `--json "[\"西安\",\"台湾\"]"` | `{"iata":"SHA","source":"city",...}` 或数组 |
| `normalize_date.py` | **位置参数** 或 `--json` | 日期串；可选 `--base yyyy-mm-dd` | `{"date":"yyyy-mm-dd",...}` 或数组 |
| `parse_multi_segment.py` | **长参数（JSON）** | `[{"origin","destination","date"}, ...]` | `[{"departure","arrival","departureDate"}, ...]` |
| `query_flight_api.py` | **长参数（JSON）** | `departure`、`arrival`、`departureDate`、`maxSegments`（未指定则 `"1"`） | API 完整响应，成功时含 **`result.flightCount`**；失败为 `{error,...}` |
| `filter_sort_flights.py` | **长参数（JSON）** 或 `--file <path>` | `flightInfo` + 可选 `options` | 筛选/排序后的 `flightInfo` 数组 |
