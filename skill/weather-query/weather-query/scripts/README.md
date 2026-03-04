# 天气查询脚本（心知天气）

## 总入口

- **run_weather_search.py**：地点（必填）+ 可选日期、`--days N`、`--with-suggestion`、`--with-air`，输出统一 JSON。

## 认证

- 环境变量 **SENIVERSE_KEY**（私钥），或 **SENIVERSE_UID** + **SENIVERSE_PRIVATE_KEY**（签名验证）。

## 用法

```bash
# 实况 + 默认 3 天逐日
python run_weather_search.py 北京

# 指定日期（明天）并 5 天逐日
python run_weather_search.py 上海 明天 --days 5

# 同时拉取生活指数与空气质量
python run_weather_search.py 北京 --with-suggestion --with-air
```

## 依赖

见上级目录 `requirements.txt`，需安装 `requests`。

## 测试

- **单元/功能/系统测试**：在 weatherPrj 根目录执行 `pytest tests/ -v`。测试用例与评估方法见 `references/测试用例与评估方法.md`。
- **真实环境批量测试**：在 weather-query 目录执行 `python scripts/run_real_env_tests.py`，会跑完全部 16 条真实 API 用例并生成 `references/real_env_test_report.json`。用例全集与结果报告见 `references/真实环境测试用例全集.md`、`references/真实环境测试结果报告.md`。

## API

- 心知天气 v3：实况 now、逐日 daily、生活指数 suggestion、空气质量 air；需 Key 或签名。详见 references/心知天气-API接口文档.md。
