---
name: weather-query
description: "天气查询：基于心知天气 API，根据城市/地点查询实况与逐日预报，可选生活指数与空气质量。Capabilities: 心知 now/daily/suggestion/air、中文地点、私钥或签名认证。Use for: 查天气、某地天气、今天明天天气、气温、穿衣建议、空气质量、PM2.5。Triggers: 天气、气温、下雨、明天天气、北京天气、查天气、穿衣、空气质量"
---

# 天气查询（心知天气）

根据用户自然语言查询天气：解析地点（城市中文名/拼音/英文/经纬度），调用**心知天气 API** 获取实况、逐日预报，可选生活指数与空气质量，输出统一 JSON。**推荐**：直接调用总入口 **`scripts/run_weather_search.py`**，传入**位置参数**（地点必填，日期可选）；脚本输出压缩 JSON，由模型整理后呈现给用户。

所有脚本**仅通过命令行长参数**接收输入，不使用 stdin、不传 JSON。

## 1. 输入输出与范围

- **输入**：自然语言（地点、可选日期如今天/明天/昨天、或「未来几天」）；可选「要生活指数」「要空气质量」。
- **输出**：当前天气（实况）+ 逐日预报；可选生活指数、空气质量；解析或 API 失败时给出清晰原因。
- **范围**：心知支持全国约 3156、全球约 24,962 个城市；**生活指数仅支持中国城市**。
- **结果展示**：拿到 API 返回后，**由模型进行输出**，把天气信息用自然语言或表格呈现；不得截断关键字段。

## 2. 认证（必配）

