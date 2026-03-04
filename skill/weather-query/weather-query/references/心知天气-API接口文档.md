# 心知天气 API 接口文档

本文档基于心知天气官方文档与公开资料整理。您提供的 [心知天气 API 使用手册（V4版）· 语雀](https://seniverse.yuque.com/hyper_data/api_v4) 在抓取时超时无法直接解析，以下内容整理自 [心知天气官方文档](https://docs.seniverse.com/)（docs.seniverse.com）及公开接口说明；若语雀 V4 与本文有差异，请以语雀或官方最新文档为准。

---

## 一、接口总览

| 分类 | 接口 | 路径/端点 | 用途 | 认证 |
|------|------|-----------|------|------|
| 通用 | 使用说明 | [start](https://docs.seniverse.com/api/start/start.html) | 服务说明、调用约定 | 需 KEY |
| 通用 | 通用参数 | [common](https://docs.seniverse.com/api/start/common.html) | location / language / unit 等 | - |
| 通用 | 密钥与签名 | [key](https://docs.seniverse.com/api/start/key.html)、[validation](https://docs.seniverse.com/api/start/validation.html) | 私钥、公钥、签名验证 | 必选其一 |
| 天气 | 天气实况 | `/v3/weather/now.json` | 当前温度、体感、现象、风力等 | 需 KEY |
| 天气 | 逐日预报 | `/v3/weather/daily.json` | 最多 15 天日预报（免费 3 天） | 需 KEY |
| 天气 | 24 小时逐时 | `/v3/weather/hourly.json` | 未来 24 小时逐小时 | 需 KEY |
| 天气 | 15 天逐 3 小时 | `/v3/weather/hourly3h.json` | 精细化 3h/6h/12h 预报 | 需 KEY |
| 空气 | 空气质量实况 | `/v3/air/now.json` | AQI、PM2.5、PM10 等 | 需 KEY |
| 生活 | 生活指数 | `/v3/life/suggestion.json` | 穿衣、紫外线等 27 项（中国城市） | 需 KEY |
| 地理/功能 | 城市搜索 | [fct/search](https://docs.seniverse.com/api/fct/search.html) | 城市 ID、名称、层级、时区 | 需 KEY |

**基础 URL**：`https://api.seniverse.com`（具体以官方文档为准）。  
**数据覆盖**：全国约 3156 个、全球约 24,962 个城市和地点。

---

## 二、认证方式

### 2.1 私钥直接请求

- 请求中携带参数 **`key`** = 你的私钥（从 [心知产品管理](https://www.seniverse.com/products) 获取）。
- 简单易用，但 key 暴露在请求中，适合内网或临时调试。

### 2.2 公钥 + 签名验证（推荐）

- 请求中不传私钥，改为：**`uid`**（公钥）+ **`ts`**（时间戳）+ **`ttl`**（可选，有效期秒，默认 1800）+ **`sig`**（签名）。
- **签名生成**（参考 [使用签名验证方式](https://docs.seniverse.com/api/start/validation.html)）：
  1. 将参数按**字典升序**排列，用 `&` 拼接，例如：`ts=1443079775&ttl=300&uid=你的公钥`
  2. 使用**私钥**对上述字符串做 **HMAC-SHA1**
  3. 将结果 **Base64** 编码后再 **URL 编码** 得到 `sig`
  4. 请求中附带：`ts`、`ttl`、`uid`、`sig`

---

## 三、通用参数（多数接口共用）

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| key | String | 是* | - | API 私钥（与签名二选一）。 |
| location | Location | 是 | - | 查询位置，见下表。 |
| language | String | 否 | zh-Hans | 返回语言：zh-Hans、en、ja 等。 |
| unit | String | 否 | c | **c**：摄氏、km/h；**f**：华氏、mph。 |

\* 使用签名验证时改为 uid + ts + ttl + sig，不传 key。

### 3.1 location 支持形式

（据 [接口中的通用参数](https://docs.seniverse.com/api/start/common.html)）

| 形式 | 示例 |
|------|------|
| 城市 ID | WX4FBXXFKE4F |
| 城市中文名 | 北京、上海 |
| 拼音/英文名 | beijing、shanghai |
| 经纬度 | 纬度:经度（如 39.9:116.4） |
| IP 地址 | 或使用请求方 IP 自动识别 |

---

## 四、天气实况（now）

**请求**：`GET https://api.seniverse.com/v3/weather/now.json`

### 4.1 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| key（或签名参数） | 是 | 认证。 |
| location | 是 | 地点。 |
| language | 否 | 默认 zh-Hans。 |
| unit | 否 | 默认 c。 |

### 4.2 返回示例与字段（概念）

- **免费用户**：通常仅返回天气现象文字、现象代码、气温等少量字段。
- **付费用户**：可包含体感温度、气压、湿度、能见度、风向、风速、风力等级等。

典型字段（具体以实际响应为准）：天气现象文字、天气现象代码、温度、体感温度、气压、相对湿度、能见度、风向、风速、风力等级。

### 4.3 请求示例

```
https://api.seniverse.com/v3/weather/now.json?key=你的私钥&location=beijing&language=zh-Hans&unit=c
```

---

## 五、逐日天气预报（daily）

**请求**：`GET https://api.seniverse.com/v3/weather/daily.json`

### 5.1 参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| key（或签名） | - | 是 | - | 认证。 |
| location | Location | 是 | - | 地点。 |
| language | String | 否 | zh-Hans | 语言。 |
| unit | String | 否 | c | 单位。 |
| start | Int 或 日期 | 否 | 0 | **0**=今天，**1**=明天，**-1**=昨天，**-2**=前天；或 **yyyy/m/d** 如 2015/10/1。 |
| days | Int | 否 | - | 预报天数。免费一般 3 天，付费最多 15 天。 |

### 5.2 返回概念

- 按「日」聚合的预报：日期、日最高/最低温、白天/夜间天气现象、降水等（字段名以实际 API 为准）。

### 5.3 请求示例

```
https://api.seniverse.com/v3/weather/daily.json?key=你的私钥&location=北京&start=0&days=5
```

---

## 六、24 小时逐小时预报（hourly）

**请求**：`GET https://api.seniverse.com/v3/weather/hourly.json`

### 6.1 参数

与通用参数一致：key（或签名）、location、language、unit。部分接口可能支持 `start`/`hours` 等（以官方文档为准）。

### 6.2 返回概念

- 未来 24 小时逐小时的天气：时间、温度、天气现象、降水、风速等。

文档参考：[24小时逐小时天气预报](https://docs.seniverse.com/api/weather/hourly.html)。

---

## 七、15 天逐 3 小时精细化预报（hourly3h）

**请求**：`GET https://api.seniverse.com/v3/weather/hourly3h.json`

### 7.1 参数

key（或签名）、location、language、unit 等通用参数。

### 7.2 数据规则（概念）

- **未来 3 天**：逐 3 小时一条。
- **未来 4–6 天**：逐 6 小时。
- **未来 7–15 天**：逐 12 小时。

返回字段可包含：预报时刻、天气现象代码、温度、最高/最低温、湿度、降水量、风速、风力等级、云量、体感温度等。详见 [15天逐3小时精细化天气预报](https://docs.seniverse.com/api/weather/hourly3h.html)。

---

## 八、空气质量实况（air/now）

**请求**：`GET https://api.seniverse.com/v3/air/now.json`

### 8.1 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| key（或签名） | 是 | 认证。 |
| location | 是 | 地点。 |
| language | 否 | 默认 zh-Hans。 |
| scope | 否 | 如 **city** 表示城市级别。 |

### 8.2 返回概念

- AQI、PM2.5、PM10、SO₂、NO₂、CO、O₃、首要污染物、空气质量类别（优/良/轻度污染等）。详见 [空气质量实况](https://docs.seniverse.com/api/air/now.html)。

### 8.3 请求示例

```
https://api.seniverse.com/v3/air/now.json?key=你的私钥&location=beijing&language=zh-Hans&scope=city
```

---

## 九、生活指数（life/suggestion）

**请求**：`GET https://api.seniverse.com/v3/life/suggestion.json`

### 9.1 参数

key（或签名）、location、language。**仅支持中国城市**。

### 9.2 返回概念

- **5 大类、共 27 项**生活指数；**免费用户**一般仅返回 6 项基本类（如穿衣、紫外线等）。
- 类别大致包括：基本类、交通类、生活类、运动类、健康类。详见 [生活指数](https://docs.seniverse.com/api/life/suggestion.html)。

---

## 十、城市搜索（地理/功能）

**文档**：[城市搜索](https://docs.seniverse.com/api/fct/search.html)

### 10.1 功能

- 按**拼音**（如 suzhou）、**中文名**（如 上海）、**IP**（如 202.108.33.60）等查询。
- 返回：城市 ID、城市名称、国家代码、隶属层级、时区等，用于后续作为 `location` 调用天气接口。

---

## 十一、其他模块（概要）

官方文档中还包含以下模块，具体路径与参数以 [心知天气产品文档](https://www.seniverse.com/docs) 为准：

| 类别 | 说明 |
|------|------|
| 地理类 | 潮汐等地理信息。 |
| 海洋类 | 海洋相关数据。 |
| 农业类 | 农业天气数据。 |
| 气象图层 | 图层数据（如降水 rain 等）。 |
| 公里级网格 | 高精度网格天气。 |

---

## 十二、错误与限制

- **认证失败**：key 无效或签名错误时，接口会返回相应错误信息。
- **免费与付费**：免费版在实况、逐日、生活指数等接口上字段或天数会有限制（如实况仅 3 项、逐日 3 天、生活指数 6 项）。
- **地域限制**：生活指数仅支持中国城市；其他接口以官方说明为准。
- **限流**：请遵守心知天气的调用频率与配额规定。

---

## 十三、参考链接

- [心知天气 API 使用手册（V4版）· 语雀](https://seniverse.yuque.com/hyper_data/api_v4)（您提供的文档）
- [心知天气官方文档 - 使用说明](https://docs.seniverse.com/api/start/start.html)
- [通用参数](https://docs.seniverse.com/api/start/common.html)
- [天气实况](https://docs.seniverse.com/api/weather/now.html)
- [逐日天气预报和昨日天气](https://docs.seniverse.com/api/weather/daily.html)
- [24小时逐小时天气预报](https://docs.seniverse.com/api/weather/hourly.html)
- [15天逐3小时精细化天气预报](https://docs.seniverse.com/api/weather/hourly3h.html)
- [空气质量实况](https://docs.seniverse.com/api/air/now.html)
- [生活指数](https://docs.seniverse.com/api/life/suggestion.html)
- [城市搜索](https://docs.seniverse.com/api/fct/search.html)
- [密钥与签名验证](https://docs.seniverse.com/api/start/key.html)、[签名验证方式](https://docs.seniverse.com/api/start/validation.html)

---

*本文档根据心知天气官方文档与公开资料整理，若与语雀 V4 或官方最新版不一致，请以心知天气官方/语雀文档为准。*
