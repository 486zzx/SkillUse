# 数据文件路径

本目录为默认数据目录，需包含以下文件（用于地点 → IATA 解析）：

- `city_map.json` — 有机场城市名与 IATA 码
- `province_map.json` — 省份名与省会 IATA 码
- `airport_list.json` — 机场列表（格式 [{"iata":"PVG","name_zh":"上海浦东国际机场"}, ...]）
- `nearest_airport_map.json` — 无机场城市与最近机场三字码（格式 [{"城市":"昌吉","机场三字码":"URC"}, ...]）

通过环境变量 **FLIGHT_DATA_DIR** 可指定其他数据目录；未设置时脚本使用本目录。
