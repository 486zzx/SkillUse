---
name: multi-engine-search
description: 多引擎聚合搜索。用户需要「搜一下」「查一下」「找资料」「多源搜索」「聚合搜索」或问需要查网上信息才能回答的问题时，用本 skill 运行聚合搜索脚本，从百度、Tavily、智谱等引擎并行检索并得到整合后的结果。
license: Apache-2.0
---

# 多引擎聚合搜索

用户提出需要查网上信息的问题时，你要先做参数提取：**关键词列表** + **搜索类型** + **搜索模式**。然后运行本 skill 的**聚合搜索脚本**（不传原始问题），脚本按类型与模式选引擎，经过并发检索与统一后处理后输出 JSON。

## 工作流程

```
用户查询
    │
    ├─> 参数提取：
    │    - 搜索类型 --search-type（16 个分类型之一，直接写分类名）
    │    - 搜索模式 --search-mode：Fast（单源）/ Balanced / Precision（多源，可配置）
    │    - 多个 -k（每条关键词一个 -k，仅通过 -k 传入，不支持 stdin）
    │
    ├─> 调用聚合脚本 aggregate_search.py --search-type <type> --search-mode <mode> -k "kw1" -k "kw2"
    │       │
    │       ├─ 按 search_mode 选引擎（Fast=仅 baidu，Balanced/Precision=多源见 reference/search_modes.json）
    │       ├─ 按 search_type 选引擎权重、域名权重（多源时）；单源时排序仅 RRF+域名+BM25
    │       ├─ 关键词 × 选中引擎 全并发请求（关键词间、引擎间均并行）
    │       ├─ URL 规范化 + 同 URL 多源合并
    │       ├─ 重排序：BM25 预过滤 + RRF + 引擎权重（多源时）+ 域名权重
    │       ├─ token 保底 + 总长度限制 + top-k
    │       └─ 输出 JSON：仅 success、results（每条 title/content/url/date）、total_count、error；其余写日志
    │
    └─> 根据 results 组织回复
```

## 执行方式（你必须做的）

1. **准备参数**  
   - **搜索类型 `--search-type`**：根据用户问题所属领域，从下文的「搜索类型（16 类）说明」中选用最匹配的一类，直接写分类名（如 政策法规、医疗医药、软件开发与IT、知识问答 等）。  
   - **搜索模式 `--search-mode`**：`Fast`（默认，仅百度，响应快）、`Balanced`、`Precision`（多源，结果更全）；引擎列表见 `reference/search_modes.json`。  
   - **多个 `-k`**：从用户问题拆出关键词，每条关键词一个 `-k`；**仅通过 `-k` 传参，不支持 stdin**。  
   - **不要传原始问题**：只传 `search_type`、`search_mode` 和 `keywords`。

2. **调用聚合搜索脚本**  
   ```bash
   python <聚合脚本路径> --search-type 软件开发与IT --search-mode Fast -k "关键词1" -k "关键词2" -k "关键词3"
   ```  
   必须至少传一个 `-k`。`--search-type` 不传时默认 `知识问答`，`--search-mode` 不传时默认 `Fast`。脚本向标准输出打印 JSON（仅含 success、results、total_count、error），无需你再手动去重排序。

**脚本路径约定**（换环境也适用，不写死绝对路径）  
- 脚本位于**本 skill 根目录**下的 `scripts/aggregate_search.py`（即与本文档 SKILL.md 同级的 `scripts` 子目录）。  
- 调用时请以**当前环境中本 skill 的安装位置**为基准拼接路径（例如你加载到本 skill 时可知 SKILL.md 所在目录，脚本为同目录下的 `scripts/aggregate_search.py`）。  
- 运行依赖 Python 3；调用百度 API 时需安装 `requests`。

3. **根据脚本输出回答用户**  
   若 `success` 为 true，用 `results` 中的标题（title）、链接（url）、摘要（content）、发布时间（date）组织回答；若为 false，根据 `error` 说明原因并建议用户检查配置或重试。

