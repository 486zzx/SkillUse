#!/usr/bin/env python3
"""单独测试百度搜索 API：检查 key、请求与返回。"""
import os
import sys

# 从同目录加载
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetchers.baidu import BaiduFetcher

def main():
    key = os.environ.get("BAIDU_APPBUILDER_API_KEY", "")
    print("BAIDU_APPBUILDER_API_KEY set:", bool(key and key.strip()))
    f = BaiduFetcher()
    query = "python"
    print("Query:", repr(query))
    source, items, err = f.fetch(query)
    print("source:", source)
    print("error:", err or "(none)")
    print("items count:", len(items))
    for i, x in enumerate(items[:5]):
        title = (x.get("title") or "")[:60]
        url = (x.get("url") or "")[:70]
        print(f"  [{i+1}] {title}")
        print(f"      {url}")
    return 0 if not err else 1

if __name__ == "__main__":
    sys.exit(main())
