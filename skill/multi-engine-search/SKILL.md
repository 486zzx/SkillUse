---
name: multi-engine-search
description: 多引擎聚合搜索。用户需要「搜一下」「查一下」「找资料」「多源搜索」「聚合搜索」或问需要查网上信息才能回答的问题时，用本 skill 运行聚合搜索脚本，从百度、Tavily、智谱等引擎并行检索并得到整合后的结果。
license: Apache-2.0
---

# 多引擎聚合搜索

用户提出需要查网上信息的问题时，你要先做参数提取：**关键词列表** + **搜索类型**。然后运行本 skill 的**聚合搜索脚本**（不传原始问题），脚本按搜索类型决定引擎与权重，经过并发检索与统一后处理后输出 JSON。

## 工作流程

```
用户查询
    │
    ├─> 参数提取：
    │    - 搜索类型 --search-type（16 个分类型之一，或别名 general/code/news）
    │    - 多个 -k（每条关键词一个 -k）
    │
    ├─> 调用聚合脚本 aggregate_search.py --search-type <type> -k "kw1" -k "kw2" -k "kw3"
    │       │
    │       ├─ 按 search_type 选择引擎、引擎权重、域名权重
    │       ├─ 关键词 × 选中引擎 全并发请求（关键词间、引擎间均并行）
    │       ├─ URL 规范化 + 同 URL 多源合并
    │       ├─ 可选：results 总长度上限（默认 2500，--max-total-chars 覆盖）
    │       ├─ 重排序：BM25 预过滤 + Rank Fusion + 引擎权重 + 域名权重
    │       ├─ token 保底 + 总长度限制 + top-k
    │       └─ 输出 JSON（含 results、stats、query_rewrite.keywords）
    │
    └─> 根据 results 与 stats 组织回复
```

## 执行方式（你必须做的）

1. **准备参数**  
   - **搜索类型 `--search-type`**：根据用户问题所属领域，从下文的「搜索类型（16 类）说明」中选用最匹配的一类（如政策法规、医疗医药、软件开发与IT 等）；也可用别名 `general`/`code`/`news`（分别对应 知识问答/软件开发与IT/新闻资讯）。  
   - **多个 `-k`**：从用户问题拆出关键词，每条关键词一个 `-k`。  
   - **不要传原始问题**：只传 `search_type` 和 `keywords`。

2. **调用聚合搜索脚本**  
   ```bash
   python <聚合脚本路径> --search-type code -k "关键词1" -k "关键词2" -k "关键词3"
   ```  
   必须至少传一个 `-k`。`--search-type` 不传时默认 `general`。脚本向标准输出打印 JSON，无需你再手动去重排序。

**脚本路径约定**（换环境也适用，不写死绝对路径）  
- 脚本位于**本 skill 根目录**下的 `scripts/aggregate_search.py`（即与本文档 SKILL.md 同级的 `scripts` 子目录）。  
- 调用时请以**当前环境中本 skill 的安装位置**为基准拼接路径（例如你加载到本 skill 时可知 SKILL.md 所在目录，脚本为同目录下的 `scripts/aggregate_search.py`）。  
- 运行依赖 Python 3；调用百度 API 时需安装 `requests`。

3. **根据脚本输出回答用户**  
   若 `success` 为 true，用 `results` 中的标题、链接、摘要组织回答；若为 false，根据 `error` 说明原因并建议用户检查配置或重试。

## 输出结构（脚本返回的 JSON）

```yaml
success: true/false
results: [ { title, url, content, sources, search_keywords?, score?, date?, breadcrumbs?, aggregate_index? }, ... ]   # sources=引擎列表(如 ["baidu","tavily"])，search_keywords=命中该条时使用的关键词列表
total_count: number
sources_used: [ "baidu", "tavily", "zhipu" ]  # 视启用的引擎而定
error: "" 或错误说明
search_type: 本次使用的分类（16 类之一或别名，如 "知识问答"、"政策法规"、"code" 等）
selected_engines: [ "baidu", "tavily", "zhipu" ]   # 本次实际参与并发的引擎
query_rewrite: { keywords }   # 兼容字段，仅回传关键词
stats:                                        # 统计信息
  total_original: number                     # 去重前条数
  total_after_dedup: number                  # 去重与过滤后条数
  dedup_rate: number                         # 去重率 %
  engine_counts: { "baidu": n, "tavily": m, "zhipu": k } # 各引擎原始条数（视启用引擎而定）
  duration_ms: number                        # 本次请求耗时（毫秒）
```

你只需解析该 JSON 并据此生成回复，**不要**再自行调用多个搜索引擎或手动做合并与去重。

## 参数与环境

**所有配置项统一在 `scripts/config.py` 中维护**（环境变量名、默认值、说明）。主要项如下：

