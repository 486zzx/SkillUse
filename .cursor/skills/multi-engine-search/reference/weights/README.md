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
- 入口脚本 `aggregate_search.py` 当前**仅接受上述分类名**，不接收别名；传参时直接写分类名（如 `--search-type 软件开发与IT`）。

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

权重目录固定为 **reference/weights**（本 skill 根目录下），也可通过环境变量覆盖根目录：

```bash
export WEIGHTS_DIR=/path/to/weights   # 可选，覆盖权重根目录
```

**多组权重**：若权重根目录下有多组（每组建一子目录，内含 `engine_weights_by_category.json` 等），**当前请求使用的引擎与组名一致时自动使用该组权重**（组名与引擎列表排序后按下划线拼接一致，如 `baidu`、`bocha`、`baidu_bocha`）。未匹配到或未设置引擎时，由 **reference/weights/current.txt**（单行组名）指定；若无 current.txt 或组无效，则使用 **baidu** 组；若无 `baidu` 子目录则使用根目录（兼容单目录结构）。网格搜索多组（如 `--fusion-sources "baidu;bocha;bocha,baidu"`）跑完后，每组最优会写入并同步到本目录下对应子目录（baidu/、bocha/、baidu_bocha/）。

## 参与聚合的引擎（本 skill 上层目录）

本 skill 实际参与聚合的引擎列表由 **reference/aggregate_engines.txt** 控制（与 weights 同级目录）：每行一个引擎 id。若该文件存在且非空，则只使用文件中列出的引擎（如 `baidu`、`tavily`、`zhipu`）；若不存在则使用环境变量 `AGGREGATE_ENGINES` 或代码默认 `baidu,tavily,zhipu`。这样可固定只使用部分引擎（例如仅 3 个），而不使用权重文件中出现的其他引擎（如 zhipu_std、zhipu_pro、zhipu_quark）。
