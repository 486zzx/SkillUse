# reference 配置说明

## 引擎配置（两处配合使用）

| 文件 | 作用 |
|------|------|
| **aggregate_engines.txt** | **引擎池**：允许参与聚合的引擎白名单（每行一个 id）。只有出现在这里的引擎才会被用到。 |
| **search_modes.json** | **各模式用哪些引擎**：Fast/Balanced/Precision 下各自使用的引擎列表 + 超时（秒）。 |

**实际生效逻辑**：先按 `--search-mode` 从 `search_modes.json` 取出该模式的 `engines`，再与 `aggregate_engines.txt` 的池子做**交集**、保序。因此：

- `search_modes.json` 里写的引擎必须在池子里存在，否则会被过滤掉。
- 两处保持一致即可，不冲突；若只改一处，以池子为准（池子没有的引擎不会被用）。

当前与三组权重（baidu / bocha / baidu_bocha）一致：池子与模式均为 **baidu + bocha**；Fast=仅 baidu，Balanced/Precision=baidu+bocha。

## 权重

见 `weights/README.md`。权重组与引擎组对应时（如只用 baidu → 用 weights/baidu/，用 baidu+bocha → 用 weights/baidu_bocha/）会自动选用对应目录。
