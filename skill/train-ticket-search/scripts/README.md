# 列车班次查询脚本

本目录用于放置班次查询工具的实现脚本，供 SKILL 调用。

## 主入口

- **`run_train_search.py`**：总入口，接收出发站、到达站、**出发时间**（自然语言，如「明天」「后天下午五点后」）、可选 **`--arrival-time`**（自然语言时间范围，如「五点后」）及车型、排序。时间由 **`time_utils.py`** 用 jionlp 归一为单日日期(YYYY-MM-DD)+时间段(HH:MM)，再调用火车票 API、筛选排序后输出统一 JSON。

## 实现约定

- 需求、架构、接口与测试用例见项目 **`docs/train-ticket-search/`**：
  - `start.md`：需求与流程；**API接口信息**（当前为航班示例，实现时需使用火车票接口）
  - `requirements.md`：功能与非功能需求
  - `architecture.md`：模块划分（参数转化、查询调度、筛选排序、结果整合）
  - `api.md`：入参/出参、车型 [G(高铁/城际), D(动车), Z(直达特快), T(特快), K(快速), O(其他), F(复兴号), S(智能动车组)]、排序枚举
  - `test-cases.md`：功能/边界/并发/E2E 用例
- **`time_utils.py`**：自然语言时间 → 单日日期+时间段，**仅依赖 jionlp.parse_time**（无 fallback）。需安装 jionlp；解析失败时返回 None，由主入口报错。直接采用 jionlp 的解析结果，不做日期/年份修正。
- 多用户并发、工具内多子工具并发、模块低耦合等见 `docs/train-ticket-search/requirements.md`。

## 调用示例（与 SKILL.md 一致）

```bash
python scripts/run_train_search.py 北京 上海 明天
python scripts/run_train_search.py 杭州 南京 "后天下午五点后" --arrival-time "五点后" --train-type G --sort-by price_asc
```

输出为 JSON：`success`、`trains`、`total_count`、`error`（失败时）。

**环境变量**：需配置 **`JUHE_TRAIN_API_KEY`**（聚合个人中心 → 数据中心 → 我的API）。接口地址与参数见 `docs/train-ticket-search/start.md`「API接口信息」。排查空结果时可在同目录下设置 **`JUHE_TRAIN_DEBUG=1`**，脚本会在 stderr 打印请求 URL（key 已脱敏）与接口返回的 error_code/reason/result 条数。
