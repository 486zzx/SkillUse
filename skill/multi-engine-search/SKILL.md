---
name: multi-engine-search
description: 多引擎聚合搜索。用户需要「搜一下」「查一下」「找资料」「多源搜索」「聚合搜索」或问需要查网上信息才能回答的问题时，用本 skill 运行聚合搜索脚本，从百度与 Tavily 并行检索并得到整合后的结果。
license: Apache-2.0
---

# 多引擎聚合搜索

用户输入一个问题或查询时，通过运行本 skill 提供的**聚合搜索脚本**，从多个搜索源并行获取结果，经脚本内**汇总、去重、排序、过滤**后得到统一格式的 JSON，你再根据该结果回答用户。

## 工作流程

```
用户查询
    │
    ├─> 第 1 个参数：用户问题 query（如「python是什么」）
    ├─> 多个 -k：每条搜索词一个 -k（如 -k "python" -k "python 教程"），由你从问题中拆出或扩展
    │
    ├─> 调用聚合脚本 aggregate_search.py "query" -k "kw1" -k "kw2" -k "kw3"
    │       │
    │       ├─ 无 keywords 时：单 query 可选改写，多引擎并行
    │       ├─ 有 keywords 时：每个关键词 × 每个引擎 全部并行请求（关键词间、引擎间均并行）
    │       ├─ URL 规范化 + 同 URL 多源合并
    │       ├─ 重排序（Reranker + 域优先级 + 垃圾过滤），以 query 为相关度依据
    │       ├─ 关键词保底 + 条数上限
    │       └─ 输出 JSON（含 results、stats、query_rewrite.keywords）
    │
    └─> 根据 results 与 stats 组织回复
```

## 执行方式（你必须做的）

1. **准备参数**  
   - **第 1 个参数**：用户问题（如「python是什么」）。  
   - **多个 -k**：每条搜索词一个 `-k`，由你从问题中拆出或扩展（如 `-k "python" -k "python 教程" -k "python 学习 26 教程"`）。脚本会对每个关键词在每个引擎上并行搜索。

2. **调用聚合搜索脚本**  
   ```bash
   python <聚合脚本路径> "用户问题" -k "关键词1" -k "关键词2" -k "关键词3"
   ```
   不传 `-k` 时：仅用用户问题在多引擎上搜索（单 query）。  
   脚本向标准输出打印 JSON，无需你再做去重、排序或格式化。

**脚本路径约定**（换环境也适用，不写死绝对路径）  
- 脚本位于**本 skill 根目录**下的 `scripts/aggregate_search.py`（即与本文档 SKILL.md 同级的 `scripts` 子目录）。  
- 调用时请以**当前环境中本 skill 的安装位置**为基准拼接路径（例如你加载到本 skill 时可知 SKILL.md 所在目录，脚本为同目录下的 `scripts/aggregate_search.py`）。  
- 运行依赖 Python 3；调用百度 API 时需安装 `requests`。

3. **根据脚本输出回答用户**  
   若 `success` 为 true，用 `results` 中的标题、链接、摘要组织回答；若为 false，根据 `error` 说明原因并建议用户检查配置或重试。  
   **用上 suggestions**：当 `query_rewrite.suggestions` 非空时（技术/开发者类查询会有），在回复中可提示用户「若结果不够精准，可以再试：」并列出其中 1～3 条建议搜索词（如「Python 文档」「Python site:docs.python.org」），便于用户换词或限定站点再搜。

## 输出结构（脚本返回的 JSON）

```yaml
success: true/false
results: [ { title, url, content, sources, search_keywords?, score?, date?, breadcrumbs?, aggregate_index? }, ... ]   # sources=引擎列表(如 ["baidu","tavily"])，search_keywords=命中该条时使用的关键词列表
total_count: number
sources_used: [ "baidu", "tavily" ]
error: "" 或错误说明
query_rewrite: { original, best_query, keywords?, suggestions, is_developer_query }   # suggestions 供你展示给用户作「可尝试的其它搜索词」（如 query+文档、query+site:xxx）
stats:                                        # 统计信息
  total_original: number                     # 去重前条数
  total_after_dedup: number                  # 去重与过滤后条数
  dedup_rate: number                         # 去重率 %
  engine_counts: { "baidu": n, "tavily": m } # 各引擎原始条数
  duration_ms: number                        # 本次请求耗时（毫秒）
```

你只需解析该 JSON 并据此生成回复，**不要**再自行调用多个搜索引擎或手动做合并与去重。

## 参数与环境

| 说明         | 方式 |
|--------------|------|
| 参与聚合的引擎 | 环境变量 `AGGREGATE_ENGINES`，逗号分隔，如 `baidu,tavily`；不设则默认启用已注册的引擎。 |
| 是否查询改写   | 默认开启。设 `AGGREGATE_QUERY_REWRITE=0` 或 `false` 关闭。 |
| 百度 / Tavily | 需配置 `BAIDU_APPBUILDER_API_KEY`、`TAVILY_API_KEY`（或项目约定方式）。 |

## 使用示例

**示例 1：用户问题 + 多个 -k（关键词×引擎并行）**

```text
用户: python是什么？想学一下

1. 第 1 参数: "python是什么"
2. 多个 -k: -k "python" -k "python 教程" -k "python 学习 26 教程"（由你从问题拆出或扩展）
3. 执行: python <skill 根目录>/scripts/aggregate_search.py "python是什么" -k "python" -k "python 教程" -k "python 学习 26 教程"
4. 用 results 与 stats 组织回答。
```

**示例 2：仅用户问题（不传 -k）**

```text
用户: Python 3.12 新特性有哪些？

1. 只传 query，不传 -k
2. 执行: python <skill 根目录>/scripts/aggregate_search.py "Python 3.12 新特性"
3. 单 query 多引擎，解析 results 与 stats 回答。
```

**示例 3：对比类**

```text
用户: Rust 和 Go 在 2024 年性能对比

1. query: "Rust 和 Go 2024 性能对比"，用多个 -k 扩展: -k "Rust Go 性能对比" -k "Rust 2024" -k "Go 2024 性能"
2. 执行脚本传入 query 与多个 -k，根据 results 组织对比式回答。
```

**示例 4：失败时**

```text
若 success 为 false，根据 error 提示用户（如未配置 API Key、无有效结果等）；stats 中仍有 duration_ms、engine_counts 可供排查。
```