## 输出结构（脚本返回的 JSON）

脚本**标准输出**仅包含以下字段；其余数据（sources_used、search_type、selected_engines、stats 等）写入日志文件（`AGGREGATE_LOG_PATH`），便于排查与统计。

```yaml
success: true/false
results: [ { title, content, url, date }, ... ]   # 每条仅此四字段：标题、内容摘要、链接、发布时间
total_count: number
error: "" 或错误说明
```

你只需解析该 JSON 并据此生成回复，**不要**再自行调用多个搜索引擎或手动做合并与去重。

## 参数与环境

**所有配置项统一在 `scripts/config.py` 中维护**（环境变量名、默认值、说明）。主要项如下：

| 说明         | 方式 |
|--------------|------|
| 参与聚合的引擎池 | 优先读本 skill 根目录下 `reference/aggregate_engines.txt`（每行一个引擎 id）；无该文件时用环境变量 `AGGREGATE_ENGINES`（逗号分隔）；再不设则默认 `baidu,tavily,zhipu`。智谱需配置 `ZHIPU_API_KEY` 才会返回结果。 |
| 搜索模式 | `--search-mode`：`Fast`（仅 baidu）、`Balanced`、`Precision`；各模式使用的引擎列表与**整体并行搜索墙钟超时（秒）**见 `reference/search_modes.json`（如 Fast=5、Balanced=8、Precision=12），到点后未返回的请求不再等待；可与池子取交集。单源（Fast）时排序仅用 RRF+域名+BM25，不用引擎权重。 |
| 搜索类型 | `--search-type`：16 个分类型之一（见下「搜索类型说明」），直接写分类名；多源时据此选择引擎权重与域名权重。 |
| 权重组 | 从 **reference/weights** 获取：当前组由 `reference/weights/current.txt`（单行组名）指定；若该组无专门权重则使用 **baidu** 组，详见 `reference/weights/README.md`。 |
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

| 日志 | `AGGREGATE_LOG_PATH` 日志路径；每次请求的完整输入输出异步写入该 JSONL 文件。 |
| 百度 / Tavily / 智谱 | 各引擎 API Key：`BAIDU_APPBUILDER_API_KEY`、`TAVILY_API_KEY`、`ZHIPU_API_KEY`（仅环境变量，无默认值）。 |

## 使用示例

**示例 1：软件开发与IT 搜索（默认 Fast 单源）**

```text
用户: python是什么？想学一下

1. 从问题拆出/扩展关键词，不传用户原句
2. 执行: python <skill 根目录>/scripts/aggregate_search.py --search-type 软件开发与IT -k "python" -k "python 教程"
3. 用 results 中每条 title、content、url、date 组织回答。
```

**示例 2：多源 Precision 模式**

```text
用户: Python 3.12 新特性有哪些？要全面一点

1. 使用 --search-mode Precision 启用多引擎
2. 执行: python <skill 根目录>/scripts/aggregate_search.py --search-type 软件开发与IT --search-mode Precision -k "Python 3.12 新特性"
3. 解析 results（title/content/url/date）回答。
```

**示例 3：对比类**

```text
用户: Rust 和 Go 在 2024 年性能对比

1. 用多个 -k 扩展: -k "Rust Go 性能对比" -k "Rust 2024" -k "Go 2024 性能"
2. 执行: python <skill 根目录>/scripts/aggregate_search.py --search-type 软件开发与IT -k "Rust Go 性能对比" -k "Rust 2024" -k "Go 2024 性能"
3. 根据 results 组织对比式回答。
```

**示例 4：失败时**

```text
若 success 为 false，根据 error 提示用户（如未配置 API Key、无有效结果等）；完整 stats、sources_used 等写入日志（AGGREGATE_LOG_PATH），可供排查。
```

