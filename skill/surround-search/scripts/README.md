# 周边搜索脚本

## 主入口

- **run_surround_search.py**：一站式周边搜索。必填环境变量 `AMAP_KEY`（高德 Web 服务 API Key）。

### 用法

```bash
# 设置 Key（必填）
export AMAP_KEY="你的高德Key"

# 必填：目标地址（位置参数）；可选：--city --keyword --sort-by --radius --max-results
python run_surround_search.py 北京西站 --city 北京 --keyword 餐厅 --max-results 10
python run_surround_search.py 三里屯 --keyword 咖啡店 --radius 2000 --sort-by distance
```

### 输出

JSON：`{ "success": true|false, "pois": [...], "total_count": N, "query_summary": {...}, "error": "..." }`。  
单条 POI：`name`, `address`, `distance`(米), `poi_type`, `location`(可选)。
