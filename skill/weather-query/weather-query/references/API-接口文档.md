# Open-Meteo 天气查询 API 接口文档

基于 [Open-Meteo](https://open-meteo.com/) 官方文档整理，覆盖地理编码、天气预报、空气质量、海洋、历史与洪水等接口全集。

---

## 一、接口总览

| 接口 | 端点 | 用途 | 认证 |
|------|------|------|------|
| 地理编码 | `geocoding-api.open-meteo.com/v1/search` | 地名/邮编 → 经纬度、时区 | 非商业无需 KEY |
| 天气预报 | `api.open-meteo.com/v1/forecast` | 当前 + 逐时/逐日预报（最多 16 天） | 非商业无需 KEY |
| 空气质量 | `air-quality.api.open-meteo.com/v1/air-quality` | 污染物与花粉预报（约 11 km） | 非商业无需 KEY |
| 海洋天气 | `marine-api.open-meteo.com/v1/marine` | 海浪、海温、潮位、海流等 | 非商业无需 KEY |
| 历史天气 | `archive-api.open-meteo.com/v1/archive` | 1940 年至今历史数据 | 非商业无需 KEY |
| 洪水 | `flood-api.open-meteo.com/v1/flood` | 河流流量/洪水模拟（约 5 km） | 非商业无需 KEY |

商业使用需 apikey，且服务器 URL 使用 `customer-` 前缀。以下仅描述非商业用法。

---

## 二、地理编码 API（Geocoding）

**端点**：`https://geocoding-api.open-meteo.com/v1/search`

### 2.1 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| name | String | 是 | - | 搜索词（地名或邮编）。空或 1 字符返回空；2 字符仅精确匹配；≥3 字符模糊匹配。 |
| count | Integer | 否 | 10 | 返回结果数量，最多 100。 |
| format | String | 否 | json | json 或 protobuf。 |
| language | String | 否 | en | 结果语言（小写）。 |
| countryCode | String | 否 | - | ISO-3166-1 alpha2 国家码，用于过滤。 |

### 2.2 响应示例与字段

```json
{
  "results": [
    {
      "id": 2950159,
      "name": "Berlin",
      "latitude": 52.52437,
      "longitude": 13.41053,
      "elevation": 74.0,
      "feature_code": "PPLC",
      "country_code": "DE",
      "timezone": "Europe/Berlin",
      "population": 3426354,
      "country": "Deutschland",
      "admin1": "Berlin",
      "admin2": "",
      "admin3": "Berlin, Stadt",
      "admin4": "Berlin"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| id | 地点唯一 ID，可用 `/v1/get?id=xxx` 解析 |
| name | 地点名（受 language 影响） |
| latitude, longitude | WGS84 经纬度 |
| elevation | 海拔（米） |
| timezone | 时区（如 Europe/Berlin） |
| country_code, country | 国家码与国家名 |
| admin1~admin4 | 行政区划层级名称 |

### 2.3 错误

参数错误等返回 HTTP 400 及 JSON：`{"error": true, "reason": "..."}`。

---

## 三、天气预报 API（Forecast）

**端点**：`https://api.open-meteo.com/v1/forecast`

### 3.1 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| latitude, longitude | Float | 是 | - | WGS84 经纬度；多地点用逗号分隔，返回变为列表。 |
| elevation | Float | 否 | DEM | 海拔（米），用于订正；多地点可逗号分隔。 |
| hourly | String | 否 | - | 逐时变量，逗号分隔，见下表。 |
| daily | String | 否 | - | 逐日变量，逗号分隔；使用 daily 时建议传 timezone。 |
| current | String | 否 | - | 当前天气变量，逗号分隔。 |
| temperature_unit | String | 否 | celsius | celsius / fahrenheit。 |
| wind_speed_unit | String | 否 | kmh | kmh / ms / mph / kn。 |
| precipitation_unit | String | 否 | mm | mm / inch。 |
| timezone | String | 否 | GMT | 时区名或 `auto`（按坐标解析）。 |
| timeformat | String | 否 | iso8601 | iso8601 / unixtime。 |
| past_days | Integer | 否 | 0 | 0–92，包含过去几天。 |
| forecast_days | Integer | 否 | 7 | 0–16，预报天数。 |
| start_date, end_date | String (yyyy-mm-dd) | 否 | - | 日期区间。 |
| start_hour, end_hour | String (ISO8601) | 否 | - | 逐时数据时间区间。 |
| models | String | 否 | auto | 指定气象模型。 |
| cell_selection | String | 否 | land | land / sea / nearest。 |
| apikey | String | 否 | - | 商业用。 |

### 3.2 逐时变量（hourly）选列

| 变量 | 时间类型 | 单位 | 说明 |
|------|----------|------|------|
| temperature_2m | 瞬时 | °C/°F | 2 m 气温 |
| relative_humidity_2m | 瞬时 | % | 2 m 相对湿度 |
| dew_point_2m | 瞬时 | °C/°F | 2 m 露点 |
| apparent_temperature | 瞬时 | °C/°F | 体感温度 |
| pressure_msl, surface_pressure | 瞬时 | hPa | 海平面/地面气压 |
| cloud_cover, cloud_cover_low/mid/high | 瞬时 | % | 总/低/中/高云量 |
| precipitation | 前一小时合计 | mm | 总降水 |
| rain, showers, snowfall | 前一小时合计 | mm/cm | 雨、阵雨、雪 |
| precipitation_probability | 前一小时概率 | % | 降水概率 |
| weather_code | 瞬时 | WMO | 天气现象码（见 WMO 码表） |
| wind_speed_10m, wind_direction_10m | 瞬时 | km/h, ° | 10 m 风速、风向 |
| wind_gusts_10m | 前一小时最大 | km/h | 阵风 |
| visibility | 瞬时 | m | 能见度 |
| snow_depth | 瞬时 | m | 雪深 |
| shortwave_radiation, direct_radiation, diffuse_radiation | 前一小时平均 | W/m² | 短波/直接/散射辐射 |
| uv_index | 瞬时 | - | 紫外线指数 |
| is_day | 瞬时 | - | 1=白天 0=夜间 |

### 3.3 逐日变量（daily）选列

| 变量 | 单位 | 说明 |
|------|------|------|
| temperature_2m_max, temperature_2m_min | °C/°F | 日最高/最低温 |
| apparent_temperature_max/min | °C/°F | 日体感最高/最低 |
| precipitation_sum, rain_sum, showers_sum, snowfall_sum | mm/cm | 日降水/雨/阵雨/雪合计 |
| precipitation_hours | 小时 | 有降水小时数 |
| precipitation_probability_max/mean/min | % | 降水概率 |
| weather_code | WMO | 当日最重天气现象 |
| sunrise, sunset | ISO8601 | 日出日落 |
| sunshine_duration, daylight_duration | 秒 | 日照时长、昼长 |
| wind_speed_10m_max, wind_gusts_10m_max | km/h | 日最大风速、阵风 |
| wind_direction_10m_dominant | ° | 主导风向 |
| shortwave_radiation_sum | MJ/m² | 日短波辐射合计 |
| uv_index_max, uv_index_clear_sky_max | 指数 | 日最大 UV |
| et0_fao_evapotranspiration | mm | 日参考蒸散 |

### 3.4 当前天气（current）

与 hourly 同名字段含义一致，为“当前时刻”的瞬时或前 15 分钟聚合。常用组合示例：

`current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,precipitation`

### 3.5 15 分钟数据（minutely_15）

参数 `minutely_15=` 可请求 15 分钟分辨率；区域依赖 NOAA HRRR、DWD ICON-D2、Météo-France AROME 等，其他区域可能由逐时插值得到。

### 3.6 气压层变量（pressure level）

支持 1000–30 hPa 多层级：`temperature_1000hPa`、`relative_humidity_850hPa`、`wind_speed_500hPa`、`geopotential_height_500hPa` 等。

### 3.7 响应结构

```json
{
  "latitude": 52.52,
  "longitude": 13.419,
  "elevation": 44.812,
  "generationtime_ms": 2.21,
  "utc_offset_seconds": 3600,
  "timezone": "Europe/Berlin",
  "timezone_abbreviation": "CEST",
  "current": {
    "time": "2022-07-01T12:00",
    "interval": 900,
    "temperature_2m": 22.5,
    "relative_humidity_2m": 65,
    "weather_code": 1
  },
  "hourly": {
    "time": ["2022-07-01T00:00", "2022-07-01T01:00", ...],
    "temperature_2m": [13, 12.7, ...]
  },
  "hourly_units": { "temperature_2m": "°C" },
  "daily": {
    "time": ["2022-07-01", "2022-07-02", ...],
    "temperature_2m_max": [24, 26, ...],
    "temperature_2m_min": [12, 14, ...]
  },
  "daily_units": { "temperature_2m_max": "°C" }
}
```

### 3.8 WMO 天气现象码（简要）

| 码 | 描述 | 码 | 描述 |
|----|------|----|------|
| 0 | 晴 | 45, 48 | 雾、冻雾 |
| 1–3 | 少云、多云、阴 | 51–57 | 毛毛雨、冻毛毛雨 |
| 61–67 | 雨、冻雨 | 71–77 | 雪、雪粒 |
| 80–82 | 小/中/大阵雨 | 85–86 | 小/大雪阵雨 |
| 95 | 雷暴 | 96, 99 | 雷暴+小/大冰雹 |

---

## 四、空气质量 API（Air Quality）

**端点**：`https://air-quality.api.open-meteo.com/v1/air-quality`

### 4.1 主要参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| latitude, longitude | Float | 是 | - | WGS84 坐标。 |
| hourly | String | 否 | - | 逐时变量：如 pm10, pm2_5, nitrogen_dioxide, ozone 等。 |
| current | String | 否 | - | 当前污染物/花粉。 |
| timezone | String | 否 | GMT | 时区或 auto。 |
| forecast_days | Integer | 否 | 5 | 预报天数。 |
| past_days | Integer | 否 | 0 | 过去天数。 |

### 4.2 响应示例

```json
{
  "latitude": 52.52,
  "longitude": 13.419,
  "timezone": "Europe/Berlin",
  "hourly": {
    "time": ["2022-07-01T00:00", ...],
    "pm10": [1, 1.7, ...],
    "pm2_5": [0.5, ...]
  },
  "hourly_units": { "pm10": "μg/m³" }
}
```

---

## 五、海洋天气 API（Marine）

**端点**：`https://marine-api.open-meteo.com/v1/marine`

### 5.1 主要参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| latitude, longitude | Float | 是 | - | WGS84 坐标（海上或沿岸）。 |
| hourly | String | 否 | - | 逐时：wave_height, wave_direction, wave_period, swell_wave_height 等。 |
| daily | String | 否 | - | 逐日：wave_height_max, swell_wave_height_max 等。 |
| current | String | 否 | - | 当前海浪/海温等。 |
| timezone | String | 否 | GMT | 时区或 auto。 |
| forecast_days | Integer | 否 | 5 | 最多约 8 天。 |
| length_unit | String | 否 | metric | metric / imperial。 |
| cell_selection | String | 否 | sea | land / sea / nearest。 |

### 5.2 常用变量

| 变量 | 说明 |
|------|------|
| wave_height, wave_direction, wave_period | 有效波高、波向、周期 |
| wind_wave_height, swell_wave_height | 风浪、涌浪波高 |
| sea_surface_temperature | 海表温度 |
| sea_level_height_msl | 含潮位等的海平面高度 |
| ocean_current_velocity, ocean_current_direction | 海流流速与方向 |

---

## 六、历史天气 API（Historical / Archive）

**端点**：`https://archive-api.open-meteo.com/v1/archive`

### 6.1 主要参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| latitude, longitude | Float | 是 | - | WGS84 坐标。 |
| start_date, end_date | String (yyyy-mm-dd) | 是 | - | 查询日期区间。 |
| hourly | String | 否 | - | 与 Forecast 类似的逐时变量名。 |
| daily | String | 否 | - | 逐日聚合变量。 |
| timezone | String | 否 | GMT | 时区或 auto。 |
| temperature_unit, wind_speed_unit, precipitation_unit | String | 否 | 同 Forecast | 单位。 |

### 6.2 数据源与时间范围

- **ECMWF IFS**：约 9 km，2017 年至今，逐小时。
- **ERA5**：约 0.25°，1940 年至今，逐小时，约 5 天延迟。
- **ERA5-Land**：约 0.1°，1950 年至今。
- **CERRA**：欧洲约 5 km，1985–2021 年 6 月。

长时间气候分析建议仅用 ERA5 或 ERA5-Land 以保证一致性。

### 6.3 响应结构

与 Forecast 类似：`latitude`, `longitude`, `timezone`, `hourly`, `hourly_units`, `daily`, `daily_units` 等。

---

## 七、洪水 API（Flood）

**端点**：`https://flood-api.open-meteo.com/v1/flood`

### 7.1 主要参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| latitude, longitude | Float | 是 | - | WGS84 坐标。 |
| daily | String | 否 | - | 如 river_discharge, river_discharge_mean, river_discharge_max 等。 |
| timezone | String | 否 | GMT | 时区。 |
| forecast_days | Integer | 否 | 约 3 个月 | 预报长度。 |

### 7.2 响应示例

```json
{
  "latitude": 59.9,
  "longitude": 10.75,
  "timezone": "GMT",
  "daily_units": { "river_discharge": "m³/s" },
  "daily": {
    "time": ["2025-03-03", "2025-03-04", ...],
    "river_discharge": [8.04, 8.75, ...]
  }
}
```

---

## 八、通用说明

### 8.1 单位与时间

- 温度：celsius / fahrenheit。
- 风速：kmh / ms / mph / kn。
- 降水：mm / inch。
- 时间：默认 ISO8601；可选 unixtime（GMT+0，日界需加 utc_offset_seconds）。

### 8.2 多地点请求

Forecast / Archive 等支持 `latitude=52.52,48.85` 与 `longitude=13.41,2.35`，响应变为**数组**，每项对应一个地点；CSV/XLSX 会多一列 `location_id`。

### 8.3 错误响应

参数错误等返回 HTTP 400，Body 示例：

```json
{
  "error": true,
  "reason": "Cannot initialize WeatherVariable from invalid String value ..."
}
```

### 8.4 数据源与引用

- 预报：多国气象局数值模式（如 DWD ICON、NOAA GFS、ECMWF IFS、CMA 等），按区域自动选择。
- 历史：ERA5、ERA5-Land、CERRA、IFS 等再分析。
- 海洋：MétéoFrance MFWAM、ECMWF WAM、NCEP GFS Wave 等。
- 使用数据时请按官网要求进行引用与归属说明。

---

*文档整理自 Open-Meteo 官方文档，以官网最新说明为准。*