- **方式一**：环境变量 **`SENIVERSE_KEY`** = 心知私钥（从 [心知产品管理](https://www.seniverse.com/products) 获取），请求时传 `key=xxx`。
- **方式二**：签名验证（推荐生产环境）：**`SENIVERSE_UID`**（公钥）+ **`SENIVERSE_PRIVATE_KEY`**（私钥，仅用于生成签名）；脚本按心知规范生成 `ts`、`ttl`、`sig` 与请求一起发送，不传 key。

未配置时脚本返回 `success: false`，提示配置 SENIVERSE_KEY 或签名参数。

## 3. 地点（location）

心知 **location** 支持多种形式，脚本直接透传（必要时可用 references/city_map 做中文别名→标准名）：

| 形式 | 示例 |
|------|------|
| 城市中文名 | 北京、上海 |
| 拼音/英文名 | beijing、shanghai |
| 城市 ID | WX4FBXXFKE4F |
| 经纬度 | 纬度:经度（如 39.9:116.4） |

无需单独地理编码接口；心知接口直接接受上述 location。

## 4. 日期与预报范围

- **未指定日期**：仅返回**实况**（current）+ 默认 3 天逐日（今日起）。
- **指定「今天」**：实况 + 逐日，start=0，从今天起。
- **指定「明天」「后天」**：start=1 或 2，从该日起的逐日。
- **指定「昨天」「前天」**：start=-1 或 -2，逐日接口可查历史单日。
- **具体日期**：start=yyyy/m/d（如 2026/3/5），days=1 或更多。
- **天数**：`--days N`，免费版一般 3 天，付费最多 15 天；脚本默认 3。

### 4.1 模糊时间与调用约定（重要）

为提高模糊时间场景下的识别准确性，约定如下：

- **大模型**：只**原样抽取**用户输入中的时间字段（如「明天」「下周一下午」「3月5号」），**不做**时间解析或推理；将抽取到的**原始时间字符串**作为第二个位置参数传给 `run_weather_search.py`。
- **脚本**：由 `run_weather_search.py` 使用 **JioNLP** 对传入的原始时间字符串进行语义解析，得到心知 API 所需的 start 参数（0/1/2/-1/-2 或 yyyy/m/d）。

## 5. 调用的心知接口

| 能力 | 心知路径 | 说明 |
|------|----------|------|
| 实况 | GET /v3/weather/now.json | 当前温度、体感、天气现象、风力等；免费约 3 项。 |
| 逐日 | GET /v3/weather/daily.json | start、days；免费 3 天，付费 15 天。 |
| 生活指数 | GET /v3/life/suggestion.json | 穿衣、紫外线等；**仅中国城市**；可选 `--with-suggestion`。 |
| 空气质量 | GET /v3/air/now.json | AQI、PM2.5、PM10 等；可选 `--with-air`。 |

基础 URL：`https://api.seniverse.com`。成功时脚本返回 `success: true` 与 `result`；失败返回 `success: false` 与 `error`。

## 6. 执行流程

**推荐**：调用总入口 **`scripts/run_weather_search.py`**，传入**位置参数**。

### 6.1 命令构造（PowerShell / Linux）

- **必填（位置参数）**：第 1 个为**地点**（如 北京、上海、beijing）。
- **可选（位置参数）**：第 2 个为**日期**（今天、明天、后天、昨天、前天、或 `yyyy-mm-dd`）；不传则从今天起查逐日。
- **可选（--key 值）**：`--days 5`（逐日天数，默认 3）、`--with-suggestion`（拉取生活指数）、`--with-air`（拉取空气质量）、`--language zh-Hans`、`--unit c`。

**PowerShell**

```powershell
$env:SENIVERSE_KEY = "你的私钥"
python scripts/run_weather_search.py 北京
python scripts/run_weather_search.py 上海 明天 --days 5
python scripts/run_weather_search.py 北京 --with-suggestion --with-air
```

**Linux / Bash**

```bash
export SENIVERSE_KEY="你的私钥"
python scripts/run_weather_search.py 北京
python scripts/run_weather_search.py 上海 明天 --days 5
python scripts/run_weather_search.py 北京 --with-suggestion --with-air
```

**规则**：第一个参数为地点，第二个可选为日期；需要生活指数/空气质量时加对应 flag。

## 7. 输出结构示例

成功时输出压缩 JSON，例如：

```json
{"success":true,"result":{"location":{"name":"北京","id":"WX4FBXXFKE4F"},"current":{"text":"晴","code":"0","temperature":"5","feels_like":"2"},"daily":[{"date":"2026-03-04","high":"8","low":"-1","text_day":"晴","text_night":"多云"}],"suggestion":{},"air":{}}}
```

- `result.location`：地点名、ID（若有）。
- `result.current`：实况（text、code、temperature、feels_like 等；免费版字段可能较少）。
- `result.daily`：逐日数组，每项含 date、high、low、text_day、text_night、降水等（以心知实际返回为准）。
- `result.suggestion`：生活指数（仅当请求带 `--with-suggestion` 且为中国城市时有内容）。
- `result.air`：空气质量（仅当请求带 `--with-air` 时有内容）。

## 8. 脚本参数速查

| 脚本 | 入口 | 关键参数 | 输出 |
|------|------|----------|------|
| **run_weather_search.py** | 位置参数 | 必填：地点。可选：日期、`--days N`、`--with-suggestion`、`--with-air`、`--language`、`--unit` | 压缩 JSON：`{success, result: {location, current, daily, suggestion?, air?}}` 或 `{success:false, error}` |

## 9. 数据与依赖

- **API**：心知天气 v3（实况、逐日、生活指数、空气质量），需 API Key 或签名，见 [心知天气-API接口文档](references/心知天气-API接口文档.md)。
- **依赖**：`requests`、`jionlp`（时间语义解析）；Python 3.8+。
- **环境变量**：`SENIVERSE_KEY`（私钥）或 `SENIVERSE_UID` + `SENIVERSE_PRIVATE_KEY`（签名）；可选 `WEATHER_DATA_DIR` 指向 references 目录。
- **references**：可选 `city_map.json` 做地点别名；详见 [心知天气-需求场景与特性设计方案](references/心知天气-需求场景与特性设计方案.md)。

## 10. 触发场景

当用户表达以下意图时使用本 skill：查天气、某地天气、今天/明天/后天/昨天天气、气温、会不会下雨、穿衣建议、紫外线、空气质量、PM2.5、北京/上海/xx 天气。

## 11. 参考文档

- **心知天气接口文档**： [references/心知天气-API接口文档.md](references/心知天气-API接口文档.md)
- **心知天气需求与特性设计**： [references/心知天气-需求场景与特性设计方案.md](references/心知天气-需求场景与特性设计方案.md)
- **测试用例与评估方法**： [references/测试用例与评估方法.md](references/测试用例与评估方法.md) — 单元/功能/系统测试用例与通过标准、覆盖率与 CI 建议。
- **Open-Meteo 接口与设计**（备用数据源）： [references/API-接口文档.md](references/API-接口文档.md)、 [references/需求场景与特性设计方案.md](references/需求场景与特性设计方案.md)
