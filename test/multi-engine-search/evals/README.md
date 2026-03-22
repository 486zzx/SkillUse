# 多引擎聚合搜索 Skill 测试

基于 `docs/skill内部功能测试用例设计.md` 第 5 节。

## 运行

```bash
cd .cursor/skills/multi-engine-search
python -m pytest evals/test_aggregate_search.py -v
```

## API Key

- 环境变量：`TAVILY_API_KEY`、`BAIDU_APPBUILDER_API_KEY`（两者都需配置 E2E 才不 skip）
- 无 Key 时：M-QK-01/02、M-OUT-* 会 skip；M-QK-03、M-RER-*（Pipeline 单元）照常执行。

## 用例对应

- M-QK：无 query 无 k、仅 query、query+多 k
- M-OUT：条数上限、无 site 语法
- M-RER：URL 规范化、去重合并、重排序、垃圾过滤、run_pipeline
