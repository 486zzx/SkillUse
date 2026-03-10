# 天气查询 Skill 测试

基于 `docs/skill内部功能测试用例设计.md` 第 3 节。

## 运行

```bash
cd .cursor/skills/weather-query/weather-query
python -m pytest evals/test_weather_search.py -v
```

## API Key

- 环境变量：`SENIVERSE_KEY`（或签名方式）
- 无 Key 时：W-E2E-01～04、W-OUT-* 会 skip；W-LOC-05、W-E2E-05 照常执行（脚本可能含默认 key）。

## 用例对应

- W-LOC：地点（空）
- W-E2E：正常、日期/天数、生活指数、空气质量、无 Key
- W-OUT：天数、组合
