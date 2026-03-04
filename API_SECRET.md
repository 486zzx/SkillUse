# 各 Skill 的 API Key 配置说明


| Skill | 环境变量 / 配置项 | 读取位置 | 说明 | 配置类型 | API KEY | api文档 |
|-------|------------------|:---------|----------------|----------|----------|----------|
| **train-ticket-search** | `JUHE_TRAIN_API_KEY` | `skill/train-ticket-search/scripts/query_api.py` | 聚合数据-火车查询 | evals/集成测试依赖， 可在 skill 根目录建 `.env` | 联系zhangzhenxiong获取 | https://www.juhe.cn/docs/api/id/817 |
| **weather-query** | `SENIVERSE_KEY` | `skill/weather-query/scripts/run_weather_search.py` | 心知天气 |  | 联系zhangzhenxiong获取 | https://seniverse.yuque.com/hyper_data/api_v3/nyiu3t |
| **surround-search** | `AMAP_KEY` | `skill/surround-search/scripts/run_surround_search.py` | 高德 Web 服务 API |  | 联系zhangzhenxiong获取 | 文档：https://lbs.amap.com/api/webservice/guide/api-advanced/search#t5:~:text=%E7%9A%84%E8%BA%AB%E4%BB%BD%E6%A0%87%E8%AF%86%E3%80%82-,%E5%91%A8%E8%BE%B9%E6%90%9C%E7%B4%A2,-%E5%91%A8%E8%BE%B9%E6%90%9C%E7%B4%A2API<br/>https://lbs.amap.com/api/webservice/guide/api/georegeo |
| **multi-engine-search** | `TAVILY_API_KEY` | `skill/multi-engine-search/scripts/fetchers/tavily.py` | Tavily API | `test_tavily_only.py` | 联系zhangzhenxiong获取 | https://docs.tavily.com/documentation/api-reference/endpoint/search |
| **multi-engine-search** | `BAIDU_APPBUILDER_API_KEY` | `skill/multi-engine-search/scripts/fetchers/baidu.py` | 百度搜索 API | `test_baidu_only.py` | 联系zhangzhenxiong获取 | https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK |
| **flight-search** | `JUHE_FLIGHT_API_KEY` | `skill/flight-search/scripts/query_flight_api.py` | 聚合数据-航班 API |  | 联系zhangzhenxiong获取 | https://www.juhe.cn/docs/api/id/818 |



---

## 配置方式说明

- **环境变量**：在运行脚本的 shell 中 `export 变量名=你的key`（Linux/macOS）或 `$env:变量名="你的key"`（PowerShell），或在 Cursor/IDE 的运行配置里设置。

## 配置类型说明

| 配置类型 | 含义 |
|----------|------|
| **必要 skill 使用** | 使用该 skill 的正式能力（查火车/天气/周边/多引擎搜索/航班）时必须配置，否则接口会报错或返回“未配置 key”类错误。 |
| **测试代码配置** | 仅用于跑 evals、集成测试或单测真实接口；不配置时测试会 skip 或仅跑不依赖真实 API 的用例。当前表中各 key 均为「必要 skill 使用」；train-ticket-search 的 evals 复用同一 key，multi-engine-search 的 `test_*_only.py` 只做 key 是否存在的检查。 |