| 说明         | 方式 |
|--------------|------|
| 参与聚合的引擎 | 优先读本 skill 根目录下 `reference/aggregate_engines.txt`（每行一个引擎 id，默认仅 `baidu`、`tavily`、`zhipu`，不含 zhipu_std/zhipu_pro/zhipu_quark 等）；无该文件时用环境变量 `AGGREGATE_ENGINES`（逗号分隔）；再不设则默认 `baidu,tavily,zhipu`。智谱需配置 `ZHIPU_API_KEY` 才会返回结果。 |
| 搜索类型 | `--search-type`：16 个分类型之一（见下「搜索类型说明」）或 general/code/news 别名；脚本据此选择引擎与权重。 |
| 输出长度控制   | 默认 2500（`config.DEFAULT_MAX_TOTAL_CHARS`）；命令行入参 `--max-total-chars N` 可覆盖。单条上限由总长推导（总长/5 且不超过 12000）。 |

## 搜索类型（16 类）说明

选择 `--search-type` 时，根据用户问题所属领域选用下表对应分类，以便使用该分类的引擎与域名权重，提高结果相关性。

| 分类名 | 适用场景与区别 |
|--------|----------------|
| **政策法规** | 国家法律、行政法规、部门规章、地方条例、监管政策、政府通知、政策解读及官方文件等权威政策信息。 |
| **新闻资讯** | 国内外新闻报道、社会热点、政策动态、科技商业新闻、突发事件及主流媒体资讯。 |
| **证券投资** | 股票、基金、债券、期货等资本市场信息，上市公司公告、财报、市场行情、投资分析与讨论。 |
| **企业工商** | 企业工商注册、股东结构、经营范围、变更记录、关联企业、风险信息及商业尽调；企业/公司基本信息、组织架构、总部或分支机构所在地、办公地址等。 |
| **医疗医药** | 疾病知识、诊疗指南、药品与医疗器械信息、医学研究进展、医生专业内容及医疗健康科普。 |
| **技术标准** | 国家标准、行业标准、团体标准、技术规范、标准公告及标准全文查询等标准化信息。 |
| **学术论文** | 学术论文、期刊文章、学术综述、科研成果、研究报告及各类学术研究资料。 |
| **软件开发与IT** | 软件开发、编程语言、报错解决、API 文档、算法、云计算、人工智能技术框架、开源项目及工程实践等硬核技术内容。 |
| **数码与科技资讯** | 智能手机、电脑硬件、数码家电等 3C 评测与导购，前沿科技趋势、互联网大厂动态、AI 行业新闻及科技创投分析；**不含**企业基本信息、公司地址、组织架构（属「企业工商」），仅限产品与行业资讯。 |
| **知识问答** | 概念解释、经验分享、常识性问题、生活技巧、用户讨论及中文互联网泛知识内容。 |
| **教育考试** | 高考、考研、公务员考试、职业资格考试、招生政策、升学信息及各类教育考试相关内容；**不含**学校/机构沿革、建校时间等历史常识（属「知识问答」）。 |
| **自然地理与防灾** | 自然灾害预警、应急管理政策、地理常识、生态环境保护、水利工程及地球科学科普；**不含**日常天气预报和空气质量查询。 |
| **宏观经济** | 宏观经济指标、统计数据、货币政策、财政政策、金融监管、经济运行情况及官方经济数据。 |
| **生活消费** | 餐饮美食、购物消费、旅游出行、酒店住宿、本地服务、汽车消费及日常生活消费信息。 |
| **体育娱乐** | 体育赛事、赛程比分、体育新闻、影视剧、电影、音乐、明星动态及娱乐产业相关内容。 |
| **知识产权与专利** | 专利查询、商标注册、版权保护、知识产权法律法规及相关案例分析。 |

**别名**（便于简短入参）：`general` → 知识问答，`code` → 软件开发与IT，`news` → 新闻资讯。

| 日志与调试   | `AGGREGATE_LOG_PATH` 日志路径；`AGGREGATE_TIMING=1` 时向 stderr 输出各阶段耗时。 |
| 百度 / Tavily / 智谱 | 各引擎 API Key：`BAIDU_APPBUILDER_API_KEY`、`TAVILY_API_KEY`、`ZHIPU_API_KEY`（仅环境变量，无默认值）。 |

## 使用示例

**示例 1：code 搜索（关键词×引擎并行）**

```text
用户: python是什么？想学一下

1. 从问题拆出/扩展关键词，不传用户原句
2. 执行: python <skill 根目录>/scripts/aggregate_search.py --search-type code -k "python" -k "python 教程" -k "python 学习 26 教程"
3. 用 results 与 stats 组织回答。
```

**示例 2：单关键词**

```text
用户: Python 3.12 新特性有哪些？

1. 传一个 -k 即可
2. 执行: python <skill 根目录>/scripts/aggregate_search.py --search-type news -k "Python 3.12 新特性"
3. 解析 results 与 stats 回答。
```

**示例 3：对比类**

```text
用户: Rust 和 Go 在 2024 年性能对比

1. 用多个 -k 扩展: -k "Rust Go 性能对比" -k "Rust 2024" -k "Go 2024 性能"
2. 执行: python <skill 根目录>/scripts/aggregate_search.py --search-type code -k "Rust Go 性能对比" -k "Rust 2024" -k "Go 2024 性能"
3. 根据 results 组织对比式回答。
```

**示例 4：失败时**

```text
若 success 为 false，根据 error 提示用户（如未配置 API Key、无有效结果等）；stats 中仍有 duration_ms、engine_counts 可供排查。
```

