# 权重文件目录

**权重与分类均由此目录下的 JSON 提供，代码中不配置、不虚构分类。**

未放置某文件时：引擎列表与 RRF/融合系数使用最小兜底（等权、默认引擎列表），以保证脚本可运行。

## 文件说明

| 文件 | 说明 |
|------|------|
| `engine_weights_by_category.json` | 各分类下引擎权重与参与引擎；可选顶层 `aliases` 将 general/code/news 映射到某分类 |
| `domain_weights_by_category.json` | 各分类下域名→权重，用于结果重排；无此文件时域名项使用中性分 |
| `rerank_policy.json` | 融合权重（w_rrf/w_engine/w_domain）与 RRF k、top_k 等 |

## 分类来源

- 有效分类 = `engine_weights_by_category.json` 中 `by_category` 的键（如 政策法规、知识问答、软件开发与IT）。
- 若需兼容 `--search-type general/code/news`，请在 `engine_weights_by_category.json` 顶层增加 `aliases`，例如：
  ```json
  "aliases": {
    "general": "知识问答",
    "code": "软件开发与IT",
    "news": "新闻资讯"
  }
  ```
- 直接传入分类名（如 `政策法规`）时，只要该名在 `by_category` 中即会使用对应权重。

## 如何生成与同步

在 SearchEvalEngine 中：**测试模块**算指标，**优化模块**建权重并自动同步到本目录：

```bash
# 1. 测试模块：先算指标（若已有可跳过）
python metrics/run_metrics.py --run api
# 或分别：--run engine / --run category / --run domain

# 2. 优化模块：根据指标构建权重并同步到本目录
python metrics/run_optimization.py --run weights
```

同步时会保留本目录下 `engine_weights_by_category.json` 中已有的 `aliases`（如 general/code/news）。当前使用的权重版本见本目录下的 `weights_origin.json`（生成时间与数据来源）。

通过环境变量指定其他权重目录：

```bash
export WEIGHTS_DIR=/path/to/weights
```

## 参与聚合的引擎（本 skill 上层目录）

本 skill 实际参与聚合的引擎列表由 **reference/aggregate_engines.txt** 控制（与 weights 同级目录）：每行一个引擎 id。若该文件存在且非空，则只使用文件中列出的引擎（如 `baidu`、`tavily`、`zhipu`）；若不存在则使用环境变量 `AGGREGATE_ENGINES` 或代码默认 `baidu,tavily,zhipu`。这样可固定只使用部分引擎（例如仅 3 个），而不使用权重文件中出现的其他引擎（如 zhipu_std、zhipu_pro、zhipu_quark）。
