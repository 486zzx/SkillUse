# 航班查询 Skill 测试

基于 `docs/skill内部功能测试用例设计.md` 第 1 节生成。

## 运行方式

```bash
# 在 skill 根目录（flight-search）下执行
cd .cursor/skills/flight-search
python -m pytest evals/test_flight_search.py -v
```

## API Key 配置

- **环境变量**：`JUHE_FLIGHT_API_KEY`（聚合数据航班 API Key）。
- **无 Key 时**：所有带 `@requires_api_key` 的用例（F-E2E-01～04、F-OUT-01/04/05/07/14）会自动 **skip**，其余单元测试照常执行。
- **配置 Key 后**：可先设置环境变量再跑 pytest，E2E 与输出处理用例会真实请求 API。

```powershell
# PowerShell 示例：配置 Key 后跑全量
$env:JUHE_FLIGHT_API_KEY = "你的key"
python -m pytest evals/test_flight_search.py -v
```

## 快速剔除需 API 的用例

若希望**永久不跑**依赖 API 的用例（不配置 Key 且不看到 skip）：

- 打开 `evals/test_flight_search.py`，将 `SKIP_E2E_WHEN_NO_KEY = True` 改为 `False`，并**删除或注释**所有带 `@requires_api_key` 的测试函数；或
- 运行时只跑单元：`pytest evals/test_flight_search.py -v -k "F_LOC or F_DAT or F_SEG or E2E_05 or E2E_06 or E2E_07"`

## 用例与文档对应

| 文档章节     | 用例编号     | 说明 |
|-------------|--------------|------|
| 1.1 出发地/目的地解析 | F-LOC-01～19 | 城市、机场、省份、IATA、空与无效、句中包含 |
| 1.1.1 地理精度/粒度   | F-LOC-20～23, 26, 28～30 | 市+区、路名、无效粒度 |
| 1.2 日期解析         | F-DAT-01～07, 10～11 | 今天/明天/后天、下周一、绝对日期、空与无效 |
| 1.3 多段行程解析     | F-SEG-01～03 | 单段、两段、无效出发地 |
| 1.4 端到端           | F-E2E-01～07 | 正常、无 Key、无效出发地/日期（需 Key 的会 skip） |
| 1.5 输出处理         | F-OUT-01, 04, 05, 07, 14 | 排序、价格、航段（需 Key 的会 skip） |

数据目录默认使用本 skill 的 `references/`，通过 `FLIGHT_DATA_DIR` 可覆盖。
